"""INT-619 — the thirteen base.intake red-flag families, written where a source allows.

Owner, 18 Nov 2026, in chat: *"yes write the 13 red flag rules"*. Read with D18
(files/00_STATE.md §3): agent-sourced clinical content for the synthetic host and
simulated patients only, checked by an independent verifier, with a licensed
physician signing before any real patient. ``clinical_signoff`` is untouched and the
pack stays L0, so nothing here reaches a patient.

What is pinned, each with its near miss:

- which families became active rules and which stay ``draft_needs_source``, and why
  (the two suicide families are licence-blocked, HB-L2, and wait on HB-C8);
- every active rule cites a committed snapshot and its quote is verbatim there —
  checked by the pack loader itself, which refuses a chain-pack rule whose quote is
  not (the near miss: one word changed);
- every KIRMIZI rule declares a register and resolves for REMOTE, ON_SITE and
  UNKNOWN, offers no 112 under ON_SITE, and spells every number out (invariant 22);
- every trigger reads only declared slots, and every tense anchor is a dated slot,
  so no active rule is dead on arrival;
- the register entries CD-108..CD-120 load, one per family;
- ``files/protocols/base.life_threat.yaml`` is byte-identical, so the D23 synthetic
  signature still verifies.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.clinical_decisions import DecisionStatus, load_decision
from protocols.dsl import RedFlagRule
from protocols.loader import PackSchemaError, check_rule_sources, load_pack
from protocols.pack import ProtocolPack
from protocols.source_snapshots import source_snapshot_problem
from protocols.triage.expr import parse_when, referenced_slots
from protocols.types import EK4Level, RedFlagRoute, RuleStatus, SlotType
from protocols.validator import PLACEHOLDER_SIGNOFF_RE

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_INTAKE = REPO_ROOT / "packages" / "protocols" / "base" / "intake.yaml"
DECISIONS = REPO_ROOT / "packages" / "protocols" / "decisions"
DOCS_DECISIONS = REPO_ROOT / "docs" / "clinical" / "decisions"
SOURCES = REPO_ROOT / "packages" / "protocols" / "sources"
LIFE_THREAT = REPO_ROOT / "files" / "protocols" / "base.life_threat.yaml"
RED_SIGNATURE = REPO_ROOT / "packages" / "protocols" / "signing" / "red_rule_set.synthetic.json"

#: family -> (status, EK-4 level, route, register or None, decision id)
EXPECTED: dict[str, tuple[RuleStatus, EK4Level, RedFlagRoute, str | None, str]] = {
    "rf.chest_pain_acute": (
        RuleStatus.ACTIVE,
        EK4Level.KIRMIZI_K2,
        RedFlagRoute.EMERGENCY_NOW,
        "ALERT",
        "CD-108",
    ),
    "rf.stroke_fast": (
        RuleStatus.ACTIVE,
        EK4Level.KIRMIZI_K2,
        RedFlagRoute.EMERGENCY_NOW,
        "ALERT",
        "CD-109",
    ),
    "rf.dyspnoea_rest": (
        RuleStatus.DRAFT_NEEDS_SOURCE,
        EK4Level.YESIL,
        RedFlagRoute.EXPEDITE,
        None,
        "CD-110",
    ),
    "rf.anaphylaxis": (
        RuleStatus.ACTIVE,
        EK4Level.KIRMIZI_K2,
        RedFlagRoute.EMERGENCY_NOW,
        "ALERT",
        "CD-111",
    ),
    "rf.severe_bleeding": (
        RuleStatus.ACTIVE,
        EK4Level.KIRMIZI_K2,
        RedFlagRoute.EMERGENCY_NOW,
        "ALERT",
        "CD-112",
    ),
    "rf.suicidal_intent": (
        RuleStatus.DRAFT_NEEDS_SOURCE,
        EK4Level.YESIL,
        RedFlagRoute.EXPEDITE,
        None,
        "CD-113",
    ),
    "rf.sepsis_like": (
        RuleStatus.ACTIVE,
        EK4Level.KIRMIZI_K2,
        RedFlagRoute.EMERGENCY_NOW,
        "ALERT",
        "CD-114",
    ),
    "rf.thunderclap_headache": (
        RuleStatus.ACTIVE,
        EK4Level.KIRMIZI_K2,
        RedFlagRoute.EMERGENCY_NOW,
        "ALERT",
        "CD-115",
    ),
    "rf.pregnancy_bleeding_pain": (
        RuleStatus.DRAFT_NEEDS_SOURCE,
        EK4Level.YESIL,
        RedFlagRoute.EXPEDITE,
        None,
        "CD-116",
    ),
    "rf.fever_high_persistent": (
        RuleStatus.ACTIVE,
        EK4Level.SARI_K1,
        RedFlagRoute.SAME_DAY_ACIL,
        None,
        "CD-117",
    ),
    "rf.weight_loss_unintentional": (
        RuleStatus.ACTIVE,
        EK4Level.SARI_K2,
        RedFlagRoute.EXPEDITE,
        None,
        "CD-118",
    ),
    "rf.new_neuro_deficit_subacute": (
        RuleStatus.DRAFT_NEEDS_SOURCE,
        EK4Level.YESIL,
        RedFlagRoute.EXPEDITE,
        None,
        "CD-119",
    ),
    "rf.suicidal_ideation_passive": (
        RuleStatus.DRAFT_NEEDS_SOURCE,
        EK4Level.YESIL,
        RedFlagRoute.EXPEDITE,
        None,
        "CD-120",
    ),
}
ACTIVE = tuple(f for f, row in EXPECTED.items() if row[0] is RuleStatus.ACTIVE)
DRAFT = tuple(f for f, row in EXPECTED.items() if row[0] is RuleStatus.DRAFT_NEEDS_SOURCE)
SUICIDE_FAMILIES = ("rf.suicidal_intent", "rf.suicidal_ideation_passive")
NEW_SNAPSHOTS = ("NICE-NG128", "NICE-CG150", "RCUK-ANAPHYLAXIS-2021")


@pytest.fixture(scope="module")
def pack() -> ProtocolPack:
    return load_pack(BASE_INTAKE)


def _rules(pack: ProtocolPack) -> dict[str, RedFlagRule]:
    return {rule.id: rule for rule in pack.red_flags}


def _declared(pack: ProtocolPack) -> dict[str, SlotType]:
    """Both spellings a rule may use for a slot: ``section.slot`` and bare ``slot``."""
    declared: dict[str, SlotType] = {}
    for section_id, section in pack.sections.items():
        for key, slot in section.slots.items():
            declared[f"{section_id}.{key}"] = slot.type
            declared[key] = slot.type
    return declared


# --- the census ---------------------------------------------------------------


def test_eight_families_are_active_and_five_stay_draft(pack: ProtocolPack) -> None:
    rules = _rules(pack)
    assert set(rules) == set(EXPECTED)
    for family, (status, level, route, register, _) in EXPECTED.items():
        rule = rules[family]
        assert rule.status is status, family
        assert rule.level is level, family
        assert rule.route is route, family
        assert (rule.register.value if rule.register else None) == register, family
    assert len(ACTIVE) == 8 and len(DRAFT) == 5


def test_every_draft_keeps_the_sanctioned_pending_trigger_and_names_its_decision(
    pack: ProtocolPack,
) -> None:
    rules = _rules(pack)
    for family in DRAFT:
        rule = rules[family]
        assert PLACEHOLDER_SIGNOFF_RE.fullmatch(rule.when) is not None, family
        assert rule.source is None, family
        assert EXPECTED[family][4] in (rule.source_gap or ""), family


def test_the_suicide_families_stay_blocked_on_the_licence_and_the_escalation_policy(
    pack: ProtocolPack,
) -> None:
    """C-SSRS is licence-BLOCKED (HB-L2) and the 04 §4.2 policy does not exist
    (HB-C8): the brief says keep them blocked and do not write them."""
    rules = _rules(pack)
    for family in SUICIDE_FAMILIES:
        rule = rules[family]
        assert rule.status is RuleStatus.DRAFT_NEEDS_SOURCE
        gap = rule.source_gap or ""
        assert "HB-L2" in gap and "HB-C8" in gap, family
        assert "C-SSRS" not in rule.when


def test_no_active_rule_carries_a_pending_value(pack: ProtocolPack) -> None:
    rules = _rules(pack)
    for family in ACTIVE:
        rule = rules[family]
        assert "TODO" not in rule.model_dump_json(), family
        assert rule.source_gap is None, family


# --- provenance ---------------------------------------------------------------


def test_every_active_rule_quotes_a_committed_snapshot_verbatim(pack: ProtocolPack) -> None:
    rules = _rules(pack)
    for family in ACTIVE:
        source = rules[family].source
        assert source is not None and source.quote_snapshot is not None, family
        problem = source_snapshot_problem(
            quote_snapshot=source.quote_snapshot,
            guideline_id=source.guideline_id,
            quote=source.quote,
            url=source.url,
            retrieved_on=source.retrieved_on,
            version_or_date=source.version_or_date,
        )
        assert problem is None, f"{family}: {problem}"


@pytest.mark.parametrize("guideline_id", NEW_SNAPSHOTS)
def test_each_new_snapshot_carries_its_header_and_the_fetched_sha256(guideline_id: str) -> None:
    text = (SOURCES / f"{guideline_id}.txt").read_text(encoding="utf-8")
    header, _, body = text.partition("\n---\n")
    for key in ("guideline_id", "title", "version_or_date", "url", "retrieved_on", "retrieval"):
        assert f"# {key}: " in header, (guideline_id, key)
    assert f"# guideline_id: {guideline_id}" in header
    assert "# retrieved_on: 2026-11-18" in header
    assert "sha256 " in header
    assert body.strip()


def _write_pack_with_quote(tmp_path: Path, family: str, quote: str) -> Path:
    raw: dict[str, Any] = yaml.safe_load(BASE_INTAKE.read_text(encoding="utf-8"))
    for flag in raw["red_flags"]:
        if flag["id"] == family:
            flag["source"]["quote"] = quote
    path = tmp_path / "intake.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_the_loader_refuses_a_chain_pack_rule_whose_quote_is_not_verbatim(
    pack: ProtocolPack, tmp_path: Path
) -> None:
    """dsl.SourceBlock promised it: when a chain pack's rule cites a snapshot, its
    loader runs the same check as the life-threat loader. Near miss: one word."""
    quote = _rules(pack)["rf.stroke_fast"].source.quote  # type: ignore[union-attr]
    assert load_pack(_write_pack_with_quote(tmp_path, "rf.stroke_fast", quote))
    with pytest.raises(PackSchemaError, match=r"rf\.stroke_fast"):
        load_pack(_write_pack_with_quote(tmp_path, "rf.stroke_fast", quote + " ve afazi"))


def test_a_committed_pack_rule_must_name_its_snapshot_and_a_test_pack_need_not(
    tmp_path: Path,
) -> None:
    """Under packages/protocols/ the snapshot is mandatory. A SENTETİK test pack
    elsewhere may cite a source without one (the near miss): the fixtures that
    exercise the compiler do."""
    raw: dict[str, Any] = yaml.safe_load(BASE_INTAKE.read_text(encoding="utf-8"))
    for flag in raw["red_flags"]:
        if flag["id"] == "rf.sepsis_like":
            del flag["source"]["quote_snapshot"]
    path = tmp_path / "intake.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    unsnapshotted = load_pack(path)  # a test pack: admitted
    with pytest.raises(PackSchemaError, match=r"rf\.sepsis_like: a cited source names"):
        check_rule_sources(path, unsnapshotted, committed=True)


@pytest.mark.parametrize("family", list(EXPECTED))
def test_each_family_has_its_register_entry_and_human_twin(family: str) -> None:
    decision_id = EXPECTED[family][4]
    decision = load_decision(DECISIONS / f"{decision_id}.yaml")
    assert (DOCS_DECISIONS / f"{decision_id}.md").is_file()
    assert decision.value["rule"] == family
    expected = (
        DecisionStatus.ACTIVE
        if EXPECTED[family][0] is RuleStatus.ACTIVE
        else DecisionStatus.DRAFT_NEEDS_SOURCE
    )
    assert decision.status is expected, family
    assert decision.verifier.role is not None and "not independent" in decision.verifier.role


# --- invariant 21 and invariant 22 on the KIRMIZI rules ------------------------


def test_every_kirmizi_rule_resolves_for_all_three_locations_without_112_on_site(
    pack: ProtocolPack,
) -> None:
    for rule in pack.red_flags:
        if not rule.level.is_red:
            continue
        assert rule.register is not None and rule.action is not None, rule.id
        assert rule.notify_clinic.value == "always", rule.id
        assert rule.action.remote.show_112 is True, rule.id
        assert rule.action.on_site.show_112 is False, rule.id
        assert rule.action.on_site.notify_staff_immediate is True, rule.id
        assert rule.action.unknown.ask_one_tr["tr"] == "Şu anda hastanede misiniz?", rule.id
        remote = rule.action.remote.action_tr
        assert remote is not None and "yüz on iki" in remote["tr"], rule.id
        on_site = rule.action.on_site.action_tr
        assert on_site is not None and "yüz on iki" not in on_site["tr"], rule.id


def _action_texts(rule: RedFlagRule) -> list[str]:
    texts: list[str] = []
    if rule.action is None:
        return texts
    for branch in (rule.action.remote, rule.action.on_site):
        for field in (branch.action_tr, branch.why_tr):
            if field is not None:
                texts.extend(field.values())
        for items in branch.do_nots_tr.values():
            texts.extend(items)
    texts.extend(rule.action.unknown.ask_one_tr.values())
    return texts


def test_no_action_script_carries_a_digit(pack: ProtocolPack) -> None:
    """Invariant 22: every number in a script is spelled out in Turkish."""
    for rule in pack.red_flags:
        for text in _action_texts(rule):
            assert not any(ch.isdigit() for ch in text), f"{rule.id}: {text!r}"


def test_red_scripts_use_the_bare_imperative_plural_never_sen(pack: ProtocolPack) -> None:
    for rule in pack.red_flags:
        for text in _action_texts(rule):
            words = {"".join(c for c in w.casefold() if c.isalpha()) for w in text.split()}
            assert not words & {"sen", "sana", "seni", "senin"}, f"{rule.id}: {text!r}"


# --- reachability -------------------------------------------------------------


def test_every_active_trigger_reads_declared_slots_and_anchors_on_a_date(
    pack: ProtocolPack,
) -> None:
    declared = _declared(pack)
    rules = _rules(pack)
    for family in ACTIVE:
        rule = rules[family]
        reads = referenced_slots(parse_when(rule.when))
        assert reads, family
        assert reads <= set(declared), (family, reads - set(declared))
        assert declared[rule.tense_anchor] is SlotType.DATE, family


def test_every_new_probe_is_askable_with_one_question(pack: ProtocolPack) -> None:
    rules = _rules(pack)
    declared_slots = {
        f"{section_id}.{key}": slot
        for section_id, section in pack.sections.items()
        for key, slot in section.slots.items()
    }
    for family in ACTIVE:
        for ref in referenced_slots(parse_when(rules[family].when)):
            slot = declared_slots[ref]
            assert slot.ask_tr is not None, ref
            assert slot.ask_tr["tr"].count("?") == 1, ref
            assert slot.follow_up_tr is not None, ref


# --- invariant 7 and D23 ------------------------------------------------------


def test_the_life_threat_set_is_byte_identical_so_the_d23_signature_stands() -> None:
    signed = json.loads(RED_SIGNATURE.read_text(encoding="utf-8"))
    digest = hashlib.sha256(LIFE_THREAT.read_bytes()).hexdigest()
    assert digest == signed["payload"]["life_threat"]["sha256"]


def test_no_family_sits_below_the_floor_it_had(pack: ProtocolPack) -> None:
    """Monotonic (invariant 7): every family started at the YESIL floor, so a
    written rule may only stay there or rise."""
    for rule in pack.red_flags:
        assert rule.level.severity >= EK4Level.YESIL.severity


def test_the_anaphylaxis_probe_asks_for_an_airway_or_breathing_problem_not_swelling_alone(
    pack: ProtocolPack,
) -> None:
    """Verifier finding (CD-111): RCUK 3.1 does not count angioedema without an
    airway, breathing or circulation problem. Near miss: a probe that fired on
    tongue swelling alone, as the first draft did."""
    probe = pack.sections["red_flags"].slots["rf_anaphylaxis"].ask_tr
    assert probe is not None
    text = probe["tr"]
    assert "nefes almada güçlük" in text
    assert "yutkunmanızı zorlaştıran bir şişlik" in text
    assert "dil ya da boğaz şişliği," not in text
