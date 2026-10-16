"""INT-546 — CD-112's per-slot answer mappings, read from the decision (INT-519 items 2, 3).

GitHub #925. CD-112 (D18, verified) decides that on two gating slots a hedge is
recorded as an authored choice, never UNCLEAR and never the plain negative, so
the gate behind the slot never reads Unknown once the question has been asked:

- ``pmh_fh_sh.immunosuppression``: 'bilmiyorum', every CD-04 entry that reads
  on ``*`` and any unmatched hedge record "bilmiyorum" (``mapped_from_hedge``),
  and so does an answer still off-choice after the slot's follow-up
  (``mapped_from_unresolved``) — gates[1].hedge_mapping.
- ``pmh_fh_sh.pregnancy_status``: the same hedges record "emin değilim" —
  CD-100 T4(c), carried by gates[2]. An answer still off-choice after the
  follow-up is NOT mapped: CD-100 round 4 names it the remaining gap.

On both slots the mapping is read before CD-04's ``*`` entries. This suite
pins :mod:`protocols.answer_mappings`, the build of that and nothing more: the
table is the decision's, the hedges are CD-04's own entries (no surface is
written in the module), each mapped choice opens its gate and the plain
negative closes it, and every way the decision could ask for something this
build does not do is refused when the table is built.

The utterances are synthetic (files/04 §7).
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols import answer_mappings
from protocols.answer_mappings import (
    MAPPING_DECISION_ID,
    AnswerMappingError,
    AnswerMappingTable,
    MappingSource,
    answer_mapping_table,
    load_answer_mapping_table,
)
from protocols.answer_states import (
    HedgeBasis,
    HedgeEntry,
    HedgeState,
    load_answer_state_table,
)
from protocols.clinical_decisions import ClinicalDecision, DecisionStatus, load_decision
from protocols.valuesets import load_committed_valuesets

REPO_ROOT = Path(__file__).resolve().parents[2]
CD112 = REPO_ROOT / "packages" / "protocols" / "decisions" / "CD-112.yaml"
CD100 = REPO_ROOT / "packages" / "protocols" / "decisions" / "CD-100.yaml"

IMMUNO = "pmh_fh_sh.immunosuppression"
PREGNANCY = "pmh_fh_sh.pregnancy_status"

#: slot → (the choice CD-112 records for a hedge, whether an unresolved answer maps)
DECIDED: dict[str, tuple[str, bool]] = {
    IMMUNO: ("bilmiyorum", True),
    PREGNANCY: ("emin değilim", False),
}

#: A patient's answer to each mapped question that reads as a CD-04 ``*`` entry.
ANY_SLOT_HEDGES: tuple[str, ...] = (
    "Bilmiyorum.",
    "Emin değilim.",
    "Sanmıyorum.",
    "Pek sayılmaz.",
    "Yok gibi.",
    "Bayılmadım ama bayılacak gibi oldum.",
    "Kanama yoktu, sadece siyahtı.",
)
#: Plain answers: no CD-04 entry reads them, so the mapping does not either.
PLAIN: tuple[str, ...] = ("Hayır.", "Yok.", "Evet.", "Olmadı.", "Dün akşam olmuştu.")


def _raw() -> dict[str, Any]:
    loaded = yaml.safe_load(CD112.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _gate(index: int) -> dict[str, Any]:
    gate = _raw()["value"]["gates"][index]
    assert isinstance(gate, dict)
    return gate


def _table() -> AnswerMappingTable:
    return load_answer_mapping_table()


def _mutated(change: Callable[[dict[str, Any]], None]) -> ClinicalDecision:
    decision = load_decision(CD112)
    value = copy.deepcopy(decision.value)
    change(value)
    return decision.model_copy(update={"value": value})


def _build(decision: ClinicalDecision) -> AnswerMappingTable:
    return answer_mapping_table(decision, load_answer_state_table(), load_committed_valuesets())


# --- 1 · the table is CD-112's ---------------------------------------------------------


def test_the_mapped_slots_are_cd112s_and_nothing_else() -> None:
    table = _table()
    assert table.decision_id == MAPPING_DECISION_ID == "CD-112"
    assert table.slots == frozenset(DECIDED)
    declared = {
        gate["hedge_mapping"]["slot"]
        for gate in _raw()["value"]["gates"]
        if "hedge_mapping" in gate
    }
    assert declared == set(DECIDED)


@pytest.mark.parametrize("slot", sorted(DECIDED))
def test_each_mapping_records_the_decided_authored_choice(slot: str) -> None:
    choice, maps_unresolved = DECIDED[slot]
    mapping = _table().mappings[slot]
    members = load_committed_valuesets().members(mapping.valueset)
    assert members is not None
    assert mapping.records_choice == choice and choice in members
    assert mapping.plain_negative == "hayır" and mapping.plain_negative in members
    assert mapping.records_choice != mapping.plain_negative
    assert mapping.maps_unresolved is maps_unresolved


def test_the_hedges_are_cd04s_entries_and_not_written_in_the_module() -> None:
    source = inspect.getsource(answer_mappings)
    for entry in load_answer_state_table().entries:
        assert entry.surface_tr not in source
    for choice, _ in DECIDED.values():
        assert choice not in source


def test_the_restated_pregnancy_mapping_is_cd100_t4c() -> None:
    """gates[2].hedge_mapping restates, machine-readable, the hedges line of
    gates[2] and CD-100 T4 change (c); it carries no value of its own."""
    gate = _gate(2)
    restated = gate["hedge_mapping"]
    assert restated["slot"] == PREGNANCY
    assert f"'{restated['records_choice']}'" in gate["hedges"]
    cd100 = yaml.safe_load(CD100.read_text(encoding="utf-8"))
    [t4] = [item for item in cd100["value"]["items"] if item.get("ref") == "T4"]
    assert f'recorded as the "{restated["records_choice"]}"' in " ".join(t4["change"].split())
    assert "unresolved_after_follow_up" not in restated
    assert set(restated["record_label_by_source"]) == {"hedge"}


# --- 2 · what each answer records ------------------------------------------------------


@pytest.mark.parametrize("said", ANY_SLOT_HEDGES)
@pytest.mark.parametrize("slot", sorted(DECIDED))
def test_every_cd04_any_slot_hedge_records_the_mapped_choice_never_unclear(
    slot: str, said: str
) -> None:
    mapped = _table().read(slot, said)
    assert mapped is not None
    assert (mapped.slot, mapped.choice, mapped.source, mapped.label) == (
        slot,
        DECIDED[slot][0],
        MappingSource.HEDGE,
        "mapped_from_hedge",
    )
    assert mapped.decision_id == "CD-112"


def test_the_mapping_is_read_before_cd04s_any_slot_entries() -> None:
    """CD-04 alone reads 'Sanmıyorum' UNCLEAR on the slot — which would make the
    gate Unknown. The mapping is read first and records the authored choice."""
    reading = load_answer_state_table().read(IMMUNO, "Sanmıyorum.")
    assert reading is not None and reading.state is HedgeState.UNCLEAR
    mapped = _table().read(IMMUNO, "Sanmıyorum.")
    assert mapped is not None and mapped.choice == "bilmiyorum"


@pytest.mark.parametrize("said", PLAIN)
@pytest.mark.parametrize("slot", sorted(DECIDED))
def test_near_miss_a_plain_answer_is_not_mapped(slot: str, said: str) -> None:
    """Only a hedge is mapped: a plain 'hayır' stays the patient's 'hayır', and
    'yok' is not 'yok gibi'."""
    assert _table().read(slot, said) is None


def test_near_miss_a_hedge_on_a_slot_with_no_mapping_is_not_mapped() -> None:
    assert _table().read("chest_pain.character", "Bilmiyorum.") is None
    assert _table().read("chest_pain.onset_at", "Bilmiyorum.") is None
    assert _table().unresolved("chest_pain.character") is None


def test_an_unresolved_answer_maps_only_where_cd112_decides_it() -> None:
    """Immunosuppression: an answer still off-choice after the follow-up records
    "bilmiyorum", labelled ``mapped_from_unresolved``. Pregnancy: not mapped —
    CD-100 round 4 leaves an UNCLEAR pregnancy_status as the remaining gap."""
    mapped = _table().unresolved(IMMUNO)
    assert mapped is not None
    assert (mapped.choice, mapped.source, mapped.label) == (
        "bilmiyorum",
        MappingSource.UNRESOLVED,
        "mapped_from_unresolved",
    )
    assert _table().unresolved(PREGNANCY) is None


@pytest.mark.parametrize("index", [1, 2])
def test_each_mapped_choice_opens_its_gate_and_the_plain_negative_closes_it(index: int) -> None:
    gate = _gate(index)
    mapping = _table().mappings[gate["hedge_mapping"]["slot"]]
    assert mapping.records_choice in gate["opens_on"]
    assert gate["closes_on"] == [mapping.plain_negative]
    assert gate["gate_decided"].endswith(f"!= '{mapping.plain_negative}'")


def test_the_mapped_answer_shows_no_choice() -> None:
    """invariant 6: a mapped answer names the slot, the label and the decision."""
    mapped = _table().read(PREGNANCY, "Bilmiyorum.")
    assert mapped is not None
    shown = f"{mapped!r} {mapped}"
    assert "emin" not in shown and "bilmiyorum" not in shown.lower()
    assert PREGNANCY in shown and "mapped_from_hedge" in shown and "CD-112" in shown


# --- 3 · a decision outside this build is refused --------------------------------------


def _set(path: tuple[str | int, ...], new: object) -> Callable[[dict[str, Any]], None]:
    def change(value: dict[str, Any]) -> None:
        node: Any = value
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = new

    return change


def _drop(path: tuple[str | int, ...]) -> Callable[[dict[str, Any]], None]:
    def change(value: dict[str, Any]) -> None:
        node: Any = value
        for part in path[:-1]:
            node = node[part]
        del node[path[-1]]

    return change


def _second_mapping_on_one_slot(value: dict[str, Any]) -> None:
    value["gates"][2]["hedge_mapping"]["slot"] = IMMUNO


IMMUNO_MAP = ("gates", 1, "hedge_mapping")
PREG_MAP = ("gates", 2, "hedge_mapping")

REFUSALS = [
    pytest.param(_set((*IMMUNO_MAP, "records_choice"), "bilmiyorm"), id="not-a-member"),
    pytest.param(_set((*IMMUNO_MAP, "records_choice"), "hayır"), id="records-the-negative"),
    pytest.param(_set((*IMMUNO_MAP, "never"), ["hayır"]), id="may-be-unclear"),
    pytest.param(_set((*IMMUNO_MAP, "never"), ["UNCLEAR"]), id="may-be-the-negative"),
    pytest.param(_set((*IMMUNO_MAP, "plain_negative_only"), "hayir"), id="negative-not-member"),
    pytest.param(_drop((*IMMUNO_MAP, "record_label_by_source", "hedge")), id="no-hedge-label"),
    pytest.param(
        _drop((*IMMUNO_MAP, "record_label_by_source", "unresolved")), id="unresolved-unlabelled"
    ),
    pytest.param(
        _set((*PREG_MAP, "record_label_by_source", "unresolved"), "mapped_from_unresolved"),
        id="labelled-but-undecided",
    ),
    pytest.param(_set((*IMMUNO_MAP, "slot"), "immunosuppression"), id="slot-not-a-step"),
    pytest.param(_set((*IMMUNO_MAP, "precedence"), ""), id="no-precedence"),
    pytest.param(_set(("gates", 1, "opens_on"), ["evet"]), id="mapping-does-not-open"),
    pytest.param(_set(("gates", 1, "status"), "draft_needs_source"), id="gate-draft"),
    pytest.param(_set(("gates", 1, "valueset"), "vs.unknown"), id="valueset-uncommitted"),
    pytest.param(_second_mapping_on_one_slot, id="two-mappings-one-slot"),
    pytest.param(_set(("gates",), []), id="no-gates"),
    pytest.param(_set(("gates",), "gates"), id="gates-not-a-list"),
    pytest.param(_set(("gates", 1), "gate"), id="gate-not-a-mapping"),
    pytest.param(_set(IMMUNO_MAP, "bilmiyorum"), id="mapping-not-a-mapping"),
    pytest.param(_set((*IMMUNO_MAP, "record_label_by_source"), "hedge"), id="labels-not-a-mapping"),
    pytest.param(
        _set((*IMMUNO_MAP, "record_label_by_source", "document"), "mapped_from_document"),
        id="an-unknown-source",
    ),
]


@pytest.mark.parametrize("change", REFUSALS)
def test_a_decision_this_build_cannot_follow_exactly_is_refused(
    change: Callable[[dict[str, Any]], None],
) -> None:
    with pytest.raises(AnswerMappingError):
        _build(_mutated(change))


def test_near_miss_the_unchanged_decision_builds() -> None:
    assert _build(_mutated(lambda value: None)) == _table()


def test_a_decision_that_is_itself_draft_is_refused() -> None:
    draft = load_decision(CD112).model_copy(update={"status": DecisionStatus.DRAFT_NEEDS_SOURCE})
    with pytest.raises(AnswerMappingError, match="draft_needs_source"):
        _build(draft)


def test_a_decision_with_no_mapping_at_all_is_refused() -> None:
    def no_mappings(value: dict[str, Any]) -> None:
        for gate in value["gates"]:
            gate.pop("hedge_mapping", None)

    with pytest.raises(AnswerMappingError, match="no gate carries"):
        _build(_mutated(no_mappings))


def test_a_cd04_entry_that_names_a_mapped_slot_is_refused() -> None:
    """The mapping is read before CD-04's ``*`` entries; an entry naming the
    slot itself would make that precedence a guess, so it is refused."""
    hedges = load_answer_state_table()
    named = HedgeEntry(
        surface_tr="sentetik",
        tokens=("sentetik",),
        state=HedgeState.UNCLEAR,
        qualifier="sentetik",
        slots=frozenset({IMMUNO}),
        basis=HedgeBasis.DECIDED,
    )
    widened = dataclasses.replace(hedges, entries=(*hedges.entries, named))
    with pytest.raises(AnswerMappingError, match=IMMUNO):
        answer_mapping_table(load_decision(CD112), widened, load_committed_valuesets())
