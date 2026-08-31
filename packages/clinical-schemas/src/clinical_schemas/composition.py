"""The note composer's input and output shapes (INT-084).

:class:`NoteSources` is what a session hands the composer: the same content
``PreVisitNote`` carries, but every value wrapped in
:class:`~clinical_schemas.provenance.Attributed`. That is the only door into
a note, so *"every fact carries source span"* is a property of the type
system rather than of a reviewer's attention.

:class:`AttributedNote` is what comes back out: the files/04 §5 note (which
the INT-033 exchange mappers already understand, unchanged) alongside the
flat fact list the human renderers walk. Its validator refuses the two states
that would break the chain — a fact in a section that is not attributable,
and a note that carries content in a section no fact accounts for.

``data_gaps`` is the deliberate exception and stays a plain tuple of slot
refs: files/12 §2 makes a gap an *absence*, and an absence has no source.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal

from pydantic import Field, model_validator

from clinical_schemas.common import FrozenModel, JsonScalar, JsonValue
from clinical_schemas.note import (
    AllergyItem,
    Consideration,
    ImportedObjectiveItem,
    KonusmaOzellikleri,
    MedicationItem,
    PmhItem,
    PreVisitNote,
    RosItem,
    ScreeningProvenance,
)
from clinical_schemas.provenance import ATTRIBUTABLE_SECTIONS, Attributed, NoteFact
from clinical_schemas.triage import RulesTriageResult

__all__ = [
    "OLDCARTS_TEXT_FIELDS",
    "AttributedNote",
    "FamilySocialSources",
    "HpiSources",
    "NoteSources",
    "OldcartsField",
    "ScreeningSources",
]

#: The free-text OLDCARTS dimensions of files/04 §5 ``hpi.oldcarts``.
#: ``severity_nrs`` is excluded on purpose — it is a number and travels in its
#: own typed field so it can never be rendered as prose (invariant 22).
OldcartsField = Literal[
    "onset", "location", "duration", "character", "radiation", "timing", "trajectory"
]

OLDCARTS_TEXT_FIELDS: Final[tuple[OldcartsField, ...]] = (
    "onset",
    "location",
    "duration",
    "character",
    "radiation",
    "timing",
    "trajectory",
)


class HpiSources(FrozenModel):
    """files/04 §5 ``hpi``, one attribution per slot.

    Per-slot rather than per-block because that is how the engine fills it:
    one answered step, one utterance. A single span set over the whole HPI
    would say "somewhere in this session", which is not provenance.
    """

    narrative: Attributed[str] | None = None
    oldcarts: Mapping[OldcartsField, Attributed[str]] = Field(default_factory=dict)
    severity_nrs: Attributed[int] | None = None
    aggravating: tuple[Attributed[str], ...] = ()
    relieving: tuple[Attributed[str], ...] = ()
    associated: tuple[Attributed[str], ...] = ()
    negatives: tuple[Attributed[str], ...] = ()
    """Elicited negatives only (files/04 §5; files/12 §2). A slot that was
    never asked belongs in ``NoteSources.data_gaps`` — it has no span, so it
    cannot be expressed here even by accident."""

    def is_empty(self) -> bool:
        return not (
            self.narrative
            or self.oldcarts
            or self.severity_nrs
            or self.aggravating
            or self.relieving
            or self.associated
            or self.negatives
        )


class FamilySocialSources(FrozenModel):
    """files/04 §5 ``family_social``."""

    family: tuple[Attributed[str], ...] = ()
    smoking: Attributed[dict[str, JsonScalar]] | None = None
    alcohol: Attributed[dict[str, JsonScalar]] | None = None
    occupation: Attributed[str] | None = None
    living_situation: Attributed[str] | None = None

    def is_empty(self) -> bool:
        return not (
            self.family or self.smoking or self.alcohol or self.occupation or self.living_situation
        )


class ScreeningSources(FrozenModel):
    """files/04 §5 ``screening``. Scores are attributed; ``provenance`` is
    session metadata (files/06 §6 attribution flags), which is a fact about
    the *setting* rather than a value extracted from anything, so it carries
    no span and is required rather than defaulted."""

    phq2: Attributed[int] | None = None
    gad2: Attributed[int] | None = None
    phq9: Attributed[int] | None = None
    gad7: Attributed[int] | None = None
    cssrs: Attributed[JsonValue] | None = None
    provenance: ScreeningProvenance

    def scored(self) -> bool:
        return any(
            score is not None for score in (self.phq2, self.gad2, self.phq9, self.gad7, self.cssrs)
        )


class NoteSources(FrozenModel):
    """Everything the composer may put in a note, and where each piece came
    from. There is no field here that accepts bare content."""

    chief_complaint: Attributed[str] | None = None
    patient_goals: tuple[Attributed[str], ...] = ()
    hpi: HpiSources = Field(default_factory=HpiSources)
    ros_pertinent: tuple[Attributed[RosItem], ...] = ()
    pmh: tuple[Attributed[PmhItem], ...] = ()
    medications: tuple[Attributed[MedicationItem], ...] = ()
    allergies: tuple[Attributed[AllergyItem], ...] = ()
    family_social: FamilySocialSources = Field(default_factory=FamilySocialSources)
    screening: ScreeningSources
    konusma_ozellikleri: Attributed[KonusmaOzellikleri] | None = None
    imported_objective: tuple[Attributed[ImportedObjectiveItem], ...] = ()
    suggested_focus_questions: tuple[Attributed[str], ...] = ()
    considerations: tuple[Attributed[Consideration], ...] = ()
    patient_confirmed_sections: tuple[Attributed[str], ...] = ()
    data_gaps: tuple[str, ...] = ()
    """Slot refs the session could not close (files/12 §2 ``CoverageGap``).
    An absence, not a finding: no span, no fact, its own rendered block."""


def content_sections(note: PreVisitNote) -> frozenset[str]:
    """Attributable sections in which ``note`` actually carries content."""
    present: set[str] = set()
    if note.chief_complaint.text or note.chief_complaint.patient_goals:
        present.add("chief_complaint")
    hpi = note.hpi
    oldcarts = hpi.oldcarts
    if (
        hpi.narrative
        or hpi.associated
        or hpi.negatives
        or oldcarts.severity_nrs is not None
        or oldcarts.aggravating
        or oldcarts.relieving
        or any(getattr(oldcarts, name) for name in OLDCARTS_TEXT_FIELDS)
    ):
        present.add("hpi")
    social = note.family_social
    if (
        social.family
        or social.smoking
        or social.alcohol
        or social.occupation
        or social.living_situation
    ):
        present.add("family_social")
    screening = note.screening
    if any(
        score is not None
        for score in (
            screening.phq2,
            screening.gad2,
            screening.phq9,
            screening.gad7,
            screening.cssrs,
        )
    ):
        present.add("screening")
    if note.konusma_ozellikleri is not None:
        present.add("konusma_ozellikleri")
    for name in (
        "ros_pertinent",
        "pmh",
        "medications",
        "allergies",
        "imported_objective",
        "suggested_focus_questions",
        "considerations",
        "patient_confirmed_sections",
    ):
        if getattr(note, name):
            present.add(name)
    return frozenset(present)


class AttributedNote(FrozenModel):
    """A composed note, the provenance that accounts for all of it, and the
    rules-engine result it reports.

    ``rules_triage`` is carried beside the note rather than folded into it for
    two reasons. It keeps the RED three-axis result whole — ``register`` and
    ``location`` are required fields with no permitted default (CLAUDE.md
    invariant 21) and files/04 §5's ``NoteTriage`` has nowhere to put them —
    and it lets the validator below assert that the note's level and rules are
    the rules engine's own, byte for byte. A note cannot become a second route
    to a level, because the only level it can hold is the one it was handed
    (invariant 1).
    """

    note: PreVisitNote
    facts: tuple[NoteFact, ...]
    rules_triage: RulesTriageResult

    @model_validator(mode="after")
    def _level_is_the_rules_level(self) -> AttributedNote:
        if self.note.triage.level is not self.rules_triage.level:
            raise ValueError("the note level must be the rules-engine level (invariant 1)")
        if self.note.triage.rules != self.rules_triage.rules:
            raise ValueError("the note must report the rules that actually fired")
        return self

    @model_validator(mode="after")
    def _facts_account_for_the_content(self) -> AttributedNote:
        sections = {fact.section for fact in self.facts}
        stray = sections - set(ATTRIBUTABLE_SECTIONS)
        if stray:
            raise ValueError(f"facts claim non-attributable sections: {sorted(stray)}")
        missing = content_sections(self.note) - sections
        if missing:
            raise ValueError(f"note carries unattributed content in: {sorted(missing)}")
        order = {name: index for index, name in enumerate(ATTRIBUTABLE_SECTIONS)}
        positions = [order[fact.section] for fact in self.facts]
        if positions != sorted(positions):
            raise ValueError("facts must be ordered by note section (deterministic render)")
        return self

    def screening_scored(self) -> bool:
        return "screening" in content_sections(self.note)
