# Registrant Remarks Feature — Persistent Across Imports

> **Implementation status (2026-09-01):** Phases 1 through 4 are complete. The
> durable Remarks model, scoped backend API, authorization, table aggregates,
> filtering, accessible modal workflow, import preservation, and regression
> hardening are implemented and validated on SQLite and MySQL.
> See `REGISTRANT_REMARKS_PHASE_1_ASSESSMENT.md` for the ownership decision.

## Purpose

Add a **Remarks** feature to the Registrations module so authorized users can add one or more operational remarks to a specific participant and track each remark as:

- `Pending`
- `Resolved`

The critical rule is:

> **Remarks must not be reset, deleted, recreated, or changed when a new registration file or batch is imported.**

Remarks are **application-owned operational data**, just like Attestation Status.

---

# Core Business Rule

For the same participant, importing updated registration data must preserve all existing remarks and their statuses.

Example:

```text
Before Import

Participant: Juan Dela Cruz

Remark 1:
"Confirm satellite assignment."
Status: Pending

Remark 2:
"Mobile number verified."
Status: Resolved
```

After importing an updated registration file:

```text
Participant: Juan Dela Cruz

Remark 1:
"Confirm satellite assignment."
Status: Pending

Remark 2:
"Mobile number verified."
Status: Resolved
```

Only source-owned registration data may change.

The Remarks records must remain untouched.

---

# Ownership Principle

Remarks must not depend solely on a replaceable imported `registrants.id`.

The target relationship should follow the same stable identity approach being used for Attestation Status:

```text
Stable Participant
        +
Logical Event / Registration Scope
        ↓
Registrant Remarks
```

Repeated imports may create or update registration rows, but the remarks remain associated with the same participant.

Conceptually:

```text
Import #1 ─┐
Import #2 ─┼──> Stable Participant ───> Remarks
Import #3 ─┘
```

---

# Relationship to Attestation Status

Both workflows are application-owned.

```text
Attestation Status
→ preserved across imports

Registrant Remarks
→ preserved across imports
```

Neither should be overwritten by imported source data.

However, they remain separate features and separate data structures.

Changing a remark must never change Attestation Status.

Changing Attestation Status must never change remarks.

---

# Recommended Data Model

Use a dedicated table for remarks because a participant may have multiple remarks.

Recommended conceptual model:

```text
registrant_remarks
------------------
id
participant_id / curated_registrant_id
logical_batch_id / event_scope_id
remark
status
created_by_user_id
resolved_by_user_id
created_at
updated_at
resolved_at
```

Allowed statuses:

```text
pending
resolved
```

Do not finalize the exact foreign keys until Phase 1 confirms the current database and import architecture.

---

# Important Database Rule

A remark itself must be a persistent independent record.

Example:

```text
Participant A
├── Remark 101 — Pending
├── Remark 102 — Resolved
└── Remark 103 — Pending
```

A new import must continue resolving Participant A to these same records.

The importer must never:

```text
DELETE remarks
RESET remarks
RECREATE remarks as Pending
COPY remarks into duplicate records
```

---

# PHASE 1 — Current Database and Import Ownership Assessment

## Objective

Inspect the existing database and import lifecycle so remarks can be attached to a stable participant identity rather than to a replaceable imported row.

**Phase 1 is analysis and planning only.**

## Inspect Current Tables

Review:

```text
events
import_batches
registrants
curated_registrants
curated_registrant_sources
attestation_verifications
users
```

Also inspect any existing:

```text
remarks
notes
comments
admin annotations
status history
```

## Determine Stable Participant Identity

Confirm how the system currently recognizes the same person across repeated imports.

Preferred identity if already stable:

```text
curated_registrant_id
```

Otherwise identify the existing stable participant entity used by the importer.

Do not use mutable fields such as:

```text
name
email
mobile number
satellite
```

as database foreign keys.

## Inspect Import Lifecycle

Determine whether a new upload:

- updates existing `registrants` rows;
- inserts replacement rows;
- deletes/recreates records;
- creates a new `import_batches` record;
- changes the active batch;
- maps rows back to curated registrants.

Document exactly why Attestation Status and future Remarks could become disconnected if tied only to `registrants.id`.

## Determine Logical Scope

Confirm whether remarks should be scoped by:

```text
event + participant
```

or:

```text
logical registration batch + participant
```

Use the same stable scope principle chosen for Attestation Status unless there is a documented business reason not to.

A technical import-run ID must not cause remarks to reset.

## Phase 1 Deliverable

Document:

```text
Current schema
Import lifecycle
Stable participant identity
Logical batch/event scope
Existing Attestation ownership model
Recommended Remarks ownership model
Required migration
Required endpoints
Required query changes
Required tests
```

## Phase 1 Exit Criteria

- [x] Current schema is documented.
- [x] Import lifecycle is documented.
- [x] Stable participant identity is confirmed.
- [x] Logical event/batch scope is confirmed.
- [x] Technical import IDs are distinguished from logical ownership.
- [x] Recommended Remarks ownership key is selected.
- [x] Existing remarks/note structures have been checked.
- [x] Required migration and API work are documented.

