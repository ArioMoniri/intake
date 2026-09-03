"""The console IP allow-list (INT-180; files/08 §2.3).

Two decisions, both in the fail-closed direction.

**An empty list admits nobody.** §2.3 says "IP allow-list for the console" and
names no addresses; no file in this repository names an office range, a VPN
egress or a bastion. Shipping empty is therefore the correct state, and it
means the console is unreachable until a deployment supplies one — an
allow-list with a plausible address in it would be worse than none, because it
would look configured (CLAUDE.md invariant 17, HUMAN_BLOCKERS rule 1).

**Only the transport peer counts.** :meth:`permits` is given the address the
socket actually came from. ``X-Forwarded-For`` is attacker-controlled unless a
trusted-proxy hop count is configured, no such configuration exists here, and
an allow-list that reads a spoofable header is not an allow-list. A client
address that is not an IP address at all — a unix socket peer, a test
transport — is refused rather than coerced.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

__all__ = ["IpAllowList"]

_Network = IPv4Network | IPv6Network


@dataclass(frozen=True)
class IpAllowList:
    networks: tuple[_Network, ...]

    @classmethod
    def from_spec(cls, spec: str) -> IpAllowList:
        """Parse a comma-separated CIDR list. A malformed entry raises rather
        than being skipped: silently dropping one entry of an allow-list
        widens or narrows it in a way nobody sees."""
        entries = [chunk.strip() for chunk in spec.split(",") if chunk.strip()]
        return cls(networks=tuple(ip_network(entry, strict=False) for entry in entries))

    def permits(self, client_host: str) -> bool:
        if not self.networks:
            return False
        try:
            address = ip_address(client_host)
        except ValueError:
            return False
        return any(address in network for network in self.networks)
