"""INT-299 — a translated answer is not the patient's words.

Acceptance lines under test, verbatim from docs/backlog/issues.yaml:

1. *"a line built from a translated answer carries `translated` rather than
   `hasta beyanı`"* — :class:`TestATranslatedLineIsNotHastaBeyani`.
2. *"the original is retained verbatim beside the rendering, with its source
   locale, and is reachable from the clinician surface"* —
   :class:`TestTheOriginalIsTheRecord`.
3. *"the translator is identified the way a model is: name, `model_id@revision`
   and `sha256` … a line whose translator cannot be identified raises rather
   than rendering unattributed"* —
   :class:`TestTheTranslatorIsIdentifiedTheWayAModelIs`.
4. *"INT-085's patient summary refuses a translated line whose original the
   patient can no longer see"* — :class:`TestTheSummaryNeverShowsTheMachineVersion`.
5. *"the attribution vocabulary gains exactly one member and the addition is
   closed"* — :class:`TestTheVocabularyIsClosed`.

Every value here is synthetic (files/04 §7). No translator is registered and
no locale beyond ``tr`` exists, so the tests build their identities and their
source locales explicitly: the seam is what ships, not a model.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from pathlib import Path

import pytest
from clinical_schemas.note import (
    ChiefComplaint,
    Hpi,
    ImportedObjectiveItem,
    NoteMeta,
    Oldcarts,
    PmhItem,
    ScreeningBlock,
    ScreeningProvenance,
)
from clinical_schemas.triage import RuleFire, RulesTriageResult, TriageLevel
from intake_platform.legal import LegalStringsCatalog
from intake_platform.locale import DEFAULT_LOCALE
from intake_voice_runtime.note import (
    NOTE_COPY_KEYS,
    SECTION_ATTRIBUTIONS,
    Attribution,
    AttributionRefused,
    ComposedNote,
    FactSubject,
    NoteCopy,
    NoteFact,
    Sourced,
    SourceSpan,
    TranslatedOriginalUnreachable,
    TranslatedText,
    TranslatorIdentity,
    TranslatorUnidentified,
    compose,
    facts_by_section,
    note_copy_from_legal_strings,
    render_fhir_document,
    render_note_pdf,
    render_soap,
    translator,
)
from intake_voice_runtime.note.translation import TRANSLATOR_REGISTRY
from intake_voice_runtime.summary import (
    SUMMARY_ATTRIBUTIONS,
    SUMMARY_COPY_KEYS,
    PatientSummaryCopy,
    SummaryRefused,
    build_patient_summary,
    summary_copy_from_legal_strings,
)

REPO = Path(__file__).resolve().parents[2]
NOTE_STRINGS = REPO / "tests" / "fixtures" / "legal" / "strings.synthetic.yaml"
SUMMARY_STRINGS = REPO / "tests" / "fixtures" / "legal" / "strings.summary.synthetic.yaml"
GENERATED_AT = datetime.datetime(2026, 9, 2, 9, 30, tzinfo=datetime.UTC)

#: A synthetic source locale. Registering it is HB-O5's, HB-C19's, HB-L23's,
#: HB-L24's and HB-L25's — five humans — so nothing here registers it. A
#: translated line records the locale it *came from*; it does not make that
#: locale offerable, and a test below asserts the registry is untouched.
SOURCE_LOCALE = "qx"

#: Synthetic patient material. The original and the rendering are deliberately
#: unlike each other so a test can assert which one a surface showed.
ORIGINAL_COMPLAINT = "SENTETIK-OZGUN-YAKINMA"
RENDERED_COMPLAINT = "Sentetik çevrilmiş yakınma"
ORIGINAL_CONDITION = "SENTETIK-OZGUN-DURUM"
RENDERED_CONDITION = "Sentetik çevrilmiş durum"

#: A synthetic translator identity, in the shape files/03 §4.9.4 uses for a
#: model: a name, ``model_id@revision`` and a weight hash.
TRANSLATOR = TranslatorIdentity(
    name="sentetik-ceviri",
    model_id="sentetik/ceviri-modeli",
    revision="rev0",
    sha256="c" * 64,
)


# --------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------


@pytest.fixture
def copy() -> NoteCopy:
    catalog = LegalStringsCatalog(NOTE_STRINGS)
    return note_copy_from_legal_strings(catalog.entry(required=NOTE_COPY_KEYS))


@pytest.fixture
def patient_copy() -> PatientSummaryCopy:
    catalog = LegalStringsCatalog(SUMMARY_STRINGS)
    return summary_copy_from_legal_strings(catalog.entry(required=SUMMARY_COPY_KEYS))


def _meta() -> NoteMeta:
    return NoteMeta(
        visit_id="visit-0299",
        protocol_hash="d" * 64,
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


def _translated(original: str) -> TranslatedText:
    return TranslatedText(
        original,
        source_locale=SOURCE_LOCALE,
        translator=TRANSLATOR,
    )


def _translated_note(*, level: TriageLevel = TriageLevel.GREEN) -> ComposedNote:
    """One note whose chief complaint and one history item are translated."""
    return compose(
        meta=_meta(),
        triage=RulesTriageResult(
            level=level,
            rules=(RuleFire(id="rule.synthetic.none", evidence="slot_a=no"),),
        ),
        screening=_screening(),
        chief_complaint=Sourced(
            ChiefComplaint(text=RENDERED_COMPLAINT),
            attribution=Attribution.TRANSLATED,
            span=SourceSpan.utterance(work_id="work-1", char_start=0, char_end=22),
            translation=_translated(ORIGINAL_COMPLAINT),
        ),
        hpi=Sourced(
            Hpi(narrative="", oldcarts=Oldcarts()),
            attribution=Attribution.PATIENT_SELF,
            span=SourceSpan.utterance(work_id="work-2", char_start=0, char_end=1),
        ),
        pmh=(
            Sourced(
                PmhItem(condition=RENDERED_CONDITION, status="unconfirmed", source="patient"),
                attribution=Attribution.TRANSLATED,
                span=SourceSpan.utterance(work_id="work-3", char_start=0, char_end=21),
                translation=_translated(ORIGINAL_CONDITION),
            ),
        ),
    )


def _untranslated_note() -> ComposedNote:
    return compose(
        meta=_meta(),
        triage=RulesTriageResult(level=TriageLevel.GREEN, rules=()),
        screening=_screening(),
        chief_complaint=Sourced(
            ChiefComplaint(text=RENDERED_COMPLAINT),
            attribution=Attribution.PATIENT_SELF,
            span=SourceSpan.utterance(work_id="work-1", char_start=0, char_end=22),
        ),
    )


# --------------------------------------------------------------------------------------
# 5. the vocabulary gains exactly one member, and the addition is closed
# --------------------------------------------------------------------------------------


class TestTheVocabularyIsClosed:
    def test_the_attribution_enum_is_exactly_these_seven(self) -> None:
        """Walks the enum and asserts the set. A later locale that wants a
        second translated-ish class — "post-edited", "interpreted",
        "clinician-translated" — has to change this line, and changing it is
        the review."""
        assert {member.value for member in Attribution} == {
            "patient_self",
            "relative",
            "carried",
            "record",
            "rules_engine",
            "llm_candidate",
            "translated",
        }
        assert len(Attribution) == 7

    def test_exactly_one_member_is_about_translation(self) -> None:
        translated = [member for member in Attribution if "translat" in member.value]
        assert translated == [Attribution.TRANSLATED]

    def test_the_note_copy_key_set_gained_exactly_one_key(self) -> None:
        keys = [key for key in NOTE_COPY_KEYS if key.startswith("previsit_note.attribution.")]
        assert len(keys) == len(Attribution)
        assert keys.count("previsit_note.attribution.translated") == 1

    def test_the_summary_still_has_no_word_for_a_rule_or_a_candidate(self) -> None:
        """INT-085's safety property is a *missing vocabulary*, not a filter.
        Adding `translated` must not have widened the set that reaches a
        patient's card."""
        assert Attribution.TRANSLATED in SUMMARY_ATTRIBUTIONS
        assert Attribution.RULES_ENGINE not in SUMMARY_ATTRIBUTIONS
        assert Attribution.LLM_CANDIDATE not in SUMMARY_ATTRIBUTIONS
        joined = " ".join(SUMMARY_COPY_KEYS)
        assert "rules_engine" not in joined
        assert "llm_candidate" not in joined

    def test_a_translated_answer_goes_where_the_patients_own_answer_goes(self) -> None:
        """One rule, stated as an equivalence rather than a second table: a
        section admits `translated` exactly when it admits `patient_self`. A
        section that took a translation but not a direct statement — or the
        reverse — would be a place the two are distinguished for a reason
        nobody wrote down."""
        for section, admitted in SECTION_ATTRIBUTIONS.items():
            assert (Attribution.TRANSLATED in admitted) == (Attribution.PATIENT_SELF in admitted), (
                section
            )

    def test_no_locale_was_registered_by_this_issue(self) -> None:
        """HB-O5, HB-C19, HB-L23, HB-L24 and HB-L25 all sit between this
        mechanism and a second language. The seam ships; the content does
        not."""
        from intake_platform.locale import enabled_locales

        assert enabled_locales() == (DEFAULT_LOCALE,)
        assert dict(TRANSLATOR_REGISTRY) == {}


