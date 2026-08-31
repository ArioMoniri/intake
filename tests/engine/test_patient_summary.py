"""INT-085 — the patient summary, its exclusion rule and its readability gate.

Acceptance (verbatim, docs/backlog/issues.yaml):
    "plain-language summary excludes wellbeing signals; readability metric
    gate"

Two clauses, and each is enforced as a mechanism rather than as a habit.

**"excludes wellbeing signals" is a safety exclusion.** INT-116's acceptance
says the wellbeing outputs are *"never in patient summary"*, and files/02 §5.6
says the same thing in product terms — the wellbeing surface shows
*"plain-language check-in results … never scores and never labels"*. Handing a
patient a depression score with no clinician present is the harm, so the rule
is expressed as a POSITIVE allow-list of the note fields that may cross
(:data:`~intake_api.note.summary.PATIENT_VISIBLE_FIELDS`) rather than as a
deny-list of the ones that may not. A deny-list admits the next signal
somebody adds; an allow-list refuses it without anybody remembering to.
:class:`TestANewSignalIsExcludedWithoutEditingTheRule` is the test that proves
it, and :class:`TestNearMissControls` proves the allow-list is not so blunt
that it also drops legitimate patient-facing content.

**"readability metric gate"** — :class:`TestReadabilityGate` and
:class:`TestTheMetricIsNotInvented`. No Turkish readability formula is
committed in this repository and none is named in ``files/``; Flesch-Kincaid
is an English formula and reporting its output as a Turkish B1 level would be
a fabricated measurement, which CLAUDE.md invariant 20 forbids outright. So
what ships is the set of STRUCTURAL checks that can be defended one by one,
and the scored-metric registry ships EMPTY with the gate refusing to claim a
level — the absence recorded against a HUMAN_BLOCKERS row rather than filled
in with a plausible number.

Every value in this module is synthetic (files/04 §7). The Turkish strings the
summary renders are a synthetic catalogue in exactly the sense INT-084's
``SYNTHETIC_STRINGS`` is: patient-facing clinical copy is authored by the
clinical copy owner against ``tr`` resource keys (invariant 5), never here.
"""

from __future__ import annotations

import ast
import logging
from collections.abc import Mapping
from pathlib import Path

import note_fixtures as fx
import pytest
from clinical_schemas.composition import AttributedNote
from clinical_schemas.note import (
    AllergyItem,
    MedicationItem,
    PatientSummary,
    ScreeningBlock,
)
from clinical_schemas.provenance import ATTRIBUTABLE_SECTIONS, Attributed, NoteFact
from clinical_schemas.triage import CandidateFlag, TriageLevel
from intake_api.note import (
    B1_MAX_WORDS_PER_SENTENCE,
    CLINICIAN_ONLY_SECTIONS,
    PATIENT_VISIBLE_FIELDS,
    PATIENT_VISIBLE_SECTIONS,
    ComposedSummary,
    NoteCompositionError,
    PatientSummaryReadabilityError,
    ReadabilityCheck,
    ReadabilityMetric,
    SummaryStringsMissingError,
    SummaryText,
    TextOrigin,
    build_patient_summary,
    check_readability,
    compose_note,
    normalise_field_ref,
    render_patient_summary,
    section_partition_error,
    summary_string_keys,
)
from intake_api.note import summary as summary_module
from intake_api.note.readability import SCORED_METRICS
from intake_platform.legal.claims import scan_text
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker import policy_guard as pg
from intake_voice_runtime.talker.policy_guard import (
    FormOfAddress,
    PolicyGuard,
    ViolationClass,
)

REPO = Path(__file__).resolve().parents[2]
NOTE_PACKAGE = REPO / "services" / "api" / "src" / "intake_api" / "note"

