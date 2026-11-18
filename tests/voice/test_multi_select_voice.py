"""INT-604 round 1 (ADR-043) — the voice lane binds a multi-select answer whole.

``chest_pain.radiation`` is ``multiple: true``. A patient who says "omzuma ve
koluma yayılıyor" names two sites. Before this change the extraction schema
offered one string, a list was refused as WRONG_TYPE, and a model keeping only
"omuz" left the K2 cardiac RED unfired. Now:

- the schema the model is handed is an array of the committed members;
- the parser binds the set through ``protocols.choices.bind_choice_set``, so a
  set holding the exclusive "yok" beside a site is refused (flagged
  ``exclusive_conflict``, nothing bound), never trimmed;
- ``SessionTriage.context`` reads a bound set whole (``submitted_set_answer``),
  so any named site that fires, fires.

Golden: "omuz" + "kol" fires the K2 RED. Near miss: "omuz" alone does not.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
import test_extraction_valuesets as int518
import test_live_triage as live
from clinical_schemas.session import AnswerState
from intake_voice_runtime.extraction.parse import parse_extraction
from intake_voice_runtime.extraction.result import FlagReason
from intake_voice_runtime.extraction.schema import slot_output_schema
from intake_voice_runtime.profiles import VoiceProfile
from protocols.loader import load_pack
from protocols.valuesets import load_committed_valuesets

RADIATION = int518.RADIATION
K2 = "rf.chest_pain_cardiac_features"


def _radiation_slot():  # type: ignore[no-untyped-def]
    return (
        load_pack(int518.REPO_ROOT / "packages/protocols/base/intake.yaml")
        .sections["chest_pain"]
        .slots["radiation"]
    )


def _members() -> dict[str, tuple[str, ...]]:
    return load_committed_valuesets().member_map()


def test_the_schema_offers_an_array_of_the_committed_members() -> None:
    schema = slot_output_schema({RADIATION: _radiation_slot()}, _members())
    value = schema["properties"]["slots"]["properties"][RADIATION]["properties"]["value"]
    assert value["type"] == "array"
    assert value["items"] == {"type": "string", "enum": list(_members()["vs.chest_pain_radiation"])}
    assert value["minItems"] == 1
    assert value["uniqueItems"] is True


def _completion(value: object, confidence: float = 0.9) -> str:
    return json.dumps(
        {
            "slots": {RADIATION: {"value": value, "confidence": confidence}},
            "candidate_flags": [],
            "clarification_needed": False,
        },
        ensure_ascii=False,
    )


def _parse(value: object) -> tuple[list[object], list[FlagReason]]:
    raw = _completion(value)
    result = parse_extraction(
        raw=raw, slots={RADIATION: _radiation_slot()}, valuesets=_members(), step_id=RADIATION
    )
    return [u.value for u in result.slot_updates], [f.reason for f in result.flags]


def test_two_sites_bind_as_the_set() -> None:
    assert _parse(["omuz", "kol"]) == ([["omuz", "kol"]], [])


def test_one_site_binds_as_that_site() -> None:
    assert _parse(["kol"]) == (["kol"], [])
    assert _parse("kol") == (["kol"], [])


@pytest.mark.parametrize("value", [["kol", "yok"], ["yok", "kol"]])
def test_yok_beside_a_site_is_refused_never_trimmed(value: list[str]) -> None:
    assert _parse(value) == ([], [FlagReason.EXCLUSIVE_CONFLICT])


@pytest.mark.parametrize("value", [["kol", "kalça"], [], [3]])
def test_a_non_member_an_empty_set_or_a_non_string_is_refused(value: list[object]) -> None:
    updates, flags = _parse(value)
    assert updates == []
    assert flags in ([FlagReason.VALUESET_VIOLATION], [FlagReason.WRONG_TYPE])


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_golden_shoulder_and_arm_fires_the_k2_red(profile: VoiceProfile) -> None:
    rig = live._rig(profile, int518._model_answers("başka bir his", ["omuz", "kol"]))  # type: ignore[arg-type]
    live._drive(rig)
    context = rig.triage.context(rig.stack.engine)
    assert context.answers[RADIATION].values == ("omuz", "kol")
    assert context.answers[RADIATION].state is AnswerState.CONTESTED
    # Layer B told the clinic; the next turn delivers the pre-positioned RED.
    assert [n.rule_ids for n in rig.clinic.notifications] == [(K2,)]
    live._turn(rig)
    assert [m.rule_id for m in rig.channel.published] == [K2]


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_the_shoulder_alone_does_not_fire(profile: VoiceProfile) -> None:
    rig = live._rig(profile, int518._model_answers("başka bir his", ["omuz"]))  # type: ignore[arg-type]
    live._drive(rig)
    assert rig.stack.engine.value_of(RADIATION) == "omuz"
    live._turn(rig)
    assert rig.clinic.notifications == []
    assert rig.channel.published == []


def test_confidence_is_kept_for_a_set() -> None:
    raw = _completion(["omuz", "kol"], 0.75)
    result = parse_extraction(
        raw=raw, slots={RADIATION: _radiation_slot()}, valuesets=_members(), step_id=RADIATION
    )
    assert result.slot_updates[0].confidence == Decimal("0.75")


# --- runtime review round 1: a refused set never drops a symptom ------------------


_RADIATION_SAID = (dict(int518.TRANSCRIPTS)[RADIATION], "Koluma yayılıyor.")


class _Sequenced(int518.AnswerTable):
    """The model's radiation answers in order, one per Work that declares it."""

    def __init__(self, radiation: list[object]) -> None:
        super().__init__(int518._model_answers("başka bir his", "yok"))
        self.radiation = list(radiation)

    def complete(self, call):  # type: ignore[no-untyped-def]
        # Only the radiation question and its follow-up are answered about the
        # spread; every other Work's words carry no radiation answer.
        self.answers.pop(RADIATION, None)
        if call.data.text in _RADIATION_SAID and self.radiation:
            self.answers[RADIATION] = self.radiation.pop(0)  # type: ignore[assignment]
        return super().complete(call)


