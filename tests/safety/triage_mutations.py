"""INT-059 mutation harness — proof that the goldens can actually fail.

Acceptance clause, verbatim: "a deliberately broken RED rule fails the
suite (proved, reverted)". A golden suite that passes tells you nothing on
its own; what makes it a safety control is that a broken rule makes it go
red. This module applies representative breakages and asserts the suite
detects every one.

Every mutation here runs against an IN-MEMORY life-threat document or a
TEMP COPY of the pack directory (:func:`run_mutation` refuses to write
anywhere else — see :func:`_temp_pack_dir`). The real
``files/protocols/base.life_threat.yaml`` and
``tests/protocols/goldens/valid/*.yaml`` are never touched, so this is safe
in CI. The on-disk proved-then-reverted run required by the acceptance is
recorded in docs/evidence/INT-059.md.

A mutation "fails the suite" in either of two ways, both of which count:
the rule set refuses to BUILD (schema/validator refusal — the earlier line
of defence, e.g. a RED stripped of its register), or the built rule set
evaluates at least one golden differently from its recorded expectation.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from triage_goldens_corpus import (
    PACK_DIR,
    GoldenCase,
    RuleSets,
    build_rule_sets,
    load_life_threat_document,
    run_suite,
)

PackEdit = Callable[[dict[str, Any]], None]
LifeEdit = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class Mutation:
    """One deliberate breakage, with the class of defect it stands for."""

    id: str
    kind: str
    target: str
    description: str
    life_edit: LifeEdit | None = None
    pack_file: str | None = None
    pack_edit: PackEdit | None = None


@dataclass(frozen=True)
class MutationOutcome:
    """What the suite did when the mutation was applied."""

    mutation: Mutation
    build_error: str | None
    failed_case_ids: tuple[str, ...]

    @property
    def detected(self) -> bool:
        return self.build_error is not None or bool(self.failed_case_ids)

    def summary(self) -> str:
        if self.build_error is not None:
            return f"refused to build: {self.build_error.splitlines()[0][:120]}"
        return f"{len(self.failed_case_ids)} goldens failed, first: {self.failed_case_ids[0]}"


# ---------------------------------------------------------------------------
# Editing helpers — small, explicit, and total (a helper that cannot find its
# target raises, so a mutation can never silently become a no-op and score a
# false "detected").
# ---------------------------------------------------------------------------


class MutationTargetError(LookupError):
    """A mutation could not find what it meant to break."""


def _life_rule(document: dict[str, Any], rule_id: str) -> dict[str, Any]:
    for rule in document["rules"]:
        if rule["id"] == rule_id:
            return rule  # type: ignore[no-any-return]
    raise MutationTargetError(f"life-threat rule {rule_id!r} not found")


def _pack_rule(pack: dict[str, Any], rule_id: str) -> dict[str, Any]:
    for rule in pack.get("red_flags", ()):
        if rule["id"] == rule_id:
            return rule  # type: ignore[no-any-return]
    for op in pack.get("ops", ()):
        rule = op.get("rule")
        if rule is not None and rule["id"] == rule_id:
            return rule  # type: ignore[no-any-return]
    raise MutationTargetError(f"pack rule {rule_id!r} not found")


def _drop_pack_rule(pack: dict[str, Any], rule_id: str) -> None:
    before = len(pack.get("red_flags", ()))
    pack["red_flags"] = [rule for rule in pack.get("red_flags", ()) if rule["id"] != rule_id]
    if len(pack["red_flags"]) == before:
        raise MutationTargetError(f"pack rule {rule_id!r} not found to delete")


# ---------------------------------------------------------------------------
# The mutation set. Each entry names the defect class it stands for; the
# four the issue calls out by name are marked in ``kind``.
# ---------------------------------------------------------------------------

MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        id="red_gate_loosened_to_presence",
        kind="weaken a RED gate",
        target="rf.chest_pain_cardiac_features",
        description="the cardiac gate collapses to `chest_pain.present == true` — "
        "exactly the loosening LT-01-N was written to defend against; the "
        "positive LT-01-P keeps passing, so only the near-miss negatives catch it",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_cardiac_features").__setitem__(
            "gate", "chest_pain.present == true"
        ),
    ),
    Mutation(
        id="red_gate_kill_switch_removed",
        kind="weaken a RED gate",
        target="rf.chest_pain_cardiac_features",
        description="the `chest_pain.present == true` conjunct is dropped, so the "
        "feature disjunction fires on its own with no chest pain asserted",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_cardiac_features").__setitem__(
            "gate",
            'chest_pain.character in {"baskı", "sıkışma", "ağırlık"}\n'
            '|| chest_pain.radiation in {"kol", "çene", "sırt"}\n'
            "|| associated.diaphoresis == true\n"
            "|| associated.dyspnoea == true",
        ),
    ),
    Mutation(
        id="red_gate_narrowed_one_arm",
        kind="weaken a RED gate (under-trigger direction)",
        target="rf.synthetic_kirmizi",
        description="a disjunct arm is deleted from the base RED — the direction a "
        "positive-only suite is blind to, caught by the per-arm positives",
        pack_file="base.yaml",
        pack_edit=lambda pack: _pack_rule(pack, "rf.synthetic_kirmizi").__setitem__(
            "when", "renk_tercihi == 'kirmizi'"
        ),
    ),
    Mutation(
        id="red_rule_deleted_life",
        kind="delete a RED rule",
        target="rf.chest_pain_cardiac_features",
        description="the cardiac RED is removed from the life-threat set entirely",
        life_edit=lambda doc: doc.__setitem__(
            "rules",
            [rule for rule in doc["rules"] if rule["id"] != "rf.chest_pain_cardiac_features"],
        ),
    ),
    Mutation(
        id="red_rule_deleted_pack",
        kind="delete a RED rule",
        target="rf.synthetic_kirmizi",
        description="the base RED is deleted from the pack, which also orphans the "
        "child's tighten_rule parent",
        pack_file="base.yaml",
        pack_edit=lambda pack: _drop_pack_rule(pack, "rf.synthetic_kirmizi"),
    ),
    Mutation(
        id="comparison_flipped_equality",
        kind="flip a comparison",
        target="rf.synthetic_kirmizi",
        description="`==` becomes `!=` on the base RED's code comparison",
        pack_file="base.yaml",
        pack_edit=lambda pack: _pack_rule(pack, "rf.synthetic_kirmizi").__setitem__(
            "when", "renk_tercihi != 'kirmizi' || bekleme_suresi_asildi == true"
        ),
    ),
    Mutation(
        id="comparison_flipped_negation",
        kind="flip a comparison",
        target="rf.chest_pain_no_cardiac_history",
        description="the negated set membership loses its `!`, inverting the SARI arm "
        "into the cardiac feature set it was written to exclude",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_no_cardiac_history").__setitem__(
            "gate",
            "chest_pain.present == true\n"
            '&& (chest_pain.character in {"baskı", "sıkışma", "ağırlık"})\n'
            '&& chest_pain.radiation == "yok"\n'
            "&& associated.diaphoresis == false\n"
            "&& associated.dyspnoea == false\n"
            "&& trauma.recent == false",
        ),
    ),
    Mutation(
        id="register_axis_dropped",
        kind="drop a register axis",
        target="rf.chest_pain_cardiac_features",
        description="the RED loses its `register` — invariant 21 admits no default, "
        "so this must be refused rather than silently delivered as ALERT",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_cardiac_features").pop("register"),
    ),
    Mutation(
        id="register_changed_alert_to_calm",
        kind="drop a register axis (wrong value)",
        target="rf.chest_pain_cardiac_features",
        description="the register is silently changed ALERT → CALM: schema-legal, "
        "clinically a different delivery decision, and the goldens pin it",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_cardiac_features").__setitem__(
            "register", "CALM"
        ),
    ),
    Mutation(
        id="location_axis_dropped",
        kind="drop a location axis",
        target="rf.chest_pain_cardiac_features",
        description="the ON_SITE branch is deleted — a RED whose action does not "
        "resolve for all three locations must not compile (invariant 21)",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_cardiac_features")["action"].pop(
            "ON_SITE"
        ),
    ),
    Mutation(
        id="on_site_offers_112",
        kind="drop a location axis (ON_SITE semantics)",
        target="rf.synthetic_kirmizi",
        description="ON_SITE sets `show_112: true` — under ON_SITE the 112 affordance "
        "is absent, not de-emphasised (invariant 21)",
        pack_file="base.yaml",
        pack_edit=lambda pack: _pack_rule(pack, "rf.synthetic_kirmizi")["action"][
            "ON_SITE"
        ].__setitem__("show_112", True),
    ),
    Mutation(
        id="route_axis_changed",
        kind="change the route axis",
        target="rf.chest_pain_cardiac_features",
        description="EMERGENCY_NOW → SAME_DAY_ACIL. Axis 1 of invariant 21 rides on "
        "the rule, not on RulesTriageResult, so only a golden that pins the "
        "winning rule's route notices a RED quietly becoming a same-day referral",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_cardiac_features").__setitem__(
            "route", "SAME_DAY_ACIL"
        ),
    ),
    Mutation(
        id="red_level_downgraded",
        kind="relax acuity",
        target="rf.chest_pain_cardiac_features",
        description="KIRMIZI_K2 → SARI_K1: the RED stops being a RED and the axes "
        "disappear with it",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_cardiac_features").__setitem__(
            "level", "SARI_K1"
        ),
    ),
    Mutation(
        id="tighten_rule_relaxed",
        kind="relax acuity (monotonic inheritance)",
        target="rf.synthetic_kirmizi.genis",
        description="the child's tightened rule lowers acuity below its parent — "
        "children tighten, never relax (invariant 7); the validator must refuse it",
        pack_file="child.yaml",
        pack_edit=lambda pack: _pack_rule(pack, "rf.synthetic_kirmizi.genis").__setitem__(
            "level", "SARI_K2"
        ),
    ),
    Mutation(
        id="action_script_edited",
        kind="paraphrase a scripted action",
        target="rf.chest_pain_cardiac_features",
        description="the REMOTE `action_tr` is reworded — scripted RED text is spoken "
        "verbatim (invariant 10), so any edit is a suite failure",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_cardiac_features")["action"][
            "REMOTE"
        ].__setitem__("action_tr", "Bir doktora görünün."),
    ),
    Mutation(
        id="tense_widened",
        kind="widen a temporal window",
        target="rf.chest_pain_cardiac_features",
        description="`tense: now` becomes `ever`, so a years-old symptom fires a "
        "KIRMIZI_K2 — the boundary goldens are the only thing that sees it",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_cardiac_features").__setitem__(
            "tense", "ever"
        ),
    ),
    Mutation(
        id="tense_window_widened_sari",
        kind="widen a temporal window",
        target="rf.synthetic_sari",
        description="the SARI's window widens within_7d → within_30d, which the "
        "day-8 boundary golden catches",
        pack_file="base.yaml",
        pack_edit=lambda pack: _pack_rule(pack, "rf.synthetic_sari").__setitem__(
            "tense", "within_30d"
        ),
    ),
    Mutation(
        id="red_gate_narrowed_arms_dropped",
        kind="weaken a RED gate (under-trigger direction)",
        target="rf.chest_pain_cardiac_features",
        description="the diaphoresis and dyspnoea arms are deleted from the cardiac "
        "gate — an under-trigger with no build-time tripwire, caught by the "
        "per-arm positives alone",
        life_edit=lambda doc: _life_rule(doc, "rf.chest_pain_cardiac_features").__setitem__(
            "gate",
            "chest_pain.present == true\n"
            '&& (chest_pain.character in {"baskı", "sıkışma", "ağırlık"}\n'
            '    || chest_pain.radiation in {"kol", "çene", "sırt"})',
        ),
    ),
)


# ---------------------------------------------------------------------------
# Running a mutation. Nothing here writes outside ``tmp_root``.
# ---------------------------------------------------------------------------


def _temp_pack_dir(tmp_root: Path, mutation: Mutation) -> Path:
    """A throwaway copy of the pack directory with the mutation applied.

    The copy is the ONLY thing edited; ``PACK_DIR`` is read-only here.
    """
    target = tmp_root / mutation.id
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(PACK_DIR, target)
    if mutation.pack_file is None or mutation.pack_edit is None:
        return target
    path = target / mutation.pack_file
    pack = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutation.pack_edit(pack)
    path.write_text(yaml.safe_dump(pack, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return target


def run_mutation(
    mutation: Mutation,
    cases: tuple[GoldenCase, ...],
    tmp_root: Path,
    baseline_document: Mapping[str, Any] | None = None,
) -> MutationOutcome:
    """Apply one mutation to a temp copy / in-memory document and run the
    whole golden suite against the result."""
    document = deepcopy(dict(baseline_document or load_life_threat_document()))
    if mutation.life_edit is not None:
        mutation.life_edit(document)
    pack_dir = _temp_pack_dir(tmp_root, mutation)
    try:
        rule_sets = build_rule_sets(pack_dir=pack_dir, life_document=document)
    except Exception as exc:  # noqa: BLE001 — any refusal is a detection
        return MutationOutcome(
            mutation=mutation, build_error=f"{type(exc).__name__}: {exc}", failed_case_ids=()
        )
    failures = run_suite(rule_sets, cases)
    return MutationOutcome(
        mutation=mutation,
        build_error=None,
        failed_case_ids=tuple(sorted(failures)),
    )


def run_all(cases: tuple[GoldenCase, ...], tmp_root: Path) -> tuple[MutationOutcome, ...]:
    """Every mutation, against one shared baseline document read once."""
    baseline = load_life_threat_document()
    return tuple(run_mutation(m, cases, tmp_root, baseline) for m in MUTATIONS)


def baseline_is_green(cases: tuple[GoldenCase, ...], tmp_root: Path) -> RuleSets:
    """The unmutated control: the same builder over an untouched temp copy
    must be green, or a "detection" proves nothing."""
    control = tmp_root / "_control"
    if control.exists():
        shutil.rmtree(control)
    shutil.copytree(PACK_DIR, control)
    rule_sets = build_rule_sets(pack_dir=control)
    failures = run_suite(rule_sets, cases)
    if failures:
        raise AssertionError(f"the unmutated control is not green: {failures}")
    return rule_sets
