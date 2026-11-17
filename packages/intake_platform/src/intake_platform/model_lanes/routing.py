"""The routing decision table (INT-428, ADR-035).

One pure function, :func:`decide_route`, answers "which route serves this
role for this deployment right now?" from four facts: the role's configured
route and fallback, the hosted kill switches, the ADR-035 guard, and whether
the provider is ready and the self-hosted lane healthy. It does no I/O, so the
whole table is a unit test (tests/platform/test_model_lane_routing.py). The
model is resolved afterwards, by the router.

=================  ======================================  ==============================
configured         condition                               serves (or the refusal code)
=================  ======================================  ==============================
``self_hosted``    self-hosted healthy                     ``self_hosted``
``self_hosted``    unhealthy, no fallback                  ``self_hosted_unhealthy``
``self_hosted``    unhealthy, fallback admitted            ``hosted:<fallback>``
``self_hosted``    unhealthy, fallback blocked             the block's code
``hosted:<p>``     admitted                                ``hosted:<p>``
``hosted:<p>``     blocked, self-hosted healthy            ``self_hosted`` (switch-over)
``hosted:<p>``     blocked, self-hosted unhealthy          the block's code
=================  ======================================  ==============================

A hosted provider is *blocked*, checked in this order, when: the lanes' own
kill switch is engaged (``hosted_disabled``); the tenant's INT-182 voice kill
switch is engaged (``kill_switch_engaged``); the deployment is not synthetic
(``hosted_lane_real_phi_refused`` — the only answer a real-PHI deployment can
get, ADR-035); or the provider is not ready — not in this deployment's image
(``hosted_not_in_deployment``), no egress allow-list row
(``hosted_egress_not_listed``) or no key (``hosted_key_not_set``). Every
refusal is a code, never a silent default.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from intake_platform.egress import DataClass
from intake_platform.model_lanes.guard import HostedLaneRefused, check_hosted_permitted
from intake_platform.model_lanes.model import (
    Lane,
    LaneRoute,
    ModelLanesControl,
    ModelRole,
    ProviderId,
    RouteKind,
    TenantDataClass,
)

__all__ = [
    "REASON_CONFIGURED",
    "REASON_FALLBACK",
    "REASON_SELF_HOSTED_UNHEALTHY",
    "REASON_SWITCH_OVER",
    "RouteDecision",
    "decide_route",
    "hosted_block",
]

REASON_CONFIGURED: Final = "configured"
REASON_FALLBACK: Final = "self_hosted_unhealthy_fallback"
REASON_SWITCH_OVER: Final = "hosted_blocked_self_hosted"
REASON_SELF_HOSTED_UNHEALTHY: Final = "self_hosted_unhealthy"


@dataclass(frozen=True)
class RouteDecision:
    """The answer for one role. ``serving is None`` means: refuse the call."""

    role: ModelRole
    configured: LaneRoute
    serving: LaneRoute | None
    reason: str
    #: The data class the egress policy is told a hosted call carries.
    egress_data_class: DataClass | None = None

    @property
    def lane(self) -> Lane:
        return self.role.lane

    @property
    def available(self) -> bool:
        return self.serving is not None

    @property
    def fallback(self) -> bool:
        return self.reason == REASON_FALLBACK


def hosted_block(
    provider: ProviderId,
    *,
    control: ModelLanesControl,
    data_class: TenantDataClass,
    provider_block: Callable[[ProviderId], str | None],
    tenant_kill_switch: bool,
) -> tuple[str | None, DataClass | None]:
    """``(None, data_class)`` when the provider may serve, else ``(code, None)``."""
    if control.hosted_disabled:
        return "hosted_disabled", None
    if tenant_kill_switch:
        return "kill_switch_engaged", None
    try:
        permit = check_hosted_permitted(data_class=data_class, provider=provider)
    except HostedLaneRefused as refusal:
        return refusal.code, None
    readiness = provider_block(provider)
    if readiness is not None:
        return readiness, None
    return None, permit.egress_data_class


def decide_route(
    role: ModelRole,
    control: ModelLanesControl,
    *,
    data_class: TenantDataClass,
    self_hosted_healthy: bool,
    provider_block: Callable[[ProviderId], str | None],
    tenant_kill_switch: bool,
) -> RouteDecision:
    """See the module docstring's table. ``role`` reads its own setting, or
    its lane's when it has none."""
    setting = control.setting_for(role)
    configured = setting.parsed_route

    def blocked(provider: ProviderId) -> tuple[str | None, DataClass | None]:
        return hosted_block(
            provider,
            control=control,
            data_class=data_class,
            provider_block=provider_block,
            tenant_kill_switch=tenant_kill_switch,
        )

    if configured.kind is RouteKind.SELF_HOSTED:
        if self_hosted_healthy:
            return RouteDecision(role, configured, configured, REASON_CONFIGURED)
        if setting.fallback is None:
            return RouteDecision(role, configured, None, REASON_SELF_HOSTED_UNHEALTHY)
        code, egress = blocked(setting.fallback)
        if code is not None:
            return RouteDecision(role, configured, None, code)
        return RouteDecision(
            role, configured, LaneRoute.hosted(setting.fallback), REASON_FALLBACK, egress
        )

    provider = configured.provider
    if provider is None:  # pragma: no cover - LaneRoute refuses this at construction
        raise ValueError("a hosted route names its provider")
    code, egress = blocked(provider)
    if code is None:
        return RouteDecision(role, configured, configured, REASON_CONFIGURED, egress)
    if self_hosted_healthy:
        return RouteDecision(role, configured, LaneRoute.self_hosted(), REASON_SWITCH_OVER)
    return RouteDecision(role, configured, None, code)
