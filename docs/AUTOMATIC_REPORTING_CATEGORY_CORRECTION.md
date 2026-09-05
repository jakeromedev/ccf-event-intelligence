# Automatic Reporting Category Derivation Correction

## Document Status

This document is a **post-implementation correction**.

It assumes the previously implemented Satellite Target Analytics Grouping feature is already implemented. This correction does **not** redesign the entire target analytics feature.

Its purpose is to remove the unnecessary manual **Reporting Category** assignment for Dashboard Target Satellites and replace it with automatic category derivation from the existing canonical Satellite hierarchy.

---

# 1. Correction Summary

The current implementation incorrectly requires an administrator to manually assign a Reporting Category to Dashboard Target Satellites.

This manual step must be removed.

The system already has a canonical hierarchy:

```text
Hub Group
    ↓
Hub
    ↓
Satellite
```

Therefore, the Reporting Category must be derived automatically from that hierarchy.

The corrected model is:

```text
Canonical Satellite
        ↓
Assigned Hub
        ↓
Hub Group
        ↓
Automatic Reporting Category
        ↓
Analytics Target Group
        ↓
Dashboard / Satellites Analytics
```

The administrator should only configure how the automatically derived categories are combined for analytics.

---

# 2. Core Rule

The system must enforce this principle:

> A Satellite's Reporting Category is derived automatically from its canonical Hub / Hub Group relationship. Users must not manually assign a Reporting Category to individual Satellites.

The following concepts must remain separate:

```text
AUTOMATIC
Satellite → Reporting Category
```

and:

```text
CONFIGURABLE
Reporting Categories → Analytics Target Groups
```

---

# 3. Base Reporting Categories

The three reporting categories remain:

```text
outside_metro_manila
within_metro_manila
main
```

Display labels:

- Outside Metro Manila Hubs
- Within Metro Manila Hubs
- Main

These are still the categories used by Analytics Target Groups.

The correction is only about **how a Satellite gets into one of these categories**.

---

# 4. Remove Manual Reporting Category Assignment

Remove all UI and backend behavior that allows a user to manually select a Reporting Category for an individual Satellite.

Remove controls such as:

```text
Reporting Category
[ Outside Metro Manila Hubs ▼ ]
```

from:

- Dashboard Target Satellite configuration;
- Satellite Settings Satellite rows;
- Satellite edit forms;
- bulk Satellite edit actions;
- modals;
- any related API payload intended only for manual category assignment.

The user must not need to classify the same Satellite twice.

---

# 5. Automatic Category Resolution

The application must determine the Reporting Category using canonical hierarchy data.

Conceptually:

```text
Satellite
    ↓
satellite_directory.hub_id
    ↓
satellite_hubs
    ↓
hub_groups
    ↓
Reporting Category
```

The Reporting Category resolver must be centralized and reusable.

Do not independently derive categories in Dashboard JavaScript, Satellites Page JavaScript, or multiple unrelated queries.

---

# 6. Outside Metro Manila Hubs Rule

If the Satellite's canonical Hub belongs to the Hub Group representing:

```text
Outside Metro Manila Hubs
```

then:

```text
reporting_category = outside_metro_manila
```

No separate Reporting Category assignment is required.

---

# 7. Within Metro Manila Hubs Rule

If the Satellite's canonical Hub belongs to the Hub Group representing:

```text
Within Metro Manila Hubs
```

then:

```text
reporting_category = within_metro_manila
```

No separate Reporting Category assignment is required.

---

# 8. Main Category Rule

`Main` must also be automatically resolvable.

The implementation must use the existing canonical configuration that identifies Main.

Do not add another manual Reporting Category field specifically for Main.

Recommended implementation priority:

```text
existing canonical Main hierarchy / identity
        ↓
main
```

If the existing implementation already has a stable canonical Main Hub Group, Hub, Satellite, or dedicated Main marker, reuse that source of truth.

Do not infer Main from display text in frontend code.

If the current system does not yet contain a stable canonical way to identify Main, introduce one server-side canonical rule and document it clearly.

