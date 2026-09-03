# Satellites Page — Canonical Hub & Satellite Analytics Redesign

- **Status:** Proposed Major Revision
- **Primary route:** `/events/<event_id>/satellites`
- **Registrant drilldown:** `/events/<event_id>/satellites/registrants`
- **Primary objective:** Completely revise the Event-level Satellites page so its analytics, filters, ranking, and registrant drilldown follow the canonical Satellite Settings hierarchy and database relationships.
- **Out of scope:** Attendance and check-in analytics.

---

# 1. Background

The existing Satellites page is primarily organized around:

```text
Event
↓
Satellite Analytics
↓
Local / International
↓
Attendance
↓
Satellite
```

The current Satellite Settings schema establishes a different and more authoritative hierarchy:

```text
Hub Group
↓
Hub
↓
Canonical Satellite
↓
Imported Satellite Evidence
```

The revised Satellites page must follow the canonical Satellite Settings structure so both modules describe the same data model and naming logic.

The page becomes an Event-scoped analytics and drilldown surface over the global canonical Satellite directory.

---

# 2. New Core Information Architecture

The revised Satellites page must follow:

```text
Selected Event
    ↓
Active Import Batch
    ↓
Imported Satellite Evidence
    ↓ satellites.directory_id
Canonical Satellite
    ↓ satellite_directory.hub_id
Hub
    ↓ satellite_hubs.hub_group_id
Hub Group
```

The main user-facing hierarchy becomes:

```text
Event
↓
Hub Group
↓
Hub
↓
Canonical Satellite
↓
Registrants
```

This replaces Local/International affiliation as the main grouping logic.

---

# 3. Canonical Data Sources

The redesigned page should use:

```text
hub_groups
    ↓
satellite_hubs
    ↓
satellite_directory
    ↓
satellites.directory_id
```

## Hub Groups

Use the two fixed classifications:

```text
Within Metro Manila Hubs
Outside Metro Manila Hubs
```

## Hubs

Display Hub names from:

```text
satellite_hubs.name
```

## Satellites

Display canonical Satellite names from:

```text
satellite_directory.name
```

The imported `satellites.name` should primarily remain source/import evidence or fallback text where required.

## Imported Satellite Evidence

Event- and batch-scoped Satellite evidence remains in `satellites` and connects to the directory through:

```text
satellites.directory_id
→ satellite_directory.id
```

---

# 4. Registrant Counting Logic

Reuse the existing curated-person association logic already used by the Satellites page.

The important change is how curated registrants are grouped.

Instead of grouping mainly through:

```text
satellites.affiliation
```

or imported Satellite names, group through:

```text
satellites.directory_id
→ satellite_directory.id
→ satellite_hubs.id
→ hub_groups.id
```

Recommended conceptual calculation:

```text
Canonical Satellite Registrants
=
COUNT(DISTINCT curated_registrant)
associated with imported Satellite evidence
linked to the canonical Satellite
```

Do not use `satellites.source_record_count` as the primary registrant count. It represents imported source rows and may not equal unique curated registrants.

---

# 5. Distribution Counting Rule

The existing system allows one curated person to be associated with more than one Satellite.

Because of this, the Satellite ranking can legitimately count the same person once under multiple Satellites.

For the Hub pie chart, avoid presenting overlapping Hub-level unique-person counts as though they form a strict 100% partition.

Recommended pie-chart measure:

```text
Registrant-to-Satellite associations grouped by canonical Hub
```

rather than blindly summing unique registrants per Hub.

If future business rules guarantee exactly one canonical Satellite per Event registrant, the chart can then be labeled simply as `Registrants by Hub`.

---

# 6. Remove Attendance and Check-In Analytics

Attendance and check-in are explicitly out of scope.

Remove:

- Unique Checked In;
- Satellite Attendance Rate;
- Checked In counts;
- attendance progress bars;
- Checked In sorting;
- Attendance Rate sorting;
- attendance explanations;
- check-in badges;
- attendance metrics from Satellite drilldown;
- Check-In Status from the registrant table.

