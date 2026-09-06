import json
import re
from collections import defaultdict

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
from .satellite_analytics import (
    EFFECTIVE_ASSOCIATIONS_CTE,
    HUB_CHART_COLORS,
    canonical_satellite_metrics,
    satellite_target_category_analytics,
)
from .satellite_reporting_categories import (
    REPORTING_CATEGORY_KEYS,
    REPORTING_CATEGORY_LABELS,
    REPORTING_CATEGORY_SQL,
)


ICP_LOCATION_SOURCE_FIELDS = (
    "Specify Icp Hub",
    "Icp Hub",
    "B1g Satellite",
    "Specify B1g Satellite",
    "Specify Home Location",
    "Specify Work Location",
)


def _dashboard_location_key(value):
    key = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    for prefix in ("b1g ", "ccf "):
        if key.startswith(prefix):
            key = key[len(prefix) :].strip()
    return key


def _inferred_icp_directory_ids(source_data_json, directories):
    try:
        source_data = json.loads(source_data_json or "{}")
    except (TypeError, ValueError):
        return set()
    if not isinstance(source_data, dict):
        return set()

    casefolded = {str(key).casefold(): value for key, value in source_data.items()}
    candidates = [
        _dashboard_location_key(casefolded.get(field.casefold()))
        for field in ICP_LOCATION_SOURCE_FIELDS
    ]
    candidates = [candidate for candidate in candidates if candidate]
    matches = set()
    for directory in directories:
        directory_key = _dashboard_location_key(directory["name"])
        if not directory_key:
            continue
        compact_directory_key = directory_key.replace(" ", "")
        for candidate in candidates:
            compact_candidate = candidate.replace(" ", "")
            if (
                candidate == directory_key
                or directory_key in candidate
                or compact_directory_key in compact_candidate
            ):
                matches.add(directory["id"])
                break
    return matches


def _dashboard_hub_chart(satellite_rows):
    associations_by_hub = defaultdict(int)
    for row in satellite_rows:
        if row["hub_name"] and row["hub_name"] != "Needs Mapping":
            associations_by_hub[(row["hub_id"], row["hub_name"])] += row[
                "participants"
            ]
    ranked = sorted(
        (
            {"id": hub_id, "name": name, "associations": associations}
            for (hub_id, name), associations in associations_by_hub.items()
        ),
        key=lambda item: (-item["associations"], item["name"].casefold()),
    )
    if len(ranked) > 8:
        displayed = ranked[:7]
        icp = next(
            (item for item in ranked if item["name"].casefold() == "icp"), None
        )
        if icp is not None and icp not in displayed:
            displayed[-1] = icp
        displayed_ids = {item["id"] for item in displayed}
        displayed.append(
            {
                "id": None,
                "name": "Other",
                "associations": sum(
                    item["associations"]
                    for item in ranked
                    if item["id"] not in displayed_ids
                ),
            }
        )
    else:
        displayed = ranked

    association_count = sum(item["associations"] for item in ranked)
    cursor = 0.0
    chart = []
    for index, item in enumerate(displayed):
        percentage = (
            item["associations"] / association_count * 100
            if association_count
            else 0
        )
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
    return {
        "association_count": association_count,
        "hubs_represented": len(ranked),
        "items": chart,
    }


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


LEADERSHIP_CATEGORIES = (
    ("dgroup_leader", "Dgroup Leaders"),
    ("d12_leader", "D12 Leaders"),
)
LEADERSHIP_YEARS = (
    ("under_1", "< 1 year"),
    ("1_2", "1–2 years"),
    ("3_5", "3–5 years"),
    ("6_10", "6–10 years"),
    ("over_10", "More than 10 years"),
)
SHIRT_SIZES = (
    ("xs", "XS", 'W: 17" · L: 24"'),
    ("s", "S", 'W: 18" · L: 25"'),
    ("m", "M", 'W: 19" · L: 26"'),
    ("l", "L", 'W: 20" · L: 27"'),
    ("xl", "XL", 'W: 21" · L: 28"'),
    ("2xl", "2XL", 'W: 22" · L: 29"'),
    ("3xl", "3XL", 'W: 23" · L: 30"'),
)
TRANSPORTATION_MODES = (
    ("carpool", "Carpool", "car"),
    ("bus", "Bus", "bus"),
    ("public_transportation", "Public Transportation", "train"),
)


def _source_answer_expression(db, alias, header):
    path = '$."{}"'.format(header.replace('"', '\\"')).replace("'", "''")
    expression = "JSON_EXTRACT({}.source_data_json, '{}')".format(alias, path)
    return "JSON_UNQUOTE({})".format(expression) if db.is_mysql else expression


def _source_answers_expression(db, alias, headers):
    expressions = [_source_answer_expression(db, alias, header) for header in headers]
    return expressions[0] if len(expressions) == 1 else "COALESCE({})".format(
        ", ".join(expressions)
    )


def _clean_answer(value):
    return " ".join(str(value or "").strip().split())


