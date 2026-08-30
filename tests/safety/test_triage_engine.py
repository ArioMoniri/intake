"""INT-080 — deterministic triage engine: levels, monotonic merge, action scripts.

Acceptance (docs/backlog/issues.yaml INT-080, verbatim): "rules only; LLM
candidates cap at YELLOW_REVIEW and can never lower a level (type-level);
action scripts verbatim".

Every rule, slot and Turkish string in this file is SYNTHETIC (SENTETİK TEST
VERİSİ) — zero clinical content, per the INT-080 scope and CLAUDE.md
invariant 17. Blueprint anchors: CLAUDE.md invariants 1/7/10/21; files/12 §1,
§1.1, §2.4, §4, §7.3; files/02 §5.3; files/03 §6, §8; files/04 §8.1.
"""

from __future__ import annotations

import ast as python_ast
import itertools
import textwrap
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    RedLocation,
    RedRegister,
    RulesTriageResult,
    TriageLevel,
)
from intake_voice_runtime.clinical_agent import IntakeEngine
from protocols import EK4Level, RedFlagRule, load_pack, resolve_red_flags
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.loader import PackRegistry
from protocols.triage import (
    DraftRuleError,
    SlotAnswer,
    TriageContext,
    TriageEngineError,
    TriageEvaluation,
    Truth,
    canonical_scalar,
    evaluate_triage,
    rule_truth,
    with_candidates,
)
from protocols.types import Delivery, SlotType
from pydantic import ValidationError
from synthetic_triage import ANCHOR, REF_TIME, ctx, make_rule, present

# ---------------------------------------------------------------------------
# Levels: GREEN / YELLOW / RED from rules only (CLAUDE.md invariant 1).
# ---------------------------------------------------------------------------


class TestLevels:
    def test_no_rules_is_green(self) -> None:
        evaluation = evaluate_triage((), ctx(), RedLocation.REMOTE)
        assert evaluation.result.level is TriageLevel.GREEN
        assert evaluation.result.source == "rules"
        assert evaluation.ek4 is EK4Level.YESIL
        assert evaluation.result.rules == ()
        assert evaluation.action is None

    def test_nothing_fires_is_green(self) -> None:
        rule = make_rule("rf.sentetik_sari", EK4Level.SARI_K2, "isaret == true")
        evaluation = evaluate_triage((rule,), ctx(isaret=present(False)), RedLocation.REMOTE)
        assert evaluation.result.level is TriageLevel.GREEN
        assert evaluation.result.rules == ()

    def test_unknown_never_fires(self) -> None:
        # files/12 §1.1: rules fire only on TRUE; not_asked reads Unknown.
        rule = make_rule("rf.sentetik_sari", EK4Level.SARI_K2, "isaret == true")
        evaluation = evaluate_triage((rule,), ctx(), RedLocation.REMOTE)
        assert evaluation.result.level is TriageLevel.GREEN

    def test_sari_fires_yellow_without_red_axes(self) -> None:
        rule = make_rule("rf.sentetik_sari", EK4Level.SARI_K1, "isaret == true")
        evaluation = evaluate_triage((rule,), ctx(isaret=present(True)), RedLocation.REMOTE)
        assert evaluation.result.level is TriageLevel.YELLOW
        assert evaluation.ek4 is EK4Level.SARI_K1
        assert [fire.id for fire in evaluation.result.rules] == ["rf.sentetik_sari"]
        # register/location are RED axes only (files/02 §5.3; INT-031 validator)
        assert evaluation.result.register is None
        assert evaluation.result.location is None
        assert evaluation.action is None

    def test_kirmizi_fires_red_with_register_and_location(self) -> None:
        rule = make_rule(
            "rf.sentetik_kirmizi",
            EK4Level.KIRMIZI_K2,
            "isaret == true",
            register=RedRegister.ALERT,
        )
        evaluation = evaluate_triage((rule,), ctx(isaret=present(True)), RedLocation.REMOTE)
        assert evaluation.result.level is TriageLevel.RED
        assert evaluation.ek4 is EK4Level.KIRMIZI_K2
        assert evaluation.result.register is RedRegister.ALERT
        assert evaluation.result.location is RedLocation.REMOTE
        assert evaluation.result.rules[0].id == "rf.sentetik_kirmizi"

    def test_yesil_rule_fires_green_with_rule_named(self) -> None:
        rule = make_rule("rf.sentetik_yesil", EK4Level.YESIL, "isaret == true")
        evaluation = evaluate_triage((rule,), ctx(isaret=present(True)), RedLocation.REMOTE)
        assert evaluation.result.level is TriageLevel.GREEN
        assert evaluation.ek4 is EK4Level.YESIL
        assert [fire.id for fire in evaluation.result.rules] == ["rf.sentetik_yesil"]

    def test_evidence_names_the_satisfying_slot_values(self) -> None:
        rule = make_rule("rf.sentetik_sari", EK4Level.SARI_K2, "isaret == true")
        evaluation = evaluate_triage((rule,), ctx(isaret=present(True)), RedLocation.REMOTE)
        evidence = evaluation.result.rules[0].evidence
        assert "isaret=true" in evidence
        assert ANCHOR in evidence  # tense anchor is part of what satisfied the rule

    def test_evidence_skips_slots_that_carry_no_value(self) -> None:
        rule = make_rule(
            "rf.sentetik_sari",
            EK4Level.SARI_K2,
            "isaret == true || bilinmeyen == true",
        )
        evaluation = evaluate_triage((rule,), ctx(isaret=present(True)), RedLocation.REMOTE)
        evidence = evaluation.result.rules[0].evidence
        assert "isaret=true" in evidence
        assert "bilinmeyen" not in evidence  # never asked → never rendered as evidence


