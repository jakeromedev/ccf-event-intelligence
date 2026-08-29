"""Event-safe Phase 3 aggregate analytics.

Raw imports remain immutable.  This module extracts a deliberately small set of
analytical fields and applies conservative, documented classifications in one
place so dashboard and API consumers cannot drift apart.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .normalization import calculate_age_at_event, get_age_bucket, normalize_gender, normalize_life_stage


UNKNOWN = "Unknown"
CONFLICTING = "Conflicting / multiple values"
FILTER_DIMENSIONS = (
    "gender",
    "life_stage",
    "age_group",
    "payment_status",
    "payment_method",
    "occupation",
    "dgroup",
    "home_area",
    "check_in",
    "satellite",
    "satellite_dataset",
)


class AnalyticsFilterError(ValueError):
    """Raised when a requested filter is outside the Event's allowed values."""


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _canonical_label(value):
    value = _clean(value)
    return value.casefold()


def normalize_payment_status(value):
    """Normalize only formatting variants; retain the source business label."""
    value = _clean(value)
    if not value:
        return UNKNOWN
    known = {
        "payment validated": "Payment Validated",
        "payment failed": "Payment Failed",
        "payment cancelled": "Payment Cancelled",
        "payment canceled": "Payment Cancelled",
    }
    return known.get(value.casefold(), value)


def normalize_payment_method(value):
    value = _clean(value)
    if not value:
        return UNKNOWN
    known = {
        "debit or credit card": "Debit or Credit Card",
        "bank transfer": "Bank Transfer",
        "bills payment": "Bills Payment",
        "cash": "Cash",
    }
    return known.get(value.casefold(), value)


def normalize_profile_value(value):
    """Normalize casing/spacing without inventing profile classifications."""
    value = re.sub(r"\s*/\s*", "/", _clean(value))
    if not value:
        return UNKNOWN
    value = value.title()
    for label in ("IT", "BPO", "NGO", "HR", "CCF"):
        value = re.sub(r"\b{}\b".format(label.title()), label, value)
    return value


def normalize_yes_no(value):
    value = _canonical_label(value)
    if value in {"yes", "y", "true", "1"}:
        return "yes"
    if value in {"no", "n", "false", "0"}:
        return "no"
    return "unknown"


def classify_dgroup(member_value, leader_value):
    member = normalize_yes_no(member_value)
    leader = normalize_yes_no(leader_value)
    if member == "yes" and leader == "yes":
        return "Dgroup Leader"
    if member == "yes" and leader in {"no", "unknown"}:
        return "Dgroup Member"
    if member == "no" and leader in {"no", "unknown"}:
        return "Not in Dgroup"
    if member == "unknown" and leader == "unknown":
        return UNKNOWN
    return CONFLICTING


def _json_expression(db, alias, header):
    path = '$."{}"'.format(header.replace('"', '\\"')).replace("'", "''")
    expression = "JSON_EXTRACT({}.source_data_json, '{}')".format(alias, path)
    return "JSON_UNQUOTE({})".format(expression) if db.is_mysql else expression


def _resolved(values, normalizer):
    normalized = {normalizer(value) for value in values if _clean(value)}
    if not normalized:
        return UNKNOWN
    if len(normalized) > 1:
        return CONFLICTING
    return normalized.pop()


