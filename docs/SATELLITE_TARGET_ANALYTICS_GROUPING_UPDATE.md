# Satellite Target Analytics Grouping Update

## Document Status

This document is a **new implementation update** that assumes the previously implemented Satellite Target and Category Reporting feature is already complete.

It does **not** replace the existing canonical Satellite classification, target configuration, or reporting logic. This update adds a new layer that allows the three existing base reporting categories to be **combined into shared analytics target groups**.

---

## 1. Purpose

The system currently uses three permanent Satellite reporting categories:

1. **Outside Metro Manila Hubs**
2. **Within Metro Manila Hubs**
3. **Main**

These categories remain the base classification of Satellites.

This update introduces an additional configuration layer so administrators can combine these base categories for Dashboard target reporting and high-level Satellite analytics.

Examples:

```text
Outside Metro Manila Hubs
+
Within Metro Manila Hubs
=
Outside + Within Metro Manila
```

or:

```text
Within Metro Manila Hubs
+
Main
=
Within Metro Manila + Main
```

or:

```text
Outside Metro Manila Hubs
+
Within Metro Manila Hubs
+
Main
=
All Satellite Categories
```

Implementation flow:

```text
Canonical Satellite
        ↓
Base Reporting Category
        ↓
Configurable Analytics Target Group
        ↓
Dashboard Target / Actual
        ↓
Satellites Page Distribution
```

The underlying Satellite hierarchy and canonical Satellite assignments must remain unchanged.

---

## 2. Existing Logic That Must Remain Intact

### 2.1 Base categories

The system continues to maintain exactly three permanent base categories:

```text
outside_metro_manila
within_metro_manila
main
```

Display labels:

- Outside Metro Manila Hubs
- Within Metro Manila Hubs
- Main

### 2.2 Canonical Satellite identity

Satellite membership must continue using:

```text
satellite_directory.id
```

Imported `satellites.id` must not become the durable category identity.

### 2.3 Effective Satellite assignment

Registrant analytics must continue using the effective association logic:

```text
manual Event Satellite assignment
        if present
otherwise
imported canonical Satellite association
```

Manual assignments remain authoritative.

### 2.4 Participant Target counts

Dashboard actuals must continue using:

```sql
COUNT(DISTINCT curated_registrant.id)
```

with:

```text
registration_type = 'participant'
```

Volunteers remain excluded from Dashboard Satellite Target actuals.

### 2.5 Active batch scope

All current actual counts must continue to use only:

```text
Event
+
active import batch
```

Historical or inactive batches must not contribute to current metrics.

---

## 3. New Concept: Analytics Target Groups

Introduce a reporting layer above the three base Satellite categories.

An **Analytics Target Group** contains one or more base categories.

Example:

```text
Analytics Group A
├── Outside Metro Manila Hubs
└── Within Metro Manila Hubs
```

```text
Analytics Group B
└── Main
```

The Dashboard and high-level Satellite distribution must consume these Analytics Target Groups instead of assuming that all three base categories always appear independently.

---

## 4. Supported Grouping Configurations

Because there are only three base categories, the active configuration should always be a partition of those categories.

### Configuration A — All Separate

```text
Group 1 → Outside Metro Manila Hubs
Group 2 → Within Metro Manila Hubs
Group 3 → Main
```

Dashboard reporting groups: **3**

### Configuration B — Outside + Within

```text
Group 1 → Outside Metro Manila Hubs + Within Metro Manila Hubs
Group 2 → Main
```

Dashboard reporting groups: **2**

### Configuration C — Outside + Main

```text
Group 1 → Outside Metro Manila Hubs + Main
Group 2 → Within Metro Manila Hubs
```

Dashboard reporting groups: **2**

### Configuration D — Within + Main

```text
Group 1 → Within Metro Manila Hubs + Main
Group 2 → Outside Metro Manila Hubs
```

Dashboard reporting groups: **2**

### Configuration E — All Combined

