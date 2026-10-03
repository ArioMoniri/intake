"""INT-084 — the note composer, its provenance and the three renderers.

The acceptance has three clauses and this module is organised around them:

1. **"every fact carries source span"** — :class:`TestSourceSpanIsStructural`
   and :class:`TestAttribution`. The guarantee is not a validator: every
   fact-placed item reaches :func:`compose` inside a ``Sourced`` wrapper whose
   ``span`` is a required constructor argument, so a fact without a span has
   no expression. The attribution axis rides the same wrapper, which is what
   makes INT-282's rule — *the note mapper must not attribute a relative's
   condition to the patient* — a shape rather than a habit.
2. **"fixed legal disclaimer text … rendered on note+PDF"** —
   :class:`TestDisclaimer`. The wording is files/06 §7's and it renders only
   from the hash-bound ``docs/legal/strings.yaml`` (invariant 18). That file
   is counsel's deliverable under INT-210 and does not exist, so the
   production path fails closed and a test says so; the fixture at
   ``tests/fixtures/legal/strings.synthetic.yaml`` proves where the footer
   lands when it does exist.
3. **"golden note snapshots"** — :class:`TestGoldens`, pinning the SOAP text,
   the FHIR document and the PDF text layer byte-for-byte.

Plus the ``notes`` threat-model row, whose three named threats each get a
class: :class:`TestNoteRenderingIsNotMarkup` ([T] XSS through note rendering),
:class:`TestProvenanceIsReachable` ([R] a fact in the note with no
provenance), and :class:`TestCandidatesNeverBecomeFindings` (LLM09
misinformation presented without review, which is invariant 1's note face).

**No clinical content is authored here.** Every complaint, condition, drug and
Turkish heading in this module is synthetic (files/04 §7); the authored pack is
INT-043 (`awaiting-human`, HB-C1) and none of it is needed, because every
clause above is a mechanism.
"""

from __future__ import annotations

import datetime
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.mappers import codes
from clinical_schemas.mappers.document import previsit_note_to_document_bundle
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
    Oldcarts,
    PmhItem,
    PreVisitNote,
    RosItem,
    ScreeningBlock,
    ScreeningProvenance,
    SelfReportedMeasure,
)
from clinical_schemas.triage import (
    CandidateFlag,
    EvidenceSlot,
    LlmCandidateTriage,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_platform.legal import LegalStringsCatalog, LegalStringsMissingError
from intake_platform.pdf import FooterTooLongError, encode_text, render_document_pdf
from intake_voice_runtime.note import (
    NOTE_COPY_KEYS,
    SECTION_ATTRIBUTIONS,
    Attribution,
    AttributionRefused,
    ComposedNote,
    FactSubject,
    MeasureCode,
    NoteCopy,
    NoteGap,
    NoteGapReason,
    Sourced,
    SourceSpan,
    compose,
    note_copy_from_legal_strings,
    render_fhir_document,
    render_note_pdf,
    render_soap,
)

REPO = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).parent / "golden" / "int084"
SYNTHETIC_STRINGS = REPO / "tests" / "fixtures" / "legal" / "strings.synthetic.yaml"

#: files/06 §7, quoted here as the control for where it must land — the same
#: way tests/legal/test_store_labels.py quotes it. Nothing in this repo renders
#: it from a Python constant; the renderers read the hash-bound file.
FOOTER_06_7 = (
    "Bu belge hastanın beyanına dayanır; hekim değerlendirmesinin yerine geçmez. "
    "İçerik yapay zekâ desteğiyle yapılandırılmıştır ve tanı niteliği taşımaz."
)

GENERATED_AT = datetime.datetime(2026, 9, 2, 9, 30, tzinfo=datetime.UTC)


# --------------------------------------------------------------------------------------
# fixtures — every value synthetic (files/04 §7)
# --------------------------------------------------------------------------------------


@pytest.fixture
def copy() -> NoteCopy:
    catalog = LegalStringsCatalog(SYNTHETIC_STRINGS)
    return note_copy_from_legal_strings(catalog.entry(required=NOTE_COPY_KEYS))


def _meta() -> NoteMeta:
    return NoteMeta(
        visit_id="visit-0001",
        protocol_hash="a" * 64,
        mode="detailed",
        generated_at=GENERATED_AT,
        model="synthetic-note-model@rev0",
        prompt_version="note-v0",
    )


def _screening() -> ScreeningBlock:
    return ScreeningBlock(
        provenance=ScreeningProvenance(
            administration_mode="typed",
            proxy_reported=False,
            third_party_present=False,
        )
    )


def _utterance(work_id: str, start: int, end: int) -> SourceSpan:
    return SourceSpan.utterance(work_id=work_id, char_start=start, char_end=end)


