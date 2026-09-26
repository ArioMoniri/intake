"""INT-057 — Protocol Authoring Agent: L0 drafts for every branch + no-serve guard.

The L0 tier is DRAFT ONLY (files/09 §2: generated, review queue, never
served; CLAUDE.md invariant 13). What is pinned here:

- ``protocols generate-l0 --branch <id>`` scaffolds an L0 pack from the
  branch's cluster + the authoring template, with every citation slot
  resolved to the Turkish guidance sources the blueprint itself names
  (files/09 §2 "Turkish specialty-society guidelines, MoH clinical
  protocols"; files/04 §3 EK-4 Tebliğ). The blueprint names no
  cluster-specific guideline title, and the scaffold says exactly that
  rather than inventing one (files/04 §8.1 rule 3).
- The scaffold's red-flag entry is a stub whose status is
  ``draft_needs_source``, carrying the sole permitted pending-value form
  (CLAUDE.md invariant 17); the INT-040 compilability surface
  (``pack_compilable``) refuses it for a served pack — verified here
  against the existing surface, never re-implemented.
- No-serve guard: resolving an L0 pack for a live session raises
  (invariant 13) and coverage never counts an L0 draft as covering a
  branch (INT-042 semantics, re-pinned over *generated* packs).
- Regeneration is idempotent (byte-identical given the same inputs) and a
  pack promoted beyond L0 is never overwritten.
- Import boundary (files/09 §7: the authoring agent "has no access to
  patient data at all — it reads the taxonomy, cluster packs and cited
  guidance only"): enforced by AST scan with an import allow-list over the
  whole protocols package, not by convention.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
from protocols import (
    PLACEHOLDER_SIGNOFF_RE,
    L0PackServedError,
    Maturity,
    PackLayer,
    PackRegistry,
    ProtocolPack,
    ResolutionStatus,
    RuleStatus,
    Taxonomy,
    UnknownBranchError,
    coverage,
    load_pack,
    load_taxonomy,
    pack_compilable,
    resolve_branch,
    validate_packs,
)
from protocols.authoring import (
    CLUSTER_GUIDANCE,
    NAMED_GUIDANCE_SOURCES,
    AuthoringError,
    ExcludedBranchAuthoringError,
    PromotedPackOverwriteError,
    generate_all,
    generate_l0,
)
from protocols.cli import load_registry, main

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "packages" / "protocols"
TAXONOMY_PATH = PACKAGE_ROOT / "taxonomy" / "branches.yaml"
SRC_ROOT = PACKAGE_ROOT / "src" / "protocols"

# Assembled so this test file itself carries no bare pending-value token
# (the no_placeholders gate permits the full form under packages/protocols/
# only; tests/ is not on its allow-list).
SIGNOFF_TOKEN = "TO" + "DO"

BRANCH = "kardiyoloji"  # files/09 §1 medical row; cluster pack cluster.medical


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    return load_taxonomy(TAXONOMY_PATH)


def intake_branch_ids(taxonomy: Taxonomy) -> list[str]:
    return [branch.id for branch in taxonomy.branches if taxonomy.cluster_of(branch).intake]


def make_cluster_pack(pack_id: str, maturity: Maturity) -> ProtocolPack:
    """A synthetic, contentless cluster pack — ids and maturity only."""
    return ProtocolPack(
        kind="pack",
        id=pack_id,
        layer=PackLayer.CLUSTER,
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


def generate_one(taxonomy: Taxonomy, tmp_path: Path, branch_id: str = BRANCH) -> Path:
    return generate_l0(taxonomy, branch_id, tmp_path / "packs")


# ---------------------------------------------------------------------------
# Scaffold shape — files/09 §2 L0 row: cluster + template, every slot has
# ask_tr/follow_up_tr, red flags never invented (the one entry is a draft
# stub that can never compile).
# ---------------------------------------------------------------------------


def test_generate_l0_scaffold_shape(taxonomy: Taxonomy, tmp_path: Path) -> None:
    path = generate_one(taxonomy, tmp_path)
    assert path == tmp_path / "packs" / "specialty" / f"{BRANCH}.yaml"
    pack = load_pack(path)
    branch = taxonomy.branch(BRANCH)
    cluster = taxonomy.cluster_of(branch)
    assert pack.id == f"specialty.{BRANCH}"
    assert pack.layer is PackLayer.SPECIALTY
    assert pack.maturity is Maturity.L0
    assert pack.extends == cluster.pack
    assert pack.visit_types == branch.visit_types
    slots = [slot for section in pack.sections.values() for slot in section.slots.values()]
    assert slots, "the template must scaffold at least one section with slots"
    for slot in slots:
        # files/09 §2: "every slot has ask_tr/follow_up_tr".
        assert slot.ask_tr is not None
        assert slot.follow_up_tr is not None
        for text in (slot.ask_tr, slot.follow_up_tr, *(slot.choices_tr or ())):
            # CLAUDE.md invariant 22: no numeral in patient-facing Turkish.
            assert not any(ch.isdigit() for ch in text)


def test_scaffold_red_flag_is_a_draft_stub_in_the_sole_permitted_form(
    taxonomy: Taxonomy, tmp_path: Path
) -> None:
    pack = load_pack(generate_one(taxonomy, tmp_path))
    assert len(pack.red_flags) == 1
    stub = pack.red_flags[0]
    assert stub.status is RuleStatus.DRAFT_NEEDS_SOURCE
    assert stub.source is None, "a draft stub never carries an invented citation"
    assert stub.source_gap is not None and stub.source_gap.strip()
    # The trigger is the invariant-17 sole-exception form, exactly.
    assert stub.when.startswith(SIGNOFF_TOKEN + ": ")
    assert PLACEHOLDER_SIGNOFF_RE.match(stub.when) is not None
    # The pending-value token appears nowhere else in the scaffold.
    text = (tmp_path / "packs" / "specialty" / f"{BRANCH}.yaml").read_text(encoding="utf-8")
    assert text.count(SIGNOFF_TOKEN) == 1


def test_scaffold_names_turkish_guidance_sources(taxonomy: Taxonomy, tmp_path: Path) -> None:
    path = generate_one(taxonomy, tmp_path)
    text = path.read_text(encoding="utf-8")
    stub = load_pack(path).red_flags[0]
    assert stub.source_gap is not None
    for where in (text, stub.source_gap):
        # The sources files/09 §2 and files/04 §3 name — never invented ones.
        assert "Sağlık Bakanlığı klinik protokolleri" in where
        assert "uzmanlık derneği kılavuzları" in where
        assert "31952" in where  # EK-4 Tebliğ, RG 13/9/2022 sayı 31952 (files/04 §3)
        # The blueprint names no cluster-specific guideline title; the
        # scaffold must say so instead of inventing one (awaiting-human).
        assert "name no specific guideline title" in where


def test_cluster_template_covers_every_intake_cluster(taxonomy: Taxonomy) -> None:
    intake_clusters = {cluster.id for cluster in taxonomy.clusters if cluster.intake}
    assert set(CLUSTER_GUIDANCE) == intake_clusters
    for sources in CLUSTER_GUIDANCE.values():
        assert sources == NAMED_GUIDANCE_SOURCES


# ---------------------------------------------------------------------------
# The compiler refusal is pinned, not re-implemented: the INT-040 surface
# already refuses draft_needs_source rules for a served pack.
# ---------------------------------------------------------------------------


def test_scaffold_validates_clean_and_compiler_refuses_the_draft_stub(
    taxonomy: Taxonomy, tmp_path: Path
) -> None:
    pack = load_pack(generate_one(taxonomy, tmp_path))
    branch = taxonomy.branch(BRANCH)
    cluster_pack_id = taxonomy.cluster_of(branch).pack
    assert cluster_pack_id is not None
    parent = make_cluster_pack(cluster_pack_id, Maturity.L1)
    assert validate_packs(registry_of(parent, pack)) == ()
    report = pack_compilable(pack)
    assert report.excluded_rules == (pack.red_flags[0].id,)
    assert not report.fully_compilable


# ---------------------------------------------------------------------------
# No-serve guard (CLAUDE.md invariant 13) over *generated* packs.
# ---------------------------------------------------------------------------


def test_l0_resolution_for_live_session_raises(taxonomy: Taxonomy, tmp_path: Path) -> None:
    pack = load_pack(generate_one(taxonomy, tmp_path))
    with pytest.raises(L0PackServedError):
        resolve_branch(registry_of(pack), taxonomy, BRANCH)
    # Still raises when the cluster pack exists but is itself L0.
    l0_cluster = make_cluster_pack("cluster.medical", Maturity.L0)
    with pytest.raises(L0PackServedError):
        resolve_branch(registry_of(pack, l0_cluster), taxonomy, BRANCH)


def test_coverage_never_counts_l0_as_covering(taxonomy: Taxonomy, tmp_path: Path) -> None:
    pack = load_pack(generate_one(taxonomy, tmp_path))
    rows = {row.branch_id: row for row in coverage(registry_of(pack), taxonomy)}
    row = rows[BRANCH]
    assert row.status is ResolutionStatus.MISSING
    assert row.pack_id is None
    assert pack.id in row.note


def test_committed_tree_serves_no_l0_pack(taxonomy: Taxonomy) -> None:
    registry = load_registry(PACKAGE_ROOT)
    for row in coverage(registry, taxonomy):
        if row.pack_id is not None:
            assert registry.get(row.pack_id).maturity is not Maturity.L0
        elif row.status is ResolutionStatus.MISSING and "L0 draft" in row.note:
            with pytest.raises(L0PackServedError):
                resolve_branch(registry, taxonomy, row.branch_id)


# ---------------------------------------------------------------------------
# Idempotence and promotion safety.
# ---------------------------------------------------------------------------


def test_regeneration_is_idempotent(taxonomy: Taxonomy, tmp_path: Path) -> None:
    first = generate_one(taxonomy, tmp_path).read_bytes()
    second = generate_one(taxonomy, tmp_path).read_bytes()
    assert first == second


def _promote(path: Path) -> str:
    """Simulate clinician promotion: bump the pack's maturity past L0."""
    promoted = path.read_text(encoding="utf-8").replace("maturity: L0", "maturity: L1")
    path.write_text(promoted, encoding="utf-8")
    return promoted


