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

from clinical_schemas.overlay import LearnedFactSource
from clinical_schemas.records import RecordItemKind
from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.types import BigInteger, Integer, Uuid

from intake_platform.db.inventory import (
    BASIS_AWAITING_HUMAN_GUARDIAN,
    BASIS_CONTRACT,
    BASIS_EVENTS_BY_TYPE,
    BASIS_HEALTH_CONSENT,
    BASIS_LEGAL_OBLIGATION,
    BASIS_SATISFACTION_CONSENT,
    CAT_CONSENT,
    CAT_GUARDIANSHIP,
    CAT_HEALTH,
    CAT_OPERATIONAL,
    CAT_PSEUDONYM,
    REC_AUDITOR,
    REC_CLINICIAN,
    REC_GUARDIAN_INTERNAL,
    REC_HOSPITAL_SYSTEM_AWAITING_HUMAN,
    REC_INTERNAL,
    REC_PATIENT_CLINICIAN,
    RET_AWAITING_HUMAN_GUARDIAN,
    RET_CONSENT_AUDIT,
    RET_DSAR,
    RET_EVENTS,
    RET_NOTIFICATION_PREFERENCE,
    RET_PREVISIT_OUTPUT,
    RET_RECORD,
    RET_SATISFACTION,
    RET_SHARE,
    RET_TENANT,
    inv,
)
from intake_platform.db.vector import Vector
from intake_platform.locale import DEFAULT_LOCALE

__all__ = [
    "Base",
    "Consent",
    "DoctorLink",
    "Document",
    "DsarKind",
    "DsarRectification",
    "DsarRequest",
    "DsarStatus",
    "Event",
    "GuardianLink",
    "IntakeSession",
    "KvkkRole",
    "NotificationPreference",
    "Note",
    "OverlayFact",
    "Patient",
    "PatientOverlayHeader",
    "PreVisitOutputRow",
    "RecordEmbedding",
    "SessionAttribution",
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


class SessionAttribution(enum.StrEnum):
    """INT-133 — who produced the answers in this session (files/02 §3).

    Three values, not two: ``assisted_self_report`` is the patient's own
    words on a family member's device, which the other two both misdescribe.
    This column is the SOURCE of files/06 §6's "companion/proxy answers are
    always flagged ``proxy_reported`` on the record" — every record derived
    from a session reads the flag from here rather than carrying an
    independently settable copy that could drift out of step.
    """

    SELF_REPORT = "self_report"
    PROXY_REPORT = "proxy_report"
    ASSISTED_SELF_REPORT = "assisted_self_report"


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


# The three helpers below default to the contract ground. A table whose rows
# rest on another ground passes it (INT-536: csat_texts and events).


def _uuid_pk(purpose: str, retention: str, *, basis: str = BASIS_CONTRACT) -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        info=inv(CAT_OPERATIONAL, purpose, basis, retention, REC_INTERNAL),
    )


def _tenant_fk(retention: str, *, basis: str = BASIS_CONTRACT) -> Mapped[uuid.UUID]:
    return mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "RLS boundary: the tenant this row belongs to (policies compare it "
            "to the app.tenant_id GUC)",
            basis,
            retention,
            REC_INTERNAL,
        ),
    )


