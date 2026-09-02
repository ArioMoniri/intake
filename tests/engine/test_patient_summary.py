"""INT-085 — the patient summary and its reading-level check.

The acceptance has two clauses and this module is organised around them.

1. **"plain-language summary excludes wellbeing signals"** —
   :class:`TestWellbeingSignalsCannotReachTheSummary`. The exclusion is not a
   filter at the end: every ``PreVisitNote`` field is classified once, in
   :data:`SUMMARY_SECTIONS` or :data:`EXCLUDED_SECTIONS`, and a test asserts
   the two partition ``PreVisitNote.model_fields`` — so a field added to the
   note tomorrow cannot *default* into a patient-facing card.
2. **"readability metric gate"** — :class:`TestTheReadingLevelCheck` for what
   the metric measures, and :class:`TestTheGateIsWiredAtBothEnds` for where it
   refuses. The metric is deliberately a proxy and says so: it emits no score
   and no level, because CEFR B1 describes a *reader* and no committed Turkish
   corpus in this repo calibrates a threshold on a *text*.

Plus the two properties INT-084 established that a friendlier surface is the
obvious place to lose — :class:`TestAttributionSurvivesPatientProse` (a
relative's condition and a carried fact's date) — and the ``wellbeing``
threat-model row's *"[Dd] a sensitive inference reaching an unconsented
surface"*, which is clause 1 read as a security property rather than a
product one.

**No clinical content is authored here.** Every complaint, condition, drug,
relative and Turkish string in this module and in
``tests/fixtures/legal/strings.summary.synthetic.yaml`` is synthetic (files/04
§7); the authored pack is INT-043 (`awaiting-human`, HB-C1) and none of it is
needed, because both clauses are mechanisms.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
from decimal import Decimal
from pathlib import Path

import pytest
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
    PatientSummary,
    PmhItem,
    PreVisitNote,
    RosItem,
    ScreeningBlock,
    ScreeningProvenance,
    SelfReportedMeasure,
)
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_platform.legal import LegalStringsCatalog, LegalStringsMissingError
from intake_voice_runtime.note import (
    Attribution,
    AttributionRefused,
    ComposedNote,
    FactSubject,
    Sourced,
    SourceSpan,
    compose,
)
from intake_voice_runtime.summary import (
    EXCLUDED_SECTIONS,
    EXCLUSION_REASONS,
    SUMMARY_CARD_SECTIONS,
    SUMMARY_COPY_KEYS,
    SUMMARY_SECTIONS,
    BringItem,
    ComposedSummary,
    NotPatientReadableError,
    PatientSummaryCopy,
    ReadabilityIssue,
    SummaryCardId,
    SummaryRefused,
    build_patient_summary,
    measure_turkish,
    read_check,
    summary_copy_from_legal_strings,
    syllables,
)

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC_STRINGS = REPO / "tests" / "fixtures" / "legal" / "strings.summary.synthetic.yaml"
GENERATED_AT = datetime.datetime(2026, 9, 2, 9, 30, tzinfo=datetime.UTC)
CARRIED_ON = datetime.date(2026, 5, 12)

#: Synthetic patient material (files/04 §7). Distinctive on purpose: several
#: tests assert a token appears on exactly one line, or nowhere at all.
COMPLAINT = "Sentetik yakınma A"
GOAL = "Sentetik beklenti"
NARRATIVE = "Sentetik anlatım B"
CONDITION_SELF = "Sentetik durum A"
CONDITION_RECORD = "Sentetik durum B"
CONDITION_RELATIVE = "Sentetik kalıtsal durum"
DRUG_CARRIED = "Sentetikol"
DRUG_STOPPED = "Durdurulan sentetik ilaç"
ALLERGEN = "Sentetik alerjen"
IMPORTED = "Sentetik dış bulgu"
QUESTION = "Sentetik sorum ne olacak"

#: Synthetic wellbeing material. Nothing that carries these tokens may reach a
#: patient-facing card — that is acceptance clause 1, stated as a string.
WELLBEING_QUALIFIER = "SENTETIK-TARAMA-NITELEYICI"
SPEECH_CAVEAT = "SENTETIK-KONUSMA-KAVEATI"
RULE_EVIDENCE = "SENTETIK-KURAL-KANITI"
CANDIDATE_TEXT = "SENTETIK-ADAY-BULGU"


# --------------------------------------------------------------------------------------
# fixtures — every value synthetic (files/04 §7)
# --------------------------------------------------------------------------------------


@pytest.fixture
def copy() -> PatientSummaryCopy:
    catalog = LegalStringsCatalog(SYNTHETIC_STRINGS)
    return summary_copy_from_legal_strings(catalog.entry(required=SUMMARY_COPY_KEYS))


def _meta() -> NoteMeta:
    return NoteMeta(
        visit_id="visit-0001",
        protocol_hash="b" * 64,
        mode="detailed",
        generated_at=GENERATED_AT,
        model="synthetic-summary-model@rev0",
        prompt_version="summary-v0",
    )


def _screening(*, scored: bool) -> ScreeningBlock:
    """The wellbeing block, with and without an attested self-report."""
    provenance = ScreeningProvenance(
        administration_mode="typed",
        proxy_reported=False,
        third_party_present=scored,
        qualifier_tr=WELLBEING_QUALIFIER if scored else "",
    )
    if not scored:
        return ScreeningBlock(provenance=provenance)
    return ScreeningBlock(phq2=4, gad2=3, phq9=14, gad7=11, provenance=provenance)


def _konusma() -> KonusmaOzellikleri:
    return KonusmaOzellikleri(
        speech_rate_syll_s=4.1,
        pause_ratio=0.22,
        f0_mean_hz=142.0,
        f0_sd_hz=18.0,
        response_latency_ms_mean=610.0,
        reference_ranges={"speech_rate_syll_s": "synthetic"},
        recording_conditions_caveat_tr=SPEECH_CAVEAT,
    )


def _utterance(work_id: str, start: int, end: int) -> SourceSpan:
    return SourceSpan.utterance(work_id=work_id, char_start=start, char_end=end)


def _self[T](value: T, *, work_id: str = "work-1") -> Sourced[T]:
    return Sourced(value, attribution=Attribution.PATIENT_SELF, span=_utterance(work_id, 0, 8))


def _note(
    *,
    level: TriageLevel = TriageLevel.GREEN,
    scored_wellbeing: bool = True,
    with_konusma: bool = True,
) -> ComposedNote:
    triage = (
        RulesTriageResult(
            level=level,
            rules=(RuleFire(id="rf.synthetic", evidence=RULE_EVIDENCE),),
            register=RedRegister.CALM,
            location=RedLocation.REMOTE,
        )
        if level is TriageLevel.RED
        else RulesTriageResult(
            level=level,
            rules=(RuleFire(id="rf.synthetic", evidence=RULE_EVIDENCE),)
            if level is TriageLevel.YELLOW
            else (),
        )
    )
    return compose(
        meta=_meta(),
        triage=triage,
        screening=_screening(scored=scored_wellbeing),
        konusma_ozellikleri=_konusma() if with_konusma else None,
        candidates=LlmCandidateTriage(
            candidate_flags=(CandidateFlag(text=CANDIDATE_TEXT, evidence=RULE_EVIDENCE),)
        ),
        chief_complaint=_self(ChiefComplaint(text=COMPLAINT, patient_goals=(GOAL,))),
        hpi=_self(Hpi(narrative=NARRATIVE, oldcarts=Oldcarts(onset="iki gün"))),
        ros_pertinent=[_self(RosItem(system="sentetik", finding="sentetik", present=False))],
        pmh=[
            _self(PmhItem(condition=CONDITION_SELF, status="unconfirmed", source="patient")),
            Sourced(
                PmhItem(condition=CONDITION_RECORD, status="confirmed", source="record"),
                attribution=Attribution.RECORD,
                span=SourceSpan.document(document_ref="doc-0001", page=2),
            ),
        ],
        medications=[
            Sourced(
                MedicationItem(
                    name=DRUG_CARRIED,
                    dose="günde bir kez bir tablet",
                    reconciliation="matches",
                ),
                attribution=Attribution.CARRIED,
                span=SourceSpan.earlier_visit(visit_ref="visit-0000", asserted_at=CARRIED_ON),
            ),
            Sourced(
                MedicationItem(name=DRUG_STOPPED, reconciliation="stopped"),
                attribution=Attribution.CARRIED,
                span=SourceSpan.earlier_visit(visit_ref="visit-0000", asserted_at=CARRIED_ON),
            ),
        ],
        allergies=[_self(AllergyItem(substance=ALLERGEN, reaction="sentetik tepki"))],
        family=[
            Sourced(
                CONDITION_RELATIVE,
                attribution=Attribution.RELATIVE,
                subject=FactSubject.MOTHER,
                span=_utterance("work-4", 0, 12),
            )
        ],
        social=_self(FamilySocial(occupation="sentetik meslek")),
        measurements=[
            _self(SelfReportedMeasure(code="height", magnitude=Decimal("1234"), unit="cm"))
        ],
        imported_objective=[
            Sourced(
                ImportedObjectiveItem(type="lab", summary=IMPORTED, date="2026-05-01"),
                attribution=Attribution.RECORD,
                span=SourceSpan.document(document_ref="doc-0002", page=1),
            )
        ],
        considerations=[Consideration(pattern="sentetik örüntü", why=RULE_EVIDENCE)],
        suggested_focus_questions=["SENTETIK-HEKIM-SORUSU"],
        patient_confirmed_sections=["medications"],
    )


@pytest.fixture
def composed() -> ComposedNote:
    return _note()


@pytest.fixture
def summary(composed: ComposedNote, copy: PatientSummaryCopy) -> ComposedSummary:
    return build_patient_summary(
        composed,
        copy,
        questions_for_doctor=[_self(QUESTION, work_id="work-9")],
    )


def _all_text(summary: PatientSummary) -> str:
    """Every string the value carries, joined. Deliberately not
    ``model_dump_json``: a serializer that escapes non-ASCII would make a
    Turkish token trivially absent and the leak tests vacuous."""
    parts = [summary.triage_message_tr, *summary.questions_for_doctor, *summary.bring_list]
    for card in summary.cards:
        parts.append(card.title_tr)
        parts.extend(card.lines)
    return " | ".join(parts)


# --------------------------------------------------------------------------------------
# 1. the reading-level check — what it measures
# --------------------------------------------------------------------------------------


class TestTheReadingLevelCheck:
    """The metric, stated so a reviewer can disagree with it in review rather
    than discover it in production."""

    def test_syllables_are_exact_for_turkish_because_every_vowel_is_one(self) -> None:
        """The one measure Turkish gives away for free: syllable nuclei are the
        eight vowels and nothing else, so this is a count, not an estimate."""
        assert syllables("anamnez") == 3
        assert syllables("hastalığınız") == 5
        assert syllables("göğüs") == 2
        assert syllables("â") == 1
        assert syllables("") == 0

    def test_the_syllable_measure_is_reported_and_never_gated(self) -> None:
        """Turkish is agglutinative: word length is morpheme count, not lexical
        difficulty. `hastalığınız` is five syllables and transparent to every
        Turkish speaker; `anamnez` is three and is jargon. A Flesch-shaped
        formula inherits its syllable term from English and would rank these
        the wrong way round, so the count is measured, reported and NOT a
        finding — the vocabulary arm is PolicyGuard's lexicon instead."""
        long_word = read_check("Kayıtlarınızdaki belgeleri getirin.")
        assert long_word.passes
        assert long_word.measures[0].syllables > long_word.measures[0].words
        assert read_check("Anamnez alalım.").findings, "jargon must still be a finding"

    def test_syllables_per_word_is_reported_on_every_measure(self) -> None:
        """The ungated measure still has to be *emitted*, or "we measured it
        and chose not to gate it" is a claim with nothing behind it."""
        measure = measure_turkish("Belgelerinizi getirin.")[0]
        assert measure.syllables_per_word == measure.syllables / measure.words
        assert measure_turkish("") == ()

    def test_the_report_carries_no_score_and_no_level(self) -> None:
        """Invariant 20's shape. B1 describes a reader; no corpus in this repo
        calibrates a threshold on a text, so a number here would read as a
        property of the product. The report has measures and findings only."""
        report = read_check("Randevunuz yarın.")
        names = {field.name for field in dataclasses.fields(report)}
        assert names == {"measures", "findings"}
        for banned in ("score", "level", "grade", "index", "ease"):
            assert not any(banned in name for name in names)

    def test_one_subordinate_clause_passes_and_two_do_not(self) -> None:
        """The arm PolicyGuard does not have. Turkish is verb-final, so every
        embedded clause has to be held until the matrix verb arrives; stacking
        them is where a Turkish sentence stops being B1, and it is invisible to
        a word count."""
        assert read_check("Randevunuza gelirken listeyi yanınıza alalım.").passes
        stacked = read_check("Aldığınız belgeleri göstermek için hazırlayarak getirin.")
        assert not stacked.passes
        assert {finding.issue for finding in stacked.findings} == {
            ReadabilityIssue.TOO_MANY_SUBORDINATE_CLAUSES
        }

    def test_the_subordination_arm_demands_a_stem_not_a_final_syllable(self) -> None:
        """INT-248's lesson, applied before it can bite: a final syllable is not
        a morpheme. `erken` is not a converb and `tarak` is not a gerund."""
        for near_miss in ("Erken gelin.", "Bu bir tarak.", "İnce bir çizgi."):
            assert measure_turkish(near_miss)[0].subordinators == ()

    def test_every_arm_that_fires_names_itself(self) -> None:
        """A finding a reviewer cannot trace to a morpheme is a finding they
        will learn to ignore."""
        measure = measure_turkish("Gelince aldığınız kutuları getirin.")[0]
        assert set(measure.subordinators) == {"converb_ince", "factive_participle"}

    def test_the_check_runs_policyguard_rather_than_a_second_lexicon(self) -> None:
        """Invariant 2 names one guard. Growing a second clinical lexicon here
        would be a clinical review dressed as an engineering change."""
        report = read_check("Bu bir sentetik durum.")
        assert report.findings
        assert any(finding.issue.value == "diagnosis" for finding in report.findings)