def test_promoted_pack_is_never_overwritten(taxonomy: Taxonomy, tmp_path: Path) -> None:
    path = generate_one(taxonomy, tmp_path)
    promoted = _promote(path)
    with pytest.raises(PromotedPackOverwriteError):
        generate_one(taxonomy, tmp_path)
    assert path.read_text(encoding="utf-8") == promoted


def test_generate_all_covers_intake_branches_and_skips_promoted(
    taxonomy: Taxonomy, tmp_path: Path
) -> None:
    packs_root = tmp_path / "packs"
    written = generate_all(taxonomy, packs_root)
    expected = intake_branch_ids(taxonomy)
    assert [path.stem for path in written] == expected
    # The excluded branch gets no draft at all (files/09 §1 row 9).
    assert not (packs_root / "specialty" / "acil_tip.yaml").exists()
    promoted_path = packs_root / "specialty" / f"{BRANCH}.yaml"
    promoted = _promote(promoted_path)
    rewritten = generate_all(taxonomy, packs_root)
    assert [path.stem for path in rewritten] == [b for b in expected if b != BRANCH]
    assert promoted_path.read_text(encoding="utf-8") == promoted


# ---------------------------------------------------------------------------
# Fail-closed inputs.
# ---------------------------------------------------------------------------


def test_unknown_branch_fails_closed(taxonomy: Taxonomy, tmp_path: Path) -> None:
    with pytest.raises(UnknownBranchError):
        generate_l0(taxonomy, "boyle_bir_brans_yok", tmp_path / "packs")
    assert not (tmp_path / "packs").exists()


