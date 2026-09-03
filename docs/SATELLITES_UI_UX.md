# Satellites Page UI/UX Specification

## Document purpose

This document describes the complete current user interface and user experience
of the Event-level Satellites analytics page and its registrant drilldown. It
covers page structure, content, metric meaning, filtering, sorting, pagination,
responsive behavior, accessibility, privacy, and interface states.

Administrative directory management is outside this document's scope. No
directory-management workflow, form, schema, or behavior is specified here.

## Product purpose

The Satellites page helps an Event operator answer four questions:

1. How many unique curated people are associated with Satellites?
2. How many of those people checked in, and what is their attendance rate?
3. How are those people distributed between Local and International
   Satellites?
4. Which Satellite Churches have the most registrants, and who are those
   registrants?

The page is an analytics and drilldown surface. It reads the selected Event's
active import dataset and does not directly edit imported records.

## Route and navigation

Main page:

```text
GET /events/<event_id>/satellites
```

Registrant drilldown:

```text
GET /events/<event_id>/satellites/registrants
```

The Satellites item in the Event workspace sidebar is active on both routes.
The shared sidebar also provides navigation to the other Event modules and a
Back to Events action.

The shared application header shows:

- the sidebar toggle;
- the selected Event name and Event-switch action;
- the module name `Satellites`;
- the description `Review satellite participation, attendance, and
  source-traceable rosters.`;
- active-dataset status;
- active import time and batch number when a dataset exists.

## Access model

The main page and registrant drilldown are available to approved
administrators, approved standard users, and approved Registration operators
with the `satellites.view` capability. Registration operators remain governed
by the application's deny-by-default endpoint policy; only these two
Satellite-reporting endpoints are in their allowlist. Administrative directory
management remains administrator-only. Unauthenticated users are redirected
to login. Authentication-disabled local development can access the page.

The Event and active batch are resolved on the server. An unknown Event returns
HTTP 404.

## Page structure

With an active dataset, the desktop information hierarchy is:

```text
┌──────────────── Shared application header ────────────────┐
│ Event context · Satellites · active dataset metadata      │
└────────────────────────────────────────────────────────────┘

┌──────────────── Page introduction ────────────────────────┐
│ Event Insights / Satellite Analytics                     │
│ Satellite Analytics                                     │
│ Unique-person satellite insights with traceable sources │
└────────────────────────────────────────────────────────────┘

View scope  [All Satellites] [Local] [International]

┌────────┬────────┬────────┬────────┬────────┐
│ People │ Checked│ Rate   │ Local  │ Intl.  │
└────────┴────────┴────────┴────────┴────────┘

┌──────────── Registrants by Type ──────────────────────────┐
│ Donut chart + legend              About these numbers    │
└────────────────────────────────────────────────────────────┘

┌──────────── Satellite ranking ────────────────────────────┐
│ Title                Search · Rows                        │
│ Rank · Church · Type · Registrants · Check-in · Rate     │
│ Pagination summary                    Page navigation     │
└────────────────────────────────────────────────────────────┘
```

## Page introduction

The first panel establishes the workspace context with:

- breadcrumb: `Event Insights / Satellite Analytics`;
- heading: `Satellite Analytics`;
- supporting copy: `Unique-person satellite insights with traceable
  registration sources.`

The panel uses the shared administrative card language: a white surface,
subtle border and shadow, compact uppercase breadcrumb, and a prominent page
heading.

## Active-dataset dependency

All analytics are based on the Event's active import batch.

If no active dataset exists, the scope controls, metric cards, type chart, and
ranking table are not rendered. Instead, the shared empty state displays:

- an imports icon;
- `No active dataset` eyebrow;
- `No active dataset for this event` heading;
- guidance to upload the three required Event exports;
- an `Upload Required CSV Files` action.

Access to the upload destination remains subject to the current user's role.

## Scope control

The View scope row contains three pill-style links:

