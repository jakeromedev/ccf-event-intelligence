import csv
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from werkzeug.utils import secure_filename

from .classifier import classify_affiliation, clean
from .curation import rebuild_batch_curation
from .satellite_datasets import remap_satellite_dataset_links
from .normalization import normalize_registration_type


REGISTRANT_CORE_HEADERS = {
    "ID",
    "Event Name",
    "Event Slug",
    "Registration Code",
    "Ticket Code",
    "Ticket Status",
}

REGISTRANT_AFFILIATION_HEADERS = (
    {
        "Are You Attending Ccf",
        "Are You From A Local Or International Satellite",
        "Which Local Satellite",
        "Which International Satellite",
    },
    {
        "B1g Satellite Hub",
        "B1g Satellite",
        "Specify B1g Satellite",
    },
)


EXPORT_DEFINITIONS = {
    "tickets": {
        "required": {
            "Id",
            "Slug",
            "Event Name",
            "Ticket Code",
            "Control Number",
            "Ticket Status",
            "Payment Status",
            "Buyer Reference Number",
            "Check-in Date Time",
        },
        "unique": ("Id", "Ticket Code"),
        "warning_unique": ("Control Number",),
        "required_values": ("Ticket Code", "Control Number"),
    },
    "buyers": {
        "required": {
            "Id",
            "Slug",
            "Event Name",
            "Buyer Reference Number",
            "Payment Status",
            "Quantity",
            "Gross Amount",
            "Amount Paid",
        },
        "unique": ("Id", "Buyer Reference Number"),
        "warning_unique": (),
        "required_values": ("Buyer Reference Number",),
    },
    "registrants": {
        "required": REGISTRANT_CORE_HEADERS,
        "required_any": REGISTRANT_AFFILIATION_HEADERS,
        "unique": ("ID", "Registration Code", "Ticket Code"),
        "warning_unique": (),
        "required_values": ("Registration Code", "Ticket Code"),
    },
}


@dataclass
class Issue:
    severity: str
    category: str
    entity_type: str
    message: str
    source_row: int = None
    source_identifier: str = None


@dataclass
class FileValidation:
    export_type: str
    filename: str
    path: str
    detected_type: str = None
    status: str = "validating"
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    duplicate_records: int = 0
    relationship_issues: int = 0
    warning_count: int = 0
    rows: list = field(default_factory=list)
    issues: list = field(default_factory=list)


