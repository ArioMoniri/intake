"""PreVisitNote and PatientSummary (INT-031).

The authoritative JSON sketch is files/04 §5 ("Note schemas (authoritative
JSON, packages/clinical-schemas)"), including the two 25 Aug 2026 changes
recorded there: ``screening.affect_summary`` is deleted (the factual
qualifiers live in ``screening.provenance``), and ``konusma_ozellikleri``
is a sibling of ``screening``, never a child of it. There is no field
anywhere in ``PreVisitNote`` for the ``acoustic`` module's output — that
goes to the sealed research store (files/03 §4.7.4).

``PatientSummary`` is patient-facing: its transitive annotation closure must
never reach clinician-only material (files/12 §2.3), which the roundtrip test
walks and asserts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field

from clinical_schemas.common import FrozenModel, JsonValue, Ref, Sha256
from clinical_schemas.triage import CandidateFlag, RuleFire, TriageLevel


class NoteMeta(FrozenModel):
    """files/04 §5 ``PreVisitNote.meta``."""

    visit_id: Ref = Field(description="Visit this note belongs to (files/04 §5 meta.visit_id).")
    protocol_hash: Sha256 = Field(
        description="Resolved protocol pack hash pinned per session (files/04 §5 "
        "meta.protocol_hash; files/04 §7 signed packs)."
    )
    mode: Literal["fast", "detailed"] = Field(
        description="Intake mode (files/04 §5 meta.mode: fast|detailed)."
    )
    language: Literal["tr"] = Field(
        default="tr", description="Note language (files/04 §5 meta.language; invariant 5)."
    )
    generated_at: AwareDatetime = Field(
        description="When the note was composed (files/04 §5 meta.generated_at)."
    )
    model: str = Field(
        min_length=1,
        description="Note-composition model reference (files/04 §5 meta.model; pinned "
        "per files/03 §4.9.1).",
    )
    prompt_version: str = Field(
        min_length=1,
        description="Versioned prompt id (files/04 §5 meta.prompt_version; files/03 §4.3 "
        "prompts are versioned).",
    )


class NoteTriage(FrozenModel):
    """files/04 §5 ``PreVisitNote.triage`` — rules and LLM candidates side by
    side, never merged (invariant 1)."""

    level: TriageLevel = Field(
        description="Rules-engine level RED|YELLOW|GREEN (files/04 §5 triage.level)."
    )
    rules: tuple[RuleFire, ...] = Field(
        default=(), description="Fired rules with evidence (files/04 §5 triage.rules)."
    )
    llm_candidates: tuple[CandidateFlag, ...] = Field(
        default=(),
        description="LLM candidate flags, clinician-review material only "
        "(files/04 §5 triage.llm_candidates; ceiling YELLOW_REVIEW, files/03 §4.6).",
    )


class ChiefComplaint(FrozenModel):
    """files/04 §5 ``PreVisitNote.chief_complaint``."""

    text: str = Field(description="Presenting complaint (files/04 §5 chief_complaint.text).")
    patient_goals: tuple[str, ...] = Field(
        default=(),
        description="What the patient wants from the visit (files/04 §5 "
        "chief_complaint.patient_goals).",
    )


class Oldcarts(FrozenModel):
    """files/04 §5 ``PreVisitNote.hpi.oldcarts``."""

    onset: str = Field(default="", description="files/04 §5 oldcarts.onset.")
    location: str = Field(default="", description="files/04 §5 oldcarts.location.")
    duration: str = Field(default="", description="files/04 §5 oldcarts.duration.")
    character: str = Field(default="", description="files/04 §5 oldcarts.character.")
    aggravating: tuple[str, ...] = Field(
        default=(), description="files/04 §5 oldcarts.aggravating."
    )
    relieving: tuple[str, ...] = Field(default=(), description="files/04 §5 oldcarts.relieving.")
    radiation: str = Field(default="", description="files/04 §5 oldcarts.radiation.")
    timing: str = Field(default="", description="files/04 §5 oldcarts.timing.")
    severity_nrs: int | None = Field(
        default=None,
        ge=0,
        le=10,
        description="Numeric rating scale 0-10 (files/04 §5 oldcarts.severity_nrs); "
        "None when not elicited — an absent score is never rendered as 0.",
    )
    trajectory: str = Field(default="", description="files/04 §5 oldcarts.trajectory.")


class Hpi(FrozenModel):
    """files/04 §5 ``PreVisitNote.hpi``."""

    narrative: str = Field(description="files/04 §5 hpi.narrative.")
    oldcarts: Oldcarts = Field(description="files/04 §5 hpi.oldcarts.")
    associated: tuple[str, ...] = Field(default=(), description="files/04 §5 hpi.associated.")
    negatives: tuple[str, ...] = Field(
        default=(),
        description="Elicited negatives only (files/04 §5 hpi.negatives; files/13 §9.3 — "
        "only ASKED_ABSENT may enter a pertinent-negative list).",
    )


class RosItem(FrozenModel):
    """files/04 §5 ``PreVisitNote.ros_pertinent[]``."""

    system: str = Field(description="files/04 §5 ros_pertinent.system.")
    finding: str = Field(description="files/04 §5 ros_pertinent.finding.")
    present: bool = Field(description="files/04 §5 ros_pertinent.present.")


class PmhItem(FrozenModel):
    """files/04 §5 ``PreVisitNote.pmh[]``."""

    condition: str = Field(description="files/04 §5 pmh.condition.")
    icd10: str | None = Field(
        default=None, description="ICD-10 code when known (files/04 §5 pmh.icd10)."
    )
    status: Literal["confirmed", "unconfirmed"] = Field(
        description="files/04 §5 pmh.status: confirmed|unconfirmed."
    )
    source: Literal["patient", "record"] = Field(
        description="files/04 §5 pmh.source: patient|record."
    )


class MedicationItem(FrozenModel):
    """files/04 §5 ``PreVisitNote.medications[]``."""

    name: str = Field(description="files/04 §5 medications.name.")
    atc: str | None = Field(
        default=None, description="ATC code when known (files/04 §5 medications.atc)."
    )
    dose: str = Field(
        default="",
        description="Dose as Turkish orthography text (files/04 §5 medications.dose; "
        "CLAUDE.md invariant 22 — numbers never cross a boundary unguarded).",
    )
    adherence: str = Field(default="", description="files/04 §5 medications.adherence.")
    source: str = Field(default="", description="files/04 §5 medications.source.")
    reconciliation: Literal["matches", "new", "stopped", "conflict"] = Field(
        description="files/04 §5 medications.reconciliation: matches|new|stopped|conflict."
    )


class AllergyItem(FrozenModel):
    """files/04 §5 ``PreVisitNote.allergies[]``."""

    substance: str = Field(description="files/04 §5 allergies.substance.")
    reaction: str = Field(default="", description="files/04 §5 allergies.reaction.")
    severity: str = Field(default="", description="files/04 §5 allergies.severity.")


class FamilySocial(FrozenModel):
    """files/04 §5 ``PreVisitNote.family_social``."""

    family: tuple[str, ...] = Field(default=(), description="files/04 §5 family_social.family.")
    smoking: dict[str, JsonValue] = Field(
        default_factory=dict, description="files/04 §5 family_social.smoking (open map)."
    )
    alcohol: dict[str, JsonValue] = Field(
        default_factory=dict, description="files/04 §5 family_social.alcohol (open map)."
    )
    occupation: str = Field(default="", description="files/04 §5 family_social.occupation.")
    living_situation: str = Field(
        default="", description="files/04 §5 family_social.living_situation."
    )


class ScreeningProvenance(FrozenModel):
    """files/04 §5 ``screening.provenance`` — the factual qualifiers that
    replaced the deleted ``affect_summary`` (files/04 §5 change note, 25 Aug
    2026; files/04 §4.3 third-party qualifier)."""

    administration_mode: Literal["voice", "typed", "keypad"] = Field(
        description="files/04 §5 provenance.administration_mode: voice|typed|keypad."
    )
    proxy_reported: bool = Field(
        description="files/04 §5 provenance.proxy_reported; files/12 §2.2 reporter rules."
    )
    third_party_present: bool = Field(
        description="files/04 §5 provenance.third_party_present; files/04 §4.3 — a second "
        "voice was audible, worded strictly factually."
    )
    qualifier_tr: str = Field(
        default="",
        description="Strictly factual Turkish qualifier rendered with every score "
        "(files/04 §4.3: 'başka bir konuşmacı duyuldu', never an identity claim).",
    )


class ScreeningBlock(FrozenModel):
    """files/04 §5 ``PreVisitNote.screening``. Scores are None until an
    attested self-report exists (files/12 §2.2: InstrumentNotScored is never
    a number)."""

    phq2: int | None = Field(
        default=None, ge=0, le=6, description="PHQ-2 total 0-6 (files/04 §5 screening.phq2)."
    )
    gad2: int | None = Field(
        default=None, ge=0, le=6, description="GAD-2 total 0-6 (files/04 §5 screening.gad2)."
    )
    phq9: int | None = Field(
        default=None, ge=0, le=27, description="PHQ-9 total 0-27 (files/04 §5 screening.phq9)."
    )
    gad7: int | None = Field(
        default=None, ge=0, le=21, description="GAD-7 total 0-21 (files/04 §5 screening.gad7)."
    )
    cssrs: JsonValue = Field(
        default=None,
        description="C-SSRS outcome; shape not fixed by files/04 §5 (sketch: null) and the "
        "instrument licence is BLOCKED (HUMAN_BLOCKERS.md HB-L2), so this stays an open "
        "JSON slot until the licence lands.",
    )
    provenance: ScreeningProvenance = Field(
        description="files/04 §5 screening.provenance — required with any score."
    )


class KonusmaOzellikleri(FrozenModel):
    """files/04 §5 ``PreVisitNote.konusma_ozellikleri`` — objective speech
    measures, a sibling of screening by design (files/04 §5 change note;
    files/03 §4.7.6). Every measure ships with a population reference range
    and a recording-condition caveat, or the block is not rendered."""

    speech_rate_syll_s: float = Field(
        ge=0, description="Speech rate, syllables/s (files/04 §5; files/03 §4.7.6)."
    )
    pause_ratio: float = Field(
        ge=0, le=1, description="Pause ratio 0-1 (files/04 §5; files/03 §4.7.6)."
    )
    f0_mean_hz: float = Field(ge=0, description="Mean F0 in Hz (files/04 §5; files/03 §4.7.6).")
    f0_sd_hz: float = Field(ge=0, description="F0 SD in Hz (files/04 §5; files/03 §4.7.6).")
    response_latency_ms_mean: float = Field(
        ge=0, description="Mean response latency in ms (files/04 §5; files/03 §4.7.6)."
    )
    reference_ranges: dict[str, JsonValue] = Field(
        min_length=1,
        description="Population reference range per measure — required, or the block is "
        "not rendered (files/04 §5 change note).",
    )
    recording_conditions_caveat_tr: str = Field(
        min_length=1,
        description="Recording-condition caveat — required, or the block is not rendered "
        "(files/04 §5 change note).",
    )


class ImportedObjectiveItem(FrozenModel):
    """files/04 §5 ``PreVisitNote.imported_objective[]``."""

    type: Literal["lab", "imaging", "procedure"] = Field(
        description="files/04 §5 imported_objective.type: lab|imaging|procedure."
    )
    summary: str = Field(description="files/04 §5 imported_objective.summary.")
    date: str = Field(
        default="",
        description="Date as printed on the source record (files/04 §5 imported_objective.date).",
    )
    provenance: str = Field(
        default="",
        description="Source trail, e.g. document id + page (files/04 §5 "
        "imported_objective.provenance; files/03 §4.6 Provenance with page/bbox).",
    )


class Consideration(FrozenModel):
    """files/04 §5 ``PreVisitNote.considerations[]`` — patterns for the
    clinician, never diagnoses (invariant 2)."""

    pattern: str = Field(description="files/04 §5 considerations.pattern.")
    why: str = Field(description="files/04 §5 considerations.why.")


class PreVisitNote(FrozenModel):
    """The clinician-ready pre-visit note (files/04 §5, authoritative JSON).
    Persisted only as field-level-encrypted payload (INT-030 notes.payload;
    invariant 14)."""

    meta: NoteMeta = Field(description="files/04 §5 PreVisitNote.meta.")
    triage: NoteTriage = Field(description="files/04 §5 PreVisitNote.triage.")
    chief_complaint: ChiefComplaint = Field(description="files/04 §5 PreVisitNote.chief_complaint.")
    hpi: Hpi = Field(description="files/04 §5 PreVisitNote.hpi.")
    ros_pertinent: tuple[RosItem, ...] = Field(
        default=(), description="files/04 §5 PreVisitNote.ros_pertinent."
    )
    pmh: tuple[PmhItem, ...] = Field(default=(), description="files/04 §5 PreVisitNote.pmh.")
    medications: tuple[MedicationItem, ...] = Field(
        default=(), description="files/04 §5 PreVisitNote.medications."
    )
    allergies: tuple[AllergyItem, ...] = Field(
        default=(), description="files/04 §5 PreVisitNote.allergies."
    )
    family_social: FamilySocial = Field(description="files/04 §5 PreVisitNote.family_social.")
    screening: ScreeningBlock = Field(description="files/04 §5 PreVisitNote.screening.")
    konusma_ozellikleri: KonusmaOzellikleri | None = Field(
        default=None,
        description="Objective speech measures, sibling of screening (files/04 §5 change "
        "note); None when not rendered — the caveat/range rule makes partial rendering "
        "unrepresentable.",
    )
    imported_objective: tuple[ImportedObjectiveItem, ...] = Field(
        default=(), description="files/04 §5 PreVisitNote.imported_objective."
    )
    data_gaps: tuple[str, ...] = Field(
        default=(),
        description="Visible gaps, e.g. a dropped OCR item (files/04 §5 data_gaps; "
        "files/03 §4.6 — a missing value the clinician can see is safe).",
    )
    suggested_focus_questions: tuple[str, ...] = Field(
        default=(), description="files/04 §5 PreVisitNote.suggested_focus_questions."
    )
    considerations: tuple[Consideration, ...] = Field(
        default=(), description="files/04 §5 PreVisitNote.considerations."
    )
    patient_confirmed_sections: tuple[str, ...] = Field(
        default=(), description="files/04 §5 PreVisitNote.patient_confirmed_sections."
    )


class SummaryCard(FrozenModel):
    """files/04 §5 ``PatientSummary.cards[]``."""

    title_tr: str = Field(description="Card title, ≤ B1 Turkish (files/04 §5; invariant 2).")
    lines: tuple[str, ...] = Field(default=(), description="files/04 §5 cards.lines.")


class PatientSummary(FrozenModel):
    """The patient-facing summary (files/04 §5). Everything here passes
    PolicyGuard (invariant 2); its annotation closure never reaches
    clinician-only material (files/12 §2.3), which tests walk and assert."""

    cards: tuple[SummaryCard, ...] = Field(
        default=(), description="files/04 §5 PatientSummary.cards."
    )
    questions_for_doctor: tuple[str, ...] = Field(
        default=(), description="files/04 §5 PatientSummary.questions_for_doctor."
    )
    bring_list: tuple[str, ...] = Field(
        default=(), description="files/04 §5 PatientSummary.bring_list."
    )
    triage_message_tr: str = Field(
        default="",
        description="Patient-safe triage message (files/04 §5 triage_message_tr; never "
        "alarming beyond the triage action — CLAUDE.md clinical content rules).",
    )
