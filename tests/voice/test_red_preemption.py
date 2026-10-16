"""INT-093 — the RED preemption path: stop ≤ 150 ms, e2e ≤ 300 ms, fake clocks.

Acceptance (docs/backlog/issues.yaml): *"only rules-engine RED carries
priority preempt; playback cancel and script start measured on fake clock"*.

Four blueprint sentences shape every test below.

1. **files/03 §4.6 invariant 4** — *"the RED script is pre-positioned on the
   device"* and triggered over the data channel, and *"the test changes too:
   it must assert the RED path touches no media transport"*. So the headline
   assertions here are structural, not only temporal: the path has no route to
   TTS, to the clip store or to ``play``, and the wire carries identifiers and
   axes only.
2. **CLAUDE.md invariant 21** — register × location, no defaults. ``SILENT``
   and ``DEFERRED_CLINICIAN`` must not speak, and under ``ON_SITE`` the 112
   affordance is absent through every carrier (INT-255).
3. **files/03 §4.3** — *"On RED: cancel playback ≤ 150 ms, play the cached RED
   script, emit ``emergency_interrupt``, notify clinic if connected."*
4. **files/02 §8.2** — *"Barge-in stop ≤ 150 ms. RED preemption ≤ 300 ms from
   rule evaluation."* The stamp the path measures from is therefore the
   rules-engine determination, supplied by the caller — never ``now()`` at the
   moment Layer A noticed, which would understate the budget it is policing.

**No clinical content is authored here.** Every rule id, script id and Turkish
string is synthetic (files/04 §7). The RED scripts themselves are pre-positioned
device content that INT-043 (HB-C1) blocks, and this suite never needs one: it
addresses a script by id and asserts the id travelled.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.talker.delivery import DeliveryClass
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    InlinePayload,
    PreemptRefused,
    Presentation,
    Priority,
)
from intake_voice_runtime.talker.red_path import (
    E2E_BUDGET_MS,
    GENERIC_RED_SCRIPT_IDS,
    REGISTER_DELIVERY,
    STOP_BUDGET_MS,
    MappingRedScriptIndex,
    RedDelivery,
    RedPathViolation,
    RedPreemption,
    RedPreemptionOutcome,
    RedTriggerMessage,
    RedViolation,
)
from pydantic import ValidationError
from red_harness import (
    BLUEPRINT_DEVICE_OUTPUT_MS,
    BLUEPRINT_DOWNLINK_MS,
    MediaPlane,
    MediaPlaneGone,
    RecordingClinicNotifier,
    RecordingDataChannel,
)
from talker_harness import FakeClock, build_session, scripted_step

REPO = Path(__file__).resolve().parents[2]
RED_PATH_MODULE = (
    REPO / "services" / "voice-runtime" / "src" / "intake_voice_runtime" / "talker" / "red_path.py"
)
CLIENT_RED_TS = REPO / "apps" / "mobile" / "src" / "lib" / "livekit" / "red.ts"

# --- synthetic fixtures (files/04 §7) -------------------------------------------------

RULE_A = "rf.sentetik_a"
RULE_B = "rf.sentetik_b"
PACK_RULES = frozenset({RULE_A, RULE_B})

SCRIPTS = MappingRedScriptIndex(
    entries={
        (RULE_A, RedLocation.REMOTE): "sentetik.a.remote",
        (RULE_A, RedLocation.ON_SITE): "sentetik.a.on_site",
        (RULE_A, RedLocation.UNKNOWN): "sentetik.a.unknown",
        (RULE_B, RedLocation.REMOTE): "sentetik.b.remote",
        (RULE_B, RedLocation.ON_SITE): "sentetik.b.on_site",
        (RULE_B, RedLocation.UNKNOWN): "sentetik.b.unknown",
    }
)


def red_triage(
    *,
    register: RedRegister = RedRegister.ALERT,
    location: RedLocation = RedLocation.REMOTE,
    rule_id: str = RULE_A,
) -> RulesTriageResult:
    return RulesTriageResult(
        level=TriageLevel.RED,
        rules=(RuleFire(id=rule_id, evidence="sentetik_yanit=evet"),),
        register=register,
        location=location,
    )


def red_result(
    *,
    work_id: str = "w_red",
    register: RedRegister = RedRegister.ALERT,
    location: RedLocation = RedLocation.REMOTE,
    rule_id: str = RULE_A,
    speech_tr: str | None = None,
    inline: InlinePayload | None = None,
) -> BackendResult:
    return BackendResult(
        work_id=work_id,
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        presentation=Presentation(
            inline=inline,
            speech_tr=speech_tr,
            triage_update=red_triage(register=register, location=location, rule_id=rule_id),
        ),
        priority=Priority.PREEMPT,
    )


class Rig:
    """One wired RED path over doubles, plus the clock they all share."""

    def __init__(
        self,
        *,
        cancel_cost_ms: float = 5.0,
        downlink_ms: float = BLUEPRINT_DOWNLINK_MS,
        device_output_ms: float = BLUEPRINT_DEVICE_OUTPUT_MS,
        cancel_raises: Exception | None = None,
        publish_raises: Exception | None = None,
        scripts: MappingRedScriptIndex = SCRIPTS,
    ) -> None:
        self.clock = FakeClock()
        self.media = MediaPlane(
            clock=self.clock, cancel_cost_ms=cancel_cost_ms, cancel_raises=cancel_raises
        )
        self.channel = RecordingDataChannel(
            clock=self.clock,
            downlink_ms=downlink_ms,
            device_output_ms=device_output_ms,
            publish_raises=publish_raises,
        )
        self.clinic = RecordingClinicNotifier()
        self.path = RedPreemption(
            canceller=self.media,
            channel=self.channel,
            clinic=self.clinic,
            scripts=scripts,
            clock=self.clock,
        )

    def trigger(
        self, result: BackendResult, *, evaluated_at_ms: float = 0.0
    ) -> RedPreemptionOutcome:
        return self.clock.run(self.path.trigger(result, evaluated_at_ms=evaluated_at_ms))


# --- clause 1: only a rules-engine RED takes this path ---------------------------------------


class TestOnlyARulesEngineRedTakesThisPath:
    """The acceptance's first clause, at the *path* rather than at the type.

    INT-091 already proves the two gates on ``BackendResult`` (shape) and
    ``authorise_preempt`` (provenance). What is new here is that the path
    itself refuses anything those gates would have let past by construction:
    a normal-priority result has no business on it at all.
    """

    def test_a_normal_priority_result_is_refused_by_the_path(self) -> None:
        rig = Rig()
        routine = BackendResult(
            work_id="w1",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.ROUTINE,
            presentation=Presentation(speech_tr="Belgeniz okundu."),
        )
        with pytest.raises(ValueError, match="preempt"):
            rig.trigger(routine)
        assert rig.media.calls == []
        assert rig.channel.published == []
        assert rig.clinic.notifications == []

    def test_a_forged_result_that_bypassed_the_validator_is_still_refused(self) -> None:
        """``model_construct`` skips ``BackendResult``'s own validator, which
        is how a preempt shape could be assembled by an emitter rather than
        built. The path narrows again rather than trusting the type it was
        handed — this is the one path where being wrong is fatal."""
        rig = Rig()
        forged = BackendResult.model_construct(
            work_id="w_forged",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.RED,
            presentation=Presentation(speech_tr="Belgeniz okundu."),
            priority=Priority.PREEMPT,
        )
        with pytest.raises(ValueError, match="rules-engine RED"):
            rig.trigger(forged)
        assert rig.media.calls == []
        assert rig.channel.published == []

    def test_an_llm_candidate_can_never_reach_the_path(self) -> None:
        """Invariant 1 at type level: the candidate type has no RED to offer,
        so the object this path takes cannot be built from LLM output."""
        candidate = LlmCandidateTriage(
            candidate_flags=(CandidateFlag(text="olası kanama", evidence="ifade"),)
        )
        with pytest.raises(ValidationError, match="RED"):
            BackendResult(
                work_id="w1",
                state=WorkState.COMPLETED,
                delivery_class=DeliveryClass.RED,
                presentation=Presentation(triage_update=candidate),
                priority=Priority.PREEMPT,
            )

    def test_the_session_refuses_an_unpinned_red_before_anything_is_stopped(self) -> None:
        """An unpinned session cannot attribute a RED to the rules engine, so
        nothing is cancelled, nothing is published and nothing is notified."""
        rig = Rig()
        session = build_session(rig.clock, steps=[scripted_step()], rule_ids=frozenset())
        session.preemption = rig.path
        with pytest.raises(PreemptRefused):
            rig.clock.run(session.deliver_preempt(red_result(), evaluated_at_ms=0.0))
        assert rig.media.calls == []
        assert rig.channel.published == []
        assert rig.clinic.notifications == []

    def test_a_red_naming_a_rule_outside_the_pinned_pack_never_reaches_the_path(self) -> None:
        rig = Rig()
        session = build_session(rig.clock, steps=[scripted_step()], rule_ids=PACK_RULES)
        session.preemption = rig.path
        forged = red_result(rule_id="rf.uydurma_kural")
        with pytest.raises(PreemptRefused, match="rf.uydurma_kural"):
            rig.clock.run(session.deliver_preempt(forged, evaluated_at_ms=0.0))
        assert rig.channel.published == []


# --- clause 2: the budgets, on the fake clock -------------------------------------------------


class TestTheBudgets:
    """*"playback cancel and script start measured on fake clock"*.

    Both stamps are read off the shared virtual clock. Nothing sleeps in wall
    time, so the numbers are the arithmetic of the charged legs and are the
    same on every machine.
    """

    @staticmethod
    def _after_a_minute(rig: Rig) -> RedPreemptionOutcome:
        """Fire the RED a minute into the session, so a path that measured
        from zero — or from ``now()`` at the moment Layer A noticed — reads
        wrong rather than reading the same."""

        async def scenario() -> RedPreemptionOutcome:
            await rig.clock.sleep(60.0)
            return await rig.path.trigger(red_result(), evaluated_at_ms=rig.clock.now_ms())

        return rig.clock.run(scenario())

    def test_the_stop_is_measured_from_rule_evaluation_and_holds_the_budget(self) -> None:
        rig = Rig(cancel_cost_ms=40.0)
        outcome = self._after_a_minute(rig)
        assert outcome.evaluated_at_ms == pytest.approx(60_000.0)
        assert outcome.stop_ms == pytest.approx(40.0)
        assert outcome.stop_ms is not None and outcome.stop_ms <= STOP_BUDGET_MS

    def test_the_e2e_is_measured_to_the_script_start_on_the_device(self) -> None:
        rig = Rig(cancel_cost_ms=40.0)
        outcome = self._after_a_minute(rig)
        expected = 40.0 + BLUEPRINT_DOWNLINK_MS + BLUEPRINT_DEVICE_OUTPUT_MS
        assert outcome.e2e_ms == pytest.approx(expected)
        assert outcome.e2e_ms is not None and outcome.e2e_ms <= E2E_BUDGET_MS

    def test_the_blueprint_worst_case_transport_still_fits_both_budgets(self) -> None:
        """The stop is charged its whole budget and the trigger the blueprint's
        own worst-case downlink; e2e must still fit. This is the arithmetic
        files/03 §4.6 invariant 4 asserts, run rather than believed."""
        rig = Rig(cancel_cost_ms=STOP_BUDGET_MS)
        outcome = rig.trigger(red_result(), evaluated_at_ms=0.0)
        assert outcome.stop_ms == pytest.approx(STOP_BUDGET_MS)
        assert outcome.e2e_ms is not None and outcome.e2e_ms <= E2E_BUDGET_MS
        assert outcome.violations == ()

    def test_rt02_a_red_mid_sentence_cuts_the_playback_it_found(self) -> None:
        """files/04 §7 RT-02: *"RED rule fires while the agent is mid-sentence
        — playback cut ≤ 150 ms, RED script spoken, UI interrupt ≤ 300 ms"*."""
        rig = Rig(cancel_cost_ms=40.0)

        async def scenario() -> RedPreemptionOutcome:
            import asyncio

            playing = asyncio.ensure_future(rig.media.play(b"x" * 400, label="s1"))
            await rig.clock.sleep(0.100)
            evaluated_at_ms = rig.clock.now_ms()
            outcome = await rig.path.trigger(red_result(), evaluated_at_ms=evaluated_at_ms)
            await playing
            return outcome

        outcome = rig.clock.run(scenario())
        assert rig.media.interrupted == ["s1"]
        assert rig.media.completed == []
        assert outcome.stop_ms is not None and outcome.stop_ms <= STOP_BUDGET_MS
        assert outcome.e2e_ms is not None and outcome.e2e_ms <= E2E_BUDGET_MS

    def test_the_budget_constants_are_the_blueprint_numbers(self) -> None:
        assert STOP_BUDGET_MS == 150.0
        assert E2E_BUDGET_MS == 300.0


