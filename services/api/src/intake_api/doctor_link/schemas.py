"""INT-150 — the Doctor Link wire bodies.

Two rules the shapes encode:

- **The token appears in exactly one response**, :class:`DoctorLinkIssued`,
  and in exactly one request field, on POST bodies. There is no query
  parameter and no path parameter carrying it anywhere in this package, so a
  credential cannot reach an access log, a Referer header or a browser history
  entry (CLAUDE.md invariant 6).
- **The clinician's view carries a stamp and no viewer identity.** The
  watermark fields come from the grant the patient issued plus the instant of
  this opening — never from the request — so the stamp cannot become a way to
  identify the reader beyond what the patient consented to.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from intake_platform.doctor_link import DEFAULT_VIEW_LIMIT
from pydantic import BaseModel, ConfigDict, Field

from intake_api.schemas import NoteSection

__all__ = [
    "AccessLogEntryOut",
    "DoctorLinkCreate",
    "DoctorLinkIssued",
    "DoctorLinkOtpOut",
    "DoctorLinkOut",
    "DoctorLinkView",
    "RedeemBody",
    "TokenBody",
]


class DoctorLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient: str = Field(max_length=200)
    #: The patient may tighten the openings budget, never widen it.
    view_limit: int | None = Field(default=None, ge=1, le=DEFAULT_VIEW_LIMIT)


class DoctorLinkOut(BaseModel):
    """A grant as the PATIENT sees it. No token and no fingerprint: the token
    is shown once, at issue, and there is nothing to show afterwards."""

    link_id: uuid.UUID
    recipient: str
    expires_at: datetime
    view_limit: int
    views_used: int
    #: The patient actively revoked it.
    revoked: bool
    #: It can no longer be opened for ANY reason — revoked, past its expiry,
    #: or out of openings. Two fields rather than one because "I stopped this"
    #: and "this ran out" are different facts to the person who shared it.
    spent: bool


class DoctorLinkIssued(DoctorLinkOut):
    """The one response that carries the token, once."""

    token: str


class DoctorLinkOtpOut(BaseModel):
    code: str
    expires_in_s: int
    resend_after_s: int


class TokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=128)


class RedeemBody(TokenBody):
    code: str = Field(min_length=4, max_length=12)


class DoctorLinkView(BaseModel):
    """What the clinician gets: the shared sections and the stamp."""

    sections: list[NoteSection]
    watermark_recipient: str
    watermark_viewed_at_utc: str
    watermark_link_ref: str
    watermark_line: str
    view_index: int
    views_remaining: int
    expires_at: datetime
    proxy_reported: bool
    third_party_present: bool


class AccessLogEntryOut(BaseModel):
    seq: int
    occurred_at_utc: str
    category: str
    accessor_role: str
    resource_ref: str
    entry_hash: str
