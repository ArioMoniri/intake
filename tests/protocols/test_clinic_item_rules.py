"""INT-547 — CD-08's chest-pain arms item, read from the decisions.

GitHub #927 (split from #917, finding F3). Verified clinical decisions
(files/00_STATE.md D18) already decide a clinician-only clinic-inbox item, and
nothing built it:

- **CD-04** ``value.unresolved_after_follow_up``: a CD-01 chest-pain slot still
  UNCLEAR after its ``follow_up_tr`` has been asked once raises a CD-08 item of
  kind ``chest_pain_arms_unresolved``, because under three-valued logic it can
  leave both chest-pain arms silent.
- **CD-01** declares the seven chest-pain slots.
- **CD-08** routes the item to the booked clinic's inbox (``clinic_inbox``) and
  leaves its SLA, out-of-hours cover and escalation ``draft_needs_source``.

This suite pins ``protocols.clinic_items`` — the build of that trigger and of
nothing else:

1. Every slot, kind and bound is read from the decisions; the module names no
   slot. The follow-up bound is CD-04's own "once"
   (``unclear_follow_up_tr_asks``), and CD-08's SLA is still open.
2. The arms trigger: UNCLEAR after the follow-up was asked → raised; near
   misses: the same UNCLEAR before its follow-up, a slot resolved by its
   follow-up, a slot still pending, and an UNCLEAR slot CD-04 does not name.
3. Every way a decision could ask for something this build does not do is
   refused when the rules are built.
"""

from __future__ import annotations

import copy
import inspect
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from clinical_schemas.session import AnswerState
from protocols import clinic_items
from protocols.clinic_items import (
    ARMS_DECISION_ID,
    CHEST_PAIN_DECISION_ID,
    CLINIC_INBOX_CHANNEL,
    ROUTING_DECISION_ID,
    ClinicItemError,
    ClinicItemKind,
    ClinicItemRules,
    clinic_item_rules,
    load_clinic_item_rules,
)
from protocols.clinical_decisions import ClinicalDecision, DecisionStatus, load_decision
from protocols.validator import PLACEHOLDER_SIGNOFF_RE

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTER = REPO_ROOT / "packages" / "protocols" / "decisions"

CHARACTER = "chest_pain.character"
RADIATION = "chest_pain.radiation"
ONSET = "chest_pain.onset_at"


def _raw(decision_id: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REGISTER / f"{decision_id}.yaml").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _decision(decision_id: str) -> ClinicalDecision:
    return load_decision(REGISTER / f"{decision_id}.yaml")


def _rules() -> ClinicItemRules:
    return load_clinic_item_rules()


def _seven() -> frozenset[str]:
    sections = _raw("CD-01")["value"]["sections"]
    return frozenset(f"{section}.{slot}" for section, slots in sections.items() for slot in slots)


# --- 1 · read from the decisions, never restated ------------------------------------------


def test_the_three_decisions_are_the_ones_this_build_reads() -> None:
    assert (ARMS_DECISION_ID, CHEST_PAIN_DECISION_ID, ROUTING_DECISION_ID) == (
        "CD-04",
        "CD-01",
        "CD-08",
    )
    rules = _rules()
    assert rules.arms.decision_ids == ("CD-04", "CD-08")
    assert rules.channel == CLINIC_INBOX_CHANNEL == "clinic_inbox"


def test_the_kind_is_the_one_cd04_names_and_cd08_routes() -> None:
    routed = _raw("CD-08")["value"]["applies_to"]
    arms = _raw("CD-04")["value"]["unresolved_after_follow_up"]
    rules = _rules()
    assert rules.arms.kind is ClinicItemKind.CHEST_PAIN_ARMS_UNRESOLVED
    assert rules.arms.kind.value == arms["kind"]
    assert {kind.value for kind in ClinicItemKind} <= set(routed)
    assert arms["decision_ref"] == "CD-08"


def test_the_arms_slots_are_cd04s_and_every_one_is_cd01s() -> None:
    applies = frozenset(_raw("CD-04")["value"]["unresolved_after_follow_up"]["applies_to"])
    rules = _rules()
    assert rules.arms.slots == applies
    assert len(_seven()) == 7
    assert rules.arms.slots == _seven()  # CD-04 names every CD-01 slot


def test_the_follow_up_bound_is_cd04s_once() -> None:
    """CD-04: the item is raised when *"the slot is still UNCLEAR after its
    follow_up_tr has been asked once"* — the same "once" the decision carries
    machine-readable as ``unclear_follow_up_tr_asks``."""
    raw = _raw("CD-04")["value"]
    assert "asked once" in raw["unresolved_after_follow_up"]["trigger"]
    assert raw["unclear_follow_up_tr_asks"] == 1
    assert _rules().arms.follow_up_asks == 1


