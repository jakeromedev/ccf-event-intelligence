import logging
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "f7c2a8d5e913"


class RegistrantSatelliteAssignmentMigrationTests(unittest.TestCase):
    def setUp(self):
        self.app_logger_was_disabled = logging.getLogger("app").disabled
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "registrant-satellites.sqlite3"
        self.config = Config(str(ROOT / "alembic.ini"))
        self.config.set_main_option("script_location", str(ROOT / "migrations"))
        self.config.set_main_option(
            "sqlalchemy.url", "sqlite+pysqlite:///{}".format(self.database_path)
        )

    def tearDown(self):
        logging.getLogger("app").disabled = self.app_logger_was_disabled
        self.temp.cleanup()

    def _connection(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _alembic(self, operation, *args):
        with mock.patch.dict("os.environ", {"DATABASE_URL": ""}):
            return operation(self.config, *args)

    def test_manual_assignment_constraints_and_batch_independence(self):
        self._alembic(command.upgrade, PREVIOUS_REVISION)
        self._alembic(command.upgrade, "head")
        self._alembic(command.check)

        with self._connection() as db:
            event_id = db.execute(
                "INSERT INTO events (name) VALUES ('Manual Assignment Event')"
            ).lastrowid
            other_event_id = db.execute(
                "INSERT INTO events (name) VALUES ('Other Event')"
            ).lastrowid
            batch_id = db.execute(
                """
                INSERT INTO import_batches (event_id, status)
                VALUES (?, 'inactive')
                """,
                (event_id,),
            ).lastrowid
            participant_id = db.execute(
                "INSERT INTO attestation_participants (event_id) VALUES (?)",
                (event_id,),
            ).lastrowid
            other_participant_id = db.execute(
                "INSERT INTO attestation_participants (event_id) VALUES (?)",
                (other_event_id,),
            ).lastrowid
            directory_id = db.execute(
                """
                INSERT INTO satellite_directory (name, normalized_name)
                VALUES ('B1G Davao', 'b1g davao')
                """
            ).lastrowid
            db.execute(
                """
                INSERT INTO event_registrant_satellites (
                    event_id, attestation_participant_id, directory_id,
                    assignment_source
                ) VALUES (?, ?, ?, 'manual')
                """,
                (event_id, participant_id, directory_id),
            )
            db.execute(
                """
                INSERT INTO event_registrant_satellite_audits (
                    event_id, attestation_participant_id, action,
                    new_directory_id, new_directory_name
                ) VALUES (?, ?, 'manual', ?, 'B1G Davao')
                """,
                (event_id, participant_id, directory_id),
            )
            db.commit()

            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_registrant_satellites (
                        event_id, attestation_participant_id, directory_id,
                        assignment_source
                    ) VALUES (?, ?, ?, 'manual')
                    """,
                    (event_id, participant_id, directory_id),
                )
            db.rollback()

            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_registrant_satellites (
                        event_id, attestation_participant_id, directory_id,
                        assignment_source, source_batch_id
                    ) VALUES (?, ?, ?, 'manual', ?)
                    """,
                    (other_event_id, other_participant_id, directory_id, batch_id),
                )
            db.rollback()

            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_registrant_satellites (
                        event_id, attestation_participant_id, directory_id,
                        assignment_source
                    ) VALUES (?, ?, ?, 'automatic')
                    """,
                    (other_event_id, other_participant_id, directory_id),
                )
            db.rollback()

            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_registrant_satellites (
                        event_id, attestation_participant_id, directory_id,
                        assignment_source
                    ) VALUES (?, ?, ?, 'manual')
                    """,
                    (event_id, other_participant_id, directory_id),
                )
            db.rollback()

            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_registrant_satellites (
                        event_id, attestation_participant_id, directory_id,
                        assignment_source
                    ) VALUES (?, ?, ?, 'manual')
                    """,
                    (other_event_id, other_participant_id, directory_id + 999),
                )
            db.rollback()

            db.execute("DELETE FROM import_batches WHERE id = ?", (batch_id,))
            db.commit()
            assignment = db.execute(
                """
                SELECT event_id, attestation_participant_id, directory_id,
                       assignment_source, source_batch_id
                FROM event_registrant_satellites
                """
            ).fetchone()
            self.assertEqual(event_id, assignment["event_id"])
            self.assertEqual(participant_id, assignment["attestation_participant_id"])
            self.assertEqual(directory_id, assignment["directory_id"])
            self.assertEqual("manual", assignment["assignment_source"])
            self.assertIsNone(assignment["source_batch_id"])
            audit = db.execute(
                """
                SELECT action, new_directory_id, new_directory_name
                FROM event_registrant_satellite_audits
                """
            ).fetchone()
            self.assertEqual("manual", audit["action"])
            self.assertEqual(directory_id, audit["new_directory_id"])
            self.assertEqual("B1G Davao", audit["new_directory_name"])

        self._alembic(command.downgrade, PREVIOUS_REVISION)
        with self._connection() as db:
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertNotIn("event_registrant_satellites", tables)
            self.assertNotIn("event_registrant_satellite_audits", tables)


if __name__ == "__main__":
    unittest.main()
