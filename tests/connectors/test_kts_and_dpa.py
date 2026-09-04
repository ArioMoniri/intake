"""INT-162 — the KTS application pack and the processor-role DPA references.

Two acceptance clauses gate here: *"KTS (SBYS Kayıt Tescil) application pack
generated from repo docs"* and *"processor-role DPA references"*.

Both are legal artefacts, and both follow the docs/legal pattern (INT-210): the
mechanism ships complete and the human-legal content is empty and fails closed.
The KTS pack is generated from a committed checklist derived verbatim from
files/06 §63 (SBYS-6); an item whose repo anchor is missing, and every item
whose authority is a list only SBSGM publishes, comes back ``blocked`` so the
pack is never reported ``complete`` on content nobody has supplied. The DPA
reference set is the closed list of processor clauses files/06 §7 requires,
each anchored to where this repo already meets it — the executed DPA itself is
HB-A15's to supply.
"""

from __future__ import annotations

from pathlib import Path

from intake_connectors.dpa import ProcessorDpaClause, processor_role_references
from intake_connectors.kts import KtsPack, KtsRequirement, build_kts_pack

REPO_ROOT = Path(__file__).resolve().parents[2]
KTS_PACK_DOC = REPO_ROOT / "docs/regulatory/kts_pack.md"


# --- KTS application pack ------------------------------------------------------------


def test_the_kts_pack_builds_from_the_committed_checklist() -> None:
    pack = build_kts_pack()
    assert isinstance(pack, KtsPack)
    assert pack.requirements
    assert all(isinstance(item, KtsRequirement) for item in pack.requirements)


def test_the_pack_is_not_complete_while_the_sbsgm_list_is_uncommitted() -> None:
    """The published KTS document list is SBSGM's to define and no committed
    source holds it, so the pack fails closed rather than declaring itself
    ready on content nobody supplied."""
    pack = build_kts_pack()
    assert pack.is_complete() is False
    assert pack.blocked(), "at least the SBSGM-published-list item is blocked"


def test_every_present_requirement_anchors_to_a_file_that_exists() -> None:
    """A pack item that claims a repo anchor must point at a real file, or the
    generator refuses it — a citation to a document that is not there is worse
    than a blocked item, because it reads as satisfied."""
    pack = build_kts_pack()
    present = [item for item in pack.requirements if item.status == "present"]
    assert present
    for item in present:
        assert item.repo_anchor is not None
        assert (REPO_ROOT / item.repo_anchor).exists(), item.repo_anchor


def test_the_pack_covers_usvs_conformance_and_processor_duties() -> None:
    ids = {item.id for item in build_kts_pack().requirements}
    assert "usvs_conformance" in ids
    assert "processor_duties" in ids
    assert "security_annex" in ids


def test_the_rendered_pack_matches_the_committed_document() -> None:
    """The committed ``docs/regulatory/kts_pack.md`` is the generator's output,
    so it cannot drift from the checklist without this test catching it."""
    assert KTS_PACK_DOC.exists()
    assert build_kts_pack().render_markdown() == KTS_PACK_DOC.read_text(encoding="utf-8")


# --- processor-role DPA references --------------------------------------------------


def test_the_processor_clause_set_is_the_files06_mandatory_list() -> None:
    clauses = processor_role_references()
    ids = {clause.id for clause in clauses}
    # files/06 §7's mandatory processor clauses.
    for required in (
        "role_allocation",
        "security_annex",
        "subprocessor_list",
        "audit_rights",
        "breach_notice",
        "deletion_return",
        "execution_kep_eimza",
    ):
        assert required in ids


def test_every_dpa_clause_anchors_to_a_repo_document_that_exists() -> None:
    for clause in processor_role_references():
        assert isinstance(clause, ProcessorDpaClause)
        assert (REPO_ROOT / clause.repo_anchor).exists(), clause.repo_anchor


def test_the_breach_notice_clause_states_the_24h_window() -> None:
    """The one number files/06 §7 fixes for the processor: breach notice to the
    controller within 24 hours. It is a requirement, not an accuracy claim, so
    it is stated here verbatim from the source."""
    breach = next(c for c in processor_role_references() if c.id == "breach_notice")
    assert "24" in breach.requirement
