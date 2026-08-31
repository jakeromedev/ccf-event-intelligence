# Registrations Module — Three-Phase Implementation Plan

## Status summary

| Phase | Status | Scope |
|---|---|---|
| Phase 1 | **Complete** | Read-only, Event-scoped Registrations table foundation |
| Phase 2 | **Complete** | Application-owned attestation verification workflow |
| Phase 3 | **Ready for Acceptance** | Operational polish, governance review, and acceptance |

Phase 1 and Phase 2 were implemented and verified on 2026-08-30. Phase 3 local
engineering and scripted acceptance are complete; hosted CI and manual
target-browser/product-owner acceptance remain external evidence. Phase 2 adds
current attestation state and reviewer attribution without changing imported
registration or attachment data.

## Module boundaries

Registrations is a focused operational module built from immutable imported
registrations. It is not an alias of Admin Tables and does not use curated
people as rows.

```text
Registrations
  -> one row per registrants record
  -> focused contact and logistics fields
  -> batch-scoped tickets relationship for Payment Status

Admin Tables
  -> complete source inspection and curated-source lineage
```

The imported `registrants`, `tickets`, `buyers`, and `source_data_json` values
remain immutable throughout all phases.

---

# Phase 1 — Registrations Table Foundation

Status: **Complete**

## Verified implementation checklist

### Navigation and authorization

- [x] Add Registrations as a separate top-level Event sidebar item.
- [x] Reuse the existing sidebar visual language and add a registration/list icon.
- [x] Show the navigation item only to authorized users.
- [x] Apply an active navigation state on the page and data endpoint.
- [x] Protect page and data routes independently of navigation visibility.
- [x] Keep PII-bearing Registrations access behind an explicit operational
  capability (administrator initially; approved `registration` role added on
  2026-08-30 without granting standard-user access).

Implementation:

- access decision: `app.routes.can_access_registrations`
- route decorator: `app.routes.registrations_access_required`
- navigation: `app/templates/base.html`
- approved standard users receive HTTP 403 on direct page and data requests;
- approved Registration operators receive page/data access under the
  deny-by-default role policy

### Row, Event, and batch scope

- [x] Use `registrants` as the base table.
- [x] Represent every imported registration separately without curation/deduplication.
- [x] Begin every query from an explicit Event.
- [x] Use the selected Event's active batch by default.
- [x] Reuse the established `active`, explicit historical batch, and `all` selector.
- [x] Validate explicit batch ownership server-side.
- [x] Reject cross-Event batch manipulation.
- [x] Preserve Event scope when `batch=all` is intentionally selected.

Implementation reuses `resolve_batch_scope` and `event_batches` from the Admin
Tables query layer. The page rejects an invalid scope with HTTP 404; the JSON
data endpoint returns HTTP 400 with a minimal validation message.

### Data composition

- [x] Use normalized `registrants` fields where they exist.
- [x] Read source-only contact/logistics/attestation values from immutable `source_data_json`.
- [x] Use normalized/final `registrants.satellite_name` without another classifier.
- [x] Resolve Payment Status with a batch-scoped Generated Ticket relationship.
- [x] Keep a registration visible when its ticket relationship is missing.
- [x] Exclude buyer monetary and other unnecessary sensitive fields.
- [x] Add no copied Registrations table and no migration.

The exact Payment Status relationship is:

```text
registrants.batch_id = tickets.batch_id
AND
registrants.ticket_code = tickets.ticket_code
```

It is a `LEFT JOIN`; missing tickets produce `payment_status = null`, rendered
as `—`. `buyers` is not required.

### Fixed table contract

- [x] Registration Code
- [x] Ticket Code
- [x] First Name
- [x] Last Name
- [x] Email Address
- [x] Mobile Number
- [x] Gender
- [x] Birth Month
- [x] Birth Year
- [x] Life Stage
- [x] Satellite
- [x] Shirt Size
- [x] Transportation To MMRC
- [x] Transportation From MMRC
- [x] Plate Number
- [x] Attestation Form
- [x] Payment Status

Column definitions and query composition live in `app/registrations.py`.
Complete source columns remain available only through Admin Tables.

### Attestation Form

- [x] Share server-side HTTP/HTTPS URL sanitization with Admin Tables.
- [x] Repeat protocol validation in the browser as defense in depth.
- [x] Render a concise **View Form** label.
- [x] Open valid links with `target="_blank"`.
- [x] Use `rel="noopener noreferrer"`.
- [x] Render blank, malformed, `javascript:`, `data:`, and `file:` values as `—`.
- [x] Build cell content through DOM properties without rendering source HTML.
- [x] Add no Attestation Status or editing behavior.

