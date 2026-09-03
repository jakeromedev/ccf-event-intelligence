import json
import re
import tempfile
import unittest
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from app import create_app
from app.db import get_db, get_engine
from app.models import Base
from app.satellite_analytics import canonical_satellite_metrics
from app.satellite_datasets import satellite_dataset_options
from app.satellite_settings import satellite_settings_hierarchy, update_satellite
from app.satellite_settings_registrants import event_settings_registrants
from app.satellite_sync import (
    ALREADY_SYNCED,
    AMBIGUOUS,
    HUB_NOT_FOUND,
    MISSING_SATELLITE,
    READY_TO_SYNC,
    SATELLITE_NOT_CONFIGURED,
    SatelliteSyncAnalysisError,
    analyze_event_satellite_sync,
    execute_event_satellite_sync,
)


class SatelliteSyncAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "DATABASE_URL": "sqlite+pysqlite:///{}".format(root / "test.sqlite3"),
                "STAGING_DIR": str(root / "staging"),
                "AUTHENTICATION_DISABLED": True,
                "WTF_CSRF_ENABLED": False,
            }
        )
        with self.app.app_context():
            Base.metadata.create_all(get_engine())
            db = get_db()
            self.event_id = db.execute(
                "INSERT INTO events (name) VALUES ('Sync Event')"
            ).lastrowid
            self.batch_id = db.execute(
                """
                INSERT INTO import_batches (
                    event_id, status, active_event_id, activated_at
                ) VALUES (?, 'active', ?, CURRENT_TIMESTAMP)
                """,
                (self.event_id, self.event_id),
            ).lastrowid
            db.executemany(
                """
                INSERT INTO hub_groups (code, name, sort_order)
                VALUES (?, ?, ?)
                """,
                [
                    ("within_metro_manila", "Within Metro Manila Hubs", 1),
                    ("outside_metro_manila", "Outside Metro Manila Hubs", 2),
                ],
            )
            db.commit()

    def tearDown(self):
        self.temp.cleanup()

    def _hub(self, name, group="outside_metro_manila"):
        with self.app.app_context():
            db = get_db()
            group_id = db.execute(
                "SELECT id FROM hub_groups WHERE code = ?", (group,)
            ).fetchone()["id"]
            hub_id = db.execute(
                """
                INSERT INTO satellite_hubs (hub_group_id, name, normalized_name)
                VALUES (?, ?, ?)
                """,
                (group_id, name, " ".join(name.strip().split()).casefold()),
            ).lastrowid
            db.commit()
            return hub_id

    def _directory(self, hub_id, name):
        with self.app.app_context():
            db = get_db()
            directory_id = db.execute(
                """
                INSERT INTO satellite_directory (hub_id, name, normalized_name)
                VALUES (?, ?, ?)
                """,
                (hub_id, name, " ".join(name.strip().split()).casefold()),
            ).lastrowid
            db.commit()
            return directory_id

    def _evidence(
        self,
        source_hub="Mindanao South",
        source_satellite="B1G Tagum",
        directory_id=None,
        sequence=1,
        imported_id=None,
        imported_name="B1G Tagum",
    ):
        source_fields = {
            "Luzon South": "Luzon South Hub",
            "Mindanao South": "Mindanao South Hub",
            "Mindanao North": "Mindanao North Hub",
            "Visayas": "Visayas Hub",
            "ICP": "Specify Icp Hub",
        }
        normalized_source_hub = " ".join(source_hub.strip().split()).casefold()
        field = next(
            (
                value
                for key, value in source_fields.items()
                if key.casefold() == normalized_source_hub
            ),
            "Mindanao South Hub",
        )
        source_data = {field: source_satellite}
        with self.app.app_context():
            db = get_db()
            if imported_id is None:
                imported_id = db.execute(
                    """
                    INSERT INTO satellites (
                        event_id, batch_id, directory_id, name, normalized_name,
                        affiliation, source_record_count
                    ) VALUES (?, ?, ?, ?, ?, 'Local Satellite', 1)
                    """,
                    (
                        self.event_id,
                        self.batch_id,
                        directory_id,
                        imported_name,
                        " ".join(imported_name.strip().split()).casefold(),
                    ),
                ).lastrowid
            else:
                db.execute(
                    """
                    UPDATE satellites SET source_record_count = source_record_count + 1
                    WHERE id = ?
                    """,
                    (imported_id,),
                )
            db.execute(
                """
                INSERT INTO registrants (
                    batch_id, source_id, registration_code, ticket_code,
                    first_name, last_name, b1g_satellite_hub_raw,
                    affiliation, satellite_name, ticket_matched, source_data_json
                ) VALUES (?, ?, ?, ?, 'Test', 'Registrant', ?,
                          'Local Satellite', ?, 1, ?)
                """,
                (
                    self.batch_id,
                    str(sequence),
                    "R-{}".format(sequence),
                    "T-{}".format(sequence),
                    source_hub,
                    imported_name,
                    json.dumps(source_data),
                ),
            )
            db.commit()
            return imported_id

    def _analyze(self):
        with self.app.app_context():
            return analyze_event_satellite_sync(get_db(), self.event_id)

    def _review_for_confirmation(self, client):
        response = client.post(
            "/satellites/settings/sync/review", data={"event_id": self.event_id}
        )
        match = re.search(
            rb'name="confirmation_token" value="([^"]+)"', response.data
        )
        self.assertIsNotNone(match, response.data.decode(errors="replace"))
        return response, match.group(1).decode()

    def test_exact_match_is_ready_and_analysis_is_read_only(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        imported_id = self._evidence()

        plan = self._analyze()

        self.assertEqual(READY_TO_SYNC, plan["entries"][0]["status"])
        self.assertEqual(canonical_id, plan["entries"][0]["canonical_satellite"]["id"])
        self.assertEqual(1, plan["source_satellite_records"])
        self.assertEqual(1, plan["represented_registrations"])
        with self.app.app_context():
            directory_id = get_db().execute(
                "SELECT directory_id FROM satellites WHERE id = ?", (imported_id,)
            ).fetchone()["directory_id"]
        self.assertIsNone(directory_id)

    def test_case_whitespace_and_nfkc_normalization_match(self):
        hub_id = self._hub("Mindanao South")
        self._directory(hub_id, "B1G Tagum")
        self._evidence("  MINDANAO   SOUTH ", "  Ｂ１Ｇ   Ｔａｇｕｍ  ")

        self.assertEqual(READY_TO_SYNC, self._analyze()["entries"][0]["status"])

    def test_missing_configured_hub_is_reported(self):
        self._evidence(source_hub="Luzon South")
        self.assertEqual(HUB_NOT_FOUND, self._analyze()["entries"][0]["status"])

    def test_missing_source_satellite_is_reported(self):
        self._hub("Mindanao South")
        self._evidence(source_satellite="")
        self.assertEqual(MISSING_SATELLITE, self._analyze()["entries"][0]["status"])

    def test_satellite_under_wrong_hub_is_not_matched(self):
        self._hub("Mindanao South")
        other_hub = self._hub("Visayas")
        self._directory(other_hub, "B1G Tagum")
        self._evidence()
        self.assertEqual(
            SATELLITE_NOT_CONFIGURED, self._analyze()["entries"][0]["status"]
        )

    def test_already_synced_link_is_skipped(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        self._evidence(directory_id=canonical_id)
        self.assertEqual(ALREADY_SYNCED, self._analyze()["entries"][0]["status"])

    def test_different_existing_link_is_reported_as_already_synced(self):
        expected_hub = self._hub("Mindanao South")
        self._directory(expected_hub, "B1G Tagum")
        other_hub = self._hub("Visayas")
        existing_id = self._directory(other_hub, "B1G Cebu")
        self._evidence(directory_id=existing_id)
        self.assertEqual(ALREADY_SYNCED, self._analyze()["entries"][0]["status"])

    def test_aggregate_with_two_hub_interpretations_is_ambiguous(self):
        south = self._hub("Mindanao South")
        north = self._hub("Mindanao North")
        self._directory(south, "B1G Tagum")
        self._directory(north, "B1G Tagum")
        imported_id = self._evidence(sequence=1)
        self._evidence(
            source_hub="Mindanao North", sequence=2, imported_id=imported_id
        )

        plan = self._analyze()
        self.assertEqual(AMBIGUOUS, plan["entries"][0]["status"])
        self.assertEqual(
            [AMBIGUOUS, AMBIGUOUS],
            [item["status"] for item in plan["entries"][0]["registrations"]],
        )

    def test_invalid_or_unknown_event_is_rejected(self):
        with self.app.app_context():
            with self.assertRaises(SatelliteSyncAnalysisError):
                analyze_event_satellite_sync(get_db(), "not-an-id")
            with self.assertRaises(SatelliteSyncAnalysisError):
                analyze_event_satellite_sync(get_db(), 999999)

    def test_sync_action_is_only_shown_with_event_context(self):
        client = self.app.test_client()
        global_settings = client.get("/satellites/settings")
        event_settings = client.get(
            "/satellites/settings", query_string={"event_id": self.event_id}
        )

        self.assertEqual(200, global_settings.status_code)
        self.assertNotIn(b"Sync Registration Satellites", global_settings.data)
        self.assertEqual(200, event_settings.status_code)
        self.assertIn(b"Sync Registration Satellites", event_settings.data)
        self.assertIn(b"/satellites/settings/sync/review", event_settings.data)

    def test_review_route_renders_counts_failures_filter_and_changes_nothing(self):
        imported_id = self._evidence(source_hub="Luzon South")
        client = self.app.test_client()

        response = client.post(
            "/satellites/settings/sync/review", data={"event_id": self.event_id}
        )

        self.assertEqual(200, response.status_code)
        for marker in (
            b"data-sync-review-modal",
            b"Registration Satellite Scan",
            b"Source Satellite Records",
            b"Represented Registrations",
            b"Ready to Sync",
            b"Already Synced",
            b"Not Synced Registrations",
            b"data-sync-reason-filter",
            b"data-sync-failure-row",
            b"Hub Not Found",
            b"Luzon South",
            b"B1G Tagum",
            b"Test Registrant",
            b"No new Hub or Satellite records will be created",
            b"No data has been changed during this review",
        ):
            self.assertIn(marker, response.data)
        self.assertNotIn(b"Confirm Sync", response.data)
        with self.app.app_context():
            row = get_db().execute(
                "SELECT directory_id, name, source_record_count FROM satellites WHERE id = ?",
                (imported_id,),
            ).fetchone()
        self.assertIsNone(row["directory_id"])
        self.assertEqual("B1G Tagum", row["name"])
        self.assertEqual(1, row["source_record_count"])

    def test_review_route_requires_a_valid_event(self):
        client = self.app.test_client()
        self.assertEqual(
            400, client.post("/satellites/settings/sync/review", data={}).status_code
        )
        self.assertEqual(
            404,
            client.post(
                "/satellites/settings/sync/review", data={"event_id": 999999}
            ).status_code,
        )

    def test_review_ui_has_accessible_dialog_and_client_side_reason_filter(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "templates"
            / "satellite_settings.html"
        ).read_text()
        script = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "static"
            / "satellite_settings.js"
        ).read_text()

        for marker in (
            'aria-labelledby="satellite-sync-title"',
            'aria-describedby="satellite-sync-description"',
            'role="region"',
            'aria-live="polite"',
            'data-sync-review-close',
        ):
            self.assertIn(marker, template)
        for marker in (
            "data-sync-reason-filter",
            "applyReasonFilter",
            'addEventListener("cancel"',
            "requestAnimationFrame",
        ):
            self.assertIn(marker, script)

    def test_confirmation_updates_only_directory_id_and_is_idempotent(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        imported_id = self._evidence()
        with self.app.app_context():
            db = get_db()
            before = dict(
                db.execute("SELECT * FROM satellites WHERE id = ?", (imported_id,)).fetchone()
            )
            counts_before = {
                table: db.execute("SELECT COUNT(*) FROM {}".format(table)).fetchone()[0]
                for table in (
                    "hub_groups",
                    "satellite_hubs",
                    "satellite_directory",
                    "satellites",
                    "registrants",
                )
            }

        client = self.app.test_client()
        review, confirmation_token = self._review_for_confirmation(client)
        self.assertIn(b"Confirm Sync", review.data)
        confirmed = client.post(
            "/satellites/settings/sync/confirm",
            data={
                "event_id": self.event_id,
                "confirmation_token": confirmation_token,
            },
            follow_redirects=True,
        )
        self.assertIn(b"Registration Satellite Sync Complete", confirmed.data)
        self.assertIn(b"Newly Synchronized</dt><dd>1", confirmed.data)
        self.assertIn(b"Registrations Synchronized</dt><dd>1", confirmed.data)
        self.assertIn(b"All eligible registration Satellites are synchronized", confirmed.data)
        refreshed_result_url = client.get(
            "/satellites/settings",
            query_string={"event_id": self.event_id, "sync_complete": 1},
        )
        self.assertNotIn(b"Registration Satellite Sync Complete", refreshed_result_url.data)

        with self.app.app_context():
            db = get_db()
            after = dict(
                db.execute("SELECT * FROM satellites WHERE id = ?", (imported_id,)).fetchone()
            )
            counts_after = {
                table: db.execute("SELECT COUNT(*) FROM {}".format(table)).fetchone()[0]
                for table in counts_before
            }
        self.assertEqual(canonical_id, after.pop("directory_id"))
        before.pop("directory_id")
        self.assertEqual(before, after)
        self.assertEqual(counts_before, counts_after)

        repeated = client.post(
            "/satellites/settings/sync/confirm",
            data={
                "event_id": self.event_id,
                "confirmation_token": confirmation_token,
            },
            follow_redirects=True,
        )
        self.assertIn(b"already used", repeated.data)
        with self.app.app_context():
            service_result = execute_event_satellite_sync(get_db(), self.event_id)
            self.assertEqual(0, service_result["synchronized_count"])
            self.assertEqual(1, service_result["already_synced_count"])
            get_db().rollback()
            self.assertEqual(
                canonical_id,
                get_db().execute(
                    "SELECT directory_id FROM satellites WHERE id = ?", (imported_id,)
                ).fetchone()["directory_id"],
            )

    def test_confirmation_skips_unmatched_and_existing_linked_records(self):
        south = self._hub("Mindanao South")
        self._directory(south, "B1G Tagum")
        visayas = self._hub("Visayas")
        existing_id = self._directory(visayas, "B1G Existing Assignment")
        unmatched_id = self._evidence(
            source_hub="Luzon South",
            source_satellite="B1G Cebu",
            sequence=1,
            imported_name="B1G Cebu",
        )
        source_target = self._directory(south, "B1G Davao")
        existing_link_id = self._evidence(
            source_satellite="B1G Davao",
            directory_id=existing_id,
            sequence=2,
            imported_name="B1G Davao",
        )
        ready_id = self._evidence(sequence=3)

        client = self.app.test_client()
        _review, confirmation_token = self._review_for_confirmation(client)
        result = client.post(
            "/satellites/settings/sync/confirm",
            data={
                "event_id": self.event_id,
                "confirmation_token": confirmation_token,
            },
            follow_redirects=True,
        )

        self.assertIn(b"Registration Satellite Sync Complete", result.data)
        self.assertIn(b"Newly Synchronized</dt><dd>1", result.data)
        self.assertIn(b"Already Synced</dt><dd>1", result.data)
        self.assertIn(b"Not Synchronized</dt><dd>1", result.data)
        self.assertIn(b"View Not Synced Registrations", result.data)
        self.assertIn(b"Hub Not Found", result.data)
        self.assertNotIn(b"Conflict", result.data)
        with self.app.app_context():
            db = get_db()
            rows = {
                row["id"]: row["directory_id"]
                for row in db.execute(
                    "SELECT id, directory_id FROM satellites ORDER BY id"
                ).fetchall()
            }
        self.assertIsNone(rows[unmatched_id])
        self.assertEqual(existing_id, rows[existing_link_id])
        self.assertNotEqual(source_target, rows[existing_link_id])
        self.assertIsNotNone(rows[ready_id])

    def test_confirmation_revalidates_changes_made_after_review(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        imported_id = self._evidence()
        client = self.app.test_client()
        review, confirmation_token = self._review_for_confirmation(client)
        self.assertIn(b"Confirm Sync", review.data)
        with self.app.app_context():
            db = get_db()
            db.execute(
                """
                UPDATE satellite_directory
                SET name = 'B1G Renamed', normalized_name = 'b1g renamed'
                WHERE id = ?
                """,
                (canonical_id,),
            )
            db.commit()

        confirmed = client.post(
            "/satellites/settings/sync/confirm",
            data={
                "event_id": self.event_id,
                "confirmation_token": confirmation_token,
            },
            follow_redirects=True,
        )

        self.assertIn(b"Registration Satellite Sync Complete", confirmed.data)
        self.assertIn(b"Newly Synchronized</dt><dd>0", confirmed.data)
        self.assertIn(b"Not Synchronized</dt><dd>1", confirmed.data)
        with self.app.app_context():
            self.assertIsNone(
                get_db().execute(
                    "SELECT directory_id FROM satellites WHERE id = ?", (imported_id,)
                ).fetchone()["directory_id"]
            )

    def test_database_failure_rolls_back_every_directory_link(self):
        hub_id = self._hub("Mindanao South")
        self._directory(hub_id, "B1G Tagum")
        self._directory(hub_id, "B1G Davao")
        first_id = self._evidence(sequence=1)
        second_id = self._evidence(
            source_satellite="B1G Davao", sequence=2, imported_name="B1G Davao"
        )
        with self.app.app_context():
            db = get_db()
            db.execute(
                """
                CREATE TRIGGER fail_satellite_sync
                BEFORE UPDATE OF directory_id ON satellites
                WHEN OLD.id = {}
                BEGIN SELECT RAISE(ABORT, 'forced sync failure'); END
                """.format(second_id)
            )
            db.commit()

        client = self.app.test_client()
        _review, confirmation_token = self._review_for_confirmation(client)
        response = client.post(
            "/satellites/settings/sync/confirm",
            data={
                "event_id": self.event_id,
                "confirmation_token": confirmation_token,
            },
            follow_redirects=True,
        )

        self.assertIn(b"No changes were saved", response.data)
        with self.app.app_context():
            rows = get_db().execute(
                "SELECT id, directory_id FROM satellites WHERE id IN (?, ?) ORDER BY id",
                (first_id, second_id),
            ).fetchall()
        self.assertEqual([None, None], [row["directory_id"] for row in rows])

    def test_execution_service_leaves_transaction_control_to_caller(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        imported_id = self._evidence()
        with self.app.app_context():
            db = get_db()
            result = execute_event_satellite_sync(db, self.event_id)
            linked = db.execute(
                "SELECT directory_id FROM satellites WHERE id = ?", (imported_id,)
            ).fetchone()["directory_id"]
            self.assertEqual(1, result["synchronized_count"])
            self.assertEqual(1, result["synchronized_registration_count"])
            self.assertEqual(canonical_id, linked)
            db.rollback()
            self.assertIsNone(
                db.execute(
                    "SELECT directory_id FROM satellites WHERE id = ?", (imported_id,)
                ).fetchone()["directory_id"]
            )

    def test_successful_confirmation_emits_aggregate_only_audit_log(self):
        hub_id = self._hub("Mindanao South")
        self._directory(hub_id, "B1G Tagum")
        self._evidence()
        client = self.app.test_client()
        _review, confirmation_token = self._review_for_confirmation(client)

        with patch.object(self.app.logger, "info") as log_info:
            response = client.post(
                "/satellites/settings/sync/confirm",
                data={
                    "event_id": self.event_id,
                    "confirmation_token": confirmation_token,
                },
            )

        self.assertEqual(302, response.status_code)
        with client.session_transaction() as saved_session:
            stored_result = saved_session["satellite_sync_result"]
        self.assertEqual(
            {
                "event_id",
                "synchronized_count",
                "synchronized_registration_count",
                "already_synced_count",
                "not_synced_count",
            },
            set(stored_result),
        )
        audit_calls = [
            call
            for call in log_info.call_args_list
            if call.args and call.args[0] == "registration_satellite_sync_completed"
        ]
        self.assertEqual(1, len(audit_calls))
        extra = audit_calls[0].kwargs["extra"]
        self.assertEqual(self.event_id, extra["event_id"])
        self.assertEqual(1, extra["matched_count"])
        self.assertEqual(0, extra["skipped_count"])
        self.assertEqual(0, extra["failed_count"])
        for sensitive_key in (
            "registration",
            "participant",
            "source_hub",
            "source_satellite",
        ):
            self.assertNotIn(sensitive_key, extra)

    def test_synced_link_integrates_with_directory_rename_and_dataset_selectors(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        imported_id = self._evidence()
        with self.app.app_context():
            db = get_db()
            execute_event_satellite_sync(db, self.event_id)
            db.commit()
            update_satellite(db, canonical_id, hub_id, "B1G Tagum Central")
            db.commit()

            imported = db.execute(
                "SELECT directory_id, name, normalized_name FROM satellites WHERE id = ?",
                (imported_id,),
            ).fetchone()
            options = satellite_dataset_options(db, self.event_id, self.batch_id)
            hierarchy = satellite_settings_hierarchy(db)

        self.assertEqual(canonical_id, imported["directory_id"])
        self.assertEqual("B1G Tagum", imported["name"])
        self.assertEqual("b1g tagum", imported["normalized_name"])
        self.assertEqual("B1G Tagum Central", options[0]["name"])
        directory_entry = next(
            satellite
            for group in hierarchy["groups"]
            for hub in group["hubs"]
            for satellite in hub["satellites"]
            if satellite["id"] == canonical_id
        )
        self.assertEqual("B1G Tagum Central", directory_entry["name"])
        self.assertEqual(1, directory_entry["source_records"])

    def test_event_settings_registrants_aggregate_filter_sort_and_paginate(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        imported_id = self._evidence(directory_id=canonical_id, sequence=1)
        self._evidence(directory_id=canonical_id, sequence=2, imported_id=imported_id)
        self._evidence(
            source_hub="Visayas",
            source_satellite="B1G Cebu",
            sequence=3,
            imported_name="B1G Cebu",
        )

        with self.app.app_context():
            result = event_settings_registrants(
                get_db(), self.event_id, sort="identifier", direction="desc",
                page=1, per_page=1,
            )
            synced = event_settings_registrants(
                get_db(), self.event_id, sync_status="synced"
            )
            review = event_settings_registrants(
                get_db(), self.event_id, sync_status="needs_review"
            )
            searched = event_settings_registrants(
                get_db(), self.event_id, query="R-2"
            )

        self.assertEqual(3, result["totals"]["registrants"])
        self.assertEqual(2, result["totals"]["synced"])
        self.assertEqual(1, result["totals"]["review"])
        self.assertEqual(3, result["pagination"]["total"])
        self.assertEqual(1, len(result["rows"]))
        self.assertEqual("3", result["rows"][0]["identifier"])
        self.assertEqual(2, synced["pagination"]["total"])
        self.assertEqual(1, review["pagination"]["total"])
        self.assertEqual(1, searched["pagination"]["total"])
        self.assertEqual(
            2,
            result["counts"]["satellite:{}".format(canonical_id)]["registrants"],
        )

    def test_event_settings_uses_canonical_match_for_unassigned_legacy_link(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        with self.app.app_context():
            db = get_db()
            legacy_id = db.execute(
                """
                INSERT INTO satellite_directory (hub_id, name, normalized_name)
                VALUES (NULL, 'B1G Tagum', 'b1g tagum')
                """
            ).lastrowid
            db.commit()
        imported_id = self._evidence(directory_id=legacy_id)

        with self.app.app_context():
            db = get_db()
            result = event_settings_registrants(
                db,
                self.event_id,
                satellite_id=canonical_id,
                search_scope="registrant",
            )
            stored_directory_id = db.execute(
                "SELECT directory_id FROM satellites WHERE id = ?", (imported_id,)
            ).fetchone()["directory_id"]

        self.assertEqual(1, result["pagination"]["total"])
        self.assertEqual(canonical_id, result["rows"][0]["satellite_id"])
        self.assertEqual("Mindanao South", result["rows"][0]["hub"])
        self.assertEqual("B1G Tagum", result["rows"][0]["satellite"])
        self.assertEqual(
            1,
            result["counts"]["hub:{}".format(hub_id)]["registrants"],
        )
        self.assertEqual(legacy_id, stored_directory_id)

    def test_event_settings_page_and_lazy_registrant_endpoint(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        self._evidence(directory_id=canonical_id)
        client = self.app.test_client()

        page = client.get(
            "/satellites/settings",
            query_string={"event_id": self.event_id, "view": "registrants"},
        )
        payload = client.get(
            "/satellites/settings/registrants",
            query_string={
                "event_id": self.event_id,
                "satellite_id": canonical_id,
                "per_page": 10,
            },
        )

        self.assertEqual(200, page.status_code)
        self.assertIn(b"Registration Satellite Assignments", page.data)
        self.assertIn(b"Already Synced", page.data)
        self.assertEqual(200, payload.status_code)
        self.assertEqual(1, payload.get_json()["pagination"]["total"])
        self.assertEqual(
            "B1G Tagum", payload.get_json()["rows"][0]["satellite"]
        )

    def test_global_settings_never_embeds_event_registrants(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        self._evidence(directory_id=canonical_id)

        response = self.app.test_client().get("/satellites/settings")

        self.assertEqual(200, response.status_code)
        self.assertNotIn(b"Test Registrant", response.data)
        self.assertNotIn(b"Registration Satellite Assignments", response.data)
        self.assertNotIn(b"data-registrants-url", response.data)

    def test_large_event_registrants_remain_server_paginated(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        imported_id = self._evidence(directory_id=canonical_id, sequence=1)
        source_data = json.dumps({"Mindanao South Hub": "B1G Tagum"})
        with self.app.app_context():
            db = get_db()
            db.executemany(
                """
                INSERT INTO registrants (
                    batch_id, source_id, registration_code, ticket_code,
                    first_name, last_name, b1g_satellite_hub_raw,
                    affiliation, satellite_name, ticket_matched, source_data_json
                ) VALUES (?, ?, ?, ?, 'Scale', 'Registrant', 'Mindanao South',
                          'Local Satellite', 'B1G Tagum', 1, ?)
                """,
                [
                    (
                        self.batch_id,
                        str(sequence),
                        "R-{}".format(sequence),
                        "T-{}".format(sequence),
                        source_data,
                    )
                    for sequence in range(2, 1251)
                ],
            )
            db.execute(
                "UPDATE satellites SET source_record_count = 1250 WHERE id = ?",
                (imported_id,),
            )
            db.commit()
            started = perf_counter()
            result = event_settings_registrants(
                db, self.event_id, page=25, per_page=25
            )
            elapsed = perf_counter() - started

        self.assertEqual(1250, result["pagination"]["total"])
        self.assertEqual(25, len(result["rows"]))
        self.assertEqual(25, result["pagination"]["page"])
        self.assertLess(elapsed, 5.0)

    def test_mobile_filter_sheet_and_accessible_filter_chips_render(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        self._evidence(directory_id=canonical_id)

        response = self.app.test_client().get(
            "/satellites/settings",
            query_string={
                "event_id": self.event_id,
                "group": "outside_metro_manila",
                "hub_id": hub_id,
                "satellite_id": canonical_id,
                "sync_status": "already_synced",
            },
        )

        self.assertEqual(200, response.status_code)
        for marker in (
            b"data-mobile-filters-open",
            b"data-mobile-filter-dialog",
            b"Apply Filters",
            b"aria-haspopup=\"dialog\"",
            b"aria-label=\"Remove Hub Group filter\"",
            b"aria-label=\"Remove Hub filter\"",
            b"aria-label=\"Remove Satellite filter\"",
            b"aria-label=\"Remove Sync Status filter\"",
        ):
            self.assertIn(marker, response.data)

    def test_main_page_metrics_refresh_after_sync(self):
        hub_id = self._hub("Mindanao South")
        self._directory(hub_id, "B1G Tagum")
        self._evidence()
        client = self.app.test_client()

        before = client.get(
            "/satellites/settings", query_string={"event_id": self.event_id}
        )
        with self.app.app_context():
            db = get_db()
            execute_event_satellite_sync(db, self.event_id)
            db.commit()
        after = client.get(
            "/satellites/settings", query_string={"event_id": self.event_id}
        )

        self.assertIn(
            b'data-registrant-count="1" data-synced-count="0" data-ready-count="1"',
            before.data,
        )
        self.assertIn(
            b'data-registrant-count="1" data-synced-count="1" data-ready-count="0"',
            after.data,
        )

    def test_sync_repairs_incomplete_legacy_link_and_refreshes_analytics(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        legacy_id = self._directory(None, "B1G Tagum")
        imported_id = self._evidence(directory_id=legacy_id)

        with self.app.app_context():
            db = get_db()
            before = canonical_satellite_metrics(db, self.batch_id)
            plan = analyze_event_satellite_sync(db, self.event_id)

            self.assertEqual(1, before["needs_mapping"])
            self.assertEqual(READY_TO_SYNC, plan["entries"][0]["status"])

            result = execute_event_satellite_sync(db, self.event_id)
            db.commit()
            after = canonical_satellite_metrics(db, self.batch_id)
            linked_id = db.execute(
                "SELECT directory_id FROM satellites WHERE id = ?", (imported_id,)
            ).fetchone()["directory_id"]

        self.assertEqual(1, result["synchronized_count"])
        self.assertEqual(canonical_id, linked_id)
        self.assertEqual(0, after["needs_mapping"])

    def test_directory_uses_hub_tables_and_breadcrumb_explorer(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        self._evidence(directory_id=canonical_id)

        response = self.app.test_client().get(
            "/satellites/settings", query_string={"event_id": self.event_id}
        )

        self.assertEqual(200, response.status_code)
        for marker in (
            b"satellite-hub-table",
            b"data-open-satellite-explorer",
            b"View Satellites",
            b"data-hub-satellites-template",
            b"data-modal-view-registrants",
            b"data-satellite-explorer",
            b"data-explorer-breadcrumb",
        ):
            self.assertIn(marker, response.data)
        self.assertNotIn(b"data-hub-toggle", response.data)
        self.assertNotIn(b"Test Registrant", response.data)

    def test_registrant_search_shows_satellite_information(self):
        hub_id = self._hub("Mindanao South")
        canonical_id = self._directory(hub_id, "B1G Tagum")
        self._evidence(directory_id=canonical_id)

        response = self.app.test_client().get(
            "/satellites/settings",
            query_string={
                "event_id": self.event_id,
                "search_scope": "registrant",
                "q": "R-1",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertIn(b"Satellite Information", response.data)
        self.assertIn(b"Test Registrant", response.data)
        self.assertIn(b"B1G Tagum", response.data)
        self.assertIn(b"View Satellite", response.data)
        self.assertIn(b'<option value="registrant" selected>', response.data)


if __name__ == "__main__":
    unittest.main()
