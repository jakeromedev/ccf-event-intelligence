from pathlib import Path

from flask import Flask, g, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import HTTPException

from .auth import bp as auth_bp
from .auth import init_app as init_auth_app
from .config import ApplicationConfigurationError, configure_app
from .db import init_app as init_db_app
from .extensions import csrf
from .observability import configure_logging
from .operations import bp as operations_bp
from .operations import init_app as init_operations_app
from .routes import bp


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    configure_app(app, test_config)
    configure_logging(app)

    proxy_hops = app.config["PROXY_HOPS"]
    if any(proxy_hops.values()):
        app.wsgi_app = ProxyFix(app.wsgi_app, **proxy_hops)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["STAGING_DIR"]).mkdir(parents=True, exist_ok=True)

    # This configures a lazy SQLAlchemy engine only. Alembic is solely
    # responsible for creating and upgrading the database schema.
    init_db_app(app)
    app.register_blueprint(operations_bp)
    init_operations_app(app)
    app.register_blueprint(auth_bp)
    # Register the authentication guard before global CSRF validation so an
    # unauthenticated POST is redirected to login instead of leaking a CSRF error.
    init_auth_app(app)
    csrf.init_app(app)
    app.register_blueprint(bp)

    if app.config["REQUIRE_SCHEMA_CURRENT"]:
        from .db import check_database_readiness

        with app.app_context():
            ready, reason = check_database_readiness()
        if not ready:
            app.logger.critical(
                "startup_readiness_failed",
                extra={"event": "startup_readiness_failed", "reason": reason},
            )
            raise ApplicationConfigurationError(
                "Application startup readiness check failed: {}.".format(reason)
            )

    @app.context_processor
    def administrative_access_context():
        from .routes import can_access_admin_tables, can_access_registrations

        return {
            "admin_tables_allowed": can_access_admin_tables(),
            "registrations_allowed": can_access_registrations(),
            "max_upload_mb": app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
        }

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if isinstance(error, HTTPException):
            return error
        if app.config.get("TESTING"):
            raise error
        request_id = getattr(g, "request_id", None)
        app.logger.error(
            "unexpected_server_error",
            extra={
                "event": "unexpected_server_error",
                "request_id": request_id,
                "error_type": type(error).__name__,
            },
        )
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"status": "error", "request_id": request_id}), 500
        return render_template("error.html", request_id=request_id), 500

    return app
