"""Admin console primitives (INT-180; files/08 §2, §8; sec_row admin-console).

The console is the largest privilege in the system, so this package ships the
properties rather than the screens: the files/08 §2.1 role set, the
``DangerousAction`` tiers, the four-eyes pending-action protocol, the
break-glass content rules, the IP allow-list, the append-only seam onto the
one hash-chained audit record, and the files/08 §2.3 second-factor policy
every staff token is held to (INT-365).

``ADMIN_ROUTES`` is the route descriptor table: :mod:`intake_api.admin` builds
its FastAPI router from it rather than declaring routes of its own, so a route
cannot exist without the audit action and the role set that govern it.
"""

from __future__ import annotations

from intake_platform.admin.actions import (
    BREAK_GLASS_OPEN,
    DANGEROUS_ACTIONS,
    ActionDirection,
    ActionTier,
    DangerousAction,
    dangerous_action,
)
from intake_platform.admin.audit import (
    ADMIN_BASIS_REF,
    AdminActionRecord,
    AdminAuditSink,
    admin_resource_ref,
    detail_digest,
)
from intake_platform.admin.break_glass import (
    BREAK_GLASS_GRANT_TTL,
    MIN_JUSTIFICATION_CHARS,
    BreakGlassReason,
    BreakGlassRefused,
    Deployment,
    build_break_glass_justification,
)
from intake_platform.admin.four_eyes import (
    ActorBlock,
    ApprovalBrief,
    FourEyesRefused,
    FourEyesService,
    Justification,
    PendingAction,
    PendingActionState,
)
from intake_platform.admin.ip_allowlist import IpAllowList
from intake_platform.admin.principal import (
    AdminClaimsVerifier,
    AdminPrincipal,
    ClaimsRejected,
    PrincipalRefused,
    RoleNotPermitted,
    TenantScopeRefused,
    effective_tenant,
    principal_from_claims,
)
from intake_platform.admin.roles import (
    ADMIN_ROLES,
    ROLE_SPECS,
    TIER3_APPROVER_ROLES,
    AdminRole,
    PatientContentPath,
    RoleScope,
    RoleSpec,
    role_spec,
)
from intake_platform.admin.second_factor import SecondFactorRequired, requires_webauthn
from intake_platform.admin.wiring import ADMIN_ROUTES, AdminRoute, AdminWiring

__all__ = [
    "ADMIN_BASIS_REF",
    "ADMIN_ROUTES",
    "ADMIN_ROLES",
    "BREAK_GLASS_GRANT_TTL",
    "BREAK_GLASS_OPEN",
    "DANGEROUS_ACTIONS",
    "MIN_JUSTIFICATION_CHARS",
    "ROLE_SPECS",
    "TIER3_APPROVER_ROLES",
    "ActionDirection",
    "ActionTier",
    "ActorBlock",
    "AdminActionRecord",
    "AdminAuditSink",
    "AdminClaimsVerifier",
    "AdminPrincipal",
    "AdminRole",
    "AdminRoute",
    "AdminWiring",
    "ApprovalBrief",
    "BreakGlassReason",
    "BreakGlassRefused",
    "ClaimsRejected",
    "DangerousAction",
    "Deployment",
    "FourEyesRefused",
    "FourEyesService",
    "IpAllowList",
    "Justification",
    "PatientContentPath",
    "PendingAction",
    "PendingActionState",
    "PrincipalRefused",
    "RoleNotPermitted",
    "RoleScope",
    "RoleSpec",
    "SecondFactorRequired",
    "TenantScopeRefused",
    "admin_resource_ref",
    "build_break_glass_justification",
    "dangerous_action",
    "detail_digest",
    "effective_tenant",
    "principal_from_claims",
    "requires_webauthn",
    "role_spec",
]
