# CCF Systems Dashboard — Phase Checklists

This document is the project-level checklist for completed and proposed phases.
It summarizes implementation status without replacing the detailed contracts in
the module documentation.

## How to use this document

- `[x]` means the item is implemented and verified in the current codebase.
- `[ ]` means the item is outstanding, proposed, or requires approval.
- Items marked **Decision required** must be defined by the product owner before
  implementation begins.
- A phase is complete only when its exit criteria are satisfied, not merely when
  its individual features have been coded.
- Update the checklist in the same change that completes an item. Link the
  relevant tests, migrations, runbooks, or design decisions in the detailed
  documentation when appropriate.

## Current status

| Phase | Status | Purpose |
|---|---|---|
| Phase 1 | Complete | Event imports, curation, dashboard analytics, Data Quality, Admin Tables, and authentication |
| Phase 2 | Ready for Production Acceptance | Engineering and hosted release gates pass; product decisions and target-environment acceptance remain open |
| Phase 3 | In Progress | Advanced analytics, reporting, exports, and historical comparisons |
| Phase 4 | Future/conditional | Data remediation workflows, advanced import modes, and scale automation |

Phase 3 engineering is in progress, but its unresolved product decisions are
not approved schedules or delivery commitments. Phase 4 remains proposed and
conditional.

---

## Phase 1 — Core Event Intelligence MVP

### Event and import foundation

- [x] Create and manage multiple Events.
- [x] Isolate batches, dashboards, imports, and settings by Event.
- [x] Require Generated Tickets, Buyers, and Registrants exports for every batch.
- [x] Detect export types from header signatures rather than filenames.
- [x] Validate schemas, identifiers, relationships, and Event consistency.
- [x] Preserve raw source rows and import audit information.
- [x] Process and activate complete batches atomically.
- [x] Preserve the previous active dataset when processing fails.
- [x] Switch previously processed batches back to active status.
- [x] Restrict batch deletion to administrators and protect active/in-progress batches.
- [x] Remove retained staged files when their deletable batch is removed.
- [x] Manage schema changes through SQLAlchemy and Alembic on MySQL.

### Curation and analytical data

- [x] Build deterministic, batch-scoped unique-person curation.
- [x] Preserve complete raw-to-curated registrant traceability.
- [x] Keep incomplete identities separate from automatic duplicate merging.
- [x] Detect duplicate groups, registration-type conflicts, and multiple-satellite associations.
- [x] Normalize conservative satellite-name variations while retaining source spellings.
- [x] Rebuild derived curation safely for a batch or Event.

### Dashboard and satellite analytics

- [x] Report unique participants, unique volunteers, raw registrations, and check-ins.
- [x] Support Event Date and Participant Target settings.
- [x] Reconcile target progress and prevent negative remaining-slot values.
- [x] Report participant Gender, Life Stage, and event-date Age distributions.
- [x] Reconcile every demographic distribution to its eligible population.
- [x] Classify CCF Main, Local Satellite, International Satellite, Non-CCF, and Unknown.
- [x] Provide satellite totals, attendance rates, scope filters, search, sorting, and pagination.
- [x] Provide satellite registrant drill-downs.
- [x] Configure Event-owned Satellite Datasets with independent targets.
- [x] Preserve and recalculate Satellite Datasets when the active batch changes.
- [x] Provide aggregate dashboard JSON without exposing raw personal data.

### Data Quality and Admin Tables

- [x] Persist import, relationship, affiliation, and curation-quality findings.
- [x] Separate Import Quality and Curation Quality reporting.
- [x] Provide issue summary cards, grouped details, safe instance drill-downs, and pagination.
- [x] Provide independent ten-row pagination for Data Quality curation tables.
- [x] Provide administrator-only Registrants, Generated Tickets, Buyers, and Curated Registrants tables.
- [x] Preserve server-side Admin Table search, filters, sorting, pagination, and batch scoping.
- [x] Provide configurable column visibility with browser-local preferences.
- [x] Display valid attestation-form URLs as safe new-tab links and reject unsafe values.
- [x] Provide curated-source inspection without changing source records.

