"""INT-059 — the triage golden suite and its mutation proof.

Acceptance (docs/backlog/issues.yaml INT-059, verbatim): "goldens across
base+clusters+deep; a deliberately broken RED rule fails the suite (proved,
reverted)".

The corpus (tests/safety/triage_goldens_cases.py, 206 cases) runs against
the rule content that exists in the repository TODAY — the INT-040
synthetic chain packs and the four exemplars of
files/protocols/base.life_threat.yaml. Nothing here invents a clinical rule,
threshold, register or Turkish string; where a case class has no rule to
exercise yet (numeric thresholds, KIRMIZI_K1, `ever` tense) the gap is
recorded in docs/evidence/INT-059.md rather than padded with a rule that no
clinician wrote.

The mutation harness (tests/safety/triage_mutations.py) is what makes the
suite a control rather than a decoration: seventeen deliberate breakages,
each of which must make the suite go red. Every mutation in CI runs against
an in-memory document or a temp copy — `test_the_real_packs_are_never_
written` proves the on-disk packs are byte-identical afterwards. The
proved-then-reverted on-disk run the acceptance calls for is recorded in
docs/evidence/INT-059.md.

Blueprint anchors: CLAUDE.md invariants 1, 7, 8, 10, 17, 21; files/02 §5.3;
files/04 §8.1-8.3; files/12 §1, §1.1, §2.4, §4, §7.3.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import triage_goldens_cases
from clinical_schemas.triage import RedLocation, TriageLevel
from protocols.types import RuleStatus
from triage_goldens_cases import (
    BK,
    CG,
    FAMILY_COUNTS,
    GOLDEN_CASES,
    MERGE_CONTEXT_LETTERS,
    MERGE_GROWING_CHAINS,
    NEAR_MISS_BY_RULE,
)
from triage_goldens_corpus import (
    LIFE_THREAT_PATH,
    PACK_DIR,
    GoldenCase,
    RuleSets,
    build_rule_sets,
    run_case,
)
from triage_mutations import MUTATIONS, MutationOutcome, baseline_is_green, run_all

# The acceptance floor. It only ever goes up (CLAUDE.md invariant 8 applies
# the same ratchet logic to coverage; the same reasoning holds here).
MINIMUM_GOLDENS = 200

CASES_BY_ID = {case.id: case for case in GOLDEN_CASES}


@pytest.fixture(scope="module")
def rule_sets() -> RuleSets:
    """The real, unmutated rule sets — built once from the repo's own files."""
    return build_rule_sets()


# ---------------------------------------------------------------------------
# The corpus itself.
# ---------------------------------------------------------------------------


class TestCorpusShape:
    def test_at_least_two_hundred_goldens(self) -> None:
        assert len(GOLDEN_CASES) >= MINIMUM_GOLDENS

    def test_case_ids_are_unique(self) -> None:
        assert len(CASES_BY_ID) == len(GOLDEN_CASES)

    @pytest.mark.parametrize(
        ("family", "claimed"), FAMILY_COUNTS, ids=[f for f, _ in FAMILY_COUNTS]
    )
    def test_the_family_arithmetic_is_honest(self, family: str, claimed: int) -> None:
        # The docstring table and docs/evidence/INT-059.md both publish these
        # counts; a builder that quietly grows or shrinks would make the
        # published derivation a lie.
        assert len(getattr(triage_goldens_cases, family)()) == claimed

    def test_the_family_counts_sum_to_the_corpus(self) -> None:
        assert sum(count for _, count in FAMILY_COUNTS) == len(GOLDEN_CASES)

    def test_every_case_carries_a_note(self) -> None:
        # A golden whose intent is not written down cannot be reviewed, and
        # an unreviewable safety case is a decoration.
        assert [case.id for case in GOLDEN_CASES if not case.note.strip()] == []

    def test_every_red_golden_declares_all_three_axes(self) -> None:
        # Invariant 21: RED is route × register × location, none of which has
        # a permitted default — so a RED golden that leaves one unstated is
        # not testing a RED. ``location`` is non-optional on the case.
        offenders = [
            case.id
            for case in GOLDEN_CASES
            if case.level is TriageLevel.RED
            and (case.winner is None or case.register is None or case.route is None)
        ]
        assert offenders == []

    def test_non_red_goldens_declare_no_red_axes(self) -> None:
        offenders = [
            case.id
            for case in GOLDEN_CASES
            if case.level is not TriageLevel.RED
            and (case.register is not None or case.winner is not None or case.route is not None)
        ]
        assert offenders == []


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda case: case.id)
def test_golden(case: GoldenCase, rule_sets: RuleSets) -> None:
    """Each golden: typed answer state in → the recorded determination out."""
    assert run_case(case, rule_sets) == [], case.note


