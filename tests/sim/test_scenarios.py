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

**Both intake modes, and four patients who break the turn order.** Every
scenario runs in Hızlı and in Detaylı — files/02 §2's *"same engine,
different protocol profile"*, realised as a ``visit_type`` pack rather than a
flag, because the engine has no mode to read — and the pair is asserted for
composition (Detaylı adds, never removes; the obligation set may grow and may
not shrink; a longer session does not move the determination) and never for a
turn budget, which is an open clinical decision (HB-C5).
:class:`TestHardPersonasExist` and the four classes after it cover the shapes
a happy-path script never produces: an answer to a different question, a
disclosure after the question closed, a reversal of an earlier answer, and a
patient who says everything in one word.
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
    UnboundReason,
    UnknownSlotInScript,
    free_text_critical_path_steps,
    run_scenario,
)
from intake_voice_runtime.clinical_agent import MAX_CLARIFICATION_ATTEMPTS
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import StepKind
from intake_voice_runtime.talker.registry import TALKER_TOOLS
from personas import PERSONAS, Literacy, Persona, ScriptedAnswer, SubjectRole
from protocol import IntakeMode, sim_protocol
from protocols.locale_text import entry_for
from protocols.types import EK4Level
from scenarios import SCENARIOS, ClinicalContentBlocked, Scenario

SIM_DIR = Path(__file__).resolve().parent
PROFILES = (VoiceProfile.TYPED, VoiceProfile.RESIDENCY_TR)


def _both(scenario: Scenario, persona: Persona) -> tuple[SimResult, SimResult]:
    return tuple(  # type: ignore[return-value]
        run_scenario(scenario, persona, profile=profile) for profile in PROFILES
    )


def _run(
    scenario_id: str,
    *,
    profile: VoiceProfile = VoiceProfile.TYPED,
    persona_id: str | None = None,
    mode: IntakeMode = IntakeMode.FAST,
) -> SimResult:
    scenario = SCENARIOS[scenario_id]
    persona = PERSONAS[persona_id or scenario.persona_ids[0]]
    return run_scenario(scenario, persona, profile=profile, mode=mode)


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
        locale = sim_protocol().locale
        for scenario in SCENARIOS.values():
            result = run_scenario(
                scenario,
                PERSONAS[scenario.persona_ids[0]],
                profile=VoiceProfile.RESIDENCY_TR,
            )
            for spoken in result.played:
                authored = by_id[spoken.origin_id]
                if spoken.kind is StepKind.FOLLOW_UP:
                    assert spoken.text_tr == entry_for(authored.follow_up_tr, locale)
                elif spoken.kind is StepKind.CONFIRM:
                    assert spoken.text_tr == authored.confirm_tr
                else:
                    assert spoken.text_tr == entry_for(authored.ask_tr, locale)

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
        locale = sim_protocol().locale
        instruments = sim_protocol().instruments
        assert instruments
        for instrument in instruments:
            assert instrument.voice is not None
            assert instrument.voice.allow_paraphrase is not None
            assert entry_for(instrument.voice.allow_paraphrase, locale) is False
            for item in instrument.items:
                assert entry_for(item.allow_paraphrase, locale) is False

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


# ---------------------------------------------------------------------------
# 13. the two intake modes — "same engine, different protocol profile"
# ---------------------------------------------------------------------------


