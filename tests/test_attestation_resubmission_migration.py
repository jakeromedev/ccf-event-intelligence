import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config


class AttestationResubmissionMigrationTests(unittest.TestCase):
    def test_migration_preserves_review_decisions_and_supports_new_status(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DATABASE_URL": ""}):
            path = Path(directory) / "migration.sqlite3"
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
            command.upgrade(config, "a8e1c4d9f205")
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO events (id, name) VALUES (1, 'Review Event')")
                db.execute("INSERT INTO attestation_participants (id, event_id) VALUES (1, 1), (2, 1)")
                db.execute("""INSERT INTO attestation_verifications
                           (event_id, attestation_participant_id, status)
                           VALUES (1, 1, 'verified'), (1, 2, 'invalid')""")
            command.upgrade(config, "b9f2d5a7c310")
            with sqlite3.connect(path) as db:
                self.assertEqual([('verified',), ('invalid',)], db.execute(
                    "SELECT status FROM attestation_verifications ORDER BY attestation_participant_id"
                ).fetchall())
                db.execute("""UPDATE attestation_verifications SET status = 'to_verify',
                           form_url = 'https://files.example.com/new.pdf'
                           WHERE attestation_participant_id = 2""")
                db.execute("""INSERT INTO attestation_resubmission_imports
                           (id, event_id, filename, report_json) VALUES (1, 1, 'forms.csv', '{}')""")
                db.execute("""INSERT INTO attestation_resubmissions
                           (event_id, attestation_participant_id, import_id, link_hash, form_url)
                           VALUES (1, 2, 1, 'hash', 'https://files.example.com/new.pdf')""")
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("""INSERT INTO attestation_resubmissions
                               (event_id, attestation_participant_id, import_id, link_hash, form_url)
                               VALUES (1, 2, 1, 'hash', 'https://files.example.com/new.pdf')""")
            command.downgrade(config, "a8e1c4d9f205")
            with sqlite3.connect(path) as db:
                self.assertEqual([('verified',), ('pending',)], db.execute(
                    "SELECT status FROM attestation_verifications ORDER BY attestation_participant_id"
                ).fetchall())