# ---------------------------------------------------------------------------
# Monotonic merge (CLAUDE.md invariant 7 at runtime; files/12 §1 lattice max).
# Exhaustive small-domain property: hypothesis is not a workspace dev
# dependency, so the domain is enumerated completely instead.
# ---------------------------------------------------------------------------

_POOL_LEVELS = (
    EK4Level.SARI_K2,
    EK4Level.SARI_K1,
    EK4Level.KIRMIZI_K2,
    EK4Level.KIRMIZI_K1,
    EK4Level.SARI_K2,
)


def _pool() -> tuple[RedFlagRule, ...]:
    registers = (None, None, RedRegister.ALERT, RedRegister.CALM, None)
    return tuple(
        make_rule(f"rf.sentetik_{index}", level, f"s{index} == true", register=register)
        for index, (level, register) in enumerate(zip(_POOL_LEVELS, registers, strict=True))
    )


def _pool_ctx() -> TriageContext:
    return ctx(**{f"s{index}": present(True) for index in range(len(_POOL_LEVELS))})


class TestMonotonicMerge:
    def test_every_subset_merges_to_the_highest_level(self) -> None:
        pool = _pool()
        context = _pool_ctx()
        for size in range(len(pool) + 1):
            for subset in itertools.combinations(range(len(pool)), size):
                evaluation = evaluate_triage(
                    tuple(pool[i] for i in subset), context, RedLocation.REMOTE
                )
                expected = max(
                    (pool[i].level.severity for i in subset), default=EK4Level.YESIL.severity
                )
                assert evaluation.ek4.severity == expected
                assert {fire.id for fire in evaluation.result.rules} == {pool[i].id for i in subset}

    def test_adding_rules_can_only_escalate(self) -> None:
        pool = _pool()
        context = _pool_ctx()
        severity: dict[tuple[int, ...], int] = {}
        indices = range(len(pool))
        for size in range(len(pool) + 1):
            for subset in itertools.combinations(indices, size):
                evaluation = evaluate_triage(
                    tuple(pool[i] for i in subset), context, RedLocation.REMOTE
                )
                severity[subset] = evaluation.ek4.severity
        for smaller, larger in itertools.product(severity, severity):
            if set(smaller) <= set(larger):
                assert severity[larger] >= severity[smaller]

    def test_no_input_ordering_ever_lowers_a_level(self) -> None:
        pool = _pool()
        context = _pool_ctx()
        baseline = evaluate_triage(pool, context, RedLocation.REMOTE)
        for permutation in itertools.permutations(pool):
            evaluation = evaluate_triage(permutation, context, RedLocation.REMOTE)
            assert evaluation == baseline

    def test_all_fired_rules_are_listed_highest_first(self) -> None:
        pool = _pool()
        evaluation = evaluate_triage(pool, _pool_ctx(), RedLocation.REMOTE)
        severities = [
            EK4Level(level).severity
            for level in (
                _POOL_LEVELS[3],
                _POOL_LEVELS[2],
                _POOL_LEVELS[1],
                _POOL_LEVELS[0],
                _POOL_LEVELS[4],
            )
        ]
        listed = [fire.id for fire in evaluation.result.rules]
        assert listed == [
            "rf.sentetik_3",
            "rf.sentetik_2",
            "rf.sentetik_1",
            "rf.sentetik_0",
            "rf.sentetik_4",
        ]
        assert severities == sorted(severities, reverse=True)


