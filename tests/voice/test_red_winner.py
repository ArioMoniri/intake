"""INT-453: the RED path triggers the RED the rules engine named, and it
always shows the patient a RED.

Found by INT-446 (#766). ``RedPreemption.trigger`` addressed the script with
``rule_ids[0]``. ``RulesTriageResult.rules`` is ordered by severity and then id,
while the engine breaks a severity tie on register restrictiveness. With two
RED rules firing, the wire could therefore carry rule B's register beside rule
A's script.

The fix has three parts:

- The engine now names its RED in the result (``red_rule_id``), and the path
  reads that name instead of a position or a re-derivation.
- Only that one RED rule has to be addressable, so a YELLOW rule firing beside
  it never drops the RED.
- A RED whose script cannot be addressed still reaches the device as the
  generic escalation. That trigger uses ALERT, the result's own location (so
  there is no 112 under ON_SITE), and a SCRIPT_UNADDRESSABLE failure is raised
  loudly. Sending nothing is no longer a possible outcome.

The tests drive the real engine (``protocols.triage.evaluate_triage``) into
the real path over SENTETİK rules built from the committed signed fixture.
Each case has a near-miss control.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import (
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.talker.delivery import DeliveryClass
from intake_voice_runtime.talker.preemption import BackendResult, Presentation, Priority
from intake_voice_runtime.talker.red_path import (
    GENERIC_RED_SCRIPT_IDS,
    MappingRedScriptIndex,
    RedPathViolation,
    RedTriggerMessage,
    RedViolation,
)
from protocols import EK4Level, RedFlagRule
from protocols.compile import load_life_threat_set
from protocols.generic_red import load_generic_red
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage
from test_red_preemption import Rig

REPO = Path(__file__).resolve().parents[2]
SIGNED = REPO / "tests" / "fixtures" / "protocols" / "compile" / "life_threat_signed.yaml"
CLIENT_RED_TS = REPO / "apps" / "mobile" / "src" / "lib" / "livekit" / "red.ts"
GENERIC_SENTETIK = REPO / "tests" / "fixtures" / "triage_hop" / "generic_red_sentetik.yaml"
GENERIC_COMMITTED = REPO / "packages" / "protocols" / "generic" / "generic_red.yaml"
BASE = load_life_threat_set(SIGNED).rules[0].rule

RULE_A = "rf.sentetik_a"  # sorts first
RULE_B = "rf.sentetik_b"
RULE_Y = "rf.sentetik_0_sari"  # sorts before both

FIRING = TriageContext(
    reference_time=datetime.fromisoformat("2026-08-29T10:00:00+03:00"),
    answers={
        "ziyaret.basvuru_nedeni": SlotAnswer(
            state=AnswerState.ASKED_PRESENT, values=("sentetik_yasamsal",)
        ),
        "sure_dakika": SlotAnswer(state=AnswerState.ASKED_PRESENT, values=("2026-08-29",)),
    },
)


def red(rule_id: str, register: RedRegister, level: EK4Level = EK4Level.KIRMIZI_K1) -> RedFlagRule:
    """The signed SENTETİK rule, re-identified: same gate, so every copy fires."""
    return BASE.model_copy(update={"id": rule_id, "register": register, "level": level})


def yellow(rule_id: str) -> RedFlagRule:
    return BASE.model_copy(
        update={"id": rule_id, "level": EK4Level.SARI_K1, "register": None, "action": None}
    )


def scripts(*rule_ids: str) -> MappingRedScriptIndex:
    """Scripts for these rules only: a YELLOW rule has none, and needs none."""
    return MappingRedScriptIndex(
        entries={
            (rule_id, location): f"{rule_id}.{location.value.lower()}"
            for rule_id in rule_ids
            for location in RedLocation
        }
    )


def preempt(triage: RulesTriageResult, work_id: str = "w_red") -> BackendResult:
    return BackendResult(
        work_id=work_id,
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        presentation=Presentation(triage_update=triage),
        priority=Priority.PREEMPT,
    )


def sent(rig: Rig) -> list[RedTriggerMessage]:
    messages = list(rig.channel.published)
    assert all(isinstance(message, RedTriggerMessage) for message in messages)
    return messages


# --- the engine names the RED; the path never reads a position ------------------------------


@pytest.mark.parametrize("location", list(RedLocation))
def test_a_register_tie_triggers_the_named_red_not_the_first_listed_rule(
    location: RedLocation,
) -> None:
    alert = red(RULE_A, RedRegister.ALERT)
    silent = red(RULE_B, RedRegister.SILENT)
    triage = evaluate_triage((alert, silent), FIRING, location).result
    # Near miss: the rule listed first is the ALERT one.
    assert [fire.id for fire in triage.rules] == [RULE_A, RULE_B]
    assert (triage.red_rule_id, triage.register) == (RULE_B, RedRegister.SILENT)
    rig = Rig(scripts=scripts(RULE_A, RULE_B))
    outcome = rig.trigger(preempt(triage))
    [message] = sent(rig)
    assert (message.rule_id, message.register, message.location) == (
        RULE_B,
        RedRegister.SILENT,
        location,
    )
    assert message.script_id == f"{RULE_B}.{location.value.lower()}"
    assert outcome.script_id == message.script_id
    assert outcome.rule_ids == (RULE_A, RULE_B)  # the clinician still sees every rule


def test_the_named_red_is_used_even_when_it_is_not_listed_first() -> None:
    """Severity: the K1 rule is named. ``rules`` here is in arrival order, as a
    result rebuilt from another carrier may be, and the K1 rule is second.
    With ``rule_ids[0]`` restored, the K2 rule's script would be sent."""
    triage = RulesTriageResult(
        level=TriageLevel.RED,
        rules=(
            RuleFire(id=RULE_A, evidence="sentetik"),
            RuleFire(id=RULE_B, evidence="sentetik"),
        ),
        register=RedRegister.ALERT,
        location=RedLocation.REMOTE,
        red_rule_id=RULE_B,
    )
    rig = Rig(scripts=scripts(RULE_A, RULE_B))
    rig.trigger(preempt(triage))
    [message] = sent(rig)
    assert (message.rule_id, message.script_id) == (RULE_B, f"{RULE_B}.remote")
    # Near miss: K2 SILENT beside K1 ALERT, as the engine itself orders them.
    engine = evaluate_triage(
        (red(RULE_A, RedRegister.SILENT, EK4Level.KIRMIZI_K2), red(RULE_B, RedRegister.ALERT)),
        FIRING,
        RedLocation.REMOTE,
    ).result
    assert (engine.red_rule_id, engine.register) == (RULE_B, RedRegister.ALERT)


