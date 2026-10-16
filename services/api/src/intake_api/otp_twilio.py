"""INT-329 — the Twilio SMS delivery adapter for the OTP tier (audit 2026-09-26 F13).

**Not wired since INT-528.** The owner chose Netgsm as the SMS vendor on 16 Oct
2026 (INT-358, GitHub #576), whose processing the decision records as in
Türkiye, to be confirmed by the signed DPA.
``intake_api.otp_netgsm`` is the adapter the OTP tier wires outside dev, and
nothing constructs this one outside its own tests. It stays as INT-329's record
and as the second implementation the port's tests run against.

What it does, and what it refuses:

- **Async.** ``send`` awaits an ``httpx.AsyncClient`` over the INT-018 guarded
  async transport, so the OTP route never holds the event loop while the vendor
  answers. The adapter it replaces made a blocking ``httpx.post`` inside the
  async route, for up to 8 s.
- **Egress.** Every call declares ``EgressPurpose.SMS_OTP_DELIVERY`` and
  ``DataClass.PHI``. A phone number is personal data under KVKK, and the phone
  of a patient signing up for a clinical intake says they are one, so the call
  takes the strictest class; both personal classes clear the same gate. The
  shipped allow-list has no row for this purpose. A row would send personal
  data to a processor abroad, which needs the owner's DPA and cross-border
  decision (and, on the PHI tier, a ``phi_exception_approval`` naming it).
  Until that row exists the wiring leaves the tier at 503, and the guard would
  refuse the call before a byte left anyway.
- **Credentials from OpenBao only** (invariant 14): the KV document
  ``secret/api/twilio`` holds ``account_sid``, ``auth_token`` and ``from``,
  inside the API's own subtree (scripts/security/openbao_dev_setup.sh). The
  ``TWILIO_*`` environment variables are never read. Each value is
  shape-checked, a refusal names the field and never the value, and the token
  never reaches ``repr``.
- **Logs** (invariant 6): one line per outcome, with the vendor message id,
  the HTTP status, a closed-vocabulary reason and the vendor's numeric error
  code. Never the phone, the code, the token or a vendor body: Twilio's error
  message echoes the number, and its 201 echoes the number and the body.
- **Errors** are :class:`~intake_api.otp.OtpDeliveryError` with a typed reason,
  raised outside the ``except`` block, so no transport exception is chained to
  them. A transport exception holds the request, and the request holds the
  form body.
- **No retry.** A retried SMS is a second code in flight; the patient's resend
  after the 60 s cooldown is the retry.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

import httpx
from intake_platform.egress import (
    DataClass,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    TransferLog,
    guarded_async_client,
)

from intake_api.otp import DeliveryReceipt, OtpDeliveryError, OtpDeliveryFailure

__all__ = [
    "SMS_EGRESS",
    "TWILIO_API_HOST",
    "TWILIO_KV_PATH",
    "TwilioConfigError",
    "TwilioCredentials",
    "TwilioSmsDeliveryAdapter",
]

logger = logging.getLogger("intake_api.otp_twilio")

TWILIO_API_HOST: Final = "api.twilio.com"
TWILIO_API_PORT: Final = 443
#: KV v2 path under ``secret/``, inside the ``intake-api`` policy's subtree.
TWILIO_KV_PATH: Final = "api/twilio"
SMS_EGRESS: Final = EgressContext(purpose=EgressPurpose.SMS_OTP_DELIVERY, data_class=DataClass.PHI)
DEFAULT_TIMEOUT: Final = httpx.Timeout(8.0, connect=3.0)
#: siz register, -iniz for instructional prose (CLAUDE.md, clinical content
#: rules). No brand name: which one ships is not settled on main.
SMS_TEMPLATE: Final = "Doğrulama kodunuz: {code}. Bu kodu kimseyle paylaşmayınız."

_FIELDS: Final = ("account_sid", "auth_token", "from")
_ACCOUNT_SID = re.compile(r"AC[0-9a-fA-F]{32}")
_MESSAGE_SID = re.compile(r"(SM|MM)[0-9a-fA-F]{32}")
_SERVICE_SID = re.compile(r"MG[0-9a-fA-F]{32}")
_E164 = re.compile(r"\+[1-9][0-9]{7,14}")
_ALPHANUMERIC_SENDER = re.compile(r"(?=.*[A-Za-z])[A-Za-z0-9 ]{1,11}")
#: Twilio message states — the only vendor text a log line may carry.
_VENDOR_STATES: Final = frozenset(
    {"accepted", "scheduled", "queued", "sending", "sent", "delivered", "undelivered", "failed"}
)


class TwilioConfigError(ValueError):
    """The vault document is missing a value or holds a malformed one. The
    message names fields, never values."""


@dataclass(frozen=True)
class TwilioCredentials:
    """The account, its auth token and the sender: a phone number in E.164, a
    Messaging Service SID, or an alphanumeric sender id."""

    account_sid: str
    auth_token: str = field(repr=False)
    sender: str

    @classmethod
    def parse(cls, document: Mapping[str, object]) -> TwilioCredentials:
        values: dict[str, str] = {}
        missing: list[str] = []
        malformed: list[str] = []
        for name in _FIELDS:
            raw = document.get(name)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                missing.append(name)
            elif not isinstance(raw, str):
                malformed.append(name)
            else:
                values[name] = raw.strip()
        if missing:
            raise TwilioConfigError(
                f"OpenBao secret/{TWILIO_KV_PATH} is missing {', '.join(missing)}"
            )
        if not _ACCOUNT_SID.fullmatch(values.get("account_sid", "")):
            malformed.append("account_sid")
        sender = values.get("from", "")
        if not any(p.fullmatch(sender) for p in (_E164, _SERVICE_SID, _ALPHANUMERIC_SENDER)):
            malformed.append("from")
        if malformed:
            names = ", ".join(sorted(set(malformed)))
            raise TwilioConfigError(f"OpenBao secret/{TWILIO_KV_PATH} has malformed {names}")
        return cls(values["account_sid"], values["auth_token"], values["from"])


def _reason_for(status: int) -> OtpDeliveryFailure:
    if status in (401, 403):
        return OtpDeliveryFailure.AUTH_FAILED
    if status == 429:
        return OtpDeliveryFailure.RATE_LIMITED
    if status >= 500:
        return OtpDeliveryFailure.VENDOR_UNAVAILABLE
    return OtpDeliveryFailure.REJECTED


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _vendor_code(body: Mapping[str, Any]) -> int | None:
    code = body.get("code")
    return code if isinstance(code, int) and not isinstance(code, bool) else None


class TwilioSmsDeliveryAdapter:
    """The OTP tier's SMS adapter over Twilio's Messages API (INT-329)."""

    def __init__(
        self,
        credentials: TwilioCredentials,
        *,
        egress: EgressPolicy,
        inner: httpx.AsyncBaseTransport | None = None,
        transfer_log: TransferLog | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._credentials = credentials
        self._policy = egress
        self._inner = inner
        self._transfer_log = transfer_log
        self._timeout = timeout
        self._url = (
            f"https://{TWILIO_API_HOST}/2010-04-01/Accounts/{credentials.account_sid}/Messages.json"
        )
        sender = credentials.sender
        self._sender_field = "MessagingServiceSid" if _SERVICE_SID.fullmatch(sender) else "From"

    async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
        form = {
            "To": phone_e164,
            self._sender_field: self._credentials.sender,
            "Body": SMS_TEMPLATE.format(code=code),
        }
        auth = (self._credentials.account_sid, self._credentials.auth_token)
        response: httpx.Response | None = None
        reason: OtpDeliveryFailure | None = None
        async with guarded_async_client(
            self._policy,
            SMS_EGRESS,
            inner=self._inner,
            transfer_log=self._transfer_log,
            timeout=self._timeout,
        ) as client:
            try:
                response = await client.post(self._url, data=form, auth=auth)
            except EgressDenied:
                reason = OtpDeliveryFailure.EGRESS_DENIED
            except httpx.TimeoutException:
                reason = OtpDeliveryFailure.TIMEOUT
            except httpx.TransportError:
                reason = OtpDeliveryFailure.UNREACHABLE
        # Raised here, after the except blocks have closed, so nothing is
        # chained: the transport error holds the request and its form body.
        if response is None:
            raise self._failed(OtpDeliveryError(reason or OtpDeliveryFailure.UNREACHABLE))
        return self._receipt(response)

    def _receipt(self, response: httpx.Response) -> DeliveryReceipt:
        status = response.status_code
        body = _json_object(response)
        if not 200 <= status < 300:
            raise self._failed(
                OtpDeliveryError(
                    _reason_for(status), status_code=status, vendor_code=_vendor_code(body)
                )
            )
        sid = body.get("sid")
        if not (isinstance(sid, str) and _MESSAGE_SID.fullmatch(sid)):
            # accepted-looking but unprovable: never record a receipt we cannot tie
            # to a vendor message
            raise self._failed(
                OtpDeliveryError(OtpDeliveryFailure.MALFORMED_RESPONSE, status_code=status)
            )
        state = body.get("status")
        logger.info(
            "otp delivery accepted (twilio) delivery_id=%s http_status=%s vendor_status=%s",
            sid,
            status,
            state if state in _VENDOR_STATES else "-",
        )
        return DeliveryReceipt(delivery_id=sid)

    @staticmethod
    def _failed(error: OtpDeliveryError) -> OtpDeliveryError:
        logger.warning(
            "otp delivery failed (twilio) reason=%s http_status=%s vendor_code=%s",
            error.reason,
            error.status_code if error.status_code is not None else "-",
            error.vendor_code if error.vendor_code is not None else "-",
        )
        return error