def _participants(db, event_id, batch_id, event_date):
    occupation = _json_expression(db, "r", "Occupation")
    home_area = _json_expression(db, "r", "Home Area")
    dgroup_member = _json_expression(db, "r", "Are You Part Of A Discipleship Group")
    dgroup_leader = _json_expression(db, "r", "Are You Leading A Discipleship Group")
    payment_method = _json_expression(db, "b", "Payment Method")
    rows = db.execute(
        """
        SELECT cr.id curated_id, cr.gender, cr.life_stage, cr.birth_date,
               cr.birth_month, cr.birth_year, cr.checked_in,
               t.payment_status ticket_payment_status,
               b.payment_status buyer_payment_status,
               {payment_method} payment_method,
               {occupation} occupation,
               {home_area} home_area,
               {dgroup_member} dgroup_member,
               {dgroup_leader} dgroup_leader
        FROM curated_registrants cr
        JOIN curated_registrant_sources source
          ON source.event_id = cr.event_id AND source.batch_id = cr.batch_id
         AND source.curated_registrant_id = cr.id
        JOIN registrants r
          ON r.batch_id = source.batch_id AND r.id = source.registrant_id
        LEFT JOIN tickets t
          ON t.batch_id = r.batch_id AND t.ticket_code = r.ticket_code
        LEFT JOIN buyers b
          ON b.batch_id = t.batch_id AND b.buyer_reference = t.buyer_reference
        WHERE cr.event_id = ? AND cr.batch_id = ?
          AND cr.registration_type = 'participant'
        ORDER BY cr.id, source.id
        """.format(
            payment_method=payment_method,
            occupation=occupation,
            home_area=home_area,
            dgroup_member=dgroup_member,
            dgroup_leader=dgroup_leader,
        ),
        (event_id, batch_id),
    ).fetchall()

    sources = defaultdict(list)
    curated = {}
    for row in rows:
        curated[row["curated_id"]] = row
        sources[row["curated_id"]].append(row)

    satellite_rows = db.execute(
        """
        SELECT crs.curated_registrant_id, s.id, s.name
        FROM curated_registrant_satellites crs
        JOIN satellites s
          ON s.event_id = crs.event_id AND s.batch_id = crs.batch_id
         AND s.id = crs.satellite_id
        WHERE crs.event_id = ? AND crs.batch_id = ?
        ORDER BY crs.curated_registrant_id, LOWER(s.name), s.id
        """,
        (event_id, batch_id),
    ).fetchall()
    satellites = defaultdict(list)
    for row in satellite_rows:
        satellites[row["curated_registrant_id"]].append(
            {"id": str(row["id"]), "name": row["name"]}
        )

    result = []
    for curated_id, row in curated.items():
        source_rows = sources[curated_id]
        payment_status = _resolved(
            [
                item["ticket_payment_status"]
                if _clean(item["ticket_payment_status"])
                else item["buyer_payment_status"]
                for item in source_rows
            ],
            normalize_payment_status,
        )
        payment_method_value = _resolved(
            [item["payment_method"] for item in source_rows], normalize_payment_method
        )
        occupation_value = _resolved(
            [item["occupation"] for item in source_rows], normalize_profile_value
        )
        home_area_value = _resolved(
            [item["home_area"] for item in source_rows], normalize_profile_value
        )
        dgroups = {
            classify_dgroup(item["dgroup_member"], item["dgroup_leader"])
            for item in source_rows
        }
        dgroup_value = dgroups.pop() if len(dgroups) == 1 else CONFLICTING
        age = calculate_age_at_event(
            row["birth_date"], event_date, row["birth_month"], row["birth_year"]
        )
        person_satellites = satellites[curated_id]
        result.append(
            {
                "gender": normalize_gender(row["gender"]),
                "life_stage": normalize_life_stage(row["life_stage"]),
                "age_group": get_age_bucket(age),
                "payment_status": payment_status,
                "payment_method": payment_method_value,
                "occupation": occupation_value,
                "dgroup": dgroup_value,
                "home_area": home_area_value,
                "check_in": "Checked in" if row["checked_in"] else "Not checked in",
                "checked_in": bool(row["checked_in"]),
                "satellite": [item["id"] for item in person_satellites],
                "satellite_names": [item["name"] for item in person_satellites],
            }
        )
    return result


def _dataset_memberships(db, event_id, batch_id):
    rows = db.execute(
        """
        SELECT d.id dataset_id, crs.curated_registrant_id
        FROM satellite_datasets d
        JOIN satellite_dataset_satellites dss
          ON dss.event_id = d.event_id AND dss.satellite_dataset_id = d.id
        JOIN curated_registrant_satellites crs
          ON crs.event_id = dss.event_id AND crs.batch_id = ?
         AND dss.satellite_batch_id = crs.batch_id
         AND crs.satellite_id = dss.satellite_id
        WHERE d.event_id = ?
        """,
        (batch_id, event_id),
    ).fetchall()
    memberships = defaultdict(set)
    for row in rows:
        memberships[str(row["dataset_id"])].add(row["curated_registrant_id"])
    return memberships


