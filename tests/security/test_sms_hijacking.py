"""INT-580 — SMS hijacking and phishing (owner order, 28 Oct 2026; GitHub #975).

Acceptance, verbatim: "No PHI and no links in any SMS: the code and the app name
only (template test); the domain-bound one-time-code line (@<domain> #<code>) so
iOS autofills only into Önvizit (associated-domains entitlement checked in the
mobile config; the domain comes from config, never invented); a new-device
sign-in notice; sensitive actions step up to the passkey, which mitigates a SIM
swap. Any change to the SMS text is copy that patients see: siz register,
PolicyGuard, tr source of truth."

The audit (docs/evidence/INT-577.md, rows 28-33) found the SMS already free of
PHI and links, and these gaps:

- **no app name** and **no tr source**: the copy was a Python constant twice
  (the Netgsm one folded from the Twilio one). It now lives in one tr resource,
  ``intake_api/sms_copy.tr.json``, names the app, and both adapters render from
  it; the copy passes PolicyGuard in the siz register;
- **no domain-bound line**, and **no domain to bind to**: ``apps/mobile/app.json``
  declared no ``ios.associatedDomains``. The mechanism reads the app's own
  ``webcredentials:`` entitlement and appends ``@<domain> #<code>`` only for
  exactly one valid public name; anything else — none, two, a malformed one, a
  developer-mode one — sends no line. The owner chose the synthetic host
  (D34, 28 Oct 2026): the app declares ``webcredentials:3-211-2-143.sslip.io``,
  so the line goes out, and the host serves the association file that lets
  iOS honour it (``tests/infra/test_staging_aasa.py``);
- **no new-device signal**: a sign-in from a device the account has not signed
  in from is now detected (keyed hashes of the device, kept for the session
  lifetime), counted, put on the hash chain and handed to a notice channel —
  which fails closed, because no channel to the patient exists yet (an owner
  input).

The passkey step-up is not built here: patients have no passkeys (docs/evidence/INT-580.md).
"""

from __future__ import annotations

import contextlib
import importlib
import json
import re
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import FormOfAddress, PolicyGuard, policy_guard_for
from prometheus_client import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import netgsm_testkit as kit  # noqa: E402
from intake_api.app import _auth_from_settings  # noqa: E402
from intake_api.auth_store import OTP_WINDOW_S, REFRESH_TTL_S  # noqa: E402
from intake_api.otp import AuthWiring  # noqa: E402
from intake_api.settings import ApiSettings  # noqa: E402
from test_otp_abuse import PHONE, DpopClient, OtpHarness, _build  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SHIPPED_APP_CONFIG = REPO / "apps" / "mobile" / "app.json"
DOCKERIGNORE = REPO / "infra" / "staging" / "Dockerfile.api.dockerignore"
CODE = "482915"


def copy_module() -> ModuleType:
    """Resolved per call, so each test fails on its own line before the module
    exists instead of failing collection."""
    return importlib.import_module("intake_api.sms_copy")


def app_config(tmp_path: Path, domains: list[str] | None) -> Path:
    """A mobile app config like the shipped one, with ``domains`` as its
    ``ios.associatedDomains`` (or none at all)."""
    config = json.loads(SHIPPED_APP_CONFIG.read_text(encoding="utf-8"))
    if domains is None:
        config["expo"]["ios"].pop("associatedDomains", None)
    else:
        config["expo"]["ios"]["associatedDomains"] = domains
    path = tmp_path / "app.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def guard() -> PolicyGuard:
    return policy_guard_for(
        locale="tr", profile=VoiceProfile.RESIDENCY_TR, form_of_address=FormOfAddress.SIZ
    )


# --- the copy: one tr source, the code and the app name, siz, PolicyGuard -------------------


def test_the_sms_copy_lives_in_one_tr_resource() -> None:
    module = copy_module()
    resource = json.loads(module.SMS_COPY_PATH.read_text(encoding="utf-8"))
    assert module.OTP_BODY_TR == resource["sms.otp.body"]
    netgsm = importlib.import_module("intake_api.otp_netgsm")
    twilio = importlib.import_module("intake_api.otp_twilio")
    # both adapters render from it: Netgsm's OTP product takes no Turkish
    # letters, so its form is the same words folded to ASCII
    assert twilio.SMS_TEMPLATE == module.OTP_BODY_TR
    assert netgsm.SMS_TEMPLATE == module.fold_ascii(module.OTP_BODY_TR)


