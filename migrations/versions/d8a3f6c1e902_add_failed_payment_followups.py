"""Add durable payment follow-ups and remarks."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "d8a3f6c1e902"
down_revision = "c6e2a9b4d801"
branch_labels = None
depends_on = None


def upgrade():
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "failed_payment_followups",
        sa.Column("id", identifier, primary_key=True, autoincrement=True),
        sa.Column("event_id", identifier, sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("remark", sa.Text()),
        sa.Column("created_by_user_id", identifier, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("kind IN ('outreach', 'remark')", name="ck_failed_payment_followup_kind"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_failed_payment_followup_person", "failed_payment_followups", ["event_id", "person_key"])


def downgrade():
    op.drop_table("failed_payment_followups")