def test_cd08s_sla_and_escalation_are_still_open_for_the_d18_lane() -> None:
    """CD-08 leaves the SLA, out-of-hours cover and escalation draft. The build
    states none; when the D18 lane decides them this fails and is wired."""
    routing = _decision("CD-08")
    assert routing.status is DecisionStatus.DRAFT_NEEDS_SOURCE
    for key in ("sla", "out_of_hours.coverage"):
        assert routing.value_status[key] is DecisionStatus.DRAFT_NEEDS_SOURCE
    node: Any = routing.value
    assert PLACEHOLDER_SIGNOFF_RE.fullmatch(node["sla"].strip()) is not None
    for key in ("escalation_role", "escalation_after"):
        assert PLACEHOLDER_SIGNOFF_RE.fullmatch(node["failure_path"][key].strip()) is not None
    assert _rules().sla_decided is False


def test_the_module_names_no_slot_of_the_decisions() -> None:
    source = inspect.getsource(clinic_items)
    for ref in _seven():
        assert ref not in source


def test_the_rules_carry_no_level_priority_or_register() -> None:
    """Invariant 1: a clinic item is not a triage outcome. The rules have no
    field a queue could read as a level, a register or a priority."""
    rules = _rules()
    for part in (rules, rules.arms):
        names = set(vars(part))
        assert not names & {"level", "priority", "register", "location", "triage_update"}


# --- 2 · the arms trigger -------------------------------------------------------------------


def _states(**overrides: AnswerState) -> dict[str, AnswerState]:
    states = dict.fromkeys(_seven(), AnswerState.ASKED_PRESENT)
    states.update({key.replace("__", "."): value for key, value in overrides.items()})
    return states


def test_a_cd04_slot_unclear_after_its_follow_up_is_unresolved() -> None:
    states = _states(chest_pain__character=AnswerState.UNCLEAR)
    assert _rules().arms.unresolved(states, {CHARACTER: 1}) == (CHARACTER,)


def test_more_follow_ups_than_once_still_raise() -> None:
    """The runtime still gives a non-anchor slot two follow-ups (INT-543 F8);
    a slot UNCLEAR after two was asked at least once."""
    states = _states(chest_pain__character=AnswerState.UNCLEAR)
    assert _rules().arms.unresolved(states, {CHARACTER: 2}) == (CHARACTER,)


def test_every_unresolved_slot_is_named_in_slot_order() -> None:
    states = _states(
        chest_pain__radiation=AnswerState.UNCLEAR, chest_pain__onset_at=AnswerState.UNCLEAR
    )
    assert _rules().arms.unresolved(states, {RADIATION: 1, ONSET: 1}) == (ONSET, RADIATION)


def test_near_miss_unclear_before_its_follow_up_is_not_unresolved() -> None:
    """CD-04: the item waits for the follow-up; an UNCLEAR whose follow-up was
    never asked is not yet unresolved under rounds 1 and 2."""
    states = _states(chest_pain__character=AnswerState.UNCLEAR)
    assert _rules().arms.unresolved(states, {}) == ()
    assert _rules().arms.unresolved(states, {CHARACTER: 0}) == ()


@pytest.mark.parametrize(
    "state",
    [
        AnswerState.ASKED_PRESENT,
        AnswerState.ASKED_ABSENT,
        AnswerState.ASKED_PENDING,
        AnswerState.NOT_ASKED,
        AnswerState.DECLINED,
        AnswerState.CONTESTED,
    ],
)
def test_near_miss_a_slot_that_is_not_unclear_is_not_unresolved(state: AnswerState) -> None:
    states = _states(chest_pain__character=state)
    assert _rules().arms.unresolved(states, {CHARACTER: 1}) == ()


def test_near_miss_an_unclear_slot_cd04_does_not_name_is_not_unresolved() -> None:
    states = {**_states(), "hpi.onset_date": AnswerState.UNCLEAR}
    assert _rules().arms.unresolved(states, {"hpi.onset_date": 1}) == ()


# --- 3 · a decision outside this build is refused -------------------------------------------


_IDS = {"arms": "CD-04", "chest_pain": "CD-01", "routing": "CD-08"}


def _mutated(decision_id: str, change: Callable[[dict[str, Any]], None]) -> ClinicalDecision:
    decision = _decision(decision_id)
    value = copy.deepcopy(decision.value)
    change(value)
    return decision.model_copy(update={"value": value})


