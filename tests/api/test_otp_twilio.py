"""INT-329 — the Twilio SMS delivery adapter: tested, async, and silent about PII.

Production audit 2026-09-26, finding F13. The adapter that existed off main made
a blocking ``httpx.post`` inside the async OTP route, had no tests, read its
credentials from the environment and called a host that is not on the egress
allow-list. This file pins the adapter; test_otp_twilio_wiring.py pins where it
is (and is not) wired.

- Every exchange runs over ``httpx.MockTransport`` behind the INT-018 guarded
  transport with an injected resolver: no socket, no DNS, no vendor call.
- Success, 4xx (invalid number), 401/403 (auth), 429, 5xx, timeout, connect
  failure, an unfollowed redirect and a 2xx without a message id each map to
  one typed ``OtpDeliveryError`` reason.
- No phone number, code or auth token reaches a log record, an exception or
  the transfer log, on any of those paths.
- The send awaits: the event loop keeps running while the vendor answers.
- The shipped allow-list has no SMS row, so the guard refuses the call before
  a byte leaves (the owner's DPA and cross-border decision).
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx
import pytest
from intake_platform.egress import EgressPolicy, EgressPurpose, InMemoryTransferLog, load_allowlist
from twilio_testkit import (
    ACCOUNT_SID,
    AUTH_TOKEN,
    CODE,
    FAILURES,
    MESSAGE_SID,
    PHONE,
    PUBLIC_ANSWER,
    SENDER,
    SERVICE_SID,
    SHIPPED_ALLOWLIST,
    VAULT_DOC,
    Vendor,
    adapter,
    assert_clean,
    created,
    credentials,
    empty_policy,
    otp_module,
    record_text,
    refused,
    resolver,
    send,
    twilio,
)


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


# --- success ------------------------------------------------------------------------


def test_success_returns_the_vendor_message_id(phi_egress: None) -> None:
    vendor = Vendor(created)
    receipt = send(adapter(vendor))
    assert receipt.delivery_id == MESSAGE_SID
    [request] = vendor.requests
    assert request.method == "POST"
    assert request.url.path == f"/2010-04-01/Accounts/{ACCOUNT_SID}/Messages.json"
    expected = base64.b64encode(f"{ACCOUNT_SID}:{AUTH_TOKEN}".encode()).decode("ascii")
    assert request.headers["authorization"] == f"Basic {expected}"
    [body] = vendor.bodies
    assert body["To"] == [PHONE]
    assert body["From"] == [SENDER]
    assert "MessagingServiceSid" not in body


def test_the_request_leaves_through_the_guard_pinned_to_one_lookup(phi_egress: None) -> None:
    """INT-018's resolve-once-and-pin applies: the socket gets the pinned
    address, TLS still verifies the vendor's name, and the transfer log has
    one allow row with the declared purpose and data class."""
    vendor, log = Vendor(created), InMemoryTransferLog()
    send(adapter(vendor, log=log))
    [request] = vendor.requests
    assert request.url.host == PUBLIC_ANSWER
    assert request.headers["host"] == "api.twilio.com"
    assert request.extensions["sni_hostname"] == "api.twilio.com"
    [record] = log.entries
    assert (record.decision, record.host, record.purpose) == (
        "allow",
        "api.twilio.com",
        EgressPurpose("sms_otp_delivery"),
    )
    assert str(record.data_class) == "phi"


def test_a_messaging_service_sender_uses_the_service_parameter(phi_egress: None) -> None:
    vendor = Vendor(created)
    send(adapter(vendor, sender=SERVICE_SID))
    [body] = vendor.bodies
    assert body["MessagingServiceSid"] == [SERVICE_SID]
    assert "From" not in body


def test_the_sms_copy_is_the_turkish_siz_template_with_the_code(phi_egress: None) -> None:
    vendor = Vendor(created)
    send(adapter(vendor))
    [body] = vendor.bodies
    assert body["Body"] == [f"Doğrulama kodunuz: {CODE}. Bu kodu kimseyle paylaşmayınız."]


# --- the send awaits ------------------------------------------------------------------


def test_the_send_is_a_coroutine() -> None:
    assert asyncio.iscoroutinefunction(twilio().TwilioSmsDeliveryAdapter.send)
    assert asyncio.iscoroutinefunction(otp_module().DevLogDeliveryAdapter.send)


def test_the_send_never_blocks_the_event_loop(phi_egress: None) -> None:
    """While the vendor takes its time, other coroutines keep running. The old
    adapter's synchronous ``httpx.post`` held the loop for up to 8 s."""

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return created(request)

    delivery = adapter(Vendor(slow))
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    async def scenario() -> Any:
        task = asyncio.create_task(ticker())
        try:
            return await delivery.send(phone_e164=PHONE, code=CODE)
        finally:
            task.cancel()

    assert asyncio.run(scenario()).delivery_id == MESSAGE_SID
    assert ticks >= 3, f"the loop ran {ticks} ticks during a 50 ms send"


