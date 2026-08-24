#!/usr/bin/env python3
"""Copy the historical SQLite database into an Alembic-managed MySQL schema.

The source file is read-only and is never removed or modified. The destination
must contain the current Alembic schema and no application data.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Boolean, Date, DateTime, create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import TABLES_IN_DEPENDENCY_ORDER  # noqa: E402
from app.normalization import normalize_gender, normalize_life_stage  # noqa: E402


MODELS_BY_TABLE = {model.__table__.name: model for model in TABLES_IN_DEPENDENCY_ORDER}
TABLE_ORDER = tuple(MODELS_BY_TABLE)
OPTIONAL_DERIVED_TABLES = {
    "curated_registrants",
    "curated_registrant_sources",
    "satellites",
    "satellite_source_variations",
    "curated_registrant_satellites",
}
OWNERSHIP = {
    "import_batches": ("event_id", "events"),
    "import_files": ("batch_id", "import_batches"),
    "validation_issues": ("batch_id", "import_batches"),
    "buyers": ("batch_id", "import_batches"),
    "tickets": ("batch_id", "import_batches"),
    "registrants": ("batch_id", "import_batches"),
    "curated_registrants": ("batch_id", "import_batches"),
    "curated_registrant_sources": ("batch_id", "import_batches"),
    "satellites": ("batch_id", "import_batches"),
    "satellite_source_variations": ("batch_id", "import_batches"),
    "curated_registrant_satellites": ("batch_id", "import_batches"),
}
UNIQUE_KEYS = {
    "import_files": (("batch_id", "export_type"),),
    "buyers": (("batch_id", "buyer_reference"),),
    "tickets": (("batch_id", "ticket_code"),),
    "registrants": (("batch_id", "registration_code"), ("batch_id", "ticket_code")),
    "curated_registrants": (("batch_id", "dedupe_key"),),
    "satellites": (("batch_id", "normalized_name"),),
}


class MigrationError(RuntimeError):
    pass


def _source_tables(source):
    return {
        row[0]
        for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _stats_sql(table):
    return "SELECT COUNT(*), MIN(id), MAX(id), COUNT(DISTINCT id) FROM {}".format(table)


def _source_stats(source, table):
    count, minimum, maximum, distinct_ids = source.execute(_stats_sql(table)).fetchone()
    return {
        "count": count,
        "min_id": minimum,
        "max_id": maximum,
        "distinct_ids": distinct_ids,
    }


def _destination_stats(connection, table):
    row = connection.execute(
        text("SELECT COUNT(*), MIN(id), MAX(id), COUNT(DISTINCT id) FROM {}".format(table))
    ).one()
    return {
        "count": row[0],
        "min_id": row[1],
        "max_id": row[2],
        "distinct_ids": row[3],
    }


def _parse_date(value, table, column):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise MigrationError(
            "{}.{} contains a non-ISO date value: {!r}".format(table, column, value)
        ) from exc


def _parse_datetime(value, table, column):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise MigrationError(
            "{}.{} contains an unsupported timestamp: {!r}".format(table, column, value)
        ) from exc
    # Existing SQLite values are naive wall-clock values. A timezone-aware
    # legacy value is normalized without shifting its displayed clock time.
    return parsed.replace(tzinfo=None)


def _coerce_row(table, table_object, row):
    result = {}
    for column in table_object.columns:
        if column.computed is not None:
            continue
        if table == "import_batches" and column.name == "active_event_id":
            value = row["event_id"] if row["status"] == "active" else None
        else:
            value = row[column.name]
        if isinstance(column.type, DateTime):
            value = _parse_datetime(value, table, column.name)
        elif isinstance(column.type, Date):
            value = _parse_date(value, table, column.name)
        elif isinstance(column.type, Boolean) and value is not None:
            value = bool(value)
        result[column.name] = value
    return result


def validate_source(source, source_tables):
    missing = set(TABLE_ORDER[:7]) - source_tables
    if missing:
        raise MigrationError("SQLite source is missing required tables: {}".format(", ".join(sorted(missing))))

    for table in TABLE_ORDER:
        if table not in source_tables:
            if table in OPTIONAL_DERIVED_TABLES:
                continue
            raise MigrationError("SQLite source is missing required table {!r}.".format(table))
        source_columns = {row[1] for row in source.execute("PRAGMA table_info({})".format(table))}
        required = {
            column.name
            for column in MODELS_BY_TABLE[table].__table__.columns
            if column.computed is None
            and not (table == "import_batches" and column.name == "active_event_id")
        }
        missing_columns = required - source_columns
        if missing_columns:
            raise MigrationError(
                "SQLite table {} is missing columns required by MySQL: {}".format(
                    table, ", ".join(sorted(missing_columns))
                )
            )
        stats = _source_stats(source, table)
        if stats["count"] != stats["distinct_ids"]:
            raise MigrationError("SQLite table {} contains duplicate primary keys.".format(table))

    for child, (foreign_column, parent) in OWNERSHIP.items():
        if child not in source_tables or parent not in source_tables:
            continue
        orphan_count = source.execute(
            "SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p ON p.id = c.{column} "
            "WHERE p.id IS NULL".format(child=child, parent=parent, column=foreign_column)
        ).fetchone()[0]
        if orphan_count:
            raise MigrationError(
                "SQLite ownership check failed: {} {} rows have no {} parent.".format(
                    orphan_count, child, parent
                )
            )

    active_duplicates = source.execute(
        "SELECT event_id, COUNT(*) FROM import_batches WHERE status = 'active' "
        "GROUP BY event_id HAVING COUNT(*) > 1"
    ).fetchall()
    if active_duplicates:
        raise MigrationError("SQLite contains more than one active batch for an Event.")

    for table, keys in UNIQUE_KEYS.items():
        if table not in source_tables:
            continue
        for columns in keys:
            duplicate = source.execute(
                "SELECT 1 FROM {table} GROUP BY {columns} HAVING COUNT(*) > 1 LIMIT 1".format(
                    table=table, columns=", ".join(columns)
                )
            ).fetchone()
            if duplicate:
                raise MigrationError(
                    "SQLite violates the expected {} uniqueness on ({}).".format(
                        table, ", ".join(columns)
                    )
                )


def validate_destination_schema(engine, require_alembic=True):
    inspector = inspect(engine)
    if engine.dialect.name == "mysql" and engine.dialect.server_version_info < (8, 0, 16):
        raise MigrationError("MySQL 8.0.16 or newer is required for enforced CHECK constraints.")
    if require_alembic:
        alembic_config = Config(str(ROOT / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(ROOT / "migrations"))
        expected_heads = set(ScriptDirectory.from_config(alembic_config).get_heads())
        with engine.connect() as connection:
            current_heads = set(MigrationContext.configure(connection).get_current_heads())
        if current_heads != expected_heads:
            raise MigrationError(
                "Destination Alembic revision is not current. Run 'alembic upgrade head'. "
                "Expected {}, found {}.".format(sorted(expected_heads), sorted(current_heads))
            )
    destination_tables = set(inspector.get_table_names())
    missing = set(TABLE_ORDER) - destination_tables
    if missing:
        raise MigrationError(
            "Destination schema is incomplete. Run 'alembic upgrade head'. Missing: {}".format(
                ", ".join(sorted(missing))
            )
        )
    for table in TABLE_ORDER:
        actual = {column["name"] for column in inspector.get_columns(table)}
        expected = {column.name for column in MODELS_BY_TABLE[table].__table__.columns}
        missing_columns = expected - actual
        if missing_columns:
            raise MigrationError(
                "Destination table {} is missing columns: {}".format(
                    table, ", ".join(sorted(missing_columns))
                )
            )
    if engine.dialect.name == "mysql":
        table_binds = {
            "table_{}".format(index): table for index, table in enumerate(TABLE_ORDER)
        }
        placeholders = ", ".join(":{}".format(name) for name in table_binds)
        with engine.connect() as connection:
            options = connection.execute(
                text(
                    "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME IN ({})".format(placeholders)
                ),
                {"schema": engine.url.database, **table_binds},
            ).fetchall()
        invalid = [
            row
            for row in options
            if row[1].casefold() != "innodb" or not row[2].casefold().startswith("utf8mb4_")
        ]
        if invalid or len(options) != len(TABLE_ORDER):
            raise MigrationError("Every destination application table must use InnoDB and utf8mb4.")


def _logical_relationship_diagnostics(connection):
    orphan_ticket_buyers = connection.execute(
        text(
            "SELECT COUNT(*) FROM tickets t LEFT JOIN buyers b "
            "ON b.batch_id = t.batch_id AND b.buyer_reference = t.buyer_reference "
            "WHERE t.buyer_reference IS NOT NULL AND t.buyer_reference <> '' AND b.id IS NULL"
        )
    ).scalar_one()
    orphan_registrant_tickets = connection.execute(
        text(
            "SELECT COUNT(*) FROM registrants r LEFT JOIN tickets t "
            "ON t.batch_id = r.batch_id AND t.ticket_code = r.ticket_code WHERE t.id IS NULL"
        )
    ).scalar_one()
    return {
        "tickets_without_buyers": orphan_ticket_buyers,
        "registrants_without_tickets": orphan_registrant_tickets,
    }


def _business_snapshot(fetch_all, fetch_one, event_id):
    """Capture business-significant metrics without relying on engine-specific SQL."""
    event = fetch_one("SELECT event_date, participant_target FROM events WHERE id = :event_id", {"event_id": event_id})
    active = fetch_one(
        "SELECT id FROM import_batches WHERE event_id = :event_id AND status = 'active' "
        "ORDER BY activated_at DESC, id DESC LIMIT 1",
        {"event_id": event_id},
    )
    batch_id = active[0] if active else None
    snapshot = {
        "active_batch_id": batch_id,
        "participant_target": event[1],
        "registration_types": {},
        "checked_in": 0,
        "raw_registrations": 0,
        "gender": {},
        "life_stage": {},
        "affiliations": {},
        "satellites": 0,
        "satellite_associations": 0,
        "data_quality": {},
    }
    if batch_id is None:
        return snapshot
    params = {"batch_id": batch_id}
    snapshot["registration_types"] = {
        row[0]: row[1]
        for row in fetch_all(
            "SELECT registration_type, COUNT(*) FROM curated_registrants "
            "WHERE batch_id = :batch_id GROUP BY registration_type",
            params,
        )
    }
    snapshot["checked_in"] = fetch_one(
        "SELECT COALESCE(SUM(checked_in), 0) FROM curated_registrants WHERE batch_id = :batch_id",
        params,
    )[0]
    snapshot["raw_registrations"] = fetch_one(
        "SELECT COUNT(*) FROM registrants WHERE batch_id = :batch_id AND ticket_matched = 1",
        params,
    )[0]
    participant_profiles = fetch_all(
        "SELECT gender, life_stage FROM curated_registrants "
        "WHERE batch_id = :batch_id AND registration_type = 'participant'",
        params,
    )
    for gender, life_stage in participant_profiles:
        normalized_gender = normalize_gender(gender)
        normalized_life_stage = normalize_life_stage(life_stage)
        snapshot["gender"][normalized_gender] = snapshot["gender"].get(normalized_gender, 0) + 1
        snapshot["life_stage"][normalized_life_stage] = snapshot["life_stage"].get(normalized_life_stage, 0) + 1
    snapshot["affiliations"] = {
        row[0]: row[1]
        for row in fetch_all(
            "SELECT affiliation, COUNT(*) FROM registrants "
            "WHERE batch_id = :batch_id AND ticket_matched = 1 GROUP BY affiliation",
            params,
        )
    }
    snapshot["satellites"] = fetch_one(
        "SELECT COUNT(*) FROM satellites WHERE batch_id = :batch_id", params
    )[0]
    snapshot["satellite_associations"] = fetch_one(
        "SELECT COUNT(*) FROM curated_registrant_satellites WHERE batch_id = :batch_id", params
    )[0]
    snapshot["data_quality"] = {
        row[0]: row[1]
        for row in fetch_all(
            "SELECT category, COUNT(*) FROM validation_issues "
            "WHERE batch_id = :batch_id GROUP BY category",
            params,
        )
    }
    participants = snapshot["registration_types"].get("participant", 0)
    target = snapshot["participant_target"]
    snapshot["target_progress"] = (
        None
        if target is None or target == 0
        else {
            "percentage": participants / target * 100,
            "remaining": max(target - participants, 0),
        }
    )
    return snapshot


def _compare_business_metrics(source, destination):
    def source_all(statement, params):
        return source.execute(statement, params).fetchall()

    def source_one(statement, params):
        return source.execute(statement, params).fetchone()

    def destination_all(statement, params):
        return destination.execute(text(statement), params).fetchall()

    def destination_one(statement, params):
        return destination.execute(text(statement), params).fetchone()

    event_ids = [row[0] for row in source.execute("SELECT id FROM events ORDER BY id")]
    snapshots = {}
    for event_id in event_ids:
        source_snapshot = _business_snapshot(source_all, source_one, event_id)
        destination_snapshot = _business_snapshot(destination_all, destination_one, event_id)
        if source_snapshot != destination_snapshot:
            raise MigrationError(
                "Dashboard/Data Quality metric mismatch for event {}: SQLite={}, MySQL={}".format(
                    event_id, source_snapshot, destination_snapshot
                )
            )
        snapshots[event_id] = source_snapshot
    return snapshots


def validate_copy(source, destination, source_tables):
    report = {}
    for table in TABLE_ORDER:
        source_stats = (
            _source_stats(source, table)
            if table in source_tables
            else {"count": 0, "min_id": None, "max_id": None, "distinct_ids": 0}
        )
        destination_stats = _destination_stats(destination, table)
        if source_stats != destination_stats:
            raise MigrationError(
                "Validation mismatch for {}: SQLite={}, MySQL={}".format(
                    table, source_stats, destination_stats
                )
            )
        report[table] = source_stats

    for child, (foreign_column, parent) in OWNERSHIP.items():
        orphan_count = destination.execute(
            text(
                "SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p ON p.id = c.{column} "
                "WHERE p.id IS NULL".format(child=child, parent=parent, column=foreign_column)
            )
        ).scalar_one()
        if orphan_count:
            raise MigrationError("Destination ownership validation failed for {}.".format(child))

    active_duplicates = destination.execute(
        text(
            "SELECT event_id FROM import_batches WHERE status = 'active' "
            "GROUP BY event_id HAVING COUNT(*) > 1"
        )
    ).first()
    if active_duplicates:
        raise MigrationError("Destination contains multiple active batches for an Event.")

    report["logical_relationships"] = _logical_relationship_diagnostics(destination)
    report["business_snapshots"] = _compare_business_metrics(source, destination)
    return report


def _ensure_auto_increment(engine, report):
    if engine.dialect.name != "mysql":
        return
    database_name = engine.url.database
    with engine.begin() as connection:
        for table in TABLE_ORDER:
            maximum = report[table]["max_id"]
            if maximum is None:
                continue
            next_value = connection.execute(
                text(
                    "SELECT AUTO_INCREMENT FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table"
                ),
                {"schema": database_name, "table": table},
            ).scalar_one()
            if next_value is None or next_value <= maximum:
                # Both identifier and value are internally derived and validated.
                connection.execute(text("ALTER TABLE `{}` AUTO_INCREMENT = {}".format(table, maximum + 1)))


def migrate(source_path, engine, require_mysql=True, progress=print):
    source_path = Path(source_path).expanduser().resolve()
    if not source_path.is_file():
        raise MigrationError("SQLite source does not exist: {}".format(source_path))
    if require_mysql and engine.dialect.name != "mysql":
        raise MigrationError("The destination DATABASE_URL must use a MySQL driver.")

    source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        source.execute("PRAGMA query_only = ON")
        source.execute("SELECT 1").fetchone()
        source_tables = _source_tables(source)
        validate_source(source, source_tables)
        validate_destination_schema(engine, require_alembic=require_mysql)

        with engine.begin() as destination:
            nonempty = {
                table: destination.execute(
                    select(func.count()).select_from(MODELS_BY_TABLE[table].__table__)
                ).scalar_one()
                for table in TABLE_ORDER
            }
            populated = {table: count for table, count in nonempty.items() if count}
            if populated:
                raise MigrationError(
                    "Destination is not empty; refusing to merge databases: {}".format(
                        ", ".join("{}={}".format(table, count) for table, count in populated.items())
                    )
                )

            for table in TABLE_ORDER:
                progress("Migrating {}...".format(table))
                if table not in source_tables:
                    progress("0 rows migrated (table was not present in the legacy schema).")
                    continue
                table_object = MODELS_BY_TABLE[table].__table__
                columns = [
                    column.name
                    for column in table_object.columns
                    if column.computed is None
                    and not (
                        table == "import_batches" and column.name == "active_event_id"
                    )
                ]
                cursor = source.execute(
                    "SELECT {} FROM {} ORDER BY id".format(", ".join(columns), table)
                )
                copied = 0
                while True:
                    rows = cursor.fetchmany(1000)
                    if not rows:
                        break
                    payload = [_coerce_row(table, table_object, row) for row in rows]
                    destination.execute(table_object.insert(), payload)
                    copied += len(payload)
                progress("{} rows migrated.".format(copied))

            report = validate_copy(source, destination, source_tables)

        _ensure_auto_increment(engine, report)
        progress("Validation complete. Source and destination row counts and ID ranges match.")
        logical = report["logical_relationships"]
        progress(
            "Logical relationship diagnostics (preserved, not fatal): "
            "tickets without buyers={}, registrants without tickets={}.".format(
                logical["tickets_without_buyers"], logical["registrants_without_tickets"]
            )
        )
        return report
    finally:
        source.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="instance/ccf_dashboard.sqlite3",
        help="Path to the existing SQLite database (opened read-only).",
    )
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required and must point to the migrated MySQL database.")

    engine_options = {"pool_pre_ping": True, "future": True}
    if make_url(database_url).get_backend_name() == "mysql":
        engine_options["connect_args"] = {"charset": "utf8mb4"}
    engine = create_engine(database_url, **engine_options)
    try:
        migrate(args.source, engine)
    except MigrationError as exc:
        print("Migration failed: {}".format(exc), file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(
            "Migration failed during a database operation ({}). No success was reported; "
            "review the destination schema and MySQL server logs.".format(type(exc).__name__),
            file=sys.stderr,
        )
        return 1
    except sqlite3.Error as exc:
        print(
            "Migration failed while reading SQLite ({}). Verify the source file and its integrity.".format(
                type(exc).__name__
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()
    print("The SQLite source was left unchanged at {}.".format(Path(args.source).resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
