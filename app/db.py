import csv
import sqlite3
from pathlib import Path

from flask import current_app, g


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    event_slug TEXT,
    event_name TEXT,
    status TEXT NOT NULL CHECK (status IN ('validating', 'invalid', 'validated', 'processing', 'active', 'failed', 'superseded')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT,
    activated_at TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS import_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    export_type TEXT NOT NULL CHECK (export_type IN ('tickets', 'buyers', 'registrants')),
    filename TEXT NOT NULL,
    staged_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('uploaded', 'validating', 'valid', 'invalid')),
    total_rows INTEGER NOT NULL DEFAULT 0,
    valid_rows INTEGER NOT NULL DEFAULT 0,
    invalid_rows INTEGER NOT NULL DEFAULT 0,
    duplicate_records INTEGER NOT NULL DEFAULT 0,
    relationship_issues INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    detected_type TEXT,
    UNIQUE (batch_id, export_type)
);

CREATE TABLE IF NOT EXISTS validation_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    severity TEXT NOT NULL CHECK (severity IN ('error', 'warning')),
    category TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    source_row INTEGER,
    source_identifier TEXT,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS buyers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    source_id TEXT,
    event_slug TEXT,
    buyer_reference TEXT NOT NULL,
    payment_status TEXT,
    quantity INTEGER,
    UNIQUE (batch_id, buyer_reference)
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    source_id TEXT,
    event_slug TEXT,
    ticket_code TEXT NOT NULL,
    control_number TEXT,
    buyer_reference TEXT,
    ticket_status TEXT,
    payment_status TEXT,
    check_in_at TEXT,
    UNIQUE (batch_id, ticket_code)
);

CREATE TABLE IF NOT EXISTS registrants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    source_id TEXT,
    event_slug TEXT,
    registration_code TEXT NOT NULL,
    ticket_code TEXT NOT NULL,
    ticket_status TEXT,
    first_name TEXT,
    last_name TEXT,
    first_name_present INTEGER NOT NULL DEFAULT 0,
    last_name_present INTEGER NOT NULL DEFAULT 0,
    email_present INTEGER NOT NULL DEFAULT 0,
    mobile_present INTEGER NOT NULL DEFAULT 0,
    gender_raw TEXT,
    birth_month_raw TEXT,
    birth_year_raw TEXT,
    b1g_satellite_hub_raw TEXT,
    b1g_satellite_raw TEXT,
    b1g_satellite_specify_raw TEXT,
    attending_ccf_raw TEXT,
    satellite_scope_raw TEXT,
    local_satellite_raw TEXT,
    international_satellite_raw TEXT,
    affiliation TEXT NOT NULL CHECK (affiliation IN ('CCF Main', 'Local Satellite', 'International Satellite', 'Non-CCF', 'Unknown')),
    satellite_name TEXT,
    ticket_matched INTEGER NOT NULL DEFAULT 0,
    checked_in INTEGER NOT NULL DEFAULT 0,
    UNIQUE (batch_id, registration_code),
    UNIQUE (batch_id, ticket_code)
);

