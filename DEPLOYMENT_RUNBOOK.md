# Production Deployment Runbook

This runbook deploys the Flask application through Gunicorn in the supplied OCI
container. Replace platform placeholders only after the target environment is
approved in `PHASE_2_DECISIONS.md`. The Flask development server is local-only.

## Prerequisites

- Approved release artifact/commit and release approver.
- Container runtime/orchestrator able to pass secrets at runtime, persist the
  staging volume, terminate HTTPS, and send `SIGTERM` with at least the
  configured Gunicorn graceful timeout.
- MySQL 8.0.16+ with InnoDB and `utf8mb4`; application and migration credentials
  should be separate where the platform supports it.
- `mysqldump`/`mysql` clients for the backup operator.
- Network policy allowing only the trusted reverse proxy to reach the app and
  only the app/migration/backup roles to reach MySQL.

## Environment separation

`CCF_ENV` must be one of `development`, `testing`, `staging`, or `production`.
Each environment must use a distinct database, secret, staging volume, and log
destination. Testing may use temporary SQLite; normal runtime requires MySQL.

Required production values:

- `CCF_ENV=production`
- `DATABASE_URL` from the secret manager, naming the production MySQL database
- `CCF_DASHBOARD_SECRET`, randomly generated, non-placeholder, at least 32 characters
- `CCF_SESSION_COOKIE_SECURE=1`
- `CCF_TRUSTED_HOSTS`, the externally valid host names
- exact `CCF_PROXY_X_*` hop counts for the trusted proxy chain; leave unrelated
  forwarded-header counts at zero
- a persistent, private `CCF_STAGING_DIR`

Review every variable in `.env.example`. Production refuses debug mode,
disabled authentication, insecure cookies, disabled CSRF, missing/default
secrets, non-MySQL URLs, and disabled schema compatibility checks. Do not bake
secrets into the image or write them to logs.

## Repeatable release sequence

1. Record artifact digest, configuration version, operator, approver, and time.
2. Confirm the target host, database name, and `CCF_ENV` aloud/in the change record.
3. Run the pre-release backup in `BACKUP_AND_RECOVERY.md`; verify its checksum
   manifest and encrypted storage transfer.
4. From the approved release image or checkout, inspect migration state:

   ```sh
   alembic current
   alembic heads
   alembic upgrade head
   alembic current
   alembic check
   ```

   A failure stops the release. Do not use `db.create_all()` and do not start
   request workers against a partially migrated schema.

5. Build and identify the immutable image:

   ```sh
   docker build --tag ccf-systems-dashboard:RELEASE .
   docker image inspect ccf-systems-dashboard:RELEASE --format '{{.Id}}'
   ```

6. Deploy with runtime secrets/environment and a persistent private staging
   volume mounted at `/data/staged`. The entrypoint runs `production-check`,
   then replaces itself with Gunicorn. It never migrates the schema.
7. Wait for `/health/live` and `/health/ready` to return HTTP 200 with minimal
   JSON. A readiness failure must keep the instance out of traffic.
8. Verify external HTTPS, the expected host, redirects, and a login response
   cookie containing `Secure`, `HttpOnly`, and the approved `SameSite` value.
9. Run smoke checks: administrator login, Event isolation, Dashboard, Data
   Quality, administrator-only Admin Tables, user approval, and logout.
10. In staging or with an approved non-personal production fixture, validate a
    complete three-file import, processing/activation, and the failed-batch
    preservation path. Do not create production test registrant data without approval.
11. Observe JSON events for startup, requests, authentication failure,
    readiness, and import processing; confirm no personal/secret data appears.
12. Complete `PRODUCTION_ACCEPTANCE.md` and retain evidence.

## Graceful restart verification

Send `SIGTERM` through the platform, confirm the instance leaves traffic, in-flight
requests finish within `GUNICORN_GRACEFUL_TIMEOUT`, `application_stopped` is
emitted, replacement workers pass readiness, and no batch is left in an
unexpected state. Imports are synchronous; do not initiate a rollout while an
import is processing.

## Migration limitations

Alembic is authoritative. Read each migration before release. `alembic downgrade`
is permitted only when its reviewed downgrade is data-safe. Destructive or
transformative migrations can require application roll-forward or backup
restoration instead. A schema upgrade must fail visibly, and application startup
refuses a database whose `alembic_version` is not the repository head.

## Administrator credential recovery

From a trusted terminal with production secrets and database access, run:

```sh
flask --app 'app:create_app()' admin-init
```

Confirm the warning and securely capture the newly generated password. The
existing admin record is reset and existing admin sessions are invalidated. Do
not paste the password into tickets, chat, or logs. Record only that recovery
occurred, operator, time, and reason.

## Rollback

Follow `ROLLBACK_RUNBOOK.md`; never assume application and database rollback are
the same operation. After rollback, repeat health, security, authentication,
Event isolation, and import-preservation checks.