# ---------------------------------------------------------------------------
# Register and script selection when several REDs fire (files/02 §5.3:
# alarm is the right register for most REDs and a mechanism of harm for
# some — the most delivery-restrictive register wins among equals; severity
# outranks register because the register was approved for that rule).
# ---------------------------------------------------------------------------


def _red(rule_id: str, register: RedRegister, level: EK4Level = EK4Level.KIRMIZI_K2) -> RedFlagRule:
    return make_rule(rule_id, level, f"{rule_id.rsplit('.', 1)[-1]} == true", register=register)


def _fire_all(*rules: RedFlagRule, location: RedLocation = RedLocation.REMOTE) -> TriageEvaluation:
    slots = {rule.id.rsplit(".", 1)[-1]: present(True) for rule in rules}
    return evaluate_triage(rules, ctx(**slots), location)


class TestRegisterSelection:
    @pytest.mark.parametrize(
        ("first", "second", "winner"),
        [
            (RedRegister.ALERT, RedRegister.CALM, RedRegister.CALM),
            (RedRegister.ALERT, RedRegister.SILENT, RedRegister.SILENT),
            (RedRegister.CALM, RedRegister.SILENT, RedRegister.SILENT),
            (RedRegister.ALERT, RedRegister.DEFERRED_CLINICIAN, RedRegister.ALERT),
            (RedRegister.CALM, RedRegister.DEFERRED_CLINICIAN, RedRegister.CALM),
        ],
    )
    def test_most_restrictive_register_wins_at_equal_severity(
        self, first: RedRegister, second: RedRegister, winner: RedRegister
    ) -> None:
        a = _red("rf.sentetik_a", first)
        b = _red("rf.sentetik_b", second)
        for ordering in ((a, b), (b, a)):
            evaluation = _fire_all(*ordering)
            assert evaluation.result.register is winner

    def test_higher_severity_outranks_register(self) -> None:
        silent_k2 = _red("rf.sentetik_a", RedRegister.SILENT, EK4Level.KIRMIZI_K2)
        alert_k1 = _red("rf.sentetik_b", RedRegister.ALERT, EK4Level.KIRMIZI_K1)
        evaluation = _fire_all(silent_k2, alert_k1)
        assert evaluation.result.register is RedRegister.ALERT
        assert evaluation.ek4 is EK4Level.KIRMIZI_K1

    def test_script_comes_from_the_winning_rule(self) -> None:
        calm = _red("rf.sentetik_a", RedRegister.CALM)
        alert = _red("rf.sentetik_b", RedRegister.ALERT)
        evaluation = _fire_all(calm, alert)
        assert evaluation.action is calm.action.remote  # type: ignore[union-attr]

    def test_equal_rules_tie_break_on_id_deterministically(self) -> None:
        a = _red("rf.sentetik_a", RedRegister.ALERT)
        b = _red("rf.sentetik_b", RedRegister.ALERT)
        for ordering in ((a, b), (b, a)):
            evaluation = _fire_all(*ordering)
            assert evaluation.action is a.action.remote  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Action scripts verbatim (CLAUDE.md invariants 10 and 21; files/04 §8.1
# rule 7). The engine returns the rule's own frozen objects — byte-exact by
# construction, no paraphrase path exists.
# ---------------------------------------------------------------------------


class TestActionScripts:
    def test_remote_action_is_the_rules_own_object(self) -> None:
        rule = _red("rf.sentetik_a", RedRegister.ALERT)
        evaluation = _fire_all(rule, location=RedLocation.REMOTE)
        assert evaluation.action is rule.action.remote  # type: ignore[union-attr]
        assert evaluation.result.location is RedLocation.REMOTE

    def test_on_site_action_never_contains_112(self) -> None:
        rule = _red("rf.sentetik_a", RedRegister.ALERT)
        evaluation = _fire_all(rule, location=RedLocation.ON_SITE)
        action = evaluation.action
        assert action is rule.action.on_site  # type: ignore[union-attr]
        assert action is not None
        dumped = action.model_dump()
        assert dumped["show_112"] is False
        for text in (
            dumped["action_tr"],
            dumped["why_tr"],
            *dumped["do_nots_tr"],
        ):
            assert text is None or "112" not in text

    def test_unknown_location_yields_the_single_ask_one(self) -> None:
        rule = _red("rf.sentetik_a", RedRegister.ALERT)
        evaluation = _fire_all(rule, location=RedLocation.UNKNOWN)
        assert evaluation.action is rule.action.unknown  # type: ignore[union-attr]
        assert evaluation.result.location is RedLocation.UNKNOWN

    def test_non_red_evaluation_never_carries_an_action(self) -> None:
        with pytest.raises(ValidationError):
            TriageEvaluation(
                result=RulesTriageResult(level=TriageLevel.GREEN),
                ek4=EK4Level.YESIL,
                action=_ACTION_OBJECT(),
            )

    def test_red_evaluation_must_carry_an_action(self) -> None:
        result = RulesTriageResult(
            level=TriageLevel.RED,
            rules=({"id": "rf.sentetik_a", "evidence": "isaret=true"},),
            register=RedRegister.ALERT,
            location=RedLocation.REMOTE,
        )
        with pytest.raises(ValidationError):
            TriageEvaluation(result=result, ek4=EK4Level.KIRMIZI_K2, action=None)


def _ACTION_OBJECT() -> object:
    return _red("rf.sentetik_a", RedRegister.ALERT).action.remote  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# LLM candidates: type-level YELLOW_REVIEW ceiling, never touching the level
# (CLAUDE.md invariant 1; files/03 §8; files/12 §2.3).
# ---------------------------------------------------------------------------


def _candidate() -> LlmCandidateTriage:
    return LlmCandidateTriage(
        candidate_flags=(CandidateFlag(text="sentetik aday bulgu", evidence="sentetik kanıt"),)
    )


class TestLlmCandidates:
    def test_candidates_attach_without_touching_a_green_level(self) -> None:
        evaluation = evaluate_triage((), ctx(), RedLocation.REMOTE)
        annotated = with_candidates(evaluation, [_candidate()])
        assert annotated.result is evaluation.result
        assert annotated.result.level is TriageLevel.GREEN
        assert [flag.text for flag in annotated.candidate_flags] == ["sentetik aday bulgu"]
        assert annotated.result.rules == ()

    def test_candidates_never_lower_a_red(self) -> None:
        rule = _red("rf.sentetik_a", RedRegister.ALERT)
        evaluation = _fire_all(rule)
        annotated = with_candidates(evaluation, [_candidate(), _candidate()])
        assert annotated.result is evaluation.result
        assert annotated.result.level is TriageLevel.RED
        assert len(annotated.candidate_flags) == 2
        assert annotated.action is evaluation.action

    def test_a_red_labelled_candidate_is_untypeable(self) -> None:
        # Type-level cap: the only level the candidate type can express is
        # YELLOW_REVIEW (INT-031; files/03 §4.6) — RED does not validate.
        with pytest.raises(ValidationError):
            LlmCandidateTriage.model_validate(
                {
                    "level": "RED",
                    "candidate_flags": ({"text": "sentetik", "evidence": "sentetik"},),
                }
            )
        assert get_args(LlmCandidateTriage.model_fields["level"].annotation) == ("YELLOW_REVIEW",)

    def test_the_result_field_is_typed_rules_only(self) -> None:
        # The level field derives exclusively from rules: the result slot of
        # TriageEvaluation is RulesTriageResult, not the discriminated union.
        assert TriageEvaluation.model_fields["result"].annotation is RulesTriageResult

    def test_the_result_is_frozen_against_mutation(self) -> None:
        evaluation = evaluate_triage((), ctx(), RedLocation.REMOTE)
        with pytest.raises(ValidationError):
            evaluation.result.level = TriageLevel.RED  # type: ignore[misc]


# ---------------------------------------------------------------------------
# draft_needs_source never evaluates (CLAUDE.md invariant 17; files/04 §8.1
# rule 3) — defence in depth behind pack_compilable's exclusion.
# ---------------------------------------------------------------------------

_DRAFT_PACK = """\
kind: pack
id: base.sentetik
layer: base
version: 1.0.0
schema_version: 2
maturity: L0
status: awaiting-clinical-review
language: tr
title_tr: "Sentetik taslak paketi"
red_flags:
  - id: rf.sentetik_taslak
    label_tr: "Sentetik taslak kural"
    when: "isaret == true"
    tense: ever
    tense_anchor: olay_zamani
    level: SARI_K2
    route: SAME_DAY_ACIL
    notify_clinic: always
    status: draft_needs_source
    source_gap: "sentetik: kaynak klinik onay bekliyor"
"""


class TestDraftRefusal:
    def test_a_draft_rule_is_refused_directly(self) -> None:
        draft = make_rule(
            "rf.sentetik_taslak",
            EK4Level.SARI_K2,
            "isaret == true",
            status="draft_needs_source",
        )
        with pytest.raises(DraftRuleError):
            evaluate_triage((draft,), ctx(isaret=present(True)), RedLocation.REMOTE)

    def test_a_pack_containing_a_draft_rule_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "base.sentetik.yaml"
        path.write_text(textwrap.dedent(_DRAFT_PACK), encoding="utf-8")
        pack = load_pack(path)
        registry = PackRegistry()
        registry.add(pack)
        resolved, findings = resolve_red_flags(pack, registry)
        assert findings == ()
        with pytest.raises(DraftRuleError):
            evaluate_triage(tuple(resolved.values()), ctx(isaret=present(True)), RedLocation.REMOTE)


# ---------------------------------------------------------------------------
# Schema-bypass mutations (the files/12 §2.3 model_construct pattern): a RED
# rule stripped of its register or action must raise, never default.
# ---------------------------------------------------------------------------


class TestSchemaBypassMutations:
    def _stripped(self, **overrides: object) -> RedFlagRule:
        rule = _red("rf.sentetik_a", RedRegister.ALERT)
        payload = dict(rule)
        payload.update(overrides)
        return RedFlagRule.model_construct(**payload)

    def test_red_without_register_raises_instead_of_defaulting(self) -> None:
        mutant = self._stripped(register=None)
        with pytest.raises(TriageEngineError):
            evaluate_triage((mutant,), ctx(sentetik_a=present(True)), RedLocation.REMOTE)

    def test_red_without_action_raises_instead_of_defaulting(self) -> None:
        mutant = self._stripped(action=None)
        with pytest.raises(TriageEngineError):
            evaluate_triage((mutant,), ctx(sentetik_a=present(True)), RedLocation.REMOTE)


# ---------------------------------------------------------------------------
# No LLM anywhere under packages/protocols (CLAUDE.md invariant 1; INT-080
# scope item 1): the import graph carries no LLM/vendor/network client.
# ---------------------------------------------------------------------------

_FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "anthropic",
    "boto3",
    "botocore",
    "cohere",
    "google",
    "groq",
    "grpc",
    "httpx",
    "langchain",
    "litellm",
    "mistralai",
    "ollama",
    "openai",
    "requests",
    "together",
    "transformers",
    "urllib3",
    "vertexai",
    "vllm",
    "websockets",
}