# ---------------------------------------------------------------------------
# Coverage of the rule content that exists (files/04 §8.2
# `every_rule_has_a_true_positive_and_a_near_miss_negative`).
# ---------------------------------------------------------------------------


def _active_ids(rule_sets: RuleSets) -> set[str]:
    return {rule.id for rule in rule_sets.by_id.values() if rule.status is RuleStatus.ACTIVE}


class TestRuleCoverage:
    def test_every_active_rule_has_a_firing_golden(self, rule_sets: RuleSets) -> None:
        fired = {rule_id for case in GOLDEN_CASES for rule_id in case.fired}
        assert _active_ids(rule_sets) - fired == set()

    def test_every_active_rule_has_a_near_miss_negative(self, rule_sets: RuleSets) -> None:
        assert _active_ids(rule_sets) - set(NEAR_MISS_BY_RULE) == set()

    @pytest.mark.parametrize(
        ("rule_id", "case_ids"),
        sorted(NEAR_MISS_BY_RULE.items()),
        ids=sorted(NEAR_MISS_BY_RULE),
    )
    def test_declared_near_misses_really_do_not_fire(
        self, rule_id: str, case_ids: tuple[str, ...]
    ) -> None:
        # A near miss that quietly started firing would still be listed here
        # and would still "pass" as a negative — so assert the substance.
        assert case_ids
        for case_id in case_ids:
            case = CASES_BY_ID[case_id]
            assert rule_id not in case.fired, f"{case_id} no longer misses {rule_id}"

    def test_every_active_red_rule_is_exercised_at_all_three_locations(
        self, rule_sets: RuleSets
    ) -> None:
        # Invariant 21: a RED action must resolve for REMOTE, ON_SITE and
        # UNKNOWN, and under ON_SITE the 112 affordance is absent.
        red_ids = {
            rule.id
            for rule in rule_sets.by_id.values()
            if rule.level.is_red and rule.status is RuleStatus.ACTIVE
        }
        seen: dict[str, set[RedLocation]] = {rule_id: set() for rule_id in red_ids}
        for case in GOLDEN_CASES:
            if case.level is TriageLevel.RED and case.winner in seen:
                seen[case.winner].add(case.location)
        for rule_id, locations in seen.items():
            assert locations == set(RedLocation), (
                f"{rule_id} untested at {set(RedLocation) - locations}"
            )

    def test_on_site_goldens_never_expect_the_112_affordance(self) -> None:
        offenders = [
            case.id
            for case in GOLDEN_CASES
            if case.location is RedLocation.ON_SITE and case.action_show_112
        ]
        assert offenders == []

    def test_the_draft_exemplars_are_covered_by_a_refusal(self, rule_sets: RuleSets) -> None:
        # Invariant 17: an unsourced rule never produces a level. Both draft
        # exemplars live in the `life_with_drafts` set, which every
        # draft/* golden asserts is refused outright.
        refusals = [case for case in GOLDEN_CASES if case.expect_error is not None]
        assert refusals
        assert all(case.rule_set == "life_with_drafts" for case in refusals)


# ---------------------------------------------------------------------------
# Monotonic inheritance, read off the merge matrix (CLAUDE.md invariant 7 at
# runtime): as the rule set grows, a level never falls.
# ---------------------------------------------------------------------------


class TestMonotonicInheritance:
    @pytest.mark.parametrize("letter", MERGE_CONTEXT_LETTERS)
    def test_growing_the_rule_set_never_lowers_the_level(self, letter: str) -> None:
        for chain in MERGE_GROWING_CHAINS:
            severities: list[tuple[str, int]] = []
            for rule_set in chain:
                case = CASES_BY_ID.get(f"merge/{letter}-{rule_set}")
                if case is not None:
                    severities.append((rule_set, case.ek4.severity))
            for (smaller, low), (larger, high) in zip(severities, severities[1:], strict=False):
                assert high >= low, f"merge/{letter}: {larger} sits below {smaller}"

    def test_a_child_never_removes_a_parent_firing(self) -> None:
        # Deletion has no representation in the op set; the runtime shape of
        # that guarantee is that the parent's fired set is always a subset.
        for letter in MERGE_CONTEXT_LETTERS:
            base = CASES_BY_ID.get(f"merge/{letter}-base")
            child = CASES_BY_ID.get(f"merge/{letter}-child")
            if base is None or child is None:
                continue
            assert set(base.fired) <= set(child.fired), f"merge/{letter} lost a parent firing"

    def test_the_tightened_rule_never_replaces_its_parent(self) -> None:
        # files/12 §4 layer 2: tighten_rule mints a sibling and leaves the
        # parent live. Wherever the parent fires under `child`, both do.
        for case in GOLDEN_CASES:
            if case.rule_set == "child" and BK in case.fired:
                assert CG in case.fired, f"{case.id}: the parent fired without its tightening"


