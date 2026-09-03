"""Event-scoped registrant read model for Satellite Settings."""

from __future__ import annotations

import math
import unicodedata
from collections import Counter, defaultdict

from .satellite_sync import (
    ALREADY_SYNCED,
    AMBIGUOUS,
    HUB_NOT_FOUND,
    MISSING_SATELLITE,
    READY_TO_SYNC,
    SATELLITE_NOT_CONFIGURED,
    analyze_event_satellite_sync,
)


NEEDS_REVIEW = "Needs Review"
NEEDS_REVIEW_STATUSES = frozenset(
    (SATELLITE_NOT_CONFIGURED, HUB_NOT_FOUND, MISSING_SATELLITE, AMBIGUOUS)
)
STATUS_VALUES = {
    "ready_to_sync": READY_TO_SYNC,
    "already_synced": ALREADY_SYNCED,
    "satellite_not_configured": SATELLITE_NOT_CONFIGURED,
    "hub_not_found": HUB_NOT_FOUND,
    "missing_satellite": MISSING_SATELLITE,
    "ambiguous": AMBIGUOUS,
}
STATUS_OPTIONS = (
    ("all", "All statuses"),
    ("synced", "Synced"),
    ("needs_review", NEEDS_REVIEW),
    *tuple(STATUS_VALUES.items()),
)
SORT_FIELDS = frozenset(("participant", "identifier", "hub", "satellite", "status"))


def _clean(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).strip().split())


def _key(value):
    return _clean(value).casefold()


def _positive_int(value, default, maximum=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if result < 1:
        return default
    return min(result, maximum) if maximum else result


def _pagination(total, page, per_page):
    pages = max(1, math.ceil(total / per_page))
    page = min(page, pages)
    start = (page - 1) * per_page
    lower = max(1, page - 2)
    upper = min(pages, page + 2)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "start": start + 1 if total else 0,
        "end": min(start + per_page, total),
        "has_previous": page > 1,
        "has_next": page < pages,
        "page_numbers": list(range(lower, upper + 1)),
        "offset": start,
    }


def _directory_index(db):
    rows = db.execute(
        """
        SELECT directory.id, directory.name AS satellite_name,
               hubs.id AS hub_id, hubs.name AS hub_name,
               hub_group.id AS group_id, hub_group.code AS group_code,
               hub_group.name AS group_name
        FROM satellite_directory AS directory
        JOIN satellite_hubs AS hubs ON hubs.id = directory.hub_id
        JOIN hub_groups AS hub_group ON hub_group.id = hubs.hub_group_id
        ORDER BY hub_group.sort_order, hub_group.name, hubs.name, directory.name
        """
    ).fetchall()
    return {
        row["id"]: {
            "satellite_id": row["id"],
            "satellite": row["satellite_name"],
            "hub_id": row["hub_id"],
            "hub": row["hub_name"],
            "group_id": row["group_id"],
            "group_code": row["group_code"],
            "group": row["group_name"],
        }
        for row in rows
    }


def _effective_directory_id(resolution):
    imported = resolution.get("imported_satellite") or {}
    if imported.get("directory_id"):
        return imported["directory_id"]
    canonical = resolution.get("canonical_satellite") or {}
    if resolution["status"] == READY_TO_SYNC:
        return canonical.get("id")
    return None


def _records(db, event_id):
    plan = analyze_event_satellite_sync(db, event_id)
    directory = _directory_index(db)
    records = []
    for resolution in plan["registrations"]:
        location = directory.get(_effective_directory_id(resolution), {})
        registration = resolution["registration"]
        records.append(
            {
                "id": registration["id"],
                "identifier": registration["identifier"],
                "registration_code": registration["registration_code"],
                "participant": registration["participant"] or "—",
                "group_id": location.get("group_id"),
                "group_code": location.get("group_code"),
                "group": location.get("group") or "Unresolved",
                "hub_id": location.get("hub_id"),
                "hub": location.get("hub") or resolution.get("source_hub") or "—",
                "satellite_id": location.get("satellite_id"),
                "satellite": location.get("satellite") or resolution.get("source_satellite") or "—",
                "source_hub": resolution.get("source_hub") or "—",
                "source_satellite": resolution.get("source_satellite") or "—",
                "status": resolution["status"],
                "needs_review": resolution["status"] in NEEDS_REVIEW_STATUSES,
            }
        )
    return plan, records, directory


def _status_matches(record, value):
    if value in (None, "", "all"):
        return True
    if value == "synced":
        return record["status"] == ALREADY_SYNCED
    if value == "needs_review":
        return record["needs_review"]
    return record["status"] == STATUS_VALUES.get(value)


def filter_registrants(
    records, query="", group_code="", hub_id=None, satellite_id=None, sync_status="all"
):
    query_key = _key(query)
    hub_id = _positive_int(hub_id, None) if hub_id else None
    satellite_id = _positive_int(satellite_id, None) if satellite_id else None
    filtered = []
    for record in records:
        searchable = " ".join(
            str(record[field] or "")
            for field in (
                "participant",
                "identifier",
                "registration_code",
                "group",
                "hub",
                "satellite",
                "source_hub",
                "source_satellite",
                "status",
            )
        )
        if query_key and query_key not in _key(searchable):
            continue
        if group_code and group_code != "all" and record["group_code"] != group_code:
            continue
        if hub_id and record["hub_id"] != hub_id:
            continue
        if satellite_id and record["satellite_id"] != satellite_id:
            continue
        if not _status_matches(record, sync_status):
            continue
        filtered.append(record)
    return filtered


def _sorted(records, sort, direction):
    sort = sort if sort in SORT_FIELDS else "participant"
    direction = direction if direction in ("asc", "desc") else "asc"
    return (
        sorted(
            records,
            key=lambda item: (_key(item[sort]), item["id"]),
            reverse=direction == "desc",
        ),
        sort,
        direction,
    )


