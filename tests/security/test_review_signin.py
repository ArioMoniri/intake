"""INT-488 — the App Store review sign-in (owner decision D39, 30 Oct 2026; GitHub #829).

A release build signs in only by an SMS code, which an App Review reviewer
cannot receive. D39 approves one reviewer account, and every clause is pinned
here with a near miss:

1. **a reserved reviewer number that never sends an SMS** — no vendor call on
   any path, whatever the window, the gate or the code says;
2. **one fixed code, generated on the host and stored only in OpenBao**,
   compared as an HMAC under the OTP pepper. No code is written in this file:
   every test draws its own from the CSPRNG;
3. **only the synthetic host's synthetic tenant** — the environment, the
   baked data class, the tenant's real-patient flag (INT-465's tenant kind) and
   the named deployment must all say synthetic, and a deployment failing any
   one refuses the reviewer with no vendor call;
4. **every use on the hash chain, and an alert**, rate-limited under the
   INT-578 lockout;
5. **a review-window switch, default OFF**, every flip audited;
6. **the sign-in lands a synthetic reviewer patient**, never real data.

fakeredis, SQLite and an injected clock, as in test_otp_abuse.py; nothing
here reaches OpenBao, Netgsm or a host.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import logging
import re
import secrets
import sys
import traceback
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import fakeredis
import pytest
import redis
import yaml
from intake_platform.audit import AuditChain, InMemoryAuditStore, verify_entries
from intake_platform.model_lanes.model import TenantDataClass
from intake_platform.otel import JsonLogFormatter
from intake_platform.red_tenant import TenantKind
from intake_platform.tokenization import Tokenizer
from intake_platform.voice_control.model import TenantVoiceControl
from intake_platform.voice_control.store import VoiceControlUnavailable
from prometheus_client import REGISTRY, generate_latest
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import netgsm_testkit as kit  # noqa: E402
from intake_api.app import _auth_from_settings  # noqa: E402
from intake_api.auth_store import OTP_MAX_ATTEMPTS, RESEND_COOLDOWN_S  # noqa: E402
from intake_api.otp import CONSUMER_TENANT_ID, AuthWiring  # noqa: E402
from intake_api.otp_pepper import OtpPepper  # noqa: E402
from intake_api.settings import ApiSettings  # noqa: E402
from test_otp_abuse import DpopClient, OtpHarness, _build  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RULES = REPO / "infra" / "observability" / "security-rules.yaml"
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
RUNBOOK = REPO / "docs" / "runbooks" / "review-signin.md"
#: the harness's tokenizer (test_otp_abuse._build), rebuilt so the reviewer's
#: pseudonym matches the one the service derives
TOKENIZER = Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1")
DEVICE = "review-device-a"


def review() -> ModuleType:
    """Resolved per call, so each test fails on its own line before the module
    exists instead of failing collection."""
    return importlib.import_module("intake_api.review_signin")


def window_module() -> ModuleType:
    return importlib.import_module("intake_api.review_window")


def cli_module() -> ModuleType:
    return importlib.import_module("intake_api.review_cli")


class Voice:
    """The INT-182 voice-control store as the model-lane router reads it: the
    reviewer tenant's kill switch, engaged unless a test says otherwise."""

    def __init__(self, *, engaged: bool = True, unreadable: bool = False) -> None:
        self.engaged = engaged
        self.unreadable = unreadable

    def read(self, tenant_id: str) -> TenantVoiceControl:
        if self.unreadable:
            raise VoiceControlUnavailable("voice_control_unreachable")
        return TenantVoiceControl(tenant_id=tenant_id, kill_switch=self.engaged)


def guards(**knobs: Any) -> Any:
    """The live guards of the synthetic host with hosted lanes switched off for
    the reviewer tenant; a test overrides one at a time."""
    knobs.setdefault("voice", Voice())
    return window_module().ReviewGuards(**knobs)


def keyed(seed: str = "a") -> OtpPepper:
    """A unit pepper, derived rather than written out."""
    return OtpPepper.parse({"pepper": hashlib.sha256(f"int488-pepper-{seed}".encode()).hexdigest()})


@dataclass(frozen=True)
class Reviewer:
    """The reviewer account a test runs against: both values drawn from the
    CSPRNG for this test, as --generate draws them on the host."""

    number: str
    code: str

    @property
    def wrong(self) -> str:
        return f"{(int(self.code) + 1) % 10**6:06d}"

    @property
    def forms(self) -> tuple[str, ...]:
        national = self.number[3:]
        return (
            self.number,
            self.number[1:],
            "0" + national,
            national,
            f"+90 {national[:3]} {national[3:6]} {national[6:8]} {national[8:]}",
        )