def _leadership_role(value):
    value = _clean_answer(value).casefold()
    if "d12" in value and "leader" in value:
        return "d12_leader"
    if ("dgroup" in value or "discipleship group" in value) and "leader" in value:
        return "dgroup_leader"
    return None


def _years_leading_bucket(value):
    value = _clean_answer(value).casefold().replace("–", "-")
    if not value:
        return None
    if value.startswith("<") or "less than 1" in value or "under 1" in value:
        return "under_1"
    if "more than 10" in value or "over 10" in value or value.startswith("> 10"):
        return "over_10"
    numbers = tuple(int(number) for number in re.findall(r"\d+", value))
    if numbers and max(numbers) <= 2:
        return "1_2"
    if numbers and max(numbers) <= 5:
        return "3_5"
    if numbers and max(numbers) <= 10:
        return "6_10"
    if numbers and max(numbers) > 10:
        return "over_10"
    return "other"


def _shirt_size(value):
    value = _clean_answer(value).upper().replace(" ", "")
    if not value:
        return None
    aliases = {"SMALL": "s", "MEDIUM": "m", "LARGE": "l", "XXL": "2xl", "XXXL": "3xl"}
    if value in aliases:
        return aliases[value]
    match = re.match(r"^(3XL|2XL|XL|XS|S|M|L)(?:\b|\()", value)
    return match.group(1).casefold() if match else "other"


def _transportation_mode(value):
    value = _clean_answer(value).casefold()
    if not value:
        return None
    if "carpool" in value:
        return "carpool"
    if "bus" in value:
        return "bus"
    if "public transportation" in value or "public transport" in value:
        return "public_transportation"
    return "other"


def participant_ministry_and_shirt_metrics(db, batch_id):
    """Aggregate leadership and shirt answers once per curated registrant."""
    if batch_id is None:
        return participant_ministry_and_shirt_metrics_empty()
    status = _source_answer_expression(db, "r", "Dgroup Status")
    legacy_leader = _source_answer_expression(
        db, "r", "Are You Leading A Discipleship Group"
    )
    years = _source_answer_expression(db, "r", "Years Leading A Dgroup")
    shirt = _source_answer_expression(db, "r", "Shirt Size")
    rows = db.execute(
        """
        SELECT cr.id curated_id, {status} leadership_status,
               {legacy_leader} legacy_leader, {years} years_leading,
               {shirt} shirt_size
        FROM curated_registrants cr
        JOIN curated_registrant_sources source
          ON source.event_id = cr.event_id AND source.batch_id = cr.batch_id
         AND source.curated_registrant_id = cr.id
        JOIN registrants r
          ON r.batch_id = source.batch_id AND r.id = source.registrant_id
        WHERE cr.batch_id = ?
        ORDER BY cr.id, source.id
        """.format(
            status=status,
            legacy_leader=legacy_leader,
            years=years,
            shirt=shirt,
        ),
        (batch_id,),
    ).fetchall()
    people = defaultdict(lambda: {"roles": set(), "years": set(), "shirts": set()})
    for row in rows:
        role = _leadership_role(row["leadership_status"])
        if role is None and _clean_answer(row["legacy_leader"]).casefold() in {
            "yes", "y", "true", "1"
        }:
            role = "dgroup_leader"
        years_bucket = _years_leading_bucket(row["years_leading"])
        shirt_size = _shirt_size(row["shirt_size"])
        if role:
            people[row["curated_id"]]["roles"].add(role)
        if years_bucket:
            people[row["curated_id"]]["years"].add(years_bucket)
        if shirt_size:
            people[row["curated_id"]]["shirts"].add(shirt_size)

    role_counts = {key: 0 for key, _label in LEADERSHIP_CATEGORIES}
    years_counts = {key: 0 for key, _label in LEADERSHIP_YEARS}
    years_counts["other"] = 0
    shirt_counts = {key: 0 for key, _label, _detail in SHIRT_SIZES}
    shirt_counts["other"] = 0
    leadership_conflicts = 0
    years_conflicts = 0
    shirt_conflicts = 0
    for person in people.values():
        if len(person["roles"]) == 1:
            role_counts[next(iter(person["roles"]))] += 1
        elif len(person["roles"]) > 1:
            leadership_conflicts += 1
        if len(person["years"]) == 1:
            years_counts[next(iter(person["years"]))] += 1
        elif len(person["years"]) > 1:
            years_conflicts += 1
        if len(person["shirts"]) == 1:
            shirt_counts[next(iter(person["shirts"]))] += 1
        elif len(person["shirts"]) > 1:
            shirt_conflicts += 1

    leadership_total = sum(role_counts.values())
    years_total = sum(years_counts.values())
    shirt_total = sum(shirt_counts.values())
    leadership = _distribution(
        LEADERSHIP_CATEGORIES, role_counts, leadership_total, include_segments=True
    )
    leadership.update(
        {
            "unreported": len(people) - leadership_total - leadership_conflicts,
            "conflicts": leadership_conflicts,
        }
    )
    years_items = [
        {
            "key": key,
            "label": label,
            "count": years_counts[key],
            "percentage": years_counts[key] / years_total * 100 if years_total else 0,
        }
        for key, label in LEADERSHIP_YEARS
    ]
    if years_counts["other"]:
        years_items.append(
            {
                "key": "other",
                "label": "Other",
                "count": years_counts["other"],
                "percentage": years_counts["other"] / years_total * 100,
            }
        )
    shirt_items = [
        {
            "key": key,
            "label": label,
            "detail": detail,
            "count": shirt_counts[key],
            "percentage": shirt_counts[key] / shirt_total * 100 if shirt_total else 0,
        }
        for key, label, detail in SHIRT_SIZES
    ]
    if shirt_counts["other"]:
        shirt_items.append(
            {
                "key": "other",
                "label": "Other",
                "detail": "Review source response",
                "count": shirt_counts["other"],
                "percentage": shirt_counts["other"] / shirt_total * 100,
            }
        )
    return {
        "leadership": leadership,
        "years_leading": {
            "total": years_total,
            "items": years_items,
            "unreported": len(people) - years_total - years_conflicts,
            "conflicts": years_conflicts,
        },
        "shirt_sizes": {
            "total": shirt_total,
            "items": shirt_items,
            "unreported": len(people) - shirt_total - shirt_conflicts,
            "conflicts": shirt_conflicts,
        },
    }


