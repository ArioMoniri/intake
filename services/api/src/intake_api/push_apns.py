"""INT-583 — the APNs adapter behind the push gateway port (D35).

**Why direct APNs.** The notice goes to iOS devices only: Android cannot sign
in on a real mode until Play Integrity proves a key (HB-A3). Apple's push
service is the one processor no iOS push can avoid; a relay (Expo's push
service, or any other) would be a second processor abroad holding the device
tokens, the notice and — for Expo — our APNs signing key. Direct APNs keeps the
key in OpenBao and the processor list at one.

**The wire contract** is Apple's documentation (retrieved 30 Oct 2026,
docs/evidence/INT-583.md): "Sending notification requests to APNs",
"Establishing a token-based connection to APNs" and "Handling notification
responses from APNs". The tests replay ``tests/fixtures/apns/responses.json``,
derived from those pages; nothing in a test reaches Apple.

- ``POST https://api.push.apple.com/3/device/<token>`` (``api.sandbox.push.apple.com``
  for development-signed builds) over HTTP/2, which APNs requires.
- ``authorization: bearer <provider token>``: an ES256 JWT, header
  ``{alg, kid}``, claims ``{iss: team id, iat}``, signed with the ``.p8`` key and
  renewed every :data:`PROVIDER_TOKEN_RENEW_S` (Apple: no more often than every
  20 minutes, no less often than every 60).
- ``apns-push-type: alert``, ``apns-topic: <bundle id>``, ``apns-priority: 10``,
  ``apns-expiration`` a day ahead, ``apns-collapse-id`` the notice's constant.
- Success is 200 with an ``apns-id``; an error is a JSON ``{"reason": ...}``.
  410 (``ExpiredToken``, ``Unregistered``) and 400 ``BadDeviceToken`` /
  ``DeviceTokenNotForTopic`` mean the token is gone: the registration is
  dropped and never retried, as Apple says.

**Posture**, the INT-528 adapter's:

- Over the INT-018 guarded async transport, declaring
  ``EgressPurpose.PUSH_SECURITY_NOTICE`` and ``DataClass.PHI`` (a device token
  addressed to a patient account of a clinical intake app says the person is
  one). It clears only a PHI-tier row naming D35, with the runtime gate open.
  No such row ships: the owner's patch adds it (``owner-583-apns-egress.patch``).
- Credentials from OpenBao only (invariant 14): ``secret/api/apns`` holds
  ``key_p8``, ``key_id`` and ``team_id``; ``infra/staging/apns_secrets.sh``
  writes it from SSM. No environment variable is read. A refusal names the
  field, never the value; the key never reaches ``repr``. The wiring is
  ``intake_api.push_wiring``.
- On the synthetic host every network is internal: the call rides the
  push-only forward proxy ``push-egress`` (ADR-042's pattern), the one proxy
  ``intake_platform.egress`` admits for this purpose. TLS and HTTP/2 run end
  to end through its CONNECT tunnel, so it sees ``host:443`` and nothing else.
- Logs and metrics carry no token, no key, no vendor text (invariant 6): the
  APNs reason is logged only when it is one of Apple's documented strings,
  httpx's own request line, whose URL holds the token, is redacted on the
  ``httpx`` logger before any handler sees it, and the ``hpack`` logger, which
  logs every header h2 compresses at DEBUG, is held at INFO.
- No retry: a second push is a second notice on the lock screen.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal

import httpx
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from intake_platform.egress import (
    DEDICATED_PERSONAL_PROXIES,
    DataClass,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    TransferLog,
    guarded_async_client,
)
from prometheus_client import Counter

from intake_api.device_sessions import APNS_TOKEN_SHAPE
from intake_api.push_port import (
    PushAlert,
    PushDeliveryError,
    PushFailure,
    PushReceipt,
)

__all__ = [
    "APNS_DOCUMENTED_REASONS",
    "APNS_HOSTS",
    "APNS_KV_PATH",
    "NOTICE_EXPIRY_S",
    "PROVIDER_TOKEN_RENEW_S",
    "PUSH_DELIVERY_TOTAL",
    "PUSH_EGRESS",
    "ApnsConfigError",
    "ApnsCredentials",
    "ApnsPushGateway",
    "apns_environment",
    "provider_token",
]

logger = logging.getLogger("intake_api.push_apns")

ApnsEnvironment = Literal["production", "sandbox"]

APNS_HOSTS: Final[Mapping[ApnsEnvironment, str]] = MappingProxyType(
    {"production": "api.push.apple.com", "sandbox": "api.sandbox.push.apple.com"}
)
APNS_PORT: Final = 443
#: KV v2 path under ``secret/``, inside the ``intake-api`` policy's read grant.
APNS_KV_PATH: Final = "api/apns"
PUSH_EGRESS: Final = EgressContext(
    purpose=EgressPurpose.PUSH_SECURITY_NOTICE, data_class=DataClass.PHI
)
DEFAULT_TIMEOUT: Final = httpx.Timeout(8.0, connect=3.0)
#: Renew the provider token after 50 minutes: inside Apple's 20-to-60 window.
PROVIDER_TOKEN_RENEW_S: Final = 50 * 60
#: APNs keeps an undelivered notice this long (a phone off overnight still
#: gets it). An engineering default (docs/evidence/INT-583.md).
NOTICE_EXPIRY_S: Final = 24 * 3600

_FIELDS: Final = ("key_p8", "key_id", "team_id")
#: Apple's Key ID and Team ID: ten upper-case letters and digits.
_APPLE_ID = re.compile(r"[A-Z0-9]{10}")
_APNS_ID = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)

#: Every reason string Apple documents, so a log line can name one without
#: ever echoing text the vendor chose (retrieved 30 Oct 2026).
APNS_DOCUMENTED_REASONS: Final = frozenset(
    {
        "BadCollapseId",
        "BadDeviceToken",
        "BadExpirationDate",
        "BadMessageId",
        "BadPriority",
        "BadTopic",
        "DeviceTokenNotForTopic",
        "DuplicateHeaders",
        "IdleTimeout",
        "InvalidPushType",
        "MissingDeviceToken",
        "MissingTopic",
        "PayloadEmpty",
        "TopicDisallowed",
        "BadCertificate",
        "BadCertificateEnvironment",
        "ExpiredProviderToken",
        "Forbidden",
        "InvalidProviderToken",
        "MissingProviderToken",
        "UnrelatedKeyIdInToken",
        "BadEnvironmentKeyIdInToken",
        "BadPath",
        "MethodNotAllowed",
        "ExpiredToken",
        "Unregistered",
        "PayloadTooLarge",
        "TooManyProviderTokenUpdates",
        "TooManyRequests",
        "InternalServerError",
        "ServiceUnavailable",
        "Shutdown",
    }
)
#: 400 reasons that mean the token itself will never work for this app.
_TOKEN_GONE_400: Final = frozenset({"BadDeviceToken", "DeviceTokenNotForTopic"})
#: 403 reasons after which a fresh provider token is worth minting.
_STALE_PROVIDER_TOKEN: Final = frozenset({"ExpiredProviderToken", "InvalidProviderToken"})

_DEVICE_PATH = re.compile(r"/3/device/[0-9A-Fa-f]+")


class _RedactDevicePath(logging.Filter):
    """httpx logs every request line at INFO with its full URL, and an APNs URL
    carries the device token in its path (invariant 6). This filter, on the
    ``httpx`` logger, rewrites that path before any handler sees the line."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "/3/device/" in message:
            record.msg = _DEVICE_PATH.sub("/3/device/<redacted>", message)
            record.args = None
        return True