def _full_note() -> ComposedNote:
    """One composed note that exercises every attribution and every gap
    reason. Deliberately the SAME value the goldens are rendered from, so a
    behavioural change shows up in the snapshot rather than only in a rule."""
    return compose(
        meta=_meta(),
        triage=RulesTriageResult(
            level=TriageLevel.GREEN,
            rules=(RuleFire(id="rule.synthetic.none", evidence="slot_a=no"),),
        ),
        candidates=LlmCandidateTriage(
            candidate_flags=(
                CandidateFlag(text="sentetik aday bulgu", evidence="konusma-1: 40-58"),
            )
        ),
        chief_complaint=Sourced(
            ChiefComplaint(text="sentetik yakınma", patient_goals=("sentetik hedef",)),
            attribution=Attribution.PATIENT_SELF,
            span=_utterance("work-1", 0, 16),
        ),
        hpi=Sourced(
            Hpi(
                narrative="sentetik öykü",
                oldcarts=Oldcarts(onset="iki gün", severity_nrs=4),
            ),
            attribution=Attribution.PATIENT_SELF,
            span=_utterance("work-2", 0, 13),
        ),
        ros_pertinent=(
            Sourced(
                RosItem(system="sentetik-sistem", finding="sentetik bulgu", present=False),
                attribution=Attribution.PATIENT_SELF,
                span=_utterance("work-3", 4, 20),
            ),
        ),
        pmh=(
            Sourced(
                PmhItem(condition="Sentetik durum A", status="unconfirmed", source="patient"),
                attribution=Attribution.PATIENT_SELF,
                span=_utterance("work-4", 0, 16),
            ),
            Sourced(
                PmhItem(condition="Sentetik durum B", status="unconfirmed", source="record"),
                attribution=Attribution.RECORD,
                span=SourceSpan.document(
                    document_ref="doc-0001", page=2, bbox=(0.10, 0.20, 0.30, 0.40)
                ),
            ),
        ),
        medications=(
            Sourced(
                MedicationItem(
                    name="Sentetikol",
                    dose="günde bir kez bir tablet",
                    reconciliation="matches",
                ),
                attribution=Attribution.CARRIED,
                span=SourceSpan.earlier_visit(
                    visit_ref="visit-0000", asserted_at=datetime.date(2026, 5, 12)
                ),
            ),
        ),
        allergies=(
            Sourced(
                AllergyItem(substance="Sentetisilin", reaction="döküntü"),
                attribution=Attribution.CARRIED,
                span=SourceSpan.earlier_visit(
                    visit_ref="visit-0000", asserted_at=datetime.date(2026, 5, 12)
                ),
            ),
        ),
        family=(
            Sourced(
                "Sentetik kalıtsal durum",
                attribution=Attribution.RELATIVE,
                subject=FactSubject.MOTHER,
                span=_utterance("work-5", 0, 23),
            ),
        ),
        social=Sourced(
            FamilySocial(occupation="sentetik meslek"),
            attribution=Attribution.PATIENT_SELF,
            span=_utterance("work-6", 0, 15),
        ),
        measurements=(
            Sourced(
                SelfReportedMeasure(code=MeasureCode.HEIGHT, magnitude=Decimal("172"), unit="cm"),
                attribution=Attribution.PATIENT_SELF,
                span=_utterance("work-7", 0, 3),
            ),
            Sourced(
                SelfReportedMeasure(code=MeasureCode.WEIGHT, magnitude=Decimal("1234"), unit="kg"),
                attribution=Attribution.PATIENT_SELF,
                span=_utterance("work-8", 0, 4),
            ),
        ),
        imported_objective=(
            Sourced(
                ImportedObjectiveItem(type="lab", summary="sentetik tetkik", date="2026-05-12"),
                attribution=Attribution.RECORD,
                span=SourceSpan.document(document_ref="doc-0002", page=1),
            ),
        ),
        screening=_screening(),
        considerations=(Consideration(pattern="sentetik örüntü", why="sentetik gerekçe"),),
        suggested_focus_questions=("sentetik odak sorusu",),
        patient_confirmed_sections=("chief_complaint",),
        gaps=(
            NoteGap(section="screening", reason=NoteGapReason.DEFERRED_ENVIRONMENT, unit="phq2"),
            NoteGap(section="family_social", reason=NoteGapReason.DECLINED, unit="fh_father"),
            NoteGap(section="ros_pertinent", reason=NoteGapReason.SESSION_ENDED, unit="ros_gi"),
            NoteGap(
                section="pmh",
                reason=NoteGapReason.UNRESOLVED_PRECONDITION,
                unit="pmh_surgery_detail",
            ),
        ),
    )


