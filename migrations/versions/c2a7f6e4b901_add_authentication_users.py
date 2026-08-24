"""add authentication users

Revision ID: c2a7f6e4b901
Revises: d7b5a45fd0fb
Create Date: 2026-08-24 10:15:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "c2a7f6e4b901"
down_revision: Union[str, Sequence[str], None] = "d7b5a45fd0fb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False
        ),
        sa.Column(
            "username",
            mysql.VARCHAR(length=64, collation="utf8mb4_unicode_ci"),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column(
            "auth_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
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
        sa.CheckConstraint("role IN ('admin','user')", name="ck_users_role"),
        sa.CheckConstraint(
            "status IN ('pending','approved')", name="ck_users_status"
        ),
        sa.CheckConstraint(
            "(role = 'admin' AND username = 'admin' AND status = 'approved') OR "
            "(role = 'user' AND username <> 'admin')",
            name="ck_users_single_admin_identity",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND approved_at IS NULL) OR "
            "(status = 'approved' AND approved_at IS NOT NULL)",
            name="ck_users_approval_timestamp",
        ),
        sa.CheckConstraint("auth_version >= 1", name="ck_users_auth_version"),
        sa.CheckConstraint(
            "failed_login_count >= 0", name="ck_users_failed_login_count"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "idx_users_status_created", "users", ["status", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_users_status_created", table_name="users")
    op.drop_table("users")
