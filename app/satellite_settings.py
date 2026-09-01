"""Read model for the global Hub Group -> Hub -> Satellite settings hierarchy."""

from __future__ import annotations

import re
import unicodedata


HUB_GROUPS = (
    ("within_metro_manila", "Within Metro Manila Hubs", 1),
    ("outside_metro_manila", "Outside Metro Manila Hubs", 2),
)
MAX_HUB_NAME_LENGTH = 160
MAX_SATELLITE_NAME_LENGTH = 512
MAX_BULK_INPUT_LENGTH = 100_000
MAX_BULK_ENTRIES = 1_000


class SatelliteSettingsValidationError(ValueError):
    """Raised when an individual settings operation is invalid."""


def normalize_settings_name(value, label, maximum):
    cleaned = " ".join(
        unicodedata.normalize("NFKC", str(value or "")).strip().split()
    )
    if not cleaned:
        raise SatelliteSettingsValidationError("{} is required.".format(label))
    if len(cleaned) > maximum:
        raise SatelliteSettingsValidationError(
            "{} cannot exceed {} characters.".format(label, maximum)
        )
    return cleaned, cleaned.casefold()


def _normalize_bulk_values(values, label, maximum):
    normalized = []
    for value in values:
        if not str(value or "").strip():
            continue
        normalized.append(normalize_settings_name(value, label, maximum))
    if not normalized:
        raise SatelliteSettingsValidationError(
            "Paste at least one {}.".format(label)
        )
    if len(normalized) > MAX_BULK_ENTRIES:
        raise SatelliteSettingsValidationError(
            "Bulk entry supports at most {} records at a time.".format(
                MAX_BULK_ENTRIES
            )
        )
    return normalized


def parse_bulk_names(value, label, maximum):
    """Parse spreadsheet columns, rows, and comma-separated values."""
    text = str(value or "")
    if len(text) > MAX_BULK_INPUT_LENGTH:
        raise SatelliteSettingsValidationError(
            "Bulk entry cannot exceed {:,} characters.".format(MAX_BULK_INPUT_LENGTH)
        )
    return _normalize_bulk_values(
        re.split(r"[,\t\r\n]+", text), label, maximum
    )


def _classify_bulk_entries(normalized_values, existing_names):
    seen = set()
    entries = []
    for name, normalized_name in normalized_values:
        duplicate = normalized_name in existing_names or normalized_name in seen
        entries.append(
            {
                "name": name,
                "normalized_name": normalized_name,
                "status": "duplicate" if duplicate else "new",
            }
        )
        seen.add(normalized_name)
    return entries


def _identifier(value, label):
    try:
        identifier = int(value)
    except (TypeError, ValueError):
        raise SatelliteSettingsValidationError("Select a valid {}.".format(label))
    if identifier < 1:
        raise SatelliteSettingsValidationError("Select a valid {}.".format(label))
    return identifier


def _hub_group(db, group_id):
    group_id = _identifier(group_id, "Hub Group")
    row = db.execute(
        "SELECT id, name FROM hub_groups WHERE id = ?", (group_id,)
    ).fetchone()
    if row is None:
        raise SatelliteSettingsValidationError("Select a valid Hub Group.")
    return row


def _hub(db, hub_id):
    hub_id = _identifier(hub_id, "Hub")
    row = db.execute(
        "SELECT id, hub_group_id, name FROM satellite_hubs WHERE id = ?", (hub_id,)
    ).fetchone()
    if row is None:
        raise SatelliteSettingsValidationError("Select a valid Hub.")
    return row


def create_hub(db, group_id, name):
    group = _hub_group(db, group_id)
    name, normalized_name = normalize_settings_name(
        name, "Hub Name", MAX_HUB_NAME_LENGTH
    )
    duplicate = db.execute(
        """
        SELECT id FROM satellite_hubs
        WHERE hub_group_id = ? AND normalized_name = ?
        """,
        (group["id"], normalized_name),
    ).fetchone()
    if duplicate:
        raise SatelliteSettingsValidationError(
            "A Hub named ‘{}’ already exists in {}.".format(name, group["name"])
        )
    hub_id = db.execute(
        """
        INSERT INTO satellite_hubs (hub_group_id, name, normalized_name)
        VALUES (?, ?, ?)
        """,
        (group["id"], name, normalized_name),
    ).lastrowid
    return hub_id, name


