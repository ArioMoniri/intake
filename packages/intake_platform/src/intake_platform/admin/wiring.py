"""The admin route descriptor table and the console's wiring (INT-180).

**Why the routes are declared as data.** files/08 §8 rule (b) says there is no
such thing as an unregistered admin write, and invariant 4 says every action
is audited. Both properties are structural here rather than reviewed: the
FastAPI router in :mod:`intake_api.admin` is BUILT from this tuple, so a route
cannot come into existence without an audit action attached to it, and
``tests/admin/test_admin_audit.py`` reads the served route table off FastAPI
itself and fails when the two sets differ. The audited-route list is therefore
derived from what is reachable, never maintained alongside it.

``AdminWiring`` is the console's injectable dependency block. Two of its
fields ship deliberately barren:

- ``ip_allowlist`` — empty, so the console admits nobody until a deployment
  names its ranges (files/08 §2.3 names none);
- ``deployments`` — empty, so break-glass refuses for every tenant until the
  controller/processor question is answered per tenant (files/08 §2.6).

Neither is a gap to be filled with a plausible value; both are the fail-closed
state the design asks for.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from intake_platform.admin.actions import BREAK_GLASS_OPEN
from intake_platform.admin.break_glass import Deployment
from intake_platform.admin.four_eyes import FourEyesService
from intake_platform.admin.ip_allowlist import IpAllowList
from intake_platform.admin.principal import AdminClaimsVerifier
from intake_platform.admin.roles import ADMIN_ROLES, AdminRole

__all__ = ["ADMIN_ROUTES", "AdminRoute", "AdminWiring"]

_ANY_CONSOLE_ROLE = frozenset(ADMIN_ROLES)

#: The brief is what the second pair of eyes reads before deciding, so it is
#: readable by the roles that may open a ceremony, the roles that may approve
#: one, and `auditor` — read-only evidence export, every read audited (§2.1).
_BRIEF_READERS = (
    BREAK_GLASS_OPEN.actor_roles | BREAK_GLASS_OPEN.approver_roles | {AdminRole.AUDITOR}
)


@dataclass(frozen=True)
class AdminRoute:
    method: str
    path: str
    #: The dotted name the chain records. The write-ahead pair appends
    #: ``<audit_action>.intent`` and then ``<audit_action>.success|failure``.
    audit_action: str
    permitted_roles: frozenset[AdminRole]
    #: Set for every mutating route (files/08 §8 rule b).
    dangerous_action_id: str | None = None


ADMIN_ROUTES: tuple[AdminRoute, ...] = (
    AdminRoute("GET", "/admin/whoami", "admin.whoami.read", _ANY_CONSOLE_ROLE),
    AdminRoute("GET", "/admin/access/roles", "admin.access.roles.read", _ANY_CONSOLE_ROLE),
    AdminRoute("GET", "/admin/actions", "admin.actions.read", _ANY_CONSOLE_ROLE),
    AdminRoute(
        "POST",
        "/admin/break-glass",
        "admin.break_glass.open",
        BREAK_GLASS_OPEN.actor_roles,
        BREAK_GLASS_OPEN.id,
    ),
    AdminRoute(
        "GET",
        "/admin/break-glass/{action_id}",
        "admin.break_glass.brief.read",
        frozenset(_BRIEF_READERS),
    ),
    AdminRoute(
        "POST",
        "/admin/break-glass/{action_id}/approve",
        "admin.break_glass.approve",
        BREAK_GLASS_OPEN.approver_roles,
        BREAK_GLASS_OPEN.id,
    ),
)


@dataclass
class AdminWiring:
    claims: AdminClaimsVerifier
    ip_allowlist: IpAllowList = field(default_factory=lambda: IpAllowList(networks=()))
    four_eyes: FourEyesService = field(default_factory=FourEyesService)
    #: tenant id -> which side of the controller/processor line it sits on.
    #: Empty by default: no file in this repository records it, and a guessed
    #: entry would decide a lawful-basis question (files/08 §2.6, HB-L6).
    deployments: Mapping[str, Deployment] = field(default_factory=dict)