def participant_ministry_and_shirt_metrics_empty():
    return {
        "leadership": {
            **_distribution(
                LEADERSHIP_CATEGORIES,
                {key: 0 for key, _label in LEADERSHIP_CATEGORIES},
                0,
                include_segments=True,
            ),
            "unreported": 0,
            "conflicts": 0,
        },
        "years_leading": {
            "total": 0,
            "items": [
                {"key": key, "label": label, "count": 0, "percentage": 0}
                for key, label in LEADERSHIP_YEARS
            ],
            "unreported": 0,
            "conflicts": 0,
        },
        "shirt_sizes": {
            "total": 0,
            "items": [
                {
                    "key": key,
                    "label": label,
                    "detail": detail,
                    "count": 0,
                    "percentage": 0,
                }
                for key, label, detail in SHIRT_SIZES
            ],
            "unreported": 0,
            "conflicts": 0,
        },
    }


def participant_transportation_metrics(db, batch_id):
    """Aggregate each travel direction once per curated registrant."""
    if batch_id is None:
        return participant_transportation_metrics_empty()
    to_mmrc = _source_answers_expression(
        db,
        "r",
        ("Transportation From Ccf To Mmrc", "Transportation To MMRC"),
    )
    from_mmrc = _source_answers_expression(
        db,
        "r",
        ("Transportation From Mmrc To Ccf", "Transportation From MMRC"),
    )
    rows = db.execute(
        """
        SELECT cr.id curated_id, {to_mmrc} to_mmrc, {from_mmrc} from_mmrc
        FROM curated_registrants cr
        JOIN curated_registrant_sources source
          ON source.event_id = cr.event_id AND source.batch_id = cr.batch_id
         AND source.curated_registrant_id = cr.id
        JOIN registrants r
          ON r.batch_id = source.batch_id AND r.id = source.registrant_id
        WHERE cr.batch_id = ?
        ORDER BY cr.id, source.id
        """.format(to_mmrc=to_mmrc, from_mmrc=from_mmrc),
        (batch_id,),
    ).fetchall()
    people = defaultdict(lambda: {"to_mmrc": set(), "from_mmrc": set()})
    for row in rows:
        for direction in ("to_mmrc", "from_mmrc"):
            mode = _transportation_mode(row[direction])
            if mode:
                people[row["curated_id"]][direction].add(mode)

    direction_definitions = (
        ("to_mmrc", "CCF to MMRC", "Outbound trip", "Bus to MMRC"),
        ("from_mmrc", "MMRC to CCF", "Return trip", "Bus to CCF"),
    )
    directions = []
    for key, label, trip_label, bus_label in direction_definitions:
        counts = {mode: 0 for mode, _label, _icon in TRANSPORTATION_MODES}
        other = 0
        conflicts = 0
        unreported = 0
        for person in people.values():
            answers = person[key]
            if not answers:
                unreported += 1
            elif len(answers) > 1:
                conflicts += 1
            else:
                mode = next(iter(answers))
                if mode in counts:
                    counts[mode] += 1
                else:
                    other += 1
        total = sum(counts.values())
        directions.append(
            {
                "key": key,
                "label": label,
                "trip_label": trip_label,
                "total": total,
                "items": [
                    {
                        "key": mode,
                        "label": bus_label if mode == "bus" else mode_label,
                        "icon": icon,
                        "count": counts[mode],
                        "percentage": counts[mode] / total * 100 if total else 0,
                    }
                    for mode, mode_label, icon in TRANSPORTATION_MODES
                ],
                "unreported": unreported,
                "other": other,
                "conflicts": conflicts,
            }
        )
    return {"registrants": len(people), "directions": directions}


