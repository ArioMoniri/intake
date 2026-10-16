"""The model-lane control record (INT-428, ADR-035).

Three lanes — ``llm``, ``asr``, ``tts`` — each routed to one of two kinds of
backend, spelled on the wire as:

- ``self_hosted`` — a model from the attested self-hosting registry
  (files/03 §4.9.1; invariant 19's state);
- ``hosted:<provider>`` — a hosted provider from the closed
  :class:`ProviderId` vocabulary, which exists only in the synthetic
  deployment's image (ADR-035).

There is no ``mock`` route: a lane with no model is not a lane an operator may
select (invariant 17; AI/ML review). CI and the no-GPU dev path keep their
recorded gateways as the *self-hosted* backend, configured by environment,
never by the console.

A lane may name a hosted ``fallback`` provider, which serves only while the
self-hosted lane is unhealthy, only for a synthetic deployment, and never
mid-session (:class:`~intake_platform.model_lanes.router.SessionLanes`).

Each lane also picks a **model** (owner extension, 2 Oct 2026): a key into the
provider's dated-snapshot allow-list or the attested self-hosting registry
(:mod:`intake_platform.model_lanes.models`), or ``None`` for the lane default.

**Roles.** A lane is a *kind* of model; a role is a use of one. The three
lanes are themselves roles (``llm``, ``asr``, ``tts``); any other role is a
dotted id under a lane — ``llm.council.chair`` — which inherits its lane's
setting until the console gives it one of its own. That is the generic
"role → (provider, model)" seam other services resolve through
(:class:`~intake_platform.model_lanes.router.ModelResolver`).

The record is one document for the deployment, revisioned, written only by the
admin console behind the ``DangerousAction`` registry. No record reads as
:meth:`ModelLanesControl.unconfigured`: every lane self-hosted, no fallback.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "LANES",
    "MAX_ROLES",
    "Lane",
    "LaneRoute",
    "LaneSetting",
    "ModelLanesChange",
    "ModelLanesControl",
    "ModelLanesRefused",
    "ModelRole",
    "ClipVendor",
    "KeyHolder",
    "ProviderId",
    "RouteKind",
    "TenantDataClass",
    "parse_lane",
    "parse_model_key",
    "parse_provider",
    "parse_role",
    "parse_route",
    "require_bound_class",
]

_SUBJECT: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$")
_ROLE: Final = re.compile(r"^(llm|asr|tts)(\.[a-z0-9][a-z0-9_-]{0,31}){0,3}$")
_MODEL_KEY: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:-]{0,191}$")
#: A ceiling on configured roles: the control is one record, read per call.
MAX_ROLES: Final = 64


class ModelLanesRefused(ValueError):
    """A value the control will not hold. ``code`` reaches an HTTP body and
    never echoes the submitted value (invariant 6)."""

    code = "model_lanes_refused"

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Lane(enum.StrEnum):
    LLM = "llm"
    ASR = "asr"
    TTS = "tts"


#: Every lane, in the order the console renders them.
LANES: Final[tuple[Lane, ...]] = (Lane.LLM, Lane.ASR, Lane.TTS)


class RouteKind(enum.StrEnum):
    SELF_HOSTED = "self_hosted"
    HOSTED = "hosted"


class ProviderId(enum.StrEnum):
    """Hosted providers the synthetic image can reach. Closed on purpose: a
    provider is a catalogue row, an egress allow-list row and an ADR-035
    question, so a new one is a reviewed change — never a typed string."""

    OPENAI = "openai"


class ClipVendor(enum.StrEnum):
    """Hosted vendors of scripted-clip speech (INT-443, ADR-035), synthetic
    image only. Not a model lane: a clip vendor speaks the server's scripted
    catalogue and nothing else, so it has no catalogue row, no lane default
    and no route a console can switch to. Its key sits beside the providers'
    (``model-lanes/providers/<vendor>``) and is read the same way."""

    ELEVENLABS = "elevenlabs"


#: Whose key the provider-key vault holds.
KeyHolder = ProviderId | ClipVendor


class TenantDataClass(enum.StrEnum):
    """A deployment's declared data class (ADR-035). See
    :mod:`intake_platform.model_lanes.guard` for how it is read and bound."""

    SYNTHETIC = "synthetic"
    REAL_PHI = "real_phi"


class ModelLanesChange(enum.StrEnum):
    """What the last write did; also the ``control`` label of the console
    metric ``admin_model_lane_changes_total``."""

    ROUTE_SWITCH = "route_switch"
    SELF_HOSTED_ENGAGE = "self_hosted_engage"
    HOSTED_DISABLE = "hosted_disable"
    HOSTED_RELEASE = "hosted_release"
    KEY_SET = "key_set"


@dataclass(frozen=True)
class LaneRoute:
    """One route, parsed. ``provider`` is set exactly for ``hosted``."""

    kind: RouteKind
    provider: ProviderId | None = None

    def __post_init__(self) -> None:
        if (self.kind is RouteKind.HOSTED) != (self.provider is not None):
            raise ModelLanesRefused("model_lanes_route_malformed")

    @property
    def wire(self) -> str:
        if self.kind is RouteKind.HOSTED and self.provider is not None:
            return f"{RouteKind.HOSTED.value}:{self.provider.value}"
        return self.kind.value

    @property
    def provider_label(self) -> str:
        """The ``provider`` metric label: the provider id, or ``none``."""
        return self.provider.value if self.provider is not None else "none"

    @classmethod
    def self_hosted(cls) -> LaneRoute:
        return cls(RouteKind.SELF_HOSTED)

    @classmethod
    def hosted(cls, provider: ProviderId) -> LaneRoute:
        return cls(RouteKind.HOSTED, provider)


@dataclass(frozen=True)
class ModelRole:
    """A use of a lane: the lane itself (``llm``) or a dotted role under it
    (``llm.council.chair``)."""

    id: str
    lane: Lane

    @property
    def is_lane(self) -> bool:
        return self.id == self.lane.value

    @classmethod
    def of(cls, lane: Lane) -> ModelRole:
        return cls(lane.value, lane)


def parse_lane(value: object) -> Lane:
    try:
        return Lane(value if isinstance(value, str) else "")
    except ValueError:
        raise ModelLanesRefused("model_lanes_lane_unknown") from None


def parse_provider(value: object) -> ProviderId:
    try:
        return ProviderId(value if isinstance(value, str) else "")
    except ValueError:
        raise ModelLanesRefused("model_lanes_provider_unknown") from None


def parse_role(value: object) -> ModelRole:
    """``llm`` | ``asr`` | ``tts``, optionally with up to three dotted id
    segments — nothing else."""
    if not isinstance(value, str) or _ROLE.match(value) is None:
        raise ModelLanesRefused("model_role_unknown")
    return ModelRole(value, Lane(value.split(".", 1)[0]))


def parse_model_key(value: object) -> str | None:
    """A model selection key's shape: ``None`` (the default) or an id."""
    if value is None:
        return None
    if not isinstance(value, str) or _MODEL_KEY.match(value) is None:
        raise ModelLanesRefused("model_key_malformed")
    return value


