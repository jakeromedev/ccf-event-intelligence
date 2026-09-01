"""SQLAlchemy database lifecycle and a small query compatibility facade.

Schema creation and upgrades belong to Alembic. This module deliberately does
not create or alter tables during Flask startup.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path

from flask import current_app, g
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker


class DatabaseConfigurationError(RuntimeError):
    """Raised when database configuration is missing or unsafe."""


class Row(Mapping):
    """Mapping row that supports both named and positional access."""

    def __init__(self, keys, values):
        self._keys = tuple(keys)
        # Preserve the application's historical ISO-string result contract even
        # though MySQL now stores real DATE and DATETIME values.
        self._values = tuple(
            value.isoformat(sep=" ")
            if isinstance(value, datetime)
            else value.isoformat()
            if isinstance(value, date)
            else value
            for value in values
        )
        self._mapping = dict(zip(self._keys, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)

    def keys(self):
        return self._keys


class Result:
    """Keep existing query call sites compact while using SQLAlchemy results."""

    def __init__(self, result):
        self._result = result
        self._keys = tuple(result.keys()) if result.returns_rows else ()
        self.lastrowid = getattr(result, "lastrowid", None)
        self.rowcount = result.rowcount

    def _row(self, value):
        return None if value is None else Row(self._keys, tuple(value))

    def fetchone(self):
        return self._row(self._result.fetchone())

    def fetchall(self):
        return [self._row(value) for value in self._result.fetchall()]

    def __iter__(self):
        for value in self._result:
            yield self._row(value)


def _replace_qmarks(statement):
    """Convert DB-API qmark binds to named binds while ignoring SQL quotes."""
    output = []
    bind_count = 0
    quote = None
    index = 0
    while index < len(statement):
        character = statement[index]
        if quote:
            output.append(character)
            if character == quote:
                if index + 1 < len(statement) and statement[index + 1] == quote:
                    output.append(statement[index + 1])
                    index += 1
                else:
                    quote = None
        elif character in ("'", '"', "`"):
            quote = character
            output.append(character)
        elif character == "?":
            output.append(":p{}".format(bind_count))
            bind_count += 1
        else:
            output.append(character)
        index += 1
    return "".join(output), bind_count


def _named_params(values, count):
    values = tuple(values or ())
    if len(values) != count:
        raise ValueError("SQL expected {} parameters but received {}.".format(count, len(values)))
    return {"p{}".format(index): value for index, value in enumerate(values)}


class Database:
    """Request-scoped SQLAlchemy session with explicit transaction control."""

    def __init__(self, session: Session):
        self.session = session

    @property
    def dialect_name(self):
        return self.session.get_bind().dialect.name

    @property
    def is_mysql(self):
        return self.dialect_name == "mysql"

    def _dialect_sql(self, statement):
        if not self.is_mysql:
            return statement
        # MySQL tables use a case-insensitive utf8mb4 collation by default.
        statement = re.sub(r"\s+COLLATE\s+NOCASE\b", "", statement, flags=re.IGNORECASE)
        statement = re.sub(r"\bAS\s+TEXT\b", "AS CHAR", statement, flags=re.IGNORECASE)
        statement = re.sub(
            r"\bAS\s+REAL\b", "AS DECIMAL(30, 10)", statement, flags=re.IGNORECASE
        )
        statement = statement.replace(
            "COALESCE(participant.first_name, '') || ' ' ||\n"
            "                          COALESCE(participant.last_name, '')",
            "CONCAT(COALESCE(participant.first_name, ''), ' ',\n"
            "                          COALESCE(participant.last_name, ''))",
        )
        statement = statement.replace(
            "GROUP_CONCAT(s.name, ' | ')", "GROUP_CONCAT(s.name SEPARATOR ' | ')"
        )
        return statement

    def execute(self, statement, params=None):
        if not isinstance(statement, str):
            return Result(self.session.execute(statement, params or {}))
        statement = self._dialect_sql(statement)
        converted, count = _replace_qmarks(statement)
        if isinstance(params, Mapping):
            if count:
                raise ValueError("Named parameters cannot be mixed with qmark parameters.")
            bound = dict(params)
        else:
            bound = _named_params(params, count)
        return Result(self.session.execute(text(converted), bound))

    def executemany(self, statement, parameter_sets):
        parameter_sets = list(parameter_sets)
        if not parameter_sets:
            return None
        statement = self._dialect_sql(statement)
        converted, count = _replace_qmarks(statement)
        bound = [_named_params(values, count) for values in parameter_sets]
        return Result(self.session.execute(text(converted), bound))

    def lock_event(self, event_id):
        """Serialize activation decisions for one event on MySQL."""
        suffix = " FOR UPDATE" if self.is_mysql else ""
        return self.execute("SELECT id FROM events WHERE id = ?" + suffix, (event_id,)).fetchone()

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()

    def close(self):
        self.session.close()


def _database_url(app):
    configured = app.config.get("DATABASE_URL")
    if not configured:
        raise DatabaseConfigurationError(
            "DATABASE_URL is required (for example "
            "mysql+pymysql://user:password@localhost:3306/ccf_events)."
        )
    url = make_url(configured)
    if not app.config.get("TESTING") and url.get_backend_name() != "mysql":
        raise DatabaseConfigurationError("Normal runtime requires a MySQL DATABASE_URL.")
    return configured


def init_app(app):
    url = _database_url(app)
    engine_options = {"pool_pre_ping": True, "future": True}
    if make_url(url).get_backend_name() == "mysql":
        engine_options.update(
            pool_recycle=app.config.get("SQLALCHEMY_POOL_RECYCLE", 1800),
            pool_size=app.config.get("SQLALCHEMY_POOL_SIZE", 5),
            max_overflow=app.config.get("SQLALCHEMY_MAX_OVERFLOW", 10),
            isolation_level=app.config.get("SQLALCHEMY_ISOLATION_LEVEL", "READ COMMITTED"),
            connect_args={
                "charset": "utf8mb4",
                # CURRENT_TIMESTAMP must follow the same UTC-at-rest contract
                # as application-generated timestamps.
                "init_command": "SET time_zone = '+00:00'",
            },
        )
    else:
        engine_options["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **engine_options)
    app.extensions["sqlalchemy_engine"] = engine
    app.extensions["sqlalchemy_session_factory"] = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True
    )
    app.teardown_appcontext(close_db)

    @app.cli.command("db-check")
    def db_check_command():
        """Verify connectivity without mutating the schema."""
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("Database connection successful.")


def get_engine() -> Engine:
    return current_app.extensions["sqlalchemy_engine"]


def _expected_schema_heads():
    project_root = Path(current_app.root_path).resolve().parent
    config = AlembicConfig(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    return set(ScriptDirectory.from_config(config).get_heads())


def check_database_readiness():
    """Return a public-safe dependency status without exposing SQL or credentials."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
            versions = {
                row[0]
                for row in connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).fetchall()
            }
    except Exception:
        return False, "database_unavailable"
    try:
        expected = _expected_schema_heads()
    except Exception:
        return False, "schema_check_unavailable"
    if versions != expected:
        return False, "schema_not_current"
    return True, "ready"


def get_db():
    if "db" not in g:
        factory = current_app.extensions["sqlalchemy_session_factory"]
        g.db = Database(factory())
    return g.db


def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()
