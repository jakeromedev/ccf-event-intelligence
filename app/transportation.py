"""Durable transportation overrides. Callers commit the encompassing transaction.

Event locking serializes writes with imports; revisions and the active batch
protect edit forms. The page routes live in transportation_pages.py.
"""

import json


DIRECTIONS = ("to_mmrc", "from_mmrc")
MODES = ("bus", "carpool", "public_transportation", "other", "unreported")
IMPORT_HEADERS = {
    "to_mmrc": ("Transportation From Ccf To Mmrc", "Transportation To MMRC"),
    "from_mmrc": ("Transportation From Mmrc To Ccf", "Transportation From MMRC"),
}


class TransportationError(ValueError):
    pass


class TransportationConflict(TransportationError):
    """The active import or edited trip has changed since the form was loaded."""


def _imported_mode(value):
    value = str(value or "").strip().casefold()
    if not value or value in {"n/a", "na", "not reported"}:
        return "unreported"
    if "carpool" in value:
        return "carpool"
    if "bus" in value:
        return "bus"
    if "public transportation" in value or "public transport" in value:
        return "public_transportation"
    return "other"


def _participant(db, event_id, participant_id):
    if not db.execute(
        "SELECT id FROM attestation_participants WHERE event_id = ? AND id = ?",
        (event_id, participant_id),
    ).fetchone():
        raise TransportationError("Participant does not belong to this event.")


def resolve_transportation(db, event_id, participant_id):
    """Resolve each trip as manual override > active imported answers.

    Blank duplicate answers are ignored when another source has an answer.
    Different populated modes are retained as a conflict, never picked by order.
    Participants absent from the active import retain manual state but cannot be
    edited until they are linked to the active import again.
    """
    _participant(db, event_id, participant_id)
    batch = db.execute(
        "SELECT id FROM import_batches WHERE event_id = ? AND status = 'active'",
        (event_id,),
    ).fetchone()
    batch_id = batch["id"] if batch else None
    sources = db.execute(
        """SELECT r.source_data_json FROM attestation_participant_registrants link
           JOIN registrants r ON r.id = link.registrant_id AND r.batch_id = link.batch_id
           WHERE link.event_id = ? AND link.attestation_participant_id = ?
             AND link.batch_id = ? ORDER BY r.id""",
        (event_id, participant_id, batch_id),
    ).fetchall() if batch else []
    overrides = db.execute(
        """SELECT direction, mode, revision, updated_by_user_id, updated_at
           FROM participant_transportation
           WHERE event_id = ? AND attestation_participant_id = ?""",
        (event_id, participant_id),
    ).fetchall()
    return {"active_batch_id": batch_id, "present_in_active_batch": bool(sources),
            "trips": resolve_trip_values(sources, overrides)}


def resolve_trip_values(sources, override_rows):
    """Shared single-person resolver for both detail and bulk list queries."""
    imported = {direction: set() for direction in DIRECTIONS}
    for source in sources:
        answers = json.loads(source["source_data_json"] or "{}")
        for direction, headers in IMPORT_HEADERS.items():
            # Retain both populated aliases if they disagree instead of silently
            # allowing a blank/new header to hide the old provider answer.
            for header in headers:
                answer = str(answers.get(header) or "").strip()
                if answer:
                    imported[direction].add(answer)
    overrides = {row["direction"]: row for row in override_rows}
    trips = {}
    for direction in DIRECTIONS:
        raw_values = sorted(imported[direction])
        modes = {_imported_mode(value) for value in raw_values} - {"unreported"}
        imported_mode = next(iter(modes)) if len(modes) == 1 else (
            "conflicting" if modes else "unreported"
        )
        override = overrides.get(direction)
        manual = override["mode"] if override else None
        trips[direction] = {
            "mode": manual if manual is not None else imported_mode,
            "source": "manual" if manual is not None else "imported",
            "imported_mode": imported_mode,
            "imported_values": raw_values,
            "override_mode": manual,
            "revision": override["revision"] if override else 0,
        }
    return trips