#: A SYNTHETIC ``tr`` catalogue. The real copy is patient-facing clinical text
#: authored against the keys below by the clinical copy owner (invariant 5,
#: CLAUDE.md clinical content rules); it is deliberately not written here.
#: Every string is ``siz``, one clause, well inside the sentence bound, so the
#: catalogue itself never contributes a readability finding.
SYNTHETIC_STRINGS: Mapping[str, str] = {
    "patient_summary.card.chief_complaint.title": "Sentetik baslik bir",
    "patient_summary.card.hpi.title": "Sentetik baslik iki",
    "patient_summary.card.medications.title": "Sentetik baslik uc",
    "patient_summary.card.allergies.title": "Sentetik baslik dort",
    "patient_summary.triage.GREEN": "Sentetik bilgi metnidir.",
    "patient_summary.triage.YELLOW": "Sentetik bilgi metnidir.",
    "patient_summary.triage.RED": "Sentetik metni okuyun.",
}


def _compose(scenario: str) -> AttributedNote:
    meta, triage, sources, candidates = getattr(fx, scenario)()
    return compose_note(meta=meta, triage=triage, sources=sources, candidate_flags=candidates)


def _build(scenario: str = "red_full", **kwargs: object) -> ComposedSummary:
    return build_patient_summary(_compose(scenario), strings=SYNTHETIC_STRINGS, **kwargs)  # type: ignore[arg-type]


def _surfaces(composed: ComposedSummary) -> tuple[str, str]:
    """Every surface this issue emits, as text: the render and the wire form."""
    return (
        render_patient_summary(composed.summary),
        composed.summary.model_dump_json(),
    )


# --------------------------------------------------------------------------
# 1. "excludes wellbeing signals" — the positive allow-list
# --------------------------------------------------------------------------


class TestTheRuleIsAnAllowList:
    def test_the_visible_and_clinician_only_sections_partition_the_note(self) -> None:
        """Every attributable section is classified exactly once. A section
        added to the note tomorrow belongs to neither list, and that is a
        build failure rather than a silent leak."""
        visible = set(PATIENT_VISIBLE_SECTIONS)
        clinician = set(CLINICIAN_ONLY_SECTIONS)
        assert visible & clinician == set()
        assert visible | clinician == set(ATTRIBUTABLE_SECTIONS)

    def test_an_unclassified_section_fails_closed_rather_than_defaulting(self) -> None:
        error = section_partition_error(tuple(ATTRIBUTABLE_SECTIONS) + ("wellbeing_trend",))
        assert error is not None
        assert "wellbeing_trend" in error
        assert section_partition_error(tuple(ATTRIBUTABLE_SECTIONS)) is None

    def test_screening_is_not_a_patient_visible_section(self) -> None:
        assert "screening" not in PATIENT_VISIBLE_SECTIONS
        assert "screening" in CLINICIAN_ONLY_SECTIONS
        assert "konusma_ozellikleri" not in PATIENT_VISIBLE_SECTIONS

    def test_every_allow_listed_field_belongs_to_a_visible_section(self) -> None:
        for ref in PATIENT_VISIBLE_FIELDS:
            head = ref.split(".", 1)[0].split("[", 1)[0]
            assert head in PATIENT_VISIBLE_SECTIONS, ref

    def test_a_summary_carries_only_allow_listed_facts(self) -> None:
        composed = _build()
        admitted = {normalise_field_ref(ref) for ref in composed.admitted_field_refs}
        assert admitted
        assert admitted <= set(PATIENT_VISIBLE_FIELDS)

    def test_the_withheld_refs_name_what_was_kept_back(self) -> None:
        composed = _build()
        assert "screening.phq9" in composed.withheld_field_refs
        assert "screening.gad7" in composed.withheld_field_refs
        assert "konusma_ozellikleri.f0_mean_hz" in composed.withheld_field_refs
        assert "chief_complaint.text" not in composed.withheld_field_refs

    def test_the_clinician_focus_questions_are_not_the_patients_questions(self) -> None:
        """``suggested_focus_questions`` is written FOR the clinician (files/03
        §11); the patient's own questions come from the wrap-up slot
        ``open_questions`` (packages/protocols/base/intake.yaml). Wiring the
        first into the second is the most tempting wrong wiring in this issue."""
        composed = _build()
        for surface in _surfaces(composed):
            assert "sentetik odak sorusu" not in surface
        assert composed.summary.questions_for_doctor == ()

        with_question = _build(
            questions_for_doctor=(
                Attributed(value="sentetik hasta sorusu", spans=(fx.utterance("turn:20", 0, 21),)),
            )
        )
        assert with_question.summary.questions_for_doctor == ("sentetik hasta sorusu",)


