# Satellites Page Logic for Dashboard Satellite Targets

## 1. Purpose

This document describes the current production logic of the Event-level
**Satellite Overview** page and defines how that logic should be reused when
configuring and calculating **Satellite Targets** on the Event Dashboard.

The implementation goal is:

```text
Satellite Overview canonical hierarchy and effective assignments
                              ↓
Dashboard Satellite Target selection and participant counts
```

The Dashboard must not build a second interpretation of Satellite membership.
For the same Event, active import batch, filters, and canonical Satellite set,
both pages should identify the same people.

This is an implementation contract based on the current code, not the older
Local/International and attendance-oriented Satellite design.

## 2. Authoritative implementation files

| Concern | Current source |
|---|---|
| Satellite Overview route and query parameters | `app/routes.py` — `event_satellites` |
| Canonical metrics, filters, mapping status, and hierarchy | `app/satellite_analytics.py` |
| Satellite registrant drilldown | `app/aggregation.py` — `satellite_registrants` |
| Satellite Overview rendering | `app/templates/satellites.html` |
| Cascading filter behavior | `app/static/satellites.js` |
| Satellite Target CRUD and batch remapping | `app/satellite_datasets.py` |
| Current Satellite Target calculation | `app/aggregation.py` — `satellite_dataset_metrics` |
| Dashboard Target UI | `app/templates/overview.html` |
| Dashboard Target modal behavior | `app/static/satellite_datasets.js` |
| Canonical and dataset database constraints | `app/models.py` |
| Behavioral coverage | `tests/test_phase1.py`, `tests/test_satellite_sync.py`, and `tests/test_registrant_satellite_assignment_imports.py` |

Do not use the legacy portion of `aggregation.satellite_metrics` as the model
for new work. It retains Local/International, check-in, and attendance fields
for backward compatibility. The canonical source is
`canonical_satellite_metrics`.

## 3. Canonical data model

The Satellite Overview follows this hierarchy:

```text
Event
└── active import batch
    └── curated registrant
        └── effective Satellite association
            └── canonical Satellite (`satellite_directory`)
                └── Hub (`satellite_hubs`)
                    └── Hub Group (`hub_groups`)
```

Relevant tables:

| Table | Meaning |
|---|---|
| `events` | Event ownership boundary |
| `import_batches` | Event imports; only the active batch drives the page |
| `registrants` | Raw matched registration records |
| `curated_registrants` | Deduplicated people for a batch |
| `curated_registrant_sources` | Raw-to-curated traceability |
| `satellites` | Batch-specific imported Satellite evidence |
| `curated_registrant_satellites` | Imported Satellite associations for curated people |
| `satellite_directory` | Stable canonical Satellite identity and display name |
| `satellite_hubs` | Canonical Hub containing a Satellite |
| `hub_groups` | Top-level canonical grouping |
| `attestation_participant_registrants` | Stable participant ownership across imports |
| `event_registrant_satellites` | Event-scoped manual Satellite assignment |
| `satellite_datasets` | Event-scoped named target configuration |
| `satellite_dataset_satellites` | Current batch-bound Target-to-Satellite selections |

### Identity rules

- `satellites.id` is an imported, batch-specific identity.
- `satellite_directory.id` is the canonical Satellite identity.
- `satellite_hubs.id` and `hub_groups.id` are canonical hierarchy identities.
- `curated_registrants.id` is the unique-person identity within an import batch.
- Satellite Target membership should ultimately be expressed in canonical
  `satellite_directory.id` values, not only imported `satellites.id` values.

## 4. Event and active-batch scope

The route is:

```text
GET /events/<event_id>/satellites
```

The page first resolves the Event, then selects its active batch using:

```text
import_batches.event_id = event_id
AND import_batches.status = 'active'
ORDER BY activated_at DESC, id DESC
LIMIT 1
```

Rules:

- Every metric is scoped to exactly one Event and its active batch.
- Data from inactive or historical batches must not contribute.
- Data from another Event must never contribute.
- If no active batch exists, render the no-active-dataset state and do not
  render filters, metrics, charts, ranking, or hierarchy.

