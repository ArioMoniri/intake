"""PreVisitNote → FHIR document Bundle (INT-033).

files/03 §4.8: the note assembly renderers include "FHIR ``Composition`` +
Bundle". The Composition's section codes are the authoritative files/04 §5
note keys (``codes.NOTE_SECTION_IDS``), in note order; section titles stay
the technical ids on purpose — human headings belong to the renderers
(Doctor Link, PDF), not the exchange layer.

Invariant 1's interop face: the note's ``llm_candidates`` never cross into
the document — no FHIR resource, no narrative line. The RiskAssessment and
Flag entries carry the rules result only.

Narrative text is generated, escaped XHTML. Clinical quantities in the
konuşma özellikleri narrative render without grouping and with a
non-breaking space binding number to unit (CLAUDE.md invariant 22).
"""

from __future__ import annotations

import html
import uuid
from collections.abc import Iterable, Sequence

from clinical_schemas.common import JsonValue
from clinical_schemas.mappers import codes
from clinical_schemas.mappers.r4 import (
    AllergyIntolerance,
    Bundle,
    BundleEntry,
    CodeableConcept,
    Coding,
    Composition,
    CompositionSection,
    Condition,
    Extension,
    Flag,
    Identifier,
    MedicationStatement,
    Narrative,
    Observation,
    Patient,
    Reference,
    RiskAssessment,
    RiskPrediction,
)
from clinical_schemas.mappers.to_r4 import (
    allergy_item_to_allergy_intolerance,
    medication_item_to_medication_statement,
    pmh_item_to_condition,
    screening_to_observations,
)
from clinical_schemas.note import KonusmaOzellikleri, NoteTriage, PreVisitNote
from clinical_schemas.triage import TriageLevel

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:intake:fhir:document")

# One non-breaking space: number + unit is one atom (CLAUDE.md invariant 22).
_NBSP = "\u00a0"


def _div(lines: Iterable[str]) -> Narrative:
    body = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
    return Narrative(
        status="generated",
        div=f'<div xmlns="http://www.w3.org/1999/xhtml">{body}</div>',
    )


def _concept(system: str, code: str) -> CodeableConcept:
    return CodeableConcept(coding=(Coding(system=system, code=code),))


def _note_triage_resources(
    triage: NoteTriage, *, subject_ref: str
) -> tuple[RiskAssessment, Flag | None]:
    """The note's triage block (files/04 §5) → RiskAssessment (+Flag when
    RED/YELLOW). Only ``level`` and ``rules`` exist on the note shape;
    ``llm_candidates`` are deliberately not consumed here (invariant 1)."""
    assessment = RiskAssessment(
        status="final",
        method=_concept(codes.TRIAGE_METHOD_SYSTEM, codes.TRIAGE_METHOD_RULES),
        subject=Reference(reference=subject_ref),
        reason_code=tuple(
            CodeableConcept(
                coding=(Coding(system=codes.TRIAGE_RULE_SYSTEM, code=rule.id),),
                text=rule.evidence,
            )
            for rule in triage.rules
        )
        or None,
        prediction=(
            RiskPrediction(
                qualitative_risk=_concept(codes.TRIAGE_LEVEL_SYSTEM, triage.level.value)
            ),
        ),
    )
    flag: Flag | None = None
    if triage.level is not TriageLevel.GREEN:
        codings = [Coding(system=codes.TRIAGE_LEVEL_SYSTEM, code=triage.level.value)]
        codings.extend(
            Coding(system=codes.TRIAGE_RULE_SYSTEM, code=rule.id) for rule in triage.rules
        )
        flag = Flag(
            status="active",
            code=CodeableConcept(coding=tuple(codings), text=triage.level.value),
            subject=Reference(reference=subject_ref),
        )
    return assessment, flag


def _open_map_lines(prefix: str, mapping: dict[str, JsonValue]) -> list[str]:
    return [f"{prefix}.{key}: {value}" for key, value in mapping.items()]


