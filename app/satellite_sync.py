"""Read-only planning for Event-scoped registration Satellite synchronization."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping

from .curation import normalize_satellite_name
from .satellite_settings import (
    MAX_HUB_NAME_LENGTH,
    MAX_SATELLITE_NAME_LENGTH,
    SatelliteSettingsValidationError,
    normalize_settings_name,
)


READY_TO_SYNC = "Ready to Sync"
ALREADY_SYNCED = "Already Synced"
MANUAL_PROTECTED = "Manual Assignment — Protected"
SATELLITE_NOT_CONFIGURED = "Satellite Not Configured"
HUB_NOT_FOUND = "Hub Not Found"
MISSING_SATELLITE = "Missing Satellite"
AMBIGUOUS = "Ambiguous"

SYNC_STATUSES = (
    READY_TO_SYNC,
    ALREADY_SYNCED,
    MANUAL_PROTECTED,
    SATELLITE_NOT_CONFIGURED,
    HUB_NOT_FOUND,
    MISSING_SATELLITE,
    AMBIGUOUS,
)

# These are source-data field names, not aliases. A source Hub outside this
# contract is deliberately left unmatched.
REGISTRATION_SATELLITE_FIELDS = {
    "luzon north central": "Luzon North Central Hub",
    "luzon central": "Luzon Central Hub",
    "luzon north east": "Luzon North East Hub",
    "luzon north west": "Luzon North West Hub",
    "luzon south": "Luzon South Hub",
    "mindanao south": "Mindanao South Hub",
    "mindanao north": "Mindanao North Hub",
    "visayas": "Visayas Hub",
    "icp": "Specify Icp Hub",
    "metro east": "Metro East Hub",
    "metro west": "Metro West Hub",
    "metro south": "Metro South Hub",
    "main": "Main Hub",
}


class SatelliteSyncAnalysisError(ValueError):
    """Raised when a synchronization plan cannot be generated."""


def _clean(value):
    return " ".join(str(value or "").strip().split())


def _normalized(value, label, maximum):
    if not _clean(value):
        return None
    try:
        return normalize_settings_name(value, label, maximum)[1]
    except SatelliteSettingsValidationError:
        return None


def _source_data(value):
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, Mapping) else {}


def _public_registration(row):
    participant = _clean("{} {}".format(row["first_name"] or "", row["last_name"] or ""))
    return {
        "id": row["id"],
        "identifier": row["source_id"] or row["registration_code"] or str(row["id"]),
        "source_id": row["source_id"],
        "registration_code": row["registration_code"],
        "participant": participant or None,
    }


def _public_hub(row):
    if row is None:
        return None
    return {"id": row["id"], "name": row["name"]}


def _public_satellite(row):
    if row is None:
        return None
    return {"id": row["id"], "hub_id": row["hub_id"], "name": row["name"]}


def _result(
    registration,
    source_hub,
    source_satellite,
    expected_hub,
    canonical_satellite,
    imported_satellite,
    status,
):
    return {
        "registration": _public_registration(registration),
        "source_hub": source_hub or None,
        "source_satellite": source_satellite or None,
        "expected_hub": _public_hub(expected_hub),
        "canonical_satellite": _public_satellite(canonical_satellite),
        "imported_satellite": (
            {
                "id": imported_satellite["id"],
                "directory_id": imported_satellite["directory_id"],
                "name": imported_satellite["name"],
            }
            if imported_satellite is not None
            else None
        ),
        "status": status,
        "reason": (
            None
            if status in (READY_TO_SYNC, ALREADY_SYNCED, MANUAL_PROTECTED)
            else status
        ),
    }


def resolve_registration_satellite(
    registration, imported_satellite, hubs_by_name, satellites_by_hub_and_name
):
    """Resolve one registration without mutating imported or directory data."""
    source_hub = _clean(registration["b1g_satellite_hub_raw"])
    source_hub_key = _normalized(source_hub, "Hub Name", MAX_HUB_NAME_LENGTH)
    source_field = REGISTRATION_SATELLITE_FIELDS.get(source_hub_key)
    source_satellite = _clean(_source_data(registration["source_data_json"]).get(source_field))

    if not source_hub or (source_field is not None and not source_satellite):
        return _result(
            registration, source_hub, source_satellite, None, None,
            imported_satellite, MISSING_SATELLITE,
        )

    matching_hubs = hubs_by_name.get(source_hub_key, ())
    if not matching_hubs:
        return _result(
            registration, source_hub, source_satellite, None, None,
            imported_satellite, HUB_NOT_FOUND,
        )
    if len(matching_hubs) != 1:
        return _result(
            registration, source_hub, source_satellite, None, None,
            imported_satellite, AMBIGUOUS,
        )

    expected_hub = matching_hubs[0]
    satellite_key = _normalized(
        source_satellite, "Satellite Name", MAX_SATELLITE_NAME_LENGTH
    )
    if satellite_key is None:
        return _result(
            registration, source_hub, source_satellite, expected_hub, None,
            imported_satellite, MISSING_SATELLITE,
        )

    canonical_matches = satellites_by_hub_and_name.get(
        (expected_hub["id"], satellite_key), ()
    )
    if not canonical_matches:
        return _result(
            registration, source_hub, source_satellite, expected_hub, None,
            imported_satellite, SATELLITE_NOT_CONFIGURED,
        )
    if len(canonical_matches) != 1:
        return _result(
            registration, source_hub, source_satellite, expected_hub, None,
            imported_satellite, AMBIGUOUS,
        )

    canonical = canonical_matches[0]
    if imported_satellite is None:
        # There is no imported evidence row whose directory_id can be linked.
        status = MISSING_SATELLITE
    elif imported_satellite["directory_id"] is None:
        status = READY_TO_SYNC
    elif (
        imported_satellite["directory_id"] != canonical["id"]
        and not imported_satellite["directory_link_complete"]
    ):
        # Imports created before the canonical Hub hierarchy may still point at
        # an unassigned directory entry. That non-null link is not complete from
        # the analytics perspective, so an exact registration-derived match may
        # safely repair it. Complete existing assignments remain non-destructive.
        status = READY_TO_SYNC
    else:
        # A matching or otherwise complete canonical assignment is considered
        # synchronized. The sync never replaces an established complete link.
        status = ALREADY_SYNCED
    return _result(
        registration, source_hub, source_satellite, expected_hub, canonical,
        imported_satellite, status,
    )


def _ambiguous_aggregate(resolutions):
    """An aggregate row may only represent one exact Hub/Satellite path."""
    interpretations = {
        (
            _normalized(item["source_hub"], "Hub Name", MAX_HUB_NAME_LENGTH),
            _normalized(
                item["source_satellite"], "Satellite Name", MAX_SATELLITE_NAME_LENGTH
            ),
        )
        for item in resolutions
    }
    return len(interpretations) > 1


def analyze_event_satellite_sync(db, event_id):
    """Generate a complete, reusable, read-only sync plan for one Event."""
    try:
        event_id = int(event_id)
    except (TypeError, ValueError) as exc:
        raise SatelliteSyncAnalysisError("Select a valid Event.") from exc
    if event_id < 1:
        raise SatelliteSyncAnalysisError("Select a valid Event.")

    event = db.execute("SELECT id, name FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        raise SatelliteSyncAnalysisError("The selected Event does not exist.")
    batch = db.execute(
        """
        SELECT id FROM import_batches
        WHERE event_id = ? AND status = 'active'
        ORDER BY activated_at DESC, id DESC LIMIT 1
        """,
        (event_id,),
    ).fetchone()
    if batch is None:
        return {
            "event": {"id": event["id"], "name": event["name"]},
            "active_batch_id": None,
            "entries": [],
            "registrations": [],
            "counts": {status: 0 for status in SYNC_STATUSES},
            "source_satellite_records": 0,
            "represented_registrations": 0,
        }

    hubs_by_name = defaultdict(list)
    for hub in db.execute(
        "SELECT id, name, normalized_name FROM satellite_hubs ORDER BY id"
    ).fetchall():
        hubs_by_name[hub["normalized_name"]].append(hub)

    satellites_by_hub_and_name = defaultdict(list)
    for directory in db.execute(
        """
        SELECT id, hub_id, name, normalized_name FROM satellite_directory
        WHERE hub_id IS NOT NULL ORDER BY id
        """
    ).fetchall():
        satellites_by_hub_and_name[
            (directory["hub_id"], directory["normalized_name"])
        ].append(directory)

    imported_rows = db.execute(
        """
        SELECT imported.id, imported.directory_id, imported.name,
               imported.normalized_name, imported.source_record_count,
               CASE WHEN current_group.id IS NOT NULL THEN 1 ELSE 0 END
                    directory_link_complete
        FROM satellites imported
        LEFT JOIN satellite_directory current_directory
          ON current_directory.id = imported.directory_id
        LEFT JOIN satellite_hubs current_hub
          ON current_hub.id = current_directory.hub_id
        LEFT JOIN hub_groups current_group
          ON current_group.id = current_hub.hub_group_id
        WHERE imported.event_id = ? AND imported.batch_id = ?
        ORDER BY imported.id
        """,
        (event_id, batch["id"]),
    ).fetchall()
    imported_by_key = {row["normalized_name"]: row for row in imported_rows}
    registrations = db.execute(
        """
        SELECT id, source_id, registration_code, first_name, last_name,
               affiliation, satellite_name, b1g_satellite_hub_raw, source_data_json
        FROM registrants WHERE batch_id = ? AND ticket_matched = 1 ORDER BY id
        """,
        (batch["id"],),
    ).fetchall()
    manual_assignments = {
        row["registrant_id"]: {
            "directory_id": row["directory_id"],
            "satellite_name": row["satellite_name"],
        }
        for row in db.execute(
            """
            SELECT owner.registrant_id, assignment.directory_id,
                   directory.name satellite_name
            FROM attestation_participant_registrants owner
            JOIN event_registrant_satellites assignment
              ON assignment.event_id = owner.event_id
             AND assignment.attestation_participant_id = owner.attestation_participant_id
             AND assignment.assignment_source = 'manual'
            JOIN satellite_directory directory ON directory.id = assignment.directory_id
            WHERE owner.event_id = ? AND owner.batch_id = ?
            """,
            (event_id, batch["id"]),
        ).fetchall()
    }

    resolutions = []
    by_imported_id = defaultdict(list)
    for registration in registrations:
        normalized_import = normalize_satellite_name(
            registration["satellite_name"], registration["affiliation"]
        )
        imported = imported_by_key.get(normalized_import["key"]) if normalized_import else None
        resolution = resolve_registration_satellite(
            registration, imported, hubs_by_name, satellites_by_hub_and_name
        )
        manual_assignment = manual_assignments.get(registration["id"])
        if manual_assignment is not None:
            resolution["status"] = MANUAL_PROTECTED
            resolution["reason"] = None
            resolution["manual_assignment"] = manual_assignment
        resolutions.append(resolution)
        if imported is not None:
            by_imported_id[imported["id"]].append(resolution)

    entries = []
    for imported in imported_rows:
        represented = by_imported_id.get(imported["id"], [])
        unprotected = [
            item for item in represented if item["status"] != MANUAL_PROTECTED
        ]
        if not represented:
            status = MISSING_SATELLITE
            representative = None
        elif not unprotected:
            status = MANUAL_PROTECTED
            representative = represented[0]
        elif _ambiguous_aggregate(unprotected):
            status = AMBIGUOUS
            representative = unprotected[0]
            for item in unprotected:
                item["status"] = AMBIGUOUS
                item["reason"] = AMBIGUOUS
        else:
            representative = unprotected[0]
            statuses = {item["status"] for item in unprotected}
            status = representative["status"] if len(statuses) == 1 else AMBIGUOUS
            if status == AMBIGUOUS:
                for item in unprotected:
                    item["status"] = AMBIGUOUS
                    item["reason"] = AMBIGUOUS
        entries.append(
            {
                "imported_satellite": {
                    "id": imported["id"],
                    "directory_id": imported["directory_id"],
                    "name": imported["name"],
                    "source_record_count": imported["source_record_count"],
                },
                "source_hub": representative["source_hub"] if representative else None,
                "source_satellite": (
                    representative["source_satellite"] if representative else None
                ),
                "expected_hub": representative["expected_hub"] if representative else None,
                "canonical_satellite": (
                    representative["canonical_satellite"] if representative else None
                ),
                "status": status,
                "reason": (
                    None
                    if status in (READY_TO_SYNC, ALREADY_SYNCED, MANUAL_PROTECTED)
                    else status
                ),
                "registrations": represented,
            }
        )

    counts = Counter(entry["status"] for entry in entries)
    return {
        "event": {"id": event["id"], "name": event["name"]},
        "active_batch_id": batch["id"],
        "entries": entries,
        "registrations": resolutions,
        "counts": {status: counts[status] for status in SYNC_STATUSES},
        "source_satellite_records": len(imported_rows),
        "represented_registrations": sum(
            row["source_record_count"] for row in imported_rows
        ),
    }


def execute_event_satellite_sync(db, event_id):
    """Revalidate and apply only exact, currently unassigned directory links.

    The caller owns commit and rollback so the complete confirmation remains a
    single transaction.
    """
    try:
        event_id = int(event_id)
    except (TypeError, ValueError) as exc:
        raise SatelliteSyncAnalysisError("Select a valid Event.") from exc
    if event_id < 1:
        raise SatelliteSyncAnalysisError("Select a valid Event.")

    # Serialize confirmations for an Event on MySQL before rebuilding the plan.
    # SQLite test transactions retain the same call contract without FOR UPDATE.
    db.lock_event(event_id)
    db.lock_satellite_directory()
    plan = analyze_event_satellite_sync(db, event_id)
    synchronized = []
    for entry in plan["entries"]:
        if entry["status"] != READY_TO_SYNC:
            continue
        imported = entry["imported_satellite"]
        canonical = entry["canonical_satellite"]
        if canonical is None:
            continue
        previous_directory_id = imported["directory_id"]
        if previous_directory_id is None:
            current_link_guard = "directory_id IS NULL"
            parameters = (
                canonical["id"],
                imported["id"],
                event_id,
                plan["active_batch_id"],
            )
        else:
            current_link_guard = "directory_id = ?"
            parameters = (
                canonical["id"],
                imported["id"],
                event_id,
                plan["active_batch_id"],
                previous_directory_id,
            )
        result = db.execute(
            """
            UPDATE satellites SET directory_id = ?
            WHERE id = ? AND event_id = ? AND batch_id = ?
              AND {current_link_guard}
            """.format(current_link_guard=current_link_guard),
            parameters,
        )
        if result.rowcount == 1:
            synchronized.append(entry)

    return {
        "event": plan["event"],
        "active_batch_id": plan["active_batch_id"],
        "synchronized_count": len(synchronized),
        "synchronized_registration_count": sum(
            entry["imported_satellite"]["source_record_count"]
            for entry in synchronized
        ),
        "already_synced_count": plan["counts"][ALREADY_SYNCED],
        "not_synced_count": sum(
            count
            for status, count in plan["counts"].items()
            if status not in (READY_TO_SYNC, ALREADY_SYNCED, MANUAL_PROTECTED)
        ),
        "plan": plan,
    }
