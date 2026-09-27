"""The previsit-output recipient registry: who may fetch a finished previsit.

This is the **inbound** twin of ``intake_connectors.destinations`` and it
exists for the same reason that one does. A share of clinical data to another
organisation is a decision a human takes out of band and records; it is never
a value a caller supplies, and it is never implied by the caller merely being
authenticated. INT-160 held that line for pushes; a hospital *pulling* a
previsit is the same disclosure with the arrow reversed.

**What a row costs.** Three refs, each naming something a human has actually
produced:

``dpa_ref``
    the executed data-processing agreement with the receiving hospital,
    naming this interface.
``approval_ref``
    the recorded tier-3 approval that registered the reader (files/10 §8: two
    humans, different organisations, write-ahead audit).
``retention_ref``
    the clause of that DPA which states **how long the hospital keeps the copy
    it fetched**. This is the field this repository could not fill in for
    itself. files/06 §3 states how long INTAKE keeps a record; it says nothing
    about a copy that has left, and in the hospital deployment the hospital is
    the controller of what it holds (``KvkkRole.PROCESSOR``). Inventing a
    period here would be inventing a retention, so the row demands the clause
    instead and the registry refuses a row without one.

**One reader per tenant.** A second row for the same tenant would make "which
agreement is this fetch under" ambiguous at the exact moment the fetch is
written to the audit chain, so it is refused at load rather than resolved by
ordering.

``infra/previsit_output/recipients.yaml`` ships with zero rows: no DPA is
executed, no reader is approved, and no retention clause exists to name. The
mechanism is wired and refuses everything, which is the fail-closed state and
not a gap (CLAUDE.md invariant 17).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "HospitalRecipient",
    "RecipientNotRegistered",
    "RecipientRegistry",
    "RecipientRegistryError",
    "load_recipients",
]

#: Ids, refs and clause references: the audit chain's own shape (invariant 6),
#: because every one of these reaches an audit entry. Prose has no carrier.
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@#-]{0,127}$")

_REQUIRED_REFS = ("recipient_id", "dpa_ref", "approval_ref", "retention_ref")
_ROW_KEYS = frozenset({"recipient_id", "tenant_id", *_REQUIRED_REFS})
_TOP_LEVEL_KEYS = frozenset({"version", "recipients"})


class RecipientRegistryError(Exception):
    """The registry file, or a row in it, violates a policy invariant.

    Messages name fields and ids — registry data — and never echo a value that
    failed a shape check: a refused ref travels further than the code that
    refused it.
    """


class RecipientNotRegistered(Exception):
    """No approved reader answers for this tenant.

    The message names nothing beyond that. Whether a row exists under a
    *different* tenant is exactly the cross-tenant probe the registry refuses
    to answer.
    """


@dataclass(frozen=True)
class HospitalRecipient:
    """One approved reader of one tenant's finished previsits."""

    recipient_id: str
    tenant_id: uuid.UUID
    dpa_ref: str
    approval_ref: str
    #: The DPA clause stating the hospital's own retention of a fetched copy.
    retention_ref: str


@dataclass(frozen=True)
class RecipientRegistry:
    """The loaded registry. Empty is the shipping state and a valid one."""

    rows: tuple[HospitalRecipient, ...]

    def for_tenant(self, tenant_id: uuid.UUID) -> HospitalRecipient:
        for row in self.rows:
            if row.tenant_id == tenant_id:
                return row
        raise RecipientNotRegistered("no approved previsit-output reader for this tenant")


def _require_ref(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RecipientRegistryError(f"a recipient row must declare {field!r}")
    if _REF.match(value) is None:
        raise RecipientRegistryError(
            f"{field!r} must be id-shaped; the refused value is not echoed (invariant 6)"
        )
    return value


def _row(raw: object) -> HospitalRecipient:
    if not isinstance(raw, dict):
        raise RecipientRegistryError("each recipient must be a mapping")
    unknown = set(raw) - _ROW_KEYS
    if unknown:
        raise RecipientRegistryError(f"unknown recipient keys: {sorted(unknown)}")
    refs = {field: _require_ref(raw, field) for field in _REQUIRED_REFS}
    raw_tenant = raw.get("tenant_id")
    if not isinstance(raw_tenant, str):
        raise RecipientRegistryError("a recipient row must declare 'tenant_id'")
    try:
        tenant_id = uuid.UUID(raw_tenant)
    except ValueError:
        raise RecipientRegistryError("'tenant_id' must be a UUID") from None
    return HospitalRecipient(tenant_id=tenant_id, **refs)


def load_recipients(path: Path) -> RecipientRegistry:
    """Load and validate the registry, or refuse.

    A missing file is a refusal rather than an empty registry: "there is no
    file" and "there are no approved readers" happen to have the same effect
    today, but only one of them is a statement somebody made on purpose.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        raise RecipientRegistryError(
            "the previsit-output recipient registry is unreadable; the path is not echoed"
        ) from None
    document = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(document, dict):
        raise RecipientRegistryError("the recipient registry must be a mapping")
    unknown = set(document) - _TOP_LEVEL_KEYS
    if unknown:
        raise RecipientRegistryError(f"unknown top-level keys: {sorted(unknown)}")
    if document.get("version") != 1:
        raise RecipientRegistryError("the recipient registry must declare 'version: 1'")
    entries = document.get("recipients")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise RecipientRegistryError("'recipients' must be a list")
    rows = tuple(_row(entry) for entry in entries)
    tenants = [row.tenant_id for row in rows]
    if len(set(tenants)) != len(tenants):
        raise RecipientRegistryError(
            "a tenant may register at most one previsit-output reader: two rows would "
            "make the agreement a fetch is audited under ambiguous"
        )
    ids = [row.recipient_id for row in rows]
    if len(set(ids)) != len(ids):
        raise RecipientRegistryError("recipient ids must be unique")
    return RecipientRegistry(rows=rows)