def _konusma_lines(block: KonusmaOzellikleri) -> list[str]:
    lines = [
        f"speech_rate_syll_s: {block.speech_rate_syll_s}{_NBSP}syll/s",
        f"pause_ratio: {block.pause_ratio}",
        f"f0_mean_hz: {block.f0_mean_hz}{_NBSP}Hz",
        f"f0_sd_hz: {block.f0_sd_hz}{_NBSP}Hz",
        f"response_latency_ms_mean: {block.response_latency_ms_mean}{_NBSP}ms",
    ]
    lines.extend(_open_map_lines("reference_ranges", dict(block.reference_ranges)))
    lines.append(f"recording_conditions_caveat_tr: {block.recording_conditions_caveat_tr}")
    return lines


def _section_lines(note: PreVisitNote, section_id: str) -> list[str]:
    """Narrative lines per text-only section — factual key:value renderings
    of the files/04 §5 fields, no interpretation added."""
    if section_id == "triage":
        lines = [f"level: {note.triage.level.value}"]
        lines.extend(f"rule {rule.id}: {rule.evidence}" for rule in note.triage.rules)
        return lines
    if section_id == "chief_complaint":
        lines = [note.chief_complaint.text] if note.chief_complaint.text else []
        lines.extend(f"goal: {goal}" for goal in note.chief_complaint.patient_goals)
        return lines
    if section_id == "hpi":
        lines = [note.hpi.narrative] if note.hpi.narrative else []
        oldcarts = note.hpi.oldcarts
        for field in (
            "onset",
            "location",
            "duration",
            "character",
            "radiation",
            "timing",
            "trajectory",
        ):
            value = getattr(oldcarts, field)
            if value:
                lines.append(f"{field}: {value}")
        lines.extend(f"aggravating: {v}" for v in oldcarts.aggravating)
        lines.extend(f"relieving: {v}" for v in oldcarts.relieving)
        if oldcarts.severity_nrs is not None:
            lines.append(f"severity_nrs: {oldcarts.severity_nrs}")
        lines.extend(f"associated: {v}" for v in note.hpi.associated)
        lines.extend(f"negative: {v}" for v in note.hpi.negatives)
        return lines
    if section_id == "ros_pertinent":
        return [
            f"{item.system}: {item.finding} ({'+' if item.present else '-'})"
            for item in note.ros_pertinent
        ]
    if section_id == "family_social":
        social = note.family_social
        lines = [f"family: {v}" for v in social.family]
        lines.extend(_open_map_lines("smoking", dict(social.smoking)))
        lines.extend(_open_map_lines("alcohol", dict(social.alcohol)))
        if social.occupation:
            lines.append(f"occupation: {social.occupation}")
        if social.living_situation:
            lines.append(f"living_situation: {social.living_situation}")
        return lines
    if section_id == "measurements":
        # invariant 22: no grouping, and number + unit is one non-breaking
        # atom. Decimal's own str() never groups, so the atom is the whole
        # guarantee here rather than a locale setting.
        return [
            f"{item.code.value}: {item.magnitude}{_NBSP}{item.unit}" for item in note.measurements
        ]
    if section_id == "konusma_ozellikleri":
        return _konusma_lines(note.konusma_ozellikleri) if note.konusma_ozellikleri else []
    if section_id == "imported_objective":
        return [
            f"{item.type}: {item.summary}"
            + (f" ({item.date})" if item.date else "")
            + (f" [{item.provenance}]" if item.provenance else "")
            for item in note.imported_objective
        ]
    if section_id == "data_gaps":
        return list(note.data_gaps)
    if section_id == "suggested_focus_questions":
        return list(note.suggested_focus_questions)
    if section_id == "considerations":
        return [f"{item.pattern}: {item.why}" for item in note.considerations]
    if section_id == "patient_confirmed_sections":
        return list(note.patient_confirmed_sections)
    return []


