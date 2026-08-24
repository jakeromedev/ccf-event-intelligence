"""Shared, event-scoped query layer for the administrative record tables."""

import hashlib
import json
import re


PER_PAGE_OPTIONS = (25, 50, 100)
TEXT_OPERATORS = ("contains", "equals", "starts_with", "ends_with", "is_empty", "is_not_empty")
SELECT_OPERATORS = ("equals", "in", "is_empty", "is_not_empty")
BOOLEAN_OPERATORS = ("equals",)
DATE_OPERATORS = ("exact", "before", "after", "between", "is_empty", "is_not_empty")
NUMBER_OPERATORS = ("equals", "greater_than", "less_than", "between", "is_empty", "is_not_empty")


DATASET_LABELS = {
    "registrants": "Registrants",
    "tickets": "Generated Tickets",
    "buyers": "Buyers",
    "curated": "Curated Registrants",
}


def _column(key, label, expression, data_type="text", group="Record", default=False, searchable=True):
    operators = {
        "text": TEXT_OPERATORS,
        "select": SELECT_OPERATORS,
        "boolean": BOOLEAN_OPERATORS,
        "date": DATE_OPERATORS,
        "number": NUMBER_OPERATORS,
    }[data_type]
    return {
        "key": key,
        "label": label,
        "expression": expression,
        "type": data_type,
        "group": group,
        "default": default,
        "searchable": searchable,
        "sortable": True,
        "operators": list(operators),
    }


COMMON_COLUMNS = [
    _column("event_name", "Event", "event.name", "select", "Context", True),
    _column("batch_id", "Batch", "record.batch_id", "select", "Context", True),
    _column("batch_status", "Batch Status", "batch.status", "select", "Context"),
]


DATASET_COLUMNS = {
    "registrants": [
        _column("id", "Record ID", "record.id", "number", "Identity"),
        _column("source_id", "Source Registrant ID", "record.source_id", group="Identity"),
        _column("registration_code", "Registration Code", "record.registration_code", group="Registration", default=True),
        _column("ticket_code", "Ticket Code", "record.ticket_code", group="Registration", default=True),
        _column("ticket_name_raw", "Ticket Name", "record.ticket_name_raw", "select", "Registration"),
        _column("ticket_status", "Ticket Status", "record.ticket_status", "select", "Registration", True),
        _column("registration_type", "Registration Type", "record.registration_type", "select", "Registration", True),
        _column("first_name", "First Name", "record.first_name", group="Identity", default=True),
        _column("last_name", "Last Name", "record.last_name", group="Identity", default=True),
        _column("gender_raw", "Gender", "record.gender_raw", "select", "Demographics", True),
        _column("life_stage_raw", "Life Stage", "record.life_stage_raw", "select", "Demographics"),
        _column("birth_date_raw", "Birth Date", "record.birth_date_raw", "date", "Demographics", True),
        _column("birth_month_raw", "Birth Month", "record.birth_month_raw", "select", "Demographics"),
        _column("birth_year_raw", "Birth Year", "record.birth_year_raw", "number", "Demographics"),
        _column("affiliation", "Affiliation", "record.affiliation", "select", "Church & Satellite", True),
        _column("satellite_name", "Satellite", "record.satellite_name", "select", "Church & Satellite", True),
        _column("attending_ccf_raw", "Attending CCF", "record.attending_ccf_raw", "select", "Church & Satellite"),
        _column("satellite_scope_raw", "Satellite Scope", "record.satellite_scope_raw", "select", "Church & Satellite"),
        _column("local_satellite_raw", "Local Satellite Response", "record.local_satellite_raw", "select", "Church & Satellite"),
        _column("international_satellite_raw", "International Satellite Response", "record.international_satellite_raw", "select", "Church & Satellite"),
        _column("b1g_satellite_hub_raw", "B1G Satellite Hub", "record.b1g_satellite_hub_raw", "select", "Church & Satellite"),
        _column("b1g_satellite_raw", "B1G Satellite", "record.b1g_satellite_raw", "select", "Church & Satellite"),
        _column("b1g_satellite_specify_raw", "Specified B1G Satellite", "record.b1g_satellite_specify_raw", group="Church & Satellite"),
        _column("ticket_matched", "Ticket Matched", "record.ticket_matched", "boolean", "Import", True),
        _column("checked_in", "Checked In", "record.checked_in", "boolean", "Registration", True),
        _column("event_slug", "Source Event Slug", "record.event_slug", group="Import"),
        _column("first_name_present", "First Name Present", "record.first_name_present", "boolean", "Import", searchable=False),
        _column("last_name_present", "Last Name Present", "record.last_name_present", "boolean", "Import", searchable=False),
        _column("email_present", "Email Present", "record.email_present", "boolean", "Import", searchable=False),
        _column("mobile_present", "Mobile Present", "record.mobile_present", "boolean", "Import", searchable=False),
    ],
    "tickets": [
        _column("id", "Record ID", "record.id", "number", "Identity"),
        _column("source_id", "Source Ticket ID", "record.source_id", group="Identity"),
        _column("ticket_code", "Ticket Code", "record.ticket_code", group="Ticket", default=True),
        _column("control_number", "Control Number", "record.control_number", group="Ticket", default=True),
        _column("buyer_reference", "Buyer Reference", "record.buyer_reference", group="Relationships", default=True),
        _column("ticket_status", "Ticket Status", "record.ticket_status", "select", "Ticket", True),
        _column("payment_status", "Payment Status", "record.payment_status", "select", "Payment", True),
        _column("check_in_at", "Check-In Date/Time", "record.check_in_at", "date", "Ticket", True),
        _column("event_slug", "Source Event Slug", "record.event_slug", group="Import"),
    ],
    "buyers": [
        _column("id", "Record ID", "record.id", "number", "Identity"),
        _column("source_id", "Source Buyer ID", "record.source_id", group="Identity"),
        _column("buyer_reference", "Buyer Reference", "record.buyer_reference", group="Buyer", default=True),
        _column("payment_status", "Payment Status", "record.payment_status", "select", "Payment", True),
        _column("quantity", "Quantity", "record.quantity", "number", "Buyer", True),
        _column("event_slug", "Source Event Slug", "record.event_slug", group="Import"),
    ],
}


