# Sync Registration Satellites

## Purpose

Satellite Settings can reconcile an Event's imported registration Satellite
evidence with the existing canonical Hub and Satellite directory. The feature
only assigns `satellites.directory_id`; it never creates, renames, merges, or
deletes directory or imported evidence records.

Open the workflow from:

```text
/satellites/settings?event_id=<event_id>
```

The action is intentionally absent without Event context and requires the
`satellites.settings.manage` capability.

## Matching contract

The analyzer reads `Bg Satellite Hub` and then the matching Hub-specific field
from each registration's preserved `source_data_json`. It requires one exact
configured path:

```text
normalized configured Hub + normalized Satellite name
```

Normalization reuses Satellite Settings: Unicode NFKC, trimmed and collapsed
whitespace, and case-folded comparison. There is no fuzzy matching, automatic
Hub aliasing, or cross-Hub Satellite matching.

Results use these statuses:

- `Ready to Sync`
- `Already Synced`
- `Satellite Not Configured`
- `Hub Not Found`
- `Missing Satellite`
- `Ambiguous`
- `Conflict`

A `Conflict` is never overwritten. Aggregated evidence that resolves to more
than one Hub/Satellite interpretation is `Ambiguous` and remains unchanged.

## Administrator workflow

1. Select an Event and open Satellite Settings.
2. Choose **Sync Registration Satellites**.
3. Review source-record, represented-registration, ready, already-synced, and
   not-synchronized totals.
4. Filter and inspect individual not-synchronized registrations by reason.
5. Confirm only after reviewing the exceptions.
6. Inspect the completion summary and refreshed exception list.

The completion report shows newly synchronized Satellite rows, represented
registrations synchronized, already-synchronized rows skipped, unmatched rows,
and individual registrations still requiring attention.

## Transaction and concurrency safety

Review is read-only. Confirmation requires a one-time, session-bound review
token and re-runs the complete analysis rather than trusting displayed results.
On MySQL, confirmation locks the Event and canonical Hub/Satellite directory
rows before revalidation. Updates are additionally constrained to the selected
Event, active batch, imported Satellite ID, and a currently null
`directory_id`.

All eligible updates commit in one transaction. Any database failure rolls the
transaction back and displays an error stating that no changes were saved.
Repeated or duplicate confirmation submissions cannot create records or change
an existing correct link.

## Operational logging

Successful confirmations emit `registration_satellite_sync_completed` with:

- `event_id`
- authenticated `user_id`
- `matched_count`
- `skipped_count`
- `failed_count`

Registration identifiers, participant names, Hub answers, and Satellite
answers are deliberately excluded from synchronization logs.

## Routes

| Method | Route | Behavior |
| --- | --- | --- |
| `POST` | `/satellites/settings/sync/review` | Produces a read-only Event scan and one-time confirmation token |
| `POST` | `/satellites/settings/sync/confirm` | Revalidates and atomically updates valid `directory_id` links |

Both routes use the application's CSRF protection and Satellite Settings
management authorization.
