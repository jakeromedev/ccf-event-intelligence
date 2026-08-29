#!/usr/bin/env python3
"""Restore a CCF MySQL backup with explicit target and environment safeguards."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from mysql_common import (
    OperationalSafetyError,
    client_defaults_file,
    configured_database,
    environment_name,
    sha256_file,
    utc_timestamp,
    write_json_exclusive,
)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--confirm-environment", required=True)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--allow-nonempty", action="store_true")
    parser.add_argument("--verification-dir", type=Path, required=True)
    return parser.parse_args()


def _verify_manifest(backup, manifest_path):
    if not manifest_path.exists():
        raise OperationalSafetyError("The backup manifest is required and was not found.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("backup_file") != backup.name:
        raise OperationalSafetyError("Manifest backup filename does not match.")
    if manifest.get("sha256") != sha256_file(backup):
        raise OperationalSafetyError("Backup checksum verification failed.")
    return manifest


def _safe_mysql_error(stderr):
    """Return only an error code/line, never SQL or restored row contents."""
    decoded = stderr.decode("utf-8", errors="replace")
    match = re.search(r"ERROR\s+(\d+)(?:\s+\([^)]*\))?\s+at line\s+(\d+)", decoded)
    if match:
        return "mysql_error_{}_line_{}".format(match.group(1), match.group(2))
    match = re.search(r"ERROR\s+(\d+)", decoded)
    return "mysql_error_{}".format(match.group(1)) if match else "mysql_error_unknown"


def main():
    args = arguments()
    if shutil.which("mysql") is None:
        raise OperationalSafetyError("mysql client is required on PATH.")
    raw_url, url = configured_database()
    environment = environment_name()
    if args.confirm_database != url.database:
        raise OperationalSafetyError("--confirm-database does not match DATABASE_URL.")
    if not environment or args.confirm_environment.casefold() != environment:
        raise OperationalSafetyError("--confirm-environment does not match CCF_ENV.")
    if environment == "production" and not args.allow_production:
        raise OperationalSafetyError("Production restore requires --allow-production.")
    if not args.backup.is_file():
        raise OperationalSafetyError("The backup file does not exist.")

    manifest_path = args.manifest or args.backup.with_suffix(args.backup.suffix + ".json")
    manifest = _verify_manifest(args.backup, manifest_path)

    engine = create_engine(raw_url, pool_pre_ping=True)
    existing_tables = inspect(engine).get_table_names()
    if existing_tables and not args.allow_nonempty:
        raise OperationalSafetyError(
            "Target database is not empty; create a new recovery database or pass --allow-nonempty."
        )

    defaults = client_defaults_file(url)
    command = ["mysql", "--defaults-extra-file={}".format(defaults), url.database]
    try:
        with gzip.open(args.backup, "rb") as source:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stderr=subprocess.PIPE
            )
            assert process.stdin is not None
            try:
                shutil.copyfileobj(source, process.stdin)
            except BrokenPipeError:
                pass
            finally:
                process.stdin.close()
            protected_stderr = process.stderr.read() if process.stderr else b""
            return_code = process.wait()
        if return_code:
            raise OperationalSafetyError(
                "mysql restore failed with exit code {} ({}). The target may be partially restored; "
                "quarantine or recreate it before retrying.".format(
                    return_code, _safe_mysql_error(protected_stderr)
                )
            )
    finally:
        defaults.unlink(missing_ok=True)

    verification = {
        "format": "ccf-restore-verification-v1",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "target_environment": environment,
        "target_database": url.database,
        "source_environment": manifest.get("source_environment"),
        "source_database": manifest.get("source_database"),
        "backup_file": args.backup.name,
        "backup_sha256": manifest["sha256"],
        "connectivity": False,
        "alembic_versions": [],
        "table_count": 0,
    }
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        verification["connectivity"] = True
        verification["table_count"] = len(inspect(connection).get_table_names())
        try:
            verification["alembic_versions"] = sorted(
                row[0] for row in connection.execute(text("SELECT version_num FROM alembic_version"))
            )
        except Exception:
            verification["alembic_versions"] = []
    engine.dispose()

    record = args.verification_dir / "restore-{}-{}.json".format(
        environment, utc_timestamp()
    )
    write_json_exclusive(record, verification)
    print("Restore completed. Verification record: {}".format(record))
    print("Complete the application-level restoration checklist before acceptance.")


if __name__ == "__main__":
    try:
        main()
    except (OperationalSafetyError, json.JSONDecodeError) as error:
        print("Restore refused: {}".format(error), file=sys.stderr)
        raise SystemExit(2)
