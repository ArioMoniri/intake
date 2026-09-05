"""Egress policy: the vendor allow-list as data + default-deny enforcement (INT-018).

files/10 §4 and CLAUDE.md invariants 14/19: only contracted vendors are
reachable from any INTAKE process, the PHI path reaches **no** external model
or speech vendor at all (self-hosting, 00_STATE D11), and every egress
decision is logged as KVKK transfer evidence — hosts, purposes and byte counts
only, never payloads, paths or query strings (invariant 6).

The layers, so that no single config mistake silently widens the boundary:

1. **Validation** — the allow-list is pydantic-checked at load: IP-literal
   hosts are refused (files/10 §4 denies literal IPs and private/link-local/
   metadata ranges), a ``*`` in a host is refused unless the entry declares
   ``glob: true`` (and then only the leading ``*.suffix`` form), every row
   declares a ``purpose_id`` from a closed vocabulary, and ``phi_allowed:
   true`` is refused without a ``phi_exception_approval`` naming a recorded
   human decision.
2. **Purpose and data class** — a destination is not a permission. The caller
   states what it is sending (:class:`DataClass`) and why
   (:class:`EgressPurpose`); a row serves exactly one purpose, and personal
   data — pseudonymous included, because KVKK treats it as personal — only
   moves to a row that is ``phi_allowed``. An allow-listed host addressed for
   the wrong reason is refused as firmly as an unlisted one.
3. **Runtime double-gate** — even a validated ``phi_allowed`` entry denies
   unless ``INTAKE_ALLOW_PHI_EGRESS=explicit-yes`` is set. Default deny twice:
   config alone is not enough, an operator must also say so at runtime.
4. **Resolve once and pin** — a hostname allow-list that hands the hostname to
   the socket layer has checked a *spelling*, not a destination. The policy
   resolves the authorised host itself, refuses an answer inside a
   private/loopback/link-local/metadata range (the SSRF shape files/10 §4
   describes, `169.254.169.254` included), and then connects to the pinned
   address with SNI and ``Host`` still naming the hostname — so certificate
   verification is unchanged and there is no second lookup for a rebinding
   attack to win. The lookup happens *after* the allow-list check, so a
   refused destination never becomes a DNS query carrying an attacker's name.
5. **Vendor-LLM pin** — :func:`assert_dev_only_vendors` refuses any list where
   an anthropic/openai/google API host is PHI-enabled or appears on the PHI
   path at all: those adapters are the mock/dev path only (invariant 19).

:func:`guarded_transport` wraps ``httpx`` so services adopt enforcement by
construction, and :func:`guarded_client` builds a client with redirects off
(files/10 §4). A transport carrying personal data may not be pointed at the
forward proxy at all — see :func:`guarded_transport` — because that is the one
configuration in which neither enforcement point does the resolve-and-pin.

Redirects are safe either way by composition: httpx follows one
by issuing a new request through the same transport, so every hop is checked,
resolved and pinned independently.

The deployed forward proxy (``infra/docker-compose.egress.yml``, profile
``egress``) enforces the *same* file at the network tier — its squid config is
generated from ``infra/security/egress-allowlist.yaml`` by
``scripts/security/render_egress_proxy_conf.py`` so the two enforcement points
cannot drift, and ``tests/infra/test_egress_proxy.py`` decides a table of
hosts through both. Pass ``proxy=`` to :func:`guarded_transport` when a
process sits behind it: the hostname then survives to the CONNECT line (which
is what squid matches on, and an IP literal would match nothing) and the proxy
does the resolve-and-pin files/10 §4 assigns it, while the allow-list, purpose
and data-class checks still run in process. Without that parameter the two
controls would refuse each other's traffic, which is a trap worth removing
rather than documenting.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

import httpx
import yaml
from prometheus_client import Counter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "DENIED_RANGES",
    "VENDOR_LLM_DOMAINS",
    "AllowlistEntry",
    "Authorization",
    "DataClass",
    "Decision",
    "EgressAllowlist",
    "EgressConfigError",
    "EgressContext",
    "EgressDenied",
    "EgressPolicy",
    "EgressPurpose",
    "InMemoryTransferLog",
    "LoggingTransferLog",
    "Pin",
    "Resolver",
    "Tier",
    "TransferLog",
    "TransferRecord",
    "assert_dev_only_vendors",
    "default_resolver",
    "guarded_client",
    "guarded_transport",
    "load_allowlist",
]

_LOGGER = logging.getLogger("intake_platform.egress")

_PHI_EGRESS_ENV = "INTAKE_ALLOW_PHI_EGRESS"
_PHI_EGRESS_VALUE = "explicit-yes"
_DEFAULT_SCHEME_PORTS = {"https": 443, "http": 80}

#: files/10 §5 names egress denials a hard alert; the series is catalogued in
#: observability/metrics_catalog.yaml with `target: "0 (any increase pages)"`.
#: No labels — a host label would make the cardinality of an attack unbounded
#: and hand an attacker a way to write chosen strings into the metric store.
EGRESS_DENIED_TOTAL = Counter(
    "sec_egress_denied_total",
    "Denied egress attempts from the PHI path.",
)

#: The vendor LLM domain families whose adapters are mock/dev only (invariant
#: 19). Matched as suffixes — any host under one of these domains counts —
#: which is deliberately broader than three literal API endpoints, and keeps
#: this module clean under scripts/ci/assert_no_vendor_calls.sh (the INT-001
#: gate that refuses literal vendor endpoint strings outside files/).
VENDOR_LLM_DOMAINS: frozenset[str] = frozenset(
    {
        "anthropic.com",
        "openai.com",
        "googleapis.com",
    }
)

#: Address ranges no resolved answer may fall into (files/10 §4: "denies
#: literal IPs and private / link-local / metadata ranges"). Written out
#: rather than delegated to ``ipaddress.is_global`` because this exact list is
#: also rendered into the proxy's ``acl denied_nets dst`` line, and a control
#: that reads differently at its two enforcement points is one control.
#:
#: The two IPv6 entries worth naming: ``::ffff:0:0/96`` is an IPv4 denial in
#: v6 clothing (``::ffff:169.254.169.254`` reaches the metadata service), and
#: ``64:ff9b::/96`` is NAT64 — a v6 address whose destination is v4.
DENIED_RANGES: tuple[tuple[str, str], ...] = (
    ("0.0.0.0/8", "this-network"),
    ("10.0.0.0/8", "private (RFC 1918)"),
    ("100.64.0.0/10", "shared address space (RFC 6598)"),
    ("127.0.0.0/8", "loopback"),
    ("169.254.0.0/16", "link-local — the cloud metadata endpoint lives here"),
    ("172.16.0.0/12", "private (RFC 1918)"),
    ("192.0.0.0/24", "IETF protocol assignments"),
    ("192.168.0.0/16", "private (RFC 1918)"),
    ("198.18.0.0/15", "benchmarking (RFC 2544)"),
    ("224.0.0.0/4", "multicast"),
    ("240.0.0.0/4", "reserved"),
    ("255.255.255.255/32", "broadcast"),
    ("::/128", "unspecified"),
    ("::1/128", "loopback"),
    ("::ffff:0:0/96", "IPv4-mapped — an IPv4 denial in v6 clothing"),
    ("64:ff9b::/96", "NAT64 — an IPv4 destination behind a v6 address"),
    ("fc00::/7", "unique-local"),
    ("fe80::/10", "link-local"),
    ("ff00::/8", "multicast"),
)

_DENIED_NETWORKS: tuple[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, str], ...] = tuple(
    (ipaddress.ip_network(cidr), why) for cidr, why in DENIED_RANGES
)

Tier = Literal["dev", "phi_path"]

#: Resolve a host to the addresses it currently answers with. Injected so the
#: unit lane never performs a DNS lookup (a lookup in CI is a network call).
Resolver = Callable[[str, int], "Sequence[str]"]


class EgressPurpose(StrEnum):
    """Why an outbound call exists — the KVKK purpose of the transfer.

    Closed on purpose: files/10 §4 records that free-text destinations are the
    console SSRF, and a free-text *purpose* is the transfer-register version
    of the same mistake — a register whose purpose column is prose cannot be
    audited. Every member is declared by a shipped policy artefact and every
    row's purpose is a member (both directions tested): the vendor rows in
    ``infra/security/egress-allowlist.yaml`` for the four vendor purposes, and
    the connector destination schema for ``CLINICAL_RECORD_PUSH``, whose
    destinations are per-tenant data rather than committed rows.
    """

    PACKAGE_REGISTRY = "package_registry"
    SOURCE_CONTROL = "source_control"
    ISSUE_TRACKING = "issue_tracking"
    MODEL_WEIGHTS = "model_weights"
    #: INT-160 / ADR-026. The one purpose whose destinations are NOT vendor
    #: rows: a hospital endpoint is per-tenant data, registered out-of-band and
    #: bound to a signed DPA (files/10 inv. 46), so it never appears in
    #: ``infra/security/egress-allowlist.yaml`` — the connector registry
    #: synthesises an :class:`AllowlistEntry` per send instead, and the vendor
    #: file's own test asserts the stronger direction: this member must not
    #: appear there.
    CLINICAL_RECORD_PUSH = "clinical_record_push"
    #: INT-161 / ADR-027. A SMART backend services token exchange: the second
    #: host a FHIR push needs, and the one that must never carry a clinical
    #: byte. Separated from ``CLINICAL_RECORD_PUSH`` rather than folded into
    #: it because a purpose is a permission — an authorization server that
    #: inherited the push purpose would be a destination approved to receive
    #: patient records, which is ADR-025's fifth bypass granted by a shortcut.
    #: Like the push purpose, its destinations are per-tenant registry data,
    #: so it never appears in ``infra/security/egress-allowlist.yaml`` either.
    CONNECTOR_AUTHORIZATION = "connector_authorization"


class DataClass(StrEnum):
    """What the caller is putting on the wire.

    ``PSEUDONYMOUS`` is personal data, not a middle ground: KVKK treats
    pseudonymised data as personal data because the key exists, so it clears
    the same gate PHI does. Only ``NON_PERSONAL`` travels to a row that is not
    ``phi_allowed``.
    """

    NON_PERSONAL = "non_personal"
    PSEUDONYMOUS = "pseudonymous"
    PHI = "phi"

    @property
    def is_personal(self) -> bool:
        return self is not DataClass.NON_PERSONAL


@dataclass(frozen=True)
class EgressContext:
    """The caller's declaration, bound to a transport rather than a call.

    One transport per outbound integration is exactly the granularity of a
    purpose, and binding it here means a redirect, a retry or a library that
    builds its own requests cannot arrive without one.
    """

    purpose: EgressPurpose
    data_class: DataClass


class EgressConfigError(Exception):
    """The allow-list is structurally valid but violates a policy invariant."""


class EgressDenied(Exception):
    """An outbound request was refused by the egress policy (default deny)."""


def _normalize_host(host: str) -> str:
    """Lowercase + strip the trailing FQDN dot, so matching is by identity,
    not by spelling — ``PyPI.org.`` and ``pypi.org`` are the same host."""
    return host.strip().lower().rstrip(".")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _denied_range_reason(address: str) -> str | None:
    """``None`` when the address may be connected to; otherwise why not."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return f"{address!r} is not an IP address"
    for network, why in _DENIED_NETWORKS:
        if ip.version == network.version and ip in network:
            return why
    return None