def test_yellow_firing_beside_red_still_shows_the_red() -> None:
    """Only the RED rule has to be addressable; the YELLOW rule has no script."""
    rule = red(RULE_A, RedRegister.CALM)
    triage = evaluate_triage((yellow(RULE_Y), rule), FIRING, RedLocation.REMOTE).result
    assert {fire.id for fire in triage.rules} == {RULE_Y, RULE_A}
    rig = Rig(scripts=scripts(RULE_A))  # near miss: no script exists for the YELLOW rule
    outcome = rig.trigger(preempt(triage))
    [message] = sent(rig)
    assert (message.rule_id, message.register) == (RULE_A, RedRegister.CALM)
    assert outcome.violations == ()


def test_one_fired_rule_without_a_name_is_its_own_red() -> None:
    triage = RulesTriageResult(
        level=TriageLevel.RED,
        rules=(RuleFire(id=RULE_A, evidence="sentetik"),),
        register=RedRegister.CALM,
        location=RedLocation.ON_SITE,
    )
    rig = Rig(scripts=scripts(RULE_A))
    rig.trigger(preempt(triage))
    assert [m.script_id for m in sent(rig)] == [f"{RULE_A}.on_site"]


# --- unaddressable is still a RED on the device ----------------------------------------------


DEVICE_REGISTERS = (RedRegister.ALERT, RedRegister.CALM, RedRegister.SILENT)


@pytest.mark.parametrize("location", list(RedLocation))
@pytest.mark.parametrize("register", DEVICE_REGISTERS)
def test_an_unaddressable_red_shows_the_generic_red_in_the_results_own_register(
    register: RedRegister, location: RedLocation
) -> None:
    """CD-24 carry_engine_register: the generic is told in the engine result's
    own register, never a fixed ALERT, at the result's own location."""
    rule = red(RULE_A, register)
    triage = evaluate_triage((rule,), FIRING, location).result
    rig = Rig(scripts=MappingRedScriptIndex(entries={}))  # pack drift: no script for it
    with pytest.raises(RedPathViolation) as excinfo:
        rig.trigger(preempt(triage))
    assert RedViolation.SCRIPT_UNADDRESSABLE in excinfo.value.violations  # loud
    [message] = sent(rig)  # …and still shown
    assert message.script_id == GENERIC_RED_SCRIPT_IDS[location]
    assert message.register is register  # the result's own, never a fixed ALERT
    assert message.location is location  # ON_SITE stays ON_SITE: the device shows no 112
    assert message.rule_id == RULE_A
    # The delivery floor: intake stops and the clinician is told, with a silent
    # generic marked as such.
    assert rig.media.calls == ["cancel"]
    [notice] = rig.clinic.notifications
    assert notice.silent_generic is (register is RedRegister.SILENT)


