"""The in-boundary form of the egress guard, for PHI-path clients (INT-018).

``intake_platform.egress`` answers "may this process reach this *vendor*?".
This module answers the narrower question a PHI-path client asks: "may this
client reach anything at all outside the deployment boundary?" — and the
answer, per invariant 19 and 00_STATE D11, is no. ``phi_path: []`` in
``infra/security/egress-allowlist.yaml`` is not an empty list waiting to be
filled; it is the design. EHRbase, OpenBao and Unleash all run inside the
boundary (files/10 §2 "Services"), so a client that finds itself dialling a
routable host has been mis-configured or re-pointed, and that is precisely
the server-side-fetch attack files/10 §4 describes: a destination typed by
someone else, fetched *from inside the PHI network*, where even the failure
discloses.

**The rule.** A destination is in-boundary when it cannot exist in the public
DNS, or is the machine itself:

* a bare service label with no dot — ``ehrbase``, ``openbao`` — which has no
  public TLD to resolve against, so it can only mean a compose or Kubernetes
  service name;
* a name under a suffix reserved by a standard so that it is never delegated:
  ``.test`` and ``.invalid`` and ``.localhost`` (RFC 6761), ``.local``
  (RFC 6762 mDNS, which also covers ``.svc.cluster.local``), and ``.internal``
  (ICANN-reserved for private use, 2024);
* a loopback literal — ``127.0.0.0/8`` or ``::1``, the dev tier's form.

Everything else is refused: every public FQDN, and **every routable IP
literal** including RFC 1918 space, link-local and the cloud metadata address
``169.254.169.254``. Refusing private ranges as well as public ones is
deliberate — "inside a private network" is not "inside our boundary", and an
attacker who can set a base URL to a neighbouring subnet has the same payoff.

**How it fails.** Never at construction. A client with an out-of-boundary base
URL builds fine and then refuses every request, emitting the same
``sec.egress_denied`` record the vendor guard emits — because the acceptance
is "a call to an unlisted host is refused *and logged*", and a client that
raised at import time would produce no transfer record at all.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address

import httpx

from intake_platform.egress import (
    DEFAULT_SCHEME_PORTS,
    Decision,
    guarded_transport,
    normalize_host,
)

__all__ = [
    "BOUNDARY_SUFFIXES",
    "BoundaryDestination",
    "BoundaryPolicy",
    "boundary_transport",
    "is_boundary_host",
]

#: Suffixes reserved by a standard so that they are never delegated in the
#: public DNS. Membership here is a property of the name, not a convenience:
#: a suffix that resolved globally would be an exfiltration destination.
BOUNDARY_SUFFIXES: frozenset[str] = frozenset(
    {
        ".internal",  # ICANN-reserved private-use TLD (2024)
        ".invalid",  # RFC 6761 §6.4
        ".local",  # RFC 6762 mDNS — covers .svc.cluster.local
        ".localhost",  # RFC 6761 §6.3
        ".test",  # RFC 6761 §6.2
    }
)


def _ip_literal(host: str) -> IPv4Address | IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def is_boundary_host(host: str) -> bool:
    """Is ``host`` a destination inside the deployment boundary? See the
    module docstring for the rule; default is False for anything unrecognised."""
    normalized = normalize_host(host)
    if not normalized:
        return False
    address = _ip_literal(normalized)
    if address is not None:
        # loopback is the machine itself; every other literal — public,
        # RFC 1918, link-local, the metadata address — is routable and refused.
        return address.is_loopback
    if "." not in normalized:
        return True
    return any(normalized.endswith(suffix) for suffix in BOUNDARY_SUFFIXES)


@dataclass(frozen=True)
class BoundaryDestination:
    """The one host and port a boundary-guarded client may reach."""

    host: str
    port: int


class BoundaryPolicy:
    """Default-deny policy over a single in-boundary destination.

    Satisfies ``intake_platform.egress.EgressCheck``, so it composes with
    :func:`intake_platform.egress.guarded_transport` — the same enforcement
    point, the same structured transfer record, a narrower allow set.
    """

    def __init__(self, service: str, purpose: str, destination: BoundaryDestination | None) -> None:
        self._service = service
        self._purpose = purpose
        self._destination = destination

    @classmethod
    def for_base_url(cls, *, service: str, purpose: str, base_url: str) -> BoundaryPolicy:
        """Build the policy from a client's configured base URL.

        An out-of-boundary base URL yields a policy that permits **nothing**:
        the client is built, and every request it makes is refused and logged.
        """
        url = httpx.URL(base_url)
        host = normalize_host(url.host)
        if not is_boundary_host(host):
            return cls(service, purpose, None)
        port = url.port or DEFAULT_SCHEME_PORTS.get(url.scheme, 0)
        return cls(service, purpose, BoundaryDestination(host, port))

    def check(self, host: str, port: int) -> Decision:
        normalized = normalize_host(host)
        destination = self._destination
        if destination is None:
            return Decision(
                False,
                f"'{self._service}' is configured outside the deployment boundary — a "
                "PHI-path client reaches no vendor and no routable host (invariant 19)",
                normalized,
                port,
                self._purpose,
            )
        if normalized == destination.host and port == destination.port:
            return Decision(
                True,
                f"in-boundary destination for '{self._service}'",
                normalized,
                port,
                self._purpose,
            )
        return Decision(
            False,
            f"not the in-boundary destination for '{self._service}' "
            f"({destination.host}:{destination.port}) — default deny",
            normalized,
            port,
            self._purpose,
        )


def boundary_transport(
    *,
    service: str,
    purpose: str,
    base_url: str,
    inner: httpx.BaseTransport | None = None,
) -> httpx.BaseTransport:
    """The transport a PHI-path client hands to ``httpx.Client``.

    ``inner`` is the transport underneath the guard, never a way around it:
    a test that injects ``httpx.MockTransport`` is still policed, because a
    guard that every exercised path bypasses is a guard nobody exercises.
    """
    policy = BoundaryPolicy.for_base_url(service=service, purpose=purpose, base_url=base_url)
    return guarded_transport(policy, inner)
