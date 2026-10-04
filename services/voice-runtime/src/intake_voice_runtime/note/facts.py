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
import re
from collections.abc import Mapping
from dataclasses import KW_ONLY, dataclass, field
from types import MappingProxyType
from typing import Final

from intake_voice_runtime.note.translation import TranslatedText, TranslatorUnidentified

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
    "TranslatedText",
    "TranslatorUnidentified",
]


#: ``intake_platform.records.index.item_ref_of``'s shape. Spelled here rather
#: than imported so the note's span type keeps no dependency on the index.
_ITEM_REF: Final = re.compile(r"ri_[0-9a-f]{32}")


class AttributionRefused(ValueError):
    """A fact was offered to a note section that does not accept its
    attribution. Refused rather than relabelled: a relative's condition
    filed under the patient's history is a false clinical statement, and
    silently moving it would be a second one."""


class Attribution(enum.StrEnum):
    """Who is asserting the fact, and on what standing.

    The set is closed and a test walks it. A further kind of assertion would
    be a new row in :data:`SECTION_ATTRIBUTIONS` and therefore a visible
    review — which is the point: INT-299 added ``TRANSLATED``, and the closure
    test is what stops a later locale quietly adding a second translated-ish
    class beside it ("post-edited", "interpreted", "clinician-translated"),
    each of which would be a different clinical claim wearing one word.
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
    #: the patient, about themselves, in a language the note is not written
    #: in — so what the clinician reads is a machine's rendering and not the
    #: sentence the patient said (INT-299). The words themselves are retained
    #: on the fact as a
    #: :class:`~intake_voice_runtime.note.translation.TranslatedText`.
    TRANSLATED = "translated"


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
    #: The confirmed record item a document span cites (INT-123) — the id the
    #: record index derives from the item's source box, so a clinician's "where
    #: did this line come from?" resolves to one item, not just to a page.
    item_ref: str | None = None

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
        item_ref: str | None = None,
    ) -> SourceSpan:
        """files/03 §4.6's Provenance: the stored document, a page and a box —
        and, for a retrieved record item, the item's id (INT-123)."""
        if page is not None and page < 1:
            raise ValueError("page numbers are 1-based")
        if item_ref is not None and not _ITEM_REF.fullmatch(item_ref):
            raise ValueError(
                "an item ref is the record index's derived id (ri_ + 32 hex), never a "
                "line of the document (invariant 6)"
            )
        return cls(
            kind=SourceKind.DOCUMENT, ref=document_ref, page=page, bbox=bbox, item_ref=item_ref
        )

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
            if self.item_ref is not None:
                parts.append(self.item_ref)
            return ":".join(parts)
        if self.kind is SourceKind.EARLIER_VISIT:
            return f"{self.kind.value}:{self.ref}:{self.asserted_at}"
        return f"{self.kind.value}:{self.ref}"


@dataclass(frozen=True, slots=True)
class Sourced[T]:
    """One 04 §5 item with the axes attached.

    ``span`` is keyword-only and has no default. That single fact is the
    acceptance clause: ``compose`` accepts no bare item anywhere, so a note
    cannot contain a fact whose origin nobody recorded.

    ``translation`` is INT-299's half and it is an *equivalence* rather than
    an optional extra: a ``TRANSLATED`` item without one is refused, because
    there would be no way back to what the patient said; and an item that
    carries one without the ``TRANSLATED`` attribution is refused too, because
    that is a machine's sentence printed as ``hasta beyanı`` — the exact
    defect the class exists to prevent.
    """

    value: T
    _: KW_ONLY
    attribution: Attribution
    span: SourceSpan
    subject: FactSubject = FactSubject.PATIENT
    translation: TranslatedText | None = None

    def __post_init__(self) -> None:
        if self.attribution is Attribution.TRANSLATED and self.translation is None:
            raise TranslatorUnidentified(
                "a translated item must carry the original it was translated from and the "
                "translator that produced it; rendering it unattributed would put a "
                "machine's sentence on the record as the patient's own"
            )
        if self.attribution is not Attribution.TRANSLATED and self.translation is not None:
            raise ValueError(
                f"an item carrying a translation must be attributed "
                f"{Attribution.TRANSLATED.value!r}, not {self.attribution.value!r}: "
                "a machine rendering labelled as a direct patient statement attributes "
                "to the patient a sentence they did not say"
            )
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
    #: The patient's own words and the translator that rendered them, for a
    #: ``TRANSLATED`` fact. It sits here, on the fact, rather than in a
    #: sidecar a renderer might not read: ``lines`` is the rendering and this
    #: is the original, and the two travel together to every surface.
    translation: TranslatedText | None = None

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
    * ``not_asked_proxy`` — INT-483, ADR-040: someone answered for the patient
      and the pack skips this item in a proxy session (owner decision D24
      answer 1Y). Nobody was asked and nobody said no, so it is none of the
      other four — and never a negative.
    """

    DEFERRED_ENVIRONMENT = "deferred_environment"
    DECLINED = "declined"
    SESSION_ENDED = "session_ended"
    UNRESOLVED_PRECONDITION = "unresolved_precondition"
    NOT_ASKED_PROXY = "not_asked_proxy"


@dataclass(frozen=True, slots=True)
class NoteGap:
    """One thing the note does not have, and why.

    There is deliberately no free-text field: a reason a caller can write is a
    reason two different causes can be spelled the same way.
    """

    section: str
    reason: NoteGapReason
    unit: str = field(default="")

    @classmethod
    def not_asked_proxy(cls, step_id: str) -> NoteGap:
        """The gap a proxy-skipped step leaves (ADR-040), from its
        ``<section>.<slot>`` step id — the engine's ``proxy_skipped``."""
        section, _, unit = step_id.partition(".")
        return cls(section=section, reason=NoteGapReason.NOT_ASKED_PROXY, unit=unit)

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
#: result — and, since INT-299, so a translated *document* cannot arrive
#: through the note's attribution axis either. That is a document-extraction
#: question with its own provenance (files/03 §4.6), not this one.
#:
#: ``TRANSLATED`` is admitted in exactly the rows that admit ``PATIENT_SELF``,
#: and :data:`_SELF_REPORTED` is why the two cannot drift: a translated answer
#: goes wherever the patient's own answer goes, stated once rather than typed
#: eight times. A row where they differed would be a place the distinction
#: was made for a reason nobody wrote down.
_SELF_REPORTED: Final[frozenset[Attribution]] = frozenset(
    {Attribution.PATIENT_SELF, Attribution.TRANSLATED}
)

SECTION_ATTRIBUTIONS: Final[Mapping[str, frozenset[Attribution]]] = MappingProxyType(
    {
        "chief_complaint": _SELF_REPORTED,
        "hpi": _SELF_REPORTED,
        "ros_pertinent": _SELF_REPORTED,
        "pmh": _SELF_REPORTED | {Attribution.RECORD, Attribution.CARRIED},
        "medications": _SELF_REPORTED | {Attribution.RECORD, Attribution.CARRIED},
        "allergies": _SELF_REPORTED | {Attribution.RECORD, Attribution.CARRIED},
        "family_social": _SELF_REPORTED | {Attribution.RELATIVE},
        "measurements": _SELF_REPORTED,
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
