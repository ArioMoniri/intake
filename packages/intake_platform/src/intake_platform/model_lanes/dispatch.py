"""Running one call on a role's assignment (INT-428, ADR-035).

INT-439 (00_STATE §3 D19): every hosted attempt — the first and a fallback
retry alike — is admitted by the router's :class:`~intake_platform.
model_lanes.spend.HostedSpendGate` before it runs and charged after, so the
synthetic deployment's hosted lanes stop at the owner's 80 USD monthly cap.

:func:`dispatch` is the one place a routed gateway runs a call: it refuses an
unavailable assignment with a code, times the call, meters it, and — outside a
session, when a self-hosted call fails and the role has an admitted fallback
(synthetic deployments only, by construction) — retries it once on the hosted
provider. Inside a session the assignment is frozen and a failure is a
refusal. The adapters behind the existing interfaces (``ExtractionGateway``,
``Transcriber``, ``TtsGateway``) are thin shims over it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from intake_platform.model_lanes.health import LaneIdentityMismatch, LaneRefused
from intake_platform.model_lanes.hosted import HostedLaneUnavailable, HostedUsage
from intake_platform.model_lanes.metrics import (
    MODEL_LANE_AUDIO_SECONDS_TOTAL,
    MODEL_LANE_CALLS_TOTAL,
    MODEL_LANE_CHARACTERS_TOTAL,
    MODEL_LANE_FALLBACK_TOTAL,
    MODEL_LANE_LATENCY_SECONDS,
    MODEL_LANE_REFUSED_TOTAL,
    MODEL_LANE_TOKENS_TOTAL,
)
from intake_platform.model_lanes.model import Lane, ModelRole, RouteKind
from intake_platform.model_lanes.router import (
    LaneRouter,
    ModelAssignment,
    SessionLanes,
    target_role,
)
from intake_platform.model_lanes.spend import CODE_UNMETERED, HostedSpendGate, SpendGateRefused

__all__ = ["LaneResult", "dispatch", "verify_served_model"]


@dataclass(frozen=True)
class LaneResult[T]:
    """A backend's answer and what it reported using."""

    value: T
    usage: HostedUsage = field(default_factory=HostedUsage)


def verify_served_model(assignment: ModelAssignment, served: str | None) -> None:
    """The per-call model check: a backend that names the model it served
    must name the one it was asked for. ``None`` (the wire carries no model
    field) is checked by the identity probe instead."""
    if served is None or assignment.model is None:
        return
    if served != assignment.model.wire:
        raise LaneIdentityMismatch("the backend answered as another model")


def _labels(assignment: ModelAssignment) -> dict[str, str]:
    route = assignment.route
    if route is None:  # pragma: no cover - only available assignments are attempted
        raise ValueError("an unavailable assignment is never attempted")
    return {
        "lane": assignment.lane.value,
        "route": route.kind.value,
        "provider": route.provider_label,
    }


def _meter(assignment: ModelAssignment, usage: HostedUsage) -> None:
    labels = _labels(assignment)
    if usage.input_tokens:
        MODEL_LANE_TOKENS_TOTAL.labels(**labels, direction="input").inc(usage.input_tokens)
    if usage.output_tokens:
        MODEL_LANE_TOKENS_TOTAL.labels(**labels, direction="output").inc(usage.output_tokens)
    if usage.audio_seconds:
        MODEL_LANE_AUDIO_SECONDS_TOTAL.labels(**labels).inc(usage.audio_seconds)
    if usage.characters:
        MODEL_LANE_CHARACTERS_TOTAL.labels(**labels).inc(usage.characters)


def _model_id(assignment: ModelAssignment) -> str | None:
    return assignment.model.model_id if assignment.model is not None else None


def _hosted(assignment: ModelAssignment) -> bool:
    return assignment.route is not None and assignment.route.kind is RouteKind.HOSTED


def _admit_spend(router: LaneRouter, lane: Lane, assignment: ModelAssignment) -> None:
    """INT-439: a hosted call runs only inside the monthly elective cap."""
    if not _hosted(assignment):
        return
    gate: HostedSpendGate | None = router.spend
    if gate is None:
        raise _refuse(lane, CODE_UNMETERED)
    try:
        gate.admit(assignment.provider, _model_id(assignment))
    except SpendGateRefused as refused:
        raise _refuse(lane, refused.code) from None


