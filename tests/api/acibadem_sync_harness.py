"""Shared wiring for the INT-318 ``POST /v1/visits/sync`` suites.

A module rather than a ``conftest.py`` for the reason ``api_harness.py`` gives:
two test files drive the same app over the same feed, and one file's
assumptions must not drift from the other's.

What is built here is the real stack minus the network: the OTP+DPoP tier over
fakeredis and an injected clock (exactly as ``tests/security/test_otp_abuse.py``
does), SQLite in place of Postgres, and the Acıbadem connector over a
request-counting ``httpx.MockTransport``. The feed payloads are the INLINE
Python literals in ``tests/connectors/acibadem_harness.py``, reused rather than
copied into a fixture tree, because a checksum-valid TC Kimlik under
``tests/fixtures/**`` is refused by ``phi_scan.sh``.

The source row the client is built from is a test row. Its binding refs are
the connector suite's fixture refs; the route under test never names one.
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
from intake_connectors.acibadem import AcibademAppointmentsClient  # noqa: E402
from intake_connectors.credentials import InMemoryCredentialResolver  # noqa: E402
from intake_connectors.sources import ClinicalSource  # noqa: E402

__all__ = [
    "BEFORE_THE_VISITS",
    "FATMA_PHONE",
    "MEHMET_PHONE",
    "SHARED_PHONE",
    "UNKNOWN_PHONE",
    "CountingFeed",
    "DpopClient",
    "SyncHarness",
    "build_sync_harness",
    "consumer_source",
    "feed_client",
]

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


def consumer_source(**overrides: object) -> ClinicalSource:
    """The connector suite's test row, registered for the tenant the OTP tier
    creates its accounts in — the only tenant whose patients it may serve."""
    base: dict[str, object] = {"tenant_id": str(CONSUMER_TENANT_ID)}
    base.update(overrides)
    return acb.source(**base)


# --- a mock transport that counts, so "the feed was never touched" is provable ------------


@dataclass
class CountingFeed:
    routes: dict[str, Any] = field(default_factory=lambda: dict(_ROUTES))
    calls: list[str] = field(default_factory=list)
    #: when set, every request fails at the transport the way a dropped link does
    fail_with: type[httpx.TransportError] | None = None
    #: when set, every request answers with this status and an empty JSON body
    status: int | None = None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        if self.fail_with is not None:
            raise self.fail_with("feed unreachable", request=request)
        if self.status is not None:
            return httpx.Response(self.status, json={})
        body = self.routes.get(request.url.path)
        if body is None:
            return httpx.Response(404, json={"detail": "no such fixture route"})
        return httpx.Response(200, json=body)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)


def feed_client(
    feed: CountingFeed,
    source: ClinicalSource,
    *,
    resolver: InMemoryCredentialResolver | None = None,
) -> AcibademAppointmentsClient:
    """The real connector client for one registered row, over the counting feed.
    ``resolver`` replaces the harness credential store (e.g. an empty one)."""
    return acb.client(feed.transport(), src=source, resolver=resolver)


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
        requested = self.client.post(
            "/v1/auth/otp/request", json={"phone": phone}, headers=self._attestation()
        )
        assert requested.status_code == 202
        code = self.client.get("/v1/auth/dev/otp-peek", params={"phone": phone}).json()["code"]
        headers = self._attestation()
        headers["DPoP"] = dpop.proof("POST", f"{self.base}/v1/auth/otp/verify", iat=self.clock())
        # INT-578: a code is bound to the request id its 202 answered with
        bound = {"phone": phone, "code": code, "request_id": requested.json().get("request_id")}
        response = self.client.post("/v1/auth/otp/verify", json=bound, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    def grant(self, patient_id: str, scope: str) -> None:
        async def _grant() -> None:
            async with AsyncSession(self.engine) as session, session.begin():
                session.add(
                    Consent(
                        tenant_id=CONSUMER_TENANT_ID,
                        patient_id=uuid.UUID(patient_id),
                        scope=scope,
                        version="int318-test",
                        granted_at=datetime.now(UTC),
                    )
                )

        run(_grant())

    def grant_core(self, patient_id: str) -> None:
        self.grant(patient_id, "core")

    def sync(self, phone: str, access_token: str, dpop: DpopClient) -> httpx.Response:
        url = f"{self.base}/v1/visits/sync"
        proof = dpop.proof("POST", url, iat=self.clock(), access_token=access_token)
        return self.client.post(
            "/v1/visits/sync",
            json={"phone": phone},
            headers={"Authorization": f"DPoP {access_token}", "DPoP": proof},
        )


def build_sync_harness(
    tmp_path: Path,
    *,
    feed: CountingFeed | None = None,
    source: ClinicalSource | None = None,
    registered: bool = True,
    client: AcibademAppointmentsClient | None = None,
) -> Iterator[SyncHarness]:
    """The app with the OTP tier and, unless ``registered`` is False, one
    Acıbadem client built from ``source`` (the consumer-tenant test row by
    default) — or ``client`` itself when given. ``registered=False`` is the
    shipped state: no row, no client."""
    feed = feed if feed is not None else CountingFeed()
    app_db = tmp_path / "sync.db"
    audit_db = tmp_path / "sync-audit.db"
    ddl = create_engine(f"sqlite+pysqlite:///{app_db}")
    sqlite_ddl_clone().create_all(ddl)
    ddl.dispose()
    audit_engine = create_engine(f"sqlite+pysqlite:///{audit_db}")
    sqlite_ddl_clone().create_all(audit_engine)

    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}", poolclass=NullPool)
    clock = Clock()
    acibadem = (
        None
        if not registered
        else client
        if client is not None
        else feed_client(feed, source if source is not None else consumer_source())
    )

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
        acibadem=acibadem,
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