---

# PHASE 2 — Persistent Remarks Model and Backend API

## Objective

Create a persistent remarks model that survives new imports.

## 1. Create `registrant_remarks`

Recommended conceptual schema:

```text
registrant_remarks
├── id
├── stable_participant_id / curated_registrant_id
├── logical_batch_id / event_scope_id
├── remark
├── status
├── created_by_user_id
├── resolved_by_user_id
├── created_at
├── updated_at
└── resolved_at
```

Do not make `registrant_id` the sole authoritative owner if Phase 1 confirms that imported row IDs can change.

## 2. Multiple Remarks Per Participant

Support:

```text
1 participant
→ many remarks
```

Each remark has its own status.

Example:

```text
Remark 1 → Pending
Remark 2 → Pending
Remark 3 → Resolved
```

## 3. Default Status

New remarks default to:

```text
pending
```

Existing remarks must not be reset to Pending during imports.

## 4. Create Remark API

Conceptual endpoint:

```text
POST /events/{event_id}/participants/{participant_id}/remarks
```

Payload:

```json
{
  "remark": "Please confirm satellite assignment."
}
```

Server creates:

```text
status = pending
created_by_user_id = current_user.id
created_at = now
```

## 5. Resolve Remark API

Conceptual endpoint:

```text
PATCH /events/{event_id}/participants/{participant_id}/remarks/{remark_id}
```

Payload:

```json
{
  "status": "resolved"
}
```

When resolved:

```text
status = resolved
resolved_by_user_id = current_user.id
resolved_at = now
```

## 6. Optional Reopen

If supported:

```text
Resolved → Pending
```

Then clear:

```text
resolved_by_user_id
resolved_at
```

This is optional for the first release.

## 7. Import Protection

The importer must never directly update:

```text
registrant_remarks.remark
registrant_remarks.status
registrant_remarks.created_by_user_id
registrant_remarks.resolved_by_user_id
registrant_remarks.resolved_at
```

These are application-owned fields.

## Phase 2 Exit Criteria

- [x] Persistent Remarks table exists.
- [x] Remarks use stable participant ownership.
- [x] Multiple remarks are supported.
- [x] New remarks default to Pending.
- [x] Pending → Resolved works.
- [x] Existing remarks are unaffected by import code.
- [x] Reviewer/author metadata is preserved.
- [x] SQLite migration passes.
- [x] MySQL migration passes.

---

# PHASE 3 — Registrations UI and Import Preservation Integration

## Objective

Add Remarks to the Registrations UI and ensure repeated imports continue showing the same participant remarks.

## 1. Add Remarks Column / Action

Add a Remarks action to each participant row.

Suggested display:

```text
No Remarks
```

or:

```text
2 Pending
```

or:

```text
1 Pending · 3 Resolved
```

## 2. Remarks Modal

Clicking Remarks opens a modal containing:

```text
Participant Name

Add Remark
[ textarea ]

[ Save ]

Pending Remarks
Resolved Remarks
```

## 3. Pending First

Display:

```text
Pending remarks
→ first

Resolved remarks
→ after Pending
```

Recommended ordering within each group:

```text
newest first
```

## 4. Add Remark

Users can add a new remark from the modal.

New record:

```text
status = Pending
```

The UI should update immediately where practical.

## 5. Resolve Remark

Each Pending remark has:

```text
Mark Resolved
```

Resolved remarks display:

```text
Resolved By
Resolved At
```

## 6. Preserve Remarks During Import

Import flow must behave as:

```text
Resolve imported row
        ↓
Resolve stable participant
        ↓
Update source-owned registration fields
        ↓
Leave registrant_remarks untouched
        ↓
Registrations page continues showing existing remarks
```

Example:

```text
Before import:
Juan
2 Pending
1 Resolved

After import:
Juan
2 Pending
1 Resolved
```

## 7. Replacement Registrant Rows

If a new upload creates a different `registrants.id` for Juan:

```text
Old registrant_id = 101
New registrant_id = 488
```

the UI must still resolve the same stable participant and display the existing remarks.

## 8. Filtering

Recommended filter:

```text
Remarks
├── All
├── Has Pending Remarks
├── Has Remarks
└── No Remarks
```

At minimum:

```text
Has Pending Remarks
```

## 9. Attestation Independence

Remarks functionality must not modify:

```text
Attestation Status
Attestation Form URL
Attestation reviewer
Attestation timestamps
```

## Phase 3 Exit Criteria

- [x] Remarks action is available per registrant.
- [x] Users can create remarks.
- [x] Users can resolve remarks.
- [x] Pending remarks are easy to identify.
- [x] Resolved remarks remain visible.
- [x] Re-importing the participant preserves all remarks.
- [x] Replacement `registrants.id` values do not lose remarks.
- [x] Existing Attestation Status is unaffected.
- [x] Filtering and pagination remain functional.

---

# PHASE 4 — Regression Testing, Integrity, and Documentation

## Objective

Prove that remarks survive repeated imports and cannot be accidentally reset.