---

# 9. Read-Only Display Is Allowed

The UI may still display the resolved Reporting Category as read-only information.

Example:

```text
B1G Singapore

Hub:
ICP

Reporting Category:
Outside Metro Manila Hubs
```

This is informational only.

Do not render:

- dropdown;
- edit icon;
- inline select;
- bulk category edit;
- manual override.

---

# 10. Automatic Reclassification After Hierarchy Changes

If a Satellite is moved to a Hub under a different Hub Group, its Reporting Category must update automatically.

Example:

Before:

```text
Satellite A
    ↓
Hub X
    ↓
Outside Metro Manila Hubs
    ↓
Outside
```

After moving Satellite A:

```text
Satellite A
    ↓
Hub Y
    ↓
Within Metro Manila Hubs
    ↓
Within
```

The system must automatically treat Satellite A as:

```text
within_metro_manila
```

No second update should be required in Target settings.

---

# 11. Do Not Modify Analytics Grouping Behavior

The previously implemented Analytics Target Group feature remains valid.

Administrators still configure combinations such as:

```text
Outside + Within
Main
```

or:

```text
Outside
Within + Main
```

or:

```text
Outside + Within + Main
```

The correction only changes how the base category membership of each Satellite is resolved.

The grouping flow becomes:

```text
Canonical hierarchy
        ↓
Automatic base Reporting Category
        ↓
Configured Analytics Target Group
```

---

# 12. Dashboard Impact

The Dashboard must no longer depend on manually stored Satellite Reporting Category values.

When calculating an Analytics Target Group:

1. resolve the group's base category keys;
2. resolve canonical Satellites whose hierarchy maps to those categories;
3. evaluate effective registrant-Satellite associations;
4. filter to the active Event batch;
5. filter to `registration_type = 'participant'`;
6. count distinct curated participants.

Conceptually:

```text
Analytics Group
    ↓
Base Categories
    ↓
Canonical Satellites resolved from hierarchy
    ↓
Effective Associations
    ↓
Participant-only
    ↓
COUNT(DISTINCT curated_registrant.id)
```

---

# 13. Dashboard Target vs Actual Graph

The Dashboard graph must continue to use the configured Analytics Target Groups.

No visual redesign is required solely because of this correction.

However, the graph's Actual values must now rely only on automatically resolved Reporting Categories.

If a Satellite moves between categories, Dashboard Actuals must recalculate automatically.

---

# 14. Dashboard Target Inputs

Existing Analytics Target Group target inputs remain unchanged.

The target input belongs to the Analytics Target Group.

It does not belong to an individual Satellite or manually assigned Reporting Category.

---

# 15. Satellites Page Distribution Impact

The Satellites Page distribution chart must also consume automatic Reporting Category resolution.

Flow:

```text
Canonical Satellite hierarchy
        ↓
Automatic Reporting Category
        ↓
Analytics Grouping
        ↓
Distribution Chart
```

Do not use stale manually assigned category fields when producing:

- two-slice distributions;
- three-slice distributions;
- one-group summaries;
- Analytics Group filters.

Dashboard and Satellites Page must use the same category resolver.

---

# 16. Effective Registrant Assignment Must Remain Authoritative

This correction does not change registrant-to-Satellite resolution.

Continue using:

```text
manual Event Satellite assignment
        if present
otherwise
imported canonical Satellite association
```

Once the effective Satellite is resolved, its Reporting Category is derived from its canonical hierarchy.

Correct sequence:

```text
Registrant
    ↓
Effective Satellite
    ↓
Canonical Hub
    ↓
Hub Group
    ↓
Automatic Reporting Category
    ↓
Analytics Group
```

---

# 17. Database Cleanup

If the previous implementation introduced a manually maintained field or table specifically for:

```text
Satellite → Reporting Category
```

it should no longer be treated as authoritative.

Preferred approach:

- remove the redundant manual assignment column/table when safe.

Compatibility approach:

- stop writing to the manual category field;
- stop reading from it for analytics;
- mark it deprecated;
- derive Reporting Category from hierarchy everywhere;
- remove the field/table in a later cleanup migration.

Do not maintain both as active sources of truth.

---

# 18. Migration of Existing Manual Category Data

Existing manually assigned Reporting Category values must not continue overriding canonical hierarchy.

During migration:

1. resolve every canonical Satellite through its Hub / Hub Group;
2. calculate the automatic Reporting Category;
3. compare it with any existing manual category value;
4. record mismatches for migration diagnostics if useful;
5. make the automatic hierarchy-derived category authoritative;
6. remove or ignore old manual values.

Do not mutate canonical Hub or Satellite hierarchy merely to preserve an old manual category value.

---

# 19. Unresolvable Category State

If a canonical Satellite cannot resolve to one of the three supported Reporting Categories, do not guess.

Examples:

- missing Hub;
- missing Hub Group;
- unsupported Hub Group;
- unresolved Main rule.

Return an explicit unresolved state.

Suggested internal result:

```text
reporting_category = null
```

Suggested UI:

```text
Reporting Category:
Needs Mapping
```

Such Satellites must not silently contribute to an incorrect Analytics Target Group.

---

# 20. Server-Side Resolver

Create or update one shared server-side function/service.

Conceptual contract:

```text
resolve_reporting_category(directory_id)
```

Possible result:

```json
{
  "directory_id": 208,
  "category_key": "outside_metro_manila",
  "category_label": "Outside Metro Manila Hubs",
  "hub_id": 8,
  "hub_group_id": 2,
  "resolved": true
}
```

Unresolved example:

```json
{
  "directory_id": 350,
  "category_key": null,
  "category_label": "Needs Mapping",
  "resolved": false
}
```

The exact code structure may differ, but the logic must be shared.

---

# 21. Bulk Resolution

For analytics queries, do not resolve categories one Satellite at a time with repeated database calls.

Provide a set-based resolver/query capable of handling all canonical Satellites for an Event efficiently.

Conceptually:

```text
canonical Satellites
JOIN canonical Hubs
JOIN Hub Groups
→ reporting_category_key
```

Reuse this for:

- Dashboard metrics;
- Satellites Page distribution;
- Target preview;
- drilldowns;
- Settings read-only labels.

---

# 22. Settings UI Correction

In Satellite Settings:

## Remove

- Reporting Category dropdown;
- Reporting Category bulk edit;
- category override save endpoint;
- related validation for manually selected category.

## Keep

- Hub Group configuration;
- Hub configuration;
- Satellite configuration;
- Analytics Target Group configuration;
- target values;
- read-only automatic Reporting Category display if useful.

---

# 23. Analytics Grouping UI Correction

The grouping UI should only combine the three automatic categories.

Example:

```text
Dashboard Analytics Grouping

○ Keep all three separate
○ Combine Outside + Within
○ Combine Outside + Main
○ Combine Within + Main
○ Combine all three
```

This configuration remains user-controlled.

The user is not choosing which individual Satellite is Outside, Within, or Main from this UI.

---

# 24. API / Form Contract Cleanup

Remove manually submitted fields such as:

```text
reporting_category
reporting_category_key
category_override
```

from Satellite create/edit payloads if they exist solely for this feature.

If backward compatibility requires temporarily accepting them:

- ignore them for authoritative classification;
- do not persist new overrides;
- document them as deprecated.

---

# 25. Phase 1 — Remove Manual Category Authority

## Goal

Stop treating manually assigned Satellite Reporting Category values as authoritative.

## Scope

1. Identify all manual Reporting Category fields/tables/endpoints.
2. Remove or deprecate manual category writes.
3. Remove manual category selectors from Satellite Settings.
4. Remove bulk Reporting Category editing.
5. Compare existing manual values against hierarchy-derived values.
6. Make canonical hierarchy the sole source of truth.
7. Preserve Analytics Target Group configuration.

## Acceptance Criteria

