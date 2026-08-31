"""INT-084 — note composer, renderers, provenance and the fixed disclaimer.

Acceptance (verbatim, docs/backlog/issues.yaml):
    "every fact carries source span; fixed legal disclaimer text (06 §7
    wording: hasta beyanina dayanir, hekim degerlendirmesinin yerine gecmez)
    rendered on note+PDF; golden note snapshots"

The suite is organised around the three clauses plus the invariants the
issue's ``risk:legal`` label makes load-bearing:

1. **"every fact carries source span"** — :class:`TestEveryFactCarriesASpan`.
   The guarantee is structural, not procedural: a note fact without a span is
   unconstructible, the composer's whole input surface accepts content only
   through the span-carrying wrapper, and the renderers emit a content line
   only from a fact. The near-miss control is an empty span tuple, which is
   the shape a careless caller actually produces.
2. **"fixed legal disclaimer text … rendered on note+PDF"** —
   :class:`TestFixedLegalDisclaimer`. CLAUDE.md invariant 18: the text renders
   only from ``docs/legal/`` with hash binding. That file does not exist in
   this repository, so the honest state of this clause today is *fails
   closed* — asserted directly — and every wording assertion runs against a
   SYNTHETIC fixture, never against copy transcribed from files/06 §7.
3. **"golden note snapshots"** — :class:`TestGoldenSnapshots`, byte-for-byte
   over three scenarios in every renderer.

Plus: invariant 1 (:class:`TestTriageIsRulesOnly`), invariant 20
(:class:`TestNoAccuracyClaims`), invariant 22
(:class:`TestNumbersAtTheBoundary`), invariant 6 and 4
(:class:`TestNoPhiAndNoNewEgress`), files/12 §2 coverage-gap semantics
(:class:`TestGapsAreAbsencesNotFacts`), and the one-authoritative-composer
question (:class:`TestOneAuthoritativeNoteVocabulary`).

Every value in the fixtures is synthetic (files/04 §7).
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import logging
import types
import typing
from pathlib import Path

import note_fixtures as fx
import pytest
from clinical_schemas.composition import AttributedNote, NoteSources
from clinical_schemas.mappers import NOTE_SECTION_IDS
from clinical_schemas.note import PreVisitNote
from clinical_schemas.provenance import (
    ATTRIBUTABLE_SECTIONS,
    Attributed,
    NoteFact,
    SourceKind,
    SourceSpan,
)
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    TriageLevel,
)
from intake_api.note import (
    NBSP,
    LineKind,
    NoteCompositionError,
    RenderedLine,
    UnattributedLineError,
    Watermark,
    compose_note,
    load_note_strings,
    note_string_keys,
    previsit_note_bundle,
    render_note_pdf,
    render_soap,
)
from intake_platform.legal import (
    LegalStrings,
    LegalStringsCatalog,
    LegalStringsChangedError,
    LegalStringsMissingError,
)
from intake_platform.legal.claims import scan_text
from intake_platform.llm.units import render_quantity
from pydantic import BaseModel, ValidationError

REPO = Path(__file__).resolve().parents[2]
GOLDENS = Path(__file__).resolve().parent / "goldens"

#: A SYNTHETIC fixed-strings file. The Turkish copy of files/06 §7 is a legal
#: text: it renders only from docs/legal/strings.yaml, authored by counsel
#: under INT-210, and is deliberately NOT reproduced anywhere in this suite.
SYNTHETIC_STRINGS = """---
legal_strings_version: int-084-test-fixture.1
---
previsit_note.disclaimer: "SENTETIK DIPNOT - gercek metin degildir"
previsit_note.screening_ai_label: "SENTETIK ETIKET - gercek metin degildir"
"""


def _write_strings(tmp_path: Path, body: str = SYNTHETIC_STRINGS) -> Path:
    path = tmp_path / "strings.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _strings(tmp_path: Path, body: str = SYNTHETIC_STRINGS) -> LegalStrings:
    catalog = LegalStringsCatalog(_write_strings(tmp_path, body))
    return catalog.entry(required=note_string_keys(screening_scored=True))


def _compose(scenario: str) -> AttributedNote:
    meta, triage, sources, candidates = getattr(fx, scenario)()
    return compose_note(meta=meta, triage=triage, sources=sources, candidate_flags=candidates)


SCENARIOS = ("green_typed", "yellow_candidates", "red_full")


# --------------------------------------------------------------------------
# 1. every fact carries source span
# --------------------------------------------------------------------------


class TestEveryFactCarriesASpan:
    """The provenance half. Structural, not procedural."""

    def test_a_span_is_required_on_the_fact_type(self) -> None:
        """Omitting the field is a construction error, not a render error."""
        with pytest.raises(ValidationError):
            NoteFact(section="chief_complaint", field_ref="chief_complaint.text", text="x")  # type: ignore[call-arg]

    def test_an_empty_span_tuple_is_the_near_miss_and_is_refused(self) -> None:
        """The negative control: the shape a careless caller actually makes."""
        with pytest.raises(ValidationError):
            NoteFact(
                section="chief_complaint",
                field_ref="chief_complaint.text",
                text="x",
                spans=(),
            )

    def test_the_attributed_carrier_refuses_a_value_without_a_span(self) -> None:
        with pytest.raises(ValidationError):
            Attributed[str](value="x")  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            Attributed[str](value="x", spans=())

    def test_a_span_must_be_a_real_interval(self) -> None:
        with pytest.raises(ValidationError):
            SourceSpan(kind=SourceKind.UTTERANCE, source_ref="turn:1", start=5, end=5)
        with pytest.raises(ValidationError):
            SourceSpan(kind=SourceKind.UTTERANCE, source_ref="turn:1", start=9, end=4)

    def test_a_page_belongs_to_a_document_span_only(self) -> None:
        with pytest.raises(ValidationError):
            SourceSpan(kind=SourceKind.UTTERANCE, source_ref="turn:1", start=0, end=2, page=1)

    def test_every_content_field_of_the_composer_input_is_span_carrying(self) -> None:
        """No seam: a caller cannot hand the composer content any other way."""
        unattributed = [
            name
            for name, info in NoteSources.model_fields.items()
            if name != "data_gaps" and not _carries_attribution(info.annotation)
        ]
        assert unattributed == [], unattributed

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_every_composed_fact_carries_at_least_one_span(self, scenario: str) -> None:
        composed = _compose(scenario)
        assert composed.facts
        for fact in composed.facts:
            assert fact.spans

    def test_a_content_line_without_a_fact_is_unconstructible(self) -> None:
        """The near-miss at the render boundary: a clinical statement on the
        page with no provenance behind it."""
        fact = _compose("green_typed").facts[0]
        with pytest.raises(UnattributedLineError):
            RenderedLine(LineKind.FACT, "bir sey")
        with pytest.raises(UnattributedLineError):
            RenderedLine(LineKind.HEADER, "S", fact)

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_every_rendered_content_line_traces_to_a_fact(
        self, scenario: str, tmp_path: Path
    ) -> None:
        rendered = render_soap(_compose(scenario), strings=_strings(tmp_path))
        for line in rendered.lines:
            assert (line.fact is not None) == (line.kind is LineKind.FACT)
        facts = {line.fact for line in rendered.lines if line.fact is not None}
        assert facts == set(_compose(scenario).facts)

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_the_sources_index_names_every_fact_and_its_spans(
        self, scenario: str, tmp_path: Path
    ) -> None:
        composed = _compose(scenario)
        rendered = render_soap(composed, strings=_strings(tmp_path))
        index = "\n".join(line.text for line in rendered.lines if line.kind is LineKind.SOURCE)
        for fact in composed.facts:
            assert fact.field_ref in index
            for span in fact.spans:
                assert f"{span.source_ref}[{span.start}:{span.end}]" in index

    def test_an_attributed_value_that_is_empty_produces_no_fact_and_no_content(self) -> None:
        """An empty answer is not a finding. It leaves the note, and the
        provenance index, silent rather than printing a blank line."""
        meta, triage, sources, _ = fx.green_typed()
        composed = compose_note(
            meta=meta,
            triage=triage,
            sources=sources.model_copy(
                update={
                    "chief_complaint": Attributed[str](value="", spans=(fx.typed("turn:1", 0, 1),))
                }
            ),
        )
        assert composed.note.chief_complaint.text == ""
        assert all(fact.section != "chief_complaint" for fact in composed.facts)

    def test_items_without_their_optional_fields_still_render_and_still_trace(
        self, tmp_path: Path
    ) -> None:
        """A coded item whose code, dose or date was never supplied prints what
        it has and nothing more — an absent optional is not an empty label."""
        meta, triage, sources, _ = fx.red_full()
        composed = compose_note(
            meta=meta, triage=triage, sources=sources.model_copy(update=fx.bare_items())
        )
        text = render_soap(composed, strings=_strings(tmp_path)).text()
        assert "pmh[0]: sentetik durum | status=unconfirmed | source=record" in text
        assert "medications[0]: sentetik ilac | reconciliation=new" in text
        assert "allergies[0]: sentetik madde" in text
        assert "imported_objective[0]: lab | summary=sentetik ozet" in text
        assert "icd10=" not in text

    def test_a_populated_section_without_a_fact_is_unrepresentable(self) -> None:
        """A hand-built note that populates content and names no fact is refused."""
        meta, triage, sources, _ = fx.green_typed()
        composed = compose_note(meta=meta, triage=triage, sources=sources)
        with pytest.raises(ValidationError):
            AttributedNote(note=composed.note, facts=())


def _carries_attribution(annotation: object) -> bool:
    """True when every content path of ``annotation`` goes through Attributed."""
    if isinstance(annotation, type) and issubclass(annotation, Attributed):
        return True
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in {typing.Union, types.UnionType}:
        return all(_carries_attribution(arg) for arg in args if arg is not type(None))
    if args:
        return any(_carries_attribution(arg) for arg in args)
    # a nested *Sources model is span-carrying when all of its own fields are;
    # ``provenance`` is excluded because it describes the session's setting
    # (files/06 §6), which is not a value extracted from any source
    return (
        isinstance(annotation, type)
        and issubclass(annotation, BaseModel)
        and annotation.__name__.endswith("Sources")
        and all(
            _carries_attribution(info.annotation)
            for name, info in annotation.model_fields.items()
            if name != "provenance"
        )
    )


# --------------------------------------------------------------------------
# 2. the fixed legal disclaimer
# --------------------------------------------------------------------------


class TestFixedLegalDisclaimer:
    """Invariant 18: legal texts render only from docs/legal with hash binding."""

    def test_the_repository_has_no_fixed_strings_file_yet(self) -> None:
        """The honest state of the acceptance's second clause today."""
        assert not (REPO / "docs" / "legal" / "strings.yaml").exists()

    def test_no_module_in_the_note_package_carries_the_copy(self) -> None:
        """The keys are declared here; the wording is counsel's, in docs/legal."""
        for path in sorted((REPO / "services/api/src/intake_api/note").rglob("*.py")):
            body = path.read_text(encoding="utf-8")
            assert "beyan" not in body.casefold(), path
            assert "hekim" not in body.casefold(), path

    def test_rendering_fails_closed_with_the_strings_file_absent(self, tmp_path: Path) -> None:
        catalog = LegalStringsCatalog(tmp_path / "legal" / "strings.yaml")
        with pytest.raises(LegalStringsMissingError):
            load_note_strings(catalog, _compose("green_typed"))

    def test_rendering_fails_closed_with_the_disclaimer_key_empty(self, tmp_path: Path) -> None:
        body = SYNTHETIC_STRINGS.replace('"SENTETIK DIPNOT - gercek metin degildir"', '""')
        catalog = LegalStringsCatalog(_write_strings(tmp_path, body))
        with pytest.raises(LegalStringsMissingError, match="previsit_note.disclaimer"):
            load_note_strings(catalog, _compose("green_typed"))

    def test_a_scored_screening_also_requires_its_ai_label(self, tmp_path: Path) -> None:
        body = SYNTHETIC_STRINGS.replace('"SENTETIK ETIKET - gercek metin degildir"', '""')
        catalog = LegalStringsCatalog(_write_strings(tmp_path, body))
        # unscored: the label is not required, so the note still renders
        assert load_note_strings(catalog, _compose("green_typed")).version
        with pytest.raises(LegalStringsMissingError, match="screening_ai_label"):
            load_note_strings(catalog, _compose("red_full"))

    def test_the_disclaimer_is_rendered_on_the_note(self, tmp_path: Path) -> None:
        strings = _strings(tmp_path)
        rendered = render_soap(_compose("red_full"), strings=strings)
        legal = [line.text for line in rendered.lines if line.kind is LineKind.LEGAL]
        assert strings.values["previsit_note.disclaimer"] in legal
        assert strings.values["previsit_note.screening_ai_label"] in legal

    def test_the_disclaimer_is_rendered_on_the_pdf(self, tmp_path: Path) -> None:
        strings = _strings(tmp_path)
        document = render_note_pdf(_compose("red_full"), strings=strings)
        assert b"SENTETIK DIPNOT" in document.pdf
        assert document.legal_strings_hash == strings.text_hash
        assert document.legal_strings_version == strings.version

    def test_the_renderer_itself_refuses_strings_that_lack_a_required_key(
        self, tmp_path: Path
    ) -> None:
        """The gate is on the render too, not only on the load: a caller that
        assembled the strings some other way still cannot produce a note."""
        body = SYNTHETIC_STRINGS.replace('"SENTETIK ETIKET - gercek metin degildir"', '"x"')
        strings = LegalStringsCatalog(_write_strings(tmp_path, body)).entry(
            required=note_string_keys(screening_scored=False)
        )
        loosened = dataclasses.replace(strings, values={"previsit_note.disclaimer": "SENTETIK"})
        with pytest.raises(LegalStringsMissingError, match="screening_ai_label"):
            render_soap(_compose("red_full"), strings=loosened)

    def test_the_render_records_the_binding_that_proves_what_it_said(self, tmp_path: Path) -> None:
        strings = _strings(tmp_path)
        rendered = render_soap(_compose("green_typed"), strings=strings)
        assert rendered.legal_strings_hash == strings.text_hash
        assert strings.text_hash in rendered.text()
        assert strings.version in rendered.text()

    def test_a_moved_strings_file_refuses_to_re_render_the_same_document(
        self, tmp_path: Path
    ) -> None:
        path = _write_strings(tmp_path)
        first = LegalStringsCatalog(path).entry(required=note_string_keys(screening_scored=False))
        _write_strings(
            tmp_path, SYNTHETIC_STRINGS.replace("int-084-test-fixture.1", "int-084-test-fixture.2")
        )
        with pytest.raises(LegalStringsChangedError):
            LegalStringsCatalog(path).entry(
                required=note_string_keys(screening_scored=False),
                expected_hash=first.text_hash,
            )

    def test_the_required_keys_are_declared_and_are_keys_not_copy(self) -> None:
        keys = note_string_keys(screening_scored=True)
        assert keys == ("previsit_note.disclaimer", "previsit_note.screening_ai_label")
        assert note_string_keys(screening_scored=False) == ("previsit_note.disclaimer",)