### Authentication and security baseline

- [x] Provide login, logout, registration, pending approval, and administrator approval.
- [x] Restrict application access to approved users.
- [x] Restrict Admin Tables, user approval, and batch deletion to the administrator.
- [x] Hash passwords with Argon2id.
- [x] Protect state-changing requests with CSRF validation.
- [x] Apply session hardening, login lockout, and safe redirect validation.
- [x] Keep credentials, staged files, databases, and source exports out of version control.

### Verification and Phase 1 exit criteria

- [x] Maintain isolated SQLite tests for normal development.
- [x] Support the same suite against a disposable MySQL test database.
- [x] Cover Event isolation, imports, curation, metrics, security, migrations, and Admin Tables.
- [x] Pass the complete automated test suite (71 tests at the current baseline).
- [x] Verify supplied-data reconciliation and migration safeguards.
- [x] Document local MySQL setup, Alembic migration, administrator initialization, and startup.
- [x] Phase 1 is operational on the local development environment.

### Phase 1 documentation closeout

- [x] Consolidate or clearly archive historical SQLite-only implementation sections.
- [x] Remove stale statements claiming authentication, demographics, satellite normalization,
  and batch cleanup are not implemented.
- [x] Align all module limitation sections with the current MySQL-backed implementation.

These documentation items do not reopen Phase 1 implementation. They are the
required preflight work for approving Phase 2.

---

## Phase 2 — Production Readiness and Governance

### Scope and ownership gate

- [ ] **Decision required:** Approve Phase 2 scope, owner, target environment, and release date.
- [ ] **Decision required:** Define expected users, traffic, import volume, uptime, and recovery objectives.
- [ ] **Decision required:** Decide whether approved standard users may modify Event settings and imports.
- [x] Define documented production acceptance criteria.
- [ ] **Decision required:** Assign the accountable final production release approver.

### Deployment and runtime

- [x] Select and configure the Gunicorn production WSGI server.
- [x] Add a production OCI container definition with health check and non-root runtime.
- [x] Configure explicit trusted reverse-proxy handling for external HTTPS termination.
- [x] Require and automatically test secure production session-cookie behavior.
- [x] Separate development, testing, staging, and production configuration.
- [x] Add deployment, rollback, and schema-migration runbooks.
- [x] Verify local MySQL production-mode Gunicorn startup, readiness, and graceful `SIGTERM` shutdown.
- [x] Complete and record a disposable production-mode deployment, restart, and configuration-rollback rehearsal.

### Data protection and recovery

- [ ] Define database backup frequency, retention, encryption, and ownership.
- [x] Perform and document a logical backup/restore rehearsal against disposable MySQL 8.4.
- [ ] Define retention rules for staged uploads, inactive batches, logs, and historical exports.
- [x] Document the personal-data lifecycle and unresolved retention governance decisions without automatic deletion.
- [ ] Verify target-environment transport, filesystem, database, and backup encryption controls.
- [x] Document incident response and administrator credential recovery.

### Operations and quality gates

- [x] Add and test production liveness, MySQL/schema readiness, and dependency-failure behavior.
- [x] Add structured request/authentication/import/lifecycle logging with an operational-field allow-list.
- [x] Define vendor-neutral monitoring signals and recommended availability/database/import alerts.
- [x] Exercise local application-unavailable, database-readiness, and import-failure signals without leaking secrets.
- [ ] Exercise end-to-end alert delivery through the selected monitoring platform.
- [x] Execute the CI workflow for tests, migrations, static analysis, production startup, and container build/runtime in hosted CI.
- [x] Run the complete 71-test integration suite against disposable MySQL in release validation.
- [x] Complete automated administrator and approved-user authorization/UAT regression coverage.
- [ ] Complete administrator and approved-user acceptance testing.

### Phase 2 exit criteria