def draw() -> Reviewer:
    return Reviewer(
        number="+905" + "".join(str(secrets.randbelow(10)) for _ in range(9)),
        code=f"{secrets.randbelow(10**6):06d}",
    )


def strict(**overrides: Any) -> ApiSettings:
    """The synthetic host's settings (infra/staging/compose.yaml and the image),
    with one fact overridden per near miss."""
    values: dict[str, Any] = {
        "token_patient": None,
        "token_admin": None,
        "app_db_url": "postgresql+psycopg://app_rw@db.internal:5432/intake",
        "audit_db_url": "postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        "bootstrap_db_url": "postgresql+psycopg://intake_owner@db.internal:5432/intake",
        "kek_mode": "transit",
        "tokenization_key": "k",
        "environment": "staging",
        "deployment_data_class": TenantDataClass.SYNTHETIC,
        "triage_tenant_kind": TenantKind.SYNTHETIC,
        "triage_deployment": "i-synthetic-host",
        "sms_egress_proxy_url": "http://sms-egress:3128",
        "egress_allowlist_path": kit.SHIPPED_ALLOWLIST,
    }
    values.update(overrides)
    return ApiSettings(**values)


#: Every way a deployment can fail to be the synthetic host's synthetic tenant,
#: one fact at a time; the fact the wiring names for each.
NOT_SYNTHETIC: dict[str, tuple[dict[str, Any], str]] = {
    "production": ({"environment": "prod", "sms_egress_proxy_url": None}, "environment"),
    "dev": ({"environment": "dev", "sms_egress_proxy_url": None}, "environment"),
    "another-staging-name": (
        {"environment": "staging-2", "sms_egress_proxy_url": None},
        "environment",
    ),
    "real-phi-image": ({"deployment_data_class": TenantDataClass.REAL_PHI}, "data_class"),
    "real-patient-flag": ({"triage_tenant_kind": TenantKind.REAL}, "tenant_kind"),
    "no-deployment-named": ({"triage_deployment": None}, "deployment"),
}


def built(
    reviewer: Reviewer,
    pepper: OtpPepper,
    settings: ApiSettings | None = None,
    live: Any = None,
) -> Any:
    """The ReviewSignIn the wiring builds from an OpenBao document."""
    vault = kit.Vault({"api/review_signin": {"number": reviewer.number, "code": reviewer.code}})
    return review().review_signin_from_vault(
        vault,
        settings=settings or strict(),
        tokenizer=TOKENIZER,
        pepper=pepper,
        guards=live if live is not None else guards(),
    )


@contextlib.contextmanager
def harness(
    tmp_path: Path,
    reviewer: Reviewer,
    *,
    settings: ApiSettings | None = None,
    signin: Any = None,
    window: bool = True,
) -> Iterator[OtpHarness]:
    pepper = keyed()
    held = signin if signin is not None else built(reviewer, pepper, settings)
    tmp_path.mkdir(parents=True, exist_ok=True)
    harnesses = _build(tmp_path, pepper=pepper, review=held)
    otp = next(harnesses)
    try:
        if window:
            review().ReviewWindow(otp.redis_client).open()
        yield otp
    finally:
        next(harnesses, None)


def ask(otp: OtpHarness, reviewer: Reviewer, device: str = DEVICE) -> Any:
    return otp.request_otp(reviewer.number, device_id=device)


def answer(
    otp: OtpHarness,
    dpop: DpopClient,
    reviewer: Reviewer,
    asked: Any,
    code: str | None = None,
    device: str = DEVICE,
) -> Any:
    request_id = asked.json()["request_id"] if asked.status_code == 202 else "f" * 32
    return otp.verify(
        dpop,
        phone=reviewer.number,
        code=code if code is not None else reviewer.code,
        device_id=device,
        request_id=request_id,
    )


def counted(step: str, outcome: str) -> float:
    labels = {"step": step, "outcome": outcome}
    return REGISTRY.get_sample_value("sec_review_signin_total", labels) or 0.0


def rows(otp: OtpHarness, sql: str) -> list[tuple[Any, ...]]:
    url = str(otp.engine.url).replace("+aiosqlite", "+pysqlite")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(sql))]
    finally:
        engine.dispose()


def actions(otp: OtpHarness) -> list[str]:
    return [entry.action for entry in otp.audit_store.entries()]


# --- 1. the reserved number never sends an SMS ------------------------------------------------


