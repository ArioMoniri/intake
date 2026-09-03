"""INT-043 — ``base.intake``: complete in structure, empty in clinical value.

This suite is written the way the issue is scoped. ``base.intake`` is the
front-loaded root of the content chain, and it **closes only on a named
licensed physician's sign-off under CODEOWNERS** (HUMAN_BLOCKERS HB-C1). So
what is asserted here is not that the pack triages correctly — nothing in it
triages at all — but that:

- every section files/04 §1 names exists, and no other;
- every red-flag family files/04 §3 names exists, and no other;
- **not one of them asserts a clinical value a clinician has not supplied**:
  the trigger is the invariant-17 sanctioned literal, the rule is
  ``draft_needs_source``, and the compiler refuses it into a served pack;
- the six HB-C6 slot additions are authored as patient-facing question copy,
  which is the one part of this issue that is *not* clinical judgment;
- the gates that will bind the physician's content are already wired and
  already fail closed — invariant 21's register/location axes, the HB-C1
  sign-off interlock, the licence gate, the numeral boundary.

Everything patient-facing is Turkish; the English mirror is a sibling
document because the DSL has no English field (files/12 §1 pins
``language: tr``; CLAUDE.md invariant 5 makes the tr key the source of
truth).
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.bindings import OperationalTemplate
from protocols.compile import CompileError, LifeThreatSet, RefusalCode, resolve_protocol
from protocols.dsl import RedFlagRule, Slot
from protocols.loader import PackRegistry, load_pack
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.locale_text import entry_for
from protocols.pack import ProtocolPack
from protocols.types import Delivery, EK4Level, Maturity, PackLayer, RuleStatus
from protocols.validator import PLACEHOLDER_SIGNOFF_RE, pack_compilable, validate_packs

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKS_ROOT = REPO_ROOT / "packages" / "protocols"
BASE_INTAKE = PACKS_ROOT / "base" / "intake.yaml"
BASE_INTAKE_EN = PACKS_ROOT / "base" / "intake.en.yaml"
GOLDENS = Path(__file__).resolve().parent / "goldens" / "base" / "red_flag_families.yaml"

# files/04 §1, the eight rows of the `base.intake` table, in its order.
SECTIONS_04_S1: tuple[str, ...] = (
    "identity_check",
    "reason_for_visit",
    "hpi",
    "red_flags",
    "meds_allergies",
    "pmh_fh_sh",
    "screening",
    "expectations_wrapup",
)

# files/04 §3, the universal red-flag table. Exactly these families, no more:
# §1's `red_flags` row delegates to §3, and §3 is the enumeration.
FAMILIES_04_S3: tuple[str, ...] = (
    "rf.chest_pain_acute",
    "rf.stroke_fast",
    "rf.dyspnoea_rest",
    "rf.anaphylaxis",
    "rf.severe_bleeding",
    "rf.suicidal_intent",
    "rf.sepsis_like",
    "rf.thunderclap_headache",
    "rf.pregnancy_bleeding_pain",
    "rf.fever_high_persistent",
    "rf.weight_loss_unintentional",
    "rf.new_neuro_deficit_subacute",
    "rf.suicidal_ideation_passive",
)

# HUMAN_BLOCKERS HB-C6 — the six slots `base.intake` does not collect today.
HB_C6_ADDITIONS: tuple[str, ...] = (
    "pregnancy_status",
    "lmp_date",
    "immunosuppression",
    "anticoagulant_use",
    "weight_kg",
    "time_last_known_well",
)

# files/04 §1 "Turn budget: fast ≤ 18 turns"; files/02 §2 already records the
# content list at 16-21 turns in the clean case, i.e. over-subscribed BEFORE
# the six additions above. HB-C5 owns the reconciliation.
FAST_MODE_TURN_CEILING = 18

# CLAUDE.md invariant 12 register rule: `siz` universally, never `sen`,
# reachable only by mirroring. These are the second-person-singular forms a
# patient-facing string must never contain.
SEN_FORMS: tuple[str, ...] = ("sen", "sana", "seni", "senin", "sende", "senden")


@pytest.fixture(scope="module")
def pack() -> ProtocolPack:
    return load_pack(BASE_INTAKE)


@pytest.fixture(scope="module")
def base_registry(pack: ProtocolPack) -> PackRegistry:
    registry = PackRegistry()
    registry.add(pack)
    return registry


@pytest.fixture(scope="module")
def mirror() -> dict[str, Any]:
    loaded = yaml.safe_load(BASE_INTAKE_EN.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="module")
def goldens() -> dict[str, Any]:
    loaded = yaml.safe_load(GOLDENS.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _slots(pack: ProtocolPack) -> Iterator[tuple[str, str, Slot]]:
    for section_id, section in pack.sections.items():
        for key, slot in section.slots.items():
            yield section_id, key, slot


#: Every spoken slot field is a locale map: ``ask_tr`` and ``follow_up_tr``
#: since INT-297, ``confirm_tr`` since INT-314. The two shapes no longer
#: coexist, so the walker no longer has to know which is which — but the set is
#: kept named rather than inlined, because it is the list a reader checks the
#: DSL against.
_LOCALE_MAPPED = frozenset({"ask_tr", "confirm_tr", "follow_up_tr"})


def _patient_facing(pack: ProtocolPack) -> Iterator[tuple[str, str]]:
    """Every string a patient could hear or read, with its tr resource key.

    The resource key spelling is unchanged by INT-297 — ``<section>.<slot>.ask_tr``,
    ``…choices_tr[0]`` — because the English mirror is keyed BY it and a key that
    moved would silently orphan every mirror entry. What changed is where the
    Turkish is read from: the locale's own entry, via ``entry_for``, which raises
    rather than falling back.
    """
    for section_id, key, slot in _slots(pack):
        for field in ("ask_tr", "confirm_tr", "follow_up_tr"):
            value = getattr(slot, field)
            if value is None:
                continue
            text = entry_for(value, TR) if field in _LOCALE_MAPPED else value
            yield f"{section_id}.{key}.{field}", text
        if slot.choices_tr is not None:
            for index, choice in enumerate(entry_for(slot.choices_tr, TR)):
                yield f"{section_id}.{key}.choices_tr[{index}]", choice


def _tr_keys(pack: ProtocolPack) -> dict[str, str]:
    """The full tr resource key set the English mirror must cover 1:1."""
    keys = dict(_patient_facing(pack))
    if pack.title_tr is not None:
        keys["title_tr"] = pack.title_tr
    for rule in pack.red_flags:
        keys[f"{rule.id}.label_tr"] = rule.label_tr
    return keys


# --- the pack itself ---------------------------------------------------------


def test_pack_is_the_base_layer_root_and_is_not_servable(pack: ProtocolPack) -> None:
    """files/03 §6 resolution order: `base.intake` is the chain root. It is
    L0 until a physician signs (HB-C1), and L0 is never served (files/09 §2;
    CLAUDE.md invariant 13)."""
    assert pack.id == "base.intake"
    assert pack.layer is PackLayer.BASE
    assert pack.extends is None
    assert pack.language == "tr"
    assert pack.maturity is Maturity.L0
    assert "awaiting-clinical-review" in pack.status


def test_every_section_of_04_s1_is_present_and_no_others(pack: ProtocolPack) -> None:
    """files/04 §1 enumerates eight sections. Use exactly those, add none."""
    assert tuple(pack.sections) == SECTIONS_04_S1


def test_every_red_flag_family_of_04_s3_is_present_and_no_others(pack: ProtocolPack) -> None:
    """files/04 §1's `red_flags` row is "universal set (§3)"; §3 is the list."""
    assert tuple(rule.id for rule in pack.red_flags) == FAMILIES_04_S3


