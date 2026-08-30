# Phase 3 Decision Register

Status: **Phase 3 approved aggregate analytics complete; financial analytics deferred**
Last reviewed: 2026-08-30

This register separates product/governance authority from engineering facts.
An implementation may provide a safe capability without resolving the business
decision. `Decision Required` entries must not be treated as approval.

## P3-01 — Analytics priority

**Status: Deferred / not required for current Phase 3 scope**

| Candidate | Approved priority |
| --- | --- |
| Payment Status | Approved / implemented |
| Payment Method | Approved / implemented |
| Revenue | Deferred / not required for current Phase 3 scope |
| Occupation | Approved / implemented |
| Dgroup | Approved / implemented |
| Home Area | Approved / implemented |
| Historical trends | Approved / implemented |
| Cross-Event comparison | Approved / implemented |

Engineering has begun the source-derived, non-monetary aggregates because their
eligible population and fields can be traced directly to current imports.
Implementing them does not establish their organizational priority.

## P3-02 — Monetary definitions

**Status: Deferred / not required for current Phase 3 scope**

### Source-field audit — evidence, not a formula

The supplied files were inspected on 2026-08-30. These are candidate inputs;
their presence does not establish accounting meaning or authority.

| Candidate | Source export and field | Observed supplied-data behavior | Unresolved limitation |
| --- | --- | --- | --- |
| Ticket price | Generated Tickets — `Price` | 8,000 rows: 4,365 numeric, 3,635 blank, 851 zero; numeric range 0–800. | Ticket-level value; allocation and blank/zero meanings are not approved. |
| Price classification | Generated Tickets — `Price Type`, `Price Name` | Types include Regular, Buy X Get Y Free, and Bundle; names include Fixed Price, Buy 1 Take 1, bundled tickets, and Physical Ticket Price. | Promotions make naive per-ticket multiplication unsafe. |
| Ticket payment state | Generated Tickets — `Payment Status` | Payment Validated, Payment Cancelled, and blank occur. | No approved equivalence between Payment Validated and recognized/collected revenue. |
| Buyer gross amount | Buyers — `Gross Amount` | 3,228/3,228 numeric, none blank/invalid/zero; range 800–16,000. | Buyer/order-level, not participant-level; definition is not documented by the source. |
| Service charge | Buyers — `Service Charge` | 3,228/3,228 numeric; 1,872 zero; range 0–330. | Inclusion in Revenue is undecided. |
| Buyer net amount | Buyers — `Net Amount` | 3,228/3,228 numeric, none blank/invalid/zero; range 800–16,330. | The label alone does not prove accounting recognition. |
| Amount paid | Buyers — `Amount Paid` | 3,228/3,228 numeric; 700 zero; range 0–16,000. | Buyer-level amount; refunds, settlement, and participant allocation are undefined. |
| Buyer payment state/method | Buyers — `Payment Status`, `Payment Method` | 2,525 Validated, 700 Failed, 3 Cancelled; four populated payment methods. | Status is analytical today, not an approved accounting rule. |
| Payment reference | Buyers — `Payment Reference Number` | Populated on all 3,228 supplied rows, including states that may not represent collection. | Presence cannot be treated as proof of payment. |
| Discount reference | Buyers — `Discount Reference Number` | Blank on all 3,228 supplied rows. | Cannot explain promotional ticket prices or discounts in this dataset. |
| Refund | No dedicated source field | No refund amount/status column and no refund text was observed in status, remarks, or failure fields. | Absence of evidence is not a zero-refund rule. |
| Waiver/complimentary amount | No dedicated source field | No waiver amount or explicit waiver/complimentary marker was observed; zero-price tickets exist. | A zero price must not be assumed to be a waiver. |
| Currency | No field in any supplied export | No currency code/symbol column exists. | PHP or another currency cannot be assumed from repository evidence. |

The Registrants export contains no authoritative monetary field. Raw candidate
values remain immutable in imported source JSON; no normalized monetary column
or Revenue calculation has been added.

### Required decision contract

Every section below is retained as future reference for financial analytics.
It is not a blocker for the current Phase 3 release.

