"""INT-470 round 2 — what CD-110 decides, pinned (review of PR #804, round 1).

Each test reads the committed CD-110 record and checks one decided value with
the same parser and Kleene evaluator the runtime gates use
(protocols.triage.expr), so a gate that would close on an unsure answer, on a
skipped proxy item or on an episodic complaint fails here. Near misses: the
review's wrong shapes, each failing rather than passing quietly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import policy_guard_for
from protocols.clinical_decisions import VerifierVerdict, load_register
from protocols.triage.expr import Truth, evaluate_node, parse_when

_NT = "docs/evidence/verification/near-twin-sweep-582.md#L"
_WB = "docs/evidence/verification/cluster-wave-b.md#L"
_W8 = "docs/evidence/verification/specialty-wave8-geriatric-dental.md#L"

PRESENCE_GATE = "guncel_saglik_sikayeti != 'hayir' || chest_pain.present == true"
CLUSTER_AIRWAY_GATE = "yuz_cene_sisligi == true || dis_agrisi == true || yuz_cene_darbe == true"
PEDODONTI_AIRWAY_GATE = "dis_agrisi == true || dis_eti_sisligi == true || yuz_cene_sisligi == true"
CLUSTER_SWELLING_TEXT = "Yüzünüzde, çenenizde ya da dilinizin altında şişlik var mı?"
NEW_SLOT_IDS = frozenset(
    {
        "hpi.guncel_saglik_sikayeti",
        "hpi.episodicity",
        "planlanan_islem",
        "planlanan_asi",
        "kurul_saglik_sorunlari",
        "korunmasiz_deneme_suresi",
        "durumu_bilme_suresi",
    }
)


def _resolution(item: str) -> Mapping[str, Any]:
    decision = load_register()["CD-110"]
    return next(r for r in decision.value["resolutions"] if r["item"] == item)


def _truth(expression: str, values: Mapping[str, Any]) -> Truth:
    return evaluate_node(parse_when(expression), lambda ref: values.get(ref))


def _guard_clean(text: str) -> bool:
    guard = policy_guard_for(locale="tr", profile=VoiceProfile.RESIDENCY_TR)
    return not guard.inspect_sentence(text) and not any(c.isdigit() for c in text)


# --- the checkers --------------------------------------------------------------------


def presence_gate_problems(gate: str) -> list[str]:
    """The history opens toward asking: on yes, on unsure, and on a chest-pain yes."""
    cases = [
        ({"guncel_saglik_sikayeti": "evet"}, True, "a yes opens the history"),
        ({"guncel_saglik_sikayeti": "emin_degilim"}, True, "an unsure answer opens it"),
        (
            {"guncel_saglik_sikayeti": "hayir", "chest_pain.present": True},
            True,
            "a later chest-pain yes reopens it",
        ),
        (
            {"guncel_saglik_sikayeti": "hayir", "chest_pain.present": False},
            False,
            "a plain no with no chest pain closes it",
        ),
    ]
    problems = []
    for values, opens, label in cases:
        if (_truth(gate, values) is Truth.TRUE) is not opens:
            problems.append(label)
    return problems


def airway_gate_problems(gate: str, required_terms: frozenset[str]) -> list[str]:
    """Each required presentation alone opens the airway item; trismus never does."""
    problems = []
    for term in sorted(required_terms):
        values = {name: False for name in required_terms}
        values[term] = True
        if _truth(gate, values) is not Truth.TRUE:
            problems.append(f"{term} alone does not open the airway item")
    if "agiz_acma_guclugu" in gate:
        problems.append("trismus is a gate term")
    return problems


def lmp_guard_problems(guard: Mapping[str, Any]) -> list[str]:
    problems = []
    if list(guard.get("applies_to", ())) != ["pmh_fh_sh.lmp_date"]:
        problems.append("the guard applies to lmp_date only")
    if "pmh_fh_sh.pregnancy_status" not in guard.get("not_applied_to", ()):
        problems.append("pregnancy_status stays unguarded, asked every session")
    if guard.get("unknown_opens") is not True:
        problems.append("an unknown sex at birth or age opens the question")
    if guard.get("excludes_only") != "recorded":
        problems.append("only a recorded value excludes")
    return problems


# --- T1 (findings 1, 2) ----------------------------------------------------------------


def test_lmp_guard_fails_toward_asking_and_leaves_pregnancy_status_alone() -> None:
    assert lmp_guard_problems(_resolution(f"{_NT}94")["population_guard"]) == []


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"applies_to": ["pmh_fh_sh.lmp_date", "pmh_fh_sh.pregnancy_status"]}, "lmp_date only"),
        ({"not_applied_to": []}, "pregnancy_status stays"),
        ({"unknown_opens": False}, "unknown sex"),
        ({"excludes_only": "inferred"}, "recorded value"),
    ],
)
def test_each_wrong_lmp_guard_fails(overrides: dict[str, Any], expected: str) -> None:
    guard = dict(_resolution(f"{_NT}94")["population_guard"])
    guard.update(overrides)
    assert any(expected in p for p in lmp_guard_problems(guard))


def test_kadin_q2_stays_until_base_asks_every_patient_of_the_chain() -> None:
    t1 = _resolution(f"{_NT}94")
    assert t1["kadin_q2"]["removed_only_when"] == "base asks lmp_date of every patient in the chain"
    assert t1["red_flag_gate_input"] is True, "lmp_date gates pregnancy rules: make safety"


# --- T17 (findings 3, 12) --------------------------------------------------------------


def test_derived_duration_needs_an_ongoing_answer() -> None:
    t17 = _resolution(f"{_NT}110")
    item = t17["episodicity_item"]
    assert item["slot"] == "hpi.episodicity"
    assert item["choices_tr"] == ["sürekli", "arada bir", "emin değilim"]
    assert item["derive_duration_only_when"] == "sürekli"
    assert _guard_clean(item["ask_tr"]) and item["ask_tr"].count("?") == 1
    assert "no recorded fact is lost" not in t17["change"]
    assert "files/04" in t17["change"], "files/04 §1 and §5 amended in the same change"


@pytest.mark.parametrize("bad", ["arada bir", "emin değilim", None])
def test_a_duration_is_never_derived_from_an_episodic_or_unknown_answer(bad: str | None) -> None:
    assert _resolution(f"{_NT}110")["episodicity_item"]["derive_duration_only_when"] != bad


# --- #L116 (findings 4, 5) ---------------------------------------------------------------


def test_presence_screen_is_three_valued_recent_and_reopened_by_chest_pain() -> None:
    screen = _resolution(f"{_WB}116")["presence_screen"]
    assert screen["gate"] == PRESENCE_GATE
    assert presence_gate_problems(screen["gate"]) == []
    assert screen["type"] == "code"
    assert screen["choices_tr"] == ["evet", "hayır", "emin değilim"]
    assert screen["position"] == "before hpi.onset_date"
    assert "yakın zamanda" in screen["ask_tr"], "recent and intermittent symptoms count"
    assert _guard_clean(screen["ask_tr"]) and screen["ask_tr"].count("?") == 1
    assert screen["retired_by_open_turn"] == "evet only"


@pytest.mark.parametrize(
    ("gate", "expected"),
    [
        ("guncel_saglik_sikayeti == 'evet'", "an unsure answer opens it"),
        ("guncel_saglik_sikayeti != 'hayir'", "a later chest-pain yes reopens it"),
        ("guncel_saglik_sikayeti == true", "a yes opens the history"),
    ],
)
def test_each_wrong_presence_gate_fails(gate: str, expected: str) -> None:
    assert expected in presence_gate_problems(gate)


# --- dental airway (findings 6, 7, 8) -------------------------------------------------------


def test_cluster_airway_gate_opens_on_pain_swelling_or_injury_never_trismus() -> None:
    dental = _resolution(f"{_WB}103")
    assert dental["cluster_gate"] == CLUSTER_AIRWAY_GATE
    terms = frozenset({"yuz_cene_sisligi", "dis_agrisi", "yuz_cene_darbe"})
    assert airway_gate_problems(dental["cluster_gate"], terms) == []


def test_pedodonti_asks_a_child_with_facial_swelling_only() -> None:
    pedo = _resolution(f"{_WB}104")
    assert pedo["gate"] == PEDODONTI_AIRWAY_GATE
    terms = frozenset({"dis_agrisi", "dis_eti_sisligi", "yuz_cene_sisligi"})
    assert airway_gate_problems(pedo["gate"], terms) == []
    assert _guard_clean(pedo["child_swelling_tr"])


@pytest.mark.parametrize(
    ("gate", "terms"),
    [
        ("dis_agrisi == true || dis_eti_sisligi == true", {"yuz_cene_sisligi"}),
        ("yuz_cene_sisligi == true || dis_agrisi == true", {"yuz_cene_darbe"}),
        ("agiz_acma_guclugu == true || dis_agrisi == true", {"dis_agrisi"}),
    ],
)
def test_each_narrower_airway_gate_fails(gate: str, terms: set[str]) -> None:
    assert airway_gate_problems(gate, frozenset(terms))


def test_one_posture_only_widens_and_endodonti_keeps_under_tongue_swelling() -> None:
    posture = _resolution(f"{_W8}96")
    assert posture["branch_rule"] == (
        "every dental chain asks at least under the cluster gate; a branch may re-declare "
        "the item only with a wider gate (an extra OR term)"
    )
    assert posture["endodonti_yuz_cene_sisligi_tr"] == CLUSTER_SWELLING_TEXT


# --- T3 (finding 13), inventory routing (14), sources (15), history ---------------------------


def test_t3_keeps_years_text_first_and_time_known() -> None:
    t3 = _resolution(f"{_NT}96")
    assert t3["korunmasiz_deneme_suresi"]["delivery"] == "text_first"
    follow = t3["onset_follow_up_tr"]
    assert "yıl" in follow and _guard_clean(follow)
    assert t3["perinatoloji"]["slot"] == "durumu_bilme_suresi"


def test_every_new_slot_id_is_routed_for_its_inventory_row() -> None:
    routing = load_register()["CD-110"].value["inventory_rows_routed"]
    assert set(routing["slots"]) == NEW_SLOT_IDS
    assert routing["to"] == "the legal lane (INT-471, GitHub #800)"


def test_calgary_cambridge_is_cited_for_structure_only() -> None:
    decision = load_register()["CD-110"]
    for source in decision.sources:
        if getattr(source, "guideline_id", "") == "CALGARY-CAMBRIDGE-GUIDE":
            assert "not as a clinical guideline" in str(source.caveat), source.section
    assert "at0002" in str(decision.inference_disclosure)


def test_round_one_is_history_and_the_verdict_waits_for_re_verification() -> None:
    decision = load_register()["CD-110"]
    assert decision.verifier.verdict is VerifierVerdict.PENDING
    history = decision.value["verification_history"]
    assert history[0]["round"] == 1 and history[0]["verdict"] == "request_changes"
    assert len(history[0]["per_resolution"]) == 18
