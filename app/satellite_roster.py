"""Filter and paginate the grouped Satellite Overview participant table."""

from .aggregation import _pagination_metadata
from .satellite_export import participant_contact_details, satellite_roster_rows


def satellite_participant_table(db, event_id, batch_id, *, satellite="", query="",
                                page=1, per_page=10, overview_filters=None, overview_query=""):
    rows = []
    filters = overview_filters or {}
    for record in satellite_roster_rows(db, event_id, batch_id):
        row = dict(record)
        row.update(participant_contact_details(row))
        row["name"] = " ".join(
            value for value in (row["first_name"], row["last_name"]) if value
        ) or "Name unavailable"
        row["registration_id"] = row["registration_code"] or row["source_id"] or str(row["curated_id"])
        row["satellite_key"] = (
            "directory:{}".format(row["directory_id"]) if row["directory_id"]
            else "unmapped:{}".format(row["satellite"])
        )
        if any(filters.get(key) and filters[key] != row[key]
               for key in ("group_id", "hub_id")):
            continue
        if filters.get("satellite_id") and filters["satellite_id"] != row["directory_id"]:
            continue
        status = filters.get("link_status", "all")
        if status == "linked" and row["link_status"] != "Linked":
            continue
        if status == "needs_mapping" and row["link_status"] != "Needs Mapping":
            continue
        if overview_query.casefold() not in " ".join(
            str(row.get(key) or "") for key in (
                "name", "registration_id", "satellite", "hub", "hub_group", "submitted_hub"
            )
        ).casefold():
            continue
        rows.append(row)
    rows.sort(key=lambda row: (
        row["satellite"].casefold(), row["satellite_key"], row["hub"].casefold(),
        (row["last_name"] or "").casefold(), (row["first_name"] or "").casefold(), row["curated_id"],
    ))
    options = {}
    for row in rows:
        options[row["satellite_key"]] = row["satellite"]
    query = query.strip()[:100]
    matching = [row for row in rows if
                (not satellite or row["satellite_key"] == satellite)
                and query.casefold() in " ".join(
                    row[key] for key in ("name", "registration_id", "email", "mobile_number")
                ).casefold()]
    per_page = per_page if per_page in (10, 25, 50, 100) else 10
    pagination = _pagination_metadata(len(matching), page, per_page)
    return {
        "rows": matching[pagination["offset"]:pagination["offset"] + per_page],
        "options": options, "satellite": satellite, "query": query, "pagination": pagination,
    }
