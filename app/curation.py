"""Deterministic, rebuildable registrant and satellite curation.

Raw ``registrants`` rows remain the import source of truth. Every row written by
this module is derived, batch-scoped, and traceable back through source mappings.
"""

import calendar
import re
import unicodedata
from collections import Counter, defaultdict

from .normalization import normalize_gender, normalize_life_stage
from .satellite_datasets import (
    capture_rebuilt_batch_links,
    restore_rebuilt_batch_links,
)


IDENTITY_FIELDS = ("Last Name", "Birth Month", "Birth Year", "Gender")
AFFILIATION_PRIORITY = {
    "CCF Main": 0,
    "Local Satellite": 1,
    "International Satellite": 2,
}
LIFE_STAGE_PRIORITY = ("single", "single-parent", "married", "unknown")


def clean_text(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).strip().split())


def normalize_last_name(value):
    cleaned = clean_text(value)
    return cleaned.casefold() if cleaned else None


def normalize_birth_month(value):
    cleaned = clean_text(value).casefold()
    if not cleaned:
        return None
    month_names = {
        name.casefold(): number
        for number, name in enumerate(calendar.month_name)
        if name
    }
    month_names.update(
        {
            name.casefold(): number
            for number, name in enumerate(calendar.month_abbr)
            if name
        }
    )
    try:
        month = int(cleaned) if cleaned.isdigit() else month_names[cleaned]
    except (KeyError, TypeError, ValueError):
        return None
    return "{:02d}".format(month) if 1 <= month <= 12 else None


def normalize_birth_year(value):
    cleaned = clean_text(value)
    if not re.fullmatch(r"\d{4}", cleaned):
        return None
    year = int(cleaned)
    return str(year) if 1900 <= year <= 2100 else None


def normalize_identity(row):
    last_name = normalize_last_name(row["last_name"])
    birth_month = normalize_birth_month(row["birth_month_raw"])
    birth_year = normalize_birth_year(row["birth_year_raw"])
    gender = normalize_gender(row["gender_raw"])
    values = (last_name, birth_month, birth_year, gender)
    missing = []
    if not last_name:
        missing.append("Last Name")
    if not birth_month:
        missing.append("Birth Month")
    if not birth_year:
        missing.append("Birth Year")
    if gender not in ("male", "female"):
        missing.append("Gender")
    complete = not missing
    return {
        "normalized_last_name": last_name,
        "normalized_birth_month": birth_month,
        "normalized_birth_year": birth_year,
        "normalized_gender": gender if gender in ("male", "female") else None,
        "complete": complete,
        "missing": missing,
        "dedupe_key": "|".join(values) if complete else "incomplete:{}".format(row["id"]),
    }


def _display_words(value):
    words = clean_text(value).lower().title()
    return re.sub(r"\bCcf\b", "CCF", re.sub(r"\bB1G\b", "B1G", words, flags=re.I))


def normalize_satellite_name(value, affiliation):
    """Return a conservative normalized key/display pair for a satellite."""
    cleaned = clean_text(value)
    if not cleaned or affiliation not in AFFILIATION_PRIORITY:
        return None
    if affiliation == "CCF Main":
        return {"key": "ccf main", "name": "CCF Main", "source": cleaned}

    folded = cleaned.casefold()
    if folded.startswith("b1g "):
        core = clean_text(cleaned[4:])
        if not core:
            return None
        return {
            "key": "b1g {}".format(core.casefold()),
            "name": "B1G {}".format(_display_words(core)),
            "source": cleaned,
        }

    core = re.sub(r"^ccf\s+", "", cleaned, flags=re.IGNORECASE).strip()
    if not core:
        return None
    return {
        "key": "ccf {}".format(core.casefold()),
        "name": "CCF {}".format(_display_words(core)),
        "source": cleaned,
    }


