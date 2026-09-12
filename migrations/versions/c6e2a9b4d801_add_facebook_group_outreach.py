"""Track confirmed Facebook Group outreach attempts."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "c6e2a9b4d801"
down_revision = "b9f2d5a7c310"
branch_labels = None
depends_on = None


def upgrade():
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    op.add_column(
        "registrant_facebook_group_memberships",
        sa.Column("reached_out", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.create_table(
        "registrant_facebook_group_outreach",
        sa.Column("id", identifier, primary_key=True, autoincrement=True),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column("created_by_user_id", identifier, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_fb_outreach_participant", "registrant_facebook_group_outreach",
                    ["event_id", "attestation_participant_id"])


def downgrade():
    op.drop_table("registrant_facebook_group_outreach")
    op.drop_column("registrant_facebook_group_memberships", "reached_out")
