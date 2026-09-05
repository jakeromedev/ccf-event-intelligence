import re
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.db import get_db, get_engine
from app.models import Base, hash_password, verify_password_hash


CSRF_PATTERN = re.compile(rb'name="csrf_token"[^>]*value="([^"]+)"')
PASSWORD = "PublicDashboard12!"


class PublicDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "public-dashboard-test-secret",
                "DATABASE_URL": "sqlite+pysqlite:///{}".format(
                    root / "public-dashboard.sqlite3"
                ),
                "STAGING_DIR": str(root / "staging"),
                "AUTHENTICATION_DISABLED": False,
                "WTF_CSRF_ENABLED": True,
                "SESSION_COOKIE_SECURE": False,
            }
        )
        with self.app.app_context():
            Base.metadata.create_all(get_engine())
            self.event_id = get_db().execute(
                """
                INSERT INTO events (
                    name, public_dashboard_password_hash,
                    public_dashboard_access_version
                ) VALUES (?, ?, 1)
                """,
                ("Public Event", hash_password(PASSWORD)),
            ).lastrowid
            self.disabled_event_id = get_db().execute(
                "INSERT INTO events (name) VALUES (?)", ("Private Event",)
            ).lastrowid
            get_db().commit()
        self.client = self.app.test_client()
        self.path = "/public/events/{}/dashboard".format(self.event_id)

    def tearDown(self):
        with self.app.app_context():
            get_engine().dispose()
        self.temp.cleanup()

    def _csrf(self):
        response = self.client.get(self.path)
        match = CSRF_PATTERN.search(response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode("utf-8")

    def test_public_dashboard_is_available_without_operator_authentication(self):
        response = self.client.get(self.path)
        self.assertEqual(200, response.status_code)
        self.assertIn(b"Presentation View", response.data)
        self.assertIn(b"Public Event", response.data)
        self.assertNotIn(b'application-sidebar', response.data)
        self.assertNotIn(b'application-header', response.data)
        self.assertEqual("private, no-store", response.headers["Cache-Control"])
        self.assertEqual("noindex, nofollow", response.headers["X-Robots-Tag"])

    def test_correct_password_grants_seven_day_cookie_and_dashboard_only_view(self):
        token = self._csrf()
        denied = self.client.post(
            self.path,
            data={"csrf_token": token, "password": "incorrect"},
        )
        self.assertEqual(401, denied.status_code)
        self.assertIn(b"dashboard password is incorrect", denied.data)

        token = self._csrf()
        granted = self.client.post(
            self.path,
            data={"csrf_token": token, "password": PASSWORD},
        )
        self.assertEqual(302, granted.status_code)
        cookie = granted.headers["Set-Cookie"]
        self.assertIn("Max-Age=604800", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

        dashboard = self.client.get(self.path)
        self.assertEqual(200, dashboard.status_code)
        self.assertIn(b"Event Dashboard", dashboard.data)
        self.assertIn(b"Registration snapshot", dashboard.data)
        self.assertIn(b'id="dashboard-satellite-reporting"', dashboard.data)
        self.assertIn(b"data-public-dashboard-nav", dashboard.data)
        self.assertEqual(8, dashboard.data.count(b"data-dashboard-nav-link"))
        for section_id in (
            "event-overview",
            "registration-progress",
            "satellite-targets",
            "dashboard-satellite-reporting",
            "dashboard-leadership",
            "dashboard-transportation",
            "dashboard-shirt-sizes",
            "participant-profile",
        ):
            self.assertIn('href="#{}"'.format(section_id).encode(), dashboard.data)
            self.assertIn('id="{}"'.format(section_id).encode(), dashboard.data)
        self.assertIn(b"/static/public_dashboard.js", dashboard.data)
        self.assertLess(
            dashboard.data.index(b'href="#participant-profile"'),
            dashboard.data.index(b'href="#satellite-targets"'),
        )
        self.assertLess(
            dashboard.data.index(b'id="participant-profile"'),
            dashboard.data.index(b'id="satellite-targets"'),
        )
        self.assertNotIn(b'application-sidebar', dashboard.data)
        self.assertNotIn(b'application-header', dashboard.data)
        self.assertNotIn(b'id="event-settings"', dashboard.data)
        self.assertNotIn(b"Manage Satellite Targets", dashboard.data)

        self.app.config["AUTHENTICATION_DISABLED"] = True
        bypass_dashboard = self.client.get(self.path)
        self.assertNotIn(b'id="event-settings"', bypass_dashboard.data)
        self.assertNotIn(b"Open Imports", bypass_dashboard.data)
        self.assertNotIn(b"Manage Satellite Targets", bypass_dashboard.data)

        script = (
            Path(__file__).parents[1] / "app/static/public_dashboard.js"
        ).read_text()
        self.assertIn("IntersectionObserver", script)
        self.assertIn("scrollIntoView", script)
        self.assertIn('aria-current", "location', script)

    def test_password_version_change_revokes_existing_cookie(self):
        token = self._csrf()
        self.client.post(
            self.path,
            data={"csrf_token": token, "password": PASSWORD},
        )
        self.assertIn(b"Registration snapshot", self.client.get(self.path).data)

        with self.app.app_context():
            get_db().execute(
                """
                UPDATE events
                SET public_dashboard_password_hash = ?,
                    public_dashboard_access_version = 2
                WHERE id = ?
                """,
                (hash_password("ReplacementPassword12!"), self.event_id),
            )
            get_db().commit()

        revoked = self.client.get(self.path)
        self.assertEqual(200, revoked.status_code)
        self.assertIn(b"Enter the dashboard password", revoked.data)
        self.assertNotIn(b"Registration snapshot", revoked.data)

    def test_event_without_public_password_is_not_exposed(self):
        response = self.client.get(
            "/public/events/{}/dashboard".format(self.disabled_event_id)
        )
        self.assertEqual(404, response.status_code)

    def test_event_configuration_changes_and_disables_public_password(self):
        self.app.config.update(
            AUTHENTICATION_DISABLED=True,
            WTF_CSRF_ENABLED=False,
        )
        settings_path = "/events/{}/settings".format(self.event_id)
        response = self.client.post(
            settings_path,
            data={
                "event_date": "",
                "participant_target": "",
                "public_dashboard_password": "ReplacementPassword12!",
                "public_dashboard_password_confirmation": "ReplacementPassword12!",
            },
        )
        self.assertEqual(302, response.status_code)
        with self.app.app_context():
            event = get_db().execute(
                "SELECT * FROM events WHERE id = ?", (self.event_id,)
            ).fetchone()
            self.assertTrue(
                verify_password_hash(
                    event["public_dashboard_password_hash"],
                    "ReplacementPassword12!",
                )
            )
            self.assertEqual(2, event["public_dashboard_access_version"])

        self.client.post(
            settings_path,
            data={"event_date": "", "participant_target": ""},
        )
        with self.app.app_context():
            event = get_db().execute(
                "SELECT * FROM events WHERE id = ?", (self.event_id,)
            ).fetchone()
            self.assertEqual(2, event["public_dashboard_access_version"])
            self.assertIsNotNone(event["public_dashboard_password_hash"])

        self.client.post(
            settings_path,
            data={
                "event_date": "",
                "participant_target": "",
                "disable_public_dashboard": "1",
            },
        )
        with self.app.app_context():
            event = get_db().execute(
                "SELECT * FROM events WHERE id = ?", (self.event_id,)
            ).fetchone()
            self.assertIsNone(event["public_dashboard_password_hash"])
            self.assertEqual(3, event["public_dashboard_access_version"])


if __name__ == "__main__":
    unittest.main()
