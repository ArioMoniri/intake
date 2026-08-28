"""The destruction engine (INT-036; KVKK-7, DEST-2017; sec_row: retention).

Cadence — DEST-2017 (RG 30224, 28.10.2017) via files/06 §1 and §3: periodic
destruction runs at most every 6 months, "with logged reports". The engine
finds its own last periodic run on the audit chain and refuses one younger
than the policy's floor (:class:`PeriodicRunTooSoonError`). The targeted
DSAR single-subject path (KVKK m.11 erasure) is a separate code path the
floor does not block — and it is logged the same way.

The destruction log IS the audit chain: every run appends
``retention.destroyed`` / ``retention.dsar_destroyed`` entries carrying
counts and data classes — ids only, never item content (invariant 6) — plus
one run-summary entry. Riding the INT-016 hash chain buys three properties
at once: append-only, tamper-evident, and the WORM copy's 10-year retention,
which covers DEST-2017's ≥ 3-year destruction-record duty. And because the
executor is routed by :class:`DestroyableClass`, which cannot name the chain,
the log structurally survives every purge the engine performs.

Fail closed, twice: the planner never schedules a ``draft_needs_source``
class, and :meth:`DestructionEngine.execute_plan` re-checks every due item so
even a hand-built plan cannot purge one (:class:`DraftClassDestructionError`).
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from prometheus_client import Counter

from intake_platform.audit import AuditChain, AuditStore
from intake_platform.retention.planner import (
    DestructionPlan,
    DueItem,
    InventoryItem,
    RefusedItem,
    add_months,
    dsar_plan,
    due_for_destruction,
)
from intake_platform.retention.policy import (
    ClassStatus,
    DestroyableClass,
    RetentionPolicy,
)

__all__ = [
    "ACTION_DSAR_DESTROYED",
    "ACTION_DSAR_RUN",
    "ACTION_PERIODIC_DESTROYED",
    "ACTION_PERIODIC_RUN",
    "DestructionEngine",
    "DestructionReport",
    "DraftClassDestructionError",
    "NoExecutorRegisteredError",
    "PeriodicRunTooSoonError",
    "RetentionEngineError",
    "RetentionExecutor",
    "RoutingExecutor",
    "RunKind",
]

ACTION_PERIODIC_DESTROYED = "retention.destroyed"
ACTION_PERIODIC_RUN = "retention.periodic_run"
ACTION_DSAR_DESTROYED = "retention.dsar_destroyed"
ACTION_DSAR_RUN = "retention.dsar_run"

_SCOPE_PERIODIC = "legal:kvkk-7/dest-2017"
_SCOPE_DSAR = "legal:kvkk-11/erasure"

# Catalogued in observability/metrics_catalog.yaml (inv. 13); the threat-model
# `retention` row's signal — a destruction job failing silently is the [De]
# threat, so success and refusal are both counted.
RETENTION_DESTRUCTION_RUNS_TOTAL = Counter(
    "retention_destruction_runs_total",
    "Destruction runs by kind (periodic/dsar) and outcome (completed/refused_floor).",
    ["kind", "outcome"],
)
RETENTION_DESTROYED_ITEMS_TOTAL = Counter(
    "retention_destroyed_items_total",
    "Items destroyed by the retention engine, by policy data class.",
    ["data_class"],
)


class RetentionEngineError(Exception):
    """Base for engine refusals."""


class PeriodicRunTooSoonError(RetentionEngineError):
    """A periodic run younger than the DEST-2017 floor."""


class DraftClassDestructionError(RetentionEngineError):
    """A plan tried to purge a draft_needs_source class — refused, fail closed."""


class NoExecutorRegisteredError(RetentionEngineError):
    """A due class with nothing wired to destroy it — refused, never skipped."""


class RunKind(enum.StrEnum):
    PERIODIC = "periodic"
    DSAR = "dsar"


class RetentionExecutor(Protocol):
    """The executor seam: destruction is a per-class capability, routed by
    the closed DestroyableClass enum — which is the type-level reason the
    audit chain and the destruction log can never be destruction targets
    (the enum cannot name them, so no executor can be asked). A Protocol so
    test fakes and the SQLAlchemy wiring stay structurally typed."""

    def destroy(self, data_class: DestroyableClass, item_refs: Sequence[str]) -> int: ...


Destroyer = Callable[[Sequence[str]], int]


class RoutingExecutor:
    """Routes each class to its registered destroyer; an unregistered class is
    a typed refusal, because silently skipping a due class is exactly the
    [De] threat the sec_row names (a destruction job failing silently)."""

    def __init__(self, routes: Mapping[DestroyableClass, Destroyer]) -> None:
        self._routes = dict(routes)

    def destroy(self, data_class: DestroyableClass, item_refs: Sequence[str]) -> int:
        destroyer = self._routes.get(data_class)
        if destroyer is None:
            raise NoExecutorRegisteredError(
                f"no destroyer registered for {data_class.value!r}: the run must "
                "fail loudly rather than leave the class quietly undestroyed"
            )
        return destroyer(item_refs)


@dataclass(frozen=True)
class DestructionReport:
    """The "logged report" of 06 §3, as a value: what ran, what was destroyed
    per class, and what was refused with reasons (the draft_needs_source rows
    surface here on every run until a human sources them)."""

    run_id: str
    kind: RunKind
    ran_at: datetime
    destroyed: dict[DestroyableClass, int]
    refused: tuple[RefusedItem, ...]


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class DestructionEngine:
    """Plans via the pure planner, destroys via the routed executor, logs via
    the hash chain. ``chain`` and ``store`` must wrap the same underlying
    audit storage: the chain writes the destruction log, the store is read to
    find the last periodic run for the floor check."""

    def __init__(
        self,
        *,
        policy: RetentionPolicy,
        chain: AuditChain,
        store: AuditStore,
        executor: RetentionExecutor,
        actor: str = "svc-retention",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = policy
        self._chain = chain
        self._store = store
        self._executor = executor
        self._actor = actor
        self._clock = clock if clock is not None else _utc_now

    # --- cadence ------------------------------------------------------------------

    def last_periodic_run(self) -> datetime | None:
        latest: datetime | None = None
        for entry in self._store.entries():
            if entry.action != ACTION_PERIODIC_RUN:
                continue
            stamp = datetime.fromisoformat(entry.timestamp_utc)
            if latest is None or stamp > latest:
                latest = stamp
        return latest

    def _check_floor(self, now: datetime) -> None:
        last = self.last_periodic_run()
        if last is None:
            return
        next_allowed = add_months(last, self._policy.periodic_destruction.interval_months)
        if now < next_allowed:
            RETENTION_DESTRUCTION_RUNS_TOTAL.labels(
                kind=RunKind.PERIODIC.value, outcome="refused_floor"
            ).inc()
            raise PeriodicRunTooSoonError(
                "periodic destruction runs at most every "
                f"{self._policy.periodic_destruction.interval_months} months "
                f"(DEST-2017, RG 30224): last run {last.isoformat()}, next allowed "
                f"{next_allowed.isoformat()} — use the targeted DSAR path for a "
                "single-subject erasure inside the window"
            )

    # --- the two legal paths ---------------------------------------------------------

    def run_periodic(self, inventory: Sequence[InventoryItem]) -> DestructionReport:
        now = self._clock()
        plan = due_for_destruction(now, inventory, self._policy)
        return self.execute_plan(plan, kind=RunKind.PERIODIC)

    def run_dsar(self, subject_ref: str, inventory: Sequence[InventoryItem]) -> DestructionReport:
        now = self._clock()
        plan = dsar_plan(now, subject_ref, inventory, self._policy)
        return self.execute_plan(plan, kind=RunKind.DSAR, subject_ref=subject_ref)

    # --- execution --------------------------------------------------------------------

    def _refuse_wrong_path(self, item: DueItem, kind: RunKind) -> None:
        row = self._policy.class_for(item.data_class)
        if row.status is ClassStatus.DRAFT_NEEDS_SOURCE:
            raise DraftClassDestructionError(
                f"{item.data_class.value!r} is draft_needs_source: 06 §3 supplies no "
                "duration, so nothing may be destroyed — fail closed, ask the human"
            )
        if kind is RunKind.PERIODIC and row.destruction_path == "dsar_only":
            raise RetentionEngineError(
                f"{item.data_class.value!r} is dsar_only and cannot ride a periodic run"
            )

    def execute_plan(
        self,
        plan: DestructionPlan,
        *,
        kind: RunKind,
        subject_ref: str | None = None,
    ) -> DestructionReport:
        """The single choke point: floor check (periodic), draft re-check
        (both paths), destroy, log, count."""
        now = self._clock()
        for item in plan.due:
            self._refuse_wrong_path(item, kind)
        if kind is RunKind.PERIODIC:
            self._check_floor(now)
        elif subject_ref is None:
            raise ValueError("a DSAR run names its subject: subject_ref is required")

        grouped: dict[DestroyableClass, list[str]] = {}
        for item in plan.due:
            grouped.setdefault(item.data_class, []).append(item.item_ref)

        destroyed_action = (
            ACTION_PERIODIC_DESTROYED if kind is RunKind.PERIODIC else ACTION_DSAR_DESTROYED
        )
        scope = _SCOPE_PERIODIC if kind is RunKind.PERIODIC else _SCOPE_DSAR
        run_id = uuid.uuid4().hex
        destroyed: dict[DestroyableClass, int] = {}
        for data_class, refs in grouped.items():
            count = self._executor.destroy(data_class, refs)
            destroyed[data_class] = count
            RETENTION_DESTROYED_ITEMS_TOTAL.labels(data_class=data_class.value).inc(count)
            # Counts and data classes only — an item ref never reaches the
            # chain from here, and item content could not (invariant 6).
            self._chain.append(
                actor=self._actor,
                action=destroyed_action,
                resource_ref=f"class:{data_class.value}:count:{count}",
                consent_scope_ref=scope,
            )
        total = sum(destroyed.values())
        if kind is RunKind.PERIODIC:
            summary_ref = f"run:{run_id}:classes:{len(destroyed)}:items:{total}"
            summary_action = ACTION_PERIODIC_RUN
        else:
            summary_ref = (
                f"dsar:{run_id}:subject:{subject_ref}:classes:{len(destroyed)}:items:{total}"
            )
            summary_action = ACTION_DSAR_RUN
        self._chain.append(
            actor=self._actor,
            action=summary_action,
            resource_ref=summary_ref,
            consent_scope_ref=scope,
        )
        RETENTION_DESTRUCTION_RUNS_TOTAL.labels(kind=kind.value, outcome="completed").inc()
        return DestructionReport(
            run_id=run_id, kind=kind, ran_at=now, destroyed=destroyed, refused=plan.refused
        )
