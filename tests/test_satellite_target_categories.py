import tempfile
import unittest
from pathlib import Path

from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.aggregation import event_dashboard_metrics
from app.db import get_db, get_engine
from app.models import Base
from app.satellite_target_categories import (
    SATELLITE_TARGET_CATEGORY_KEYS,
    ensure_event_satellite_target_categories,
    satellite_target_category_rows,
)


def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    dbapi_connection.execute("PRAGMA foreign_keys = ON")


class SatelliteTargetCategoryFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        database_path = Path(self.temp.name) / "categories.sqlite3"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "DATABASE_URL": "sqlite+pysqlite:///{}".format(database_path),
                "STAGING_DIR": str(Path(self.temp.name) / "staging"),
                "AUTHENTICATION_DISABLED": True,
                "WTF_CSRF_ENABLED": False,
            }
        )
        with self.app.app_context():
            engine = get_engine()
            sqlalchemy_event.listen(engine, "connect", enable_sqlite_foreign_keys)
            Base.metadata.create_all(engine)

    def tearDown(self):
        self.temp.cleanup()

    def test_event_creation_seeds_exactly_three_fixed_categories(self):
        response = self.app.test_client().post(
            "/events", data={"name": "Category Event"}
        )
        self.assertEqual(302, response.status_code)
        with self.app.app_context():
            db = get_db()
            event_id = db.execute(
                "SELECT id FROM events WHERE name = 'Category Event'"
            ).fetchone()["id"]
            categories = satellite_target_category_rows(db, event_id)
            self.assertEqual(
                list(SATELLITE_TARGET_CATEGORY_KEYS),
                [category["key"] for category in categories],
            )
            self.assertEqual([0, 0, 0], [row["participant_target"] for row in categories])
            self.assertEqual([0, 0, 0], [row["satellite_count"] for row in categories])

            ensure_event_satellite_target_categories(db, event_id)
            self.assertEqual(
                3,
                db.execute(
                    """
                    SELECT COUNT(*) FROM event_satellite_target_categories
                    WHERE event_id = ?
                    """,
                    (event_id,),
                ).fetchone()[0],
            )

    def test_dashboard_target_update_is_complete_validated_and_atomic(self):
        client = self.app.test_client()
        client.post("/events", data={"name": "Target Event"})
        with self.app.app_context():
            db = get_db()
            event_id = db.execute(
                "SELECT id FROM events WHERE name = 'Target Event'"
            ).fetchone()["id"]

        valid = client.post(
            "/events/{}/satellite-target-categories/targets".format(event_id),
            data={
                "target_outside_metro_manila": "500",
                "target_within_metro_manila": "0",
                "target_main": "1000",
            },
            follow_redirects=True,
        )
        self.assertEqual(200, valid.status_code)
        self.assertIn(b"Dashboard Satellite Targets saved", valid.data)
        with self.app.app_context():
            dashboard = event_dashboard_metrics(get_db(), event_id)
        categories = dashboard["satellite_target_categories"]
        self.assertEqual(list(SATELLITE_TARGET_CATEGORY_KEYS), [row["key"] for row in categories])
        self.assertEqual([500, 0, 1000], [row["participant_target"] for row in categories])
        self.assertEqual([0, 0, 0], [row["actual_participants"] for row in categories])
        self.assertEqual(0, categories[0]["progress_percentage"])
        self.assertFalse(categories[1]["target_configured"])
        self.assertIsNone(categories[1]["progress_percentage"])

        invalid_submissions = (
            {
                "target_outside_metro_manila": "501",
                "target_within_metro_manila": "1.5",
                "target_main": "1001",
            },
            {
                "target_outside_metro_manila": "501",
                "target_within_metro_manila": "-1",
                "target_main": "1001",
            },
            {
                "target_outside_metro_manila": "501",
                "target_within_metro_manila": "1",
                "target_main": "1000000001",
            },
            {
                "target_outside_metro_manila": "501",
                "target_within_metro_manila": "1",
            },
        )
        for submission in invalid_submissions:
            response = client.post(
                "/events/{}/satellite-target-categories/targets".format(event_id),
                data=submission,
                follow_redirects=True,
            )
            self.assertEqual(200, response.status_code)
            self.assertIn(b"No changes were made", response.data)
            with self.app.app_context():
                rows = satellite_target_category_rows(get_db(), event_id)
                self.assertEqual(
                    [500, 0, 1000],
                    [row["participant_target"] for row in rows],
                )

        page = client.get("/events/{}".format(event_id))
        self.assertEqual(1, page.data.count(b'name="target_outside_metro_manila"'))
        self.assertEqual(1, page.data.count(b'name="target_within_metro_manila"'))
        self.assertEqual(1, page.data.count(b'name="target_main"'))
        self.assertNotIn(b"satellite-dataset-modal", page.data)

    def test_database_enforces_targets_membership_exclusivity_and_cascades(self):
        with self.app.app_context():
            db = get_db()
            event_id = db.execute(
                "INSERT INTO events (name) VALUES ('Constraint Event')"
            ).lastrowid
            ensure_event_satellite_target_categories(db, event_id)
            db.execute(
                """
                INSERT INTO hub_groups (code, name, sort_order)
                VALUES ('within_metro_manila', 'Within Metro Manila Hubs', 1)
                """
            )
            hub_id = db.execute(
                """
                INSERT INTO satellite_hubs (hub_group_id, name, normalized_name)
                VALUES (1, 'Main Hub', 'main hub')
                """
            ).lastrowid
            directory_id = db.execute(
                """
                INSERT INTO satellite_directory (hub_id, name, normalized_name)
                VALUES (?, 'B1G Main', 'b1g main')
                """,
                (hub_id,),
            ).lastrowid
            db.execute(
                """
                INSERT INTO event_satellite_target_satellites (
                    event_id, category_key, directory_id
                ) VALUES (?, 'main', ?)
                """,
                (event_id, directory_id),
            )
            db.commit()

            with self.assertRaises(IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_satellite_target_satellites (
                        event_id, category_key, directory_id
                    ) VALUES (?, 'within_metro_manila', ?)
                    """,
                    (event_id, directory_id),
                )
                db.commit()
            db.rollback()

            with self.assertRaises(IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_satellite_target_categories (
                        event_id, category_key, participant_target
                    ) VALUES (?, 'main', 1)
                    """,
                    (event_id,),
                )
                db.commit()
            db.rollback()

            with self.assertRaises(IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_satellite_target_satellites (
                        event_id, category_key, directory_id
                    ) VALUES (?, 'main', ?)
                    """,
                    (event_id + 1, directory_id),
                )
                db.commit()
            db.rollback()

            with self.assertRaises(IntegrityError):
                db.execute(
                    """
                    UPDATE event_satellite_target_categories
                    SET participant_target = 1000000001
                    WHERE event_id = ? AND category_key = 'main'
                    """,
                    (event_id,),
                )
                db.commit()
            db.rollback()

            db.execute("DELETE FROM events WHERE id = ?", (event_id,))
            db.commit()
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM event_satellite_target_categories WHERE event_id = ?",
                    (event_id,),
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM event_satellite_target_satellites WHERE event_id = ?",
                    (event_id,),
                ).fetchone()[0],
            )

    def test_settings_page_saves_complete_canonical_membership_atomically(self):
        with self.app.app_context():
            db = get_db()
            event_a = db.execute("INSERT INTO events (name) VALUES ('Event A')").lastrowid
            event_b = db.execute("INSERT INTO events (name) VALUES ('Event B')").lastrowid
            ensure_event_satellite_target_categories(db, event_a)
            ensure_event_satellite_target_categories(db, event_b)
            within_group = db.execute(
                """
                INSERT INTO hub_groups (code, name, sort_order)
                VALUES ('within_metro_manila', 'Within Metro Manila Hubs', 1)
                """
            ).lastrowid
            outside_group = db.execute(
                """
                INSERT INTO hub_groups (code, name, sort_order)
                VALUES ('outside_metro_manila', 'Outside Metro Manila Hubs', 2)
                """
            ).lastrowid
            within_hub = db.execute(
                """
                INSERT INTO satellite_hubs (hub_group_id, name, normalized_name)
                VALUES (?, 'Metro East', 'metro east')
                """,
                (within_group,),
            ).lastrowid
            outside_hub = db.execute(
                """
                INSERT INTO satellite_hubs (hub_group_id, name, normalized_name)
                VALUES (?, 'ICP', 'icp')
                """,
                (outside_group,),
            ).lastrowid
            main_directory = db.execute(
                """
                INSERT INTO satellite_directory (hub_id, name, normalized_name)
                VALUES (?, 'B1G Main', 'b1g main')
                """,
                (within_hub,),
            ).lastrowid
            icp_directory = db.execute(
                """
                INSERT INTO satellite_directory (hub_id, name, normalized_name)
                VALUES (?, 'B1G Singapore', 'b1g singapore')
                """,
                (outside_hub,),
            ).lastrowid
            east_directory = db.execute(
                """
                INSERT INTO satellite_directory (hub_id, name, normalized_name)
                VALUES (?, 'B1G Antipolo', 'b1g antipolo')
                """,
                (within_hub,),
            ).lastrowid
            unmapped_directory = db.execute(
                """
                INSERT INTO satellite_directory (name, normalized_name)
                VALUES ('Unmapped', 'unmapped')
                """
            ).lastrowid
            batch_id = db.execute(
                "INSERT INTO import_batches (event_id, status) VALUES (?, 'inactive')",
                (event_a,),
            ).lastrowid
            db.executemany(
                """
                INSERT INTO satellites (
                    event_id, batch_id, directory_id, name, normalized_name,
                    affiliation, source_record_count
                ) VALUES (?, ?, ?, ?, ?, 'Local Satellite', 1)
                """,
                [
                    (event_a, batch_id, main_directory, "B1G Main", "b1g main"),
                    (
                        event_a,
                        batch_id,
                        icp_directory,
                        "B1G Singapore",
                        "b1g singapore",
                    ),
                    (
                        event_a,
                        batch_id,
                        east_directory,
                        "B1G Antipolo",
                        "b1g antipolo",
                    ),
                    (event_a, batch_id, None, "Unmapped", "unmapped import"),
                ],
            )
            db.commit()

        client = self.app.test_client()
        page = client.get(
            "/satellites/settings",
            query_string={"event_id": event_a, "view": "targets"},
        )
        self.assertEqual(200, page.status_code)
        self.assertIn(b"Dashboard Target Satellites", page.data)
        self.assertIn(b"B1G Singapore", page.data)
        self.assertIn(b"data-target-category-settings", page.data)
        self.assertNotIn(
            'target-category-{}'.format(unmapped_directory).encode(), page.data
        )

        assignments = [
            "{}:main".format(main_directory),
            "{}:outside_metro_manila".format(icp_directory),
            "{}:within_metro_manila".format(east_directory),
        ]
        saved = client.post(
            "/events/{}/satellite-target-categories/memberships".format(event_a),
            data={"category_assignments": assignments},
            follow_redirects=True,
        )
        self.assertEqual(200, saved.status_code)
        self.assertIn(b"Dashboard Target Satellites saved", saved.data)
        with self.app.app_context():
            db = get_db()
            rows = db.execute(
                """
                SELECT category_key, directory_id
                FROM event_satellite_target_satellites
                WHERE event_id = ? ORDER BY directory_id
                """,
                (event_a,),
            ).fetchall()
            self.assertEqual(
                sorted(
                    [
                        ("main", main_directory),
                        ("outside_metro_manila", icp_directory),
                        ("within_metro_manila", east_directory),
                    ],
                    key=lambda row: row[1],
                ),
                [(row["category_key"], row["directory_id"]) for row in rows],
            )
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM event_satellite_target_satellites WHERE event_id = ?",
                    (event_b,),
                ).fetchone()[0],
            )
            db.execute("DELETE FROM satellites WHERE event_id = ?", (event_a,))
            db.execute(
                """
                UPDATE satellite_directory
                SET hub_id = ?, name = 'B1G Main Renamed',
                    normalized_name = 'b1g main renamed'
                WHERE id = ?
                """,
                (outside_hub, main_directory),
            )
            db.commit()

        persisted = client.get(
            "/satellites/settings",
            query_string={"event_id": event_a, "view": "targets"},
        )
        self.assertIn(b"B1G Main Renamed", persisted.data)
        self.assertIn(
            'value="{}:main" selected'.format(main_directory).encode(),
            persisted.data,
        )

        # A stale/incomplete snapshot fails before deletion and keeps every row.
        rejected = client.post(
            "/events/{}/satellite-target-categories/memberships".format(event_a),
            data={"category_assignments": assignments[:-1]},
            follow_redirects=True,
        )
        self.assertEqual(200, rejected.status_code)
        self.assertIn(b"directory changed while this form was open", rejected.data)
        cross_event = client.post(
            "/events/{}/satellite-target-categories/memberships".format(event_b),
            data={"category_assignments": assignments},
            follow_redirects=True,
        )
        self.assertEqual(200, cross_event.status_code)
        self.assertIn(b"directory changed while this form was open", cross_event.data)
        with self.app.app_context():
            self.assertEqual(
                3,
                get_db().execute(
                    "SELECT COUNT(*) FROM event_satellite_target_satellites WHERE event_id = ?",
                    (event_a,),
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                get_db().execute(
                    "SELECT COUNT(*) FROM event_satellite_target_satellites WHERE event_id = ?",
                    (event_b,),
                ).fetchone()[0],
            )

        script = (Path(__file__).parents[1] / "app/static/satellite_settings.js").read_text()
        self.assertIn("if (!matches) row.querySelector", script)
        self.assertNotIn("select.disabled", script)


if __name__ == "__main__":
    unittest.main()
