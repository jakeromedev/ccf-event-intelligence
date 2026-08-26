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
| Local database distribution | Project-local native MySQL 8.4 installation under `instance/` |
| Authentication | Flask-Login 0.6.3, Flask-WTF 1.2.2, and Argon2 password hashing |
| Test framework | Python standard-library `unittest` |
| Application entry point | `run.py` |
| Default address | `http://127.0.0.1:5050` |

All Python dependencies are pinned in `requirements.txt`:

```text
Flask==3.1.2
Flask-Login==0.6.3
Flask-WTF==1.2.2
argon2-cffi==25.1.0
SQLAlchemy==2.0.43
Alembic==1.16.5
PyMySQL[rsa]==1.1.2
```

## Runtime configuration

Configuration is supplied through environment variables. `.env.example` is the
committed template; `.env` files and local credentials are ignored by Git.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` | Yes | None | SQLAlchemy connection URL. Normal runtime accepts only a MySQL URL. |
| `CCF_DASHBOARD_SECRET` | Required outside local development | `dev-only-change-me` | Flask signing and CSRF secret. |
| `CCF_SESSION_COOKIE_SECURE` | Required for HTTPS | Disabled | Adds the `Secure` flag to the session cookie when set to `1`, `true`, `yes`, or `on`. |
| `CCF_DASHBOARD_PORT` | No | `5050` | Port used by `run.py`. |
| `CCF_DASHBOARD_DEBUG` | No | `0` | Enables Flask debug mode only when set to `1`. |
| `MYSQL_TEST_DATABASE_URL` | Only for MySQL integration tests | None | Disposable MySQL test schema; its database name must contain `test`. |

Example production-style configuration:

```sh
export DATABASE_URL='mysql+pymysql://ccf_app:strong-password@127.0.0.1:3306/ccf_events'
export CCF_DASHBOARD_SECRET='replace-with-a-long-random-secret'
export CCF_SESSION_COOKIE_SECURE=1
```

The application has a 32 MiB request-body limit. Staged uploads are written to
`instance/staged_imports/`.

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
- The current Alembic head is `a9d3c7e5f102`.
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

`run.py` uses Flask's built-in server and binds only to `127.0.0.1`. A production
deployment should use an appropriate WSGI server or service manager and terminate
HTTPS at the application server or a trusted reverse proxy. No production WSGI
server is currently declared in `requirements.txt`.

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
- Session cookies are `HttpOnly` and `SameSite=Lax`; the `Secure` attribute is
  controlled by `CCF_SESSION_COOKIE_SECURE`.
- Authenticated sessions have an eight-hour lifetime.
- Login is temporarily locked after five failed attempts for 15 minutes.
- Public passwords must be 12–128 characters and use at least three of these
  categories: lowercase, uppercase, digits, and symbols.
- The built-in `admin` username is reserved and is initialized only through the
  terminal command.

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
