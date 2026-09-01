"""Event-scoped configuration over the existing batch-scoped satellites."""

from __future__ import annotations


SATELLITE_DATASET_NAME_MAX_LENGTH = 160
SATELLITE_DATASET_TARGET_MAX = 1_000_000_000


def satellite_dataset_options(db, event_id, batch_id):
    """Return selectable satellites from only the Event's active batch."""
    if batch_id is None:
        return []
    return [
        dict(row)
        for row in db.execute(
            """
            SELECT s.id, COALESCE(directory.name, s.name) name,
                   s.affiliation, s.normalized_name
            FROM satellites s
            LEFT JOIN satellite_directory directory ON directory.id = s.directory_id
            WHERE s.event_id = ? AND s.batch_id = ?
            ORDER BY s.affiliation, LOWER(COALESCE(directory.name, s.name)), s.id
            """,
            (event_id, batch_id),
        ).fetchall()
    ]


def validate_satellite_dataset_form(db, event_id, form, dataset_id=None):
    """Validate and normalize one create/edit submission server-side."""
    name = " ".join((form.get("name") or "").strip().split())
    target_raw = (form.get("participant_target") or "").strip()
    submitted_ids = form.getlist("satellite_ids")
    errors = []

    if not name:
        errors.append("Dataset Name is required.")
    elif len(name) > SATELLITE_DATASET_NAME_MAX_LENGTH:
        errors.append(
            "Dataset Name must be {} characters or fewer.".format(
                SATELLITE_DATASET_NAME_MAX_LENGTH
            )
        )

    participant_target = None
    if not target_raw:
        errors.append("Participant Target is required.")
    else:
        try:
            participant_target = int(target_raw)
        except ValueError:
            participant_target = -1
        if participant_target < 0:
            errors.append("Participant Target must be a non-negative whole number.")
        elif participant_target > SATELLITE_DATASET_TARGET_MAX:
            errors.append(
                "Participant Target must be {:,} or fewer.".format(
                    SATELLITE_DATASET_TARGET_MAX
                )
            )

    satellite_ids = []
    invalid_identifier = False
    for submitted in submitted_ids:
        try:
            identifier = int(submitted)
            if identifier <= 0:
                raise ValueError
        except (TypeError, ValueError):
            invalid_identifier = True
            continue
        if identifier not in satellite_ids:
            satellite_ids.append(identifier)
    if invalid_identifier:
        errors.append("One or more selected satellites are invalid.")
    if not satellite_ids:
        errors.append("Select at least one satellite.")

    satellites = []
    if satellite_ids:
        placeholders = ", ".join("?" for _identifier in satellite_ids)
        satellites = db.execute(
            """
            SELECT id, event_id, batch_id, name
            FROM satellites
            WHERE id IN ({}) AND event_id = ?
            """.format(placeholders),
            tuple(satellite_ids) + (event_id,),
        ).fetchall()
        if len(satellites) != len(satellite_ids):
            errors.append(
                "Every selected satellite must belong to the current Event."
            )

    if name:
        duplicate_params = [event_id, name]
        duplicate_sql = (
            "SELECT id FROM satellite_datasets "
            "WHERE event_id = ? AND LOWER(name) = LOWER(?)"
        )
        if dataset_id is not None:
            duplicate_sql += " AND id <> ?"
            duplicate_params.append(dataset_id)
        if db.execute(duplicate_sql, tuple(duplicate_params)).fetchone():
            errors.append("A Satellite Dataset with that name already exists for this Event.")

    return {
        "name": name,
        "participant_target": participant_target,
        "satellites": satellites,
    }, errors


def create_satellite_dataset(db, event_id, values):
    cursor = db.execute(
        """
        INSERT INTO satellite_datasets (event_id, name, participant_target)
        VALUES (?, ?, ?)
        """,
        (event_id, values["name"], values["participant_target"]),
    )
    dataset_id = cursor.lastrowid
    _replace_satellite_links(db, event_id, dataset_id, values["satellites"])
    return dataset_id


def update_satellite_dataset(db, event_id, dataset_id, values):
    db.execute(
        """
        UPDATE satellite_datasets
        SET name = ?, participant_target = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND event_id = ?
        """,
        (values["name"], values["participant_target"], dataset_id, event_id),
    )
    _replace_satellite_links(db, event_id, dataset_id, values["satellites"])