# --------------------------------------------------------------------------------------
# 2. the gate — where the metric refuses
# --------------------------------------------------------------------------------------


class TestTheGateIsWiredAtBothEnds:
    def test_the_synthetic_catalogue_binds(self, copy: PatientSummaryCopy) -> None:
        """A fixture that could not pass the gate would not prove it is wired."""
        assert copy.version == "synthetic-int085"
        assert set(copy.values) == set(SUMMARY_COPY_KEYS)

    def test_a_catalogue_value_above_the_bound_is_refused_at_load(self) -> None:
        """Gate one: the copy cannot bind. Fails closed on the whole catalogue,
        never on the one string — a summary with a hole where a card title
        belongs is not a shorter summary, it is a different one."""
        catalog = LegalStringsCatalog(SYNTHETIC_STRINGS)
        strings = catalog.entry(required=SUMMARY_COPY_KEYS)
        broken = dict(strings.values)
        broken["patient_summary.card.story"] = (
            "Bu kart, görüşme sırasında bize anlattığınız her şeyi, "
            "hekiminizin okuyabileceği biçimde, sırayla ve eksiksiz olarak toplar."
        )
        with pytest.raises(NotPatientReadableError):
            summary_copy_from_legal_strings(dataclasses.replace(strings, values=broken))

    def test_an_authored_line_above_the_bound_is_refused_at_build(
        self, composed: ComposedNote, copy: PatientSummaryCopy
    ) -> None:
        """Gate two, independent of gate one: the copy is checked as it is
        bound, and every authored segment is checked again as it is assembled,
        because a marker joined to a date is a string nobody authored."""
        values = dict(copy.values)
        values["patient_summary.attribution.carried"] = (
            "önceki kayıt, yani daha önceki bir görüşmede bize söylediğiniz "
            "ve o gün not aldığımız bilgi"
        )
        with pytest.raises(NotPatientReadableError):
            build_patient_summary(
                composed,
                PatientSummaryCopy(values=values, version=copy.version, text_hash=copy.text_hash),
            )

    def test_the_patients_own_words_are_never_measured_and_never_rewritten(
        self, copy: PatientSummaryCopy
    ) -> None:
        """The patient said it. Rewriting what a patient said is its own defect
        (INT-084 §7), and failing the build on it would make a long sentence at
        the microphone a deploy failure. Only what the product authored is
        measured."""
        long_complaint = (
            "Sabah kalktığımdan beri sürekli devam eden ve akşama doğru daha da "
            "artan bir rahatsızlık hissediyorum, ayrıca dün gece hiç uyuyamadım."
        )
        composed = compose(
            meta=_meta(),
            triage=RulesTriageResult(level=TriageLevel.GREEN),
            screening=_screening(scored=False),
            chief_complaint=_self(ChiefComplaint(text=long_complaint)),
        )
        built = build_patient_summary(composed, copy)
        assert any(long_complaint == line.quoted for line in built.lines)
        assert not read_check(long_complaint).passes, "the control must really be over"

    def test_the_quoted_exclusion_is_not_vacuous(self, summary: ComposedSummary) -> None:
        """An exclusion that never excludes anything proves nothing."""
        assert any(line.quoted for line in summary.lines)
        assert all(line.authored for line in summary.lines)

    def test_a_catalogue_bound_without_a_required_key_is_refused(self) -> None:
        """The loader's `required` set and this module's key set have to be the
        same set. A caller who binds with a shorter one gets a raise rather
        than a card whose title is a KeyError at render time."""
        catalog = LegalStringsCatalog(SYNTHETIC_STRINGS)
        strings = catalog.entry(required=SUMMARY_COPY_KEYS)
        short = {
            key: value
            for key, value in strings.values.items()
            if key != "patient_summary.card.story"
        }
        with pytest.raises(KeyError):
            summary_copy_from_legal_strings(dataclasses.replace(strings, values=short))

    def test_the_production_catalogue_does_not_exist_and_the_summary_fails_closed(
        self,
    ) -> None:
        """invariant 18 + HUMAN_BLOCKERS rule 2: the mechanism ships, the gate
        fails closed, the content stays empty until a human supplies it."""
        production = REPO / "docs" / "legal" / "strings.yaml"
        assert not production.exists(), "strings.yaml landed; wire it and delete this test"
        with pytest.raises(LegalStringsMissingError):
            LegalStringsCatalog(production).entry(required=SUMMARY_COPY_KEYS)


