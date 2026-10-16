"""Pinning a member to a model: once per session, fail closed, PHI-path aware.

The model behind a member is INT-428's decision (ADR-035): the lane router resolves the
role ``llm.council.<member_id>`` to a route and a model. INT-428 was not on
``origin/main`` when this landed, so the verifier reads it through
:class:`MemberResolver`, a structural port shaped after INT-428's
``ModelResolver.resolve(role, *, tenant_id)``. Binding the real router is one
adapter in the composition root once INT-428 merges (ADR-036, split row).

**What this module refuses, and where.**

- A ``mock`` route is not a member at all. :class:`RouteKind` has no such
  member, so :func:`pin_member` cannot return one (CLAUDE.md invariant 17;
  the AI/ML review: *"mock is not an admin option"*).
- On a real-PHI deployment a hosted member is unrepresentable:
  :func:`pin_member` returns a :class:`SelfHostedMember` there or raises, and
  :class:`HostedSyntheticMember` carries the synthetic data class as a
  literal it cannot be constructed without. There is no transfer-basis
  escape hatch (medical review §12; AI/ML review "the DPA branch is deleted").
- An unset deployment data class reads as real PHI — the INT-428 rule.
- A member is pinned once, at session start (:class:`SessionPins`). A
  resolver that later answers with another model is drift, and drift
  refuses rather than switching mid-session (AI/ML review: *"no mid-session
  flapping"*).
- A pinned member whose :class:`~.policy.LaneBinding` digest differs from the
  one the policy was calibrated against is refused: a threshold calibrated on
  one model is not a threshold for another.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Protocol

from intake_voice_runtime.clinical_agent.council.policy import (
    LaneBinding,
    VerifierPolicy,
)

__all__ = [
    "ENV_DEPLOYMENT_DATA_CLASS",
    "DeploymentDataClass",
    "HostedSyntheticMember",
    "MemberAssignment",
    "MemberRefused",
    "MemberResolver",
    "PinnedMember",
    "RefusalCode",
    "RouteKind",
    "SelfHostedMember",
    "SessionPins",
    "binding_of",
    "deployment_data_class",
    "pin_member",
]

ENV_DEPLOYMENT_DATA_CLASS: Final = "INTAKE_DEPLOYMENT_DATA_CLASS"


class DeploymentDataClass(enum.StrEnum):
    SYNTHETIC = "synthetic"
    REAL_PHI = "real_phi"


class RouteKind(enum.StrEnum):
    """The routes a member may run on. ``mock`` is deliberately absent."""

    SELF_HOSTED = "self_hosted"
    HOSTED = "hosted"


class RefusalCode(enum.StrEnum):
    UNAVAILABLE = "unavailable"
    UNKNOWN_ROUTE = "unknown_route"
    HOSTED_ON_PHI_DEPLOYMENT = "hosted_on_phi_deployment"
    UNPINNED_MODEL = "unpinned_model"
    BINDING_MISMATCH = "binding_mismatch"
    PIN_DRIFT = "pin_drift"


class MemberRefused(RuntimeError):
    """A member cannot be pinned or used. Carries a closed code, nothing else."""

    def __init__(self, code: RefusalCode, member_id: str) -> None:
        super().__init__(f"council member {member_id!r} refused: {code.value}")
        self.code = code
        self.member_id = member_id


@dataclass(frozen=True, slots=True)
class MemberAssignment:
    """What a lane router answers for one role — raw, before any judgement."""

    role_id: str
    available: bool
    route_kind: str
    provider: str | None
    model_id: str | None
    revision: str | None
    weights_sha256: str | None


class MemberResolver(Protocol):
    def resolve(self, role: str, *, tenant_id: str | None) -> MemberAssignment: ...


@dataclass(frozen=True, slots=True)
class SelfHostedMember:
    member_id: str
    provider: str
    model_id: str
    revision: str
    weights_sha256: str
    route_kind: Literal[RouteKind.SELF_HOSTED] = RouteKind.SELF_HOSTED


@dataclass(frozen=True, slots=True)
class HostedSyntheticMember:
    """A hosted member. It exists only on a synthetic deployment."""

    member_id: str
    provider: str
    model_id: str
    revision: str
    weights_sha256: str
    deployment: Literal[DeploymentDataClass.SYNTHETIC]
    route_kind: Literal[RouteKind.HOSTED] = RouteKind.HOSTED


type PinnedMember = SelfHostedMember | HostedSyntheticMember


def deployment_data_class(env: Mapping[str, str]) -> DeploymentDataClass:
    """Unset, or anything but ``synthetic``, reads as real PHI (fail closed)."""
    if env.get(ENV_DEPLOYMENT_DATA_CLASS) == DeploymentDataClass.SYNTHETIC.value:
        return DeploymentDataClass.SYNTHETIC
    return DeploymentDataClass.REAL_PHI


def pin_member(
    member_id: str, assignment: MemberAssignment, *, deployment: DeploymentDataClass
) -> PinnedMember:
    """Judge one assignment. Returns a pinned member or raises :class:`MemberRefused`."""
    if not assignment.available:
        raise MemberRefused(RefusalCode.UNAVAILABLE, member_id)
    try:
        kind = RouteKind(assignment.route_kind)
    except ValueError:
        raise MemberRefused(RefusalCode.UNKNOWN_ROUTE, member_id) from None
    provider, model_id = assignment.provider, assignment.model_id
    revision, weights = assignment.revision, assignment.weights_sha256
    if not (provider and model_id and revision and weights):
        raise MemberRefused(RefusalCode.UNPINNED_MODEL, member_id)
    if kind is RouteKind.SELF_HOSTED:
        return SelfHostedMember(
            member_id=member_id,
            provider=provider,
            model_id=model_id,
            revision=revision,
            weights_sha256=weights,
        )
    if deployment is not DeploymentDataClass.SYNTHETIC:
        raise MemberRefused(RefusalCode.HOSTED_ON_PHI_DEPLOYMENT, member_id)
    return HostedSyntheticMember(
        member_id=member_id,
        provider=provider,
        model_id=model_id,
        revision=revision,
        weights_sha256=weights,
        deployment=DeploymentDataClass.SYNTHETIC,
    )


def binding_of(
    member: PinnedMember, *, prompt_version: str, temperature: str, slot_types: tuple[str, ...]
) -> LaneBinding:
    return LaneBinding(
        provider=member.provider,
        model_id=member.model_id,
        revision=member.revision,
        weights_sha256=member.weights_sha256,
        prompt_version=prompt_version,
        temperature=temperature,
        slot_types=slot_types,
    )


@dataclass(frozen=True, slots=True)
class SessionPins:
    """Every member, pinned at session start and never re-resolved silently."""

    members: Mapping[str, PinnedMember]
    tenant_id: str | None

    @classmethod
    def capture(
        cls,
        policy: VerifierPolicy,
        resolver: MemberResolver,
        *,
        tenant_id: str | None,
        deployment: DeploymentDataClass,
        prompt_version: str,
        slot_types: tuple[str, ...],
    ) -> SessionPins:
        pinned: dict[str, PinnedMember] = {}
        for spec in policy.members:
            member = pin_member(
                spec.member_id,
                resolver.resolve(spec.role_id, tenant_id=tenant_id),
                deployment=deployment,
            )
            binding = binding_of(
                member,
                prompt_version=prompt_version,
                temperature=policy.temperature,
                slot_types=slot_types,
            )
            if binding.digest != policy.bindings[spec.member_id]:
                raise MemberRefused(RefusalCode.BINDING_MISMATCH, spec.member_id)
            pinned[spec.member_id] = member
        return cls(members=MappingProxyType(pinned), tenant_id=tenant_id)

    def confirm_unchanged(
        self,
        resolver: MemberResolver,
        policy: VerifierPolicy,
        *,
        deployment: DeploymentDataClass,
    ) -> None:
        """Refuse if the router now answers any member with a different model."""
        for spec in policy.members:
            current = pin_member(
                spec.member_id,
                resolver.resolve(spec.role_id, tenant_id=self.tenant_id),
                deployment=deployment,
            )
            if current != self.members[spec.member_id]:
                raise MemberRefused(RefusalCode.PIN_DRIFT, spec.member_id)
