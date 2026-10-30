"""INT-344 — App Attest on the OTP flow, end to end through the real app.

files/10 §2: attestation on OTP request AND session start, bound to a server
challenge. The flow the mobile client now runs in release builds:

  POST /v1/auth/attest/challenge  -> single-use challenge
  POST /v1/auth/attest/key        -> the App Attest ATTESTATION registers the key
  POST /v1/auth/otp/request       -> X-Intake-Attestation carries an ASSERTION
  POST /v1/auth/otp/verify        -> another assertion, plus the DPoP proof

What this file proves (the branches the verifier cannot see on its own):
- an attested device signs up end to end, counter 1 then 2;
- a replayed challenge is refused — on the OTP call AND on key registration;
- a refused attestation still burns its challenge (single-use whatever the
  outcome, so a caller cannot retry verification against one challenge);
- an assertion made for one call is refused on another;
- with no Apple configuration the registration endpoint fails closed;
- INT-578: a code requested under one App Attest key is refused under another,
  even when both payloads claim the same install id — the binding is the
  PROVEN key, never the claim.

The PKI is synthetic (app_attest_testkit); the verifier is the production class
with the test root injected through ``root=``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from api_harness import run, sqlite_ddl_clone
from app_attest_testkit import BUNDLE_ID, NOW, TEAM_ID, Device, Pki
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient
from intake_api.app import ApiWiring, create_app
from intake_api.app_attest import AppAttestConfig, AppAttestEnvironment, AppAttestVerifier
from intake_api.app_attest_store import RedisAppAttestKeyStore
from intake_api.attestation import (
    AttestationReason,
    FailClosedAttestationVerifier,
    PlatformAttestationVerifier,
    attestation_client_data,
)
from intake_api.otp import AuthWiring, DevLogDeliveryAdapter, ensure_consumer_tenant
from intake_api.settings import ApiSettings
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from intake_platform.tokenization import Tokenizer
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

PHONE = "+905321114455"
BASE = "http://testserver"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _dpop(key: ec.EllipticCurvePrivateKey, method: str, url: str, iat: float) -> str:
    """RFC 9449 proof over a P-256 key (the mobile client's shape)."""
    numbers = key.public_key().public_numbers()
    header = {
        "typ": "dpop+jwt",
        "alg": "ES256",
        "jwk": {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64url(numbers.x.to_bytes(32, "big")),
            "y": _b64url(numbers.y.to_bytes(32, "big")),
        },
    }
    claims = {"htm": method, "htu": url, "iat": int(iat), "jti": uuid.uuid4().hex}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(claims, separators=(",", ":")).encode())
    )
    r, s = decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    return signing_input + "." + _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


@dataclass
class Flow:
    client: TestClient
    device: Device
    counter: int = 0
    #: INT-578: the request id the last admitted request answered with
    request_id: str | None = None

    def challenge(self) -> str:
        response = self.client.post("/v1/auth/attest/challenge")
        assert response.status_code == 201, response.text
        value: str = response.json()["challenge"]
        return value

    def register(self, challenge: str | None = None, **knobs: Any) -> Any:
        nonce = challenge if challenge is not None else self.challenge()
        token = self.device.attest(attestation_client_data("attest.key", nonce), **knobs)
        return self.client.post(
            "/v1/auth/attest/key",
            json={
                "platform": "ios",
                "key_id": self.device.key_id,
                "attestation": token,
                "challenge": nonce,
            },
        )

    def header(self, purpose: str, *, signed_for: str | None = None) -> dict[str, str]:
        nonce = self.challenge()
        self.counter += 1
        client_data = attestation_client_data(signed_for or purpose, nonce)
        payload = {
            "platform": "ios",
            "mode": "app-attest",
            "token": self.device.assertion(client_data, self.counter),
            "key_id": self.device.key_id,
            "device_id": "install-a",
            "nonce": nonce,
        }
        return {"X-Intake-Attestation": json.dumps(payload)}

    def request_otp(self, headers: dict[str, str] | None = None) -> Any:
        response = self.client.post(
            "/v1/auth/otp/request",
            json={"phone": PHONE},
            headers=headers if headers is not None else self.header("otp.request"),
        )
        if response.status_code == 202:
            self.request_id = response.json().get("request_id")
        return response

    def verify(self, dpop_key: ec.EllipticCurvePrivateKey, headers: dict[str, str]) -> Any:
        code = self.client.get("/v1/auth/dev/otp-peek", params={"phone": PHONE})
        assert code.status_code == 200, code.text
        url = f"{BASE}/v1/auth/otp/verify"
        return self.client.post(
            "/v1/auth/otp/verify",
            json={"phone": PHONE, "code": code.json()["code"], "request_id": self.request_id},
            headers={**headers, "DPoP": _dpop(dpop_key, "POST", url, NOW.timestamp())},
        )


