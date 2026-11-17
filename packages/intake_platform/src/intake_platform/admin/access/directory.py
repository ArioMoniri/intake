"""The identity seams the access review and offboarding stand on (INT-366).

files/08 §2.4 makes Keycloak "the single source of truth" for who holds a
console account, and §2.7 says the quarterly review is "produced by the
console from Keycloak, the role grants and the audit log". This module is the
contract with the first two; :mod:`.keycloak` and :mod:`.openbao` implement it
over the real admin APIs, and tests drive those implementations against
recorded answers rather than replacing them.

What crosses the seam is deliberately narrow. A :class:`DirectoryUser` holds
identifiers, flags, role names and two instants. Keycloak also returns first
name, last name and mail; the adapter never copies them, so no review, log or
audit row can carry them (invariant 6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol, TypeGuard

from intake_platform.admin.roles import ADMIN_ROLES, AdminRole

__all__ = [
    "CLINICIAN_REALM_ROLE",
    "STAFF_REALM_ROLES",
    "SUBJECT_SHAPE",
    "DirectoryUnavailable",
    "DirectoryUser",
    "IdentityDirectory",
    "LeaseRevoker",
    "LoginHistoryUnavailable",
    "RevocationFailed",
    "is_subject",
]

#: The realm role a clinician account carries (infra/keycloak/dev-realm.json).
#: files/08 §2.7 puts clinician accounts in the quarterly review, reviewed by
#: the tenant's `tenant_clinical_responsible`.
CLINICIAN_REALM_ROLE: Final = "clinician"

#: Every realm role that makes an account a staff account: the files/08 §2.1
#: console roles plus the clinician role. The review covers exactly these
#: holders and the 60-day auto-disable applies to exactly these accounts.
STAFF_REALM_ROLES: Final = frozenset({role.value for role in ADMIN_ROLES} | {CLINICIAN_REALM_ROLE})

#: A Keycloak user id as it may appear in a URL path segment and on the audit
#: chain: no slash, no dot-dot, no colon — the id travels into
#: ``/admin/realms/<realm>/users/<id>`` and must not be able to leave it.
SUBJECT_SHAPE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")

_CONSOLE_ROLE_VALUES: Final = {role.value: role for role in ADMIN_ROLES}


def is_subject(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and SUBJECT_SHAPE.fullmatch(value) is not None


class DirectoryUnavailable(Exception):
    """The directory could not be read or did not answer in the expected
    shape. A review that cannot see the holders has reviewed nobody, so this
    is raised and refused, never turned into an empty list."""

    code = "directory_unavailable"


class LoginHistoryUnavailable(DirectoryUnavailable):
    """The realm does not keep enough login history to tell a dormant account
    from one whose last login was forgotten. The auto-disable refuses rather
    than treating every account as never having logged in."""

    code = "login_history_unavailable"


class RevocationFailed(Exception):
    """A revocation call was refused or could not be made. The step is
    reported failed; the offboarding stays incomplete."""

    code = "revocation_failed"


@dataclass(frozen=True)
class DirectoryUser:
    """One realm account, as the review and the offboarding need it."""

    subject: str
    #: The login handle, when it is id-shaped; ``None`` otherwise, so a mail
    #: address or a display name used as a username never reaches a page.
    username: str | None
    enabled: bool
    realm_roles: frozenset[str]
    tenant: str | None
    org: str | None
    created_at: datetime
    last_login_at: datetime | None

    @property
    def console_roles(self) -> frozenset[AdminRole]:
        return frozenset(
            _CONSOLE_ROLE_VALUES[name] for name in self.realm_roles if name in _CONSOLE_ROLE_VALUES
        )

    @property
    def is_staff(self) -> bool:
        return bool(self.realm_roles & STAFF_REALM_ROLES)

    @property
    def last_activity_at(self) -> datetime:
        """The last login, or the account's creation when it never logged in:
        an account created yesterday is not dormant."""
        if self.last_login_at is None or self.last_login_at < self.created_at:
            return self.created_at
        return self.last_login_at


class IdentityDirectory(Protocol):
    """Keycloak's admin API, as INT-366 uses it."""

    def staff_users(self) -> list[DirectoryUser]:
        """Every account holding a staff realm role, with its last login."""
        ...

    def user(self, subject: str) -> DirectoryUser | None:
        """One account by id, or ``None`` when the realm has no such user."""
        ...

    def login_history_days(self) -> float:
        """How many days of LOGIN events the realm keeps (``inf`` when they
        never expire). Raises :class:`LoginHistoryUnavailable` when login
        events are not recorded at all."""
        ...

    def disable(self, subject: str) -> None:
        """Disable the account: no new login, no refresh of an offline token."""
        ...

    def revoke_sessions(self, subject: str) -> None:
        """End every session the account holds."""
        ...


class LeaseRevoker(Protocol):
    """OpenBao, as offboarding uses it."""

    def revoke_for(self, subject: str) -> int:
        """Disable the person's identity and revoke every token it holds —
        which revokes every lease those tokens created. Returns the number of
        tokens revoked; zero when the person has no identity."""
        ...