class TestFastAndDetailedMode:
    """files/02 §2, verbatim: *"The two intake modes (same engine, different
    protocol profile)"*, and *"Both modes run the Protocol Registry:
    ``base.intake`` → ``specialty.*`` → ``visit_type.*`` → patient overlays"*.

    So the mode is **not** a flag the engine reads — there is no ``mode``
    parameter on ``IntakeEngine`` and the plan builder refuses the GuardExpr
    whitelist that would carry one (INT-081). The mode is which pack the
    registry resolved, and the simulator models it that way: Hızlı runs the
    synthetic base pack, Detaylı runs a ``visit_type`` pack that extends it
    with the *"+ full specialty module, ROS, PMH/FH/SH deltas"* shape of
    files/02 §2's Content row.

    What the suite can and cannot assert about the pair is the point. It can
    assert **composition** — that Detaylı adds and never removes, that no
    mandated question survives in one mode and vanishes in the other, and
    that lengthening the session does not move the triage result for the same
    answers. It cannot assert the **turn budget**: files/02 §2's ≤ 14 / ≤ 18
    pair collides with its own content list in the same table, and that is an
    open clinical decision (HUMAN_BLOCKERS **HB-C5**). No number is asserted
    here.
    """

    def test_the_two_modes_are_exactly_the_two_the_session_schema_names(self) -> None:
        # clinical_schemas.session.SessionState.mode is Literal["fast",
        # "detailed"] (files/04 §5 meta.mode). A third simulator mode would be
        # a mode no session could ever record.
        assert {mode.value for mode in IntakeMode} == {"fast", "detailed"}

    def test_detailed_resolves_a_longer_chain_than_fast(self) -> None:
        fast = sim_protocol(IntakeMode.FAST)
        detailed = sim_protocol(IntakeMode.DETAILED)
        assert len(detailed.chain) > len(fast.chain)
        assert fast.pack_id in detailed.chain

    @pytest.mark.parametrize("scenario_id", list(SCENARIOS))
    def test_every_scenario_runs_in_both_modes(self, scenario_id: str) -> None:
        scenario = SCENARIOS[scenario_id]
        for persona_id in scenario.persona_ids:
            for mode in IntakeMode:
                result = run_scenario(
                    scenario,
                    PERSONAS[persona_id],
                    profile=VoiceProfile.TYPED,
                    mode=mode,
                )
                assert result.mode is mode
                assert result.termination is Termination.FRONTIER_EMPTY

    @pytest.mark.parametrize("scenario_id", list(SCENARIOS))
    def test_typed_and_mock_voice_agree_in_detailed_mode_too(self, scenario_id: str) -> None:
        # The parity of ADR-010 is a property of both modes, not only of the
        # short one — a longer session is exactly where a channel could drift.
        scenario = SCENARIOS[scenario_id]
        for persona_id in scenario.persona_ids:
            typed, voiced = (
                run_scenario(
                    scenario,
                    PERSONAS[persona_id],
                    profile=profile,
                    mode=IntakeMode.DETAILED,
                )
                for profile in PROFILES
            )
            assert typed.states == voiced.states
            assert typed.values == voiced.values
            assert typed.coverage == voiced.coverage
            assert typed.triage.result == voiced.triage.result

    def test_detailed_asks_a_strict_superset_of_what_fast_asks(self) -> None:
        # files/02 §2's Content row is written as "+": detailed is fast plus
        # the specialty module, ROS and the history deltas. A mode that
        # *replaced* questions would be a second protocol wearing the same
        # name.
        fast = _run("IM-01", mode=IntakeMode.FAST)
        detailed = _run("IM-01", mode=IntakeMode.DETAILED)
        assert set(fast.asked) < set(detailed.asked)

    def test_no_mandated_question_is_obliged_in_one_mode_and_absent_in_the_other(self) -> None:
        # The obligation set may grow with the mode; it may not shrink. A
        # must_ask that fast owes and detailed does not would mean the longer
        # session quietly dropped a clinician-mandated question.
        for scenario in SCENARIOS.values():
            persona = PERSONAS[scenario.persona_ids[0]]
            fast = run_scenario(scenario, persona, profile=VoiceProfile.TYPED)
            detailed = run_scenario(
                scenario, persona, profile=VoiceProfile.TYPED, mode=IntakeMode.DETAILED
            )
            assert set(fast.coverage.obliged) <= set(detailed.coverage.obliged)

    def test_lengthening_the_session_does_not_move_the_triage_result(self) -> None:
        # The added Detaylı section feeds no rule, so the same answers must
        # produce the same determination in both modes. If this ever fails,
        # either a rule started reading a mode-only slot or the mode changed
        # an answer — both are defects, and neither is visible from the
        # coverage figures.
        for scenario_id in ("IM-01", "IM-04", "IM-03", "IM-02"):
            fast = _run(scenario_id, mode=IntakeMode.FAST)
            detailed = _run(scenario_id, mode=IntakeMode.DETAILED)
            assert fast.triage.result.level is detailed.triage.result.level
            assert [fire.id for fire in fast.triage.result.rules] == [
                fire.id for fire in detailed.triage.result.rules
            ]

    def test_the_detailed_only_questions_are_answerable_without_reading(self) -> None:
        # files/02 §3's low-literacy path is a property of the product, not of
        # the short mode: the mode that adds questions is the one that could
        # quietly add a free-text one.
        assert free_text_critical_path_steps(sim_protocol(IntakeMode.DETAILED)) == ()

    def test_the_control_persona_leaves_nothing_mandated_outstanding_in_either_mode(self) -> None:
        for mode in IntakeMode:
            result = _run("IM-01", mode=mode)
            assert result.coverage.outstanding == ()
            assert result.coverage.ratio == 1