# --------------------------------------------------------------------------------------
# 3. acceptance clause 1 — wellbeing signals cannot reach the summary
# --------------------------------------------------------------------------------------


class TestWellbeingSignalsCannotReachTheSummary:
    def test_every_note_field_is_classified_exactly_once(self) -> None:
        """The exclusion is a partition, not a filter. A field added to
        `PreVisitNote` tomorrow fails this test until somebody decides, in
        review, whether a patient may read it."""
        assert set(SUMMARY_SECTIONS) & set(EXCLUDED_SECTIONS) == set()
        assert set(SUMMARY_SECTIONS) | set(EXCLUDED_SECTIONS) == set(PreVisitNote.model_fields)

    def test_every_exclusion_carries_its_reason(self) -> None:
        assert set(EXCLUSION_REASONS) == set(EXCLUDED_SECTIONS)
        assert all(len(reason) > 40 for reason in EXCLUSION_REASONS.values())

    def test_screening_and_speech_measures_are_excluded_by_name(self) -> None:
        """files/02 §5.6: wellbeing results live on their own consent-gated
        surface, 'never scores and never labels'. files/03 §4.7: the observer
        lanes never reach a patient-facing surface at all."""
        assert "screening" in EXCLUDED_SECTIONS
        assert "konusma_ozellikleri" in EXCLUDED_SECTIONS

    def test_no_wellbeing_token_appears_anywhere_in_the_summary(
        self, summary: ComposedSummary
    ) -> None:
        """The `wellbeing` threat-model row's [Dd] — a sensitive inference
        reaching an unconsented surface — as a string search over the whole
        serialised value, not over the fields we remembered to check."""
        text = _all_text(summary.summary)
        for token in (WELLBEING_QUALIFIER, SPEECH_CAVEAT, RULE_EVIDENCE, CANDIDATE_TEXT):
            assert token not in text
        for score in ("phq", "gad", "cssrs", "phq2", "phq9"):
            assert score not in text.casefold()

    def test_a_scored_note_and_an_unscored_note_produce_the_same_summary(
        self, copy: PatientSummaryCopy
    ) -> None:
        """The strongest form of clause 1: the wellbeing block is not merely
        omitted, it is not an input. Two notes that differ only in their
        screening scores are indistinguishable from the summary."""
        scored = build_patient_summary(_note(scored_wellbeing=True), copy)
        unscored = build_patient_summary(_note(scored_wellbeing=False, with_konusma=False), copy)
        assert scored.summary == unscored.summary

    def test_no_copy_key_can_name_an_instrument_or_a_lane(self) -> None:
        """There is no key through which a screening result could be worded
        into the summary even if a builder wanted one."""
        joined = " ".join(SUMMARY_COPY_KEYS)
        for token in ("phq", "gad", "cssrs", "who5", "screening", "affect", "acoustic"):
            assert token not in joined

    def test_the_clinicians_focus_questions_are_not_the_patients_questions(
        self, summary: ComposedSummary
    ) -> None:
        """files/02 §5.7 writes `suggested_focus_questions` for the resident.
        A field whose name reads patient-facing and whose reader is not the
        patient is exactly how clinician material gets laundered."""
        assert "suggested_focus_questions" in EXCLUDED_SECTIONS
        assert "SENTETIK-HEKIM-SORUSU" not in _all_text(summary.summary)
        assert summary.summary.questions_for_doctor == (QUESTION,)


