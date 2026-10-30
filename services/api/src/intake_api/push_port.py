"""INT-583 — the push gateway port: what the sign-in notice hands a push provider.

Owner decision D35 (28 Oct 2026, files/00_STATE.md §3): a sign-in from a new
device is told to the patient by PUSH to the devices already signed in, never by
SMS, because a SIM swap would hand an SMS notice to the attacker.

The port is provider-agnostic (CLAUDE.md "all external calls go through
gateways with adapter interfaces"). Its one adapter is direct APNs
(``intake_api.push_apns``); tests replay recorded APNs answers through it and
never call Apple.

What crosses it is a :class:`PushAlert` built from constants (the tr copy in
``sign_in_notice.tr.json``) and one device token. A failure is a closed,
id-shaped :class:`PushFailure` and never a vendor body, a token or a
credential (invariant 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol, final

__all__ = [
    "PUSH_FAILURES_THAT_DROP_THE_TOKEN",
    "PushAlert",
    "PushDeliveryError",
    "PushFailure",
    "PushGateway",
    "PushReceipt",
    "PushUnconfigured",
]


class PushFailure(StrEnum):
    """Why one push did not reach the provider's acceptance. Safe as a metric
    label and in a log line."""

    EGRESS_DENIED = "egress_denied"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    REJECTED = "rejected"
    #: the provider says the token is no longer a device (APNs 410, or 400
    #: BadDeviceToken): the registration is dropped, never retried
    TOKEN_GONE = "token_gone"  # noqa: S105 — a failure label, not a credential
    VENDOR_UNAVAILABLE = "vendor_unavailable"
    MALFORMED_RESPONSE = "malformed_response"


#: The failures after which a token is useless: keeping it would only send
#: the next notice into the same refusal.
PUSH_FAILURES_THAT_DROP_THE_TOKEN: Final = frozenset({PushFailure.TOKEN_GONE})


class PushUnconfigured(StrEnum):
    """Why no push channel was wired. The notice then fails closed: no push is
    attempted, the sign-in still counts and is audited, and this reason is in
    the log line and the ``push_channel_unconfigured`` gauge."""

    NO_CREDENTIALS = "no_credentials"
    MALFORMED_CREDENTIALS = "malformed_credentials"
    EGRESS_REFUSED = "egress_refused"
    HTTP2_UNAVAILABLE = "http2_unavailable"
    #: on the synthetic host the dedicated push proxy is the only route out,
    #: and it is not named, or a proxy other than it is named
    NO_ROUTE = "no_route"


@final
@dataclass(frozen=True, slots=True)
class PushAlert:
    """The only content a push carries: a title, a body and a collapse id,
    each a committed constant. There is no field for a visit, a branch, a link
    or a name."""

    title: str
    body: str
    collapse_id: str


@final
@dataclass(frozen=True, slots=True)
class PushReceipt:
    """The provider's handle for an accepted push (APNs ``apns-id``)."""

    push_id: str


class PushDeliveryError(Exception):
    """One push was not accepted. Carries the reason and the HTTP status only."""

    def __init__(self, reason: PushFailure, *, status_code: int | None = None) -> None:
        self.reason = reason
        self.status_code = status_code
        super().__init__(f"push not accepted: {reason} (status {status_code or '-'})")


class PushGateway(Protocol):
    """The push seam. ``send`` returns the provider's receipt or raises
    :class:`PushDeliveryError`; it never retries (a retried notice is a second
    notice on the patient's lock screen)."""

    async def send(self, *, device_token: str, alert: PushAlert) -> PushReceipt: ...
