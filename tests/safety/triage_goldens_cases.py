"""INT-059 golden corpus — assembly, arithmetic, and the last three families.

This module is what the suite imports: it assembles ``GOLDEN_CASES`` from
the family builders, publishes the arithmetic as data (``FAMILY_COUNTS``),
and declares the per-rule near misses (``NEAR_MISS_BY_RULE``) and the
merge-matrix reading order. Families 10, 11 and 13 (draft refusal, LLM
candidate ceiling, the green baseline) are small enough to live here; the
rest sit in sibling modules so no file passes the 500-line ceiling:

- ``triage_goldens_fixtures``  — shorthands and case constructors
- ``triage_goldens_symptoms``  — families 1-2 (firing arms, near misses)
- ``triage_goldens_answers``   — families 3, 4, 6, 14 (answer state)
- ``triage_goldens_temporal``  — family 5 (tense windows)
- ``triage_goldens_structure`` — families 7-9, 12 (axes, merge, sibling set)
- ``triage_goldens_anchors``   — family 15 (CD-05 onset choices, INT-522)

Arithmetic (``test_the_family_arithmetic_is_honest`` asserts every builder
really produces its claimed count; the total is asserted ≥ 200 in
tests/safety/test_triage_goldens.py):

======================  =====  ==================================================
family                  cases  what a mutation would have to survive
======================  =====  ==================================================
fired_positive_arms        19  every disjunct arm of every rule fires
near_miss_negatives        17  one attribute off → must NOT fire (repo convention)
valueless_states           35  files/12 §1.1: Unknown never fires; declines too
explicit_absent            7   asked_absent carries its value both directions
temporal_boundaries        42  every tense window: at / inside / outside / defect
contested_values           13  files/12 §7.3 escalating world union
red_axes_locations         15  invariant 21 axes + verbatim scripts per location
merge_matrix               42  8 contexts × the inheritance sets, absolute cells
sibling_life_threat        3   base.life_threat rides alongside, never diluted
draft_refusal              2   draft_needs_source rules refuse to evaluate
candidate_ceiling          3   LLM flags attach, level/action untouched
register_tiebreak          3   equal-severity RED winner is total and stable
green_baseline             1   the life set alone, empty context
type_mismatch_unknown      6   cross-type comparison is Unknown, never False
anchor_choices             10  CD-05: each onset choice's day, near miss 3 days
======================  =====  ==================================================
total                     218

Rule levels available in merged content today: KIRMIZI_K2 (rf.synthetic_
kirmizi, rf.synthetic_kirmizi.genis, rf.chest_pain_cardiac_features),
SARI_K1 (rf.synthetic_dal_sari, rf.chest_pain_no_cardiac_history), SARI_K2
(rf.synthetic_sari, rf.synthetic_ek_sari). No active KIRMIZI_K1, no YESIL
rule, no ``ever``-tensed rule and no numeric-threshold comparison exists in
merged content yet — those classes are covered at engine level by the
INT-080 synthetic suite and join this corpus when such rules land
(docs/evidence/INT-059.md records the gap arithmetic).
"""

from __future__ import annotations

from protocols.triage import DraftRuleError
from protocols.types import EK4Level
from triage_goldens_anchors import anchor_choices
from triage_goldens_answers import (
    contested_values,
    explicit_absent,
    type_mismatch_unknown,
    valueless_states,
)
from triage_goldens_corpus import (
    AW_ANCHOR,
    BK,
    BS,
    C1,
    C2,
    CD,
    CG,
    OE,
    TODAY,
    GoldenCase,
    p,
)
from triage_goldens_fixtures import green, red, syn, yellow
from triage_goldens_structure import (
    merge_matrix,
    red_axes_locations,
    register_tiebreak,
    sibling_life_threat,
)
from triage_goldens_symptoms import fired_positive_arms, near_miss_negatives
from triage_goldens_temporal import temporal_boundaries

# Re-exported so a reader (and the tests) can reach every rule id and case
# constructor through the one module the suite imports.
__all__ = [
    "FAMILY_COUNTS",
    "GOLDEN_CASES",
    "MERGE_CONTEXT_LETTERS",
    "MERGE_GROWING_CHAINS",
    "NEAR_MISS_BY_RULE",
    "BK",
    "BS",
    "C1",
    "C2",
    "CD",
    "CG",
    "OE",
]

# ---------------------------------------------------------------------------
# Family 10 — draft_needs_source rules refuse to evaluate (2; invariant 17,
# files/04 §8.1 rule 3 — defence in depth behind pack_compilable).
# ---------------------------------------------------------------------------


def draft_refusal() -> list[GoldenCase]:
    return [
        GoldenCase(
            id="draft/empty",
            rule_set="life_with_drafts",
            answers={},
            note="the engine refuses a draft rule before reading any slot",
            expect_error=DraftRuleError,
        ),
        GoldenCase(
            id="draft/airway",
            rule_set="life_with_drafts",
            answers={
                AW_ANCHOR: p(TODAY),
                "subject.age_years": p(3),
                "airway.stridor_reported": p(True),
            },
            note="a would-be-positive paediatric airway case still refuses:"
            " an unsourced rule never produces a level",
            expect_error=DraftRuleError,
        ),
    ]


