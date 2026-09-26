"""INT-353 — the review queue (specialty and cluster) is never a served pack.

``packages/protocols/review/specialty/`` and ``packages/protocols/review/cluster/``
hold QUESTIONS-authored candidates that await the physician of record's
sign-off (HB-C1). Their pack ids are the ids a served pack would carry
(``specialty.<branch>``, ``cluster.<cluster>``), so the only thing standing
between a candidate and a live session is where the registry reads from and
what maturity the candidate carries. Both are pinned here:

- the served registry reads the files/12 §1 layer directories only, and no
  layer is the review queue, so ``resolve_branch`` never sees a candidate;
- ``load_registry`` refuses the review queue itself as a packs root, so a
  mistyped ``--packs`` fails closed instead of serving candidates (a root
  whose name merely contains the word still loads — the near-miss control);
- ``load_registry`` also refuses a layer directory or a pack file that
  resolves into the review queue, so linking ``cluster/`` (which has no
  served tree yet) or ``specialty/`` to the queue fails closed too (a layer
  linked to a served tree still loads — the near-miss control);
- every committed candidate is L0, unsigned, not compilable, and raises
  ``L0PackServedError`` even when it is registered on purpose (invariant 13);
- the served drafts stay byte-identical to ``protocols generate-l0``, which
  ``test_l0_guard.py`` already pins and is not re-implemented here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from protocols import (
    L0PackServedError,
    Maturity,
    NoServablePackError,
    PackLayer,
    PackRegistry,
    PackSchemaError,
    ProtocolPack,
    RuleStatus,
    Taxonomy,
    load_pack,
    load_taxonomy,
    pack_compilable,
    resolve_branch,
)
from protocols.cli import REVIEW_QUEUE_DIRNAME, ReviewQueueRootError, load_registry

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "packages" / "protocols"
REVIEW_ROOT = PACKAGE_ROOT / "review"
REVIEW_SPECIALTY = REVIEW_ROOT / "specialty"
REVIEW_CLUSTER = REVIEW_ROOT / "cluster"
SERVED_SPECIALTY = PACKAGE_ROOT / "specialty"
SERVED_CLUSTER = PACKAGE_ROOT / "cluster"
TAXONOMY_PATH = PACKAGE_ROOT / "taxonomy" / "branches.yaml"


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    return load_taxonomy(TAXONOMY_PATH)


@pytest.fixture(scope="module")
def served() -> PackRegistry:
    return load_registry(PACKAGE_ROOT)


def candidate_paths() -> list[Path]:
    return sorted(REVIEW_SPECIALTY.glob("*.yaml"))


def cluster_candidate_paths() -> list[Path]:
    return sorted(REVIEW_CLUSTER.glob("*.yaml"))


def all_candidate_paths() -> list[Path]:
    return candidate_paths() + cluster_candidate_paths()


def test_the_review_queue_is_committed_and_is_not_a_pack_layer() -> None:
    assert candidate_paths(), (
        "the review queue must hold candidates for this guard to mean anything"
    )
    assert cluster_candidate_paths(), (
        "the review queue must hold cluster candidates for this guard to mean anything"
    )
    assert REVIEW_ROOT.name == REVIEW_QUEUE_DIRNAME
    assert REVIEW_QUEUE_DIRNAME not in {layer.value for layer in PackLayer}


def test_the_cluster_queue_holds_one_candidate_per_intake_cluster(taxonomy: Taxonomy) -> None:
    expected = {cluster.pack for cluster in taxonomy.clusters if cluster.pack is not None}
    ids = {load_pack(path).id for path in cluster_candidate_paths()}
    assert ids == expected
    for path in cluster_candidate_paths():
        assert load_pack(path).layer is PackLayer.CLUSTER, path.name


def test_served_registry_never_holds_a_review_candidate(served: PackRegistry) -> None:
    for path in candidate_paths():
        candidate = load_pack(path)
        registered = served.maybe(candidate.id)
        assert registered is not None, f"{path.name}: candidate has no served draft"
        assert registered == load_pack(SERVED_SPECIALTY / path.name)
        assert registered != candidate, f"{path.name}: the served registry holds the candidate"


def test_served_registry_never_holds_a_cluster_candidate(served: PackRegistry) -> None:
    for path in cluster_candidate_paths():
        candidate = load_pack(path)
        registered = served.maybe(candidate.id)
        if (SERVED_CLUSTER / path.name).exists():
            assert registered == load_pack(SERVED_CLUSTER / path.name)
        else:
            assert registered is None, f"{path.name}: served without a served cluster pack"
        assert registered != candidate, f"{path.name}: the served registry holds the candidate"


def test_resolve_branch_never_returns_a_cluster_candidate(
    served: PackRegistry, taxonomy: Taxonomy
) -> None:
    candidates = [load_pack(path) for path in cluster_candidate_paths()]
    intake_clusters = {cluster.id for cluster in taxonomy.clusters if cluster.intake}
    for branch in taxonomy.branches:
        if branch.cluster not in intake_clusters:
            continue
        try:
            row = resolve_branch(served, taxonomy, branch.id)
        except (L0PackServedError, NoServablePackError):
            continue
        assert row.pack_id is not None
        assert served.get(row.pack_id) not in candidates, f"{branch.id} resolved to a candidate"


def test_resolve_branch_never_returns_a_review_candidate(
    served: PackRegistry, taxonomy: Taxonomy
) -> None:
    candidates = [load_pack(path) for path in candidate_paths()]
    for path, candidate in zip(candidate_paths(), candidates, strict=True):
        try:
            row = resolve_branch(served, taxonomy, path.stem)
        except L0PackServedError:
            continue
        assert row.pack_id is not None
        assert served.get(row.pack_id) not in candidates, f"{path.stem} resolved to a candidate"
        assert served.get(row.pack_id) != candidate


def test_every_candidate_is_l0_unsigned_and_refused_by_the_compiler() -> None:
    for path in all_candidate_paths():
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "clinical_signoff" not in raw, (
            f"{path.name}: a signed candidate belongs in promotion"
        )
        pack = load_pack(path)
        assert pack.maturity is Maturity.L0, f"{path.name}: only promotion may write L1"
        assert pack.red_flags, f"{path.name}: the branch red-flag stub is missing"
        for rule in pack.red_flags:
            assert rule.status is RuleStatus.DRAFT_NEEDS_SOURCE, f"{path.name}: {rule.id}"
        assert not pack_compilable(pack).fully_compilable, path.name


def test_a_candidate_registered_on_purpose_still_raises(taxonomy: Taxonomy) -> None:
    for path in candidate_paths():
        registry = PackRegistry()
        registry.add(load_pack(path))
        with pytest.raises(L0PackServedError):
            resolve_branch(registry, taxonomy, path.stem)


def test_a_cluster_candidate_registered_on_purpose_still_raises(taxonomy: Taxonomy) -> None:
    for path in cluster_candidate_paths():
        candidate = load_pack(path)
        registry = PackRegistry()
        registry.add(candidate)
        cluster_ids = {cluster.id for cluster in taxonomy.clusters if cluster.pack == candidate.id}
        branches = [branch for branch in taxonomy.branches if branch.cluster in cluster_ids]
        assert branches, f"{path.name}: no branch maps to {candidate.id}"
        for branch in branches:
            with pytest.raises(L0PackServedError):
                resolve_branch(registry, taxonomy, branch.id)


def test_load_registry_refuses_the_review_queue_as_a_packs_root() -> None:
    with pytest.raises(ReviewQueueRootError):
        load_registry(REVIEW_ROOT)
    assert issubclass(ReviewQueueRootError, PackSchemaError)


def _minimal_pack(pack_id: str) -> ProtocolPack:
    return ProtocolPack(
        kind="pack",
        id=pack_id,
        layer=PackLayer.SPECIALTY,
        version="0.1.0",
        schema_version=2,
        maturity=Maturity.L0,
        status="synthetic-test-pack",
        language="tr",
    )


@pytest.mark.parametrize("root_name", ["reviewed", "review_notes", "packs"])
def test_near_miss_root_names_still_load(tmp_path: Path, root_name: str) -> None:
    root = tmp_path / root_name
    (root / PackLayer.SPECIALTY.value).mkdir(parents=True)
    pack = _minimal_pack("specialty.ornek")
    document = pack.model_dump(mode="json", exclude_none=True)
    (root / PackLayer.SPECIALTY.value / "ornek.yaml").write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    registry = load_registry(root)
    assert [p.id for p in registry] == ["specialty.ornek"]


def test_a_symlinked_review_queue_is_refused_too(tmp_path: Path) -> None:
    alias = tmp_path / "packs"
    alias.symlink_to(REVIEW_ROOT, target_is_directory=True)
    with pytest.raises(ReviewQueueRootError):
        load_registry(alias)


def _served_base_root(tmp_path: Path) -> Path:
    root = tmp_path / "packs"
    root.mkdir()
    (root / PackLayer.BASE.value).symlink_to(
        PACKAGE_ROOT / PackLayer.BASE.value, target_is_directory=True
    )
    return root


@pytest.mark.parametrize("layer", [PackLayer.CLUSTER, PackLayer.SPECIALTY])
def test_a_layer_linked_into_the_review_queue_is_refused(tmp_path: Path, layer: PackLayer) -> None:
    root = _served_base_root(tmp_path)
    (root / layer.value).symlink_to(REVIEW_ROOT / layer.value, target_is_directory=True)
    with pytest.raises(ReviewQueueRootError):
        load_registry(root)


def test_a_single_candidate_linked_into_a_served_layer_is_refused(tmp_path: Path) -> None:
    root = _served_base_root(tmp_path)
    layer_dir = root / PackLayer.CLUSTER.value
    layer_dir.mkdir()
    candidate = cluster_candidate_paths()[0]
    (layer_dir / candidate.name).symlink_to(candidate)
    with pytest.raises(ReviewQueueRootError):
        load_registry(root)


def test_a_layer_linked_to_the_served_tree_still_loads(tmp_path: Path) -> None:
    root = _served_base_root(tmp_path)
    (root / PackLayer.SPECIALTY.value).symlink_to(SERVED_SPECIALTY, target_is_directory=True)
    registry = load_registry(root)
    served_ids = {
        pack.id
        for pack in load_registry(PACKAGE_ROOT)
        if pack.layer in {PackLayer.BASE, PackLayer.SPECIALTY}
    }
    assert {pack.id for pack in registry} == served_ids
