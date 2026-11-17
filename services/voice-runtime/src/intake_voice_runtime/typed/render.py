"""What the typed profile puts on the screen (INT-096).

Two rules, and both are the same rules the voice profile runs under — the
channel changed, the invariants did not.

**Verbatim.** CLAUDE.md invariant 10 governs scripted questions, red-flag
action scripts and validated instruments; it says *spoken* because the profile
it was written for speaks. Displaying an improvised rewording of an authored
Turkish question is the same defect with a different output device, which is
why the permission is decided once, above the transport, in
:func:`~intake_voice_runtime.talker.egress.text_for`. :func:`typed_prompt`
copies ``text_tr`` byte for byte and carries no ``allow_paraphrase``: a
permission nothing here can exercise is a field that will eventually be read
as an instruction.

**Numbers.** Invariant 22's display half: ``useGrouping:false`` for every
clinical quantity, number + unit as one non-breaking atom, and the decimal
point of the reader's locale. :func:`render_measure` writes through
:func:`clinical_schemas.quantity.quantity_atom`, the one renderer the records
confirm card, the clinician note, the patient summary and the FHIR narrative
also write through (INT-386). Before INT-386 this was the fourth private copy
of that rule (docs/evidence/INT-096.md, finding F2), and all four wrote a full
stop for a Turkish reader, who takes a full stop as grouping.

This module is for the screen only. The rail is the typed profile's channel
for a number precisely because nothing is spoken on it; the spoken profile's
numbers are the compiler's Turkish orthography, and ``talker.speech`` refuses a
digit on the way to TTS. No module on that path loads this one
(tests/records/test_quantity_render.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.quantity import NBSP, quantity_atom
from protocols.triage.context import canonical_scalar
from pydantic import Field

from intake_voice_runtime.steps import NextStep, StepKind
from intake_voice_runtime.typed.affordance import AffordanceKind, SlotFacts

__all__ = ["NBSP", "TypedPrompt", "numeric_rail", "render_measure", "typed_prompt"]


class TypedPrompt(FrozenModel):
    """One question, as the typed profile displays it.

    Carries no transcript, no patient entry and no triage field — it is the
    outbound half of the turn only (CLAUDE.md invariants 1 and 6).
    """

    step_id: str = Field(min_length=1)
    kind: StepKind = Field(description="The engine's step kind (files/03 §4.2).")
    text_tr: str = Field(
        min_length=1, description="The authored Turkish, byte for byte (invariant 10)."
    )
    choices_tr: tuple[str, ...] = Field(default=(), description="Authored answer labels, verbatim.")
    affordance: AffordanceKind = Field(description="The input control this step admits.")
    engine_version: int = Field(
        ge=0, description="The snapshot version the step was read at (files/12 §7.2)."
    )


def typed_prompt(step: NextStep, facts: SlotFacts) -> TypedPrompt:
    """Project one engine step into the prompt the screen shows.

    Raises :class:`~intake_voice_runtime.typed.affordance.FreeNumericEntryRefused`
    when the slot admits no typed answer — the refusal reaches the caller
    rather than being swallowed into a text field.
    """
    return TypedPrompt(
        step_id=step.step_id,
        kind=step.kind,
        text_tr=step.text_tr,
        choices_tr=step.choices_tr or facts.choices_tr,
        affordance=facts.affordance(),
        engine_version=step.engine_version,
    )


def render_measure(value: Decimal | int, unit: str | None, *, locale: str) -> str:
    """One clinical quantity, written the one way it may be written, for a
    reader of ``locale``.

    No digit grouping, no exponent, the locale's decimal point, and the unit
    joined by a non-breaking space so the pair cannot be split by a line break
    (invariant 22). ``Decimal("1E+3")`` is written ``1000``: a dose in
    scientific notation on a patient's screen is unreadable in the way that
    gets guessed at. ``locale`` has no default, and a locale with no recorded
    decimal point raises
    :class:`~clinical_schemas.quantity.QuantityLocaleUnknown` rather than being
    written with a guess.
    """
    magnitude = value if isinstance(value, Decimal) else Decimal(value)
    return quantity_atom(magnitude, unit, locale=locale)


def numeric_rail(
    values: Mapping[str, JsonValue], facts: Mapping[str, SlotFacts], *, locale: str
) -> dict[str, str]:
    """Every bound numeric value, rendered for the "Anlattıklarınız" rail.

    files/03 §4.6 invariant 30 pairs each spoken number with an ``inline``
    render on the same ``work_id``. In typed nothing is spoken, so the rail is
    not a counterpart — it is the only channel the number has, and it is
    rendered by :func:`render_measure` for exactly the same reason, in the
    session's ``locale``.

    A value that does not canonicalise to a magnitude is skipped rather than
    coerced: ``protocols.triage.context.canonical_scalar`` is the repository's
    single reading of what a ``JsonValue`` means as a number, and a second one
    here could disagree with the gate that read the same slot.
    """
    rail: dict[str, str] = {}
    for step_id, value in values.items():
        slot = facts.get(step_id)
        if slot is None or not slot.numeric:
            continue
        scalar = canonical_scalar(value)
        if not isinstance(scalar, Decimal):
            continue
        rail[step_id] = render_measure(scalar, slot.unit, locale=locale)
    return rail
