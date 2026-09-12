"""Preserve the operator responsible for each registration import."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "e9b4d7a2f603"
down_revision = "d8a3f6c1e902"
branch_labels = None
depends_on = None


def upgrade():
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    with op.batch_alter_table("import_batches") as batch:
        batch.add_column(sa.Column("imported_by_user_id", identifier, nullable=True))
        batch.add_column(sa.Column("imported_by_username", sa.String(64), nullable=True))
        batch.create_foreign_key("fk_import_batches_imported_by", "users",
                                 ["imported_by_user_id"], ["id"], ondelete="SET NULL")


def downgrade():
    with op.batch_alter_table("import_batches") as batch:
        batch.drop_constraint("fk_import_batches_imported_by", type_="foreignkey")
        batch.drop_column("imported_by_username")
        batch.drop_column("imported_by_user_id")