class TestAMissedBudgetFailsLoudly:
    """*"a missed RED budget must fail loudly, never degrade silently"*.

    And the louder half: failing must not abandon the patient. Every test here
    asserts both — the violation is raised, **and** the RED still reached the
    device and the clinician.
    """

    def test_a_slow_stop_raises_and_still_delivers(self) -> None:
        rig = Rig(cancel_cost_ms=STOP_BUDGET_MS + 1.0)
        with pytest.raises(RedPathViolation) as excinfo:
            rig.trigger(red_result(), evaluated_at_ms=0.0)
        assert RedViolation.STOP_BUDGET in excinfo.value.violations
        assert len(rig.channel.published) == 1
        assert len(rig.clinic.notifications) == 1

    def test_a_slow_end_to_end_raises_and_still_delivers(self) -> None:
        rig = Rig(cancel_cost_ms=10.0, downlink_ms=E2E_BUDGET_MS, device_output_ms=0.0)
        with pytest.raises(RedPathViolation) as excinfo:
            rig.trigger(red_result(), evaluated_at_ms=0.0)
        assert RedViolation.E2E_BUDGET in excinfo.value.violations
        assert len(rig.channel.published) == 1
        assert len(rig.clinic.notifications) == 1

    def test_the_violation_carries_the_whole_outcome_for_the_operator(self) -> None:
        rig = Rig(cancel_cost_ms=STOP_BUDGET_MS + 1.0)
        with pytest.raises(RedPathViolation) as excinfo:
            rig.trigger(red_result(), evaluated_at_ms=0.0)
        outcome = excinfo.value.outcome
        assert outcome.work_id == "w_red"
        assert outcome.script_started_at_ms is not None
        assert outcome.notified_clinician is True

    def test_an_unaddressable_script_raises_rather_than_inventing_one(self) -> None:
        """No pre-positioned script for this rule at this location. The path
        refuses to derive an id — a guessed script id addresses the wrong words
        on the device — and fails loudly. It still shows the patient a RED: the
        generic escalation (INT-453; tests/voice/test_red_winner.py)."""
        rig = Rig(scripts=MappingRedScriptIndex(entries={}))
        with pytest.raises(RedPathViolation) as excinfo:
            rig.trigger(red_result(), evaluated_at_ms=0.0)
        assert RedViolation.SCRIPT_UNADDRESSABLE in excinfo.value.violations
        assert [message.script_id for message in rig.channel.published] == [
            GENERIC_RED_SCRIPT_IDS[RedLocation.REMOTE]
        ]
        # The intake still stops and the clinician is still told.
        assert rig.media.calls == ["cancel"]
        assert len(rig.clinic.notifications) == 1

    def test_a_red_carrying_server_side_speech_is_refused_and_never_spoken(self) -> None:
        """CLAUDE.md invariant 21: the RED script is pre-positioned on the
        device. A RED whose result carries ``speech_tr`` is a Work asking the
        server to speak a RED; the speech has no route here and the attempt is
        a violation rather than a silent drop (invariant 17)."""
        rig = Rig()
        with pytest.raises(RedPathViolation) as excinfo:
            rig.trigger(red_result(speech_tr="Hemen yüz on ikiyi arayın."), evaluated_at_ms=0.0)
        assert RedViolation.SERVER_SIDE_SPEECH in excinfo.value.violations
        assert "synthesize" not in rig.media.calls
        assert "play" not in rig.media.calls
        assert len(rig.channel.published) == 1

    def test_a_clean_delivery_raises_nothing(self) -> None:
        """The negative control: without it every assertion above is satisfied
        by a path that always raises."""
        rig = Rig()
        outcome = rig.trigger(red_result(), evaluated_at_ms=0.0)
        assert outcome.violations == ()


