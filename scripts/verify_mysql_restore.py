#!/usr/bin/env python3
"""Compare a restored MySQL database with its source using metadata and counts only."""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from mysql_common import OperationalSafetyError


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url-env", default="DATABASE_URL")
    parser.add_argument("--target-url-env", default="MYSQL_RESTORE_DATABASE_URL")
    parser.add_argument("--allow-production-target", action="store_true")
    return parser.parse_args()


def _url_from_environment(name):
    value = os.environ.get(name, "")
    if not value:
        raise OperationalSafetyError("{} is required.".format(name))
    url = make_url(value)
    if url.get_backend_name() != "mysql" or not url.database:
        raise OperationalSafetyError("{} must name an explicit MySQL database.".format(name))
    return value, url


def main():
    args = arguments()
    source_url, source = _url_from_environment(args.source_url_env)
    target_url, target = _url_from_environment(args.target_url_env)
    if source.database == target.database and (source.host, source.port) == (
        target.host,
        target.port,
    ):
        raise OperationalSafetyError("Source and target databases must differ.")
    safe_target = any(token in target.database.casefold() for token in ("test", "restore", "recovery"))
    if not safe_target and not args.allow_production_target:
        raise OperationalSafetyError(
            "Target name must contain test, restore, or recovery unless explicitly approved."
        )

    source_engine = create_engine(source_url, pool_pre_ping=True)
    target_engine = create_engine(target_url, pool_pre_ping=True)
    try:
        with source_engine.connect() as left, target_engine.connect() as right:
            source_tables = sorted(inspect(left).get_table_names())
            target_tables = sorted(inspect(right).get_table_names())
            if source_tables != target_tables:
                raise OperationalSafetyError("Restored table catalog does not match the source.")
            counts = {}
            for table in source_tables:
                if not table.replace("_", "").isalnum():
                    raise OperationalSafetyError("Unsafe table name encountered.")
                statement = text("SELECT COUNT(*) FROM `{}`".format(table))
                source_count = left.execute(statement).scalar_one()
                target_count = right.execute(statement).scalar_one()
                if source_count != target_count:
                    raise OperationalSafetyError(
                        "Row-count mismatch for {} (source {}, target {}).".format(
                            table, source_count, target_count
                        )
                    )
                counts[table] = source_count

            invariant = text(
                "SELECT COUNT(*) FROM import_batches "
                "WHERE status = 'active' AND (active_event_id IS NULL OR active_event_id <> event_id)"
            )
            if left.execute(invariant).scalar_one() or right.execute(invariant).scalar_one():
                raise OperationalSafetyError("Active-batch ownership invariant failed.")
    finally:
        source_engine.dispose()
        target_engine.dispose()

    print("Restored table counts match source across {} tables.".format(len(counts)))
    print(
        "Restored Events: {}; import batches: {}; registrants: {}; curated registrants: {}.".format(
            counts.get("events", 0),
            counts.get("import_batches", 0),
            counts.get("registrants", 0),
            counts.get("curated_registrants", 0),
        )
    )
    print("Active-batch ownership invariants passed in source and restored target.")


if __name__ == "__main__":
    try:
        main()
    except OperationalSafetyError as error:
        print("Restore verification failed: {}".format(error), file=sys.stderr)
        raise SystemExit(2)
