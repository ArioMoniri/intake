"""INT-528 — the Netgsm OTP SMS adapter behind the INT-329 SMS port.

The owner chose Netgsm's OTP SMS product on 16 Oct 2026 (INT-358, GitHub #576).
This file pins the adapter; test_otp_netgsm_wiring.py pins where it is (and is
not) wired.

- Every vendor answer is replayed from ``tests/fixtures/netgsm/otp_rest_v2.json``,
  built from Netgsm's public documentation, behind the INT-018 guarded async
  transport with an injected resolver: no socket, no DNS, no vendor call.
- The wire body is enumerated by hand, exactly the documented three fields.
- Every documented vendor code maps to one typed refusal and one port reason,
  whatever HTTP status carries it; transport faults map to the port's reasons.
- No phone number, code or password reaches a log record, an exception, the
  transfer log or a metric label, on any path.
- The shipped allow-list has no Netgsm row, so the guard refuses the call
  before a byte leaves until the owner applies the egress patch.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx
import pytest
from api_harness import run
from intake_platform.egress import DataClass, EgressContext, EgressPolicy, load_allowlist
from netgsm_testkit import (
    CODE,
    CODE_REFUSALS,
    DOCUMENTED_CODES,
    FAULTS,
    JOBID,
    MSGHEADER,
    PASSWORD,
    PHONE,
    PHONE_NATIONAL,
    PUBLIC_ANSWER,
    RECORDED,
    SHIPPED_ALLOWLIST,
    USERCODE,
    VAULT_DOC,
    Vendor,
    accepted,
    adapter,
    assert_clean,
    body,
    credentials,
    empty_policy,
    netgsm,
    otp_module,
    record_text,
    replay,
    resolver,
    send,
)
from prometheus_client import REGISTRY


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def _sample(outcome: str) -> float:
    value = REGISTRY.get_sample_value(
        "otp_sms_delivery_total", {"vendor": "netgsm", "outcome": outcome}
    )
    return value or 0.0


def _failure(delivery: Any, phone: str = PHONE, code: str = CODE) -> Any:
    with pytest.raises(otp_module().OtpDeliveryError) as caught:
        send(delivery, phone, code)
    return caught.value


# --- the recorded contract ------------------------------------------------------------


def test_the_fixture_is_labelled_as_built_from_the_documentation() -> None:
    assert RECORDED["provenance"] == "built-from-documentation"
    assert RECORDED["source_url"] == "https://www.netgsm.com.tr/dokuman/#otp-sms"
    assert RECORDED["retrieved_on"] == "2026-10-16"
    assert "live call" in RECORDED["note"]
    assert RECORDED["endpoint"]["url"] == netgsm().NETGSM_OTP_URL


def test_the_wire_body_is_the_documented_request_shape_and_nothing_else(phi_egress: None) -> None:
    vendor = Vendor(accepted)
    send(adapter(vendor))
    [wire] = vendor.bodies
    assert set(wire) == set(RECORDED["documented_request"])
    sealed = netgsm().seal_otp_request(credentials(), phone_e164=PHONE, code=CODE)
    assert sealed.as_wire() == wire


# --- success --------------------------------------------------------------------------


def test_success_returns_the_vendor_job_id(phi_egress: None) -> None:
    vendor = Vendor(accepted)
    receipt = send(adapter(vendor))
    assert receipt.delivery_id == JOBID
    [request] = vendor.requests
    assert request.method == "POST"
    # the guard connects to the pinned address with the hostname intact
    assert request.url.scheme == "https"
    assert request.url.host == PUBLIC_ANSWER
    assert request.url.path == "/sms/rest/v2/otp"
    assert request.headers["host"] == "api.netgsm.com.tr"
    expected = base64.b64encode(f"{USERCODE}:{PASSWORD}".encode()).decode("ascii")
    assert request.headers["authorization"] == f"Basic {expected}"
    assert request.headers["content-type"] == "application/json"
    [wire] = vendor.bodies
    assert wire == {
        "msgheader": MSGHEADER,
        "msg": netgsm().SMS_TEMPLATE.format(code=CODE),
        "no": PHONE_NATIONAL,
    }


def test_success_counts_one_accepted_delivery(phi_egress: None) -> None:
    before = _sample("accepted")
    send(adapter(Vendor(accepted)))
    assert _sample("accepted") == before + 1


def test_the_send_awaits_and_the_loop_keeps_running(phi_egress: None) -> None:
    ticks: list[int] = []

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return accepted(request)

    async def scenario() -> Any:
        async def ticker() -> None:
            for tick in range(5):
                ticks.append(tick)
                await asyncio.sleep(0.005)

        task = asyncio.create_task(ticker())
        receipt = await adapter(Vendor(slow)).send(phone_e164=PHONE, code=CODE)
        await task
        return receipt

    assert run(scenario()).delivery_id == JOBID
    assert len(ticks) == 5


def test_the_adapter_has_no_marketing_path() -> None:
    """Owner, 16 Oct 2026: OTP-type, transactional only. The module names the
    OTP endpoint alone: no bulk-send endpoint and no İYS filter field, so a
    commercial message has no route through it."""
    import inspect
    import re

    source = inspect.getsource(netgsm())
    assert set(re.findall(r"/sms/[a-z0-9/]+", source)) == {"/sms/rest/v2/otp"}
    for other in ("/sms/rest/v2/send", "/sms/send/xml", "iysfilter", "template/send"):
        assert other not in source, other


# --- the message: one segment, no Turkish letters (the OTP product's rule) ---------------


def test_the_template_is_the_twilio_wording_folded_to_ascii() -> None:
    from intake_api.otp_twilio import SMS_TEMPLATE as WORDING

    fold = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    assert netgsm().SMS_TEMPLATE == WORDING.translate(fold)
    # pinned on its own too, so the copy outlives the unwired Twilio module
    assert netgsm().SMS_TEMPLATE == "Dogrulama kodunuz: {code}. Bu kodu kimseyle paylasmayiniz."


@pytest.mark.parametrize("code", ["0000", CODE, "9" * 10])
def test_every_rendered_message_is_ascii_and_one_segment(code: str) -> None:
    message = netgsm().SMS_TEMPLATE.format(code=code)
    assert message.isascii()
    assert len(message) <= netgsm().MAX_MESSAGE_LENGTH == 155


# --- every documented vendor code is a typed refusal ----------------------------------


def test_the_mapping_covers_exactly_the_documented_codes() -> None:
    assert set(CODE_REFUSALS) == set(DOCUMENTED_CODES)
    assert set(netgsm().VENDOR_CODE_REFUSALS) == set(DOCUMENTED_CODES)


@pytest.mark.parametrize("status", [406, 200], ids=["recorded-406", "same-body-at-200"])
@pytest.mark.parametrize("code", DOCUMENTED_CODES)
def test_each_documented_code_maps_to_one_typed_refusal(
    phi_egress: None, code: str, status: int
) -> None:
    refusal, reason = CODE_REFUSALS[code]
    before = _sample(refusal)
    error = _failure(adapter(Vendor(replay("error", code=code, status=status))))
    assert isinstance(error, netgsm().NetgsmDeliveryError)
    assert error.refusal == netgsm().NetgsmRefusal(refusal)
    assert error.reason == otp_module().OtpDeliveryFailure(reason)
    assert error.vendor_code == int(code)
    assert error.status_code == status
    assert _sample(refusal) == before + 1


def test_a_numeric_code_is_read_as_the_documented_string(phi_egress: None) -> None:
    """The documentation shows codes as strings ("00", "30"); a number in
    their place means the same thing, never a malformed answer."""
    receipt = send(adapter(Vendor(body(200, {"code": 0, "jobid": JOBID}))))
    assert receipt.delivery_id == JOBID
    error = _failure(adapter(Vendor(body(406, {"code": 30}))))
    assert error.refusal == netgsm().NetgsmRefusal.CREDENTIALS_REFUSED
    assert error.vendor_code == 30


@pytest.mark.parametrize("scenario", sorted(FAULTS))
def test_each_transport_fault_maps_to_one_port_reason(phi_egress: None, scenario: str) -> None:
    respond, refusal, reason, status = FAULTS[scenario]
    error = _failure(adapter(Vendor(respond)))
    assert error.reason == otp_module().OtpDeliveryFailure(reason)
    assert error.status_code == status
    expected = None if refusal is None else netgsm().NetgsmRefusal(refusal)
    assert error.refusal == expected


def test_a_failure_is_never_chained_to_the_transport_error(phi_egress: None) -> None:
    """A transport exception holds the request, and the request holds the body."""
    for scenario in ("timeout", "connect-error", "ok-not-json"):
        error = _failure(adapter(Vendor(FAULTS[scenario][0])))
        assert error.__cause__ is None and error.__context__ is None, scenario


# --- refused before the wire ------------------------------------------------------------


@pytest.mark.parametrize("phone", ["+4915112345678", "+903121234567", "5321234567", "+90532123456"])
def test_a_number_netgsm_cannot_reach_is_refused_before_the_wire(
    phi_egress: None, phone: str
) -> None:
    """OTP SMS goes to Turkish mobiles only; nothing abroad, no landline."""
    vendor = Vendor(accepted)
    error = _failure(adapter(vendor), phone=phone)
    assert error.refusal == netgsm().NetgsmRefusal.NOT_A_TR_MOBILE
    assert error.reason == otp_module().OtpDeliveryFailure.REJECTED
    assert vendor.requests == []


@pytest.mark.parametrize("code", ["", "12ab56", "1" * 11, "１２３４５６"])
def test_a_code_that_is_not_plain_digits_is_refused_before_the_wire(
    phi_egress: None, code: str
) -> None:
    vendor = Vendor(accepted)
    error = _failure(adapter(vendor), code=code)
    assert error.refusal == netgsm().NetgsmRefusal.CODE_NOT_SENDABLE
    assert vendor.requests == []


def test_an_egress_refusal_never_reaches_the_vendor(phi_egress: None) -> None:
    vendor = Vendor(accepted)
    error = _failure(adapter(vendor, empty_policy()))
    assert error.reason == otp_module().OtpDeliveryFailure.EGRESS_DENIED
    assert vendor.requests == []


def test_the_runtime_phi_gate_unset_refuses_even_a_listed_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INTAKE_ALLOW_PHI_EGRESS", raising=False)
    vendor = Vendor(accepted)
    error = _failure(adapter(vendor))
    assert error.reason == otp_module().OtpDeliveryFailure.EGRESS_DENIED
    assert vendor.requests == []


def test_the_shipped_allowlist_admits_netgsm_on_the_phi_tier_alone(phi_egress: None) -> None:
    """The owner's row (owner-528-netgsm-egress.patch): the SMS call clears the
    PHI tier and nothing else, and the adapter reaches the vendor through it."""
    allowlist = load_allowlist(SHIPPED_ALLOWLIST)
    shipped = EgressPolicy.for_tier(allowlist, "phi_path", resolver)
    assert shipped.check(netgsm().NETGSM_API_HOST, 443, netgsm().SMS_EGRESS).allowed
    dev = EgressPolicy.for_tier(allowlist, "dev", resolver)
    for data_class in DataClass:
        context = EgressContext(purpose=netgsm().SMS_EGRESS.purpose, data_class=data_class)
        assert not dev.check(netgsm().NETGSM_API_HOST, 443, context).allowed
    vendor = Vendor(accepted)
    assert send(adapter(vendor, shipped)).delivery_id == JOBID


def test_the_call_declares_the_sms_purpose_and_the_strictest_class() -> None:
    declared = netgsm().SMS_EGRESS
    assert declared.purpose.value == "sms_otp_delivery"
    assert declared.data_class is DataClass.PHI


# --- nothing personal escapes -----------------------------------------------------------


def _every_failure() -> list[Any]:
    behaviours = [replay("error", code=code) for code in DOCUMENTED_CODES]
    behaviours += [respond for respond, _, _, _ in FAULTS.values()]
    # a vendor whose description echoes the recipient and the message
    behaviours.append(body(406, {"code": "50", "description": f"{PHONE_NATIONAL} {CODE}"}))
    return behaviours


def test_no_log_record_error_or_transfer_record_carries_the_phone_code_or_password(
    phi_egress: None, caplog: pytest.LogCaptureFixture
) -> None:
    from intake_platform.egress import InMemoryTransferLog

    caplog.set_level(logging.DEBUG)
    log = InMemoryTransferLog()
    send(adapter(Vendor(accepted), log=log))
    for respond in _every_failure():
        error = _failure(adapter(Vendor(respond), log=log))
        assert_clean(f"{error} {error.args!r} {vars(error)!r}", "the error")
    assert caplog.records, "the adapter logs one line per outcome"
    for record in caplog.records:
        assert_clean(record_text(record), "a log record")
    assert log.entries
    for entry in log.entries:
        assert_clean(repr(entry), "a transfer record")


def test_a_failure_log_line_names_the_refusal_and_the_numeric_code_only(
    phi_egress: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    _failure(adapter(Vendor(replay("error", code="30"))))
    [line] = [r.getMessage() for r in caplog.records if r.name == "intake_api.otp_netgsm"]
    assert "refusal=credentials_refused" in line
    assert "vendor_code=30" in line
    assert "error message desc." not in line, "the vendor's description is never logged"


def test_metric_outcomes_are_a_closed_vocabulary() -> None:
    allowed = netgsm().DELIVERY_OUTCOMES
    assert "accepted" in allowed
    assert {r.value for r in netgsm().NetgsmRefusal} <= allowed
    assert {r.value for r in otp_module().OtpDeliveryFailure} <= allowed
    for metric in REGISTRY.collect():
        if metric.name != "otp_sms_delivery":
            continue
        for sample in metric.samples:
            assert sample.labels.get("vendor") in (None, "netgsm")
            if "outcome" in sample.labels:
                assert sample.labels["outcome"] in allowed
                assert_clean(repr(sample.labels), "a metric label")


# --- credentials: shape-checked, named by field, never echoed ----------------------------


@pytest.mark.parametrize("field", ["usercode", "password", "msgheader"])
@pytest.mark.parametrize("empty", [None, "", "   "])
def test_a_missing_value_is_refused_by_name(field: str, empty: str | None) -> None:
    document = {key: value for key, value in VAULT_DOC.items() if key != field}
    if empty is not None:
        document[field] = empty
    with pytest.raises(netgsm().NetgsmConfigError) as caught:
        netgsm().NetgsmCredentials.parse(document)
    assert field in str(caught.value)
    assert_clean(str(caught.value), "a config refusal")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("usercode", "85012345"),
        ("usercode", "850123456a"),
        ("msgheader", "AB"),
        ("msgheader", "TWELVECHARSX"),
        ("msgheader", "ÖNVİZİT"),
        ("msgheader", " ONVIZIT"),
        ("password", 12345678),
    ],
)
def test_a_malformed_value_is_refused_by_name_without_its_value(field: str, value: object) -> None:
    with pytest.raises(netgsm().NetgsmConfigError) as caught:
        netgsm().NetgsmCredentials.parse({**VAULT_DOC, field: value})
    assert field in str(caught.value)
    assert str(value) not in str(caught.value)


def test_the_password_never_reaches_repr() -> None:
    assert PASSWORD not in repr(credentials())
    sealed = netgsm().seal_otp_request(credentials(), phone_e164=PHONE, code=CODE)
    assert_clean(repr(sealed), "the sealed request's repr")