def test_the_reviewer_signs_in_and_no_sms_is_ever_sent(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        asked = ask(otp, reviewer)
        assert asked.status_code == 202, asked.text
        assert set(asked.json()) == {"request_id", "resend_after_s"}
        signed = answer(otp, DpopClient(), reviewer, asked)
        assert signed.status_code == 200, signed.text
        # a resend after the cooldown, and a second sign-in: still nothing sent
        otp.clock.advance(RESEND_COOLDOWN_S * 4)
        again = ask(otp, reviewer)
        assert answer(otp, DpopClient(), reviewer, again).status_code == 200
        assert otp.sends == 0, "the reviewer number reached the SMS vendor"
        # nothing in Redis is a dev peek copy of the code
        assert list(otp.redis_client.scan_iter("auth:otp:peek:*")) == []


def test_near_miss_an_ordinary_number_on_the_same_wiring_is_still_sent(tmp_path: Path) -> None:
    """The reviewer branch is the reviewer number's alone."""
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        assert otp.sent("+905321114455")
        assert otp.sends == 1


# --- 2. one fixed code, held only as an HMAC under the pepper ------------------------------


def test_the_api_holds_the_code_only_as_an_hmac_under_the_pepper() -> None:
    reviewer = draw()
    signin = built(reviewer, keyed("a"))
    assert signin.code_key == keyed("a").review_code(reviewer.code)
    # near misses: another pepper, another code, and the code in clear
    assert signin.code_key != keyed("b").review_code(reviewer.code)
    assert signin.code_key != keyed("a").review_code(reviewer.wrong)
    held = repr(signin) + str(signin) + json.dumps(vars(signin), default=str)
    for secret in (reviewer.code, *reviewer.forms):
        assert secret not in held, "the reviewer document reached the held object"
    # the review domain is separate from a code digest and a device binding
    assert keyed("a").review_code(reviewer.code) != keyed("a").device_binding(reviewer.code)


def test_the_reviewer_code_is_compared_through_the_int578_code_record(tmp_path: Path) -> None:
    """The request mints an ordinary INT-578 record: bound to the device and the
    request id, single use, under the number's attempt budget."""
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        asked = ask(otp, reviewer)
        [key] = list(otp.redis_client.scan_iter("auth:otp:code:*"))
        record = json.loads(otp.redis_client.get(key))
        assert set(record) == {"digest", "binding", "expires"}
        assert reviewer.code not in json.dumps(record)
        # single use: the same code and request id a second time is refused
        dpop = DpopClient()
        assert answer(otp, dpop, reviewer, asked).status_code == 200
        assert answer(otp, DpopClient(), reviewer, asked).status_code == 401
        # bound to the device that asked
        otp.clock.advance(RESEND_COOLDOWN_S * 4)
        other = ask(otp, reviewer, device="review-device-a")
        stolen = answer(otp, DpopClient(), reviewer, other, device="review-device-b")
        assert stolen.status_code == 401


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"code": ""},
        {"code": "12345"},
        {"code": "1234567"},
        {"code": "12a456"},
        {"code": 123456},
    ],
    ids=["absent", "empty", "five-digits", "seven-digits", "not-digits", "not-a-string"],
)
def test_a_code_absent_from_openbao_answers_a_typed_503_and_sends_nothing(
    tmp_path: Path, document: dict[str, object]
) -> None:
    reviewer = draw()
    pepper = keyed()
    vault = kit.Vault({"api/review_signin": {**document, "number": reviewer.number}})
    signin = review().review_signin_from_vault(
        vault, settings=strict(), tokenizer=TOKENIZER, pepper=pepper, guards=guards()
    )
    assert signin is not None and signin.code_key is None
    with harness(tmp_path, reviewer, signin=signin) as otp:
        before = counted("request", "unconfigured")
        asked = ask(otp, reviewer)
        assert asked.status_code == 503
        assert asked.json() == {"error": "review_signin_unconfigured"}
        refused = answer(otp, DpopClient(), reviewer, asked)
        assert refused.status_code == 503
        assert refused.json() == {"error": "review_signin_unconfigured"}
        assert otp.sends == 0
        assert counted("request", "unconfigured") == before + 1
        assert "auth.review.refused" in actions(otp)


def test_near_miss_the_same_document_with_its_code_signs_in(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        assert answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).status_code == 200


