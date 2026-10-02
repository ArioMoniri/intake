"""INT-202 — ``python -m intake_platform.backup``: render the drill plan.

``scripts/backup/restore_drill.sh --dry-run`` and ``make backup-drill-dry``
print this, and ``infra/staging/backup.sh replicate`` pipes
``--emit-replication`` into the object store's own client. Printing is all
this does: nothing here opens a socket or starts a container.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from .config import (
    BackupConfigError,
    load_pgbackrest_config,
    load_replication_plan,
    replication_commands,
    withheld_rules,
)
from .drill import plan_restore_drill
from .status import RETENTION_CEILING_DAYS, RPO_BUDGET_S, RTO_BUDGET_S

EXIT_OK = 0
EXIT_REFUSED = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="intake-backup-drill", description="INT-202: render the restore drill plan."
    )
    parser.add_argument("--infra", type=Path, required=True, help="path to infra/backup")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--show-replication", action="store_true")
    parser.add_argument(
        "--emit-replication",
        action="store_true",
        help="print only the mc commands, one per line, for piping into a shell",
    )
    return parser


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    environ = os.environ if env is None else env

    try:
        config = load_pgbackrest_config(args.infra / "pgbackrest.conf")
        plan = load_replication_plan(args.infra / "minio-replication.yaml")
        steps = plan_restore_drill(config)
    except (BackupConfigError, OSError) as err:
        print(f"INT-202 restore drill: configuration refused — {err}")
        return EXIT_REFUSED

    if args.emit_replication:
        for command in replication_commands(plan):
            print(" ".join(command))
        return EXIT_OK

    print("INT-202 restore drill — plan")
    print(f"  stanza            {config.stanza}")
    print(f"  repository        {config.repo_type}:{config.repo_path}")
    print(
        f"  encrypted at rest {config.repo_cipher_type} "
        f"(passphrase from {config.cipher_pass_env}, never a file)"
    )
    if config.retention_full is None:
        print(
            "  retention         not set — nothing expires until the owner answers HB-I8(a); "
            f"a window must be ≤ {RETENTION_CEILING_DAYS} days (files/06 §1)"
        )
    else:
        print(f"  retention         {config.retention_full} days")
    endpoint = environ.get(plan.target_endpoint_env, "").strip()
    if endpoint:
        print(f"  second location   configured via ${plan.target_endpoint_env}")
    else:
        print(
            f"  second location   NOT CONFIGURED — ${plan.target_endpoint_env} "
            "has no default (HB-I8(b))"
        )
    for rule, reason in withheld_rules(plan):
        print(f"  withheld          {rule.bucket}: {reason}")
    print(f"  budgets           RPO {RPO_BUDGET_S}s · RTO {RTO_BUDGET_S}s")
    for index, step in enumerate(steps, 1):
        print(f"  {index:>2}. {step.name:<21} {step.description}")
        print(f"       [{step.where}] $ {' '.join(step.argv)}")

    if args.show_replication:
        print("  replication:")
        for command in replication_commands(plan):
            print(f"       $ {' '.join(command)}")
    return EXIT_OK
