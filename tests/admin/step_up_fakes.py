"""A recorded Keycloak for the INT-563 step-up (ADR-043): authorize, then redeem.

No test dials Keycloak and there is no container runtime to start one. This
plays the two hops a real step-up makes, and nothing else:

- :meth:`RecordedKeycloak.authorize` is the browser at the authorization
  endpoint. It reads the URL the API built and refuses one that does not ask
  for what ADR-043 says — the step-up client, ``prompt=login``, ``max_age=0``,
  PKCE S256, the console callback — then issues a code bound to the
  challenge, the nonce and the account that "authenticated".
- :meth:`RecordedKeycloak.exchange` is the API at the token endpoint. It
  checks the verifier against the challenge, spends the code, and returns an
  ID token signed with an in-process key whose claims are the ones Keycloak
  26 puts in an ID token for the committed realm's step-up client
  (:func:`keycloak_mappers.mint_id_token_claims` over ``dev-realm.json``).

The key pair is generated for the test run; nothing here is a secret.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from admin_harness import bearer, recorded_claims, token_for
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from intake_platform.admin.oidc import KeycloakClaimsVerifier, load_jwks
from intake_platform.admin.step_up import (
    STEP_UP_CLIENT_ID,
    StepUpConfig,
    StepUpExchangeFailed,
    StepUpService,
)
from keycloak_mappers import mint_id_token_claims

REPO = Path(__file__).resolve().parents[2]
DEV_REALM = REPO / "infra" / "keycloak" / "dev-realm.json"
#: The recorded claim set's issuer (fixtures/keycloak_claims.json).
ISSUER = "http://localhost:8080/realms/intake-dev"
CALLBACK = "http://localhost:3000/step-up/callback"
CONFIG = StepUpConfig(
    authorize_endpoint=f"{ISSUER}/protocol/openid-connect/auth",
    token_endpoint=f"{ISSUER}/protocol/openid-connect/token",
    redirect_uri=CALLBACK,
)
KID = "int563-unit-lane"
#: A fixed instant the step-up suites run at (2027-01-15T08:00:00Z).
T0 = datetime(2027, 1, 15, 8, 0, tzinfo=UTC)

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def jwks() -> dict[str, Any]:
    numbers = _KEY.public_key().public_numbers()
    return {
        "keys": [
            {
                "kid": KID,
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "n": _b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
                "e": _b64(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
            }
        ]
    }


def sign(claims: Mapping[str, Any]) -> str:
    head = _b64(json.dumps({"alg": "RS256", "kid": KID, "typ": "JWT"}).encode())
    body = _b64(json.dumps(dict(claims)).encode())
    signature = _KEY.sign(f"{head}.{body}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}.{_b64(signature)}"


@dataclass
class Clock:
    now: datetime = T0

    def __call__(self) -> datetime:
        return self.now

    def epoch(self) -> int:
        return int(self.now.timestamp())

    def advance(self, by: timedelta) -> None:
        self.now += by


@dataclass(frozen=True)
class Login:
    """What one re-authentication at Keycloak produced. Defaults are the
    honest case; a test changes one field to build its near miss."""

    subject: str
    session_id: str
    credential_id: str
    aaguid: str = "00000000-0000-0000-0000-000000000000"
    amr: tuple[str, ...] = ("pwd", "hwk")
    #: seconds after the ceremony began (negative: a remembered login)
    auth_offset_s: int = 5
    typ: str = "ID"
    nonce: str | None = None
    overrides: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class _Issued:
    challenge: str
    claims: dict[str, Any]


@dataclass
class RecordedKeycloak:
    clock: Clock
    _codes: dict[str, _Issued] = field(default_factory=dict)
    exchanges: int = 0

    def authorize(self, url: str, login: Login) -> tuple[str, str]:
        """The browser's hop: (state, code) for the console's callback."""
        parts = urlsplit(url)
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == CONFIG.authorize_endpoint
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        assert query["client_id"] == STEP_UP_CLIENT_ID
        assert query["response_type"] == "code" and query["scope"] == "openid"
        assert query["prompt"] == "login" and query["max_age"] == "0"
        assert query["code_challenge_method"] == "S256"
        assert query["redirect_uri"] == CALLBACK
        realm = json.loads(DEV_REALM.read_text(encoding="utf-8"))
        now = self.clock.epoch()
        base: dict[str, Any] = {
            "iss": ISSUER,
            "aud": STEP_UP_CLIENT_ID,
            "azp": STEP_UP_CLIENT_ID,
            "typ": login.typ,
            "sub": login.subject,
            "sid": login.session_id,
            "nonce": login.nonce if login.nonce is not None else query["nonce"],
            "auth_time": now + login.auth_offset_s,
            "amr": list(login.amr),
            "iat": now,
            "exp": now + 300,
            "jti": secrets.token_hex(16),
            **login.overrides,
        }
        claims = mint_id_token_claims(
            realm,
            STEP_UP_CLIENT_ID,
            base=base,
            user_attributes={},
            session_notes={
                "intake.webauthn.aaguid": login.aaguid,
                "intake.webauthn.credential_id": login.credential_id,
            },
        )
        code = secrets.token_urlsafe(24)
        self._codes[code] = _Issued(challenge=query["code_challenge"], claims=claims)
        return query["state"], code

    def exchange(self, *, code: str, verifier: str) -> str:
        """The API's hop: one ID token per code, and only for its verifier."""
        self.exchanges += 1
        issued = self._codes.pop(code, None)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        if issued is None or _b64(digest) != issued.challenge:
            raise StepUpExchangeFailed("the token endpoint refused the code")
        return sign(issued.claims)


