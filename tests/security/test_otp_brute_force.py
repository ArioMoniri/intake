"""INT-578 — OTP brute force and replay (owner order, 28 Oct 2026; GitHub #973).

Acceptance, verbatim: "6-digit codes with TTL ≤ 5 minutes; single use; at most
5 attempts then a lockout; constant-time compare; stored only as an HMAC with a
pepper read from OpenBao; bound to the requesting device's DPoP/App Attest key
and request id so a code is useless on another device."

The audit (docs/evidence/INT-577.md, rows 1-10) found the first two enforced
and pinned in test_otp_abuse.py, and these gaps, each pinned here with a near
miss:

- **The pepper.** INT-131 kept ``sha256(pseudonym:code)``: anyone with a Redis
  dump and a pseudonym recovered a code in 10⁶ hashes. The code is now kept
  only as an HMAC under a pepper that OpenBao holds (``secret/api/otp``), and no
  wiring outside dev reads it from anywhere else.
- **Single use under a race.** GET, compare and DEL were three commands, so two
  workers verifying the right code at once both signed in.
- **The attempt budget under a race.** The count was read-modify-write, so N
  wrong guesses that all read before any wrote were all compared.
- **The lockout.** A dead code could be replaced a minute later: 15 guesses a
  number an hour. The fifth miss now locks the number for a whole request
  window, which brings that to 5.
- **Constant time.** ``hmac.compare_digest`` was used and no test said so; a
  missing code returned before any comparison.
- **Device and request binding.** A code verified on any attested device, and
  no request id existed. A code is now bound to the attestation key that asked
  for it (App Attest's proven key id, never the install id a payload claims)
  and to the request id the 202 returned.

fakeredis and the injected clock keep everything deterministic (docs/TDD.md
rule 6). The races are not timed: :class:`InterleavingRedis` runs the competing
caller exactly between one caller's read and its write, which is the window a
second worker would have to hit.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import importlib
import json
import logging
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import fakeredis
import pytest
from prometheus_client import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import netgsm_testkit as kit  # noqa: E402
from intake_api import auth_store as auth_store_module  # noqa: E402
from intake_api.app import _auth_from_settings  # noqa: E402
from intake_api.auth_store import (  # noqa: E402
    OTP_MAX_ATTEMPTS,
    OTP_WINDOW_S,
    RESEND_COOLDOWN_S,
    AuthStore,
)
from intake_api.otp import AuthWiring  # noqa: E402
from intake_api.settings import ApiSettings  # noqa: E402
from test_otp_abuse import PHONE, Clock, DpopClient, OtpHarness, _build  # noqa: E402

OTHER_PHONE = "+905339998877"
PSEUDONYM = "v1." + "c" * 64
RIGHT = hashlib.sha256(b"int578-right-digest").hexdigest()
WRONG = hashlib.sha256(b"int578-wrong-digest").hexdigest()
DEVICE = hashlib.sha256(b"int578-device-a").hexdigest()


def pepper_module() -> ModuleType:
    """Resolved per call, so each test fails on its own line before the module
    exists instead of failing collection."""
    return importlib.import_module("intake_api.otp_pepper")


def pepper_hex(seed: str = "a") -> str:
    """A unit pepper, derived rather than written out (a 64-hex literal is the
    shape a secret scanner rightly flags)."""
    return hashlib.sha256(f"int578-unit-pepper-{seed}".encode()).hexdigest()


def pepper(seed: str = "a") -> Any:
    return pepper_module().OtpPepper.parse({"pepper": pepper_hex(seed)})


def verify_count(outcome: str) -> float:
    return REGISTRY.get_sample_value("otp_verify_total", {"outcome": outcome}) or 0.0


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


def wrong_code(real: str) -> str:
    return "000000" if real != "000000" else "111111"


class InterleavingRedis:
    """fakeredis, plus a queue of callers that run between one caller's READ of
    a code record and whatever it does next.

    Each queued caller runs from inside the previous one's read, so N queued
    guesses all read the record before any of them writes: the schedule two or
    more API workers would produce, made exact instead of hoped for.
    """

    def __init__(self, inner: fakeredis.FakeStrictRedis) -> None:
        self._inner = inner
        self.pending: list[Callable[[], object]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def get(self, name: Any) -> Any:
        value = self._inner.get(name)
        key = name.decode() if isinstance(name, bytes) else str(name)
        if self.pending and ":otp:code:" in key:
            self.pending.pop(0)()
        return value


# --- the pepper (stored only as an HMAC under a pepper from OpenBao) ------------------


def test_the_code_is_kept_only_as_an_hmac_under_the_pepper(tmp_path: Path) -> None:
    keyed = pepper("a")
    with harness(tmp_path, pepper=keyed) as otp:
        assert otp.request_otp().status_code == 202
        code = otp.peek()
        request_id = otp.request_ids[PHONE]
        [key] = list(otp.redis_client.scan_iter("auth:otp:code:*"))
        pseudonym = key.decode().split(":", 3)[3]
        record = json.loads(otp.redis_client.get(key))
        assert record["digest"] == keyed.code_digest(pseudonym, request_id, code)
        # near misses: INT-131's unkeyed form, and the same code under another pepper
        assert record["digest"] != hashlib.sha256(f"{pseudonym}:{code}".encode()).hexdigest()
        assert record["digest"] != pepper("b").code_digest(pseudonym, request_id, code)
        # nothing in Redis but the dev peek slot carries the code, or the
        # digest anyone could recompute without the pepper
        unkeyed = hashlib.sha256(f"{pseudonym}:{code}".encode()).hexdigest()
        for name in otp.redis_client.scan_iter("*"):
            if b":otp:peek:" in name or otp.redis_client.type(name) != b"string":
                continue
            value = otp.redis_client.get(name).decode()
            # the code as a stored value, or as a string inside a JSON record
            # (a bare substring test would trip on a timestamp's digits)
            assert value != code, name
            assert json.dumps(code) not in value, name
            assert unkeyed not in value, name


def test_the_pepper_parses_from_its_openbao_document() -> None:
    first, again = pepper("a"), pepper("a")
    digest = first.code_digest(PSEUDONYM, "f" * 32, "123456")
    assert digest == again.code_digest(PSEUDONYM, "f" * 32, "123456")
    assert len(digest) == 64 and int(digest, 16) >= 0
    # every input moves the digest (near misses one field at a time)
    assert digest != first.code_digest(PSEUDONYM, "f" * 32, "123457")
    assert digest != first.code_digest(PSEUDONYM, "e" * 32, "123456")
    assert digest != first.code_digest("v1." + "d" * 64, "f" * 32, "123456")
    # the two derivations are domain-separated
    assert first.device_binding("123456") != first.code_digest("", "", "123456")


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"pepper": ""},
        {"pepper": None},
        {"pepper": 1234567890},
        {"pepper": hashlib.sha256(b"x").hexdigest()[:62]},  # 31 bytes: one short
        {"pepper": hashlib.sha256(b"x").hexdigest()[:63]},  # odd length
        {"pepper": "zz" * 32},
        {"pepper": hashlib.sha256(b"x").hexdigest().upper()},
    ],
    ids=["absent", "empty", "null", "number", "short", "odd", "not-hex", "upper-case"],
)
def test_a_missing_short_or_malformed_pepper_is_refused_by_name(
    document: dict[str, object],
) -> None:
    module = pepper_module()
    with pytest.raises(module.OtpPepperError) as refused:
        module.OtpPepper.parse(document)
    message = str(refused.value)
    assert "pepper" in message
    value = document.get("pepper")
    if isinstance(value, str) and value:
        assert value not in message, "the refusal echoed the value"


def test_the_shortest_accepted_pepper_is_thirty_two_bytes() -> None:
    """Near miss for the 'short' case above: 64 hex characters parse."""
    assert pepper_module().OtpPepper.parse({"pepper": pepper_hex()}) is not None


def test_the_pepper_never_reaches_repr_or_str() -> None:
    keyed = pepper("a")
    for shown in (repr(keyed), str(keyed)):
        assert pepper_hex("a") not in shown
        assert pepper_hex("a")[:16] not in shown


def test_two_process_local_peppers_differ() -> None:
    """The dev file-dev path's pepper is random per process — never a literal."""
    module = pepper_module()
    one, two = module.OtpPepper.ephemeral(), module.OtpPepper.ephemeral()
    assert one.code_digest(PSEUDONYM, "f" * 32, "123456") != two.code_digest(
        PSEUDONYM, "f" * 32, "123456"
    )


