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
clinical quantity, and number + unit as one non-breaking atom.

⚠ **A recorded defect, not a decision taken here.** This is the *fourth*
private implementation of "how a clinical quantity is written" on this tree —
``clinical_schemas.mappers.document``, ``note.composer`` and
``summary.builder`` each keep their own ``_NBSP`` and their own format call,
and no issue owns unifying them. :func:`render_measure` deliberately produces
the **same bytes** as those three for the same input, so the fourth copy
cannot be the one that starts printing ``1.500``; the finding is recorded in
docs/evidence/INT-096.md rather than fixed here, because a single renderer
would touch the note and the patient summary and belongs to whichever issue
owns them. In particular the decimal separator is left exactly as the other
three print it: files/00 §2 settles grouping and the atom, not the separator,
and diverging here alone would create the drift this note exists to prevent.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Final

from clinical_schemas.common import FrozenModel, JsonValue
from protocols.triage.context import canonical_scalar
from pydantic import Field

from intake_voice_runtime.steps import NextStep, StepKind
from intake_voice_runtime.typed.affordance import AffordanceKind, SlotFacts

__all__ = ["NBSP", "TypedPrompt", "numeric_rail", "render_measure", "typed_prompt"]

NBSP: Final[str] = " "
"""The character that keeps a magnitude and its unit on one line.

files/00 §2 rules that *"number + unit is one non-breaking atom"*. A normal
space lets a renderer wrap ``2,5`` onto one line and ``mg`` onto the next, and
a dose read without its unit is a dose read wrongly.
"""


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


def render_measure(value: Decimal | int, unit: str | None) -> str:
    """One clinical quantity, written the one way it may be written.

    No digit grouping, no exponent, and the unit joined by a non-breaking
    space so the pair cannot be split by a line break (invariant 22).
    ``format(..., "f")`` is what removes the exponent: ``Decimal("1E+3")``
    would otherwise render as ``1E+3``, and a dose in scientific notation on a
    patient's screen is unreadable in the way that gets guessed at.
    """
    rendered = format(value, "f") if isinstance(value, Decimal) else str(value)
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
