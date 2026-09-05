"""add password-gated public dashboard access

Revision ID: f1a4c8e2d607
Revises: e7c3a9f5d206
Create Date: 2026-09-05 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a4c8e2d607"
down_revision: Union[str, Sequence[str], None] = "e7c3a9f5d206"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("public_dashboard_password_hash", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column(
            "public_dashboard_access_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_column("public_dashboard_access_version")
        batch_op.drop_column("public_dashboard_password_hash")
