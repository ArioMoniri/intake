"""INT-471 — the legal decisions register holds its own provenance (owner decision D25).

D25 (files/00_STATE.md §3) lets a sourced legal-author agent decide open legal
items, with a separate legal-reviewer agent verifying them, **for synthetic and
test use only**. A licensed Turkish lawyer countersigns before any real
patient. This suite enforces the three conditions mechanically:

- **no answer without a source**: a decision quotes a committed verbatim
  snapshot of an official text, or it stays ``draft`` with a ``legal_gap``
  sentence and carries no answer (no pending token at all — the
  invariant-17 literal is clinical, and widening it is not this lane's call);
- **no active decision without a verdict**: ``active`` needs the reviewer's
  non-pending, non-disagreeing verdict;
- **no real patient without a countersign**: ``real_patient`` scope needs every
  countersign field, and no committed decision is cleared for a real patient.

Each refusal sits beside the near-miss shape it admits, so a loader that
refused everything would fail as surely as one that refused nothing.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.legal.decisions import (
    COUNTERSIGN_FIELDS,
    REGISTER_DIR,
    Audience,
    DecisionStatus,
    LegalClearanceError,
    LegalDecisionError,
    Scope,
    VerifierVerdict,
    clearance,
    draft_paths,
    load_decision,
    load_register,
    quote_in_snapshot,
    snapshot_body,
    snapshot_header,
    value_for,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs" / "legal" / "decisions"
SOURCES = "packages/intake_platform/legal_decisions/sources"

# Built, never written, so this suite does not carry the token it forbids.
PENDING = "TO" + "DO" + ": a retention period requires legal sign-off"

SNAPSHOT = """# source_id: TEST-LAW-1
# instrument: Sentetik Test Kanunu
# url: https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=1&MevzuatTur=1&MevzuatTertip=5
# gazette: 7/4/2016 sayı 29677
# retrieved_on: 2026-10-03
---
MADDE 1- (1) Kişisel veriler ilgili
kişinin açık rızası olmaksızın işlenemez.
"""

STANDARD_SNAPSHOT = """# source_id: TEST-STD-1
# instrument: Synthetic Accessibility Standard
# url: https://www.w3.org/TR/2024/REC-WCAG22-20241212/
# version_or_date: W3C Recommendation 12 December 2024
# retrieved_on: 2026-10-03
---
The time limit is essential and extending it would invalidate the activity; or
"""

VERIFIED = {
    "verdict": "agree",
    "role": "independent legal reviewer (agent; Turkish health and data-protection law)",
    "verified_on": "2026-10-03",
}

COUNTERSIGN = {
    "lawyer_name": "Av. Sentetik Kişi",
    "bar_association": "İstanbul Barosu",
    "bar_registration_no": "00000",
    "signed_commit": "0" * 40,
    "signed_on": "2026-10-03",
    "evidence": "docs/evidence/INT-471.md#countersign",
}


def _source(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "legislation",
        "source_id": "TEST-LAW-1",
        "instrument": "Sentetik Test Kanunu",
        "provision": "m.1(1)",
        "url": "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=1&MevzuatTur=1&MevzuatTertip=5",
        "gazette": {"published_on": "2016-04-07", "number": 29677},
        "retrieved_on": "2026-10-03",
        "quote": "Kişisel veriler ilgili kişinin açık rızası olmaksızın işlenemez.",
        "snapshot": f"{SOURCES}/TEST-LAW-1.txt",
        "supports": "basis",
    }
    base.update(overrides)
    return base


def _decision(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "legal_decision",
        "id": "LD-99",
        "title": "Synthetic",
        "question": "Q?",
        "outcome": "O.",
        "legal_basis": "Sentetik Test Kanunu m.1(1)",
        "status": "proposed",
        "scope": "synthetic_test_only",
        "author_role": "Turkish health and data-protection lawyer (agent)",
        "sources": [_source()],
        "value": {"basis": "acik_riza"},
        "verifier": {"verdict": "pending"},
    }
    base.update(overrides)
    return base


@pytest.fixture
def root(tmp_path: Path) -> Path:
    sources = tmp_path / SOURCES
    sources.mkdir(parents=True)
    (sources / "TEST-LAW-1.txt").write_text(SNAPSHOT, encoding="utf-8")
    (sources / "TEST-STD-1.txt").write_text(STANDARD_SNAPSHOT, encoding="utf-8")
    spec = tmp_path / "files"
    spec.mkdir()
    (spec / "00_STATE.md").write_text("Legal questions go to this lane.\n", encoding="utf-8")
    evidence = tmp_path / "docs" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "INT-471.md").write_text("## countersign\n", encoding="utf-8")
    return tmp_path


def _write(root: Path, document: dict[str, Any]) -> Path:
    path = root / f"{document['id']}.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    return path


def _snapshot_at(root: Path, url: str) -> dict[str, Any]:
    """A copy of the test snapshot published at another official url."""
    name = f"TEST-LAW-1-{abs(hash(url)) % 10_000}.txt"
    text = SNAPSHOT.replace(_source()["url"], url)
    (root / SOURCES / name).write_text(text, encoding="utf-8")
    return _source(url=url, snapshot=f"{SOURCES}/{name}")


def _load(root: Path, **overrides: Any) -> Any:
    return load_decision(_write(root, _decision(**overrides)), repo_root=root)


# --- verbatim quotes ------------------------------------------------------------


def test_a_sourced_proposed_decision_loads_with_a_quote_wrapped_across_lines(root: Path) -> None:
    decision = _load(root)
    assert decision.status is DecisionStatus.PROPOSED
    assert decision.scope is Scope.SYNTHETIC_TEST_ONLY


def test_a_quote_that_is_not_in_its_snapshot_is_refused(root: Path) -> None:
    changed = _source(quote="Kişisel veriler ilgili kişinin açık rızası olmadan işlenemez.")
    with pytest.raises(LegalDecisionError, match="not verbatim"):
        _load(root, sources=[changed])


def test_quote_matching_normalises_whitespace_and_nothing_else() -> None:
    assert quote_in_snapshot("a  b\nc", "x a b c y")
    assert not quote_in_snapshot("a b, c", "x a b c y")


def test_only_hash_lines_above_the_separator_are_header_and_the_body_is_below_it() -> None:
    text = "# source_id: X-1\na stray title line\n# retrieved_on: 2026-10-03\n---\nbody line\n"
    assert snapshot_header(text) == {"source_id": "X-1", "retrieved_on": "2026-10-03"}
    assert snapshot_body(text) == "body line"


def test_a_snapshot_that_is_not_committed_is_refused(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="not committed"):
        _load(root, sources=[_source(snapshot=f"{SOURCES}/ABSENT.txt")])


def test_a_snapshot_outside_the_sources_tree_is_refused(root: Path) -> None:
    for elsewhere in ("docs/legal/TEST-LAW-1.txt", f"{SOURCES}/../TEST-LAW-1.txt"):
        with pytest.raises(LegalDecisionError, match="must live under"):
            _load(root, sources=[_source(snapshot=elsewhere)])


def test_a_snapshot_declaring_another_source_is_refused(root: Path) -> None:
    other = SNAPSHOT.replace("TEST-LAW-1", "TEST-LAW-2")
    (root / SOURCES / "TEST-LAW-2.txt").write_text(other, encoding="utf-8")
    with pytest.raises(LegalDecisionError, match="declares"):
        _load(root, sources=[_source(snapshot=f"{SOURCES}/TEST-LAW-2.txt")])


def test_a_snapshot_retrieved_on_another_day_is_refused(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="retrieved_on"):
        _load(root, sources=[_source(retrieved_on="2026-10-02")])


def test_a_snapshot_without_its_header_separator_is_refused(root: Path) -> None:
    (root / SOURCES / "TEST-LAW-3.txt").write_text(
        "# source_id: TEST-LAW-3\nno separator\n", encoding="utf-8"
    )
    with pytest.raises(LegalDecisionError, match="separating header"):
        _load(root, sources=[_source(source_id="TEST-LAW-3", snapshot=f"{SOURCES}/TEST-LAW-3.txt")])


# --- official texts only --------------------------------------------------------


def test_legislation_is_cited_from_an_official_host(root: Path) -> None:
    secondary = _source(url="https://www.alomaliye.com/2026/05/19/saglik-raporlari-yonetmeligi/")
    with pytest.raises(LegalDecisionError, match="official"):
        _load(root, sources=[secondary])
    official = _snapshot_at(root, "https://www.resmigazete.gov.tr/eskiler/2026/05/20260519-12.pdf")
    assert _load(root, sources=[official])


def test_a_lookalike_host_is_not_official(root: Path) -> None:
    lookalike = _source(url="https://mevzuat.gov.tr.example.com/mevzuat?MevzuatNo=1")
    with pytest.raises(LegalDecisionError, match="official"):
        _load(root, sources=[lookalike])
    subdomain = _snapshot_at(root, "https://shgmmevzuatdb.saglik.gov.tr/TR-117242/x.html")
    assert _load(root, sources=[subdomain])


def test_legislation_names_its_resmi_gazete_date_and_number(root: Path) -> None:
    no_gazette = _source()
    del no_gazette["gazette"]
    with pytest.raises(LegalDecisionError, match="Resmî Gazete"):
        _load(root, sources=[no_gazette])


def test_a_standard_is_cited_from_its_publisher_with_its_version(root: Path) -> None:
    standard = {
        "kind": "standard",
        "source_id": "TEST-STD-1",
        "instrument": "Synthetic Accessibility Standard",
        "provision": "SC 2.2.1",
        "url": "https://www.w3.org/TR/2024/REC-WCAG22-20241212/",
        "version_or_date": "W3C Recommendation 12 December 2024",
        "retrieved_on": "2026-10-03",
        "quote": "The time limit is essential and extending it would invalidate the activity",
        "snapshot": f"{SOURCES}/TEST-STD-1.txt",
        "supports": "basis",
    }
    assert _load(root, sources=[standard])
    with pytest.raises(LegalDecisionError, match="version_or_date"):
        _load(root, sources=[{k: v for k, v in standard.items() if k != "version_or_date"}])
    with pytest.raises(LegalDecisionError, match="official"):
        _load(root, sources=[dict(standard, url="https://example.org/wcag")])


# --- no answer without a source ---------------------------------------------------


def test_an_unsourced_decision_that_is_not_a_draft_is_refused(root: Path) -> None:
    for status in ("proposed", "active"):
        with pytest.raises(LegalDecisionError, match="at least one source"):
            _load(root, status=status, sources=[], verifier=VERIFIED)
    draft = _load(
        root,
        status="draft",
        sources=[],
        value={},
        legal_gap="No retrieved text sets this period; the Kurul's guidance would settle it.",
    )
    assert draft.status is DecisionStatus.DRAFT


def test_a_draft_names_its_legal_gap(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="legal_gap"):
        _load(root, status="draft", sources=[], value={})
    with pytest.raises(LegalDecisionError, match="legal_gap"):
        _load(root, status="draft", sources=[], value={}, legal_gap="   ")


def test_a_pending_token_is_refused_anywhere_even_in_a_draft(root: Path) -> None:
    gap = "No retrieved text sets this period."
    with pytest.raises(LegalDecisionError, match="pending token"):
        _load(root, status="draft", sources=[], legal_gap=gap, value={"retention": PENDING})
    with pytest.raises(LegalDecisionError, match="pending token"):
        _load(root, outcome="Decided. " + PENDING)
    with pytest.raises(LegalDecisionError, match="pending token"):
        _load(root, value={"rows": [{"basis": "a", "note": PENDING}]})


def test_a_draft_key_is_named_in_value_status_and_explained_by_the_gap(root: Path) -> None:
    partly = {
        "value": {"basis": "acik_riza", "retention": "unset"},
        "value_status": {"basis": "sourced", "retention": "draft"},
    }
    with pytest.raises(LegalDecisionError, match="legal_gap"):
        _load(root, **partly)
    decision = _load(root, legal_gap="No retrieved text sets the retention period.", **partly)
    assert draft_paths(decision) == ("retention",)


def test_value_status_names_keys_that_exist(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="value lacks"):
        _load(root, value_status={"recipients": "draft"}, legal_gap="gap")
    nested = _load(
        root,
        sources=[_source(supports="rows.relatives.basis")],
        value={"rows": {"relatives": {"basis": "x", "notice": "unset"}}},
        value_status={"rows.relatives.notice": "draft"},
        legal_gap="No retrieved text says how a relative is informed.",
    )
    assert draft_paths(nested) == ("rows.relatives.notice",)


def test_a_legal_gap_on_a_fully_sourced_decision_is_refused(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="only for"):
        _load(root, legal_gap="but also a gap")


def test_a_spec_basis_quote_must_be_verbatim_in_a_committed_file(root: Path) -> None:
    basis = {
        "file": "files/00_STATE.md",
        "section": "§3 D25",
        "quote": "Legal questions go to this lane.",
        "supports": "basis",
    }
    assert _load(root, spec_basis=[basis])
    with pytest.raises(LegalDecisionError, match="not verbatim"):
        _load(root, spec_basis=[dict(basis, quote="Legal questions go to the owner.")])
    with pytest.raises(LegalDecisionError, match="not committed"):
        _load(root, spec_basis=[dict(basis, file="files/ABSENT.md")])
    with pytest.raises(LegalDecisionError, match="not committed"):
        _load(root, spec_basis=[dict(basis, file="../outside.md")])


# --- no active decision without the reviewer's verdict ------------------------------


def test_a_decision_without_a_non_pending_verdict_cannot_be_active(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="verdict"):
        _load(root, status="active")
    with pytest.raises(LegalDecisionError, match="verdict"):
        _load(root, status="active", verifier=dict(VERIFIED, verdict="disagree"))
    active = _load(root, status="active", verifier=VERIFIED)
    assert active.verifier.verdict is VerifierVerdict.AGREE
    applied = dict(VERIFIED, verdict="agree_with_changes", notes="Changes 1-3 applied in abc1234.")
    with_changes = _load(root, status="active", verifier=applied)
    assert with_changes.status is DecisionStatus.ACTIVE


def test_a_verified_decision_is_not_left_proposed(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="active"):
        _load(root, verifier=VERIFIED)
    assert _load(root, verifier=dict(VERIFIED, verdict="disagree"))


def test_a_verdict_names_the_reviewer_and_the_date(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="reviewer role"):
        _load(root, status="active", verifier={"verdict": "agree"})


# --- no real patient without a licensed lawyer's countersign ---------------------------


def test_real_patient_scope_without_a_countersign_is_refused(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="countersign"):
        _load(root, status="active", verifier=VERIFIED, scope="real_patient")
    partial = dict(COUNTERSIGN, bar_registration_no=None, signed_commit="  ")
    with pytest.raises(LegalDecisionError, match="bar_registration_no, signed_commit"):
        _load(
            root,
            status="active",
            verifier=VERIFIED,
            scope="real_patient",
            counsel_countersign=partial,
        )
    signed = _load(
        root,
        status="active",
        verifier=VERIFIED,
        scope="real_patient",
        counsel_countersign=COUNTERSIGN,
    )
    assert signed.counsel_countersign is not None
    assert signed.counsel_countersign.missing() == ()


def test_a_countersigned_decision_must_itself_be_active(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="active"):
        _load(root, scope="real_patient", counsel_countersign=COUNTERSIGN)


def test_a_countersign_belongs_only_to_a_real_patient_decision(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="real_patient"):
        _load(root, status="active", verifier=VERIFIED, counsel_countersign=COUNTERSIGN)
    empty = dict.fromkeys(COUNTERSIGN_FIELDS)
    assert _load(root, counsel_countersign=empty)


def test_a_countersign_is_recorded_in_an_evidence_file(root: Path) -> None:
    elsewhere = dict(COUNTERSIGN, evidence="docs/legal/decisions/LD-99.md")
    with pytest.raises(LegalDecisionError, match="docs/evidence/"):
        _load(
            root,
            status="active",
            verifier=VERIFIED,
            scope="real_patient",
            counsel_countersign=elsewhere,
        )


def test_an_unknown_scope_is_refused(root: Path) -> None:
    with pytest.raises(LegalDecisionError):
        _load(root, scope="production")


# --- the gate a consumer reads through ------------------------------------------------


def test_synthetic_use_needs_an_active_decision(root: Path) -> None:
    proposed = _load(root)
    with pytest.raises(LegalClearanceError, match="proposed"):
        clearance(proposed, Audience.SYNTHETIC_TEST)
    draft = _load(root, status="draft", sources=[], value={}, legal_gap="No text decides it.")
    with pytest.raises(LegalClearanceError, match="draft"):
        clearance(draft, Audience.SYNTHETIC_TEST)
    clearance(_load(root, status="active", verifier=VERIFIED), Audience.SYNTHETIC_TEST)


def test_real_patient_use_needs_the_countersign(root: Path) -> None:
    synthetic = _load(root, status="active", verifier=VERIFIED)
    with pytest.raises(LegalClearanceError, match="licensed"):
        clearance(synthetic, Audience.REAL_PATIENT)
    signed = _load(
        root,
        status="active",
        verifier=VERIFIED,
        scope="real_patient",
        counsel_countersign=COUNTERSIGN,
    )
    clearance(signed, Audience.REAL_PATIENT)
    clearance(signed, Audience.SYNTHETIC_TEST)


def test_a_draft_value_is_absent_never_defaulted(root: Path) -> None:
    decision = _load(
        root,
        status="active",
        verifier=VERIFIED,
        sources=[_source(supports="rows.basis")],
        value={"rows": {"basis": "acik_riza", "retention": "unset"}},
        value_status={"rows.retention": "draft"},
        legal_gap="No retrieved text sets the retention period.",
    )
    assert value_for(decision, "rows.basis", Audience.SYNTHETIC_TEST) == "acik_riza"
    with pytest.raises(LegalClearanceError, match="draft"):
        value_for(decision, "rows.retention", Audience.SYNTHETIC_TEST)
    with pytest.raises(LegalClearanceError, match="draft"):
        value_for(decision, "rows", Audience.SYNTHETIC_TEST)
    with pytest.raises(LegalClearanceError, match="no value"):
        value_for(decision, "rows.recipients", Audience.SYNTHETIC_TEST)
    with pytest.raises(LegalClearanceError, match="licensed"):
        value_for(decision, "rows.basis", Audience.REAL_PATIENT)


# --- round 2: every answer is tied to the text that gives it ------------------------------


def test_a_sourced_leaf_that_says_not_decided_is_refused(root: Path) -> None:
    value = {"basis": "acik_riza", "minor": "not decided (HB-L20)"}
    with pytest.raises(LegalDecisionError, match="not decided"):
        _load(root, value=value)
    drafted = _load(
        root,
        value=value,
        value_status={"minor": "draft"},
        legal_gap="No retrieved text says whether a minor consents alone.",
    )
    assert draft_paths(drafted) == ("minor",)


def test_every_source_names_the_value_it_supports(root: Path) -> None:
    bare = _source()
    del bare["supports"]
    with pytest.raises(LegalDecisionError, match="supports"):
        _load(root, sources=[bare])


def test_a_supports_path_must_resolve_in_value(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="resolves to nothing"):
        _load(root, sources=[_source(supports="basis"), _source(supports="retention")])
    rows = {"rows": {"a": {"basis": "x"}, "b": {"basis": "y"}}}
    assert _load(root, value=rows, sources=[_source(supports="rows.*.basis")])
    with pytest.raises(LegalDecisionError, match="resolves to nothing"):
        _load(
            root,
            value=rows,
            sources=[_source(supports="rows.*.basis"), _source(supports="rows.*.notice")],
        )
    with pytest.raises(LegalDecisionError, match="wildcard"):
        _load(root, sources=[_source(supports="*")])


def test_every_sourced_leaf_is_covered_by_a_source_or_a_spec_basis(root: Path) -> None:
    value = {"basis": "acik_riza", "recipients": "the tenant's clinicians"}
    with pytest.raises(LegalDecisionError, match="'recipients' has no source"):
        _load(root, value=value)
    assert _load(
        root,
        value=value,
        value_status={"recipients": "draft"},
        legal_gap="No retrieved text names the recipients.",
    )
    spec = {
        "file": "files/00_STATE.md",
        "section": "§3",
        "quote": "Legal questions go to this lane.",
        "supports": "recipients",
    }
    assert _load(root, value=value, spec_basis=[spec])
    nested = {"rows": {"basis": "acik_riza", "recipients": "the tenant's clinicians"}}
    assert _load(root, value=nested, sources=[_source(supports="rows")])


def test_a_spec_basis_supports_a_value_or_the_question(root: Path) -> None:
    spec = {
        "file": "files/00_STATE.md",
        "section": "§3",
        "quote": "Legal questions go to this lane.",
        "supports": "nothing_here",
    }
    with pytest.raises(LegalDecisionError, match="resolves to nothing"):
        _load(root, spec_basis=[spec])
    assert _load(root, spec_basis=[dict(spec, supports="question")])
    with pytest.raises(LegalDecisionError, match="resolves to nothing"):
        _load(root, sources=[_source(supports="basis"), _source(supports="question")])


def test_the_snapshot_header_carries_the_cited_gazette(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="gazette"):
        _load(root, sources=[_source(gazette={"published_on": "2016-04-07", "number": 29678})])
    with pytest.raises(LegalDecisionError, match="gazette"):
        _load(root, sources=[_source(gazette={"published_on": "2016-04-08", "number": 29677})])
    (root / SOURCES / "TEST-LAW-NOGAZ.txt").write_text(
        SNAPSHOT.replace("# gazette: 7/4/2016 sayı 29677\n", ""), encoding="utf-8"
    )
    with pytest.raises(LegalDecisionError, match="gazette"):
        _load(root, sources=[_source(snapshot=f"{SOURCES}/TEST-LAW-NOGAZ.txt")])


def test_the_snapshot_header_carries_the_cited_url(root: Path) -> None:
    other = "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=2&MevzuatTur=1&MevzuatTertip=5"
    with pytest.raises(LegalDecisionError, match="url"):
        _load(root, sources=[_source(url=other)])


def test_a_standard_snapshot_carries_the_cited_version(root: Path) -> None:
    standard = {
        "kind": "standard",
        "source_id": "TEST-STD-1",
        "instrument": "Synthetic Accessibility Standard",
        "provision": "SC 2.2.1",
        "url": "https://www.w3.org/TR/2024/REC-WCAG22-20241212/",
        "version_or_date": "W3C Recommendation 5 October 2023",
        "retrieved_on": "2026-10-03",
        "quote": "The time limit is essential and extending it would invalidate the activity",
        "snapshot": f"{SOURCES}/TEST-STD-1.txt",
        "supports": "basis",
    }
    with pytest.raises(LegalDecisionError, match="version_or_date"):
        _load(root, sources=[standard])


def test_a_quote_shorter_than_four_words_is_refused(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="four words"):
        _load(root, sources=[_source(quote="açık rızası olmaksızın")])
    assert _load(root, sources=[_source(quote="açık rızası olmaksızın işlenemez.")])


def test_agree_with_changes_is_active_only_with_the_changes_recorded(root: Path) -> None:
    changed = dict(VERIFIED, verdict="agree_with_changes")
    with pytest.raises(LegalDecisionError, match="notes"):
        _load(root, status="active", verifier=changed)
    with pytest.raises(LegalDecisionError, match="notes"):
        _load(root, status="active", verifier=dict(changed, notes="  "))
    assert _load(root, status="active", verifier=dict(changed, notes="Applied in abc1234."))


def test_the_reviewer_is_not_the_author(root: Path) -> None:
    same = dict(VERIFIED, role="Turkish health and data-protection lawyer (agent)")
    with pytest.raises(LegalDecisionError, match="independent"):
        _load(root, status="active", verifier=same)
    with pytest.raises(LegalDecisionError, match="independent"):
        _load(
            root,
            status="active",
            verifier=dict(same, role="  turkish HEALTH and data-protection lawyer (agent) "),
        )


def test_a_countersign_binds_a_commit_a_date_and_an_evidence_file(root: Path) -> None:
    signed = {"status": "active", "verifier": VERIFIED, "scope": "real_patient"}
    with pytest.raises(LegalDecisionError, match="40"):
        _load(root, counsel_countersign=dict(COUNTERSIGN, signed_commit="abc1234"), **signed)
    with pytest.raises(LegalDecisionError, match="before"):
        _load(root, counsel_countersign=dict(COUNTERSIGN, signed_on="2026-10-02"), **signed)
    absent = dict(COUNTERSIGN, evidence="docs/evidence/INT-999.md#countersign")
    with pytest.raises(LegalDecisionError, match="not committed"):
        _load(root, counsel_countersign=absent, **signed)
    assert _load(root, counsel_countersign=COUNTERSIGN, **signed)


# --- document shape ---------------------------------------------------------------------


def test_file_name_and_id_must_agree(root: Path) -> None:
    path = root / "LD-98.yaml"
    path.write_text(yaml.safe_dump(_decision(), allow_unicode=True), encoding="utf-8")
    with pytest.raises(LegalDecisionError, match="disagree"):
        load_decision(path, repo_root=root)


def test_a_document_that_is_not_a_mapping_is_refused(root: Path) -> None:
    path = root / "LD-97.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(LegalDecisionError, match="mapping"):
        load_decision(path, repo_root=root)


def test_an_empty_register_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LegalDecisionError, match="empty"):
        load_register(tmp_path, repo_root=tmp_path)


def test_a_register_loads_every_decision_read_only(root: Path) -> None:
    register_dir = root / "register"
    register_dir.mkdir()
    _write(register_dir, _decision())
    register = load_register(register_dir, repo_root=root)
    assert list(register) == ["LD-99"]
    with pytest.raises(TypeError):
        register["LD-98"] = register["LD-99"]  # type: ignore[index]


# --- the committed register ---------------------------------------------------------------


def test_the_committed_register_loads_and_every_quote_is_verbatim() -> None:
    register = load_register()
    assert {"LD-01", "LD-02", "LD-03", "LD-04", "LD-05"} <= set(register)
    for decision in register.values():
        assert decision.scope is Scope.SYNTHETIC_TEST_ONLY, decision.id


def test_no_committed_decision_is_cleared_for_a_real_patient() -> None:
    """D25's gate, the mirror of D17: nothing an agent decided reaches a real
    patient until a licensed Turkish lawyer countersigns it."""
    for decision in load_register().values():
        with pytest.raises(LegalClearanceError, match="licensed"):
            clearance(decision, Audience.REAL_PATIENT)


def test_every_committed_source_is_an_official_text_with_a_snapshot() -> None:
    for decision in load_register().values():
        for source in decision.sources:
            assert (REPO_ROOT / source.snapshot).is_file(), (decision.id, source.snapshot)
            assert source.retrieved_on <= date.today(), (decision.id, source.source_id)


def test_every_decision_has_a_human_readable_twin() -> None:
    register = load_register()
    docs = {path.stem for path in DOCS_DIR.glob("LD-*.md")}
    assert docs == set(register)
    for decision_id, decision in register.items():
        text = (DOCS_DIR / f"{decision_id}.md").read_text(encoding="utf-8")
        assert text.startswith(f"# {decision_id} — "), decision_id
        assert "synthetic and test use only" in text, decision_id
        assert "licensed Turkish lawyer" in text, decision_id
        assert f"Status: `{decision.status.value}`" in text, decision_id
        assert f"**{decision.verifier.verdict.value}**" in text, decision_id


def test_the_register_index_lists_every_decision() -> None:
    index = (DOCS_DIR / "README.md").read_text(encoding="utf-8")
    for decision_id, decision in load_register().items():
        row = re.search(rf"^\| \[{decision_id}\]\({decision_id}\.md\) \|.*$", index, re.MULTILINE)
        assert row is not None, decision_id
        assert f"`{decision.status.value}`" in row.group(0), decision_id


def test_the_register_lives_where_the_loader_reads_it() -> None:
    assert REGISTER_DIR == REPO_ROOT / "packages" / "intake_platform" / "legal_decisions"


# --- the first five decisions say what they decided -----------------------------------------


def test_ld01_keeps_the_report_purpose_item_out_of_adli_tip() -> None:
    value = load_register()["LD-01"].value
    assert value["allied_q3_rapor_amaci"]["carried_to_adli_tip"] is False
    assert value["saglik_raporlari_yonetmeligi_governs_adli_rapor"] is True
    assert value["madde_8_5_and_adli_rapor"] == "moot_for_product"
    # The pack still inherits the slot until INT-469 (PR #816); the decision says so.
    assert value["as_built"]["adli_tip_inherits_rapor_amaci"] is True
    # The no-intake-answer rule is a product rule, not a reading of the text.
    assert "intake_answer_into_adli_rapor" not in value
    assert "product rule" in load_register()["LD-01"].inference_disclosure


def test_ld02_names_no_proxy_for_an_adult_and_closes_the_child_and_carer_paths() -> None:
    decision = load_register()["LD-02"]
    who = decision.value["who_may_act_in_law"]
    assert who["adult_not_restricted"] == "self_only"
    assert who["adult_without_discernment_unrepresented"] == "nobody_in_law"
    assert decision.value["carers"]["synthetic_product_rule"] == "nobody_answers"
    assert decision.value["synthetic_paths"] == {"child": "closed", "carer": "closed"}
    drafted = draft_paths(decision)
    assert {"hb_l20.adolescent_self_consent", "consent_footing.minor_with_discernment"} <= set(
        drafted
    )
    assert "hb_l20.leap_day_maturity" not in drafted
    assert value_for_synthetic_is_refused(decision, "consent_footing.minor_with_discernment")


def value_for_synthetic_is_refused(decision: Any, key: str) -> bool:
    """A draft key stays absent even once the decision is verified."""
    verified = decision.model_copy(update={"status": DecisionStatus.ACTIVE})
    with pytest.raises(LegalClearanceError, match="draft"):
        value_for(verified, key, Audience.SYNTHETIC_TEST)
    return True


def test_ld03_bases_relatives_data_on_the_health_provider_and_never_on_the_patient() -> None:
    decision = load_register()["LD-03"]
    rows = decision.value["rows"]
    relatives = rows["family_history_relatives_consanguinity"]
    assert relatives["basis_patient"] == "kvkk_6_3_a_acik_riza"
    assert relatives["basis_other_subject"]["hospital_deployment"] == "kvkk_6_3_e"
    assert rows["hearing_voices_q16"]["register_category"] == "general_health"
    assert {
        "rows.family_history_relatives_consanguinity.consent_scope",
        "rows.hearing_voices_q16.consent_scope",
    } <= set(draft_paths(decision))


def test_ld04_files_tb_contact_under_household_and_sick_leave_under_occupational() -> None:
    items = load_register()["LD-04"].value["items"]
    assert items["isle_ilgili_rapor"]["register_category"] == "occupational"
    assert items["is_suresi"]["kvkk_class"] == "ordinary"
    assert items["evde_verem_temasi"]["register_category"] == "household"
    assert "only as far as that care requires" in items["evde_verem_temasi"]["recipients"]
    assert all("purpose" in item for item in items.values())


def test_ld05_holds_the_essential_exception_only_while_a_late_answer_is_honoured() -> None:
    value = load_register()["LD-05"].value
    assert value["is_a_time_limit_under_sc_2_2_1"] is True
    assert value["classification"] == "essential_exception_conditional"
    assert value["condition"]["late_location_answer_honoured"] is True
    assert "no_conforming_alternative_for_the_advance" in value


def test_every_committed_decision_is_either_awaiting_review_or_independently_verified() -> None:
    """Before a verdict is recorded: proposed, pending, review history kept.
    Once one is: active, agreeing, a reviewer who is not the author, dated,
    with what was checked or changed in the notes."""
    register = load_register()
    for decision_id in ("LD-01", "LD-02", "LD-03", "LD-04", "LD-05"):
        notes = register[decision_id].verifier.notes or ""
        assert "Round 1" in notes and "Round 2" in notes and "Round 3" in notes, decision_id
    for decision in register.values():
        verifier = decision.verifier
        if verifier.verdict is VerifierVerdict.PENDING:
            assert decision.status is DecisionStatus.PROPOSED, decision.id
            continue
        assert decision.status is DecisionStatus.ACTIVE, decision.id
        assert verifier.verdict in {VerifierVerdict.AGREE, VerifierVerdict.AGREE_WITH_CHANGES}
        assert verifier.role and verifier.role.strip().lower() != decision.author_role.lower()
        assert verifier.verified_on is not None, decision.id
        assert verifier.notes and verifier.notes.strip(), decision.id


# --- round 3: the reviewer's round 2 -------------------------------------------------------


def _text_of(decision_id: str) -> str:
    """What a decision asserts today: the YAML without its verifier block and the
    prose twin above its verdict. The reviewer's history may quote what was wrong."""
    yaml_text = (REGISTER_DIR / f"{decision_id}.yaml").read_text(encoding="utf-8")
    md_text = (DOCS_DIR / f"{decision_id}.md").read_text(encoding="utf-8")
    asserted_yaml = yaml_text.split("\nverifier:\n", 1)[0]
    asserted_md = md_text.split("\n## Reviewer verdict\n", 1)[0]
    assert asserted_yaml != yaml_text and asserted_md != md_text, decision_id
    return asserted_yaml + asserted_md