The page should focus on:

- Hub Groups;
- Hubs;
- canonical Satellites;
- registrant distribution;
- Satellite ranking;
- registrant drilldown;
- canonical mapping quality.

---

# 7. Remove Local / International as Primary UX Logic

Remove the current primary scope controls:

```text
All Satellites
Local Satellites
International Satellites
```

Replace them with canonical hierarchy filters:

```text
Hub Group
→ Hub
→ Satellite
```

The imported `affiliation` field can remain in the database for source traceability, but it should no longer drive the page's main information architecture.

---

# 8. Revised Page Purpose

The redesigned Satellites page should answer:

1. How many registrants are linked to configured canonical Satellites?
2. Which Satellites have the most registrants?
3. How are registrant associations distributed across Hubs?
4. How are registrations distributed between Within Metro Manila and Outside Metro Manila Hub Groups?
5. Which Hubs and Satellites are represented in this Event?
6. Who are the registrants under each Satellite?
7. Which imported Satellite records still require canonical mapping?

---

# 9. Revised Page Introduction

Recommended copy:

```text
Event Insights / Satellite Distribution

Satellite Overview

Review registrant distribution across
Hub Groups, Hubs, and Satellites.
```

The shared application header should continue showing the selected Event and active import dataset metadata.

---

# 10. Summary KPI Cards

Replace the attendance-related metrics with four operational KPIs:

```text
[ Linked Registrants ]
[ Hubs Represented ]
[ Satellites Represented ]
[ Needs Mapping ]
```

## Linked Registrants

Unique curated registrants associated with at least one imported Satellite linked to the canonical directory.

## Hubs Represented

Canonical Hubs with at least one linked Event registrant or registrant-Satellite association.

## Satellites Represented

Canonical Satellites with at least one linked Event registrant.

## Needs Mapping

Event Satellite evidence/registrations that cannot currently resolve to the canonical directory.

Possible reasons may include:

- `satellites.directory_id IS NULL`;
- canonical Satellite has no Hub;
- source Hub cannot be resolved;
- Satellite is not configured;
- missing Satellite evidence;
- ambiguous mapping.

Where the existing synchronization engine already exposes explicit statuses, reuse those classifications.

---

# 11. Actionable KPIs

Operational KPIs should be clickable where useful.

Example:

```text
18 Needs Mapping
```

Clicking should apply:

```text
Link Status = Needs Mapping
```

and show the affected records.

---

# 12. Unified Search & Filter Toolbar

Recommended desktop layout:

```text
[ Search registrant, hub, satellite, or registration ID... ]

[ Hub Group ▼ ]
[ Hub ▼ ]
[ Satellite ▼ ]
[ Link Status ▼ ]

                                             [Clear Filters]
```

Search should match:

- Hub Group;
- Hub;
- canonical Satellite;
- registrant name;
- registration identifier.

---

# 13. Cascading Filters

Filters should constrain child options:

```text
Hub Group
    ↓
Hub
    ↓
Satellite
```

Example:

```text
Outside Metro Manila Hubs
        ↓
North Mindanao
        ↓
B1G Cagayan de Oro
```

Changing a parent filter should clear any incompatible child filter.

---

# 14. Link Status Filter

Recommended options:

```text
All
Linked
Needs Mapping
```

If detailed synchronization statuses are useful, optionally expose:

```text
Ready to Sync
Already Synced
Satellite Not Configured
Hub Not Found
Missing Satellite
Ambiguous
```

`Needs Mapping` should remain the high-level grouped filter.

---

# 15. Active Filter Chips

Display active filters as removable chips:

```text
[ Outside Metro Manila × ]
[ North Mindanao × ]
[ B1G Cagayan de Oro × ]
[ Needs Mapping × ]

Clear All
```

---

# 16. Main Analytics Layout

Recommended desktop composition:

```text
┌──────────────────────────────────────────┬──────────────────────────┐
│ SATELLITES BY REGISTRANTS                │ REGISTRANT DISTRIBUTION  │
│                                          │ BY HUB                   │
│ Horizontal Bar Chart                     │                          │
│                                          │ Pie Chart                │
│ B1G Cebu         ███████████████ 145     │                          │
│ B1G CDO          █████████████   122     │ North Mindanao  24%      │
│ B1G Davao        ███████████     108     │ Visayas         19%      │
│ B1G Makati       █████████        93     │ South Mindanao  16%      │
│                                          │ ...                      │
└──────────────────────────────────────────┴──────────────────────────┘
```

Recommended desktop ratio:

```text
65% Satellite Ranking
35% Hub Distribution
```

---

# 17. Satellite Ranking Horizontal Bar Chart

## Title

```text
Satellites by Registrants
```

## Description

```text
Ranked by unique registrants linked to each canonical Satellite.
```

## Chart Type

Use a horizontal bar chart because Satellite names may be long and horizontal rankings are easier to scan.

## Default View

Show the Top 10 Satellites by default.

Optional control:

```text
Show
[ Top 10 ▼ ]

Top 10
Top 20
All
```

## Bar Interaction

Selecting a bar should show:

```text
B1G Cagayan de Oro
122 Registrants

Hub
North Mindanao

Hub Group
Outside Metro Manila
```

Selecting a bar should optionally apply the Satellite filter or scroll to the matching Satellite in the directory/ranking section.

---

# 18. Hub Distribution Pie Chart

## Recommended Title

If based on exclusive registrants:

```text
Registrant Distribution by Hub
```

If based on association counts:

```text
Registrant-Satellite Associations by Hub
```

## Aggregation Path

```text
Registrant association
↓
Imported Satellite
↓ directory_id
Canonical Satellite
↓ hub_id
Canonical Hub
```

Group by canonical Hub, not `satellites.affiliation`.

Example legend:

```text
North Mindanao     298     24.0%
Visayas            236     19.0%
South Mindanao     198     16.0%
South Luzon        174     14.0%
```

If too many Hubs make the pie unreadable, either use a clearly documented `Other` category or switch to a more appropriate ranked visual.

---

# 19. Hub Group Distribution Summary

Add two high-level summary cards below the charts.

Example:

```text
WITHIN METRO MANILA
438 Associations
5 Hubs Represented
31 Satellites Represented
```

```text
OUTSIDE METRO MANILA
802 Associations
9 Hubs Represented
55 Satellites Represented
```

Selecting a Hub Group card should apply its corresponding filter.

---

# 20. Revised Satellite Ranking Table

Replace the current attendance-oriented columns with:

| Column | Purpose |
|---|---|
| Rank | Position in the current sorting |
| Satellite | Canonical Satellite |
| Hub | Canonical Hub |
| Hub Group | Canonical Hub Group |
| Registrants | Unique curated registrants |
| Share | Share of the chosen distribution measure |
| Action | View registrants |

Example:

```text
#   Satellite           Hub              Hub Group       Registrants   Share
1   B1G Cebu            Visayas          Outside Metro       145       11.7%
2   B1G CDO             North Mindanao   Outside Metro       122        9.8%
3   B1G Davao           South Mindanao   Outside Metro       108        8.7%
```

---

# 21. Revised Sorting

Supported sorting should become:

```text
Registrants ↓
Registrants ↑
Satellite A–Z
Satellite Z–A
Hub A–Z
Hub Group
```

Remove Checked In, Attendance Rate, and Type sorting.

---

# 22. Satellite Directory Distribution

Add an expandable hierarchy that mirrors Satellite Settings:

```text
SATELLITE DIRECTORY DISTRIBUTION

▼ OUTSIDE METRO MANILA
  9 Hubs · 55 Satellites · 802 Associations

  ▼ NORTH MINDANAO
    9 Satellites · 298 Associations

    ▼ B1G CAGAYAN DE ORO
      122 Registrants

      [View Registrants]

    ▶ B1G ILIGAN
      48 Registrants

    ▶ B1G MALAYBALAY
      32 Registrants

  ▶ SOUTH MINDANAO
    8 Satellites · 198 Associations

▶ WITHIN METRO MANILA
  5 Hubs · 31 Satellites · 438 Associations
```