Shared server helper: `app.url_safety.safe_external_url`.

### Server-side query behavior

- [x] Search Registration Code, Ticket Code, First Name, Last Name, Email, and Mobile.
- [x] Filter Payment Status, Shirt Size, Gender, Satellite, Transportation To, and Transportation From.
- [x] Compose multiple validated filters.
- [x] Sort allow-listed Registration Code, Ticket Code, First Name, Last Name, Shirt Size, and Payment Status fields.
- [x] Fall back safely when an unavailable sort is requested.
- [x] Paginate with the established 25, 50, and 100 page-size options.
- [x] Preserve batch, search, filters, sort, direction, page, and page size in URL state.
- [x] Avoid loading the complete dataset into browser memory.

The data route is:

```text
GET /events/<event_id>/registrations/data
```

### Table UX and privacy

- [x] Provide grouped Registrant, Logistics, and Requirements headings.
- [x] Provide sticky headers, a sticky identifier column, and horizontal scrolling.
- [x] Provide loading, empty, error, filter-chip, page-size, and pagination states.
- [x] Give Attestation Form and Payment Status restrained operational emphasis.
- [x] Add no CSV/XLSX export.
- [x] Log no registration row contents.
- [x] Expose no medical, allergy, emergency-contact, full-address, or Dgroup-leader details.

## Phase 1 implementation evidence

Implementation date: **2026-08-30**

### Files created

- `app/registrations.py` — focused column/query service
- `app/url_safety.py` — shared imported external-URL allow-list
- `app/templates/registrations.html` — operational table page
- `app/static/registrations.js` — URL state, querying, rendering, filters, sorting, and pagination
- `tests/test_registrations.py` — Phase 1 coverage
- `docs/REGISTRATIONS_MODULE.md` — actual implementation reference

### Files modified

- `app/routes.py` — authorization decision plus page/data routes
- `app/__init__.py` — authorized sidebar context
- `app/templates/base.html` — sidebar item and active state
- `app/templates/_icons.html` — registration/list icon
- `app/static/app.css` — table grouping and requirement styles
- `app/admin_tables.py` — shared server-side attestation URL sanitization
- relevant documentation and documentation indexes

### Routes

```text
GET /events/<event_id>/registrations
GET /events/<event_id>/registrations/data
```

### Automated evidence

- Focused Registrations tests: **9 passed** on SQLite.
- Focused Registrations tests: **9 passed** as part of disposable MySQL validation.
- Complete SQLite suite: **91 passed**.
- Complete disposable MySQL suite: **91 passed** against local MySQL 8.4.
- Ruff: **passed** for the complete configured repository scope.
- Python compilation: **passed** for app, migrations, scripts, tests, and `run.py`.
- Fresh disposable MySQL migration: **passed**, `base -> a9d3c7e5f102`.
- `alembic current` and `alembic heads`: **a9d3c7e5f102 (head)**.
- `alembic check`: **passed**, no new upgrade operations detected.
- Production configuration/database/schema validation: **passed**.
- Local production-mode Gunicorn readiness: **passed**.
- Graceful Gunicorn SIGTERM shutdown: **passed**.
- Representative local MySQL query: **4,334 registrations, approximately 230.3 ms**.
- Hosted CI for this working-tree change: **not executed in this environment**.

### Phase 1 exit decision

All Phase 1 functional and locally executable verification criteria pass.
Phase 1 is **Complete**. No schema change or Alembic migration was required or
generated.

---

# Phase 2 — Attestation Verification Workflow

Status: **Complete**

## Goal

Add application-owned current attestation verification state without changing
the imported form URL, source JSON, source CSV, or legacy `AF Checking` data.

## State contract

Only these database/application values are permitted:

| Stored value | UI label |
|---|---|
| `pending` | Pending |
| `verified` | Verified |
| `invalid` | Invalid |

Default presentation when no verification row exists:

```text
Attestation Status: Pending
Last Reviewed By: —
Last Reviewed At: —
```

No user is attributed merely because the default state is Pending.

## Implemented migration contract

Alembic revision `b7e4c1a9d306` creates the finalized table:

```text
attestation_verifications
```

SQLAlchemy/Alembic fields:

