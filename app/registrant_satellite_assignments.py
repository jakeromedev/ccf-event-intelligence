"""Registrant-level effective Satellite assignment resolution."""

from __future__ import annotations

from .satellite_sync import ALREADY_SYNCED, READY_TO_SYNC, analyze_event_satellite_sync


AUTOMATIC_ASSIGNMENT = "automatic"
MANUAL_ASSIGNMENT = "manual"


class RegistrantSatelliteAssignmentError(ValueError):
    """Raised when a requested assignment is outside its allowed scope."""


def _positive_identifier(value, label):
    try:
        identifier = int(value)
    except (TypeError, ValueError):
        raise RegistrantSatelliteAssignmentError("Select a valid {}.".format(label))
    if identifier < 1:
        raise RegistrantSatelliteAssignmentError("Select a valid {}.".format(label))
    return identifier


def _directory(db, directory_id):
    if directory_id is None:
        return None
    return db.execute(
        """
        SELECT directory.id directory_id, directory.name satellite_name,
               hub.id hub_id, hub.name hub_name,
               hub_group.id hub_group_id, hub_group.name hub_group_name
        FROM satellite_directory directory
        LEFT JOIN satellite_hubs hub ON hub.id = directory.hub_id
        LEFT JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
        WHERE directory.id = ?
        """,
        (directory_id,),
    ).fetchone()


def _audit_change(
    db,
    event_id,
    participant_id,
    action,
    previous_directory,
    new_directory,
    changed_by_user_id,
):
    db.execute(
        """
        INSERT INTO event_registrant_satellite_audits (
            event_id, attestation_participant_id, action,
            previous_directory_id, previous_directory_name,
            new_directory_id, new_directory_name, changed_by_user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            participant_id,
            action,
            previous_directory["directory_id"] if previous_directory else None,
            previous_directory["satellite_name"] if previous_directory else None,
            new_directory["directory_id"] if new_directory else None,
            new_directory["satellite_name"] if new_directory else None,
            changed_by_user_id,
        ),
    )


def _latest_imported_assignment(db, event_id, participant_id):
    """Resolve the latest valid automatic target without consulting manual state."""
    plan = analyze_event_satellite_sync(db, event_id)
    batch_id = plan["active_batch_id"]
    if batch_id is None:
        return None, None
    registrant_ids = {
        row["registrant_id"]
        for row in db.execute(
            """
            SELECT registrant_id
            FROM attestation_participant_registrants
            WHERE event_id = ? AND batch_id = ?
              AND attestation_participant_id = ?
            """,
            (event_id, batch_id, participant_id),
        ).fetchall()
    }
    candidates = set()
    for resolution in plan["registrations"]:
        if resolution["registration"]["id"] not in registrant_ids:
            continue
        imported = resolution.get("imported_satellite") or {}
        imported_directory = _directory(db, imported.get("directory_id"))
        if imported_directory and imported_directory["hub_group_id"] is not None:
            candidates.add(imported_directory["directory_id"])
            continue
        canonical = resolution.get("canonical_satellite") or {}
        if resolution["status"] in (READY_TO_SYNC, ALREADY_SYNCED) and canonical.get("id"):
            candidates.add(canonical["id"])
    if len(candidates) != 1:
        return None, batch_id
    return _directory(db, candidates.pop()), batch_id


def _result(directory, source, assignment_id=None, source_batch_id=None):
    if directory is None:
        return {
            "assignment_id": None,
            "assignment_source": None,
            "directory_id": None,
            "satellite_name": None,
            "hub_id": None,
            "hub_name": None,
            "hub_group_id": None,
            "hub_group_name": None,
            "source_batch_id": None,
            "is_manual": False,
        }
    return {
        "assignment_id": assignment_id,
        "assignment_source": source,
        "directory_id": directory["directory_id"],
        "satellite_name": directory["satellite_name"],
        "hub_id": directory["hub_id"],
        "hub_name": directory["hub_name"],
        "hub_group_id": directory["hub_group_id"],
        "hub_group_name": directory["hub_group_name"],
        "source_batch_id": source_batch_id,
        "is_manual": source == MANUAL_ASSIGNMENT,
    }


def resolve_effective_satellite_assignment(
    db,
    event_id,
    attestation_participant_id,
    *,
    automatic_directory_id=None,
    automatic_source_batch_id=None,
):
    """Resolve manual > current automatic > stored automatic > unassigned.

    The optional automatic values bridge the current batch-scoped assignment
    model until later phases integrate this resolver into imports and reports.
    A persisted manual row always wins over those values.
    """
    participant = db.execute(
        """
        SELECT id FROM attestation_participants
        WHERE event_id = ? AND id = ?
        """,
        (event_id, attestation_participant_id),
    ).fetchone()
    if participant is None:
        return _result(None, None)

    assignment = db.execute(
        """
        SELECT assignment.id assignment_id, assignment.directory_id,
               assignment.assignment_source, assignment.source_batch_id
        FROM event_registrant_satellites assignment
        WHERE assignment.event_id = ?
          AND assignment.attestation_participant_id = ?
        """,
        (event_id, attestation_participant_id),
    ).fetchone()

    if assignment and assignment["assignment_source"] == MANUAL_ASSIGNMENT:
        return _result(
            _directory(db, assignment["directory_id"]),
            MANUAL_ASSIGNMENT,
            assignment_id=assignment["assignment_id"],
        )

    automatic = _directory(db, automatic_directory_id)
    if automatic is not None:
        return _result(
            automatic,
            AUTOMATIC_ASSIGNMENT,
            source_batch_id=automatic_source_batch_id,
        )

    if assignment and assignment["assignment_source"] == AUTOMATIC_ASSIGNMENT:
        return _result(
            _directory(db, assignment["directory_id"]),
            AUTOMATIC_ASSIGNMENT,
            assignment_id=assignment["assignment_id"],
            source_batch_id=assignment["source_batch_id"],
        )

    return _result(None, None)


def set_manual_satellite_assignment(
    db,
    event_id,
    attestation_participant_id,
    directory_id,
    *,
    updated_by_user_id=None,
):
    """Create or update the one manual assignment for a durable registrant."""
    event_id = _positive_identifier(event_id, "Event")
    attestation_participant_id = _positive_identifier(attestation_participant_id, "Registrant")
    directory_id = _positive_identifier(directory_id, "Satellite")
    db.lock_event(event_id)
    participant = db.execute(
        """
        SELECT id FROM attestation_participants
        WHERE event_id = ? AND id = ?
        """,
        (event_id, attestation_participant_id),
    ).fetchone()
    if participant is None:
        raise RegistrantSatelliteAssignmentError("Select a valid registrant for this Event.")
    directory = db.execute(
        """
        SELECT directory.id, directory.name
        FROM satellite_directory directory
        JOIN satellite_hubs hub ON hub.id = directory.hub_id
        JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
        WHERE directory.id = ?
        """,
        (directory_id,),
    ).fetchone()
    if directory is None:
        raise RegistrantSatelliteAssignmentError("Select an existing configured Satellite.")

    existing = db.execute(
        """
        SELECT id, directory_id, assignment_source
        FROM event_registrant_satellites
        WHERE event_id = ? AND attestation_participant_id = ?
        """,
        (event_id, attestation_participant_id),
    ).fetchone()
    previous_directory = _directory(db, existing["directory_id"]) if existing else None
    if (
        existing
        and existing["assignment_source"] == MANUAL_ASSIGNMENT
        and existing["directory_id"] == directory_id
    ):
        return {
            "assignment_id": existing["id"],
            "directory_id": directory["id"],
            "satellite_name": directory["name"],
            "changed": False,
        }
    if existing:
        db.execute(
            """
            UPDATE event_registrant_satellites
            SET directory_id = ?, assignment_source = 'manual',
                source_batch_id = NULL, updated_by_user_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (directory_id, updated_by_user_id, existing["id"]),
        )
        assignment_id = existing["id"]
    else:
        assignment_id = db.execute(
            """
            INSERT INTO event_registrant_satellites (
                event_id, attestation_participant_id, directory_id,
                assignment_source, updated_by_user_id
            ) VALUES (?, ?, ?, 'manual', ?)
            """,
            (
                event_id,
                attestation_participant_id,
                directory_id,
                updated_by_user_id,
            ),
        ).lastrowid
    new_directory = _directory(db, directory_id)
    _audit_change(
        db,
        event_id,
        attestation_participant_id,
        MANUAL_ASSIGNMENT,
        previous_directory,
        new_directory,
        updated_by_user_id,
    )
    return {
        "assignment_id": assignment_id,
        "directory_id": directory["id"],
        "satellite_name": directory["name"],
        "changed": True,
    }