class TestWellbeingSignalsAreExcluded:
    def test_no_instrument_score_reaches_any_surface(self) -> None:
        built = _compose("red_full")
        assert built.note.screening.phq9 == 12  # the fixture really does carry one
        composed = build_patient_summary(built, strings=SYNTHETIC_STRINGS)
        rendered = {
            line.lstrip("\u2022 ").strip()
            for line in render_patient_summary(composed.summary).splitlines()
        }
        for score in (
            built.note.screening.phq2,
            built.note.screening.gad2,
            built.note.screening.phq9,
            built.note.screening.gad7,
        ):
            assert str(score) not in rendered
        for surface in _surfaces(composed):
            for field in ("phq2", "gad2", "phq9", "gad7", "cssrs", "screening"):
                assert field not in surface

    def test_no_screening_fact_text_reaches_any_surface(self) -> None:
        composed = _compose("red_full")
        built = build_patient_summary(composed, strings=SYNTHETIC_STRINGS)
        screening_texts = [f.text for f in composed.facts if f.section == "screening"]
        assert screening_texts
        for surface in _surfaces(built):
            for text in screening_texts:
                assert f'"{text}"' not in surface

    def test_the_speech_measures_are_excluded_too(self) -> None:
        """files/04 §5 makes ``konusma_ozellikleri`` a sibling of screening
        precisely so it is not filed under one; it is still a derived signal
        about the patient and it is still not patient-facing."""
        composed = _build()
        for surface in _surfaces(composed):
            assert "konusma" not in surface
            assert "4.25" not in surface
            assert "sentetik kayit kosulu notu" not in surface


class TestANewSignalIsExcludedWithoutEditingTheRule:
    def test_every_screening_field_name_is_outside_the_allow_list(self) -> None:
        """Introspective, so it covers fields that do not exist yet: whatever
        ``ScreeningBlock`` grows, the allow-list does not grow with it."""
        for name in ScreeningBlock.model_fields:
            assert f"screening.{name}" not in PATIENT_VISIBLE_FIELDS

    def test_a_newly_added_wellbeing_fact_is_excluded_end_to_end(self) -> None:
        """The composer emits one fact per note field. A wellbeing field added
        tomorrow arrives here as one more ``screening.*`` fact, and nothing in
        the exclusion rule is edited to keep it out."""
        composed = _compose("red_full")
        newcomer = NoteFact(
            section="screening",
            field_ref="screening.who5",
            text="SENTETIK IYILIK HALI SINYALI",
            spans=(fx.typed("instrument:who5", 0, 2),),
        )
        order = {name: index for index, name in enumerate(ATTRIBUTABLE_SECTIONS)}
        facts = tuple(
            sorted(
                (*composed.facts, newcomer),
                key=lambda fact: order[fact.section],
            )
        )
        grown = AttributedNote(note=composed.note, facts=facts, rules_triage=composed.rules_triage)
        built = build_patient_summary(grown, strings=SYNTHETIC_STRINGS)
        assert "screening.who5" in built.withheld_field_refs
        for surface in _surfaces(built):
            assert "SENTETIK IYILIK HALI SINYALI" not in surface
            assert "who5" not in surface


class TestAListItemIsAdmittedFieldByField:
    def test_the_clinician_shorthand_of_a_medication_never_crosses(self) -> None:
        """The composer's medication fact is written for a clinician: an ATC
        code and a reconciliation status. The summary rebuilds the line from
        the item's own allow-listed fields instead of reusing it."""
        composed = _build()
        assert "medications[].atc" in composed.withheld_field_refs
        assert "medications[].reconciliation" in composed.withheld_field_refs
        assert "allergies[].severity" in composed.withheld_field_refs
        for surface in _surfaces(composed):
            assert "A01AA01" not in surface
            assert "reconciliation" not in surface

    def test_a_new_item_field_is_outside_the_allow_list_by_default(self) -> None:
        for model, admitted in (
            (MedicationItem, {"name", "dose"}),
            (AllergyItem, {"substance", "reaction"}),
        ):
            section = "medications" if model is MedicationItem else "allergies"
            for name in model.model_fields:
                ref = f"{section}[].{name}"
                assert (ref in PATIENT_VISIBLE_FIELDS) is (name in admitted), ref

    def test_the_patient_line_carries_the_medication_the_patient_named(self) -> None:
        render = render_patient_summary(_build().summary)
        assert "sentetik ilac, beş miligram" in render
        assert "sentetik madde, dokuntu" in render