def _satellite_directory_id(db, normalized_name, display_name, source_hubs):
    """Resolve an imported name without guessing between same-name Hub entries."""
    for source_hub, _count in source_hubs.most_common():
        matched = db.execute(
            """
            SELECT directory.id
            FROM satellite_directory directory
            JOIN satellite_hubs hub ON hub.id = directory.hub_id
            WHERE directory.normalized_name = ? AND hub.normalized_name = ?
            """,
            (normalized_name, clean_text(source_hub).casefold()),
        ).fetchone()
        if matched:
            return matched["id"]

    candidates = db.execute(
        """
        SELECT id, hub_id FROM satellite_directory
        WHERE normalized_name = ?
        ORDER BY CASE WHEN hub_id IS NULL THEN 0 ELSE 1 END, id
        """,
        (normalized_name,),
    ).fetchall()
    if len(candidates) == 1 or (candidates and candidates[0]["hub_id"] is None):
        return candidates[0]["id"]
    return db.execute(
        """
        INSERT INTO satellite_directory (name, normalized_name)
        VALUES (?, ?)
        """,
        (display_name, normalized_name),
    ).lastrowid


def _resolved_life_stage(rows):
    counts = Counter(normalize_life_stage(row["life_stage_raw"]) for row in rows)
    return min(
        LIFE_STAGE_PRIORITY,
        key=lambda value: (-counts[value], LIFE_STAGE_PRIORITY.index(value)),
    )


def _resolved_registration_type(rows):
    types = {row["registration_type"] for row in rows}
    # Participant precedence keeps a conflicted person in participant-target
    # reporting while the conflict flag and source mappings make the decision
    # fully visible for review.
    return ("participant" if "participant" in types else "volunteer", len(types) > 1)


