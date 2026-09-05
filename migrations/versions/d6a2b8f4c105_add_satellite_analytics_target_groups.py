"""add satellite analytics target groups

Revision ID: d6a2b8f4c105
Revises: c4f1a9e7d203
Create Date: 2026-09-05 15:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "d6a2b8f4c105"
down_revision: Union[str, Sequence[str], None] = "c4f1a9e7d203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CATEGORIES = (
    ("outside_metro_manila", "Outside Metro Manila Hubs"),
    ("within_metro_manila", "Within Metro Manila Hubs"),
    ("main", "Main"),
)


def upgrade() -> None:
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    table_options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }
    op.create_table(
        "event_satellite_target_groups",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("display_label", sa.String(length=160), nullable=False),
        sa.Column(
            "participant_target", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
            "participant_target >= 0 AND participant_target <= 1000000000",
            name="ck_event_satellite_target_groups_target",
        ),
        sa.CheckConstraint(
            "sort_order >= 1 AND sort_order <= 3",
            name="ck_event_satellite_target_groups_sort",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "event_id", name="uq_event_satellite_target_groups_id_event"
        ),
        sa.UniqueConstraint(
            "event_id",
            "sort_order",
            name="uq_event_satellite_target_groups_event_sort",
        ),
        **table_options,
    )
    op.create_index(
        "idx_event_satellite_target_groups_event",
        "event_satellite_target_groups",
        ["event_id", "sort_order"],
    )

    op.create_table(
        "event_satellite_target_group_categories",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("target_group_id", identifier, nullable=False),
        sa.Column("category_key", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category_key IN "
            "('outside_metro_manila','within_metro_manila','main')",
            name="ck_event_satellite_target_group_categories_key",
        ),
        sa.ForeignKeyConstraint(
            ["target_group_id", "event_id"],
            ["event_satellite_target_groups.id", "event_satellite_target_groups.event_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "category_key"],
            [
                "event_satellite_target_categories.event_id",
                "event_satellite_target_categories.category_key",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_group_id",
            "category_key",
            name="uq_event_satellite_target_group_categories_member",
        ),
        sa.UniqueConstraint(
            "event_id",
            "category_key",
            name="uq_event_satellite_target_group_categories_partition",
        ),
        **table_options,
    )
    op.create_index(
        "idx_event_satellite_target_group_categories_group",
        "event_satellite_target_group_categories",
        ["target_group_id"],
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT event_id, category_key, participant_target
            FROM event_satellite_target_categories
            ORDER BY event_id, id
            """
        )
    ).mappings()
    by_event = {}
    for row in rows:
        by_event.setdefault(row["event_id"], {})[row["category_key"]] = row[
            "participant_target"
        ]
    for event_id, targets in by_event.items():
        for sort_order, (category_key, label) in enumerate(CATEGORIES, start=1):
            result = connection.execute(
                sa.text(
                    """
                    INSERT INTO event_satellite_target_groups (
                        event_id, display_label, participant_target, sort_order
                    ) VALUES (:event_id, :label, :target, :sort_order)
                    """
                ),
                {
                    "event_id": event_id,
                    "label": label,
                    "target": targets.get(category_key, 0),
                    "sort_order": sort_order,
                },
            )
            connection.execute(
                sa.text(
                    """
                    INSERT INTO event_satellite_target_group_categories (
                        event_id, target_group_id, category_key
                    ) VALUES (:event_id, :target_group_id, :category_key)
                    """
                ),
                {
                    "event_id": event_id,
                    "target_group_id": result.lastrowid,
                    "category_key": category_key,
                },
            )


def downgrade() -> None:
    op.drop_table("event_satellite_target_group_categories")
    op.drop_table("event_satellite_target_groups")