def _answer_follow_up(rig: live.Rig) -> str:
    """Speak the queued follow-up and send the patient's next answer to it."""
    [follow_up] = rig.stack.engine.follow_ups
    rig.stack.session.ask_ledger.note_asked(follow_up)
    rig.stack.session.submit_utterance(follow_up, "Koluma yayılıyor.")
    rig.stack.agent.run_pending()
    return follow_up


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_golden_a_refused_set_is_asked_again_and_the_second_answer_fires(
    profile: VoiceProfile,
) -> None:
    gateway = _Sequenced([["kol", "yok"], "kol"])
    rig = live._rig(profile, {}, gateway=gateway)
    live._drive(rig)
    engine = rig.stack.engine
    # refused, not dropped: the step is pending and its follow-up is queued
    assert engine.state_of(RADIATION) is AnswerState.ASKED_PENDING
    assert len(engine.follow_ups) == 1
    assert rig.clinic.notifications == []
    _answer_follow_up(rig)
    assert engine.value_of(RADIATION) == "kol"
    assert [n.rule_ids for n in rig.clinic.notifications] == [(K2,)]
    live._turn(rig)
    assert [m.rule_id for m in rig.channel.published] == [K2]


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_golden_with_the_clarify_budget_spent_the_named_sites_reach_triage_whole(
    profile: VoiceProfile,
) -> None:
    gateway = _Sequenced([["kol", "yok"], ["kol", "yok"], ["kol", "yok"]])
    rig = live._rig(profile, {}, gateway=gateway)
    live._drive(rig)
    engine = rig.stack.engine
    while engine.follow_ups:
        _answer_follow_up(rig)
    # never a bare UNCLEAR: every named site is bound, and triage reads the union
    assert engine.state_of(RADIATION) is AnswerState.ASKED_PRESENT
    assert engine.value_of(RADIATION) == ["kol", "yok"]
    assert rig.triage.context(engine).answers[RADIATION].values == ("kol", "yok")
    assert [n.rule_ids for n in rig.clinic.notifications] == [(K2,)]
    live._turn(rig)
    assert [m.rule_id for m in rig.channel.published] == [K2]


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_yok_alone_binds_and_fires_nothing(profile: VoiceProfile) -> None:
    rig = live._rig(profile, {}, gateway=_Sequenced([["yok"]]))
    live._drive(rig)
    assert rig.stack.engine.value_of(RADIATION) == "yok"
    assert rig.stack.engine.follow_ups == ()
    live._turn(rig)
    assert rig.clinic.notifications == []
    assert rig.channel.published == []
