import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config


class FacebookGroupOutreachMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_tags_and_allows_repeated_outreach(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DATABASE_URL": ""}):
            path = Path(directory) / "migration.sqlite3"
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{path}")
            command.upgrade(config, "b9f2d5a7c310")
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO events (id, name) VALUES (1, 'Event')")
                db.execute("INSERT INTO attestation_participants (id, event_id) VALUES (1, 1)")
                db.execute("""INSERT INTO registrant_facebook_group_memberships
                    (event_id, attestation_participant_id, joined) VALUES (1, 1, 1)""")
            command.upgrade(config, "head")
            with sqlite3.connect(path) as db:
                self.assertEqual((1, 0), db.execute(
                    "SELECT joined, reached_out FROM registrant_facebook_group_memberships"
                ).fetchone())
                for _ in range(2):
                    db.execute("""INSERT INTO registrant_facebook_group_outreach
                        (event_id, attestation_participant_id) VALUES (1, 1)""")
                self.assertEqual(2, db.execute(
                    "SELECT COUNT(*) FROM registrant_facebook_group_outreach WHERE created_at IS NOT NULL"
                ).fetchone()[0])
            command.downgrade(config, "b9f2d5a7c310")
            with sqlite3.connect(path) as db:
                self.assertEqual((1,), db.execute(
                    "SELECT joined FROM registrant_facebook_group_memberships"
                ).fetchone())
