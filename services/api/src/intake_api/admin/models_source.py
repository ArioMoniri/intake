"""Where the models module gets its facts (INT-183).

One rule and it is invariant 13's: **the console reads the registry, it does
not keep one.** ``observability/registry.yaml`` is the single declaration of
what is self-hostable, what is self-hosted now, what probes it and what stands
behind it, and this module loads it through ``intake_probes`` — the same
package that runs the 60-second sweep and evaluates the release gate. There is
no second matrix to fall out of date, because there is no second matrix.

``intake-probes`` is therefore a declared dependency of ``intake-api`` rather
than a copied model, for the same reason INT-241 declared ``intake-metrics``:
a second implementation of a gate is a gate that disagrees with itself on the
day it matters.

**The sweep may be absent, and the console says so rather than assuming.**
``INTAKE_PROBE_RESULTS_PATH`` names the runner's results file. When it is
unset or unreadable the module renders an empty sweep, which makes every
enabled row's own probe read *"no probe result in this sweep"* and makes the
release gate block on any fallback it cannot see the health of. That is the
fail-closed direction: an unobserved fallback is not a healthy one.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from os import environ
from pathlib import Path

from intake_probes.app import registry_path_from_env
from intake_probes.console import (
    BenchmarkKind,
    BenchmarkPlan,
    BenchmarkResult,
    ModelsModule,
    models_module,
    plan_benchmark,
    run_latency_benchmark,
)
from intake_probes.gate import ProbeResultRecord, load_results
from intake_probes.registry import Registry, load_registry
from intake_probes.runner import DevProbeConfig, build_dev_clients

__all__ = [
    "PROBE_CLIENTS_ENV",
    "PROBE_RESULTS_ENV",
    "load_models_module",
    "resolve_benchmark",
    "run_benchmark",
]

#: Set to ``dev`` to let the benchmark trigger actually dial the dev stack.
#: Unset by default, and unset in every test: a console route that opens a
#: socket because a suite happened to import it is how a test lane starts
#: depending on a machine. When it is unset the trigger plans and says so.
PROBE_CLIENTS_ENV = "INTAKE_PROBE_CLIENTS"

#: The runner writes its sweep here; the console reads it. Unset in a dev
#: checkout, which is why the empty-sweep path is the tested one.
PROBE_RESULTS_ENV = "INTAKE_PROBE_RESULTS_PATH"


def _results() -> Mapping[str, ProbeResultRecord]:
    raw = environ.get(PROBE_RESULTS_ENV)
    if not raw:
        return {}
    path = Path(raw)
    if not path.is_file():
        return {}
    return load_results(path)


def _registry() -> Registry:
    return load_registry(registry_path_from_env())


def load_models_module() -> ModelsModule:
    """The whole module: every registry row, plus the release decision."""
    return models_module(_registry(), _results())


def resolve_benchmark(component: str, kind: BenchmarkKind, corpus_id: str | None) -> BenchmarkPlan:
    """Plan a benchmark for one component, or raise :class:`BenchmarkRefused`."""
    return plan_benchmark(_registry(), component, kind, corpus_id)


def run_benchmark(plan: BenchmarkPlan) -> BenchmarkResult | None:
    """Execute the latency lane, or return ``None`` if this environment cannot.

    ``None`` is not a failure and is not an empty result — it means no probe
    client is wired here, so the trigger returns its plan and says that. The
    alternative, reporting a zero or a fabricated healthy, is the shape
    invariant 20 and invariant 17 both refuse.
    """
    if environ.get(PROBE_CLIENTS_ENV) != "dev":
        return None
    registry = _registry()
    clients = build_dev_clients(registry, DevProbeConfig())
    return run_latency_benchmark(registry, plan, clients, datetime.now(UTC).date())