def update_hub(db, hub_id, group_id, name):
    hub = _hub(db, hub_id)
    group = _hub_group(db, group_id)
    name, normalized_name = normalize_settings_name(
        name, "Hub Name", MAX_HUB_NAME_LENGTH
    )
    duplicate = db.execute(
        """
        SELECT id FROM satellite_hubs
        WHERE hub_group_id = ? AND normalized_name = ? AND id <> ?
        """,
        (group["id"], normalized_name, hub["id"]),
    ).fetchone()
    if duplicate:
        raise SatelliteSettingsValidationError(
            "A Hub named ‘{}’ already exists in {}.".format(name, group["name"])
        )
    db.execute(
        """
        UPDATE satellite_hubs
        SET hub_group_id = ?, name = ?, normalized_name = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (group["id"], name, normalized_name, hub["id"]),
    )
    return name


def _duplicate_satellite(db, hub_id, normalized_name, exclude_id=None):
    statement = (
        "SELECT id FROM satellite_directory "
        "WHERE hub_id = ? AND normalized_name = ?"
    )
    params = [hub_id, normalized_name]
    if exclude_id is not None:
        statement += " AND id <> ?"
        params.append(exclude_id)
    return db.execute(statement, params).fetchone()


def create_satellite(db, hub_id, name):
    hub = _hub(db, hub_id)
    name, normalized_name = normalize_settings_name(
        name, "Satellite Name", MAX_SATELLITE_NAME_LENGTH
    )
    if _duplicate_satellite(db, hub["id"], normalized_name):
        raise SatelliteSettingsValidationError(
            "A Satellite named ‘{}’ already exists in {}.".format(name, hub["name"])
        )
    satellite_id = db.execute(
        """
        INSERT INTO satellite_directory (hub_id, name, normalized_name)
        VALUES (?, ?, ?)
        """,
        (hub["id"], name, normalized_name),
    ).lastrowid
    return satellite_id, name


def update_satellite(db, satellite_id, hub_id, name):
    satellite_id = _identifier(satellite_id, "Satellite")
    existing = db.execute(
        "SELECT id FROM satellite_directory WHERE id = ?", (satellite_id,)
    ).fetchone()
    if existing is None:
        raise SatelliteSettingsValidationError("Select a valid Satellite.")
    hub = _hub(db, hub_id)
    name, normalized_name = normalize_settings_name(
        name, "Satellite Name", MAX_SATELLITE_NAME_LENGTH
    )
    if _duplicate_satellite(db, hub["id"], normalized_name, satellite_id):
        raise SatelliteSettingsValidationError(
            "A Satellite named ‘{}’ already exists in {}.".format(name, hub["name"])
        )
    db.execute(
        """
        UPDATE satellite_directory
        SET hub_id = ?, name = ?, normalized_name = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (hub["id"], name, normalized_name, satellite_id),
    )
    return name


def review_bulk_hubs(db, group_id, value):
    group = _hub_group(db, group_id)
    values = parse_bulk_names(value, "Hub Name", MAX_HUB_NAME_LENGTH)
    existing = {
        row["normalized_name"]
        for row in db.execute(
            "SELECT normalized_name FROM satellite_hubs WHERE hub_group_id = ?",
            (group["id"],),
        ).fetchall()
    }
    entries = _classify_bulk_entries(values, existing)
    return _bulk_review_payload("hubs", group, entries)


def review_bulk_satellites(db, hub_id, value):
    hub = _hub(db, hub_id)
    values = parse_bulk_names(value, "Satellite Name", MAX_SATELLITE_NAME_LENGTH)
    existing = {
        row["normalized_name"]
        for row in db.execute(
            "SELECT normalized_name FROM satellite_directory WHERE hub_id = ?",
            (hub["id"],),
        ).fetchall()
    }
    entries = _classify_bulk_entries(values, existing)
    return _bulk_review_payload("satellites", hub, entries)


def _bulk_review_payload(kind, target, entries):
    new_entries = [entry for entry in entries if entry["status"] == "new"]
    duplicates = [entry for entry in entries if entry["status"] == "duplicate"]
    return {
        "kind": kind,
        "target_id": target["id"],
        "target_name": target["name"],
        "entries": entries,
        "new_entries": new_entries,
        "duplicates": duplicates,
        "detected_count": len(entries),
        "new_count": len(new_entries),
        "duplicate_count": len(duplicates),
    }