MAPPED_SOURCE_HEADERS = {
    "registrants": {
        "ID", "Event Name", "Event Slug", "Registration Code", "Ticket Code", "Ticket Name",
        "Ticket Status", "First Name", "Last Name", "Gender", "Life Stage", "Date of Birth",
        "Birth Date", "Birth Month", "Birth Year", "Are You Attending Ccf",
        "Are You From A Local Or International Satellite", "Which Local Satellite",
        "Which International Satellite", "B1g Satellite Hub", "B1g Satellite",
        "Specify B1g Satellite",
    },
    "tickets": {
        "Id", "Slug", "Event Name", "Ticket Code", "Control Number", "Ticket Status",
        "Payment Status", "Buyer Reference Number", "Check-in Date Time",
    },
    "buyers": {
        "Id", "Slug", "Event Name", "Buyer Reference Number", "Payment Status", "Quantity",
    },
}


CURATED_COLUMNS = [
    _column("id", "Curated Registrant ID", "record.id", "number", "Identity", True),
    _column("event_id", "Event ID", "record.event_id", "number", "Context"),
    _column("event_name", "Event", "event.name", "select", "Context", True),
    _column("batch_id", "Batch", "record.batch_id", "select", "Context", True),
    _column("batch_status", "Batch Status", "batch.status", "select", "Context"),
    _column("first_name", "First Name", "representative.first_name", group="Identity", default=True),
    _column("last_name", "Last Name", "record.last_name", group="Identity", default=True),
    _column("birth_date", "Birth Date", "record.birth_date", "date", "Demographics"),
    _column("birth_month", "Birth Month", "record.birth_month", "select", "Demographics", True),
    _column("birth_year", "Birth Year", "record.birth_year", "number", "Demographics", True),
    _column("gender", "Gender", "record.gender", "select", "Demographics", True),
    _column("life_stage", "Life Stage", "record.life_stage", "select", "Demographics"),
    _column("normalized_last_name", "Normalized Last Name", "record.normalized_last_name", group="Curation"),
    _column("normalized_birth_month", "Normalized Birth Month", "record.normalized_birth_month", "select", "Curation"),
    _column("normalized_birth_year", "Normalized Birth Year", "record.normalized_birth_year", "number", "Curation"),
    _column("normalized_gender", "Normalized Gender", "record.normalized_gender", "select", "Curation"),
    _column("dedupe_key", "Match Key", "record.dedupe_key", group="Curation"),
    _column("dedupe_complete", "Identity Complete", "record.dedupe_complete", "boolean", "Curation"),
    _column("dedupe_status", "Curation Status", "record.dedupe_status", "select", "Curation"),
    _column("missing_identity_fields", "Missing Identity Fields", "record.missing_identity_fields", group="Curation"),
    _column("registration_type", "Registration Type", "record.registration_type", "select", "Registration", True),
    _column("registration_type_conflict", "Type Conflict", "record.registration_type_conflict", "boolean", "Curation"),
    _column("checked_in", "Checked In", "record.checked_in", "boolean", "Registration", True),
    _column("source_registrant_count", "Registration Sources", "record.source_registrant_count", "number", "Curation", True),
    _column("created_at", "Curated At", "record.created_at", "date", "Audit"),
    _column("updated_at", "Updated At", "record.updated_at", "date", "Audit"),
]