def _created_at(retention: str, *, basis: str = BASIS_CONTRACT) -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        info=inv(
            CAT_OPERATIONAL,
            "row creation instant (retention clocks start here)",
            basis,
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
    # --- INT-133: session attribution (files/02 §3; files/06 §6; files/13 §13) ---
    # No new personal-data CATEGORY: these are the same three provenance
    # facts the clinician note already carries and already sends to FHIR
    # (clinical_schemas.note.ScreeningProvenance), lifted to the session so
    # every record derived from it reads ONE flag. Nothing here identifies
    # the companion — no name, no account ref, no relationship. A persisted
    # person↔person link is the separate, gated guardian_links table.
    attribution: Mapped[SessionAttribution] = mapped_column(
        Enum(
            SessionAttribution,
            name="session_attribution",
            native_enum=False,
            length=24,
            values_callable=lambda cls: [member.value for member in cls],
        ),
        nullable=False,
        default=SessionAttribution.SELF_REPORT,
        server_default=SessionAttribution.SELF_REPORT.value,
        info=inv(
            CAT_HEALTH,
            "who produced the answers (self / proxy / assisted): a clinician reading the "
            "note must know whether the symptoms are reported or observed",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_CLINICIAN,
        ),
    )
    third_party_present: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        info=inv(
            CAT_HEALTH,
            "a second person was present or answering (files/13 §13): the disclosure "
            "confound that forces sensitive sections to text and stops safeguarding",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_CLINICIAN,
        ),
    )
    proxy_ack_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "instant the companion acknowledged answering on the patient's behalf; an "
            "acknowledgement of ROLE only — never evidence of legal representation "
            "(policy row guardian_relationship_proof is awaiting-human)",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    # --- INT-296: the session locale (CLAUDE.md inv. 5, 6, 18) ---------------
    # ONE language per session, fixed at the start and changed only by an
    # explicit patient act. It lives here rather than being threaded through
    # each lookup so the note, the audit entry and the metric label read the
    # same value and no single turn can be assembled out of two languages.
    #
    # The value set is closed by intake_platform.locale.LOCALE_REGISTRY, which
    # today holds exactly `tr` (HB-O5 names the rest, HB-C19 signs them). No
    # DB enum: the registry is the authority and a Postgres enum nobody can
    # migrate cheaply would become a second, drifting one.
    locale: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=DEFAULT_LOCALE,
        server_default=DEFAULT_LOCALE,
        info=inv(
            CAT_OPERATIONAL,
            "which language the patient was actually asked in, so the note, the audit "
            "entry and the metric label cannot disagree. Operational rather than "
            "special-category WHILE `tr` is the only registered locale: the column is "
            "then the service's own language and states nothing about the patient. A "
            "second registered locale changes that — a language choice can proxy ethnic "
            "origin (KVKK m.6) — and the category, basis and recipients must be "
            "re-decided before one is enabled (HUMAN_BLOCKERS.md HB-L25). Never a free-"
            "text language name: the value is a registry code (inv. 6)",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_CLINICIAN,
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
            "decides the value representation from the slot's protocol data "
            "category: plain JSON for general_health, an EncryptedField envelope "
            "for every other category (INT-349)",
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
            "the slot value; every data category but general_health carries "
            "EncryptedField JSON (envelope_json), never plaintext, and is further "
            "governed by its row in docs/legal/data-categories.yaml, whose basis, "
            "retention and recipients counsel supplies (INT-349)",
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


class GuardianLink(Base):
    """INT-223 — "this account is the legal representative of that minor".

    Behind the closed ``guardian_link`` gate
    (:mod:`intake_platform.consent.guardian`): persisting a guardian↔minor
    relationship is a NEW personal-data category, which CLAUDE.md makes a
    stop-and-ask, so **every** column carries an awaiting-human basis and an
    awaiting-human retention rather than a ground somebody guessed. The
    minor is a pseudonymised patient row and the guardian is an id-shaped
    account ref — no name, no TCKN, no relationship narrative (invariant
    14/6). ``verified_at`` stays NULL because no proof standard exists yet
    (policy row ``guardian_relationship_proof``).
    """

    __tablename__ = "guardian_links"
    __table_args__ = (UniqueConstraint("tenant_id", "minor_patient_id", "guardian_account_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        info=inv(
            CAT_GUARDIANSHIP,
            "guardian↔minor link key",
            BASIS_AWAITING_HUMAN_GUARDIAN,
            RET_AWAITING_HUMAN_GUARDIAN,
            REC_GUARDIAN_INTERNAL,
        ),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_GUARDIANSHIP,
            "RLS boundary: the tenant this link belongs to",
            BASIS_AWAITING_HUMAN_GUARDIAN,
            RET_AWAITING_HUMAN_GUARDIAN,
            REC_GUARDIAN_INTERNAL,
        ),
    )
    minor_patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_GUARDIANSHIP,
            "the pseudonymised minor the link is about",
            BASIS_AWAITING_HUMAN_GUARDIAN,
            RET_AWAITING_HUMAN_GUARDIAN,
            REC_GUARDIAN_INTERNAL,
        ),
    )
    guardian_account_ref: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_GUARDIANSHIP,
            "id-shaped ref to the guardian's account; never a name or an identifier",
            BASIS_AWAITING_HUMAN_GUARDIAN,
            RET_AWAITING_HUMAN_GUARDIAN,
            REC_GUARDIAN_INTERNAL,
        ),
    )
    relationship_ref: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_GUARDIANSHIP,
            "id of the relationship-evidence record (acknowledgement or desk check) — an id, "
            "never the evidence and never the relationship in words",
            BASIS_AWAITING_HUMAN_GUARDIAN,
            RET_AWAITING_HUMAN_GUARDIAN,
            REC_GUARDIAN_INTERNAL,
        ),
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        info=inv(
            CAT_GUARDIANSHIP,
            "instant a proof standard was satisfied; NULL while no standard exists "
            "(policy row guardian_relationship_proof)",
            BASIS_AWAITING_HUMAN_GUARDIAN,
            RET_AWAITING_HUMAN_GUARDIAN,
            REC_GUARDIAN_INTERNAL,
        ),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        info=inv(
            CAT_GUARDIANSHIP,
            "instant the link ended (majority reached, representation changed); NULL while live",
            BASIS_AWAITING_HUMAN_GUARDIAN,
            RET_AWAITING_HUMAN_GUARDIAN,
            REC_GUARDIAN_INTERNAL,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        info=inv(
            CAT_GUARDIANSHIP,
            "row creation instant",
            BASIS_AWAITING_HUMAN_GUARDIAN,
            RET_AWAITING_HUMAN_GUARDIAN,
            REC_GUARDIAN_INTERNAL,
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


class DoctorLink(Base):
    """INT-150 — one tokenized clinician grant over one share (files/10 §2).

    Why a table of its own rather than columns on ``shares``: a share is the
    patient's decision about WHAT is shared; a Doctor Link is one addressed,
    expiring, countable way of reaching it, and a patient may issue, revoke and
    re-issue links against a single unchanged share. The scope therefore stays
    on the share and is never copied here — the section list has exactly one
    home, so a link can never expose a section the share does not carry.

    What is deliberately NOT a column:

    - **the token.** ``token_fingerprint`` is SHA-256 of a 128-bit random
      token; a database dump therefore yields no access (invariant 6).
    - **the OTP code, its attempt count and its request windows.** Those live
      in Redis behind ``intake_api.auth_store.AuthStore`` — the SAME gate the
      phone-OTP tier uses (INT-131/INT-263), not a second one.
    - **the first-open instant.** Every open is written to the hash-chained
      audit log, which is what invariant 4 requires and what the patient's
      access log renders. A queryable open-instant column is the missing half
      of ``wait.doctor_link_first_open_h``, and landing it without the
      publisher would put ``intake_platform.wait_times``, the metrics
      catalogue and the writer out of step — the exact drift that registry
      exists to prevent (docs/evidence/INT-150.md records the ask).
    """

    __tablename__ = "doctor_links"

    id: Mapped[uuid.UUID] = _uuid_pk("doctor link grant key", RET_SHARE)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_SHARE)
    share_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shares.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_CONSENT,
            "the share this link grants access to (the section scope lives there)",
            BASIS_HEALTH_CONSENT,
            RET_SHARE,
            REC_CLINICIAN,
        ),
    )
    token_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        info=inv(
            CAT_OPERATIONAL,
            "SHA-256 of the 128-bit link token; the token itself is never stored",
            BASIS_HEALTH_CONSENT,
            RET_SHARE,
            REC_INTERNAL,
        ),
    )
    recipient: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "envelope-encrypted recipient label the patient named, rendered only "
            "into the watermark of the view that recipient opens",
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
            "hard expiry, anchored on the visit date + 72 h (files/02 §2b), never on issue time",
            BASIS_HEALTH_CONSENT,
            RET_SHARE,
            REC_INTERNAL,
        ),
    )
    view_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "how many openings this grant permits (files/10 §2 view limit)",
            BASIS_HEALTH_CONSENT,
            RET_SHARE,
            REC_INTERNAL,
        ),
    )
    views_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        default=0,
        info=inv(
            CAT_OPERATIONAL,
            "openings spent; incremented by the same guarded UPDATE that admits one",
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
            "instant the link was revoked (by the patient, or by the share it hangs off)",
            BASIS_HEALTH_CONSENT,
            RET_SHARE,
            REC_INTERNAL,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_SHARE)

    __table_args__ = (
        CheckConstraint("view_limit > 0", name="view_limit_positive"),
        CheckConstraint("views_used >= 0", name="views_used_not_negative"),
    )


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
            BASIS_EVENTS_BY_TYPE,
            RET_EVENTS,
            REC_INTERNAL,
        ),
    )
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_EVENTS, basis=BASIS_EVENTS_BY_TYPE)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "session the event refers to, when session-scoped",
            BASIS_EVENTS_BY_TYPE,
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
            BASIS_EVENTS_BY_TYPE,
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
            BASIS_EVENTS_BY_TYPE,
            RET_EVENTS,
            REC_INTERNAL,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_EVENTS, basis=BASIS_EVENTS_BY_TYPE)


