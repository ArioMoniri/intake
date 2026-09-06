"""Versioned event schemas (INT-031): csat.v1, nps.v1, clinician_pulse.v1,
wait.v1, audit.v1, security.v1.

Satisfaction events are first-class events on Redis streams with a schema in
``packages/clinical-schemas/events`` (files/08 §8 observability pipeline);
``audit.v1``/``security.v1`` separate security events from application logs
(files/10 §2). Payloads are id-shaped only — no PHI in events (invariant 6);
the persistence twin is the append-only ``events`` table (INT-030), whose
``created_at`` owns event time, so payloads carry no timestamp of their own
(the one exception is ``audit.v1``, which mirrors the INT-016 chain entry
field for field — the timestamp is part of what was hashed).

Event identity follows the TS convention (``schemaId`` in
``packages/clinical-schemas/src/index.ts``): ``intake.clinical.<name>.v1``.
"""

from __future__ import annotations

import enum
import uuid
from typing import Literal

from pydantic import Field

from clinical_schemas.common import FrozenModel, Ref, Sha256


class CsatReason(enum.StrEnum):
    """The CSAT reason distribution of files/08 §4 group F: too long /
    didn't understand me / felt rushed / helpful / felt heard."""

    TOO_LONG = "too_long"
    DIDNT_UNDERSTAND_ME = "didnt_understand_me"
    FELT_RUSHED = "felt_rushed"
    HELPFUL = "helpful"
    FELT_HEARD = "felt_heard"


class CsatV1(FrozenModel):
    """Session satisfaction (INT-240 acceptance: "csat.v1 (1-5 + reason enum
    + optional text)"; emitted via POST /sessions/{id}/csat, files/03 §6)."""

    schema_id: Literal["intake.clinical.csat.v1"] = Field(
        default="intake.clinical.csat.v1",
        description="Versioned event id per the TS schemaId convention.",
    )
    tenant_id: uuid.UUID = Field(description="Owning tenant (INT-030 events.tenant_id).")
    session_id: uuid.UUID = Field(
        description="Session the rating refers to (INT-030 events.session_id; "
        "POST /sessions/{id}/csat, files/03 §6)."
    )
    score: int = Field(
        ge=1, le=5, description="CSAT 1-5 (files/08 §4 group F: csat.score, target >= 4.3)."
    )
    reason: CsatReason | None = Field(
        default=None,
        description="Reason category (INT-240 reason enum; files/08 §4 group F "
        "csat.reason distribution). Optional since INT-305: files/02 §5.4's "
        "one-tap prompt forms a complete rating from the score alone, so a "
        "score with no reason is a whole event — and a reason is never "
        "defaulted or inferred from the score (invariant 6).",
    )
    text: str | None = Field(
        default=None,
        max_length=500,
        description="Optional free text (INT-240). Patient-authored: treat as sensitive "
        "content — rendered to service owners only, never into logs or traces "
        "(invariant 6).",
    )


class NpsV1(FrozenModel):
    """Net promoter score (INT-240; files/08 §4 group F nps.monthly; emitted
    via POST /feedback/nps, files/03 §6). Standard NPS 0-10 scale."""

    schema_id: Literal["intake.clinical.nps.v1"] = Field(
        default="intake.clinical.nps.v1",
        description="Versioned event id per the TS schemaId convention.",
    )
    tenant_id: uuid.UUID = Field(description="Owning tenant (INT-030 events.tenant_id).")
    score: int = Field(ge=0, le=10, description="NPS 0-10 (files/08 §4 group F nps.monthly).")


class ClinicianPulseV1(FrozenModel):
    """Quarterly clinician pulse (INT-240; files/08 §4 group F:
    clinician.pulse, quarterly 1-5)."""

    schema_id: Literal["intake.clinical.clinician_pulse.v1"] = Field(
        default="intake.clinical.clinician_pulse.v1",
        description="Versioned event id per the TS schemaId convention.",
    )
    tenant_id: uuid.UUID = Field(description="Owning tenant (INT-030 events.tenant_id).")
    clinician_ref: Ref = Field(
        description="Clinician as an id — never a name (invariant 6; files/08 §4 group F)."
    )
    score: int = Field(
        ge=1, le=5, description="Pulse score 1-5 (files/08 §4 group F clinician.pulse)."
    )


class WaitKind(enum.StrEnum):
    """The wait intervals files/08 §4 group G names and INT-241's acceptance
    enumerates. A closed set: a kind outside group G has no catalogue row, so
    it has no honest way to be emitted (invariant 13)."""

    TIME_TO_FIRST_QUESTION = "time_to_first_question"
    NOTE_READY_AFTER_WRAPUP = "note_ready_after_wrapup"
    DOCTOR_LINK_FIRST_OPEN = "doctor_link_first_open"
    CHECKIN_TO_SEEN = "checkin_to_seen"
    RECORDS_PROCESSING = "records_processing"


class DocumentKind(enum.StrEnum):
    """The ``document_type`` breakdown files/08 §4 G asks of
    ``wait.records_processing_s``.

    These are the THREE content types the ingest allow-list already accepts
    (``intake_platform.documents.ALLOWED_CONTENT_TYPES``), renamed to a label
    value. It is deliberately not a clinical document taxonomy — lab report,
    discharge summary, prescription — because this repo has none and inventing
    one here would be a value chosen once by an engineer for every future
    reader. ``intake_platform.wait_times`` holds the mapping and a test fails
    the build if the allow-list gains a type this enum does not cover.
    """

    PDF = "pdf"
    JPEG = "jpeg"
    PNG = "png"