---

# 23. Hierarchy Row Content

## Hub Group Row

Show:

- Hub Group name;
- Hubs represented;
- Satellites represented;
- registrant/association count;
- expand/collapse control.

## Hub Row

Show:

- Hub name;
- Satellite count;
- registrant/association count;
- percentage share where useful;
- expand/collapse control.

## Satellite Row

Show:

- canonical Satellite name;
- unique registrant count;
- percentage share;
- View Registrants action.

---

# 24. Revised Registrant Drilldown

Retain the existing drilldown route but revise the content.

Recommended heading:

```text
Event Insights / Satellite Registrants

B1G Cagayan de Oro

North Mindanao
Outside Metro Manila

122 Registrants
```

Remove all attendance/check-in information.

---

# 25. Registrant Drilldown Table

Recommended columns:

| Column | Purpose |
|---|---|
| # | Result position |
| Registrant | Participant name |
| Registration ID | Primary registration identifier |
| Hub | Canonical Hub |
| Satellite | Canonical Satellite |
| Link Status | Linked / Needs Mapping where applicable |
| Action | Optional registration detail action |

Support participant and registration ID search.

Maintain server-side pagination for large result sets.

---

# 26. Privacy

Continue the existing privacy-limited behavior.

Do not expose by default:

- email address;
- mobile number;
- unnecessary contact details;
- unrelated registration fields.

The module should remain focused on distribution and canonical Satellite assignment.

---

# 27. Needs Mapping Section

Add a dedicated data-quality callout:

```text
DATA QUALITY

18 Registrations Need Satellite Mapping

These records could not currently be connected
to the canonical Hub and Satellite directory.

[Review Needs Mapping]
```

The action should apply the Needs Mapping filter or lead to the appropriate synchronization/review workflow.

---

# 28. Unassigned and Unlinked Records

The schema permits:

```text
satellite_directory.hub_id IS NULL
```

and:

```text
satellites.directory_id IS NULL
```

Do not silently place these records under a Hub.

They should appear under a clearly labeled Needs Mapping or Unassigned state until corrected through Satellite Settings/synchronization.

---

# 29. No Active Dataset

Preserve the existing no-active-dataset behavior.

When the Event has no active import batch:

- do not render metrics;
- do not render charts;
- do not render ranking;
- do not render directory distribution;
- show the existing upload guidance.

---

# 30. URL / State Model

Replace Local/International-centric state with canonical hierarchy filters.

Recommended parameters:

```text
hub_group=outside_metro_manila
hub_id=4
satellite_id=28
link_status=linked
q=juan
sort=registrants
direction=desc
page=1
per_page=25
```

The view should remain bookmarkable where practical.

---

# 31. Responsive Design

## Desktop

Recommended order:

1. introduction;
2. KPI cards;
3. search/filter toolbar;
4. bar chart + pie chart;
5. Hub Group summary;
6. ranking table;
7. directory hierarchy.

## Tablet

- KPI cards use two columns;
- filters wrap into two columns;
- charts stack when width becomes constrained;
- ranking table remains usable through controlled horizontal scrolling.

## Mobile

Stack visualizations:

```text
Satellites by Registrants
[Horizontal chart]

Registrant Distribution by Hub
[Pie chart]

Hub Group Distribution
[Within Metro Manila]
[Outside Metro Manila]
```

Directory rows become cards.

Avoid forcing desktop tables into narrow screens where card-based presentation is clearer.

---

# 32. Accessibility

The revised module should provide:

- text alternatives for charts;
- text values alongside colors;
- keyboard-operable filter controls;
- `aria-expanded` for hierarchy accordions;
- `aria-sort` for sortable columns;
- labelled pagination controls;
- visible focus states;
- accessible filter chip removal;
- no hover-only essential interactions.

---

# 33. Performance Requirements

