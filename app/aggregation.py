from .classifier import AFFILIATIONS
from .normalization import (
    AGE_BUCKETS,
    GENDER_CATEGORIES,
    LIFE_STAGE_CATEGORIES,
    calculate_age_at_event,
    get_age_bucket,
    normalize_gender,
    normalize_life_stage,
)


def active_batch(db, event_id):
    return db.execute(
        """
        SELECT * FROM import_batches
        WHERE event_id = ? AND status = 'active'
        ORDER BY activated_at DESC, id DESC LIMIT 1
        """,
        (event_id,),
    ).fetchone()


def event_summaries(db):
    events = db.execute("SELECT * FROM events ORDER BY updated_at DESC, id DESC").fetchall()
    summaries = []
    for event in events:
        batch = active_batch(db, event["id"])
        latest_batch = db.execute(
            """
            SELECT * FROM import_batches WHERE event_id = ?
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (event["id"],),
        ).fetchone()
        metrics = event_summary_metrics(db, batch["id"]) if batch else None
        summaries.append(
            {
                "event": event,
                "active_batch": batch,
                "latest_batch": latest_batch,
                "metrics": metrics,
                "status": "active" if batch else (latest_batch["status"] if latest_batch else "upload-required"),
                "last_import": (batch["activated_at"] if batch else latest_batch["created_at"] if latest_batch else None),
            }
        )
    return summaries


def event_summary_metrics(db, batch_id):
    """Unique-person metrics for the Event selector cards."""
    row = db.execute(
        """
        SELECT COUNT(*) total_registrants,
               COALESCE(SUM(checked_in), 0) checked_in
        FROM curated_registrants WHERE batch_id = ?
        """,
        (batch_id,),
    ).fetchone()
    total = row["total_registrants"] or 0
    checked = row["checked_in"] or 0
    raw = db.execute(
        "SELECT COUNT(*) FROM registrants WHERE batch_id = ? AND ticket_matched = 1",
        (batch_id,),
    ).fetchone()[0]
    return {
        "total_registrants": total,
        "checked_in": checked,
        "attendance_rate": checked / total * 100 if total else 0,
        "raw_registrations": raw,
    }


def overview_metrics(db, batch_id, basis="registrants"):
    checked_only = basis == "checked-in"
    where = "WHERE batch_id = ? AND ticket_matched = 1" + (" AND checked_in = 1" if checked_only else "")
    total_registrants = db.execute(
        "SELECT COUNT(*) FROM registrants WHERE batch_id = ? AND ticket_matched = 1", (batch_id,)
    ).fetchone()[0]
    checked_in = db.execute(
        "SELECT COUNT(*) FROM registrants WHERE batch_id = ? AND ticket_matched = 1 AND checked_in = 1", (batch_id,)
    ).fetchone()[0]
    rows = db.execute(
        "SELECT affiliation, COUNT(*) count FROM registrants {} GROUP BY affiliation".format(where),
        (batch_id,),
    ).fetchall()
    counts = {name: 0 for name in AFFILIATIONS}
    counts.update({row["affiliation"]: row["count"] for row in rows})
    basis_total = sum(counts.values())
    affiliation = []
    for name in AFFILIATIONS:
        count = counts[name]
        affiliation.append(
            {
                "name": name,
                "count": count,
                "percentage": (count / basis_total * 100) if basis_total else 0,
            }
        )
    return {
        "basis": basis,
        "basis_total": basis_total,
        "total_registrants": total_registrants,
        "checked_in": checked_in,
        "attendance_rate": (checked_in / total_registrants * 100) if total_registrants else 0,
        "ccf_main": counts["CCF Main"],
        "satellites": counts["Local Satellite"] + counts["International Satellite"],
        "non_ccf": counts["Non-CCF"],
        "unknown": counts["Unknown"],
        "affiliation": affiliation,
    }


def _distribution(categories, counts, total, include_segments=False):
    items = []
    cumulative = 0.0
    for key, label in categories:
        count = counts[key]
        percentage = count / total * 100 if total else 0
        item = {
            "key": key,
            "label": label,
            "count": count,
            "percentage": percentage,
        }
        if include_segments:
            item.update({"start": cumulative, "end": cumulative + percentage})
        items.append(item)
        cumulative += percentage
    return {"total": total, "items": items}


def participant_profile_metrics(db, batch_id, event_date=None):
    """Aggregate Phase 1 demographics for participants in one import batch."""
    rows = db.execute(
        """
        SELECT gender_raw, life_stage_raw, birth_date_raw,
               birth_month_raw, birth_year_raw
        FROM registrants
        WHERE batch_id = ? AND ticket_matched = 1
          AND registration_type = 'participant'
        """,
        (batch_id,),
    ).fetchall()
    total = len(rows)

    gender_counts = {key: 0 for key, _label in GENDER_CATEGORIES}
    life_stage_counts = {key: 0 for key, _label in LIFE_STAGE_CATEGORIES}
    for row in rows:
        gender_counts[normalize_gender(row["gender_raw"])] += 1
        life_stage_counts[normalize_life_stage(row["life_stage_raw"])] += 1

    age_counts = {label: 0 for label in AGE_BUCKETS}
    for row in rows:
        age = calculate_age_at_event(
            row["birth_date_raw"],
            event_date,
            row["birth_month_raw"],
            row["birth_year_raw"],
        )
        age_counts[get_age_bucket(age)] += 1

    age_items = [
        {
            "label": label,
            "count": age_counts[label],
            "percentage": age_counts[label] / total * 100 if total else 0,
        }
        for label in AGE_BUCKETS
    ]
    return {
        "gender": _distribution(
            GENDER_CATEGORIES, gender_counts, total, include_segments=True
        ),
        "life_stage": _distribution(
            LIFE_STAGE_CATEGORIES, life_stage_counts, total, include_segments=True
        ),
        "age": {
            "total": total,
            "items": age_items,
            "reference_date": event_date,
            "configured": bool(event_date),
            "unknown": age_counts["Unknown"],
            "estimated": sum(
                1
                for row in rows
                if not (row["birth_date_raw"] or "").strip()
                and (row["birth_month_raw"] or "").strip()
                and (row["birth_year_raw"] or "").strip()
                and calculate_age_at_event(
                    None, event_date, row["birth_month_raw"], row["birth_year_raw"]
                ) is not None
            ),
        },
    }


def curated_participant_profile_metrics(db, batch_id, event_date=None):
    """Aggregate participant demographics from unique curated people."""
    rows = db.execute(
        """
        SELECT gender, life_stage, birth_date, birth_month, birth_year
        FROM curated_registrants
        WHERE batch_id = ? AND registration_type = 'participant'
        """,
        (batch_id,),
    ).fetchall()
    total = len(rows)
    gender_counts = {key: 0 for key, _label in GENDER_CATEGORIES}
    life_stage_counts = {key: 0 for key, _label in LIFE_STAGE_CATEGORIES}
    age_counts = {label: 0 for label in AGE_BUCKETS}
    estimated = 0
    for row in rows:
        gender_counts[normalize_gender(row["gender"])] += 1
        life_stage_counts[normalize_life_stage(row["life_stage"])] += 1
        age = calculate_age_at_event(
            row["birth_date"], event_date, row["birth_month"], row["birth_year"]
        )
        age_counts[get_age_bucket(age)] += 1
        if (
            not (row["birth_date"] or "").strip()
            and row["birth_month"]
            and row["birth_year"]
            and age is not None
        ):
            estimated += 1
    return {
        "gender": _distribution(
            GENDER_CATEGORIES, gender_counts, total, include_segments=True
        ),
        "life_stage": _distribution(
            LIFE_STAGE_CATEGORIES, life_stage_counts, total, include_segments=True
        ),
        "age": {
            "total": total,
            "items": [
                {
                    "label": label,
                    "count": age_counts[label],
                    "percentage": age_counts[label] / total * 100 if total else 0,
                }
                for label in AGE_BUCKETS
            ],
            "reference_date": event_date,
            "configured": bool(event_date),
            "unknown": age_counts["Unknown"],
            "estimated": estimated,
        },
    }


def registration_progress(participants, participant_target):
    """Calculate participant-only progress with an explicit unconfigured state."""
    configured = participant_target is not None and participant_target > 0
    if not configured:
        return {
            "target_configured": False,
            "progress_percentage": None,
            "remaining_slots": None,
            "target_exceeded": False,
        }
    return {
        "target_configured": True,
        "progress_percentage": participants / participant_target * 100,
        "remaining_slots": max(participant_target - participants, 0),
        "target_exceeded": participants > participant_target,
    }


def satellite_dataset_metrics(db, event_id, batch_id):
    """Aggregate all Event satellite targets without per-dataset queries."""
    datasets = db.execute(
        """
        SELECT id, name, participant_target, created_at, updated_at
        FROM satellite_datasets
        WHERE event_id = ?
        ORDER BY LOWER(name), id
        """,
        (event_id,),
    ).fetchall()
    if not datasets:
        return []

    configured_satellites = {dataset["id"]: [] for dataset in datasets}
    links = db.execute(
        """
        SELECT dss.satellite_dataset_id, s.id,
               COALESCE(directory.name, s.name) name, s.affiliation,
               s.normalized_name, s.batch_id
        FROM satellite_dataset_satellites dss
        JOIN satellite_datasets d
          ON d.id = dss.satellite_dataset_id AND d.event_id = dss.event_id
        JOIN satellites s
          ON s.id = dss.satellite_id
         AND s.event_id = dss.event_id
         AND s.batch_id = dss.satellite_batch_id
        LEFT JOIN satellite_directory directory ON directory.id = s.directory_id
        WHERE d.event_id = ?
        ORDER BY dss.satellite_dataset_id, s.affiliation,
                 LOWER(COALESCE(directory.name, s.name)), s.id
        """,
        (event_id,),
    ).fetchall()
    for link in links:
        configured_satellites[link["satellite_dataset_id"]].append(
            {
                "id": link["id"],
                "name": link["name"],
                "affiliation": link["affiliation"],
                "normalized_name": link["normalized_name"],
                "available_in_active_batch": bool(
                    batch_id is not None and link["batch_id"] == batch_id
                ),
            }
        )

    counts = {dataset["id"]: 0 for dataset in datasets}
    if batch_id is not None:
        count_rows = db.execute(
            """
            SELECT d.id dataset_id, COUNT(DISTINCT cr.id) actual_participants
            FROM satellite_datasets d
            LEFT JOIN satellite_dataset_satellites dss
              ON dss.satellite_dataset_id = d.id AND dss.event_id = d.event_id
            LEFT JOIN curated_registrant_satellites crs
              ON crs.satellite_id = dss.satellite_id
             AND crs.event_id = d.event_id
             AND crs.batch_id = ?
            LEFT JOIN curated_registrants cr
              ON cr.id = crs.curated_registrant_id
             AND cr.event_id = crs.event_id
             AND cr.batch_id = crs.batch_id
             AND cr.registration_type = 'participant'
            WHERE d.event_id = ?
            GROUP BY d.id
            """,
            (batch_id, event_id),
        ).fetchall()
        counts.update(
            {
                row["dataset_id"]: row["actual_participants"] or 0
                for row in count_rows
            }
        )

    result = []
    for dataset in datasets:
        actual = counts[dataset["id"]]
        progress = registration_progress(actual, dataset["participant_target"])
        satellites = configured_satellites[dataset["id"]]
        result.append(
            {
                "id": dataset["id"],
                "name": dataset["name"],
                "participant_target": dataset["participant_target"],
                "actual_participants": actual,
                "satellite_count": len(satellites),
                "satellite_ids": [satellite["id"] for satellite in satellites],
                "satellites": satellites,
                **progress,
            }
        )
    return result


def event_dashboard_metrics(db, event_id):
    """Return the authoritative, event-scoped Phase 1 dashboard response."""
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        return None
    batch = active_batch(db, event_id)
    counts = {"participant": 0, "volunteer": 0}
    raw_registrations = 0
    source_mappings = 0
    if batch:
        rows = db.execute(
            """
            SELECT registration_type, COUNT(*) AS count
            FROM curated_registrants
            WHERE batch_id = ?
            GROUP BY registration_type
            """,
            (batch["id"],),
        ).fetchall()
        counts.update({row["registration_type"]: row["count"] for row in rows})
        raw_registrations = db.execute(
            """
            SELECT COUNT(*) FROM registrants
            WHERE batch_id = ? AND ticket_matched = 1
            """,
            (batch["id"],),
        ).fetchone()[0]
        source_mappings = db.execute(
            "SELECT COUNT(*) FROM curated_registrant_sources WHERE batch_id = ?",
            (batch["id"],),
        ).fetchone()[0]

    participants = counts["participant"]
    volunteers = counts["volunteer"]
    target = event["participant_target"]
    progress = registration_progress(participants, target)
    profile = (
        curated_participant_profile_metrics(db, batch["id"], event["event_date"])
        if batch
        else participant_profile_metrics_empty(event["event_date"])
    )
    total_registrations = participants + volunteers
    return {
        "event": {
            "id": event["id"],
            "name": event["name"],
            "event_date": event["event_date"],
        },
        "active_batch_id": batch["id"] if batch else None,
        "last_updated": batch["activated_at"] if batch else event["updated_at"],
        "overview": {
            "participants": participants,
            "volunteers": volunteers,
            "total_registrations": total_registrations,
            "unique_registrants": total_registrations,
            "raw_registrations": raw_registrations,
            "duplicate_records_merged": max(raw_registrations - total_registrations, 0),
            "participant_target": target,
            **progress,
        },
        "participant_profile": profile,
        "satellite_datasets": satellite_dataset_metrics(
            db, event_id, batch["id"] if batch else None
        ),
        "reconciliation": {
            "registrations_reconcile": total_registrations == participants + volunteers,
            "gender_reconciles": sum(item["count"] for item in profile["gender"]["items"])
            == participants,
            "life_stage_reconciles": sum(
                item["count"] for item in profile["life_stage"]["items"]
            )
            == participants,
            "age_reconciles": sum(item["count"] for item in profile["age"]["items"])
            == participants,
            "raw_to_curated_reconciles": raw_registrations
            == total_registrations + max(raw_registrations - total_registrations, 0),
            "source_traceability_reconciles": source_mappings == raw_registrations,
        },
    }


def participant_profile_metrics_empty(event_date=None):
    gender = _distribution(
        GENDER_CATEGORIES,
        {key: 0 for key, _label in GENDER_CATEGORIES},
        0,
        include_segments=True,
    )
    life_stage = _distribution(
        LIFE_STAGE_CATEGORIES,
        {key: 0 for key, _label in LIFE_STAGE_CATEGORIES},
        0,
        include_segments=True,
    )
    return {
        "gender": gender,
        "life_stage": life_stage,
        "age": {
            "total": 0,
            "items": [
                {"label": label, "count": 0, "percentage": 0} for label in AGE_BUCKETS
            ],
            "reference_date": event_date,
            "configured": bool(event_date),
            "unknown": 0,
            "estimated": 0,
        },
    }


def overview_registrants(db, batch_id):
    """Return the privacy-scoped registrant roster used by overview drill-downs."""
    rows = db.execute(
        """
        SELECT first_name, last_name, registration_code, ticket_code,
               ticket_status, affiliation, satellite_name, gender_raw,
               birth_month_raw, birth_year_raw, checked_in
        FROM registrants
        WHERE batch_id = ? AND ticket_matched = 1
        ORDER BY LOWER(COALESCE(last_name, '')),
                 LOWER(COALESCE(first_name, '')), id
        """,
        (batch_id,),
    ).fetchall()
    reference_date = db.execute(
        """
        SELECT event.event_date
        FROM import_batches batch
        JOIN events event ON event.id = batch.event_id
        WHERE batch.id = ?
        """,
        (batch_id,),
    ).fetchone()[0]
    gender_labels = {key: label for key, label in GENDER_CATEGORIES}
    registrants = []
    for row in rows:
        gender_key = normalize_gender(row["gender_raw"])
        age_group = _registrant_age_group(
            row["birth_month_raw"], row["birth_year_raw"], reference_date
        )
        registrants.append(
            {
                "name": " ".join(
                    value for value in (row["first_name"], row["last_name"]) if value
                ) or "Name unavailable",
                "registration_code": row["registration_code"],
                "ticket_code": row["ticket_code"],
                "ticket_status": row["ticket_status"] or "Unknown",
                "origin": row["affiliation"],
                "satellite": row["satellite_name"] or "—",
                "gender_key": gender_key,
                "gender": gender_labels[gender_key],
                "age_group": age_group,
                "checked_in": bool(row["checked_in"]),
            }
        )
    return registrants


def _registrant_age_group(month_raw, year_raw, reference_date):
    return get_age_bucket(
        calculate_age_at_event(None, reference_date, month_raw, year_raw)
    )


SATELLITE_SORTS = {
    "name": "satellite_name COLLATE NOCASE",
    "scope": "scope",
    "registrants": "registrants",
    "checked_in": "checked_in",
    "attendance_rate": "attendance_rate",
}


def satellite_metrics(
    db,
    batch_id,
    scope="all",
    query="",
    page=1,
    per_page=10,
    sort="registrants",
    direction="desc",
):
    scope = scope if scope in ("all", "local", "international") else "all"
    query = (query or "").strip()[:100]
    page = max(int(page or 1), 1)
    per_page = per_page if per_page in (10, 25, 50) else 10
    sort = sort if sort in SATELLITE_SORTS else "registrants"
    direction = direction if direction in ("asc", "desc") else "desc"

    filters = ""
    filter_params = [batch_id]
    if scope == "local":
        filters += " AND s.affiliation = 'Local Satellite'"
    elif scope == "international":
        filters += " AND s.affiliation = 'International Satellite'"
    if query:
        filters += """
            AND (
                LOWER(COALESCE(directory.name, s.name)) LIKE LOWER(?)
                OR EXISTS (
                    SELECT 1
                    FROM curated_registrant_sources source
                    JOIN registrants participant ON participant.id = source.registrant_id
                    WHERE source.curated_registrant_id = cr.id
                      AND LOWER(TRIM(
                          COALESCE(participant.first_name, '') || ' ' ||
                          COALESCE(participant.last_name, '')
                      )) LIKE LOWER(?)
                )
            )
        """
        pattern = "%{}%".format(query)
        filter_params.extend((pattern, pattern))

    grouped_sql = """
        WITH grouped AS (
            SELECT s.id satellite_id,
                   COALESCE(directory.name, s.name) satellite_name,
                   CASE s.affiliation
                       WHEN 'Local Satellite' THEN 'Local'
                       ELSE 'International'
                   END scope,
                   COUNT(cr.id) registrants,
                   COALESCE(SUM(cr.checked_in), 0) checked_in,
                   CAST(COALESCE(SUM(cr.checked_in), 0) AS REAL) / COUNT(cr.id) * 100 attendance_rate
            FROM satellites s
            LEFT JOIN satellite_directory directory ON directory.id = s.directory_id
            JOIN curated_registrant_satellites link ON link.satellite_id = s.id
            JOIN curated_registrants cr ON cr.id = link.curated_registrant_id
            WHERE s.batch_id = ?
              AND s.affiliation IN ('Local Satellite', 'International Satellite')
              {filters}
            GROUP BY s.id, directory.name, s.name, s.affiliation
        )
    """.format(filters=filters)

    matching = db.execute(
        grouped_sql + " SELECT COUNT(*) FROM grouped",
        filter_params,
    ).fetchone()[0]
    pages = (matching + per_page - 1) // per_page if matching else 1
    page = min(page, pages)
    offset = (page - 1) * per_page
    order_sql = SATELLITE_SORTS[sort]
    tie_breaker = (
        ", scope ASC" if sort == "name" else ", satellite_name COLLATE NOCASE ASC"
    )
    rows = db.execute(
        grouped_sql
        + " SELECT * FROM grouped ORDER BY {} {}{} LIMIT ? OFFSET ?".format(
            order_sql, direction.upper(), tie_breaker
        ),
        filter_params + [per_page, offset],
    ).fetchall()
    ranking = [
        {
            "rank": offset + index,
            "id": row["satellite_id"],
            "name": row["satellite_name"],
            "scope": row["scope"],
            "registrants": row["registrants"],
            "checked_in": row["checked_in"],
            "attendance_rate": row["attendance_rate"],
        }
        for index, row in enumerate(rows, start=1)
    ]

    totals = db.execute(
        """
        WITH associated AS (
            SELECT cr.id, cr.checked_in, s.affiliation
            FROM curated_registrants cr
            JOIN curated_registrant_satellites link ON link.curated_registrant_id = cr.id
            JOIN satellites s ON s.id = link.satellite_id
            WHERE cr.batch_id = ?
              AND s.affiliation IN ('Local Satellite', 'International Satellite')
        ), people AS (
            SELECT id, MAX(checked_in) checked_in,
                   MAX(affiliation = 'Local Satellite') has_local,
                   MAX(affiliation = 'International Satellite') has_international
            FROM associated GROUP BY id
        )
        SELECT COUNT(*) registrants,
               COALESCE(SUM(checked_in), 0) checked_in,
               COALESCE(SUM(has_local), 0) local_count,
               COALESCE(SUM(has_international), 0) international_count
        FROM people
        """,
        (batch_id,),
    ).fetchone()
    total_registrants = totals["registrants"] or 0
    total_checked = totals["checked_in"] or 0
    return {
        "scope": scope,
        "query": query,
        "sort": sort,
        "direction": direction,
        "registrants": total_registrants,
        "checked_in": total_checked,
        "attendance_rate": (total_checked / total_registrants * 100) if total_registrants else 0,
        "local_count": totals["local_count"] or 0,
        "international_count": totals["international_count"] or 0,
        "local_percentage": ((totals["local_count"] or 0) / total_registrants * 100) if total_registrants else 0,
        "international_percentage": ((totals["international_count"] or 0) / total_registrants * 100) if total_registrants else 0,
        "ranking": ranking,
        "pagination": {
            "page": page,
            "pages": pages,
            "per_page": per_page,
            "total": matching,
            "start": offset + 1 if matching else 0,
            "end": min(offset + per_page, matching),
            "has_previous": page > 1,
            "has_next": page < pages,
            "page_numbers": _pagination_numbers(page, pages),
        },
    }


def satellite_registrants(db, batch_id, satellite_name, scope, page=1, per_page=50):
    """Return a privacy-limited unique-person list for one curated satellite."""
    affiliation = {
        "local": "Local Satellite",
        "international": "International Satellite",
    }.get(scope)
    if not affiliation:
        return None

    page = max(int(page or 1), 1)
    per_page = per_page if per_page in (25, 50, 100) else 50
    satellite = db.execute(
        """
        SELECT s.id, COALESCE(directory.name, s.name) name
        FROM satellites s
        LEFT JOIN satellite_directory directory ON directory.id = s.directory_id
        WHERE s.batch_id = ? AND s.affiliation = ?
          AND COALESCE(directory.name, s.name) = ? COLLATE NOCASE
        """,
        (batch_id, affiliation, satellite_name),
    ).fetchone()
    if satellite is None:
        return None
    params = (batch_id, satellite["id"])
    total = db.execute(
        """
        SELECT COUNT(*)
        FROM curated_registrant_satellites link
        JOIN curated_registrants cr ON cr.id = link.curated_registrant_id
        WHERE cr.batch_id = ? AND link.satellite_id = ?
        """,
        params,
    ).fetchone()[0]
    if not total:
        return None

    checked_in = db.execute(
        """
        SELECT COALESCE(SUM(cr.checked_in), 0)
        FROM curated_registrant_satellites link
        JOIN curated_registrants cr ON cr.id = link.curated_registrant_id
        WHERE cr.batch_id = ? AND link.satellite_id = ?
        """,
        params,
    ).fetchone()[0]
    pages = (total + per_page - 1) // per_page
    page = min(page, pages)
    offset = (page - 1) * per_page
    rows = db.execute(
        """
        WITH representative AS (
            SELECT source.curated_registrant_id, MIN(source.registrant_id) registrant_id
            FROM curated_registrant_sources source
            WHERE source.batch_id = ?
            GROUP BY source.curated_registrant_id
        )
        SELECT raw.first_name, raw.last_name, raw.ticket_status, cr.checked_in
        FROM curated_registrant_satellites link
        JOIN curated_registrants cr ON cr.id = link.curated_registrant_id
        JOIN representative rep ON rep.curated_registrant_id = cr.id
        JOIN registrants raw ON raw.id = rep.registrant_id
        WHERE link.satellite_id = ?
        ORDER BY LOWER(COALESCE(raw.last_name, '')),
                 LOWER(COALESCE(raw.first_name, '')), cr.id
        LIMIT ? OFFSET ?
        """,
        params + (per_page, offset),
    ).fetchall()
    participants = []
    for row in rows:
        display_name = " ".join(
            value for value in (row["first_name"], row["last_name"]) if value
        ) or "Name unavailable"
        participants.append(
            {
                "name": display_name,
                "ticket_status": row["ticket_status"] or "Unknown",
                "checked_in": bool(row["checked_in"]),
            }
        )
    return {
        "satellite_name": satellite["name"],
        "scope": scope,
        "scope_label": affiliation,
        "registrants": total,
        "checked_in": checked_in,
        "attendance_rate": checked_in / total * 100 if total else 0,
        "participants": participants,
        "pagination": {
            "page": page,
            "pages": pages,
            "per_page": per_page,
            "total": total,
            "start": offset + 1,
            "end": min(offset + per_page, total),
            "has_previous": page > 1,
            "has_next": page < pages,
            "page_numbers": _pagination_numbers(page, pages),
        },
    }


def _pagination_numbers(page, pages):
    if pages <= 7:
        return list(range(1, pages + 1))
    selected = sorted({1, pages, page - 2, page - 1, page, page + 1, page + 2})
    selected = [number for number in selected if 1 <= number <= pages]
    result = []
    previous = None
    for number in selected:
        if previous is not None and number - previous > 1:
            result.append(None)
        result.append(number)
        previous = number
    return result


def _pagination_metadata(total, page, per_page):
    pages = (total + per_page - 1) // per_page if total else 1
    page = min(max(int(page or 1), 1), pages)
    offset = (page - 1) * per_page
    return {
        "page": page,
        "pages": pages,
        "per_page": per_page,
        "total": total,
        "start": offset + 1 if total else 0,
        "end": min(offset + per_page, total),
        "has_previous": page > 1,
        "has_next": page < pages,
        "page_numbers": _pagination_numbers(page, pages),
        "offset": offset,
    }


def curation_quality(db, batch_id, pages=None, per_page=10):
    """Return batch-scoped curation metrics and audit-friendly review tables."""
    pages = pages or {}
    per_page = per_page if per_page in (10, 25, 50) else 10
    summary = db.execute(
        """
        WITH satellite_counts AS (
            SELECT curated_registrant_id, COUNT(*) count
            FROM curated_registrant_satellites
            WHERE batch_id = ?
            GROUP BY curated_registrant_id
        )
        SELECT
            (SELECT COUNT(*) FROM registrants
             WHERE batch_id = ? AND ticket_matched = 1) raw_registrants,
            (SELECT COUNT(*) FROM curated_registrants
             WHERE batch_id = ?) curated_registrants,
            (SELECT COALESCE(SUM(source_registrant_count - 1), 0)
             FROM curated_registrants WHERE batch_id = ?) duplicate_records_merged,
            (SELECT COUNT(*) FROM curated_registrants
             WHERE batch_id = ? AND source_registrant_count > 1) duplicate_groups,
            (SELECT COUNT(*) FROM curated_registrants
             WHERE batch_id = ? AND dedupe_complete = 0) incomplete_identity_records,
            (SELECT COUNT(*) FROM curated_registrants
             WHERE batch_id = ? AND registration_type_conflict = 1) registration_type_conflicts,
            (SELECT COUNT(*) FROM satellite_counts WHERE count > 1) multiple_satellite_registrants,
            (SELECT COUNT(*) FROM satellites WHERE batch_id = ?) unique_satellites,
            (SELECT COUNT(*) FROM satellite_source_variations
             WHERE batch_id = ?) raw_satellite_variations,
            (SELECT COUNT(*) FROM curated_registrant_satellites
             WHERE batch_id = ?) registrant_associations
        """,
        (batch_id,) * 10,
    ).fetchone()
    summary = dict(summary)
    pagination = {
        "duplicate_groups": _pagination_metadata(
            summary["duplicate_groups"], pages.get("duplicate_groups", 1), per_page
        ),
        "incomplete_identity": _pagination_metadata(
            summary["incomplete_identity_records"],
            pages.get("incomplete_identity", 1),
            per_page,
        ),
        "satellites": _pagination_metadata(
            summary["unique_satellites"], pages.get("satellites", 1), per_page
        ),
        "multi_satellite": _pagination_metadata(
            summary["multiple_satellite_registrants"],
            pages.get("multi_satellite", 1),
            per_page,
        ),
    }

    duplicate_groups = db.execute(
        """
        SELECT cr.id, cr.last_name, cr.birth_month, cr.birth_year, cr.gender,
               cr.dedupe_key, cr.source_registrant_count, cr.checked_in,
               cr.registration_type, cr.registration_type_conflict,
               COUNT(link.satellite_id) satellite_count
        FROM curated_registrants cr
        LEFT JOIN curated_registrant_satellites link
          ON link.curated_registrant_id = cr.id
        WHERE cr.batch_id = ? AND cr.source_registrant_count > 1
        GROUP BY cr.id
        ORDER BY cr.source_registrant_count DESC, cr.dedupe_key
        LIMIT ? OFFSET ?
        """,
        (
            batch_id,
            per_page,
            pagination["duplicate_groups"]["offset"],
        ),
    ).fetchall()

    incomplete = db.execute(
        """
        SELECT cr.id, cr.last_name, cr.missing_identity_fields,
               cr.registration_type, cr.checked_in,
               raw.registration_code, raw.source_id
        FROM curated_registrants cr
        JOIN curated_registrant_sources source
          ON source.curated_registrant_id = cr.id
        JOIN registrants raw ON raw.id = source.registrant_id
        WHERE cr.batch_id = ? AND cr.dedupe_complete = 0
        ORDER BY cr.id
        LIMIT ? OFFSET ?
        """,
        (
            batch_id,
            per_page,
            pagination["incomplete_identity"]["offset"],
        ),
    ).fetchall()

    satellites = db.execute(
        """
        SELECT s.id, COALESCE(directory.name, s.name) name,
               s.normalized_name, s.affiliation,
               s.source_record_count,
               COUNT(DISTINCT variation.id) variation_count,
               COUNT(DISTINCT link.curated_registrant_id) curated_registrants,
               GROUP_CONCAT(DISTINCT variation.source_value) source_values
        FROM satellites s
        LEFT JOIN satellite_directory directory ON directory.id = s.directory_id
        LEFT JOIN satellite_source_variations variation ON variation.satellite_id = s.id
        LEFT JOIN curated_registrant_satellites link ON link.satellite_id = s.id
        WHERE s.batch_id = ?
        GROUP BY s.id, directory.name
        ORDER BY curated_registrants DESC,
                 COALESCE(directory.name, s.name) COLLATE NOCASE
        LIMIT ? OFFSET ?
        """,
        (batch_id, per_page, pagination["satellites"]["offset"]),
    ).fetchall()

    multi_satellite = db.execute(
        """
        SELECT cr.id, cr.last_name, cr.birth_month, cr.birth_year, cr.gender,
               cr.source_registrant_count,
               COUNT(link.satellite_id) satellite_count,
               GROUP_CONCAT(COALESCE(directory.name, s.name), ' | ') satellite_names
        FROM curated_registrants cr
        JOIN curated_registrant_satellites link ON link.curated_registrant_id = cr.id
        JOIN satellites s ON s.id = link.satellite_id
        LEFT JOIN satellite_directory directory ON directory.id = s.directory_id
        WHERE cr.batch_id = ?
        GROUP BY cr.id
        HAVING COUNT(link.satellite_id) > 1
        ORDER BY satellite_count DESC, cr.last_name COLLATE NOCASE
        LIMIT ? OFFSET ?
        """,
        (batch_id, per_page, pagination["multi_satellite"]["offset"]),
    ).fetchall()

    return {
        "summary": summary,
        "duplicate_groups": [dict(row) for row in duplicate_groups],
        "incomplete_identity": [dict(row) for row in incomplete],
        "satellites": [
            {
                **dict(row),
                "source_values": (
                    sorted(row["source_values"].split(","), key=str.casefold)
                    if row["source_values"]
                    else []
                ),
            }
            for row in satellites
        ],
        "multi_satellite": [
            {
                **dict(row),
                "satellite_names": (
                    row["satellite_names"].split(" | ")
                    if row["satellite_names"]
                    else []
                ),
            }
            for row in multi_satellite
        ],
        "pagination": {
            key: {name: value for name, value in metadata.items() if name != "offset"}
            for key, metadata in pagination.items()
        },
    }


def curated_registrant_detail(db, batch_id, curated_registrant_id):
    curated = db.execute(
        """
        SELECT cr.*,
               (SELECT COUNT(*) FROM curated_registrant_satellites link
                WHERE link.curated_registrant_id = cr.id) satellite_count
        FROM curated_registrants cr
        WHERE cr.id = ? AND cr.batch_id = ?
        """,
        (curated_registrant_id, batch_id),
    ).fetchone()
    if curated is None:
        return None
    sources = db.execute(
        """
        SELECT raw.id, raw.registration_code, raw.source_id,
               raw.first_name, raw.last_name, raw.satellite_name,
               raw.affiliation, raw.registration_type, raw.checked_in,
               raw.gender_raw, raw.birth_month_raw, raw.birth_year_raw
        FROM curated_registrant_sources source
        JOIN registrants raw ON raw.id = source.registrant_id
        WHERE source.curated_registrant_id = ? AND source.batch_id = ?
        ORDER BY raw.id
        """,
        (curated_registrant_id, batch_id),
    ).fetchall()
    return {"curated_registrant": dict(curated), "source_registrations": [dict(row) for row in sources]}


def satellite_curation_detail(db, batch_id, satellite_id):
    satellite = db.execute(
        """
        SELECT s.*, COALESCE(directory.name, s.name) canonical_name,
               COUNT(DISTINCT link.curated_registrant_id) curated_registrants
        FROM satellites s
        LEFT JOIN satellite_directory directory ON directory.id = s.directory_id
        LEFT JOIN curated_registrant_satellites link ON link.satellite_id = s.id
        WHERE s.id = ? AND s.batch_id = ?
        GROUP BY s.id, directory.name
        """,
        (satellite_id, batch_id),
    ).fetchone()
    if satellite is None:
        return None
    variations = db.execute(
        """
        SELECT source_value, normalized_source_value, affiliation, source_record_count
        FROM satellite_source_variations
        WHERE satellite_id = ? AND batch_id = ?
        ORDER BY source_record_count DESC, source_value COLLATE NOCASE
        """,
        (satellite_id, batch_id),
    ).fetchall()
    satellite_data = dict(satellite)
    satellite_data["name"] = satellite_data.pop("canonical_name")
    return {"satellite": satellite_data, "source_variations": [dict(row) for row in variations]}


QUALITY_LABELS = {
    "unknown_affiliation": "Unknown church affiliation",
    "incomplete_profile": "Incomplete registrant profiles",
    "contradictory_affiliation": "Contradictory CCF/satellite answers",
    "registrant_without_ticket": "Registrants without matching tickets",
    "ticket_without_registrant": "Tickets without matching registrants",
    "buyer_without_ticket": "Buyers without matching generated tickets",
    "duplicate_identifier": "Duplicate identifiers",
    "missing_identifier": "Missing identifiers",
    "invalid_csv": "Invalid import rows",
    "wrong_export_type": "Incorrect export types",
    "missing_columns": "Missing required columns",
    "event_mismatch": "Event consistency issues",
    "ticket_without_buyer": "Tickets with unmatched buyer references",
}

QUALITY_CARD_ICONS = {
    "unknown_affiliation": "unknown",
    "incomplete_profile": "person",
    "contradictory_affiliation": "warning",
    "registrant_without_ticket": "ticket",
    "ticket_without_registrant": "ticket-off",
    "buyer_without_ticket": "user-x",
    "duplicate_identifier": "duplicate",
    "invalid_csv": "document",
}

QUALITY_SORTS = {
    "severity": "CASE severity WHEN 'error' THEN 0 ELSE 1 END",
    "category": "category COLLATE NOCASE",
    "entity": "entity_type COLLATE NOCASE",
    "count": "issue_count",
    "source_identifier": "first_identifier COLLATE NOCASE",
    "row": "first_row",
}


def quality_label(category):
    return QUALITY_LABELS.get(category, category.replace("_", " ").title())


def data_quality(
    db,
    batch_id,
    query="",
    severity="all",
    category="all",
    entity="all",
    page=1,
    per_page=10,
    sort="severity",
    direction="asc",
):
    count_rows = db.execute(
        """
        SELECT category, severity, COUNT(*) count
        FROM validation_issues
        WHERE batch_id = ?
        GROUP BY category, severity
        """,
        (batch_id,),
    ).fetchall()
    counts = {}
    severity_counts = {}
    for row in count_rows:
        counts[row["category"]] = counts.get(row["category"], 0) + row["count"]
        severity_counts.setdefault(row["category"], {})[row["severity"]] = row["count"]

    required_categories = [
        "unknown_affiliation",
        "incomplete_profile",
        "contradictory_affiliation",
        "registrant_without_ticket",
        "ticket_without_registrant",
        "buyer_without_ticket",
        "duplicate_identifier",
        "invalid_csv",
    ]
    cards = [
        {
            "category": category,
            "label": QUALITY_LABELS[category],
            "count": counts.get(category, 0),
            "severity": (
                "error"
                if severity_counts.get(category, {}).get("error", 0)
                else "warning"
                if severity_counts.get(category, {}).get("warning", 0)
                else "clean"
            ),
            "icon": QUALITY_CARD_ICONS[category],
        }
        for category in required_categories
    ]

    available_category_values = [
        row["category"]
        for row in db.execute(
            """
            SELECT DISTINCT category FROM validation_issues
            WHERE batch_id = ? ORDER BY category COLLATE NOCASE
            """,
            (batch_id,),
        ).fetchall()
    ]
    available_entity_values = [
        row["entity_type"]
        for row in db.execute(
            """
            SELECT DISTINCT entity_type FROM validation_issues
            WHERE batch_id = ? ORDER BY entity_type COLLATE NOCASE
            """,
            (batch_id,),
        ).fetchall()
    ]

    query = (query or "").strip()[:100]
    severity = severity if severity in ("all", "warning", "error") else "all"
    category = category if category in available_category_values else "all"
    entity = entity if entity in available_entity_values else "all"
    page = max(int(page or 1), 1)
    per_page = per_page if per_page in (10, 25, 50) else 10
    sort = sort if sort in QUALITY_SORTS else "severity"
    direction = direction if direction in ("asc", "desc") else "asc"

    conditions = ["batch_id = ?"]
    params = [batch_id]
    if severity != "all":
        conditions.append("severity = ?")
        params.append(severity)
    if category != "all":
        conditions.append("category = ?")
        params.append(category)
    if entity != "all":
        conditions.append("entity_type = ?")
        params.append(entity)
    if query:
        pattern = "%{}%".format(query)
        search_parts = [
            "LOWER(category) LIKE LOWER(?)",
            "LOWER(message) LIKE LOWER(?)",
            "LOWER(COALESCE(source_identifier, '')) LIKE LOWER(?)",
            "LOWER(entity_type) LIKE LOWER(?)",
        ]
        search_params = [pattern, pattern, pattern, pattern]
        label_categories = [
            value
            for value in available_category_values
            if query.casefold() in quality_label(value).casefold()
        ]
        if label_categories:
            search_parts.append(
                "category IN ({})".format(", ".join("?" for _value in label_categories))
            )
            search_params.extend(label_categories)
        conditions.append("({})".format(" OR ".join(search_parts)))
        params.extend(search_params)

    where_sql = "WHERE " + " AND ".join(conditions)
    grouped_sql = """
        WITH grouped AS (
            SELECT category, severity, entity_type,
                   MIN(message) message,
                   COUNT(*) issue_count,
                   MIN(source_identifier) first_identifier,
                   MIN(source_row) first_row
            FROM validation_issues
            {where_sql}
            GROUP BY category, severity, entity_type
        )
    """.format(where_sql=where_sql)
    matching = db.execute(
        grouped_sql + " SELECT COUNT(*) FROM grouped",
        params,
    ).fetchone()[0]
    pages = (matching + per_page - 1) // per_page if matching else 1
    page = min(page, pages)
    offset = (page - 1) * per_page
    order_sql = QUALITY_SORTS[sort]
    details = db.execute(
        grouped_sql
        + """
          SELECT * FROM grouped
          ORDER BY {order_sql} {direction},
                   category COLLATE NOCASE ASC,
                   entity_type COLLATE NOCASE ASC,
                   first_row ASC
          LIMIT ? OFFSET ?
          """.format(order_sql=order_sql, direction=direction.upper()),
        params + [per_page, offset],
    ).fetchall()

    detail_items = []
    for row in details:
        sample_conditions = list(conditions) + [
            "category = ?",
            "severity = ?",
            "entity_type = ?",
            "source_identifier IS NOT NULL",
        ]
        sample_params = list(params) + [
            row["category"],
            row["severity"],
            row["entity_type"],
        ]
        samples = db.execute(
            """
            SELECT source_identifier FROM validation_issues
            WHERE {conditions}
            ORDER BY source_row, id LIMIT 5
            """.format(conditions=" AND ".join(sample_conditions)),
            sample_params,
        ).fetchall()
        detail_items.append(
            {
                "category": row["category"],
                "label": quality_label(row["category"]),
                "severity": row["severity"],
                "entity_type": row["entity_type"],
                "message": row["message"],
                "count": row["issue_count"],
                "first_row": row["first_row"],
                "samples": [sample["source_identifier"] for sample in samples],
            }
        )

    return {
        "cards": cards,
        "issue_total": sum(counts.values()),
        "details": detail_items,
        "categories": [
            {"value": value, "label": quality_label(value)}
            for value in available_category_values
        ],
        "entities": [
            {"value": value, "label": value.replace("_", " ").title()}
            for value in available_entity_values
        ],
        "filters": {
            "query": query,
            "severity": severity,
            "category": category,
            "entity": entity,
            "sort": sort,
            "direction": direction,
        },
        "pagination": {
            "page": page,
            "pages": pages,
            "per_page": per_page,
            "total": matching,
            "start": offset + 1 if matching else 0,
            "end": min(offset + per_page, matching),
            "has_previous": page > 1,
            "has_next": page < pages,
            "page_numbers": _pagination_numbers(page, pages),
        },
    }


def data_quality_issue_instances(
    db,
    batch_id,
    category,
    query="",
    severity="all",
    entity="all",
    page=1,
    per_page=10,
):
    """Return privacy-safe issue instances for one summary-card category."""
    if category not in QUALITY_CARD_ICONS:
        return None

    available_entities = [
        row["entity_type"]
        for row in db.execute(
            """
            SELECT DISTINCT entity_type
            FROM validation_issues
            WHERE batch_id = ? AND category = ?
            ORDER BY entity_type COLLATE NOCASE
            """,
            (batch_id, category),
        ).fetchall()
    ]
    query = (query or "").strip()[:100]
    severity = severity if severity in ("all", "warning", "error") else "all"
    entity = entity if entity in available_entities else "all"
    page = max(int(page or 1), 1)
    per_page = per_page if per_page in (10, 25, 50) else 10

    conditions = ["batch_id = ?", "category = ?"]
    params = [batch_id, category]
    if severity != "all":
        conditions.append("severity = ?")
        params.append(severity)
    if entity != "all":
        conditions.append("entity_type = ?")
        params.append(entity)
    if query:
        pattern = "%{}%".format(query)
        conditions.append(
            """
            (
                LOWER(message) LIKE LOWER(?)
                OR LOWER(COALESCE(source_identifier, '')) LIKE LOWER(?)
                OR LOWER(entity_type) LIKE LOWER(?)
                OR LOWER(severity) LIKE LOWER(?)
                OR CAST(COALESCE(source_row, '') AS TEXT) LIKE ?
            )
            """
        )
        params.extend((pattern, pattern, pattern, pattern, pattern))

    where_sql = "WHERE " + " AND ".join(conditions)
    total = db.execute(
        "SELECT COUNT(*) FROM validation_issues {}".format(where_sql),
        params,
    ).fetchone()[0]
    pages = (total + per_page - 1) // per_page if total else 1
    page = min(page, pages)
    offset = (page - 1) * per_page
    rows = db.execute(
        """
        SELECT severity, entity_type, source_row, source_identifier, message
        FROM validation_issues
        {where_sql}
        ORDER BY CASE severity WHEN 'error' THEN 0 ELSE 1 END,
                 COALESCE(source_row, 2147483647), id
        LIMIT ? OFFSET ?
        """.format(where_sql=where_sql),
        params + [per_page, offset],
    ).fetchall()
    return {
        "category": category,
        "label": quality_label(category),
        "entities": available_entities,
        "filters": {
            "query": query,
            "severity": severity,
            "entity": entity,
        },
        "issues": [
            {
                "severity": row["severity"],
                "entity_type": row["entity_type"],
                "source_row": row["source_row"],
                "source_identifier": row["source_identifier"] or "—",
                "message": row["message"],
            }
            for row in rows
        ],
        "pagination": {
            "page": page,
            "pages": pages,
            "per_page": per_page,
            "total": total,
            "start": offset + 1 if total else 0,
            "end": min(offset + per_page, total),
            "has_previous": page > 1,
            "has_next": page < pages,
        },
    }