def _build(**replaced: ClinicalDecision) -> ClinicItemRules:
    decisions: Mapping[str, ClinicalDecision] = {
        "routing": _decision("CD-08"),
        "arms": _decision("CD-04"),
        "chest_pain": _decision("CD-01"),
        **replaced,
    }
    return clinic_item_rules(**decisions)


def _set(path: tuple[str, ...], new: object) -> Callable[[dict[str, Any]], None]:
    def change(value: dict[str, Any]) -> None:
        node: Any = value
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = new

    return change


def _drop(path: tuple[str, ...]) -> Callable[[dict[str, Any]], None]:
    def change(value: dict[str, Any]) -> None:
        node: Any = value
        for part in path[:-1]:
            node = node[part]
        del node[path[-1]]

    return change


ARMS = ("unresolved_after_follow_up",)

REFUSALS = [
    pytest.param("arms", _set((*ARMS, "kind"), "chest_pain_unclear"), id="arms-kind-renamed"),
    pytest.param("arms", _set((*ARMS, "action"), "notify"), id="arms-not-an-inbox-item"),
    pytest.param("arms", _set((*ARMS, "decision_ref"), "CD-03"), id="arms-routed-elsewhere"),
    pytest.param("arms", _set((*ARMS, "never_dropped"), False), id="arms-droppable"),
    pytest.param("arms", _set((*ARMS, "pinned_to_note"), False), id="arms-not-pinned"),
    pytest.param("arms", _set((*ARMS, "applies_to"), []), id="arms-no-slots"),
    pytest.param("arms", _set((*ARMS, "applies_to"), "chest_pain.present"), id="arms-slots-str"),
    pytest.param("arms", _set((*ARMS, "applies_to"), [""]), id="arms-empty-slot"),
    pytest.param("arms", _drop(ARMS), id="arms-no-trigger"),
    pytest.param("arms", _set(("unclear_follow_up_tr_asks",), -1), id="arms-negative-bound"),
    pytest.param("arms", _set(("unclear_follow_up_tr_asks",), True), id="arms-boolean-bound"),
    pytest.param("arms", _set((*ARMS, "applies_to"), ["hpi.onset_date"]), id="arms-not-cd01"),
    pytest.param("chest_pain", _set(("sections",), {}), id="no-chest-pain-slots"),
    pytest.param("chest_pain", _set(("sections", "trauma"), {}), id="a-section-without-slots"),
    pytest.param("routing", _set(("applies_to",), ["yellow_review_candidate"]), id="kind-unrouted"),
    pytest.param("routing", _set(("channel",), "acil_triage_desk"), id="routing-not-the-inbox"),
    pytest.param("routing", _drop(("item_kind_notes",)), id="routing-no-kind-notes"),
]


@pytest.mark.parametrize(("which", "change"), REFUSALS)
def test_a_decision_this_build_cannot_follow_exactly_is_refused(
    which: str, change: Callable[[dict[str, Any]], None]
) -> None:
    with pytest.raises(ClinicItemError):
        _build(**{which: _mutated(_IDS[which], change)})


def test_a_routing_key_that_is_not_active_is_refused() -> None:
    routing = _decision("CD-08")
    drafted = {**routing.value_status, "applies_to": DecisionStatus.DRAFT_NEEDS_SOURCE}
    with pytest.raises(ClinicItemError, match="applies_to"):
        _build(routing=routing.model_copy(update={"value_status": drafted}))


@pytest.mark.parametrize("which", ["arms", "chest_pain"])
def test_a_decision_that_is_itself_draft_is_refused(which: str) -> None:
    draft = _decision(_IDS[which]).model_copy(update={"status": DecisionStatus.DRAFT_NEEDS_SOURCE})
    with pytest.raises(ClinicItemError, match="draft_needs_source"):
        _build(**{which: draft})


def test_decisions_handed_in_the_wrong_places_are_refused() -> None:
    with pytest.raises(ClinicItemError, match="CD-08"):
        _build(routing=_decision("CD-04"), arms=_decision("CD-08"))
    with pytest.raises(ClinicItemError, match="CD-01"):
        _build(chest_pain=_decision("CD-04"))


def test_near_miss_the_unchanged_decisions_build() -> None:
    assert _build() == _rules()


def test_near_miss_an_sla_decided_by_the_d18_lane_is_read_as_decided() -> None:
    """The SLA's value is CD-08's; this build reads only whether it is decided."""
    routing = _decision("CD-08")
    decided = {**routing.value_status, "sla": DecisionStatus.ACTIVE}
    assert _build(routing=routing.model_copy(update={"value_status": decided})).sla_decided
