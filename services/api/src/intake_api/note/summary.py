"""The patient summary, and the allow-list that decides what may be in one
(INT-085).

files/03 §11 calls it *"Anlattıklarınız"*: section cards, B1 Turkish, no
diagnoses, questions to ask your doctor, what to bring. files/04 §5 fixes its
shape as ``PatientSummary``. This module is the only thing that builds one,
the same way :mod:`intake_api.note.compose` is the only thing that builds a
``PreVisitNote`` — one door, so the rule below is a property of the type and
not of a reviewer's attention.

**The exclusion is an allow-list, and that is the whole design.** The wellbeing
outputs — PHQ-2, GAD-2, PHQ-9, GAD-7, C-SSRS and anything derived from them —
are *"never in patient summary"* (INT-116's acceptance), and files/02 §5.6
says the same in product terms: the patient sees plain-language check-in
results, *"never scores and never labels"*. Handing someone a depression score
with no clinician present is the harm the rule exists to prevent.

A deny-list would express that rule as a list of things to remember. It would
be correct on the day it was written and wrong on the day somebody adds the
next signal, because the new field is admitted by default and nothing fails.
So the rule here runs the other way: :data:`PATIENT_VISIBLE_SECTIONS` and
:data:`PATIENT_VISIBLE_FIELDS` name what MAY cross, everything else is
withheld by construction, and a note field that appears tomorrow is outside
both lists on the day it appears. :func:`section_partition_error` closes the
last gap — the two section lists must partition
``ATTRIBUTABLE_SECTIONS`` exactly, and this module refuses to import if they
do not, so a new note *section* is a build failure rather than a silent leak.

Three consequences of the allow-list worth stating, because each reads as a
limitation and each is deliberate:

- **``hpi.narrative`` is withheld.** It is model-composed prose about the
  patient, and the summary reproduces what the patient said rather than a
  paraphrase of it. Its neighbour ``hpi.negatives`` — an elicited negative in
  the patient's own words — is admitted, and the two share a five-character
  prefix, which is why matching is on the whole normalised reference and never
  on a prefix.
- **``suggested_focus_questions`` is withheld**, even though
  ``PatientSummary`` has a ``questions_for_doctor`` field it would slot into.
  Those questions are written *for the clinician* (files/03 §11). The
  patient's own questions come from the wrap-up slot ``open_questions``
  (``packages/protocols/base/intake.yaml``) and reach this module as an
  argument, carrying their own spans.
- **A list item is admitted field by field, not whole.** The composer's fact
  text for a medication is clinician shorthand — an ATC code, a reconciliation
  status — so the summary rebuilds the line from the item's own allow-listed
  fields. A field added to ``MedicationItem`` tomorrow is outside the list on
  the same terms as everything else.

**Every product string arrives by key** (invariant 5). This module declares a
key set and nothing else; a missing or blank string is a refusal, never an
English fallback and never a sentence invented here. The copy is patient-facing
clinical text and belongs to the clinical copy owner.

**Triage wording is the rules engine's level and no more** (invariant 1). The
message is chosen by ``AttributedNote.rules_triage.level``; an LLM candidate
flag cannot reach it, and there is no key for a level the rules engine cannot
produce.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from clinical_schemas.composition import AttributedNote
from clinical_schemas.note import PatientSummary, SummaryCard
from clinical_schemas.provenance import ATTRIBUTABLE_SECTIONS, Attributed, NoteFact
from clinical_schemas.triage import TriageLevel

from intake_api.note.readability import (
    JARGON_TERMS,
    ReadabilityReport,
    SummaryText,
    TextOrigin,
    check_readability,
)

__all__ = [
    "CLINICIAN_ONLY_SECTIONS",
    "PATIENT_VISIBLE_FIELDS",
    "PATIENT_VISIBLE_SECTIONS",
    "ComposedSummary",
    "PatientSummaryReadabilityError",
    "SummaryStringsMissingError",
    "build_patient_summary",
    "jargon_terms",
    "normalise_field_ref",
    "render_patient_summary",
    "section_partition_error",
    "summary_string_keys",
]


class SummaryStringsMissingError(ValueError):
    """A ``tr`` resource key the summary cannot be rendered without."""


class PatientSummaryReadabilityError(ValueError):
    """Authored copy that does not carry the structural properties the gate
    requires. Raised rather than rendered: a summary is patient-facing text,
    and shipping it past its own gate would make the gate advisory."""


class SectionPartitionError(RuntimeError):
    """A note section classified as neither patient-visible nor
    clinician-only. Raised at import, because a note section nobody has
    classified is a leak waiting for its first note."""


#: Sections whose content the patient may see. Their own words, and the
#: reconciled lists they were read back (files/02 §5.2 rail; §5.4 cards).
PATIENT_VISIBLE_SECTIONS: Final[tuple[str, ...]] = (
    "chief_complaint",
    "hpi",
    "medications",
    "allergies",
)

#: Everything else. ``screening`` and ``konusma_ozellikleri`` are named first
#: because they are the reason this module exists.
CLINICIAN_ONLY_SECTIONS: Final[tuple[str, ...]] = (
    "screening",
    "konusma_ozellikleri",
    "ros_pertinent",
    "pmh",
    "family_social",
    "imported_objective",
    "suggested_focus_questions",
    "considerations",
    "patient_confirmed_sections",
)


def section_partition_error(sections: Sequence[str]) -> str | None:
    """The reason ``sections`` is not partitioned by the two lists, or None."""
    visible = set(PATIENT_VISIBLE_SECTIONS)
    clinician = set(CLINICIAN_ONLY_SECTIONS)
    both = sorted(visible & clinician)
    if both:
        return f"sections classified twice: {both}"
    unclassified = sorted(set(sections) - visible - clinician)
    if unclassified:
        return (
            f"note sections classified neither patient-visible nor clinician-only: {unclassified}"
        )
    unknown = sorted((visible | clinician) - set(sections))
    if unknown:
        return f"classified sections that are not note sections: {unknown}"
    return None


_PARTITION_ERROR = section_partition_error(ATTRIBUTABLE_SECTIONS)
if _PARTITION_ERROR is not None:  # pragma: no cover - import-time interlock
    raise SectionPartitionError(_PARTITION_ERROR)


#: The note field paths that may cross into a patient summary, normalised (a
#: list index reads as ``[]``). Nothing else is rendered, at any depth.
PATIENT_VISIBLE_FIELDS: Final[tuple[str, ...]] = (
    "chief_complaint.text",
    "chief_complaint.patient_goals[]",
    "hpi.oldcarts.onset",
    "hpi.oldcarts.location",
    "hpi.oldcarts.duration",
    "hpi.oldcarts.character",
    "hpi.oldcarts.radiation",
    "hpi.oldcarts.timing",
    "hpi.oldcarts.trajectory",
    "hpi.oldcarts.severity_nrs",
    "hpi.oldcarts.aggravating[]",
    "hpi.oldcarts.relieving[]",
    "hpi.associated[]",
    "hpi.negatives[]",
    "medications[].name",
    "medications[].dose",
    "allergies[].substance",
    "allergies[].reaction",
)

_VISIBLE: Final[frozenset[str]] = frozenset(PATIENT_VISIBLE_FIELDS)

#: Sections whose facts address a list item rather than a value: the fact is
#: admitted only to locate the item, and the line is rebuilt from the item's
#: own allow-listed fields.
_ITEM_SECTIONS: Final[tuple[str, ...]] = ("medications", "allergies")

#: One card per patient-visible section, in reading order, each with the ``tr``
#: key of its title.
_CARD_TITLE_KEYS: Final[tuple[tuple[str, str], ...]] = (
    ("chief_complaint", "patient_summary.card.chief_complaint.title"),
    ("hpi", "patient_summary.card.hpi.title"),
    ("medications", "patient_summary.card.medications.title"),
    ("allergies", "patient_summary.card.allergies.title"),
)

_TRIAGE_KEYS: Final[Mapping[TriageLevel, str]] = {
    level: f"patient_summary.triage.{level.value}" for level in TriageLevel
}

#: Structural separators. Punctuation, not copy.
_ITEM_JOIN: Final = ", "
_BULLET: Final = "• "


def jargon_terms() -> tuple[str, ...]:
    """The closed jargon vocabulary the gate matches on, for cross-checking
    against the runtime guard that owns the same vocabulary at the microphone."""
    return JARGON_TERMS


def normalise_field_ref(field_ref: str) -> str:
    """``medications[0].name`` -> ``medications[].name``.

    An index identifies which medication, never which kind of field, so it is
    dropped before the allow-list is consulted. Matching is on the whole
    normalised reference: ``hpi.narrative`` and ``hpi.negatives[0]`` share a
    prefix and land on opposite sides of the rule.
    """
    out: list[str] = []
    skipping = False
    for char in field_ref:
        if char == "[":
            skipping = True
            out.append("[")
        elif char == "]":
            skipping = False
            out.append("]")
        elif not skipping:
            out.append(char)
    return "".join(out)


def _admits(field_ref: str) -> bool:
    normalised = normalise_field_ref(field_ref)
    if normalised in _VISIBLE:
        return True
    return any(ref.startswith(f"{normalised}.") for ref in _VISIBLE)


def _item_line(note: AttributedNote, fact: NoteFact) -> tuple[str, list[str], list[str]]:
    """One list item, rebuilt from its own allow-listed fields.

    Returns the rendered line, the sub-field references it drew on, and the
    ones it withheld — so a field added to ``MedicationItem`` tomorrow appears
    in the second list on the day it appears, with nothing edited here.
    """
    ref = normalise_field_ref(fact.field_ref)
    index = int(fact.field_ref.split("[", 1)[1].split("]", 1)[0])
    item = getattr(note.note, fact.section)[index]
    parts: list[str] = []
    admitted: list[str] = []
    withheld: list[str] = []
    for name in type(item).model_fields:
        value = str(getattr(item, name) or "")
        if f"{ref}.{name}" not in _VISIBLE:
            withheld.append(f"{ref}.{name}")
            continue
        if value:
            parts.append(value)
            admitted.append(f"{fact.field_ref}.{name}")
    return _ITEM_JOIN.join(parts), admitted, withheld


def _cards(
    note: AttributedNote, strings: Mapping[str, str]
) -> tuple[tuple[SummaryCard, ...], tuple[str, ...], tuple[str, ...]]:
    """The cards, the field refs admitted, and the field refs withheld."""
    admitted: list[str] = []
    withheld: list[str] = []
    lines_by_section: dict[str, list[str]] = {}

    for fact in note.facts:
        if fact.section not in PATIENT_VISIBLE_SECTIONS or not _admits(fact.field_ref):
            withheld.append(normalise_field_ref(fact.field_ref))
            continue
        if fact.section in _ITEM_SECTIONS:
            line, item_admitted, item_withheld = _item_line(note, fact)
            withheld.extend(item_withheld)
        else:
            line, item_admitted = fact.text, [fact.field_ref]
        if not line:
            withheld.append(normalise_field_ref(fact.field_ref))
            continue
        admitted.extend(item_admitted)
        lines_by_section.setdefault(fact.section, []).append(line)

    cards = tuple(
        SummaryCard(title_tr=strings[key], lines=tuple(lines_by_section[section]))
        for section, key in _CARD_TITLE_KEYS
        if lines_by_section.get(section)
    )
    # De-duplicated in first-seen order: two medications withhold the same
    # sub-field references, and the record is of which references were kept
    # back, not of how many times.
    return cards, tuple(admitted), tuple(dict.fromkeys(withheld))


def summary_string_keys(note: AttributedNote) -> tuple[str, ...]:
    """The ``tr`` keys this summary cannot be rendered without.

    Content-gated, like :func:`intake_api.note.strings.note_string_keys`: a
    card with nothing in it needs no title, and requiring one would make the
    key set depend on the caller's memory rather than on the note.
    """
    sections = {
        fact.section
        for fact in note.facts
        if fact.section in PATIENT_VISIBLE_SECTIONS and _admits(fact.field_ref)
    }
    keys = [key for section, key in _CARD_TITLE_KEYS if section in sections]
    keys.append(_TRIAGE_KEYS[note.rules_triage.level])
    return tuple(keys)


def _require(strings: Mapping[str, str], keys: Sequence[str]) -> None:
    absent = sorted({key for key in keys if not strings.get(key, "").strip()})
    if absent:
        raise SummaryStringsMissingError(
            "the patient summary cannot be rendered without its tr resource keys: "
            + ", ".join(absent)
        )


@dataclass(frozen=True, slots=True)
class ComposedSummary:
    """The summary, what the allow-list did, and what the gate found."""

    summary: PatientSummary
    report: ReadabilityReport
    admitted_field_refs: tuple[str, ...]
    withheld_field_refs: tuple[str, ...]

    @property
    def admitted_values(self) -> tuple[str, ...]:
        """Every value the allow-list let through, as rendered."""
        values = [line for card in self.summary.cards for line in card.lines]
        values.extend(card.title_tr for card in self.summary.cards)
        values.extend(self.summary.questions_for_doctor)
        values.extend(self.summary.bring_list)
        if self.summary.triage_message_tr:
            values.append(self.summary.triage_message_tr)
        return tuple(values)


def build_patient_summary(
    note: AttributedNote,
    *,
    strings: Mapping[str, str],
    questions_for_doctor: Sequence[Attributed[str]] = (),
    bring_list: Sequence[str] = (),
) -> ComposedSummary:
    """Build one patient summary, or refuse.

    ``questions_for_doctor`` carries the patient's own wrap-up questions and
    is therefore attributed, exactly as note content is. ``bring_list`` is
    resolved protocol-pack copy, which has no utterance to point at, so it
    arrives as text and is gated as authored copy.
    """
    _require(strings, summary_string_keys(note))
    cards, admitted, withheld = _cards(note, strings)
    level = note.rules_triage.level
    summary = PatientSummary(
        cards=cards,
        questions_for_doctor=tuple(entry.value for entry in questions_for_doctor),
        bring_list=tuple(bring_list),
        triage_message_tr=strings[_TRIAGE_KEYS[level]],
    )

    units: list[SummaryText] = []
    for card_index, card in enumerate(summary.cards):
        units.append(
            SummaryText(
                location=f"cards[{card_index}].title_tr",
                text=card.title_tr,
                origin=TextOrigin.AUTHORED,
            )
        )
        units.extend(
            SummaryText(
                location=f"cards[{card_index}].lines[{line_index}]",
                text=line,
                origin=TextOrigin.QUOTED,
            )
            for line_index, line in enumerate(card.lines)
        )
    units.extend(
        SummaryText(
            location=f"questions_for_doctor[{index}]",
            text=question,
            origin=TextOrigin.QUOTED,
            prose=True,
        )
        for index, question in enumerate(summary.questions_for_doctor)
    )
    units.extend(
        SummaryText(
            location=f"bring_list[{index}]",
            text=entry,
            origin=TextOrigin.AUTHORED,
        )
        for index, entry in enumerate(summary.bring_list)
    )
    units.append(
        SummaryText(
            location="triage_message_tr",
            text=summary.triage_message_tr,
            origin=TextOrigin.AUTHORED,
            prose=True,
            red_register=level is TriageLevel.RED,
        )
    )

    report = check_readability(units)
    if not report.gate_passes:
        raise PatientSummaryReadabilityError(
            "authored patient copy did not pass the readability gate: "
            + ", ".join(
                f"{finding.location}:{finding.check.value}" for finding in report.authored_findings
            )
        )
    return ComposedSummary(
        summary=summary,
        report=report,
        admitted_field_refs=admitted,
        withheld_field_refs=withheld,
    )


def render_patient_summary(summary: PatientSummary) -> str:
    """The summary as text. Deterministic, and it adds nothing of its own.

    Every non-blank line is either a title or a value the allow-list admitted;
    the only strings this function contributes are a bullet and the newlines.
    """
    blocks: list[list[str]] = []
    for card in summary.cards:
        blocks.append([card.title_tr, *(f"{_BULLET}{line}" for line in card.lines)])
    if summary.questions_for_doctor:
        blocks.append([f"{_BULLET}{question}" for question in summary.questions_for_doctor])
    if summary.bring_list:
        blocks.append([f"{_BULLET}{entry}" for entry in summary.bring_list])
    if summary.triage_message_tr:
        blocks.append([summary.triage_message_tr])
    if not blocks:
        return ""
    return "\n\n".join("\n".join(block) for block in blocks) + "\n"
