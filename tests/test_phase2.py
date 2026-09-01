import io
import json
import logging
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from flask import Flask, request

from app import create_app
from app.config import ApplicationConfigurationError, configure_app
from app.db import _expected_schema_heads, get_db
from app.models import Base
from app.observability import JsonLogFormatter
from app.db import get_engine
from app.time_utils import as_manila_time, format_operational_datetime, utc_now


class ProductionConfigurationTests(unittest.TestCase):
    def test_production_requires_a_non_placeholder_secret(self):
        app = Flask(__name__)
        with patch.dict(
            "os.environ",
            {
                "CCF_ENV": "production",
                "CCF_DASHBOARD_SECRET": "change-me",
                "DATABASE_URL": "mysql+pymysql://user:password@db/ccf_events",
            },
            clear=True,
        ):
            with self.assertRaises(ApplicationConfigurationError):
                configure_app(app)

    def test_production_defaults_are_secure_and_fail_closed(self):
        app = Flask(__name__)
        with patch.dict(
            "os.environ",
            {
                "CCF_ENV": "production",
                "CCF_DASHBOARD_SECRET": "a-valid-production-secret-with-more-than-32-characters",
                "DATABASE_URL": "mysql+pymysql://user:password@db/ccf_events",
                "CCF_TRUSTED_HOSTS": "dashboard.example.test",
            },
            clear=True,
        ):
            configure_app(app)
        self.assertFalse(app.config["DEBUG"])
        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])
        self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual("Lax", app.config["SESSION_COOKIE_SAMESITE"])
        self.assertTrue(app.config["REQUIRE_SCHEMA_CURRENT"])
        self.assertFalse(app.config["STANDARD_USER_MUTATIONS_ALLOWED"])
        self.assertEqual("Asia/Manila", app.config["DISPLAY_TIMEZONE"])

    def test_production_refuses_disabled_csrf_or_schema_validation(self):
        for override in ({"WTF_CSRF_ENABLED": False}, {"REQUIRE_SCHEMA_CURRENT": False}):
            with self.subTest(override=override):
                app = Flask(__name__)
                environment = {
                    "CCF_ENV": "production",
                    "CCF_DASHBOARD_SECRET": "a-valid-production-secret-with-more-than-32-characters",
                    "DATABASE_URL": "mysql+pymysql://user:password@db/ccf_events",
                    "CCF_TRUSTED_HOSTS": "dashboard.example.test",
                }
                with patch.dict("os.environ", environment, clear=True):
                    with self.assertRaises(ApplicationConfigurationError):
                        configure_app(app, override)

    def test_production_requires_trusted_hosts(self):
        app = Flask(__name__)
        with patch.dict(
            "os.environ",
            {
                "CCF_ENV": "production",
                "CCF_DASHBOARD_SECRET": "a-valid-production-secret-with-more-than-32-characters",
                "DATABASE_URL": "mysql+pymysql://user:password@db/ccf_events",
            },
            clear=True,
        ):
            with self.assertRaises(ApplicationConfigurationError):
                configure_app(app)


class OperationalTimezoneTests(unittest.TestCase):
    def test_naive_utc_timestamp_is_displayed_in_manila(self):
        self.assertEqual(
            "Sep 1, 2026 · 5:37 PM PHT",
            format_operational_datetime("2026-09-01 09:37:50"),
        )

    def test_aware_timestamp_is_converted_to_manila(self):
        converted = as_manila_time(datetime(2026, 9, 1, 9, 37, tzinfo=timezone.utc))
        self.assertEqual("2026-09-01T17:37:00+08:00", converted.isoformat())

    def test_utc_now_matches_naive_database_contract(self):
        current = utc_now()
        self.assertIsNone(current.tzinfo)
        elapsed = datetime.now(timezone.utc).replace(tzinfo=None) - current
        self.assertLess(abs(elapsed.total_seconds()), 2)


class OperationalEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE_URL": "sqlite+pysqlite:///{}".format(root / "phase2.sqlite3"),
                "STAGING_DIR": str(root / "staging"),
                "AUTHENTICATION_DISABLED": False,
                "WTF_CSRF_ENABLED": True,
            }
        )
        with self.app.app_context():
            Base.metadata.create_all(get_engine())
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            get_engine().dispose()
        self.temp.cleanup()

    def test_health_endpoints_are_public_minimal_and_machine_readable(self):
        live = self.client.get("/health/live")
        self.assertEqual(200, live.status_code)
        self.assertEqual({"status": "ok"}, live.get_json())
        with patch("app.operations.check_database_readiness", return_value=(True, "ready")):
            ready = self.client.get("/health/ready")
        self.assertEqual(200, ready.status_code)
        self.assertEqual({"status": "ready"}, ready.get_json())
        self.assertIn("X-Request-ID", ready.headers)

    def test_readiness_dependency_failure_is_503_without_details(self):
        with patch(
            "app.operations.check_database_readiness",
            return_value=(False, "database_unavailable"),
        ):
            response = self.client.get("/health/ready")
        self.assertEqual(503, response.status_code)
        self.assertEqual({"status": "unavailable"}, response.get_json())
        self.assertNotIn(b"database", response.data)

    def test_forwarded_protocol_is_ignored_unless_proxy_hops_are_configured(self):
        self.app.config["AUTHENTICATION_DISABLED"] = True

        @self.app.get("/_test/scheme")
        def scheme():
            return {"scheme": request.scheme}

        response = self.client.get(
            "/_test/scheme", headers={"X-Forwarded-Proto": "https"}
        )
        self.assertEqual("http", response.get_json()["scheme"])

    def test_explicit_proxy_hop_uses_forwarded_protocol(self):
        root = Path(self.temp.name)
        proxy_app = create_app(
            {
                "TESTING": True,
                "DATABASE_URL": "sqlite+pysqlite:///{}".format(root / "proxy.sqlite3"),
                "STAGING_DIR": str(root / "proxy-staging"),
                "AUTHENTICATION_DISABLED": True,
                "WTF_CSRF_ENABLED": False,
                "PROXY_HOPS": {
                    "x_for": 0,
                    "x_proto": 1,
                    "x_host": 0,
                    "x_port": 0,
                    "x_prefix": 0,
                },
            }
        )

        @proxy_app.get("/_test/scheme")
        def scheme():
            return {"scheme": request.scheme}

        response = proxy_app.test_client().get(
            "/_test/scheme", headers={"X-Forwarded-Proto": "https"}
        )
        self.assertEqual("https", response.get_json()["scheme"])
        with proxy_app.app_context():
            get_engine().dispose()

    def test_startup_schema_check_accepts_head_and_rejects_mismatch(self):
        root = Path(self.temp.name)
        database_url = "sqlite+pysqlite:///{}".format(root / "schema-check.sqlite3")
        bootstrap = create_app(
            {
                "TESTING": True,
                "DATABASE_URL": database_url,
                "STAGING_DIR": str(root / "schema-staging"),
            }
        )
        with bootstrap.app_context():
            engine = get_engine()
            Base.metadata.create_all(engine)
            head = next(iter(_expected_schema_heads()))
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO alembic_version (version_num) VALUES (?)", (head,)
                )
            engine.dispose()

        checked = create_app(
            {
                "TESTING": True,
                "DATABASE_URL": database_url,
                "STAGING_DIR": str(root / "schema-staging"),
                "REQUIRE_SCHEMA_CURRENT": True,
            }
        )
        with checked.app_context():
            get_engine().dispose()

        mismatch_url = "sqlite+pysqlite:///{}".format(root / "schema-mismatch.sqlite3")
        with self.assertRaises(ApplicationConfigurationError):
            create_app(
                {
                    "TESTING": True,
                    "DATABASE_URL": mismatch_url,
                    "STAGING_DIR": str(root / "schema-mismatch-staging"),
                    "REQUIRE_SCHEMA_CURRENT": True,
                }
            )

    def test_controlled_import_failure_emits_safe_signal_and_preserves_active_batch(self):
        self.app.config.update(
            AUTHENTICATION_DISABLED=True,
            WTF_CSRF_ENABLED=False,
            LOG_FORMAT="json",
        )
        with self.app.app_context():
            db = get_db()
            event_id = db.execute(
                "INSERT INTO events (name) VALUES ('Signal Exercise Event')"
            ).lastrowid
            active_id = db.execute(
                """
                INSERT INTO import_batches (
                    event_id, event_slug, event_name, status, active_event_id,
                    processed_at, activated_at
                ) VALUES (?, 'signal-active', 'Signal Exercise Event', 'active', ?,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (event_id, event_id),
            ).lastrowid
            candidate_id = db.execute(
                """
                INSERT INTO import_batches (event_id, event_slug, event_name, status)
                VALUES (?, 'signal-candidate', 'Signal Exercise Event', 'validated')
                """,
                (event_id,),
            ).lastrowid
            db.commit()

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonLogFormatter())
        previous_handlers = list(self.app.logger.handlers)
        self.app.logger.handlers = [handler]
        try:
            with patch(
                "app.routes.process_batch",
                side_effect=RuntimeError("raw-row-secret@example.test"),
            ):
                response = self.client.post(
                    "/events/{}/imports/{}/process".format(event_id, candidate_id)
                )
        finally:
            self.app.logger.handlers = previous_handlers

        self.assertEqual(302, response.status_code)
        with self.app.app_context():
            active = get_db().execute(
                "SELECT id FROM import_batches WHERE event_id = ? AND status = 'active'",
                (event_id,),
            ).fetchone()
            self.assertEqual(active_id, active["id"])
        entries = [json.loads(line) for line in stream.getvalue().splitlines()]
        failure = next(
            item for item in entries if item.get("event") == "import_processing_failed"
        )
        self.assertEqual(event_id, failure["event_id"])
        self.assertEqual(candidate_id, failure["batch_id"])
        self.assertEqual("RuntimeError", failure["error_type"])
        self.assertNotIn("raw-row-secret", stream.getvalue())


class StructuredLoggingTests(unittest.TestCase):
    def test_json_formatter_allowlist_excludes_sensitive_extra_fields(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonLogFormatter())
        logger = logging.getLogger("phase2-sensitive-log-test")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)
        logger.info(
            "authentication_failed",
            extra={
                "event": "authentication_failed",
                "reason": "invalid_credentials",
                "user_id": 7,
                "password": "NeverLogThis!",
                "email": "person@example.test",
                "csrf_token": "csrf-secret",
            },
        )
        payload = json.loads(stream.getvalue())
        self.assertEqual("authentication_failed", payload["event"])
        self.assertEqual(7, payload["user_id"])
        serialized = json.dumps(payload)
        self.assertNotIn("NeverLogThis", serialized)
        self.assertNotIn("person@example", serialized)
        self.assertNotIn("csrf-secret", serialized)


if __name__ == "__main__":
    unittest.main()
