"""Doctor Link primitives (INT-150; files/10 §2 clinicians; files/02 §2b, §376).

The pieces a Doctor Link is made of, kept out of the API so the rules they
encode have one home and one test:

- the **token**: 128 bits from :mod:`secrets`, handed to the patient once and
  never stored in clear anywhere (invariant 6 — a token is a credential). What
  persists is :func:`token_fingerprint`, a SHA-256 digest; comparison is
  :func:`token_matches`, which is constant-time. A digest is enough here
  precisely because the input is 128 uniform bits: there is no dictionary to
  run against it, which is why no keyed construction (the OTP's ``code_digest``
  shape) is needed for a token and IS needed for a six-digit code.
- the **expiry anchor**: files/02 §2b pins Doctor Link expiry to
  ``visit_datetime + 72 h`` and says in terms that ``issue_time + 72 h`` is the
  wrong clock — *"the single most likely cause of 'the doctor couldn't see it'
  at P1"*. This repo records a visit **date** and no time of day (the
  ``visit.date`` slot, INT-134), so the exact datetime cannot be computed.
  :func:`link_expires_at` therefore anchors to the **start** of the visit date
  in Türkiye and adds 72 h. That direction is deliberate: the start of the day
  is never later than the appointment, so the computed expiry is never later
  than the spec's value — it errs strictly towards LESS exposure — while still
  leaving at least 48 h after any appointment on that date. An hour of the day
  is not invented anywhere.
- the **watermark**: files/10 §2 wants the recipient and the timestamp on
  every rendered view and download. :class:`Watermark` composes exactly those,
  plus the opaque link reference that ties a leaked page back to one grant.
  It carries NOTHING derived from the request — no IP, no user agent, no
  device fingerprint — because a watermark that identified the viewer beyond
  what the patient's consent covers would be new personal data collected for
  a control's convenience.

Nothing here touches a database, a clock it did not receive, or a log.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = [
    "DEFAULT_VIEW_LIMIT",
    "DOCTOR_LINK_TTL",
    "MAX_RECIPIENT_CHARS",
    "TOKEN_ENTROPY_BITS",
    "TZ_NAME",
    "RecipientInvalidError",
    "TimezoneUnavailableError",
    "Watermark",
    "link_expires_at",
    "new_token",
    "normalise_recipient",
    "token_fingerprint",
    "token_matches",
]

#: files/10 §2: "128-bit random token". Written as the bit count because that
#: is what the spec states; the byte count follows from it.
TOKEN_ENTROPY_BITS = 128
_TOKEN_BYTES = TOKEN_ENTROPY_BITS // 8

#: files/10 §2 / files/02 §2b: "expiry (default 72 h)", anchored on the visit.
DOCTOR_LINK_TTL = timedelta(hours=72)

#: files/10 §2 names a "view limit" and no number, so this is an engineering
#: default and is labelled as one (the INT-131 precedent for RESEND_COOLDOWN_S
#: and DEVICE_LIMIT_PER_HOUR). Ten openings, because the failure this control
#: must not cause is the one files/02 §2b already names — a clinician who
#: cannot see the note — and a clinician who opens the note before the visit,
#: during it and once afterwards, on a browser that reloads, is ordinary use
#: rather than abuse. The patient may lower it per link; nothing raises it.
DEFAULT_VIEW_LIMIT = 10

#: Türkiye's civil time. The visit date is a Turkish calendar date, so the
#: start of that date is a Turkish instant; anchoring in UTC would silently
#: shift the whole window by the offset.
TZ_NAME = "Europe/Istanbul"

#: The recipient is patient-typed. Bounded, single-line, and rendered only
#: into the watermark of the view that recipient opened.
MAX_RECIPIENT_CHARS = 120

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class RecipientInvalidError(ValueError):
    """The recipient label is empty, over-long, or carries control characters.

    Refused rather than sanitised: a watermark is evidence of who a document
    was released to, and silently rewriting it changes what the evidence says.
    The message names the rule, never the value (invariant 6).
    """


class TimezoneUnavailableError(RuntimeError):
    """The IANA zone this computation needs is not installed.

    Raised rather than falling back to UTC: a fallback would move every Doctor
    Link expiry by three hours without anything saying so, which is exactly the
    class of silent clock error files/02 §2b exists to stop.
    """


def new_token() -> str:
    """A fresh 128-bit link token, URL-safe. Returned to the patient once."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def token_fingerprint(token: str) -> str:
    """What is persisted: SHA-256 hex of the token. Never the token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(candidate: str, stored_fingerprint: str) -> bool:
    """Constant-time check of a presented token against a stored fingerprint."""
    return hmac.compare_digest(token_fingerprint(candidate), stored_fingerprint)


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(TZ_NAME)
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - platform dependent
        raise TimezoneUnavailableError(
            f"{TZ_NAME} is not installed; the Doctor Link expiry anchor refuses to "
            "fall back to UTC (files/02 §2b)"
        ) from exc


def link_expires_at(visit_date: dt.date) -> dt.datetime:
    """``start of the visit date in Türkiye + 72 h``, as an aware UTC instant.

    See the module docstring for why the anchor is the start of the day: the
    schema records a date and no time, and the start of the day is the only
    anchor that cannot land later than the appointment it is protecting.
    """
    start = dt.datetime.combine(visit_date, dt.time.min, tzinfo=_tz())
    return (start + DOCTOR_LINK_TTL).astimezone(UTC)


def normalise_recipient(raw: str) -> str:
    """Validate the patient's recipient label for watermark rendering."""
    label = raw.strip()
    if not label:
        raise RecipientInvalidError("recipient label must not be empty")
    if len(label) > MAX_RECIPIENT_CHARS:
        raise RecipientInvalidError(
            f"recipient label must be at most {MAX_RECIPIENT_CHARS} characters"
        )
    if _CONTROL.search(label):
        raise RecipientInvalidError("recipient label must not carry control characters")
    return label


@dataclass(frozen=True, slots=True)
class Watermark:
    """What a Doctor Link view and its PDF are stamped with (files/10 §2).

    Three fields and no fourth. ``recipient`` is the label the PATIENT chose
    when they issued the link — not anything observed about whoever opened it,
    which is what keeps the stamp inside the consent the patient gave.
    ``link_ref`` is the opaque grant id, so a leaked page names the grant to
    revoke without naming the patient.
    """

    recipient: str
    viewed_at_utc: str
    link_ref: str

    def render(self) -> str:
        """The single line handed to ``render_document_pdf(watermark=...)``."""
        return f"{self.recipient} · {self.viewed_at_utc} · {self.link_ref}"

    @classmethod
    def compose(cls, *, recipient: str, viewed_at: dt.datetime, link_id: object) -> Watermark:
        """Build the stamp from the grant and the instant of THIS view."""
        return cls(
            recipient=normalise_recipient(recipient),
            viewed_at_utc=viewed_at.astimezone(UTC).replace(microsecond=0).isoformat(),
            link_ref=f"doctor_link:{link_id}",
        )
