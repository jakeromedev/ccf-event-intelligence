"""Fixed Event-level Satellite reporting category foundation.

Category targets and membership are durable Event configuration. Membership
uses canonical ``satellite_directory.id`` values and is deliberately
independent from an Event's active import batch.
"""

from __future__ import annotations

from dataclasses import dataclass


SATELLITE_TARGET_MAX = 1_000_000_000


@dataclass(frozen=True)
class SatelliteTargetCategoryDefinition:
    key: str
    name: str


SATELLITE_TARGET_CATEGORIES = (
    SatelliteTargetCategoryDefinition(
        "outside_metro_manila", "Outside Metro Manila Hubs"
    ),
    SatelliteTargetCategoryDefinition(
        "within_metro_manila", "Within Metro Manila Hubs"
    ),
    SatelliteTargetCategoryDefinition("main", "Main"),
)
SATELLITE_TARGET_CATEGORY_KEYS = tuple(
    category.key for category in SATELLITE_TARGET_CATEGORIES
)
SATELLITE_TARGET_CATEGORY_BY_KEY = {
    category.key: category for category in SATELLITE_TARGET_CATEGORIES
}


class SatelliteTargetCategoryValidationError(ValueError):
    """Raised when an Event category membership submission is invalid."""


def ensure_event_satellite_target_categories(db, event_id):
    """Create any missing fixed target rows for one existing Event.

    The function participates in the caller's transaction. This keeps Event
    creation atomic and lets later reads repair data created outside the normal
    application path without committing unrelated work.
    """
    existing = {
        row["category_key"]
        for row in db.execute(
            """
            SELECT category_key
            FROM event_satellite_target_categories
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchall()
    }
    missing = [
        (event_id, category.key, 0)
        for category in SATELLITE_TARGET_CATEGORIES
        if category.key not in existing
    ]
    db.executemany(
        """
        INSERT INTO event_satellite_target_categories (
            event_id, category_key, participant_target
        ) VALUES (?, ?, ?)
        """,
        missing,
    )


def satellite_target_category_rows(db, event_id):
    """Return the three fixed categories in product display order."""
    ensure_event_satellite_target_categories(db, event_id)
    stored = {
        row["category_key"]: row
        for row in db.execute(
            """
            SELECT category.id, category.event_id, category.category_key,
                   category.participant_target,
                   COUNT(membership.id) satellite_count
            FROM event_satellite_target_categories category
            LEFT JOIN event_satellite_target_satellites membership
              ON membership.event_id = category.event_id
             AND membership.category_key = category.category_key
            WHERE category.event_id = ?
            GROUP BY category.id, category.event_id, category.category_key,
                     category.participant_target
            """,
            (event_id,),
        ).fetchall()
    }
    return [
        {
            "id": stored[definition.key]["id"],
            "event_id": event_id,
            "key": definition.key,
            "name": definition.name,
            "participant_target": stored[definition.key]["participant_target"],
            "satellite_count": stored[definition.key]["satellite_count"],
        }
        for definition in SATELLITE_TARGET_CATEGORIES
    ]


def satellite_target_settings(db, event_id):
    """Return fixed categories and fully mapped canonical Satellite options."""
    categories = satellite_target_category_rows(db, event_id)
    selected_rows = db.execute(
        """
        SELECT category_key, directory_id
        FROM event_satellite_target_satellites
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchall()
    selected_by_directory = {
        row["directory_id"]: row["category_key"] for row in selected_rows
    }
    option_rows = db.execute(
        """
        SELECT directory.id directory_id, directory.name,
               hub.id hub_id, hub.name hub_name,
               hub_group.id group_id, hub_group.code group_code,
               hub_group.name group_name,
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
                   FROM event_registrant_satellites manual
                   WHERE manual.event_id = ?
                     AND manual.directory_id = directory.id
                     AND manual.assignment_source = 'manual'
               ) THEN 1 ELSE 0 END available_in_active_batch,
               CASE WHEN EXISTS (
                   SELECT 1
                   FROM satellites imported
                   WHERE imported.event_id = ?
                     AND imported.directory_id = directory.id
               ) OR EXISTS (
                   SELECT 1
                   FROM event_registrant_satellites assignment
                   WHERE assignment.event_id = ?
                     AND assignment.directory_id = directory.id
               ) THEN 1 ELSE 0 END represented_in_event
        FROM satellite_directory directory
        JOIN satellite_hubs hub ON hub.id = directory.hub_id
        JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
        WHERE EXISTS (
            SELECT 1
            FROM satellites imported
            WHERE imported.event_id = ?
              AND imported.directory_id = directory.id
        ) OR EXISTS (
            SELECT 1
            FROM event_registrant_satellites assignment
            WHERE assignment.event_id = ?
              AND assignment.directory_id = directory.id
        ) OR EXISTS (
            SELECT 1
            FROM event_satellite_target_satellites membership
            WHERE membership.event_id = ?
              AND membership.directory_id = directory.id
        )
        ORDER BY hub_group.sort_order, LOWER(hub_group.name), hub_group.id,
                 LOWER(hub.name), hub.id, LOWER(directory.name), directory.id
        """,
        (event_id, event_id, event_id, event_id, event_id, event_id, event_id),
    ).fetchall()
    options = [
        {
            **dict(row),
            "category_key": selected_by_directory.get(row["directory_id"], ""),
        }
        for row in option_rows
    ]
    selected_counts = {key: 0 for key in SATELLITE_TARGET_CATEGORY_KEYS}
    for option in options:
        if option["category_key"]:
            selected_counts[option["category_key"]] += 1
    for category in categories:
        category["selected_count"] = selected_counts[category["key"]]

    groups = []
    hubs = []
    seen_groups = set()
    seen_hubs = set()
    for option in options:
        if option["group_id"] not in seen_groups:
            groups.append(
                {
                    "id": option["group_id"],
                    "code": option["group_code"],
                    "name": option["group_name"],
                }
            )
            seen_groups.add(option["group_id"])
        if option["hub_id"] not in seen_hubs:
            hubs.append(
                {
                    "id": option["hub_id"],
                    "name": option["hub_name"],
                    "group_code": option["group_code"],
                }
            )
            seen_hubs.add(option["hub_id"])

    needs_mapping = db.execute(
        """
        SELECT COUNT(DISTINCT imported.id)
        FROM satellites imported
        JOIN import_batches batch
          ON batch.id = imported.batch_id
         AND batch.event_id = imported.event_id
        LEFT JOIN satellite_directory directory
          ON directory.id = imported.directory_id
        LEFT JOIN satellite_hubs hub ON hub.id = directory.hub_id
        LEFT JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
        WHERE imported.event_id = ? AND batch.status = 'active'
          AND (
              directory.id IS NULL OR hub.id IS NULL OR hub_group.id IS NULL
          )
        """,
        (event_id,),
    ).fetchone()[0]
    return {
        "categories": categories,
        "groups": groups,
        "hubs": hubs,
        "options": options,
        "selected_count": sum(selected_counts.values()),
        "needs_mapping_count": needs_mapping,
    }


def validate_satellite_target_memberships(db, event_id, assignments):
    """Validate a complete canonical category-assignment form snapshot."""
    parsed = {}
    malformed = False
    for assignment in assignments:
        directory_raw, separator, category_key = str(assignment or "").partition(":")
        try:
            directory_id = int(directory_raw)
        except (TypeError, ValueError):
            malformed = True
            continue
        if not separator or directory_id < 1 or directory_id in parsed:
            malformed = True
            continue
        if category_key and category_key not in SATELLITE_TARGET_CATEGORY_BY_KEY:
            malformed = True
            continue
        parsed[directory_id] = category_key
    if malformed:
        raise SatelliteTargetCategoryValidationError(
            "One or more Dashboard Target Satellite assignments are invalid."
        )

    eligible = {
        row["id"]
        for row in db.execute(
            """
            SELECT directory.id
            FROM satellite_directory directory
            JOIN satellite_hubs hub ON hub.id = directory.hub_id
            JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
            WHERE EXISTS (
                SELECT 1 FROM satellites imported
                WHERE imported.event_id = ?
                  AND imported.directory_id = directory.id
            ) OR EXISTS (
                SELECT 1 FROM event_registrant_satellites assignment
                WHERE assignment.event_id = ?
                  AND assignment.directory_id = directory.id
            ) OR EXISTS (
                SELECT 1 FROM event_satellite_target_satellites membership
                WHERE membership.event_id = ?
                  AND membership.directory_id = directory.id
            )
            """,
            (event_id, event_id, event_id),
        ).fetchall()
    }
    if set(parsed) != eligible:
        raise SatelliteTargetCategoryValidationError(
            "The canonical Satellite directory changed while this form was open. "
            "Reload the page and try again."
        )
    return [
        (directory_id, category_key)
        for directory_id, category_key in parsed.items()
        if category_key
    ]


def replace_satellite_target_memberships(db, event_id, memberships):
    """Atomically replace canonical membership inside the caller transaction."""
    ensure_event_satellite_target_categories(db, event_id)
    db.execute(
        "DELETE FROM event_satellite_target_satellites WHERE event_id = ?",
        (event_id,),
    )
    db.executemany(
        """
        INSERT INTO event_satellite_target_satellites (
            event_id, category_key, directory_id
        ) VALUES (?, ?, ?)
        """,
        [
            (event_id, category_key, directory_id)
            for directory_id, category_key in memberships
        ],
    )


def validate_satellite_target_values(form):
    """Validate the Dashboard's complete three-field target submission."""
    values = {}
    errors = []
    for category in SATELLITE_TARGET_CATEGORIES:
        raw = (form.get("target_{}".format(category.key)) or "").strip()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = None
        if value is None or value < 0:
            errors.append(
                "{} Target must be a non-negative whole number.".format(
                    category.name
                )
            )
        elif value > SATELLITE_TARGET_MAX:
            errors.append(
                "{} Target must be {:,} or fewer.".format(
                    category.name, SATELLITE_TARGET_MAX
                )
            )
        else:
            values[category.key] = value
    if errors:
        raise SatelliteTargetCategoryValidationError(" ".join(errors))
    return values


def update_satellite_target_values(db, event_id, values):
    """Update all three fixed category targets in the caller transaction."""
    if set(values) != set(SATELLITE_TARGET_CATEGORY_KEYS):
        raise SatelliteTargetCategoryValidationError(
            "All three Dashboard Satellite Targets are required."
        )
    ensure_event_satellite_target_categories(db, event_id)
    db.executemany(
        """
        UPDATE event_satellite_target_categories
        SET participant_target = ?, updated_at = CURRENT_TIMESTAMP
        WHERE event_id = ? AND category_key = ?
        """,
        [
            (values[category.key], event_id, category.key)
            for category in SATELLITE_TARGET_CATEGORIES
        ],
    )
