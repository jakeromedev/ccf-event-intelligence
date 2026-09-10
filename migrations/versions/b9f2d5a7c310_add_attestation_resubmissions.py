"""Add durable attestation resubmissions and system-owned Re-verify status."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "b9f2d5a7c310"
down_revision = "a8e1c4d9f205"
branch_labels = None
depends_on = None


def upgrade():
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    with op.batch_alter_table("attestation_verifications") as batch:
        batch.drop_constraint("ck_attestation_verifications_status", type_="check")
        batch.create_check_constraint(
            "ck_attestation_verifications_status",
            "status IN ('pending','verified','invalid','to_verify')",
        )
        batch.add_column(sa.Column("form_url", sa.Text(), nullable=True))
    op.create_table(
        "attestation_resubmission_imports",
        sa.Column("id", identifier, primary_key=True, autoincrement=True),
        sa.Column("event_id", identifier, sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("report_json", mysql.LONGTEXT().with_variant(sa.Text(), "sqlite"), nullable=False),
        sa.Column("created_by_user_id", identifier, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "attestation_resubmissions",
        sa.Column("id", identifier, primary_key=True, autoincrement=True),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column("import_id", identifier, sa.ForeignKey("attestation_resubmission_imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("link_hash", sa.String(64), nullable=False),
        sa.Column("form_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("event_id", "attestation_participant_id", "link_hash",
                            name="uq_attestation_resubmission_link"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade():
    op.execute("UPDATE attestation_verifications SET status = 'pending' WHERE status = 'to_verify'")
    op.drop_table("attestation_resubmissions")
    op.drop_table("attestation_resubmission_imports")
    with op.batch_alter_table("attestation_verifications") as batch:
        batch.drop_column("form_url")
        batch.drop_constraint("ck_attestation_verifications_status", type_="check")
        batch.create_check_constraint(
            "ck_attestation_verifications_status", "status IN ('pending','verified','invalid')",
        )
