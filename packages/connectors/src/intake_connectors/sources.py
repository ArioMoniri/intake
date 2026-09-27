"""Clinical **read** sources: an on-premises hospital host, and the narrower
guard that is the only thing allowed to reach one.

Why this module exists at all, stated plainly, because the alternative reading
is that someone routed around the egress guard.

``infra/security/egress-allowlist.yaml`` and :class:`~intake_platform.egress.
EgressPolicy` cannot express a hospital's on-premises appointment API, and
that is ADR-025 working rather than a gap. The measured destination is
``10.150.0.42:8091`` over plaintext HTTP, and the vendor list refuses each of
those three properties independently: :class:`~intake_platform.egress.
AllowlistEntry` rejects an IP-literal host at validation, ``EgressPolicy.check``
rejects one again at call time, ``authorize`` rejects any answer inside
``10.0.0.0/8``, and ``protocol`` is ``Literal["https"]``. Weakening any of
those would weaken the control that makes invariant 19 true for every vendor
call in the system, to serve one hospital LAN.

So the rule is kept and a second, **strictly narrower** policy is added beside
it. The containment property is the point, and it is tested in both
directions:

* ``EgressPolicy`` reaches public **hostnames** and refuses every literal.
* :class:`LanSourcePolicy` reaches **private IPv4 literals** that appear in
  its own registry, and refuses every hostname.

The two therefore address disjoint sets of destinations, and neither is a
route around the other. What this policy gives up in exchange for accepting a
literal, it gains back elsewhere: it performs **no DNS at all**, so the
resolve-and-pin machinery — and the rebinding attack it defends against — has
no surface here; there is nothing to resolve and nothing to poison.

Everything else is kept from ADR-025 unchanged. A row declares a purpose from
the closed vocabulary and a caller must present a matching one; a row is bound
to a signed DPA and a recorded tier-3 approval; carrying clinical identifiers
over plaintext needs its own second approval, because that is a decision a
human takes and records rather than a default a schema hands out; the runtime
denies unless an operator has said so as well (``INTAKE_ALLOW_LAN_SOURCE``);
every decision lands in the same KVKK transfer register the vendor guard
writes to; and a denial raises the same :class:`~intake_platform.egress.
EgressDenied`, so no caller can catch one guard's refusal and miss the other's.

``infra/connectors/sources.yaml`` ships with zero rows, exactly as
``destinations.yaml`` does. Registering the Acıbadem source needs three values
no agent may mint: a consent purpose id for reading a patient's hospital
record (blocked by HUMAN_BLOCKERS HB-L27 — ``docs/legal/`` is unsigned, so no
new consent can be granted at all), a tier-3 approval reference for the read,
and a second approval for the plaintext transport. That is the fail-closed
state, not a gap.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
import yaml
from intake_platform.consent.registry import UnknownPurposeError, resolve_scope
from intake_platform.egress import (
    EGRESS_DENIED_TOTAL,
    DataClass,
    Decision,
    EgressContext,
    EgressDenied,
    EgressPurpose,
    LoggingTransferLog,
    TransferLog,
    TransferRecord,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from intake_connectors.destinations import CREDENTIAL_ROOT, is_ref_shaped, require_path_shape

__all__ = [
    "LAN_SOURCE_ENV",
    "LAN_SOURCE_VALUE",
    "ClinicalSource",
    "LanSourcePolicy",
    "SourceNotRegistered",
    "SourceRegistry",
    "SourceRegistryError",
    "lan_source_client",
    "lan_source_transport",
    "load_sources",
]

#: The runtime half of default-deny-twice, mirroring ``INTAKE_ALLOW_PHI_EGRESS``.
#: A registered row is a configuration decision; this is an operator saying so
#: on the box that is about to make the call.
LAN_SOURCE_ENV = "INTAKE_ALLOW_LAN_SOURCE"
LAN_SOURCE_VALUE = "explicit-yes"

_TIMEOUT_S = 10.0

#: The only address space a clinical read source may live in. Deliberately not
#: "anything ``ipaddress`` calls private": ``127.0.0.0/8`` reaches this
#: process's own sidecars and ``169.254.0.0/16`` reaches the cloud metadata
#: endpoint, and those two are the SSRF targets the literal ban was written
#: against in the first place. A hospital LAN is RFC 1918 and nothing else.
_PERMITTED_NETWORKS: tuple[ipaddress.IPv4Network, ...] = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)


class SourceRegistryError(Exception):
    """The registry file or the rows it holds violate a policy invariant."""


class SourceNotRegistered(Exception):
    """No row answers to this ``(tenant_id, source_id)`` pair.

    Like :class:`~intake_connectors.destinations.DestinationNotRegistered`,
    the message never says whether the id exists under a different tenant:
    that distinction is the cross-tenant probe the registry refuses.
    """


def require_private_ipv4(value: str) -> str:
    """The one address grammar a clinical read source may use.

    A hostname fails here, which is what makes this policy unable to reach a
    public host; a public literal fails too, which is what keeps it from
    becoming a general-purpose exemption.
    """
    candidate = value.strip()
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        raise ValueError(
            "a clinical read source is addressed by a private IPv4 literal and by "
            "nothing else — a hostname belongs on the vendor allow-list, where it is "
            "resolved and pinned (ADR-025)"
        ) from None
    if address.version != 4:
        raise ValueError("a clinical read source address must be IPv4")
    if not any(address in network for network in _PERMITTED_NETWORKS):
        raise ValueError(
            "a clinical read source address must be inside RFC 1918 space "
            "(10/8, 172.16/12, 192.168/16) — loopback, link-local and public "
            "literals are refused, and the link-local range is where the cloud "
            "metadata endpoint lives"
        )
    return str(address)


class ClinicalSource(BaseModel):
    """One on-premises system this deployment may READ a patient record from.

    The schema is the control, in the same three ways the push registry's is:
    there is no field a URL fits into, the row is bound to a signed agreement
    and a recorded approval, and the credential is a reference rather than a
    value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    adapter_id: str = Field(min_length=1)
    #: A private IPv4 literal. Not a hostname, and not a URL.
    address: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    protocol: Literal["http", "https"] = "https"
    #: The one place a path is expressible, under the same segment grammar the
    #: push registry uses: no query, no fragment, no traversal, no second
    #: slash — so it cannot name a host.
    base_path: str = ""
    #: The consent scope every read from this source must clear (invariant 4),
    #: validated against the closed INT-038 purpose registry at load time. A
    #: row naming a purpose no ``docs/legal/`` text binds cannot be
    #: registered, so the read it would authorise cannot happen.
    consent_scope: str = Field(min_length=1)
    #: An OpenBao path under ``connectors/``. What resolves it is injected:
    #: production reads OpenBao, and the demo tier reads a named environment
    #: variable through ``EnvCredentialResolver``. Either way the row holds no
    #: value (invariant 14).
    credential_ref: str = Field(min_length=1)
    dpa_ref: str = Field(min_length=1)
    approval_ref: str = Field(min_length=1)
    #: Required when ``protocol`` is ``http``. A clinical feed carrying TC
    #: Kimlik numbers, mobile numbers and names over an unencrypted channel is
    #: a risk a named human accepts on the record, not a default.
    plaintext_approval: str | None = None

    @field_validator("address")
    @classmethod
    def _private_literal(cls, value: str) -> str:
        return require_private_ipv4(value)

    @field_validator("base_path")
    @classmethod
    def _safe_path(cls, value: str) -> str:
        return require_path_shape(value)

    @field_validator("source_id", "tenant_id", "adapter_id")
    @classmethod
    def _id_shaped(cls, value: str) -> str:
        if not is_ref_shaped(value):
            raise ValueError("identifier must be id-shaped (no whitespace, no prose)")
        return value

    @field_validator("dpa_ref", "approval_ref", "plaintext_approval")
    @classmethod
    def _binding_refs(cls, value: str | None) -> str | None:
        if value is not None and not is_ref_shaped(value):
            raise ValueError("binding reference must be id-shaped")
        return value

    @field_validator("consent_scope")
    @classmethod
    def _registered_purpose(cls, value: str) -> str:
        try:
            resolve_scope(value)
        except UnknownPurposeError:
            raise ValueError(
                f"{value!r} is not a registered consent purpose — the INT-038 registry "
                "is closed (files/06 §2) and a read cannot be authorised by a scope "
                "no docs/legal text binds"
            ) from None
        return value

    @field_validator("credential_ref")
    @classmethod
    def _credential_path(cls, value: str) -> str:
        if not value.startswith(CREDENTIAL_ROOT) or not is_ref_shaped(value):
            raise ValueError(
                f"a credential reference must be an id-shaped path under {CREDENTIAL_ROOT!r}"
            )
        return value

    @model_validator(mode="after")
    def _plaintext_is_a_decision(self) -> ClinicalSource:
        if self.protocol == "http" and not self.plaintext_approval:
            raise ValueError(
                "protocol: http requires plaintext_approval naming a recorded human "
                "decision — clinical identifiers on an unencrypted channel is a risk "
                "someone accepts by name, never a schema default"
            )
        if self.protocol == "https" and self.plaintext_approval:
            raise ValueError(
                "plaintext_approval is meaningless on an https row; remove it rather "
                "than leaving an approval that approves nothing"
            )
        return self

    def egress_context(self) -> EgressContext:
        """What this source's traffic is, and why it exists.

        Always PHI: the feed carries names, mobile numbers and TC Kimlik
        numbers, and declaring anything softer would be a declaration the data
        contradicts.
        """
        return EgressContext(purpose=EgressPurpose.CLINICAL_RECORD_READ, data_class=DataClass.PHI)

    def url(self, path: str) -> httpx.URL:
        """The absolute URL for one request, built from the row and the path.

        ``base_path`` and ``path`` are both re-checked, because a path
        assembled from a receiver's own identifier is exactly where a second
        destination could be smuggled past a schema that only ever saw the
        registered prefix.
        """
        require_path_shape(self.base_path)
        require_path_shape(path)
        return httpx.URL(
            scheme=self.protocol,
            host=self.address,
            port=self.port,
            path=f"{self.base_path}{path}" or "/",
        )


