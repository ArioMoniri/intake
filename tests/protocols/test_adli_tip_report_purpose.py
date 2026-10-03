"""INT-469 — Adli Tıp does not inherit the allied cluster's report-purpose item.

``specialty.adli_tip`` extends ``cluster.allied_and_reports``, which asks
``rapor_amaci`` (the purpose of the requested report) of every allied branch.
For a forensic visit that purpose belongs to the authority that requested the
report, not to the person examined, so the adli_tip candidate removes the
inherited slot with one ``suppress_slot`` op. The generator emits that op from
the proposal's ``pack: suppress=`` line; the candidate is never edited by hand.

Pinned here, against the committed candidates and the real resolver:

- the merged adli_tip pack (the chain plus every op of every layer, as the
  resolver hands it to its rule-read check) declares no ``rapor_amaci``, and
  the op that removed it is adli_tip's own;
- exactly that slot is removed: every other cluster report item stays;
- near miss: Sağlık Kurulu, the five other allied branches and the cluster
  itself still carry ``rapor_amaci``;
- the resolution head never hands an Adli Tıp booking a pack that asks the
  report purpose. Nothing is served today; a cluster promoted ahead of
  adli_tip (synthetic) is caught, and the near miss is that the other allied
  branches may still fall back to it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from protocols import (
    BranchResolutionError,
    Maturity,
    PackRegistry,
    ProtocolPack,
    ResolutionStatus,
    SuppressSlotOp,
    Taxonomy,
    load_pack,
    load_taxonomy,
    resolve_branch,
)
from protocols.bindings import OperationalTemplate
from protocols.cli import load_registry
from protocols.compile import (
    CompileError,
    LifeThreatSet,
    Refusal,
    load_life_threat_set,
    resolve_protocol,
)
from protocols.compile import resolve as resolve_module
from protocols.compile.rule_reads import rule_read_refusals

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOLS = REPO_ROOT / "packages" / "protocols"
BASE_INTAKE = PROTOCOLS / "base" / "intake.yaml"
REVIEW_SPECIALTY = PROTOCOLS / "review" / "specialty"
ALLIED_CLUSTER = PROTOCOLS / "review" / "cluster" / "allied_and_reports.yaml"
REAL_LIFE_THREAT = REPO_ROOT / "files" / "protocols" / "base.life_threat.yaml"
TAXONOMY = load_taxonomy(PROTOCOLS / "taxonomy" / "branches.yaml")

CLUSTER_ID = "cluster.allied_and_reports"
ADLI_TIP = "adli_tip"
REPORT_PURPOSE = ("sorular", "rapor_amaci")
REPORT_PURPOSE_POINTER = "/sections/sorular/slots/rapor_amaci"
ALLIED_BRANCHES = sorted(b.id for b in TAXONOMY.branches if b.cluster == "allied_and_reports")
OTHER_ALLIED = [b for b in ALLIED_BRANCHES if b != ADLI_TIP]


def _allied_registry() -> PackRegistry:
    registry = PackRegistry()
    registry.add(load_pack(BASE_INTAKE))
    registry.add(load_pack(ALLIED_CLUSTER))
    for branch in ALLIED_BRANCHES:
        registry.add(load_pack(REVIEW_SPECIALTY / f"{branch}.yaml"))
    return registry


REVIEW = _allied_registry()


@pytest.fixture(scope="module")
def real_life_threat() -> LifeThreatSet:
    return load_life_threat_set(REAL_LIFE_THREAT)


class _Merged:
    """What the resolver handed its rule-read check: the merged pack's slots
    and the suppressions every layer applied to reach it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> list[Refusal]:
        kwargs["declared"] = frozenset(kwargs["declared"])
        kwargs["suppressions"] = frozenset(kwargs["suppressions"])
        self.calls.append(kwargs)
        return rule_read_refusals(**kwargs)


Merge = Callable[[str], dict[str, Any]]


@pytest.fixture
def merged_of(
    monkeypatch: pytest.MonkeyPatch,
    real_life_threat: LifeThreatSet,
    template: OperationalTemplate,
) -> Merge:
    def _merged(pack_id: str) -> dict[str, Any]:
        spy = _Merged()
        monkeypatch.setattr(resolve_module, "rule_read_refusals", spy)
        with pytest.raises(CompileError):
            resolve_protocol(
                pack_id=pack_id,
                registry=REVIEW,
                life_threat=real_life_threat,
                template=template,
            )
        assert len(spy.calls) == 1, f"{pack_id}: an op did not apply, so nothing merged"
        return spy.calls[0]

    return _merged


def test_the_allied_cluster_has_seven_branches_and_carries_the_report_purpose() -> None:
    assert len(ALLIED_BRANCHES) == 7
    assert ADLI_TIP in ALLIED_BRANCHES and "saglik_kurulu" in OTHER_ALLIED
    assert REPORT_PURPOSE[1] in REVIEW.get(CLUSTER_ID).sections["sorular"].slots
    for branch in ALLIED_BRANCHES:
        assert REVIEW.get(f"specialty.{branch}").extends == CLUSTER_ID


