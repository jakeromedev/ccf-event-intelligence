import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config


class FailedPaymentFollowupMigrationTests(unittest.TestCase):
    def test_upgrade_repeat_history_and_downgrade_preserve_existing_data(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DATABASE_URL": ""}):
            path = Path(directory) / "migration.sqlite3"
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
            command.upgrade(config, "c6e2a9b4d801")
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO events (id, name) VALUES (1, 'Event')")
            command.upgrade(config, "d8a3f6c1e902")
            with sqlite3.connect(path) as db:
                for kind in ("outreach", "outreach", "remark"):
                    db.execute("INSERT INTO failed_payment_followups (event_id, person_key, kind, remark) "
                               "VALUES (1, 'person', ?, 'A note')", (kind,))
                self.assertEqual(3, db.execute("SELECT COUNT(*) FROM failed_payment_followups WHERE created_at IS NOT NULL").fetchone()[0])
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("INSERT INTO failed_payment_followups (event_id, person_key, kind) VALUES (1, 'person', 'invalid')")
            command.downgrade(config, "c6e2a9b4d801")
            with sqlite3.connect(path) as db:
                self.assertEqual("Event", db.execute("SELECT name FROM events WHERE id = 1").fetchone()[0])
