"""The console projection of the self-hosting registry (INT-183).

files/08 §148 gives the *Models & self-hosting registry* module one job: show,
per model and per service, what it is pinned to, who hosts it, under what
licence, whether it is self-hostable, whether it is self-hosted *now*, what
probes it, what stands behind it — and whether any of that blocks a release.

Three design rules, each of which is a rule the module is easy to get wrong.

**1. Projection, never a copy.** Every row here is read out of
``observability/registry.yaml`` through the same loader
:mod:`intake_probes.gate` uses (invariant 13). The console holds no matrix of
its own; there is nothing to keep in sync, so there is nothing to drift.

**2. The release decision is the INT-022 gate, called.** files/08 §6:
*"a release is blocked if a component enabled on the PHI path has
`self_hostable=false` or no healthy fallback"*. Both arms are honoured, and
the first is honoured by being unreachable — :class:`RegistryEntry` refuses a
``phi_path`` row that is not ``self_hostable``, so that state cannot be
written down. The second is :func:`~intake_probes.gate.evaluate_release_gate`,
invoked rather than reimplemented. A second implementation of a gate is a gate
that disagrees with itself on the day it matters.

**3. Red and amber are different things, and the difference is enforced.**
A cell is RED — :attr:`CellSeverity.BLOCKING` — if and only if the gate names
its component. Everything else worth saying is AMBER: a licence the registry
itself records as unread or as forbidding commercial use (INT-561's
``licence_commercial_use``), a PHI-path row that is declared but not running, a
component whose own probe is unhealthy while its fallback is fine. Amber is
loud and does not block. If amber blocked too, "red blocks the release" would
carry no information.

**Measurements, not claims.** :class:`Measurement` cannot be constructed
without a named corpus and a date, so a bare number cannot reach the console
at all (invariant 20). The quality benchmark lane refuses for exactly that
reason: :data:`BENCHMARK_CORPORA` is EMPTY because no Turkish clinical
evaluation corpus exists (HUMAN_BLOCKERS **HB-C10**; **HB-A13** for the
records side). The mechanism ships, the gate is wired, the content is empty —
a plausible corpus id here would be the invented value invariant 17 forbids.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from intake_probes.gate import ProbeResultRecord, evaluate_release_gate
from intake_probes.registry import CommercialUse, Registry, RegistryEntry
from intake_probes.runner import ProbeFn, ProbeResult, ProbeStatus, run_probes_once

__all__ = [
    "BENCHMARK_CORPORA",
    "BenchmarkCorpus",
    "BenchmarkKind",
    "BenchmarkPlan",
    "BenchmarkRefused",
    "BenchmarkResult",
    "BlockReason",
    "CellSeverity",
    "Finding",
    "Measurement",
    "ModelRow",
    "ModelsModule",
    "ReleaseDecision",
    "models_module",
    "plan_benchmark",
    "run_latency_benchmark",
]

#: The sentinel observability/registry.yaml uses for a licence that has not
#: been read from a raw LICENSE blob (its header: *"Licences here are
#: findings, never claims: UNVERIFIED stays UNVERIFIED until a raw LICENSE
#: blob has been read"*). The console surfaces the registry's own word for it
#: rather than inventing a second vocabulary.
_UNVERIFIED_SENTINEL = "UNVERIFIED"


class CellSeverity(StrEnum):
    """What a cell's colour *does*, named for the effect and not the hue."""

    OK = "ok"
    #: Amber. A finding a reader must see. It does not block a release.
    ATTENTION = "attention"
    #: Red. The release gate names this component; the release is blocked.
    BLOCKING = "blocking"


@dataclass(frozen=True)
class Finding:
    """One thing wrong with a row, with a stable code and readable detail."""

    code: str
    detail: str


