# Phase 3 Decision Register

Status: **Phase 3 engineering in progress**  
Last reviewed: 2026-08-30

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

Every section below remains **Decision Required**, so Revenue remains disabled.

#### Expected Amount — Decision Required

Define the eligible population, authoritative source or formula, bundle and Buy
X Get Y allocation, and blank/zero/cancelled/complimentary treatment.

#### Paid Amount — Decision Required

Identify the authoritative collected-money field and states, refund semantics,
and allocation of one Buyer amount across tickets and curated people.

#### Revenue — Decision Required

Choose and name gross collections, net collections, expected ticket value,
recognized revenue, or another definition. Decide whether service charges are
inside or outside Revenue.

#### Payment Discrepancy — Decision Required

Approve operands, sign/direction, aggregation level, tolerance/rounding, and
null/unallocatable behavior. No subtraction formula is implied.

#### Refunds — Decision Required

Identify an authoritative refund source, define partial/full refund treatment,
and specify effects on Paid Amount, Revenue, and Discrepancy. The current
exports do not support treating refunds as zero.

#### Discounts and waivers — Decision Required

Define how promotions, discount references, zero-price tickets, complimentary
access, and approved waivers affect Expected Amount and Discrepancy.

#### Currency — Decision Required

Define the authoritative currency source/default and missing-currency behavior.
For multiple currencies, define separation or an approved conversion source,
date, and rounding policy. Currencies may not be silently combined.

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
| Refunds | Authoritative source and effects on Paid Amount, Revenue, and Discrepancy. |
| Discounts / Waivers | Promotion allocation and zero/complimentary/waiver behavior. |
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
No aggregate or row-level permission capability has been added because neither
the permitted roles nor the long-term role model has been approved. Any future
permission must be enforced server-side and must not be inferred from page
visibility or normal aggregate-dashboard access.

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

| Privacy question | Current engineering behavior | Approval status |
| --- | --- | --- |
| Minimum visible group | Configurable 1–100; temporary default 5 | Decision Required |
| Display token | `< threshold` for a directly small non-zero group | Decision Required |
| Small category labels | Combined as `Suppressed categories` | Decision Required |
| Percentages | Withheld when they disclose a suppressed count | Decision Required |
| Complementary suppression | Additional category/complementary values withheld when subtraction would disclose a small group | Decision Required |
| Repeated-query differencing | Low-frequency filter values are omitted; broader differencing risk still needs privacy-owner review | Decision Required |

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
repository as of 2026-08-30. Record the approver, decision date, exact rule, and
effective release here before changing a status from `Decision Required`.
