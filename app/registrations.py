"""Focused registration records and attestation verification operations."""

import json
from datetime import datetime

from .admin_tables import (
    AdminTableQueryError,
    PER_PAGE_OPTIONS,
    SELECT_OPERATORS,
    TEXT_OPERATORS,
    _categorical_options,
    _column,
    _filter_clause,
    _json_expression,
    _parse_filters,
    resolve_batch_scope,
)
from .url_safety import safe_external_url


ATTESTATION_STATUSES = ("pending", "verified", "invalid")
MAX_REGISTRATION_FILTERS = 20
ATTESTATION_STATUS_LABELS = {
    "pending": "Pending",
    "verified": "Verified",
    "invalid": "Invalid",
}


SOURCE_HEADERS = {
    "email_address": ("Email Address",),
    "mobile_number": ("Mobile Number",),
    "shirt_size": ("Shirt Size",),
    "transportation_to_mmrc": (
        "Transportation From Ccf To Mmrc",
        "Transportation To MMRC",
    ),
    "transportation_from_mmrc": (
        "Transportation From Mmrc To Ccf",
        "Transportation From MMRC",
    ),
    "plate_number": ("Plate No", "Plate Number"),
    "attestation_form": ("Upload Your Accomplished Attestation Form Here",),
}


def _source_expression(db, field):
    expressions = [_json_expression(db, header) for header in SOURCE_HEADERS[field]]
    if len(expressions) == 1:
        return expressions[0]
    return "COALESCE({})".format(", ".join(expressions))


def _registration_column(
    key,
    label,
    expression,
    data_type="text",
    group="Registrant",
    searchable=False,
    filterable=False,
    sortable=False,
    renderer=None,
    hidden=False,
):
    column = _column(
        key,
        label,
        expression,
        data_type=data_type,
        group=group,
        default=True,
        searchable=searchable,
        renderer=renderer,
    )
    column["filterable"] = filterable
    column["sortable"] = sortable
    column["hidden"] = hidden
    return column


def registration_columns(db):
    """Return query columns, including search-only identifiers hidden from the UI."""
    return [
        _registration_column(
            "registration_code",
            "Registration Code",
            "record.registration_code",
            searchable=True,
            sortable=True,
            hidden=True,
        ),
        _registration_column(
            "ticket_code",
            "Ticket Code",
            "record.ticket_code",
            searchable=True,
            sortable=True,
            hidden=True,
        ),
        _registration_column(
            "attestation_form",
            "Attestation Form",
            _source_expression(db, "attestation_form"),
            group="Attestation & Payment",
            renderer="attestation_review",
        ),
        _registration_column(
            "attestation_status",
            "Attestation Status",
            "COALESCE(verification.status, 'pending')",
            data_type="select",
            group="Attestation & Payment",
            filterable=True,
            sortable=True,
            renderer="attestation_status",
        ),
        _registration_column(
            "payment_status",
            "Payment Status",
            "ticket.payment_status",
            data_type="select",
            group="Attestation & Payment",
            filterable=True,
            sortable=True,
            renderer="payment_status",
        ),
        _registration_column(
            "first_name",
            "First Name",
            "record.first_name",
            group="Registrant Details",
            searchable=True,
            sortable=True,
        ),
        _registration_column(
            "last_name",
            "Last Name",
            "record.last_name",
            group="Registrant Details",
            searchable=True,
            sortable=True,
        ),
        _registration_column(
            "email_address",
            "Email Address",
            _source_expression(db, "email_address"),
            group="Registrant Details",
            searchable=True,
        ),
        _registration_column(
            "mobile_number",
            "Mobile Number",
            _source_expression(db, "mobile_number"),
            group="Registrant Details",
            searchable=True,
        ),
        _registration_column(
            "gender",
            "Gender",
            "record.gender_raw",
            data_type="select",
            group="Registrant Details",
            filterable=True,
        ),
        _registration_column(
            "birth_month",
            "Birth Month",
            "record.birth_month_raw",
            data_type="select",
            group="Registrant Details",
        ),
        _registration_column(
            "birth_year",
            "Birth Year",
            "record.birth_year_raw",
            group="Registrant Details",
        ),
        _registration_column(
            "life_stage",
            "Life Stage",
            "record.life_stage_raw",
            data_type="select",
            group="Registrant Details",
        ),
        _registration_column(
            "satellite",
            "Satellite",
            "record.satellite_name",
            data_type="select",
            group="Registrant Details",
            filterable=True,
        ),
        _registration_column(
            "shirt_size",
            "Shirt Size",
            _source_expression(db, "shirt_size"),
            data_type="select",
            group="Logistics",
            filterable=True,
            sortable=True,
        ),
        _registration_column(
            "transportation_to_mmrc",
            "Transportation To MMRC",
            _source_expression(db, "transportation_to_mmrc"),
            data_type="select",
            group="Logistics",
            filterable=True,
        ),
        _registration_column(
            "transportation_from_mmrc",
            "Transportation From MMRC",
            _source_expression(db, "transportation_from_mmrc"),
            data_type="select",
            group="Logistics",
            filterable=True,
        ),
        _registration_column(
            "plate_number",
            "Plate Number",
            _source_expression(db, "plate_number"),
            group="Logistics",
        ),
        _registration_column(
            "last_reviewed_by",
            "Last Reviewed By",
            "reviewer.username",
            group="Attestation & Payment",
        ),
        _registration_column(
            "last_reviewed_at",
            "Last Reviewed At",
            "verification.updated_at",
            group="Attestation & Payment",
            renderer="reviewed_at",
        ),
    ]


