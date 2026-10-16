"""INT-490 — which tenants' data may enter a vendor-side aggregate (LD-06).

LD-06 (a): improving the service is the vendor's purpose of its own. Where
INTAKE is the CONTROLLER (the consumer deployment) it may compute anonymised
aggregates under KVKK m.28(1)(b). Where it is the PROCESSOR (the hospital
deployment) it processes "on the controller's authority and on its behalf"
(m.3(1)(ğ)), so ``hospital_deployment_needs_controller_authorisation: true`` —
and ``fail_closed_while_draft`` says "in the hospital deployment no aggregate
is computed for the vendor's own use until the DPA authorises it".

**Two inputs, and the database decides the role.** The registry below names
which tenants an operator wants counted and, for a processor tenant, the DPA
clause that authorises it. Whether a tenant IS a processor is never taken from
the registry: it is the tenant row's own ``kvkk_role`` (INT-030, "every table,
screen and export knows which role applies via this tenant flag"), read inside
that tenant's RLS session. A registry that calls a processor a controller
cannot make it one.

**The registry ships unset.** No tenant id is committed here — ids are made at
provisioning, per deployment — so an unset ``INTAKE_ANALYTICS_TENANTS_PATH``
admits nobody, and the Analytics page says so. The file, when a deployment
provides one::

    tenants:
      - tenant_id: <uuid>
        dpa_authorisation_ref: null   # or the id of the DPA clause (processor)

No executed DPA authorises vendor-side aggregates today (LD-06
``controller_authorisation_wording``: not decided), so no processor tenant is
admitted by any committed configuration.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml
from prometheus_client import Counter

from intake_platform.db.models import KvkkRole

__all__ = [
    "ANALYTICS_RESEARCH_TENANT_REFUSED",
    "ENV_TENANT_REGISTRY",
    "AdmittedTenant",
    "TenantRegistry",
    "TenantRegistryRefused",
    "admission_refusal",
]

ENV_TENANT_REGISTRY: Final = "INTAKE_ANALYTICS_TENANTS_PATH"

ANALYTICS_RESEARCH_TENANT_REFUSED = Counter(
    "analytics_research_tenant_refused_total",
    "Registry tenants left out of a research analytics release, by reason class.",
    ["reason"],
)

_REF_SHAPE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
_ROW_KEYS: Final = frozenset({"tenant_id", "dpa_authorisation_ref"})


class TenantRegistryRefused(ValueError):
    """The registry file is absent, unreadable or not the closed shape.
    ``code`` names the class of the defect, never a value from the file."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AdmittedTenant:
    tenant_id: uuid.UUID
    #: the DPA clause authorising vendor-side aggregates; required for a
    #: processor tenant, meaningless for a controller one
    dpa_authorisation_ref: str | None


def _row(raw: object) -> AdmittedTenant:
    if not isinstance(raw, Mapping) or set(raw) != _ROW_KEYS:
        raise TenantRegistryRefused("registry_malformed")
    try:
        tenant_id = uuid.UUID(str(raw["tenant_id"]))
    except ValueError:
        raise TenantRegistryRefused("tenant_id_malformed") from None
    ref = raw["dpa_authorisation_ref"]
    if ref is not None and (not isinstance(ref, str) or _REF_SHAPE.fullmatch(ref) is None):
        raise TenantRegistryRefused("dpa_authorisation_ref_malformed")
    return AdmittedTenant(tenant_id=tenant_id, dpa_authorisation_ref=ref)


@dataclass(frozen=True)
class TenantRegistry:
    tenants: tuple[AdmittedTenant, ...]

    @classmethod
    def from_mapping(cls, data: object) -> TenantRegistry:
        if not isinstance(data, Mapping) or set(data) != {"tenants"}:
            raise TenantRegistryRefused("registry_malformed")
        rows = data["tenants"]
        if not isinstance(rows, list):
            raise TenantRegistryRefused("registry_malformed")
        tenants = tuple(_row(raw) for raw in rows)
        if len({tenant.tenant_id for tenant in tenants}) != len(tenants):
            raise TenantRegistryRefused("tenant_duplicated")
        return cls(tenants=tenants)

    @classmethod
    def from_yaml(cls, path: Path) -> TenantRegistry:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            raise TenantRegistryRefused("registry_unreadable") from None
        return cls.from_mapping(data)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> TenantRegistry | None:
        """The configured registry, ``None`` when unset (nobody admitted), or
        :class:`TenantRegistryRefused` when set but unusable."""
        raw = env.get(ENV_TENANT_REGISTRY, "").strip()
        if not raw:
            return None
        return cls.from_yaml(Path(raw))


def admission_refusal(tenant: AdmittedTenant, kvkk_role: KvkkRole | None) -> str | None:
    """``None`` when the tenant's data may enter the aggregate, else why not.

    ``kvkk_role`` is the tenant row's own, or ``None`` when the database holds
    no such tenant.
    """
    if kvkk_role is None:
        return "tenant_unknown"
    if kvkk_role is KvkkRole.PROCESSOR and tenant.dpa_authorisation_ref is None:
        return "processor_without_dpa_authorisation"
    return None
