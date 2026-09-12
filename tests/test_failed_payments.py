import json
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.db import get_db, get_engine
from app.failed_payments import failed_payment_report
from app.models import Base, User, hash_password
from app.time_utils import utc_now


class FailedPaymentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = create_app({
            "TESTING": True, "SECRET_KEY": "failed-payments-test",
            "DATABASE_URL": "sqlite+pysqlite:///{}".format(root / "test.sqlite3"),
            "STAGING_DIR": str(root / "staging"),
            "AUTHENTICATION_DISABLED": True, "WTF_CSRF_ENABLED": False,
        })
        self.ctx = self.app.app_context()
        self.ctx.push()
        Base.metadata.create_all(get_engine())
        self.db = get_db()
        self.event = self.db.execute("INSERT INTO events (name) VALUES ('Test Event')").lastrowid
        self.batch = self.db.execute(
            "INSERT INTO import_batches (event_id, status, active_event_id) VALUES (?, 'active', ?)",
            (self.event, self.event),
        ).lastrowid
        self.db.commit()
        self.count = 0

    def tearDown(self):
        self.ctx.pop()
        self.temp.cleanup()

    def buyer(self, name="Alex Santos", email="alex@example.com", mobile="09171234567",
              created="2026-08-01 10:00:00", status="Payment Failed", batch=None):
        self.count += 1
        reference = "BUY-{}".format(self.count)
        self.db.execute(
            "INSERT INTO buyers (batch_id, buyer_reference, payment_status, source_data_json) VALUES (?, ?, ?, ?)",
            (batch or self.batch, reference, status, json.dumps({
                "Buyer Name": name, "Email Address": email, "Mobile Number": mobile,
                "Created At": created, "Failed At": created, "Failed Reason": "Bank declined",
            })),
        )
        self.db.commit()
        return reference

    def registration(self, first="Alex", last="Santos", email="alex@example.com",
                     mobile="+63 917 123 4567", created="2026-08-02 10:00:00",
                     status="Payment Validated", batch=None):
        self.count += 1
        batch = batch or self.batch
        ticket = "T-{}".format(self.count)
        self.db.execute(
            "INSERT INTO tickets (batch_id, ticket_code, payment_status) VALUES (?, ?, ?)",
            (batch, ticket, status),
        )
        self.db.execute(
            """INSERT INTO registrants (batch_id, registration_code, ticket_code,
               first_name, last_name, affiliation, source_data_json)
               VALUES (?, ?, ?, ?, ?, 'Unknown', ?)""",
            (batch, "R-{}".format(self.count), ticket, first, last, json.dumps({
                "Email Address": email, "Mobile Number": mobile, "Created At": created,
            })),
        )
        self.db.commit()

    def report(self):
        return failed_payment_report(self.db, self.batch)

    def test_failed_buyers_without_registrant_rows_are_listed_and_grouped(self):
        self.buyer()
        latest = self.buyer(created="2026-08-03 10:00:00")
        self.buyer(status="Payment Cancelled")
        self.buyer(status="For Payment Validation")
        report = self.report()
        self.assertEqual(2, report["failed_attempts"])
        self.assertEqual(1, len(report["rows"]))
        self.assertEqual(2, report["rows"][0]["attempts"])
        self.assertEqual(latest, report["rows"][0]["reference"])

    def test_later_paid_registration_removes_failed_attempt_with_normalized_contact(self):
        self.buyer(email=" ALEX@EXAMPLE.COM ")
        self.registration(first=" ALEX ", email="different@example.com", created="August 02, 2026 10:00 AM")
        self.assertEqual([], self.report()["rows"])
        self.assertEqual(1, self.report()["recovered_attempts"])

    def test_pending_and_earlier_registrations_do_not_hide_failed_attempt(self):
        self.buyer()
        self.registration(status="For Payment Validation")
        self.assertEqual(1, len(self.report()["rows"]))
        self.registration(created="2026-07-31 10:00:00")
        self.assertEqual(1, len(self.report()["rows"]))
        self.assertEqual(1, self.report()["review_count"])

    def test_missing_dates_and_shared_contacts_stay_for_review(self):
        self.buyer()
        self.registration(first="Jamie")
        self.assertEqual(1, self.report()["review_count"])
        self.registration(created="")
        self.assertEqual(1, len(self.report()["rows"]))
        self.assertIn("date unavailable", self.report()["rows"][0]["review"])

    def test_missing_contacts_are_not_merged_by_name(self):
        self.buyer(email="", mobile="")
        self.buyer(email="", mobile="")
        self.registration()
        self.assertEqual(2, len(self.report()["rows"]))
        self.assertEqual(2, self.report()["review_count"])

    def test_comparison_stays_in_active_batch_and_event(self):
        self.buyer()
        other_event = self.db.execute("INSERT INTO events (name) VALUES ('Other Event')").lastrowid
        other_batch = self.db.execute(
            "INSERT INTO import_batches (event_id, status, active_event_id) VALUES (?, 'active', ?)",
            (other_event, other_event),
        ).lastrowid
        inactive = self.db.execute(
            "INSERT INTO import_batches (event_id, status) VALUES (?, 'inactive')", (self.event,),
        ).lastrowid
        self.registration(batch=other_batch)
        self.registration(batch=inactive)
        self.buyer(name="Other person", batch=other_batch)
        self.assertEqual(1, len(self.report()["rows"]))
        self.assertEqual(1, self.report()["failed_attempts"])

    def test_page_search_pagination_empty_state_and_escaping(self):
        for index in range(28):
            self.buyer(name="Person {}".format(index))
        self.buyer(name="<script>alert(1)</script>")
        client = self.app.test_client()
        url = "/events/{}/failed-payments".format(self.event)
        page = client.get(url + "?page=2")
        self.assertEqual(200, page.status_code)
        self.assertIn(b"Page 2 of 2", page.data)
        search = client.get(url, query_string={"q": "<script>"})
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", search.data)
        self.assertNotIn(b"<script>alert(1)</script>", search.data)
        self.assertIn(b"No matches found", client.get(url + "?q=missing").data)
        self.assertEqual(200, client.get(url + "?page=bad&per_page=bad").status_code)
        self.assertEqual(404, client.get("/events/9999/failed-payments").status_code)
        self.db.execute("UPDATE import_batches SET status = 'inactive', active_event_id = NULL WHERE id = ?", (self.batch,))
        self.db.commit()
        self.assertIn(b"No active import yet", client.get(url).data)

    def test_role_access(self):
        self.app.config["AUTHENTICATION_DISABLED"] = False
        self.buyer()
        url = "/events/{}/failed-payments".format(self.event)
        client = self.app.test_client()
        self.assertEqual(302, client.get(url).status_code)
        for role, username, expected in (("user", "operator", 200),
                                         ("admin", "admin", 200),
                                         ("registration", "registration-operator", 403)):
            user = User(username=username, role=role, status="approved", approved_at=utc_now(),
                        password_hash=hash_password("StrongPassword12!"), auth_version=1)
            self.db.session.add(user)
            self.db.commit()
            self.ctx.pop()
            self.ctx = self.app.app_context()
            self.ctx.push()
            self.db = get_db()
            client = self.app.test_client()
            client.post("/login", data={"username": username, "password": "StrongPassword12!"})
            self.assertEqual(expected, client.get(url).status_code)
            overview = client.get("/events/{}".format(self.event))
            self.assertEqual(expected == 200, b">Failed Payments</span>" in overview.data)

    def test_table_excludes_review_cases_before_search_and_pagination(self):
        self.buyer(name="Visible Person", email="visible@example.com", mobile="")
        for index in range(30):
            self.buyer(name="Uncertain {}".format(index), email="", mobile="")
        self.buyer()
        self.registration(created="")
        self.assertEqual(31, self.report()["review_count"])
        client = self.app.test_client()
        url = "/events/{}/failed-payments".format(self.event)
        page = client.get(url)
        self.assertEqual(200, page.status_code)
        self.assertIn(b"Visible Person", page.data)
        self.assertNotIn(b"Uncertain 0", page.data)
        self.assertNotIn(b"Alex Santos", page.data)
        self.assertIn(b"Page 1 of 1", page.data)
        self.assertIn(b"1 result", page.data)
        search = client.get(url, query_string={"q": "Uncertain"})
        self.assertIn(b"No matches found", search.data)