class TestNearMissControls:
    def test_a_shared_prefix_does_not_decide_admission(self) -> None:
        """``hpi.narrative`` and ``hpi.negatives[0]`` share five characters.
        The first is model-composed prose and is withheld; the second is an
        elicited negative in the patient's own words and must survive. A
        prefix match would get exactly one of them wrong."""
        composed = _build()
        assert "hpi.narrative" in composed.withheld_field_refs
        assert "hpi.negatives[]" in {
            normalise_field_ref(ref) for ref in composed.admitted_field_refs
        }
        render = render_patient_summary(composed.summary)
        assert "atesi yok" in render
        assert "ani basladi" not in render

    def test_the_patients_own_mood_words_are_not_a_wellbeing_signal(self) -> None:
        """A near-miss on content rather than on field name: a complaint that
        reads like a screening item is still the patient's own complaint,
        arriving through a patient-facing field, and dropping it would be the
        allow-list over-firing on the one sentence the patient came to say."""
        meta, triage, sources, _ = fx.green_typed()
        sources = sources.model_copy(
            update={
                "chief_complaint": Attributed(
                    value="kendimi yorgun ve mutsuz hissediyorum",
                    spans=(fx.typed("turn:1", 0, 36),),
                )
            }
        )
        built = build_patient_summary(
            compose_note(meta=meta, triage=triage, sources=sources),
            strings=SYNTHETIC_STRINGS,
        )
        assert "kendimi yorgun ve mutsuz hissediyorum" in render_patient_summary(built.summary)


class TestExclusionSurvivesRendering:
    def test_the_render_draws_only_on_the_model_it_was_given(self) -> None:
        composed = _build()
        render = render_patient_summary(composed.summary)
        for card in composed.summary.cards:
            assert card.title_tr in render
            for line in card.lines:
                assert line in render

    def test_the_render_introduces_no_string_of_its_own(self) -> None:
        """There is no second door. Every non-structural line of the render is
        either a catalogue value or a value the allow-list admitted, so the
        exclusion cannot be undone downstream of it — and neither can a
        renderer quietly add copy of its own (invariant 5)."""
        composed = _build()
        permitted = set(SYNTHETIC_STRINGS.values()) | set(composed.admitted_values)
        for line in render_patient_summary(composed.summary).splitlines():
            stripped = line.lstrip("\u2022 ").strip()
            if not stripped:
                continue
            assert stripped in permitted, stripped

    def test_an_empty_summary_renders_empty(self) -> None:
        assert render_patient_summary(PatientSummary()) == ""


# --------------------------------------------------------------------------
# 2. "readability metric gate"
# --------------------------------------------------------------------------