The page should remain performant for large Events.

Requirements:

- aggregate KPI data server-side;
- aggregate chart data server-side;
- server-side filtering and search;
- server-side ranking pagination;
- lazy-load or separately route Satellite registrant drilldowns;
- do not load every registrant into the main analytics page;
- preserve active Event and batch scope on all queries.

---

# 34. Data Integrity Boundaries

The Satellites page remains read-only analytics.

It must not:

- create Hubs;
- create Satellites;
- rename canonical Satellites;
- move canonical Satellites;
- overwrite directory mappings;
- automatically correct unmapped records;
- modify registration data.

Canonical directory maintenance remains in Satellite Settings.

---

# 35. Source-of-Truth Principle

The division of responsibility should be:

```text
Satellite Settings
=
Define and maintain the canonical hierarchy
```

```text
Satellites Page
=
Show how Event registrations are distributed
through that canonical hierarchy
```

Both modules must use:

```text
Hub Group
→ Hub
→ Satellite
```

as the common logic.

---

# 36. Implementation Phases

## Phase 1 — Data Model Alignment & Aggregation Rewrite

This is the most important phase and should be completed before redesigning the visual layer.

### Scope

- inspect the current Satellites aggregation implementation;
- locate the existing curated registrant-to-Satellite association queries;
- retain unique curated-person counting;
- replace imported-affiliation grouping with canonical directory joins;
- join `satellites.directory_id` to `satellite_directory`;
- join `satellite_directory.hub_id` to `satellite_hubs`;
- join `satellite_hubs.hub_group_id` to `hub_groups`;
- define Event-specific Hub Group aggregation;
- define Event-specific Hub aggregation;
- define Event-specific Satellite aggregation;
- define Linked Registrants;
- define Hubs Represented;
- define Satellites Represented;
- define Needs Mapping;
- define mathematically valid Hub pie-chart aggregation;
- preserve active Event and active batch scoping;
- ensure unlinked evidence is never assigned to an incorrect Hub;
- add/update aggregation tests.

### Deliverable

A backend read model representing:

```text
Event
→ Hub Group
→ Hub
→ Canonical Satellite
→ Curated Registrants
```

### Critical Rule

Do not simply relabel the old Local/International aggregation. The underlying grouping logic must change first.

---

## Phase 2 — Core Dashboard & Visual Analytics

Replace the attendance-centric dashboard with the new canonical overview.

### Remove

- Local/International scope pills;
- attendance KPIs;
- check-in KPIs;
- Local/International distribution donut;
- attendance progress bars.

### Add

- Linked Registrants KPI;
- Hubs Represented KPI;
- Satellites Represented KPI;
- Needs Mapping KPI;
- canonical search/filter toolbar;
- cascading Hub Group → Hub → Satellite filters;
- Link Status filter;
- active filter chips;
- Satellites by Registrants horizontal bar chart;
- Hub distribution pie chart;
- Hub Group summary cards;
- clickable metrics and chart interactions;
- responsive chart layout;
- chart accessibility text alternatives.

### Deliverable

A high-level dashboard showing:

```text
How many registrants?
Which Satellites rank highest?
Which Hubs carry the largest share?
Which records still need mapping?
```

---

## Phase 3 — Ranking, Hierarchy & Registrant Drilldown

Build the detailed investigation workflow beneath the dashboard.

### Scope

Revise ranking table to:

```text
Rank
Satellite
Hub
Hub Group
Registrants
Share
Action
```

Add:

- registrant-count sorting;
- Satellite-name sorting;
- Hub sorting;
- Hub Group sorting;
- ranking pagination;
- expandable Hub Group → Hub → Satellite directory hierarchy;
- aggregate counts at each hierarchy level;
- View Registrants action;
- revised Satellite registrant drilldown;
- Registration ID visibility;
- participant search;
- server-side pagination;
- privacy-preserving registrant presentation.

Remove:

- Checked In column;
- Attendance Rate column;
- check-in status from registrant drilldown.

### Deliverable

