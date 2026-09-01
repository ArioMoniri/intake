"""INT-084 — what a fact in the pre-visit note *is*.

The acceptance clause is *"every fact carries source span"*. The usual shape
for that is a validator on the way out. This does what INT-083 did with the
``YELLOW_REVIEW`` ceiling and what INT-091 did with RED preemption: put the
requirement in the type, so there is nothing for a validator to catch.

Three axes ride together on :class:`Sourced`, and each one answers a failure
this repo has already met:

* **span** — files/10 §5 LLM09 and the ``notes`` threat-model row's *"[R] a
  fact in the note with no provenance"*. ``span`` is a keyword-only field with
  no default, so an unsourced fact is a ``TypeError`` at the call site.
* **attribution** — INT-282's finding: *the note mapper must not attribute a
  relative's condition to the patient*. Generalised here into
  :data:`SECTION_ATTRIBUTIONS`, a table a reviewer reads, in which
  ``RELATIVE`` appears in exactly one row.
* **subject** — who the line is *about*, which is what makes the attribution
  checkable rather than decorative. A ``RELATIVE`` fact must name a relative;
  every other attribution must name the patient.

The 04 §5 note already distinguishes some of this structurally
(``pmh.source``, ``medications.reconciliation``, ``family_social.family`` as
its own field). That is the exchange layer's half. This module is the half
the human renderers need, because "under a different heading" is not the same
guarantee as "labelled as somebody else's".
"""

from __future__ import annotations

import datetime
import enum
from collections.abc import Mapping
from dataclasses import KW_ONLY, dataclass, field
from types import MappingProxyType
from typing import Final

__all__ = [
    "SECTION_ATTRIBUTIONS",
    "Attribution",
    "AttributionRefused",
    "FactSubject",
    "NoteFact",
    "NoteGap",
    "NoteGapReason",
    "SourceKind",
    "SourceSpan",
    "Sourced",
]


class AttributionRefused(ValueError):
    """A fact was offered to a note section that does not accept its
    attribution. Refused rather than relabelled: a relative's condition
    filed under the patient's history is a false clinical statement, and
    silently moving it would be a second one."""


class Attribution(enum.StrEnum):
    """Who is asserting the fact, and on what standing.

    The set is closed. A sixth kind of assertion would be a new row in
    :data:`SECTION_ATTRIBUTIONS` and therefore a visible review.
    """

    #: the patient, about themselves, in this session
    PATIENT_SELF = "patient_self"
    #: the patient, about a relative — files/04 §5 ``family_social.family``
    RELATIVE = "relative"
    #: recorded at an earlier visit and not yet re-asserted in this one
    #: (INT-247 carried facts; files/09 §3 ``PatientOverlay``)
    CARRIED = "carried"
    #: extracted from an uploaded document or record (files/03 §4.6)
    RECORD = "record"
    #: a fired rules-engine rule (invariant 1 — the only producer of a level)
    RULES_ENGINE = "rules_engine"
    #: an LLM candidate flag, clinician-review material only (invariant 1)
    LLM_CANDIDATE = "llm_candidate"


class FactSubject(enum.StrEnum):
    """Who the fact is *about*. The relative set is INT-282's — the four the
    HBYS schema enumerates plus the three ``fh_detail`` covers."""

    PATIENT = "patient"
    MOTHER = "mother"
    FATHER = "father"
    BROTHER = "brother"
    SISTER = "sister"
    CHILD = "child"
    GRANDPARENT = "grandparent"
    OTHER_RELATIVE = "other_relative"

    @property
    def is_relative(self) -> bool:
        return self is not FactSubject.PATIENT


class SourceKind(enum.StrEnum):
    """Where a span points. One locator shape per kind, all of them ids and
    offsets — never narrative (invariant 6)."""

    UTTERANCE = "utterance"
    DOCUMENT = "document"
    EARLIER_VISIT = "earlier_visit"
    RULE = "rule"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Where a fact came from, precisely enough to go back and look.

    Built through the four classmethods rather than the constructor, because
    each kind needs a different locator and a single flat constructor would
    let a caller build a document span with an utterance offset."""

    kind: SourceKind
    ref: str
    char_start: int | None = None
    char_end: int | None = None
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    asserted_at: datetime.date | None = None

    @classmethod
    def utterance(cls, *, work_id: str, char_start: int, char_end: int) -> SourceSpan:
        """A span of one transcribed turn, addressed by the Work that carried
        it (files/03 §4.5 ``work_id``). Offsets, never the text itself."""
        if char_start < 0:
            raise ValueError("char_start is a 0-based offset and cannot be negative")
        if char_end < char_start:
            raise ValueError("char_end precedes char_start — that is not a span")
        return cls(kind=SourceKind.UTTERANCE, ref=work_id, char_start=char_start, char_end=char_end)

    @classmethod
    def document(
        cls,
        *,
        document_ref: str,
        page: int | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> SourceSpan:
        """files/03 §4.6's Provenance: the stored document, a page and a box."""
        if page is not None and page < 1:
            raise ValueError("page numbers are 1-based")
        return cls(kind=SourceKind.DOCUMENT, ref=document_ref, page=page, bbox=bbox)

    @classmethod
    def earlier_visit(cls, *, visit_ref: str, asserted_at: datetime.date) -> SourceSpan:
        """A carried fact's origin. The date is part of the locator because a
        carried fact without its date is indistinguishable from a current
        one, which is the whole failure INT-247 exists to prevent."""
        return cls(kind=SourceKind.EARLIER_VISIT, ref=visit_ref, asserted_at=asserted_at)

    @classmethod
    def rule(cls, *, rule_id: str) -> SourceSpan:
        return cls(kind=SourceKind.RULE, ref=rule_id)

    @property
    def locator(self) -> str:
        """A stable, language-neutral address. Ids and offsets only."""
        if self.kind is SourceKind.UTTERANCE:
            return f"{self.kind.value}:{self.ref}:{self.char_start}-{self.char_end}"
        if self.kind is SourceKind.DOCUMENT:
            parts = [self.kind.value, self.ref]
            if self.page is not None:
                parts.append(f"p{self.page}")
            if self.bbox is not None:
                parts.append(",".join(f"{value:g}" for value in self.bbox))
            return ":".join(parts)
        if self.kind is SourceKind.EARLIER_VISIT:
            return f"{self.kind.value}:{self.ref}:{self.asserted_at}"
        return f"{self.kind.value}:{self.ref}"


