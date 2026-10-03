"""The deployment-role gate on the other-subject data categories (INT-474).

Three of the owner's D3 categories collect data about a person who is not the
patient: ``household`` (household members), ``relatives_health`` (relatives)
and ``partner_fertility`` (the partner). That person gives no açık rıza, and
the patient cannot give it for them. The INT-471 legal lane (LD-03, LD-04;
proposed, in legal review, D25 scope: synthetic and test use only) reads the
ground for their data as KVKK m.6(3)(e): processing necessary for diagnosis,
treatment and care by persons under a duty of secrecy or authorised
institutions. That ground belongs to the health service provider. It holds in
the hospital deployment, where the hospital is veri sorumlusu and INTAKE
processes on its behalf (files/06 §0.1(1)(b)). In the consumer deployment the
company is veri sorumlusu (files/06 §0.1(1)(a)), and whether any ground exists
there is not decided, so those categories are not served there.

The INT-349 register row cannot express that split. It records whether counsel
has placed a category, not in which deployment, so a filled row would open
both. This gate is therefore independent of the row. It admits the three
categories only for :attr:`DeploymentRole.HOSPITAL_CONTROLLER`; it refuses them
for the consumer deployment and when no role was declared. There is no default
that admits, and no bypass. The role comes from configuration (the compile
command's ``--deployment-role``, the tenant row's ``kvkk_role`` at runtime),
never from patient input.
"""

from __future__ import annotations

import enum
from typing import Final

from protocols.data_register import OTHER_SUBJECT_CATEGORIES
from protocols.types import DataCategory

__all__ = [
    "HOSPITAL_CONTROLLER_ONLY",
    "DeploymentRole",
    "DeploymentRoleRefused",
    "admits",
    "refusal_reason",
    "require_admitted",
]


class DeploymentRole(enum.StrEnum):
    """Who is the KVKK data controller where a pack is served (files/06 §0.1(1)).

    A closed set. It has no default member: a compile or a tenant that names
    no role is treated as one in which the gated categories are refused.
    """

    HOSPITAL_CONTROLLER = "hospital_controller"
    """The hospital deployment (clinic console, kiosk, connectors): the
    hospital is veri sorumlusu and INTAKE is its veri işleyen under a written
    DPA. The tenant row says ``kvkk_role: processor``."""

    CONSUMER_CONTROLLER = "consumer_controller"
    """The consumer app (the patient-owned record): INTAKE, the company, is
    veri sorumlusu. The tenant row says ``kvkk_role: controller``."""


HOSPITAL_CONTROLLER_ONLY: Final[frozenset[DataCategory]] = OTHER_SUBJECT_CATEGORIES
"""The categories where another person is the data subject (D3 §3). Their
ground for that person is m.6(3)(e), the health service provider's, so they
are admitted in the hospital-controller deployment and nowhere else. The set is
the register's own, so a category D3 adds there is gated here too."""


class DeploymentRoleRefused(Exception):
    """A gated category was asked for outside the hospital-controller
    deployment. Carries ids only: no answer, no tenant name (invariant 6)."""

    def __init__(self, category: DataCategory, role: DeploymentRole | None) -> None:
        self.category = category
        self.role = role
        super().__init__(refusal_reason(category, role))


def admits(category: DataCategory, role: DeploymentRole | None) -> bool:
    """Whether ``role``'s deployment may serve or store ``category``.

    Only the parsed enum member opens the gate. A raw string that skipped
    parsing does not, so an unvalidated configuration value fails closed.
    """
    if category not in HOSPITAL_CONTROLLER_ONLY:
        return True
    return role is DeploymentRole.HOSPITAL_CONTROLLER


def refusal_reason(category: DataCategory, role: DeploymentRole | None) -> str:
    """Why ``category`` is refused for ``role``, naming the decision it rests on."""
    given = "no deployment role was declared" if role is None else f"the deployment is {role!s}"
    return (
        f"INT-474: data category {category.value!r} is about a person who is not "
        f"the patient, and {given}. Its ground for that person is KVKK m.6(3)(e), "
        "which belongs to the health service provider, so it is admitted only in "
        f"the {DeploymentRole.HOSPITAL_CONTROLLER.value} deployment (files/06 "
        "§0.1(1)(b); INT-471 LD-03 and LD-04). A complete register row does not "
        "change this: the consumer deployment's ground is undecided and the gate "
        "stays closed there until counsel decides it"
    )


def require_admitted(category: DataCategory, role: DeploymentRole | None) -> None:
    """Raise :class:`DeploymentRoleRefused` unless ``role`` admits ``category``."""
    if not admits(category, role):
        raise DeploymentRoleRefused(category, role)
