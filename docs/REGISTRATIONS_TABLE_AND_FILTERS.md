# Registrations Table and Filter Reference

This document describes the implemented Registrations table, its source
relationships, and its server-side query controls. The authoritative
implementation is in `app/registrations.py`; the page and browser behavior are
defined by `app/templates/registrations.html` and
`app/static/registrations.js`.

## Purpose and row contract

The Registrations page is an Event-scoped operational view of registration
submissions. One displayed row represents one imported `registrants` record.
It does not use `curated_registrants`, deduplicate people, or copy data into a
separate registrations table.

```text
Selected Event
  -> selected batch (active batch by default)
      -> one output row for each registrants record
```

The module is available to approved Administrators and users with the
`registration` role. Both the HTML page and JSON data route enforce this access
server-side.

## Routes

| Surface | Method | Route |
|---|---|---|
| Registrations page | `GET` | `/events/<event_id>/registrations` |
| Table data | `GET` | `/events/<event_id>/registrations/data` |
| Attestation status update | `PATCH` | `/events/<event_id>/registrations/<registrant_id>/attestation` |
| List/create remarks | `GET`, `POST` | `/events/<event_id>/registrations/<registrant_id>/remarks` |
| Resolve remark | `PATCH` | `/events/<event_id>/registrations/<registrant_id>/remarks/<remark_id>` |

The table data endpoint returns columns, categorical filter options, rows,
summary counts, normalized query state, and pagination metadata as JSON.

## Source tables and joins

| Table | Use in Registrations | Relationship |
|---|---|---|
| `events` | Enforces the selected Event boundary | `events.id = import_batches.event_id` |
| `import_batches` | Supplies active or explicitly selected batch scope | `import_batches.id = registrants.batch_id` |
| `registrants` | Base row source and imported registration fields | One output row per record |
| `tickets` | Supplies Payment Status | Same `batch_id` and `ticket_code` as the registrant |
| `attestation_participant_registrants` | Resolves replaceable source rows to durable participants | Same `batch_id` and `registrant_id` as the registrant |
| `attestation_verifications` | Supplies the application-owned current attestation status and review time | Same Event and durable `attestation_participant_id` |
| `registrant_remarks` | Supplies pre-aggregated Pending, Resolved, and total counts | Grouped by Event and durable `attestation_participant_id` before joining |
| `users` | Supplies the last reviewer's username | `users.id = attestation_verifications.updated_by_user_id` |

The ticket, verification, and reviewer relationships are left joins. A
registration therefore remains visible when any of those related records is
missing. Missing verification means Pending. Multiple source rows mapped to one
participant display the same state; counts remain source-row counts. Names,
email addresses, and mobile numbers are never used as join keys.

## Batch scope

| `batch` value | Result |
|---|---|
| Omitted, blank, or `active` | Uses the selected Event's active batch |
| A numeric batch ID | Uses that batch only after verifying it belongs to the selected Event |
| `all` | Uses all batches belonging to the selected Event |

An invalid batch value produces a validation error. A numeric batch belonging
to a different Event is rejected. If the Event has no active batch, active
scope returns no rows rather than falling back to another batch or Event.

## Displayed table columns

The visible columns follow the fixed order below. Registration Code and Ticket
Code remain search-only fields; they are deliberately absent from the display
contract. `Search`, `Filter`, and `Sort` identify supported operations.

| Group | Column | Source/expression | Search | Filter | Sort |
|---|---|---|:---:|:---:|:---:|
| Attestation & Payment | Attestation Form | `source_data_json["Upload Your Accomplished Attestation Form Here"]` | No | No | No |
| Attestation & Payment | Attestation Status | Verification status, defaulting to `pending` when no verification row exists | No | Yes | Yes |
| Attestation & Payment | Remarks | Durable-participant Pending and Resolved counts | No | Yes | No |
| Attestation & Payment | Payment Status | Matched ticket's `payment_status` | No | Yes | Yes |
| Registrant Details | First Name | `registrants.first_name` | Yes | No | Yes |
| Registrant Details | Last Name | `registrants.last_name` | Yes | No | Yes |
| Registrant Details | Email Address | `source_data_json["Email Address"]` | Yes | No | No |
| Registrant Details | Mobile Number | `source_data_json["Mobile Number"]` | Yes | No | No |
| Registrant Details | Gender | `registrants.gender_raw` | No | Yes | No |
| Registrant Details | Birth Month | `registrants.birth_month_raw` | No | No | No |
| Registrant Details | Birth Year | `registrants.birth_year_raw` | No | No | No |
| Registrant Details | Life Stage | `registrants.life_stage_raw` | No | No | No |
| Registrant Details | Satellite | `registrants.satellite_name` | No | Yes | No |
| Logistics | Shirt Size | `source_data_json["Shirt Size"]` | No | Yes | Yes |
| Logistics | Transportation To MMRC | `source_data_json["Transportation From Ccf To Mmrc"]`, with `Transportation To MMRC` fallback | No | Yes | No |
| Logistics | Transportation From MMRC | `source_data_json["Transportation From Mmrc To Ccf"]`, with `Transportation From MMRC` fallback | No | Yes | No |
| Logistics | Plate Number | `source_data_json["Plate No"]`, with `Plate Number` fallback | No | No | No |
| Attestation & Payment | Last Reviewed By | Reviewer username | No | No | No |
| Attestation & Payment | Last Reviewed At | Verification `updated_at` | No | No | No |

