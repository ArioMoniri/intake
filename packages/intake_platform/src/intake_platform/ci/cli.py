"""INT-206 — `python -m intake_platform.ci`: run the no-PHI-in-CI policy.

Exit 0 when every surface is clean, 1 on the first finding. The report names a
surface, a location and a digest; it never prints the value that triggered it,
because this command's stdout is a CI job log.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from os import environ
from pathlib import Path

from intake_platform.ci.errors import CiPolicyError
from intake_platform.ci.policy import run_ci_policy

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="intake-ci-policy",
        description="The no-PHI-in-CI policy over one repository (INT-206).",
    )
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="repository root (default: cwd)"
    )
    parser.add_argument(
        "--scan-environment",
        action="store_true",
        help="include this process's own environment — the form the CI job runs",
    )
    args = parser.parse_args(argv)

    env = dict(environ) if args.scan_environment else {}
    try:
        findings = run_ci_policy(args.repo, env=env)
    except CiPolicyError as err:
        print(f"no_phi_in_ci: FAIL — {err}")
        return 1

    if not findings:
        print("no_phi_in_ci: OK — fixtures, env, logs, artefacts, cache and runners clean")
        return 0

    print(f"no_phi_in_ci: FAIL — {len(findings)} finding(s) (CLAUDE.md invariant 6):")
    for finding in findings:
        print(f"  [{finding.surface.value}] {finding.where}: {finding.detail}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
