"""The daily audit-chain verifier as a runnable, observable job (INT-016).

``intake_platform.audit.run_daily_verifier`` is pure and stays pure. What it
lacked was anything that RUNS it: the chain was verified only when a test
called the function. This module is the smallest thing that fixes that
without inventing a service — a batch entry point:

    python -m intake_platform.audit_verify --audit-db-url <url> \\
        [--expected-head <sha256>] [--metrics-file <path>]

Three outputs, because a scheduler reads all three differently:

- **exit code** — :data:`EXIT_OK`, :data:`EXIT_BROKEN`, :data:`EXIT_UNUSABLE`.
  The third is not the second: a chain that could not be READ (bad URL,
  unreachable database, missing table) is an operational failure, and
  reporting it as a tamper finding would page the wrong on-call and teach them
  to discount the real one.
- **one JSON object on stdout** — ids, counts, seqs and hashes only. Never the
  connection string (it carries credentials) and never an entry's content
  (invariant 6).
- **``sec_audit_chain_ok``**, optionally written in the Prometheus textfile
  format for a node-exporter collector. The id is already in
  observability/metrics_catalog.yaml, so nothing uncatalogued is emitted
  (invariant 13); the gauge is built in a LOCAL registry so importing this
  module never adds a series to a service's ``/metrics``.

**What this deliberately does not do.** It does not schedule itself: no cron,
no Celery beat, no ``services/workers``. It does not fetch the externally
anchored head — that transport (files/10 §2's hourly publication outside the
``platform_admin`` blast radius, invariant 40) does not exist yet, so the head
is an INPUT here. A run without one reports ``anchored: false`` rather than a
green tick that overstates what was proved: an unanchored chain walk cannot
catch an attacker who edits a row and recomputes the chain forward.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Final

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from intake_platform.audit import GENESIS_PREV_HASH, AuditEntry, run_daily_verifier
from intake_platform.db.audit_store import SqlAlchemyAuditStore

__all__ = ["EXIT_BROKEN", "EXIT_OK", "EXIT_UNUSABLE", "METRIC_NAME", "main"]

EXIT_OK: Final = 0
EXIT_BROKEN: Final = 1
EXIT_UNUSABLE: Final = 2

#: observability/metrics_catalog.yaml, group "sec": name ``sec_audit_chain_ok``
#: / id ``sec.audit_chain_ok``, gauge, unit "bool (0/1)", owner security.
METRIC_NAME: Final = "sec_audit_chain_ok"
_METRIC_HELP: Final = "Daily audit hash-chain verification (1 = intact)."

_URL_ENV: Final = "INTAKE_AUDIT_DB_URL"


def _write_metric(path: str, ok: bool) -> None:
    """Prometheus textfile-collector output, via a LOCAL registry so no series
    is added to the importing process's default collector."""
    from prometheus_client import CollectorRegistry, Gauge, write_to_textfile

    registry = CollectorRegistry()
    gauge = Gauge(METRIC_NAME, _METRIC_HELP, registry=registry)
    gauge.set(1.0 if ok else 0.0)
    write_to_textfile(path, registry)


def _head_of(entries: Sequence[AuditEntry]) -> str:
    return entries[-1].entry_hash if entries else GENESIS_PREV_HASH


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m intake_platform.audit_verify",
        description="Verify the hash-chained audit log (INT-016, files/10 §2).",
    )
    parser.add_argument(
        "--audit-db-url",
        default=os.environ.get(_URL_ENV),
        help=f"SQLAlchemy URL of the audit database (default: ${_URL_ENV}).",
    )
    parser.add_argument(
        "--expected-head",
        default=None,
        help=(
            "The externally anchored chain head to check against (invariant 40). "
            "Omitted: the run is unanchored and says so."
        ),
    )
    parser.add_argument(
        "--metrics-file",
        default=None,
        help=f"Write {METRIC_NAME} here in the Prometheus textfile format.",
    )
    return parser.parse_args(list(argv))


def _emit(report: dict[str, object], metrics_file: str | None, ok: bool) -> None:
    if metrics_file is not None:
        _write_metric(metrics_file, ok)
    json.dump(report, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    metrics_file: str | None = args.metrics_file

    if not args.audit_db_url:
        _emit(
            {"check": "audit_chain", "ok": False, "error": "audit_db_url_missing"},
            metrics_file,
            ok=False,
        )
        return EXIT_UNUSABLE

    try:
        engine = create_engine(args.audit_db_url)
    except (SQLAlchemyError, ValueError):
        # the URL itself is unusable; it is NOT echoed (it carries credentials)
        _emit(
            {"check": "audit_chain", "ok": False, "error": "audit_db_url_unusable"},
            metrics_file,
            ok=False,
        )
        return EXIT_UNUSABLE

    try:
        store = SqlAlchemyAuditStore(engine)
        entries = store.entries()
        result = run_daily_verifier(store, expected_head=args.expected_head)
    except SQLAlchemyError:
        # unreadable is not tampered: report it as its own failure class
        _emit(
            {"check": "audit_chain", "ok": False, "error": "audit_store_unreadable"},
            metrics_file,
            ok=False,
        )
        return EXIT_UNUSABLE
    finally:
        engine.dispose()

    report: dict[str, object] = {
        "check": "audit_chain",
        "ok": result.ok,
        "anchored": args.expected_head is not None,
        "entry_count": len(entries),
        "chain_head": _head_of(entries),
        "first_bad_seq": result.first_bad_seq,
        "reason": result.reason,
    }
    _emit(report, metrics_file, ok=result.ok)
    return EXIT_OK if result.ok else EXIT_BROKEN


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
