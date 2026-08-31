"""Render the dev forward proxy's squid.conf from the vendor allow-list (INT-018).

The allow-list header already says it: the file "is DATA, not code:
``intake_platform.egress`` loads and validates it, and the deployed proxy tier
will consume the same file". This module is that consumption. The proxy and
the in-process policy are one source of truth rendered twice, and
``tests/security/test_egress_proxy_compose.py`` asserts byte-identity between
this render and the committed ``infra/security/squid/squid.conf``, so the two
cannot drift.

Three properties the render keeps, because a proxy that does not keep them is
worse than no proxy:

1. **Default deny.** ``http_access deny all`` is the last rule. Nothing is
   reachable that the allow-list does not name, and the per-entry allow lines
   bind host *and* port exactly as ``AllowlistEntry.matches`` does — including
   the glob semantics, where ``*.hf.co`` covers a subdomain and never the
   apex. A ``dstdomain .hf.co`` would have covered the apex too; the render
   emits an anchored ``dstdom_regex`` instead so the two tiers agree.
2. **CONNECT to the entry's port only.** Every allow-list row is ``https``, so
   the proxy tunnels and never sees a request line — which is also why the
   access log *cannot* contain a path or query even by accident.
3. **The access log is the vendor-transfer register's feed** (files/10 §5,
   legal code TRANSFER-2024): ``{ts, host, port, decision, bytes_out}`` and
   nothing else. ``%>rd`` and ``%>rP`` are the destination host and port;
   ``%ru``/``%rp`` — the codes that carry a path or query — never appear
   (invariant 6). Purpose and legal basis are not repeated per line; they are
   joined from the allow-list row for that host, which is where a human
   already reviews them.

Regenerate with ``python -m intake_platform.egress_proxy``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from intake_platform.egress import (
    AllowlistEntry,
    EgressAllowlist,
    Tier,
    assert_dev_only_vendors,
    load_allowlist,
)

__all__ = [
    "ALLOWLIST_PATH",
    "PROXY_PORT",
    "SQUID_CONF_PATH",
    "acl_name",
    "main",
    "render_squid_conf",
]

_REPO = Path(__file__).resolve().parents[4]
ALLOWLIST_PATH = _REPO / "infra" / "security" / "egress-allowlist.yaml"
SQUID_CONF_PATH = _REPO / "infra" / "security" / "squid" / "squid.conf"

#: The proxy's listener. 3128 is squid's own default; keeping it means the
#: compose service needs no port remapping and no surprise for a reader.
PROXY_PORT = 3128

#: Where the proxy's clients live. In compose these are the other services on
#: the project network; the rule denies anything else outright so the proxy is
#: never an open relay if its port is ever exposed by accident.
_CLIENT_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")

_HEADER = """\
# GENERATED — do not edit by hand.
#
# Rendered from infra/security/egress-allowlist.yaml (tier: {tier}) by
# intake_platform.egress_proxy.render_squid_conf. The allow-list is the single
# source of truth for both this proxy and the in-process policy in
# intake_platform.egress; tests/security/test_egress_proxy_compose.py asserts
# this file is byte-identical to the render, so an edit here fails the build.
# Regenerate with: python -m intake_platform.egress_proxy
#
# INT-018 — "forward proxy in dev compose; only allow-listed vendor hosts
# reachable from PHI-path services; every egress logged {{host,purpose,bytes,ts}}
# feeding the vendor-transfer register; denial emits sec.egress_denied".
# files/10 §4 (egress proxy with an allow-list), §5 (egress denials page),
# CLAUDE.md invariants 6, 14 and 19. Legal: KVKK-9, TRANSFER-2024.
#
# NOTE: this configuration has never been started. There is no Docker daemon
# in the session that wrote it; it is validated statically, the way INT-202
# landed the backup tier. See docs/evidence/INT-018.md."""


def acl_name(entry_name: str) -> str:
    """Squid ACL identifier for an allow-list row. Deterministic and
    collision-visible: two rows that slugify the same would emit the same ACL
    name, which the renderer refuses rather than silently merging."""
    return "vendor_" + re.sub(r"[^a-z0-9]+", "_", entry_name.strip().lower()).strip("_")


def _match_directive(entry: AllowlistEntry) -> str:
    """The squid ACL body that matches exactly what ``entry.matches`` matches."""
    if entry.glob:
        suffix = entry.host[1:]  # "*.hf.co" -> ".hf.co"
        return "dstdom_regex -i ^.+" + re.escape(suffix).replace("/", r"\/") + "$"
    return f"dstdomain {entry.host}"


