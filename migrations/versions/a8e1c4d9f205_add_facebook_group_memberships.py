"""add durable registrant Facebook Group membership tags

Revision ID: a8e1c4d9f205
Revises: f1a4c8e2d607
Create Date: 2026-09-08 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "a8e1c4d9f205"
down_revision: Union[str, Sequence[str], None] = "f1a4c8e2d607"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "registrant_facebook_group_memberships",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column(
            "joined", sa.Boolean(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("updated_by_user_id", identifier, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "attestation_participant_id",
            name="uq_registrant_fb_group_memberships_participant",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_registrant_fb_group_memberships_joined",
        "registrant_facebook_group_memberships",
        ["event_id", "joined"],
    )
    op.create_index(
        "idx_registrant_fb_group_memberships_updater",
        "registrant_facebook_group_memberships",
        ["updated_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("registrant_facebook_group_memberships")
