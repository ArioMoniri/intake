"""INT-205 — `python -m intake_platform.siem`: render the plan, judge the host.

What scripts/security/siem_up.sh calls, and what `make siem-dry` prints. A dry
render is never a failure — it reports a blocked host rather than exiting on it
— so that the plan stays readable on a machine that cannot run the tier. Only
``--enforce-host`` turns the verdict into an exit code, and that is what the
real run passes.
"""

from __future__ import annotations

import argparse
import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from intake_platform.siem.deploy import (
    RETENTION_ASK,
    RETENTION_ENV,
    DeployBlocked,
    host_preflight,
    plan_siem_deploy,
)
from intake_platform.siem.errors import SiemConfigError
from intake_platform.siem.rules import load_falco_ruleset, load_ossec_config, load_wazuh_ruleset

__all__ = ["main"]

REPO_ROOT = Path(__file__).resolve().parents[5]
_SECURITY = REPO_ROOT / "infra" / "security"


def _row(label: str, value: str) -> None:
    print(f"  {label:<17} {value}")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m intake_platform.siem",
        description="Render the INT-205 SIEM deployment plan and judge this host.",
    )
    parser.add_argument("--free-disk-bytes", type=int, default=None)
    parser.add_argument("--container-memory-bytes", type=int, default=None)
    parser.add_argument("--retention-days", type=int, default=None)
    parser.add_argument("--enforce-host", action="store_true")
    return parser.parse_args(argv)


def _retention(args: argparse.Namespace, env: Mapping[str, str]) -> int | None:
    if args.retention_days is not None:
        return int(args.retention_days)
    raw = env.get(RETENTION_ENV)
    if raw is None:
        return None
    if not raw.lstrip("-").isdigit():
        raise ValueError(f"{RETENTION_ENV}={raw!r} is not a number of days")
    return int(raw)


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = _parse(argv)
    environ = os.environ if env is None else env

    try:
        retention = _retention(args, environ)
    except ValueError as exc:
        print(f"refused: {exc}")
        print(f"refused: set {RETENTION_ENV} to a whole number of days (INT-212 owns the value)")
        return 2

    try:
        config = load_ossec_config(_SECURITY / "wazuh" / "ossec.conf")
        wazuh = load_wazuh_ruleset(_SECURITY / "wazuh" / "rules" / "intake_rules.xml")
        falco = load_falco_ruleset(_SECURITY / "falco" / "rules" / "intake_rules.yaml")
    except SiemConfigError as exc:
        print(f"refused: {exc}")
        return 2

    if retention is None:
        print(f"refused: {RETENTION_ASK}")
        return 2

    steps = plan_siem_deploy(retention)

    free_disk = (
        shutil.disk_usage(REPO_ROOT).free if args.free_disk_bytes is None else args.free_disk_bytes
    )
    memory = 0 if args.container_memory_bytes is None else args.container_memory_bytes
    verdict = host_preflight(free_disk_bytes=free_disk, docker_memory_bytes=memory)

    print("INT-205 — Wazuh + Falco tier")
    _row("ingests", f"{len(config.localfiles)} json sources")
    _row("wazuh rules", str(len(wazuh.rules)))
    _row("falco rules", str(len(falco.rules)))
    _row("retention", f"{retention} days")
    _row("host", "ready" if verdict is None else f"BLOCKED — {verdict.reason}")
    for step in steps:
        _row(step.name, " ".join(step.argv))

    if args.enforce_host and isinstance(verdict, DeployBlocked):
        return 3
    return 0
