# Registrations Module

Status: **Phase 3 engineering complete — ready for external acceptance**

## Purpose

Registrations is the focused operational view of imported registration
submissions. It is separate from aggregate dashboards and from Admin Tables:

- Registrations presents a fixed set of registration, personal, logistics, and
  requirement fields used in normal operations.
- Admin Tables remains the administrator-only complete-source inspection tool
  for Registrants, Generated Tickets, Buyers, and curated lineage.

Imported registration data remains read-only. Phase 2 adds a separate,
application-owned current attestation decision; it does not modify source JSON,
source CSV values, or the uploaded-form URL. The module provides no downloads.

## Navigation and routes

Registrations is a top-level Event-workspace sidebar item with its own active
state.

| Surface | Route | Method |
|---|---|---|
| Registrations page | `/events/<event_id>/registrations` | GET |
| Paginated registration data | `/events/<event_id>/registrations/data` | GET |
| Update current attestation state | `/events/<event_id>/registrations/<registrant_id>/attestation` | PATCH |

All routes independently apply `registrations_access_required`; sidebar
visibility is not an authorization control.

## Authorization

The table contains names, contact information, logistics responses, and
attachment links. It therefore uses the same restrictive role boundary as
detailed registration inspection:

- normal authenticated runtime: approved administrator only;
- approved standard user: denied with HTTP 403;
- unauthenticated request: redirected by the global authentication guard;
- authentication-disabled development/test mode: read access is allowed for
  the established local workflow, but verification updates are disabled because
  an authenticated reviewer is required.

Phase 2 does not introduce a new role or broaden Event-data permissions. The
PATCH endpoint requires an authenticated administrator even when read-only local
access is enabled, and global Flask-WTF CSRF validation remains mandatory.

The Phase 3 permission review preserves one deny-by-default operational role:
the administrator can both view and edit Registrations, while standard users
can do neither. A future dedicated reviewer/viewer permission remains a product
decision and is not inferred from Event/import mutation access.

## Row definition and scope

One row represents one immutable `registrants` record. Registrations does not
use `curated_registrants` and does not deduplicate people.

```text
Selected Event
  -> active import_batches row by default
      -> every registrants row in that batch
          -> optional batch-scoped Generated Ticket match
```

The existing Admin Tables batch convention is reused:

- omitted, blank, or `batch=active`: selected Event's active batch;
- `batch=<id>`: one historical batch after Event-ownership validation;
- `batch=all`: all batches belonging to the selected Event only.

A batch ID owned by another Event is rejected. If the selected Event has no
active batch, active scope returns an empty result rather than another Event's
data.

## Data sources and relationships

```text
registrants record
  |-- normalized registration/person/satellite fields
  |-- immutable source_data_json logistics/contact/attestation values
  `-- (batch_id, ticket_code)
          LEFT JOIN tickets (batch_id, ticket_code)
              `-- payment_status
  `-- id
          LEFT JOIN attestation_verifications.registrant_id
              |-- current verification status
              |-- reviewed timestamp
              `-- users.id reviewer username
```

`buyers` is not needed for Phase 1. Payment Status comes directly from the
Generated Ticket row whose `batch_id` and `ticket_code` match the registration.
The left join deliberately retains a registration whose ticket is missing;
that row receives no Payment Status and displays `—`.

Names and email addresses are never used as relationship keys.

## Displayed columns

| Group | Display column | Source |
|---|---|---|
| Registrant | Registration Code | `registrants.registration_code` |
| Registrant | Ticket Code | `registrants.ticket_code` |
| Registrant | First Name | `registrants.first_name` |
| Registrant | Last Name | `registrants.last_name` |
| Registrant | Email Address | `registrants.source_data_json["Email Address"]` |
| Registrant | Mobile Number | `registrants.source_data_json["Mobile Number"]` |
| Registrant | Gender | `registrants.gender_raw` |
| Registrant | Birth Month | `registrants.birth_month_raw` |
| Registrant | Birth Year | `registrants.birth_year_raw` |
| Registrant | Life Stage | `registrants.life_stage_raw` |
| Registrant | Satellite | normalized/final `registrants.satellite_name` |
| Logistics | Shirt Size | `source_data_json["Shirt Size"]` |
| Logistics | Transportation To MMRC | `source_data_json["Transportation From Ccf To Mmrc"]` with supported header fallback |
| Logistics | Transportation From MMRC | `source_data_json["Transportation From Mmrc To Ccf"]` with supported header fallback |
| Logistics | Plate Number | `source_data_json["Plate No"]` with `Plate Number` fallback |
| Requirements | Attestation Form | `source_data_json["Upload Your Accomplished Attestation Form Here"]` |
| Requirements | Attestation Status | `COALESCE(attestation_verifications.status, 'pending')` |
| Requirements | Last Reviewed By | `users.username` through `updated_by_user_id` |
| Requirements | Last Reviewed At | `attestation_verifications.updated_at` |
| Requirements | Payment Status | `tickets.payment_status` through the batch/ticket-code relationship |

