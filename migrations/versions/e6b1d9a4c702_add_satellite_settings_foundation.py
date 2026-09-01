"""add satellite settings foundation

Revision ID: e6b1d9a4c702
Revises: d5f8a1c2b304
Create Date: 2026-09-01 18:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "e6b1d9a4c702"
down_revision: Union[str, Sequence[str], None] = "d5f8a1c2b304"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _identifier():
    return mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")


def _directory_name(length):
    return mysql.VARCHAR(
        length=length, collation="utf8mb4_unicode_ci"
    ).with_variant(sa.String(length=length, collation="NOCASE"), "sqlite")


def upgrade() -> None:
    identifier = _identifier()
    table_options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }
    op.create_table(
        "hub_groups",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", _directory_name(160), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "code IN ('outside_metro_manila','within_metro_manila')",
            name="ck_hub_groups_code",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_hub_groups_code"),
        sa.UniqueConstraint("name", name="uq_hub_groups_name"),
        **table_options,
    )
    hub_groups = sa.table(
        "hub_groups",
        sa.column("id", identifier),
        sa.column("code", sa.String(length=32)),
        sa.column("name", _directory_name(160)),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(
        hub_groups,
        [
            {
                "id": 1,
                "code": "within_metro_manila",
                "name": "Within Metro Manila Hubs",
                "sort_order": 1,
            },
            {
                "id": 2,
                "code": "outside_metro_manila",
                "name": "Outside Metro Manila Hubs",
                "sort_order": 2,
            },
        ],
    )

    op.create_table(
        "satellite_hubs",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("hub_group_id", identifier, nullable=False),
        sa.Column("name", _directory_name(160), nullable=False),
        sa.Column("normalized_name", _directory_name(160), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["hub_group_id"], ["hub_groups.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "hub_group_id", "normalized_name", name="uq_satellite_hubs_group_name"
        ),
        **table_options,
    )
    op.create_index(
        "idx_satellite_hubs_group",
        "satellite_hubs",
        ["hub_group_id", "name"],
        unique=False,
    )

    op.create_table(
        "satellite_directory",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("hub_id", identifier, nullable=True),
        sa.Column("name", _directory_name(512), nullable=False),
        sa.Column("normalized_name", _directory_name(512), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["hub_id"], ["satellite_hubs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_name", name="uq_satellite_directory_name"
        ),
        **table_options,
    )
    op.create_index(
        "idx_satellite_directory_hub",
        "satellite_directory",
        ["hub_id", "name"],
        unique=False,
    )

    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "auto"
    with op.batch_alter_table("satellites", recreate=recreate) as batch_op:
        batch_op.add_column(sa.Column("directory_id", identifier, nullable=True))
        batch_op.create_index(
            "idx_satellites_directory", ["directory_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_satellites_directory",
            "satellite_directory",
            ["directory_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        """
        INSERT INTO satellite_directory (name, normalized_name)
        SELECT MIN(name), normalized_name
        FROM satellites
        GROUP BY normalized_name
        """
    )
    op.execute(
        """
        UPDATE satellites
        SET directory_id = (
            SELECT directory.id
            FROM satellite_directory directory
            WHERE directory.normalized_name = satellites.normalized_name
        )
        """
    )


def downgrade() -> None:
    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "auto"
    with op.batch_alter_table("satellites", recreate=recreate) as batch_op:
        batch_op.drop_constraint("fk_satellites_directory", type_="foreignkey")
        batch_op.drop_index("idx_satellites_directory")
        batch_op.drop_column("directory_id")
    op.drop_index("idx_satellite_directory_hub", table_name="satellite_directory")
    op.drop_table("satellite_directory")
    op.drop_index("idx_satellite_hubs_group", table_name="satellite_hubs")
    op.drop_table("satellite_hubs")
    op.drop_table("hub_groups")
