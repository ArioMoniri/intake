"""INT-497 — `make runtime-sim` reports the turn's audio timeline, server side.

The owner's order names three measurements: end of the patient's speech → the
agent's first audio, the gaps between consecutive clips, and ASR finalisation.
The harness can honestly see a slice of the first two and none of the third,
and this file pins exactly that slice:

- **first audio**: virtual milliseconds from entering ``take_turn`` to the
  first sample handed to the audio sink. It is the Talker's own contribution
  to the turn gap — everything before (end-of-turn detection, the STT flush,
  the uplink) and after (downlink, jitter buffer, device output) is outside
  this process, and the report says so rather than adding it up;
- **joins**: dead air the Talker leaves between two sentences it plays inside
  one turn (a YELLOW at its insertion window, then the next question);
- **ASR finalisation**: not in this path at all — the Talker is handed a final
  transcript — and the report says that instead of printing a number.

The device measures all three end to end (apps/mobile turnTimeline.ts).
"""

from __future__ import annotations

import pytest
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.simulator import (
    NetworkProfile,
    ParityTrace,
    ScenarioReport,
    TurnClass,
    TurnRecord,
    render_report,
    runnable_scenarios,
)
from test_invariants import run_scenario

NETWORK = NetworkProfile.TR_MOBILE_MID_LTE


@pytest.mark.parametrize("scenario", [s.id for s in runnable_scenarios()])
def test_every_turn_that_spoke_on_voice_reports_when_its_first_audio_left(scenario: str) -> None:
    report = run_scenario(scenario, VoiceProfile.RESIDENCY_TR, NETWORK)
    for turn in report.turns:
        if turn.spoke:
            assert turn.first_audio_ms is not None
            assert turn.first_audio_ms >= 0.0


@pytest.mark.parametrize("scenario", [s.id for s in runnable_scenarios()])
def test_a_typed_turn_reports_no_audio_rather_than_zero(scenario: str) -> None:
    report = run_scenario(scenario, VoiceProfile.TYPED, NETWORK)
    for turn in report.turns:
        assert turn.first_audio_ms is None
        assert turn.join_gaps_ms == ()


def test_a_stalled_backend_does_not_delay_the_first_audio() -> None:
    """RT-03: Layer B stalled ten seconds. The question's first sample still
    leaves at once — the Talker never awaits Backend Work (invariant 9)."""
    report = run_scenario("RT-03", VoiceProfile.RESIDENCY_TR, NETWORK)
    spoken = [turn for turn in report.turns if turn.spoke]
    assert spoken
    assert all(turn.first_audio_ms == 0.0 for turn in spoken)


def test_a_yellow_and_the_next_question_join_with_no_dead_air() -> None:
    """RT-07: the YELLOW is spoken at its insertion window and the next
    question follows it inside the same turn. The Talker adds nothing between."""
    report = run_scenario("RT-07", VoiceProfile.RESIDENCY_TR, NETWORK)
    joins = [gap for turn in report.turns for gap in turn.join_gaps_ms]
    assert joins, "RT-07 should play two sentences back to back in one turn"
    assert all(gap == 0.0 for gap in joins)


def test_the_timeline_is_transport_only_and_stays_out_of_parity() -> None:
    """Invariant 8's parity is over what a turn DID. Audio timing is a
    transport quantity — a screen plays nothing — so it is not compared."""
    residency = ParityTrace.of(run_scenario("RT-07", VoiceProfile.RESIDENCY_TR, NETWORK))
    typed = ParityTrace.of(run_scenario("RT-07", VoiceProfile.TYPED, NETWORK))
    assert residency.divergence(typed) == ()


def test_the_report_prints_the_timeline_and_says_what_it_cannot_see() -> None:
    report = ScenarioReport(
        scenario_id="RT-07",
        profile=VoiceProfile.RESIDENCY_TR,
        turn_class=TurnClass.SCRIPTED,
        network=NETWORK,
        turns=(
            TurnRecord(
                index=0, elapsed_ms=120.0, spoke=True, first_audio_ms=0.0, join_gaps_ms=(0.0,)
            ),
        ),
    )
    rendered = render_report((report,))
    assert "first audio +0.0 ms" in rendered
    assert "joins 0.0 ms" in rendered
    assert "ASR finalisation" in rendered
    assert "not in this path" in rendered


def test_a_turn_that_played_nothing_prints_no_audio_timing() -> None:
    report = ScenarioReport(
        scenario_id="RT-08",
        profile=VoiceProfile.RESIDENCY_TR,
        turn_class=TurnClass.SCRIPTED,
        network=NETWORK,
        turns=(TurnRecord(index=0, elapsed_ms=0.0, spoke=False),),
    )
    assert "first audio" not in render_report((report,)).split("turn 0:")[1]
