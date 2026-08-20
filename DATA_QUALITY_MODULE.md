# Data Quality Module

This document describes the currently implemented Data Quality module in the
CCF Event Dashboard. It covers Event scoping, validation sources, issue
categories, counting behavior, user interface, privacy safeguards, and current
Phase 1 limitations.

## Purpose

The Data Quality module makes import, relationship, and classification
problems visible without exposing participant contact information.

It answers questions such as:

- How many registrants have an Unknown church affiliation?
- How many registrant profiles contain no identifying profile fields?
- Are there contradictory CCF and satellite answers?
- Are any registrants missing their generated ticket relationship?
- Are generated tickets missing registrant records?
- Are any buyers unrelated to generated tickets?
- Did the source exports contain duplicate or invalid identifiers?
- What other validation warnings were recorded for the active import batch?

The module reports issues; it does not edit source records or silently repair
them.

## Route

Data Quality is available inside an Event workspace:

```text
/events/<event_id>/data-quality
```

For example:

```text
/events/2/data-quality
```

Summary-card drill-down data is served from the Event-scoped JSON endpoint:

```text
/events/<event_id>/data-quality/issues
```

The endpoint requires one of the eight supported summary-card categories. It
supports case-insensitive search, severity and entity filters, and server-side
pagination. It always resolves the selected Event's active batch before
returning any records.

The issue register accepts these server-side query parameters:

| Parameter | Supported values | Default |
|---|---|---|
| `q` | Case-insensitive issue, message, identifier, or entity search; maximum 100 characters | blank |
| `severity` | `all`, `warning`, `error` | `all` |
| `category` | `all` or a category present in the active batch | `all` |
| `entity` | `all` or an entity type present in the active batch | `all` |
| `page` | Positive integer | `1` |
| `per_page` | `10`, `25`, `50` | `10` |
| `sort` | `severity`, `category`, `entity`, `count`, `source_identifier`, `row` | `severity` |
| `direction` | `asc`, `desc` | `asc` |

Unsupported values fall back safely.

## Event Scoping

All displayed information follows this ownership chain:

```text
Selected Event
    → Active Import Batch belonging to that Event
    → Validation Issues belonging to that Batch
    → Data Quality summary and issue register
```

The route obtains the active batch with:

```text
active_batch(database, event_id)
```

It then aggregates issues with:

```text
data_quality(database, active_batch_id, query, filters, page, page_size, sort)
```

The module never searches for a globally active batch and never combines
issues from different Events.

The Data Quality page describes the active dashboard dataset. Issues attached
to invalid, validated, failed, or superseded batches remain available through
the selected Event's Imports page and import history, but are not mixed into
the active batch's Data Quality page.

## Where Issues Come From

Issues are collected at two points in the import lifecycle.

### File and batch validation

Before processing, the importer validates:

- CSV readability and structure
- Export type based on header signatures
- Required columns
- Required identifier values
- Primary identifier uniqueness
- Check-in date/time format
- Buyer quantity format
- Buyers → Generated Tickets relationships
- Generated Tickets → Registrants relationships
- Event slug and Event name consistency across all three exports

Validation issues are saved when the import preview batch is created.

### Processing and classification

When a validated batch is processed, the importer adds issues discovered while
normalizing and integrating the records:

- Unknown church affiliation
- Completely incomplete registrant profiles
- Contradictory Non-CCF and satellite answers
- Generated tickets without registrants

Processing and activation remain transactional. If processing fails, the new
batch is marked failed and the Event's previous active batch remains active.

## Persistent Issue Model

Issues are stored in:

```text
validation_issues
```

Each issue contains:

| Field | Purpose |
|---|---|
| `batch_id` | Owns the issue through one Event import batch |
| `severity` | `error` or `warning` |
| `category` | Stable machine-readable issue category |
| `entity_type` | `tickets`, `buyers`, `registrants`, or `batch` |
| `source_row` | CSV row number when the issue belongs to a source row |
| `source_identifier` | Non-contact identifier used for investigation |
| `message` | Human-readable explanation |

Issue records are preserved with their import batch for auditing and future
import-history features.

## Summary Cards

The page always provides the following eight summary categories for an active
batch:

| Category | Display label | Meaning |
|---|---|---|
| `unknown_affiliation` | Unknown church affiliation | The registrant could not be assigned to an approved affiliation category |
| `incomplete_profile` | Incomplete registrant profiles | Name, email, and mobile profile fields are all absent |
| `contradictory_affiliation` | Contradictory CCF/satellite answers | A Non-CCF response also contains satellite information |
| `registrant_without_ticket` | Registrants without matching tickets | Registrant `Ticket Code` does not exist in Generated Tickets |
| `ticket_without_registrant` | Tickets without matching registrants | Generated ticket has no Registrants record |
| `buyer_without_ticket` | Buyers without matching generated tickets | Buyer reference does not appear on a generated ticket |
| `duplicate_identifier` | Duplicate identifiers | A required unique identifier, or warning-only Control Number, is repeated |
| `invalid_csv` | Invalid import rows | The CSV could not be read as a valid supported export |