class TestReadabilityGate:
    def test_the_sentence_bound_is_the_runtime_bound(self) -> None:
        """services/api cannot depend on services/voice-runtime, so the B1
        proxy is mirrored rather than imported — and pinned here so the two
        cannot drift into two different answers to the same question."""
        assert B1_MAX_WORDS_PER_SENTENCE == pg.B1_MAX_WORDS_PER_SENTENCE

    def test_a_long_authored_sentence_fails_the_gate(self) -> None:
        long_sentence = " ".join(["kelime"] * (B1_MAX_WORDS_PER_SENTENCE + 1)) + "."
        report = check_readability(
            (
                SummaryText(
                    location="triage_message_tr",
                    text=long_sentence,
                    origin=TextOrigin.AUTHORED,
                    prose=True,
                ),
            )
        )
        assert not report.gate_passes
        assert {f.check for f in report.findings} == {ReadabilityCheck.SENTENCE_LENGTH}

    def test_two_ideas_in_one_sentence_is_a_finding(self) -> None:
        report = check_readability(
            (
                SummaryText(
                    location="triage_message_tr",
                    text="Notunuz hazır ve hekiminize gidecek ama önce kontrol edin.",
                    origin=TextOrigin.AUTHORED,
                    prose=True,
                ),
            )
        )
        assert ReadabilityCheck.ONE_IDEA in {f.check for f in report.findings}

    def test_one_conjunction_joining_two_nouns_is_not_two_ideas(self) -> None:
        report = check_readability(
            (
                SummaryText(
                    location="cards[0].lines[0]",
                    text="Ateş ve öksürük.",
                    origin=TextOrigin.AUTHORED,
                    prose=True,
                ),
            )
        )
        assert report.gate_passes

    def test_the_sen_register_is_a_finding(self) -> None:
        report = check_readability(
            (
                SummaryText(
                    location="triage_message_tr",
                    text="Senin notun hazır.",
                    origin=TextOrigin.AUTHORED,
                    prose=True,
                ),
            )
        )
        assert ReadabilityCheck.REGISTER_SEN in {f.check for f in report.findings}

    def test_the_siz_forms_that_share_a_prefix_are_not_findings(self) -> None:
        report = check_readability(
            (
                SummaryText(
                    location="triage_message_tr",
                    text="Notunuzu gördünüz mü?",
                    origin=TextOrigin.AUTHORED,
                    prose=True,
                ),
            )
        )
        assert report.gate_passes

    def test_jargon_without_a_gloss_is_a_finding_and_with_one_is_not(self) -> None:
        bare = check_readability(
            (
                SummaryText(
                    location="cards[0].lines[0]",
                    text="Dispne notunuzda yazılı.",
                    origin=TextOrigin.AUTHORED,
                ),
            )
        )
        assert ReadabilityCheck.JARGON in {f.check for f in bare.findings}
        glossed = check_readability(
            (
                SummaryText(
                    location="cards[0].lines[0]",
                    text="Dispne (nefes darlığı) notunuzda yazılı.",
                    origin=TextOrigin.AUTHORED,
                ),
            )
        )
        assert glossed.gate_passes

    def test_every_jargon_term_is_jargon_to_policyguard_too(self) -> None:
        """One vocabulary, two enforcement points. The guard at the microphone
        and the gate on the screen must not disagree about what a B1 reader
        carries."""
        guard = PolicyGuard(profile=VoiceProfile.TYPED)
        for term in summary_module.jargon_terms():
            found = guard.inspect_sentence(f"{term} notunuzda yazılı.")
            assert ViolationClass.JARGON in {v.violation_class for v in found}, term

    def test_instructional_prose_takes_the_long_imperative(self) -> None:
        short = check_readability(
            (
                SummaryText(
                    location="triage_message_tr",
                    text="Listenizi hazırlayın.",
                    origin=TextOrigin.AUTHORED,
                    prose=True,
                ),
            )
        )
        assert ReadabilityCheck.INSTRUCTIONAL_FORM in {f.check for f in short.findings}
        long = check_readability(
            (
                SummaryText(
                    location="triage_message_tr",
                    text="Listenizi hazırlayınız.",
                    origin=TextOrigin.AUTHORED,
                    prose=True,
                ),
            )
        )
        assert long.gate_passes

    def test_inside_red_the_rule_inverts(self) -> None:
        """CLAUDE.md: *"Invert inside RED, where the bare imperative plural
        (Tutun · Arayın · Bakmayın) is correct because ambiguity is the
        harm."*"""
        bare = check_readability(
            (
                SummaryText(
                    location="triage_message_tr",
                    text="Hemen arayın.",
                    origin=TextOrigin.AUTHORED,
                    prose=True,
                    red_register=True,
                ),
            )
        )
        assert bare.gate_passes
        doubled = check_readability(
            (
                SummaryText(
                    location="triage_message_tr",
                    text="Hemen arayınız.",
                    origin=TextOrigin.AUTHORED,
                    prose=True,
                    red_register=True,
                ),
            )
        )
        assert ReadabilityCheck.INSTRUCTIONAL_FORM in {f.check for f in doubled.findings}

    def test_a_short_label_is_not_instructional_prose(self) -> None:
        report = check_readability(
            (
                SummaryText(
                    location="cards[0].title_tr",
                    text="Kimliğinizi getirin",
                    origin=TextOrigin.AUTHORED,
                ),
            )
        )
        assert report.gate_passes

    def test_the_gate_refuses_to_build_a_summary_with_failing_authored_copy(self) -> None:
        broken = dict(SYNTHETIC_STRINGS)
        broken["patient_summary.triage.RED"] = "Senin notun hazır."
        with pytest.raises(PatientSummaryReadabilityError):
            build_patient_summary(_compose("red_full"), strings=broken)

    def test_the_patients_own_words_are_reported_and_never_rewritten(self) -> None:
        """A gate that paraphrases the patient's own sentence back at them has
        broken the promise files/02 §5.2 makes with the rail — the patient
        watches their words become structure. A quoted finding is reported so
        the surface and the metrics can see it; it never fails the build and it
        never edits the sentence."""
        meta, triage, sources, _ = fx.green_typed()
        rambling = " ".join(["kelime"] * (B1_MAX_WORDS_PER_SENTENCE + 3))
        sources = sources.model_copy(
            update={
                "chief_complaint": Attributed(value=rambling, spans=(fx.typed("turn:1", 0, 10),))
            }
        )
        built = build_patient_summary(
            compose_note(meta=meta, triage=triage, sources=sources),
            strings=SYNTHETIC_STRINGS,
        )
        quoted = [f for f in built.report.findings if f.origin is TextOrigin.QUOTED]
        assert quoted
        assert built.report.gate_passes
        assert rambling in render_patient_summary(built.summary)


