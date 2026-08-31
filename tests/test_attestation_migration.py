import sqlite3
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "c8f5d2b0e417"


class AttestationOwnershipMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "migration.sqlite3"
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
        # migrations/env.py intentionally honors the deployment DATABASE_URL.
        # This test owns an isolated SQLite URL and must not inherit a developer
        # or CI MySQL runtime URL from the surrounding process.
        with mock.patch.dict("os.environ", {"DATABASE_URL": ""}):
            return operation(self.config, *args)

    def test_upgrade_backfills_and_consolidates_latest_review_state(self):
        self._alembic(command.upgrade, PREVIOUS_REVISION)
        with self._connection() as db:
            event_id = db.execute(
                "INSERT INTO events (name) VALUES ('Migration Event')"
            ).lastrowid
            old_batch_id = db.execute(
                """
                INSERT INTO import_batches (event_id, status)
                VALUES (?, 'inactive')
                """,
                (event_id,),
            ).lastrowid
            active_batch_id = db.execute(
                """
                INSERT INTO import_batches (
                    event_id, status, active_event_id, processed_at, activated_at
                ) VALUES (?, 'active', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (event_id, event_id),
            ).lastrowid
            old_registrant_id = db.execute(
                """
                INSERT INTO registrants (
                    batch_id, source_id, registration_code, ticket_code,
                    affiliation, registration_type
                ) VALUES (?, 'PERSON-1', 'R-1', 'T-1', 'CCF Main', 'participant')
                """,
                (old_batch_id,),
            ).lastrowid
            active_registrant_id = db.execute(
                """
                INSERT INTO registrants (
                    batch_id, source_id, registration_code, ticket_code,
                    affiliation, registration_type
                ) VALUES (?, 'PERSON-1', 'R-1', 'T-1', 'CCF Main', 'participant')
                """,
                (active_batch_id,),
            ).lastrowid
            db.execute(
                """
                INSERT INTO attestation_verifications (
                    registrant_id, status, created_at, updated_at
                ) VALUES (?, 'verified', '2026-08-01 09:00:00', '2026-08-01 10:00:00')
                """,
                (old_registrant_id,),
            )
            winner_id = db.execute(
                """
                INSERT INTO attestation_verifications (
                    registrant_id, status, created_at, updated_at
                ) VALUES (?, 'invalid', '2026-08-02 09:00:00', '2026-08-02 10:00:00')
                """,
                (active_registrant_id,),
            ).lastrowid
            db.commit()

        self._alembic(command.upgrade, "head")
        self._alembic(command.check)
        with self._connection() as db:
            self.assertEqual(
                1, db.execute("SELECT COUNT(*) FROM attestation_participants").fetchone()[0]
            )
            self.assertEqual(
                2,
                db.execute(
                    "SELECT COUNT(*) FROM attestation_participant_registrants"
                ).fetchone()[0],
            )
            verification = db.execute(
                "SELECT * FROM attestation_verifications"
            ).fetchone()
            self.assertEqual(winner_id, verification["id"])
            self.assertEqual(event_id, verification["event_id"])
            self.assertEqual(active_registrant_id, verification["registrant_id"])
            self.assertEqual("invalid", verification["status"])
            self.assertEqual("2026-08-02 09:00:00", verification["created_at"])
            self.assertEqual("2026-08-02 10:00:00", verification["updated_at"])

        self._alembic(command.downgrade, PREVIOUS_REVISION)
        with self._connection() as db:
            columns = {
                row[1]
                for row in db.execute(
                    "PRAGMA table_info(attestation_verifications)"
                ).fetchall()
            }
            self.assertNotIn("event_id", columns)
            verification = db.execute(
                "SELECT registrant_id, status FROM attestation_verifications"
            ).fetchone()
            self.assertEqual(active_registrant_id, verification["registrant_id"])
            self.assertEqual("invalid", verification["status"])


if __name__ == "__main__":
    unittest.main()
