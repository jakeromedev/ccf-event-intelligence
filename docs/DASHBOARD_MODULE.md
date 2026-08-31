# Event Dashboard Module

This document is the implementation guide for the current Event Dashboard. It
describes the data scope, curation rules, calculations, HTTP endpoints,
presentation behavior, security boundaries, and reconciliation guarantees used
by the application.

## Purpose

The dashboard gives an event-scoped view of registration volume, participant
progress, and participant demographics. It deliberately separates unique people
from source registration rows so that duplicate registrations remain visible
without inflating participant counts.

The rendered dashboard contains:

- Event Date and Participant Target settings
- Unique Participants
- Unique Volunteers
- Unique Registrants
- Raw Registrations
- Participant Target
- Registration Progress and Remaining Slots
- Configurable Satellite Dataset targets and progress
- Participant-only Gender, Life Stage, and Age distributions
- Active-dataset and last-updated context

Advanced Analytics, Satellite analytics, Data Quality, Imports, and Admin Tables
are neighboring event-workspace modules and are documented separately. The
Phase 3 analytics definitions, filters, privacy suppression, historical
snapshots, and Event comparison contract are in `ANALYTICS_REFERENCE.md`.

## Implementation Map

| Responsibility | Location |
|---|---|
| Dashboard page and HTTP endpoints | `app/routes.py` |
| Metric aggregation and reconciliation | `app/aggregation.py` |
| Phase 3 aggregate analytics and filters | `app/analytics.py` |
| Demographic and registration-type normalization | `app/normalization.py` |
| Unique-person curation | `app/curation.py` |
| Dashboard template | `app/templates/overview.html` |
| Shared application shell | `app/templates/base.html` |
| Dashboard and responsive styling | `app/static/app.css` |
| Database schema | `app/models.py` |
| Import validation and activation | `app/importer.py` |
| Dashboard tests | `tests/test_phase1.py` |

## Authoritative Data Flow

Every dashboard calculation follows the selected Event and never searches for a
globally active dataset:

```text
events.id
  -> newest active import_batches row owned by that Event
  -> ticket-linked registrants in that batch
  -> batch-scoped curated unique people
  -> overview counts and participant-only demographic distributions
```

An active batch is selected with all of the following constraints:

```sql
WHERE event_id = :event_id
  AND status = 'active'
ORDER BY activated_at DESC, id DESC
LIMIT 1
```

The database also enforces at most one active batch per Event through the
nullable, unique `import_batches.active_event_id` invariant. Activating a newer
valid batch supersedes only the previous batch belonging to the same Event.

The Generated Tickets, Buyers, and Registrants CSV exports are the source of
dashboard data. There is no separate dashboard upload or manually editable
metric store.

## Raw Registrations and Unique People

### Raw registration population

A raw registration is counted only when its Registrants-export row belongs to
the active batch and its `Ticket Code` matched a Generated Tickets record in
that same batch:

```sql
SELECT COUNT(*)
FROM registrants
WHERE batch_id = :active_batch_id
  AND ticket_matched = 1
```

Email address is not used as a registration identity.

### Unique-person curation

The importer rebuilds a deterministic curation layer for every successfully
processed batch. A registrant has a complete deduplication identity when all of
these normalized fields are available:

- Last Name
- Birth Month
- Birth Year
- Gender (`Male` or `Female`)

The complete deduplication key is:

```text
normalized last name | normalized birth month | normalized birth year | normalized gender
```

Normalization is conservative:

- Text is Unicode-normalized, trimmed, whitespace-collapsed, and case-folded.
- Birth month accepts month names, abbreviations, or numbers and becomes
  `01` through `12`.
- Birth year must be four digits from 1900 through 2100.
- Only recognized Male/Female values complete the identity.

Rows with a complete matching identity are merged into one
`curated_registrants` record. A row missing any identity component receives a
batch-local `incomplete:<registrant_id>` key and is deliberately kept separate;
the application does not merge people on partial evidence.

