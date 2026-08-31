#!/usr/bin/env python3
"""The nightly adversarial LLM-judge job (INT-102) — entry point.

files/10 §9 row ``llm-boundary`` pairs the RT-09…RT-12 injection scenarios
with a *"nightly LLM red-team (promptfoo/garak style)"*. This is that job's
command. It has two modes and they are not symmetric on purpose:

``--plan``
    Enumerate the RT-09…RT-14 cases, read from files/04 line 203 itself, and
    print what a run would put to a judge. Costs nothing, reaches nothing,
    and is safe in CI — ``make safety`` runs it, which is how the wiring stays
    checked rather than asserted.

``--run``
    Attempt the run. It requires ``EVAL_BUDGET_USD`` and
    ``INTAKE_JUDGE_MAX_COST_PER_CALL_USD`` — neither has a default — and a
    judge client, of which **this repository contains none**. So on any host
    without one deliberately wired in, ``--run`` refuses and exits non-zero,
    having invoked nothing. That is the intended behaviour, not a limitation:
    CLAUDE.md forbids calling a paid or live API from tests or CI, ``make
    eval-live`` is the only live path in the product, and a judgement produced
    without a judge would be a fabricated measurement under invariant 20.

Exit codes: ``0`` the mode completed; ``2`` the run was refused (the reason is
printed and names the missing piece). A refusal is never softened into a pass.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "llm-evals" / "src"))

from llm_evals.judge import (  # noqa: E402  - after the path wiring above
    ENV_BUDGET_USD,
    ENV_MAX_COST_PER_CALL_USD,
    JudgeError,
    NightlyJudgeJob,
    judge_budget_from_env,
)

BLUEPRINT = REPO / "files" / "04_CLINICAL_PROTOCOLS.md"
BLUEPRINT_LINE_NO = 203


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, add_help=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--plan",
        action="store_true",
        help="enumerate the RT-09..14 cases; invokes nothing and costs nothing",
    )
    mode.add_argument(
        "--run",
        action="store_true",
        help="attempt the judged run; refuses without a budget and a judge client",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    job = NightlyJudgeJob.from_blueprint(BLUEPRINT, line_no=BLUEPRINT_LINE_NO)

    if args.plan:
        print(
            f"nightly adversarial judge — plan only, no judge invoked "
            f"({len(job.plan())} case(s) from {BLUEPRINT.name} line {BLUEPRINT_LINE_NO})"
        )
        for case in job.plan():
            print(f"  {case.case_id}: {case.blueprint_line}")
        print(
            f"  a judged run additionally requires {ENV_BUDGET_USD}, "
            f"{ENV_MAX_COST_PER_CALL_USD} and a judge client"
        )
        return 0

    try:
        budget = judge_budget_from_env()
    except JudgeError as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 2

    # There is no judge client in this repository. The seam is
    # ``llm_evals.judge.JudgeClient``; wiring one is a deliberate, reviewed act
    # on a host that is allowed to spend, never a default this script supplies.
    try:
        run = job.run(budget=budget, client=None)
    except JudgeError as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 2

    for line in run.render():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