def previsit_note_to_document_bundle(
    note: PreVisitNote,
    *,
    patient_id: str,
    fact_provenance: Sequence[str] = (),
) -> Bundle:
    """The PreVisitNote as a FHIR document: Composition first (bdl-11),
    urn:uuid fullUrls resolved entirely inside the Bundle, identifier +
    timestamp per bdl-9/bdl-10. Deterministic: same note, same bytes.

    ``fact_provenance`` (INT-084) carries one opaque line per composed fact —
    ``ref|section|attribution|subject|locator`` — as repeated Composition
    extensions. They are extensions and not sections on purpose: the section
    codes are exactly ``NOTE_SECTION_IDS`` (files/04 §5 keys) and a
    provenance section would put a code in that vocabulary that no note field
    backs. Empty by default, so INT-033's own callers are unchanged."""

    def full_url(name: str) -> str:
        return f"urn:uuid:{uuid.uuid5(_NAMESPACE, f'{note.meta.visit_id}:{name}')}"

    patient_url = full_url(f"patient:{patient_id}")
    entries: list[BundleEntry] = [
        BundleEntry(full_url=patient_url, resource=Patient(id=patient_id))
    ]
    section_entries: dict[str, list[Reference]] = {}

    def add(
        section_id: str,
        name: str,
        resource: Observation
        | Condition
        | MedicationStatement
        | AllergyIntolerance
        | RiskAssessment
        | Flag,
    ) -> None:
        url = full_url(name)
        entries.append(BundleEntry(full_url=url, resource=resource))
        section_entries.setdefault(section_id, []).append(Reference(reference=url))

    assessment, flag = _note_triage_resources(note.triage, subject_ref=patient_url)
    add("triage", "triage:risk-assessment", assessment)
    if flag is not None:
        add("triage", "triage:flag", flag)
    for observation in screening_to_observations(
        note.screening, subject_ref=patient_url, effective=note.meta.generated_at
    ):
        instrument = observation.code.text or "score"
        add("screening", f"screening:{instrument}", observation)
    for index, pmh in enumerate(note.pmh):
        add("pmh", f"pmh:{index}", pmh_item_to_condition(pmh, subject_ref=patient_url))
    for index, medication in enumerate(note.medications):
        add(
            "medications",
            f"medication:{index}",
            medication_item_to_medication_statement(medication, subject_ref=patient_url),
        )
    for index, allergy in enumerate(note.allergies):
        add(
            "allergies",
            f"allergy:{index}",
            allergy_item_to_allergy_intolerance(allergy, subject_ref=patient_url),
        )

    sections: list[CompositionSection] = []
    for section_id in codes.NOTE_SECTION_IDS:
        lines = _section_lines(note, section_id)
        refs = section_entries.get(section_id)
        if not lines and not refs:
            continue  # cmp-1: a section carries text or entries, or is absent
        sections.append(
            CompositionSection(
                title=section_id,
                code=_concept(codes.SECTION_SYSTEM, section_id),
                text=_div(lines) if lines else None,
                entry=tuple(refs) if refs else None,
            )
        )

    composition = Composition(
        extension=(
            Extension(url=codes.EXT_PROTOCOL_HASH, value_string=note.meta.protocol_hash),
            Extension(url=codes.EXT_MODE, value_string=note.meta.mode),
            Extension(url=codes.EXT_MODEL, value_string=note.meta.model),
            Extension(url=codes.EXT_PROMPT_VERSION, value_string=note.meta.prompt_version),
            *(
                Extension(url=codes.EXT_FACT_PROVENANCE, value_string=line)
                for line in fact_provenance
            ),
        ),
        text=_div([codes.DOCUMENT_TITLE_TR]),
        status="final",
        type=CodeableConcept(
            coding=(Coding(system=codes.DOC_TYPE_SYSTEM, code=codes.DOCUMENT_TYPE_CODE),),
            text=codes.DOCUMENT_TYPE_CODE,
        ),
        subject=Reference(reference=patient_url),
        date=note.meta.generated_at.isoformat(),
        author=(Reference(reference=patient_url),),
        title=codes.DOCUMENT_TITLE_TR,
        section=tuple(sections),
    )
    return Bundle(
        identifier=Identifier(system=codes.VISIT_ID_SYSTEM, value=note.meta.visit_id),
        type="document",
        timestamp=note.meta.generated_at.isoformat(),
        entry=(
            BundleEntry(full_url=full_url("composition"), resource=composition),
            *entries,
        ),
    )
