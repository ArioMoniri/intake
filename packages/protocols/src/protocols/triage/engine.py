"""Deterministic triage evaluation: levels, monotonic merge, verbatim
action scripts (INT-080; CLAUDE.md invariant 1 — RED/YELLOW can only be
produced by these rules).

Pure and replayable: the result is a function of ``(rules, context,
location)`` alone — no wall clock, no I/O, no LLM anywhere in this package
(the import-boundary test in tests/safety/test_triage_engine.py asserts
that transitively).

- **Merge** (CLAUDE.md invariant 7 at runtime; files/12 §1): fired rules
  join under the EK-4 lattice ``max`` — adding a rule or reordering the
  input can never lower the level; the exhaustive small-domain property
  test proves it over every subset and permutation of its pool.
- **Action scripts verbatim** (invariants 10 and 21; files/04 §8.1 rule 7):
  a RED evaluation carries the winning rule's *own frozen action object*
  for the resolved location — REMOTE/ON_SITE return the rule's
  ``LocationAction`` untouched, UNKNOWN returns the rule's single
  ``ask_one_tr`` question object. There is no string handling here at all,
  so no paraphrase path exists.
- **LLM candidates** (invariant 1; files/03 §8): :func:`with_candidates`
  can only append ``candidate_flags`` — a separate field — and passes the
  rules result through untouched; the candidate type itself can express no
  level but ``YELLOW_REVIEW`` (INT-031, files/12 §2.3).
- **Draft rules never evaluate** (invariant 17; files/04 §8.1 rule 3):
  ``pack_compilable`` already excludes them from a served pack; this
  engine refuses them again, as defence in depth.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from clinical_schemas.common import FrozenModel
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from pydantic import Field, model_validator

from protocols.dsl import LocationAction, RedFlagRule, UnknownAction
from protocols.triage.context import (
    SlotValue,
    TriageContext,
    canonical_scalar,
    temporal_within,
)
from protocols.triage.expr import (
    Lookup,
    Truth,
    WhenNode,
    evaluate_node,
    parse_when,
    referenced_slots,
    truth_and,
    truth_or,
)
from protocols.types import EK4Level, RuleStatus

__all__ = [
    "DraftRuleError",
    "TriageEngineError",
    "TriageEvaluation",
    "evaluate_triage",
    "rule_truth",
    "when_truth",
    "with_candidates",
]


class TriageEngineError(ValueError):
    """The engine refuses an input it must never act on."""


class DraftRuleError(TriageEngineError):
    """A draft_needs_source rule reached evaluation (files/04 §8.1 rule 3)."""


class TriageEvaluation(FrozenModel):
    """One deterministic evaluation: the rules result, its EK-4 acuity, the
    verbatim RED action script, and LLM candidate flags in a field of their
    own that the level structurally cannot read."""

    result: RulesTriageResult = Field(
        description="The rules-engine determination — the only producer of "
        "RED/YELLOW (CLAUDE.md invariant 1; INT-031)."
    )
    ek4: EK4Level = Field(
        description="EK-4 acuity under the lattice max of every fired rule "
        "(files/12 §1, §2.1); YESIL when nothing fired."
    )
    action: LocationAction | UnknownAction | None = Field(
        default=None,
        description="RED only: the winning rule's own frozen action object for "
        "the resolved location — verbatim by construction (invariants 10, 21); "
        "UNKNOWN yields the rule's single ask_one_tr (files/04 §8.1 rule 7).",
    )
    candidate_flags: tuple[CandidateFlag, ...] = Field(
        default=(),
        description="LLM candidate flags — a separate field, never a level "
        "(files/03 §8; files/12 §2.3 YELLOW_REVIEW ceiling).",
    )

    @model_validator(mode="after")
    def _action_iff_red(self) -> TriageEvaluation:
        if (self.action is None) == (self.result.level is TriageLevel.RED):
            raise ValueError(
                "a RED evaluation carries the location-resolved action script "
                "and a non-RED one never does (CLAUDE.md invariant 21; "
                "files/02 §5.3)"
            )
        return self


# Delivery-restrictiveness order for the register axis, most restrictive
# first (files/02 §5.3: alarm — and speech itself — is the right register
# for most REDs and a *mechanism of harm* for some; where several REDs of
# equal acuity fire, the register whose harm model forbids the louder
# delivery wins. DEFERRED_CLINICIAN ranks last: it exists for findings with
# no useful patient action, and it must not swallow one that has one).
_REGISTER_PRECEDENCE: Mapping[RedRegister, int] = {
    RedRegister.SILENT: 0,
    RedRegister.CALM: 1,
    RedRegister.ALERT: 2,
    RedRegister.DEFERRED_CLINICIAN: 3,
}


def when_truth(when: str, context: TriageContext) -> Truth:
    """Kleene truth of a bare ``when`` predicate over the context."""
    node = parse_when(when)
    return _truth_over_worlds(node, referenced_slots(node), context, None, None)


def rule_truth(rule: RedFlagRule, context: TriageContext) -> Truth:
    """Truth of a rule: its ``when`` conjoined with the files/12 §2.4
    temporal guard over its tense anchor — Unknown on an undated symptom."""
    node = parse_when(rule.when)
    refs = referenced_slots(node) | {rule.tense_anchor}
    return _truth_over_worlds(node, refs, context, rule, rule.tense_anchor)


def _truth_over_worlds(
    node: WhenNode,
    refs: frozenset[str],
    context: TriageContext,
    rule: RedFlagRule | None,
    anchor: str | None,
) -> Truth:
    """Evaluate per contested-value world and join with Kleene OR — the
    files/12 §7.3 union: any world that fires, fires; escalation only."""
    contested = [
        ref
        for ref in sorted(refs)
        if (slot := context.answers.get(ref)) is not None and len(slot.values) > 1
    ]
    value_choices = [context.answers[ref].values for ref in contested]
    truths: list[Truth] = []
    for combo in itertools.product(*value_choices):
        world = dict(zip(contested, combo, strict=True))
        truth = evaluate_node(node, _world_lookup(context, world))
        if rule is not None and anchor is not None:
            truths.append(truth_and((truth, _anchor_truth(context, world, rule, anchor))))
        else:
            truths.append(truth)
    return truth_or(truths)


def _world_lookup(context: TriageContext, world: Mapping[str, SlotValue]) -> Lookup:
    def lookup(ref: str) -> bool | Decimal | str | None:
        if ref in world:
            return canonical_scalar(world[ref])
        values = context.candidate_values(ref)
        if values is None:
            return None
        return canonical_scalar(values[0])

    return lookup


def _anchor_truth(
    context: TriageContext,
    world: Mapping[str, SlotValue],
    rule: RedFlagRule,
    anchor: str,
) -> Truth:
    if anchor in world:
        anchor_value: SlotValue = world[anchor]
    else:
        values = context.candidate_values(anchor)
        if values is None:
            return Truth.UNKNOWN  # the anchor was never asked (files/12 §2.4)
        anchor_value = values[0]
    return temporal_within(anchor_value, rule.tense, context.reference_time)


def evaluate_triage(
    rules: Sequence[RedFlagRule],
    context: TriageContext,
    location: RedLocation,
) -> TriageEvaluation:
    """Evaluate the ACTIVE red-flag rules over the typed answer state.

    ``location`` is the RED location axis, derived by the caller from the
    visit lifecycle state (files/02 §5.3 Axis 3 — never guessed here).
    """
    drafts = sorted(rule.id for rule in rules if rule.status is RuleStatus.DRAFT_NEEDS_SOURCE)
    if drafts:
        raise DraftRuleError(
            f"draft_needs_source rules never evaluate: {', '.join(drafts)} "
            "(CLAUDE.md invariant 17; files/04 §8.1 rule 3 — pack_compilable "
            "already excludes them; this engine refuses them again)"
        )
    fired = [rule for rule in rules if rule_truth(rule, context) is Truth.TRUE]
    fired.sort(key=lambda rule: (-rule.level.severity, rule.id))
    if not fired:
        return TriageEvaluation(
            result=RulesTriageResult(level=TriageLevel.GREEN),
            ek4=EK4Level.YESIL,
        )
    ek4 = fired[0].level
    rule_fires = tuple(RuleFire(id=rule.id, evidence=_evidence(rule, context)) for rule in fired)
    level = _triage_level(ek4)
    if level is not TriageLevel.RED:
        return TriageEvaluation(result=RulesTriageResult(level=level, rules=rule_fires), ek4=ek4)
    winner = _winning_red(fired, ek4)
    return TriageEvaluation(
        result=RulesTriageResult(
            level=TriageLevel.RED,
            rules=rule_fires,
            register=_required_register(winner),
            location=location,
        ),
        ek4=ek4,
        action=_resolved_action(winner, location),
    )


def with_candidates(
    evaluation: TriageEvaluation, candidates: Iterable[LlmCandidateTriage]
) -> TriageEvaluation:
    """Attach LLM candidate flags. The rules result passes through as the
    same object; nothing here reads a candidate's level — the type can only
    say YELLOW_REVIEW (invariant 1; files/03 §8; files/12 §2.3)."""
    flags = list(evaluation.candidate_flags)
    for candidate in candidates:
        flags.extend(candidate.candidate_flags)
    return TriageEvaluation(
        result=evaluation.result,
        ek4=evaluation.ek4,
        action=evaluation.action,
        candidate_flags=tuple(flags),
    )


def _triage_level(ek4: EK4Level) -> TriageLevel:
    """EK-4 acuity → the three patient-routing colours (files/03 §8;
    files/12 §2.1: three colours, five levels)."""
    if ek4.is_red:
        return TriageLevel.RED
    if ek4 is EK4Level.YESIL:
        return TriageLevel.GREEN
    return TriageLevel.YELLOW


def _winning_red(fired: Sequence[RedFlagRule], ek4: EK4Level) -> RedFlagRule:
    """One rule supplies both register and script: severity first (the
    highest acuity dictates delivery), then register restrictiveness
    (files/02 §5.3 — see _REGISTER_PRECEDENCE), then rule id, so the choice
    is total and order-independent. Register and script travel together
    because the register was clinician-approved for that rule's script
    (files/02 §5.3 binding authoring rule), never mixed across rules."""
    candidates = [rule for rule in fired if rule.level is ek4]
    return min(candidates, key=lambda rule: (_register_rank(rule), rule.id))


def _register_rank(rule: RedFlagRule) -> int:
    return _REGISTER_PRECEDENCE[_required_register(rule)]


def _required_register(rule: RedFlagRule) -> RedRegister:
    if rule.register is None:
        raise TriageEngineError(
            f"KIRMIZI rule {rule.id} carries no register — no permitted "
            "default (CLAUDE.md invariant 21; files/02 §5.3)"
        )
    return rule.register


def _resolved_action(rule: RedFlagRule, location: RedLocation) -> LocationAction | UnknownAction:
    if rule.action is None:
        raise TriageEngineError(
            f"KIRMIZI rule {rule.id} carries no action block — a RED must "
            "resolve for all three locations (CLAUDE.md invariant 21; "
            "files/04 §8.1 rule 7)"
        )
    if location is RedLocation.REMOTE:
        return rule.action.remote
    if location is RedLocation.ON_SITE:
        return rule.action.on_site
    return rule.action.unknown


def _evidence(rule: RedFlagRule, context: TriageContext) -> str:
    """Deterministic 'which slot values satisfied the rule' text
    (files/04 §5 triage.rules.evidence): every referenced slot with a
    usable value, sorted, all carried values joined."""
    refs = sorted(referenced_slots(parse_when(rule.when)) | {rule.tense_anchor})
    parts: list[str] = []
    for ref in refs:
        values = context.candidate_values(ref)
        if values is not None:
            rendered = "|".join(_render_value(value) for value in values)
            parts.append(f"{ref}={rendered}")
    return "; ".join(parts)


def _render_value(value: SlotValue) -> str:
    """One carried value as evidence text, exactly as it was carried.

    ``json.dumps`` cannot serialise a ``Decimal`` at all, and routing one
    through ``float`` to make it serialisable would put a float on the path
    files/13 §9.5 keeps clear of them and drop the authored scale that
    :func:`~protocols.triage.context.canonical_scalar` deliberately carries
    (INT-267). A Decimal therefore renders from its own exact form, which
    is already a JSON number literal.
    """
    if isinstance(value, Decimal):
        return str(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