class NotificationPreference(Base):
    """INT-141 — the patient's own message-refusal register: one opt-out flag
    and, optionally, a quiet window.

    It is a table rather than a setting in a process because a quiet-hours
    window that lives in memory is a quiet-hours window that stops working at
    the next deploy — at 03:00, for everybody at once.

    Shape notes:

    - **Two integers and a flag.** Minutes since local midnight, evaluated on
      the fixed Türkiye offset (``intake_platform.notifications.preferences``),
      so no per-patient timezone column exists and no location signal is
      collected to support one.
    - **Both ends or neither** (``ck_notification_preferences_quiet_window``):
      half a window is not a window, and accepting one end while defaulting
      the other would be the invented value rule 1 forbids.
    - **Nothing here is an identifier**: no device token, no push handle, no
      phone number (invariant 14). Delivery addressing belongs to the
      transport and its vendor contract, which does not exist yet.
    - One row per patient per tenant; a change replaces it in place, because
      the history of a preference is the audit chain's business, not this
      table's.
    """

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "patient_id"),
        CheckConstraint(
            "(quiet_start_minute IS NULL) = (quiet_end_minute IS NULL)",
            name="quiet_window",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk("notification preference row key", RET_NOTIFICATION_PREFERENCE)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_NOTIFICATION_PREFERENCE)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the pseudonymised patient whose delivery preference this is",
            BASIS_CONTRACT,
            RET_NOTIFICATION_PREFERENCE,
            REC_INTERNAL,
        ),
    )
    opted_out: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        info=inv(
            CAT_OPERATIONAL,
            "the patient has asked to receive no messages; honoured for every "
            "class this product sends (files/06 §1 row 6563-İYS)",
            BASIS_CONTRACT,
            RET_NOTIFICATION_PREFERENCE,
            REC_INTERNAL,
        ),
    )
    quiet_start_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "start of the patient's quiet window, minutes since local midnight; "
            "NULL means she has said nothing about hours, never that she is "
            "happy to be woken",
            BASIS_CONTRACT,
            RET_NOTIFICATION_PREFERENCE,
            REC_INTERNAL,
        ),
    )
    quiet_end_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        info=inv(
            CAT_OPERATIONAL,
            "end of the patient's quiet window, minutes since local midnight; "
            "NULL exactly when the start is NULL (check constraint)",
            BASIS_CONTRACT,
            RET_NOTIFICATION_PREFERENCE,
            REC_INTERNAL,
        ),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        info=inv(
            CAT_OPERATIONAL,
            "instant the patient last changed the setting",
            BASIS_CONTRACT,
            RET_NOTIFICATION_PREFERENCE,
            REC_INTERNAL,
        ),
    )


