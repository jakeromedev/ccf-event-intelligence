"""Print and verify the authoritative Phase 1 metrics for one Event.

Usage:
    .venv/bin/python scripts/reconcile_phase1.py EVENT_ID
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.aggregation import curation_quality, event_dashboard_metrics  # noqa: E402
from app.db import get_db  # noqa: E402


def reconciliation_report(dashboard, curation=None):
    profile = dashboard["participant_profile"]
    return {
        "event": dashboard["event"],
        "active_batch_id": dashboard["active_batch_id"],
        "overview": dashboard["overview"],
        "gender": {
            item["label"]: item["count"] for item in profile["gender"]["items"]
        },
        "life_stage": {
            item["label"]: item["count"] for item in profile["life_stage"]["items"]
        },
        "age_distribution": {
            item["label"]: item["count"] for item in profile["age"]["items"]
        },
        "reconciliation": dashboard["reconciliation"],
        "curation_quality": curation,
    }


def json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError("Unsupported report value: {}".format(type(value).__name__))


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile event-scoped Phase 1 dashboard metrics."
    )
    parser.add_argument("event_id", type=int)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        dashboard = event_dashboard_metrics(get_db(), args.event_id)
        curation = (
            curation_quality(get_db(), dashboard["active_batch_id"])["summary"]
            if dashboard and dashboard["active_batch_id"]
            else None
        )
    if dashboard is None:
        parser.error("Event {} does not exist.".format(args.event_id))

    report = reconciliation_report(dashboard, curation)
    print(json.dumps(report, indent=2, sort_keys=True, default=json_value))
    if not all(report["reconciliation"].values()):
        print("Phase 1 reconciliation failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