# ---------------------------------------------------------------------------
# Family 11 — LLM candidates attach as flags only (3; invariant 1).
# ---------------------------------------------------------------------------


def candidate_ceiling() -> list[GoldenCase]:
    return [
        GoldenCase(
            id="cand/green",
            rule_set="base",
            answers={},
            note="candidates on GREEN: flags carried, level untouched",
            candidates=2,
        ),
        yellow(
            "cand/yellow",
            "base",
            syn(bekleme_suresi_gun_asimi=p(True)),
            (BS,),
            EK4Level.SARI_K2,
            "candidates on YELLOW: the rules result passes through unchanged",
        ),
        red(
            "cand/red",
            "base",
            syn(renk_tercihi=p("kirmizi")),
            (BK,),
            BK,
            "candidates on RED: level, axes and script all untouched",
        ),
    ]


def _with_candidates(cases: list[GoldenCase]) -> list[GoldenCase]:
    adjusted: list[GoldenCase] = []
    for case in cases:
        if case.id.startswith("cand/") and case.candidates == 0:
            adjusted.append(
                GoldenCase(**{**case.__dict__, "candidates": 3})  # type: ignore[arg-type]
            )
        else:
            adjusted.append(case)
    return adjusted


# ---------------------------------------------------------------------------
# Families 13/14 — green baseline (1) and cross-type Unknown (6).
# ---------------------------------------------------------------------------


def green_baseline() -> list[GoldenCase]:
    return [green("green/life-empty", "life", {}, "the life set alone, nothing asked: GREEN")]


# The corpus arithmetic, as data rather than prose: family → the count this
# module's docstring claims for it. `test_the_family_arithmetic_is_honest`
# asserts each builder really produces that many and that they sum to the
# corpus size, so the documented derivation cannot drift away from the code
# (the issue asks for the arithmetic to be auditable, not asserted).
FAMILY_COUNTS: tuple[tuple[str, int], ...] = (
    ("fired_positive_arms", 19),
    ("near_miss_negatives", 17),
    ("valueless_states", 35),
    ("explicit_absent", 7),
    ("temporal_boundaries", 42),
    ("contested_values", 13),
    ("red_axes_locations", 15),
    ("merge_matrix", 42),
    ("sibling_life_threat", 3),
    ("draft_refusal", 2),
    ("candidate_ceiling", 3),
    ("register_tiebreak", 3),
    ("green_baseline", 1),
    ("type_mismatch_unknown", 6),
    ("anchor_choices", 10),
)


def build_cases() -> tuple[GoldenCase, ...]:
    cases: list[GoldenCase] = []
    cases.extend(fired_positive_arms())
    cases.extend(near_miss_negatives())
    cases.extend(valueless_states())
    cases.extend(explicit_absent())
    cases.extend(temporal_boundaries())
    cases.extend(contested_values())
    cases.extend(red_axes_locations())
    cases.extend(merge_matrix())
    cases.extend(sibling_life_threat())
    cases.extend(draft_refusal())
    cases.extend(_with_candidates(candidate_ceiling()))
    cases.extend(register_tiebreak())
    cases.extend(green_baseline())
    cases.extend(type_mismatch_unknown())
    cases.extend(anchor_choices())
    return tuple(cases)


GOLDEN_CASES: tuple[GoldenCase, ...] = build_cases()

# Every ACTIVE rule in merged content → the near-miss negatives written for
# it. files/protocols/base.life_threat.yaml states why this mapping, not the
# positives, is the load-bearing half: a positive keeps passing under every
# loosening of the gate, so only a negative sitting one attribute away — on
# the exact attribute the gate turns on — can detect silent gate drift. The
# suite asserts the mapping is total over the active rules and that each
# listed case really does leave its rule unfired (CI gate
# ``every_rule_has_a_true_positive_and_a_near_miss_negative``, files/04 §8.2).
NEAR_MISS_BY_RULE: dict[str, tuple[str, ...]] = {
    BK: ("miss/bk-diakritik", "miss/bk-buyuk-harf", "miss/bk-mavi"),
    BS: ("miss/bs", "tense/bs-disi"),
    CD: ("miss/child-all-off",),
    CG: ("miss/child-all-off",),
    OE: ("miss/oe", "tense/oe-disi"),
    C1: (
        "miss/lt01n",
        "miss/c1-karakter",
        "miss/c1-yayilim",
        "miss/c1-diakritik",
        "miss/c1-kill-switch",
        "anchor/c1-uc-gunden-once",
    ),
    C2: (
        "miss/lt02n-dispne",
        "miss/c2-karakter",
        "miss/c2-yayilim",
        "miss/c2-terleme",
        "miss/c2-travma",
        "miss/c2-mevcut-degil",
        "anchor/c2-uc-gunden-once",
    ),
}

# The merge-matrix columns, in growing-rule-set order. Reading down a column
# must never lower the level (CLAUDE.md invariant 7 at runtime).
MERGE_CONTEXT_LETTERS: tuple[str, ...] = ("a", "b", "c", "d", "e", "f", "g", "h")
MERGE_GROWING_CHAINS: tuple[tuple[str, ...], ...] = (
    ("base", "child", "child_overlay", "child_overlay_life"),
    ("overlay", "child_overlay", "child_overlay_life"),
)
