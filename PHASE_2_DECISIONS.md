# Phase 2 Decision Register

This register separates product-owner decisions from engineering choices. A
`Decision Required` entry is intentionally unresolved; it must not be inferred
from a code default. The release approver should record a decision, owner, date,
and evidence before production acceptance.

## Product and operational decisions

| ID | Decision | Status | Current safe behavior |
|---|---|---|---|
| P2-01 | Phase 2 owner | **Decision Required** | Unassigned role placeholder is used in runbooks. |
| P2-02 | Target production environment/platform | **Decision Required** | A portable OCI container is provided; vendor deployment remains unspecified. |
| P2-03 | Target/release date | **Decision Required** | No date is claimed. |
| P2-04 | Expected number of users | **Decision Required** | No capacity commitment is claimed. |
| P2-05 | Expected traffic and concurrency | **Decision Required** | Gunicorn sizing is configurable and must be load-tested against the approved target. |
| P2-06 | Expected import volume and maximum representative dataset | **Decision Required** | Existing 32 MiB request limit is configurable; no volume SLA is claimed. |
| P2-07 | Required uptime/SLA | **Decision Required** | Health and monitoring integration points exist, but no SLA is invented. |
| P2-08 | Recovery point objective (RPO) and recovery time objective (RTO) | **Decision Required** | Backup frequency and restoration acceptance cannot be finalized. |
| P2-09 | Whether approved standard users may modify Event settings and imports/batches | **Decision Required** | Staging/production default to administrator-only mutation. Development/testing preserve the Phase 1 behavior. Set `CCF_STANDARD_USER_MUTATIONS_ALLOWED=1` only after approval. Batch deletion remains administrator-only regardless. |
| P2-10 | Final production release approver | **Decision Required** | A role placeholder is used; no person is fabricated. |

Additional governance decisions remain required for backup frequency,
retention periods, backup storage location, encryption/key ownership, data
retention periods, log retention, and incident contacts. These depend on P2-01,
P2-02, P2-07, and P2-08 and are tracked in the operational documents.

## Current authorization boundary while P2-09 is open

Privileged operations remain deny-by-default. Navigation visibility is not the
security boundary; the same policy is enforced on direct endpoint requests.

| Capability | Administrator | Approved standard user in staging/production |
|---|---|---|
| View accessible Events, Dashboard, Data Quality, satellite analytics, and import history | Allowed | Allowed |
| Change Event settings or Satellite Datasets | Allowed | Denied |
| Upload, validate, process, activate, or otherwise mutate imports/batches | Allowed | Denied |
| Delete an eligible inactive batch | Allowed | Denied unconditionally |
| View Admin Tables or curated source rows | Allowed | Denied |
| View/approve users or initialize/recover the administrator | Allowed; initialization/recovery is terminal-only | Denied |

If the product owner approves broader Event/import privileges, record the
approved operations and scope against P2-09, update the staging/production
configuration intentionally, and add regression/UAT evidence for every newly
allowed endpoint. Approval would not by itself grant Admin Tables, user
management, administrator recovery, or batch deletion.

## Engineering decisions

| Decision | Rationale |
|---|---|
| Gunicorn `gthread` WSGI runtime | It directly hosts the existing synchronous Flask application, supports graceful `SIGTERM`, and adds no framework rewrite. |
| Production OCI container | It is portable while the target platform is unresolved and keeps the development `run.py` workflow intact. |
| Alembic migrations run as a separate release step | Multiple web workers must never race schema changes; startup only verifies connectivity and the exact migration head. |
| Explicit `ProxyFix` hop counts, default zero | Forwarded headers are trusted only when the deployment declares the exact trusted proxy chain. |
| JSON operational logs to stdout in staging/production | Vendor-neutral collection works with container platforms and avoids local log-file lifecycle coupling. |
| Public liveness/readiness with minimal JSON | Orchestrators can monitor the process and MySQL/schema dependency without authentication redirects or confidential details. |
| Logical MySQL backups plus checksum manifest | This is reproducible and portable; storage encryption, frequency, and retention remain governance decisions. |
| No automatic retention deletion | Historical and personal data must not be deleted until policy and ownership are approved. |

## Approval record template

For each resolved item, replace `Decision Required` with `Approved`, record the
approved value, accountable role/person, approval date, and link to the decision
evidence. A production release is not Phase 2 complete while any P2-01 through
P2-10 item remains unresolved.