# --------------------------------------------------------------------------------------
# 1. a translated line is not `hasta beyanı`
# --------------------------------------------------------------------------------------


class TestATranslatedLineIsNotHastaBeyani:
    def test_the_marker_is_the_translated_one_and_names_the_source_locale(
        self, copy: NoteCopy
    ) -> None:
        soap = render_soap(_translated_note(), copy)
        patient_self = copy.attribution(Attribution.PATIENT_SELF)
        translated = copy.attribution(Attribution.TRANSLATED)
        assert patient_self != translated

        line = _line_containing(soap, RENDERED_COMPLAINT)
        assert translated in line
        assert SOURCE_LOCALE in line
        assert patient_self not in line

    def test_no_fact_line_carries_the_clinicians_phrase_for_a_direct_statement(
        self, copy: NoteCopy
    ) -> None:
        """Both facts are translated and the only untranslated one is an empty
        HPI that renders no line, so no `[fNN]` line says `hasta beyanı`.

        The whole document still does: the S block's own heading is *"S —
        hasta beyanı"* in the catalogue, which is the SOAP split's name for
        the block and not a claim about any one line. Asserting over the fact
        lines is the assertion that means something."""
        soap = render_soap(_translated_note(), copy)
        patient_self = copy.attribution(Attribution.PATIENT_SELF)
        fact_lines = [line for line in soap.splitlines() if "[f" in line]
        assert fact_lines
        assert not [line for line in fact_lines if patient_self in line]

    def test_an_untranslated_note_still_says_hasta_beyani(self, copy: NoteCopy) -> None:
        """The negative control: the change is to translated lines only."""
        soap = render_soap(_untranslated_note(), copy)
        assert copy.attribution(Attribution.PATIENT_SELF) in soap
        assert copy.attribution(Attribution.TRANSLATED) not in soap

    def test_a_translated_fact_carries_the_attribution_on_the_fact(self) -> None:
        composed = _translated_note()
        (fact,) = facts_by_section(composed, "chief_complaint")
        assert fact.attribution is Attribution.TRANSLATED
        assert fact.subject is FactSubject.PATIENT