def _what_it_says(message: str, code: str) -> str:
    """The message with the app name and the code taken out: what is left is
    the fixed wording, which must carry nothing else."""
    return message.replace(code, "").replace("Önvizit", "").replace("Onvizit", "")


def test_the_sms_carries_the_code_and_the_app_name_and_nothing_else() -> None:
    module = copy_module()
    for message in (
        module.render_otp_sms(CODE),
        module.render_otp_sms(CODE, ascii_only=True),
    ):
        assert message.count(CODE) == 1
        assert "Önvizit" in message or "Onvizit" in message
        rest = _what_it_says(message, CODE)
        assert not re.search(r"\d", rest), "a number other than the code"
        assert not re.search(r"https?:|www\.|\.[a-z]{2,}\b|@", rest), "a link or an address"
        assert "{" not in rest and "}" not in rest


def test_the_checker_would_catch_a_link() -> None:
    """Near miss for the template test: the same predicate flags a variant that
    carries a link or a second number."""
    rest = _what_it_says(f"Önvizit kodunuz {CODE}: https://onvizit.example/g 2", CODE)
    assert re.search(r"https?:|www\.|\.[a-z]{2,}\b|@", rest)
    assert re.search(r"\d", rest)


def test_the_sms_copy_passes_policyguard_in_siz(guard: PolicyGuard) -> None:
    body = copy_module().render_otp_sms(CODE)
    verdict = guard.filter(body, scripted=False)
    assert verdict.violations == () and verdict.dropped == ()
    for sentence in guard.sentences(body):
        assert not guard.inspect_sentence(sentence), sentence
    # siz: the possessive and the instruction are second person plural
    assert "kodunuz" in body and "paylaşmayınız" in body


def test_a_sen_form_of_the_copy_is_refused(guard: PolicyGuard) -> None:
    """Near miss: the same words in the sen register fail the guard."""
    verdict = guard.filter(
        f"Önvizit doğrulama kodun: {CODE}. Bu kodu kimseyle paylaşma.", scripted=False
    )
    assert verdict.violations


@pytest.mark.parametrize("code", ["0000", CODE, "9" * 10])
@pytest.mark.parametrize("domain", [None, "giris.onvizit.example"])
def test_every_netgsm_message_is_ascii_and_one_segment(code: str, domain: str | None) -> None:
    message = copy_module().render_otp_sms(code, domain=domain, ascii_only=True)
    assert message.isascii()
    assert len(message) <= importlib.import_module("intake_api.otp_netgsm").MAX_MESSAGE_LENGTH


# --- the domain-bound line, from the app's own entitlement ---------------------------------


SYNTHETIC_HOST = "3-211-2-143.sslip.io"


def test_the_shipped_app_binds_codes_to_the_synthetic_host() -> None:
    """D34 (owner, 28 Oct 2026): the app's one webcredentials domain is the
    synthetic host, so every OTP SMS ends with its domain-bound line, and iOS
    offers the code only inside Önvizit."""
    module = copy_module()
    domain = module.associated_domain(SHIPPED_APP_CONFIG)
    assert domain == SYNTHETIC_HOST
    for ascii_only in (False, True):
        message = module.render_otp_sms(CODE, domain=domain, ascii_only=ascii_only)
        assert message.splitlines()[-1] == f"@{SYNTHETIC_HOST} #{CODE}"
        assert len(message) <= module.SEGMENT_LIMIT


def test_a_config_without_the_entitlement_sends_no_line(tmp_path: Path) -> None:
    """Near miss for the test above: the same config without the domain."""
    module = copy_module()
    assert module.associated_domain(app_config(tmp_path, None)) is None
    assert "@" not in module.render_otp_sms(CODE, domain=None)