Every ticket-linked raw row maps to exactly one curated record through
`curated_registrant_sources`. This preserves drill-down traceability and makes
curation rebuildable from the source tables.

### Resolving merged values

When several source rows form one curated person:

- Registration type uses participant precedence. If any source is a
  participant, the curated person is a participant; a participant/volunteer
  disagreement is retained in `registration_type_conflict`.
- Checked-in status is true when any source row is checked in.
- Life Stage uses the most frequent normalized value, with deterministic
  priority `Single`, `Single Parent`, `Married`, then `Unknown` for ties.
- The first available normalized display values are retained for supported
  profile fields.
- `source_registrant_count` records how many raw rows formed the person.

## Registration-Type Logic

Registration type is derived from the imported Ticket Name and export Event
Name. A case-insensitive complete-word match for `volunteer` or `volunteers`
classifies the row as a volunteer. Every other ticket-linked registrant is a
participant.

Contact fields and demographic values are not used for this classification.

## Overview Metrics

Let:

```text
P = curated people with registration_type = participant
V = curated people with registration_type = volunteer
R = ticket-linked raw registrant rows
T = configured participant target
```

The dashboard calculates:

| Metric | Formula or rule |
|---|---|
| Unique Participants | `P` |
| Unique Volunteers | `V` |
| Unique Registrants | `P + V` |
| Raw Registrations | `R` |
| Duplicate Records Merged | `max(R - (P + V), 0)` |
| Participant Target | Nullable Event setting `T` |

`total_registrations` in the backend response is a compatibility name for
Unique Registrants; it is not the raw source-row count.

Duplicate Records Merged is returned by the JSON API and used for
reconciliation, although it does not currently have its own visible KPI card.

## Participant Target and Progress

The target is Event configuration, not imported data. It never caps, filters,
or changes registration records.

A target is configured only when `T > 0`. For a configured target:

```text
Progress Percentage = P / T * 100
Remaining Slots     = max(T - P, 0)
Target Exceeded     = P > T
```

The percentage is allowed to exceed 100%. The circular progress visualization
is capped at 100% for drawing purposes, while the displayed percentage retains
the true value. Remaining Slots never becomes negative.

A null or zero target produces an explicit unconfigured state:

- `target_configured = false`
- `progress_percentage = null`
- `remaining_slots = null`
- `target_exceeded = false`

Volunteers and raw duplicate rows are excluded from target progress.

## Satellite Datasets and Targets

A Satellite Dataset is an Event-owned reporting group over the existing
normalized satellites. It gives an operator a reusable way to track a target
for several satellites without adding group names to imported or curated data.

Examples include `GGMA`, `North Cluster`, and `South Cluster`; these are user
configuration and are never hardcoded by the application.

### Database relationships

Configuration uses two tables:

```text
events
  -> satellite_datasets
       -> satellite_dataset_satellites
            -> satellites
                 -> curated_registrant_satellites
                      -> curated_registrants
```

`satellite_datasets` stores the Event, unique-within-Event name, and independent
Participant Target. `satellite_dataset_satellites` is the many-to-many junction
to real `satellites.id` rows. It also carries Event and satellite-batch scope so
composite foreign keys enforce that a mapping cannot cross Events.

A dataset deletion cascades only to its junction rows. It never deletes a
satellite, registrant, curated person, import batch, or source row. Deleting an
Event cascades its dataset configuration with the rest of the Event-owned data.

Dataset names use case-insensitive Event-local uniqueness. The same name may be
used by a different Event. Satellites may belong to several datasets, and
datasets may overlap freely.

### Configuration modal

`Manage Satellite Targets` opens an in-page dashboard modal; there is no
separate settings page. The modal lists existing datasets and supports create,
edit, and intentionally confirmed delete operations. The shared editor provides:

- Required Dataset Name, trimmed and limited to 160 characters
- Required Participant Target from 0 through 1,000,000,000
- Searchable checklist of normalized satellites in the Event's active batch
- At least one required satellite selection
- Preloaded name, target, and satellite selections during editing