# --------------------------------------------------------------------------------------
# 2. the original is the record
# --------------------------------------------------------------------------------------


class TestTheOriginalIsTheRecord:
    def test_the_original_rides_on_the_fact_verbatim_with_its_locale(self) -> None:
        composed = _translated_note()
        (fact,) = facts_by_section(composed, "chief_complaint")
        assert fact.translation is not None
        assert fact.translation.original == ORIGINAL_COMPLAINT
        assert fact.translation.source_locale == SOURCE_LOCALE

    def test_the_original_is_reachable_in_the_soap_face(self, copy: NoteCopy) -> None:
        soap = render_soap(_translated_note(), copy)
        assert ORIGINAL_COMPLAINT in soap
        assert ORIGINAL_CONDITION in soap

    def test_the_original_sits_beside_its_own_rendering(self, copy: NoteCopy) -> None:
        """Beside, not in a block somewhere else: the original line follows
        the line it is the original *of*, and carries the same `fNN` handle,
        so a clinician reading one is already reading the other."""
        lines = render_soap(_translated_note(), copy).splitlines()
        rendered_at = _index_of(lines, RENDERED_COMPLAINT)
        assert ORIGINAL_COMPLAINT in lines[rendered_at + 1]
        assert SOURCE_LOCALE in lines[rendered_at + 1]
        # indented further than the rendering it belongs to
        assert _indent(lines[rendered_at + 1]) > _indent(lines[rendered_at])

    def test_the_original_survives_into_the_pdf_text_layer(self, copy: NoteCopy) -> None:
        drawn = render_note_pdf(_translated_note(), copy)
        assert ORIGINAL_COMPLAINT.encode("ascii") in drawn or ORIGINAL_COMPLAINT in drawn.decode(
            "latin-1", errors="ignore"
        )

    def test_a_translation_with_no_original_is_unconstructible(self) -> None:
        with pytest.raises(ValueError, match="original"):
            TranslatedText("   ", source_locale=SOURCE_LOCALE, translator=TRANSLATOR)

    def test_a_translation_from_turkish_into_turkish_is_refused(self) -> None:
        """Labelling a Turkish answer `translated` is the same defect pointing
        the other way: it takes the patient's own words and marks them as a
        machine's."""
        with pytest.raises(ValueError, match="tr"):
            TranslatedText("x", source_locale=DEFAULT_LOCALE, translator=TRANSLATOR)

    def test_a_source_locale_that_is_not_a_code_is_refused_and_never_echoed(self) -> None:
        """Invariant 6. A sentence in the locale field is a sentence a patient
        may have typed, so the refusal names the shape, never the value."""
        spoken = "Ben bu dili konuşuyorum ve numaram 05001112233"
        with pytest.raises(ValueError) as excinfo:
            TranslatedText("x", source_locale=spoken, translator=TRANSLATOR)
        assert spoken not in str(excinfo.value)
        assert "05001112233" not in str(excinfo.value)

    def test_a_refusal_never_echoes_the_patients_original(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            TranslatedText(ORIGINAL_COMPLAINT, source_locale="!!", translator=TRANSLATOR)
        assert ORIGINAL_COMPLAINT not in str(excinfo.value)


# --------------------------------------------------------------------------------------
# 3. the translator is identified the way a model is
# --------------------------------------------------------------------------------------


class TestTheTranslatorIsIdentifiedTheWayAModelIs:
    def test_the_identity_carries_name_pinned_id_and_sha256(self) -> None:
        assert TRANSLATOR.name == "sentetik-ceviri"
        assert TRANSLATOR.pinned_id == "sentetik/ceviri-modeli@rev0"
        assert TRANSLATOR.sha256 == "c" * 64

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("name", "  "),
            ("model_id", ""),
            ("revision", " "),
        ],
    )
    def test_an_unnamed_translator_is_unconstructible(self, field: str, value: str) -> None:
        kwargs = {
            "name": "sentetik-ceviri",
            "model_id": "sentetik/ceviri-modeli",
            "revision": "rev0",
            "sha256": "c" * 64,
            field: value,
        }
        with pytest.raises(TranslatorUnidentified):
            TranslatorIdentity(**kwargs)  # type: ignore[arg-type]

    @pytest.mark.parametrize("sha", ["", "abc", "C" * 64, "z" * 64, "c" * 63])
    def test_a_sha256_that_is_not_one_is_refused(self, sha: str) -> None:
        """Shape only — no hash is invented here. A value that cannot be a
        sha256 cannot be recorded as one."""
        with pytest.raises(TranslatorUnidentified):
            TranslatorIdentity(
                name="sentetik-ceviri",
                model_id="sentetik/ceviri-modeli",
                revision="rev0",
                sha256=sha,
            )

    def test_a_model_id_that_already_carries_a_revision_is_refused(self) -> None:
        with pytest.raises(TranslatorUnidentified, match="@"):
            TranslatorIdentity(
                name="sentetik-ceviri",
                model_id="sentetik/ceviri-modeli@rev9",
                revision="rev0",
                sha256="c" * 64,
            )

    def test_the_registry_is_empty_and_the_lookup_raises(self) -> None:
        """Invariant 19 governs which translators may exist; none is chosen,
        so the lookup is the refusal. Build the mechanism, wire the gate, make
        it fail closed, leave the content empty."""
        with pytest.raises(TranslatorUnidentified) as excinfo:
            translator("any-translator")
        assert "19" in str(excinfo.value) or "invariant" in str(excinfo.value).lower()

    def test_a_translated_fact_with_no_translator_cannot_be_built(self) -> None:
        """The acceptance's "raises rather than rendering unattributed", at the
        earliest possible point: the value does not exist."""
        with pytest.raises(TranslatorUnidentified):
            Sourced(
                ChiefComplaint(text=RENDERED_COMPLAINT),
                attribution=Attribution.TRANSLATED,
                span=SourceSpan.utterance(work_id="work-1", char_start=0, char_end=1),
            )

    def test_a_translation_offered_without_the_translated_attribution_is_refused(self) -> None:
        """The other direction, and it is the defect this issue exists for: a
        translated line labelled `hasta beyanı`."""
        with pytest.raises(ValueError, match="translated"):
            Sourced(
                ChiefComplaint(text=RENDERED_COMPLAINT),
                attribution=Attribution.PATIENT_SELF,
                span=SourceSpan.utterance(work_id="work-1", char_start=0, char_end=1),
                translation=_translated(ORIGINAL_COMPLAINT),
            )

    def test_the_translator_is_recorded_where_the_provenance_is_read(self, copy: NoteCopy) -> None:
        """A note can be read against the translator that produced it: the
        provenance block resolves the handle to the span *and* to the
        identity, in full — an auditor needs the exact bytes, not a prefix."""
        soap = render_soap(_translated_note(), copy)
        provenance = soap.split(copy.value("previsit_note.heading.provenance"))[1]
        assert TRANSLATOR.name in provenance
        assert TRANSLATOR.pinned_id in provenance
        assert TRANSLATOR.sha256 in provenance
        assert SOURCE_LOCALE in provenance

    def test_a_fact_built_around_the_type_still_raises_at_render(self, copy: NoteCopy) -> None:
        """`NoteFact` is a plain dataclass, so a caller can assemble one
        directly. A renderer that met a translated fact with no identity would
        print an unattributed machine sentence, so it raises instead."""
        composed = _translated_note()
        (fact,) = facts_by_section(composed, "chief_complaint")
        stripped = NoteFact(
            ref=fact.ref,
            section=fact.section,
            attribution=fact.attribution,
            subject=fact.subject,
            lines=fact.lines,
            span=fact.span,
            translation=None,
        )
        broken = ComposedNote(
            note=composed.note,
            facts=(stripped, *composed.facts[1:]),
            gaps=composed.gaps,
        )
        with pytest.raises(TranslatorUnidentified):
            render_soap(broken, copy)