def confirm_bulk_hubs(db, group_id, values):
    group = _hub_group(db, group_id)
    normalized = _normalize_bulk_values(
        values, "Hub Name", MAX_HUB_NAME_LENGTH
    )
    existing = {
        row["normalized_name"]
        for row in db.execute(
            "SELECT normalized_name FROM satellite_hubs WHERE hub_group_id = ?",
            (group["id"],),
        ).fetchall()
    }
    entries = _classify_bulk_entries(normalized, existing)
    new_entries = [entry for entry in entries if entry["status"] == "new"]
    db.executemany(
        """
        INSERT INTO satellite_hubs (hub_group_id, name, normalized_name)
        VALUES (?, ?, ?)
        """,
        [
            (group["id"], entry["name"], entry["normalized_name"])
            for entry in new_entries
        ],
    )
    return len(new_entries), len(entries) - len(new_entries), group["name"]


def confirm_bulk_satellites(db, hub_id, values):
    hub = _hub(db, hub_id)
    normalized = _normalize_bulk_values(
        values, "Satellite Name", MAX_SATELLITE_NAME_LENGTH
    )
    existing = {
        row["normalized_name"]
        for row in db.execute(
            "SELECT normalized_name FROM satellite_directory WHERE hub_id = ?",
            (hub["id"],),
        ).fetchall()
    }
    entries = _classify_bulk_entries(normalized, existing)
    new_entries = [entry for entry in entries if entry["status"] == "new"]
    db.executemany(
        """
        INSERT INTO satellite_directory (hub_id, name, normalized_name)
        VALUES (?, ?, ?)
        """,
        [
            (hub["id"], entry["name"], entry["normalized_name"])
            for entry in new_entries
        ],
    )
    return len(new_entries), len(entries) - len(new_entries), hub["name"]


def satellite_settings_hierarchy(db):
    """Return the canonical directory without altering imported batch records."""
    group_rows = db.execute(
        "SELECT id, code, name, sort_order FROM hub_groups ORDER BY sort_order, id"
    ).fetchall()
    hub_rows = db.execute(
        """
        SELECT id, hub_group_id, name
        FROM satellite_hubs
        ORDER BY LOWER(name), id
        """
    ).fetchall()
    satellite_rows = db.execute(
        """
        SELECT directory.id, directory.hub_id, directory.name,
               COUNT(satellite.id) import_count,
               COALESCE(SUM(satellite.source_record_count), 0) source_records,
               COUNT(DISTINCT satellite.event_id) event_count
        FROM satellite_directory directory
        LEFT JOIN satellites satellite ON satellite.directory_id = directory.id
        GROUP BY directory.id, directory.hub_id, directory.name
        ORDER BY LOWER(directory.name), directory.id
        """
    ).fetchall()

    groups = []
    groups_by_id = {}
    for row in group_rows:
        group = {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "hubs": [],
            "hub_count": 0,
            "satellite_count": 0,
        }
        groups.append(group)
        groups_by_id[row["id"]] = group

    hubs_by_id = {}
    for row in hub_rows:
        group = groups_by_id.get(row["hub_group_id"])
        if group is None:
            continue
        hub = {
            "id": row["id"],
            "hub_group_id": row["hub_group_id"],
            "name": row["name"],
            "satellites": [],
        }
        group["hubs"].append(hub)
        group["hub_count"] += 1
        hubs_by_id[row["id"]] = (group, hub)

    unassigned = []
    for row in satellite_rows:
        satellite = {
            "id": row["id"],
            "name": row["name"],
            "import_count": row["import_count"],
            "source_records": row["source_records"],
            "event_count": row["event_count"],
        }
        owner = hubs_by_id.get(row["hub_id"])
        if owner is None:
            unassigned.append(satellite)
            continue
        group, hub = owner
        hub["satellites"].append(satellite)
        group["satellite_count"] += 1

    return {
        "groups": groups,
        "hubs": [hub for group in groups for hub in group["hubs"]],
        "unassigned": unassigned,
        "hub_count": sum(group["hub_count"] for group in groups),
        "satellite_count": len(satellite_rows),
        "assigned_count": len(satellite_rows) - len(unassigned),
    }
