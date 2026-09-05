# Dashboard Satellite Targets and Category Reporting Update

## 1. Purpose

This document defines the updated implementation plan for simplifying Dashboard Satellite Targets and aligning them with the canonical Satellite hierarchy already used by the Satellite Overview and Satellite Settings modules.

The revised design removes the need for users to create arbitrary Satellite Target datasets from the Dashboard. Instead, the system will use three fixed reporting categories:

1. **Outside Metro Manila Hubs**
2. **Within Metro Manila Hubs**
3. **Main**

The responsibilities of the system will be separated clearly:

```text
Satellite Settings
    defines which canonical Satellites belong to each reporting category

Dashboard
    stores only the numeric participant target for each reporting category
    and displays Target vs Actual

Satellites Page
    displays a high-level registration distribution across the same three categories
```

The existing canonical Satellite and effective-assignment logic must remain authoritative. No new independent interpretation of Satellite membership should be introduced.

---

## 2. Updated Product Direction

### Previous Dashboard Target workflow

The current or previously planned workflow allowed users to:

- create a named Satellite Target dataset;
- select individual Satellites from the Dashboard;
- configure a participant target;
- maintain Target membership from the Dashboard itself.

This is being replaced.

### New workflow

The new workflow has only three fixed target categories:

```text
Outside Metro Manila Hubs
Within Metro Manila Hubs
Main
```

Users will no longer select Target Satellites from the Dashboard.

Instead:

```text
Satellite Settings
    ↓
Configure which canonical Satellites belong to each fixed category
    ↓
Dashboard
    ↓
Encode only 3 numeric participant targets
    ↓
Display Target vs Actual for all 3 categories
```

This keeps configuration logic in Satellite Settings and analytics/performance logic in the Dashboard.

---

## 3. Core Architecture

The canonical hierarchy remains:

```text
Event
└── Active Import Batch
    └── Curated Registrant
        └── Effective Satellite Association
            └── Canonical Satellite (`satellite_directory`)
                └── Hub (`satellite_hubs`)
                    └── Hub Group (`hub_groups`)
```

The reporting-category layer is added above canonical Satellite membership:

```text
Canonical Satellite
        ↓
Dashboard Reporting Category
        ↓
Outside Metro Manila Hubs
Within Metro Manila Hubs
Main
```

A Dashboard Target should never depend directly on imported `satellites.id` values.

Target category membership must use canonical:

```text
satellite_directory.id
```

This ensures membership survives:

- active-batch replacement;
- canonical Satellite renames;
- canonical Satellite movement between Hubs;
- manual registrant Satellite reassignment;
- historical batch reactivation.

---

## 4. Fixed Reporting Categories

The system will support exactly three Target/reporting categories.

| Category Key | Display Name |
|---|---|
| `outside_metro_manila` | Outside Metro Manila Hubs |
| `within_metro_manila` | Within Metro Manila Hubs |
| `main` | Main |

These are system-defined categories and should not be freely renamed or duplicated from the normal user interface.

The user should not create custom Target dataset names for this feature.

---

## 5. Satellite Settings Responsibilities

Satellite Settings becomes the authoritative configuration location for determining which canonical Satellites belong to each reporting category.

A new section should be added to the Satellite Settings page:

```text
Dashboard Target Satellites
```

This section should show all three categories and allow authorized users to manage their canonical Satellite membership.

### Example

```text
Dashboard Target Satellites

Outside Metro Manila Hubs
    [✓] B1G Singapore
    [✓] B1G Malaysia
    [✓] B1G Thailand

Within Metro Manila Hubs
    [✓] B1G Makati
    [✓] B1G Pasig
    [✓] B1G Quezon City

Main
    [✓] Main
```

### Required behavior

The Settings page should support:

- canonical Satellite search;
- Hub filtering;
- Hub Group filtering;
- assignment to one of the three reporting categories;
- bulk assignment where appropriate;
- selected count per category;
- clear display of canonical Satellite, Hub, and Hub Group context;
- server-side validation;
- safe saving without partially replacing data after a failed request.