# --- nothing clinical is asserted --------------------------------------------


def test_no_family_asserts_a_trigger_a_clinician_has_not_supplied(pack: ProtocolPack) -> None:
    """Which symptoms constitute a red flag is clinical judgment. Every
    trigger is therefore the ONE sanctioned pending form (CLAUDE.md invariant
    17 sole exception) on a `draft_needs_source` rule — never a plausible
    predicate, which would read as authoritative to every later reader."""
    for rule in pack.red_flags:
        assert rule.status is RuleStatus.DRAFT_NEEDS_SOURCE, rule.id
        assert PLACEHOLDER_SIGNOFF_RE.fullmatch(rule.when) is not None, rule.id
        assert rule.source is None, rule.id
        assert rule.source_gap is not None and rule.source_gap.strip(), rule.id


def test_no_family_asserts_an_ek4_acuity_no_snapshot_supports(pack: ProtocolPack) -> None:
    """files/04 §3's table predates the EK-4 correction below it, and that
    correction says in terms that **a naive three-to-three colour map
    systematically under-triages**. Mapping §3's RED/YELLOW onto the five
    EK-4 levels is therefore the named failure mode, not a transcription — so
    every family sits at the schema's floor, which asserts nothing, exactly
    as INT-057's generator does for the same reason."""
    for rule in pack.red_flags:
        assert rule.level is EK4Level.YESIL, rule.id
        assert rule.level.severity == 0, rule.id


