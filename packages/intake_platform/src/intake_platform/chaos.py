"""Chaos harness (INT-024) — experiment runner + the `vendor_kill` experiment.

files/10 §7 names the posture: chaos experiments (kill a vendor adapter,
stall the Backend, drop the SFU) run monthly in STAGING, results tracked as
metrics. No staging environment exists yet, so `make chaos EXPERIMENT=<id>`
is the standalone entry point and the scheduled staging job arrives with the
staging environment (docs/evidence/INT-024.md records the deferral).

The seam: intake_platform has no formal LLM/speech vendor-adapter interface
yet — the provider-agnostic gateways land with the voice runtime — so this
module defines the minimal :class:`AdapterProbe` contract a vendor adapter
must satisfy to sit behind :class:`DegradationRouter`, plus the in-process
:class:`MockVendorAdapter` with a kill switch as the experiment's subject.
The mock stands on no serving path: real vendor adapters are blocked from
the PHI path by the egress allow-list (CLAUDE.md inv. 19), and the router's
fallback decision is the `typed` profile — ADR-010's degrade-to-text tier,
a mode of the same service, never a separate component.

Every family emitted here is declared in observability/metrics_catalog.yaml
(inv. 13); tests/chaos/test_vendor_kill_fallback.py asserts the acceptance:
kill → typed fallback within :data:`FALLBACK_DEADLINE_S`, counters moved.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol, runtime_checkable

from prometheus_client import REGISTRY, Counter, Histogram, disable_created_metrics

__all__ = [
    "FALLBACK_DEADLINE_S",
    "AdapterProbe",
    "ChaosError",
    "Clock",
    "DegradationRouter",
    "ExperimentReport",
    "MockVendorAdapter",
    "MonotonicClock",
    "RouteResult",
    "UnknownExperimentError",
    "VendorAdapterError",
    "VendorKilled",
    "main",
    "run_experiment",
    "run_vendor_kill",
]

# The client's `_created` companion series would sit next to every counter
# and histogram without appearing in the catalogue (inv. 13) — off, as
# everywhere else on the platform.
disable_created_metrics()  # type: ignore[no-untyped-call]  # upstream def has no annotations

#: INT-024 acceptance bound: the caller holds a typed fallback decision no
#: later than this many seconds after the failing vendor call started.
FALLBACK_DEADLINE_S: Final[float] = 2.0

VENDOR_KILL: Final[str] = "vendor_kill"

VENDOR_ADAPTER_FAILURES_TOTAL = Counter(
    "vendor_adapter_failures_total",
    "Vendor adapter calls that failed, by adapter id.",
    ["adapter"],
)

VENDOR_ADAPTER_FALLBACKS_TOTAL = Counter(
    "vendor_adapter_fallbacks_total",
    "Fallback decisions handed to callers after a vendor adapter failure, "
    "by adapter id and fallback mode.",
    ["adapter", "mode"],
)

VENDOR_FALLBACK_LATENCY_SECONDS = Histogram(
    "vendor_fallback_latency_seconds",
    "Seconds from the failing vendor call's start to the fallback decision.",
    ["adapter"],
)

CHAOS_EXPERIMENT_RUNS_TOTAL = Counter(
    "chaos_experiment_runs_total",
    "Chaos experiment executions, by experiment id and outcome.",
    ["experiment", "outcome"],
)


class ChaosError(Exception):
    """Base for every typed refusal this module raises."""


class VendorAdapterError(ChaosError):
    """A vendor adapter failed to serve a call."""


class VendorKilled(VendorAdapterError):
    """The kill switch is thrown: the vendor behaves like a dead upstream."""


class UnknownExperimentError(ChaosError):
    """The requested experiment id is not registered."""


@runtime_checkable
class AdapterProbe(Protocol):
    """The minimal vendor-adapter seam the degradation router routes over.

    One stable id and one synchronous unit of vendor work that raises on
    failure — nothing more. The provider-agnostic gateways (CLAUDE.md §How
    we work) adopt this contract when they land; until then it is defined
    here so the chaos harness has a real seam to cut.
    """

    @property
    def name(self) -> str: ...

    def call(self, payload: str) -> str: ...


@dataclass
class MockVendorAdapter:
    """In-process mock vendor with a kill switch — the experiment's subject.

    Named by the INT-024 acceptance ("kills a mock vendor adapter"); it
    exists for chaos experiments only and stands on no serving path.
    """

    name: str = "mock_vendor"
    killed: bool = False

    def kill(self) -> None:
        """Throw the kill switch: every later call fails like a dead vendor."""
        self.killed = True

    def call(self, payload: str) -> str:
        if self.killed:
            raise VendorKilled(f"vendor adapter {self.name!r} is killed")
        return f"{self.name}:{payload}"


class Clock(Protocol):
    """Injectable time source so fallback latency is testable exactly."""

    def monotonic(self) -> float: ...


@dataclass(frozen=True)
class MonotonicClock:
    """The real clock — the wall bound in the acceptance is measured on it."""

    def monotonic(self) -> float:
        return time.monotonic()


RouteMode = Literal["vendor", "typed"]


@dataclass(frozen=True)
class RouteResult:
    """What the caller receives from the degradation router.

    ``mode == "vendor"`` carries the vendor response. ``mode == "typed"`` is
    the typed fallback decision: the caller degrades the session to the
    `typed` profile (ADR-010). ``reason`` carries the failure's exception
    class name only — never message text, which could quote payload content
    (inv. 6 discipline for anything a caller might log).
    """

    mode: RouteMode
    adapter: str
    response: str | None
    fallback_latency_s: float | None
    reason: str | None


@dataclass
class DegradationRouter:
    """Routes one call through a vendor adapter; any failure degrades to typed.

    The router never propagates a vendor failure: the caller always receives
    a decision — the vendor response or the typed fallback — and the
    failure/fallback families move on every degradation.
    """

    adapter: AdapterProbe
    clock: Clock = field(default_factory=MonotonicClock)

    def route(self, payload: str) -> RouteResult:
        started = self.clock.monotonic()
        try:
            response = self.adapter.call(payload)
        except Exception as err:
            latency_s = self.clock.monotonic() - started
            VENDOR_ADAPTER_FAILURES_TOTAL.labels(adapter=self.adapter.name).inc()
            VENDOR_ADAPTER_FALLBACKS_TOTAL.labels(adapter=self.adapter.name, mode="typed").inc()
            VENDOR_FALLBACK_LATENCY_SECONDS.labels(adapter=self.adapter.name).observe(latency_s)
            return RouteResult(
                mode="typed",
                adapter=self.adapter.name,
                response=None,
                fallback_latency_s=latency_s,
                reason=type(err).__name__,
            )
        return RouteResult(
            mode="vendor",
            adapter=self.adapter.name,
            response=response,
            fallback_latency_s=None,
            reason=None,
        )


@dataclass(frozen=True)
class ExperimentReport:
    """One experiment's verdict, measured latency and observed metric deltas."""

    experiment: str
    passed: bool
    fallback_latency_s: float
    deadline_s: float
    metric_deltas: Mapping[str, float]
    notes: tuple[str, ...]

    def render(self) -> tuple[str, ...]:
        verdict = "PASS" if self.passed else "FAIL"
        lines = [
            f"chaos {self.experiment}: {verdict} — typed fallback in "
            f"{self.fallback_latency_s:.6f} s (bound {self.deadline_s:.1f} s)"
        ]
        lines.extend(f"  {note}" for note in self.notes)
        lines.extend(f"  metric {name} +{delta:g}" for name, delta in self.metric_deltas.items())
        return tuple(lines)