# --- invariant 21: the register decides delivery, with no default -----------------------------


class TestTheRegisterDecidesDelivery:
    """files/02 §5.3 Axis 2, as a total table rather than scattered branches.

    ``SILENT`` is *"Screen only … No audio, ever"*; ``DEFERRED_CLINICIAN`` is
    *"Patient screen unchanged. Finding routes to the clinician only"* — and
    is *"exactly what ``device_functions=off`` requires"*, where the session
    continues and triage is shadow-logged (files/03 §15b). So the deferred
    register neither stops the intake nor reaches the patient at all.
    """

    @pytest.mark.parametrize("register", [RedRegister.ALERT, RedRegister.CALM])
    def test_the_patient_facing_audible_registers_stop_and_trigger(
        self, register: RedRegister
    ) -> None:
        rig = Rig()
        outcome = rig.trigger(red_result(register=register), evaluated_at_ms=0.0)
        assert rig.media.calls == ["cancel"]
        assert [message.register for message in rig.channel.published] == [register]
        assert outcome.script_started_at_ms is not None

    def test_a_silent_red_stops_and_renders_but_carries_its_register_verbatim(self) -> None:
        rig = Rig()
        outcome = rig.trigger(red_result(register=RedRegister.SILENT), evaluated_at_ms=0.0)
        assert rig.media.calls == ["cancel"]
        published = rig.channel.published[0]
        assert published.register is RedRegister.SILENT
        assert outcome.violations == ()
        # Nothing was spoken, and nothing could have been: no TTS, no clip.
        assert "synthesize" not in rig.media.calls
        assert "fetch" not in rig.media.calls
        assert "play" not in rig.media.calls

    def test_a_deferred_clinician_red_reaches_the_clinician_and_nobody_else(self) -> None:
        rig = Rig()
        outcome = rig.trigger(
            red_result(register=RedRegister.DEFERRED_CLINICIAN), evaluated_at_ms=0.0
        )
        assert rig.media.calls == []
        assert rig.channel.published == []
        assert len(rig.clinic.notifications) == 1
        assert outcome.stopped_at_ms is None
        assert outcome.stop_ms is None
        assert outcome.script_started_at_ms is None
        assert outcome.e2e_ms is None
        assert outcome.violations == ()

    def test_every_register_reaches_the_clinician(self) -> None:
        """files/protocols/base.life_threat.yaml: ``notify_clinic: always`` on
        every RED, unconditional and time-bound (files/04 §4.2)."""
        for register in RedRegister:
            rig = Rig()
            rig.trigger(red_result(register=register), evaluated_at_ms=0.0)
            assert len(rig.clinic.notifications) == 1, register

    def test_the_delivery_table_is_total_over_the_register_enum(self) -> None:
        assert set(REGISTER_DELIVERY) == set(RedRegister)

    def test_an_unmapped_register_raises_rather_than_defaulting(self) -> None:
        """The negative control for the table: a register with no row must be
        a hard failure. A default chosen once by an engineer is the failure
        invariant 21 exists to prevent (files/02 §5.3 binding authoring rule)."""
        rig = Rig()
        thinned = {
            register: delivery
            for register, delivery in REGISTER_DELIVERY.items()
            if register is not RedRegister.SILENT
        }
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("intake_voice_runtime.talker.red_path.REGISTER_DELIVERY", thinned)
            with pytest.raises(KeyError):
                rig.trigger(red_result(register=RedRegister.SILENT), evaluated_at_ms=0.0)

    def test_every_row_names_the_blueprint_sentence_it_comes_from(self) -> None:
        for register, delivery in REGISTER_DELIVERY.items():
            assert isinstance(delivery, RedDelivery)
            assert delivery.source.strip(), register

    def test_the_notifier_port_has_no_awaitable_member(self) -> None:
        """The clinician route runs before the stop and must not be able to
        delay it — the same structural trick ADR-009 uses on ``WorkSubmitter``."""
        import inspect

        from intake_voice_runtime.talker.red_path import ClinicNotifier

        for name, member in inspect.getmembers(ClinicNotifier, inspect.isfunction):
            if name.startswith("_"):
                continue
            assert not inspect.iscoroutinefunction(member), name
            annotation = inspect.signature(member).return_annotation
            assert "Awaitable" not in str(annotation), name