def _build(tmp_path: Path, *, configured: bool = True) -> Iterator[Flow]:
    from intake_platform.db.audit_store import SqlAlchemyAuditStore
    from sqlalchemy import create_engine

    app_db = tmp_path / "attest.db"
    audit_db = tmp_path / "attest-audit.db"
    for path in (app_db, audit_db):
        ddl = create_engine(f"sqlite+pysqlite:///{path}")
        sqlite_ddl_clone().create_all(ddl)
        ddl.dispose()
    audit_engine = create_engine(f"sqlite+pysqlite:///{audit_db}")
    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}", poolclass=NullPool)
    redis_client = fakeredis.FakeStrictRedis()
    pki = Pki.build()
    config = AppAttestConfig(
        team_id=TEAM_ID, bundle_id=BUNDLE_ID, environment=AppAttestEnvironment.PRODUCTION
    )
    verifier = AppAttestVerifier(
        config, RedisAppAttestKeyStore(redis_client), root=pki.root.cert, now_fn=NOW.timestamp
    )
    unconfigured = FailClosedAttestationVerifier(AttestationReason.APP_ATTEST_NOT_CONFIGURED)
    wiring = ApiWiring(
        settings=ApiSettings(
            token_patient=None,
            token_admin=None,
            app_db_url=f"sqlite+aiosqlite:///{app_db}",
            audit_db_url=f"sqlite+pysqlite:///{audit_db}",
            bootstrap_db_url=f"sqlite+aiosqlite:///{app_db}",
            kek_mode="file-dev",
        ),
        engine=engine,
        audit_store=SqlAlchemyAuditStore(audit_engine),
        cipher=EnvelopeCipher(FileKekProvider()),
        bootstrap=False,
        documents=None,
        auth=AuthWiring(
            redis_client=redis_client,
            tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
            delivery=DevLogDeliveryAdapter(),
            attestation=PlatformAttestationVerifier(
                app_attest=verifier if configured else unconfigured,
                play_integrity=FailClosedAttestationVerifier(
                    AttestationReason.PLAY_INTEGRITY_NOT_CONFIGURED
                ),
            ),
            key_attestation=verifier if configured else unconfigured,
            dev_otp_peek=True,
            now_fn=NOW.timestamp,
        ),
    )
    run(ensure_consumer_tenant(engine))
    with TestClient(create_app(wiring), raise_server_exceptions=False) as client:
        yield Flow(client=client, device=Device(pki))
    run(engine.dispose())
    audit_engine.dispose()


@pytest.fixture()
def flow(tmp_path: Path) -> Iterator[Flow]:
    yield from _build(tmp_path)


@pytest.fixture()
def unconfigured(tmp_path: Path) -> Iterator[Flow]:
    yield from _build(tmp_path, configured=False)


def test_an_attested_device_signs_up_end_to_end(flow: Flow) -> None:
    registered = flow.register()
    assert registered.status_code == 201, registered.text
    assert registered.json() == {"key_id": flow.device.key_id}

    assert flow.request_otp().status_code == 202

    dpop_key = ec.generate_private_key(ec.SECP256R1())
    response = flow.verify(dpop_key, flow.header("otp.verify"))
    assert response.status_code == 200, response.text
    assert response.json()["token_type"] == "DPoP"


