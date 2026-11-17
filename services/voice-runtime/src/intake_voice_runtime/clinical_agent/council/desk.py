"""The verifier as Backend Work: after the bind, off every critical path.

The sequence for one answer, and why each step sits where it does:

1. The primary ``extract_slots`` handler binds the answer under the engine
   lock — the binding triage reads, single-pass, exactly as before — and then
   calls :meth:`VerifierDesk.request_verification`, which appends to a bounded
   deque and returns. Nothing is awaited; nothing is convened.
2. :meth:`VerifierDesk.pump_once` runs on the Backend's event loop. It admits
   the verification against the session budget (an *elective* charge —
   refused outright while HB-O8 leaves the cap undeclared) and against the
   process-wide :class:`AdmissionGate` (a saturated verifier sheds rather than
   queues behind the primary lane). It reads the slot views, convenes the
   draws with a deadline on the injected clock, and adjudicates.
3. The verdict is handed back through the ordinary state lane as a
   ``plan_follow_ups`` Work, so it is applied under the same engine lock, in
   FIFO order after the extraction it verifies, and through the queue's RED
   seal. :class:`ApplyVerdictHandler` compare-and-swaps each action on the
   slot revision, re-runs triage, and returns only add-only candidate flags.
4. A verdict that lands after the session ended, or after a RED sealed the
   queue, is not applied: its red-flag evidence becomes a clinician-inbox
   addendum and triage is re-run anyway (medical review §6).

The Talker is on none of these paths, which is invariant 9 by construction;
``tests/voice/test_council_timing.py`` measures it on a fake clock.
"""

from __future__ import annotations

import enum
import hashlib
import secrets
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Final, Protocol

from intake_voice_runtime.clinical_agent.council.adjudicate import (
    ActionKind,
    SlotView,
    Verdict,
    adjudicate,
    views_of,
)
from intake_voice_runtime.clinical_agent.council.ledger import EventKind, VerifierLedger
from intake_voice_runtime.clinical_agent.council.orchestrator import (
    SpanContext,
    VerifierOrchestrator,
)
from intake_voice_runtime.clinical_agent.council.scope import VerifierScope
from intake_voice_runtime.clinical_agent.fsm import AppendOutcome, VerificationKind
from intake_voice_runtime.clinical_agent.work_queue import (
    BackendAgent,
    QueueSealed,
    StateContext,
    StateEffect,
)
from intake_voice_runtime.extraction.boundary import PatientData
from intake_voice_runtime.metering.components import ChargeClass, MeteredComponent
from intake_voice_runtime.metering.meter import SessionMeter
from intake_voice_runtime.metrics import (
    COUNCIL_ACTIONS_TOTAL,
    COUNCIL_MEMBER_AGREEMENT_TOTAL,
    COUNCIL_VERIFICATIONS_TOTAL,
)
from intake_voice_runtime.ports import Clock, WorkRequest, WorkType, work_key

__all__ = [
    "AddendumReason",
    "AddendumSink",
    "AdmissionGate",
    "ApplyVerdictHandler",
    "ClinicianAddendum",
    "DeskOutcome",
    "RerunReason",
    "TriageRerun",
    "VerdictVault",
    "VerifierDesk",
]

#: How long the desk waits before retrying a busy engine lock. The desk never
#: blocks the event loop on that lock: a state handler may hold it for a whole
#: primary extraction, and the Talker shares the loop.
VIEW_RETRY_S: Final = 0.05
DEFAULT_MAX_PENDING: Final = 8


class DeskOutcome(enum.StrEnum):
    SUBMITTED = "submitted"
    LATE = "late"
    SHED_SATURATED = "shed_saturated"
    REFUSED_BUDGET = "refused_budget"


class RerunReason(enum.StrEnum):
    VERIFICATION_LANDED = "verification_landed"
    VERIFICATION_LATE = "verification_late"


class TriageRerun(Protocol):
    """Re-evaluates the rules engine over the engine's current answers."""

    def rerun(self, reason: RerunReason) -> None: ...


class AddendumReason(enum.StrEnum):
    LATE_RED_FLAG_EVIDENCE = "late_red_flag_evidence"
    LATE_NUMERIC_DOUBT = "late_numeric_doubt"


@dataclass(frozen=True, slots=True)
class ClinicianAddendum:
    """A late finding for the clinician inbox. Ids and codes only."""

    session_id_hash: str
    ref: str
    reason: AddendumReason
    members: tuple[str, ...]


class AddendumSink(Protocol):
    def append(self, addendum: ClinicianAddendum) -> None: ...


