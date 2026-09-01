"""The IntakeEngine — a deterministic protocol FSM, no LLM inside (INT-081).

files/03 §5 names the inputs and the outputs: ``apply_extraction(step_id,
slot_updates, clarification_needed)`` in; ``next_step()``, ``section_done``
and ``follow_ups[]`` out; *"Pure, replayable from the event log; protocol
hash pinned per session."* files/13 §9.2 makes purity concrete — the state
is a fold and there is **no wall clock**: ``now`` is the session's
``reference_time``, which is the only time value this class holds.

**Ask ahead, reconcile behind** (files/03 §4.5; ADR-011). :meth:`mark_asked`
puts a step into ``ASKED_PENDING`` — the ask-ahead bookkeeping state of
files/13 §9.3 — and the very next :meth:`next_step` already returns the step
after it. Nothing here awaits anything: the engine is the Layer-B side of
ADR-009 and every method returns a value immediately.

**The ask-ahead race is closed by discarding, never by storing** (files/13
§11.3). When a landed extraction closes the gate of a step that is still
``ASKED_PENDING``, that step is moved to :attr:`EngineSnapshot.invalidated`,
its answer is dropped, and any answer that arrives for it afterwards is
dropped too. Storing it would be fabricated clinical data.

**Nothing binds to a question that was not asked.** An update for a step in
any state other than ``ASKED_PENDING`` is ignored. Inferring a slot from a
neighbouring answer is how a note comes to read as *elicited* when it was
*inferred* — the exact failure mode files/13 §9.6 refuses runtime selection
over — so the engine under-binds by construction.

No model, gateway or adapter is reachable from this module: the only inputs
are a resolved protocol, the session clock and the patient's confirmed
facts. CLAUDE.md invariant 1 lives one layer out, in
``packages/protocols/triage``, and nothing here can produce a triage level
at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from clinical_schemas.common import JsonValue
from clinical_schemas.overlay import PatientOverlay
from clinical_schemas.session import AnswerState
from protocols.compile.resolve import ResolvedProtocol
from protocols.triage.context import canonical_scalar
from protocols.triage.expr import Truth

from intake_voice_runtime.clinical_agent.coverage import MustAskCoverage
from intake_voice_runtime.clinical_agent.coverage import must_ask_coverage as _compute_coverage
from intake_voice_runtime.clinical_agent.delta import DeltaDecision, decide_delta
from intake_voice_runtime.clinical_agent.plan import EngineStep, StepPriority, build_plan
from intake_voice_runtime.ports import EngineSnapshot
from intake_voice_runtime.steps import NextStep, Step, StepKind

__all__ = ["MAX_CLARIFICATION_ATTEMPTS", "EngineError", "IntakeEngine"]

MAX_CLARIFICATION_ATTEMPTS = 2
"""files/13 §11.1: *"bounded at 2 attempts … There is no third attempt: an
unbounded clarification loop is both a turn-budget bomb and a CSAT
failure."* After the second, the slot is ``UNCLEAR`` and enters the gaps."""


class EngineError(ValueError):
    """An input the engine refuses to act on."""


@dataclass(frozen=True, slots=True)
class _ReEntry:
    """One queued class-3 clarification (files/13 §9.1, §11.1)."""

    step_id: str
    origin: str
    text_tr: str


def _same_value(left: JsonValue, right: JsonValue) -> bool:
    """Exact identity of value *and* type.

    ``True == 1`` in Python, and a confirm step that read a boolean
    re-confirmation as an unchanged integer would silently keep a prior
    value the patient just contradicted.
    """
    return type(left) is type(right) and bool(left == right)