| Field | Type/rule |
|---|---|
| `id` | existing unsigned BIGINT ID type, primary key, auto-increment |
| `registrant_id` | existing unsigned BIGINT ID type, required |
| `status` | `VARCHAR(16)`, required, server default `pending` |
| `updated_by_user_id` | existing unsigned BIGINT ID type, nullable |
| `created_at` | `DATETIME`, required, server-generated current timestamp |
| `updated_at` | `DATETIME`, required, server-generated/update timestamp managed by application update code |

Foreign keys and deletion behavior:

```text
registrant_id -> registrants.id ON DELETE CASCADE
updated_by_user_id -> users.id ON DELETE SET NULL
```

Constraints and indexes:

```text
UNIQUE(registrant_id)
CHECK(status IN ('pending', 'verified', 'invalid'))
INDEX(status)
INDEX(updated_by_user_id)
```

The unique registrant relationship stores one current state per immutable
source registration. Cascading a registrant deletion prevents orphaned state
when an eligible historical batch is deleted. Reviewer deletion must not erase
the decision; `SET NULL` retains state/time while displaying reviewer `—`.

MySQL/SQLite migration considerations:

- use the existing model ID type variants and `MYSQL_TABLE_OPTIONS`;
- use constraint/index names consistent with `app/models.py`;
- add the model after `Registrant` and `User` dependencies in schema metadata;
- validate upgrade on empty MySQL and SQLite test fixtures;
- test batch cascade behavior on both engines;
- do not use `db.create_all()` as deployment migration behavior;
- document downgrade data loss honestly if the table is dropped on downgrade.

No Phase 2 migration was generated during Phase 1. Revision
`b7e4c1a9d306` was created only after the separate Phase 2 instruction.

## Model and query integration

`AttestationVerification` is defined in `app/models.py`. The query in
`app/registrations.py` uses a `LEFT JOIN attestation_verifications` on
`record.id = verification.registrant_id` and derives:

```text
COALESCE(verification.status, 'pending')
reviewer username through users.id = verification.updated_by_user_id
verification.updated_at
```

The missing-row default must remain presentation/query behavior; it must not
eagerly create thousands of Pending rows.

## Audit contract

Every actual change must set on the server:

```text
updated_by_user_id = current_user.id
updated_at = server-generated current timestamp
```

The browser must not provide or override reviewer identity or timestamp. Phase
2 records the current last editor and edit time. It is not a complete historical
audit ledger; a separate history table would require another approved scope.

## Endpoint contract

Implemented route, aligned with the Phase 1 dashboard blueprint:

```text
PATCH /events/<int:event_id>/registrations/<int:registrant_id>/attestation
```

Request:

```json
{"status": "pending | verified | invalid"}
```

The request carries the current batch query context and a Flask-WTF CSRF
token using the supported request header/form mechanism.

Server checks, in order:

1. global authentication;
2. `registrations_access_required` authorization;
3. valid CSRF token;
4. selected Event exists;
5. requested batch resolves through `resolve_batch_scope`;
6. registrant exists and joins through its batch to the selected Event;
7. registrant belongs to the resolved batch scope;
8. status is exactly `pending`, `verified`, or `invalid`;
9. transactional insert-or-update succeeds.

Responses:

- `200` with `{batch_id, status, label, updated_by, updated_at}` after a successful update;
- `400` for malformed JSON, invalid status, or invalid batch input;
- `403` for an authenticated unauthorized user;
- `404` for an Event/registrant ownership mismatch;
- CSRF failure through the existing global error behavior.

The response must not serialize the Registrant model or unrelated PII.

## Implemented UI changes

The Requirements group uses this sequence:

```text
Attestation Form
Attestation Status
Last Reviewed By
Last Reviewed At
Payment Status
```

The compact inline dropdown permits only:

```text
Pending
Verified
Invalid
```

The update shows saving/failure state, retains the previous visible state on
failure, and does not bypass CSRF. Attestation Status uses the same server-side
filter model.

Scoped summary cards are derived from the same query definitions:

- Total Registrations
- Attestation Pending
- Attestation Verified
- Attestation Invalid
- Payment Validated

`Payment Validated` remains a source status count, not a monetary metric.

## Phase 2 verification contract

Test on both SQLite and disposable MySQL:

- absent verification row derives Pending with no reviewer/time;
- all transitions among Pending, Verified, and Invalid;
- arbitrary status rejection;
- authenticated reviewer attribution and server timestamp;
- repeated updates replace the current last-editor/time state; the application
  continues to enforce its single-administrator identity;