class SourceRegistry:
    """The rows this deployment may read from, addressed by tenant and id."""

    def __init__(self, sources: Iterable[ClinicalSource]) -> None:
        self._rows = tuple(sources)
        seen: set[tuple[str, str]] = set()
        for row in self._rows:
            key = (row.tenant_id, row.source_id)
            if key in seen:
                raise SourceRegistryError(
                    f"duplicate source row for {row.source_id!r} — two rows for one id "
                    "means the effective destination depends on file order"
                )
            seen.add(key)

    @property
    def rows(self) -> tuple[ClinicalSource, ...]:
        return self._rows

    def resolve(self, *, tenant_id: str, source_id: str) -> ClinicalSource:
        for row in self._rows:
            if row.tenant_id == tenant_id and row.source_id == source_id:
                return row
        raise SourceNotRegistered(f"no clinical read source registered as {source_id!r}")


class _SourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    sources: list[ClinicalSource] = Field(default_factory=list)


def load_sources(path: Path) -> SourceRegistry:
    """Load and validate ``infra/connectors/sources.yaml`` (or a test copy).

    A malformed file raises rather than degrading to allow-nothing-quietly:
    the two are indistinguishable in behaviour and very different in cause.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SourceRegistry(_SourceFile.model_validate(raw).sources)


class LanSourcePolicy:
    """Default-deny address/port/purpose policy over exactly one source row.

    One row rather than a list, on purpose: a client is built for one source,
    and a policy that held several would let a bug in path construction reach
    a different hospital's system with the first one's credential.
    """

    def __init__(self, source: ClinicalSource) -> None:
        self._source = source

    @property
    def tier(self) -> str:
        return f"lan-source:{self._source.source_id}"

    @property
    def source(self) -> ClinicalSource:
        return self._source

    def check(self, host: str, port: int, context: EgressContext) -> Decision:
        """The whole predicate. No DNS — there is nothing here to resolve."""
        candidate = host.strip()
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return Decision(
                False,
                "a clinical read source is addressed by its registered literal; a "
                "hostname is never reachable through this policy (it would need a "
                "lookup this guard deliberately does not perform)",
                candidate,
                port,
            )
        if candidate != self._source.address or port != self._source.port:
            return Decision(
                False,
                "address/port is not the registered clinical read source (default deny)",
                candidate,
                port,
            )
        if context.purpose is not EgressPurpose.CLINICAL_RECORD_READ:
            return Decision(
                False,
                f"purpose mismatch: this row exists for {EgressPurpose.CLINICAL_RECORD_READ} "
                f"and the caller declared {context.purpose} — a destination is not a "
                "permission",
                candidate,
                port,
                EgressPurpose.CLINICAL_RECORD_READ,
            )
        if os.environ.get(LAN_SOURCE_ENV) != LAN_SOURCE_VALUE:
            return Decision(
                False,
                f"a registered clinical read source additionally requires "
                f"{LAN_SOURCE_ENV}={LAN_SOURCE_VALUE} at runtime (default deny)",
                candidate,
                port,
                EgressPurpose.CLINICAL_RECORD_READ,
            )
        return Decision(
            True,
            f"registered clinical read source: {self._source.source_id} (tier {self.tier})",
            candidate,
            port,
            EgressPurpose.CLINICAL_RECORD_READ,
        )


class _LanSourceTransport(httpx.BaseTransport):
    """httpx transport that consults :class:`LanSourcePolicy` before any bytes
    leave, and records every decision in the KVKK transfer register."""

    def __init__(
        self,
        policy: LanSourcePolicy,
        context: EgressContext,
        inner: httpx.BaseTransport,
        transfer_log: TransferLog,
    ) -> None:
        self._policy = policy
        self._context = context
        self._inner = inner
        self._transfer_log = transfer_log

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        decision = self._policy.check(host, port, self._context)
        # Header-declared size, never the body; and zero for a request that
        # transferred nothing because it was denied.
        bytes_out = int(request.headers.get("content-length", 0)) if decision.allowed else 0
        self._transfer_log.record(
            TransferRecord(
                ts=datetime.now(UTC),
                host=decision.host,
                port=decision.port,
                purpose=decision.purpose,
                data_class=self._context.data_class,
                bytes_out=bytes_out,
                decision="allow" if decision.allowed else "deny",
                reason=decision.reason,
                tier=self._policy.tier,
            )
        )
        if not decision.allowed:
            # The same counter and the same exception as the vendor guard: a
            # caller must not be able to catch one refusal and miss the other,
            # and an operator must not have two denial series to watch.
            EGRESS_DENIED_TOTAL.inc()
            raise EgressDenied(
                f"egress denied for {decision.host}:{decision.port} — {decision.reason}"
            )
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def lan_source_transport(
    policy: LanSourcePolicy,
    context: EgressContext,
    inner: httpx.BaseTransport | None = None,
    transfer_log: TransferLog | None = None,
) -> httpx.BaseTransport:
    """The enforcing transport for one source row and one declared purpose."""
    return _LanSourceTransport(
        policy,
        context,
        inner if inner is not None else httpx.HTTPTransport(),
        transfer_log if transfer_log is not None else LoggingTransferLog(),
    )


def lan_source_client(
    source: ClinicalSource,
    inner: httpx.BaseTransport | None = None,
    transfer_log: TransferLog | None = None,
    *,
    timeout: httpx.Timeout | float | None = None,
) -> httpx.Client:
    """An ``httpx.Client`` over :func:`lan_source_transport`, redirects off.

    The keyword surface is narrow rather than ``**kwargs`` for the reason
    ``guarded_client`` gives: a passthrough would let a caller hand
    ``httpx.Client`` a ``proxy``, a ``base_url`` or its own ``transport`` and
    quietly route around the guard. Redirects stay off because a redirect is a
    destination the caller never named, and on a plaintext LAN it is a
    destination anyone on the wire can choose.
    """
    return httpx.Client(
        transport=lan_source_transport(
            LanSourcePolicy(source), source.egress_context(), inner, transfer_log
        ),
        follow_redirects=False,
        timeout=timeout if timeout is not None else httpx.Timeout(_TIMEOUT_S),
    )
