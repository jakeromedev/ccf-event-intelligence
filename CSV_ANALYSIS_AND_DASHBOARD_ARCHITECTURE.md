# CCF Event Dashboard: CSV Analysis and Proposed Architecture

> **Historical discovery/proposal document.** Statements phrased as future
> requirements reflect the pre-implementation analysis. Current runtime,
> security, database, curation, demographics, cleanup, and deployment behavior
> is authoritative in `README.md`, `TECHNICAL_REFERENCE.md`, and the module
> documentation. The current application uses MySQL + SQLAlchemy + Alembic;
> SQLite is limited to isolated tests and historical transfer tooling.

## Executive Summary

Three CSV exports were analyzed:

1. `Aug20_26_0426PM_event_generated_tickets.csv`
2. `Aug20_26_0427PM_event_buyers.csv`
3. `Aug20_26_0432PM_event_registrants.csv`

The verified relationship is:

```text
Buyer / transaction
  Buyer Reference Number
        1
        │
        │ 0..many
        ▼
Generated ticket
  Ticket Code
        1
        │
        │ 0..1
        ▼
Registrant profile
```

Verified join keys:

- `buyers.Buyer Reference Number` → `tickets.Buyer Reference Number`
- `tickets.Ticket Code` → `registrants.Ticket Code`
- `Registration Code` is unique to the registrant export but does not match buyer references or ticket identifiers.
- The church-affiliation dashboard should be based on registrant rows, enriched with ticket/check-in and buyer/payment information through these joins.

Current church-affiliation result across all 4,334 registrant records:

| Classification | Count | % of registrant records |
|---|---:|---:|
| CCF Main | 1,280 | 29.53% |
| Local Satellites | 1,498 | 34.56% |
| International Satellites | 8 | 0.18% |
| All Satellite Churches | 1,506 | 34.75% |
| Non-CCF | 440 | 10.15% |
| Unknown/unanswered | 1,108 | 25.57% |
| Total | 4,334 | 100% |

CCF attendees total 2,786, or 64.28% of registrant records. Within CCF attendees:

- CCF Main: 45.94%
- All satellites: 54.06%

## 1. Dataset Analysis

### Generated Tickets

File: `Aug20_26_0426PM_event_generated_tickets.csv`

- 8,000 rows
- One row per generated ticket
- `Ticket Code` is complete and unique across all 8,000 rows.
- Ticket `Id` is also unique. `Control Number` has 4,800 distinct values across 8,000 rows; 3,200 later occurrences repeat a control number and should be reported as non-primary duplicate warnings.
- Contains ticket lifecycle, payment status, price, assignment, and check-in timestamps.

Important fields:

- Event: `Slug`, `Event Name`
- Ticket identity: `Id`, `Ticket Code`, `Control Number`
- Transaction relationship: `Buyer Reference Number`
- State: `Ticket Status`, `Payment Status`
- Commercial: `Price`, `Price Type`, `Price Name`
- Attendance: `Check-in Date Time`
- Lifecycle: `Assigned At`, `Created At`, `Updated At`

Status summary:

| Ticket state | Count |
|---|---:|
| Assigned + Payment Validated | 4,360 |
| Available + no payment status | 3,635 |
| Cancelled + Payment Cancelled | 5 |
| Total | 8,000 |

There are 3,869 checked-in tickets. Pre-event and post-event check-in fields are unused in this export.

### Buyers

File: `Aug20_26_0427PM_event_buyers.csv`

- 3,228 rows
- One row per purchase/payment transaction, not per participant
- `Buyer Reference Number` is complete and unique.
- One transaction can have multiple tickets through `Quantity`.

Important fields:

- Transaction identity: `Id`, `Buyer Reference Number`
- Buyer contact: `Buyer Name`, `Email Address`, `Mobile Number`
- Payment: `Payment Status`, `Payment Method`, `Payment Reference Number`
- Amounts: `Gross Amount`, `Service Charge`, `Net Amount`, `Amount Paid`
- Audit: `Validated By`, `Validated At`, failure fields
- Time: `Created At`, `Updated At`

Payment summary:

| Payment status | Buyers | Quantity |
|---|---:|---:|
| Payment Validated | 2,525 | 4,359 |
| Payment Failed | 700 | 1,168 |
| Payment Cancelled | 3 | 5 |