def build_step_up(clock: Clock) -> tuple[StepUpService, RecordedKeycloak]:
    keycloak = RecordedKeycloak(clock)
    verifier = KeycloakClaimsVerifier(
        issuer=ISSUER, audience=STEP_UP_CLIENT_ID, keys=load_jwks(jwks()), clock=clock.epoch
    )
    service = StepUpService(
        config=CONFIG, verifier=verifier, exchange=keycloak.exchange, clock=clock
    )
    return service, keycloak


#: The recorded accounts' Keycloak sessions (fixtures/keycloak_claims.json),
#: and a fresh credential per account for the step-up — not the one the
#: console session logged in with, so a test can see which one is used.
def login_for(account: Mapping[str, Any], **changes: Any) -> Login:
    fresh = _b64(hashlib.sha256(str(account["sub"]).encode()).digest()[:18])
    values: dict[str, Any] = {
        "subject": account["sub"],
        "session_id": account["sid"],
        "credential_id": fresh,
    }
    values.update(changes)
    return Login(**values)


@dataclass
class StepUpHarness:
    """The step-up an admin suite wires, and the one way its tests approve:
    begin at the API, re-authenticate at the recorded Keycloak, complete at
    the API, then present the grant — the console's own sequence."""

    clock: Clock
    service: StepUpService
    keycloak: RecordedKeycloak

    @classmethod
    def build(cls) -> StepUpHarness:
        clock = Clock()
        service, keycloak = build_step_up(clock)
        return cls(clock=clock, service=service, keycloak=keycloak)

    def grant(self, client: Any, account: str, action_id: str, **changes: Any) -> Any:
        """The ``/complete`` response, or the first refusal on the way."""
        begun = client.post(
            "/admin/step-up", json={"action_id": action_id}, headers=bearer(account)
        )
        if begun.status_code != 200:
            return begun
        login = login_for(recorded_claims()[token_for(account)], **changes)
        state, code = self.keycloak.authorize(begun.json()["authorize_url"], login)
        return client.post(
            "/admin/step-up/complete",
            json={"state": state, "code": code},
            headers=bearer(account),
        )

    def approve(self, client: Any, url: str, action_id: str, account: str, **changes: Any) -> Any:
        """Approve (or countersign) at ``url`` through a fresh step-up."""
        done = self.grant(client, account, action_id, **changes)
        if done.status_code != 200:
            return done
        return client.post(
            url, json={"step_up_grant": done.json()["grant"]}, headers=bearer(account)
        )
