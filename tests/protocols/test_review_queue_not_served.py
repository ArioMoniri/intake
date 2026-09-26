"""INT-353 — the specialty review queue is never a served pack.

``packages/protocols/review/specialty/`` holds QUESTIONS-authored candidates
that await the physician of record's sign-off (HB-C1). Their pack ids are the
served drafts' own ids (``specialty.<branch>``), so the only thing standing
between a candidate and a live session is where the registry reads from and
what maturity the candidate carries. Both are pinned here:

- the served registry reads the files/12 §1 layer directories only, and no
  layer is the review queue, so ``resolve_branch`` never sees a candidate;
- ``load_registry`` refuses the review queue itself as a packs root, so a
  mistyped ``--packs`` fails closed instead of serving candidates (a root
  whose name merely contains the word still loads — the near-miss control);
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
SERVED_SPECIALTY = PACKAGE_ROOT / "specialty"
TAXONOMY_PATH = PACKAGE_ROOT / "taxonomy" / "branches.yaml"


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    return load_taxonomy(TAXONOMY_PATH)


@pytest.fixture(scope="module")
def served() -> PackRegistry:
    return load_registry(PACKAGE_ROOT)


def candidate_paths() -> list[Path]:
    return sorted(REVIEW_SPECIALTY.glob("*.yaml"))


def test_the_review_queue_is_committed_and_is_not_a_pack_layer() -> None:
    assert candidate_paths(), (
        "the review queue must hold candidates for this guard to mean anything"
    )
    assert REVIEW_ROOT.name == REVIEW_QUEUE_DIRNAME
    assert REVIEW_QUEUE_DIRNAME not in {layer.value for layer in PackLayer}


def test_served_registry_never_holds_a_review_candidate(served: PackRegistry) -> None:
    for path in candidate_paths():
        candidate = load_pack(path)
        registered = served.maybe(candidate.id)
        assert registered is not None, f"{path.name}: candidate has no served draft"
        assert registered == load_pack(SERVED_SPECIALTY / path.name)
        assert registered != candidate, f"{path.name}: the served registry holds the candidate"


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
    for path in candidate_paths():
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