def test_a_replayed_challenge_is_refused_on_the_otp_call(flow: Flow) -> None:
    assert flow.register().status_code == 201
    headers = flow.header("otp.request")
    assert flow.request_otp(headers).status_code == 202
    replayed = flow.request_otp(headers)
    assert replayed.status_code == 403
    assert replayed.json()["error"] == "challenge_invalid"


def test_a_replayed_challenge_is_refused_on_key_registration(flow: Flow) -> None:
    nonce = flow.challenge()
    assert flow.register(nonce).status_code == 201
    again = flow.register(nonce)
    assert again.status_code == 403
    assert again.json()["error"] == "challenge_invalid"


def test_a_refused_attestation_still_burns_its_challenge(flow: Flow) -> None:
    nonce = flow.challenge()
    refused = flow.register(nonce, counter=7)
    assert refused.status_code == 403
    assert refused.json()["error"] == "attestation_unverified"
    retried = flow.register(nonce)
    assert retried.status_code == 403
    assert retried.json()["error"] == "challenge_invalid"


def test_an_assertion_is_bound_to_the_call_it_was_made_for(flow: Flow) -> None:
    assert flow.register().status_code == 201
    assert flow.request_otp().status_code == 202
    dpop_key = ec.generate_private_key(ec.SECP256R1())
    # a live challenge and a genuine key, but signed for otp.request
    misbound = flow.verify(dpop_key, flow.header("otp.verify", signed_for="otp.request"))
    assert misbound.status_code == 403
    assert misbound.json()["error"] == "attestation_unverified"


def test_a_code_requested_under_one_key_is_useless_under_another(flow: Flow) -> None:
    """INT-578: both devices claim the install id ``install-a``; only the key
    differs, and the key is what the code is bound to."""
    other = Flow(client=flow.client, device=Device(flow.device.pki))
    assert flow.register().status_code == 201
    assert other.register().status_code == 201
    assert flow.request_otp().status_code == 202
    dpop_key = ec.generate_private_key(ec.SECP256R1())
    stolen = flow.verify(dpop_key, other.header("otp.verify"))
    assert stolen.status_code == 401
    assert stolen.json() == {"error": "otp_invalid"}
    # near miss: the key that asked, same code, same request id
    assert flow.verify(dpop_key, flow.header("otp.verify")).status_code == 200


def test_an_unregistered_key_cannot_request_a_code(flow: Flow) -> None:
    response = flow.request_otp()
    assert response.status_code == 403
    assert response.json()["error"] == "attestation_unverified"


def test_registration_is_schema_constrained(flow: Flow) -> None:
    oversized = flow.client.post(
        "/v1/auth/attest/key",
        json={
            "platform": "ios",
            "key_id": flow.device.key_id,
            "attestation": "A" * 20_000,
            "challenge": flow.challenge(),
        },
    )
    assert oversized.status_code == 422
    android = flow.client.post(
        "/v1/auth/attest/key",
        json={
            "platform": "android",
            "key_id": flow.device.key_id,
            "attestation": "AAAA",
            "challenge": flow.challenge(),
        },
    )
    assert android.status_code == 422


def test_key_registration_fails_closed_without_apple_config(unconfigured: Flow) -> None:
    response = unconfigured.register()
    assert response.status_code == 403
    assert response.json()["error"] == "attestation_unverified"


def test_no_attestation_material_reaches_the_logs(
    flow: Flow, caplog: pytest.LogCaptureFixture
) -> None:
    """Invariant 6 discipline: a refusal logs its typed reason and nothing else —
    not the key id, not the token, not the challenge."""
    caplog.set_level("INFO")
    nonce = flow.challenge()
    flow.register(nonce, counter=7)
    text = caplog.text
    assert "app_attest_counter_invalid" in text
    for material in (flow.device.key_id, nonce, hashlib.sha256(nonce.encode()).hexdigest()):
        assert material not in text
