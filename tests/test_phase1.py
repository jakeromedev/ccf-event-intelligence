import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.aggregation import (
    active_batch,
    data_quality,
    event_summaries,
    overview_metrics,
    overview_registrants,
    participant_profile_metrics,
    satellite_metrics,
)
from app.classifier import classify_affiliation
from app.db import get_db
from app.import_history import import_history
from app.importer import process_batch, store_validation, validate_batch, validate_file


ROOT = Path(__file__).resolve().parents[1]
TICKET_FIELDS = [
    "Id", "Slug", "Event Name", "Ticket Code", "Control Number", "Ticket Status",
    "Payment Status", "Buyer Reference Number", "Check-in Date Time",
]
BUYER_FIELDS = [
    "Id", "Slug", "Event Name", "Buyer Reference Number", "Payment Status",
    "Quantity", "Gross Amount", "Amount Paid",
]
REGISTRANT_FIELDS = [
    "ID", "Event Name", "Event Slug", "Registration Code", "Ticket Code", "Ticket Status",
    "First Name", "Last Name", "Email Address", "Mobile Number", "Are You Attending Ccf",
    "Gender", "Birth Month", "Birth Year",
    "Are You From A Local Or International Satellite", "Which Local Satellite",
    "Which International Satellite",
]
REGISTRANT_B1G_FIELDS = [
    "ID", "Event Name", "Event Slug", "Registration Code", "Ticket Code", "Ticket Status",
    "First Name", "Last Name", "Email Address", "Mobile Number", "Gender", "Birth Month",
    "Birth Year", "B1g Satellite Hub", "B1g Satellite", "Specify B1g Satellite",
]


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class ClassifierTests(unittest.TestCase):
    def test_approved_precedence_and_categories(self):
        cases = [
            ({"Are You Attending Ccf": "Yes", "Are You From A Local Or International Satellite": "Local Satellite", "Which Local Satellite": "CCF Main"}, "CCF Main", "CCF Main"),
            ({"Are You Attending Ccf": "Yes", "Are You From A Local Or International Satellite": "Local Satellite", "Which Local Satellite": "Eastwood"}, "Local Satellite", "Eastwood"),
            ({"Are You Attending Ccf": "Yes", "Are You From A Local Or International Satellite": "International Satellite", "Which International Satellite": "Singapore"}, "International Satellite", "Singapore"),
            ({"Are You Attending Ccf": "No"}, "Non-CCF", None),
            ({"Are You Attending Ccf": ""}, "Unknown", None),
        ]
        for row, category, satellite in cases:
            with self.subTest(category=category):
                result = classify_affiliation(row)
                self.assertEqual(category, result.affiliation)
                self.assertEqual(satellite, result.satellite_name)

    def test_non_ccf_precedence_flags_satellite_contradiction(self):
        result = classify_affiliation({
            "Are You Attending Ccf": "No",
            "Are You From A Local Or International Satellite": "Local Satellite",
            "Which Local Satellite": "CCF Main",
        })
        self.assertEqual("Non-CCF", result.affiliation)
        self.assertTrue(result.contradictory)

    def test_b1g_affiliation_schema_uses_approved_precedence(self):
        cases = [
            ({"B1g Satellite Hub": "CCF Center", "B1g Satellite": "B1G Main"}, "CCF Main", "B1G Main"),
            ({"B1g Satellite Hub": "Metro East", "B1g Satellite": "B1G Antipolo"}, "Local Satellite", "B1G Antipolo"),
            ({"B1g Satellite Hub": "Others", "B1g Satellite": "Others", "Specify B1g Satellite": "B1G Naga"}, "Local Satellite", "B1G Naga"),
            ({"B1g Satellite Hub": "ICP", "B1g Satellite": "Others", "Specify B1g Satellite": "B1G Singapore"}, "International Satellite", "B1G Singapore"),
            ({"B1g Satellite Hub": "", "B1g Satellite": ""}, "Unknown", None),
        ]
        for row, category, satellite in cases:
            with self.subTest(category=category, satellite=satellite):
                result = classify_affiliation(row)
                self.assertEqual(category, result.affiliation)
                self.assertEqual(satellite, result.satellite_name)


class EventIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = str(root / "test.sqlite3")
        self.staging_dir = str(root / "staging")
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATABASE": self.database,
            "STAGING_DIR": self.staging_dir,
        })
        self.paths = {
            "tickets": root / "anything-a.csv",
            "buyers": root / "anything-b.csv",
            "registrants": root / "anything-c.csv",
        }
        self._write_fixture()
        with self.app.app_context():
            self.event_a = get_db().execute("INSERT INTO events (name) VALUES ('Event A')").lastrowid
            self.event_b = get_db().execute("INSERT INTO events (name) VALUES ('Event B')").lastrowid
            get_db().commit()

    def tearDown(self):
        self.temp.cleanup()

    def _write_fixture(self, registrant_limit=None):
        buyer = lambda identifier, reference: {
            "Id": identifier, "Slug": "event-1", "Event Name": "Event One",
            "Buyer Reference Number": reference, "Payment Status": "Payment Validated",
            "Quantity": "1", "Gross Amount": "100", "Amount Paid": "100",
        }
        ticket = lambda identifier, code, buyer_ref, checked="": {
            "Id": identifier, "Slug": "event-1", "Event Name": "Event One", "Ticket Code": code,
            "Control Number": identifier, "Ticket Status": "Assigned", "Payment Status": "Payment Validated",
            "Buyer Reference Number": buyer_ref, "Check-in Date Time": checked,
        }
        registrant = lambda identifier, code, attending, scope="", local="", international="", gender="", birth_month="", birth_year="": {
            "ID": identifier, "Event Name": "Event One", "Event Slug": "event-1",
            "Registration Code": "R-{}".format(identifier), "Ticket Code": code, "Ticket Status": "Assigned",
            "First Name": "Test", "Last Name": "Registrant", "Email Address": "test{}@example.com".format(identifier),
            "Mobile Number": "0900", "Are You Attending Ccf": attending,
            "Gender": gender, "Birth Month": birth_month, "Birth Year": birth_year,
            "Are You From A Local Or International Satellite": scope,
            "Which Local Satellite": local, "Which International Satellite": international,
        }
        write_csv(self.paths["buyers"], BUYER_FIELDS, [buyer("1", "B-1"), buyer("2", "B-ORPHAN")])
        write_csv(self.paths["tickets"], TICKET_FIELDS, [
            ticket("1", "T-MAIN", "B-1", "2025-09-05 08:00:00"),
            ticket("2", "T-LOCAL", "B-1", "2025-09-05 08:01:00"),
            ticket("3", "T-INTL", "B-1", "2025-09-05 08:02:00"),
            ticket("4", "T-NON", "B-1", "2025-09-05 08:03:00"),
            ticket("5", "T-UNKNOWN", "B-1"),
            ticket("6", "T-NOREG", "B-1"),
        ])
        rows = [
            registrant("1", "T-MAIN", "Yes", "Local Satellite", "CCF Main", gender="Male", birth_month="January", birth_year="2000"),
            registrant("2", "T-LOCAL", "Yes", "Local Satellite", "Eastwood", gender="Female", birth_month="October", birth_year="1990"),
            registrant("3", "T-INTL", "Yes", "International Satellite", international="Singapore", gender="Prefer not to say", birth_month="June", birth_year="1980"),
            registrant("4", "T-NON", "No", "Local Satellite", "CCF Main", gender="Nonbinary", birth_month="May", birth_year="1970"),
            registrant("5", "T-UNKNOWN", ""),
        ]
        write_csv(self.paths["registrants"], REGISTRANT_FIELDS, rows[:registrant_limit])

    def _process(self, event_id):
        staged = {key: (str(path), path.name) for key, path in self.paths.items()}
        validation = validate_batch(staged)
        self.assertTrue(validation.valid)
        with self.app.app_context():
            batch_id = store_validation(get_db(), validation, event_id)
            process_batch(get_db(), batch_id)
        return batch_id

    def _add_satellite_ranking_fixture(self, batch_id):
        """Add aggregate-only rows that exercise ranking pagination and sorting."""
        rows = []
        sequence = 100

        def add(name, count, checked):
            nonlocal sequence
            for index in range(count):
                sequence += 1
                rows.append((
                    batch_id,
                    "extra-{}".format(sequence),
                    "event-1",
                    "R-EXTRA-{}".format(sequence),
                    "T-EXTRA-{}".format(sequence),
                    "Assigned",
                    "Local Satellite",
                    name,
                    1,
                    1 if index < checked else 0,
                ))

        add("Alpha Hub", 3, 3)
        add("Beta Hub", 2, 0)
        for number in range(1, 13):
            add("Site {:02d}".format(number), 1, number % 2)

        with self.app.app_context():
            get_db().executemany(
                """
                INSERT INTO registrants (
                    batch_id, source_id, event_slug, registration_code,
                    ticket_code, ticket_status, affiliation, satellite_name,
                    ticket_matched, checked_in
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            get_db().commit()

    def _add_quality_fixture(self, batch_id):
        rows = []
        entities = ("registrants", "tickets", "buyers", "batch")
        for number in range(1, 13):
            rows.append((
                batch_id,
                "error" if number % 2 == 0 else "warning",
                "custom_{:02d}".format(number),
                entities[(number - 1) % len(entities)],
                1000 + number,
                "DQ-{:02d}".format(number),
                "Synthetic issue message {:02d}.".format(number),
            ))
        for number in range(7):
            rows.append((
                batch_id,
                "error",
                "custom_samples",
                "buyers",
                2000 + number,
                "SAMPLE-{:02d}".format(number),
                "Repeated sample group.",
            ))
        with self.app.app_context():
            get_db().executemany(
                """
                INSERT INTO validation_issues (
                    batch_id, severity, category, entity_type,
                    source_row, source_identifier, message
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            get_db().commit()

    def test_event_creation_and_multiple_events(self):
        client = self.app.test_client()
        response = client.post("/events", data={"name": "Welcome Retreat 2026"})
        self.assertEqual(302, response.status_code)
        with self.app.app_context():
            names = [row["name"] for row in get_db().execute("SELECT name FROM events ORDER BY id")]
        self.assertEqual(["Event A", "Event B", "Welcome Retreat 2026"], names)
        self.assertIn("/events/", response.headers["Location"])

    def test_all_three_uploads_remain_required(self):
        client = self.app.test_client()
        response = client.post("/events/{}/imports/validate".format(self.event_a), data={})
        self.assertEqual(302, response.status_code)
        with self.app.app_context():
            count = get_db().execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
        self.assertEqual(0, count)

    def test_event_dashboards_are_isolated(self):
        batch_a = self._process(self.event_a)
        self._write_fixture(registrant_limit=2)
        batch_b = self._process(self.event_b)
        with self.app.app_context():
            self.assertEqual(batch_a, active_batch(get_db(), self.event_a)["id"])
            self.assertEqual(batch_b, active_batch(get_db(), self.event_b)["id"])
            self.assertEqual(5, overview_metrics(get_db(), batch_a)["total_registrants"])
            self.assertEqual(2, overview_metrics(get_db(), batch_b)["total_registrants"])
            summaries = {item["event"]["id"]: item for item in event_summaries(get_db())}
            self.assertEqual(5, summaries[self.event_a]["metrics"]["total_registrants"])
            self.assertEqual(2, summaries[self.event_b]["metrics"]["total_registrants"])

    def test_new_event_a_batch_supersedes_only_event_a(self):
        first_a = self._process(self.event_a)
        active_b = self._process(self.event_b)
        self._write_fixture(registrant_limit=2)
        second_a = self._process(self.event_a)
        with self.app.app_context():
            statuses = {
                row["id"]: row["status"]
                for row in get_db().execute("SELECT id, status FROM import_batches")
            }
            self.assertEqual("superseded", statuses[first_a])
            self.assertEqual("active", statuses[second_a])
            self.assertEqual("active", statuses[active_b])
            self.assertEqual(active_b, active_batch(get_db(), self.event_b)["id"])

    def test_failed_event_a_processing_keeps_both_previous_active_batches(self):
        active_a = self._process(self.event_a)
        active_b = self._process(self.event_b)
        staged = {key: (str(path), path.name) for key, path in self.paths.items()}
        validation = validate_batch(staged)
        with self.app.app_context():
            failed_batch = store_validation(get_db(), validation, self.event_a)
        self.paths["registrants"].unlink()
        with self.app.app_context():
            with self.assertRaises(FileNotFoundError):
                process_batch(get_db(), failed_batch)
            failed = get_db().execute(
                "SELECT status FROM import_batches WHERE id = ?", (failed_batch,)
            ).fetchone()
            self.assertEqual("failed", failed["status"])
            self.assertEqual(active_a, active_batch(get_db(), self.event_a)["id"])
            self.assertEqual(active_b, active_batch(get_db(), self.event_b)["id"])

    def test_existing_metrics_satellites_quality_and_privacy(self):
        batch_id = self._process(self.event_a)
        with self.app.app_context():
            metrics = overview_metrics(get_db(), batch_id)
            self.assertEqual(5, metrics["total_registrants"])
            self.assertEqual(4, metrics["checked_in"])
            self.assertEqual(80, metrics["attendance_rate"])
            self.assertEqual(1, metrics["ccf_main"])
            self.assertEqual(2, metrics["satellites"])
            self.assertEqual(1, metrics["non_ccf"])
            self.assertEqual(1, metrics["unknown"])
            checked = overview_metrics(get_db(), batch_id, "checked-in")
            self.assertEqual(4, checked["basis_total"])
            profile = participant_profile_metrics(get_db(), batch_id)
            self.assertEqual(5, profile["gender"]["total"])
            self.assertEqual(5, sum(item["count"] for item in profile["gender"]["items"]))
            self.assertEqual(4, profile["age"]["valid"])
            self.assertEqual(1, profile["age"]["missing"])
            self.assertEqual(0, profile["age"]["invalid"])
            satellites = satellite_metrics(get_db(), batch_id)
            self.assertEqual(["Eastwood", "Singapore"], [row["name"] for row in satellites["ranking"]])
            quality = {item["category"]: item["count"] for item in data_quality(get_db(), batch_id)["cards"]}
            self.assertEqual(1, quality["unknown_affiliation"])
            self.assertEqual(1, quality["contradictory_affiliation"])
            self.assertEqual(1, quality["ticket_without_registrant"])
            self.assertEqual(1, quality["buyer_without_ticket"])

        client = self.app.test_client()
        overview_page = client.get("/events/{}".format(self.event_a))
        self.assertEqual(200, overview_page.status_code)
        self.assertIn(b"Registrants by Church Origin", overview_page.data)
        self.assertIn(b"Registrant Profile by Gender", overview_page.data)
        self.assertIn(b"Age Distribution", overview_page.data)
        self.assertIn(b"Based on 5 registrants", overview_page.data)
        self.assertIn(b"100.0%", overview_page.data)
        self.assertNotIn(b"Checked-In Attendees", overview_page.data)
        self.assertNotIn(b"Attendance Rate", overview_page.data)
        self.assertNotIn(b"Checked In</a>", overview_page.data)
        quality_page = client.get("/events/{}/data-quality".format(self.event_a))
        self.assertEqual(200, quality_page.status_code)
        self.assertNotIn(b"test1@example.com", quality_page.data)
        self.assertNotIn(b"Test Registrant", quality_page.data)

    def test_overview_registrant_drilldown_is_scoped_and_privacy_limited(self):
        batch_id = self._process(self.event_a)
        with self.app.app_context():
            registrants = overview_registrants(get_db(), batch_id)
            self.assertEqual(5, len(registrants))
            self.assertEqual(
                {"CCF Main", "Local Satellite", "International Satellite", "Non-CCF", "Unknown"},
                {row["origin"] for row in registrants},
            )
            self.assertEqual("25–34", registrants[0]["age_group"])
            self.assertNotIn("email", registrants[0])
            self.assertNotIn("mobile", registrants[0])

        client = self.app.test_client()
        overview_page = client.get("/events/{}".format(self.event_a))
        self.assertIn(b"data-registrant-modal", overview_page.data)
        self.assertIn(b"data-registrant-trigger", overview_page.data)
        self.assertIn(b"overview.js", overview_page.data)

        response = client.get(
            "/events/{}/overview/registrants".format(self.event_a),
            headers={"Accept": "application/json"},
        )
        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual(5, len(payload["registrants"]))
        self.assertEqual("Test Registrant", payload["registrants"][0]["name"])
        self.assertNotIn(b"@example.com", response.data)
        self.assertNotIn(b"0900", response.data)

        empty = client.get("/events/{}/overview/registrants".format(self.event_b))
        self.assertEqual([], empty.get_json()["registrants"])
        self.assertEqual(404, client.get("/events/999999/overview/registrants").status_code)

    def test_satellite_search_scope_pagination_and_sorting(self):
        batch_id = self._process(self.event_a)
        self._add_satellite_ranking_fixture(batch_id)

        with self.app.app_context():
            default = satellite_metrics(get_db(), batch_id)
            self.assertEqual(19, default["registrants"])
            self.assertEqual(16, default["pagination"]["total"])
            self.assertEqual(10, len(default["ranking"]))
            self.assertEqual(["Alpha Hub", "Beta Hub"], [
                row["name"] for row in default["ranking"][:2]
            ])

            searched = satellite_metrics(
                get_db(), batch_id, query="SITE", page=2, per_page=10,
                sort="name", direction="asc",
            )
            self.assertEqual(12, searched["pagination"]["total"])
            self.assertEqual(2, searched["pagination"]["page"])
            self.assertEqual(2, len(searched["ranking"]))
            self.assertEqual(11, searched["ranking"][0]["rank"])

            participant_search = satellite_metrics(
                get_db(), batch_id, query="test registrant",
            )
            self.assertEqual(
                {"Eastwood", "Singapore"},
                {row["name"] for row in participant_search["ranking"]},
            )

            international = satellite_metrics(get_db(), batch_id, scope="international")
            self.assertEqual(1, international["pagination"]["total"])
            self.assertEqual("International", international["ranking"][0]["scope"])
            # Page filters never change the five overall summary totals.
            self.assertEqual(default["registrants"], international["registrants"])

            attendance = satellite_metrics(
                get_db(), batch_id, sort="attendance_rate", direction="asc",
            )
            self.assertEqual("Beta Hub", attendance["ranking"][0]["name"])
            self.assertEqual(0, attendance["ranking"][0]["attendance_rate"])

        client = self.app.test_client()
        response = client.get(
            "/events/{}/satellites?scope=local&q=site&page=2&per_page=10"
            "&sort=name&direction=asc".format(self.event_a)
        )
        self.assertEqual(200, response.status_code)
        self.assertIn(b"Showing 11\xe2\x80\x9312 of 12 satellites", response.data)
        self.assertIn(b'value="site"', response.data)
        self.assertIn(b"q=site", response.data)
        self.assertIn(b"Previous", response.data)
        self.assertIn(b"#satellite-table", response.data)
        self.assertNotIn(b"test1@example.com", response.data)

        ranking = client.get("/events/{}/satellites".format(self.event_a))
        self.assertIn(b"View registrants", ranking.data)
        self.assertNotIn(b"Test Registrant", ranking.data)
        participant_page = client.get(
            "/events/{}/satellites/registrants".format(self.event_a),
            query_string={"name": "Eastwood", "scope": "local"},
        )
        self.assertEqual(200, participant_page.status_code)
        self.assertIn(b"Test Registrant", participant_page.data)
        self.assertIn(b"Names only; contact information is not displayed", participant_page.data)
        self.assertNotIn(b"test2@example.com", participant_page.data)
        self.assertNotIn(b"0900", participant_page.data)

        missing_satellite = client.get(
            "/events/{}/satellites/registrants".format(self.event_a),
            query_string={"name": "Not a Satellite", "scope": "local"},
        )
        self.assertEqual(404, missing_satellite.status_code)

        empty = client.get(
            "/events/{}/satellites?q=does-not-exist".format(self.event_a)
        )
        self.assertEqual(200, empty.status_code)
        self.assertIn(b"No satellites match the current filters", empty.data)
        self.assertIn(b"Clear filters", empty.data)

    def test_data_quality_filters_pagination_sorting_scope_and_privacy(self):
        batch_a = self._process(self.event_a)
        self._add_quality_fixture(batch_a)
        self._process(self.event_b)

        with self.app.app_context():
            default = data_quality(get_db(), batch_a)
            self.assertGreater(default["pagination"]["total"], 10)
            self.assertEqual(10, len(default["details"]))

            errors = data_quality(get_db(), batch_a, severity="error", per_page=50)
            self.assertTrue(errors["details"])
            self.assertTrue(all(item["severity"] == "error" for item in errors["details"]))

            category = data_quality(get_db(), batch_a, category="custom_03")
            self.assertEqual(1, category["pagination"]["total"])
            self.assertEqual("custom_03", category["details"][0]["category"])

            buyers = data_quality(get_db(), batch_a, entity="buyers", per_page=50)
            self.assertTrue(all(item["entity_type"] == "buyers" for item in buyers["details"]))

            searched = data_quality(get_db(), batch_a, query="message 04")
            self.assertEqual(1, searched["pagination"]["total"])
            self.assertEqual("custom_04", searched["details"][0]["category"])

            friendly = data_quality(get_db(), batch_a, query="Unknown church affiliation")
            self.assertEqual("unknown_affiliation", friendly["details"][0]["category"])

            sorted_counts = data_quality(
                get_db(), batch_a, sort="count", direction="desc", per_page=50,
            )
            self.assertEqual("custom_samples", sorted_counts["details"][0]["category"])
            self.assertEqual(7, sorted_counts["details"][0]["count"])
            self.assertEqual(5, len(sorted_counts["details"][0]["samples"]))

            second_page = data_quality(get_db(), batch_a, page=2, per_page=10)
            self.assertEqual(2, second_page["pagination"]["page"])
            event_b_quality = data_quality(get_db(), active_batch(get_db(), self.event_b)["id"])
            self.assertNotIn("custom_samples", {
                item["category"] for item in event_b_quality["details"]
            })

        client = self.app.test_client()
        response = client.get(
            "/events/{}/data-quality?q=Synthetic&severity=error&category=all"
            "&entity=all&page=1&per_page=10&sort=category&direction=asc".format(self.event_a)
        )
        self.assertEqual(200, response.status_code)
        self.assertIn(b"Data Quality Summary", response.data)
        self.assertIn(b"Data Quality Issues", response.data)
        self.assertIn(b'value="Synthetic"', response.data)
        self.assertIn(b"q=Synthetic", response.data)
        self.assertIn(b"#quality-issues", response.data)
        self.assertNotIn(b"test1@example.com", response.data)
        self.assertNotIn(b"Test Registrant", response.data)

        empty_filter = client.get(
            "/events/{}/data-quality?q=does-not-exist".format(self.event_a)
        )
        self.assertIn(b"No issues match the current filters", empty_filter.data)
        self.assertIn(b"Clear filters", empty_filter.data)

        with self.app.app_context():
            clean_event = get_db().execute(
                "INSERT INTO events (name) VALUES ('Clean Event')"
            ).lastrowid
            get_db().execute(
                """
                INSERT INTO import_batches (event_id, event_slug, event_name, status, activated_at)
                VALUES (?, 'clean-event', 'Clean Event', 'active', CURRENT_TIMESTAMP)
                """,
                (clean_event,),
            )
            get_db().commit()
        clean_page = client.get("/events/{}/data-quality".format(clean_event))
        self.assertEqual(200, clean_page.status_code)
        self.assertIn(b"No data-quality issues were recorded", clean_page.data)
        self.assertIn(b">Clean<", clean_page.data)

    def test_data_quality_summary_cards_open_scoped_filterable_issue_details(self):
        batch_a = self._process(self.event_a)
        self._process(self.event_b)
        with self.app.app_context():
            detail_rows = [
                (
                    batch_a,
                    "error" if number == 14 else "warning",
                    "unknown_affiliation",
                    "tickets" if number == 14 else "registrants",
                    3000 + number,
                    "DETAIL-{:02d}".format(number),
                    "Affiliation detail issue {:02d}.".format(number),
                )
                for number in range(15)
            ]
            get_db().executemany(
                """
                INSERT INTO validation_issues (
                    batch_id, severity, category, entity_type,
                    source_row, source_identifier, message
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                detail_rows,
            )
            get_db().commit()

        client = self.app.test_client()
        page = client.get("/events/{}/data-quality".format(self.event_a))
        self.assertEqual(200, page.status_code)
        self.assertEqual(8, page.data.count(b"data-quality-card"))
        self.assertIn(b"data-quality-modal", page.data)
        self.assertIn(b"data_quality.js", page.data)
        self.assertIn(
            "/events/{}/data-quality/issues".format(self.event_a).encode(),
            page.data,
        )

        endpoint = "/events/{}/data-quality/issues".format(self.event_a)
        first = client.get(
            endpoint,
            query_string={"category": "unknown_affiliation", "page": 1, "per_page": 10},
        )
        self.assertEqual(200, first.status_code)
        first_payload = first.get_json()
        self.assertGreaterEqual(first_payload["pagination"]["total"], 15)
        self.assertEqual(10, len(first_payload["issues"]))
        self.assertTrue(first_payload["pagination"]["has_next"])

        second = client.get(
            endpoint,
            query_string={"category": "unknown_affiliation", "page": 2, "per_page": 10},
        ).get_json()
        self.assertGreater(len(second["issues"]), 0)

        searched = client.get(
            endpoint,
            query_string={"category": "unknown_affiliation", "q": "detail-14"},
        ).get_json()
        self.assertEqual(1, searched["pagination"]["total"])
        self.assertEqual("DETAIL-14", searched["issues"][0]["source_identifier"])

        errors = client.get(
            endpoint,
            query_string={"category": "unknown_affiliation", "severity": "error"},
        ).get_json()
        self.assertEqual(1, errors["pagination"]["total"])
        self.assertEqual("error", errors["issues"][0]["severity"])

        tickets = client.get(
            endpoint,
            query_string={"category": "unknown_affiliation", "entity": "tickets"},
        ).get_json()
        self.assertEqual(1, tickets["pagination"]["total"])
        self.assertEqual("tickets", tickets["issues"][0]["entity_type"])

        other_event = client.get(
            "/events/{}/data-quality/issues".format(self.event_b),
            query_string={"category": "unknown_affiliation", "q": "DETAIL"},
        ).get_json()
        self.assertEqual(0, other_event["pagination"]["total"])
        self.assertNotIn("DETAIL-14", str(other_event))
        self.assertNotIn("@example.com", str(first_payload))
        self.assertNotIn("Test Registrant", str(first_payload))
        self.assertEqual(404, client.get(
            endpoint, query_string={"category": "not_a_supported_card"}
        ).status_code)

    def test_event_routes_navigation_and_empty_states(self):
        client = self.app.test_client()
        self.assertEqual(302, client.get("/").status_code)
        events_page = client.get("/events")
        self.assertEqual(200, events_page.status_code)
        self.assertIn(b"Event A", events_page.data)
        for suffix in ("", "/satellites", "/data-quality", "/imports"):
            response = client.get("/events/{}{}".format(self.event_a, suffix))
            self.assertEqual(200, response.status_code)
            self.assertIn(b"Event A", response.data)
            if suffix != "/imports":
                self.assertIn(b"No active dataset for this event", response.data)
        self.assertEqual(404, client.get("/events/999999").status_code)

    def test_import_history_cannot_cross_event_boundaries(self):
        batch_a = self._process(self.event_a)
        client = self.app.test_client()
        response = client.get("/events/{}/imports?batch={}".format(self.event_b, batch_a))
        self.assertEqual(404, response.status_code)

    def test_import_history_filter_search_sort_and_pagination(self):
        with self.app.app_context():
            statuses = ("validated", "invalid", "failed", "superseded", "processing", "validating")
            batch_ids = []
            for index in range(1, 15):
                status = statuses[(index - 1) % len(statuses)]
                cursor = get_db().execute(
                    """
                    INSERT INTO import_batches (
                        event_id, event_slug, event_name, status, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.event_a,
                        "source-event-{}".format(index),
                        "Source Event {}".format(index),
                        status,
                        "2026-08-{:02d} 10:00:00".format(index),
                    ),
                )
                batch_id = cursor.lastrowid
                batch_ids.append(batch_id)
                for export_type, total in (("tickets", 40 + index), ("buyers", 20 + index), ("registrants", 30 + index)):
                    filename = "needle-tickets.csv" if index == 7 and export_type == "tickets" else "{}-{}.csv".format(export_type, index)
                    get_db().execute(
                        """
                        INSERT INTO import_files (
                            batch_id, export_type, filename, staged_path, status,
                            total_rows, valid_rows, detected_type
                        ) VALUES (?, ?, ?, ?, 'valid', ?, ?, ?)
                        """,
                        (batch_id, export_type, filename, "/staged/{}".format(filename), total, total, export_type),
                    )
                if status == "invalid":
                    get_db().execute(
                        """
                        INSERT INTO validation_issues (
                            batch_id, severity, category, entity_type, message
                        ) VALUES (?, 'error', 'event_mismatch', 'batch', 'Event mismatch.')
                        """,
                        (batch_id,),
                    )
            get_db().execute(
                """
                INSERT INTO import_batches (event_id, event_slug, event_name, status)
                VALUES (?, 'private-event', 'Private Other Event', 'invalid')
                """,
                (self.event_b,),
            )
            get_db().commit()

            first_page = import_history(get_db(), self.event_a)
            self.assertEqual(14, first_page["pagination"]["total"])
            self.assertEqual(10, len(first_page["batches"]))
            self.assertEqual(2, first_page["pagination"]["pages"])

            second_page = import_history(get_db(), self.event_a, page=2)
            self.assertEqual(4, len(second_page["batches"]))

            invalid = import_history(get_db(), self.event_a, status="invalid")
            self.assertTrue(invalid["batches"])
            self.assertTrue(all(row["status"] == "invalid" for row in invalid["batches"]))

            searched = import_history(get_db(), self.event_a, query="NEEDLE")
            self.assertEqual(1, searched["pagination"]["total"])
            self.assertEqual(batch_ids[6], searched["batches"][0]["id"])
            self.assertEqual(0, import_history(get_db(), self.event_a, query="Private Other Event")["pagination"]["total"])

            ascending = import_history(
                get_db(), self.event_a, per_page=25, sort="batch_id", direction="asc"
            )
            self.assertEqual(sorted(batch_ids), [row["id"] for row in ascending["batches"]])

        client = self.app.test_client()
        page = client.get(
            "/events/{}/imports?q=source&page=2&per_page=10&sort=batch_id&direction=asc".format(self.event_a)
        )
        self.assertEqual(200, page.status_code)
        self.assertIn(b"Showing 11\xe2\x80\x9314 of 14 batches", page.data)
        self.assertIn(b"q=source", page.data)
        self.assertIn(b"sort=batch_id", page.data)
        self.assertIn(b"direction=asc", page.data)
        self.assertEqual(4, page.data.count(b"View Details"))
        self.assertNotIn(b"Private Other Event", page.data)

        filtered = client.get(
            "/events/{}/imports?q=source&status=invalid&per_page=25".format(self.event_a)
        )
        self.assertEqual(200, filtered.status_code)
        self.assertIn(b'value="source"', filtered.data)
        self.assertIn(b'value="invalid" selected', filtered.data)
        self.assertNotIn(b'<span class="batch-status failed">', filtered.data)

        empty = client.get("/events/{}/imports?q=does-not-exist".format(self.event_a))
        self.assertEqual(200, empty.status_code)
        self.assertIn(b"No import batches match the current filters", empty.data)
        self.assertIn(b"Clear filters", empty.data)

    def test_event_mismatch_blocks_processing(self):
        with open(self.paths["buyers"], "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[0]["Event Name"] = "Another Event"
        write_csv(self.paths["buyers"], BUYER_FIELDS, rows)
        staged = {key: (str(path), path.name) for key, path in self.paths.items()}
        validation = validate_batch(staged)
        self.assertFalse(validation.valid)
        self.assertIn("event_mismatch", {issue.category for issue in validation.issues})
        with self.app.app_context():
            batch_id = store_validation(get_db(), validation, self.event_a)
            with self.assertRaises(ValueError):
                process_batch(get_db(), batch_id)
            self.assertEqual(
                "invalid",
                get_db().execute("SELECT status FROM import_batches WHERE id = ?", (batch_id,)).fetchone()["status"],
            )

    def test_imports_page_does_not_expose_registrant_pii(self):
        self._process(self.event_a)
        response = self.app.test_client().get("/events/{}/imports".format(self.event_a))
        self.assertEqual(200, response.status_code)
        self.assertNotIn(b"Test Registrant", response.data)
        self.assertNotIn(b"@example.com", response.data)
        self.assertNotIn(b"0900", response.data)
        self.assertNotIn(self.staging_dir.encode(), response.data)
        self.assertNotIn(b">People</span>", response.data)

    def test_wrong_export_and_control_number_validation_unchanged(self):
        result = validate_file("tickets", self.paths["buyers"].name, str(self.paths["buyers"]))
        self.assertEqual("invalid", result.status)
        self.assertIn("wrong_export_type", {issue.category for issue in result.issues})
        with open(self.paths["tickets"], "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[1]["Control Number"] = rows[0]["Control Number"]
        write_csv(self.paths["tickets"], TICKET_FIELDS, rows)
        result = validate_file("tickets", self.paths["tickets"].name, str(self.paths["tickets"]))
        self.assertEqual("valid", result.status)
        self.assertEqual(1, result.duplicate_records)

    def test_b1g_registrants_header_variant_is_recognized(self):
        write_csv(
            self.paths["registrants"],
            REGISTRANT_B1G_FIELDS,
            [{
                "ID": "1", "Event Name": "B1G Event", "Event Slug": "b1g-event",
                "Registration Code": "R-1", "Ticket Code": "T-1", "Ticket Status": "Assigned",
                "First Name": "Test", "Last Name": "Registrant", "Email Address": "test@example.com",
                "Mobile Number": "0900", "Gender": "Female", "Birth Month": "January",
                "Birth Year": "1990", "B1g Satellite Hub": "Metro East",
                "B1g Satellite": "B1G Antipolo", "Specify B1g Satellite": "",
            }],
        )
        result = validate_file("registrants", self.paths["registrants"].name, str(self.paths["registrants"]))
        self.assertEqual("valid", result.status)
        self.assertEqual("registrants", result.detected_type)

    def test_b1g_registrants_process_into_existing_dashboard_categories(self):
        base = {
            "Event Name": "Event One", "Event Slug": "event-1", "Ticket Status": "Assigned",
            "First Name": "Test", "Last Name": "Registrant", "Email Address": "test@example.com",
            "Mobile Number": "0900", "Gender": "Female", "Birth Month": "January", "Birth Year": "1990",
        }
        rows = [
            dict(base, ID="1", **{"Registration Code": "R-1", "Ticket Code": "T-MAIN", "B1g Satellite Hub": "CCF Center", "B1g Satellite": "B1G Main", "Specify B1g Satellite": ""}),
            dict(base, ID="2", **{"Registration Code": "R-2", "Ticket Code": "T-LOCAL", "B1g Satellite Hub": "Metro East", "B1g Satellite": "B1G Antipolo", "Specify B1g Satellite": ""}),
            dict(base, ID="3", **{"Registration Code": "R-3", "Ticket Code": "T-INTL", "B1g Satellite Hub": "ICP", "B1g Satellite": "Others", "Specify B1g Satellite": "B1G Singapore"}),
            dict(base, ID="4", **{"Registration Code": "R-4", "Ticket Code": "T-NON", "B1g Satellite Hub": "Others", "B1g Satellite": "Others", "Specify B1g Satellite": "B1G Naga"}),
            dict(base, ID="5", **{"Registration Code": "R-5", "Ticket Code": "T-UNKNOWN", "B1g Satellite Hub": "", "B1g Satellite": "", "Specify B1g Satellite": ""}),
        ]
        write_csv(self.paths["registrants"], REGISTRANT_B1G_FIELDS, rows)
        batch_id = self._process(self.event_a)
        with self.app.app_context():
            metrics = overview_metrics(get_db(), batch_id)
            self.assertEqual(1, metrics["ccf_main"])
            self.assertEqual(3, metrics["satellites"])
            self.assertEqual(0, metrics["non_ccf"])
            self.assertEqual(1, metrics["unknown"])
            ranking = satellite_metrics(get_db(), batch_id)["ranking"]
            self.assertEqual(
                {"B1G Antipolo", "B1G Singapore", "B1G Naga"},
                {item["name"] for item in ranking},
            )
            raw = get_db().execute(
                "SELECT b1g_satellite_hub_raw FROM registrants WHERE batch_id = ? AND ticket_code = 'T-INTL'",
                (batch_id,),
            ).fetchone()
            self.assertEqual("ICP", raw["b1g_satellite_hub_raw"])

    def test_profile_fields_are_backfilled_for_an_existing_batch(self):
        batch_id = self._process(self.event_a)
        with self.app.app_context():
            get_db().execute(
                """
                UPDATE registrants
                SET gender_raw = NULL, birth_month_raw = NULL, birth_year_raw = NULL
                WHERE batch_id = ?
                """,
                (batch_id,),
            )
            get_db().commit()

        migrated_app = create_app({
            "TESTING": True,
            "DATABASE": self.database,
            "STAGING_DIR": self.staging_dir,
        })
        with migrated_app.app_context():
            profile = participant_profile_metrics(get_db(), batch_id)
            self.assertEqual(5, profile["gender"]["total"])
            self.assertEqual(4, profile["age"]["valid"])
            self.assertEqual(1, profile["age"]["missing"])


class MigrationTests(unittest.TestCase):
    def test_legacy_active_batch_is_backfilled_without_data_loss(self):
        with tempfile.TemporaryDirectory() as temp:
            database = str(Path(temp) / "legacy.sqlite3")
            connection = sqlite3.connect(database)
            connection.executescript("""
                CREATE TABLE import_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_slug TEXT,
                    event_name TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    processed_at TEXT,
                    activated_at TEXT,
                    error_message TEXT
                );
                INSERT INTO import_batches (event_slug, event_name, status)
                VALUES ('legacy-event', 'Legacy Event', 'active');
            """)
            connection.close()
            app = create_app({
                "TESTING": True,
                "DATABASE": database,
                "STAGING_DIR": str(Path(temp) / "staging"),
            })
            with app.app_context():
                event = get_db().execute("SELECT * FROM events").fetchone()
                batch = get_db().execute("SELECT * FROM import_batches").fetchone()
                self.assertEqual("Legacy Event", event["name"])
                self.assertEqual(event["id"], batch["event_id"])
                self.assertEqual("active", batch["status"])
                self.assertEqual("ok", get_db().execute("PRAGMA integrity_check").fetchone()[0])


class ProvidedDatasetTests(unittest.TestCase):
    def test_supplied_exports_keep_verified_metrics_when_event_scoped(self):
        required = {
            "tickets": ROOT / "Aug20_26_0426PM_event_generated_tickets.csv",
            "buyers": ROOT / "Aug20_26_0427PM_event_buyers.csv",
            "registrants": ROOT / "Aug20_26_0432PM_event_registrants.csv",
        }
        if not all(path.exists() for path in required.values()):
            self.skipTest("Provided CSV fixtures are unavailable.")
        with tempfile.TemporaryDirectory() as temp:
            app = create_app({
                "TESTING": True,
                "DATABASE": str(Path(temp) / "provided.sqlite3"),
                "STAGING_DIR": str(Path(temp) / "staging"),
            })
            validation = validate_batch({
                export_type: (str(path), path.name) for export_type, path in required.items()
            })
            self.assertTrue(validation.valid)
            with app.app_context():
                event_id = get_db().execute(
                    "INSERT INTO events (name) VALUES ('B1G Converge 2025')"
                ).lastrowid
                get_db().commit()
                batch_id = store_validation(get_db(), validation, event_id)
                process_batch(get_db(), batch_id)
                metrics = overview_metrics(get_db(), batch_id)
                self.assertEqual(4334, metrics["total_registrants"])
                self.assertEqual(3869, metrics["checked_in"])
                self.assertAlmostEqual(89.2708814, metrics["attendance_rate"])
                self.assertEqual(1280, metrics["ccf_main"])
                self.assertEqual(1506, metrics["satellites"])
                self.assertEqual(440, metrics["non_ccf"])
                self.assertEqual(1108, metrics["unknown"])
                profile = participant_profile_metrics(get_db(), batch_id)
                gender = {item["label"]: item["count"] for item in profile["gender"]["items"]}
                self.assertEqual({"Male": 786, "Female": 2440, "Prefer not to say": 0, "Other": 0, "Unknown": 1108}, gender)
                self.assertEqual(3226, profile["age"]["valid"])
                self.assertEqual(1108, profile["age"]["missing"])
                self.assertEqual(0, profile["age"]["invalid"])
                age = {item["label"]: item["count"] for item in profile["age"]["items"]}
                self.assertEqual(2207, age["25–34"])
                satellites = satellite_metrics(get_db(), batch_id)
                self.assertEqual(1498, satellites["local_count"])
                self.assertEqual(8, satellites["international_count"])
            overview_page = app.test_client().get("/events/{}".format(event_id))
            self.assertEqual(200, overview_page.status_code)
            self.assertIn(b"4,334", overview_page.data)
            self.assertIn(b"29.5%", overview_page.data)
            self.assertIn(b"1,506", overview_page.data)
            self.assertIn(b"2,440", overview_page.data)
            self.assertIn(b"3,226", overview_page.data)
            self.assertNotIn(b"Checked-In Attendees", overview_page.data)
            self.assertNotIn(b"Attendance Rate", overview_page.data)


if __name__ == "__main__":
    unittest.main()