def default_resolver(host: str, port: int) -> Sequence[str]:
    """The production resolver: one ``getaddrinfo`` call, addresses only."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:  # pragma: no cover - exercised through the fake resolver
        raise EgressDenied(f"egress denied for {host}:{port} — resolution failed") from exc
    return tuple(dict.fromkeys(str(info[4][0]) for info in infos))


class AllowlistEntry(BaseModel):
    """One vendor row: who is reachable, on which port, and on what legal basis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    protocol: Literal["https"]
    purpose_id: EgressPurpose
    purpose: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    phi_allowed: bool = False
    glob: bool = False
    phi_exception_approval: str | None = None

    @field_validator("host")
    @classmethod
    def _normalized_host(cls, value: str) -> str:
        return _normalize_host(value)

    @model_validator(mode="after")
    def _enforce_shape(self) -> AllowlistEntry:
        if self.glob:
            if not self.host.startswith("*.") or "*" in self.host[2:]:
                raise ValueError(
                    "glob entries take exactly the leading '*.suffix' form — anything "
                    "wider is an implicit allow the reviewer cannot see"
                )
        elif "*" in self.host:
            raise ValueError(
                "host contains '*' but the entry does not declare glob: true — "
                "subdomain matching must be explicit, never accidental"
            )
        if not self.glob and _is_ip_literal(self.host):
            raise ValueError(
                "IP-literal hosts are never allow-listed: files/10 §4 denies literal "
                "IPs and private/link-local/metadata ranges outright"
            )
        if self.phi_allowed and not self.phi_exception_approval:
            raise ValueError(
                "phi_allowed: true requires phi_exception_approval naming a recorded "
                "human decision id (invariant 19 / 00_STATE D11) — and even then the "
                f"runtime denies without {_PHI_EGRESS_ENV}={_PHI_EGRESS_VALUE}"
            )
        return self

    def matches(self, host: str, port: int) -> bool:
        """Exact host identity, or — for declared globs only — one-or-more
        labels under the suffix. ``*.hf.co`` covers ``cdn-lfs-us-1.hf.co``,
        never the bare apex and never ``evilhf.co``."""
        if port != self.port:
            return False
        if self.glob:
            suffix = self.host[1:]  # "*.hf.co" -> ".hf.co"
            return host.endswith(suffix) and len(host) > len(suffix)
        return host == self.host


