import calendar
from datetime import datetime

from .classifier import AFFILIATIONS


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
        metrics = overview_metrics(db, batch["id"]) if batch else None
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


GENDER_CATEGORIES = (
    ("male", "Male"),
    ("female", "Female"),
    ("prefer-not-to-say", "Prefer not to say"),
    ("other", "Other"),
    ("unknown", "Unknown"),
)

AGE_GROUPS = (
    ("Below 13", None, 12),
    ("13–17", 13, 17),
    ("18–24", 18, 24),
    ("25–34", 25, 34),
    ("35–44", 35, 44),
    ("45–54", 45, 54),
    ("55–64", 55, 64),
    ("65+", 65, None),
)


def normalize_gender(value):
    normalized = (value or "").strip().casefold()
    if normalized in ("male", "m"):
        return "male"
    if normalized in ("female", "f"):
        return "female"
    if normalized in (
        "prefer not to say",
        "prefer not to answer",
        "decline to answer",
        "rather not say",
    ):
        return "prefer-not-to-say"
    if not normalized:
        return "unknown"
    return "other"


def participant_profile_metrics(db, batch_id):
    """Aggregate privacy-safe gender and age profile data for one import batch."""
    rows = db.execute(
        """
        SELECT gender_raw, birth_month_raw, birth_year_raw
        FROM registrants
        WHERE batch_id = ? AND ticket_matched = 1
        """,
        (batch_id,),
    ).fetchall()
    total = len(rows)

    gender_counts = {key: 0 for key, _label in GENDER_CATEGORIES}
    for row in rows:
        gender_counts[normalize_gender(row["gender_raw"])] += 1

    gender_items = []
    cumulative = 0.0
    for key, label in GENDER_CATEGORIES:
        count = gender_counts[key]
        percentage = count / total * 100 if total else 0
        gender_items.append(
            {
                "key": key,
                "label": label,
                "count": count,
                "percentage": percentage,
                "start": cumulative,
                "end": cumulative + percentage,
            }
        )
        cumulative += percentage

    reference_date, reference_source = _profile_reference_date(db, batch_id)
    month_numbers = {
        name.casefold(): number
        for number, name in enumerate(calendar.month_name)
        if name
    }
    age_counts = {label: 0 for label, _minimum, _maximum in AGE_GROUPS}
    missing_age = 0
    invalid_age = 0
    for row in rows:
        month_raw = (row["birth_month_raw"] or "").strip()
        year_raw = (row["birth_year_raw"] or "").strip()
        if not month_raw and not year_raw:
            missing_age += 1
            continue
        try:
            birth_month = month_numbers[month_raw.casefold()]
            birth_year = int(year_raw)
            age = reference_date.year - birth_year - int(birth_month > reference_date.month)
        except (KeyError, TypeError, ValueError):
            invalid_age += 1
            continue
        if age < 0 or age > 120:
            invalid_age += 1
            continue
        for label, minimum, maximum in AGE_GROUPS:
            if (minimum is None or age >= minimum) and (maximum is None or age <= maximum):
                age_counts[label] += 1
                break

    valid_age = sum(age_counts.values())
    max_age_count = max(age_counts.values()) if age_counts else 0
    age_items = [
        {
            "label": label,
            "count": age_counts[label],
            "height": age_counts[label] / max_age_count * 100 if max_age_count else 0,
        }
        for label, _minimum, _maximum in AGE_GROUPS
    ]
    return {
        "gender": {
            "total": total,
            "items": gender_items,
        },
        "age": {
            "total": total,
            "valid": valid_age,
            "missing": missing_age,
            "invalid": invalid_age,
            "items": age_items,
            "reference_date": "{} {}, {}".format(
                reference_date.strftime("%B"), reference_date.day, reference_date.year
            ),
            "reference_source": reference_source,
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
    reference_date, _reference_source = _profile_reference_date(db, batch_id)
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
    if not (month_raw or "").strip() and not (year_raw or "").strip():
        return "Missing"
    month_numbers = {
        name.casefold(): number
        for number, name in enumerate(calendar.month_name)
        if name
    }
    try:
        birth_month = month_numbers[(month_raw or "").strip().casefold()]
        birth_year = int((year_raw or "").strip())
        age = reference_date.year - birth_year - int(birth_month > reference_date.month)
    except (KeyError, TypeError, ValueError):
        return "Invalid"
    if age < 0 or age > 120:
        return "Invalid"
    for label, minimum, maximum in AGE_GROUPS:
        if (minimum is None or age >= minimum) and (maximum is None or age <= maximum):
            return label
    return "Invalid"


def _profile_reference_date(db, batch_id):
    first_check_in = db.execute(
        "SELECT MIN(check_in_at) FROM tickets WHERE batch_id = ? AND check_in_at IS NOT NULL",
        (batch_id,),
    ).fetchone()[0]
    if first_check_in:
        try:
            return datetime.fromisoformat(first_check_in), "first recorded check-in"
        except ValueError:
            pass

    batch = db.execute(
        "SELECT activated_at, processed_at, created_at FROM import_batches WHERE id = ?",
        (batch_id,),
    ).fetchone()
    for value in (batch["activated_at"], batch["processed_at"], batch["created_at"]):
        if value:
            try:
                return datetime.fromisoformat(value), "import activation"
            except ValueError:
                continue
    return datetime.utcnow(), "import processing"


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
        filters += " AND r.affiliation = 'Local Satellite'"
    elif scope == "international":
        filters += " AND r.affiliation = 'International Satellite'"
    if query:
        filters += """
            AND (
                LOWER(r.satellite_name) LIKE LOWER(?)
                OR EXISTS (
                    SELECT 1
                    FROM registrants participant
                    WHERE participant.batch_id = r.batch_id
                      AND participant.ticket_matched = 1
                      AND participant.affiliation = r.affiliation
                      AND participant.satellite_name = r.satellite_name
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
            SELECT r.satellite_name,
                   CASE r.affiliation
                       WHEN 'Local Satellite' THEN 'Local'
                       ELSE 'International'
                   END scope,
                   COUNT(*) registrants,
                   COALESCE(SUM(r.checked_in), 0) checked_in,
                   CAST(COALESCE(SUM(r.checked_in), 0) AS REAL) / COUNT(*) * 100 attendance_rate
            FROM registrants r
            WHERE r.batch_id = ?
              AND r.ticket_matched = 1
              AND r.affiliation IN ('Local Satellite', 'International Satellite')
              {filters}
            GROUP BY r.satellite_name, r.affiliation
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
        SELECT COUNT(*) registrants,
               SUM(checked_in) checked_in,
               SUM(CASE WHEN affiliation = 'Local Satellite' THEN 1 ELSE 0 END) local_count,
               SUM(CASE WHEN affiliation = 'International Satellite' THEN 1 ELSE 0 END) international_count
        FROM registrants
        WHERE batch_id = ?
          AND ticket_matched = 1
          AND affiliation IN ('Local Satellite', 'International Satellite')
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
    """Return a privacy-limited participant list for one satellite."""
    affiliation = {
        "local": "Local Satellite",
        "international": "International Satellite",
    }.get(scope)
    if not affiliation:
        return None

    page = max(int(page or 1), 1)
    per_page = per_page if per_page in (25, 50, 100) else 50
    params = (batch_id, affiliation, satellite_name)
    total = db.execute(
        """
        SELECT COUNT(*)
        FROM registrants
        WHERE batch_id = ? AND ticket_matched = 1
          AND affiliation = ? AND satellite_name = ?
        """,
        params,
    ).fetchone()[0]
    if not total:
        return None

    checked_in = db.execute(
        """
        SELECT COALESCE(SUM(checked_in), 0)
        FROM registrants
        WHERE batch_id = ? AND ticket_matched = 1
          AND affiliation = ? AND satellite_name = ?
        """,
        params,
    ).fetchone()[0]
    pages = (total + per_page - 1) // per_page
    page = min(page, pages)
    offset = (page - 1) * per_page
    rows = db.execute(
        """
        SELECT first_name, last_name, ticket_status, checked_in
        FROM registrants
        WHERE batch_id = ? AND ticket_matched = 1
          AND affiliation = ? AND satellite_name = ?
        ORDER BY LOWER(COALESCE(last_name, '')),
                 LOWER(COALESCE(first_name, '')), id
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
        "satellite_name": satellite_name,
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