class Measurement(BaseModel):
    """A number the console may show.

    Invariant 20 in type form: a measurement is a dated observation over a
    named corpus, never a property of the product. Both fields are required
    and both are non-empty, so an unlabelled figure cannot be constructed —
    which is the only way to stop one being rendered.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    #: What it was measured over. Never blank, never "internal".
    corpus: str = Field(min_length=1)
    measured_on: date

    def render(self) -> str:
        return (
            f"{self.metric} {self.value:g} {self.unit} — measured {self.measured_on.isoformat()} "
            f"on {self.corpus}"
        )


@dataclass(frozen=True)
class ModelRow:
    """One registry component as the console shows it."""

    component: str
    self_hostable: bool
    self_hosted_now: bool
    host: str
    license: str
    probe: str
    budget_ms: int
    fallback: str
    phi_path: bool
    #: ``model_id@revision`` where the row pins weights, else ``None``.
    pin: str | None
    licence_verified_at: date | None
    severity: CellSeverity
    findings: tuple[Finding, ...]

    @property
    def blocks_release(self) -> bool:
        return self.severity is CellSeverity.BLOCKING


@dataclass(frozen=True)
class BlockReason:
    component: str
    reason: str


@dataclass(frozen=True)
class ReleaseDecision:
    blocked: bool
    reasons: tuple[BlockReason, ...]


@dataclass(frozen=True)
class ModelsModule:
    rows: tuple[ModelRow, ...]
    release: ReleaseDecision


def _pin(entry: RegistryEntry) -> str | None:
    if entry.model_id is None or entry.revision is None:
        return None
    return f"{entry.model_id}@{entry.revision}"


def _findings(entry: RegistryEntry, result: ProbeResultRecord | None) -> tuple[Finding, ...]:
    found: list[Finding] = []
    if entry.licence_commercial_use is CommercialUse.NO:
        # INT-561: read, hashed — and it forbids commercial use. Invariant 19
        # makes that a finding on any row, never a verified licence.
        found.append(
            Finding(
                "licence_not_commercially_usable",
                f"{entry.component}: the raw licence blob ({entry.licence_spdx}) forbids "
                f"commercial use (invariant 19).",
            )
        )
    elif (
        entry.licence_commercial_use is CommercialUse.BLOB_NOT_FOUND
        or entry.license.upper().startswith(_UNVERIFIED_SENTINEL)
    ):
        found.append(
            Finding(
                "licence_not_verified_from_blob",
                f"{entry.component}: the declared licence has not been read from a raw "
                f"LICENSE blob ({entry.license}). files/03 §4.9.0 rule 3 — a card tag or a "
                f"badge is not a grant.",
            )
        )
    if entry.phi_path and not entry.self_hosted_now:
        found.append(
            Finding(
                "planned_not_running",
                f"{entry.component}: declared on the PHI path and not self-hosted now, so "
                f"the release gate does not bind to it yet ({entry.host}).",
            )
        )
    if entry.self_hosted_now and (result is None or result.status is not ProbeStatus.HEALTHY):
        state = "no probe result in this sweep" if result is None else result.status.value
        found.append(
            Finding(
                "probe_not_healthy",
                f"{entry.component}: own probe {entry.probe.value} is {state}.",
            )
        )
    return tuple(found)


def models_module(registry: Registry, results: Mapping[str, ProbeResultRecord]) -> ModelsModule:
    """Project the registry and one probe sweep into the console module."""
    violations = evaluate_release_gate(registry, dict(results))
    blocked_reasons = tuple(BlockReason(v.component, v.reason) for v in violations)
    blocked_components = {reason.component for reason in blocked_reasons}

    rows: list[ModelRow] = []
    for entry in registry:
        result = results.get(entry.component)
        findings = _findings(entry, result)
        if entry.component in blocked_components:
            severity = CellSeverity.BLOCKING
            findings = findings + tuple(
                Finding("release_blocked", reason.reason)
                for reason in blocked_reasons
                if reason.component == entry.component
            )
        elif findings:
            severity = CellSeverity.ATTENTION
        else:
            severity = CellSeverity.OK
        rows.append(
            ModelRow(
                component=entry.component,
                self_hostable=entry.self_hostable,
                self_hosted_now=entry.self_hosted_now,
                host=entry.host,
                license=entry.license,
                probe=entry.probe.value,
                budget_ms=entry.budget_ms,
                fallback=entry.fallback,
                phi_path=entry.phi_path,
                pin=_pin(entry),
                licence_verified_at=entry.licence_verified_at,
                severity=severity,
                findings=findings,
            )
        )

    return ModelsModule(
        rows=tuple(rows),
        release=ReleaseDecision(blocked=bool(blocked_reasons), reasons=blocked_reasons),
    )


# --------------------------------------------------------------------------
# The benchmark trigger (files/08 §148 "run benchmark", §8 POST route)
# --------------------------------------------------------------------------


class BenchmarkKind(StrEnum):
    """The two things "run benchmark" can mean, kept apart on purpose.

    ``LATENCY`` is an operational measurement of our own deployment against
    the row's declared ``budget_ms``, over a synthetic probe payload. It
    carries no patient data (invariant 6) and states no accuracy figure, so it
    runs today.

    ``QUALITY`` is a WER / extraction-accuracy style measurement. It needs a
    named, dated, licensed corpus, and none exists (HB-C10). It refuses.
    """

    LATENCY = "latency"
    QUALITY = "quality"


@dataclass(frozen=True)
class BenchmarkCorpus:
    """A named evaluation set: what it is, when it was obtained, its licence."""

    corpus_id: str
    description: str
    obtained_on: date
    licence: str


#: EMPTY, and deliberately so — the same fail-closed shape as INT-180's
#: ``ip_allowlist`` and tenant ``deployments``. HB-C10 (*"a 3-5 h Turkish
#: spontaneous clinical-speech eval set … highest-value open task in the
#: project"*) and HB-A13 (*"name a records eval corpus, and say where it may
#: live"*) are both open. Until one is named, dated and licensed by a human,
#: the quality lane has nothing to measure over, and a figure produced over an
#: unnamed set is precisely the accuracy claim invariant 20 exists to prevent.
BENCHMARK_CORPORA: Mapping[str, BenchmarkCorpus] = {}


class BenchmarkRefused(Exception):
    """A benchmark that cannot honestly run. ``code`` is the wire reason."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class BenchmarkPlan:
    """What a triggered benchmark will do, before it does it."""

    component: str
    kind: BenchmarkKind
    probe: str
    budget_ms: int
    #: The named basis the resulting Measurement will carry. Never blank.
    corpus: str


