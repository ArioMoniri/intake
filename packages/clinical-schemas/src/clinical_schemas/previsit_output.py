"""``PreVisitOutput`` — the finished previsit in the one shape a hospital
receives it in (owner directive: *"after the previsit is done write output
version of json … the Acıbadem side will then send a request there to get the
previsit details of json for that patient with the same structure"*).

**Why this is not ``PreVisitNote``.** The note is the *working* artefact:
``notes.payload`` is rewritten in place on every save (INT-197
``upsert_note``) and its shape mirrors the review screen, whose sections the
patient can re-scope until the moment they send. What another organisation
joins to its own record has to be the opposite of that — frozen at the instant
the previsit finished, versioned by an id the receiver can branch on, and
explicit about its own provenance. So this is a separate document with its own
``schema_version``, and the note stays what it is.

Three of this repository's invariants are carried in the *types* here rather
than in whichever route happens to serve them. The receiver is another
organisation's software; a rule that lives in one serving path is a rule the
next serving path will not inherit.

**Invariant 1 — RED/YELLOW come only from ``packages/protocols/triage``.**
``triage`` is a union discriminated on ``source`` with exactly two members:
:class:`~clinical_schemas.triage.RulesTriageResult`, which is rules-only by
construction and already refuses a non-GREEN level naming no fired rule, and
:class:`TriageNotEvaluated`. ``LlmCandidateTriage`` is deliberately **not** a
member, so an LLM judgement has exactly one home in this document — the
sibling ``llm_candidates`` list — and no field it could be written into that a
receiver would read as a routing level. ``None`` is not a member either: a
missing key beside a list of candidate flags reads as *nothing fired*, which
is the same laundering by a quieter route. An absent determination has to say
so out loud.

**Invariant 22 — numbers never cross a representation boundary unguarded.**
:class:`OutputMeasurement` binds a magnitude to its unit in one object, so a
receiver cannot pick up one without the other, and the magnitude is typed
:data:`~clinical_schemas.common.JsonValue` — the one carrier whose JSON form
INT-309/ADR-030 defines (a tagged string, ``"~d38.50"``, which survives the
round trip with its declared scale). No second encoding is defined here: the
codec sits on the shared alias, so this document inherits it without an edit.

**Invariant 6 — ids, never values.** No field of this document can carry a
direct identifier. The hospital's own ``patient_number`` is what the *request*
names; the read-back echoes it from there (``intake_api.previsit_output``), so
no table and no serialised document in this repository holds it.
"""

from __future__ import annotations

import enum
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field

from clinical_schemas.common import FrozenModel, JsonValue, Ref
from clinical_schemas.note import MeasureCode
from clinical_schemas.triage import CandidateFlag, RulesTriageResult

__all__ = [
    "PREVISIT_OUTPUT_SCHEMA_ID",
    "NotEvaluatedReason",
    "OutputMeasurement",
    "OutputSection",
    "OutputTriage",
    "PreVisitOutput",
    "TriageNotEvaluated",
]

#: The versioned identity a receiver switches on. Same convention as every
#: other schema in this package (``clinical_schemas.common.schema_id``); it is
#: spelled as a literal because it is also the ``Literal`` type of the field.
PREVISIT_OUTPUT_SCHEMA_ID: Final = "intake.clinical.previsit_output.v1"


class OutputSection(FrozenModel):
    """One section of the finished previsit, as the patient reviewed it.

    The id set is the note's own (``chief_complaint`` / ``hpi`` /
    ``medications`` today) rather than a second vocabulary invented for the
    hospital: a receiver joining on a section id must be joining on the id the
    patient's own share scope was expressed in, or the two can disagree about
    what was sent.
    """

    id: Ref = Field(description="Section id, the same id the share scope names.")
    title_tr: str = Field(
        min_length=1, description="Section heading in Turkish (invariant 5: tr is the source)."
    )
    lines: tuple[str, ...] = Field(
        min_length=1, description="The section's lines, verbatim as the patient confirmed them."
    )