class AdminTableQueryError(ValueError):
    pass


def event_batches(db, event_id):
    return [
        dict(row)
        for row in db.execute(
            """
            SELECT id, status, created_at, activated_at, event_name
            FROM import_batches
            WHERE event_id = ?
            ORDER BY id DESC
            """,
            (event_id,),
        ).fetchall()
    ]


def resolve_batch_scope(db, event_id, requested_batch, active_batch_id):
    if requested_batch in (None, "", "active"):
        return active_batch_id
    if requested_batch == "all":
        return "all"
    try:
        batch_id = int(requested_batch)
    except (TypeError, ValueError):
        raise AdminTableQueryError("The selected batch is invalid.")
    exists = db.execute(
        "SELECT 1 FROM import_batches WHERE id = ? AND event_id = ?",
        (batch_id, event_id),
    ).fetchone()
    if not exists:
        raise AdminTableQueryError("The selected batch does not belong to this event.")
    return batch_id


def _raw_key(header):
    slug = re.sub(r"[^a-z0-9]+", "_", header.casefold()).strip("_")[:42] or "field"
    digest = hashlib.sha1(header.encode("utf-8")).hexdigest()[:8]
    return "source_{}_{}".format(slug, digest)


def _json_expression(db, header):
    json_path = '$."{}"'.format(header.replace('"', '\\"'))
    expression = "JSON_EXTRACT(record.source_data_json, '{}')".format(
        json_path.replace("'", "''")
    )
    return "JSON_UNQUOTE({})".format(expression) if db.is_mysql else expression


def _raw_headers(db, dataset, event_id, batch_scope):
    conditions = ["batch.event_id = ?", "record.source_data_json IS NOT NULL"]
    params = [event_id]
    if batch_scope != "all":
        if batch_scope is None:
            return []
        conditions.append("record.batch_id = ?")
        params.append(batch_scope)
    json_rows = (
        "JOIN JSON_TABLE(JSON_KEYS(record.source_data_json), '$[*]' "
        "COLUMNS (`key` VARCHAR(255) PATH '$')) source"
        if db.is_mysql
        else "JOIN json_each(record.source_data_json) source"
    )
    key_expression = "source.`key`" if db.is_mysql else "source.key"
    rows = db.execute(
        """
        SELECT DISTINCT {key_expression} AS extracted_key
        FROM {table} record
        JOIN import_batches batch ON batch.id = record.batch_id
        {json_rows}
        WHERE {conditions}
        ORDER BY {key_expression} COLLATE NOCASE
        """.format(
            table=dataset,
            json_rows=json_rows,
            key_expression=key_expression,
            conditions=" AND ".join(conditions),
        ),
        params,
    ).fetchall()
    return [row["extracted_key"] for row in rows]