class CsatText(Base):
    """INT-240 — the optional free text on a ``csat.v1`` response.

    Why it is not a column on ``events``: satisfaction feedback is written by
    the patient, so it WILL carry symptoms and names, and ``events.payload`` is
    declared id-shaped and PHI-free because the rollups and the console read it
    (invariant 6; threat row `experience` threat [I]). Splitting the sentence
    out keeps that declaration true instead of quietly weakening it — the
    scores stay analysable and the words stay behind an envelope.

    Storage is the clinical regime: field-level envelope encryption, never
    plaintext at rest (invariant 14), exactly like ``notes.payload`` and
    ``dsar_rectifications.payload``.

    Destruction needs no new sweeper, which is the point of both foreign keys
    being ``ON DELETE CASCADE``:

    - **session** — a KVKK m.7/m.11 erasure deletes the subject's sessions
      (``intake_api.dsar.shred``), so the words go with them;
    - **event** — the files/06 §3 ``satisfaction`` class ("with account")
      destroys the event rows (``retention.executors.destroy_events``), so the
      words go with those too.

    A third sweeper could fall out of step with the two that already exist; a
    foreign key cannot.
    """

    __tablename__ = "csat_texts"

    id: Mapped[uuid.UUID] = _uuid_pk(
        "csat free-text row key", RET_SATISFACTION, basis=BASIS_SATISFACTION_CONSENT
    )
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_SATISFACTION, basis=BASIS_SATISFACTION_CONSENT)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the session the response rates; the FK cascade is what makes a "
            "DSAR erasure reach the text (invariant 4)",
            BASIS_SATISFACTION_CONSENT,
            RET_SATISFACTION,
            REC_INTERNAL,
        ),
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        info=inv(
            CAT_OPERATIONAL,
            "the csat.v1 event row this text belongs to; the FK cascade is "
            "what makes the 06 §3 satisfaction clock reach the text",
            BASIS_SATISFACTION_CONSENT,
            RET_SATISFACTION,
            REC_INTERNAL,
        ),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "the patient's satisfaction comment in their own words as "
            "EncryptedField JSON (field-level envelope encryption; never "
            "plaintext at rest). Health data whatever the survey calls it: "
            "free text about a visit carries symptoms",
            BASIS_HEALTH_CONSENT,
            RET_SATISFACTION,
            REC_INTERNAL,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_SATISFACTION, basis=BASIS_SATISFACTION_CONSENT)


