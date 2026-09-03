"""INT-059 golden-suite infrastructure: rule loading, case shape, checker.

The golden suite exercises the INT-080 triage engine over the rule content
that exists in the repository TODAY — nothing here invents a clinical rule
(CLAUDE.md "never invent a value"; the corpus arithmetic is recorded in
docs/evidence/INT-059.md):

- the INT-040 synthetic chain packs ``tests/protocols/goldens/valid/``
  (``base.synthetic`` → ``specialty.synthetic_dal`` with its ``tighten_rule``
  op, plus ``overlay.synthetic_ek``) — SENTETİK TEST VERİSİ, mechanism only;
- the four exemplar rules of ``files/protocols/base.life_threat.yaml``
  (L0, ``served: false``, D17 in files/00_STATE.md §3): the two sourced
  chest-pain exemplars evaluate; the two ``draft_needs_source`` exemplars
  must be REFUSED by the engine (invariant 17 defence in depth).

Life-threat translation, stated openly: that file spells the predicate
``gate:`` and the provenance block ``evidence:`` (ADR-024 keeps that on-disk
spelling and makes ``when:``/``source:`` canonical in code).
:func:`translate_life_threat_rule` maps those two key names and projects onto
the DSL field set. It rewrites NOTHING else: since INT-254 the DSL types
``tense_anchor`` as a slot REFERENCE, so the document's dotted anchors are
carried verbatim like the predicate, and rule ``status`` is read with no
default because the document now states it on every rule. No level,
threshold, register, tense, predicate or Turkish string is altered — a
mutation test in tests/safety/test_triage_goldens.py proves edits flow
through.

The checker (:func:`run_case`) is deliberately shared between the golden
test and the mutation harness: a mutation "fails the suite" exactly when
:func:`run_case` reports a mismatch (or the rule set refuses to build) for
at least one golden.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    RedLocation,
    RedRegister,
    TriageLevel,
)
from protocols import RedFlagRule, load_pack, resolve_red_flags
from protocols.loader import PackRegistry
from protocols.locale_text import DEFAULT_LOCALE
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage, with_candidates
from protocols.types import EK4Level, RedFlagRoute, RuleStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = REPO_ROOT / "tests" / "protocols" / "goldens" / "valid"
LIFE_THREAT_PATH = REPO_ROOT / "files" / "protocols" / "base.life_threat.yaml"

# The session clock every golden folds over (files/13 §9.2: a pure input,
# never a wall clock) — same day as the synthetic-pack retrieval dates.
REF_TIME = datetime(2026, 8, 28, 10, 0, 0, tzinfo=UTC)


def d(days_ago: int) -> str:
    """ISO date ``days_ago`` calendar days before the reference day."""
    return (REF_TIME.date() - timedelta(days=days_ago)).isoformat()


TODAY = d(0)

# Rule ids as they exist in the repo (tests/protocols/goldens/valid/*.yaml
# and files/protocols/base.life_threat.yaml).
BK = "rf.synthetic_kirmizi"
BS = "rf.synthetic_sari"
CD = "rf.synthetic_dal_sari"
CG = "rf.synthetic_kirmizi.genis"
OE = "rf.synthetic_ek_sari"
C1 = "rf.chest_pain_cardiac_features"
C2 = "rf.chest_pain_no_cardiac_history"
D3 = "rf.paediatric_airway_obstruction"
D4 = "rf.crisis_disclosure_signposting"

# Slot names exactly as the rules spell them — the life-threat anchors are
# section-qualified references in the `gate:` namespace (INT-254).
ANCHOR = "olay_zamani"
CP_ANCHOR = "chest_pain.onset_at"
AW_ANCHOR = "airway.onset_at"

ASK_ONE_TR = "Şu anda hastanede misiniz?"


# ---------------------------------------------------------------------------
# Slot-answer shorthands.
# ---------------------------------------------------------------------------


def p(value: object) -> SlotAnswer:
    """asked_present carrying one value."""
    return SlotAnswer(state=AnswerState.ASKED_PRESENT, values=(value,))


def ab(value: object) -> SlotAnswer:
    """asked_absent — the elicited negative, which DOES carry its value."""
    return SlotAnswer(state=AnswerState.ASKED_ABSENT, values=(value,))


def st(state: AnswerState) -> SlotAnswer:
    """A valueless state (not_asked / asked_pending / unclear / declined) —
    reads Unknown, never False (files/12 §1.1)."""
    return SlotAnswer(state=state)


def con(*values: object) -> SlotAnswer:
    """contested — keeps every value; triage takes the escalating world
    (files/12 §7.3)."""
    return SlotAnswer(state=AnswerState.CONTESTED, values=tuple(values))


VALUELESS_STATES: tuple[AnswerState, ...] = (
    AnswerState.NOT_ASKED,
    AnswerState.ASKED_PENDING,
    AnswerState.UNCLEAR,
    AnswerState.DECLINED,
)


# ---------------------------------------------------------------------------
# Rule-set construction — from the repo's own files, rebuildable from
# mutated copies by the mutation harness.
# ---------------------------------------------------------------------------


class CorpusBuildError(ValueError):
    """The rule sets refuse to build — for the mutation harness this IS a
    suite failure (schema/validator refusal is the earlier line of defence)."""


# Projection of the life-threat authoring schema onto the DSL field set.
# Everything outside these keys is the life-threat WRAPPER (age_band,
# excluded_criteria, the golden blocks — carried by LifeThreatRule, not by
# RedFlagRule) — dropped, never rewritten. The mapped names: gate→when,
# evidence→source (the file's own schema_reconciliation item).
#
# Since INT-255 the delivery annotations below ARE modelled, so they are
# projected: a rule evaluated here without its register audio, its suppressed
# interrupt or its crisis path is not the rule the document contains, and the
# safety suite would be asserting about a different object than the one the
# compiler loads. `test_the_translator_carries_every_annotation_the_loader_
# does` in test_triage_goldens.py pins the two readings equal.
_RULE_KEYS = (
    "id",
    "label_tr",
    "tense",
    "tense_anchor",
    "level",
    "route",
    "register",
    "distress_sensitive",
    "subject_is_child",
    "audio",
    "suppress_attention_interrupt",
    "consent_independent",
    "offline_draft_path",
    "abandonment_handler",
    "notify_clinic",
    "source_gap",
)
_SOURCE_KEYS = (
    "guideline_id",
    "guideline_title",
    "version_or_date",
    "url",
    "retrieved_on",
    "quote",
    "quote_snapshot",
    "note",
)
_LOCATION_KEYS = (
    "primary",
    "secondary",
    "show_112",
    "numbers",
    "carry_child",
    "action_tr",
    "action_tr_ref",
    "do_nots_tr",
    "why_tr",
    "why_tr_ref",
    "notify_staff_immediate",
    "open_question",
    "note",
)
_UNKNOWN_KEYS = ("ask_one_tr", "on_yes", "on_no", "on_no_answer")


def _project(raw: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: raw[key] for key in keys if key in raw}


def translate_life_threat_rule(raw: Mapping[str, Any]) -> RedFlagRule:
    """One life-threat rule → :class:`RedFlagRule`, content verbatim.

    ``gate`` becomes ``when`` unchanged and ``evidence`` becomes ``source``;
    every other field, ``tense_anchor`` and ``status`` included, is read
    straight off the document. ``status`` deliberately has NO default here:
    the DSL requires it with none, and a translator that supplied one would
    hide exactly the omission INT-254 fixed.
    """
    payload: dict[str, Any] = _project(raw, _RULE_KEYS)
    payload["when"] = raw["gate"]
    payload["status"] = raw["status"]
    evidence = raw.get("evidence")
    if evidence is not None:
        payload["source"] = _project(evidence, _SOURCE_KEYS)
    action = raw.get("action")
    if action is not None:
        # Only the keys the document actually carries are forwarded, so a
        # missing location branch reaches RedFlagAction and is refused THERE
        # (invariant 21) rather than raising out of this translator.
        keyed = {"REMOTE": _LOCATION_KEYS, "ON_SITE": _LOCATION_KEYS, "UNKNOWN": _UNKNOWN_KEYS}
        payload["action"] = {
            location: _project(action[location], keys)
            for location, keys in keyed.items()
            if location in action
        }
    return RedFlagRule.model_validate(payload)


def load_life_threat_document(path: Path = LIFE_THREAT_PATH) -> dict[str, Any]:
    """The life-threat YAML document, with its sibling-set facts asserted."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise CorpusBuildError(f"{path}: not a YAML mapping")
    if document.get("kind") != "life_threat_set":
        raise CorpusBuildError("base.life_threat must stay kind: life_threat_set (files/12 §1)")
    if "extends" in document:
        raise CorpusBuildError("the life-threat set never joins the extends chain (invariant 7)")
    return document


