# Attestation Status Import Preservation — Implementation Plan

> **Implementation status (2026-08-31):** Phases 1–4 are implemented. Durable
> Event-scoped participant ownership now drives imports, Registrations reads,
> and status writes, with complete SQLite and dedicated MySQL regression suites
> passing. Hosted CI and manual browser acceptance remain external.

## Purpose

This document defines the planned update for the **Registrations module attestation workflow** so that importing updated registration files does **not reset an already reviewed participant's Attestation Status back to `Pending`**.

This change is intentionally limited to **Attestation Status**.

> **Payment Status is completely out of scope for this update.**

The implementation must preserve the existing principle that imported registration data and application-managed operational data are separate.

---

# Problem Statement

The current Registrations module displays one imported `registrants` record per row.

The current attestation relationship is conceptually:

```text
registrants.id
    ↓
attestation_verifications.registrant_id
    ↓
Pending / Verified / Invalid
```

This means the Attestation Status is attached to a specific imported registration row.

When an updated registration file is imported, the importer may:

- create a replacement/new `registrants` row;
- recreate the record under a new import batch;
- delete/rebuild records;
- fail to reuse the existing `registrants.id`;
- or otherwise cause the previous `attestation_verifications.registrant_id`
  relationship to no longer represent the current row.

The Registrations module then sees no matching verification record and correctly
falls back to:

```text
Pending
```

from the application's current default behavior.

The visible symptom is therefore:

```text
Participant is reviewed
        ↓
Attestation Status = Verified
        ↓
Updated registration file is imported
        ↓
Registrant row is recreated/replaced/re-resolved
        ↓
Previous verification relationship is not found
        ↓
Attestation Status appears as Pending
```

This must be fixed.

---

# Required Business Rule

## Core Rule

**Attestation Status belongs to the participant within the logical registration batch, not to an individual imported row.**

For one participant in one logical batch:

```text
1 participant
+
1 logical batch
=
1 current Attestation Status
```

There must never be multiple independent current statuses for the same participant inside the same logical batch.

Example:

```text
Batch: B1G19 Registration Batch A
Participant: Juan Dela Cruz

Attestation Status:
Verified
```

If Juan's registration data is imported again with updated information:

```text
Old import:
Juan Dela Cruz
Satellite = B1G Imus
Attestation Status = Verified

Updated import:
Juan Dela Cruz
Satellite = B1G Gen. Trias
```

the expected result is:

```text
Satellite:
B1G Imus → B1G Gen. Trias

Attestation Status:
Verified → Verified
```

The importer may update source-owned participant information, but it must not
reset or replace the application-owned Attestation Status.

---

# Status Ownership Contract

## Imported / Source-Owned Data

The importer may create or update fields originating from the uploaded source,
including the Attestation Form URL itself.

Examples:

```text
First Name
Last Name
Email
Mobile Number
Gender
Birth Month
Birth Year
Satellite
Life Stage
Shirt Size
Transportation
Plate Number
Attestation Form URL
other imported source_data_json values
```

## Application-Owned Data

The importer must **not** own the Attestation Status.

Application-owned attestation information includes:

```text
Attestation Status
Last Reviewed By
Last Reviewed At
Created At / Updated At for the verification record
```

Allowed status values remain:

```text
pending
verified
invalid
```

The importer must never blindly execute behavior equivalent to:

```python
attestation_status = "pending"
```

for an already known participant in the same logical batch.

---

# Important Definition: Logical Batch vs Import Run

Before implementation, the project must establish what `import_batches`
currently represents.

There are two possibilities:

## Case A — `import_batches` represents the logical operational batch

Example:

```text
Event
└── Registration Batch A
    ├── Initial file import
    ├── Updated file import
    └── Final file import
```

If this is already how the database behaves, Attestation Status can potentially
use the existing `batch_id` as part of its ownership key.

## Case B — every uploaded file creates a new `import_batches` row

Example:

```text
Event
├── Import Batch 101 — Initial file
├── Import Batch 102 — Updated file
└── Import Batch 103 — Final file
```

If this is the current behavior, `import_batches.id` alone cannot safely define
the logical ownership of Attestation Status.

In that case the implementation must identify or introduce a stable logical
batch/event-registration scope that survives repeated imports.

