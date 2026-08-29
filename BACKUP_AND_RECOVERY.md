# MySQL Backup and Recovery

The database, dumps, and verification records may contain personal information.
Limit access, encrypt transport and storage, and never commit them. Backup
frequency, retention, storage location, encryption/key owner, backup operator,
and restore approver are **Decision Required**; no organization-specific values
are invented here.

## Engineering capability

The repository provides consistent logical backup, compression, checksum
manifests, guarded restore, target confirmations, production-restore opt-in,
schema verification, source/target count comparison, and recovery evidence.
These capabilities do not decide when backups run, how long they are retained,
or who may create, access, delete, or restore them.

## Organization-approved backup policy

No row below is approved merely because the tooling exists.

| Policy control | Required approved value | Current status | Acceptance evidence required |
|---|---|---|---|
| Backup frequency | **Decision Required — Backup Frequency** | Open governance decision | Approved schedule consistent with RPO, plus successful scheduled execution. |
| Backup retention | **Decision Required — Backup Retention** | Open governance decision | Approved retention/deletion schedule and evidence from the selected store. |
| Backup owner | **Decision Required — Backup Owner** | Open governance decision | Named accountable role and operating procedure. |
| Encryption | **Decision Required — Encryption and Key Owner** | Engineering requires encrypted transport and at-rest storage; platform control unverified | Target-store encryption/key policy and verification output. |
| Restore authority | **Decision Required — Restore Authority** | Restore tooling fails closed but cannot assign organizational authority | Approved requester/operator/approver roles and recorded authorization test. |
| Backup location | **Decision Required — Backup Location** | Repository stores no production backup destination | Approved region/store, access boundary, redundancy, and data-residency review. |
| Backup verification | **Decision Required — Verification Schedule and Owner** | A disposable MySQL rehearsal passed | Approved recurring checksum/restore-test schedule and retained evidence. |

Until these controls are approved, there is no organization-approved production
backup policy. Do not schedule deletion or claim an RPO/RTO from the engineering
rehearsal.

## Create a backup

Export `CCF_ENV` and the exact target `DATABASE_URL`, then run:

```sh
.venv/bin/python scripts/mysql_backup.py \
  --output-dir /approved/encrypted/backup/staging \
  --label pre-release
```

The script uses `mysqldump --single-transaction`, supplies credentials through a
mode-0600 temporary client file, compresses the logical dump, refuses overwrite,
and writes a JSON SHA-256 manifest without credentials. Move both files to the
approved encrypted backup store. Restrict the backup account to the privileges
needed for consistent logical backup. Monitor command exit status and file age.

## Restore into an explicit target

Prefer a new recovery database. Provision it first, point `DATABASE_URL` to that
database, and provide two independent confirmations:

```sh
export CCF_ENV=staging
export DATABASE_URL='mysql+pymysql://recovery-user:SECRET@db/ccf_recovery_test'
.venv/bin/python scripts/mysql_restore.py \
  --backup /approved/path/ccf-production-pre-release-TIMESTAMP.sql.gz \
  --confirm-database ccf_recovery_test \
  --confirm-environment staging \
  --verification-dir /approved/recovery-evidence
```

The script verifies the manifest/checksum, requires an exact environment and
database-name match, refuses a non-empty target by default, and requires an
additional `--allow-production` for production. `--allow-nonempty` is a
high-risk exception requiring explicit restore approval and a documented target
backup. The dump does not contain `CREATE DATABASE`/`USE`, so it cannot silently
redirect restoration to the source database.

Compare restored metadata/counts and active-batch ownership against the source
without printing row data:

```sh
export DATABASE_URL='mysql+pymysql://source-user:SECRET@db/ccf_events'
export MYSQL_RESTORE_DATABASE_URL='mysql+pymysql://recovery-user:SECRET@db/ccf_recovery_test'
.venv/bin/python scripts/verify_mysql_restore.py
```

## Restoration verification checklist

- [ ] Restore command and checksum verification succeeded.
- [ ] Verification record names the intended environment/database and contains no credentials.
- [ ] MySQL connectivity succeeds and expected tables exist.
- [ ] `alembic current` equals repository `alembic heads`; run approved migrations if restoring an older supported backup.
- [ ] `/health/ready` passes using the restored database.
- [ ] Administrator login and approval flow work.
- [ ] Event and batch counts reconcile with the backup record/source snapshot.
- [ ] Active batch per Event is correct; no Event references another Event's batch.
- [ ] Dashboard, demographics, satellites, Data Quality, Admin Tables, and curated-source traceability reconcile.
- [ ] A non-production import smoke test preserves atomic activation and failed-batch recovery.
- [ ] Evidence records operator, approver, start/end time, backup ID, image/schema revision, results, and discovered gaps.

A generated verification JSON file is not a complete restoration test. Phase 2
may mark restoration complete only after this checklist is executed against an
appropriate MySQL recovery environment and its evidence is retained.

## 2026-08-29 engineering restoration rehearsal

A local-development MySQL 8.4 logical backup was checksummed, restored into the
dedicated disposable `ccf_events_test` database, and verified at Alembic head.
All 16 table catalogs/counts matched the source; 3 Events, 6 batches, 5,537 raw
registrants, and 5,512 curated registrants reconciled. Active-batch ownership
invariants and dashboard reconciliation for Events 1–3 passed. The protected
verification record is stored under the Git-ignored local backup directory.

This proves the tooling in a disposable MySQL environment. It does not satisfy
target-production acceptance because the platform, backup store, recovery
objectives, owners, and approver remain `Decision Required`.
