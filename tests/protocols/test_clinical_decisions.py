"""INT-432 — the clinical decisions register holds its own provenance.

Owner decision D18 (files/00_STATE.md §3) lets agents resolve open clinical
decisions for simulated-patient stress testing, on one condition this suite
enforces mechanically: **no value without a source**. A decision either
quotes a committed snapshot verbatim, or cites an openEHR CKM archetype by
id and revision, or stays ``draft_needs_source`` with the invariant-17
literal in exactly the place that is unsourced.

Each refusal below has a near-miss twin that is admitted, so a loader that
refused everything would fail as surely as one that refused nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.clinical_decisions import (
    REGISTER_DIR,
    SCOPE,
    DecisionRegisterError,
    DecisionStatus,
    VerifierVerdict,
    load_decision,
    load_register,
    quote_in_snapshot,
    snapshot_body,
    unsourced_paths,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs" / "clinical" / "decisions"
PENDING = "TO" + "DO" + ": a threshold requires clinical sign-off"

SNAPSHOT = """# guideline_id: TEST-GL-1
# title: Synthetic guideline for the loader's own tests
# version_or_date: 2026
# url: https://example.org/gl
# retrieved_on: 2026-10-02
---
Refer people to hospital as an emergency
if they currently have the symptom.
"""


def _decision(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "clinical_decision",
        "id": "CD-99",
        "title": "Synthetic",
        "question": "Q?",
        "decision": "D.",
        "status": "active",
        "scope": SCOPE,
        "author_role": "emergency medicine physician (agent)",
        "sources": [
            {
                "kind": "guideline",
                "guideline_id": "TEST-GL-1",
                "title": "Synthetic guideline",
                "version_or_date": "2026",
                "url": "https://example.org/gl",
                "retrieved_on": "2026-10-02",
                "quote": "Refer people to hospital as an emergency if they currently have",
                "snapshot": "packages/protocols/sources/TEST-GL-1.txt",
            }
        ],
        "value": {"answer": 1},
        "verifier": {"verdict": "pending"},
    }
    base.update(overrides)
    return base


@pytest.fixture
def root(tmp_path: Path) -> Path:
    sources = tmp_path / "packages" / "protocols" / "sources"
    sources.mkdir(parents=True)
    (sources / "TEST-GL-1.txt").write_text(SNAPSHOT, encoding="utf-8")
    return tmp_path


def _write(root: Path, document: dict[str, Any]) -> Path:
    path = root / f"{document['id']}.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    return path


# --- verbatim quotes ----------------------------------------------------------


def test_a_quote_wrapped_across_snapshot_lines_is_still_verbatim(root: Path) -> None:
    decision = load_decision(_write(root, _decision()), repo_root=root)
    assert decision.status is DecisionStatus.ACTIVE


def test_a_quote_with_one_word_changed_is_refused(root: Path) -> None:
    doc = _decision()
    doc["sources"][0]["quote"] = "Refer people to hospital as an emergency if they ever have"
    with pytest.raises(DecisionRegisterError, match="not verbatim"):
        load_decision(_write(root, doc), repo_root=root)


def test_quote_matching_normalises_whitespace_and_nothing_else() -> None:
    assert quote_in_snapshot("a  b\nc", "x a b c y")
    assert not quote_in_snapshot("a b, c", "x a b c y")


def test_a_snapshot_that_is_not_committed_is_refused(root: Path) -> None:
    doc = _decision()
    doc["sources"][0]["snapshot"] = "packages/protocols/sources/ABSENT.txt"
    with pytest.raises(DecisionRegisterError, match="not committed"):
        load_decision(_write(root, doc), repo_root=root)


def test_a_snapshot_outside_the_sources_tree_is_refused(root: Path) -> None:
    doc = _decision()
    doc["sources"][0]["snapshot"] = "docs/elsewhere/TEST-GL-1.txt"
    with pytest.raises(DecisionRegisterError, match="must live under"):
        load_decision(_write(root, doc), repo_root=root)


def test_a_snapshot_declaring_another_guideline_is_refused(root: Path) -> None:
    doc = _decision()
    doc["sources"][0]["guideline_id"] = "TEST-GL-2"
    with pytest.raises(DecisionRegisterError, match="the source cites"):
        load_decision(_write(root, doc), repo_root=root)


def test_a_retired_guideline_is_refused(root: Path) -> None:
    (root / "packages/protocols/sources/NICE-NG51.txt").write_text(
        SNAPSHOT.replace("TEST-GL-1", "NICE-NG51"), encoding="utf-8"
    )
    doc = _decision()
    doc["sources"][0].update(
        guideline_id="NICE-NG51", snapshot="packages/protocols/sources/NICE-NG51.txt"
    )
    with pytest.raises(DecisionRegisterError, match="retired"):
        load_decision(_write(root, doc), repo_root=root)


def test_a_ckm_archetype_needs_an_id_and_a_revision(root: Path) -> None:
    ckm = {
        "kind": "openehr_ckm",
        "archetype_id": "openEHR-EHR-CLUSTER.symptom_sign.v2",
        "revision": "2.1.0",
        "url": "https://ckm.openehr.org/ckm/archetypes/1013.1.188",
        "retrieved_on": "2026-10-02",
    }
    assert load_decision(_write(root, _decision(sources=[ckm])), repo_root=root)
    bad = dict(ckm, archetype_id="symptom_sign")
    with pytest.raises(DecisionRegisterError):
        load_decision(_write(root, _decision(sources=[bad])), repo_root=root)


# --- status and the invariant-17 literal --------------------------------------


def test_an_active_decision_without_a_source_is_refused(root: Path) -> None:
    with pytest.raises(DecisionRegisterError, match="at least one source"):
        load_decision(_write(root, _decision(sources=[])), repo_root=root)


def test_a_draft_decision_names_its_gap(root: Path) -> None:
    draft = _decision(status="draft_needs_source", sources=[], value={"x": PENDING})
    with pytest.raises(DecisionRegisterError, match="source_gap"):
        load_decision(_write(root, draft), repo_root=root)
    draft["source_gap"] = "no current guideline states a number"
    decision = load_decision(_write(root, draft), repo_root=root)
    assert unsourced_paths(decision) == ("value.x",)


def test_the_pending_literal_in_an_active_entry_is_refused(root: Path) -> None:
    doc = _decision(value={"windows": [{"class": "lab", "window_days": PENDING}]})
    with pytest.raises(DecisionRegisterError, match="neither the decision nor its entry"):
        load_decision(_write(root, doc), repo_root=root)


def test_the_pending_literal_inside_a_draft_entry_is_admitted(root: Path) -> None:
    entry = {
        "class": "lab",
        "window_days": PENDING,
        "status": "draft_needs_source",
        "source_gap": "no guideline states a recency for this class",
    }
    decision = load_decision(_write(root, _decision(value={"windows": [entry]})), repo_root=root)
    assert unsourced_paths(decision) == ("value.windows[0].window_days",)


def test_a_draft_entry_without_a_gap_is_refused(root: Path) -> None:
    entry = {"class": "lab", "window_days": PENDING, "status": "draft_needs_source"}
    with pytest.raises(DecisionRegisterError, match="names no source_gap"):
        load_decision(_write(root, _decision(value={"windows": [entry]})), repo_root=root)


def test_any_other_pending_token_is_refused_even_in_a_draft(root: Path) -> None:
    loose = "TO" + "DO" + " later"
    draft = _decision(status="draft_needs_source", sources=[], source_gap="gap", value={"x": loose})
    with pytest.raises(DecisionRegisterError, match="sanctioned"):
        load_decision(_write(root, draft), repo_root=root)


def test_a_decision_claiming_a_real_patient_scope_is_refused(root: Path) -> None:
    with pytest.raises(DecisionRegisterError):
        load_decision(_write(root, _decision(scope="production")), repo_root=root)


def test_a_verdict_names_the_verifier_and_the_date(root: Path) -> None:
    with pytest.raises(DecisionRegisterError, match="verifier role"):
        load_decision(_write(root, _decision(verifier={"verdict": "agree"})), repo_root=root)
    verified = {
        "verdict": "agree",
        "role": "independent verifier (agent)",
        "verified_on": "2026-10-02",
    }
    assert load_decision(_write(root, _decision(verifier=verified)), repo_root=root)


def test_file_name_and_id_must_agree(root: Path) -> None:
    path = root / "CD-98.yaml"
    path.write_text(yaml.safe_dump(_decision(), allow_unicode=True), encoding="utf-8")
    with pytest.raises(DecisionRegisterError, match="disagree"):
        load_decision(path, repo_root=root)


# --- the remaining refusals, each beside the shape it admits -------------------


def test_an_active_decision_carries_a_gap_only_for_keys_it_marks_draft(root: Path) -> None:
    with pytest.raises(DecisionRegisterError, match="only for the value_status keys"):
        load_decision(_write(root, _decision(source_gap="but also a gap")), repo_root=root)
    partly = _decision(
        source_gap="the window is not stated by any source",
        value={"route": "same_day", "window": PENDING},
        value_status={"route": "active", "window": "draft_needs_source"},
    )
    decision = load_decision(_write(root, partly), repo_root=root)
    assert unsourced_paths(decision) == ("value.window",)


def test_a_value_status_draft_covers_the_literal_and_an_active_one_does_not(
    root: Path,
) -> None:
    covered = _decision(
        source_gap="gap",
        value={"route": {"remote": PENDING}},
        value_status={"route": "draft_needs_source"},
    )
    assert load_decision(_write(root, covered), repo_root=root)
    with pytest.raises(DecisionRegisterError, match="neither the decision nor its entry"):
        load_decision(
            _write(root, dict(covered, value_status={"route": "active"}, source_gap=None)),
            repo_root=root,
        )


def test_a_draft_entry_may_state_its_reason_as_a_basis_or_through_the_decision_gap(
    root: Path,
) -> None:
    row = {"key": "nf-1", "status": "draft_needs_source", "basis": "no source sets urgency"}
    assert load_decision(_write(root, _decision(value={"rows": [row]})), repo_root=root)
    silent = {"key": "nf-1", "status": "draft_needs_source", "when": PENDING}
    with pytest.raises(DecisionRegisterError, match="names no source_gap"):
        load_decision(_write(root, _decision(value={"rows": [silent]})), repo_root=root)
    gap_above = _decision(
        source_gap="nf-1: no retrieved source states an action",
        value={"rows": [silent]},
        value_status={"rows": "draft_needs_source"},
    )
    assert load_decision(_write(root, gap_above), repo_root=root)


def test_a_snapshot_without_its_header_separator_is_refused(root: Path) -> None:
    (root / "packages/protocols/sources/TEST-GL-1.txt").write_text(
        SNAPSHOT.replace("---\n", ""), encoding="utf-8"
    )
    with pytest.raises(DecisionRegisterError, match="separating header"):
        load_decision(_write(root, _decision()), repo_root=root)
    with pytest.raises(DecisionRegisterError, match="separating header"):
        snapshot_body("no separator here")


def test_a_ckm_snapshot_of_another_revision_is_refused(root: Path) -> None:
    (root / "packages/protocols/sources/ckm.txt").write_text(
        "# guideline_id: openEHR-EHR-CLUSTER.symptom_sign.v2\n"
        "# version_or_date: revision 2.1.4\n---\nCharacter\n",
        encoding="utf-8",
    )
    ckm = {
        "kind": "openehr_ckm",
        "archetype_id": "openEHR-EHR-CLUSTER.symptom_sign.v2",
        "revision": "2.1.4",
        "url": "https://ckm.openehr.org/ckm/archetypes/1013.1.188",
        "retrieved_on": "2026-10-02",
        "quote": "Character",
        "snapshot": "packages/protocols/sources/ckm.txt",
    }
    assert load_decision(_write(root, _decision(sources=[ckm])), repo_root=root)
    with pytest.raises(DecisionRegisterError, match="not revision"):
        load_decision(
            _write(root, _decision(sources=[dict(ckm, revision="2.1.3")])), repo_root=root
        )


def test_a_source_nested_in_value_is_held_to_the_same_rules(root: Path) -> None:
    nested = dict(_decision()["sources"][0])
    admitted = _decision(value={"entry": {"x": 1, "sources": [nested]}})
    assert load_decision(_write(root, admitted), repo_root=root)
    reworded = dict(nested, quote="Refer people to clinic as an emergency")
    with pytest.raises(DecisionRegisterError, match="not verbatim"):
        load_decision(
            _write(root, _decision(value={"entry": {"sources": [reworded]}})), repo_root=root
        )
    malformed = {"kind": "guideline", "guideline_id": "TEST-GL-1"}
    with pytest.raises(DecisionRegisterError, match="malformed"):
        load_decision(
            _write(root, _decision(value={"entry": {"sources": [malformed]}})), repo_root=root
        )


def test_a_pending_token_in_the_decision_text_is_refused(root: Path) -> None:
    with pytest.raises(DecisionRegisterError, match="title carries"):
        load_decision(_write(root, _decision(title=PENDING)), repo_root=root)


def test_a_document_that_is_not_a_mapping_is_refused(root: Path) -> None:
    path = root / "CD-99.yaml"
    path.write_text("- a list\n", encoding="utf-8")
    with pytest.raises(DecisionRegisterError, match="is a mapping"):
        load_decision(path, repo_root=root)


def test_a_spec_basis_quote_must_be_verbatim_in_a_committed_file(root: Path) -> None:
    (root / "spec.md").write_text("The budget yields — not the safety set.\n", encoding="utf-8")
    basis = {"file": "spec.md", "section": "§1", "quote": "The budget yields", "supports": "x"}
    assert load_decision(_write(root, _decision(spec_basis=[basis])), repo_root=root)
    with pytest.raises(DecisionRegisterError, match="not verbatim"):
        reworded = dict(basis, quote="The safety set yields")
        load_decision(_write(root, _decision(spec_basis=[reworded])), repo_root=root)
    for missing in ("absent.md", "../outside.md"):
        with pytest.raises(DecisionRegisterError, match="not committed"):
            load_decision(
                _write(root, _decision(spec_basis=[dict(basis, file=missing)])), repo_root=root
            )


def test_value_status_names_real_keys_and_an_active_key_is_sourced(root: Path) -> None:
    draft = {"status": "draft_needs_source", "source_gap": "no number stated"}
    value = {"floor": PENDING, "gate": "regression", "nested": {"cap": PENDING, **draft}}
    admitted = _decision(
        status="draft_needs_source",
        sources=[],
        source_gap="the floor has no source",
        value=value,
        value_status={"floor": "draft_needs_source", "gate": "active"},
    )
    assert load_decision(_write(root, admitted), repo_root=root)
    with pytest.raises(DecisionRegisterError, match="which value lacks"):
        load_decision(_write(root, dict(admitted, value_status={"gaet": "active"})), repo_root=root)
    with pytest.raises(DecisionRegisterError, match="marked active but carries"):
        load_decision(
            _write(root, dict(admitted, value_status={"nested.cap": "active"})), repo_root=root
        )


def test_an_empty_register_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DecisionRegisterError, match="empty"):
        load_register(tmp_path)


# --- the committed register ---------------------------------------------------


def test_the_committed_register_loads_and_every_quote_is_verbatim() -> None:
    register = load_register()
    assert register
    for decision_id, decision in register.items():
        assert decision.scope == SCOPE, decision_id


def test_every_decision_has_a_human_readable_twin() -> None:
    ids = {path.stem for path in REGISTER_DIR.glob("CD-*.yaml")}
    docs = {path.stem for path in DOCS_DIR.glob("CD-*.md")}
    assert ids == docs


def test_every_decision_carries_an_independent_verdict() -> None:
    """INT-432 acceptance: the verifier's verdict is part of the entry."""
    for decision_id, decision in load_register().items():
        assert decision.verifier.verdict is not VerifierVerdict.PENDING, decision_id


