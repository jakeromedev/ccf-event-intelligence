import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "d5f8a1c2b304"


class SatelliteSettingsMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "satellite-settings.sqlite3"
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

    def test_upgrade_seeds_groups_and_preserves_existing_satellites(self):
        self._alembic(command.upgrade, PREVIOUS_REVISION)
        with self._connection() as db:
            event_id = db.execute(
                "INSERT INTO events (name) VALUES ('Satellite Settings Event')"
            ).lastrowid
            batch_id = db.execute(
                "INSERT INTO import_batches (event_id, status) VALUES (?, 'inactive')",
                (event_id,),
            ).lastrowid
            satellite_id = db.execute(
                """
                INSERT INTO satellites (
                    event_id, batch_id, name, normalized_name, affiliation,
                    source_record_count
                ) VALUES (?, ?, 'B1G Calamba', 'b1g calamba',
                          'Local Satellite', 4)
                """,
                (event_id, batch_id),
            ).lastrowid
            db.execute(
                """
                INSERT INTO satellite_source_variations (
                    event_id, batch_id, satellite_id, source_value,
                    normalized_source_value, affiliation, source_record_count
                ) VALUES (?, ?, ?, 'B1G Calamba', 'b1g calamba',
                          'Local Satellite', 4)
                """,
                (event_id, batch_id, satellite_id),
            )
            db.commit()

        self._alembic(command.upgrade, "head")
        self._alembic(command.check)
        with self._connection() as db:
            groups = db.execute(
                "SELECT code, name FROM hub_groups ORDER BY sort_order"
            ).fetchall()
            self.assertEqual(
                [
                    ("within_metro_manila", "Within Metro Manila Hubs"),
                    ("outside_metro_manila", "Outside Metro Manila Hubs"),
                ],
                [(row["code"], row["name"]) for row in groups],
            )
            preserved = db.execute(
                """
                SELECT satellite.id, satellite.name, satellite.normalized_name,
                       satellite.affiliation, satellite.source_record_count,
                       directory.name directory_name
                FROM satellites satellite
                JOIN satellite_directory directory
                  ON directory.id = satellite.directory_id
                WHERE satellite.id = ?
                """,
                (satellite_id,),
            ).fetchone()
            self.assertEqual("B1G Calamba", preserved["name"])
            self.assertEqual("b1g calamba", preserved["normalized_name"])
            self.assertEqual("Local Satellite", preserved["affiliation"])
            self.assertEqual(4, preserved["source_record_count"])
            self.assertEqual("B1G Calamba", preserved["directory_name"])
            self.assertEqual(
                1, db.execute("SELECT COUNT(*) FROM satellite_directory").fetchone()[0]
            )
            self.assertEqual(
                1,
                db.execute(
                    "SELECT COUNT(*) FROM satellite_source_variations "
                    "WHERE satellite_id = ?",
                    (satellite_id,),
                ).fetchone()[0],
            )

        self._alembic(command.downgrade, PREVIOUS_REVISION)
        with self._connection() as db:
            columns = {
                row[1] for row in db.execute("PRAGMA table_info(satellites)").fetchall()
            }
            self.assertNotIn("directory_id", columns)
            preserved = db.execute(
                "SELECT name, normalized_name FROM satellites WHERE id = ?",
                (satellite_id,),
            ).fetchone()
            self.assertEqual("B1G Calamba", preserved["name"])
            self.assertEqual(
                1,
                db.execute(
                    "SELECT COUNT(*) FROM satellite_source_variations "
                    "WHERE satellite_id = ?",
                    (satellite_id,),
                ).fetchone()[0],
            )
            self.assertIsNone(
                db.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'satellite_directory'"
                ).fetchone()
            )


if __name__ == "__main__":
    unittest.main()