When no active satellites exist, configuration remains viewable and deletable,
but creation/saving is disabled until an import supplies selectable satellites.
All submitted dataset and satellite identifiers are revalidated server-side.

### Authoritative aggregation

For each dataset:

```text
Event
  -> Event's active import batch
  -> selected normalized satellite relationships in that batch
  -> DISTINCT curated_registrant_id
  -> registration_type = participant
```

The calculation uses `COUNT(DISTINCT curated_registrants.id)` across all
selected satellites. A participant connected to two selected satellites counts
once in that dataset. A participant may count independently in two overlapping
datasets because each reporting group has its own scope.

Volunteers, unmatched raw rows, and duplicate source registrations do not
inflate Actual Participants. Counts are grouped in SQL for all datasets rather
than calculated with a query per dataset or by summing satellite totals.

Let `A` be Actual Unique Participants and `T` the dataset target:

```text
Progress Percentage = A / T * 100
Remaining Slots     = max(T - A, 0)
Target Exceeded     = A > T
```

This reuses the Event target convention. A zero target is an unconfigured
progress state, never a division-by-zero operation. Percentages may exceed
100%; only the card's visual fill is capped.

### Active-batch persistence

Satellite rows are derived and batch-scoped, while Satellite Dataset settings
belong to the Event. During activation, junction rows are remapped to the new
batch's real satellite IDs by the existing `satellites.normalized_name`
identity. No second satellite catalog and no copied satellite name column are
introduced.

If an identity is absent from the new import, its historical mapping is retained
and contributes zero to current metrics. A later batch containing that identity
remaps it automatically. Rebuilding curation for the same batch captures and
restores matching selections around the derived-satellite rebuild.

Targets and calculated totals remain separate: dataset totals are never stored,
dataset targets need not sum to the Event target, and every request recalculates
against the authoritative active batch.

## Participant Profile

All demographic panels use curated participants only. Volunteers are excluded,
and Unknown remains in every distribution denominator so each panel reconciles
to Unique Participants.

### Gender

| Imported value | Dashboard category |
|---|---|
| `Male`, `M` | Male |
| `Female`, `F` | Female |
| Blank or any other value | Unknown |

Gender is never inferred from a name, email address, or another profile field.

### Life Stage

| Imported value | Dashboard category |
|---|---|
| `Single` | Single |
| `Single Parent`, `Solo Parent` | Single Parent |
| `Married` | Married |
| Blank or any other value | Unknown |

Whitespace, underscores, and hyphens are normalized before matching. Values
such as Separated and Widow/Widower remain represented as Unknown rather than
being silently dropped.

### Age

Age is always evaluated at the configured Event Date.

When a full Date of Birth is present, age uses day-accurate birthday logic:

```text
event year - birth year - 1 when the birthday has not occurred by Event Date
```

When only Birth Month and Birth Year are present, the calculation uses the first
day of that birth month as its reproducible approximation. The page reports how
many displayed ages were estimated this way.

Age becomes Unknown when:

- Event Date is not configured.
- Required birth information is missing.
- A date, month, or year cannot be parsed.
- The calculated age is below 0 or above 120.

The buckets are:

- Below 20
- 20–25
- 26–30
- 31–35
- 36–40
- 41+
- Unknown

If Event Date is missing, all participants reconcile under Unknown and the page
prompts the operator to configure the date.

## Reconciliation Guarantees

The dashboard response includes boolean checks that make data drift visible:

| Check | Required invariant |
|---|---|
| `registrations_reconcile` | Unique Registrants = Participants + Volunteers |
| `gender_reconciles` | Sum of Gender categories = Participants |
| `life_stage_reconciles` | Sum of Life Stage categories = Participants |
| `age_reconciles` | Sum of Age buckets = Participants |
| `raw_to_curated_reconciles` | Raw = Unique Registrants + Duplicates Merged |
| `source_traceability_reconciles` | Source mappings = Raw Registrations |

These values are part of the JSON contract and are covered by automated tests.
They are not currently displayed as warnings in the page UI.