> An updated file upload must not accidentally create a completely new
> Attestation Status lifecycle merely because the technical import-run ID
> changed.

This distinction must be resolved in **Phase 1 before any migration is written**.

---

# Target Data Model Principle

The final model must enforce:

```text
Logical Batch
    +
Stable Participant Identity
    ↓
One Attestation Verification
```

Conceptually:

```text
logical_batch
    │
    ├── participant A
    │      └── one attestation status
    │
    ├── participant B
    │      └── one attestation status
    │
    └── participant C
           └── one attestation status
```

Repeated imported rows for Participant A must resolve back to the **same
verification record**.

---

# Stable Participant Identity

Do not choose the final participant key until Phase 1 confirms the current
database structure.

Preferred options, in order:

1. Existing stable `curated_registrant_id`, if it is available, trustworthy,
   event-compatible, and already survives re-imports.
2. Another existing stable participant/entity identifier already used by the
   importer.
3. A dedicated stable participant identity record/key introduced specifically
   to prevent imported row IDs from being used as person identity.

Do **not** rely on mutable display fields such as:

```text
First Name
Last Name
Email
Mobile Number
```

as a database foreign key.

If the existing curated registrant matching logic is used, Phase 1 must verify
its exact identity contract and collision behavior before it becomes the basis
for Attestation Status.

---

# PHASE 1 — Current Database and Import Flow Assessment

## Objective

Understand the exact current database structure and importer lifecycle before
changing any schema or application behavior.

**Phase 1 is analysis and planning only.**

Do not implement the final migration or change production Attestation Status
behavior during this phase.

---

## 1. Inspect Current Database Models

Document the actual models/tables related to:

```text
events
import_batches
registrants
curated_registrants
curated_registrant_sources
attestation_verifications
users
```

Also inspect any additional tables used to identify:

- participant identity;
- event ownership;
- logical batch ownership;
- import provenance;
- source-record replacement;
- deduplication.

For every relevant table, record:

```text
Primary Key
Foreign Keys
Unique Constraints
Indexes
Nullable Fields
Cascade / Restrict Behavior
Created / Updated timestamps
```

---

## 2. Document the Current Relationships

Produce the actual current relationship diagram.

At minimum verify whether the existing implementation is effectively:

```text
events
   ↓
import_batches
   ↓
registrants
   ↓
attestation_verifications
```

and confirm:

```text
attestation_verifications.registrant_id
    → registrants.id
```

Determine whether `registrant_id` currently has a unique constraint.

---

## 3. Inspect the Actual Attestation Verification Schema

Confirm the exact columns and constraints in
`attestation_verifications`.

Expected/current conceptual fields may include:

```text
id
registrant_id
status
updated_by_user_id
created_at
updated_at
```

Do not assume the documentation is identical to the live implementation.

Verify:

- default status behavior;
- whether a row is created automatically;
- whether `Pending` is represented by an actual row or by absence of a row;
- how reviewer attribution works;
- how timestamps are generated;
- how deletion of a registrant affects verification records.

---

## 4. Inspect the Registrations Query

Review the current Registrations module query and confirm how Attestation
Status is joined.

Document the current behavior for:

```text
registrants
LEFT JOIN attestation_verifications
    ON attestation_verifications.registrant_id = registrants.id
```

Confirm how:

```text
no verification row
```

becomes:

```text
Pending
```

in:

- table rows;
- summary counts;
- quick filters;
- sorting;
- filtering;
- Attestation Review modal;
- status PATCH endpoint.

---

## 5. Inspect the Import Lifecycle

Trace a real import from file upload through database persistence.

Determine whether an updated import:

- updates an existing `registrants` row in place;
- inserts a new row;
- deletes/recreates rows;
- creates an entirely new `import_batches` record;
- marks an older batch inactive;
- copies records from the previous batch;
- replaces source rows wholesale;
- uses an upsert;
- or uses another reconciliation strategy.

Document the exact code path.

---

## 6. Determine What a "Batch" Currently Means

This is a mandatory Phase 1 decision point.

Answer:

### Is `import_batches.id`:

**A. A logical registration batch**

or

**B. A technical file-import execution?**

Document examples from the existing data.

The implementation must not proceed until this is understood.

---

## 7. Inspect Participant Identity / Deduplication

Determine how the project currently identifies the same person across source
records and imports.

Review:

