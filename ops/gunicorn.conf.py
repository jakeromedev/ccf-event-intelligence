"""Environment-driven Gunicorn settings and machine-readable lifecycle events."""

import json
import os
from datetime import datetime, timezone


bind = "0.0.0.0:{}".format(os.environ.get("PORT", "8080"))
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = None
errorlog = "-"
capture_output = True


def _lifecycle(event, **fields):
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "INFO",
        "logger": "gunicorn.lifecycle",
        "message": event,
        "event": event,
    }
    payload.update(fields)
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def on_starting(server):
    _lifecycle("application_starting", workers=workers, threads=threads)


def when_ready(server):
    _lifecycle("application_ready", workers=workers)


def worker_exit(server, worker):
    _lifecycle("worker_stopped", worker_pid=worker.pid)


def on_exit(server):
    _lifecycle("application_stopped")