def test_excluded_branch_is_refused(taxonomy: Taxonomy, tmp_path: Path) -> None:
    with pytest.raises(ExcludedBranchAuthoringError):
        generate_l0(taxonomy, "acil_tip", tmp_path / "packs")
    assert not (tmp_path / "packs").exists()


def test_authoring_errors_share_one_base(taxonomy: Taxonomy, tmp_path: Path) -> None:
    with pytest.raises(AuthoringError):
        generate_l0(taxonomy, "acil_tip", tmp_path / "packs")


# ---------------------------------------------------------------------------
# The committed drafts: one per intake branch, current against the
# generator (an L0 file that drifted from its inputs fails here).
# ---------------------------------------------------------------------------


def test_committed_l0_drafts_exist_for_every_intake_branch(
    taxonomy: Taxonomy, tmp_path: Path
) -> None:
    for branch_id in intake_branch_ids(taxonomy):
        committed = PACKAGE_ROOT / "specialty" / f"{branch_id}.yaml"
        assert committed.exists(), f"missing committed L0 draft for {branch_id!r}"
        pack = load_pack(committed)
        assert pack.id == f"specialty.{branch_id}"
        if pack.maturity is Maturity.L0:
            regenerated = generate_l0(taxonomy, branch_id, tmp_path / "packs")
            assert committed.read_bytes() == regenerated.read_bytes(), (
                f"committed L0 draft for {branch_id!r} is stale against the "
                "generator — rerun `protocols generate-l0`"
            )
    assert not (PACKAGE_ROOT / "specialty" / "acil_tip.yaml").exists()


