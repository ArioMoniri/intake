"""INT-583 — the APNs adapter behind the push gateway port (GitHub #982, D35).

The notice goes straight to Apple's push service (no relay): an ES256 provider
token from the ``.p8`` key in OpenBao, ``POST /3/device/<token>`` over HTTP/2,
and Apple's documented answers mapped to a closed failure vocabulary. Every
answer here is replayed from ``tests/fixtures/apns/responses.json``; nothing
reaches Apple. Near misses throughout: a 400 that is not about the token, a
P-384 key, an 11-character key id, an undocumented reason string.
"""

from __future__ import annotations

import base64
import importlib
import json
import logging
from pathlib import Path
from types import ModuleType
from typing import Any

import apns_testkit as kit
import httpx
import pytest
from api_harness import run
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from intake_api.settings import ApiSettings
from intake_platform.egress import InMemoryTransferLog
from prometheus_client import REGISTRY

NOW = 1_761_800_000.0
#: PEM armour around text that is not a key, assembled from parts so this file
#: holds no whole key header for a secret scanner to read as a key.
_ARMOUR = "PRIVATE" + " KEY-----"
ARMOURED_NOT_A_KEY = f"-----BEGIN {_ARMOUR}\nnot a key\n-----END {_ARMOUR}\n"


def apns() -> ModuleType:
    """Resolved per call, so each test fails on its own line before the module exists."""
    return importlib.import_module("intake_api.push_apns")


def port() -> ModuleType:
    return importlib.import_module("intake_api.push_port")


def alert() -> Any:
    notice = importlib.import_module("intake_api.sign_in_notice")
    return notice.NOTICE_ALERT


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def phi_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def gateway(
    vendor: kit.Vendor,
    *,
    key: ec.EllipticCurvePrivateKey | None = None,
    clock: Clock | None = None,
    policy: Any = None,
    transfer_log: Any = None,
) -> Any:
    module = apns()
    credentials = module.ApnsCredentials.parse(kit.vault_doc(key or kit.signing_key()))
    return module.ApnsPushGateway(
        credentials,
        topic=kit.TOPIC,
        egress=policy if policy is not None else kit.policy(),
        inner=vendor.transport(),
        transfer_log=transfer_log,
        now_fn=clock or Clock(),
    )


def send(gw: Any, token: str = kit.TOKEN_A) -> Any:
    return run(gw.send(device_token=token, alert=alert()))


def _count(outcome: str) -> float:
    value = REGISTRY.get_sample_value("push_delivery_total", {"vendor": "apns", "outcome": outcome})
    return value or 0.0


