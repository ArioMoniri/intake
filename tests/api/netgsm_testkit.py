"""Shared fixtures for the INT-528 and INT-576 Netgsm tests (test_otp_netgsm*.py).

Vendor responses come from ``tests/fixtures/netgsm/otp_rest_v2.json``, which
INT-576 re-derived from Netgsm's public documentation and its official SDKs
(verbatim snapshots in ``tests/fixtures/netgsm/sources/``) and which was never
captured from a live call. :func:`replay` serves it in the posture of
``intake_platform.notifications.ports.RecordedTransport``: a scenario the file
does not record is refused, never invented. Transport faults (a timeout, a
refused connection, a 5xx with no body) are not vendor shapes at all, so they
are written here as faults and named as such. So are the 2xx answers this
endpoint is not documented to give (:data:`UNREADABLE`): each one is a near
miss of a documented shape, named for what it gets wrong.

The egress row exists only in memory or in a tmp file and is NOT a recorded
decision: the shipped allow-list gains the Netgsm row only through the owner's
patch (docs/evidence/INT-528.md). The vault is a dict and the resolver is a
table, so nothing here opens a socket or asks DNS.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import yaml
from api_harness import run
from intake_platform.egress import AllowlistEntry, EgressPolicy, EgressPurpose, InMemoryTransferLog

REPO = Path(__file__).resolve().parents[2]
SHIPPED_ALLOWLIST = REPO / "infra" / "security" / "egress-allowlist.yaml"
FIXTURE = REPO / "tests" / "fixtures" / "netgsm" / "otp_rest_v2.json"
HOST = "api.netgsm.com.tr"

USERCODE = "8501234567"
PASSWORD = "int528-api-subuser-" + "f00dfeed" * 2  # noqa: S105 — unit fixture
MSGHEADER = "BASLIK"
PHONE = "+905321234567"
PHONE_NATIONAL = "5321234567"
CODE = "482915"
PUBLIC_ANSWER = "203.0.113.20"  # TEST-NET-3: routable-looking, never a real host
VAULT_DOC: dict[str, object] = {"usercode": USERCODE, "password": PASSWORD, "msgheader": MSGHEADER}
SECRETS = (PHONE, PHONE_NATIONAL, CODE, PASSWORD)
STRICT_ENVIRONMENTS = ("prod", "staging")

_STANDARD_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


def recorded() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return document


RECORDED = recorded()
JOBID: str = RECORDED["responses"]["accepted"]["body"]["jobid"]
DOCUMENTED_CODES: tuple[str, ...] = tuple(RECORDED["documented_error_codes"])
#: the scenarios that are documented successes of this endpoint
SUCCESS_SCENARIOS: tuple[str, ...] = ("accepted", "accepted_sdk")


def netgsm() -> ModuleType:
    """Resolved per call, so each test fails on its own line before the
    implementation exists instead of failing collection."""
    return importlib.import_module("intake_api.otp_netgsm")


def otp_module() -> ModuleType:
    return importlib.import_module("intake_api.otp")


def shape_module() -> ModuleType:
    return importlib.import_module("intake_api.otp_netgsm_shape")


def resolver(host: str, port: int) -> tuple[str, ...]:
    assert host == HOST and port == 443, f"unexpected lookup {host}:{port}"
    return (PUBLIC_ANSWER,)


def netgsm_row(host: str = HOST) -> AllowlistEntry:
    return AllowlistEntry(
        name="netgsm-otp-test-row",
        host=host,
        port=443,
        protocol="https",
        purpose_id=EgressPurpose("sms_otp_delivery"),
        purpose="unit fixture: the SMS row the owner's patch adds",
        basis="unit fixture only",
        phi_allowed=True,
        phi_exception_approval="unit-fixture-not-a-decision",
    )


def policy() -> EgressPolicy:
    return EgressPolicy([netgsm_row()], "phi_path", resolver=resolver)


def empty_policy() -> EgressPolicy:
    return EgressPolicy([], "phi_path", resolver=resolver)


def allowlist_with(tmp_path: Path, row: AllowlistEntry) -> Path:
    path = tmp_path / "egress-allowlist.yaml"
    document = {"version": 1, "tiers": {"dev": [], "phi_path": [row.model_dump(mode="json")]}}
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def allowlist_with_the_row(tmp_path: Path) -> Path:
    return allowlist_with(tmp_path, netgsm_row())


class Vendor:
    """A MockTransport handler that records what reached the wire."""

    def __init__(self, respond: Callable[[httpx.Request], Any]) -> None:
        self.respond = respond
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict[str, Any]] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        self.requests.append(request)
        self.bodies.append(json.loads(request.content.decode("utf-8")))
        result = self.respond(request)
        if asyncio.iscoroutine(result):
            result = await result
        assert isinstance(result, httpx.Response)
        return result


def replay(
    scenario: str, *, code: str | None = None, status: int | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    """The committed response for ``scenario``; ``code`` fills the documented
    error sample's ``XX``, and only with a code the documentation lists."""
    responses = RECORDED["responses"]
    if scenario not in responses:
        raise LookupError(f"no recorded Netgsm response {scenario!r}; record one, never invent it")
    recorded_response = responses[scenario]
    body = dict(recorded_response["body"])
    if code is not None:
        assert scenario == "error", "only the error sample carries a code to fill"
        body["code"] = code
    answer = recorded_response["status"] if status is None else status

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(answer, json=body)

    return respond


