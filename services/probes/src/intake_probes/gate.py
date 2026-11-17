"""Release-gate evaluation over the registry + a probe-results file (INT-022).

Acceptance, verbatim: "release-gate script blocks when an enabled phi_path
component lacks a healthy self-hosted fallback". Enabled means
`self_hosted_now: true` — a planned component binds the moment it runs.

Fallback semantics:
- `none`                         → violation while the component is enabled;
- `in-process:<module>`          → satisfied: the fallback ships inside the
                                   component's own artefact, so it is exactly
                                   as self-hosted and as alive as the
                                   component itself;
- `component:<name>`             → that registry row must be self-hosted now
                                   and its probe result HEALTHY.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter

from intake_probes.registry import FallbackKind, Registry
from intake_probes.runner import ProbeStatus

__all__ = [
    "GateViolation",
    "ProbeResultRecord",
    "evaluate_release_gate",
    "load_results",
    "render_report",
]


class ProbeResultRecord(BaseModel):
    """One runner result on the wire — the shape ProbeResult.to_json emits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component: str
    probe: str
    status: ProbeStatus
    latency_ms: float | None = None
    detail: str = ""
    #: the instant the probe started (INT-181); absent in a sweep written
    #: before the runner stamped one, which a reader treats as "age unknown"
    checked_at: datetime | None = None


_RESULTS_ADAPTER: TypeAdapter[list[ProbeResultRecord]] = TypeAdapter(list[ProbeResultRecord])


@dataclass(frozen=True)
class GateViolation:
    component: str
    reason: str


def load_results(path: Path) -> dict[str, ProbeResultRecord]:
    """Parse a runner results file; the last record per component wins."""
    records = _RESULTS_ADAPTER.validate_python(json.loads(path.read_text(encoding="utf-8")))
    return {record.component: record for record in records}


def evaluate_release_gate(
    registry: Registry, results: dict[str, ProbeResultRecord]
) -> list[GateViolation]:
    violations: list[GateViolation] = []
    for entry in registry:
        if not (entry.self_hosted_now and entry.phi_path):
            continue  # planned rows bind when they run; non-PHI rows never do
        kind = entry.fallback_kind
        if kind is FallbackKind.IN_PROCESS:
            continue
        if kind is FallbackKind.NONE:
            violations.append(
                GateViolation(entry.component, "no self-hosted fallback declared (fallback: none)")
            )
            continue
        target = registry.get(entry.fallback_target)
        if not target.self_hosted_now:
            violations.append(
                GateViolation(
                    entry.component,
                    f"fallback {target.component!r} is not self-hosted now ({target.host})",
                )
            )
            continue
        result = results.get(target.component)
        if result is None:
            violations.append(
                GateViolation(
                    entry.component,
                    f"fallback {target.component!r} has no probe result in this sweep",
                )
            )
        elif result.status is not ProbeStatus.HEALTHY:
            violations.append(
                GateViolation(
                    entry.component,
                    f"fallback {target.component!r} probe is {result.status.value}: "
                    f"{result.detail}",
                )
            )
    return violations


def render_report(violations: list[GateViolation]) -> str:
    if not violations:
        return (
            "RELEASE GATE: PASS — every enabled phi_path component has a healthy "
            "self-hosted fallback."
        )
    lines = [
        f"RELEASE GATE: BLOCKED — {len(violations)} enabled phi_path component(s) "
        "lack a healthy self-hosted fallback:"
    ]
    lines.extend(f" - {v.component} — {v.reason}" for v in violations)
    return "\n".join(lines)
