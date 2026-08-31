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

- normal authenticated runtime: approved administrator or approved
  `registration` role;
- approved standard user: denied with HTTP 403;
- unauthenticated request: redirected by the global authentication guard;
- authentication-disabled development/test mode: read access is allowed for
  the established local workflow, but verification updates are disabled because
  an authenticated reviewer is required.

The Registration role is deny-by-default at the global endpoint guard. It may
view the Dashboard and Registrations and may edit only the application-owned
attestation state. It cannot access Analytics, Data Quality, Admin Tables,
imports/batches, Event or Satellite Dataset settings, or user administration.
Standard users can do neither Registrations action. The PATCH endpoint requires
an attributable administrator or Registration operator even when read-only
local access is enabled, and global Flask-WTF CSRF validation remains mandatory.

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
| Attestation & Payment | Attestation Form | `source_data_json["Upload Your Accomplished Attestation Form Here"]` |
| Attestation & Payment | Attestation Status | `COALESCE(attestation_verifications.status, 'pending')` |
| Attestation & Payment | Payment Status | `tickets.payment_status` through the batch/ticket-code relationship |
| Registrant Details | First Name | `registrants.first_name` |
| Registrant Details | Last Name | `registrants.last_name` |
| Registrant Details | Email Address | `registrants.source_data_json["Email Address"]` |
| Registrant Details | Mobile Number | `registrants.source_data_json["Mobile Number"]` |
| Registrant Details | Gender | `registrants.gender_raw` |
| Registrant Details | Birth Month | `registrants.birth_month_raw` |
| Registrant Details | Birth Year | `registrants.birth_year_raw` |
| Registrant Details | Life Stage | `registrants.life_stage_raw` |
| Registrant Details | Satellite | normalized/final `registrants.satellite_name` |
| Logistics | Shirt Size | `source_data_json["Shirt Size"]` |
| Logistics | Transportation To MMRC | `source_data_json["Transportation From Ccf To Mmrc"]` with supported header fallback |
| Logistics | Transportation From MMRC | `source_data_json["Transportation From Mmrc To Ccf"]` with supported header fallback |
| Logistics | Plate Number | `source_data_json["Plate No"]` with `Plate Number` fallback |
| Attestation & Payment | Last Reviewed By | `users.username` through `updated_by_user_id` |
| Attestation & Payment | Last Reviewed At | `attestation_verifications.updated_at` |

Registration Code and Ticket Code remain searchable query fields but are not
part of the displayed column contract and have no table sorting controls.

The module does not expose medical information, allergies, emergency contacts,
full residential addresses, Dgroup leader contacts, buyer monetary values, or
other complete-source fields.

## Attestation Form safety

`app.url_safety.safe_external_url` is shared by Registrations and Admin Tables.
It returns a value only when it is a complete HTTP or HTTPS URL. Blank,
malformed, control-character, `javascript:`, `data:`, and `file:` values become
the standard `—` state.

The browser repeats the protocol allow-list as defense in depth. The
Attestation Form button opens the in-page review modal immediately, paints a
loading state, and then requests the image asynchronously. Successful image
previews default to Fit to View and provide 25%–300% zoom, 100% natural size,
and document-only horizontal/vertical scrolling. Other file types receive a
preview-unavailable state. Only a validated URL can activate the optional
original-file link:

```text
label: Open Original
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
every imported registration. The Attestation Review modal shows the registrant,
Satellite, Payment Status, submitted form, and current state. An administrator
or Registration operator can change the state in that modal; read-only viewers
receive the same preview without editing controls. The server, never the
browser, supplies `current_user.id` and the review timestamp.

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

Visible sorting controls are available for First Name, Last Name, Shirt Size,
Attestation Status, and Payment Status. Registration Code remains the internal
default order, and Registration Code and Ticket Code remain allow-listed for
the existing server query contract without being shown in the table. An
unavailable field falls back to the default; direction is limited to ascending
or descending. Record ID is the deterministic tie-breaker.

### Pagination and URL state

Page sizes are 25, 50, and 100, with 50 as the default. Counts, sorting,
filtering, and `LIMIT/OFFSET` pagination all execute on the server. Batch,
search, filters, sort, direction, page, and non-default page size are preserved
in query parameters.

## UI behavior

The table uses the existing design system and provides:

- fixed operational ordering beginning with Attestation Form, Attestation
  Status, and Payment Status;
- three persisted column-group controls for Attestation & Payment, Registrant
  Details, and Logistics, plus Reset to Default;
- sticky headers and the first operational-action column;
- horizontal and vertical scrolling;
- loading, empty, and failure states;
- filter chips and clear-all behavior;
- page-size and page navigation controls;
- emphasized but restrained Attestation Form and Payment Status treatments;
- an accessible Attestation Review modal with image loading/failure states,
  safe original-file access, focus trapping/restoration, and unsaved-change
  protection;
- modal-based Pending/Verified/Invalid status updates with saving and failure
  feedback;
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
| Registration-role page/data/edit access | Pass | Capability, CSRF, and reviewer-attribution tests |
| Registration-role restricted-module denial | Pass | Direct page/API/mutation requests return 403 |
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

- Focused Registrations suite: **19 passed** on SQLite and within disposable
  MySQL validation.
- Complete suite: **104 passed** on SQLite.
- Complete suite: **104 passed** on disposable MySQL 8.4.
- Empty MySQL migration, downgrade/re-upgrade, and `alembic check`: **passed**.
- Ruff, Python compilation, JavaScript syntax, and whitespace validation: **passed**.
- Production configuration/schema check: **passed**.

## Registration role implementation evidence

Implementation verified: **2026-08-31**

- Internal role value: `registration`; display label: **Registration**.
- Administrator assignment works during approval and through the protected
  role-update form; public registration remains `user/pending` and ignores any
  submitted role value.
- Centralized capabilities grant Dashboard read access, Registrations page/data
  access, and attestation verification editing only.
- Direct restricted page, API, import/batch, settings, source-lineage, and user
  administration requests return HTTP 403.
- Registration operator attestation updates retain CSRF, status allow-list,
  Event/batch/registrant ownership, server timestamp, and reviewer attribution.
- Alembic revision `c8f5d2b0e417` adds the role to database constraints; a
  downgrade converts Registration accounts to ordinary `user` accounts before
  restoring the former constraint.
- Fresh disposable-MySQL migration to `c8f5d2b0e417`, migration
  downgrade/re-upgrade, and `alembic check` passed.
- Ruff, compilation, production configuration/schema validation, Gunicorn
  readiness, and graceful SIGTERM passed. Hosted CI and container execution
  were not run locally.
- Local production-mode readiness and graceful SIGTERM: **passed**.
- Hosted CI and manual target-browser acceptance: **not executed**.

## Current limitations

The module has no export surface and does not provide complete verification
history. Organization-specific retention ownership/duration and any future
split reviewer permission remain explicit decisions. Local engineering is
ready for acceptance, but hosted CI and manual target-browser UAT must be
recorded before the three-phase plan can truthfully be marked Complete.
