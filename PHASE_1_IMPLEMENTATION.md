# CCF Event Dashboard — Phase 1 Implementation

> Historical implementation record: SQLite-specific sections below describe the
> original MVP. The current runtime uses SQLAlchemy, MySQL, and Alembic; see
> `README.md` and `CURRENT_DATABASE_STRUCTURE.md` for current operations.

## Document Purpose

This document describes everything created for the Phase 1 CCF Event Dashboard MVP, including:

- Application architecture
- Project files and responsibilities
- Database schema
- CSV import and validation behavior
- Dataset integration
- Affiliation classification
- Dashboard metrics and pages
- Data-quality reporting
- Privacy and security decisions
- Automated tests
- Verified results from the provided CSV exports
- Local setup and operation
- Known limitations and intentionally deferred work

Phase 1 is intentionally focused on reliable three-file imports, registrant and check-in metrics, church-affiliation analytics, satellite analytics, basic data-quality reporting, and event-scoped workspaces.

> **Event-management extension:** The application now supports multiple user-created Events. Each Event owns its import history, may have one active batch, and has isolated Overview, Satellite, Data Quality, and Imports pages. The event-scoped behavior described below supersedes older references in this document to a single global active batch.

---

## 1. Implemented Architecture

### Technology Stack

- **Backend and web framework:** Python 3.9+ and Flask 3.1
- **Database:** SQLite
- **Templating:** Jinja templates
- **Frontend:** Server-rendered HTML, custom responsive CSS, and minimal vanilla JavaScript
- **CSV processing:** Python standard-library `csv` module
- **Validation:** Application domain services with server-side checks
- **Testing:** Python standard-library `unittest`

The earlier proposal recommended Next.js and PostgreSQL for a larger production system. The implementation uses Flask and SQLite because the project began empty and the available environment did not contain Node.js. This keeps the Phase 1 MVP small and locally runnable while preserving service boundaries that can later be migrated to PostgreSQL or another frontend stack.

### Main Application Layers

```text
Browser
  │
  ▼
Flask routes and Jinja pages
  │
  ├── CSV Importer and Validator
  ├── Data Integration
  ├── Affiliation Classifier
  ├── Dashboard Aggregation
  └── Data-Quality Aggregation
          │
          ▼
        SQLite
```

The implementation separates import logic, classification, persistence, aggregation, routes, templates, and presentation styling rather than putting all behavior into route handlers.

---

## 2. Project Structure

```text
ccf-systems-dashboard/
├── app/
│   ├── __init__.py
│   ├── aggregation.py
│   ├── classifier.py
│   ├── db.py
│   ├── importer.py
│   ├── routes.py
│   ├── static/
│   │   └── app.css
│   └── templates/
│       ├── _empty.html
│       ├── _icons.html
│       ├── base.html
│       ├── data_quality.html
│       ├── event_new.html
│       ├── events.html
│       ├── imports.html
│       ├── overview.html
│       └── satellites.html
├── scripts/
│   └── import_provided.py
├── tests/
│   └── test_phase1.py
├── instance/
│   ├── ccf_dashboard.sqlite3
│   └── staged_imports/
├── .gitignore
├── CSV_ANALYSIS_AND_DASHBOARD_ARCHITECTURE.md
├── PHASE_1_IMPLEMENTATION.md
├── README.md
├── requirements.txt
└── run.py
```

The `instance/` directory and `.venv/` are excluded from version control because they contain runtime data, staged uploads, and environment-specific dependencies.

---

## 3. Files Created

### `run.py`

The local application entry point.

Responsibilities:

- Creates the Flask application.
- Runs it on `127.0.0.1`.
- Uses port `5050` by default.
- Supports a configurable port through `CCF_DASHBOARD_PORT`.
- Keeps debug mode disabled by default.
- Allows explicit debug mode through `CCF_DASHBOARD_DEBUG=1`.

