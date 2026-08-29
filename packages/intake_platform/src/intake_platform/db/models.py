"""INT-030 — core tables (files/06 data model; files/10 §2 data-at-rest).

Design decisions the columns encode:
- **patients is pseudonym-only** (invariant 14): the ``pseudonym`` column is
  the Tokenizer's output (``kid.hmac-hex``, intake_platform.tokenization); no
  name/TCKN/phone/address column exists in any app table — the raw identifier
  lives only in identity_vault, readable by the tokenization role alone.
- **envelope columns**: notes.payload always, and slots.value when
  ``sensitivity = sensitive``, carry EncryptedField JSON
  (intake_platform.db.envelope_json over intake_platform.envelope) — never
  plaintext clinical narrative (invariant 14, field-level envelope encryption).
- **documents are references**: object-store ref + sha256 provenance; the
  bytes never sit inline (tests pin the absence of any LargeBinary column).
- **events are append-only** rows for the generic event streams; the
  hash-chained audit is a separate table (audit_store.AuditChainRow) so the
  two write paths can hold different grants.
- **every column carries the invariant-18 inventory annotation** via
  ``info=inv(category, purpose, basis, retention, recipients)``.

RLS, FORCE RLS, roles and grants are DDL, not model metadata: they live in
migrations/versions/0001_int030_core_schema.py and are pinned statically by
tests/data/test_schema_shape.py and live by tests/data/test_rls.py.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import BigInteger, Uuid

from intake_platform.db.inventory import (
    BASIS_CONTRACT,
    BASIS_HEALTH_CONSENT,
    BASIS_LEGAL_OBLIGATION,
    CAT_CONSENT,
    CAT_HEALTH,
    CAT_OPERATIONAL,
    CAT_PSEUDONYM,
    REC_AUDITOR,
    REC_CLINICIAN,
    REC_INTERNAL,
    REC_PATIENT_CLINICIAN,
    RET_CONSENT_AUDIT,
    RET_DSAR,
    RET_EVENTS,
    RET_RECORD,
    RET_SHARE,
    RET_TENANT,
    inv,
)

__all__ = [
    "Base",
    "Consent",
    "Document",
    "DsarKind",
    "DsarRectification",
    "DsarRequest",
    "DsarStatus",
    "Event",
    "IntakeSession",
    "KvkkRole",
    "Note",
    "Patient",
    "SessionStatus",
    "Share",
    "Slot",
    "SlotSensitivity",
    "Tenant",
]

_NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING)


class KvkkRole(enum.StrEnum):
    """files/06 §1: consumer app → INTAKE is controller; hospital deployment →
    the hospital is controller and INTAKE is processor. Every table, screen
    and export knows which role applies via this tenant flag (INT-030)."""

    CONTROLLER = "controller"
    PROCESSOR = "processor"


class SessionStatus(enum.StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DsarKind(enum.StrEnum):
    """The KVKK m.11 rights INT-037 serves. Closed by construction: a request
    the tracker cannot name is a request nobody is accountable for."""

    EXPORT = "export"
    DELETE = "delete"
    RECTIFY = "rectify"


class DsarStatus(enum.StrEnum):
    """``received`` — the m.13 clock is running; ``scheduled`` — an erasure
    inside its files/06 §3 grace; ``completed`` — answered or executed;
    ``cancelled`` — the subject withdrew the erasure inside the grace."""

    RECEIVED = "received"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SlotSensitivity(enum.StrEnum):
    """Decides what slots.value carries: ``plain`` → the JSON value itself;
    ``sensitive`` → an EncryptedField envelope (envelope_json)."""

    PLAIN = "plain"
    SENSITIVE = "sensitive"


def _uuid_pk(purpose: str, retention: str) -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        info=inv(CAT_OPERATIONAL, purpose, BASIS_CONTRACT, retention, REC_INTERNAL),
    )


def _tenant_fk(retention: str) -> Mapped[uuid.UUID]:
    return mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "RLS boundary: the tenant this row belongs to (policies compare it "
            "to the app.tenant_id GUC)",
            BASIS_CONTRACT,
            retention,
            REC_INTERNAL,
        ),
    )


def _created_at(retention: str) -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        info=inv(
            CAT_OPERATIONAL,
            "row creation instant (retention clocks start here)",
            BASIS_CONTRACT,
            retention,
            REC_INTERNAL,
        ),
    )


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = _uuid_pk("tenant identity key", RET_TENANT)
    display_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "organisation display name (an institution, never a person)",
            BASIS_CONTRACT,
            RET_TENANT,
            REC_INTERNAL,
        ),
    )
    kvkk_role: Mapped[KvkkRole] = mapped_column(
        Enum(
            KvkkRole,
            name="kvkk_role",
            native_enum=False,
            length=16,
            values_callable=lambda cls: [member.value for member in cls],
        ),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "controller/processor flag per deployment (files/06 §1)",
            BASIS_LEGAL_OBLIGATION,
            RET_TENANT,
            REC_AUDITOR,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_TENANT)


class Patient(Base):
    """Pseudonymised: the row proves a patient exists in a tenant and nothing
    more. Identity resolution goes through the tokenization service."""

    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("tenant_id", "pseudonym"),)

    id: Mapped[uuid.UUID] = _uuid_pk("pseudonymised patient row key", RET_RECORD)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_RECORD)
    pseudonym: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_PSEUDONYM,
            "keyed HMAC pseudonym from the Tokenizer (kid.hex); the raw "
            "identifier exists only in identity_vault",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_RECORD)


class IntakeSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk("intake session key", RET_RECORD)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_RECORD)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the pseudonymised patient this session belongs to",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    protocol_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "which protocol pack ran (reveals the presenting-complaint area)",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_CLINICIAN,
        ),
    )
    protocol_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "exact pack version for reproducibility and re-triage sweeps",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(
            SessionStatus,
            name="session_status",
            native_enum=False,
            length=16,
            values_callable=lambda cls: [member.value for member in cls],
        ),
        nullable=False,
        default=SessionStatus.CREATED,
        info=inv(
            CAT_HEALTH,
            "session lifecycle state (a completed intake is a health fact)",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_CLINICIAN,
        ),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "when the voice/typed intake actually began",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "when the intake finished (SLO + retention inputs)",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_RECORD)


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (UniqueConstraint("session_id", "slot_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk("protocol slot value key", RET_RECORD)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_RECORD)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "owning intake session",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    slot_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "protocol slot name (names the clinical question asked)",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_CLINICIAN,
        ),
    )
    sensitivity: Mapped[SlotSensitivity] = mapped_column(
        Enum(
            SlotSensitivity,
            name="slot_sensitivity",
            native_enum=False,
            length=16,
            values_callable=lambda cls: [member.value for member in cls],
        ),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "decides the value representation: plain JSON or an EncryptedField "
            "envelope for sensitive slot classes",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "the slot value; sensitive classes carry EncryptedField JSON "
            "(envelope_json), never plaintext",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_CLINICIAN,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_RECORD)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = _uuid_pk("pre-visit note key", RET_RECORD)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_RECORD)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the intake session this note was composed from",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the pseudonymised patient the note belongs to",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "clinician-ready pre-visit note as EncryptedField JSON "
            "(field-level envelope encryption; never plaintext at rest)",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_PATIENT_CLINICIAN,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_RECORD)


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = _uuid_pk("consent grant key", RET_CONSENT_AUDIT)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_CONSENT_AUDIT)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_CONSENT,
            "the pseudonymised patient who granted the scope",
            BASIS_LEGAL_OBLIGATION,
            RET_CONSENT_AUDIT,
            REC_AUDITOR,
        ),
    )
    scope: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_CONSENT,
            "consent scope id (every clinical read/share checks one — invariant 4)",
            BASIS_LEGAL_OBLIGATION,
            RET_CONSENT_AUDIT,
            REC_AUDITOR,
        ),
    )
    version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_CONSENT,
            "version of the consent text presented (hash-bound to docs/legal)",
            BASIS_LEGAL_OBLIGATION,
            RET_CONSENT_AUDIT,
            REC_AUDITOR,
        ),
    )
    text_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        info=inv(
            CAT_CONSENT,
            "SHA-256 of the exact docs/legal consent text shown (invariant 18; "
            "files/06 §2 text_hash); NULL only on pre-INT-038 dev-tier seed rows, "
            "which the guard treats as stale the moment a canonical text exists",
            BASIS_LEGAL_OBLIGATION,
            RET_CONSENT_AUDIT,
            REC_AUDITOR,
        ),
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info=inv(
            CAT_CONSENT,
            "grant instant (proof of when açık rıza was given)",
            BASIS_LEGAL_OBLIGATION,
            RET_CONSENT_AUDIT,
            REC_AUDITOR,
        ),
    )
    channel: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        info=inv(
            CAT_CONSENT,
            "collection surface — app|kiosk|clinician|admin|web (files/06 §1 "
            "KVKK-10: layered aydınlatma per channel; files/06 §2 channel); "
            "NULL only on pre-INT-038 dev-tier seed rows",
            BASIS_LEGAL_OBLIGATION,
            RET_CONSENT_AUDIT,
            REC_AUDITOR,
        ),
    )
    evidence_ref: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        info=inv(
            CAT_CONSENT,
            "id of the acceptance-evidence record (files/06 §2 evidence) — an "
            "id, never the evidence itself (invariant 6); NULL only on "
            "pre-INT-038 dev-tier seed rows",
            BASIS_LEGAL_OBLIGATION,
            RET_CONSENT_AUDIT,
            REC_AUDITOR,
        ),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        info=inv(
            CAT_CONSENT,
            "withdrawal instant; NULL while the grant stands",
            BASIS_LEGAL_OBLIGATION,
            RET_CONSENT_AUDIT,
            REC_AUDITOR,
        ),
    )


class Share(Base):
    __tablename__ = "shares"

    id: Mapped[uuid.UUID] = _uuid_pk("note share key", RET_SHARE)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_SHARE)
    note_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notes.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_CONSENT,
            "the note this share grants access to",
            BASIS_HEALTH_CONSENT,
            RET_SHARE,
            REC_CLINICIAN,
        ),
    )
    scope_sections: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_CONSENT,
            "which note sections the share exposes (section ids only)",
            BASIS_HEALTH_CONSENT,
            RET_SHARE,
            REC_CLINICIAN,
        ),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info=inv(
            CAT_CONSENT,
            "hard expiry of the share token (≤ 72 h default, 06 §3)",
            BASIS_HEALTH_CONSENT,
            RET_SHARE,
            REC_INTERNAL,
        ),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        info=inv(
            CAT_CONSENT,
            "instant the patient revoked the share; NULL while live",
            BASIS_HEALTH_CONSENT,
            RET_SHARE,
            REC_INTERNAL,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_SHARE)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk("ingested document key", RET_RECORD)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_RECORD)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the pseudonymised patient the document belongs to",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "intake session the upload arrived in, when it did",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    object_ref: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "object-store reference (bucket/key); document bytes never sit inline in a row",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_CLINICIAN,
        ),
    )
    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "content hash: provenance and tamper evidence for the stored object",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    media_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "sniffed media type (upload pipeline, files/10 §4)",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "source trail (uploader ref, capture channel, scan verdicts) — id-shaped values only",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_RECORD)


class DsarRequest(Base):
    """One data-subject request and its KVKK m.13 clock (INT-037).

    The SLA queue is read by operations staff, so this row carries ids, a
    closed kind/status and timestamps — and nothing else (invariant 6). What
    the subject asked to correct lives, encrypted, on ``dsar_rectifications``;
    what they asked to receive is assembled at read time and never stored.
    """

    __tablename__ = "dsar_requests"
    __table_args__ = (Index("ix_dsar_requests_tenant_status", "tenant_id", "status"),)

    id: Mapped[uuid.UUID] = _uuid_pk("data-subject request key", RET_DSAR)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_DSAR)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the pseudonymised data subject exercising the right",
            BASIS_LEGAL_OBLIGATION,
            RET_DSAR,
            REC_AUDITOR,
        ),
    )
    kind: Mapped[DsarKind] = mapped_column(
        Enum(
            DsarKind,
            name="dsar_kind",
            native_enum=False,
            length=16,
            values_callable=lambda cls: [member.value for member in cls],
        ),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "which KVKK m.11 right was exercised (export|delete|rectify)",
            BASIS_LEGAL_OBLIGATION,
            RET_DSAR,
            REC_AUDITOR,
        ),
    )
    status: Mapped[DsarStatus] = mapped_column(
        Enum(
            DsarStatus,
            name="dsar_status",
            native_enum=False,
            length=16,
            values_callable=lambda cls: [member.value for member in cls],
        ),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "lifecycle state of the request (received|scheduled|completed|cancelled)",
            BASIS_LEGAL_OBLIGATION,
            RET_DSAR,
            REC_AUDITOR,
        ),
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "when the request arrived — the instant the KVKK m.13 clock starts",
            BASIS_LEGAL_OBLIGATION,
            RET_DSAR,
            REC_AUDITOR,
        ),
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "statutory response deadline: received_at + 30 days (06 §1 KVKK-11/13)",
            BASIS_LEGAL_OBLIGATION,
            RET_DSAR,
            REC_AUDITOR,
        ),
    )
    grace_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "erasure only: end of the 30-day deletion grace, after which the "
            "crypto-shred executes (06 §3); NULL for every other kind",
            BASIS_LEGAL_OBLIGATION,
            RET_DSAR,
            REC_AUDITOR,
        ),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "when the request was answered or executed; NULL while the clock runs",
            BASIS_LEGAL_OBLIGATION,
            RET_DSAR,
            REC_AUDITOR,
        ),
    )
    legal_strings_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "SHA-256 of the exact docs/legal/strings.yaml bytes the answer was "
            "issued under (invariant 18, the consents.text_hash precedent): a "
            "re-issue against moved copy is refused rather than restated; NULL "
            "until an export is first rendered and for kinds that render none",
            BASIS_LEGAL_OBLIGATION,
            RET_DSAR,
            REC_AUDITOR,
        ),
    )


class DsarRectification(Base):
    """A KVKK m.11 / KSVY m.13 correction, stored as an ADDENDUM.

    files/02 §3: rectification produces "an addendum rather than a silent
    rewrite" — overwriting the note would falsify the record of what the
    patient actually said, which is the one thing an audit cannot survive. The
    correction is the subject's own words, so it is special-category health
    data and carries an envelope like every other clinical payload.
    """

    __tablename__ = "dsar_rectifications"

    id: Mapped[uuid.UUID] = _uuid_pk("rectification addendum key", RET_RECORD)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_RECORD)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the pseudonymised patient whose record the addendum corrects",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dsar_requests.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the m.11 request this addendum answers",
            BASIS_LEGAL_OBLIGATION,
            RET_RECORD,
            REC_AUDITOR,
        ),
    )
    target_ref: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "what is being corrected, as an id-shaped reference (kind:uuid) — "
            "validated at the boundary so free text cannot enter a column the "
            "tracker and the audit both read (invariant 6)",
            BASIS_LEGAL_OBLIGATION,
            RET_RECORD,
            REC_AUDITOR,
        ),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "the correction in the patient's own words as EncryptedField JSON "
            "(field-level envelope encryption; never plaintext at rest)",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_PATIENT_CLINICIAN,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_RECORD)


class Event(Base):
    """Generic append-only event rows (csat/nps/lifecycle streams). The
    hash-chained audit is a different table with a different writer role."""

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_tenant_type", "tenant_id", "event_type"),)

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        info=inv(
            CAT_OPERATIONAL,
            "event row key",
            BASIS_CONTRACT,
            RET_EVENTS,
            REC_INTERNAL,
        ),
    )
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_EVENTS)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "session the event refers to, when session-scoped",
            BASIS_CONTRACT,
            RET_EVENTS,
            REC_INTERNAL,
        ),
    )
    event_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "versioned event name (csat.v1, nps.v1, …)",
            BASIS_CONTRACT,
            RET_EVENTS,
            REC_INTERNAL,
        ),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "event body — id-shaped values only, no PHI (invariant 6)",
            BASIS_CONTRACT,
            RET_EVENTS,
            REC_INTERNAL,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_EVENTS)
