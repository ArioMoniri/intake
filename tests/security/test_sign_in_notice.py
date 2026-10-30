"""INT-583 — the new-device sign-in notice, by push to the previously signed-in devices.

Owner decision D35 (28 Oct 2026): push, never SMS — a SIM swap would hand an SMS
notice to the attacker. INT-580 detects the new device; this suite holds the send
rules end to end through the OTP routes and the real APNs adapter, replaying
Apple's recorded answers (``tests/fixtures/apns/responses.json``):

- every previously signed-in device with a push token is told, and the new
  device never is — near miss: the new device with a live session and a token
  of its own on its slot;
- a known device tells nobody; a signed-out device is not told;
- never by SMS: the SMS adapter sees only the codes;
- every notice is audited with ids only, and no token reaches a log;
- a token Apple calls gone is dropped; a refused push still lets the sign-in
  through; the account's notices are rate-limited;
- no channel fails closed, with its typed reason;
- the copy: one tr source, siz, PolicyGuard-clean, no link, no number, no PHI.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import FormOfAddress, PolicyGuard, policy_guard_for
from prometheus_client import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import apns_testkit as kit  # noqa: E402
from intake_api.auth_store import OTP_WINDOW_S, AuthStore  # noqa: E402
from push_session_kit import PEPPER, Device, device_ref, harness, sign_in  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
MOBILE_TR = REPO / "apps" / "mobile" / "src" / "lib" / "i18n" / "tr.ts"


def notice() -> Any:
    return importlib.import_module("intake_api.sign_in_notice")


def apns() -> Any:
    return importlib.import_module("intake_api.push_apns")


@pytest.fixture(autouse=True)
def phi_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def apns_gateway(vendor: kit.Vendor) -> Any:
    module = apns()
    return module.ApnsPushGateway(
        module.ApnsCredentials.parse(kit.vault_doc(kit.signing_key())),
        topic=kit.TOPIC,
        egress=kit.policy(),
        inner=vendor.transport(),
    )


def pushed_to(vendor: kit.Vendor) -> list[str]:
    return sorted(r.url.path.rsplit("/", 1)[-1] for r in vendor.requests)


def actions(otp: Any, prefix: str = "auth.notice.") -> list[str]:
    return [e.action for e in otp.audit_store.entries() if e.action.startswith(prefix)]


def _notices(outcome: str) -> float:
    value = REGISTRY.get_sample_value("sec_sign_in_notices_total", {"outcome": outcome})
    return value or 0.0


def two_registered(otp: Any) -> tuple[Device, Device]:
    """Two devices signed in, then both registered (so nobody was told yet)."""
    a = sign_in(otp, "device-a")
    b = sign_in(otp, "device-b")
    assert a.renew().register(kit.TOKEN_A).status_code == 204
    assert b.register(kit.TOKEN_B).status_code == 204
    return a, b


# --- who is told ---------------------------------------------------------------------------


def test_a_new_device_is_pushed_to_every_previously_signed_in_device(tmp_path: Path) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=apns_gateway(vendor)) as otp:
        two_registered(otp)
        assert vendor.requests == [], "device-b was new, but nobody had a token yet"
        before = _notices("sent")
        sign_in(otp, "device-c")
        assert pushed_to(vendor) == sorted([kit.TOKEN_A, kit.TOKEN_B])
        assert _notices("sent") == before + 2


def test_the_new_device_is_never_told_even_with_a_token_of_its_own(tmp_path: Path) -> None:
    """Near miss: device-c has a live session and a token on its own slot, and
    its sign-in still reads as new (its remembered hash was lost). Everyone
    else is told; device-c is not."""
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=apns_gateway(vendor)) as otp:
        a, _ = two_registered(otp)
        c = sign_in(otp, "device-c")
        assert c.register(kit.TOKEN_C).status_code == 204
        vendor.requests.clear()
        otp.redis_client.srem(f"auth:otp:devices:{a.patient_id}", device_ref("device-c"))
        sign_in(otp, "device-c")
        assert pushed_to(vendor) == sorted([kit.TOKEN_A, kit.TOKEN_B])
        assert kit.TOKEN_C not in pushed_to(vendor)


def test_a_known_device_signing_in_again_tells_nobody(tmp_path: Path) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=apns_gateway(vendor)) as otp:
        two_registered(otp)
        sign_in(otp, "device-a")
        assert vendor.requests == []
        assert actions(otp) == ["auth.notice.no_device"], "only device-b's own first sign-in"


def test_a_signed_out_device_is_not_told(tmp_path: Path) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=apns_gateway(vendor)) as otp:
        a, _ = two_registered(otp)
        otp.clock.advance(24 * 3600)
        a.renew()
        b_id = next(s["session_id"] for s in a.sessions()["sessions"] if not s["current"])
        assert a.call("DELETE", f"/v1/auth/sessions/{b_id}").status_code == 204
        sign_in(otp, "device-c")
        assert pushed_to(vendor) == [kit.TOKEN_A]


def test_the_notice_never_goes_by_sms(tmp_path: Path) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=apns_gateway(vendor)) as otp:
        two_registered(otp)
        sends = otp.sends
        sign_in(otp, "device-c")
        assert otp.sends == sends + 1, "the one code, and no SMS notice"
        assert len(vendor.requests) == 2
    source = Path(notice().__file__).read_text(encoding="utf-8")
    for seam in ("otp_netgsm", "otp_twilio", "OtpDeliveryAdapter", "phone_e164"):
        assert seam not in source, seam


# --- what is recorded -------------------------------------------------------------------------


def test_every_notice_is_audited_under_the_patient_with_ids_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=apns_gateway(vendor)) as otp:
        a, _ = two_registered(otp)
        sign_in(otp, "device-c")
        rows = [e for e in otp.audit_store.entries() if e.action == "auth.notice.sent"]
        assert [(r.actor, r.resource_ref) for r in rows] == [
            (f"patient:{a.patient_id}", f"patient:{a.patient_id}")
        ] * 2
        everything = "\n".join(
            f"{e.actor} {e.action} {e.resource_ref} {e.consent_scope_ref}"
            for e in otp.audit_store.entries()
        )
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for token in (kit.TOKEN_A, kit.TOKEN_B, kit.TOKEN_C):
        assert token not in everything and token not in logged


def test_a_token_apple_calls_gone_is_dropped_and_never_tried_again(tmp_path: Path) -> None:
    vendor = kit.Vendor(kit.per_token({kit.TOKEN_A: "unregistered", kit.TOKEN_B: "accepted"}))
    with harness(tmp_path, push_gateway=apns_gateway(vendor)) as otp:
        a, _ = two_registered(otp)
        sign_in(otp, "device-c")
        assert sorted(actions(otp)[-2:]) == ["auth.notice.failed", "auth.notice.sent"]
        assert device_ref("device-a") not in {
            f.decode() for f in otp.redis_client.hkeys(f"auth:push:{a.patient_id}")
        }
        vendor.requests.clear()
        sign_in(otp, "device-d")
        assert pushed_to(vendor) == [kit.TOKEN_B]


def test_a_refused_push_keeps_the_token_and_the_sign_in(tmp_path: Path) -> None:
    """Near miss of the test above: a 503 is the vendor's, not the token's."""
    vendor = kit.Vendor(kit.replay("service_unavailable"))
    with harness(tmp_path, push_gateway=apns_gateway(vendor)) as otp:
        a, _ = two_registered(otp)
        sign_in(otp, "device-c")
        assert actions(otp)[-2:] == ["auth.notice.failed", "auth.notice.failed"]
        assert len(otp.redis_client.hkeys(f"auth:push:{a.patient_id}")) == 2


class CrashingGateway:
    async def send(self, *, device_token: str, alert: Any) -> Any:
        raise RuntimeError(f"adapter bug holding {device_token}")


def test_a_crashing_channel_never_takes_the_sign_in_down(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    with harness(tmp_path, push_gateway=CrashingGateway()) as otp:
        two_registered(otp)
        sign_in(otp, "device-c")  # asserts the 200
        assert actions(otp)[-1] == "auth.notice.failed"
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in logged and kit.TOKEN_A not in logged


def test_the_accounts_notices_are_rate_limited(tmp_path: Path) -> None:
    """Three an hour; the fourth is withheld; a window later, sent again."""
    sessions_module = importlib.import_module("intake_api.device_sessions")
    now = [1_761_800_000.0]
    redis_client = fakeredis.FakeStrictRedis()
    store = sessions_module.DeviceSessionStore(
        redis_client, PEPPER, AuthStore(redis_client, lambda: now[0]), lambda: now[0]
    )
    patient = uuid.uuid4()
    store.bind(patient, "ref-a", "family-a")
    redis_client.sadd("auth:fam:family-a", "x")
    store.register_push(patient, "ref-a", kit.TOKEN_A)
    vendor = kit.Vendor(kit.replay("accepted"))
    channel = notice().PushSignInNotice(apns_gateway(vendor), store)

    def tell() -> tuple[Any, ...]:
        return tuple(
            asyncio.run(channel.new_device_sign_in(patient_id=patient, new_device_ref="ref-new"))
        )

    limit = sessions_module.NOTICE_LIMIT_PER_HOUR
    assert limit == 3
    outcomes = [tell() for _ in range(limit + 1)]
    assert outcomes == [("sent",)] * limit + [("withheld",)]
    now[0] += OTP_WINDOW_S
    assert tell() == ("sent",)
    assert len(vendor.requests) == limit + 1


def test_nobody_to_tell_is_recorded_as_such(tmp_path: Path) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=apns_gateway(vendor)) as otp:
        sign_in(otp, "device-a")  # no token
        sign_in(otp, "device-b")
        assert actions(otp) == ["auth.notice.no_device"]
        assert vendor.requests == []


def test_without_a_channel_the_notice_fails_closed_with_its_reason(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    port = importlib.import_module("intake_api.push_port")
    channel = notice().NoSignInNoticeChannel(port.PushUnconfigured.EGRESS_REFUSED)
    with harness(tmp_path, sign_in_notice=channel) as otp:
        sign_in(otp, "device-a")
        sign_in(otp, "device-b")
        assert actions(otp) == ["auth.notice.unconfigured"]
        assert "auth.login.new_device" in actions(otp, "auth.login.")
    assert any("egress_refused" in r.getMessage() for r in caplog.records)


def test_the_shipped_wiring_has_no_channel_until_the_owner_applies_the_row() -> None:
    app = importlib.import_module("intake_api.app")
    port = importlib.import_module("intake_api.push_port")
    settings = importlib.import_module("intake_api.settings").ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
        audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
        kek_mode="transit",
        environment="production",
        egress_allowlist_path=kit.SHIPPED_ALLOWLIST,
    )
    channel = app._sign_in_notice_from_settings(settings, fakeredis.FakeStrictRedis(), PEPPER, None)
    assert isinstance(channel, notice().NoSignInNoticeChannel)
    assert channel.reason is port.PushUnconfigured.EGRESS_REFUSED
    gauge = REGISTRY.get_sample_value("push_channel_unconfigured", {"reason": "egress_refused"})
    assert gauge == 1.0
    assert REGISTRY.get_sample_value("push_channel_unconfigured", {"reason": "no_credentials"}) == 0


# --- the copy ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def guard() -> PolicyGuard:
    return policy_guard_for(
        locale="tr", profile=VoiceProfile.RESIDENCY_TR, form_of_address=FormOfAddress.SIZ
    )


def test_the_copy_lives_in_one_tr_resource() -> None:
    module = notice()
    resource = json.loads(module.NOTICE_COPY_PATH.read_text(encoding="utf-8"))
    assert module.NOTICE_ALERT.title == resource["push.sign_in.title"] == "Önvizit"
    assert module.NOTICE_ALERT.body == resource["push.sign_in.body"]


def test_the_copy_passes_policyguard_in_siz(guard: PolicyGuard) -> None:
    body = notice().NOTICE_ALERT.body
    verdict = guard.filter(body, scripted=False)
    assert verdict.violations == () and verdict.dropped == ()
    for sentence in guard.sentences(body):
        assert not guard.inspect_sentence(sentence), sentence
    assert "Hesabınıza" in body and "kapatabilirsiniz" in body


def test_a_sen_form_of_the_copy_is_refused(guard: PolicyGuard) -> None:
    verdict = guard.filter(
        "Hesabına yeni bir cihazdan giriş yapıldı. Bu giriş senin değilse "
        "uygulamadaki Cihazların ekranından o cihazın oturumunu kapat.",
        scripted=False,
    )
    assert verdict.violations


def test_the_copy_says_a_new_device_signed_in_and_where_to_look() -> None:
    body = notice().NOTICE_ALERT.body
    assert "yeni bir cihazdan giriş yapıldı" in body
    # the screen it names is the app's own sessions screen
    assert '"me.sessions": "Cihazlarınız"' in MOBILE_TR.read_text(encoding="utf-8")
    assert "Cihazlarınız" in body


def test_the_copy_carries_no_link_number_or_clinical_word() -> None:
    alert = notice().NOTICE_ALERT
    text = f"{alert.title} {alert.body}"
    assert not re.search(r"\d", text)
    assert not re.search(r"https?:|www\.|\.[a-z]{2,}\b|@", text)
    # the title is the app's name, which carries "vizit"; that and nothing
    # else is allowed, in the title and the body alike
    scanned = text.replace("Önvizit", "").lower()
    for clinical in ("vizit", "randevu", "doktor", "hekim", "şikayet", "sağlık", "tanı", "ilaç"):
        assert clinical not in scanned, clinical


def test_a_clinical_word_in_the_title_would_be_caught() -> None:
    """Near miss for the scan above: the allowance is the app's name, not
    every word that contains it."""
    scanned = "Önvizit vizitiniz yaklaşıyor".replace("Önvizit", "").lower()
    assert "vizit" in scanned


def test_a_link_in_the_copy_would_be_caught() -> None:
    """Near miss for the test above: the same predicate flags a link."""
    assert re.search(r"https?:|www\.|\.[a-z]{2,}\b|@", "Bakınız: https://onvizit.example/s")
