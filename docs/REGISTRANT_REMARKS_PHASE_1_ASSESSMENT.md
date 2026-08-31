# Registrant Remarks — Phase 1 Assessment

Status: **Phase 1 complete (assessment and planning only)**
Assessed: 2026-09-01

This assessment implements Phase 1 of
`REGISTRANT_REMARKS_FEATURE_PLAN (1).md`. It does not add a remarks table,
endpoint, importer mutation, or UI behavior.

## Decision summary

Remarks should use the same durable participant and logical scope already used
by Attestation Status:

```text
events.id
    +
attestation_participants.id
    -> one durable participant in one Event registration lifecycle
    -> many registrant_remarks
```

The recommended authoritative ownership key for each remark is therefore:

```text
(event_id, attestation_participant_id)
```

`import_batches.id`, `registrants.id`, and `curated_registrants.id` must not own
remarks. A registrant ID may be accepted by a row-oriented API only as a scoped
locator that the server resolves through `attestation_participant_registrants`.
It must not be stored as the remark's authoritative identity.

The current table name `attestation_participants` reflects the feature that
introduced it, but the row itself is now the application's durable
Event-scoped operational participant identity. Reusing it avoids parallel
identity systems that could disagree about whether two imports represent the
same participant. Renaming that established table is not required for Remarks.

## Current schema

### Logical and technical scope

- `events`: durable logical registration and authorization scope. Primary key
  `id`; deleting an Event cascades its complete registration lifecycle.
- `import_batches`: one technical three-file upload run. It belongs to an Event,
  has a lifecycle status, and only one run per Event is active. Every replacement
  upload creates a new ID; old processed runs become inactive.
- `registrants`: replaceable imported source rows owned by one technical batch.
  Registration code and ticket code are unique only within a batch. Deleting a
  batch cascades its registrants.

### Existing participant identity

- `attestation_participants`: durable identities owned by `events.id` with
  `UNIQUE(event_id, id)`. Rows survive deletion of individual import batches.
- `attestation_participant_identifiers`: Event-scoped exact normalized aliases
  for source ID, registration code, and ticket code. The database guarantees
  `UNIQUE(event_id, identifier_type, identifier_value)`.
- `attestation_participant_registrants`: maps each replaceable imported row to
  a durable participant. `(batch_id, registrant_id)` is unique and cascades with
  the source row; the durable participant does not.
- `curated_registrants`: analytical groups rebuilt inside one import batch.
  Its ID and uniqueness scope are batch-local, so it is not durable Remarks
  ownership.
- `curated_registrant_sources`: batch-local traceability from curated groups to
  imported registrants. It helps group duplicates during reconciliation but is
  not a cross-import identity.

### Existing application-owned review state

`attestation_verifications` already demonstrates the required ownership model:

```text
event_id + attestation_participant_id -> one current verification
```

Its unique constraint is `(event_id, attestation_participant_id)`. Reviewer
references use `ON DELETE SET NULL`; participant/Event deletion cascades the
state. Nullable `registrant_id` is only latest-review provenance. Registrations
reads join imported rows through `attestation_participant_registrants` to the
durable verification, so replacement row IDs do not reset status.

### Users

`users.id` is the application operator identity. User deletion can safely use
`SET NULL` for remark author/resolver references so the operational remark and
timestamps remain intact.

### Existing remarks or note structures

No implemented database or application structure currently stores registrant
remarks, notes, comments, administrative annotations, or remark status history.

- `import_history` is a computed view of import batches, not participant notes.
- `validation_issues` contains importer-generated data-quality findings, not
  operator-authored participant remarks.
- Data Quality annotation/resolution is only a deferred roadmap item.
- Attestation verification stores current state and attribution, not comments
  or a general history ledger.

There is consequently no existing Remarks data to migrate or backfill.

## Import lifecycle

The current import path is:

1. validate a complete buyers/tickets/registrants file set;
2. `store_validation()` inserts a new technical `import_batches` row;
3. `process_batch()` inserts new source-owned rows under that batch ID;
4. `rebuild_batch_curation()` recreates batch-local analytical groups;
5. `reconcile_attestation_participants()` maps every new registrant to the
   durable Event-scoped participant using exact normalized source aliases and
   same-run curated grouping;
6. activation makes the new run active and the previous run inactive.

The reconciliation step never updates `attestation_verifications`, and future
Remarks processing must follow the same rule: imports may add participant-to-
registrant mappings but must never insert, update, reset, copy, or delete
`registrant_remarks`.

If exact aliases in one source group resolve to multiple durable participants,
processing fails and retains the previous active batch. If all authoritative
aliases change, the row is conservatively treated as a new participant. These
existing identity behaviors will also govern Remarks.

## Logical scope decision

The logical Remarks scope is **Event + durable participant**.

An Event currently represents one registration lifecycle and can have many
technical import snapshots but only one active dataset. Remarks should follow
participants across all those snapshots. The same source identity imported
under a different Event resolves to a different durable participant and must
not share remarks.

No separate logical-batch table is required by the current product model. If
multiple independent registration lifecycles are later introduced inside one
Event, both Attestation and Remarks would need an explicit durable lifecycle
scope; `import_batches.id` would still be unsuitable.

## Recommended Phase 2 schema

Create `registrant_remarks`:

| Column | Rule |
|---|---|
| `id` | Numeric auto-increment primary key |
| `event_id` | Non-null durable Event scope |
| `attestation_participant_id` | Non-null durable participant owner |
| `remark` | Non-null text; trim and reject blank content; bounded by API validation |
| `status` | Non-null `pending`/`resolved`, default `pending` |
| `created_by_user_id` | Nullable FK to `users.id`; supplied by server |
| `resolved_by_user_id` | Nullable FK to `users.id`; supplied by server on resolution |
| `created_at` | Non-null server/application timestamp |
| `updated_at` | Non-null server/application timestamp |
| `resolved_at` | Null while Pending; non-null while Resolved |

Required constraints:

```text
(event_id, attestation_participant_id)
    -> attestation_participants(event_id, id) ON DELETE CASCADE

created_by_user_id -> users.id ON DELETE SET NULL
resolved_by_user_id -> users.id ON DELETE SET NULL

status IN ('pending', 'resolved')

(status = 'pending'  AND resolved_at IS NULL)
OR
(status = 'resolved' AND resolved_at IS NOT NULL)
```

`resolved_by_user_id` must be allowed to become null after resolver deletion,
so resolution consistency should rely on `resolved_at`, not require the user FK
to remain non-null. Multiple remarks intentionally have no uniqueness
constraint on text.

Recommended index:

```text
INDEX(event_id, attestation_participant_id, status, created_at)
```

This supports participant lists, Pending-first ordering, and aggregated counts.

## Recommended APIs and authorization

Keep the Registrations row-oriented route contract while resolving durable
ownership server-side:

```text
GET   /events/{event_id}/registrations/{registrant_id}/remarks
POST  /events/{event_id}/registrations/{registrant_id}/remarks
PATCH /events/{event_id}/registrations/{registrant_id}/remarks/{remark_id}
```

All routes should accept the existing `batch` scope convention. The server
must verify Event, selected batch, registrant, participant mapping, and—for
PATCH—the remark's `(event_id, participant_id)` ownership before reading or
writing. Never trust a participant ID or author/resolver ID from JSON.

Recommended first-release behavior:

- GET returns Pending first, then Resolved; newest first within each group.
- POST accepts only trimmed remark text, creates `pending`, attributes
  `current_user.id`, and uses a server timestamp.
- PATCH accepts only `resolved` for the initial release, supplies resolver and
  resolution time server-side, and does not edit remark text.
- Use a separate `can_edit_registrant_remarks` capability even if it initially
  grants the same administrator/Registration roles as Attestation editing. This
  keeps the two features independently governable.
- Retain current authentication, authorization, CSRF, and PII-safe logging
  boundaries.

## Required Registrations query changes

Add participant remark counts without joining raw remark rows into the base
table query. A raw one-to-many join would multiply Registrations rows, summary
counts, filters, and pagination.

Use a pre-aggregated subquery or CTE keyed by
`(event_id, attestation_participant_id)` that provides:

```text
pending_remark_count
resolved_remark_count
total_remark_count
```

Left join that single aggregate row after
`attestation_participant_registrants`. The UI may then render `No Remarks`,
`2 Pending`, or `1 Pending · 3 Resolved`. A `Has Pending Remarks` filter should
use the aggregate count and must retain source-row pagination semantics.

The modal should load full remark records through the scoped GET endpoint, not
embed every remark body in the paginated table payload.

## Migration and backfill

Phase 2 requires one Alembic revision that creates the table, constraints, and
index in both SQLite and MySQL. No data backfill is required because no current
remarks/note structure exists.

The migration must validate:

- fresh upgrade to head;
- upgrade from current revision `f3a8c2d9e401`;
- downgrade/re-upgrade;
- `alembic check`;
- Event/participant composite FK enforcement;
- status and resolution timestamp checks;
- user deletion preserving remarks through `SET NULL`.

The importer needs no remark-data migration or copy logic. Its only dependency
is that participant reconciliation continues to complete before batch
activation.

## Required tests

### Persistence and imports

- Pending, Resolved, and multiple remarks survive a replacement import.
- Three or more repeated imports neither duplicate nor delete remarks.
- Replacement `registrants.id` resolves the same remarks.
- A genuinely new participant starts with no remarks.
- Same source identity in another Event has independent remarks.
- Ambiguous identity import fails without changing remarks or active batch.
- Attestation Verified/Invalid state remains unchanged by remark operations,
  and remark state remains unchanged by Attestation operations.

### API and integrity

- Multiple remarks per participant are accepted.
- Blank/oversized text and invalid status transitions are rejected.
- Pending defaults and Pending-to-Resolved attribution/timestamps are correct.
- Database rejects invalid statuses and inconsistent resolution timestamps.
- Author/resolver deletion retains remark content, state, and timestamps.
- Cross-Event, cross-batch, manipulated registrant, participant, and remark IDs
  are rejected.
- Unauthenticated/unauthorized requests and missing CSRF are rejected.

### Query and UI

- Counts do not multiply table rows, summaries, or pagination.
- Active, historical, explicit, and all-batches scopes reconcile.
- Duplicate source rows for one participant show the same remark counts.
- Has-Pending filtering composes with existing filters and search.
- Modal ordering is Pending first/newest first and Resolved newest first.
- Empty, loading, validation-failure, save, and resolution UI states remain
  accessible.

## Phase 1 conclusion

The project already has the stable identity Remarks needs. Phase 2 should add
only the independent one-to-many `registrant_remarks` model and scoped backend
API. It should not alter imported source ownership, Attestation Status, Payment
Status, or the batch-local curation model.
