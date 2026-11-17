"""INT-576 — Netgsm's answer, read as documented; an unreadable 200 is never retried.

28 Oct 2026: the owner's real OTP send on the synthetic host logged
``refusal=- reason=malformed_response http_status=200 vendor_code=-``, and the
SMS from the approved sender arrived anyway, after both tries. The request,
the credentials, the header, Netgsm's IP allow-list and the SMS proxy
(ADR-042) all worked; INT-528's parser knew only the documentation's sample.

These tests replay ``tests/fixtures/netgsm/otp_rest_v2.json``, re-derived from
Netgsm's documentation and its official SDKs (verbatim snapshots beside it in
``sources/``) and never captured from a live call:

- both documented success shapes of ``/sms/rest/v2/otp`` give a receipt with
  the job id: ``jobid`` (the documentation's sample) and ``jobId`` (Netgsm's
  JS SDK, its response type and its integration test against this endpoint);
- every documented OTP error code is one typed refusal (test_otp_netgsm.py);
- any other 2xx is a typed refusal (``unparseable_response``,
  ``accepted_without_job_id``, ``unknown_vendor_code``): never a success,
  sent exactly once, and not retryable, because Netgsm may have sent the code;
- the owner's opt-in diagnostic sees the answer's structure and no value.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

import httpx
import pytest
from netgsm_testkit import (
    CODE,
    DOCUMENTED_CODES,
    FAULTS,
    JOBID,
    PHONE,
    PHONE_NATIONAL,
    RECORDED,
    REPO,
    SUCCESS_SCENARIOS,
    UNREADABLE,
    Vendor,
    adapter,
    assert_clean,
    bare,
    body,
    netgsm,
    otp_module,
    record_text,
    replay,
    send,
    shape_module,
)
from prometheus_client import REGISTRY

SOURCES = {source["name"]: source for source in RECORDED["sources"]}


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def _sample(outcome: str) -> float:
    value = REGISTRY.get_sample_value(
        "otp_sms_delivery_total", {"vendor": "netgsm", "outcome": outcome}
    )
    return value or 0.0


def _failure(vendor: Vendor) -> Any:
    with pytest.raises(otp_module().OtpDeliveryError) as caught:
        send(adapter(vendor))
    return caught.value


def _snapshot(name: str) -> str:
    return (REPO / SOURCES[name]["snapshot"]).read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    head = text.index(start) + len(start)
    return text[head : text.index(end, head)]


# --- the shape, settled from the sources ------------------------------------------------


def test_the_fixture_is_derived_from_the_documentation_and_sdk_never_a_live_call() -> None:
    assert RECORDED["provenance"] == "derived-from-documentation-and-sdk"
    assert RECORDED["retrieved_on"] == "2026-10-28"
    assert "live call" in RECORDED["note"]
    assert set(SOURCES) == {"netgsm-dokuman", "netgsm-sms-js", "netgsm1-otp", "netgsm-sms-python"}
    for source in SOURCES.values():
        snapshot = REPO / source["snapshot"]
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == source["snapshot_sha256"]
        text = snapshot.read_text(encoding="utf-8")
        header = text.split("\n---\n", 1)[0]
        assert "# retrieved_on: 2026-10-28" in header, source["name"]
        assert re.search(r"^# (url|source): ", header, re.MULTILINE), source["name"]
        assert re.search(r"sha256:? [0-9a-f]{64}", text), f"{source['name']} names no sha256"


def test_the_recorded_bodies_are_the_documentation_s_own_samples() -> None:
    otp = _between(_snapshot("netgsm-dokuman"), "## OTP SMS\n", "\n[...]")
    success = _between(otp, "#### Örnek Başarılı Cevap (Success Response)\n```json\n", "```")
    error = _between(otp, "#### Örnek Hata Cevabı (Error Response)\n```json\n", "```")
    assert json.loads(success) == RECORDED["responses"]["accepted"]["body"]
    assert json.loads(error) == RECORDED["responses"]["error"]["body"]
    assert "POST https://api.netgsm.com.tr/sms/rest/v2/otp" in otp
    assert RECORDED["endpoint"]["url"] == netgsm().NETGSM_OTP_URL


def test_the_sdk_shape_is_the_js_sdk_s_otp_response_type() -> None:
    js = _snapshot("netgsm-sms-js")
    otp_type = _between(js, "export interface OtpSmsResponse {", "}")
    assert "jobId?: string;" in otp_type and "jobid" not in otp_type
    assert "expect(smsResponse.jobId).toBeTruthy();" in js
    sdk = RECORDED["responses"]["accepted_sdk"]["body"]
    assert set(sdk) == {"code", "description", "jobId"} and sdk["code"] == "00"
    assert "otp" not in _snapshot("netgsm-sms-python").split("\n---\n", 1)[1].lower()


def test_the_documented_codes_are_exactly_the_union_of_the_three_sources() -> None:
    otp = _between(_snapshot("netgsm-dokuman"), "## OTP SMS\n", "\n[...]")
    docs: set[str] = set()
    for low, high in re.findall(r"^\| `(\d+)(?:-(\d+))?` \|", otp, re.MULTILINE):
        docs |= {str(code) for code in range(int(low), int(high or low) + 1)}
    enum = _between(_snapshot("netgsm-sms-js"), "export enum SendOtpSmsErrorCode {", "}")
    js = set(re.findall(r'= "(\d+)"', enum)) - {"00", "5000"}
    php = set(re.findall(r"^\s*\d+\|\s+(\d+)=>'", _snapshot("netgsm1-otp"), re.MULTILINE))
    assert docs == {"20", "30", "40", "41", "50", "51", "52", "60", "70", "100"}
    assert set(DOCUMENTED_CODES) == docs | js | php
    for code, entry in RECORDED["documented_error_codes"].items():
        named = {"netgsm-dokuman": docs, "netgsm-sms-js": js, "netgsm1-otp": php}
        assert {name for name, codes in named.items() if code in codes} == set(entry["sources"])


def test_the_job_id_is_read_under_this_endpoint_s_documented_keys_only() -> None:
    assert set(netgsm().JOB_ID_KEYS) == set(RECORDED["job_id_keys"]) == {"jobid", "jobId"}


# --- the documented successes ----------------------------------------------------------


@pytest.mark.parametrize("scenario", SUCCESS_SCENARIOS)
def test_each_documented_success_shape_is_a_receipt_with_the_job_id(
    phi_egress: None, scenario: str
) -> None:
    before = _sample("accepted")
    vendor = Vendor(replay(scenario))
    receipt = send(adapter(vendor))
    assert receipt.delivery_id == JOBID
    assert len(vendor.requests) == 1
    assert _sample("accepted") == before + 1


def test_a_success_body_carrying_a_documented_error_code_is_that_refusal(phi_egress: None) -> None:
    """Near miss: the success sample with code 30 in place of 00. The code
    decides; a job id beside it proves nothing."""
    accepted = RECORDED["responses"]["accepted"]["body"]
    error = _failure(Vendor(body(200, {**accepted, "code": "30"})))
    assert error.refusal == netgsm().NetgsmRefusal.CREDENTIALS_REFUSED
    assert error.vendor_code == 30
    assert error.retryable, "Netgsm said it refused, so nothing was sent"


# --- anything else at a 2xx: typed, once, never retried ---------------------------------


@pytest.mark.parametrize("scenario", sorted(UNREADABLE))
def test_an_unreadable_2xx_is_a_typed_refusal_sent_once_and_never_retryable(
    phi_egress: None, scenario: str
) -> None:
    respond, refusal = UNREADABLE[scenario]
    before = _sample(refusal)
    vendor = Vendor(respond)
    error = _failure(vendor)
    assert isinstance(error, netgsm().NetgsmDeliveryError)
    assert error.refusal == netgsm().NetgsmRefusal(refusal)
    assert error.reason == otp_module().OtpDeliveryFailure.MALFORMED_RESPONSE
    assert error.status_code == 200
    assert error.retryable is False
    assert len(vendor.requests) == 1, "an answer that may mean 'sent' is never sent again"
    assert _sample(refusal) == before + 1
    assert error.__cause__ is None and error.__context__ is None


def test_an_undocumented_code_refused_with_a_4xx_stays_a_plain_rejection(phi_egress: None) -> None:
    """The near miss of the 2xx case: at 406 the vendor plainly refused."""
    respond, refusal, reason, status = FAULTS["unknown-code"]
    error = _failure(Vendor(respond))
    assert (error.refusal, error.reason, error.status_code) == (
        netgsm().NetgsmRefusal(refusal),
        otp_module().OtpDeliveryFailure(reason),
        status,
    )
    assert error.vendor_code == 99


def test_a_timeout_is_sent_once_and_never_retryable(phi_egress: None) -> None:
    vendor = Vendor(FAULTS["timeout"][0])
    error = _failure(vendor)
    assert error.retryable is False
    assert len(vendor.requests) == 1


def test_retryable_is_false_wherever_the_vendor_may_have_sent_the_code() -> None:
    failure = otp_module().OtpDeliveryFailure
    may_have_sent = {failure.MALFORMED_RESPONSE, failure.TIMEOUT, failure.VENDOR_UNAVAILABLE}
    assert otp_module().DELIVERY_MAY_HAVE_SENT == may_have_sent
    for reason in failure:
        error = otp_module().OtpDeliveryError(reason)
        assert error.retryable is (reason not in may_have_sent), reason


def test_the_adapter_has_no_retry_loop() -> None:
    """One ``post`` per send and no loop anywhere in the adapter's class: the
    patient's resend after the cooldown is the only second attempt."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(netgsm().NetgsmSmsDeliveryAdapter)))
    loops = [
        node for node in ast.walk(tree) if isinstance(node, ast.While | ast.For | ast.AsyncFor)
    ]
    posts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
    ]
    assert loops == []
    assert len(posts) == 1


