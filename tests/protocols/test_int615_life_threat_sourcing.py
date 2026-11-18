"""INT-615: sourcing the draft rules of base.life_threat (owner, 17 Nov 2026).

The owner was told there are fifteen draft red-flag rules. That is the compiler's
count over base.intake with the life-threat set: the life-threat pack holds four
rules, two of them ``draft_needs_source``, and base.intake's ``red_flags`` holds
thirteen draft skeletons, which INT-615 does not author. These tests pin what
INT-615 found and decided (CD-107):

- the paediatric airway trigger set now has a paediatric source, the RCH
  Melbourne CPG, committed verbatim;
- the rule still stays a draft, because no source states its level or its age
  bound unambiguously, and each of those is the invariant-17 literal in CD-107;
- the crisis rule stays a draft, because its lexicon has to be authored by a
  clinician (HB-C17) and its escalation policy does not exist (HB-C8);
- nothing was relaxed (invariant 7): the airway rule keeps its level and every
  trigger.

Every refusal has a near miss that loads.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.clinical_decisions import (
    REGISTER_DIR,
    DecisionRegisterError,
    DecisionStatus,
    load_decision,
    quote_in_snapshot,
    snapshot_body,
    snapshot_header,
)
from protocols.compile.life_threat import load_life_threat_set
from protocols.types import RuleStatus

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
BASE_INTAKE = REPO / "packages" / "protocols" / "base" / "intake.yaml"
RCH = REPO / "packages" / "protocols" / "sources" / "RCH-CPG-AUAO-2021.txt"
EK4 = REPO / "packages" / "protocols" / "sources" / "TR-EK4-2022.txt"
CD107 = REGISTER_DIR / "CD-107.yaml"
AIRWAY = "rf.paediatric_airway_obstruction"
CRISIS = "rf.crisis_disclosure_signposting"


def _rules() -> dict[str, Any]:
    return {entry.rule.id: entry.rule for entry in load_life_threat_set(LIFE_THREAT).rules}


def _raw_rule(rule_id: str) -> dict[str, Any]:
    doc = yaml.safe_load(LIFE_THREAT.read_text(encoding="utf-8"))
    return next(rule for rule in doc["rules"] if rule["id"] == rule_id)


def test_the_pack_holds_two_draft_rules_not_fifteen() -> None:
    rules = _rules()
    drafts = sorted(r for r, rule in rules.items() if rule.status is RuleStatus.DRAFT_NEEDS_SOURCE)
    assert len(rules) == 4
    assert drafts == [CRISIS, AIRWAY]


def test_the_fifteen_are_two_life_threat_drafts_and_thirteen_base_intake_drafts() -> None:
    """The count the owner was given is the compile's: base.intake's red_flags plus this set."""
    intake = yaml.safe_load(BASE_INTAKE.read_text(encoding="utf-8"))
    base_drafts = {
        flag["id"] for flag in intake["red_flags"] if flag["status"] == "draft_needs_source"
    }
    decision = load_decision(CD107)
    # CD-107 records the census as INT-615 found it (thirteen skeletons, none
    # authored). INT-619 (owner, 18 Nov 2026; CD-108..CD-120) wrote eight of them,
    # so five remain, each one of the thirteen CD-107 named.
    recorded = set(decision.value["life_threat_census"]["base_intake_drafts"])
    assert len(recorded) == 13
    assert decision.value["life_threat_census"]["base_intake_drafts_authored"] is False
    assert base_drafts < recorded
    assert len(base_drafts) == 5
    life_threat_drafts = {
        r for r, rule in _rules().items() if rule.status is RuleStatus.DRAFT_NEEDS_SOURCE
    }
    assert len(base_drafts | life_threat_drafts) == 7


def test_the_rch_snapshot_is_committed_with_its_header() -> None:
    header = snapshot_header(RCH.read_text(encoding="utf-8"))
    assert header["guideline_id"] == "RCH-CPG-AUAO-2021"
    assert header["retrieved_on"] == "2026-11-17"
    assert header["url"].startswith("https://www.rch.org.au/clinicalguide/")
    assert "March 2021" in header["version_or_date"]


@pytest.mark.parametrize(
    "quote",
    [
        "Stridor",
        "Sniffing or tripod position",
        "Dysphagia and drooling",
        "Hot potato/muffled voice",
        "Pooling of secretions, drooling",
        "Allow children with acute upper airway obstruction to adopt a position of their "
        "choice and avoid causing distress",
    ],
)
def test_every_airway_trigger_has_a_verbatim_paediatric_quote(quote: str) -> None:
    assert quote_in_snapshot(quote, snapshot_body(RCH.read_text(encoding="utf-8")))


def test_a_trigger_the_source_does_not_print_is_not_found() -> None:
    """Near miss for the trigger quotes: an adult-sounding paraphrase is absent."""
    body = snapshot_body(RCH.read_text(encoding="utf-8"))
    assert not quote_in_snapshot("Stridor at rest", body)
    assert not quote_in_snapshot("tripod position", body.replace("tripod", "tri-pod"))


def test_ek4_puts_the_named_airway_features_in_kategori_2() -> None:
    """The level conflict CD-107 records, pinned to the snapshot it reads."""
    body = snapshot_body(EK4.read_text(encoding="utf-8"))
    k1 = body.index("Kategori 1: Hayatı tehdit eden")
    k2 = body.index("Kategori 2: Hayatı tehdit etme olasılığı yüksek")
    assert k1 < body.index("* Havayolu tıkanıklığı riski") < k2
    named = body.index("Şiddetli stridor veya yutkunma güçlüğü ile beraber olan havayolu")
    assert named > k2


def test_cd107_loads_and_keeps_level_and_age_band_draft() -> None:
    decision = load_decision(CD107)
    ids = {getattr(source, "guideline_id", None) for source in decision.sources}
    assert {"RCH-CPG-AUAO-2021", "TR-EK4-2022"} <= ids
    assert decision.value_status["trigger_set"] is DecisionStatus.ACTIVE
    for key in ("level", "age_band", "stridor_qualifier", "crisis_rule"):
        assert decision.value_status[key] is DecisionStatus.DRAFT_NEEDS_SOURCE, key


def test_cd107_marking_the_age_band_active_is_refused(tmp_path: Path) -> None:
    """Near miss for the load above: the same entry, the unsourced key flipped active."""
    raw = yaml.safe_load(CD107.read_text(encoding="utf-8"))
    flipped = copy.deepcopy(raw)
    flipped["value_status"]["age_band"] = "active"
    flipped["value"]["age_band"].pop("status")
    path = tmp_path / "CD-107.yaml"
    path.write_text(yaml.safe_dump(flipped, allow_unicode=True, sort_keys=False), "utf-8")
    with pytest.raises(DecisionRegisterError):
        load_decision(path, repo_root=REPO)


def test_both_draft_rules_stay_draft_and_unserved() -> None:
    rules = _rules()
    for rule_id in (AIRWAY, CRISIS):
        assert rules[rule_id].status is RuleStatus.DRAFT_NEEDS_SOURCE
        assert rules[rule_id].source is None


def test_the_airway_rule_is_not_relaxed() -> None:
    """Invariant 7: the level and every trigger are as authored before INT-615."""
    raw = _raw_rule(AIRWAY)
    assert raw["level"] == "KIRMIZI_K1"
    gate = " ".join(raw["gate"].split())
    for trigger in (
        "airway.stridor_reported == true",
        "airway.drooling_unable_to_swallow == true",
        "airway.tripod_position == true",
        "airway.muffled_voice == true",
    ):
        assert trigger in gate
    assert gate.count("||") == 3
