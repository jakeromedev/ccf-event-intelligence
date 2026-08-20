# CCF Event Dashboard — Phase 1 MVP

A privacy-conscious, event-based dashboard for importing CCF Generated Tickets, Buyers, and Registrants exports as one validated batch per Event.

## Phase 1 features

- Three required CSV upload slots with header-based export detection
- Server-side schema, identifier, relationship, and consistency validation
- Atomic batch activation: a failed or incomplete batch never replaces active data
- Event management with isolated import history and one active batch per Event
- Registrant and checked-in attendance metrics
- Approved CCF Main, Local Satellite, International Satellite, Non-CCF, and Unknown classification
- Dynamic satellite ranking and attendance rates
- Aggregated data-quality reporting and import history

## Local setup

Python 3.9 or newer is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Open <http://127.0.0.1:5050>. Create or open an Event, then use its **Imports** workspace to upload all three CSV exports.

The default is port `5050` because macOS AirPlay Receiver commonly reserves port `5000`. To select another port:

```sh
CCF_DASHBOARD_PORT=8000 .venv/bin/python run.py
```

To import the three provided project CSVs from the command line:

```sh
.venv/bin/python scripts/import_provided.py
```

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```

SQLite data and staged uploads are stored under `instance/`, which is excluded from version control. Dashboard analytics are aggregated by default; overview drill-downs show registrant names and event registration details while keeping email addresses and mobile numbers hidden.

## Module documentation

- [Event Imports module](EVENT_IMPORTS_MODULE.md)
