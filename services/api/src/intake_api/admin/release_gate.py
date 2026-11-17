"""The release gate the deploy path runs (INT-187; files/08 §3, §8.2, §9).

``infra/staging/deploy.sh`` — the only deploy path this repository has, since
Argo CD is not deployed — runs, before it touches the host::

    compose run --rm --no-deps -T api python -m intake_api.admin.release_gate

in a one-off container of the image it just built, on the project network,
with the api's own environment. This module reads the deployment's freeze
record and its error budget, applies
:func:`intake_platform.release_freeze.release_verdict` — the same rule the
console's deploy-gate tile renders — prints what it decided, one line per
reason, and exits:

- ``0`` — allowed;
- ``3`` — refused: deploys are frozen, an SLO's error budget is exhausted, or
  something the verdict needs could not be read (the freeze store unset,
  unreachable or malformed; a declared Prometheus that cannot answer). Fail
  closed: a gate that cannot see the freeze does not get to assume there is
  none. Any other exit code means the gate itself did not run, and deploy.sh
  refuses that too.

:func:`error_budget` lives here and the console imports it, so the deploy path
and the page cannot disagree about a budget.

**Nothing secret is printed.** The store URL carries the Redis password; it is
never echoed — a malformed value is reported by its variable's name, a failed
connection as a code. The freeze's reason text never enters the record, so it
cannot reach this output either (invariant 6): the lines carry codes, a staff
subject and a timestamp.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, TextIO

import yaml
from intake_platform.release_freeze import (
    DeployFreeze,
    ErrorBudget,
    ReleaseFreezeStore,
    ReleaseFreezeUnavailable,
    release_freeze_store_from_env,
    release_verdict,
)
from intake_platform.slo import SLOFile

from intake_api.admin.ops_prom import PromClient, PromSession, TileUnknown, prom_client_from_env
from intake_api.admin.reliability_console import ENV_SLO_DIR, load_slo_files
from intake_api.admin.reliability_slo import slo_label_sets, slo_queries, slo_tile

__all__ = [
    "EXIT_ALLOWED",
    "EXIT_REFUSED",
    "error_budget",
    "main",
    "read_freeze",
    "run_gate",
]

EXIT_ALLOWED: Final = 0
EXIT_REFUSED: Final = 3
_DEFAULT_SLO_DIR: Final = "docs/slo"
#: An SLO these reasons blank has nothing measured — noted, never "within
#: budget". Every other unknown reason is a source that failed to answer.
_UNMEASURED: Final = frozenset({"no_series", "sli_outside_console_grammar"})

_WHY: Final[Mapping[str, str]] = {
    "deploy_freeze_engaged": "deploys are frozen from the console",
    "error_budget_exhausted": "an SLO's error budget is exhausted",
    "error_budget_unreadable": "the declared error-budget source did not answer",
    "release_freeze_unconfigured": "no freeze store is configured, so the freeze cannot be read",
    "release_freeze_misconfigured": "the freeze store variable is not a redis:// URL",
    "release_freeze_unreachable": "the freeze store did not answer",
    "release_freeze_malformed": "the freeze record is not one this gate can read",
    "error_budget_not_configured": "no Prometheus is declared for this tier; "
    "the error-budget freeze is not evaluated here",
    "error_budget_unmeasured": "some SLOs have no series yet; "
    "they are not counted as within budget",
}


def error_budget(
    prom: PromClient | None,
    slo_files: Sequence[SLOFile] | None,
    prom_misconfigured: bool,
) -> tuple[ErrorBudget, dict[str, Any]]:
    """The error budget from the SLO files' SLIs, and its console tile.

    ``prom`` unset is a tier that declares no budget source (noted, not
    refused); a Prometheus URL that is set but malformed, SLO files that do
    not load, or a Prometheus that cannot answer are a declared source that
    failed (refused). An SLO with no series is unmeasured, never within budget.
    """
    if prom is None:
        if prom_misconfigured:
            return ErrorBudget.failed("prometheus_misconfigured"), _budget_tile(
                "prometheus_misconfigured"
            )
        return ErrorBudget.not_configured(), _budget_tile("prometheus_unconfigured")
    if slo_files is None:
        return ErrorBudget.failed("slo_files_unreadable"), _budget_tile("slo_files_unreadable")
    queries = slo_queries(slo_files)
    session = PromSession(prom, queries, slo_label_sets(queries))
    exhausted: list[str] = []
    unmeasured: list[str] = []
    for slo_file in slo_files:
        for slo in slo_file.slos:
            name = f"{slo_file.service}/{slo.name}"
            try:
                remaining = slo_tile(session, slo_file, slo)["error_budget_remaining"]
            except TileUnknown as unknown:
                if unknown.reason in _UNMEASURED:
                    unmeasured.append(name)
                    continue
                return ErrorBudget.failed(unknown.reason), _budget_tile(unknown.reason)
            if remaining is None:
                unmeasured.append(name)
            elif remaining <= 0:
                exhausted.append(name)
    budget = ErrorBudget.measured(exhausted=tuple(exhausted), unmeasured=tuple(unmeasured))
    return budget, {
        "state": "ok",
        "reason": None,
        "exhausted": list(budget.exhausted),
        "unmeasured": list(budget.unmeasured),
    }


def _budget_tile(reason: str) -> dict[str, Any]:
    return {"state": "unknown", "reason": reason, "exhausted": [], "unmeasured": []}


def read_freeze(store: ReleaseFreezeStore | None) -> tuple[DeployFreeze | None, str | None]:
    """The freeze, or ``None`` and the code that says why it could not be read."""
    if store is None:
        return None, "release_freeze_unconfigured"
    try:
        return store.read(), None
    except ReleaseFreezeUnavailable as failure:
        return None, failure.code


def run_gate(
    *,
    store: ReleaseFreezeStore | None,
    store_failure: str | None,
    prom: PromClient | None,
    prom_misconfigured: bool,
    slo_files: Sequence[SLOFile] | None,
    out: TextIO,
) -> int:
    """Decide, print one line per reason, and return the exit code."""
    freeze: DeployFreeze | None
    failure: str | None
    if store_failure is not None:
        freeze, failure = None, store_failure
    else:
        freeze, failure = read_freeze(store)
    budget, _ = error_budget(prom, slo_files, prom_misconfigured)
    verdict = release_verdict(freeze=freeze, freeze_failure=failure, budget=budget)
    decision = "allowed" if verdict.allowed else "refused"
    print(f"release gate: {decision}", file=out)
    for code in verdict.refusals:
        print(f"release gate: refused {code} - {_WHY.get(code, code)}", file=out)
    if freeze is not None and freeze.engaged:
        at = freeze.changed_at.isoformat() if freeze.changed_at else "-"
        print(
            f"release gate: freeze revision {freeze.revision} engaged at {at} "
            f"by {freeze.changed_by or '-'} (reason class {freeze.reason_class or '-'})",
            file=out,
        )
    for name in budget.exhausted:
        print(f"release gate: error budget exhausted: {name}", file=out)
    if budget.failure is not None:
        print(f"release gate: error-budget source failed: {budget.failure}", file=out)
    for code in verdict.notes:
        print(f"release gate: note {code} - {_WHY.get(code, code)}", file=out)
    return EXIT_ALLOWED if verdict.allowed else EXIT_REFUSED


def main(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None) -> int:
    """The deploy path's entry point. Takes no arguments: everything it reads
    is the api's own environment, so nothing on the command line can steer it."""
    env = os.environ if env is None else env
    store: ReleaseFreezeStore | None
    store_failure: str | None = None
    try:
        store = release_freeze_store_from_env(env)
    except ValueError:
        store, store_failure = None, "release_freeze_misconfigured"
    try:
        prom, misconfigured = prom_client_from_env(env), False
    except ValueError:
        prom, misconfigured = None, True
    try:
        files: tuple[SLOFile, ...] | None = load_slo_files(
            Path(env.get(ENV_SLO_DIR, "").strip() or _DEFAULT_SLO_DIR)
        )
    except (OSError, ValueError, yaml.YAMLError):
        files = None
    return run_gate(
        store=store,
        store_failure=store_failure,
        prom=prom,
        prom_misconfigured=misconfigured,
        slo_files=files,
        out=sys.stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
