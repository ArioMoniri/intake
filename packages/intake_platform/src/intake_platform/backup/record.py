"""INT-202 — write the drill's evidence record (files/10 §3: "quarterly
restore drills with evidence in the console").

The record is the artefact ``services/probes``' ``backup_freshness`` probe
reads and the console renders, so its shape is load-bearing and its content
is deliberately narrow: clocks, budgets, a verdict, and one integer per
public table. :func:`build_record` starts from
:func:`~intake_platform.backup.drill.drill_evidence_skeleton`, which has no
field an identifier could occupy, and refuses any row-count line whose value
is not an integer — an unparseable line is dropped rather than carried
through, because the one way patient text could reach this file is a psql
error string arriving where a count was expected (invariant 6).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import load_pgbackrest_config
from .drill import RTO_BUDGET_S, drill_evidence_skeleton

#: psql is invoked with ``--field-separator=:``; each line is ``relname:count``.
_SEPARATOR = ":"

#: Table names are identifiers, not content. Anything else on the left of the
#: separator is a psql notice or an error, and is discarded.
_MAX_RELNAME = 63


def parse_row_counts(raw: str) -> dict[str, int]:
    """Turn psql's tuples-only output into ``{table: count}``.

    Lines that are not exactly a bare identifier and an integer are dropped.
    That is the point: the parser cannot pass anything through that is not a
    count, so a psql error carrying a fragment of a row cannot land in the
    evidence file.
    """
    counts: dict[str, int] = {}
    for line in raw.splitlines():
        name, separator, value = line.strip().partition(_SEPARATOR)
        if not separator:
            continue
        name = name.strip()
        if not name.isidentifier() or len(name) > _MAX_RELNAME:
            continue
        try:
            counts[name] = int(value.strip())
        except ValueError:
            continue
    return counts


def build_record(
    config_path: Path,
    env: Mapping[str, str],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fill the evidence skeleton from the drill's environment."""
    config = load_pgbackrest_config(config_path)
    retention = env.get("PGBACKREST_REPO1_RETENTION_FULL", "").strip()
    record = drill_evidence_skeleton(config, int(retention) if retention else None)

    restore_seconds = int(env.get("DRILL_RESTORE_SECONDS", "0") or 0)
    record["started_at"] = env.get("DRILL_STARTED_AT") or None
    record["finished_at"] = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    record["recovery_target_time"] = env.get("DRILL_RECOVERY_TARGET") or None
    record["restore_seconds"] = restore_seconds
    record["row_counts"] = parse_row_counts(env.get("DRILL_ROW_COUNTS", ""))
    record["host_preflight"] = "ready"
    record["verdict"] = "pass" if restore_seconds <= RTO_BUDGET_S else "rto_exceeded"
    return record


def main(env: Mapping[str, str] | None = None) -> int:
    environ = os.environ if env is None else env
    repo_root = Path(environ.get("INTAKE_REPO_ROOT", ".")).resolve()
    config_path = Path(
        environ.get("INTAKE_PGBACKREST_CONF", str(repo_root / "infra/backup/pgbackrest.conf"))
    )
    out_dir = Path(environ.get("DRILL_EVIDENCE_DIR", str(repo_root / ".cache/backups")))
    out_dir.mkdir(parents=True, exist_ok=True)

    record = build_record(config_path, environ)
    stamp = str(record["finished_at"]).replace(":", "").replace("-", "")
    out_path = out_dir / f"restore-drill-{stamp}.json"
    out_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"restore drill evidence: {out_path} — verdict {record['verdict']}, "
        f"{len(record['row_counts'])} tables counted"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the drill script
    raise SystemExit(main())