Dashboard Satellite Targets must resolve the same active batch before loading
selection options or calculating counts.

## 5. Effective Satellite association

The most important reusable logic is `EFFECTIVE_ASSOCIATIONS_CTE`.

Conceptually:

```text
manual assignment for the curated person
    if present
otherwise
imported Satellite's canonical directory link
```

Equivalent rule:

```text
effective_directory_id =
    COALESCE(manual_assignment.directory_id, imported_satellite.directory_id)
```

The manual assignment is found by joining:

```text
curated_registrant_sources
→ attestation_participant_registrants
→ event_registrant_satellites
```

Only assignments with:

```text
assignment_source = 'manual'
```

take precedence.

Consequences:

- A manual assignment changes analytics without altering the imported CSV.
- A manually reassigned person must count under the manual canonical Satellite,
  not the imported one.
- Satellite Target counts must use effective associations too. Joining Targets
  directly to `satellites.directory_id` without the manual override would make
  the Dashboard disagree with Satellite Overview.
- Manual assignments are Event-scoped and persist across future imports through
  stable attestation participant ownership.

## 6. Canonical completeness and mapping states

An association is fully linked only when this entire path exists:

```text
effective directory ID
→ satellite_directory row
→ satellite_hubs row
→ hub_groups row
```

If any part is absent, the imported evidence belongs to **Needs Mapping** and is
excluded from linked Hub/Satellite distributions.

Current Needs Mapping reasons:

| Reason key | Display status | Meaning |
|---|---|---|
| `satellite_not_configured` | Satellite Not Configured | Imported evidence has no canonical directory link |
| `hub_unassigned` | Hub Not Found | Canonical Satellite exists but has no Hub |
| `missing_hub` | Hub Not Found | The directory references a Hub that no longer resolves |
| `missing_hub_group` | Hub Group Not Found | The Hub has no resolvable Hub Group |

Important current limitation:

- Needs Mapping begins from a row in `satellites`.
- A raw registrant with a Hub response but no usable Satellite name produces no
  `satellites` row and is therefore not included in the current Overview's
  Needs Mapping count or table.
- Do not invent a canonical Satellite for such a record. A future enhancement
  should surface it explicitly as `Missing Satellite` evidence.

For Dashboard Satellite Targets, only fully linked canonical Satellites should
be selectable by default. Unmapped evidence cannot be a stable Target member.

## 7. Filter option logic

The Overview exposes these URL-backed filters:

```text
q
group
hub
satellite
link_status
sort
direction
page
per_page
```

### Hub Groups

All Hub Groups are loaded from `hub_groups` in `sort_order, id` order. A group
may be shown with zero represented Hubs or Satellites.

### Hubs

The current option list includes Hubs represented by imported Satellites linked
to the active batch, plus Hubs introduced by effective manual assignments.

### Satellites

The current option list includes canonical Satellites represented by imported
Satellite links in the active batch, plus canonical Satellites introduced by
effective manual assignments.

### Cascading validation

Server-side validation is authoritative:

- IDs must be positive integers.
- Unknown IDs are cleared.
- A selected Hub is cleared if it does not belong to the selected Hub Group.
- A selected Satellite is cleared if it does not belong to the selected Hub or
  Hub Group.
- `link_status` accepts only `all`, `linked`, or `needs_mapping`.
- Selecting `needs_mapping` clears Group, Hub, and Satellite filters because an
  incomplete canonical path cannot satisfy those filters.

Client-side JavaScript mirrors these rules:

- changing Group clears Hub and Satellite;
- changing Hub clears Satellite;
- choosing Needs Mapping clears all hierarchy selectors and submits;
- choosing a Satellite submits immediately;
- hidden incompatible options are disabled.

Dashboard Satellite Target setup should use the same cascading hierarchy. It
should not present one flat list labeled only by Local/International status.

## 8. Search logic

The Overview search is normalized to collapsed whitespace and truncated to 100
characters. It matches case-insensitively against:

- Hub Group name;
- Hub name;
- canonical Satellite name;
- imported Satellite evidence name;
- registrant first/last name;
- registration code; and
- raw source ID.

