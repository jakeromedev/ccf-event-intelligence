# Phase 3 Reporting and Export Governance

Status: **Downloads disabled — product authorization required**
Last reviewed: 2026-08-30

This document records the actual reporting surface and the contract required
before downloads can be enabled. It does not grant export permission.

## Current supported reporting surface

| Surface | Format | Scope | Authorization | Personal data |
| --- | --- | --- | --- | --- |
| Event Analytics workspace | HTML | Explicit Event and active batch, with validated filters | Approved authenticated users under the current dashboard boundary | Aggregate only |
| Event analytics API | JSON | Explicit Event and active batch, with validated filters | Approved authenticated users | Aggregate only |
| Historical trends | HTML/JSON | Explicit Event; each active/inactive batch is an independent snapshot | Approved authenticated users | Aggregate only |
| Cross-Event comparison | HTML/JSON | Explicit selection of 2–10 Events | Approved authenticated users under the current all-Events dashboard model | Aggregate only |
| Downloadable aggregate report | None | Not available | Decision Required | Not applicable |
| Row-level export | None | Not available | Decision Required; most restrictive default | Not applicable |

There is no hidden CSV/XLSX route and no Reports download control. Admin Tables
provides administrator-only on-screen source inspection; it is not an export
permission and does not provide a Phase 3 download endpoint.

## Decisions required before aggregate CSV

The product owner must approve the roles/capability, allowed historical and
cross-Event scope, final privacy/differencing policy, report types/columns, and
audit ownership/retention. If approved, CSV is the preferred first format.

The endpoint must invoke the same `app/analytics.py` result used by the screen,
including the same Event, batch, validated filters, category labels,
suppression, count, and percentage. No export-specific metric formula or filter
implementation is permitted.

## Required aggregate schema and data minimization

An approved aggregate report should contain only fields needed to interpret the
aggregate: Event, batch, report type, metric, category, public count/display
value, public percentage, applied filter summary, and generated timestamp. It
must not contain names, birth dates, emails, phone numbers, residential
addresses, registration/ticket codes, attachment/attestation URLs, raw rows, or
hidden internal counts.

Suppressed values must remain suppressed. CSV cannot become an alternate path
to recover a count hidden by HTML or JSON.

## Required authorization and scope behavior

- Check authentication and export authorization independently on every request;
  hiding a button is insufficient.
- Check Event and batch ownership server-side.
- Historical exports must name one explicit Event and batch and retain snapshot
  semantics.
- Cross-Event exports must name 2–10 explicit Events and validate every Event;
  they must never default to all Events.
- Aggregate dashboard access must not imply row-level export access.

An explicit capability such as `analytics.export.aggregate` may be appropriate
after the role decision, but no RBAC redesign is justified before approval.

## Required file and spreadsheet safety

If CSV is approved:

- construct filenames from a server-generated slug, approved report type, and
  date, never a raw Event/filter label or path;
- allow only a constrained ASCII filename character set, remove path/control
  characters, cap length, and set an explicit `.csv` extension;
- protect source/user-derived text beginning (after leading whitespace) with
  `=`, `+`, `-`, or `@` against spreadsheet formula execution;
- return `text/csv` with an attachment `Content-Disposition` header;
- avoid retaining unnecessary file copies.

These are future implementation requirements, not claims about absent code.

## Required export audit metadata

If protected exports are approved, record only requesting user ID, Event ID,
batch ID, report type, aggregate/row-level classification, timestamp, validated
filters, and exported row count. Do not log report contents, source rows,
credentials, session/CSRF values, or personal data. Audit retention and owner
remain governance decisions.

## Row-level export gate

Row-level exports are not implemented. Approval must define an explicit role or
permission, exact allowed-column schema, purpose, Event/batch scope, auditing,
retention, and privacy/legal owner. It must not serialize Admin Tables wholesale.
Potentially sensitive fields include identity/contact data, birth information,
gender, location, Dgroup, payments, and attestation links; every allowed field
requires a documented purpose.

## Verification while downloads remain disabled

Automated tests confirm common aggregate and row-level download paths are absent
(HTTP 404), the Analytics UI contains no download control, and existing
aggregate APIs remain privacy-suppressed. Export authorization, filename,
formula-injection, audit, and report-reconciliation checklist items remain
incomplete because no approved export exists to implement or test.