def _decimal_note() -> ComposedNote:
    """A note whose quantities have a fractional part (INT-386). Every golden
    quantity above is a whole number, which reads the same in every locale, so
    the goldens alone cannot show which decimal point a renderer writes."""
    return compose(
        meta=_meta(),
        triage=RulesTriageResult(level=TriageLevel.GREEN),
        screening=_screening(),
        measurements=(
            Sourced(
                SelfReportedMeasure(code=MeasureCode.WEIGHT, magnitude=Decimal("72.5"), unit="kg"),
                attribution=Attribution.PATIENT_SELF,
                span=_utterance("work-1", 0, 4),
            ),
        ),
        konusma_ozellikleri=KonusmaOzellikleri(
            speech_rate_syll_s=4.1,
            pause_ratio=0.22,
            f0_mean_hz=142.5,
            f0_sd_hz=21.0,
            response_latency_ms_mean=610.25,
            reference_ranges={"speech_rate_syll_s": "sentetik"},
            recording_conditions_caveat_tr="sentetik kayıt koşulu",
        ),
    )


def _wire(obj: Any) -> dict[str, Any]:
    return json.loads(obj.model_dump_json(by_alias=True, exclude_none=True))


# --------------------------------------------------------------------------------------
# 1. every fact carries a source span — structurally, not by a check
# --------------------------------------------------------------------------------------


class TestSourceSpanIsStructural:
    def test_a_sourced_item_cannot_be_built_without_a_span(self) -> None:
        with pytest.raises(TypeError):
            Sourced(  # type: ignore[call-arg]
                PmhItem(condition="x", status="unconfirmed", source="patient"),
                attribution=Attribution.PATIENT_SELF,
            )

    def test_every_fact_placed_section_argument_is_a_sourced_wrapper(self) -> None:
        """The whole guarantee in one assertion: there is no parameter on
        ``compose`` that accepts a bare 04 §5 item, so there is no call that
        produces a fact without a span."""
        import inspect

        placed = {
            "chief_complaint",
            "hpi",
            "ros_pertinent",
            "pmh",
            "medications",
            "allergies",
            "family",
            "social",
            "measurements",
            "imported_objective",
        }
        hints = inspect.signature(compose).parameters
        for name in placed:
            annotation = str(hints[name].annotation)
            assert "Sourced" in annotation, f"{name} accepts an unsourced item"

    def test_every_rendered_fact_has_a_span_and_a_reference(self) -> None:
        composed = _full_note()
        assert composed.facts
        refs = [fact.ref for fact in composed.facts]
        assert len(refs) == len(set(refs))
        for fact in composed.facts:
            assert fact.span.locator
            assert fact.section in codes.NOTE_SECTION_IDS

    def test_span_locators_name_their_kind_and_never_carry_narrative(self) -> None:
        assert _utterance("work-1", 0, 4).locator == "utterance:work-1:0-4"
        assert (
            SourceSpan.document(document_ref="doc-1", page=3, bbox=(0.1, 0.2, 0.3, 0.4)).locator
            == "document:doc-1:p3:0.1,0.2,0.3,0.4"
        )
        assert (
            SourceSpan.earlier_visit(
                visit_ref="visit-0", asserted_at=datetime.date(2026, 5, 12)
            ).locator
            == "earlier_visit:visit-0:2026-05-12"
        )
        assert SourceSpan.rule(rule_id="rule.x").locator == "rule:rule.x"

    def test_a_span_refuses_an_end_before_its_start(self) -> None:
        with pytest.raises(ValueError, match="char_end"):
            SourceSpan.utterance(work_id="w", char_start=9, char_end=2)


# --------------------------------------------------------------------------------------
# 2. attribution — the INT-282 rule, generalised
# --------------------------------------------------------------------------------------