def _charge_spend(router: LaneRouter, assignment: ModelAssignment, usage: HostedUsage) -> None:
    if _hosted(assignment) and router.spend is not None:
        router.spend.charge(assignment.provider, _model_id(assignment), usage)


def _attempt[T](
    assignment: ModelAssignment,
    call: Callable[[ModelAssignment], LaneResult[T]],
    failures: tuple[type[BaseException], ...],
) -> LaneResult[T]:
    labels = _labels(assignment)
    caught: tuple[type[BaseException], ...] = (
        HostedLaneUnavailable,
        LaneIdentityMismatch,
        *failures,
    )
    started = time.perf_counter()
    try:
        result = call(assignment)
    except caught:
        MODEL_LANE_CALLS_TOTAL.labels(**labels, outcome="failed").inc()
        raise
    MODEL_LANE_LATENCY_SECONDS.labels(**labels).observe(time.perf_counter() - started)
    MODEL_LANE_CALLS_TOTAL.labels(**labels, outcome="ok").inc()
    _meter(assignment, result.usage)
    return result


def _refuse(lane: Lane, code: str) -> LaneRefused:
    MODEL_LANE_REFUSED_TOTAL.labels(lane=lane.value, reason=code).inc()
    return LaneRefused(code)


def _count_fallback(assignment: ModelAssignment) -> None:
    route = assignment.route
    if assignment.fallback and route is not None and route.provider is not None:
        MODEL_LANE_FALLBACK_TOTAL.labels(
            lane=assignment.lane.value, provider=route.provider.value
        ).inc()


def dispatch[T](
    router: LaneRouter,
    role: str | ModelRole | Lane,
    *,
    tenant_id: str | None,
    call: Callable[[ModelAssignment], LaneResult[T]],
    failures: tuple[type[BaseException], ...] = (),
    session: SessionLanes | None = None,
) -> T:
    """Run one call on the role's assignment.

    With a ``session`` the assignment is the session's frozen one and a failed
    call is a refusal — never a retry on another provider. Without one, a
    failed self-hosted call quarantines the lane and is retried once on an
    admitted hosted fallback (synthetic deployments only, by construction).
    ``failures`` are the self-hosted backends' own "unavailable" exceptions;
    anything else — a parser's or a guard's refusal — propagates untouched.
    """
    target = target_role(role)
    assignment = (
        session.resolve(target)
        if session is not None
        else router.assign(target, tenant_id=tenant_id)
    )
    if not assignment.available or assignment.route is None:
        raise _refuse(target.lane, assignment.reason)
    _count_fallback(assignment)
    _admit_spend(router, target.lane, assignment)
    try:
        result = _attempt(assignment, call, failures)
        _charge_spend(router, assignment, result.usage)
        return result.value
    except HostedLaneUnavailable as failure:
        raise _refuse(target.lane, failure.code) from None
    except LaneIdentityMismatch:
        if assignment.route.kind is RouteKind.SELF_HOSTED:
            router.health.report_failure(target.lane)
        raise _refuse(target.lane, LaneIdentityMismatch.code) from None
    except failures:
        if assignment.route.kind is not RouteKind.SELF_HOSTED:
            raise _refuse(target.lane, f"{assignment.route.kind.value}_failed") from None
    router.health.report_failure(target.lane)
    if session is not None:
        raise _refuse(target.lane, "self_hosted_failed")
    retry = router.assign(target, tenant_id=tenant_id)
    if not retry.available or retry.route is None or retry.route.kind is not RouteKind.HOSTED:
        raise _refuse(target.lane, "self_hosted_failed")
    _count_fallback(retry)
    _admit_spend(router, target.lane, retry)
    try:
        result = _attempt(retry, call, failures)
        _charge_spend(router, retry, result.usage)
        return result.value
    except HostedLaneUnavailable as failure:
        raise _refuse(target.lane, failure.code) from None
    except LaneIdentityMismatch:
        raise _refuse(target.lane, LaneIdentityMismatch.code) from None
