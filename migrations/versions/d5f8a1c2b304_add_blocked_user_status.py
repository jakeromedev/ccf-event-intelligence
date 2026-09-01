"""add blocked user status

Revision ID: d5f8a1c2b304
Revises: a4c9e2f7b610
Create Date: 2026-09-01 17:45:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d5f8a1c2b304"
down_revision: Union[str, Sequence[str], None] = "a4c9e2f7b610"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATUS_CONSTRAINT = "status IN ('pending','approved','blocked')"
APPROVAL_CONSTRAINT = (
    "(status = 'pending' AND approved_at IS NULL) OR "
    "(status IN ('approved','blocked') AND approved_at IS NOT NULL)"
)
PREVIOUS_STATUS_CONSTRAINT = "status IN ('pending','approved')"
PREVIOUS_APPROVAL_CONSTRAINT = (
    "(status = 'pending' AND approved_at IS NULL) OR "
    "(status = 'approved' AND approved_at IS NOT NULL)"
)


def _replace_constraints(status_constraint: str, approval_constraint: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_users_status", type_="check")
            batch_op.drop_constraint(
                "ck_users_approval_timestamp", type_="check"
            )
            batch_op.create_check_constraint("ck_users_status", status_constraint)
            batch_op.create_check_constraint(
                "ck_users_approval_timestamp", approval_constraint
            )
        return

    op.drop_constraint("ck_users_status", "users", type_="check")
    op.drop_constraint("ck_users_approval_timestamp", "users", type_="check")
    op.create_check_constraint("ck_users_status", "users", status_constraint)
    op.create_check_constraint(
        "ck_users_approval_timestamp", "users", approval_constraint
    )


def upgrade() -> None:
    _replace_constraints(STATUS_CONSTRAINT, APPROVAL_CONSTRAINT)


def downgrade() -> None:
    op.execute("UPDATE users SET status = 'approved' WHERE status = 'blocked'")
    _replace_constraints(PREVIOUS_STATUS_CONSTRAINT, PREVIOUS_APPROVAL_CONSTRAINT)