@dataclass(frozen=True)
class RuleSets:
    """Every rule set a golden can evaluate against, plus an id index for
    verbatim action-identity checks."""

    sets: Mapping[str, tuple[RedFlagRule, ...]]
    by_id: Mapping[str, RedFlagRule]

    def rule(self, rule_id: str) -> RedFlagRule:
        return self.by_id[rule_id]


def _resolve(pack_id: str, registry: PackRegistry) -> dict[str, RedFlagRule]:
    resolved, findings = resolve_red_flags(registry.get(pack_id), registry)
    if findings:
        raise CorpusBuildError(f"{pack_id}: {[f.message for f in findings]}")
    return resolved


def build_rule_sets(
    pack_dir: Path = PACK_DIR,
    life_document: Mapping[str, Any] | None = None,
) -> RuleSets:
    """Load base/child/overlay through the real loader + resolver, translate
    the life-threat exemplars, and compose the evaluation sets.

    The mutation harness calls this with a mutated ``pack_dir`` copy or a
    mutated ``life_document`` — any schema or monotonicity refusal surfaces
    as :class:`CorpusBuildError` (or the loader/DSL error types), which the
    harness counts as the suite failing.
    """
    registry = PackRegistry()
    for name in ("base", "child", "overlay"):
        registry.add(load_pack(pack_dir / f"{name}.yaml"))
    base_rules = tuple(_resolve("base.synthetic", registry).values())
    child_rules = tuple(_resolve("specialty.synthetic_dal", registry).values())
    overlay_rules = tuple(_resolve("overlay.synthetic_ek", registry).values())

    if life_document is None:
        life_document = load_life_threat_document()
    life_all = tuple(translate_life_threat_rule(raw) for raw in life_document["rules"])
    life_active = tuple(rule for rule in life_all if rule.status is RuleStatus.ACTIVE)
    life_drafts = tuple(rule for rule in life_all if rule.status is not RuleStatus.ACTIVE)

    sets: dict[str, tuple[RedFlagRule, ...]] = {
        "base": base_rules,
        "child": child_rules,
        "overlay": overlay_rules,
        "child_overlay": child_rules + overlay_rules,
        "life": life_active,
        "child_overlay_life": child_rules + overlay_rules + life_active,
        "life_with_drafts": life_active + life_drafts,
    }
    by_id: dict[str, RedFlagRule] = {}
    for members in sets.values():
        for rule in members:
            by_id.setdefault(rule.id, rule)
    return RuleSets(sets=sets, by_id=by_id)