```text
Group 1 → Outside Metro Manila Hubs
         + Within Metro Manila Hubs
         + Main
```

Dashboard reporting groups: **1**

---

## 5. Non-Overlapping Group Rule

A base category must belong to exactly one active Analytics Target Group.

The following must be rejected:

```text
Group A
Outside + Within

Group B
Within + Main
```

because `Within Metro Manila Hubs` would be included in more than one active analytics group.

The active analytics grouping must behave as a partition. Each of these:

```text
Outside
Within
Main
```

must appear:

- exactly once;
- in one active Target Group only; and
- never omitted from the complete active grouping.

This keeps Dashboard totals, Target comparisons, and distribution percentages unambiguous.

---

## 6. Satellite Settings Page Update

The configuration must live in the **Satellite Settings page**.

Do not move this configuration back into the Dashboard.

Satellite Settings remains responsible for:

```text
Canonical Satellite
        ↓
Base Category
```

and will now also manage:

```text
Base Categories
        ↓
Analytics Target Groups
```

---

## 7. New Settings Section

Add a new section after the existing Target Satellite category configuration.

Suggested title:

```text
Dashboard Analytics Grouping
```

Suggested description:

```text
Choose whether Outside Metro Manila Hubs, Within Metro Manila Hubs,
and Main should be reported separately or combined for Dashboard
targets and high-level Satellite analytics.
```

---

## 8. Recommended Grouping UI

The UI should not require users to manually recreate Satellite selections.

Users combine **base categories**, not individual Satellites.

Example:

```text
Dashboard Analytics Grouping

Group 1
[✓] Outside Metro Manila Hubs
[✓] Within Metro Manila Hubs
[ ] Main

Group 2
[ ] Outside Metro Manila Hubs
[ ] Within Metro Manila Hubs
[✓] Main
```

The UI must prevent a base category from being selected in more than one group.

When a category is assigned to one group, it should become unavailable in other groups unless first removed from its current group.

---

## 9. Simplified Preset UX

Because only five valid grouping arrangements exist, the preferred UX may use presets instead of a completely free-form builder.

Example:

```text
Reporting Structure

○ Keep all three categories separate

○ Combine Outside + Within
  Main remains separate

○ Combine Outside + Main
  Within remains separate

○ Combine Within + Main
  Outside remains separate

○ Combine all three categories
```

This approach is recommended if no future requirement exists for adding more base categories.

Benefits:

- fewer invalid states;
- easier validation;
- faster configuration;
- simpler testing;
- no overlapping category groups;
- predictable Dashboard rendering.

The backend should still store the resulting group/category relationships explicitly.

---

## 10. Analytics Group Labels

The system may automatically generate labels from group composition.

| Categories | Display Label |
|---|---|
| Outside | Outside Metro Manila Hubs |
| Within | Within Metro Manila Hubs |
| Main | Main |
| Outside + Within | Outside + Within Metro Manila |
| Outside + Main | Outside Metro Manila + Main |
| Within + Main | Within Metro Manila + Main |
| Outside + Within + Main | All Satellite Categories |

Custom user-defined names are not required for this update.

The generated label must be used consistently across:

- Satellite Settings;
- Dashboard Target inputs;
- Dashboard Target vs Actual chart;
- progress cards;
- Satellites Page pie/distribution chart;
- analytics filters;
- drilldowns;
- API or export labels, if applicable.

---

## 11. Target Input Behavior

The Dashboard Target editor must dynamically follow the active Analytics Target Groups.

The Dashboard must **not** always render exactly three fields after this update.

### Example: all separate

```text
Outside Metro Manila Hubs
Target: [ 500 ]

Within Metro Manila Hubs
Target: [ 700 ]

Main
Target: [ 1000 ]
```

Three Target inputs.

### Example: Outside + Within

```text
Outside + Within Metro Manila
Target: [ 1200 ]

Main
Target: [ 1000 ]
```

Two Target inputs.

