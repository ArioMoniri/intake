"""INT-082 — the headless patient simulator: personas × scenarios IM-01…IM-14.

Acceptance line under test, verbatim (docs/backlog/issues.yaml INT-082):
  "12+ scripted personas incl. proxy, low-literacy, crisis, oncology; runs in
   typed and mock voice; used by CI"

**What the blueprint actually supplies, and what it does not.** files/04 §6
is the source of record for the simulator, and it names exactly three IM
scenarios — ``IM-02``, ``IM-09``, ``IM-14`` — inside a "starter set (40)"
that is a list of examples, not a roster. files/10 §9 cites ``IM-14`` once
more, as the test for the companion/guardian row. There is no definition
anywhere in ``files/`` for IM-01, IM-03…IM-08 or IM-10…IM-13. Those eleven
ids are therefore carried as **mechanism** scenarios: each names a property
the blueprint does write down elsewhere (files/13 §11.1, §11.3; files/09 §3;
CLAUDE.md invariants 1, 3, 6, 9, 10), and each carries
``blueprint_line=None`` so a reader can tell a transcription from a
mechanism at a glance. Not one of them invents a clinical presentation.

**Every scenario's clinical content is empty and gated.** files/04 §6 makes
a scenario's "hidden truth" symptoms, meds and red flags, and its expected
output a triage level. Every red-flag family in this repository is
``status: draft_needs_source`` (HUMAN_BLOCKERS HB-C1, HB-C2, HB-C7), the
crisis escalation policy does not exist (HB-C8), the paediatric set does not
exist (HB-C3), and C-SSRS is licence-blocked (HB-L2). So
:meth:`Scenario.clinical_truth` **raises** for all fourteen — the gate is
wired, it fails closed, and the content is left empty (HUMAN_BLOCKERS
Rule 2). The pack the simulator runs on is synthetic throughout
(files/04 §7: "simulator transcripts are synthetic").

**Invariant 1 is structural here, not asserted.** A simulated patient must
not be able to produce a RED by claiming one. No persona, answer or scenario
type in this package carries a level, a register or a route; the only
producer of a triage result in the whole simulator is
:func:`protocols.triage.evaluate_triage` over the resolved pack's own rules.
:class:`TestTriageComesOnlyFromRules` asserts both halves, including the
near-miss negative control one field away from the RED gate.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, TriageLevel
from driver import (
    MAX_TURNS,
    SimResult,
    Termination,
    free_text_critical_path_steps,
    run_scenario,
)
from intake_voice_runtime.clinical_agent import MAX_CLARIFICATION_ATTEMPTS
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import StepKind
from intake_voice_runtime.talker.registry import TALKER_TOOLS
from personas import PERSONAS, Literacy, Persona, ScriptedAnswer, SubjectRole
from protocol import sim_protocol
from protocols.types import EK4Level
from scenarios import SCENARIOS, ClinicalContentBlocked, Scenario

SIM_DIR = Path(__file__).resolve().parent
PROFILES = (VoiceProfile.TYPED, VoiceProfile.RESIDENCY_TR)


def _both(scenario: Scenario, persona: Persona) -> tuple[SimResult, SimResult]:
    return tuple(  # type: ignore[return-value]
        run_scenario(scenario, persona, profile=profile) for profile in PROFILES
    )


def _run(scenario_id: str, *, profile: VoiceProfile = VoiceProfile.TYPED) -> SimResult:
    scenario = SCENARIOS[scenario_id]
    persona = PERSONAS[scenario.persona_ids[0]]
    return run_scenario(scenario, persona, profile=profile)


# ---------------------------------------------------------------------------
# 1. the roster: fourteen scenarios, twelve-plus personas
# ---------------------------------------------------------------------------


class TestRoster:
    def test_the_fourteen_im_ids_are_present_and_no_others(self) -> None:
        assert tuple(SCENARIOS) == tuple(f"IM-{n:02d}" for n in range(1, 15))

    def test_there_are_at_least_twelve_scripted_personas(self) -> None:
        assert len(PERSONAS) >= 12

    def test_the_four_personas_the_acceptance_names_exist(self) -> None:
        # "12+ scripted personas incl. proxy, low-literacy, crisis, oncology"
        roles = {persona.subject_role for persona in PERSONAS.values()}
        assert SubjectRole.PROXY in roles
        assert any(p.literacy is Literacy.LOW for p in PERSONAS.values())
        assert any(p.crisis_path for p in PERSONAS.values())
        assert any("overlay.oncology_patient" in p.overlay_refs for p in PERSONAS.values())

    def test_every_persona_is_exercised_by_at_least_one_scenario(self) -> None:
        used = {pid for scenario in SCENARIOS.values() for pid in scenario.persona_ids}
        assert used == set(PERSONAS)

    def test_every_scenario_names_personas_that_exist(self) -> None:
        for scenario in SCENARIOS.values():
            assert scenario.persona_ids
            for persona_id in scenario.persona_ids:
                assert persona_id in PERSONAS

    def test_every_scenario_says_what_it_proves(self) -> None:
        for scenario in SCENARIOS.values():
            assert scenario.proves.strip()


# ---------------------------------------------------------------------------
# 2. blueprint fidelity: transcribed, or honestly marked as mechanism
# ---------------------------------------------------------------------------


class TestBlueprintFidelity:
    #: The only IM scenarios files/ defines, transcribed verbatim.
    TRANSCRIBED = {
        "IM-02": "IM-02 uncontrolled HTN with headache (YELLOW)",
        "IM-09": "IM-09 passive SI on PHQ-9 (YELLOW + safety script)",
        "IM-14": "IM-14 companion reporting for father with dementia",
    }

    def test_the_three_defined_scenarios_carry_the_blueprint_line_verbatim(self) -> None:
        for scenario_id, line in self.TRANSCRIBED.items():
            scenario = SCENARIOS[scenario_id]
            assert scenario.blueprint_line == line
            assert scenario.blueprint_ref is not None

    def test_the_blueprint_line_is_actually_in_files_04(self) -> None:
        source = (SIM_DIR.parents[1] / "files" / "04_CLINICAL_PROTOCOLS.md").read_text(
            encoding="utf-8"
        )
        for line in self.TRANSCRIBED.values():
            assert line in source

    def test_a_scenario_with_no_blueprint_line_says_so_and_names_its_mechanism(self) -> None:
        undefined = [s for s in SCENARIOS.values() if s.blueprint_line is None]
        assert len(undefined) == 11
        for scenario in undefined:
            assert scenario.blueprint_ref is None
            assert scenario.mechanism_ref.strip()

    def test_every_scenario_refuses_to_supply_clinical_content(self) -> None:
        # HUMAN_BLOCKERS Rule 2: the mechanism is built, the gate is wired,
        # it fails closed, the content is empty.
        for scenario in SCENARIOS.values():
            assert scenario.blockers
            with pytest.raises(ClinicalContentBlocked):
                scenario.clinical_truth()

    def test_every_blocker_id_exists_in_human_blockers(self) -> None:
        source = (SIM_DIR.parents[1] / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
        for scenario in SCENARIOS.values():
            for blocker in scenario.blockers:
                assert f"**{blocker}**" in source


# ---------------------------------------------------------------------------
# 3. "runs in typed and mock voice"
# ---------------------------------------------------------------------------


class TestTypedAndMockVoice:
    @pytest.mark.parametrize("scenario_id", list(SCENARIOS))
    def test_every_scenario_runs_in_both_profiles(self, scenario_id: str) -> None:
        scenario = SCENARIOS[scenario_id]
        for persona_id in scenario.persona_ids:
            typed, voiced = _both(scenario, PERSONAS[persona_id])
            assert typed.profile is VoiceProfile.TYPED
            assert voiced.profile is VoiceProfile.RESIDENCY_TR

    @pytest.mark.parametrize("scenario_id", list(SCENARIOS))
    def test_typed_and_mock_voice_reach_the_same_clinical_state(self, scenario_id: str) -> None:
        # ADR-010 / files/02: typed is keyboard *parity*, not a lesser mode.
        # The channel may differ in what is spoken; it may not differ in what
        # is recorded.
        scenario = SCENARIOS[scenario_id]
        for persona_id in scenario.persona_ids:
            typed, voiced = _both(scenario, PERSONAS[persona_id])
            assert typed.states == voiced.states
            assert typed.values == voiced.values
            assert typed.data_gaps == voiced.data_gaps
            assert typed.coverage == voiced.coverage
            assert typed.triage.result == voiced.triage.result

    def test_the_typed_profile_touches_no_speech_path_at_all(self) -> None:
        for scenario in SCENARIOS.values():
            result = run_scenario(
                scenario, PERSONAS[scenario.persona_ids[0]], profile=VoiceProfile.TYPED
            )
            assert result.clip_fetches == ()
            assert result.synthesized == ()
            assert result.played == ()

    def test_the_mock_voice_profile_speaks_every_step_it_asks(self) -> None:
        result = _run("IM-01", profile=VoiceProfile.RESIDENCY_TR)
        assert result.played
        assert len(result.played) == len(result.asked)


# ---------------------------------------------------------------------------
# 4. invariant 1 — RED/YELLOW only from packages/protocols/triage
# ---------------------------------------------------------------------------

#: Names a simulated patient must not be able to reach. A persona that could
#: name a level could assert a RED, which is exactly what invariant 1 forbids.
_LEVEL_NAMES = frozenset(
    {
        "TriageLevel",
        "EK4Level",
        "RulesTriageResult",
        "RuleFire",
        "RedRegister",
        "RedFlagRoute",
        "CandidateFlag",
        "LlmCandidateTriage",
    }
)

#: The simulator modules a patient's script is authored in. `driver.py` is
#: excluded because it is the module that *calls* the rules engine.
_PATIENT_AUTHORED_MODULES = ("personas.py", "scenarios.py", "doubles.py")


class TestTriageComesOnlyFromRules:
    def test_no_patient_authored_module_can_even_name_a_triage_level(self) -> None:
        offenders: dict[str, set[str]] = {}
        for name in _PATIENT_AUTHORED_MODULES:
            tree = ast.parse((SIM_DIR / name).read_text(encoding="utf-8"))
            hits = {
                node.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Name) and node.id in _LEVEL_NAMES
            } | {
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and node.attr in _LEVEL_NAMES
            }
            if hits:
                offenders[name] = hits
        assert offenders == {}

    def test_a_scripted_answer_carries_no_level_field(self) -> None:
        forbidden = {"level", "triage", "ek4", "register", "route", "red", "yellow"}
        for model in (ScriptedAnswer, Persona, Scenario):
            assert not forbidden & set(model.model_fields)

    def test_the_driver_reaches_triage_only_through_the_rules_engine(self) -> None:
        tree = ast.parse((SIM_DIR / "driver.py").read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("protocols")
            for alias in node.names
        }
        assert "evaluate_triage" in imported
        assert not _LEVEL_NAMES & imported

    def test_red_arises_from_the_rules_on_the_simulated_answers(self) -> None:
        result = _run("IM-04")
        assert result.triage.result.level is TriageLevel.RED
        assert result.triage.ek4 is EK4Level.KIRMIZI_K2
        assert [fire.id for fire in result.triage.result.rules] == ["rf.sentetik_sim_kirmizi"]

    def test_the_near_miss_control_one_field_away_does_not_go_red(self) -> None:
        # Same persona shape, same wording, one differing conjunct — the case
        # that starts firing if the gate is ever loosened.
        near = _run("IM-03")
        red = _run("IM-04")
        differing = {
            key
            for key in red.values.keys() | near.values.keys()
            if red.values.get(key) != near.values.get(key)
        }
        assert differing == {"ziyaret.basvuru_nedeni"}
        assert near.triage.result.level is TriageLevel.GREEN
        assert near.triage.result.rules == ()
        assert near.triage.action is None

    def test_yellow_also_comes_only_from_a_rule(self) -> None:
        result = _run("IM-02")
        assert result.triage.result.level is TriageLevel.YELLOW
        assert [fire.id for fire in result.triage.result.rules] == ["rf.sentetik_sim_sari"]

    def test_a_red_resolves_an_action_for_all_three_locations(self) -> None:
        # CLAUDE.md invariant 21: route × register × location, no default.
        scenario = SCENARIOS["IM-04"]
        persona = PERSONAS[scenario.persona_ids[0]]
        actions = {
            location: run_scenario(
                scenario, persona, profile=VoiceProfile.TYPED, location=location
            ).triage
            for location in RedLocation
        }
        for evaluation in actions.values():
            assert evaluation.result.level is TriageLevel.RED
            assert evaluation.action is not None
        # under ON_SITE the 112 affordance is absent, not de-emphasised
        assert actions[RedLocation.REMOTE].action.show_112 is True  # type: ignore[union-attr]
        assert actions[RedLocation.ON_SITE].action.show_112 is False  # type: ignore[union-attr]
        assert actions[RedLocation.UNKNOWN].action.ask_one_tr  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# 5. invariant 3 — raw audio never touches disk
# ---------------------------------------------------------------------------


class TestAudioNeverTouchesDisk:
    @pytest.mark.parametrize("scenario_id", list(SCENARIOS))
    def test_the_mock_voice_run_opens_no_file_for_writing(self, scenario_id: str) -> None:
        result = _run(scenario_id, profile=VoiceProfile.RESIDENCY_TR)
        assert result.disk_writes == ()

    def test_the_session_retains_no_audio_buffer_when_it_ends(self) -> None:
        result = _run("IM-01", profile=VoiceProfile.RESIDENCY_TR)
        assert result.retained_frames == 0
        assert result.retained_bytes_in_doubles == 0

    def test_the_probe_would_notice_a_write(self, tmp_path: Path) -> None:
        # A gate that cannot fail is not a gate.
        from doubles import record_disk_writes

        with record_disk_writes() as writes:
            (tmp_path / "sentetik.bin").write_bytes(b"x")
        assert writes


# ---------------------------------------------------------------------------
# 6. invariant 9 — six tools, and no await of Backend Work
# ---------------------------------------------------------------------------


class TestSixToolBoundary:
    def test_the_driver_only_ever_calls_the_six_tools(self) -> None:
        for scenario in SCENARIOS.values():
            for persona_id in scenario.persona_ids:
                result = run_scenario(
                    scenario, PERSONAS[persona_id], profile=VoiceProfile.RESIDENCY_TR
                )
                assert set(result.tool_calls) <= TALKER_TOOLS

    def test_the_simulator_registers_no_seventh_tool(self) -> None:
        result = _run("IM-01", profile=VoiceProfile.RESIDENCY_TR)
        assert result.tool_surface == TALKER_TOOLS

    def test_submitting_an_utterance_returns_a_ticket_rather_than_an_awaitable(self) -> None:
        result = _run("IM-01", profile=VoiceProfile.RESIDENCY_TR)
        assert result.work_ids
        assert result.awaited_backend is False


# ---------------------------------------------------------------------------
# 7. invariant 10 — verbatim text_tr, paraphrase only where authored
# ---------------------------------------------------------------------------


class TestVerbatimSpeech:
    def test_every_spoken_step_matches_its_authored_turkish_exactly(self) -> None:
        by_id = {
            f"{section.id}.{slot.key}": slot.slot
            for section in sim_protocol().sections
            for slot in section.slots
        }
        for scenario in SCENARIOS.values():
            result = run_scenario(
                scenario,
                PERSONAS[scenario.persona_ids[0]],
                profile=VoiceProfile.RESIDENCY_TR,
            )
            for spoken in result.played:
                if spoken.kind is StepKind.FOLLOW_UP:
                    assert spoken.text_tr == by_id[spoken.origin_id].follow_up_tr
                elif spoken.kind is StepKind.CONFIRM:
                    assert spoken.text_tr == by_id[spoken.origin_id].confirm_tr
                else:
                    assert spoken.text_tr == by_id[spoken.origin_id].ask_tr

    def test_only_the_paraphrase_section_is_marked_paraphrasable(self) -> None:
        result = _run("IM-01", profile=VoiceProfile.RESIDENCY_TR)
        paraphrasable = {s.origin_id for s in result.played if s.kind is StepKind.PARAPHRASE_OK}
        assert paraphrasable == {"beklenti.beklenti_metni"}

    def test_a_repeat_re_asks_the_same_sentence_never_a_reworded_one(self) -> None:
        # files/03 §4.2: request_repeat_or_clarify re-asks verbatim.
        result = _run("IM-13", profile=VoiceProfile.RESIDENCY_TR)
        assert result.repeats
        for repeat in result.repeats:
            assert repeat.text_tr == repeat.original_text_tr

    def test_instrument_items_are_authored_unparaphrasable(self) -> None:
        instruments = sim_protocol().instruments
        assert instruments
        for instrument in instruments:
            assert instrument.voice is not None
            assert instrument.voice.allow_paraphrase is False
            for item in instrument.items:
                assert item.allow_paraphrase is False

    def test_one_question_per_turn(self) -> None:
        # files/04 §6 forbidden behaviours: never more than one question in a
        # turn. A turn that only reconciles a held extraction speaks nothing,
        # which is why this is "at most one" plus a total that ties every
        # spoken sentence back to exactly one asked step.
        for scenario in SCENARIOS.values():
            result = run_scenario(
                scenario,
                PERSONAS[scenario.persona_ids[0]],
                profile=VoiceProfile.RESIDENCY_TR,
            )
            for turn in result.turns:
                assert len(turn.spoken) <= 1
            assert sum(len(turn.spoken) for turn in result.turns) == len(result.asked)


# ---------------------------------------------------------------------------
# 8. invariant 6 — no PHI/PII in anything logged
# ---------------------------------------------------------------------------


class TestNoPhiInLogs:
    def test_the_run_log_carries_ids_only(self) -> None:
        for scenario in SCENARIOS.values():
            for persona_id in scenario.persona_ids:
                persona = PERSONAS[persona_id]
                result = run_scenario(scenario, persona, profile=VoiceProfile.RESIDENCY_TR)
                blob = "\n".join(result.log)
                assert persona.label_tr not in blob
                for turn in result.turns:
                    for reply in turn.replies:
                        assert reply.transcript_tr not in blob

    def test_the_log_never_carries_a_bound_slot_value(self) -> None:
        result = _run("IM-04", profile=VoiceProfile.RESIDENCY_TR)
        blob = "\n".join(result.log)
        for value in result.values.values():
            assert str(value) not in blob


# ---------------------------------------------------------------------------
# 9. the UNCLEAR must-ask question — the finding this issue was asked to make
#    visible
# ---------------------------------------------------------------------------


class TestUnclearMustAsk:
    """files/13 §9.2 lists ``UNCLEAR`` among the frontier candidates; §11.1
    forbids a third attempt. INT-081 resolved it by dropping ``UNCLEAR`` from
    the frontier. That is safe for a detail slot. For a slot a **clinician
    marked ``must_ask``** it means a mandated question stops being asked, and
    the only thing standing between that and silence is whether the drop is
    recorded somewhere a human reads. These tests pin exactly where it shows
    and exactly where it does not.
    """

    def test_two_clarifications_then_the_slot_is_unclear_and_the_session_ends(self) -> None:
        result = _run("IM-06")
        assert result.termination is Termination.FRONTIER_EMPTY
        assert result.states["oyku.seyir"] is AnswerState.UNCLEAR
        assert "oyku.seyir" in result.data_gaps

    def test_the_mandated_question_is_asked_exactly_the_bounded_number_of_times(self) -> None:
        result = _run("IM-06")
        asks = [step_id for step_id in result.asked if step_id.startswith("oyku.seyir")]
        assert len(asks) == 1 + MAX_CLARIFICATION_ATTEMPTS
        assert asks[1:] == ["oyku.seyir/clarify/1", "oyku.seyir/clarify/2"]

    def test_the_dropped_must_ask_is_visible_in_coverage_not_silently_covered(self) -> None:
        result = _run("IM-06")
        assert "oyku.seyir" in result.coverage.obliged
        assert "oyku.seyir" in result.coverage.outstanding
        assert "oyku.seyir" not in result.coverage.covered
        assert result.coverage.ratio is not None
        assert result.coverage.ratio < 1

    def test_the_engine_snapshot_the_talker_reads_does_not_show_the_gap(self) -> None:
        # The finding, stated as a test rather than a comment: `EngineSnapshot`
        # carries version / next_step / awaiting / invalidated and nothing
        # else, so Layer A cannot see that a clinician-mandated question was
        # abandoned. It is visible to Layer B (data_gaps, must_ask_coverage),
        # which is what writes the note — so the gap reaches the clinician,
        # but nothing in the conversation can react to it.
        result = _run("IM-06")
        assert "oyku.seyir" not in result.final_snapshot.awaiting
        assert "oyku.seyir" not in result.final_snapshot.invalidated
        assert result.final_snapshot.next_step is None

    def test_the_section_holding_the_abandoned_must_ask_still_reports_done(self) -> None:
        # Also a finding: files/03 §5 defines section_done as "nothing offered
        # and nothing awaiting", and an UNCLEAR step is neither. A consumer
        # reading section_done alone would conclude the section completed.
        result = _run("IM-06")
        assert "oyku" in result.section_done


# ---------------------------------------------------------------------------
# 10. termination and the bounded clarification loop
# ---------------------------------------------------------------------------


class TestTermination:
    @pytest.mark.parametrize("scenario_id", list(SCENARIOS))
    def test_every_scenario_terminates_because_the_frontier_emptied(self, scenario_id: str) -> None:
        scenario = SCENARIOS[scenario_id]
        for persona_id in scenario.persona_ids:
            for profile in PROFILES:
                result = run_scenario(scenario, PERSONAS[persona_id], profile=profile)
                assert result.termination is Termination.FRONTIER_EMPTY
                assert len(result.turns) < MAX_TURNS

    @pytest.mark.parametrize("scenario_id", list(SCENARIOS))
    def test_no_slot_is_asked_more_often_than_the_clarification_bound(
        self, scenario_id: str
    ) -> None:
        scenario = SCENARIOS[scenario_id]
        for persona_id in scenario.persona_ids:
            result = run_scenario(scenario, PERSONAS[persona_id], profile=VoiceProfile.TYPED)
            counts: dict[str, int] = {}
            for step_id in result.asked:
                origin = step_id.split("/clarify/")[0]
                counts[origin] = counts.get(origin, 0) + 1
            assert max(counts.values()) <= 1 + MAX_CLARIFICATION_ATTEMPTS

    def test_work_remaining_never_grows_across_a_turn(self) -> None:
        for scenario in SCENARIOS.values():
            for persona_id in scenario.persona_ids:
                result = run_scenario(scenario, PERSONAS[persona_id], profile=VoiceProfile.TYPED)
                remaining = [turn.work_remaining for turn in result.turns]
                assert remaining == sorted(remaining, reverse=True)

    def test_the_strict_decrease_of_files_13_9_5_does_not_hold_every_turn(self) -> None:
        # The finding, pinned rather than described. files/13 §9.5 requires
        # every turn to strictly decrease |NOT_ASKED| + |queued re-entries|.
        # A clarification turn takes one step out of NOT_ASKED and puts one
        # re-entry into the queue, which is a wash — so the measure is
        # non-increasing, not strictly decreasing, and what actually bounds
        # the session is the two-attempt cap of §11.1 plus termination.
        result = _run("IM-06")
        remaining = [turn.work_remaining for turn in result.turns]
        assert any(before == after for before, after in zip(remaining, remaining[1:], strict=False))

    def test_the_session_ends_with_an_empty_frontier_not_an_empty_plan(self) -> None:
        # A gated-off step legitimately stays NOT_ASKED forever: its gate is
        # FALSE, so it never obliged anything. Termination is the frontier
        # emptying, which is what the loop asserts everywhere else.
        result = _run("IM-05")
        assert result.termination is Termination.FRONTIER_EMPTY
        assert result.final_snapshot.next_step is None


# ---------------------------------------------------------------------------
# 11. the paths the acceptance names by persona
# ---------------------------------------------------------------------------


class TestProxyPath:
    def test_the_proxy_scenario_records_who_is_answering_before_anything_else(self) -> None:
        # files/10 §9 companion/guardian row: "proxy flag on every record,
        # acknowledgement … scenario IM-14".
        scenario = SCENARIOS["IM-14"]
        for persona_id in scenario.persona_ids:
            result = run_scenario(scenario, PERSONAS[persona_id], profile=VoiceProfile.TYPED)
            assert result.asked[0] == "ziyaret.bildiren_rol"
            assert result.states["ziyaret.bildiren_rol"] is AnswerState.ASKED_PRESENT

    def test_a_proxy_persona_is_flagged_on_the_result(self) -> None:
        scenario = SCENARIOS["IM-14"]
        results = [
            run_scenario(scenario, PERSONAS[pid], profile=VoiceProfile.TYPED)
            for pid in scenario.persona_ids
        ]
        assert any(result.proxy_reported for result in results)
        assert any(result.third_party_present for result in results)


class TestLowLiteracyPath:
    def test_the_low_literacy_persona_never_meets_free_text_on_the_critical_path(self) -> None:
        # files/02 §3: full operation without reading; no free text anywhere
        # on the critical path; severity numeracy-free via ordinal anchors.
        assert free_text_critical_path_steps(sim_protocol()) == ()

    def test_the_free_text_gate_can_fail(self) -> None:
        from protocol import protocol_with_free_text_must_ask

        assert free_text_critical_path_steps(protocol_with_free_text_must_ask()) == (
            "oyku.serbest_metin",
        )

    def test_the_low_literacy_run_answers_every_gated_step_from_spoken_choices(self) -> None:
        result = _run("IM-10", profile=VoiceProfile.RESIDENCY_TR)
        chips = [s for s in result.played if s.kind is StepKind.CHOICE]
        assert chips
        for spoken in chips:
            assert spoken.choices_tr

    def test_the_persona_is_never_asked_whether_they_can_read(self) -> None:
        # files/02 §3: acquisition must be non-stigmatising — never ask
        # "okuyabiliyor musunuz?".
        result = _run("IM-10", profile=VoiceProfile.RESIDENCY_TR)
        for spoken in result.played:
            assert "okuyabiliyor" not in spoken.text_tr.lower()


class TestCrisisPath:
    def test_the_crisis_scenario_is_blocked_on_the_escalation_policy(self) -> None:
        scenario = SCENARIOS["IM-09"]
        assert "HB-C8" in scenario.blockers
        assert "HB-L2" in scenario.blockers
        with pytest.raises(ClinicalContentBlocked):
            scenario.clinical_truth()

    def test_the_screening_section_is_text_only_so_nothing_sensitive_is_spoken(self) -> None:
        # files/13 §13: screening and safeguarding content is text_only — no
        # clip, no speech, ever.
        section = next(s for s in sim_protocol().sections if s.id == "tarama")
        assert section.delivery.value == "text_only"

    def test_the_simulator_offers_no_instrument_step_because_none_is_compiled(self) -> None:
        # The instrument engine is INT-116; the IntakeEngine plans slots, not
        # questionnaire items. Asserted so the absence is recorded rather than
        # discovered later as a coverage hole.
        result = _run("IM-09")
        assert not [step_id for step_id in result.asked if step_id.startswith("SYN-OLCEK")]


class TestOncologyOverlay:
    def test_the_oncology_persona_carries_the_overlay_reference_but_no_content(self) -> None:
        scenario = SCENARIOS["IM-12"]
        persona = PERSONAS[scenario.persona_ids[0]]
        assert "overlay.oncology_patient" in persona.overlay_refs
        assert sim_protocol().overlays == ()
        assert "HB-C2" in scenario.blockers

    def test_an_overlay_never_removes_a_must_ask_step(self) -> None:
        # files/04 §2.3: overlays may add or tighten; they never remove a
        # question a clinician marked must_ask.
        baseline = _run("IM-01")
        oncology = _run("IM-12")
        assert set(baseline.coverage.obliged) <= set(oncology.coverage.obliged)


class TestDeltaMode:
    def test_a_confirmed_fact_is_confirmed_rather_than_re_asked(self) -> None:
        result = _run("IM-07")
        assert result.delta_mode == "on"
        confirms = [s for s in result.asked_kinds if s is StepKind.CONFIRM]
        assert confirms

    def test_contradicting_a_prefill_re_opens_the_full_ask(self) -> None:
        # files/09 §3 "full HPI only on change".
        result = _run("IM-08", profile=VoiceProfile.RESIDENCY_TR)
        confirm = next(s for s in result.played if s.kind is StepKind.CONFIRM)
        reasked = [
            s
            for s in result.played
            if s.origin_id == confirm.origin_id and s.kind is not StepKind.CONFIRM
        ]
        assert reasked


class TestAskAheadRace:
    def test_an_invalidated_step_drops_its_answer_rather_than_storing_it(self) -> None:
        # files/13 §11.3: the ask-ahead race is closed by discarding, never by
        # storing. Storing it would be fabricated clinical data.
        result = _run("IM-05")
        assert "oyku.ek_bilgi" in result.invalidated
        assert "oyku.ek_bilgi" not in result.values
        assert result.states["oyku.ek_bilgi"] is AnswerState.NOT_ASKED


class TestDecline:
    def test_a_declined_slot_is_not_counted_as_covered(self) -> None:
        # A finding, pinned: the IntakeEngine has no API that reaches
        # AnswerState.DECLINED or CONTESTED, though coverage.py counts both as
        # covering. A patient who declines therefore leaves the slot pending
        # forever rather than declined — visible as an outstanding obligation,
        # which is the safe direction, but not the state files/13 §9.3 names.
        result = _run("IM-11")
        assert result.states["tarama.tarama_onayi"] is AnswerState.ASKED_PENDING
        assert "tarama.tarama_onayi" in result.coverage.outstanding
        assert AnswerState.DECLINED not in set(result.states.values())
