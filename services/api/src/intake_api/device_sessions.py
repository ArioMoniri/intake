"""INT-583 — the devices an account is signed in on, and their push tokens.

INT-580 already keeps a set of keyed hashes of the devices an account signed in
from (``auth:otp:devices:<patient>``), to tell a new one from a known one. This
store keeps what the sessions screen and the new-device notice need on top of
that, in Redis beside the tokens:

``auth:sess:<patient>`` — one hash field per device, keyed by the same device
hash (the OTP pepper's ``rate_key("known_device", <binding>)``, never the App
Attest key id). Its value is the device's random ``session_id`` (what the app
names a device by), the refresh families it signed in with, and when it last
signed in. A row whose families have all died goes; the key is renewed on
every sign-in and refresh (:meth:`DeviceSessionStore.touch`).

``auth:push:<patient>`` — one hash field per device, keyed the same way: the
APNs device token the app registered from a session of THAT device, sealed with
AES-256-GCM under a key derived from the OpenBao pepper
(:meth:`intake_api.otp_pepper.OtpPepper.push_token_key`), with the patient id
and the device hash as associated data, so a sealed token cannot be moved to
another account or device, and the instant it was last registered. A token is
only ever registered for the device the calling session signed in from: the
client cannot name the device.

**Retention is per record, not per key** (legal review, 30 Oct 2026). A token
goes when its device is signed out or its sessions end, when the app
unregisters it, when Apple reports it gone, or :data:`REFRESH_TTL_S` after it
was last registered, whichever is first, however recently another device of
the account wrote the hash. Every read prunes what has gone.

``auth:push:rate:<patient>`` — the rolling window of new-device notices sent for
the account (:data:`NOTICE_LIMIT_PER_HOUR`), and ``auth:disowned:<patient>``
the one "not me" report a day that is recorded. Both are admitted atomically
(WATCH/MULTI), so two racing callers never get past the limit between them.

Signing a device out revokes every refresh family it holds (tombstoned, so a
refresh in flight cannot revive one; its access tokens die with them), drops
its push token, and removes its row; when another device did it, the device is
forgotten as well, so its next sign-in is new again and the patient is told.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final

import redis
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from intake_api.auth_store import OTP_WINDOW_S, REFRESH_TTL_S, AuthStore
from intake_api.otp_pepper import OtpPepper

__all__ = [
    "APNS_TOKEN_SHAPE",
    "DISOWNED_REPORT_WINDOW_S",
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
#: One "not me" report per account in this rolling window is recorded (and
#: pages); repeats inside it change nothing the incident has not got already.
DISOWNED_REPORT_WINDOW_S: Final = 24 * 3600


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
    memory, for the one send, and never in ``repr``."""

    session_id: str
    device_ref: str
    token: str = field(repr=False)


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

    def touch(self, patient_id: uuid.UUID) -> None:
        """A refresh: the rows live another session lifetime. The sign-in
        instant is not moved, so the hold still counts from the sign-in."""
        self._r.expire(self._sessions_key(patient_id), REFRESH_TTL_S)

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
        """Every device with at least one live refresh family, newest first.
        A row whose families have all died is deleted here."""
        key = self._sessions_key(patient_id)
        found: list[DeviceSession] = []
        for raw_field, raw in self._r.hgetall(key).items():
            device_ref = _text(raw_field)
            if device_ref is None:
                continue
            session = self._read(device_ref, _text(raw))
            if session is not None and any(self._auth.family_alive(f) for f in session.families):
                found.append(session)
            else:
                self._r.hdel(key, device_ref)
        return sorted(found, key=lambda s: s.signed_in_at, reverse=True)

    def session_of_family(self, patient_id: uuid.UUID, family_id: str) -> DeviceSession | None:
        """The device a session's refresh family belongs to."""
        for session in self.sessions(patient_id):
            if family_id in session.families:
                return session
        return None

    def sign_out(self, patient_id: uuid.UUID, device_ref: str, *, forget: bool) -> int:
        """End every session of one device: its refresh families (tombstoned,
        and with them its access tokens), its push token and its row. With
        ``forget`` (another device asked) it also leaves the account's known
        devices, so its next sign-in is new and told. Returns the refresh
        tokens revoked."""
        key = self._sessions_key(patient_id)
        session = self._read(device_ref, _text(self._r.hget(key, device_ref)))
        revoked = 0
        if session is not None:
            for family in session.families:
                revoked += self._auth.revoke_family(family)
        self._r.hdel(key, device_ref)
        self._r.hdel(self._push_key(patient_id), device_ref)
        if forget:
            self._auth.forget_device(str(patient_id), device_ref)
        return revoked

    # --- push tokens ------------------------------------------------------------------

    @staticmethod
    def _aad(patient_id: uuid.UUID, device_ref: str) -> bytes:
        return f"intake.push.v1|{patient_id}|{device_ref}".encode("ascii")

    def register_push(self, patient_id: uuid.UUID, device_ref: str, token: str) -> None:
        """Seal and keep the device's token with the instant it was registered;
        a second registration replaces it. What has gone is pruned first."""
        if not APNS_TOKEN_SHAPE.fullmatch(token):
            raise ValueError("not an APNs device token")
        self._live_push_records(patient_id)
        nonce = secrets.token_bytes(12)
        sealed = self._seal.encrypt(nonce, token.encode("ascii"), self._aad(patient_id, device_ref))
        record = {
            "n": base64.b64encode(nonce).decode(),
            "c": base64.b64encode(sealed).decode(),
            "at": self._now(),
        }
        key = self._push_key(patient_id)
        self._r.hset(key, device_ref, json.dumps(record))
        self._r.expire(key, REFRESH_TTL_S)

    def unregister_push(self, patient_id: uuid.UUID, device_ref: str) -> None:
        self._r.hdel(self._push_key(patient_id), device_ref)

    def _live_push_records(
        self, patient_id: uuid.UUID
    ) -> tuple[Mapping[str, str], Mapping[str, DeviceSession]]:
        """The push records still within retention, keyed by device hash, and
        the live sessions they belong to. A record registered more than
        :data:`REFRESH_TTL_S` ago, unreadable, or for a device with no live
        session is deleted here."""
        sessions = {s.device_ref: s for s in self.sessions(patient_id)}
        key = self._push_key(patient_id)
        oldest = self._now() - REFRESH_TTL_S
        live: dict[str, str] = {}
        for raw_field, raw in self._r.hgetall(key).items():
            device_ref, text = _text(raw_field), _text(raw)
            if device_ref is None:
                continue
            try:
                registered_at = float(json.loads(text or "")["at"])
            except (KeyError, TypeError, ValueError):
                registered_at = float("-inf")
            if device_ref not in sessions or registered_at <= oldest or text is None:
                self._r.hdel(key, device_ref)
                continue
            live[device_ref] = text
        return live, sessions

    def registered_devices(self, patient_id: uuid.UUID) -> frozenset[str]:
        """The device hashes with a push token still within retention."""
        live, _ = self._live_push_records(patient_id)
        return frozenset(live)

    def push_targets(self, patient_id: uuid.UUID, *, except_device: str) -> list[PushTarget]:
        """Every signed-in device with a push token still within retention,
        except ``except_device`` (the device that just signed in). A token that
        does not open under its own slot is dropped, never sent to."""
        live, sessions = self._live_push_records(patient_id)
        targets: list[PushTarget] = []
        for device_ref, raw in live.items():
            if device_ref == except_device:
                continue
            token = self._open(patient_id, device_ref, raw)
            if token is None:
                self.unregister_push(patient_id, device_ref)
                continue
            targets.append(
                PushTarget(
                    session_id=sessions[device_ref].session_id, device_ref=device_ref, token=token
                )
            )
        return sorted(targets, key=lambda t: t.session_id)

    def _open(self, patient_id: uuid.UUID, device_ref: str, raw: str) -> str | None:
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

    # --- per-account budgets, admitted atomically ---------------------------------------

    def _admit(self, key: str, limit: int, window_s: int) -> bool:
        """Spend one of ``limit`` admissions in the rolling ``window_s``, or
        refuse. WATCH/MULTI: if another caller writes the key between this
        read and this write, the write is abandoned and the read retried."""
        while True:
            with self._r.pipeline() as pipe:
                try:
                    pipe.watch(key)  # type: ignore[no-untyped-call]  # redis-py: untyped
                    now = self._now()
                    held = int(pipe.zcount(key, f"({now - window_s}", "+inf"))
                    if held >= limit:
                        pipe.unwatch()
                        return False
                    pipe.multi()
                    pipe.zremrangebyscore(key, "-inf", now - window_s)
                    pipe.zadd(key, {secrets.token_hex(8): now})
                    pipe.expire(key, window_s * 2)
                    pipe.execute()
                    return True
                except redis.WatchError:
                    continue

    def notice_admitted(self, patient_id: uuid.UUID) -> bool:
        """Spend one of the account's notices in the rolling hour, or refuse."""
        return self._admit(f"auth:push:rate:{patient_id}", NOTICE_LIMIT_PER_HOUR, OTP_WINDOW_S)

    def first_disowned_report(self, patient_id: uuid.UUID) -> bool:
        """Whether this "not me" report is the account's first in the window."""
        return self._admit(f"auth:disowned:{patient_id}", 1, DISOWNED_REPORT_WINDOW_S)
