"""Canonical SQLAlchemy schema for B1G Admin Internal System.

MySQL is the production database.  The small SQLite type variants exist only so
unit tests and the one-time migration test fixtures can use an ephemeral local
database without changing the production schema.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from flask_login import UserMixin
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


MYSQL_TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}
ID_TYPE = mysql.BIGINT(unsigned=True).with_variant(Integer, "sqlite")
COUNT_TYPE = mysql.BIGINT(unsigned=True).with_variant(Integer, "sqlite")
LONG_TEXT = mysql.LONGTEXT().with_variant(Text, "sqlite")
CASE_SENSITIVE_SOURCE_TEXT = mysql.VARCHAR(
    512, collation="utf8mb4_bin"
).with_variant(String(512), "sqlite")
USERNAME_TYPE = mysql.VARCHAR(
    64, collation="utf8mb4_unicode_ci"
).with_variant(String(64, collation="NOCASE"), "sqlite")
SATELLITE_DATASET_NAME_TYPE = mysql.VARCHAR(
    160, collation="utf8mb4_unicode_ci"
).with_variant(String(160, collation="NOCASE"), "sqlite")
HUB_DIRECTORY_NAME_TYPE = mysql.VARCHAR(
    160, collation="utf8mb4_unicode_ci"
).with_variant(String(160, collation="NOCASE"), "sqlite")
SATELLITE_DIRECTORY_NAME_TYPE = mysql.VARCHAR(
    512, collation="utf8mb4_unicode_ci"
).with_variant(String(512, collation="NOCASE"), "sqlite")
PASSWORD_HASHER = PasswordHasher()


def hash_password(plaintext: str) -> str:
    return PASSWORD_HASHER.hash(plaintext)


def verify_password_hash(password_hash: str, plaintext: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, plaintext)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


class Base(DeclarativeBase):
    pass


class User(UserMixin, Base):
    """An application operator, separate from event registrants."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin','user','registration')", name="ck_users_role"
        ),
        CheckConstraint(
            "status IN ('pending','approved','blocked')", name="ck_users_status"
        ),
        CheckConstraint(
            "(role = 'admin' AND username = 'admin' AND status = 'approved') OR "
            "(role IN ('user','registration') AND username <> 'admin')",
            name="ck_users_single_admin_identity",
        ),
        CheckConstraint(
            "(status = 'pending' AND approved_at IS NULL) OR "
            "(status IN ('approved','blocked') AND approved_at IS NOT NULL)",
            name="ck_users_approval_timestamp",
        ),
        CheckConstraint("auth_version >= 1", name="ck_users_auth_version"),
        CheckConstraint("failed_login_count >= 0", name="ck_users_failed_login_count"),
        UniqueConstraint("username", name="uq_users_username"),
        Index("idx_users_status_created", "status", "created_at"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(USERNAME_TYPE, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    approved_at: Mapped[Optional[object]] = mapped_column(DateTime)
    approved_by: Mapped[Optional[int]] = mapped_column(
        ID_TYPE, ForeignKey("users.id", ondelete="SET NULL")
    )
    auth_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    locked_until: Mapped[Optional[object]] = mapped_column(DateTime)
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    def set_password(self, plaintext: str) -> None:
        self.password_hash = hash_password(plaintext)

    def check_password(self, plaintext: str) -> bool:
        return verify_password_hash(self.password_hash, plaintext)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin" and self.username == "admin"


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "participant_target IS NULL OR participant_target >= 0",
            name="ck_events_participant_target_nonnegative",
        ),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    event_date: Mapped[Optional[object]] = mapped_column(Date)
    participant_target: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    batches: Mapped[list["ImportBatch"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", passive_deletes=True
    )


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('validating','invalid','validated','processing','active','inactive','failed')",
            name="ck_import_batches_status",
        ),
        CheckConstraint(
            "(status = 'active' AND active_event_id IS NOT NULL "
            "AND active_event_id = event_id) OR "
            "(status <> 'active' AND active_event_id IS NULL)",
            name="ck_import_batches_active_event",
        ),
        UniqueConstraint("event_id", "id", name="uq_import_batches_event_id_id"),
        UniqueConstraint("active_event_id", name="uq_import_batches_active_event"),
        Index("idx_import_batches_event", "event_id", "created_at"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    event_slug: Mapped[Optional[str]] = mapped_column(String(255))
    event_name: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    # A stored generated column based on event_id cannot coexist with MySQL's
    # ON DELETE CASCADE foreign key. The CHECK + nullable UNIQUE pair provides
    # the same invariant while retaining ownership cascades.
    active_event_id: Mapped[Optional[int]] = mapped_column(ID_TYPE)
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    processed_at: Mapped[Optional[object]] = mapped_column(DateTime)
    activated_at: Mapped[Optional[object]] = mapped_column(DateTime)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    event: Mapped[Event] = relationship(back_populates="batches")


class ImportFile(Base):
    __tablename__ = "import_files"
    __table_args__ = (
        CheckConstraint(
            "export_type IN ('tickets','buyers','registrants')",
            name="ck_import_files_export_type",
        ),
        CheckConstraint(
            "status IN ('uploaded','validating','valid','invalid')",
            name="ck_import_files_status",
        ),
        UniqueConstraint("batch_id", "export_type", name="uq_import_files_batch_export"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    export_type: Mapped[str] = mapped_column(String(24), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    staged_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    total_rows: Mapped[int] = mapped_column(COUNT_TYPE, nullable=False, server_default=text("0"))
    valid_rows: Mapped[int] = mapped_column(COUNT_TYPE, nullable=False, server_default=text("0"))
    invalid_rows: Mapped[int] = mapped_column(COUNT_TYPE, nullable=False, server_default=text("0"))
    duplicate_records: Mapped[int] = mapped_column(COUNT_TYPE, nullable=False, server_default=text("0"))
    relationship_issues: Mapped[int] = mapped_column(COUNT_TYPE, nullable=False, server_default=text("0"))
    warning_count: Mapped[int] = mapped_column(COUNT_TYPE, nullable=False, server_default=text("0"))
    detected_type: Mapped[Optional[str]] = mapped_column(String(24))


class ValidationIssue(Base):
    __tablename__ = "validation_issues"
    __table_args__ = (
        CheckConstraint("severity IN ('error','warning')", name="ck_validation_issues_severity"),
        Index("idx_issues_batch_category", "batch_id", "category"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(96), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    source_row: Mapped[Optional[int]] = mapped_column(Integer)
    source_identifier: Mapped[Optional[str]] = mapped_column(String(512))
    message: Mapped[str] = mapped_column(Text, nullable=False)


class Buyer(Base):
    __tablename__ = "buyers"
    __table_args__ = (
        UniqueConstraint("batch_id", "buyer_reference", name="uq_buyers_batch_reference"),
        Index("idx_buyers_batch_status", "batch_id", "payment_status"),
        UniqueConstraint("batch_id", "id", name="uq_buyers_batch_id"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[Optional[str]] = mapped_column(String(255))
    event_slug: Mapped[Optional[str]] = mapped_column(String(255))
    buyer_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    payment_status: Mapped[Optional[str]] = mapped_column(String(96))
    quantity: Mapped[Optional[int]] = mapped_column(Integer)
    source_data_json: Mapped[Optional[str]] = mapped_column(LONG_TEXT)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("batch_id", "ticket_code", name="uq_tickets_batch_code"),
        UniqueConstraint("batch_id", "id", name="uq_tickets_batch_id"),
        Index("idx_tickets_batch_buyer", "batch_id", "buyer_reference"),
        Index("idx_tickets_batch_status", "batch_id", "ticket_status"),
        Index("idx_tickets_batch_checkin", "batch_id", "check_in_at"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[Optional[str]] = mapped_column(String(255))
    event_slug: Mapped[Optional[str]] = mapped_column(String(255))
    ticket_code: Mapped[str] = mapped_column(String(255), nullable=False)
    control_number: Mapped[Optional[str]] = mapped_column(String(255))
    buyer_reference: Mapped[Optional[str]] = mapped_column(String(255))
    ticket_status: Mapped[Optional[str]] = mapped_column(String(96))
    payment_status: Mapped[Optional[str]] = mapped_column(String(96))
    check_in_at: Mapped[Optional[object]] = mapped_column(DateTime)
    source_data_json: Mapped[Optional[str]] = mapped_column(LONG_TEXT)


class Registrant(Base):
    __tablename__ = "registrants"
    __table_args__ = (
        CheckConstraint(
            "affiliation IN ('CCF Main','Local Satellite','International Satellite','Non-CCF','Unknown')",
            name="ck_registrants_affiliation",
        ),
        CheckConstraint(
            "registration_type IN ('participant','volunteer')",
            name="ck_registrants_registration_type",
        ),
        CheckConstraint(
            "first_name_present IN (0,1) AND last_name_present IN (0,1) "
            "AND email_present IN (0,1) AND mobile_present IN (0,1) "
            "AND ticket_matched IN (0,1) AND checked_in IN (0,1)",
            name="ck_registrants_boolean_flags",
        ),
        UniqueConstraint("batch_id", "registration_code", name="uq_registrants_batch_registration"),
        UniqueConstraint("batch_id", "ticket_code", name="uq_registrants_batch_ticket"),
        UniqueConstraint("batch_id", "id", name="uq_registrants_batch_id"),
        Index("idx_registrants_batch_affiliation", "batch_id", "ticket_matched", "affiliation", "checked_in"),
        Index("idx_registrants_batch_type", "batch_id", "ticket_matched", "registration_type"),
        Index("idx_registrants_batch_gender", "batch_id", "gender_raw"),
        Index("idx_registrants_batch_status", "batch_id", "ticket_status"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[Optional[str]] = mapped_column(String(255))
    event_slug: Mapped[Optional[str]] = mapped_column(String(255))
    registration_code: Mapped[str] = mapped_column(String(255), nullable=False)
    ticket_code: Mapped[str] = mapped_column(String(255), nullable=False)
    ticket_name_raw: Mapped[Optional[str]] = mapped_column(Text)
    ticket_status: Mapped[Optional[str]] = mapped_column(String(96))
    first_name: Mapped[Optional[str]] = mapped_column(String(255))
    last_name: Mapped[Optional[str]] = mapped_column(String(255))
    first_name_present: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    last_name_present: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    email_present: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    mobile_present: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    gender_raw: Mapped[Optional[str]] = mapped_column(String(255))
    life_stage_raw: Mapped[Optional[str]] = mapped_column(Text)
    birth_date_raw: Mapped[Optional[str]] = mapped_column(Text)
    birth_month_raw: Mapped[Optional[str]] = mapped_column(Text)
    birth_year_raw: Mapped[Optional[str]] = mapped_column(Text)
    b1g_satellite_hub_raw: Mapped[Optional[str]] = mapped_column(Text)
    b1g_satellite_raw: Mapped[Optional[str]] = mapped_column(Text)
    b1g_satellite_specify_raw: Mapped[Optional[str]] = mapped_column(Text)
    attending_ccf_raw: Mapped[Optional[str]] = mapped_column(Text)
    satellite_scope_raw: Mapped[Optional[str]] = mapped_column(Text)
    local_satellite_raw: Mapped[Optional[str]] = mapped_column(Text)
    international_satellite_raw: Mapped[Optional[str]] = mapped_column(Text)
    affiliation: Mapped[str] = mapped_column(String(32), nullable=False)
    satellite_name: Mapped[Optional[str]] = mapped_column(String(512))
    registration_type: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'participant'"))
    ticket_matched: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    checked_in: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    source_data_json: Mapped[Optional[str]] = mapped_column(LONG_TEXT)

    attestation_verification: Mapped[Optional["AttestationVerification"]] = relationship(
        back_populates="registrant", uselist=False
    )


class AttestationParticipant(Base):
    """Durable participant identity within one Event's registration lifecycle."""

    __tablename__ = "attestation_participants"
    __table_args__ = (
        ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        UniqueConstraint("event_id", "id", name="uq_attestation_participants_event_id"),
        Index("idx_attestation_participants_event", "event_id"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class AttestationParticipantIdentifier(Base):
    """Authoritative imported identifiers attached to a durable participant."""

    __tablename__ = "attestation_participant_identifiers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "identifier_type IN ('source_id','registration_code','ticket_code')",
            name="ck_attestation_participant_identifiers_type",
        ),
        UniqueConstraint(
            "event_id",
            "identifier_type",
            "identifier_value",
            name="uq_attestation_participant_identifiers_value",
        ),
        Index(
            "idx_attestation_participant_identifiers_participant",
            "event_id",
            "attestation_participant_id",
        ),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    attestation_participant_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class AttestationParticipantRegistrant(Base):
    """Maps replaceable imported rows to durable attestation participants."""

    __tablename__ = "attestation_participant_registrants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["batch_id", "registrant_id"],
            ["registrants.batch_id", "registrants.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "batch_id",
            "registrant_id",
            name="uq_attestation_participant_registrants_source",
        ),
        Index(
            "idx_attestation_participant_registrants_participant",
            "event_id",
            "attestation_participant_id",
        ),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    batch_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    registrant_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    attestation_participant_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class AttestationVerification(Base):
    """Application-owned current review state for one durable participant."""

    __tablename__ = "attestation_verifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','verified','invalid')",
            name="ck_attestation_verifications_status",
        ),
        ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "event_id",
            "attestation_participant_id",
            name="uq_attestation_verifications_participant",
        ),
        Index("idx_attestation_verifications_status", "status"),
        Index("idx_attestation_verifications_reviewer", "updated_by_user_id"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    attestation_participant_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    registrant_id: Mapped[Optional[int]] = mapped_column(
        ID_TYPE,
        ForeignKey("registrants.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    registrant: Mapped[Registrant] = relationship(
        back_populates="attestation_verification"
    )
    updated_by: Mapped[Optional[User]] = relationship(
        foreign_keys=[updated_by_user_id]
    )


class RegistrantRemark(Base):
    """Application-owned operational note for one durable participant."""

    __tablename__ = "registrant_remarks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','resolved')",
            name="ck_registrant_remarks_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) OR "
            "(status = 'resolved' AND resolved_at IS NOT NULL)",
            name="ck_registrant_remarks_resolution",
        ),
        ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        Index(
            "idx_registrant_remarks_participant_status_created",
            "event_id",
            "attestation_participant_id",
            "status",
            "created_at",
        ),
        Index("idx_registrant_remarks_creator", "created_by_user_id"),
        Index("idx_registrant_remarks_resolver", "resolved_by_user_id"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    attestation_participant_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    remark: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ID_TYPE, ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(
        ID_TYPE, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    resolved_at: Mapped[Optional[object]] = mapped_column(DateTime)

    created_by: Mapped[Optional[User]] = relationship(
        foreign_keys=[created_by_user_id]
    )
    resolved_by: Mapped[Optional[User]] = relationship(
        foreign_keys=[resolved_by_user_id]
    )


class CuratedRegistrant(Base):
    __tablename__ = "curated_registrants"
    __table_args__ = (
        ForeignKeyConstraint(["event_id", "batch_id"], ["import_batches.event_id", "import_batches.id"], ondelete="CASCADE"),
        CheckConstraint("dedupe_status IN ('complete','incomplete')", name="ck_curated_dedupe_status"),
        CheckConstraint("registration_type IN ('participant','volunteer')", name="ck_curated_registration_type"),
        CheckConstraint("source_registrant_count >= 1", name="ck_curated_source_count"),
        CheckConstraint(
            "dedupe_complete IN (0,1) AND registration_type_conflict IN (0,1) "
            "AND checked_in IN (0,1)",
            name="ck_curated_boolean_flags",
        ),
        UniqueConstraint("batch_id", "dedupe_key", name="uq_curated_batch_dedupe"),
        UniqueConstraint("event_id", "batch_id", "id", name="uq_curated_scope_id"),
        Index("idx_curated_batch_type_checkin", "batch_id", "registration_type", "checked_in"),
        Index("idx_curated_event_batch", "event_id", "batch_id"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    batch_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(255))
    birth_date: Mapped[Optional[str]] = mapped_column(Text)
    birth_month: Mapped[Optional[str]] = mapped_column(String(32))
    birth_year: Mapped[Optional[str]] = mapped_column(String(32))
    gender: Mapped[Optional[str]] = mapped_column(String(64))
    life_stage: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'unknown'"))
    normalized_last_name: Mapped[Optional[str]] = mapped_column(String(255))
    normalized_birth_month: Mapped[Optional[str]] = mapped_column(String(8))
    normalized_birth_year: Mapped[Optional[str]] = mapped_column(String(8))
    normalized_gender: Mapped[Optional[str]] = mapped_column(String(32))
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False)
    dedupe_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    dedupe_status: Mapped[str] = mapped_column(String(24), nullable=False)
    missing_identity_fields: Mapped[Optional[str]] = mapped_column(String(255))
    registration_type: Mapped[str] = mapped_column(String(24), nullable=False)
    registration_type_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    checked_in: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    source_registrant_count: Mapped[int] = mapped_column(COUNT_TYPE, nullable=False, server_default=text("1"))
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class CuratedRegistrantSource(Base):
    __tablename__ = "curated_registrant_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "batch_id", "curated_registrant_id"],
            ["curated_registrants.event_id", "curated_registrants.batch_id", "curated_registrants.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["batch_id", "registrant_id"], ["registrants.batch_id", "registrants.id"], ondelete="CASCADE"),
        UniqueConstraint("curated_registrant_id", "registrant_id", name="uq_curated_sources_pair"),
        UniqueConstraint("batch_id", "registrant_id", name="uq_curated_sources_batch_registrant"),
        Index("idx_curated_sources_curated", "curated_registrant_id"),
        Index("idx_curated_sources_registrant", "registrant_id"),
        Index("idx_curated_sources_batch", "batch_id"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    batch_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    curated_registrant_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    registrant_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class HubGroup(Base):
    """One of the two fixed geographic classifications for satellite hubs."""

    __tablename__ = "hub_groups"
    __table_args__ = (
        CheckConstraint(
            "code IN ('outside_metro_manila','within_metro_manila')",
            name="ck_hub_groups_code",
        ),
        UniqueConstraint("code", name="uq_hub_groups_code"),
        UniqueConstraint("name", name="uq_hub_groups_name"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(HUB_DIRECTORY_NAME_TYPE, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class SatelliteHub(Base):
    """A user-managed hub belonging to one fixed hub group."""

    __tablename__ = "satellite_hubs"
    __table_args__ = (
        UniqueConstraint(
            "hub_group_id", "normalized_name", name="uq_satellite_hubs_group_name"
        ),
        Index("idx_satellite_hubs_group", "hub_group_id", "name"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    hub_group_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("hub_groups.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(HUB_DIRECTORY_NAME_TYPE, nullable=False)
    normalized_name: Mapped[str] = mapped_column(HUB_DIRECTORY_NAME_TYPE, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class SatelliteDirectoryEntry(Base):
    """Canonical, batch-independent identity for an encoded satellite."""

    __tablename__ = "satellite_directory"
    __table_args__ = (
        UniqueConstraint(
            "hub_id", "normalized_name", name="uq_satellite_directory_hub_name"
        ),
        Index("idx_satellite_directory_hub", "hub_id", "name"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    hub_id: Mapped[Optional[int]] = mapped_column(
        ID_TYPE, ForeignKey("satellite_hubs.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(SATELLITE_DIRECTORY_NAME_TYPE, nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        SATELLITE_DIRECTORY_NAME_TYPE, nullable=False
    )
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class EventSatelliteTargetCategory(Base):
    """One fixed Dashboard Satellite target owned by an Event."""

    __tablename__ = "event_satellite_target_categories"
    __table_args__ = (
        CheckConstraint(
            "category_key IN "
            "('outside_metro_manila','within_metro_manila','main')",
            name="ck_event_satellite_target_categories_key",
        ),
        CheckConstraint(
            "participant_target >= 0 AND participant_target <= 1000000000",
            name="ck_event_satellite_target_categories_target",
        ),
        UniqueConstraint(
            "event_id",
            "category_key",
            name="uq_event_satellite_target_categories_event_key",
        ),
        Index(
            "idx_event_satellite_target_categories_event",
            "event_id",
            "category_key",
        ),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    category_key: Mapped[str] = mapped_column(String(32), nullable=False)
    participant_target: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class EventSatelliteTargetSatellite(Base):
    """Canonical Satellite membership in one fixed Event target category."""

    __tablename__ = "event_satellite_target_satellites"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "category_key"],
            [
                "event_satellite_target_categories.event_id",
                "event_satellite_target_categories.category_key",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "event_id",
            "category_key",
            "directory_id",
            name="uq_event_satellite_target_satellites_member",
        ),
        UniqueConstraint(
            "event_id",
            "directory_id",
            name="uq_event_satellite_target_satellites_exclusive",
        ),
        Index(
            "idx_event_satellite_target_satellites_category",
            "event_id",
            "category_key",
        ),
        Index(
            "idx_event_satellite_target_satellites_directory",
            "directory_id",
        ),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    category_key: Mapped[str] = mapped_column(String(32), nullable=False)
    directory_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("satellite_directory.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class EventRegistrantSatellite(Base):
    """Effective canonical Satellite ownership for one durable registrant."""

    __tablename__ = "event_registrant_satellites"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["event_id", "source_batch_id"],
            ["import_batches.event_id", "import_batches.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "assignment_source IN ('manual','automatic')",
            name="ck_event_registrant_satellites_source",
        ),
        CheckConstraint(
            "(assignment_source = 'manual' AND source_batch_id IS NULL) OR "
            "(assignment_source = 'automatic' AND source_batch_id IS NOT NULL)",
            name="ck_event_registrant_satellites_source_batch",
        ),
        UniqueConstraint(
            "event_id",
            "attestation_participant_id",
            name="uq_event_registrant_satellites_participant",
        ),
        Index(
            "idx_event_registrant_satellites_directory",
            "directory_id",
            "event_id",
        ),
        Index(
            "idx_event_registrant_satellites_source_batch",
            "event_id",
            "source_batch_id",
        ),
        Index(
            "idx_event_registrant_satellites_updater",
            "updated_by_user_id",
        ),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    attestation_participant_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    directory_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("satellite_directory.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assignment_source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_batch_id: Mapped[Optional[int]] = mapped_column(ID_TYPE)
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    updated_by: Mapped[Optional[User]] = relationship(
        foreign_keys=[updated_by_user_id]
    )


class EventRegistrantSatelliteAudit(Base):
    """Immutable audit trail for administrator assignment decisions."""

    __tablename__ = "event_registrant_satellite_audits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "attestation_participant_id"],
            ["attestation_participants.event_id", "attestation_participants.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "action IN ('manual','reset')",
            name="ck_event_registrant_satellite_audits_action",
        ),
        Index(
            "idx_event_registrant_satellite_audits_participant",
            "event_id",
            "attestation_participant_id",
            "created_at",
        ),
        Index(
            "idx_event_registrant_satellite_audits_actor",
            "changed_by_user_id",
        ),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    attestation_participant_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_directory_id: Mapped[Optional[int]] = mapped_column(
        ID_TYPE,
        ForeignKey("satellite_directory.id", ondelete="SET NULL"),
    )
    previous_directory_name: Mapped[Optional[str]] = mapped_column(String(512))
    new_directory_id: Mapped[Optional[int]] = mapped_column(
        ID_TYPE,
        ForeignKey("satellite_directory.id", ondelete="SET NULL"),
    )
    new_directory_name: Mapped[Optional[str]] = mapped_column(String(512))
    changed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Satellite(Base):
    __tablename__ = "satellites"
    __table_args__ = (
        ForeignKeyConstraint(["event_id", "batch_id"], ["import_batches.event_id", "import_batches.id"], ondelete="CASCADE"),
        CheckConstraint("affiliation IN ('CCF Main','Local Satellite','International Satellite')", name="ck_satellites_affiliation"),
        CheckConstraint("source_record_count >= 0", name="ck_satellites_source_count"),
        CheckConstraint("affiliation_conflict IN (0,1)", name="ck_satellites_affiliation_conflict"),
        UniqueConstraint("batch_id", "normalized_name", name="uq_satellites_batch_name"),
        UniqueConstraint("event_id", "batch_id", "id", name="uq_satellites_scope_id"),
        Index("idx_satellites_event_batch", "event_id", "batch_id"),
        Index("idx_satellites_directory", "directory_id"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    batch_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    directory_id: Mapped[Optional[int]] = mapped_column(
        ID_TYPE, ForeignKey("satellite_directory.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(512), nullable=False)
    affiliation: Mapped[str] = mapped_column(String(32), nullable=False)
    affiliation_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    source_record_count: Mapped[int] = mapped_column(COUNT_TYPE, nullable=False, server_default=text("0"))
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class SatelliteDataset(Base):
    """Event-owned reporting target over existing normalized satellites."""

    __tablename__ = "satellite_datasets"
    __table_args__ = (
        CheckConstraint(
            "participant_target >= 0",
            name="ck_satellite_datasets_target_nonnegative",
        ),
        UniqueConstraint("event_id", "name", name="uq_satellite_datasets_event_name"),
        UniqueConstraint("event_id", "id", name="uq_satellite_datasets_event_id"),
        Index("idx_satellite_datasets_event", "event_id", "created_at"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(SATELLITE_DATASET_NAME_TYPE, nullable=False)
    participant_target: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class SatelliteSourceVariation(Base):
    __tablename__ = "satellite_source_variations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "batch_id", "satellite_id"],
            ["satellites.event_id", "satellites.batch_id", "satellites.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("affiliation IN ('CCF Main','Local Satellite','International Satellite')", name="ck_variations_affiliation"),
        CheckConstraint("source_record_count >= 0", name="ck_variations_source_count"),
        UniqueConstraint("satellite_id", "source_value", "affiliation", name="uq_variations_source"),
        Index("idx_satellite_variations_satellite", "satellite_id"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    batch_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    satellite_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    # Legacy SQLite uniqueness was case-sensitive; retain exact raw variations
    # such as "B1G Imus" and "B1G imus" while still using utf8mb4.
    source_value: Mapped[str] = mapped_column(CASE_SENSITIVE_SOURCE_TEXT, nullable=False)
    normalized_source_value: Mapped[str] = mapped_column(String(512), nullable=False)
    affiliation: Mapped[str] = mapped_column(String(32), nullable=False)
    source_record_count: Mapped[int] = mapped_column(COUNT_TYPE, nullable=False, server_default=text("0"))
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class CuratedRegistrantSatellite(Base):
    __tablename__ = "curated_registrant_satellites"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "batch_id", "curated_registrant_id"],
            ["curated_registrants.event_id", "curated_registrants.batch_id", "curated_registrants.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["event_id", "batch_id", "satellite_id"],
            ["satellites.event_id", "satellites.batch_id", "satellites.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("curated_registrant_id", "satellite_id", name="uq_curated_satellites_pair"),
        Index("idx_curated_satellites_curated", "curated_registrant_id"),
        Index("idx_curated_satellites_satellite", "satellite_id"),
        Index("idx_curated_satellites_batch", "batch_id"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    batch_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    curated_registrant_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    satellite_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class SatelliteDatasetSatellite(Base):
    """Many-to-many selection of existing Event satellite records."""

    __tablename__ = "satellite_dataset_satellites"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "satellite_dataset_id"],
            ["satellite_datasets.event_id", "satellite_datasets.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["event_id", "satellite_batch_id", "satellite_id"],
            ["satellites.event_id", "satellites.batch_id", "satellites.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "satellite_dataset_id",
            "satellite_id",
            name="uq_satellite_dataset_satellites_pair",
        ),
        Index("idx_satellite_dataset_satellites_dataset", "satellite_dataset_id"),
        Index("idx_satellite_dataset_satellites_satellite", "satellite_id"),
        Index(
            "idx_satellite_dataset_satellites_event_batch",
            "event_id",
            "satellite_batch_id",
        ),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    satellite_dataset_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    satellite_batch_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    satellite_id: Mapped[int] = mapped_column(ID_TYPE, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


TABLES_IN_DEPENDENCY_ORDER = (
    Event,
    ImportBatch,
    ImportFile,
    ValidationIssue,
    Buyer,
    Ticket,
    Registrant,
    CuratedRegistrant,
    CuratedRegistrantSource,
    Satellite,
    SatelliteDataset,
    SatelliteSourceVariation,
    CuratedRegistrantSatellite,
    SatelliteDatasetSatellite,
)
