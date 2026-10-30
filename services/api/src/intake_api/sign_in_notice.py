"""INT-583 — the new-device sign-in notice, by push to the devices already signed in.

Owner decision D35 (28 Oct 2026, files/00_STATE.md §3): when an account is
signed in from a device it has not used, the patient is told by PUSH on the
devices that were signed in before, and never by SMS — a SIM swap delivers the
SMS to the attacker, who is exactly who signed in.

INT-580 detects the event (``intake_api.otp``: the ``sec_new_device_logins``
counter and the ``auth.login.new_device`` audit row) and hands it to the
:class:`SignInNotice` port defined here. The send rules:

- **Every previously signed-in device, never the new one.** The targets are the
  account's devices with a live session and a push token, minus the device
  that just signed in (``DeviceSessionStore.push_targets``). A token registered
  earlier on the new device's own slot is not told either.
- **Never SMS.** The only adapter behind the port is a push gateway
  (``intake_api.push_port``); nothing here can reach the SMS seam.
- **Rate-limited**: :data:`~intake_api.device_sessions.NOTICE_LIMIT_PER_HOUR`
  per account per rolling hour.
- **Constant content**: one tr resource (``sign_in_notice.tr.json``), siz,
  PolicyGuard-clean, no PHI, no link, nothing clinical.
- **Fail closed**: with no push channel (no APNs key in OpenBao, the egress
  policy refusing APNs, no HTTP/2), :class:`NoSignInNoticeChannel` says so by
  its typed reason, and the sign-in is still counted and audited.

The port answers with one :class:`NoticeOutcome` per device tried (or one for
the whole notice when none was), and ``OtpAuthService`` audits each on the hash
chain with ids only and counts it in ``sec_sign_in_notices_total``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol

from prometheus_client import Counter, Gauge

from intake_api.device_sessions import DeviceSessionStore
from intake_api.push_port import (
    PUSH_FAILURES_THAT_DROP_THE_TOKEN,
    PushAlert,
    PushDeliveryError,
    PushGateway,
    PushUnconfigured,
)

__all__ = [
    "NOTICE_ALERT",
    "NOTICE_COPY_PATH",
    "PUSH_CHANNEL_UNCONFIGURED",
    "SEC_SIGN_IN_NOTICES_TOTAL",
    "NoSignInNoticeChannel",
    "NoticeOutcome",
    "PushSignInNotice",
    "SignInNotice",
    "mark_channel",
]

logger = logging.getLogger("intake_api.sign_in_notice")

NOTICE_COPY_PATH: Final = Path(__file__).with_name("sign_in_notice.tr.json")
#: APNs collapses notices with one id into the latest on the lock screen.
_COLLAPSE_ID: Final = "intake-sign-in"


class NoticeOutcome(StrEnum):
    """What became of a notice, per device tried. A closed, id-shaped
    vocabulary: the audit action suffix and the metric label."""

    SENT = "sent"
    FAILED = "failed"
    #: the account's notice budget for the hour is spent
    WITHHELD = "withheld"
    #: no other signed-in device has a push token: nobody could be told
    NO_DEVICE = "no_device"
    #: no push channel is wired
    UNCONFIGURED = "unconfigured"


SEC_SIGN_IN_NOTICES_TOTAL: Final = Counter(
    "sec_sign_in_notices_total",
    "New-device sign-in notices by outcome, one per device tried.",
    ("outcome",),
)
PUSH_CHANNEL_UNCONFIGURED: Final = Gauge(
    "push_channel_unconfigured",
    "1 for the reason no push channel is wired for the sign-in notice, else 0.",
    ("reason",),
)


def _load_alert() -> PushAlert:
    document = json.loads(NOTICE_COPY_PATH.read_text(encoding="utf-8"))
    title, body = document["push.sign_in.title"], document["push.sign_in.body"]
    if not (isinstance(title, str) and isinstance(body, str)) or "{" in title + body:
        raise ValueError("sign_in_notice.tr.json: the notice is two constant strings")
    return PushAlert(title=title, body=body, collapse_id=_COLLAPSE_ID)


#: The notice, in Turkish, exactly as it reaches a lock screen.
NOTICE_ALERT: Final = _load_alert()


class SignInNotice(Protocol):
    """INT-580's port, given the device to leave out (INT-583): tell the
    account holder that their account was signed in to from ``new_device_ref``
    on every other device, and say what became of it."""

    async def new_device_sign_in(
        self, *, patient_id: uuid.UUID, new_device_ref: str
    ) -> tuple[NoticeOutcome, ...]: ...


class NoSignInNoticeChannel:
    """No channel: the notice fails closed, says why, and reaches nobody. The
    signal itself (the counter, the audit row) does not depend on a channel."""

    def __init__(self, reason: PushUnconfigured = PushUnconfigured.NO_CREDENTIALS) -> None:
        self.reason = reason

    async def new_device_sign_in(
        self, *, patient_id: uuid.UUID, new_device_ref: str
    ) -> tuple[NoticeOutcome, ...]:
        del patient_id, new_device_ref
        logger.warning(
            "new-device sign-in not told to the patient: no sign-in notice channel (%s)",
            self.reason.value,
        )
        return (NoticeOutcome.UNCONFIGURED,)


class PushSignInNotice:
    """The D35 channel: a push to every previously signed-in device."""

    def __init__(self, gateway: PushGateway, sessions: DeviceSessionStore) -> None:
        self._gateway = gateway
        self._sessions = sessions

    async def new_device_sign_in(
        self, *, patient_id: uuid.UUID, new_device_ref: str
    ) -> tuple[NoticeOutcome, ...]:
        targets = await asyncio.to_thread(
            self._sessions.push_targets, patient_id, except_device=new_device_ref
        )
        if not targets:
            logger.info("new-device sign-in notice: no other device has a push token")
            return (NoticeOutcome.NO_DEVICE,)
        if not await asyncio.to_thread(self._sessions.notice_admitted, patient_id):
            logger.warning("new-device sign-in notice withheld: the account's hourly budget")
            return (NoticeOutcome.WITHHELD,)
        outcomes: list[NoticeOutcome] = []
        for target in targets:
            failure: PushDeliveryError | None = None
            try:
                receipt = await self._gateway.send(device_token=target.token, alert=NOTICE_ALERT)
            except PushDeliveryError as exc:
                failure = exc
            if failure is None:
                logger.info("new-device sign-in notice sent push_id=%s", receipt.push_id)
                outcomes.append(NoticeOutcome.SENT)
                continue
            logger.warning(
                "new-device sign-in notice not accepted reason=%s http_status=%s",
                failure.reason.value,
                failure.status_code if failure.status_code is not None else "-",
            )
            if failure.reason in PUSH_FAILURES_THAT_DROP_THE_TOKEN:
                await asyncio.to_thread(
                    self._sessions.unregister_push, patient_id, target.device_ref
                )
            outcomes.append(NoticeOutcome.FAILED)
        return tuple(outcomes)


def mark_channel(reason: PushUnconfigured | None) -> None:
    """Set the wiring gauge: 1 on the reason no channel is wired, 0 elsewhere."""
    for member in PushUnconfigured:
        PUSH_CHANNEL_UNCONFIGURED.labels(reason=member.value).set(1 if member is reason else 0)