def parse_route(value: object) -> LaneRoute:
    """``self_hosted`` | ``hosted:<provider>`` — nothing else, ``mock`` included."""
    if not isinstance(value, str):
        raise ModelLanesRefused("model_lanes_route_unknown")
    if value == RouteKind.SELF_HOSTED.value:
        return LaneRoute.self_hosted()
    kind, sep, provider = value.partition(":")
    if kind != RouteKind.HOSTED.value or not sep:
        raise ModelLanesRefused("model_lanes_route_unknown")
    return LaneRoute.hosted(parse_provider(provider))


class LaneSetting(BaseModel):
    """One lane's (or role's) configuration: route, model, hosted fallback."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    route: str = RouteKind.SELF_HOSTED.value
    fallback: ProviderId | None = None
    #: The selected model for ``route`` (``None`` = the lane default), and for
    #: the fallback provider. Checked against the catalogue when a switch is
    #: requested, when it is approved, and on every call.
    model: str | None = None
    fallback_model: str | None = None

    @field_validator("route")
    @classmethod
    def _route(cls, value: str) -> str:
        return parse_route(value).wire

    @field_validator("model", "fallback_model")
    @classmethod
    def _model_key(cls, value: str | None) -> str | None:
        return parse_model_key(value)

    @property
    def parsed_route(self) -> LaneRoute:
        return parse_route(self.route)

    @model_validator(mode="after")
    def _fallback_only_behind_self_hosted(self) -> Self:
        # A fallback is what serves while the GPU lane is down. On a lane that
        # is not self-hosted it would never be read, and a setting nothing
        # reads is a setting somebody believes is doing something.
        if self.fallback is not None and self.parsed_route.kind is not RouteKind.SELF_HOSTED:
            raise ValueError("a hosted fallback is only meaningful behind a self_hosted route")
        if self.fallback_model is not None and self.fallback is None:
            raise ValueError("a fallback model needs a fallback provider")
        return self


def _all_self_hosted() -> dict[Lane, LaneSetting]:
    return {lane: LaneSetting() for lane in LANES}


class ModelLanesControl(BaseModel):
    """The deployment's model-lane control (one record, revisioned)."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_assignment=True, hide_input_in_errors=True
    )

    schema_version: Literal[1] = 1
    lanes: dict[Lane, LaneSetting] = Field(default_factory=_all_self_hosted)
    #: Roles with a setting of their own (``llm.council.chair`` …). A role
    #: absent here inherits its lane's setting.
    roles: dict[str, LaneSetting] = Field(default_factory=dict)
    #: The lanes' own kill switch: while engaged no hosted provider serves any
    #: lane, as a configured route or as a fallback.
    hosted_disabled: bool = False
    #: The deployment's data class, bound by the first write and never changed
    #: by a later one — the stores refuse it (medical review, finding 12: the
    #: synthetic flag is immutable). A declaration that disagrees reads as
    #: ``real_phi`` (:func:`~intake_platform.model_lanes.guard.effective_data_class`).
    data_class: TenantDataClass | None = None
    revision: int = Field(default=0, ge=0, strict=True)
    changed_at: datetime | None = None
    changed_by: str | None = None
    approved_by: str | None = None
    last_change: ModelLanesChange | None = None

    @field_validator("changed_by", "approved_by")
    @classmethod
    def _subject(cls, value: str | None) -> str | None:
        if value is not None and _SUBJECT.match(value) is None:
            raise ValueError("an actor is an id-shaped subject, never a name")
        return value

    @model_validator(mode="after")
    def _every_lane(self) -> Self:
        if set(self.lanes) != set(LANES):
            raise ValueError("the control names every lane exactly once")
        if len(self.roles) > MAX_ROLES:
            raise ValueError("too many configured roles")
        for role_id in self.roles:
            if parse_role(role_id).is_lane:
                raise ValueError("a lane's own setting lives under lanes, not roles")
        return self

    @classmethod
    def unconfigured(cls) -> ModelLanesControl:
        """Every lane self-hosted, no fallback, nothing hosted — invariant 19."""
        return cls()

    def setting(self, lane: Lane) -> LaneSetting:
        return self.lanes[lane]

    def setting_for(self, role: ModelRole) -> LaneSetting:
        """The role's own setting, else its lane's."""
        if role.is_lane:
            return self.lanes[role.lane]
        return self.roles.get(role.id, self.lanes[role.lane])

    def with_role(
        self, role: ModelRole, setting: LaneSetting
    ) -> tuple[dict[Lane, LaneSetting], dict[str, LaneSetting]]:
        """``(lanes, roles)`` with ``role`` set to ``setting``."""
        if role.is_lane:
            return {**self.lanes, role.lane: setting}, dict(self.roles)
        return dict(self.lanes), {**self.roles, role.id: setting}


def require_bound_class(current: ModelLanesControl, new: ModelLanesControl) -> None:
    """The stores' transition rule: a bound data class never changes."""
    if current.data_class is not None and new.data_class is not current.data_class:
        raise ModelLanesRefused("model_lanes_data_class_bound")