def render_squid_conf(allowlist: EgressAllowlist, *, tier: Tier) -> str:
    """Render the whole squid.conf for one tier of the allow-list.

    Raises :class:`intake_platform.egress.EgressConfigError` when the
    allow-list itself is one the library refuses (a vendor LLM family on the
    PHI path, or PHI-enabled at all — invariant 19), so a proxy config can
    never be generated for a list the policy would reject.
    """
    if tier == "dev":
        entries = list(allowlist.tiers.dev)
    elif tier == "phi_path":
        entries = list(allowlist.tiers.phi_path)
    else:
        raise ValueError(f"unknown allow-list tier {tier!r} — expected 'dev' or 'phi_path'")
    assert_dev_only_vendors(allowlist)

    names = [acl_name(entry.name) for entry in entries]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(
            f"allow-list rows collapse to the same squid ACL name {duplicates} — "
            "rename a row rather than letting two vendors share one rule"
        )

    lines: list[str] = [_HEADER.format(tier=tier), ""]

    lines += [
        "# --- listener ----------------------------------------------------------------",
        f"http_port {PROXY_PORT}",
        "visible_hostname intake-forward-proxy",
        "",
        "# --- who may ask -------------------------------------------------------------",
    ]
    lines += [f"acl intake_clients src {network}" for network in _CLIENT_NETWORKS]
    lines += [
        "acl CONNECT method CONNECT",
        "",
        "# --- ports the allow-list names ----------------------------------------------",
    ]
    for port in sorted({entry.port for entry in entries}):
        lines.append(f"acl port_{port} port {port}")
    if not entries:
        lines.append("# (no row in this tier: nothing is reachable)")
    lines += [
        "",
        "# --- denied before anything else ----------------------------------------------",
        "# An open relay, the proxy's own manager interface, and the two destination",
        "# classes files/10 §4 names outright: loopback and link-local (which is where",
        "# 169.254.169.254 lives). A bare IP destination matches no dstdomain rule and",
        "# falls through to `deny all` regardless.",
        "http_access deny !intake_clients",
        "http_access deny manager",
        "http_access deny to_localhost",
        "http_access deny to_linklocal",
        "http_access deny !CONNECT",
        "",
        f"# --- the allow-list, tier `{tier}` ---",
    ]
    if entries:
        for entry in entries:
            name = acl_name(entry.name)
            lines += [
                f"# {entry.name} — {entry.purpose}",
                f"#   basis: {entry.basis}",
                f"acl {name} {_match_directive(entry)}",
                f"http_access allow CONNECT intake_clients {name} port_{entry.port}",
            ]
    else:
        lines.append(
            "# Empty on purpose: the PHI path is self-hosted end to end "
            "(invariant 19 / 00_STATE D11)."
        )
    lines += [
        "",
        "# --- the vendor-transfer register feed (files/10 §5; TRANSFER-2024) -----------",
        "# {ts, host, port, decision, bytes_out} and nothing else. %>rd and %>rP are the",
        "# destination host and port; the path-bearing codes (%ru, %rp and their",
        "# variants) and every client-identity code are absent by construction —",
        "# invariant 6, and a query string is exactly where an identifier would leak.",
        "# Purpose and legal basis are joined per host from the allow-list row.",
        "logformat intake_transfer ts=%ts.%03tu host=%>rd port=%>rP decision=%Ss "
        "bytes_out=%>st reason=%err_code",
        "access_log stdio:/dev/stdout intake_transfer",
        "cache_log stdio:/dev/stderr",
        "",
        "# --- the proxy stores nothing and identifies nobody ---------------------------",
        "# A caching egress proxy is a store of response bodies, and a forwarded client",
        "# identity is a record of who inside asked. Neither belongs on the PHI path.",
        "cache deny all",
        "forwarded_for delete",
        "via off",
        "httpd_suppress_version_string on",
        "",
        "# --- default deny --------------------------------------------------------------",
        "http_access deny all",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    """Regenerate ``infra/security/squid/squid.conf`` in place."""
    allowlist = load_allowlist(ALLOWLIST_PATH)
    SQUID_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQUID_CONF_PATH.write_text(render_squid_conf(allowlist, tier="dev"), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())