class OutputMeasurement(FrozenModel):
    """A self-reported quantity: magnitude and unit as one indivisible atom.

    CLAUDE.md invariant 22 — *number + unit is one non-breaking atom* — is a
    typing decision here, not a rendering one. A hospital that read a
    magnitude out of one field and a unit out of another could pair them
    wrongly; a hospital that reads this object cannot.
    """

    code: MeasureCode = Field(description="Which self-reported measure this is (files/04 §5).")
    magnitude: JsonValue = Field(
        description="Exact magnitude on the shared JSON carrier — a Decimal keeps its "
        "declared scale across the wire (INT-309/ADR-030); never a float."
    )
    unit: str = Field(
        min_length=1,
        description="Unit as the patient's control was labelled; never silently converted.",
    )


class NotEvaluatedReason(enum.StrEnum):
    """Why no rules-engine determination accompanies this previsit.

    A closed set, because this value is the receiver's cue about what it is
    NOT being told, and free text there would be a place to write a level in
    prose.
    """

    #: The path that produced this output does not run the triage rules engine
    #: (the INT-197 note surface). Nothing fired because nothing was asked.
    RULES_ENGINE_NOT_ON_THIS_PATH = "rules_engine_not_on_this_path"


class TriageNotEvaluated(FrozenModel):
    """ "No rules-engine determination exists for this previsit", stated.

    The alternative — omitting ``triage`` — reads as GREEN to any receiver
    that has ever seen a GREEN document, which is exactly the assertion this
    repository may not make without a rule having fired (invariant 1).
    """

    source: Literal["not_evaluated"] = Field(
        default="not_evaluated",
        description="Provenance discriminator: no rules-engine determination (invariant 1).",
    )
    reason: NotEvaluatedReason = Field(
        description="Why the rules engine produced nothing, from a closed set."
    )


type OutputTriage = Annotated[RulesTriageResult | TriageNotEvaluated, Field(discriminator="source")]
"""Discriminated on ``source``. The two members are the only two things this
document may say about triage; ``LlmCandidateTriage`` is not among them."""


class PreVisitOutput(FrozenModel):
    """The frozen, versioned previsit a hospital fetches.

    Keyed on the visit and nothing else. The hospital's ``patient_number``
    resolves to a patient through the Tokenizer at request time and is echoed
    from the request into the response envelope, so this document — the thing
    that is actually stored — names no person at all.
    """

    schema_version: Literal["intake.clinical.previsit_output.v1"] = Field(
        default=PREVISIT_OUTPUT_SCHEMA_ID,
        description="The versioned identity of this structure; a receiver branches on it.",
    )
    visit_ref: Ref = Field(description="The visit (intake session) this output was produced from.")
    completed_at: AwareDatetime = Field(
        description="When the previsit finished — the output's own clock, never the row's."
    )
    locale: str = Field(
        min_length=2,
        description="The language the patient was actually asked in (INT-296 sessions.locale).",
    )
    protocol_id: Ref = Field(description="Which protocol container ran (files/04 §5 meta).")
    protocol_version: Ref = Field(description="Its exact version, for reproducibility.")
    proxy_reported: bool = Field(
        description="files/06 §6 — a companion answered on the patient's behalf. A clinician "
        "must be able to tell a reported symptom from an observed one before reading a word."
    )
    third_party_present: bool = Field(
        description="files/02 §3 — someone else was in the room during the intake."
    )
    sections: tuple[OutputSection, ...] = Field(
        min_length=1, description="The sections this output carries (see the serving filter)."
    )
    measurements: tuple[OutputMeasurement, ...] = Field(
        default=(), description="Self-reported quantities, each an indivisible number+unit atom."
    )
    triage: OutputTriage = Field(
        description="The rules-engine determination, or an explicit statement that none exists. "
        "Never derived from llm_candidates (invariant 1)."
    )
    llm_candidates: tuple[CandidateFlag, ...] = Field(
        default=(),
        description="LLM candidate concerns — clinician-review material with a YELLOW_REVIEW "
        "ceiling (files/03 §4.6). A sibling of triage, never a component of it.",
    )