def test_a_webcredentials_domain_binds_the_code_to_it(tmp_path: Path) -> None:
    module = copy_module()
    config = app_config(tmp_path, ["applinks:onvizit.example", "webcredentials:onvizit.example"])
    domain = module.associated_domain(config)
    assert domain == "onvizit.example"
    message = module.render_otp_sms(CODE, domain=domain)
    last = message.splitlines()[-1]
    assert last == f"@onvizit.example #{CODE}", "the WebKit domain-bound format, last line"
    assert message.count(CODE) == 2, "the line binds the code the body carries"


@pytest.mark.parametrize(
    "domains",
    [
        None,
        [],
        ["applinks:onvizit.example"],  # a link domain is not a credentials domain
        ["webcredentials:onvizit.example", "webcredentials:other.example"],  # ambiguous
        ["webcredentials:onvizit.example?mode=developer"],  # a development entitlement
        ["webcredentials:not a domain"],
        ["webcredentials:localhost"],
        ["webcredentials:203.0.113.7"],
        ["webcredentials:" + "a" * 120 + ".example"],  # would push the SMS past a segment
        "webcredentials:onvizit.example",  # not a list
    ],
    ids=[
        "absent",
        "empty",
        "applinks-only",
        "two",
        "developer-mode",
        "malformed",
        "single-label",
        "ip-literal",
        "too-long",
        "not-a-list",
    ],
)
def test_anything_but_one_valid_domain_sends_no_line(tmp_path: Path, domains: Any) -> None:
    assert copy_module().associated_domain(app_config(tmp_path, domains)) is None


def test_an_unreadable_app_config_sends_no_line(tmp_path: Path) -> None:
    assert copy_module().associated_domain(tmp_path / "absent.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert copy_module().associated_domain(broken) is None


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def _staging(tmp_path: Path, config: Path) -> ApiSettings:
    return ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
        audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
        kek_mode="transit",
        tokenization_key="k",
        environment="staging",
        egress_allowlist_path=kit.allowlist_with_the_row(tmp_path),
        sms_egress_proxy_url="http://sms-egress:3128",
        mobile_app_config_path=config,
    )


def test_the_netgsm_wiring_takes_the_domain_from_the_app_config(
    phi_egress: None, tmp_path: Path
) -> None:
    configured = app_config(tmp_path, ["webcredentials:onvizit.example"])
    wiring = _auth_from_settings(_staging(tmp_path, configured), secrets=kit.complete_vault())
    assert isinstance(wiring, AuthWiring)
    assert wiring.delivery.domain == "onvizit.example"
    # the shipped config carries the synthetic host (D34)
    shipped = _auth_from_settings(
        _staging(tmp_path, SHIPPED_APP_CONFIG), secrets=kit.complete_vault()
    )
    assert isinstance(shipped, AuthWiring)
    assert shipped.delivery.domain == SYNTHETIC_HOST
    # near miss: a config without the entitlement, no line
    (tmp_path / "bare").mkdir()
    bare = _auth_from_settings(
        _staging(tmp_path, app_config(tmp_path / "bare", None)), secrets=kit.complete_vault()
    )
    assert isinstance(bare, AuthWiring)
    assert bare.delivery.domain is None


def test_the_wire_body_carries_the_line_when_a_domain_is_configured() -> None:
    netgsm = importlib.import_module("intake_api.otp_netgsm")
    credentials = netgsm.NetgsmCredentials.parse(kit.VAULT_DOC)
    bound = netgsm.seal_otp_request(
        credentials, phone_e164=kit.PHONE, code=CODE, domain="onvizit.example"
    )
    assert bound.msg.splitlines()[-1] == f"@onvizit.example #{CODE}"
    plain = netgsm.seal_otp_request(credentials, phone_e164=kit.PHONE, code=CODE)
    assert "@" not in plain.msg


def test_the_api_image_carries_the_app_config() -> None:
    """The domain is read from the app's own config, so the API image ships it
    (one more file of apps/, beside the scripted catalogue)."""
    lines = [line.strip() for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()]
    assert "!apps/mobile/app.json" in lines


# --- the new-device sign-in signal ---------------------------------------------------------