### Recommended exclusivity rule

By default, a canonical Satellite should belong to only one Dashboard reporting category for a given Event.

Recommended constraint:

```text
UNIQUE(event_id, directory_id)
```

This prevents the same canonical Satellite from being simultaneously classified as Outside, Within, and Main.

If future business rules require overlapping category membership, this constraint can be relaxed, but the counting behavior must then be explicitly defined.

---

## 6. Dashboard Responsibilities

The Dashboard should no longer manage Satellite selection.

It should only manage the participant target value for each of the three fixed categories.

### Target Settings UI

The Dashboard target configuration should contain exactly three numeric inputs:

```text
Set Satellite Targets

Outside Metro Manila Hubs
[ 500 ]

Within Metro Manila Hubs
[ 750 ]

Main
[ 1200 ]

[ Cancel ] [ Save Targets ]
```

Although visually these may be textfield-style controls, they should use numeric validation.

### Validation

Each target must:

- be a whole number;
- be greater than or equal to 0;
- be less than or equal to 1,000,000,000;
- reject non-numeric values;
- be validated server-side.

Existing rule:

```text
0 = target not configured
```

For a target of zero:

```text
target_configured = false
progress_percentage = null
remaining_slots = null
target_exceeded = false
```

---

## 7. Effective Satellite Assignment Must Remain Authoritative

The existing effective Satellite logic remains unchanged and must be reused by both Dashboard and Satellite Overview analytics.

Conceptually:

```text
effective_directory_id =
    COALESCE(
        manual_assignment.directory_id,
        imported_satellite.directory_id
    )
```

Priority:

```text
Manual Event Satellite assignment
        >
Imported canonical Satellite mapping
```

Example:

```text
Imported association:
John → Satellite A

Manual assignment:
John → Satellite B
```

If Satellite A is in Outside and Satellite B is in Main, John must count under Main immediately.

The import file itself must not be modified to achieve this behavior.

---

## 8. Dashboard Actual Participant Counting

Each category's Actual value should be calculated using the canonical Satellite IDs configured for that category in Satellite Settings.

Conceptually:

```sql
WITH effective_associations AS (...shared effective association query...)
SELECT COUNT(DISTINCT curated.id)
FROM effective_associations association
JOIN curated_registrants curated
  ON curated.id = association.curated_registrant_id
 AND curated.event_id = association.event_id
 AND curated.batch_id = association.batch_id
WHERE association.event_id = :event_id
  AND association.batch_id = :active_batch_id
  AND association.directory_id IN (:category_directory_ids)
  AND curated.registration_type = 'participant';
```

### Required counting rules

Dashboard Target actuals must:

- count distinct curated participants;
- exclude volunteers;
- use only the active Event batch;
- honor manual assignments;
- deduplicate the same participant across multiple Satellites inside the same category;
- ignore attendance/check-in status;
- not use raw registration row counts;
- not use `satellites.source_record_count`;
- not depend on Local/International imported affiliation labels.

### Example

If a category contains:

```text
Satellite A = 100 participants
Satellite B = 80 participants
30 participants belong to both
```

The category Actual is:

```text
150 unique participants
```

not 180.

---

## 9. Dashboard Target vs Actual Graph

The Dashboard should display one grouped bar chart comparing Target and Actual for all three categories.

The categories are fixed:

```text
Outside Metro Manila Hubs
Within Metro Manila Hubs
Main
```

Each category should display two values:

```text
Target
Actual
```

### Example dataset

| Category | Target | Actual |
|---|---:|---:|
| Outside Metro Manila Hubs | 500 | 432 |
| Within Metro Manila Hubs | 750 | 681 |
| Main | 1,000 | 1,041 |

### Visualization behavior

The chart should:

- use grouped bars rather than stacked bars;
- display Target and Actual side by side;
- preserve all three categories even when their count is zero;
- clearly label the measured unit as participants;
- use server-calculated values;
- support actual values exceeding Target values.