def columns_for(db, dataset, event_id, batch_scope):
    if dataset == "curated":
        return [dict(column) for column in CURATED_COLUMNS]
    if dataset not in DATASET_COLUMNS:
        raise AdminTableQueryError("Unknown administrative table.")
    columns = [dict(column) for column in COMMON_COLUMNS + DATASET_COLUMNS[dataset]]
    for header in _raw_headers(db, dataset, event_id, batch_scope):
        if header in MAPPED_SOURCE_HEADERS[dataset]:
            continue
        lower = header.casefold()
        data_type = "date" if "date" in lower or lower.endswith(" at") else "number" if any(
            token in lower for token in ("amount", "quantity", "number of", "how many", "year")
        ) else "text"
        columns.append(
            _column(
                _raw_key(header),
                header,
                _json_expression(db, header),
                data_type,
                "Additional Export Fields",
            )
        )
    return columns


def _base_sql(dataset):
    if dataset == "curated":
        return """
            FROM curated_registrants record
            JOIN import_batches batch ON batch.id = record.batch_id
            JOIN events event ON event.id = record.event_id
            LEFT JOIN registrants representative ON representative.id = (
                SELECT MIN(source.registrant_id)
                FROM curated_registrant_sources source
                WHERE source.curated_registrant_id = record.id
            )
        """
    return """
        FROM {table} record
        JOIN import_batches batch ON batch.id = record.batch_id
        JOIN events event ON event.id = batch.event_id
    """.format(table=dataset)


def _parse_filters(args, column_map):
    parsed = []
    raw_json = args.get("filters")
    if raw_json:
        try:
            values = json.loads(raw_json)
        except (TypeError, ValueError):
            raise AdminTableQueryError("Filters must be valid JSON.")
        if not isinstance(values, list):
            raise AdminTableQueryError("Filters must be a list.")
        parsed.extend(values)
    for key in args:
        match = re.fullmatch(r"filters\[([^]]+)\]", key)
        if match:
            parsed.append({"field": match.group(1), "operator": "equals", "value": args.get(key)})

    clean_filters = []
    for item in parsed[:20]:
        if not isinstance(item, dict):
            raise AdminTableQueryError("Each filter must be an object.")
        field = item.get("field")
        column = column_map.get(field)
        if not column:
            raise AdminTableQueryError("A filter references an unavailable column.")
        operator = item.get("operator") or ("equals" if column["type"] in ("select", "boolean") else "contains")
        if operator not in column["operators"]:
            raise AdminTableQueryError("A filter operation is not valid for that column.")
        value = item.get("value")
        if operator not in ("is_empty", "is_not_empty") and (value is None or value == ""):
            continue
        clean_filters.append({"field": field, "operator": operator, "value": value})
    return clean_filters