class TestAttribution:
    def test_the_attribution_table_is_exactly_the_declared_one(self) -> None:
        """Written out member by member rather than derived, so widening a row
        is a diff a reviewer reads. INT-299 widened eight of the nine with
        ``TRANSLATED``: a translated answer goes wherever the patient's own
        answer goes, and ``imported_objective`` — the record-only row — is the
        one it does not reach."""
        self_reported = frozenset({Attribution.PATIENT_SELF, Attribution.TRANSLATED})
        assert SECTION_ATTRIBUTIONS == {
            "chief_complaint": self_reported,
            "hpi": self_reported,
            "ros_pertinent": self_reported,
            "pmh": self_reported | {Attribution.RECORD, Attribution.CARRIED},
            "medications": self_reported | {Attribution.RECORD, Attribution.CARRIED},
            "allergies": self_reported | {Attribution.RECORD, Attribution.CARRIED},
            "family_social": self_reported | {Attribution.RELATIVE},
            "measurements": self_reported,
            "imported_objective": frozenset({Attribution.RECORD}),
        }

    def test_relative_is_admissible_in_exactly_one_section(self) -> None:
        """INT-282's finding stated once, where a reviewer reads it: a
        relative's condition has exactly one home and it is not the patient's
        history."""
        admits = [s for s, a in SECTION_ATTRIBUTIONS.items() if Attribution.RELATIVE in a]
        assert admits == ["family_social"]

    def test_a_relative_condition_cannot_be_composed_into_pmh(self) -> None:
        with pytest.raises(AttributionRefused, match="pmh"):
            compose(
                meta=_meta(),
                triage=RulesTriageResult(level=TriageLevel.GREEN),
                screening=_screening(),
                pmh=(
                    Sourced(
                        PmhItem(
                            condition="Sentetik kalıtsal durum",
                            status="unconfirmed",
                            source="patient",
                        ),
                        attribution=Attribution.RELATIVE,
                        subject=FactSubject.MOTHER,
                        span=_utterance("work-1", 0, 23),
                    ),
                ),
            )

    def test_a_relative_attribution_requires_a_relative_subject(self) -> None:
        with pytest.raises(ValueError, match="subject"):
            Sourced(
                "Sentetik kalıtsal durum",
                attribution=Attribution.RELATIVE,
                subject=FactSubject.PATIENT,
                span=_utterance("work-1", 0, 23),
            )

    def test_a_non_relative_attribution_requires_the_patient_as_subject(self) -> None:
        with pytest.raises(ValueError, match="subject"):
            Sourced(
                PmhItem(condition="Sentetik durum", status="unconfirmed", source="patient"),
                attribution=Attribution.PATIENT_SELF,
                subject=FactSubject.MOTHER,
                span=_utterance("work-1", 0, 15),
            )

    def test_a_relative_condition_is_never_the_patients_in_any_renderer(
        self, copy: NoteCopy
    ) -> None:
        """The sharp edge, asserted three times over — once per renderer.

        The condition string exists exactly once in each rendering, on a line
        that names the relative, and it never appears under the patient's own
        history or as a subject-referencing FHIR resource."""
        composed = _full_note()
        condition = "Sentetik kalıtsal durum"

        # (a) the note value itself: family_social, tagged with the relative
        # code, and absent from pmh.
        assert composed.note.family_social.family == (f"{FactSubject.MOTHER.value}: {condition}",)
        assert all(condition not in item.condition for item in composed.note.pmh)

        # (b) SOAP: on a line carrying the relative marker, under the
        # family_social heading, and on no other line.
        soap = render_soap(composed, copy)
        carrying = [line for line in soap.splitlines() if condition in line]
        assert len(carrying) == 1
        assert copy.subject(FactSubject.MOTHER) in carrying[0]
        assert copy.attribution(Attribution.RELATIVE) in carrying[0]
        assert copy.attribution(Attribution.PATIENT_SELF) not in carrying[0]

        # (c) FHIR: only inside the family_social section's narrative — never
        # a Condition, which would assert it of the Patient.
        wire = _wire(render_fhir_document(composed, patient_id="pt-0001"))
        payload = json.dumps(wire, ensure_ascii=False)
        assert payload.count(condition) == 1
        composition = wire["entry"][0]["resource"]
        holders = [
            section["code"]["coding"][0]["code"]
            for section in composition["section"]
            if condition in json.dumps(section, ensure_ascii=False)
        ]
        assert holders == ["family_social"]
        for entry in wire["entry"]:
            resource = entry["resource"]
            if resource.get("resourceType") == "Condition":
                assert condition not in json.dumps(resource, ensure_ascii=False)

        # (d) PDF: same single line, same marker.
        pdf = render_note_pdf(composed, copy).decode("latin-1")
        assert pdf.count(_pdf_literal(condition)) == 1

    def test_a_carried_fact_is_distinguishable_from_this_visits_statement(
        self, copy: NoteCopy
    ) -> None:
        """INT-256's lesson at the note layer: a fact recorded at an earlier
        visit and a sentence the patient said today are different findings,
        and the difference survives every renderer."""
        composed = _full_note()
        soap = render_soap(composed, copy)
        carried = [line for line in soap.splitlines() if "Sentetikol" in line]
        assert len(carried) == 1
        assert copy.attribution(Attribution.CARRIED) in carried[0]
        assert "2026-05-12" in carried[0]

        own = [line for line in soap.splitlines() if "Sentetik durum A" in line]
        assert len(own) == 1
        assert copy.attribution(Attribution.PATIENT_SELF) in own[0]
        assert copy.attribution(Attribution.CARRIED) not in own[0]

        # and in FHIR the two carry different provenance extensions
        wire = _wire(render_fhir_document(composed, patient_id="pt-0001"))
        extensions = {
            ext["valueString"]
            for ext in wire["entry"][0]["resource"]["extension"]
            if ext["url"] == codes.EXT_FACT_PROVENANCE
        }
        assert any("carried" in value and "earlier_visit" in value for value in extensions)
        assert any("patient_self" in value and "utterance" in value for value in extensions)

    def test_three_attributions_never_share_a_marker(self, copy: NoteCopy) -> None:
        markers = [copy.attribution(a) for a in Attribution]
        assert len(markers) == len(set(markers))


