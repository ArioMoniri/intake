"""The quarterly access review, generated rather than assembled (INT-366; files/08 §2.7).

    "The review is produced by the console from Keycloak, the role grants and
    the audit log, not assembled by hand into a spreadsheet [...] a review
    older than 100 days downgrades every platform_owner and tenant_admin
    session to read-only and pages."

**What the document is.** Every staff account in the realm (the files/08 §2.1
console roles plus the clinician role), with its effective role grants, its
enabled flag, its last login, its last console action and when its section was
last reviewed — grouped into the sections §2.7 assigns reviewers to:

======================  ===========================  =================================
section                 signs                        countersigns
======================  ===========================  =================================
``platform_owner``      ``compliance_officer``       a second key from ANOTHER
                                                     organisation (§2.7's "external
                                                     signature")
``console_roles``       ``compliance_officer``       a second key (§3 "countersign")
``clinicians:<tenant>`` that tenant's                a second key
                        ``tenant_clinical_responsible``
======================  ===========================  =================================

Each section carries a digest over its population — who holds which staff role,
enabled or not, in which tenant and organisation. Logins do not move it; a grant
does. A signature names the digest, and a countersignature is refused if the
population changed in between, so the second key approves what the first saw.

**Where "last review" lives.** On the audit chain. A countersigned section is
one ``admin.access_review.signed`` row whose resource reference is
``access_review:<section>:<digest>``, and :class:`ReviewLedger` reads the review
state back from those rows. There is no second store to drift from the chain,
restarts lose nothing, and every replica reads the same answer.

**Enforcement.** The console review is the ``platform_owner`` and
``console_roles`` sections — the two that cover console roles, and so the two
the §2.7 downgrade is about. Its age is the age of the staler of the two; a
section never countersigned makes it infinitely old. Past 100 days
:meth:`ReviewLedger.read_only_roles` names ``platform_owner`` and
``tenant_admin``, and the admin router refuses any write reached only through
one of them. A ledger that has not read the chain yet is treated as never
reviewed: an unknown review is not a current one. Clinician sections carry
their own age on the page; they do not stand in for the console review.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol

from intake_platform.admin.access.directory import STAFF_REALM_ROLES, DirectoryUser
from intake_platform.admin.access.offboarding import DORMANT_AFTER_DAYS
from intake_platform.admin.metrics import ADMIN_ACCESS_REVIEW_AGE_DAYS
from intake_platform.admin.roles import AdminRole
from intake_platform.audit import AuditEntry

__all__ = [
    "CLINICIANS_PREFIX",
    "CLINICIANS_UNSCOPED",
    "CONSOLE_SECTIONS",
    "READ_ONLY_ROLES",
    "REVIEW_MAX_AGE_DAYS",
    "SECTION_CONSOLE_ROLES",
    "SECTION_PLATFORM_OWNER",
    "SIGNED_ACTION",
    "AccessReview",
    "AuditRows",
    "HolderRow",
    "ReviewLedger",
    "ReviewSection",
    "SectionRule",
    "generate_review",
    "last_console_actions",
    "parse_signed_ref",
    "scoped_to_tenant",
    "section_digest",
    "section_rule",
    "signed_resource_ref",
]

#: files/08 §2.7: "a review older than 100 days downgrades [...]".
REVIEW_MAX_AGE_DAYS: Final = 100
#: files/08 §2.7: "[...] every platform_owner and tenant_admin session to read-only".
READ_ONLY_ROLES: Final = frozenset({AdminRole.PLATFORM_OWNER, AdminRole.TENANT_ADMIN})

#: The chain row a countersigned section leaves. Not a route action: the
#: countersign route writes it after the ceremony succeeds.
SIGNED_ACTION: Final = "admin.access_review.signed"

SECTION_PLATFORM_OWNER: Final = "platform_owner"
SECTION_CONSOLE_ROLES: Final = "console_roles"
CONSOLE_SECTIONS: Final = (SECTION_PLATFORM_OWNER, SECTION_CONSOLE_ROLES)
CLINICIANS_PREFIX: Final = "clinicians:"
#: A clinician account with no tenant attribute. Reviewed by the compliance
#: officer, because there is no tenant whose medical director owns it — and
#: listed, because an unscoped clinician is exactly what a review should see.
CLINICIANS_UNSCOPED: Final = "clinicians:unscoped"

_REF_PREFIX: Final = "access_review:"
_DIGEST: Final = re.compile(r"[0-9a-f]{32}")
_TENANT: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}")
_DAY: Final = timedelta(days=1)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


# --- sections ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionRule:
    signer_role: AdminRole
    #: For a clinician section, the tenant whose reviewer signs it.
    signer_tenant: str | None
    #: files/08 §2.7: `platform_owner` needs "an external signature".
    countersigner_external: bool


def section_rule(section: str) -> SectionRule | None:
    """Who signs ``section``, or ``None`` when it is not a section at all."""
    if section == SECTION_PLATFORM_OWNER:
        return SectionRule(AdminRole.COMPLIANCE_OFFICER, None, countersigner_external=True)
    if section in (SECTION_CONSOLE_ROLES, CLINICIANS_UNSCOPED):
        return SectionRule(AdminRole.COMPLIANCE_OFFICER, None, countersigner_external=False)
    tenant = section.removeprefix(CLINICIANS_PREFIX)
    if section.startswith(CLINICIANS_PREFIX) and _TENANT.fullmatch(tenant):
        return SectionRule(AdminRole.TENANT_CLINICAL_RESPONSIBLE, tenant, False)
    return None


def _sections_of(user: DirectoryUser) -> tuple[str, ...]:
    sections: list[str] = []
    roles = user.console_roles
    if AdminRole.PLATFORM_OWNER in roles:
        sections.append(SECTION_PLATFORM_OWNER)
    if roles - {AdminRole.PLATFORM_OWNER}:
        sections.append(SECTION_CONSOLE_ROLES)
    if "clinician" in user.realm_roles:
        tenant = user.tenant
        valid = tenant is not None and _TENANT.fullmatch(tenant)
        sections.append(f"{CLINICIANS_PREFIX}{tenant}" if valid else CLINICIANS_UNSCOPED)
    return tuple(sections)


def _staff_roles(user: DirectoryUser) -> tuple[str, ...]:
    return tuple(sorted(user.realm_roles & STAFF_REALM_ROLES))


def section_digest(section: str, users: Iterable[DirectoryUser]) -> str:
    """128 bits over the section's population: who holds which staff role,
    enabled or not, in which tenant and organisation. Canonical JSON, like the
    audit detail digest, so a reviewer can recompute it."""
    population = sorted(
        [user.subject, list(_staff_roles(user)), user.enabled, user.tenant, user.org]
        for user in users
    )
    canonical = json.dumps(
        [section, population], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def signed_resource_ref(section: str, digest: str) -> str:
    return f"{_REF_PREFIX}{section}:{digest}"


def parse_signed_ref(ref: str) -> tuple[str, str] | None:
    """``(section, digest)`` from a signed row's reference, or ``None``."""
    if not ref.startswith(_REF_PREFIX):
        return None
    section, _, digest = ref[len(_REF_PREFIX) :].rpartition(":")
    if not _DIGEST.fullmatch(digest) or section_rule(section) is None:
        return None
    return section, digest


