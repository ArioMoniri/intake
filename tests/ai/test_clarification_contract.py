"""INT-540 — the extraction contract says what ``clarification_needed`` means.

The INT-522 clinical review, finding F1: the instruction region never said
when to set ``clarification_needed``. For 'bilmiyorum' or a narrative answer
the model could return no slot and ``false``, and the engine — which binds
nothing to an unrecorded slot and queues a follow-up only on the flag — left
the onset anchor ``ASKED_PENDING`` for the rest of the session.

Both halves of the contract now say it:

- **The instructions** (model-facing, ``PROMPT_VERSION`` bumped because the
  wording changed): the flag is true when a declared slot the patient was
  answering cannot be recorded as any value the schema allows — they do not
  know, are not sure, hedge, or answer outside the offered values — and that
  slot is then left out; never a guessed value instead.
- **The parse** (runtime-facing): :meth:`ExtractionResult.outcome_of` gives
  every declared slot exactly one reading of a completion — ``CLARIFY`` when
  the flag is set (the engine binds nothing from that Work, files/13 §11.1),
  else ``BOUND``, ``REFUSED`` (offered and refused, flagged), or ``SILENT``
  (no value and no flag). ``SILENT`` is the reading the instructions now rule
  out and the runtime does not trust: for an asked tense anchor it is CD-05's
  answer fitting no choice (``tests/voice/test_anchor_unclear.py``).

The instruction region stays English and carries no Turkish letter, so a
transcript cannot have leaked into it (invariant 14).
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from intake_voice_runtime.extraction import (
    PROMPT_VERSION,
    build_instructions,
    parse_extraction,
    slot_output_schema,
)
from intake_voice_runtime.extraction.result import ExtractionResult, FlagReason, SlotOutcome
from protocols.dsl import Slot
from protocols.types import SlotType

SLOTS: dict[str, Slot] = {
    "hpi.sure_gun": Slot(type=SlotType.INTEGER, required=True),
    "hpi.siddet": Slot(type=SlotType.CODE, valueset="vs.siddet"),
    "hpi.var_mi": Slot(type=SlotType.BOOLEAN),
}
VALUESETS: dict[str, tuple[str, ...]] = {"vs.siddet": ("hafif", "orta")}


def _instructions() -> str:
    return build_instructions(slot_output_schema(SLOTS, VALUESETS))


def _prose() -> str:
    """The instruction region above the embedded schema."""
    return _instructions().split("Schema:", 1)[0]


def _parse(slots: dict[str, object], *, clarify: bool) -> ExtractionResult:
    body = {
        "slots": {ref: {"value": value, "confidence": 0.9} for ref, value in slots.items()},
        "candidate_flags": [],
        "clarification_needed": clarify,
    }
    return parse_extraction(
        raw=json.dumps(body), slots=SLOTS, valuesets=VALUESETS, step_id="hpi.sure_gun"
    )


# --- the instructions ------------------------------------------------------------------


def test_the_instructions_define_when_clarification_is_needed() -> None:
    prose = _prose()
    [rule] = [line for line in prose.splitlines() if line.startswith("8. clarification_needed")]
    for clause in (
        "do not know",
        "not sure",
        "hedge",
        "none of the values",
        "leave that slot out",
        "never record a guessed value",
        "false when every slot the patient answered is recorded",
    ):
        assert clause in rule, clause


def test_the_wording_changed_so_the_prompt_version_did_too() -> None:
    """A recording made under the old wording is not a recording of this call;
    the recorded gateway refuses on the version (tests/ai/test_extraction_contract)."""
    assert PROMPT_VERSION == "extraction.v2"


def test_the_instruction_prose_carries_no_turkish_letter() -> None:
    prose = _prose()
    for letter in "ğşıİöüçĞŞÖÜÇ":
        assert letter not in prose


def test_the_instructions_still_take_the_schema_and_nothing_else() -> None:
    assert _instructions() == build_instructions(slot_output_schema(SLOTS, VALUESETS))


# --- the parse -------------------------------------------------------------------------


def test_a_recorded_slot_is_bound_and_an_unrecorded_one_is_silent() -> None:
    result = _parse({"hpi.sure_gun": 3}, clarify=False)
    assert result.outcome_of("hpi.sure_gun") is SlotOutcome.BOUND
    assert result.outcome_of("hpi.siddet") is SlotOutcome.SILENT


def test_a_value_offered_and_refused_is_refused_not_silent() -> None:
    result = _parse({"hpi.siddet": "agir", "hpi.sure_gun": "3"}, clarify=False)
    assert result.outcome_of("hpi.siddet") is SlotOutcome.REFUSED
    assert result.outcome_of("hpi.sure_gun") is SlotOutcome.REFUSED
    assert {(f.ref, f.reason) for f in result.flags} == {
        ("hpi.siddet", FlagReason.VALUESET_VIOLATION),
        ("hpi.sure_gun", FlagReason.AMBIGUOUS_NUMERAL),
    }


@pytest.mark.parametrize(
    "slots",
    [
        pytest.param({}, id="nothing-recorded"),
        pytest.param({"hpi.sure_gun": 3}, id="a-value-beside-the-flag"),
    ],
)
def test_the_flag_makes_every_declared_slot_clarify(slots: dict[str, object]) -> None:
    """files/13 §11.1: the engine binds nothing from a Work that asks to
    clarify, so a value recorded beside the flag is not bound either, and the
    reading says so rather than calling it bound."""
    result = _parse(slots, clarify=True)
    for ref in SLOTS:
        assert result.outcome_of(ref) is SlotOutcome.CLARIFY


def test_a_ref_the_step_does_not_declare_has_no_reading() -> None:
    result = _parse({"hpi.sure_gun": 3}, clarify=False)
    with pytest.raises(LookupError, match="hpi.yok"):
        result.outcome_of("hpi.yok")


def test_the_reading_is_a_closed_set() -> None:
    assert {outcome.value for outcome in SlotOutcome} == {"bound", "refused", "clarify", "silent"}


def test_a_decimal_still_binds_as_a_decimal() -> None:
    slots = {"hpi.olcum": Slot(type=SlotType.DECIMAL)}
    body = {
        "slots": {"hpi.olcum": {"value": 38.5, "confidence": 0.9}},
        "candidate_flags": [],
        "clarification_needed": False,
    }
    result = parse_extraction(raw=json.dumps(body), slots=slots, valuesets={}, step_id="hpi.olcum")
    assert result.outcome_of("hpi.olcum") is SlotOutcome.BOUND
    assert result.slot_updates[0].value == Decimal("38.5")