Registrant matching is performed through `curated_registrant_sources`, so a
search can match any raw source row belonging to the curated person.

For Target setup, search should at minimum match:

- canonical Satellite name;
- Hub name; and
- Hub Group name.

If Target setup adds a preview of affected people, its participant search must
reuse the same privacy-safe registrant matching logic.

## 9. Counting rules

Two measures are intentionally different.

### Unique registrants

```text
COUNT(DISTINCT curated_registrant.id)
```

Use this for:

- Linked Registrants;
- registrants per canonical Satellite;
- registrants per Hub;
- registrants per Hub Group;
- Satellite Target actual participants; and
- registrant roster totals.

### Registrant-to-Satellite associations

```text
COUNT(effective_association.id)
```

Use this for:

- total associations;
- Hub distribution shares;
- Hub Group distribution; and
- additive hierarchy summaries.

One curated person may be associated with multiple Satellites. Therefore:

- summing Satellite registrant counts may exceed Linked Registrants;
- summing distinct registrants across Hubs may double-count people;
- association counts are the correct denominator for a 100% Hub distribution;
- a Target containing multiple Satellites must count a person once with
  `COUNT(DISTINCT curated_registrant.id)`.

Never use `satellites.source_record_count` as a unique-person count. It is raw
import evidence and is displayed only for traceability.

## 10. Overview KPI logic

| KPI | Definition |
|---|---|
| Linked Registrants | Distinct curated people with at least one association resolving through Satellite → Hub → Hub Group |
| Hubs Represented | Distinct canonical Hubs reached by linked effective associations |
| Satellites Represented | Distinct canonical directory Satellites reached by linked effective associations |
| Needs Mapping | Distinct imported `satellites` rows whose effective canonical path does not resolve to a Hub Group |
| Association Count | Additive count of linked registrant-to-Satellite associations |
| Needs Mapping Registrants | Distinct curated people attached to incomplete imported evidence |
| Needs Mapping Associations | Additive associations attached to incomplete imported evidence |

The main linked KPIs and Needs Mapping metrics are calculated separately. An
unmapped record must not leak into linked totals.

## 11. Satellite ranking and chart

Each ranking row represents one canonical `satellite_directory.id` and contains:

```text
Satellite ID and canonical name
Hub ID and name
Hub Group ID, code, and name
distinct registrant count
association count
share of all filtered linked associations
rank
```

The share formula is:

```text
satellite.associations / total_filtered_linked_associations * 100
```

The horizontal chart uses the top 10 rows ordered by:

```text
registrants DESC
canonical Satellite name ASC
canonical Satellite ID ASC
```

The chart bar width is relative to the largest displayed registrant count, not
the association share.

The tabular ranking supports:

- `registrants` sort, default descending;
- `satellite` sort;
- `hub` sort;
- `group` sort;
- `asc` or `desc` direction;
- page sizes 10, 25, or 50; and
- server-side page clamping.

Non-registrant sorts use canonical names and deterministic secondary keys.

## 12. Hub distribution chart

The Hub chart groups effective associations by canonical Hub.

```text
Hub percentage = Hub association count / all filtered linked associations * 100
```

Display behavior:

- rank Hubs by association count descending, then name ascending;
- if eight or fewer Hubs are represented, show all;
- if more than eight are represented, show the top seven and combine the rest
  into `Other`;
- use the fixed eight-color `HUB_CHART_COLORS` palette; and
- label the measure as associations, not mutually exclusive people.

## 13. Hub Group and directory hierarchy

All configured Hub Groups are rendered. For each group, the response attaches
only represented Hubs and Satellites from the filtered analytics result.

Each Hub Group exposes:

- distinct registrants;
- association count and percentage;
- represented Hub count;
- represented Satellite count;
- represented Hubs; and
- represented Satellites.

Each represented Hub exposes:

- distinct registrants;
- association count and percentage;
- represented Satellite count; and
- represented Satellites.

The directory explorer is an analytics distribution, not a complete dump of
every configured zero-count Satellite in Satellite Settings.

## 14. Registrant drilldown