# --------------------------------------------------------------------------------------
# 3. what is missing, and why — three different facts that never collapse
# --------------------------------------------------------------------------------------


class TestGapsDoNotCollapse:
    def test_the_reason_set_is_closed_and_has_four_members(self) -> None:
        assert [reason.value for reason in NoteGapReason] == [
            "deferred_environment",
            "declined",
            "session_ended",
            "unresolved_precondition",
        ]

    def test_a_gap_carries_a_reason_code_and_never_free_text(self) -> None:
        """files/02 §33's ``eksik: ortam uygun değildi`` is a different fact
        from "the patient declined" and from "we ran out of turns". A free
        string would let two of them become one; an enum cannot."""
        gap = NoteGap(section="screening", reason=NoteGapReason.DECLINED, unit="phq2")
        assert not hasattr(gap, "text")
        assert gap.code == "screening:declined:phq2"

    def test_data_gaps_carry_section_reason_and_unit_language_neutrally(self) -> None:
        composed = _full_note()
        assert composed.note.data_gaps == (
            "screening:deferred_environment:phq2",
            "family_social:declined:fh_father",
            "ros_pertinent:session_ended:ros_gi",
            "pmh:unresolved_precondition:pmh_surgery_detail",
        )

    def test_the_four_reasons_render_to_four_different_markers(self, copy: NoteCopy) -> None:
        markers = [copy.gap(reason) for reason in NoteGapReason]
        assert len(markers) == len(set(markers))
        soap = render_soap(_full_note(), copy)
        for marker in markers:
            assert marker in soap

    def test_the_environment_deferral_keeps_the_02_33_wording(self, copy: NoteCopy) -> None:
        assert copy.gap(NoteGapReason.DEFERRED_ENVIRONMENT) == "eksik: ortam uygun değildi"

    def test_an_unresolved_precondition_is_a_gap_the_note_can_express(self) -> None:
        """files/13 §9.4 and docs/evidence/INT-282.md: the engine counts a
        must-ask step whose gate is TRUE **or UNKNOWN** as obliged; mobile
        keeps gate-TRUE only and calls the rest "skipped, not missing". The
        note takes the engine's definition, because under-reporting what is
        absent is the dangerous direction on a partial note — and it takes it
        by having a reason for it at all. Mobile's definition is not
        representable here: it produces no gap."""
        assert NoteGapReason.UNRESOLVED_PRECONDITION in set(NoteGapReason)
        composed = _full_note()
        assert any("unresolved_precondition" in gap for gap in composed.note.data_gaps)

    def test_gaps_and_facts_never_describe_the_same_thing(self) -> None:
        composed = _full_note()
        gap_sections = {gap.section for gap in composed.gaps}
        assert "screening" in gap_sections


# --------------------------------------------------------------------------------------
# 4. invariant 1 at the note layer
# --------------------------------------------------------------------------------------


class TestCandidatesNeverBecomeFindings:
    def test_the_note_level_is_the_rules_level(self) -> None:
        composed = compose(
            meta=_meta(),
            triage=RulesTriageResult(level=TriageLevel.GREEN),
            candidates=LlmCandidateTriage(
                candidate_flags=(CandidateFlag(text="sentetik aday", evidence="work-1: 0-13"),)
            ),
            screening=_screening(),
        )
        assert composed.note.triage.level is TriageLevel.GREEN
        assert len(composed.note.triage.llm_candidates) == 1

    def test_compose_has_no_parameter_that_could_carry_a_candidate_level(self) -> None:
        import inspect

        source = inspect.getsource(compose)
        assert "YELLOW_REVIEW" not in source

    def test_a_candidate_is_never_placed_as_a_fact(self) -> None:
        composed = _full_note()
        assert all(fact.attribution is not Attribution.LLM_CANDIDATE for fact in composed.facts)

    def test_a_candidate_renders_under_its_own_heading_and_never_as_a_finding(
        self, copy: NoteCopy
    ) -> None:
        composed = _full_note()
        soap = render_soap(composed, copy)
        lines = soap.splitlines()
        index = next(i for i, line in enumerate(lines) if "sentetik aday bulgu" in line)
        heading = copy.value("previsit_note.heading.candidates")
        assert heading in "\n".join(lines[:index])
        assert copy.attribution(Attribution.LLM_CANDIDATE) in lines[index]
        # and never inside the S block, where a clinician reads findings
        subjective = soap.split(copy.value("previsit_note.soap.objective"))[0]
        assert "sentetik aday bulgu" not in subjective

    def test_candidates_still_never_cross_into_fhir(self) -> None:
        composed = _full_note()
        payload = json.dumps(
            _wire(render_fhir_document(composed, patient_id="pt-0001")), ensure_ascii=False
        )
        assert "sentetik aday bulgu" not in payload
        assert "YELLOW_REVIEW" not in payload


