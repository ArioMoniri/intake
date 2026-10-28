"""INT-579 — OTP enumeration (owner order, 28 Oct 2026; GitHub #974).

Acceptance, verbatim: "The OTP request and verify routes return the same
status, body shape and timing envelope whether or not the number is
registered, locked, rate-limited for another reason, or allow-list-refused; a
statistical timing test (no wall-clock budget asserted on the shared runner —
compare distributions or use a fake clock) with near misses."

The audit (docs/evidence/INT-577.md, rows 21-27) found the request route
telling a stranger three things about a number it had no business knowing:

- **allow-list-refused** answered 422 where a listed number answered 202;
- **rate-limited for the number** (its resend wait, its hourly budget) and,
  since INT-578, **locked** answered 429 with the wait — which says someone
  asked for codes to that number in the last hour;
- **timing**: the vendor call sat on the response path, so a refused number
  answered in microseconds and a sent one in a vendor round trip; a vendor
  outage turned sent numbers into 503s and refused ones into 422s.

Now every number-scoped refusal is WITHHELD: the caller gets the 202 an
admission gets — a fresh request id and a resend wait read from the caller's
own device, never the number's — and no code is minted or sent. The vendor call
runs after the response (``OtpAuthService.settle`` waits for it in tests and at
shutdown). What still differs is what is the same for every number: a malformed
number (422), the caller's own device or address budget (429), the platform's
caps and kill switch (429/503).

The timing envelope is pinned twice. Deterministically: the Redis commands a
withheld request runs are the same commands, in the same counts, as a sent one,
and each writes one audit row — a fake clock cannot see a vendor round trip, but
it can see work that is or is not done. Statistically: with a vendor that takes
50 ms, sent and withheld requests are timed alternately and their medians
compared with a ratio of 3, which the old path misses by a wide margin and a
loaded runner does not approach.
"""

from __future__ import annotations

import asyncio
import contextlib
import statistics
import sys
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from intake_api.auth_store import (  # noqa: E402
    DEVICE_LIMIT_PER_HOUR,
    OTP_MAX_ATTEMPTS,
    RESEND_COOLDOWN_S,
)
from intake_api.otp import DeliveryReceipt, OtpDeliveryError, OtpDeliveryFailure  # noqa: E402
from intake_api.sms_recipients import SmsTestAllowlist  # noqa: E402
from test_otp_abuse import PHONE, DpopClient, OtpHarness, _build  # noqa: E402

LISTED = tuple(f"+90532888{n:04d}" for n in range(40))
UNLISTED = tuple(f"+90532999{n:04d}" for n in range(40))
REDIS_COMMANDS = (
    "get",
    "set",
    "delete",
    "incr",
    "expire",
    "zadd",
    "zrange",
    "zremrangebyscore",
)


@contextlib.contextmanager
def harness(tmp_path: Path, **knobs: Any) -> Iterator[OtpHarness]:
    built = _build(tmp_path, **knobs)
    try:
        yield next(built)
    finally:
        next(built, None)


@pytest.fixture()
def otp(tmp_path: Path) -> Iterator[OtpHarness]:
    yield from _build(tmp_path)


def _answer(response: Any) -> tuple[int, frozenset[str], str]:
    """What a caller can compare across two answers, beyond the values a fresh
    request makes up anew: status, body shape, content type."""
    return (
        response.status_code,
        frozenset(response.json()),
        response.headers["content-type"],
    )


def _assert_indistinguishable(sent: Any, withheld: Any) -> None:
    assert _answer(withheld) == _answer(sent)
    assert sent.status_code == 202
    for body in (sent.json(), withheld.json()):
        assert set(body) == {"request_id", "resend_after_s"}
        assert len(body["request_id"]) == 32 and int(body["request_id"], 16) >= 0
    # the advertised wait is the caller's own (a fresh device: the first step)
    assert sent.json()["resend_after_s"] == withheld.json()["resend_after_s"]
    assert sent.json()["request_id"] != withheld.json()["request_id"]


# --- the request route: one answer whatever the number's state ----------------------


def test_a_number_off_the_test_list_answers_like_one_on_it(tmp_path: Path) -> None:
    gate = SmsTestAllowlist(frozenset(LISTED))
    with harness(tmp_path, recipients=gate) as otp:
        before = otp.sends
        sent = otp.request_otp(LISTED[0], device_id="device-listed")
        assert otp.sends == before + 1
        withheld = otp.request_otp(UNLISTED[0], device_id="device-unlisted")
        assert otp.sends == before + 1, "a number off the list was sent a code"
        _assert_indistinguishable(sent, withheld)


def test_a_number_in_its_resend_wait_answers_like_a_fresh_one(otp: OtpHarness) -> None:
    assert otp.sent(PHONE, device_id="device-victim")
    before = otp.sends
    fresh = otp.request_otp("+905330001122", device_id="device-probe-1")
    withheld = otp.request_otp(PHONE, device_id="device-probe-2")
    assert otp.sends == before + 1, "the number in its resend wait was sent a code"
    _assert_indistinguishable(fresh, withheld)


