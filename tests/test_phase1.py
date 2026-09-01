import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, event as sqlalchemy_event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app import create_app
from app.aggregation import (
    active_batch,
    curated_registrant_detail,
    curation_quality,
    data_quality,
    event_dashboard_metrics,
    event_summaries,
    overview_metrics,
    overview_registrants,
    participant_profile_metrics,
    registration_progress,
    satellite_curation_detail,
    satellite_metrics,
)
from app.analytics import event_analytics
from app.classifier import classify_affiliation
from app.curation import (
    normalize_birth_month,
    normalize_birth_year,
    normalize_last_name,
    normalize_satellite_name,
    rebuild_batch_curation,
)
from app.db import DatabaseConfigurationError, get_db, get_engine
from app.import_history import import_history
from app.importer import process_batch, store_validation, validate_batch, validate_file
from app.normalization import (
    calculate_age_at_event,
    get_age_bucket,
    normalize_gender,
    normalize_life_stage,
    normalize_registration_type,
)
from app.models import Base
from scripts.migrate_sqlite_to_mysql import MigrationError, migrate


ROOT = Path(__file__).resolve().parents[1]


def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    dbapi_connection.execute("PRAGMA foreign_keys = ON")


def create_test_schema(app, reset=False):
    with app.app_context():
        engine = get_engine()
        if engine.dialect.name == "sqlite":
            sqlalchemy_event.listen(engine, "connect", enable_sqlite_foreign_keys)
        if reset:
            Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
TICKET_FIELDS = [
    "Id", "Slug", "Event Name", "Ticket Code", "Control Number", "Ticket Status",
    "Payment Status", "Buyer Reference Number", "Check-in Date Time",
]
BUYER_FIELDS = [
    "Id", "Slug", "Event Name", "Buyer Reference Number", "Payment Status",
    "Payment Method", "Quantity", "Gross Amount", "Amount Paid",
]
REGISTRANT_FIELDS = [
    "ID", "Event Name", "Event Slug", "Registration Code", "Ticket Code", "Ticket Status",
    "Ticket Name", "First Name", "Last Name", "Email Address", "Mobile Number", "Are You Attending Ccf",
    "Gender", "Life Stage", "Date of Birth", "Birth Month", "Birth Year",
    "Are You From A Local Or International Satellite", "Which Local Satellite",
    "Which International Satellite", "Upload Your Accomplished Attestation Form Here",
    "Occupation", "Home Area", "Are You Part Of A Discipleship Group",
    "Are You Leading A Discipleship Group",
]
REGISTRANT_B1G_FIELDS = [
    "ID", "Event Name", "Event Slug", "Registration Code", "Ticket Code", "Ticket Status",
    "First Name", "Last Name", "Email Address", "Mobile Number", "Gender", "Birth Month",
    "Birth Year", "B1g Satellite Hub", "B1g Satellite", "Specify B1g Satellite",
]
REGISTRANT_REGIONAL_B1G_FIELDS = [
    "ID", "Event Name", "Event Slug", "Registration Code", "Ticket Code", "Ticket Status",
    "First Name", "Last Name", "Email Address", "Mobile Number", "Gender", "Birth Month",
    "Birth Year", "Bg Satellite Hub", "B1g Fridays Attendee",
    "Luzon North Central Hub", "Luzon Central Hub", "Luzon North East Hub",
    "Luzon North West Hub", "Luzon South Hub", "Mindanao South Hub",
    "Mindanao North Hub", "Visayas Hub", "Specify Icp Hub",
]


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class HeaderDesignContractTests(unittest.TestCase):
    def test_authenticated_pages_use_shared_application_and_panel_headers(self):
        template_names = (
            "admin_table.html",
            "analytics.html",
            "analytics_compare.html",
            "data_quality.html",
            "error.html",
            "event_new.html",
            "events.html",
            "imports.html",
            "overview.html",
            "registrations.html",
            "satellite_registrants.html",
            "satellites.html",
            "users.html",
        )
        for template_name in template_names:
            template = (ROOT / "app" / "templates" / template_name).read_text()
            with self.subTest(template=template_name):
                self.assertIn("block application_header_page", template)
                self.assertIn("block page_header", template)
                self.assertTrue(
                    "admin-table-heading" in template
                    or "render_panel_header" in template
                )
                self.assertNotIn("render_page_header(", template)

        styles = (ROOT / "app" / "static" / "app.css").read_text()
        for selector in (
            ".application-header-page",
            ".admin-table-panel",
            ".admin-table-heading",
            ".admin-breadcrumb",
        ):
            self.assertIn(selector, styles)


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


class DashboardNormalizationTests(unittest.TestCase):
    def test_registration_progress_contract(self):
        configured = registration_progress(525, 700)
        self.assertEqual(75, configured["progress_percentage"])
        self.assertEqual(175, configured["remaining_slots"])
        self.assertTrue(configured["target_configured"])
        zero = registration_progress(0, 700)
        self.assertEqual(0, zero["progress_percentage"])
        self.assertEqual(700, zero["remaining_slots"])
        for target in (None, 0):
            result = registration_progress(525, target)
            self.assertIsNone(result["progress_percentage"])
            self.assertIsNone(result["remaining_slots"])
            self.assertFalse(result["target_configured"])
        exceeded = registration_progress(8, 5)
        self.assertEqual(160, exceeded["progress_percentage"])
        self.assertEqual(0, exceeded["remaining_slots"])
        self.assertTrue(exceeded["target_exceeded"])

    def test_gender_normalization_contract(self):
        for value in ("Male", " male ", "MALE", "m"):
            self.assertEqual("male", normalize_gender(value))
        for value in ("Female", " female ", "FEMALE", "f"):
            self.assertEqual("female", normalize_gender(value))
        for value in (None, "", "  ", "unexpected", "Prefer not to say"):
            self.assertEqual("unknown", normalize_gender(value))

    def test_life_stage_normalization_contract(self):
        for value in ("Single", " single ", "SINGLE"):
            self.assertEqual("single", normalize_life_stage(value))
        for value in ("Single Parent", "single-parent", " solo  parent "):
            self.assertEqual("single-parent", normalize_life_stage(value))
        self.assertEqual("married", normalize_life_stage(" MARRIED "))
        for value in (None, "", "Separated", "Widow/Widower"):
            self.assertEqual("unknown", normalize_life_stage(value))

    def test_registration_type_uses_explicit_volunteer_labels(self):
        self.assertEqual("volunteer", normalize_registration_type("Event Volunteer", "Event"))
        self.assertEqual("volunteer", normalize_registration_type("Main", "Event (Volunteers)"))
        self.assertEqual("participant", normalize_registration_type("Main", "Event (Participants)"))
        self.assertEqual("participant", normalize_registration_type("", "Event"))

    def test_age_at_event_honors_birthday_and_bucket_boundaries(self):
        self.assertEqual(25, calculate_age_at_event("2000-09-13", "2026-09-12"))
        self.assertEqual(26, calculate_age_at_event("2000-09-12", "2026-09-12"))
        self.assertEqual(25, calculate_age_at_event(None, "2026-09-12", "October", "2000"))
        for age, bucket in (
            (19, "Below 20"), (20, "20–25"), (25, "20–25"),
            (26, "26–30"), (30, "26–30"), (31, "31–35"),
            (35, "31–35"), (36, "36–40"), (40, "36–40"),
            (41, "41+"),
        ):
            self.assertEqual(bucket, get_age_bucket(age))
        for age in (None, -1, 121, "invalid"):
            self.assertEqual("Unknown", get_age_bucket(age))
        self.assertIsNone(calculate_age_at_event(None, None, "January", "2000"))
        self.assertIsNone(calculate_age_at_event("not-a-date", "2026-09-12"))
        self.assertIsNone(calculate_age_at_event(None, "2026-09-12", "Month 13", "2000"))


class CurationNormalizationTests(unittest.TestCase):
    def test_identity_fields_normalize_conservatively(self):
        for value in ("  DE LA CRUZ ", "De La Cruz", "de   la cruz"):
            self.assertEqual("de la cruz", normalize_last_name(value))
        for value in ("January", "JAN", "Jan", "1", "01"):
            self.assertEqual("01", normalize_birth_month(value))
        self.assertEqual("12", normalize_birth_month("December"))
        for value in (None, "", "13", "not a month"):
            self.assertIsNone(normalize_birth_month(value))
        self.assertEqual("1995", normalize_birth_year(" 1995 "))
        for value in (None, "95", "unknown", "1899"):
            self.assertIsNone(normalize_birth_year(value))

    def test_satellite_aliases_normalize_without_merging_b1g_names(self):
        aliases = ("CCF Eastwood", "Eastwood", "CCF EASTWOOD", "CCF EastWood")
        self.assertEqual(
            {"ccf eastwood"},
            {normalize_satellite_name(value, "Local Satellite")["key"] for value in aliases},
        )
        self.assertEqual(
            "b1g eastwood",
            normalize_satellite_name("B1G Eastwood", "Local Satellite")["key"],
        )
        self.assertIsNone(normalize_satellite_name("", "Local Satellite"))

class EventIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = str(root / "test.sqlite3")
        self.staging_dir = str(root / "staging")
        mysql_test_url = os.environ.get("MYSQL_TEST_DATABASE_URL")
        if mysql_test_url and "test" not in (make_url(mysql_test_url).database or "").casefold():
            self.fail("MYSQL_TEST_DATABASE_URL must name a dedicated database containing 'test'.")
        self.database_url = mysql_test_url or "sqlite+pysqlite:///{}".format(self.database)
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATABASE_URL": self.database_url,
            "STAGING_DIR": self.staging_dir,
            "AUTHENTICATION_DISABLED": True,
            "WTF_CSRF_ENABLED": False,
        })
        create_test_schema(self.app, reset=bool(mysql_test_url))
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

    def _write_fixture(self, registrant_limit=None, volunteer_identifier=None):
        buyer = lambda identifier, reference, method="Debit or Credit Card": {
            "Id": identifier, "Slug": "event-1", "Event Name": "Event One",
            "Buyer Reference Number": reference, "Payment Status": "Payment Validated",
            "Payment Method": method, "Quantity": "1", "Gross Amount": "100", "Amount Paid": "100",
        }
        ticket = lambda identifier, code, buyer_ref, checked="": {
            "Id": identifier, "Slug": "event-1", "Event Name": "Event One", "Ticket Code": code,
            "Control Number": identifier, "Ticket Status": "Assigned", "Payment Status": "Payment Validated",
            "Buyer Reference Number": buyer_ref, "Check-in Date Time": checked,
        }
        registrant = lambda identifier, code, attending, scope="", local="", international="", gender="", life_stage="Single", birth_date="", birth_month="", birth_year="", attestation="", occupation="", home_area="", dgroup_member="", dgroup_leader="": {
            "ID": identifier, "Event Name": "Event One", "Event Slug": "event-1",
            "Registration Code": "R-{}".format(identifier), "Ticket Code": code, "Ticket Status": "Assigned",
            "Ticket Name": "Event Volunteer" if identifier == volunteer_identifier else "Event Participant",
            "First Name": "Test", "Last Name": "Registrant", "Email Address": "test{}@example.com".format(identifier),
            "Mobile Number": "0900", "Are You Attending Ccf": attending,
            "Gender": gender, "Life Stage": life_stage, "Date of Birth": birth_date,
            "Birth Month": birth_month, "Birth Year": birth_year,
            "Are You From A Local Or International Satellite": scope,
            "Which Local Satellite": local, "Which International Satellite": international,
            "Upload Your Accomplished Attestation Form Here": attestation,
            "Occupation": occupation, "Home Area": home_area,
            "Are You Part Of A Discipleship Group": dgroup_member,
            "Are You Leading A Discipleship Group": dgroup_leader,
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
            registrant("1", "T-MAIN", "Yes", "Local Satellite", "CCF Main", gender="Male", birth_month="January", birth_year="2000", attestation="https://files.example.com/attestation-1.pdf", occupation="IT/Technology Related", home_area="Quezon City", dgroup_member="Yes", dgroup_leader="Yes"),
            registrant("2", "T-LOCAL", "Yes", "Local Satellite", "Eastwood", gender="Female", birth_month="October", birth_year="1990", occupation="Accounting/Finance Related", home_area="Pasig", dgroup_member="Yes", dgroup_leader="No"),
            registrant("3", "T-INTL", "Yes", "International Satellite", international="Singapore", gender="Prefer not to say", birth_month="June", birth_year="1980", occupation="IT / Technology Related", home_area="Manila", dgroup_member="No", dgroup_leader="No"),
            registrant("4", "T-NON", "No", "Local Satellite", "CCF Main", gender="Nonbinary", birth_month="May", birth_year="1970", occupation="Others", home_area="Others"),
            registrant("5", "T-UNKNOWN", "", attestation="javascript:alert(1)"),
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

    def _satellite_id(self, event_id, normalized_name):
        with self.app.app_context():
            batch = active_batch(get_db(), event_id)
            row = get_db().execute(
                """
                SELECT id FROM satellites
                WHERE event_id = ? AND batch_id = ? AND normalized_name = ?
                """,
                (event_id, batch["id"], normalized_name),
            ).fetchone()
            self.assertIsNotNone(row, normalized_name)
            return row["id"]

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
            rebuild_batch_curation(get_db(), batch_id)
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

    def test_mysql_schema_constraints_and_logical_orphans(self):
        batch_id = self._process(self.event_a)
        with self.app.app_context():
            db = get_db()

            def rejected(statement, params):
                with self.assertRaises(DBAPIError):
                    db.execute(statement, params)
                db.rollback()

            rejected(
                "INSERT INTO import_batches (event_id, status) VALUES (?, 'active')",
                (self.event_a,),
            )
            rejected(
                "INSERT INTO import_files (batch_id, export_type, filename, staged_path, status) "
                "VALUES (?, 'tickets', 'duplicate.csv', '/private/duplicate.csv', 'valid')",
                (batch_id,),
            )
            rejected(
                "INSERT INTO buyers (batch_id, buyer_reference) VALUES (?, 'B-1')",
                (batch_id,),
            )
            rejected(
                "INSERT INTO tickets (batch_id, ticket_code) VALUES (?, 'T-MAIN')",
                (batch_id,),
            )
            rejected(
                "INSERT INTO registrants "
                "(batch_id, registration_code, ticket_code, affiliation, registration_type) "
                "VALUES (?, 'R-1', 'UNUSED', 'Unknown', 'participant')",
                (batch_id,),
            )
            rejected(
                "INSERT INTO registrants "
                "(batch_id, registration_code, ticket_code, affiliation, registration_type) "
                "VALUES (?, 'UNUSED', 'T-MAIN', 'Unknown', 'participant')",
                (batch_id,),
            )

            # Cross-file references intentionally remain logical so validation
            # can retain and report inconsistent source records.
            db.execute(
                "INSERT INTO tickets (batch_id, ticket_code, buyer_reference) "
                "VALUES (?, 'T-LOGICAL-ORPHAN', 'NO-SUCH-BUYER')",
                (batch_id,),
            )
            db.execute(
                "INSERT INTO registrants "
                "(batch_id, registration_code, ticket_code, affiliation, registration_type) "
                "VALUES (?, 'R-LOGICAL-ORPHAN', 'NO-SUCH-TICKET', 'Unknown', 'participant')",
                (batch_id,),
            )
            db.commit()

    def test_phase1_dashboard_counts_progress_profiles_and_api_are_scoped(self):
        self._write_fixture(volunteer_identifier="4")
        self._process(self.event_a)
        self._write_fixture(registrant_limit=2)
        self._process(self.event_b)
        client = self.app.test_client()
        saved = client.post(
            "/events/{}/settings".format(self.event_a),
            data={"event_date": "2025-09-05", "participant_target": "8"},
        )
        self.assertEqual(302, saved.status_code)

        with self.app.app_context():
            dashboard = event_dashboard_metrics(get_db(), self.event_a)
            self.assertEqual(4, dashboard["overview"]["participants"])
            self.assertEqual(1, dashboard["overview"]["volunteers"])
            self.assertEqual(5, dashboard["overview"]["total_registrations"])
            self.assertEqual(50, dashboard["overview"]["progress_percentage"])
            self.assertEqual(4, dashboard["overview"]["remaining_slots"])
            self.assertTrue(all(dashboard["reconciliation"].values()))
            profile = dashboard["participant_profile"]
            self.assertEqual(4, sum(item["count"] for item in profile["gender"]["items"]))
            self.assertEqual(4, sum(item["count"] for item in profile["life_stage"]["items"]))
            self.assertEqual(4, sum(item["count"] for item in profile["age"]["items"]))
            isolated = event_dashboard_metrics(get_db(), self.event_b)
            self.assertEqual(2, isolated["overview"]["participants"])
            self.assertEqual(0, isolated["overview"]["volunteers"])
            self.assertIsNone(isolated["overview"]["participant_target"])

        payload = client.get("/events/{}/dashboard".format(self.event_a)).get_json()
        self.assertEqual(4, payload["overview"]["participants"])
        self.assertEqual(1, payload["overview"]["volunteers"])
        self.assertTrue(all(payload["reconciliation"].values()))
        self.assertNotIn("@example.com", str(payload))
        page = client.get("/events/{}".format(self.event_a))
        self.assertIn(b"50.0%", page.data)
        self.assertIn(b"Remaining Slots", page.data)
        self.assertIn(b"Life Stage", page.data)
        self.assertNotIn(b"Participant target not configured", page.data)
        self.assertIn(b"B1G Admin Internal System", page.data)
        self.assertIn(b'class="application-header"', page.data)
        self.assertIn(b'form="event-settings-form"', page.data)
        self.assertEqual(1, page.data.count(b">Save Changes</span>"))

    def test_satellite_dataset_crud_validation_and_event_scoping(self):
        batch_a = self._process(self.event_a)
        self._write_fixture(registrant_limit=3)
        self._process(self.event_b)
        eastwood_a = self._satellite_id(self.event_a, "ccf eastwood")
        singapore_a = self._satellite_id(self.event_a, "ccf singapore")
        eastwood_b = self._satellite_id(self.event_b, "ccf eastwood")
        client = self.app.test_client()

        created = client.post(
            "/events/{}/satellite-datasets".format(self.event_a),
            data={
                "name": "  GGMA  ",
                "participant_target": "250",
                "satellite_ids": [str(eastwood_a), str(singapore_a)],
            },
        )
        self.assertEqual(302, created.status_code)
        with self.app.app_context():
            dataset = get_db().execute(
                "SELECT * FROM satellite_datasets WHERE event_id = ?",
                (self.event_a,),
            ).fetchone()
            self.assertEqual("GGMA", dataset["name"])
            self.assertEqual(250, dataset["participant_target"])
            dataset_id = dataset["id"]
            self.assertEqual(
                2,
                get_db().execute(
                    "SELECT COUNT(*) FROM satellite_dataset_satellites "
                    "WHERE satellite_dataset_id = ?",
                    (dataset_id,),
                ).fetchone()[0],
            )

        duplicate = client.post(
            "/events/{}/satellite-datasets".format(self.event_a),
            data={"name": "ggma", "participant_target": "10", "satellite_ids": str(eastwood_a)},
        )
        self.assertEqual(302, duplicate.status_code)
        empty_selection = client.post(
            "/events/{}/satellite-datasets".format(self.event_a),
            data={"name": "Empty", "participant_target": "10"},
        )
        self.assertEqual(302, empty_selection.status_code)
        for invalid_target in ("", "-1", "1.5", "invalid", "1000000001"):
            response = client.post(
                "/events/{}/satellite-datasets".format(self.event_a),
                data={
                    "name": "Invalid {}".format(invalid_target or "blank"),
                    "participant_target": invalid_target,
                    "satellite_ids": str(eastwood_a),
                },
            )
            self.assertEqual(302, response.status_code)

        same_name_other_event = client.post(
            "/events/{}/satellite-datasets".format(self.event_b),
            data={"name": "GGMA", "participant_target": "50", "satellite_ids": str(eastwood_b)},
        )
        self.assertEqual(302, same_name_other_event.status_code)
        with self.app.app_context():
            event_a_metric = event_dashboard_metrics(get_db(), self.event_a)[
                "satellite_datasets"
            ][0]
            self.assertEqual(2, event_a_metric["actual_participants"])
        cross_event_satellite = client.post(
            "/events/{}/satellite-datasets".format(self.event_a),
            data={"name": "Cross Event", "participant_target": "50", "satellite_ids": str(eastwood_b)},
        )
        self.assertEqual(302, cross_event_satellite.status_code)

        edited = client.post(
            "/events/{}/satellite-datasets/{}".format(self.event_a, dataset_id),
            data={"name": "East Cluster", "participant_target": "5", "satellite_ids": str(eastwood_a)},
        )
        self.assertEqual(302, edited.status_code)
        self.assertEqual(
            404,
            client.post(
                "/events/{}/satellite-datasets/{}".format(self.event_b, dataset_id),
                data={"name": "Hijacked", "participant_target": "1", "satellite_ids": str(eastwood_b)},
            ).status_code,
        )
        self.assertEqual(
            404,
            client.post(
                "/events/{}/satellite-datasets/{}/delete".format(self.event_b, dataset_id),
                data={"confirm_delete": "yes"},
            ).status_code,
        )

        not_confirmed = client.post(
            "/events/{}/satellite-datasets/{}/delete".format(self.event_a, dataset_id),
            data={},
        )
        self.assertEqual(302, not_confirmed.status_code)
        deleted = client.post(
            "/events/{}/satellite-datasets/{}/delete".format(self.event_a, dataset_id),
            data={"confirm_delete": "yes"},
        )
        self.assertEqual(302, deleted.status_code)
        with self.app.app_context():
            db = get_db()
            self.assertIsNone(
                db.execute("SELECT id FROM satellite_datasets WHERE id = ?", (dataset_id,)).fetchone()
            )
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM satellite_dataset_satellites WHERE satellite_dataset_id = ?",
                    (dataset_id,),
                ).fetchone()[0],
            )
            self.assertGreater(
                db.execute("SELECT COUNT(*) FROM satellites WHERE batch_id = ?", (batch_a,)).fetchone()[0],
                0,
            )
            names = [
                row["name"]
                for row in db.execute("SELECT name FROM satellite_datasets ORDER BY event_id, id")
            ]
            self.assertEqual(["GGMA"], names)

    def test_satellite_dataset_aggregation_deduplicates_people_and_excludes_volunteers(self):
        batch_id = self._process(self.event_a)
        eastwood = self._satellite_id(self.event_a, "ccf eastwood")
        singapore = self._satellite_id(self.event_a, "ccf singapore")
        client = self.app.test_client()
        for name, target, satellites in (
            ("Combined", 1, (eastwood, singapore)),
            ("East Only", 5, (eastwood,)),
            ("Singapore Only", 0, (singapore,)),
        ):
            self.assertEqual(
                302,
                client.post(
                    "/events/{}/satellite-datasets".format(self.event_a),
                    data={
                        "name": name,
                        "participant_target": str(target),
                        "satellite_ids": [str(value) for value in satellites],
                    },
                ).status_code,
            )

        with self.app.app_context():
            db = get_db()
            # This source row has the same complete curation identity as the
            # Eastwood participant but a Singapore relationship. It must add a
            # second satellite association, not a second person.
            db.execute(
                """
                INSERT INTO registrants (
                    batch_id, registration_code, ticket_code, last_name,
                    gender_raw, life_stage_raw, birth_month_raw, birth_year_raw,
                    affiliation, satellite_name, registration_type,
                    ticket_matched, checked_in
                ) VALUES (?, 'R-DUP-EAST', 'T-DUP-EAST', 'Registrant',
                          'Female', 'Single', 'October', '1990',
                          'International Satellite', 'Singapore', 'participant', 1, 0)
                """,
                (batch_id,),
            )
            db.execute(
                """
                INSERT INTO registrants (
                    batch_id, registration_code, ticket_code, last_name,
                    gender_raw, life_stage_raw, birth_month_raw, birth_year_raw,
                    affiliation, satellite_name, registration_type,
                    ticket_matched, checked_in
                ) VALUES (?, 'R-VOL-EAST', 'T-VOL-EAST', 'Volunteer',
                          'Male', 'Single', 'March', '1985',
                          'Local Satellite', 'Eastwood', 'volunteer', 1, 0)
                """,
                (batch_id,),
            )
            rebuild_batch_curation(db, batch_id)
            db.commit()
            dashboard = event_dashboard_metrics(db, self.event_a)

        datasets = {item["name"]: item for item in dashboard["satellite_datasets"]}
        combined = datasets["Combined"]
        self.assertEqual(2, combined["actual_participants"])
        self.assertEqual(200, combined["progress_percentage"])
        self.assertEqual(0, combined["remaining_slots"])
        self.assertTrue(combined["target_exceeded"])
        self.assertEqual(1, datasets["East Only"]["actual_participants"])
        self.assertEqual(20, datasets["East Only"]["progress_percentage"])
        self.assertEqual(4, datasets["East Only"]["remaining_slots"])
        self.assertEqual(2, datasets["Singapore Only"]["actual_participants"])
        self.assertFalse(datasets["Singapore Only"]["target_configured"])
        self.assertIsNone(datasets["Singapore Only"]["progress_percentage"])
        self.assertIsNone(datasets["Singapore Only"]["remaining_slots"])

        payload = client.get("/events/{}/dashboard".format(self.event_a)).get_json()
        self.assertEqual(3, len(payload["satellite_datasets"]))
        self.assertNotIn("@example.com", str(payload))
        self.assertNotIn("Mobile Number", str(payload))
        page = client.get("/events/{}".format(self.event_a))
        self.assertIn(b"Manage Satellite Targets", page.data)
        self.assertIn(b"Combined", page.data)
        self.assertIn(b"satellite-dataset-modal", page.data)

    def test_satellite_dataset_survives_active_batch_replacement_and_recalculates(self):
        first_batch = self._process(self.event_a)
        eastwood = self._satellite_id(self.event_a, "ccf eastwood")
        client = self.app.test_client()
        client.post(
            "/events/{}/satellite-datasets".format(self.event_a),
            data={"name": "East", "participant_target": "5", "satellite_ids": str(eastwood)},
        )
        with self.app.app_context():
            before = event_dashboard_metrics(get_db(), self.event_a)["satellite_datasets"][0]
            self.assertEqual(1, before["actual_participants"])
            dataset_id = before["id"]

        # The next import contains two distinct Eastwood participants.
        self._write_fixture(registrant_limit=3)
        with open(self.paths["registrants"], "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[2]["Are You From A Local Or International Satellite"] = "Local Satellite"
        rows[2]["Which Local Satellite"] = "Eastwood"
        rows[2]["Which International Satellite"] = ""
        write_csv(self.paths["registrants"], REGISTRANT_FIELDS, rows)
        second_batch = self._process(self.event_a)

        with self.app.app_context():
            db = get_db()
            after = event_dashboard_metrics(db, self.event_a)["satellite_datasets"][0]
            self.assertEqual(dataset_id, after["id"])
            self.assertEqual("East", after["name"])
            self.assertEqual(5, after["participant_target"])
            self.assertEqual(2, after["actual_participants"])
            mapping = db.execute(
                "SELECT satellite_batch_id FROM satellite_dataset_satellites "
                "WHERE satellite_dataset_id = ?",
                (dataset_id,),
            ).fetchone()
            self.assertEqual(second_batch, mapping["satellite_batch_id"])
            self.assertEqual(
                "inactive",
                db.execute("SELECT status FROM import_batches WHERE id = ?", (first_batch,)).fetchone()[0],
            )

        # Activating another Event remains isolated from Event A's target.
        self._write_fixture(registrant_limit=2)
        self._process(self.event_b)
        with self.app.app_context():
            isolated = event_dashboard_metrics(get_db(), self.event_a)["satellite_datasets"][0]
            self.assertEqual(2, isolated["actual_participants"])
            self.assertEqual(dataset_id, isolated["id"])

    def test_curation_is_traceable_incomplete_safe_idempotent_and_batch_scoped(self):
        with open(self.paths["registrants"], "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        duplicate_variants = (
            ("  DE LA CRUZ ", "January", "Male", "Eastwood", "Event Participant"),
            ("De La Cruz", "JAN", " male ", "CCF EASTWOOD", "Event Volunteer"),
            ("de   la cruz", "01", "MALE", "CCF Main", "Event Participant"),
        )
        for row, (last_name, month, gender, satellite, ticket_name) in zip(rows[:3], duplicate_variants):
            row["Last Name"] = last_name
            row["Birth Month"] = month
            row["Birth Year"] = "1995"
            row["Gender"] = gender
            row["Ticket Name"] = ticket_name
            row["Are You Attending Ccf"] = "Yes"
            row["Are You From A Local Or International Satellite"] = "Local Satellite"
            row["Which Local Satellite"] = satellite
            row["Which International Satellite"] = ""
        for row in rows[3:]:
            row["Last Name"] = "Santos"
            row["Birth Month"] = ""
            row["Birth Year"] = ""
            row["Gender"] = "Female"
            row["Ticket Name"] = "Event Participant"
        write_csv(self.paths["registrants"], REGISTRANT_FIELDS, rows)

        batch_a = self._process(self.event_a)
        with self.app.app_context():
            db = get_db()
            summary = curation_quality(db, batch_a)["summary"]
            self.assertEqual(5, summary["raw_registrants"])
            self.assertEqual(3, summary["curated_registrants"])
            self.assertEqual(2, summary["duplicate_records_merged"])
            self.assertEqual(1, summary["duplicate_groups"])
            self.assertEqual(2, summary["incomplete_identity_records"])
            self.assertEqual(1, summary["registration_type_conflicts"])
            self.assertEqual(1, summary["multiple_satellite_registrants"])

            duplicate = db.execute(
                """
                SELECT * FROM curated_registrants
                WHERE batch_id = ? AND source_registrant_count = 3
                """,
                (batch_a,),
            ).fetchone()
            self.assertEqual("de la cruz|01|1995|male", duplicate["dedupe_key"])
            self.assertEqual("participant", duplicate["registration_type"])
            self.assertTrue(duplicate["registration_type_conflict"])
            self.assertTrue(duplicate["checked_in"])
            self.assertEqual(
                3,
                db.execute(
                    "SELECT COUNT(*) FROM curated_registrant_sources WHERE curated_registrant_id = ?",
                    (duplicate["id"],),
                ).fetchone()[0],
            )
            self.assertEqual(
                2,
                db.execute(
                    "SELECT COUNT(*) FROM curated_registrant_satellites WHERE curated_registrant_id = ?",
                    (duplicate["id"],),
                ).fetchone()[0],
            )
            incomplete_keys = [
                row["dedupe_key"]
                for row in db.execute(
                    "SELECT dedupe_key FROM curated_registrants WHERE batch_id = ? AND dedupe_complete = 0",
                    (batch_a,),
                )
            ]
            self.assertEqual(2, len(incomplete_keys))
            self.assertEqual(2, len(set(incomplete_keys)))

            before = {
                table: db.execute("SELECT COUNT(*) FROM {} WHERE batch_id = ?".format(table), (batch_a,)).fetchone()[0]
                for table in (
                    "curated_registrants", "curated_registrant_sources",
                    "satellites", "curated_registrant_satellites",
                    "satellite_source_variations",
                )
            }
            rebuild_batch_curation(db, batch_a)
            after = {
                table: db.execute("SELECT COUNT(*) FROM {} WHERE batch_id = ?".format(table), (batch_a,)).fetchone()[0]
                for table in before
            }
            self.assertEqual(before, after)
            db.commit()

            dashboard = event_dashboard_metrics(db, self.event_a)
            self.assertEqual(3, dashboard["overview"]["participants"])
            self.assertEqual(5, dashboard["overview"]["raw_registrations"])
            self.assertEqual(2, dashboard["overview"]["duplicate_records_merged"])

        batch_b = self._process(self.event_b)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(3, curation_quality(db, batch_b)["summary"]["curated_registrants"])
            self.assertEqual(3, event_dashboard_metrics(db, self.event_a)["overview"]["participants"])
            self.assertEqual(3, event_dashboard_metrics(db, self.event_b)["overview"]["participants"])
            self.assertEqual(
                2,
                db.execute(
                    "SELECT COUNT(*) FROM curated_registrants WHERE dedupe_key = 'de la cruz|01|1995|male'"
                ).fetchone()[0],
            )

    def test_curation_drilldowns_are_active_batch_scoped_and_auditable(self):
        batch_a = self._process(self.event_a)
        self._process(self.event_b)
        with self.app.app_context():
            db = get_db()
            curated_id = db.execute(
                "SELECT id FROM curated_registrants WHERE batch_id = ? ORDER BY id LIMIT 1",
                (batch_a,),
            ).fetchone()[0]
            satellite_id = db.execute(
                "SELECT id FROM satellites WHERE batch_id = ? AND name = 'CCF Eastwood'",
                (batch_a,),
            ).fetchone()[0]
            detail = curated_registrant_detail(db, batch_a, curated_id)
            self.assertTrue(detail["source_registrations"])
            self.assertNotIn("email", detail["source_registrations"][0])
            variation = satellite_curation_detail(db, batch_a, satellite_id)
            self.assertEqual("CCF Eastwood", variation["satellite"]["name"])
            self.assertEqual("Eastwood", variation["source_variations"][0]["source_value"])

        client = self.app.test_client()
        self.assertEqual(
            200,
            client.get("/events/{}/data-quality/curation/registrants/{}".format(self.event_a, curated_id)).status_code,
        )
        self.assertEqual(
            404,
            client.get("/events/{}/data-quality/curation/registrants/{}".format(self.event_b, curated_id)).status_code,
        )
        page = client.get("/events/{}/data-quality".format(self.event_a))
        self.assertIn(b"Registrant Curation", page.data)
        self.assertIn(b"Raw Registrations", page.data)
        self.assertIn(b"Unique Registrants", page.data)
        self.assertIn(b"Satellite Curation", page.data)
        self.assertIn(b"curation_quality.js", page.data)

    def test_curation_scope_guards_and_batch_delete_cascade(self):
        batch_a = self._process(self.event_a)
        batch_b = self._process(self.event_b)
        with self.app.app_context():
            db = get_db()
            curated_a = db.execute(
                "SELECT id FROM curated_registrants WHERE batch_id = ? LIMIT 1",
                (batch_a,),
            ).fetchone()[0]
            satellite_b = db.execute(
                "SELECT id FROM satellites WHERE batch_id = ? LIMIT 1",
                (batch_b,),
            ).fetchone()[0]
            with self.assertRaises(DBAPIError):
                db.execute(
                    """
                    INSERT INTO curated_registrant_satellites (
                        event_id, batch_id, curated_registrant_id, satellite_id
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (self.event_a, batch_a, curated_a, satellite_b),
                )
            db.rollback()

            db.execute("DELETE FROM import_batches WHERE id = ?", (batch_b,))
            db.commit()
            for table in (
                "registrants", "curated_registrants", "curated_registrant_sources",
                "satellites", "satellite_source_variations",
                "curated_registrant_satellites",
            ):
                self.assertEqual(
                    0,
                    db.execute(
                        "SELECT COUNT(*) FROM {} WHERE batch_id = ?".format(table),
                        (batch_b,),
                    ).fetchone()[0],
                )
            self.assertGreater(
                db.execute(
                    "SELECT COUNT(*) FROM curated_registrants WHERE batch_id = ?",
                    (batch_a,),
                ).fetchone()[0],
                0,
            )

    def test_event_settings_validation_update_zero_and_event_isolation(self):
        client = self.app.test_client()
        first = client.post(
            "/events/{}/settings".format(self.event_a),
            data={"event_date": "2026-09-12", "participant_target": "700"},
        )
        self.assertEqual(302, first.status_code)
        update = client.post(
            "/events/{}/settings".format(self.event_a),
            data={"event_date": "2026-09-13", "participant_target": "0"},
        )
        self.assertEqual(302, update.status_code)
        with self.app.app_context():
            event_a = get_db().execute("SELECT * FROM events WHERE id = ?", (self.event_a,)).fetchone()
            event_b = get_db().execute("SELECT * FROM events WHERE id = ?", (self.event_b,)).fetchone()
            self.assertEqual("2026-09-13", event_a["event_date"])
            self.assertEqual(0, event_a["participant_target"])
            self.assertIsNone(event_b["event_date"])
            self.assertIsNone(event_b["participant_target"])
            self.assertFalse(event_dashboard_metrics(get_db(), self.event_a)["overview"]["target_configured"])

        for invalid_target in ("-1", "1.5", "abc"):
            response = client.post(
                "/events/{}/settings".format(self.event_a),
                data={"event_date": "2026-09-13", "participant_target": invalid_target},
            )
            self.assertEqual(302, response.status_code)
        response = client.post(
            "/events/{}/settings".format(self.event_a),
            data={"event_date": "2026-02-30", "participant_target": "10"},
        )
        self.assertEqual(302, response.status_code)
        with self.app.app_context():
            event_a = get_db().execute("SELECT * FROM events WHERE id = ?", (self.event_a,)).fetchone()
            self.assertEqual("2026-09-13", event_a["event_date"])
            self.assertEqual(0, event_a["participant_target"])
            with self.assertRaises(DBAPIError):
                get_db().execute(
                    "UPDATE events SET participant_target = -1 WHERE id = ?", (self.event_a,)
                )

    def test_target_exceeded_never_returns_negative_remaining_slots(self):
        self._process(self.event_a)
        self.app.test_client().post(
            "/events/{}/settings".format(self.event_a),
            data={"event_date": "2025-09-05", "participant_target": "2"},
        )
        with self.app.app_context():
            overview = event_dashboard_metrics(get_db(), self.event_a)["overview"]
            self.assertEqual(250, overview["progress_percentage"])
            self.assertEqual(0, overview["remaining_slots"])
            self.assertTrue(overview["target_exceeded"])

    def test_new_event_a_batch_inactivates_only_event_a(self):
        first_a = self._process(self.event_a)
        active_b = self._process(self.event_b)
        self._write_fixture(registrant_limit=2)
        second_a = self._process(self.event_a)
        with self.app.app_context():
            statuses = {
                row["id"]: row["status"]
                for row in get_db().execute("SELECT id, status FROM import_batches")
            }
            self.assertEqual("inactive", statuses[first_a])
            self.assertEqual("active", statuses[second_a])
            self.assertEqual("active", statuses[active_b])
            self.assertEqual(active_b, active_batch(get_db(), self.event_b)["id"])

    def test_inactive_processed_batches_can_be_switched_active_again(self):
        first_batch = self._process(self.event_a)
        self._write_fixture(registrant_limit=2)
        second_batch = self._process(self.event_a)

        with self.app.app_context():
            self.assertEqual(
                2,
                event_dashboard_metrics(get_db(), self.event_a)["overview"]["participants"],
            )
        client = self.app.test_client()
        switched = client.post(
            "/events/{}/imports/{}/activate".format(self.event_a, first_batch)
        )
        self.assertEqual(302, switched.status_code)

        with self.app.app_context():
            statuses = {
                row["id"]: row["status"]
                for row in get_db().execute(
                    "SELECT id, status FROM import_batches WHERE event_id = ?",
                    (self.event_a,),
                )
            }
            self.assertEqual("active", statuses[first_batch])
            self.assertEqual("inactive", statuses[second_batch])
            self.assertEqual(first_batch, active_batch(get_db(), self.event_a)["id"])
            self.assertEqual(
                5,
                event_dashboard_metrics(get_db(), self.event_a)["overview"]["participants"],
            )

        self.assertEqual(
            404,
            client.post(
                "/events/{}/imports/{}/activate".format(self.event_b, first_batch)
            ).status_code,
        )
        page = client.get("/events/{}/imports".format(self.event_a))
        self.assertIn(b'<span class="batch-status inactive">inactive</span>', page.data)
        self.assertIn(b">Activate</button>", page.data)
        self.assertNotIn(b"superseded", page.data.lower())

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
            profile = participant_profile_metrics(get_db(), batch_id, "2025-09-05")
            self.assertEqual(5, profile["gender"]["total"])
            self.assertEqual(5, sum(item["count"] for item in profile["gender"]["items"]))
            self.assertEqual(5, sum(item["count"] for item in profile["age"]["items"]))
            self.assertEqual(1, profile["age"]["unknown"])
            satellites = satellite_metrics(get_db(), batch_id)
            self.assertEqual(["CCF Eastwood", "CCF Singapore"], [row["name"] for row in satellites["ranking"]])
            quality = {item["category"]: item["count"] for item in data_quality(get_db(), batch_id)["cards"]}
            self.assertEqual(1, quality["unknown_affiliation"])
            self.assertEqual(1, quality["contradictory_affiliation"])
            self.assertEqual(1, quality["ticket_without_registrant"])
            self.assertEqual(1, quality["buyer_without_ticket"])

        client = self.app.test_client()
        overview_page = client.get("/events/{}".format(self.event_a))
        self.assertEqual(200, overview_page.status_code)
        self.assertIn(b"Event Overview", overview_page.data)
        self.assertIn(b"Participant Profile", overview_page.data)
        self.assertIn(b"Life Stage", overview_page.data)
        self.assertIn(b"Age Distribution", overview_page.data)
        self.assertIn(b"Total Participants", overview_page.data)
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
            self.assertEqual("Unknown", registrants[0]["age_group"])
            self.assertNotIn("email", registrants[0])
            self.assertNotIn("mobile", registrants[0])

        client = self.app.test_client()
        overview_page = client.get("/events/{}".format(self.event_a))
        self.assertIn(b"Participant Profile", overview_page.data)

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
            self.assertEqual(["CCF Alpha Hub", "CCF Beta Hub"], [
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
                {"CCF Eastwood", "CCF Singapore"},
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
            self.assertEqual("CCF Beta Hub", attendance["ranking"][0]["name"])
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
            query_string={"name": "CCF Eastwood", "scope": "local"},
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
                INSERT INTO import_batches (
                    event_id, event_slug, event_name, status, active_event_id, activated_at
                ) VALUES (?, 'clean-event', 'Clean Event', 'active', ?, CURRENT_TIMESTAMP)
                """,
                (clean_event, clean_event),
            )
            get_db().commit()
        clean_page = client.get("/events/{}/data-quality".format(clean_event))
        self.assertEqual(200, clean_page.status_code)
        self.assertIn(b"No data-quality issues were recorded", clean_page.data)
        self.assertIn(b">Clean<", clean_page.data)

    def test_data_quality_curation_tables_paginate_ten_rows_independently(self):
        batch_id = self._process(self.event_a)
        self._add_satellite_ranking_fixture(batch_id)

        with self.app.app_context():
            first_page = curation_quality(get_db(), batch_id)
            satellite_pagination = first_page["pagination"]["satellites"]
            self.assertGreater(satellite_pagination["total"], 10)
            self.assertEqual(10, satellite_pagination["per_page"])
            self.assertEqual(10, len(first_page["satellites"]))
            self.assertTrue(satellite_pagination["has_next"])

            second_page = curation_quality(
                get_db(), batch_id, pages={"satellites": 2}
            )
            self.assertEqual(2, second_page["pagination"]["satellites"]["page"])
            self.assertNotEqual(
                [item["id"] for item in first_page["satellites"]],
                [item["id"] for item in second_page["satellites"]],
            )
            for metadata in first_page["pagination"].values():
                self.assertEqual(10, metadata["per_page"])

        client = self.app.test_client()
        default_page = client.get(
            "/events/{}/data-quality".format(self.event_a)
        )
        self.assertEqual(200, default_page.status_code)
        self.assertEqual(
            10, default_page.data.count(b'data-curation-kind="satellite"')
        )
        self.assertIn(b"satellite_page=2", default_page.data)
        self.assertIn(b"#satellite-curation", default_page.data)

        second_page = client.get(
            "/events/{}/data-quality?satellite_page=2".format(self.event_a)
        )
        self.assertEqual(200, second_page.status_code)
        self.assertIn(b'value="2"', second_page.data)

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
        empty_dashboard = client.get("/events/{}/dashboard".format(self.event_a)).get_json()
        self.assertEqual(0, empty_dashboard["overview"]["participants"])
        self.assertEqual(0, empty_dashboard["overview"]["volunteers"])
        self.assertEqual(0, empty_dashboard["overview"]["total_registrations"])
        self.assertTrue(all(empty_dashboard["reconciliation"].values()))
        self.assertEqual(404, client.get("/events/999999").status_code)
        self.assertEqual(404, client.get("/events/999999/dashboard").status_code)

    def test_import_history_cannot_cross_event_boundaries(self):
        batch_a = self._process(self.event_a)
        client = self.app.test_client()
        response = client.get("/events/{}/imports?batch={}".format(self.event_b, batch_a))
        self.assertEqual(404, response.status_code)

    def test_import_history_filter_search_sort_and_pagination(self):
        with self.app.app_context():
            statuses = ("validated", "invalid", "failed", "inactive", "processing", "validating")
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
        self.assertEqual(4, page.data.count(b">View</a>"))
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

    def test_duplicate_authoritative_registration_identity_is_rejected(self):
        with open(self.paths["registrants"], "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[1]["Registration Code"] = rows[0]["Registration Code"]
        write_csv(self.paths["registrants"], REGISTRANT_FIELDS, rows)
        result = validate_file(
            "registrants", self.paths["registrants"].name, str(self.paths["registrants"])
        )
        self.assertEqual("invalid", result.status)
        self.assertEqual(1, result.duplicate_records)
        self.assertIn("duplicate_identifier", {issue.category for issue in result.issues})

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

    def test_regional_b1g_registrants_variant_is_normalized_and_recognized(self):
        write_csv(
            self.paths["registrants"],
            REGISTRANT_REGIONAL_B1G_FIELDS,
            [{
                "ID": "1", "Event Name": "B1G Event", "Event Slug": "b1g-event",
                "Registration Code": "R-1", "Ticket Code": "T-1", "Ticket Status": "Assigned",
                "Bg Satellite Hub": "Mindanao South", "Mindanao South Hub": "B1G Tagum",
            }],
        )
        result = validate_file("registrants", self.paths["registrants"].name, str(self.paths["registrants"]))
        self.assertEqual("valid", result.status)
        self.assertEqual("registrants", result.detected_type)
        self.assertEqual("Mindanao South", result.rows[0]["B1g Satellite Hub"])
        self.assertEqual("B1G Tagum", result.rows[0]["B1g Satellite"])
        self.assertNotIn("Bg Satellite Hub", result.rows[0])

    def test_regional_b1g_registrants_process_regional_satellites(self):
        base = {
            "Event Name": "Event One", "Event Slug": "event-1", "Ticket Status": "Assigned",
            "First Name": "Test", "Last Name": "Registrant", "Email Address": "test@example.com",
            "Mobile Number": "0900", "Gender": "Female", "Birth Month": "January", "Birth Year": "1990",
        }
        rows = [
            dict(base, ID="1", **{"Registration Code": "R-1", "Ticket Code": "T-MAIN", "Bg Satellite Hub": "Mindanao South", "Mindanao South Hub": "B1G Tagum"}),
            dict(base, ID="2", **{"Registration Code": "R-2", "Ticket Code": "T-LOCAL", "Bg Satellite Hub": "Mindanao North", "Mindanao North Hub": "B1G Malaybalay"}),
            dict(base, ID="3", **{"Registration Code": "R-3", "Ticket Code": "T-INTL", "Bg Satellite Hub": "ICP", "Specify Icp Hub": "B1G Hong Kong"}),
        ]
        write_csv(self.paths["registrants"], REGISTRANT_REGIONAL_B1G_FIELDS, rows)
        batch_id = self._process(self.event_a)
        with self.app.app_context():
            ranking = satellite_metrics(get_db(), batch_id)["ranking"]
            self.assertEqual(
                {"B1G Tagum", "B1G Malaybalay", "B1G Hong Kong"},
                {item["name"] for item in ranking},
            )
            stored = get_db().execute(
                "SELECT b1g_satellite_hub_raw, b1g_satellite_raw FROM registrants "
                "WHERE batch_id = ? AND ticket_code = 'T-MAIN'",
                (batch_id,),
            ).fetchone()
            self.assertEqual("Mindanao South", stored["b1g_satellite_hub_raw"])
            self.assertEqual("B1G Tagum", stored["b1g_satellite_raw"])

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

    def test_application_startup_does_not_mutate_existing_rows(self):
        batch_id = self._process(self.event_a)
        with self.app.app_context():
            get_db().execute(
                """
                UPDATE registrants
                SET gender_raw = NULL, life_stage_raw = NULL, ticket_name_raw = NULL,
                    birth_month_raw = NULL, birth_year_raw = NULL
                WHERE batch_id = ?
                """,
                (batch_id,),
            )
            get_db().commit()

        migrated_app = create_app({
            "TESTING": True,
            "DATABASE_URL": self.database_url,
            "STAGING_DIR": self.staging_dir,
        })
        with migrated_app.app_context():
            profile = participant_profile_metrics(get_db(), batch_id, "2025-09-05")
            self.assertEqual(5, profile["gender"]["total"])
            self.assertEqual(5, sum(item["count"] for item in profile["age"]["items"]))
            self.assertEqual(5, profile["age"]["unknown"])
            self.assertEqual(5, sum(item["count"] for item in profile["life_stage"]["items"]))
    def test_admin_tables_navigation_primary_exports_and_authorization(self):
        self._process(self.event_a)
        client = self.app.test_client()
        page = client.get("/events/{}/admin-tables/registrants".format(self.event_a))
        self.assertEqual(200, page.status_code)
        self.assertIn(b"Admin Tables", page.data)
        self.assertIn(b"Generated Tickets", page.data)
        self.assertIn(b"Buyers", page.data)
        self.assertIn(b"All Registrants", page.data)
        self.assertIn(b"Curated Registrants", page.data)
        self.assertIn(b"admin_tables.js", page.data)
        self.assertIn(b"data-nav-group-toggle", page.data)
        self.assertIn(b'aria-controls="admin-tables-submenu"', page.data)
        self.assertIn(b'aria-expanded="true"', page.data)
        self.assertIn(b'class="nav-module active expanded"', page.data)
        self.assertIn(b'class="application-header-page"', page.data)
        self.assertIn(b"Inspect complete imported source records without deduplication", page.data)
        self.assertNotIn(b"overview-header admin-tables-header", page.data)
        self.assertIn(b'class="admin-breadcrumb"', page.data)
        self.assertEqual(2, page.data.count(b"<h1"))
        self.assertNotIn(b"Registrant-Satellite Links", page.data)

        overview_page = client.get("/events/{}".format(self.event_a))
        self.assertIn(b'class="nav-module "', overview_page.data)
        self.assertIn(b'aria-expanded="false"', overview_page.data)

        for dataset, label in (
            ("registrants", "Registrants"),
            ("tickets", "Generated Tickets"),
            ("buyers", "Buyers"),
        ):
            dataset_page = client.get(
                "/events/{}/admin-tables/{}".format(self.event_a, dataset)
            )
            self.assertEqual(200, dataset_page.status_code)
            self.assertIn(
                (
                    '<span class="application-header-module">Admin Tables</span> '
                    '<span class="application-header-separator" aria-hidden="true">/</span> '
                    "{}</h1>".format(label)
                ).encode(),
                dataset_page.data,
            )

        curated_page = client.get(
            "/events/{}/admin-tables/registrants?view=curated".format(self.event_a)
        )
        self.assertIn(b"Curated Registrants</h1>", curated_page.data)
        self.assertIn(b"Inspect canonical people generated by the existing curation layer", curated_page.data)

        restricted = create_app({
            "TESTING": True,
            "DATABASE_URL": self.database_url,
            "STAGING_DIR": self.staging_dir,
            "ADMIN_TABLES_ENABLED": False,
            "AUTHENTICATION_DISABLED": True,
            "WTF_CSRF_ENABLED": False,
        })
        restricted_client = restricted.test_client()
        self.assertEqual(
            403,
            restricted_client.get(
                "/events/{}/admin-tables/registrants".format(self.event_a)
            ).status_code,
        )
        overview = restricted_client.get("/events/{}".format(self.event_a))
        self.assertNotIn(b">Admin Tables</span>", overview.data)

    def test_admin_tables_preserve_complete_rows_and_expose_all_source_columns(self):
        self._process(self.event_a)
        client = self.app.test_client()
        registrants = client.get(
            "/events/{}/admin-tables/registrants/data?per_page=25".format(self.event_a)
        ).get_json()
        tickets = client.get(
            "/events/{}/admin-tables/tickets/data?per_page=25".format(self.event_a)
        ).get_json()
        buyers = client.get(
            "/events/{}/admin-tables/buyers/data?per_page=25".format(self.event_a)
        ).get_json()

        self.assertEqual(5, registrants["pagination"]["total"])
        self.assertEqual(6, tickets["pagination"]["total"])
        self.assertEqual(2, buyers["pagination"]["total"])
        registrant_labels = {column["label"] for column in registrants["columns"]}
        buyer_labels = {column["label"] for column in buyers["columns"]}
        self.assertIn("Email Address", registrant_labels)
        self.assertIn("Mobile Number", registrant_labels)
        self.assertIn("Gross Amount", buyer_labels)
        self.assertIn("Amount Paid", buyer_labels)
        attestation_column = next(
            column
            for column in registrants["columns"]
            if column["label"] == "Upload Your Accomplished Attestation Form Here"
        )
        self.assertTrue(attestation_column["default"])
        self.assertEqual("attestation_form_link", attestation_column["renderer"])
        self.assertEqual(
            "https://files.example.com/attestation-1.pdf",
            registrants["rows"][0][attestation_column["key"]],
        )
        self.assertTrue(any(column["default"] for column in registrants["columns"]))
        self.assertTrue(all("expression" not in column for column in registrants["columns"]))

        admin_script = (Path(__file__).parents[1] / "app/static/admin_tables.js").read_text()
        self.assertIn('link.textContent = "View Attestation Form"', admin_script)
        self.assertIn('link.target = "_blank"', admin_script)
        self.assertIn('link.rel = "noopener noreferrer"', admin_script)
        self.assertIn('["http:", "https:"]', admin_script)

        with self.app.app_context():
            preserved = get_db().execute(
                "SELECT source_data_json FROM buyers WHERE batch_id = ? ORDER BY id LIMIT 1",
                (registrants["rows"][0]["batch_id"],),
            ).fetchone()[0]
            self.assertEqual("100", json.loads(preserved)["Gross Amount"])

    def test_admin_table_search_filters_sort_pagination_and_event_batch_scope(self):
        batch_a_1 = self._process(self.event_a)
        self._write_fixture(registrant_limit=2)
        batch_a_2 = self._process(self.event_a)
        self._write_fixture(registrant_limit=1)
        batch_b = self._process(self.event_b)
        client = self.app.test_client()

        active = client.get(
            "/events/{}/admin-tables/registrants/data?per_page=25".format(self.event_a)
        ).get_json()
        self.assertEqual(batch_a_2, active["batch"])
        self.assertEqual(2, active["pagination"]["total"])

        all_batches = client.get(
            "/events/{}/admin-tables/registrants/data?batch=all&per_page=25".format(self.event_a)
        ).get_json()
        self.assertEqual(7, all_batches["pagination"]["total"])
        self.assertNotIn(batch_b, {row["batch_id"] for row in all_batches["rows"]})

        filters = json.dumps([
            {"field": "gender_raw", "operator": "equals", "value": "Female"},
            {"field": "checked_in", "operator": "equals", "value": "yes"},
        ])
        filtered = client.get(
            "/events/{}/admin-tables/registrants/data".format(self.event_a),
            query_string={
                "batch": batch_a_1,
                "search": "Registrant",
                "filters": filters,
                "sort": "registration_code",
                "direction": "desc",
                "page": 1,
                "per_page": 25,
            },
        ).get_json()
        self.assertEqual(1, filtered["pagination"]["total"])
        self.assertEqual("Female", filtered["rows"][0]["gender_raw"])
        self.assertTrue(filtered["rows"][0]["checked_in"])

        bracket_filter = client.get(
            "/events/{}/admin-tables/registrants/data?filters%5Bregistration_type%5D=participant".format(self.event_a)
        ).get_json()
        self.assertEqual(2, bracket_filter["pagination"]["total"])
        date_filter = client.get(
            "/events/{}/admin-tables/tickets/data".format(self.event_a),
            query_string={
                "batch": batch_a_1,
                "filters": json.dumps([{
                    "field": "check_in_at", "operator": "exact", "value": "2025-09-05"
                }]),
            },
        ).get_json()
        self.assertEqual(4, date_filter["pagination"]["total"])
        numeric_filter = client.get(
            "/events/{}/admin-tables/buyers/data".format(self.event_a),
            query_string={
                "batch": batch_a_1,
                "filters": json.dumps([{
                    "field": "quantity", "operator": "greater_than", "value": "0"
                }]),
            },
        ).get_json()
        self.assertEqual(2, numeric_filter["pagination"]["total"])
        invalid_scope = client.get(
            "/events/{}/admin-tables/registrants/data?batch={}".format(self.event_a, batch_b)
        )
        self.assertEqual(400, invalid_scope.status_code)

    def test_curated_admin_view_and_complete_registration_source_lineage(self):
        with open(self.paths["registrants"], "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[1]["Last Name"] = rows[0]["Last Name"]
        rows[1]["Birth Month"] = rows[0]["Birth Month"] = "January"
        rows[1]["Birth Year"] = rows[0]["Birth Year"] = "1995"
        rows[1]["Gender"] = rows[0]["Gender"] = "Male"
        write_csv(self.paths["registrants"], REGISTRANT_FIELDS, rows)
        batch_id = self._process(self.event_a)
        client = self.app.test_client()

        page = client.get(
            "/events/{}/admin-tables/registrants?view=curated".format(self.event_a)
        )
        self.assertEqual(200, page.status_code)
        self.assertIn(b'data-dataset="curated"', page.data)

        curated = client.get(
            "/events/{}/admin-tables/curated/data?sort=source_registrant_count&direction=desc".format(self.event_a)
        ).get_json()
        self.assertEqual(4, curated["pagination"]["total"])
        merged = curated["rows"][0]
        self.assertEqual(2, merged["source_registrant_count"])
        detail = client.get(
            "/events/{}/admin-tables/registrants/curated/{}/sources?batch={}".format(
                self.event_a, merged["id"], batch_id
            )
        ).get_json()
        self.assertEqual(2, len(detail["sources"]))
        self.assertTrue(all(source["event_id"] == self.event_a for source in detail["sources"]))
        self.assertTrue(all(source["batch_id"] == batch_id for source in detail["sources"]))
        self.assertIn("Email Address", detail["sources"][0]["source_values"])
        self.assertIn("Mobile Number", detail["sources"][0]["source_values"])
        self.assertIn("registration_code", detail["sources"][0]["normalized_values"])

        self._process(self.event_b)
        self.assertEqual(
            404,
            client.get(
                "/events/{}/admin-tables/registrants/curated/{}/sources".format(
                    self.event_b, merged["id"]
                )
            ).status_code,
        )


class MigrationTests(unittest.TestCase):
    def test_normal_runtime_requires_mysql_database_url(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(DatabaseConfigurationError):
                create_app(
                    {
                        "DATABASE_URL": "sqlite+pysqlite:///{}".format(Path(temp) / "runtime.sqlite3"),
                        "STAGING_DIR": str(Path(temp) / "staging"),
                    }
                )

    def test_startup_does_not_create_or_upgrade_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            database = str(Path(temp) / "empty.sqlite3")
            app = create_app({
                "TESTING": True,
                "DATABASE_URL": "sqlite+pysqlite:///{}".format(database),
                "STAGING_DIR": str(Path(temp) / "staging"),
            })
            with app.app_context():
                self.assertEqual([], inspect(get_engine()).get_table_names())

    def test_sqlite_copy_preserves_ids_unicode_relationships_and_rejects_rerun(self):
        with tempfile.TemporaryDirectory() as temp:
            source_path = Path(temp) / "source.sqlite3"
            source_engine = create_engine("sqlite+pysqlite:///{}".format(source_path))
            sqlalchemy_event.listen(source_engine, "connect", enable_sqlite_foreign_keys)
            Base.metadata.create_all(source_engine)
            with source_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO events (id, name, event_date, participant_target) "
                        "VALUES (7, 'Événement 家庭', '2026-09-05', 100)"
                    )
                )
                connection.execute(
                    text("INSERT INTO events (id, name) VALUES (8, 'Second Event')")
                )
                connection.execute(
                    text(
                        "INSERT INTO import_batches "
                        "(id, event_id, event_slug, event_name, status, activated_at) "
                        "VALUES (10, 7, 'unicode-event', 'Événement 家庭', 'inactive', "
                        "'2026-08-20 10:00:00')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO import_batches "
                        "(id, event_id, event_slug, event_name, status, active_event_id, activated_at) "
                        "VALUES (11, 7, 'unicode-event', 'Événement 家庭', 'active', 7, "
                        "'2026-08-24 10:00:00')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO import_batches (id, event_id, status, error_message) "
                        "VALUES (12, 8, 'failed', 'Representative failure')"
                    )
                )
                for file_id, export_type in enumerate(("tickets", "buyers", "registrants"), 20):
                    connection.execute(
                        text(
                            "INSERT INTO import_files "
                            "(id, batch_id, export_type, filename, staged_path, status) "
                            "VALUES (:id, 11, :kind, :filename, :path, 'valid')"
                        ),
                        {
                            "id": file_id,
                            "kind": export_type,
                            "filename": export_type + ".csv",
                            "path": "/private/" + export_type + ".csv",
                        },
                    )
                connection.execute(
                    text(
                        "INSERT INTO buyers (id, batch_id, buyer_reference, quantity) "
                        "VALUES (31, 11, 'BUY-1', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO tickets (id, batch_id, ticket_code, buyer_reference) "
                        "VALUES (41, 11, 'TICKET-1', 'BUY-1')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO registrants "
                        "(id, batch_id, registration_code, ticket_code, first_name, last_name, "
                        "gender_raw, birth_date_raw, affiliation, satellite_name, "
                        "registration_type, ticket_matched, checked_in) VALUES "
                        "(51, 11, 'REG-1', 'TICKET-1', 'José', '李', 'Male', 'raw-value', "
                        "'Local Satellite', 'CCF 東京', 'participant', 1, 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO validation_issues "
                        "(id, batch_id, severity, category, entity_type, message) "
                        "VALUES (61, 11, 'warning', 'sample_warning', 'registrants', 'Babala ⚠')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO validation_issues "
                        "(id, batch_id, severity, category, entity_type, source_row, message) "
                        "VALUES (62, 11, 'error', 'sample_error', 'tickets', 2, 'Invalid sample')"
                    )
                )
            source_engine.dispose()

            destination = create_engine("sqlite+pysqlite:///:memory:")
            sqlalchemy_event.listen(destination, "connect", enable_sqlite_foreign_keys)
            Base.metadata.create_all(destination)
            report = migrate(source_path, destination, require_mysql=False, progress=lambda _line: None)
            self.assertEqual(8, report["events"]["max_id"])
            self.assertEqual(51, report["registrants"]["max_id"])
            with destination.connect() as connection:
                row = connection.execute(
                    text("SELECT first_name, last_name, satellite_name, birth_date_raw FROM registrants")
                ).one()
                self.assertEqual(("José", "李", "CCF 東京", "raw-value"), tuple(row))
            with destination.begin() as connection:
                inserted = connection.execute(text("INSERT INTO events (name) VALUES ('After migration')"))
                self.assertGreater(inserted.lastrowid, 8)
            with self.assertRaises(MigrationError):
                migrate(source_path, destination, require_mysql=False, progress=lambda _line: None)


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
                "DATABASE_URL": "sqlite+pysqlite:///{}".format(Path(temp) / "provided.sqlite3"),
                "STAGING_DIR": str(Path(temp) / "staging"),
                "AUTHENTICATION_DISABLED": True,
                "WTF_CSRF_ENABLED": False,
            })
            create_test_schema(app)
            validation = validate_batch({
                export_type: (str(path), path.name) for export_type, path in required.items()
            })
            self.assertTrue(validation.valid)
            with app.app_context():
                event_id = get_db().execute(
                    """
                    INSERT INTO events (name, event_date, participant_target)
                    VALUES ('B1G Converge 2025', '2025-09-05', 5000)
                    """
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
                dashboard = event_dashboard_metrics(get_db(), event_id)
                self.assertEqual(4312, dashboard["overview"]["participants"])
                self.assertEqual(0, dashboard["overview"]["volunteers"])
                self.assertEqual(4312, dashboard["overview"]["total_registrations"])
                self.assertEqual(4334, dashboard["overview"]["raw_registrations"])
                self.assertEqual(22, dashboard["overview"]["duplicate_records_merged"])
                self.assertAlmostEqual(86.24, dashboard["overview"]["progress_percentage"])
                self.assertTrue(all(dashboard["reconciliation"].values()))
                profile = dashboard["participant_profile"]
                gender = {item["label"]: item["count"] for item in profile["gender"]["items"]}
                self.assertEqual({"Male": 783, "Female": 2421, "Unknown": 1108}, gender)
                life_stage = {item["label"]: item["count"] for item in profile["life_stage"]["items"]}
                self.assertEqual(
                    {"Single": 3024, "Single Parent": 71, "Married": 95, "Unknown": 1122},
                    life_stage,
                )
                self.assertEqual(1108, profile["age"]["unknown"])
                age = {item["label"]: item["count"] for item in profile["age"]["items"]}
                self.assertEqual(
                    {
                        "Below 20": 20, "20–25": 640, "26–30": 1262,
                        "31–35": 808, "36–40": 280, "41+": 194,
                        "Unknown": 1108,
                    },
                    age,
                )
                satellites = satellite_metrics(get_db(), batch_id)
                self.assertEqual(1492, satellites["local_count"])
                self.assertEqual(8, satellites["international_count"])
                analytics = event_analytics(get_db(), event_id, threshold=1)
                self.assertEqual(4312, analytics["population"]["registered"]["count"])
                self.assertEqual(3854, analytics["population"]["checked_in"]["count"])
                self.assertTrue(analytics["reconciliation"]["distribution_totals"])
                for distribution in analytics["distributions"].values():
                    self.assertEqual(
                        4312,
                        sum(item["count"] for item in distribution["items"]),
                    )
            overview_page = app.test_client().get("/events/{}".format(event_id))
            self.assertEqual(200, overview_page.status_code)
            self.assertIn(b"4,334", overview_page.data)
            self.assertIn(b"4,312", overview_page.data)
            self.assertIn(b"2,421", overview_page.data)
            self.assertIn(b"3,024", overview_page.data)
            self.assertIn(b"1,262", overview_page.data)
            self.assertIn(b"86.2%", overview_page.data)
            self.assertNotIn(b"Checked-In Attendees", overview_page.data)
            self.assertNotIn(b"Attendance Rate", overview_page.data)


if __name__ == "__main__":
    unittest.main()
