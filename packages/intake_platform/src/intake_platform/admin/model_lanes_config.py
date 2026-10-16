"""Resolving a requested lane setting for a ceremony (INT-428, ADR-035).

:func:`resolve_setting` admits a setting's hosted providers (the ADR-035
guard), resolves its models against the dated-snapshot allow-list or the
attested registry, applies the swap gate (:func:`require_qualified`) and
returns what the approver's brief shows — versions, pins, qualifying eval run
ids — with a ``config_hash`` over all of it. The governor computes it when a
switch is requested and again when it is approved; a different hash is a
different decision.
"""

from __future__ import annotations

import hashlib
import json

from intake_platform.admin.model_lanes_refusals import ModelLanesGovernanceRefused
from intake_platform.model_lanes import (
    HostedLaneRefused,
    Lane,
    LaneRouter,
    LaneSetting,
    ModelRef,
    ModelSelectionRefused,
    RouteKind,
    TenantDataClass,
    check_hosted_permitted,
)

__all__ = ["require_qualified", "resolve_setting"]


def require_qualified(router: LaneRouter, lane: Lane, ref: ModelRef | None) -> str:
    """The swap gate. Returns the qualifying run ids ('' on an ungated lane)."""
    qualifications = router.qualifications
    if not qualifications.gated(lane):
        return ""
    row = qualifications.qualification(lane, ref)
    if row is None:
        raise ModelLanesGovernanceRefused(code="model_not_qualified")
    return row.run_ids


def resolve_setting(
    router: LaneRouter, lane: Lane, setting: LaneSetting, data_class: TenantDataClass
) -> dict[str, str]:
    """Admit and resolve the setting's models, or refuse. Returns what the
    brief shows of them and the ``config_hash`` the approval re-checks."""
    route = setting.parsed_route
    models = router.models
    resolved: list[tuple[str, ModelRef, str]] = []
    try:
        for provider in (p for p in (route.provider, setting.fallback) if p is not None):
            check_hosted_permitted(data_class=data_class, provider=provider)
        if route.kind is RouteKind.HOSTED and route.provider is not None:
            ref = models.hosted_model(route.provider, lane, setting.model)
            resolved.append(("model", ref, require_qualified(router, lane, ref)))
        else:
            ref = models.self_hosted_model(lane, setting.model, data_class)
            resolved.append(("model", ref, require_qualified(router, lane, ref)))
        if setting.fallback is not None:
            fb = models.hosted_model(setting.fallback, lane, setting.fallback_model)
            resolved.append(("fallback_model", fb, require_qualified(router, lane, fb)))
    except HostedLaneRefused as refusal:
        raise ModelLanesGovernanceRefused(code=refusal.code) from None
    except ModelSelectionRefused as refusal:
        raise ModelLanesGovernanceRefused(code=refusal.code) from None
    shown: dict[str, str] = {}
    hashed: list[dict[str, str]] = [setting.model_dump(mode="json")]
    for name, ref, runs in resolved:
        shown[f"{name}_version"] = ref.version
        shown[f"{name}_pin"] = ref.sha256 or ref.wire
        if runs:
            shown[f"{name}_eval_runs"] = runs
        hashed.append(
            {"model_id": ref.model_id, "version": ref.version, "pin": shown[f"{name}_pin"]}
            | {"runs": runs}
        )
    canonical = json.dumps(hashed, sort_keys=True, separators=(",", ":"))
    shown["config_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return shown
