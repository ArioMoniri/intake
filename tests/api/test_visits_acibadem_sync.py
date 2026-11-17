"""INT-318 — POST /v1/visits/sync: a logged-in patient's own upcoming visits,
read from the Acıbadem feed after OTP verification.

Carried from int-demo (2402ff27, 8fd3a6e9). What this pins, one near-miss
control per test:

* the happy path — a verified phone that is a single feed match returns that
  patient's upcoming visits (past ones filtered) and their display name;
* **patient A cannot read patient B's visits** by submitting B's phone: the
  ownership guard refuses BEFORE the feed is touched (asserted by a request
  counter that stays at zero);
* a shared handset (one number, two patients, no TC to separate them) surfaces
  as a clean ``ambiguous`` — never one patient's visits shown to the other;
* a phone with no matching row returns an empty list, not an error;
* a phone whose only rows are in the past returns an empty list;
* an absent ``core`` consent is a 403 at the door (invariant 4), and the feed
  is never touched;
* every disclosure is written to the hash-chained audit (invariant 4);
* an upstream failure — a dropped link or a non-200 — is an honest
  ``upstream_unavailable`` with no visits, never a 500 that breaks the login.

The registry half of the route (the row comes only from
``infra/connectors/sources.yaml``) is pinned in test_visits_acibadem_registry.py.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from acibadem_sync_harness import (
    BEFORE_THE_VISITS,
    FATMA_PHONE,
    MEHMET_PHONE,
    SHARED_PHONE,
    UNKNOWN_PHONE,
    CountingFeed,
    DpopClient,
    SyncHarness,
    build_sync_harness,
)
from intake_api import visits_acibadem


@pytest.fixture()
def sync_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SyncHarness]:
    # the LanSourcePolicy runtime double-gate (the client would otherwise deny)
    monkeypatch.setenv("INTAKE_ALLOW_LAN_SOURCE", "explicit-yes")
    yield from build_sync_harness(tmp_path)


# --- the happy path -----------------------------------------------------------------------


def test_matched_phone_returns_its_own_upcoming_visits(
    sync_harness: SyncHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(visits_acibadem, "_today", lambda: BEFORE_THE_VISITS)
    dpop = DpopClient()
    bundle = sync_harness.sign_up(FATMA_PHONE, dpop)
    sync_harness.grant_core(bundle["patient_id"])

    response = sync_harness.sync(FATMA_PHONE, bundle["access_token"], dpop)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["outcome"] == "matched"
    assert body["patient_name"] == "Fatma Kaya"
    # the 2021 row is filtered; both 2026-09-05 visits survive, earliest first
    assert [(v["date"], v["time"], v["department"]) for v in body["visits"]] == [
        ("2026-09-05", "13:00", "Kardiyoloji"),
        ("2026-09-05", "13:05", "Kadın Hastalıkları ve Doğum"),
    ]
    assert all(v["noteStatus"] is None for v in body["visits"])
    # distinct ids for the two same-day visits (13:00 vs 13:05)
    assert len({v["id"] for v in body["visits"]}) == 2


def test_the_disclosure_is_audited_against_core(sync_harness: SyncHarness) -> None:
    dpop = DpopClient()
    bundle = sync_harness.sign_up(FATMA_PHONE, dpop)
    sync_harness.grant_core(bundle["patient_id"])
    sync_harness.sync(FATMA_PHONE, bundle["access_token"], dpop)

    entries = sync_harness.audit_store.entries()
    synced = [e for e in entries if e.action == "api.visit.acibadem.sync"]
    assert len(synced) == 1
    assert synced[0].actor == f"patient:{bundle['patient_id']}"
    # the test row's registered purpose is core, so the audit names core
    assert synced[0].consent_scope_ref == "scope:core"
    # the resolved hospital-side id is safe to log; the phone/name never are
    assert synced[0].resource_ref == "acibadem:40000003"


# --- the leak control: A cannot read B ----------------------------------------------------


def test_patient_a_cannot_read_b_by_submitting_bs_phone(sync_harness: SyncHarness) -> None:
    dpop = DpopClient()
    a = sync_harness.sign_up(FATMA_PHONE, dpop)  # A owns FATMA_PHONE
    sync_harness.grant_core(a["patient_id"])

    # A, authenticated as themselves, submits a DIFFERENT patient's number
    response = sync_harness.sync(MEHMET_PHONE, a["access_token"], dpop)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["outcome"] == "not_your_number"
    assert body["visits"] == []
    assert body["patient_name"] is None
    # the decisive property: the feed was never consulted for B's number
    assert sync_harness.feed.calls == []


# --- the shared handset: a clean refusal, never a guess -----------------------------------


def test_shared_handset_is_a_clean_refusal(sync_harness: SyncHarness) -> None:
    dpop = DpopClient()
    bundle = sync_harness.sign_up(SHARED_PHONE, dpop)  # 40000007 & 40000008 share it
    sync_harness.grant_core(bundle["patient_id"])

    response = sync_harness.sync(SHARED_PHONE, bundle["access_token"], dpop)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["outcome"] == "ambiguous"
    assert body["visits"] == []
    assert body["patient_name"] is None
    # the directory was read once; no per-patient fetch followed the refusal
    assert sync_harness.feed.calls == ["/api/v1/appointments/upcoming"]


# --- empties are not errors ---------------------------------------------------------------


def test_unknown_number_returns_empty_not_error(sync_harness: SyncHarness) -> None:
    dpop = DpopClient()
    bundle = sync_harness.sign_up(UNKNOWN_PHONE, dpop)
    sync_harness.grant_core(bundle["patient_id"])

    response = sync_harness.sync(UNKNOWN_PHONE, bundle["access_token"], dpop)
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "no_appointment"
    assert body["visits"] == []


def test_only_past_visits_returns_empty(
    sync_harness: SyncHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(visits_acibadem, "_today", lambda: dt.date(2027, 1, 1))
    dpop = DpopClient()
    bundle = sync_harness.sign_up(FATMA_PHONE, dpop)
    sync_harness.grant_core(bundle["patient_id"])

    response = sync_harness.sync(FATMA_PHONE, bundle["access_token"], dpop)
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "no_upcoming"
    assert body["visits"] == []


# --- consent (invariant 4) is enforced at the door ----------------------------------------


def test_absent_core_consent_is_refused_before_the_feed(sync_harness: SyncHarness) -> None:
    dpop = DpopClient()
    bundle = sync_harness.sign_up(FATMA_PHONE, dpop)  # NO grant_core

    response = sync_harness.sync(FATMA_PHONE, bundle["access_token"], dpop)
    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": "core"}
    assert sync_harness.feed.calls == []


# --- an upstream blip degrades to an honest empty result (8fd3a6e9) -----------------------


@pytest.mark.parametrize(
    "feed",
    [
        pytest.param(CountingFeed(fail_with=httpx.ConnectError), id="link-dropped"),
        pytest.param(CountingFeed(fail_with=httpx.ReadTimeout), id="read-timeout"),
        pytest.param(CountingFeed(status=503), id="upstream-503"),
    ],
)
def test_an_upstream_failure_is_upstream_unavailable_not_a_500(
    feed: CountingFeed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_LAN_SOURCE", "explicit-yes")
    for harness in build_sync_harness(tmp_path, feed=feed):
        dpop = DpopClient()
        bundle = harness.sign_up(FATMA_PHONE, dpop)
        harness.grant_core(bundle["patient_id"])

        response = harness.sync(FATMA_PHONE, bundle["access_token"], dpop)
        assert response.status_code == 200, response.text
        assert response.json() == {
            "outcome": "upstream_unavailable",
            "patient_name": None,
            "visits": [],
        }
        # the directory read was attempted once and nothing followed it
        assert harness.feed.calls == ["/api/v1/appointments/upcoming"]


def test_a_failed_appointments_read_after_a_match_is_upstream_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_LAN_SOURCE", "explicit-yes")
    directory_only = CountingFeed()
    directory_only.routes.pop("/api/v1/patients/40000003/appointments")
    for harness in build_sync_harness(tmp_path, feed=directory_only):
        dpop = DpopClient()
        bundle = harness.sign_up(FATMA_PHONE, dpop)
        harness.grant_core(bundle["patient_id"])

        response = harness.sync(FATMA_PHONE, bundle["access_token"], dpop)
        assert response.status_code == 200, response.text
        # a half-answered sync shows nothing rather than a name without visits
        assert response.json() == {
            "outcome": "upstream_unavailable",
            "patient_name": None,
            "visits": [],
        }
        assert harness.feed.calls == [
            "/api/v1/appointments/upcoming",
            "/api/v1/patients/40000003/appointments",
        ]


def test_a_number_that_is_not_a_turkish_mobile_is_refused_before_the_feed(
    sync_harness: SyncHarness,
) -> None:
    dpop = DpopClient()
    bundle = sync_harness.sign_up(FATMA_PHONE, dpop)
    sync_harness.grant_core(bundle["patient_id"])

    response = sync_harness.sync("+4930123456", bundle["access_token"], dpop)
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "phone_invalid"
    assert sync_harness.feed.calls == []
