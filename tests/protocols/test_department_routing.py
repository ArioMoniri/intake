"""INT-323 — Department-dynamic previsit routing: department → branch → pack.

Today a received visit's ``department`` string is regex-matched to ~10 mobile
fixture packs and silently falls back to ``general``
(``apps/mobile/src/lib/intake/questions.ts`` ``packForDepartment``). The
durable backend must MAP a received department (from the Acıbadem/MHRS
connector, or any inbound source) onto the branch taxonomy and resolve the
SERVED pack per CLAUDE.md invariant 13 — never a silent wrong specialty, never
a bare ``base.intake``.

This pins:

- ``fold_department`` mirrors the mobile ``foldDepartment`` normalisation
  (Turkish-aware lowercase + diacritic strip + ``ı`` → ``i``);
- ``map_department`` maps a normalised department to a ``branches.yaml``
  ``branch_id`` by exact ``name_tr`` and by the aliases DERIVED from the
  committed mobile ``PACKS`` regexes — and returns an explicit ``UNMAPPED``
  state for anything else (fail closed), never a fuzzy guess;
- ``resolve_department`` chains department → branch → pack through
  :func:`protocols.taxonomy.resolve_branch`, so invariant 13 holds end to end:
  an unknown department raises :class:`DepartmentNotRoutableError` (no pack), an
  L0-only branch raises :class:`L0PackServedError`, Acil Tıp raises
  :class:`ExcludedBranchError`, and nothing servable raises
  :class:`NoServablePackError` rather than serving bare ``base.intake``.

Every synthetic pack here is MECHANISM ONLY (ids + maturity, zero clinical
content). The served pack CONTENT past L0 is gated on HB-C1 (clinical
sign-off) exactly as INT-042/INT-043 — the routing mechanism is what INT-323
delivers, and it fails closed while that gate is open.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from protocols import Maturity, PackLayer, PackRegistry, ProtocolPack
from protocols.department_routing import (
    DEPARTMENT_ALIASES,
    DepartmentMatch,
    DepartmentNotRoutableError,
    DepartmentRouting,
    department_index,
    fold_department,
    map_department,
    resolve_department,
)
from protocols.taxonomy import (
    ExcludedBranchError,
    L0PackServedError,
    NoServablePackError,
    ResolutionStatus,
    Taxonomy,
    TaxonomyError,
    load_taxonomy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = REPO_ROOT / "packages" / "protocols" / "taxonomy" / "branches.yaml"


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
# fold_department — the mobile foldDepartment mirror (files parity).
# ---------------------------------------------------------------------------


def test_fold_mirrors_the_mobile_normalisation() -> None:
    # The three cases the mobile comment names: full form, an in-flow form and
    # a truncated ASCII form all fold to the same key.
    assert fold_department("İç Hastalıkları") == "ic hastaliklari"
    assert fold_department("iç hastalıkları") == "ic hastaliklari"
    # Every Turkish special letter folds to ASCII (ğ ş ı İ ç ö ü).
    assert fold_department("Göğüs Hastalıkları") == "gogus hastaliklari"
    assert fold_department("Kulak Burun Boğaz Hastalıkları") == "kulak burun bogaz hastaliklari"
    assert fold_department("Deri ve Zührevi Hastalıkları") == "deri ve zuhrevi hastaliklari"
    # Locale-independent uppercase İ / dotless ı both land on "i".
    assert fold_department("KARDİYOLOJİ") == "kardiyoloji"


def test_fold_is_idempotent() -> None:
    once = fold_department("İç Hastalıkları")
    assert fold_department(once) == once


# ---------------------------------------------------------------------------
# map_department — exact name, alias, and the explicit UNMAPPED fail-closed.
# ---------------------------------------------------------------------------


def test_exact_taxonomy_name_maps_by_folded_name(seeded: Taxonomy) -> None:
    routing = map_department(seeded, "Kardiyoloji")
    assert isinstance(routing, DepartmentRouting)
    assert routing.branch_id == "kardiyoloji"
    assert routing.match is DepartmentMatch.EXACT_NAME


def test_exact_name_folds_case_and_diacritics(seeded: Taxonomy) -> None:
    assert map_department(seeded, "İÇ HASTALIKLARI").branch_id == "ic_hastaliklari"
    # Surrounding whitespace an inbound feed may carry does not defeat the map.
    assert map_department(seeded, "  Nöroloji  ").branch_id == "noroloji"


def test_derived_mhrs_aliases_map_to_taxonomy_branches(seeded: Taxonomy) -> None:
    # Aliases transcribed (folded) from the committed mobile PACKS regexes.
    cases = {
        "Dahiliye": "ic_hastaliklari",
        "KBB": "kulak_burun_bogaz_hastaliklari",
        "Dermatoloji": "deri_ve_zuhrevi_hastaliklari",
        "Cildiye": "deri_ve_zuhrevi_hastaliklari",
        "Ortopedi": "ortopedi_ve_travmatoloji",
        "Kadın Doğum": "kadin_hastaliklari_ve_dogum",
        "Jinekoloji": "kadin_hastaliklari_ve_dogum",
        "Göz": "goz_hastaliklari",
        "Gastroenteroloji": "gastroenteroloji",
        "Bevliye": "uroloji",
    }
    for department, branch_id in cases.items():
        routing = map_department(seeded, department)
        assert routing.branch_id == branch_id, department
        # An exact taxonomy name reports EXACT_NAME; a short form reports ALIAS.
        expected = (
            DepartmentMatch.EXACT_NAME
            if fold_department(department) in {fold_department(b.name_tr) for b in seeded.branches}
            else DepartmentMatch.ALIAS
        )
        assert routing.match is expected, department


def test_unknown_department_is_explicitly_unmapped(seeded: Taxonomy) -> None:
    routing = map_department(seeded, "Uzay Tıbbı")
    assert routing.branch_id is None
    assert routing.match is DepartmentMatch.UNMAPPED


def test_blank_department_is_unmapped(seeded: Taxonomy) -> None:
    for blank in ("", "   "):
        assert map_department(seeded, blank).match is DepartmentMatch.UNMAPPED


def test_near_miss_does_not_fuzzy_match(seeded: Taxonomy) -> None:
    # A prefix of a real branch name is NOT a match — the router is exact, so a
    # partial string never leaks into the wrong specialty (invariant 22's
    # "üre is never substring-matched" discipline, applied to routing).
    assert map_department(seeded, "Kardiyo").match is DepartmentMatch.UNMAPPED
    assert map_department(seeded, "Nöro").match is DepartmentMatch.UNMAPPED


# ---------------------------------------------------------------------------
# department_index — build guards fail closed on ambiguity and stale aliases.
# ---------------------------------------------------------------------------


def test_index_covers_every_branch_name(seeded: Taxonomy) -> None:
    index = department_index(seeded)
    for branch in seeded.branches:
        assert index[fold_department(branch.name_tr)] == branch.id


def test_every_alias_targets_a_real_seed_branch(seeded: Taxonomy) -> None:
    known = {branch.id for branch in seeded.branches}
    for alias, branch_id in DEPARTMENT_ALIASES.items():
        assert branch_id in known, f"alias {alias!r} → unknown branch {branch_id!r}"
        # Aliases are stored already folded, so the index build is stable.
        assert fold_department(alias) == alias, alias


def test_ambiguous_folded_names_raise(tmp_path: Path) -> None:
    # Two distinct branches whose names fold to the same key cannot both own it.
    path = tmp_path / "branches.yaml"
    path.write_text(
        "verify_live_list: true\n"
        "clusters:\n"
        "  - {id: sensory, pack: cluster.sensory}\n"
        "branches:\n"
        "  - {id: goz_a, name_tr: Göz, cluster: sensory, visit_types: [first]}\n"
        "  - {id: goz_b, name_tr: GÖZ, cluster: sensory, visit_types: [first]}\n",
        encoding="utf-8",
    )
    taxonomy = load_taxonomy(path)
    with pytest.raises(TaxonomyError, match="ambiguous"):
        department_index(taxonomy)


def test_stale_alias_target_raises(tmp_path: Path) -> None:
    # A taxonomy that lacks a branch an alias points at fails the index build
    # closed, rather than mapping a department to a branch that is not there.
    path = tmp_path / "branches.yaml"
    path.write_text(
        "verify_live_list: true\n"
        "clusters:\n"
        "  - {id: sensory, pack: cluster.sensory}\n"
        "branches:\n"
        "  - {id: goz_hastaliklari, name_tr: Göz Hastalıkları, cluster: sensory,\n"
        "     visit_types: [first]}\n",
        encoding="utf-8",
    )
    taxonomy = load_taxonomy(path)
    with pytest.raises(TaxonomyError, match="alias"):
        department_index(taxonomy)


# ---------------------------------------------------------------------------
# resolve_department — department → branch → served pack, invariant 13.
# ---------------------------------------------------------------------------


def test_known_department_resolves_to_its_direct_pack(seeded: Taxonomy) -> None:
    registry = registry_of(make_pack("specialty.romatoloji", PackLayer.SPECIALTY, Maturity.L1))
    resolution = resolve_department(registry, seeded, "Romatoloji")
    assert resolution.status is ResolutionStatus.DIRECT
    assert resolution.branch_id == "romatoloji"
    assert resolution.pack_id == "specialty.romatoloji"


def test_alias_department_resolves_through_its_cluster_pack(seeded: Taxonomy) -> None:
    # "Dahiliye" → ic_hastaliklari (medical); no specialty pack, so the branch
    # runs its reviewed cluster pack (files/09 §2).
    registry = registry_of(make_pack("cluster.medical", PackLayer.CLUSTER, Maturity.L1))
    resolution = resolve_department(registry, seeded, "Dahiliye")
    assert resolution.status is ResolutionStatus.CLUSTER
    assert resolution.branch_id == "ic_hastaliklari"
    assert resolution.pack_id == "cluster.medical"


def test_unknown_department_never_gets_a_specialty_pack(seeded: Taxonomy) -> None:
    # THE fail-closed guarantee: even with specialty packs present, an unknown
    # department resolves to NOTHING — never a silent wrong specialty.
    registry = registry_of(
        make_pack("specialty.kardiyoloji", PackLayer.SPECIALTY, Maturity.L1),
        make_pack("specialty.romatoloji", PackLayer.SPECIALTY, Maturity.L1),
        make_pack("cluster.medical", PackLayer.CLUSTER, Maturity.L1),
    )
    with pytest.raises(DepartmentNotRoutableError, match="uzay"):
        resolve_department(registry, seeded, "Uzay Tıbbı")


def test_l0_only_branch_raises_never_serves_a_draft(seeded: Taxonomy) -> None:
    # Invariant 13: an L0 pack resolved for a live session raises. "Kardiyoloji"
    # maps to kardiyoloji, whose only candidate here is an L0 cluster draft.
    registry = registry_of(make_pack("cluster.medical", PackLayer.CLUSTER, Maturity.L0))
    with pytest.raises(L0PackServedError, match="cluster.medical"):
        resolve_department(registry, seeded, "Kardiyoloji")


def test_excluded_department_is_refused(seeded: Taxonomy) -> None:
    # Acil Tıp books no pre-visit intake — RED routing only (files/09 §1).
    with pytest.raises(ExcludedBranchError, match="acil_tip"):
        resolve_department(registry_of(), seeded, "Acil Tıp")


def test_nothing_servable_fails_closed_not_bare_base(seeded: Taxonomy) -> None:
    with pytest.raises(NoServablePackError, match="romatoloji"):
        resolve_department(registry_of(), seeded, "Romatoloji")