# ---------------------------------------------------------------------------
# 14. the hard personas — answers that are not answers to the question asked
# ---------------------------------------------------------------------------


class TestHardPersonasExist:
    """The four conversational shapes a simulator that only walks the happy
    path certifies nothing about, each with a persona and each with a run."""

    def test_a_persona_answers_a_different_question_than_the_one_asked(self) -> None:
        assert any(persona.topic_shifts for persona in PERSONAS.values())

    def test_a_persona_discloses_after_the_question_already_closed(self) -> None:
        assert any(persona.volunteers_late for persona in PERSONAS.values())

    def test_a_persona_contradicts_its_own_earlier_answer(self) -> None:
        assert any(persona.contradicts_earlier_answer for persona in PERSONAS.values())

    def test_a_persona_answers_telegraphically(self) -> None:
        assert any(persona.telegraphic for persona in PERSONAS.values())


class TestAnswerToADifferentQuestion:
    """P15 answers a question that was not asked.

    This is the dangerous shape and it is not the same as being unreadable:
    the reply parses, it means something, and a recorded extraction binds it
    — to the wrong slot. Nothing asks for a clarification, because from the
    extraction's point of view nothing went wrong.
    """

    @staticmethod
    def _result() -> SimResult:
        return _run("IM-13", persona_id="P15-answers-a-different-question")

    def test_the_question_that_was_asked_is_never_resolved(self) -> None:
        result = self._result()
        assert result.states["ziyaret.basvuru_nedeni"] is AnswerState.ASKED_PENDING

    def test_and_it_is_never_asked_again_because_nothing_reported_a_problem(self) -> None:
        result = self._result()
        assert result.asked.count("ziyaret.basvuru_nedeni") == 1
        assert not [gap for gap in result.data_gaps if gap == "ziyaret.basvuru_nedeni"]

    def test_the_answer_it_gave_instead_is_dropped_rather_than_stored(self) -> None:
        result = self._result()
        dropped = {
            update.ref
            for update in result.unbound_updates
            if update.reason is UnboundReason.NEVER_ASKED
        }
        assert "oyku.belirti_var" in dropped

    def test_the_mandated_question_stays_visible_as_an_outstanding_obligation(self) -> None:
        result = self._result()
        assert "ziyaret.basvuru_nedeni" in result.coverage.outstanding
        assert result.coverage.ratio is not None
        assert result.coverage.ratio < 1

    def test_the_session_still_terminates(self) -> None:
        assert self._result().termination is Termination.FRONTIER_EMPTY


