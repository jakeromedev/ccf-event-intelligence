# Rollback Runbook

Stop the rollout and preserve logs, artifact digests, configuration versions,
migration output, and timestamps before changing state.

## Application rollback

1. Confirm the previous immutable image is compatible with the current schema.
2. Route traffic away from the failed revision.
3. Deploy the previous image with the currently approved configuration.
4. Require `/health/live` and `/health/ready` HTTP 200, then smoke-test login,
   dashboard reconciliation, Event isolation, Data Quality, and Admin Tables authorization.

## Configuration rollback

Restore the previous versioned non-secret configuration and secret-manager
references. Do not recover by weakening authentication, CSRF, cookies, schema
checks, trusted-host validation, or proxy hop restrictions. Restart gracefully
and reverify HTTPS redirects and cookies.

## Database migration rollback

Before using `alembic downgrade`, inspect the exact migration's downgrade and
test it on a restored copy. Downgrade only when it preserves all required data
and the previous application supports the result. Run:

```sh
alembic current
alembic downgrade REVISION
alembic current
```

If downgrade is absent, lossy, or uncertain, do not run it. Prefer a compatible
application roll-forward. If the schema/data must be reverted, place the
application in maintenance/out-of-traffic state and restore the verified
pre-release backup into an explicitly confirmed target using
`BACKUP_AND_RECOVERY.md`. Account for writes after the backup according to the
approved RPO; no RPO is currently approved.

## Verification and record

Record reason, operator, approver role, old/new image digest, configuration
version, database revision before/after, backup identifier if used, health
results, smoke results, data-loss assessment, and incident link. Keep the failed
artifact and relevant logs available for investigation.
