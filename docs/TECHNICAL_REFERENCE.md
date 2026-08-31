# CCF Systems Dashboard — Technical Reference

## Application profile

| Item | Technical detail |
| --- | --- |
| Application type | Server-rendered Python web application |
| Backend | Flask 3.1.2 |
| Python | 3.9 or newer; the current local virtual environment uses Python 3.9.6 |
| Templates | Jinja templates rendered by Flask |
| Browser assets | Plain JavaScript and CSS; no frontend package manager or build step |
| ORM and SQL | SQLAlchemy 2.0.43 |
| Database migrations | Alembic 1.16.5 |
| Runtime database | MySQL 8.0.16 or newer through PyMySQL 1.1.2 |
| Production WSGI runtime | Gunicorn 23.0 (`gthread`) in the supplied OCI container |
| Local database distribution | Project-local native MySQL 8.4 installation under `instance/` |
| Authentication | Flask-Login 0.6.3, Flask-WTF 1.2.2, and Argon2 password hashing |
| Test framework | Python standard-library `unittest` |
| Development entry point | `run.py` at `http://127.0.0.1:5050` |
| Production entry point | `ops/docker-entrypoint.sh` → configuration/schema check → Gunicorn |

All Python dependencies are pinned in `requirements.txt`:

```text
Flask==3.1.2
Flask-Login==0.6.3
Flask-WTF==1.2.2
argon2-cffi==25.1.0
SQLAlchemy==2.0.43
Alembic==1.16.5
PyMySQL[rsa]==1.1.2
gunicorn==23.0.0
```

## Runtime configuration

Configuration is supplied through environment variables. `.env.example` is the
committed template; `.env` files and local credentials are ignored by Git.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `CCF_ENV` | Production: yes | `development` | `development`, `testing`, `staging`, or `production`. |
| `DATABASE_URL` | Yes | None | SQLAlchemy connection URL. Normal runtime accepts only a MySQL URL. |
| `CCF_DASHBOARD_SECRET` | Production: yes | Development-only placeholder | Flask signing and CSRF secret; production requires 32+ non-placeholder characters. |
| `CCF_SESSION_COOKIE_SECURE` | Production: yes | Enabled in production | Adds the `Secure` cookie flag; production refuses false. |
| `CCF_SESSION_COOKIE_SAMESITE` | No | `Lax` | `Lax`, `Strict`, or secure-only `None`. |
| `CCF_SESSION_HOURS` | No | `8` | Session lifetime, constrained to 1–24 hours. |
| `CCF_CSRF_TIME_LIMIT_SECONDS` | No | `7200` | CSRF token lifetime. |
| `CCF_STAGING_DIR` | Production: yes | `instance/staged_imports` | Environment-specific private upload staging directory. |
| `CCF_MAX_UPLOAD_MB` | No | `32` | Environment-specific request limit. |
| `CCF_TRUSTED_HOSTS` | Production: yes | None | Comma-separated externally valid host names. |
| `CCF_PROXY_X_FOR`, `CCF_PROXY_X_PROTO`, `CCF_PROXY_X_HOST`, `CCF_PROXY_X_PORT`, `CCF_PROXY_X_PREFIX` | When behind trusted proxy | `0` | Exact trusted proxy hop counts; arbitrary forwarded headers are ignored at zero. |
| `CCF_LOG_LEVEL`, `CCF_LOG_FORMAT` | No | Environment-driven | Staging/production default to `INFO` JSON stdout. |
| `CCF_STANDARD_USER_MUTATIONS_ALLOWED` | After policy approval | Development/testing true; staging/production false | Controls standard-user Event settings/Satellite Dataset/import mutation; never changes admin-only deletion/Admin Tables/users. |
| `CCF_ANALYTICS_MIN_GROUP_SIZE` | Policy approval pending | `5` | Withholds exact non-zero analytical groups below 1–100 configured records; the default is an engineering value, not approved policy. |
| `CCF_REQUIRE_SCHEMA_CURRENT` | Production/staging mandatory | Enabled there | Verifies MySQL and exact Alembic head at startup/readiness. |
| `CCF_DASHBOARD_PORT` | No | `5050` | Port used by `run.py`. |
| `CCF_DASHBOARD_DEBUG` | Development only | `0` | Production refuses debug mode. |
| `MYSQL_TEST_DATABASE_URL` | Only for MySQL integration tests | None | Disposable MySQL test schema; its database name must contain `test`. |

Example production-style configuration:

```sh
export CCF_ENV=production
export DATABASE_URL='mysql+pymysql://ccf_app:SECRET@mysql/ccf_events'
export CCF_DASHBOARD_SECRET='GENERATED-SECRET-FROM-PROTECTED-SECRET-MANAGER'
export CCF_SESSION_COOKIE_SECURE=1
export CCF_TRUSTED_HOSTS='dashboard.example.org'
export CCF_PROXY_X_FOR=1
export CCF_PROXY_X_PROTO=1
export CCF_PROXY_X_HOST=1
```

See `.env.example` for the complete placeholder-only configuration. Production
also refuses disabled authentication/CSRF/schema checks. The secret, database,
staging path, cookie policy, logging, proxy trust, pool sizing, and limits are
environment-driven.

Phase 3 aggregate analytics live in `app/analytics.py` and are presented through
a dedicated Event workspace plus aggregate JSON APIs. This service owns Event
and active-batch scoping, source-field normalization, composable validated
filters, privacy suppression, historical snapshot queries, and explicit
cross-Event comparisons. `ANALYTICS_REFERENCE.md` is the metric contract and
`PHASE_3_DECISIONS.md` records deferred financial, export, priority, and
privacy roadmap items. `REPORTING.md` records the deliberately disabled download
surface and future approval requirements. No Phase 3 database migration is
required for the current derived analytics.

