"""Add durable per-trip transportation overrides and update history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "f2c5e8a1b704"
down_revision = "e9b4d7a2f603"
branch_labels = None
depends_on = None


def upgrade():
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    options = dict(mysql_engine="InnoDB", mysql_charset="utf8mb4",
                   mysql_collate="utf8mb4_unicode_ci")
    op.create_table(
        "participant_transportation",
        sa.Column("id", identifier, primary_key=True, autoincrement=True),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(32), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", identifier, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["event_id", "attestation_participant_id"],
                                ["attestation_participants.event_id", "attestation_participants.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("event_id", "attestation_participant_id", "direction",
                            name="uq_transportation_participant_direction"),
        sa.CheckConstraint("direction IN ('to_mmrc','from_mmrc')", name="ck_transportation_direction"),
        sa.CheckConstraint("mode IS NULL OR mode IN ('bus','carpool','public_transportation','other','unreported')",
                           name="ck_transportation_mode"),
        sa.CheckConstraint("revision > 0", name="ck_transportation_revision"),
        **options,
    )
    op.create_table(
        "participant_transportation_history",
        sa.Column("id", identifier, primary_key=True, autoincrement=True),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_value_json", sa.Text(), nullable=False),
        sa.Column("new_value_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=True),
        sa.Column("changed_by_user_id", identifier, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("changed_by_username", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["event_id", "attestation_participant_id"],
                                ["attestation_participants.event_id", "attestation_participants.id"],
                                ondelete="CASCADE"),
        sa.CheckConstraint("direction IN ('to_mmrc','from_mmrc')", name="ck_transport_history_direction"),
        sa.CheckConstraint("action IN ('set','reset')", name="ck_transport_history_action"),
        sa.CheckConstraint("revision > 0", name="ck_transport_history_revision"),
        sa.UniqueConstraint("event_id", "attestation_participant_id", "direction", "revision",
                            name="uq_transport_history_revision"),
        **options,
    )
    op.create_index("idx_transport_history_person", "participant_transportation_history",
                    ["event_id", "attestation_participant_id", "id"])


def downgrade():
    op.drop_table("participant_transportation_history")
    op.drop_table("participant_transportation")
