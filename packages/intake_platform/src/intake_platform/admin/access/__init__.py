"""Access & identity (INT-366; files/08 §2.4, §2.7, §3; sec_row admin-console).

The quarterly access review, generated from Keycloak, the role grants and the
audit chain (:mod:`.review`); one-action offboarding across Keycloak, OpenBao
and every other console account, plus the 60-day dormancy rule
(:mod:`.offboarding`); and the adapters those stand on — the Keycloak admin
API (:mod:`.keycloak`), OpenBao's identity and token APIs (:mod:`.openbao`)
and the configured list of console systems outside both (:mod:`.systems`).

:class:`IdentityWiring` is what the console holds when all of that is
configured. When it is not, the review and the offboarding answer 503 — and
the read-only downgrade still applies, because it reads only the chain.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from intake_platform.admin.access.directory import (
    CLINICIAN_REALM_ROLE,
    STAFF_REALM_ROLES,
    DirectoryUnavailable,
    DirectoryUser,
    IdentityDirectory,
    LeaseRevoker,
    LoginHistoryUnavailable,
    RevocationFailed,
    is_subject,
)
from intake_platform.admin.access.keycloak import KeycloakAdminDirectory
from intake_platform.admin.access.openbao import OpenBaoLeaseRevoker
from intake_platform.admin.access.systems import (
    BUILT_IN_SYSTEMS,
    AccountRevoker,
    ConsoleAccountSystem,
    ConsoleSystemsRefused,
    Revocation,
    load_console_systems,
)

__all__ = [
    "BUILT_IN_SYSTEMS",
    "CLINICIAN_REALM_ROLE",
    "STAFF_REALM_ROLES",
    "AccountRevoker",
    "ConsoleAccountSystem",
    "ConsoleSystemsRefused",
    "DirectoryUnavailable",
    "DirectoryUser",
    "IdentityDirectory",
    "IdentityWiring",
    "KeycloakAdminDirectory",
    "LeaseRevoker",
    "LoginHistoryUnavailable",
    "OpenBaoLeaseRevoker",
    "Revocation",
    "RevocationFailed",
    "is_subject",
    "load_console_systems",
]


@dataclass(frozen=True)
class IdentityWiring:
    """The directory, the lease revoker and the console systems, together."""

    directory: IdentityDirectory
    leases: LeaseRevoker
    systems: tuple[ConsoleAccountSystem, ...]
    #: Adapters for the systems configured ``programmatic``, by system id.
    adapters: Mapping[str, AccountRevoker] = field(default_factory=dict)