def accepted(request: httpx.Request) -> httpx.Response:
    return replay("accepted")(request)


def accepted_sdk(request: httpx.Request) -> httpx.Response:
    return replay("accepted_sdk")(request)


def elsewhere(scenario: str) -> Callable[[httpx.Request], httpx.Response]:
    """A body the documentation gives for a DIFFERENT endpoint, served at 200
    as if this one had sent it: a near miss, never a success."""
    text = RECORDED["documented_elsewhere"][scenario]["body"]

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=text)

    return respond


def fault(error: type[httpx.TransportError]) -> Callable[[httpx.Request], httpx.Response]:
    """A transport fault: no vendor shape, so nothing to record."""

    def respond(request: httpx.Request) -> httpx.Response:
        raise error("vendor did not answer", request=request)

    return respond


def bare(
    status: int, text: str = "", content_type: str | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    """An HTTP answer with no Netgsm body: a gateway in front of the vendor."""
    headers = {"content-type": content_type} if content_type is not None else None

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=text, headers=headers)

    return respond


def body(status: int, payload: object) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return respond


#: documented code -> the typed refusal and the port's reason it maps to
CODE_REFUSALS: dict[str, tuple[str, str]] = {
    "20": ("message_refused", "rejected"),
    "30": ("credentials_refused", "auth_failed"),
    "40": ("sender_refused", "rejected"),
    "41": ("sender_refused", "rejected"),
    "50": ("number_refused", "rejected"),
    "51": ("number_refused", "rejected"),
    "52": ("number_refused", "rejected"),
    "60": ("otp_package_missing", "rejected"),
    "70": ("parameters_refused", "rejected"),
    "80": ("send_limit_exceeded", "rate_limited"),
    "100": ("vendor_system_error", "vendor_unavailable"),
    "101": ("vendor_system_error", "vendor_unavailable"),
}

#: scenario -> (vendor behaviour, refusal or None, port reason, HTTP status)
FAULTS: dict[str, tuple[Callable[[httpx.Request], Any], str | None, str, int | None]] = {
    "unauthorised-401": (bare(401), None, "auth_failed", 401),
    "forbidden-403": (bare(403), None, "auth_failed", 403),
    "throttled-429": (bare(429), None, "rate_limited", 429),
    "gateway-502": (bare(502, "<html/>"), None, "vendor_unavailable", 502),
    "unavailable-503": (bare(503), None, "vendor_unavailable", 503),
    "timeout": (fault(httpx.ReadTimeout), None, "timeout", None),
    "connect-error": (fault(httpx.ConnectError), None, "unreachable", None),
    "redirect-not-followed": (
        lambda request: httpx.Response(307, headers={"location": "https://evil.example/"}),
        None,
        "rejected",
        307,
    ),
    "unknown-code": (
        body(406, {"code": "99", "description": "x"}),
        "unknown_vendor_code",
        "rejected",
        406,
    ),
}


