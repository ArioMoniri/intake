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
  at P1"*. Since INT-306 a visit records a time of day where one is known
  (:class:`~clinical_schemas.visit_time.VisitSchedule`), so
  :func:`link_expires_at` applies the spec's own rule unapproximated whenever
  the schedule carries one. Where it does not — an honest recorded state, not a
  missing value — INT-150's anchor stays as the documented **fallback**: the
  start of the visit date in Türkiye, plus 72 h. That direction is what makes
  the fallback safe rather than merely different — the start of the day is
  never later than the appointment, so the fallback expiry is never later than
  the spec's value; it errs strictly towards LESS exposure while still leaving
  at least 48 h after any appointment on that date. An hour of the day is not
  invented anywhere, and taking a ``VisitSchedule`` rather than a bare date is
  what makes the caller say which of the two rules it is asking for.
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

from clinical_schemas.visit_time import VisitSchedule

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
    "visit_instant",
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


def visit_instant(schedule: VisitSchedule) -> dt.datetime:
    """The visit's instant in Türkiye, as an aware UTC instant.

    The appointment itself where the schedule records an hour; otherwise the
    START of the visit date — never later than the appointment, so every clock
    anchored here (the Doctor Link expiry, the T-24h confirm, the INT-407
    ``missed`` guard) can only run early, never late.

    The zone is applied here and only here: a :class:`VisitTime` is a civil
    time in the visit's own calendar, so combining it with the visit's date
    under ``Europe/Istanbul`` is the one place the two halves become an instant.
    """
    anchor = schedule.time.at if schedule.time is not None else dt.time.min
    return dt.datetime.combine(schedule.date, anchor, tzinfo=_tz()).astimezone(UTC)


def link_expires_at(schedule: VisitSchedule) -> dt.datetime:
    """``the visit's instant in Türkiye + 72 h``, as an aware UTC instant.

    files/02 §2b's rule, applied to the appointment itself where the schedule
    records one. Where it does not, the anchor falls back to the START of the
    visit date — never later than the appointment, therefore never later than
    the spec's value, so the fallback can only shorten the window and never
    lengthen it. The module docstring carries the reasoning;
    ``test_the_fallback_is_never_later_than_the_true_appointment`` in
    ``tests/clinician/test_doctor_link.py`` asserts that direction for every
    minute of the day. The instant itself is :func:`visit_instant`.
    """
    return visit_instant(schedule) + DOCTOR_LINK_TTL


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
