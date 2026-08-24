"""add event-scoped satellite datasets

Revision ID: e8c6f1a2b3d4
Revises: c2a7f6e4b901
Create Date: 2026-08-24 14:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "e8c6f1a2b3d4"
down_revision: Union[str, Sequence[str], None] = "c2a7f6e4b901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "satellite_datasets",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column(
            "name",
            mysql.VARCHAR(length=160, collation="utf8mb4_unicode_ci").with_variant(
                sa.String(length=160, collation="NOCASE"), "sqlite"
            ),
            nullable=False,
        ),
        sa.Column("participant_target", sa.Integer(), nullable=False),
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
            "participant_target >= 0",
            name="ck_satellite_datasets_target_nonnegative",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "name", name="uq_satellite_datasets_event_name"
        ),
        sa.UniqueConstraint(
            "event_id", "id", name="uq_satellite_datasets_event_id"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_satellite_datasets_event",
        "satellite_datasets",
        ["event_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "satellite_dataset_satellites",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("satellite_dataset_id", identifier, nullable=False),
        sa.Column("satellite_batch_id", identifier, nullable=False),
        sa.Column("satellite_id", identifier, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "satellite_dataset_id"],
            ["satellite_datasets.event_id", "satellite_datasets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "satellite_batch_id", "satellite_id"],
            ["satellites.event_id", "satellites.batch_id", "satellites.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "satellite_dataset_id",
            "satellite_id",
            name="uq_satellite_dataset_satellites_pair",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_satellite_dataset_satellites_dataset",
        "satellite_dataset_satellites",
        ["satellite_dataset_id"],
        unique=False,
    )
    op.create_index(
        "idx_satellite_dataset_satellites_satellite",
        "satellite_dataset_satellites",
        ["satellite_id"],
        unique=False,
    )
    op.create_index(
        "idx_satellite_dataset_satellites_event_batch",
        "satellite_dataset_satellites",
        ["event_id", "satellite_batch_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_satellite_dataset_satellites_event_batch",
        table_name="satellite_dataset_satellites",
    )
    op.drop_index(
        "idx_satellite_dataset_satellites_satellite",
        table_name="satellite_dataset_satellites",
    )
    op.drop_index(
        "idx_satellite_dataset_satellites_dataset",
        table_name="satellite_dataset_satellites",
    )
    op.drop_table("satellite_dataset_satellites")
    op.drop_index("idx_satellite_datasets_event", table_name="satellite_datasets")
    op.drop_table("satellite_datasets")