## Event Settings

The dashboard settings form submits to:

```text
POST /events/<event_id>/settings
```

The request is CSRF-protected during normal runtime. Validation rules are:

- Event Date may be blank or a strict ISO date in `YYYY-MM-DD` format.
- Participant Target may be blank or a whole number from `0` through
  `1,000,000,000`.
- Blank values are stored as `NULL`.
- Zero is stored but is treated as an unconfigured progress target.
- Invalid input leaves the prior settings unchanged and redirects back with an
  error message.

Settings are isolated by Event. Saving one Event cannot change another Event's
configuration or batch selection.

## HTTP Interface

### Rendered page

```text
GET /events/<event_id>
```

The route loads the Event, selects its active batch, calculates the complete
dashboard response, and server-renders `app/templates/overview.html`.

An unknown Event returns `404`.

### Dashboard JSON

```text
GET /events/<event_id>/dashboard
Accept: application/json
```

The endpoint returns the same authoritative aggregation used by the rendered
page. Its top-level shape is:

```json
{
  "event": {
    "id": 1,
    "name": "Example Event",
    "event_date": "2026-09-12"
  },
  "active_batch_id": 12,
  "last_updated": "...",
  "overview": {
    "participants": 525,
    "volunteers": 15,
    "total_registrations": 540,
    "unique_registrants": 540,
    "raw_registrations": 548,
    "duplicate_records_merged": 8,
    "participant_target": 700,
    "target_configured": true,
    "progress_percentage": 75.0,
    "remaining_slots": 175,
    "target_exceeded": false
  },
  "participant_profile": {
    "gender": {"total": 525, "items": []},
    "life_stage": {"total": 525, "items": []},
    "age": {"total": 525, "items": []}
  },
  "satellite_datasets": [
    {
      "id": 1,
      "name": "GGMA",
      "participant_target": 250,
      "actual_participants": 187,
      "progress_percentage": 74.8,
      "remaining_slots": 63,
      "target_exceeded": false,
      "target_configured": true,
      "satellite_count": 5,
      "satellite_ids": [11, 12, 13, 14, 15],
      "satellites": []
    }
  ],
  "reconciliation": {}
}
```

Distribution items contain labels, counts, and percentages. Gender and Life
Stage items also contain cumulative `start` and `end` percentages used to build
CSS conic-gradient segments.

An unknown Event returns `404`. An existing Event without an active batch still
returns `200` with zeroed metrics and distributions.

### Satellite Dataset CRUD

```text
POST /events/<event_id>/satellite-datasets
POST /events/<event_id>/satellite-datasets/<dataset_id>
POST /events/<event_id>/satellite-datasets/<dataset_id>/delete
```

These form endpoints use the dashboard settings permission model, global CSRF
protection, Event ownership checks, and server-side input validation. A dataset
cannot be edited or deleted through another Event URL, and submitted satellite
IDs must all belong to the route Event. The delete endpoint additionally
requires the modal's explicit confirmation value.

### Registrant roster endpoint

The repository also contains:

```text
GET /events/<event_id>/overview/registrants
```

It returns a ticket-linked raw registrant roster with names, registration and
ticket codes, origin, demographic labels, ticket status, and check-in state.
`app/static/overview.js` contains a client-side searchable modal implementation
for this endpoint. The current `overview.html` does not render that modal or
load this script, so it is not part of the visible dashboard flow at present.

Because this endpoint contains row-level data, it should not be confused with
the aggregate-only `/dashboard` response.

## Presentation Behavior

The page is server-rendered with Jinja and uses CSS-based visualizations; the
current overview does not require a charting library or frontend build step.

- KPI cards display the five headline values.
- The progress ring displays participant progress against the Event target.
- Gender and Life Stage use CSS conic-gradient donut charts.
- Age uses horizontal percentage bars.
- Counts use thousands separators.
- Percentages display with one decimal place.
- Unknown values remain visible in legends and bars.
- The shared application shell shows Event name, active-dataset status,
  activation timestamp, and batch number.
