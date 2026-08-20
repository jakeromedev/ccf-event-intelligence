# Satellite Analytics Module

This document describes the currently implemented Satellite Analytics module, including its event scope, classification sources, metrics, filters, ranking behavior, user interface, privacy rules, and known Phase 1 limitations.

## Purpose

Satellite Analytics answers:

- How many ticket-linked registrants belong to Satellite Churches?
- How many satellite registrants checked in?
- What is the satellite attendance rate?
- How many satellite registrants are Local versus International?
- Which individual satellite churches have the most registrants?
- How do registration, check-in, and attendance rate compare by satellite?

CCF Main is intentionally excluded because it is a separate top-level affiliation.

## Route

The module is available inside an Event workspace:

```text
/events/<event_id>/satellites
```

Filter examples:

```text
/events/1/satellites?scope=all
/events/1/satellites?scope=local
/events/1/satellites?scope=international
/events/1/satellites?scope=local&q=east&page=1&per_page=10&sort=registrants&direction=desc
```

Supported query parameters are:

| Parameter | Supported values | Default |
|---|---|---|
| `scope` | `all`, `local`, `international` | `all` |
| `q` | Case-insensitive satellite-name or participant-name search, limited to 100 characters | blank |
| `page` | Positive integer | `1` |
| `per_page` | `10`, `25`, `50` | `10` |
| `sort` | `name`, `scope`, `registrants`, `checked_in`, `attendance_rate` | `registrants` |
| `direction` | `asc`, `desc` | `desc` |

Unsupported values fall back safely to their defaults.

## Event Scoping

All Satellite Analytics data follows this relationship:

```text
Selected Event
    → Active Import Batch belonging to that Event
    → Ticket-linked Registrants in that Batch
    → Local and International Satellite classifications
    → Satellite Analytics
```

The module never searches for a globally active batch and never combines data from multiple Events.

The route obtains the active batch with:

```text
active_batch(database, event_id)
```

It then calls:

```text
satellite_metrics(database, active_batch_id, scope)
```

The aggregation function also accepts the validated search, page-size, page,
sort-column, and sort-direction values supplied by the route.

## Included Registrants

A record is included in Satellite Analytics only when:

1. It belongs to the selected Event's active batch.
2. Its `Ticket Code` matches a generated ticket, represented by `ticket_matched = 1`.
3. Its normalized affiliation is either:
   - `Local Satellite`
   - `International Satellite`

The following classifications are excluded:

- CCF Main
- Non-CCF
- Unknown

## Satellite Classification Sources

Satellite Analytics uses the central affiliation classifier. It does not independently infer church origin.

### Standard CCF registrant format

The original registrant format uses:

- `Are You Attending Ccf`
- `Are You From A Local Or International Satellite`
- `Which Local Satellite`
- `Which International Satellite`

Approved behavior:

- CCF attendance response of No → Non-CCF
- Local Satellite with `Which Local Satellite = CCF Main` → CCF Main
- Other Local Satellite responses → Local Satellite
- International Satellite responses → International Satellite
- Missing or unusable affiliation responses → Unknown

### B1G registrant format

The B1G registrant format uses:

- `B1g Satellite Hub`
- `B1g Satellite`
- `Specify B1g Satellite`

Approved precedence:

1. `B1g Satellite = B1G Main` → CCF Main
2. `B1g Satellite Hub = ICP` → International Satellite
3. Every other populated hub → Local Satellite
4. When `B1g Satellite = Others`, `Specify B1g Satellite` becomes the displayed satellite name
5. Missing hub or satellite name → Unknown

ICP takes precedence over Others. Therefore, a record with Hub = ICP and Satellite = Others remains International and uses the specified satellite name.

## Dynamic Satellite Names

Satellite names are not hardcoded.

They come from the imported registrant profile:

- Standard local satellite name
- Standard international satellite name
- B1G satellite selection
- B1G specified satellite name when Others is selected

The normalized name is stored in:

```text
registrants.satellite_name
```

The original source values remain stored in their raw columns for auditing and future normalization improvements.

## Summary Metrics

The page displays five summary cards.

### Satellite Registrants

```text
COUNT(ticket-linked Local Satellite registrants)
+
COUNT(ticket-linked International Satellite registrants)
```

### Satellite Checked In

A Checked-In Satellite Registrant is an included satellite registrant whose matched generated ticket has a populated, valid:

```text
Check-in Date Time
```

The normalized database represents this with:

```text
checked_in = 1
```

### Satellite Attendance Rate

```text
Satellite Checked In / Satellite Registrants × 100
```

When there are no satellite registrants, the rate is displayed as 0.0% rather than dividing by zero.

### Local Registrants

The number of included records classified as:

```text
Local Satellite
```

CCF Main is excluded.

### International Registrants

The number of included records classified as:

```text
International Satellite
```

## Scope Filter

The page provides:

- All Satellites
- Local Satellites
- International Satellites

In the current Phase 1 implementation, the scope filter changes the **individual satellite ranking**.

The five top summary cards continue to show totals for all satellites so the overall satellite context remains visible while browsing a filtered ranking.

| Filter | Ranking contents |
|---|---|
| All Satellites | Local and International satellite rows |
| Local | Local Satellite rows only |
| International | International Satellite rows only |

