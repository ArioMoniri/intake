"""INT-112 — the Turkish lexicons: a matcher with no vocabulary in it.

files/03 §4.7.5 gives the ``linguistic`` lane *"deterministic Turkish
lexicons (negative affect, hopelessness, anhedonia, somatic worry)"* and a
crisis family whose hits *"bypass the lane"*. A lexicon is **clinical
content**: a list of Turkish words asserted to mean hopelessness is a
clinical judgement in exactly the way a threshold is, and HUMAN_BLOCKERS
rule 1 forbids inventing one. INT-043 is ``awaiting-human`` (HB-C1) and the
lexicons are HB-C16, raised by this issue.

So this suite asserts the shape of a *mechanism*:

- the shipped lexicon carries five families and **not one term**, each
  ``draft_needs_source`` with a written gap;
- the compiler refuses every one of them, and names why — a family that
  did not compile has **no key at all** in a match result, because ``0``
  would read as *measured, none found*;
- a draft family cannot smuggle terms past the schema, and an active one
  cannot ship without a source block;
- matching is by **whole token**, never by substring (CLAUDE.md invariant
  22: *"``üre`` is never substring-matched"*), and folds case the Turkish
  way, where ``I`` lowercases to ``ı`` and ``İ`` to ``i``;
- the marker families and the crisis family are reachable through
  **different methods**, so a caller typed to one cannot read the other.

Every Turkish string used as a *term* in this file is synthetic nonsense
(files/04 §7). That is the point: the mechanism is testable without anyone
authoring clinical vocabulary, and a suite that needed real terms to pass
would have smuggled the blocked content in through the test.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.lexicon import (
    CompiledLexicon,
    FamilyKind,
    LexiconDocument,
    LexiconSchemaError,
    compile_lexicon,
    load_lexicon,
    turkish_fold,
)
from protocols.types import RuleStatus
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
LEXICON_PATH = REPO_ROOT / "packages" / "protocols" / "lexicons" / "tr" / "linguistic.yaml"

#: The four marker families of files/03 §4.7.5, plus the crisis family whose
#: hits bypass the lane (files/03 §4.7.5; files/04 §4.2 defect 3).
MARKER_FAMILIES = ("negative_affect", "hopelessness", "anhedonia", "somatic_worry")
CRISIS_FAMILY = "crisis_disclosure"

#: A committed-snapshot-shaped source block. Synthetic: it exists so the
#: schema's active-family branch is reachable in a test, never as a citation.
SYNTHETIC_SOURCE = {
    "guideline_id": "sentetik-kilavuz",
    "version_or_date": "1.0",
    "url": "https://example.invalid/sentetik",
    "retrieved_on": date(2026, 9, 2),
    "quote": "sentetik alinti",
}


def _family(
    family_id: str,
    *,
    kind: str = "marker",
    status: str = "active",
    terms: tuple[str, ...] = ("mor kaplan",),
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": family_id,
        "kind": kind,
        "status": status,
        "terms": list(terms),
    }
    if status == RuleStatus.ACTIVE.value:
        payload["source"] = dict(SYNTHETIC_SOURCE)
    else:
        payload["source_gap"] = "sentetik bosluk"
    payload.update(overrides)
    return payload


def _document(*families: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "lexicon",
        "language": "tr",
        "version": 1,
        "families": list(families),
    }


def _signed(
    *, marker_terms: tuple[str, ...] = ("mor kaplan",), crisis_terms: tuple[str, ...]
) -> CompiledLexicon:
    """A fully synthetic *signed* lexicon — the test-only fixture that opens
    the gate, exactly as INT-110's ICF-bearing ``StudyRecord`` subclass did.
    Its terms are nonsense; no clinical vocabulary is authored anywhere."""
    return compile_lexicon(
        LexiconDocument.model_validate(
            _document(
                _family("negative_affect", terms=marker_terms),
                _family(CRISIS_FAMILY, kind="crisis", terms=crisis_terms),
            )
        )
    )


class TestTheShippedLexiconHasNoVocabularyInIt:
    def test_the_file_declares_the_families_files_03_names_and_no_others(self) -> None:
        document = load_lexicon(LEXICON_PATH)
        assert document.language == "tr"
        assert tuple(family.id for family in document.families) == (*MARKER_FAMILIES, CRISIS_FAMILY)

    def test_every_family_is_draft_needs_source_with_no_terms_and_a_written_gap(self) -> None:
        document = load_lexicon(LEXICON_PATH)
        for family in document.families:
            assert family.status is RuleStatus.DRAFT_NEEDS_SOURCE, family.id
            assert family.terms == (), family.id
            assert family.source is None, family.id
            assert family.source_gap is not None and family.source_gap.strip(), family.id

    def test_exactly_one_family_is_the_crisis_kind(self) -> None:
        document = load_lexicon(LEXICON_PATH)
        kinds = {family.id: family.kind for family in document.families}
        assert kinds[CRISIS_FAMILY] is FamilyKind.CRISIS
        assert all(kinds[name] is FamilyKind.MARKER for name in MARKER_FAMILIES)

    def test_the_raw_file_carries_no_term_string_at_all(self) -> None:
        """Read as YAML rather than through the model: a term hidden under a
        key the model ignores would still be authored vocabulary."""
        raw = yaml.safe_load(LEXICON_PATH.read_text(encoding="utf-8"))
        for family in raw["families"]:
            assert family["terms"] == []

    def test_the_shipped_lexicon_compiles_to_nothing_and_says_why(self) -> None:
        compiled = compile_lexicon(load_lexicon(LEXICON_PATH))
        assert compiled.marker_families == ()
        assert compiled.crisis_families == ()
        assert set(compiled.refused) == {*MARKER_FAMILIES, CRISIS_FAMILY}
        for family_id, reason in compiled.refused.items():
            assert reason.strip(), family_id

    def test_a_family_that_did_not_compile_has_no_key_rather_than_a_zero(self) -> None:
        """``0`` reads as *measured, none found*; absence reads as absent.
        This is INT-110's refused-lane-is-absent-not-idle, one layer in."""
        compiled = compile_lexicon(load_lexicon(LEXICON_PATH))
        assert compiled.match_markers("mor kaplan uctu") == {}
        assert compiled.match_crisis("mor kaplan uctu") == {}


