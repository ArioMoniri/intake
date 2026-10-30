"""INT-583, review round three: a device stops being known when its last session ends.

Security B1, remaining: an intruder's phone had three exits that left it
"known", so its return was silent while the patient's refreshes kept the
known-device set alive. Each one now forgets the device:

- it signs itself out (test_device_session_lifecycle.py);
- its refresh family is revoked on reuse;
- its family expires, and the row is dropped at the account's next read or
  refresh. The drop is a compare-and-delete, so a row a sign-in has just
  rewritten is never dropped.

Legal B2-r: the account's refresh prunes the dead rows, so the retention text
("at the account's next refresh or read once all its sessions have ended") is
true. Legal B6: "not me" is admitted per account AND per reporting device, so
an intruder's report during the hold never swallows the patient's own report.
Repeats leave a non-paging trace.
"""

from __future__ import annotations

import json
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
from intake_api.auth_store import AuthStore  # noqa: E402
from push_session_kit import (  # noqa: E402
    PEPPER,
    device_ref,
    harness,
    recorded_gateway,
    sign_in,
)

DAY_S = 24 * 3600


@pytest.fixture(autouse=True)
def phi_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def _actions(otp: Any, action: str) -> list[str]:
    return [e.action for e in otp.audit_store.entries() if e.action == action]


def _known(otp: Any, patient_id: uuid.UUID) -> set[str]:
    return {m.decode() for m in otp.redis_client.smembers(f"auth:otp:devices:{patient_id}")}


def _expire_families(otp: Any, patient_id: uuid.UUID, device_id: str) -> None:
    """What the family key's TTL does on a live server."""
    raw = otp.redis_client.hget(f"auth:sess:{patient_id}", device_ref(device_id))
    for family in json.loads(raw)["fam"]:
        otp.redis_client.delete(f"auth:fam:{family}")


def _pushed(vendor: kit.Vendor) -> list[str]:
    return sorted(r.url.path.rsplit("/", 1)[-1] for r in vendor.requests)


# --- the reuse revoke ------------------------------------------------------------------------


def test_a_device_whose_family_is_revoked_on_reuse_is_forgotten(tmp_path: Path) -> None:
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=recorded_gateway(vendor)) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        assert a.renew().register(kit.TOKEN_A).status_code == 204
        stolen = str(b.body["refresh_token"])
        assert b.renew() is b  # the first use rotates
        reused = otp.refresh(b.dpop, stolen)  # the old token again: reuse
        assert reused.status_code == 401
        assert device_ref("device-b") not in _known(otp, a.patient_id)
        vendor.requests.clear()
        sign_in(otp, "device-b")
        assert _pushed(vendor) == [kit.TOKEN_A]


def test_a_rotation_without_reuse_keeps_the_device_known(tmp_path: Path) -> None:
    """Near miss for the test above."""
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        b.renew()
        assert device_ref("device-b") in _known(otp, a.patient_id)


# --- the family that expires ---------------------------------------------------------------


def test_an_expired_device_is_dropped_and_forgotten_at_the_accounts_next_refresh(
    tmp_path: Path,
) -> None:
    """Legal B2-r and security B1: A's family expires and only B refreshes.
    The refresh prunes A's row, so auth:sess holds only B, and A is forgotten,
    so A's next sign-in is told."""
    vendor = kit.Vendor(kit.replay("accepted"))
    with harness(tmp_path, push_gateway=recorded_gateway(vendor)) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        assert b.register(kit.TOKEN_B).status_code == 204
        _expire_families(otp, a.patient_id, "device-a")
        b.renew()
        rows = {f.decode() for f in otp.redis_client.hkeys(f"auth:sess:{a.patient_id}")}
        assert rows == {device_ref("device-b")}
        assert device_ref("device-a") not in _known(otp, a.patient_id)
        vendor.requests.clear()
        sign_in(otp, "device-a")
        assert _pushed(vendor) == [kit.TOKEN_B]


def test_while_a_is_alive_its_row_stays_through_bs_refresh(tmp_path: Path) -> None:
    """Near miss for the test above."""
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        b.renew()
        rows = {f.decode() for f in otp.redis_client.hkeys(f"auth:sess:{a.patient_id}")}
        assert rows == {device_ref("device-a"), device_ref("device-b")}
        assert device_ref("device-a") in _known(otp, a.patient_id)


