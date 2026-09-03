"""The per-tenant connector destination registry (INT-160; files/10 inv. 46).

A connector destination is where full clinical notes go, so the schema is the
control. Three properties, each enforced by a validator rather than by review:

1. **There is no field a URL fits into.** ``host`` is a public DNS name and
   nothing else — an IP literal, a scheme, a port suffix, userinfo, a path, a
   wildcard or a single unqualified label (``openbao``) all fail to validate.
   files/10 §4's SSRF paragraph is about a `tenant_admin` typing
   ``169.254.169.254`` or ``http://openbao:8200`` into a free-text box; the
   answer is that the box does not exist. ``base_path`` is the one place a
   path is expressible and it is a strict segment grammar with no ``..``, no
   query, no fragment and no second slash, so it cannot name a host.
2. **A row is bound to a signed agreement and a recorded approval.**
   ``dpa_ref`` and ``approval_ref`` are required and non-empty. A connector
   endpoint change is a tier-3 action in files/10 §8's matrix; the row is
   where that decision is recorded, and :meth:`ConnectorDestination.egress_entry`
   feeds ``approval_ref`` straight into the ``phi_exception_approval`` slot the
   INT-018 allow-list already demands of any PHI-enabled row.
3. **The credential is a reference, never a value.** ``credential_ref`` and
   ``client_cert_ref`` are OpenBao paths under ``connectors/``; the material is
   read at send time and never persists in this file, this process's config or
   any receipt (invariant 14).

The registry composes with the INT-018 egress guard rather than replacing it
(ADR-026): :meth:`egress_entry` returns the *same* :class:`AllowlistEntry`
type the vendor allow-list validates, so one implementation of "what an entry
means" serves both lists and the two cannot drift. What the registry adds is
the tenant dimension — ADR-025's fifth bypass, *the right host addressed for
the wrong reason*, in the form it actually takes here: a host that is
contracted, allow-listed and approved, for a different hospital.

``infra/connectors/destinations.yaml`` ships with zero rows because no DPA is
signed and no hospital endpoint is contracted. That is the whole content of
the mechanism today, and it is the fail-closed state, not a gap.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml
from intake_platform.egress import AllowlistEntry, EgressPurpose
from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "CREDENTIAL_ROOT",
    "ConnectorDestination",
    "DestinationNotRegistered",
    "DestinationRegistry",
    "RegistryError",
    "is_ref_shaped",
    "load_destinations",
    "require_path_shape",
]

#: Every OpenBao path a connector row may name lives under this prefix, which
#: is what the per-service policy grants read on. A row pointing anywhere else
#: would be a request for a secret this framework has no business reading.
CREDENTIAL_ROOT = "connectors/"

#: Ids, refs and OpenBao paths: the audit chain's own shape (invariant 6), so
#: nothing that reaches a log or a receipt can carry narrative.
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")

#: A DNS name with at least two labels. The trailing ``+`` on the group is
#: what refuses a single unqualified label — ``openbao``, ``unleash``,
#: ``localhost`` — which is how an internal service is addressed.
_HOST = re.compile(
    r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
    r"(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)

#: Path segments only. ``?``, ``#``, whitespace, ``//`` and an empty segment
#: all fail; ``..`` matches the character class, so it is refused separately.
_PATH = re.compile(r"^(/[A-Za-z0-9._~-]+)*$")

_MAX_PATH_CHARS = 128


class RegistryError(Exception):
    """The registry file or the rows it holds violate a policy invariant."""


class DestinationNotRegistered(Exception):
    """No row answers to this ``(tenant_id, endpoint_id)`` pair.

    The message names the endpoint id — registry data, never patient data —
    and never says whether the id exists under a different tenant: that
    distinction is exactly the cross-tenant probe the registry refuses.
    """


def is_ref_shaped(value: str) -> bool:
    """Id-shaped: what may cross into a log, a receipt or an audit entry."""
    return _REF.match(value) is not None


def require_path_shape(value: str) -> str:
    """The request-path grammar, shared by the schema validator and the sender.

    The sender re-checks what an adapter built, because an adapter is the one
    component here that is written per hospital: a path assembled from a
    receiver's own identifier is exactly where a second destination could be
    smuggled back in past a schema that only ever saw ``base_path``.
    """
    if len(value) > _MAX_PATH_CHARS:
        raise ValueError(f"request path exceeds {_MAX_PATH_CHARS} characters")
    if _PATH.match(value) is None:
        raise ValueError(
            "a request path must be zero or more '/segment' parts (no query, no "
            "fragment, no whitespace, no empty segment) — a path is not a place "
            "to name a host"
        )
    if any(segment == ".." for segment in value.split("/")):
        raise ValueError("a request path must not traverse ('..')")
    return value


def _ref(field_name: str, value: str) -> str:
    if _REF.match(value) is None:
        raise ValueError(
            f"{field_name} must be id-shaped ([A-Za-z0-9._:/@-], 1-128 chars, no spaces)"
        )
    return value


class ConnectorDestination(BaseModel):
    """One registered destination: who may push, where, under what agreement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    endpoint_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    adapter_id: str = Field(min_length=1)
    host: str = Field(min_length=1)
    port: int = Field(default=443, ge=1, le=65535)
    protocol: Literal["https"] = "https"
    base_path: str = ""
    #: Transport authentication. ``mtls`` is the only mode this framework
    #: implements; SMART backend services arrives with the FHIR adapter
    #: (INT-161) as an added member, never as a relaxation of this one.
    auth_mode: Literal["mtls"]
    credential_ref: str = Field(min_length=1)
    client_cert_ref: str = Field(min_length=1)
    #: The consent scope every push to this destination must clear
    #: (invariant 4). Checked per push, never cached across pushes.
    consent_scope: str = Field(min_length=1)
    #: The executed data-processing agreement this destination is bound to.
    dpa_ref: str = Field(min_length=1)
    #: The recorded tier-3 approval that registered the row (files/10 §8).
    approval_ref: str = Field(min_length=1)
    #: Whether the *receiver's* DPA states that it honours an idempotency key.
    #: No default: "we sent it twice and the hospital deduplicated" is not a
    #: guarantee this system can make on the hospital's behalf, so the answer
    #: is written down per endpoint or the row does not load.
    receiver_idempotency: Literal["honoured_per_dpa", "not_declared"]

    @field_validator("host")
    @classmethod
    def _public_hostname(cls, value: str) -> str:
        host = value.strip().lower().rstrip(".")
        try:
            ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            pass
        else:
            raise ValueError(
                "an IP literal is never a registered destination: files/10 §4 denies "
                "literal IPs and private/link-local/metadata ranges outright"
            )
        if _HOST.match(host) is None:
            raise ValueError(
                "host must be a public DNS name with at least two labels — no scheme, "
                "no port, no userinfo, no path, no wildcard, and no bare service name"
            )
        return host

    @field_validator("base_path")
    @classmethod
    def _safe_path(cls, value: str) -> str:
        return require_path_shape(value)

    @field_validator("endpoint_id", "tenant_id", "adapter_id", "consent_scope")
    @classmethod
    def _id_shaped(cls, value: str) -> str:
        return _ref("identifier", value)

    @field_validator("dpa_ref", "approval_ref")
    @classmethod
    def _binding_refs(cls, value: str) -> str:
        return _ref("binding reference", value)

    @field_validator("credential_ref", "client_cert_ref")
    @classmethod
    def _credential_paths(cls, value: str) -> str:
        _ref("credential reference", value)
        if not value.startswith(CREDENTIAL_ROOT):
            raise ValueError(
                f"a credential reference must live under {CREDENTIAL_ROOT!r} — the only "
                "OpenBao subtree the connector policy grants read on"
            )
        return value

    def egress_entry(self) -> AllowlistEntry:
        """This row as an INT-018 allow-list entry.

        The same type, so the same validators run: an IP-literal host is
        refused a second time, and ``phi_allowed: true`` is refused without an
        approval reference. Nothing here widens the vendor allow-list — the
        entry is built per send and lives only for that request.
        """
        return AllowlistEntry(
            name=f"connector:{self.endpoint_id}",
            host=self.host,
            port=self.port,
            protocol=self.protocol,
            purpose_id=EgressPurpose.CLINICAL_RECORD_PUSH,
            purpose=f"clinical record push to the registered destination {self.endpoint_id}",
            basis=f"KVKK-8/9; processor under {self.dpa_ref}; approved as {self.approval_ref}",
            phi_allowed=True,
            phi_exception_approval=self.approval_ref,
        )