class TestTheMetricIsNotInvented:
    def test_no_scored_readability_metric_is_committed(self) -> None:
        """No Turkish readability formula exists in this repository and none is
        named in ``files/``. The registry is the mechanism, wired and empty
        (HUMAN_BLOCKERS.md HB-C17); a number here would read as authoritative
        to every later reader, which is the one failure CLAUDE.md forbids
        absolutely."""
        assert SCORED_METRICS == ()

    def test_the_report_claims_no_b1_level(self) -> None:
        composed = _build()
        assert composed.report.scores == ()
        assert composed.report.asserts_b1_level is False
        assert composed.report.structural_only is True

    def test_a_metric_row_cannot_be_added_without_its_source(self) -> None:
        with pytest.raises(ValueError):
            ReadabilityMetric(name="", formula_source="docs/evidence/x.md", b1_threshold=1.0)
        with pytest.raises(ValueError):
            ReadabilityMetric(name="sentetik", formula_source="", b1_threshold=1.0)

    def test_no_readability_figure_appears_in_the_summary_surfaces(self) -> None:
        composed = _build()
        for surface in _surfaces(composed):
            assert scan_text(surface, groups=("performance", "satisfaction")) == ()


# --------------------------------------------------------------------------
# 3. the invariants this issue rides on
# --------------------------------------------------------------------------