class TestDisclosureAfterTheQuestionClosed:
    """P16 volunteers the trigger three turns after its question closed.

    The persona answers ``ziyaret.basvuru_nedeni`` with the calm code, and
    then — while answering a later step — says the trigger code instead. Had
    it bound, the synthetic RED rule's first conjunct would be satisfied and
    IM-04 proves the rule fires when it is. It does not bind: files/13 §9.6
    makes the engine under-bind by construction, so a question that already
    closed absorbs nothing.

    Recorded as the two-sided pair it is, rather than as a claim about which
    behaviour is right. Binding it would make a note read as *elicited* what
    was volunteered; not binding it means a late disclosure of the trigger
    leaves no trace in the session state at all.
    """

    @staticmethod
    def _result() -> SimResult:
        return _run("IM-05", persona_id="P16-discloses-after-the-question-closed")

    def test_the_earlier_answer_stands_and_the_late_one_is_dropped(self) -> None:
        result = self._result()
        assert result.values["ziyaret.basvuru_nedeni"] == "sentetik_sakin"
        late = [
            update
            for update in result.unbound_updates
            if update.ref == "ziyaret.basvuru_nedeni"
            and update.reason is UnboundReason.ALREADY_RESOLVED
        ]
        assert late
        assert all(update.differs_from_bound for update in late)

    def test_the_session_stays_green_although_the_patient_said_the_trigger(self) -> None:
        result = self._result()
        assert result.triage.result.level is TriageLevel.GREEN
        assert result.triage.result.rules == ()
        assert result.triage.action is None

    def test_and_the_same_value_arriving_on_its_own_turn_does_fire_the_rule(self) -> None:
        # The other side of the control. Without this the test above would
        # pass just as well if the rule were broken. The two runs differ in
        # exactly one thing: WHEN the trigger was said.
        armed = _run("IM-04")
        assert armed.triage.result.level is TriageLevel.RED
        assert [fire.id for fire in armed.triage.result.rules] == ["rf.sentetik_sim_kirmizi"]

    def test_nothing_in_the_session_state_records_that_it_was_said(self) -> None:
        # Not a gap, not a follow-up, not a contested value: the disclosure
        # is visible only in the simulator's own transcript.
        result = self._result()
        assert "ziyaret.basvuru_nedeni" not in result.data_gaps
        assert "ziyaret.basvuru_nedeni" not in result.final_snapshot.invalidated
        assert result.states["ziyaret.basvuru_nedeni"] is AnswerState.ASKED_PRESENT


class TestContradictionOfAnEarlierAnswer:
    """P17 reverses an answer it gave earlier in the same session.

    ``AnswerState.CONTESTED`` exists for exactly this (files/13 §9.3: *"
    CONTESTED keeps both answers"*) and ``coverage.COVERED_STATES`` counts
    it. Nothing in the engine assigns it, so the reversal is dropped and the
    first answer stands unmarked.
    """

    @staticmethod
    def _result() -> SimResult:
        return _run("IM-11", persona_id="P17-contradicts-an-earlier-answer")

    def test_the_reversal_is_dropped_and_the_first_answer_stands(self) -> None:
        result = self._result()
        assert result.values["oyku.belirti_var"] is True
        assert result.states["oyku.belirti_var"] is AnswerState.ASKED_PRESENT

    def test_the_contradiction_is_recorded_by_the_simulator_and_by_nothing_else(self) -> None:
        result = self._result()
        contradictions = [
            update
            for update in result.unbound_updates
            if update.ref == "oyku.belirti_var" and update.differs_from_bound
        ]
        assert contradictions
        assert AnswerState.CONTESTED not in set(result.states.values())

    def test_the_slot_still_counts_as_covered_on_the_answer_that_was_taken_back(self) -> None:
        result = self._result()
        assert "oyku.belirti_var" in result.coverage.covered


