"""INT-442 egress probe. smoke.sh runs it inside the api container.

Subcommand ``proxy`` proves, from the API's own network position, the three
facts the synthetic host's egress rests on:

1. **No direct route.** A plain connection to a public host fails: every
   network the API sits on is internal.
2. **Unlisted is refused.** The forward proxy named by
   ``INTAKE_EGRESS_PROXY_URL`` answers 403 to a CONNECT for a host that is not
   a hosted-model row of the allow-list, and to the cloud metadata address.
3. **Listed is admitted.** Every ``hosted_model_inference`` row of the
   allow-list is tunnelled: any HTTP answer from the vendor proves the CONNECT
   opened. With no such row the probe says so; nothing is admitted then.

The probe speaks raw ``httpx`` on purpose: it tests the network enforcer, not
the in-process guard (``intake_platform.egress``), which decides the same rows
a second time on every real call. No credential is sent and no response body
is read or printed (invariant 6): a line names a host, a status code or an
exception class.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final, TextIO

import httpx
from intake_platform.egress import EgressPurpose, load_allowlist
from intake_platform.model_lanes.guard import EgressProxyRefused, egress_proxy_url

__all__ = ["UNLISTED_TARGETS", "Fetch", "hosted_hosts", "main", "probe_proxy"]

#: Never on the allow-list: a public host, and the cloud metadata address (a
#: literal IP inside the proxy's denied ranges).
UNLISTED_TARGETS: Final = ("example.com", "169.254.169.254")
ALLOWLIST: Final = Path("infra/security/egress-allowlist.yaml")
TIMEOUT_S: Final = 8.0

#: ``fetch(url, proxy)`` -> an HTTP status, or the outcome's name.
Fetch = Callable[[str, str | None], str]


def _fetch(url: str, proxy: str | None) -> str:
    try:
        response = httpx.get(url, proxy=proxy, timeout=TIMEOUT_S, trust_env=False)
    except httpx.ProxyError as err:
        # httpx reports the proxy's CONNECT answer as the error text, e.g.
        # "403 Forbidden"; only the leading status token is kept
        token = str(err).split(" ", 1)[0]
        return f"proxy_{token}" if token.isdigit() else "proxy_error"
    except httpx.HTTPError as err:
        return type(err).__name__
    return str(response.status_code)


def hosted_hosts(allowlist_path: Path = ALLOWLIST) -> list[str]:
    """The allow-list's hosted-model hosts, which the proxy must admit."""
    rows = load_allowlist(allowlist_path).tiers.dev
    return sorted(e.host for e in rows if e.purpose_id is EgressPurpose.HOSTED_MODEL_INFERENCE)


def probe_proxy(proxy: str, hosts: Sequence[str], fetch: Fetch) -> tuple[list[str], list[str]]:
    """``(passes, failures)``; each line names a host and an outcome only."""
    passes: list[str] = []
    failures: list[str] = []
    direct = fetch(f"https://{UNLISTED_TARGETS[0]}/", None)
    if direct.isdigit():
        failures.append(f"direct route to {UNLISTED_TARGETS[0]} answered {direct}")
    else:
        passes.append(f"no direct route ({direct})")
    for target in UNLISTED_TARGETS:
        outcome = fetch(f"https://{target}/", proxy)
        if outcome == "proxy_403":
            passes.append(f"unlisted {target}: refused by the proxy (403)")
        else:
            failures.append(f"unlisted {target}: {outcome}, not the proxy's 403")
    if not hosts:
        passes.append("no hosted_model_inference row on the allow-list: nothing is admitted")
    for host in hosts:
        outcome = fetch(f"https://{host}/", proxy)
        if outcome.isdigit():
            passes.append(f"listed {host}: tunnelled (vendor answered {outcome})")
        else:
            failures.append(f"listed {host}: {outcome}")
    return passes, failures


def main(
    argv: Sequence[str],
    *,
    environ: Mapping[str, str] = os.environ,
    fetch: Fetch = _fetch,
    hosts: Callable[[], list[str]] = hosted_hosts,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    if list(argv) != ["proxy"]:
        print("usage: egress_probe.py proxy", file=stderr)
        return 64
    try:
        proxy = egress_proxy_url(environ)
    except EgressProxyRefused as err:
        print(f"egress: refused ({err})", file=stderr)
        return 2
    if proxy is None:
        print("egress: no forward proxy is configured", file=stderr)
        return 2
    passes, failures = probe_proxy(proxy, hosts(), fetch)
    for line in passes:
        print(f"egress: {line}", file=stdout)
    for line in failures:
        print(f"egress: FAIL {line}", file=stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