- unauthenticated, approved-standard-user, and direct-route denial;
- CSRF rejection for missing/invalid token;
- Event, batch, and registrant ownership manipulation rejection;
- historical registrations retain independent verification state;
- new-batch registrations do not inherit old-batch state;
- registrant/batch deletion cascades without orphans;
- summary and filtered counts reconcile;
- imported `registrants` and `source_data_json` remain unchanged;
- migration upgrade, downgrade limitation, and `alembic check` behavior.

## Phase 2 verified implementation checklist

- [x] Create Alembic migration for `attestation_verifications`.
- [x] Add `AttestationVerification` SQLAlchemy model.
- [x] Add model to schema dependency order.
- [x] Add unique/check constraints and indexes.
- [x] Add registrant cascade and reviewer `SET NULL` foreign keys.
- [x] Extend registration query composition with derived Pending state.
- [x] Join reviewer display through `users`.
- [x] Add Attestation Status, Last Reviewed By, and Last Reviewed At columns.
- [x] Add CSRF-protected PATCH endpoint.
- [x] Add status allow-list validation.
- [x] Add server-owned reviewer attribution and timestamp.
- [x] Add inline dropdown saving/error behavior.
- [x] Add Attestation Status filter.
- [x] Add scoped summary counts.
- [x] Add authorization and CSRF tests.
- [x] Add Event/batch/registrant isolation tests.
- [x] Add default-state and transition tests.
- [x] Add cascade/orphan tests.
- [x] Run SQLite and disposable MySQL suites.
- [x] Run empty-MySQL migration and `alembic check`.
- [x] Update `CURRENT_DATABASE_STRUCTURE.md` and `REGISTRATIONS_MODULE.md`.

## Phase 2 implementation evidence

Implementation date: **2026-08-30**

### Files added or changed

- `app/models.py` — `AttestationVerification` model and Registrant relationship
- `migrations/versions/b7e4c1a9d306_add_attestation_verifications.py`
- `app/registrations.py` — state composition, summaries, filtering, and updates
- `app/routes.py` — CSRF-protected PATCH route for administrator and
  Registration operators
- `app/templates/registrations.html` — summary and update contract
- `app/static/registrations.js` — inline update state and feedback
- `app/static/app.css` — state, summary, and feedback styling
- `app/observability.py` — safe `registrant_id` operational log field
- `tests/test_registrations.py` — Phase 1 and Phase 2 regression coverage
- Registrations, schema, and authentication documentation

### Verified behavior

- no verification row derives Pending with reviewer/time `—`;
- Pending, Verified, and Invalid are the only accepted application/database states;
- the authenticated administrator or Registration operator and server
  timestamp are recorded on updates;
- current state is inserted once and updated without duplicate rows;
- CSRF, operational-role authorization, Event ownership, batch ownership, and
  registrant ownership are enforced server-side;
- active and historical registration snapshots retain independent state;
- registration/batch deletion cascades verification rows;
- reviewer deletion retains state/time and sets reviewer ID to null;
- table/filter/summary results reconcile and source registration JSON remains unchanged;
- update responses and structured logs contain no registration PII or form URL.

### Automated evidence

- Focused Registrations suite: **14 passed** on SQLite.
- Focused Registrations suite: **14 passed** on disposable MySQL 8.4.
- Complete SQLite suite: **96 passed**.
- Complete disposable MySQL suite: **96 passed**.
- Empty MySQL migration: **base -> b7e4c1a9d306 passed**.
- MySQL downgrade to `a9d3c7e5f102` and re-upgrade: **passed**.
- SQLite revision upgrade/downgrade/re-upgrade from the prior head: **passed**.
- `alembic check`: **passed**, no new upgrade operations detected.
- Ruff and Python compilation: **passed** for the complete configured scope.
- Production configuration/database/schema validation: **passed**.
- Local production-mode Gunicorn readiness and graceful SIGTERM: **passed**.
- Representative supplied-data query: **4,334 registrations; median 465.7 ms
  over three local MySQL runs**.
- Hosted CI for this working-tree change: **not executed in this environment**.

The downgrade removes the current verification table and therefore loses its
data. Production rollback must preserve/restore that data when it is required;
the downgrade is not a substitute for a backup.

---

# Phase 3 — Operational Polish, Governance, and Acceptance

Status: **Ready for Acceptance**