class _BindsBeforeTheDelete:
    """A Redis client whose first compare-and-delete is overtaken, between its
    read and its write, by a sign-in that rewrites the same row."""

    def __init__(self, inner: Any, overtake: list[Any]) -> None:
        self._inner = inner
        self._overtake = overtake

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def pipeline(self, *args: Any, **kwargs: Any) -> Any:
        pipe = self._inner.pipeline(*args, **kwargs)
        overtake = self._overtake
        real_multi = pipe.multi

        def multi() -> None:
            if overtake:
                overtake.pop()()
            real_multi()

        pipe.multi = multi
        return pipe


def test_a_row_a_sign_in_just_rewrote_is_never_dropped() -> None:
    sessions_module = __import__("intake_api.device_sessions", fromlist=["x"])
    server = fakeredis.FakeServer()
    now = [1_761_800_000.0]
    patient = uuid.uuid4()

    def store(client: Any) -> Any:
        return sessions_module.DeviceSessionStore(
            client, PEPPER, AuthStore(client, lambda: now[0]), lambda: now[0]
        )

    plain = fakeredis.FakeStrictRedis(server=server)
    signer = store(plain)
    signer.bind(patient, "ref-x", "old-family")  # its family never existed: dead
    plain.sadd(f"auth:otp:devices:{patient}", "ref-x")

    def sign_in_again() -> None:
        plain.sadd("auth:fam:new-family", "h")
        signer.bind(patient, "ref-x", "new-family")

    reader = store(_BindsBeforeTheDelete(fakeredis.FakeStrictRedis(server=server), [sign_in_again]))
    assert [s.device_ref for s in reader.sessions(patient)] == []  # it read the dead row
    row = json.loads(plain.hget(f"auth:sess:{patient}", "ref-x"))
    assert row["fam"] == ["new-family"], "the rewritten row survived"
    assert plain.sismember(f"auth:otp:devices:{patient}", "ref-x")
    # near miss: with no sign-in in between, the dead row goes and is forgotten
    signer.bind(patient, "ref-y", "dead-family")
    plain.sadd(f"auth:otp:devices:{patient}", "ref-y")
    assert [s.device_ref for s in store(plain).sessions(patient)] == ["ref-x"]
    assert plain.hget(f"auth:sess:{patient}", "ref-y") is None
    assert not plain.sismember(f"auth:otp:devices:{patient}", "ref-y")


# --- legal B6: "not me" per account and per reporting device ---------------------------------


def _disowned_total() -> float:
    return REGISTRY.get_sample_value("sec_sign_in_disowned_total") or 0.0


def test_each_reporting_devices_first_report_is_recorded(tmp_path: Path) -> None:
    """The new device reports during its hold, then the patient's older
    device reports: two rows, and the counter that pages moves twice."""
    with harness(tmp_path) as otp:
        a = sign_in(otp, "device-a")
        otp.clock.advance(DAY_S)  # the patient's phone has been signed in for a day
        b = sign_in(otp, "device-b")  # the newcomer, held
        before = _disowned_total()
        assert (
            b.call("POST", "/v1/auth/sessions/sign-out-others", {"not_me": True}).status_code == 403
        )
        a.renew()
        assert (
            a.call("POST", "/v1/auth/sessions/sign-out-others", {"not_me": True}).status_code == 200
        )
        assert len(_actions(otp, "auth.session.disowned")) == 2
        assert _disowned_total() == before + 2


def test_the_same_device_reporting_three_times_is_one_row_and_two_traces(
    tmp_path: Path,
) -> None:
    """Near miss for the test above. The repeats leave a non-paging trace."""
    with harness(tmp_path) as otp:
        sign_in(otp, "device-a")
        b = sign_in(otp, "device-b")
        before = _disowned_total()
        for _ in range(3):
            b.call("POST", "/v1/auth/sessions/sign-out-others", {"not_me": True})
        assert len(_actions(otp, "auth.session.disowned")) == 1
        assert len(_actions(otp, "auth.session.disowned_repeat")) == 2
        assert _disowned_total() == before + 1


def test_the_report_key_names_the_reporting_device() -> None:
    sessions_module = __import__("intake_api.device_sessions", fromlist=["x"])
    client = fakeredis.FakeStrictRedis()
    now = [1_761_800_000.0]
    store = sessions_module.DeviceSessionStore(
        client, PEPPER, AuthStore(client, lambda: now[0]), lambda: now[0]
    )
    patient = uuid.uuid4()
    assert store.first_disowned_report(patient, "ref-a")
    assert store.first_disowned_report(patient, None)
    assert not store.first_disowned_report(patient, "ref-a")
    keys = sorted(k.decode() for k in client.scan_iter("auth:disowned:*"))
    assert keys == [f"auth:disowned:{patient}:ref-a", f"auth:disowned:{patient}:unbound"]
