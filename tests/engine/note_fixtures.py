"""Synthetic note-composition fixtures for the INT-084 golden suite.

Every id, span, Turkish word and number in this module is SYNTHETIC and
carries no clinical meaning (files/04 §7). Nothing here is a clinical value:
the scores, the severity and the speech measures exist to exercise the
rendering boundary of CLAUDE.md invariant 22, not to assert anything about a
patient. The three scenarios are shaped by what the acceptance pins:

``green_typed``
    The floor: one complaint, one HPI slot, a GREEN rules result, a data gap.
    Proves a note with the smallest possible content still carries provenance
    and the fixed disclaimer.
``yellow_candidates``
    An LLM ``candidate_flags`` payload alongside a rules YELLOW. Proves the
    two never merge (invariant 1) and that a candidate renders as a candidate.
``red_full``
    Every section populated, including the sections that carry numbers, so the
    golden pins the number rendering (invariant 22) and the RED three-axis
    result (invariant 21).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from clinical_schemas.composition import (
    FamilySocialSources,
    HpiSources,
    NoteSources,
    ScreeningSources,
)
from clinical_schemas.note import (
    AllergyItem,
    Consideration,
    ImportedObjectiveItem,
    KonusmaOzellikleri,
    MedicationItem,
    NoteMeta,
    PmhItem,
    RosItem,
    ScreeningProvenance,
)
from clinical_schemas.provenance import Attributed, SourceKind, SourceSpan
from clinical_schemas.triage import (
    CandidateFlag,
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)

PROTOCOL_HASH = "b" * 64
GENERATED_AT = dt.datetime(2026, 8, 31, 9, 15, tzinfo=dt.UTC)


def utterance(ref: str, start: int, end: int) -> SourceSpan:
    return SourceSpan(kind=SourceKind.UTTERANCE, source_ref=ref, start=start, end=end)


def typed(ref: str, start: int, end: int) -> SourceSpan:
    return SourceSpan(kind=SourceKind.TYPED, source_ref=ref, start=start, end=end)


def document(ref: str, start: int, end: int, page: int) -> SourceSpan:
    return SourceSpan(kind=SourceKind.DOCUMENT, source_ref=ref, start=start, end=end, page=page)


def meta(mode: str = "fast") -> NoteMeta:
    return NoteMeta(
        visit_id="visit-0001",
        protocol_hash=PROTOCOL_HASH,
        mode="fast" if mode == "fast" else "detailed",
        generated_at=GENERATED_AT,
        model="synthetic-extractor@rev-0",
        prompt_version="extract.v0",
    )


def unscored_screening(mode: str, third_party: bool = False) -> ScreeningSources:
    """No instrument was administered. ``provenance`` is still required: the
    setting a note was taken in is a fact about the session (files/06 §6), and
    it is knowable whether or not a score exists."""
    return ScreeningSources(
        provenance=ScreeningProvenance(
            administration_mode="typed" if mode == "typed" else "voice",
            proxy_reported=False,
            third_party_present=third_party,
        )
    )


def green_typed() -> tuple[NoteMeta, RulesTriageResult, NoteSources, tuple[CandidateFlag, ...]]:
    sources = NoteSources(
        chief_complaint=Attributed(value="bas agrisi", spans=(typed("turn:1", 0, 10),)),
        hpi=HpiSources(
            oldcarts={"duration": Attributed(value="iki gun", spans=(typed("turn:2", 0, 8),))},
        ),
        screening=unscored_screening("typed"),
        data_gaps=("hpi.oldcarts.character", "medications"),
    )
    return meta(), RulesTriageResult(level=TriageLevel.GREEN), sources, ()


def yellow_candidates() -> tuple[
    NoteMeta, RulesTriageResult, NoteSources, tuple[CandidateFlag, ...]
]:
    sources = NoteSources(
        chief_complaint=Attributed(value="gogus agrisi", spans=(utterance("turn:1", 4, 17),)),
        patient_goals=(Attributed(value="rahatlamak", spans=(utterance("turn:1", 20, 30),)),),
        hpi=HpiSources(
            narrative=Attributed(value="dun aksam basladi", spans=(utterance("turn:2", 0, 17),)),
            oldcarts={
                "onset": Attributed(value="dun aksam", spans=(utterance("turn:2", 0, 9),)),
                "character": Attributed(value="baski", spans=(utterance("turn:3", 5, 10),)),
            },
            severity_nrs=Attributed(value=6, spans=(utterance("turn:4", 0, 1),)),
            associated=(Attributed(value="terleme", spans=(utterance("turn:5", 3, 10),)),),
            negatives=(Attributed(value="nefes darligi yok", spans=(utterance("turn:6", 0, 17),)),),
        ),
        screening=unscored_screening("voice"),
        data_gaps=("hpi.oldcarts.radiation",),
    )
    triage = RulesTriageResult(
        level=TriageLevel.YELLOW,
        rules=(RuleFire(id="synthetic.rule.yellow_a", evidence="onset=dun aksam"),),
    )
    candidates = (CandidateFlag(text="sentetik aday not", evidence="turn:5 terleme"),)
    return meta(), triage, sources, candidates


def red_full() -> tuple[NoteMeta, RulesTriageResult, NoteSources, tuple[CandidateFlag, ...]]:
    sources = NoteSources(
        chief_complaint=Attributed(
            value="siddetli bas agrisi", spans=(utterance("turn:1", 0, 19),)
        ),
        patient_goals=(Attributed(value="acil yardim", spans=(utterance("turn:1", 22, 33),)),),
        hpi=HpiSources(
            narrative=Attributed(value="ani basladi", spans=(utterance("turn:2", 0, 11),)),
            oldcarts={
                "onset": Attributed(value="ani", spans=(utterance("turn:2", 0, 3),)),
                "location": Attributed(value="ense", spans=(utterance("turn:3", 0, 4),)),
                "duration": Attributed(value="bir saat", spans=(utterance("turn:3", 6, 14),)),
                "character": Attributed(value="zonklayici", spans=(utterance("turn:4", 0, 10),)),
                "radiation": Attributed(value="omuza", spans=(utterance("turn:4", 12, 17),)),
                "timing": Attributed(value="surekli", spans=(utterance("turn:5", 0, 7),)),
                "trajectory": Attributed(value="artiyor", spans=(utterance("turn:5", 9, 16),)),
            },
            severity_nrs=Attributed(value=10, spans=(utterance("turn:6", 0, 2),)),
            aggravating=(Attributed(value="hareket", spans=(utterance("turn:7", 0, 7),)),),
            relieving=(Attributed(value="karanlik oda", spans=(utterance("turn:7", 9, 21),)),),
            associated=(Attributed(value="bulanti", spans=(utterance("turn:8", 0, 7),)),),
            negatives=(Attributed(value="atesi yok", spans=(utterance("turn:8", 9, 18),)),),
        ),
        ros_pertinent=(
            Attributed(
                value=RosItem(system="noro", finding="ense sertligi", present=True),
                spans=(utterance("turn:9", 0, 13),),
            ),
        ),
        pmh=(
            Attributed(
                value=PmhItem(
                    condition="sentetik kronik durum",
                    icd10="Z00.0",
                    status="confirmed",
                    source="patient",
                ),
                spans=(utterance("turn:10", 0, 21),),
            ),
        ),
        medications=(
            Attributed(
                value=MedicationItem(
                    name="sentetik ilac",
                    atc="A01AA01",
                    dose="beş miligram",
                    adherence="duzenli",
                    source="patient",
                    reconciliation="matches",
                ),
                spans=(utterance("turn:11", 0, 13),),
            ),
        ),
        allergies=(
            Attributed(
                value=AllergyItem(substance="sentetik madde", reaction="dokuntu", severity="hafif"),
                spans=(utterance("turn:12", 0, 14),),
            ),
        ),
        family_social=FamilySocialSources(
            family=(Attributed(value="anne migren", spans=(utterance("turn:13", 0, 11),)),),
            smoking=Attributed(value={"status": "never"}, spans=(utterance("turn:14", 0, 5),)),
            alcohol=Attributed(value={"status": "never"}, spans=(utterance("turn:14", 7, 12),)),
            occupation=Attributed(value="ogretmen", spans=(utterance("turn:15", 0, 8),)),
            living_situation=Attributed(value="ailesiyle", spans=(utterance("turn:15", 10, 19),)),
        ),
        screening=ScreeningSources(
            phq2=Attributed(value=1, spans=(typed("instrument:phq2", 0, 1),)),
            gad2=Attributed(value=0, spans=(typed("instrument:gad2", 0, 1),)),
            phq9=Attributed(value=12, spans=(typed("instrument:phq9", 0, 2),)),
            gad7=Attributed(value=9, spans=(typed("instrument:gad7", 0, 1),)),
            provenance=ScreeningProvenance(
                administration_mode="typed",
                proxy_reported=False,
                third_party_present=True,
                qualifier_tr="başka bir konuşmacı duyuldu",
            ),
        ),
        konusma_ozellikleri=Attributed(
            value=KonusmaOzellikleri(
                speech_rate_syll_s=4.25,
                pause_ratio=0.125,
                f0_mean_hz=132.5,
                f0_sd_hz=18.75,
                response_latency_ms_mean=1250.0,
                reference_ranges={"speech_rate_syll_s": "sentetik aralik"},
                recording_conditions_caveat_tr="sentetik kayit kosulu notu",
            ),
            spans=(utterance("window:1", 0, 30),),
        ),
        imported_objective=(
            Attributed(
                value=ImportedObjectiveItem(
                    type="lab",
                    summary="Üre 45 mg/dL",
                    date="2026-08-20",
                    provenance="document:doc-1 p2",
                ),
                spans=(document("document:doc-1", 40, 52, 2),),
            ),
        ),
        considerations=(
            Attributed(
                value=Consideration(pattern="sentetik oruntu", why="sentetik gerekce"),
                spans=(utterance("turn:2", 0, 11),),
            ),
        ),
        suggested_focus_questions=(
            Attributed(value="sentetik odak sorusu", spans=(utterance("turn:9", 0, 13),)),
        ),
        patient_confirmed_sections=(
            Attributed(value="chief_complaint", spans=(utterance("turn:16", 0, 4),)),
            Attributed(value="medications", spans=(utterance("turn:16", 6, 10),)),
        ),
        data_gaps=("family_social.occupation_detail",),
    )
    triage = RulesTriageResult(
        level=TriageLevel.RED,
        rules=(
            RuleFire(id="synthetic.rule.red_a", evidence="onset=ani; severity_nrs=10"),
            RuleFire(id="synthetic.rule.red_b", evidence="ros=ense sertligi"),
        ),
        register=RedRegister.ALERT,
        location=RedLocation.REMOTE,
    )
    return meta("detailed"), triage, sources, ()


def bare_items() -> dict[str, object]:
    """The same sections with every OPTIONAL field left unset — the shape a
    session produces when the patient names a medication but not its dose."""
    return {
        "pmh": (
            Attributed(
                value=PmhItem(condition="sentetik durum", status="unconfirmed", source="record"),
                spans=(utterance("turn:10", 0, 14),),
            ),
        ),
        "medications": (
            Attributed(
                value=MedicationItem(name="sentetik ilac", reconciliation="new"),
                spans=(utterance("turn:11", 0, 13),),
            ),
        ),
        "allergies": (
            Attributed(
                value=AllergyItem(substance="sentetik madde"),
                spans=(utterance("turn:12", 0, 14),),
            ),
        ),
        "imported_objective": (
            Attributed(
                value=ImportedObjectiveItem(type="lab", summary="sentetik ozet"),
                spans=(document("document:doc-1", 0, 13, 1),),
            ),
        ),
    }


#: A quantity used by the invariant-22 tests: four digits, so a grouping
#: separator would be visible if one ever appeared.
GROUPING_PROBE = Decimal("10000.5")
