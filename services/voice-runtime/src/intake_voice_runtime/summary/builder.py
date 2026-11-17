"""INT-085 — the patient summary: the patient's view of the clinician's note.

``build_patient_summary`` is the only way to turn a
:class:`~intake_voice_runtime.note.composer.ComposedNote` into a
:class:`~clinical_schemas.note.PatientSummary`. It takes the *composed* note
rather than the bare :class:`~clinical_schemas.note.PreVisitNote`, and that is
load-bearing: the note value has already lost some of what the summary needs.
``pmh`` records that an item came from a record, but not *which* record; and
after INT-084's composer the fact index is where a line's attribution, its
subject and the date a carried fact was first asserted actually live.

Five refusals, each because a friendlier surface is where the corresponding
guarantee is usually lost.

1. **A relative's item is refused, never relocated.** INT-084 established the
   rule at the composer and gave the reason: moving it silently hides the
   caller's bug. The summary adds exactly one new entry point —
   ``questions_for_doctor`` — and holds the same line there rather than
   quietly filing a relative's question as the patient's.
2. **Every line carries its marker**, not only the exceptional ones. A marker
   on the exceptions makes the unmarked lines read as endorsed, so the rule is
   "every line" with no card-dependent branch to get wrong. A carried line
   names **the date it was first recorded** — without it a carried fact reads
   as a current one, and on the patient's own screen there is no second source
   to catch it.
3. **A wellbeing signal is not filtered out, it is not an input.** See
   :mod:`intake_voice_runtime.summary.cards`: the note's fields are
   partitioned, not filtered, so two notes differing only in their screening
   scores build byte-identical summaries.
4. **A translated line shows the patient their own words, or there is no
   summary.** The note's job is to give the clinician a Turkish rendering with
   the original beside it; the summary's is the reverse — the patient reads
   the sentence they actually said, marked with the language they said it in,
   and the machine's version is not shown to them at all. A fact whose
   original is missing refuses the whole summary (INT-299).
5. **A RED note has no summary.** Invariant 21 makes RED three axes — route ×
   register × location — with its script pre-positioned on the device and
   triggered over the data channel. A card set is none of those three, and a
   RED sentence whose register is decided by page layout is the default the
   invariant forbids. The catalogue has no RED key and this function raises,
   so there is no path by which layout could become a register.

**Nothing here authors Turkish.** Every fixed string comes from the hash-bound
catalogue; all the builder adds to an authored segment is punctuation and, for
a carried fact, an ISO date. A test replaces every catalogue value with a
sentinel and asserts no letter survives into an authored segment.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from clinical_schemas.note import (
    AllergyItem,
    ImportedObjectiveItem,
    MedicationItem,
    PatientSummary,
    PmhItem,
    PreVisitNote,
    SelfReportedMeasure,
    SummaryCard,
)
from clinical_schemas.quantity import quantity_atom
from clinical_schemas.triage import TriageLevel

from intake_voice_runtime.note import (
    Attribution,
    AttributionRefused,
    ComposedNote,
    FactSubject,
    NoteFact,
    Sourced,
    SourceKind,
    facts_by_section,
)
from intake_voice_runtime.summary.cards import (
    SUMMARY_CARD_SECTIONS,
    BringItem,
    SummaryCardId,
)
from intake_voice_runtime.summary.copy import PatientSummaryCopy
from intake_voice_runtime.summary.readability import assert_patient_readable

__all__ = ["ComposedSummary", "SummaryLine", "SummaryRefused", "build_patient_summary"]

#: What separates a line's authored marker from the words it is about.
_SEPARATOR: Final = " — "

#: Returned instead of an original when this fact has already shown one. A
#: sentinel rather than ``None``: ``None`` is what an *absent* original looks
#: like, and that case refuses the summary — the two must not be spelled the
#: same way.
_ALREADY_SHOWN: Final = "\x00already-shown"

#: A reconciliation state a patient's own medication card must not carry.
#:
#: ``stopped`` is the clinician's word for a drug the patient is no longer on.
#: There is no patient-facing copy key for a reconciliation state — inventing
#: one would be authoring clinical copy — so a stopped drug could only appear
#: *unmarked*, and an unmarked stopped drug in a list headed "İlaçlarınız"
#: reads as current. It is dropped rather than worded; the clinician note still
#: carries it, with its state, where a reconciliation vocabulary exists.
_NOT_TAKEN: Final = "stopped"

#: Which card a note section's facts land on, inverted from the one table.
#:
#: Derived rather than restated, and *used* rather than checked: the card is
#: read off the fact's own section, so the table and the builder body cannot
#: disagree about where a line goes. A mismatch that has to be detected is a
#: mismatch that can happen; this one cannot be expressed.
_CARD_OF_SECTION: Final[Mapping[str, SummaryCardId]] = MappingProxyType(
    {section: card for card, sections in SUMMARY_CARD_SECTIONS.items() for section in sections}
)


class SummaryRefused(ValueError):
    """The summary may not be produced for this note at all."""


@dataclass(frozen=True, slots=True)
class SummaryLine:
    """One line of one card, split at the seam that matters.

    ``authored`` is the product's words and is measured by the readability
    gate. ``quoted`` is the patient's own — or a document's — and is **never**
    measured and never rewritten: rewriting what a patient said is its own
    defect, and failing a build on a long sentence somebody spoke at the
    microphone would be that defect with a deploy attached.
    """

    card: SummaryCardId
    section: str
    attribution: Attribution
    subject: FactSubject
    authored: str
    quoted: str

    @property
    def rendered(self) -> str:
        return f"{self.authored}{_SEPARATOR}{self.quoted}"


@dataclass(frozen=True, slots=True)
class ComposedSummary:
    """The summary and the line index behind it.

    The sidecar is the summary's answer to the question the note answers with
    ``ComposedNote.facts``: ``PatientSummary`` is four lists of strings, so the
    value alone cannot say which line was whose, and a test that can only read
    the value cannot prove a relative's condition stayed a relative's.
    """

    summary: PatientSummary
    lines: tuple[SummaryLine, ...]


def _marker(fact: NoteFact, copy: PatientSummaryCopy) -> str:
    """The authored half of a line.

    Mirrors :func:`intake_voice_runtime.note.render._marker` in *what it
    distinguishes* and differs in *what it names*. A relative is named,
    because whose condition it is, is the whole point. A carried fact names
    its date, for the same reason it does on the note. A record says only that
    it came from a document: which document is an internal id, and the records
    surface (files/02 §5.5) is where a patient goes to see the source snippet.
    A translated line names the locale the patient spoke, because the words
    beside the marker are theirs and the language is how they recognise them.

    The ``translation is not None`` guard is not defensive: the caller has
    already refused the fact without one (:meth:`_LineIndex.add`), and this
    branch is what keeps that refusal the *only* way such a fact is handled
    rather than silently falling through to an unmarked base.
    """
    base = copy.attribution(fact.attribution)
    if fact.attribution is Attribution.TRANSLATED and fact.translation is not None:
        return f"{base}: {fact.translation.source_locale}"
    if fact.attribution is Attribution.RELATIVE:
        return f"{base}: {copy.subject(fact.subject)}"
    if fact.attribution is Attribution.CARRIED and fact.span.kind is SourceKind.EARLIER_VISIT:
        return f"{base}: {fact.span.asserted_at}"
    return base


def _pmh_text(item: PmhItem) -> str:
    """The condition only. ``status`` and ``source`` are the clinician's axes
    and the marker already carries the one a patient needs."""
    return item.condition


def _medication_text(item: MedicationItem) -> str:
    return f"{item.name} · {item.dose}" if item.dose else item.name


def _allergy_text(item: AllergyItem) -> str:
    return f"{item.substance} · {item.reaction}" if item.reaction else item.substance


def _measure_text(item: SelfReportedMeasure, *, locale: str) -> str:
    # invariant 22, through the one renderer (INT-386): no grouping, the
    # patient's decimal point, and the number bound to its unit with a
    # non-breaking space so no layout can split the pair.
    return quantity_atom(item.magnitude, item.unit, locale=locale)


def _imported_text(item: ImportedObjectiveItem) -> str:
    return f"{item.summary} · {item.date}" if item.date else item.summary


def _story_texts(note: PreVisitNote) -> tuple[str, ...]:
    """The patient's own account, in their own words.

    The OLDCARTS decomposition is deliberately absent: it is the clinician's
    frame over the same story, and re-presenting a patient's words under
    clinical field names is the note's job, not the summary's. The patient
    already said all of it in the narrative.
    """
    return tuple(
        text for text in (note.chief_complaint.text, *note.chief_complaint.patient_goals) if text
    )


class _LineIndex:
    """Collects the lines and runs the build-time half of the readability gate."""

    def __init__(self, copy: PatientSummaryCopy) -> None:
        self._copy = copy
        self._lines: list[SummaryLine] = []
        self._translated_refs: set[str] = set()

    def add(self, fact: NoteFact, quoted: str) -> None:
        if fact.attribution is Attribution.TRANSLATED:
            quoted = self._original(fact)
            if quoted is _ALREADY_SHOWN:
                return
        card = _CARD_OF_SECTION[fact.section]
        authored = _marker(fact, self._copy)
        # The assembled marker is a string nobody authored — a catalogue value
        # joined to a subject or a date — so it is checked here as well as at
        # bind time. `quoted` is never checked: see SummaryLine.
        assert_patient_readable(authored, where=f"summary.{card.value}.marker")
        self._lines.append(
            SummaryLine(
                card=card,
                section=fact.section,
                attribution=fact.attribution,
                subject=fact.subject,
                authored=authored,
                quoted=quoted,
            )
        )

    def _original(self, fact: NoteFact) -> str:
        """What a translated line shows the patient: their own words.

        Never the rendering. A summary that shows a patient a machine version
        of what they said, with no way back to the sentence they actually
        spoke, is worse than showing nothing — so a fact whose original is
        gone refuses the **whole** summary rather than contributing a line the
        patient has no way to check.

        A fact that renders into several lines still records one utterance, so
        the original is shown once. Repeating it under each rendered line
        would read as several separate things the patient said.
        """
        if fact.translation is None:
            raise SummaryRefused(
                f"fact {fact.ref} is a translation whose original is not on the record, so "
                "the summary would be showing a machine version of the patient's own words "
                "with no way back to them — refused for the whole summary"
            )
        if fact.ref in self._translated_refs:
            return _ALREADY_SHOWN
        self._translated_refs.add(fact.ref)
        return fact.translation.original

    def for_card(self, card: SummaryCardId) -> tuple[SummaryLine, ...]:
        return tuple(line for line in self._lines if line.card is card)

    @property
    def lines(self) -> tuple[SummaryLine, ...]:
        return tuple(self._lines)


def _paired[T](
    composed: ComposedNote, section: str, values: Sequence[T]
) -> list[tuple[NoteFact, T]]:
    """Join a section's facts to the note values they were composed from.

    The composer files one fact per item in order, so the pairing is
    positional; the length check is here so a future composer change surfaces
    as a raise rather than as a line labelled with the wrong person's marker.
    """
    facts = facts_by_section(composed, section)
    if len(facts) != len(values):
        raise SummaryRefused(
            f"section {section!r} has {len(facts)} facts for {len(values)} values — "
            "the summary cannot label a line whose fact it cannot identify"
        )
    return list(zip(facts, values, strict=True))


def build_patient_summary(
    composed: ComposedNote,
    copy: PatientSummaryCopy,
    *,
    questions_for_doctor: Sequence[Sourced[str]] = (),
) -> ComposedSummary:
    """Build the patient-facing summary, or refuse.

    ``questions_for_doctor`` are the patient's own questions — files/13's
    ``expectations_wrapup.open_questions``, whose ``ask_tr`` is *"Doktorunuza
    sormak istediğiniz bir şey var mı?"*. They travel verbatim: a question is
    the one thing in this artefact the patient wrote for themselves.
    """
    note = composed.note
    if note.triage.level is TriageLevel.RED:
        raise SummaryRefused(
            "a RED result has no patient summary — invariant 21 routes it by "
            "register and location over the data channel, and a card set is "
            "neither axis"
        )

    index = _LineIndex(copy)

    story_fact = facts_by_section(composed, "chief_complaint")
    for fact in story_fact:
        for text in _story_texts(note):
            index.add(fact, text)
    for fact in facts_by_section(composed, "hpi"):
        if note.hpi.narrative:
            index.add(fact, note.hpi.narrative)

    for fact, condition in _paired(composed, "pmh", note.pmh):
        index.add(fact, _pmh_text(condition))
    for fact, medication in _paired(composed, "medications", note.medications):
        if medication.reconciliation != _NOT_TAKEN:
            index.add(fact, _medication_text(medication))
    for fact, allergy in _paired(composed, "allergies", note.allergies):
        index.add(fact, _allergy_text(allergy))
    for fact, measure in _paired(composed, "measurements", note.measurements):
        index.add(fact, _measure_text(measure, locale=note.meta.language))
    for fact, imported in _paired(composed, "imported_objective", note.imported_objective):
        index.add(fact, _imported_text(imported))

    # `family_social` carries two different things under one section id: the
    # relatives' conditions and the patient's own social history. Only the
    # first is summarised — the second's lines are open-map keys the caller
    # chose (`smoking.<key>`), and rendering a caller's key as patient-facing
    # text would be authoring copy at runtime.
    for fact in facts_by_section(composed, "family_social"):
        if fact.attribution is Attribution.RELATIVE:
            index.add(fact, fact.lines[0])

    questions: list[str] = []
    for question in questions_for_doctor:
        if question.attribution is not Attribution.PATIENT_SELF:
            raise AttributionRefused(
                f"a question attributed {question.attribution.value!r} is not the patient's "
                "own question — refused rather than relocated (INT-084)"
            )
        questions.append(question.value)

    bring: list[BringItem] = []
    if any(item.reconciliation != _NOT_TAKEN for item in note.medications):
        bring.append(BringItem.MEDICATIONS)
    if note.imported_objective:
        bring.append(BringItem.DOCUMENTS)

    cards: list[SummaryCard] = []
    for card in SUMMARY_CARD_SECTIONS:
        card_lines = index.for_card(card)
        if not card_lines:
            continue
        title = copy.card(card)
        assert_patient_readable(title, where=f"summary.{card.value}.title")
        cards.append(SummaryCard(title_tr=title, lines=tuple(line.rendered for line in card_lines)))

    bring_texts: list[str] = []
    for item in bring:
        text = copy.bring(item)
        assert_patient_readable(text, where=f"summary.bring.{item.value}")
        bring_texts.append(text)

    message = copy.triage_message(note.triage.level)
    assert_patient_readable(message, where=f"summary.triage_message.{note.triage.level.value}")

    return ComposedSummary(
        summary=PatientSummary(
            cards=tuple(cards),
            questions_for_doctor=tuple(questions),
            bring_list=tuple(bring_texts),
            triage_message_tr=message,
        ),
        lines=index.lines,
    )
