"""ADR-042 — the SMS vendor's dedicated egress proxy, and the one exception it
makes to INT-203.

INT-203 (ADR-032) refuses, at construction, any personal-data transport that
names a forward proxy: behind the shared proxy neither enforcement point
resolves, and that proxy's allow-list carries no personal-data row. ADR-042
admits exactly one arrangement that answers both reasons: the OTP tier's SMS
call (``SMS_OTP_DELIVERY``) through ``http://sms-egress:3128``, a proxy that
renders the allow-list's SMS row and nothing else, closes the rebinding window
itself and refuses the denied ranges at connect.

Everything else INT-203 refuses stays refused, and the in-process allow-list,
purpose, data-class and runtime-gate checks still run on the admitted path.
"""

from __future__ import annotations

from asyncio import run
from typing import Any

import httpx
import pytest
from intake_platform.egress import (
    DEDICATED_PERSONAL_PROXIES,
    AllowlistEntry,
    DataClass,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    InMemoryTransferLog,
    guarded_async_client,
    guarded_transport,
)

SMS_PROXY = "http://sms-egress:3128"
SHARED_PROXY = "http://egress-proxy:3128"
SMS = EgressContext(purpose=EgressPurpose.SMS_OTP_DELIVERY, data_class=DataClass.PHI)


def _row() -> AllowlistEntry:
    return AllowlistEntry(
        name="netgsm-otp-test-row",
        host="api.netgsm.com.tr",
        port=443,
        protocol="https",
        purpose_id=EgressPurpose.SMS_OTP_DELIVERY,
        purpose="unit fixture",
        basis="unit fixture only",
        phi_allowed=True,
        phi_exception_approval="unit-fixture-not-a-decision",
    )


def _never_resolve(host: str, port: int) -> tuple[str, ...]:
    raise AssertionError("behind the dedicated proxy the process does not resolve (ADR-032)")


def _policy() -> EgressPolicy:
    return EgressPolicy([_row()], "phi_path", resolver=_never_resolve)


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def test_the_one_dedicated_proxy_is_the_sms_purpose_s() -> None:
    assert dict(DEDICATED_PERSONAL_PROXIES) == {EgressPurpose.SMS_OTP_DELIVERY: SMS_PROXY}


