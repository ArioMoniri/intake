"""INT-582 harness: the API with the OTP/DPoP tier and the passkey tier wired
over one fakeredis and one injected clock, plus a signed-in device per call.

Real OTP sign-in (dev attestation + the dev peek, as tests/security/
test_otp_abuse.py does), real DPoP proofs, and the passkey_testkit
authenticator on the phone side. Nothing dials a network; nothing sleeps.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fakeredis
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness, run
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient
from intake_api.attestation import DevStructuralAttestationVerifier
from intake_api.auth_store import OTP_WINDOW_S
from intake_api.otp import AuthWiring, DevLogDeliveryAdapter, ensure_consumer_tenant
from intake_api.passkey.service import PasskeyWiring
from intake_api.passkey.webauthn import PasskeyConfig
from intake_platform.db.models import PatientPasskey
from intake_platform.tokenization import Tokenizer
from passkey_testkit import ORIGIN, RP_ID, Authenticator, b64url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

CONFIG = PasskeyConfig(rp_id=RP_ID, origins=frozenset({ORIGIN}))
PHONE_A = "+905321114455"
PHONE_B = "+905321114466"
BASE = "http://testserver"


class Clock:
    """Seeded from the start of an OTP window (the INT-285 rule) on the real
    epoch, because the DPoP ``iat`` skew check reads this same clock."""

    def __init__(self) -> None:
        self.now = float(int(time.time()) // OTP_WINDOW_S * OTP_WINDOW_S) + 60.0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now

    @property
    def utc(self) -> datetime:
        return datetime.fromtimestamp(self.now, UTC)


class Dpop:
    """The client half of RFC 9449: one device key, compact ES256 proofs."""

    def __init__(self) -> None:
        self._key = ec.generate_private_key(ec.SECP256R1())
        numbers = self._key.public_key().public_numbers()
        self.jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": b64url(numbers.x.to_bytes(32, "big")),
            "y": b64url(numbers.y.to_bytes(32, "big")),
        }

    def proof(self, method: str, url: str, *, iat: float, access_token: str | None = None) -> str:
        header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self.jwk}
        claims: dict[str, Any] = {
            "htm": method.upper(),
            "htu": url,
            "iat": int(iat),
            "jti": uuid.uuid4().hex,
        }
        if access_token is not None:
            claims["ath"] = b64url(hashlib.sha256(access_token.encode("ascii")).digest())
        signing_input = (
            b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + b64url(json.dumps(claims, separators=(",", ":")).encode())
        )
        der = self._key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return signing_input + "." + b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


@dataclass
class Session:
    """One signed-in device: its DPoP key and its access token. ``None`` in
    place of a Session means the dev-bearer patient."""

    dpop: Dpop
    token: str
    patient_id: str


@dataclass
class PasskeyKit:
    harness: ApiHarness
    clock: Clock
    redis_client: Any

    @property
    def client(self) -> TestClient:
        return self.harness.client

    def _attestation(self, device_id: str) -> dict[str, str]:
        nonce = self.client.post("/v1/auth/attest/challenge").json()["challenge"]
        payload = {
            "platform": "ios",
            "mode": "dev-unattested",
            "token": b64url(b"intake-dev-attest"),
            "device_id": device_id,
            "nonce": nonce,
        }
        return {"X-Intake-Attestation": json.dumps(payload)}

    def sign_in(self, phone: str = PHONE_A, device_id: str = "device-a") -> Session:
        requested = self.client.post(
            "/v1/auth/otp/request", json={"phone": phone}, headers=self._attestation(device_id)
        )
        assert requested.status_code == 202, requested.text
        code = self.client.get("/v1/auth/dev/otp-peek", params={"phone": phone}).json()["code"]
        dpop = Dpop()
        headers = self._attestation(device_id)
        headers["DPoP"] = dpop.proof("POST", f"{BASE}/v1/auth/otp/verify", iat=self.clock())
        verified = self.client.post(
            "/v1/auth/otp/verify", json={"phone": phone, "code": code}, headers=headers
        )
        assert verified.status_code == 200, verified.text
        body = verified.json()
        # the next OTP request waits out the shared resend cooldown
        self.clock.advance(61)
        return Session(dpop=dpop, token=body["access_token"], patient_id=body["patient_id"])

    def call(
        self,
        session: Session | None,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        sent = dict(headers or {})
        if session is None:
            sent["Authorization"] = f"Bearer {PATIENT_TOKEN}"
        else:
            sent["Authorization"] = f"DPoP {session.token}"
            sent["DPoP"] = session.dpop.proof(
                method, f"{BASE}{path}", iat=self.clock(), access_token=session.token
            )
        return self.client.request(method, path, json=json_body, headers=sent)

    # --- the passkey ceremonies --------------------------------------------------------

    def register(
        self,
        session: Session | None,
        device: Authenticator,
        *,
        grant: str | None = None,
        **knobs: Any,
    ) -> Any:
        """Enrol ``device``. ``grant`` is a passkey_add grant, sent on both
        registration calls — required once the patient already holds a passkey."""
        headers = {"X-Intake-Step-Up-Grant": grant} if grant is not None else None
        options = self.call(
            session, "POST", "/v1/me/passkeys/registration/options", headers=headers
        )
        assert options.status_code == 200, options.text
        credential = device.register(options.json(), **knobs)
        return self.call(
            session,
            "POST",
            "/v1/me/passkeys/registration",
            json_body={"credential": credential},
            headers=headers,
        )

    def step_up_options(self, session: Session | None, action: str) -> Any:
        return self.call(
            session, "POST", "/v1/me/passkeys/step-up/options", json_body={"action": action}
        )

    def finish_step_up(
        self, session: Session | None, action: str, credential: dict[str, Any]
    ) -> Any:
        return self.call(
            session,
            "POST",
            "/v1/me/passkeys/step-up",
            json_body={"action": action, "credential": credential},
        )

    def step_up(
        self,
        session: Session | None,
        device: Authenticator,
        action: str,
        *,
        finish_as: str | None = None,
        **knobs: Any,
    ) -> Any:
        options = self.step_up_options(session, action)
        assert options.status_code == 200, options.text
        body = options.json()
        assert body["enrolled"] is True, body
        return self.finish_step_up(session, finish_as or action, device.assertion(body, **knobs))

    def grant(self, session: Session | None, device: Authenticator, action: str) -> str:
        response = self.step_up(session, device, action)
        assert response.status_code == 200, response.text
        grant: str = response.json()["grant"]
        return grant

    def passkey_rows(self) -> list[PatientPasskey]:
        async def _load() -> list[PatientPasskey]:
            async with AsyncSession(self.harness.engine) as session:
                return list((await session.scalars(select(PatientPasskey))).all())

        rows: list[PatientPasskey] = run(_load())
        return rows

    def audit_actions(self) -> list[tuple[str, str, str]]:
        return [
            (entry.action, entry.resource_ref, entry.actor)
            for entry in self.harness.audit_store.entries()
        ]


def build_passkey_kit(tmp_path: Path, *, passkey_wired: bool = True) -> Iterator[PasskeyKit]:
    clock = Clock()
    redis_client = fakeredis.FakeStrictRedis()
    auth = AuthWiring(
        redis_client=redis_client,
        tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
        delivery=DevLogDeliveryAdapter(),
        attestation=DevStructuralAttestationVerifier(),
        dev_otp_peek=True,
        now_fn=clock,
    )
    passkey = (
        PasskeyWiring(config=CONFIG, redis_client=redis_client, now_fn=clock)
        if passkey_wired
        else None
    )
    harnesses = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        auth=auth,
        dev_otp_peek=True,
        passkey=passkey,
    )
    harness = next(harnesses)
    run(ensure_consumer_tenant(harness.engine))
    yield PasskeyKit(harness=harness, clock=clock, redis_client=redis_client)
    for _ in harnesses:  # drain so the harness tears down
        pass
