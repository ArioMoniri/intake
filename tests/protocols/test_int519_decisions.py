"""INT-519 — the D18 decisions on the review-queue gates and the onset anchor are data.

GitHub #885. INT-441 found three review-queue cluster gates comparing a code slot
against a string no authored answer holds, and the INT-522 and INT-540 reviews left
the onset anchor's open questions to the D18 lane (files/00_STATE.md D18: agent
author plus independent verifier, simulated-patient stress testing only). This
suite pins that what was decided is machine-readable and internally consistent;
it does not restate a clinical value the decisions do not hold:

1. **CD-112** decides one authored literal per gate. Each is a member of the
   slot's committed value set, and the pre-fix literal it replaces is not (the
   near miss is the INT-441 defect itself). Each pack gate is today's spelling or
   the decided one, never a third. The immunosuppression hedge mapping records an
   authored choice that is not the plain negative.
2. **CD-04 round 3** splits the tense anchor's follow-up bound by cause, keeping
   the decision-wide "once" the runtime reads today.
3. **CD-05 round 3** names every cause its more-acute resolution covers, decides
   the never-asked anchor and the straddle tie-break without making either less
   acute than an answer that fits no choice, and leaves the twelve-to-seventy-two
   hour band open in the invariant-17 form.
4. **CD-100 round 4** re-reads T1 on the corrected premise: the population guard
   is an extra OR term on base's three-answer gate, so it can only add askers.

Every nested ``sources`` id in an INT-519 entry is one of the decision's own
top-level sources, so no entry cites a guideline the register did not check.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.clinical_decisions import (
    CkmSource,
    ClinicalDecision,
    DecisionStatus,
    GuidelineSource,
    load_register,
)
from protocols.validator import PLACEHOLDER_SIGNOFF_RE
from protocols.valuesets import load_committed_valuesets

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_INTAKE = REPO_ROOT / "packages" / "protocols" / "base" / "intake.yaml"
ISSUE = "INT-519"
#: The causes the runtime records for an UNCLEAR anchor (INT-540 UnclearCause).
ANCHOR_CAUSES = frozenset({"hedge", "no_choice", "session_closed"})
_GATE = re.compile(r"^(?P<slot>[a-z_.]+) (?P<op>==|!=) '(?P<literal>[^']+)'$")


def _decision(decision_id: str) -> ClinicalDecision:
    return load_register()[decision_id]


def _source_ids(decision: ClinicalDecision) -> frozenset[str]:
    ids: set[str] = set()
    for source in decision.sources:
        if isinstance(source, GuidelineSource):
            ids.add(source.guideline_id)
        elif isinstance(source, CkmSource):
            ids.add(source.archetype_id)
    return frozenset(ids)


def _nested_source_ids(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, child in node.items():
            if key == "sources" and isinstance(child, list):
                found.extend(item for item in child if isinstance(item, str))
            else:
                found.extend(_nested_source_ids(child))
    elif isinstance(node, list):
        for child in node:
            found.extend(_nested_source_ids(child))
    return found


def _int519_amendments(decision: ClinicalDecision) -> list[dict[str, Any]]:
    return [a for a in decision.value.get("amendments", ()) if a.get("issue", "").startswith(ISSUE)]


def _gate(text: str) -> tuple[str, str, str]:
    match = _GATE.match(text)
    assert match is not None, text
    return match.group("slot"), match.group("op"), match.group("literal")


def _slot_ask_if(pack_file: str, slot_ref: str) -> object:
    document = yaml.safe_load((REPO_ROOT / pack_file).read_text(encoding="utf-8"))
    section, key = slot_ref.split(".")
    return document["sections"][section]["slots"][key].get("ask_if")


# --- 1 · CD-112: one authored literal per gate ----------------------------------------


def test_cd112_decides_the_three_issue_items() -> None:
    cd112 = _decision("CD-112")
    assert cd112.status is DecisionStatus.ACTIVE
    assert [item["item"] for item in cd112.value["gates"]] == [1, 2, 3]


@pytest.mark.parametrize("index", [0, 1, 2])
def test_each_decided_literal_is_a_member_and_the_replaced_one_is_not(index: int) -> None:
    item = _decision("CD-112").value["gates"][index]
    members = load_committed_valuesets().members(item["valueset"])
    assert members is not None, item["valueset"]
    slot, _, decided = _gate(item["gate_decided"])
    assert decided == item["literal"] and decided in members
    today_slot, _, replaced = _gate(item["gate_today"])
    assert today_slot == slot
    # the near miss is the INT-441 defect: a literal no authored answer holds
    assert replaced not in members


@pytest.mark.parametrize("index", [0, 1, 2])
def test_each_pack_gate_is_todays_spelling_or_the_decided_one_never_a_third(index: int) -> None:
    item = _decision("CD-112").value["gates"][index]
    allowed = {item["gate_today"], item["gate_decided"]}
    if item.get("encoding_once_applied", {}).get("gate") == "none":
        allowed.add(None)
    for slot in item["slots"]:
        assert _slot_ask_if(item["file"], slot) in allowed, (item["pack"], slot)


def test_item1_applies_only_once_the_self_proxy_mechanism_lands() -> None:
    item = _decision("CD-112").value["gates"][0]
    assert item["reading"] == "self_report_only"
    assert "#833" in item["applies_when"]
    once = item["encoding_once_applied"]
    assert once == {"gate": "none", "proxy": {"skip": True}}


def test_item2_hedges_on_immunosuppression_record_an_authored_choice_not_the_negative() -> None:
    mapping = _decision("CD-112").value["gates"][1]["hedge_mapping"]
    members = load_committed_valuesets().members("vs.immunosuppression")
    assert members is not None
    assert mapping["records_choice"] in members
    assert mapping["plain_negative_only"] in members
    assert mapping["records_choice"] != mapping["plain_negative_only"]
    assert "UNCLEAR" in mapping["never"] and mapping["plain_negative_only"] in mapping["never"]


def test_item3_reaches_the_five_cd100_t4b_items_with_the_same_literal() -> None:
    item = _decision("CD-112").value["gates"][2]
    assert item["also_applies_to"]["record"] == "CD-100"
    assert item["also_applies_to"]["gate"] == item["gate_decided"]
    assert len(item["also_applies_to"]["slots"]) == 5


# --- 2 · CD-04 round 3: the anchor's follow-up bound, by cause -----------------------


def test_cd04_keeps_its_once_and_splits_the_anchor_bound_by_cause() -> None:
    cd04 = _decision("CD-04")
    assert "triggers the slot's follow_up_tr once" in cd04.decision
    assert cd04.value["unclear_follow_up_tr_asks"] == 1
    by_cause = cd04.value["tense_anchor_follow_up_tr_asks"]
    assert set(by_cause) == {"hedge", "no_choice"} <= ANCHOR_CAUSES
    assert by_cause == {"hedge": 0, "no_choice": 1}
    assert all(isinstance(n, int) and not isinstance(n, bool) for n in by_cause.values())


# --- 3 · CD-05 round 3: every cause, the close, the straddle --------------------------


def test_cd05_names_every_cause_its_more_acute_resolution_covers() -> None:
    unresolved = _decision("CD-05").value["unresolved_answer"]
    assert set(unresolved["causes"]) == ANCHOR_CAUSES
    assert (unresolved["answer_state"], unresolved["resolves_to"]) == ("UNCLEAR", "reference_day")


def test_cd05_never_asked_and_straddle_are_never_less_acute_than_no_choice() -> None:
    value = _decision("CD-05").value
    unresolved = value["unresolved_answer"]["resolves_to"]
    never_asked = value["never_asked_at_close"]
    assert never_asked["status"] == DecisionStatus.ACTIVE.value
    assert never_asked["evaluated_as"] == unresolved
    assert never_asked["answer_state"] == "NOT_ASKED"  # never an elicited answer
    straddle = value["straddle"]
    assert (straddle["tie_break"], straddle["fallback"]) == ("more_acute", "unresolved_answer")
    assert straddle["follow_up_cause"] == "no_choice"


def test_cd05_twelve_to_seventy_two_hours_stays_open_and_says_what_closes_it() -> None:
    [band] = [
        choice
        for choice in _decision("CD-05").value["choices"]
        if choice["status"] == DecisionStatus.DRAFT_NEEDS_SOURCE.value
    ]
    assert PLACEHOLDER_SIGNOFF_RE.fullmatch(band["resolves_to"])
    assert band["while_draft"]["resolves_to"] == "reference_day"
    assert len(band["final_resolution_needs"]) >= 3


# --- 4 · CD-100 round 4: T1 on the corrected premise ----------------------------------


def test_cd100_t1_guard_is_an_extra_or_term_on_bases_three_answer_gate() -> None:
    [amendment] = [a for a in _int519_amendments(_decision("CD-100")) if a["ref"] == "T1"]
    base = yaml.safe_load(BASE_INTAKE.read_text(encoding="utf-8"))
    three_answer = base["sections"]["pmh_fh_sh"]["slots"]["lmp_date"]["ask_if"]
    shape = amendment["gate_shape"]
    assert shape.startswith(three_answer + " || (")
    # near miss: the narrowed spellings a guard must never ride on
    assert "!= 'hayır'" not in shape and "!= 'hayir'" not in shape
    assert "#804" in amendment["applies_when"]


# --- every INT-519 entry cites only what its decision's register entry checked ---------


@pytest.mark.parametrize("decision_id", ["CD-04", "CD-05", "CD-100", "CD-112"])
def test_int519_entries_cite_only_their_decisions_checked_sources(decision_id: str) -> None:
    decision = _decision(decision_id)
    entries: object = (
        decision.value["gates"] if decision_id == "CD-112" else _int519_amendments(decision)
    )
    assert entries, decision_id
    cited = _nested_source_ids(entries)
    assert cited, decision_id
    assert set(cited) <= _source_ids(decision), decision_id
