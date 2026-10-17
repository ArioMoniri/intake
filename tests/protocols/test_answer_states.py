"""INT-540 — CD-04's Turkish hedge table, read from the decision and never restated.

GitHub #913, from the INT-522 clinical review (F2). CD-04 (active, verified)
decides that a hedged answer to a scripted red-flag question — 'bilmiyorum',
'emin değilim' and the rest of its table — is UNCLEAR at once, never
ASKED_ABSENT, and that UNCLEAR reads Unknown and triggers the slot's
``follow_up_tr`` once. Nothing built it: the runtime waited for the engine's
generic two follow-ups and for whatever the model chose to flag.

This suite pins ``protocols.answer_states`` — the build of CD-04's table and
nothing more:

1. The table is CD-04's, entry for entry, read through the clinical-decisions
   register; no surface is written in the module. The follow-up bound is
   CD-04's own ``unclear_follow_up_tr_asks`` (the decision's "once"), so the
   D18 amendment open on INT-519 item 5 changes data, not code.
2. Each UNCLEAR entry reads UNCLEAR on any scripted slot; each
   PRESENT_QUALIFIED entry reads only on the slots it names. The two draft
   entries take their sourced UNCLEAR floor, and their open upgrade stays the
   invariant-17 literal under ``draft_needs_source`` (the D18 lane).
3. The matcher tests the longest surface first, by whole words after case and
   punctuation only — never a diacritic fold, never a substring.
4. Every way the decision could ask for something this build does not do is
   refused when the table is built.

The utterances are synthetic (files/04 §7).
"""

from __future__ import annotations

import copy
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols import answer_states
from protocols.anchor_choices import load_anchor_choice_table
from protocols.answer_states import (
    ANSWER_STATE_DECISION_ID,
    ANY_SLOT,
    AnswerStateError,
    AnswerStateTable,
    HedgeBasis,
    HedgeState,
    answer_state_table,
    load_answer_state_table,
    utterance_tokens,
)
from protocols.clinical_decisions import ClinicalDecision, DecisionStatus, load_decision
from protocols.validator import PLACEHOLDER_SIGNOFF_RE

REPO_ROOT = Path(__file__).resolve().parents[2]
CD04 = REPO_ROOT / "packages" / "protocols" / "decisions" / "CD-04.yaml"

ANCHOR = "chest_pain.onset_at"
PRESENT = "chest_pain.present"
CHARACTER = "chest_pain.character"
DYSPNOEA = "associated.dyspnoea"
DIAPHORESIS = "associated.diaphoresis"

#: What a patient says, and the CD-04 entry it must read as on a ``*`` slot.
ACTIVE_UNCLEAR: tuple[tuple[str, str, str], ...] = (
    ("Bilmiyorum.", "bilmiyorum", "unknown"),
    ("Emin değilim, tam hatırlamıyorum.", "emin değilim", "unsure"),
    ("Sanmıyorum.", "sanmıyorum", "hedged_negative"),
    ("Pek sayılmaz.", "pek sayılmaz", "hedged_negative"),
    ("Şimdi yok gibi.", "yok gibi", "hedged_negative"),
)
DRAFT_FLOOR: tuple[tuple[str, str], ...] = (
    ("Bayılmadım ama bayılacak gibi oldum.", "near_faint"),
    ("Kanama yoktu, sadece siyahtı.", "black_stool_denied_as_bleeding"),
)