@dataclass
class AdmissionGate:
    """Process-wide cap on verifications in flight. Full means shed, not wait."""

    max_in_flight: int
    _in_flight: int = field(default=0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def try_enter(self) -> bool:
        with self._lock:
            if self._in_flight >= self.max_in_flight:
                return False
            self._in_flight += 1
            return True

    def leave(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)


@dataclass
class VerdictVault:
    """Verdicts between the desk and the state lane, keyed by their digest."""

    _held: dict[str, Verdict] = field(default_factory=dict, repr=False)

    def deposit(self, verdict: Verdict, *, input_hash: str) -> str:
        key = hashlib.sha256(f"{input_hash}\x00{verdict!r}".encode()).hexdigest()
        self._held[key] = verdict
        return key

    def take(self, key: str) -> Verdict:
        verdict = self._held.pop(key, None)
        if verdict is None:
            raise LookupError(f"no verdict is held for {key[:12]}…")
        return verdict

    def discard(self, key: str) -> None:
        self._held.pop(key, None)


@dataclass(frozen=True, slots=True)
class _Pending:
    request: WorkRequest
    data: PatientData


@dataclass
class VerifierDesk:
    """One session's verifier. Satisfies ``extraction.handler.VerificationSink``."""

    session_id: str
    tenant_id: str
    agent: BackendAgent
    orchestrator: VerifierOrchestrator
    scope: VerifierScope
    meter: SessionMeter
    gate: AdmissionGate
    triage: TriageRerun
    addenda: AddendumSink
    clock: Clock
    vault: VerdictVault = field(default_factory=VerdictVault)
    ledger: VerifierLedger = field(default_factory=VerifierLedger)
    max_pending: int = DEFAULT_MAX_PENDING
    cache_salt: str = field(default_factory=lambda: secrets.token_hex(16), repr=False)
    _pending: deque[_Pending] = field(default_factory=deque, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _ended: bool = field(default=False, init=False)

    # --- the sink half: called from the primary extraction handler ------------

    def request_verification(self, request: WorkRequest, data: PatientData) -> None:
        """Queue one answer for verification. O(1); awaits and convenes nothing."""
        if self.scope.is_text_only(request.step_id):
            self.ledger.log(EventKind.REFUSED_TEXT_ONLY, ref=request.step_id)
            return
        with self._lock:
            self._pending.append(_Pending(request=request, data=data))
            while len(self._pending) > self.max_pending:
                self._pending.popleft()
                self.ledger.log(EventKind.EVICTED)

    def end_session(self) -> None:
        """From here on every landing is late: addendum and triage re-run."""
        self._ended = True

    @property
    def pending(self) -> int:
        return len(self._pending)

    # --- the pump half: runs on the Backend's event loop -----------------------

    async def pump_once(self) -> DeskOutcome | None:
        with self._lock:
            item = self._pending.popleft() if self._pending else None
        if item is None:
            return None
        if not self.meter.admits(MeteredComponent.LLM_EXTRACTION, ChargeClass.ELECTIVE).admitted:
            return self._count(DeskOutcome.REFUSED_BUDGET, EventKind.REFUSED_BUDGET)
        if not self.gate.try_enter():
            return self._count(DeskOutcome.SHED_SATURATED, EventKind.SHED_SATURATED)
        try:
            views = await self._read_views()
            round_ = await self.orchestrator.convene(
                data=item.data,
                scope=self.scope,
                cache_salt=self.cache_salt,
                context=SpanContext(
                    work_id=work_key(item.request),
                    session_id=self.session_id,
                    tenant_id=self.tenant_id,
                    protocol_hash=item.request.protocol_hash,
                ),
            )
        finally:
            self.gate.leave()
        self.meter.charge_extraction_tokens(
            sum(result.input_tokens for result in round_.results),
            sum(result.output_tokens for result in round_.results),
        )
        verdict = adjudicate(round_, views, self.scope)
        self.ledger.log_round(round_)
        for member_id, agreement in verdict.agreement:
            COUNCIL_MEMBER_AGREEMENT_TOTAL.labels(member=member_id, agreement=agreement.value).inc()
        if self._ended or self.agent.sealed:
            return self._land_late(verdict)
        key = self.vault.deposit(verdict, input_hash=item.request.input_hash)
        try:
            self.agent.submit(
                WorkRequest(
                    session_id=self.session_id,
                    work_type=WorkType.PLAN_FOLLOW_UPS,
                    step_id=item.request.step_id,
                    input_hash=key,
                    protocol_hash=item.request.protocol_hash,
                    engine_version=item.request.engine_version,
                )
            )
        except QueueSealed:
            self.vault.discard(key)
            return self._land_late(verdict)
        COUNCIL_VERIFICATIONS_TOTAL.labels(outcome=DeskOutcome.SUBMITTED.value).inc()
        return DeskOutcome.SUBMITTED

    async def _read_views(self) -> dict[str, SlotView]:
        lock = self.agent.engine_lock
        while not lock.acquire(blocking=False):
            await self.clock.sleep(VIEW_RETRY_S)
        try:
            return views_of(self.agent.engine, self.scope)
        finally:
            lock.release()

    def _land_late(self, verdict: Verdict) -> DeskOutcome:
        session_hash = hashlib.sha256(self.session_id.encode("utf-8")).hexdigest()
        for action in verdict.actions:
            reason = (
                AddendumReason.LATE_NUMERIC_DOUBT
                if action.kind is ActionKind.CONFIRM_BACK
                else AddendumReason.LATE_RED_FLAG_EVIDENCE
            )
            self.addenda.append(
                ClinicianAddendum(
                    session_id_hash=session_hash,
                    ref=action.ref,
                    reason=reason,
                    members=action.members,
                )
            )
            self.ledger.log(EventKind.LATE_ADDENDUM, ref=action.ref, code=reason.value)
        for ref in verdict.narrative_refs:
            self.addenda.append(
                ClinicianAddendum(
                    session_id_hash=session_hash,
                    ref=ref,
                    reason=AddendumReason.LATE_RED_FLAG_EVIDENCE,
                    members=(),
                )
            )
            self.ledger.log(EventKind.LATE_ADDENDUM, ref=ref, code="narrative")
        self.triage.rerun(RerunReason.VERIFICATION_LATE)
        self.ledger.log(EventKind.TRIAGE_RERUN, code=RerunReason.VERIFICATION_LATE.value)
        COUNCIL_VERIFICATIONS_TOTAL.labels(outcome=DeskOutcome.LATE.value).inc()
        return DeskOutcome.LATE

    def _count(self, outcome: DeskOutcome, event: EventKind) -> DeskOutcome:
        self.ledger.log(event)
        COUNCIL_VERIFICATIONS_TOTAL.labels(outcome=outcome.value).inc()
        return outcome


_KIND_OF: Final = {
    ActionKind.REASK_POSITIVE: VerificationKind.REASK,
    ActionKind.CONFIRM_BACK: VerificationKind.CONFIRM_BACK,
}


@dataclass
class ApplyVerdictHandler:
    """The ``plan_follow_ups`` state handler: compare-and-swap, then re-run triage.

    ``confirmation_ceiling`` is the clinical cap on numeric confirm-backs per
    session — INT-432's decision CD-07. While that decision is unsigned it is
    absent, and absent means *no session cap*: each slot is still bounded by
    files/13 §11.1's two attempts, and a D13 confirm-back is never withheld
    on a number nobody signed. A red-flag re-ask is never capped at all —
    safety questions win over the turn budget (medical review §9).
    """

    vault: VerdictVault
    ledger: VerifierLedger
    triage: TriageRerun
    confirmation_ceiling: int | None = None
    _confirm_backs: int = field(default=0, init=False)

    def __call__(self, context: StateContext) -> StateEffect:
        verdict = self.vault.take(context.request.input_hash)
        stale: set[str] = set()
        for action in verdict.actions:
            kind = _KIND_OF.get(action.kind)
            if kind is None:
                result = "flagged"
            elif kind is VerificationKind.CONFIRM_BACK and self._capped():
                result = "ceiling"
            else:
                outcome = context.engine.append_verification(
                    action.ref, kind, action.expected_revision
                )
                if outcome is AppendOutcome.STALE_REVISION:
                    stale.add(action.ref)
                if outcome is AppendOutcome.APPENDED and kind is VerificationKind.CONFIRM_BACK:
                    self._confirm_backs += 1
                result = outcome.value
            COUNCIL_ACTIONS_TOTAL.labels(action=action.kind.value, result=result).inc()
            self.ledger.log(EventKind.ACTION, ref=action.ref, code=f"{action.kind.value}:{result}")
        self.ledger.record_verdict(verdict, stale=frozenset(stale))
        self.triage.rerun(RerunReason.VERIFICATION_LANDED)
        self.ledger.log(EventKind.TRIAGE_RERUN, code=RerunReason.VERIFICATION_LANDED.value)
        # Candidate flags go to the clinician's record, not the presentation:
        # a state-lane effect carries no LLM material (files/12 §7.4), and the
        # flag's reader is the clinician, never the patient's device.
        self.ledger.add_candidate_flags(verdict.candidate_flags)
        return StateEffect()

    def _capped(self) -> bool:
        ceiling = self.confirmation_ceiling
        return ceiling is not None and self._confirm_backs >= ceiling
