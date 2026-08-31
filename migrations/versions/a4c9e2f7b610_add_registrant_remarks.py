"""add persistent registrant remarks

Revision ID: a4c9e2f7b610
Revises: f3a8c2d9e401
Create Date: 2026-09-01 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "a4c9e2f7b610"
down_revision: Union[str, Sequence[str], None] = "f3a8c2d9e401"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "registrant_remarks",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", identifier, nullable=True),
        sa.Column("resolved_by_user_id", identifier, nullable=True),
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
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','resolved')",
            name="ck_registrant_remarks_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) OR "
            "(status = 'resolved' AND resolved_at IS NOT NULL)",
            name="ck_registrant_remarks_resolution",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_registrant_remarks_participant_status_created",
        "registrant_remarks",
        ["event_id", "attestation_participant_id", "status", "created_at"],
    )
    op.create_index(
        "idx_registrant_remarks_creator",
        "registrant_remarks",
        ["created_by_user_id"],
    )
    op.create_index(
        "idx_registrant_remarks_resolver",
        "registrant_remarks",
        ["resolved_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("registrant_remarks")