@pytest.mark.parametrize(
    "number",
    ["", "05321112233", "+90532111223", "+9053211122334", "+905321112233 ", "+4915112345678"],
    ids=["empty", "national", "short", "long", "trailing-space", "not-turkish"],
)
def test_a_malformed_number_wires_no_reviewer_and_names_no_value(
    number: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    code = draw().code
    vault = kit.Vault({"api/review_signin": {"number": number, "code": code}})
    signin = review().review_signin_from_vault(
        vault, settings=strict(), tokenizer=TOKENIZER, pepper=keyed()
    )
    assert signin is None
    assert any("number" in record.getMessage() for record in caplog.records)
    assert code not in caplog.text
    if number.strip():
        assert number.strip() not in caplog.text


def test_no_document_wires_no_reviewer(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    signin = review().review_signin_from_vault(
        kit.Vault(), settings=strict(), tokenizer=TOKENIZER, pepper=keyed()
    )
    assert signin is None
    assert any("secret/api/review_signin" in record.getMessage() for record in caplog.records)


# --- 3. the synthetic host's synthetic tenant, and nowhere else ----------------------------


@pytest.mark.parametrize("case", sorted(NOT_SYNTHETIC))
def test_a_non_synthetic_tenant_refuses_the_reviewer_with_no_vendor_call(
    tmp_path: Path, case: str
) -> None:
    overrides, fact = NOT_SYNTHETIC[case]
    reviewer = draw()
    settings = strict(**overrides)
    signin = built(reviewer, keyed(), settings)
    assert signin is not None, "the number stays reserved where the gate refuses"
    assert signin.refused_by == (fact,)
    with harness(tmp_path, reviewer, signin=signin) as otp:
        before = counted("request", "not_synthetic")
        asked = ask(otp, reviewer)
        # withheld: the answer an admission gets, with nothing minted or sent
        assert asked.status_code == 202
        assert list(otp.redis_client.scan_iter("auth:otp:code:*")) == []
        refused = answer(otp, DpopClient(), reviewer, asked)
        assert refused.status_code == 401
        assert refused.json() == {"error": "otp_invalid"}
        assert otp.sends == 0, "the reviewer number reached the SMS vendor"
        assert counted("request", "not_synthetic") == before + 1
        tenant = review().REVIEW_TENANT_ID.hex
        assert rows(otp, f"SELECT id FROM patients WHERE tenant_id = '{tenant}'") == []  # noqa: S608
        assert "auth.review.signed_in" not in actions(otp)


def test_near_miss_every_fact_synthetic_admits_the_reviewer() -> None:
    signin = built(draw(), keyed(), strict())
    assert signin is not None and signin.refused_by == () and signin.admitted


#: Dev reads no review document at all (test_dev_never_reads_it), so the
#: wiring cases are every other one.
WIRED_CASES = sorted(case for case in NOT_SYNTHETIC if case != "dev")


@pytest.mark.parametrize("case", WIRED_CASES)
def test_the_wiring_names_the_failed_fact_and_no_value(
    case: str, phi_egress: None, caplog: pytest.LogCaptureFixture
) -> None:
    overrides, fact = NOT_SYNTHETIC[case]
    reviewer = draw()
    caplog.set_level(logging.DEBUG)
    vault = kit.complete_vault()
    vault.documents["api/review_signin"] = {"number": reviewer.number, "code": reviewer.code}
    wiring = _auth_from_settings(strict(**overrides), secrets=vault)
    assert isinstance(wiring, AuthWiring)
    assert wiring.review is not None and wiring.review.refused_by == (fact,)
    assert any(fact in record.getMessage() for record in caplog.records)
    for secret in (reviewer.code, *reviewer.forms):
        assert secret not in caplog.text


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def test_the_wiring_reads_the_review_document_after_the_pepper(phi_egress: None) -> None:
    reviewer = draw()
    vault = kit.complete_vault()
    vault.documents["api/review_signin"] = {"number": reviewer.number, "code": reviewer.code}
    wiring = _auth_from_settings(strict(), secrets=vault)
    assert isinstance(wiring, AuthWiring)
    assert vault.paths == ["api/netgsm", "api/otp", "api/review_signin"]
    assert wiring.review is not None and wiring.review.admitted
    assert wiring.review.code_key == wiring.pepper.review_code(reviewer.code)


def test_dev_never_reads_it(phi_egress: None, tmp_path: Path) -> None:
    vault = kit.complete_vault()
    settings = strict(
        environment="dev",
        sms_egress_proxy_url=None,
        egress_allowlist_path=kit.allowlist_with_the_row(tmp_path),
    )
    wiring = _auth_from_settings(settings, secrets=vault)
    assert isinstance(wiring, AuthWiring)
    assert "api/review_signin" not in vault.paths
    assert wiring.review is None


# --- 4. audited, alerted, rate-limited under the INT-578 lockout ---------------------------


def test_every_use_is_on_the_hash_chain(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        asked = ask(otp, reviewer)
        answer(otp, DpopClient(), reviewer, asked, code=reviewer.wrong)
        answer(otp, DpopClient(), reviewer, asked)
        review().ReviewWindow(otp.redis_client).close()
        otp.clock.advance(RESEND_COOLDOWN_S * 4)
        closed = ask(otp, reviewer)
        answer(otp, DpopClient(), reviewer, closed)
        entries = list(otp.audit_store.entries())
        assert verify_entries(entries).ok
        seen = [entry.action for entry in entries if entry.action.startswith("auth.review.")]
        assert seen == [
            "auth.review.requested",
            "auth.review.verify_refused",
            "auth.review.signed_in",
            "auth.review.refused",
            "auth.review.verify_refused",
        ]
        refs = [entry.resource_ref for entry in entries if entry.action.startswith("auth.review.")]
        assert refs[3] == "review:window_closed"
        assert refs[4] == "otp_verify:window_closed"


def test_a_wrong_code_counts_toward_the_lockout(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        asked = ask(otp, reviewer)
        for _ in range(OTP_MAX_ATTEMPTS):
            missed = answer(otp, DpopClient(), reviewer, asked, code=reviewer.wrong)
            assert missed.status_code == 401
        assert list(otp.redis_client.scan_iter("auth:otp:lock:*")), "five misses lock the number"
        # locked: a fresh request is withheld and the right code is refused
        otp.clock.advance(RESEND_COOLDOWN_S * 4)
        fresh = ask(otp, reviewer)
        assert fresh.status_code == 202
        assert answer(otp, DpopClient(), reviewer, fresh).status_code == 401
        assert counted("verify", "locked") >= 1
        assert otp.sends == 0


def test_near_miss_four_wrong_codes_then_the_right_one_signs_in(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        asked = ask(otp, reviewer)
        for _ in range(OTP_MAX_ATTEMPTS - 1):
            answer(otp, DpopClient(), reviewer, asked, code=reviewer.wrong)
        assert answer(otp, DpopClient(), reviewer, asked).status_code == 200
        assert list(otp.redis_client.scan_iter("auth:otp:lock:*")) == []


def test_the_reviewer_request_is_under_the_number_budget(tmp_path: Path) -> None:
    """Three codes an hour for the number, as for any number; the fourth is
    withheld and mints nothing."""
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        for i, step in enumerate((0, RESEND_COOLDOWN_S, RESEND_COOLDOWN_S * 2)):
            otp.clock.advance(step + 1)
            assert ask(otp, reviewer, device=f"review-device-{i}").status_code == 202
        otp.clock.advance(RESEND_COOLDOWN_S * 8)
        before = counted("request", "withheld")
        # a fresh device, so no budget of the caller's refuses: the number's does
        withheld = ask(otp, reviewer, device="review-device-x")
        assert withheld.status_code == 202
        assert counted("request", "withheld") == before + 1
        late = answer(otp, DpopClient(), reviewer, withheld, device="review-device-x")
        assert late.status_code == 401


def test_the_alert_rules_exist_read_a_catalogued_series_and_link_a_runbook() -> None:
    from intake_platform.alert_rules import runbook_problem

    groups = yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"]
    rules = {rule.get("alert"): rule for group in groups for rule in group["rules"]}
    used, refused = rules.get("ReviewSignInUsed"), rules.get("ReviewSignInRefused")
    assert used is not None and refused is not None
    for rule in (used, refused):
        assert "sec_review_signin_total" in rule["expr"]
        assert runbook_problem(rule["annotations"]["runbook"], REPO) is None
        assert rule["annotations"]["runbook"].startswith("docs/runbooks/review-signin.md#")
    assert used["labels"]["severity"] == "ticket"
    assert refused["labels"]["severity"] == "page"
    catalog = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["metrics"]
    [entry] = [m for m in catalog if m["name"] == "sec_review_signin_total"]
    assert entry["labels"] == ["step", "outcome"]
    assert entry.get("status", "live") == "live"


def test_a_runbook_link_one_character_off_does_not_resolve() -> None:
    """Near miss for the runbook check: the link test is not blind."""
    from intake_platform.alert_rules import runbook_problem

    groups = yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"]
    [link] = [
        rule["annotations"]["runbook"]
        for group in groups
        for rule in group["rules"]
        if rule.get("alert") == "ReviewSignInUsed"
    ]
    assert runbook_problem(link[:-1], REPO) is not None


# --- 5. the window: default OFF, every flip audited --------------------------------------------


def test_the_window_is_off_by_default_and_off_refuses(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer, window=False) as otp:
        before = counted("request", "window_closed")
        asked = ask(otp, reviewer)
        assert asked.status_code == 202
        assert list(otp.redis_client.scan_iter("auth:otp:code:*")) == []
        assert answer(otp, DpopClient(), reviewer, asked).status_code == 401
        assert counted("request", "window_closed") == before + 1
        assert otp.sends == 0
        # near miss: opened, the same reviewer signs in; closed again, refused
        review().ReviewWindow(otp.redis_client).open()
        otp.clock.advance(RESEND_COOLDOWN_S * 4)
        assert answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).status_code == 200
        review().ReviewWindow(otp.redis_client).close()
        otp.clock.advance(RESEND_COOLDOWN_S * 8)
        assert answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).status_code == 401


#: A well-formed window id: 16 bytes as hex, derived so no 32-hex literal sits here.
WINDOW_ID = hashlib.sha256(b"int488-window").hexdigest()[:32]


@pytest.mark.parametrize(
    "stored",
    [
        "open",
        "{}",
        json.dumps({"state": "opened", "since": 1, "id": WINDOW_ID}),
        json.dumps({"state": "OPEN", "since": 1, "id": WINDOW_ID}),
        json.dumps({"state": "closed", "since": 1, "id": WINDOW_ID}),
        json.dumps({"state": "open", "id": WINDOW_ID}),
        json.dumps({"state": "open", "since": "soon", "id": WINDOW_ID}),
        json.dumps({"state": "open", "since": 1}),
        json.dumps({"state": "open", "since": 1, "id": WINDOW_ID[:31]}),
        json.dumps({"state": "open", "since": 1, "id": 7}),
        b"\xff",
    ],
    ids=[
        "bare-word",
        "empty-object",
        "opened",
        "upper-case",
        "closed",
        "no-since",
        "since-not-a-number",
        "no-id",
        "short-id",
        "id-not-a-string",
        "not-utf8",
    ],
)
def test_a_garbled_window_reads_closed(stored: str | bytes) -> None:
    fake = fakeredis.FakeStrictRedis()
    fake.set("auth:review:window", stored)
    assert review().ReviewWindow(fake).is_open() is False


def test_near_miss_a_well_formed_open_window_reads_open() -> None:
    fake = fakeredis.FakeStrictRedis()
    fake.set("auth:review:window", json.dumps({"state": "open", "since": 1, "id": WINDOW_ID}))
    state = review().ReviewWindow(fake).state()
    assert state is not None and state.id == WINDOW_ID


def test_an_unreachable_window_reads_closed() -> None:
    class Down:
        def get(self, name: str) -> bytes:
            raise redis.ConnectionError("down")

    assert review().ReviewWindow(Down()).is_open() is False  # type: ignore[arg-type]


def cli(
    verb: str,
    fake: Any,
    *,
    ready: str | None = None,
    audit: Any = None,
    reset: Any = None,
) -> tuple[int, str, list[str]]:
    audited: list[str] = []
    out = io.StringIO()
    code = cli_module().main(
        [verb],
        out=out,
        redis_factory=lambda: fake,
        audit=audit if audit is not None else audited.append,
        readiness=lambda: ready,
        reset=reset if reset is not None else lambda: None,
    )
    return code, out.getvalue(), audited


def test_every_flip_is_audited_and_a_repeat_flip_writes_nothing() -> None:
    fake = fakeredis.FakeStrictRedis()
    assert review().ReviewWindow(fake).is_open() is False
    code, said, audited = cli("on", fake)
    assert code == 0 and audited == ["auth.review.window.opened"]
    assert review().ReviewWindow(fake).is_open() is True
    assert "open" in said
    assert cli("on", fake)[2] == [], "already open: no flip, no row"
    code, said, audited = cli("off", fake)
    assert code == 0 and audited == ["auth.review.window.closed"]
    assert review().ReviewWindow(fake).is_open() is False
    assert cli("off", fake)[2] == []


def test_the_flips_land_on_a_verifiable_chain() -> None:
    store = InMemoryAuditStore()
    chain = AuditChain(store)

    def append(action: str) -> None:
        chain.append(
            actor="operator:host",
            action=action,
            resource_ref="review_signin:window",
            consent_scope_ref="scope:auth",
        )

    fake = fakeredis.FakeStrictRedis()
    cli("on", fake, audit=append)
    cli("off", fake, audit=append)
    entries = store.entries()
    assert [entry.action for entry in entries] == [
        "auth.review.window.opened",
        "auth.review.window.closed",
    ]
    assert verify_entries(entries).ok


def test_opening_is_refused_when_its_row_cannot_be_written() -> None:
    fake = fakeredis.FakeStrictRedis()

    def failing(action: str) -> None:
        raise RuntimeError("audit store down")

    code, said, _ = cli("on", fake, audit=failing)
    assert code == 1
    assert review().ReviewWindow(fake).is_open() is False, "opened without a row"
    assert "audit" in said


def test_a_close_whose_row_fails_still_closes_and_says_so() -> None:
    fake = fakeredis.FakeStrictRedis()
    review().ReviewWindow(fake).open()

    def failing(action: str) -> None:
        raise RuntimeError("audit store down")

    code, said, _ = cli("off", fake, audit=failing)
    assert code == 1
    assert review().ReviewWindow(fake).is_open() is False, "the safer state first"
    assert "audit" in said


@pytest.mark.parametrize(
    "problem", ["not the synthetic host's synthetic tenant (tenant_kind)", "no reviewer code"]
)
def test_on_refuses_where_the_reviewer_cannot_sign_in(problem: str) -> None:
    fake = fakeredis.FakeStrictRedis()
    code, said, audited = cli("on", fake, ready=problem)
    assert code == 1 and audited == []
    assert review().ReviewWindow(fake).is_open() is False
    assert problem in said


@pytest.mark.parametrize("case", sorted(NOT_SYNTHETIC))
def test_readiness_names_the_failed_fact(case: str) -> None:
    overrides, fact = NOT_SYNTHETIC[case]
    reviewer = draw()
    vault = kit.Vault({"api/review_signin": {"number": reviewer.number, "code": reviewer.code}})
    problem = review().review_readiness(strict(**overrides), vault, guards())
    assert problem is not None and fact in problem
    assert reviewer.code not in problem and reviewer.number not in problem


def test_readiness_needs_a_document_with_a_code() -> None:
    reviewer = draw()
    assert review().review_readiness(strict(), kit.Vault(), guards()) is not None
    without = kit.Vault({"api/review_signin": {"number": reviewer.number}})
    assert review().review_readiness(strict(), without, guards()) is not None
    whole = kit.Vault({"api/review_signin": {"number": reviewer.number, "code": reviewer.code}})
    assert review().review_readiness(strict(), whole, guards()) is None
    # the live guards too: hosted lanes on for the reviewer tenant refuse, by id
    lanes_on = review().review_readiness(strict(), whole, guards(voice=Voice(engaged=False)))
    assert lanes_on is not None and str(review().REVIEW_TENANT_ID) in lanes_on


def test_status_prints_the_state_and_no_value() -> None:
    fake = fakeredis.FakeStrictRedis()
    code, said, audited = cli("status", fake)
    assert code == 0 and audited == [] and "closed" in said
    assert cli("bogus", fake)[0] == 2


# --- 6. a synthetic reviewer patient, never real data -------------------------------------------


def test_the_landed_patient_is_the_synthetic_reviewer(tmp_path: Path) -> None:
    reviewer = draw()
    module = review()
    with harness(tmp_path, reviewer) as otp:
        consumer = otp.sign_up(DpopClient())  # a patient of the consumer tenant
        bundle = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
        window = module.ReviewWindow(otp.redis_client).state()
        patient_id, pseudonym = module.review_patient(window.id)
        assert bundle["tenant_id"] == str(module.REVIEW_TENANT_ID)
        assert bundle["patient_id"] == str(patient_id)
        assert bundle["tenant_id"] != str(CONSUMER_TENANT_ID)
        assert module.REVIEW_TENANT_ID != CONSUMER_TENANT_ID
        assert pseudonym.startswith("review.")
        # the reviewer tenant holds exactly the synthetic reviewer, keyed by a
        # fixed synthetic label and never by the number's pseudonym
        tenant = module.REVIEW_TENANT_ID.hex
        held = rows(otp, f"SELECT pseudonym FROM patients WHERE tenant_id = '{tenant}'")  # noqa: S608
        assert held == [(pseudonym,)]
        everyone = [row[0] for row in rows(otp, "SELECT pseudonym FROM patients")]
        assert TOKENIZER.pseudonym(reviewer.number) not in everyone
        assert consumer["patient_id"] != bundle["patient_id"]
        [name] = rows(otp, f"SELECT display_name FROM tenants WHERE id = '{tenant}'")  # noqa: S608
        assert "synthetic" in name[0]


def test_the_reviewer_token_reaches_only_the_reviewer_patient(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        dpop = DpopClient()
        bundle = answer(otp, dpop, reviewer, ask(otp, reviewer)).json()
        visits = otp.get_visits(dpop, bundle["access_token"])
        # authenticated, then the consent gate (no consent rows, as any new account)
        assert visits.status_code == 403
        assert visits.json() == {"error": "consent_required", "scope": "core"}


def test_closing_the_window_ends_the_reviewer_session(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        dpop = DpopClient()
        bundle = answer(otp, dpop, reviewer, ask(otp, reviewer)).json()
        patient_dpop = DpopClient()
        patient = otp.sign_up(patient_dpop)
        review().ReviewWindow(otp.redis_client).close()
        assert otp.get_visits(dpop, bundle["access_token"]).status_code == 401
        assert otp.refresh(dpop, bundle["refresh_token"]).status_code == 401
        # near miss: a consumer patient's session is untouched by the window
        assert otp.get_visits(patient_dpop, patient["access_token"]).status_code == 403
        assert otp.refresh(patient_dpop, patient["refresh_token"]).status_code == 200


def test_a_reviewer_refresh_stays_in_the_reviewer_tenant(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        dpop = DpopClient()
        bundle = answer(otp, dpop, reviewer, ask(otp, reviewer)).json()
        rotated = otp.refresh(dpop, bundle["refresh_token"])
        assert rotated.status_code == 200, rotated.text
        assert rotated.json()["tenant_id"] == str(review().REVIEW_TENANT_ID)


# --- the canary: no code, no number, anywhere ---------------------------------------------------


def _records_text(records: list[logging.LogRecord]) -> str:
    formatter = JsonLogFormatter()
    out = []
    for record in records:
        if record.name.startswith(("httpx", "httpcore")):
            continue  # the test's own HTTP client, not the API's output
        out += [record.getMessage(), repr(record.args), formatter.format(record)]
        if record.exc_info:
            out.append("".join(traceback.format_exception(*record.exc_info)))
    return "\n".join(out)


def _store_text(otp: OtpHarness) -> str:
    out = []
    for name in otp.redis_client.scan_iter("*"):
        out.append(name.decode())
        kind = otp.redis_client.type(name)
        if kind == b"string":
            out.append(otp.redis_client.get(name).decode(errors="replace"))
        elif kind == b"zset":
            out += [m.decode() for m in otp.redis_client.zrange(name, 0, -1)]
        elif kind == b"set":
            out += [m.decode() for m in otp.redis_client.smembers(name)]
    url = str(otp.engine.url).replace("+aiosqlite", "+pysqlite")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            for table in inspect(engine).get_table_names():
                for row in connection.execute(text(f'SELECT * FROM "{table}"')):  # noqa: S608
                    out.append(repr(tuple(row)))
    finally:
        engine.dispose()
    out += [repr(entry) for entry in otp.audit_store.entries()]
    return "\n".join(out)


def find(blob: str, reviewer: Reviewer) -> list[str]:
    found = [form for form in reviewer.forms if form in blob]
    for code in (reviewer.code, reviewer.wrong):
        if re.search(rf"(?<![0-9]){re.escape(code)}(?![0-9])", blob):
            found.append(code)
    return found


def test_no_code_or_number_reaches_a_log_metric_trace_answer_or_store(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    spans = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.add_span_processor(SimpleSpanProcessor(spans))
    caplog.set_level(logging.DEBUG)
    reviewer = draw()
    answers: list[str] = []
    stores: list[str] = []
    with harness(tmp_path / "open", reviewer) as otp:
        asked = ask(otp, reviewer)
        wrong = answer(otp, DpopClient(), reviewer, asked, code=reviewer.wrong)
        signed = answer(otp, DpopClient(), reviewer, asked)
        refreshed = otp.refresh(DpopClient(), signed.json()["refresh_token"])
        cli("off", otp.redis_client)
        otp.clock.advance(RESEND_COOLDOWN_S * 4)
        closed = ask(otp, reviewer)
        late = answer(otp, DpopClient(), reviewer, closed)
        cli("on", otp.redis_client)
        cli("status", otp.redis_client)
        answers += [r.text + repr(dict(r.headers)) for r in (asked, wrong, signed, refreshed)]
        answers += [r.text for r in (closed, late)]
        stores.append(_store_text(otp))
    vault = kit.Vault({"api/review_signin": {"number": reviewer.number}})
    unconfigured = review().review_signin_from_vault(
        vault, settings=strict(), tokenizer=TOKENIZER, pepper=keyed(), guards=guards()
    )
    with harness(tmp_path / "unconfigured", reviewer, signin=unconfigured) as otp:
        refused = ask(otp, reviewer)
        answers.append(refused.text + answer(otp, DpopClient(), reviewer, refused).text)
        stores.append(_store_text(otp))
    with harness(
        tmp_path / "real", reviewer, settings=strict(triage_tenant_kind=TenantKind.REAL)
    ) as otp:
        refused = ask(otp, reviewer)
        answers.append(refused.text + answer(otp, DpopClient(), reviewer, refused).text)
        stores.append(_store_text(otp))
    sinks = {
        "logs": _records_text(caplog.records),
        "metrics": generate_latest(REGISTRY).decode(),
        "traces": "\n".join(span.to_json() for span in spans.get_finished_spans()),
        "answers": "\n".join(answers),
        "store, audit and database": "\n".join(stores),
    }
    for sink, blob in sinks.items():
        assert find(blob, reviewer) == [], f"the reviewer's code or number reached the {sink}"


def test_the_scan_finds_a_leak_when_one_is_there() -> None:
    """Near miss: the scanner is not blind to a code or a number form."""
    reviewer = draw()
    assert find(f"code {reviewer.code} ok", reviewer) == [reviewer.code]
    assert find(f"to {reviewer.forms[4]}", reviewer) != []
    assert find(f"at 17931{reviewer.code}.0", reviewer) == [], "a longer digit run is not a code"