def _b64(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


# --- the request: exactly Apple's contract, nothing more -----------------------------------


def test_an_accepted_push_returns_apns_id_and_counts(phi_gate: None) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    before = _count("accepted")
    receipt = send(gateway(vendor))
    assert receipt.push_id == kit.RECORDED["responses"]["accepted"]["headers"]["apns-id"]
    assert _count("accepted") == before + 1


def test_the_request_is_apples_contract_and_nothing_else(phi_gate: None) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    send(gateway(vendor))
    [request] = vendor.requests
    assert request.method == "POST"
    assert request.url.path == f"/3/device/{kit.TOKEN_A}"
    assert request.headers["host"] == kit.HOST  # pinned address, the name kept
    assert request.headers["apns-push-type"] == "alert"
    assert request.headers["apns-topic"] == kit.TOPIC
    assert request.headers["apns-priority"] == "10"
    assert request.headers["apns-collapse-id"] == "intake-sign-in"
    assert len(request.headers["apns-collapse-id"].encode()) <= 64
    assert int(request.headers["apns-expiration"]) == int(NOW) + apns().NOTICE_EXPIRY_S
    assert request.headers["authorization"].startswith("bearer ")
    # the body is the notice's two constant strings, under aps
    assert vendor.bodies == [
        {"aps": {"alert": {"title": alert().title, "body": alert().body}, "sound": "default"}}
    ]
    assert len(request.content) <= 4096


def test_the_provider_token_is_an_es256_jwt_apple_can_verify(phi_gate: None) -> None:
    key = kit.signing_key()
    vendor = kit.Vendor(kit.replay("accepted"))
    send(gateway(vendor, key=key))
    jwt = vendor.requests[0].headers["authorization"].removeprefix("bearer ")
    header_b64, claims_b64, signature_b64 = jwt.split(".")
    assert json.loads(_b64(header_b64)) == {"alg": "ES256", "kid": kit.KEY_ID}
    assert json.loads(_b64(claims_b64)) == {"iss": kit.TEAM_ID, "iat": int(NOW)}
    raw = _b64(signature_b64)
    assert len(raw) == 64
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    key.public_key().verify(der, f"{header_b64}.{claims_b64}".encode(), ec.ECDSA(hashes.SHA256()))


def test_the_provider_token_is_renewed_inside_apples_window(phi_gate: None) -> None:
    """Apple: refresh no more often than every 20 minutes, no less often than
    every 60. Near miss: one second before the renewal, the same token."""
    clock = Clock()
    vendor = kit.Vendor(kit.replay("accepted"))
    gw = gateway(vendor, clock=clock)
    renew = apns().PROVIDER_TOKEN_RENEW_S
    assert 20 * 60 <= renew < 60 * 60
    send(gw)
    clock.now += renew - 1
    send(gw)
    clock.now += 1
    send(gw)
    tokens = [r.headers["authorization"] for r in vendor.requests]
    assert tokens[0] == tokens[1] != tokens[2]


def test_a_stale_provider_token_is_reminted_on_the_next_send(phi_gate: None) -> None:
    clock = Clock()
    vendor = kit.Vendor(kit.sequence("expired_provider_token", "accepted"))
    gw = gateway(vendor, clock=clock)
    with pytest.raises(port().PushDeliveryError) as refused:
        send(gw)
    assert refused.value.reason is port().PushFailure.AUTH_FAILED
    clock.now += 1
    send(gw)
    first, second = (r.headers["authorization"] for r in vendor.requests)
    assert first != second


# --- the answers: Apple's documented outcomes, mapped -----------------------------------------


@pytest.mark.parametrize(
    ("scenario", "failure"),
    [
        ("unregistered", "token_gone"),
        ("expired_token", "token_gone"),
        ("bad_device_token", "token_gone"),
        ("device_token_not_for_topic", "token_gone"),
        # near misses: a 400 that is not about the token keeps it
        ("bad_topic", "rejected"),
        ("bad_collapse_id", "rejected"),
        ("payload_too_large", "rejected"),
        ("forbidden", "auth_failed"),
        ("invalid_provider_token", "auth_failed"),
        ("too_many_requests", "rate_limited"),
        ("too_many_provider_token_updates", "rate_limited"),
        ("internal_server_error", "vendor_unavailable"),
        ("service_unavailable", "vendor_unavailable"),
        ("shutdown", "vendor_unavailable"),
    ],
)
def test_every_documented_refusal_maps_to_one_closed_reason(
    phi_gate: None, scenario: str, failure: str
) -> None:
    vendor = kit.Vendor(kit.replay(scenario))
    before = _count(failure)
    with pytest.raises(port().PushDeliveryError) as refused:
        send(gateway(vendor))
    assert refused.value.reason == failure
    assert refused.value.status_code == kit.RECORDED["responses"][scenario]["status"]
    assert _count(failure) == before + 1


def test_only_token_gone_drops_the_token() -> None:
    assert port().PUSH_FAILURES_THAT_DROP_THE_TOKEN == {port().PushFailure.TOKEN_GONE}


def test_a_200_without_an_apns_id_is_not_a_receipt(phi_gate: None) -> None:
    """A near miss of the accepted answer: the same status, no handle."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    with pytest.raises(port().PushDeliveryError) as refused:
        send(gateway(kit.Vendor(respond)))
    assert refused.value.reason is port().PushFailure.MALFORMED_RESPONSE


def test_an_undocumented_reason_is_never_logged(
    phi_gate: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Vendor text never reaches a log line: only Apple's documented reason
    strings are named, anything else is '-'."""
    caplog.set_level(logging.WARNING)
    canary = "Canary90532111445"

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"reason": canary}, request=request)

    with pytest.raises(port().PushDeliveryError):
        send(gateway(kit.Vendor(respond)))
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert canary not in text and "apns_reason=-" in text
    caplog.clear()
    with pytest.raises(port().PushDeliveryError):
        send(gateway(kit.Vendor(kit.replay("bad_topic"))))
    assert "apns_reason=BadTopic" in "\n".join(r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    ("fault", "failure"),
    [
        (httpx.ConnectTimeout("connect timed out"), "timeout"),
        (httpx.ConnectError("refused"), "unreachable"),
    ],
)
def test_a_transport_fault_is_typed_and_chains_nothing(
    phi_gate: None, fault: Exception, failure: str
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise fault

    with pytest.raises(port().PushDeliveryError) as refused:
        send(gateway(kit.Vendor(respond)))
    assert refused.value.reason == failure
    assert refused.value.__cause__ is None and refused.value.__context__ is None


@pytest.mark.parametrize("token", ["a1" * 31 + "a", "A1" * 32, "zz" * 32, "a1" * 101, ""])
def test_a_malformed_token_is_refused_before_the_wire(phi_gate: None, token: str) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    with pytest.raises(port().PushDeliveryError) as refused:
        send(gateway(vendor), token)
    assert refused.value.reason is port().PushFailure.REJECTED
    assert vendor.requests == []


# --- egress: the owner's row, the runtime gate -----------------------------------------------


def test_without_the_owners_row_nothing_leaves(phi_gate: None) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    log = InMemoryTransferLog()
    with pytest.raises(port().PushDeliveryError) as refused:
        send(gateway(vendor, policy=kit.empty_policy(), transfer_log=log))
    assert refused.value.reason is port().PushFailure.EGRESS_DENIED
    assert vendor.requests == []
    [record] = log.entries
    # a refused host is logged with no purpose granted, and nothing left
    assert (record.decision, record.host, record.bytes_out) == ("deny", kit.HOST, 0)


def test_with_the_row_but_the_gate_shut_nothing_leaves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTAKE_ALLOW_PHI_EGRESS", raising=False)
    vendor = kit.Vendor(kit.replay("accepted"))
    with pytest.raises(port().PushDeliveryError) as refused:
        send(gateway(vendor))
    assert refused.value.reason is port().PushFailure.EGRESS_DENIED
    assert vendor.requests == []


def test_the_call_declares_the_push_purpose_as_personal_data() -> None:
    declared = apns().PUSH_EGRESS
    assert declared.purpose.value == "push_security_notice"
    assert declared.data_class.is_personal


# --- credentials: OpenBao only, shapes checked, never printed ---------------------------------


def test_credentials_parse_and_never_print_the_key() -> None:
    key = kit.signing_key()
    credentials = apns().ApnsCredentials.parse(kit.vault_doc(key))
    assert (credentials.key_id, credentials.team_id) == (kit.KEY_ID, kit.TEAM_ID)
    assert "PRIVATE" not in repr(credentials) and "signing_key" not in repr(credentials)


@pytest.mark.parametrize("missing", ["key_p8", "key_id", "team_id"])
def test_a_missing_field_is_named_and_no_value_is(missing: str) -> None:
    document = kit.vault_doc(kit.signing_key())
    document[missing] = "   "
    with pytest.raises(apns().ApnsConfigError) as refused:
        apns().ApnsCredentials.parse(document)
    assert missing in str(refused.value) and kit.TEAM_ID not in str(refused.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("key_id", "ABC123DEFGH"),  # 11 characters
        ("key_id", "abc123defg"),  # lower case
        ("team_id", "TEAM12345"),  # 9 characters
        ("key_p8", ARMOURED_NOT_A_KEY),
        ("key_p8", kit.p8(ec.generate_private_key(ec.SECP384R1()))),  # not ES256
    ],
)
def test_a_malformed_field_is_named(field: str, value: str) -> None:
    document = kit.vault_doc(kit.signing_key())
    document[field] = value
    with pytest.raises(apns().ApnsConfigError) as refused:
        apns().ApnsCredentials.parse(document)
    assert field in str(refused.value)


