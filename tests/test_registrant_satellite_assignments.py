import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, event as sqlalchemy_event
from sqlalchemy.orm import Session

from app.db import Database
from app.models import Base
from app.registrant_satellite_assignments import (
    AUTOMATIC_ASSIGNMENT,
    MANUAL_ASSIGNMENT,
    RegistrantSatelliteAssignmentError,
    reset_manual_satellite_assignment,
    resolve_effective_satellite_assignment,
    set_manual_satellite_assignment,
)


class RegistrantSatelliteAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        database_path = Path(self.temp.name) / "assignments.sqlite3"
        self.engine = create_engine("sqlite+pysqlite:///{}".format(database_path))
        sqlalchemy_event.listen(
            self.engine,
            "connect",
            lambda connection, _record: connection.execute("PRAGMA foreign_keys = ON"),
        )
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.db = Database(self.session)
        self.event_id = self.db.execute(
            "INSERT INTO events (name) VALUES ('Assignment Event')"
        ).lastrowid
        self.participant_id = self.db.execute(
            "INSERT INTO attestation_participants (event_id) VALUES (?)",
            (self.event_id,),
        ).lastrowid
        group_id = self.db.execute(
            """
            INSERT INTO hub_groups (code, name, sort_order)
            VALUES ('outside_metro_manila', 'Outside Metro Manila Hubs', 1)
            """
        ).lastrowid
        hub_id = self.db.execute(
            """
            INSERT INTO satellite_hubs (hub_group_id, name, normalized_name)
            VALUES (?, 'Mindanao South', 'mindanao south')
            """,
            (group_id,),
        ).lastrowid
        self.imported_directory_id = self.db.execute(
            """
            INSERT INTO satellite_directory (hub_id, name, normalized_name)
            VALUES (?, 'B1G Tagum', 'b1g tagum')
            """,
            (hub_id,),
        ).lastrowid
        self.manual_directory_id = self.db.execute(
            """
            INSERT INTO satellite_directory (hub_id, name, normalized_name)
            VALUES (?, 'B1G Davao', 'b1g davao')
            """,
            (hub_id,),
        ).lastrowid
        self.db.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_effective_resolution_is_manual_then_automatic_then_unassigned(self):
        unassigned = resolve_effective_satellite_assignment(
            self.db, self.event_id, self.participant_id
        )
        self.assertIsNone(unassigned["directory_id"])
        self.assertIsNone(unassigned["assignment_source"])

        automatic = resolve_effective_satellite_assignment(
            self.db,
            self.event_id,
            self.participant_id,
            automatic_directory_id=self.imported_directory_id,
            automatic_source_batch_id=91,
        )
        self.assertEqual(self.imported_directory_id, automatic["directory_id"])
        self.assertEqual(AUTOMATIC_ASSIGNMENT, automatic["assignment_source"])
        self.assertEqual(91, automatic["source_batch_id"])
        self.assertFalse(automatic["is_manual"])

        assignment_id = self.db.execute(
            """
            INSERT INTO event_registrant_satellites (
                event_id, attestation_participant_id, directory_id,
                assignment_source
            ) VALUES (?, ?, ?, 'manual')
            """,
            (self.event_id, self.participant_id, self.manual_directory_id),
        ).lastrowid
        self.db.commit()
        manual = resolve_effective_satellite_assignment(
            self.db,
            self.event_id,
            self.participant_id,
            automatic_directory_id=self.imported_directory_id,
            automatic_source_batch_id=91,
        )
        self.assertEqual(assignment_id, manual["assignment_id"])
        self.assertEqual(self.manual_directory_id, manual["directory_id"])
        self.assertEqual(MANUAL_ASSIGNMENT, manual["assignment_source"])
        self.assertEqual("B1G Davao", manual["satellite_name"])
        self.assertIsNone(manual["source_batch_id"])
        self.assertTrue(manual["is_manual"])

        other_event_id = self.db.execute(
            "INSERT INTO events (name) VALUES ('Other Assignment Event')"
        ).lastrowid
        wrong_event = resolve_effective_satellite_assignment(
            self.db,
            other_event_id,
            self.participant_id,
            automatic_directory_id=self.imported_directory_id,
        )
        self.assertIsNone(wrong_event["directory_id"])

    def test_stored_automatic_assignment_is_available_without_a_batch_candidate(self):
        batch_id = self.db.execute(
            """
            INSERT INTO import_batches (event_id, status)
            VALUES (?, 'inactive')
            """,
            (self.event_id,),
        ).lastrowid
        assignment_id = self.db.execute(
            """
            INSERT INTO event_registrant_satellites (
                event_id, attestation_participant_id, directory_id,
                assignment_source, source_batch_id
            ) VALUES (?, ?, ?, 'automatic', ?)
            """,
            (
                self.event_id,
                self.participant_id,
                self.imported_directory_id,
                batch_id,
            ),
        ).lastrowid
        self.db.commit()

        assignment = resolve_effective_satellite_assignment(
            self.db, self.event_id, self.participant_id
        )
        self.assertEqual(assignment_id, assignment["assignment_id"])
        self.assertEqual(AUTOMATIC_ASSIGNMENT, assignment["assignment_source"])
        self.assertEqual(batch_id, assignment["source_batch_id"])

    def test_manual_assignment_is_an_idempotent_upsert(self):
        created = set_manual_satellite_assignment(
            self.db,
            self.event_id,
            self.participant_id,
            self.imported_directory_id,
        )
        updated = set_manual_satellite_assignment(
            self.db,
            self.event_id,
            self.participant_id,
            self.manual_directory_id,
        )
        duplicate = set_manual_satellite_assignment(
            self.db,
            self.event_id,
            self.participant_id,
            self.manual_directory_id,
        )
        self.db.commit()

        assignment = self.db.execute(
            """
            SELECT id, directory_id, assignment_source, source_batch_id
            FROM event_registrant_satellites
            WHERE event_id = ? AND attestation_participant_id = ?
            """,
            (self.event_id, self.participant_id),
        ).fetchone()
        count = self.db.execute(
            "SELECT COUNT(*) count FROM event_registrant_satellites"
        ).fetchone()["count"]

        self.assertEqual(created["assignment_id"], updated["assignment_id"])
        self.assertFalse(duplicate["changed"])
        self.assertEqual(1, count)
        self.assertEqual(self.manual_directory_id, assignment["directory_id"])
        self.assertEqual(MANUAL_ASSIGNMENT, assignment["assignment_source"])
        self.assertIsNone(assignment["source_batch_id"])
        audit_count = self.db.execute(
            """
            SELECT COUNT(*) count FROM event_registrant_satellite_audits
            WHERE event_id = ? AND attestation_participant_id = ?
            """,
            (self.event_id, self.participant_id),
        ).fetchone()["count"]
        self.assertEqual(2, audit_count)

    def test_reset_without_valid_latest_import_becomes_unassigned_and_is_idempotent(self):
        set_manual_satellite_assignment(
            self.db,
            self.event_id,
            self.participant_id,
            self.manual_directory_id,
        )
        first = reset_manual_satellite_assignment(
            self.db, self.event_id, self.participant_id
        )
        duplicate = reset_manual_satellite_assignment(
            self.db, self.event_id, self.participant_id
        )
        self.db.commit()

        assignment_count = self.db.execute(
            "SELECT COUNT(*) count FROM event_registrant_satellites"
        ).fetchone()["count"]
        audits = self.db.execute(
            """
            SELECT action, previous_directory_name, new_directory_name
            FROM event_registrant_satellite_audits ORDER BY id
            """
        ).fetchall()
        self.assertTrue(first["changed"])
        self.assertIsNone(first["assignment_source"])
        self.assertFalse(duplicate["changed"])
        self.assertEqual(0, assignment_count)
        self.assertEqual(["manual", "reset"], [row["action"] for row in audits])
        self.assertEqual("B1G Davao", audits[-1]["previous_directory_name"])
        self.assertIsNone(audits[-1]["new_directory_name"])

    def test_manual_assignment_rejects_cross_event_or_unconfigured_targets(self):
        other_event_id = self.db.execute(
            "INSERT INTO events (name) VALUES ('Other Event')"
        ).lastrowid
        unattached_directory_id = self.db.execute(
            """
            INSERT INTO satellite_directory (name, normalized_name)
            VALUES ('Legacy Satellite', 'legacy satellite')
            """
        ).lastrowid

        with self.assertRaises(RegistrantSatelliteAssignmentError):
            set_manual_satellite_assignment(
                self.db,
                other_event_id,
                self.participant_id,
                self.manual_directory_id,
            )
        with self.assertRaises(RegistrantSatelliteAssignmentError):
            set_manual_satellite_assignment(
                self.db,
                self.event_id,
                self.participant_id,
                unattached_directory_id,
            )


if __name__ == "__main__":
    unittest.main()