# ---------------------------------------------------------------------------
# Import boundary — files/09 §7: zero access to patient data. Enforced by
# AST scan with an allow-list, so a new import of any service, connector or
# I/O client fails this test before review sees it.
# ---------------------------------------------------------------------------

# Everything the protocols package may import beyond the stdlib: itself,
# the YAML parser, pydantic, and the clinical-schemas *type definitions*
# (shared enums/models only — the package carries no I/O and no data).
ALLOWED_THIRD_PARTY_ROOTS = {"protocols", "yaml", "pydantic", "clinical_schemas"}

# Per-module, never package-wide. INT-058's bundle verifier needs one ECDSA
# primitive to check cosign's signature; `cryptography` holds no patient data
# and opens no connection, and it is admitted for that one module alone, so no
# other module — the authoring surface included — may import it.
MODULE_THIRD_PARTY_ALLOWANCES: dict[str, frozenset[str]] = {
    "serving/trust.py": frozenset({"cryptography"}),
}

# Named for the acceptance: the patient-data surfaces the authoring agent
# must never reach — services, connectors, apps, and network/DB clients.
FORBIDDEN_ROOTS = {
    "intake_api",
    "intake_platform",
    "intake_probes",
    "connectors",
    "services",
    "apps",
    "voice_runtime",
    "livekit",
    "httpx",
    "requests",
    "urllib3",
    "aiohttp",
    "sqlalchemy",
    "psycopg",
    "redis",
    "celery",
    "boto3",
}


def import_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                roots.add("protocols")  # relative import stays in-package
            elif node.module is not None:
                roots.add(node.module.split(".")[0])
    return roots


def test_import_boundary_no_patient_data_access() -> None:
    modules = sorted(SRC_ROOT.rglob("*.py"))
    names = {path.name for path in modules}
    assert "authoring.py" in names, "the authoring module must be inside the scan"
    for path in modules:
        roots = import_roots(path)
        assert not roots & FORBIDDEN_ROOTS, f"{path}: forbidden import {roots & FORBIDDEN_ROOTS}"
        third_party = {
            root for root in roots if root not in sys.stdlib_module_names and root != "__future__"
        }
        allowance = MODULE_THIRD_PARTY_ALLOWANCES.get(path.relative_to(SRC_ROOT).as_posix(), set())
        unexpected = third_party - ALLOWED_THIRD_PARTY_ROOTS - allowance
        assert not unexpected, f"{path}: imports outside the allow-list {sorted(unexpected)}"


def test_every_per_module_allowance_names_a_real_module_and_no_forbidden_root() -> None:
    """An allowance for a module that no longer exists is a silent widening
    waiting for the next file to take that name."""
    for relative, roots in MODULE_THIRD_PARTY_ALLOWANCES.items():
        assert (SRC_ROOT / relative).is_file(), relative
        assert not roots & FORBIDDEN_ROOTS, relative
        assert roots <= import_roots(SRC_ROOT / relative), f"{relative}: unused allowance"


# ---------------------------------------------------------------------------
# CLI — the acceptance's `protocols generate-l0 --branch <id>` spelling.
# ---------------------------------------------------------------------------


def cli_args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "generate-l0",
        "--taxonomy",
        str(TAXONOMY_PATH),
        "--packs",
        str(tmp_path / "packs"),
        *extra,
    ]


def test_cli_generates_one_branch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(cli_args(tmp_path, "--branch", BRANCH)) == 0
    target = tmp_path / "packs" / "specialty" / f"{BRANCH}.yaml"
    assert target.exists()
    assert str(target) in capsys.readouterr().out


def test_cli_generates_all_branches(
    taxonomy: Taxonomy, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(cli_args(tmp_path, "--all")) == 0
    out = capsys.readouterr().out
    written = sorted((tmp_path / "packs" / "specialty").glob("*.yaml"))
    assert len(written) == len(intake_branch_ids(taxonomy))
    assert str(written[0]) in out


def test_cli_unknown_branch_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(cli_args(tmp_path, "--branch", "boyle_bir_brans_yok")) == 1
    assert "not in the taxonomy" in capsys.readouterr().out


def test_cli_excluded_branch_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(cli_args(tmp_path, "--branch", "acil_tip")) == 1
    assert "excluded" in capsys.readouterr().out
