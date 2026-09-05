"""derive Satellite reporting categories from canonical hierarchy

Revision ID: e7c3a9f5d206
Revises: d6a2b8f4c105
Create Date: 2026-09-05 17:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "e7c3a9f5d206"
down_revision: Union[str, Sequence[str], None] = "d6a2b8f4c105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "satellite_hubs",
        sa.Column("is_main", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE satellite_hubs
            SET is_main = 1
            WHERE normalized_name IN ('main', 'main hub')
               OR id IN (
                   SELECT DISTINCT directory.hub_id
                   FROM event_satellite_target_satellites legacy
                   JOIN satellite_directory directory
                     ON directory.id = legacy.directory_id
                   WHERE legacy.category_key = 'main'
                     AND directory.hub_id IS NOT NULL
               )
            """
        )
    )
    op.drop_table("event_satellite_target_satellites")


def downgrade() -> None:
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    table_options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }
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
    connection.execute(
        sa.text(
            """
            INSERT INTO event_satellite_target_satellites (
                event_id, category_key, directory_id
            )
            SELECT DISTINCT source_event.id,
                   CASE
                       WHEN hub.is_main = 1 THEN 'main'
                       ELSE hub_group.code
                   END,
                   directory.id
            FROM events source_event
            JOIN satellite_directory directory
              ON EXISTS (
                  SELECT 1 FROM satellites imported
                  WHERE imported.event_id = source_event.id
                    AND imported.directory_id = directory.id
              ) OR EXISTS (
                  SELECT 1 FROM event_registrant_satellites assignment
                  WHERE assignment.event_id = source_event.id
                    AND assignment.directory_id = directory.id
              )
            JOIN satellite_hubs hub ON hub.id = directory.hub_id
            JOIN hub_groups hub_group ON hub_group.id = hub.hub_group_id
            WHERE hub.is_main = 1
               OR hub_group.code IN (
                   'outside_metro_manila', 'within_metro_manila'
               )
            """
        )
    )
    with op.batch_alter_table("satellite_hubs") as batch_op:
        batch_op.drop_column("is_main")
