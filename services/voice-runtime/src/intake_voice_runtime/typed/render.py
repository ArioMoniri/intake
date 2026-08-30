"""What the typed lane puts on the screen (INT-096).

Two rules, and both are the same rules the voice lane runs under — the
channel changed, the invariants did not.

**Verbatim.** CLAUDE.md invariant 10 governs scripted questions, red-flag
action scripts and validated instruments; it says *spoken* because the lane it
was written for speaks. Displaying an improvised rewording of an authored
Turkish question is the same defect with a different output device, so
:func:`typed_prompt` copies ``text_tr`` byte for byte and the typed lane holds
no generator that could do otherwise. ``allow_paraphrase`` is not carried
forward at all: a permission nothing can exercise is a field that will
eventually be read as an instruction.

**Numbers.** Invariant 22's display half: ``useGrouping:false`` for every
clinical quantity, and number + unit as one non-breaking atom. The rendering
itself is :func:`intake_platform.llm.units.render_quantity`, reused rather than
re-derived — a second implementation of "how a clinical quantity is written"
is precisely how the two drift and one of them starts printing ``1.500``.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Final

from clinical_schemas.common import FrozenModel, JsonValue
from intake_platform.llm.units import render_quantity
from protocols.triage.context import canonical_scalar
from pydantic import Field

from intake_voice_runtime.steps import NextStep, StepKind
from intake_voice_runtime.typed.affordance import AffordanceKind, SlotFacts

__all__ = ["NBSP", "TypedPrompt", "numeric_rail", "render_measure", "typed_prompt"]

NBSP: Final[str] = "\u00a0"
"""The character that keeps a magnitude and its unit on one line.

files/00 §2 rules that *"number + unit is one non-breaking atom"*. A normal
space lets a renderer wrap ``2,5`` onto one line and ``mg`` onto the next,
and a dose read without its unit is a dose read wrongly.
"""


class TypedPrompt(FrozenModel):
    """One question, as the typed lane displays it.

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


def render_measure(value: Decimal | int, unit: str | None) -> str:
    """One clinical quantity, written the one way it may be written.

    No digit grouping, no exponent, no locale separator, and the unit joined
    by a non-breaking space so the pair cannot be split (invariant 22).
    """
    rendered = render_quantity(value)
    return rendered if unit is None else f"{rendered}{NBSP}{unit}"


def numeric_rail(values: Mapping[str, JsonValue], facts: Mapping[str, SlotFacts]) -> dict[str, str]:
    """Every bound numeric value, rendered for the "Anlattıklarınız" rail.

    files/03 §4.6 invariant 30 pairs each spoken number with an ``inline``
    render on the same ``work_id``. In typed nothing is spoken, so the rail is
    not a counterpart — it is the only channel the number has, and it is
    rendered by :func:`render_measure` for exactly the same reason.

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
        rail[step_id] = render_measure(scalar, slot.unit)
    return rail
