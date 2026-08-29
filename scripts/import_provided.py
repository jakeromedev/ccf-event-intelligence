#!/usr/bin/env python3
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from app.aggregation import data_quality, overview_metrics, satellite_metrics
from app.db import get_db
from app.importer import process_batch, store_validation, validate_batch


FILES = {
    "tickets": ROOT / "Aug20_26_0426PM_event_generated_tickets.csv",
    "buyers": ROOT / "Aug20_26_0427PM_event_buyers.csv",
    "registrants": ROOT / "Aug20_26_0432PM_event_registrants.csv",
}


def json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError("Object of type {} is not JSON serializable".format(type(value).__name__))


def main():
    missing = [str(path) for path in FILES.values() if not path.exists()]
    if missing:
        raise SystemExit("Missing provided export(s): {}".format(", ".join(missing)))

    app = create_app()
    with app.app_context():
        staged = {
            export_type: (str(path), path.name)
            for export_type, path in FILES.items()
        }
        validation = validate_batch(staged)
        event = get_db().execute(
            "SELECT id FROM events WHERE name = ? ORDER BY id LIMIT 1",
            (validation.event_name or "Imported Event",),
        ).fetchone()
        if event:
            event_id = event["id"]
        else:
            cursor = get_db().execute(
                "INSERT INTO events (name) VALUES (?)",
                (validation.event_name or "Imported Event",),
            )
            event_id = cursor.lastrowid
            get_db().commit()
        batch_id = store_validation(get_db(), validation, event_id)
        if not validation.valid:
            raise SystemExit("Provided export set failed validation; batch #{} was not activated.".format(batch_id))
        process_batch(get_db(), batch_id)
        overview = overview_metrics(get_db(), batch_id)
        checked = overview_metrics(get_db(), batch_id, "checked-in")
        satellites = satellite_metrics(get_db(), batch_id)
        quality = data_quality(get_db(), batch_id)
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "event_id": event_id,
                    "overview": overview,
                    "checked_in_affiliation": checked["affiliation"],
                    "satellites": {key: value for key, value in satellites.items() if key != "ranking"},
                    "quality": {item["category"]: item["count"] for item in quality["cards"]},
                },
                indent=2,
                default=json_default,
            )
        )


if __name__ == "__main__":
    main()