class WaitV1(FrozenModel):
    """One completed wait interval (INT-241; files/08 §4 group G).

    **A duration, not two instants.** The interval is reduced to a scalar
    before it is written: instants plus a session id are a queue position that
    correlates to a person, a duration is not. The row's own ``created_at``
    still owns event time (the module convention above), which is what puts
    the observation inside a rollup window.

    **No free text and no minimum unit of one.** ``kind`` and
    ``document_type`` are closed enumerations; ``duration_ms`` is a count of
    milliseconds. There is nowhere for an identifier or a sentence to ride
    (invariant 6), which is what lets the rollups read the payload directly.
    """

    schema_id: Literal["intake.clinical.wait.v1"] = Field(
        default="intake.clinical.wait.v1",
        description="Versioned event id per the TS schemaId convention.",
    )
    tenant_id: uuid.UUID = Field(description="Owning tenant (INT-030 events.tenant_id).")
    kind: WaitKind = Field(
        description="Which files/08 §4 group G interval this measures (closed set)."
    )
    duration_ms: int = Field(
        ge=0,
        description="Elapsed milliseconds between the interval's two instants, measured "
        "on a monotonic clock. A count, never a wall-clock pair.",
    )
    document_type: DocumentKind | None = Field(
        default=None,
        description="Ingest content kind, for wait.records_processing_s only "
        "(files/08 §4 G: 'by document type'). None for every other kind.",
    )


class AuditV1(FrozenModel):
    """One hash-chain audit entry as an event — field for field the INT-016
    ``AuditEntry`` (packages/intake_platform/src/intake_platform/audit.py),
    which is the source of truth for this shape (invariant 4: every read/
    share audited; the chain makes editing detectable)."""

    schema_id: Literal["intake.clinical.audit.v1"] = Field(
        default="intake.clinical.audit.v1",
        description="Versioned event id per the TS schemaId convention.",
    )
    seq: int = Field(ge=1, description="Chain position (INT-016 AuditEntry.seq).")
    timestamp_utc: str = Field(
        min_length=1,
        description="ISO-8601 UTC instant exactly as hashed (INT-016 "
        "AuditEntry.timestamp_utc — part of the hashed material, so it travels "
        "verbatim, never reformatted).",
    )
    actor: Ref = Field(description="Acting principal id (INT-016 AuditEntry.actor).")
    action: Ref = Field(
        description="Dotted action name, e.g. note.read (INT-016 AuditEntry.action)."
    )
    resource_ref: Ref = Field(
        description="Resource acted on, as an id (INT-016 AuditEntry.resource_ref)."
    )
    consent_scope_ref: Ref = Field(
        description="Consent scope that authorised the action (INT-016 "
        "AuditEntry.consent_scope_ref; invariant 4)."
    )
    prev_hash: Sha256 = Field(
        description="SHA-256 of the predecessor entry (INT-016 AuditEntry.prev_hash)."
    )
    entry_hash: Sha256 = Field(description="SHA-256 of this entry (INT-016 AuditEntry.entry_hash).")


class SecurityEventCategory(enum.StrEnum):
    """Security signal families, one per named signal in files/10 §5."""

    FAILED_LOGIN = "failed_login"
    OTP_ANOMALY = "otp_anomaly"
    IMPOSSIBLE_TRAVEL = "impossible_travel"
    NEW_DEVICE_LOGIN = "new_device_login"
    TOKEN_REUSE = "token_reuse"  # noqa: S105 — a signal family name, not a credential
    WAF_BLOCK = "waf_block"
    ADMIN_ACTION = "admin_action"
    BREAK_GLASS = "break_glass"
    CONSENT_SCOPE_DENIAL = "consent_scope_denial"
    EGRESS_DENIAL = "egress_denial"
    INJECTION_SUSPECTED = "injection_suspected"
    POLICYGUARD_SPIKE = "policyguard_spike"
    INTEGRITY_FAILURE = "integrity_failure"


class SecurityV1(FrozenModel):
    """One security event, separated from application logs (files/10 §2).
    Every value is id-shaped — structured JSON with ids only (files/10 §2,
    §5 Logging; invariant 6): narrative has no carrier here."""

    schema_id: Literal["intake.clinical.security.v1"] = Field(
        default="intake.clinical.security.v1",
        description="Versioned event id per the TS schemaId convention.",
    )
    category: SecurityEventCategory = Field(description="Signal family (files/10 §5 signals list).")
    tenant_id: uuid.UUID | None = Field(
        default=None,
        description="Owning tenant when tenant-scoped; None for platform-level events "
        "(files/10 §6 tenant_id propagation).",
    )
    actor_ref: Ref | None = Field(
        default=None,
        description="Acting principal id when one exists (files/10 §5: admin actions, "
        "break-glass per actor); None for e.g. integrity failures.",
    )
    resource_ref: Ref | None = Field(
        default=None,
        description="Affected resource id when one exists (files/10 §5).",
    )
    correlation_id: Ref = Field(
        description="Correlation id linking the event to its trace/log context "
        "(files/10 §5 Logging: correlation ids; files/08 §8 SafeError "
        "{error_code, correlation_id})."
    )
    attributes: dict[str, Ref] = Field(
        default_factory=dict,
        description="Additional context as id-shaped values only — the value type "
        "enforces the ids-only logging rule (files/10 §2; invariant 6).",
    )


EVENT_MODELS: dict[str, type[FrozenModel]] = {
    "intake.clinical.csat.v1": CsatV1,
    "intake.clinical.nps.v1": NpsV1,
    "intake.clinical.clinician_pulse.v1": ClinicianPulseV1,
    "intake.clinical.wait.v1": WaitV1,
    "intake.clinical.audit.v1": AuditV1,
    "intake.clinical.security.v1": SecurityV1,
}
"""Registry keyed by schema id — the event set of the INT-031 acceptance."""