def reset_manual_satellite_assignment(
    db,
    event_id,
    attestation_participant_id,
    *,
    updated_by_user_id=None,
):
    """Remove manual protection and resolve the latest valid imported target."""
    event_id = _positive_identifier(event_id, "Event")
    attestation_participant_id = _positive_identifier(
        attestation_participant_id, "Registrant"
    )
    db.lock_event(event_id)
    participant = db.execute(
        """
        SELECT id FROM attestation_participants
        WHERE event_id = ? AND id = ?
        """,
        (event_id, attestation_participant_id),
    ).fetchone()
    if participant is None:
        raise RegistrantSatelliteAssignmentError(
            "Select a valid registrant for this Event."
        )
    existing = db.execute(
        """
        SELECT id, directory_id, assignment_source
        FROM event_registrant_satellites
        WHERE event_id = ? AND attestation_participant_id = ?
        """,
        (event_id, attestation_participant_id),
    ).fetchone()
    if existing is None or existing["assignment_source"] != MANUAL_ASSIGNMENT:
        return {"changed": False, "assignment_source": None, "directory_id": None}

    previous_directory = _directory(db, existing["directory_id"])
    automatic_directory, batch_id = _latest_imported_assignment(
        db, event_id, attestation_participant_id
    )
    if automatic_directory is None:
        db.execute(
            "DELETE FROM event_registrant_satellites WHERE id = ?",
            (existing["id"],),
        )
        assignment_source = None
        directory_id = None
    else:
        db.execute(
            """
            UPDATE event_registrant_satellites
            SET directory_id = ?, assignment_source = 'automatic',
                source_batch_id = ?, updated_by_user_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND assignment_source = 'manual'
            """,
            (
                automatic_directory["directory_id"],
                batch_id,
                updated_by_user_id,
                existing["id"],
            ),
        )
        assignment_source = AUTOMATIC_ASSIGNMENT
        directory_id = automatic_directory["directory_id"]
    _audit_change(
        db,
        event_id,
        attestation_participant_id,
        "reset",
        previous_directory,
        automatic_directory,
        updated_by_user_id,
    )
    return {
        "changed": True,
        "assignment_source": assignment_source,
        "directory_id": directory_id,
        "satellite_name": (
            automatic_directory["satellite_name"]
            if automatic_directory
            else None
        ),
    }


__all__ = [
    "AUTOMATIC_ASSIGNMENT",
    "MANUAL_ASSIGNMENT",
    "RegistrantSatelliteAssignmentError",
    "resolve_effective_satellite_assignment",
    "reset_manual_satellite_assignment",
    "set_manual_satellite_assignment",
]
