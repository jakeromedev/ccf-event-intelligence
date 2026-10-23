import sqlite3
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.models import Base


class TransportationMigrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("MYSQL_TEST_DATABASE_URL"), "Dedicated MySQL test database not configured")
    def test_mysql_upgrade_matches_models_and_downgrades_cleanly(self):
        url = os.environ["MYSQL_TEST_DATABASE_URL"]
        self.assertIn("test", (make_url(url).database or "").lower())
        engine = create_engine(url)
        self.addCleanup(engine.dispose)
        # The existing test suite uses this explicitly disposable database.
        Base.metadata.drop_all(engine)
        with engine.begin() as db:
            db.execute(text("DROP TABLE IF EXISTS alembic_version"))
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with patch.dict("os.environ", {"DATABASE_URL": url}):
            command.upgrade(config, "e9b4d7a2f603")
            with engine.begin() as db:
                db.execute(text("INSERT INTO events (id, name) VALUES (1, 'Existing')"))
                db.execute(text("INSERT INTO attestation_participants (id, event_id) VALUES (1, 1)"))
            command.upgrade(config, "f2c5e8a1b704")
            command.check(config)
            with engine.begin() as db:
                db.execute(text("""INSERT INTO participant_transportation
                    (event_id, attestation_participant_id, direction, mode, revision)
                    VALUES (1, 1, 'to_mmrc', 'bus', 1)"""))
            command.downgrade(config, "e9b4d7a2f603")
            self.assertNotIn("participant_transportation", inspect(engine).get_table_names())
            with engine.connect() as db:
                self.assertEqual("Existing", db.execute(text("SELECT name FROM events WHERE id = 1")).scalar_one())

    def test_upgrade_constraints_metadata_and_downgrade_preserve_existing_data(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DATABASE_URL": ""}):
            path = Path(directory) / "migration.sqlite3"
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
            command.upgrade(config, "e9b4d7a2f603")
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO events (id, name) VALUES (1, 'Existing'), (2, 'Other')")
                db.execute("INSERT INTO attestation_participants (id, event_id) VALUES (1, 1)")
                db.execute("INSERT INTO import_batches (id, event_id, status, active_event_id) VALUES (1, 1, 'active', 1)")
            command.upgrade(config, "f2c5e8a1b704")
            command.check(config)
            with sqlite3.connect(path) as db:
                db.execute("PRAGMA foreign_keys = ON")
                statement = """INSERT INTO participant_transportation
                    (event_id, attestation_participant_id, direction, mode, revision)
                    VALUES (?, 1, ?, ?, ?)"""
                db.execute(statement, (1, "to_mmrc", "bus", 1))
                for args in [(1, "to_mmrc", "carpool", 1), (2, "from_mmrc", "bus", 1),
                             (1, "invalid", "bus", 1), (1, "from_mmrc", "taxi", 1),
                             (1, "from_mmrc", "bus", 0)]:
                    with self.subTest(args=args), self.assertRaises(sqlite3.IntegrityError):
                        db.execute(statement, args)
                db.execute(statement, (1, "from_mmrc", None, 1))
                self.assertEqual(("active", 1), db.execute("SELECT status, active_event_id FROM import_batches WHERE id = 1").fetchone())
            command.downgrade(config, "e9b4d7a2f603")
            with sqlite3.connect(path) as db:
                self.assertEqual(("Existing",), db.execute("SELECT name FROM events WHERE id = 1").fetchone())
                self.assertEqual((1,), db.execute("SELECT event_id FROM attestation_participants WHERE id = 1").fetchone())
                self.assertEqual(("active", 1), db.execute("SELECT status, active_event_id FROM import_batches WHERE id = 1").fetchone())
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name = 'participant_transportation'").fetchone())
