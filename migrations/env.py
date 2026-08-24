"""Alembic environment for the canonical SQLAlchemy metadata."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, make_url, pool

from app.models import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    """Ignore MySQL's implicit supporting indexes for composite foreign keys."""
    if (
        type_ == "index"
        and reflected
        and compare_to is None
        and name == "event_id_2"
        and obj.table.name
        in {"curated_registrant_satellites", "satellite_dataset_satellites"}
    ):
        return False
    return True


def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine_options = {}
    if make_url(config.get_main_option("sqlalchemy.url")).get_backend_name() == "mysql":
        engine_options["connect_args"] = {"charset": "utf8mb4"}
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        **engine_options,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
