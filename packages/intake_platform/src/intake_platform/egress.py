"""Egress policy: the vendor allow-list as data + default-deny enforcement (INT-018).

files/10 §4 and CLAUDE.md invariants 14/19: only contracted vendors are
reachable from any INTAKE process, the PHI path reaches **no** external model
or speech vendor at all (self-hosting, 00_STATE D11), and every egress
decision is logged as KVKK transfer evidence — hosts and purposes only, never
payloads, paths or query strings (invariant 6).

Three layers, so a config mistake cannot silently widen the boundary:

1. **Validation** — the allow-list is pydantic-checked at load: IP-literal
   hosts are refused (files/10 §4 denies literal IPs and private/link-local/
   metadata ranges), a ``*`` in a host is refused unless the entry declares
   ``glob: true`` (and then only the leading ``*.suffix`` form), and
   ``phi_allowed: true`` is refused without a ``phi_exception_approval``
   naming a recorded human decision.
2. **Runtime double-gate** — even a validated ``phi_allowed`` entry denies
   unless ``INTAKE_ALLOW_PHI_EGRESS=explicit-yes`` is set. Default deny twice:
   config alone is not enough, an operator must also say so at runtime.
3. **Vendor-LLM pin** — :func:`assert_dev_only_vendors` refuses any list where
   an anthropic/openai/google API host is PHI-enabled or appears on the PHI
   path at all: those adapters are the mock/dev path only (invariant 19).

:func:`guarded_transport` wraps ``httpx`` so services adopt enforcement by
construction. Redirects are safe by composition: httpx follows a redirect by
issuing a new request through the same transport, so every hop is re-checked
(and ``follow_redirects`` defaults to off in httpx anyway — files/10 §4 wants
redirects disabled at the proxy tier too). The deployed forward proxy that
makes this network-mandatory (Envoy/squid in compose) is INT-203 infra; this
module is the policy and the in-process enforcement it will share.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "VENDOR_LLM_DOMAINS",
    "AllowlistEntry",
    "Decision",
    "EgressAllowlist",
    "EgressConfigError",
    "EgressDenied",
    "EgressPolicy",
    "Tier",
    "assert_dev_only_vendors",
    "guarded_transport",
    "load_allowlist",
]

_LOGGER = logging.getLogger("intake_platform.egress")

_PHI_EGRESS_ENV = "INTAKE_ALLOW_PHI_EGRESS"
_PHI_EGRESS_VALUE = "explicit-yes"
_DEFAULT_SCHEME_PORTS = {"https": 443, "http": 80}

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

Tier = Literal["dev", "phi_path"]


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


class AllowlistEntry(BaseModel):
    """One vendor row: who is reachable, on which port, and on what legal basis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    protocol: Literal["https"]
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
    purpose: str | None = None


class EgressPolicy:
    """Default-deny host/port policy over one tier of the allow-list."""

    def __init__(self, entries: list[AllowlistEntry], tier: str) -> None:
        self._entries = tuple(entries)
        self._tier = tier

    @classmethod
    def for_tier(cls, allowlist: EgressAllowlist, tier: Tier) -> EgressPolicy:
        entries = allowlist.tiers.dev if tier == "dev" else allowlist.tiers.phi_path
        return cls(entries, tier)

    def check(self, host: str, port: int) -> Decision:
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
            if entry.phi_allowed and os.environ.get(_PHI_EGRESS_ENV) != _PHI_EGRESS_VALUE:
                return Decision(
                    False,
                    f"phi_allowed entry '{entry.name}' additionally requires "
                    f"{_PHI_EGRESS_ENV}={_PHI_EGRESS_VALUE} at runtime (default deny)",
                    normalized,
                    port,
                    entry.purpose,
                )
            return Decision(
                True,
                f"allow-listed: {entry.name} (tier {self._tier})",
                normalized,
                port,
                entry.purpose,
            )
        return Decision(
            False,
            f"host is not on the '{self._tier}' egress allow-list (default deny)",
            normalized,
            port,
        )


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


def _log_decision(decision: Decision, bytes_out: int) -> None:
    """One structured record per decision: {host, port, decision, purpose,
    bytes_out, reason} — the in-process feed for the vendor-transfer register.
    Never the URL path, query or payload (invariant 6): a query string is
    exactly where an identifier would leak."""
    fields = {
        "host": decision.host,
        "port": decision.port,
        "decision": "allow" if decision.allowed else "deny",
        "purpose": decision.purpose or "-",
        "bytes_out": bytes_out,
        "reason": decision.reason,
    }
    if decision.allowed:
        _LOGGER.info("sec.egress_allowed", extra=fields)
    else:
        _LOGGER.warning("sec.egress_denied", extra=fields)


class _GuardedTransport(httpx.BaseTransport):
    """httpx transport that consults the policy before any bytes leave.

    Composition keeps CI vendor-free: tests wrap ``httpx.MockTransport``; the
    default wraps a real ``httpx.HTTPTransport``. Redirect hops re-enter
    ``handle_request``, so every hop is checked independently.
    """

    def __init__(self, policy: EgressPolicy, inner: httpx.BaseTransport) -> None:
        self._policy = policy
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        port = request.url.port or _DEFAULT_SCHEME_PORTS.get(request.url.scheme, 0)
        decision = self._policy.check(host, port)
        # bytes_out only for requests that actually leave; a denied request
        # transferred nothing. Header-declared size — never the body itself.
        bytes_out = int(request.headers.get("content-length", 0)) if decision.allowed else 0
        _log_decision(decision, bytes_out)
        if not decision.allowed:
            raise EgressDenied(
                f"egress denied for {decision.host}:{decision.port} — {decision.reason}"
            )
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def guarded_transport(
    policy: EgressPolicy, inner: httpx.BaseTransport | None = None
) -> httpx.BaseTransport:
    """Build the enforcing transport: ``httpx.Client(transport=guarded_transport(p))``.

    Pass ``inner`` to compose (tests use ``httpx.MockTransport``); omitted, it
    wraps a standard ``httpx.HTTPTransport``.
    """
    return _GuardedTransport(policy, inner if inner is not None else httpx.HTTPTransport())