`Quantity` represents tickets requested or purchased and should not be treated as attendees.

### Registrants

File: `Aug20_26_0432PM_event_registrants.csv`

- 4,334 rows
- One row per ticket-linked registration record
- `Ticket Code` is complete and unique.
- `Registration Code` is complete and unique.
- Every row has `Ticket Status = Assigned`.

This is the participant/profile dataset and the correct source for:

- Church affiliation and satellite
- Name and participant contact details
- Gender
- Birth month/year
- Life stage
- Home area
- Occupation
- Discovery/marketing source
- Discipleship-group membership and leadership

## 2. Relationship Analysis

### Buyers to Tickets

Use the event-scoped relationship:

```text
(event, Buyer Reference Number)
```

Results:

- All 4,365 tickets with a populated buyer reference match a buyer.
- The remaining 3,635 tickets have no buyer reference; these are the available tickets.
- 2,528 buyer transactions have generated ticket rows.
- 700 buyers have no matching tickets in this ticket export. These are the 700 failed-payment buyer records.
- Buyer references are unique in buyers but repeat in tickets, confirming a one-to-many relationship.
- For 2,527 of the 2,528 matched transactions, buyer `Quantity` equals the number of generated tickets.
- One transaction reports quantity 1 but has two ticket rows.

`Buyer Reference Number` is a valid relational key when populated, but the application must use a left join and retain unlinked buyers and tickets. It is reliable for joining successful/generated-ticket transactions, not as a universal participant identifier.

The numeric prefix of every buyer reference also matches the buyer row `Id`, but that should be considered an implementation detail—not a substitute join key.

### Tickets to Registrants

Use the event-scoped relationship:

```text
(event, Ticket Code)
```

Results:

- All 4,334 registrant rows match exactly one generated ticket.
- Every registrant ticket code is unique.
- Every ticket code in the generated-ticket export is unique.
- 3,666 generated tickets have no registrant record.
- No registrant is orphaned.

This is a clean one-to-zero-or-one relationship in the current data.

### Registration Code

`Registration Code` is unique within the registrants file, but:

- It does not match `Buyer Reference Number`.
- It does not match ticket `Ticket Code`.
- It does not match ticket `Control Number`.

It should be stored as the registration entity's source identifier, not used to connect the current exports.

## 3. Data-Quality Findings

### Registrant Completeness

The largest issue is that a registrant row does not always mean an identified person:

- 1,108 rows have no church-affiliation response.
- 1,106 rows have no first name, last name, email, or mobile number.
- Email is populated on 3,226 rows but represents 3,146 distinct normalized values.
- Names are populated on 3,228 rows.
- The 1,108 blank-affiliation rows also have broad gaps across gender, birth data, life stage, home area, and occupation.

Record sources help explain this:

| Created by | Rows | Profile pattern |
|---|---:|---|
| Workshop Registration Form | 3,224 | Profiles and affiliation populated |
| Seeder | 1,041 | Mostly blank/placeholder records |
| Check-In Form | 69 | Mostly blank profile records |

The application should therefore report at least two measures:

- **Registrant records:** 4,334 unique ticket-linked registration rows
- **Profile-complete/identified registrants:** based on an explicit completeness rule

The second measure should not be labeled “unique people.” No stable person ID exists, and repeated emails do not necessarily prove duplicate people.

### Church-Affiliation Inconsistencies

Most responses are coherent:

- `Are You Attending Ccf = Yes`: 2,786
- `Are You Attending Ccf = No`: 440
- Blank: 1,108

Satellite type:

- Local Satellite: 2,780
- International Satellite: 8
- Blank: 1,546

Two records contain contradictory values:

- `Are You Attending Ccf = No`
- Satellite type = Local
- Local satellite = CCF Main

The explicit `No` response should take precedence. These records should be classified as Non-CCF while also receiving a data-quality warning.

There are no `Yes` records missing their satellite type or name in this snapshot.

### Satellite Values

The values are structured enough to support dynamic drill-down. Examples include:

- CCF Main: 1,282 raw rows, including the two contradictory Non-CCF answers
- North Edsa: 86
- Alabang: 85
- Fairview: 72
- San Pedro: 69
- Makati: 62
- BGC: 56
- Taytay: 55
- Las Pinas: 54
- Eastwood: 45
- Manila: 45
- Feliz: 36

International values are:

- Qatar 1: 4
- Singapore: 2
- Hong Kong: 1
- Los Angeles North: 1

The application should ingest these values dynamically. It should retain the raw spelling and support an optional alias table for future spelling, punctuation, or naming variations.

### Payment Issues

- Failed payments properly show zero amount paid.
- One validated transaction paid ₱800 more than its net amount.
- Five cancelled tickets exist.
- Revenue should be defined explicitly, preferably as validated `Amount Paid`, while also showing expected net amount and discrepancies.

### Privacy

The files contain names, emails, phone numbers, birth information, account/payment metadata, and attachment URLs. The application should include authentication, role-based access, import auditing, encrypted transport/storage, and avoid displaying raw personal information on aggregate dashboards.

## 4. Recommended Classification Rules

Apply these rules in precedence order:

1. **Non-CCF**
   - `Are You Attending Ccf`, normalized, equals `No`.
   - Ignore satellite fields for classification, but flag populated dependent fields as inconsistent.

2. **Unknown**
   - The CCF-attendance response is blank or not recognized.

3. **CCF Main**
   - CCF-attendance response is `Yes`.
   - Satellite type is `Local Satellite`.
   - Normalized local satellite value equals `CCF Main`.

4. **International Satellite**
   - CCF-attendance response is `Yes`.
   - Type is `International Satellite`.
   - International satellite is populated.

5. **Local Satellite**
   - CCF-attendance response is `Yes`.
   - Type is `Local Satellite`.
   - Local satellite is populated and is not `CCF Main`.

6. **Unknown CCF affiliation**
   - CCF-attendance response is `Yes`, but type or corresponding satellite name is missing or invalid.

The last category has zero records in the current export but should exist for future imports.

Classification should store:

- `affiliation_group`: Main, Satellite, Non-CCF, or Unknown
- `satellite_scope`: Local, International, not applicable, or unknown
- `satellite_name`: normalized value
- `satellite_name_raw`: original CSV value

## 5. Defining Registrants and Attendees

These terms should remain separate:

- **Generated tickets:** all 8,000 ticket inventory records
- **Assigned tickets:** 4,365 tickets that were assigned at some point
- **Registrant records:** 4,334 ticket-linked registrant rows
- **Paid/validated registrations:** determined through ticket payment status
- **Checked-in attendees:** 3,869 tickets with a check-in timestamp
- **Unique people:** not currently reliable because no stable person identifier exists

Recommendations:

- The initial dashboard should be titled **Registrants by CCF Affiliation** and use all 4,334 registrant records, including Unknown.
- Actual event attendance should use **checked-in ticket-linked registrants**.
- Assigned or payment-validated tickets should not be labeled as attendees.

Checked-in registrants by affiliation:

| Classification | Registrants | Checked in |
|---|---:|---:|
| CCF Main | 1,280 | 1,232 |
| Local Satellites | 1,498 | 1,461 |
| International Satellites | 8 | 8 |
| Non-CCF | 440 | 420 |
| Unknown | 1,108 | 748 |
| Total | 4,334 | 3,869 |

This supports an eventual dashboard toggle between Registrants and Checked in.

## 6. Proposed Data Model

Use immutable imports plus normalized analytical tables.

### Import and Audit Layer

#### `import_batches`

- Type: tickets, buyers, or registrants
- Original filename
- Checksum
- Uploaded timestamp and user
- Detected event
- Row counts and accepted/rejected counts
- Import status and validation report

#### `raw_import_rows`

- Import batch
- Row number
- Original JSON payload
- Validation errors

This preserves source evidence and permits reprocessing when rules change.

### Normalized Layer

#### `events`

- Internal ID
- Source slug
- Event name

#### `buyer_transactions`

- Event ID
- Source buyer ID
- Buyer reference
- Payment status and method
- Quantity and monetary values
- Source timestamps
- Import batch

#### `tickets`

- Event ID
- Source ticket ID
- Ticket code
- Buyer transaction ID, nullable
- Control number
- Ticket and payment status
- Price
- Assignment and check-in timestamps
- Import batch

#### `registrations`

- Event ID
- Registration code
- Ticket ID
- Source status
- Created and updated timestamps
- Import batch

#### `registrant_profiles`

- Registration ID
- Participant details
- Demographics
- Church questionnaire responses
- Discipleship fields

#### `satellites`

- Canonical name
- Scope: main, local, or international
- Active flag

