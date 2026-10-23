import csv
import json
import unittest
from unittest.mock import patch

from app.db import get_db
from app.importer import activate_batch
from app.transportation import (
    TransportationConflict, TransportationError, resolve_transportation,
    transportation_history, update_transportation,
)
from tests import test_phase1 as fixtures


class TransportationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.EventIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.event = self.fixture.event_a
        self._source("Bus to MMRC", "Carpool")
        self.batch = self.fixture._process(self.event)
        self.context = self.fixture.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.db = get_db()
        self.person = self.db.execute(
            """SELECT link.attestation_participant_id FROM attestation_participant_registrants link
               JOIN registrants r ON r.id = link.registrant_id
               WHERE link.event_id = ? AND link.batch_id = ? AND r.registration_code = 'R-1'""",
            (self.event, self.batch),
        ).fetchone()["attestation_participant_id"]
        self.user = self.db.execute(
            """INSERT INTO users (username, password_hash, role, status, approved_at)
               VALUES ('travel-operator', 'unused', 'user', 'approved', CURRENT_TIMESTAMP)"""
        ).lastrowid
        self.db.commit()

    def _source(self, outbound, inbound):
        path = self.fixture.paths["registrants"]
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        for name, value in (("Transportation From Ccf To Mmrc", outbound),
                            ("Transportation From Mmrc To Ccf", inbound)):
            if name not in fields:
                fields.append(name)
            rows[0][name] = value
        fixtures.write_csv(path, fields, rows)

    def state(self):
        return resolve_transportation(self.db, self.event, self.person)

    def save(self, changes, **kwargs):
        state = self.state()
        options = dict(changed_by_user_id=self.user, expected_batch_id=state["active_batch_id"],
                       expected_revisions={d: state["trips"][d]["revision"] for d in changes})
        options.update(kwargs)
        return update_transportation(self.db, self.event, self.person, changes, **options)

    def history(self):
        return transportation_history(self.db, self.event, self.person)

    def test_independent_trips_explicit_unreported_noops_and_reset(self):
        before_source = self.db.execute("SELECT source_data_json FROM registrants ORDER BY id").fetchall()
        self.assertEqual([], self.save({"to_mmrc": "bus", "from_mmrc": None})["changed"])
        self.save({"to_mmrc": "unreported", "from_mmrc": "public_transportation"}, reason="Travel plans changed")
        self.db.commit()
        self.assertEqual("unreported", self.state()["trips"]["to_mmrc"]["mode"])
        self.assertEqual("manual", self.state()["trips"]["to_mmrc"]["source"])
        self.assertEqual(2, len(self.history()))
        self.assertEqual("travel-operator", self.history()[0]["changed_by_username"])
        self.assertEqual("Travel plans changed", self.history()[0]["reason"])
        self.assertEqual([], self.save({"to_mmrc": "unreported"})["changed"])
        self.save({"to_mmrc": None})
        self.db.commit()
        self.assertEqual("bus", self.state()["trips"]["to_mmrc"]["mode"])
        self.assertEqual("public_transportation", self.state()["trips"]["from_mmrc"]["mode"])
        self.assertEqual("reset", self.history()[0]["action"])
        self.assertEqual("unreported", self.history()[0]["previous_value"]["mode"])
        self.assertEqual("bus", self.history()[0]["new_value"]["mode"])
        self.assertEqual(3, len(self.history()))
        self.assertEqual(before_source, self.db.execute("SELECT source_data_json FROM registrants ORDER BY id").fetchall())

    def test_reimport_activation_and_batch_deletion_preserve_manual_and_history(self):
        self.save({"to_mmrc": "carpool"})
        self.db.commit()
        history_before = self.history()
        self._source("Public Transportation", "Bus to CCF")
        replacement = self.fixture._process(self.event)
        self.assertEqual(replacement, self.state()["active_batch_id"])
        self.assertEqual("carpool", self.state()["trips"]["to_mmrc"]["mode"])
        self.assertEqual("public_transportation", self.state()["trips"]["to_mmrc"]["imported_mode"])
        self.assertEqual("bus", self.state()["trips"]["from_mmrc"]["mode"])
        activate_batch(self.db, self.event, self.batch)
        self.assertEqual("carpool", self.state()["trips"]["to_mmrc"]["mode"])
        self.assertEqual("carpool", self.state()["trips"]["from_mmrc"]["mode"])
        activate_batch(self.db, self.event, replacement)
        self.db.execute("DELETE FROM import_batches WHERE id = ?", (self.batch,))
        self.db.commit()
        self.assertEqual(history_before, self.history())
        self.save({"to_mmrc": None})
        self.db.commit()
        self.assertEqual("public_transportation", self.state()["trips"]["to_mmrc"]["mode"])

    def test_stale_revision_batch_and_wrong_event_rejected(self):
        self.save({"to_mmrc": "carpool"})
        self.db.commit()
        with self.assertRaises(TransportationConflict):
            self.save({"to_mmrc": "bus"}, expected_revisions={"to_mmrc": 0})
        with self.assertRaises(TransportationConflict):
            self.save({"from_mmrc": "bus"}, expected_batch_id=999999)
        with self.assertRaises(TransportationError):
            resolve_transportation(self.db, self.fixture.event_b, self.person)
        with self.assertRaises(TransportationError):
            update_transportation(self.db, self.fixture.event_b, self.person, {"to_mmrc": "bus"},
                                  changed_by_user_id=self.user, expected_batch_id=self.batch,
                                  expected_revisions={"to_mmrc": 0})
        self.assertEqual(1, len(self.history()))

    def test_invalid_input_and_operator_do_not_write(self):
        for changes, extra in [({"invalid": "bus"}, {}), ({"to_mmrc": "taxi"}, {}),
                               ({"to_mmrc": "carpool"}, {"reason": "x" * 2001}),
                               ({"to_mmrc": "carpool"}, {"changed_by_user_id": 999999})]:
            with self.subTest(changes=changes, extra=list(extra)):
                with self.assertRaises(TransportationError):
                    update_transportation(self.db, self.event, self.person, changes,
                                          expected_batch_id=self.batch, expected_revisions={"to_mmrc": 0},
                                          **dict({"changed_by_user_id": self.user}, **extra))
        for status, role in [("blocked", "user"), ("pending", "user"), ("approved", "registration")]:
            self.db.execute("""UPDATE users SET status = ?, role = ?,
                            approved_at = CASE WHEN ? = 'pending' THEN NULL ELSE CURRENT_TIMESTAMP END
                            WHERE id = ?""", (status, role, status, self.user))
            with self.assertRaises(TransportationError):
                self.save({"to_mmrc": "carpool"})
        self.assertEqual([], self.history())

    def test_audit_failure_rolls_back_both_trips_even_if_caller_commits(self):
        original = self.db.execute
        audit_count = 0

        def fail_second_audit(sql, params=None):
            nonlocal audit_count
            if "INSERT INTO participant_transportation_history" in sql:
                audit_count += 1
                if audit_count == 2:
                    raise RuntimeError("Simulated audit storage failure")
            return original(sql, params)

        with patch.object(self.db, "execute", side_effect=fail_second_audit):
            with self.assertRaises(RuntimeError):
                self.save({"to_mmrc": "carpool", "from_mmrc": "bus"})
        self.db.commit()
        self.assertEqual([], self.history())
        self.assertEqual("bus", self.state()["trips"]["to_mmrc"]["mode"])
        self.assertEqual("carpool", self.state()["trips"]["from_mmrc"]["mode"])

    def test_caller_rollback_and_operator_snapshot_retention(self):
        self.save({"to_mmrc": "carpool"})
        self.db.rollback()
        self.assertEqual([], self.history())
        self.save({"to_mmrc": "carpool"})
        self.db.commit()
        self.db.execute("UPDATE users SET username = 'renamed' WHERE id = ?", (self.user,))
        self.db.execute("DELETE FROM users WHERE id = ?", (self.user,))
        self.db.commit()
        self.assertEqual("travel-operator", self.history()[0]["changed_by_username"])
        self.assertIsNone(self.history()[0]["changed_by_user_id"])
        self.assertEqual("carpool", self.state()["trips"]["to_mmrc"]["mode"])

    def test_import_alias_conflict_missing_and_other_are_preserved(self):
        row = self.db.execute("SELECT id, source_data_json FROM registrants WHERE batch_id = ? AND registration_code = 'R-1'", (self.batch,)).fetchone()
        answers = json.loads(row["source_data_json"])
        answers.update({"Transportation To MMRC": "Carpool", "Transportation From Mmrc To Ccf": "Own vehicle"})
        self.db.execute("UPDATE registrants SET source_data_json = ? WHERE id = ?", (json.dumps(answers), row["id"]))
        self.assertEqual("conflicting", self.state()["trips"]["to_mmrc"]["mode"])
        self.assertEqual("other", self.state()["trips"]["from_mmrc"]["mode"])
        self.save({"to_mmrc": "bus"})
        self.assertEqual("conflicting", self.history()[0]["previous_value"]["mode"])
        self.save({"to_mmrc": None})
        self.assertEqual("conflicting", self.state()["trips"]["to_mmrc"]["mode"])
        answers.update({"Transportation From Ccf To Mmrc": "", "Transportation To MMRC": ""})
        self.db.execute("UPDATE registrants SET source_data_json = ? WHERE id = ?", (json.dumps(answers), row["id"]))
        self.assertEqual("unreported", self.state()["trips"]["to_mmrc"]["mode"])

    def test_absent_participant_retains_state_but_cannot_be_edited(self):
        self.save({"to_mmrc": "carpool"})
        self.db.commit()
        self.db.execute("UPDATE import_batches SET status = 'inactive', active_event_id = NULL WHERE id = ?", (self.batch,))
        self.db.commit()
        self.assertFalse(self.state()["present_in_active_batch"])
        self.assertEqual("carpool", self.state()["trips"]["to_mmrc"]["mode"])
        with self.assertRaises(TransportationConflict):
            self.save({"to_mmrc": None})
        self.assertEqual(1, len(self.history()))

    def test_duplicate_sources_resolve_once_and_keep_conflicting_evidence(self):
        second = self.db.execute("SELECT id FROM registrants WHERE batch_id = ? AND registration_code = 'R-2'", (self.batch,)).fetchone()["id"]
        self.db.execute("""UPDATE attestation_participant_registrants
                           SET attestation_participant_id = ? WHERE event_id = ? AND registrant_id = ?""",
                        (self.person, self.event, second))
        self.db.execute("UPDATE registrants SET source_data_json = ? WHERE id = ?",
                        (json.dumps({"Transportation To MMRC": "Bus to MMRC"}), second))
        self.assertEqual("bus", self.state()["trips"]["to_mmrc"]["mode"])
        self.db.execute("UPDATE registrants SET source_data_json = ? WHERE id = ?",
                        (json.dumps({"Transportation To MMRC": "Carpool"}), second))
        self.assertEqual("conflicting", self.state()["trips"]["to_mmrc"]["mode"])
        self.save({"to_mmrc": "other"})
        self.db.commit()
        self.assertEqual(1, len(self.history()))
        self.assertEqual(["Bus to MMRC", "Carpool"], self.history()[0]["previous_value"]["imported_values"])

    def test_history_pagination_and_reset_revision_remains_monotonic(self):
        self.save({"to_mmrc": "carpool"})
        self.save({"to_mmrc": None})
        self.save({"to_mmrc": "other"})
        self.db.commit()
        newest = transportation_history(self.db, self.event, self.person, limit=1)
        older = transportation_history(self.db, self.event, self.person, before_id=newest[0]["id"])
        self.assertEqual([3, 2, 1], [h["revision"] for h in newest + older])
        self.assertEqual(3, self.state()["trips"]["to_mmrc"]["revision"])