```text
curated_registrants
curated_registrant_sources
```

and any identity-resolution logic.

Confirm whether the existing curated registrant identity is stable enough to
support:

```text
logical_batch_id + curated_registrant_id
```

as the Attestation Status uniqueness key.

If the current curated identity logic uses a composite such as:

```text
Last Name
+ Birth Month
+ Birth Year
+ Gender
```

document:

- normalization rules;
- null handling;
- collision behavior;
- changes to participant data;
- how multiple source records map to one curated registrant;
- whether the curated identity survives a new import.

Do not redesign the entire curated registrant system as part of this task.

---

## 8. Reproduce the Current Bug

Create a focused automated/integration reproduction.

Example:

```text
1. Import Participant A.
2. Participant A has no verification row.
3. UI displays Pending.
4. Set Participant A to Verified.
5. Import an updated source file containing Participant A.
6. Load the current Registrations module.
7. Observe whether Participant A becomes Pending again.
```

Record why the relationship is lost.

The reproduction test should initially fail and later become a regression test.

---

## 9. Determine the Safest Target Ownership Key

At the end of Phase 1, recommend one concrete target.

Preferred target if supported by the actual schema:

```text
UNIQUE (
    logical_batch_id,
    curated_registrant_id
)
```

Possible alternative:

```text
UNIQUE (
    logical_batch_id,
    stable_participant_id
)
```

Avoid retaining:

```text
UNIQUE (registrant_id)
```

as the sole identity contract if `registrant_id` changes during re-import.

---

## 10. Phase 1 Deliverable

Create/update a technical assessment document containing:

### Current State

```text
Current tables
Current foreign keys
Current import behavior
Current participant identity behavior
Current Attestation Status behavior
```

### Root Cause

Explain precisely why a new import results in:

```text
Verified / Invalid
        ↓
Pending
```

### Proposed Target State

Document:

```text
one Attestation Status
per participant
per logical batch
```

### Migration Impact

List:

- tables requiring changes;
- constraints requiring changes;
- query joins requiring changes;
- endpoints requiring changes;
- importer changes;
- data migration/backfill requirements;
- tests that must be updated.

---

## Phase 1 Exit Criteria

Phase 1 is complete only when all of the following are known:

- [x] Exact `attestation_verifications` schema is documented.
- [x] Exact `registrants` relationship is documented.
- [x] Exact meaning/lifecycle of `import_batches` is documented.
- [x] Updated-import behavior has been traced in code.
- [x] The reset-to-Pending bug has been reproduced.
- [x] Stable participant identity options have been evaluated.
- [x] The logical batch identifier has been identified.
- [x] The proposed uniqueness key has been selected.
- [x] Existing verification records that require migration are understood.
- [x] No production data behavior has been changed prematurely.

---

# PHASE 2 — Attestation Ownership Model and Database Migration

## Objective

Change the Attestation Status persistence model so that it belongs to the
participant within a logical batch rather than to a replaceable imported row.

Proceed only using the findings from Phase 1.

---

## 1. Required Uniqueness Rule

The database must guarantee:

```text
one current attestation verification
per participant
per logical batch
```

Preferred conceptual constraint:

```text
UNIQUE (
    logical_batch_id,
    stable_participant_id
)
```

If Phase 1 confirms `curated_registrant_id` is appropriate:

```text
UNIQUE (
    logical_batch_id,
    curated_registrant_id
)
```

---

## 2. Verification Record Concept

Target conceptual table:

```text
attestation_verifications
├── id
├── logical_batch_id
├── stable_participant_id / curated_registrant_id
├── status
├── updated_by_user_id
├── created_at
└── updated_at
```

`registrant_id` may:

- be removed;
- remain temporarily for migration;
- or remain as non-authoritative source provenance;

depending on Phase 1 findings.

It must not remain the only identity mechanism if imported row IDs are unstable.

---

## 3. Status Default

A participant with no verification record should continue to be interpreted as:

```text
Pending
```

with:

```text
Last Reviewed By = —
Last Reviewed At = —
```

Do not create unnecessary `Pending` rows for every participant unless the
existing architecture specifically benefits from it.

---

## 4. Existing Data Migration

Existing manual review work must be preserved.

For every current `attestation_verifications` row:

```text
current registrant_id
    ↓
resolve registrant
    ↓
resolve logical batch
    ↓
resolve stable participant
    ↓
migrate verification ownership
```

Preserve:

```text
status
updated_by_user_id
created_at
updated_at
```

Do not silently convert:

```text
Verified → Pending
Invalid → Pending
```

during migration.

---

## 5. Duplicate Verification Conflict Handling

If historical data reveals more than one verification row that resolves to the
same:

```text
logical batch + participant
```

do not silently discard records.

Define a deterministic migration policy.

Recommended approach:

1. report the conflict;
2. inspect status/timestamps;
3. preserve the most recently reviewed current state where appropriate;
4. retain enough migration logging to identify what was consolidated;
5. fail safely if the conflict cannot be resolved deterministically.

Do not create a permanent complex audit-history system as part of this update
unless separately approved.

---

## 6. Database Compatibility

Migration must remain compatible with the project's supported database targets.

Validate against:

```text
SQLite
MySQL
```

Follow current Alembic conventions.

---

## Phase 2 Exit Criteria

- [x] Verification ownership no longer depends solely on a replaceable imported row.
- [x] Database guarantees one status per participant per logical batch.
- [x] Existing Verified/Invalid/Pending review state is preserved.
- [x] Existing reviewer attribution is preserved.
- [x] Existing review timestamps are preserved.
- [x] Migration handles conflicts safely.
- [x] SQLite migration passes.
- [ ] MySQL migration passes.
- [x] `alembic check` passes.

---

# PHASE 3 — Import Reconciliation and Registrations Module Integration

## Objective

Ensure updated imports reuse the existing participant-level Attestation Status
instead of resetting it.

---

## 1. Import Rule

When importing a participant:

```text
Resolve logical batch
        ↓
Resolve stable participant identity
        ↓
Import/update source-owned registration data
        ↓
Look up existing Attestation Status
using logical batch + participant
        ↓
PRESERVE it
```

The importer must not create a new verification state merely because it created
or updated a `registrants` row.

---

## 2. New Participant Behavior

When a participant is genuinely new to the logical batch:

```text
No existing verification record
        ↓
Attestation Status displays Pending
```

This is correct behavior.

---

## 3. Existing Participant Behavior

When the participant already exists in the logical batch:

```text
Existing status = Verified
Updated file imported
Existing status = Verified
```

or:

```text
Existing status = Invalid
Updated file imported
Existing status = Invalid
```

or:

```text
Existing status = Pending
Updated file imported
Existing status = Pending
```

---

## 4. Attestation Form URL Changes

The Attestation Form URL is imported source data.

If an updated import changes:

```text
old_attestation_form_url
        ↓
new_attestation_form_url
```

do **not** automatically reset the Attestation Status.

Required default behavior:

```text
Form URL changed
Attestation Status preserved
```

A future "Needs Re-review" feature may be designed separately if required.

It is not part of this update.

---

## 5. Registrations Query

Update the Registrations query so Attestation Status is resolved through the
new participant-within-batch ownership relationship.

Conceptually:

```text
registrants
    ↓
resolve stable participant
    ↓
logical batch
    ↓
attestation_verifications
```

Do not rely solely on:

```text
attestation_verifications.registrant_id = registrants.id
```

if Phase 1 confirms that imported IDs are unstable.

---

## 6. Multiple Imported Rows for the Same Participant

If the current Registrations page continues to display one source
`registrants` row per table row, multiple rows that resolve to the same
participant within the same batch must show the **same current Attestation
Status**.

Example:

```text
Batch A

Registrant Row 101 → Participant X ┐
Registrant Row 184 → Participant X ├─→ Verified
Registrant Row 230 → Participant X ┘
```

Changing status from any valid workflow for Participant X must update the one
shared verification state.

There must not be:

```text
Row 101 = Verified
Row 184 = Pending
Row 230 = Invalid
```

for the same participant in the same logical batch.

---

## 7. Status Update Endpoint

Update the existing Attestation Status PATCH flow so it resolves:

```text
event
logical batch
participant
```

before updating the verification record.

The endpoint must still enforce:

- authentication;
- authorization;
- CSRF protection;
- event ownership;
- batch ownership;
- participant ownership;
- allow-listed statuses.

Allowed values remain:

```text
pending
verified
invalid
```

---

## 8. Reviewer Metadata