Port 5050 is used because macOS AirPlay Receiver commonly reserves port 5000. On the development machine, macOS `ControlCenter` was confirmed to be listening on port 5000 and returning the reported HTTP 403 response.

### `requirements.txt`

Pins the application framework dependency:

```text
Flask==3.1.2
```

Flask installs its required dependencies, including Werkzeug, Jinja, Click, ItsDangerous, and MarkupSafe.

### `app/__init__.py`

Contains the Flask application factory.

Responsibilities:

- Creates the Flask application.
- Defines the SQLite database location.
- Defines the staged-import directory.
- Sets the maximum upload request size to 32 MB.
- Creates required runtime directories.
- Initializes the database schema.
- Registers the dashboard routes.
- Supports test-specific configuration.

Configuration values:

- `DATABASE`: defaults to `instance/ccf_dashboard.sqlite3`
- `STAGING_DIR`: defaults to `instance/staged_imports`
- `MAX_CONTENT_LENGTH`: 32 MB
- `SECRET_KEY`: can be set with `CCF_DASHBOARD_SECRET`

### `app/db.py`

Defines SQLite connectivity and the complete Phase 1 schema.

Responsibilities:

- Opens one database connection per Flask application context.
- Enables SQLite foreign-key enforcement.
- Creates tables and indexes when the application starts.
- Closes database connections after requests.
- Runs an idempotent migration that creates `events`, adds and backfills `import_batches.event_id`, and preserves legacy batch children.
- Enforces at most one active import batch per Event with a partial unique index.

### `app/classifier.py`

Implements the approved affiliation-classification rules.

Responsibilities:

- Normalizes surrounding whitespace without losing raw source values.
- Classifies registrants into exactly one of five approved categories.
- Preserves the selected satellite name.
- Detects contradictory Non-CCF/satellite answers.
- Detects incomplete CCF satellite details.

Classification categories:

1. `CCF Main`
2. `Local Satellite`
3. `International Satellite`
4. `Non-CCF`
5. `Unknown`

### `app/importer.py`

Implements CSV staging, type detection, file validation, relationship validation, persistence, data integration, and atomic activation.

Major responsibilities:

- Stores uploaded files in a unique staged-import directory.
- Reads UTF-8 CSVs with BOM support.
- Detects export types from header signatures rather than filenames.
- Validates required columns and identifiers.
- Detects duplicate identifiers.
- Validates check-in timestamps and buyer quantities.
- Checks event consistency across all three files.
- Validates cross-file relationships.
- Stores import summaries and validation issues.
- Inserts normalized buyer, ticket, and registrant records.
- Applies affiliation classification during processing.
- Marks checked-in registrants using the generated-ticket check-in timestamp.
- Generates data-quality issues.
- Activates a batch only after all processing completes successfully.
- Preserves the previous active batch when processing fails.

### `app/aggregation.py`

Provides SQL-based dashboard aggregations.

Responsibilities:

- Finds the active import batch.
- Calculates Overview metrics.
- Applies the Registrants/Checked-In metric basis.
- Calculates affiliation counts and percentages.
- Calculates satellite totals and attendance rates.
- Generates dynamic satellite rankings.
- Aggregates data-quality categories.
- Returns only a small number of non-personal sample identifiers per issue group.

The data-quality query was optimized so thousands of identifiers are counted in SQLite but only five samples per issue type are sent to the browser.

### `app/routes.py`

Defines the application pages and import actions.

Routes:

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Redirect to Events |
| GET | `/events` | Event list and application landing page |
| GET | `/events/new` | Focused Event creation form |
| POST | `/events` | Create an Event from its name |
| GET | `/events/<event_id>` | Event Overview Dashboard |
| GET | `/events/<event_id>/satellites` | Event Satellite Analytics |
| GET | `/events/<event_id>/data-quality` | Event Data Quality |
| GET | `/events/<event_id>/imports` | Event upload, validation summary, and import history |
| POST | `/events/<event_id>/imports/validate` | Upload and validate one complete three-file set for an Event |
| POST | `/events/<event_id>/imports/<batch_id>/process` | Process and activate a validated Event batch |