A zero count receives the clean/success treatment. A nonzero count receives a
visible issue treatment.

Every summary card is an accessible button. Selecting one opens an issue-detail
modal for that category. Clean cards remain clickable and show the explicit
empty state `No issues were recorded for this category.` This makes it possible
to inspect any category without changing or losing the filters applied to the
grouped issue register below it.

### Counting behavior

Summary values count stored issue records in each category:

```text
COUNT(validation_issues rows grouped by category)
```

They are issue-instance counts, not deduplicated participant counts. A source
row can produce more than one issue when it violates multiple rules.

## Detailed Issue Register

Below the summary cards, the Validation Details table displays every category
recorded for the active batch, including categories that do not have a
dedicated summary card.

The grouped table contains:

| Column | Meaning |
|---|---|
| Severity | Warning or Error |
| Issue | Friendly category label |
| Entity Type | Tickets, Buyers, Registrants, or Batch |
| Count | Number of issue records in that category/severity/entity group |
| Sample identifiers | Up to five non-contact source identifiers |
| Message | Representative validation message |

Details are grouped by:

```text
category + severity + entity_type
```

For each group, the interface shows one representative message and at most five
source identifiers ordered by source row.

The issue register supports:

- Case-insensitive search across category, friendly label, message, source
  identifier, and entity type
- Severity filtering
- A dynamic category filter populated from the active batch
- A dynamic entity-type filter populated from the active batch
- Single-column sorting
- Server-side pagination with 10, 25, or 50 groups per page
- Filter and sort persistence across pagination links
- A table anchor so pagination and sorting return to the issue section

Filtering changes the grouped issue register only. The eight summary cards
continue to describe all issue instances in the active batch.

## Summary Card Detail Modal

The summary-card modal displays the underlying stored issue instances for the
selected category. It is a focused investigation view; it does not alter the
existing grouped issue register or any counting rule.

The modal includes:

- Case-insensitive search across source identifier, message, source row,
  severity, and entity type
- Severity filtering for All, Warning, or Error
- An entity-type filter populated dynamically from the selected category
- Server-side pagination with 10, 25, or 50 rows per page
- Previous and Next controls with the current page and result range

The detail table contains only:

| Column | Meaning |
|---|---|
| Severity | Warning or Error |
| Entity Type | The source entity associated with the validation issue |
| Source Identifier | A non-contact registration, ticket, buyer, or batch identifier |
| Source Row | The source CSV row when available |
| Message | The stored validation explanation |

Opening and closing the modal does not navigate away from the page. Focus moves
to the dialog when it opens and returns to the selected card when it closes.
The modal can also be closed with Escape or by selecting the backdrop.

Additional detail categories may include:

- `missing_identifier`
- `wrong_export_type`
- `missing_columns`
- `event_mismatch`
- `ticket_without_buyer`
- `invalid_datetime`
- `invalid_quantity`

Categories without a custom display label are converted from their internal
snake-case name into a readable title.

## Severity and Activation Behavior

### Errors

Errors make the import batch invalid and prevent processing or activation.

Current error-producing rules include:

- Unreadable or malformed CSV
- Incorrect or unrecognized export type
- Missing required columns
- Missing supported registrant affiliation headers
- Missing required identifiers
- Invalid check-in date/time
- Invalid buyer quantity
- Duplicate primary identifiers
- Mismatched source Event slug or Event name

### Warnings

Warnings remain visible but do not by themselves block activation.

Current warnings include:

- Duplicate non-primary ticket Control Number; the row is preserved
- Ticket with an unmatched Buyer Reference Number
- Registrant with an unmatched Ticket Code
- Buyer without a generated ticket
- Unknown affiliation
- Completely incomplete profile
- Contradictory Non-CCF and satellite information
- Generated ticket without a registrant

Problematic warning records are preserved so the dashboard and Data Quality
module can make the relationship gaps visible.

## Relationship Rules

The module reflects the approved integration relationships.

### Buyers → Generated Tickets

```text
Buyer Reference Number
```

Expected cardinality:

```text
one Buyer → many Generated Tickets
```

Related issue categories:

- `ticket_without_buyer`
- `buyer_without_ticket`

### Generated Tickets → Registrants

```text
Ticket Code
```

Expected cardinality:

```text
one Generated Ticket → zero or one Registrant
```

Related issue categories:

- `registrant_without_ticket`
- `ticket_without_registrant`

`Registration Code` is not used to join Buyers or Generated Tickets.

## Affiliation Quality Rules

The Data Quality module uses results from the central affiliation classifier.
It does not independently infer affiliation.