def _raw() -> dict[str, Any]:
    loaded = yaml.safe_load(CD04.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _decision() -> ClinicalDecision:
    return load_decision(CD04)


def _table() -> AnswerStateTable:
    return load_answer_state_table()


def _mutated(change: Callable[[dict[str, Any]], None]) -> ClinicalDecision:
    """CD-04 with one change to its ``value``: the near miss of a refusal."""
    decision = _decision()
    value = copy.deepcopy(decision.value)
    change(value)
    return decision.model_copy(update={"value": value})


# --- 1 · the table is CD-04's, and the bound is its own -------------------------------


def test_the_table_is_cd04_entry_for_entry() -> None:
    raw = _raw()["value"]["entries"]
    table = _table()
    assert table.decision_id == ANSWER_STATE_DECISION_ID == "CD-04"
    built = {
        (entry.surface_tr, entry.state.value, entry.qualifier, entry.slots, entry.basis)
        for entry in table.entries
    }
    expected = {
        (
            item["surface_tr"],
            item["answer_state"],
            item["qualifier"],
            frozenset(item["slots"]),
            HedgeBasis.DECIDED if item["status"] == "active" else HedgeBasis.DRAFT_FLOOR,
        )
        for item in raw
    }
    assert built == expected
    assert len(table.entries) == len(raw) == 14


def test_the_hedge_list_is_read_from_the_decision_and_not_written_in_the_module() -> None:
    """The build restates no surface: a test that the module source names
    none of CD-04's Turkish entries is what keeps the list the decision's."""
    source = inspect.getsource(answer_states)
    for item in _raw()["value"]["entries"]:
        assert item["surface_tr"] not in source


def test_the_follow_up_bound_is_cd04s_once_read_from_the_decision() -> None:
    """CD-04: *"UNCLEAR reads Unknown and triggers the slot's follow_up_tr
    once"*. The machine-readable key restates that "once"; the build reads the
    key and nothing else."""
    raw = _raw()
    assert "triggers the slot's follow_up_tr once" in raw["decision"]
    assert raw["value"]["unclear_follow_up_tr_asks"] == 1
    assert _table().unclear_follow_up_tr_asks == 1


@pytest.mark.parametrize("asks", [0, 1, 2])
def test_an_amendment_to_the_bound_changes_data_and_not_code(asks: int) -> None:
    """INT-519 item 5 (the D18 lane) may resolve an explicit hedge at once. When
    it lands, the decision's number changes and this module reads it."""
    amended = _mutated(lambda value: value.__setitem__("unclear_follow_up_tr_asks", asks))
    assert answer_state_table(amended).unclear_follow_up_tr_asks == asks


# --- 2 · what each entry reads as, and where -----------------------------------------


@pytest.mark.parametrize(("said", "surface", "qualifier"), ACTIVE_UNCLEAR)
@pytest.mark.parametrize("slot", [ANCHOR, CHARACTER, "hpi.onset_date"])
def test_each_active_unclear_hedge_reads_unclear_on_any_scripted_slot(
    said: str, surface: str, qualifier: str, slot: str
) -> None:
    reading = _table().read(slot, said)
    assert reading is not None
    assert (reading.slot, reading.state, reading.qualifier, reading.basis) == (
        slot,
        HedgeState.UNCLEAR,
        qualifier,
        HedgeBasis.DECIDED,
    )
    assert reading.surface_tr == surface
    assert reading.decision_id == "CD-04"


@pytest.mark.parametrize(("said", "qualifier"), DRAFT_FLOOR)
def test_a_draft_entry_takes_its_unclear_floor_and_its_upgrade_stays_open(
    said: str, qualifier: str
) -> None:
    """CD-04: the near-faint and black-stool strings take the sourced UNCLEAR
    floor; whether they are PRESENT_QUALIFIED stays the invariant-17 literal
    under ``draft_needs_source``, and the build reads them as the floor."""
    reading = _table().read(ANCHOR, said)
    assert reading is not None
    assert (reading.state, reading.qualifier, reading.basis) == (
        HedgeState.UNCLEAR,
        qualifier,
        HedgeBasis.DRAFT_FLOOR,
    )
    [raw] = [item for item in _raw()["value"]["entries"] if item["qualifier"] == qualifier]
    assert raw["status"] == DecisionStatus.DRAFT_NEEDS_SOURCE.value
    assert PLACEHOLDER_SIGNOFF_RE.fullmatch(raw["present_qualified_upgrade"]) is not None


@pytest.mark.parametrize(
    ("slot", "said", "qualifier"),
    [
        (PRESENT, "Şu an yok ama vardı.", "resolved"),
        (PRESENT, "Ağrım yok değil hani.", "double_negation"),
        (PRESENT, "Ağrı değil de bir sıkıntı var.", "discomfort_not_pain"),
        (PRESENT, "Arada bir oluyor.", "intermittent"),
        (PRESENT, "Eskiden vardı.", "past"),
        (DYSPNOEA, "Biraz nefesim daralıyor.", "mild"),
        (DIAPHORESIS, "Biraz terledim.", "mild_not_marked"),
    ],
)
def test_a_present_qualified_entry_reads_only_on_the_slots_it_names(
    slot: str, said: str, qualifier: str
) -> None:
    table = _table()
    reading = table.read(slot, said)
    assert reading is not None
    assert (reading.state, reading.qualifier) == (HedgeState.PRESENT_QUALIFIED, qualifier)
    # near miss: the same words to the onset question are not that entry
    assert table.read(ANCHOR, said) is None


def test_no_present_qualified_entry_names_a_cd05_anchor() -> None:
    """A tense anchor is a date: CD-04 gives it UNCLEAR readings only."""
    anchors = load_anchor_choice_table().anchors
    assert _table().present_qualified_slots == frozenset({PRESENT, DYSPNOEA, DIAPHORESIS})
    assert _table().present_qualified_slots.isdisjoint(anchors)


# --- 3 · how the matcher reads an utterance --------------------------------------------


def test_the_longest_surface_is_tested_first() -> None:
    """CD-04 ``match_order``: hedge entries longest first. Two hedges in one
    answer read as the longer one."""
    reading = _table().read(ANCHOR, "Bilmiyorum, emin değilim.")
    assert reading is not None and reading.surface_tr == "emin değilim"


@pytest.mark.parametrize(
    "said",
    ["EMİN DEĞİLİM!", "emin   değilim", "…emin değilim?", "Valla bilmiyorum ki", "BİLMİYORUM"],
)
def test_case_punctuation_and_spacing_do_not_hide_a_hedge(said: str) -> None:
    assert _table().read(ANCHOR, said) is not None


@pytest.mark.parametrize(
    "said",
    [
        pytest.param("emin degilim", id="no-diacritic"),
        pytest.param("bilmiyorumki", id="one-word"),
        pytest.param("bilmiyor", id="another-word"),
        pytest.param("Şu anda var.", id="a-choice"),
        pytest.param("Yok.", id="plain-negative"),
        pytest.param("Hayır.", id="plain-no"),
        pytest.param("Dün akşam olmuştu.", id="a-narrative"),
    ],
)
def test_near_miss_an_answer_that_is_no_entry_reads_as_nothing(said: str) -> None:
    """Whole words, never a diacritic fold or a substring; a plain negative is
    not 'yok gibi'. An answer that is no entry reads as nothing here — what the
    runtime does with it is CD-05's unresolved answer, not this table's."""
    assert _table().read(ANCHOR, said) is None


def test_the_utterance_is_folded_with_turkish_dotted_and_dotless_i() -> None:
    assert utterance_tokens("IŞIK İnce, ılık.") == ("ışık", "ince", "ılık")
    assert utterance_tokens("") == ()


def test_the_reading_shows_no_qualifier_and_no_surface() -> None:
    """invariant 6: a reading names the slot and the decision, never what the
    patient's answer was taken to mean."""
    reading = _table().read(ANCHOR, "Emin değilim.")
    assert reading is not None
    shown = f"{reading!r} {reading}"
    assert "unsure" not in shown and "emin" not in shown
    assert ANCHOR in shown and "CD-04" in shown


# --- 4 · a decision outside this build is refused -------------------------------------


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


def _duplicate_bilmiyorum(value: dict[str, Any]) -> None:
    value["entries"].append(copy.deepcopy(value["entries"][3]))


OPEN_LITERAL = "TO" + "DO: this upgrade requires clinical sign-off"

REFUSALS = [
    pytest.param(_drop(("unclear_follow_up_tr_asks",)), id="no-bound"),
    pytest.param(_set(("unclear_follow_up_tr_asks",), -1), id="negative-bound"),
    pytest.param(_set(("unclear_follow_up_tr_asks",), True), id="boolean-bound"),
    pytest.param(_set(("unclear_follow_up_tr_asks",), "1"), id="string-bound"),
    pytest.param(_set(("unclear_follow_up_tr_asks",), 1.5), id="fractional-bound"),
    pytest.param(_set(("unclear_evaluates_as",), "absent"), id="unclear-not-unknown"),
    pytest.param(_set(("present_qualified_evaluates_as",), "unknown"), id="pq-not-present"),
    pytest.param(_set(("unmatched_hedge",), "ASKED_ABSENT"), id="unmatched-not-unclear"),
    pytest.param(_set(("plain_negative_to_scripted_question",), "UNCLEAR"), id="plain-negative"),
    pytest.param(_set(("entries",), []), id="no-entries"),
    pytest.param(_set(("entries",), "bilmiyorum"), id="entries-not-a-list"),
    pytest.param(_set(("entries", 3), "bilmiyorum"), id="entry-not-a-mapping"),
    pytest.param(_set(("entries", 3, "surface_tr"), ""), id="empty-surface"),
    pytest.param(_set(("entries", 3, "surface_tr"), "?!"), id="surface-without-a-word"),
    pytest.param(_set(("entries", 3, "surface_tr"), 7), id="surface-not-a-string"),
    pytest.param(_set(("entries", 3, "answer_state"), "ASKED_ABSENT"), id="absent-state"),
    pytest.param(_set(("entries", 3, "qualifier"), ""), id="no-qualifier"),
    pytest.param(_set(("entries", 3, "slots"), []), id="no-slots"),
    pytest.param(_set(("entries", 3, "slots"), "*"), id="slots-not-a-list"),
    pytest.param(_set(("entries", 3, "slots"), [""]), id="empty-slot"),
    pytest.param(_set(("entries", 3, "status"), "proposed"), id="unknown-status"),
    pytest.param(_set(("entries", 1, "answer_state"), "PRESENT_QUALIFIED"), id="draft-upgraded"),
    pytest.param(_set(("entries", 1, "present_qualified_upgrade"), "yes"), id="upgrade-closed"),
    pytest.param(_drop(("entries", 1, "present_qualified_upgrade")), id="draft-no-upgrade"),
    pytest.param(_set(("entries", 0, "slots"), [ANY_SLOT]), id="pq-on-every-slot"),
    pytest.param(_duplicate_bilmiyorum, id="duplicate-entry"),
]


@pytest.mark.parametrize("change", REFUSALS)
def test_a_decision_this_build_cannot_follow_exactly_is_refused(
    change: Callable[[dict[str, Any]], None],
) -> None:
    """Each one change to CD-04 asks for a reading this module does not build.
    It is refused at load — before a session is composed — never guessed."""
    with pytest.raises(AnswerStateError):
        answer_state_table(_mutated(change))


def test_near_miss_the_unchanged_decision_builds() -> None:
    assert answer_state_table(_mutated(lambda value: None)) == _table()


def test_near_miss_a_draft_upgrade_reworded_but_still_open_builds() -> None:
    """The refusal is for an upgrade that stopped being open, not for its wording."""
    reworded = _mutated(_set(("entries", 1, "present_qualified_upgrade"), OPEN_LITERAL))
    assert answer_state_table(reworded).entries == _table().entries


def test_a_decision_that_is_itself_draft_is_refused() -> None:
    draft = _decision().model_copy(update={"status": DecisionStatus.DRAFT_NEEDS_SOURCE})
    with pytest.raises(AnswerStateError, match="draft_needs_source"):
        answer_state_table(draft)
