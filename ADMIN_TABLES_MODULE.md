# Admin Tables Module

Admin Tables provides detailed, event-scoped inspection of the application's
three required import datasets:

- Registrants
- Generated Tickets
- Buyers

Curated Registrants is a contextual tab within Registrants. Registration
Sources opens in a detail drawer and is not a separate navigation module.
Satellites and internal mapping/pivot tables remain outside Admin Tables.

## Data scope

Every query starts from the selected Event. The default scope is that Event's
active import batch. Administrators may intentionally select another batch or
all batches belonging to the same Event. Cross-Event batch IDs are rejected.

## Complete source rows

The normalized `buyers`, `tickets`, and `registrants` tables retain their
existing application columns. An additive `source_data_json` column preserves
the complete imported CSV row without changing normalized values or source
files. New imports populate it during processing; application startup safely
backfills historical rows from preserved staged CSVs when available.

## Shared query contract

`app/admin_tables.py` owns the reusable column catalog and server-side query
logic. The JSON endpoints support:

```text
batch, search, filters, sort, direction, page, per_page
```

Filters are a JSON array of field/operator/value objects. Bracket-style exact
filters such as `filters[gender_raw]=Female` are also accepted. Dataset names,
columns, operators, sorting directions, page sizes, and batch ownership are
allow-listed before SQL is built.

The browser stores column visibility only in local storage. Search, filters,
sorting, pagination, page size, view, and batch context remain in the URL.
The registrant attestation-form source field is visible by default and renders
valid HTTP(S) values as a concise external link; empty, malformed, and
non-HTTP(S) values render as the standard empty-state dash.

## Authorization and privacy

Page, data, and source-lineage routes all use the same backend authorization
decorator. In normal runtime, an approved administrator session is required.
The feature can be disabled or further restricted through:

```python
ADMIN_TABLES_ENABLED = False
ADMIN_TABLES_AUTHORIZER = lambda request: current_user.can_view_event_data
```

The sidebar uses the same access decision, but route protection does not rely
on navigation visibility. No download/export function was added, and source
data is not written to logs.