@dataclass(frozen=True, slots=True)
class Sourced[T]:
    """One 04 §5 item with the three axes attached.

    ``span`` is keyword-only and has no default. That single fact is the
    acceptance clause: ``compose`` accepts no bare item anywhere, so a note
    cannot contain a fact whose origin nobody recorded.
    """

    value: T
    _: KW_ONLY
    attribution: Attribution
    span: SourceSpan
    subject: FactSubject = FactSubject.PATIENT

    def __post_init__(self) -> None:
        if self.attribution is Attribution.RELATIVE and not self.subject.is_relative:
            raise ValueError(
                "a relative attribution must name the relative in `subject` — "
                "an unattributed relative fact is the INT-282 failure"
            )
        if self.attribution is not Attribution.RELATIVE and self.subject.is_relative:
            raise ValueError(
                f"subject {self.subject.value!r} is a relative, so the attribution must be "
                f"{Attribution.RELATIVE.value!r} and not {self.attribution.value!r}"
            )


@dataclass(frozen=True, slots=True)
class NoteFact:
    """One placed fact: what it says, where it sits, who said it, and where to
    go and check. ``ref`` is the short handle every renderer prints beside the
    line and resolves in its provenance block."""

    ref: str
    section: str
    attribution: Attribution
    subject: FactSubject
    lines: tuple[str, ...]
    span: SourceSpan

    @property
    def provenance_line(self) -> str:
        """The exchange-layer rendering: language-neutral, one line, stable."""
        return (
            f"{self.ref}|{self.section}|{self.attribution.value}|"
            f"{self.subject.value}|{self.span.locator}"
        )


class NoteGapReason(enum.StrEnum):
    """Why something is absent from a partial note.

    These are four different facts and the enum is the reason they can never
    become one string:

    * ``deferred_environment`` — files/02 §33: a third party was audible, so
      the section was not asked at all. The clinician's marker is that file's
      verbatim ``eksik: ortam uygun değildi``.
    * ``declined`` — the patient was asked and chose not to answer. A
      refusal is a disclosure decision, not a setting.
    * ``session_ended`` — the session stopped before the section (files/02
      §34's "Sıranız geldi" checkpoint is the common case, and files/02 §2
      calls it the most common way a detailed session ends).
    * ``unresolved_precondition`` — the step was obliged but its gate never
      resolved. See the module note in :mod:`intake_voice_runtime.note` for
      why the note keeps this category at all.
    """

    DEFERRED_ENVIRONMENT = "deferred_environment"
    DECLINED = "declined"
    SESSION_ENDED = "session_ended"
    UNRESOLVED_PRECONDITION = "unresolved_precondition"


@dataclass(frozen=True, slots=True)
class NoteGap:
    """One thing the note does not have, and why.

    There is deliberately no free-text field: a reason a caller can write is a
    reason two different causes can be spelled the same way.
    """

    section: str
    reason: NoteGapReason
    unit: str = field(default="")

    @property
    def code(self) -> str:
        """The ``data_gaps`` entry: section, reason and the unit that is
        missing, language-neutral so every renderer localises it itself."""
        return (
            f"{self.section}:{self.reason.value}:{self.unit}"
            if self.unit
            else (f"{self.section}:{self.reason.value}")
        )


#: Which attributions each files/04 §5 section admits.
#:
#: This table is INT-282's finding stated once, where a reviewer reads it.
#: ``RELATIVE`` appears in exactly one row, and a test asserts that — so a
#: relative's condition has one home in the note and it is not the patient's
#: history. ``imported_objective`` is the mirror image: only a record may sit
#: there, so a sentence the patient said cannot be printed as an imported
#: result.
SECTION_ATTRIBUTIONS: Final[Mapping[str, frozenset[Attribution]]] = MappingProxyType(
    {
        "chief_complaint": frozenset({Attribution.PATIENT_SELF}),
        "hpi": frozenset({Attribution.PATIENT_SELF}),
        "ros_pertinent": frozenset({Attribution.PATIENT_SELF}),
        "pmh": frozenset({Attribution.PATIENT_SELF, Attribution.RECORD, Attribution.CARRIED}),
        "medications": frozenset(
            {Attribution.PATIENT_SELF, Attribution.RECORD, Attribution.CARRIED}
        ),
        "allergies": frozenset({Attribution.PATIENT_SELF, Attribution.RECORD, Attribution.CARRIED}),
        "family_social": frozenset({Attribution.PATIENT_SELF, Attribution.RELATIVE}),
        "measurements": frozenset({Attribution.PATIENT_SELF}),
        "imported_objective": frozenset({Attribution.RECORD}),
    }
)


def check_admissible(section: str, sourced: Sourced[object]) -> None:
    """Refuse a fact its section does not accept. Raises, never relabels."""
    admitted = SECTION_ATTRIBUTIONS[section]
    if sourced.attribution not in admitted:
        raise AttributionRefused(
            f"section {section!r} does not accept an attribution of "
            f"{sourced.attribution.value!r} (admits: "
            f"{', '.join(sorted(a.value for a in admitted))})"
        )