# --- wiring: fail closed with a typed reason ---------------------------------------------------


class Vault:
    """The OpenBao reader, recording which paths were read."""

    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents
        self.reads: list[str] = []

    def get_kv(self, path: str) -> dict[str, Any]:
        self.reads.append(path)
        return self.documents[path]


def _settings(allowlist: Path, environment: str | None = None) -> ApiSettings:
    return ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
        audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
        kek_mode="transit",
        environment="production",
        egress_allowlist_path=allowlist,
        app_attest_environment=environment,
    )


def test_the_shipped_allowlist_refuses_apns_so_no_key_is_read() -> None:
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    result = apns().push_gateway_from_settings(_settings(kit.SHIPPED_ALLOWLIST), vault)
    assert result is port().PushUnconfigured.EGRESS_REFUSED
    assert vault.reads == []


def test_with_the_row_the_gate_and_the_key_the_gateway_is_wired(
    tmp_path: Path, phi_gate: None
) -> None:
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    result = apns().push_gateway_from_settings(
        _settings(kit.allowlist_with_the_row(tmp_path)), vault
    )
    assert isinstance(result, apns().ApnsPushGateway)
    assert result.host == kit.HOST
    assert vault.reads == ["api/apns"]


def test_a_development_build_pushes_to_the_sandbox(tmp_path: Path, phi_gate: None) -> None:
    """The APNs host follows App Attest's environment (one provisioning
    profile carries both). Near miss: the production row does not admit it."""
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    sandbox = _settings(kit.allowlist_with_the_row(tmp_path, kit.SANDBOX_HOST), "development")
    result = apns().push_gateway_from_settings(sandbox, vault)
    assert isinstance(result, apns().ApnsPushGateway) and result.host == kit.SANDBOX_HOST
    production_row_only = _settings(kit.allowlist_with_the_row(tmp_path), "development")
    assert (
        apns().push_gateway_from_settings(production_row_only, vault)
        is port().PushUnconfigured.EGRESS_REFUSED
    )
    assert apns().apns_environment("Development") == "production"