#### Expected Amount — Deferred / not required for current Phase 3 scope

Define the eligible population, authoritative source or formula, bundle and Buy
X Get Y allocation, and blank/zero/cancelled/complimentary treatment.

#### Paid Amount — Deferred / not required for current Phase 3 scope

Identify the authoritative collected-money field and states, refund semantics,
and allocation of one Buyer amount across tickets and curated people.

#### Revenue — Deferred / not required for current Phase 3 scope

Choose and name gross collections, net collections, expected ticket value,
recognized revenue, or another definition. Decide whether service charges are
inside or outside Revenue.

#### Payment Discrepancy — Deferred / not required for current Phase 3 scope

Approve operands, sign/direction, aggregation level, tolerance/rounding, and
null/unallocatable behavior. No subtraction formula is implied.

#### Refunds — Deferred / not required for current Phase 3 scope

Identify an authoritative refund source, define partial/full refund treatment,
and specify effects on Paid Amount, Revenue, and Discrepancy. The current
exports do not support treating refunds as zero.

#### Discounts and waivers — Deferred / not required for current Phase 3 scope

Define how promotions, discount references, zero-price tickets, complimentary
access, and approved waivers affect Expected Amount and Discrepancy.

#### Currency — Deferred / not required for current Phase 3 scope

Define the authoritative currency source/default and missing-currency behavior.
For multiple currencies, define separation or an approved conversion source,
date, and rounding policy. Currencies may not be silently combined.

The supplied Buyers export contains `Gross Amount`, `Service Charge`, `Net
Amount`, and `Amount Paid`; Generated Tickets contains `Price`. No source field
defines currency, and no approved rule identifies which field is authoritative
for a participant after cancellation, failure, refund, partial payment,
multi-ticket purchase, or service charges.

The product owner may approve each definition independently in a future
financial-analytics phase:

| Concept | Decision required |
| --- | --- |
| Expected Amount | Deferred / future financial analytics. |
| Paid Amount | Deferred / future financial analytics. |
| Revenue | Deferred / future financial analytics. |
| Payment Discrepancy | Deferred / future financial analytics. |
| Refunds | Deferred / future financial analytics. |
| Discounts / Waivers | Deferred / future financial analytics. |
| Currency | Deferred / future financial analytics. |

The application does not calculate or display any monetary metric. This is an
intentional scope decision, not an implementation defect. No `Price ×
Registrants` assumption is used.

## P3-03 — Report and export authorization

**Status: Deferred / optional**

Aggregate CSV reports and row-level exports are not part of the approved Phase
3 scope. If a future product release introduces downloads, the roles, row-level
field list, audit retention, and server-side enforcement rules will need to be
defined before implementation.

Current safe behavior is no Phase 3 download endpoint. Dashboard access does
not imply export permission, and Admin Tables remains administrator-only.

## P3-04 — Small-group privacy threshold

**Status: Engineering default implemented; organizational policy deferred**

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

Before any externally distributed reporting feature is introduced, the product
owner/privacy owner should approve the threshold, acceptable differencing risk,
and whether stricter rules are needed for multi-dimensional or cross-Event
views.

| Privacy question | Current engineering behavior | Approval status |
| --- | --- | --- |
| Minimum visible group | Configurable 1–100; temporary default 5 | Deferred / configurable engineering default |
| Display token | `< threshold` for a directly small non-zero group | Deferred / configurable engineering default |
| Small category labels | Combined as `Suppressed categories` | Deferred / configurable engineering default |
| Percentages | Withheld when they disclose a suppressed count | Deferred / configurable engineering default |
| Complementary suppression | Additional category/complementary values withheld when subtraction would reveal a small group | Deferred / configurable engineering default |
| Repeated-query differencing | Low-frequency filter values are omitted; broader differencing risk still needs privacy-owner review | Deferred / configurable engineering default |

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

No Phase 3 product decision needs to block the approved aggregate analytics
scope. If future financial analytics or exports are reintroduced, record the
approver, decision date, exact rule, and effective release here before treating
them as required scope.