def test_a_number_over_its_hourly_budget_answers_like_a_fresh_one(otp: OtpHarness) -> None:
    for n in range(1, 4):
        assert otp.sent(PHONE, device_id=f"device-victim-{n}")
        otp.clock.advance(RESEND_COOLDOWN_S * 2 ** (n - 1) + 1)
    before = otp.sends
    withheld = otp.request_otp(PHONE, device_id="device-probe-1")
    fresh = otp.request_otp("+905330001133", device_id="device-probe-2")
    assert otp.sends == before + 1, "the number over its budget was sent a code"
    _assert_indistinguishable(fresh, withheld)


def test_a_locked_number_answers_like_a_fresh_one(otp: OtpHarness) -> None:
    dpop = DpopClient()
    assert otp.sent(PHONE, device_id="device-a")
    real = otp.peek()
    for _ in range(OTP_MAX_ATTEMPTS):
        otp.verify(dpop, code="000000" if real != "000000" else "111111")
    otp.clock.advance(RESEND_COOLDOWN_S * 2)
    before = otp.sends
    withheld = otp.request_otp(PHONE, device_id="device-probe-1")
    fresh = otp.request_otp("+905330001144", device_id="device-probe-2")
    assert otp.sends == before + 1, "a locked number was sent a code"
    _assert_indistinguishable(fresh, withheld)


def test_a_registered_number_answers_like_an_unregistered_one(otp: OtpHarness) -> None:
    otp.sign_up(DpopClient())
    otp.clock.advance(3600 + 1)
    registered = otp.request_otp(PHONE, device_id="device-probe-1")
    unregistered = otp.request_otp("+905330001155", device_id="device-probe-2")
    _assert_indistinguishable(unregistered, registered)


def test_a_withheld_request_mints_no_code(otp: OtpHarness) -> None:
    """Near miss for the indistinguishable answers: the withheld request is a
    decoy, so nothing the caller could guess at exists behind it."""
    assert otp.sent(PHONE, device_id="device-a")
    code = otp.peek()
    assert not otp.sent(PHONE, device_id="device-b")
    assert otp.peek() == code, "the withheld request replaced the live code"


def test_the_caller_s_own_budget_still_answers_429(otp: OtpHarness) -> None:
    """What is NOT masked, and why it is no oracle: a device's budget is the
    same whatever number it asks for."""
    for n in range(DEVICE_LIMIT_PER_HOUR):
        assert otp.request_otp(f"+90533444{n:04d}", device_id="one-device").status_code == 202
    for number in (PHONE, "+905339990000"):
        refused = otp.request_otp(number, device_id="one-device")
        assert refused.status_code == 429
        assert refused.json()["error"] == "otp_limited"


def test_the_advertised_wait_follows_the_caller_not_the_number(otp: OtpHarness) -> None:
    """The legitimate user is one device asking for one number: it is told the
    doubled wait the number is held to. A stranger's device is told its own
    first step, whatever the number has been through."""
    first = otp.request_otp(PHONE, device_id="device-a")
    otp.clock.advance(RESEND_COOLDOWN_S + 1)
    second = otp.request_otp(PHONE, device_id="device-a")
    assert (first.json()["resend_after_s"], second.json()["resend_after_s"]) == (
        RESEND_COOLDOWN_S,
        2 * RESEND_COOLDOWN_S,
    )
    stranger = otp.request_otp(PHONE, device_id="device-stranger")
    assert stranger.json()["resend_after_s"] == RESEND_COOLDOWN_S


def test_a_failed_delivery_answers_202_and_is_audited(tmp_path: Path) -> None:
    """The vendor is after the response, so its refusal can no longer be read
    off the route (Netgsm refuses an unreachable number with its own code: a
    503 there was an oracle for which numbers are live)."""

    class Refusing:
        async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
            del phone_e164, code
            raise OtpDeliveryError(OtpDeliveryFailure.REJECTED, vendor_code=50)

    with harness(tmp_path, delivery=Refusing()) as otp:
        response = otp.request_otp()
        assert response.status_code == 202
        assert set(response.json()) == {"request_id", "resend_after_s"}
        actions = [entry.action for entry in otp.audit_store.entries()]
        assert actions[-2:] == ["auth.otp.requested", "auth.otp.delivery_failed"]


# --- the same work: the deterministic half of the timing envelope ---------------------


class CommandTrace:
    """Records the name of every Redis command the API runs, without its
    arguments: the shape of the work, which is what timing leaks."""

    def __init__(self, client: Any) -> None:
        self.calls: list[str] = []
        self._client = client
        self._real = {name: getattr(client, name) for name in REDIS_COMMANDS}
        for name in REDIS_COMMANDS:
            setattr(client, name, self._wrap(name))

    def _wrap(self, name: str) -> Any:
        real = self._real[name]

        def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(name)
            return real(*args, **kwargs)

        return call

    def take(self) -> Counter[str]:
        taken = Counter(self.calls)
        self.calls.clear()
        return taken


