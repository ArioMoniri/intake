"""Branch taxonomy: loader, validation, resolution, coverage (INT-042).

The data file is ``packages/protocols/taxonomy/branches.yaml`` — files/09 §1
names it the source of truth, seeded from the MHRS branch registry with
``verify_live_list: true`` until the owner confirms the live list (HB-A11).

What is enforced here, each with its blueprint anchor:

- **Every branch resolves to a listed cluster** (files/09 §1: "every branch
  maps to exactly one cluster pack"); unknown cluster refs, duplicate ids
  and non-09-§1 visit types are refused at load.
- **Resolution order head** (files/03 §6; files/09 §1): a branch serves its
  own ``specialty.<branch_id>`` pack at L1+ when one exists, else its
  cluster's pack — "a real, reviewed protocol, not a fallback" (files/09
  §2). No patient ever runs on bare ``base.intake``.
- **Invariant 13** (CLAUDE.md): every branch resolves to an L1+ pack or its
  cluster pack (:func:`coverage` is the CI matrix), and an L0 pack resolved
  for a live session raises (:class:`L0PackServedError`) — L0 is generated,
  review-queue-only, never served (files/09 §2).
- **Unknown booked branch fails closed** (INT-042 acceptance): a resolution
  request for a branch id the taxonomy does not know raises
  :class:`UnknownBranchError` — an unmapped MHRS booking never silently
  runs any pack.
- **Acil Tıp is excluded** (files/09 §1 row 9; files/12 §1
  ``cluster.excluded``): pre-visit intake is never used for emergencies, so
  live resolution raises :class:`ExcludedBranchError` and the matrix shows
  ``EXCLUDED``, not ``MISSING``. ``base.life_threat`` still applies to every
  session as the sibling set outside this chain (files/12 §1).
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Annotated

import yaml
from clinical_schemas.common import FrozenModel
from pydantic import Field, StringConstraints, ValidationError, model_validator

from protocols.loader import PackRegistry
from protocols.pack import ProtocolPack
from protocols.types import Maturity, VisitType

__all__ = [
    "Branch",
    "BranchResolution",
    "BranchResolutionError",
    "Cluster",
    "ExcludedBranchError",
    "L0PackServedError",
    "NoServablePackError",
    "ResolutionStatus",
    "Taxonomy",
    "TaxonomyError",
    "UnknownBranchError",
    "coverage",
    "direct_pack_id",
    "load_taxonomy",
    "resolve_branch",
]

TaxonId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
ClusterPackId = Annotated[str, StringConstraints(pattern=r"^cluster\.[a-z][a-z0-9_]*$")]


class TaxonomyError(ValueError):
    """A taxonomy file the schema or cross-checks reject (one error type at
    the load boundary, mirroring :class:`protocols.loader.PackSchemaError`)."""


class BranchResolutionError(Exception):
    """Base of the live-session resolution failures — every subclass exists
    so a session fails closed instead of running the wrong (or no) pack."""


class UnknownBranchError(BranchResolutionError):
    """A booked branch id the taxonomy does not know (INT-042 acceptance:
    this is what protects a live session from an unmapped MHRS booking)."""


class ExcludedBranchError(BranchResolutionError):
    """A branch in a non-intake cluster (Acil Tıp): pre-visit intake is
    never used for emergencies — RED routing only (files/09 §1)."""


class L0PackServedError(BranchResolutionError):
    """An L0 pack would have served a live session (CLAUDE.md invariant 13;
    files/09 §2: L0 is generated, review queue only, never served)."""


class NoServablePackError(BranchResolutionError):
    """No L1+ pack exists for the branch or its cluster — the session fails
    closed rather than running bare ``base.intake`` (files/09 §1)."""


class Cluster(FrozenModel):
    """One of the nine files/09 §1 clusters."""

    id: TaxonId = Field(description="Cluster id, verbatim from files/09 §1.")
    pack: ClusterPackId | None = Field(
        default=None,
        description="The cluster pack every member branch falls back to "
        "(files/09 §1); None only for a non-intake cluster.",
    )
    intake: bool = Field(
        default=True,
        description="False only for `excluded` — pre-visit intake is never "
        "used for emergencies (files/09 §1 row 9).",
    )

    @model_validator(mode="after")
    def _pack_matches_intake(self) -> Cluster:
        if self.intake and self.pack is None:
            raise ValueError(
                f"intake cluster {self.id!r} must bind a cluster pack — no patient "
                "ever runs on bare base.intake (files/09 §1)"
            )
        if not self.intake and self.pack is not None:
            raise ValueError(
                f"non-intake cluster {self.id!r} may not bind an intake pack "
                "(files/09 §1: RED routing only)"
            )
        return self


class Branch(FrozenModel):
    """One bookable MHRS branch or hospital-specific clinic (files/09 §1)."""

    id: TaxonId = Field(description="Branch id (slug of the booked Turkish name).")
    name_tr: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="Turkish name as booked (files/09 §1, verbatim)."
    )
    cluster: TaxonId = Field(description="The one cluster this branch maps to (files/09 §1).")
    visit_types: tuple[VisitType, ...] = Field(
        description="Visit types this branch books — members of the "
        "files/09 §1 set only, empty only for an excluded branch."
    )


class Taxonomy(FrozenModel):
    """The whole ``branches.yaml`` document, cross-checked."""

    verify_live_list: bool = Field(
        description="True while the seed awaits confirmation against the "
        "live MHRS/SKRS list (HB-A11); the seed remains the build target."
    )
    clusters: tuple[Cluster, ...] = Field(description="The files/09 §1 cluster set.")
    branches: tuple[Branch, ...] = Field(description="Every bookable branch (files/09 §1).")

    @model_validator(mode="after")
    def _cross_checks(self) -> Taxonomy:
        cluster_ids: set[str] = set()
        for cluster in self.clusters:
            if cluster.id in cluster_ids:
                raise ValueError(f"duplicate cluster id {cluster.id!r}")
            cluster_ids.add(cluster.id)
        by_id = {cluster.id: cluster for cluster in self.clusters}
        branch_ids: set[str] = set()
        for branch in self.branches:
            if branch.id in branch_ids:
                raise ValueError(f"duplicate branch id {branch.id!r}")
            branch_ids.add(branch.id)
            owner = by_id.get(branch.cluster)
            if owner is None:
                raise ValueError(
                    f"branch {branch.id!r} references unknown cluster "
                    f"{branch.cluster!r} — every branch maps to exactly one "
                    "listed cluster (files/09 §1)"
                )
            if owner.intake and not branch.visit_types:
                raise ValueError(
                    f"branch {branch.id!r} must book at least one visit type "
                    "(files/09 §1); only an excluded branch books none"
                )
            if not owner.intake and branch.visit_types:
                raise ValueError(
                    f"excluded branch {branch.id!r} may not book intake visit "
                    "types (files/09 §1: RED routing only)"
                )
        return self

    def cluster_of(self, branch: Branch) -> Cluster:
        """The branch's cluster — total, because ``_cross_checks`` proved it."""
        return next(cluster for cluster in self.clusters if cluster.id == branch.cluster)

    def branch(self, branch_id: str) -> Branch:
        """The branch for a booked id, or :class:`UnknownBranchError`."""
        for branch in self.branches:
            if branch.id == branch_id:
                return branch
        raise UnknownBranchError(
            f"booked branch {branch_id!r} is not in the taxonomy — an unmapped "
            "MHRS booking must fail closed, never run an arbitrary pack "
            "(INT-042 acceptance; HB-A11)"
        )