- [ ] Production deployment and rollback are repeatable from documented procedures.
- [ ] HTTPS, secure cookies, secrets, and role boundaries are verified in the target environment.
- [ ] Backup restoration has been successfully demonstrated.
- [ ] Monitoring and failure alerts have been exercised.
- [ ] All automated and user-acceptance checks pass.
- [ ] Current documentation describes the deployed architecture without historical contradictions.

### Verified engineering evidence — 2026-08-29

- Isolated SQLite suite: 71 tests passed.
- Disposable MySQL 8.4 suite: the same 71 tests passed.
- Fresh disposable MySQL migration: all four Alembic upgrades reached
  `a9d3c7e5f102`; `alembic check` reported no new operations.
- Static analysis and compilation: Ruff and `compileall` passed.
- Production configuration/schema check: passed against local MySQL.
- Gunicorn production-mode readiness and graceful `SIGTERM`: passed locally.
- Backup/restoration rehearsal: checksum, restore, 16-table count comparison,
  active-batch ownership, and Events 1–3 dashboard reconciliation passed.
- A new disposable deployment rehearsal covered pre-deployment backup, clean
  migration, Gunicorn startup, administrator and standard-user HTTP access,
  structured logs, database outage/recovery, observed application unavailability,
  graceful shutdown, configuration recovery, restart, and readiness recovery.