class PatientOverlayHeader(Base):
    """INT-170 — the versioned header of one patient's ``PatientOverlay``.

    files/09 §3 makes the overlay *"versioned, patient-owned, exported/
    deletable"*. The version cannot be derived from the facts themselves: a
    deletion is a mutation, and a version taken as ``max()`` over surviving
    rows would go **backwards** when the patient removes the newest fact. So
    the counter is a column, bumped by every mutation and by nothing else.

    Version 1 is the empty overlay every patient starts with — the header row
    appears on the first mutation, at version 2, so "no header" and "version 1"
    are the same statement rather than two.
    """

    __tablename__ = "patient_overlays"
    __table_args__ = (UniqueConstraint("tenant_id", "patient_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk("patient overlay header key", RET_RECORD)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_RECORD)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the pseudonymised patient who owns this overlay",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "overlay version — monotonic, one increment per mutation (files/09 §3: "
            "the overlay is versioned)",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        info=inv(
            CAT_OPERATIONAL,
            "instant of the most recent overlay mutation",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )


class OverlayFact(Base):
    """INT-170 — one CONFIRMED learned fact (files/09 §3; invariant 12).

    There is deliberately **no companion table for unconfirmed candidates**,
    and the absence is the design rather than an omission. A nullable
    ``source`` column — one table holding both forms — is exactly the runtime
    check invariant 12 refuses to rely on; and persisting unconfirmed
    proposals would be a new category of personal data, which CLAUDE.md makes
    a stop-and-ask. A :class:`~clinical_schemas.overlay.FactCandidate` is
    therefore held by the patient's own device until they confirm it, and only
    the confirmation is written here (see docs/evidence/INT-170.md).

    Shape notes:

    - **The value is an envelope, always** (invariant 14: field-level envelope
      encryption for *"transcripts/notes/learned facts"*). ``payload`` carries
      EncryptedField JSON over ``{"value": …, "confidence": …}``; there is no
      plaintext-value column to fall back to.
    - **``fact_key`` is in the clear**, exactly as ``slots.slot_id`` is: a fact
      key is an authored protocol reference (``oyku.belirti_var``), not
      patient narrative — that is what makes delta mode able to match it
      against a step id at all.
    - **One row per key per patient.** Re-confirmation replaces it in place and
      restarts the twelve-month clock; the history of a confirmation is the
      hash-chained audit's business, not this table's.
    - **A deletion removes the row**, with no tombstone: a tombstone that keeps
      the key keeps the health fact the patient asked us to forget.
    """

    __tablename__ = "overlay_facts"
    __table_args__ = (UniqueConstraint("tenant_id", "patient_id", "fact_key"),)

    id: Mapped[uuid.UUID] = _uuid_pk("learned fact row key", RET_RECORD)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_RECORD)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the pseudonymised patient the fact was learned about",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    fact_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "authored protocol reference the fact answers (files/09 §3 fact key); "
            "an id in the shape of slots.slot_id, never patient narrative",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_PATIENT_CLINICIAN,
        ),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "the learned value and its confidence as EncryptedField JSON "
            "(field-level envelope encryption; never plaintext at rest)",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_PATIENT_CLINICIAN,
        ),
    )
    source: Mapped[str] = mapped_column(
        Enum(
            LearnedFactSource,
            name="learned_fact_source",
            native_enum=False,
            length=32,
            values_callable=lambda cls: [member.value for member in cls],
        ),
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "confirmed provenance (files/09 §3): the closed three-member vocabulary, "
            "which has no unconfirmed value to store",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_PATIENT_CLINICIAN,
        ),
    )
    source_ref: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "id of the confirming artefact — the 'where from' every fact must show "
            "the patient (files/09 §3 guardrails)",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_PATIENT_CLINICIAN,
        ),
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "when the patient or clinician confirmed it; the twelve-month "
            "re-confirmation window runs from here (files/09 §3)",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_PATIENT_CLINICIAN,
        ),
    )
    shared: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        info=inv(
            CAT_CONSENT,
            "per-field share scope (files/09 §3 guardrails): whether this fact may "
            "travel with a shared note",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_PATIENT_CLINICIAN,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_RECORD)