# --------------------------------------------------------------------------------------
# 4. attribution — INT-084's two properties, in patient-facing prose
# --------------------------------------------------------------------------------------


class TestAttributionSurvivesPatientProse:
    def test_every_line_carries_a_marker(
        self, summary: ComposedSummary, copy: PatientSummaryCopy
    ) -> None:
        """A marker only on the exceptional lines makes the unmarked ones read
        as endorsed, so the rule is 'every line', with no card-dependent
        branch to get wrong."""
        assert summary.lines
        assert all(line.authored.strip() for line in summary.lines)
        assert all(copy.attribution(line.attribution) in line.authored for line in summary.lines)

    def test_a_relatives_condition_names_the_relative_and_appears_once(
        self, summary: ComposedSummary, copy: PatientSummaryCopy
    ) -> None:
        """INT-282's finding, carried into copy the patient reads. Friendlier
        prose is exactly where 'annemde de vardı' becomes 'sizde var'."""
        carrying = [line for line in summary.lines if CONDITION_RELATIVE in line.quoted]
        assert len(carrying) == 1
        line = carrying[0]
        assert line.card is SummaryCardId.FAMILY
        assert line.attribution is Attribution.RELATIVE
        assert copy.subject(FactSubject.MOTHER) in line.authored
        rendered = [
            text
            for card in summary.summary.cards
            for text in card.lines
            if CONDITION_RELATIVE in text
        ]
        assert len(rendered) == 1
        assert copy.subject(FactSubject.MOTHER) in rendered[0]

    def test_a_relatives_condition_is_never_in_the_patients_own_cards(
        self, summary: ComposedSummary
    ) -> None:
        patient_cards = {SummaryCardId.STORY, SummaryCardId.HISTORY}
        assert not [
            line
            for line in summary.lines
            if line.card in patient_cards and CONDITION_RELATIVE in line.quoted
        ]

    def test_a_relative_attributed_question_is_refused_not_relocated(
        self, composed: ComposedNote, copy: PatientSummaryCopy
    ) -> None:
        """INT-084's rule, held at the one place this issue adds a new entry
        point. Moving it silently would hide the caller's bug in the summary."""
        with pytest.raises(AttributionRefused):
            build_patient_summary(
                composed,
                copy,
                questions_for_doctor=[
                    Sourced(
                        QUESTION,
                        attribution=Attribution.RELATIVE,
                        subject=FactSubject.MOTHER,
                        span=_utterance("work-9", 0, 4),
                    )
                ],
            )

    def test_a_carried_fact_carries_the_date_it_was_first_recorded(
        self, summary: ComposedSummary, copy: PatientSummaryCopy
    ) -> None:
        """Without the date a carried fact reads as a current one — the failure
        INT-247 exists to prevent, and worse on the patient's own screen than
        on the clinician's, because the patient has no second source."""
        carried = [line for line in summary.lines if DRUG_CARRIED in line.quoted]
        assert len(carried) == 1
        assert carried[0].attribution is Attribution.CARRIED
        assert str(CARRIED_ON) in carried[0].authored
        assert copy.attribution(Attribution.CARRIED) in carried[0].authored

    def test_a_stopped_medication_is_not_in_the_patients_medication_card(
        self, summary: ComposedSummary
    ) -> None:
        """A reconciliation state is the clinician's vocabulary and has no
        patient-facing copy key, so a stopped drug could only appear unmarked —
        and an unmarked stopped drug in a list headed 'İlaçlarınız' reads as
        current. It is dropped rather than worded."""
        assert DRUG_STOPPED not in _all_text(summary.summary)
        assert DRUG_CARRIED in _all_text(summary.summary)

    def test_a_section_whose_facts_and_values_disagree_is_refused(
        self, composed: ComposedNote, copy: PatientSummaryCopy
    ) -> None:
        """The pairing is positional because the composer files one fact per
        item. If that ever stops being true the summary must not guess: a line
        paired with the wrong fact carries the wrong person's marker."""
        facts = tuple(fact for fact in composed.facts if fact.section != "pmh")
        with pytest.raises(SummaryRefused):
            build_patient_summary(dataclasses.replace(composed, facts=facts), copy)

    def test_an_empty_narrative_contributes_no_line(self, copy: PatientSummaryCopy) -> None:
        """An absent narrative is absent, not an empty line under a heading —
        the same rule INT-084 applied to an absent `severity_nrs`."""
        built = build_patient_summary(
            compose(
                meta=_meta(),
                triage=RulesTriageResult(level=TriageLevel.GREEN),
                screening=_screening(scored=False),
                chief_complaint=_self(ChiefComplaint(text=COMPLAINT)),
                hpi=_self(Hpi(narrative="", oldcarts=Oldcarts(onset="iki gün"))),
            ),
            copy,
        )
        assert [line.quoted for line in built.lines] == [COMPLAINT]

    def test_there_is_no_copy_key_for_a_rule_or_a_candidate(self) -> None:
        """Invariant 1's summary face: not a filter, an absent vocabulary."""
        joined = " ".join(SUMMARY_COPY_KEYS)
        assert Attribution.RULES_ENGINE.value not in joined
        assert Attribution.LLM_CANDIDATE.value not in joined

    def test_no_line_sits_under_a_card_its_section_is_not_assigned_to(
        self, summary: ComposedSummary
    ) -> None:
        """The card table is the placement, not documentation of it: the
        builder never names a card, it reads one off the fact's section through
        the table's inverse. This walks the result back to the public table, so
        a line under the wrong heading — which is still a line, and which every
        other test here would tolerate — is not reachable."""
        for line in summary.lines:
            assert line.section in SUMMARY_CARD_SECTIONS[line.card]
        # And the fixture reaches every summarised section, so the check above
        # is not passing because most of them were never exercised.
        assert {line.section for line in summary.lines} == set(SUMMARY_SECTIONS)

    def test_the_card_table_admits_a_relative_in_exactly_one_card(self) -> None:
        admitting = [
            card
            for card, sections in SUMMARY_CARD_SECTIONS.items()
            if any("family" in section for section in sections)
        ]
        assert admitting == [SummaryCardId.FAMILY]


