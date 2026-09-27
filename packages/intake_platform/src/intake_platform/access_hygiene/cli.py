"""``python -m intake_platform.access_hygiene`` — one tick of the 60-day auto-disable.

The scheduler calls this (``make access-hygiene``; docs/runbooks/access-review.md
says what calls it, how often, and with which credentials). It reads the
OpenBao pointer the way every service does, builds the Keycloak and OpenBao
adapters from the deployment (:mod:`intake_platform.admin.access.config`),
appends to the audit chain through the audit writer's database role, and
prints one line per dormant account: its Keycloak id and what happened.
Identifiers only (invariant 6).

    exit 0  nothing dormant, or every dormant account offboarded (manual
            steps are listed for confirmation, as for any offboarding)
    exit 2  a step failed for at least one account: it is not fully offboarded
    exit 4  refused — not configured, the directory unreadable, or the realm
            keeps too little login history to tell who is dormant

``--dry-run`` lists who would be disabled and changes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Final

import httpx

from intake_platform.access_hygiene.job import HygieneReport, run_auto_disable
from intake_platform.admin.access import (
    ConsoleSystemsRefused,
    DirectoryUnavailable,
    IdentityWiring,
)
from intake_platform.admin.access.config import IdentityUnconfigured, identity_from_env
from intake_platform.admin.access.offboarding import StepOutcome
from intake_platform.admin.audit import AdminAuditSink
from intake_platform.secrets import SecretsBootError, SecretsProvider

__all__ = ["ENV_AUDIT_DB_URL", "EXIT_FAILED", "EXIT_OK", "EXIT_REFUSED", "main"]

EXIT_OK: Final = 0
EXIT_FAILED: Final = 2
EXIT_REFUSED: Final = 4

#: The audit writer's database URL — the same variable the API reads, and the
#: role (`svc_audit_writer`) that holds the audit table's only INSERT grant.
ENV_AUDIT_DB_URL: Final = "INTAKE_API_AUDIT_DB_URL"

_PREFIX: Final = "INT-366 access hygiene"


def _now() -> datetime:
    return datetime.now(UTC)


class _ChainSink:
    """The job's append-only seam onto the one hash-chained audit record."""

    def __init__(self, url: str) -> None:
        from sqlalchemy import create_engine

        from intake_platform.audit import AuditChain
        from intake_platform.db.audit_store import SqlAlchemyAuditStore

        self._chain = AuditChain(SqlAlchemyAuditStore(create_engine(url)))

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None:
        self._chain.append(
            actor=actor, action=action, resource_ref=resource_ref, consent_scope_ref=consent_scope
        )


def _print(report: HygieneReport) -> None:
    mode = " (dry run: nothing changed)" if report.dry_run else ""
    print(
        f"{_PREFIX}: {report.staff_accounts} staff accounts, {len(report.disabled)} with no "
        f"login for 60 days or more{mode}"
    )
    if report.dry_run:
        for subject in report.disabled:
            print(f"  {subject}  would be disabled")
        return
    for result in report.offboardings:
        failed = [step.system for step in result.steps if step.outcome is StepOutcome.FAILED]
        pending = [
            step.system for step in result.steps if step.outcome is StepOutcome.PENDING_CONFIRMATION
        ]
        print(
            f"  {result.subject}  offboarding {result.offboarding_id}  "
            f"failed: {failed or 'none'}  to confirm: {pending or 'none'}"
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    identity: IdentityWiring | None = None,
    sink: AdminAuditSink | None = None,
    clock: Callable[[], datetime] = _now,
) -> int:
    parser = argparse.ArgumentParser(
        prog="intake-access-hygiene",
        description=(
            "INT-366: disable every staff account with no login for 60 days (files/08 §2.4), "
            "through the one-action offboarding, audited."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="list, change nothing")
    args = parser.parse_args(argv)

    if identity is None:
        try:
            identity = identity_from_env(os.environ, SecretsProvider.from_env())
        except (
            SecretsBootError,
            IdentityUnconfigured,
            ConsoleSystemsRefused,
            httpx.HTTPError,
        ) as err:
            print(f"{_PREFIX}: refused — not configured ({type(err).__name__}: {err})")
            return EXIT_REFUSED
    if sink is None and not args.dry_run:
        url = os.environ.get(ENV_AUDIT_DB_URL, "").strip()
        if not url:
            print(
                f"{_PREFIX}: refused — {ENV_AUDIT_DB_URL} is not set; nothing is disabled unaudited"
            )
            return EXIT_REFUSED
        sink = _ChainSink(url)

    try:
        report = asyncio.run(run_auto_disable(identity, sink, now=clock(), dry_run=args.dry_run))
    except DirectoryUnavailable as err:
        print(f"{_PREFIX}: refused — {err.code}; nobody was disabled")
        return EXIT_REFUSED
    _print(report)
    return EXIT_OK if report.ok else EXIT_FAILED