# --- invariant 6 on the new paths -------------------------------------------------------


def _echoing() -> list[Any]:
    """2xx answers that echo the recipient and the code in values, keys and tags."""
    return [
        body(200, {PHONE_NATIONAL: CODE, "description": f"{PHONE} {CODE}"}),
        body(200, {"code": CODE, "jobid": PHONE_NATIONAL}),
        body(200, {"code": int(PHONE_NATIONAL), "jobId": int(CODE)}),
        body(200, {"code": "00", "jobid": f"{PHONE_NATIONAL}-{CODE}", "description": CODE}),
        bare(200, f"00 {PHONE_NATIONAL} {CODE}"),
        bare(200, f"<html><body>{PHONE} {CODE}</body></html>", "text/html"),
        bare(
            200, f"<xml><main><code>0</code><no>{PHONE_NATIONAL}</no><msg>{CODE}</msg></main></xml>"
        ),
    ]


def test_no_unreadable_answer_puts_a_phone_or_code_in_the_error_log_or_shape(
    phi_egress: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    for respond in _echoing():
        error = _failure(Vendor(respond))
        assert_clean(f"{error} {error.args!r} {vars(error)!r}", "the error")
        assert_clean(error.shape.render(), "the answer's shape")
    for record in caplog.records:
        assert_clean(record_text(record), "a log record")


def test_an_unreadable_answer_logs_one_typed_line_and_no_part_of_the_body(
    phi_egress: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    _failure(Vendor(UNREADABLE["plain-text-00-jobid"][0]))
    [line] = [r.getMessage() for r in caplog.records if r.name == "intake_api.otp_netgsm"]
    assert line == (
        "otp delivery failed (netgsm) refusal=unparseable_response "
        "reason=malformed_response http_status=200 vendor_code=-"
    )


# --- the owner's diagnostic: structure only ---------------------------------------------


def _shape_of(respond: Any) -> str:
    error = _failure(Vendor(respond))
    rendered: str = error.shape.render()
    return rendered


def test_the_shape_of_a_success_names_its_keys_and_their_types(phi_egress: None) -> None:
    receipt = send(adapter(Vendor(replay("accepted_sdk"))))
    length = len(httpx.Response(200, json=RECORDED["responses"]["accepted_sdk"]["body"]).content)
    assert receipt.shape.render() == (
        "content_type=application/json kind=json-object "
        f"keys=code:string,description:string,jobId:string code=00 length={length}"
    )
    assert JOBID not in receipt.shape.render()


def test_the_shape_of_the_xml_endpoint_s_answer_lists_its_tags(phi_egress: None) -> None:
    shape = _shape_of(UNREADABLE["xml-otp-endpoint-answer"][0])
    assert "kind=markup keys=xml,main,code,jobID code=0 " in shape
    assert "172551745916519453710565585" not in shape


def test_the_shape_of_plain_text_and_of_an_html_page(phi_egress: None) -> None:
    text = _shape_of(UNREADABLE["plain-text-00-jobid"][0])
    assert text == f"content_type=text/plain kind=text keys=- code=00 length={len(JOBID) + 3}"
    html = _shape_of(UNREADABLE["html-page"][0])
    assert html.startswith("content_type=text/html kind=markup keys=html,head,title,body code=-")


def test_the_shape_marks_a_name_it_will_not_print(phi_egress: None) -> None:
    shape = _shape_of(body(200, {PHONE_NATIONAL: CODE, "jobid": 1, "x1": [], "Code": None}))
    assert "keys=?:string,jobid:number,?:array,Code:null code=-" in shape


def test_the_shape_names_each_tag_once_and_at_most_twelve_names(phi_egress: None) -> None:
    keys = _shape_of(body(200, {"k" + "x" * i: True for i in range(20)}))
    assert keys.count(":boolean") == 12
    tags = "".join(f"<t{'a' * i}></t{'a' * i}>" for i in range(20))
    markup = _shape_of(bare(200, f"<r><r>{tags}"))
    names = markup.split("keys=", 1)[1].split(" ", 1)[0].split(",")
    assert names[:3] == ["r", "t", "ta"] and len(names) == 12


@pytest.mark.parametrize("scenario", sorted(UNREADABLE))
def test_every_unreadable_answer_carries_its_shape_and_no_job_id(
    phi_egress: None, scenario: str
) -> None:
    shape = _shape_of(UNREADABLE[scenario][0])
    assert shape.startswith("content_type=")
    assert JOBID not in shape


@pytest.mark.parametrize(
    ("headers", "content", "expected"),
    [
        ({}, b"", "content_type=- kind=empty keys=- code=- length=0"),
        ({"content-type": "Application/JSON ; charset=x"}, b"7", "content_type=application/json"),
        ({"content-type": "text/<b>"}, b"[1]", "content_type=? kind=json-other keys=- code=-"),
    ],
    ids=["no-header-no-body", "media-type-normalised", "media-type-refused"],
)
def test_the_content_type_is_the_bare_media_type_or_a_mark(
    headers: dict[str, str], content: bytes, expected: str
) -> None:
    response = httpx.Response(200, content=content, headers=headers)
    assert shape_module().answer_shape(response).render().startswith(expected)
