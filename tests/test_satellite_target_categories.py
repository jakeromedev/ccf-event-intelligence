import tempfile
import unittest
from pathlib import Path

from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.aggregation import event_dashboard_metrics
from app.db import get_db, get_engine
from app.models import Base
from app.satellite_reporting_categories import (
    resolve_reporting_categories,
    resolve_reporting_category,
)
from app.satellite_target_categories import (
    SATELLITE_TARGET_CATEGORY_KEYS,
    SatelliteTargetCategoryValidationError,
    ensure_event_satellite_target_categories,
    replace_satellite_target_grouping,
    satellite_target_category_rows,
    satellite_target_groups,
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

    def target_form(self, event_id, values):
        with self.app.app_context():
            groups = satellite_target_groups(get_db(), event_id)["groups"]
            get_db().commit()
        return {
            "target_group_{}".format(group["id"]): str(value)
            for group, value in zip(groups, values)
        }

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
            data=self.target_form(event_id, (500, 0, 1000)),
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

        invalid_submissions = [
            self.target_form(event_id, values)
            for values in (
                (501, "1.5", 1001),
                (501, -1, 1001),
                (501, 1, 1000000001),
            )
        ]
        incomplete = self.target_form(event_id, (501, 1, 1001))
        incomplete.pop(next(reversed(incomplete)))
        invalid_submissions.append(incomplete)
        for submission in invalid_submissions:
            response = client.post(
                "/events/{}/satellite-target-categories/targets".format(event_id),
                data=submission,
                follow_redirects=True,
            )
            self.assertEqual(200, response.status_code)
            self.assertIn(b"No changes were made", response.data)
            with self.app.app_context():
                rows = satellite_target_groups(get_db(), event_id)["groups"]
                self.assertEqual(
                    [500, 0, 1000],
                    [row["participant_target"] for row in rows],
                )

        page = client.get(
            "/satellites/settings?event_id={}&view=targets".format(event_id)
        )
        self.assertEqual(3, page.data.count(b'name="target_group_'))
        dashboard_page = client.get("/events/{}".format(event_id))
        self.assertNotIn(b'name="target_group_', dashboard_page.data)
        self.assertIn(b"Manage Satellite Targets", dashboard_page.data)

    def test_all_supported_groupings_and_deterministic_target_migration(self):
        client = self.app.test_client()
        client.post("/events", data={"name": "Grouping Event"})
        with self.app.app_context():
            db = get_db()
            event_id = db.execute(
                "SELECT id FROM events WHERE name = 'Grouping Event'"
            ).fetchone()["id"]

        client.post(
            "/events/{}/satellite-target-categories/targets".format(event_id),
            data=self.target_form(event_id, (500, 700, 1000)),
        )
        expected = {
            "separate": 3,
            "outside_within": 2,
            "outside_main": 2,
            "within_main": 2,
            "all": 1,
        }
        for preset, count in expected.items():
            with self.app.app_context():
                db = get_db()
                # Reset from a known separate state so every supported
                # partition is tested independently.
                replace_satellite_target_grouping(db, event_id, "separate")
                result = replace_satellite_target_grouping(db, event_id, preset)
                db.commit()
                self.assertEqual(count, len(result["groups"]))
                represented = [
                    key for group in result["groups"] for key in group["category_keys"]
                ]
                self.assertCountEqual(SATELLITE_TARGET_CATEGORY_KEYS, represented)

        with self.app.app_context():
            db = get_db()
            replace_satellite_target_grouping(db, event_id, "separate")
            groups = satellite_target_groups(db, event_id)["groups"]
            for group, target in zip(groups, (500, 700, 1000)):
                db.execute(
                    "UPDATE event_satellite_target_groups SET participant_target = ? WHERE id = ?",
                    (target, group["id"]),
                )
            merged = replace_satellite_target_grouping(db, event_id, "outside_within")
            self.assertEqual([1200, 1000], [g["participant_target"] for g in merged["groups"]])
            split = replace_satellite_target_grouping(db, event_id, "separate")
            db.commit()
            self.assertTrue(split["split_targets_reset"])
            self.assertEqual([0, 0, 1000], [g["participant_target"] for g in split["groups"]])

    def test_grouping_route_rejects_invalid_preset_without_changes(self):
        client = self.app.test_client()
        client.post("/events", data={"name": "Atomic Grouping Event"})
        with self.app.app_context():
            db = get_db()
            event_id = db.execute(
                "SELECT id FROM events WHERE name = 'Atomic Grouping Event'"
            ).fetchone()["id"]
        response = client.post(
            "/events/{}/satellite-target-groups/grouping".format(event_id),
            data={"grouping_preset": "overlapping-invalid"},
            follow_redirects=True,
        )
        self.assertIn(b"No changes were made", response.data)
        with self.app.app_context():
            grouping = satellite_target_groups(get_db(), event_id)
            self.assertEqual("separate", grouping["preset_key"])
            self.assertEqual(3, len(grouping["groups"]))

    def test_group_partition_constraints_and_event_isolation(self):
        client = self.app.test_client()
        client.post("/events", data={"name": "Partition Event A"})
        client.post("/events", data={"name": "Partition Event B"})
        with self.app.app_context():
            db = get_db()
            events = {
                row["name"]: row["id"]
                for row in db.execute(
                    "SELECT id, name FROM events WHERE name LIKE 'Partition Event %'"
                ).fetchall()
            }
            grouping_a = satellite_target_groups(db, events["Partition Event A"])
            grouping_b = satellite_target_groups(db, events["Partition Event B"])
            db.commit()

            with self.assertRaises(IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_satellite_target_group_categories (
                        event_id, target_group_id, category_key
                    ) VALUES (?, ?, 'outside_metro_manila')
                    """,
                    (events["Partition Event A"], grouping_a["groups"][1]["id"]),
                )
            db.rollback()

            db.execute(
                """
                DELETE FROM event_satellite_target_group_categories
                WHERE event_id = ? AND category_key = 'main'
                """,
                (events["Partition Event A"],),
            )
            with self.assertRaises(SatelliteTargetCategoryValidationError):
                satellite_target_groups(db, events["Partition Event A"])
            db.rollback()

            replace_satellite_target_grouping(db, events["Partition Event A"], "all")
            db.commit()
            self.assertEqual(
                "all", satellite_target_groups(db, events["Partition Event A"])["preset_key"]
            )
            self.assertEqual("separate", grouping_b["preset_key"])

    def test_reporting_category_resolver_uses_hierarchy_and_stable_main_identity(self):
        with self.app.app_context():
            db = get_db()
            event_a = db.execute("INSERT INTO events (name) VALUES ('Event A')").lastrowid
            ensure_event_satellite_target_categories(db, event_a)
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
            main_hub = db.execute(
                """
                INSERT INTO satellite_hubs (
                    hub_group_id, name, normalized_name, is_main
                ) VALUES (?, 'Main Hub', 'main hub', 1)
                """,
                (within_group,),
            ).lastrowid
            main_directory = db.execute(
                """
                INSERT INTO satellite_directory (hub_id, name, normalized_name)
                VALUES (?, 'B1G Main', 'b1g main')
                """,
                (main_hub,),
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
            resolutions = {
                row["directory_id"]: row
                for row in resolve_reporting_categories(
                    db,
                    [
                        main_directory,
                        icp_directory,
                        east_directory,
                        unmapped_directory,
                    ],
                )
            }
            self.assertEqual("main", resolutions[main_directory]["category_key"])
            self.assertEqual(
                "outside_metro_manila", resolutions[icp_directory]["category_key"]
            )
            self.assertEqual(
                "within_metro_manila", resolutions[east_directory]["category_key"]
            )
            self.assertFalse(resolutions[unmapped_directory]["resolved"])
            self.assertEqual(
                "Needs Mapping", resolutions[unmapped_directory]["category_label"]
            )

            db.execute(
                "UPDATE satellite_directory SET hub_id = ? WHERE id = ?",
                (outside_hub, east_directory),
            )
            self.assertEqual(
                "outside_metro_manila",
                resolve_reporting_category(db, east_directory)["category_key"],
            )
            db.execute(
                """
                UPDATE satellite_hubs
                SET hub_group_id = ?, name = 'Renamed Canonical Hub',
                    normalized_name = 'renamed canonical hub'
                WHERE id = ?
                """,
                (outside_group, main_hub),
            )
            self.assertEqual(
                "main", resolve_reporting_category(db, main_directory)["category_key"]
            )
            missing = resolve_reporting_category(db, 999999)
            self.assertFalse(missing["resolved"])
            self.assertIsNone(missing["category_key"])

            with self.assertRaises(IntegrityError):
                db.execute(
                    """
                    INSERT INTO event_satellite_target_categories (
                        event_id, category_key, participant_target
                    ) VALUES (?, 'main', 1)
                    """,
                    (event_a,),
                )

    def test_settings_page_displays_automatic_categories_without_manual_writes(self):
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
            main_hub = db.execute(
                """
                INSERT INTO satellite_hubs (
                    hub_group_id, name, normalized_name, is_main
                ) VALUES (?, 'Main Hub', 'main hub', 1)
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
                (main_hub,),
            ).lastrowid
            icp_directory = db.execute(
                """
                INSERT INTO satellite_directory (hub_id, name, normalized_name)
                VALUES (?, 'B1G Singapore', 'b1g singapore')
                """,
                (outside_hub,),
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
                    (event_a, batch_id, unmapped_directory, "Unmapped", "unmapped"),
                ],
            )
            db.commit()

        client = self.app.test_client()
        page = client.get(
            "/satellites/settings",
            query_string={"event_id": event_a, "view": "targets"},
        )
        self.assertEqual(200, page.status_code)
        self.assertIn(b"Satellite Reporting Categories", page.data)
        self.assertIn(b"B1G Singapore", page.data)
        self.assertIn(b"Main", page.data)
        self.assertIn(b"Outside Metro Manila Hubs", page.data)
        self.assertIn(b"Needs Mapping", page.data)
        self.assertNotIn(b"category_assignments", page.data)
        self.assertNotIn(b"Bulk assignment", page.data)
        self.assertEqual(
            404,
            client.post(
                "/events/{}/satellite-target-categories/memberships".format(event_a)
            ).status_code,
        )

        with self.app.app_context():
            db = get_db()
            db.execute(
                """
                UPDATE satellite_hubs
                SET hub_group_id = ?, name = 'Main Hub Renamed',
                    normalized_name = 'main hub renamed'
                WHERE id = ?
                """,
                (outside_group, main_hub),
            )
            db.commit()

        updated = client.get(
            "/satellites/settings",
            query_string={"event_id": event_a, "view": "targets"},
        )
        self.assertIn(b"Main Hub Renamed", updated.data)
        self.assertIn(b"Main", updated.data)
        other_event = client.get(
            "/satellites/settings",
            query_string={"event_id": event_b, "view": "targets"},
        )
        self.assertIn(b"No canonical Satellites are represented by this Event", other_event.data)


if __name__ == "__main__":
    unittest.main()
