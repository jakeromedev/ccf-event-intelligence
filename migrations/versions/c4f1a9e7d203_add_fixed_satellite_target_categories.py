"""add fixed satellite target categories

Revision ID: c4f1a9e7d203
Revises: b8d3e6f1a924
Create Date: 2026-09-05 14:00:00
"""

from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "c4f1a9e7d203"
down_revision: Union[str, Sequence[str], None] = "b8d3e6f1a924"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CATEGORIES = (
    ("outside_metro_manila", "Outside Metro Manila Hubs"),
    ("within_metro_manila", "Within Metro Manila Hubs"),
    ("main", "Main"),
)
TARGET_MAX = 1_000_000_000


def _normalized_name(value):
    return " ".join((value or "").strip().lower().split())


def _migrate_explicit_legacy_datasets(connection):
    """Copy only legacy datasets whose names explicitly identify a category.

    Arbitrary dataset names cannot be classified safely. If multiple legacy
    datasets explicitly name the same category for an Event, that category is
    also left at its seeded zero value rather than choosing one implicitly.
    """
    aliases = {
        _normalized_name(alias): key
        for key, display_name in CATEGORIES
        for alias in (key, display_name)
    }
    candidates = defaultdict(list)
    rows = connection.execute(
        sa.text(
            """
            SELECT id, event_id, name, participant_target
            FROM satellite_datasets
            ORDER BY event_id, id
            """
        )
    ).mappings()
    for row in rows:
        category_key = aliases.get(_normalized_name(row["name"]))
        if category_key is not None:
            candidates[(row["event_id"], category_key)].append(row)

    mapped_datasets = {}
    for (event_id, category_key), matches in candidates.items():
        if len(matches) != 1:
            continue
        match = matches[0]
        target = match["participant_target"]
        if target is None or target < 0 or target > TARGET_MAX:
            continue
        connection.execute(
            sa.text(
                """
                UPDATE event_satellite_target_categories
                SET participant_target = :target,
                    updated_at = CURRENT_TIMESTAMP
                WHERE event_id = :event_id AND category_key = :category_key
                """
            ),
            {
                "target": target,
                "event_id": event_id,
                "category_key": category_key,
            },
        )
        mapped_datasets[match["id"]] = (event_id, category_key)

    if not mapped_datasets:
        return

    links = connection.execute(
        sa.text(
            """
            SELECT DISTINCT link.satellite_dataset_id, satellite.directory_id
            FROM satellite_dataset_satellites link
            JOIN satellites satellite ON satellite.id = link.satellite_id
            JOIN satellite_directory directory
              ON directory.id = satellite.directory_id
            JOIN satellite_hubs hub ON hub.id = directory.hub_id
            JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
            WHERE satellite.directory_id IS NOT NULL
            """
        )
    ).mappings()
    memberships = defaultdict(set)
    for link in links:
        mapped = mapped_datasets.get(link["satellite_dataset_id"])
        if mapped is None:
            continue
        event_id, category_key = mapped
        memberships[(event_id, link["directory_id"])].add(category_key)

    # Enforce the adopted exclusive-category rule without guessing when old
    # datasets overlap. Unambiguous canonical memberships are preserved.
    for (event_id, directory_id), category_keys in memberships.items():
        if len(category_keys) != 1:
            continue
        connection.execute(
            sa.text(
                """
                INSERT INTO event_satellite_target_satellites (
                    event_id, category_key, directory_id
                ) VALUES (:event_id, :category_key, :directory_id)
                """
            ),
            {
                "event_id": event_id,
                "category_key": next(iter(category_keys)),
                "directory_id": directory_id,
            },
        )


def upgrade() -> None:
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    table_options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }
    op.create_table(
        "event_satellite_target_categories",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("category_key", sa.String(length=32), nullable=False),
        sa.Column(
            "participant_target", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category_key IN "
            "('outside_metro_manila','within_metro_manila','main')",
            name="ck_event_satellite_target_categories_key",
        ),
        sa.CheckConstraint(
            "participant_target >= 0 AND participant_target <= 1000000000",
            name="ck_event_satellite_target_categories_target",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "category_key",
            name="uq_event_satellite_target_categories_event_key",
        ),
        **table_options,
    )
    op.create_index(
        "idx_event_satellite_target_categories_event",
        "event_satellite_target_categories",
        ["event_id", "category_key"],
    )

    op.create_table(
        "event_satellite_target_satellites",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("category_key", sa.String(length=32), nullable=False),
        sa.Column("directory_id", identifier, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "category_key"],
            [
                "event_satellite_target_categories.event_id",
                "event_satellite_target_categories.category_key",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["directory_id"], ["satellite_directory.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "category_key",
            "directory_id",
            name="uq_event_satellite_target_satellites_member",
        ),
        sa.UniqueConstraint(
            "event_id",
            "directory_id",
            name="uq_event_satellite_target_satellites_exclusive",
        ),
        **table_options,
    )
    op.create_index(
        "idx_event_satellite_target_satellites_category",
        "event_satellite_target_satellites",
        ["event_id", "category_key"],
    )
    op.create_index(
        "idx_event_satellite_target_satellites_directory",
        "event_satellite_target_satellites",
        ["directory_id"],
    )

    connection = op.get_bind()
    events = connection.execute(sa.text("SELECT id FROM events ORDER BY id")).scalars()
    for event_id in events:
        for category_key, _display_name in CATEGORIES:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO event_satellite_target_categories (
                        event_id, category_key, participant_target
                    ) VALUES (:event_id, :category_key, 0)
                    """
                ),
                {"event_id": event_id, "category_key": category_key},
            )

    _migrate_explicit_legacy_datasets(connection)


def downgrade() -> None:
    op.drop_table("event_satellite_target_satellites")
    op.drop_table("event_satellite_target_categories")
