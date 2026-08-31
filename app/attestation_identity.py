"""Durable, Event-scoped participant identity for attestation ownership."""

import unicodedata
from collections import defaultdict


IDENTIFIER_COLUMNS = (
    ("source_id", "source_id"),
    ("registration_code", "registration_code"),
    ("ticket_code", "ticket_code"),
)


class AttestationIdentityConflict(RuntimeError):
    """Raised when source identifiers would merge distinct participants."""


def _normalize_identifier(value):
    cleaned = " ".join(
        unicodedata.normalize("NFKC", str(value or "")).strip().split()
    )
    return cleaned.casefold() or None


def _identifiers(row):
    return {
        (identifier_type, normalized)
        for identifier_type, column in IDENTIFIER_COLUMNS
        if (normalized := _normalize_identifier(row[column])) is not None
    }


def reconcile_attestation_participants(db, event_id, batch_id):
    """Map every imported registrant to one durable participant.

    Existing authoritative source identifiers are reused across import runs.
    Curation groups are used only to bind multiple rows in the same run; the
    mutable demographic curation key is never stored as durable identity.
    """
    rows = db.execute(
        """
        SELECT record.id, record.source_id, record.registration_code,
               record.ticket_code, source.curated_registrant_id
        FROM registrants record
        JOIN import_batches batch ON batch.id = record.batch_id
        LEFT JOIN curated_registrant_sources source
          ON source.batch_id = record.batch_id
         AND source.registrant_id = record.id
        WHERE batch.event_id = ? AND record.batch_id = ?
        ORDER BY record.id
        """,
        (event_id, batch_id),
    ).fetchall()

    groups = defaultdict(list)
    for row in rows:
        group_key = (
            "curated",
            row["curated_registrant_id"],
        ) if row["curated_registrant_id"] is not None else ("registrant", row["id"])
        groups[group_key].append(row)

    mapped = 0
    for group_rows in groups.values():
        identifiers = set().union(*(_identifiers(row) for row in group_rows))
        participant_ids = set()
        for identifier_type, identifier_value in identifiers:
            existing = db.execute(
                """
                SELECT attestation_participant_id
                FROM attestation_participant_identifiers
                WHERE event_id = ? AND identifier_type = ?
                  AND identifier_value = ?
                """,
                (event_id, identifier_type, identifier_value),
            ).fetchone()
            if existing:
                participant_ids.add(existing["attestation_participant_id"])
        if len(participant_ids) > 1:
            raise AttestationIdentityConflict(
                "Registrant identifiers resolve to multiple attestation participants."
            )
        if participant_ids:
            participant_id = next(iter(participant_ids))
        else:
            participant_id = db.execute(
                "INSERT INTO attestation_participants (event_id) VALUES (?)",
                (event_id,),
            ).lastrowid

        for identifier_type, identifier_value in sorted(identifiers):
            existing = db.execute(
                """
                SELECT attestation_participant_id
                FROM attestation_participant_identifiers
                WHERE event_id = ? AND identifier_type = ?
                  AND identifier_value = ?
                """,
                (event_id, identifier_type, identifier_value),
            ).fetchone()
            if existing is None:
                db.execute(
                    """
                    INSERT INTO attestation_participant_identifiers (
                        event_id, attestation_participant_id, identifier_type,
                        identifier_value
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (event_id, participant_id, identifier_type, identifier_value),
                )
            elif existing["attestation_participant_id"] != participant_id:
                raise AttestationIdentityConflict(
                    "An attestation identifier is already owned by another participant."
                )

        for row in group_rows:
            existing_mapping = db.execute(
                """
                SELECT attestation_participant_id
                FROM attestation_participant_registrants
                WHERE batch_id = ? AND registrant_id = ?
                """,
                (batch_id, row["id"]),
            ).fetchone()
            if existing_mapping is None:
                db.execute(
                    """
                    INSERT INTO attestation_participant_registrants (
                        event_id, batch_id, registrant_id,
                        attestation_participant_id
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (event_id, batch_id, row["id"], participant_id),
                )
            elif existing_mapping["attestation_participant_id"] != participant_id:
                raise AttestationIdentityConflict(
                    "A registrant is already mapped to another attestation participant."
                )
            mapped += 1
    return mapped


def resolve_attestation_participant(db, event_id, batch_id, registrant_id):
    mapping = db.execute(
        """
        SELECT attestation_participant_id
        FROM attestation_participant_registrants
        WHERE event_id = ? AND batch_id = ? AND registrant_id = ?
        """,
        (event_id, batch_id, registrant_id),
    ).fetchone()
    if mapping is None:
        reconcile_attestation_participants(db, event_id, batch_id)
        mapping = db.execute(
            """
            SELECT attestation_participant_id
            FROM attestation_participant_registrants
            WHERE event_id = ? AND batch_id = ? AND registrant_id = ?
            """,
            (event_id, batch_id, registrant_id),
        ).fetchone()
    return mapping["attestation_participant_id"] if mapping else None


__all__ = [
    "AttestationIdentityConflict",
    "reconcile_attestation_participants",
    "resolve_attestation_participant",
]