# --- invariant 21: no media transport ----------------------------------------------------------


class TestThePathTouchesNoMediaTransport:
    """files/03 §4.6 invariant 4, in the form the blueprint asks for.

    Three independent proofs, because each fails differently: the module
    cannot *name* the media path (AST), it is not *handed* one (signature),
    and at runtime it *calls* nothing but the cancel.
    """

    #: Anything that would put the RED script on the audio path.
    FORBIDDEN_IMPORTS = frozenset(
        {
            "intake_voice_runtime.talker.speech",
            "intake_voice_runtime.talker.clips",
            "SpeechRouter",
            "SpeechSynthesizer",
            "ClipStore",
            "ClipCatalogue",
            "AudioSink",
        }
    )
    #: Method names that move audio. ``cancel`` is deliberately absent: it
    #: stops the media plane, it does not carry anything through it.
    FORBIDDEN_ATTRIBUTES = frozenset({"play", "synthesize", "fetch", "speak", "text_for"})

    def _tree(self) -> ast.Module:
        return ast.parse(RED_PATH_MODULE.read_text(encoding="utf-8"))

    def test_the_module_imports_nothing_on_the_audio_path(self) -> None:
        names: set[str] = set()
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names.add(node.module)
                names.update(alias.name for alias in node.names)
        assert not (names & self.FORBIDDEN_IMPORTS), sorted(names & self.FORBIDDEN_IMPORTS)

    def test_the_module_names_no_method_that_moves_audio(self) -> None:
        used = {node.attr for node in ast.walk(self._tree()) if isinstance(node, ast.Attribute)}
        assert not (used & self.FORBIDDEN_ATTRIBUTES), sorted(used & self.FORBIDDEN_ATTRIBUTES)

    def test_the_controller_is_handed_no_media_port(self) -> None:
        """A port parameter is how a media path gets into a class. The
        constructor's parameter set is pinned, so adding one fails here."""
        import dataclasses

        parameters = {field.name for field in dataclasses.fields(RedPreemption) if field.init}
        assert parameters == {"canceller", "channel", "clinic", "scripts", "clock"}

    def test_at_runtime_the_only_media_call_is_the_cancel(self) -> None:
        rig = Rig()
        rig.trigger(red_result(), evaluated_at_ms=0.0)
        assert rig.media.calls == ["cancel"]
        assert rig.media.played == []

    def test_a_red_renders_with_the_media_plane_already_gone(self) -> None:
        """The case invariant 4 exists for: the audio plane is torn down and
        the RED must still reach the patient over the data channel. A cancel
        that cannot run is a reason the RED renders, not a reason to drop it."""
        rig = Rig(cancel_raises=MediaPlaneGone("audio session released"))
        outcome = rig.trigger(red_result(), evaluated_at_ms=0.0)
        assert outcome.media_plane_unreachable is True
        assert len(rig.channel.published) == 1
        assert outcome.script_started_at_ms is not None
        assert outcome.violations == ()