def rebuild_batch_curation(db, batch_id):
    """Replace one batch's derived curation layer without committing.

    Callers own the surrounding transaction. Re-running this function produces
    the same logical groups, mappings, satellite variations, and relationships.
    """
    batch = db.execute(
        "SELECT id, event_id FROM import_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if batch is None:
        raise ValueError("The import batch does not exist.")
    event_id = batch["event_id"]
    if event_id is None:
        raise ValueError("The import batch is not owned by an Event.")

    preserved_dataset_links = capture_rebuilt_batch_links(db, batch_id)
    rows = db.execute(
        """
        SELECT id, registration_code, source_id, first_name, last_name,
               gender_raw, life_stage_raw, birth_date_raw, birth_month_raw, birth_year_raw,
               registration_type, checked_in, affiliation, satellite_name,
               b1g_satellite_hub_raw
        FROM registrants
        WHERE batch_id = ? AND ticket_matched = 1
        ORDER BY id
        """,
        (batch_id,),
    ).fetchall()

    # Both roots cascade to mappings, variations, and pivot rows.
    db.execute("DELETE FROM curated_registrants WHERE batch_id = ?", (batch_id,))
    db.execute("DELETE FROM satellites WHERE batch_id = ?", (batch_id,))

    grouped = defaultdict(list)
    identity_by_registrant = {}
    satellite_by_registrant = defaultdict(set)
    satellite_aggregates = {}

    for row in rows:
        identity = normalize_identity(row)
        identity_by_registrant[row["id"]] = identity
        grouped[identity["dedupe_key"]].append(row)

        satellite = normalize_satellite_name(row["satellite_name"], row["affiliation"])
        if satellite:
            key = satellite["key"]
            aggregate = satellite_aggregates.setdefault(
                key,
                {
                    "name": satellite["name"],
                    "affiliations": Counter(),
                    "source_count": 0,
                    "variations": Counter(),
                    "source_hubs": Counter(),
                },
            )
            aggregate["affiliations"][row["affiliation"]] += 1
            aggregate["source_count"] += 1
            aggregate["variations"][(satellite["source"], row["affiliation"])] += 1
            if clean_text(row["b1g_satellite_hub_raw"]):
                aggregate["source_hubs"][
                    clean_text(row["b1g_satellite_hub_raw"])
                ] += 1
            satellite_by_registrant[row["id"]].add(key)

    curated_ids = {}
    for dedupe_key in sorted(grouped):
        sources = grouped[dedupe_key]
        identity = identity_by_registrant[sources[0]["id"]]
        registration_type, type_conflict = _resolved_registration_type(sources)
        display_last_name = next(
            (clean_text(row["last_name"]) for row in sources if clean_text(row["last_name"])),
            None,
        )
        cursor = db.execute(
            """
            INSERT INTO curated_registrants (
                event_id, batch_id, last_name, birth_date, birth_month, birth_year, gender,
                life_stage, normalized_last_name, normalized_birth_month,
                normalized_birth_year, normalized_gender, dedupe_key,
                dedupe_complete, dedupe_status, missing_identity_fields,
                registration_type, registration_type_conflict, checked_in,
                source_registrant_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                batch_id,
                display_last_name,
                next(
                    (
                        clean_text(row["birth_date_raw"])
                        for row in sources
                        if clean_text(row["birth_date_raw"])
                    ),
                    None,
                ),
                identity["normalized_birth_month"],
                identity["normalized_birth_year"],
                identity["normalized_gender"],
                _resolved_life_stage(sources),
                identity["normalized_last_name"],
                identity["normalized_birth_month"],
                identity["normalized_birth_year"],
                identity["normalized_gender"],
                dedupe_key,
                int(identity["complete"]),
                "complete" if identity["complete"] else "incomplete",
                ", ".join(identity["missing"]) or None,
                registration_type,
                int(type_conflict),
                int(any(row["checked_in"] for row in sources)),
                len(sources),
            ),
        )
        curated_id = cursor.lastrowid
        curated_ids[dedupe_key] = curated_id
        db.executemany(
            """
            INSERT INTO curated_registrant_sources (
                event_id, batch_id, curated_registrant_id, registrant_id
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (event_id, batch_id, curated_id, source["id"])
                for source in sources
            ],
        )

    satellite_ids = {}
    for key in sorted(satellite_aggregates):
        aggregate = satellite_aggregates[key]
        affiliation = min(
            aggregate["affiliations"],
            key=lambda value: (
                -aggregate["affiliations"][value],
                AFFILIATION_PRIORITY[value],
            ),
        )
        directory_id = _satellite_directory_id(
            db, key, aggregate["name"], aggregate["source_hubs"]
        )
        cursor = db.execute(
            """
            INSERT INTO satellites (
                event_id, batch_id, directory_id, name, normalized_name, affiliation,
                affiliation_conflict, source_record_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                batch_id,
                directory_id,
                aggregate["name"],
                key,
                affiliation,
                int(len(aggregate["affiliations"]) > 1),
                aggregate["source_count"],
            ),
        )
        satellite_id = cursor.lastrowid
        satellite_ids[key] = satellite_id
        db.executemany(
            """
            INSERT INTO satellite_source_variations (
                event_id, batch_id, satellite_id, source_value,
                normalized_source_value, affiliation, source_record_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event_id,
                    batch_id,
                    satellite_id,
                    source_value,
                    clean_text(source_value).casefold(),
                    source_affiliation,
                    count,
                )
                for (source_value, source_affiliation), count
                in sorted(aggregate["variations"].items())
            ],
        )

    pivot_rows = []
    for dedupe_key, sources in grouped.items():
        curated_id = curated_ids[dedupe_key]
        satellite_keys = set()
        for source in sources:
            satellite_keys.update(satellite_by_registrant[source["id"]])
        pivot_rows.extend(
            (event_id, batch_id, curated_id, satellite_ids[key])
            for key in sorted(satellite_keys)
        )
    db.executemany(
        """
        INSERT INTO curated_registrant_satellites (
            event_id, batch_id, curated_registrant_id, satellite_id
        ) VALUES (?, ?, ?, ?)
        """,
        pivot_rows,
    )
    restore_rebuilt_batch_links(
        db, event_id, batch_id, preserved_dataset_links
    )

    return {
        "raw_registrants": len(rows),
        "curated_registrants": len(grouped),
        "satellites": len(satellite_aggregates),
        "satellite_relationships": len(pivot_rows),
    }
