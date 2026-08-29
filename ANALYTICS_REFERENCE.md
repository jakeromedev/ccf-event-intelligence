# Advanced Analytics Reference

This document defines the implemented Phase 3 aggregate analytics contract.
All metrics use the centralized `app/analytics.py` service. The rendered page
and JSON APIs consume the same results; route handlers do not independently
recalculate metrics.

## Scope and eligible population

Unless a section says otherwise, the eligible population is:

```text
selected Event
  -> selected Event's active import batch
  -> curated_registrants.registration_type = participant
  -> one record per curated person
```

Merged raw registrations remain traceable through
`curated_registrant_sources`. Phase 3 reads source values but never modifies
them. Volunteers are excluded from participant analytics. `checked_in` reuses
the Phase 1 curated rule: true when any source registration in the curated group
matched a checked-in Generated Ticket.

## Implemented metric definitions

Every metric below uses the eligible curated-participant population defined
above and applies the configured suppression policy to public counts and
percentages.

| Metric | Definition / formula | Source export and field | Normalization and Unknown behavior | Suppression | Limitations |
| --- | --- | --- | --- | --- | --- |
| Registered Participants | Count of eligible curated participants after filters. | Derived curation — `curated_registrants.registration_type` | Only `participant`; not applicable to Unknown. | A non-zero filtered total below threshold is withheld. | Curated identity is Event/batch scoped, not global. |
| Checked In | Count with Phase 1 curated `checked_in = true`. | Generated Tickets — `Check-in Date Time`, through `curated_registrants.checked_in` | Missing check-in is Not Checked In; any checked-in source makes the curated person checked in. | Small and complementary values are withheld. | Uses the imported snapshot, not live gate state. |
| Not Checked In | `Registered Participants - Checked In`. | Same as Checked In | Never negative; zero denominator is safe. | Withheld with its complement when subtraction could disclose a small value. | Same snapshot limitation as Checked In. |
| Attendance Rate | `Checked In / Registered Participants × 100`; absent at zero denominator. | Same as Checked In | No separate attendance definition. | Withheld if numerator or denominator is suppressed. | Rounded only for presentation. |
| Payment Status | Count/eligible total by status. Ticket value is authoritative for this descriptive distribution; Buyer status is fallback only when Ticket is blank. | Generated Tickets — `Payment Status`; Buyers — `Payment Status` fallback | Trim/case normalization of observed statuses; blank is Unknown; merged-source disagreement is Conflicting / multiple values. | Small labels combine; count/percentage may be withheld. | `Payment Validated` is not renamed Paid and has no approved revenue meaning. |
| Payment Method | Count/eligible total by matched Buyer method. | Buyers — `Payment Method` | Conservative casing/spacing for observed methods; unmatched/blank is Unknown; merged-source disagreement is Conflicting / multiple values. | Small labels combine; count/percentage may be withheld. | Buyer-level method may cover several tickets. |
| Occupation | Count/eligible total by structured occupation answer; no inferred taxonomy. | Registrants — `Occupation` | Trim, whitespace/slash, and case normalization only; blank is Unknown; `Others` is retained. | Small labels combine; count/percentage may be withheld. | Free-text detail and `Occupation Others` are not exposed. |
| Dgroup | Leader when member=Yes and leader=Yes; Member when member=Yes; Not in Dgroup when member=No and leader is not Yes. | Registrants — `Are You Part Of A Discipleship Group`, `Are You Leading A Discipleship Group` | Explicit Yes/No only; both blank is Unknown; inconsistent/merged disagreement is Conflicting / multiple values. | Small labels combine; count/percentage may be withheld. | No membership inference from leader name, church, or other fields. |
| Home Area | Count/eligible total by structured Home Area. | Registrants — `Home Area` | Trim/case normalization; blank is Unknown; `Others` retained. | Small labels combine; count/percentage may be withheld. | Full addresses, `Home Area Others`, and geocoding are excluded. |

Payment labels retain the source business language. In particular, `Payment
Validated` is not renamed `Paid`, because that business equivalence is not yet
approved. Payment method, occupation, and Home Area normalization is limited to
trimming, whitespace collapsing, casing of known exact labels, and whitespace
around `/`. Semantically different labels are never merged by similarity.

## Combined filters

The analytics workspace accepts composable query parameters for:

- `satellite`
- `satellite_dataset`
- `gender`
- `life_stage`
- `age_group`
- `payment_status`
- `payment_method`
- `occupation`
- `dgroup`
- `home_area`
- `check_in`