def load_taxonomy(path: Path) -> Taxonomy:
    """Load and validate ``branches.yaml``; every failure is a
    :class:`TaxonomyError`. Top-level keys starting with ``_`` are YAML
    anchor scaffolding (``_all_visit_types``) and carry no data."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise TaxonomyError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise TaxonomyError(f"{path}: the taxonomy document must be a YAML mapping")
    payload = {key: value for key, value in raw.items() if not str(key).startswith("_")}
    try:
        return Taxonomy.model_validate(payload)
    except ValidationError as exc:
        raise TaxonomyError(f"{path}: {exc}") from exc


class ResolutionStatus(enum.StrEnum):
    """How (whether) a branch resolves to a servable pack (invariant 13)."""

    DIRECT = "DIRECT"
    CLUSTER = "CLUSTER"
    MISSING = "MISSING"
    EXCLUDED = "EXCLUDED"


class BranchResolution(FrozenModel):
    """One row of the branch × resolution matrix."""

    branch_id: str = Field(description="The booked branch.")
    name_tr: str = Field(description="Turkish name as booked (files/09 §1).")
    cluster: str = Field(description="The branch's cluster.")
    status: ResolutionStatus = Field(description="DIRECT | CLUSTER | MISSING | EXCLUDED.")
    pack_id: str | None = Field(
        default=None, description="The servable pack, present only for DIRECT/CLUSTER."
    )
    note: str = Field(default="", description="Why, when the status needs explaining.")


def direct_pack_id(branch_id: str) -> str:
    """The id a branch's own pack carries: ``specialty.<branch_id>``
    (files/12 §1 directory layout; files/03 §6 ``specialty.X``)."""
    return f"specialty.{branch_id}"


def _servable(pack: ProtocolPack) -> bool:
    """L1+ only — an L0 pack is never coverage (files/09 §2)."""
    return pack.maturity is not Maturity.L0


def _candidates(
    packs: PackRegistry, taxonomy: Taxonomy, branch: Branch
) -> tuple[ProtocolPack | None, ProtocolPack | None]:
    cluster = taxonomy.cluster_of(branch)
    direct = packs.maybe(direct_pack_id(branch.id))
    cluster_pack = packs.maybe(cluster.pack) if cluster.pack is not None else None
    return direct, cluster_pack


def resolve_branch(packs: PackRegistry, taxonomy: Taxonomy, branch_id: str) -> BranchResolution:
    """Live-session resolution head: DIRECT (L1+ ``specialty.<id>``) else
    CLUSTER (the cluster pack) — every other outcome raises.

    Raises :class:`UnknownBranchError` (unmapped booking),
    :class:`ExcludedBranchError` (Acil Tıp), :class:`L0PackServedError`
    (invariant 13 — the pack that would have served is L0) or
    :class:`NoServablePackError` (nothing exists; never bare base.intake).
    """
    branch = taxonomy.branch(branch_id)
    cluster = taxonomy.cluster_of(branch)
    if not cluster.intake:
        raise ExcludedBranchError(
            f"branch {branch.id!r} is in the excluded cluster — pre-visit intake "
            "is never used for emergencies; RED routing only (files/09 §1)"
        )
    direct, cluster_pack = _candidates(packs, taxonomy, branch)
    if direct is not None and _servable(direct):
        return BranchResolution(
            branch_id=branch.id,
            name_tr=branch.name_tr,
            cluster=branch.cluster,
            status=ResolutionStatus.DIRECT,
            pack_id=direct.id,
        )
    if cluster_pack is not None and _servable(cluster_pack):
        note = ""
        if direct is not None:
            note = (
                f"L0 draft {direct.id} skipped — a branch without an L1 pack "
                "runs its cluster pack (files/09 §2)"
            )
        return BranchResolution(
            branch_id=branch.id,
            name_tr=branch.name_tr,
            cluster=branch.cluster,
            status=ResolutionStatus.CLUSTER,
            pack_id=cluster_pack.id,
            note=note,
        )
    l0 = next((pack for pack in (direct, cluster_pack) if pack is not None), None)
    if l0 is not None:
        raise L0PackServedError(
            f"only the L0 pack {l0.id!r} would resolve for branch {branch.id!r} "
            "— an L0 pack resolved for a live session raises (CLAUDE.md "
            "invariant 13; files/09 §2: L0 is never served)"
        )
    raise NoServablePackError(
        f"no L1+ pack exists for branch {branch.id!r} or its cluster "
        f"{branch.cluster!r} — failing closed; no patient ever runs on bare "
        "base.intake (files/09 §1)"
    )


def coverage(packs: PackRegistry, taxonomy: Taxonomy) -> tuple[BranchResolution, ...]:
    """The branch × resolution matrix (invariant 13; files/09 §6
    ``taxonomy_coverage``). Reporting only — it never raises for a gap: a
    branch that resolves to nothing is an honest ``MISSING`` row, and an L0
    draft is named in the note but never counted as coverage."""
    rows: list[BranchResolution] = []
    for branch in taxonomy.branches:
        cluster = taxonomy.cluster_of(branch)
        if not cluster.intake:
            rows.append(
                BranchResolution(
                    branch_id=branch.id,
                    name_tr=branch.name_tr,
                    cluster=branch.cluster,
                    status=ResolutionStatus.EXCLUDED,
                    note="pre-visit intake is never used for emergencies; "
                    "RED routing only (files/09 §1)",
                )
            )
            continue
        direct, cluster_pack = _candidates(packs, taxonomy, branch)
        served = (direct is not None and _servable(direct)) or (
            cluster_pack is not None and _servable(cluster_pack)
        )
        if served:
            rows.append(resolve_branch(packs, taxonomy, branch.id))
            continue
        drafts = [pack.id for pack in (direct, cluster_pack) if pack is not None]
        note = (
            f"only L0 draft(s) exist ({', '.join(drafts)}) — L0 is never served (files/09 §2)"
            if drafts
            else "no pack exists yet"
        )
        rows.append(
            BranchResolution(
                branch_id=branch.id,
                name_tr=branch.name_tr,
                cluster=branch.cluster,
                status=ResolutionStatus.MISSING,
                note=note,
            )
        )
    return tuple(rows)
