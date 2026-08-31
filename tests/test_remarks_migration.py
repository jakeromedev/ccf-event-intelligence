import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "f3a8c2d9e401"


class RegistrantRemarksMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "remarks-migration.sqlite3"
        self.config = Config(str(ROOT / "alembic.ini"))
        self.config.set_main_option("script_location", str(ROOT / "migrations"))
        self.config.set_main_option(
            "sqlalchemy.url", "sqlite+pysqlite:///{}".format(self.database_path)
        )

    def tearDown(self):
        self.temp.cleanup()

    def _connection(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _alembic(self, operation, *args):
        with mock.patch.dict("os.environ", {"DATABASE_URL": ""}):
            return operation(self.config, *args)

    def test_upgrade_constraints_attribution_and_downgrade(self):
        self._alembic(command.upgrade, PREVIOUS_REVISION)
        with self._connection() as db:
            user_id = db.execute(
                """
                INSERT INTO users (
                    username, password_hash, role, status, approved_at
                ) VALUES ('remark-author', 'unused', 'registration', 'approved',
                          CURRENT_TIMESTAMP)
                """
            ).lastrowid
            event_id = db.execute(
                "INSERT INTO events (name) VALUES ('Remarks Migration Event')"
            ).lastrowid
            participant_id = db.execute(
                "INSERT INTO attestation_participants (event_id) VALUES (?)",
                (event_id,),
            ).lastrowid
            db.commit()

        self._alembic(command.upgrade, "head")
        self._alembic(command.check)
        with self._connection() as db:
            remark_id = db.execute(
                """
                INSERT INTO registrant_remarks (
                    event_id, attestation_participant_id, remark,
                    created_by_user_id
                ) VALUES (?, ?, 'Migration remark', ?)
                """,
                (event_id, participant_id, user_id),
            ).lastrowid
            db.commit()
            remark = db.execute(
                "SELECT * FROM registrant_remarks WHERE id = ?", (remark_id,)
            ).fetchone()
            self.assertEqual("pending", remark["status"])
            self.assertIsNone(remark["resolved_at"])

            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "UPDATE registrant_remarks SET status = 'invalid' WHERE id = ?",
                    (remark_id,),
                )
            db.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "UPDATE registrant_remarks SET status = 'resolved' WHERE id = ?",
                    (remark_id,),
                )
            db.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "UPDATE registrant_remarks SET resolved_at = CURRENT_TIMESTAMP "
                    "WHERE id = ?",
                    (remark_id,),
                )
            db.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO registrant_remarks (
                        event_id, attestation_participant_id, remark
                    ) VALUES (?, ?, 'Cross-event owner')
                    """,
                    (event_id + 1, participant_id),
                )
            db.rollback()

            db.execute(
                """
                UPDATE registrant_remarks
                SET status = 'resolved', resolved_by_user_id = ?,
                    resolved_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (user_id, remark_id),
            )
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            db.commit()
            retained = db.execute(
                """
                SELECT remark, status, created_by_user_id,
                       resolved_by_user_id, resolved_at
                FROM registrant_remarks
                """
            ).fetchone()
            self.assertEqual("Migration remark", retained["remark"])
            self.assertEqual("resolved", retained["status"])
            self.assertIsNone(retained["created_by_user_id"])
            self.assertIsNone(retained["resolved_by_user_id"])
            self.assertIsNotNone(retained["resolved_at"])

            db.execute("DELETE FROM events WHERE id = ?", (event_id,))
            db.commit()
            self.assertEqual(
                0, db.execute("SELECT COUNT(*) FROM registrant_remarks").fetchone()[0]
            )

        self._alembic(command.downgrade, PREVIOUS_REVISION)
        with self._connection() as db:
            self.assertIsNone(
                db.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'registrant_remarks'"
                ).fetchone()
            )


if __name__ == "__main__":
    unittest.main()