def test_the_resolved_adli_tip_pack_has_no_report_purpose_item(merged_of: Merge) -> None:
    merged = merged_of(f"specialty.{ADLI_TIP}")
    assert REPORT_PURPOSE not in merged["declared"]
    assert merged["suppressions"] == {(f"specialty.{ADLI_TIP}", REPORT_PURPOSE_POINTER)}


def test_exactly_the_report_purpose_is_removed_and_the_other_report_items_stay(
    merged_of: Merge,
) -> None:
    adli = merged_of(f"specialty.{ADLI_TIP}")["declared"]
    cluster = merged_of(CLUSTER_ID)["declared"]
    own = {
        (section_id, key)
        for section_id, section in REVIEW.get(f"specialty.{ADLI_TIP}").sections.items()
        for key in section.slots
    }
    assert adli == (cluster | own) - {REPORT_PURPOSE}
    for key in ("rapor_icin_basvuru", "kurum_sevk_yazisi", "kisisel_saglik_bilgi_formu"):
        assert ("sorular", key) in adli


@pytest.mark.parametrize("branch", OTHER_ALLIED)
def test_near_miss_the_other_allied_branches_keep_the_report_purpose(
    branch: str, merged_of: Merge
) -> None:
    merged = merged_of(f"specialty.{branch}")
    assert REPORT_PURPOSE in merged["declared"]
    assert merged["suppressions"] == frozenset()


def test_near_miss_the_cluster_itself_keeps_the_report_purpose(merged_of: Merge) -> None:
    assert REPORT_PURPOSE in merged_of(CLUSTER_ID)["declared"]


def test_near_miss_six_other_allied_branches_are_checked() -> None:
    assert len(OTHER_ALLIED) == 6


# --- the resolution head ------------------------------------------------------


def _chain(registry: PackRegistry, pack: ProtocolPack) -> list[ProtocolPack]:
    chain = [pack]
    while chain[-1].extends is not None:
        chain.append(registry.get(chain[-1].extends))
    return chain


def _runs_the_report_purpose(registry: PackRegistry, taxonomy: Taxonomy, branch_id: str) -> bool:
    """True when a live booking for the branch would resolve to a pack whose
    chain declares the report purpose and no layer suppresses it."""
    try:
        row = resolve_branch(registry, taxonomy, branch_id)
    except BranchResolutionError:
        return False
    assert row.pack_id is not None
    chain = _chain(registry, registry.get(row.pack_id))
    section_id, key = REPORT_PURPOSE
    declared = any(
        section_id in pack.sections and key in pack.sections[section_id].slots for pack in chain
    )
    suppressed = any(
        isinstance(op, SuppressSlotOp) and op.pointer == REPORT_PURPOSE_POINTER
        for pack in chain
        for op in pack.ops
    )
    return declared and not suppressed


def _promoted(pack: ProtocolPack) -> ProtocolPack:
    return pack.model_copy(update={"maturity": Maturity.L1})


def _registry(*packs: ProtocolPack) -> PackRegistry:
    registry = PackRegistry()
    for pack in packs:
        registry.add(pack)
    return registry


def test_a_live_adli_tip_booking_never_runs_the_report_purpose_today() -> None:
    served = load_registry(PROTOCOLS)
    assert not _runs_the_report_purpose(served, TAXONOMY, ADLI_TIP)


def test_a_cluster_promoted_ahead_of_adli_tip_would_hand_it_the_report_purpose() -> None:
    base, cluster = REVIEW.get("base.intake"), REVIEW.get(CLUSTER_ID)
    adli = REVIEW.get(f"specialty.{ADLI_TIP}")
    early = _registry(base, _promoted(cluster), adli)
    row = resolve_branch(early, TAXONOMY, ADLI_TIP)
    assert row.status is ResolutionStatus.CLUSTER
    assert _runs_the_report_purpose(early, TAXONOMY, ADLI_TIP)


def test_adli_tip_promoted_with_its_suppression_does_not_run_the_report_purpose() -> None:
    base, cluster = REVIEW.get("base.intake"), REVIEW.get(CLUSTER_ID)
    adli = _promoted(REVIEW.get(f"specialty.{ADLI_TIP}"))
    signed = _registry(base, _promoted(cluster), adli)
    assert resolve_branch(signed, TAXONOMY, ADLI_TIP).status is ResolutionStatus.DIRECT
    assert not _runs_the_report_purpose(signed, TAXONOMY, ADLI_TIP)
    unsuppressed = _registry(base, _promoted(cluster), adli.model_copy(update={"ops": ()}))
    assert _runs_the_report_purpose(unsuppressed, TAXONOMY, ADLI_TIP)


@pytest.mark.parametrize("branch", OTHER_ALLIED)
def test_near_miss_other_allied_branches_may_fall_back_to_the_cluster(branch: str) -> None:
    base, cluster = REVIEW.get("base.intake"), REVIEW.get(CLUSTER_ID)
    early = _registry(base, _promoted(cluster), REVIEW.get(f"specialty.{branch}"))
    assert resolve_branch(early, TAXONOMY, branch).status is ResolutionStatus.CLUSTER
    assert _runs_the_report_purpose(early, TAXONOMY, branch)