class TestTheSchemaRefusesAHalfWrittenFamily:
    def test_a_draft_family_cannot_carry_terms(self) -> None:
        with pytest.raises(ValidationError, match="draft_needs_source"):
            LexiconDocument.model_validate(
                _document(
                    _family("negative_affect", status="draft_needs_source", terms=("mor kaplan",))
                )
            )

    def test_an_active_family_must_carry_a_source_block(self) -> None:
        payload = _family("negative_affect")
        del payload["source"]
        with pytest.raises(ValidationError, match="source"):
            LexiconDocument.model_validate(_document(payload))

    def test_an_active_family_with_no_terms_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="term"):
            LexiconDocument.model_validate(_document(_family("negative_affect", terms=())))

    def test_a_draft_family_must_state_its_gap(self) -> None:
        payload = _family("negative_affect", status="draft_needs_source", terms=())
        del payload["source_gap"]
        with pytest.raises(ValidationError, match="source_gap"):
            LexiconDocument.model_validate(_document(payload))

    def test_two_families_may_not_share_an_id(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            LexiconDocument.model_validate(
                _document(_family("negative_affect"), _family("negative_affect"))
            )

    def test_an_unknown_key_is_refused_rather_than_ignored(self) -> None:
        with pytest.raises(ValidationError):
            LexiconDocument.model_validate(_document(_family("negative_affect", severity=3)))

    def test_a_document_of_the_wrong_kind_is_refused_by_name(self) -> None:
        payload = _document(_family("negative_affect"))
        payload["kind"] = "pack"
        with pytest.raises(ValidationError):
            LexiconDocument.model_validate(payload)

    def test_a_non_turkish_document_is_refused(self) -> None:
        payload = _document(_family("negative_affect"))
        payload["language"] = "en"
        with pytest.raises(ValidationError):
            LexiconDocument.model_validate(payload)

    def test_loading_a_file_that_is_not_a_mapping_is_one_error_type(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.yaml"
        path.write_text("- not a mapping\n", encoding="utf-8")
        with pytest.raises(LexiconSchemaError):
            load_lexicon(path)

    def test_loading_invalid_yaml_is_the_same_error_type(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.yaml"
        path.write_text("families: [\n", encoding="utf-8")
        with pytest.raises(LexiconSchemaError):
            load_lexicon(path)

    def test_loading_a_document_the_schema_rejects_is_the_same_error_type(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "broken.yaml"
        path.write_text(yaml.safe_dump({"kind": "lexicon"}), encoding="utf-8")
        with pytest.raises(LexiconSchemaError):
            load_lexicon(path)


class TestMatchingIsByWholeTokenAndFoldsCaseTheTurkishWay:
    def test_a_term_never_matches_inside_a_longer_word(self) -> None:
        """CLAUDE.md invariant 22's last clause, as a lexicon property:
        ``üre`` is never substring-matched. The near-miss negative control
        is ``üreme``, which contains the term and must not fire."""
        compiled = _signed(marker_terms=("üre",), crisis_terms=("mor kaplan",))
        assert compiled.match_markers("üre yüksek") == {"negative_affect": 1}
        assert compiled.match_markers("üreme sağlığı") == {}
        assert compiled.match_markers("üre nitrojeni") == {"negative_affect": 1}

    def test_case_folds_the_turkish_way_not_the_ascii_way(self) -> None:
        compiled = _signed(marker_terms=("ışık",), crisis_terms=("mor kaplan",))
        assert compiled.match_markers("IŞIK vardı") == {"negative_affect": 1}
        assert compiled.match_markers("İŞİK vardı") == {}

    def test_the_dotted_capital_folds_to_the_dotted_lowercase(self) -> None:
        compiled = _signed(marker_terms=("iyi",), crisis_terms=("mor kaplan",))
        assert compiled.match_markers("İYİ hissediyorum") == {"negative_affect": 1}
        assert compiled.match_markers("IYI hissediyorum") == {}

    def test_turkish_fold_is_exported_and_exact(self) -> None:
        assert turkish_fold("I") == "ı"
        assert turkish_fold("İ") == "i"
        assert turkish_fold("IŞIK") == "ışık"
        assert turkish_fold("İSTANBUL") == "istanbul"

    def test_a_multi_word_term_matches_only_as_a_contiguous_run(self) -> None:
        compiled = _signed(marker_terms=("mor kaplan",), crisis_terms=("sarı tebeşir",))
        assert compiled.match_markers("bir mor kaplan gördüm") == {"negative_affect": 1}
        assert compiled.match_markers("mor bir kaplan gördüm") == {}

    def test_punctuation_does_not_hide_a_term(self) -> None:
        compiled = _signed(marker_terms=("mor kaplan",), crisis_terms=("sarı tebeşir",))
        assert compiled.match_markers("gördüm: mor kaplan!") == {"negative_affect": 1}

    def test_repeated_terms_are_counted_not_collapsed(self) -> None:
        compiled = _signed(marker_terms=("mor kaplan",), crisis_terms=("sarı tebeşir",))
        assert compiled.match_markers("mor kaplan ve mor kaplan") == {"negative_affect": 2}

    def test_matching_is_deterministic_across_repeats_and_family_order(self) -> None:
        forward = compile_lexicon(
            LexiconDocument.model_validate(
                _document(
                    _family("negative_affect", terms=("mor kaplan",)),
                    _family("hopelessness", terms=("sarı tebeşir",)),
                    _family(CRISIS_FAMILY, kind="crisis", terms=("yeşil kalem",)),
                )
            )
        )
        reversed_order = compile_lexicon(
            LexiconDocument.model_validate(
                _document(
                    _family("hopelessness", terms=("sarı tebeşir",)),
                    _family("negative_affect", terms=("mor kaplan",)),
                    _family(CRISIS_FAMILY, kind="crisis", terms=("yeşil kalem",)),
                )
            )
        )
        text = "mor kaplan ile sarı tebeşir ve yeşil kalem"
        first = forward.match_markers(text)
        for _ in range(50):
            assert forward.match_markers(text) == first
        assert reversed_order.match_markers(text) == first
        assert forward.match_crisis(text) == reversed_order.match_crisis(text)


class TestTheMarkerAndCrisisSurfacesAreSeparate:
    def test_match_markers_never_reports_the_crisis_family(self) -> None:
        compiled = _signed(marker_terms=("mor kaplan",), crisis_terms=("yeşil kalem",))
        assert compiled.match_markers("mor kaplan ve yeşil kalem") == {"negative_affect": 1}

    def test_match_crisis_never_reports_a_marker_family(self) -> None:
        compiled = _signed(marker_terms=("mor kaplan",), crisis_terms=("yeşil kalem",))
        assert compiled.match_crisis("mor kaplan ve yeşil kalem") == {CRISIS_FAMILY: 1}

    def test_the_two_family_lists_are_disjoint(self) -> None:
        compiled = _signed(marker_terms=("mor kaplan",), crisis_terms=("yeşil kalem",))
        assert set(compiled.marker_families).isdisjoint(compiled.crisis_families)

    def test_a_compiled_lexicon_is_frozen(self) -> None:
        compiled = _signed(marker_terms=("mor kaplan",), crisis_terms=("yeşil kalem",))
        with pytest.raises((AttributeError, TypeError, ValidationError)):
            compiled.marker_families = ()  # type: ignore[misc]


class TestTheHalfWrittenFamiliesTheOtherWayRound:
    """A family may not carry the *other* status's provenance either: a draft
    with a source block is not a draft, and an active family with a gap is
    telling two stories at once."""

    def test_a_draft_family_may_not_carry_a_source_block(self) -> None:
        payload = _family("negative_affect", status="draft_needs_source", terms=())
        payload["source"] = dict(SYNTHETIC_SOURCE)
        with pytest.raises(ValidationError, match="not a draft"):
            LexiconDocument.model_validate(_document(payload))

    def test_an_active_family_may_not_carry_a_source_gap(self) -> None:
        payload = _family("negative_affect")
        payload["source_gap"] = "sentetik bosluk"
        with pytest.raises(ValidationError, match="source_gap"):
            LexiconDocument.model_validate(_document(payload))

    def test_text_with_no_token_in_it_matches_nothing(self) -> None:
        compiled = _signed(crisis_terms=("yeşil kalem",))
        assert compiled.match_markers("… — !") == {}
        assert compiled.match_crisis("") == {}
