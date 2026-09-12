import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config


class ImportOperatorMigrationTests(unittest.TestCase):
    def test_existing_batches_and_operator_snapshot_survive_upgrade(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DATABASE_URL": ""}):
            path = Path(directory) / "migration.sqlite3"
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
            command.upgrade(config, "d8a3f6c1e902")
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO events (id, name) VALUES (1, 'Event')")
                db.execute("INSERT INTO import_batches (id, event_id, status, active_event_id) VALUES (1, 1, 'active', 1)")
            command.upgrade(config, "e9b4d7a2f603")
            with sqlite3.connect(path) as db:
                db.execute("PRAGMA foreign_keys = ON")
                self.assertEqual(('active', 1, None, None), db.execute(
                    "SELECT status, active_event_id, imported_by_user_id, imported_by_username FROM import_batches WHERE id = 1"
                ).fetchone())
                db.execute("""INSERT INTO users (id, username, password_hash, role, status, approved_at)
                    VALUES (1, 'original-operator', 'test-hash', 'user', 'approved', CURRENT_TIMESTAMP)""")
                db.execute("UPDATE import_batches SET imported_by_user_id = 1, imported_by_username = 'original-operator' WHERE id = 1")
                db.execute("UPDATE users SET username = 'renamed-operator' WHERE id = 1")
                self.assertEqual('original-operator', db.execute(
                    "SELECT imported_by_username FROM import_batches WHERE id = 1"
                ).fetchone()[0])
                db.execute("DELETE FROM users WHERE id = 1")
                self.assertEqual((None, 'original-operator'), db.execute(
                    "SELECT imported_by_user_id, imported_by_username FROM import_batches WHERE id = 1"
                ).fetchone())
            command.downgrade(config, "d8a3f6c1e902")
            with sqlite3.connect(path) as db:
                self.assertEqual(('active', 1), db.execute(
                    "SELECT status, active_event_id FROM import_batches WHERE id = 1"
                ).fetchone())
