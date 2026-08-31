# Attestation Status Import Preservation — Phase 1 Assessment

Status: **Phase 1 complete (analysis and reproduction only)**
Assessed: 2026-08-31

This assessment implements Phase 1 of
`ATTESTATION_STATUS_IMPORT_PRESERVATION_PLAN.md`. It does not change production
Attestation Status behavior and does not add a migration.

## Decision summary

`import_batches.id` is **a technical file-import execution (Case B)**, not a
stable logical registration batch. Every validated three-file upload creates a
new row. Processing inserts a new set of buyers, tickets, registrants, and
curated rows under that ID, makes it active, and makes the prior active run
inactive.

The only existing scope that survives those replacement imports is
`events.id`. The application consistently treats an Event as the ownership and
authorization boundary and permits one active import dataset per Event.

Neither `registrants.id` nor `curated_registrants.id` is a stable participant
identity:

- `registrants.id` is recreated for every import run;
- curation is rebuilt per batch and `curated_registrants.id` is recreated;
- curated uniqueness is `(batch_id, dedupe_key)`, so it cannot identify one
  participant across runs;
- the curated match key is based on mutable demographic fields and incomplete
  records deliberately receive a row-ID-based key.

The safest target is therefore an Event-scoped stable participant entity and
one verification per Event/participant:

```text
events.id (current logical registration scope)
    +
stable_participants.id (new durable participant identity)
    -> UNIQUE(event_id, stable_participant_id)
       in attestation_verifications
```

If the product later needs multiple independent registration lifecycles inside
one Event, that scope must become an explicit durable `logical_batch_id`. It
must not reuse `import_batches.id`.

## Current relationships

```text
events
  id
   |
   +--< import_batches                         one row per upload run
          id, event_id
          |
          +--< registrants                     recreated per run
          |      id, batch_id
          |       |
          |       +--0..1 attestation_verifications
          |              registrant_id UNIQUE
          |
          +--< curated_registrants             rebuilt per run
                 id, event_id, batch_id
                  |
                  +--< curated_registrant_sources >-- registrants

users --0..1< attestation_verifications.updated_by_user_id
```

The attestation join is exactly:

```sql
LEFT JOIN attestation_verifications verification
  ON verification.registrant_id = record.id
```

## Relevant schema inventory

The application uses SQLAlchemy model metadata as the current schema contract;
Alembic migration `b7e4c1a9d306` creates the attestation table. All IDs below
are numeric primary keys. Timestamps are database-generated unless noted.

### `events`

- Columns: `id`, `name`, nullable `event_date`, nullable
  `participant_target`, `created_at`, `updated_at`.
- Constraint: participant target is null or non-negative.
- Foreign keys, unique constraints, and secondary indexes: none.
- Deletion: an Event cascades to its import batches; their children then
  cascade.
- Role: durable operational and authorization scope.

### `import_batches`

- Columns: `id`, non-null `event_id`, nullable source `event_slug` and
  `event_name`, non-null `status`, nullable `active_event_id`, `created_at`,
  nullable `processed_at`, nullable `activated_at`, nullable `error_message`.
- Foreign key: `event_id -> events.id ON DELETE CASCADE`.
- Unique constraints: `(event_id, id)` and nullable `active_event_id`.
- Check constraints: lifecycle status allow-list; an active row must set
  `active_event_id = event_id`, while every non-active row must leave it null.
- Index: `(event_id, created_at)`.
- Meaning: one complete uploaded export set and its processing lifecycle.
  There may be many rows for one Event, but only one active row.

### `registrants`

- Columns: `id`, non-null `batch_id`, source identifiers and raw profile
  fields, derived affiliation/satellite/type/check-in fields, and
  `source_data_json`. It has no created/updated timestamp.
- Nullable fields include source ID/slug, names, raw demographic/affiliation
  values, satellite name, and source JSON. Batch and registration/ticket codes,
  derived status fields, and boolean presence/match flags are non-null.
- Foreign key: `batch_id -> import_batches.id ON DELETE CASCADE`.
- Unique constraints: `(batch_id, id)`, `(batch_id, registration_code)`, and
  `(batch_id, ticket_code)`.
- Indexes: batch-scoped affiliation/check-in, registration type, gender, and
  ticket status indexes.
- Identity implication: source identifiers are only constrained inside one
  technical run. No database contract maps them across runs.

### `attestation_verifications`