The module does not expose medical information, allergies, emergency contacts,
full residential addresses, Dgroup leader contacts, buyer monetary values, or
other complete-source fields.

## Attestation Form safety

`app.url_safety.safe_external_url` is shared by Registrations and Admin Tables.
It returns a value only when it is a complete HTTP or HTTPS URL. Blank,
malformed, control-character, `javascript:`, `data:`, and `file:` values become
the standard `—` state.

The browser repeats the protocol allow-list as defense in depth and creates the
link through DOM properties rather than source HTML:

```text
label: View Form
target: _blank
rel: noopener noreferrer
```

## Attestation verification

The application owns exactly three verification states:

| Stored value | UI label |
|---|---|
| `pending` | Pending |
| `verified` | Verified |
| `invalid` | Invalid |

No `attestation_verifications` row means **Pending** with reviewer and reviewed
time displayed as `—`. This derived default avoids materializing a row for
every imported registration. An administrator can change the state through the
inline dropdown. The server, never the browser, supplies `current_user.id` and
the review timestamp.

Updates validate the Event, selected active/historical batch, registration
ownership, and exact status allow-list before writing. The JSON response is
limited to status, label, reviewer, timestamp, and batch ID. Operational logs
contain safe IDs and status only—not names, contact fields, form URLs, or source
rows.

The table records current last-editor attribution and time. It is not a
complete historical audit ledger: later updates replace the prior current
state, reviewer, and timestamp.

## Query contract

`app/registrations.py` owns the fixed column definitions and query composition.
It reuses Admin Tables' allow-listed batch resolution, filter parsing, filter
clauses, categorical options, and pagination conventions.

Supported query parameters:

```text
batch, search (or q), filters, sort, direction, page, per_page
```

### Search

Search is performed in SQL across:

- Registration Code
- Ticket Code
- First Name
- Last Name
- Email Address
- Mobile Number

The search term is trimmed and limited to 200 characters.

### Filters

Composable, server-validated categorical filters are available for:

- Payment Status
- Shirt Size
- Gender
- Satellite
- Transportation To MMRC
- Transportation From MMRC
- Attestation Status (`Pending`, `Verified`, or `Invalid` choices always remain available)

Available filter values are queried within the selected Event and batch scope.
Requests cannot filter arbitrary source fields or SQL expressions.

The All, Pending, Verified, and Invalid quick-filter buttons use this same
server-side filter specification. They replace only the Attestation Status
filter, retain every other active filter and the Event/batch context, reset to
page one, and preserve the resulting state in the URL.

### Sorting

Allow-listed sorting is available for Registration Code, Ticket Code, First
Name, Last Name, Shirt Size, Attestation Status, and Payment Status. The default is Registration
Code ascending. An unavailable field falls back to the default; direction is
limited to ascending or descending. Record ID is the deterministic tie-breaker.

### Pagination and URL state

Page sizes are 25, 50, and 100, with 50 as the default. Counts, sorting,
filtering, and `LIMIT/OFFSET` pagination all execute on the server. Batch,
search, filters, sort, direction, page, and non-default page size are preserved
in query parameters.

## UI behavior

The table uses the existing design system and provides:

- grouped Registrant, Logistics, and Requirements headers;
- sticky headers and first identifier column;
- horizontal and vertical scrolling;
- loading, empty, and failure states;
- filter chips and clear-all behavior;
- page-size and page navigation controls;
- emphasized but restrained Attestation Form and Payment Status treatments;
- inline Pending/Verified/Invalid status updates with saving and failure feedback;
- Total Registrations, Attestation Pending, Attestation Verified, Attestation
  Invalid, and Payment Validated summary cards using the current server scope.

