"""The SOAP rendering of a composed note (INT-084).

files/03 §11: the clinician pre-visit note is *"SOAP-compatible (S =
patient-reported; O = imported objective data; A/P left for the clinician; an
optional 'considerations' block lists patterns, not diagnoses)"*. That is
exactly the layout below, and the A and P blocks are rendered **present and
empty** rather than omitted: a clinician has to be able to see that the
assessment slot was left for them, not that the renderer dropped it.

**Headings are the files/04 §5 technical ids, not Turkish prose.** The FHIR
document mapper made the same choice for the same reason (*"human headings
belong to the renderers … not the exchange layer"*), and here it is also
CLAUDE.md invariant 5: `tr` resource keys are the source of truth, and the
clinician-facing Turkish headings belong to the clinician view (INT-151) with
its own catalogue. The only Turkish on this page is the patient's own words,
which are reproduced, and the fixed legal strings, which are bound.

Every content line carries the :class:`~clinical_schemas.provenance.NoteFact`
it came from, and a fact cannot exist without a span — so *"every fact carries
source span"* survives the render rather than being re-checked in it. The
``sources`` block prints the index a clinician reads back against.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final

from clinical_schemas.composition import AttributedNote
from clinical_schemas.provenance import NoteFact, SourceSpan
from clinical_schemas.triage import RulesTriageResult
from intake_platform.legal import LegalStrings, LegalStringsMissingError

from intake_api.note.strings import (
    NOTE_DISCLAIMER_KEY,
    NOTE_SCREENING_AI_LABEL_KEY,
    note_string_keys,
)

__all__ = [
    "LineKind",
    "RenderedLine",
    "RenderedNote",
    "UnattributedLineError",
    "render_soap",
]

#: S — what the patient reported (files/03 §11).
SUBJECTIVE_SECTIONS: Final[tuple[str, ...]] = (
    "chief_complaint",
    "hpi",
    "ros_pertinent",
    "pmh",
    "medications",
    "allergies",
    "family_social",
    "screening",
)

#: O — measured or imported, not reported (files/03 §11; files/03 §4.7.6 puts
#: the speech measures here and never under screening).
OBJECTIVE_SECTIONS: Final[tuple[str, ...]] = ("konusma_ozellikleri", "imported_objective")

#: Blocks that follow A/P: patterns, questions and what the patient confirmed.
TRAILING_SECTIONS: Final[tuple[str, ...]] = (
    "considerations",
    "suggested_focus_questions",
    "patient_confirmed_sections",
)


class LineKind(enum.StrEnum):
    """What a rendered line is, so a consumer never has to parse prose."""

    HEADER = "header"
    META = "meta"
    FACT = "fact"
    RESERVED = "reserved"
    TRIAGE = "triage"
    CANDIDATE = "candidate"
    GAP = "gap"
    SOURCE = "source"
    LEGAL = "legal"


class UnattributedLineError(ValueError):
    """A content line that names no fact, or a non-content line that names one."""


@dataclass(frozen=True, slots=True)
class RenderedLine:
    """One line. ``fact`` is set if and only if ``kind`` is ``FACT``.

    Enforced here rather than asserted downstream: a ``FACT`` line without a
    fact is a rendered clinical statement with no provenance, which is the one
    thing this issue exists to make impossible. A ``NoteFact`` cannot exist
    without a span, so a content line cannot exist without one either.
    """

    kind: LineKind
    text: str
    fact: NoteFact | None = None

    def __post_init__(self) -> None:
        if (self.kind is LineKind.FACT) != (self.fact is not None):
            raise UnattributedLineError(
                "a content line carries its fact, and only a content line may"
            )


@dataclass(frozen=True, slots=True)
class RenderedNote:
    """The note as lines, plus the binding that proves what it said."""

    lines: tuple[RenderedLine, ...]
    legal_strings_version: str
    legal_strings_hash: str

    def text(self) -> str:
        return "".join(f"{line.text}\n" for line in self.lines)


def _span_text(span: SourceSpan) -> str:
    page = f" p{span.page}" if span.page is not None else ""
    return f"{span.kind.value} {span.source_ref}[{span.start}:{span.end}]{page}"


def _triage_lines(triage: RulesTriageResult) -> list[RenderedLine]:
    """The rules result, all three axes. ``register`` and ``location`` are
    required on RED with no permitted default (CLAUDE.md invariant 21), so
    when they are present they are printed rather than summarised away."""
    lines = [RenderedLine(LineKind.TRIAGE, f"level: {triage.level.value}")]
    if triage.register is not None:
        lines.append(RenderedLine(LineKind.TRIAGE, f"register: {triage.register.value}"))
    if triage.location is not None:
        lines.append(RenderedLine(LineKind.TRIAGE, f"location: {triage.location.value}"))
    lines.extend(
        RenderedLine(LineKind.TRIAGE, f"rule {rule.id}: {rule.evidence}") for rule in triage.rules
    )
    return lines


def _require(strings: LegalStrings, note: AttributedNote) -> None:
    absent = [
        key
        for key in note_string_keys(screening_scored=note.screening_scored())
        if not strings.values.get(key, "").strip()
    ]
    if absent:
        raise LegalStringsMissingError(
            "the note cannot be rendered without its fixed legal strings: "
            + ", ".join(sorted(absent))
        )


def render_soap(note: AttributedNote, *, strings: LegalStrings) -> RenderedNote:
    """Render one composed note. Deterministic for equal inputs."""
    _require(strings, note)
    meta = note.note.meta
    by_section: dict[str, list[NoteFact]] = {}
    for fact in note.facts:
        by_section.setdefault(fact.section, []).append(fact)

    lines: list[RenderedLine] = [
        RenderedLine(LineKind.HEADER, "previsit_note"),
        RenderedLine(LineKind.META, f"visit_id: {meta.visit_id}"),
        RenderedLine(LineKind.META, f"generated_at: {meta.generated_at.isoformat()}"),
        RenderedLine(LineKind.META, f"protocol_hash: {meta.protocol_hash}"),
        RenderedLine(LineKind.META, f"mode: {meta.mode}"),
        RenderedLine(LineKind.META, f"language: {meta.language}"),
        RenderedLine(LineKind.META, f"model: {meta.model}"),
        RenderedLine(LineKind.META, f"prompt_version: {meta.prompt_version}"),
        RenderedLine(LineKind.META, f"legal_strings_version: {strings.version}"),
        RenderedLine(LineKind.META, f"legal_strings_sha256: {strings.text_hash}"),
    ]

    def block(section_ids: tuple[str, ...]) -> None:
        for section in section_ids:
            for fact in by_section.get(section, ()):
                lines.append(RenderedLine(LineKind.FACT, f"{fact.field_ref}: {fact.text}", fact))

    lines.append(RenderedLine(LineKind.HEADER, "S"))
    block(SUBJECTIVE_SECTIONS)
    lines.append(RenderedLine(LineKind.HEADER, "O"))
    block(OBJECTIVE_SECTIONS)
    lines.append(RenderedLine(LineKind.HEADER, "A"))
    lines.append(RenderedLine(LineKind.RESERVED, "-"))
    lines.append(RenderedLine(LineKind.HEADER, "P"))
    lines.append(RenderedLine(LineKind.RESERVED, "-"))
    for section in TRAILING_SECTIONS:
        if by_section.get(section):
            lines.append(RenderedLine(LineKind.HEADER, section))
            block((section,))

    lines.append(RenderedLine(LineKind.HEADER, "triage"))
    lines.extend(_triage_lines(note.rules_triage))
    triage = note.note.triage
    if triage.llm_candidates:
        lines.append(RenderedLine(LineKind.HEADER, "llm_candidates"))
        lines.extend(
            RenderedLine(
                LineKind.CANDIDATE,
                f"llm_candidate: {flag.text} | evidence: {flag.evidence}",
            )
            for flag in triage.llm_candidates
        )
    if note.note.data_gaps:
        lines.append(RenderedLine(LineKind.HEADER, "data_gaps"))
        lines.extend(RenderedLine(LineKind.GAP, gap) for gap in note.note.data_gaps)

    lines.append(RenderedLine(LineKind.HEADER, "sources"))
    for fact in note.facts:
        trail = " ; ".join(_span_text(span) for span in fact.spans)
        lines.append(RenderedLine(LineKind.SOURCE, f"{fact.field_ref} <- {trail}"))

    lines.append(RenderedLine(LineKind.HEADER, "legal"))
    lines.append(RenderedLine(LineKind.LEGAL, strings.values[NOTE_DISCLAIMER_KEY]))
    if note.screening_scored():
        lines.append(RenderedLine(LineKind.LEGAL, strings.values[NOTE_SCREENING_AI_LABEL_KEY]))

    return RenderedNote(
        lines=tuple(lines),
        legal_strings_version=strings.version,
        legal_strings_hash=strings.text_hash,
    )