# --------------------------------------------------------------------------------------
# 5. the disclaimer — files/06 §7, hash-bound, and reachable at every size
# --------------------------------------------------------------------------------------


class TestDisclaimer:
    def test_the_production_catalogue_does_not_exist_and_the_note_fails_closed(self) -> None:
        """Invariant 18 + HUMAN_BLOCKERS rule 2: the mechanism is built, the
        gate is wired, it fails closed, and the content stays empty until
        counsel supplies it (INT-210, files/06 §7)."""
        production = REPO / "docs" / "legal" / "strings.yaml"
        assert not production.exists()
        with pytest.raises(LegalStringsMissingError):
            note_copy_from_legal_strings(
                LegalStringsCatalog(production).entry(required=NOTE_COPY_KEYS)
            )

    def test_the_footer_key_is_required_copy(self) -> None:
        assert "previsit_note.footer" in NOTE_COPY_KEYS

    def test_a_catalogue_missing_the_footer_refuses_the_whole_note(self, tmp_path: Path) -> None:
        text = SYNTHETIC_STRINGS.read_text(encoding="utf-8")
        stripped = "\n".join(
            line for line in text.splitlines() if not line.startswith("previsit_note.footer:")
        )
        path = tmp_path / "strings.yaml"
        path.write_text(stripped + "\n", encoding="utf-8")
        with pytest.raises(LegalStringsMissingError, match="previsit_note.footer"):
            note_copy_from_legal_strings(LegalStringsCatalog(path).entry(required=NOTE_COPY_KEYS))

    def test_the_footer_is_the_06_7_wording_and_is_on_the_note(self, copy: NoteCopy) -> None:
        assert copy.value("previsit_note.footer") == FOOTER_06_7
        assert FOOTER_06_7 in render_soap(_full_note(), copy)

    def test_the_footer_is_on_every_page_of_the_pdf(self, copy: NoteCopy) -> None:
        """INT-284's lesson, translated to paper: the line is load-bearing, so
        it must be reachable however long the note gets. The footer band is
        reserved below the content box before pagination, so content can never
        push it off a page and never overlap it."""
        pages = _pdf_pages(render_note_pdf(_long_note(), copy))
        assert len(pages) > 3
        for drawn in pages:
            assert _pdf_literal(FOOTER_06_7) in " ".join(drawn)

    def test_the_footer_survives_a_watermark_on_every_page(self, copy: NoteCopy) -> None:
        pages = _pdf_pages(render_note_pdf(_long_note(), copy, watermark="visit-0001 · pt-0001"))
        for drawn in pages:
            assert _pdf_literal("visit-0001 · pt-0001") in drawn
            assert _pdf_literal(FOOTER_06_7) in " ".join(drawn)

    def test_the_footer_is_never_truncated_to_fit(self, copy: NoteCopy) -> None:
        """The wrap is by whole words, so rejoining the drawn segments with a
        single space reproduces files/06 §7 verbatim. A footer that did not
        fit its band would have raised rather than lost its tail."""
        for page in _pdf_pages(render_note_pdf(_full_note(), copy)):
            assert _pdf_literal(FOOTER_06_7) in " ".join(page)

    def test_a_footer_too_long_for_its_band_is_refused_not_shrunk(self) -> None:
        with pytest.raises(FooterTooLongError):
            render_document_pdf(title="t", lines=["l"], footer="söz " * 200)


# --------------------------------------------------------------------------------------
# 6. the `notes` threat-model row
# --------------------------------------------------------------------------------------


class TestNoteRenderingIsNotMarkup:
    def test_a_script_tag_in_a_fact_is_escaped_in_the_fhir_narrative(self) -> None:
        composed = _hostile_note()
        payload = json.dumps(
            _wire(render_fhir_document(composed, patient_id="pt-0001")), ensure_ascii=False
        )
        assert "<script>" not in payload
        assert "&lt;script&gt;" in payload

    def test_the_soap_render_is_text_and_carries_no_markup_of_its_own(self, copy: NoteCopy) -> None:
        soap = render_soap(_hostile_note(), copy)
        # the hostile string survives verbatim as TEXT — never rewritten, and
        # never joined by markup the renderer itself emitted
        assert "<script>alert(1)</script>" in soap
        assert re.search(r"<(?!script|/script)[a-zA-Z]", soap) is None

    def test_the_pdf_render_never_transliterates_a_turkish_letter(self, copy: NoteCopy) -> None:
        pdf = render_note_pdf(_full_note(), copy)
        assert b"Basvuru" not in pdf


