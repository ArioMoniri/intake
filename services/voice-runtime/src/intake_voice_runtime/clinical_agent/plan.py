"""The static step plan the IntakeEngine runs over (INT-081).

files/03 §5 describes the engine as "a state machine over protocol sections
… each section owning a slot schema compiled from the resolved protocol",
whose steps carry ``kind``, ``must_ask``, ``ask_if``, ``skip_if``. This
module is the projection from :class:`~protocols.compile.resolve.
ResolvedProtocol` to exactly that: one step per resolved slot, in authored
order, with its gates parsed once at build.

**Everything the blueprint calls a compile-time check is a refusal here, not
a warning.** files/13 §9.5 lists five CI-blocking compiler checks; two of
them are decidable from a resolved document alone and are enforced at build:

- a step must carry the verbatim Turkish it will be spoken from
  (``ask_tr``) — CLAUDE.md invariant 10 leaves no path to an improvised
  question, so a slot without one cannot become a step;
- a **required** slot must carry ``follow_up_tr`` (files/04 §1; files/13
  §11.1 "already mandatory on every required slot — so it is
  pre-synthesised, and a follow-up is a clip hit, not a TTS miss"). Without
  it the class-3 re-entry would have nothing verbatim to say.

**Gates are read with the closed ``when`` grammar** of files/03 §6 —
:func:`~protocols.triage.expr.parse_when`, the same parser and the same
Kleene evaluator the triage engine uses, so a gate and a red-flag rule can
never disagree about what ``Unknown`` means. GuardExpr's wider function
whitelist (``age_years``, ``any``, ``days_since`` …, files/13 §9.5) is not
implemented: a gate that reaches for it is **refused at build** rather than
guessed at, which fails closed — an unreadable gate stops the pack, it never
silently opens.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field

from clinical_schemas.common import FrozenModel
from protocols.compile.resolve import ResolvedProtocol
from protocols.locale_text import entry_for
from protocols.triage.expr import (
    Lookup,
    Truth,
    WhenGrammarError,
    WhenNode,
    evaluate_node,
    parse_when,
)
from protocols.types import Delivery
from pydantic import Field

from intake_voice_runtime.steps import StepKind

__all__ = ["EngineStep", "IntakePlan", "PlanError", "StepPriority", "build_plan"]


class PlanError(ValueError):
    """A resolved protocol the engine refuses to run."""


class StepPriority(enum.IntEnum):
    """The nine priority classes of files/13 §9.1, in the blueprint's own
    integers, sorted as ``(priority_class, order, id)`` — "a **total** order
    with no floats".

    The engine mints the classes it can derive from a resolved document
    today: :attr:`REENTRY` for a clarification follow-up (files/13 §11.1),
    :attr:`MUST_ASK` for a clinician-marked slot, :attr:`DETAIL` for
    everything else. The remaining classes are carried at their blueprint
    numbers so that the issues owning their content — the RED action script,
    the open narrative turn, the armed red-flag probe, the instrument block,
    wrap-up — slot in without renumbering an order that is already frozen
    and versioned (files/13 §4 "freeze and version the order").
    """

    SAFETY_SCRIPT = 0
    GATEKEEPER = 1
    OPEN_NARRATIVE = 2
    REENTRY = 3
    RF_PROBE_ARMED = 4
    MUST_ASK = 5
    INSTRUMENT_ITEM = 6
    DETAIL = 7
    WRAP_UP = 8


class EngineStep(FrozenModel):
    """One step: a resolved slot plus the bookkeeping the FSM sorts on."""

    step_id: str = Field(
        min_length=1,
        description="``<section>.<slot>`` — the same dotted reference a gate "
        "and a red-flag predicate spell (files/03 §6 atoms), so one lookup "
        "serves the frontier and the rules engine.",
    )
    section_id: str = Field(min_length=1, description="Owning section (files/03 §5).")
    order: int = Field(ge=0, description="Authored position; frozen and versioned (files/13 §4).")
    priority: StepPriority = Field(description="Priority class (files/13 §9.1).")
    must_ask: bool = Field(description="Clinician-marked must-ask (files/04 §1).")
    required: bool = Field(description="Required slot (files/03 §6).")
    delivery: Delivery = Field(description="Effective channel (files/13 §13).")
    full_kind: StepKind = Field(
        description="The kind this step takes when asked in full — as opposed to "
        "the ``confirm`` form delta mode offers it in (files/03 §4.2, §5)."
    )
    ask_tr: str = Field(min_length=1, description="Verbatim Turkish question (invariant 10).")
    confirm_tr: str | None = Field(
        default=None, description="Verbatim Turkish confirm text (files/04 §1)."
    )
    follow_up_tr: str | None = Field(
        default=None, description="Verbatim Turkish clarification (files/13 §11.1)."
    )
    choices_tr: tuple[str, ...] = Field(default=(), description="Spoken options (files/04 §1).")
    ask_if: str | None = Field(default=None, description="Gate expression (files/03 §5-6).")
    skip_if: str | None = Field(default=None, description="Retire expression (files/03 §5).")

    @property
    def sort_key(self) -> tuple[int, int, str]:
        """files/13 §9.1: ``(priority_class, order, id)``."""
        return (int(self.priority), self.order, self.step_id)


@dataclass(frozen=True, slots=True)
class IntakePlan:
    """The steps plus their parsed gates. Parsed once, at build."""

    steps: tuple[EngineStep, ...]
    ask_gates: Mapping[str, WhenNode] = field(default_factory=dict)
    skip_gates: Mapping[str, WhenNode] = field(default_factory=dict)

    @property
    def by_id(self) -> dict[str, EngineStep]:
        return {step.step_id: step for step in self.steps}

    def gate_truth(self, step_id: str, lookup: Lookup) -> Truth:
        """Kleene truth of the step's ``ask_if``; an ungated step is TRUE.

        files/13 §9.5: "a gate opens only on TRUE" — UNKNOWN does not open
        one, which is what keeps a not-yet-known slot from being read as a
        negative.
        """
        node = self.ask_gates.get(step_id)
        return Truth.TRUE if node is None else evaluate_node(node, lookup)

    def retired(self, step_id: str, lookup: Lookup) -> bool:
        """Whether the step's ``skip_if`` has retired it — TRUE only.

        files/13 §9.2 spells this field ``retire_if`` while files/03 §5-6 and
        the DSL spell it ``skip_if``; they are the same field and the DSL
        name is the one that exists.
        """
        node = self.skip_gates.get(step_id)
        return node is not None and evaluate_node(node, lookup) is Truth.TRUE


def _parse_gate(step_id: str, field_name: str, text: str) -> WhenNode:
    try:
        return parse_when(text)
    except WhenGrammarError as exc:
        raise PlanError(
            f"{step_id}: {field_name} {text!r} is not in the closed when grammar of "
            f"files/03 §6 ({exc}) — a gate the engine cannot read is refused rather "
            "than guessed at, so it can never silently open"
        ) from exc


def build_plan(protocol: ResolvedProtocol) -> IntakePlan:
    """Project a resolved protocol into the engine's step plan.

    Raises :class:`PlanError` on the first defect that would make a step
    unaskable or a gate unreadable.
    """
    steps: list[EngineStep] = []
    ask_gates: dict[str, WhenNode] = {}
    skip_gates: dict[str, WhenNode] = {}
    seen: set[str] = set()

    for section in protocol.sections:
        for resolved in section.slots:
            slot = resolved.slot
            step_id = f"{section.id}.{resolved.key}"
            if step_id in seen:
                raise PlanError(f"duplicate step id {step_id!r} in the resolved protocol")
            seen.add(step_id)
            if slot.ask_tr is None:
                raise PlanError(
                    f"{step_id}: a step is spoken verbatim from ask_tr and this slot "
                    "carries none — there is no path to an improvised question "
                    "(CLAUDE.md invariant 10; files/04 §1)"
                )
            if slot.required and slot.follow_up_tr is None:
                raise PlanError(
                    f"{step_id}: follow_up_tr is mandatory on every required slot "
                    "(files/04 §1; files/13 §11.1) — without it the class-3 "
                    "clarification re-entry has nothing verbatim to say"
                )
            if slot.ask_if is not None:
                ask_gates[step_id] = _parse_gate(step_id, "ask_if", slot.ask_if)
            if slot.skip_if is not None:
                skip_gates[step_id] = _parse_gate(step_id, "skip_if", slot.skip_if)
            # INT-297/INT-314: the DSL carries these per locale; the engine step carries
            # one language, the one the document was resolved for. Projected
            # through entry_for, which raises rather than falling back — a plan
            # built with a hole in it would surface as silence mid-turn.
            ask_tr = entry_for(slot.ask_tr, protocol.locale) if slot.ask_tr is not None else None
            confirm_tr = (
                entry_for(slot.confirm_tr, protocol.locale) if slot.confirm_tr is not None else None
            )
            follow_up_tr = (
                entry_for(slot.follow_up_tr, protocol.locale)
                if slot.follow_up_tr is not None
                else None
            )
            choices = (
                entry_for(slot.choices_tr, protocol.locale) if slot.choices_tr is not None else ()
            )
            if choices:
                kind = StepKind.CHOICE
            elif section.allow_paraphrase:
                kind = StepKind.PARAPHRASE_OK
            else:
                kind = StepKind.SCRIPTED
            steps.append(
                EngineStep(
                    step_id=step_id,
                    section_id=section.id,
                    order=len(steps),
                    priority=StepPriority.MUST_ASK if slot.must_ask else StepPriority.DETAIL,
                    must_ask=slot.must_ask,
                    required=slot.required,
                    delivery=resolved.delivery,
                    full_kind=kind,
                    ask_tr=ask_tr,
                    confirm_tr=confirm_tr,
                    follow_up_tr=follow_up_tr,
                    choices_tr=tuple(choices),
                    ask_if=slot.ask_if,
                    skip_if=slot.skip_if,
                )
            )
    return IntakePlan(steps=tuple(steps), ask_gates=ask_gates, skip_gates=skip_gates)