The route layer does not log CSV row contents when failures occur.

### `app/templates/base.html`

Defines the shared application layout:

- CCF event-dashboard branding
- Responsive sidebar navigation
- Active-event indicator
- Flash notifications
- Main page header
- Shared page blocks

Navigation is limited to the approved Phase 1 pages:

- Application level: Events
- Event workspace: Overview, Satellites, Data Quality, Imports, and Back to Events

### `app/templates/events.html`

Implements the event-management landing page with a restrained teal header, Create Event action, active/import status, registrant and check-in summaries, attendance rate, last import, and Open Event action.

### `app/templates/event_new.html`

Provides the focused creation experience. The only requested value is Event Name.

### `app/templates/_icons.html`

Provides lightweight inline SVG line icons for the actual application navigation and primary actions without adding a frontend icon dependency.

### `app/templates/_empty.html`

Shared empty state displayed when there is no active dataset. It directs the user to import all three required exports.

### `app/templates/overview.html`

Implements the primary dashboard.

Includes:

- Registrants/Checked-In metric basis toggle
- Total Registrants card
- Checked-In Attendees card
- Attendance Rate card
- CCF Main card
- Satellite Churches card
- Non-CCF card
- Unknown card
- Affiliation distribution bar
- Count and percentage for all five affiliation categories

The Overview now renders Registrants and Checked-In affiliation panels side-by-side from two calls to the existing batch-scoped aggregation. The basis control remains as a comparison-focus selector: it emphasizes the chosen panel and places that panel first when the layout stacks, without changing formulas or hiding the other basis.

### `app/templates/satellites.html`

Implements Satellite Analytics.

Includes:

- Total Satellite Registrants
- Total Satellite Checked In
- Satellite Attendance Rate
- Local Satellite registrations
- International Satellite registrations
- All/Local/International filters
- Dynamic individual-satellite ranking
- Registrant count per satellite
- Checked-in count per satellite
- Attendance rate per satellite

CCF Main is excluded from the satellite ranking because it is a top-level classification.

No satellite-name list is hardcoded.

### `app/templates/data_quality.html`

Implements aggregate data-quality reporting.

Shows:

- Unknown church affiliation
- Incomplete registrant profiles
- Contradictory affiliation responses
- Registrants without matching tickets
- Tickets without matching registrants
- Buyers without matching generated tickets
- Duplicate identifiers
- Invalid CSV rows
- Additional validation issue groups when applicable

Only counts, messages, entity types, severity, and non-personal source-identifier samples are displayed. Names, email addresses, phone numbers, and other personal fields are not shown.

### `app/templates/imports.html`

Implements the required three-file import experience.

Upload slots:

1. Generated Tickets — Required
2. Buyers — Required
3. Registrants — Required

Client-visible slot states:

- Not uploaded
- Uploaded
- Validating
- Valid
- Invalid

The validation action stays disabled until all three slots contain a file.

The validation summary includes:

- Expected file type
- Filename
- Detected export type
- File status
- Total rows
- Valid rows
- Invalid rows
- Duplicate records
- Relationship issues
- Warnings

The process-and-activate action is available only for a fully validated batch.

The page also includes an import-history table with batch, event, status, creation time, and activation time.

### `app/static/app.css`

Provides the full responsive visual design without a third-party frontend framework.

Includes styles for:

- Fixed desktop sidebar and mobile navigation
- Event and status indicators
- Summary metric cards
- Metric-basis segmented controls
- Affiliation colors and distribution visualization
- Satellite and quality tables
- Upload slots and validation states
- Import history
- Data-quality cards and severity labels
- Empty states and notifications
- Desktop, tablet, and mobile layouts

The stylesheet uses local system fonts and makes no external font request.

### `scripts/import_provided.py`