def _filter_clause(column, operator, value):
    expression = column["expression"]
    if operator == "is_empty":
        return "({0} IS NULL OR TRIM(CAST({0} AS TEXT)) = '')".format(expression), []
    if operator == "is_not_empty":
        return "({0} IS NOT NULL AND TRIM(CAST({0} AS TEXT)) != '')".format(expression), []
    if operator == "contains":
        return "LOWER(CAST({} AS TEXT)) LIKE LOWER(?)".format(expression), ["%{}%".format(value)]
    if operator == "starts_with":
        return "LOWER(CAST({} AS TEXT)) LIKE LOWER(?)".format(expression), ["{}%".format(value)]
    if operator == "ends_with":
        return "LOWER(CAST({} AS TEXT)) LIKE LOWER(?)".format(expression), ["%{}".format(value)]
    if operator in ("equals", "exact"):
        if column["type"] == "boolean":
            normalized = str(value).casefold()
            if normalized not in ("1", "0", "true", "false", "yes", "no"):
                raise AdminTableQueryError("A boolean filter must be Yes or No.")
            return "{} = ?".format(expression), [1 if normalized in ("1", "true", "yes") else 0]
        if column["type"] == "number":
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                raise AdminTableQueryError("A numeric filter requires a number.")
            return "CAST({} AS REAL) = ?".format(expression), [numeric]
        if column["type"] == "date":
            return "DATE({}) = DATE(?)".format(expression), [str(value)]
        return "LOWER(CAST({} AS TEXT)) = LOWER(?)".format(expression), [str(value)]
    if operator == "in":
        values = value if isinstance(value, list) else str(value).split(",")
        values = [str(item).strip() for item in values if str(item).strip()][:50]
        if not values:
            raise AdminTableQueryError("A multi-select filter requires a value.")
        return "LOWER(CAST({} AS TEXT)) IN ({})".format(
            expression, ",".join("LOWER(?)" for _item in values)
        ), values
    if operator in ("before", "less_than", "after", "greater_than"):
        comparison = "<" if operator in ("before", "less_than") else ">"
        if column["type"] == "number":
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                raise AdminTableQueryError("A numeric filter requires a number.")
            return "CAST({} AS REAL) {} ?".format(expression, comparison), [numeric]
        return "DATE({}) {} DATE(?)".format(expression, comparison), [value]
    if operator == "between":
        values = value if isinstance(value, list) else str(value).split(",", 1)
        if len(values) != 2 or values[0] == "" or values[1] == "":
            raise AdminTableQueryError("A between filter requires two values.")
        if column["type"] == "number":
            try:
                values = [float(item) for item in values]
            except (TypeError, ValueError):
                raise AdminTableQueryError("A numeric range requires two numbers.")
            return "CAST({} AS REAL) BETWEEN ? AND ?".format(expression), values
        return "DATE({}) BETWEEN DATE(?) AND DATE(?)".format(expression), values
    raise AdminTableQueryError("Unsupported filter operation.")


def _categorical_options(db, base_sql, conditions, params, columns):
    options = {}
    for column in columns:
        if column["type"] not in ("select", "boolean"):
            continue
        if column["type"] == "boolean":
            options[column["key"]] = [
                {"value": "yes", "label": "Yes"},
                {"value": "no", "label": "No"},
            ]
            continue
        rows = db.execute(
            "SELECT DISTINCT {expression} value {base} WHERE {where} "
            "AND {expression} IS NOT NULL AND TRIM(CAST({expression} AS TEXT)) != '' "
            "ORDER BY CAST({expression} AS TEXT) COLLATE NOCASE LIMIT 200".format(
                expression=column["expression"], base=base_sql, where=" AND ".join(conditions)
            ),
            params,
        ).fetchall()
        options[column["key"]] = [
            {"value": str(row["value"]), "label": str(row["value"])} for row in rows
        ]
    return options


