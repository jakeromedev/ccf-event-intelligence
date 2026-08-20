# Event Imports Module

## Purpose

The Event Imports module accepts one complete set of CCF event exports, validates the files together, stores an audit record, and activates the resulting dataset for a selected Event.

Each import batch requires exactly three CSV exports:

1. **Generated Tickets** — ticket inventory, ticket/payment status, buyer relationship, and check-in timestamp.
2. **Buyers** — purchase reference, payment status, and quantity.
3. **Registrants** — participant identity/profile fields, ticket relationship, and church-affiliation responses.

An Event can have many historical batches but only one active batch. Uploading or validating a new batch does not change the active dashboard. Activation occurs only after the complete batch processes successfully.

## Primary implementation files

| File | Responsibility |
|---|---|
| `app/templates/imports.html` | Upload form, client-side file-selection states, validation summary, process action, and import history |
| `app/routes.py` | Event-scoped Imports routes and request/error handling |
| `app/import_history.py` | Sanitized Event-scoped history search, status filtering, sorting, and pagination |
| `app/importer.py` | CSV staging, detection, validation, issue generation, persistence, processing, and activation |
| `app/classifier.py` | Converts supported registrant affiliation answers into dashboard categories |
| `app/db.py` | Import, normalized record, issue, index, and event-isolation schema |
| `app/static/app.css` | Upload, validation, status, history, and responsive presentation |
| `scripts/import_provided.py` | Command-line import of the supplied project CSV files |
| `tests/test_phase1.py` | Unit, integration, migration, event-isolation, and supplied-dataset coverage |

## User workflow

```text
Open an Event's Imports page
  → select all three required CSV files
  → submit the complete set
  → files are copied into one unique staging directory
  → each file is detected and validated
  → cross-file relationships and event identity are checked
  → a validated or invalid batch is saved in import history
  → review file totals, errors, and warnings
  → process a validated batch
  → normalized records are inserted in one transaction
  → the previous active batch for that Event is superseded
  → the new batch becomes active
```

If validation or processing fails, the Event's previous active dataset remains active.

## HTTP routes

| Method | Route | Behavior |
|---|---|---|
| `GET` | `/events/<event_id>/imports` | Shows the upload form, newest validation summary, and Event-scoped import history |
| `GET` | `/events/<event_id>/imports?batch=<batch_id>` | Shows one batch's file and issue summary; returns `404` if the batch belongs to another Event |
| `POST` | `/events/<event_id>/imports/validate` | Requires all three uploads, stages them, validates them, and stores the result |
| `POST` | `/events/<event_id>/imports/<batch_id>/process` | Processes and activates a validated batch owned by the Event |

The legacy unscoped `/imports` URL redirects to the Events page.

## Upload behavior

- All three files are mandatory in one request.
- The browser accepts `.csv`/`text/csv`; all authoritative validation is server-side.
- The complete request is limited to **32 MB** by `MAX_CONTENT_LENGTH`.
- Filenames do not determine the export type. The module detects file types from their headers and verifies that each file was placed in the correct slot.
- Filenames are sanitized with Werkzeug's `secure_filename` before staging.
- Each set is stored in a UUID-named directory under `instance/staged_imports/` by default.
- CSV files are read as UTF-8 with optional BOM support (`utf-8-sig`) and strict CSV parsing.
- Blank header rows, duplicate column headers, and rows containing more values than headers are rejected.

## Supported export signatures

### Generated Tickets

Required headers:

- `Id`
- `Slug`
- `Event Name`
- `Ticket Code`
- `Control Number`
- `Ticket Status`
- `Payment Status`
- `Buyer Reference Number`
- `Check-in Date Time`

Required values: `Ticket Code`, `Control Number`.

Unique within the file: `Id`, `Ticket Code`.

A repeated `Control Number` is a warning. The affected row is preserved because control numbers are treated as non-primary identifiers.

### Buyers

Required headers:

- `Id`
- `Slug`
- `Event Name`
- `Buyer Reference Number`
- `Payment Status`
- `Quantity`
- `Gross Amount`
- `Amount Paid`

Required value: `Buyer Reference Number`.

Unique within the file: `Id`, `Buyer Reference Number`.

### Registrants

Required core headers:

- `ID`
- `Event Name`
- `Event Slug`
- `Registration Code`
- `Ticket Code`
- `Ticket Status`

The export must also contain one supported church-affiliation header family.

Standard CCF family:

- `Are You Attending Ccf`
- `Are You From A Local Or International Satellite`
- `Which Local Satellite`
- `Which International Satellite`

B1G family:

- `B1g Satellite Hub`
- `B1g Satellite`
- `Specify B1g Satellite`

Required values: `Registration Code`, `Ticket Code`.

Unique within the file: `ID`, `Registration Code`, `Ticket Code`.

## Validation rules

### Blocking errors

Any error marks the complete batch invalid and prevents processing.

| Category | Condition |
|---|---|
| `invalid_csv` | The CSV cannot be read strictly, has no headers, has duplicate headers, or has malformed row widths |
| `wrong_export_type` | Detected headers do not match the upload slot |
| `missing_columns` | Required headers or a supported registrant affiliation family are missing |
| `missing_identifier` | A required row identifier is blank |
| `invalid_datetime` | A nonblank ticket check-in value cannot be parsed by `datetime.fromisoformat` |
| `invalid_quantity` | A nonblank buyer quantity is negative or not a whole number |
| `duplicate_identifier` | A primary unique identifier is repeated within an export |
| `event_mismatch` | The three files do not resolve to exactly one matching event slug and one event name |

### Non-blocking warnings

Warnings remain visible but do not stop activation.

| Category | Condition |
|---|---|
| `duplicate_identifier` | A ticket `Control Number` repeats; the row is retained |
| `ticket_without_buyer` | A ticket's buyer reference is absent from Buyers |
| `registrant_without_ticket` | A registrant's ticket code is absent from Generated Tickets |
| `buyer_without_ticket` | A buyer reference is unused by Generated Tickets |
| `ticket_without_registrant` | A generated ticket has no registrant row |
| `unknown_affiliation` | A registrant's church affiliation cannot be classified |
| `incomplete_profile` | First name, last name, email, and mobile are all blank |
| `contradictory_affiliation` | A Non-CCF answer also contains satellite information; Non-CCF takes precedence |

File summaries expose total, valid, invalid, duplicate, relationship-issue, and warning counts. Detailed issue rows retain severity, category, entity type, source row, non-profile source identifier, and a safe message.

## Cross-file reconciliation

The three exports are linked as follows:

```text
buyers.Buyer Reference Number
  ← tickets.Buyer Reference Number

tickets.Ticket Code
  ← registrants.Ticket Code
```

Missing relationships are reported as warnings rather than blocking errors. During processing, each registrant receives:

- `ticket_matched = 1` when its ticket exists in Generated Tickets;
- `checked_in = 1` when that matched ticket has a nonblank check-in timestamp.

Dashboard totals include ticket-matched registrant rows. They are **registration records, not guaranteed unique people**. Names, email addresses, mobile numbers, and birth fields are not used to merge people. Two records with different registration/ticket identifiers are counted separately even if their names and birth data match.

## Batch lifecycle

Possible persisted states are:

| Status | Meaning |
|---|---|
| `validating` | Validation lifecycle state supported by the schema |
| `invalid` | Blocking validation errors were found |
| `validated` | Validation passed and the batch is eligible for processing |
| `processing` | Normalized records are being inserted |
| `active` | The batch currently drives the selected Event's dashboard |
| `failed` | Processing raised an exception |
| `superseded` | A newer batch became active for the same Event |

The database enforces at most one active batch per Event with a partial unique index.

## Import history queries

Import history is filtered, sorted, and paginated on the server. All queries require the selected `event_id`; neither search nor batch selection can return a batch from another Event.

| Parameter | Supported values | Default |
|---|---|---|
| `q` | Batch ID, source Event name/slug, or sanitized original filename | empty |
| `status` | `all` or a supported lifecycle status | `all` |
| `page` | Positive integer | `1` |
| `per_page` | `10`, `25`, or `50` | `10` |
| `sort` | `batch_id`, `created_at`, `activated_at`, or `status` | `created_at` |
| `direction` | `asc` or `desc` | `desc` |

Unsupported values fall back to the documented defaults. Page numbers are clamped to the available result set, and filter/sort parameters are retained in table sorting and pagination links.

## Processing and transaction safety