# ---------------------------------------------------------------------------
# The golden case and its checker.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldenCase:
    """One golden: typed answer state in → expected triage determination out.

    For RED the expectation carries all three axes of invariant 21
    explicitly: ``register`` and ``location`` are asserted on the result,
    and ``route`` is asserted on the winning rule — the route lives on the
    rule rather than on ``RulesTriageResult``, so pinning it here is what
    stops a RED silently changing from EMERGENCY_NOW to SAME_DAY_ACIL.
    ``winner`` also names the rule whose OWN frozen action object must come
    back verbatim for that location (invariants 10 and 21).
    """

    id: str
    rule_set: str
    answers: Mapping[str, SlotAnswer]
    note: str
    location: RedLocation = RedLocation.REMOTE
    level: TriageLevel = TriageLevel.GREEN
    ek4: EK4Level = EK4Level.YESIL
    fired: tuple[str, ...] = ()
    register: RedRegister | None = None
    route: RedFlagRoute | None = None
    winner: str | None = None
    action_primary: str | None = None
    action_show_112: bool | None = None
    action_tr: str | None = None
    ask_one_tr: str | None = None
    evidence_contains: tuple[tuple[str, str], ...] = ()
    candidates: int = 0
    expect_error: type[Exception] | None = None

    def context(self) -> TriageContext:
        return TriageContext(reference_time=REF_TIME, answers=dict(self.answers))


def _action_for(rule: RedFlagRule, location: RedLocation) -> object:
    action = rule.action
    if action is None:  # a RED winner always carries one; guarded for mypy
        raise CorpusBuildError(f"{rule.id} carries no action block")
    if location is RedLocation.REMOTE:
        return action.remote
    if location is RedLocation.ON_SITE:
        return action.on_site
    return action.unknown


