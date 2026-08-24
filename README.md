# CCF Event Dashboard — Phase 1 MVP

A privacy-conscious, event-based dashboard for importing CCF Generated Tickets, Buyers, and Registrants exports as one validated batch per Event.

## Phase 1 features

- Three required CSV upload slots with header-based export detection
- Server-side schema, identifier, relationship, and consistency validation
- Atomic batch activation: a failed or incomplete batch never replaces active data
- Deterministic, batch-scoped unique-person curation with complete raw-source traceability
- Conservative satellite normalization with source-variation auditing and multi-satellite support
- Event management with isolated import history and one active batch per Event
- Event-scoped Event Date and Participant Target settings
- Unique participant, unique volunteer, raw-registration, target, progress, and remaining-slot metrics
- Participant-only Gender, Life Stage, and event-date Age distributions with Unknown reconciliation
- Read-only event dashboard JSON at `/events/<event_id>/dashboard`
- Registrant and checked-in attendance metrics
- Approved CCF Main, Local Satellite, International Satellite, Non-CCF, and Unknown classification
- Dynamic satellite ranking and attendance rates
- Separate import-quality and curation-quality reporting with duplicate/source drill-downs
- Permission-protected Admin Tables for Registrants, Generated Tickets, and Buyers
- Server-side Admin Table search, filters, sorting, pagination, column controls, and curated-source inspection

## MySQL development setup

Python 3.9 or newer and MySQL 8.0.16+ are required. Create a dedicated database
and account; use a different password outside local development.

This workspace includes a native (non-containerized) MySQL 8.4 installation
under the Git-ignored `instance/` directory. Start it and load the local-only
connection settings with:

```sh
.venv/bin/python scripts/local_mysql.py start
. instance/mysql.env
```

Use `status` or `stop` in place of `start` to inspect or stop the server. The
server is bound to `127.0.0.1:3306`; its data, configuration, logs, and local
credentials are not committed. The SQL below is only needed when provisioning
a different MySQL installation.

```sql
CREATE DATABASE ccf_events
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
CREATE USER 'ccf_app'@'localhost' IDENTIFIED BY 'change-this-password';
GRANT ALL PRIVILEGES ON ccf_events.* TO 'ccf_app'@'localhost';
```

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export DATABASE_URL='mysql+pymysql://ccf_app:change-this-password@127.0.0.1:3306/ccf_events'
.venv/bin/alembic upgrade head
.venv/bin/flask --app 'app:create_app()' db-check
.venv/bin/flask --app 'app:create_app()' admin-init
.venv/bin/python run.py
```

Open <http://127.0.0.1:5050>. Create or open an Event, then use its **Imports** workspace to upload all three CSV exports.

`DATABASE_URL` is required. Credentials, host, port, and database name are not
stored in the repository. SQLAlchemy uses pooled, pre-pinged connections. Flask
startup verifies configuration but never creates or alters schema; run Alembic
explicitly for every deployment.

The terminal-only `admin-init` command creates the single `admin` account and
prints its generated password. Running it again resets that same account's
password, invalidates its existing sessions, and never creates another admin.
Browser registrations always create pending standard-user accounts; the admin
approves them from **Users** in the application navigation. See
[Authentication and user approval](AUTHENTICATION.md) for the complete workflow
and security model.

The default is port `5050` because macOS AirPlay Receiver commonly reserves port `5000`. To select another port:

```sh
CCF_DASHBOARD_PORT=8000 .venv/bin/python run.py
```

To import the three provided project CSVs from the command line:

```sh
.venv/bin/python scripts/import_provided.py
```

## Transfer the existing SQLite data

First back up the MySQL database and verify that the Alembic-managed application
tables are empty. Then run:

```sh
export DATABASE_URL='mysql+pymysql://ccf_app:change-this-password@127.0.0.1:3306/ccf_events'
.venv/bin/alembic upgrade head
.venv/bin/python scripts/migrate_sqlite_to_mysql.py \
  --source instance/ccf_dashboard.sqlite3
```

The copier opens SQLite read-only, preserves primary keys, copies all 12 tables
in dependency order, validates counts/ID ranges/ownership/uniqueness and
dashboard/Data Quality snapshots, and verifies MySQL auto-increment state. It
aborts if any destination application table is non-empty. Logical orphan
diagnostics for buyer references and ticket codes are reported but are not
treated as migration failures because they are valid Data Quality findings.
The source SQLite file is never deleted or modified.

To rebuild derived curation for a historical batch or Event:

```sh
.venv/bin/python scripts/rebuild_curation.py --batch-id 12
.venv/bin/python scripts/rebuild_curation.py --event-id 3
```

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The default suite uses an isolated SQLAlchemy test database. To run the full
integration suite against MySQL, provide a disposable database whose name
contains `test`; the suite drops and recreates its application tables:

```sh
export MYSQL_TEST_DATABASE_URL='mysql+pymysql://ccf_test:password@127.0.0.1:3306/ccf_events_test'
.venv/bin/python -m unittest discover -s tests -v
```

Never point this variable at production. Timestamps are stored as naive
`DATETIME` values to preserve
the existing wall-clock interpretation without timezone shifts. New application
timestamps use the MySQL server's current time, so the database and application
hosts should use the same operational timezone convention.

Staged uploads and the retained SQLite rollback artifact remain under
`instance/`, which is excluded from version control. Dashboard analytics remain
aggregated and privacy-limited. Complete source-row values are available only
through the permission-protected Admin Tables module; deployments can connect
their identity provider through `ADMIN_TABLES_AUTHORIZER`.

## Module documentation

- [Event Imports module](EVENT_IMPORTS_MODULE.md)
- [Phase 1 Core Event Dashboard](PHASE_1_CORE_DASHBOARD.md)
- [Current Database Structure](CURRENT_DATABASE_STRUCTURE.md)
- [Age Distribution Logic](AGE_DISTRIBUTION_LOGIC.md)
- [Registrant and Satellite Curation](CURATION_LAYER.md)
- [Admin Tables module](ADMIN_TABLES_MODULE.md)
- [Authentication and user approval](AUTHENTICATION.md)