class IntakeEngine:
    """The deterministic FSM over one resolved protocol and one session."""

    def __init__(
        self,
        *,
        protocol: ResolvedProtocol,
        reference_time: datetime,
        overlay_facts: PatientOverlay | None = None,
    ) -> None:
        self._plan = build_plan(protocol)
        self._by_id = self._plan.by_id
        self._reference_time = reference_time
        self._delta = decide_delta(plan=self._plan, overlay_facts=overlay_facts, now=reference_time)
        self._prefills = {prefill.slot_ref: prefill for prefill in self._delta.prefills}
        self._states: dict[str, AnswerState] = {
            step.step_id: AnswerState.NOT_ASKED for step in self._plan.steps
        }
        self._values: dict[str, JsonValue] = {}
        self._invalidated: list[str] = []
        self._data_gaps: list[str] = []
        self._clarify_attempts: dict[str, int] = {}
        self._reentries: dict[str, _ReEntry] = {}
        self._asked_reentries: set[str] = set()
        self._version = 0

    # --- reads -------------------------------------------------------------

    @property
    def reference_time(self) -> datetime:
        """The session's ``now``, stamped once (files/13 §9.2). No wall clock."""
        return self._reference_time

    @property
    def delta(self) -> DeltaDecision:
        """What the patient's overlay did to this session (files/09 §3)."""
        return self._delta

    @property
    def snapshot(self) -> EngineSnapshot:
        """The immutable snapshot ``protocol_next`` reads (files/12 §7.2)."""
        offered = self.frontier()
        return EngineSnapshot(
            version=self._version,
            next_step=offered[0] if offered else None,
            awaiting=tuple(
                step.step_id
                for step in self._plan.steps
                if self._states[step.step_id] is AnswerState.ASKED_PENDING
            ),
            invalidated=tuple(self._invalidated),
        )

    @property
    def follow_ups(self) -> tuple[str, ...]:
        """Queued clarification re-entries (files/03 §5 ``follow_ups[]``)."""
        return tuple(self._reentries)

    @property
    def data_gaps(self) -> tuple[str, ...]:
        """Slots that went ``UNCLEAR`` after two attempts (files/13 §11.1)."""
        return tuple(self._data_gaps)

    @property
    def section_done(self) -> tuple[str, ...]:
        """Sections with nothing offered and nothing awaiting (files/03 §5)."""
        open_ids = {self._origin_of(step.step_id) for step in self.frontier()}
        open_ids |= {
            step_id for step_id, state in self._states.items() if state is AnswerState.ASKED_PENDING
        }
        done: list[str] = []
        for step in self._plan.steps:
            if step.section_id in done:
                continue
            section_steps = [
                other for other in self._plan.steps if other.section_id == step.section_id
            ]
            if all(other.step_id not in open_ids for other in section_steps):
                done.append(step.section_id)
        return tuple(done)

    def state_of(self, step_id: str) -> AnswerState:
        """The step's answer state (files/13 §9.3)."""
        state = self._states.get(step_id)
        if state is None:
            raise EngineError(f"no such step: {step_id!r}")
        return state

    def value_of(self, step_id: str) -> JsonValue:
        """The bound value, or ``None`` where nothing is bound."""
        return self._values.get(step_id)

    def frontier(self) -> tuple[Step, ...]:
        """The offered steps, sorted ``(priority_class, order, id)``.

        files/13 §9.2: candidates are the steps still to ask whose gate is
        TRUE and whose ``skip_if`` has not retired them. ``UNCLEAR`` steps
        are **not** re-offered — §9.2 lists them as candidates, but §11.1
        forbids a third attempt and §9.5's termination check measures
        ``|NOT_ASKED| + |queued re-entries|``, which a re-offered ``UNCLEAR``
        step would never decrease. The gap is recorded in
        :attr:`data_gaps` instead.
        """
        lookup = self._lookup
        offered: list[tuple[tuple[int, int, str], Step]] = []
        for index, reentry in enumerate(self._reentries.values()):
            if reentry.step_id in self._asked_reentries:
                continue
            offered.append(
                (
                    (int(StepPriority.REENTRY), index, reentry.step_id),
                    Step(
                        step_id=reentry.step_id,
                        kind=StepKind.FOLLOW_UP,
                        text_tr=reentry.text_tr,
                    ),
                )
            )
        for step in self._plan.steps:
            step_id = step.step_id
            if self._states[step_id] is not AnswerState.NOT_ASKED:
                continue
            if step_id in self._invalidated:
                continue
            if self._plan.gate_truth(step_id, lookup) is not Truth.TRUE:
                continue
            if self._plan.retired(step_id, lookup):
                continue
            offered.append((step.sort_key, self._offer(step)))
        offered.sort(key=lambda item: item[0])
        return tuple(step for _, step in offered)

    def next_step(self) -> NextStep | None:
        """The head of the frontier, stamped with the snapshot version."""
        offered = self.frontier()
        return NextStep.of(offered[0], self._version) if offered else None

    def must_ask_coverage(self) -> MustAskCoverage:
        """``protocol.must_ask_coverage`` over this session's must-ask steps."""
        lookup = self._lookup
        must_ask = [step for step in self._plan.steps if step.must_ask]
        return _compute_coverage(
            states={step.step_id: self._states[step.step_id] for step in must_ask},
            gates={step.step_id: self._plan.gate_truth(step.step_id, lookup) for step in must_ask},
        )

    # --- writes ------------------------------------------------------------

    def mark_asked(self, step_id: str) -> None:
        """Record that the Talker spoke ``step_id`` — ask-ahead starts here.

        Only a step the frontier is currently offering may be asked: the
        frontier is the protocol's decision about what is askable, and a
        question put outside it was never opened by a gate.
        """
        if step_id not in {step.step_id for step in self.frontier()}:
            raise EngineError(
                f"{step_id!r} is not on the frontier — the engine offers what may be "
                "asked, and a step outside it has no open gate (files/13 §9.2)"
            )
        if step_id in self._reentries:
            self._asked_reentries.add(step_id)
        else:
            self._states[step_id] = AnswerState.ASKED_PENDING
        self._version += 1

    def apply_extraction(
        self,
        step_id: str,
        slot_updates: Mapping[str, JsonValue],
        clarification_needed: bool = False,
    ) -> None:
        """Reconcile behind (files/03 §5 input signature).

        ``step_id`` may name a plan step or one of its clarification
        re-entries; either way the answer binds to the origin slot.
        """
        origin = self._origin_of(step_id)
        self._version += 1
        if origin in self._invalidated:
            # files/13 §11.3: discard the answer rather than storing it, and
            # record nothing for that slot
            self._drop_reentry(step_id)
            return
        if clarification_needed:
            self._clarify(origin, consumed=step_id)
            return
        self._drop_reentry(step_id)
        self._bind(slot_updates)
        self._sweep_invalidated()

    # --- internals ---------------------------------------------------------

    def _lookup(self, ref: str) -> bool | Decimal | str | None:
        """Canonical scalar for a gate atom; ``None`` reads Unknown.

        Only ``ASKED_PRESENT`` / ``ASKED_ABSENT`` carry a readable value —
        the same three-valued reading ``protocols.triage.context`` applies,
        so a gate and a red-flag predicate agree about every slot.
        """
        if self._states.get(ref) not in {
            AnswerState.ASKED_PRESENT,
            AnswerState.ASKED_ABSENT,
        }:
            return None
        return canonical_scalar(self._values.get(ref))

    def _offer(self, step: EngineStep) -> Step:
        """The form a step is offered in: confirm under delta, else the ask."""
        prefill = self._prefills.get(step.step_id)
        if prefill is not None:
            return Step(step_id=step.step_id, kind=StepKind.CONFIRM, text_tr=prefill.confirm_tr)
        return Step(
            step_id=step.step_id,
            kind=step.full_kind,
            text_tr=step.ask_tr,
            choices_tr=step.choices_tr,
        )

    def _origin_of(self, step_id: str) -> str:
        reentry = self._reentries.get(step_id)
        if reentry is not None:
            return reentry.origin
        if step_id in self._by_id:
            return step_id
        raise EngineError(f"no such step: {step_id!r}")

    def _drop_reentry(self, step_id: str) -> None:
        if self._reentries.pop(step_id, None) is not None:
            self._asked_reentries.discard(step_id)

    def _clarify(self, origin: str, *, consumed: str) -> None:
        """Queue a class-3 re-entry, or record the gap (files/13 §11.1)."""
        self._drop_reentry(consumed)
        step = self._by_id[origin]
        attempts = self._clarify_attempts.get(origin, 0)
        if step.follow_up_tr is None or attempts >= MAX_CLARIFICATION_ATTEMPTS:
            # no follow_up_tr means no verbatim text to speak, and invariant
            # 10 leaves no improvised alternative — the honest move is the gap
            self._give_up(origin)
            return
        attempts += 1
        self._clarify_attempts[origin] = attempts
        reentry_id = f"{origin}/clarify/{attempts}"
        self._reentries[reentry_id] = _ReEntry(
            step_id=reentry_id, origin=origin, text_tr=step.follow_up_tr
        )

    def _give_up(self, origin: str) -> None:
        self._states[origin] = AnswerState.UNCLEAR
        if origin not in self._data_gaps:
            self._data_gaps.append(origin)
        self._drop_origin_reentries(origin)

    def _drop_origin_reentries(self, origin: str) -> None:
        for reentry_id in [key for key, entry in self._reentries.items() if entry.origin == origin]:
            self._drop_reentry(reentry_id)

    def _bind(self, slot_updates: Mapping[str, JsonValue]) -> None:
        for ref, value in slot_updates.items():
            if self._states.get(ref) is not AnswerState.ASKED_PENDING:
                continue  # nothing binds to a question that was not asked
            prefill = self._prefills.pop(ref, None)
            if prefill is not None and not _same_value(value, prefill.value):
                # files/09 §3 "full HPI only on change": a confirm_tr question
                # is not the slot's own question, so a contradicting answer
                # re-opens the full ask instead of binding to the confirm
                self._states[ref] = AnswerState.NOT_ASKED
                continue
            self._values[ref] = value
            self._states[ref] = (
                AnswerState.ASKED_ABSENT if value is False else AnswerState.ASKED_PRESENT
            )

    def _sweep_invalidated(self) -> None:
        """files/13 §11.3: a pending step whose gate just closed is dropped."""
        lookup = self._lookup
        for step in self._plan.steps:
            step_id = step.step_id
            if self._states[step_id] is not AnswerState.ASKED_PENDING:
                continue
            if self._plan.gate_truth(step_id, lookup) is Truth.TRUE and not self._plan.retired(
                step_id, lookup
            ):
                continue
            self._states[step_id] = AnswerState.NOT_ASKED
            self._values.pop(step_id, None)
            self._invalidated.append(step_id)
            self._drop_origin_reentries(step_id)
