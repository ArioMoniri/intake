"""The console role set (INT-180; files/08 §2.1).

The table below is a transcription of §2.1 and nothing else — no role is
invented here and none is dropped. ``tests/admin/test_rbac_matrix.py`` parses
§2.1 out of files/08 itself and holds this registry against it, so the spec
and the code cannot drift in either direction.

Two fields carry the weight:

- ``patient_content`` says by which path — if any — the role reaches a
  patient's clinical content. §2.1's "only via break-glass" is
  :attr:`PatientContentPath.BREAK_GLASS`, and it is the only value that opens
  the ceremony in :mod:`intake_platform.admin.break_glass`.
- ``scope`` says what the role's authority ranges over. ``platform_admin`` was
  unconstrained before the 25 Aug audit and is now
  :attr:`RoleScope.PLATFORM_INFRASTRUCTURE` — no clinical surfaces, and no
  grant anywhere near the audit table, whose INSERT belongs to
  ``svc-audit-writer`` alone (§0c F5).

A role's narrowings are expressed where they can be enforced: in
:mod:`intake_platform.admin.actions`, whose registry names the roles that may
request each action. A list of forbidden action ids kept here would name
actions that do not exist yet, and a constraint against nothing is not a
control.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

__all__ = [
    "ADMIN_ROLES",
    "ROLE_SPECS",
    "TIER3_APPROVER_ROLES",
    "AdminRole",
    "PatientContentPath",
    "RoleScope",
    "RoleSpec",
    "role_spec",
]


class AdminRole(enum.StrEnum):
    """files/08 §2.1, in table order."""

    PLATFORM_OWNER = "platform_owner"
    PLATFORM_ADMIN = "platform_admin"
    TENANT_ADMIN = "tenant_admin"
    TENANT_CLINICAL_RESPONSIBLE = "tenant_clinical_responsible"
    CLINICAL_LEAD = "clinical_lead"
    QMS_OWNER = "qms_owner"
    INVESTIGATOR = "investigator"
    AUDITOR = "auditor"
    SRE_ONCALL = "sre_oncall"
    COMPLIANCE_OFFICER = "compliance_officer"
    RESEARCHER = "researcher"
    SUPPORT = "support"


class RoleScope(enum.StrEnum):
    """What the role's authority ranges over (§2.1 "scope" column)."""

    ALL_TENANTS = "all_tenants"
    PLATFORM_INFRASTRUCTURE = "platform_infrastructure"
    ONE_TENANT = "one_tenant"
    ONE_STUDY = "one_study"
    ONE_PATIENT_GRANT = "one_patient_grant"


class PatientContentPath(enum.StrEnum):
    """§2.1 "may reach patient content?", as a path rather than a boolean —
    *how* the role gets there is what governance attaches to."""

    NONE = "none"
    BREAK_GLASS = "break_glass"
    ORDINARY_CARE = "ordinary_care"
    STUDY_ONLY = "study_only"
    PATIENT_GRANT = "patient_grant"


@dataclass(frozen=True)
class RoleSpec:
    role: AdminRole
    scope: RoleScope
    patient_content: PatientContentPath
    #: May stand as the second key on a tier-3 ceremony (files/08 §8.2).
    may_approve_tier3: bool
    #: A grant of this role pages (`admin.role_granted_total{privileged}`).
    privileged: bool


def _spec(
    role: AdminRole,
    scope: RoleScope,
    patient_content: PatientContentPath,
    *,
    approves_tier3: bool = False,
    privileged: bool = False,
) -> RoleSpec:
    return RoleSpec(
        role=role,
        scope=scope,
        patient_content=patient_content,
        may_approve_tier3=approves_tier3,
        privileged=privileged,
    )


ROLE_SPECS: dict[AdminRole, RoleSpec] = {
    spec.role: spec
    for spec in (
        _spec(
            AdminRole.PLATFORM_OWNER,
            RoleScope.ALL_TENANTS,
            PatientContentPath.BREAK_GLASS,
            privileged=True,
        ),
        _spec(
            AdminRole.PLATFORM_ADMIN,
            RoleScope.PLATFORM_INFRASTRUCTURE,
            PatientContentPath.NONE,
            privileged=True,
        ),
        _spec(
            AdminRole.TENANT_ADMIN,
            RoleScope.ONE_TENANT,
            PatientContentPath.NONE,
            privileged=True,
        ),
        _spec(
            AdminRole.TENANT_CLINICAL_RESPONSIBLE,
            RoleScope.ONE_TENANT,
            PatientContentPath.ORDINARY_CARE,
        ),
        _spec(
            AdminRole.CLINICAL_LEAD,
            RoleScope.ALL_TENANTS,
            PatientContentPath.BREAK_GLASS,
            approves_tier3=True,
        ),
        _spec(
            AdminRole.QMS_OWNER,
            RoleScope.ALL_TENANTS,
            PatientContentPath.NONE,
            approves_tier3=True,
        ),
        _spec(AdminRole.INVESTIGATOR, RoleScope.ONE_STUDY, PatientContentPath.STUDY_ONLY),
        _spec(AdminRole.AUDITOR, RoleScope.ALL_TENANTS, PatientContentPath.NONE),
        _spec(AdminRole.SRE_ONCALL, RoleScope.PLATFORM_INFRASTRUCTURE, PatientContentPath.NONE),
        _spec(
            AdminRole.COMPLIANCE_OFFICER,
            RoleScope.ALL_TENANTS,
            PatientContentPath.BREAK_GLASS,
            approves_tier3=True,
        ),
        _spec(AdminRole.RESEARCHER, RoleScope.ALL_TENANTS, PatientContentPath.NONE),
        _spec(AdminRole.SUPPORT, RoleScope.ONE_PATIENT_GRANT, PatientContentPath.PATIENT_GRANT),
    )
}

ADMIN_ROLES: tuple[AdminRole, ...] = tuple(ROLE_SPECS)

#: files/08 §8.2: a tier-3 ceremony needs at least one of these as a key.
TIER3_APPROVER_ROLES: frozenset[AdminRole] = frozenset(
    role for role, spec in ROLE_SPECS.items() if spec.may_approve_tier3
)


def role_spec(role: AdminRole) -> RoleSpec:
    return ROLE_SPECS[role]