# --- the ledger ----------------------------------------------------------------------------


class AuditRows(Protocol):
    """Read access to the chain's rows. ``intake_api.audit.AuditWriter``
    satisfies it; nothing here can append, and nothing here sees the head."""

    async def entries(self) -> Sequence[AuditEntry]: ...


def _stamp(entry: AuditEntry) -> datetime | None:
    try:
        at = datetime.fromisoformat(entry.timestamp_utc)
    except ValueError:
        return None
    return at if at.tzinfo is not None else None


class ReviewLedger:
    """When each section was last countersigned, read back from the chain.

    Constructing one binds ``admin_access_review_age_days`` to it: the gauge
    is computed at scrape time from the cached sign-off instants, so it keeps
    counting even when nobody opens the console.
    """

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock if clock is not None else _utc_now
        self._signed: dict[str, datetime] = {}
        self._loaded = False
        ADMIN_ACCESS_REVIEW_AGE_DAYS.set_function(self.review_age_days)

    def now(self) -> datetime:
        return self._clock()

    def load(self, entries: Iterable[AuditEntry]) -> None:
        signed: dict[str, datetime] = {}
        for entry in entries:
            if entry.action != SIGNED_ACTION:
                continue
            parsed = parse_signed_ref(entry.resource_ref)
            at = _stamp(entry)
            if parsed is None or at is None:
                continue
            section = parsed[0]
            if section not in signed or at > signed[section]:
                signed[section] = at
        self._signed = signed
        self._loaded = True

    async def refresh(self, source: AuditRows) -> Sequence[AuditEntry]:
        """Re-read the chain; returns the rows so a caller need not read twice."""
        entries = await source.entries()
        self.load(entries)
        return entries

    def last_signed(self, section: str) -> datetime | None:
        return self._signed.get(section)

    def section_age_days(self, section: str) -> float:
        at = self._signed.get(section) if self._loaded else None
        if at is None:
            return math.inf
        return max(0.0, (self._clock() - at) / _DAY)

    def review_age_days(self) -> float:
        """The console review's age: the staler of its two sections."""
        return max(self.section_age_days(section) for section in CONSOLE_SECTIONS)

    def read_only_roles(self) -> frozenset[AdminRole]:
        if self.review_age_days() > REVIEW_MAX_AGE_DAYS:
            return READ_ONLY_ROLES
        return frozenset()