| Control | Query value | Ranking rows included |
| --- | --- | --- |
| All Satellites | `scope=all` | Local and International |
| Local Satellites | `scope=local` | Local only |
| International Satellites | `scope=international` | International only |

The selected pill uses a filled accent treatment; unselected pills use a light
bordered treatment. Choosing a scope:

- keeps the current search query;
- keeps rows-per-page and sorting choices;
- resets the result page to page 1;
- reloads the server-rendered page.

Important: scope changes only the ranking result set. It does not change the
five summary cards or the Local/International distribution panel. Those areas
always describe the full active Event dataset.

Invalid scope values safely fall back to `all`.

## Summary metric cards

Five cards provide Event-wide totals. Each card combines a circular icon,
short label, large formatted value, and a one-line definition.

### Unique Satellite Registrants

The number of unique curated people associated with at least one Local or
International Satellite.

A person associated with more than one Satellite is counted once in this
overall total.

### Unique Checked In

The number of those unique people whose curated record is checked in. The
curated check-in state represents whether any linked source registration has a
valid check-in.

### Satellite Attendance Rate

Calculated as:

```text
Unique Checked In ÷ Unique Satellite Registrants × 100
```

If there are no Satellite registrants, the rate is `0.0%`.

### Unique Local Registrants

The number of unique curated people associated with at least one Satellite
whose imported affiliation is `Local Satellite`.

### Unique International Registrants

The number of unique curated people associated with at least one Satellite
whose imported affiliation is `International Satellite`.

A person associated with both Local and International Satellites appears once
in each type count but only once in the overall total. Therefore, the two type
counts and percentages are not required to be mutually exclusive.

Counts use thousands separators. Percentages display one decimal place.

## Satellite Registrants by Type

This panel visualizes the Event-wide Local and International counts.

### Heading

The heading contains:

- `Satellite Registrants by Type`;
- `Based on <count> satellite registrants`.

### Donut chart

The chart uses a CSS conic gradient with Local and International colors. Its
center repeats the overall unique Satellite registrant count and the label
`Total`.

The visual also has a text alternative through `role="img"` and an accessible
label containing the Local and International counts.

### Legend

The legend provides one row per type with:

- color swatch;
- type label;
- unique-person count;
- percentage of the overall unique Satellite registrant total.

### Explanatory callout

The About these numbers callout explains the overlap rule: a person associated
with both types appears in both type counts but only once in the overall total.
This prevents users from assuming that the two categories always form an
exclusive partition.

## Satellite ranking panel

The ranking panel is titled `Top Satellite Churches by Registrants` and is
described as `Ranked by unique curated registrants`.

Only Satellites that meet all of these conditions appear:

- they belong to the active batch;
- their affiliation is Local or International Satellite;
- they have at least one curated registrant association;
- they satisfy the selected scope and search query.

`CCF Main` affiliation rows are excluded from this page's Satellite analytics.
Satellites with no curated registrants do not appear in the ranking table.

When a canonical display name is available, the page uses it. Otherwise, it
falls back to the name retained on the imported Satellite row.

## Search

The ranking header contains a search input with the placeholder:

```text
Search satellite or participant...
```

Search is server-side, case-insensitive, and substring-based. It matches:

- the Satellite's displayed name;
- a source participant's trimmed first-and-last-name combination.

A participant-name match returns the Satellite rows associated with that
curated person. Participant names are used for matching but are not exposed in
the main ranking table.

Search behavior:

- the query is trimmed and limited to 100 characters;
- scope and current sorting are preserved;
- submission returns to page 1;
- the URL fragment scrolls the browser back to `#satellite-table`;
- search does not change the summary cards or type chart.

The visible Search button makes the workflow usable without relying on
JavaScript.

## Rows-per-page control

The ranking supports:

- 10 rows, the default;
- 25 rows;
- 50 rows.

