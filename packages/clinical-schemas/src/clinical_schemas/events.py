"""Versioned event schemas (INT-031): csat.v1, nps.v1, clinician_pulse.v1,
audit.v1, security.v1.

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
    reason: CsatReason = Field(
        description="Reason category (INT-240 reason enum; files/08 §4 group F "
        "csat.reason distribution)."
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
    "intake.clinical.audit.v1": AuditV1,
    "intake.clinical.security.v1": SecurityV1,
}
"""Registry keyed by schema id — the event set of the INT-031 acceptance."""
