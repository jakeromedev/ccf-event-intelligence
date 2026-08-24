#!/usr/bin/env python3
"""Start, stop, or inspect the project-local native MySQL server."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTANCE_DIR = PROJECT_ROOT / "instance"
MYSQLD = INSTANCE_DIR / "mysql-server" / "bin" / "mysqld"
CONFIG = INSTANCE_DIR / "mysql.cnf"
PID_FILE = INSTANCE_DIR / "mysql-run" / "mysql.pid"


def read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def is_running(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def start() -> int:
    pid = read_pid()
    if is_running(pid):
        print(f"MySQL is already running (PID {pid}).")
        return 0
    if not MYSQLD.is_file() or not CONFIG.is_file():
        print("Project-local MySQL is not installed or configured.", file=sys.stderr)
        return 1
    subprocess.run(
        [str(MYSQLD), f"--defaults-file={CONFIG}", "--daemonize"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    pid = read_pid()
    print(f"MySQL started on 127.0.0.1:3306 (PID {pid}).")
    return 0


def stop() -> int:
    pid = read_pid()
    if not is_running(pid):
        print("MySQL is not running.")
        return 0
    assert pid is not None
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        if not is_running(pid):
            print("MySQL stopped.")
            return 0
        time.sleep(0.1)
    print(f"MySQL did not stop within 10 seconds (PID {pid}).", file=sys.stderr)
    return 1


def status() -> int:
    pid = read_pid()
    if is_running(pid):
        print(f"MySQL is running on 127.0.0.1:3306 (PID {pid}).")
        return 0
    print("MySQL is not running.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status"))
    args = parser.parse_args()
    return {"start": start, "stop": stop, "status": status}[args.action]()


if __name__ == "__main__":
    raise SystemExit(main())
