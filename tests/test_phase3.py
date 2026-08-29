import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from sqlalchemy.engine import make_url

from app.analytics import (
    AnalyticsFilterError,
    classify_dgroup,
    compare_events,
    event_analytics,
    historical_trends,
    normalize_payment_method,
    normalize_payment_status,
    normalize_profile_value,
)
from app.db import get_db
from app import create_app
from app.aggregation import active_batch
from app.config import ApplicationConfigurationError, configure_app
from app.importer import process_batch, store_validation, validate_batch
from tests.test_phase1 import (
    BUYER_FIELDS,
    REGISTRANT_FIELDS,
    TICKET_FIELDS,
    create_test_schema,
    write_csv,
)


class AnalyticsNormalizationTests(unittest.TestCase):
    def test_conservative_source_normalization(self):
        self.assertEqual("Payment Validated", normalize_payment_status(" payment validated "))
        self.assertEqual("Payment Cancelled", normalize_payment_status("Payment Canceled"))
        self.assertEqual("Unknown", normalize_payment_status(""))
        self.assertEqual("Custom Review", normalize_payment_status("Custom Review"))
        self.assertEqual("Debit or Credit Card", normalize_payment_method("debit or credit card"))
        self.assertEqual("IT/Technology Related", normalize_profile_value(" IT / Technology   Related "))

    def test_dgroup_uses_only_explicit_membership_and_leadership(self):
        self.assertEqual("Dgroup Leader", classify_dgroup("Yes", "Yes"))
        self.assertEqual("Dgroup Member", classify_dgroup("Yes", "No"))
        self.assertEqual("Not in Dgroup", classify_dgroup("No", "No"))
        self.assertEqual("Unknown", classify_dgroup("", ""))
        self.assertEqual("Conflicting / multiple values", classify_dgroup("No", "Yes"))

    def test_privacy_threshold_is_environment_driven_and_bounded(self):
        app = Flask(__name__)
        with patch.dict(
            "os.environ",
            {"CCF_ENV": "testing", "CCF_ANALYTICS_MIN_GROUP_SIZE": "7"},
            clear=True,
        ):
            configure_app(app)
        self.assertEqual(7, app.config["ANALYTICS_MIN_GROUP_SIZE"])
        with patch.dict(
            "os.environ",
            {"CCF_ENV": "testing", "CCF_ANALYTICS_MIN_GROUP_SIZE": "0"},
            clear=True,
        ):
            with self.assertRaises(ApplicationConfigurationError):
                configure_app(Flask(__name__))


class AnalyticsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.paths = {
            "tickets": root / "tickets.csv",
            "buyers": root / "buyers.csv",
            "registrants": root / "registrants.csv",
        }
        mysql_test_url = os.environ.get("MYSQL_TEST_DATABASE_URL")
        if mysql_test_url and "test" not in (make_url(mysql_test_url).database or "").casefold():
            self.fail("MYSQL_TEST_DATABASE_URL must name a dedicated database containing 'test'.")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "DATABASE_URL": mysql_test_url
                or "sqlite+pysqlite:///{}".format(root / "test.sqlite3"),
                "STAGING_DIR": str(root / "staging"),
                "AUTHENTICATION_DISABLED": True,
                "WTF_CSRF_ENABLED": False,
            }
        )
        create_test_schema(self.app, reset=bool(mysql_test_url))
        self._write_fixture()
        with self.app.app_context():
            db = get_db()
            self.event_a = db.execute("INSERT INTO events (name) VALUES ('Event A')").lastrowid
            self.event_b = db.execute("INSERT INTO events (name) VALUES ('Event B')").lastrowid
            db.commit()

    def tearDown(self):
        self.temp.cleanup()

    def _write_fixture(self):
        buyers = [
            {
                "Id": "1", "Slug": "event-1", "Event Name": "Event One",
                "Buyer Reference Number": "B-1", "Payment Status": "Payment Validated",
                "Payment Method": "Debit or Credit Card", "Quantity": "5",
                "Gross Amount": "500", "Amount Paid": "500",
            }
        ]
        tickets = []
        registrants = []
        profiles = (
            ("Male", "IT/Technology Related", "Quezon City", "Yes", "Yes", "CCF Main"),
            ("Female", "Accounting/Finance Related", "Pasig", "Yes", "No", "Eastwood"),
            ("Female", "IT / Technology Related", "Manila", "No", "No", "Eastwood"),
            ("Male", "Others", "Others", "", "", "CCF Main"),
            ("", "", "", "", "", ""),
        )
        for index, profile in enumerate(profiles, 1):
            code = "T-{}".format(index)
            payment_status = {
                3: "Payment Failed",
                4: "Payment Cancelled",
                5: "",
            }.get(index, "Payment Validated")
            tickets.append(
                {
                    "Id": str(index), "Slug": "event-1", "Event Name": "Event One",
                    "Ticket Code": code, "Control Number": str(index),
                    "Ticket Status": "Assigned", "Payment Status": payment_status,
                    "Buyer Reference Number": "B-1",
                    "Check-in Date Time": "2026-08-29 08:00:00" if index < 5 else "",
                }
            )
            registrants.append(
                {
                    "ID": str(index), "Event Name": "Event One", "Event Slug": "event-1",
                    "Registration Code": "R-{}".format(index), "Ticket Code": code,
                    "Ticket Status": "Assigned", "Ticket Name": "Event Participant",
                    "First Name": "Private", "Last Name": "Person{}".format(index),
                    "Email Address": "private{}@example.com".format(index), "Mobile Number": "0900",
                    "Are You Attending Ccf": "Yes" if profile[5] else "",
                    "Gender": profile[0], "Life Stage": "Single", "Birth Month": "January",
                    "Birth Year": str(1980 + index),
                    "Are You From A Local Or International Satellite": "Local Satellite" if profile[5] else "",
                    "Which Local Satellite": profile[5], "Which International Satellite": "",
                    "Upload Your Accomplished Attestation Form Here": "",
                    "Occupation": profile[1], "Home Area": profile[2],
                    "Are You Part Of A Discipleship Group": profile[3],
                    "Are You Leading A Discipleship Group": profile[4],
                }
            )
        write_csv(self.paths["buyers"], BUYER_FIELDS, buyers)
        write_csv(self.paths["tickets"], TICKET_FIELDS, tickets)
        write_csv(self.paths["registrants"], REGISTRANT_FIELDS, registrants)

    def _process(self, event_id):
        staged = {key: (str(path), path.name) for key, path in self.paths.items()}
        validation = validate_batch(staged)
        self.assertTrue(validation.valid)
        with self.app.app_context():
            batch_id = store_validation(get_db(), validation, event_id)
            process_batch(get_db(), batch_id)
            self.assertEqual(batch_id, active_batch(get_db(), event_id)["id"])
        return batch_id

    def test_analytics_reconcile_supported_dimensions_and_combined_filters(self):
        batch_id = self._process(self.event_a)
        with self.app.app_context():
            analytics = event_analytics(get_db(), self.event_a, threshold=1)
            self.assertEqual(batch_id, analytics["batch"]["id"])
            self.assertEqual(5, analytics["population"]["registered"]["count"])
            self.assertEqual(4, analytics["population"]["checked_in"]["count"])
            self.assertTrue(analytics["reconciliation"]["distribution_totals"])
            for distribution in analytics["distributions"].values():
                self.assertEqual(5, sum(item["count"] for item in distribution["items"]))
            payment_counts = {
                item["label"]: item["count"]
                for item in analytics["distributions"]["payment_status"]["items"]
            }
            self.assertEqual(
                {"Payment Validated": 3, "Payment Failed": 1, "Payment Cancelled": 1},
                payment_counts,
            )
            occupation_counts = {
                item["label"]: item["count"]
                for item in analytics["distributions"]["occupation"]["items"]
            }
            self.assertEqual(2, occupation_counts["IT/Technology Related"])
            filtered = event_analytics(
                get_db(),
                self.event_a,
                {
                    "gender": "female",
                    "payment_status": "Payment Validated",
                    "home_area": "Pasig",
                },
                threshold=1,
            )
            self.assertEqual(1, filtered["population"]["registered"]["count"])
            satellite_id = next(
                item["value"]
                for item in analytics["filter_options"]["satellite"]["items"]
                if "Eastwood" in item["label"]
            )
            satellite_filtered = event_analytics(
                get_db(), self.event_a, {"satellite": satellite_id}, threshold=1
            )
            self.assertEqual(2, satellite_filtered["population"]["registered"]["count"])
            impossible = event_analytics(
                get_db(),
                self.event_a,
                {"gender": "male", "home_area": "Pasig"},
                threshold=1,
            )
            self.assertEqual(0, impossible["population"]["registered"]["count"])
            with self.assertRaises(AnalyticsFilterError):
                event_analytics(
                    get_db(), self.event_a, {"payment_status": "' OR 1=1 --"}, threshold=1
                )

    def test_privacy_suppression_hides_small_labels_and_exact_counts(self):
        self._process(self.event_a)
        with self.app.app_context():
            analytics = event_analytics(get_db(), self.event_a, threshold=3)
            occupations = analytics["distributions"]["occupation"]["items"]
            self.assertEqual(["Suppressed categories"], [item["label"] for item in occupations])
            self.assertNotIn(
                "Accounting/Finance Related",
                [item["label"] for item in analytics["filter_options"]["occupation"]["items"]],
            )
            filtered = event_analytics(
                get_db(), self.event_a, {"payment_status": "Payment Validated"}, threshold=3
            )
            self.assertEqual(3, filtered["population"]["registered"]["count"])
            self.assertIsNone(filtered["population"]["checked_in"]["count"])
            self.assertIsNone(filtered["population"]["not_checked_in"]["count"])
            complementary = event_analytics(get_db(), self.event_a, threshold=2)
            self.assertEqual(5, complementary["population"]["registered"]["count"])
            self.assertIsNone(complementary["population"]["checked_in"]["count"])
            self.assertIsNone(complementary["population"]["not_checked_in"]["count"])

    def test_api_is_aggregate_event_scoped_and_contains_no_raw_pii(self):
        self._process(self.event_a)
        self._process(self.event_b)
        self.app.config["ANALYTICS_MIN_GROUP_SIZE"] = 1
        client = self.app.test_client()
        response = client.get("/api/events/{}/analytics".format(self.event_a))
        self.assertEqual(200, response.status_code)
        body = response.get_data(as_text=True)
        for personal_value in ("private1@example.com", "0900", "Private", "Person1"):
            self.assertNotIn(personal_value, body)
        invalid = client.get(
            "/api/events/{}/analytics?home_area=Not%20An%20Allowed%20Area".format(self.event_a)
        )
        self.assertEqual(400, invalid.status_code)
        self.assertEqual(400, client.get("/analytics/compare?events=not-a-number").status_code)
        comparison = client.get(
            "/api/analytics/compare?events={},{}".format(self.event_a, self.event_b)
        )
        self.assertEqual(200, comparison.status_code)
        self.assertEqual(
            {self.event_a, self.event_b},
            {item["event"]["id"] for item in comparison.get_json()["events"]},
        )

    def test_historical_batches_are_ordered_event_scoped_snapshots(self):
        first = self._process(self.event_a)
        second = self._process(self.event_a)
        self._process(self.event_b)
        with self.app.app_context():
            trends = historical_trends(get_db(), self.event_a, threshold=1)
            self.assertEqual([first, second], [item["batch_id"] for item in trends["items"]])
            self.assertEqual(["inactive", "active"], [item["status"] for item in trends["items"]])
            self.assertTrue(trends["snapshot_semantics"])
            self.assertTrue(all(item["registered"]["count"] == 5 for item in trends["items"]))
            with self.assertRaises(AnalyticsFilterError):
                compare_events(get_db(), [self.event_a], threshold=1)
            with self.assertRaises(AnalyticsFilterError):
                compare_events(get_db(), [self.event_a, 999999], threshold=1)

    def test_analytics_page_has_filters_definitions_and_snapshot_table(self):
        self._process(self.event_a)
        self.app.config["ANALYTICS_MIN_GROUP_SIZE"] = 1
        response = self.app.test_client().get(
            "/events/{}/analytics".format(self.event_a)
        )
        self.assertEqual(200, response.status_code)
        body = response.get_data(as_text=True)
        self.assertIn("Participant distributions", body)
        self.assertIn("Registration vs check-in", body)
        self.assertIn("Historical Trends", body)
        self.assertIn("Revenue is not shown", body)
