"""INT-453 — the RED path triggers the winning rule's own script.

Found by INT-446 (#766). ``RedPreemption.trigger`` addressed the script with
``rule_ids[0]``. ``RulesTriageResult.rules`` is ordered by severity then id,
and the engine breaks a severity tie on register restrictiveness, so with two
RED rules firing the wire could carry rule B's register beside rule A's script
— an ALERT script under a SILENT register, or the reverse.

These tests run the real engine (``protocols.triage.evaluate_triage``) over two
SENTETİK rules built from the committed signed fixture, hand its result to the
real RED path, and read what reached the data channel. Each case has its near
miss: the rule listed first, whose script must NOT be the one triggered.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, RedRegister, RulesTriageResult
from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.talker.delivery import DeliveryClass
from intake_voice_runtime.talker.preemption import BackendResult, Presentation, Priority
from intake_voice_runtime.talker.red_path import (
    MappingRedScriptIndex,
    RedPathViolation,
    RedTriggerMessage,
    RedViolation,
)
from protocols import EK4Level, RedFlagRule
from protocols.compile import load_life_threat_set
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage
from test_red_preemption import Rig

REPO = Path(__file__).resolve().parents[2]
SIGNED = REPO / "tests" / "fixtures" / "protocols" / "compile" / "life_threat_signed.yaml"
BASE = load_life_threat_set(SIGNED).rules[0].rule

RULE_A = "rf.sentetik_a"  # sorts first
RULE_B = "rf.sentetik_b"

FIRING = TriageContext(
    reference_time=datetime.fromisoformat("2026-08-29T10:00:00+03:00"),
    answers={
        "ziyaret.basvuru_nedeni": SlotAnswer(
            state=AnswerState.ASKED_PRESENT, values=("sentetik_yasamsal",)
        ),
        "sure_dakika": SlotAnswer(state=AnswerState.ASKED_PRESENT, values=("2026-08-29",)),
    },
)


def rule(rule_id: str, register: RedRegister, level: EK4Level = EK4Level.KIRMIZI_K1) -> RedFlagRule:
    """The signed SENTETİK rule, re-identified: same gate, so every copy fires."""
    return BASE.model_copy(update={"id": rule_id, "register": register, "level": level})


def scripts(*rules: RedFlagRule) -> MappingRedScriptIndex:
    return MappingRedScriptIndex(
        entries={
            (r.id, location): f"{r.id}.{location.value.lower()}"
            for r in rules
            for location in RedLocation
        },
        rules={r.id: r for r in rules},
    )


def preempt(triage: RulesTriageResult, work_id: str = "w_red") -> BackendResult:
    return BackendResult(
        work_id=work_id,
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        presentation=Presentation(triage_update=triage),
        priority=Priority.PREEMPT,
    )


def published(rig: Rig) -> RedTriggerMessage:
    assert len(rig.channel.published) == 1
    message = rig.channel.published[0]
    assert isinstance(message, RedTriggerMessage)
    return message


@pytest.mark.parametrize("location", list(RedLocation))
def test_a_register_tie_triggers_the_winner_not_the_first_listed_rule(
    location: RedLocation,
) -> None:
    alert = rule(RULE_A, RedRegister.ALERT)
    silent = rule(RULE_B, RedRegister.SILENT)
    triage = evaluate_triage((alert, silent), FIRING, location).result
    # Near miss: the rule listed first is the ALERT one.
    assert [fire.id for fire in triage.rules] == [RULE_A, RULE_B]
    assert triage.register is RedRegister.SILENT
    rig = Rig(scripts=scripts(alert, silent))
    outcome = rig.trigger(preempt(triage))
    message = published(rig)
    assert message.rule_id == RULE_B
    assert message.register is RedRegister.SILENT
    assert message.location is location
    assert message.script_id == f"{RULE_B}.{location.value.lower()}"
    assert outcome.script_id == message.script_id
    assert outcome.rule_ids == (RULE_A, RULE_B)  # the clinician still sees every rule


def test_higher_severity_triggers_its_own_script_over_a_more_restrictive_register() -> None:
    silent_k2 = rule(RULE_A, RedRegister.SILENT, EK4Level.KIRMIZI_K2)
    alert_k1 = rule(RULE_B, RedRegister.ALERT, EK4Level.KIRMIZI_K1)
    triage = evaluate_triage((silent_k2, alert_k1), FIRING, RedLocation.REMOTE).result
    rig = Rig(scripts=scripts(silent_k2, alert_k1))
    rig.trigger(preempt(triage))
    message = published(rig)
    assert (message.rule_id, message.register) == (RULE_B, RedRegister.ALERT)
    assert message.script_id == f"{RULE_B}.remote"


def test_one_fired_rule_is_its_own_winner_without_the_packs_rules() -> None:
    only = rule(RULE_A, RedRegister.CALM)
    triage = evaluate_triage((only,), FIRING, RedLocation.ON_SITE).result
    rig = Rig(scripts=MappingRedScriptIndex(entries={(RULE_A, RedLocation.ON_SITE): "a.on_site"}))
    rig.trigger(preempt(triage))
    assert published(rig).script_id == "a.on_site"


def _refused(rig: Rig, triage: RulesTriageResult) -> None:
    with pytest.raises(RedPathViolation) as excinfo:
        rig.trigger(preempt(triage))
    assert RedViolation.SCRIPT_UNADDRESSABLE in excinfo.value.violations
    assert rig.channel.published == []  # never a guessed script
    assert rig.media.calls == ["cancel"]  # the intake still stops
    assert len(rig.clinic.notifications) == 1  # and the clinician is still told


def test_several_fired_rules_without_the_packs_rules_are_unaddressable() -> None:
    alert = rule(RULE_A, RedRegister.ALERT)
    silent = rule(RULE_B, RedRegister.SILENT)
    triage = evaluate_triage((alert, silent), FIRING, RedLocation.REMOTE).result
    entries_only = MappingRedScriptIndex(entries=scripts(alert, silent).entries)
    _refused(Rig(scripts=entries_only), triage)


def test_a_pack_that_disagrees_on_the_register_is_unaddressable() -> None:
    alert = rule(RULE_A, RedRegister.ALERT)
    silent = rule(RULE_B, RedRegister.SILENT)
    triage = evaluate_triage((alert, silent), FIRING, RedLocation.REMOTE).result
    # The device's pack says rule B is CALM; the result says SILENT.
    drifted = scripts(alert, rule(RULE_B, RedRegister.CALM))
    _refused(Rig(scripts=drifted), triage)


def test_a_pack_holding_no_red_rule_among_them_is_unaddressable() -> None:
    alert = rule(RULE_A, RedRegister.ALERT)
    silent = rule(RULE_B, RedRegister.SILENT)
    triage = evaluate_triage((alert, silent), FIRING, RedLocation.REMOTE).result
    not_red = scripts(
        rule(RULE_A, RedRegister.ALERT, EK4Level.SARI_K1),
        rule(RULE_B, RedRegister.SILENT, EK4Level.SARI_K1),
    )
    _refused(Rig(scripts=not_red), triage)