# --------------------------------------------------------------------------------------
# the exchange face has nowhere to put the original, so it refuses
# --------------------------------------------------------------------------------------


class TestTheExchangeFaceRefusesRatherThanExportingTheMachineVersion:
    def test_fhir_refuses_a_note_that_holds_a_translated_line(self) -> None:
        with pytest.raises(TranslatedOriginalUnreachable):
            render_fhir_document(_translated_note(), patient_id="patient-0299")

    def test_fhir_still_renders_an_untranslated_note(self) -> None:
        bundle = render_fhir_document(_untranslated_note(), patient_id="patient-0299")
        assert bundle is not None

    def test_the_refusal_names_no_patient_material(self) -> None:
        with pytest.raises(TranslatedOriginalUnreachable) as excinfo:
            render_fhir_document(_translated_note(), patient_id="patient-0299")
        message = str(excinfo.value)
        assert ORIGINAL_COMPLAINT not in message
        assert RENDERED_COMPLAINT not in message


# --------------------------------------------------------------------------------------
# 4. the patient summary never shows the machine version
# --------------------------------------------------------------------------------------


class TestTheSummaryNeverShowsTheMachineVersion:
    def test_the_summary_quotes_the_original_and_not_the_rendering(
        self, patient_copy: PatientSummaryCopy
    ) -> None:
        """Showing a patient a machine version of their own words is the
        defect; showing them their own words is the fix. `quoted` is never
        measured and never rewritten, so the original travels intact."""
        built = build_patient_summary(_translated_note(), patient_copy)
        rendered = " ".join(line.rendered for line in built.lines)
        assert ORIGINAL_COMPLAINT in rendered
        assert ORIGINAL_CONDITION in rendered
        assert RENDERED_COMPLAINT not in rendered
        assert RENDERED_CONDITION not in rendered

    def test_the_machine_version_is_absent_from_the_summary_value_too(
        self, patient_copy: PatientSummaryCopy
    ) -> None:
        built = build_patient_summary(_translated_note(), patient_copy)
        joined = " ".join(line for card in built.summary.cards for line in card.lines)
        assert RENDERED_COMPLAINT not in joined
        assert ORIGINAL_COMPLAINT in joined

    def test_every_translated_line_still_carries_a_marker(
        self, patient_copy: PatientSummaryCopy
    ) -> None:
        built = build_patient_summary(_translated_note(), patient_copy)
        marker = patient_copy.attribution(Attribution.TRANSLATED)
        translated = [line for line in built.lines if line.attribution is Attribution.TRANSLATED]
        assert translated
        for line in translated:
            assert marker in line.authored
            assert SOURCE_LOCALE in line.authored

    def test_the_summary_refuses_a_translated_line_with_no_way_back(
        self, patient_copy: PatientSummaryCopy
    ) -> None:
        """ "…worse than showing nothing." A fact assembled without its
        original is refused for the whole summary rather than rendered as the
        patient's own sentence."""
        composed = _translated_note()
        (fact,) = facts_by_section(composed, "chief_complaint")
        stripped = NoteFact(
            ref=fact.ref,
            section=fact.section,
            attribution=fact.attribution,
            subject=fact.subject,
            lines=fact.lines,
            span=fact.span,
            translation=None,
        )
        broken = ComposedNote(
            note=composed.note,
            facts=(stripped, *composed.facts[1:]),
            gaps=composed.gaps,
        )
        with pytest.raises(SummaryRefused) as excinfo:
            build_patient_summary(broken, patient_copy)
        assert ORIGINAL_COMPLAINT not in str(excinfo.value)
        assert RENDERED_COMPLAINT not in str(excinfo.value)

    def test_a_relatives_question_is_still_refused(self, patient_copy: PatientSummaryCopy) -> None:
        """The one entry point INT-085 owns has not been widened: a question
        that is not the patient's own is still refused, translated or not."""
        with pytest.raises(AttributionRefused):
            build_patient_summary(
                _translated_note(),
                patient_copy,
                questions_for_doctor=(
                    Sourced(
                        "Sentetik soru",
                        attribution=Attribution.RELATIVE,
                        subject=FactSubject.MOTHER,
                        span=SourceSpan.utterance(work_id="work-9", char_start=0, char_end=4),
                    ),
                ),
            )


