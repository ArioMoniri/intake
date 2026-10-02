"""The resolver: ``role → (provider, model)``, and sessions (INT-428, ADR-035).

**Identity, not address.** :class:`SelfHostedHealth` does not call a lane
healthy because something answers at its URL — a loopback tunnel answers from
anywhere. It asks the endpoint who it is (``GET /identity`` →
``{model_id, revision, weights_manifest_sha256}``) and the lane is healthy
only when that identity is the attested registry model the role resolved to.
A call-time failure or a per-call identity mismatch quarantines the lane for a
cooldown.

**Roles, providers, models.** Every decision is made for a role — a lane
(``llm``) or a dotted use of one (``llm.council.chair``) — and resolved to a
provider *and a model* (:class:`ModelAssignment`). :class:`ModelResolver` is
that seam as a Protocol, ``role → (provider, model)``, the interface other
services (INT-430) call; :class:`LaneRouter` implements it, and returns only
attested registry components or allow-listed dated snapshots.

**Fixed per session.** :class:`SessionLanes` freezes each role's first
assignment for the session: a console switch or a GPU that recovers changes
the *next* session, never the running one, and a frozen assignment that stops
being admissible is a refusal — never a different provider (a PHI session
falls back to typed/scripted mode).

**Unrepresentable.** A :class:`ModelAssignment` refuses to be constructed with
a hosted route for a real-PHI deployment, and :attr:`ModelAssignment.
clinical_evidence` is false for every synthetic or hosted run (files/04 §8.3).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from intake_platform.egress import DataClass
from intake_platform.model_lanes.guard import effective_data_class
from intake_platform.model_lanes.health import LaneRefused, SelfHostedHealth
from intake_platform.model_lanes.hosted import HostedLanes
from intake_platform.model_lanes.keys import ProviderKeyVault
from intake_platform.model_lanes.model import (
    Lane,
    LaneRoute,
    LaneSetting,
    ModelLanesControl,
    ModelRole,
    ProviderId,
    RouteKind,
    TenantDataClass,
    parse_role,
)
from intake_platform.model_lanes.models import ModelCatalogue, ModelRef, ModelSelectionRefused
from intake_platform.model_lanes.qualifications import QualificationRegistry
from intake_platform.model_lanes.routing import RouteDecision, decide_route, hosted_block
from intake_platform.model_lanes.store import ModelLanesReader, ModelLanesUnavailable

if TYPE_CHECKING:
    from intake_platform.model_lanes.spend import HostedSpendGate

__all__ = [
    "LaneRouter",
    "ModelAssignment",
    "ModelResolver",
    "SessionLanes",
    "target_role",
]


@dataclass(frozen=True)
class ModelAssignment:
    """Who serves one role right now: the route, the provider and the model."""

    role: ModelRole
    available: bool
    reason: str
    route: LaneRoute | None
    model: ModelRef | None
    data_class: TenantDataClass
    fallback: bool = False
    egress_data_class: DataClass | None = None
    #: Whether this exact model version has green red-flag extraction goldens
    #: and negation-set runs recorded (or the lane is ungated).
    qualified: bool = False

    def __post_init__(self) -> None:
        hosted = self.route is not None and self.route.kind is RouteKind.HOSTED
        if hosted and self.data_class is not TenantDataClass.SYNTHETIC:
            raise TypeError("a hosted lane is unrepresentable for a real_phi deployment")
        if hosted and self.egress_data_class is not DataClass.NON_PERSONAL:
            raise TypeError("a hosted lane carries synthetic, non-personal data only")
        if self.available != (self.route is not None):
            raise TypeError("an assignment is available exactly when it has a route")

    @property
    def lane(self) -> Lane:
        return self.role.lane

    @property
    def provider(self) -> str | None:
        """``self_hosted`` | a provider id — or ``None`` when refused."""
        if self.route is None:
            return None
        if self.route.provider is not None:
            return self.route.provider.value
        return self.route.kind.value

    @property
    def clinical_evidence(self) -> bool:
        """Whether a run on this assignment may count as files/04 §8.3
        evidence: only a qualified self-hosted model serving a real-PHI
        deployment. A synthetic or a hosted run never does."""
        return (
            self.available
            and self.data_class is TenantDataClass.REAL_PHI
            and self.route is not None
            and self.route.kind is RouteKind.SELF_HOSTED
            and self.qualified
        )

    @classmethod
    def refused(cls, role: ModelRole, reason: str, data_class: TenantDataClass) -> ModelAssignment:
        return cls(role, False, reason, None, None, data_class)


class ModelResolver(Protocol):
    """``role → (provider, model)`` — the seam other services call.

    ``role`` is ``llm`` | ``asr`` | ``tts`` or a dotted role under one
    (``llm.council.chair``); a role with no setting of its own inherits its
    lane's. ``tenant_id`` selects the INT-182 kill switch; ``None`` reads none.
    An assignment that is ``available`` has already cleared every gate: the
    ADR-035 guard, both kill switches, the provider's deployment, allow-list
    row and key, the model allow-list or attestation and the self-hosted
    identity. A caller never re-derives any of them.
    """

    def resolve(self, role: str, *, tenant_id: str | None) -> ModelAssignment: ...


class LaneRouter:
    """Facts in, :class:`ModelAssignment` out. Implements :class:`ModelResolver`."""

    def __init__(
        self,
        *,
        store: ModelLanesReader,
        hosted: HostedLanes,
        models: ModelCatalogue,
        keys: ProviderKeyVault | None,
        qualifications: QualificationRegistry,
        declared: TenantDataClass,
        health: SelfHostedHealth,
        kill_switch: Callable[[str], bool] | None = None,
        spend: HostedSpendGate | None = None,
    ) -> None:
        #: INT-439: the monthly elective cap every hosted call is charged
        #: against. ``None`` refuses every hosted call (fail closed).
        self.spend = spend
        self.store = store
        self.hosted = hosted
        self.models = models
        self.keys = keys
        self.qualifications = qualifications
        self.declared = declared
        self.health = health
        self._kill_switch = kill_switch

    # -- facts --------------------------------------------------------------------------

    def control(self) -> ModelLanesControl:
        try:
            return self.store.read()
        except ModelLanesUnavailable:
            return ModelLanesControl.unconfigured()

    def data_class(self, control: ModelLanesControl | None = None) -> TenantDataClass:
        bound = (control if control is not None else self.control()).data_class
        return effective_data_class(self.declared, bound)

    def provider_block(self, provider: ProviderId) -> str | None:
        info = self.hosted.info(provider)
        if info is None:
            return "hosted_not_in_deployment"
        if not info.listed:
            return "hosted_egress_not_listed"
        if self.keys is None or provider not in self.hosted.backends:
            return "hosted_key_store_unconfigured"
        status = self.keys.status(provider)
        if status.state == "unknown":
            return "hosted_key_store_unavailable"
        return None if status.is_set else "hosted_key_not_set"

    def tenant_kill_switch(self, tenant_id: str | None) -> bool:
        if tenant_id is None or self._kill_switch is None:
            return False
        try:
            return self._kill_switch(tenant_id)
        except Exception:
            # an unreadable kill switch reads as engaged: hosted lanes stop
            return True

    def expected_self_hosted(
        self, role: ModelRole, setting: LaneSetting, data_class: TenantDataClass
    ) -> ModelRef | None:
        """The attested self-hosted model this role would run, or ``None``."""
        key = setting.model if setting.parsed_route.kind is RouteKind.SELF_HOSTED else None
        try:
            return self.models.self_hosted_model(role.lane, key, data_class)
        except ModelSelectionRefused:
            return None

    # -- decisions ----------------------------------------------------------------------

    def decide(self, role: ModelRole | Lane, *, tenant_id: str | None) -> RouteDecision:
        """The route only — the decision table's answer."""
        target = ModelRole.of(role) if isinstance(role, Lane) else role
        control = self.control()
        return self._decide(target, control, self.data_class(control), tenant_id)

    def _decide(
        self,
        role: ModelRole,
        control: ModelLanesControl,
        data_class: TenantDataClass,
        tenant_id: str | None,
    ) -> RouteDecision:
        expected = self.expected_self_hosted(role, control.setting_for(role), data_class)
        return decide_route(
            role,
            control,
            data_class=data_class,
            self_hosted_healthy=self.health.healthy(role.lane, expected),
            provider_block=self.provider_block,
            tenant_kill_switch=self.tenant_kill_switch(tenant_id),
        )

    def resolve(self, role: str, *, tenant_id: str | None) -> ModelAssignment:
        """:class:`ModelResolver`. An unparseable role is a :class:`LaneRefused`."""
        return self.assign(target_role(role), tenant_id=tenant_id)

    def assign(self, role: ModelRole, *, tenant_id: str | None) -> ModelAssignment:
        control = self.control()
        data_class = self.data_class(control)
        decision = self._decide(role, control, data_class, tenant_id)
        serving = decision.serving
        if serving is None:
            return ModelAssignment.refused(role, decision.reason, data_class)
        setting = control.setting_for(role)
        try:
            if serving.kind is RouteKind.SELF_HOSTED:
                model = self.expected_self_hosted(role, setting, data_class)
                if model is None:  # pragma: no cover - an unattested lane is never healthy
                    raise ModelSelectionRefused("no_attested_model")
            else:
                provider = serving.provider
                if provider is None:  # pragma: no cover - LaneRoute refuses this
                    raise ModelSelectionRefused("model_not_allowed")
                key = setting.fallback_model if decision.fallback else setting.model
                model = self.models.hosted_model(provider, role.lane, key)
        except ModelSelectionRefused as refusal:
            return ModelAssignment.refused(role, refusal.code, data_class)
        qualified = self.qualifications.qualified(role.lane, model)
        if data_class is TenantDataClass.REAL_PHI and not qualified:
            # a real patient's lane runs only a model whose exact version has
            # green red-flag extraction goldens and negation-set runs
            return ModelAssignment.refused(role, "model_not_qualified", data_class)
        return ModelAssignment(
            role,
            True,
            decision.reason,
            serving,
            model,
            data_class,
            fallback=decision.fallback,
            egress_data_class=decision.egress_data_class,
            qualified=qualified,
        )

    def readmit(self, frozen: ModelAssignment, *, tenant_id: str | None) -> str | None:
        """Whether a session's frozen assignment may still serve: ``None``, or
        the refusal code. Never a different route or model."""
        control = self.control()
        data_class = self.data_class(control)
        route, model = frozen.route, frozen.model
        if route is None or model is None:
            return frozen.reason
        if data_class is not frozen.data_class:
            return "session_data_class_changed"
        if route.kind is RouteKind.SELF_HOSTED:
            try:
                current = self.models.self_hosted_model(frozen.lane, model.key, data_class)
            except ModelSelectionRefused:
                return "session_model_withdrawn"
            if current != model:
                return "session_model_withdrawn"
            if not self.health.healthy(frozen.lane, model):
                return "self_hosted_unhealthy"
        else:
            provider = route.provider
            if provider is None:  # pragma: no cover - LaneRoute refuses this
                return "session_model_withdrawn"
            code, _ = hosted_block(
                provider,
                control=control,
                data_class=data_class,
                provider_block=self.provider_block,
                tenant_kill_switch=self.tenant_kill_switch(tenant_id),
            )
            if code is not None:
                return code
            try:
                current = self.models.hosted_model(provider, frozen.lane, model.model_id)
            except ModelSelectionRefused:
                return "session_model_withdrawn"
            if current != model:
                return "session_model_withdrawn"
        if data_class is TenantDataClass.REAL_PHI and not self.qualifications.qualified(
            frozen.lane, model
        ):
            return "model_not_qualified"
        return None


