"""Authenticated transportation management, using the active event import."""

import json
import math
from collections import defaultdict

from flask import Blueprint, abort, current_app, flash, jsonify, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from .aggregation import active_batch
from .auth import can_manage_transportation
from .db import get_db
from .time_utils import format_operational_datetime
from .transportation import (
    DIRECTIONS, TransportationConflict, TransportationError,
    resolve_transportation, resolve_trip_values, update_transportation, transportation_history,
)


bp = Blueprint("transportation", __name__)
MODE_LABELS = {
    "bus": "Bus", "carpool": "Carpool", "public_transportation": "Public Transportation",
    "other": "Other", "unreported": "Not reported", "conflicting": "Conflicting answers",
}
TRIP_LABELS = {"to_mmrc": "CCF → MMRC", "from_mmrc": "MMRC → CCF"}


@bp.before_request
def require_access():
    if not can_manage_transportation():
        abort(403)


@bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _event(event_id):
    event = get_db().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        abort(404)
    return event


def _person_sources(db, event_id, batch_id, participant_id=None):
    if batch_id is None:
        return []
    return db.execute(
        """SELECT link.attestation_participant_id participant_id,
                  r.first_name, r.last_name, r.registration_code, r.source_data_json,
                  COALESCE(directory.name, r.satellite_name) satellite_name
           FROM attestation_participant_registrants link
           JOIN registrants r ON r.id = link.registrant_id AND r.batch_id = link.batch_id
           LEFT JOIN event_registrant_satellites assignment
             ON assignment.event_id = link.event_id
            AND assignment.attestation_participant_id = link.attestation_participant_id
            AND assignment.assignment_source = 'manual'
           LEFT JOIN satellite_directory directory ON directory.id = assignment.directory_id
           WHERE link.event_id = ? AND link.batch_id = ?"""
        + (" AND link.attestation_participant_id = ?" if participant_id is not None else "")
        + " ORDER BY r.id",
        (event_id, batch_id) + ((participant_id,) if participant_id is not None else ()),
    ).fetchall()


def _identity(sources):
    names, emails, codes, satellites = set(), set(), set(), set()
    for row in sources:
        name = " ".join(part.strip() for part in (row["first_name"] or "", row["last_name"] or "") if part.strip())
        if name:
            names.add(name)
        source = json.loads(row["source_data_json"] or "{}")
        email = str(source.get("Email Address") or "").strip()
        if email:
            emails.add(email)
        codes.add(row["registration_code"])
        if row["satellite_name"]:
            satellites.add(row["satellite_name"])
    return dict(name=" / ".join(sorted(names)) or "Name not reported",
                email=" / ".join(sorted(emails)), codes=" / ".join(sorted(codes)),
                satellite=" / ".join(sorted(satellites)) or "Not reported")


def transportation_roster(db, event_id, batch_id):
    """Bulk read: one row per durable participant, without per-person queries."""
    grouped = defaultdict(list)
    for row in _person_sources(db, event_id, batch_id):
        grouped[row["participant_id"]].append(row)
    if not grouped:
        return []
    overrides = defaultdict(list)
    for row in db.execute(
        "SELECT * FROM participant_transportation WHERE event_id = ?", (event_id,),
    ).fetchall():
        overrides[row["attestation_participant_id"]].append(row)
    latest = {row["attestation_participant_id"]: row for row in db.execute(
        """SELECT history.attestation_participant_id, history.changed_by_username, history.created_at
           FROM participant_transportation_history history
           JOIN (SELECT attestation_participant_id, MAX(id) latest_id
                 FROM participant_transportation_history WHERE event_id = ?
                 GROUP BY attestation_participant_id) newest ON newest.latest_id = history.id""",
        (event_id,),
    ).fetchall()}
    people = []
    for participant_id, sources in grouped.items():
        audit = latest.get(participant_id)
        people.append(dict(
            participant_id=participant_id, **_identity(sources),
            trips=resolve_trip_values(sources, overrides[participant_id]),
            updated_at=format_operational_datetime(audit["created_at"]) if audit else None,
            updated_by=audit["changed_by_username"] if audit else None,
        ))
    return sorted(people, key=lambda person: (person["name"].casefold(), person["participant_id"]))