_ACCEPTED_BODY: dict[str, object] = dict(RECORDED["responses"]["accepted"]["body"])
_HTML = "<!DOCTYPE html><html><head><title>Netgsm</title></head><body>bakim</body></html>"

#: INT-576: a 2xx this endpoint is not documented to give -> (behaviour, the
#: typed refusal). Every one is reason ``malformed_response`` at status 200,
#: never a success and never retried: Netgsm may already have sent the code.
UNREADABLE: dict[str, tuple[Callable[[httpx.Request], Any], str]] = {
    # no documented code at all
    "plain-text-00-jobid": (bare(200, f"00 {JOBID}"), "unparseable_response"),
    "xml-otp-endpoint-answer": (elsewhere("xml_otp_accepted"), "unparseable_response"),
    "html-page": (bare(200, _HTML, "text/html; charset=utf-8"), "unparseable_response"),
    "empty-body": (bare(200), "unparseable_response"),
    "json-array": (body(200, [_ACCEPTED_BODY]), "unparseable_response"),
    "json-without-code": (
        body(200, {k: v for k, v in _ACCEPTED_BODY.items() if k != "code"}),
        "unparseable_response",
    ),
    "code-not-digits": (body(200, {**_ACCEPTED_BODY, "code": "OK"}), "unparseable_response"),
    "json-deeper-than-the-decoder": (
        bare(200, "[" * 100_000 + "]" * 100_000),
        "unparseable_response",
    ),
    # code 00, but not exactly one digit-string job id under a documented key
    "00-without-jobid": (
        body(200, {"code": "00", "description": "success"}),
        "accepted_without_job_id",
    ),
    "00-jobid-not-an-id": (
        body(200, {**_ACCEPTED_BODY, "jobid": "see https://evil.example/x"}),
        "accepted_without_job_id",
    ),
    "00-jobid-a-json-number": (
        body(200, {**_ACCEPTED_BODY, "jobid": int(JOBID)}),
        "accepted_without_job_id",
    ),
    "00-jobid-empty": (body(200, {**_ACCEPTED_BODY, "jobid": ""}), "accepted_without_job_id"),
    "00-both-spellings": (body(200, {**_ACCEPTED_BODY, "jobId": JOBID}), "accepted_without_job_id"),
    "00-xml-endpoint-spelling": (
        body(200, {"code": "00", "description": "success", "jobID": JOBID}),
        "accepted_without_job_id",
    ),
    # a code nobody documented, so nobody can say whether the SMS left
    "undocumented-code": (body(200, {"code": "99", "description": "x"}), "unknown_vendor_code"),
    "xml-style-code-0": (body(200, {"code": "0", "jobid": JOBID}), "unknown_vendor_code"),
    "send-xml-style-code-01": (body(200, {**_ACCEPTED_BODY, "code": "01"}), "unknown_vendor_code"),
}


def credentials() -> Any:
    return netgsm().NetgsmCredentials.parse(VAULT_DOC)


def adapter(
    vendor: Vendor, egress: EgressPolicy | None = None, log: InMemoryTransferLog | None = None
) -> Any:
    return netgsm().NetgsmSmsDeliveryAdapter(
        credentials(),
        egress=egress if egress is not None else policy(),
        inner=httpx.MockTransport(vendor),
        transfer_log=log if log is not None else InMemoryTransferLog(),
    )


def send(delivery: Any, phone: str = PHONE, code: str = CODE) -> Any:
    return run(delivery.send(phone_e164=phone, code=code))


def assert_clean(text: str, where: str) -> None:
    for secret in SECRETS:
        assert secret not in text, f"{where} carries a phone, code or password"


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
    return Vault({"api/netgsm": VAULT_DOC})
