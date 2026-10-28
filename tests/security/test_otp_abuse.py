"""INT-131 — OTP abuse limits, DPoP binding, refresh-family reuse detection.

Acceptance lines pinned here (files/10 §2, verbatim source of the numbers):
  "phone OTP (6 digits, 5-min TTL, 5 attempts, 3 requests/hour/phone,
  10/hour/IP …) + device attestation … on OTP request and session start;
  Access tokens 15 min, refresh tokens rotating and device-bound (DPoP,
  RFC 9449); refresh reuse detection revokes the family"

What this file proves:
- the 10 §2 limits are enforced: resend cooldown (burst), 3/hour/phone,
  10/hour/IP, per-device window, 5 verify attempts then the code is dead;
- those budgets are ROLLING, not per fixed hour (INT-263): no dimension admits
  more than its limit in ANY OTP_WINDOW_S span, an hour boundary hands no
  budget back, the advertised retry-after is the true wait for that bound, and
  the counter key set stays one key per (dimension, identifier);
- OTP codes never appear in logs or in any non-peek response, and the raw
  phone number never appears in logs or in the database (invariants 6, 14);
- the dev peek endpoint exists ONLY under INTAKE_DEV_OTP_PEEK=explicit-yes
  (fail closed → 404), and attestation fails closed without the dev flag;
- verify issues DPoP-bound tokens (RFC 9449): rotation works, a reused
  refresh revokes the WHOLE family and is audited, a replayed DPoP proof is
  rejected, and a proof signed by a different key never refreshes;
- real OTP accounts are tagged X-Intake-Auth-Tier: otp while the two
  dev-bearer accounts keep working and stay tagged dev (load-bearing tier).

fakeredis + an injected clock keep every window deterministic (docs/TDD.md
rule 6); SQLite carries the INT-030 schema exactly as tests/api does. The
clock is seeded from the rate-limit window and never from the wall clock, so
no assertion here depends on the minute the suite runs (INT-285), and the
INT-263 tests can place a sequence at a chosen phase of the hour on purpose.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient
from intake_platform.db.models import Patient
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from intake_platform.tokenization import Tokenizer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import run, sqlite_ddl_clone  # noqa: E402
from intake_api import auth_store as auth_store_module  # noqa: E402
from intake_api.app import ApiWiring, create_app  # noqa: E402
from intake_api.attestation import (  # noqa: E402
    DevStructuralAttestationVerifier,
    FailClosedAttestationVerifier,
)
from intake_api.auth_store import (  # noqa: E402
    ACCESS_TTL_S,
    DEVICE_LIMIT_PER_HOUR,
    IP_LIMIT_PER_HOUR,
    OTP_MAX_ATTEMPTS,
    OTP_TTL_S,
    OTP_WINDOW_S,
    PHONE_LIMIT_PER_HOUR,
    RESEND_COOLDOWN_S,
    AuthStore,
)
from intake_api.carrier_geo import (  # noqa: E402
    MSISDN_ALLOCATION_PATH,
    AllocationSource,
    AllocationTable,
    AllocationTableAuthority,
    CarrierGeoCheck,
    CarrierGeoConfigError,
    CarrierGeoOutcome,
    carrier_geo_from_path,
    load_allocation_table,
    split_e164,
)
from intake_api.dev_fixture import ensure_dev_fixture  # noqa: E402
from intake_api.otp import (  # noqa: E402
    CONSUMER_TENANT_ID,
    AuthWiring,
    DeliveryReceipt,
    DevLogDeliveryAdapter,
    OtpDeliveryAdapter,
    ensure_consumer_tenant,
    normalise_tr_phone,
)
from intake_api.settings import ApiSettings  # noqa: E402

PHONE = "+905321114455"
PHONE_FORMATTED = "+90 532 111 44 55"

# --- 10 §2 constants, pinned literally -------------------------------------------


def test_limits_match_files_10_section_2() -> None:
    assert OTP_TTL_S == 300, "OTP TTL is 5 minutes (files/10 §2)"
    assert OTP_MAX_ATTEMPTS == 5, "5 verify attempts per code (files/10 §2)"
    assert PHONE_LIMIT_PER_HOUR == 3, "3 requests/hour/phone (files/10 §2)"
    assert IP_LIMIT_PER_HOUR == 10, "10 requests/hour/IP (files/10 §2)"
    assert ACCESS_TTL_S == 900, "access tokens 15 min (files/10 §2)"
    assert RESEND_COOLDOWN_S == 60
    assert DEVICE_LIMIT_PER_HOUR == 3


# --- DPoP test client (RFC 9449 proofs over a P-256 key) --------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class DpopClient:
    """Client half of RFC 9449: one P-256 key, compact JWS proofs."""

    def __init__(self) -> None:
        self._key = ec.generate_private_key(ec.SECP256R1())
        numbers = self._key.public_key().public_numbers()
        self.jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64url(numbers.x.to_bytes(32, "big")),
            "y": _b64url(numbers.y.to_bytes(32, "big")),
        }

    def proof(
        self,
        method: str,
        url: str,
        *,
        iat: float,
        jti: str | None = None,
        access_token: str | None = None,
        typ: str = "dpop+jwt",
        tamper: bool = False,
    ) -> str:
        header = {"typ": typ, "alg": "ES256", "jwk": self.jwk}
        claims: dict[str, Any] = {
            "htm": method.upper(),
            "htu": url,
            "iat": int(iat),
            "jti": jti or uuid.uuid4().hex,
        }
        if access_token is not None:
            claims["ath"] = _b64url(hashlib.sha256(access_token.encode("ascii")).digest())
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(json.dumps(claims, separators=(",", ":")).encode())
        )
        der = self._key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes_sha256()))
        r, s = decode_dss_signature(der)
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        if tamper:
            raw = raw[:-1] + bytes([raw[-1] ^ 0x01])
        return signing_input + "." + _b64url(raw)


def hashes_sha256() -> Any:
    from cryptography.hazmat.primitives import hashes

    return hashes.SHA256()


# --- harness ----------------------------------------------------------------------


# Where inside a rate-limit window the harness clock starts. Far enough past
# the boundary not to be testing the boundary instant by accident, and far
# enough before the next one for every sequence below (LONGEST_WINDOW_SEQUENCE_S)
# — both pinned by the INT-285 tests.
WINDOW_START_OFFSET_S = 60.0


# The longest run of clock advances in this module that one window has to
# contain: the phone budget spent a resend cooldown at a time, then the refusal
# that proves it is spent. Derived from the limits rather than written as a
# number, so it follows if either constant moves.
def resend_step(admitted: int) -> float:
    """How far the clock moves after the ``admitted``-th code to one number so
    that the next request clears the resend wait. INT-577 made that wait
    exponential: the cooldown, doubled for each code the number already had in
    the window, plus the one second that makes it strictly enough."""
    return float(RESEND_COOLDOWN_S * 2 ** (admitted - 1) + 1)


LONGEST_WINDOW_SEQUENCE_S = sum(resend_step(n) for n in range(1, PHONE_LIMIT_PER_HOUR + 1))


class CountedDelivery:
    """Wraps the delivery a harness was built with and counts what reached it
    (INT-579). Nothing about a send is recorded but that it happened."""

    def __init__(self, inner: OtpDeliveryAdapter) -> None:
        self.inner = inner
        self.sends = 0

    async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
        self.sends += 1
        return await self.inner.send(phone_e164=phone_e164, code=code)


class Clock:
    """The suite's only clock (docs/TDD.md rule 6 — nothing here sleeps).

    Seeded from the START of a rate-limit window, never from the wall clock.
    That began as the INT-285 flake fix: ``auth_store`` counted in FIXED
    windows keyed on ``floor(now / OTP_WINDOW_S)``, so a sequence that stepped
    across a boundary saw the counters reset and a wall-clock seed made every
    refusal assertion below depend on the minute CI happened to start. INT-263
    made the windows roll, which removes that dependence at its source — the
    seed stays because it is now what lets a test CHOOSE its phase of the hour,
    and the INT-263 boundary tests do exactly that. Absolute time still tracks
    the real epoch — the DPoP ``iat`` skew check reads this same clock, and a
    synthetic epoch would hide a real-clock leak instead of proving there is
    none.
    """

    def __init__(self, offset_s: float = WINDOW_START_OFFSET_S) -> None:
        self.now = float(int(time.time()) // OTP_WINDOW_S * OTP_WINDOW_S) + offset_s

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


@dataclass
class OtpHarness:
    client: TestClient
    clock: Clock
    engine: Any
    audit_store: Any
    redis_client: Any
    delivery: Any = None
    base: str = "http://testserver"
    #: INT-578: the request id each admitted request was answered with, by
    #: canonical phone. A verify is bound to it, so the harness sends it back.
    request_ids: dict[str, str] = field(default_factory=dict)
    #: INT-579: every send that reached the delivery adapter. A withheld
    #: request answers exactly like a sent one, so this count is the only way
    #: a test can tell them apart.
    counted: Any = None

    @property
    def sends(self) -> int:
        return int(self.counted.sends) if self.counted is not None else 0

    def settle(self) -> None:
        """Wait for the background deliveries the last request scheduled
        (INT-579: the send is off the response path)."""
        settle = getattr(self.client.app.state.api.auth, "settle", None)
        if settle is not None:
            self.client.portal.call(settle)

    def challenge(self) -> str:
        response = self.client.post("/v1/auth/attest/challenge")
        assert response.status_code == 201, response.text
        challenge: str = response.json()["challenge"]
        return challenge

    def attestation(self, device_id: str = "device-a") -> dict[str, str]:
        payload = {
            "platform": "ios",
            "mode": "dev-unattested",
            "token": _b64url(b"intake-dev-attest"),
            "device_id": device_id,
            "nonce": self.challenge(),
        }
        return {"X-Intake-Attestation": json.dumps(payload)}

    def request_otp(self, phone: str = PHONE, device_id: str = "device-a") -> Any:
        before = self.sends
        response = self.client.post(
            "/v1/auth/otp/request",
            json={"phone": phone},
            headers=self.attestation(device_id),
        )
        self.settle()
        request_id = response.json().get("request_id") if response.status_code == 202 else None
        # only a code that was really sent has a request id worth verifying
        # against; a withheld request's id is a decoy (INT-579)
        if isinstance(request_id, str) and self.sends > before:
            self.request_ids[normalise_tr_phone(phone) or phone] = request_id
        return response

    def sent(self, phone: str = PHONE, device_id: str = "device-a") -> bool:
        """Request a code and say whether one was really sent: the answer is
        the same 202 either way (INT-579)."""
        before = self.sends
        response = self.request_otp(phone, device_id)
        assert response.status_code == 202, response.text
        return self.sends > before

    def peek(self, phone: str = PHONE) -> str:
        response = self.client.get("/v1/auth/dev/otp-peek", params={"phone": phone})
        assert response.status_code == 200, response.text
        code: str = response.json()["code"]
        return code

    def verify(
        self,
        dpop: DpopClient,
        phone: str = PHONE,
        code: str | None = None,
        device_id: str = "device-a",
        jti: str | None = None,
        request_id: str | None = None,
    ) -> Any:
        headers = self.attestation(device_id)
        headers["DPoP"] = dpop.proof(
            "POST", f"{self.base}/v1/auth/otp/verify", iat=self.clock(), jti=jti
        )
        bound = (
            request_id
            if request_id is not None
            else self.request_ids.get(normalise_tr_phone(phone) or phone)
        )
        return self.client.post(
            "/v1/auth/otp/verify",
            json={
                "phone": phone,
                "code": code if code is not None else self.peek(phone),
                "request_id": bound,
            },
            headers=headers,
        )

    def refresh(self, dpop: DpopClient, refresh_token: str) -> Any:
        headers = {
            "DPoP": dpop.proof("POST", f"{self.base}/v1/auth/token/refresh", iat=self.clock())
        }
        return self.client.post(
            "/v1/auth/token/refresh", json={"refresh_token": refresh_token}, headers=headers
        )

    def sign_up(self, dpop: DpopClient, phone: str = PHONE) -> dict[str, Any]:
        assert self.request_otp(phone).status_code == 202
        response = self.verify(dpop, phone)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def get_visits(self, dpop: DpopClient, access_token: str, jti: str | None = None) -> Any:
        proof = self.proof_for(dpop, "GET", "/v1/visits", access_token, jti=jti)
        return self.client.get(
            "/v1/visits",
            headers={"Authorization": f"DPoP {access_token}", "DPoP": proof},
        )

    def proof_for(
        self,
        dpop: DpopClient,
        method: str,
        path: str,
        access_token: str,
        jti: str | None = None,
    ) -> str:
        return dpop.proof(
            method, f"{self.base}{path}", iat=self.clock(), access_token=access_token, jti=jti
        )


def _build(
    tmp_path: Path,
    *,
    peek: bool = True,
    attested_dev: bool = True,
    token_patient: str | None = "unit-patient-token",  # noqa: S107 — unit fixture
    token_admin: str | None = "unit-admin-token",  # noqa: S107 — unit fixture
    clock_offset_s: float = WINDOW_START_OFFSET_S,
    carrier_geo: CarrierGeoCheck | None = None,
    delivery: OtpDeliveryAdapter | None = None,
    pepper: Any = None,
    sms_budget: Any = None,
    recipients: Any = None,
) -> Iterator[OtpHarness]:
    from intake_platform.db.audit_store import SqlAlchemyAuditStore
    from sqlalchemy import create_engine

    app_db = tmp_path / "auth.db"
    audit_db = tmp_path / "auth-audit.db"
    ddl = create_engine(f"sqlite+pysqlite:///{app_db}")
    sqlite_ddl_clone().create_all(ddl)
    ddl.dispose()
    audit_engine = create_engine(f"sqlite+pysqlite:///{audit_db}")
    sqlite_ddl_clone().create_all(audit_engine)

    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}", poolclass=NullPool)
    clock = Clock(clock_offset_s)
    fake_redis = fakeredis.FakeStrictRedis()
    delivery_adapter: OtpDeliveryAdapter = (
        delivery if delivery is not None else DevLogDeliveryAdapter()
    )
    counted = CountedDelivery(delivery_adapter)
    wiring = ApiWiring(
        settings=ApiSettings(
            token_patient=token_patient,
            token_admin=token_admin,
            app_db_url=f"sqlite+aiosqlite:///{app_db}",
            audit_db_url=f"sqlite+pysqlite:///{audit_db}",
            bootstrap_db_url=f"sqlite+aiosqlite:///{app_db}",
            kek_mode="file-dev",
        ),
        engine=engine,
        audit_store=SqlAlchemyAuditStore(audit_engine),
        cipher=EnvelopeCipher(FileKekProvider()),
        bootstrap=False,
        documents=None,
        auth=AuthWiring(
            redis_client=fake_redis,
            tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
            delivery=counted,
            attestation=(
                DevStructuralAttestationVerifier()
                if attested_dev
                else FailClosedAttestationVerifier()
            ),
            dev_otp_peek=peek,
            now_fn=clock,
            carrier_geo=carrier_geo if carrier_geo is not None else CarrierGeoCheck(),
            # INT-578: a test that needs to know the pepper passes one; every
            # other harness takes the wiring's own (a process-local random one)
            **({"pepper": pepper} if pepper is not None else {}),
            # INT-577: the tenant and global send caps, when a test sets them
            **({"sms_budget": sms_budget} if sms_budget is not None else {}),
            # INT-579: the synthetic host's test list, when a test sets one
            **({"recipients": recipients} if recipients is not None else {}),
        ),
    )
    run(ensure_consumer_tenant(engine))
    run(ensure_dev_fixture(engine))  # the dev-bearer tier stays load-bearing
    app = create_app(wiring)
    audit_store = wiring.audit_store
    with TestClient(app, raise_server_exceptions=False) as client:
        yield OtpHarness(
            client=client,
            clock=clock,
            engine=engine,
            audit_store=audit_store,
            redis_client=fake_redis,
            delivery=delivery_adapter,
            counted=counted,
        )
    run(engine.dispose())
    audit_engine.dispose()


@pytest.fixture()
def otp(tmp_path: Path) -> Iterator[OtpHarness]:
    yield from _build(tmp_path)


@pytest.fixture()
def otp_locked_down(tmp_path: Path) -> Iterator[OtpHarness]:
    """Production posture: no peek, no dev attestation acceptance."""
    yield from _build(tmp_path, peek=False, attested_dev=False)


# --- the harness clock (INT-285) ---------------------------------------------------
#
# `auth_store` used to count requests in FIXED windows: the counter key carried
# `floor(now / OTP_WINDOW_S)`. A sequence that stepped across a boundary
# therefore saw every counter reset, so while `Clock` was seeded from
# `time.time()` the refusals below held or did not hold according to the
# minute CI happened to start — 183 s of every 3600, about 5 % of runs, and one
# of them reddened an unrelated INT-016 gate run. INT-285 fixed the clock and
# pinned what the limiter then did; INT-263 (the next section) fixed the
# limiter. These three tests are unchanged and still hold the clock property —
# which is now what lets the section below put a sequence on a boundary on
# purpose rather than by luck.


def _window_floor() -> float:
    """The start of the window the wall clock is currently in."""
    return float(int(time.time()) // OTP_WINDOW_S * OTP_WINDOW_S)


@contextlib.contextmanager
def _harness(home: Path, clock_offset_s: float = WINDOW_START_OFFSET_S) -> Iterator[OtpHarness]:
    """`_build` outside the fixture, for the tests that choose their own clock."""
    home.mkdir(parents=True, exist_ok=True)
    built = _build(home, clock_offset_s=clock_offset_s)
    try:
        yield next(built)
    finally:
        next(built, None)  # resume past the yield so both engines are disposed


@pytest.mark.parametrize("phase", [0.0, 1.0, 1234.0, OTP_WINDOW_S - 1.0])
def test_the_clock_starts_at_the_same_point_whatever_the_wall_clock_says(
    phase: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _window_floor()
    monkeypatch.setattr(time, "time", lambda: base + phase)
    assert Clock().now == base + WINDOW_START_OFFSET_S


def test_the_clock_leaves_the_longest_window_sequence_room_inside_one_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Headroom asserted against the sequence, not against a number: the phone
    budget is spent one resend cooldown at a time and the refusal is the step
    after it, so LONGEST_WINDOW_SEQUENCE_S has to fit inside the window the
    sequence starts in — from the worst phase of the hour as much as any."""
    base = _window_floor()
    monkeypatch.setattr(time, "time", lambda: base + OTP_WINDOW_S - 1.0)
    headroom = OTP_WINDOW_S - (Clock().now % OTP_WINDOW_S)
    assert headroom > LONGEST_WINDOW_SEQUENCE_S