# --- the document ----------------------------------------------------------------------------


@dataclass(frozen=True)
class HolderRow:
    subject: str
    username: str | None
    enabled: bool
    roles: tuple[str, ...]
    tenant: str | None
    org: str | None
    sections: tuple[str, ...]
    created_at: datetime
    last_login_at: datetime | None
    days_since_activity: float
    days_until_auto_disable: float
    last_console_action_at: datetime | None
    last_reviewed_at: datetime | None


@dataclass(frozen=True)
class ReviewSection:
    section: str
    signer_role: AdminRole
    signer_tenant: str | None
    countersigner_external: bool
    holders: tuple[str, ...]
    review_digest: str
    last_signed_at: datetime | None
    age_days: float
    overdue: bool


@dataclass(frozen=True)
class AccessReview:
    generated_at: datetime
    holders: tuple[HolderRow, ...]
    sections: tuple[ReviewSection, ...]
    review_age_days: float
    read_only_roles: frozenset[AdminRole]


def last_console_actions(entries: Iterable[AuditEntry]) -> dict[str, datetime]:
    """Each actor's most recent console action (``admin.*`` rows only)."""
    latest: dict[str, datetime] = {}
    for entry in entries:
        if not entry.action.startswith("admin."):
            continue
        at = _stamp(entry)
        if at is not None and (entry.actor not in latest or at > latest[entry.actor]):
            latest[entry.actor] = at
    return latest


def _section_order(section: str) -> tuple[int, str]:
    order = {SECTION_PLATFORM_OWNER: 0, SECTION_CONSOLE_ROLES: 1}
    return order.get(section, 2), section


def generate_review(
    users: Sequence[DirectoryUser],
    ledger: ReviewLedger,
    last_actions: Mapping[str, datetime],
    *,
    now: datetime,
) -> AccessReview:
    staff = [user for user in users if user.is_staff]
    members: dict[str, list[DirectoryUser]] = {section: [] for section in CONSOLE_SECTIONS}
    for user in staff:
        for section in _sections_of(user):
            members.setdefault(section, []).append(user)
    sections: list[ReviewSection] = []
    for section in sorted(members, key=_section_order):
        rule = section_rule(section)
        if rule is None:
            continue
        population = members[section]
        age = ledger.section_age_days(section)
        sections.append(
            ReviewSection(
                section=section,
                signer_role=rule.signer_role,
                signer_tenant=rule.signer_tenant,
                countersigner_external=rule.countersigner_external,
                holders=tuple(sorted(user.subject for user in population)),
                review_digest=section_digest(section, population),
                last_signed_at=ledger.last_signed(section),
                age_days=age,
                overdue=age > REVIEW_MAX_AGE_DAYS,
            )
        )
    holders: list[HolderRow] = []
    for user in sorted(staff, key=lambda item: item.subject):
        own = _sections_of(user)
        reviewed = [ledger.last_signed(section) for section in own]
        idle = (now - user.last_activity_at) / _DAY
        holders.append(
            HolderRow(
                subject=user.subject,
                username=user.username,
                enabled=user.enabled,
                roles=_staff_roles(user),
                tenant=user.tenant,
                org=user.org,
                sections=own,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
                days_since_activity=idle,
                days_until_auto_disable=DORMANT_AFTER_DAYS - idle,
                last_console_action_at=last_actions.get(user.subject),
                # the stalest of the holder's sections: a holder is only as
                # reviewed as the least recently reviewed place they appear
                last_reviewed_at=(
                    None if not reviewed or None in reviewed else min(r for r in reviewed if r)
                ),
            )
        )
    return AccessReview(
        generated_at=now,
        holders=tuple(holders),
        sections=tuple(sections),
        review_age_days=ledger.review_age_days(),
        read_only_roles=ledger.read_only_roles(),
    )


def scoped_to_tenant(review: AccessReview, tenant: str | None) -> AccessReview:
    """A tenant's medical director sees their own clinician section and the
    holders in it — never another tenant's, and never the console staff."""
    section_id = f"{CLINICIANS_PREFIX}{tenant}" if tenant is not None else None
    sections = tuple(section for section in review.sections if section.section == section_id)
    visible = {subject for section in sections for subject in section.holders}
    return replace(
        review,
        sections=sections,
        holders=tuple(holder for holder in review.holders if holder.subject in visible),
    )