def test_each_source_gap_names_what_the_physician_must_supply(pack: ProtocolPack) -> None:
    """A `source_gap` that says only "no source" tells the physician nothing.
    Each one names the five decisions HB-C1 is waiting on."""
    for rule in pack.red_flags:
        gap = (rule.source_gap or "").casefold()
        for owed in ("trigger", "ek-4", "route", "register", "action"):
            assert owed in gap, f"{rule.id}: source_gap does not name {owed!r}"


def test_the_pack_carries_no_pending_value_outside_the_sanctioned_form(
    base_registry: PackRegistry,
) -> None:
    """CLAUDE.md invariant 17: the allow-list may only shrink, and the sole
    exception is the sign-off literal inside a draft rule."""
    codes = {finding.code.value for finding in validate_packs(base_registry)}
    assert "PLACEHOLDER_FORM" not in codes
    assert "PLACEHOLDER_OUTSIDE_DRAFT" not in codes


def test_the_no_placeholders_gate_accepts_the_pack_files() -> None:
    """The gate scans `git ls-files` line by line; the sanctioned form is its
    one exception and it only applies under packages/protocols/**. Run the
    real gate over the real files rather than trusting the regex twice."""
    result = subprocess.run(  # noqa: S603
        ["bash", str(REPO_ROOT / "scripts" / "ci" / "no_placeholders.sh"), *_gate_targets()],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _gate_targets() -> list[str]:
    return [
        str(path.relative_to(REPO_ROOT))
        for path in (BASE_INTAKE, BASE_INTAKE_EN, GOLDENS, Path(__file__))
    ]


def test_validator_reports_nothing_against_the_pack(base_registry: PackRegistry) -> None:
    """Monotonicity, follow_up_tr presence, instrument fidelity and licensing,
    numerals, op capabilities — the INT-040 surface, clean."""
    assert validate_packs(base_registry) == ()


def test_no_licence_blocked_instrument_is_referenced(pack: ProtocolPack) -> None:
    """C-SSRS and WHO-5 are BLOCKED (HB-L2, HB-L3). files/04 §1 lists a
    `cssrs_screen` slot, so the slot exists and the path is wired — but the
    instrument is never referenced, so the pack does not smuggle a blocked
    licence in behind a slot name."""
    report = pack_compilable(pack)
    assert report.blocked_instruments == ()
    questionnaires = {q for section in pack.sections.values() for q in section.questionnaires}
    assert "C-SSRS" not in questionnaires
    assert "WHO-5" not in questionnaires
    assert "cssrs_screen" in pack.sections["screening"].slots
    assert pack.sections["screening"].slots["cssrs_screen"].ask_tr is None


def test_every_draft_family_is_excluded_from_a_served_pack(pack: ProtocolPack) -> None:
    """files/04 §8.1 rule 3 — reported by the validator, refused by the
    compiler. Both halves matter; this is the reporting half."""
    assert pack_compilable(pack).excluded_rules == FAMILIES_04_S3
    assert not pack_compilable(pack).fully_compilable


# --- the compiler refusals, pinned against THIS pack -------------------------


def _refuse(
    pack_id: str,
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
) -> dict[RefusalCode, list[str]]:
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id=pack_id, registry=registry, life_threat=life_threat, template=template
        )
    grouped: dict[RefusalCode, list[str]] = {}
    for refusal in excinfo.value.refusals:
        grouped.setdefault(refusal.code, []).append(refusal.subject)
    return grouped