def _base_sql():
    return """
        FROM registrants record
        JOIN import_batches batch ON batch.id = record.batch_id
        JOIN events event ON event.id = batch.event_id
        LEFT JOIN tickets ticket
          ON ticket.batch_id = record.batch_id
         AND ticket.ticket_code = record.ticket_code
        LEFT JOIN attestation_verifications verification
          ON verification.registrant_id = record.id
        LEFT JOIN users reviewer
          ON reviewer.id = verification.updated_by_user_id
    """


def registrations_data(db, event_id, active_batch_id, args):
    """Build one page of source registration records inside an Event boundary."""
    batch_scope = resolve_batch_scope(db, event_id, args.get("batch"), active_batch_id)
    columns = registration_columns(db)
    column_map = {column["key"]: column for column in columns}
    raw_filters = args.get("filters")
    json_filter_count = 0
    if raw_filters:
        try:
            parsed_filters = json.loads(raw_filters)
        except (TypeError, ValueError):
            parsed_filters = None
        if isinstance(parsed_filters, list):
            json_filter_count = len(parsed_filters)
    indexed_filter_count = sum(
        1 for key in args if key.startswith("filters[") and key.endswith("]")
    )
    if json_filter_count + indexed_filter_count > MAX_REGISTRATION_FILTERS:
        raise AdminTableQueryError(
            "Registrations supports at most {} filters.".format(
                MAX_REGISTRATION_FILTERS
            )
        )
    filters = _parse_filters(args, column_map)
    for item in filters:
        if not column_map[item["field"]]["filterable"]:
            raise AdminTableQueryError("That Registrations column cannot be filtered.")

    search = (args.get("search") or args.get("q") or "").strip()[:200]
    try:
        page = max(int(args.get("page", 1)), 1)
        per_page = int(args.get("per_page", 50))
    except (TypeError, ValueError):
        raise AdminTableQueryError("Pagination values must be numeric.")
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 50

    default_sort = "registration_code"
    requested_sort = args.get("sort")
    sort = requested_sort or default_sort
    if sort not in column_map or not column_map[sort]["sortable"]:
        sort = default_sort
    direction = (args.get("direction") or "asc").casefold()
    if direction not in ("asc", "desc"):
        direction = "asc"

    base_sql = _base_sql()
    conditions = ["event.id = ?"]
    params = [event_id]
    if batch_scope != "all":
        if batch_scope is None:
            conditions.append("1 = 0")
        else:
            conditions.append("record.batch_id = ?")
            params.append(batch_scope)
    options_conditions = list(conditions)
    options_params = list(params)

    if search:
        searchable = [column for column in columns if column["searchable"]]
        conditions.append(
            "(" + " OR ".join(
                "LOWER(CAST({} AS TEXT)) LIKE LOWER(?)".format(column["expression"])
                for column in searchable
            ) + ")"
        )
        params.extend(["%{}%".format(search)] * len(searchable))

    quick_filter_conditions = list(conditions)
    quick_filter_params = list(params)
    for item in filters:
        clause, values = _filter_clause(
            column_map[item["field"]], item["operator"], item["value"]
        )
        conditions.append(clause)
        params.extend(values)
        if item["field"] != "attestation_status":
            quick_filter_conditions.append(clause)
            quick_filter_params.extend(values)

    where_sql = " AND ".join(conditions)
    quick_filter_where_sql = " AND ".join(quick_filter_conditions)
    total = db.execute(
        "SELECT COUNT(*) {} WHERE {}".format(base_sql, where_sql), params
    ).fetchone()[0]
    pages = max((total + per_page - 1) // per_page, 1)
    page = min(page, pages)
    offset = (page - 1) * per_page
    selected_columns = ", ".join(
        '{} AS "{}"'.format(column["expression"], column["key"])
        for column in columns
    )
    rows = db.execute(
        "SELECT record.id AS id, record.batch_id AS batch_id, {columns} "
        "{base} WHERE {where} "
        "ORDER BY {sort} {direction}, record.id ASC LIMIT ? OFFSET ?".format(
            columns=selected_columns,
            base=base_sql,
            where=where_sql,
            sort=column_map[sort]["expression"],
            direction=direction.upper(),
        ),
        params + [per_page, offset],
    ).fetchall()

    summary = db.execute(
        """
        SELECT
            COUNT(*) AS total_registrations,
            COUNT(CASE
                WHEN COALESCE(verification.status, 'pending') = 'pending' THEN 1
            END) AS attestation_pending,
            COUNT(CASE WHEN verification.status = 'verified' THEN 1 END)
                AS attestation_verified,
            COUNT(CASE WHEN verification.status = 'invalid' THEN 1 END)
                AS attestation_invalid,
            COUNT(CASE
                WHEN LOWER(TRIM(ticket.payment_status)) = 'payment validated' THEN 1
            END) AS payment_validated
        {base} WHERE {where}
        """.format(base=base_sql, where=where_sql),
        params,
    ).fetchone()
    quick_filter_counts = db.execute(
        """
        SELECT
            COUNT(*) AS total_registrations,
            COUNT(CASE
                WHEN COALESCE(verification.status, 'pending') = 'pending' THEN 1
            END) AS attestation_pending,
            COUNT(CASE WHEN verification.status = 'verified' THEN 1 END)
                AS attestation_verified,
            COUNT(CASE WHEN verification.status = 'invalid' THEN 1 END)
                AS attestation_invalid
        {base} WHERE {where}
        """.format(base=base_sql, where=quick_filter_where_sql),
        quick_filter_params,
    ).fetchone()

    serialized_rows = []
    for row in rows:
        values = dict(row)
        values["attestation_form"] = safe_external_url(values["attestation_form"])
        serialized_rows.append(values)

    filter_columns = [column for column in columns if column["filterable"]]
    public_columns = [
        {key: value for key, value in column.items() if key != "expression"}
        for column in columns
        if not column["hidden"]
    ]
    column_options = _categorical_options(
        db, base_sql, options_conditions, options_params, filter_columns
    )
    column_options["attestation_status"] = [
        {"value": value, "label": ATTESTATION_STATUS_LABELS[value]}
        for value in ATTESTATION_STATUSES
    ]
    return {
        "batch": batch_scope,
        "columns": public_columns,
        "column_options": column_options,
        "rows": serialized_rows,
        "summary": dict(summary),
        "quick_filter_counts": dict(quick_filter_counts),
        "query": {
            "search": search,
            "filters": filters,
            "sort": sort,
            "direction": direction,
            "default_sort": default_sort,
        },
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


def update_attestation_verification(
    db,
    event_id,
    active_batch_id,
    registrant_id,
    batch_argument,
    status,
    reviewer_user_id,
):
    """Update current verification state after enforcing Event and batch ownership."""
    batch_scope = resolve_batch_scope(
        db, event_id, batch_argument, active_batch_id
    )
    registration = db.execute(
        """
        SELECT record.id, record.batch_id
        FROM registrants record
        JOIN import_batches batch ON batch.id = record.batch_id
        WHERE record.id = ? AND batch.event_id = ?
        """,
        (registrant_id, event_id),
    ).fetchone()
    if (
        registration is None
        or batch_scope is None
        or (batch_scope != "all" and registration["batch_id"] != batch_scope)
    ):
        return None
    if status not in ATTESTATION_STATUSES:
        raise AdminTableQueryError("Attestation status is invalid.")

    reviewed_at = datetime.now()
    updated = db.execute(
        """
        UPDATE attestation_verifications
        SET status = ?, updated_by_user_id = ?, updated_at = ?
        WHERE registrant_id = ?
        """,
        (status, reviewer_user_id, reviewed_at, registrant_id),
    )
    if updated.rowcount == 0:
        db.execute(
            """
            INSERT INTO attestation_verifications (
                registrant_id, status, updated_by_user_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                registrant_id,
                status,
                reviewer_user_id,
                reviewed_at,
                reviewed_at,
            ),
        )
    db.commit()
    reviewer = db.execute(
        "SELECT username FROM users WHERE id = ?", (reviewer_user_id,)
    ).fetchone()
    return {
        "batch_id": registration["batch_id"],
        "status": status,
        "label": ATTESTATION_STATUS_LABELS[status],
        "updated_by": reviewer["username"] if reviewer else None,
        "updated_at": reviewed_at.isoformat(sep=" ", timespec="seconds"),
    }


__all__ = [
    "AdminTableQueryError",
    "ATTESTATION_STATUSES",
    "ATTESTATION_STATUS_LABELS",
    "PER_PAGE_OPTIONS",
    "SELECT_OPERATORS",
    "TEXT_OPERATORS",
    "registration_columns",
    "registrations_data",
    "update_attestation_verification",
]