# --- failures: one typed reason each ------------------------------------------------


@pytest.mark.parametrize("scenario", sorted(FAILURES))
def test_each_failure_maps_to_one_typed_reason(phi_egress: None, scenario: str) -> None:
    respond, reason, status = FAILURES[scenario]
    with pytest.raises(otp_module().OtpDeliveryError) as caught:
        send(adapter(Vendor(respond)))
    assert str(caught.value.reason) == reason
    assert caught.value.status_code == status


def test_a_vendor_error_code_is_kept_as_a_number_only(phi_egress: None) -> None:
    with pytest.raises(otp_module().OtpDeliveryError) as caught:
        send(adapter(Vendor(refused(400, 21211))))
    assert caught.value.vendor_code == 21211


def test_the_shipped_allowlist_refuses_the_vendor_before_a_byte_leaves(phi_egress: None) -> None:
    """The SHIPPED allow-list has no SMS row (awaiting the owner), so the guard
    refuses before resolving and before the transport is reached."""
    vendor = Vendor(created)
    shipped = EgressPolicy.for_tier(load_allowlist(SHIPPED_ALLOWLIST), "phi_path", resolver)
    with pytest.raises(otp_module().OtpDeliveryError) as caught:
        send(adapter(vendor, egress=shipped))
    assert str(caught.value.reason) == "egress_denied"
    assert vendor.requests == []


def test_the_runtime_phi_gate_still_applies_to_a_listed_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without INTAKE_ALLOW_PHI_EGRESS=explicit-yes even a phi_allowed row
    refuses (INT-018's double gate)."""
    monkeypatch.delenv("INTAKE_ALLOW_PHI_EGRESS", raising=False)
    vendor = Vendor(created)
    with pytest.raises(otp_module().OtpDeliveryError) as caught:
        send(adapter(vendor))
    assert str(caught.value.reason) == "egress_denied"
    assert vendor.requests == []


# --- nothing identifying leaves in a log, an error or the transfer log -------------


@pytest.mark.parametrize("scenario", ["success", *sorted(FAILURES), "egress-denied"])
def test_no_phone_code_or_token_in_any_log_error_or_transfer_record(
    phi_egress: None, scenario: str, caplog: pytest.LogCaptureFixture
) -> None:
    log = InMemoryTransferLog()
    if scenario == "egress-denied":
        delivery = adapter(Vendor(created), empty_policy(), log)
    else:
        respond = created if scenario == "success" else FAILURES[scenario][0]
        delivery = adapter(Vendor(respond), log=log)
    caplog.set_level(logging.DEBUG)
    try:
        send(delivery)
    except otp_module().OtpDeliveryError as exc:
        assert_clean(f"{exc!s} {exc!r} {exc.args!r} {vars(exc)!r}", "the raised error")
        assert exc.__cause__ is None and exc.__context__ is None, (
            "a chained transport error carries the request, and the request carries the body"
        )
    assert any(record.name == "intake_api.otp_twilio" for record in caplog.records), (
        "the adapter logs one ids-only line per outcome"
    )
    for record in caplog.records:
        assert_clean(record_text(record), f"log record {record.name}")
    for entry in log.entries:
        assert_clean(repr(entry), "the transfer log")


def test_the_credentials_never_render_the_token() -> None:
    rendered = f"{credentials()!r} {credentials()!s}"
    assert AUTH_TOKEN not in rendered


# --- credentials: all three, well-formed, refused by name only --------------------


@pytest.mark.parametrize("field", ["account_sid", "auth_token", "from"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_each_missing_value_is_refused_by_name(field: str, value: str | None) -> None:
    doc: dict[str, object] = dict(VAULT_DOC)
    if value is None:
        del doc[field]
    else:
        doc[field] = value
    with pytest.raises(twilio().TwilioConfigError) as caught:
        twilio().TwilioCredentials.parse(doc)
    assert field in str(caught.value)
    assert_clean(str(caught.value), "the config error")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_sid", "AC123"),
        ("account_sid", "AC" + "0" * 32 + "/../../Calls"),
        ("from", "05321234567"),
        ("from", "not a sender id!"),
        ("auth_token", 12345),
    ],
)
def test_a_malformed_value_is_refused_without_echoing_it(field: str, value: object) -> None:
    with pytest.raises(twilio().TwilioConfigError) as caught:
        twilio().TwilioCredentials.parse({**VAULT_DOC, field: value})
    assert field in str(caught.value)
    assert str(value) not in str(caught.value)


def test_an_alphanumeric_sender_id_is_accepted() -> None:
    parsed = twilio().TwilioCredentials.parse({**VAULT_DOC, "from": "ONVIZIT"})
    assert parsed.sender == "ONVIZIT"