- Columns: `id`, non-null `registrant_id`, non-null `status` defaulting to
  `pending`, nullable `updated_by_user_id`, `created_at`, and `updated_at`.
- Foreign keys:
  - `registrant_id -> registrants.id ON DELETE CASCADE`;
  - `updated_by_user_id -> users.id ON DELETE SET NULL`.
- Unique constraint: `registrant_id`.
- Check constraint: status is `pending`, `verified`, or `invalid`.
- Indexes: `status` and `updated_by_user_id`.
- Row lifecycle: import processing does not create a verification row. Absence
  means Pending. The PATCH operation inserts on first review and subsequently
  updates the one row, supplying the reviewer and an application-generated
  review timestamp. Deleting the source registrant or import batch deletes the
  verification; deleting the reviewer retains it and nulls attribution.

### `curated_registrants`

- Columns: `id`, non-null `event_id` and `batch_id`, normalized identity
  components, `dedupe_key`, completeness/status fields, resolved analytical
  fields, `created_at`, and `updated_at`.
- Nullable fields are the display and normalized identity components plus
  `missing_identity_fields`; ownership, keys, flags, resolved fields, and
  timestamps are non-null.
- Foreign key: `(event_id, batch_id) -> import_batches(event_id, id) ON DELETE
  CASCADE`.
- Unique constraints: `(batch_id, dedupe_key)` and `(event_id, batch_id, id)`.
- Indexes: `(batch_id, registration_type, checked_in)` and
  `(event_id, batch_id)`.
- Rebuild behavior: all curated registrants for the technical batch are
  deleted and inserted again whenever that batch's curation is rebuilt.

### `curated_registrant_sources`

- Columns: `id`, non-null `event_id`, `batch_id`, `curated_registrant_id`,
  `registrant_id`, and `created_at`.
- Nullable fields: none.
- Foreign keys: the curated side uses `(event_id, batch_id,
  curated_registrant_id)` and the raw side uses `(batch_id, registrant_id)`;
  both cascade on deletion.
- Unique constraints: `(curated_registrant_id, registrant_id)` and
  `(batch_id, registrant_id)`.
- Indexes: curated ID, registrant ID, and batch ID.
- Role: traceability inside one technical run, not a cross-run identity map.

### `users`

- Columns: `id`, non-null unique `username`, non-null password hash, role,
  status, auth version and failed-login count, nullable `approved_at`,
  `approved_by`, and `locked_until`, plus non-null `created_at` and
  `updated_at`.
- Foreign key: `approved_by -> users.id ON DELETE SET NULL`.
- Unique constraint: `username`.
- Index: `(status, created_at)`.
- Check constraints enforce the role/status allow-lists, the reserved approved
  administrator identity, approval timestamp consistency, and positive auth
  version/non-negative failed-login count.
- Attestation deletion behavior: reviewer deletion uses `SET NULL`, preserving
  the decision and timestamps.

### Import provenance and derived tables

- `import_files`: one row per export type with `UNIQUE(batch_id, export_type)`;
  deleting the batch cascades.
- `validation_issues`: validation and processing issues owned by a batch;
  deleting the batch cascades.
- `buyers` and `tickets`: newly inserted, batch-scoped source rows. Their
  source identifiers are unique only with `batch_id`.
- `satellites`, `satellite_source_variations`, and
  `curated_registrant_satellites`: derived, batch-scoped curation data rebuilt
  with the batch. None supplies stable participant identity.

## Import lifecycle

The observed code path is:

1. The upload route stages and validates all three exports.
2. `store_validation()` always inserts a new `import_batches` row, plus its
   files and issues. It does not look up or update a prior run.
3. `process_batch()` reads the staged files and inserts new buyers, tickets,
   and registrants using the new `batch_id`. It performs no cross-batch upsert.
4. `rebuild_batch_curation()` deletes/recreates derived curation for that
   technical run. It groups complete identities by normalized last name,
   birth month, birth year, and binary gender.
5. `_set_active_batch()` marks the previous active row inactive and the new
   row active. Historical source rows remain until an administrator deletes an
   inactive batch.

Thus an updated upload is a replacement active dataset, not an in-place update.

## Participant identity findings

The curated key is:

```text
normalized last name | normalized birth month | normalized birth year | gender
```

Normalization performs Unicode NFKC/whitespace cleanup, case-folds last name,
canonicalizes valid month names/numbers to `01`–`12`, accepts years
`1900`–`2100`, and accepts normalized male/female values. Any missing/invalid
component makes the identity incomplete; its key becomes
`incomplete:<registrants.id>` so it cannot merge with another source row.