# ---------------------------------------------------------------------------
# The mutation proof — the acceptance's "deliberately broken RED rule fails
# the suite" clause, run in CI against copies only.
# ---------------------------------------------------------------------------


def _digests() -> dict[str, str]:
    paths = sorted(PACK_DIR.glob("*.yaml")) + [LIFE_THREAT_PATH]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


BASELINE_DIGESTS = _digests()


@pytest.fixture(scope="module")
def outcomes(tmp_path_factory: pytest.TempPathFactory) -> tuple[MutationOutcome, ...]:
    tmp_root = tmp_path_factory.mktemp("triage-mutations")
    baseline_is_green(GOLDEN_CASES, tmp_root)
    return run_all(GOLDEN_CASES, tmp_root)


class TestMutationProof:
    def test_the_unmutated_control_is_green(self, tmp_path: Path) -> None:
        # Without this, "the mutation was detected" proves nothing: a suite
        # that is red anyway detects everything.
        baseline_is_green(GOLDEN_CASES, tmp_path)

    def test_every_mutation_is_detected(self, outcomes: tuple[MutationOutcome, ...]) -> None:
        missed = [outcome.mutation.id for outcome in outcomes if not outcome.detected]
        assert missed == [], f"the golden suite survived: {missed}"

    @pytest.mark.parametrize(
        "mutation_id", [mutation.id for mutation in MUTATIONS], ids=lambda value: value
    )
    def test_mutation(self, mutation_id: str, outcomes: tuple[MutationOutcome, ...]) -> None:
        outcome = next(item for item in outcomes if item.mutation.id == mutation_id)
        assert outcome.detected, outcome.mutation.description

    def test_a_broken_red_rule_fails_the_suite(self, outcomes: tuple[MutationOutcome, ...]) -> None:
        # The acceptance clause, asserted directly: every mutation that
        # breaks a KIRMIZI rule — its gate, its acuity, its register, its
        # location axes or its script — makes the suite red.
        red_kinds = {
            "weaken a RED gate",
            "weaken a RED gate (under-trigger direction)",
            "delete a RED rule",
            "flip a comparison",
            "drop a register axis",
            "drop a register axis (wrong value)",
            "drop a location axis",
            "drop a location axis (ON_SITE semantics)",
            "change the route axis",
            "relax acuity",
        }
        red_outcomes = [item for item in outcomes if item.mutation.kind in red_kinds]
        assert len(red_outcomes) >= 13
        assert all(item.detected for item in red_outcomes)

    def test_all_three_red_axes_have_a_mutation(self) -> None:
        # Invariant 21 names three axes; a suite that pins only two would
        # still pass every mutation aimed at the third.
        kinds = {mutation.kind for mutation in MUTATIONS}
        assert any(kind.startswith("change the route axis") for kind in kinds)
        assert any(kind.startswith("drop a register axis") for kind in kinds)
        assert any(kind.startswith("drop a location axis") for kind in kinds)

    def test_the_four_named_mutation_classes_are_all_present(self) -> None:
        # The issue names four by hand; each must have at least one mutation.
        kinds = {mutation.kind for mutation in MUTATIONS}
        for named in (
            "weaken a RED gate",
            "delete a RED rule",
            "flip a comparison",
            "drop a register axis",
            "drop a location axis",
        ):
            assert any(kind.startswith(named) for kind in kinds), named

    def test_the_real_packs_are_never_written(self, outcomes: tuple[MutationOutcome, ...]) -> None:
        # The committed harness must be safe to run in CI: after every
        # mutation, the on-disk packs and the life-threat set are unchanged.
        assert outcomes  # force the mutation run before hashing
        assert _digests() == BASELINE_DIGESTS


# ---------------------------------------------------------------------------
# INT-255 — the translator drops nothing.
#
# `translate_life_threat_rule` projects the document onto a fixed list of DSL
# field names, so a field the DSL gains and the projection does not is
# silently dropped: the safety suite would then evaluate a rule the document
# does not contain — the crisis rule without its crisis path, the airway rule
# without its suppressed interrupt. Since INT-255 the whole document loads
# through `load_life_threat_set`, which gives this a second, independent
# reading of the same file to compare against.
# ---------------------------------------------------------------------------


def test_the_translator_carries_every_annotation_the_loader_does() -> None:
    from protocols.compile import load_life_threat_set
    from triage_goldens_corpus import (
        LIFE_THREAT_PATH,
        load_life_threat_document,
        translate_life_threat_rule,
    )

    loaded = load_life_threat_set(LIFE_THREAT_PATH)
    raw_rules = load_life_threat_document()["rules"]
    assert len(raw_rules) == len(loaded.rules)
    for raw, entry in zip(raw_rules, loaded.rules, strict=True):
        assert translate_life_threat_rule(raw) == entry.rule, entry.rule.id
