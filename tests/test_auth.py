import os
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import event as sqlalchemy_event, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app import create_app
from app.db import get_db, get_engine
from app.models import Base, User


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
        self.assertNotIn(b">Delete</button>", normal_page.data)
        token = self.csrf(imports_path)
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


if __name__ == "__main__":
    unittest.main()
