import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "e6b1d9a4c702"


class SatelliteSettingsPhase2MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "satellite-settings-phase2.sqlite3"
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

    def test_hub_scoped_uniqueness_and_safe_downgrade(self):
        self._alembic(command.upgrade, PREVIOUS_REVISION)
        self._alembic(command.upgrade, "head")
        self._alembic(command.check)
        with self._connection() as db:
            within_hub = db.execute(
                """
                INSERT INTO satellite_hubs (
                    hub_group_id, name, normalized_name
                ) VALUES (1, 'East Metro', 'east metro')
                """
            ).lastrowid
            outside_hub = db.execute(
                """
                INSERT INTO satellite_hubs (
                    hub_group_id, name, normalized_name
                ) VALUES (2, 'CALABARZON', 'calabarzon')
                """
            ).lastrowid
            first_id = db.execute(
                """
                INSERT INTO satellite_directory (hub_id, name, normalized_name)
                VALUES (?, 'B1G Antipolo', 'b1g antipolo')
                """,
                (within_hub,),
            ).lastrowid
            second_id = db.execute(
                """
                INSERT INTO satellite_directory (hub_id, name, normalized_name)
                VALUES (?, 'B1G Antipolo', 'b1g antipolo')
                """,
                (outside_hub,),
            ).lastrowid
            self.assertNotEqual(first_id, second_id)
            db.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO satellite_directory (hub_id, name, normalized_name)
                    VALUES (?, 'b1g antipolo', 'b1g antipolo')
                    """,
                    (within_hub,),
                )
            db.rollback()

        self._alembic(command.downgrade, PREVIOUS_REVISION)
        with self._connection() as db:
            self.assertEqual(
                1,
                db.execute(
                    "SELECT COUNT(*) FROM satellite_directory "
                    "WHERE normalized_name = 'b1g antipolo'"
                ).fetchone()[0],
            )


if __name__ == "__main__":
    unittest.main()