### Unknown affiliation

A registrant is flagged when the classifier returns:

```text
Unknown
```

Examples include blank or invalid CCF attendance responses, missing satellite
scope details, or incomplete B1G hub/satellite information.

### Contradictory affiliation

For the standard CCF registrant format:

```text
Are You Attending Ccf = No
```

takes precedence and classifies the record as Non-CCF. If satellite fields are
also populated, the record is preserved as Non-CCF and a contradiction warning
is recorded.

### Incomplete profile

The current rule records an incomplete profile only when all of these profile
areas are absent:

- First Name and Last Name
- Email Address
- Mobile Number

It does not currently flag every partially completed profile. For example, a
record with a name but no mobile number is not counted by this rule.

## Empty States

### No active dataset

When the selected Event has no active import batch, the page does not display
fake zero-value quality metrics.

It shows:

```text
No active dataset for this event
```

with a link to:

```text
/events/<event_id>/imports
```

### Active dataset with no issues

Summary cards show clean zero states and the issue register displays:

```text
No data-quality issues were recorded.
```

## Privacy

The Data Quality page is intentionally investigation-oriented without exposing
raw profile data.

It does not display:

- Participant names
- Email addresses
- Mobile numbers
- Buyer names
- Payment details
- Raw CSV rows

Sample values are limited to non-contact source identifiers such as Ticket
Codes, Registration Codes, or Buyer Reference Numbers. At most five samples
are shown per grouped issue.

The summary-card modal follows the same privacy rule. It shows row-level issue
instances, but never returns participant names, email addresses, mobile
numbers, buyer names, payment details, or raw CSV contents. All displayed text
is inserted into the browser as text rather than executable markup.

The application also avoids logging raw CSV row contents during normal import
validation and processing.

## Responsive Interface

The current interface uses:

- Eight compact summary columns on wide desktop layouts
- Clickable summary cards with keyboard focus and hover feedback
- A responsive, full-screen-on-mobile issue-detail modal
- Four columns when desktop/tablet space narrows
- Two columns on narrower tablet layouts
- One column on mobile
- Integrated search, severity, category, entity, and page-size controls
- A horizontally scrollable issue table when the viewport is narrow
- Semantic warning, error, and clean status colors

The page uses the shared Avenir-style typography, teal palette, sidebar,
panels, tables, and responsive breakpoints used by the rest of the application.

## Current Phase 1 Limitations

- The module reports issues but does not provide an in-application resolution
  or record-editing workflow.
- It describes only the selected Event's active batch, not all historical
  batches simultaneously.
- It does not compare quality across Events.
- Summary counts represent issue instances, not deduplicated people.
- The incomplete-profile rule detects fully absent contact/name profiles, not
  every partially missing field.
- Only five sample identifiers are shown per group in the main issue register;
  the category modal provides privacy-safe issue-instance rows for focused
  investigation.
- Raw CSV content and personal contact/profile fields are intentionally not
  available in either table.
- Satellite spelling variants are preserved rather than silently normalized.

## Main Implementation Files

- `app/importer.py` — file validation, relationship validation, processing
  warnings, and issue persistence
- `app/classifier.py` — affiliation classification and contradiction detection
- `app/aggregation.py` — summary counts, grouped aggregation, privacy-safe
  issue-instance aggregation, search/filter logic, and pagination
- `app/routes.py` — Event-scoped Data Quality page and detail endpoint
- `app/templates/data_quality.html` — clickable summary cards, detail modal,
  grouped issue register, and empty state
- `app/static/data_quality.js` — modal interaction, server-side filters, and
  pagination
- `app/static/app.css` — cards, severity badges, table, and responsive styling
- `app/db.py` — `validation_issues` persistence model
- `tests/test_phase1.py` — quality-count, Event behavior, and privacy regression
  coverage

## Automated Verification

The current test suite verifies that:

- Unknown affiliation issues are counted.
- Contradictory CCF/satellite answers are counted.
- Tickets without registrants are counted.
- Buyers without generated tickets are counted.
- Data Quality renders only for the selected Event's active dataset.
- Events with no active dataset show the correct empty state.
- Participant email addresses and names are not exposed on Data Quality.
- Severity, category, and entity filters work together.
- Search works across approved privacy-safe issue fields.
- Sorting and pagination preserve active query parameters.
- Page-size selection supports 10, 25, and 50 groups.
- All eight summary cards render as modal triggers.
- Summary-card issue details remain Event-scoped and support row-level search,
  severity/entity filtering, and 10/25/50-row pagination.
- Unsupported summary-card categories return a not-found response.
- Filtered empty states and clean active-batch states render correctly.
- Sample identifiers remain capped at five per grouped issue.
- Existing import, relationship, classification, and atomic activation behavior
  continues to pass regression testing.