class TestTelegraphicAnswers:
    """P18 answers in one word. Nothing downstream can tell.

    The point is the boundary INT-083 built: the transcript is data the
    extraction reads, and it is the extraction — not the sentence — that
    binds. A one-word reply and a fluent paragraph carrying the same recorded
    extraction must therefore produce byte-identical clinical state, and the
    run proves the simulator is not smuggling meaning through its transcripts.
    """

    def test_a_one_word_reply_reaches_the_same_state_as_a_fluent_one(self) -> None:
        terse = _run("IM-10", persona_id="P18-telegraphic-answers")
        fluent = _run("IM-01")
        assert terse.states == fluent.states
        assert terse.values == fluent.values
        assert terse.coverage == fluent.coverage
        assert terse.triage.result.level is fluent.triage.result.level

    def test_the_replies_really_are_telegraphic(self) -> None:
        persona = PERSONAS["P18-telegraphic-answers"]
        assert persona.telegraphic
        spoken = [answer.transcript_tr for answer in persona.answers.values()]
        assert spoken
        assert all(len(text.split()) <= 2 for text in spoken)


class TestUnboundUpdates:
    """Every dropped update is accounted for, and the clean run drops none."""

    def test_the_control_persona_has_nothing_dropped(self) -> None:
        assert _run("IM-01").unbound_updates == ()

    def test_every_dropped_update_names_a_reason_from_the_closed_set(self) -> None:
        for scenario in SCENARIOS.values():
            for persona_id in scenario.persona_ids:
                result = run_scenario(scenario, PERSONAS[persona_id], profile=VoiceProfile.TYPED)
                for update in result.unbound_updates:
                    assert update.reason in set(UnboundReason)
                    assert update.ref in result.states

    def test_a_dropped_update_never_reaches_the_log(self) -> None:
        # CLAUDE.md invariant 6: the drop is recorded by ref, never by value.
        result = _run("IM-05", persona_id="P16-discloses-after-the-question-closed")
        assert result.unbound_updates
        for line in result.log:
            assert "sentetik_tetik" not in line

    def test_every_reason_in_the_closed_set_is_reached_by_a_persona(self) -> None:
        # A reason nothing reaches is a rule nobody is testing. Each of the
        # five is produced by a different persona, so the set cannot grow
        # without a patient who provokes it.
        reached = {
            update.reason
            for scenario in SCENARIOS.values()
            for persona_id in scenario.persona_ids
            for mode in IntakeMode
            for update in run_scenario(
                scenario, PERSONAS[persona_id], profile=VoiceProfile.TYPED, mode=mode
            ).unbound_updates
        }
        assert reached == set(UnboundReason)

    def test_a_value_offered_for_a_slot_the_engine_gave_up_on_is_dropped(self) -> None:
        # The pair with IM-06: after two failed attempts the slot is UNCLEAR
        # and has left the frontier, so the patient saying it clearly four
        # steps later has nowhere to put it — no third attempt, and no way in
        # from the side either.
        result = _run("IM-06")
        abandoned = [
            update for update in result.unbound_updates if update.reason is UnboundReason.ABANDONED
        ]
        assert [update.ref for update in abandoned] == ["oyku.seyir"]
        assert "oyku.seyir" in result.data_gaps
        assert "oyku.seyir" in result.coverage.outstanding

    def test_a_script_naming_a_slot_this_protocol_lacks_is_refused(self) -> None:
        # The guard that keeps every assertion above honest: apply_extraction
        # ignores an unknown reference in silence, so without this a fixture
        # typo would make a scenario pass by binding nothing at all.
        persona = PERSONAS["P01-self-adult-cooperative"]
        broken = persona.model_copy(
            update={
                "answers": {
                    **persona.answers,
                    "ziyaret.bildiren_rol": ScriptedAnswer(
                        transcript_tr="Sentetik yanlış alan.",
                        slot_updates={"oyku.olmayan_alan": True},
                    ),
                },
                "topic_shifts": True,
            }
        )
        with pytest.raises(UnknownSlotInScript):
            run_scenario(SCENARIOS["IM-01"], broken, profile=VoiceProfile.TYPED)