The visual bar can remain uncapped because grouped bars should accurately represent magnitude.

---

## 10. Dashboard Category Summary Cards

The grouped chart should be supported by concise category summary cards.

Each category can expose:

```text
Actual Participants
Participant Target
Progress Percentage
Remaining Slots
Exceeded Amount / Target Exceeded State
```

### Progress formulas

For target > 0:

```text
progress_percentage = actual_participants / participant_target * 100
remaining_slots = MAX(participant_target - actual_participants, 0)
target_exceeded = actual_participants > participant_target
```

If Actual exceeds Target:

```text
actual = 1,041
target = 1,000
progress = 104.1%
remaining = 0
target_exceeded = true
exceeded_amount = 41
```

---

## 11. Satellites Page Registration Distribution Pie Chart

The Satellites page should display one high-level pie chart covering the same three reporting categories.

The chart should show:

```text
Outside Metro Manila Hubs
Within Metro Manila Hubs
Main
```

Recommended title:

```text
Registration Distribution by Target Category
```

Recommended subtitle:

```text
Based on effective Satellite associations in the active Event batch.
```

### Recommended measure

For the pie chart, use effective registrant-to-Satellite association counts unless category membership and effective participant membership are guaranteed to be mutually exclusive.

Formula:

```text
Category share =
Category effective associations
──────────────────────────────
All effective associations across the 3 reporting categories
× 100
```

This keeps the pie chart mathematically valid even if one curated person has multiple effective Satellite associations.

### Important distinction

Dashboard Target actuals use:

```text
COUNT(DISTINCT curated_registrant.id)
```

The Satellites page pie should use:

```text
COUNT(effective_association.id)
```

unless future rules guarantee one exclusive reporting category per person.

The UI should avoid implying that pie slices represent mutually exclusive unique people when that is not guaranteed.

---

## 12. Satellites Page Layout Update

The Satellites page should retain its existing canonical analytics and add the new category pie at a high-level position.

Recommended layout:

```text
Satellite Overview

[ Linked Registrants ] [ Hubs Represented ] [ Satellites Represented ] [ Needs Mapping ]

Registration Distribution by Target Category
┌───────────────────────────────────────────────┐
│                    Pie Chart                  │
│                                               │
│ Outside Metro Manila Hubs                     │
│ Within Metro Manila Hubs                      │
│ Main                                          │
└───────────────────────────────────────────────┘

Satellite Ranking
[ Existing ranking chart ]

Hub / Satellite hierarchy and table
[ Existing analytics ]
```

The new pie chart should be a high-level summary and should not replace the deeper canonical Satellite ranking and hierarchy analytics.

---

## 13. Recommended Database Design

The previous arbitrary `satellite_datasets` concept should not remain the primary user-facing model for this simplified feature.

A fixed category-based model is recommended.

### Category targets

Example:

```text
event_satellite_target_categories
```

Suggested fields:

| Field | Meaning |
|---|---|
| `id` | Primary key |
| `event_id` | Event ownership |
| `category_key` | One of the 3 fixed category keys |
| `participant_target` | Dashboard numeric Target |
| `created_at` | Audit timestamp |
| `updated_at` | Audit timestamp |

Recommended constraint:

```text
UNIQUE(event_id, category_key)
```

### Category Satellite membership

Example:

```text
event_satellite_target_satellites
```

Suggested fields:

| Field | Meaning |
|---|---|
| `id` | Primary key |
| `event_id` | Event ownership |
| `category_key` | Fixed category |
| `directory_id` | Canonical `satellite_directory.id` |
| `created_at` | Audit timestamp |

Recommended constraints:

```text
UNIQUE(event_id, category_key, directory_id)
```

and, if categories are exclusive:

```text
UNIQUE(event_id, directory_id)
```

### Optional migration path

If existing `satellite_datasets` rows already contain useful production data, migration should:

1. preserve current Target values where possible;
2. convert durable selections to canonical `directory_id` values;
3. map old named datasets to the new fixed categories only when the mapping is explicit;
4. avoid guessing category membership from imported names;
5. retain a rollback-safe migration path.

