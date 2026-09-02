"""INT-084 — the note composer.

``compose`` is the only way to build a :class:`~clinical_schemas.note.PreVisitNote`
for a real session, and every parameter that carries patient material takes a
:class:`~intake_voice_runtime.note.facts.Sourced` wrapper. That is the whole of
*"every fact carries source span"*: not a check that could be forgotten, a
signature that cannot be satisfied without one.

Three things the composer refuses to do, each because a renderer downstream
would otherwise state something false:

1. **It never computes or raises a triage level.** ``triage`` is a
   :class:`~clinical_schemas.triage.RulesTriageResult` — the only type that can
   express RED or YELLOW (invariant 1) — and candidates arrive separately as a
   :class:`~clinical_schemas.triage.LlmCandidateTriage`, whose single
   inhabitant is ``YELLOW_REVIEW``. There is no arithmetic between them here
   and no parameter through which one could influence the other.
2. **It never files a fact in a section that does not admit its
   attribution** (:data:`~intake_voice_runtime.note.facts.SECTION_ATTRIBUTIONS`).
   A relative's condition offered to ``pmh`` raises; it is not moved, because
   moving it silently would hide the caller's bug in the note.
3. **It never invents a gap or a reason.** Gaps arrive as
   :class:`~intake_voice_runtime.note.facts.NoteGap` values with a closed
   reason enum, and they land in ``data_gaps`` as language-neutral codes, so
   the three different reasons a section can be absent stay three different
   facts all the way to the page.

The fired rules are deliberately **not** facts. files/04 §5 already gives each
one an ``evidence`` string — that is a rule's source — and adding a
``RULES_ENGINE`` row to the attribution table would create a second, weaker
path for a level to reach the note.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from clinical_schemas.note import (
    AllergyItem,
    ChiefComplaint,
    Consideration,
    FamilySocial,
    Hpi,
    ImportedObjectiveItem,
    KonusmaOzellikleri,
    MedicationItem,
    NoteMeta,
    NoteTriage,
    Oldcarts,
    PmhItem,
    PreVisitNote,
    RosItem,
    ScreeningBlock,
    SelfReportedMeasure,
)
from clinical_schemas.triage import LlmCandidateTriage, RulesTriageResult

from intake_voice_runtime.note.facts import (
    NoteFact,
    NoteGap,
    Sourced,
    check_admissible,
)

__all__ = ["ComposedNote", "compose", "facts_by_section"]

# One non-breaking space: number + unit is one atom (CLAUDE.md invariant 22).
_NBSP = " "

#: files/04 §5 ``hpi.oldcarts`` scalar fields, in sketch order. ``severity_nrs``
#: is handled apart because ``None`` means "not elicited" and must never print
#: as a zero.
_OLDCARTS_SCALARS = (
    "onset",
    "location",
    "duration",
    "character",
    "radiation",
    "timing",
    "trajectory",
)


@dataclass(frozen=True, slots=True)
class ComposedNote:
    """The note, its fact index and its gap index.

    The sidecars are not decoration: files/04 §5 has no per-fact provenance
    key, so the note alone cannot answer *"where did this line come from?"*.
    Every renderer takes this value rather than the bare note, which is what
    makes the provenance reachable in all three of them.
    """

    note: PreVisitNote
    facts: tuple[NoteFact, ...]
    gaps: tuple[NoteGap, ...]


def _chief_complaint_lines(value: ChiefComplaint) -> tuple[str, ...]:
    return (value.text, *(f"goal: {goal}" for goal in value.patient_goals))


def _hpi_lines(value: Hpi) -> tuple[str, ...]:
    lines: list[str] = []
    if value.narrative:
        lines.append(value.narrative)
    oldcarts: Oldcarts = value.oldcarts
    for name in _OLDCARTS_SCALARS:
        scalar = getattr(oldcarts, name)
        if scalar:
            lines.append(f"{name}: {scalar}")
    lines.extend(f"aggravating: {item}" for item in oldcarts.aggravating)
    lines.extend(f"relieving: {item}" for item in oldcarts.relieving)
    if oldcarts.severity_nrs is not None:
        lines.append(f"severity_nrs: {oldcarts.severity_nrs}")
    lines.extend(f"associated: {item}" for item in value.associated)
    lines.extend(f"negative: {item}" for item in value.negatives)
    return tuple(lines)


def _ros_line(value: RosItem) -> str:
    return f"{value.system}: {value.finding} [{'present' if value.present else 'absent'}]"


def _pmh_line(value: PmhItem) -> str:
    coded = f" [{value.icd10}]" if value.icd10 else ""
    return f"{value.condition}{coded} [{value.status}/{value.source}]"


def _medication_line(value: MedicationItem) -> str:
    parts = [value.name]
    if value.atc:
        parts.append(f"[{value.atc}]")
    if value.dose:
        parts.append(value.dose)
    if value.adherence:
        parts.append(value.adherence)
    return " · ".join(parts) + f" [{value.reconciliation}]"


def _allergy_line(value: AllergyItem) -> str:
    parts = [value.substance, value.reaction, value.severity]
    return " · ".join(part for part in parts if part)


def _social_lines(value: FamilySocial) -> tuple[str, ...]:
    lines = [f"smoking.{key}: {item}" for key, item in value.smoking.items()]
    lines.extend(f"alcohol.{key}: {item}" for key, item in value.alcohol.items())
    if value.occupation:
        lines.append(f"occupation: {value.occupation}")
    if value.living_situation:
        lines.append(f"living_situation: {value.living_situation}")
    return tuple(lines)


def _measure_line(value: SelfReportedMeasure) -> str:
    # invariant 22: Decimal's own str() never groups, and the number binds to
    # its unit with a non-breaking space so the pair cannot be split by a line
    # break in any renderer.
    return f"{value.code.value}: {value.magnitude}{_NBSP}{value.unit}"


def _imported_line(value: ImportedObjectiveItem) -> str:
    line = f"{value.type}: {value.summary}"
    if value.date:
        line += f" [{value.date}]"
    if value.provenance:
        line += f" [{value.provenance}]"
    return line


class _FactIndex:
    """Assigns the stable ``fNN`` handles, in note-section order."""

    def __init__(self) -> None:
        self._facts: list[NoteFact] = []

    def add(self, section: str, sourced: Sourced[object], lines: Sequence[str]) -> None:
        check_admissible(section, sourced)
        self._facts.append(
            NoteFact(
                ref=f"f{len(self._facts) + 1:02d}",
                section=section,
                attribution=sourced.attribution,
                subject=sourced.subject,
                lines=tuple(lines),
                span=sourced.span,
            )
        )

    @property
    def facts(self) -> tuple[NoteFact, ...]:
        return tuple(self._facts)


def compose(
    *,
    meta: NoteMeta,
    triage: RulesTriageResult,
    screening: ScreeningBlock,
    candidates: LlmCandidateTriage | None = None,
    chief_complaint: Sourced[ChiefComplaint] | None = None,
    hpi: Sourced[Hpi] | None = None,
    ros_pertinent: Sequence[Sourced[RosItem]] = (),
    pmh: Sequence[Sourced[PmhItem]] = (),
    medications: Sequence[Sourced[MedicationItem]] = (),
    allergies: Sequence[Sourced[AllergyItem]] = (),
    family: Sequence[Sourced[str]] = (),
    social: Sourced[FamilySocial] | None = None,
    measurements: Sequence[Sourced[SelfReportedMeasure]] = (),
    imported_objective: Sequence[Sourced[ImportedObjectiveItem]] = (),
    konusma_ozellikleri: KonusmaOzellikleri | None = None,
    considerations: Sequence[Consideration] = (),
    suggested_focus_questions: Sequence[str] = (),
    patient_confirmed_sections: Sequence[str] = (),
    gaps: Sequence[NoteGap] = (),
) -> ComposedNote:
    """Build the note and its provenance index together.

    ``family`` is separate from ``social`` because they are the two halves of
    files/04 §5 ``family_social`` with different subjects: a relative's
    condition and the patient's own social history. Keeping them apart at the
    signature is what lets ``family`` be the one place a ``RELATIVE``
    attribution is admissible, and ``social`` reject one.
    """
    if social is not None and social.value.family:
        raise ValueError(
            "pass relatives' conditions through `family`, not inside FamilySocial.family — "
            "the subject axis is what keeps a relative's condition off the patient's record"
        )

    index = _FactIndex()
    if chief_complaint is not None:
        index.add("chief_complaint", chief_complaint, _chief_complaint_lines(chief_complaint.value))
    if hpi is not None:
        index.add("hpi", hpi, _hpi_lines(hpi.value))
    for ros in ros_pertinent:
        index.add("ros_pertinent", ros, (_ros_line(ros.value),))
    for condition in pmh:
        index.add("pmh", condition, (_pmh_line(condition.value),))
    for medication in medications:
        index.add("medications", medication, (_medication_line(medication.value),))
    for allergy in allergies:
        index.add("allergies", allergy, (_allergy_line(allergy.value),))
    for relative in family:
        index.add("family_social", relative, (relative.value,))
    if social is not None:
        index.add("family_social", social, _social_lines(social.value))
    for measure in measurements:
        index.add("measurements", measure, (_measure_line(measure.value),))
    for imported in imported_objective:
        index.add("imported_objective", imported, (_imported_line(imported.value),))

    # `family_social.family` carries the relative CODE, never a Turkish label:
    # the exchange layer keeps codes (files/03 §7) and the human renderers
    # localise them. Either way the entry names whose condition it is, so a
    # consumer that only ever sees the note value still cannot read it as the
    # patient's own (INT-282).
    social_value = social.value if social is not None else FamilySocial()
    note = PreVisitNote(
        meta=meta,
        triage=NoteTriage(
            level=triage.level,
            rules=triage.rules,
            llm_candidates=candidates.candidate_flags if candidates is not None else (),
        ),
        chief_complaint=chief_complaint.value
        if chief_complaint is not None
        else ChiefComplaint(text=""),
        hpi=hpi.value if hpi is not None else Hpi(narrative="", oldcarts=Oldcarts()),
        ros_pertinent=tuple(item.value for item in ros_pertinent),
        pmh=tuple(item.value for item in pmh),
        medications=tuple(item.value for item in medications),
        allergies=tuple(item.value for item in allergies),
        family_social=social_value.model_copy(
            update={"family": tuple(f"{item.subject.value}: {item.value}" for item in family)}
        ),
        measurements=tuple(item.value for item in measurements),
        screening=screening,
        konusma_ozellikleri=konusma_ozellikleri,
        imported_objective=tuple(item.value for item in imported_objective),
        data_gaps=tuple(gap.code for gap in gaps),
        suggested_focus_questions=tuple(suggested_focus_questions),
        considerations=tuple(considerations),
        patient_confirmed_sections=tuple(patient_confirmed_sections),
    )
    return ComposedNote(note=note, facts=index.facts, gaps=tuple(gaps))


def facts_by_section(composed: ComposedNote, section: str) -> tuple[NoteFact, ...]:
    """The facts filed in one section, in the order they were composed."""
    return tuple(fact for fact in composed.facts if fact.section == section)