CREATE INDEX IF NOT EXISTS idx_tickets_batch_buyer ON tickets(batch_id, buyer_reference);
CREATE INDEX IF NOT EXISTS idx_registrants_batch_affiliation ON registrants(batch_id, ticket_matched, affiliation, checked_in);
CREATE INDEX IF NOT EXISTS idx_issues_batch_category ON validation_issues(batch_id, category);
CREATE INDEX IF NOT EXISTS idx_import_batches_event ON import_batches(event_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_batch_per_event
    ON import_batches(event_id) WHERE status = 'active';

CREATE TRIGGER IF NOT EXISTS require_import_batch_event_insert
BEFORE INSERT ON import_batches
WHEN NEW.event_id IS NULL
BEGIN
    SELECT RAISE(ABORT, 'import batch event_id is required');
END;

CREATE TRIGGER IF NOT EXISTS require_import_batch_event_update
BEFORE UPDATE OF event_id ON import_batches
WHEN NEW.event_id IS NULL
BEGIN
    SELECT RAISE(ABORT, 'import batch event_id is required');
END;

CREATE TRIGGER IF NOT EXISTS touch_event_on_name_change
AFTER UPDATE OF name ON events
BEGIN
    UPDATE events SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS touch_event_on_batch_activation
AFTER UPDATE OF status ON import_batches
WHEN NEW.status = 'active'
BEGIN
    UPDATE events SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.event_id;
END;
"""


EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(EVENTS_TABLE)
    existing_tables = {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if "import_batches" in existing_tables:
        columns = {
            row["name"] for row in db.execute("PRAGMA table_info(import_batches)").fetchall()
        }
        if "event_id" not in columns:
            db.execute(
                "ALTER TABLE import_batches ADD COLUMN event_id INTEGER REFERENCES events(id)"
            )
        _backfill_legacy_events(db)
    db.executescript(SCHEMA)
    _ensure_registrant_profile_columns(db)
    _backfill_registrant_profiles(db)
    _backfill_registrant_names(db)
    db.commit()


def _ensure_registrant_profile_columns(db):
    """Add the Phase 1 profile fields without replacing existing registrant data."""
    columns = {
        row["name"] for row in db.execute("PRAGMA table_info(registrants)").fetchall()
    }
    for name in (
        "first_name",
        "last_name",
        "gender_raw",
        "birth_month_raw",
        "birth_year_raw",
        "b1g_satellite_hub_raw",
        "b1g_satellite_raw",
        "b1g_satellite_specify_raw",
    ):
        if name not in columns:
            db.execute("ALTER TABLE registrants ADD COLUMN {} TEXT".format(name))


def _backfill_registrant_names(db):
    """Backfill names from preserved exports for participant lookup pages."""
    files = db.execute(
        """
        SELECT batch_id, staged_path
        FROM import_files
        WHERE export_type = 'registrants'
          AND EXISTS (
              SELECT 1 FROM registrants
              WHERE batch_id = import_files.batch_id
                AND (first_name IS NULL OR last_name IS NULL)
          )
        """
    ).fetchall()
    for source in files:
        path = Path(source["staged_path"])
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, strict=True)
                headers = set(reader.fieldnames or ())
                if not {"Ticket Code", "First Name", "Last Name"}.issubset(headers):
                    continue
                updates = []
                for row in reader:
                    ticket_code = (row.get("Ticket Code") or "").strip()
                    if not ticket_code:
                        continue
                    updates.append(
                        (
                            (row.get("First Name") or "").strip() or None,
                            (row.get("Last Name") or "").strip() or None,
                            source["batch_id"],
                            ticket_code,
                        )
                    )
                db.executemany(
                    """
                    UPDATE registrants
                    SET first_name = ?, last_name = ?
                    WHERE batch_id = ? AND ticket_code = ?
                    """,
                    updates,
                )
        except (OSError, UnicodeError, csv.Error):
            # Missing legacy staging files must not prevent application startup.
            continue


def _backfill_registrant_profiles(db):
    """Backfill legacy batches from their preserved registrants export when available."""
    if not {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }.issuperset({"registrants", "import_files"}):
        return

    files = db.execute(
        """
        SELECT batch_id, staged_path
        FROM import_files
        WHERE export_type = 'registrants'
          AND EXISTS (SELECT 1 FROM registrants WHERE batch_id = import_files.batch_id)
          AND NOT EXISTS (
              SELECT 1 FROM registrants
              WHERE batch_id = import_files.batch_id
                AND (gender_raw IS NOT NULL OR birth_month_raw IS NOT NULL OR birth_year_raw IS NOT NULL)
          )
        """
    ).fetchall()
    for source in files:
        path = Path(source["staged_path"])
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, strict=True)
                headers = set(reader.fieldnames or ())
                if not {"Ticket Code", "Gender", "Birth Month", "Birth Year"}.issubset(headers):
                    continue
                updates = []
                for row in reader:
                    ticket_code = (row.get("Ticket Code") or "").strip()
                    if not ticket_code:
                        continue
                    updates.append(
                        (
                            (row.get("Gender") or "").strip() or None,
                            (row.get("Birth Month") or "").strip() or None,
                            (row.get("Birth Year") or "").strip() or None,
                            source["batch_id"],
                            ticket_code,
                        )
                    )
                db.executemany(
                    """
                    UPDATE registrants
                    SET gender_raw = ?, birth_month_raw = ?, birth_year_raw = ?
                    WHERE batch_id = ? AND ticket_code = ?
                    """,
                    updates,
                )
        except (OSError, UnicodeError, csv.Error):
            # A missing legacy source must never make the existing dashboard unavailable.
            continue


def _backfill_legacy_events(db):
    legacy_batches = db.execute(
        """
        SELECT id, event_slug, event_name
        FROM import_batches
        WHERE event_id IS NULL
        ORDER BY id
        """
    ).fetchall()
    event_ids = {}
    for batch in legacy_batches:
        key = (batch["event_slug"] or "", batch["event_name"] or "")
        if key not in event_ids:
            display_name = (batch["event_name"] or "").strip() or "Imported Event"
            cursor = db.execute("INSERT INTO events (name) VALUES (?)", (display_name,))
            event_ids[key] = cursor.lastrowid
        db.execute(
            "UPDATE import_batches SET event_id = ? WHERE id = ?",
            (event_ids[key], batch["id"]),
        )


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
