# Phase 3 Decision Register

Status: **Phase 3 engineering in progress**  
Last reviewed: 2026-08-29

This register separates product/governance authority from engineering facts.
An implementation may provide a safe capability without resolving the business
decision. `Decision Required` entries must not be treated as approval.

## P3-01 — Analytics priority

**Status: Decision Required**

| Candidate | Approved priority |
| --- | --- |
| Payment Status | Decision Required |
| Payment Method | Decision Required |
| Revenue | Decision Required |
| Occupation | Decision Required |
| Dgroup | Decision Required |
| Home Area | Decision Required |
| Historical trends | Decision Required |
| Cross-Event comparison | Decision Required |

Engineering has begun the source-derived, non-monetary aggregates because their
eligible population and fields can be traced directly to current imports.
Implementing them does not establish their organizational priority.

## P3-02 — Monetary definitions

**Status: Decision Required — Revenue remains disabled**

The supplied Buyers export contains `Gross Amount`, `Service Charge`, `Net
Amount`, and `Amount Paid`; Generated Tickets contains `Price`. No source field
defines currency, and no approved rule identifies which field is authoritative
for a participant after cancellation, failure, refund, partial payment,
multi-ticket purchase, or service charges.

The product owner must approve each definition independently:

| Concept | Decision required |
| --- | --- |
| Expected Amount | Eligible population, authoritative field/formula, treatment of complimentary/cancelled tickets, and rounding. |
| Paid Amount | Authoritative collected field, payment-status conditions, refunds, partial payments, and allocation of Buyer-level amounts to participants. |
| Revenue | Gross, net, expected, ticket-only, or another explicitly named concept. |
| Payment Discrepancy | Direction and exact formula after Expected and Paid Amount definitions are approved. |
| Currency | Authoritative source/default, handling of missing currency, and whether currencies may ever be converted. |

The application does not calculate or display any monetary metric until these
rules are approved. No `Price × Registrants` assumption is used.

## P3-03 — Report and export authorization

**Status: Decision Required — Downloads remain disabled**

- Aggregate CSV reports: decide between administrator-only and administrator +
  approved users.
- Row-level reports: decide between administrator-only, a future explicitly
  authorized reporting role, or disabled entirely.
- Decide the permitted row-level field list and audit retention if row-level
  exports are approved.

Current safe behavior is no Phase 3 download endpoint. Dashboard access does
not imply export permission, and Admin Tables remains administrator-only.

## P3-04 — Small-group privacy threshold

**Status: Decision Required — Final organizational threshold**

Engineering behavior exists and is configurable through
`CCF_ANALYTICS_MIN_GROUP_SIZE` (valid range 1–100). The temporary engineering
default is `5`; this is not an approved organizational policy.

Current behavior:

- non-zero exact counts below the configured threshold are returned as null and
  displayed as `< threshold`;
- low-frequency distribution labels are combined as `Suppressed categories`;
- low-frequency values are omitted from filter option lists;
- percentages that would reveal a suppressed count are withheld;
- secondary suppression prevents totals and complementary attendance values
  from reconstructing a small count by subtraction;
- Event totals and larger combined suppressed groups remain reconcilable;
- aggregate APIs never include raw registrant identifiers or contact data.

Before production acceptance of Phase 3, the product owner/privacy owner must
approve the threshold, acceptable differencing risk, and whether stricter rules
are needed for multi-dimensional or cross-Event views.

## P3-05 — Cross-Event access model

**Status: Current behavior documented; future Event ACL is a separate decision**

The current authorization model grants every approved operator access to the
normal dashboard for every Event; it has no per-user Event ACL. Cross-Event
comparison therefore requires authentication and an explicit list of 2–10
existing Event IDs, within that current access boundary. It never defaults to
all Events and never performs cross-Event person matching.

If per-user Event access is introduced later, the comparison service and API
must validate every selected Event against that ACL before returning any
aggregate. This implementation does not invent an ACL or weaken Admin Tables.

## Approval record

No Phase 3 product decision has an approved owner/date recorded in the
repository as of 2026-08-29. Record the approver, decision date, exact rule, and
effective release here before changing a status from `Decision Required`.
