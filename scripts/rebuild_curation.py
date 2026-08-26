#!/usr/bin/env python3
"""Rebuild derived registrant/satellite curation for historical batches."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from app.curation import rebuild_batch_curation
from app.db import get_db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--batch-id", type=int, help="Rebuild one import batch.")
    group.add_argument("--event-id", type=int, help="Rebuild all processed batches for one Event.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        db = get_db()
        if args.batch_id:
            batch_ids = [args.batch_id]
        else:
            batch_ids = [
                row["id"]
                for row in db.execute(
                    """
                    SELECT id FROM import_batches
                    WHERE event_id = ? AND status IN ('active', 'inactive')
                    ORDER BY id
                    """,
                    (args.event_id,),
                ).fetchall()
            ]
        if not batch_ids:
            raise SystemExit("No eligible import batches were found.")

        results = []
        try:
            for batch_id in batch_ids:
                metrics = rebuild_batch_curation(db, batch_id)
                results.append({"batch_id": batch_id, **metrics})
            db.commit()
        except Exception:
            db.rollback()
            raise
        print(json.dumps({"rebuilt": results}, indent=2))


if __name__ == "__main__":
    main()