Imports the three provided project CSVs from the command line.

Flow:

1. Verifies that all three provided files exist.
2. Runs the same type detection and validation used by the UI.
3. Stores the validation batch.
4. Blocks activation if validation fails.
5. Processes and activates the batch if valid.
6. Prints calculated Overview, checked-in affiliation, Satellite, and Data Quality results as JSON.

### `tests/test_phase1.py`

Contains six automated unit and integration tests covering:

- All five approved classification categories
- Non-CCF classification precedence
- Contradictory satellite information
- Export-type detection independent of filenames
- Complete three-file validation and processing
- Atomic activation
- Overview calculations
- Checked-In metric basis
- Dynamic satellite ranking
- Data-quality issue counts
- Rejection of the wrong export in an upload slot
- Non-blocking repeated `Control Number` warnings
- Rendering pages without an active dataset

### `.gitignore`

Excludes:

- `.venv/`
- `instance/`
- Python bytecode and cache directories
- `.DS_Store`

### `README.md`

Provides concise setup, run, import, and test instructions.

### `CSV_ANALYSIS_AND_DASHBOARD_ARCHITECTURE.md`

Contains the approved pre-implementation dataset analysis, relationship analysis, metric definitions, classification rules, proposed architecture, and initial implementation plan. It was updated to document the actual repeated `Control Number` finding.

---

## 4. Database Schema

### `import_batches`

Represents one complete event import set.

Important fields:

- `id`
- `event_slug`
- `event_name`
- `status`
- `created_at`
- `processed_at`
- `activated_at`
- `error_message`

Supported statuses:

- `validating`
- `invalid`
- `validated`
- `processing`
- `active`
- `failed`
- `superseded`

Each batch belongs to an Event through `event_id`. A partial unique index permits one active batch per Event while allowing different Events to remain active simultaneously.

### `events`

Represents a user-created dashboard Event:

- Internal ID
- Event Name
- Created At
- Updated At

The Event Name entered by the user is distinct from source `event_name` and `event_slug` values detected from CSV exports.

### `import_files`

Stores metadata and validation results for each required export in a batch.

Important fields:

- Batch relationship
- Export type
- Original filename
- Staged path
- Status
- Total, valid, and invalid row counts
- Duplicate count
- Relationship-issue count
- Warning count
- Detected type

The database enforces one file per export type per batch.

### `validation_issues`

Stores validation, relationship, and data-quality issues without storing personal profile contents in issue messages.

Important fields:

- Batch
- Severity
- Category
- Entity type
- Source row
- Non-personal source identifier
- Message

### `buyers`

Stores the Phase 1 buyer/transaction fields required for relationships and validation:

- Batch
- Source ID
- Event slug
- Buyer Reference Number
- Payment status
- Quantity

`Buyer Reference Number` is unique within a batch.

### `tickets`

Stores Phase 1 generated-ticket fields:

- Batch
- Source ID
- Event slug
- Ticket Code
- Control Number
- Buyer Reference Number
- Ticket status
- Payment status
- Check-in timestamp

`Ticket Code` is unique within a batch.

### `registrants`

Stores Phase 1 participant and derived analytics fields:

- Batch
- Source ID
- Event slug
- Registration Code
- Ticket Code
- Ticket status
- Presence flags for first name, last name, email, and mobile
- Raw CCF-attendance response
- Raw satellite-scope response
- Raw local satellite value
- Raw international satellite value
- Derived affiliation
- Derived satellite name
- Ticket-match flag
- Checked-in flag

Personal field contents are not needed for Phase 1 aggregate analytics, so the database stores profile-completeness flags rather than copying names, email addresses, or phone numbers into normalized dashboard tables.

Unique constraints are applied to registration code and ticket code within each batch.

---

## 5. Export-Type Detection

Filenames are not used to identify exports.

### Generated Tickets signature

Includes required headers such as:

- `Id`
- `Slug`
- `Event Name`
- `Ticket Code`
- `Control Number`
- `Ticket Status`
- `Payment Status`
- `Buyer Reference Number`
- `Check-in Date Time`

### Buyers signature

Includes required headers such as:

- `Id`
- `Slug`
- `Event Name`
- `Buyer Reference Number`
- `Payment Status`
- `Quantity`
- `Gross Amount`
- `Amount Paid`

### Registrants signature

Includes required headers such as:

- `ID`
- `Event Name`
- `Event Slug`
- `Registration Code`
- `Ticket Code`
- `Ticket Status`
- `Are You Attending Ccf`
- `Are You From A Local Or International Satellite`
- `Which Local Satellite`
- `Which International Satellite`

The export must match exactly one supported signature and must be supplied in the correct required upload slot.

---

## 6. Import and Validation Flow

```text
Select all three files
  → upload to unique staging directory
  → read CSV and validate headers
  → detect export types
  → validate required identifiers
  → detect duplicate identifiers
  → validate check-in timestamps and quantities
  → validate event consistency
  → validate cross-file relationships
  → save batch/file/issue summaries
  → display validation preview
  → user chooses Process and Activate
  → transactionally insert normalized records
  → classify affiliations
  → generate data-quality issues
  → mark the selected Event's previous active batch superseded
  → activate new batch
```

All three files are mandatory. A partial batch cannot be validated or activated.

### Blocking validation errors

Examples:

- Unreadable or malformed CSV
- Duplicate column headers
- Incorrect export type in a slot
- Missing required headers
- Missing primary identifiers
- Duplicate primary identifiers
- Invalid check-in timestamp
- Invalid buyer quantity
- Event slug/name mismatch across exports

### Non-blocking warnings

Examples:

- Buyers without generated tickets
- Registrants without matching tickets
- Tickets with an unmatched populated buyer reference
- Repeated non-primary Control Numbers

Non-blocking records are preserved so relationship and quality problems remain visible.

### Atomic activation

Processing occurs inside a database transaction. The new batch becomes active only after all inserts, classifications, and quality checks succeed.

If processing fails:

- The transaction is rolled back.
- The batch is marked failed.
- The selected Event's previous valid active dataset remains active.
- Other Events and their active batches are never modified.

---

## 7. Data Integration

### Buyers to Tickets

Relationship key:

```text
Buyer Reference Number
```

Relationship:

```text
one buyer transaction → zero or many generated tickets
```

Unmatched buyers and tickets are preserved.

### Tickets to Registrants

Relationship key:

```text
Ticket Code
```

Relationship:

```text
one generated ticket → zero or one registrant
```

`Registration Code` is not used to connect buyers or tickets.

### Registrant metric eligibility

A Phase 1 Registrant metric includes a registrant-export row whose `Ticket Code` matches a generated ticket in the same batch. Unmatched registrant rows are retained for Data Quality but excluded from dashboard registrant metrics because the approved definition requires a ticket-linked record.

---

## 8. Affiliation Classification Rules

Rules are applied in approved precedence order.

### 1. Non-CCF

If normalized `Are You Attending Ccf` equals `No`:

- Classification: `Non-CCF`
- Satellite name: none
- Any populated satellite fields produce a contradiction warning.

This rule takes precedence over satellite values.

### 2. Unknown attendance response

If `Are You Attending Ccf` is blank or is not a recognized `Yes`/`No` value:

- Classification: `Unknown`

### 3. CCF Main

If:

- CCF attendance is `Yes`
- Scope is `Local Satellite`
- Local satellite, normalized case-insensitively, is `CCF Main`

Then:

- Classification: `CCF Main`
- Actual raw satellite name is preserved.

### 4. Local Satellite

If:

- CCF attendance is `Yes`
- Scope is `Local Satellite`
- A local satellite is populated
- The satellite is not CCF Main

Then:

- Classification: `Local Satellite`
- Satellite name comes dynamically from the imported value.