The drilldown route is:

```text
GET /events/<event_id>/satellites/registrants?satellite=<directory_id>
```

Rules:

- The primary identifier is canonical `satellite_directory.id`.
- The canonical directory entry must be represented by the active batch or a
  manual Event assignment.
- A person with a manual assignment is included under the manual Satellite.
- When a manual assignment exists, imported associations do not additionally
  place that person under the old Satellite.
- The roster uses curated people and returns one row per person.
- The representative raw record is the lowest raw registrant ID belonging to
  the curated person.
- Search matches name, registration code, or source ID.
- Page sizes are 25, 50, or 100; default is 50.
- Results sort by last name, first name, then curated ID.

Privacy contract:

- Display name and registration identifier only.
- Do not expose email, mobile number, or other contact/profile data.
- Display canonical Hub, canonical Satellite, and link status.
- Sanitize `return_to` as an internal-only URL before rendering the back link.

A Target drilldown spanning multiple Satellites must deduplicate the same
curated person across all selected canonical directory IDs.

## 15. Current Dashboard Satellite Target logic

The current target workflow is Event-scoped but stores batch-specific imported
Satellite selections.

### Setup options

`satellite_dataset_options` currently returns every `satellites` row in the
active Event batch:

```text
satellites.id
COALESCE(satellite_directory.name, satellites.name)
satellites.affiliation
satellites.normalized_name
```

This means the current selector:

- is flat rather than Hub Group → Hub → Satellite;
- includes unmapped imported evidence;
- identifies selections by batch-specific `satellites.id`; and
- labels records using imported affiliation instead of canonical hierarchy.

### Dataset validation

Current form rules:

- Dataset Name is required, whitespace-normalized, and at most 160 characters.
- Names must be unique per Event, case-insensitively at application level.
- Participant Target is required and must be a whole number from 0 through
  1,000,000,000.
- At least one Satellite is required.
- Satellite IDs must be unique positive integers.
- Every selected imported Satellite must belong to the Event.
- Create, update, and delete require Event mutation permission and CSRF.
- Delete requires `confirm_delete=yes`.

### Current count

The current metric already uses `EFFECTIVE_ASSOCIATIONS_CTE` and calculates:

```text
COUNT(DISTINCT curated_registrants.id)
WHERE curated_registrants.registration_type = 'participant'
AND effective directory ID matches a selected Satellite's directory ID
```

Therefore it correctly:

- deduplicates a participant selected through multiple Satellites;
- excludes volunteers;
- honors manual assignments; and
- reports zero for selected Satellites absent from the active batch.

### Target progress

For a target greater than zero:

```text
progress_percentage = actual_participants / participant_target * 100
remaining_slots = MAX(participant_target - actual_participants, 0)
target_exceeded = actual_participants > participant_target
```

For a target of zero:

```text
target_configured = false
progress_percentage = null
remaining_slots = null
target_exceeded = false
```

The visual progress bar is capped at 100%, but the displayed percentage is not.

### Active-batch replacement

Current selections are remapped on activation of a new batch by matching
`satellites.normalized_name` within the same Event. If a name is absent from the
new batch, the link remains on its historical Satellite and contributes zero.
If it returns in a later batch, it can be remapped again.

## 16. Required Dashboard Target alignment

### 16.1 Use the canonical selection identity

Recommended durable design:

```text
satellite_dataset_satellites.directory_id
→ satellite_directory.id
```

Store canonical directory IDs for Target membership. The imported Satellite ID
may be retained as traceability metadata, but it should not be the durable
selection identity.

Benefits:

- Target membership survives active-batch changes without name-based remapping;
- canonical renames do not break selection;
- duplicate imported names remain distinguishable by canonical Hub;
- manual assignment results remain consistent; and
- selection matches the Satellite Overview filter and drilldown identity.

If a schema change is deferred, the compatibility implementation must resolve
each selected imported Satellite to `directory_id` and treat the canonical ID
as the logical identity everywhere. Never join Target membership by imported
name alone when a canonical ID is available.

### 16.2 Reuse canonical option construction