#### `satellite_aliases`

- Raw normalized value
- Canonical satellite ID

#### `affiliation_classifications`

- Registration ID
- Derived category
- Satellite ID
- Classification-rule version
- Quality flags

#### `data_quality_issues`

- Entity and entity ID
- Issue code and severity
- Field and source value
- Import batch

Use internal surrogate keys with unique constraints on:

- `(event_id, buyer_reference)`
- `(event_id, ticket_code)`
- `(event_id, registration_code)`

Event scoping prevents collisions when future events reuse source identifiers.

## 7. Import Architecture

The importer should identify the file type by required header signatures, not filenames:

- Ticket export: `Ticket Code`, `Control Number`, `Buyer Reference Number`, and check-in fields
- Buyer export: `Buyer Reference Number`, `Quantity`, and payment/amount fields
- Registrant export: `Registration Code`, `Ticket Code`, and church-profile fields

Import flow:

```text
Upload
  → detect export type
  → validate schema
  → store immutable batch/raw rows
  → normalize values and timestamps
  → upsert source entities within event
  → rebuild relationships
  → classify affiliation
  → run quality checks
  → atomically publish the new dataset version
```

Newer exports should not immediately delete older data. Support two modes:

- **Snapshot replacement:** the newest complete export becomes active
- **Incremental append:** genuinely new entities are added and existing ones updated

Each upload should provide a preview and reconciliation report showing added, changed, unchanged, missing-from-new-snapshot, invalid, and orphaned records.

## 8. Initial Dashboard

### Filters

- Event
- Metric basis: Registrants or Checked in
- Satellite scope and name
- Gender
- Life stage
- Age group
- Home area
- Occupation
- Dgroup membership and leadership
- Registration date range
- Ticket status
- Payment status

### Summary Cards

- Total registrants
- CCF attendees
- CCF Main
- Satellite churches
- Non-CCF
- Unknown
- Checked in
- Attendance rate

### Charts

1. **Affiliation donut or 100% stacked bar**
   - Main
   - Local Satellite
   - International Satellite
   - Non-CCF
   - Unknown

2. **Satellite ranking**
   - Horizontal bar chart using dynamically imported satellite values
   - Local/international toggle
   - Searchable table for the complete list

3. **Registration versus check-in comparison**
   - Grouped bars by affiliation

4. **Data-quality panel**
   - Missing affiliation
   - Incomplete profiles
   - Inconsistent answers
   - Unmatched records

Clicking a chart segment should apply it as a filter, allowing combinations such as Eastwood + Female + Single + Dgroup Member.

## 9. Recommended Technology Stack

For this dataset size and the anticipated filter combinations:

- **Application:** Next.js with TypeScript and the App Router
- **Database:** PostgreSQL
- **Data access and migrations:** Drizzle ORM
- **Validation:** Zod
- **Charts:** Apache ECharts
- **UI:** Tailwind CSS with an accessible component system
- **Testing:** Vitest plus Playwright
- **Deployment:** Containerized application and managed PostgreSQL

Next.js can support the dashboard UI, upload routes, and server-side aggregation in one deployable application. PostgreSQL provides durable relational constraints and flexible analytical queries. ECharts supports interactive filtering and drill-down without tying the data model to a fixed chart schema.

References:

- [Next.js App Router](https://nextjs.org/docs/app)
- [PostgreSQL constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [Drizzle ORM](https://orm.drizzle.team/docs/overview)
- [Apache ECharts datasets](https://echarts.apache.org/handbook/en/concepts/dataset/)

A separate Python analytics service is unnecessary initially. Add a background worker only when import volume or processing time justifies it.

## 10. Implementation Plan

1. Define metric terminology and approve the affiliation rules.
2. Create the database schema and versioned migrations.
3. Build CSV type detection, validation, preview, and batch auditing.
4. Implement snapshot reconciliation and normalized upserts.
5. Add relationships and automated quality checks.
6. Implement versioned affiliation classification.
7. Build filtered aggregation queries.
8. Build summary cards, the affiliation chart, and satellite drill-down.
9. Add checked-in mode and attendance-rate calculations.
10. Add demographic, payment, revenue, and trend dashboards.
11. Add authentication, permissions, privacy controls, tests, and deployment.

Application implementation should begin only after the proposed definitions, classification rules, data model, and architecture are approved.