class PreVisitOutputRow(Base):
    """The finished previsit as a hospital receives it — one frozen document
    per completed previsit (owner directive: *"after the previsit is done write
    output version of json which is worked on in a sql in the data folder under
    intake"*).

    **Why a table rather than a second read of ``notes``.** ``notes.payload``
    is the working artefact: it is rewritten in place on every save, and its
    shape is the review screen's. This row is the finished thing — produced
    once, at completion, and stable afterwards — and it carries three facts the
    note has nowhere to put: the ``schema_version`` a receiver branches on, the
    ``completed_at`` instant the previsit actually ended, and a
    ``payload_sha256`` the receiver can dedupe on without decrypting anything.

    **What it deliberately does not hold.** No patient number, no name, no
    TCKN: the hospital's own key is resolved to ``patients.pseudonym`` through
    the Tokenizer at request time and echoed back from the request, so the
    direct identifier has no column anywhere in this database (invariant 14).
    No section scope either — that stays on ``shares.scope_sections``, so a
    fetch can never widen what the patient sent (the rule the Doctor Link view
    already obeys).

    ``payload`` is an EncryptedField envelope like ``notes.payload``
    (invariant 14), and ``recipients`` on every column is the awaiting-human
    one: this row exists to be fetched by a hospital system, and no DPA names
    one yet.
    """

    __tablename__ = "previsit_outputs"
    # One output per completed previsit: a resend replaces the document rather
    # than appending a second one, so "the finished previsit" stays singular.
    __table_args__ = (UniqueConstraint("tenant_id", "session_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk("previsit output key", RET_PREVISIT_OUTPUT)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_PREVISIT_OUTPUT)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the completed intake session this output was produced from",
            BASIS_CONTRACT,
            RET_PREVISIT_OUTPUT,
            REC_INTERNAL,
        ),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "the pseudonymised patient this output belongs to — the lookup key a "
            "hospital patient number resolves to through the Tokenizer",
            BASIS_CONTRACT,
            RET_PREVISIT_OUTPUT,
            REC_INTERNAL,
        ),
    )
    schema_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "versioned identity of the stored structure (clinical_schemas."
            "previsit_output); the receiver branches on it",
            BASIS_CONTRACT,
            RET_PREVISIT_OUTPUT,
            REC_HOSPITAL_SYSTEM_AWAITING_HUMAN,
        ),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "the finished previsit as EncryptedField JSON (field-level envelope "
            "encryption; never plaintext at rest)",
            BASIS_HEALTH_CONSENT,
            RET_PREVISIT_OUTPUT,
            REC_HOSPITAL_SYSTEM_AWAITING_HUMAN,
        ),
    )
    payload_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "digest of the canonical plaintext document — content identity for the "
            "receiver's own de-duplication; a digest of clinical text, not the text",
            BASIS_CONTRACT,
            RET_PREVISIT_OUTPUT,
            REC_HOSPITAL_SYSTEM_AWAITING_HUMAN,
        ),
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "when the previsit finished (a completed intake is a health fact)",
            BASIS_HEALTH_CONSENT,
            RET_PREVISIT_OUTPUT,
            REC_HOSPITAL_SYSTEM_AWAITING_HUMAN,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_PREVISIT_OUTPUT)