- Users can no longer manually assign a Reporting Category to an individual Satellite.
- Existing old values cannot override canonical hierarchy.
- No Dashboard or Satellites analytics query reads the old manual value as authoritative.

---

# 26. Phase 2 — Shared Automatic Reporting Category Resolver

## Goal

Centralize category derivation.

## Scope

1. Implement shared category resolver.
2. Map canonical hierarchy to Outside, Within, and Main.
3. Define unresolved state.
4. Add efficient bulk resolution.
5. Reuse existing Main canonical rule or introduce one stable server-side rule.
6. Add tests for hierarchy changes and missing mappings.

## Acceptance Criteria

- Every mapped canonical Satellite resolves deterministically.
- Unmapped Satellites return explicit unresolved state.
- No frontend code independently reconstructs category logic.
- Main is identified canonically, not by display-text guessing.

---

# 27. Phase 3 — Dashboard and Satellites Analytics Correction

## Goal

Replace manual Reporting Category dependencies in analytics.

## Scope

1. Update Dashboard Target actual queries.
2. Update Target vs Actual graph data source.
3. Update progress cards.
4. Update Satellites Page distribution chart.
5. Update optional Analytics Group filter.
6. Update group drilldowns.
7. Ensure effective manual registrant Satellite assignments still work.
8. Ensure target group definitions continue to combine base category keys only.

## Acceptance Criteria

- Dashboard and Satellites Page produce the same automatic category interpretation.
- Moving a Satellite between canonical Hub Groups immediately changes analytics.
- No manual Reporting Category maintenance is required.
- Existing Analytics Group combinations continue working.

---

# 28. Phase 4 — Cleanup and Regression Coverage

## Goal

Remove redundant implementation and verify no regressions.

## Scope

1. Remove deprecated manual category code when safe.
2. Remove unused database columns/tables in migration if appropriate.
3. Remove obsolete form validation and frontend state.
4. Add regression tests covering active batches, manual registrant reassignment, category grouping, Dashboard charts, Satellites distribution, and Needs Mapping.
5. Verify Event isolation and permissions.
6. Verify old implemented Analytics Group configurations remain valid.

## Acceptance Criteria

- No duplicate category source of truth remains.
- Existing analytics grouping survives the correction.
- Existing Target values remain intact.
- Existing canonical Satellite hierarchy remains intact.
- All current Dashboard and Satellite analytics reconcile.

---

# 29. Minimum Regression Tests

Add or update tests for:

- automatic Outside resolution;
- automatic Within resolution;
- automatic Main resolution;
- Satellite hierarchy move;
- old manual category mismatch;
- old category fields ignored/deprecated;
- unresolved Hub;
- unresolved Hub Group;
- effective manual registrant Satellite assignment;
- all three Analytics Groups separate;
- Outside + Within;
- Outside + Main;
- Within + Main;
- all categories combined;
- Dashboard Target actual reconciliation;
- Dashboard Target vs Actual graph response;
- Satellites Page distribution reconciliation;
- active batch replacement;
- canonical rename;
- Event isolation;
- permissions;
- CSRF;
- atomic hierarchy updates.

---

# 30. Final Acceptance Criteria

The correction is complete when:

- Reporting Category is no longer manually assigned to individual Satellites.
- Canonical Satellite → Hub → Hub Group hierarchy determines Reporting Category automatically.
- Main is resolved through a stable canonical server-side rule.
- Changing a Satellite's canonical hierarchy automatically changes its Reporting Category.
- Users configure only how Outside, Within, and Main are combined into Analytics Target Groups.
- Dashboard target inputs continue to follow Analytics Target Groups.
- Dashboard Actuals use automatic category membership.
- Dashboard Target vs Actual graphs update automatically after hierarchy changes.
- Satellites Page distribution uses the exact same automatic category logic.
- Effective manual registrant Satellite assignments remain authoritative before category resolution.
- Unresolvable categories are transparent and never guessed.
- Old manual Reporting Category data cannot override canonical hierarchy.
- No duplicate Satellite-to-category source of truth remains.