# --- CD-10 (HB-C3): one polarity for hydration items, applied ----------------------


def _review_slots(path: Path) -> dict[str, dict[str, Any]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        key: slot
        for section in document["sections"].values()
        for key, slot in section["slots"].items()
    }


def test_cd10_every_hydration_slot_asks_its_decided_question_under_its_decided_id() -> None:
    decision = load_register()["CD-10"]
    assert decision.value["polarity_convention"] == "true_is_concern"
    for entry in decision.value["slots"]:
        slots = _review_slots(REPO_ROOT / entry["file"])
        assert entry["target_slot"] in slots, entry["pack"]
        assert slots[entry["target_slot"]]["ask_tr"]["tr"] == entry["ask_tr"], entry["pack"]
        assert slots[entry["target_slot"]]["type"] == "boolean", entry["pack"]
        if entry["slot"] != entry["target_slot"]:
            assert entry["slot"] not in slots, f"{entry['pack']} still asks {entry['slot']}"


def test_cd10_the_inverted_question_is_gone_from_the_whole_review_queue() -> None:
    """Near miss for the rename: the id is gone AND so is the wording whose
    `evet` meant "no concern" — a copy of it under another id would invert
    the same way."""
    inverted = "Çocuğunuz her zamanki kadar çiş yapıyor mu?"
    for path in sorted((REPO_ROOT / "packages/protocols/review").rglob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        assert "cis_miktari" not in text, path.name
        assert inverted not in text, path.name