# --------------------------------------------------------------------------
# 3. invariant 1 — the note is not a second route to a level
# --------------------------------------------------------------------------


class TestTriageIsRulesOnly:
    def test_the_composer_refuses_an_llm_candidate_triage(self) -> None:
        meta, _, sources, _ = fx.yellow_candidates()
        candidate = LlmCandidateTriage(
            candidate_flags=(CandidateFlag(text="sentetik", evidence="turn:1"),)
        )
        with pytest.raises(NoteCompositionError):
            compose_note(meta=meta, triage=candidate, sources=sources)  # type: ignore[arg-type]

    def test_the_composed_level_is_the_rules_level_byte_for_byte(self) -> None:
        meta, triage, sources, candidates = fx.yellow_candidates()
        composed = compose_note(
            meta=meta, triage=triage, sources=sources, candidate_flags=candidates
        )
        assert composed.note.triage.level is TriageLevel.YELLOW
        assert composed.note.triage.rules == triage.rules

    def test_a_candidate_renders_as_a_candidate_and_never_as_a_determination(
        self, tmp_path: Path
    ) -> None:
        composed = _compose("yellow_candidates")
        rendered = render_soap(composed, strings=_strings(tmp_path))
        candidate_lines = [line for line in rendered.lines if line.kind is LineKind.CANDIDATE]
        assert candidate_lines
        for line in candidate_lines:
            assert "llm_candidate" in line.text
            for level in ("RED", "YELLOW", "GREEN"):
                assert level not in line.text
        triage_lines = [line.text for line in rendered.lines if line.kind is LineKind.TRIAGE]
        assert any("YELLOW" in text for text in triage_lines)

    def test_a_candidate_flag_may_not_name_a_level(self) -> None:
        """A model that answered with a level answered a different question."""
        meta, triage, sources, _ = fx.yellow_candidates()
        for word in ("RED", "yellow", "YELLOW_REVIEW"):
            with pytest.raises(NoteCompositionError):
                compose_note(
                    meta=meta,
                    triage=triage,
                    sources=sources,
                    candidate_flags=(CandidateFlag(text=word, evidence="turn:1"),),
                )

    def test_a_fact_may_not_claim_the_triage_section(self) -> None:
        with pytest.raises(ValidationError):
            NoteFact(
                section="triage",
                field_ref="triage.level",
                text="RED",
                spans=(fx.utterance("turn:1", 0, 3),),
            )
        assert "triage" not in ATTRIBUTABLE_SECTIONS

    def test_candidates_never_reach_the_fhir_document(self) -> None:
        composed = _compose("yellow_candidates")
        bundle = previsit_note_bundle(composed, patient_id="patient-0001")
        wire = json.dumps(bundle, ensure_ascii=False, sort_keys=True)
        assert "sentetik aday not" not in wire
        assert "YELLOW_REVIEW" not in wire

    def test_a_red_note_carries_the_three_axes(self, tmp_path: Path) -> None:
        rendered = render_soap(_compose("red_full"), strings=_strings(tmp_path))
        triage = "\n".join(line.text for line in rendered.lines if line.kind is LineKind.TRIAGE)
        assert "level: RED" in triage
        assert "register: ALERT" in triage
        assert "location: REMOTE" in triage