class RecordingNotice:
    """The sign-in notice port, recording which accounts it was asked to tell."""

    def __init__(self) -> None:
        self.told: list[uuid.UUID] = []

    async def new_device_sign_in(self, *, patient_id: uuid.UUID) -> bool:
        self.told.append(patient_id)
        return True


@contextlib.contextmanager
def harness(tmp_path: Path, **knobs: Any) -> Iterator[OtpHarness]:
    built = _build(tmp_path, **knobs)
    try:
        yield next(built)
    finally:
        next(built, None)


def _new_device_count() -> float:
    return REGISTRY.get_sample_value("sec_new_device_logins_total") or 0.0


def _sign_in(otp: OtpHarness, device_id: str) -> dict[str, Any]:
    assert otp.request_otp(PHONE, device_id=device_id).status_code == 202
    response = otp.verify(DpopClient(), device_id=device_id)
    assert response.status_code == 200, response.text
    # past every request budget, so each sign-in is a real code
    otp.clock.advance(OTP_WINDOW_S + 1)
    body: dict[str, Any] = response.json()
    return body


def test_a_sign_in_from_a_new_device_is_signalled_audited_and_told(tmp_path: Path) -> None:
    notice = RecordingNotice()
    with harness(tmp_path, sign_in_notice=notice) as otp:
        before = _new_device_count()
        first = _sign_in(otp, "device-a")  # the account is created: nothing to tell
        _sign_in(otp, "device-a")  # the same device again: nothing to tell
        assert notice.told == [] and _new_device_count() == before
        _sign_in(otp, "device-b")
        patient = uuid.UUID(first["patient_id"])
        assert notice.told == [patient]
        assert _new_device_count() == before + 1
        rows = [e for e in otp.audit_store.entries() if e.action == "auth.login.new_device"]
        assert [(r.actor, r.resource_ref) for r in rows] == [
            (f"patient:{patient}", f"patient:{patient}")
        ]
        # and device-b is known from now on
        _sign_in(otp, "device-b")
        assert notice.told == [patient]


def test_without_a_channel_the_notice_fails_closed_and_says_so(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("WARNING")
    with harness(tmp_path) as otp:
        _sign_in(otp, "device-a")
        _sign_in(otp, "device-b")
        rows = [e.action for e in otp.audit_store.entries()]
    assert "auth.login.new_device" in rows, "the signal does not depend on a channel"
    assert any("no sign-in notice channel" in r.getMessage() for r in caplog.records)


def test_known_devices_are_keyed_hashes_kept_for_the_session_lifetime(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        body = _sign_in(otp, "device-a")
        keys = list(otp.redis_client.scan_iter("auth:otp:devices:*"))
        assert [k.decode() for k in keys] == [f"auth:otp:devices:{body['patient_id']}"]
        members = [m.decode() for m in otp.redis_client.smembers(keys[0])]
        assert len(members) == 1 and re.fullmatch(r"[0-9a-f]{64}", members[0])
        assert "device-a" not in members[0]
        assert 0 < otp.redis_client.ttl(keys[0]) <= REFRESH_TTL_S


def test_the_device_set_carries_its_inventory_annotation() -> None:
    """Invariant 18: personal data with no column still carries the five
    inventory fields. The device set is a pseudonymous identifier per patient
    id, held in Redis, so it is an off-schema flow of the data inventory, and
    the store labels are generated from the same row."""
    from intake_platform.db.inventory import INVENTORY_FIELDS
    from intake_platform.store.facts import OFF_SCHEMA_FLOWS, data_facts

    flow = OFF_SCHEMA_FLOWS["sign_in_devices"]
    assert set(flow.annotation) == set(INVENTORY_FIELDS)
    for field_name in INVENTORY_FIELDS:
        assert flow.annotation[field_name].strip(), field_name
    assert flow.persisted and flow.active
    assert (REPO / flow.source_path).is_file()
    assert "auth:otp:devices" in flow.what
    # the retention it states is the one the store enforces
    assert REFRESH_TTL_S == 30 * 24 * 3600
    assert "30 days" in flow.annotation["retention"]
    assert "flow:sign_in_devices" in {fact.fact_id for fact in data_facts()}