### Example: all combined

```text
All Satellite Categories
Target: [ 2200 ]
```

One Target input.

Target values must belong to Analytics Target Groups rather than directly to base categories.

---

## 12. Target Value Migration When Grouping Changes

Changing the grouping structure can make existing Target values ambiguous.

The system must not silently add or split existing Targets unless the behavior is explicitly deterministic.

### Combining groups

When two or more existing groups are merged:

```text
Outside Target = 500
Within Target = 700
```

Recommended migration:

```text
Outside + Within Target = 1200
```

This is safe because the old Target values are additive planning values.

### Splitting a combined group

If:

```text
Outside + Within Target = 1200
```

is changed back to:

```text
Outside
Within
```

the system must **not automatically guess** how 1200 should be split.

Recommended behavior:

```text
Outside Target = 0 / unconfigured
Within Target = 0 / unconfigured
```

Display a clear notice that Targets for newly split groups must be re-entered.

If the implementation already retains prior historical independent Target values, they may be restored, but the system must never fabricate a split percentage.

---

## 13. Target Validation

Each Analytics Target Group Target must retain existing numeric validation:

- whole numbers only;
- minimum `0`;
- maximum `1,000,000,000`;
- no negative values;
- no partial save on validation failure.

If the existing implementation uses:

```text
0 = target not configured
```

retain that behavior.

---

## 14. Dashboard Actual Calculation for Combined Groups

For each active Analytics Target Group:

1. Resolve the base categories belonging to the group.
2. Resolve all canonical Satellites belonging to those base categories.
3. Evaluate effective Satellite associations for the active Event batch.
4. Filter to `registration_type = 'participant'`.
5. Count distinct curated people.

Conceptually:

```sql
COUNT(DISTINCT curated_registrant.id)
WHERE effective_directory_id IN (
    all canonical Satellites belonging to the group's base categories
)
AND registration_type = 'participant'
```

---

## 15. Deduplication Across Combined Categories

A combined Analytics Target Group must deduplicate participants across all member categories.

Example:

```text
Outside + Within
```

Registrant:

```text
Person A
├── effective association to an Outside Satellite
└── effective association to a Within Satellite
```

Result:

```text
Actual Participants = 1
```

not:

```text
Actual Participants = 2
```

Do not calculate combined actuals by summing existing category totals in JavaScript.

The server must calculate the distinct participant union.

---

## 16. Cross-Group Participant Overlap

Even when base categories are non-overlapping at the Satellite level, a person may potentially have effective associations to Satellites belonging to different Analytics Target Groups.

Therefore:

```text
Group A Actual
+
Group B Actual
```

must not automatically be treated as the global unique participant total.

If a total participant KPI is displayed, calculate it independently using:

```sql
COUNT(DISTINCT curated_registrant.id)
```

across all relevant canonical Satellite associations.

---

## 17. Dashboard Target vs Actual Graph

The existing Dashboard Target vs Actual graph must become dynamic.

It should render one category position per active Analytics Target Group.

Each position contains:

```text
Target
Actual
```

### 17.1 Three-group example

```text
Outside                 Target / Actual
Within                  Target / Actual
Main                    Target / Actual
```

Graph groups: **3**

### 17.2 Two-group example

```text
Outside + Within        Target / Actual
Main                    Target / Actual
```

Graph groups: **2**

### 17.3 One-group example

```text
All Satellite Categories    Target / Actual
```

Graph groups: **1**

A grouped bar chart remains the recommended visualization.

Do not keep empty placeholder bars for categories that were merged.

---

## 18. Dashboard Progress Cards

Any Dashboard cards showing:

- Actual Participants;
- Target;
- Progress %;
- Remaining;
- Exceeded;

must also render dynamically from Analytics Target Groups.

Example:

```text
Outside + Within Metro Manila

Actual       1,080
Target       1,200
Progress       90%
Remaining      120
```

and:

```text
Main

Actual         940
Target       1,000
Progress        94%
Remaining       60
```

---

## 19. Progress Calculation

Existing rules remain unchanged.

For:

```text
target > 0
```

calculate:

```text
progress_percentage =
actual_participants / participant_target * 100
```

```text
remaining_slots =
MAX(participant_target - actual_participants, 0)
```

```text
target_exceeded =
actual_participants > participant_target
```

For:

```text
target = 0
```

retain the current unconfigured Target state.

The visual progress bar may remain capped at 100%, while the displayed percentage must show the true value above 100% when exceeded.

---

## 20. Satellites Page Distribution Chart

The high-level Satellites Page pie/distribution chart must use the same active Analytics Target Group configuration as the Dashboard.

The Satellites Page must never independently infer grouping.

The source of truth is:

```text
Satellite Settings
        ↓
Analytics Target Group configuration
```

---

## 21. Distribution Chart Behavior

### Three groups

Render a three-slice pie chart.

Example:

```text
Outside      35%
Within       30%
Main         35%
```

### Two groups

Render a two-slice pie chart.

Example:

```text
Outside + Within     65%
Main                 35%
```

### One group

Do not render a one-slice pie chart.

Instead show a summary visualization/card such as:

```text
All Satellite Categories
1,940 effective registrations / associations
100%
```

A one-slice pie provides no useful comparative information.

---

## 22. Distribution Metric

Keep the existing distinction between participant Target actuals and distribution analytics.

Recommended distribution denominator:

```text
effective registrant-to-Satellite associations
```

Formula:

```text
Analytics Group Share
=
effective associations belonging to the group
/
all categorized effective associations
× 100
```

This ensures that pie/distribution slices sum to 100%.

The chart should be labeled clearly, for example:

```text
Registration Distribution by Analytics Group
```

Subtitle:

```text
Based on effective Satellite associations.
```

---

## 23. Do Not Change the Canonical Hierarchy

Combining categories for reporting must not alter:

- `hub_groups`;
- `satellite_hubs`;
- `satellite_directory`;
- Satellite-to-Hub relationships;
- Hub-to-Hub Group relationships;
- manual registrant Satellite assignments.

Example:

```text
Outside + Within Metro Manila
```

is a reporting group only.

It must not create a new Hub Group or physically merge the existing canonical hierarchy.

---

## 24. Satellite Ranking

The existing individual Satellite ranking must remain based on canonical Satellites.

Analytics grouping should not collapse the ranking into artificial aggregate Satellites.

A Satellite should continue to display its actual:

- canonical Satellite name;
- Hub;
- Hub Group;
- unique registrants;
- association count;
- rank.

Optional enhancements may add an Analytics Group label or filter, but the canonical ranking identity must remain unchanged.

---

## 25. Optional Analytics Group Filter

The Satellites Page may add:

```text
Analytics Group
[ All ▼ ]
```

Possible values depend on the current grouping configuration.

Example:

```text
All
Outside + Within Metro Manila
Main
```

Selecting a group can constrain:

- ranking;
- hierarchy distribution;
- registrant drilldown;
- represented Hubs;
- represented Satellites.

This filter must be a reporting shortcut only and must not replace the existing canonical Group / Hub / Satellite filters.

---

## 26. Drilldown Behavior

If Dashboard Target or Satellites analytics provides a group-level participant drilldown, it must:

1. Resolve all canonical Satellite IDs included in the Analytics Target Group.
2. Apply effective Satellite assignment logic.
3. Count/display one curated person once.
4. Use active Event batch scope.
5. Filter to participants for Dashboard Target rosters.
6. Preserve existing privacy restrictions.

Do not expose:

- email;
- mobile number;
- private profile/contact details.

---

## 27. Recommended Database Model

If the existing implementation currently stores one Target row per base category, extend it with explicit Analytics Target Group ownership.

Recommended conceptual table:

```text
event_satellite_target_groups
```

Suggested fields:

```text
id
event_id
display_label
participant_target
sort_order
created_at
updated_at
```

Then:

```text
event_satellite_target_group_categories
```

Suggested fields:

```text
id
target_group_id
category_key
created_at
```

where `category_key` is limited to:

```text
outside_metro_manila
within_metro_manila
main
```

---

## 28. Recommended Constraints

At minimum enforce:

```text
UNIQUE(target_group_id, category_key)
```

Additionally, application/database validation must ensure:

```text
one category_key
→ one active Target Group per Event
```

and:

```text
all three base categories
→ represented exactly once in the active configuration
```

Dataset lookup and mutation must remain Event-scoped.

---

## 29. Compatibility With Existing Satellite Category Tables

Do not duplicate canonical Satellite membership inside Analytics Target Groups.

The relationship should remain:

```text
Satellite
        ↓
Base Category
        ↓
Analytics Target Group
```

not:

```text
Analytics Target Group
        ↓
duplicate list of individual Satellite IDs
```

The Analytics Group must inherit its Satellite population from its member base categories.

This prevents configuration drift.

---

## 30. Recommended API / Service Contract

The server should expose the current reporting structure in a reusable form.

Example:

```json
{
  "groups": [
    {
      "id": 11,
      "label": "Outside + Within Metro Manila",
      "category_keys": [
        "outside_metro_manila",
        "within_metro_manila"
      ],
      "participant_target": 1200,
      "actual_participants": 1080,
      "progress_percentage": 90.0,
      "remaining_slots": 120,
      "target_exceeded": false
    },
    {
      "id": 12,
      "label": "Main",
      "category_keys": [
        "main"
      ],
      "participant_target": 1000,
      "actual_participants": 940,
      "progress_percentage": 94.0,
      "remaining_slots": 60,
      "target_exceeded": false
    }
  ]
}
```

The same resolved grouping contract should be reused by:

- Dashboard Target settings;
- Dashboard graph;
- Dashboard progress cards;
- Satellites Page distribution;
- optional Analytics Group filters;
- group-level drilldowns.

---

## 31. Source-of-Truth Rule

Do not implement separate grouping logic in different modules.

Use one server-side resolver for:

```text
Event
→ active Analytics Target Groups
→ included base category keys
→ included canonical Satellites
```

Dashboard and Satellites Page must consume that same resolver.

This creates the invariant:

```text
A category combination configured in Satellite Settings
must appear identically everywhere else.
```

---

## 32. Permission Rules

Analytics Target Group configuration belongs to Satellite Settings and must use the same authorization rules as other Satellite Settings mutations.

Requirements:

- authenticated Event access;
- Satellite Settings management permission;
- CSRF protection;
- Event-scoped lookup;
- server-side validation;
- atomic save;
- cross-Event IDs rejected.

Dashboard users should not be able to change category grouping from the Dashboard itself unless they already have Satellite Settings management access and are explicitly routed there.

---

## 33. Atomic Grouping Update

Saving a new grouping structure must be atomic.

If any group is invalid because of:

- duplicate category;
- missing category;
- invalid category key;
- cross-Event reference;
- invalid Target migration;

reject the complete configuration.

Do not partially persist group changes.

---

## 34. Configuration Change Effects

After saving a valid Analytics Group configuration:

1. Dashboard group labels must change immediately.
2. Dashboard Target inputs must follow the new groups.
3. Dashboard actuals must recalculate using the new group membership.
4. Dashboard graphs must rerender using the new number of groups.
5. Satellites distribution must use the same new grouping.
6. Optional group filters/drilldowns must use the new grouping.
7. Canonical Satellite membership must remain untouched.

---

## 35. Edge Cases

### 35.1 No active batch

- grouping configuration remains saved;
- Target values remain saved;
- Dashboard actuals become zero;
- Dashboard graph may still show Targets against zero Actual;
- Satellite distribution shows no active-data state.

### 35.2 Grouping changed from separate to combined