def admin_table_data(db, dataset, event_id, active_batch_id, args):
    batch_scope = resolve_batch_scope(db, event_id, args.get("batch"), active_batch_id)
    columns = columns_for(db, dataset, event_id, batch_scope)
    column_map = {column["key"]: column for column in columns}
    filters = _parse_filters(args, column_map)
    query = (args.get("search") or args.get("q") or "").strip()[:200]
    try:
        page = max(int(args.get("page", 1)), 1)
        per_page = int(args.get("per_page", 50))
    except (TypeError, ValueError):
        raise AdminTableQueryError("Pagination values must be numeric.")
    if per_page not in PER_PAGE_OPTIONS:
        per_page = 50
    default_sort = next(column["key"] for column in columns if column["default"])
    sort = args.get("sort") or default_sort
    if sort not in column_map or not column_map[sort]["sortable"]:
        sort = default_sort
    direction = (args.get("direction") or "asc").casefold()
    if direction not in ("asc", "desc"):
        direction = "asc"

    base_sql = _base_sql(dataset)
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

    if query:
        searchable = [column for column in columns if column["searchable"]]
        conditions.append(
            "(" + " OR ".join(
                "LOWER(CAST({} AS TEXT)) LIKE LOWER(?)".format(column["expression"])
                for column in searchable
            ) + ")"
        )
        params.extend(["%{}%".format(query)] * len(searchable))
    for item in filters:
        clause, values = _filter_clause(column_map[item["field"]], item["operator"], item["value"])
        conditions.append(clause)
        params.extend(values)

    where_sql = " AND ".join(conditions)
    total = db.execute(
        "SELECT COUNT(*) {} WHERE {}".format(base_sql, where_sql), params
    ).fetchone()[0]
    pages = max((total + per_page - 1) // per_page, 1)
    page = min(page, pages)
    offset = (page - 1) * per_page
    selected_columns = ", ".join(
        '{} AS "{}"'.format(column["expression"], column["key"]) for column in columns
    )
    rows = db.execute(
        "SELECT {columns} {base} WHERE {where} "
        "ORDER BY {sort} {direction}, record.id ASC LIMIT ? OFFSET ?".format(
            columns=selected_columns,
            base=base_sql,
            where=where_sql,
            sort=column_map[sort]["expression"],
            direction=direction.upper(),
        ),
        params + [per_page, offset],
    ).fetchall()

    public_columns = [
        {key: value for key, value in column.items() if key != "expression"}
        for column in columns
    ]
    return {
        "dataset": dataset,
        "label": DATASET_LABELS[dataset],
        "batch": batch_scope,
        "columns": public_columns,
        "column_options": _categorical_options(
            db, base_sql, options_conditions, options_params, columns
        ),
        "rows": [dict(row) for row in rows],
        "query": {
            "search": query,
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


def registration_sources(db, event_id, curated_id, batch_scope):
    conditions = ["curated.id = ?", "curated.event_id = ?"]
    params = [curated_id, event_id]
    if batch_scope != "all":
        if batch_scope is None:
            return None
        conditions.append("curated.batch_id = ?")
        params.append(batch_scope)
    curated = db.execute(
        """
        SELECT curated.*, event.name event_name, batch.status batch_status,
               representative.first_name representative_first_name
        FROM curated_registrants curated
        JOIN events event ON event.id = curated.event_id
        JOIN import_batches batch ON batch.id = curated.batch_id
        LEFT JOIN registrants representative ON representative.id = (
            SELECT MIN(source.registrant_id)
            FROM curated_registrant_sources source
            WHERE source.curated_registrant_id = curated.id
        )
        WHERE {conditions}
        """.format(conditions=" AND ".join(conditions)),
        params,
    ).fetchone()
    if curated is None:
        return None
    rows = db.execute(
        """
        SELECT raw.*, batch.status batch_status, batch.created_at import_date,
               event.id event_id, event.name event_name
        FROM curated_registrant_sources source
        JOIN registrants raw ON raw.id = source.registrant_id
        JOIN import_batches batch ON batch.id = raw.batch_id
        JOIN events event ON event.id = batch.event_id
        WHERE source.curated_registrant_id = ?
          AND source.event_id = ? AND source.batch_id = ?
        ORDER BY raw.id
        """,
        (curated_id, event_id, curated["batch_id"]),
    ).fetchall()
    source_records = []
    for row in rows:
        values = dict(row)
        raw_json = values.pop("source_data_json", None)
        source_values = {}
        if raw_json:
            try:
                source_values = json.loads(raw_json)
            except (TypeError, ValueError):
                source_values = {}
        normalized_values = {
            key: value for key, value in values.items() if key not in ("id",) and value not in (None, "")
        }
        source_records.append(
            {
                "id": row["id"],
                "registration_code": row["registration_code"],
                "event": row["event_name"],
                "event_id": row["event_id"],
                "batch_id": row["batch_id"],
                "import_date": row["import_date"],
                "source_values": source_values,
                "normalized_values": normalized_values,
            }
        )
    return {"curated_registrant": dict(curated), "sources": source_records}