class _Tiers(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dev: list[AllowlistEntry] = Field(default_factory=list)
    phi_path: list[AllowlistEntry] = Field(default_factory=list)


class EgressAllowlist(BaseModel):
    """The whole file: versioned, two tiers, nothing extra."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    tiers: _Tiers


def load_allowlist(path: Path) -> EgressAllowlist:
    """Load + validate ``infra/security/egress-allowlist.yaml`` (or a test copy).

    Validation failures raise ``pydantic.ValidationError`` — a malformed
    allow-list must stop a service at boot, not degrade to allow-all.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return EgressAllowlist.model_validate(raw)


@dataclass(frozen=True)
class Decision:
    """The auditable outcome of one egress check — safe to log as-is."""

    allowed: bool
    reason: str
    host: str
    port: int
    purpose: EgressPurpose | None = None


@dataclass(frozen=True)
class Pin:
    """The addresses one authorised lookup returned, and the one we will use."""

    host: str
    port: int
    addresses: tuple[str, ...]

    @property
    def address(self) -> str:
        return self.addresses[0]


@dataclass(frozen=True)
class Authorization:
    """A decision plus, when it allows, the pinned destination."""

    decision: Decision
    pin: Pin | None = None

    @property
    def allowed(self) -> bool:
        return self.decision.allowed


@dataclass(frozen=True)
class TransferRecord:
    """One row of the vendor-transfer register feed (KVKK-9, TRANSFER-2024).

    ``{host, purpose, bytes, ts}`` is the acceptance's field list; ``port``,
    ``data_class``, ``decision``, ``reason`` and ``tier`` are what makes a row
    reviewable. The field list is closed and every value is id-shaped or
    numeric, so there is no key a URL, a query string or a body could occupy
    even by accident (invariant 6).
    """

    ts: datetime
    host: str
    port: int
    purpose: EgressPurpose | None
    data_class: DataClass
    bytes_out: int
    decision: Literal["allow", "deny"]
    reason: str
    tier: str


class TransferLog(Protocol):
    """Where transfer records go. INT-224's register reads this feed."""

    def record(self, entry: TransferRecord) -> None: ...


@dataclass
class InMemoryTransferLog:
    """The feed as a list — for the register builder and for tests."""

    entries: list[TransferRecord] = field(default_factory=list)

    def record(self, entry: TransferRecord) -> None:
        self.entries.append(entry)


class LoggingTransferLog:
    """The default sink: one structured record per decision.

    ``sec.egress_allowed`` / ``sec.egress_denied`` are the message names the
    acceptance and files/10 §5 use. The extras are ids and numbers only — a
    URL path or query string is exactly where an identifier would leak, so
    neither is available to write here.
    """

    def record(self, entry: TransferRecord) -> None:
        fields = {
            "ts": entry.ts.isoformat(),
            "host": entry.host,
            "port": entry.port,
            "purpose": str(entry.purpose) if entry.purpose is not None else "-",
            "data_class": str(entry.data_class),
            "bytes_out": entry.bytes_out,
            "decision": entry.decision,
            "reason": entry.reason,
            "tier": entry.tier,
        }
        if entry.decision == "allow":
            _LOGGER.info("sec.egress_allowed", extra=fields)
        else:
            _LOGGER.warning("sec.egress_denied", extra=fields)


class EgressPolicy:
    """Default-deny host/port/purpose policy over one tier of the allow-list."""

    def __init__(
        self,
        entries: list[AllowlistEntry],
        tier: str,
        resolver: Resolver = default_resolver,
    ) -> None:
        self._entries = tuple(entries)
        self._tier = tier
        self._resolver = resolver

    @classmethod
    def for_tier(
        cls,
        allowlist: EgressAllowlist,
        tier: Tier,
        resolver: Resolver = default_resolver,
    ) -> EgressPolicy:
        entries = allowlist.tiers.dev if tier == "dev" else allowlist.tiers.phi_path
        return cls(entries, tier, resolver)

    @property
    def tier(self) -> str:
        return self._tier

    def check(self, host: str, port: int, context: EgressContext) -> Decision:
        """The pure policy predicate: name, port, purpose, data class. No DNS."""
        normalized = _normalize_host(host)
        if not normalized:
            return Decision(False, "empty host (default deny)", normalized, port)
        if _is_ip_literal(normalized):
            return Decision(
                False,
                "literal IP egress is denied outright — private/link-local/metadata "
                "ranges included (files/10 §4)",
                normalized,
                port,
            )
        for entry in self._entries:
            if not entry.matches(normalized, port):
                continue
            if entry.purpose_id is not context.purpose:
                return Decision(
                    False,
                    f"purpose mismatch: '{entry.name}' is allow-listed for "
                    f"{entry.purpose_id} and the caller declared {context.purpose} — "
                    "a destination is not a permission",
                    normalized,
                    port,
                    entry.purpose_id,
                )
            if context.data_class.is_personal and not entry.phi_allowed:
                return Decision(
                    False,
                    f"personal data ({context.data_class}) refused: '{entry.name}' is "
                    "not approved to receive personal data (phi_allowed: false)",
                    normalized,
                    port,
                    entry.purpose_id,
                )
            if entry.phi_allowed and os.environ.get(_PHI_EGRESS_ENV) != _PHI_EGRESS_VALUE:
                return Decision(
                    False,
                    f"phi_allowed entry '{entry.name}' additionally requires "
                    f"{_PHI_EGRESS_ENV}={_PHI_EGRESS_VALUE} at runtime (default deny)",
                    normalized,
                    port,
                    entry.purpose_id,
                )
            return Decision(
                True,
                f"allow-listed: {entry.name} (tier {self._tier})",
                normalized,
                port,
                entry.purpose_id,
            )
        return Decision(
            False,
            f"host is not on the '{self._tier}' egress allow-list (default deny)",
            normalized,
            port,
        )

    def authorize(self, host: str, port: int, context: EgressContext) -> Authorization:
        """Check, then — only for a host the check allowed — resolve and pin.

        The order is the control. Resolving first would turn every refused
        destination into a DNS query carrying an attacker-chosen name to a
        resolver we do not own, which is a working exfiltration channel out of
        a request we correctly denied.
        """
        decision = self.check(host, port, context)
        if not decision.allowed:
            return Authorization(decision)

        addresses = tuple(dict.fromkeys(self._resolver(decision.host, port)))
        if not addresses:
            return Authorization(
                Decision(
                    False,
                    "resolution returned no address (default deny)",
                    decision.host,
                    port,
                    decision.purpose,
                )
            )
        for address in addresses:
            why = _denied_range_reason(address)
            if why is not None:
                # Fail closed on the denied member rather than picking a good
                # one: discarding half a split answer would make the attack a
                # matter of retry timing. A mixed answer is itself the
                # signature. The address is not echoed — it is attacker-chosen
                # text and the reason is enough to act on.
                return Authorization(
                    Decision(
                        False,
                        f"the host resolved into a denied range ({why}) — "
                        "files/10 §4 refuses private/link-local/metadata destinations",
                        decision.host,
                        port,
                        decision.purpose,
                    )
                )
        return Authorization(decision, Pin(decision.host, port, addresses))


def _vendor_families_covered(entry: AllowlistEntry) -> list[str]:
    """Which vendor LLM domain families this entry can reach.

    For a plain entry the host itself is tested as ``domain`` or
    ``*.domain``. For a glob entry the glob's suffix is tested the same way,
    plus the reverse: a glob *wider* than the family (its suffix is a parent
    of the domain) covers it too — ``*.com`` reaches every family.
    """
    subject = entry.host[2:] if entry.glob else entry.host
    covered: list[str] = []
    for domain in sorted(VENDOR_LLM_DOMAINS):
        within = subject == domain or subject.endswith("." + domain)
        wider = entry.glob and domain.endswith("." + subject)
        if within or wider:
            covered.append(domain)
    return covered


def assert_dev_only_vendors(allowlist: EgressAllowlist) -> None:
    """Pin invariant 19: the anthropic|openai|google adapters are mock/dev only.

    Raises :class:`EgressConfigError` when any entry (a) covers a vendor LLM
    domain with ``phi_allowed: true``, or (b) puts a vendor LLM domain on the
    PHI path at all — 07 §F: "no external model or speech vendor on the list
    at all". Call it wherever the allow-list is loaded for enforcement.
    """
    tiers: tuple[tuple[str, list[AllowlistEntry]], ...] = (
        ("dev", allowlist.tiers.dev),
        ("phi_path", allowlist.tiers.phi_path),
    )
    for tier_name, entries in tiers:
        for entry in entries:
            covered = _vendor_families_covered(entry)
            if not covered:
                continue
            if entry.phi_allowed:
                raise EgressConfigError(
                    f"entry '{entry.name}' covers vendor LLM domain(s) {covered} with "
                    "phi_allowed: true — those adapters are the mock/dev path only, "
                    "blocked on the PHI path by this allow-list (invariant 19)"
                )
            if tier_name == "phi_path":
                raise EgressConfigError(
                    f"entry '{entry.name}' puts vendor LLM domain(s) {covered} on the "
                    "PHI path — the PHI path is self-hosted end to end "
                    "(invariant 19 / 00_STATE D11)"
                )


def _pinned_request(request: httpx.Request, pin: Pin) -> httpx.Request:
    """A copy of the request aimed at the pinned address.

    The URL host becomes the address, so the socket layer performs no second
    lookup. ``Host`` is preserved (constructing with ``stream=`` populates no
    automatic headers, so the caller's own ``Host`` survives untouched) and
    ``sni_hostname`` is the httpcore extension that decides both the TLS SNI
    and the name the certificate is verified against — pinning the address
    therefore removes a lookup rather than weakening verification.

    A copy, never a mutation: httpx assigns ``response.request`` from the
    object it built, so mutating in place would make a relative ``Location``
    resolve against the pinned address on the next hop.
    """
    return httpx.Request(
        method=request.method,
        url=request.url.copy_with(host=pin.address),
        headers=request.headers,
        stream=request.stream,
        extensions={**request.extensions, "sni_hostname": pin.host},
    )


class _GuardedTransport(httpx.BaseTransport):
    """httpx transport that consults the policy before any bytes leave.

    Composition keeps CI vendor-free: tests wrap ``httpx.MockTransport``; the
    default wraps a real ``httpx.HTTPTransport``. Redirect hops re-enter
    ``handle_request``, so every hop is checked, resolved and pinned
    independently — a pin never outlives the request it was authorised for.
    """

    def __init__(
        self,
        policy: EgressPolicy,
        context: EgressContext,
        inner: httpx.BaseTransport,
        transfer_log: TransferLog,
        pin_here: bool = True,
    ) -> None:
        self._policy = policy
        self._context = context
        self._inner = inner
        self._transfer_log = transfer_log
        self._pin_here = pin_here

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        port = request.url.port or _DEFAULT_SCHEME_PORTS.get(request.url.scheme, 0)
        if self._pin_here:
            authorization = self._policy.authorize(host, port, self._context)
            decision, pin = authorization.decision, authorization.pin
        else:
            # Behind the forward proxy the hostname must survive to the CONNECT
            # line — the proxy matches on it, and an IP literal would be denied
            # by its own ACLs. files/10 §4 gives that tier the resolve-and-pin
            # job ("resolves once and pins, re-validating on connect"), so
            # doing it here as well would break the composition rather than
            # double it. The allow-list, purpose and data-class checks still
            # run in process; the proxy's `denied_nets dst` ACL is what refuses
            # a hostname that resolves into a private or metadata range.
            decision, pin = self._policy.check(host, port, self._context), None
        # bytes_out only for requests that actually leave; a denied request
        # transferred nothing. Header-declared size — never the body itself.
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
            EGRESS_DENIED_TOTAL.inc()
            raise EgressDenied(
                f"egress denied for {decision.host}:{decision.port} — {decision.reason}"
            )
        outbound = _pinned_request(request, pin) if pin is not None else request
        return self._inner.handle_request(outbound)

    def close(self) -> None:
        self._inner.close()


def guarded_transport(
    policy: EgressPolicy,
    context: EgressContext,
    inner: httpx.BaseTransport | None = None,
    transfer_log: TransferLog | None = None,
    proxy: str | None = None,
) -> httpx.BaseTransport:
    """Build the enforcing transport for one declared purpose and data class.

    Pass ``inner`` to compose (tests use ``httpx.MockTransport``); omitted, it
    wraps a standard ``httpx.HTTPTransport``.

    ``proxy`` is the dev forward proxy's URL (``http://egress-proxy:3128``).
    Passing it changes exactly one thing: the request keeps its hostname
    instead of being rewritten to a pinned address, because the CONNECT line
    is what the proxy matches on and files/10 §4 gives the proxy the
    resolve-and-pin job. The allow-list, purpose and data-class checks run in
    process either way. Without this parameter the two enforcement points do
    not compose — the proxy would see an IP literal and refuse it — which is a
    trap worth removing rather than documenting.

    Note that the guard cannot be routed around by ``HTTP_PROXY`` in the
    environment: ``httpx`` ignores proxy environment variables when an
    explicit transport is supplied, so the proxy is only ever the one named
    here.

    **A personal-data transport may not take this path** (INT-203). ADR-025
    named four ways round this control and INT-160/INT-161 each found another;
    delegating the pin is the shape the next one would take, because it looks
    like configuration rather than like a change to a security boundary. The
    vendor allow-list the proxy enforces has no connector rows and its
    ``phi_path`` tier is empty, so a PHI or pseudonymous call routed through it
    would lose the in-process resolve-and-pin and gain no network-tier check in
    exchange — the two enforcement points would each assume the other had done
    it. Refused at construction rather than at the first send, so the mistake
    surfaces where it is made instead of in a receipt.
    """
    if context.data_class.is_personal and proxy is not None:
        raise ValueError(
            f"a {context.data_class} transport cannot delegate its pin to the forward "
            "proxy: the vendor allow-list the proxy enforces has no connector rows and "
            "its phi_path tier is empty, so this call would lose the in-process "
            "resolve-and-pin and gain nothing (files/10 §4; ADR-025)"
        )
    if inner is None:
        inner = httpx.HTTPTransport(proxy=proxy) if proxy else httpx.HTTPTransport()
    return _GuardedTransport(
        policy,
        context,
        inner,
        transfer_log if transfer_log is not None else LoggingTransferLog(),
        pin_here=proxy is None,
    )


def guarded_client(
    policy: EgressPolicy,
    context: EgressContext,
    inner: httpx.BaseTransport | None = None,
    transfer_log: TransferLog | None = None,
    proxy: str | None = None,
    *,
    follow_redirects: bool = False,
    timeout: httpx.Timeout | float | None = None,
) -> httpx.Client:
    """An ``httpx.Client`` over :func:`guarded_transport`, redirects off.

    files/10 §4 says the proxy "disables redirects". A caller that genuinely
    needs to follow one can pass ``follow_redirects=True`` and still not leave
    the allow-list — every hop is re-authorised — but the default is the
    boring one, because a redirect is a destination the caller never named.

    The keyword surface is deliberately narrow rather than ``**kwargs``: a
    passthrough would let a caller hand ``httpx.Client`` a ``proxy``, a
    ``base_url`` or its own ``transport`` and quietly route around the guard.
    """
    return httpx.Client(
        transport=guarded_transport(policy, context, inner, transfer_log, proxy),
        follow_redirects=follow_redirects,
        timeout=timeout if timeout is not None else httpx.Timeout(10.0),
    )