Example:

```text
Outside = 500
Within = 700
```

becomes:

```text
Outside + Within = 1200
```

if additive migration is used.

### 35.3 Grouping changed from combined to separate

Do not guess split Target values.

Require new Target entry or restore previously retained independent Target values when explicitly supported.

### 35.4 Manual assignment moves participant

If a manual reassignment moves a participant to a Satellite under another base category, the participant's Analytics Target Group must update immediately.

### 35.5 Participant associated with multiple Satellites inside one group

Count once in Dashboard actuals.

### 35.6 Participant associated across multiple Analytics Groups

Count once inside each group where effective membership qualifies.

Do not derive a global unique total by summing group counts.

### 35.7 Canonical Satellite rename

No grouping membership breakage.

### 35.8 Satellite moves Hub

No Analytics Group breakage if its base reporting category assignment remains unchanged.

If base category is derived from Hub Group rather than explicitly stored, recalculate according to the implemented base-category ownership rule.

### 35.9 One-group configuration

Do not render a one-slice pie.

### 35.10 Invalid overlapping configuration

Reject complete save.

### 35.11 Missing base category from configuration

Reject complete save.

### 35.12 Volunteer

Exclude from Dashboard actual Target counts.

### 35.13 Unmapped Satellite evidence

Do not silently infer Analytics Group membership unless it resolves through the existing canonical/base-category model.

---

## 36. Regression Requirements

Existing implemented behavior must continue working:

- Satellite Settings category assignment;
- canonical Satellite identity;
- effective manual assignment precedence;
- active batch isolation;
- participant-only Dashboard Target counting;
- distinct participant deduplication;
- Target progress calculation;
- Target exceeded behavior;
- zero/unconfigured Targets;
- canonical Satellite ranking;
- existing hierarchy filters;
- Needs Mapping handling;
- Event permissions and CSRF;
- canonical rename stability.

---

# Phase 1 — Analytics Group Data Model and Shared Resolver

## Goal

Introduce the Analytics Target Group layer without changing canonical Satellite membership.

## Scope

1. Add or extend database structure for:
   - Analytics Target Groups;
   - group-to-base-category membership;
   - group-level participant Targets.
2. Enforce:
   - valid category keys;
   - no duplicate categories;
   - no category overlap;
   - complete representation of all three base categories;
   - Event scoping.
3. Create one shared server-side resolver:

```text
Event
→ Analytics Groups
→ Base Categories
→ Canonical Satellites
```

4. Preserve existing canonical/effective Satellite association queries.
5. Add Target migration behavior for:
   - separate → combined;
   - combined → separate.
6. Add unit tests for all supported group configurations.

## Acceptance Criteria

- All five supported grouping structures can be persisted.
- A base category cannot appear in two active groups.
- All three base categories appear exactly once.
- Group membership resolves to canonical Satellites through existing base-category configuration.
- No individual Satellite list is duplicated in the Analytics Group table.

---

# Phase 2 — Satellite Settings Analytics Grouping UI

## Goal

Allow administrators to configure grouping from Satellite Settings.

## Scope

1. Add **Dashboard Analytics Grouping** section.
2. Present the five supported grouping arrangements.
3. Display resulting group labels before save.
4. Explain that grouping affects:
   - Dashboard Targets;
   - Target vs Actual graphs;
   - Satellites Page distribution.
5. Save changes atomically.
6. Apply permission and CSRF rules.
7. Warn when splitting a combined group requires new Target values.
8. Preserve the existing Satellite-to-base-category configuration UI.

## Acceptance Criteria

- Grouping can be changed without editing individual Satellite membership.
- Invalid overlapping configurations cannot be submitted.
- Current grouping is clearly visible.
- The page explains the reporting consequences of the selected grouping.
- Satellite hierarchy data is not modified.

---

# Phase 3 — Dynamic Dashboard Targets and Target vs Actual Analytics

## Goal