The table also provides a case-insensitive satellite-name or participant-name
search. A participant-name match filters the result to that participant's
satellite while keeping the displayed satellite metrics based on the complete
satellite population. Scope and search work together. Clearing the filters
returns to all satellites with no search term.

## Individual Satellite Ranking

The ranking table contains:

| Column | Meaning |
|---|---|
| Rank | Position in the current filtered and sorted result set |
| Satellite | Dynamic `satellite_name` |
| Scope | Local or International |
| Registrants | Ticket-linked registrants assigned to that satellite |
| Checked In | Registrants with a valid matched-ticket check-in timestamp |
| Attendance Rate | Checked In divided by Registrants |
| Action | Opens the participant roster for that Event, active batch, satellite, and scope |

Rows are grouped by:

```text
satellite_name + affiliation
```

The default order is:

1. Registrant count, descending
2. Satellite name, case-insensitive alphabetical order

The user can sort by Satellite Church, Type, Registrants, Checked In, or
Attendance Rate. Sorting is single-column, with satellite name used as the
stable tie-breaker except when sorting by name. Sort links preserve the active
scope, search term, and page size.

Results are paginated server-side. The default page size is 10, with options
for 25 or 50 rows. Pagination displays the current range and total matching
satellites, and preserves scope, search, page size, and sorting parameters.
Pagination and sorting links include a table anchor so navigation returns to
the ranking section instead of the top of the page.

Because scope is part of the grouping, the same written satellite name can appear as separate Local and International rows if inconsistent source data classifies it in both scopes.

CCF Main cannot appear in the table because the ranking query only includes Local Satellite and International Satellite affiliations.

## Empty States

### Event has no active dataset

The page does not render fake zero-value analytics.

It displays:

```text
No active dataset for this event.
```

with a link to the selected Event's Imports page.

### Filter has no matching satellites

The ranking table displays:

```text
No satellites match the current filters.
```

The overall satellite summary cards remain visible, and a Clear filters action
returns to the unfiltered table.

## User Interface

The page contains:

1. Event-scoped sidebar and selected Event context
2. `Satellite Analytics` page heading
3. All / Local / International segmented filter
4. Five summary metric cards
5. Local versus International donut visualization
6. Explanatory About these numbers panel
7. Searchable, sortable, server-paginated satellite ranking table
8. Local and International scope badges
9. Event-scoped participant roster linked from each satellite row

Desktop uses a five-column metric-card layout. It reduces to three or two
columns as space narrows and one column on mobile. The donut and explanation
share one analytics row at desktop widths and stack responsively.

The ranking table is wrapped in a horizontally scrollable container so it remains usable on small screens without causing page-level overflow.

## Privacy

The main Satellite Analytics page remains aggregate-only. The explicitly
requested satellite roster displays participant names only after the user
opens a specific satellite.

It does not display:

- Email addresses
- Mobile numbers
- Buyer information
- Payment details
- Registration codes
- Ticket codes
- Raw CSV rows

The roster does not display email addresses, mobile numbers, registration or
ticket codes, buyer data, or payment data. It displays only participant name,
ticket status, and check-in status for the selected satellite.

## Data-Quality Behavior

The module does not silently include records that cannot be classified.

- Missing or invalid affiliation answers remain Unknown and are excluded from Satellite Analytics.
- Registrants without matching generated tickets are excluded from dashboard metrics and remain visible in Data Quality.
- Raw satellite values are preserved for later normalization.
- Import warnings and relationship issues remain attached to their import batch.

## Current Phase 1 Limitations

- Satellite-name spelling and capitalization are not normalized beyond preserving the imported value.
- Similar names such as abbreviations, punctuation variants, or spelling variations may appear as separate ranking rows.
- The module does not merge historical import batches.
- It does not compare different Events.
- It does not offer demographic filters.
- It does not provide downloadable reports.
- Top summary cards are overall satellite totals and do not change with the Local/International ranking filter.

These limitations preserve source transparency and avoid silently merging or reclassifying satellite data.

## Main Implementation Files

- `app/aggregation.py` — satellite queries and calculations
- `app/classifier.py` — standard CCF and B1G affiliation classification
- `app/routes.py` — Event-scoped Satellite Analytics route
- `app/templates/satellites.html` — cards, type visualization, filters, paginated table, and empty states
- `app/templates/satellite_registrants.html` — event- and satellite-scoped participant roster
- `app/static/app.css` — responsive metrics, segmented controls, donut, table, pagination, and scope badges
- `tests/test_phase1.py` — event isolation, classification, ranking, and supplied-dataset regression coverage

## Automated Verification

The current test suite verifies:

- Existing standard CCF affiliation behavior
- B1G Main mapping to CCF Main
- Non-ICP B1G hubs mapping to Local Satellite
- ICP mapping to International Satellite
- B1G Others using the specified satellite name
- Dynamic Local and International ranking
- Case-insensitive satellite search
- Case-insensitive participant-name search that returns matching satellites
- Scope filtering
- Server-side pagination and page-size selection
- Registrant and attendance-rate sorting
- Query-parameter persistence across table navigation
- Filtered-result empty state
- Satellite roster scoping and contact-information exclusion
- CCF Main exclusion
- Event-scoped active batches
- Existing supplied-dataset Local and International totals
- Privacy-safe rendering
