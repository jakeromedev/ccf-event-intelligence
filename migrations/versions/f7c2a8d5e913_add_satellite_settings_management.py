"""add satellite settings management

Revision ID: f7c2a8d5e913
Revises: e6b1d9a4c702
Create Date: 2026-09-01 18:40:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f7c2a8d5e913"
down_revision: Union[str, Sequence[str], None] = "e6b1d9a4c702"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _recreate_mode():
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    with op.batch_alter_table(
        "satellite_directory", recreate=_recreate_mode()
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_satellite_directory_name", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_satellite_directory_hub_name", ["hub_id", "normalized_name"]
        )


def downgrade() -> None:
    # Phase 1 allowed only one canonical entry per normalized name. Consolidate
    # any Phase 2 same-name entries and preserve imported satellite links before
    # restoring that stricter constraint.
    op.execute(
        """
        UPDATE satellites
        SET directory_id = (
            SELECT MIN(candidate.id)
            FROM satellite_directory candidate
            JOIN satellite_directory current_entry
              ON current_entry.normalized_name = candidate.normalized_name
            WHERE current_entry.id = satellites.directory_id
        )
        WHERE directory_id IS NOT NULL
        """
    )
    op.execute(
        """
        DELETE FROM satellite_directory
        WHERE id NOT IN (
            SELECT retained.id FROM (
                SELECT MIN(id) id
                FROM satellite_directory
                GROUP BY normalized_name
            ) retained
        )
        """
    )
    with op.batch_alter_table(
        "satellite_directory", recreate=_recreate_mode()
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_satellite_directory_hub_name", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_satellite_directory_name", ["normalized_name"]
        )
