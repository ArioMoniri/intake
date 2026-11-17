"""The per-tenant voice control record (INT-182; files/08 §3 "Voice runtime").

One record per tenant, holding the three levers the Voice module controls:
the kill switch, the default profile, and a canary profile with its weight.
The admin API writes it (``services/api/admin``, four-eyes where the
direction is dangerous); the voice runtime reads it at every session start.

**Only profiles that exist** (CLAUDE.md invariant 19). :class:`VoiceControlProfile`
has the two members ADR-010 settles — ``residency_tr`` and ``typed`` — and a
test holds it equal to the runtime's own ``VoiceProfile``. Parsing any other
name is refused, so no record can name a profile the runtime cannot build.

**An unconfigured tenant is typed.** :meth:`TenantVoiceControl.unconfigured`
is what a tenant with no record reads as, and its default profile is
``typed``: voice is enabled per tenant by a tier-2 profile switch, never by
the absence of a row. That is also the fail-closed answer to a store that
lost its keys — every tenant falls to the safer transport rather than to voice.

**Ids only** (invariant 6). The record carries a tenant id, closed
enumerations, integers, a timestamp and two staff subjects (who changed it,
who approved it). The change reason's free text never enters it; the audit
chain and the four-eyes brief own that. Validation errors hide their input
(files/08 §0c F12), so a malformed record cannot put its bytes into a log.
"""

from __future__ import annotations

import enum
import re
from datetime import datetime
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "CANARY_WEIGHT_MAX",
    "CANARY_WEIGHT_MIN",
    "CanaryWeightOutOfBounds",
    "TenantInvalid",
    "TenantVoiceControl",
    "UnknownVoiceProfile",
    "VoiceControlChange",
    "VoiceControlProfile",
    "VoiceControlRefused",
    "parse_canary_weight",
    "parse_profile",
    "require_tenant_id",
]

CANARY_WEIGHT_MIN: Final = 0
CANARY_WEIGHT_MAX: Final = 100

#: A tenant id is a Prometheus label value on the runtime's route counter and
#: a Redis key suffix, so it is held to the console's id shape: lowercase ids,
#: digits and ``_ . -``. A hospital's name is not a tenant id.
_TENANT_ID: Final = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
#: The staff-subject shape the console principal already enforces.
_SUBJECT: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")


class VoiceControlRefused(ValueError):
    """A value the voice control will not hold. ``code`` is machine-shaped and
    reaches an HTTP body; the refused value is never echoed (invariant 6)."""

    code = "voice_control_refused"


class UnknownVoiceProfile(VoiceControlRefused):
    code = "voice_profile_unknown"


class CanaryWeightOutOfBounds(VoiceControlRefused):
    code = "voice_canary_weight_out_of_bounds"


class TenantInvalid(VoiceControlRefused):
    code = "voice_tenant_invalid"


class VoiceControlProfile(enum.StrEnum):
    """The profiles that exist (ADR-010). There is no third."""

    RESIDENCY_TR = "residency_tr"
    TYPED = "typed"


class VoiceControlChange(enum.StrEnum):
    """Which lever moved last — and the ``control`` label's closed domain."""

    KILL_SWITCH_ENGAGE = "kill_switch_engage"
    KILL_SWITCH_RELEASE = "kill_switch_release"
    DEFAULT_PROFILE = "default_profile"
    CANARY = "canary"


def parse_profile(value: object) -> VoiceControlProfile:
    """A profile name, or a refusal. Exact match only — no case folding and no
    trimming, because ``" typed"`` accepted today is a spelling someone relies
    on tomorrow."""
    if isinstance(value, str):
        for profile in VoiceControlProfile:
            if value == profile.value:
                return profile
    raise UnknownVoiceProfile(
        "only residency_tr and typed exist (CLAUDE.md invariant 19; ADR-010); "
        "the submitted name is not echoed"
    )


def parse_canary_weight(value: object) -> int:
    """An integer percentage in 0..100, or a refusal. ``True`` is an ``int``
    in Python and ``50.0`` compares equal to 50; neither is a weight."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CanaryWeightOutOfBounds("a canary weight is an integer percentage")
    if not CANARY_WEIGHT_MIN <= value <= CANARY_WEIGHT_MAX:
        raise CanaryWeightOutOfBounds(
            f"a canary weight is bounded {CANARY_WEIGHT_MIN}..{CANARY_WEIGHT_MAX}"
        )
    return value


def require_tenant_id(value: object) -> str:
    if not isinstance(value, str) or not _TENANT_ID.fullmatch(value):
        raise TenantInvalid("a tenant id is id-shaped; the submitted value is not echoed")
    return value


class TenantVoiceControl(BaseModel):
    """One tenant's voice control. Immutable; a change is a new revision."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    schema_version: Literal[1] = 1
    tenant_id: str
    kill_switch: bool = False
    default_profile: VoiceControlProfile = VoiceControlProfile.TYPED
    canary_profile: VoiceControlProfile | None = None
    canary_weight: int = Field(
        default=CANARY_WEIGHT_MIN, ge=CANARY_WEIGHT_MIN, le=CANARY_WEIGHT_MAX, strict=True
    )
    #: 0 is "never written". Every write moves it by exactly one, which is
    #: what a four-eyes approval binds to (the approver approves the revision
    #: the brief showed them).
    revision: int = Field(default=0, ge=0, strict=True)
    changed_at: datetime | None = None
    changed_by: str | None = None
    approved_by: str | None = None
    last_change: VoiceControlChange | None = None

    @field_validator("tenant_id")
    @classmethod
    def _tenant(cls, value: str) -> str:
        return require_tenant_id(value)

    @field_validator("changed_by", "approved_by")
    @classmethod
    def _subject(cls, value: str | None) -> str | None:
        if value is not None and not _SUBJECT.fullmatch(value):
            raise ValueError("a staff subject is id-shaped")
        return value

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.canary_weight > CANARY_WEIGHT_MIN:
            if self.canary_profile is None:
                raise ValueError("a canary weight needs a canary profile")
            if self.canary_profile is self.default_profile:
                raise ValueError("a canary of the default profile routes nothing anywhere new")
        elif self.canary_profile is not None:
            raise ValueError("a canary profile at weight 0 is a canary nobody can see")
        return self

    @classmethod
    def unconfigured(cls, tenant_id: str) -> TenantVoiceControl:
        """What a tenant with no record reads as: typed, no canary, switch off."""
        return cls(tenant_id=tenant_id)

    @property
    def configured(self) -> bool:
        return self.revision > 0

    @property
    def effective_profile(self) -> VoiceControlProfile:
        """What a session routed *outside* the canary gets. The kill switch
        dominates; the canary is a share of sessions, not the tenant's state."""
        return VoiceControlProfile.TYPED if self.kill_switch else self.default_profile