Consequences:

- the same complete inputs produce the same key text in another import, but a
  new curated row and ID are still created because uniqueness is batch-scoped;
- changes to last name, birth month/year, or gender produce a different key;
- two different people sharing all four values collide into one curated group;
- incomplete identities cannot be matched across imports;
- email, mobile, first name, source ID, registration code, and ticket code are
  not part of curation matching.

This makes the curation layer useful for analytics but unsafe as the sole
application-owned attestation identity contract.

## Current Registrations behavior

All table rows, filters, sorts, and counts use the same left join by raw
`registrant_id`. `COALESCE(verification.status, 'pending')` drives the displayed
status, Pending summary, quick filter, sorting, and filtering. Reviewer name
and review timestamp come from the same optional verification row.

The review modal receives those row values. The PATCH endpoint validates Event
and selected batch ownership using the raw registrant, then updates/inserts by
`registrant_id`. It does not resolve a participant outside that import run.

## Automated bug reproduction

`RegistrationsIntegrationTests.test_reimport_preserves_reviewed_attestation_for_same_participant`
uses the real validation and processing path:

1. import Participant A in technical batch 1;
2. verify the absent-row Pending behavior;
3. create a Verified review for batch 1's raw registrant;
4. re-import the same source identifiers and demographic identity in technical
   batch 2 while changing Satellite;
5. confirm batch 2 and its registrant have new IDs and the imported Satellite
   changed;
6. require the active row to remain Verified.

The last assertion currently fails because the active registrant has no joined
verification and is therefore Pending. The test is marked
`@unittest.expectedFailure` for Phase 1 so it records the defect without making
the suite red. Phase 2 must remove that marker when the fix lands.

## Root cause

The application-owned status is stored against a technical import artifact:

```text
old attestation_verifications.registrant_id
    -> old registrants.id
    -> old inactive import_batches.id
```

After replacement import, the Registrations module reads:

```text
new active import_batches.id
    -> new registrants.id
    -> no attestation_verifications row
    -> COALESCE(..., 'pending')
```

Nothing copies the decision, and there is no durable participant key through
which the old and new records can resolve to one application-owned state.

## Proposed target state

Phase 2 should introduce a stable Event-scoped participant identity rather
than promoting a batch-local curated row ID. Conceptually:

```text
events
  +--< stable_participants
  |      UNIQUE(event_id, durable_identity_key)
  |
  +--< import_batches --< registrants
  |                         |
  |                         +-- mapping --> stable_participants
  |
  +--< attestation_verifications
         event_id, stable_participant_id, status, reviewer, timestamps
         UNIQUE(event_id, stable_participant_id)
```

The durable identity/mapping policy must explicitly handle changed identifiers,
incomplete records, and collisions. Automated matches must be conservative;
ambiguous records must not inherit another person's review. The current
curated demographic key may be one matching signal, but must not be the foreign
key or sole durable identity.

`registrant_id` can remain as optional provenance for the row most recently
reviewed, but it must not remain the ownership key.

## Phase 2 migration impact

- **Schema:** add the stable participant entity and source mappings; move
  attestation ownership to `(event_id, stable_participant_id)` (or an explicit
  durable logical scope if product requirements add one); replace
  `UNIQUE(registrant_id)` as the sole contract.
- **Backfill:** resolve existing verifications through registrant, batch, Event,
  and curation/source mappings. Detect and report ambiguous identities and
  conflicting historical decisions; do not silently merge them. Preserve
  reviewer and timestamps.
- **Importer:** resolve every new registrant to the stable participant mapping
  transactionally. Never create or reset a verification during import.
- **Queries:** join active registrants through the stable mapping to the one
  verification. Apply this consistently to rows, counts, filters, sorting,
  reviewer attribution, and the review modal.
- **PATCH endpoint:** resolve and upsert by stable participant and Event scope,
  while retaining current authorization, status allow-list, CSRF, and audit
  behavior.
- **Deletion:** deleting an inactive technical import must not delete stable
  participant verification. Event deletion should still cascade the complete
  lifecycle.
- **Tests:** convert the expected-failure reproduction to a passing regression;
  add Verified and Invalid preservation, imported field/form updates, collision
  and incomplete-identity isolation, repeated imports, inactive-batch deletion,
  reviewer deletion, authorization, counts/filters/sorting, and migration
  backfill/conflict coverage. Payment Status remains unchanged and out of scope.