### 5. International Satellite

If:

- CCF attendance is `Yes`
- Scope is `International Satellite`
- An international satellite is populated

Then:

- Classification: `International Satellite`
- Satellite name comes dynamically from the imported value.

### Invalid or incomplete CCF details

A `Yes` response with missing or invalid scope/name information is classified as `Unknown` and flagged for future data-quality improvement.

No individual satellite list is hardcoded.

---

## 9. Metric Definitions

### Registrant

A registrant-export row linked to a generated ticket through `Ticket Code`.

### Checked-In Attendee

A ticket-linked registrant whose matching generated ticket has a valid, populated `Check-in Date Time`.

### Attendance Rate

```text
Checked-In Attendees ÷ Registrants × 100
```

### Satellite Churches

Combined count of:

- Local Satellites excluding CCF Main
- International Satellites

### Unique People

Not implemented or displayed because the current data does not provide a reliable permanent person identifier.

---

## 10. Overview Dashboard

The Overview page is the primary Phase 1 screen.

### Fixed event summary cards

- Total Registrants
- Checked-In Attendees
- Attendance Rate

### Metric-basis affiliation cards

- CCF Main
- Satellite Churches
- Non-CCF
- Unknown

### Metric Basis Toggle

Values:

- `Registrants`
- `Checked In`

When Registrants is selected, affiliation counts and percentages use all ticket-linked registrants.

When Checked In is selected, affiliation counts and percentages use only checked-in, ticket-linked registrants.

### Affiliation visualization

Shows all five categories:

- CCF Main
- Local Satellite
- International Satellite
- Non-CCF
- Unknown

For each category, the page displays:

- Count
- Percentage of the selected metric basis

Unknown values are always visible.

---

## 11. Satellite Analytics

Summary metrics:

- Total Satellite Registrants
- Total Satellite Checked In
- Satellite Attendance Rate
- Local Satellite Registrants
- International Satellite Registrants

Filters:

- All Satellites
- Local
- International

Ranking columns:

- Rank
- Satellite name
- Local/International scope
- Registrants
- Checked In
- Attendance Rate

Satellite names are grouped from actual imported values. CCF Main is excluded from the satellite ranking.

---

## 12. Data Quality

Phase 1 reports these required categories:

- Unknown church affiliation
- Incomplete registrant profiles
- Contradictory CCF/satellite answers
- Registrants without matching tickets
- Tickets without matching registrants
- Buyers without matching generated tickets
- Duplicate identifiers
- Invalid import rows

### Incomplete profile rule

A registrant profile is counted as incomplete when all of these are missing:

- First name
- Last name
- Email address
- Mobile number

The normalized database stores presence flags for these fields rather than their personal values.

### Investigation details

The issue register shows:

- Issue category
- Entity type
- Severity
- Count
- Generic issue message
- Up to five non-personal source identifiers

---

## 13. Verified Supplied-Data Results

The following files were successfully validated, processed, and activated:

- `Aug20_26_0426PM_event_generated_tickets.csv`
- `Aug20_26_0427PM_event_buyers.csv`
- `Aug20_26_0432PM_event_registrants.csv`

Stored entities:

| Entity | Rows |
|---|---:|
| Buyers | 3,228 |
| Generated Tickets | 8,000 |
| Registrants | 4,334 |

### Overview metrics

| Metric | Result |
|---|---:|
| Total Registrants | 4,334 |
| Checked-In Attendees | 3,869 |
| Attendance Rate | 89.27% |
| CCF Main | 1,280 |
| Local Satellites | 1,498 |
| International Satellites | 8 |
| All Satellite Churches | 1,506 |
| Non-CCF | 440 |
| Unknown | 1,108 |

### Affiliation percentages among registrants

| Classification | Count | Percentage |
|---|---:|---:|
| CCF Main | 1,280 | 29.53% |
| Local Satellite | 1,498 | 34.56% |
| International Satellite | 8 | 0.18% |
| Non-CCF | 440 | 10.15% |
| Unknown | 1,108 | 25.57% |