- Local failure signals were exercised. External alert delivery was not.
- GitHub Actions run [33252156921](https://github.com/jakeromedev/ccf-event-intelligence/actions/runs/33252156921)
  at commit `8852f60` passed all three jobs:
  SQLite quality, disposable MySQL integration, and production container build/runtime.
- The hosted OCI job migrated disposable MySQL through the image, verified the
  non-root UID and image exclusions, started the production entrypoint/Gunicorn,
  passed Docker health and live/ready probes, and stopped gracefully with exit 0.
- Target HTTPS/storage controls, actual immutable application rollback, external
  alert delivery, and human UAT remain unchecked.

### Remaining Phase 2 classification — 2026-08-29

| Unchecked area | Classification | Required evidence |
|---|---|---|
| P2-01 through P2-10 and backup/retention policy | **Blocked — Product Decision** | Approved values, accountable owners, dates, and decision records. |
| Target transport, proxy boundary, secrets, filesystem, database, and backup controls | **Blocked — Target Environment** | Execute `TARGET_SECURITY_VALIDATION.md` on the selected platform. |
| Production deployment/application rollback | **Blocked — Target Environment** | Exercise approved immutable artifacts through the target platform. |
| Backup/recovery acceptance | **Blocked — Product Decision / Target Environment** | Approved store/authority/RPO/RTO and a retained target-level restore record. |
| Monitoring alerts | **Blocked — External Execution / Product Decision** | Approved thresholds/channels and recorded delivery/recovery tests. |
| Administrator and approved-user UAT | **Blocked — Target Environment** | Signed human results using `PRODUCTION_ACCEPTANCE.md`. |
| Deployed-architecture documentation | **Blocked — Target Environment** | Update the vendor-neutral documents with the approved target's actual controls. |

See `PHASE_2_VERIFICATION.md` for command and hosted-CI results, local
deployment/rollback evidence, monitoring signal results, and scenario-by-scenario
automated UAT.

---

## Phase 3 — Advanced Analytics and Reporting

Status: **In Progress**. Source-supported aggregate analytics are implemented;
revenue, downloads, final privacy policy, and product priorities remain decision-gated.

### Product-definition gate

- [ ] **Decision required:** Prioritize Payment, Revenue, Occupation, Dgroup, Home Area,
  historical trends, and cross-Event comparisons.
- [ ] **Decision required:** Approve authoritative Revenue and payment-discrepancy formulas.
- [ ] **Decision required:** Define who may export row-level or aggregate reports.
- [ ] Define privacy thresholds and suppression rules for small analytical groups.
  Engineering suppression is configurable and tested; final organizational threshold
  and differencing policy remain `Decision Required` in `PHASE_3_DECISIONS.md`.

### Analytics

- [x] Add Payment Status and payment-method analytics.
- [ ] Add validated Revenue, expected amount, paid amount, and discrepancy reporting.
- [x] Add Occupation analytics where reliable source fields exist.
- [x] Add Dgroup membership and leadership analytics where reliable source fields exist.
- [x] Add Home Area and other source-supported participant filters.
- [x] Add combined interactive filters across satellite and demographic dimensions.
- [x] Add registration-versus-check-in comparisons by source-supported dimensions.
- [x] Add historical batch trends for an Event.
- [x] Add comparative analytics across Events.

### Reporting

- [ ] Add approved downloadable aggregate reports.
- [ ] Add permission-protected row-level exports only if explicitly approved.
- [ ] Ensure report filters, totals, and definitions match on-screen analytics.
- [ ] Audit exported files for personal-data minimization and safe filenames.

### Phase 3 exit criteria

- [ ] Every new metric has an approved definition and reconciliation test.
- [x] Historical and cross-Event queries preserve Event and batch ownership boundaries.
- [ ] Export authorization and privacy behavior are covered by automated tests.
- [x] User-facing metric definitions and limitations are documented.

### Phase 3 implementation evidence — 2026-08-29

- Central analytics/filter/suppression service: `app/analytics.py`.
- Aggregate APIs and dedicated Analytics/Compare views use the same service.
- Implemented source-derived dimensions: Payment Status, Payment Method, Occupation,
  Dgroup, Home Area, attendance comparisons, Event snapshot trends, and explicit
  aggregate Event comparison.
- No monetary formula, aggregate download, or row-level export was implemented while
  its product decision remains open.
- SQLite: 80 tests passed on 2026-08-29.
- Disposable MySQL: the same 80 tests passed on 2026-08-29.
- Supplied-data reconciliation: 4,312 curated participants and 3,854 unique
  checked-in participants; every implemented distribution reconciled to 4,312.
- Supplied-data MySQL analytics query: 374.6 ms locally for 4,312 participants;
  no cache or Phase 4 worker infrastructure was introduced.
- Alembic upgraded an empty disposable MySQL database to `a9d3c7e5f102` and
  `alembic check` reported no new upgrade operations.
- Ruff, Python compilation, production configuration/schema validation, local
  Gunicorn readiness, and graceful SIGTERM passed.
- Hosted CI evidence is recorded only after the pushed workflow run completes.

### Phase 3 completion-iteration evidence — 2026-08-30

- The supplied monetary fields were audited without assigning accounting
  meaning: Generated Tickets exposes `Price`, `Price Type`, `Price Name`, and
  `Payment Status`; Buyers exposes `Gross Amount`, `Service Charge`, `Net
  Amount`, `Amount Paid`, statuses/methods/references, and a blank discount
  reference. No currency, refund amount/status, or explicit waiver amount was
  found. The structured approval contract is in `PHASE_3_DECISIONS.md`.
- Revenue remains disabled because Expected Amount, Paid Amount, Revenue,
  discrepancy, refund, discount/waiver, and currency rules are not approved.
- Downloadable aggregate and row-level reports remain disabled because export
  roles and privacy policy are not approved. `REPORTING.md` documents the
  required authorization, shared-service reconciliation, minimization,
  filename, spreadsheet-injection, audit, and ownership controls.
- Automated privacy coverage now exercises combined filters, active analytics,
  historical trends, and cross-Event comparisons. A separate regression test
  confirms that common download paths and UI controls remain absent while the
  decision gate is open. These tests do not claim that an unimplemented export
  has passed export-security acceptance.
- SQLite: 82 tests passed locally on 2026-08-30.
- Disposable MySQL 8.4: the same 82 tests passed locally on 2026-08-30.
- A fresh disposable MySQL schema upgraded through all four revisions to
  `a9d3c7e5f102`; `alembic check` reported no new operations.
- Ruff, Python compilation, production configuration/schema validation,
  Gunicorn liveness/readiness, and graceful `SIGTERM` shutdown passed locally.
- The previously pushed Phase 3 analytics foundation commit `d963c35` passed
  hosted CI run `33264910728`. Hosted CI evidence for this iteration must be
  recorded after its commit is pushed and the workflow actually completes.
- No checklist box changed in this iteration: remaining Revenue, export, final
  privacy-policy, and priority items are still product decisions rather than
  engineering assumptions.

---

## Phase 4 — Data Operations and Scale Automation

Phase 4 items should begin only when operational evidence or an approved
workflow justifies their complexity.

### Data stewardship

- [ ] **Decision required:** Define whether corrections modify source-derived overlays,
  create annotations, or require a corrected source export.
- [ ] Add an auditable Data Quality resolution and annotation workflow.
- [ ] Preserve immutable imported values when applying approved analytical corrections.
- [ ] Add administrator-managed satellite aliases and canonical-name governance.
- [ ] Version classification and correction rules when results can change historically.

### Import evolution

- [ ] Add batch-to-batch reconciliation for added, changed, unchanged, and missing records.
- [ ] **Decision required:** Approve or reject incremental append as an import mode.
- [ ] If approved, define conflict resolution, deletion semantics, and rollback behavior.
- [ ] Add preview and reconciliation evidence before publishing an incremental dataset.

### Conditional scaling work

- [ ] Measure import duration, request latency, and database load with representative datasets.
- [ ] Add background import workers only when synchronous processing exceeds approved limits.
- [ ] Add caching or stored aggregates only when measurements demonstrate a need.
- [ ] Define job retry, idempotency, cancellation, and failure-recovery behavior before adding workers.

### Phase 4 exit criteria

- [ ] Corrections and aliases are auditable, reversible, and Event/batch scoped.
- [ ] Any incremental import mode preserves atomic activation and reconciliation guarantees.
- [ ] Background jobs, if introduced, are idempotent and operationally observable.
- [ ] Performance changes have before-and-after measurements and regression coverage.

---

## Supporting documentation

- [README](README.md) — current local setup and feature summary
- [Technical Reference](TECHNICAL_REFERENCE.md) — runtime, database, migration, and security configuration
- [Current Database Structure](CURRENT_DATABASE_STRUCTURE.md) — authoritative schema and ownership model
- [Event Dashboard Module](DASHBOARD_MODULE.md) — dashboard metric and API contract
- [Event Imports Module](EVENT_IMPORTS_MODULE.md) — validation, processing, activation, and history
- [Data Quality Module](DATA_QUALITY_MODULE.md) — issue definitions and quality workflows
- [Admin Tables Module](ADMIN_TABLES_MODULE.md) — row-level administrative inspection
- [Authentication](AUTHENTICATION.md) — account, approval, session, and authorization behavior
- [Registrant and Satellite Curation](CURATION_LAYER.md) — deduplication and normalization contract
- [Phase 2 Decision Register](PHASE_2_DECISIONS.md) — unresolved product/operational decisions and engineering choices
- [Deployment Runbook](DEPLOYMENT_RUNBOOK.md) — production configuration, migrations, release, health, and smoke checks
- [Rollback Runbook](ROLLBACK_RUNBOOK.md) — application, configuration, migration, and restore rollback boundaries
- [Backup and Recovery](BACKUP_AND_RECOVERY.md) — guarded MySQL backup/restore and verification
- [Operations and Incident Response](OPERATIONS_AND_INCIDENT_RESPONSE.md) — logging, monitoring, retention, and containment
- [Production Acceptance and UAT](PRODUCTION_ACCEPTANCE.md) — target-environment acceptance and role-based UAT
- [Phase 2 Verification Record](PHASE_2_VERIFICATION.md) — executed local evidence and blocker classifications
- [Target Security Validation](TARGET_SECURITY_VALIDATION.md) — executable target HTTPS, proxy, secrets, storage, database, and backup checks