Target setup should load the same active-Event option graph as the Overview:

```text
Hub Group
└── represented Hub
    └── represented canonical Satellite
```

Include Satellites introduced only by effective manual assignments.

Each selectable Satellite option should contain:

```json
{
  "directory_id": 208,
  "name": "B1G Singapore",
  "hub_id": 8,
  "hub_name": "ICP",
  "group_id": 2,
  "group_code": "outside_metro_manila",
  "group_name": "Outside Metro Manila Hubs",
  "registrants": 14
}
```

Unmapped records should be shown separately as informational Needs Mapping
items and should not be selectable until they have a complete canonical path.

### 16.3 Reuse effective participant membership

For a Target containing canonical directory IDs, calculate actual participants
as:

```sql
WITH effective_associations AS (...same canonical CTE...)
SELECT COUNT(DISTINCT curated.id)
FROM effective_associations association
JOIN curated_registrants curated
  ON curated.id = association.curated_registrant_id
 AND curated.event_id = association.event_id
 AND curated.batch_id = association.batch_id
WHERE association.event_id = :event_id
  AND association.batch_id = :active_batch_id
  AND association.directory_id IN (:target_directory_ids)
  AND curated.registration_type = 'participant';
```

The count must not depend on:

- raw registration row count;
- `satellites.source_record_count`;
- imported Local/International affiliation;
- checked-in status; or
- whether the participant is associated with one or several selected
  Satellites.

### 16.4 Mirror hierarchy and filtering behavior

The Target editor should provide:

- search by canonical Satellite, Hub, or Hub Group;
- Hub Group filter;
- Hub filter constrained by Hub Group;
- Satellite checkboxes constrained by both parents;
- a selected count;
- per-option unique participant count; and
- an unavailable/Needs Mapping explanation when appropriate.

Changing a parent filter should not silently clear already selected Target
members. It should only constrain the visible option list. This differs from
the Overview's single-result filtering, where incompatible child filters are
cleared.

### 16.5 Add a Target preview

Before save, calculate and display:

```text
selected canonical Satellites
represented Hubs
unique participants
participant target
remaining slots or exceeded amount
unmapped evidence excluded
```

The preview must deduplicate people across selections and should call a shared
server-side query rather than summing per-Satellite counts in JavaScript.

### 16.6 Add Target drilldown

Each Dashboard Target card should be able to open a privacy-limited roster that
uses the same rules as `satellite_registrants`, generalized to multiple
canonical directory IDs.

Return fields:

```text
display name
registration identifier
effective canonical Hub
effective canonical Satellite
link status
```

Do not return email or mobile data.

## 17. Recommended Target response contract

Each Target in `event_dashboard_metrics` should expose:

```json
{
  "id": 4,
  "name": "ICP Delegates",
  "participant_target": 250,
  "target_configured": true,
  "actual_participants": 217,
  "progress_percentage": 86.8,
  "remaining_slots": 33,
  "target_exceeded": false,
  "directory_ids": [208, 225, 229],
  "satellite_count": 3,
  "hub_count": 1,
  "group_count": 1,
  "unavailable_satellite_count": 0,
  "needs_mapping_excluded": 5,
  "satellites": [
    {
      "directory_id": 208,
      "name": "B1G Singapore",
      "hub_id": 8,
      "hub_name": "ICP",
      "group_id": 2,
      "group_name": "Outside Metro Manila Hubs",
      "available_in_active_batch": true,
      "participants": 42
    }
  ]
}
```

IDs and counts are illustrative. The response must not include participant
contact information.

## 18. Permission and mutation rules

- Viewing Satellite Overview follows the normal authenticated Event-page
  access policy.
- The Settings link is shown only when Satellite Settings management is
  allowed.
- Creating, updating, or deleting Satellite Targets requires
  `event_mutation_required`.
- All mutations require CSRF protection.
- Dataset lookup must include both `dataset_id` and `event_id`.
- Selected canonical Satellites must be validated server-side; client-side
  checkboxes are not an authorization boundary.
- Cross-Event Satellite IDs must be rejected.
- A failed save must not partially replace existing Target selections.