def participant_transportation_metrics_empty():
    return {
        "registrants": 0,
        "directions": [
            {
                "key": key,
                "label": label,
                "trip_label": trip_label,
                "total": 0,
                "items": [
                    {
                        "key": mode,
                        "label": bus_label if mode == "bus" else mode_label,
                        "icon": icon,
                        "count": 0,
                        "percentage": 0,
                    }
                    for mode, mode_label, icon in TRANSPORTATION_MODES
                ],
                "unreported": 0,
                "other": 0,
                "conflicts": 0,
            }
            for key, label, trip_label, bus_label in (
                ("to_mmrc", "CCF to MMRC", "Outbound trip", "Bus to MMRC"),
                ("from_mmrc", "MMRC to CCF", "Return trip", "Bus to CCF"),
            )
        ],
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
            EFFECTIVE_ASSOCIATIONS_CTE
            + """
            SELECT d.id dataset_id, COUNT(DISTINCT cr.id) actual_participants
            FROM satellite_datasets d
            LEFT JOIN satellite_dataset_satellites dss
              ON dss.satellite_dataset_id = d.id AND dss.event_id = d.event_id
            LEFT JOIN satellites selected
              ON selected.id = dss.satellite_id
             AND selected.event_id = dss.event_id
            LEFT JOIN effective_associations association
              ON association.event_id = d.event_id
             AND association.batch_id = ?
             AND association.directory_id = selected.directory_id
            LEFT JOIN curated_registrants cr
              ON cr.id = association.curated_registrant_id
             AND cr.event_id = association.event_id
             AND cr.batch_id = association.batch_id
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


def satellite_target_category_metrics(db, event_id, batch_id):
    """Calculate dynamic Dashboard Analytics Target Group metrics."""
    analytics = satellite_target_category_analytics(db, event_id, batch_id)
    result = []
    for group in analytics["groups"]:
        actual = group["actual_participants"]
        target = group["participant_target"]
        progress = registration_progress(actual, target)
        result.append(
            {
                "id": group["id"],
                "key": group["key"],
                "category_keys": group["category_keys"],
                "name": group["name"],
                "participant_target": target,
                "actual_participants": actual,
                "satellite_count": group["satellite_count"],
                "exceeded_amount": max(actual - target, 0),
                **progress,
            }
        )
    chart_max = max(
        [1]
        + [item["participant_target"] for item in result]
        + [item["actual_participants"] for item in result]
    )
    for item in result:
        item["target_bar_percentage"] = item["participant_target"] / chart_max * 100
        item["actual_bar_percentage"] = item["actual_participants"] / chart_max * 100
    return result


DASHBOARD_SATELLITE_COLORS = {
    "outside_metro_manila": "#2563eb",
    "within_metro_manila": "#f59e0b",
    "main": "#dc2626",
}


def dashboard_satellite_metrics(db, event_id, batch_id, query="", page=1):
    """Return the fixed participant-only Satellite dashboard read model."""
    query = " ".join(str(query or "").strip().split())[:100]
    try:
        page = max(int(page or 1), 1)
    except (TypeError, ValueError):
        page = 1

    empty_categories = [
        {
            "key": key,
            "label": REPORTING_CATEGORY_LABELS[key],
            "participants": 0,
            "percentage": 0,
            "start": 0,
            "end": 0,
            "color": DASHBOARD_SATELLITE_COLORS[key],
        }
        for key in REPORTING_CATEGORY_KEYS
    ]
    if batch_id is None:
        return {
            "query": query,
            "participant_assignments": 0,
            "location_responses": 0,
            "hub_only_participants": 0,
            "inferred_location_participants": 0,
            "hub_association_count": 0,
            "hubs_represented": 0,
            "hub_chart": [],
            "categorized_participants": 0,
            "categories": empty_categories,
            "rows": [],
            "pagination": _pagination_metadata(0, page, 10),
        }

    represented_directories_cte = """
    , represented_directories AS (
        SELECT DISTINCT association.directory_id
        FROM effective_associations association
        WHERE association.event_id = ? AND association.batch_id = ?
          AND association.directory_id IS NOT NULL
        UNION
        SELECT DISTINCT imported.directory_id
        FROM satellites imported
        WHERE imported.event_id = ? AND imported.batch_id = ?
          AND imported.directory_id IS NOT NULL
    )
    """
    params = (event_id, batch_id, event_id, batch_id, event_id, batch_id)
    rows = db.execute(
        EFFECTIVE_ASSOCIATIONS_CTE
        + represented_directories_cte
        + """
        SELECT directory.id, directory.name,
               hub.id hub_id, hub.name hub_name, hub.is_main,
               hub_group.code group_code, hub_group.name group_name,
               COUNT(DISTINCT participant.id) participants
        FROM represented_directories represented
        JOIN satellite_directory directory
          ON directory.id = represented.directory_id
        LEFT JOIN satellite_hubs hub ON hub.id = directory.hub_id
        LEFT JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
        LEFT JOIN effective_associations association
          ON association.directory_id = directory.id
         AND association.event_id = ? AND association.batch_id = ?
        LEFT JOIN curated_registrants participant
          ON participant.id = association.curated_registrant_id
         AND participant.event_id = association.event_id
         AND participant.batch_id = association.batch_id
         AND participant.registration_type = 'participant'
        GROUP BY directory.id, directory.name, hub.id, hub.name, hub.is_main,
                 hub_group.code, hub_group.name
        """,
        params,
    ).fetchall()
    icp_directories = [
        dict(row)
        for row in db.execute(
            """
            SELECT directory.id, directory.name,
                   hub.id hub_id, hub.name hub_name, hub.is_main,
                   hub_group.code group_code, hub_group.name group_name
            FROM satellite_directory directory
            JOIN satellite_hubs hub ON hub.id = directory.hub_id
            LEFT JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
            WHERE LOWER(hub.normalized_name) = 'icp'
            ORDER BY directory.id
            """
        ).fetchall()
    ]
    icp_source_rows = db.execute(
        EFFECTIVE_ASSOCIATIONS_CTE
        + """
        SELECT participant.id participant_id, raw.source_data_json
        FROM curated_registrants participant
        JOIN curated_registrant_sources source
          ON source.event_id = participant.event_id
         AND source.batch_id = participant.batch_id
         AND source.curated_registrant_id = participant.id
        JOIN registrants raw
          ON raw.batch_id = source.batch_id AND raw.id = source.registrant_id
        JOIN satellite_hubs hub
          ON LOWER(hub.normalized_name) = LOWER(TRIM(raw.b1g_satellite_hub_raw))
        WHERE participant.event_id = ? AND participant.batch_id = ?
          AND participant.registration_type = 'participant'
          AND LOWER(hub.normalized_name) = 'icp'
          AND NULLIF(TRIM(COALESCE(raw.satellite_name, '')), '') IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM effective_associations assigned
              WHERE assigned.event_id = participant.event_id
                AND assigned.batch_id = participant.batch_id
                AND assigned.curated_registrant_id = participant.id
          )
        """,
        (event_id, batch_id),
    ).fetchall()
    participant_assignments = sum(row["participants"] for row in rows)
    inferred_candidates = defaultdict(set)
    for source_row in icp_source_rows:
        inferred_candidates[source_row["participant_id"]].update(
            _inferred_icp_directory_ids(
                source_row["source_data_json"], icp_directories
            )
        )
    inferred_by_directory = defaultdict(set)
    for participant_id, directory_ids in inferred_candidates.items():
        if len(directory_ids) == 1:
            inferred_by_directory[next(iter(directory_ids))].add(participant_id)
    inferred_location_participants = sum(
        len(participant_ids)
        for participant_ids in inferred_by_directory.values()
    )
    location_responses = participant_assignments + inferred_location_participants
    rows_by_directory = {row["id"]: dict(row) for row in rows}
    icp_directories_by_id = {
        directory["id"]: directory for directory in icp_directories
    }
    for directory_id, participant_ids in inferred_by_directory.items():
        inferred_count = len(participant_ids)
        if directory_id in rows_by_directory:
            rows_by_directory[directory_id]["participants"] += inferred_count
            continue
        directory = icp_directories_by_id[directory_id]
        rows_by_directory[directory_id] = {
            **directory,
            "participants": inferred_count,
        }
    satellite_rows = [
        {
            "id": row["id"],
            "name": row["name"],
            "participants": row["participants"],
            "hub_id": row["hub_id"],
            "hub_name": row["hub_name"] or "Needs Mapping",
            "group_name": row["group_name"] or "Needs Mapping",
            "hub_only": False,
        }
        for row in rows_by_directory.values()
    ]
    hub_chart = _dashboard_hub_chart(satellite_rows)
    for row in satellite_rows:
        row["percentage"] = (
            row["participants"] / location_responses * 100
            if location_responses
            else 0
        )
    satellite_rows.sort(
        key=lambda item: (-item["participants"], item["name"].casefold(), item["id"])
    )
    if query:
        needle = query.casefold()
        satellite_rows = [
            row
            for row in satellite_rows
            if needle
            in " ".join(
                (row["name"], row["hub_name"], row["group_name"])
            ).casefold()
        ]

    pagination = _pagination_metadata(len(satellite_rows), page, 10)
    visible_rows = satellite_rows[
        pagination["offset"] : pagination["offset"] + pagination["per_page"]
    ]

    category_rows = db.execute(
        EFFECTIVE_ASSOCIATIONS_CTE
        + """
        SELECT {category_sql} category_key,
               COUNT(DISTINCT participant.id) participants
        FROM effective_associations association
        JOIN satellite_directory directory
          ON directory.id = association.directory_id
        JOIN satellite_hubs hub ON hub.id = directory.hub_id
        JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
        JOIN curated_registrants participant
          ON participant.id = association.curated_registrant_id
         AND participant.event_id = association.event_id
         AND participant.batch_id = association.batch_id
         AND participant.registration_type = 'participant'
        WHERE association.event_id = ? AND association.batch_id = ?
        GROUP BY {category_sql}
        """.format(category_sql=REPORTING_CATEGORY_SQL),
        (event_id, batch_id),
    ).fetchall()
    counts = {key: 0 for key in REPORTING_CATEGORY_KEYS}
    counts.update(
        {
            row["category_key"]: row["participants"]
            for row in category_rows
            if row["category_key"] in counts
        }
    )
    for directory_id, participant_ids in inferred_by_directory.items():
        directory = icp_directories_by_id[directory_id]
        category_key = (
            "main" if directory["is_main"] else directory["group_code"]
        )
        if category_key in counts:
            counts[category_key] += len(participant_ids)
    category_total = sum(counts.values())
    cursor = 0.0
    categories = []
    for key in REPORTING_CATEGORY_KEYS:
        percentage = counts[key] / category_total * 100 if category_total else 0
        categories.append(
            {
                "key": key,
                "label": REPORTING_CATEGORY_LABELS[key],
                "participants": counts[key],
                "percentage": percentage,
                "start": cursor,
                "end": cursor + percentage,
                "color": DASHBOARD_SATELLITE_COLORS[key],
            }
        )
        cursor += percentage

    return {
        "query": query,
        "participant_assignments": participant_assignments,
        "location_responses": location_responses,
        "hub_only_participants": inferred_location_participants,
        "inferred_location_participants": inferred_location_participants,
        "hub_association_count": hub_chart["association_count"],
        "hubs_represented": hub_chart["hubs_represented"],
        "hub_chart": hub_chart["items"],
        "categorized_participants": category_total,
        "categories": categories,
        "rows": visible_rows,
        "pagination": pagination,
    }


def dashboard_operational_status_metrics(db, batch_id):
    """Summarize payment and attestation workflow states for one active batch."""
    if batch_id is None:
        return {
            "total_registrations": 0,
            "payment": {"validated": 0, "for_validation": 0, "total": 0},
            "attestation": {"pending": 0, "verified": 0, "invalid": 0, "total": 0},
        }

    row = db.execute(
        """
        SELECT
            COUNT(*) AS total_registrations,
            COUNT(CASE
                WHEN LOWER(TRIM(ticket.payment_status)) = 'payment validated'
                THEN 1
            END) AS payment_validated,
            COUNT(CASE
                WHEN LOWER(TRIM(ticket.payment_status)) = 'for payment validation'
                THEN 1
            END) AS payment_for_validation,
            COUNT(CASE
                WHEN COALESCE(verification.status, 'pending') = 'pending'
                THEN 1
            END) AS attestation_pending,
            COUNT(CASE WHEN verification.status = 'verified' THEN 1 END)
                AS attestation_verified,
            COUNT(CASE WHEN verification.status = 'invalid' THEN 1 END)
                AS attestation_invalid
        FROM registrants record
        JOIN import_batches batch ON batch.id = record.batch_id
        LEFT JOIN tickets ticket
          ON ticket.batch_id = record.batch_id
         AND ticket.ticket_code = record.ticket_code
        LEFT JOIN attestation_participant_registrants participant_mapping
          ON participant_mapping.batch_id = record.batch_id
         AND participant_mapping.registrant_id = record.id
        LEFT JOIN attestation_verifications verification
          ON verification.event_id = batch.event_id
         AND verification.attestation_participant_id =
             participant_mapping.attestation_participant_id
        WHERE record.batch_id = ?
        """,
        (batch_id,),
    ).fetchone()
    payment_validated = row["payment_validated"] or 0
    payment_for_validation = row["payment_for_validation"] or 0
    attestation_pending = row["attestation_pending"] or 0
    attestation_verified = row["attestation_verified"] or 0
    attestation_invalid = row["attestation_invalid"] or 0
    return {
        "total_registrations": row["total_registrations"] or 0,
        "payment": {
            "validated": payment_validated,
            "for_validation": payment_for_validation,
            "total": payment_validated + payment_for_validation,
        },
        "attestation": {
            "pending": attestation_pending,
            "verified": attestation_verified,
            "invalid": attestation_invalid,
            "total": attestation_pending + attestation_verified + attestation_invalid,
        },
    }


def event_dashboard_metrics(db, event_id, satellite_query="", satellite_page=1):
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
    participant_details = participant_ministry_and_shirt_metrics(
        db, batch["id"] if batch else None
    )
    transportation = participant_transportation_metrics(
        db, batch["id"] if batch else None
    )
    total_registrations = participants + volunteers
    target_groups = satellite_target_category_metrics(
        db, event_id, batch["id"] if batch else None
    )
    operational_status = dashboard_operational_status_metrics(
        db, batch["id"] if batch else None
    )
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
        "operational_status": operational_status,
        **participant_details,
        "transportation": transportation,
        "satellite_target_groups": target_groups,
        # Temporary response alias for consumers of the fixed-category release.
        "satellite_target_categories": target_groups,
        "satellite_datasets": satellite_dataset_metrics(
            db, event_id, batch["id"] if batch else None
        ),
        "satellites": dashboard_satellite_metrics(
            db,
            event_id,
            batch["id"] if batch else None,
            query=satellite_query,
            page=satellite_page,
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
            "attestation_statuses_reconcile": operational_status["attestation"]["total"]
            == operational_status["total_registrations"],
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
    # Keep the legacy presentation payload available until the Phase 2 template
    # replacement, while making the canonical Phase 1 read model available to
    # the route immediately.
    canonical = canonical_satellite_metrics(db, batch_id)
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
        "canonical": canonical,
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


def satellite_registrants(
    db,
    batch_id,
    satellite,
    scope=None,
    page=1,
    per_page=50,
    query="",
):
    """Return a searchable, privacy-limited roster for one canonical Satellite."""
    try:
        directory_id = int(satellite)
    except (TypeError, ValueError):
        affiliation = {
            "local": "Local Satellite",
            "international": "International Satellite",
        }.get(scope)
        row = db.execute(
            """
            SELECT directory.id
            FROM satellites imported
            JOIN satellite_directory directory ON directory.id = imported.directory_id
            WHERE imported.batch_id = ?
              AND directory.name = ? COLLATE NOCASE
              AND (? IS NULL OR imported.affiliation = ?)
            ORDER BY directory.id LIMIT 1
            """,
            (batch_id, str(satellite or "").strip(), affiliation, affiliation),
        ).fetchone()
        directory_id = row["id"] if row else None
    if not directory_id:
        return None

    batch = db.execute(
        "SELECT event_id FROM import_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if batch is None:
        return None
    event_id = batch["event_id"]

    metadata = db.execute(
        """
        SELECT directory.id, directory.name satellite_name,
               hubs.id hub_id, hubs.name hub_name,
               hub_group.id group_id, hub_group.code group_code,
               hub_group.name group_name
        FROM satellite_directory directory
        LEFT JOIN satellite_hubs hubs ON hubs.id = directory.hub_id
        LEFT JOIN hub_groups hub_group ON hub_group.id = hubs.hub_group_id
        WHERE directory.id = ?
          AND EXISTS (
              SELECT 1 FROM satellites imported
              WHERE imported.batch_id = ? AND imported.directory_id = directory.id
              UNION ALL
              SELECT 1 FROM event_registrant_satellites assignment
              WHERE assignment.event_id = ?
                AND assignment.assignment_source = 'manual'
                AND assignment.directory_id = directory.id
          )
        """,
        (directory_id, batch_id, event_id),
    ).fetchone()
    if metadata is None:
        return None

    query = " ".join(str(query or "").strip().split())[:100]
    page = max(int(page or 1), 1)
    per_page = per_page if per_page in (25, 50, 100) else 50
    participant_name = (
        "CONCAT(COALESCE(search_raw.first_name, ''), ' ', "
        "COALESCE(search_raw.last_name, ''))"
        if db.is_mysql
        else "COALESCE(search_raw.first_name, '') || ' ' || "
        "COALESCE(search_raw.last_name, '')"
    )
    search_sql = ""
    search_params = []
    if query:
        search_sql = """
            AND EXISTS (
                SELECT 1
                FROM curated_registrant_sources search_source
                JOIN registrants search_raw ON search_raw.id = search_source.registrant_id
                WHERE search_source.curated_registrant_id = matching.id
                  AND (
                      LOWER(TRIM({participant_name})) LIKE LOWER(?)
                      OR LOWER(search_raw.registration_code) LIKE LOWER(?)
                      OR LOWER(search_raw.source_id) LIKE LOWER(?)
                  )
            )
        """.format(participant_name=participant_name)
        search_params = ["%{}%".format(query)] * 3

    roster_template = """
        WITH matching AS (
            SELECT curated.id
            FROM curated_registrants curated
            WHERE curated.batch_id = ? AND (
                EXISTS (
                    SELECT 1
                    FROM curated_registrant_sources owner_source
                    JOIN attestation_participant_registrants owner
                      ON owner.batch_id = owner_source.batch_id
                     AND owner.registrant_id = owner_source.registrant_id
                    JOIN event_registrant_satellites assignment
                      ON assignment.event_id = owner.event_id
                     AND assignment.attestation_participant_id = owner.attestation_participant_id
                    WHERE owner_source.curated_registrant_id = curated.id
                      AND assignment.assignment_source = 'manual'
                      AND assignment.directory_id = ?
                ) OR (
                    NOT EXISTS (
                        SELECT 1
                        FROM curated_registrant_sources owner_source
                        JOIN attestation_participant_registrants owner
                          ON owner.batch_id = owner_source.batch_id
                         AND owner.registrant_id = owner_source.registrant_id
                        JOIN event_registrant_satellites assignment
                          ON assignment.event_id = owner.event_id
                         AND assignment.attestation_participant_id = owner.attestation_participant_id
                        WHERE owner_source.curated_registrant_id = curated.id
                          AND assignment.assignment_source = 'manual'
                    )
                    AND EXISTS (
                        SELECT 1
                        FROM curated_registrant_satellites association
                        JOIN satellites imported ON imported.id = association.satellite_id
                        WHERE association.curated_registrant_id = curated.id
                          AND imported.batch_id = ?
                          AND imported.directory_id = ?
                    )
                )
            )
        ), representative AS (
            SELECT source.curated_registrant_id, MIN(source.registrant_id) registrant_id
            FROM curated_registrant_sources source
            WHERE source.batch_id = ?
            GROUP BY source.curated_registrant_id
        )
        SELECT matching.id curated_id, raw.first_name, raw.last_name,
               raw.registration_code, raw.source_id
        FROM matching
        JOIN representative rep ON rep.curated_registrant_id = matching.id
        JOIN registrants raw ON raw.id = rep.registrant_id
        WHERE 1 = 1 {search_sql}
    """
    roster_sql = roster_template.format(search_sql=search_sql)
    unfiltered_roster_sql = roster_template.format(search_sql="")
    base_params = [
        batch_id,
        directory_id,
        batch_id,
        directory_id,
        batch_id,
    ] + search_params
    total = db.execute(
        "SELECT COUNT(*) FROM ({}) roster".format(roster_sql), base_params
    ).fetchone()[0]
    unfiltered_total = db.execute(
        "SELECT COUNT(*) FROM ({}) roster".format(unfiltered_roster_sql),
        base_params[:5],
    ).fetchone()[0]
    if not unfiltered_total:
        return None
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    offset = (page - 1) * per_page
    rows = db.execute(
        roster_sql
        + """
          ORDER BY LOWER(COALESCE(last_name, '')),
                   LOWER(COALESCE(first_name, '')), curated_id
          LIMIT ? OFFSET ?
        """,
        base_params + [per_page, offset],
    ).fetchall()
    participants = []
    for row in rows:
        display_name = " ".join(
            value for value in (row["first_name"], row["last_name"]) if value
        ) or "Name unavailable"
        participants.append(
            {
                "name": display_name,
                "registration_id": row["registration_code"]
                or row["source_id"]
                or str(row["curated_id"]),
                "hub": metadata["hub_name"] or "Unassigned",
                "satellite": metadata["satellite_name"],
                "link_status": "Linked" if metadata["group_id"] else "Needs Mapping",
            }
        )
    return {
        "satellite_id": metadata["id"],
        "satellite_name": metadata["satellite_name"],
        "hub_id": metadata["hub_id"],
        "hub_name": metadata["hub_name"] or "Unassigned Hub",
        "group_id": metadata["group_id"],
        "group_code": metadata["group_code"],
        "group_name": metadata["group_name"] or "Needs Mapping",
        "registrants": unfiltered_total,
        "query": query,
        "participants": participants,
        "pagination": {
            "page": page,
            "pages": pages,
            "per_page": per_page,
            "total": total,
            "start": offset + 1 if total else 0,
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
    effective_satellites = db.execute(
        """
        SELECT DISTINCT directory.id, directory.name,
               hubs.id hub_id, hubs.name hub_name,
               'manual' assignment_source
        FROM curated_registrant_sources source
        JOIN attestation_participant_registrants owner
          ON owner.batch_id = source.batch_id
         AND owner.registrant_id = source.registrant_id
        JOIN event_registrant_satellites assignment
          ON assignment.event_id = owner.event_id
         AND assignment.attestation_participant_id = owner.attestation_participant_id
         AND assignment.assignment_source = 'manual'
        JOIN satellite_directory directory ON directory.id = assignment.directory_id
        LEFT JOIN satellite_hubs hubs ON hubs.id = directory.hub_id
        WHERE source.curated_registrant_id = ? AND source.batch_id = ?
        ORDER BY directory.name
        """,
        (curated_registrant_id, batch_id),
    ).fetchall()
    if not effective_satellites:
        effective_satellites = db.execute(
            """
            SELECT DISTINCT directory.id, directory.name,
                   hubs.id hub_id, hubs.name hub_name,
                   'automatic' assignment_source
            FROM curated_registrant_satellites association
            JOIN satellites imported ON imported.id = association.satellite_id
            JOIN satellite_directory directory ON directory.id = imported.directory_id
            LEFT JOIN satellite_hubs hubs ON hubs.id = directory.hub_id
            WHERE association.curated_registrant_id = ? AND association.batch_id = ?
            ORDER BY directory.name
            """,
            (curated_registrant_id, batch_id),
        ).fetchall()
    return {
        "curated_registrant": dict(curated),
        "source_registrations": [dict(row) for row in sources],
        "effective_satellites": [dict(row) for row in effective_satellites],
    }


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