# --------------------------------------------------------------------------------------
# the axes that cannot be stacked, and the ones this issue does not touch
# --------------------------------------------------------------------------------------


class TestTheAxesStayApart:
    def test_a_relatives_words_cannot_also_be_marked_translated(self) -> None:
        """Attribution is one axis and a relative's translated statement is
        two. Rather than dropping either half — the relative, or the fact that
        a machine wrote the sentence — the value is refused. Widening this is a
        separate decision with a clinical owner, not an engineering default."""
        with pytest.raises(ValueError):
            Sourced(
                PmhItem(condition=RENDERED_CONDITION, status="unconfirmed", source="patient"),
                attribution=Attribution.TRANSLATED,
                subject=FactSubject.MOTHER,
                span=SourceSpan.utterance(work_id="work-3", char_start=0, char_end=1),
                translation=_translated(ORIGINAL_CONDITION),
            )

    def test_an_imported_record_cannot_be_marked_translated(self) -> None:
        """`imported_objective` admits a record and nothing else. A translated
        document is a document-extraction question, not a note-attribution
        one."""
        assert Attribution.TRANSLATED not in SECTION_ATTRIBUTIONS["imported_objective"]
        with pytest.raises(AttributionRefused):
            compose(
                meta=_meta(),
                triage=RulesTriageResult(level=TriageLevel.GREEN, rules=()),
                screening=_screening(),
                imported_objective=(
                    Sourced(
                        ImportedObjectiveItem(type="lab", summary=RENDERED_CONDITION),
                        attribution=Attribution.TRANSLATED,
                        span=SourceSpan.document(document_ref="doc-0299"),
                        translation=_translated(ORIGINAL_CONDITION),
                    ),
                ),
            )

    def test_no_triage_level_can_be_reached_from_here(self) -> None:
        """Invariant 1. The translation module names no level and no engine:
        a translated answer must not become a route by which a reading of it
        reaches the rules engine."""
        source = (
            REPO
            / "services"
            / "voice-runtime"
            / "src"
            / "intake_voice_runtime"
            / "note"
            / "translation.py"
        ).read_text(encoding="utf-8")
        for token in ("YELLOW", "RED", "TriageLevel", "candidate_flags", "rules_engine"):
            assert token not in source

    def test_the_translated_marker_never_reaches_a_measurement_unguarded(
        self, copy: NoteCopy
    ) -> None:
        """Invariant 22's corner: a translated line is text, and the number +
        unit atom is untouched by it. The composed note holds no measurement
        here, so the assertion is that the renderer added no numeral of its
        own to a translated line."""
        soap = render_soap(_translated_note(), copy)
        original_line = _line_containing(soap, ORIGINAL_COMPLAINT)
        assert not any(character.isdigit() for character in original_line)


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _line_containing(text: str, needle: str) -> str:
    matches = [line for line in text.splitlines() if needle in line]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one line carrying {needle!r}, got {len(matches)}")
    return matches[0]


def _index_of(lines: Sequence[str], needle: str) -> int:
    matches = [index for index, line in enumerate(lines) if needle in line]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one line carrying {needle!r}, got {len(matches)}")
    return matches[0]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))