# --- where the pepper comes from (OpenBao only; invariant 14) ------------------------


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def _settings(environment: str, *, kek_mode: str = "transit") -> ApiSettings:
    return ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
        audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
        kek_mode=kek_mode,  # type: ignore[arg-type]
        tokenization_key="k",
        environment=environment,
    )


@pytest.mark.parametrize("environment", kit.STRICT_ENVIRONMENTS)
def test_every_strict_environment_reads_the_pepper_from_openbao(
    phi_egress: None, environment: str
) -> None:
    vault = kit.complete_vault()
    wiring = _auth_from_settings(_settings(environment), secrets=vault)
    assert isinstance(wiring, AuthWiring)
    assert vault.paths == ["api/netgsm", pepper_module().OTP_PEPPER_KV_PATH]
    held = pepper_module().OtpPepper.parse(kit.PEPPER_DOC)
    assert wiring.pepper.code_digest(PSEUDONYM, "f" * 32, "1") == held.code_digest(
        PSEUDONYM, "f" * 32, "1"
    )


@pytest.mark.parametrize("environment", kit.STRICT_ENVIRONMENTS)
def test_no_pepper_document_leaves_the_tier_at_503(
    phi_egress: None, environment: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    vault = kit.Vault({"api/netgsm": kit.VAULT_DOC}, pepper=False)
    assert _auth_from_settings(_settings(environment), secrets=vault) is None
    assert any("secret/api/otp" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("environment", kit.STRICT_ENVIRONMENTS)
def test_a_malformed_pepper_leaves_the_tier_at_503_and_is_not_echoed(
    phi_egress: None, environment: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    short = pepper_hex()[:40]
    vault = kit.Vault({"api/netgsm": kit.VAULT_DOC, "api/otp": {"pepper": short}})
    assert _auth_from_settings(_settings(environment), secrets=vault) is None
    assert any("pepper" in record.getMessage() for record in caplog.records)
    assert short not in caplog.text


@pytest.mark.parametrize("environment", kit.STRICT_ENVIRONMENTS)
def test_the_environment_is_not_a_pepper_source(
    phi_egress: None, environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("INTAKE_OTP_PEPPER", "OTP_PEPPER", "INTAKE_API_OTP_PEPPER"):
        monkeypatch.setenv(name, pepper_hex())
    vault = kit.Vault({"api/netgsm": kit.VAULT_DOC}, pepper=False)
    assert _auth_from_settings(_settings(environment), secrets=vault) is None


def test_file_dev_takes_a_process_local_pepper_and_reads_no_vault() -> None:
    vault = kit.Vault()
    first = _auth_from_settings(_settings("dev", kek_mode="file-dev"), secrets=vault)
    second = _auth_from_settings(_settings("dev", kek_mode="file-dev"), secrets=vault)
    assert isinstance(first, AuthWiring) and isinstance(second, AuthWiring)
    assert vault.paths == []
    assert first.pepper.code_digest(PSEUDONYM, "f" * 32, "1") != second.pepper.code_digest(
        PSEUDONYM, "f" * 32, "1"
    )


def test_dev_on_the_openbao_dev_server_reads_the_pepper_there() -> None:
    """Near miss for the file-dev case: dev with transit KEKs has OpenBao, and
    then the pepper comes from it like everywhere else."""
    vault = kit.complete_vault()
    wiring = _auth_from_settings(_settings("dev"), secrets=vault)
    assert isinstance(wiring, AuthWiring)
    assert vault.paths == [pepper_module().OTP_PEPPER_KV_PATH]


@pytest.mark.parametrize("environment", kit.STRICT_ENVIRONMENTS)
def test_file_dev_outside_dev_still_reads_openbao(phi_egress: None, environment: str) -> None:
    """A directly built settings object outside dev never gets the process-local
    pepper, whatever its KEK mode says (from_env refuses that mode anyway)."""
    vault = kit.Vault({"api/netgsm": kit.VAULT_DOC}, pepper=False)
    assert _auth_from_settings(_settings(environment, kek_mode="file-dev"), secrets=vault) is None
    assert pepper_module().OTP_PEPPER_KV_PATH in vault.paths


# --- single use --------------------------------------------------------------------------


def test_a_spent_code_is_refused_on_replay(otp: OtpHarness) -> None:
    dpop = DpopClient()
    assert otp.request_otp().status_code == 202
    code = otp.peek()
    assert otp.verify(dpop, code=code).status_code == 200
    replay = otp.verify(dpop, code=code)
    assert replay.status_code == 401
    assert replay.json() == {"error": "otp_invalid"}


def test_two_racing_verifies_of_the_right_code_admit_exactly_one() -> None:
    clock = Clock()
    inner = fakeredis.FakeStrictRedis()
    racing = InterleavingRedis(inner)
    store = AuthStore(racing, clock)  # type: ignore[arg-type]
    store.store_code(PSEUDONYM, RIGHT, binding=DEVICE)
    verdicts: list[str] = []
    racing.pending.append(
        lambda: verdicts.append(
            AuthStore(inner, clock).check_code(PSEUDONYM, RIGHT, binding=DEVICE)
        )
    )
    verdicts.append(store.check_code(PSEUDONYM, RIGHT, binding=DEVICE))
    assert sorted(verdicts) == ["missing", "ok"]


def test_one_verify_of_the_right_code_is_admitted() -> None:
    """Near miss for the race: with nobody racing, the right code signs in."""
    store = AuthStore(fakeredis.FakeStrictRedis(), Clock())
    store.store_code(PSEUDONYM, RIGHT, binding=DEVICE)
    assert store.check_code(PSEUDONYM, RIGHT, binding=DEVICE) == "ok"


# --- at most five attempts, then a lockout -------------------------------------------------


def test_racing_wrong_guesses_cannot_buy_more_than_five_comparisons() -> None:
    clock = Clock()
    inner = fakeredis.FakeStrictRedis()
    racing = InterleavingRedis(inner)
    store = AuthStore(racing, clock)  # type: ignore[arg-type]
    store.store_code(PSEUDONYM, RIGHT, binding=DEVICE)
    verdicts: list[str] = []

    def guess() -> None:
        verdicts.append(store.check_code(PSEUDONYM, WRONG, binding=DEVICE))

    racing.pending.extend([guess] * 19)
    guess()  # the first read starts the chain: all twenty read before any writes
    assert len(verdicts) == 20
    assert verdicts.count("invalid") == OTP_MAX_ATTEMPTS - 1
    assert verdicts.count("exhausted") == 20 - (OTP_MAX_ATTEMPTS - 1)
    # and twenty misses spent the budget: the right code is refused now
    assert AuthStore(inner, clock).check_code(PSEUDONYM, RIGHT, binding=DEVICE) == "exhausted"


def test_four_misses_then_the_right_code_still_signs_in(otp: OtpHarness) -> None:
    """Near miss for the lockout: the fifth attempt may be the right one."""
    dpop = DpopClient()
    assert otp.request_otp().status_code == 202
    real = otp.peek()
    for _ in range(OTP_MAX_ATTEMPTS - 1):
        assert otp.verify(dpop, code=wrong_code(real)).status_code == 401
    assert otp.verify(dpop, code=real).status_code == 200


def test_the_fifth_miss_locks_the_number_for_the_lockout(otp: OtpHarness) -> None:
    lockout_s: float = auth_store_module.OTP_LOCKOUT_S  # type: ignore[attr-defined]
    dpop = DpopClient()
    assert otp.request_otp().status_code == 202
    real = otp.peek()
    for _ in range(OTP_MAX_ATTEMPTS):
        assert otp.verify(dpop, code=wrong_code(real)).status_code == 401
    locked_before = verify_count("locked")
    # locked: the right code is refused, with the same answer as a wrong one
    refused_verify = otp.verify(dpop, code=real)
    assert refused_verify.status_code == 401
    assert refused_verify.json() == {"error": "otp_invalid"}
    assert verify_count("locked") == locked_before + 1
    # and no new code is minted for the number — withheld, so the answer is an
    # admission's and a stranger cannot read the lockout off it (INT-579)
    assert not otp.sent()
    otp.clock.advance(lockout_s - 1)
    assert not otp.sent(), "one second short of the lockout"
    otp.clock.advance(2)
    assert otp.sent()
    assert otp.verify(dpop).status_code == 200


def test_the_lockout_is_per_number(otp: OtpHarness) -> None:
    dpop = DpopClient()
    assert otp.request_otp().status_code == 202
    real = otp.peek()
    for _ in range(OTP_MAX_ATTEMPTS):
        otp.verify(dpop, code=wrong_code(real))
    assert otp.request_otp(OTHER_PHONE).status_code == 202
    assert otp.verify(dpop, phone=OTHER_PHONE).status_code == 200


def test_the_lockout_outlasts_the_request_window() -> None:
    """Why the lockout is a whole window: anything shorter lets three codes an
    hour through the per-number budget, and 3 x 5 guesses is what INT-131
    already allowed. The behaviour is the next test."""
    assert auth_store_module.OTP_LOCKOUT_S >= OTP_WINDOW_S  # type: ignore[attr-defined]


def test_a_number_takes_at_most_five_guesses_in_any_hour(otp: OtpHarness) -> None:
    """An attacker who asks for a code, spends five guesses and asks again as
    soon as anything lets them, for two hours: no rolling hour holds more than
    five guesses that reached a comparison."""
    dpop = DpopClient()
    compared: list[float] = []
    start = otp.clock()
    while otp.clock() - start < 2 * OTP_WINDOW_S:
        if otp.request_otp(device_id=f"device-{int(otp.clock())}").status_code == 202:
            real = otp.peek()
            for _ in range(OTP_MAX_ATTEMPTS):
                locked = verify_count("locked")
                otp.verify(dpop, code=wrong_code(real))
                if verify_count("locked") == locked:
                    compared.append(otp.clock())
        otp.clock.advance(RESEND_COOLDOWN_S + 1)
    assert compared, "the attacker never got a code: the test proves nothing"
    for t in compared:
        window = [g for g in compared if t <= g < t + OTP_WINDOW_S]
        assert len(window) <= OTP_MAX_ATTEMPTS, (t, len(window))


# --- constant-time comparison -------------------------------------------------------------


def test_every_comparison_is_constant_time(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, object]] = []
    real_compare = hmac.compare_digest

    def spy(a: Any, b: Any) -> bool:
        seen.append((a, b))
        return real_compare(a, b)

    monkeypatch.setattr(auth_store_module.hmac, "compare_digest", spy)
    store = AuthStore(fakeredis.FakeStrictRedis(), Clock())
    store.store_code(PSEUDONYM, RIGHT, binding=DEVICE)
    assert store.check_code(PSEUDONYM, WRONG, binding=DEVICE) == "invalid"
    assert (RIGHT, WRONG) in seen, "the code digest was not compared in constant time"
    assert (DEVICE, DEVICE) in seen, "the device binding was not compared in constant time"
    # a missing code is compared against a stand-in, never skipped
    seen.clear()
    assert store.check_code("v1." + "e" * 64, WRONG, binding=DEVICE) == "missing"
    assert len(seen) >= 2


# --- bound to the requesting device's key and to the request id ----------------------------


def test_a_code_is_useless_on_another_device(otp: OtpHarness) -> None:
    dpop = DpopClient()
    assert otp.request_otp(device_id="device-a").status_code == 202
    unbound = verify_count("unbound")
    stolen = otp.verify(dpop, device_id="device-b")
    assert stolen.status_code == 401
    assert stolen.json() == {"error": "otp_invalid"}
    assert verify_count("unbound") == unbound + 1
    # near miss: the device that asked, with the same code and request id
    assert otp.verify(dpop, device_id="device-a").status_code == 200


def test_a_code_is_bound_to_the_request_it_answered(otp: OtpHarness) -> None:
    dpop = DpopClient()
    assert otp.request_otp().status_code == 202
    first_id = otp.request_ids[PHONE]
    otp.clock.advance(RESEND_COOLDOWN_S + 1)
    assert otp.request_otp().status_code == 202
    second_id = otp.request_ids[PHONE]
    assert first_id != second_id
    # the live code under an earlier request's id, and under an invented one
    assert otp.verify(dpop, request_id=first_id).status_code == 401
    assert otp.verify(dpop, request_id="0" * 32).status_code == 401
    # near miss: the id the live code was minted under
    assert otp.verify(dpop, request_id=second_id).status_code == 200


def test_the_request_id_is_server_minted_and_carries_nothing(otp: OtpHarness) -> None:
    ids = set()
    for n in range(3):
        response = otp.request_otp(f"+90532111{4400 + n:04d}", device_id=f"device-{n}")
        assert response.status_code == 202
        request_id = response.json()["request_id"]
        assert len(request_id) == 32 and int(request_id, 16) >= 0
        assert request_id == request_id.lower()
        ids.add(request_id)
    assert len(ids) == 3


def test_a_verify_without_its_request_id_is_refused_by_shape(otp: OtpHarness) -> None:
    dpop = DpopClient()
    assert otp.request_otp().status_code == 202
    headers = otp.attestation()
    headers["DPoP"] = dpop.proof("POST", f"{otp.base}/v1/auth/otp/verify", iat=otp.clock())
    response = otp.client.post(
        "/v1/auth/otp/verify", json={"phone": PHONE, "code": otp.peek()}, headers=headers
    )
    assert response.status_code == 422


def test_verify_outcomes_are_a_closed_vocabulary() -> None:
    otp_module = importlib.import_module("intake_api.otp")
    assert otp_module.VERIFY_OUTCOMES == frozenset(
        {"ok", "invalid", "unbound", "exhausted", "missing", "locked"}
    )