Changing the Rows select immediately submits the filter form. The selected
scope, query, sort field, and sort direction are preserved. Because the form
does not submit a `page` value, the result returns to page 1.

Invalid rows-per-page values fall back to 10.

## Ranking table

The table contains seven columns:

| Column | Meaning | Sortable |
| --- | --- | --- |
| Rank | Position in the current sorted, paginated result set | No |
| Satellite Church | Canonical or imported fallback display name | Yes |
| Type | Local or International | Yes |
| Unique Registrants | Curated people associated with the Satellite | Yes |
| Checked In | Associated curated people checked in | Yes |
| Attendance Rate | Checked In ÷ Unique Registrants | Yes |
| Action | Opens the registrant drilldown | No |

### Rank presentation

Rank is displayed in a small circular badge. It is calculated from the current
page offset, so numbering continues across pages.

Rank follows the selected sort. When the user sorts alphabetically or by
attendance, it represents row position in that ordering rather than a fixed
registrant-only rank.

### Type presentation

Type appears as a compact semantic tag labeled `Local` or `International`.

### Numeric presentation

Registrant and check-in values are right-aligned and formatted with thousands
separators. Attendance Rate combines:

- a one-decimal percentage;
- a horizontal progress track whose filled width equals the percentage.

### Row action

Every row provides a `View registrants` action. The destination includes the
Event ID, displayed Satellite name, and Local/International scope needed to
resolve the correct record.

The main table deliberately does not reveal participant names or contact
information.

## Sorting

Sortable column headings are links. Supported sort fields are:

- `name`;
- `scope`;
- `registrants`;
- `checked_in`;
- `attendance_rate`.

Default order:

```text
sort=registrants&direction=desc
```

Selecting a new field starts ascending. Selecting the active field toggles
between ascending and descending. Sort links preserve scope, query, and
rows-per-page, reset to page 1, and return to the table anchor.

The visible indicators are:

- `↑` for ascending;
- `↓` for descending;
- `↕` for an inactive sortable field.

Ties use a stable Satellite-name ordering. Name sorting additionally uses Type
as a tie-breaker.

Invalid sort fields fall back to registrants. Invalid directions fall back to
descending.

## Pagination

The footer reports:

```text
Showing <start>–<end> of <total> satellites
```

When multiple pages exist, the footer shows:

- Previous;
- selected page number;
- nearby page numbers;
- first and last pages when needed;
- ellipses for skipped ranges;
- Next.

Pagination links preserve scope, query, page size, sort field, and direction,
and return to the table anchor. Previous and Next are rendered as disabled text
when unavailable.

Page numbers are compacted only when there are more than seven pages. An
out-of-range page request is clamped to the available range.

## No matching results

When the active dataset exists but no Satellite matches the current ranking
filters, the table body displays:

- `No satellites match the current filters.`;
- a `Clear filters` link.

Clear filters returns to the base Event Satellites route and restores default
scope, search, page size, sort, and direction.

The summary cards and type chart remain visible because they represent the
full active Event dataset rather than the filtered ranking result.

## Registrant drilldown

The drilldown is opened from a ranking row. It resolves a Satellite using:

- the active batch;
- Local or International affiliation;
- its displayed canonical-or-fallback name.

Missing or invalid Satellite parameters return HTTP 404 when an active batch
exists. If the Event has no active batch, the shared no-dataset state is shown.

### Back navigation

`Back to Satellite Analytics` returns to the main page's table anchor. It does
not restore the prior ranking filters or page number.

### Drilldown summary

Three cards show Satellite-specific values:

| Metric | Meaning |
| --- | --- |
| Unique Satellite Registrants | Curated people linked to this Satellite |
| Checked In | Those people with a valid curated check-in state |
| Attendance Rate | Checked In ÷ Unique Satellite Registrants |

### Participant list heading

The list panel contains:

- breadcrumb: `Event Insights / Satellite Registrants`;
- Satellite name as the page heading;
- affiliation label;
- privacy note: `Names only; contact information is not displayed.`;
- Rows selector.

