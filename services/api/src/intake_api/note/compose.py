"""The note composer (INT-084).

One composer, one direction: :class:`~clinical_schemas.composition.NoteSources`
in, :class:`~clinical_schemas.composition.AttributedNote` out. It is the only
thing in the system that builds a ``PreVisitNote``, and it builds every field
of one from an ``Attributed`` value — so a note field that carries content and
a fact that names its spans are produced by the same statement and cannot
drift apart.

Three refusals, all of them invariant 1 (*RED/YELLOW come from the rules
engine alone*):

- the ``triage`` argument is typed ``RulesTriageResult`` and re-checked at
  runtime, so an ``LlmCandidateTriage`` cannot be laundered into a note by a
  caller who ignored the type;
- a candidate flag whose text is a level word is refused outright rather than
  rendered — a model that answered with a level answered a question it was
  not asked;
- ``triage`` is not an attributable section at all
  (:mod:`clinical_schemas.provenance`), so no fact can claim it.

Numbers go through ``intake_platform.llm.units.render_quantity`` — INT-083's
single renderer, reused rather than rewritten (CLAUDE.md invariant 22). A
measure that carries a unit is joined to it with one non-breaking space, so
the pair survives every later line-wrap as one atom.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from clinical_schemas.common import JsonValue
from clinical_schemas.composition import (
    OLDCARTS_TEXT_FIELDS,
    AttributedNote,
    FamilySocialSources,
    HpiSources,
    NoteSources,
    ScreeningSources,
)
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
)
from clinical_schemas.provenance import NOTE_SECTIONS, Attributed, NoteFact, SourceSpan
from clinical_schemas.triage import CandidateFlag, RulesTriageResult, TriageLevel
from intake_platform.llm.units import render_quantity

__all__ = ["NBSP", "NoteCompositionError", "compose_note"]

#: Number and unit are one atom (CLAUDE.md invariant 22).
NBSP = "\u00a0"

_LEVEL_WORDS = frozenset({level.value for level in TriageLevel} | {"YELLOW_REVIEW"})


class NoteCompositionError(ValueError):
    """An input the composer refuses to turn into a note."""


def _quantity(value: int | float | Decimal) -> str:
    """The one permitted rendering of a clinical magnitude (invariant 22)."""
    if isinstance(value, float):
        return render_quantity(Decimal(str(value)))
    return render_quantity(value)


def _measure(value: float, unit: str) -> str:
    return f"{_quantity(value)}{NBSP}{unit}"


def _pairs(mapping: Mapping[str, JsonValue]) -> str:
    return " | ".join(f"{key}={mapping[key]}" for key in sorted(mapping))


class _Facts:
    """Accumulates facts in note-section order as the note is built."""

    def __init__(self) -> None:
        self._facts: list[NoteFact] = []

    def add(self, section: str, field_ref: str, text: str, spans: tuple[SourceSpan, ...]) -> None:
        if not text:
            return
        self._facts.append(NoteFact(section=section, field_ref=field_ref, text=text, spans=spans))

    def take(self) -> tuple[NoteFact, ...]:
        return tuple(self._facts)


def _chief_complaint(sources: NoteSources, facts: _Facts) -> ChiefComplaint:
    text = sources.chief_complaint.value if sources.chief_complaint else ""
    if sources.chief_complaint is not None:
        facts.add("chief_complaint", "chief_complaint.text", text, sources.chief_complaint.spans)
    goals: list[str] = []
    for index, goal in enumerate(sources.patient_goals):
        goals.append(goal.value)
        facts.add(
            "chief_complaint",
            f"chief_complaint.patient_goals[{index}]",
            goal.value,
            goal.spans,
        )
    return ChiefComplaint(text=text, patient_goals=tuple(goals))


def _hpi(hpi: HpiSources, facts: _Facts) -> Hpi:
    narrative = hpi.narrative.value if hpi.narrative is not None else ""
    if hpi.narrative is not None:
        facts.add("hpi", "hpi.narrative", narrative, hpi.narrative.spans)

    text_values: dict[str, str] = {}
    for name in OLDCARTS_TEXT_FIELDS:
        entry = hpi.oldcarts.get(name)
        if entry is None:
            continue
        text_values[name] = entry.value
        facts.add("hpi", f"hpi.oldcarts.{name}", entry.value, entry.spans)

    severity: int | None = None
    if hpi.severity_nrs is not None:
        severity = hpi.severity_nrs.value
        facts.add(
            "hpi",
            "hpi.oldcarts.severity_nrs",
            _quantity(severity),
            hpi.severity_nrs.spans,
        )

    aggravating: list[str] = []
    for index, entry in enumerate(hpi.aggravating):
        aggravating.append(entry.value)
        facts.add("hpi", f"hpi.oldcarts.aggravating[{index}]", entry.value, entry.spans)
    relieving: list[str] = []
    for index, entry in enumerate(hpi.relieving):
        relieving.append(entry.value)
        facts.add("hpi", f"hpi.oldcarts.relieving[{index}]", entry.value, entry.spans)

    associated: list[str] = []
    for index, entry in enumerate(hpi.associated):
        associated.append(entry.value)
        facts.add("hpi", f"hpi.associated[{index}]", entry.value, entry.spans)
    negatives: list[str] = []
    for index, entry in enumerate(hpi.negatives):
        negatives.append(entry.value)
        facts.add("hpi", f"hpi.negatives[{index}]", entry.value, entry.spans)

    return Hpi(
        narrative=narrative,
        oldcarts=Oldcarts(
            onset=text_values.get("onset", ""),
            location=text_values.get("location", ""),
            duration=text_values.get("duration", ""),
            character=text_values.get("character", ""),
            radiation=text_values.get("radiation", ""),
            timing=text_values.get("timing", ""),
            trajectory=text_values.get("trajectory", ""),
            severity_nrs=severity,
            aggravating=tuple(aggravating),
            relieving=tuple(relieving),
        ),
        associated=tuple(associated),
        negatives=tuple(negatives),
    )


def _ros(sources: NoteSources, facts: _Facts) -> tuple[RosItem, ...]:
    items: list[RosItem] = []
    for index, entry in enumerate(sources.ros_pertinent):
        item = entry.value
        items.append(item)
        facts.add(
            "ros_pertinent",
            f"ros_pertinent[{index}]",
            f"{item.system} | finding={item.finding} | present={str(item.present).lower()}",
            entry.spans,
        )
    return tuple(items)


def _pmh(sources: NoteSources, facts: _Facts) -> tuple[PmhItem, ...]:
    items: list[PmhItem] = []
    for index, entry in enumerate(sources.pmh):
        item = entry.value
        items.append(item)
        parts = [item.condition]
        if item.icd10:
            parts.append(f"icd10={item.icd10}")
        parts.extend((f"status={item.status}", f"source={item.source}"))
        facts.add("pmh", f"pmh[{index}]", " | ".join(parts), entry.spans)
    return tuple(items)


def _medications(sources: NoteSources, facts: _Facts) -> tuple[MedicationItem, ...]:
    items: list[MedicationItem] = []
    for index, entry in enumerate(sources.medications):
        item = entry.value
        items.append(item)
        parts = [item.name]
        if item.atc:
            parts.append(f"atc={item.atc}")
        if item.dose:
            parts.append(f"dose={item.dose}")
        if item.adherence:
            parts.append(f"adherence={item.adherence}")
        if item.source:
            parts.append(f"source={item.source}")
        parts.append(f"reconciliation={item.reconciliation}")
        facts.add("medications", f"medications[{index}]", " | ".join(parts), entry.spans)
    return tuple(items)


def _allergies(sources: NoteSources, facts: _Facts) -> tuple[AllergyItem, ...]:
    items: list[AllergyItem] = []
    for index, entry in enumerate(sources.allergies):
        item = entry.value
        items.append(item)
        parts = [item.substance]
        if item.reaction:
            parts.append(f"reaction={item.reaction}")
        if item.severity:
            parts.append(f"severity={item.severity}")
        facts.add("allergies", f"allergies[{index}]", " | ".join(parts), entry.spans)
    return tuple(items)


def _family_social(social: FamilySocialSources, facts: _Facts) -> FamilySocial:
    family: list[str] = []
    for index, entry in enumerate(social.family):
        family.append(entry.value)
        facts.add("family_social", f"family_social.family[{index}]", entry.value, entry.spans)
    smoking: dict[str, JsonValue] = {}
    if social.smoking is not None:
        smoking = {key: value for key, value in social.smoking.value.items()}
        facts.add(
            "family_social",
            "family_social.smoking",
            _pairs(social.smoking.value),
            social.smoking.spans,
        )
    alcohol: dict[str, JsonValue] = {}
    if social.alcohol is not None:
        alcohol = {key: value for key, value in social.alcohol.value.items()}
        facts.add(
            "family_social",
            "family_social.alcohol",
            _pairs(social.alcohol.value),
            social.alcohol.spans,
        )
    occupation = social.occupation.value if social.occupation else ""
    if social.occupation is not None:
        facts.add("family_social", "family_social.occupation", occupation, social.occupation.spans)
    living = social.living_situation.value if social.living_situation else ""
    if social.living_situation is not None:
        facts.add(
            "family_social",
            "family_social.living_situation",
            living,
            social.living_situation.spans,
        )
    return FamilySocial(
        family=tuple(family),
        smoking=smoking,
        alcohol=alcohol,
        occupation=occupation,
        living_situation=living,
    )


def _screening(screening: ScreeningSources, facts: _Facts) -> ScreeningBlock:
    def score(name: str, entry: Attributed[int] | None) -> int | None:
        if entry is None:
            return None
        facts.add("screening", f"screening.{name}", _quantity(entry.value), entry.spans)
        return entry.value

    phq2 = score("phq2", screening.phq2)
    gad2 = score("gad2", screening.gad2)
    phq9 = score("phq9", screening.phq9)
    gad7 = score("gad7", screening.gad7)
    cssrs: JsonValue = None
    if screening.cssrs is not None:
        cssrs = screening.cssrs.value
        facts.add("screening", "screening.cssrs", str(cssrs), screening.cssrs.spans)
    return ScreeningBlock(
        phq2=phq2,
        gad2=gad2,
        phq9=phq9,
        gad7=gad7,
        cssrs=cssrs,
        provenance=screening.provenance,
    )


def _konusma(
    block: Attributed[KonusmaOzellikleri] | None, facts: _Facts
) -> KonusmaOzellikleri | None:
    if block is None:
        return None
    value = block.value
    section = "konusma_ozellikleri"
    for field_ref, text in (
        ("speech_rate_syll_s", _measure(value.speech_rate_syll_s, "syll/s")),
        ("pause_ratio", _quantity(value.pause_ratio)),
        ("f0_mean_hz", _measure(value.f0_mean_hz, "Hz")),
        ("f0_sd_hz", _measure(value.f0_sd_hz, "Hz")),
        ("response_latency_ms_mean", _measure(value.response_latency_ms_mean, "ms")),
        ("reference_ranges", _pairs(dict(value.reference_ranges))),
        ("recording_conditions_caveat_tr", value.recording_conditions_caveat_tr),
    ):
        facts.add(section, f"{section}.{field_ref}", text, block.spans)
    return value


def _imported(sources: NoteSources, facts: _Facts) -> tuple[ImportedObjectiveItem, ...]:
    items: list[ImportedObjectiveItem] = []
    for index, entry in enumerate(sources.imported_objective):
        item = entry.value
        items.append(item)
        parts = [item.type, f"summary={item.summary}"]
        if item.date:
            parts.append(f"date={item.date}")
        if item.provenance:
            parts.append(f"provenance={item.provenance}")
        facts.add(
            "imported_objective", f"imported_objective[{index}]", " | ".join(parts), entry.spans
        )
    return tuple(items)


def _questions(sources: NoteSources, facts: _Facts) -> tuple[str, ...]:
    out: list[str] = []
    for index, entry in enumerate(sources.suggested_focus_questions):
        out.append(entry.value)
        facts.add(
            "suggested_focus_questions",
            f"suggested_focus_questions[{index}]",
            entry.value,
            entry.spans,
        )
    return tuple(out)


def _considerations(sources: NoteSources, facts: _Facts) -> tuple[Consideration, ...]:
    items: list[Consideration] = []
    for index, entry in enumerate(sources.considerations):
        item = entry.value
        items.append(item)
        facts.add(
            "considerations",
            f"considerations[{index}]",
            f"pattern={item.pattern} | why={item.why}",
            entry.spans,
        )
    return tuple(items)


def _confirmed(sources: NoteSources, facts: _Facts) -> tuple[str, ...]:
    out: list[str] = []
    for index, entry in enumerate(sources.patient_confirmed_sections):
        if entry.value not in NOTE_SECTIONS:
            raise NoteCompositionError(
                f"{entry.value!r} is not a note section and cannot be confirmed"
            )
        out.append(entry.value)
        facts.add(
            "patient_confirmed_sections",
            f"patient_confirmed_sections[{index}]",
            entry.value,
            entry.spans,
        )
    return tuple(out)


def compose_note(
    *,
    meta: NoteMeta,
    triage: RulesTriageResult,
    sources: NoteSources,
    candidate_flags: Sequence[CandidateFlag] = (),
) -> AttributedNote:
    """Compose one pre-visit note and the provenance that accounts for it."""
    if not isinstance(triage, RulesTriageResult):
        raise NoteCompositionError(
            "a note reports the level the rules engine produced and no other "
            "(CLAUDE.md invariant 1)"
        )
    for flag in candidate_flags:
        if flag.text.strip().upper() in _LEVEL_WORDS:
            raise NoteCompositionError(
                "a candidate flag names a concern, never a level (CLAUDE.md invariant 1)"
            )

    facts = _Facts()
    note = PreVisitNote(
        meta=meta,
        triage=NoteTriage(
            level=triage.level, rules=triage.rules, llm_candidates=tuple(candidate_flags)
        ),
        chief_complaint=_chief_complaint(sources, facts),
        hpi=_hpi(sources.hpi, facts),
        ros_pertinent=_ros(sources, facts),
        pmh=_pmh(sources, facts),
        medications=_medications(sources, facts),
        allergies=_allergies(sources, facts),
        family_social=_family_social(sources.family_social, facts),
        screening=_screening(sources.screening, facts),
        konusma_ozellikleri=_konusma(sources.konusma_ozellikleri, facts),
        imported_objective=_imported(sources, facts),
        data_gaps=tuple(sources.data_gaps),
        suggested_focus_questions=_questions(sources, facts),
        considerations=_considerations(sources, facts),
        patient_confirmed_sections=_confirmed(sources, facts),
    )
    return AttributedNote(note=note, facts=facts.take(), rules_triage=triage)