### Checked-in affiliation

| Classification | Checked In |
|---|---:|
| CCF Main | 1,232 |
| Local Satellite | 1,461 |
| International Satellite | 8 |
| Non-CCF | 420 |
| Unknown | 748 |
| Total | 3,869 |

### Satellite metrics

| Metric | Result |
|---|---:|
| Satellite Registrants | 1,506 |
| Satellite Checked In | 1,469 |
| Satellite Attendance Rate | 97.54% |
| Local Satellite Registrants | 1,498 |
| International Satellite Registrants | 8 |

### Data-quality results

| Issue | Count |
|---|---:|
| Unknown affiliation | 1,108 |
| Incomplete profiles | 1,106 |
| Contradictory affiliation answers | 2 |
| Registrants without matching tickets | 0 |
| Tickets without matching registrants | 3,666 |
| Buyers without matching generated tickets | 700 |
| Duplicate non-primary identifiers | 3,200 |
| Invalid CSV rows | 0 |

All approved metric and classification results matched the prior dataset analysis.

---

## 14. Control Number Finding

During implementation validation, `Control Number` was found not to be globally unique in the generated-ticket export:

- Generated tickets: 8,000
- Distinct Control Numbers: 4,800
- Later repeated Control Number occurrences: 3,200
- Distinct Ticket Codes: 8,000
- Distinct ticket IDs: 8,000

This does not affect dataset integration because `Ticket Code`, not `Control Number`, is the approved ticket-to-registrant relationship.

Implementation behavior:

- Duplicate ticket `Id` is blocking.
- Duplicate `Ticket Code` is blocking.
- Repeated `Control Number` is preserved and reported as a non-blocking data-quality warning.

No metric definition or affiliation rule was changed.

---

## 15. Privacy and Security Decisions

Implemented Phase 1 safeguards:

- Uploaded CSVs are validated server-side.
- All three files are required before processing.
- Dashboard pages display aggregate analytics.
- Names, email addresses, and phone numbers are not shown on dashboards.
- Normalized registrants store profile-field presence flags rather than personal field contents.
- CSV row contents are not written to application logs.
- Validation messages use generic descriptions.
- Data-quality samples use source identifiers rather than profile fields.
- Upload size is limited to 32 MB per request.
- Runtime data and staged uploads are excluded from version control.
- The server binds only to `127.0.0.1` by default.
- Flask debug mode is disabled by default.

Authentication and role-based authorization remain intentionally deferred, but the route/service structure permits adding them later.

---

## 16. Automated Verification

Run the complete test suite:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Current result:

```text
Ran 6 tests
OK
```

Additional verification performed:

- Compiled all application, script, and test modules successfully.
- Rendered all main routes successfully.
- Verified Overview in both metric bases.
- Verified Satellite local/international filtering.
- Verified Data Quality aggregation.
- Verified Imports and batch detail rendering.
- Ran SQLite integrity checking successfully: `ok`.
- Started the local server on port 5050.
- Confirmed the Overview route returns HTTP 200.

---

## 17. Local Setup and Operation

### First-time setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### Start the application

```sh
.venv/bin/python run.py
```

Open:

```text
http://127.0.0.1:5050/
```

### Use another port

```sh
CCF_DASHBOARD_PORT=8000 .venv/bin/python run.py
```

### Enable local debugging explicitly

```sh
CCF_DASHBOARD_DEBUG=1 .venv/bin/python run.py
```

Debug mode should not be enabled in a shared or production environment.

### Import through the UI

1. Open **Imports**.
2. Select the Generated Tickets export.
3. Select the Buyers export.
4. Select the Registrants export.
5. Choose **Validate complete set**.
6. Review row counts, duplicates, relationship issues, and warnings.
7. If valid, choose **Process and activate batch**.
8. The Overview Dashboard will use the newly active batch.