## 19. Edge cases

The implementation must define and test these cases:

1. No active batch: no selectable Satellites; saved Targets remain but count as
   zero.
2. Active batch with no linked Satellites: Target setup explains that canonical
   mapping is required.
3. Target equals zero: show unconfigured progress, not divide-by-zero output.
4. Actual exceeds target: remaining stays zero and `target_exceeded` is true.
5. Person appears under two selected Satellites: count once in Target actuals.
6. Person appears under selected and unselected Satellites: count once.
7. Volunteer appears under a selected Satellite: exclude from Target actuals.
8. Manual assignment moves a person into the Target: include immediately.
9. Manual assignment moves a person out: exclude immediately.
10. Canonical Satellite rename: membership survives because identity is ID-based.
11. Canonical Satellite moved to another Hub: Target survives and displays the
    new hierarchy.
12. Imported Satellite is unmapped: exclude from Target selection and count.
13. Imported Hub exists but Satellite response is blank: do not infer a
    Satellite; report Missing Satellite separately.
14. New active batch lacks a selected canonical Satellite: keep configuration,
    count zero for that member, and show it as unavailable.
15. Historical batch activation: recalculate against that newly active batch.
16. Deleted Event: datasets and links cascade.
17. Deleted Target: imported and canonical Satellite data remain unchanged.
18. Invalid or cross-Event IDs: reject the complete form submission.
19. Search returns no options: preserve current selections and show an empty
    search result, not an empty dataset.
20. Pagination beyond the last page: clamp to the last valid page.

## 20. Recommended implementation sequence

1. Extract or retain one shared canonical association query centered on
   `EFFECTIVE_ASSOCIATIONS_CTE`.
2. Add a canonical Target membership schema using `satellite_directory.id`, or
   introduce a compatibility layer that exposes canonical IDs consistently.
3. Replace the flat `satellite_dataset_options` payload with canonical
   Group/Hub/Satellite options from the active Event.
4. Update Target validation to verify canonical directory IDs and complete Hub
   Group paths.
5. Update `satellite_dataset_metrics` to join Target canonical IDs directly to
   effective associations.
6. Preserve participant-only distinct counting and existing progress rules.
7. Replace the flat checklist with cascading canonical filters while preserving
   hidden selections.
8. Add server-calculated Target preview and privacy-limited Target drilldown.
9. Preserve existing Target names and targets during migration.
10. Verify active-batch activation, manual assignment, canonical rename/move,
    cross-Event isolation, and no-active-batch behavior.

## 21. Acceptance criteria

- The Overview and Dashboard show the same effective canonical assignment for
  every curated person.
- A Dashboard Target selects canonical Satellites under visible Hub and Hub
  Group context.
- Only fully mapped canonical Satellites are selectable.
- Target actuals count distinct curated participants and exclude volunteers.
- Multiple selected Satellite associations never double-count a Target person.
- Manual assignments immediately affect both Overview and Target counts.
- Target membership survives import replacement and canonical renames.
- Inactive and cross-Event batches do not contribute.
- Unmapped or missing-Satellite evidence is excluded transparently and is not
  silently assigned.
- Target previews and cards reconcile to a privacy-limited Target roster.
- A zero target has an explicit unconfigured state.
- No attendance or check-in logic is introduced into Satellite Targets.
- Existing CRUD permissions, CSRF protection, validation bounds, and deletion
  confirmation remain enforced.

## 22. Minimum regression coverage

Add or retain tests for:

- canonical Hub Group → Hub → Satellite option hierarchy;
- effective manual assignment precedence;
- target deduplication across multiple selected Satellites;
- volunteer exclusion;
- canonical rename and Hub move stability;
- active-batch replacement and historical reactivation;
- mapped versus Needs Mapping separation;
- missing Satellite evidence;
- zero and exceeded targets;
- create/edit/delete validation and Event scoping;
- Target roster privacy and pagination; and
- API/UI reconciliation of all Target counts.

The implementation is complete only when the Dashboard Target count can be
derived from the same effective association set used by Satellite Overview,
with the additional `registration_type = 'participant'` constraint.
