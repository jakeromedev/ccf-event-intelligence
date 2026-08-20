IMPORT_HISTORY_STATUSES = (
    "active",
    "validated",
    "invalid",
    "failed",
    "superseded",
    "processing",
    "validating",
)

IMPORT_HISTORY_SORTS = {
    "batch_id": "b.id",
    "created_at": "b.created_at",
    "activated_at": "b.activated_at",
    "status": "b.status",
}


def import_history(
    db,
    event_id,
    query="",
    status="all",
    page=1,
    per_page=10,
    sort="created_at",
    direction="desc",
):
    """Return one Event's safely filtered and paginated import history."""
    query = (query or "").strip()[:100]
    status = status if status in ("all",) + IMPORT_HISTORY_STATUSES else "all"
    page = max(int(page or 1), 1)
    per_page = per_page if per_page in (10, 25, 50) else 10
    sort = sort if sort in IMPORT_HISTORY_SORTS else "created_at"
    direction = direction if direction in ("asc", "desc") else "desc"

    conditions = ["b.event_id = ?"]
    params = [event_id]
    if status != "all":
        conditions.append("b.status = ?")
        params.append(status)
    if query:
        pattern = "%{}%".format(query.casefold())
        conditions.append(
            """
            (
                CAST(b.id AS TEXT) LIKE ?
                OR LOWER(COALESCE(b.event_name, '')) LIKE ?
                OR LOWER(COALESCE(b.event_slug, '')) LIKE ?
                OR EXISTS (
                    SELECT 1 FROM import_files search_file
                    WHERE search_file.batch_id = b.id
                      AND LOWER(search_file.filename) LIKE ?
                )
            )
            """
        )
        params.extend([pattern, pattern, pattern, pattern])

    where_sql = " AND ".join(conditions)
    matching = db.execute(
        "SELECT COUNT(*) FROM import_batches b WHERE {}".format(where_sql),
        params,
    ).fetchone()[0]
    event_total = db.execute(
        "SELECT COUNT(*) FROM import_batches WHERE event_id = ?", (event_id,)
    ).fetchone()[0]

    pages = max(1, (matching + per_page - 1) // per_page)
    page = min(page, pages)
    offset = (page - 1) * per_page
    order_column = IMPORT_HISTORY_SORTS[sort]
    order_sql = "{} {}".format(order_column, direction.upper())
    if sort != "batch_id":
        order_sql += ", b.id {}".format(direction.upper())

    rows = db.execute(
        """
        SELECT b.*,
               COALESCE(files.tickets_rows, 0) AS tickets_rows,
               COALESCE(files.buyers_rows, 0) AS buyers_rows,
               COALESCE(files.registrants_rows, 0) AS registrants_rows,
               COALESCE(issues.issue_count, 0) AS issue_count,
               COALESCE(issues.error_count, 0) AS error_count,
               COALESCE(issues.warning_count, 0) AS warning_count
        FROM import_batches b
        LEFT JOIN (
            SELECT batch_id,
                   MAX(CASE WHEN export_type = 'tickets' THEN total_rows END) AS tickets_rows,
                   MAX(CASE WHEN export_type = 'buyers' THEN total_rows END) AS buyers_rows,
                   MAX(CASE WHEN export_type = 'registrants' THEN total_rows END) AS registrants_rows
            FROM import_files
            GROUP BY batch_id
        ) files ON files.batch_id = b.id
        LEFT JOIN (
            SELECT batch_id,
                   COUNT(*) AS issue_count,
                   SUM(CASE WHEN severity = 'error' THEN 1 ELSE 0 END) AS error_count,
                   SUM(CASE WHEN severity = 'warning' THEN 1 ELSE 0 END) AS warning_count
            FROM validation_issues
            GROUP BY batch_id
        ) issues ON issues.batch_id = b.id
        WHERE {}
        ORDER BY {}
        LIMIT ? OFFSET ?
        """.format(where_sql, order_sql),
        params + [per_page, offset],
    ).fetchall()

    return {
        "batches": rows,
        "event_total": event_total,
        "filters": {
            "query": query,
            "status": status,
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