---

## 14. Category Configuration Rules

Only fully mapped canonical Satellites should be assignable to Dashboard reporting categories.

Required path:

```text
satellite_directory
→ satellite_hubs
→ hub_groups
```

Unmapped imported evidence should remain under Needs Mapping and should not be silently assigned to a reporting category.

### Missing Satellite evidence

If a raw registration contains a Hub response but no usable Satellite name:

- do not infer a canonical Satellite;
- do not assign it to Outside, Within, or Main;
- continue treating it as missing Satellite evidence until explicitly resolved.

---

## 15. Active Batch Behavior

All Actual calculations and pie-chart distributions must use exactly one active batch per Event.

Rules:

- inactive batches do not contribute;
- historical batches do not contribute unless they become active again;
- cross-Event data never contributes;
- category membership configuration persists regardless of active batch;
- Target values persist regardless of active batch.

### No active batch

If no active batch exists:

- keep saved category configuration;
- keep saved Target values;
- Dashboard Actuals should be 0;
- progress should follow the existing Target rules;
- Satellites page pie should show an empty/no-active-dataset state rather than misleading percentages.

### Selected Satellite absent from active batch

If a canonical Satellite is configured under a category but not represented in the current active batch:

- keep the category membership;
- contribute zero current participants/associations;
- optionally mark it as unavailable in the Settings UI;
- automatically resume counting if it is represented again in a later active batch.

---

## 16. Permissions and Mutation Safety

Existing Event mutation rules should remain enforced.

Required protections:

- authenticated Event access;
- Event mutation permission for category and target updates;
- CSRF protection;
- server-side validation of all IDs;
- canonical Satellite validation;
- Event-scoped configuration lookup;
- atomic saving;
- rejection of cross-Event IDs.

A failed request must not partially replace category membership or Target values.

Client-side controls are not an authorization boundary.

---

## 17. Recommended API / Response Contract

A simplified Dashboard response can expose exactly three category objects.

Example:

```json
{
  "satellite_target_categories": [
    {
      "key": "outside_metro_manila",
      "name": "Outside Metro Manila Hubs",
      "participant_target": 500,
      "target_configured": true,
      "actual_participants": 432,
      "progress_percentage": 86.4,
      "remaining_slots": 68,
      "target_exceeded": false,
      "exceeded_amount": 0,
      "satellite_count": 18
    },
    {
      "key": "within_metro_manila",
      "name": "Within Metro Manila Hubs",
      "participant_target": 750,
      "target_configured": true,
      "actual_participants": 681,
      "progress_percentage": 90.8,
      "remaining_slots": 69,
      "target_exceeded": false,
      "exceeded_amount": 0,
      "satellite_count": 24
    },
    {
      "key": "main",
      "name": "Main",
      "participant_target": 1000,
      "target_configured": true,
      "actual_participants": 1041,
      "progress_percentage": 104.1,
      "remaining_slots": 0,
      "target_exceeded": true,
      "exceeded_amount": 41,
      "satellite_count": 1
    }
  ]
}
```

No participant contact information should be included in this response.

---

## 18. Edge Cases

The implementation must define and test at least the following:

1. No active batch: preserve configuration, Actual = 0.
2. Target value is zero: show Target not configured state.
3. Actual exceeds Target: remaining = 0 and exceeded state is true.
4. Same participant appears under two Satellites in one category: count once in Dashboard Actual.
5. Participant appears under Satellites in two categories: behavior must follow the category exclusivity rules and effective assignments.
6. Volunteer belongs to a configured Satellite: exclude from Dashboard Target Actual.
7. Manual assignment moves a participant into another category: update counts immediately.
8. Manual assignment moves a participant out of a category: remove from that Actual immediately.
9. Canonical Satellite rename: configuration survives.
10. Canonical Satellite moved to another Hub: configuration survives.
11. Canonical Satellite absent from current active batch: keep membership, count zero.
12. Satellite returns in later batch: counting resumes automatically.
13. Imported Satellite is unmapped: cannot be configured as a Target category member.
14. Missing Satellite response: do not infer category.
15. Cross-Event canonical Satellite ID: reject request.
16. Duplicate category assignment where exclusivity is enabled: reject request.
17. Failed bulk category save: preserve previous complete configuration.
18. Search/filter in Settings returns no visible Satellites: do not remove hidden selections.
19. Historical batch reactivation: recalculate all three category Actuals and pie data.
20. Empty category: Target may remain configured, Actual = 0.