@pytest.mark.parametrize("location", list(RedLocation))
def test_a_deferred_clinician_red_never_reaches_the_device_even_unaddressable(
    location: RedLocation,
) -> None:
    rule = red(RULE_A, RedRegister.DEFERRED_CLINICIAN)
    triage = evaluate_triage((rule,), FIRING, location).result
    rig = Rig(scripts=MappingRedScriptIndex(entries={}))
    outcome = rig.trigger(preempt(triage))
    assert sent(rig) == []
    assert rig.media.calls == []
    [notice] = rig.clinic.notifications
    assert (notice.patient_facing, notice.silent_generic) == (False, False)
    assert outcome.violations == ()


def test_a_silent_red_with_its_own_script_is_not_marked_generic() -> None:
    """Near miss for the floor's notice: a SILENT RED delivered with its own
    script is the rule's own approved silence, not a generic one."""
    rule = red(RULE_A, RedRegister.SILENT)
    triage = evaluate_triage((rule,), FIRING, RedLocation.REMOTE).result
    rig = Rig(scripts=scripts(RULE_A))
    rig.trigger(preempt(triage))
    [notice] = rig.clinic.notifications
    assert notice.silent_generic is False


def test_several_fired_rules_with_no_name_show_the_generic_red_never_a_position() -> None:
    triage = RulesTriageResult(
        level=TriageLevel.RED,
        rules=(
            RuleFire(id=RULE_A, evidence="sentetik"),
            RuleFire(id=RULE_B, evidence="sentetik"),
        ),
        register=RedRegister.SILENT,
        location=RedLocation.REMOTE,
    )
    rig = Rig(scripts=scripts(RULE_A, RULE_B))
    with pytest.raises(RedPathViolation):
        rig.trigger(preempt(triage))
    [message] = sent(rig)
    # Near miss: rules[0]'s script exists, and must not be the one sent.
    assert message.script_id == GENERIC_RED_SCRIPT_IDS[RedLocation.REMOTE]
    assert message.script_id != f"{RULE_A}.remote"


def test_a_replay_after_an_unaddressable_red_resends_the_device_trigger() -> None:
    rule = red(RULE_A, RedRegister.ALERT)
    triage = evaluate_triage((rule,), FIRING, RedLocation.REMOTE).result
    rig = Rig(scripts=MappingRedScriptIndex(entries={}))
    for _ in range(2):
        with pytest.raises(RedPathViolation):
            rig.trigger(preempt(triage))
    assert [m.script_id for m in sent(rig)] == [GENERIC_RED_SCRIPT_IDS[RedLocation.REMOTE]] * 2
    # The intake was stopped and the clinician told once; the replay is the device's.
    assert rig.media.calls == ["cancel"]
    assert len(rig.clinic.notifications) == 1


def test_a_replay_resolves_the_script_once_the_pack_holds_it() -> None:
    rule = red(RULE_A, RedRegister.ALERT)
    triage = evaluate_triage((rule,), FIRING, RedLocation.REMOTE).result
    entries: dict[tuple[str, RedLocation], str] = {}
    rig = Rig(scripts=MappingRedScriptIndex(entries=entries))
    with pytest.raises(RedPathViolation):
        rig.trigger(preempt(triage))
    entries[(RULE_A, RedLocation.REMOTE)] = f"{RULE_A}.remote"
    outcome = rig.trigger(preempt(triage))
    assert outcome.violations == ()
    assert [m.script_id for m in sent(rig)][-1] == f"{RULE_A}.remote"


def test_a_replay_after_a_delivered_red_stays_a_no_op() -> None:
    """Near miss for the re-send: a RED the device already rendered is not re-sent."""
    rule = red(RULE_A, RedRegister.ALERT)
    triage = evaluate_triage((rule,), FIRING, RedLocation.REMOTE).result
    rig = Rig(scripts=scripts(RULE_A))
    first = rig.trigger(preempt(triage))
    assert rig.trigger(preempt(triage)) is first
    assert len(sent(rig)) == 1


def test_the_device_mirrors_the_generic_red_ids() -> None:
    source = CLIENT_RED_TS.read_text(encoding="utf-8")
    for location, script_id in GENERIC_RED_SCRIPT_IDS.items():
        assert re.search(rf'{location.value}:\s*"{re.escape(script_id)}"', source), location


def test_the_generic_document_carries_cd24s_register_policy() -> None:
    """The policy the path implements is the document's own literal, so the
    two cannot drift: carry the engine result's register (CD-24)."""
    for path in (GENERIC_SENTETIK, GENERIC_COMMITTED):
        assert load_generic_red(path).register_policy == "carry_engine_register"
