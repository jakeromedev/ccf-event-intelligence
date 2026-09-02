# Sync Registration Satellites — Feature Plan

## Purpose

Add a new **Sync Registration Satellites** feature to the Satellite Settings module.

The feature will reconcile registration-derived Satellite evidence with the configured canonical Satellite directory for the currently selected Event.

The sync must be conservative:

- it must **not create new Hub or Satellite records**;
- it must **not create duplicate relationships**;
- records that are already correctly linked must be skipped;
- records that cannot be matched must remain unchanged;
- the interface must show which registrations were not synchronized and why;
- imported registration evidence must remain unchanged.

This feature builds on the existing hierarchy:

```text
Hub Group
└── Hub
    └── Satellite
```

and the existing relationship:

```text
satellites.directory_id
    ↓
satellite_directory.id
```

The sync operation only reconciles imported Satellite evidence to an existing canonical `satellite_directory` record.

---

# Core Feature

Add a new control to Satellite Settings:

```text
Sync Registration Satellites
```

The action is available only when Satellite Settings is opened with Event context:

```text
/satellites/settings?event_id=<event_id>
```

If no `event_id` is available, the button must not be shown or must remain unavailable.

The feature must use the current Event as the synchronization scope.

---

# Registration Satellite Resolution

The registration export does not contain one universal Satellite field.

The source Hub is determined first from:

```text
Bg Satellite Hub
```

The corresponding Satellite value must then be read from the appropriate registration field.

Expected mapping:

| `Bg Satellite Hub` | Satellite source field |
| --- | --- |
| Luzon North Central | `Luzon North Central Hub` |
| Luzon Central | `Luzon Central Hub` |
| Luzon North East | `Luzon North East Hub` |
| Luzon North West | `Luzon North West Hub` |
| Luzon South | `Luzon South Hub` |
| Mindanao South | `Mindanao South Hub` |
| Mindanao North | `Mindanao North Hub` |
| Visayas | `Visayas Hub` |
| ICP | `Specify Icp Hub` |

The configured Hub names must match the source Hub names used by the registration data.

Hub naming corrections such as:

```text
Mindanao North → North Mindanao
Mindanao South → South Mindanao
```

will be handled manually in Satellite Settings before synchronization.

The sync feature must therefore **not introduce automatic Hub aliases, fuzzy Hub matching, or translation rules**.

---

# Canonical Matching Rules

A registration Satellite may only be synchronized when the system finds an existing canonical Satellite under the expected configured Hub.

The effective canonical match is:

```text
Configured Hub
+
Normalized Satellite Name
```

Matching must follow the existing Satellite Settings normalization rules:

- Unicode NFKC normalization;
- trim leading and trailing whitespace;
- collapse repeated internal whitespace;
- case-insensitive comparison using the same normalization behavior already used by the module.

Do not use fuzzy matching.

Do not match a Satellite against a different Hub simply because its name is similar.

Example:

```text
Registration source:

Bg Satellite Hub = Mindanao South
Mindanao South Hub = B1G Tagum
```

After the administrator has aligned the configured Hub naming, the expected canonical path is:

```text
Outside Metro Manila Hubs
└── Mindanao South
    └── B1G Tagum
```

Only an existing `B1G Tagum` record under the expected Hub may be used.

---

# Sync Behavior

The sync operation must never create directory records.

Possible results are:

| Status | Meaning | Mutation |
| --- | --- | --- |
| Ready to Sync | Existing canonical Hub + Satellite match found | Update link |
| Already Synced | Imported Satellite already has a canonical directory link, including a different established assignment | Skip |
| Satellite Not Configured | Expected Hub exists but Satellite does not | Skip |
| Hub Not Found | Source Hub has no matching configured Hub | Skip |
| Missing Satellite | Registration has no usable Satellite value | Skip |
| Ambiguous | More than one valid interpretation exists | Skip |

The sync must never overwrite an established canonical assignment. Any
existing canonical link is reported as already synchronized.

---

# Duplicate and Existing Record Rules

Synchronization must be idempotent.

Running the same sync repeatedly must not create new records or duplicate associations.

Example:

```text
First Sync

100 source records scanned
75 synchronized
20 already synchronized
5 not synchronized
```

Running it again without changing source data or directory configuration should produce approximately:

```text
100 source records scanned
0 newly synchronized
95 already synchronized
5 not synchronized
```

For an imported `satellites` row whose `directory_id` already points to the correct canonical directory record:

```text
SKIP
```

Do not perform an unnecessary update.

Do not create another `satellites` row.

Do not create another `satellite_directory` row.

---

# Source Evidence Preservation

The synchronization operation must not rewrite imported evidence.

Do not change:

```text
satellites.name
satellites.normalized_name
satellites.event_id
satellites.batch_id
satellites.affiliation
satellites.affiliation_conflict
satellites.source_record_count
```

The intended mutation is limited to:

```text
satellites.directory_id
```

when an exact valid canonical match is found.

Legacy unassigned `satellite_directory` records must remain in the database.

The sync operation must not:

- delete legacy directory entries;
- merge directory entries;
- rename legacy entries;
- automatically assign legacy entries to Hubs.

Legacy-directory cleanup remains a separate data-curation concern.

---

# Sync Review Modal

Clicking **Sync Registration Satellites** must first open a review workflow.

Do not immediately modify the database.

Recommended modal structure:

```text
Sync Registration Satellites

Event
B1G19 Leadership Conference

Registration Satellite Scan

Source Satellite Records      167
Represented Registrations   3,199

Ready to Sync                  85
Already Synced                 60
Not Synced                     22

[Review Not Synced]
[Cancel] [Confirm Sync]
```

The exact counts depend on the selected Event.

The modal must clearly distinguish:

- records that will be updated;
- records already correct and therefore skipped;
- records that cannot be synchronized.

---

# Not Synced Registrations

The administrator must be able to see the registrations that were not synchronized.

This is a required part of the feature.

The review should provide a **Not Synced Registrations** section.

Recommended information:

| Field | Purpose |
| --- | --- |
| Registration identifier | Identify the source registration |
| Participant name | Help the administrator locate the registrant |
| Source Hub | Value derived from `Bg Satellite Hub` |
| Source Satellite | Satellite value from the corresponding Hub field |
| Reason | Why synchronization was skipped |

Possible reasons:

```text
Satellite Not Configured
Hub Not Found
Missing Satellite
Ambiguous Satellite
```

Example:

| Registration | Participant | Source Hub | Satellite | Reason |
| --- | --- | --- | --- | --- |
| 58279 | Juan Dela Cruz | Mindanao South | B1G Tagum | Satellite Not Configured |
| 58310 | Maria Santos | ICP | Singapore | Satellite Not Configured |
| 58321 | Pedro Reyes | — | — | Missing Satellite |

This list must be available before confirmation and after synchronization.

The feature should allow the administrator to understand exactly what must be corrected in Satellite Settings or registration source data before running the sync again.

---

# Registration-Level Visibility

The `satellites` table may represent multiple registrations through:

```text
source_record_count
```

The synchronization engine may continue performing reconciliation at the unique imported Satellite-evidence level for efficiency.

However, the UI requirement is registration-level visibility for failures.

Therefore:

```text
Sync processing
    ↓
unique Satellite evidence
```

may be used for matching and database updates, while:

```text
Not Synced Registrations
    ↓
individual source registration records
```

must be resolved for reporting.

This avoids thousands of identical database updates while still giving administrators the specific registrants affected by a failed match.

---

# Successful Sync Summary

After confirmation, display a result summary.

Example:

```text
Registration Satellite Sync Complete

85 Satellite records synchronized
60 already synchronized and skipped
22 could not be synchronized

Represented registrations synchronized: 1,742
Registrations requiring review: 34
```

Provide a visible action such as:

```text
View Not Synced Registrations
```

when failures exist.

If everything is synchronized:

```text
All eligible registration Satellites are synchronized.
```

---

# Transaction Safety

The server must revalidate the matches when the administrator confirms the sync.

The review screen must not be considered authoritative because the directory may have changed between review and confirmation.

At confirmation:

1. reload the selected Event;
2. reload relevant registration Satellite evidence;
3. resolve the expected Hub and Satellite again;
4. verify the canonical directory record still exists;
5. verify the current `directory_id`;
6. skip already-correct records;
7. skip existing links or unmatched records;
8. update only valid matches;
9. commit the transaction;
10. produce the final sync report.

Database failures must roll back the transaction and return a user-facing error.

---

# Access Control

Use the existing Satellite Settings capability:

```text
satellites.settings.manage
```

The sync review and sync confirmation routes must require this capability.

POST confirmation must use the application's existing CSRF protection.

The selected `event_id` must also be validated server-side.

---

# Recommended Routes

