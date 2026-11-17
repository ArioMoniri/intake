"""Model-lane governance — one key to narrow, four eyes to widen (INT-428).

The write side of :mod:`intake_platform.model_lanes`, and files/08 §8.2's
asymmetry read off invariant 19 (ADR-035), on the same primitives every other
console control uses — INT-188's closed change reasons
(:mod:`intake_platform.admin.flag_governance`), the INT-180 four-eyes service,
the write-ahead audit — so model lanes add no second governance plane:

- **To narrow, one key.** :meth:`ModelLanesGovernor.disable_hosted` stops
  every hosted lane at once; :meth:`ModelLanesGovernor.engage_self_hosted` is
  the one-click "switch to GPU", refused unless a fresh identity probe shows
  each named lane serving its attested registry model, and — on a gated lane —
  unless that exact model version is qualified.
- **To widen, two keys.** A route-and-model switch, a provider key and
  releasing the hosted kill switch each open a tier-2 ceremony; nothing
  changes until a distinct human, credential and session approves.
- **An approval binds to what it approved.** A switch ceremony carries the
  control's revision and a ``config_hash`` over the setting, the resolved
  models (id, version, pin) and the qualifying eval run ids. The approval
  recomputes both and refuses — without spending the ceremony — if either
  moved: a catalogue edit, a re-pinned model or a withdrawn qualification in
  the fifteen minutes the ceremony waited is a different decision.
- **The swap gate** (medical review, finding 12): a switch on a gated lane
  (``llm``, ``asr``) is refused with ``model_not_qualified`` unless the exact
  model version has green red-flag extraction goldens and negation-set runs.
- **The data class is bound, never moved.** The first write binds the
  deployment's declared class into the control; every later write copies it
  (and the stores refuse one that does not).
- **The guard at the door.** A hosted route or fallback in a deployment that
  is not synthetic never becomes a pending action; a provider key cannot be
  set there at all.
- **A key never enters a ceremony.** It is staged in OpenBao under a fresh
  reference before the ceremony opens; the evidence carries the provider, the
  last four characters and the reference, and the approval promotes it.

Like the other governors this is pure rule over injected state — the
write-ahead audit row and the metric belong to the route that calls it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from intake_platform.admin.actions import (
    MODEL_LANES_CEREMONIES,
    MODEL_LANES_HOSTED_DISABLE,
    MODEL_LANES_HOSTED_RELEASE,
    MODEL_LANES_KEY_SET,
    MODEL_LANES_ROUTE_SWITCH,
    MODEL_LANES_SELF_HOSTED_ENGAGE,
    DangerousAction,
)
from intake_platform.admin.flag_governance import ChangeReasonMissing
from intake_platform.admin.four_eyes import (
    ActorBlock,
    FourEyesService,
    Justification,
    PendingAction,
    PendingActionState,
)
from intake_platform.admin.model_lanes_config import require_qualified, resolve_setting
from intake_platform.admin.model_lanes_refusals import (
    ModelLanesActionMismatch,
    ModelLanesChanged,
    ModelLanesGovernanceRefused,
    ModelLanesNothingToChange,
    ModelLanesRoleIneligible,
    SelfHostedNotHealthy,
)
from intake_platform.model_lanes import (
    KeyStatus,
    KeyVaultUnavailable,
    Lane,
    LaneRoute,
    LaneRouter,
    LaneSetting,
    ModelLanesChange,
    ModelLanesConflict,
    ModelLanesControl,
    ModelLanesStore,
    ModelRole,
    ProviderApiKey,
    ProviderId,
    ProviderKeyVault,
    RouteKind,
    TenantDataClass,
    effective_data_class,
    parse_role,
)

__all__ = [
    "LANES_PENDING_TTL",
    "ModelLanesActionMismatch",
    "ModelLanesChangeResult",
    "ModelLanesChanged",
    "ModelLanesGovernanceRefused",
    "ModelLanesGovernor",
    "ModelLanesNothingToChange",
    "ModelLanesRoleIneligible",
    "SelfHostedNotHealthy",
]

#: files/10 §2: "Actor initiates → 15-minute TTL → a different sub … approves".
LANES_PENDING_TTL: Final = timedelta(minutes=15)
CONTROL_TARGET: Final = "model-lanes:control"
_DEFAULT: Final = "default"
_NONE: Final = "none"
_SAFE_ATTEMPTS: Final = 3


@dataclass(frozen=True)
class ModelLanesChangeResult:
    control: ModelLanesControl
    changed: bool


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _require_reason(justification: Justification) -> None:
    if not justification.free_text.strip():
        raise ChangeReasonMissing("a model-lane change needs a reason (INT-188)")


def _require_actor(action: DangerousAction, actor: ActorBlock) -> None:
    if actor.role not in action.actor_roles:
        raise ModelLanesRoleIneligible(f"{actor.role.value} may not take {action.id}")


class ModelLanesGovernor:
    """See the module docstring. Every refusal is typed."""

    def __init__(
        self,
        four_eyes: FourEyesService,
        store: ModelLanesStore,
        router: LaneRouter,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._four_eyes = four_eyes
        self._store = store
        self._router = router
        self._clock = clock if clock is not None else _utc_now

    # -- tier 1: narrow ------------------------------------------------------------------

    def disable_hosted(
        self, *, actor: ActorBlock, justification: Justification
    ) -> ModelLanesChangeResult:
        _require_actor(MODEL_LANES_HOSTED_DISABLE, actor)
        _require_reason(justification)
        return self._safe_write(
            lambda current: (
                None
                if current.hosted_disabled
                else self._next(
                    current,
                    change=ModelLanesChange.HOSTED_DISABLE,
                    changed_by=actor.subject,
                    approved_by=None,
                    hosted_disabled=True,
                )
            )
        )

    def engage_self_hosted(
        self, *, actor: ActorBlock, justification: Justification, lanes: tuple[Lane, ...]
    ) -> ModelLanesChangeResult:
        """The one-click switch to GPU: every named lane routes self-hosted on
        its default attested model; a lane already self-hosted is left as it
        is. Refused unless each lane's fresh identity probe shows its attested
        model, and — on a gated lane — that model version is qualified.
        Configured roles under a lane keep their own settings."""
        _require_actor(MODEL_LANES_SELF_HOSTED_ENGAGE, actor)
        _require_reason(justification)
        if not lanes:
            raise ModelLanesGovernanceRefused(code="model_lanes_lane_unknown")
        current = self._store.read()
        data_class = self._data_class(current)
        target = LaneSetting(route=RouteKind.SELF_HOSTED.value)
        for lane in lanes:
            role = ModelRole.of(lane)
            expected = self._router.expected_self_hosted(role, target, data_class)
            if not self._router.health.healthy(lane, expected, fresh=True):
                raise SelfHostedNotHealthy(f"the {lane.value} self-hosted identity is not healthy")
            require_qualified(self._router, lane, expected)

        def apply(current: ModelLanesControl) -> ModelLanesControl | None:
            settings = dict(current.lanes)
            moved = False
            for lane in lanes:
                if settings[lane].parsed_route.kind is not RouteKind.SELF_HOSTED:
                    settings[lane] = target
                    moved = True
            if not moved:
                return None
            return self._next(
                current,
                change=ModelLanesChange.SELF_HOSTED_ENGAGE,
                changed_by=actor.subject,
                approved_by=None,
                lanes=settings,
            )

        return self._safe_write(apply)

    # -- tier 2: widen -------------------------------------------------------------------

    def open_switch(
        self,
        *,
        actor: ActorBlock,
        justification: Justification,
        role: ModelRole,
        route: LaneRoute,
        model: str | None,
        fallback: ProviderId | None,
        fallback_model: str | None,
    ) -> PendingAction:
        """Request a role's provider and model. The model must be a dated
        snapshot on the provider's allow-list (hosted) or an attested registry
        row (self-hosted), and qualified on a gated lane; ``None`` selects the
        lane default."""
        _require_actor(MODEL_LANES_ROUTE_SWITCH, actor)
        _require_reason(justification)
        try:
            setting = LaneSetting(
                route=route.wire, fallback=fallback, model=model, fallback_model=fallback_model
            )
        except ValueError:
            raise ModelLanesGovernanceRefused(code="model_lanes_setting_invalid") from None
        current = self._store.read()
        data_class = self._data_class(current)
        shown = resolve_setting(self._router, role.lane, setting, data_class)
        own = role.is_lane or role.id in current.roles
        if own and current.setting_for(role) == setting:
            raise ModelLanesNothingToChange("the role already routes this way")
        evidence = {
            "control": ModelLanesChange.ROUTE_SWITCH.value,
            "role": role.id,
            "route": route.wire,
            "model": model or _DEFAULT,
            "fallback": fallback.value if fallback is not None else _NONE,
            "fallback_model": fallback_model or _DEFAULT,
            "base_revision": str(current.revision),
            **shown,
        }
        return self._open(MODEL_LANES_ROUTE_SWITCH, actor, justification, evidence)

    def approve_switch(
        self, pending_id: str, *, approver: ActorBlock, assertion_id: str
    ) -> ModelLanesControl:
        pending = self._ceremony(pending_id, MODEL_LANES_ROUTE_SWITCH)
        current = self._bound(pending)
        evidence = pending.evidence
        role = parse_role(evidence["role"])
        setting = LaneSetting(
            route=evidence["route"],
            model=None if evidence["model"] == _DEFAULT else evidence["model"],
            fallback=None if evidence["fallback"] == _NONE else ProviderId(evidence["fallback"]),
            fallback_model=(
                None if evidence["fallback_model"] == _DEFAULT else evidence["fallback_model"]
            ),
        )
        shown = resolve_setting(self._router, role.lane, setting, self._data_class(current))
        if shown["config_hash"] != evidence["config_hash"]:
            raise ModelLanesChanged(
                "the models, pins or qualifications moved since the request",
                code="model_lanes_config_changed",
            )
        approved = self._four_eyes.approve(pending_id, approver=approver, assertion_id=assertion_id)
        lanes, roles = current.with_role(role, setting)
        updated = self._next(
            current,
            change=ModelLanesChange.ROUTE_SWITCH,
            changed_by=approved.actor.subject,
            approved_by=approver.subject,
            lanes=lanes,
            roles=roles,
        )
        return self._write_bound(updated, current.revision)

    def open_release(self, *, actor: ActorBlock, justification: Justification) -> PendingAction:
        _require_actor(MODEL_LANES_HOSTED_RELEASE, actor)
        _require_reason(justification)
        current = self._store.read()
        self._require_synthetic(current)
        if not current.hosted_disabled:
            raise ModelLanesNothingToChange("hosted lanes are not disabled")
        evidence = {
            "control": ModelLanesChange.HOSTED_RELEASE.value,
            "base_revision": str(current.revision),
        }
        return self._open(MODEL_LANES_HOSTED_RELEASE, actor, justification, evidence)

    def approve_release(
        self, pending_id: str, *, approver: ActorBlock, assertion_id: str
    ) -> ModelLanesControl:
        pending = self._ceremony(pending_id, MODEL_LANES_HOSTED_RELEASE)
        current = self._bound(pending)
        if not current.hosted_disabled:
            raise ModelLanesChanged("hosted lanes were re-enabled since the request")
        approved = self._four_eyes.approve(pending_id, approver=approver, assertion_id=assertion_id)
        updated = self._next(
            current,
            change=ModelLanesChange.HOSTED_RELEASE,
            changed_by=approved.actor.subject,
            approved_by=approver.subject,
            hosted_disabled=False,
        )
        return self._write_bound(updated, current.revision)

    def open_key_set(
        self,
        *,
        actor: ActorBlock,
        justification: Justification,
        provider: ProviderId,
        key: ProviderApiKey,
    ) -> PendingAction:
        _require_actor(MODEL_LANES_KEY_SET, actor)
        _require_reason(justification)
        self._require_synthetic(self._store.read())
        keys = self._vault()
        staging_ref = uuid.uuid4().hex
        staged = keys.stage(staging_ref, provider, key)
        evidence = {
            "control": ModelLanesChange.KEY_SET.value,
            "provider": provider.value,
            "key_last4": staged.last4 or "",
            "staging_ref": staging_ref,
        }
        try:
            return self._open(MODEL_LANES_KEY_SET, actor, justification, evidence)
        except Exception:
            keys.discard(staging_ref)
            raise

    def approve_key_set(
        self, pending_id: str, *, approver: ActorBlock, assertion_id: str
    ) -> KeyStatus:
        pending = self._ceremony(pending_id, MODEL_LANES_KEY_SET)
        keys = self._vault()
        self._four_eyes.approve(pending_id, approver=approver, assertion_id=assertion_id)
        return keys.promote(
            pending.evidence["staging_ref"], ProviderId(pending.evidence["provider"])
        )

    def pending(self) -> tuple[PendingAction, ...]:
        return tuple(p for p in self._four_eyes.pending() if p.action in MODEL_LANES_CEREMONIES)

    def reap_staged_keys(self, live_refs: frozenset[str]) -> int:
        """Destroy every staged key no pending ceremony still references."""
        keys = self._vault()
        reaped = 0
        for ref in keys.staged_refs():
            if ref not in live_refs:
                keys.discard(ref)
                reaped += 1
        return reaped

    def live_staging_refs(self) -> frozenset[str]:
        return frozenset(
            p.evidence["staging_ref"]
            for p in self.pending()
            if p.action is MODEL_LANES_KEY_SET and p.state is PendingActionState.PENDING
        )

    # -- internals ----------------------------------------------------------------------

    def _data_class(self, current: ModelLanesControl) -> TenantDataClass:
        return effective_data_class(self._router.declared, current.data_class)

    def _require_synthetic(self, current: ModelLanesControl) -> None:
        if self._data_class(current) is not TenantDataClass.SYNTHETIC:
            raise ModelLanesGovernanceRefused(code="hosted_lane_real_phi_refused")

    def _vault(self) -> ProviderKeyVault:
        keys = self._router.keys
        if keys is None:
            raise KeyVaultUnavailable("model_lanes_key_store_unconfigured")
        return keys

    def _open(
        self,
        action: DangerousAction,
        actor: ActorBlock,
        justification: Justification,
        evidence: Mapping[str, str],
    ) -> PendingAction:
        return self._four_eyes.open(
            action=action,
            actor=actor,
            target_ref=CONTROL_TARGET,
            justification=justification,
            evidence=evidence,
            ttl=LANES_PENDING_TTL,
        )

    def _ceremony(self, pending_id: str, action: DangerousAction) -> PendingAction:
        pending = self._four_eyes.get(pending_id)
        if pending.action is not action:
            raise ModelLanesActionMismatch("that pending action belongs to another route")
        return pending

    def _bound(self, pending: PendingAction) -> ModelLanesControl:
        current = self._store.read()
        if current.revision != int(pending.evidence["base_revision"]):
            raise ModelLanesChanged("the model-lane control moved since this request")
        return current

    def _write_bound(self, updated: ModelLanesControl, base: int) -> ModelLanesControl:
        try:
            return self._store.write(updated, expected_revision=base)
        except ModelLanesConflict:
            raise ModelLanesChanged("the control moved while the approval landed") from None

    def _safe_write(
        self, apply: Callable[[ModelLanesControl], ModelLanesControl | None]
    ) -> ModelLanesChangeResult:
        # The narrowing direction must not bounce off a concurrent write.
        for _ in range(_SAFE_ATTEMPTS):
            current = self._store.read()
            updated = apply(current)
            if updated is None:
                return ModelLanesChangeResult(control=current, changed=False)
            try:
                written = self._store.write(updated, expected_revision=current.revision)
            except ModelLanesConflict:
                continue
            return ModelLanesChangeResult(control=written, changed=True)
        raise ModelLanesChanged("the control kept moving while it was written")

    def _next(
        self,
        current: ModelLanesControl,
        *,
        change: ModelLanesChange,
        changed_by: str,
        approved_by: str | None,
        lanes: Mapping[Lane, LaneSetting] | None = None,
        roles: Mapping[str, LaneSetting] | None = None,
        hosted_disabled: bool | None = None,
    ) -> ModelLanesControl:
        return ModelLanesControl(
            lanes=dict(lanes if lanes is not None else current.lanes),
            roles=dict(roles if roles is not None else current.roles),
            hosted_disabled=(
                current.hosted_disabled if hosted_disabled is None else hosted_disabled
            ),
            # bound by the first write, copied by every later one
            data_class=(
                current.data_class if current.data_class is not None else self._router.declared
            ),
            revision=current.revision + 1,
            changed_at=self._clock(),
            changed_by=changed_by,
            approved_by=approved_by,
            last_change=change,
        )
