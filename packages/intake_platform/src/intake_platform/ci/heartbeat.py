"""INT-206 — the runner heartbeat, evaluated (files/08 §6, probe "runner heartbeat").

The registry row for CI names `runner heartbeat` as its probe. This is the
decision half of that probe, kept in the platform package so it is exercised by
the unit lane rather than only by a live sweep; `intake_probes.probes` wraps it
into the sweep's Ok/Failed/Skipped vocabulary.

With no declared pool the answer is neither healthy nor unhealthy — there is
nothing to beat. Reporting "healthy" for an empty set is how a monitoring
system tells you a service is fine when it does not exist, so
:attr:`HeartbeatReport.healthy` is False and the detail names HB-I7.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from intake_platform.ci.pools import RUNNER_POOL_ASK, RunnerPools

__all__ = ["HeartbeatReport", "evaluate_heartbeats"]


@dataclass(frozen=True, slots=True)
class HeartbeatReport:
    checked: tuple[str, ...]
    stale: tuple[str, ...]
    missing: tuple[str, ...]
    detail: str

    @property
    def healthy(self) -> bool:
        return bool(self.checked) and not self.stale and not self.missing


def evaluate_heartbeats(
    pools: RunnerPools, seen: Mapping[str, float], now: float
) -> HeartbeatReport:
    """Compare each declared pool's last heartbeat against its own staleness bound."""
    if not pools.pools:
        return HeartbeatReport((), (), (), RUNNER_POOL_ASK)

    checked: list[str] = []
    stale: list[str] = []
    missing: list[str] = []
    for pool in pools.pools:
        checked.append(pool.label)
        last = seen.get(pool.label)
        if last is None:
            missing.append(pool.label)
        elif now - last > pool.max_heartbeat_age_s:
            stale.append(pool.label)

    parts: list[str] = []
    if missing:
        parts.append(f"no heartbeat from {', '.join(missing)}")
    if stale:
        parts.append(f"stale heartbeat from {', '.join(stale)}")
    detail = "; ".join(parts) if parts else f"{len(checked)} pool(s) beating"
    return HeartbeatReport(tuple(checked), tuple(stale), tuple(missing), detail)
