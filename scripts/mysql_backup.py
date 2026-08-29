#!/usr/bin/env python3
"""Create an encrypted-storage-ready, checksummed logical MySQL backup."""

from __future__ import annotations

import argparse
import gzip
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

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
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--label", default="scheduled")
    return parser.parse_args()


def main():
    args = arguments()
    if shutil.which("mysqldump") is None:
        raise OperationalSafetyError("mysqldump is required on PATH.")
    _raw_url, url = configured_database()
    environment = environment_name()
    if not environment:
        raise OperationalSafetyError("CCF_ENV is required to label the backup environment.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_timestamp()
    safe_label = "".join(character for character in args.label if character.isalnum() or character in "-_")
    if not safe_label:
        raise OperationalSafetyError("--label must contain letters, numbers, hyphens, or underscores.")
    backup = args.output_dir / "ccf-{}-{}-{}.sql.gz".format(environment, safe_label, timestamp)
    manifest = backup.with_suffix(backup.suffix + ".json")
    if backup.exists() or manifest.exists():
        raise OperationalSafetyError("Refusing to overwrite an existing backup or manifest.")

    defaults = client_defaults_file(url)
    command = [
        "mysqldump",
        "--defaults-extra-file={}".format(defaults),
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--events",
        "--hex-blob",
        "--set-gtid-purged=OFF",
        url.database,
    ]
    try:
        with backup.open("xb") as raw_output, gzip.GzipFile(
            fileobj=raw_output, mode="wb"
        ) as output:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            assert process.stdout is not None
            shutil.copyfileobj(process.stdout, output)
            process.stdout.close()
            _protected_stderr = process.stderr.read() if process.stderr else b""
            return_code = process.wait()
        if return_code:
            backup.unlink(missing_ok=True)
            raise OperationalSafetyError(
                "mysqldump failed with exit code {}. Review protected operator output.".format(
                    return_code
                )
            )
        with gzip.open(backup, "rb") as verification_stream:
            verification_stream.read(1)
    finally:
        defaults.unlink(missing_ok=True)

    write_json_exclusive(
        manifest,
        {
            "format": "mysql-logical-gzip-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_environment": environment,
            "source_database": url.database,
            "backup_file": backup.name,
            "bytes": backup.stat().st_size,
            "sha256": sha256_file(backup),
            "encryption_required_at_rest": True,
        },
    )
    print("Backup created: {}".format(backup))
    print("Manifest created: {}".format(manifest))


if __name__ == "__main__":
    try:
        main()
    except OperationalSafetyError as error:
        print("Backup refused: {}".format(error), file=sys.stderr)
        raise SystemExit(2)
