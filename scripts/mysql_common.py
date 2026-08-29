"""Shared, credential-safe helpers for MySQL operational scripts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url


class OperationalSafetyError(RuntimeError):
    """Raised when an operator confirmation or safe prerequisite is missing."""


def configured_database():
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        raise OperationalSafetyError("DATABASE_URL is required.")
    url = make_url(raw_url)
    if url.get_backend_name() != "mysql" or not url.database:
        raise OperationalSafetyError("DATABASE_URL must identify an explicit MySQL database.")
    return raw_url, url


def environment_name():
    return os.environ.get("CCF_ENV", "").strip().casefold()


def client_defaults_file(url):
    handle = tempfile.NamedTemporaryFile(
        mode="w", prefix="ccf-mysql-", suffix=".cnf", delete=False
    )
    try:
        handle.write("[client]\n")
        handle.write("user={}\n".format(url.username or ""))
        handle.write("password={}\n".format(url.password or ""))
        handle.write("host={}\n".format(url.host or "127.0.0.1"))
        handle.write("port={}\n".format(url.port or 3306))
        handle.write("default-character-set=utf8mb4\n")
        handle.close()
        os.chmod(handle.name, stat.S_IRUSR | stat.S_IWUSR)
        return Path(handle.name)
    except Exception:
        handle.close()
        Path(handle.name).unlink(missing_ok=True)
        raise


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json_exclusive(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")
