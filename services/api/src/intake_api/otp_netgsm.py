"""INT-528 — the Netgsm OTP SMS adapter behind the INT-329 SMS port.

The owner chose the vendor on 16 Oct 2026 (INT-358, GitHub #576): Netgsm's OTP
SMS product, which that decision records as BTK-licensed and processing the
data in Türkiye. The signed DPA is what confirms both. On the synthetic staging
host (AWS us-east-1) the number passes through that host before it reaches the
vendor. This module is the adapter and its wiring; ``intake_api.otp`` holds the
port it implements.

**The wire contract** comes from Netgsm's public API documentation, section
"OTP SMS" (https://www.netgsm.com.tr/dokuman/#otp-sms, retrieved 16 Oct 2026;
docs/evidence/INT-528.md), and its answer from that page and Netgsm's official
SDKs (retrieved 28 Oct 2026; docs/evidence/INT-576.md). The tests replay
``tests/fixtures/netgsm/otp_rest_v2.json``, derived from those sources:

- ``POST https://api.netgsm.com.tr/sms/rest/v2/otp`` with HTTP Basic auth: the
  subscriber number (``usercode``) and the API sub-user's password.
- A JSON body of exactly ``msgheader``, ``msg`` and ``no``. :class:`NetgsmOtpRequest`
  enumerates them by hand, so nothing joins the payload by reflection.
- ``no`` is the 10-digit national mobile number. The product cannot send abroad
  or to a landline, so anything but a Turkish mobile is refused before the wire.
- ``msg`` is one segment with no Turkish letters (155 characters with an
  alphanumeric sender). :data:`SMS_TEMPLATE` is the INT-329 wording folded to
  ASCII, and a test holds the two together.
- Success is a 2xx JSON object with ``"code": "00"`` and exactly one
  digit-string job id under :data:`JOB_ID_KEYS`: ``jobid`` in the
  documentation's sample, ``jobId`` in Netgsm's JS SDK (INT-576: the live
  answer was not the documentation's sample). A refusal carries one of the
  documented OTP codes 20, 30, 40-41, 50-52, 60, 70, 80 or 100-101, each mapped
  to a typed :class:`NetgsmRefusal` and to one
  :class:`~intake_api.otp.OtpDeliveryFailure`. The body's code decides wherever
  one is present, whatever the HTTP status.
- Any other 2xx is a typed refusal and never a success: ``unparseable_response``
  (no documented code), ``accepted_without_job_id`` (code 00 but no readable
  job id) or ``unknown_vendor_code``. Its port reason is ``malformed_response``,
  which is not retryable: Netgsm may already have sent the code.

**The posture is INT-329's, unchanged:**

- Async, over the INT-018 guarded async transport, declaring
  ``EgressPurpose.SMS_OTP_DELIVERY`` and ``DataClass.PHI``: the phone of a
  patient signing up for a clinical intake says they are one. The call clears
  only a ``phi_allowed`` row that names a recorded decision, with
  ``INTAKE_ALLOW_PHI_EGRESS=explicit-yes`` at runtime. The allow-list's one
  phi_path row is that row (owner-528-netgsm-egress.patch, INT-358).
- Credentials from OpenBao only (invariant 14): ``secret/api/netgsm`` holds
  ``usercode``, ``password`` and ``msgheader``. No environment variable is
  read. A refusal names the field, never the value, and the password never
  reaches ``repr``.
- Logs, metrics and traces carry no phone, code, password or vendor text
  (invariant 6): one log line per outcome with the job id, the HTTP status, the
  refusal and the numeric code; one counter with a closed outcome label.
- Errors are raised outside the ``except`` blocks, so no transport exception is
  chained to them: a transport exception holds the request, and the request
  holds the body.
- No retry. A retried SMS is a second code in flight; the patient's resend
  after the cooldown is the retry. An answer that may mean "sent" says so
  through :attr:`~intake_api.otp.OtpDeliveryError.retryable`.
- The structure of a 2xx answer that is accepted or cannot be read, and never
  a value from it, rides the receipt or the error as
  :class:`~intake_api.otp_netgsm_shape.AnswerShape`, for the owner's opt-in
  diagnostic (``intake_api.otp_send_check --shape``).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Protocol, final

import httpx
import yaml
from intake_platform.egress import (
    DEDICATED_PERSONAL_PROXIES,
    DataClass,
    EgressConfigError,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    TransferLog,
    assert_dev_only_vendors,
    guarded_async_client,
    load_allowlist,
)
from intake_platform.secrets import SecretsBootError, SecretsProvider
from prometheus_client import Counter

from intake_api.otp import (
    DeliveryReceipt,
    DevLogDeliveryAdapter,
    OtpDeliveryAdapter,
    OtpDeliveryError,
    OtpDeliveryFailure,
)
from intake_api.otp_netgsm_shape import AnswerShape, answer_shape
from intake_api.settings import ApiSettings
from intake_api.sms_recipients import (
    ADMIT_ALL,
    SYNTHETIC_ENVIRONMENTS,
    RecipientGate,
    SmsTestAllowlist,
)

__all__ = [
    "DELIVERY_OUTCOMES",
    "JOB_ID_KEYS",
    "MAX_MESSAGE_LENGTH",
    "NETGSM_API_HOST",
    "NETGSM_KV_PATH",
    "NETGSM_OTP_URL",
    "OTP_SMS_DELIVERY_TOTAL",
    "SMS_EGRESS",
    "SMS_TEMPLATE",
    "SUCCESS_CODE",
    "TEST_ALLOWLIST_FIELD",
    "VENDOR_CODE_REFUSALS",
    "KvSecrets",
    "NetgsmConfigError",
    "NetgsmCredentials",
    "NetgsmDeliveryError",
    "NetgsmOtpRequest",
    "NetgsmReceipt",
    "NetgsmRefusal",
    "NetgsmSmsDeliveryAdapter",
    "otp_delivery_from_settings",
    "seal_otp_request",
]

logger = logging.getLogger("intake_api.otp_netgsm")

NETGSM_API_HOST: Final = "api.netgsm.com.tr"
NETGSM_API_PORT: Final = 443
NETGSM_OTP_URL: Final = f"https://{NETGSM_API_HOST}/sms/rest/v2/otp"
#: KV v2 path under ``secret/``, inside the ``intake-api`` policy's grant.
NETGSM_KV_PATH: Final = "api/netgsm"
#: The same document's fourth field on the synthetic host: the owner's test
#: numbers (intake_api.sms_recipients), synced from SSM.
TEST_ALLOWLIST_FIELD: Final = "test_allowlist"
SMS_EGRESS: Final = EgressContext(purpose=EgressPurpose.SMS_OTP_DELIVERY, data_class=DataClass.PHI)
DEFAULT_TIMEOUT: Final = httpx.Timeout(8.0, connect=3.0)
#: The INT-329 wording (siz register, -iniz for instructional prose) folded to
#: ASCII, because the OTP product refuses Turkish letters. No brand name: the
#: sender header already names the app.
SMS_TEMPLATE: Final = "Dogrulama kodunuz: {code}. Bu kodu kimseyle paylasmayiniz."
#: One segment with an alphanumeric sender, per the documentation's code 20.
MAX_MESSAGE_LENGTH: Final = 155

_FIELDS: Final = ("usercode", "password", "msgheader")
_USERCODE = re.compile(r"[0-9]{10}")
#: 3 to 11 characters (the documented sender length), ASCII, no edge spaces
_MSGHEADER = re.compile(r"(?=.{3,11}\Z)[A-Za-z0-9](?:[A-Za-z0-9 .-]*[A-Za-z0-9])?")
_TR_MOBILE_E164 = re.compile(r"\+90(5[0-9]{9})")
_CODE = re.compile(r"[0-9]{4,10}")
#: Both documented job id forms are digit strings (the 2025 update lengthened them).
_JOBID = re.compile(r"[0-9]{1,64}")
_VENDOR_CODE = re.compile(r"[0-9]{1,3}")
#: The documented success code.
SUCCESS_CODE: Final = "00"
#: Where this endpoint's success puts the job id: ``jobid`` in the
#: documentation's REST v2 sample, ``jobId`` in Netgsm's JS SDK (its
#: ``OtpSmsResponse`` type and its integration test against this endpoint).
#: The XML OTP endpoint's ``jobID`` is not this endpoint's (INT-576 evidence).
JOB_ID_KEYS: Final = ("jobid", "jobId")


class NetgsmRefusal(StrEnum):
    """Why Netgsm, or this adapter on its behalf, refused a code. A closed,
    id-shaped vocabulary: safe in a log line and as a metric label."""

    MESSAGE_REFUSED = "message_refused"
    CREDENTIALS_REFUSED = "credentials_refused"
    SENDER_REFUSED = "sender_refused"
    NUMBER_REFUSED = "number_refused"
    OTP_PACKAGE_MISSING = "otp_package_missing"
    PARAMETERS_REFUSED = "parameters_refused"
    SEND_LIMIT_EXCEEDED = "send_limit_exceeded"
    VENDOR_SYSTEM_ERROR = "vendor_system_error"
    UNKNOWN_VENDOR_CODE = "unknown_vendor_code"
    UNPARSEABLE_RESPONSE = "unparseable_response"
    ACCEPTED_WITHOUT_JOB_ID = "accepted_without_job_id"
    NOT_A_TR_MOBILE = "not_a_tr_mobile"
    CODE_NOT_SENDABLE = "code_not_sendable"
    NOT_ON_TEST_ALLOWLIST = "not_on_test_allowlist"


#: The documented OTP error codes, and nothing else: the documentation's OTP SMS
#: tables, Netgsm's JS SDK (adds 101) and its PHP OTP package (adds 80).
VENDOR_CODE_REFUSALS: Final[Mapping[str, NetgsmRefusal]] = {
    "20": NetgsmRefusal.MESSAGE_REFUSED,
    "30": NetgsmRefusal.CREDENTIALS_REFUSED,
    "40": NetgsmRefusal.SENDER_REFUSED,
    "41": NetgsmRefusal.SENDER_REFUSED,
    "50": NetgsmRefusal.NUMBER_REFUSED,
    "51": NetgsmRefusal.NUMBER_REFUSED,
    "52": NetgsmRefusal.NUMBER_REFUSED,
    "60": NetgsmRefusal.OTP_PACKAGE_MISSING,
    "70": NetgsmRefusal.PARAMETERS_REFUSED,
    "80": NetgsmRefusal.SEND_LIMIT_EXCEEDED,
    "100": NetgsmRefusal.VENDOR_SYSTEM_ERROR,
    "101": NetgsmRefusal.VENDOR_SYSTEM_ERROR,
}

_PORT_REASON: Final[Mapping[NetgsmRefusal, OtpDeliveryFailure]] = {
    NetgsmRefusal.CREDENTIALS_REFUSED: OtpDeliveryFailure.AUTH_FAILED,
    NetgsmRefusal.SEND_LIMIT_EXCEEDED: OtpDeliveryFailure.RATE_LIMITED,
    NetgsmRefusal.VENDOR_SYSTEM_ERROR: OtpDeliveryFailure.VENDOR_UNAVAILABLE,
}

#: Every value the counter's ``outcome`` label can take.
DELIVERY_OUTCOMES: Final = frozenset(
    {"accepted"} | {r.value for r in NetgsmRefusal} | {r.value for r in OtpDeliveryFailure}
)

OTP_SMS_DELIVERY_TOTAL: Final = Counter(
    "otp_sms_delivery_total",
    "OTP SMS delivery attempts by vendor and outcome (accepted, or why not).",
    ("vendor", "outcome"),
)


class NetgsmConfigError(ValueError):
    """The vault document is missing a value or holds a malformed one. The
    message names fields, never values."""


class NetgsmDeliveryError(OtpDeliveryError):
    """An :class:`OtpDeliveryError` that also says which Netgsm refusal it was,
    when it was one, and, for a 2xx it could not read, the answer's structure.
    The route sees the port's error and answers one generic 503; the refusal
    is for the log line and the counter, the shape for the owner's diagnostic."""

    def __init__(
        self,
        reason: OtpDeliveryFailure,
        *,
        refusal: NetgsmRefusal | None = None,
        status_code: int | None = None,
        vendor_code: int | None = None,
        shape: AnswerShape | None = None,
    ) -> None:
        super().__init__(reason, status_code=status_code, vendor_code=vendor_code)
        self.refusal = refusal
        self.shape = shape

    @property
    def outcome(self) -> str:
        return self.refusal.value if self.refusal is not None else self.reason.value


