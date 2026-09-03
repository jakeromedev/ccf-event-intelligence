import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.aggregation import curated_registrant_detail, satellite_registrants
from app.db import get_db, get_engine
from app.importer import process_batch, store_validation, validate_batch
from app.models import Base
from app.registrant_satellite_assignments import set_manual_satellite_assignment
from app.satellite_analytics import canonical_satellite_metrics
from app.satellite_settings_registrants import event_settings_registrants
from app.satellite_sync import (
    MANUAL_PROTECTED,
    analyze_event_satellite_sync,
    execute_event_satellite_sync,
)
from tests.test_phase1 import (
    BUYER_FIELDS,
    REGISTRANT_REGIONAL_B1G_FIELDS,
    TICKET_FIELDS,
    write_csv,
)


class RegistrantSatelliteAssignmentImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.paths = {
            "tickets": root / "tickets.csv",
            "buyers": root / "buyers.csv",
            "registrants": root / "registrants.csv",
        }
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
                "INSERT INTO events (name) VALUES ('Protected Imports')"
            ).lastrowid
            self.user_id = db.execute(
                """
                INSERT INTO users (
                    username, password_hash, role, status, approved_at
                ) VALUES (
                    'satellite-operator', 'unused-test-hash', 'user',
                    'approved', CURRENT_TIMESTAMP
                )
                """
            ).lastrowid
            group_id = db.execute(
                """
                INSERT INTO hub_groups (code, name, sort_order)
                VALUES ('outside_metro_manila', 'Outside Metro Manila Hubs', 1)
                """
            ).lastrowid
            hub_id = db.execute(
                """
                INSERT INTO satellite_hubs (hub_group_id, name, normalized_name)
                VALUES (?, 'Mindanao South', 'mindanao south')
                """,
                (group_id,),
            ).lastrowid
            self.directory_ids = {}
            for name in ("B1G Tagum", "B1G Davao", "B1G General Santos"):
                self.directory_ids[name] = db.execute(
                    """
                    INSERT INTO satellite_directory (hub_id, name, normalized_name)
                    VALUES (?, ?, ?)
                    """,
                    (hub_id, name, name.casefold()),
                ).lastrowid
            db.commit()

    def tearDown(self):
        self.temp.cleanup()

    def _process(self, imported_satellite, source_id):
        write_csv(
            self.paths["buyers"],
            BUYER_FIELDS,
            [
                {
                    "Id": "buyer-{}".format(source_id),
                    "Slug": "protected-imports",
                    "Event Name": "Protected Imports",
                    "Buyer Reference Number": "BUYER-1",
                    "Payment Status": "Payment Validated",
                    "Quantity": "1",
                }
            ],
        )
        write_csv(
            self.paths["tickets"],
            TICKET_FIELDS,
            [
                {
                    "Id": "ticket-{}".format(source_id),
                    "Slug": "protected-imports",
                    "Event Name": "Protected Imports",
                    "Ticket Code": "T-STABLE",
                    "Control Number": "CONTROL-1",
                    "Ticket Status": "Assigned",
                    "Payment Status": "Payment Validated",
                    "Buyer Reference Number": "BUYER-1",
                }
            ],
        )
        write_csv(
            self.paths["registrants"],
            REGISTRANT_REGIONAL_B1G_FIELDS,
            [
                {
                    "ID": source_id,
                    "Event Name": "Protected Imports",
                    "Event Slug": "protected-imports",
                    "Registration Code": "R-STABLE",
                    "Ticket Code": "T-STABLE",
                    "Ticket Status": "Assigned",
                    "First Name": "Stable",
                    "Last Name": "Registrant",
                    "Email Address": "stable@example.com",
                    "Mobile Number": "09000000000",
                    "Gender": "Female",
                    "Birth Month": "January",
                    "Birth Year": "1990",
                    "Bg Satellite Hub": "Mindanao South",
                    "Mindanao South Hub": imported_satellite,
                }
            ],
        )
        staged = {
            export_type: (str(path), path.name)
            for export_type, path in self.paths.items()
        }
        validation = validate_batch(staged)
        self.assertTrue(validation.valid)
        with self.app.app_context():
            batch_id = store_validation(get_db(), validation, self.event_id)
            process_batch(get_db(), batch_id)
        return batch_id

    def _assignment_values(self, participant_id):
        with self.app.app_context():
            row = get_db().execute(
                """
                SELECT id, event_id, attestation_participant_id, directory_id,
                       assignment_source, source_batch_id, updated_by_user_id,
                       created_at, updated_at
                FROM event_registrant_satellites
                WHERE event_id = ? AND attestation_participant_id = ?
                """,
                (self.event_id, participant_id),
            ).fetchone()
            return tuple(row[key] for key in row.keys())

    def test_manual_assignment_survives_same_different_and_multiple_future_batches(self):
        first_batch_id = self._process("B1G Tagum", "source-1")
        with self.app.app_context():
            db = get_db()
            participant_id = db.execute(
                """
                SELECT attestation_participant_id
                FROM attestation_participant_registrants
                WHERE event_id = ? AND batch_id = ?
                """,
                (self.event_id, first_batch_id),
            ).fetchone()["attestation_participant_id"]
            set_manual_satellite_assignment(
                db,
                self.event_id,
                participant_id,
                self.directory_ids["B1G Davao"],
                updated_by_user_id=self.user_id,
            )
            db.commit()
        protected_values = self._assignment_values(participant_id)

        with self.app.app_context():
            db = get_db()
            sync_plan = analyze_event_satellite_sync(db, self.event_id)
            sync_result = execute_event_satellite_sync(db, self.event_id)
            db.commit()
        self.assertEqual(MANUAL_PROTECTED, sync_plan["registrations"][0]["status"])
        self.assertEqual(0, sync_result["synchronized_count"])
        self.assertEqual(0, sync_result["not_synced_count"])
        self.assertEqual(protected_values, self._assignment_values(participant_id))

        with self.app.app_context():
            db = get_db()
            metrics = canonical_satellite_metrics(db, first_batch_id)
            davao_roster = satellite_registrants(
                db, first_batch_id, self.directory_ids["B1G Davao"]
            )
            tagum_roster = satellite_registrants(
                db, first_batch_id, self.directory_ids["B1G Tagum"]
            )
            curated_id = db.execute(
                "SELECT id FROM curated_registrants WHERE batch_id = ?",
                (first_batch_id,),
            ).fetchone()["id"]
            curated = curated_registrant_detail(db, first_batch_id, curated_id)
        ranking = {item["name"]: item["registrants"] for item in metrics["satellites"]}
        self.assertEqual(1, ranking["B1G Davao"])
        self.assertNotIn("B1G Tagum", ranking)
        self.assertEqual(1, davao_roster["registrants"])
        self.assertIsNone(tagum_roster)
        self.assertEqual("B1G Davao", curated["effective_satellites"][0]["name"])
        self.assertEqual("manual", curated["effective_satellites"][0]["assignment_source"])

        expected_imports = (
            ("B1G Tagum", "source-2"),
            ("B1G General Santos", "source-3"),
            ("B1G Tagum", "source-4"),
        )
        for imported_satellite, source_id in expected_imports:
            with self.subTest(imported_satellite=imported_satellite, source_id=source_id):
                batch_id = self._process(imported_satellite, source_id)
                self.assertEqual(protected_values, self._assignment_values(participant_id))
                with self.app.app_context():
                    db = get_db()
                    current_participant_id = db.execute(
                        """
                        SELECT attestation_participant_id
                        FROM attestation_participant_registrants
                        WHERE event_id = ? AND batch_id = ?
                        """,
                        (self.event_id, batch_id),
                    ).fetchone()["attestation_participant_id"]
                    payload = event_settings_registrants(db, self.event_id)
                    assignment_count = db.execute(
                        """
                        SELECT COUNT(*) count FROM event_registrant_satellites
                        WHERE event_id = ? AND attestation_participant_id = ?
                        """,
                        (self.event_id, participant_id),
                    ).fetchone()["count"]

                self.assertEqual(participant_id, current_participant_id)
                self.assertEqual(1, assignment_count)
                self.assertEqual(imported_satellite, payload["rows"][0]["imported_satellite"])
                self.assertEqual("B1G Davao", payload["rows"][0]["effective_satellite"])
                self.assertEqual("manual", payload["rows"][0]["assignment_source"])
                self.assertEqual(
                    "satellite-operator", payload["rows"][0]["assignment_updated_by"]
                )

        with self.app.app_context():
            evidence = get_db().execute(
                """
                SELECT record.source_id, record.satellite_name, batch.status
                FROM registrants record
                JOIN import_batches batch ON batch.id = record.batch_id
                WHERE batch.event_id = ?
                ORDER BY batch.id
                """,
                (self.event_id,),
            ).fetchall()
        self.assertEqual(
            ["source-1", "source-2", "source-3", "source-4"],
            [row["source_id"] for row in evidence],
        )
        self.assertEqual(
            ["B1G Tagum", "B1G Tagum", "B1G General Santos", "B1G Tagum"],
            [row["satellite_name"] for row in evidence],
        )
        self.assertEqual(1, sum(row["status"] == "active" for row in evidence))


if __name__ == "__main__":
    unittest.main()