def _post(otp: OtpHarness, phone: str, device_id: str) -> Any:
    headers = otp.attestation(device_id)  # the challenge is issued before the trace
    return otp.client.post("/v1/auth/otp/request", json={"phone": phone}, headers=headers)


def test_a_withheld_request_runs_the_same_redis_work_as_a_sent_one(tmp_path: Path) -> None:
    gate = SmsTestAllowlist(frozenset(LISTED))
    with harness(tmp_path, recipients=gate) as otp:
        trace = CommandTrace(otp.redis_client)
        cases: dict[str, Counter[str]] = {}
        audits: dict[str, int] = {}

        def run(case: str, phone: str, device_id: str) -> None:
            headers = otp.attestation(device_id)
            rows = len(otp.audit_store.entries())
            trace.take()
            response = otp.client.post(
                "/v1/auth/otp/request", json={"phone": phone}, headers=headers
            )
            cases[case] = trace.take()
            otp.settle()
            # the response path's own row; the vendor's comes after it
            appended = [e.action for e in otp.audit_store.entries()[rows:]]
            audits[case] = sum(a in {"auth.otp.requested", "auth.otp.withheld"} for a in appended)
            assert response.status_code == 202, (case, response.text)

        run("sent", LISTED[0], "device-1")
        run("not_listed", UNLISTED[0], "device-2")
        run("resend_wait", LISTED[0], "device-3")
        otp.clock.advance(RESEND_COOLDOWN_S + 1)
        run("sent_again", LISTED[1], "device-4")
        for case, work in cases.items():
            assert work == cases["sent"], f"{case} ran {work}, a sent request {cases['sent']}"
        assert set(audits.values()) == {1}, audits


# --- the verify route: one answer and the same work, whatever the number --------------


def test_verify_answers_alike_and_works_alike_for_every_failure(tmp_path: Path) -> None:
    dpop = DpopClient()
    with harness(tmp_path) as otp:
        assert otp.sent(PHONE, device_id="device-a")
        real = otp.peek()
        wrong = "000000" if real != "000000" else "111111"
        trace = CommandTrace(otp.redis_client)

        def attempt(phone: str, code: str) -> tuple[Any, Counter[str]]:
            headers = otp.attestation("device-a")
            headers["DPoP"] = dpop.proof("POST", f"{otp.base}/v1/auth/otp/verify", iat=otp.clock())
            body = {"phone": phone, "code": code, "request_id": otp.request_ids[PHONE]}
            trace.take()
            response = otp.client.post("/v1/auth/otp/verify", json=body, headers=headers)
            return response, trace.take()

        wrong_live, work_live = attempt(PHONE, wrong)
        never, work_never = attempt("+905330007788", wrong)  # no code was ever sent
        for _ in range(OTP_MAX_ATTEMPTS - 1):
            attempt(PHONE, wrong)
        locked, work_locked = attempt(PHONE, real)  # the right code, under the lockout
        otp.clock.advance(3600 + 1)
        expired, work_expired = attempt(PHONE, real)
        for response in (wrong_live, never, locked, expired):
            assert response.status_code == 401
            assert response.json() == {"error": "otp_invalid"}
        assert work_never == work_live
        assert work_locked == work_live
        assert work_expired == work_live


# --- the statistical half: distributions, never a wall-clock budget ---------------------


class SlowVendor:
    """A vendor that takes 50 ms to answer, which is what a refused number's
    answer used to skip."""

    def __init__(self) -> None:
        self.sends = 0

    async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
        del phone_e164, code
        await asyncio.sleep(0.05)
        self.sends += 1
        return DeliveryReceipt(delivery_id=f"{self.sends:032x}")


def test_sent_and_withheld_requests_take_the_same_time(tmp_path: Path) -> None:
    """Alternate a sent request and a withheld one, 25 of each, and compare the
    medians. The bound is a ratio of 3: the old path, which awaited the 50 ms
    vendor on a sent request only, runs at more than ten; two samples of the
    same work on a loaded runner do not come near it. No duration is asserted
    against a budget."""
    vendor = SlowVendor()
    gate = SmsTestAllowlist(frozenset(LISTED))
    sent_s: list[float] = []
    withheld_s: list[float] = []
    statuses: list[int] = []
    with harness(tmp_path, recipients=gate, delivery=vendor) as otp:
        for n in range(25):
            for phone, samples in ((LISTED[n], sent_s), (UNLISTED[n], withheld_s)):
                headers = otp.attestation(f"device-{phone}")
                started = time.perf_counter()
                response = otp.client.post(
                    "/v1/auth/otp/request", json={"phone": phone}, headers=headers
                )
                samples.append(time.perf_counter() - started)
                statuses.append(response.status_code)
            # the address budget is 10 an hour: keep each pair in its own slice
            otp.clock.advance(800)
        otp.settle()
    sent_median = statistics.median(sent_s)
    withheld_median = statistics.median(withheld_s)
    ratio = max(sent_median, withheld_median) / min(sent_median, withheld_median)
    assert ratio < 3, (sent_median, withheld_median)
    assert set(statuses) == {202}
    assert vendor.sends == 25, "every listed number was sent its code"
