"""Shared helpers for the INT-583 tests (test_device_sessions.py, test_sign_in_notice.py).

A :class:`Device` is one phone signed in to the OTP harness: its own DPoP key,
its own attested install id and the tokens its sign-in returned, so a test can
call the sessions and push-token routes as that device. The pepper is fixed per
harness, so a test can name a device's keyed hash the way the server does.
"""

from __future__ import annotations

import contextlib
import hashlib
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from intake_api.auth_store import OTP_WINDOW_S  # noqa: E402
from intake_api.otp_pepper import OtpPepper  # noqa: E402
from test_otp_abuse import PHONE, DpopClient, OtpHarness, _build  # noqa: E402

PEPPER = OtpPepper.parse({"pepper": hashlib.sha256(b"int583-push-session-kit").hexdigest()})
OTHER_PHONE = "+905321114466"


def recorded_gateway(vendor: Any = None) -> Any:
    """The real APNs adapter over a recorded answer (accepted, unless a
    vendor is given): never Apple, never a fake channel."""
    import apns_testkit as kit
    from intake_api.push_apns import ApnsCredentials, ApnsPushGateway

    vendor = vendor if vendor is not None else kit.Vendor(kit.replay("accepted"))
    return ApnsPushGateway(
        ApnsCredentials.parse(kit.vault_doc(kit.signing_key())),
        topic=kit.TOPIC,
        egress=kit.policy(),
        inner=vendor.transport(),
    )


@contextlib.contextmanager
def harness(tmp_path: Path, *, channel: bool = True, **knobs: Any) -> Iterator[OtpHarness]:
    """The OTP harness with the D35 channel wired over a recorded gateway,
    unless ``channel`` is False or the test wires its own."""
    if channel and "push_gateway" not in knobs and "sign_in_notice" not in knobs:
        knobs["push_gateway"] = recorded_gateway()
    built = _build(tmp_path, pepper=PEPPER, **knobs)
    try:
        yield next(built)
    finally:
        next(built, None)


def device_ref(device_id: str) -> str:
    """The server's keyed hash of a dev-tier install id (INT-580)."""
    return PEPPER.rate_key("known_device", f"dev-unattested:{device_id}")


@dataclass
class Device:
    otp: OtpHarness
    device_id: str
    dpop: DpopClient = field(default_factory=DpopClient)
    body: dict[str, Any] = field(default_factory=dict)

    @property
    def access(self) -> str:
        return str(self.body["access_token"])

    @property
    def patient_id(self) -> uuid.UUID:
        return uuid.UUID(self.body["patient_id"])

    def call(self, method: str, path: str, json: Any = None, token: str | None = None) -> Any:
        access = token if token is not None else self.access
        headers = {
            "Authorization": f"DPoP {access}",
            "DPoP": self.otp.proof_for(self.dpop, method, path, access),
        }
        return self.otp.client.request(method, path, json=json, headers=headers)

    def register(self, push_token: str) -> Any:
        return self.call("PUT", "/v1/auth/push-token", {"platform": "ios", "token": push_token})

    def sessions(self) -> dict[str, Any]:
        response = self.call("GET", "/v1/auth/sessions")
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def refresh(self) -> Any:
        return self.otp.refresh(self.dpop, str(self.body["refresh_token"]))

    def renew(self) -> Device:
        """Rotate the token pair (the same family), as the app does when its
        15-minute access token has expired."""
        response = self.refresh()
        assert response.status_code == 200, response.text
        self.body = response.json()
        return self


def sign_in(otp: OtpHarness, device_id: str, phone: str = PHONE) -> Device:
    """One real sign-in from ``device_id``, the notice settled. The clock first
    moves past every request budget, so each sign-in gets a real code and
    returns a fresh access token."""
    otp.clock.advance(OTP_WINDOW_S + 1)
    device = Device(otp, device_id)
    assert otp.request_otp(phone, device_id=device_id).status_code == 202
    response = otp.verify(device.dpop, phone=phone, device_id=device_id)
    assert response.status_code == 200, response.text
    otp.settle()
    device.body = response.json()
    return device