No row contents are written to application logs, exported, or cached in a
shared public cache.

## Retention and audit governance

Verification metadata is retained for the life of its imported registration.
Deleting an eligible batch cascades the associated current-state rows. Deleting
the reviewer retains status and timestamp while clearing reviewer ID. There is
no separate automatic cleanup schedule and no copy of the attachment contents
or URL in the verification table.

Organization-specific owner and retention duration remain governance decisions
in `OPERATIONS_AND_INCIDENT_RESPONSE.md`. Phase 3 does not invent a duration or
add automatic deletion. The implemented attribution remains current last editor
and time—not a historical audit ledger.

## Performance evidence

On 2026-08-30, Phase 3 repeated three local MySQL runs against 4,334 supplied
registrations. Median times were 439.5 ms unfiltered, 443.9 ms with Attestation
Status filtering, and 443.1 ms when sorting by Payment Status. Each path also
computed scoped summaries and bounded filter options. Thirty current-state
updates against disposable MySQL had a 0.86 ms median, 1.34 ms p95, and 2.77 ms
maximum in that local environment.

These are development-host observations, not an approved production SLA. The
existing unique registrant key and status/reviewer indexes support the measured
workflow; no additional index, per-row query, cache, worker, or background job
was justified.

## Phase 1 verification history

- 9 focused Registrations tests passed on SQLite and disposable MySQL.
- Complete suite: 91 SQLite tests passed.
- Complete suite: 91 disposable MySQL tests passed.
- Fresh MySQL Alembic upgrade reached `a9d3c7e5f102`; `alembic check` was clean.
- Ruff and Python compilation passed.
- Production configuration validation, Gunicorn readiness, and graceful
  SIGTERM shutdown passed against disposable MySQL.
- No model, schema, or migration was added.

The Phase 2 verification evidence and current suite counts are recorded in
`REGISTRATIONS_MODULE_3_PHASE_PLAN.md`.

Phase 2 added 14 focused tests within complete **96-test** SQLite and
disposable-MySQL suites. The empty MySQL migration, MySQL and SQLite revision
downgrade/re-upgrade rehearsals, `alembic check`, Ruff, compilation, production
configuration validation, Gunicorn readiness, and graceful shutdown passed.
Hosted CI was not executed from the local implementation environment.

## Phase 3 acceptance results

| Scenario | Local result | Evidence |
|---|---|---|
| Administrator page and data access | Pass | Direct route/navigation tests |
| Standard-user and unauthenticated denial | Pass | Page, data, and PATCH authorization tests |
| Default Pending presentation | Pass | Missing-row query and UI contract tests |
| Pending/Verified/Invalid transitions | Pass | CSRF-protected endpoint tests |
| Active and historical batch isolation | Pass | Independent-state and ownership tests |
| Quick filters and combined filters | Pass | Server reconciliation and UI contract tests |
| Summary reconciliation | Pass | Mixed-state 30-registration fixture |
| Reviewer attribution and timestamps | Pass | Database and response tests |
| Batch cleanup and reviewer deletion | Pass | Cascade and `SET NULL` tests |
| PII-safe operational logging | Pass | JSON-log capture and exclusion assertions |
| Export/cache absence | Pass | Route-map and implementation review |
| Manual target-browser UAT | Not executed | External acceptance required |
| Hosted CI | Not executed | Requires commit/push and hosted workflow |

Phase 3 local verification:

- Focused Registrations suite: **16 passed** on SQLite and disposable MySQL.
- Complete suite: **98 passed** on SQLite.
- Complete suite: **98 passed** on disposable MySQL 8.4.
- Empty MySQL migration, downgrade/re-upgrade, and `alembic check`: **passed**.
- Ruff, Python compilation, JavaScript syntax, and whitespace validation: **passed**.
- Production configuration/schema check: **passed**.
- Local production-mode readiness and graceful SIGTERM: **passed**.
- Hosted CI and manual target-browser acceptance: **not executed**.

## Current limitations

The module has no export surface and does not provide complete verification
history. Organization-specific retention ownership/duration and any future
split reviewer permission remain explicit decisions. Local engineering is
ready for acceptance, but hosted CI and manual target-browser UAT must be
recorded before the three-phase plan can truthfully be marked Complete.