# --------------------------------------------------------------------------
# 4. invariant 20 — no accuracy claims
# --------------------------------------------------------------------------


class TestNoAccuracyClaims:
    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_the_rendered_note_trips_no_performance_claim_pattern(
        self, scenario: str, tmp_path: Path
    ) -> None:
        rendered = render_soap(_compose(scenario), strings=_strings(tmp_path))
        hits = scan_text(rendered.text(), groups=("performance", "satisfaction"))
        assert hits == (), hits

    def test_the_composer_has_no_seam_for_an_extraction_confidence(self) -> None:
        """INT-083 emits a confidence; it is not a property of the product."""
        assert "confidence" not in NoteSources.model_fields
        assert "confidence" not in AttributedNote.model_fields
        assert "confidence" not in NoteFact.model_fields
        assert "confidence" not in PreVisitNote.model_fields

    def test_the_note_package_never_names_a_performance_metric(self) -> None:
        for path in sorted((REPO / "services/api/src/intake_api/note").rglob("*.py")):
            hits = scan_text(path.read_text(encoding="utf-8"), groups=("performance",))
            assert hits == (), hits


# --------------------------------------------------------------------------
# 5. invariant 22 — numbers at a representation boundary
# --------------------------------------------------------------------------


class TestNumbersAtTheBoundary:
    def test_the_note_package_defines_no_second_quantity_renderer(self) -> None:
        """INT-083 already built one; a second one is a second answer."""
        for path in sorted((REPO / "services/api/src/intake_api/note").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FormattedValue) and node.format_spec is not None:
                    spec = ast.unparse(node.format_spec)
                    assert "," not in spec and "_" not in spec, (path, spec)

    def test_a_clinical_quantity_renders_without_grouping(self, tmp_path: Path) -> None:
        assert render_quantity(fx.GROUPING_PROBE) == "10000.5"
        rendered = render_soap(_compose("red_full"), strings=_strings(tmp_path))
        text = rendered.text()
        assert "1250" in text  # response_latency_ms_mean, ungrouped
        assert "1,250" not in text
        assert "1.250" not in text

    def test_number_and_unit_are_one_non_breaking_atom(self, tmp_path: Path) -> None:
        rendered = render_soap(_compose("red_full"), strings=_strings(tmp_path))
        speech = [line.text for line in rendered.lines if "speech_rate_syll_s" in line.text]
        assert speech
        assert any(f"4.25{NBSP}syll/s" in text for text in speech)

    def test_a_blocked_instrument_slot_renders_only_what_it_was_given(self, tmp_path: Path) -> None:
        """C-SSRS has no fixed shape in files/04 §5 and its licence is BLOCKED
        (HUMAN_BLOCKERS.md HB-L2), so the slot stays an open JSON value that is
        rendered as given and never interpreted into a score."""
        meta, triage, sources, _ = fx.red_full()
        screening = sources.screening.model_copy(
            update={
                "cssrs": Attributed[str](
                    value="sentetik", spans=(fx.typed("instrument:cssrs", 0, 8),)
                )
            }
        )
        composed = compose_note(
            meta=meta,
            triage=triage,
            sources=sources.model_copy(update={"screening": screening}),
        )
        rendered = render_soap(composed, strings=_strings(tmp_path))
        assert "screening.cssrs: sentetik" in rendered.text()

    def test_an_absent_severity_is_absent_and_never_a_zero(self, tmp_path: Path) -> None:
        rendered = render_soap(_compose("green_typed"), strings=_strings(tmp_path))
        assert "severity_nrs" not in rendered.text()

    def test_the_printed_unit_of_an_imported_value_is_carried_not_converted(
        self, tmp_path: Path
    ) -> None:
        """files/03 §4.6: magnitude wins; ``üre`` is never substring-matched."""
        rendered = render_soap(_compose("red_full"), strings=_strings(tmp_path))
        assert "Üre 45 mg/dL" in rendered.text()