def _filter_options(records, threshold, db, event_id):
    labels = {
        "gender": "Gender",
        "life_stage": "Life Stage",
        "age_group": "Age Group",
        "payment_status": "Payment Status",
        "payment_method": "Payment Method",
        "occupation": "Occupation",
        "dgroup": "Dgroup",
        "home_area": "Home Area",
        "check_in": "Check-In",
    }
    options = {}
    for dimension, label in labels.items():
        counts = Counter(record[dimension] for record in records)
        options[dimension] = {
            "label": label,
            "items": [
                {"value": value, "label": value.replace("-", " ").title() if dimension in {"gender", "life_stage"} else value}
                for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
                if count >= threshold or count == 0
            ],
        }
    satellite_counts = Counter()
    satellite_names = {}
    for record in records:
        for satellite_id, name in zip(record["satellite"], record["satellite_names"]):
            satellite_counts[satellite_id] += 1
            satellite_names[satellite_id] = name
    options["satellite"] = {
        "label": "Satellite",
        "items": [
            {"value": value, "label": satellite_names[value]}
            for value, count in sorted(satellite_counts.items(), key=lambda item: satellite_names[item[0]].casefold())
            if count >= threshold
        ],
    }
    datasets = db.execute(
        "SELECT id, name FROM satellite_datasets WHERE event_id = ? ORDER BY LOWER(name), id",
        (event_id,),
    ).fetchall()
    options["satellite_dataset"] = {
        "label": "Satellite Dataset",
        "items": [{"value": str(row["id"]), "label": row["name"]} for row in datasets],
    }
    return options


def _parse_filters(raw_filters, options):
    filters = {}
    for dimension in FILTER_DIMENSIONS:
        value = _clean(raw_filters.get(dimension))
        if not value:
            continue
        allowed = {item["value"] for item in options[dimension]["items"]}
        if value not in allowed:
            raise AnalyticsFilterError("Invalid {} filter.".format(options[dimension]["label"]))
        filters[dimension] = value
    return filters


def _matches(record, filters, dataset_memberships, record_index):
    for dimension, value in filters.items():
        if dimension == "satellite_dataset":
            if record_index not in dataset_memberships.get(value, set()):
                return False
        elif dimension == "satellite":
            if value not in record[dimension]:
                return False
        elif record[dimension] != value:
            return False
    return True


def _public_count(count, threshold):
    if count == 0 or count >= threshold:
        return {"count": count, "display": str(count), "suppressed": False}
    return {"count": None, "display": "< {}".format(threshold), "suppressed": True}


def _withheld_count():
    return {"count": None, "display": "Withheld", "suppressed": True}


def _attendance_counts(registered, checked, threshold):
    checked_public = _public_count(checked, threshold)
    not_checked_public = _public_count(registered - checked, threshold)
    # Exact complementary values plus the registered total must not reconstruct
    # a suppressed count by subtraction.
    if checked_public["suppressed"] or not_checked_public["suppressed"]:
        checked_public = _withheld_count()
        not_checked_public = _withheld_count()
    return checked_public, not_checked_public


def _distribution(records, dimension, threshold):
    counts = Counter(record[dimension] for record in records)
    total = len(records)
    visible_counts = [
        (label, count) for label, count in counts.items() if count >= threshold
    ]
    suppressed_total = sum(count for count in counts.values() if count < threshold)
    # If the remainder is itself small, the exact total minus visible categories
    # would disclose it. Hide the smallest visible category as secondary
    # suppression, producing one safe, reconcilable combined bucket.
    if 0 < suppressed_total < threshold and visible_counts:
        secondary = min(visible_counts, key=lambda item: (item[1], item[0]))
        visible_counts.remove(secondary)
        suppressed_total += secondary[1]

    visible = []
    for label, count in sorted(visible_counts, key=lambda item: (-item[1], item[0])):
        visible.append(
            {
                "label": label.replace("-", " ").title() if dimension in {"gender", "life_stage"} else label,
                "count": count,
                "display": str(count),
                "percentage": count / total * 100 if total else 0,
                "suppressed": False,
            }
        )
    if suppressed_total:
        public = _public_count(suppressed_total, threshold)
        visible.append(
            {
                "label": "Suppressed categories",
                **public,
                "percentage": suppressed_total / total * 100 if total and not public["suppressed"] else None,
            }
        )
    return {
        "total": _public_count(total, threshold),
        "items": visible,
        "reconciles": True,
    }


