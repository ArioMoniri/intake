"""Where each registry row stands on the host the console runs on (INT-560).

The INT-183 projection (:mod:`intake_probes.console`) answers a registry-wide
question: would a PHI release be blocked? The ops console's registry tile is
asked a narrower one by the people reading it on a deployed host: *what does
this host run, is it answering, and is anything this host needs broken?*
Answering the second with the first is how the synthetic AWS host came to say
"evet" and "blocking" for the team GPU server's models.

A :class:`Standing` derives four columns from the host's inventory
(:mod:`intake_probes.inventory`) and the probe runner's last sweep:

- **deployment** — ``this_host`` for what the inventory places here;
  ``elsewhere`` for a row the registry says we self-host on some other host;
  ``not_deployed`` for a row that runs nowhere; ``undeclared`` when this
  deployment has no inventory, which the page says rather than guessing.
- **probe** — the last result and its age. A missing result is
  ``no_result`` and never healthy; a result older than three sweeps, or of
  unknown age, is stale and is not current.
- **needed** — whether the deployed stack needs it, and if not, why.
- **severity** — :attr:`~CellSeverity.BLOCKING` only for what this host's
  stack needs whose probe is not currently healthy. Everything else is
  advisory and names its reason. The INT-022 release gate's verdict about a
  row is one such reason on a synthetic host: it binds a PHI deployment, and
  an inventory exists for the synthetic data class only.

With no inventory the derivation is the registry-wide one it replaced — the
strict direction — so a deployment that declares nothing cannot have a
blocking row relaxed by accident.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from intake_probes.console import CellSeverity, ModelRow, ModelsModule
from intake_probes.gate import ProbeResultRecord
from intake_probes.inventory import HostInventory
from intake_probes.runner import STALE_AFTER_S, ProbeStatus

__all__ = ["Deployment", "ProbeView", "Standing", "StandingReason", "probe_view", "standings"]

#: The probe column's word for "the sweep holds no result for this row".
NO_RESULT = "no_result"


class Deployment(StrEnum):
    THIS_HOST = "this_host"
    ELSEWHERE = "elsewhere"
    NOT_DEPLOYED = "not_deployed"
    UNDECLARED = "undeclared"


class StandingReason(StrEnum):
    """Why a row has the severity it has: one code, the most important one."""

    OK = "ok"
    #: BLOCKING — this host's stack needs it and its probe is not healthy now.
    NEEDED_NOT_HEALTHY = "needed_not_healthy"
    #: the host does not run it, so nothing here can be blocked by it
    NOT_ON_THIS_HOST = "not_on_this_host"
    #: deployed here, not needed, and its probe is not healthy now
    UNNEEDED_NOT_HEALTHY = "unneeded_not_healthy"
    #: the INT-022 gate names it; that binds a PHI deployment, not this host
    PHI_RELEASE_GATE = "phi_release_gate"
    #: the registry records no licence read from a raw LICENSE blob
    LICENCE_UNVERIFIED = "licence_unverified"
    # --- the registry-wide reading, used when no inventory is declared -------------
    RELEASE_BLOCKED = "release_blocked"
    PLANNED_NOT_RUNNING = "planned_not_running"
    PROBE_NOT_HEALTHY = "probe_not_healthy"


@dataclass(frozen=True)
class ProbeView:
    """The last result for one row, as of ``now``."""

    status: str
    checked_at: datetime | None
    age_s: int | None
    stale: bool

    @property
    def current_and_healthy(self) -> bool:
        return self.status == ProbeStatus.HEALTHY.value and not self.stale


@dataclass(frozen=True)
class Standing:
    component: str
    deployment: Deployment
    #: ``None`` unless the row is deployed on this host
    needed: bool | None
    not_needed_reason: str | None
    probe: ProbeView
    severity: CellSeverity
    reason: StandingReason


def probe_view(record: ProbeResultRecord | None, now: datetime) -> ProbeView:
    """The last result and its age; stale past three sweeps or when age is unknown."""
    if record is None:
        return ProbeView(NO_RESULT, None, None, stale=True)
    checked = record.checked_at
    if checked is None or checked.tzinfo is None:
        return ProbeView(record.status.value, None, None, stale=True)
    age = int((now - checked).total_seconds())
    if age < 0:
        # a result from the future is not one this clock can date
        return ProbeView(record.status.value, checked.astimezone(UTC), None, stale=True)
    return ProbeView(record.status.value, checked.astimezone(UTC), age, stale=age > STALE_AFTER_S)


_REGISTRY_WIDE_REASONS: dict[str, StandingReason] = {
    "release_blocked": StandingReason.RELEASE_BLOCKED,
    "licence_not_verified_from_blob": StandingReason.LICENCE_UNVERIFIED,
    "planned_not_running": StandingReason.PLANNED_NOT_RUNNING,
    "probe_not_healthy": StandingReason.PROBE_NOT_HEALTHY,
}


def _registry_wide(row: ModelRow, view: ProbeView) -> Standing:
    """No inventory: the INT-183 severity, unchanged, and its first reason."""
    codes = [finding.code for finding in row.findings]
    if row.severity is CellSeverity.BLOCKING:
        reason = StandingReason.RELEASE_BLOCKED
    else:
        reason = next(
            (_REGISTRY_WIDE_REASONS[code] for code in codes if code in _REGISTRY_WIDE_REASONS),
            StandingReason.OK,
        )
    return Standing(
        component=row.component,
        deployment=Deployment.UNDECLARED,
        needed=None,
        not_needed_reason=None,
        probe=view,
        severity=row.severity,
        reason=reason,
    )


def _host_scoped(
    row: ModelRow, view: ProbeView, inventory: HostInventory, gate_names: frozenset[str]
) -> Standing:
    component = row.component
    licence_unverified = any(f.code == "licence_not_verified_from_blob" for f in row.findings)
    if component not in inventory.deployed():
        return Standing(
            component=component,
            deployment=Deployment.ELSEWHERE if row.self_hosted_now else Deployment.NOT_DEPLOYED,
            needed=None,
            not_needed_reason=None,
            probe=view,
            severity=CellSeverity.ATTENTION,
            reason=StandingReason.NOT_ON_THIS_HOST,
        )
    needed = component in inventory.needed()
    unneeded = inventory.not_needed_reason(component)
    if not view.current_and_healthy:
        severity = CellSeverity.BLOCKING if needed else CellSeverity.ATTENTION
        reason = (
            StandingReason.NEEDED_NOT_HEALTHY if needed else StandingReason.UNNEEDED_NOT_HEALTHY
        )
    elif component in gate_names:
        severity, reason = CellSeverity.ATTENTION, StandingReason.PHI_RELEASE_GATE
    elif licence_unverified:
        severity, reason = CellSeverity.ATTENTION, StandingReason.LICENCE_UNVERIFIED
    else:
        severity, reason = CellSeverity.OK, StandingReason.OK
    return Standing(
        component=component,
        deployment=Deployment.THIS_HOST,
        needed=needed,
        not_needed_reason=None if unneeded is None else unneeded.value,
        probe=view,
        severity=severity,
        reason=reason,
    )


def standings(
    module: ModelsModule,
    inventory: HostInventory | None,
    records: Mapping[str, ProbeResultRecord],
    now: datetime,
) -> tuple[Standing, ...]:
    """One :class:`Standing` per registry row, in registry order."""
    gate_names = frozenset(reason.component for reason in module.release.reasons)
    out: list[Standing] = []
    for row in module.rows:
        view = probe_view(records.get(row.component), now)
        if inventory is None:
            out.append(_registry_wide(row, view))
        else:
            out.append(_host_scoped(row, view, inventory, gate_names))
    return tuple(out)