def _sample(name: str, labels: Mapping[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, dict(labels))
    return 0.0 if value is None else value


def run_vendor_kill(clock: Clock | None = None) -> ExperimentReport:
    """Kill the mock vendor mid-session and verify the degradation contract.

    Serves one healthy call, throws the kill switch, and checks that the
    very next call comes back as a typed fallback decision within
    :data:`FALLBACK_DEADLINE_S` — with the failure and fallback counters
    each moved by exactly one.
    """
    vendor = MockVendorAdapter()
    router = DegradationRouter(adapter=vendor, clock=clock or MonotonicClock())
    failure_labels = {"adapter": vendor.name}
    fallback_labels = {"adapter": vendor.name, "mode": "typed"}
    failures_before = _sample("vendor_adapter_failures_total", failure_labels)
    fallbacks_before = _sample("vendor_adapter_fallbacks_total", fallback_labels)

    healthy = router.route("pre-kill turn")
    vendor.kill()
    degraded = router.route("post-kill turn")

    metric_deltas = {
        "vendor_adapter_failures_total": (
            _sample("vendor_adapter_failures_total", failure_labels) - failures_before
        ),
        "vendor_adapter_fallbacks_total": (
            _sample("vendor_adapter_fallbacks_total", fallback_labels) - fallbacks_before
        ),
    }
    latency_s = (
        degraded.fallback_latency_s if degraded.fallback_latency_s is not None else float("inf")
    )
    passed = (
        healthy.mode == "vendor"
        and degraded.mode == "typed"
        and latency_s <= FALLBACK_DEADLINE_S
        and metric_deltas["vendor_adapter_failures_total"] == 1.0
        and metric_deltas["vendor_adapter_fallbacks_total"] == 1.0
    )
    CHAOS_EXPERIMENT_RUNS_TOTAL.labels(
        experiment=VENDOR_KILL, outcome="pass" if passed else "fail"
    ).inc()
    notes = (
        f"pre-kill call served by vendor adapter {vendor.name!r} (mode={healthy.mode})",
        f"kill switch thrown; next call came back mode={degraded.mode!r}"
        f" (reason={degraded.reason})",
    )
    return ExperimentReport(
        experiment=VENDOR_KILL,
        passed=passed,
        fallback_latency_s=latency_s,
        deadline_s=FALLBACK_DEADLINE_S,
        metric_deltas=metric_deltas,
        notes=notes,
    )


#: The experiment registry `make chaos EXPERIMENT=<id>` dispatches over.
EXPERIMENTS: Mapping[str, Callable[[], ExperimentReport]] = {VENDOR_KILL: run_vendor_kill}


def run_experiment(experiment_id: str) -> ExperimentReport:
    try:
        runner = EXPERIMENTS[experiment_id]
    except KeyError:
        known = ", ".join(sorted(EXPERIMENTS))
        raise UnknownExperimentError(
            f"unknown experiment {experiment_id!r} (known: {known})"
        ) from None
    return runner()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m intake_platform.chaos",
        description="INTAKE chaos harness (INT-024): run one experiment and report.",
    )
    parser.add_argument(
        "--experiment",
        required=True,
        help=f"experiment id (known: {', '.join(sorted(EXPERIMENTS))})",
    )
    args = parser.parse_args(argv)
    try:
        report = run_experiment(args.experiment)
    except UnknownExperimentError as err:
        print(f"chaos: {err}", file=sys.stderr)
        return 2
    for line in report.render():
        print(line)
    return 0 if report.passed else 1


if __name__ == "__main__":  # pragma: no cover — `make chaos` entry point
    raise SystemExit(main())
