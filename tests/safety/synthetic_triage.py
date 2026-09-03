"""Shared SYNTHETIC fixtures for the INT-080 triage-engine suite.

SENTETİK TEST VERİSİ — every rule id, slot name and Turkish string here is
invented for the mechanism tests; zero clinical content (CLAUDE.md
invariant 17; INT-080 scope). Importable by sibling test modules because
pytest prepends the test directory to sys.path in rootless layouts.
"""

from __future__ import annotations

from datetime import UTC, datetime

from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedRegister
from protocols import EK4Level, RedFlagRule
from protocols.triage import SlotAnswer, TriageContext

REF_TIME = datetime(2026, 8, 28, 10, 0, 0, tzinfo=UTC)
ANCHOR = "olay_zamani"

SOURCE = {
    "guideline_id": "SYN-GUIDE-T",
    "guideline_title": "Sentetik kılavuz T",
    "version_or_date": "sürüm bir",
    "url": "https://example.invalid/syn-guide-t",
    "retrieved_on": "2026-08-28",
    "quote": "sentetik alıntı metni",
}

ACTION = {
    "REMOTE": {
        "primary": "CALL_112",
        "show_112": True,
        "action_tr": {"tr": "Hemen yardım isteyin."},
        "do_nots_tr": {"tr": ("Yalnız kalmayın.",)},
        "why_tr": {"tr": "Bu bir sentetik test metnidir."},
    },
    "ON_SITE": {
        "primary": "GO_TO_IN_HOUSE_ACIL",
        "show_112": False,
        "notify_staff_immediate": True,
        "action_tr": {"tr": "Görevlilere haber verin ve bekleyin."},
        "why_tr": {"tr": "Bu bir sentetik test metnidir."},
    },
    "UNKNOWN": {
        "ask_one_tr": {"tr": "Şu anda hastanede misiniz?"},
        "on_yes": "ON_SITE",
        "on_no": "REMOTE",
        "on_no_answer": "REMOTE",
    },
}


def make_rule(
    rule_id: str,
    level: EK4Level,
    when: str,
    *,
    register: RedRegister | None = None,
    tense: str = "ever",
    status: str = "active",
    source_gap: str | None = None,
) -> RedFlagRule:
    payload: dict[str, object] = {
        "id": rule_id,
        "label_tr": "Sentetik kural etiketi",
        "when": when,
        "tense": tense,
        "tense_anchor": ANCHOR,
        "level": level,
        "route": "EMERGENCY_NOW" if level.is_red else "SAME_DAY_ACIL",
        "notify_clinic": "always",
        "status": status,
    }
    if status == "active":
        payload["source"] = SOURCE
    else:
        payload["source_gap"] = source_gap or "sentetik: kaynak klinik onay bekliyor"
    if level.is_red:
        payload["register"] = register or RedRegister.ALERT
        payload["action"] = ACTION
    elif register is not None:
        payload["register"] = register
    return RedFlagRule.model_validate(payload)


def present(value: object) -> SlotAnswer:
    return SlotAnswer(state=AnswerState.ASKED_PRESENT, values=(value,))


def answer(state: AnswerState, *values: object) -> SlotAnswer:
    return SlotAnswer(state=state, values=tuple(values))


def ctx(**slots: SlotAnswer) -> TriageContext:
    answers = {ANCHOR: present("2026-08-28")}
    answers.update(slots)
    return TriageContext(reference_time=REF_TIME, answers=answers)