# --------------------------------------------------------------------------------------
# 5. triage, bring list and the rest of the value
# --------------------------------------------------------------------------------------


class TestTriageAndTheRestOfTheValue:
    def test_green_and_yellow_render_the_catalogue_message(self, copy: PatientSummaryCopy) -> None:
        for level in (TriageLevel.GREEN, TriageLevel.YELLOW):
            built = build_patient_summary(_note(level=level), copy)
            assert built.summary.triage_message_tr == copy.triage_message(level)

    def test_a_red_note_has_no_summary_and_no_key_to_word_one(
        self, copy: PatientSummaryCopy
    ) -> None:
        """Invariant 21: RED is route × register × location, the script is
        pre-positioned on the device and triggered over the data channel. A
        card set is none of those three axes, and a RED sentence whose register
        is decided by layout is the default the invariant forbids."""
        assert "patient_summary.triage_message.red" not in SUMMARY_COPY_KEYS
        with pytest.raises(SummaryRefused):
            build_patient_summary(_note(level=TriageLevel.RED), copy)

    def test_the_bring_list_is_derived_never_typed(
        self, summary: ComposedSummary, copy: PatientSummaryCopy
    ) -> None:
        """A closed enum with a structural trigger each: a caller cannot spell a
        new instruction into a patient's screen."""
        assert summary.summary.bring_list == (
            copy.bring(BringItem.MEDICATIONS),
            copy.bring(BringItem.DOCUMENTS),
        )
        bare = build_patient_summary(
            compose(
                meta=_meta(),
                triage=RulesTriageResult(level=TriageLevel.GREEN),
                screening=_screening(scored=False),
                chief_complaint=_self(ChiefComplaint(text=COMPLAINT)),
            ),
            copy,
        )
        assert bare.summary.bring_list == ()

    def test_a_measurement_binds_its_number_to_its_unit_and_never_groups(
        self, summary: ComposedSummary
    ) -> None:
        """Invariant 22 on the patient's own screen."""
        measure = [line for line in summary.lines if "cm" in line.quoted]
        assert len(measure) == 1
        assert measure[0].quoted == "1234\u00a0cm"
        assert "1.234" not in _all_text(summary.summary)
        assert "1,234" not in _all_text(summary.summary)

    def test_the_summary_states_no_measurement_and_no_percentage(
        self, summary: ComposedSummary
    ) -> None:
        """Invariant 20 over patient copy: no accuracy figure, and no bare
        percentage that could read as one."""
        text = _all_text(summary.summary)
        for banned in ("duyarlılık", "özgüllük", "doğruluk", "AUROC", "WER", "%"):
            assert banned not in text

    def test_the_build_is_deterministic(
        self, composed: ComposedNote, copy: PatientSummaryCopy
    ) -> None:
        assert build_patient_summary(composed, copy) == build_patient_summary(composed, copy)

    def test_every_authored_segment_comes_from_the_catalogue(
        self, composed: ComposedNote, copy: PatientSummaryCopy
    ) -> None:
        """The module authors no Turkish. Rebuild with every catalogue value
        replaced by a distinctive sentinel and assert nothing else survives into
        an authored segment — punctuation and a date are all the builder adds."""
        sentinels = {key: f"SENTINEL{index:02d}" for index, key in enumerate(SUMMARY_COPY_KEYS)}
        built = build_patient_summary(
            composed,
            PatientSummaryCopy(values=sentinels, version=copy.version, text_hash=copy.text_hash),
        )
        residue = re.sub(r"SENTINEL\d\d", "", " ".join(line.authored for line in built.lines))
        assert not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", residue), residue
        for card in built.summary.cards:
            assert card.title_tr in sentinels.values()
