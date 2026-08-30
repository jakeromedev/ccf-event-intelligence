"""add attestation verification current state

Revision ID: b7e4c1a9d306
Revises: a9d3c7e5f102
Create Date: 2026-08-30 04:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "b7e4c1a9d306"
down_revision: Union[str, Sequence[str], None] = "a9d3c7e5f102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "attestation_verifications",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("registrant_id", identifier, nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
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
            "status IN ('pending','verified','invalid')",
            name="ck_attestation_verifications_status",
        ),
        sa.ForeignKeyConstraint(
            ["registrant_id"], ["registrants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "registrant_id", name="uq_attestation_verifications_registrant"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_attestation_verifications_status",
        "attestation_verifications",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_attestation_verifications_reviewer",
        "attestation_verifications",
        ["updated_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    # Dropping the table removes its indexes with their foreign keys. MySQL
    # refuses to drop the reviewer index separately while the FK still uses it.
    op.drop_table("attestation_verifications")
