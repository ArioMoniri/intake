"""INT-554 — the D18 decisions on CD-08's clinic items are data.

GitHub #938. The #931/#932 clinical review (items D1 to D7) and the #935
clinical review (items D8 to D10) left ten questions on the CD-08 clinic
items, CD-04, CD-01 and CD-100 T4(c) to the D18 lane (files/00_STATE.md D18:
agent author plus independent verifier, simulated-patient stress testing
only). This suite pins that what was decided is machine-readable and agrees
with the records and the build it touches; it states no clinical value the
decisions do not hold:

1. **CD-08 round 4.** The prose says the arms item *can* leave both arms
   Unknown (D1). Acknowledgement never closes an item; only a recorded action
   or plan does, and a redirect re-addresses without closing (D3). The SLA,
   out-of-hours cover and escalation stay the invariant-17 literal and are
   named tenant-agreed values; the build still reads no SLA (D4). The tenant
   Safety queue is the booked clinic's inbox only under a stated condition,
   and ``tenant_clinical_responsible`` is not the recipient role (D5).
2. **CD-04 round 4.** At close, a non-anchor chest-pain slot asked and never
   answered is UNCLEAR with CD-05's ``session_closed`` label, and one never
   asked behind an open screen stays NOT_ASKED; both raise the arms item and
   neither changes triage (D2). CD-04's "once" governs every non-anchor slot
   its trigger names, and the anchor keeps its per-cause bound (D6).
3. **CD-01 round 4.** The subject role is bound before any chest-pain slot is
   asked; an answer given before a proxy binding is invalidated without
   lowering a level; the subject's age binds from the subject's record only
   (D7).
4. **CD-100 round 5 and CD-112 round 2.** T4(c)'s named hedges are per-slot
   surfaces CD-04 does not hold (D8); a hedge beside a choice records the
   mapped choice and keeps the choice unbound, and a rule reads pregnancy as
   ``!= 'hayır'`` (D9); T4 (a), (b) and (c) apply as one change (D10).

Every nested ``sources`` id in an INT-554 entry is one of the decision's own
top-level sources, so no entry cites a guideline the register did not check.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.answer_states import utterance_tokens
from protocols.clinic_items import SubjectAge, load_clinic_item_rules
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
ISSUE = "INT-554"
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


def _int554_amendments(decision: ClinicalDecision) -> list[dict[str, Any]]:
    return [a for a in decision.value.get("amendments", ()) if a.get("issue", "").startswith(ISSUE)]


def _item(decision_id: str, item: str) -> dict[str, Any]:
    found = [
        entry
        for amendment in _int554_amendments(_decision(decision_id))
        for entry in amendment.get("items", ())
        if entry.get("item") == item
    ]
    assert len(found) == 1, (decision_id, item)
    return found[0]


def _at(node: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        node = node[part]
    return node


def _gate(text: str) -> tuple[str, str, str]:
    match = _GATE.match(text)
    assert match is not None, text
    return match.group("slot"), match.group("op"), match.group("literal")


def _anchors() -> frozenset[str]:
    return frozenset(
        anchor["anchor"]
        for anchor in _decision("CD-05").value["anchors"]
        if anchor["status"] == DecisionStatus.ACTIVE.value
    )


def _arms_slots() -> frozenset[str]:
    return frozenset(_decision("CD-04").value["unresolved_after_follow_up"]["applies_to"])


def _cd01_ask_if() -> dict[str, object]:
    sections = _decision("CD-01").value["sections"]
    return {
        f"{section}.{slot}": spec.get("ask_if")
        for section, slots in sections.items()
        for slot, spec in slots.items()
    }


# --- 1 · CD-08 round 4 ---------------------------------------------------------------


def test_d1_cd08_says_the_arms_item_can_leave_both_arms_unknown() -> None:
    cd08 = _decision("CD-08")
    assert "which can leave both chest-pain arms Unknown" in cd08.decision
    # near miss: the narrower reading the build never followed is gone
    assert "that leaves both chest-pain arms Unknown" not in cd08.decision
    assert "which can leave" in cd08.value["item_kind_notes"]["chest_pain_arms_unresolved"]
    d1 = _item("CD-08", "D1")
    assert "that leaves both chest-pain arms Unknown" in d1["was"]
    assert d1["value_changed"] is False


def test_d3_acknowledgement_never_closes_an_item_and_only_an_outcome_does() -> None:
    cd08 = _decision("CD-08")
    failure = cd08.value["failure_path"]
    outcome = failure["outcome"]
    assert cd08.value_status["failure_path.outcome"] is DecisionStatus.ACTIVE
    assert outcome["acknowledgement_closes"] is False
    closes = set(outcome["closes_on"])
    assert closes and closes < set(outcome["codes"])
    # near miss: a redirect is a code, but it re-addresses the item and leaves it open
    assert outcome["redirect_code"] in outcome["codes"]
    assert outcome["redirect_code"] not in closes
    assert outcome["redirect_closes"] is False
    for constraint in ("never_auto_cleared", "closes_only_on_recorded_clinician_outcome"):
        assert constraint in failure["constraints"]


def test_d4_sla_cover_and_escalation_stay_open_as_tenant_agreed_values() -> None:
    cd08 = _decision("CD-08")
    tenant = cd08.value["tenant_agreed"]
    keys = set(tenant["keys"])
    assert keys == {
        "sla",
        "out_of_hours.coverage",
        "failure_path.escalation_role",
        "failure_path.escalation_after",
    }
    for key in keys:
        assert cd08.value_status[key] is DecisionStatus.DRAFT_NEEDS_SOURCE, key
        assert PLACEHOLDER_SIGNOFF_RE.fullmatch(_at(cd08.value, key).strip()), key
    # the nearest published interval is on the record and not adopted
    assert tenant["nearest_published_interval"]["adopted"] is False
    assert "out_of_hours_contact_named_by_tenant" in cd08.value["out_of_hours"]["constraints"]
    # the build still states no SLA
    assert load_clinic_item_rules().sla_decided is False


def test_d5_the_tenant_queue_and_role_satisfy_cd08_only_under_the_stated_conditions() -> None:
    cd08 = _decision("CD-08")
    conformance = cd08.value["built_route_conformance"]
    assert cd08.value_status["built_route_conformance"] is DecisionStatus.ACTIVE
    queue = conformance["tenant_safety_queue"]
    assert queue["is_the_booked_clinics_inbox"] == "only_when_condition_holds"
    assert queue["while_condition_unmet"] == "interim_delivery_path"
    responsible = conformance["tenant_clinical_responsible"]
    assert responsible["is_the_recipient_role"] is False
    # the recipient role itself is unchanged
    assert cd08.value["recipient_role"]["role_id"] == "tenant_clinic_triage_trained_clinician"
    assert cd08.value["recipient_role"]["role_id"] in responsible["may_record_outcome_when"]
    report = conformance["inbox_not_ready_report"]
    assert report["required"] is True
    # every open tenant-agreed value is a reason the inbox reports not ready
    reasons = set(report["not_ready_while_unset"])
    assert set(cd08.value["tenant_agreed"]["keys"]) <= reasons
    assert "booked_clinic_routing" in reasons and "out_of_hours_contact" in reasons


# --- 2 · CD-04 round 4 ---------------------------------------------------------------


def test_d2_an_asked_unanswered_non_anchor_slot_raises_the_arms_item_at_close() -> None:
    value = _decision("CD-04").value
    close = value["unresolved_at_close"]
    assert set(close["slots"]) == _arms_slots() - _anchors()
    asked = close["asked_unanswered"]
    assert (asked["state_at_close"], asked["records"]) == ("ASKED_PENDING", "UNCLEAR")
    cd05_labels = _decision("CD-05").value["unresolved_answer"]["record_label_by_cause"]
    assert asked["label"] == cd05_labels["session_closed"]
    # an UNCLEAR whose follow-up was never asked is closed the same way: the close spends it
    unspent = close["unclear_bound_unspent"]
    assert (unspent["state_at_close"], unspent["records"]) == ("UNCLEAR", "UNCLEAR")
    assert unspent["label"] == asked["label"]
    arms = value["unresolved_after_follow_up"]
    assert (close["kind"], close["decision_ref"]) == (arms["kind"], arms["decision_ref"])
    assert close["once_per_session"] is True
    # the close tells the clinic; it never decides triage
    assert (close["evaluates_as"], close["changes_triage"]) == ("unknown", False)


def test_d2_a_never_asked_slot_raises_it_only_behind_an_open_screen() -> None:
    close = _decision("CD-04").value["unresolved_at_close"]
    never = close["never_asked_gate_open"]
    assert never["records"] == "NOT_ASKED"
    gated = {ref for ref, ask_if in _cd01_ask_if().items() if ask_if == never["gate"]}
    assert set(never["slots"]) == gated - _anchors()
    # near miss: the screen itself has no gate and is not in the never-asked list
    screens = {ref for ref, ask_if in _cd01_ask_if().items() if ask_if is None}
    assert len(screens) == 1 and not screens & set(never["slots"])
    assert never["label"] == _decision("CD-05").value["never_asked_at_close"]["record_label"]


def test_d6_once_governs_every_non_anchor_slot_and_the_anchor_keeps_its_split() -> None:
    value = _decision("CD-04").value
    scope = value["follow_up_bound_scope"]
    assert value["unclear_follow_up_tr_asks"] == 1
    assert set(scope["once_slots"]) == _arms_slots() - _anchors()
    assert scope["tense_anchors_read"] == "tense_anchor_follow_up_tr_asks"
    assert value["tense_anchor_follow_up_tr_asks"] == {"hedge": 0, "no_choice": 1}
    assert load_clinic_item_rules().arms.follow_up_asks == 1


# --- 3 · CD-01 round 4 ---------------------------------------------------------------


def test_d7_the_subject_role_is_bound_before_any_chest_pain_slot() -> None:
    cd01 = _decision("CD-01")
    first = _item("CD-01", "D7")["subject_role_first"]
    assert first["ask_ahead_before_bound"] is False
    # the gatekeeper is the slot CD-01's stop-gap and base's screen both read
    assert first["gatekeeper"] in cd01.value["proxy_unasked_inbox_item"]["raised_when"]
    base = yaml.safe_load(BASE_INTAKE.read_text(encoding="utf-8"))
    skip_if = base["sections"]["chest_pain"]["slots"]["present"]["skip_if"]
    assert _gate(skip_if)[0] == first["gatekeeper"]
    assert set(first["precedes"]) == set(_cd01_ask_if())


def test_d7_an_answer_before_the_proxy_binding_is_not_the_patients_and_never_lowers() -> None:
    cd01 = _decision("CD-01")
    late = _item("CD-01", "D7")["answered_before_proxy_binding"]
    members = load_committed_valuesets().members("vs.subject_role")
    assert members is not None and late["proxy_choice"] in members
    assert (late["answers"], late["slots_read"]) == ("invalidated", "NOT_ASKED")
    assert late["level_already_determined"] == "never_lowered"
    assert late["raises"] == cd01.value["proxy_unasked_inbox_item"]["kind"]


def test_d7_the_subject_age_binds_from_the_subjects_record_only() -> None:
    age = _item("CD-01", "D7")["subject_age"]
    assert set(age["never_from"]) == {"slot_answer", "speaker_identity"}
    assert age["absent_or_unverified"] == SubjectAge.UNKNOWN.value
    assert age["while_band_bound_unstated"] == SubjectAge.UNKNOWN.value
    proxy = load_clinic_item_rules().proxy
    assert proxy.raised(screen_skipped=True, slots_unasked=True, subject_age=SubjectAge.UNKNOWN)
    # near miss: a subject known to be outside the band is never raised
    assert not proxy.raised(
        screen_skipped=True, slots_unasked=True, subject_age=SubjectAge.OUTSIDE_ADULT_BAND
    )


# --- 4 · CD-100 round 5 and CD-112 round 2 ------------------------------------------


def _surfaces() -> dict[str, Any]:
    return dict(_item("CD-100", "D8")["hedge_surfaces_tr"])


def test_d8_t4c_named_hedges_are_per_slot_surfaces_cd04_does_not_hold() -> None:
    surfaces = _surfaces()
    assert surfaces["slot"] == "pmh_fh_sh.pregnancy_status"
    assert tuple(surfaces["surfaces"]) == ("galiba", "olabilir", "bilemiyorum")
    cd04_surfaces = {entry["surface_tr"] for entry in _decision("CD-04").value["entries"]}
    # CD-04's '*' list is not enough: none of the three is on it
    assert not set(surfaces["surfaces"]) & cd04_surfaces
    members = load_committed_valuesets().members("vs.pregnancy_status")
    assert members is not None
    assert surfaces["records_choice"] in members and surfaces["records_choice"] != "hayır"
    # each surface is one of T4 change (c)'s own named examples: a restatement
    [t4] = [item for item in _decision("CD-100").value["items"] if item["ref"] == "T4"]
    for surface in surfaces["surfaces"]:
        assert f'"{surface}"' in t4["change"], surface


def test_d8_the_golden_answer_carries_a_surface_and_its_near_miss_does_not() -> None:
    surfaces = _surfaces()
    golden = _item("CD-100", "D8")["golden"]
    words = set(utterance_tokens(golden["answer"]))
    assert words & set(surfaces["surfaces"])
    assert golden["records"] == surfaces["records_choice"]
    near_miss = golden["near_miss"]
    assert not set(utterance_tokens(near_miss["answer"])) & set(surfaces["surfaces"])
    assert near_miss["records"] == "hayır"
    # whole words only: 'bilmiyorum' is CD-04's own entry and never this surface
    assert "bilmiyorum" not in surfaces["surfaces"]


def test_d9_a_hedge_beside_a_choice_keeps_the_choice_unbound_and_rules_read_not_hayir() -> None:
    d9 = _item("CD-100", "D9")
    beside = d9["hedge_with_choice"]
    assert beside["records_choice"] == _surfaces()["records_choice"]
    assert beside["choice_bound"] is False
    anchor = _decision("CD-04").value["hedge_with_choice_on_tense_anchor"]
    assert beside["choice_recorded_as"] == anchor["choice_recorded_as"]
    slot, op, literal = _gate(d9["rule_reading"])
    assert (slot, op, literal) == ("pregnancy_status", "!=", "hayır")
    # the same reading CD-112 gives immunosuppression
    cd112_rule = _decision("CD-112").value["gates"][1]["hedge_mapping"]["rule_reading"]
    assert "!= 'hayır'" in cd112_rule


def test_d10_t4_a_b_and_c_apply_as_one_change() -> None:
    d10 = _item("CD-100", "D10")
    assert tuple(d10["parts"]) == ("(a)", "(b)", "(c)")
    assert "CD-106" in d10["with"]
    assert d10["status"] == DecisionStatus.ACTIVE.value


def test_d8_d9_cd112_reads_the_same_surfaces_and_keeps_a_hedged_choice_on_immunosuppression() -> (
    None
):
    entry = _item("CD-112", "D8-D9")
    mapping = _decision("CD-112").value["gates"][1]["hedge_mapping"]
    assert entry["slot"] == mapping["slot"]
    assert tuple(entry["surfaces"]) == tuple(_surfaces()["surfaces"])
    assert entry["records_choice"] == mapping["records_choice"]
    assert entry["hedge_with_choice"]["choice_bound"] is False


# --- every INT-554 entry cites only what its decision's register entry checked ---------


@pytest.mark.parametrize("decision_id", ["CD-01", "CD-04", "CD-08", "CD-100", "CD-112"])
def test_int554_entries_cite_only_their_decisions_checked_sources(decision_id: str) -> None:
    decision = _decision(decision_id)
    entries = _int554_amendments(decision)
    assert entries, decision_id
    cited = _nested_source_ids(entries)
    assert cited, decision_id
    assert set(cited) <= _source_ids(decision), decision_id