def _attendance(records, dimension, threshold):
    groups = defaultdict(list)
    for record in records:
        values = record[dimension] if dimension == "satellite_names" else [record[dimension]]
        if not values:
            values = [UNKNOWN]
        for value in values:
            groups[value].append(record)
    items = []
    suppressed_records = []
    for label, group in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(group) < threshold:
            suppressed_records.extend(group)
            continue
        checked = sum(record["checked_in"] for record in group)
        registered = len(group)
        checked_public, not_checked_public = _attendance_counts(
            registered, checked, threshold
        )
        items.append(
            {
                "_key": label,
                "label": label.replace("-", " ").title() if dimension in {"gender", "life_stage"} else label,
                "registered": registered,
                "checked_in": checked_public,
                "not_checked_in": not_checked_public,
                "attendance_percentage": checked / registered * 100
                if not checked_public["suppressed"]
                else None,
            }
        )
    if suppressed_records and len(suppressed_records) < threshold and items:
        secondary_item = min(
            items,
            key=lambda item: len(groups[item["_key"]]),
        )
        suppressed_records.extend(groups[secondary_item["_key"]])
        items.remove(secondary_item)
    if suppressed_records:
        registered = len(suppressed_records)
        checked = sum(record["checked_in"] for record in suppressed_records)
        registered_public = _public_count(registered, threshold)
        checked_public, not_checked_public = _attendance_counts(
            registered, checked, threshold
        )
        items.append(
            {
                "label": "Suppressed categories",
                "registered": registered_public["count"],
                "registered_display": registered_public["display"],
                "checked_in": checked_public,
                "not_checked_in": not_checked_public,
                "attendance_percentage": checked / registered * 100
                if registered and not registered_public["suppressed"] and not checked_public["suppressed"]
                else None,
            }
        )
    for item in items:
        item.pop("_key", None)
    return items