def test_the_compiler_refuses_this_pack_and_the_reasons_are_the_human_blockers(
    base_registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The success condition of INT-043 is a refusal. With a fully SIGNED
    life-threat set the only reasons left are this pack's own: it is L0, and
    all thirteen families are unsourced drafts. Nothing else — no binding
    gap, no numeral, no unresolvable gate — which is what makes the refusal
    list a to-do list for one physician rather than a bug list."""
    grouped = _refuse("base.intake", base_registry, life_threat, template)
    assert set(grouped) == {RefusalCode.PACK_NOT_SERVABLE, RefusalCode.DRAFT_RULE_NOT_SERVED}
    assert grouped[RefusalCode.PACK_NOT_SERVABLE] == ["base.intake"]
    # the compiler reports rules sorted by id, not in declaration order
    assert sorted(grouped[RefusalCode.DRAFT_RULE_NOT_SERVED]) == sorted(FAMILIES_04_S3)


def test_an_unfilled_clinical_signoff_blocks_the_l1_bundle(
    base_registry: PackRegistry,
    patched_life_threat: Any,
    template: OperationalTemplate,
) -> None:
    """HB-C1, asserted against this pack rather than in the abstract: while
    the six sign-off fields are null the compiler refuses, and it refuses for
    the paediatric signature separately, because an adult signature does not
    cover a paediatric rule."""
    unsigned = patched_life_threat(
        {
            "served": False,
            "serve_blocked_reason": "L0 / awaiting-clinical-review (HB-C1).",
            "clinical_signoff": {
                "reviewer_name": None,
                "reviewer_licence_no": None,
                "reviewer_specialty": None,
                "signed_commit": None,
                "signed_on": None,
                "paediatric_reviewer_name": None,
            },
        }
    )
    grouped = _refuse("base.intake", base_registry, unsigned, template)
    assert RefusalCode.CLINICAL_SIGNOFF_INCOMPLETE in grouped
    assert RefusalCode.LIFE_THREAT_SET_NOT_SERVED in grouped
    assert RefusalCode.PACK_NOT_SERVABLE in grouped


def test_promoting_the_pack_to_l1_does_not_make_a_draft_family_servable(
    pack: ProtocolPack, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The maturity ladder and rule provenance are independent gates. An
    engineer who "fixes" the refusal by editing `maturity:` still gets
    thirteen refusals — there is no bypass (HUMAN_BLOCKERS Rule 2)."""
    promoted = PackRegistry()
    promoted.add(pack.model_copy(update={"maturity": Maturity.L1}))
    grouped = _refuse("base.intake", promoted, life_threat, template)
    assert set(grouped) == {RefusalCode.DRAFT_RULE_NOT_SERVED}
    assert sorted(grouped[RefusalCode.DRAFT_RULE_NOT_SERVED]) == sorted(FAMILIES_04_S3)


def test_a_family_promoted_to_red_must_declare_register_and_all_three_locations(
    pack: ProtocolPack, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """CLAUDE.md invariant 21, wired ahead of the content it will govern.

    The moment the physician sets a family's acuity to KIRMIZI, register and
    a REMOTE/ON_SITE/UNKNOWN action become mandatory with **no permitted
    default** — the compiler says so before any text is written. This is the
    gate, proved against this pack, in the state the pack is actually in.
    """
    family = next(rule for rule in pack.red_flags if rule.id == "rf.stroke_fast")
    red = RedFlagRule.model_construct(
        **{
            **family.model_dump(),
            "level": EK4Level.KIRMIZI_K2,
            "status": RuleStatus.ACTIVE,
            "when": "stroke_probe == true",
        }
    )
    registry = PackRegistry()
    registry.add(pack.model_copy(update={"red_flags": (red,), "maturity": Maturity.L1}))
    grouped = _refuse("base.intake", registry, life_threat, template)
    assert RefusalCode.RED_MISSING_REGISTER in grouped
    assert RefusalCode.RED_ACTION_UNRESOLVED in grouped


# --- the six HB-C6 additions -------------------------------------------------


def test_the_six_hb_c6_additions_are_authored_as_askable_question_copy(
    pack: ProtocolPack,
) -> None:
    """HB-C6: without `ask_tr`, `follow_up_tr` and `choices_tr[]` the gate
    `no_rule_references_an_undeclared_slot` fails and `rf.stroke_fast` has no
    `tense_anchor`. Question copy is the one part of this issue that is
    patient-facing wording rather than clinical judgment, so it is authored
    in full."""
    declared = {key: slot for _, key, slot in _slots(pack)}
    for key in HB_C6_ADDITIONS:
        assert key in declared, key
        slot = declared[key]
        assert slot.ask_tr, key
        assert slot.follow_up_tr, key
        if slot.valueset is not None:
            assert slot.choices_tr, key


def test_stroke_fast_has_its_tense_anchor(pack: ProtocolPack) -> None:
    """HB-C6 names the consequence of the missing slot exactly: "`rf.stroke_fast`
    has no `tense_anchor`". files/12 §2.4 — a tense-qualified rule cannot fire
    on an undated symptom."""
    stroke = next(rule for rule in pack.red_flags if rule.id == "rf.stroke_fast")
    assert stroke.tense_anchor == "time_last_known_well"
    declared = {key for _, key, _ in _slots(pack)}
    assert {rule.tense_anchor for rule in pack.red_flags} <= declared


def test_pregnancy_and_lmp_are_text_first_and_screening_is_text_only(
    pack: ProtocolPack,
) -> None:
    """files/13 §13: screening is `text_only`; pregnancy/LMP are `text_first`.
    "text_only must mean text only: no clip, no speech_tr, ever"."""
    assert pack.sections["screening"].delivery is Delivery.TEXT_ONLY
    for _, key, slot in _slots(pack):
        if key in ("pregnancy_status", "lmp_date"):
            assert slot.delivery is Delivery.TEXT_FIRST, key
        if key in pack.sections["screening"].slots:
            assert slot.delivery in (None, Delivery.TEXT_ONLY), key


# --- representation and register boundaries ----------------------------------


def test_no_patient_facing_string_carries_a_numeral(pack: ProtocolPack) -> None:
    """CLAUDE.md invariant 22 / files/03 §4.9.6. Authored Turkish carries the
    number words; the compiler owns expansion, and both TTS candidates'
    built-in normalisers are disabled, so a digit here has nowhere safe to
    go."""
    for key, text in _patient_facing(pack):
        assert not any(char.isdigit() for char in text), f"{key}: {text!r}"


def test_every_question_asks_exactly_one_thing(pack: ProtocolPack) -> None:
    """CLAUDE.md invariant 2: one question per turn. A comma-joined second
    interrogative is still a second question — a patient who answers "evet"
    has answered one of them and nobody knows which."""
    for key, text in _patient_facing(pack):
        assert text.count("?") <= 1, f"{key}: {text!r}"


def test_patient_copy_uses_the_siz_register(pack: ProtocolPack) -> None:
    """CLAUDE.md clinical content rules: `siz` universally, never `sen`.
    Warmth comes from verb mood, not from the pronoun."""
    for key, text in _patient_facing(pack):
        words = {
            "".join(char for char in word.casefold() if char.isalpha())
            for word in text.replace("’", "'").split()
        }
        assert not words & set(SEN_FORMS), f"{key}: {text!r}"


# --- standards bindings ------------------------------------------------------


def test_every_slot_declares_an_openehr_annotation_exactly_once(pack: ProtocolPack) -> None:
    """ADR-002 / files/12 §8: a slot declares an archetype path OR a recorded
    reason for not having one — never both, never neither, so absence stays a
    decision."""
    for section_id, key, slot in _slots(pack):
        declared = (slot.openehr_path is not None, slot.openehr_deferred_reason is not None)
        assert sum(declared) == 1, f"{section_id}.{key}"


def test_every_declared_openehr_path_resolves_in_the_pinned_template(
    pack: ProtocolPack, template: OperationalTemplate
) -> None:
    """files/12 §8.1 / invariant 31 — the walker fails closed rather than
    resolving against a fabrication."""
    for section_id, key, slot in _slots(pack):
        if slot.openehr_path is not None:
            assert template.resolve(slot.openehr_path) is not None, f"{section_id}.{key}"


# --- the English mirror (CLAUDE.md invariant 5) ------------------------------


def test_the_english_mirror_covers_every_tr_key_and_invents_none(
    pack: ProtocolPack, mirror: dict[str, Any]
) -> None:
    """`tr` resource keys are the source of truth and lint fails on a missing
    `tr`. The DSL has no English field (files/12 §1 pins `language: tr`), so
    the mirror is a sibling document keyed by the tr resource key — and the
    key set must match exactly in both directions."""
    assert mirror["kind"] == "text_mirror"
    assert mirror["pack_id"] == "base.intake"
    assert mirror["language_source"] == "tr"
    assert mirror["language_mirror"] == "en"
    entries = mirror["entries"]
    assert set(entries) == set(_tr_keys(pack))
    for key, english in entries.items():
        assert isinstance(english, str) and english.strip(), key


def test_the_mirror_is_not_loadable_as_a_pack() -> None:
    """It shares the layer directory with the pack, so the registry must pass
    over it the way it passes over `life_threat_set` (files/12 §1)."""
    registry_ids = {p.id for p in _load_base_layer()}
    assert registry_ids == {"base.intake"}


def _load_base_layer() -> list[ProtocolPack]:
    packs: list[ProtocolPack] = []
    for path in sorted((PACKS_ROOT / "base").glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("kind") != "pack":
            continue
        packs.append(load_pack(path))
    return packs


# --- goldens: a near-miss negative control for every family ------------------


def test_every_family_has_a_positive_and_a_near_miss_negative(
    goldens: dict[str, Any],
) -> None:
    """files/04 §8.2 `every_rule_has_a_true_positive_and_a_near_miss_negative`.

    The negative matters more than the positive: a positive can only ever
    detect UNDER-triggering, and it keeps passing under every loosening of
    the gate. Over-triggering is invisible to it, and alert fatigue is the
    mechanism by which a correct rule stops working.
    """
    assert tuple(goldens["families"]) == FAMILIES_04_S3
    for family, entry in goldens["families"].items():
        assert entry["positive"]["case"].strip(), family
        negative = entry["near_miss_negative"]
        assert negative["case"].strip(), family
        assert negative["why_it_is_a_near_miss"].strip(), family
        assert entry["attribute_under_test"].strip(), family


def test_no_golden_asserts_an_outcome_while_the_trigger_is_unsigned(
    goldens: dict[str, Any],
) -> None:
    """A golden that asserted `fires: true` would be asserting the very
    clinical judgment HB-C1 is waiting for, dressed as a test. Each case is
    therefore carried, not executed, and says so with the blocker id — so the
    suite turns executable in the same PR that supplies the trigger."""
    for family, entry in goldens["families"].items():
        assert entry["executable"] is False, family
        assert "HB-C1" in entry["blocked_by"], family


def test_every_golden_family_matches_a_declared_rule(
    pack: ProtocolPack, goldens: dict[str, Any]
) -> None:
    """A golden for a family the pack does not declare is a golden nothing
    will ever run."""
    assert set(goldens["families"]) == {rule.id for rule in pack.red_flags}


# --- the turn budget (HB-C5) -------------------------------------------------


def test_the_fast_mode_turn_budget_is_over_subscribed(pack: ProtocolPack) -> None:
    """files/02 §2 records the content list at 16-21 turns against files/04
    §1's ≤ 18, and HB-C6's six additions land on top of that.

    This test exists so the collision is a **measured** number in CI rather
    than a sentence in a document. It is deliberately an inequality against
    the ceiling and not a pin on today's count: cutting content, raising the
    budget or compounding questions is a clinical decision (HB-C5, `00 §5`
    Q8, owner ClinicalAuthor) and an agent may not choose it. Whoever
    resolves it edits this test in the same PR, which is the review surface.
    """
    must_ask = [f"{section}.{key}" for section, key, slot in _slots(pack) if slot.must_ask]
    assert len(must_ask) > FAST_MODE_TURN_CEILING, (
        "the fast-mode collision is resolved but HB-C5 is still open: "
        f"{len(must_ask)} must-ask steps against a ceiling of {FAST_MODE_TURN_CEILING}"
    )


def test_the_five_unconditional_additions_are_part_of_that_count(pack: ProtocolPack) -> None:
    """Five of the six HB-C6 slots cost a turn unconditionally as authored:
    `lmp_date` is the only one the DSL can gate (`ask_if` projects a slot
    comparison), because `weight_kg` needs `age_years()` and
    `time_last_known_well` needs a red-flag probe whose trigger is unsigned —
    and files/13 §9.5's function whitelist is not projectable into a FHIR
    `enableWhen`. That is the arithmetic HB-C5 must be given."""
    declared = {key: slot for _, key, slot in _slots(pack)}
    assert declared["lmp_date"].ask_if is not None
    ungated = [key for key in HB_C6_ADDITIONS if declared[key].ask_if is None]
    assert len(ungated) == 5
