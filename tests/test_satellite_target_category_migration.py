import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "b8d3e6f1a924"


class SatelliteTargetCategoryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "satellite-target-categories.sqlite3"
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

    def _add_directory(self, db, hub_id, name):
        return db.execute(
            """
            INSERT INTO satellite_directory (hub_id, name, normalized_name)
            VALUES (?, ?, ?)
            """,
            (hub_id, name, name.lower()),
        ).lastrowid

    def _add_satellite(self, db, event_id, batch_id, directory_id, name):
        return db.execute(
            """
            INSERT INTO satellites (
                event_id, batch_id, directory_id, name, normalized_name,
                affiliation, source_record_count
            ) VALUES (?, ?, ?, ?, ?, 'Local Satellite', 1)
            """,
            (event_id, batch_id, directory_id, name, name.lower()),
        ).lastrowid

    def _add_dataset(self, db, event_id, name, target, batch_id, satellite_ids):
        dataset_id = db.execute(
            """
            INSERT INTO satellite_datasets (event_id, name, participant_target)
            VALUES (?, ?, ?)
            """,
            (event_id, name, target),
        ).lastrowid
        db.executemany(
            """
            INSERT INTO satellite_dataset_satellites (
                event_id, satellite_dataset_id, satellite_batch_id, satellite_id
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (event_id, dataset_id, batch_id, satellite_id)
                for satellite_id in satellite_ids
            ],
        )
        return dataset_id

    def test_fixed_categories_constraints_and_explicit_legacy_migration(self):
        self._alembic(command.upgrade, PREVIOUS_REVISION)
        with self._connection() as db:
            event_a = db.execute("INSERT INTO events (name) VALUES ('Event A')").lastrowid
            event_b = db.execute("INSERT INTO events (name) VALUES ('Event B')").lastrowid
            batch_id = db.execute(
                "INSERT INTO import_batches (event_id, status) VALUES (?, 'inactive')",
                (event_a,),
            ).lastrowid
            outside_hub = db.execute(
                """
                INSERT INTO satellite_hubs (hub_group_id, name, normalized_name)
                VALUES (2, 'Outside Hub', 'outside hub')
                """
            ).lastrowid
            main_hub = db.execute(
                """
                INSERT INTO satellite_hubs (hub_group_id, name, normalized_name)
                VALUES (1, 'Main Hub', 'main hub')
                """
            ).lastrowid
            outside_directory = self._add_directory(
                db, outside_hub, "B1G Singapore"
            )
            main_directory = self._add_directory(db, main_hub, "B1G Main")
            arbitrary_directory = self._add_directory(db, main_hub, "B1G East")
            overlap_directory = self._add_directory(db, main_hub, "B1G Shared")
            outside_satellite = self._add_satellite(
                db, event_a, batch_id, outside_directory, "B1G Singapore"
            )
            main_satellite = self._add_satellite(
                db, event_a, batch_id, main_directory, "B1G Main"
            )
            arbitrary_satellite = self._add_satellite(
                db, event_a, batch_id, arbitrary_directory, "B1G East"
            )
            overlap_satellite = self._add_satellite(
                db, event_a, batch_id, overlap_directory, "B1G Shared"
            )
            self._add_dataset(
                db,
                event_a,
                "Outside Metro Manila Hubs",
                500,
                batch_id,
                (outside_satellite, overlap_satellite),
            )
            self._add_dataset(
                db,
                event_a,
                "Main",
                1_000,
                batch_id,
                (main_satellite, overlap_satellite),
            )
            self._add_dataset(
                db, event_a, "GGMA", 250, batch_id, (arbitrary_satellite,)
            )
            db.commit()

        self._alembic(command.upgrade, "head")
        self._alembic(command.check)
        with self._connection() as db:
            categories = db.execute(
                """
                SELECT event_id, category_key, participant_target
                FROM event_satellite_target_categories
                ORDER BY event_id, category_key
                """
            ).fetchall()
            self.assertEqual(6, len(categories))
            targets = {
                (row["event_id"], row["category_key"]): row["participant_target"]
                for row in categories
            }
            self.assertEqual(500, targets[(event_a, "outside_metro_manila")])
            self.assertEqual(1_000, targets[(event_a, "main")])
            self.assertEqual(0, targets[(event_a, "within_metro_manila")])
            self.assertEqual(0, targets[(event_b, "main")])

            groups = db.execute(
                """
                SELECT report.event_id, report.id target_group_id,
                       report.participant_target,
                       report.sort_order, member.category_key
                FROM event_satellite_target_groups report
                JOIN event_satellite_target_group_categories member
                  ON member.target_group_id = report.id
                 AND member.event_id = report.event_id
                ORDER BY report.event_id, report.sort_order
                """
            ).fetchall()
            self.assertEqual(6, len(groups))
            event_a_groups = [row for row in groups if row["event_id"] == event_a]
            self.assertEqual(
                ["outside_metro_manila", "within_metro_manila", "main"],
                [row["category_key"] for row in event_a_groups],
            )
            self.assertEqual(
                [500, 0, 1_000],
                [row["participant_target"] for row in event_a_groups],
            )

            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_satellite_target_group_categories (
                        event_id, target_group_id, category_key
                    ) VALUES (?, ?, 'outside_metro_manila')
                    """,
                    (event_a, event_a_groups[1]["target_group_id"]),
                )
            db.rollback()

            memberships = db.execute(
                """
                SELECT category_key, directory_id
                FROM event_satellite_target_satellites
                WHERE event_id = ?
                ORDER BY category_key, directory_id
                """,
                (event_a,),
            ).fetchall()
            self.assertEqual(
                [("main", main_directory), ("outside_metro_manila", outside_directory)],
                [(row["category_key"], row["directory_id"]) for row in memberships],
            )
            self.assertNotIn(
                overlap_directory, [row["directory_id"] for row in memberships]
            )
            self.assertNotIn(
                arbitrary_directory, [row["directory_id"] for row in memberships]
            )

            # Membership is canonical and survives removal of imported evidence.
            db.execute("DELETE FROM satellites WHERE id = ?", (outside_satellite,))
            self.assertIsNotNone(
                db.execute(
                    """
                    SELECT id FROM event_satellite_target_satellites
                    WHERE event_id = ? AND directory_id = ?
                    """,
                    (event_a, outside_directory),
                ).fetchone()
            )

            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_satellite_target_categories (
                        event_id, category_key, participant_target
                    ) VALUES (?, 'invalid', 1)
                    """,
                    (event_a,),
                )
            db.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_satellite_target_satellites (
                        event_id, category_key, directory_id
                    ) VALUES (?, 'within_metro_manila', ?)
                    """,
                    (event_a, main_directory),
                )
            db.rollback()

            db.execute(
                """
                INSERT INTO event_satellite_target_satellites (
                    event_id, category_key, directory_id
                ) VALUES (?, 'main', ?)
                """,
                (event_b, main_directory),
            )
            db.execute("DELETE FROM events WHERE id = ?", (event_b,))
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM event_satellite_target_categories WHERE event_id = ?",
                    (event_b,),
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM event_satellite_target_satellites WHERE event_id = ?",
                    (event_b,),
                ).fetchone()[0],
            )

        self._alembic(command.downgrade, PREVIOUS_REVISION)
        with self._connection() as db:
            self.assertIsNone(
                db.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table'
                      AND name = 'event_satellite_target_groups'
                    """
                ).fetchone()
            )
            self.assertIsNone(
                db.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table'
                      AND name = 'event_satellite_target_categories'
                    """
                ).fetchone()
            )
            self.assertEqual(
                3, db.execute("SELECT COUNT(*) FROM satellite_datasets").fetchone()[0]
            )


if __name__ == "__main__":
    unittest.main()