Add routes similar to:

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/satellites/settings/sync/review` | Scan the current Event and prepare synchronization results |
| POST | `/satellites/settings/sync/confirm` | Revalidate and perform the synchronization |

Both routes must preserve:

```text
event_id
```

through the workflow.

The existing POST/redirect/GET pattern should be preserved after confirmation.

---

# Phase 1 — Data Flow and Matching Foundation

## Goal

Establish the synchronization rules without changing production data.

## Scope

1. Review the registration/import schema used to recover:
   - registration identifier;
   - participant name;
   - `Bg Satellite Hub`;
   - corresponding Hub-specific Satellite field;
   - relationship between source registrations and `satellites` aggregation rows.

2. Implement a reusable resolver that returns:

```text
registration
source_hub
source_satellite
expected_hub
canonical_satellite
status
reason
```

3. Reuse existing Satellite Settings normalization logic.

4. Match only:

```text
configured Hub + normalized Satellite name
```

5. Do not add:
   - fuzzy matching;
   - automatic Hub aliasing;
   - automatic Satellite creation;
   - automatic Hub creation.

6. Define statuses:
   - Ready to Sync;
   - Already Synced;
   - Satellite Not Configured;
   - Hub Not Found;
   - Missing Satellite;
   - Ambiguous;

7. Add automated tests covering:
   - exact match;
   - case/whitespace normalization;
   - missing Hub;
   - missing Satellite;
   - Satellite under the wrong Hub;
   - already-synced link;
   - different existing link reported as already synced.

## Deliverable

A tested read-only sync analysis service capable of generating a synchronization plan for one Event.

---

# Phase 2 — Sync Review UI and Not-Synced Reporting

## Goal

Expose the synchronization analysis to administrators before allowing mutations.

## Scope

1. Add the **Sync Registration Satellites** button to Satellite Settings.

2. Only expose the action when an `event_id` is available.

3. Add the review route.

4. Add the review modal.

5. Show totals for:
   - source Satellite records;
   - represented registrations;
   - ready to sync;
   - already synced;
   - not synced.

6. Add a detailed **Not Synced Registrations** view.

7. Show for every unsynchronized registration:
   - registration identifier;
   - participant;
   - source Hub;
   - source Satellite;
   - reason.

8. Allow filtering the failure list by reason.

9. Ensure the UI clearly communicates:

```text
No new Hub or Satellite records will be created.
Already synchronized records will be skipped.
```

10. Verify responsive behavior, keyboard access, focus handling, and dialog accessibility.

## Deliverable

A fully functional read-only synchronization review workflow with registration-level failure visibility.

---

# Phase 3 — Safe Synchronization Execution

## Goal

Enable administrators to commit valid matches without creating or duplicating records.

## Scope

1. Add the confirmation route.

2. Re-run matching on confirmation.

3. For `Ready to Sync` records:

```text
UPDATE satellites
SET directory_id = <canonical_directory_id>
```

4. For `Already Synced`:

```text
SKIP
```

5. For unmatched or invalid records:

```text
SKIP
```

6. For existing canonical links:

```text
SKIP
```

and include them in the final report.

7. Never:
   - create a Hub;
   - create a canonical Satellite;
   - create a new imported Satellite row;
   - delete a legacy directory record;
   - overwrite imported source evidence.

8. Make the operation idempotent.

9. Wrap mutations in a transaction.

10. Add integration tests covering:
    - successful synchronization;
    - repeated synchronization;
    - no duplicate creation;
    - already-synced skipping;
    - unmatched skipping;
    - existing-link protection and already-synced reporting;
    - rollback on database failure.

## Deliverable

A safe and idempotent Event-scoped synchronization operation.

---

# Phase 4 — Completion Reporting and Operational Hardening

## Goal

Make synchronization practical for repeated administrative use.

## Scope

1. Add final synchronization summary.

2. Report:
   - newly synchronized records;
   - already-synchronized records skipped;
   - not-synchronized records;
   - represented registration counts.

3. Preserve the detailed Not Synced Registrations report after confirmation.

4. Provide a clear path back to Satellite Settings so administrators can:
   - add missing Satellites manually;
   - correct Hub configuration;
   - correct naming;
   - run the sync again.

5. Add protection against:
   - concurrent directory edits;
   - stale review results;
   - deleted canonical records between review and confirmation;
   - duplicate submission.

6. Add logging for the synchronization operation, including:
   - Event;
   - administrator;
   - timestamp;
   - matched count;
   - skipped count;
   - failed count.

7. Update Satellite Settings documentation.

8. Run regression tests for:
   - Satellite rankings;
   - registrant drilldowns;
   - curation views;
   - Satellite Dataset selectors;
   - canonical rename/move behavior.

## Deliverable

A production-ready synchronization workflow with complete administrator feedback and regression coverage.

---

# Final Expected Workflow

```text
Satellite Settings
       ↓
Sync Registration Satellites
       ↓
Scan selected Event
       ↓
Resolve Hub + Satellite
       ↓
Match existing canonical directory
       ↓
┌─────────────────────────────┐
│ Ready to Sync               │
│ Already Synced              │
│ Not Synced                  │
└─────────────────────────────┘
       ↓
Review Not Synced Registrations
       ↓
Confirm Sync
       ↓
Revalidate
       ↓
Update valid directory_id links only
       ↓
Skip existing / unmatched records
       ↓
Final Sync Report
```

---

# Acceptance Criteria

The feature is complete when:

1. Satellite Settings contains a **Sync Registration Satellites** action for Event-scoped pages.
2. The feature scans the selected Event's registration Satellite evidence.
3. Matching requires an existing configured Hub and Satellite.
4. No Hub or Satellite is automatically created.
5. Existing correct links are skipped.
6. Re-running sync does not create duplicates.
7. Imported source evidence remains unchanged.
8. Only valid `satellites.directory_id` relationships are updated.
9. Unmatched and already-linked records remain unchanged.
10. Administrators can see the individual registrations that were not synchronized.
11. Every unsynchronized registration shows a clear reason.
12. Review occurs before mutation.
13. Confirmation revalidates the synchronization plan.
14. The operation is transaction-safe.
15. The final result summarizes synchronized, skipped, and not-synchronized records.
16. Existing Satellite analytics and canonical-directory behavior continue to work correctly.
