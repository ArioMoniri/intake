"""INT-042 — Taxonomy: all MHRS branches + clusters + visit types + coverage CLI.

Acceptance, verbatim: "taxonomy/branches.yaml seeded from 09 §1 with
verify_live_list true; every branch resolves to a cluster; `protocols
coverage` matrix; unknown booked branch fails a test".

The seed is packages/protocols/taxonomy/branches.yaml (files/09 §1 names it
the source of truth). Every synthetic pack built here is MECHANISM ONLY —
empty packs with ids and maturities, zero clinical content (INT-040 scope
discipline). CLAUDE.md invariant 13 (second half) is pinned here: every
branch resolves to an L1+ pack or its cluster pack, and an L0 pack resolved
for a live session raises.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from protocols import Maturity, PackLayer, PackRegistry, ProtocolPack, VisitType
from protocols.cli import load_registry, main
from protocols.taxonomy import (
    ExcludedBranchError,
    L0PackServedError,
    NoServablePackError,
    ResolutionStatus,
    Taxonomy,
    TaxonomyError,
    UnknownBranchError,
    coverage,
    load_taxonomy,
    resolve_branch,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = REPO_ROOT / "packages" / "protocols" / "taxonomy" / "branches.yaml"

# The nine clusters of files/09 §1 ("Clusters (9) — every branch maps to
# exactly one cluster pack"), including `excluded` (Acil Tıp; files/12 §1
# names `cluster.excluded` explicitly).
CLUSTERS_09_1 = {
    "medical",
    "surgical",
    "sensory",
    "womens_health",
    "child_health",
    "mental_health",
    "dental",
    "allied_and_reports",
    "excluded",
}


def make_pack(pack_id: str, layer: PackLayer, maturity: Maturity) -> ProtocolPack:
    """A synthetic, contentless chain pack — ids and maturity only."""
    return ProtocolPack(
        kind="pack",
        id=pack_id,
        layer=layer,
        version="0.1.0",
        schema_version=2,
        maturity=maturity,
        status="synthetic-test-pack",
        language="tr",
    )


def registry_of(*packs: ProtocolPack) -> PackRegistry:
    registry = PackRegistry()
    for pack in packs:
        registry.add(pack)
    return registry


@pytest.fixture(scope="module")
def seeded() -> Taxonomy:
    return load_taxonomy(TAXONOMY_PATH)


# ---------------------------------------------------------------------------
# The seed: files/09 §1 verbatim, verify_live_list true (HB-A11).
# ---------------------------------------------------------------------------


def test_seed_carries_verify_live_list_true(seeded: Taxonomy) -> None:
    # HB-A11: the flag stays set until the owner confirms the live MHRS list
    # from an e-Devlet login; INT-042 builds and tests against the seed.
    assert seeded.verify_live_list is True


def test_seed_lists_the_nine_09_1_clusters(seeded: Taxonomy) -> None:
    assert {c.id for c in seeded.clusters} == CLUSTERS_09_1
    # Every intake cluster binds a cluster-layer pack id; `excluded` binds
    # none (files/09 §1: pre-visit intake is never used for emergencies).
    for cluster in seeded.clusters:
        if cluster.id == "excluded":
            assert cluster.intake is False
            assert cluster.pack is None
        else:
            assert cluster.intake is True
            assert cluster.pack == f"cluster.{cluster.id}"


def test_every_branch_resolves_to_a_listed_cluster(seeded: Taxonomy) -> None:
    cluster_ids = {c.id for c in seeded.clusters}
    for branch in seeded.branches:
        assert branch.cluster in cluster_ids, branch.id


def test_branch_ids_are_unique_and_visit_types_are_09_1(seeded: Taxonomy) -> None:
    ids = [b.id for b in seeded.branches]
    assert len(ids) == len(set(ids))
    allowed = set(VisitType)
    for branch in seeded.branches:
        assert set(branch.visit_types) <= allowed, branch.id


def test_seed_counts_match_09_1(seeded: Taxonomy) -> None:
    by_cluster: dict[str, int] = {}
    for branch in seeded.branches:
        by_cluster[branch.cluster] = by_cluster.get(branch.cluster, 0) + 1
    # files/09 §1 cluster table, slash-lists expanded to their separately
    # bookable clinics (see the branches.yaml header for the expansion note).
    assert by_cluster == {
        "medical": 33,
        "surgical": 11,
        "sensory": 3,
        "womens_health": 5,
        "child_health": 18,
        "mental_health": 5,
        "dental": 9,
        "allied_and_reports": 7,
        "excluded": 1,
    }
    assert len(seeded.branches) == 92


def test_09_1_visit_type_annotations_are_honoured(seeded: Taxonomy) -> None:
    branches = {b.id: b for b in seeded.branches}
    # "Anesteziyoloji (preop polikliniği)" — files/09 §1 surgical row.
    assert branches["anesteziyoloji"].visit_types == (VisitType.PREOP,)
    # "Sağlık Kurulu (rapor)" and "Adli Tıp (rapor)" — allied_and_reports row.
    assert branches["saglik_kurulu"].visit_types == (VisitType.REPORT,)
    assert branches["adli_tip"].visit_types == (VisitType.REPORT,)
    # Acil Tıp books no pre-visit intake at all — no visit types.
    assert branches["acil_tip"].visit_types == ()


# ---------------------------------------------------------------------------
# Loader refusals — unknown cluster refs, duplicates, non-09-§1 visit types.
# ---------------------------------------------------------------------------

MINIMAL_HEADER = "verify_live_list: true\n"


def write_taxonomy(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "branches.yaml"
    path.write_text(MINIMAL_HEADER + body, encoding="utf-8")
    return path


def test_unknown_cluster_ref_is_refused(tmp_path: Path) -> None:
    path = write_taxonomy(
        tmp_path,
        "clusters:\n"
        "  - {id: medical, pack: cluster.medical}\n"
        "branches:\n"
        "  - {id: ic_hastaliklari, name_tr: İç Hastalıkları, cluster: ghost,\n"
        "     visit_types: [first]}\n",
    )
    with pytest.raises(TaxonomyError, match="unknown cluster"):
        load_taxonomy(path)


def test_duplicate_branch_id_is_refused(tmp_path: Path) -> None:
    path = write_taxonomy(
        tmp_path,
        "clusters:\n"
        "  - {id: medical, pack: cluster.medical}\n"
        "branches:\n"
        "  - {id: kardiyoloji, name_tr: Kardiyoloji, cluster: medical, visit_types: [first]}\n"
        "  - {id: kardiyoloji, name_tr: Kardiyoloji, cluster: medical, visit_types: [first]}\n",
    )
    with pytest.raises(TaxonomyError, match="duplicate branch id"):
        load_taxonomy(path)


def test_duplicate_cluster_id_is_refused(tmp_path: Path) -> None:
    path = write_taxonomy(
        tmp_path,
        "clusters:\n"
        "  - {id: medical, pack: cluster.medical}\n"
        "  - {id: medical, pack: cluster.medical}\n"
        "branches: []\n",
    )
    with pytest.raises(TaxonomyError, match="duplicate cluster id"):
        load_taxonomy(path)


def test_non_09_1_visit_type_is_refused(tmp_path: Path) -> None:
    path = write_taxonomy(
        tmp_path,
        "clusters:\n"
        "  - {id: medical, pack: cluster.medical}\n"
        "branches:\n"
        "  - {id: kardiyoloji, name_tr: Kardiyoloji, cluster: medical,\n"
        "     visit_types: [walk_in]}\n",
    )
    with pytest.raises(TaxonomyError, match="visit_types"):
        load_taxonomy(path)


def test_missing_verify_live_list_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "branches.yaml"
    path.write_text("clusters: []\nbranches: []\n", encoding="utf-8")
    with pytest.raises(TaxonomyError, match="verify_live_list"):
        load_taxonomy(path)


def test_intake_branch_without_visit_types_is_refused(tmp_path: Path) -> None:
    path = write_taxonomy(
        tmp_path,
        "clusters:\n"
        "  - {id: medical, pack: cluster.medical}\n"
        "branches:\n"
        "  - {id: kardiyoloji, name_tr: Kardiyoloji, cluster: medical, visit_types: []}\n",
    )
    with pytest.raises(TaxonomyError, match="at least one visit type"):
        load_taxonomy(path)


def test_non_mapping_document_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "branches.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(TaxonomyError, match="mapping"):
        load_taxonomy(path)


def test_invalid_yaml_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "branches.yaml"
    path.write_text("clusters: [unclosed\n", encoding="utf-8")
    with pytest.raises(TaxonomyError, match="invalid YAML"):
        load_taxonomy(path)


# ---------------------------------------------------------------------------
# Live-session resolution — the unknown-booked-branch guard and invariant 13.
# ---------------------------------------------------------------------------


def test_unknown_booked_branch_raises_typed_error(seeded: Taxonomy) -> None:
    # An MHRS booking for a branch the taxonomy does not know may never
    # silently run any pack (acceptance: "unknown booked branch fails a test").
    with pytest.raises(UnknownBranchError, match="uzay_dermatolojisi"):
        resolve_branch(registry_of(), seeded, "uzay_dermatolojisi")


def test_excluded_branch_never_gets_an_intake_pack(seeded: Taxonomy) -> None:
    with pytest.raises(ExcludedBranchError, match="acil_tip"):
        resolve_branch(registry_of(), seeded, "acil_tip")


def test_l0_cluster_pack_resolved_for_live_session_raises(seeded: Taxonomy) -> None:
    # Invariant 13: an L0 pack resolved for a live session raises.
    registry = registry_of(make_pack("cluster.medical", PackLayer.CLUSTER, Maturity.L0))
    with pytest.raises(L0PackServedError, match="cluster.medical"):
        resolve_branch(registry, seeded, "ic_hastaliklari")


def test_l0_direct_pack_with_no_cluster_pack_raises(seeded: Taxonomy) -> None:
    registry = registry_of(make_pack("specialty.ic_hastaliklari", PackLayer.SPECIALTY, Maturity.L0))
    with pytest.raises(L0PackServedError, match="specialty.ic_hastaliklari"):
        resolve_branch(registry, seeded, "ic_hastaliklari")


def test_l0_direct_pack_falls_back_to_reviewed_cluster_pack(seeded: Taxonomy) -> None:
    # files/09 §2: "A branch without an L1 pack runs its cluster pack" — an
    # L0 draft is not an L1 pack, and the reviewed cluster pack serves.
    registry = registry_of(
        make_pack("specialty.ic_hastaliklari", PackLayer.SPECIALTY, Maturity.L0),
        make_pack("cluster.medical", PackLayer.CLUSTER, Maturity.L1),
    )
    resolution = resolve_branch(registry, seeded, "ic_hastaliklari")
    assert resolution.status is ResolutionStatus.CLUSTER
    assert resolution.pack_id == "cluster.medical"


def test_direct_l1_pack_resolves_direct(seeded: Taxonomy) -> None:
    registry = registry_of(make_pack("specialty.romatoloji", PackLayer.SPECIALTY, Maturity.L1))
    resolution = resolve_branch(registry, seeded, "romatoloji")
    assert resolution.status is ResolutionStatus.DIRECT
    assert resolution.pack_id == "specialty.romatoloji"


def test_nothing_servable_raises_never_serves_bare_base(seeded: Taxonomy) -> None:
    # files/09 §1: no patient ever runs on bare base.intake — with no packs
    # at all the live path fails closed instead of inventing coverage.
    with pytest.raises(NoServablePackError, match="romatoloji"):
        resolve_branch(registry_of(), seeded, "romatoloji")


# ---------------------------------------------------------------------------
# Coverage matrix — DIRECT / CLUSTER / MISSING (+ EXCLUDED for Acil Tıp).
# ---------------------------------------------------------------------------


def test_coverage_today_is_honestly_all_missing(seeded: Taxonomy) -> None:
    rows = coverage(registry_of(), seeded)
    assert len(rows) == len(seeded.branches)
    by_status: dict[ResolutionStatus, int] = {}
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        assert row.pack_id is None
    assert by_status == {ResolutionStatus.MISSING: 91, ResolutionStatus.EXCLUDED: 1}


def test_coverage_counts_direct_and_cluster(seeded: Taxonomy) -> None:
    registry = registry_of(
        make_pack("specialty.romatoloji", PackLayer.SPECIALTY, Maturity.L1),
        make_pack("cluster.medical", PackLayer.CLUSTER, Maturity.L2),
    )
    rows = {row.branch_id: row for row in coverage(registry, seeded)}
    assert rows["romatoloji"].status is ResolutionStatus.DIRECT
    assert rows["romatoloji"].pack_id == "specialty.romatoloji"
    assert rows["ic_hastaliklari"].status is ResolutionStatus.CLUSTER
    assert rows["ic_hastaliklari"].pack_id == "cluster.medical"
    # A branch in another cluster is untouched by medical's pack.
    assert rows["genel_cerrahi"].status is ResolutionStatus.MISSING


def test_coverage_never_counts_an_l0_pack(seeded: Taxonomy) -> None:
    registry = registry_of(make_pack("cluster.medical", PackLayer.CLUSTER, Maturity.L0))
    rows = {row.branch_id: row for row in coverage(registry, seeded)}
    row = rows["ic_hastaliklari"]
    assert row.status is ResolutionStatus.MISSING
    assert row.pack_id is None
    assert "L0" in row.note


# ---------------------------------------------------------------------------
# CLI: `protocols coverage` — matrix + summary; --strict gates the exit code.
# ---------------------------------------------------------------------------


def cli_args(tmp_path: Path, *extra: str) -> list[str]:
    packs_root = tmp_path / "packs"
    packs_root.mkdir(exist_ok=True)
    return [
        "coverage",
        "--taxonomy",
        str(TAXONOMY_PATH),
        "--packs",
        str(packs_root),
        *extra,
    ]


def test_cli_prints_matrix_and_honest_empty_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(cli_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "ic_hastaliklari" in out
    assert "MISSING" in out
    assert "0 DIRECT" in out
    assert "0 CLUSTER" in out
    assert "91 MISSING" in out
    assert "1 EXCLUDED" in out
    # No-silent-caps: with zero packs on disk the CLI says so plainly.
    assert "zero packs" in out


def test_cli_strict_fails_while_branches_resolve_to_nothing(tmp_path: Path) -> None:
    assert main(cli_args(tmp_path, "--strict")) == 1


def test_cli_strict_passes_when_every_branch_is_covered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    taxonomy = write_taxonomy(
        tmp_path,
        "clusters:\n"
        "  - {id: medical, pack: cluster.medical}\n"
        "branches:\n"
        "  - {id: kardiyoloji, name_tr: Kardiyoloji, cluster: medical, visit_types: [first]}\n",
    )
    packs_root = tmp_path / "packs"
    (packs_root / "cluster").mkdir(parents=True)
    (packs_root / "cluster" / "medical.yaml").write_text(
        "# SENTETİK TEST VERİSİ — synthetic mechanism-only pack\n"
        "kind: pack\n"
        "id: cluster.medical\n"
        "layer: cluster\n"
        "version: 0.1.0\n"
        "schema_version: 2\n"
        "maturity: L1\n"
        "status: synthetic-test-pack\n"
        "language: tr\n",
        encoding="utf-8",
    )
    code = main(["coverage", "--taxonomy", str(taxonomy), "--packs", str(packs_root), "--strict"])
    assert code == 0
    out = capsys.readouterr().out
    assert "1 CLUSTER" in out
    assert "0 MISSING" in out


def test_registry_loader_skips_non_pack_documents(tmp_path: Path) -> None:
    # base/life_threat.yaml is a sibling life_threat_set, not a chain pack
    # (files/12 §1) — the coverage scan must pass over it, not crash on it.
    packs_root = tmp_path / "packs"
    (packs_root / "base").mkdir(parents=True)
    (packs_root / "base" / "life_threat.yaml").write_text(
        "kind: life_threat_set\nid: base.life_threat\n", encoding="utf-8"
    )
    registry = load_registry(packs_root)
    assert len(registry) == 0