---

# 19. Implementation Phases

## Phase 1 — Data Model and Canonical Category Foundation

### Goal

Create the durable Event-level configuration needed for the three fixed reporting categories and remove dependency on batch-specific Satellite IDs for Target membership.

### Scope

1. Review the current schema for:
   - `satellite_datasets`;
   - `satellite_dataset_satellites`;
   - `satellite_directory`;
   - `satellite_hubs`;
   - `hub_groups`;
   - Event ownership and cascade behavior.

2. Introduce or migrate to fixed category Target storage:
   - `outside_metro_manila`;
   - `within_metro_manila`;
   - `main`.

3. Introduce canonical category membership based on:

   ```text
   satellite_directory.id
   ```

4. Add database constraints for:
   - one target row per Event/category;
   - no duplicate Satellite within a category;
   - optional one-category-per-Satellite exclusivity.

5. Preserve current Event ownership, permissions, and cascade rules.

6. Define migration handling for any existing Dashboard Satellite Target data.

7. Retain one shared effective-association query/CTE as the canonical analytics source.

### Deliverables

- final schema or migration;
- canonical fixed category keys;
- Event-scoped category membership model;
- migration compatibility strategy;
- baseline automated tests.

### Acceptance criteria

- Target membership no longer requires imported `satellites.id` as durable identity;
- canonical Satellite IDs survive active-batch replacement;
- no cross-Event category membership is possible;
- existing manual-assignment semantics remain intact.

---

## Phase 2 — Satellite Settings Category Configuration

### Goal

Move all Satellite Target membership configuration out of the Dashboard and into Satellite Settings.

### Scope

1. Add a new **Dashboard Target Satellites** section in Satellite Settings.

2. Display all three fixed categories:
   - Outside Metro Manila Hubs;
   - Within Metro Manila Hubs;
   - Main.

3. Allow authorized users to assign canonical Satellites to categories.

4. Provide:
   - Satellite search;
   - Hub Group filter;
   - Hub filter;
   - canonical Satellite context;
   - selected count per category;
   - clear unavailable or unmapped state;
   - bulk selection/assignment where practical.

5. Preserve hidden selections when search/filter results change.

6. Prevent unmapped imported evidence from being selected.

7. Enforce one-category-per-Satellite if the exclusivity rule is adopted.

8. Save category membership atomically.

### Deliverables

- Satellite Settings Target configuration UI;
- canonical category assignment endpoints/services;
- validation and permissions;
- migration-aware existing-data handling;
- Settings regression tests.

### Acceptance criteria

- Dashboard no longer needs a Satellite selector;
- all category membership is configured from Satellite Settings;
- category selections survive import replacement and canonical renames;
- invalid/cross-Event selections cannot be saved;
- filtering never silently removes configured members.

---

## Phase 3 — Dashboard Three-Field Targets and Target vs Actual Graph

### Goal

Simplify the Dashboard Target experience to exactly three numeric target inputs and one Target-vs-Actual comparison visualization.

### Scope

1. Remove the user-facing arbitrary Satellite Dataset workflow from the Dashboard.

2. Replace it with exactly three numeric target fields:
   - Outside Metro Manila Hubs;
   - Within Metro Manila Hubs;
   - Main.

3. Preserve validation:
   - integer only;
   - 0 to 1,000,000,000;
   - server-side validation;
   - zero means unconfigured.

4. Calculate Actual Participants using:
   - active Event batch;
   - effective Satellite associations;
   - configured canonical category membership;
   - `registration_type = 'participant'`;
   - `COUNT(DISTINCT curated_registrant.id)`.

