import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import event as sqlalchemy_event, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app import create_app
from app.db import get_db, get_engine
from app.models import Base, User
from app.time_utils import utc_now


CSRF_PATTERN = re.compile(rb'name="csrf_token"[^>]*value="([^"]+)"')


def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    dbapi_connection.execute("PRAGMA foreign_keys = ON")


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        mysql_test_url = os.environ.get("MYSQL_TEST_DATABASE_URL")
        if mysql_test_url and "test" not in (
            make_url(mysql_test_url).database or ""
        ).casefold():
            self.fail("MYSQL_TEST_DATABASE_URL must name a dedicated test database.")
        database_url = mysql_test_url or "sqlite+pysqlite:///{}".format(
            root / "auth.sqlite3"
        )
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "auth-test-secret",
                "DATABASE_URL": database_url,
                "STAGING_DIR": str(root / "staging"),
                "AUTHENTICATION_DISABLED": False,
                "WTF_CSRF_ENABLED": True,
            }
        )
        with self.app.app_context():
            engine = get_engine()
            if engine.dialect.name == "sqlite":
                sqlalchemy_event.listen(
                    engine, "connect", enable_sqlite_foreign_keys
                )
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            get_engine().dispose()
        self.temp.cleanup()

    def csrf(self, path):
        response = self.client.get(path)
        self.assertEqual(200, response.status_code)
        match = CSRF_PATTERN.search(response.data)
        self.assertIsNotNone(match, response.data[:500])
        return match.group(1).decode("utf-8")

    def register(self, username, password="StrongPassword12!", confirm=None):
        token = self.csrf("/register")
        return self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "username": username,
                "password": password,
                "confirm_password": confirm if confirm is not None else password,
            },
            follow_redirects=True,
        )

    def login(self, username, password, follow_redirects=True):
        token = self.csrf("/login")
        return self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": username,
                "password": password,
            },
            follow_redirects=follow_redirects,
        )

    def logout(self):
        token = self.csrf("/events")
        return self.client.post(
            "/logout", data={"csrf_token": token}, follow_redirects=True
        )

    def create_user(
        self,
        username,
        password="StrongPassword12!",
        role="user",
        status="approved",
    ):
        with self.app.app_context():
            user = User(
                username=username,
                role=role,
                status=status,
                approved_at=datetime.now() if status == "approved" else None,
            )
            user.set_password(password)
            get_db().session.add(user)
            get_db().commit()
            return user.id

    def initialize_admin(self):
        result = self.app.test_cli_runner().invoke(args=["admin-init"])
        self.assertEqual(0, result.exit_code, result.output)
        match = re.search(r"(?:New )?Password: (\S+)", result.output)
        self.assertIsNotNone(match, result.output)
        return result, match.group(1)

    def test_application_name_brands_authentication_and_application_shell(self):
        login_page = self.client.get("/login")
        self.assertEqual(200, login_page.status_code)
        self.assertIn(b"<title>Login \xc2\xb7 B1G Admin Internal System</title>", login_page.data)
        self.assertIn(b'aria-label="B1G Admin Internal System"', login_page.data)
        self.assertIn(b"/static/b1g-logo-circle.png", login_page.data)
        self.assertNotIn(b"CCF-Logo-2017-01.png", login_page.data)
        self.assertNotIn(b"CCF Event Intelligence", login_page.data)

        self.create_user("brand-check")
        events_page = self.login("brand-check", "StrongPassword12!")
        self.assertEqual(200, events_page.status_code)
        self.assertIn(b"<title>Events \xc2\xb7 B1G Admin Internal System</title>", events_page.data)
        self.assertIn(b"B1G Admin Internal System", events_page.data)
        self.assertIn(b"/static/b1g-logo-circle.png", events_page.data)
        self.assertNotIn(b"CCF-Logo-2017-01.png", events_page.data)
        self.assertNotIn(b"CCF Event Dashboard", events_page.data)

        styles = (Path(__file__).parents[1] / "app/static/app.css").read_text()
        for token in (
            "--b1g-red: #7a0b0b",
            "--b1g-burgundy: #4a0909",
            "--b1g-cream: #faead2",
            "--b1g-page-background: #faead2",
            "--b1g-page-background-soft: #f7e9d4",
            "--b1g-surface: #ffffff",
            "--b1g-surface-muted: #fff8ee",
            "--b1g-border: #e6d2b9",
            "--b1g-focus-ring: rgba(122, 11, 11, .2)",
        ):
            self.assertIn(token, styles)
        self.assertIn(".nav-link.active", styles)
        self.assertIn("object-fit: contain", styles)
        self.assertIn(".app-main { background: var(--b1g-page-background); }", styles)
        self.assertIn(".auth-form-panel { background: var(--b1g-page-background); }", styles)
        self.assertIn(".sidebar { overflow: hidden; }", styles)
        self.assertIn(':not([type="submit"])', styles)

    def test_admin_init_creates_then_resets_one_admin_and_invalidates_session(self):
        first, old_password = self.initialize_admin()
        self.assertIn("Admin account initialized successfully", first.output)
        self.assertGreaterEqual(len(old_password), 20)
        with self.app.app_context():
            admins = get_db().session.scalars(
                select(User).where(User.role == "admin")
            ).all()
            self.assertEqual(1, len(admins))
            admin = admins[0]
            original_id = admin.id
            self.assertEqual("admin", admin.username)
            self.assertEqual("approved", admin.status)
            self.assertIsNotNone(admin.approved_at)
            self.assertTrue(admin.check_password(old_password))
            self.assertNotEqual(old_password, admin.password_hash)
            self.assertTrue(admin.password_hash.startswith("$argon2id$"))

        self.assertEqual(200, self.login("admin", old_password).status_code)
        second, new_password = self.initialize_admin()
        self.assertIn("WARNING: An admin account already exists", second.output)
        self.assertIn("OVERRIDDEN", second.output)
        self.assertIn("previous admin password is no longer valid", second.output)
        self.assertNotEqual(old_password, new_password)
        with self.app.app_context():
            admins = get_db().session.scalars(
                select(User).where(User.role == "admin")
            ).all()
            self.assertEqual(1, len(admins))
            self.assertEqual(original_id, admins[0].id)
            self.assertFalse(admins[0].check_password(old_password))
            self.assertTrue(admins[0].check_password(new_password))

        invalidated = self.client.get("/events")
        self.assertEqual(302, invalidated.status_code)
        self.assertIn("/login", invalidated.headers["Location"])
        self.assertIn(b"Invalid username or password", self.login("admin", old_password).data)
        self.assertEqual(200, self.login("admin", new_password).status_code)

    def test_registration_is_pending_normalized_hashed_and_not_logged_in(self):
        response = self.register("  New.Operator  ")
        self.assertIn(b"awaiting administrator approval", response.data)
        with self.app.app_context():
            user = get_db().session.scalar(
                select(User).where(User.username == "new.operator")
            )
            self.assertIsNotNone(user)
            self.assertEqual("user", user.role)
            self.assertEqual("pending", user.status)
            self.assertIsNone(user.approved_at)
            self.assertIsNone(user.approved_by)
            self.assertNotIn("StrongPassword12!", user.password_hash)
        protected = self.client.get("/events")
        self.assertEqual(302, protected.status_code)

    def test_public_registration_cannot_self_assign_registration_role(self):
        token = self.csrf("/register")
        response = self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "username": "role-requester",
                "password": "StrongPassword12!",
                "confirm_password": "StrongPassword12!",
                "role": "registration",
            },
            follow_redirects=True,
        )
        self.assertEqual(200, response.status_code)
        with self.app.app_context():
            user = get_db().session.scalar(
                select(User).where(User.username == "role-requester")
            )
            self.assertEqual("user", user.role)
            self.assertEqual("pending", user.status)

    def test_registration_rejects_reserved_duplicate_weak_and_mismatched_values(self):
        for reserved in ("admin", "Admin", "ADMIN", "  AdMiN  "):
            with self.subTest(reserved=reserved):
                response = self.register(reserved)
                self.assertIn(b"username is reserved", response.data)
        self.assertEqual(200, self.register("duplicate").status_code)
        duplicate = self.register("DUPLICATE")
        self.assertIn(b"already registered", duplicate.data)
        weak = self.register("weak-user", password="short", confirm="short")
        self.assertIn(b"between 12 and 128", weak.data)
        mismatch = self.register(
            "mismatch", password="StrongPassword12!", confirm="DifferentPassword12!"
        )
        self.assertIn(b"Passwords must match", mismatch.data)
        with self.app.app_context():
            self.assertEqual(
                1,
                get_db().session.scalar(
                    select(func.count(User.id)).where(User.username == "duplicate")
                ),
            )

    def test_authentication_pending_invalid_approved_logout_and_csrf(self):
        self.assertEqual(302, self.client.get("/events").status_code)
        self.assertEqual(302, self.client.get("/events/1/dashboard").status_code)
        self.assertEqual(
            302,
            self.client.post(
                "/events/1/satellite-datasets",
                data={
                    "name": "Unauthenticated",
                    "participant_target": "10",
                    "satellite_ids": "1",
                },
            ).status_code,
        )
        self.assertEqual(
            400,
            self.client.post(
                "/register",
                data={
                    "username": "no-csrf",
                    "password": "StrongPassword12!",
                    "confirm_password": "StrongPassword12!",
                },
            ).status_code,
        )

        self.register("pending-user")
        pending = self.login("pending-user", "StrongPassword12!")
        self.assertIn(b"awaiting administrator approval", pending.data)
        self.assertEqual(302, self.client.get("/events").status_code)
        invalid = self.login("pending-user", "WrongPassword12!")
        self.assertIn(b"Invalid username or password", invalid.data)

        self.create_user("approved-user")
        approved = self.login("approved-user", "StrongPassword12!")
        self.assertEqual(200, approved.status_code)
        self.assertIn(b"Your Events", approved.data)
        logged_out = self.logout()
        self.assertIn(b"You have been logged out", logged_out.data)
        self.assertEqual(302, self.client.get("/events").status_code)

    def test_analytics_is_hidden_and_denied_for_standard_users(self):
        with self.app.app_context():
            db = get_db()
            event_a = db.execute("INSERT INTO events (name) VALUES ('Analytics A')").lastrowid
            event_b = db.execute("INSERT INTO events (name) VALUES ('Analytics B')").lastrowid
            db.commit()
        analytics_paths = (
            "/events/{}/analytics".format(event_a),
            "/api/events/{}/analytics".format(event_a),
            "/api/events/{}/analytics/trends".format(event_a),
            "/analytics/compare?events={},{}".format(event_a, event_b),
            "/api/analytics/compare?events={},{}".format(event_a, event_b),
        )
        for path in analytics_paths:
            with self.subTest(path=path):
                self.assertEqual(302, self.client.get(path).status_code)

        self.create_user("analytics-operator")
        self.login("analytics-operator", "StrongPassword12!")
        event_page = self.client.get("/events/{}".format(event_a))
        self.assertEqual(200, event_page.status_code)
        self.assertNotIn(
            'href="/events/{}/analytics"'.format(event_a).encode("utf-8"),
            event_page.data,
        )
        for path in analytics_paths:
            with self.subTest(role="standard", path=path):
                self.assertEqual(403, self.client.get(path).status_code)

        self.logout()
        _, admin_password = self.initialize_admin()
        self.login("admin", admin_password)
        admin_page = self.client.get("/events/{}".format(event_a))
        self.assertIn(
            'href="/events/{}/analytics"'.format(event_a).encode("utf-8"),
            admin_page.data,
        )
        self.assertEqual(
            200, self.client.get("/api/events/{}/analytics".format(event_a)).status_code
        )
        self.assertEqual(
            200,
            self.client.get(
                "/api/analytics/compare?events={},{}".format(event_a, event_b)
            ).status_code,
        )

    def test_secure_session_cookie_and_external_redirect_rejection(self):
        self.create_user("secure-operator")
        self.app.config["SESSION_COOKIE_SECURE"] = True
        token = self.csrf("/login?next=https://attacker.example/steal")
        response = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": "secure-operator",
                "password": "StrongPassword12!",
                "next_url": "https://attacker.example/steal",
            },
            follow_redirects=False,
        )
        self.assertEqual(302, response.status_code)
        self.assertTrue(response.headers["Location"].endswith("/events"))
        cookie_headers = "\n".join(response.headers.getlist("Set-Cookie"))
        self.assertIn("Secure", cookie_headers)
        self.assertIn("HttpOnly", cookie_headers)
        self.assertIn("SameSite=Lax", cookie_headers)

    def test_registration_role_lands_on_dashboard_instead_of_restricted_next(self):
        self.create_user("registration-landing", role="registration")
        token = self.csrf("/login?next=/analytics/compare")
        response = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "username": "registration-landing",
                "password": "StrongPassword12!",
                "next_url": "/analytics/compare",
            },
            follow_redirects=False,
        )
        self.assertEqual(302, response.status_code)
        self.assertTrue(response.headers["Location"].endswith("/events"))

    def test_registration_role_can_view_satellites_but_not_satellite_settings(self):
        self.create_user("satellite-registration", role="registration")
        with self.app.app_context():
            event_id = get_db().execute(
                "INSERT INTO events (name) VALUES ('Satellite Access Event')"
            ).lastrowid
            get_db().commit()

        self.login("satellite-registration", "StrongPassword12!")
        page = self.client.get("/events/{}/satellites".format(event_id))
        self.assertEqual(200, page.status_code)
        self.assertIn(b"Satellite Overview", page.data)
        self.assertIn(
            'href="/events/{}/satellites"'.format(event_id).encode("utf-8"),
            page.data,
        )
        self.assertNotIn(b'href="/satellites/settings', page.data)

        drilldown = self.client.get(
            "/events/{}/satellites/registrants".format(event_id)
        )
        self.assertEqual(200, drilldown.status_code)
        self.assertIn(b"No active dataset for this event", drilldown.data)

        self.assertEqual(
            403,
            self.client.get(
                "/satellites/settings", query_string={"event_id": event_id}
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.get(
                "/satellites/settings/registrants",
                query_string={"event_id": event_id},
            ).status_code,
        )
        token = CSRF_PATTERN.search(page.data).group(1).decode("utf-8")
        self.assertEqual(
            403,
            self.client.post(
                "/satellites/settings/hubs",
                data={
                    "csrf_token": token,
                    "event_id": event_id,
                    "hub_group_id": 1,
                    "name": "Denied Hub",
                },
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.post(
                "/satellites/settings/registrants/1/satellite",
                data={
                    "csrf_token": token,
                    "event_id": event_id,
                    "directory_id": 1,
                },
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.post(
                "/satellites/settings/registrants/1/satellite/reset",
                data={"csrf_token": token, "event_id": event_id},
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.post(
                "/events/{}/satellite-target-categories/targets".format(event_id),
                data={
                    "csrf_token": token,
                    "target_outside_metro_manila": "10",
                    "target_within_metro_manila": "20",
                    "target_main": "30",
                },
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.post(
                "/events/{}/satellite-target-groups/grouping".format(event_id),
                data={"csrf_token": token, "grouping_preset": "all"},
            ).status_code,
        )

    def test_admin_target_and_grouping_updates_require_csrf(self):
        _, admin_password = self.initialize_admin()
        with self.app.app_context():
            db = get_db()
            event_id = db.execute(
                "INSERT INTO events (name) VALUES ('Target Category Security')"
            ).lastrowid
            from app.satellite_target_categories import satellite_target_groups

            groups = satellite_target_groups(db, event_id)["groups"]
            db.commit()
        self.login("admin", admin_password)
        target_path = "/events/{}/satellite-target-categories/targets".format(event_id)
        target_data = {
            "target_group_{}".format(group["id"]): str(value)
            for group, value in zip(groups, (10, 20, 30))
        }
        self.assertEqual(400, self.client.post(target_path, data=target_data).status_code)
        target_data["csrf_token"] = self.csrf("/events/{}".format(event_id))
        self.assertEqual(302, self.client.post(target_path, data=target_data).status_code)
        with self.app.app_context():
            values = {
                row["category_key"]: row["participant_target"]
                for row in get_db().execute(
                    """
                    SELECT member.category_key, report.participant_target
                    FROM event_satellite_target_group_categories member
                    JOIN event_satellite_target_groups report
                      ON report.id = member.target_group_id
                     AND report.event_id = member.event_id
                    WHERE member.event_id = ?
                    """,
                    (event_id,),
                ).fetchall()
            }
        self.assertEqual(
            {"outside_metro_manila": 10, "within_metro_manila": 20, "main": 30},
            values,
        )

        grouping_path = "/events/{}/satellite-target-groups/grouping".format(event_id)
        self.assertEqual(
            400,
            self.client.post(
                grouping_path, data={"grouping_preset": "outside_within"}
            ).status_code,
        )
        grouping_token = self.csrf(
            "/satellites/settings?event_id={}&view=targets".format(event_id)
        )
        self.assertEqual(
            302,
            self.client.post(
                grouping_path,
                data={
                    "csrf_token": grouping_token,
                    "grouping_preset": "outside_within",
                },
            ).status_code,
        )
        with self.app.app_context():
            rows = get_db().execute(
                """
                SELECT participant_target FROM event_satellite_target_groups
                WHERE event_id = ? ORDER BY sort_order
                """,
                (event_id,),
            ).fetchall()
        self.assertEqual([30, 30], [row["participant_target"] for row in rows])

    def test_login_lockout_blocks_correct_password_until_expiry(self):
        user_id = self.create_user("lockout-operator")
        for _attempt in range(5):
            response = self.login("lockout-operator", "WrongPassword12!")
            self.assertIn(b"Invalid username or password", response.data)

        blocked = self.login("lockout-operator", "StrongPassword12!")
        self.assertIn(b"Too many login attempts", blocked.data)
        with self.app.app_context():
            user = get_db().session.get(User, user_id)
            self.assertIsNotNone(user.locked_until)
            user.locked_until = utc_now() - timedelta(seconds=1)
            get_db().commit()

        recovered = self.login("lockout-operator", "StrongPassword12!")
        self.assertEqual(200, recovered.status_code)
        self.assertIn(b"Your Events", recovered.data)

    def test_admin_approval_and_server_side_authorization(self):
        _, admin_password = self.initialize_admin()
        pending_id = self.create_user("awaiting-user", status="pending")
        normal_id = self.create_user("normal-user")

        self.login("normal-user", "StrongPassword12!")
        self.assertEqual(403, self.client.get("/admin/users").status_code)
        token = self.csrf("/events")
        self.assertEqual(
            403,
            self.client.post(
                "/admin/users/{}/approve".format(pending_id),
                data={"csrf_token": token},
            ).status_code,
        )
        self.logout()

        self.login("admin", admin_password)
        page = self.client.get("/admin/users")
        self.assertEqual(200, page.status_code)
        self.assertIn(b"awaiting-user", page.data)
        self.assertIn(b">Settings</span>", page.data)
        self.assertIn(b'aria-controls="application-settings-submenu"', page.data)
        self.assertIn(b'id="application-settings-submenu"', page.data)
        self.assertIn(b'class="nav-module active expanded"', page.data)
        self.assertIn(b'class="active" href="/admin/users"', page.data)
        token_match = CSRF_PATTERN.search(page.data)
        self.assertIsNotNone(token_match)
        approved = self.client.post(
            "/admin/users/{}/approve".format(pending_id),
            data={"csrf_token": token_match.group(1).decode("utf-8")},
            follow_redirects=True,
        )
        self.assertIn(b"awaiting-user has been approved", approved.data)
        with self.app.app_context():
            user = get_db().session.get(User, pending_id)
            admin = get_db().session.scalar(
                select(User).where(User.username == "admin")
            )
            self.assertEqual("approved", user.status)
            self.assertIsNotNone(user.approved_at)
            self.assertEqual(admin.id, user.approved_by)
            self.assertEqual("user", get_db().session.get(User, normal_id).role)
        self.logout()
        self.assertEqual(
            200, self.login("awaiting-user", "StrongPassword12!").status_code
        )

    def test_admin_can_assign_registration_role_during_and_after_approval(self):
        _, admin_password = self.initialize_admin()
        pending_id = self.create_user("registration-request", status="pending")
        existing_id = self.create_user("existing-operator")
        self.login("admin", admin_password)

        page = self.client.get("/admin/users")
        self.assertIn(b">Registration</option>", page.data)
        token = CSRF_PATTERN.search(page.data).group(1).decode("utf-8")
        approved = self.client.post(
            "/admin/users/{}/approve".format(pending_id),
            data={"csrf_token": token, "role": "registration"},
            follow_redirects=True,
        )
        self.assertEqual(200, approved.status_code)
        with self.app.app_context():
            assigned = get_db().session.get(User, pending_id)
            self.assertEqual("registration", assigned.role)
            self.assertEqual("approved", assigned.status)

        token = CSRF_PATTERN.search(approved.data).group(1).decode("utf-8")
        changed = self.client.post(
            "/admin/users/{}/role".format(existing_id),
            data={"csrf_token": token, "role": "registration"},
            follow_redirects=True,
        )
        self.assertEqual(200, changed.status_code)
        self.assertIn(b"now has the Registration role", changed.data)
        with self.app.app_context():
            self.assertEqual(
                "registration", get_db().session.get(User, existing_id).role
            )

        token = CSRF_PATTERN.search(changed.data).group(1).decode("utf-8")
        self.assertEqual(
            400,
            self.client.post(
                "/admin/users/{}/role".format(existing_id),
                data={"csrf_token": token, "role": "admin"},
            ).status_code,
        )

    def test_admin_can_change_password_and_block_or_unblock_users(self):
        _, admin_password = self.initialize_admin()
        user_id = self.create_user("managed-operator")
        self.login("admin", admin_password)

        page = self.client.get("/admin/users")
        self.assertIn(b"Change Password", page.data)
        self.assertIn(b">Block Account</button>", page.data)
        self.assertIn(b"data-user-management-open", page.data)
        self.assertIn(b"data-user-management-dialog", page.data)
        self.assertIn(b"users.js", page.data)
        token = CSRF_PATTERN.search(page.data).group(1).decode("utf-8")

        weak = self.client.post(
            "/admin/users/{}/password".format(user_id),
            data={
                "csrf_token": token,
                "new_password": "short",
                "confirm_password": "short",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Password must be between 12 and 128 characters", weak.data)

        token = CSRF_PATTERN.search(weak.data).group(1).decode("utf-8")
        mismatch = self.client.post(
            "/admin/users/{}/password".format(user_id),
            data={
                "csrf_token": token,
                "new_password": "NewStrongPassword12!",
                "confirm_password": "DifferentPassword12!",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Passwords must match", mismatch.data)

        token = CSRF_PATTERN.search(mismatch.data).group(1).decode("utf-8")
        changed = self.client.post(
            "/admin/users/{}/password".format(user_id),
            data={
                "csrf_token": token,
                "new_password": "NewStrongPassword12!",
                "confirm_password": "NewStrongPassword12!",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Existing sessions were signed out", changed.data)
        with self.app.app_context():
            user = get_db().session.get(User, user_id)
            self.assertTrue(user.check_password("NewStrongPassword12!"))
            self.assertFalse(user.check_password("StrongPassword12!"))
            password_auth_version = user.auth_version

        token = CSRF_PATTERN.search(changed.data).group(1).decode("utf-8")
        blocked = self.client.post(
            "/admin/users/{}/status".format(user_id),
            data={"csrf_token": token, "status": "blocked"},
            follow_redirects=True,
        )
        self.assertIn(b"managed-operator has been blocked", blocked.data)
        self.assertIn(b">Unblock Account</button>", blocked.data)
        with self.app.app_context():
            user = get_db().session.get(User, user_id)
            self.assertEqual("blocked", user.status)
            self.assertGreater(user.auth_version, password_auth_version)

        self.logout()
        denied = self.login("managed-operator", "NewStrongPassword12!")
        self.assertIn(b"account has been blocked", denied.data)

        self.login("admin", admin_password)
        token = self.csrf("/admin/users")
        unblocked = self.client.post(
            "/admin/users/{}/status".format(user_id),
            data={"csrf_token": token, "status": "approved"},
            follow_redirects=True,
        )
        self.assertIn(b"managed-operator has been unblocked", unblocked.data)
        self.logout()
        self.assertEqual(
            200,
            self.login("managed-operator", "NewStrongPassword12!").status_code,
        )

    def test_admin_can_change_non_admin_username_with_public_username_rules(self):
        _, admin_password = self.initialize_admin()
        user_id = self.create_user("original-operator")
        self.create_user("existing-operator")
        self.login("admin", admin_password)

        page = self.client.get("/admin/users")
        self.assertIn(b"Save Username", page.data)
        self.assertIn(
            "/admin/users/{}/username".format(user_id).encode("utf-8"),
            page.data,
        )
        with self.app.app_context():
            original_auth_version = get_db().session.get(User, user_id).auth_version

        token = CSRF_PATTERN.search(page.data).group(1).decode("utf-8")
        changed = self.client.post(
            "/admin/users/{}/username".format(user_id),
            data={"csrf_token": token, "username": "  Renamed.Operator  "},
            follow_redirects=True,
        )
        self.assertIn(
            b"Username changed from original-operator to renamed.operator",
            changed.data,
        )
        self.assertIn(b"Existing sessions were signed out", changed.data)
        with self.app.app_context():
            renamed = get_db().session.get(User, user_id)
            self.assertEqual("renamed.operator", renamed.username)
            self.assertGreater(renamed.auth_version, original_auth_version)

        rejected_values = (
            ("admin", b"username is reserved"),
            ("ab", b"between 3 and 64 characters"),
            ("invalid username", b"Use lowercase letters"),
            ("EXISTING-OPERATOR", b"already registered"),
        )
        response = changed
        for value, message in rejected_values:
            with self.subTest(value=value):
                token = CSRF_PATTERN.search(response.data).group(1).decode("utf-8")
                response = self.client.post(
                    "/admin/users/{}/username".format(user_id),
                    data={"csrf_token": token, "username": value},
                    follow_redirects=True,
                )
                self.assertIn(message, response.data)
                with self.app.app_context():
                    self.assertEqual(
                        "renamed.operator",
                        get_db().session.get(User, user_id).username,
                    )

        with self.app.app_context():
            admin_id = get_db().session.scalar(
                select(User.id).where(User.username == "admin")
            )
        token = CSRF_PATTERN.search(response.data).group(1).decode("utf-8")
        self.assertEqual(
            404,
            self.client.post(
                "/admin/users/{}/username".format(admin_id),
                data={"csrf_token": token, "username": "renamed-admin"},
            ).status_code,
        )

        self.logout()
        self.assertIn(
            b"Invalid username or password",
            self.login("original-operator", "StrongPassword12!").data,
        )
        self.assertEqual(
            200,
            self.login("renamed.operator", "StrongPassword12!").status_code,
        )

    def test_non_admin_cannot_manage_user_credentials_or_block_status(self):
        target_id = self.create_user("managed-target")
        self.create_user("ordinary-operator")
        self.login("ordinary-operator", "StrongPassword12!")
        token = self.csrf("/events")
        self.assertEqual(
            403,
            self.client.post(
                "/admin/users/{}/username".format(target_id),
                data={"csrf_token": token, "username": "renamed-target"},
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.post(
                "/admin/users/{}/password".format(target_id),
                data={
                    "csrf_token": token,
                    "new_password": "NewStrongPassword12!",
                    "confirm_password": "NewStrongPassword12!",
                },
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.post(
                "/admin/users/{}/status".format(target_id),
                data={"csrf_token": token, "status": "blocked"},
            ).status_code,
        )

    def test_database_and_web_paths_cannot_create_a_second_admin(self):
        self.initialize_admin()
        self.assertIn(b"username is reserved", self.register("ADMIN").data)
        with self.app.app_context():
            db = get_db()
            illegal = User(
                username="second-admin",
                role="admin",
                status="approved",
                approved_at=datetime.now(),
            )
            illegal.set_password("StrongPassword12!")
            db.session.add(illegal)
            with self.assertRaises(DBAPIError):
                db.commit()
            db.rollback()
            self.assertEqual(
                1,
                db.session.scalar(
                    select(func.count(User.id)).where(User.role == "admin")
                ),
            )

    def test_only_admin_can_delete_non_active_import_batches(self):
        _, admin_password = self.initialize_admin()
        self.create_user("normal-operator")
        with self.app.app_context():
            db = get_db()
            event_id = db.execute(
                "INSERT INTO events (name) VALUES ('Deletion Test Event')"
            ).lastrowid
            inactive_batch = db.execute(
                """
                INSERT INTO import_batches (
                    event_id, event_slug, event_name, status, processed_at, activated_at
                ) VALUES (?, 'deletion-test', 'Deletion Test Event', 'inactive',
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (event_id,),
            ).lastrowid
            active_batch_id = db.execute(
                """
                INSERT INTO import_batches (
                    event_id, event_slug, event_name, status, active_event_id,
                    processed_at, activated_at
                ) VALUES (?, 'deletion-test', 'Deletion Test Event', 'active', ?,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (event_id, event_id),
            ).lastrowid
            staged_file = Path(self.app.config["STAGING_DIR"]) / "delete-me" / "tickets.csv"
            staged_file.parent.mkdir(parents=True, exist_ok=True)
            staged_file.write_text("header\n", encoding="utf-8")
            db.execute(
                """
                INSERT INTO import_files (
                    batch_id, export_type, filename, staged_path, status
                ) VALUES (?, 'tickets', 'tickets.csv', ?, 'valid')
                """,
                (inactive_batch, str(staged_file)),
            )
            db.commit()

        imports_path = "/events/{}/imports".format(event_id)
        self.login("normal-operator", "StrongPassword12!")
        normal_page = self.client.get(imports_path)
        self.assertEqual(403, normal_page.status_code)
        self.assertNotIn(b">Delete</button>", normal_page.data)
        token = self.csrf("/events/{}".format(event_id))
        denied = self.client.post(
            "/events/{}/imports/{}/delete".format(event_id, inactive_batch),
            data={"csrf_token": token},
        )
        self.assertEqual(403, denied.status_code)
        self.logout()

        self.login("admin", admin_password)
        admin_page = self.client.get(imports_path)
        self.assertIn(b">Delete</button>", admin_page.data)
        token = self.csrf(imports_path)
        active_denied = self.client.post(
            "/events/{}/imports/{}/delete".format(event_id, active_batch_id),
            data={"csrf_token": token},
            follow_redirects=True,
        )
        self.assertIn(b"Activate another batch before deleting", active_denied.data)

        deleted = self.client.post(
            "/events/{}/imports/{}/delete".format(event_id, inactive_batch),
            data={"csrf_token": token},
            follow_redirects=True,
        )
        self.assertIn(b"and its stored data were deleted", deleted.data)
        self.assertFalse(staged_file.exists())
        with self.app.app_context():
            db = get_db()
            self.assertIsNone(
                db.execute(
                    "SELECT id FROM import_batches WHERE id = ?", (inactive_batch,)
                ).fetchone()
            )
            self.assertIsNotNone(
                db.execute(
                    "SELECT id FROM import_batches WHERE id = ?", (active_batch_id,)
                ).fetchone()
            )

    def test_undecided_standard_user_event_mutations_fail_closed(self):
        _, admin_password = self.initialize_admin()
        self.create_user("read-only-operator")
        with self.app.app_context():
            event_id = get_db().execute(
                "INSERT INTO events (name) VALUES ('Production Boundary Event')"
            ).lastrowid
            get_db().commit()
        self.app.config["STANDARD_USER_MUTATIONS_ALLOWED"] = False

        self.login("read-only-operator", "StrongPassword12!")
        overview = self.client.get("/events/{}".format(event_id))
        self.assertEqual(200, overview.status_code)
        self.assertNotIn(b"Manage Satellite Targets", overview.data)
        self.assertEqual(
            403,
            self.client.get("/events/{}/imports".format(event_id)).status_code,
        )
        self.assertEqual(
            403,
            self.client.get("/events/{}/data-quality".format(event_id)).status_code,
        )
        self.assertEqual(
            200,
            self.client.get("/events/{}/registrations".format(event_id)).status_code,
        )
        self.assertEqual(
            200,
            self.client.get("/events/{}/satellites".format(event_id)).status_code,
        )
        self.assertNotIn(b"Satellite administration", self.client.get(
            "/events/{}/satellites".format(event_id)
        ).data)
        self.assertEqual(
            403,
            self.client.get(
                "/satellites/settings", query_string={"event_id": event_id}
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.get(
                "/events/{}/admin-tables/registrants".format(event_id)
            ).status_code,
        )
        self.assertEqual(403, self.client.get("/admin/users").status_code)
        token = self.csrf("/events/{}".format(event_id))
        for path in (
            "/satellites/settings/sync/review",
            "/satellites/settings/sync/confirm",
        ):
            self.assertEqual(
                403,
                self.client.post(
                    path,
                    data={"csrf_token": token, "event_id": event_id},
                ).status_code,
            )
        denied = self.client.post(
            "/events/{}/settings".format(event_id),
            data={"csrf_token": token, "participant_target": "100"},
        )
        self.assertEqual(403, denied.status_code)
        self.assertEqual(
            403,
            self.client.post(
                "/events/{}/imports/validate".format(event_id),
                data={"csrf_token": token},
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.post(
                "/events/{}/satellite-datasets".format(event_id),
                data={
                    "csrf_token": token,
                    "name": "Denied Dataset",
                    "participant_target": "10",
                },
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.post(
                "/events/{}/satellite-target-categories/targets".format(event_id),
                data={
                    "csrf_token": token,
                    "target_outside_metro_manila": "10",
                    "target_within_metro_manila": "20",
                    "target_main": "30",
                },
            ).status_code,
        )
        self.logout()

        self.login("admin", admin_password)
        token = self.csrf("/events/{}".format(event_id))
        allowed = self.client.post(
            "/events/{}/settings".format(event_id),
            data={"csrf_token": token, "participant_target": "100"},
        )
        self.assertEqual(302, allowed.status_code)


if __name__ == "__main__":
    unittest.main()