# --------------------------------------------------------------------------
# 6. invariants 6 and 4 — no PHI in logs, and no new egress
# --------------------------------------------------------------------------


class TestNoPhiAndNoNewEgress:
    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_rendering_emits_no_log_record(
        self, scenario: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        strings = _strings(tmp_path)
        with caplog.at_level(logging.DEBUG):
            composed = _compose(scenario)
            render_soap(composed, strings=strings)
            render_note_pdf(composed, strings=strings)
            previsit_note_bundle(composed, patient_id="patient-0001")
        assert caplog.records == []

    def test_the_note_package_imports_no_logger_and_no_network_client(self) -> None:
        forbidden = {"logging", "httpx", "requests", "urllib", "socket", "aiohttp"}
        for path in sorted((REPO / "services/api/src/intake_api/note").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {(node.module or "").split(".")[0]}
                else:
                    continue
                assert not (names & forbidden), (path, names & forbidden)

    def test_the_note_package_adds_no_route(self) -> None:
        """A render that leaves the service is a share (invariant 4); this
        issue adds no egress, so there is nothing here to guard."""
        for path in sorted((REPO / "services/api/src/intake_api/note").rglob("*.py")):
            body = path.read_text(encoding="utf-8")
            assert "APIRouter" not in body, path


# --------------------------------------------------------------------------
# 7. files/12 §2 — a coverage gap is an absence, not a finding
# --------------------------------------------------------------------------


class TestGapsAreAbsencesNotFacts:
    def test_a_gap_carries_no_span_and_produces_no_fact(self) -> None:
        composed = _compose("green_typed")
        assert composed.note.data_gaps == ("hpi.oldcarts.character", "medications")
        assert all(fact.section != "data_gaps" for fact in composed.facts)

    def test_a_gap_never_enters_the_pertinent_negatives(self) -> None:
        composed = _compose("green_typed")
        assert composed.note.hpi.negatives == ()

    def test_an_elicited_negative_is_a_fact_with_a_span(self) -> None:
        composed = _compose("yellow_candidates")
        negatives = [f for f in composed.facts if f.field_ref.startswith("hpi.negatives")]
        assert negatives
        assert all(fact.spans for fact in negatives)

    def test_gaps_render_in_their_own_block(self, tmp_path: Path) -> None:
        rendered = render_soap(_compose("green_typed"), strings=_strings(tmp_path))
        gaps = [line.text for line in rendered.lines if line.kind is LineKind.GAP]
        assert gaps == ["hpi.oldcarts.character", "medications"]


# --------------------------------------------------------------------------
# 8. one authoritative note vocabulary
# --------------------------------------------------------------------------


class TestOneAuthoritativeNoteVocabulary:
    def test_the_composer_speaks_the_files_04_note_keys_and_nothing_else(self) -> None:
        assert set(ATTRIBUTABLE_SECTIONS) <= set(NOTE_SECTION_IDS)
        assert set(NOTE_SECTION_IDS) - set(ATTRIBUTABLE_SECTIONS) == {"triage", "data_gaps"}

    def test_the_api_share_ledger_names_real_note_sections(self) -> None:
        """INT-197's per-section share scopes address the same things."""
        from intake_api.schemas import SectionId

        assert set(typing.get_args(SectionId)) <= set(NOTE_SECTION_IDS)

    def test_a_confirmed_section_must_name_a_real_note_section(self) -> None:
        meta, triage, sources, _ = fx.green_typed()
        with pytest.raises(NoteCompositionError):
            compose_note(
                meta=meta,
                triage=triage,
                sources=sources.model_copy(
                    update={
                        "patient_confirmed_sections": (
                            Attributed[str](
                                value="not_a_section", spans=(fx.typed("turn:1", 0, 1),)
                            ),
                        )
                    }
                ),
            )

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_every_fact_section_is_a_note_key(self, scenario: str) -> None:
        for fact in _compose(scenario).facts:
            assert fact.section in NOTE_SECTION_IDS
            assert fact.field_ref.split(".")[0].split("[")[0] == fact.section


# --------------------------------------------------------------------------
# 9. golden snapshots
# --------------------------------------------------------------------------


class TestGoldenSnapshots:
    """Byte-for-byte, three scenarios, three renderers.

    What each golden pins:

    - ``*.soap.txt`` — the SOAP layout, the S/O/A/P split, the order of the
      blocks, the sources index and the position of the fixed disclaimer.
    - ``*.bundle.json`` — the FHIR document Bundle, which is the exchange
      face of the same note (INT-033), including that no candidate crosses.
    - ``*.pdf.sha256`` — the PDF is deterministic, so its digest is a stable
      receipt; a layout change has to be an intentional golden update.
    """

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_soap_golden(self, scenario: str, tmp_path: Path) -> None:
        rendered = render_soap(_compose(scenario), strings=_strings(tmp_path))
        golden = GOLDENS / f"{scenario}.soap.txt"
        assert rendered.text() == golden.read_text(encoding="utf-8")

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_fhir_bundle_golden(self, scenario: str) -> None:
        bundle = previsit_note_bundle(_compose(scenario), patient_id="patient-0001")
        golden = GOLDENS / f"{scenario}.bundle.json"
        expected = json.loads(golden.read_text(encoding="utf-8"))
        assert bundle == expected

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_pdf_golden_is_deterministic(self, scenario: str, tmp_path: Path) -> None:
        strings = _strings(tmp_path)
        composed = _compose(scenario)
        first = render_note_pdf(composed, strings=strings).pdf
        second = render_note_pdf(composed, strings=strings).pdf
        assert first == second
        golden = GOLDENS / f"{scenario}.pdf.sha256"
        assert hashlib.sha256(first).hexdigest() == golden.read_text(encoding="utf-8").strip()

    def test_the_pdf_is_watermark_ready(self, tmp_path: Path) -> None:
        strings = _strings(tmp_path)
        composed = _compose("green_typed")
        plain = render_note_pdf(composed, strings=strings)
        stamped = render_note_pdf(
            composed,
            strings=strings,
            watermark=Watermark(recipient="clinician-0007", issued_at=fx.GENERATED_AT),
        )
        assert plain.pdf != stamped.pdf
        assert b"clinician-0007" in stamped.pdf
        other = render_note_pdf(
            composed,
            strings=strings,
            watermark=Watermark(recipient="clinician-0008", issued_at=fx.GENERATED_AT),
        )
        assert other.pdf != stamped.pdf
