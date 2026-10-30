"""Shared fixtures for the INT-583 push tests (test_push_apns.py, test_sign_in_notice.py).

APNs answers come from ``tests/fixtures/apns/responses.json``, derived from
Apple's documentation and never captured from a live call. :func:`replay`
serves a recorded scenario and refuses one the file does not record. Transport
faults are faults, written here and named as such.

The egress row exists only in memory or in a tmp file and is NOT a recorded
decision: the shipped allow-list gains the APNs rows only through the owner's
patch (docs/evidence/INT-583.md). The signing key is generated per run, the
vault is a dict and the resolver is a table: nothing opens a socket or asks DNS.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from intake_platform.egress import AllowlistEntry, EgressPolicy, EgressPurpose

REPO = Path(__file__).resolve().parents[2]
SHIPPED_ALLOWLIST = REPO / "infra" / "security" / "egress-allowlist.yaml"
FIXTURE = REPO / "tests" / "fixtures" / "apns" / "responses.json"
HOST = "api.push.apple.com"
SANDBOX_HOST = "api.sandbox.push.apple.com"
PUBLIC_ANSWER = "203.0.113.30"  # TEST-NET-3: routable-looking, never a real host
KEY_ID = "ABC123DEFG"
TEAM_ID = "TEAM123456"
TOPIC = "com.ariomoniri.intakemobile"
#: Device tokens as the app sends them: 32 bytes of lower-case hex.
TOKEN_A = "a1" * 32
TOKEN_B = "b2" * 32
TOKEN_C = "c3" * 32

RECORDED: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))


def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def p8(key: ec.EllipticCurvePrivateKey) -> str:
    """The key as Apple hands it out: an unencrypted PKCS#8 PEM (.p8)."""
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def vault_doc(key: ec.EllipticCurvePrivateKey) -> dict[str, object]:
    return {"key_p8": p8(key), "key_id": KEY_ID, "team_id": TEAM_ID}


def resolver(host: str, port: int) -> tuple[str, ...]:
    assert host in (HOST, SANDBOX_HOST) and port == 443, f"unexpected lookup {host}:{port}"
    return (PUBLIC_ANSWER,)


def apns_row(host: str = HOST) -> AllowlistEntry:
    return AllowlistEntry(
        name="apns-test-row",
        host=host,
        port=443,
        protocol="https",
        purpose_id=EgressPurpose("push_security_notice"),
        purpose="unit fixture: the APNs row the owner's patch adds",
        basis="unit fixture only",
        phi_allowed=True,
        phi_exception_approval="unit-fixture-not-a-decision",
    )


def policy(host: str = HOST) -> EgressPolicy:
    return EgressPolicy([apns_row(host)], "phi_path", resolver=resolver)


def empty_policy() -> EgressPolicy:
    return EgressPolicy([], "phi_path", resolver=resolver)


def allowlist_with_the_row(tmp_path: Path, host: str = HOST) -> Path:
    path = tmp_path / "egress-allowlist.yaml"
    document = {
        "version": 1,
        "tiers": {"dev": [], "phi_path": [apns_row(host).model_dump(mode="json")]},
    }
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


class Vendor:
    """A MockTransport handler that records what reached the wire."""

    def __init__(self, respond: Callable[[httpx.Request], httpx.Response]) -> None:
        self.respond = respond
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict[str, Any]] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        self.requests.append(request)
        self.bodies.append(json.loads(request.content.decode("utf-8")))
        return self.respond(request)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def replay(scenario: str) -> Callable[[httpx.Request], httpx.Response]:
    """The committed answer for ``scenario``; an unrecorded one is refused."""
    responses = RECORDED["responses"]
    if scenario not in responses:
        raise LookupError(f"no recorded APNs answer {scenario!r}; record one, never invent it")
    recorded = responses[scenario]

    def respond(request: httpx.Request) -> httpx.Response:
        body = recorded["body"]
        return httpx.Response(
            recorded["status"],
            headers=recorded["headers"],
            content=b"" if body is None else json.dumps(body).encode("utf-8"),
            request=request,
        )

    return respond


def sequence(*scenarios: str) -> Callable[[httpx.Request], httpx.Response]:
    """Recorded answers in order, one per request."""
    queue = [replay(s) for s in scenarios]

    def respond(request: httpx.Request) -> httpx.Response:
        return queue.pop(0)(request)

    return respond


def per_token(answers: dict[str, str]) -> Callable[[httpx.Request], httpx.Response]:
    """A recorded answer chosen by the device token in the request path."""

    def respond(request: httpx.Request) -> httpx.Response:
        token = request.url.path.rsplit("/", 1)[-1]
        return replay(answers[token])(request)

    return respond