The table intentionally excludes medical details, allergies, emergency-contact
details, full residential addresses, Dgroup leader contacts, and monetary
fields. Admin Tables remains the authorized full-source inspection surface.

## Filter fields

All Registrations filters are categorical, server validated, and composable.
The available values are queried from the selected Event and batch scope.

| UI filter | Request field | Value source |
|---|---|---|
| Gender | `gender` | Distinct `registrants.gender_raw` values |
| Satellite | `satellite` | Distinct normalized/final `registrants.satellite_name` values |
| Shirt Size | `shirt_size` | Distinct supported Shirt Size source values |
| Transportation To MMRC | `transportation_to_mmrc` | Distinct supported transportation-to source values |
| Transportation From MMRC | `transportation_from_mmrc` | Distinct supported transportation-from source values |
| Attestation Status | `attestation_status` | Fixed `Pending`, `Verified`, and `Invalid` choices |
| Remarks | `remarks` | Fixed `Has Pending Remarks` choice |
| Payment Status | `payment_status` | Distinct matched-ticket payment statuses |

### Supported operators

| Operator | UI label | Behavior |
|---|---|---|
| `equals` | Equals | Case-insensitive exact match |
| `in` | Is Any Of | Case-insensitive match against any selected value |
| `is_empty` | Is Empty | Value is null or blank |
| `is_not_empty` | Is Not Empty | Value is neither null nor blank |

Filters are combined with logical `AND`. For example:

```text
gender equals "Female"
AND satellite equals "B1G Cebu"
AND payment_status equals "Payment Validated"
```

The JSON query representation is:

```json
[
  {"field": "gender", "operator": "equals", "value": "Female"},
  {"field": "satellite", "operator": "equals", "value": "B1G Cebu"},
  {
    "field": "payment_status",
    "operator": "equals",
    "value": "Payment Validated"
  }
]
```

The server accepts at most 20 filter objects per request. It rejects unknown
fields, non-filterable columns, and operators outside the allow-list. Values
are passed as database parameters and are not interpolated into SQL.

### Attestation quick filters

The **All**, **Pending**, **Verified**, and **Invalid** buttons use the same
`attestation_status` filter contract:

| Quick filter | Applied behavior |
|---|---|
| All | Removes Attestation Status filters |
| Pending | Adds `attestation_status equals pending` |
| Verified | Adds `attestation_status equals verified` |
| Invalid | Adds `attestation_status equals invalid` |

Changing a quick filter preserves other filters and the Event/batch context,
then returns to page 1.

## Server-side search

The `search` query parameter, with `q` accepted as an alias, performs a
case-insensitive contains match across:

- Registration Code
- Ticket Code
- First Name
- Last Name
- Email Address
- Mobile Number

The search text is trimmed and limited to 200 characters. Search is combined
with filters using `AND`; the six searchable fields are combined with `OR`.

## Sorting

| Sort field | Request value |
|---|---|
| Registration Code | `registration_code` |
| Ticket Code | `ticket_code` |
| First Name | `first_name` |
| Last Name | `last_name` |
| Shirt Size | `shirt_size` |
| Attestation Status | `attestation_status` |
| Payment Status | `payment_status` |

`direction` may be `asc` or `desc`. The default is Registration Code ascending.
An unsupported sort field or direction falls back safely to the default.
`registrants.id ASC` is always appended as a deterministic tie-breaker.
Registration Code and Ticket Code are retained for compatibility with the
server query contract but have no visible table sorting controls.

## Pagination

Pagination is performed by the server after Event/batch scoping, search, and
filtering.

| Parameter | Allowed/default behavior |
|---|---|
| `page` | Positive integer; defaults to 1 and is clamped to the available page count |
| `per_page` | `25`, `50`, or `100`; defaults to `50` |

The response includes total records, page count, displayed start/end positions,
and previous/next availability. The browser never downloads the complete
registration dataset merely to paginate it.

Remark bodies are likewise excluded from this response and loaded only when an
operator opens the scoped modal. Counts come from one grouped subquery, and the
test suite verifies that adding remarks does not increase the number of SELECT
statements used to load a Registrations page.

## Query parameters and URL state

| Parameter | Purpose |
|---|---|
| `batch` | Active, historical, or all-batches scope |
| `search` / `q` | Global server-side search |
| `filters` | JSON array of allow-listed filters |
| `sort` | Allow-listed sort field |
| `direction` | `asc` or `desc` |
| `page` | Current page |
| `per_page` | Rows per page |

The page preserves this state in the URL. Search and filter changes reset the
page to 1. No registration row contents are added to the URL beyond search and
filter values deliberately entered by an authorized operator.

## Query pseudocode

The following pseudocode describes the implemented query composition without
being executable SQL:

```text
function get_registration_page(event_id, active_batch_id, request):
    require capability "view registrations"
    assert event exists

    batch_scope = resolve_batch_scope(
        event_id,
        request.batch,
        active_batch_id
    )

    query = registrants
        join import_batches on import_batches.id = registrants.batch_id
        join events on events.id = import_batches.event_id
        left_join tickets on (
            tickets.batch_id = registrants.batch_id
            and tickets.ticket_code = registrants.ticket_code
        )
        left_join attestation_participant_registrants as mapping on (
            mapping.batch_id = registrants.batch_id
            and mapping.registrant_id = registrants.id
        )
        left_join attestation_verifications on (
            attestation_verifications.event_id = events.id
            and attestation_verifications.attestation_participant_id =
                mapping.attestation_participant_id
        )
        left_join grouped_registrant_remark_counts on (
            grouped_registrant_remark_counts.event_id = events.id
            and grouped_registrant_remark_counts.attestation_participant_id =
                mapping.attestation_participant_id
        )
        left_join users as reviewer on (
            reviewer.id = attestation_verifications.updated_by_user_id
        )

    query.where(events.id equals parameter(event_id))

    if batch_scope is one batch:
        query.where(registrants.batch_id equals parameter(batch_scope))
    else if batch_scope has no active batch:
        query.where(FALSE)
    // "all" adds no batch predicate; the Event predicate still applies.

    if request.search is not blank:
        query.where(any searchable column contains parameter(request.search))

    for each validated_filter in request.filters (maximum 20):
        query.where(build_allow_listed_parameterized_filter(validated_filter))

    total = count(query)
    summary = count_requirement_states(query)

    sort_column = allow_listed_sort_or_registration_code(request.sort)
    sort_direction = asc_or_desc_else_asc(request.direction)

    rows = query
        select focused_registration_columns
        order_by sort_column sort_direction, registrants.id ascending
        limit validated_page_size
        offset calculated_page_offset

    for each row:
        row.attestation_form = safe_http_or_https_url_or_null(
            row.attestation_form
        )

    return columns, filter_options, rows, summary, query_state, pagination
```

Summary cards use the same scoped and filtered query conditions as the rows:

- Total Registrations
- Attestation Pending
- Attestation Verified
- Attestation Invalid
- Payment Validated

## Display behavior

- The unified control bar keeps the selected Event, batch scope, server-side
  search, Filters, Columns, and top-level Reset actions together. Reset returns
  search, filters, quick filters, sorting, pagination, and batch scope to their
  defaults while preserving the selected Event.
- Advanced filters are staged in a right-side drawer. **Apply Filters** commits
  the staged selection; closing the drawer leaves the current query unchanged.
  Applied filters remain visible as individually removable chips outside the
  drawer, and large Satellite option lists provide an in-drawer search field.
- The table uses a sticky header inside its own vertically and horizontally
  scrollable region. Only supported visible fields expose sort buttons, with
  `aria-sort` reflecting the current direction. Pagination remains server-side
  and identifies the current page accessibly.
- Initial loading uses a stable table skeleton. Subsequent refreshes retain the
  table with a busy treatment, while empty, no-active-batch, and request-error
  states provide distinct operator guidance. Filtered empty results can clear
  search and filters directly, and request failures provide a Retry action.
- Table interactions add browser history entries; Back and Forward restore the
  batch, search, filter, sort, page, and rows-per-page state from the URL.
- Final component polish is scoped to the Registrations panel, advanced-filter
  drawer, and Attestation Review modal. It uses the approved B1G red, burgundy,
  warm-cream, and rose tokens while retaining green, amber, and red semantic
  status meanings.
- The **Attestation Form** button opens the in-page Attestation Review modal
  before the external document request begins, so registrant and verification
  context remain immediately available during loading.
- The **Remarks** action shows `No Remarks`, Pending, and Resolved counts without
  loading note bodies into the paginated table response. Its modal fetches the
  scoped records on demand, renders Pending first, and lets authorized operators
  create or resolve notes with immediate count refresh.
- A safe `http://` or `https://` value is attempted as an image preview. When
  the browser cannot display it as an image, the modal shows a clear fallback
  and a safe **Open Original** action using `target="_blank"` and
  `rel="noopener noreferrer"`.
- Loaded images default to Fit to View. The document toolbar supports 25%–300%
  zoom in 25-point steps, 100% natural size, and return to Fit. Rendered image
  dimensions—not CSS transforms—drive document-only horizontal and vertical
  scrolling.
- Blank, malformed, `javascript:`, `data:`, and `file:` attestation values are
  shown as preview unavailable and never become links.
- A missing ticket keeps the registration row and displays Payment Status as
  `—`.
- No verification record is displayed as **Pending**, with reviewer and review
  time shown as `—`.
- Imported registration fields are read-only. Only the separate,
  application-owned Attestation Status can be changed by an authorized
  Administrator or Registration operator inside the review modal. Other
  permitted viewers receive the preview without a functional Save action.
- The three column groups can be shown or hidden as units, with visibility
  stored locally in the browser and restored by **Reset to Default**.
- The page provides no CSV/XLSX export and does not log registration row
  contents.