# --- the wire ------------------------------------------------------------------------------------


class TestTheWireCarriesIdentifiersAndAxesOnly:
    """The message the device decodes, pinned against the client that decodes it.

    ``apps/mobile/src/lib/livekit/red.ts`` is the only consumer. Two readings
    of one message is how a RED silently stops rendering, so the field names
    and the id shape are read out of the client source and asserted here
    rather than restated.
    """

    def _client_source(self) -> str:
        return CLIENT_RED_TS.read_text(encoding="utf-8")

    def test_the_message_serialises_to_exactly_the_keys_the_client_destructures(self) -> None:
        source = self._client_source()
        match = re.search(r"const \{ ([^}]+) \} = message;", source)
        assert match is not None, "the client no longer destructures the trigger"
        client_keys = {name.strip() for name in match.group(1).split(",")} | {"kind"}
        message = RedTriggerMessage(
            rule_id=RULE_A,
            register=RedRegister.ALERT,
            location=RedLocation.REMOTE,
            script_id="sentetik.a.remote",
        )
        assert set(message.model_dump(by_alias=True)) == client_keys

    def test_the_id_shape_is_the_client_id_shape(self) -> None:
        source = self._client_source()
        match = re.search(r"const ID_SHAPE = /([^/]+)/;", source)
        assert match is not None, "the client no longer pins an id shape"
        pattern = re.compile(match.group(1))
        for bad in ("has space", "", "-leading-dash", "Ahmet Yılmaz"):
            assert pattern.fullmatch(bad) is None or bad == ""
            with pytest.raises(ValidationError):
                RedTriggerMessage(
                    rule_id=bad,
                    register=RedRegister.ALERT,
                    location=RedLocation.REMOTE,
                    script_id="sentetik.a.remote",
                )

    def test_the_wire_has_no_carrier_for_the_112_affordance(self) -> None:
        """INT-255 closed the affordance's three carriers — the flag, the
        number list and the action code — on ``LocationAction``. All three
        live in the pack, which is on the device. The preemption path cannot
        reintroduce any of them because the message has nowhere to put one."""
        fields = set(RedTriggerMessage.model_fields)
        assert fields == {"kind", "rule_id", "register", "location", "script_id"}
        assert not (fields & {"show_112", "numbers", "primary", "secondary", "action_tr"})

    def test_an_on_site_red_puts_no_112_on_the_wire_in_any_form(self) -> None:
        rig = Rig()
        rig.trigger(red_result(location=RedLocation.ON_SITE), evaluated_at_ms=0.0)
        payload = json.dumps(
            rig.channel.published[0].model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
        )
        assert "112" not in payload
        assert '"ON_SITE"' in payload

    def test_the_location_selects_the_script_and_nothing_else(self) -> None:
        """The near-miss control for the test above: the same rule under two
        locations produces two different pre-positioned scripts, so the ON_SITE
        assertion is about the affordance and not about an empty message."""
        remote = Rig()
        remote.trigger(red_result(location=RedLocation.REMOTE), evaluated_at_ms=0.0)
        on_site = Rig()
        on_site.trigger(red_result(location=RedLocation.ON_SITE), evaluated_at_ms=0.0)
        assert remote.channel.published[0].script_id == "sentetik.a.remote"
        assert on_site.channel.published[0].script_id == "sentetik.a.on_site"

    def test_no_numeral_reaches_a_tts_model_because_nothing_reaches_one(self) -> None:
        """CLAUDE.md invariant 22's first clause on this path is structural:
        the RED script is device-side, so there is no synthesis step to guard."""
        rig = Rig()
        rig.trigger(red_result(location=RedLocation.UNKNOWN), evaluated_at_ms=0.0)
        assert "synthesize" not in rig.media.calls