@final
@dataclass(frozen=True)
class NetgsmReceipt(DeliveryReceipt):
    """The port's receipt, with the accepted answer's structure (never a value)."""

    shape: AnswerShape


class KvSecrets(Protocol):
    """The slice of :class:`intake_platform.secrets.SecretsProvider` used here."""

    def get_kv(self, path: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class NetgsmCredentials:
    """The subscriber number, the API sub-user's password and the approved
    sender name (message header)."""

    usercode: str
    password: str = field(repr=False)
    msgheader: str

    @classmethod
    def parse(cls, document: Mapping[str, object]) -> NetgsmCredentials:
        """Values are taken exactly as stored, never trimmed: a sender name
        with an edge space is a different, unapproved sender. The shapes are
        the ones infra/staging/netgsm_secrets.sh checks before it writes."""
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
                values[name] = raw
        if missing:
            raise NetgsmConfigError(
                f"OpenBao secret/{NETGSM_KV_PATH} is missing {', '.join(missing)}"
            )
        if "usercode" in values and not _USERCODE.fullmatch(values["usercode"]):
            malformed.append("usercode")
        if "msgheader" in values and not _MSGHEADER.fullmatch(values["msgheader"]):
            malformed.append("msgheader")
        if malformed:
            names = ", ".join(sorted(set(malformed)))
            raise NetgsmConfigError(f"OpenBao secret/{NETGSM_KV_PATH} has malformed {names}")
        return cls(values["usercode"], values["password"], values["msgheader"])


@final
@dataclass(frozen=True, slots=True)
class NetgsmOtpRequest:
    """The only thing the adapter puts on the wire."""

    msgheader: str
    msg: str = field(repr=False)
    no: str = field(repr=False)

    def as_wire(self) -> dict[str, str]:
        """Exactly the documented fields. Enumerated by hand rather than
        reflected, so a field added above cannot silently join the payload."""
        return {"msgheader": self.msgheader, "msg": self.msg, "no": self.no}


class _Unsendable(ValueError):
    """Refused before the wire. Carries the refusal and nothing else."""

    def __init__(self, refusal: NetgsmRefusal) -> None:
        super().__init__(refusal.value)
        self.refusal = refusal


def seal_otp_request(
    credentials: NetgsmCredentials, *, phone_e164: str, code: str
) -> NetgsmOtpRequest:
    """Build the wire request, or refuse what the OTP product cannot carry."""
    number = _TR_MOBILE_E164.fullmatch(phone_e164)
    if number is None:
        raise _Unsendable(NetgsmRefusal.NOT_A_TR_MOBILE)
    if not (code.isascii() and _CODE.fullmatch(code)):
        raise _Unsendable(NetgsmRefusal.CODE_NOT_SENDABLE)
    # ASCII and one segment for every code of 4 to 10 digits: a test holds the
    # template to both, so no runtime branch is needed for it
    message = SMS_TEMPLATE.format(code=code)
    return NetgsmOtpRequest(msgheader=credentials.msgheader, msg=message, no=number.group(1))


def _json_object(response: httpx.Response) -> dict[str, Any] | None:
    try:
        body = response.json()
    except (ValueError, RecursionError):
        # RecursionError: JSON nested deeper than the decoder goes
        return None
    return body if isinstance(body, dict) else None


def _vendor_code(body: Mapping[str, Any] | None) -> str | None:
    """The body's ``code`` as a digit string ("00", "30"), or None."""
    if body is None:
        return None
    raw = body.get("code")
    if isinstance(raw, int) and not isinstance(raw, bool):
        raw = f"{raw:02d}"
    return raw if isinstance(raw, str) and _VENDOR_CODE.fullmatch(raw) else None


def _job_id(body: Mapping[str, Any] | None) -> str | None:
    """The job id when exactly one documented key holds a digit string."""
    if body is None:
        return None
    values = [body[key] for key in JOB_ID_KEYS if key in body]
    if len(values) != 1:
        return None
    [value] = values
    return value if isinstance(value, str) and _JOBID.fullmatch(value) else None


def _http_reason(status: int) -> OtpDeliveryFailure:
    if status in (401, 403):
        return OtpDeliveryFailure.AUTH_FAILED
    if status == 429:
        return OtpDeliveryFailure.RATE_LIMITED
    if status >= 500:
        return OtpDeliveryFailure.VENDOR_UNAVAILABLE
    return OtpDeliveryFailure.REJECTED


class NetgsmSmsDeliveryAdapter:
    """The OTP tier's SMS adapter over Netgsm's OTP SMS API (INT-528)."""

    def __init__(
        self,
        credentials: NetgsmCredentials,
        *,
        egress: EgressPolicy,
        inner: httpx.AsyncBaseTransport | None = None,
        transfer_log: TransferLog | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        recipients: RecipientGate = ADMIT_ALL,
        proxy: str | None = None,
    ) -> None:
        self._credentials = credentials
        self._policy = egress
        self._inner = inner
        self._transfer_log = transfer_log
        self._timeout = timeout
        self._recipients = recipients
        # ADR-042: the synthetic host's SMS-only proxy, or None (resolve and
        # pin in process). intake_platform.egress admits no other proxy here.
        self._proxy = proxy

    @property
    def recipients(self) -> RecipientGate:
        """Who this adapter may send to (the synthetic host's test list)."""
        return self._recipients

    @property
    def proxy(self) -> str | None:
        """The SMS-only forward proxy this adapter rides, if any (ADR-042)."""
        return self._proxy

    async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
        refusal: NetgsmRefusal | None = None
        try:
            request = seal_otp_request(self._credentials, phone_e164=phone_e164, code=code)
        except _Unsendable as exc:
            refusal = exc.refusal
        if refusal is None and not self._recipients.admits(phone_e164):
            refusal = NetgsmRefusal.NOT_ON_TEST_ALLOWLIST
        if refusal is not None:
            raise self._failed(NetgsmDeliveryError(OtpDeliveryFailure.REJECTED, refusal=refusal))
        auth = (self._credentials.usercode, self._credentials.password)
        response: httpx.Response | None = None
        reason: OtpDeliveryFailure | None = None
        async with guarded_async_client(
            self._policy,
            SMS_EGRESS,
            inner=self._inner,
            transfer_log=self._transfer_log,
            proxy=self._proxy,
            timeout=self._timeout,
        ) as client:
            try:
                response = await client.post(NETGSM_OTP_URL, json=request.as_wire(), auth=auth)
            except EgressDenied:
                reason = OtpDeliveryFailure.EGRESS_DENIED
            except httpx.TimeoutException:
                reason = OtpDeliveryFailure.TIMEOUT
            except httpx.TransportError:
                reason = OtpDeliveryFailure.UNREACHABLE
        # Raised here, after the except blocks have closed, so nothing is
        # chained: the transport error holds the request and its body.
        if response is None:
            raise self._failed(NetgsmDeliveryError(reason or OtpDeliveryFailure.UNREACHABLE))
        return self._receipt(response)

    def _receipt(self, response: httpx.Response) -> NetgsmReceipt:
        status = response.status_code
        body = _json_object(response)
        code = _vendor_code(body)
        # the vendor's code as a number, unless it is absent or the success code
        vendor_code = int(code) if code is not None and code != SUCCESS_CODE else None
        refusal = VENDOR_CODE_REFUSALS.get(code) if code is not None else None
        if refusal is not None:
            raise self._failed(
                NetgsmDeliveryError(
                    _PORT_REASON.get(refusal, OtpDeliveryFailure.REJECTED),
                    refusal=refusal,
                    status_code=status,
                    vendor_code=vendor_code,
                )
            )
        if not 200 <= status < 300:
            # an undocumented code with a refusing status is a plain rejection
            undocumented = vendor_code is not None
            raise self._failed(
                NetgsmDeliveryError(
                    OtpDeliveryFailure.REJECTED if undocumented else _http_reason(status),
                    refusal=NetgsmRefusal.UNKNOWN_VENDOR_CODE if undocumented else None,
                    status_code=status,
                    vendor_code=vendor_code,
                )
            )
        # A 2xx. Anything but the documented success is unprovable: no receipt
        # that cannot be tied to a vendor job, and a port reason that is not
        # retryable, because Netgsm may already have sent the code (it had).
        shape = answer_shape(response)
        jobid = _job_id(body)
        if code == SUCCESS_CODE and jobid is not None:
            OTP_SMS_DELIVERY_TOTAL.labels(vendor="netgsm", outcome="accepted").inc()
            logger.info(
                "otp delivery accepted (netgsm) delivery_id=%s http_status=%s", jobid, status
            )
            return NetgsmReceipt(delivery_id=jobid, shape=shape)
        if code is None:
            unreadable = NetgsmRefusal.UNPARSEABLE_RESPONSE
        elif code == SUCCESS_CODE:
            unreadable = NetgsmRefusal.ACCEPTED_WITHOUT_JOB_ID
        else:
            unreadable = NetgsmRefusal.UNKNOWN_VENDOR_CODE
        raise self._failed(
            NetgsmDeliveryError(
                OtpDeliveryFailure.MALFORMED_RESPONSE,
                refusal=unreadable,
                status_code=status,
                vendor_code=vendor_code,
                shape=shape,
            )
        )

    @staticmethod
    def _failed(error: NetgsmDeliveryError) -> NetgsmDeliveryError:
        OTP_SMS_DELIVERY_TOTAL.labels(vendor="netgsm", outcome=error.outcome).inc()
        logger.warning(
            "otp delivery failed (netgsm) refusal=%s reason=%s http_status=%s vendor_code=%s",
            error.refusal.value if error.refusal is not None else "-",
            error.reason,
            error.status_code if error.status_code is not None else "-",
            error.vendor_code if error.vendor_code is not None else "-",
        )
        return error


# --- wiring -----------------------------------------------------------------------------


def _sms_egress_policy(path: Path) -> EgressPolicy | None:
    """The PHI-tier policy, or None when it cannot admit Netgsm. The check is
    the pure one (no DNS): whether a row exists for this purpose and host, and
    whether the runtime PHI gate is open."""
    try:
        allowlist = load_allowlist(path)
        assert_dev_only_vendors(allowlist)
    except (OSError, ValueError, EgressConfigError, yaml.YAMLError) as exc:
        logger.warning(
            "otp tier unconfigured outside dev: the egress allow-list is unusable (%s)",
            type(exc).__name__,
        )
        return None
    policy = EgressPolicy.for_tier(allowlist, "phi_path")
    decision = policy.check(NETGSM_API_HOST, NETGSM_API_PORT, SMS_EGRESS)
    if not decision.allowed:
        logger.warning(
            "otp tier unconfigured outside dev: the egress policy refuses the SMS vendor "
            "until the owner applies the Netgsm row (%s)",
            decision.reason,
        )
        return None
    return policy


def _document_from_vault(secrets: KvSecrets | None) -> dict[str, Any] | None:
    try:
        vault = secrets if secrets is not None else SecretsProvider.from_env()
        return vault.get_kv(NETGSM_KV_PATH)
    except (SecretsBootError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "otp tier unconfigured outside dev: the SMS vendor credentials are not "
            "readable from OpenBao (%s)",
            type(exc).__name__,
        )
    return None


def _credentials(document: Mapping[str, object]) -> NetgsmCredentials | None:
    try:
        return NetgsmCredentials.parse(document)
    except NetgsmConfigError as exc:
        logger.warning("otp tier unconfigured outside dev: %s", exc)
    return None


def _recipients(settings: ApiSettings, document: Mapping[str, object]) -> RecipientGate:
    """The synthetic host sends only to the owner's test numbers (INT-528);
    without a usable list it sends to nobody. Elsewhere there is no list."""
    if settings.environment not in SYNTHETIC_ENVIRONMENTS:
        return ADMIT_ALL
    allowlist = SmsTestAllowlist.parse(document.get(TEST_ALLOWLIST_FIELD))
    if allowlist.count == 0:
        logger.warning(
            "otp tier on the synthetic host: the SMS test allow-list is empty or "
            "unreadable, so every number is refused (secret/%s %s)",
            NETGSM_KV_PATH,
            TEST_ALLOWLIST_FIELD,
        )
    else:
        logger.info("otp tier on the synthetic host: %s", allowlist)
    return allowlist


def otp_delivery_from_settings(
    settings: ApiSettings, secrets: KvSecrets | None = None
) -> OtpDeliveryAdapter | None:
    """The OTP tier's delivery adapter, or None, which leaves the tier at 503.

    Dev: the dev event logger, unchanged. Outside dev: Netgsm when the egress
    policy admits it AND OpenBao holds all three values, and nothing otherwise.
    The dev logger is never wired outside dev (INT-325), and nothing wires
    Twilio. The egress check runs first, so a vendor the policy refuses never
    has its secret pulled into memory. On the synthetic host the adapter sends
    only to the test allow-list, and rides the SMS-only proxy when
    ``INTAKE_SMS_EGRESS_PROXY_URL`` names it (ADR-042).
    """
    if settings.dev_tier_expected:
        return DevLogDeliveryAdapter()
    policy = _sms_egress_policy(settings.egress_allowlist_path)
    if policy is None:
        return None
    proxy = settings.sms_egress_proxy_url
    if proxy is not None and proxy != DEDICATED_PERSONAL_PROXIES[SMS_EGRESS.purpose]:
        logger.warning(
            "otp tier unconfigured outside dev: the SMS egress proxy is not the dedicated "
            "one ADR-042 admits"
        )
        return None
    document = _document_from_vault(secrets)
    if document is None:
        return None
    credentials = _credentials(document)
    if credentials is None:
        return None
    return NetgsmSmsDeliveryAdapter(
        credentials,
        egress=policy,
        recipients=_recipients(settings, document),
        proxy=proxy,
    )
