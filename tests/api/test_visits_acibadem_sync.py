"""INT-318 — POST /v1/visits/sync: a logged-in patient's own upcoming visits,
read from the Acıbadem feed after OTP verification.

What this pins (the near-miss controls the issue names):

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
* every disclosure is written to the hash-chained audit (invariant 4).

The connector client is injected over an ``httpx.MockTransport`` (no network),
and its recorded payloads are the INLINE Python literals in
``tests/connectors/acibadem_harness.py`` — reused rather than copied into a
fixture tree, because a checksum-valid TC Kimlik under ``tests/fixtures/**`` is
refused by ``phi_scan.sh``. fakeredis + an injected clock keep the OTP tier
deterministic, exactly as ``tests/security/test_otp_abuse.py`` does.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fakeredis
import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient
from intake_platform.db.audit_store import SqlAlchemyAuditStore
from intake_platform.db.models import Consent
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from intake_platform.tokenization import Tokenizer
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "connectors"))

import acibadem_harness as acb  # noqa: E402
from api_harness import run, sqlite_ddl_clone  # noqa: E402
from intake_api import visits_acibadem  # noqa: E402
from intake_api.app import ApiWiring, create_app  # noqa: E402
from intake_api.attestation import DevStructuralAttestationVerifier  # noqa: E402
from intake_api.dev_fixture import ensure_dev_fixture  # noqa: E402
from intake_api.otp import (  # noqa: E402
    CONSUMER_TENANT_ID,
    AuthWiring,
    DevLogDeliveryAdapter,
    ensure_consumer_tenant,
)
from intake_api.settings import ApiSettings  # noqa: E402

# --- feed fixtures (one measured shape per case) ------------------------------------------

FATMA_PHONE = "+905321110003"  # 40000003, single match, 2 upcoming + 1 past (2021)
MEHMET_PHONE = "+905321110001"  # 40000001, a DIFFERENT valid mobile (leak control)
SHARED_PHONE = "+905321110007"  # 40000007 & 40000008, both TC null → ambiguous
UNKNOWN_PHONE = "+905321119999"  # a valid mobile absent from the feed
BEFORE_THE_VISITS = dt.date(2026, 9, 4)  # the fixtures' upcoming rows are 2026-09-05

_ROUTES: dict[str, Any] = {
    "/api/v1/appointments/upcoming": acb.load("upcoming.json"),
    "/api/v1/patients/40000003/appointments": acb.load("patient_40000003.json"),
}


# --- a mock transport that counts, so "the feed was never touched" is provable ------------


@dataclass
class CountingFeed:
    routes: dict[str, Any]
    calls: list[str] = field(default_factory=list)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        body = self.routes.get(request.url.path)
        if body is None:
            return httpx.Response(404, json={"detail": "no such fixture route"})
        return httpx.Response(200, json=body)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)


# --- DPoP client (RFC 9449), copied from the OTP suite so this file stands alone ----------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class DpopClient:
    def __init__(self) -> None:
        self._key = ec.generate_private_key(ec.SECP256R1())
        numbers = self._key.public_key().public_numbers()
        self.jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64url(numbers.x.to_bytes(32, "big")),
            "y": _b64url(numbers.y.to_bytes(32, "big")),
        }

    def proof(
        self,
        method: str,
        url: str,
        *,
        iat: float,
        jti: str | None = None,
        access_token: str | None = None,
    ) -> str:
        header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self.jwk}
        claims: dict[str, Any] = {
            "htm": method.upper(),
            "htu": url,
            "iat": int(iat),
            "jti": jti or uuid.uuid4().hex,
        }
        if access_token is not None:
            claims["ath"] = _b64url(hashlib.sha256(access_token.encode("ascii")).digest())
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(json.dumps(claims, separators=(",", ":")).encode())
        )
        der = self._key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return signing_input + "." + _b64url(raw)


class Clock:
    def __init__(self) -> None:
        self.now = float(int(time.time()))

    def __call__(self) -> float:
        return self.now


# --- harness ------------------------------------------------------------------------------


@dataclass
class SyncHarness:
    client: TestClient
    engine: Any
    audit_store: SqlAlchemyAuditStore
    clock: Clock
    feed: CountingFeed
    base: str = "http://testserver"

    # -- OTP onboarding (attestation → peek → DPoP verify) --
    def _attestation(self, device_id: str = "device-a") -> dict[str, str]:
        challenge = self.client.post("/v1/auth/attest/challenge").json()["challenge"]
        payload = {
            "platform": "ios",
            "mode": "dev-unattested",
            "token": _b64url(b"intake-dev-attest"),
            "device_id": device_id,
            "nonce": challenge,
        }
        return {"X-Intake-Attestation": json.dumps(payload)}

    def sign_up(self, phone: str, dpop: DpopClient) -> dict[str, Any]:
        assert (
            self.client.post(
                "/v1/auth/otp/request", json={"phone": phone}, headers=self._attestation()
            ).status_code
            == 202
        )
        code = self.client.get("/v1/auth/dev/otp-peek", params={"phone": phone}).json()["code"]
        headers = self._attestation()
        headers["DPoP"] = dpop.proof("POST", f"{self.base}/v1/auth/otp/verify", iat=self.clock())
        response = self.client.post(
            "/v1/auth/otp/verify", json={"phone": phone, "code": code}, headers=headers
        )
        assert response.status_code == 200, response.text
        return response.json()

    def grant_core(self, patient_id: str) -> None:
        async def _grant() -> None:
            async with AsyncSession(self.engine) as session, session.begin():
                session.add(
                    Consent(
                        tenant_id=CONSUMER_TENANT_ID,
                        patient_id=uuid.UUID(patient_id),
                        scope="core",
                        version="int318-test",
                        granted_at=datetime.now(UTC),
                    )
                )

        run(_grant())

    def sync(self, phone: str, access_token: str, dpop: DpopClient) -> httpx.Response:
        url = f"{self.base}/v1/visits/sync"
        proof = dpop.proof("POST", url, iat=self.clock(), access_token=access_token)
        return self.client.post(
            "/v1/visits/sync",
            json={"phone": phone},
            headers={"Authorization": f"DPoP {access_token}", "DPoP": proof},
        )


@pytest.fixture()
def sync_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SyncHarness]:
    # the LanSourcePolicy runtime double-gate (the client would otherwise deny)
    monkeypatch.setenv("INTAKE_ALLOW_LAN_SOURCE", "explicit-yes")

    app_db = tmp_path / "sync.db"
    audit_db = tmp_path / "sync-audit.db"
    ddl = create_engine(f"sqlite+pysqlite:///{app_db}")
    sqlite_ddl_clone().create_all(ddl)
    ddl.dispose()
    audit_engine = create_engine(f"sqlite+pysqlite:///{audit_db}")
    sqlite_ddl_clone().create_all(audit_engine)

    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}", poolclass=NullPool)
    clock = Clock()
    feed = CountingFeed(routes=dict(_ROUTES))
    acibadem_client = acb.client(feed.transport())

    wiring = ApiWiring(
        settings=ApiSettings(
            token_patient=None,
            token_admin=None,
            app_db_url=f"sqlite+aiosqlite:///{app_db}",
            audit_db_url=f"sqlite+pysqlite:///{audit_db}",
            bootstrap_db_url=f"sqlite+aiosqlite:///{app_db}",
            kek_mode="file-dev",
            legal_root=tmp_path / "legal-not-authored",
            dev_otp_peek=True,
        ),
        engine=engine,
        audit_store=SqlAlchemyAuditStore(audit_engine),
        cipher=EnvelopeCipher(FileKekProvider()),
        bootstrap=False,
        documents=None,
        auth=AuthWiring(
            redis_client=fakeredis.FakeStrictRedis(),
            tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
            delivery=DevLogDeliveryAdapter(),
            attestation=DevStructuralAttestationVerifier(),
            dev_otp_peek=True,
            now_fn=clock,
        ),
        acibadem=acibadem_client,
    )
    run(ensure_consumer_tenant(engine))
    run(ensure_dev_fixture(engine))
    app = create_app(wiring)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SyncHarness(
            client=client,
            engine=engine,
            audit_store=wiring.audit_store,
            clock=clock,
            feed=feed,
        )
    run(engine.dispose())
    audit_engine.dispose()


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
