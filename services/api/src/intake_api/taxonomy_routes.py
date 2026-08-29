"""INT-134 — the versioned branch-taxonomy feed (files/09 §1 projection).

``GET /v1/taxonomy/branches`` serves the mobile branch picker: every
cluster and branch from ``packages/protocols/taxonomy/branches.yaml``,
``name_tr`` verbatim (invariant 5 — the taxonomy's own tr names are the
labels), plus the content-hash ``version`` a client caches last-good
against.

Consent posture, decided rather than defaulted: this route reads NO
patient data — it projects a committed artefact — so it declares the
``reference_data`` marker to the scan (caged to /v1/taxonomy) instead of
over-claiming a clinical consent scope. Authentication still applies
(``Principal``), and reads are not audited: invariant 4 audits reads and
shares of clinical data, and a branch list contains none.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from intake_api.auth import Principal
from intake_api.consent_guard import reference_data
from intake_api.errors import taxonomy_unconfigured
from intake_api.state import State

__all__ = ["router"]

router = APIRouter(prefix="/v1/taxonomy", tags=["taxonomy"])


class ClusterOut(BaseModel):
    id: str
    pack: str | None
    intake: bool


class BranchOut(BaseModel):
    id: str
    name_tr: str
    cluster: str
    visit_types: list[str]


class TaxonomyFeedOut(BaseModel):
    version: str
    verify_live_list: bool
    clusters: list[ClusterOut]
    branches: list[BranchOut]


@router.get("/branches", response_model=TaxonomyFeedOut, dependencies=[reference_data()])
async def list_branches(_principal: Principal, state: State) -> TaxonomyFeedOut:
    loaded = state.taxonomy()
    if loaded is None:
        raise taxonomy_unconfigured()
    taxonomy = loaded.taxonomy
    return TaxonomyFeedOut(
        version=loaded.version,
        verify_live_list=taxonomy.verify_live_list,
        clusters=[
            ClusterOut(id=cluster.id, pack=cluster.pack, intake=cluster.intake)
            for cluster in taxonomy.clusters
        ],
        branches=[
            BranchOut(
                id=branch.id,
                name_tr=branch.name_tr,
                cluster=branch.cluster,
                visit_types=[visit_type.value for visit_type in branch.visit_types],
            )
            for branch in taxonomy.branches
        ],
    )