Administrators can move naturally from:

```text
high-level distribution
→ Hub
→ Satellite
→ individual registrants
```

---

## Phase 4 — Mapping Review, Responsive Polish & Regression Hardening

Complete data-quality handling and production readiness.

### Scope

- add Needs Mapping callout;
- connect Needs Mapping KPI to filtered records;
- handle `satellites.directory_id IS NULL`;
- handle `satellite_directory.hub_id IS NULL`;
- handle missing canonical parents;
- reuse existing synchronization/review statuses where appropriate;
- add Review Needs Mapping workflow/link;
- finalize URL/query-state preservation;
- finalize mobile filter UX;
- finalize mobile hierarchy cards;
- verify chart rendering on mobile;
- verify keyboard navigation;
- implement/verify `aria-expanded`;
- implement/verify `aria-sort`;
- verify chart text alternatives;
- performance-test large datasets;
- regression-test Event scoping;
- regression-test no-active-dataset state;
- regression-test privacy behavior;
- regression-test existing permissions.

### Deliverable

A production-ready Satellites module aligned with Satellite Settings and focused entirely on distribution, ranking, registrant visibility, and canonical mapping quality.

---

# 37. Phase Priority

Recommended order:

```text
Phase 1
Data Model Alignment
        ↓
Phase 2
Dashboard & Graphs
        ↓
Phase 3
Ranking & Registrant Drilldown
        ↓
Phase 4
Mapping Review & Polish
```

**Phase 1 is the heaviest and most critical phase** because the graphs, metrics, filters, ranking, and hierarchy all depend on having the correct canonical aggregation logic first.

---

# 38. Acceptance Criteria

The redesign is complete when:

1. The Satellites page uses the canonical Satellite Settings hierarchy.
2. Hub Groups come from `hub_groups`.
3. Hubs come from `satellite_hubs`.
4. Satellite names come from `satellite_directory`.
5. Imported Event Satellite evidence links through `satellites.directory_id`.
6. Local/International affiliation is no longer the main page grouping.
7. Attendance is removed.
8. Check-in metrics are removed.
9. Linked Registrants uses curated-person logic.
10. Source record counts are not mislabeled as unique registrants.
11. Hubs Represented is Event-specific.
12. Satellites Represented is Event-specific.
13. Needs Mapping is visible.
14. Unlinked evidence is never assigned to a fake Hub.
15. Unassigned canonical Satellites are clearly identified.
16. The page contains a horizontal Satellite ranking chart.
17. The ranking chart uses canonical Satellite names and unique registrant counts.
18. The page contains a Hub distribution pie chart.
19. The Hub pie uses a valid part-to-whole measure.
20. Both fixed Hub Groups are represented correctly.
21. Filters cascade Hub Group → Hub → Satellite.
22. Search can find registrants, Hubs, Satellites, and registration IDs.
23. Ranking uses canonical Hub and Satellite information.
24. Ranking contains no attendance/check-in columns.
25. Directory hierarchy mirrors Satellite Settings.
26. Registrants can be opened from a Satellite.
27. Registrant drilldown contains no attendance/check-in information.
28. Contact information remains hidden by default.
29. Large Events remain performant through server-side aggregation and pagination.
30. No-active-dataset behavior continues to work.
31. Event and active batch scoping remain correct.
32. Existing permissions remain enforced.
33. Desktop, tablet, and mobile layouts remain usable.
34. All graph information has accessible text alternatives.

---

# 39. Final UX Principle

The revised modules should communicate one consistent model:

```text
Satellite Settings

defines

Hub Group
→ Hub
→ Satellite
```

and:

```text
Satellites Page

shows

Event Registrants
→ distributed across
Hub Group
→ Hub
→ Satellite
```

The Satellites page should no longer primarily answer:

```text
Who attended?
Who checked in?
```

Its purpose becomes:

```text
Where are our registrants distributed?
Which Satellites have the most registrants?
Which Hubs carry the largest share?
Who belongs to each Satellite?
Which records still need canonical mapping?
```
