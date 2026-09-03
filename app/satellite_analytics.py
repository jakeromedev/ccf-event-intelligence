"""Canonical Event-scoped Hub Group -> Hub -> Satellite analytics read model."""

from __future__ import annotations


def _percentage(value, total):
    return value / total * 100 if total else 0


HUB_CHART_COLORS = (
    "#2563eb",
    "#f97316",
    "#16a34a",
    "#7c3aed",
    "#dc2626",
    "#0891b2",
    "#db2777",
    "#ca8a04",
)


EFFECTIVE_ASSOCIATIONS_CTE = """
WITH manual_curated AS (
    SELECT DISTINCT source.curated_registrant_id, assignment.directory_id
    FROM curated_registrant_sources source
    JOIN attestation_participant_registrants owner
      ON owner.batch_id = source.batch_id
     AND owner.registrant_id = source.registrant_id
    JOIN event_registrant_satellites assignment
      ON assignment.event_id = owner.event_id
     AND assignment.attestation_participant_id = owner.attestation_participant_id
     AND assignment.assignment_source = 'manual'
), effective_associations AS (
    SELECT association.id, association.event_id, association.batch_id,
           association.curated_registrant_id, association.satellite_id,
           COALESCE(manual.directory_id, imported.directory_id) directory_id
    FROM curated_registrant_satellites association
    JOIN satellites imported ON imported.id = association.satellite_id
    LEFT JOIN manual_curated manual
      ON manual.curated_registrant_id = association.curated_registrant_id
)
"""


def _rows(db, level, where_sql, params):
    levels = {
        "satellite": (
            "directory.id, directory.name",
            "directory.id, directory.name, hubs.id, hubs.name, "
            "hub_group.id, hub_group.code, hub_group.name, hub_group.sort_order",
        ),
        "hub": (
            "hubs.id, hubs.name",
            "hubs.id, hubs.name, hub_group.id, hub_group.code, "
            "hub_group.name, hub_group.sort_order",
        ),
        "group": (
            "hub_group.id, hub_group.code, hub_group.name",
            "hub_group.id, hub_group.code, hub_group.name, hub_group.sort_order",
        ),
    }
    select_identity, group_by = levels[level]
    return db.execute(
        EFFECTIVE_ASSOCIATIONS_CTE
        + """
        SELECT {select_identity},
               {hub_columns}
               {group_columns}
               COUNT(DISTINCT curated.id) registrants,
               COUNT(association.id) associations
        FROM effective_associations association
        JOIN satellites imported ON imported.id = association.satellite_id
        JOIN satellite_directory directory ON directory.id = association.directory_id
        JOIN satellite_hubs hubs ON hubs.id = directory.hub_id
        JOIN hub_groups hub_group ON hub_group.id = hubs.hub_group_id
        JOIN curated_registrants curated
          ON curated.id = association.curated_registrant_id
         AND curated.batch_id = imported.batch_id
         AND curated.event_id = imported.event_id
        WHERE {where_sql}
        GROUP BY {group_by}
        ORDER BY hub_group.sort_order, LOWER(hub_group.name),
                 LOWER({order_name}), {order_id}
        """.format(
            select_identity=select_identity,
            hub_columns=(
                "hubs.id hub_id, hubs.name hub_name,"
                if level == "satellite"
                else ""
            ),
            group_columns=(
                "hub_group.id group_id, hub_group.code group_code, "
                "hub_group.name group_name,"
                if level in ("satellite", "hub")
                else ""
            ),
            group_by=group_by,
            where_sql=where_sql,
            order_name={
                "satellite": "directory.name",
                "hub": "hubs.name",
                "group": "hub_group.name",
            }[level],
            order_id={
                "satellite": "directory.id",
                "hub": "hubs.id",
                "group": "hub_group.id",
            }[level],
        ),
        params,
    ).fetchall()