@dataclass
class BatchValidation:
    files: dict
    issues: list
    valid: bool
    event_slug: str = None
    event_name: str = None


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row.")
        headers = [clean(header) for header in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ValueError("CSV contains duplicate column headers.")
        rows = []
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError("CSV row {} has more values than headers.".format(row_number))
            normalized = {clean(key): value for key, value in row.items()}
            rows.append((row_number, normalized))
        return headers, rows


def detect_export_type(headers):
    header_set = set(headers)
    matches = [
        export_type
        for export_type, definition in EXPORT_DEFINITIONS.items()
        if definition["required"].issubset(header_set)
        and (
            not definition.get("required_any")
            or any(signature.issubset(header_set) for signature in definition["required_any"])
        )
    ]
    return matches[0] if len(matches) == 1 else None


def valid_datetime(value):
    value = clean(value)
    if not value:
        return True
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def stage_upload(file_storage, staging_root, slot):
    batch_token = uuid.uuid4().hex
    directory = Path(staging_root) / batch_token
    directory.mkdir(parents=True, exist_ok=False)
    filename = secure_filename(file_storage.filename or "upload.csv") or "upload.csv"
    path = directory / "{}_{}".format(slot, filename)
    file_storage.save(path)
    return str(path), filename, batch_token


def stage_upload_set(file_storages, staging_root):
    batch_token = uuid.uuid4().hex
    directory = Path(staging_root) / batch_token
    directory.mkdir(parents=True, exist_ok=False)
    staged = {}
    for slot, file_storage in file_storages.items():
        filename = secure_filename(file_storage.filename or "upload.csv") or "upload.csv"
        path = directory / "{}_{}".format(slot, filename)
        file_storage.save(path)
        staged[slot] = (str(path), filename)
    return staged


def validate_file(export_type, filename, path):
    result = FileValidation(export_type=export_type, filename=filename, path=path)
    try:
        headers, numbered_rows = read_csv(path)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        result.status = "invalid"
        result.invalid_rows = 1
        result.issues.append(Issue("error", "invalid_csv", export_type, str(exc)))
        return result

    result.detected_type = detect_export_type(headers)
    if result.detected_type != export_type:
        detected = result.detected_type or "unrecognized"
        result.status = "invalid"
        result.issues.append(
            Issue(
                "error",
                "wrong_export_type",
                export_type,
                "Expected {} export; detected {}.".format(export_type, detected),
            )
        )

    missing_columns = sorted(EXPORT_DEFINITIONS[export_type]["required"] - set(headers))
    alternative_signatures = EXPORT_DEFINITIONS[export_type].get("required_any", ())
    has_supported_signature = not alternative_signatures or any(
        signature.issubset(set(headers)) for signature in alternative_signatures
    )
    if missing_columns:
        result.status = "invalid"
        result.issues.append(
            Issue(
                "error",
                "missing_columns",
                export_type,
                "Missing required columns: {}".format(", ".join(missing_columns)),
            )
        )
    if not has_supported_signature:
        result.status = "invalid"
        result.issues.append(
            Issue(
                "error",
                "missing_columns",
                export_type,
                "Registrant export is missing a supported church-affiliation column set.",
            )
        )

    result.total_rows = len(numbered_rows)
    result.rows = [row for _number, row in numbered_rows]
    invalid_row_numbers = set()

    if not missing_columns:
        for row_number, row in numbered_rows:
            missing_values = [
                column
                for column in EXPORT_DEFINITIONS[export_type]["required_values"]
                if not clean(row.get(column))
            ]
            if missing_values:
                invalid_row_numbers.add(row_number)
                result.issues.append(
                    Issue(
                        "error",
                        "missing_identifier",
                        export_type,
                        "Missing required identifier: {}".format(", ".join(missing_values)),
                        source_row=row_number,
                    )
                )

            if export_type == "tickets" and not valid_datetime(row.get("Check-in Date Time")):
                invalid_row_numbers.add(row_number)
                result.issues.append(
                    Issue(
                        "error",
                        "invalid_datetime",
                        export_type,
                        "Check-in Date Time is not a valid date/time.",
                        source_row=row_number,
                        source_identifier=clean(row.get("Ticket Code")),
                    )
                )

            if export_type == "buyers" and clean(row.get("Quantity")):
                try:
                    quantity = float(clean(row.get("Quantity")))
                    if quantity < 0 or not quantity.is_integer():
                        raise ValueError
                except ValueError:
                    invalid_row_numbers.add(row_number)
                    result.issues.append(
                        Issue(
                            "error",
                            "invalid_quantity",
                            export_type,
                            "Quantity must be a non-negative whole number.",
                            source_row=row_number,
                            source_identifier=clean(row.get("Buyer Reference Number")),
                        )
                    )

        for column in EXPORT_DEFINITIONS[export_type]["unique"]:
            seen = {}
            for row_number, row in numbered_rows:
                value = clean(row.get(column))
                if not value:
                    continue
                if value in seen:
                    invalid_row_numbers.add(row_number)
                    result.duplicate_records += 1
                    result.issues.append(
                        Issue(
                            "error",
                            "duplicate_identifier",
                            export_type,
                            "Duplicate {} also appears on source row {}.".format(column, seen[value]),
                            source_row=row_number,
                            source_identifier=value,
                        )
                    )
                else:
                    seen[value] = row_number

        for column in EXPORT_DEFINITIONS[export_type]["warning_unique"]:
            seen = {}
            for row_number, row in numbered_rows:
                value = clean(row.get(column))
                if not value:
                    continue
                if value in seen:
                    result.duplicate_records += 1
                    result.issues.append(
                        Issue(
                            "warning",
                            "duplicate_identifier",
                            export_type,
                            "Duplicate non-primary {} also appears on source row {}; row is preserved.".format(column, seen[value]),
                            source_row=row_number,
                            source_identifier=value,
                        )
                    )
                else:
                    seen[value] = row_number

    result.invalid_rows = len(invalid_row_numbers)
    result.valid_rows = result.total_rows - result.invalid_rows
    if any(issue.severity == "error" for issue in result.issues):
        result.status = "invalid"
    else:
        result.status = "valid"
    return result


def validate_batch(staged):
    files = {
        export_type: validate_file(export_type, filename, path)
        for export_type, (path, filename) in staged.items()
    }
    issues = [issue for result in files.values() for issue in result.issues]

    if any(result.status == "invalid" for result in files.values()):
        return BatchValidation(files=files, issues=issues, valid=False)

    ticket_rows = files["tickets"].rows
    buyer_rows = files["buyers"].rows
    registrant_rows = files["registrants"].rows

    buyer_refs = {clean(row.get("Buyer Reference Number")) for row in buyer_rows}
    buyer_refs.discard("")
    ticket_refs = {clean(row.get("Buyer Reference Number")) for row in ticket_rows}
    ticket_refs.discard("")
    ticket_codes = {clean(row.get("Ticket Code")) for row in ticket_rows}
    for row_number, row in enumerate(ticket_rows, start=2):
        buyer_reference = clean(row.get("Buyer Reference Number"))
        if buyer_reference and buyer_reference not in buyer_refs:
            files["tickets"].relationship_issues += 1
            issues.append(
                Issue(
                    "warning",
                    "ticket_without_buyer",
                    "tickets",
                    "Ticket buyer reference does not match the Buyers export.",
                    source_row=row_number,
                    source_identifier=clean(row.get("Ticket Code")),
                )
            )

    for row_number, row in enumerate(registrant_rows, start=2):
        ticket_code = clean(row.get("Ticket Code"))
        if ticket_code not in ticket_codes:
            files["registrants"].relationship_issues += 1
            issues.append(
                Issue(
                    "warning",
                    "registrant_without_ticket",
                    "registrants",
                    "Registrant ticket code does not match the Generated Tickets export.",
                    source_row=row_number,
                    source_identifier=ticket_code,
                )
            )

    for row_number, row in enumerate(buyer_rows, start=2):
        buyer_reference = clean(row.get("Buyer Reference Number"))
        if buyer_reference not in ticket_refs:
            files["buyers"].relationship_issues += 1
            issues.append(
                Issue(
                    "warning",
                    "buyer_without_ticket",
                    "buyers",
                    "Buyer reference has no matching generated ticket.",
                    source_row=row_number,
                    source_identifier=buyer_reference,
                )
            )

    ticket_slugs = {clean(row.get("Slug")) for row in ticket_rows if clean(row.get("Slug"))}
    buyer_slugs = {clean(row.get("Slug")) for row in buyer_rows if clean(row.get("Slug"))}
    registrant_slugs = {clean(row.get("Event Slug")) for row in registrant_rows if clean(row.get("Event Slug"))}
    all_slugs = ticket_slugs | buyer_slugs | registrant_slugs
    event_names = {
        clean(row.get("Event Name"))
        for rows in (ticket_rows, buyer_rows, registrant_rows)
        for row in rows
        if clean(row.get("Event Name"))
    }
    if len(all_slugs) != 1 or len(event_names) != 1:
        issues.append(
            Issue(
                "error",
                "event_mismatch",
                "batch",
                "The three exports must describe exactly one matching event slug and event name.",
            )
        )

    for result in files.values():
        result.warning_count = sum(
            1 for issue in issues if issue.entity_type == result.export_type and issue.severity == "warning"
        )

    valid = not any(issue.severity == "error" for issue in issues)
    return BatchValidation(
        files=files,
        issues=issues,
        valid=valid,
        event_slug=next(iter(all_slugs), None) if len(all_slugs) == 1 else None,
        event_name=next(iter(event_names), None) if len(event_names) == 1 else None,
    )


def store_validation(db, validation, event_id):
    event = db.execute("SELECT id FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        raise ValueError("The selected event does not exist.")
    status = "validated" if validation.valid else "invalid"
    cursor = db.execute(
        "INSERT INTO import_batches (event_id, event_slug, event_name, status) VALUES (?, ?, ?, ?)",
        (event_id, validation.event_slug, validation.event_name, status),
    )
    batch_id = cursor.lastrowid

    for export_type, result in validation.files.items():
        db.execute(
            """
            INSERT INTO import_files (
                batch_id, export_type, filename, staged_path, status, total_rows,
                valid_rows, invalid_rows, duplicate_records, relationship_issues,
                warning_count, detected_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                export_type,
                result.filename,
                result.path,
                result.status,
                result.total_rows,
                result.valid_rows,
                result.invalid_rows,
                result.duplicate_records,
                result.relationship_issues,
                result.warning_count,
                result.detected_type,
            ),
        )

    _insert_issues(db, batch_id, validation.issues)
    db.commit()
    return batch_id


def _insert_issues(db, batch_id, issues):
    db.executemany(
        """
        INSERT INTO validation_issues (
            batch_id, severity, category, entity_type, source_row,
            source_identifier, message
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                batch_id,
                issue.severity,
                issue.category,
                issue.entity_type,
                issue.source_row,
                issue.source_identifier,
                issue.message,
            )
            for issue in issues
        ],
    )


def process_batch(db, batch_id):
    batch = db.execute("SELECT * FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
    if not batch or batch["status"] != "validated":
        raise ValueError("Only a fully validated three-file batch can be processed.")

    file_rows = db.execute(
        "SELECT export_type, staged_path FROM import_files WHERE batch_id = ? AND status = 'valid'",
        (batch_id,),
    ).fetchall()
    paths = {row["export_type"]: row["staged_path"] for row in file_rows}
    if set(paths) != set(EXPORT_DEFINITIONS):
        raise ValueError("All three valid exports are required.")

    parsed = {}
    try:
        for export_type, path in paths.items():
            _headers, numbered_rows = read_csv(path)
            parsed[export_type] = [row for _number, row in numbered_rows]
    except Exception as exc:
        db.execute(
            "UPDATE import_batches SET status = 'failed', error_message = ? WHERE id = ?",
            (str(exc), batch_id),
        )
        db.commit()
        raise

    # Serialize replacement of an Event's active batch. The checked nullable
    # unique column remains the final database-level guard against concurrent writers.
    db.lock_event(batch["event_id"])
    db.execute(
        "UPDATE import_batches SET status = 'processing', active_event_id = NULL WHERE id = ?",
        (batch_id,),
    )
    try:
        for row in parsed["buyers"]:
            quantity = clean(row.get("Quantity"))
            try:
                quantity_value = int(float(quantity)) if quantity else None
            except ValueError:
                quantity_value = None
            db.execute(
                """
                INSERT INTO buyers (
                    batch_id, source_id, event_slug, buyer_reference,
                    payment_status, quantity, source_data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    clean(row.get("Id")),
                    clean(row.get("Slug")),
                    clean(row.get("Buyer Reference Number")),
                    clean(row.get("Payment Status")),
                    quantity_value,
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                ),
            )

        for row in parsed["tickets"]:
            check_in_raw = clean(row.get("Check-in Date Time"))
            check_in_at = datetime.fromisoformat(check_in_raw).replace(tzinfo=None) if check_in_raw else None
            db.execute(
                """
                INSERT INTO tickets (
                    batch_id, source_id, event_slug, ticket_code, control_number,
                    buyer_reference, ticket_status, payment_status, check_in_at,
                    source_data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    clean(row.get("Id")),
                    clean(row.get("Slug")),
                    clean(row.get("Ticket Code")),
                    clean(row.get("Control Number")),
                    clean(row.get("Buyer Reference Number")) or None,
                    clean(row.get("Ticket Status")),
                    clean(row.get("Payment Status")),
                    check_in_at,
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                ),
            )

        ticket_checkins = {
            clean(row.get("Ticket Code")): bool(clean(row.get("Check-in Date Time")))
            for row in parsed["tickets"]
        }
        ticket_names = {
            clean(row.get("Ticket Code")): clean(row.get("Ticket Name"))
            for row in parsed["tickets"]
        }
        quality_issues = []
        for source_row, row in enumerate(parsed["registrants"], start=2):
            classification = classify_affiliation(row)
            ticket_code = clean(row.get("Ticket Code"))
            ticket_name = clean(row.get("Ticket Name")) or ticket_names.get(ticket_code, "")
            identity_values = [
                clean(row.get("First Name")),
                clean(row.get("Last Name")),
                clean(row.get("Email Address")),
                clean(row.get("Mobile Number")),
            ]
            db.execute(
                """
                INSERT INTO registrants (
                    batch_id, source_id, event_slug, registration_code, ticket_code,
                    ticket_name_raw, ticket_status, first_name, last_name,
                    first_name_present, last_name_present,
                    email_present, mobile_present, gender_raw, life_stage_raw,
                    birth_date_raw, birth_month_raw, birth_year_raw,
                    b1g_satellite_hub_raw, b1g_satellite_raw,
                    b1g_satellite_specify_raw, attending_ccf_raw,
                    satellite_scope_raw, local_satellite_raw,
                    international_satellite_raw, affiliation, satellite_name,
                    registration_type, ticket_matched, checked_in
                    , source_data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    clean(row.get("ID")),
                    clean(row.get("Event Slug")),
                    clean(row.get("Registration Code")),
                    ticket_code,
                    ticket_name or None,
                    clean(row.get("Ticket Status")),
                    identity_values[0] or None,
                    identity_values[1] or None,
                    int(bool(identity_values[0])),
                    int(bool(identity_values[1])),
                    int(bool(identity_values[2])),
                    int(bool(identity_values[3])),
                    clean(row.get("Gender")) or None,
                    clean(row.get("Life Stage")) or None,
                    clean(row.get("Date of Birth") or row.get("Birth Date")) or None,
                    clean(row.get("Birth Month")) or None,
                    clean(row.get("Birth Year")) or None,
                    clean(row.get("B1g Satellite Hub")) or None,
                    clean(row.get("B1g Satellite")) or None,
                    clean(row.get("Specify B1g Satellite")) or None,
                    clean(row.get("Are You Attending Ccf")),
                    clean(row.get("Are You From A Local Or International Satellite")),
                    clean(row.get("Which Local Satellite")),
                    clean(row.get("Which International Satellite")),
                    classification.affiliation,
                    classification.satellite_name,
                    normalize_registration_type(ticket_name, row.get("Event Name")),
                    int(ticket_code in ticket_checkins),
                    int(ticket_checkins.get(ticket_code, False)),
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                ),
            )

            if classification.affiliation == "Unknown":
                quality_issues.append(
                    Issue(
                        "warning",
                        "unknown_affiliation",
                        "registrants",
                        "Church affiliation is unanswered or cannot be classified.",
                        source_row=source_row,
                        source_identifier=clean(row.get("Registration Code")),
                    )
                )
            if not any(identity_values):
                quality_issues.append(
                    Issue(
                        "warning",
                        "incomplete_profile",
                        "registrants",
                        "Registrant has no name, email, or mobile profile fields.",
                        source_row=source_row,
                        source_identifier=clean(row.get("Registration Code")),
                    )
                )
            if classification.contradictory:
                quality_issues.append(
                    Issue(
                        "warning",
                        "contradictory_affiliation",
                        "registrants",
                        "Non-CCF response contains satellite information; Non-CCF takes precedence.",
                        source_row=source_row,
                        source_identifier=clean(row.get("Registration Code")),
                    )
                )

        ticket_codes = set(ticket_checkins)
        registrant_codes = {clean(row.get("Ticket Code")) for row in parsed["registrants"]}
        for ticket_code in sorted(ticket_codes - registrant_codes):
            quality_issues.append(
                Issue(
                    "warning",
                    "ticket_without_registrant",
                    "tickets",
                    "Generated ticket has no matching registrant.",
                    source_identifier=ticket_code,
                )
            )

        _insert_issues(db, batch_id, quality_issues)
        rebuild_batch_curation(db, batch_id)
        _set_active_batch(db, batch["event_id"], batch_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        db.execute(
            "UPDATE import_batches SET status = 'failed', active_event_id = NULL, "
            "error_message = ? WHERE id = ?",
            (str(exc), batch_id),
        )
        db.commit()
        raise

    return batch_id


def _set_active_batch(db, event_id, batch_id):
    """Switch one processed Event batch active within the caller's transaction."""
    remap_satellite_dataset_links(db, event_id, batch_id)
    db.execute(
        """
        UPDATE import_batches SET status = 'inactive', active_event_id = NULL
        WHERE event_id = ? AND status = 'active' AND id <> ?
        """,
        (event_id, batch_id),
    )
    db.execute(
        """
        UPDATE import_batches
        SET status = 'active', active_event_id = event_id,
            processed_at = COALESCE(processed_at, CURRENT_TIMESTAMP),
            activated_at = CURRENT_TIMESTAMP,
            error_message = NULL
        WHERE id = ? AND event_id = ?
        """,
        (batch_id, event_id),
    )
    db.execute(
        "UPDATE events SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (event_id,),
    )


def activate_batch(db, event_id, batch_id):
    """Make an already processed inactive batch drive its Event again."""
    db.lock_event(event_id)
    batch = db.execute(
        "SELECT * FROM import_batches WHERE id = ? AND event_id = ?",
        (batch_id, event_id),
    ).fetchone()
    if not batch:
        raise LookupError("The import batch does not exist for this Event.")
    if batch["status"] == "active":
        return False
    if batch["status"] != "inactive" or not batch["processed_at"]:
        raise ValueError("Only a previously processed inactive batch can be activated.")
    try:
        _set_active_batch(db, event_id, batch_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True
