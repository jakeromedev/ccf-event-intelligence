# Phase 2 Verification Record

This record separates engineering verification from product approval, hosted
execution, target-environment acceptance, and human UAT. Evidence below was
collected on **2026-08-29** in a local disposable environment unless a row says
otherwise. It is not evidence that a production platform or organizational
policy has been approved.

## Result vocabulary

- **Pass — Automated:** an automated test executed successfully.
- **Pass — Local Rehearsal:** the production-mode behavior executed against the
  project-local disposable MySQL 8.4 server.
- **Blocked — Product Decision:** a value or policy requires accountable approval.
- **Blocked — Target Environment:** the control must be inspected on the selected
  staging/production platform.
- **Blocked — External Execution:** the repository cannot prove an external
  system outcome from this environment.
- **Decision Required:** the scenario depends on an unresolved decision register item.

## Automated release validation

| Gate | Executed result |
|---|---|
| Ruff static analysis | **Pass** — `ruff check app migrations scripts tests run.py`. |
| Python compilation | **Pass** — `python -m compileall -q app migrations scripts tests run.py`. |
| SQLite suite | **Pass** — 71 tests. |
| Disposable MySQL 8.4 suite | **Pass** — the same 71 tests. |
| Empty-MySQL migration | **Pass** — 16 test tables were removed from the explicitly named `ccf_events_test` schema; all four Alembic revisions upgraded to `a9d3c7e5f102`. |
| Migration drift | **Pass** — `alembic current`, `alembic heads`, and `alembic check` agreed; no new operations were detected. |
| Production configuration/schema check | **Pass** against the migrated disposable MySQL database. |
| Hosted CI workflow | **Pass — Hosted** — GitHub Actions run [33252156921](https://github.com/jakeromedev/ccf-event-intelligence/actions/runs/33252156921) at commit `8852f60` completed successfully; SQLite quality, MySQL integration, and container jobs all passed. |
| OCI image build/runtime | **Pass — Hosted** — the image built, excluded development/sensitive-local files, contained no injected runtime secret in its history, used UID 10001, exposed a writable staging path, migrated disposable MySQL as a separate command, started the production entrypoint/Gunicorn, passed Docker health plus live/ready probes, and stopped gracefully with exit code 0. Docker, Podman, and Colima remain unavailable locally. |

The two tests added in this acceptance iteration directly verify login lockout
and expiry recovery, and controlled import-processing failure with active-batch
preservation and secret-free structured metadata. Existing security, import,
curation, reconciliation, isolation, pagination, and authorization tests remain
enabled.

## Local deployment rehearsal

The procedure followed `DEPLOYMENT_RUNBOOK.md` as closely as the disposable
environment permits.

| Step | Result | Evidence or limitation |
|---|---|---|
| Prepare target and environment | **Pass — Local Rehearsal** | Dedicated `ccf_events_test` MySQL schema, private ignored staging path, production configuration, one Gunicorn worker/two threads. |
| Confirm database and migrate | **Pass — Local Rehearsal** | Clean Alembic upgrade through `a9d3c7e5f102`; startup schema check passed. |
| Pre-deployment backup | **Pass — Local Rehearsal** | Compressed logical dump and SHA-256 manifest created in a temporary local directory. This is not approved encrypted storage. |
| Start production runtime | **Pass — Local Rehearsal** | Gunicorn 23 `gthread`; Flask development server was not used. |
| Liveness/readiness | **Pass — Local Rehearsal** | Both returned HTTP 200 and minimal JSON. |
| Authentication and representative access | **Pass — Local Rehearsal** | Administrator login returned 302 to `/events`; Events, representative Dashboard, Data Quality, Admin Tables, and user management returned 200. Approved-user Events/Dashboard/Data Quality returned 200 while direct Admin Tables and user-management URLs returned 403. |
| Import safety | **Pass — Automated** | The complete MySQL suite exercised complete-set validation, atomic activation, reactivation, deletion restrictions, Event/batch isolation, and failed-batch preservation. A non-personal live import was not performed through the local Gunicorn process. |
| Structured logs | **Pass — Local Rehearsal** | Lifecycle, request, authentication, role-denial, and readiness failure events were emitted as JSON with IDs/categories/counts rather than credentials or profile data. |
| Graceful restart | **Pass — Local Rehearsal** | `SIGTERM` produced worker/application stop events; the process became unavailable, restarted, and readiness returned HTTP 200. |
| External HTTPS/proxy/storage controls | **Blocked — Target Environment** | Execute `TARGET_SECURITY_VALIDATION.md` after P2-02 is approved. |
| Immutable image execution | **Pass — Hosted** | GitHub Actions run `33252156921` exercised the production image. Deployment and rollback on an approved target remain blocked. |

This proves that the runbook can drive a disposable production-mode deployment.
It does not prove target-platform deployment repeatability.

## Rollback rehearsal

| Rollback type | Result | Evidence or limitation |
|---|---|---|
| Configuration validation/restore | **Pass — Local Rehearsal** | Production rejects a deliberately unsafe/default secret; restoring the validated production configuration passes the configuration/schema check. Security controls were not weakened. |
| Application process restart | **Pass — Local Rehearsal** | Graceful stop, observed unavailability, restart, and readiness recovery passed. |
| Previous immutable application revision | **Blocked — Target Environment** | A prior approved image/digest and deployment platform are not defined, so an actual revision rollback was not claimed. |
| Database compatibility check | **Pass — Local Rehearsal** | Current application and schema both reported `a9d3c7e5f102`. |
| Database downgrade | **Not attempted by design** | No release migration required reversal. The runbook requires review and a restored copy; unsafe or lossy downgrades use roll-forward or verified backup restoration. |

## Monitoring signal exercise

| Condition | Signal result | External alert result |
|---|---|---|
| Application unavailable | **Pass — Local Rehearsal:** after `SIGTERM`, the probe received no HTTP response (`000`); shutdown events were emitted. | **Blocked — External Execution:** no monitoring provider/channel is configured. |
| MySQL unavailable | **Pass — Local Rehearsal:** liveness stayed 200, readiness became 503 with only `{"status":"unavailable"}`, and `readiness_failed` recorded `database_unavailable`; readiness recovered to 200 after MySQL restarted. | **Blocked — External Execution:** no notification delivery path is configured. |
| Import processing failure | **Pass — Automated:** controlled failure preserved the previous active batch and emitted `import_processing_failed` with Event ID, batch ID, and error type; the injected secret string was absent. | **Blocked — External Execution:** repeated-failure threshold and notification delivery require approved monitoring. |

Signals have been exercised; alerts have not been delivered end to end. The
Phase 2 alert exit criterion therefore remains incomplete.

## Administrator UAT evidence

These are repeatable engineering/UAT-preparation results, not signed human UAT.

| Scenario | Result |
|---|---|
| Valid login, invalid login, safe redirect, lockout, lock expiry, logout, and session invalidation | **Pass — Automated**; valid production-mode login also passed locally. Human session-expiry observation remains **Blocked — Target Environment**. |
| Pending user visibility, approval, duplicate/single-admin constraints, unauthorized rejection | **Pass — Automated**; administrator user-management access returned 200 locally. |
| Event creation/opening, switching, settings, and Event/data isolation | **Pass — Automated**; representative Event access passed locally. |
| Three-file upload/validation, processing, activation, invalid failure, previous-active protection, history, reactivation, deletion restrictions | **Pass — Automated** against SQLite and MySQL. |
| Dashboard participant/volunteer/registration/check-in/target metrics, demographics, satellite analytics and Satellite Datasets | **Pass — Automated** against SQLite and MySQL. |
| Data Quality summaries, grouping, drill-down, independent ten-row pagination, and curation-quality data | **Pass — Automated**; representative page returned 200 locally. |
| Admin Tables authorization, search, filtering, sorting, pagination, batch scope, column visibility defaults, safe attestation links, and curated-source inspection | **Pass — Automated**; representative administrator page returned 200 locally. Browser interaction/sign-off remains **Blocked — Target Environment**. |
| Complete administrator human UAT sign-off | **Blocked — Target Environment** and final approver assignment. |

## Approved standard-user UAT evidence

| Scenario | Result |
|---|---|
| Login and normal accessible Events/Dashboard/Data Quality/satellite pages | **Pass — Automated** and representative local production-mode HTTP rehearsal. |
| Event and batch isolation | **Pass — Automated** against SQLite and MySQL. |
| Direct Admin Tables and user-management URLs | **Pass — Automated** and local production-mode HTTP rehearsal: HTTP 403. |
| Direct protected batch deletion | **Pass — Automated:** HTTP 403 for a standard user. |
| Event settings, Satellite Dataset mutation, and import mutation | **Decision Required (P2-09)**; current staging/production deny-by-default behavior is **Pass — Automated** for direct endpoints. |
| Complete approved-user human UAT sign-off | **Blocked — Target Environment** and final approver assignment. |

## Remaining Phase 2 classifications

### Blocked — Product Decision

P2-01 through P2-10 remain unresolved: owner, target platform, release date,
users, traffic/concurrency, import volume, uptime/SLA, RPO/RTO, standard-user
mutation policy, and release approver. Backup and retention owners, schedules,
locations, encryption/key policy, restore authority, monitoring thresholds,
contacts, and escalation channels also require approval.

### Blocked — Target Environment

External HTTPS and redirect behavior, trusted-proxy network boundary, cookie
transport, external secret provisioning, filesystem/volume permissions, MySQL
network/TLS/least privilege, backup-store encryption/access, actual immutable
deployment/rollback, target recovery exercise, collector delivery, and signed
administrator/approved-user UAT require a selected staging/production target.

### Blocked — External Execution

End-to-end monitoring alert delivery remains blocked because no approved
provider, threshold, notification channel, or recipient exists. Hosted CI and
container execution are no longer blocked.

## Readiness conclusion

Engineering, disposable-environment, hosted CI, and production-container gates
pass, and no failed application defect remains from this iteration. Phase 2 is
**Ready for Production Acceptance**: the remaining work is accountable product
decisions, target deployment/security/recovery/rollback evidence, external alert
delivery, and signed human UAT. It is not Phase 2 Complete, and this record does
not authorize Phase 3.
