"""Environment-driven application configuration with production safety checks."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path


ENVIRONMENTS = {"development", "testing", "staging", "production"}
PLACEHOLDER_SECRETS = {
    "dev-only-change-me",
    "replace-with-a-long-random-value",
    "change-me",
    "secret",
}


class ApplicationConfigurationError(RuntimeError):
    """Raised when an environment would start with unsafe configuration."""


def environment_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def environment_integer(name, default, minimum=0, maximum=None):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ApplicationConfigurationError("{} must be an integer.".format(name)) from exc
    if parsed < minimum or (maximum is not None and parsed > maximum):
        raise ApplicationConfigurationError(
            "{} must be between {} and {}.".format(
                name, minimum, maximum if maximum is not None else "the supported maximum"
            )
        )
    return parsed


def _environment_name(test_config):
    if test_config and test_config.get("APP_ENV"):
        return str(test_config["APP_ENV"]).strip().casefold()
    if test_config and test_config.get("TESTING"):
        return "testing"
    return os.environ.get("CCF_ENV", "development").strip().casefold()


def _proxy_hops():
    return {
        "x_for": environment_integer("CCF_PROXY_X_FOR", 0, maximum=5),
        "x_proto": environment_integer("CCF_PROXY_X_PROTO", 0, maximum=5),
        "x_host": environment_integer("CCF_PROXY_X_HOST", 0, maximum=5),
        "x_port": environment_integer("CCF_PROXY_X_PORT", 0, maximum=5),
        "x_prefix": environment_integer("CCF_PROXY_X_PREFIX", 0, maximum=5),
    }


def configure_app(app, test_config=None):
    environment = _environment_name(test_config)
    if environment not in ENVIRONMENTS:
        raise ApplicationConfigurationError(
            "CCF_ENV must be one of: {}.".format(", ".join(sorted(ENVIRONMENTS)))
        )

    production = environment == "production"
    staging = environment == "staging"
    default_staging_dir = Path(app.instance_path) / "staged_imports"
    same_site = os.environ.get("CCF_SESSION_COOKIE_SAMESITE", "Lax").strip().title()
    trusted_hosts = [
        item.strip()
        for item in os.environ.get("CCF_TRUSTED_HOSTS", "").split(",")
        if item.strip()
    ]

    app.config.from_mapping(
        APP_ENV=environment,
        SECRET_KEY=os.environ.get("CCF_DASHBOARD_SECRET", "dev-only-change-me"),
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        STAGING_DIR=os.environ.get("CCF_STAGING_DIR", str(default_staging_dir)),
        MAX_CONTENT_LENGTH=environment_integer(
            "CCF_MAX_UPLOAD_MB", 32, minimum=1, maximum=1024
        )
        * 1024
        * 1024,
        AUTHENTICATION_DISABLED=environment_flag("CCF_AUTHENTICATION_DISABLED", False),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=same_site,
        SESSION_COOKIE_SECURE=environment_flag(
            "CCF_SESSION_COOKIE_SECURE", production
        ),
        PERMANENT_SESSION_LIFETIME=timedelta(
            hours=environment_integer("CCF_SESSION_HOURS", 8, minimum=1, maximum=24)
        ),
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_TIME_LIMIT=environment_integer(
            "CCF_CSRF_TIME_LIMIT_SECONDS", 7200, minimum=300, maximum=86400
        ),
        ADMIN_TABLES_ENABLED=environment_flag("CCF_ADMIN_TABLES_ENABLED", True),
        ADMIN_TABLES_AUTHORIZER=None,
        ANALYTICS_MIN_GROUP_SIZE=environment_integer(
            "CCF_ANALYTICS_MIN_GROUP_SIZE", 5, minimum=1, maximum=100
        ),
        STANDARD_USER_MUTATIONS_ALLOWED=environment_flag(
            "CCF_STANDARD_USER_MUTATIONS_ALLOWED",
            environment in {"development", "testing"},
        ),
        LOG_LEVEL=os.environ.get(
            "CCF_LOG_LEVEL",
            "WARNING" if environment == "testing" else "INFO" if production or staging else "DEBUG",
        ).strip().upper(),
        LOG_FORMAT=os.environ.get(
            "CCF_LOG_FORMAT", "json" if production or staging else "text"
        ).strip().casefold(),
        PROXY_HOPS=_proxy_hops(),
        TRUSTED_HOSTS=trusted_hosts or None,
        PREFERRED_URL_SCHEME="https" if production else "http",
        REQUIRE_SCHEMA_CURRENT=environment_flag(
            "CCF_REQUIRE_SCHEMA_CURRENT", production or staging
        ),
        SQLALCHEMY_POOL_RECYCLE=environment_integer(
            "CCF_DB_POOL_RECYCLE_SECONDS", 1800, minimum=60, maximum=86400
        ),
        SQLALCHEMY_POOL_SIZE=environment_integer(
            "CCF_DB_POOL_SIZE", 5, minimum=1, maximum=100
        ),
        SQLALCHEMY_MAX_OVERFLOW=environment_integer(
            "CCF_DB_MAX_OVERFLOW", 10, minimum=0, maximum=200
        ),
        DEBUG=environment_flag("CCF_DASHBOARD_DEBUG", False),
    )

    if test_config:
        app.config.update(test_config)

    validate_config(app.config)


def validate_config(config):
    environment = config["APP_ENV"]
    if config["SESSION_COOKIE_SAMESITE"] not in {"Lax", "Strict", "None"}:
        raise ApplicationConfigurationError(
            "CCF_SESSION_COOKIE_SAMESITE must be Lax, Strict, or None."
        )
    if config["SESSION_COOKIE_SAMESITE"] == "None" and not config["SESSION_COOKIE_SECURE"]:
        raise ApplicationConfigurationError(
            "SameSite=None requires secure session cookies."
        )
    if config["LOG_FORMAT"] not in {"json", "text"}:
        raise ApplicationConfigurationError("CCF_LOG_FORMAT must be json or text.")
    if config["LOG_LEVEL"] not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ApplicationConfigurationError(
            "CCF_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL."
        )
    if environment != "production":
        return

    secret = str(config.get("SECRET_KEY") or "")
    unsafe_markers = ("replace", "change-me", "placeholder", "generated-secret")
    if (
        len(secret) < 32
        or secret.casefold() in PLACEHOLDER_SECRETS
        or any(marker in secret.casefold() for marker in unsafe_markers)
    ):
        raise ApplicationConfigurationError(
            "Production requires CCF_DASHBOARD_SECRET with at least 32 non-placeholder characters."
        )
    if config.get("DEBUG"):
        raise ApplicationConfigurationError("Production debug mode must remain disabled.")
    if config.get("AUTHENTICATION_DISABLED"):
        raise ApplicationConfigurationError(
            "Production authentication cannot be disabled."
        )
    if not config.get("SESSION_COOKIE_SECURE"):
        raise ApplicationConfigurationError(
            "Production requires CCF_SESSION_COOKIE_SECURE=1."
        )
    if not config.get("WTF_CSRF_ENABLED"):
        raise ApplicationConfigurationError("Production CSRF protection cannot be disabled.")
    if not config.get("REQUIRE_SCHEMA_CURRENT"):
        raise ApplicationConfigurationError(
            "Production requires schema compatibility checks at startup."
        )
    if not config.get("TRUSTED_HOSTS"):
        raise ApplicationConfigurationError(
            "Production requires at least one CCF_TRUSTED_HOSTS value."
        )