class RecordEmbedding(Base):
    """INT-123 — one CONFIRMED record item's vector, in one patient's namespace.

    files/03 §10: *"pgvector embeddings for retrieval during intake"*; files/10
    §5 LLM08: *"pgvector rows scoped by patient + consent; RLS; no shared
    namespaces"*. The namespace is declared here, in ``Table.info``, and
    tests/records/test_vector_rls.py checks the migration's policies against
    it: a PERMISSIVE tenant policy like every tenant-scoped table's, and a
    RESTRICTIVE patient policy on the ``app.patient_id`` GUC, so a session
    reads one patient's vectors and no GUC reads none.

    **What is stored, and what is not.** A vector, the box it came from and
    the id of the confirmed item — never the item's text. The confirmed item
    is the source of truth and the note cites it from there; a second copy of
    the line here would be a second place to erase and a plaintext column that
    RLS alone would have to protect.

    **Only a confirmed item is ever written** (invariant 12): the one writer is
    :class:`~intake_platform.records.index.RecordIndexQueue`, which takes
    :class:`~clinical_schemas.record_extraction.ConfirmedRecordItem` alone.

    **Erasure reaches every row.** ``document_ref`` is ``doc:<documents.id>`` —
    the writer refuses any other shape — so the per-session retention executor
    finds the rows of each document it destroys, and the DSAR erasure removes
    the subject's rows by namespace. ``patient_id`` keeps NO ACTION so a path
    that forgot them fails rather than orphaning them.
    """

    __tablename__ = "record_embeddings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "patient_id", "item_ref", "model_ref"),
        CheckConstraint("page >= 1", name="page_positive"),
        CheckConstraint("char_end > char_start AND char_start >= 0", name="char_span"),
        CheckConstraint("dimensions > 0", name="dimensions_positive"),
        {
            "info": {
                "rls_namespace": (("tenant_id", "app.tenant_id"), ("patient_id", "app.patient_id"))
            }
        },
    )

    id: Mapped[uuid.UUID] = _uuid_pk("record index row key", RET_RECORD)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk(RET_RECORD)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "RLS namespace: the pseudonymised patient whose confirmed record this "
            "vector indexes (policies compare it to the app.patient_id GUC)",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    item_ref: Mapped[str] = mapped_column(
        String(35),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "derived id of the confirmed record item (sha256 of its source box), "
            "cited into the note beside the document span",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    document_ref: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        info=inv(
            CAT_OPERATIONAL,
            "provenance: doc:<documents.id> of the page the item was read from — "
            "also the key the retention executor erases by",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    page: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "provenance: 1-based page of the source box",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    bbox: Mapped[list[float]] = mapped_column(
        JSONB,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "provenance: the source box on the page, normalised [x0, y0, x1, y1]",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    char_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "provenance: start of the item's characters in the extracted text",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    char_end: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "provenance: end (exclusive) of the item's characters in the extracted text",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    kind: Mapped[RecordItemKind] = mapped_column(
        Enum(
            RecordItemKind,
            name="record_item_kind",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda cls: [member.value for member in cls],
        ),
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "the confirmed item's kind (lab, imaging, medication …) — which note "
            "section a citation of it may be filed under",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    model_ref: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "the embedding model's pin, model_id@revision (invariant 14): a vector "
            "is only ever compared with vectors from the same model",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "the vector's dimension as the model declares it; the migration checks "
            "vector_dims(embedding) against it",
            BASIS_CONTRACT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    embedding: Mapped[tuple[float, ...]] = mapped_column(
        Vector(),
        nullable=False,
        info=inv(
            CAT_HEALTH,
            "the confirmed item's embedding, for retrieval during intake (files/03 "
            "§10) — derived from health data, readable only inside the patient's "
            "RLS namespace and never by the clinician role",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    consent_scope_ref: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        info=inv(
            CAT_OPERATIONAL,
            "the consent purpose the row was written under (scope:documents; invariant 4)",
            BASIS_HEALTH_CONSENT,
            RET_RECORD,
            REC_INTERNAL,
        ),
    )
    created_at: Mapped[datetime] = _created_at(RET_RECORD)