Every value is validated against Event-scoped options before it is applied.
Low-frequency options are not exposed when privacy suppression applies. The
application uses bound SQL parameters and static JSON paths; raw filter text is
never interpolated into SQL. Query parameters preserve bookmarkable filter and
Event context. An individual chip removes one filter; Clear All removes every
filter. Filters do not carry across Event URLs.

## Attendance by dimension

Registration versus check-in is available by Gender, Life Stage, Payment
Status, Dgroup, Home Area, and Satellite. Each row uses the same eligible
participant set and provides Registered, Checked In, Not Checked In, and
Attendance Rate. A person associated with multiple satellites contributes to
each relevant satellite row; the satellite rows are therefore not intended to
sum to the Event participant total. Other dimensions reconcile one category per
eligible participant.

## Historical trends

Historical mode includes only processed snapshots in `active` or `inactive`
state for one explicit Event, ordered by batch creation time then batch ID. Each
row includes batch ID, created/processed/activation metadata, current status,
registered participants, checked-in participants, and attendance rate.

Snapshots are compared, never summed. A participant appearing in two imports is
not treated as two distinct participants within an Event-wide total. The chart
and accessible table use the same service response.

## Cross-Event comparison

Comparison requires 2–10 explicit Event IDs. It reports current active-snapshot
Registered, Checked In, Not Checked In, and Attendance Rate for each selected
Event. It does not silently select all Events. Current approved operators can
access every normal Event dashboard; see `PHASE_3_DECISIONS.md` for the future
per-Event ACL requirement.

Curated identifiers are Event/batch scoped. The comparison deliberately does
not match or count a person across Events as a global identity.

## Privacy suppression

`CCF_ANALYTICS_MIN_GROUP_SIZE` configures a value from 1 through 100. The
engineering default is 5 pending policy approval.

- Exact zero is safe and may be displayed.
- Exact non-zero values below the threshold are represented as `< threshold`.
- Small distribution labels are combined rather than listed.
- A combined suppressed bucket is exact only when the combined group itself
  meets the threshold.
- Secondary suppression hides an additional category or complementary
  attendance value when subtraction from an exact total would reveal a small group.
- Percentages capable of disclosing a suppressed exact count are withheld.
- Aggregate API responses contain no names, emails, mobile numbers, addresses,
  registration codes, ticket codes, or raw source rows.

Suppression reduces direct disclosure; it is not a substitute for an approved
organizational privacy review. Differencing policy remains P3-04.

## HTTP contract

| Endpoint | Purpose |
| --- | --- |
| `GET /events/<event_id>/analytics` | Rendered Event analytics workspace. |
| `GET /api/events/<event_id>/analytics` | Active-snapshot aggregate analytics and validated filters. |
| `GET /api/events/<event_id>/analytics/trends` | Historical snapshots for one Event. |
| `GET /analytics/compare?events=1,2` | Rendered explicit Event comparison. |
| `GET /api/analytics/compare?events=1,2` | Aggregate Event comparison API. |

All routes are covered by the global approved-user authentication guard.
Malformed filters return HTTP 400; missing Events return 404. No endpoint emits
row-level registrant data.

## Revenue and reporting limitations

Revenue, Expected Amount, Paid Amount, Payment Discrepancy, aggregate downloads,
and row-level downloads are not implemented. They are decision-gated in
`PHASE_3_DECISIONS.md`. The presence of raw monetary columns is not an approved
formula or currency definition.

The inspected monetary candidate fields and required decision contract are in
`PHASE_3_DECISIONS.md`. Actual and required future reporting behavior is in
`REPORTING.md`. No monetary metric or download endpoint is part of the current
API contract.

## Reconciliation and testing

The service returns explicit reconciliation flags for distribution totals and
`checked_in <= registered`. Automated coverage verifies conservative
normalization, Unknown values, combined filters, rejected invalid filters,
small-group suppression, absence of raw PII in APIs, Event isolation,
chronological snapshot behavior, explicit Event comparison, suppression on
active/trend/comparison endpoints, complementary-differencing protection, and
the absence of unapproved download routes.

No Phase 3 schema change is required: all classifications are derived at query
time from immutable imported data and the existing curation layer.

## Performance observation

On 2026-08-29, the complete active-snapshot service query over the supplied
4,312-person dataset completed locally against MySQL in 374.6 ms. This is a
development-machine observation, not a production SLA. The implementation uses
server-side scoped extraction plus one in-process aggregation pass; Redis,
Celery, materialized aggregates, and automatic caching were intentionally not
introduced. Production performance must be measured again at the approved
scale and target environment before any Phase 4 optimization decision.
