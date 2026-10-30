"""INT-583 review fixes: a device's session, from sign-in to forgetting it.

The security review (30 Oct 2026) found two holes and the legal review two false
statements, and this suite holds each one closed:

- **A signed-out device is forgotten** (security B1, rounds two and three).
  Its next sign-in is a new device again, so the patient is told, whoever
  signed it out, itself included.
- **Sign-out is final against a refresh that is already in flight** (security
  B2). A revoked family is tombstoned. A rotation that lands after the revoke
  is undone and refused, and the family stays dead. Shown with a
  deterministic interleaving.
- **Retention is what the inventory says** (legal B2). A push token goes 30
  days after its own last registration. A token whose device has no live
  session goes, and so does a session row whose families are all dead.
- **A device that keeps refreshing keeps its row and its "known" status**
  (legal B3). The refresh renews both, so after 30 days the patient is still
  listed and still told, and the intruder's sign-in still counts as new.
- **The notice budget and the "not me" report are atomic per account.** Two
  racing admissions never exceed the limit, and a repeated report is
  recorded once a day.
- **No channel, no registration.** PUT answers 503 `push_unavailable` and
  stores nothing; the sessions list says ``notices_on``.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from prometheus_client import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import apns_testkit as kit  # noqa: E402
from intake_api.auth_store import REFRESH_TTL_S, AuthStore  # noqa: E402
from push_session_kit import (  # noqa: E402
    PEPPER,
    Device,
    device_ref,
    harness,
    recorded_gateway,
    sign_in,
)

DAY_S = 24 * 3600
HOLD_S = DAY_S


@pytest.fixture(autouse=True)
def phi_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def _actions(otp: Any, prefix: str) -> list[str]:
    return [e.action for e in otp.audit_store.entries() if e.action.startswith(prefix)]


def _pushed(vendor: kit.Vendor) -> list[str]:
    return sorted(r.url.path.rsplit("/", 1)[-1] for r in vendor.requests)


def _other_id(device: Device) -> str:
    return next(s["session_id"] for s in device.sessions()["sessions"] if not s["current"])


# --- security B1: a device signed out by another is forgotten ---------------------------


def test_a_device_signed_out_by_another_is_new_again_and_is_told(tmp_path: Path) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=recorded_gateway(vendor)) as otp:
        a = sign_in(otp, "device-a")
        sign_in(otp, "device-b")
        assert a.renew().register(kit.TOKEN_A).status_code == 204
        otp.clock.advance(HOLD_S)
        a.renew()
        assert a.call("DELETE", f"/v1/auth/sessions/{_other_id(a)}").status_code == 204
        known = {m.decode() for m in otp.redis_client.smembers(f"auth:otp:devices:{a.patient_id}")}
        assert device_ref("device-b") not in known
        new_before = _actions(otp, "auth.login.new_device")
        vendor.requests.clear()
        sign_in(otp, "device-b")
        assert len(_actions(otp, "auth.login.new_device")) == len(new_before) + 1
        assert _pushed(vendor) == [kit.TOKEN_A]


def test_sign_out_others_forgets_every_other_device(tmp_path: Path) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=recorded_gateway(vendor)) as otp:
        a = sign_in(otp, "device-a")
        sign_in(otp, "device-b")
        sign_in(otp, "device-c")
        otp.clock.advance(HOLD_S)
        assert a.renew().register(kit.TOKEN_A).status_code == 204
        assert a.call("POST", "/v1/auth/sessions/sign-out-others", {}).status_code == 200
        known = {m.decode() for m in otp.redis_client.smembers(f"auth:otp:devices:{a.patient_id}")}
        assert known == {device_ref("device-a")}
        vendor.requests.clear()
        sign_in(otp, "device-c")
        assert _pushed(vendor) == [kit.TOKEN_A]


def test_a_device_that_signs_itself_out_is_new_again_and_is_told(tmp_path: Path) -> None:
    """Round three: an intruder's phone that signs itself out must not come
    back silently, so every sign-out forgets the device, its own included."""
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=recorded_gateway(vendor)) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        assert a.renew().register(kit.TOKEN_A).status_code == 204
        own = next(s["session_id"] for s in b.sessions()["sessions"] if s["current"])
        assert b.call("DELETE", f"/v1/auth/sessions/{own}").status_code == 204
        before = _actions(otp, "auth.login.new_device")
        vendor.requests.clear()
        sign_in(otp, "device-b")
        assert len(_actions(otp, "auth.login.new_device")) == len(before) + 1
        assert _pushed(vendor) == [kit.TOKEN_A]


# --- security B2: sign-out is final against a refresh already in flight ------------------


def _store(now: list[float]) -> AuthStore:
    return AuthStore(fakeredis.FakeStrictRedis(), lambda: now[0])


def _save(store: AuthStore, token_hash: str, family: str) -> bool:
    return store.save_refresh(
        token_hash, family_id=family, patient_id=uuid.uuid4(), tenant_id=uuid.uuid4(), jkt="k"
    )


def test_a_rotation_that_lands_after_the_revoke_is_undone() -> None:
    """The interleaving the review found: a refresh reads its record, the
    family is revoked, then the rotation writes the new token into the
    family. The write is undone and refused, and the family stays dead."""
    store = _store([1_761_800_000.0])
    assert _save(store, "h1", "F")
    assert store.get_refresh("h1") is not None  # the refresh has read its record
    store.revoke_family("F")  # the sign-out lands
    store.mark_refresh_rotated("h1")
    assert _save(store, "h2", "F") is False
    assert not store.family_alive("F")
    assert store.get_refresh("h2") is None


def test_without_a_revoke_the_rotation_stands() -> None:
    """Near miss for the interleaving above."""
    store = _store([1_761_800_000.0])
    assert _save(store, "h1", "F")
    store.mark_refresh_rotated("h1")
    assert _save(store, "h2", "F") is True
    assert store.family_alive("F") and store.get_refresh("h2") is not None


def test_a_refresh_in_flight_when_its_device_is_signed_out_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        otp.clock.advance(HOLD_S)
        a.renew()
        b_id = _other_id(a)
        real = AuthStore.mark_refresh_rotated
        fired: list[bool] = []

        def rotate_after_the_sign_out(self: AuthStore, token_hash: str) -> None:
            if not fired:
                fired.append(True)
                assert a.call("DELETE", f"/v1/auth/sessions/{b_id}").status_code == 204
            real(self, token_hash)

        monkeypatch.setattr(AuthStore, "mark_refresh_rotated", rotate_after_the_sign_out)
        response = b.refresh()
        monkeypatch.setattr(AuthStore, "mark_refresh_rotated", real)
        assert fired and response.status_code == 401
        assert [s["current"] for s in a.sessions()["sessions"]] == [True]


# --- legal B2: retention is what the inventory says --------------------------------------


def test_a_token_goes_thirty_days_after_its_own_last_registration(tmp_path: Path) -> None:
    """A registers once; B re-registers daily. On day 30 plus a second A's
    token is gone and B's is not, although B kept the account's hash fresh."""
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        assert a.renew().register(kit.TOKEN_A).status_code == 204
        for _ in range(30):
            otp.clock.advance(DAY_S)
            assert b.renew().register(kit.TOKEN_B).status_code == 204
        otp.clock.advance(1)
        store = otp.client.app.state.api.auth.device_sessions
        assert store.registered_devices(a.patient_id) == {device_ref("device-b")}
        fields = {f.decode() for f in otp.redis_client.hkeys(f"auth:push:{a.patient_id}")}
        assert fields == {device_ref("device-b")}


def test_a_token_whose_session_ended_goes_and_so_does_its_row(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        assert b.register(kit.TOKEN_B).status_code == 204
        # b's only family expires (what the key's TTL does on a live server)
        for family in _families(otp, a.patient_id, "device-b"):
            otp.redis_client.delete(f"auth:fam:{family}")
        store = otp.client.app.state.api.auth.device_sessions
        assert store.registered_devices(a.patient_id) == frozenset()
        assert otp.redis_client.hlen(f"auth:push:{a.patient_id}") == 0
        assert [s["current"] for s in a.renew().sessions()["sessions"]] == [True]
        rows = {f.decode() for f in otp.redis_client.hkeys(f"auth:sess:{a.patient_id}")}
        assert rows == {device_ref("device-a")}


def test_a_row_with_a_live_family_stays(tmp_path: Path) -> None:
    """Near miss for the test above: one live family keeps the row and the token."""
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        assert b.register(kit.TOKEN_B).status_code == 204
        store = otp.client.app.state.api.auth.device_sessions
        assert store.registered_devices(a.patient_id) == {device_ref("device-b")}
        assert otp.redis_client.hlen(f"auth:sess:{a.patient_id}") == 2


def _families(otp: Any, patient_id: uuid.UUID, device_id: str) -> list[str]:
    import json

    raw = otp.redis_client.hget(f"auth:sess:{patient_id}", device_ref(device_id))
    return [str(f) for f in json.loads(raw)["fam"]]


# --- legal B3: a device that keeps refreshing keeps its row and its "known" status ------


def test_a_device_refreshing_for_thirty_one_days_is_still_listed_and_told(
    tmp_path: Path,
) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=recorded_gateway(vendor)) as otp:
        a = sign_in(otp, "device-a")
        sessions_key = f"auth:sess:{a.patient_id}"
        known_key = f"auth:otp:devices:{a.patient_id}"
        for _ in range(31):
            otp.clock.advance(DAY_S)
            # what a live server's clock would have eaten down by now
            otp.redis_client.expire(sessions_key, 10)
            otp.redis_client.expire(known_key, 10)
            assert a.renew().register(kit.TOKEN_A).status_code == 204
            assert otp.redis_client.ttl(sessions_key) > REFRESH_TTL_S - 60
            assert otp.redis_client.ttl(known_key) > REFRESH_TTL_S - 60
        assert [s["current"] for s in a.sessions()["sessions"]] == [True]
        vendor.requests.clear()
        sign_in(otp, "device-z")
        assert _pushed(vendor) == [kit.TOKEN_A]


def test_the_hold_still_counts_from_the_sign_in_not_the_refresh(tmp_path: Path) -> None:
    """Near miss for the renewal above: a refresh renews the row's lifetime,
    never the moment it signed in, or the hold would restart every time."""
    with harness(tmp_path) as otp:
        sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        otp.clock.advance(HOLD_S - 60)
        b.renew()
        otp.clock.advance(61)
        b.renew()
        assert b.sessions()["sign_out_others_after"] is None


# --- the notice budget and the "not me" report, per account and atomic ------------------


class _Interleaved:
    """A Redis client whose first transaction is interrupted, after its read
    and before its write, by another admission on the same server."""

    def __init__(self, inner: Any, interrupt: Any) -> None:
        self._inner = inner
        self._interrupt = interrupt

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def pipeline(self, *args: Any, **kwargs: Any) -> Any:
        pipe = self._inner.pipeline(*args, **kwargs)
        interrupt = self._interrupt
        real_multi = pipe.multi

        def multi() -> None:
            if interrupt:
                interrupt.pop()()
            real_multi()

        pipe.multi = multi
        return pipe


def test_two_racing_admissions_never_exceed_the_hourly_limit() -> None:
    sessions_module = __import__("intake_api.device_sessions", fromlist=["x"])
    server = fakeredis.FakeServer()
    now = [1_761_800_000.0]
    patient = uuid.uuid4()

    def store(client: Any) -> Any:
        return sessions_module.DeviceSessionStore(
            client, PEPPER, AuthStore(client, lambda: now[0]), lambda: now[0]
        )

    other = store(fakeredis.FakeStrictRedis(server=server))
    limit = sessions_module.NOTICE_LIMIT_PER_HOUR
    for _ in range(limit - 1):
        assert other.notice_admitted(patient)
    interrupts = [lambda: other.notice_admitted(patient)]
    racing = store(_Interleaved(fakeredis.FakeStrictRedis(server=server), interrupts))
    assert racing.notice_admitted(patient) is False, "the racer saw room, then lost it"
    assert other.notice_admitted(patient) is False
    assert fakeredis.FakeStrictRedis(server=server).zcard(f"auth:push:rate:{patient}") == limit


def _disowned(otp: Any) -> list[str]:
    return [e.action for e in otp.audit_store.entries() if e.action == "auth.session.disowned"]


def test_not_me_is_recorded_once_a_day_per_reporting_device(tmp_path: Path) -> None:
    with harness(tmp_path) as otp:
        sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        before = REGISTRY.get_sample_value("sec_sign_in_disowned_total") or 0.0
        for _ in range(3):
            b.call("POST", "/v1/auth/sessions/sign-out-others", {"not_me": True})
        assert _disowned(otp) == ["auth.session.disowned"]
        assert REGISTRY.get_sample_value("sec_sign_in_disowned_total") == before + 1
        # near miss: a day later it is a new report
        otp.clock.advance(DAY_S + 1)
        b.renew().call("POST", "/v1/auth/sessions/sign-out-others", {"not_me": True})
        assert len(_disowned(otp)) == 2


def test_not_me_from_an_unbound_session_is_still_recorded(tmp_path: Path) -> None:
    """N2: the report is written before anything can refuse, the missing
    device binding included."""
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        otp.redis_client.delete(f"auth:sess:{a.patient_id}")
        response = a.call("POST", "/v1/auth/sessions/sign-out-others", {"not_me": True})
        assert response.status_code == 409
        assert _disowned(otp) == ["auth.session.disowned"]


# --- no channel, no registration ------------------------------------------------------------


def test_without_a_channel_a_token_is_refused_and_nothing_stored(tmp_path: Path) -> None:
    with harness(tmp_path, channel=False) as otp:
        a = sign_in(otp, "device-a")
        response = a.register(kit.TOKEN_A)
        assert response.status_code == 503
        assert response.json() == {"error": "push_unavailable"}
        assert otp.redis_client.exists(f"auth:push:{a.patient_id}") == 0
        assert a.sessions()["notices_on"] is False


def test_with_a_channel_the_same_token_is_kept(tmp_path: Path) -> None:
    """Near miss for the test above."""
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        assert a.register(kit.TOKEN_A).status_code == 204
        assert otp.redis_client.hlen(f"auth:push:{a.patient_id}") == 1
        assert a.sessions()["notices_on"] is True