@pytest.mark.parametrize(
    "phase", [0.0, float(OTP_WINDOW_S - LONGEST_WINDOW_SEQUENCE_S), OTP_WINDOW_S - 1.0]
)
def test_the_per_phone_refusal_does_not_move_with_the_wall_clock(
    phase: float, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """test_per_phone_limit_three_per_hour, run at the phases of the hour that
    used to decide whether it passed: the same three admitted requests a
    cooldown apart, then the same refusal."""
    base = _window_floor()
    monkeypatch.setattr(time, "time", lambda: base + phase)
    with _harness(tmp_path / f"phase-{int(phase)}") as harness:
        for n in range(1, PHONE_LIMIT_PER_HOUR + 1):
            assert harness.request_otp().status_code == 202
            harness.clock.advance(resend_step(n))
        assert harness.request_otp().status_code == 429


# --- the rolling bound (INT-263) ---------------------------------------------------
#
# INT-285 pinned what a FIXED window actually enforces — 2 x the budget inside
# one rolling hour, six codes to one phone in about six minutes — and left the
# limiter alone, because changing how an abuse budget is counted is a semantics
# change on the authentication path. This section is that near-miss control
# INVERTED: the same boundary sequence, now required to REFUSE, plus the
# properties that make the refusal mean what files/10 §2 says.
#
# Every test here places its own clock so that the budget is spent with the
# last admitted request one second before a fixed-window boundary — which is
# exactly where a fixed window handed a second budget back, and therefore the
# only place where these assertions can tell the two schemes apart.


# The clock offset that does that for a dimension whose budget is spent `limit`
# requests `spacing` seconds apart. Derived from the limits, never written as a
# number, so it follows if a constant moves (INT-285).
def _boundary_offset_s(limit: int, spacing: float) -> float:
    return float(OTP_WINDOW_S) - (limit - 1) * spacing - 1.0


# The phone budget is spent at the backoff's pace (INT-577), so its first and
# last admissions are the sum of the first `limit - 1` resend steps apart.
PHONE_SPAN_S = sum(resend_step(n) for n in range(1, PHONE_LIMIT_PER_HOUR))
PHONE_BOUNDARY_OFFSET_S = float(OTP_WINDOW_S) - PHONE_SPAN_S - 1.0


def test_a_boundary_crossing_does_not_hand_the_budget_back(tmp_path: Path) -> None:
    """The INT-285 near-miss control, inverted. It admitted
    2 x PHONE_LIMIT_PER_HOUR codes to one phone in about six minutes because
    every counter reset on the hour. The same sequence must now stop at
    PHONE_LIMIT_PER_HOUR — and the refusal must land AFTER a fixed-window
    boundary has been crossed, or the test would pass against the old limiter
    too and prove nothing."""
    with _harness(tmp_path / "boundary", clock_offset_s=PHONE_BOUNDARY_OFFSET_S) as harness:
        started = harness.clock()
        for n in range(1, PHONE_LIMIT_PER_HOUR + 1):
            assert harness.request_otp().status_code == 202
            harness.clock.advance(resend_step(n))
        refused = harness.request_otp()
        assert refused.status_code == 429, "an hour boundary is not a fresh budget"
        assert refused.json()["error"] == "otp_limited"
        assert int(started // OTP_WINDOW_S) != int(harness.clock() // OTP_WINDOW_S), (
            "the sequence has to cross a fixed-window boundary or it proves nothing"
        )
        assert harness.clock() - started < OTP_WINDOW_S, "and stay inside one rolling hour"


@pytest.mark.parametrize(
    ("dimension", "limit", "spacing"),
    [
        ("phone", PHONE_LIMIT_PER_HOUR, 0.0),  # paced by the resend backoff (INT-577)
        ("ip", IP_LIMIT_PER_HOUR, 0.0),
        ("device", DEVICE_LIMIT_PER_HOUR, 0.0),
    ],
)
def test_every_dimension_holds_its_budget_across_a_boundary(
    dimension: str, limit: int, spacing: float, tmp_path: Path
) -> None:
    """files/10 §2 is per phone AND per IP; the device window mirrors the phone
    one. One function counts all three, so all three are walked across the
    boundary that used to reset them — the phone one paced by the resend
    cooldown, the other two at a single instant, which is what their own tests
    below already do."""

    def spend(harness: OtpHarness, n: int) -> Any:
        if dimension == "phone":
            return harness.request_otp(PHONE, device_id=f"device-{n}")
        if dimension == "ip":
            return harness.request_otp(f"+90532111{4400 + n:04d}", device_id=f"device-{n}")
        return harness.request_otp(f"+90533222{1100 + n:04d}", device_id="one-device")

    def step(admitted: int) -> float:
        return resend_step(admitted) if dimension == "phone" else spacing

    crossing = 2.0
    offset = float(OTP_WINDOW_S) - sum(step(n) for n in range(1, limit)) - 1.0
    with _harness(tmp_path / f"dim-{dimension}", clock_offset_s=offset) as harness:
        started = harness.clock()
        for n in range(1, limit + 1):
            assert spend(harness, n - 1).status_code == 202
            harness.clock.advance(step(n))
        harness.clock.advance(crossing)
        assert int(started // OTP_WINDOW_S) != int(harness.clock() // OTP_WINDOW_S)
        sends = harness.sends
        refused = spend(harness, limit)
        if dimension == "phone":
            # INT-579: the number's own budget is withheld, never refused, so a
            # stranger cannot read it: an admission's answer, and nothing sent
            assert refused.status_code == 202
            assert harness.sends == sends, "the phone budget survived the boundary"
        else:
            assert refused.status_code == 429, f"the {dimension} budget survived the boundary"
            assert refused.json()["error"] == "otp_limited"


def test_the_retry_after_is_the_true_wait_not_the_time_to_the_next_boundary(
    tmp_path: Path,
) -> None:
    """A caller sent away until :00 and refused again on arrival is worse than
    the bug. The advertised wait is the instant the oldest admission in the
    window leaves it — asserted to differ from the time to the next boundary
    first (or the test cannot tell the two answers apart), then asserted as a
    value, then walked: one second early still refuses, exactly the advertised
    wait is admitted."""
    with _harness(tmp_path / "retry-after", clock_offset_s=PHONE_BOUNDARY_OFFSET_S) as harness:
        oldest = harness.clock()
        for n in range(1, PHONE_LIMIT_PER_HOUR + 1):
            assert harness.request_otp().status_code == 202
            harness.clock.advance(resend_step(n))
        refused = harness.request_otp()
        assert refused.status_code == 429
        now = harness.clock()
        true_wait = oldest + OTP_WINDOW_S - now
        to_next_boundary = (int(now // OTP_WINDOW_S) + 1) * OTP_WINDOW_S - now
        assert true_wait != to_next_boundary, (
            "the two answers must differ here or this assertion is vacuous"
        )
        assert refused.json()["retry_after_s"] == pytest.approx(true_wait, abs=0.5)
        assert int(refused.headers["Retry-After"]) == int(true_wait) + 1
        harness.clock.advance(true_wait - 1)
        assert harness.request_otp().status_code == 429, "one second early still refuses"
        harness.clock.advance(1)
        assert harness.request_otp().status_code == 202, "and the advertised wait is enough"


def test_the_retry_after_stays_true_when_a_budget_is_tightened_under_live_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lowering a limit in response to an attack is the one operation that
    leaves more admissions in a window than the limit now allows. Two of them
    have to leave before the next request fits, so the honest wait is the
    SECOND oldest leaving, not the oldest. Driven against AuthStore directly:
    the constant is read at call time, and no route can lower a limit."""
    clock = Clock()
    store = AuthStore(fakeredis.FakeStrictRedis(), now_fn=clock)
    started = clock()
    for _ in range(PHONE_LIMIT_PER_HOUR):
        assert store.otp_request_gate("pseudo-1", "10.0.0.1", "device-1") is None
        clock.advance(RESEND_COOLDOWN_S + 1)
    monkeypatch.setattr(auth_store_module, "PHONE_LIMIT_PER_HOUR", PHONE_LIMIT_PER_HOUR - 1)
    wait = store.otp_request_gate("pseudo-1", "10.0.0.1", "device-1")
    assert wait is not None, "three admissions cannot fit a budget of two"
    second_oldest = started + (RESEND_COOLDOWN_S + 1)
    assert wait == pytest.approx(second_oldest + OTP_WINDOW_S - clock(), abs=0.5)
    clock.advance(wait)
    assert store.otp_request_gate("pseudo-1", "10.0.0.1", "device-1") is None


def test_no_rolling_window_span_admits_more_than_the_phone_budget(otp: OtpHarness) -> None:
    """The acceptance clause is about ANY OTP_WINDOW_S span, not about the one
    span a test happens to pick. One phone is polled every resend cooldown for
    two whole windows, and every window that STARTS at an admission is then
    checked — a fixed window fails this at the first boundary it crosses. The
    budget must also still replenish, or a limiter that refused everything
    after the first three requests would pass."""
    step = float(RESEND_COOLDOWN_S + 1)
    admitted: list[float] = []
    for _ in range(int(2 * OTP_WINDOW_S / step)):
        if otp.request_otp().status_code == 202:
            admitted.append(otp.clock())
        otp.clock.advance(step)
    assert len(admitted) >= 2 * PHONE_LIMIT_PER_HOUR, "the budget must still replenish"
    for start in admitted:
        inside = [t for t in admitted if start <= t < start + OTP_WINDOW_S]
        assert len(inside) <= PHONE_LIMIT_PER_HOUR, (
            f"{len(inside)} admitted in the window starting at {start - admitted[0]:.0f}s"
        )


def test_the_counter_key_set_is_bounded_and_does_not_grow_with_traffic(
    otp: OtpHarness,
) -> None:
    """O(1) per request over a bounded key set: one key per (dimension,
    identifier) whatever the traffic, holding at most that dimension's limit and
    expiring on its own — so the endpoint an attacker controls cannot be turned
    into unbounded memory, and a per-request timestamp list would fail here.
    Asserted, not described (acceptance line 4)."""
    step = float(RESEND_COOLDOWN_S + 1)
    for _ in range(int(2 * OTP_WINDOW_S / step)):
        otp.request_otp()
        otp.clock.advance(step)
    keys = sorted(str(k.decode()) for k in otp.redis_client.keys("auth:otp:w:*"))
    # INT-577 added the tenant hour budget and the global hour and day caps:
    # still one key each, whatever the traffic
    assert len(keys) == 6, f"one key per dimension for one caller, got {keys}"
    from intake_api.sms_spend import DAY_S, SmsBudget

    caps = SmsBudget()
    limits = {
        "phone": (PHONE_LIMIT_PER_HOUR, OTP_WINDOW_S),
        "ip": (IP_LIMIT_PER_HOUR, OTP_WINDOW_S),
        "device": (DEVICE_LIMIT_PER_HOUR, OTP_WINDOW_S),
        "tenant": (caps.tenant_sends_per_hour, OTP_WINDOW_S),
        "global_hour": (caps.global_sends_per_hour, OTP_WINDOW_S),
        "global_day": (caps.global_sends_per_day, DAY_S),
    }
    for key in keys:
        dimension = key.split(":")[3]
        assert dimension in limits, key
        limit, window = limits[dimension]
        assert otp.redis_client.zcard(key) <= limit
        assert 0 < otp.redis_client.ttl(key) <= window * 2


# --- limits (files/10 §2) ----------------------------------------------------------


def test_resend_cooldown_blocks_immediate_burst(otp: OtpHarness) -> None:
    assert otp.sent()
    # INT-579: the number's resend wait is withheld, not refused — the burst
    # gets an admission's answer, and no second code
    assert not otp.sent()
    otp.clock.advance(RESEND_COOLDOWN_S + 1)
    assert otp.sent()


def test_phone_formatting_does_not_fork_the_bucket(otp: OtpHarness) -> None:
    assert otp.sent(PHONE_FORMATTED)
    assert not otp.sent(PHONE), "another spelling of the number is the same number"


def test_per_phone_limit_three_per_hour(otp: OtpHarness) -> None:
    # LONGEST_WINDOW_SEQUENCE_S: the loop plus the refusal must land inside the
    # window the clock starts in, which is the whole reason that clock is not
    # seeded from time.time() (INT-285).
    # A device of its own for each request, so only the number's budget can
    # refuse; and INT-579 withholds that refusal rather than answering it.
    for n in range(1, PHONE_LIMIT_PER_HOUR + 1):
        assert otp.sent(device_id=f"device-{n}")
        otp.clock.advance(resend_step(n))
    assert not otp.sent(device_id="device-over")
    otp.clock.advance(OTP_WINDOW_S)  # deliberately the next window: budget back
    assert otp.sent(device_id="device-next")


def test_per_ip_limit_ten_per_hour(otp: OtpHarness) -> None:
    for n in range(IP_LIMIT_PER_HOUR):
        phone = f"+90532111{4400 + n:04d}"
        assert otp.request_otp(phone, device_id=f"device-{n}").status_code == 202
    refused = otp.request_otp("+905321119999", device_id="device-fresh")
    assert refused.status_code == 429
    assert refused.json()["error"] == "otp_limited"


def test_per_device_window(otp: OtpHarness) -> None:
    for n in range(DEVICE_LIMIT_PER_HOUR):
        phone = f"+90533222{1100 + n:04d}"
        assert otp.request_otp(phone, device_id="one-device").status_code == 202
    refused = otp.request_otp("+905332229999", device_id="one-device")
    assert refused.status_code == 429


def test_invalid_phone_is_422_and_costs_no_budget(otp: OtpHarness) -> None:
    response = otp.request_otp("1234")
    assert response.status_code == 422
    assert response.json()["error"] == "phone_invalid"
    assert otp.request_otp().status_code == 202


def test_five_wrong_attempts_burn_the_code(otp: OtpHarness) -> None:
    dpop = DpopClient()
    assert otp.request_otp().status_code == 202
    real_code = otp.peek()
    wrong = "000000" if real_code != "000000" else "111111"
    for _ in range(OTP_MAX_ATTEMPTS):
        response = otp.verify(dpop, code=wrong)
        assert response.status_code == 401
        assert response.json() == {"error": "otp_invalid"}
    # attempt budget exhausted: even the REAL code is refused now
    assert otp.verify(dpop, code=real_code).status_code == 401
    # INT-578: the fifth miss also locked the number, so a fresh code waits
    # for the lockout rather than the resend cooldown; read at call time so
    # this module still collects where the constant does not exist
    lockout_s: int = getattr(auth_store_module, "OTP_LOCKOUT_S")  # noqa: B009
    otp.clock.advance(lockout_s + 1)
    assert otp.request_otp().status_code == 202
    assert otp.verify(dpop).status_code == 200


def test_code_expires_after_five_minutes(otp: OtpHarness) -> None:
    dpop = DpopClient()
    assert otp.request_otp().status_code == 202
    code = otp.peek()
    otp.clock.advance(OTP_TTL_S + 1)
    assert otp.verify(dpop, code=code).status_code == 401


# --- secrecy (invariant 6): codes and phones stay out of logs and responses --------


def test_code_and_phone_never_in_logs_or_request_response(
    otp: OtpHarness, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        response = otp.request_otp()
    assert response.status_code == 202
    body = response.json()
    code = otp.peek()
    assert len(code) == 6 and code.isdigit(), "OTP is 6 digits (files/10 §2)"
    assert code not in json.dumps(body)
    everything = "\n".join(
        record.getMessage() + " " + str(record.args) + " " + str(getattr(record, "extra", ""))
        for record in caplog.records
    )
    assert code not in everything, "the OTP code leaked into a log line"
    assert "5321114455" not in everything, "the raw phone leaked into a log line"
    assert "delivery" in everything.lower(), "the delivery EVENT itself must be logged (id-only)"


def test_no_raw_phone_in_the_database(otp: OtpHarness) -> None:
    dpop = DpopClient()
    otp.sign_up(dpop)

    async def _pseudonyms() -> list[str]:
        async with AsyncSession(otp.engine) as session:
            rows = await session.scalars(
                select(Patient.pseudonym).where(Patient.tenant_id == CONSUMER_TENANT_ID)
            )
            return list(rows.all())

    pseudonyms = run(_pseudonyms())
    assert pseudonyms, "verify must create the patient row"
    for pseudonym in pseudonyms:
        assert "5321114455" not in pseudonym
        assert pseudonym.startswith("v1."), "pseudonym is the Tokenizer's kid.hex output"


# --- fail-closed gates ---------------------------------------------------------------


def test_peek_is_404_when_flag_absent(otp_locked_down: OtpHarness) -> None:
    response = otp_locked_down.client.get("/v1/auth/dev/otp-peek", params={"phone": PHONE})
    assert response.status_code == 404


def test_attestation_fails_closed_without_dev_flag(otp_locked_down: OtpHarness) -> None:
    response = otp_locked_down.client.post(
        "/v1/auth/otp/request",
        json={"phone": PHONE},
        headers=otp_locked_down.attestation(),
    )
    assert response.status_code == 403
    assert response.json()["error"] == "attestation_unverified"


def test_missing_attestation_header_is_403(otp: OtpHarness) -> None:
    response = otp.client.post("/v1/auth/otp/request", json={"phone": PHONE})
    assert response.status_code == 403
    assert response.json()["error"] == "attestation_required"


def test_challenge_nonce_is_single_use(otp: OtpHarness) -> None:
    nonce = otp.challenge()
    payload = {
        "platform": "ios",
        "mode": "dev-unattested",
        "token": _b64url(b"intake-dev-attest"),
        "device_id": "device-a",
        "nonce": nonce,
    }
    headers = {"X-Intake-Attestation": json.dumps(payload)}
    first = otp.client.post("/v1/auth/otp/request", json={"phone": PHONE}, headers=headers)
    assert first.status_code == 202
    otp.clock.advance(RESEND_COOLDOWN_S + 1)
    replayed = otp.client.post("/v1/auth/otp/request", json={"phone": PHONE}, headers=headers)
    assert replayed.status_code == 403
    assert replayed.json()["error"] == "challenge_invalid"


# --- tokens: DPoP binding, rotation, reuse detection --------------------------------


def test_verify_issues_dpop_bound_tokens_and_creates_one_patient(otp: OtpHarness) -> None:
    dpop = DpopClient()
    body = otp.sign_up(dpop)
    assert body["token_type"] == "DPoP"
    assert body["expires_in"] == ACCESS_TTL_S
    assert body["access_token"] != body["refresh_token"]

    # authenticated resource call carries the otp tier tag and hits the
    # consent gate honestly (no consent rows exist until INT-132 grants them)
    visits = otp.get_visits(dpop, body["access_token"])
    assert visits.status_code == 403
    assert visits.json() == {"error": "consent_required", "scope": "core"}
    assert visits.headers["x-intake-auth-tier"] == "otp"

    # a second sign-in with the SAME phone reuses the patient row
    otp.clock.advance(RESEND_COOLDOWN_S + 1)
    again = otp.sign_up(DpopClient())
    assert again["patient_id"] == body["patient_id"]

    async def _count() -> int:
        async with AsyncSession(otp.engine) as session:
            rows = await session.scalars(
                select(Patient.id).where(Patient.tenant_id == CONSUMER_TENANT_ID)
            )
            return len(rows.all())

    assert run(_count()) == 1


def test_access_token_without_proof_or_with_wrong_key_is_401(otp: OtpHarness) -> None:
    dpop = DpopClient()
    body = otp.sign_up(dpop)
    token = body["access_token"]
    bare = otp.client.get("/v1/visits", headers={"Authorization": f"DPoP {token}"})
    assert bare.status_code == 401
    stranger = DpopClient()
    stolen = otp.client.get(
        "/v1/visits",
        headers={
            "Authorization": f"DPoP {token}",
            "DPoP": stranger.proof(
                "GET", f"{otp.base}/v1/visits", iat=otp.clock(), access_token=token
            ),
        },
    )
    assert stolen.status_code == 401


def test_dpop_proof_replay_is_rejected(otp: OtpHarness) -> None:
    dpop = DpopClient()
    body = otp.sign_up(dpop)
    token = body["access_token"]
    proof = otp.proof_for(dpop, "GET", "/v1/visits", token, jti="fixed-jti-for-replay")
    headers = {"Authorization": f"DPoP {token}", "DPoP": proof}
    first = otp.client.get("/v1/visits", headers=headers)
    assert first.status_code in (200, 403)  # consent decides; auth accepted either way
    replay = otp.client.get("/v1/visits", headers=headers)
    assert replay.status_code == 401
    assert replay.json()["error"].startswith("dpop_")


def test_tampered_or_stale_proofs_are_rejected(otp: OtpHarness) -> None:
    dpop = DpopClient()
    body = otp.sign_up(dpop)
    token = body["access_token"]
    tampered = dpop.proof(
        "GET", f"{otp.base}/v1/visits", iat=otp.clock(), access_token=token, tamper=True
    )
    response = otp.client.get(
        "/v1/visits", headers={"Authorization": f"DPoP {token}", "DPoP": tampered}
    )
    assert response.status_code == 401
    stale = dpop.proof("GET", f"{otp.base}/v1/visits", iat=otp.clock() - 3600, access_token=token)
    response = otp.client.get(
        "/v1/visits", headers={"Authorization": f"DPoP {token}", "DPoP": stale}
    )
    assert response.status_code == 401
    wrong_route = dpop.proof("GET", f"{otp.base}/v1/notes", iat=otp.clock(), access_token=token)
    response = otp.client.get(
        "/v1/visits", headers={"Authorization": f"DPoP {token}", "DPoP": wrong_route}
    )
    assert response.status_code == 401


def test_refresh_rotates_and_reuse_revokes_the_family(otp: OtpHarness) -> None:
    dpop = DpopClient()
    body = otp.sign_up(dpop)
    first_refresh = body["refresh_token"]

    rotated = otp.refresh(dpop, first_refresh)
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first_refresh
    assert second["access_token"] != body["access_token"]

    # REUSE of the rotated-away token: reuse detection revokes the family
    reused = otp.refresh(dpop, first_refresh)
    assert reused.status_code == 401
    assert reused.json()["error"] == "refresh_reused"

    # the audit chain recorded the revocation (invariant 4)
    last = otp.audit_store.last()
    assert last is not None and last.action == "auth.refresh.reuse_detected"

    # the WHOLE family is dead, including the newest member
    revoked = otp.refresh(dpop, second["refresh_token"])
    assert revoked.status_code == 401


def test_refresh_is_device_bound(otp: OtpHarness) -> None:
    dpop = DpopClient()
    body = otp.sign_up(dpop)
    stranger = DpopClient()
    response = otp.refresh(stranger, body["refresh_token"])
    assert response.status_code == 401
    # binding failure is NOT reuse: the family must survive for the real key
    assert otp.refresh(dpop, body["refresh_token"]).status_code == 200


# --- tier honesty ---------------------------------------------------------------------


def test_dev_bearer_accounts_keep_working_and_stay_dev_tier(otp: OtpHarness) -> None:
    response = otp.client.get("/v1/visits", headers={"Authorization": "Bearer unit-patient-token"})
    assert response.status_code == 200
    assert response.headers["x-intake-auth-tier"] == "dev"


def test_auth_endpoints_are_tagged_otp_tier(otp: OtpHarness) -> None:
    response = otp.request_otp()
    assert response.status_code == 202
    assert response.headers["x-intake-auth-tier"] == "otp"


# --- INT-308: the carrier/geo sanity check (files/10 §2) -----------------------------
#
# files/10 §2 named "carrier/geo sanity checks against SMS pumping" in the same
# sentence as the budgets above, and no code honoured it; INT-263 marked it
# named-but-unbuilt rather than let the sentence read as coverage. What lands
# here is the control and, more importantly, its ASYMMETRY: a lookup that cannot
# be made ADMITS, and only a positive signal REFUSES. A carrier check that
# failed closed would lock a patient out of their own intake the first time a
# lookup timed out, which is a worse failure than the cost it was meant to save.
#
# The carrier half ships INERT: infra/security/msisdn_allocation.yaml declares
# no prefixes, because which 5XX prefixes the BTK has allocated is a published
# fact nobody here has read from the publication (docs/backlog/blockers.md). So
# the tests below drive the mechanism from injected fixture tables, and one test
# pins the shipped file's emptiness so that supplying it is a visible change.

#: A number in the fixture table's allocated prefix (505) — a real subscriber.
PHONE_ALLOCATED = "+905051114455"
#: PHONE's own prefix, 532, is deliberately ABSENT from the fixture table.
UNALLOCATED_PHONES = ("+905321114455", "+905322224455", "+905323334455")

_FIXTURE_SOURCE = AllocationSource(
    authority="fixture",
    document="unit-fixture allocation table",
    published_on="2026-01-01",
    url="https://example.invalid/fixture",
    retrieved_on="2026-01-01",
)


def _exhaustive_table(*prefixes: str) -> AllocationTable:
    """A table that declares itself COMPLETE, so an absent prefix is a positive
    'not allocated' — the only shape that can refuse anything."""
    return AllocationTable(
        country_code="90",
        exhaustive=True,
        allocated_prefixes=prefixes,
        source=_FIXTURE_SOURCE,
    )


class RecordingDelivery:
    """Counts SMS sends without recording anything about them (invariant 6).
    The count is the assertion that matters: an SMS not sent is the entire
    point of an anti-pumping control."""

    def __init__(self) -> None:
        self.sends = 0

    async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
        del phone_e164, code
        self.sends += 1
        return DeliveryReceipt(delivery_id=uuid.uuid4().hex)


class RaisingAuthority:
    """An authority whose lookup fails — a timeout, a dead resolver, a bug."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def allocated(self, *, country_code: str, operator_prefix: str) -> bool | None:
        del country_code, operator_prefix
        self.calls += 1
        raise self.error


@contextlib.contextmanager
def _carrier_harness(
    home: Path,
    *,
    check: CarrierGeoCheck,
    delivery: RecordingDelivery,
) -> Iterator[OtpHarness]:
    home.mkdir(parents=True, exist_ok=True)
    built = _build(home, carrier_geo=check, delivery=delivery)
    try:
        yield next(built)
    finally:
        next(built, None)


# --- the shipped authority, and what a row costs -------------------------------------


def test_the_shipped_allocation_table_declares_no_prefixes_and_cannot_refuse() -> None:
    """The committed file is EMPTY and that is the current state, not an
    omission — so this test is expected to change when a human supplies the
    BTK list, and the change is the point (docs/backlog/blockers.md).

    Pinned rather than assumed: an empty table that quietly declared itself
    exhaustive would refuse every Turkish mobile in existence."""
    table = load_allocation_table(MSISDN_ALLOCATION_PATH)
    assert table.country_code == "90"
    assert table.allocated_prefixes == ()
    assert table.exhaustive is False
    assert table.can_refuse is False
    assert AllocationTableAuthority(table).can_refuse is False


def test_a_prefix_list_without_a_source_is_refused() -> None:
    """Which prefixes an authority allocated is a published fact. A list with
    nothing to re-read it against is the invented value rule 1 forbids, so the
    model refuses it rather than trusting whoever typed it."""
    with pytest.raises(ValueError, match="without a source"):
        AllocationTable(country_code="90", exhaustive=True, allocated_prefixes=("505",))


def test_a_table_with_a_source_but_no_prefixes_is_fine() -> None:
    """The near-miss of the rule above: the constraint is one-directional. A
    source with an empty list is a human saying 'I read it and recorded
    nothing yet', which must stay expressible."""
    table = AllocationTable(country_code="90", exhaustive=False, source=_FIXTURE_SOURCE)
    assert table.can_refuse is False


def test_split_e164_reads_the_operator_prefix_and_nothing_else() -> None:
    assert split_e164("+905321114455") == ("90", "532")
    assert split_e164("+905051114455") == ("90", "505")
    # anything that is not the one plan this check understands says nothing,
    # because refusing on a parse this module got wrong is the wrong direction
    assert split_e164("+15551114455") is None
    assert split_e164("+9053211144") is None
    assert split_e164("+90532111445x") is None


# --- the asymmetry: two tests, one per direction (acceptance clause 2) ---------------


@pytest.mark.parametrize(
    "error",
    [TimeoutError("carrier lookup timed out"), ConnectionError("no route"), RuntimeError("bug")],
    ids=["timeout", "connection", "bug"],
)
def test_a_carrier_lookup_that_fails_still_lets_the_patient_in(
    tmp_path: Path, error: BaseException, caplog: pytest.LogCaptureFixture
) -> None:
    """FAIL OPEN. A carrier lookup that times out must not lock a legitimate
    patient out of their own intake — the cost of a missed pumping attempt is
    money; the cost of a locked-out patient is an intake that does not happen."""
    authority = RaisingAuthority(error)
    delivery = RecordingDelivery()
    with caplog.at_level(logging.DEBUG):
        with _carrier_harness(
            tmp_path / "open", check=CarrierGeoCheck(authority=authority), delivery=delivery
        ) as harness:
            response = harness.request_otp(PHONE_ALLOCATED)
            assert response.status_code == 202, response.text
            assert harness.peek(PHONE_ALLOCATED).isdigit()
    assert authority.calls == 1, "the lookup was actually attempted"
    assert delivery.sends == 1, "the SMS went out despite the failed lookup"
    # Invariant 6, scoped to what this test can actually speak for: the records
    # THIS SYSTEM emits. A whole-capture grep at DEBUG also catches httpx
    # logging the harness's own dev-peek URL, which carries the phone as a query
    # parameter — a real property of that dev-only route (recorded in
    # docs/evidence/INT-308.md) and not something the carrier check can fix, so
    # asserting over it here would make this test fail for another route's
    # reason.
    ours = [r for r in caplog.records if r.name.startswith("intake_api")]
    assert any("fail open" in r.getMessage() for r in ours), (
        "a lookup that did not happen must be visible"
    )
    for record in ours:
        assert "5051114455" not in record.getMessage(), record.getMessage()
    # The check's own line is a fixed string with no arguments, so nothing from
    # the number — the operator prefix included — can reach it. Asserted as "no
    # digit at all" rather than "not 505": a three-digit needle matches by
    # accident against byte counts and uuid hex, which would make the assertion
    # pass or fail for reasons unrelated to it.
    mine = [r.getMessage() for r in ours if r.name == "intake_api.carrier_geo"]
    assert mine, "the fail-open path must say so"
    for message in mine:
        assert not any(char.isdigit() for char in message), message


def test_a_positively_unallocated_prefix_refuses_before_any_sms(tmp_path: Path) -> None:
    """FAIL CLOSED on a positive signal. The prefix is absent from a table that
    declares itself complete, so no operator has it, so no subscriber is behind
    it and the SMS is pure cost. It is refused BEFORE the code is minted."""
    delivery = RecordingDelivery()
    check = CarrierGeoCheck(authority=AllocationTableAuthority(_exhaustive_table("505")))
    with _carrier_harness(tmp_path / "closed", check=check, delivery=delivery) as harness:
        response = harness.request_otp(PHONE)
        assert response.status_code == 422, response.text
        # the same generic code a malformed number gets: a distinct code would
        # tell a caller which of its numbers exist (files/10 §9 row 1)
        assert response.json() == {"error": "phone_invalid"}
        assert delivery.sends == 0, "an SMS was sent to a number no operator allocated"
        # no code was minted either, so there is nothing to verify against
        peek = harness.client.get("/v1/auth/dev/otp-peek", params={"phone": PHONE})
        assert peek.status_code == 404


# --- near-miss negative controls -----------------------------------------------------


def test_an_allocated_prefix_still_gets_its_sms_under_the_same_table(tmp_path: Path) -> None:
    """The near miss of the refusal above: same table, same request, a prefix
    that IS allocated. A check that refused everything would pass the test
    above and fail here, which is the only reason that test means anything."""
    delivery = RecordingDelivery()
    check = CarrierGeoCheck(authority=AllocationTableAuthority(_exhaustive_table("505")))
    with _carrier_harness(tmp_path / "near", check=check, delivery=delivery) as harness:
        assert harness.request_otp(PHONE_ALLOCATED).status_code == 202
        assert delivery.sends == 1


def test_a_partial_list_has_no_opinion_and_admits_the_same_number(tmp_path: Path) -> None:
    """The near miss that costs the most if it is inverted. The ONLY difference
    from the refusal test is `exhaustive`: absent from a COMPLETE list is a
    positive 'not allocated'; absent from a PARTIAL list is silence. Getting
    this one boolean backwards refuses every subscriber the list forgot."""
    partial = AllocationTable(
        country_code="90",
        exhaustive=False,
        allocated_prefixes=("505",),
        source=_FIXTURE_SOURCE,
    )
    assert partial.can_refuse is False
    delivery = RecordingDelivery()
    with _carrier_harness(
        tmp_path / "partial",
        check=CarrierGeoCheck(authority=AllocationTableAuthority(partial)),
        delivery=delivery,
    ) as harness:
        assert harness.request_otp(PHONE).status_code == 202
        assert delivery.sends == 1


def test_a_table_for_another_country_has_no_opinion(tmp_path: Path) -> None:
    """One table answers for one numbering plan. A +90 number checked against a
    +44 table is unknown, not unallocated."""
    other = AllocationTable(
        country_code="44", exhaustive=True, allocated_prefixes=("770",), source=_FIXTURE_SOURCE
    )
    check = CarrierGeoCheck(authority=AllocationTableAuthority(other))
    assert check.evaluate(PHONE).outcome is CarrierGeoOutcome.UNCHECKED


def test_a_non_turkish_number_never_reaches_the_delivery_adapter(tmp_path: Path) -> None:
    """The GEO half, which held before INT-308 and must still hold: the
    international premium ranges SMS pumping actually profits from are refused
    by normalise_tr_phone long before any carrier question is asked. This is
    the single most load-bearing anti-pumping property the system has and it is
    a consequence of being a Turkish-only product, so it is pinned rather than
    claimed."""
    delivery = RecordingDelivery()
    with _carrier_harness(tmp_path / "geo", check=CarrierGeoCheck(), delivery=delivery) as harness:
        for foreign in ("+15551114455", "+447700900123", "+992001114455"):
            assert harness.request_otp(foreign).status_code == 422
        assert delivery.sends == 0


def test_an_unreadable_authority_admits_rather_than_locking_everyone_out(tmp_path: Path) -> None:
    """A config error is a lookup that cannot be made, and those admit. The
    warning is the visible surface: a broken table must not be silent."""
    broken = tmp_path / "broken.yaml"
    broken.write_text("allocated_prefixes: [\n", encoding="utf-8")
    with pytest.raises(CarrierGeoConfigError):
        load_allocation_table(broken)
    check = carrier_geo_from_path(broken)
    assert check.authority is None
    assert check.evaluate(PHONE).outcome is CarrierGeoOutcome.UNCHECKED
    assert carrier_geo_from_path(tmp_path / "absent.yaml").evaluate(PHONE).refuses is False


def test_a_carrier_refusal_costs_the_caller_its_budget(tmp_path: Path) -> None:
    """The check sits AFTER the abuse gate, not before it. If it ran first, a
    refused caller would pay nothing and could probe which prefixes refuse for
    free on an unauthenticated endpoint; and the budgets, which are what
    actually stands against pumping today, would stop counting the traffic."""
    delivery = RecordingDelivery()
    check = CarrierGeoCheck(authority=AllocationTableAuthority(_exhaustive_table("505")))
    with _carrier_harness(tmp_path / "budget", check=check, delivery=delivery) as harness:
        for phone in UNALLOCATED_PHONES[:DEVICE_LIMIT_PER_HOUR]:
            assert harness.request_otp(phone).status_code == 422
        # the device budget is spent, so even the allocated number is refused
        spent = harness.request_otp(PHONE_ALLOCATED)
        assert spent.status_code == 429
        assert spent.json()["error"] == "otp_limited"
        assert delivery.sends == 0


# --- invariant 6: the derivation is not stored anywhere ------------------------------


def test_the_carrier_check_stores_no_prefix_carrier_or_country(tmp_path: Path) -> None:
    """No new personal data is persisted to achieve the control, so no new
    inventory annotation is owed — asserted rather than stated. The Redis key
    namespaces stay the closed set the OTP tier already had, and no key or
    value anywhere carries the operator prefix."""
    delivery = RecordingDelivery()
    check = CarrierGeoCheck(authority=AllocationTableAuthority(_exhaustive_table("505")))
    with _carrier_harness(tmp_path / "store", check=check, delivery=delivery) as harness:
        assert harness.request_otp(PHONE).status_code == 422
        harness.clock.advance(RESEND_COOLDOWN_S + 1)
        assert harness.request_otp(PHONE_ALLOCATED).status_code == 202
        keys = [key.decode() for key in harness.redis_client.keys("*")]
        namespaces = {":".join(key.split(":")[:2]) for key in keys}
        assert namespaces <= {
            "auth:otp",
            "auth:chal",
            "auth:acc",
            "auth:ref",
            "auth:fam",
            "auth:jti",
        }, f"the carrier check opened a new keyspace: {namespaces}"
        # Structural, not a substring hunt: a three-digit prefix matches inside a
        # sha256 hex digest by accident nearly every run, so the assertion is
        # over the SHAPE of what is stored. A stored carrier or country would
        # need either a key outside this grammar or a field outside the code
        # record's closed set, and both are checked.
        for key in keys:
            parts = key.split(":")
            if parts[:3] == ["auth", "otp", "w"]:
                # INT-577 added the tenant budget and the two global caps
                assert parts[3] in {
                    "ip",
                    "device",
                    "phone",
                    "tenant",
                    "global_hour",
                    "global_day",
                }, key
            elif parts[:2] == ["auth", "otp"]:
                # INT-578 added the attempt counter and the lockout instant,
                # INT-577 the spend kill switch
                assert parts[2] in {"cool", "code", "peek", "att", "lock", "kill"}, key
            if parts[:3] == ["auth", "otp", "code"]:
                record = json.loads(harness.redis_client.get(key))
                # INT-578: the attempts left the record for an atomic counter,
                # and the device binding (an HMAC) joined it
                assert set(record) == {"digest", "binding", "expires"}, record
        # and the numbers themselves, which ARE specific enough to grep for
        for key in keys:
            blob = key + " " + str(harness.redis_client.dump(key))
            assert "5321114455" not in blob
            assert "5051114455" not in blob


def test_a_carrier_refusal_writes_no_audit_row(tmp_path: Path) -> None:
    """A refused request is a number nobody owns. Writing an audit row keyed on
    its pseudonym would be storing a derivation about a person who does not
    exist, and the budget refusal beside it audits nothing either."""
    delivery = RecordingDelivery()
    check = CarrierGeoCheck(authority=AllocationTableAuthority(_exhaustive_table("505")))
    with _carrier_harness(tmp_path / "audit", check=check, delivery=delivery) as harness:
        assert harness.request_otp(PHONE).status_code == 422
        assert harness.audit_store.entries() == ()


def test_a_malformed_prefix_list_is_refused() -> None:
    """Two shapes that would silently weaken the table: a duplicate (which
    makes 'exhaustive' ambiguous about what was read) and a non-digit prefix
    (which can never match a derivation and so is a row that does nothing)."""
    with pytest.raises(ValueError, match="duplicate"):
        AllocationTable(
            country_code="90",
            exhaustive=True,
            allocated_prefixes=("505", "505"),
            source=_FIXTURE_SOURCE,
        )
    with pytest.raises(ValueError, match="not a run of digits"):
        AllocationTable(
            country_code="90",
            exhaustive=True,
            allocated_prefixes=("5O5",),
            source=_FIXTURE_SOURCE,
        )


def test_a_supplied_exhaustive_table_wires_a_check_that_can_refuse(tmp_path: Path) -> None:
    """What lands the day a human answers the blocker: the same loader, the
    same wiring, and a check that now has an opinion. Written now so that
    supplying the list is a data change and not a code change."""
    supplied = tmp_path / "supplied.yaml"
    supplied.write_text(
        "country_code: '90'\n"
        "exhaustive: true\n"
        "allocated_prefixes: ['505']\n"
        "source:\n"
        "  authority: fixture\n"
        "  document: unit-fixture allocation table\n"
        "  published_on: '2026-01-01'\n"
        "  url: https://example.invalid/fixture\n"
        "  retrieved_on: '2026-01-01'\n",
        encoding="utf-8",
    )
    check = carrier_geo_from_path(supplied)
    assert check.evaluate(PHONE_ALLOCATED).outcome is CarrierGeoOutcome.ADMIT
    assert check.evaluate(PHONE).refuses is True


def test_an_empty_allocation_file_is_an_empty_table_not_a_crash(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(CarrierGeoConfigError):
        # country_code and exhaustive have no defaults: a table that does not
        # say which plan it answers for, or whether its list is complete, is
        # not a table this check will act on
        load_allocation_table(empty)
