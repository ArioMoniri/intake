"""The rules engine, run on every Work that binds a slot a served rule reads (INT-521).

INT-518 made every ``base.intake`` code slot bind in a live session, and that
exposed the next gap (GitHub #887): no production module called
``protocols.triage.evaluate_triage`` during a session, and no handler set
``StateEffect.triage_update``. The answers a red-flag rule needs bound, and
nothing evaluated them, so a chest-pain RED could not fire from the
conversation.

:class:`SessionTriage` is that evaluation, held by the session's
:class:`~intake_voice_runtime.clinical_agent.work_queue.BackendAgent`. After a
state-lane Work completes, the queue compares the answers the served rules
read before and after it; when one was bound, it asks this class for a
determination and passes it on as the Work's ``triage_update``. From there
the path already existed: the queue derives ``preempt`` from a RED and from
nothing else, authorises it against the pinned rule ids, tells the clinician
route, settles and seals (files/12 §7.1); the Talker drains it and runs the
pre-positioned RED script over the data channel (invariant 21).

What it holds to:

- **Only ``packages/protocols/triage`` produces the level** (invariant 1).
  This module builds a :class:`~protocols.triage.TriageContext` from the
  engine's bound answers and returns ``evaluate_triage(...).result`` as it
  comes. It names no level and builds no result.
- **The served rules are the pinned protocol's own**: the pack rules and the
  sibling ``base.life_threat`` set the resolved document carries
  (files/12 §1). A compiled document holds no ``draft_needs_source`` rule
  (files/04 §8.1 rule 3); one that does is refused when the session is
  composed, by the engine itself, rather than at the first evaluation.
- **The location is the caller's.** files/02 §5.3 Axis 3 derives it from the
  visit lifecycle and the mode; it is handed in, required, never defaulted
  here (invariant 21).
- **Only a bound answer is a value.** ``ASKED_PRESENT`` and ``ASKED_ABSENT``
  carry their value; every other state is absent from the context and reads
  Unknown (files/12 §1.1), the same reading the engine's own gates use.
- **One exception, decided by CD-05: an UNCLEAR onset anchor** (INT-522). An
  answer that never fitted a closed onset choice is recorded UNCLEAR, and
  CD-05 ``unresolved_answer`` resolves it to the more acute reading, the
  reference day. Where the session carries
  :class:`~intake_voice_runtime.clinical_agent.anchors.SessionAnchors`, such
  an anchor is read as that day — before and after every Work, so the Work
  that spent the last clarification is evaluated — and every other UNCLEAR
  slot still reads Unknown. Since INT-546 (CD-05 round 3 item 10) an anchor
  the session's close found never asked, with chest pain affirmed, is read as
  CD-05's ``never_asked_at_close`` day the same way; the slot stays NOT_ASKED.
- **A read is spelled ``<section>.<slot>`` or bare ``<slot>``** (files/12
  §2.4). Each spelling is mapped to the step it names; a bare name two
  sections share names neither and reads Unknown, because guessing between
  two slots is how a rule comes to fire on the wrong answer.
- **It runs in Layer B only.** The queue calls it under the engine lock,
  inside ``run_pending``. The Talker holds no reference to it and awaits
  nothing it does (invariant 9).

Ids only (invariant 6): :attr:`SessionTriage.evaluated` is the receipt, a
list of content-addressed Work ids.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, RulesTriageResult
from protocols.anchor_choices import AnchorResolution
from protocols.compile.resolve import ResolvedProtocol
from protocols.compile.rule_reads import rule_reads
from protocols.dsl import RedFlagRule
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage

from intake_voice_runtime.clinical_agent.anchors import SessionAnchors
from intake_voice_runtime.clinical_agent.fsm import IntakeEngine

__all__ = [
    "BoundReads",
    "SessionTriage",
    "UnreadableRule",
    "served_rules",
    "step_spellings",
]

#: The read slots' bound answers, ``(step_id, state, value)``, in step order:
#: what the queue compares before and after a Work.
type BoundReads = tuple[tuple[str, AnswerState, JsonValue], ...]


class UnreadableRule(ValueError):
    """A served rule whose reads cannot be listed, so cannot be watched."""


def served_rules(protocol: ResolvedProtocol) -> tuple[RedFlagRule, ...]:
    """The red-flag rules a session pinned to ``protocol`` evaluates.

    The pack's own rules and the sibling life-threat set, side by side and
    never merged (files/12 §1): both are what the compiled document serves.
    """
    return (*protocol.red_flags, *protocol.life_threat_rules)


def step_spellings(spellings: Collection[str], step_ids: Collection[str]) -> dict[str, str]:
    """``{spelling: step_id}`` for every spelling that names exactly one step.

    A dotted spelling names the step of the same id. A bare one names the step
    whose slot key it is, when exactly one step has that key. Anything else
    names nothing and is left out, so it reads Unknown.
    """
    by_key: dict[str, list[str]] = {}
    for step_id in step_ids:
        by_key.setdefault(step_id.split(".", 1)[-1], []).append(step_id)
    resolved: dict[str, str] = {}
    for spelling in spellings:
        if spelling in step_ids:
            resolved[spelling] = spelling
        elif "." not in spelling and len(by_key.get(spelling, ())) == 1:
            resolved[spelling] = by_key[spelling][0]
    return resolved


@dataclass
class SessionTriage:
    """One session's served rules, the slots they read, and where the patient is."""

    rules: tuple[RedFlagRule, ...]
    location: RedLocation
    #: ``{spelling a rule uses: step_id}``, for every spelling that resolves.
    spellings: Mapping[str, str]
    #: CD-05's anchors (INT-522), so an UNCLEAR onset reads its decided day.
    anchors: SessionAnchors | None = None
    #: Content-addressed Work ids, in the order they were evaluated.
    evaluated: list[str] = field(default_factory=list, init=False)

    @classmethod
    def for_protocol(
        cls,
        protocol: ResolvedProtocol,
        *,
        location: RedLocation,
        reference_time: datetime,
        anchors: SessionAnchors | None = None,
    ) -> SessionTriage:
        """Pin the protocol's served rules. Refuses what the engine would refuse.

        A rule whose ``when`` cannot be parsed raises :class:`UnreadableRule`.
        The served set is then evaluated once over an empty answer state at the
        session's ``reference_time``: nothing can fire on no answers, and the
        engine raises :class:`~protocols.triage.DraftRuleError` for a draft, so
        a session pinned to one is refused here, before anything is asked.
        """
        rules = served_rules(protocol)
        spellings: set[str] = set()
        for rule in rules:
            reads = rule_reads(rule)
            if reads is None or not reads.parsed:
                raise UnreadableRule(
                    f"{rule.id}: its when cannot be parsed, so the slots it reads cannot "
                    "be listed and no answer could be shown to trigger it"
                )
            spellings |= reads.all
        step_ids = {
            f"{section.id}.{resolved.key}"
            for section in protocol.sections
            for resolved in section.slots
        }
        triage = cls(
            rules=rules,
            location=location,
            spellings=step_spellings(spellings, step_ids),
            anchors=anchors,
        )
        evaluate_triage(rules, TriageContext(reference_time=reference_time, answers={}), location)
        return triage

    @property
    def reads(self) -> frozenset[str]:
        """The step ids any served rule reads, the tense anchors included."""
        return frozenset(self.spellings.values())

    def bound(self, engine: IntakeEngine) -> BoundReads:
        """The read slots' bound answers, for the queue's before/after compare."""
        answered = self._answered(engine)
        return tuple(
            (step_id, *answered[step_id]) for step_id in sorted(self.reads) if step_id in answered
        )

    def context(self, engine: IntakeEngine) -> TriageContext:
        """The engine's bound answers, keyed by each spelling the rules use."""
        answered = self._answered(engine)
        answers: dict[str, SlotAnswer] = {}
        for spelling, step_id in self.spellings.items():
            if step_id in answered:
                state, value = answered[step_id]
                answers[spelling] = SlotAnswer(state=state, values=(value,))
        return TriageContext(reference_time=engine.reference_time, answers=answers)

    def evaluate(self, engine: IntakeEngine, *, work_id: str) -> RulesTriageResult:
        """The rules engine's determination over the session's answers now."""
        result = evaluate_triage(self.rules, self.context(engine), self.location).result
        if self.anchors is not None:
            for resolution in self._anchor_readings(self.anchors, engine).values():
                self.anchors.note(resolution)
        self.evaluated.append(work_id)
        return result

    def _anchor_readings(
        self, anchors: SessionAnchors, engine: IntakeEngine
    ) -> dict[str, AnchorResolution]:
        """Each anchor CD-05 reads although nothing is bound to it (pure)."""
        readings = anchors.unclear_readings(engine, self.reads)
        readings.update(anchors.never_asked_readings(engine, self.reads))
        return readings

    def _answered(self, engine: IntakeEngine) -> dict[str, tuple[AnswerState, JsonValue]]:
        """The engine's bound answers, plus each anchor read as CD-05 decides.

        An UNCLEAR anchor carries the day CD-05 ``unresolved_answer`` resolves
        it to, and an anchor the close found never asked with chest pain
        affirmed carries CD-05's ``never_asked_at_close`` day (INT-546), each as
        a value-bearing answer: the record of the slot is unchanged
        (``engine.state_of`` is UNCLEAR or NOT_ASKED; nothing is bound), and
        ``SessionAnchors.record`` labels the day.
        """
        answered = engine.answered()
        if self.anchors is not None:
            for step_id, resolution in self._anchor_readings(self.anchors, engine).items():
                answered[step_id] = (AnswerState.ASKED_PRESENT, resolution.resolved_on)
        return answered
