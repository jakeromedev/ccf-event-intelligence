# Operations, Data Governance, and Incident Response

## Operational interfaces

- `GET /health/live`: process liveness, `{"status":"ok"}`.
- `GET /health/ready`: MySQL connectivity and exact Alembic-head readiness;
  returns HTTP 503 with only `{"status":"unavailable"}` on failure.
- staging/production stdout logs: newline-delimited JSON with request IDs,
  durations, safe IDs/counts/statuses, and error categories.
- `X-Request-ID`: a validated incoming value or server-generated identifier,
  returned on responses for correlation.

Logs cover application lifecycle, request completion, safe authentication
failure categories, readiness failure, unexpected server errors, and import
validation/processing/activation status, duration, batch/Event IDs, row counts,
and validation counts. The formatter allow-lists operational fields. Do not add
names, emails, phones, addresses, birth values, source identifiers/raw rows,
attachment contents/URLs, filenames/paths, passwords, sessions, CSRF values, or
database URLs. Stack traces and exception strings are not emitted by the common
production failure events.

## Monitoring integration and recommended alerts

The platform is **Decision Required**. Standard HTTP probes and JSON stdout are
vendor-neutral integration points. Configure and exercise, at minimum:

| Signal | Recommended alert concept |
|---|---|
| Liveness unavailable | Multiple consecutive probe failures across healthy routing paths. |
| Readiness HTTP 503 | Instance cannot serve normal traffic; correlate `readiness_failed` reason and MySQL monitoring. |
| Database unavailable | Readiness failures plus database-native availability/connection alarms. |
| Repeated import failure | More than the approved threshold of `import_validation_failed`, `import_processing_failed`, or `import_activation_failed` events in the approved window. |

Thresholds, notification channels, on-call ownership, maintenance suppression,
and escalation timings are **Decision Required**. Written alerts are not
considered verified until safely triggered in the target monitoring environment
and receipt/recovery are recorded.

## Data lifecycle and retention governance

No automatic deletion is introduced while durations are unresolved.

| Category | Retained data and purpose | Personal data | Current deletion behavior | Proposed control | Owner / period / status |
|---|---|---|---|---|---|
| Staged uploads | Complete source files retained for batch traceability, reprocessing, and investigation. | **High:** registration rows, contact/birth/payment fields, and attachment URLs may occur. | Removed only when an administrator deletes an eligible batch; cleanup is confined to the staging root. No time-based deletion. | Private encrypted volume, access audit, legal-hold exception, and approved scheduled cleanup only after traceability requirements are met. | **Decision Required — Staged Upload Owner and Retention Period** |
| Processed source rows/files | Normalized rows and `source_data_json` preserve source truth and curated lineage. | **High:** names and complete source data may be present. | Cascades only through approved Event/batch deletion; no automatic retention deletion. | Approved source-record retention and auditable deletion procedure. | **Decision Required — Source Data Owner and Retention Period** |
| Inactive batches | Historical processed datasets support rollback, audit, and comparison with the active batch. | **High:** batch children contain personal data. | Preserved by default; administrator deletion excludes active/processing/validating batches. | Approved minimum/maximum history, legal hold, and deletion authorization. | **Decision Required — Batch Owner and Retention Period** |
| Attestation verification metadata | Current Pending/Verified/Invalid state, reviewer user ID, and review timestamps support registration operations. | **Moderate:** no form contents are copied, but state is linked to a personal registration and operator account. | Retained for the life of its registration; registration/batch deletion cascades it. Reviewer deletion retains state/time and clears reviewer ID. No independent time-based deletion. | Align with approved source-registration/batch retention, preserve during legal hold, and decide whether future full history requires a separate policy. | **Decision Required — Verification Metadata Owner and Retention Period** |
| Operational logs | Request IDs, safe entity IDs, counts, status, durations, and error categories support diagnosis and alerting. | **Low by design:** identifiers remain operational metadata; the allow-list excludes profile data and secrets. | Application writes stdout and does not control collector deletion. | Collector access controls, approved retention, redaction review, and incident legal hold. | **Decision Required — Log Owner and Retention Period** |
| Historical exports | Any externally produced report/export retained for operational use. Phase 2 adds no export feature. | **Potentially high**, depending on the external file. | Outside application lifecycle; no automatic application deletion. | Approved export inventory, owner, encrypted storage, recipient controls, and deletion schedule before exports are authorized. | **Decision Required — Export Owner and Retention Period** |
| Database backups | Full logical database copy for disaster recovery. | **High:** includes all application personal data. | Backup scripts never delete existing backups; no schedule is configured. | Approved encrypted store, checksum/restore verification, legal hold, lifecycle deletion, and access review. | **Decision Required — Backup Owner and Retention Period** |

Until decisions are approved, preserve records, restrict access, and document
manual changes. Do not treat Git ignore as encryption or access control.

## Incident handling principles

Assign incident commander, operations owner, security/privacy owner, database
owner, and communications/release approver roles; actual contacts are
**Decision Required**. For every incident: establish timeline, contain safely,
preserve immutable logs/config/artifact/migration/backup evidence, avoid copying
personal data into tickets, record commands/results, and obtain approval before
destructive action.

### Application unavailable

Check external HTTPS, liveness, readiness, container lifecycle events, recent
release/config changes, and capacity. Remove unready instances from traffic;
restart gracefully or roll back the application only after preserving evidence.

### MySQL unavailable

Stop new imports/deployments, check database-native health/network/certificate/
capacity signals, preserve DB and app logs, and keep unready instances out of
traffic. Do not point production at another database or restore without target
confirmation and approval.

### Failed deployment or migration

Halt rollout. Preserve Alembic output and database revision. Do not retry a
partially understood migration or run `create_all`. Use `ROLLBACK_RUNBOOK.md`;
prefer compatible roll-forward when downgrade is unsafe.

### Repeated import failure

Stop retries that could amplify load. Record Event ID, batch IDs, stages,
counts, timestamps, and error categories—never raw rows. Confirm the previous
active batch remains active. Preserve staged files under restricted access for
approved investigation.

### Suspected credential compromise

Restrict access, rotate the affected secret in the secret manager/database,
invalidate sessions (administrator recovery resets its authentication version),
restart with the new secret where required, audit access, and preserve evidence.
Never log or transmit the old/new value.

### Administrator recovery

Use the terminal-only `admin-init` procedure in `DEPLOYMENT_RUNBOOK.md` with two-
person/approver oversight if policy requires it. Capture no plaintext password
outside the approved password manager.

### Suspected personal-data exposure

Immediately restrict the affected route, file, backup, log destination, or
account without deleting evidence. Preserve access logs and object metadata;
identify categories and scope using IDs/counts rather than reproducing rows.
Engage the assigned privacy/security roles and follow approved notification law/
policy; jurisdiction and contacts are **Decision Required**.

### Backup restoration

Quarantine the target, confirm environment/database, verify checksum, and follow
`BACKUP_AND_RECOVERY.md`. Do not overwrite production by default. Preserve both
the original failure evidence and restoration verification record.