class TestInvariantsHold:
    def test_the_whole_summary_passes_policyguard(self) -> None:
        """Invariant 2. INT-084 renders Assessment and Plan empty so no
        diagnosis, treatment or prognosis language can appear on a note; the
        patient summary must not reintroduce any of it by paraphrase."""
        guard = PolicyGuard(profile=VoiceProfile.TYPED, form_of_address=FormOfAddress.SIZ)
        composed = _build()
        texts = [card.title_tr for card in composed.summary.cards]
        texts += [line for card in composed.summary.cards for line in card.lines]
        texts.append(composed.summary.triage_message_tr)
        for text in texts:
            if not text:
                continue
            for violation in guard.inspect_sentence(text):
                assert violation.violation_class not in {
                    ViolationClass.DIAGNOSIS,
                    ViolationClass.TREATMENT,
                    ViolationClass.PROGNOSIS,
                }, (text, violation)

    def test_the_triage_message_is_the_rules_level_and_nothing_more(self) -> None:
        """Invariant 1: the summary reads its level from the rules result, and
        an LLM candidate flag cannot move it."""
        meta, triage, sources, candidates = fx.yellow_candidates()
        assert candidates
        with_candidates = build_patient_summary(
            compose_note(meta=meta, triage=triage, sources=sources, candidate_flags=candidates),
            strings=SYNTHETIC_STRINGS,
        )
        without = build_patient_summary(
            compose_note(meta=meta, triage=triage, sources=sources),
            strings=SYNTHETIC_STRINGS,
        )
        assert with_candidates.summary == without.summary
        assert (
            with_candidates.summary.triage_message_tr
            == (SYNTHETIC_STRINGS["patient_summary.triage.YELLOW"])
        )

    def test_a_candidate_flag_never_reaches_the_patient(self) -> None:
        composed = _build("yellow_candidates")
        for surface in _surfaces(composed):
            assert "sentetik aday not" not in surface
            for word in ("RED", "YELLOW", "GREEN"):
                assert word not in surface

    def test_the_summary_renders_only_from_tr_resource_keys(self) -> None:
        """Invariant 5. Nothing in this module carries authored Turkish copy:
        every product string it renders arrives by key, and a missing key is a
        refusal rather than an English fallback or an invented sentence."""
        keys = set(summary_string_keys(_compose("red_full")))
        assert keys <= set(SYNTHETIC_STRINGS)
        for key in sorted(keys):
            partial = {k: v for k, v in SYNTHETIC_STRINGS.items() if k != key}
            with pytest.raises(SummaryStringsMissingError) as excinfo:
                build_patient_summary(_compose("red_full"), strings=partial)
            assert key in str(excinfo.value)

    def test_a_blank_string_is_as_missing_as_an_absent_one(self) -> None:
        blanked = dict(SYNTHETIC_STRINGS)
        blanked["patient_summary.card.hpi.title"] = "   "
        with pytest.raises(SummaryStringsMissingError):
            build_patient_summary(_compose("red_full"), strings=blanked)

    def test_the_summary_module_declares_keys_and_never_copy(self) -> None:
        """The mechanical form of invariant 5: every key this module can
        render is a dotted resource key, and the module holds no mapping from
        one to a Turkish sentence. The copy lives with the clinical copy
        owner; the module holds the keys and the refusal."""
        keys = summary_string_keys(_compose("red_full"))
        assert keys
        assert all(key.startswith("patient_summary.") for key in keys)
        body = (NOTE_PACKAGE / "summary.py").read_text(encoding="utf-8")
        tree = ast.parse(body)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for value in node.values:
                    assert not (
                        isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and value.value.endswith(".")
                    ), ast.unparse(value)

    def test_numbers_cross_the_boundary_ungrouped(self) -> None:
        """Invariant 22: the severity the patient gave is rendered by INT-083's
        one renderer upstream and reaches the card unchanged and ungrouped."""
        render = render_patient_summary(_build().summary)
        assert "10" in render
        assert "1,0" not in render and "1.0" not in render

    def test_building_a_summary_emits_no_log_record(self, caplog: pytest.LogCaptureFixture) -> None:
        """Invariant 6."""
        with caplog.at_level(logging.DEBUG):
            composed = _build()
            render_patient_summary(composed.summary)
        assert caplog.records == []

    def test_the_summary_is_deterministic(self) -> None:
        first = _build()
        second = _build()
        assert first.summary == second.summary
        assert first.withheld_field_refs == second.withheld_field_refs

    def test_a_green_note_still_produces_a_summary(self) -> None:
        composed = _build("green_typed")
        assert composed.summary.cards
        assert (
            composed.summary.triage_message_tr
            == (SYNTHETIC_STRINGS["patient_summary.triage.GREEN"])
        )
        assert TriageLevel.GREEN.value not in render_patient_summary(composed.summary)

    def test_a_candidate_flag_cannot_be_laundered_through_the_summary(self) -> None:
        meta, triage, sources, _ = fx.yellow_candidates()
        with pytest.raises(NoteCompositionError):
            compose_note(
                meta=meta,
                triage=triage,
                sources=sources,
                candidate_flags=(CandidateFlag(text="RED", evidence="turn:1"),),
            )
