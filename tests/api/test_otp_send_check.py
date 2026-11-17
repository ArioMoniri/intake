"""INT-528 — the owner's one real OTP (``intake_api.otp_send_check``).

Owner authorisation, 16 Oct 2026: one code to the single number on the
synthetic host's SMS test allow-list, through the API's own wiring. These
tests replay the documentation-built fixtures behind the guarded transport (no
vendor call) and hold:

- the code goes to the list's one number, which is never an argument and
  never printed; only the job id (code 00) or a typed refusal is printed;
- a list with no number, or with several, sends nothing;
- a deployment with no list (production) or a dev deployment sends nothing;
- an unconfigured tier is reported as the 503 the route would answer;
- INT-576: an answer Netgsm may have sent on is reported ``unconfirmed``,
  after exactly one send, with the owner told to check the phone before
  running again; ``--shape`` adds the answer's structure and never a value.

Every number here is synthetic.
"""

from __future__ import annotations

import io
from typing import Any

import httpx
import pytest
from intake_api.otp_send_check import NOT_SENT, REFUSED, SENT, UNCONFIRMED, main
from intake_api.settings import ApiSettings
from intake_api.sms_recipients import ADMIT_ALL, RecipientGate, SmsTestAllowlist
from netgsm_testkit import (
    JOBID,
    UNREADABLE,
    Vendor,
    accepted,
    credentials,
    netgsm,
    policy,
    replay,
)

LISTED = "+905550000001"
OTHER = "+905559999999"


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def _settings(environment: str = "staging") -> ApiSettings:
    return ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
        audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
        kek_mode="transit",
        tokenization_key="k",
        environment=environment,
    )


def _delivery(vendor: Vendor, recipients: RecipientGate) -> Any:
    return netgsm().NetgsmSmsDeliveryAdapter(
        credentials(),
        egress=policy(),
        inner=httpx.MockTransport(vendor),
        recipients=recipients,
    )


class Recorder:
    """A delivery factory that hands out one adapter and counts the calls."""

    def __init__(self, delivery: Any) -> None:
        self.delivery = delivery
        self.calls = 0

    def __call__(self, settings: ApiSettings) -> Any:
        self.calls += 1
        return self.delivery


def _run(
    factory: Recorder, environment: str = "staging", argv: tuple[str, ...] = ()
) -> tuple[int, str]:
    out = io.StringIO()
    code = main(
        out=out,
        settings_factory=lambda: _settings(environment),
        delivery_factory=factory,
        argv=argv,
    )
    return code, out.getvalue()


def test_the_code_goes_to_the_one_listed_number_and_only_the_job_id_is_printed(
    phi_egress: None,
) -> None:
    vendor = Vendor(accepted)
    code, shown = _run(Recorder(_delivery(vendor, SmsTestAllowlist.parse(LISTED))))
    assert code == SENT
    assert shown == f"accepted: code 00, job id {JOBID}\n"
    [wire] = vendor.bodies
    assert wire["no"] == LISTED[3:]
    sent_code = wire["msg"].split(": ")[1].split(".")[0]
    for secret in (LISTED, LISTED[3:], sent_code):
        assert secret not in shown


@pytest.mark.parametrize(
    "gate",
    [SmsTestAllowlist.parse(""), SmsTestAllowlist.parse(f"{LISTED},{OTHER}"), ADMIT_ALL],
    ids=["empty-list", "two-numbers", "no-list"],
)
def test_anything_but_exactly_one_listed_number_sends_nothing(
    phi_egress: None, gate: RecipientGate
) -> None:
    vendor = Vendor(accepted)
    code, shown = _run(Recorder(_delivery(vendor, gate)))
    assert code == REFUSED
    assert vendor.requests == []
    assert LISTED not in shown and OTHER not in shown


def test_a_dev_deployment_builds_no_wiring() -> None:
    factory = Recorder(None)
    code, _ = _run(factory, environment="dev")
    assert code == REFUSED
    assert factory.calls == 0


def test_an_unconfigured_tier_is_reported_as_the_503_it_is() -> None:
    code, shown = _run(Recorder(None))
    assert code == NOT_SENT
    assert "would answer 503" in shown


def test_a_vendor_refusal_is_reported_by_its_typed_names(phi_egress: None) -> None:
    vendor = Vendor(replay("error", code="30"))
    code, shown = _run(Recorder(_delivery(vendor, SmsTestAllowlist.parse(LISTED))))
    assert code == NOT_SENT
    assert "refusal=credentials_refused" in shown and "vendor_code=30" in shown
    assert "error message desc." not in shown
    assert LISTED not in shown and LISTED[3:] not in shown


# --- INT-576: an answer that may mean "sent" -------------------------------------------


def test_an_unreadable_answer_is_unconfirmed_after_exactly_one_send(phi_egress: None) -> None:
    vendor = Vendor(UNREADABLE["plain-text-00-jobid"][0])
    code, shown = _run(Recorder(_delivery(vendor, SmsTestAllowlist.parse(LISTED))))
    assert code == UNCONFIRMED
    assert len(vendor.requests) == 1
    assert shown == (
        "unconfirmed: reason=malformed_response refusal=unparseable_response http_status=200 "
        "vendor_code=-; Netgsm may have sent the code, so check the phone before running "
        "this again\n"
    )
    assert JOBID not in shown and LISTED[3:] not in shown


def test_shape_prints_the_structure_of_an_unreadable_answer_and_no_value(
    phi_egress: None,
) -> None:
    vendor = Vendor(UNREADABLE["plain-text-00-jobid"][0])
    code, shown = _run(
        Recorder(_delivery(vendor, SmsTestAllowlist.parse(LISTED))), argv=("--shape",)
    )
    assert code == UNCONFIRMED
    [_, shape] = shown.splitlines()
    assert shape == (
        f"answer shape: content_type=text/plain kind=text keys=- code=00 length={len(JOBID) + 3}"
    )
    sent_code = vendor.bodies[0]["msg"].split(": ")[1].split(".")[0]
    for secret in (JOBID, LISTED, LISTED[3:], sent_code):
        assert secret not in shown


def test_shape_after_a_success_names_the_documented_keys(phi_egress: None) -> None:
    vendor = Vendor(replay("accepted_sdk"))
    code, shown = _run(
        Recorder(_delivery(vendor, SmsTestAllowlist.parse(LISTED))), argv=("--shape",)
    )
    assert code == SENT
    [accepted_line, shape] = shown.splitlines()
    assert accepted_line == f"accepted: code 00, job id {JOBID}"
    assert shape.startswith(
        "answer shape: content_type=application/json kind=json-object "
        "keys=code:string,description:string,jobId:string code=00 length="
    )


def test_without_shape_nothing_but_the_outcome_is_printed(phi_egress: None) -> None:
    vendor = Vendor(replay("accepted_sdk"))
    code, shown = _run(Recorder(_delivery(vendor, SmsTestAllowlist.parse(LISTED))))
    assert code == SENT
    assert shown == f"accepted: code 00, job id {JOBID}\n"


def test_an_unknown_argument_is_refused_before_anything_is_built() -> None:
    factory = Recorder(None)
    with pytest.raises(SystemExit) as caught:
        _run(factory, argv=("--number",))
    assert caught.value.code == REFUSED
    assert factory.calls == 0