### Import the supplied files from the command line

```sh
.venv/bin/python scripts/import_provided.py
```

### Run tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```

---

## 18. Port 5000 HTTP 403 Resolution

The initial URL `http://127.0.0.1:5000/` returned HTTP 403 because macOS `ControlCenter`, associated with AirPlay Receiver, was already listening on TCP port 5000.

The dashboard was not the process returning the 403.

Resolution:

- Changed the dashboard's default port from 5000 to 5050.
- Made the port configurable through `CCF_DASHBOARD_PORT`.
- Verified `http://127.0.0.1:5050/` returns HTTP 200 and the Overview page.

---

## 19. Intentionally Deferred Beyond Phase 1

The following were not implemented:

- Demographic analytics
- Gender dashboards
- Age analytics
- Life-stage analytics
- Occupation analytics
- Dgroup analytics
- Revenue dashboard
- Payment analytics dashboard
- Advanced report builder
- Exportable reports
- Advanced authentication and role management
- Complex historical comparisons
- Multi-event comparative analytics
- Advanced satellite alias/canonical-name management
- PostgreSQL deployment migration
- Dedicated production WSGI server and deployment configuration
- Background import workers

These remain Phase 2 or later concerns.

---

## 20. Current Phase 1 Status

Phase 1 is implemented and operational.

- The three provided CSV exports are loaded in the local SQLite database.
- The validated batch is active.
- All approved metrics match the previously analyzed values.
- All automated tests pass.
- SQLite integrity verification passes.
- The dashboard is configured for `http://127.0.0.1:5050/` by default.

---

## 21. Event Management and Visual Design Extension

### Event ownership

- `events.name` is the application-level name entered by the user.
- `import_batches.event_name` and `event_slug` remain source metadata detected from CSV exports.
- Every new batch is created with a required Event relationship.
- Dashboard aggregation first resolves the selected Event's active batch, then reuses the existing batch-scoped metric queries.
- Import history and validation previews reject attempts to access a batch through a different Event URL.

### Legacy data migration

The startup migration:

1. Creates `events` if needed.
2. Adds `event_id` to a legacy `import_batches` table if needed.
3. Groups legacy batches by detected source event slug/name.
4. Creates a sensible Event using the source Event Name.
5. Backfills every legacy batch without changing its ID or child records.
6. Adds event-scoped indexes, integrity triggers, and the one-active-batch-per-event constraint.

Before applying this migration to the project database, a consistent backup was created at:

```text
instance/backups/before-event-scope-20260820.sqlite3
```

The existing `B1G Converge 2025` active batch was migrated to Event ID 1. Buyers, tickets, registrants, issues, metrics, classifications, and active status were preserved.

The migration audit also found 3 orphan `import_files` rows and 3,200 orphan warning rows left by a previously deleted invalid development batch. These did not belong to the active dataset or any Event. They were removed after the backup was created. Both `PRAGMA integrity_check` and `PRAGMA foreign_key_check` now pass.

### Reference-inspired visual system

The UI was restyled using the supplied image as a visual-language reference:

- White, lightweight sidebar
- Circular teal CCF brand mark
- Pale-teal active navigation
- Inline SVG line icons
- `Avenir Next`/Inter/system font stack without external font downloads
- Teal, dark-teal, white, and very-light-teal palette
- Restrained teal gradient on the Event Management header only
- White analytical cards with soft borders, rounded corners, and subtle shadows
- Airier tables and status badges
- Responsive desktop, tablet, and mobile layouts

No login, marketing, mission, resource, help, or other nonfunctional reference-image content was added.

### Event routes

```text
/events
/events/new
/events/<event_id>
/events/<event_id>/satellites
/events/<event_id>/data-quality
/events/<event_id>/imports
```

The root URL redirects to `/events`. Legacy global workspace URLs redirect to Events because there is no longer a meaningful global dataset context.
