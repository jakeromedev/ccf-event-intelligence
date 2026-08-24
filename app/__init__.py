import os
from datetime import timedelta
from pathlib import Path

from flask import Flask

from .auth import bp as auth_bp
from .auth import init_app as init_auth_app
from .db import init_app as init_db_app
from .extensions import csrf
from .routes import bp


def _environment_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("CCF_DASHBOARD_SECRET", "dev-only-change-me"),
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        STAGING_DIR=str(Path(app.instance_path) / "staged_imports"),
        MAX_CONTENT_LENGTH=32 * 1024 * 1024,
        AUTHENTICATION_DISABLED=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_environment_flag("CCF_SESSION_COOKIE_SECURE"),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_TIME_LIMIT=7200,
        # The current application is deployed as a trusted administrative tool.
        # Integrations can replace this with a request-aware authorization hook.
        ADMIN_TABLES_ENABLED=True,
        ADMIN_TABLES_AUTHORIZER=None,
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["STAGING_DIR"]).mkdir(parents=True, exist_ok=True)

    # This configures a lazy SQLAlchemy engine only. Alembic is solely
    # responsible for creating and upgrading the database schema.
    init_db_app(app)
    app.register_blueprint(auth_bp)
    # Register the authentication guard before global CSRF validation so an
    # unauthenticated POST is redirected to login instead of leaking a CSRF error.
    init_auth_app(app)
    csrf.init_app(app)
    app.register_blueprint(bp)

    @app.context_processor
    def administrative_access_context():
        from .routes import can_access_admin_tables

        return {"admin_tables_allowed": can_access_admin_tables()}

    return app