def delete_satellite_dataset(db, event_id, dataset_id):
    return db.execute(
        "DELETE FROM satellite_datasets WHERE id = ? AND event_id = ?",
        (dataset_id, event_id),
    ).rowcount


def _replace_satellite_links(db, event_id, dataset_id, satellites):
    db.execute(
        "DELETE FROM satellite_dataset_satellites WHERE satellite_dataset_id = ?",
        (dataset_id,),
    )
    db.executemany(
        """
        INSERT INTO satellite_dataset_satellites (
            event_id, satellite_dataset_id, satellite_batch_id, satellite_id
        ) VALUES (?, ?, ?, ?)
        """,
        [
            (event_id, dataset_id, satellite["batch_id"], satellite["id"])
            for satellite in satellites
        ],
    )


def capture_rebuilt_batch_links(db, batch_id):
    """Capture links that cascade when curation rebuilds this batch's satellites."""
    return [
        (row["satellite_dataset_id"], row["normalized_name"])
        for row in db.execute(
            """
            SELECT dss.satellite_dataset_id, s.normalized_name
            FROM satellite_dataset_satellites dss
            JOIN satellites s ON s.id = dss.satellite_id
            WHERE s.batch_id = ?
            ORDER BY dss.id
            """,
            (batch_id,),
        ).fetchall()
    ]


def restore_rebuilt_batch_links(db, event_id, batch_id, captured_links):
    """Restore selections after the same batch's satellite rows are rebuilt."""
    if not captured_links:
        return
    satellites = {
        row["normalized_name"]: row["id"]
        for row in db.execute(
            "SELECT id, normalized_name FROM satellites WHERE event_id = ? AND batch_id = ?",
            (event_id, batch_id),
        ).fetchall()
    }
    rows = [
        (event_id, dataset_id, batch_id, satellites[normalized_name])
        for dataset_id, normalized_name in captured_links
        if normalized_name in satellites
    ]
    db.executemany(
        """
        INSERT INTO satellite_dataset_satellites (
            event_id, satellite_dataset_id, satellite_batch_id, satellite_id
        ) VALUES (?, ?, ?, ?)
        """,
        rows,
    )


def remap_satellite_dataset_links(db, event_id, new_batch_id):
    """Move matching Event selections to equivalent satellites in a new batch.

    Links whose normalized identity does not occur in the new batch remain on
    their historical satellite. They therefore contribute zero to active-batch
    metrics but can be remapped automatically by a later import.
    """
    new_satellites = {
        row["normalized_name"]: row["id"]
        for row in db.execute(
            "SELECT id, normalized_name FROM satellites WHERE event_id = ? AND batch_id = ?",
            (event_id, new_batch_id),
        ).fetchall()
    }
    if not new_satellites:
        return
    links = db.execute(
        """
        SELECT dss.id, dss.satellite_dataset_id, dss.satellite_id,
               s.normalized_name
        FROM satellite_dataset_satellites dss
        JOIN satellite_datasets d
          ON d.id = dss.satellite_dataset_id AND d.event_id = dss.event_id
        JOIN satellites s ON s.id = dss.satellite_id
        WHERE d.event_id = ?
        ORDER BY dss.id
        """,
        (event_id,),
    ).fetchall()
    for link in links:
        new_satellite_id = new_satellites.get(link["normalized_name"])
        if new_satellite_id is None or new_satellite_id == link["satellite_id"]:
            continue
        duplicate = db.execute(
            """
            SELECT id FROM satellite_dataset_satellites
            WHERE satellite_dataset_id = ? AND satellite_id = ? AND id <> ?
            """,
            (link["satellite_dataset_id"], new_satellite_id, link["id"]),
        ).fetchone()
        if duplicate:
            db.execute(
                "DELETE FROM satellite_dataset_satellites WHERE id = ?",
                (link["id"],),
            )
        else:
            db.execute(
                """
                UPDATE satellite_dataset_satellites
                SET satellite_id = ?, satellite_batch_id = ?
                WHERE id = ? AND event_id = ?
                """,
                (new_satellite_id, new_batch_id, link["id"], event_id),
            )