## Database

MySQL is mandatory during normal application runtime. SQLite compatibility is
retained only for isolated tests and for reading the historical database during
the one-time SQLite-to-MySQL transfer.

Database characteristics:

- MySQL 8.0.16+ is required so `CHECK` constraints are enforced.
- Tables use InnoDB, `utf8mb4`, and `utf8mb4_unicode_ci`.
- Connections use the PyMySQL driver with `utf8mb4` client encoding.
- SQLAlchemy enables connection pre-ping, a 1,800-second pool recycle interval,
  and `READ COMMITTED` isolation for MySQL.
- Request database work uses request-scoped SQLAlchemy sessions with explicit
  commit and rollback behavior.
- Alembic exclusively owns schema creation and upgrades; application startup
  does not create or modify tables.
- The current Alembic head is `c8f5d2b0e417`.
- Application timestamps are stored as naive MySQL `DATETIME` values. Database
  and application hosts should use the same operational timezone convention.

The local database helper controls the native MySQL installation stored in the
Git-ignored `instance/` directory:

```sh
.venv/bin/python scripts/local_mysql.py start
.venv/bin/python scripts/local_mysql.py status
.venv/bin/python scripts/local_mysql.py stop
```

Local connection variables are stored in `instance/mysql.env` when the bundled
database has been provisioned:

```sh
. instance/mysql.env
```

## Installation and startup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# Start the bundled local MySQL and load its connection variables.
.venv/bin/python scripts/local_mysql.py start
. instance/mysql.env

# Apply the schema and confirm connectivity.
.venv/bin/alembic upgrade head
.venv/bin/flask --app 'app:create_app()' db-check

# Create or reset the sole administrator account.
.venv/bin/flask --app 'app:create_app()' admin-init

# Start the application.
.venv/bin/python run.py
```

`run.py` remains the local-development server and binds only to `127.0.0.1`.
Production uses Gunicorn via `Dockerfile` and `ops/docker-entrypoint.sh`.
Gunicorn handles `SIGTERM` gracefully and emits lifecycle JSON. HTTPS terminates
at the selected trusted reverse proxy. `ProxyFix` is enabled only for explicit
per-header hop counts; Flask trusted-host validation and secure cookies remain
active. The entrypoint verifies configuration, MySQL, and Alembic head but never
runs migrations. Follow `DEPLOYMENT_RUNBOOK.md`.

## Schema migration and data transfer

Apply committed schema migrations with:

```sh
.venv/bin/alembic current
.venv/bin/alembic upgrade head
.venv/bin/alembic check
```

To transfer the retained historical SQLite data into an empty, Alembic-managed
MySQL schema:

```sh
.venv/bin/python scripts/migrate_sqlite_to_mysql.py \
  --source instance/ccf_dashboard.sqlite3
```

The transfer utility opens the SQLite source read-only, preserves primary keys,
validates the copy, and refuses to run when destination application tables
contain data. It does not delete or modify the SQLite source.

## Testing

Run the default isolated suite:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The default tests use temporary SQLite databases through SQLAlchemy. Run the
same suite against a disposable MySQL schema with:

```sh
export MYSQL_TEST_DATABASE_URL='mysql+pymysql://ccf_test:password@127.0.0.1:3306/ccf_events_test'
.venv/bin/python -m unittest discover -s tests -v
```

The MySQL test setup drops and recreates application tables. Never point
`MYSQL_TEST_DATABASE_URL` at a development or production database.

## Security settings

- Passwords are hashed with Argon2.
- CSRF protection is enabled globally, with a two-hour token lifetime.
- Session cookies are `HttpOnly` and `SameSite=Lax` by default; production
  requires `Secure` and refuses unsafe secret/debug/authentication/CSRF/schema settings.
- Authenticated sessions have an eight-hour lifetime.
- Login is temporarily locked after five failed attempts for 15 minutes.
- Public passwords must be 12–128 characters and use at least three of these
  categories: lowercase, uppercase, digits, and symbols.
- The built-in `admin` username is reserved and is initialized only through the
  terminal command.
- Authorization uses centralized application capabilities. The `registration`
  role is deny-by-default and receives only Dashboard read access,
  Registrations access, and attestation-verification editing. Its endpoint
  allow-list independently blocks Analytics, Data Quality, Admin Tables,
  satellites, imports/batches, Event settings, and user administration.
- Public registration always creates `user/pending`; only the administrator can
  assign `registration` during approval or later role management.

## Local and sensitive files

The following are intentionally excluded from version control:

- `.env` and `.env.*`, except `.env.example`
- `.venv/`
- `instance/`, including MySQL data, local credentials, staged uploads, and the
  historical SQLite file
- CSV files, because source exports can contain personal information
- Logs, test caches, coverage output, editor settings, and Python bytecode

Back up the MySQL database before schema or data-transfer operations. Treat the
contents of `instance/`, source CSV files, database dumps, and administrator
credentials as sensitive data.

## Production operations

- `GET /health/live` checks process liveness.
- `GET /health/ready` checks MySQL connectivity and exact Alembic head.
- staging/production use PII-conscious JSON logs and request correlation.
- `.github/workflows/ci.yml` runs lint/compile/SQLite tests, the complete suite
  against disposable MySQL, Alembic checks, production configuration checks,
  and a container build.
- Backup/restore commands and safeguards are in `BACKUP_AND_RECOVERY.md`.
- Deployment, rollback, monitoring, incident response, acceptance, and UAT are
  linked from `README.md` and `PHASE_CHECKLISTS.md`.
