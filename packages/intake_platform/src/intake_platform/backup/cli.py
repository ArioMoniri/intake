"""INT-202 — ``python -m intake_platform.backup``: render or gate the drill.

``scripts/backup/restore_drill.sh`` calls this for both halves of its work, so
the plan the operator reads and the plan the script executes are the same
list of steps built by the same code. Printing is all this does; nothing here
opens a socket or starts a container.
"""

from __future__ import annotations

import argparse
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from .config import (
    RETENTION_FULL_ENV,
    BackupConfigError,
    load_pgbackrest_config,
    load_replication_plan,
    replication_commands,
)
from .drill import (
    RetentionNotConfiguredError,
    drill_evidence_skeleton,
    host_preflight,
    plan_restore_drill,
)

#: Exit codes. 0 the plan is sound · 2 the configuration or the environment
#: refuses · 3 the host cannot run it (a refusal, not a failure).
EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_HOST_BLOCKED = 3


def _retention_from_env(env: dict[str, str]) -> int | None:
    raw = env.get(RETENTION_FULL_ENV, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return -1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="intake-backup-drill",
        description="INT-202 restore drill: render the plan, or gate a real run.",
    )
    parser.add_argument("--infra", type=Path, required=True, help="path to infra/backup")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument(
        "--enforce-host",
        action="store_true",
        help="exit non-zero when the host cannot run the drill (the real run does)",
    )
    parser.add_argument("--free-disk-bytes", type=int, default=None)
    parser.add_argument("--container-memory-bytes", type=int, default=0)
    parser.add_argument("--show-replication", action="store_true")
    parser.add_argument(
        "--emit-replication",
        action="store_true",
        help="print only the mc commands, one per line, for piping into a shell",
    )
    return parser


def main(argv: Sequence[str] | None = None, env: dict[str, str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    environ = dict(os.environ) if env is None else env

    try:
        config = load_pgbackrest_config(args.infra / "pgbackrest.conf")
        plan = load_replication_plan(args.infra / "minio-replication.yaml")
    except (BackupConfigError, OSError) as err:
        print(f"INT-202 restore drill: configuration refused — {err}")
        return EXIT_REFUSED

    if args.emit_replication:
        # Only the commands, so the caller pipes them into a shell without
        # having to grep the plan back out of prose.
        for command in replication_commands(plan):
            print(" ".join(command))
        return EXIT_OK

    print("INT-202 restore drill — plan")
    print(f"  stanza            {config.stanza}")
    print(f"  repository        {config.repo_type}://{config.repo_bucket}")
    print(
        f"  encrypted at rest {config.repo_cipher_type} "
        f"(passphrase from {config.cipher_pass_env}, never from a file)"
    )
    print(f"  second location   {plan.target_alias} via ${plan.target_endpoint_env}")

    try:
        steps = plan_restore_drill(config, plan, _retention_from_env(environ))
    except RetentionNotConfiguredError as err:
        print(f"  REFUSED: {err}")
        return EXIT_REFUSED
    except ValueError as err:
        print(f"  REFUSED: {err}")
        return EXIT_REFUSED

    for index, step in enumerate(steps, 1):
        print(f"  {index}. {step.name:<17} {step.description}")
        print(f"       $ {' '.join(step.argv)}")

    if args.show_replication:
        print("  replication:")
        for command in replication_commands(plan):
            print(f"       $ {' '.join(command)}")

    skeleton = drill_evidence_skeleton(config, _retention_from_env(environ))
    print(
        f"  budgets           RPO {skeleton['rpo_budget_s']}s · RTO {skeleton['rto_budget_s']}s"
        f" · retention {skeleton['retention_full']} full"
    )

    free_disk = args.free_disk_bytes
    if free_disk is None:
        free_disk = shutil.disk_usage(args.repo_root).free
    blocked = host_preflight(free_disk, args.container_memory_bytes)
    if blocked is None:
        print("  host              ready")
        return EXIT_OK
    print(f"  host              BLOCKED — {blocked.reason}")
    return EXIT_HOST_BLOCKED if args.enforce_host else EXIT_OK
