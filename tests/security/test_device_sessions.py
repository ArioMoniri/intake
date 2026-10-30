"""INT-583 — the patient's sessions and the push token, bound to the attested device.

- A push token is registered only from a signed-in OTP session, and is kept for
  the device that session signed in from: the client cannot name a device, and
  the token is sealed at rest under a key derived from the OpenBao pepper.
- The sessions screen lists the devices, signs one or all of the others out —
  ending their refresh AND access tokens at once and dropping their push token —
  and takes "Bu girişi ben yapmadım", the breach hook.
- A session younger than the hold cannot sign the other devices out (whoever just
  signed in with a stolen code must not sign the real patient out first); it can
  sign itself out, and its "not me" report is recorded anyway.
- Near misses throughout: 63- and 201-character tokens, an extra ``device``
  field, another patient's session id, one second short of the hold.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from prometheus_client import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import apns_testkit as kit  # noqa: E402
from intake_api.auth_store import REFRESH_TTL_S  # noqa: E402
from push_session_kit import OTHER_PHONE, device_ref, harness, sign_in  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
HOLD_S = 24 * 3600


def sessions_module() -> Any:
    return importlib.import_module("intake_api.device_sessions")


def _count(name: str, labels: dict[str, str] | None = None) -> float:
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


def _actions(otp: Any, prefix: str) -> list[str]:
    return [e.action for e in otp.audit_store.entries() if e.action.startswith(prefix)]


# --- the push token: a signed-in session, its own device, sealed ------------------------------


def test_a_token_is_registered_only_from_a_signed_in_session(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        body = {"platform": "ios", "token": kit.TOKEN_A}
        assert otp.client.put("/v1/auth/push-token", json=body).status_code == 401
        # the dev bearer tier is not a device session
        dev = {"Authorization": "Bearer unit-patient-token"}
        assert otp.client.put("/v1/auth/push-token", json=body, headers=dev).status_code == 401
        # a DPoP proof from another key does not carry the session
        stranger = importlib.import_module("test_otp_abuse").DpopClient()
        headers = {
            "Authorization": f"DPoP {a.access}",
            "DPoP": otp.proof_for(stranger, "PUT", "/v1/auth/push-token", a.access),
        }
        assert otp.client.put("/v1/auth/push-token", json=body, headers=headers).status_code == 401
        assert otp.redis_client.hlen(f"auth:push:{a.patient_id}") == 0
        assert a.register(kit.TOKEN_A).status_code == 204
        assert _actions(otp, "auth.push.") == ["auth.push.registered"]


def test_the_token_is_kept_for_the_sessions_own_device(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        assert b.register(kit.TOKEN_B).status_code == 204
        fields = {f.decode() for f in otp.redis_client.hkeys(f"auth:push:{a.patient_id}")}
        assert fields == {device_ref("device-b")}
        # the client cannot name a device: an extra field is refused
        named = b.call(
            "PUT",
            "/v1/auth/push-token",
            {"platform": "ios", "token": kit.TOKEN_B, "device": device_ref("device-a")},
        )
        assert named.status_code == 422
        assert a.renew().sessions()["sessions"][1]["push"] is True  # b, not a
        assert a.sessions()["sessions"][0]["push"] is False


@pytest.mark.parametrize(
    "token",
    ["a1" * 31 + "a", "A1" * 32, "g1" * 32, "a1" * 100 + "a", "", "a1" * 32 + " "],
)
def test_a_malformed_token_is_refused(tmp_path: Path, token: str) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        assert a.register(token).status_code == 422
        assert (
            a.call(
                "PUT", "/v1/auth/push-token", {"platform": "android", "token": kit.TOKEN_A}
            ).status_code
            == 422
        )
        assert otp.redis_client.hlen(f"auth:push:{a.patient_id}") == 0


def test_the_token_is_sealed_at_rest_and_bound_to_its_slot(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        sign_in(otp, "device-b")
        assert a.renew().register(kit.TOKEN_A).status_code == 204
        dump = b"".join(
            key + b"".join(v for pair in otp.redis_client.hgetall(key).items() for v in pair)
            for key in otp.redis_client.scan_iter("auth:push:*")
        )
        assert kit.TOKEN_A.encode() not in dump and bytes.fromhex(kit.TOKEN_A) not in dump
        store = otp.client.app.state.api.auth.device_sessions
        [target] = store.push_targets(a.patient_id, except_device="none")
        assert target.token == kit.TOKEN_A
        # moved to device-b's slot, the sealed token does not open, and is dropped
        key = f"auth:push:{a.patient_id}"
        sealed = otp.redis_client.hget(key, device_ref("device-a"))
        otp.redis_client.hdel(key, device_ref("device-a"))
        otp.redis_client.hset(key, device_ref("device-b"), sealed)
        assert store.push_targets(a.patient_id, except_device="none") == []
        assert otp.redis_client.hlen(key) == 0


def test_unregistering_is_idempotent(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        assert a.register(kit.TOKEN_A).status_code == 204
        assert a.call("DELETE", "/v1/auth/push-token").status_code == 204
        assert a.call("DELETE", "/v1/auth/push-token").status_code == 204
        assert otp.redis_client.hlen(f"auth:push:{a.patient_id}") == 0


def test_a_session_from_before_device_binding_is_unbound(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        otp.redis_client.delete(f"auth:sess:{a.patient_id}")
        response = a.register(kit.TOKEN_A)
        assert response.status_code == 409
        assert response.json() == {"error": "session_unbound"}
        assert a.call("GET", "/v1/auth/sessions").status_code == 409


# --- the sessions screen ------------------------------------------------------------------------


def test_the_list_puts_this_device_first_and_says_what_each_holds(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        assert b.register(kit.TOKEN_B).status_code == 204
        listed = a.renew().sessions()
        assert [s["current"] for s in listed["sessions"]] == [True, False]
        assert [s["push"] for s in listed["sessions"]] == [False, True]
        for row in listed["sessions"]:
            assert re.fullmatch(r"[0-9a-f]{32}", row["session_id"])
            assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", row["signed_in_at"])
            assert set(row) == {"session_id", "current", "signed_in_at", "push"}
        assert listed["sign_out_others_after"] is not None
        # the same device keeps its id across sign-ins
        again = sign_in(otp, "device-a")
        assert again.sessions()["sessions"][0]["session_id"] == listed["sessions"][0]["session_id"]
        assert len(again.sessions()["sessions"]) == 2


def test_signing_a_device_out_ends_its_tokens_at_once(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        assert b.register(kit.TOKEN_B).status_code == 204
        otp.clock.advance(HOLD_S)
        a.renew()
        b_id = next(s["session_id"] for s in a.sessions()["sessions"] if not s["current"])
        before = _count("sec_sessions_signed_out_total", {"scope": "one"})
        assert a.call("DELETE", f"/v1/auth/sessions/{b_id}").status_code == 204
        assert b.refresh().status_code == 401
        assert b.call("GET", "/v1/auth/sessions").status_code == 401  # access, not at expiry
        assert otp.redis_client.hlen(f"auth:push:{a.patient_id}") == 0
        # near miss: the device that signed it out is still in
        assert [s["current"] for s in a.sessions()["sessions"]] == [True]
        assert _count("sec_sessions_signed_out_total", {"scope": "one"}) == before + 1
        assert "auth.session.signed_out" in _actions(otp, "auth.session.")


def test_a_new_session_cannot_sign_the_others_out_until_the_hold_ends(tmp_path: Path) -> None:
    sessions = sessions_module()
    assert sessions.SIGN_OUT_OTHERS_HOLD_S == HOLD_S
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")  # the newcomer
        a_id = next(s["session_id"] for s in b.sessions()["sessions"] if not s["current"])
        refused = b.call("DELETE", f"/v1/auth/sessions/{a_id}")
        assert refused.status_code == 403
        assert refused.json()["error"] == "session_too_new"
        assert 0 < refused.json()["retry_after_s"] <= HOLD_S
        assert b.call("POST", "/v1/auth/sessions/sign-out-others", {}).status_code == 403
        # one second short of the hold: still refused
        otp.clock.advance(HOLD_S - 1)
        b.renew()
        assert b.call("DELETE", f"/v1/auth/sessions/{a_id}").status_code == 403
        assert a.renew().refresh().status_code == 200
        otp.clock.advance(1)
        b.renew()
        assert b.sessions()["sign_out_others_after"] is None
        assert b.call("DELETE", f"/v1/auth/sessions/{a_id}").status_code == 204


def test_a_new_session_can_sign_itself_out(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        own = next(s["session_id"] for s in b.sessions()["sessions"] if s["current"])
        assert b.call("DELETE", f"/v1/auth/sessions/{own}").status_code == 204
        assert b.refresh().status_code == 401
        assert "auth.session.signed_out_self" in _actions(otp, "auth.session.")


def test_sign_out_others_ends_every_other_device(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        c = sign_in(otp, "device-c")
        otp.clock.advance(HOLD_S)
        a.renew()
        response = a.call("POST", "/v1/auth/sessions/sign-out-others", {"not_me": False})
        assert response.status_code == 200 and response.json() == {"signed_out": 2}
        assert b.refresh().status_code == 401 and c.refresh().status_code == 401
        assert [s["current"] for s in a.sessions()["sessions"]] == [True]
        assert "auth.session.disowned" not in _actions(otp, "auth.session.")


def test_not_me_is_the_breach_hook_and_is_recorded_even_under_the_hold(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        before = _count("sec_sign_in_disowned_total")
        held = b.call("POST", "/v1/auth/sessions/sign-out-others", {"not_me": True})
        assert held.status_code == 403
        assert _count("sec_sign_in_disowned_total") == before + 1
        assert _actions(otp, "auth.session.") == ["auth.session.disowned"]
        rows = [e for e in otp.audit_store.entries() if e.action == "auth.session.disowned"]
        assert [r.resource_ref for r in rows] == [f"patient:{b.patient_id}"]


def test_not_me_after_the_hold_signs_the_others_out(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        otp.clock.advance(HOLD_S)
        a.renew()
        response = a.call("POST", "/v1/auth/sessions/sign-out-others", {"not_me": True})
        assert response.status_code == 200 and response.json() == {"signed_out": 1}
        assert b.refresh().status_code == 401
        assert _actions(otp, "auth.session.") == [
            "auth.session.disowned",
            "auth.session.signed_out_others",
        ]


def test_another_patients_session_is_not_found(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        other = sign_in(otp, "device-z", phone=OTHER_PHONE)
        foreign = other.sessions()["sessions"][0]["session_id"]
        otp.clock.advance(HOLD_S)
        a.renew()
        assert a.call("DELETE", f"/v1/auth/sessions/{foreign}").status_code == 404
        assert a.call("DELETE", "/v1/auth/sessions/not-an-id").status_code == 404
        assert other.renew().refresh().status_code == 200


# --- the record: inventory, metrics, the alert ----------------------------------------------


@pytest.mark.parametrize("flow_id", ["device_sessions", "push_tokens"])
def test_each_new_datum_carries_its_inventory_annotation(flow_id: str) -> None:
    """Invariant 18: personal data with no column still carries the five
    inventory fields, and the store labels are generated from the same row."""
    from intake_platform.db.inventory import INVENTORY_FIELDS
    from intake_platform.store.facts import OFF_SCHEMA_FLOWS, data_facts, sharing_for

    flow = OFF_SCHEMA_FLOWS[flow_id]
    assert set(flow.annotation) == set(INVENTORY_FIELDS)
    for field_name in INVENTORY_FIELDS:
        assert flow.annotation[field_name].strip(), field_name
    assert flow.persisted and flow.active
    assert (REPO / flow.source_path).is_file()
    assert REFRESH_TTL_S == 30 * 24 * 3600 and "30 days" in flow.annotation["retention"]
    assert f"flow:{flow_id}" in {fact.fact_id for fact in data_facts()}
    sharing_for(flow.annotation["recipients"])  # classified, or the build stops


def test_the_push_token_names_apple_as_its_one_recipient() -> None:
    from intake_platform.store.facts import OFF_SCHEMA_FLOWS

    recipients = OFF_SCHEMA_FLOWS["push_tokens"].annotation["recipients"]
    assert "Apple Push Notification service" in recipients and "processor" in recipients
    assert "auth:push:" in OFF_SCHEMA_FLOWS["push_tokens"].what
    assert "auth:sess:" in OFF_SCHEMA_FLOWS["device_sessions"].what


def test_the_disowned_alert_pages_and_names_the_runbook() -> None:
    rules = yaml.safe_load(
        (REPO / "infra" / "observability" / "security-rules.yaml").read_text("utf-8")
    )
    found = [
        rule
        for group in rules["groups"]
        for rule in group["rules"]
        if rule.get("alert") == "SignInDisowned"
    ]
    assert len(found) == 1
    [rule] = found
    assert "sec_sign_in_disowned_total" in rule["expr"]
    assert rule["labels"]["severity"] == "page"
    runbook = rule["annotations"]["runbook"]
    path, _, anchor = runbook.partition("#")
    text = (REPO / path).read_text("utf-8")
    assert "72" in text and anchor
    assert "auth.session.disowned" in text


def test_every_new_series_is_catalogued() -> None:
    catalog = yaml.safe_load((REPO / "observability" / "metrics_catalog.yaml").read_text("utf-8"))
    names = {m["name"] for m in catalog["metrics"]}
    for name in (
        "sec_sign_in_notices_total",
        "push_channel_unconfigured",
        "push_delivery_total",
        "sec_sessions_signed_out_total",
        "sec_sign_in_disowned_total",
    ):
        assert name in names, name
