"""RT-01…RT-08, transcribed from files/04 §6 — not invented (INT-094).

``files/04_CLINICAL_PROTOCOLS.md`` line 204 is the source of record for the
runtime scenarios, and unlike the IM-* set of INT-082 **all eight of RT-01…08
are actually defined there**. Every ``blueprint_line`` below is a verbatim
substring of that line, and
``tests/voice/test_invariants.py::test_every_runtime_scenario_line_is_in_files_04``
re-reads the file at test time so a transcription cannot drift from its
source. Nothing here paraphrases the blueprint and nothing here invents a
scenario.

**RT-06 names two profiles that do not exist**, and that is a defect in
files/04, not a licence to build them: CLAUDE.md invariant 19 and files/00 §0b
delete ``cascade_fast`` and ``s2s_cloud``, and files/02 §8.1 records the
deletion as a *correction* to the older text. files/00 wins (CLAUDE.md read
order), so RT-06 is carried by the property that survives the deletion — the
one PolicyGuard clause the scenario itself states — against the two profiles
that exist. The verbatim line is kept anyway, because a transcription that
silently drops the half it disagrees with is not a transcription. The two
names appear in this module only inside that quoted line and inside prose;
the AST gate that forbids them lives over ``services/voice-runtime/src``,
where no such string exists.

``covered_by`` names the test that actually holds each property today, and
``gap`` says — in the scenario's own words — which clause of the blueprint
line nothing in this repository proves yet. A scenario with a ``gap`` is not
a passing scenario dressed up; the gap is the deliverable.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["RUNTIME_SCENARIOS", "RuntimeScenario", "scenario"]


@dataclass(frozen=True, slots=True)
class RuntimeScenario:
    """One RT-0x id, its verbatim blueprint line, and what proves it."""

    scenario_id: str
    #: Verbatim substring of files/04 line 204. Never a paraphrase.
    blueprint_line: str
    #: ``path::test`` node ids that hold the properties this scenario states.
    covered_by: tuple[str, ...]
    #: Clauses of ``blueprint_line`` that nothing in this repository proves,
    #: each naming the component that owns them. Empty when fully covered.
    gaps: tuple[str, ...] = ()


RUNTIME_SCENARIOS: tuple[RuntimeScenario, ...] = (
    RuntimeScenario(
        scenario_id="RT-01",
        blueprint_line=(
            "RT-01 patient keeps talking for 40 s while two documents parse in the "
            "background — Talker must acknowledge, never stall, and speak the "
            "document result only at a pause"
        ),
        covered_by=(
            "tests/voice/test_invariants.py::test_rt01_two_backend_works_never_stall_the_turn",
            "tests/voice/test_insertion_window.py::test_speech_is_held_while_the_patient_is_talking",
            "tests/voice/test_insertion_window.py::test_speech_lands_at_the_natural_window",
        ),
        gaps=(
            "the acknowledgement itself — its Turkish is patient copy no human has "
            "signed off, so TalkerConfig.safe_bridge_clip_id is unset and the turn "
            "stays silent rather than improvising one (INT-091's recorded ask)",
            "'two documents parse' — the document pipeline is services/workers, not "
            "the runtime; the harness models them as two Backend Work items",
        ),
    ),
    RuntimeScenario(
        scenario_id="RT-02",
        blueprint_line=(
            "RT-02 RED rule fires while the agent is mid-sentence — playback cut ≤ 150 "
            "ms, RED script spoken, UI interrupt ≤ 300 ms"
        ),
        covered_by=(
            "tests/voice/test_red_preemption.py::test_playback_stop_is_measured_and_within_the_150_ms_budget",
            "tests/voice/test_red_preemption.py"
            "::test_end_to_end_script_start_is_measured_and_within_the_300_ms_budget",
            "tests/voice/test_red_preemption.py::test_the_red_path_import_closure_contains_no_media_module",
            "tests/voice/test_red_preempt_only.py::test_a_rules_engine_red_may_preempt",
            "tests/voice/test_invariants.py::test_rt02_a_red_cuts_playback_before_anything_is_sent",
        ),
        gaps=(
            "'UI interrupt ≤ 300 ms' is measured to the data-channel trigger, not to "
            "a rendered frame — the client is apps/mobile and no device runs here",
        ),
    ),
    RuntimeScenario(
        scenario_id="RT-03",
        blueprint_line=(
            "RT-03 Backend Agent stalled 10 s — Talker continues within budget, rail "
            'shows "güncelleniyor" chip, no duplicate injection on recovery'
        ),
        covered_by=(
            "tests/voice/test_talker_never_awaits.py"
            "::test_turn_latency_is_unchanged_by_an_arbitrarily_stalled_backend",
            "tests/voice/test_insertion_window.py::test_delivery_is_idempotent_on_work_id",
            "tests/voice/test_invariants.py::test_rt03_a_ten_second_stall_costs_the_turn_nothing",
        ),
        gaps=(
            "the rail chip's own label — files/03 §4.6 invariant 10 puts activity "
            "labels in a fixed tr/en table that is authored copy, not runtime state",
        ),
    ),
    RuntimeScenario(
        scenario_id="RT-04",
        blueprint_line=(
            "RT-04 extraction returns `clarification_needed` for step n after step n+1 "
            "was already asked — follow-up card appears and is asked next turn, never "
            "re-asking n verbatim"
        ),
        covered_by=(
            "tests/engine/test_fsm.py::TestFollowUpTr"
            "::test_a_clarification_queues_a_follow_up_spoken_verbatim",
            "tests/sim/test_scenarios.py::TestTermination"
            "::test_no_slot_is_asked_more_often_than_the_clarification_bound",
        ),
        gaps=("'follow-up card' is an apps/mobile affordance, not a runtime object",),
    ),
    RuntimeScenario(
        scenario_id="RT-05",
        blueprint_line=(
            "RT-05 five answers submitted in 3 s (fast talker) — FIFO order preserved, "
            "one Work in flight, final slot state identical to sequential run"
        ),
        covered_by=(
            "tests/voice/test_work_queue.py::test_work_runs_in_submission_order",
            "tests/voice/test_work_queue.py::test_only_one_work_is_ever_in_flight",
            "tests/voice/test_work_queue.py"
            "::test_no_slot_update_is_lost_or_reordered_under_interleaved_submission",
        ),
    ),
    RuntimeScenario(
        scenario_id="RT-06",
        blueprint_line=(
            "RT-06 `s2s_cloud` model attempts a diagnostic sentence — output-transcript "
            "monitor catches it, retraction turn is spoken, incident logged; scenario "
            "must also pass in `cascade_fast` where PolicyGuard blocks before TTS"
        ),
        covered_by=(
            "tests/voice/test_invariants.py"
            "::test_policyguard_blocks_a_diagnosis_before_it_reaches_the_synthesiser",
            "tests/voice/test_policyguard_precision.py::test_a_genuine_diagnosis_claim_is_still_caught",
        ),
        gaps=(
            "the two profiles this line names were deleted by files/00 §0b and "
            "CLAUDE.md invariant 19; the surviving clause — PolicyGuard blocks before "
            "TTS — is what is held, in the two profiles that exist",
            "'output-transcript monitor' and 'retraction turn': a monitor over a "
            "speech-to-speech model's own output presupposes such a model, and the "
            "retraction sentence is unauthored patient copy",
        ),
    ),
    RuntimeScenario(
        scenario_id="RT-07",
        blueprint_line=(
            "RT-07 YELLOW rule fires — spoken only at the insertion window, never preempting"
        ),
        covered_by=(
            "tests/voice/test_red_preempt_only.py::test_a_rules_engine_yellow_may_not_preempt",
            "tests/voice/test_red_preempt_only.py"
            "::test_a_yellow_result_goes_to_the_insertion_scheduler_not_the_preempt_path",
            "tests/voice/test_invariants.py::test_rt07_a_yellow_waits_for_the_window_a_red_does_not",
        ),
    ),
    RuntimeScenario(
        scenario_id="RT-08",
        blueprint_line=(
            'RT-08 patient says "bir dakika, hemşireyle konuşuyorum" — backchannel '
            "suppressed, turn detector holds, no question asked until they return"
        ),
        covered_by=(
            "tests/voice/test_talker_session.py"
            "::test_a_span_inside_the_agents_own_playback_is_refused",
            "tests/voice/test_insertion_window.py::test_speech_is_held_while_the_patient_is_talking",
        ),
        gaps=(
            "'turn detector holds, no question asked until they return' — the Talker's "
            "take_turn speaks the next step unconditionally; the VAD/turn-detector hold "
            "is the LiveKit Agents entrypoint's, which is INT-095 and does not exist "
            "yet. Only the Backend-speech half of the hold is built (InsertionScheduler)",
        ),
    ),
)


def scenario(scenario_id: str) -> RuntimeScenario:
    """The scenario with this id, or a ``KeyError`` naming what exists."""
    for candidate in RUNTIME_SCENARIOS:
        if candidate.scenario_id == scenario_id:
            return candidate
    raise KeyError(
        f"{scenario_id!r} is not a transcribed runtime scenario; files/04 line 204 "
        f"defines {[s.scenario_id for s in RUNTIME_SCENARIOS]}"
    )
