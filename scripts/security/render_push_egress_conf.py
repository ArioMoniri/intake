"""INT-583 — render the synthetic host's push-only forward proxy from the egress allow-list.

The new-device sign-in notice (D35) is the second personal-data call that rides
a forward proxy (``intake_platform.egress.DEDICATED_PERSONAL_PROXIES``), on
ADR-042's pattern, and this is that proxy's whole configuration. It is rendered
from the same file the in-process guard loads,
``infra/security/egress-allowlist.yaml`` (ADR-025, one list, two enforcers),
and admits the ``phi_path`` tier's ``push_security_notice`` rows and nothing
else: exact hosts, port 443, CONNECT only. With no such row it admits nothing
at all, and says so. That is the shipped state until the owner applies the
APNs rows (owner-583-apns-egress.patch), which re-renders this file.

What INT-203 (ADR-032) asks of a proxy that carries personal data, it does, as
``render_sms_egress_conf.py`` does for the SMS proxy:

- the rebinding window is closed here, where it exists: no IP or FQDN cache,
  one-second DNS TTLs, no search-domain expansion, so the ACL check and the
  connect share one lookup;
- the denied ranges (``intake_platform.egress.DENIED_RANGES``) are refused at
  connect, whatever the hostname resolved to;
- TLS (and HTTP/2 inside it) runs end to end through CONNECT, so the proxy
  sees no request content: not the device token in the path, not the provider
  token, not the notice. Its log line is ``host:port``, a status and byte
  counts, never a path, a query or a header.

Usage:
    uv run python scripts/security/render_push_egress_conf.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "intake_platform" / "src"))

from intake_platform.egress import (  # noqa: E402
    DENIED_RANGES,
    AllowlistEntry,
    EgressPurpose,
    load_allowlist,
)

ALLOWLIST = REPO / "infra" / "security" / "egress-allowlist.yaml"
TARGET = REPO / "infra" / "staging" / "push-egress" / "squid.conf"
PROXY_PORT = 3128


def push_rows(allowlist_path: Path = ALLOWLIST) -> list[AllowlistEntry]:
    """The PHI tier's push rows: exact hosts on 443, approved for personal data."""
    rows = [
        entry
        for entry in load_allowlist(allowlist_path).tiers.phi_path
        if entry.purpose_id is EgressPurpose.PUSH_SECURITY_NOTICE
    ]
    for entry in rows:
        if entry.glob or entry.port != 443 or not entry.phi_allowed:
            raise SystemExit(
                f"allow-list row {entry.name}: a push row is an exact host on 443 with "
                "phi_allowed: true (INT-583, ADR-042's pattern)"
            )
    return rows


def render(allowlist_path: Path = ALLOWLIST) -> str:
    hosts = sorted(entry.host for entry in push_rows(allowlist_path))
    denied = " ".join(cidr for cidr, _ in DENIED_RANGES)
    lines = [
        "# GENERATED — do not edit by hand.",
        "#",
        "# Source:      infra/security/egress-allowlist.yaml (phi_path, push_security_notice rows)",
        "# Generator:   scripts/security/render_push_egress_conf.py",
        "# Consumed by: infra/staging/compose.yaml, service `push-egress`",
        "#",
        "# INT-583 (D35), on ADR-042's pattern: the synthetic host's push-only",
        "# forward proxy. It sits on a network shared with the API alone, admits",
        "# CONNECT to the allow-list's APNs hosts on 443 and nothing else, and is",
        "# the only proxy intake_platform.egress lets the push notice ride.",
        "",
        f"http_port {PROXY_PORT}",
        "pid_filename none",
        "# The ICMP pinger needs CAP_NET_RAW, which this container does not hold.",
        "pinger_enable off",
        "",
        "# --- what the proxy itself discloses ------------------------------------",
        "via off",
        "forwarded_for delete",
        "strip_query_terms on",
        "httpd_suppress_version_string on",
        "cache deny all",
        "",
        "# --- re-validating on connect (INT-203 / ADR-032) -------------------------",
        "# No cache and one-second TTLs: the dst ACL below and the connect share",
        "# one lookup, so a name cannot be authorised against one answer and",
        "# connected to against another.",
        "ipcache_size 0",
        "fqdncache_size 0",
        "positive_dns_ttl 1 second",
        "negative_dns_ttl 1 second",
        "dns_defnames off",
        "",
        "# --- the log: host:port, status and bytes; never a path, query or header --",
        "logformat push_connect %ts.%03tu %rm %ru %>st %<st %Ss/%03>Hs",
        "logformat push_other %ts.%03tu %rm %>st %<st %Ss/%03>Hs",
        "access_log stdio:/dev/stdout push_connect CONNECT",
        "access_log stdio:/dev/stdout push_other !CONNECT",
        "cache_log stdio:/dev/stderr",
        "",
        "# --- destinations that are never reachable, whatever the hostname said ----",
        f"acl denied_nets dst {denied}",
        "",
        "# --- the allow-list (phi_path push_security_notice rows only) -------------",
        "acl SSL_ports port 443",
        "acl CONNECT method CONNECT",
    ]
    if hosts:
        lines.append(f"acl push_vendor dstdomain {' '.join(hosts)}")
    lines += [
        "",
        "# --- order is the control: deny before allow, `deny all` last -------------",
        "http_access deny denied_nets",
        "http_access deny !CONNECT",
        "http_access deny CONNECT !SSL_ports",
    ]
    if hosts:
        lines.append("http_access allow push_vendor")
    else:
        lines.append("# no push_security_notice row on the allow-list: nothing is admitted")
    lines += ["http_access deny all", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when the committed config is stale instead of rewriting it",
    )
    args = parser.parse_args()
    rendered = render()
    current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else None
    if args.check:
        if current == rendered:
            return 0
        print(f"{TARGET.relative_to(REPO)} is stale — re-run the renderer", file=sys.stderr)
        return 1
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(REPO)} ({len(rendered.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
