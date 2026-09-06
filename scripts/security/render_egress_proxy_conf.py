"""Render infra/security/egress-allowlist.yaml into the forward proxy's config.

INT-018. The allow-list has two enforcement points — `intake_platform.egress`
in process and the squid forward proxy at the network tier — and two
hand-maintained copies of a security list is the defect this script exists to
remove. The proxy config is GENERATED; `--check` fails when the committed file
is stale, and tests/infra/test_egress_proxy.py decides a table of hosts through
both the library and the rendered ACLs so their semantics cannot diverge.

Two squid details the rendering is deliberate about:

- **Globs are regexes, not `dstdomain .suffix`.** Squid's leading-dot form
  matches the bare apex as well as subdomains; `AllowlistEntry.matches` does
  not (`*.hf.co` covers `cdn-lfs-us-1.hf.co`, never `hf.co`). An anchored
  `dstdom_regex` is the form that agrees.
- **`%ru` is CONNECT-only.** For a CONNECT request squid's `%ru` is exactly
  `host:port` — no path, no query — which is what the transfer register needs.
  For any other method it is the full URL, which is where a token or an
  identifier would leak (invariant 6). So the format carrying `%ru` is
  attached to a CONNECT-scoped `access_log` line and the other format does not
  carry it at all.

Usage:
    uv run python scripts/security/render_egress_proxy_conf.py [--check]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "intake_platform" / "src"))

from intake_platform.egress import (  # noqa: E402
    DENIED_RANGES,
    AllowlistEntry,
    load_allowlist,
)

ALLOWLIST = REPO / "infra" / "security" / "egress-allowlist.yaml"
TARGET = REPO / "infra" / "security" / "squid" / "squid.conf"

#: The proxy listens here inside the container; the compose file binds it to
#: loopback on the host. 3128 is squid's own default — not a value anyone had
#: to supply.
PROXY_PORT = 3128

_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"


def _glob_regex(entry: AllowlistEntry) -> str:
    """`*.hf.co` -> `^([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\\.)+hf\\.co$`.

    One or more labels, then the literal suffix, anchored at both ends: the
    apex fails the `+`, and a lookalike like `evilhf.co` fails the escaped dot
    that has to precede the suffix.
    """
    suffix = re.escape(entry.host[2:])
    return rf"^({_LABEL}\.)+{suffix}$"


def render() -> str:
    allowlist = load_allowlist(ALLOWLIST)
    dev = allowlist.tiers.dev
    exact = sorted(entry.host for entry in dev if not entry.glob)
    globs = [entry for entry in dev if entry.glob]
    ports = sorted({entry.port for entry in dev})

    denied = " ".join(cidr for cidr, _ in DENIED_RANGES)

    lines: list[str] = [
        "# GENERATED — do not edit by hand.",
        "#",
        "# Source:      infra/security/egress-allowlist.yaml",
        "# Generator:   scripts/security/render_egress_proxy_conf.py (`make egress-conf`)",
        "# Consumed by: infra/docker-compose.egress.yml, service `egress-proxy`",
        "#",
        "# INT-018 / ADR-025: one allow-list, two enforcers. Editing this file",
        "# instead of the allow-list makes the proxy disagree with",
        "# intake_platform.egress, and tests/infra/test_egress_proxy.py fails.",
        "",
        f"http_port {PROXY_PORT}",
        "pid_filename none",
        "",
        "# --- what the proxy itself discloses ------------------------------------",
        "# `via off` and `forwarded_for delete` keep our internal topology out of",
        "# the request; `strip_query_terms on` keeps query strings out of the log,",
        "# where an identifier is exactly what would land (invariant 6).",
        "via off",
        "forwarded_for delete",
        "strip_query_terms on",
        "httpd_suppress_version_string on",
        "",
        "# A cache is a copy, and nothing that passes here is worth keeping a",
        "# copy of.",
        "cache deny all",
        "",
        "# --- re-validating on connect (INT-203) -----------------------------------",
        "# files/10 §4 asks this tier to 'resolve once and pin, re-validating on",
        "# connect'. squid evaluates `dst` ACLs against its IP cache, whose default",
        "# positive TTL is SIX HOURS: a name authorised against one answer can be",
        "# connected to against another, which is the DNS-rebinding attack the",
        "# clause is about — and the in-process guard cannot catch it, because",
        "# behind a proxy the process never resolves at all (that is the whole",
        "# point of passing the hostname through to the CONNECT line).",
        "#",
        "# `ipcache_size 0` disables the cache, so the ACL check and the connect",
        "# share one lookup per request; the TTLs are floored as well, because a",
        "# squid that treats a zero cache size as advisory would otherwise still",
        "# hold an answer for six hours. `dns_defnames off` stops a bare label",
        "# acquiring the container search domain and resolving to something",
        "# internal.",
        "ipcache_size 0",
        "fqdncache_size 0",
        "positive_dns_ttl 1 second",
        "negative_dns_ttl 1 second",
        "dns_defnames off",
        "",
        "# --- the transfer register feed ------------------------------------------",
        "# %ru on a CONNECT is `host:port` and nothing else; on any other method it",
        "# is the full URL. So it appears in one format only, and that format's",
        "# access_log line is CONNECT-scoped.",
        "logformat intake_connect %ts.%03tu %rm %ru %>st %<st %Ss/%03>Hs",
        "logformat intake_other %ts.%03tu %rm %>st %<st %Ss/%03>Hs",
        "access_log stdio:/dev/stdout intake_connect CONNECT",
        "access_log stdio:/dev/stdout intake_other !CONNECT",
        "cache_log stdio:/dev/stderr",
        "",
        "# --- destinations that are never reachable, whatever the hostname said ----",
        "# files/10 §4: literal IPs and private / link-local / metadata ranges. The",
        "# same list is intake_platform.egress.DENIED_RANGES; both are rendered",
        "# from it. 169.254.0.0/16 is what makes the cloud metadata endpoint",
        "# unreachable even when a hostname on the list resolves to it.",
        f"acl denied_nets dst {denied}",
        "",
        "# --- the allow-list ------------------------------------------------------",
        f"acl vendor_ports port {' '.join(str(port) for port in ports)}",
        "acl SSL_ports port 443",
        "acl CONNECT method CONNECT",
        f"acl vendor_exact dstdomain {' '.join(exact)}",
    ]
    for entry in globs:
        lines.append(f"# {entry.name}: {entry.host}")
        lines.append(f"acl vendor_glob dstdom_regex -i {_glob_regex(entry)}")
    if not globs:
        # An ACL squid can parse and nothing can match, so `any-of` below stays
        # valid without a glob row existing.
        lines.append(r"acl vendor_glob dstdom_regex -i ^\0$")
    lines += [
        "acl vendor_allowed any-of vendor_exact vendor_glob",
        "",
        "# --- order is the control -------------------------------------------------",
        "# Deny before allow, and `deny all` last: a rule added below the final",
        "# deny is dead, which is the failure mode a reviewer should be able to see.",
        "http_access deny denied_nets",
        "http_access deny !CONNECT",
        "http_access deny CONNECT !SSL_ports",
        "http_access deny !vendor_ports",
        "http_access allow vendor_allowed",
        "http_access deny all",
        "",
        "# Redirects are the proxy's business only insofar as it never issues one",
        "# (files/10 §4 'disables redirects'); a 3xx from an allow-listed host is",
        "# followed, if at all, by the client — where every hop re-enters",
        "# intake_platform.egress and is checked, resolved and pinned again.",
        "",
    ]
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
        print(f"{TARGET.relative_to(REPO)} is stale — run `make egress-conf`", file=sys.stderr)
        return 1
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8")
    print(f"wrote {TARGET} ({len(rendered.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
