# Phase 1 — Core Event Dashboard

## Authoritative event scope

Every Phase 1 query follows one path:

```text
events.id
  -> that Event's active import_batches row
  -> ticket-linked registrants in that batch
  -> curated unique people with raw-source mappings
  -> overview and participant-only demographic aggregation
```

The three required Generated Tickets, Buyers, and Registrants CSV exports remain
the only import workflow. Dashboard data is not uploaded separately.

## Source mapping

| Dashboard meaning | Imported source |
|---|---|
| Registration identity | `Registration Code` (with event/batch database uniqueness); `Ticket Code` is the validated ticket relationship |
| Participant/Volunteer | explicit `Volunteer`/`Volunteers` word in `Ticket Name` or export `Event Name`; all other ticket-linked registrants are participants |
| Gender | `Gender` |
| Life Stage | `Life Stage` |
| Full DOB, when available | optional `Date of Birth` or `Birth Date` |
| Current export age source | `Birth Month` + `Birth Year` |

Email is never used as the registration count identity.

## Metric rules

- Unique Participants and Unique Volunteers count `curated_registrants` of
  their resolved type in the selected Event's active batch.
- Unique Registrants is Unique Participants + Unique Volunteers. Raw
  Registrations remains a separate ticket-linked source-row count.
- Participant Target is nullable event configuration, not registration data.
- Registration Progress is Participants / Participant Target. A null or zero
  target produces an unconfigured state. Remaining Slots never falls below zero.
- Gender is Male, Female, or Unknown.
- Life Stage is Single, Single Parent, Married, or Unknown. Observed `Separated`
  and `Widow/Widower` source values are retained analytically as Unknown rather
  than discarded.
- Age uses the configured Event Date. A full DOB gets day-accurate birthday
  handling. The current exports have month/year only, so their birthday is
  reproducibly treated as the first day of the birth month and the UI labels
  these rows as estimates.
- Age buckets are Below 20, 20–25, 26–30, 31–35, 36–40, 41+, and Unknown.
  Below 20 is included because the supplied dataset contains 20 legitimate rows
  in this population at the verified September 5, 2025 reference date.

All three demographic distributions retain Unknown and reconcile to Participants.

## Reconciliation

Run:

```sh
.venv/bin/python scripts/reconcile_phase1.py EVENT_ID
```

The command prints overview and category counts and exits nonzero if any of the
four Phase 1 invariants fail.

For the supplied B1G Converge 2025 exports at Event Date 2025-09-05:

- Unique Participants: 4,312
- Raw Registrations: 4,334
- Duplicate source records merged: 22
- Volunteers: 0 (no volunteer-labeled registration rows occur in this export)
- Gender: Male 783, Female 2,421, Unknown 1,108
- Life Stage: Single 3,024, Single Parent 71, Married 95, Unknown 1,122
- Age: Below 20 20, 20–25 640, 26–30 1,262, 31–35 808,
  36–40 280, 41+ 194, Unknown 1,108

These totals differ from the former raw-registration dashboard because the
curation contract merges 22 complete-identity duplicate rows and Phase 1 uses
the new age buckets rather than the former 18–24/25–34/etc. buckets.
Life Stage Unknown includes 1,108 blanks, 8 Separated responses, and 6
Widow/Widower responses. No values were manually adjusted to match Excel.

## Security and performance

The application currently has no authentication or role/policy layer. Phase 1
does not invent one; settings and dashboard routes therefore inherit the same
access model as the existing event workspace. Counts are grouped in the database, and
the participant profile is normalized in one bounded backend query. Raw records
are not sent to the dashboard browser or dashboard API.

## Deferred roadmap

Church/ministry and the later logistics/capacity and attendance/requirements
roadmap remain deferred. Satellite and Data Quality reporting now consume the
shared curation layer documented in `CURATION_LAYER.md`.