Only a batch with status `validated` can be processed. Processing:

1. Confirms that all three stored files exist and were valid.
2. Reads the staged CSV files again.
3. Changes the batch state to `processing`.
4. Inserts normalized buyer, ticket, and registrant rows.
5. Classifies affiliation and computes ticket/check-in flags.
6. Adds processing-time data-quality warnings.
7. Marks the Event's existing active batch `superseded`.
8. Marks the new batch `active` and records processing/activation timestamps.
9. Commits the complete transaction.

If any processing step fails, normalized changes are rolled back, the batch is marked `failed`, and the previous active batch is preserved.

## Persistence model

### `import_batches`

One record per complete three-file set. It stores Event ownership, source event slug/name, lifecycle status, timestamps, and an optional processing error message.

### `import_files`

One record for each required export in a batch. It stores the export type, sanitized upload filename, staged path, detected type, validation status, and summary counts. `(batch_id, export_type)` is unique.

### `validation_issues`

Stores validation and processing-time issues. Issues are deleted automatically if their parent batch is deleted.

### `buyers`, `tickets`, and `registrants`

Normalized, batch-scoped records used by analytics. Important constraints include:

- buyer reference unique per batch;
- ticket code unique per batch;
- registration code unique per batch;
- registrant ticket code unique per batch.

Registrant rows store first and last name for roster/drill-down views, profile-presence flags, demographic inputs, raw affiliation inputs, derived affiliation/satellite, and ticket/check-in flags. Email and mobile contents are not copied into normalized tables.

## UI states and behavior

The Imports page provides:

- three required upload cards;
- `Not uploaded`, `Uploaded`, and `Validating` client-side states;
- a Validate button enabled only after all three browser inputs contain files;
- a per-file validation summary;
- compact totals for errors, warnings, and relationship issues;
- a Process and Activate action only for `validated` batches;
- a disabled processing action for `invalid` batches;
- Event-scoped import history with batch, source Event, compact file/record totals, status, issues, and timestamps;
- case-insensitive search and supported-status filtering;
- sortable Batch ID, Created At, Activated At, and Status columns;
- server-side pagination with 10, 25, and 50 rows per page;
- distinct empty states for an Event with no batches and filters with no matching batches.

Client-side readiness is only a usability feature. The server independently requires all three uploads and revalidates every file.

## Privacy and security boundaries

- Raw uploaded files remain in the staging directory and may contain personal information.
- `instance/` is excluded from version control.
- Route exception logs intentionally avoid logging CSV contents.
- Validation issue messages use source identifiers rather than names, email addresses, or mobile numbers.
- Normalized registrants retain names but not email/mobile values.
- The Flask routes shown here do not implement module-level authentication, authorization roles, or CSRF tokens. Deployment must restrict dashboard access appropriately before handling production personal data.
- Staged-file retention and batch deletion/cleanup are not currently automated.

## Configuration

| Setting | Default |
|---|---|
| `DATABASE` | `instance/ccf_dashboard.sqlite3` |
| `STAGING_DIR` | `instance/staged_imports` |
| `MAX_CONTENT_LENGTH` | 32 MB per HTTP request |

## Command-line import

`scripts/import_provided.py` runs the same `validate_batch`, `store_validation`, and `process_batch` functions for the three project CSV fixtures. It creates or reuses an Event based on the detected source event name and prints JSON summary metrics after successful activation.

Run it with:

```sh
.venv/bin/python scripts/import_provided.py
```

## Verification

Relevant automated coverage includes:

- all three uploads remaining mandatory;
- correct export-type detection independent of filename;
- blocking duplicate primary identifiers;
- warning-only duplicate ticket control numbers;
- standard CCF and B1G registrant header variants;
- B1G affiliation classification and raw-field preservation;
- Event-scoped batch history and cross-Event `404` behavior;
- one active batch per Event;
- superseding only the selected Event's previous batch;
- preserving active datasets when processing fails;
- migrations/backfills for existing databases;
- validation and processing of the supplied full dataset.
- import-history status/search filtering, sorting, page-size selection, pagination, query persistence, and empty-filter states;
- privacy checks ensuring Event Imports does not render registrant names, email addresses, or mobile numbers.

Run the suite with:

```sh
.venv/bin/python -m unittest discover -s tests -v
```