class SessionLanes:
    """One session's frozen assignments (both reviews: the lane is fixed at
    session start). The first resolution of a role — available or not — is
    the session's answer for that role."""

    def __init__(self, router: LaneRouter, *, tenant_id: str | None) -> None:
        self._router = router
        self._tenant_id = tenant_id
        self._pins: dict[str, ModelAssignment] = {}

    @property
    def router(self) -> LaneRouter:
        return self._router

    @property
    def tenant_id(self) -> str | None:
        return self._tenant_id

    def pinned(self, role: str | ModelRole | Lane) -> ModelAssignment | None:
        return self._pins.get(target_role(role).id)

    def resolve(self, role: str | ModelRole | Lane) -> ModelAssignment:
        target = target_role(role)
        frozen = self._pins.get(target.id)
        if frozen is None:
            first = self._router.assign(target, tenant_id=self._tenant_id)
            self._pins[target.id] = first
            return first
        if not frozen.available:
            return frozen
        code = self._router.readmit(frozen, tenant_id=self._tenant_id)
        if code is None:
            return frozen
        return ModelAssignment.refused(target, code, frozen.data_class)


def target_role(role: str | ModelRole | Lane) -> ModelRole:
    """A role from its id, a :class:`ModelRole` or a bare lane — or refuse."""
    if isinstance(role, Lane):
        return ModelRole.of(role)
    if isinstance(role, ModelRole):
        return role
    try:
        return parse_role(role)
    except ValueError:
        raise LaneRefused("model_role_unknown") from None