class TestNoPhiOnTheRedPath:
    """CLAUDE.md invariant 6: ids and closed enumerations only."""

    def test_the_wire_carries_no_rule_evidence(self) -> None:
        rig = Rig()
        rig.trigger(red_result(), evaluated_at_ms=0.0)
        payload = json.dumps(
            rig.channel.published[0].model_dump(by_alias=True, mode="json"), ensure_ascii=False
        )
        assert "sentetik_yanit" not in payload

    def test_the_clinic_notification_carries_ids_and_axes_only(self) -> None:
        rig = Rig()
        rig.trigger(red_result(), evaluated_at_ms=0.0)
        dumped: dict[str, Any] = rig.clinic.notifications[0].model_dump(mode="json")
        assert set(dumped) == {
            "work_id",
            "rule_ids",
            "register",
            "location",
            "evaluated_at_ms",
            "patient_facing",
            # INT-453 / CD-24 delivery floor: a boolean, no patient material.
            "silent_generic",
        }
        assert isinstance(dumped["silent_generic"], bool)
        assert "sentetik_yanit" not in json.dumps(dumped, ensure_ascii=False)


# --- delivery semantics ---------------------------------------------------------------------------


class TestIdempotentAndSealed:
    def test_the_same_work_id_triggers_the_device_exactly_once(self) -> None:
        """files/03 §4.6 invariant 6 and files/12 §7.5: a re-derived RED
        carries the same content-addressed ``work_id``, so replay is a no-op."""
        rig = Rig()
        first = rig.trigger(red_result(), evaluated_at_ms=0.0)
        second = rig.trigger(red_result(), evaluated_at_ms=0.0)
        assert len(rig.channel.published) == 1
        assert len(rig.clinic.notifications) == 1
        assert rig.media.calls == ["cancel"]
        assert second == first

    def test_a_different_red_is_not_deduped_against_the_first(self) -> None:
        rig = Rig()
        rig.trigger(red_result(work_id="w_red"), evaluated_at_ms=0.0)
        rig.trigger(red_result(work_id="w_red_2", rule_id=RULE_B), evaluated_at_ms=0.0)
        assert len(rig.channel.published) == 2
        assert rig.path.delivered_work_ids == ("w_red", "w_red_2")

    def test_the_queue_seals_itself_and_the_path_does_not_re_seal(self) -> None:
        """INT-092 already seals the Work queue when it derives the preempt
        (files/12 §7.1). Sealing again here would be a second implementation of
        the same rule, and the two would drift."""
        source = RED_PATH_MODULE.read_text(encoding="utf-8")
        assert "_seal" not in source
        assert "work_queue" not in source


