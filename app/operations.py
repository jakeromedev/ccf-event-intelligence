"""Minimal public operational health endpoints and production checks."""

from __future__ import annotations

import click
from flask import Blueprint, current_app, jsonify

from .db import check_database_readiness


bp = Blueprint("operations", __name__)


@bp.get("/health/live")
def liveness():
    return jsonify({"status": "ok"})


@bp.get("/health/ready")
def readiness():
    ready, reason = check_database_readiness()
    status = 200 if ready else 503
    if not ready:
        current_app.logger.error(
            "readiness_failed",
            extra={"event": "readiness_failed", "reason": reason},
        )
    return jsonify({"status": "ready" if ready else "unavailable"}), status


def init_app(app):
    @app.cli.command("production-check")
    def production_check_command():
        """Validate production-sensitive configuration and schema state."""
        ready, reason = check_database_readiness()
        if not ready:
            raise click.ClickException(
                "Production readiness check failed: {}.".format(reason)
            )
        click.echo("Production configuration, database, and schema checks passed.")