- Responsive styles collapse and stack panels for narrower screens.

## Empty-State Behavior

An Event may exist before it has an active import batch. In that state:

- The Event workspace remains accessible.
- A notice links the operator to Imports.
- All overview and profile counts are zero.
- Target settings remain editable.
- Target progress can be configured, but participant progress remains zero.
- `active_batch_id` is null.
- `last_updated` uses the Event's `updated_at` timestamp.
- All reconciliation booleans remain true for the empty population.

No placeholder analytics or data from another Event are displayed.

## Authentication, Authorization, and Privacy

Normal runtime applies the application's global authentication guard to the
dashboard page, settings action, and JSON endpoints. Authenticated approved
administrators, standard users, and Registration operators may view the normal
Dashboard. Registration operators receive the aggregate dashboard only: the
Event settings panel, create/import actions, and Satellite Dataset management
controls are absent, and direct mutation requests are denied with HTTP 403.
Test deployments may explicitly enable `AUTHENTICATION_DISABLED`.

The `CCF_STANDARD_USER_MUTATIONS_ALLOWED` policy controls Event settings and
related import mutations. Development/testing default to the Phase 1 approved-
user workflow. Staging/production default to administrator-only mutation until
the product owner approves broader access. This switch applies only to the
`user` role and can never grant Registration operators mutation access. Admin
Tables remain administrator-only.

The rendered overview and `/dashboard` JSON response are aggregate-only. They
do not include names, email addresses, mobile numbers, registration codes,
ticket codes, or raw birth values. The separate `/overview/registrants` endpoint
is row-level and remains denied to the Registration role; registration staff
use the focused, Event-scoped Registrations module instead.

## Database and Performance Notes

- Normal runtime requires MySQL; SQLite is used only for isolated tests and the
  one-time migration path.
- The active batch, curated registration type, raw ticket match, and source
  mapping columns have supporting constraints or indexes in `app/models.py`.
- Headline counts are grouped in SQL.
- Participant profile calculation loads only the curated demographic columns
  for participants in one active batch; it does not load raw JSON payloads.
- Metrics are calculated on request. There is no dashboard cache or stored
  aggregate table.
- Import activation is atomic: a failed or incomplete batch does not replace
  the Event's active dashboard data.
- Satellite Dataset counts use one grouped distinct-person query for all Event
  datasets; they do not issue per-satellite or per-dataset participant queries.

## Verification

Run the complete automated suite with:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Run the Phase 1 reconciliation command for a specific Event with:

```sh
.venv/bin/python scripts/reconcile_phase1.py EVENT_ID
```

Important dashboard coverage in `tests/test_phase1.py` verifies:

- Event and active-batch isolation
- Participant and volunteer counts
- Raw-to-curated duplicate accounting
- Participant target validation and progress behavior
- Target-exceeded behavior without negative remaining slots
- Gender, Life Stage, and Age reconciliation
- Empty Event behavior
- JSON privacy and `404` behavior
- Curation traceability and idempotence
- Superseding a batch without affecting another Event
- Satellite Dataset CRUD and validation
- Cross-Event dataset, satellite, edit, delete, and count isolation
- Distinct-person counting across multiple selected satellites
- Volunteer, raw-duplicate, and unselected-satellite exclusion
- Independent overlapping dataset calculations and zero-target behavior
- Dataset remapping and recalculation after active-batch replacement
- Aggregate JSON privacy after adding Satellite Dataset configuration

## Related Documentation

- `PHASE_1_CORE_DASHBOARD.md` — concise Phase 1 metric contract
- `CURATION_LAYER.md` — registrant and satellite curation details
- `EVENT_IMPORTS_MODULE.md` — upload, validation, processing, and activation
- `DATA_QUALITY_MODULE.md` — validation and curation quality reporting
- `CURRENT_DATABASE_STRUCTURE.md` — database tables and relationships
- `AUTHENTICATION.md` — login, approval, session, and authorization behavior