## Scenario A — Pending Remark Survives Import

```text
Import Participant A
Add Remark
Status = Pending

Import updated Participant A

Expected:
Same remark exists
Status = Pending
```

## Scenario B — Resolved Remark Survives Import

```text
Participant A
Remark = Resolved

Import updated Participant A

Expected:
Same remark exists
Status = Resolved
Resolved By unchanged
Resolved At unchanged
```

## Scenario C — Multiple Remarks Survive Import

```text
Participant A
Remark 1 = Pending
Remark 2 = Resolved
Remark 3 = Pending

Import updated Participant A

Expected:
All 3 remarks remain unchanged
```

## Scenario D — Repeated Imports

Run:

```text
Import #1
Import #2
Import #3
Import #4
```

Expected:

```text
No duplicate remarks
No deleted remarks
No reset statuses
```

## Scenario E — New Imported Row ID

If Participant A receives a new imported `registrants.id`:

```text
Old row → 101
New row → 410
```

Expected:

```text
Participant A still sees the same remarks
```

## Scenario F — Attestation Status Independence

```text
AF Status = Verified
Remark = Pending

Import updated data
```

Expected:

```text
AF Status = Verified
Remark = Pending
```

Neither workflow resets the other.

## Scenario G — Remark Resolution

```text
Pending remark
→ Mark Resolved
→ Import updated registration file
```

Expected:

```text
Resolved remains Resolved
```

## Data Integrity Tests

Verify:

- remarks point to stable participant ownership;
- no import creates duplicate remark records;
- author metadata survives imports;
- resolver metadata survives imports;
- timestamps survive imports.

## Security Tests

Verify:

- unauthorized create is rejected;
- unauthorized resolve is rejected;
- manipulated participant ID is rejected;
- cross-event access is rejected;
- cross-scope access is rejected;
- CSRF remains enforced.

## Performance Tests

Avoid N+1 queries when loading remark counts.

Prefer aggregated queries or subqueries for:

```text
Pending count
Resolved count
Has Pending Remarks
```

## Migration Validation

Validate:

```text
SQLite
MySQL
Alembic upgrade
Fresh database
alembic check
```

## Documentation

Document the final rule:

> **Registrant Remarks are application-owned operational data and must persist across registration imports.**

Also document:

```text
New registration import
→ source data may update
→ remarks remain unchanged
→ remark statuses remain unchanged
```

## Phase 4 Exit Criteria

- [x] Pending remarks survive imports.
- [x] Resolved remarks survive imports.
- [x] Multiple remarks survive imports.
- [x] Repeated imports do not duplicate remarks.
- [x] New imported row IDs do not disconnect remarks.
- [x] Author/resolver metadata survives imports.
- [x] Attestation Status remains independent.
- [x] Security tests pass.
- [x] SQLite/MySQL validation passes.
- [x] Documentation is updated.

---

# Explicitly Out of Scope

Do not include:

- Payment Status changes
- payment notes
- monetary fields
- Attestation Status redesign
- Attestation Form redesign
- remark attachments
- @mentions
- email notifications
- Slack notifications
- rich-text editor
- reactions
- global comment threads
- header redesign
- sidebar redesign
- unrelated dashboard changes

---

# Final Architecture

```text
                  STABLE PARTICIPANT
                         │
             ┌───────────┴───────────┐
             │                       │
             ▼                       ▼
   ATTESTATION VERIFICATION     REGISTRANT REMARKS
             │                       │
       one current status       many persistent notes
             │                       │
             ▼                       ▼
     survives imports          survives imports
```

Repeated uploads:

```text
Import #1 ─┐
Import #2 ─┼──> Stable Participant
Import #3 ─┘            │
                        ├── Attestation Status
                        └── Remarks
```

The import layer may change.

The application-owned operational data remains.

---

# Final Acceptance Criteria

- [x] Users can add remarks to a participant.
- [x] Each new remark starts as Pending.
- [x] Pending remarks can be marked Resolved.
- [x] Multiple remarks can exist for one participant.
- [x] Remarks are stored independently from imported registration rows.
- [x] Importing an updated file does not delete remarks.
- [x] Importing an updated file does not reset remark statuses.
- [x] Importing an updated file does not duplicate remarks.
- [x] A replacement `registrants.id` does not disconnect remarks.
- [x] Resolved By and Resolved At survive imports.
- [x] Created By and Created At survive imports.
- [x] Attestation Status remains independent and preserved.
- [x] Payment Status is untouched.
- [x] Authorization and CSRF protections remain intact.
- [x] SQLite and MySQL validation pass.
- [x] Technical documentation reflects the persistent ownership model.

---

# Implementation Sequence

```text
PHASE 1
Inspect Database + Stable Participant Ownership
        ↓
PHASE 2
Create Persistent Remarks Model + API
        ↓
PHASE 3
Registrations UI + Import Preservation
        ↓
PHASE 4
Regression Tests + Integrity + Documentation
```

## Governing Principle

> **Imports update registration-source data. They must never erase or reset operational remarks already created for that participant.**