### Participant table

The table contains:

| Column | Content |
| --- | --- |
| # | Position in the paginated result |
| Registrant Name | First and last name from a representative source row |
| Ticket Status | Source ticket status, or `Unknown` |
| Check-In Status | `Checked In` or `Not Checked In` badge |

If both name fields are empty, the UI displays `Name unavailable`.

Participants are ordered by last name, first name, and curated-record ID. One
representative source registration is chosen for each curated person so the
drilldown remains a unique-person list.

### Drilldown rows and pagination

Supported page sizes are:

- 25 rows;
- 50 rows, the default;
- 100 rows.

Changing the Rows select navigates directly to the equivalent URL at page 1.
The footer reports the displayed unique-registrant range and provides the same
compact Previous/page/Next navigation model as the main table.

## Privacy model

The page is intentionally privacy-limited:

- the main ranking never renders participant records;
- the drilldown renders names, ticket status, and check-in status only;
- email addresses, mobile numbers, and other contact fields are not displayed;
- metrics use curated people to reduce duplicate counting;
- imported source traceability remains in the data model without exposing all
  source details in this interface.

## State and URL model

The main page is completely server-rendered from URL parameters:

| Parameter | Allowed values | Default | Applies to |
| --- | --- | --- | --- |
| `scope` | `all`, `local`, `international` | `all` | Ranking |
| `q` | Text up to 100 characters | Empty | Ranking |
| `page` | Positive integer | `1` | Ranking |
| `per_page` | `10`, `25`, `50` | `10` | Ranking |
| `sort` | `name`, `scope`, `registrants`, `checked_in`, `attendance_rate` | `registrants` | Ranking |
| `direction` | `asc`, `desc` | `desc` | Ranking |

The drilldown uses:

| Parameter | Allowed values | Default |
| --- | --- | --- |
| `name` | Existing displayed Satellite name | Required with an active batch |
| `scope` | `local`, `international` | Required with an active batch |
| `page` | Positive integer | `1` |
| `per_page` | `25`, `50`, `100` | `50` |

Because state lives in the URL, ranking views can be bookmarked, copied, and
reloaded without losing the current selection.

## Responsive behavior

### Wide desktop

- five metric cards appear in one row;
- the type panel places the chart/legend beside the explanatory callout;
- the ranking heading and filters share one row;
- tables use their full desktop column layout.

### Up to 1320 px

- metric cards change to three columns;
- the type panel stacks its chart section and explanatory callout.

### Up to 980 px

- metric cards change to two columns;
- the ranking heading and filter form stack;
- filters wrap while retaining their labels and controls.

### Up to 780 px

- scope label and pills stack vertically;
- scope pills scroll horizontally instead of wrapping into an excessively tall
  control;
- metric cards become a single column and reduce their minimum height;
- donut and legend stack;
- search expands to the available width;
- pagination summary and navigation stack;
- pagination can scroll horizontally;
- participant summary cards become one column;
- the participant-list heading stacks.

The ranking table has a minimum width of 990 px, and the participant table has
a minimum width of 620 px. Their shared table wrapper supplies horizontal
scrolling on narrow screens so columns are not compressed into unreadable
layouts.

## Visual language

The page uses:

- the shared B1G application shell;
- white cards with subtle borders, rounded corners, and soft shadows;
- compact labels and large tabular metric values;
- teal data-visualization accents for Satellite scope, icons, charts, and
  attendance tracks;
- Local and International color differentiation;
- the shared branded accent treatment for common buttons and pagination;
- muted supporting text to keep attention on counts and table values.

Charts are implemented with CSS rather than canvas, so text and structural
content remain part of the document.

## Accessibility behavior

Current accessibility support includes:

- semantic sections, headings, navigation elements, tables, and forms;
- named regions for Satellite scope and summary metrics;
- a text alternative on the donut chart;
- a visually hidden search label;
- a visually hidden table Actions heading;
- keyboard-operable links, buttons, search, and select controls;
- visible focus treatment on the search field and shared controls;
- named pagination navigation on both pages;
- text values alongside all color-based chart and status treatments;
- disabled Previous/Next states rendered without active links.

Current limitations to consider in future improvements:

- the selected scope pill uses visual styling but does not set `aria-current`;
- sortable headings show a visual arrow whose span is hidden from assistive
  technology, but the table does not currently expose `aria-sort`;
- the rows-per-page control depends on an inline `onchange` navigation or form
  submission, although the primary search and navigation flows remain normal
  server links/forms.

## Interaction preservation matrix

| Action | Scope | Query | Page size | Sort | Page |
| --- | --- | --- | --- | --- | --- |
| Change scope | Preserve target choice | Preserve | Preserve | Preserve | Reset to 1 |
| Submit search | Preserve | Replace | Preserve | Preserve | Reset to 1 |
| Change rows | Preserve | Preserve | Replace | Preserve | Reset to 1 |
| Change sort | Preserve | Preserve | Preserve | Replace/toggle | Reset to 1 |
| Change page | Preserve | Preserve | Preserve | Preserve | Replace |
| Clear filters | Reset | Reset | Reset | Reset | Reset |
| Return from drilldown | Reset | Reset | Reset | Reset | Reset |

## Error and edge states

The experience accounts for:

- unknown Event: HTTP 404;
- no active batch: full analytics replaced by the shared no-dataset state;
- invalid scope: normalized to All;
- invalid page size: normalized to the route default;
- invalid sort field or direction: normalized to default ranking order;
- page beyond the final result: clamped to the final valid page;
- zero matching ranking rows: inline table empty state with Clear filters;
- invalid drilldown name or scope: HTTP 404;
- Satellite with no curated registrants: omitted from ranking and unavailable as
  a valid drilldown result;
- missing representative name: `Name unavailable`;
- missing ticket status: `Unknown`;
- zero overall registrants: zero counts and `0.0%` attendance.

## Implementation map

| Concern | File |
| --- | --- |
| Main page template | `app/templates/satellites.html` |
| Registrant drilldown template | `app/templates/satellite_registrants.html` |
| Shared application shell | `app/templates/base.html` |
| Shared no-dataset state | `app/templates/_empty.html` |
| Main and drilldown route handling | `app/routes.py` |
| Metrics, search, sorting, and pagination | `app/aggregation.py` |
| Page and responsive styling | `app/static/app.css` |
| Authorization capabilities | `app/auth.py` |
| Integration coverage | `tests/test_phase1.py` |

No page-specific JavaScript bundle is loaded by the current Satellites page.
Its primary state changes use GET links and form submissions. The shared shell
JavaScript remains responsible for application navigation behavior.

## UI/UX acceptance checklist

- [ ] The shared header identifies the Event, module, and active dataset.
- [ ] No-dataset Events show the shared empty state instead of analytics.
- [ ] Scope pills filter only the ranking and preserve other ranking controls.
- [ ] All five summary metrics remain Event-wide when table filters change.
- [ ] Unique-person and overlapping-type semantics are explained accurately.
- [ ] Search matches both Satellite display names and participant names.
- [ ] Participant names do not appear in the main ranking results.
- [ ] Sorting supports all five documented fields and resets to page 1.
- [ ] Rows-per-page choices and pagination preserve ranking state.
- [ ] Empty filtered results provide a clear reset path.
- [ ] View registrants opens the correct Local or International Satellite.
- [ ] The drilldown exposes no email address, phone number, or other contact
  information.
- [ ] Both tables remain usable through horizontal scrolling on narrow screens.
- [ ] Scope, chart, pagination, and tables retain meaningful text without color.
- [ ] Invalid query parameters fall back safely or return the documented 404.