def _positive_identifier(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def canonical_satellite_filter_options(db, batch_id):
    """Return Event-relevant canonical options for cascading dashboard filters."""
    groups = [
        dict(row)
        for row in db.execute(
            "SELECT id, code, name FROM hub_groups ORDER BY sort_order, id"
        ).fetchall()
    ]
    hubs = [
        dict(row)
        for row in db.execute(
            """
            SELECT DISTINCT hubs.id, hubs.name, hubs.hub_group_id group_id
            FROM satellites imported
            JOIN satellite_directory directory ON directory.id = imported.directory_id
            JOIN satellite_hubs hubs ON hubs.id = directory.hub_id
            JOIN hub_groups hub_group ON hub_group.id = hubs.hub_group_id
            WHERE imported.batch_id = ?
            ORDER BY LOWER(hubs.name), hubs.id
            """,
            (batch_id,),
        ).fetchall()
    ]
    satellites = [
        dict(row)
        for row in db.execute(
            """
            SELECT DISTINCT directory.id, directory.name, directory.hub_id,
                            hubs.hub_group_id group_id
            FROM satellites imported
            JOIN satellite_directory directory ON directory.id = imported.directory_id
            JOIN satellite_hubs hubs ON hubs.id = directory.hub_id
            JOIN hub_groups hub_group ON hub_group.id = hubs.hub_group_id
            WHERE imported.batch_id = ?
            ORDER BY LOWER(directory.name), directory.id
            """,
            (batch_id,),
        ).fetchall()
    ]
    manual_satellites = [
        dict(row)
        for row in db.execute(
            """
            SELECT DISTINCT directory.id, directory.name, directory.hub_id,
                            hubs.hub_group_id group_id
            FROM attestation_participant_registrants owner
            JOIN event_registrant_satellites assignment
              ON assignment.event_id = owner.event_id
             AND assignment.attestation_participant_id = owner.attestation_participant_id
             AND assignment.assignment_source = 'manual'
            JOIN satellite_directory directory ON directory.id = assignment.directory_id
            JOIN satellite_hubs hubs ON hubs.id = directory.hub_id
            WHERE owner.batch_id = ?
            ORDER BY LOWER(directory.name), directory.id
            """,
            (batch_id,),
        ).fetchall()
    ]
    satellite_ids = {item["id"] for item in satellites}
    satellites.extend(
        item for item in manual_satellites if item["id"] not in satellite_ids
    )
    hub_ids = {item["id"] for item in hubs}
    manual_hub_ids = {
        item["hub_id"] for item in manual_satellites if item["hub_id"] not in hub_ids
    }
    if manual_hub_ids:
        placeholders = ", ".join("?" for _identifier in manual_hub_ids)
        hubs.extend(
            dict(row)
            for row in db.execute(
                """
                SELECT id, name, hub_group_id group_id
                FROM satellite_hubs WHERE id IN ({})
                ORDER BY LOWER(name), id
                """.format(placeholders),
                tuple(sorted(manual_hub_ids)),
            ).fetchall()
        )
    hubs.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    satellites.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    return {"groups": groups, "hubs": hubs, "satellites": satellites}


def _filters(options, group_id, hub_id, satellite_id, link_status):
    group_id = _positive_identifier(group_id)
    hub_id = _positive_identifier(hub_id)
    satellite_id = _positive_identifier(satellite_id)
    group_ids = {item["id"] for item in options["groups"]}
    hubs = {item["id"]: item for item in options["hubs"]}
    satellites = {item["id"]: item for item in options["satellites"]}
    if group_id not in group_ids:
        group_id = None
    if hub_id not in hubs or (group_id and hubs[hub_id]["group_id"] != group_id):
        hub_id = None
    if satellite_id not in satellites:
        satellite_id = None
    elif hub_id and satellites[satellite_id]["hub_id"] != hub_id:
        satellite_id = None
    elif group_id and satellites[satellite_id]["group_id"] != group_id:
        satellite_id = None
    if link_status not in ("all", "linked", "needs_mapping"):
        link_status = "all"
    if link_status == "needs_mapping":
        group_id = None
        hub_id = None
        satellite_id = None
    group = next((item for item in options["groups"] if item["id"] == group_id), None)
    hub = hubs.get(hub_id)
    satellite = satellites.get(satellite_id)
    return {
        "group_id": group_id,
        "group_name": group["name"] if group else None,
        "hub_id": hub_id,
        "hub_name": hub["name"] if hub else None,
        "satellite_id": satellite_id,
        "satellite_name": satellite["name"] if satellite else None,
        "link_status": link_status,
        "link_status_label": {
            "all": None,
            "linked": "Linked",
            "needs_mapping": "Needs Mapping",
        }[link_status],
    }


def _where(db, batch_id, filters, query):
    clauses = ["imported.batch_id = ?"]
    params = [batch_id]
    if filters["group_id"]:
        clauses.append("hub_group.id = ?")
        params.append(filters["group_id"])
    if filters["hub_id"]:
        clauses.append("hubs.id = ?")
        params.append(filters["hub_id"])
    if filters["satellite_id"]:
        clauses.append("directory.id = ?")
        params.append(filters["satellite_id"])
    if filters["link_status"] == "linked":
        clauses.append("hub_group.id IS NOT NULL")
    elif filters["link_status"] == "needs_mapping":
        clauses.append("hub_group.id IS NULL")
    if query:
        pattern = "%{}%".format(query)
        participant_name = (
            "CONCAT(COALESCE(participant.first_name, ''), ' ', "
            "COALESCE(participant.last_name, ''))"
            if db.is_mysql
            else "COALESCE(participant.first_name, '') || ' ' || "
            "COALESCE(participant.last_name, '')"
        )
        clauses.append(
            """
            (
                LOWER(hub_group.name) LIKE LOWER(?)
                OR LOWER(hubs.name) LIKE LOWER(?)
                OR LOWER(directory.name) LIKE LOWER(?)
                OR LOWER(imported.name) LIKE LOWER(?)
                OR EXISTS (
                    SELECT 1
                    FROM curated_registrant_sources source
                    JOIN registrants participant ON participant.id = source.registrant_id
                    WHERE source.curated_registrant_id = curated.id
                      AND (
                          LOWER(TRIM({participant_name})) LIKE LOWER(?)
                          OR LOWER(participant.registration_code) LIKE LOWER(?)
                          OR LOWER(participant.source_id) LIKE LOWER(?)
                      )
                )
            )
            """.format(participant_name=participant_name)
        )
        params.extend([pattern] * 7)
    return " AND ".join(clauses), params


def _hub_chart(hubs, association_total):
    ranked = sorted(hubs, key=lambda item: (-item["associations"], item["name"].casefold()))
    if len(ranked) > 8:
        displayed = ranked[:7]
        displayed.append(
            {
                "id": None,
                "name": "Other",
                "associations": sum(item["associations"] for item in ranked[7:]),
                "registrants": None,
            }
        )
    else:
        displayed = ranked
    cursor = 0
    chart = []
    for index, item in enumerate(displayed):
        percentage = _percentage(item["associations"], association_total)
        chart.append(
            {
                **item,
                "percentage": percentage,
                "start": cursor,
                "end": cursor + percentage,
                "color": HUB_CHART_COLORS[index],
            }
        )
        cursor += percentage
    return chart


def canonical_satellite_metrics(
    db,
    batch_id,
    *,
    query="",
    group_id=None,
    hub_id=None,
    satellite_id=None,
    link_status="all",
    sort="registrants",
    direction="desc",
    page=1,
    per_page=10,
):
    """Build canonical analytics for one import batch.

    ``associations`` is the additive distribution measure. A curated person may
    appear under multiple canonical Satellites, while ``registrants`` always
    uses a distinct-person count at the reported level.
    """
    batch = db.execute(
        "SELECT id, event_id FROM import_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if batch is None:
        raise ValueError("The import batch does not exist.")
    query = " ".join(str(query or "").strip().split())[:100]
    sort = sort if sort in ("registrants", "satellite", "hub", "group") else "registrants"
    direction = direction if direction in ("asc", "desc") else "desc"
    try:
        page = max(int(page or 1), 1)
    except (TypeError, ValueError):
        page = 1
    per_page = per_page if per_page in (10, 25, 50) else 10
    options = canonical_satellite_filter_options(db, batch_id)
    filters = _filters(options, group_id, hub_id, satellite_id, link_status)
    where_sql, params = _where(db, batch_id, filters, query)

    totals = db.execute(
        EFFECTIVE_ASSOCIATIONS_CTE
        + """
        SELECT COUNT(DISTINCT CASE WHEN hub_group.id IS NOT NULL
                              THEN curated.id END) linked_registrants,
               COUNT(DISTINCT CASE WHEN hub_group.id IS NOT NULL
                              THEN hubs.id END) hubs_represented,
               COUNT(DISTINCT CASE WHEN hub_group.id IS NOT NULL
                              THEN directory.id END) satellites_represented,
               COALESCE(SUM(CASE WHEN hub_group.id IS NOT NULL
                                      AND association.id IS NOT NULL
                            THEN 1 ELSE 0 END), 0) associations,
               COUNT(DISTINCT CASE WHEN hub_group.id IS NULL
                              THEN imported.id END) needs_mapping,
               COUNT(DISTINCT CASE WHEN hub_group.id IS NULL
                              THEN curated.id END) needs_mapping_registrants,
               COALESCE(SUM(CASE WHEN hub_group.id IS NULL
                                      AND association.id IS NOT NULL
                            THEN 1 ELSE 0 END), 0) needs_mapping_associations
        FROM satellites imported
        LEFT JOIN effective_associations association
          ON association.satellite_id = imported.id
         AND association.batch_id = imported.batch_id
         AND association.event_id = imported.event_id
        LEFT JOIN satellite_directory directory
          ON directory.id = COALESCE(association.directory_id, imported.directory_id)
        LEFT JOIN satellite_hubs hubs ON hubs.id = directory.hub_id
        LEFT JOIN hub_groups hub_group ON hub_group.id = hubs.hub_group_id
        LEFT JOIN curated_registrants curated
          ON curated.id = association.curated_registrant_id
         AND curated.batch_id = imported.batch_id
         AND curated.event_id = imported.event_id
        WHERE {where_sql}
        """.format(where_sql=where_sql),
        params,
    ).fetchone()

    satellite_rows = _rows(db, "satellite", where_sql, params)
    hub_rows = _rows(db, "hub", where_sql, params)
    group_rows = _rows(db, "group", where_sql, params)
    association_total = totals["associations"] or 0

    satellites = [
        {
            "id": row["id"],
            "name": row["name"],
            "hub_id": row["hub_id"],
            "hub_name": row["hub_name"],
            "group_id": row["group_id"],
            "group_code": row["group_code"],
            "group_name": row["group_name"],
            "registrants": row["registrants"],
            "associations": row["associations"],
            "share": _percentage(row["associations"], association_total),
        }
        for row in satellite_rows
    ]
    chart_ranking = sorted(
        satellites,
        key=lambda item: (-item["registrants"], item["name"].casefold(), item["id"]),
    )
    ranking_keys = {
        "satellite": lambda item: (item["name"].casefold(), item["id"]),
        "hub": lambda item: (item["hub_name"].casefold(), item["name"].casefold()),
        "group": lambda item: (item["group_name"].casefold(), item["hub_name"].casefold()),
    }
    if sort == "registrants":
        ordered_ranking = sorted(
            satellites,
            key=lambda item: (
                -item["registrants"] if direction == "desc" else item["registrants"],
                item["name"].casefold(),
                item["id"],
            ),
        )
    else:
        ordered_ranking = sorted(
            satellites,
            key=ranking_keys[sort],
            reverse=direction == "desc",
        )
    ranking_total = len(ordered_ranking)
    ranking_pages = max(1, (ranking_total + per_page - 1) // per_page)
    page = min(page, ranking_pages)
    ranking_offset = (page - 1) * per_page
    ranking = []
    for index, item in enumerate(
        ordered_ranking[ranking_offset : ranking_offset + per_page],
        start=ranking_offset + 1,
    ):
        ranking.append({**item, "rank": index})

    hubs = [
        {
            "id": row["id"],
            "name": row["name"],
            "group_id": row["group_id"],
            "group_code": row["group_code"],
            "group_name": row["group_name"],
            "registrants": row["registrants"],
            "associations": row["associations"],
            "percentage": _percentage(row["associations"], association_total),
        }
        for row in hub_rows
    ]

    represented_groups = {
        row["id"]: {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "registrants": row["registrants"],
            "associations": row["associations"],
            "percentage": _percentage(row["associations"], association_total),
        }
        for row in group_rows
    }
    groups = []
    for row in db.execute(
        "SELECT id, code, name FROM hub_groups ORDER BY sort_order, id"
    ).fetchall():
        group = represented_groups.get(
            row["id"],
            {
                "id": row["id"],
                "code": row["code"],
                "name": row["name"],
                "registrants": 0,
                "associations": 0,
                "percentage": 0,
            },
        )
        group["hubs"] = [item for item in hubs if item["group_id"] == row["id"]]
        group["hub_count"] = len(group["hubs"])
        group["satellites"] = [
            item for item in satellites if item["group_id"] == row["id"]
        ]
        group["satellite_count"] = len(group["satellites"])
        for hub in group["hubs"]:
            hub["satellites"] = [
                item for item in satellites if item["hub_id"] == hub["id"]
            ]
            hub["satellite_count"] = len(hub["satellites"])
        groups.append(group)

    unresolved_rows = db.execute(
        EFFECTIVE_ASSOCIATIONS_CTE
        + """
        SELECT imported.id, imported.name source_name,
               imported.source_record_count, directory.id directory_id,
               directory.name canonical_name, directory.hub_id,
               hubs.id resolved_hub_id, hubs.name hub_name,
               hub_group.id group_id,
               COUNT(DISTINCT curated.id) registrants,
               COUNT(association.id) associations
        FROM satellites imported
        LEFT JOIN effective_associations association
          ON association.satellite_id = imported.id
         AND association.batch_id = imported.batch_id
         AND association.event_id = imported.event_id
        LEFT JOIN satellite_directory directory
          ON directory.id = COALESCE(association.directory_id, imported.directory_id)
        LEFT JOIN satellite_hubs hubs ON hubs.id = directory.hub_id
        LEFT JOIN hub_groups hub_group ON hub_group.id = hubs.hub_group_id
        LEFT JOIN curated_registrants curated
          ON curated.id = association.curated_registrant_id
         AND curated.batch_id = imported.batch_id
         AND curated.event_id = imported.event_id
        WHERE {where_sql} AND hub_group.id IS NULL
        GROUP BY imported.id, imported.name, imported.source_record_count,
                 directory.id, directory.name, directory.hub_id,
                 hubs.id, hubs.name, hub_group.id
        ORDER BY LOWER(imported.name), imported.id
        """.format(where_sql=where_sql),
        params,
    ).fetchall()
    needs_mapping = []
    for row in unresolved_rows:
        if row["directory_id"] is None:
            reason = "satellite_not_configured"
            status = "Satellite Not Configured"
            explanation = "Imported evidence is not linked to a canonical Satellite."
        elif row["hub_id"] is None:
            reason = "hub_unassigned"
            status = "Hub Not Found"
            explanation = "The canonical Satellite has not been assigned to a Hub."
        elif row["resolved_hub_id"] is None:
            reason = "missing_hub"
            status = "Hub Not Found"
            explanation = "The canonical Satellite references a Hub that no longer exists."
        else:
            reason = "missing_hub_group"
            status = "Hub Group Not Found"
            explanation = "The canonical Hub does not resolve to a Hub Group."
        needs_mapping.append({
            "id": row["id"],
            "source_name": row["source_name"],
            "directory_id": row["directory_id"],
            "canonical_name": row["canonical_name"],
            "hub_name": row["hub_name"],
            "reason": reason,
            "status": status,
            "explanation": explanation,
            "registrants": row["registrants"],
            "associations": row["associations"],
            # Kept explicitly as import evidence; never used as a registrant count.
            "source_record_count": row["source_record_count"],
        })

    return {
        "event_id": batch["event_id"],
        "batch_id": batch["id"],
        "query": query,
        "filters": filters,
        "options": options,
        "sort": sort,
        "direction": direction,
        "linked_registrants": totals["linked_registrants"] or 0,
        "hubs_represented": totals["hubs_represented"] or 0,
        "satellites_represented": totals["satellites_represented"] or 0,
        "association_count": association_total,
        "needs_mapping": totals["needs_mapping"] or 0,
        "needs_mapping_registrants": totals["needs_mapping_registrants"] or 0,
        "needs_mapping_associations": totals["needs_mapping_associations"] or 0,
        "hub_groups": groups,
        "hubs": hubs,
        "satellites": satellites,
        "chart_ranking": chart_ranking[:10],
        "ranking": ranking,
        "ranking_max": max((item["registrants"] for item in chart_ranking), default=0),
        "ranking_pagination": {
            "page": page,
            "pages": ranking_pages,
            "per_page": per_page,
            "total": ranking_total,
            "start": ranking_offset + 1 if ranking_total else 0,
            "end": min(ranking_offset + per_page, ranking_total),
            "has_previous": page > 1,
            "has_next": page < ranking_pages,
            "page_numbers": list(
                range(max(1, page - 2), min(ranking_pages, page + 2) + 1)
            ),
        },
        "hub_distribution": hubs,
        "hub_chart": _hub_chart(hubs, association_total),
        "needs_mapping_records": needs_mapping,
    }