Make Dashboard Target controls and graphs follow the configured Analytics Target Groups.

## Scope

1. Replace fixed three-group assumptions with dynamic group loading.
2. Render 1–3 Target input fields depending on configuration.
3. Store Targets at Analytics Target Group level.
4. Calculate Actual using:
   - active batch;
   - effective associations;
   - all canonical Satellites inherited through member base categories;
   - participant-only filtering;
   - distinct curated registrants.
5. Update grouped Target vs Actual chart.
6. Update progress cards.
7. Recalculate remaining/exceeded status.
8. Ensure overall participant KPIs are independently deduplicated.

## Acceptance Criteria

- Dashboard reflects grouping immediately.
- Combined groups deduplicate participants correctly.
- Graph category count changes from 1 to 3 depending on configuration.
- No empty categories remain after merging.
- Target and Actual values reconcile to backend queries.
- Volunteers are excluded.

---

# Phase 4 — Satellites Page Distribution and Cross-Module Reconciliation

## Goal

Make all high-level Satellite analytics use the same Analytics Group structure.

## Scope

1. Update the high-level distribution chart.
2. Render:
   - three slices for three groups;
   - two slices for two groups;
   - summary card instead of one-slice pie.
3. Calculate distribution using effective Satellite associations.
4. Add optional Analytics Group filter.
5. Add/update group-level drilldown if supported.
6. Reconcile:
   - Satellite Settings;
   - Dashboard Target inputs;
   - Dashboard graph;
   - Dashboard progress cards;
   - Satellites Page distribution.
7. Add regression tests for grouping changes and active-batch changes.

## Acceptance Criteria

- Satellites Page uses the exact grouping configured in Satellite Settings.
- Distribution percentages reconcile to the same underlying association set.
- Combined groups are never independently reconstructed in frontend code.
- One-group configuration does not render a meaningless pie chart.
- Existing canonical ranking and hierarchy remain unchanged.

---

## 41. Recommended Implementation Order

```text
Phase 1
Data model + shared resolver
        ↓
Phase 2
Satellite Settings configuration
        ↓
Phase 3
Dashboard Target + graph adaptation
        ↓
Phase 4
Satellites Page distribution + reconciliation
```

Do not begin Dashboard graph changes before the shared grouping resolver is stable.

---

## 42. Minimum Test Coverage

Add tests for:

- all three categories separate;
- Outside + Within;
- Outside + Main;
- Within + Main;
- all categories combined;
- duplicate category rejection;
- missing category rejection;
- separate → combined Target migration;
- combined → separate Target reset/restore behavior;
- participant deduplication within combined groups;
- cross-group participant overlap;
- volunteer exclusion;
- manual Satellite reassignment;
- no active batch;
- canonical Satellite rename;
- Hub move;
- one-group distribution behavior;
- two-group distribution behavior;
- three-group distribution behavior;
- Event isolation;
- permissions;
- CSRF;
- atomic configuration save;
- Dashboard/Satellites reconciliation.

---

## 43. Final Acceptance Criteria

The update is complete when:

- Outside Metro Manila Hubs, Within Metro Manila Hubs, and Main remain the permanent base Satellite categories.
- Administrators can combine those categories for reporting in Satellite Settings.
- Each base category belongs to exactly one active Analytics Target Group.
- The grouping does not modify canonical Hub/Satellite hierarchy.
- Dashboard Target inputs dynamically match the current reporting groups.
- Dashboard Target vs Actual graph dynamically renders 1–3 reporting groups.
- Combined Dashboard actuals count distinct participants across all included Satellites.
- Volunteers remain excluded from Target actuals.
- Manual Satellite assignments immediately affect Analytics Group actuals.
- Satellites Page distribution uses the same active grouping.
- Two-group configurations render two distribution slices.
- A one-group configuration uses a summary instead of a one-slice pie.
- All grouping logic comes from a shared server-side source of truth.
- Existing Satellite category configuration and canonical analytics remain intact.
