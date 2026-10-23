# Participant transportation — phases 1–4

Phase 1 provides the data model and Python service. Phase 2 adds the management
page, dashboard button, search/filters/pagination, and editing dialog. Imported
answers remain unchanged. Phase 3 connects dashboard totals to effective values
and adds the participant history viewer.

## Dashboard totals and history

Transportation Plan now counts the same durable participants as the management
page: everyone linked to the active import, once per trip, including missing
answers. Both surfaces use the shared resolver, so manual overrides take priority,
resets follow the active import, and conflicting imported answers remain explicit.
Other, not-reported and conflicting modes are shown separately from categorized
bus/carpool/public-transport totals. Percentages retain the categorized denominator.
The public dashboard receives these effective counts without exposing operators,
reasons, or management/history links. Counts are computed afresh on each request.

Choose **History** beside a participant to view newest-first updates, including
trip, set/reset action, before/after modes and sources, imported evidence at the
time, operator name snapshot, optional reason, and Manila timestamp. The route
`/events/<event_id>/transportation/<participant_id>/history` uses the same approved
admin/standard-user permission as editing and private/no-store responses.
Pages contain at most 50 entries, with an older-record cursor and a newest link.
History remains readable at its URL when a participant leaves the active import;
no history editing or deletion controls are exposed. Text is HTML-escaped.

Phase 4 covers release validation, the production migration/deployment, and
post-release health verification. Release checks: 285 full-suite tests passed
(one optional MySQL test skipped in that run), followed by 26 focused tests with
the dedicated MySQL database, including migration upgrade/downgrade and schema
parity. Ruff, JavaScript syntax, and whitespace checks passed. Browser visual
verification remains unavailable because the computer-use tool cannot read its
configuration file.

Released to Railway production on 2026-10-23 (Manila), deployment
`85e4d6b3-4d6d-4045-9956-ffd538804307` (`SUCCESS`). Deployment logs confirmed
the upgrade from `e9b4d7a2f603` to `f2c5e8a1b704` and successful production
configuration/database/schema checks. Live smoke checks returned healthy
liveness/readiness, HTTP 200 for login and transportation JavaScript, and login
redirects for unauthenticated transportation/history requests. No participant
transportation records were changed as part of production smoke verification.

## Management page

Open an Event's Transportation Plan and choose **Manage Transportation**, or
visit `/events/<event_id>/transportation`. Only authenticated, approved
administrators and standard users can access the page or detail/update endpoint.
Registration-only operators and public-dashboard visitors cannot access it.
The management link stays hidden in the public presentation, even for admins.

The page lists each durable participant in the active import once, including
those with no reported travel arrangements. It shows name, email, registration
codes, satellite (manual assignment if present, otherwise imported), both trip
modes and their sources, and the latest transportation update time/operator.
Search covers name, email, registration code, and satellite. Trip, mode, and
source filters are combined on the same trip; choosing “Either trip” does not
match a mode on one trip and a manual override on the other. Filters apply before
pagination, with 25, 50, or 100 results per page and stable ordering.

Choose **Edit** to load fresh values, select a new mode or **Use imported value**
for either trip, optionally add a reason, and save. **Keep current** leaves that
trip untouched. Cancel/close performs no write. A successful save preserves the
current search/filter/page URL. The dialog shows imported evidence independently
from current manual values. Stale revisions/imports receive HTTP 409 and require
reloading current values before another save. Network errors likewise require
reload to avoid replaying an uncertain save. The UI never sends an operator ID;
the server attributes writes to the signed-in account.

GET and POST `/events/<event_id>/transportation/<participant_id>` validate event
and active-import membership. POST requires CSRF and a JSON object containing
`changes`, `expected_batch_id`, `expected_revisions`, and optional `reason`.
Management responses use `Cache-Control: private, no-store`. Names, emails,
source answers, and reasons are rendered as text, not HTML.

## Stored state

Migration `f2c5e8a1b704` adds `participant_transportation` and
`participant_transportation_history`. Both use the existing stable
`attestation_participants` identity scoped to an Event, rather than a temporary
Registrant ID. Each direction (`to_mmrc`, `from_mmrc`) has independent state.

Manual modes are `bus`, `carpool`, `public_transportation`, `other`, and
`unreported`. `unreported` is an explicit manual choice. A null override means
“use the active import”, including after a reset. Reset rows retain their revision
so a stale form cannot accidentally reuse an earlier version number.

Effective values resolve manual overrides first, then the active batch's linked
source answers. Both supported provider header variants are read. Missing
answers resolve to `unreported`; different populated normalized answers resolve
to `conflicting` and retain their raw evidence. No response is chosen arbitrarily.
Manual `other` is a category; use the optional reason to explain a custom mode.

Replacement imports and batch switches do not rewrite manual state. After a
reset, the value follows whichever batch is active. If a participant disappears
from the active batch, their settings and history remain stored, but edits are
rejected until they reappear. Identity matching follows the existing import
reconciliation rules; changed/ambiguous identities are not merged by this module.

## Service contract

`app.transportation.resolve_transportation(db, event_id, participant_id)` returns
the active batch, membership flag, and both trip values, sources, imported
evidence, override modes, and revisions.

`update_transportation` accepts a `changes` dictionary (one or both directions),
an approved administrator/standard-user ID, the expected active batch ID, and
expected revisions for edited directions. Pass a mode to set it or `None` to
reset that direction. A reason is optional, trimmed, and limited to 2,000
characters. Saving the current effective mode or resetting an already imported
value does nothing and creates no history. Resetting a manual value is logged
even when the imported value happens to be the same.

Writes lock the Event, validate scope and actor, and reject stale batch/revision
values. Changes to both directions and their history records share a savepoint:
failure rolls back the entire edit. The caller must commit on success or roll
back its transaction. Phase 2 routes enforce authentication, capabilities, and
CSRF before calling the service and commit both changes/history together.

`transportation_history` returns newest-first entries, default 50 and maximum
100, with an optional `before_id` cursor. Each entry preserves direction, action,
revision, before/after effective and imported evidence, batch ID at the time,
operator ID/name snapshot, reason, and UTC timestamp. The history viewer uses
the existing Manila timezone formatting.

History has no update/delete service operations. Operator renaming or deletion
does not erase the name snapshot; batch deletion does not erase either settings
or history. Deleting the entire Event or its durable identity cascades to these
records, consistent with the existing Event lifecycle. Database administrators
retain normal direct database privileges; append-only behavior is enforced by
the application service, not database triggers.

## Verification and release

Tests cover independent trips, resets, explicit missing values, source conflicts,
duplicate sources, re-imports, activation and batch deletion, stale edits, actor
and event scope, audit rollback, caller rollback, history pagination and identity
retention. Migration tests verify constraints, metadata parity, upgrade and
downgrade; the optional MySQL tests use only `MYSQL_TEST_DATABASE_URL` whose
database name must contain `test`.

Railway runs `alembic upgrade head` in the existing pre-deploy step. No data backfill is
needed: existing registrations resolve directly from their imported answers.
For an application rollback, redeploy the previous application image and retain
the additive transportation tables, preserving any updates already recorded.
Downgrading to `e9b4d7a2f603` drops only the new tables, permanently discarding
transportation overrides/history; take a backup before using that rollback.