@bp.get("/events/<int:event_id>/transportation")
def manage(event_id):
    event = _event(event_id)
    batch = active_batch(get_db(), event_id)
    query = request.args.get("q", "").strip()[:100]
    direction = request.args.get("direction", "all")
    mode = request.args.get("mode", "all")
    source = request.args.get("source", "all")
    if direction not in ("all", *DIRECTIONS) or mode not in ("all", *MODE_LABELS) or source not in ("all", "manual", "imported"):
        abort(400, "Invalid transportation filter.")
    try:
        per_page = int(request.args.get("per_page", 25))
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        abort(400, "Invalid page size or number.")
    if per_page not in (25, 50, 100):
        abort(400, "Invalid page size.")
    rows = transportation_roster(get_db(), event_id, batch["id"] if batch else None)
    population = len(rows)
    directions = DIRECTIONS if direction == "all" else (direction,)
    rows = [row for row in rows if (
        not query or query.casefold() in " ".join(row[key] for key in ("name", "email", "codes", "satellite")).casefold()
    ) and any(
        (mode == "all" or row["trips"][trip]["mode"] == mode)
        and (source == "all" or row["trips"][trip]["source"] == source)
        for trip in directions
    )]
    total = len(rows)
    pages = max(1, math.ceil(total / per_page))
    page = min(page, pages)
    params = dict(q=query, direction=direction, mode=mode, source=source, per_page=per_page)
    return render_template(
        "transportation.html", event=event, active_batch=batch,
        rows=rows[(page - 1) * per_page:page * per_page], population=population, total=total,
        page=page, pages=pages, query=query, direction=direction, mode=mode, source=source,
        per_page=per_page, mode_labels=MODE_LABELS, trip_labels=TRIP_LABELS,
        previous_url=url_for("transportation.manage", event_id=event_id, page=page-1, **params) if page > 1 else None,
        next_url=url_for("transportation.manage", event_id=event_id, page=page+1, **params) if page < pages else None,
        filtered=bool(query or direction != "all" or mode != "all" or source != "all"),
    )


@bp.route("/events/<int:event_id>/transportation/<int:participant_id>", methods=("GET", "POST"))
def participant(event_id, participant_id):
    _event(event_id)
    db = get_db()
    batch = active_batch(db, event_id)
    sources = _person_sources(db, event_id, batch["id"] if batch else None, participant_id)
    if not sources:
        abort(404)
    if request.method == "GET":
        return jsonify(**_identity(sources), **resolve_transportation(db, event_id, participant_id))
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or type(payload.get("expected_batch_id")) is not int:
        return jsonify(error="Provide the current trip selections and import version."), 400
    try:
        result = update_transportation(
            db, event_id, participant_id, payload.get("changes"),
            changed_by_user_id=current_user.id,
            expected_batch_id=payload["expected_batch_id"],
            expected_revisions=payload.get("expected_revisions"), reason=payload.get("reason"),
        )
        db.commit()
    except TransportationConflict as exc:
        db.rollback()
        return jsonify(error=str(exc)), 409
    except TransportationError as exc:
        db.rollback()
        return jsonify(error=str(exc)), 400
    except SQLAlchemyError:
        db.rollback()
        current_app.logger.error("transportation_update_failed")
        return jsonify(error="The update could not be saved. Reload the current values before trying again."), 500
    flash("Transportation updated." if result["changed"] else "No transportation changes were needed.", "success")
    return jsonify(changed=result["changed"])


@bp.get("/events/<int:event_id>/transportation/<int:participant_id>/history")
def history(event_id, participant_id):
    event = _event(event_id)
    db = get_db()
    if not db.execute(
        "SELECT id FROM attestation_participants WHERE event_id = ? AND id = ?",
        (event_id, participant_id),
    ).fetchone():
        abort(404)
    cursor = request.args.get("before_id")
    try:
        cursor = int(cursor) if cursor is not None else None
        entries = transportation_history(db, event_id, participant_id, limit=51, before_id=cursor)
    except (ValueError, TransportationError):
        abort(400, "Invalid history cursor.")
    more = len(entries) > 50
    entries = entries[:50]
    for entry in entries:
        entry["display_time"] = format_operational_datetime(entry["created_at"])
    batch = active_batch(db, event_id)
    sources = _person_sources(db, event_id, batch["id"] if batch else None, participant_id)
    return render_template(
        "transportation_history.html", event=event,
        person=_identity(sources) if sources else None, participant_id=participant_id,
        entries=entries, mode_labels=MODE_LABELS, trip_labels=TRIP_LABELS,
        older_url=url_for("transportation.history", event_id=event_id, participant_id=participant_id,
                          before_id=entries[-1]["id"]) if more else None,
        newest_url=url_for("transportation.history", event_id=event_id, participant_id=participant_id) if cursor else None,
    )