Phase 3 engineering followed the implemented Phase 2 workflow without changing
its state, ownership, or source-immutability contracts.

## Verified work and remaining evidence

- [x] Exercise a scripted verification workflow with the administrator role.
- [x] Apply the approved deny-by-default Registration role: Dashboard and
  Registrations access plus attestation editing only; standard users remain denied.
- [x] Finalize All/Pending/Verified/Invalid quick filters using the existing server query path.
- [x] Confirm summary cards and table filters reconcile.
- [x] Document current attribution versus full-history limitations.
- [x] Review and document retention/deletion governance for verification metadata.
- [x] Re-measure query, filter, sort, update, and summary performance locally.
- [x] Review existing indexes against measured behavior; no additional index is justified.
- [x] Confirm no PII or attachment URLs appear in operational logs.
- [x] Confirm no CSV/XLSX route or public cache was introduced.
- [x] Run complete local SQLite/MySQL, migration, lint, compilation, and production gates.
- [ ] Execute hosted CI for the final pushed commit. **Blocked — External Execution.**
- [ ] Record manual target-browser/product-owner UAT. **Blocked — External Acceptance.**
- [x] Update final module, database, authentication, governance, and operational documentation.

## Phase 3 engineering evidence

Implementation date: **2026-08-30**

- Quick filters replace only Attestation Status while retaining other filters,
  Event/batch scope, pagination conventions, and URL state.
- Mixed-state reconciliation covers 25 Pending, 2 Verified, and 3 Invalid rows
  in a 30-registration fixture, including a combined Gender + status filter.
- Structured update logs were captured and verified to contain safe Event,
  batch, registrant, user, and status metadata without names, email addresses,
  attachment URLs, or source rows.
- Route inspection confirms no Registrations CSV/XLSX/download endpoint.
- Permission review grants view/edit to the administrator and Registration role
  only; standard-user Event/import mutation configuration does not grant
  Registrations access, and Registration cannot reach unrelated modules.
- Retention review confirms state follows registration/batch lifetime, reviewer
  deletion uses `SET NULL`, no automatic deletion exists, and organization owner
  and duration remain governance decisions.
- Current-state attribution is documented explicitly; complete history remains
  outside the approved module scope.
- Local supplied-data medians for 4,334 registrations were 439.5 ms unfiltered,
  443.9 ms with status filtering, and 443.1 ms with Payment Status sorting;
  every case included summary and option queries.
- Thirty disposable-MySQL state updates measured 0.86 ms median, 1.34 ms p95,
  and 2.77 ms maximum. These observations are not a production SLA.
- Focused Registrations suites: **19 passed** on SQLite and within disposable
  MySQL 8.4 validation after the Registration-role update.
- Complete suites: **104 passed** on SQLite and **104 passed** on disposable MySQL 8.4.
- Empty-MySQL migration and MySQL downgrade/re-upgrade to head
  `c8f5d2b0e417`: **passed**; `alembic check` found no schema operations.
- Ruff, Python compilation, JavaScript syntax, whitespace validation,
  production configuration, local Gunicorn readiness, and graceful SIGTERM:
  **passed**.
- Hosted CI and manual target-browser/product-owner UAT: **not executed**.

## External acceptance checklist

- [ ] Push the final reviewed commit.
- [ ] Confirm the hosted CI SQLite, MySQL, migration, production, and container jobs pass.
- [ ] Execute the administrator workflow in the target browser/environment.
- [ ] Confirm attachment opening, dropdown feedback, quick filters, summaries,
  responsive table behavior, and session timeout with the operational owner.
- [x] Record the approved Registration-role permission contract: Dashboard
  read-only, Registrations view/edit, and deny-by-default elsewhere.
- [ ] Record product-owner acceptance of current-state attribution and the
  remaining target-browser workflow, or document approved changes.

## Exit criteria

- verification behavior and authorization are accepted by the product owner;
- verification data cannot become orphaned through allowed batch deletion;
- summary/filter/table values reconcile;
- performance remains acceptable on representative data;
- privacy and logging review passes;
- complete SQLite and MySQL suites pass;
- migration validation and hosted CI pass;
- documentation matches the deployed behavior.

Phase 3 remains **Ready for Acceptance**, not Complete, until hosted CI and the
external acceptance checklist are evidenced. This is not an implementation
defect; unchecked external items are not marked complete without execution.

Phase 3 must remain a focused operational completion phase. It must not expand
Registrations into complete source inspection, reporting exports, or unrelated
analytics.