def _counts(records):
    totals = defaultdict(lambda: Counter(registrants=0, synced=0, review=0, ready=0))
    for record in records:
        for kind, identifier in (
            ("group", record["group_id"]),
            ("hub", record["hub_id"]),
            ("satellite", record["satellite_id"]),
        ):
            if identifier is None:
                continue
            bucket = totals[(kind, identifier)]
            bucket["registrants"] += 1
            bucket["synced"] += record["status"] == ALREADY_SYNCED
            bucket["ready"] += record["status"] == READY_TO_SYNC
            bucket["review"] += record["needs_review"]
    return {
        "{}:{}".format(kind, identifier): dict(value)
        for (kind, identifier), value in totals.items()
    }


def _options(db, directory):
    groups = {
        row["code"]: {"id": row["id"], "code": row["code"], "name": row["name"]}
        for row in db.execute(
            "SELECT id, code, name FROM hub_groups ORDER BY sort_order, name"
        ).fetchall()
    }
    hubs = {
        row["id"]: {"id": row["id"], "name": row["name"], "group_code": row["group_code"]}
        for row in db.execute(
            """
            SELECT hubs.id, hubs.name, hub_group.code AS group_code
            FROM satellite_hubs AS hubs
            JOIN hub_groups AS hub_group ON hub_group.id = hubs.hub_group_id
            ORDER BY hub_group.sort_order, hubs.name
            """
        ).fetchall()
    }
    satellites = [
        {
            "id": item["satellite_id"],
            "name": item["satellite"],
            "hub_id": item["hub_id"],
            "group_code": item["group_code"],
        }
        for item in directory.values()
    ]
    return {
        "groups": sorted(groups.values(), key=lambda item: item["name"]),
        "hubs": sorted(hubs.values(), key=lambda item: item["name"]),
        "satellites": sorted(satellites, key=lambda item: item["name"]),
        "statuses": STATUS_OPTIONS,
    }


def event_settings_registrants(
    db,
    event_id,
    *,
    query="",
    group_code="",
    hub_id=None,
    satellite_id=None,
    sync_status="all",
    sort="participant",
    direction="asc",
    page=1,
    per_page=25,
):
    """Return Event-only aggregates plus a filtered, sorted page of registrants."""
    plan, records, directory = _records(db, event_id)
    options = _options(db, directory)
    filtered = filter_registrants(records, query, group_code, hub_id, satellite_id, sync_status)
    filter_active = bool(
        _clean(query)
        or group_code
        or hub_id
        or satellite_id
        or sync_status not in (None, "", "all")
    )
    visible_satellites = {
        item["satellite_id"] for item in filtered if item["satellite_id"] is not None
    }
    if sync_status in (None, "", "all"):
        query_key = _key(query)
        requested_hub = _positive_int(hub_id, None) if hub_id else None
        requested_satellite = _positive_int(satellite_id, None) if satellite_id else None
        for item in directory.values():
            if group_code and item["group_code"] != group_code:
                continue
            if requested_hub and item["hub_id"] != requested_hub:
                continue
            if requested_satellite and item["satellite_id"] != requested_satellite:
                continue
            if query_key and query_key not in _key(
                "{} {} {}".format(item["group"], item["hub"], item["satellite"])
            ):
                continue
            visible_satellites.add(item["satellite_id"])
    visible_hubs = {directory[item]["hub_id"] for item in visible_satellites if item in directory}
    visible_groups = {
        directory[item]["group_id"] for item in visible_satellites if item in directory
    }
    if sync_status in (None, "", "all") and not satellite_id:
        query_key = _key(query)
        groups_by_code = {item["code"]: item for item in options["groups"]}
        for hub in options["hubs"]:
            group = groups_by_code.get(hub["group_code"], {})
            if group_code and hub["group_code"] != group_code:
                continue
            if hub_id and hub["id"] != _positive_int(hub_id, None):
                continue
            if query_key and query_key not in _key(
                "{} {}".format(group.get("name", ""), hub["name"])
            ):
                continue
            visible_hubs.add(hub["id"])
            if group.get("id") is not None:
                visible_groups.add(group["id"])
        if not hub_id:
            for group in options["groups"]:
                if group_code and group["code"] != group_code:
                    continue
                if query_key and query_key not in _key(group["name"]):
                    continue
                visible_groups.add(group["id"])
    ordered, sort, direction = _sorted(filtered, sort, direction)
    pagination = _pagination(len(ordered), _positive_int(page, 1), _positive_int(per_page, 25, 100))
    rows = ordered[pagination["offset"] : pagination["offset"] + pagination["per_page"]]
    overall = Counter(
        registrants=len(records),
        synced=sum(item["status"] == ALREADY_SYNCED for item in records),
        ready=sum(item["status"] == READY_TO_SYNC for item in records),
        review=sum(item["needs_review"] for item in records),
    )
    return {
        "event": plan["event"],
        "active_batch_id": plan["active_batch_id"],
        "totals": dict(overall),
        "filtered_totals": {
            "registrants": len(filtered),
            "synced": sum(item["status"] == ALREADY_SYNCED for item in filtered),
            "ready": sum(item["status"] == READY_TO_SYNC for item in filtered),
            "review": sum(item["needs_review"] for item in filtered),
        },
        "counts": _counts(filtered),
        "visibility": {
            "active": filter_active,
            "groups": sorted(visible_groups),
            "hubs": sorted(visible_hubs),
            "satellites": sorted(visible_satellites),
        },
        "options": options,
        "rows": rows,
        "pagination": {key: value for key, value in pagination.items() if key != "offset"},
        "sort": sort,
        "direction": direction,
    }
