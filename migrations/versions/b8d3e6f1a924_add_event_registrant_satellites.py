"""add event registrant satellites

Revision ID: b8d3e6f1a924
Revises: f7c2a8d5e913
Create Date: 2026-09-03 18:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "b8d3e6f1a924"
down_revision: Union[str, Sequence[str], None] = "f7c2a8d5e913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "event_registrant_satellites",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column("directory_id", identifier, nullable=False),
        sa.Column("assignment_source", sa.String(length=16), nullable=False),
        sa.Column("source_batch_id", identifier, nullable=True),
        sa.Column("updated_by_user_id", identifier, nullable=True),
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
            "assignment_source IN ('manual','automatic')",
            name="ck_event_registrant_satellites_source",
        ),
        sa.CheckConstraint(
            "(assignment_source = 'manual' AND source_batch_id IS NULL) OR "
            "(assignment_source = 'automatic' AND source_batch_id IS NOT NULL)",
            name="ck_event_registrant_satellites_source_batch",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "source_batch_id"],
            ["import_batches.event_id", "import_batches.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["directory_id"],
            ["satellite_directory.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "attestation_participant_id",
            name="uq_event_registrant_satellites_participant",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_event_registrant_satellites_directory",
        "event_registrant_satellites",
        ["directory_id", "event_id"],
    )
    op.create_index(
        "idx_event_registrant_satellites_source_batch",
        "event_registrant_satellites",
        ["event_id", "source_batch_id"],
    )
    op.create_index(
        "idx_event_registrant_satellites_updater",
        "event_registrant_satellites",
        ["updated_by_user_id"],
    )
    op.create_table(
        "event_registrant_satellite_audits",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("previous_directory_id", identifier, nullable=True),
        sa.Column("previous_directory_name", sa.String(length=512), nullable=True),
        sa.Column("new_directory_id", identifier, nullable=True),
        sa.Column("new_directory_name", sa.String(length=512), nullable=True),
        sa.Column("changed_by_user_id", identifier, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('manual','reset')",
            name="ck_event_registrant_satellite_audits_action",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["previous_directory_id"],
            ["satellite_directory.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["new_directory_id"],
            ["satellite_directory.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_event_registrant_satellite_audits_participant",
        "event_registrant_satellite_audits",
        ["event_id", "attestation_participant_id", "created_at"],
    )
    op.create_index(
        "idx_event_registrant_satellite_audits_actor",
        "event_registrant_satellite_audits",
        ["changed_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("event_registrant_satellite_audits")
    op.drop_table("event_registrant_satellites")
