# Event Overview Page

> Historical design note: the 4,334 figures below describe raw registration-row
> analytics. The current Event Dashboard displays both 4,334 Raw Registrations
> and 4,312 Unique Registrants. See `CURATION_LAYER.md` for authoritative
> current behavior.

This document describes the current Event Overview presentation, data sources, calculations, privacy behavior, and responsive layout.

## Purpose

The Event Overview focuses on the selected event's registration and aggregate participant profile:

- Total Registrants
- CCF Main versus Satellite Churches
- Detailed church-origin distribution
- Gender ratio
- Age distribution

Attendance data remains available in the backend and other application services, but Checked-In Attendees, Attendance Rate, the metric-basis toggle, and Checked-In church-origin analytics are intentionally not displayed on this page.

## Event Scope

All values follow this scope:

```text
Selected Event
    → Active Import Batch for that Event
    → Ticket-linked Registrants in that Batch
    → Aggregate Overview Metrics
```

The page never searches for a globally active batch and never combines multiple Events.

## Header

The header displays dynamically:

- Eyebrow: `CCF Event Intelligence`
- Title: `Event Overview`
- Selected Event name
- Description: `Registration and participant profile at a glance.`
- Import activation timestamp
- Active batch number
- Dataset status

Events without an active batch retain the Event workspace and display the existing upload empty state instead of fake zero-value analytics.

## Total Registrants

A Registrant is a Registrants-export record whose `Ticket Code` matches a generated ticket in the same active batch.

The primary card shows:

- Label: `Total Registrants`
- Dynamic ticket-linked registrant count
- Description: `Ticket-linked registration records`

For the currently supplied dataset, the count remains **4,334**.

## Registrants by Church Origin

The Church Origin panel displays four summary cards with count and percentage:

- CCF Main
- Satellite Churches
- Non-CCF
- Unknown

`Satellite Churches` is:

```text
Local Satellite, excluding CCF Main
+
International Satellite
```

The detailed distribution includes:

- CCF Main
- Local Satellite
- International Satellite
- Non-CCF
- Unknown

Unknown remains in the denominator. The stacked bar, counts, percentages, and total all use the existing approved affiliation classifier.

### Current supplied dataset

| Classification | Count | Percentage |
|---|---:|---:|
| CCF Main | 1,280 | 29.5% |
| Local Satellite | 1,498 | 34.6% |
| International Satellite | 8 | 0.2% |
| Non-CCF | 440 | 10.2% |
| Unknown | 1,108 | 25.6% |
| **Total** | **4,334** | **100.0%** |

Satellite Churches therefore total **1,506**.

## Gender Profile

### Source

Gender uses only the explicit `Gender` field from the Registrants export. It is not inferred from names, email addresses, or other personal information.

The normalized database stores the original profile response in `registrants.gender_raw`.

### Normalization

- `Male` and `M` → Male
- `Female` and `F` → Female
- Common decline-to-answer responses → Prefer not to say
- Blank → Unknown
- Other unrecognized nonblank responses → Other

All ticket-linked registrants remain in the denominator, so gender counts reconcile to Total Registrants.

### Current supplied dataset

| Gender | Count | Percentage |
|---|---:|---:|
| Male | 786 | 18.1% |
| Female | 2,440 | 56.3% |
| Unknown | 1,108 | 25.6% |
| **Total** | **4,334** | **100.0%** |

The page renders these aggregates as a CSS donut chart and a count/percentage legend.

## Age Distribution

### Source

The Registrants export does not provide a direct age or complete birthdate. It provides:

- `Birth Month`
- `Birth Year`

The normalized database stores these values in:

- `registrants.birth_month_raw`
- `registrants.birth_year_raw`

### Reference date and estimation

Age is estimated using the active batch's earliest valid generated-ticket check-in timestamp as the event-date reference. If no check-in exists, the batch activation date is used.

Because the source does not contain the day of birth, the displayed ages are explicitly described as estimated. The chart uses these groups:

- Below 13
- 13–17
- 18–24
- 25–34
- 35–44
- 45–54
- 55–64
- 65+

Blank month and year values are Missing. Partial, unparseable, future, or implausible age values are Invalid. Missing and invalid profiles are reported outside the plotted valid-age population.

### Current supplied dataset

- Valid month/year profiles: **3,226**
- Missing month/year profiles: **1,108**
- Invalid profiles: **0**
- Reference date: **September 5, 2025**, the first recorded check-in

| Age group | Registrants |
|---|---:|
| Below 13 | 0 |
| 13–17 | 3 |
| 18–24 | 426 |
| 25–34 | 2,207 |
| 35–44 | 504 |
| 45–54 | 73 |
| 55–64 | 12 |
| 65+ | 1 |
| **Valid age total** | **3,226** |

The page renders the distribution as a responsive CSS vertical bar chart.

## Data Migration

The schema change is additive:

- `gender_raw`
- `birth_month_raw`
- `birth_year_raw`

Existing registrant, ticket, buyer, affiliation, check-in, and import-batch rows are not replaced.

For legacy batches, the application backfills these three fields from the preserved Registrants export referenced by `import_files.staged_path` when that source is still available. A missing legacy source does not prevent the application from starting.

New imports populate the fields through the existing transactional import process.

## Visual Design

The page uses:

- Global `"Avenir Next", Avenir, "Helvetica Neue", Arial, sans-serif` typography
- Existing teal/white CCF palette
- Existing Event workspace sidebar
- Light decorative header arcs
- One full-width Total Registrants card
- Side-by-side Church Origin and Gender panels on desktop
- Full-width Age Distribution panel
- White cards, light borders, restrained shadows, and rounded corners
- Inline SVG navigation and metric icons
- CSS-only dynamic charts with no new frontend dependency

On tablet and mobile, analytics panels stack, the gender chart and legend reflow, and the age chart scrolls within its card without causing page-level horizontal overflow.

## Privacy

The Overview remains aggregate-only. It does not display:

- Names
- Email addresses
- Mobile numbers
- Raw birth data
- Raw gender responses
- Buyer or payment information
- Raw registration rows

Only aggregate Event metadata, classifications, counts, percentages, and profile distributions appear.
