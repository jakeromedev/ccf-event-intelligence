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

| Metric | Definition | Source fields | Unknown/conflict behavior |
| --- | --- | --- | --- |
| Registered Participants | Count of eligible curated participants in the selected snapshot after filters. | `curated_registrants.registration_type` | Not applicable. |
| Checked In | Eligible curated participants with Phase 1 `checked_in = true`. | `curated_registrants.checked_in`, derived from Generated Tickets `Check-in Date Time` | Missing check-in is Not Checked In. |
| Not Checked In | Registered Participants minus Checked In. | Same as above. | Always reconciles; never negative. |
| Attendance Rate | `Checked In / Registered Participants × 100`; withheld for suppressed numerator/denominator and absent when denominator is zero. | Same as above. | No division by zero. |
| Payment Status | Distribution of Generated Ticket `Payment Status`; Buyer `Payment Status` is fallback only when Ticket status is blank. | Generated Tickets `Payment Status`; Buyers `Payment Status` | Blank is Unknown; disagreeing merged sources are Conflicting / multiple values. |
| Payment Method | Distribution of the matched Buyer's payment method. | Buyers `Payment Method` | Blank/unmatched Buyer is Unknown; merged-source disagreement is Conflicting / multiple values. |
| Occupation | Frequency of the structured Registrant occupation answer. No occupation taxonomy is inferred. | Registrants `Occupation` | Blank is Unknown; `Others` remains a source category. |
| Dgroup | Dgroup Leader when membership=Yes and leadership=Yes; Dgroup Member when membership=Yes; Not in Dgroup when membership=No and leadership is not Yes. | Registrants `Are You Part Of A Discipleship Group`; `Are You Leading A Discipleship Group` | Both blank is Unknown; logically inconsistent answers are Conflicting / multiple values. |
| Home Area | Frequency of the structured Home Area answer. Full addresses and free-text address parsing are not used. | Registrants `Home Area` | Blank is Unknown; `Others` remains a source category. |

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

## Reconciliation and testing

The service returns explicit reconciliation flags for distribution totals and
`checked_in <= registered`. Automated coverage verifies conservative
normalization, Unknown values, combined filters, rejected invalid filters,
small-group suppression, absence of raw PII in APIs, Event isolation,
chronological snapshot behavior, and explicit Event comparison.

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