def _import_roots(tree: python_ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in python_ast.walk(tree):
        if isinstance(node, python_ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, python_ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


class TestImportBoundary:
    def test_nothing_under_protocols_imports_an_llm_or_vendor_client(self) -> None:
        src = Path(__file__).resolve().parents[2] / "packages" / "protocols" / "src"
        assert src.is_dir()
        offenders: dict[str, set[str]] = {}
        for path in sorted(src.rglob("*.py")):
            roots = _import_roots(python_ast.parse(path.read_text(encoding="utf-8")))
            hits = roots & _FORBIDDEN_IMPORT_ROOTS
            if hits:
                offenders[str(path)] = hits
        assert offenders == {}


# ---------------------------------------------------------------------------
# INT-267 — the decimal carrier, from the extraction boundary to the verdict.
#
# INT-083's extraction emits decimal and quantity slot values as exact
# `Decimal` (a float would breach CLAUDE.md invariant 22; files/13 §9.5 "no
# floats anywhere ... exact comparison"). `canonical_scalar` declares
# `bool | Decimal | str | None` and used to refuse the very type it returns,
# so such a value read Unknown to every gate that referenced it.
#
# SENTETİK TEST VERİSİ: the slot names, the Turkish strings and the 38.5
# threshold below are invented for this test and carry NO clinical meaning.
# The `sentetik.` prefix is this repo's marker for exactly that (files/04
# §7); no clinical threshold is invented here or anywhere else.
# ---------------------------------------------------------------------------

SENTETIK_ANCHOR = "sentetik.olay_zamani"
SENTETIK_OLCUM = "sentetik.olcum"
SENTETIK_GATED = "sentetik.ek_soru"
SENTETIK_ESIK = "38.5"
SENTETIK_WHEN = f"{SENTETIK_OLCUM} >= {SENTETIK_ESIK}"
SENTETIK_GUN = "2026-08-28"  # the reference day of synthetic_triage.REF_TIME


def _esik_rule() -> RedFlagRule:
    return make_rule(
        "rf.sentetik_esik",
        EK4Level.KIRMIZI_K2,
        SENTETIK_WHEN,
        register=RedRegister.ALERT,
        anchor=SENTETIK_ANCHOR,
    )


def _esik_ctx(value: object) -> TriageContext:
    return TriageContext(
        reference_time=REF_TIME,
        answers={
            SENTETIK_ANCHOR: present(SENTETIK_GUN),
            SENTETIK_OLCUM: present(value),
        },
    )


class TestDecimalThresholdGolden:
    """The golden and its near-miss negative control (CLAUDE.md clinical
    content rules: any change under packages/protocols/** ships with one)."""

    def test_over_the_threshold_fires_red_with_its_own_verbatim_script(self) -> None:
        rule = _esik_rule()
        context = _esik_ctx(Decimal("38.5"))
        # the golden must stay a DECIMAL golden: a carrier that quietly
        # coerced the value to float would make it prove nothing
        assert isinstance(context.answers[SENTETIK_OLCUM].values[0], Decimal)
        assert rule_truth(rule, context) is Truth.TRUE
        evaluation = evaluate_triage((rule,), context, RedLocation.REMOTE)
        assert evaluation.result.level is TriageLevel.RED
        assert evaluation.ek4 is EK4Level.KIRMIZI_K2
        assert evaluation.result.register is RedRegister.ALERT
        assert evaluation.result.location is RedLocation.REMOTE
        assert [fire.id for fire in evaluation.result.rules] == ["rf.sentetik_esik"]
        assert rule.action is not None
        assert evaluation.action is rule.action.remote

    def test_the_near_miss_just_under_the_threshold_is_false_not_unknown(self) -> None:
        # The negative control, and the whole point of the issue: a gate
        # that cannot decide returns Unknown, and Unknown is not a safe
        # default merely because it is not FALSE. So the near miss is
        # asserted as FALSE on the rule truth itself, not only as a GREEN
        # verdict — GREEN is what Unknown produces too.
        rule = _esik_rule()
        context = _esik_ctx(Decimal("38.4"))
        assert isinstance(context.answers[SENTETIK_OLCUM].values[0], Decimal)
        assert rule_truth(rule, context) is Truth.FALSE
        evaluation = evaluate_triage((rule,), context, RedLocation.REMOTE)
        assert evaluation.result.level is TriageLevel.GREEN
        assert evaluation.result.rules == ()
        assert evaluation.action is None

    def test_the_evidence_renders_the_decimal_at_its_authored_scale(self) -> None:
        # The evidence string is the clinician-facing "which values
        # satisfied this rule"; a Decimal is rendered from its own exact
        # form, so 38.50 reads 38.50 and no float ever formats it.
        rule = _esik_rule()
        evaluation = evaluate_triage((rule,), _esik_ctx(Decimal("38.50")), RedLocation.REMOTE)
        evidence = evaluation.result.rules[0].evidence
        assert f"{SENTETIK_OLCUM}=38.50" in evidence
        assert f"{SENTETIK_ANCHOR}=" in evidence

    @pytest.mark.parametrize(
        ("carrier", "over", "under"),
        [
            ("decimal", Decimal("39"), Decimal("38")),
            ("int", 39, 38),
            ("float", 39.0, 38.0),
        ],
    )
    def test_every_carrier_reaches_the_same_verdict(
        self, carrier: str, over: object, under: object
    ) -> None:
        rule = _esik_rule()
        assert rule_truth(rule, _esik_ctx(over)) is Truth.TRUE
        assert rule_truth(rule, _esik_ctx(under)) is Truth.FALSE
        assert (
            evaluate_triage((rule,), _esik_ctx(over), RedLocation.REMOTE).result.level
            is TriageLevel.RED
        )
        assert (
            evaluate_triage((rule,), _esik_ctx(under), RedLocation.REMOTE).result.level
            is TriageLevel.GREEN
        )

    def test_no_float_reaches_the_comparison(self) -> None:
        # files/13 §9.5. Whatever the carrier, the compared scalar is a
        # Decimal — the float carrier converts through its string form and
        # the Decimal carrier is not converted at all.
        for value in (Decimal("39"), 39, 39.0):
            compared = canonical_scalar(value)
            assert isinstance(compared, Decimal)
            assert not isinstance(compared, float)


def _sentetik_protocol() -> ResolvedProtocol:
    """A two-answer synthetic protocol whose third step is gated on the
    decimal slot, so the FSM gate and the red-flag rule read the same
    value through the same `canonical_scalar`."""

    def resolved(key: str, **fields: object) -> ResolvedSlot:
        return ResolvedSlot(
            section_id="sentetik",
            key=key,
            fhir_link_id=f"sentetik.{key}",
            slot=Slot.model_validate(fields),
            delivery=Delivery.VOICE,
        )

    section = ResolvedSection(
        id="sentetik",
        delivery=Delivery.VOICE,
        allow_paraphrase=False,
        slots=(
            resolved("olay_zamani", type=SlotType.DATE, ask_tr="Sentetik: bu ne zaman oldu?"),
            resolved("olcum", type=SlotType.DECIMAL, ask_tr="Sentetik ölçüm sorusu."),
            resolved(
                "ek_soru",
                type=SlotType.BOOLEAN,
                ask_if=SENTETIK_WHEN,
                ask_tr="Sentetik ek soru.",
            ),
        ),
    )
    return ResolvedProtocol(
        pack_id="base.sentetik_esik",
        version="1.0.0",
        chain=("base.sentetik_esik",),
        sections=(section,),
        resolved_protocol_hash="0" * 64,
    )


def _drive(value: object) -> tuple[IntakeEngine, TriageContext]:
    """Answer the anchor and the decimal slot through the real
    `IntakeEngine.apply_extraction`, then project the engine's own answer
    state onto the triage context the rules evaluate over."""
    engine = IntakeEngine(protocol=_sentetik_protocol(), reference_time=REF_TIME)
    engine.mark_asked(SENTETIK_ANCHOR)
    engine.apply_extraction(SENTETIK_ANCHOR, {SENTETIK_ANCHOR: SENTETIK_GUN})
    engine.mark_asked(SENTETIK_OLCUM)
    engine.apply_extraction(SENTETIK_OLCUM, {SENTETIK_OLCUM: value})
    answers = {
        ref: SlotAnswer(state=engine.state_of(ref), values=(engine.value_of(ref),))
        for ref in (SENTETIK_ANCHOR, SENTETIK_OLCUM)
    }
    return engine, TriageContext(reference_time=REF_TIME, answers=answers)


class TestDecimalCarrierThroughIntakeEngine:
    """The boundary the value actually arrives through (files/03 §5
    `apply_extraction`), across all three carriers, so the extraction path
    (INT-083) and the typed path cannot disagree."""

    @pytest.mark.parametrize(
        ("carrier", "over", "under"),
        [
            ("decimal", Decimal("39"), Decimal("38")),
            ("int", 39, 38),
            ("float", 39.0, 38.0),
        ],
    )
    def test_apply_extraction_reaches_the_same_verdict_for_every_carrier(
        self, carrier: str, over: object, under: object
    ) -> None:
        rule = _esik_rule()
        _, fires = _drive(over)
        _, misses = _drive(under)
        assert evaluate_triage((rule,), fires, RedLocation.REMOTE).result.level is TriageLevel.RED
        assert (
            evaluate_triage((rule,), misses, RedLocation.REMOTE).result.level is TriageLevel.GREEN
        )

    @pytest.mark.parametrize(
        ("carrier", "over", "under"),
        [
            ("decimal", Decimal("39"), Decimal("38")),
            ("int", 39, 38),
            ("float", 39.0, 38.0),
        ],
    )
    def test_the_engines_own_gate_opens_on_the_same_reading(
        self, carrier: str, over: object, under: object
    ) -> None:
        # `IntakeEngine._lookup` canonicalises through the same function, so
        # a value invisible to a red-flag rule is invisible to the protocol
        # gate too — and an UNKNOWN gate never offers its step.
        opened, _ = _drive(over)
        closed, _ = _drive(under)
        assert SENTETIK_GATED in [step.step_id for step in opened.frontier()]
        assert SENTETIK_GATED not in [step.step_id for step in closed.frontier()]

    def test_the_engine_carries_the_decimal_without_converting_it(self) -> None:
        engine, context = _drive(Decimal("38.50"))
        carried = engine.value_of(SENTETIK_OLCUM)
        assert isinstance(carried, Decimal)
        assert not isinstance(carried, float)
        assert str(carried) == "38.50"
        assert engine.state_of(SENTETIK_OLCUM) is AnswerState.ASKED_PRESENT
        projected = context.answers[SENTETIK_OLCUM].values[0]
        assert isinstance(projected, Decimal)
        assert str(projected) == "38.50"
