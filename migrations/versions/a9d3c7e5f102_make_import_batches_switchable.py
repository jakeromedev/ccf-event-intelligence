"""make processed import batches switchable

Revision ID: a9d3c7e5f102
Revises: e8c6f1a2b3d4
Create Date: 2026-08-25 23:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9d3c7e5f102"
down_revision: Union[str, Sequence[str], None] = "e8c6f1a2b3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPGRADE_STATUS_CHECK = (
    "status IN ('validating','invalid','validated','processing','active','inactive','failed')"
)
DOWNGRADE_STATUS_CHECK = (
    "status IN ('validating','invalid','validated','processing','active','failed','superseded')"
)


def _drop_status_check() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("import_batches", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_import_batches_status", type_="check")
    else:
        op.drop_constraint(
            "ck_import_batches_status", "import_batches", type_="check"
        )


def _create_status_check(expression: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("import_batches", recreate="always") as batch_op:
            batch_op.create_check_constraint(
                "ck_import_batches_status", expression
            )
    else:
        op.create_check_constraint(
            "ck_import_batches_status", "import_batches", expression
        )


def upgrade() -> None:
    _drop_status_check()
    op.execute(
        sa.text(
            "UPDATE import_batches SET status = 'inactive' "
            "WHERE status = 'superseded'"
        )
    )
    _create_status_check(UPGRADE_STATUS_CHECK)


def downgrade() -> None:
    _drop_status_check()
    op.execute(
        sa.text(
            "UPDATE import_batches SET status = 'superseded' "
            "WHERE status = 'inactive'"
        )
    )
    _create_status_check(DOWNGRADE_STATUS_CHECK)
