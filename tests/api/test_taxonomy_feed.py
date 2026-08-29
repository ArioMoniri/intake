"""INT-134 — the versioned branch-taxonomy feed the mobile picker eats.

What this file pins:
- GET /v1/taxonomy/branches serves a faithful projection of
  packages/protocols/taxonomy/branches.yaml (files/09 §1 source of truth):
  every cluster, every branch, ``name_tr`` verbatim (invariant 5 — the
  taxonomy's own tr names ARE the labels), visit types per branch;
- the feed is VERSIONED: ``version`` is the sha256 of the served file's
  bytes, so a client can cache last-good and detect change honestly;
- the route declares itself to the consent scan as REFERENCE DATA — it
  reads no patient data, so requiring a health-data consent scope would be
  an over-claim; the marker is caged to /v1/taxonomy exactly like the
  pre_auth and consent_management markers are caged to their prefixes, so
  no data route elsewhere can borrow it (unguarded_data_routes stays the
  authority and still returns []);
- the route still requires an authenticated principal (401 bare), and a
  read is NOT audited — invariant 4 covers reads of clinical data, and a
  branch list contains none;
- an absent/broken taxonomy file fails CLOSED: 503 ``taxonomy_unconfigured``,
  never an empty list a picker would render as "no branches exist".
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness
from intake_api.consent_guard import (
    REFERENCE_DATA_PREFIX,
    reference_data,
    reference_data_routes,
    unguarded_data_routes,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = REPO_ROOT / "packages" / "protocols" / "taxonomy" / "branches.yaml"

# files/09 §1: nine clusters; 92 seeded branches (88 full-set + Anesteziyoloji
# preop-only + Sağlık Kurulu / Adli Tıp report-only + Acil Tıp excluded).
CLUSTER_COUNT = 9
BRANCH_COUNT = 92

ALL_VISIT_TYPES = [
    "first",
    "followup",
    "preop",
    "report",
    "pregnancy_followup",
    "chronic_review",
    "post_discharge",
    "screening",
    "second_opinion",
    "teleconsult",
]


def _feed(harness: ApiHarness) -> dict[str, object]:
    response = harness.client.get("/v1/taxonomy/branches", headers=harness.patient())
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_feed_requires_an_authenticated_principal(harness: ApiHarness) -> None:
    assert harness.client.get("/v1/taxonomy/branches").status_code == 401
    assert (
        harness.client.get(
            "/v1/taxonomy/branches", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )


def test_feed_serves_every_cluster_and_branch_from_the_yaml(harness: ApiHarness) -> None:
    body = _feed(harness)
    clusters = body["clusters"]
    branches = body["branches"]
    assert isinstance(clusters, list) and len(clusters) == CLUSTER_COUNT
    assert isinstance(branches, list) and len(branches) == BRANCH_COUNT
    assert body["verify_live_list"] is True  # HB-A11 still open — say so honestly

    by_id = {str(entry["id"]): entry for entry in branches}
    # tr labels come from the taxonomy's own names, verbatim (invariant 5)
    assert by_id["kardiyoloji"]["name_tr"] == "Kardiyoloji"
    assert by_id["kardiyoloji"]["cluster"] == "medical"
    assert by_id["kardiyoloji"]["visit_types"] == ALL_VISIT_TYPES
    assert by_id["deri_ve_zuhrevi_hastaliklari"]["name_tr"] == "Deri ve Zührevi Hastalıkları"
    # restricted visit-type branches survive the projection exactly
    assert by_id["anesteziyoloji"]["visit_types"] == ["preop"]
    assert by_id["saglik_kurulu"]["visit_types"] == ["report"]
    # the excluded branch is served (the client must KNOW it books no intake)
    assert by_id["acil_tip"]["cluster"] == "excluded"
    assert by_id["acil_tip"]["visit_types"] == []

    cluster_by_id = {str(entry["id"]): entry for entry in clusters}
    assert cluster_by_id["medical"]["pack"] == "cluster.medical"
    assert cluster_by_id["medical"]["intake"] is True
    assert cluster_by_id["excluded"]["pack"] is None
    assert cluster_by_id["excluded"]["intake"] is False


def test_feed_version_is_the_sha256_of_the_served_file(harness: ApiHarness) -> None:
    body = _feed(harness)
    expected = hashlib.sha256(TAXONOMY_PATH.read_bytes()).hexdigest()
    assert body["version"] == expected
    # stable across requests — the cache key a client can trust
    assert _feed(harness)["version"] == expected


def test_feed_is_readable_by_the_admin_principal_too(harness: ApiHarness) -> None:
    response = harness.client.get("/v1/taxonomy/branches", headers=harness.admin())
    assert response.status_code == 200


def test_feed_reads_are_not_audited(harness: ApiHarness) -> None:
    before = len(harness.audit_store.entries())
    _feed(harness)
    # invariant 4 audits reads/shares of CLINICAL data; a branch list has none
    assert len(harness.audit_store.entries()) == before


def test_feed_route_carries_the_reference_data_declaration(harness: ApiHarness) -> None:
    app = harness.client.app
    assert reference_data_routes(app) == ["GET /v1/taxonomy/branches"]
    assert all(
        route.split(" ", 1)[1].startswith(REFERENCE_DATA_PREFIX)
        for route in reference_data_routes(app)
    )
    # with the marker accepted, the whole surface still scans clean
    assert unguarded_data_routes(app) == []


def test_reference_data_marker_outside_its_prefix_is_not_a_declaration() -> None:
    """A data route elsewhere cannot borrow the reference-data marker to
    dodge the scan — outside /v1/taxonomy it still counts as unguarded."""
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/v1/sneaky", dependencies=[reference_data()])
    async def sneaky() -> dict[str, str]:
        return {"ok": "no"}

    @app.get("/v1/taxonomyish", dependencies=[reference_data()])
    async def lookalike() -> dict[str, str]:
        return {"ok": "no"}

    assert sorted(unguarded_data_routes(app)) == ["GET /v1/sneaky", "GET /v1/taxonomyish"]


def test_missing_taxonomy_file_fails_closed(tmp_path: Path) -> None:
    generator = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        taxonomy_path=tmp_path / "no-taxonomy-here.yaml",
    )
    harness = next(generator)
    try:
        response = harness.client.get("/v1/taxonomy/branches", headers=harness.patient())
        assert response.status_code == 503
        assert response.json() == {"error": "taxonomy_unconfigured"}
    finally:
        for _ in generator:  # drive the generator's teardown
            pass


def test_invalid_taxonomy_file_fails_closed(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("clusters: [not, a, taxonomy]\n", encoding="utf-8")
    generator = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        taxonomy_path=broken,
    )
    harness = next(generator)
    try:
        response = harness.client.get("/v1/taxonomy/branches", headers=harness.patient())
        assert response.status_code == 503
        assert response.json() == {"error": "taxonomy_unconfigured"}
    finally:
        for _ in generator:
            pass