def test_the_sms_call_rides_its_dedicated_proxy_with_the_hostname_intact(
    phi_egress: None,
) -> None:
    seen: list[httpx.Request] = []

    async def vendor(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": "00", "jobid": "1"})

    log = InMemoryTransferLog()

    async def scenario() -> Any:
        async with guarded_async_client(
            _policy(), SMS, inner=httpx.MockTransport(vendor), transfer_log=log, proxy=SMS_PROXY
        ) as client:
            return await client.post("https://api.netgsm.com.tr/sms/rest/v2/otp", json={})

    assert run(scenario()).status_code == 200
    [request] = seen
    assert request.url.host == "api.netgsm.com.tr", "the CONNECT line names the host"
    [entry] = log.entries
    assert entry.decision == "allow" and entry.host == "api.netgsm.com.tr"


@pytest.mark.parametrize(
    ("context", "proxy"),
    [
        (SMS, SHARED_PROXY),
        (SMS, "http://sms-egress:3129"),
        (SMS, "https://sms-egress:3128"),
        (SMS, "http://sms-egress.evil.example:3128"),
        (EgressContext(EgressPurpose.CLINICAL_RECORD_PUSH, DataClass.PHI), SMS_PROXY),
        (EgressContext(EgressPurpose.MODEL_WEIGHTS, DataClass.PSEUDONYMOUS), SMS_PROXY),
    ],
    ids=["shared-proxy", "other-port", "other-scheme", "lookalike-host", "push", "pseudonymous"],
)
def test_every_other_personal_proxy_arrangement_is_still_refused(
    context: EgressContext, proxy: str
) -> None:
    """INT-203 unchanged everywhere but the one admitted pair."""
    with pytest.raises(ValueError, match="cannot delegate its pin"):
        guarded_transport(_policy(), context, proxy=proxy)
    with pytest.raises(ValueError, match="cannot delegate its pin"):
        guarded_async_client(_policy(), context, proxy=proxy)


def test_the_in_process_checks_still_run_behind_the_dedicated_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The allow-list and the runtime gate decide before the proxy is asked."""
    calls: list[httpx.Request] = []

    async def vendor(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    async def post(url: str) -> None:
        async with guarded_async_client(
            _policy(), SMS, inner=httpx.MockTransport(vendor), proxy=SMS_PROXY
        ) as client:
            await client.post(url, json={})

    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")
    with pytest.raises(EgressDenied):
        run(post("https://api.netgsm.com.tr.evil.example/sms/rest/v2/otp"))
    monkeypatch.delenv("INTAKE_ALLOW_PHI_EGRESS")
    with pytest.raises(EgressDenied):
        run(post("https://api.netgsm.com.tr/sms/rest/v2/otp"))
    assert calls == []


# --- INT-442 x ADR-042: two proxies, and neither carries the other's purpose -------------

HOSTED = EgressPurpose.HOSTED_MODEL_INFERENCE


def test_each_routed_purpose_is_bound_to_its_one_proxy() -> None:
    """The SMS call rides only sms-egress; a hosted-model call only egress-proxy."""
    from intake_platform import egress

    assert dict(egress.PURPOSE_PROXIES) == {
        EgressPurpose.SMS_OTP_DELIVERY: SMS_PROXY,
        HOSTED: SHARED_PROXY,
    }


@pytest.mark.parametrize("data_class", list(DataClass), ids=str)
@pytest.mark.parametrize(
    "purpose",
    sorted(set(EgressPurpose) - {EgressPurpose.SMS_OTP_DELIVERY}, key=str),
    ids=str,
)
def test_the_sms_proxy_carries_no_other_purpose_whatever_its_class(
    purpose: EgressPurpose, data_class: DataClass
) -> None:
    """Non-personal included: a hosted-model call is not personal data, and the
    SMS proxy refuses it anyway, in process as well as at the network."""
    context = EgressContext(purpose=purpose, data_class=data_class)
    with pytest.raises(ValueError):
        guarded_transport(_policy(), context, proxy=SMS_PROXY)
    with pytest.raises(ValueError):
        guarded_async_client(_policy(), context, proxy=SMS_PROXY)


@pytest.mark.parametrize("data_class", list(DataClass), ids=str)
@pytest.mark.parametrize(
    "proxy",
    [SHARED_PROXY, "http://egress-proxy.evil.example:3128", "http://sms-egress:3129"],
    ids=["shared-proxy", "lookalike", "other-port"],
)
def test_the_sms_purpose_rides_no_other_proxy_whatever_its_class(
    proxy: str, data_class: DataClass
) -> None:
    context = EgressContext(purpose=EgressPurpose.SMS_OTP_DELIVERY, data_class=data_class)
    with pytest.raises(ValueError):
        guarded_transport(_policy(), context, proxy=proxy)
    with pytest.raises(ValueError):
        guarded_async_client(_policy(), context, proxy=proxy)


@pytest.mark.parametrize(
    "proxy",
    [SMS_PROXY, "http://egress-proxy.evil.example:3128", "http://egress-proxy:3129"],
    ids=["sms-proxy", "lookalike", "other-port"],
)
def test_a_hosted_model_call_rides_no_proxy_but_the_shared_one(proxy: str) -> None:
    context = EgressContext(purpose=HOSTED, data_class=DataClass.NON_PERSONAL)
    with pytest.raises(ValueError):
        guarded_transport(_policy(), context, proxy=proxy)
    with pytest.raises(ValueError):
        guarded_async_client(_policy(), context, proxy=proxy)


def test_the_near_misses_still_construct() -> None:
    """The controls: each purpose on its own proxy, and either one direct."""
    hosted = EgressContext(purpose=HOSTED, data_class=DataClass.NON_PERSONAL)
    guarded_transport(_policy(), hosted, proxy=SHARED_PROXY)
    guarded_transport(_policy(), hosted)
    guarded_transport(_policy(), SMS, proxy=SMS_PROXY)
    guarded_transport(_policy(), SMS)