def event_analytics(db, event_id, raw_filters=None, threshold=5, batch_id=None):
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        return None
    batch = (
        db.execute(
            "SELECT * FROM import_batches WHERE id = ? AND event_id = ?",
            (batch_id, event_id),
        ).fetchone()
        if batch_id is not None
        else db.execute(
            """SELECT * FROM import_batches WHERE event_id = ? AND status = 'active'
               ORDER BY activated_at DESC, id DESC LIMIT 1""",
            (event_id,),
        ).fetchone()
    )
    records = _participants(db, event_id, batch["id"], event["event_date"]) if batch else []
    options = _filter_options(records, threshold, db, event_id)
    filters = _parse_filters(raw_filters or {}, options)
    memberships = _dataset_memberships(db, event_id, batch["id"]) if batch else {}

    # Membership sets contain curated IDs while the compact records intentionally
    # omit identifiers. Rebuild deterministic indices from the same ordered query.
    if "satellite_dataset" in filters:
        member_ids = memberships.get(filters["satellite_dataset"], set())
        ordered_ids = [
            row["id"]
            for row in db.execute(
                """SELECT id FROM curated_registrants
                   WHERE event_id = ? AND batch_id = ? AND registration_type = 'participant'
                   ORDER BY id""",
                (event_id, batch["id"]),
            ).fetchall()
        ]
    else:
        member_ids = set()
        ordered_ids = list(range(len(records)))
    filtered = []
    for index, record in enumerate(records):
        record_key = ordered_ids[index]
        if _matches(record, filters, {filters.get("satellite_dataset", ""): member_ids}, record_key):
            filtered.append(record)

    dimensions = (
        "payment_status",
        "payment_method",
        "occupation",
        "dgroup",
        "home_area",
    )
    checked = sum(record["checked_in"] for record in filtered)
    checked_public, not_checked_public = _attendance_counts(
        len(filtered), checked, threshold
    )
    total_public = _public_count(len(filtered), threshold)
    return {
        "event": {"id": event["id"], "name": event["name"], "event_date": event["event_date"]},
        "batch": {"id": batch["id"], "status": batch["status"]} if batch else None,
        "privacy": {
            "minimum_group_size": threshold,
            "rule": "Exact non-zero counts below the threshold are withheld.",
        },
        "filters": filters,
        "filter_options": options,
        "population": {
            "registered": total_public,
            "checked_in": checked_public,
            "not_checked_in": not_checked_public,
            "attendance_percentage": checked / len(filtered) * 100
            if filtered and not checked_public["suppressed"] and not total_public["suppressed"]
            else None,
        },
        "distributions": {
            dimension: _distribution(filtered, dimension, threshold) for dimension in dimensions
        },
        "attendance": {
            dimension: _attendance(filtered, dimension, threshold)
            for dimension in ("gender", "life_stage", "payment_status", "dgroup", "home_area", "satellite_names")
        },
        "reconciliation": {
            "distribution_totals": all(
                sum(Counter(record[dimension] for record in filtered).values()) == len(filtered)
                for dimension in dimensions
            ),
            "checked_in_not_above_registered": checked <= len(filtered),
        },
    }


def historical_trends(db, event_id, threshold=5):
    event = db.execute("SELECT id, name FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        return None
    batches = db.execute(
        """SELECT id, status, created_at, processed_at, activated_at
           FROM import_batches
           WHERE event_id = ? AND status IN ('active', 'inactive')
           ORDER BY created_at, id""",
        (event_id,),
    ).fetchall()
    items = []
    for batch in batches:
        counts = db.execute(
            """SELECT COUNT(*) registered, COALESCE(SUM(checked_in), 0) checked_in
               FROM curated_registrants
               WHERE event_id = ? AND batch_id = ? AND registration_type = 'participant'""",
            (event_id, batch["id"]),
        ).fetchone()
        registered = counts["registered"] or 0
        checked = counts["checked_in"] or 0
        items.append(
            {
                "batch_id": batch["id"],
                "status": batch["status"],
                "created_at": batch["created_at"],
                "processed_at": batch["processed_at"],
                "activated_at": batch["activated_at"],
                "registered": _public_count(registered, threshold),
                "checked_in": _public_count(checked, threshold),
                "attendance_percentage": checked / registered * 100
                if registered and not _public_count(registered, threshold)["suppressed"]
                and not _public_count(checked, threshold)["suppressed"]
                else None,
            }
        )
    maximum = max(
        (item["registered"]["count"] or 0 for item in items),
        default=0,
    )
    for item in items:
        item["registered_bar_percentage"] = (
            item["registered"]["count"] / maximum * 100
            if maximum and item["registered"]["count"] is not None
            else None
        )
    return {
        "event": dict(event),
        "privacy": {"minimum_group_size": threshold},
        "snapshot_semantics": True,
        "items": items,
    }


def compare_events(db, event_ids, threshold=5):
    event_ids = list(dict.fromkeys(event_ids))
    if len(event_ids) < 2 or len(event_ids) > 10:
        raise AnalyticsFilterError("Select between 2 and 10 Events explicitly.")
    items = []
    for event_id in event_ids:
        analytics = event_analytics(db, event_id, threshold=threshold)
        if analytics is None:
            raise AnalyticsFilterError("One or more selected Events do not exist.")
        items.append(
            {
                "event": analytics["event"],
                "active_batch_id": analytics["batch"]["id"] if analytics["batch"] else None,
                "population": analytics["population"],
            }
        )
    return {
        "events": items,
        "privacy": {"minimum_group_size": threshold},
        "identity_resolution": False,
    }
