"""PII-conscious structured logging and request correlation."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone

from flask import g, request


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
RESERVED_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}
SAFE_OPERATIONAL_FIELDS = {
    "batch_id",
    "buyer_rows",
    "changed",
    "debug",
    "duration_ms",
    "endpoint",
    "environment",
    "error_type",
    "event",
    "event_id",
    "failed_count",
    "method",
    "matched_count",
    "path",
    "proxy_enabled",
    "reason",
    "registrant_id",
    "registrant_rows",
    "request_id",
    "role",
    "row_count",
    "secure_cookies",
    "skipped_count",
    "status",
    "threads",
    "ticket_rows",
    "user_id",
    "valid",
    "validation_error_count",
    "validation_warning_count",
    "worker_pid",
    "workers",
}


class JsonLogFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if (
                key.startswith("_")
                or key in RESERVED_RECORD_FIELDS
                or key not in SAFE_OPERATIONAL_FIELDS
            ):
                continue
            if value is not None and isinstance(value, (str, int, float, bool)):
                payload[key] = value
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def configure_logging(app):
    handler = logging.StreamHandler(sys.stdout)
    if app.config["LOG_FORMAT"] == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
    level = getattr(logging, app.config["LOG_LEVEL"], logging.INFO)
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(level)
    app.logger.propagate = False

    @app.before_request
    def start_request_observation():
        supplied = request.headers.get("X-Request-ID", "")
        g.request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid.uuid4().hex
        g.request_started_at = time.perf_counter()

    @app.after_request
    def finish_request_observation(response):
        request_id = getattr(g, "request_id", uuid.uuid4().hex)
        response.headers["X-Request-ID"] = request_id
        duration_ms = round(
            (time.perf_counter() - getattr(g, "request_started_at", time.perf_counter()))
            * 1000,
            2,
        )
        is_health = request.endpoint in {"operations.liveness", "operations.readiness"}
        if not is_health or response.status_code >= 400:
            app.logger.info(
                "request_completed",
                extra={
                    "event": "request_completed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "endpoint": request.endpoint or "unmatched",
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        return response

    app.logger.info(
        "application_configured",
        extra={
            "event": "application_configured",
            "environment": app.config["APP_ENV"],
            "debug": bool(app.config["DEBUG"]),
            "secure_cookies": bool(app.config["SESSION_COOKIE_SECURE"]),
            "proxy_enabled": any(app.config["PROXY_HOPS"].values()),
        },
    )