def plan_benchmark(
    registry: Registry,
    component: str,
    kind: BenchmarkKind,
    corpus_id: str | None = None,
) -> BenchmarkPlan:
    """Resolve a benchmark request, or refuse it with a reason.

    Refusal is the normal outcome for :attr:`BenchmarkKind.QUALITY` today and
    that is the delivered state, not a gap: see :data:`BENCHMARK_CORPORA`.
    """
    try:
        entry = registry.get(component)
    except KeyError:
        raise BenchmarkRefused(
            "unknown_component",
            f"{component!r} is not a row in observability/registry.yaml",
        ) from None

    if kind is BenchmarkKind.LATENCY:
        return BenchmarkPlan(
            component=entry.component,
            kind=kind,
            probe=entry.probe.value,
            budget_ms=entry.budget_ms,
            corpus=(
                f"synthetic probe {entry.probe.value} against the declared host (no patient data)"
            ),
        )

    corpus = BENCHMARK_CORPORA.get(corpus_id) if corpus_id is not None else None
    if corpus is None:
        raise BenchmarkRefused(
            "no_named_corpus",
            "no named evaluation corpus is declared, so a quality figure would have no "
            "corpus and no date to attach to (CLAUDE.md invariant 20; "
            "files/HUMAN_BLOCKERS.md HB-C10 and HB-A13 are open)",
        )
    return BenchmarkPlan(
        component=entry.component,
        kind=kind,
        probe=entry.probe.value,
        budget_ms=entry.budget_ms,
        corpus=f"{corpus.corpus_id} ({corpus.description}, {corpus.licence})",
    )


@dataclass(frozen=True)
class BenchmarkResult:
    """What a run of :func:`run_latency_benchmark` observed.

    ``measurement`` is ``None`` when the environment had no client for this
    component — the runner's own ``SKIPPED`` outcome, which is *visible, not
    faked*. A benchmark that could not reach anything reports that it could
    not reach anything; it does not report a zero.
    """

    plan: BenchmarkPlan
    status: ProbeStatus
    detail: str
    measurement: Measurement | None


def run_latency_benchmark(
    registry: Registry,
    plan: BenchmarkPlan,
    clients: Mapping[str, ProbeFn],
    today: date,
) -> BenchmarkResult:
    """Execute the latency lane: one probe, once, against one component.

    It is the same sweep the 60-second runner performs, narrowed to a single
    row and triggered by hand — so a benchmark and a probe cannot disagree
    about what "healthy" or "over budget" means. ``clients`` is injected:
    tests supply a callable, the dev wiring supplies
    :func:`~intake_probes.runner.build_dev_clients`, and neither this module
    nor any test opens a socket of its own.

    The resulting :class:`Measurement` carries the probe id and the declared
    host as its corpus and the run date as its date, because a latency figure
    with neither attached is a claim about the product rather than an
    observation of one deployment (invariant 20).
    """
    # The whole registry is swept with a client map holding this component
    # alone: every other row answers SKIPPED without touching anything, so
    # exactly one probe runs and the narrowing needs no second code path.
    narrowed = {plan.component: clients[plan.component]} if plan.component in clients else {}
    results: list[ProbeResult] = run_probes_once(registry, narrowed)
    observed = next(result for result in results if result.component == plan.component)
    measurement = (
        Measurement(
            metric="probe_latency",
            value=round(observed.latency_ms, 3),
            unit="ms",
            corpus=plan.corpus,
            measured_on=today,
        )
        if observed.latency_ms is not None
        else None
    )
    return BenchmarkResult(
        plan=plan, status=observed.status, detail=observed.detail, measurement=measurement
    )