def update_transportation(
    db, event_id, participant_id, changes, *, changed_by_user_id,
    expected_batch_id, expected_revisions, reason=None,
):
    """Atomically set/reset one or both trips and append history.

    `changes` maps direction to a supported mode, or None to reset to import.
    `unreported` is an explicit manual choice, distinct from resetting. Saving
    the existing effective mode is a no-op. Never commits unrelated caller work.
    """
    if not isinstance(changes, dict) or not changes or set(changes) - set(DIRECTIONS):
        raise TransportationError("Select one or both valid trip directions.")
    if any(value is not None and value not in MODES for value in changes.values()):
        raise TransportationError("Select a supported transportation mode.")
    if not isinstance(expected_revisions, dict) or any(
        type(expected_revisions.get(direction)) is not int or expected_revisions[direction] < 0
        for direction in changes
    ):
        raise TransportationError("Provide the revision for each edited trip.")
    if reason is not None and not isinstance(reason, str):
        raise TransportationError("The reason must be text.")
    reason = (reason or "").strip() or None
    if reason and len(reason) > 2000:
        raise TransportationError("The reason must be at most 2,000 characters.")

    db.lock_event(event_id)
    if not db.is_mysql:
        # SQLite's legacy driver does not BEGIN on SELECT. Establish the outer
        # transaction before SAVEPOINT so releasing it cannot commit the edit.
        db.execute("UPDATE events SET id = id WHERE id = ?", (event_id,))
    with db.session.begin_nested():
        current = resolve_transportation(db, event_id, participant_id)
        if current["active_batch_id"] != expected_batch_id or not current["present_in_active_batch"]:
            raise TransportationConflict("The active import changed or the participant is absent. Reload the page.")
        actor = db.execute(
            "SELECT username FROM users WHERE id = ? AND status = 'approved' AND role IN ('admin','user')",
            (changed_by_user_id,),
        ).fetchone()
        if actor is None:
            raise TransportationError("An approved administrator or standard user is required.")
        for direction in changes:
            if current["trips"][direction]["revision"] != expected_revisions[direction]:
                raise TransportationConflict("Transportation was updated by another operator. Reload the page.")
        changed = []
        for direction, mode in changes.items():
            previous = current["trips"][direction]
            if (mode is None and previous["override_mode"] is None) or mode == previous["mode"]:
                continue
            revision = previous["revision"] + 1
            new = dict(previous, mode=previous["imported_mode"] if mode is None else mode,
                       source="imported" if mode is None else "manual",
                       override_mode=mode, revision=revision)
            if previous["revision"]:
                db.execute(
                    """UPDATE participant_transportation SET mode = ?, revision = ?,
                       updated_by_user_id = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE event_id = ? AND attestation_participant_id = ? AND direction = ?""",
                    (mode, revision, changed_by_user_id, event_id, participant_id, direction),
                )
            else:
                db.execute(
                    """INSERT INTO participant_transportation
                       (event_id, attestation_participant_id, direction, mode, revision, updated_by_user_id)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (event_id, participant_id, direction, mode, revision, changed_by_user_id),
                )
            db.execute(
                """INSERT INTO participant_transportation_history
                   (event_id, attestation_participant_id, direction, action, revision,
                    previous_value_json, new_value_json, reason, changed_by_user_id, changed_by_username)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, participant_id, direction, "reset" if mode is None else "set", revision,
                 json.dumps(dict(previous, batch_id=expected_batch_id)),
                 json.dumps(dict(new, batch_id=expected_batch_id)), reason,
                 changed_by_user_id, actor["username"]),
            )
            changed.append(direction)
    return {"changed": changed, **resolve_transportation(db, event_id, participant_id)}


def transportation_history(db, event_id, participant_id, *, limit=50, before_id=None):
    """Return bounded, newest-first history; no edit/delete operations exist."""
    _participant(db, event_id, participant_id)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise TransportationError("History limit must be between 1 and 100.")
    if before_id is not None and (type(before_id) is not int or before_id < 1):
        raise TransportationError("Invalid history cursor.")
    rows = db.execute(
        """SELECT * FROM participant_transportation_history
           WHERE event_id = ? AND attestation_participant_id = ?"""
        + (" AND id < ?" if before_id is not None else "") + " ORDER BY id DESC LIMIT ?",
        (event_id, participant_id) + ((before_id,) if before_id is not None else ()) + (limit,),
    ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["previous_value"] = json.loads(item.pop("previous_value_json"))
        item["new_value"] = json.loads(item.pop("new_value_json"))
        results.append(item)
    return results
