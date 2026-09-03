# Manual Registrant Satellite Overrides

Satellite Settings supports administrator-approved Satellite assignments at the
stable Event + participant level. Open an Event's Satellite Settings, choose
**Registrants**, and use **Edit Satellite** on a participant row. The selector
contains only Satellites already configured in the canonical Hub hierarchy.

## Assignment behavior

The effective assignment order is:

1. manual override;
2. the current imported/canonical assignment;
3. a stored automatic assignment;
4. unassigned.

The imported Satellite remains batch-scoped source evidence. Saving a manual
override does not rewrite the registration row or the shared imported
`satellites` record. Replacement imports reconcile the new source row to the
durable `attestation_participants` identity and preserve every existing manual
assignment unchanged. Automatic Satellite synchronization may update the
shared imported link, but the manual effective assignment still takes priority.
Registrants with a manual override are reported as **Manual Assignment —
Protected** by Satellite Settings and are removed from the **Needs Review**
issue count. Their original imported mismatch remains preserved as source
evidence.

## Resetting an override

**Reset to Imported Satellite** is available only for a manual assignment and
requires a confirmation step. Reset uses the active batch's imported Satellite
only when it resolves to an existing configured canonical Satellite. If it does
not resolve uniquely, the participant becomes unassigned; reset never creates a
Hub or Satellite.

Repeated save and reset submissions are idempotent. The unique Event +
participant constraint prevents duplicate current assignments.

## Audit and access control

Every effective manual change and reset appends an immutable row to
`event_registrant_satellite_audits`, including previous and new Satellite name
snapshots and the acting user when available. Satellite Settings shows the last
administrator on current manual assignments.

Both mutation routes use the existing Satellite Settings administrator
capability and application-wide CSRF protection. The registrant list, canonical
Satellite rankings, Satellite registrant drilldowns, and curated registrant
detail resolve manual assignments as the effective Satellite.
