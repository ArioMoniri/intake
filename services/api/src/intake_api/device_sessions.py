"""INT-583 — the devices an account is signed in on, and their push tokens.

INT-580 already keeps a set of keyed hashes of the devices an account signed in
from (``auth:otp:devices:<patient>``), to tell a new one from a known one. This
store keeps what the sessions screen and the new-device notice need on top of
that, in Redis beside the tokens, under the same 30-day clock:

``auth:sess:<patient>`` — one hash field per device, keyed by the same device
hash (the OTP pepper's ``rate_key("known_device", <binding>)``, never the App
Attest key id). Its value is the device's random ``session_id`` (what the app
names a device by), the refresh families it signed in with, and when it last
signed in.

``auth:push:<patient>`` — one hash field per device, keyed the same way: the
APNs device token the app registered from a session of THAT device, sealed with
AES-256-GCM under a key derived from the OpenBao pepper
(:meth:`intake_api.otp_pepper.OtpPepper.push_token_key`), with the patient id
and the device hash as associated data, so a sealed token cannot be moved to
another account or device. A token is only ever registered for the device the
calling session signed in from: the client cannot name the device.

``auth:push:rate:<patient>`` — the rolling window of new-device notices sent
for the account (:data:`NOTICE_LIMIT_PER_HOUR`).

Signing a device out revokes every refresh family it holds (its access tokens
die with them: ``AuthStore.family_alive``), drops its push token, and removes
its row. Every key is renewed to :data:`~intake_api.auth_store.REFRESH_TTL_S`
when written, so nothing here outlives the last session by more than that.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import redis
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from intake_api.auth_store import OTP_WINDOW_S, REFRESH_TTL_S, AuthStore
from intake_api.otp_pepper import OtpPepper

__all__ = [
    "APNS_TOKEN_SHAPE",
    "NOTICE_LIMIT_PER_HOUR",
    "SESSION_ID_SHAPE",
    "SIGN_OUT_OTHERS_HOLD_S",
    "DeviceSession",
    "DeviceSessionStore",
    "PushTarget",
]

#: An APNs device token as the app sends it: lower-case hex. Apple's tokens
#: are 32 bytes today and Apple has said they may grow, so up to 100 bytes.
APNS_TOKEN_SHAPE: Final = re.compile(r"(?:[0-9a-f]{2}){32,100}")
SESSION_ID_SHAPE: Final = re.compile(r"[0-9a-f]{32}")
#: A session younger than this may sign itself out, but not other devices:
#: whoever just signed in with an intercepted code or a swapped SIM must not be
#: able to sign the real patient out before the notice is read. An engineering
#: default (docs/evidence/INT-583.md), not a clinical value.
SIGN_OUT_OTHERS_HOLD_S: Final = 24 * 3600
#: New-device notices per account per rolling hour. A new-device sign-in needs
#: a fresh code, and a number gets 3 an hour (files/10 §2), so this is a
#: backstop against a loop, never the bound a real sign-in meets.
NOTICE_LIMIT_PER_HOUR: Final = 3


@dataclass(frozen=True)
class DeviceSession:
    """One device the account is signed in on."""

    session_id: str
    device_ref: str
    families: tuple[str, ...]
    signed_in_at: float


@dataclass(frozen=True)
class PushTarget:
    """One registered device a notice can go to. ``token`` is in clear only in
    memory, for the one send."""

    session_id: str
    device_ref: str
    token: str


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


class DeviceSessionStore:
    """Synchronous, like :class:`AuthStore` (the service hops it off the loop)."""

    def __init__(
        self,
        redis_client: redis.Redis,
        pepper: OtpPepper,
        auth_store: AuthStore,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._r = redis_client
        self._seal = AESGCM(pepper.push_token_key())
        self._auth = auth_store
        self._now_fn = now_fn

    def _now(self) -> float:
        return self._now_fn() if self._now_fn is not None else time.time()

    @staticmethod
    def _sessions_key(patient_id: uuid.UUID) -> str:
        return f"auth:sess:{patient_id}"

    @staticmethod
    def _push_key(patient_id: uuid.UUID) -> str:
        return f"auth:push:{patient_id}"

    @staticmethod
    def _rate_key(patient_id: uuid.UUID) -> str:
        return f"auth:push:rate:{patient_id}"

    # --- sessions ------------------------------------------------------------------

    def bind(self, patient_id: uuid.UUID, device_ref: str, family_id: str) -> DeviceSession:
        """A sign-in on ``device_ref`` with a new refresh family. The device
        keeps its session id across sign-ins; families that have since died
        (expired, revoked) are pruned so the row holds only live ones."""
        key = self._sessions_key(patient_id)
        current = self._read(device_ref, _text(self._r.hget(key, device_ref)))
        live = tuple(f for f in (current.families if current else ()) if self._auth.family_alive(f))
        session = DeviceSession(
            session_id=current.session_id if current else secrets.token_hex(16),
            device_ref=device_ref,
            families=(*live, family_id),
            signed_in_at=self._now(),
        )
        record = {
            "sid": session.session_id,
            "fam": list(session.families),
            "at": session.signed_in_at,
        }
        self._r.hset(key, device_ref, json.dumps(record))
        self._r.expire(key, REFRESH_TTL_S)
        return session

    @staticmethod
    def _read(device_ref: str, raw: str | None) -> DeviceSession | None:
        if raw is None:
            return None
        record = json.loads(raw)
        return DeviceSession(
            session_id=str(record["sid"]),
            device_ref=device_ref,
            families=tuple(str(f) for f in record["fam"]),
            signed_in_at=float(record["at"]),
        )

    def sessions(self, patient_id: uuid.UUID) -> list[DeviceSession]:
        """Every device with at least one live refresh family, newest first."""
        found: list[DeviceSession] = []
        for field, raw in self._r.hgetall(self._sessions_key(patient_id)).items():
            device_ref = _text(field)
            session = self._read(device_ref, _text(raw)) if device_ref is not None else None
            if session is not None and any(self._auth.family_alive(f) for f in session.families):
                found.append(session)
        return sorted(found, key=lambda s: s.signed_in_at, reverse=True)

    def session_of_family(self, patient_id: uuid.UUID, family_id: str) -> DeviceSession | None:
        """The device a session's refresh family belongs to."""
        for session in self.sessions(patient_id):
            if family_id in session.families:
                return session
        return None

    def sign_out(self, patient_id: uuid.UUID, device_ref: str) -> int:
        """End every session of one device: its refresh families (and with
        them its access tokens), its push token and its row. Returns the
        refresh tokens revoked."""
        key = self._sessions_key(patient_id)
        session = self._read(device_ref, _text(self._r.hget(key, device_ref)))
        revoked = 0
        if session is not None:
            for family in session.families:
                revoked += self._auth.revoke_family(family)
        self._r.hdel(key, device_ref)
        self._r.hdel(self._push_key(patient_id), device_ref)
        return revoked

    # --- push tokens ------------------------------------------------------------------

    @staticmethod
    def _aad(patient_id: uuid.UUID, device_ref: str) -> bytes:
        return f"intake.push.v1|{patient_id}|{device_ref}".encode("ascii")

    def register_push(self, patient_id: uuid.UUID, device_ref: str, token: str) -> None:
        """Seal and keep the device's token; a second registration replaces it."""
        if not APNS_TOKEN_SHAPE.fullmatch(token):
            raise ValueError("not an APNs device token")
        nonce = secrets.token_bytes(12)
        sealed = self._seal.encrypt(nonce, token.encode("ascii"), self._aad(patient_id, device_ref))
        record = {"n": base64.b64encode(nonce).decode(), "c": base64.b64encode(sealed).decode()}
        key = self._push_key(patient_id)
        self._r.hset(key, device_ref, json.dumps(record))
        self._r.expire(key, REFRESH_TTL_S)

    def unregister_push(self, patient_id: uuid.UUID, device_ref: str) -> None:
        self._r.hdel(self._push_key(patient_id), device_ref)

    def registered_devices(self, patient_id: uuid.UUID) -> frozenset[str]:
        """The device hashes with a push token, for the sessions screen."""
        fields = self._r.hkeys(self._push_key(patient_id))
        return frozenset(t for t in (_text(f) for f in fields) if t is not None)

    def push_targets(self, patient_id: uuid.UUID, *, except_device: str) -> list[PushTarget]:
        """Every signed-in device with a push token, except ``except_device``
        (the device that just signed in). A token that does not open under its
        own slot is dropped, never sent to."""
        sessions = {s.device_ref: s for s in self.sessions(patient_id)}
        targets: list[PushTarget] = []
        for field, raw in self._r.hgetall(self._push_key(patient_id)).items():
            device_ref = _text(field)
            if device_ref is None or device_ref == except_device or device_ref not in sessions:
                continue
            token = self._open(patient_id, device_ref, _text(raw))
            if token is None:
                self.unregister_push(patient_id, device_ref)
                continue
            targets.append(
                PushTarget(
                    session_id=sessions[device_ref].session_id, device_ref=device_ref, token=token
                )
            )
        return sorted(targets, key=lambda t: t.session_id)

    def _open(self, patient_id: uuid.UUID, device_ref: str, raw: str | None) -> str | None:
        if raw is None:
            return None
        try:
            record = json.loads(raw)
            plain = self._seal.decrypt(
                base64.b64decode(record["n"]),
                base64.b64decode(record["c"]),
                self._aad(patient_id, device_ref),
            )
        except (InvalidTag, KeyError, TypeError, ValueError):
            return None
        return plain.decode("ascii")

    # --- the notice budget -------------------------------------------------------------

    def notice_admitted(self, patient_id: uuid.UUID) -> bool:
        """Spend one of the account's notices in the rolling hour, or refuse."""
        key = self._rate_key(patient_id)
        now = self._now()
        self._r.zremrangebyscore(key, "-inf", now - OTP_WINDOW_S)
        if int(self._r.zcard(key)) >= NOTICE_LIMIT_PER_HOUR:
            return False
        self._r.zadd(key, {secrets.token_hex(8): now})
        self._r.expire(key, OTP_WINDOW_S * 2)
        return True