Manual changes must continue to update:

```text
updated_by_user_id
updated_at
```

The new import process must not impersonate a reviewer and must not rewrite
reviewer metadata when only imported source data changed.

---

## Phase 3 Exit Criteria

- [x] Updated imports preserve Attestation Status.
- [x] Updated imports preserve Last Reviewed By.
- [x] Updated imports preserve Last Reviewed At.
- [x] New participants correctly appear as Pending.
- [x] Existing Verified participants remain Verified.
- [x] Existing Invalid participants remain Invalid.
- [x] Form URL changes do not reset status.
- [x] Duplicate imported rows for the same participant share one status.
- [x] Status updates use the participant-within-batch identity.
- [x] Existing authorization and CSRF protections remain intact.

---

# PHASE 4 — Regression Testing, Data Integrity, and Documentation

## Objective

Prove that Attestation Status cannot be lost through future registration
imports and document the final architecture.

---

## 1. Core Regression Tests

### Scenario A — Verified Survives Import

```text
Import Participant A
Set status = Verified
Import updated Participant A
Expected = Verified
```

### Scenario B — Invalid Survives Import

```text
Import Participant A
Set status = Invalid
Import updated Participant A
Expected = Invalid
```

### Scenario C — Pending Survives Import

```text
Import Participant A
Status remains default Pending
Import updated Participant A
Expected = Pending
```

### Scenario D — New Participant

```text
Import Participant B for first time
Expected = Pending
Reviewer = —
Reviewed At = —
```

### Scenario E — Form URL Changed

```text
Participant A = Verified
Import updated Participant A with new Attestation Form URL
Expected:
Form URL = new URL
Status = Verified
```

### Scenario F — Multiple Source Rows Same Participant

```text
Two source rows resolve to Participant A in same logical batch
Set Participant A = Verified
Expected:
Both displayed rows = Verified
Only one current verification record exists
```

### Scenario G — Different Logical Batch

Confirm the intended isolation rule:

```text
Participant A in Batch 1
Participant A in Batch 2
```

Each logical batch has its own single Attestation Status record.

Do not accidentally share a status across unrelated logical batches.

---

## 2. Import Repeatability

Test repeated imports:

```text
Initial Import
Updated Import #1
Updated Import #2
Updated Import #3
```

The number of Attestation Status records for the same participant and logical
batch must remain:

```text
1
```

not:

```text
4
```

---

## 3. Database Constraint Test

Attempt to create two verification records for the same:

```text
logical batch + participant
```

The database must reject the duplicate.

Do not rely only on application code to enforce the rule.

---

## 4. Query and UI Regression

Verify:

- Attestation summary counts;
- Pending / Verified / Invalid quick filters;
- Attestation Status filtering;
- Attestation Status sorting;
- Attestation Review modal;
- Last Reviewed By;
- Last Reviewed At;
- active batch view;
- specific batch view;
- all-batches view.

Counts must not be multiplied incorrectly by duplicate source rows or joins.

If the UI intentionally counts imported rows rather than unique participants,
document that distinction explicitly.

---

## 5. Security Regression

Retest:

- unauthenticated status update;
- unauthorized status update;
- manipulated event ID;
- manipulated batch ID;
- manipulated participant/registrant ID;
- cross-event access;
- CSRF enforcement.

---

## 6. Full Project Validation

Run the repository's normal validation suite, including where applicable:

```text
SQLite tests
MySQL tests
Alembic upgrade
Fresh database migration
alembic check
Ruff
Python compilation
Production configuration validation
CI
```

Do not remove, skip, or weaken existing valid tests to make this update pass.

---

## 7. Documentation Update

Update the relevant project documentation to clearly state:

> Attestation Status is application-owned operational data. It is stored once
> per participant per logical batch and is not overwritten by registration
> imports.

Update documentation describing:

- Registrations module row contract;
- Attestation verification relationship;
- importer behavior;
- participant identity;
- batch identity;
- status update endpoint;
- default Pending behavior;
- reviewer metadata;
- data migration;
- known limitations.

---

# Explicitly Out of Scope

Do not include any of the following in this update:

- Payment Status changes
- Payment Status preservation logic
- payment reconciliation
- paid amount or revenue calculations
- ticket payment redesign
- monetary fields
- new payment workflows
- Attestation audit-history ledger
- automatic Attestation re-review when the form URL changes
- redesign of the global header
- redesign of the sidebar
- unrelated Admin Tables changes
- unrelated dashboard changes
- broad curated-registrant redesign unless strictly required to establish a
  stable participant identity

---

# Final Expected Architecture

## Implemented identity and counting contract

- `events.id` is the durable logical registration scope. Technical
  `import_batches.id` values are replaceable source snapshots inside it.
- One `attestation_participants` row represents durable attestation identity
  inside an Event.
- Normalized exact source ID, registration code, and ticket code aliases map
  replacement imports to that identity. If all authoritative identifiers
  change, the record is conservatively treated as a new participant and starts
  Pending.
- Mutable demographic curation values are not durable foreign keys. They only
  group duplicate source rows inside one import run.
- If a source group would join identifiers already owned by different durable
  participants, processing fails and the previous active batch remains active.
- Registrations continues to display and count imported source rows. Therefore
  two displayed rows for one participant both contribute to summary counts,
  but both resolve the same single verification record.
- Attestation Form URL remains source-owned. A URL change does not reset status
  or reviewer metadata.
- `registrant_id` on a verification is nullable latest-review provenance, not
  ownership. Deleting a technical batch may clear it without deleting status.

## Phase 4 local validation

- Verified, Invalid, and derived Pending preservation: passed.
- New participant Pending behavior: passed.
- Form URL and imported field changes with preserved review metadata: passed.
- Three sequential replacement imports with exactly one verification: passed.
- Duplicate source rows sharing one verification: passed.
- Same identifiers isolated across different Events: passed.
- Active, historical, and all-batches row counts/filtering/sorting: passed.
- Ambiguous identity import failure with previous-active preservation: passed.
- Database duplicate-verification rejection: passed.
- Existing authentication, authorization, CSRF, and ownership tests: passed.
- SQLite fresh migration, populated backfill, `alembic check`, and downgrade:
  passed.
- Ruff, Python compilation, JavaScript syntax, and whitespace checks: passed.
- Live local MySQL migration, `alembic check`, database check, and complete
  dedicated-MySQL suite: passed.
- Hosted CI and manual browser acceptance: not executed in this environment.

```text
                         EVENT
                           │
                           ▼
                    LOGICAL BATCH
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
     IMPORTED REGISTRATIONS      PARTICIPANT IDENTITY
              │                         │
              │                         │
   source-owned fields                   │
              │                         │
              └────────────┬────────────┘
                           ▼
                ATTESTATION VERIFICATION
                           │
                 one row per participant
                    per logical batch
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
          Status      Last Reviewer   Reviewed At
```

Updated registration imports may replace or update imported source records, but
the Attestation Verification record remains anchored to:

```text
logical batch + participant
```

rather than to a transient imported row.

---

# Final Acceptance Criteria

The update is complete when all of the following are true:

- [x] Importing an updated registration file never resets an existing
      Attestation Status solely because of the import.
- [x] Attestation Status is not imported from the source file.
- [x] Attestation Status is not stored as mutable source data.
- [x] A participant has exactly one current Attestation Status inside a logical
      batch.
- [x] Repeated imports do not create duplicate verification states.
- [x] Verified remains Verified after import.
- [x] Invalid remains Invalid after import.
- [x] Pending remains Pending after import.
- [x] A genuinely new participant starts as Pending.
- [x] Reviewer and review timestamp survive source-data imports.
- [x] Changing the Attestation Form URL does not automatically reset status.
- [x] Database constraints enforce the one-status-per-participant-per-batch
      rule.
- [x] Existing Registrations filtering, sorting, summary counts, modal review,
      and authorization continue to work.
- [x] Payment Status behavior is untouched.
- [x] SQLite validation passes.
- [x] Live MySQL validation passes.
- [x] Migrations and project documentation accurately describe the final model.

---

# Implementation Sequence Summary

```text
PHASE 1
Inspect Current Database + Import Lifecycle
        ↓
PHASE 2
Design/Migrate Participant-Within-Batch Status Ownership
        ↓
PHASE 3
Make Imports Preserve Attestation Verification
        ↓
PHASE 4
Regression Testing + Integrity + Documentation
```

## Governing Principle

> **An import updates registration data. It does not erase operational review
> decisions already made inside the system.**