class _RegistryFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    destinations: list[ConnectorDestination] = Field(default_factory=list)


class DestinationRegistry:
    """The loaded rows, addressable only by ``(tenant_id, endpoint_id)``."""

    def __init__(self, destinations: Iterable[ConnectorDestination]) -> None:
        by_id: dict[str, ConnectorDestination] = {}
        for row in destinations:
            if row.endpoint_id in by_id:
                raise RegistryError(
                    f"duplicate endpoint_id {row.endpoint_id!r}: an endpoint id is the "
                    "handle a console renders and an audit row records, so it names one "
                    "destination globally — never one per tenant"
                )
            by_id[row.endpoint_id] = row
        self._by_id = by_id

    def resolve(self, *, tenant_id: str, endpoint_id: str) -> ConnectorDestination:
        row = self._by_id.get(endpoint_id)
        if row is None or row.tenant_id != tenant_id:
            raise DestinationNotRegistered(
                f"no destination {endpoint_id!r} is registered for this tenant"
            )
        return row

    def for_tenant(self, tenant_id: str) -> tuple[ConnectorDestination, ...]:
        """The rows a console renders as a select — the only way to choose one."""
        return tuple(row for row in self._by_id.values() if row.tenant_id == tenant_id)

    def __len__(self) -> int:
        return len(self._by_id)


def load_destinations(path: Path) -> DestinationRegistry:
    """Load + validate the registry file. A malformed file raises rather than
    degrading to an empty (and therefore silently send-nothing) registry."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RegistryError(f"{path} is not a mapping")
    parsed = _RegistryFile.model_validate(raw)
    return DestinationRegistry(parsed.destinations)