class TestProvenanceIsReachable:
    def test_every_fact_line_in_soap_carries_a_reference_that_resolves(
        self, copy: NoteCopy
    ) -> None:
        composed = _full_note()
        soap = render_soap(composed, copy)
        refs = set(re.findall(r"\[(f\d{2})\]", soap))
        assert refs == {fact.ref for fact in composed.facts}
        provenance = soap.split(copy.value("previsit_note.heading.provenance"))[1]
        for fact in composed.facts:
            assert f"[{fact.ref}] {fact.span.locator}" in provenance

    def test_every_fact_reaches_the_fhir_document_as_a_provenance_extension(self) -> None:
        composed = _full_note()
        wire = _wire(render_fhir_document(composed, patient_id="pt-0001"))
        values = [
            ext["valueString"]
            for ext in wire["entry"][0]["resource"]["extension"]
            if ext["url"] == codes.EXT_FACT_PROVENANCE
        ]
        assert len(values) == len(composed.facts)
        for fact in composed.facts:
            assert any(value.startswith(f"{fact.ref}|") for value in values)
            assert any(fact.span.locator in value for value in values)


# --------------------------------------------------------------------------------------
# 7. invariants 20 and 22
# --------------------------------------------------------------------------------------


class TestNoPerformanceClaims:
    def test_no_renderer_emits_an_accuracy_word(self, copy: NoteCopy) -> None:
        forbidden = ("duyarlılık", "özgüllük", "doğruluk", "AUROC", "WER", "%")
        soap = render_soap(_full_note(), copy)
        for word in forbidden:
            assert word not in soap
        assert not any(word in " ".join(NOTE_COPY_KEYS) for word in forbidden)


class TestNumbersNeverCrossUnguarded:
    def test_a_quantity_is_one_non_breaking_atom_without_grouping(self, copy: NoteCopy) -> None:
        soap = render_soap(_full_note(), copy)
        assert "1234 kg" in soap
        assert "1.234" not in soap
        assert "1,234" not in soap

    def test_the_same_atom_reaches_the_fhir_narrative(self) -> None:
        payload = json.dumps(
            _wire(render_fhir_document(_full_note(), patient_id="pt-0001")), ensure_ascii=False
        )
        assert "1234 kg" in payload

    def test_a_decimal_is_written_with_the_notes_decimal_comma_on_every_face(
        self, copy: NoteCopy
    ) -> None:
        """INT-386. The note's language is Turkish, and a Turkish reader takes a
        full stop as grouping. Every face of the note writes the self-reported
        measure and the speech measures with a comma, and the near miss, the
        full stop all three wrote before, is absent."""
        composed = _decimal_note()
        soap = render_soap(composed, copy)
        assert "weight: 72,5 kg" in soap
        assert "f0_mean_hz: 142,5" in soap
        assert "response_latency_ms_mean: 610,25" in soap
        pdf = "\n".join(
            line
            for page in _pdf_pages(render_note_pdf(composed, copy, watermark="visit-0001"))
            for line in page
        )
        assert "72,5" in pdf
        assert "142,5" in pdf
        payload = json.dumps(
            _wire(render_fhir_document(composed, patient_id="pt-0001")), ensure_ascii=False
        )
        assert "<p>weight: 72,5 kg</p>" in payload
        assert "<p>f0_mean_hz: 142,5 Hz</p>" in payload
        for face in (soap, pdf, payload):
            for near_miss in ("72.5", "142.5", "610.25", "4.1", "0.22"):
                assert near_miss not in face, near_miss

    def test_a_rule_evidence_decimal_is_written_with_the_notes_decimal_comma(
        self, copy: NoteCopy
    ) -> None:
        """INT-404. A fired rule's evidence line is written from the fire's
        parts for the note's reader on every face. The engine's own text,
        with its full stop, is the near miss: no face prints it."""
        fire = RuleFire(
            id="rule.synthetic.olcum",
            evidence="synthetic.olcum=38.50",
            evidence_slots=(
                EvidenceSlot(slot="synthetic.olcum", values=(Decimal("38.50"),), unit="°C"),
            ),
        )
        composed = compose(
            meta=_meta(),
            triage=RulesTriageResult(level=TriageLevel.YELLOW, rules=(fire,)),
            screening=_screening(),
        )
        soap = render_soap(composed, copy)
        assert "  [rule.synthetic.olcum] synthetic.olcum=38,50 °C\n" in soap
        pdf = "\n".join(
            line
            for page in _pdf_pages(render_note_pdf(composed, copy, watermark="visit-0001"))
            for line in page
        )
        assert _pdf_literal("[rule.synthetic.olcum] synthetic.olcum=38,50 °C") in pdf
        payload = json.dumps(
            _wire(render_fhir_document(composed, patient_id="pt-0001")), ensure_ascii=False
        )
        assert "<p>rule rule.synthetic.olcum: synthetic.olcum=38,50 °C</p>" in payload
        for face in (soap, pdf, payload):
            assert "38.50" not in face

    def test_a_measure_keeps_its_exact_decimal(self) -> None:
        measure = SelfReportedMeasure(code=MeasureCode.WEIGHT, magnitude=Decimal("72.5"), unit="kg")
        assert str(measure.magnitude) == "72.5"

    def test_an_absent_severity_is_not_rendered_as_zero(self, copy: NoteCopy) -> None:
        composed = compose(
            meta=_meta(),
            triage=RulesTriageResult(level=TriageLevel.GREEN),
            screening=_screening(),
            hpi=Sourced(
                Hpi(narrative="sentetik öykü", oldcarts=Oldcarts()),
                attribution=Attribution.PATIENT_SELF,
                span=_utterance("work-1", 0, 13),
            ),
        )
        assert "severity_nrs" not in render_soap(composed, copy)


