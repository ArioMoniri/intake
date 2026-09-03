"""INT-150 — the pieces both Doctor Link surfaces need.

Kept in one place so the patient's routes and the clinician's routes cannot
drift on the two things that must not fork: what "live" means for a grant, and
the fact that nothing in this package is indexable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import Response
from intake_platform.access_log import AccessorRole
from intake_platform.db.envelope_json import encrypted_field_from_json, encrypted_field_to_json
from intake_platform.db.models import DoctorLink

from intake_api.doctor_link.metrics import DoctorLinkEvent, record_event
from intake_api.doctor_link.schemas import DoctorLinkOut
from intake_api.doctor_link.service import DoctorLinkService
from intake_api.errors import (
    doctor_link_expired,
    doctor_link_revoked,
    doctor_link_unconfigured,
    doctor_link_view_limit,
)
from intake_api.state import ApiState

__all__ = [
    "NOINDEX",
    "accessor_role",
    "aware",
    "decrypt_recipient",
    "encrypt_recipient",
    "link_out",
    "no_index",
    "require_live",
    "service_of",
    "shared_ids",
]

#: files/10 §9 `doctor-link` row: "no indexing". Applied on every response of
#: both routers. It is set here rather than in the shared platform middleware
#: because the loop guardrails put ``intake_platform.security`` out of reach —
#: which is the right constraint: a per-surface header is reviewable in the
#: diff that adds the surface.
NOINDEX = "noindex, nofollow, noarchive, nosnippet, noimageindex"


def no_index(response: Response) -> None:
    response.headers["X-Robots-Tag"] = NOINDEX


def service_of(state: ApiState) -> DoctorLinkService:
    """The Doctor Link tier needs the same Redis the OTP tier needs. Without
    it the surface answers 503 rather than issuing links whose opening code
    nobody could check (fail closed)."""
    if state.doctor_link is None:
        raise doctor_link_unconfigured()
    return state.doctor_link


def aware(value: datetime) -> datetime:
    """SQLite hands back naive UTC; postgres hands back aware."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def accessor_role(actor: str) -> AccessorRole:
    """files/10 §3: the patient sees a ROLE, never a name.

    The only actor shapes this package writes are the patient's own account id
    and ``doctor_link:<id>``. Anything else stays UNKNOWN rather than guessed —
    inferring a role from an id shape is how a display name reaches a screen.
    """
    if actor.startswith("doctor_link:"):
        return AccessorRole.CLINICIAN
    if actor.startswith("svc-"):
        return AccessorRole.SYSTEM
    return AccessorRole.UNKNOWN


def encrypt_recipient(state: ApiState, tenant_id: uuid.UUID, label: str) -> dict[str, object]:
    field = state.cipher.encrypt_field(str(tenant_id), label.encode("utf-8"))
    return dict(encrypted_field_to_json(field))


def decrypt_recipient(state: ApiState, tenant_id: uuid.UUID, payload: dict[str, object]) -> str:
    field = encrypted_field_from_json(payload)
    return state.cipher.decrypt_field(str(tenant_id), field).decode("utf-8")


def link_out(link: DoctorLink, recipient: str, *, now: datetime) -> DoctorLinkOut:
    return DoctorLinkOut(
        link_id=link.id,
        recipient=recipient,
        expires_at=aware(link.expires_at),
        view_limit=link.view_limit,
        views_used=link.views_used,
        revoked=link.revoked_at is not None,
        spent=link.revoked_at is not None
        or aware(link.expires_at) <= now
        or link.views_used >= link.view_limit,
    )


def require_live(link: DoctorLink, *, now: datetime) -> None:
    """The three refusals, in the order a token holder needs them.

    Each one is counted (files/10 §9 signals) and each one is specific: the
    caller has already presented the 128-bit token, so telling them WHY the
    link stopped discloses nothing they did not have, and withholding it is
    what turns files/02 §2b's "the doctor couldn't see it" into a support call
    with no answer.
    """
    if link.revoked_at is not None:
        record_event(DoctorLinkEvent.REFUSED_REVOKED)
        raise doctor_link_revoked()
    if aware(link.expires_at) <= now:
        record_event(DoctorLinkEvent.REFUSED_EXPIRED)
        raise doctor_link_expired()
    if link.views_used >= link.view_limit:
        record_event(DoctorLinkEvent.REFUSED_VIEW_LIMIT)
        raise doctor_link_view_limit()


def shared_ids(scope_sections: dict[str, object]) -> set[str]:
    """The scope as the SHARE recorded it. Never a hard-coded section list:
    when the share vocabulary grows (INT-304) nothing here has to change."""
    ids = scope_sections.get("section_ids")
    if not isinstance(ids, list):
        return set()
    return {str(item) for item in ids}
