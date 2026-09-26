"""Shared fixtures for the INT-329 Twilio tests (test_otp_twilio*.py).

Everything here is a unit fixture: the vendor is an ``httpx.MockTransport``
handler, the resolver answers from a table (no DNS), the egress row exists only
in memory or in a tmp file, and the vault is a dict. The row in particular is
NOT a recorded decision — the shipped allow-list has no SMS row until the owner
records the DPA and the cross-border decision (docs/evidence/INT-329.md).
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import parse_qs

import httpx
import yaml
from api_harness import run
from intake_platform.egress import AllowlistEntry, EgressPolicy, EgressPurpose, InMemoryTransferLog

REPO = Path(__file__).resolve().parents[2]
SHIPPED_ALLOWLIST = REPO / "infra" / "security" / "egress-allowlist.yaml"

ACCOUNT_SID = "AC" + "3f9c1a7e5b2d4c6f" * 2
AUTH_TOKEN = "int329authtoken" + "9e8d7c6b5a4f3e2d1c0b"  # noqa: S105 — unit fixture
SENDER = "+15005550006"
SERVICE_SID = "MG" + "0a1b2c3d4e5f6a7b" * 2
MESSAGE_SID = "SM" + "c0ffee00deadbeef" * 2
PHONE = "+905321234567"
PHONE_NATIONAL = "5321234567"
CODE = "482915"
PUBLIC_ANSWER = "203.0.113.10"  # TEST-NET-3: routable-looking, never a real host
VAULT_DOC: dict[str, object] = {
    "account_sid": ACCOUNT_SID,
    "auth_token": AUTH_TOKEN,
    "from": SENDER,
}
SECRETS = (PHONE, PHONE_NATIONAL, CODE, AUTH_TOKEN)
STRICT_ENVIRONMENTS = ("prod", "staging")

_STANDARD_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


def twilio() -> ModuleType:
    """Resolved per call, so each test fails on its own line before the
    implementation exists instead of failing collection."""
    return importlib.import_module("intake_api.otp_twilio")


def otp_module() -> ModuleType:
    return importlib.import_module("intake_api.otp")


def resolver(host: str, port: int) -> tuple[str, ...]:
    assert host == "api.twilio.com" and port == 443, f"unexpected lookup {host}:{port}"
    return (PUBLIC_ANSWER,)


def twilio_row() -> AllowlistEntry:
    return AllowlistEntry(
        name="twilio-sms-test-row",
        host="api.twilio.com",
        port=443,
        protocol="https",
        purpose_id=EgressPurpose("sms_otp_delivery"),
        purpose="unit fixture: the SMS row awaiting the owner's decision",
        basis="unit fixture only",
        phi_allowed=True,
        phi_exception_approval="unit-fixture-not-a-decision",
    )


def policy() -> EgressPolicy:
    return EgressPolicy([twilio_row()], "phi_path", resolver=resolver)


def empty_policy() -> EgressPolicy:
    return EgressPolicy([], "phi_path", resolver=resolver)


def allowlist_with_the_row(tmp_path: Path) -> Path:
    path = tmp_path / "egress-allowlist.yaml"
    document = {
        "version": 1,
        "tiers": {"dev": [], "phi_path": [twilio_row().model_dump(mode="json")]},
    }
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


class Vendor:
    """A MockTransport handler that records what reached the wire."""

    def __init__(self, respond: Callable[[httpx.Request], Any]) -> None:
        self.respond = respond
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict[str, list[str]]] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        self.requests.append(request)
        self.bodies.append(parse_qs(request.content.decode("utf-8")))
        result = self.respond(request)
        if asyncio.iscoroutine(result):
            result = await result
        assert isinstance(result, httpx.Response)
        return result


def created(request: httpx.Request) -> httpx.Response:
    # Twilio's 201 echoes the recipient and the body — never to be logged
    return httpx.Response(
        201, json={"sid": MESSAGE_SID, "status": "queued", "to": PHONE, "body": CODE}
    )


def refused(status: int, vendor_code: int) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        message = f"The 'To' number {PHONE} is not a valid phone number."
        return httpx.Response(
            status, json={"code": vendor_code, "message": message, "status": status}
        )

    return respond


def raises(error: type[httpx.TransportError]) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        raise error("vendor did not answer", request=request)

    return respond


#: scenario -> (vendor behaviour, expected reason, expected HTTP status)
FAILURES: dict[str, tuple[Callable[[httpx.Request], Any], str, int | None]] = {
    "invalid-number-400": (refused(400, 21211), "rejected", 400),
    "auth-failure-401": (refused(401, 20003), "auth_failed", 401),
    "forbidden-403": (refused(403, 20003), "auth_failed", 403),
    "rate-limited-429": (refused(429, 20429), "rate_limited", 429),
    "vendor-500": (refused(500, 20500), "vendor_unavailable", 500),
    "vendor-503": (refused(503, 20503), "vendor_unavailable", 503),
    "timeout": (raises(httpx.ReadTimeout), "timeout", None),
    "connect-error": (raises(httpx.ConnectError), "unreachable", None),
    "created-without-sid": (
        lambda request: httpx.Response(201, json={"status": "queued"}),
        "malformed_response",
        201,
    ),
    "created-not-json": (
        lambda request: httpx.Response(201, text="<html/>"),
        "malformed_response",
        201,
    ),
    "redirect-not-followed": (
        lambda request: httpx.Response(307, headers={"location": "https://evil.example/"}),
        "rejected",
        307,
    ),
}


def credentials(sender: str = SENDER) -> Any:
    return twilio().TwilioCredentials.parse({**VAULT_DOC, "from": sender})


def adapter(
    vendor: Vendor,
    egress: EgressPolicy | None = None,
    log: InMemoryTransferLog | None = None,
    sender: str = SENDER,
) -> Any:
    return twilio().TwilioSmsDeliveryAdapter(
        credentials(sender),
        egress=egress if egress is not None else policy(),
        inner=httpx.MockTransport(vendor),
        transfer_log=log if log is not None else InMemoryTransferLog(),
    )


def send(delivery: Any) -> Any:
    return run(delivery.send(phone_e164=PHONE, code=CODE))


def assert_clean(text: str, where: str) -> None:
    for secret in SECRETS:
        assert secret not in text, f"{where} carries a phone, code or token"


def record_text(record: logging.LogRecord) -> str:
    """Everything a handler could render from a record: the message, its args,
    any extras and any exception text — but not the timestamps, whose digits
    could contain a six-digit code by chance."""
    extras = {
        key: value for key, value in record.__dict__.items() if key not in _STANDARD_RECORD_KEYS
    }
    return f"{record.getMessage()} {record.args!r} {extras!r} {record.exc_text or ''}"


class Vault:
    """The slice of SecretsProvider the wiring reads. Records every path."""

    def __init__(
        self,
        documents: Mapping[str, Mapping[str, object]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.documents = dict(documents or {})
        self.error = error
        self.paths: list[str] = []

    def get_kv(self, path: str) -> dict[str, Any]:
        self.paths.append(path)
        if self.error is not None:
            raise self.error
        if path not in self.documents:
            request = httpx.Request("GET", f"http://openbao.test/v1/secret/data/{path}")
            raise httpx.HTTPStatusError("404", request=request, response=httpx.Response(404))
        return dict(self.documents[path])


def complete_vault() -> Vault:
    return Vault({"api/twilio": VAULT_DOC})
