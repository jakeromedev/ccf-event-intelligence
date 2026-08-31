"""move attestation ownership to stable participants

Revision ID: f3a8c2d9e401
Revises: c8f5d2b0e417
Create Date: 2026-08-31 20:00:00
"""

import logging
import unicodedata
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "f3a8c2d9e401"
down_revision: Union[str, Sequence[str], None] = "c8f5d2b0e417"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOGGER = logging.getLogger("alembic.attestation_participants")
IDENTIFIER_COLUMNS = (
    ("source_id", "source_id"),
    ("registration_code", "registration_code"),
    ("ticket_code", "ticket_code"),
)


def _identifier(value):
    cleaned = " ".join(
        unicodedata.normalize("NFKC", str(value or "")).strip().split()
    )
    return cleaned.casefold() or None


def _create_identity_tables(identifier):
    table_options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }
    op.create_table(
        "attestation_participants",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
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
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "id", name="uq_attestation_participants_event_id"
        ),
        **table_options,
    )
    op.create_index(
        "idx_attestation_participants_event",
        "attestation_participants",
        ["event_id"],
    )
    op.create_table(
        "attestation_participant_identifiers",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("identifier_value", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "identifier_type IN ('source_id','registration_code','ticket_code')",
            name="ck_attestation_participant_identifiers_type",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "identifier_type",
            "identifier_value",
            name="uq_attestation_participant_identifiers_value",
        ),
        **table_options,
    )
    op.create_index(
        "idx_attestation_participant_identifiers_participant",
        "attestation_participant_identifiers",
        ["event_id", "attestation_participant_id"],
    )
    op.create_table(
        "attestation_participant_registrants",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("batch_id", identifier, nullable=False),
        sa.Column("registrant_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "registrant_id"],
            ["registrants.batch_id", "registrants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            "registrant_id",
            name="uq_attestation_participant_registrants_source",
        ),
        **table_options,
    )
    op.create_index(
        "idx_attestation_participant_registrants_participant",
        "attestation_participant_registrants",
        ["event_id", "attestation_participant_id"],
    )


def _cleanup_partial_upgrade(bind):
    """Remove artifacts left by a failed non-transactional MySQL upgrade."""
    tables = set(sa.inspect(bind).get_table_names())
    if "attestation_verifications_v2" in tables:
        op.drop_table("attestation_verifications_v2")
    # Revision c8 never owns these tables, so their presence while this
    # revision is starting can only be residue from an interrupted attempt.
    for table in (
        "attestation_participant_registrants",
        "attestation_participant_identifiers",
        "attestation_participants",
    ):
        if table in tables:
            op.drop_table(table)


def _backfill_participants(bind):
    batches = bind.execute(
        sa.text("SELECT id, event_id FROM import_batches ORDER BY created_at, id")
    ).mappings()
    for batch in batches:
        rows = list(
            bind.execute(
                sa.text(
                    """
                    SELECT r.id, r.source_id, r.registration_code, r.ticket_code,
                           s.curated_registrant_id
                    FROM registrants r
                    LEFT JOIN curated_registrant_sources s
                      ON s.batch_id = r.batch_id AND s.registrant_id = r.id
                    WHERE r.batch_id = :batch_id
                    ORDER BY r.id
                    """
                ),
                {"batch_id": batch["id"]},
            ).mappings()
        )
        groups = defaultdict(list)
        for row in rows:
            group = (
                ("curated", row["curated_registrant_id"])
                if row["curated_registrant_id"] is not None
                else ("registrant", row["id"])
            )
            groups[group].append(row)

        for group_rows in groups.values():
            aliases = {
                (alias_type, normalized)
                for row in group_rows
                for alias_type, column in IDENTIFIER_COLUMNS
                if (normalized := _identifier(row[column])) is not None
            }
            participant_ids = set()
            for alias_type, alias_value in aliases:
                existing = bind.execute(
                    sa.text(
                        """
                        SELECT attestation_participant_id
                        FROM attestation_participant_identifiers
                        WHERE event_id = :event_id
                          AND identifier_type = :identifier_type
                          AND identifier_value = :identifier_value
                        """
                    ),
                    {
                        "event_id": batch["event_id"],
                        "identifier_type": alias_type,
                        "identifier_value": alias_value,
                    },
                ).scalar_one_or_none()
                if existing is not None:
                    participant_ids.add(existing)
            if len(participant_ids) > 1:
                raise RuntimeError(
                    "Attestation identity conflict in import batch {}: source "
                    "identifiers resolve to multiple participants.".format(batch["id"])
                )
            if participant_ids:
                participant_id = next(iter(participant_ids))
            else:
                participant_id = bind.execute(
                    sa.text(
                        "INSERT INTO attestation_participants (event_id) "
                        "VALUES (:event_id)"
                    ),
                    {"event_id": batch["event_id"]},
                ).lastrowid

            for alias_type, alias_value in sorted(aliases):
                existing = bind.execute(
                    sa.text(
                        """
                        SELECT attestation_participant_id
                        FROM attestation_participant_identifiers
                        WHERE event_id = :event_id
                          AND identifier_type = :identifier_type
                          AND identifier_value = :identifier_value
                        """
                    ),
                    {
                        "event_id": batch["event_id"],
                        "identifier_type": alias_type,
                        "identifier_value": alias_value,
                    },
                ).scalar_one_or_none()
                if existing is None:
                    bind.execute(
                        sa.text(
                            """
                            INSERT INTO attestation_participant_identifiers (
                                event_id, attestation_participant_id,
                                identifier_type, identifier_value
                            ) VALUES (
                                :event_id, :participant_id,
                                :identifier_type, :identifier_value
                            )
                            """
                        ),
                        {
                            "event_id": batch["event_id"],
                            "participant_id": participant_id,
                            "identifier_type": alias_type,
                            "identifier_value": alias_value,
                        },
                    )
                elif existing != participant_id:
                    raise RuntimeError(
                        "Attestation identifier ownership changed during backfill."
                    )
            bind.execute(
                sa.text(
                    """
                    INSERT INTO attestation_participant_registrants (
                        event_id, batch_id, registrant_id,
                        attestation_participant_id
                    ) VALUES (
                        :event_id, :batch_id, :registrant_id, :participant_id
                    )
                    """
                ),
                [
                    {
                        "event_id": batch["event_id"],
                        "batch_id": batch["id"],
                        "registrant_id": row["id"],
                        "participant_id": participant_id,
                    }
                    for row in group_rows
                ],
            )


def _create_verification_v2(identifier):
    op.create_table(
        "attestation_verifications_v2",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("event_id", identifier, nullable=False),
        sa.Column("attestation_participant_id", identifier, nullable=False),
        sa.Column("registrant_id", identifier, nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("updated_by_user_id", identifier, nullable=True),
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
        sa.CheckConstraint(
            "status IN ('pending','verified','invalid')",
            name="ck_attestation_verifications_status",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["registrant_id"], ["registrants.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "attestation_participant_id",
            name="uq_attestation_verifications_participant",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def _backfill_verifications(bind):
    rows = list(
        bind.execute(
            sa.text(
                """
                SELECT v.*, m.event_id, m.attestation_participant_id
                FROM attestation_verifications v
                JOIN attestation_participant_registrants m
                  ON m.registrant_id = v.registrant_id
                ORDER BY v.id
                """
            )
        ).mappings()
    )
    old_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM attestation_verifications")
    ).scalar_one()
    if len(rows) != old_count:
        raise RuntimeError(
            "Every existing attestation verification must resolve to a participant."
        )
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["event_id"], row["attestation_participant_id"])].append(row)
    for key, candidates in grouped.items():
        winner = max(
            candidates,
            key=lambda row: (str(row["updated_at"] or ""), row["id"]),
        )
        if len(candidates) > 1:
            LOGGER.warning(
                "Consolidating attestation verifications %s into record %s for "
                "event %s participant %s using latest updated_at then id.",
                [row["id"] for row in candidates],
                winner["id"],
                key[0],
                key[1],
            )
        bind.execute(
            sa.text(
                """
                INSERT INTO attestation_verifications_v2 (
                    id, event_id, attestation_participant_id, registrant_id,
                    status, updated_by_user_id, created_at, updated_at
                ) VALUES (
                    :id, :event_id, :participant_id, :registrant_id,
                    :status, :reviewer_id, :created_at, :updated_at
                )
                """
            ),
            {
                "id": winner["id"],
                "event_id": winner["event_id"],
                "participant_id": winner["attestation_participant_id"],
                "registrant_id": winner["registrant_id"],
                "status": winner["status"],
                "reviewer_id": winner["updated_by_user_id"],
                "created_at": winner["created_at"],
                "updated_at": winner["updated_at"],
            },
        )


def upgrade() -> None:
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    bind = op.get_bind()
    _cleanup_partial_upgrade(bind)
    _create_identity_tables(identifier)
    _backfill_participants(bind)
    if bind.dialect.name == "mysql":
        # MySQL requires CHECK names to be schema-unique, including while both
        # old and replacement tables coexist during this data migration.
        op.drop_constraint(
            "ck_attestation_verifications_status",
            "attestation_verifications",
            type_="check",
        )
    _create_verification_v2(identifier)
    _backfill_verifications(bind)
    op.drop_table("attestation_verifications")
    op.rename_table("attestation_verifications_v2", "attestation_verifications")
    op.create_index(
        "idx_attestation_verifications_status",
        "attestation_verifications",
        ["status"],
    )
    op.create_index(
        "idx_attestation_verifications_reviewer",
        "attestation_verifications",
        ["updated_by_user_id"],
    )


def downgrade() -> None:
    identifier = mysql.BIGINT(unsigned=True).with_variant(sa.Integer(), "sqlite")
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.drop_constraint(
            "ck_attestation_verifications_status",
            "attestation_verifications",
            type_="check",
        )
    op.create_table(
        "attestation_verifications_v1",
        sa.Column("id", identifier, autoincrement=True, nullable=False),
        sa.Column("registrant_id", identifier, nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("updated_by_user_id", identifier, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending','verified','invalid')",
            name="ck_attestation_verifications_status",
        ),
        sa.ForeignKeyConstraint(
            ["registrant_id"], ["registrants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "registrant_id", name="uq_attestation_verifications_registrant"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    missing_provenance = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM attestation_verifications "
            "WHERE registrant_id IS NULL"
        )
    ).scalar_one()
    if missing_provenance:
        raise RuntimeError(
            "Cannot downgrade attestation verification rows without registrant provenance."
        )
    bind.execute(
        sa.text(
            """
            INSERT INTO attestation_verifications_v1 (
                id, registrant_id, status, updated_by_user_id, created_at, updated_at
            )
            SELECT id, registrant_id, status, updated_by_user_id, created_at, updated_at
            FROM attestation_verifications
            """
        )
    )
    op.drop_table("attestation_verifications")
    op.rename_table("attestation_verifications_v1", "attestation_verifications")
    op.create_index(
        "idx_attestation_verifications_status",
        "attestation_verifications",
        ["status"],
    )
    op.create_index(
        "idx_attestation_verifications_reviewer",
        "attestation_verifications",
        ["updated_by_user_id"],
    )
    op.drop_table("attestation_participant_registrants")
    op.drop_table("attestation_participant_identifiers")
    op.drop_table("attestation_participants")
