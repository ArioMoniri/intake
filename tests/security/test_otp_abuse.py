"""INT-131 — OTP abuse limits, DPoP binding, refresh-family reuse detection.

Acceptance lines pinned here (files/10 §2, verbatim source of the numbers):
  "phone OTP (6 digits, 5-min TTL, 5 attempts, 3 requests/hour/phone,
  10/hour/IP …) + device attestation … on OTP request and session start;
  Access tokens 15 min, refresh tokens rotating and device-bound (DPoP,
  RFC 9449); refresh reuse detection revokes the family"

What this file proves:
- the 10 §2 limits are enforced: resend cooldown (burst), 3/hour/phone,
  10/hour/IP, per-device window, 5 verify attempts then the code is dead;
- those budgets are ROLLING, not per fixed hour (INT-265): no dimension admits
  more than its limit in ANY OTP_WINDOW_S span, a boundary crossing hands no
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
no assertion here depends on the minute the suite runs (INT-264), and the
INT-265 tests can place a sequence at a chosen phase of the hour on purpose.
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
from dataclasses import dataclass
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
)
from intake_api.dev_fixture import ensure_dev_fixture  # noqa: E402
from intake_api.otp import (  # noqa: E402
    CONSUMER_TENANT_ID,
    AuthWiring,
    DevLogDeliveryAdapter,
    ensure_consumer_tenant,
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
# — both pinned by the INT-264 tests.
WINDOW_START_OFFSET_S = 60.0

# The longest run of clock advances in this module that one window has to
# contain: the phone budget spent a resend cooldown at a time, then the refusal
# that proves it is spent. Derived from the limits rather than written as a
# number, so it follows if either constant moves.
LONGEST_WINDOW_SEQUENCE_S = PHONE_LIMIT_PER_HOUR * (RESEND_COOLDOWN_S + 1)


class Clock:
    """The suite's only clock (docs/TDD.md rule 6 — nothing here sleeps).

    Seeded from the START of a rate-limit window, never from the wall clock.
    That began as the INT-264 flake fix: ``auth_store`` counted in FIXED
    windows keyed on ``floor(now / OTP_WINDOW_S)``, so a sequence that stepped
    across a boundary saw the counters reset and a wall-clock seed made every
    refusal assertion below depend on the minute CI happened to start. INT-265
    made the windows roll, which removes that dependence at the source — the
    seed is kept because it is now what lets a test CHOOSE its phase, and the
    INT-265 boundary tests do exactly that. Absolute time still tracks the real
    epoch — the DPoP ``iat`` skew check reads this same clock, and a synthetic
    epoch would hide a real-clock leak instead of proving there is none.
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
    base: str = "http://testserver"

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
        return self.client.post(
            "/v1/auth/otp/request",
            json={"phone": phone},
            headers=self.attestation(device_id),
        )

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
    ) -> Any:
        headers = self.attestation(device_id)
        headers["DPoP"] = dpop.proof(
            "POST", f"{self.base}/v1/auth/otp/verify", iat=self.clock(), jti=jti
        )
        return self.client.post(
            "/v1/auth/otp/verify",
            json={"phone": phone, "code": code if code is not None else self.peek(phone)},
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
            delivery=DevLogDeliveryAdapter(),
            attestation=(
                DevStructuralAttestationVerifier()
                if attested_dev
                else FailClosedAttestationVerifier()
            ),
            dev_otp_peek=peek,
            now_fn=clock,
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


# --- the harness clock (INT-264) ---------------------------------------------------
#
# `auth_store` used to count requests in FIXED windows: the counter key carried
# `floor(now / OTP_WINDOW_S)`. A sequence that stepped across a boundary
# therefore saw every counter reset, so while `Clock` was seeded from
# `time.time()` the refusals below held or did not hold according to the
# minute CI happened to start — 183 s of every 3600, about 5 % of runs, and
# one of them reddened an unrelated INT-016 gate run. INT-264 fixed the clock
# and pinned the limiter's behaviour; INT-265 (the next section) fixed the
# limiter. These three tests still hold the clock property, which is what lets
# the section below place a sequence on a boundary deliberately.


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
        for _ in range(PHONE_LIMIT_PER_HOUR):
            assert harness.request_otp().status_code == 202
            harness.clock.advance(RESEND_COOLDOWN_S + 1)
        assert harness.request_otp().status_code == 429


# --- the rolling bound (INT-265) ---------------------------------------------------
#
# INT-264 pinned what a FIXED window actually enforces — 2 x the budget inside
# one rolling hour, six codes to one phone in about six minutes — and left the
# limiter alone. This section is that control INVERTED: the same boundary
# sequence, now required to REFUSE, plus the properties that make the refusal
# mean what files/10 §2 says. The offset is chosen so the budget is spent with
# the last admitted request one second before a fixed-window boundary, which is
# exactly where a fixed window used to hand a second budget back.

# Clock offset that puts the last of PHONE_LIMIT_PER_HOUR admitted requests one
# second before a fixed-window boundary, spending them one resend cooldown
# apart. Derived from the limits, never written as a number (INT-264).
BOUNDARY_OFFSET_S = float(OTP_WINDOW_S - (PHONE_LIMIT_PER_HOUR - 1) * (RESEND_COOLDOWN_S + 1) - 1)


def test_a_boundary_crossing_does_not_hand_the_budget_back(tmp_path: Path) -> None:
    """The INT-264 near-miss control, inverted. It admitted
    2 x PHONE_LIMIT_PER_HOUR codes to one phone in about six minutes because
    every counter reset on the hour; the same sequence must now stop at
    PHONE_LIMIT_PER_HOUR, and the refusal must land AFTER a fixed-window
    boundary has been crossed — otherwise the test would pass against the old
    limiter and prove nothing."""
    with _harness(tmp_path / "boundary", clock_offset_s=BOUNDARY_OFFSET_S) as harness:
        started = harness.clock()
        for _ in range(PHONE_LIMIT_PER_HOUR):
            assert harness.request_otp().status_code == 202
            harness.clock.advance(RESEND_COOLDOWN_S + 1)
        refused = harness.request_otp()
        assert refused.status_code == 429, "a boundary is not a fresh budget"
        assert refused.json()["error"] == "otp_limited"
        assert int(started // OTP_WINDOW_S) != int(harness.clock() // OTP_WINDOW_S), (
            "the sequence must actually cross a fixed-window boundary"
        )
        elapsed = harness.clock() - started
        assert elapsed < OTP_WINDOW_S, "and it must still be inside one rolling hour"


def test_the_retry_after_is_the_true_wait_not_the_time_to_the_next_boundary(
    tmp_path: Path,
) -> None:
    """A caller told to come back at :00 and then refused again is worse than
    the bug. The advertised retry-after is the instant the oldest request in the
    window falls out of it — asserted as a value, then walked: one second early
    still refuses, and exactly that wait is admitted."""
    with _harness(tmp_path / "retry-after", clock_offset_s=BOUNDARY_OFFSET_S) as harness:
        oldest = harness.clock()
        for _ in range(PHONE_LIMIT_PER_HOUR):
            assert harness.request_otp().status_code == 202
            harness.clock.advance(RESEND_COOLDOWN_S + 1)
        refused = harness.request_otp()
        assert refused.status_code == 429
        now = harness.clock()
        true_wait = oldest + OTP_WINDOW_S - now
        to_next_boundary = (int(now // OTP_WINDOW_S) + 1) * OTP_WINDOW_S - now
        assert true_wait != to_next_boundary, (
            "the two answers must differ here or this test cannot tell them apart"
        )
        assert refused.json()["retry_after_s"] == pytest.approx(true_wait, abs=0.5)
        assert int(refused.headers["Retry-After"]) == int(true_wait) + 1

        harness.clock.advance(true_wait - 1)
        assert harness.request_otp().status_code == 429, "one second early still refuses"
        harness.clock.advance(1)
        assert harness.request_otp().status_code == 202, "and the advertised wait is enough"


@pytest.mark.parametrize(
    ("dimension", "limit", "spacing"),
    [
        ("phone", PHONE_LIMIT_PER_HOUR, float(RESEND_COOLDOWN_S + 1)),
        ("ip", IP_LIMIT_PER_HOUR, 0.0),
        ("device", DEVICE_LIMIT_PER_HOUR, 0.0),
    ],
)
def test_every_dimension_holds_its_budget_across_a_boundary(
    dimension: str, limit: int, spacing: float, tmp_path: Path
) -> None:
    """files/10 §2 is per phone AND per IP; the device window mirrors the
    phone one. All three are counted by the same code, so all three are
    asserted across the boundary that used to reset them."""

    def spend(harness: OtpHarness, n: int) -> Any:
        if dimension == "phone":
            return harness.request_otp(PHONE, device_id=f"device-{n}")
        if dimension == "ip":
            return harness.request_otp(f"+90532111{4400 + n:04d}", device_id=f"device-{n}")
        return harness.request_otp(f"+90533222{1100 + n:04d}", device_id="one-device")

    offset = float(OTP_WINDOW_S - (limit - 1) * spacing - 1)
    crossing = spacing if spacing else 2.0
    with _harness(tmp_path / f"dim-{dimension}", clock_offset_s=offset) as harness:
        started = harness.clock()
        for n in range(limit):
            assert spend(harness, n).status_code == 202
            harness.clock.advance(spacing)
        harness.clock.advance(crossing)
        assert int(started // OTP_WINDOW_S) != int(harness.clock() // OTP_WINDOW_S)
        refused = spend(harness, limit)
        assert refused.status_code == 429, f"the {dimension} budget survived the boundary"
        assert refused.json()["error"] == "otp_limited"


def test_no_rolling_window_span_admits_more_than_the_phone_budget(otp: OtpHarness) -> None:
    """The acceptance clause is about ANY OTP_WINDOW_S span, not about the
    span this file happens to pick. One phone is polled every resend cooldown
    for two whole windows; every window that starts at an admission is then
    checked. A fixed window fails this at the first boundary it crosses."""
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
    """O(1) per request against a bounded key set: one key per (dimension,
    identifier) whatever the traffic, holding at most that dimension's limit —
    so the endpoint an attacker controls cannot be turned into unbounded
    memory. Asserted, not described."""
    step = float(RESEND_COOLDOWN_S + 1)
    for _ in range(int(2 * OTP_WINDOW_S / step)):
        otp.request_otp()
        otp.clock.advance(step)
    keys = sorted(k.decode() for k in otp.redis_client.keys("auth:otp:w:*"))
    assert len(keys) == 3, f"one key per dimension for one caller, got {keys}"
    dimensions = {
        "phone": PHONE_LIMIT_PER_HOUR,
        "ip": IP_LIMIT_PER_HOUR,
        "device": DEVICE_LIMIT_PER_HOUR,
    }
    for key in keys:
        dimension = key.split(":")[3]
        assert dimension in dimensions, key
        assert otp.redis_client.zcard(key) <= dimensions[dimension]
        assert 0 < otp.redis_client.ttl(key) <= OTP_WINDOW_S * 2


# --- limits (files/10 §2) ----------------------------------------------------------


def test_resend_cooldown_blocks_immediate_burst(otp: OtpHarness) -> None:
    assert otp.request_otp().status_code == 202
    burst = otp.request_otp()
    assert burst.status_code == 429
    body = burst.json()
    assert body["error"] == "otp_limited"
    assert 0 < body["retry_after_s"] <= RESEND_COOLDOWN_S
    otp.clock.advance(RESEND_COOLDOWN_S + 1)
    assert otp.request_otp().status_code == 202


def test_phone_formatting_does_not_fork_the_bucket(otp: OtpHarness) -> None:
    assert otp.request_otp(PHONE_FORMATTED).status_code == 202
    assert otp.request_otp(PHONE).status_code == 429


def test_per_phone_limit_three_per_hour(otp: OtpHarness) -> None:
    # LONGEST_WINDOW_SEQUENCE_S: the loop plus the refusal must land inside the
    # window the clock starts in, which is the whole reason that clock is not
    # seeded from time.time() (INT-264).
    for _ in range(PHONE_LIMIT_PER_HOUR):
        assert otp.request_otp().status_code == 202
        otp.clock.advance(RESEND_COOLDOWN_S + 1)
    refused = otp.request_otp()
    assert refused.status_code == 429
    assert refused.json()["error"] == "otp_limited"
    otp.clock.advance(OTP_WINDOW_S)  # deliberately the next window: budget back
    assert otp.request_otp().status_code == 202


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
    # a fresh code after the cooldown works
    otp.clock.advance(RESEND_COOLDOWN_S + 1)
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