def _install_redaction() -> None:
    target = logging.getLogger("httpx")
    if not any(isinstance(f, _RedactDevicePath) for f in target.filters):
        target.addFilter(_RedactDevicePath())
    # h2's header compressor logs every header it adds to its table at DEBUG,
    # the :path with the device token and the authorization bearer among them;
    # its loggers (hpack.*) inherit this level, so no such record is made
    logging.getLogger("hpack").setLevel(logging.INFO)


_install_redaction()

PUSH_DELIVERY_TOTAL: Final = Counter(
    "push_delivery_total",
    "Push sends by vendor and outcome (accepted, or why not).",
    ("vendor", "outcome"),
)


class ApnsConfigError(ValueError):
    """The vault document is missing a value or holds a malformed one. The
    message names fields, never values."""


@dataclass(frozen=True)
class ApnsCredentials:
    """The ``.p8`` signing key, its Key ID and the Team ID."""

    key_id: str
    team_id: str
    signing_key: ec.EllipticCurvePrivateKey = field(repr=False)

    @classmethod
    def parse(cls, document: Mapping[str, object]) -> ApnsCredentials:
        missing = [
            name
            for name in _FIELDS
            if not isinstance(document.get(name), str) or not str(document.get(name)).strip()
        ]
        if missing:
            raise ApnsConfigError(f"OpenBao secret/{APNS_KV_PATH} is missing {', '.join(missing)}")
        key_id, team_id = str(document["key_id"]), str(document["team_id"])
        malformed = [
            name
            for name, value in (("key_id", key_id), ("team_id", team_id))
            if not _APPLE_ID.fullmatch(value)
        ]
        signing_key = _signing_key(str(document["key_p8"]))
        if signing_key is None:
            malformed.append("key_p8")
        if malformed or signing_key is None:
            raise ApnsConfigError(
                f"OpenBao secret/{APNS_KV_PATH} has malformed {', '.join(sorted(malformed))}"
            )
        return cls(key_id=key_id, team_id=team_id, signing_key=signing_key)


