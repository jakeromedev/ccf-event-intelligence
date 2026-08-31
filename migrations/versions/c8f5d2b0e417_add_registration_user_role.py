"""add registration user role

Revision ID: c8f5d2b0e417
Revises: b7e4c1a9d306
Create Date: 2026-08-30 12:00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c8f5d2b0e417"
down_revision: Union[str, Sequence[str], None] = "b7e4c1a9d306"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ROLE_CONSTRAINT = "role IN ('admin','user','registration')"
IDENTITY_CONSTRAINT = (
    "(role = 'admin' AND username = 'admin' AND status = 'approved') OR "
    "(role IN ('user','registration') AND username <> 'admin')"
)
PREVIOUS_ROLE_CONSTRAINT = "role IN ('admin','user')"
PREVIOUS_IDENTITY_CONSTRAINT = (
    "(role = 'admin' AND username = 'admin' AND status = 'approved') OR "
    "(role = 'user' AND username <> 'admin')"
)


def _replace_constraints(role_constraint: str, identity_constraint: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_users_role", type_="check")
            batch_op.drop_constraint(
                "ck_users_single_admin_identity", type_="check"
            )
            batch_op.create_check_constraint("ck_users_role", role_constraint)
            batch_op.create_check_constraint(
                "ck_users_single_admin_identity", identity_constraint
            )
        return

    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_constraint(
        "ck_users_single_admin_identity", "users", type_="check"
    )
    op.create_check_constraint("ck_users_role", "users", role_constraint)
    op.create_check_constraint(
        "ck_users_single_admin_identity", "users", identity_constraint
    )


def upgrade() -> None:
    _replace_constraints(ROLE_CONSTRAINT, IDENTITY_CONSTRAINT)


def downgrade() -> None:
    # The former schema cannot represent Registration users. Converting those
    # operators to ordinary approved users preserves their accounts while
    # revoking Registration-module access after an application rollback.
    op.execute("UPDATE users SET role = 'user' WHERE role = 'registration'")
    _replace_constraints(PREVIOUS_ROLE_CONSTRAINT, PREVIOUS_IDENTITY_CONSTRAINT)