def test_ld01_names_the_adli_tip_follow_up_by_its_own_id() -> None:
    decision = load_register()["LD-01"]
    assert "INT-469 (PR #816)" in decision.outcome
    assert "INT-469" in (decision.fail_closed_while_draft or "")
    wrong = "INT-" + "473"
    assert wrong not in _text_of("LD-01")
    sry_row = next(
        line
        for line in (REPO_ROOT / "files" / "06_COMPLIANCE_TR.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("| SRY-2026 |")
    )
    assert "INT-469" in sry_row and wrong not in sry_row


def test_ld01_quotes_the_ninth_part_opening_at_madde_53() -> None:
    quotes = [source.quote for source in load_register()["LD-01"].sources]
    assert any(
        quote.startswith("DOKUZUNCU BÖLÜM") and quote.rstrip().endswith("MADDE 53-")
        for quote in quotes
    )


def test_ld05_records_that_796_honours_a_late_answer() -> None:
    decision = load_register()["LD-05"]
    assert "As of PR #796 head 3e243d16 (not yet on main) the condition is met" in decision.outcome
    assert "the condition is not met" not in _text_of("LD-05")
    assert "3e243d16" in (decision.inference_disclosure or "")
    assert (decision.fail_closed_while_draft or "").startswith(
        "BK13 is reported as supported for this timer only while the late answer is honoured"
    )
    assert decision.value["classification"] == "essential_exception_conditional"


def test_ld02_states_the_carer_texts_and_m15_no_stronger_than_written() -> None:
    decision = load_register()["LD-02"]
    quotes = [source.quote for source in decision.sources]
    assert any(
        q.startswith("Kanunda gösterilen ayrık durumlar saklı kalmak üzere,") for q in quotes
    )
    carers = [s for s in decision.sources if s.supports == "carers.in_law"]
    assert {s.source_id for s in carers} == {"TR-HHY-1998"}
    assert any("yakını veya kanuni temsilcisi" in s.quote for s in carers)
    in_law = decision.value["carers"]["in_law"]
    assert "as a rule the patient is informed personally" in in_law
    assert "only on the patient's signed written request" not in _text_of("LD-02")
    assert "save where the law provides otherwise" in decision.outcome


def test_ld04_purposes_stay_within_the_patients_own_care() -> None:
    items = load_register()["LD-04"].value["items"]
    for name, item in items.items():
        assert item["purpose"].startswith("the patient's own diagnosis and care"), name
        assert "public health" not in item["purpose"], name


def test_the_backlog_row_carries_the_genelge_code() -> None:
    rows = yaml.safe_load(
        (REPO_ROOT / "docs" / "backlog" / "issues.yaml").read_text(encoding="utf-8")
    )
    row = next(row for row in rows if row["id"] == "INT-471")
    assert "G2025-10" in row["legal"].split(",")


def test_the_ksvy_amendment_of_rg_33300_is_recorded_in_files_06() -> None:
    header = (REGISTER_DIR / "sources" / "TR-KSVY-2019.txt").read_text(encoding="utf-8")
    assert "4/7/2026 sayı 33300" in header
    ksvy_row = next(
        line
        for line in (REPO_ROOT / "files" / "06_COMPLIANCE_TR.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("| KSVY-5/6/7/13/16 |")
    )
    assert "RG 33300" in ksvy_row


# --- INT-484: guidance sources and LD-06 -----------------------------------------------------

GUIDANCE_SNAPSHOT = """# source_id: TEST-GUIDE-1
# instrument: Sentetik Kurul Rehberi
# url: https://www.kvkk.gov.tr/yayinlar/rehber.pdf
# version_or_date: Kasım 2017
# retrieved_on: 2026-10-04
---
K-anonimlik, bir veri kümesindeki belirli alanlarla, birden fazla kişinin tanımlanmasını sağlar.
"""


def _guidance(root: Path, **overrides: Any) -> dict[str, Any]:
    (root / SOURCES / "TEST-GUIDE-1.txt").write_text(GUIDANCE_SNAPSHOT, encoding="utf-8")
    base: dict[str, Any] = {
        "kind": "guidance",
        "source_id": "TEST-GUIDE-1",
        "instrument": "Sentetik Kurul Rehberi",
        "provision": "§3.1.3",
        "url": "https://www.kvkk.gov.tr/yayinlar/rehber.pdf",
        "version_or_date": "Kasım 2017",
        "retrieved_on": "2026-10-04",
        "quote": "K-anonimlik, bir veri kümesindeki belirli alanlarla",
        "snapshot": f"{SOURCES}/TEST-GUIDE-1.txt",
        "supports": "basis",
    }
    base.update(overrides)
    return base


def test_an_authority_guidance_is_cited_from_its_official_host_with_its_edition(root: Path) -> None:
    assert _load(root, sources=[_guidance(root)])
    with pytest.raises(LegalDecisionError, match="official"):
        _load(root, sources=[_guidance(root, url="https://example.org/rehber.pdf")])
    with pytest.raises(LegalDecisionError, match="version_or_date"):
        _load(root, sources=[_guidance(root, version_or_date=None)])


def test_a_guidance_snapshot_carries_the_cited_edition(root: Path) -> None:
    with pytest.raises(LegalDecisionError, match="version_or_date"):
        _load(root, sources=[_guidance(root, version_or_date="Ocak 2019")])


def test_ld06_decides_what_the_admin_analytics_may_hold() -> None:
    decision = load_register()["LD-06"]
    assert decision.scope is Scope.SYNTHETIC_TEST_ONLY
    assert decision.status is DecisionStatus.PROPOSED
    value = decision.value
    assert value["improvement"]["rides_the_care_purpose"] is False
    assert value["improvement"]["anonymised_aggregates_need_a_ground_or_consent"] is False
    assert value["improvement"]["hospital_deployment_needs_controller_authorisation"] is True
    assert value["research"]["anonymised_aggregates_need_consent"] is False
    assert value["research"]["record_level"]["separate_purpose"] is True
    assert value["admin_analytics"]["may_hold"] == "anonymised_aggregates_only"
    assert value["admin_analytics"]["pseudonymised_rows"] == "personal_data_never_admin_analytics"


def test_ld06_leaves_the_legal_cell_size_and_the_retention_periods_draft() -> None:
    from intake_platform.analytics import K_ANONYMITY_FLOOR

    decision = load_register()["LD-06"]
    drafted = set(draft_paths(decision))
    assert {"cell_size.legal_minimum", "retention.aggregates", "retention.raw_telemetry"} <= drafted
    assert decision.value["cell_size"]["product_floor_subjects"] == K_ANONYMITY_FLOOR
    assert decision.value["retention"]["periodic_destruction_max_months"] == 6


def test_ld06_gives_the_owner_one_recommendation_on_consent_scope() -> None:
    decision = load_register()["LD-06"]
    consent = decision.value["consent_scope"]
    assert "consent_scope.decision" in draft_paths(decision)
    assert consent["stop_and_ask"] is True
    assert isinstance(consent["owner_recommendation"], str) and consent["owner_recommendation"]
    recommendations = [
        path for path, _ in _leaves_of(decision.value) if path.endswith("owner_recommendation")
    ]
    assert recommendations == ["consent_scope.owner_recommendation"]


def _leaves_of(node: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(node, dict):
        out: list[tuple[str, Any]] = []
        for key, child in node.items():
            out += _leaves_of(child, f"{prefix}.{key}" if prefix else str(key))
        return out
    return [(prefix, node)]
