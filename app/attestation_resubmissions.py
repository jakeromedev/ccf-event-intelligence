"""Event-scoped imports of replacement attestation links, without replacing a batch."""

import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict

from .attestation_identity import _normalize_identifier
from .time_utils import utc_now
from .url_safety import safe_external_url

LINK_HEADER = "Reupload Your Accomplished Attestation Form Here"
MAX_RESUBMISSION_BYTES = 8 * 1024 * 1024
MAX_RESUBMISSION_ROWS = 5000


class AttestationResubmissionError(ValueError):
    pass


def _phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("09") and len(digits) == 11:
        digits = "63" + digits[1:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "63" + digits
    return digits if len(digits) >= 10 else None


def _json(value):
    try:
        result = json.loads(value or "{}")
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def parse_resubmission_csv(content):
    if not content or len(content) > MAX_RESUBMISSION_BYTES:
        raise AttestationResubmissionError("Choose a nonempty CSV file no larger than 8 MB.")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise AttestationResubmissionError("The CSV contains duplicate column headers.")
        if LINK_HEADER not in headers or not any(
            key in headers for key in ("Email Address", "Mobile Number", "Registration Code", "Ticket Code")
        ):
            raise AttestationResubmissionError(
                "Use the AF resubmission CSV with the reupload link and registrant contact or registration columns."
            )
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise AttestationResubmissionError("A CSV row has missing or extra columns.")
            if any(value.strip() for value in row.values()):
                rows.append(row)
            if len(rows) > MAX_RESUBMISSION_ROWS:
                raise AttestationResubmissionError("Upload no more than 5,000 rows at once.")
    except (UnicodeError, csv.Error) as exc:
        raise AttestationResubmissionError("The file must be a valid UTF-8 CSV export.") from exc
    if not rows:
        raise AttestationResubmissionError("The CSV has no data rows.")
    return rows


def match_resubmissions(db, event_id, rows):
    """Match within the active Event; separate-form IDs never match original IDs."""
    batch = db.execute(
        "SELECT id, event_slug FROM import_batches WHERE event_id = ? AND status = 'active'",
        (event_id,),
    ).fetchone()
    if not batch:
        raise AttestationResubmissionError("Activate a registration import for this Event first.")
    targets = db.execute(
        """SELECT record.id, record.source_id, record.registration_code, record.ticket_code,
                  record.source_data_json, owner.attestation_participant_id
           FROM registrants record
           JOIN attestation_participant_registrants owner
             ON owner.registrant_id = record.id AND owner.batch_id = record.batch_id
           WHERE record.batch_id = ? AND owner.event_id = ?""",
        (batch["id"], event_id),
    ).fetchall()
    indexes = defaultdict(lambda: defaultdict(set))
    people = {}
    for record in targets:
        participant = record["attestation_participant_id"]
        source = _json(record["source_data_json"])
        person = people.setdefault(participant, {"registrant_id": record["id"], "original_links": set()})
        original = safe_external_url(source.get("Upload Your Accomplished Attestation Form Here"))
        if original:
            person["original_links"].add(original)
        values = {
            "ID": record["source_id"], "Registration Code": record["registration_code"],
            "Ticket Code": record["ticket_code"], "Email Address": source.get("Email Address"),
            "Mobile Number": _phone(source.get("Mobile Number")),
        }
        for key, value in values.items():
            normalized = _normalize_identifier(value)
            if normalized:
                indexes[key][normalized].add(participant)
    matched = []
    for number, row in enumerate(rows, 2):
        candidates = set()
        keys = ["Email Address", "Mobile Number"]
        # The resubmission form is a different source Event. Its generated IDs
        # are useful only when the export explicitly has the original slug.
        if batch["event_slug"] and row.get("Event Slug") == batch["event_slug"]:
            keys += ["ID", "Registration Code", "Ticket Code"]
        for key in keys:
            value = _phone(row.get(key)) if key == "Mobile Number" else row.get(key)
            normalized = _normalize_identifier(value)
            if normalized:
                candidates.update(indexes[key].get(normalized, ()))
        participant = next(iter(candidates)) if len(candidates) == 1 else None
        matched.append({
            "row": number,
            "name": " ".join(filter(None, (row.get("First Name"), row.get("Last Name")))),
            "registration_code": row.get("Registration Code", ""),
            "participant_id": participant,
            "link": safe_external_url(row.get(LINK_HEADER)),
            "status": "ambiguous" if len(candidates) > 1 else "unmatched" if not candidates else None,
        })
    return batch, people, matched


def import_attestation_resubmissions(db, event_id, content, filename, user_id):
    rows = parse_resubmission_csv(content)
    # Serialize uploads for this Event. Review updates also lock the participant
    # row, so an import cannot race a human's Verified decision.
    lock = " FOR UPDATE" if db.is_mysql else ""
    db.execute("SELECT id FROM events WHERE id = ?" + lock, (event_id,)).fetchone()
    batch, people, matches = match_resubmissions(db, event_id, rows)
    import_id = db.execute(
        """INSERT INTO attestation_resubmission_imports
           (event_id, filename, report_json, created_by_user_id) VALUES (?, ?, '{}', ?)""",
        (event_id, filename[:255], user_id),
    ).lastrowid
    links_by_person = defaultdict(set)
    for item in matches:
        if item["participant_id"] and item["link"]:
            links_by_person[item["participant_id"]].add(item["link"])
    counts = Counter()
    for item in matches:
        participant = item["participant_id"]
        link = item["link"]
        status = item["status"]
        if not link:
            status = "missing_or_invalid_link"
        if not status and len(links_by_person[participant]) > 1:
            status = "conflicting_links"
        if not status:
            db.execute(
                "SELECT id FROM attestation_participants WHERE id = ? AND event_id = ?" + lock,
                (participant, event_id),
            ).fetchone()
            verification = db.execute(
                "SELECT status, form_url FROM attestation_verifications "
                "WHERE event_id = ? AND attestation_participant_id = ?" + lock,
                (event_id, participant),
            ).fetchone()
            digest = hashlib.sha256(link.encode("utf-8")).hexdigest()
            seen = db.execute(
                "SELECT id FROM attestation_resubmissions WHERE event_id = ? "
                "AND attestation_participant_id = ? AND link_hash = ?",
                (event_id, participant, digest),
            ).fetchone()
            if verification and verification["status"] == "verified":
                status = "verified_protected"
            elif seen or link in people[participant]["original_links"] or (
                verification and link == verification["form_url"]
            ):
                status = "unchanged"
            else:
                db.execute(
                    """INSERT INTO attestation_resubmissions
                       (event_id, attestation_participant_id, import_id, link_hash, form_url)
                       VALUES (?, ?, ?, ?, ?)""", (event_id, participant, import_id, digest, link),
                )
                now = utc_now()
                if verification:
                    db.execute(
                        """UPDATE attestation_verifications SET status = 'to_verify', form_url = ?,
                           updated_by_user_id = NULL, updated_at = ?, registrant_id = ?
                           WHERE event_id = ? AND attestation_participant_id = ?""",
                        (link, now, people[participant]["registrant_id"], event_id, participant),
                    )
                else:
                    db.execute(
                        """INSERT INTO attestation_verifications
                           (event_id, attestation_participant_id, registrant_id, status, form_url)
                           VALUES (?, ?, ?, 'to_verify', ?)""",
                        (event_id, participant, people[participant]["registrant_id"], link),
                    )
                status = "updated"
        item["status"] = status
        counts[status] += 1
        # Keep the report useful without persisting private document URLs twice.
        item.pop("link")
    report = {"batch_id": batch["id"], "total": len(matches), "counts": dict(counts), "rows": matches}
    db.execute("UPDATE attestation_resubmission_imports SET report_json = ? WHERE id = ?",
               (json.dumps(report), import_id))
    return import_id, report