5. Add one grouped bar chart:

   ```text
   Outside Metro Manila Hubs: Target vs Actual
   Within Metro Manila Hubs: Target vs Actual
   Main: Target vs Actual
   ```

6. Add concise summary values/cards for:
   - Actual;
   - Target;
   - progress percentage;
   - remaining slots;
   - exceeded state/amount.

7. Remove attendance and check-in dependencies from this reporting feature.

### Deliverables

- simplified Target modal/form;
- server-side category Actual metrics;
- grouped Target-vs-Actual chart;
- updated Dashboard response contract;
- Dashboard regression tests.

### Acceptance criteria

- only three Target fields are editable from Dashboard;
- Satellite membership cannot be changed from Dashboard;
- Actual participant counts reconcile to effective canonical assignments;
- volunteers are excluded;
- duplicate participants inside a category are counted once;
- manual assignment changes affect Dashboard immediately.

---

## Phase 4 — Satellites Page Category Pie, Reconciliation, and Regression Coverage

### Goal

Add the high-level three-category registration distribution to the Satellites page and complete full cross-module reconciliation.

### Scope

1. Add one pie chart to the Satellites page for:
   - Outside Metro Manila Hubs;
   - Within Metro Manila Hubs;
   - Main.

2. Base the pie on effective Satellite associations unless future exclusivity rules guarantee a true unique-person partition.

3. Label the pie clearly as an effective Satellite association distribution.

4. Preserve existing Satellite Overview:
   - KPIs;
   - Satellite ranking;
   - Hub distribution;
   - canonical hierarchy;
   - Needs Mapping behavior.

5. Ensure the new high-level category summary does not include unmapped evidence.

6. Add reconciliation tests across:
   - Satellite Settings membership;
   - Dashboard category Actuals;
   - Dashboard Target values;
   - Satellites page category distribution;
   - manual assignments;
   - active-batch changes.

7. Verify edge cases and migration behavior.

### Deliverables

- three-category pie chart;
- shared category analytics service/query;
- end-to-end tests;
- final cleanup of legacy user-facing Dashboard Dataset selection where safe.

### Acceptance criteria

- the Satellites page pie and Dashboard use the same configured category membership;
- Dashboard Actuals use distinct participants;
- pie shares use the documented association denominator;
- manual assignment changes reconcile across all modules;
- no inactive or cross-Event data contributes;
- Needs Mapping remains excluded and visible separately;
- no attendance/check-in logic is introduced.

---

## 20. Recommended Phase Dependency

```text
Phase 1
Canonical category data model
        ↓
Phase 2
Satellite Settings category membership
        ↓
Phase 3
Dashboard three-field targets + Target vs Actual
        ↓
Phase 4
Satellites page pie + reconciliation + regression hardening
```

Phase 1 is foundational. Phases 2 and 3 should not independently invent category logic.

The implementation should centralize category membership and effective-association calculations so both Dashboard and Satellite Overview consume the same source of truth.

---

## 21. Final Acceptance Criteria

The update is complete only when all of the following are true:

- there are exactly three fixed reporting categories;
- Target Satellite membership is managed from Satellite Settings;
- Dashboard contains exactly three participant Target inputs;
- Dashboard no longer requires users to create arbitrary Target datasets;
- canonical `satellite_directory.id` is the durable membership identity;
- Dashboard Actuals count distinct participants only;
- volunteers are excluded from Dashboard Actuals;
- manual Satellite assignments immediately affect category counts;
- Target membership survives import replacement and canonical renames;
- Dashboard displays one Target-vs-Actual graph for all three categories;
- Satellites page displays one pie chart for the same three categories;
- pie distribution excludes unmapped evidence;
- category membership and Dashboard Target values remain Event-scoped;
- inactive and cross-Event batches never contribute;
- failed saves are atomic;
- permissions and CSRF remain enforced;
- no attendance or check-in logic is introduced into these Target calculations.
