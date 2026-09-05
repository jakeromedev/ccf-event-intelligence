"""Canonical hierarchy-derived Satellite reporting categories.

The canonical Hub is the sole category authority. A Hub with the durable
``is_main`` identity resolves to Main; every other Hub inherits its fixed Hub
Group code. Event-specific target configuration never classifies Satellites.
"""

from __future__ import annotations


REPORTING_CATEGORY_LABELS = {
    "outside_metro_manila": "Outside Metro Manila Hubs",
    "within_metro_manila": "Within Metro Manila Hubs",
    "main": "Main",
}
REPORTING_CATEGORY_KEYS = tuple(REPORTING_CATEGORY_LABELS)
NEEDS_MAPPING_LABEL = "Needs Mapping"

REPORTING_CATEGORY_SQL = """
CASE
    WHEN hub.is_main = 1 THEN 'main'
    WHEN hub_group.code = 'outside_metro_manila' THEN 'outside_metro_manila'
    WHEN hub_group.code = 'within_metro_manila' THEN 'within_metro_manila'
    ELSE NULL
END
""".strip()


def _public_resolution(row):
    category_key = row["category_key"]
    return {
        **dict(row),
        "category_label": REPORTING_CATEGORY_LABELS.get(
            category_key, NEEDS_MAPPING_LABEL
        ),
        "resolved": category_key in REPORTING_CATEGORY_LABELS,
    }


def resolve_reporting_categories(db, directory_ids=None):
    """Resolve canonical directories in one set-based hierarchy query."""
    params = []
    where = ""
    if directory_ids is not None:
        identifiers = sorted({int(value) for value in directory_ids if int(value) > 0})
        if not identifiers:
            return []
        where = "WHERE directory.id IN ({})".format(
            ", ".join("?" for _value in identifiers)
        )
        params.extend(identifiers)
    rows = db.execute(
        """
        SELECT directory.id directory_id, directory.name,
               hub.id hub_id, hub.name hub_name, hub.is_main,
               hub_group.id hub_group_id, hub_group.code hub_group_code,
               hub_group.name hub_group_name,
               {category_sql} category_key
        FROM satellite_directory directory
        LEFT JOIN satellite_hubs hub ON hub.id = directory.hub_id
        LEFT JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
        {where}
        ORDER BY directory.id
        """.format(category_sql=REPORTING_CATEGORY_SQL, where=where),
        params,
    ).fetchall()
    return [_public_resolution(row) for row in rows]


def resolve_reporting_category(db, directory_id):
    """Resolve one canonical directory, returning an explicit unresolved state."""
    rows = resolve_reporting_categories(db, [directory_id])
    if rows:
        return rows[0]
    return {
        "directory_id": directory_id,
        "name": None,
        "hub_id": None,
        "hub_name": None,
        "is_main": False,
        "hub_group_id": None,
        "hub_group_code": None,
        "hub_group_name": None,
        "category_key": None,
        "category_label": NEEDS_MAPPING_LABEL,
        "resolved": False,
    }


def event_reporting_category_resolutions(db, event_id):
    """Resolve every canonical Satellite represented by one Event."""
    rows = db.execute(
        """
        SELECT directory.id directory_id, directory.name,
               hub.id hub_id, hub.name hub_name, hub.is_main,
               hub_group.id hub_group_id, hub_group.code hub_group_code,
               hub_group.name hub_group_name,
               {category_sql} category_key,
               CASE WHEN EXISTS (
                   SELECT 1
                   FROM satellites imported
                   JOIN import_batches batch
                     ON batch.id = imported.batch_id
                    AND batch.event_id = imported.event_id
                   WHERE imported.event_id = ?
                     AND imported.directory_id = directory.id
                     AND batch.status = 'active'
               ) OR EXISTS (
                   SELECT 1
                   FROM event_registrant_satellites manual_assignment
                   WHERE manual_assignment.event_id = ?
                     AND manual_assignment.directory_id = directory.id
                     AND manual_assignment.assignment_source = 'manual'
               ) THEN 1 ELSE 0 END available_in_active_batch
        FROM satellite_directory directory
        LEFT JOIN satellite_hubs hub ON hub.id = directory.hub_id
        LEFT JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
        WHERE EXISTS (
            SELECT 1 FROM satellites imported
            WHERE imported.event_id = ?
              AND imported.directory_id = directory.id
        ) OR EXISTS (
            SELECT 1 FROM event_registrant_satellites assignment
            WHERE assignment.event_id = ?
              AND assignment.directory_id = directory.id
        )
        ORDER BY COALESCE(hub_group.sort_order, 999),
                 LOWER(hub_group.name), hub_group.id,
                 LOWER(hub.name), hub.id, LOWER(directory.name), directory.id
        """.format(category_sql=REPORTING_CATEGORY_SQL),
        (event_id, event_id, event_id, event_id),
    ).fetchall()
    return [_public_resolution(row) for row in rows]