class TestTheSessionStopsTheIntake:
    """files/03 §4.6: *"Kırmızı (RED) = preempt, stop intake"*."""

    def test_after_a_patient_facing_red_the_turn_loop_asks_nothing_more(self) -> None:
        rig = Rig()
        session = build_session(rig.clock, steps=[scripted_step()], rule_ids=PACK_RULES)
        session.preemption = rig.path

        async def scenario() -> Any:
            await session.deliver_preempt(red_result(), evaluated_at_ms=0.0)
            return await session.take_turn(None)

        outcome = rig.clock.run(scenario())
        assert session.red_stopped is True
        assert outcome.step_id is None
        assert outcome.spoken_text == ""

    def test_a_deferred_clinician_red_leaves_the_session_running(self) -> None:
        rig = Rig()
        session = build_session(rig.clock, steps=[scripted_step()], rule_ids=PACK_RULES)
        session.preemption = rig.path

        async def scenario() -> Any:
            await session.deliver_preempt(
                red_result(register=RedRegister.DEFERRED_CLINICIAN), evaluated_at_ms=0.0
            )
            return await session.take_turn(None)

        outcome = rig.clock.run(scenario())
        assert session.red_stopped is False
        assert outcome.step_id == "s1"

    def test_a_session_with_no_red_path_wired_refuses_rather_than_pretending(self) -> None:
        clock = FakeClock()
        session = build_session(clock, steps=[scripted_step()], rule_ids=PACK_RULES)
        with pytest.raises(LookupError, match="RED"):
            clock.run(session.deliver_preempt(red_result(), evaluated_at_ms=0.0))