def run_case(case: GoldenCase, rule_sets: RuleSets) -> list[str]:
    """Evaluate one golden; every returned string is a mismatch."""
    rules = rule_sets.sets[case.rule_set]
    try:
        evaluation = evaluate_triage(rules, case.context(), case.location)
    except Exception as exc:  # noqa: BLE001 — refusal is part of the contract
        if case.expect_error is not None and isinstance(exc, case.expect_error):
            return []
        return [f"raised {type(exc).__name__}: {exc}"]
    mismatches: list[str] = []
    if case.expect_error is not None:
        return [f"expected {case.expect_error.__name__}, engine evaluated instead"]
    if evaluation.result.level is not case.level:
        mismatches.append(f"level {evaluation.result.level} != {case.level}")
    if evaluation.ek4 is not case.ek4:
        mismatches.append(f"ek4 {evaluation.ek4} != {case.ek4}")
    fired = tuple(fire.id for fire in evaluation.result.rules)
    if set(fired) != set(case.fired):
        mismatches.append(f"fired {sorted(fired)} != {sorted(case.fired)}")
    if evaluation.result.register is not case.register:
        mismatches.append(f"register {evaluation.result.register} != {case.register}")
    expected_location = case.location if case.level is TriageLevel.RED else None
    if evaluation.result.location is not expected_location:
        mismatches.append(f"location {evaluation.result.location} != {expected_location}")
    mismatches.extend(_check_action(case, evaluation.action, rule_sets))
    evidence = {fire.id: fire.evidence for fire in evaluation.result.rules}
    for rule_id, fragment in case.evidence_contains:
        if fragment not in evidence.get(rule_id, ""):
            mismatches.append(f"evidence[{rule_id}] lacks {fragment!r}")
    if case.candidates:
        mismatches.extend(_check_candidates(case, evaluation))
    return mismatches


def _check_action(case: GoldenCase, action: object, rule_sets: RuleSets) -> list[str]:
    mismatches: list[str] = []
    if case.level is not TriageLevel.RED:
        if action is not None:
            mismatches.append("non-RED evaluation carries an action")
        return mismatches
    if case.winner is None:
        return ["a RED golden must name its winning rule"]
    winner = rule_sets.by_id.get(case.winner)
    if winner is None:
        # A mutation that deletes the winning rule must be REPORTED, not
        # raise past the checker — the harness would otherwise see a crash
        # where it should see a suite failure.
        return [f"winning rule {case.winner} is absent from the rule set"]
    if case.route is not None and winner.route is not case.route:
        # Axis 1 of invariant 21. It rides on the rule, not on the result,
        # so nothing else in the pipeline would notice it changing.
        mismatches.append(f"route {winner.route} != {case.route}")
    expected = _action_for(winner, case.location)
    if action is not expected:
        mismatches.append(f"action is not {case.winner}'s own {case.location} object")
    for attr, want in (
        ("primary", case.action_primary),
        ("show_112", case.action_show_112),
    ):
        if want is not None and getattr(action, attr, None) != want:
            mismatches.append(f"action.{attr} {getattr(action, attr, None)!r} != {want!r}")
    # INT-314: the two spoken fields are locale maps now. The golden keeps
    # naming the Turkish SENTENCE rather than the map, because the assertion a
    # reader has to be able to check is "REMOTE resolves the rule's own REMOTE
    # script" — and a golden that compared maps would still pass if the map
    # gained a locale saying something else.
    for attr, want in (("action_tr", case.action_tr), ("ask_one_tr", case.ask_one_tr)):
        if want is None:
            continue
        carried = getattr(action, attr, None)
        spoken = carried.get(DEFAULT_LOCALE) if isinstance(carried, Mapping) else carried
        if spoken != want:
            mismatches.append(f"action.{attr}[{DEFAULT_LOCALE}] {spoken!r} != {want!r}")
    return mismatches


def _check_candidates(case: GoldenCase, evaluation: Any) -> list[str]:
    """LLM candidates attach as flags and can never move the level, the
    fired set or the action (invariant 1; files/12 §2.3)."""

    flags = tuple(
        LlmCandidateTriage(
            candidate_flags=(
                CandidateFlag(text=f"sentetik aday {index}", evidence="sentetik kanıt"),
            )
        )
        for index in range(case.candidates)
    )
    annotated = with_candidates(evaluation, flags)
    mismatches: list[str] = []
    if annotated.result is not evaluation.result:
        mismatches.append("candidates replaced the rules result object")
    if annotated.action is not evaluation.action:
        mismatches.append("candidates replaced the action object")
    if len(annotated.candidate_flags) != case.candidates:
        mismatches.append("candidate flags were not all carried")
    return mismatches


def run_suite(rule_sets: RuleSets, cases: tuple[GoldenCase, ...]) -> dict[str, list[str]]:
    """Every golden's mismatches, keyed by case id — empty dict means green."""
    failures: dict[str, list[str]] = {}
    for case in cases:
        mismatches = run_case(case, rule_sets)
        if mismatches:
            failures[case.id] = mismatches
    return failures