# --------------------------------------------------------------------------------------
# 8. the 04 §5 schema addition
# --------------------------------------------------------------------------------------


class TestMeasurementsField:
    def test_measurements_is_a_note_section_in_note_order(self) -> None:
        assert "measurements" in codes.NOTE_SECTION_IDS
        ids = list(codes.NOTE_SECTION_IDS)
        assert ids.index("family_social") < ids.index("measurements") < ids.index("screening")

    def test_the_code_set_is_anthropometry_only(self) -> None:
        """02 §2 promises "vitals entry" but INT-282 asserted by name that
        pulse, blood pressure and respiration are clinician-measured rows the
        patient is never asked. Naming this block ``vitals`` would invite a
        patient-typed blood pressure into a clinician note; naming what
        actually exists does not."""
        assert [code.value for code in MeasureCode] == ["height", "weight"]

    def test_the_pain_score_uses_the_field_04_5_already_has(self) -> None:
        assert "severity_nrs" in Oldcarts.model_fields
        assert not any("pain" in code.value for code in MeasureCode)

    def test_the_document_mapper_renders_the_new_section(self) -> None:
        note = _full_note().note
        wire = _wire(previsit_note_to_document_bundle(note, patient_id="pt-0001"))
        composition = wire["entry"][0]["resource"]
        section = next(
            s for s in composition["section"] if s["code"]["coding"][0]["code"] == "measurements"
        )
        assert "172 cm" in json.dumps(section, ensure_ascii=False)


# --------------------------------------------------------------------------------------
# 9. golden snapshots
# --------------------------------------------------------------------------------------


class TestGoldens:
    def test_soap_golden(self, copy: NoteCopy) -> None:
        _assert_golden("note_soap.txt", render_soap(_full_note(), copy))

    def test_fhir_golden(self) -> None:
        wire = _wire(render_fhir_document(_full_note(), patient_id="pt-0001"))
        _assert_golden(
            "note_fhir.json", json.dumps(wire, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )

    def test_pdf_text_layer_golden(self, copy: NoteCopy) -> None:
        pdf = render_note_pdf(_full_note(), copy, watermark="visit-0001 · pt-0001")
        drawn = "\n".join(line for page in _pdf_pages(pdf) for line in page)
        _assert_golden("note_pdf_text.txt", drawn + "\n")

    def test_the_render_is_deterministic(self, copy: NoteCopy) -> None:
        first, second = _full_note(), _full_note()
        assert render_soap(first, copy) == render_soap(second, copy)
        assert render_note_pdf(first, copy) == render_note_pdf(second, copy)


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _pdf_literal(text: str) -> str:
    return encode_text(text).decode("latin-1")


def _pdf_pages(pdf: bytes) -> list[list[str]]:
    """The drawn text of each page, in draw order — the PDF's own text layer,
    read back the way a reader would."""
    streams = re.findall(rb"stream\n(.*?)endstream", pdf, re.S)
    return [re.findall(r"\((.*?)\) Tj", stream.decode("latin-1")) for stream in streams]


def _long_note() -> ComposedNote:
    return compose(
        meta=_meta(),
        triage=RulesTriageResult(level=TriageLevel.GREEN),
        screening=_screening(),
        ros_pertinent=tuple(
            Sourced(
                RosItem(system=f"sistem-{index:03d}", finding="sentetik bulgu", present=False),
                attribution=Attribution.PATIENT_SELF,
                span=_utterance(f"work-{index}", 0, 8),
            )
            for index in range(180)
        ),
    )


def _hostile_note() -> ComposedNote:
    return compose(
        meta=_meta(),
        triage=RulesTriageResult(level=TriageLevel.GREEN),
        screening=_screening(),
        chief_complaint=Sourced(
            ChiefComplaint(text="<script>alert(1)</script>"),
            attribution=Attribution.PATIENT_SELF,
            span=_utterance("work-1", 0, 25),
        ),
    )


def _assert_golden(name: str, rendered: str) -> None:
    path = GOLDEN / name
    if not path.exists():  # pragma: no cover - first authoring only
        raise AssertionError(f"missing golden {path}")
    assert rendered == path.read_text(encoding="utf-8")


def test_the_note_value_round_trips_through_json() -> None:
    note = _full_note().note
    assert PreVisitNote.model_validate_json(note.model_dump_json()) == note