def _signing_key(pem: str) -> ec.EllipticCurvePrivateKey | None:
    """The ``.p8`` file's key: PKCS#8 PEM, unencrypted, EC P-256 (ES256)."""
    try:
        key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    except (ValueError, TypeError, UnicodeEncodeError, UnsupportedAlgorithm):
        return None
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        return None
    return key


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def provider_token(credentials: ApnsCredentials, issued_at: int) -> str:
    """The ES256 JWT APNs authenticates a provider by."""
    header = {"alg": "ES256", "kid": credentials.key_id}
    claims = {"iss": credentials.team_id, "iat": issued_at}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(claims, separators=(",", ":")).encode())
    )
    der = credentials.signing_key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return f"{signing_input}.{_b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def apns_environment(app_attest_environment: str | None) -> ApnsEnvironment:
    """A development-signed build carries both App Attest's and APNs's
    development entitlement, from one provisioning profile, so the APNs host
    follows the App Attest environment: sandbox only for exactly
    ``development``, as App Attest itself reads it."""
    return "sandbox" if app_attest_environment == "development" else "production"


class ApnsPushGateway:
    """The push gateway over APNs (INT-583)."""

    def __init__(
        self,
        credentials: ApnsCredentials,
        *,
        topic: str,
        egress: EgressPolicy,
        environment: ApnsEnvironment = "production",
        inner: httpx.AsyncBaseTransport | None = None,
        transfer_log: TransferLog | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        now_fn: Callable[[], float] | None = None,
        proxy: str | None = None,
    ) -> None:
        # the synthetic host's push-only proxy (push-egress), or None (resolve
        # and pin in process); intake_platform.egress admits no other proxy,
        # and neither does this constructor
        if proxy is not None and proxy != DEDICATED_PERSONAL_PROXIES[PUSH_EGRESS.purpose]:
            raise ValueError("a push call rides only the dedicated push-egress proxy")
        self._credentials = credentials
        self._proxy = proxy
        self._topic = topic
        self._policy = egress
        self._host = APNS_HOSTS[environment]
        self._inner = inner
        self._transfer_log = transfer_log
        self._timeout = timeout
        self._now_fn = now_fn
        self._token: tuple[float, str] | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def proxy(self) -> str | None:
        """The push-only forward proxy this adapter rides, if any."""
        return self._proxy

    def _now(self) -> float:
        return self._now_fn() if self._now_fn is not None else time.time()

    def _bearer(self) -> str:
        now = self._now()
        if self._token is None or now - self._token[0] >= PROVIDER_TOKEN_RENEW_S:
            self._token = (now, provider_token(self._credentials, int(now)))
        return self._token[1]

    def _request(self, device_token: str, alert: PushAlert) -> tuple[str, dict[str, str], bytes]:
        """The one request this adapter makes. Every header and body field is
        enumerated here by hand."""
        headers = {
            "authorization": f"bearer {self._bearer()}",
            "apns-push-type": "alert",
            "apns-topic": self._topic,
            "apns-priority": "10",
            "apns-expiration": str(int(self._now()) + NOTICE_EXPIRY_S),
            "apns-collapse-id": alert.collapse_id,
            "content-type": "application/json",
        }
        payload = {"aps": {"alert": {"title": alert.title, "body": alert.body}, "sound": "default"}}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return f"https://{self._host}/3/device/{device_token}", headers, body

    async def send(self, *, device_token: str, alert: PushAlert) -> PushReceipt:
        if not APNS_TOKEN_SHAPE.fullmatch(device_token):
            raise self._failed(PushFailure.REJECTED, None, None)
        url, headers, body = self._request(device_token, alert)
        inner = (
            self._inner
            if self._inner is not None
            else httpx.AsyncHTTPTransport(http2=True, proxy=self._proxy)
        )
        response: httpx.Response | None = None
        reason: PushFailure | None = None
        async with guarded_async_client(
            self._policy,
            PUSH_EGRESS,
            inner=inner,
            transfer_log=self._transfer_log,
            proxy=self._proxy,
            timeout=self._timeout,
        ) as client:
            try:
                response = await client.post(url, headers=headers, content=body)
            except EgressDenied:
                reason = PushFailure.EGRESS_DENIED
            except httpx.TimeoutException:
                reason = PushFailure.TIMEOUT
            except httpx.TransportError:
                reason = PushFailure.UNREACHABLE
        # raised after the except blocks close: a transport error holds the
        # request, and the request holds the device token
        if response is None:
            raise self._failed(reason or PushFailure.UNREACHABLE, None, None)
        return self._receipt(response)

    def _receipt(self, response: httpx.Response) -> PushReceipt:
        status = response.status_code
        if status == 200:
            push_id = response.headers.get("apns-id", "")
            if not _APNS_ID.fullmatch(push_id):
                raise self._failed(PushFailure.MALFORMED_RESPONSE, status, None)
            PUSH_DELIVERY_TOTAL.labels(vendor="apns", outcome="accepted").inc()
            return PushReceipt(push_id=push_id.lower())
        apns_reason = _documented_reason(response)
        if apns_reason in _STALE_PROVIDER_TOKEN:
            self._token = None
        if status == 410 or (status == 400 and apns_reason in _TOKEN_GONE_400):
            failure = PushFailure.TOKEN_GONE
        elif status == 403:
            failure = PushFailure.AUTH_FAILED
        elif status == 429:
            failure = PushFailure.RATE_LIMITED
        elif status >= 500:
            failure = PushFailure.VENDOR_UNAVAILABLE
        elif 200 <= status < 300:
            failure = PushFailure.MALFORMED_RESPONSE
        else:
            failure = PushFailure.REJECTED
        raise self._failed(failure, status, apns_reason)

    @staticmethod
    def _failed(
        failure: PushFailure, status: int | None, apns_reason: str | None
    ) -> PushDeliveryError:
        PUSH_DELIVERY_TOTAL.labels(vendor="apns", outcome=failure.value).inc()
        logger.warning(
            "push not accepted (apns) reason=%s apns_reason=%s http_status=%s",
            failure.value,
            apns_reason or "-",
            status if status is not None else "-",
        )
        return PushDeliveryError(failure, status_code=status)


def _documented_reason(response: httpx.Response) -> str | None:
    """Apple's ``reason`` when it is one of the documented strings, else None."""
    try:
        body = response.json()
    except (ValueError, RecursionError):
        return None
    reason = body.get("reason") if isinstance(body, dict) else None
    return reason if isinstance(reason, str) and reason in APNS_DOCUMENTED_REASONS else None
