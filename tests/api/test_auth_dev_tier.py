"""INT-197 — dev-bearer auth: exactly two synthetic accounts, fail closed.

What this file pins:
- tokens come from the environment ONLY (`INTAKE_DEV_TOKEN_PATIENT` /
  `INTAKE_DEV_TOKEN_ADMIN`); with either unset every /v1 route answers 503 —
  fail closed, never a baked-in default;
- every response — success and refusal alike — carries
  ``X-Intake-Auth-Tier: dev`` so no caller can mistake this tier for the real
  OIDC auth (INT-131);
- a wrong or missing bearer is 401; the admin account cannot write patient
  data (403).
"""

from __future__ import annotations

from api_harness import ApiHarness

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}


def test_missing_bearer_is_401_and_still_tagged_dev_tier(harness: ApiHarness) -> None:
    response = harness.client.get("/v1/visits")
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert response.headers["x-intake-auth-tier"] == "dev"


def test_wrong_bearer_is_401(harness: ApiHarness) -> None:
    response = harness.client.get("/v1/visits", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_patient_bearer_resolves_and_lists_own_visits(harness: ApiHarness) -> None:
    response = harness.client.get("/v1/visits", headers=harness.patient())
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["x-intake-auth-tier"] == "dev"


def test_admin_bearer_resolves(harness: ApiHarness) -> None:
    response = harness.client.get("/v1/visits", headers=harness.admin())
    assert response.status_code == 200


def test_admin_cannot_create_visits(harness: ApiHarness) -> None:
    response = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.admin())
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}


def test_unset_tokens_fail_closed_with_503(unconfigured_harness: ApiHarness) -> None:
    client = unconfigured_harness.client
    for headers in ({}, {"Authorization": "Bearer anything"}):
        response = client.get("/v1/visits", headers=headers)
        assert response.status_code == 503
        assert response.json() == {"error": "dev_auth_unconfigured"}
        assert response.headers["x-intake-auth-tier"] == "dev"


def test_unset_tokens_flip_readiness(unconfigured_harness: ApiHarness) -> None:
    response = unconfigured_harness.client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["dev_auth"] == "error"


def test_health_endpoints_need_no_auth(harness: ApiHarness) -> None:
    for path in ("/healthz", "/readyz", "/version", "/metrics"):
        assert harness.client.get(path).status_code == 200