def test_no_key_in_openbao_is_no_channel(tmp_path: Path, phi_gate: None) -> None:
    result = apns().push_gateway_from_settings(
        _settings(kit.allowlist_with_the_row(tmp_path)), Vault({})
    )
    assert result is port().PushUnconfigured.NO_CREDENTIALS


def test_a_malformed_key_is_no_channel_and_names_no_value(
    tmp_path: Path, phi_gate: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    document = kit.vault_doc(kit.signing_key())
    document["team_id"] = "not-a-team"
    result = apns().push_gateway_from_settings(
        _settings(kit.allowlist_with_the_row(tmp_path)), Vault({"api/apns": document})
    )
    assert result is port().PushUnconfigured.MALFORMED_CREDENTIALS
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "team_id" in text and "not-a-team" not in text and "PRIVATE KEY" not in text


def test_without_http2_there_is_no_channel(
    tmp_path: Path, phi_gate: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = apns()
    real = module.importlib.util.find_spec
    monkeypatch.setattr(
        module.importlib.util, "find_spec", lambda name: None if name == "h2" else real(name)
    )
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    result = module.push_gateway_from_settings(
        _settings(kit.allowlist_with_the_row(tmp_path)), vault
    )
    assert result is port().PushUnconfigured.HTTP2_UNAVAILABLE
    assert vault.reads == []


def test_http2_support_is_installed() -> None:
    """APNs speaks HTTP/2 only; the shipped API image carries h2."""
    assert importlib.util.find_spec("h2") is not None


def test_the_fixture_names_its_source_and_date() -> None:
    assert kit.RECORDED["retrieved_on"] == "2026-10-30"
    assert "developer.apple.com" in kit.RECORDED["_source"]
    reasons = {
        r["body"]["reason"] for r in kit.RECORDED["responses"].values() if r["body"] is not None
    }
    assert reasons <= apns().APNS_DOCUMENTED_REASONS


def test_httpx_request_lines_never_carry_the_device_token(
    phi_gate: None, caplog: pytest.LogCaptureFixture
) -> None:
    """httpx logs each request line with its full URL at INFO, and an APNs URL
    holds the token. Near miss: a line without an APNs path is left alone."""
    caplog.set_level(logging.INFO)
    send(gateway(kit.Vendor(kit.replay("accepted"))))
    lines = [r.getMessage() for r in caplog.records if r.name == "httpx"]
    assert lines and all(kit.TOKEN_A not in line for line in lines)
    assert any("/3/device/<redacted>" in line for line in lines)
    logging.getLogger("httpx").info("HTTP Request: %s %s", "GET", "https://example.test/healthz")
    assert caplog.records[-1].getMessage() == "HTTP Request: GET https://example.test/healthz"
