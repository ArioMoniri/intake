"""INT-102 — the nightly LLM red-team job (files/10 §9 row ``llm-boundary``).

files/10 §9 pairs the recorded scenarios RT-09…RT-12 with a *"nightly LLM
red-team (promptfoo/garak style)"*. The recorded half runs in ``make safety``
against fixtures and calls nothing. **This** is the half that would reach a
live model, and CLAUDE.md is unambiguous about it: *"Never call paid/live APIs
in tests or CI. Live evals run only via `make eval-live` with
`EVAL_BUDGET_USD`."*

So the design problem is not "how does the job call a model" — it is **how the
job is made unreachable from the gates**, structurally rather than by
convention. Four mechanisms, and each is asserted in
``tests/safety/test_nightly_red_team.py``:

1. **This module imports no HTTP client.** There is no transport in it, at
   module scope or inside a function. A judge is a parameter
   (:class:`RedTeamClient`), never something this file can construct — so
   "reaches a model" is not a state the module can enter on its own. A test
   walks this file's own ``ast`` and fails on any networking import.
2. **The budget gate runs before the client is even looked up.** Both
   ``EVAL_BUDGET_USD`` and ``INTAKE_RED_TEAM_MAX_CALLS`` are required with no
   defaults, and a budget above the 20 USD ceiling CLAUDE.md reserves for a
   human decision is refused. A run with the environment unset consults no
   factory at all.
3. **``--plan`` cannot call.** It never touches the client seam; it enumerates
   the cases and prints them. That is the mode ``make safety`` runs, and a
   counting factory proves the seam is untouched.
4. **The build graph is checked.** ``nightly-red-team`` is not in the
   prerequisite closure of ``check``, ``check-py`` or ``safety``, and no recipe
   in that closure names this file with ``--run``. The test computes the
   closure from the Makefile and has a control Makefile it does catch.

**The cases come from files/04, not from here.** ``load_cases`` re-reads the
adversarial line and takes the ``RT-nn`` ids out of it, exactly as the suite's
scenario table does, so the job and the suite cannot disagree about what is
being red-teamed without one of them failing.

On this tree ``--run`` refuses: :func:`client_from_env` returns ``None``,
because no live judge is configured anywhere in this repository. That refusal
is the honest state and is reported with an exit code, not with a synthesised
score — a red-team number nobody measured is worse than no number
(CLAUDE.md invariant 20).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, Protocol, TextIO

REPO = Path(__file__).resolve().parents[2]
BLUEPRINT = REPO / "files" / "04_CLINICAL_PROTOCOLS.md"

ENV_BUDGET_USD: Final = "EVAL_BUDGET_USD"
ENV_MAX_CALLS: Final = "INTAKE_RED_TEAM_MAX_CALLS"

#: CLAUDE.md §When to stop and ask the human: *"Any spend > 20 USD on live
#: evals"*. The job refuses rather than asking, because there is nobody to ask
#: at 03:00 and a nightly that pauses for an answer is a nightly that hangs.
HUMAN_DECISION_CEILING_USD: Final = Decimal("20")

#: The exit codes, so a scheduler can tell the three refusals apart.
EXIT_OK: Final = 0
EXIT_USAGE: Final = 2
EXIT_BUDGET: Final = 3
EXIT_NO_JUDGE: Final = 4

_CASE_ID = re.compile(r"\bRT-(\d{2})\b")
_ADVERSARIAL_MARKER: Final = "**Adversarial & security scenarios"


class RedTeamRefused(RuntimeError):
    """The job refuses to start. Carries the reason, never a payload."""


@dataclass(frozen=True)
class Budget:
    """What one nightly run is allowed to spend, and how many calls it may make.

    Both halves are required: a dollar cap with no call cap is a cap that a
    mispriced model walks through, and a call cap with no dollar cap is not a
    budget at all.
    """

    usd: Decimal
    max_calls: int


class RedTeamClient(Protocol):
    """The judge seam. A parameter, never something this module constructs."""

    def judge(self, case_id: str, prompt: str) -> str: ...


#: How a judge is obtained. Injectable so a test can count consultations of the
#: seam and prove the budget gate runs first.
ClientFactory = Callable[[Mapping[str, str]], "RedTeamClient | None"]


def blueprint_line(path: Path = BLUEPRINT) -> str:
    """The one line of files/04 §6 that defines the adversarial scenarios."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(_ADVERSARIAL_MARKER):
            return line
    raise RedTeamRefused(
        f"{path.name} carries no adversarial-scenario line — the job takes its "
        "cases from the blueprint and will not invent a case list"
    )


def load_cases(path: Path = BLUEPRINT) -> tuple[str, ...]:
    """The case ids, in file order, de-duplicated."""
    line = blueprint_line(path)
    seen: list[str] = []
    for match in _CASE_ID.finditer(line):
        case_id = f"RT-{match.group(1)}"
        if case_id not in seen:
            seen.append(case_id)
    if not seen:
        raise RedTeamRefused("the adversarial line names no RT-nn case")
    return tuple(seen)


def read_budget(env: Mapping[str, str]) -> Budget:
    """Both caps, or a refusal. Nothing here has a default."""
    raw_usd = env.get(ENV_BUDGET_USD)
    raw_calls = env.get(ENV_MAX_CALLS)
    missing = [
        name for name, value in ((ENV_BUDGET_USD, raw_usd), (ENV_MAX_CALLS, raw_calls)) if not value
    ]
    if missing:
        raise RedTeamRefused(
            f"set {' and '.join(missing)} — the nightly red team reaches a live model "
            "and neither cap has a default (CLAUDE.md §How we work)"
        )
    try:
        usd = Decimal(str(raw_usd))
    except InvalidOperation as err:
        raise RedTeamRefused(f"{ENV_BUDGET_USD} is not a decimal amount") from err
    if usd <= 0:
        raise RedTeamRefused(f"{ENV_BUDGET_USD} must be positive")
    if usd > HUMAN_DECISION_CEILING_USD:
        raise RedTeamRefused(
            f"{ENV_BUDGET_USD}={usd} exceeds the {HUMAN_DECISION_CEILING_USD} USD ceiling "
            "CLAUDE.md reserves for a human decision — raise it in a PR a person signs, "
            "not in a scheduler's environment"
        )
    if not str(raw_calls).isdigit() or int(str(raw_calls)) <= 0:
        raise RedTeamRefused(f"{ENV_MAX_CALLS} must be a positive integer")
    return Budget(usd=usd, max_calls=int(str(raw_calls)))


def client_from_env(env: Mapping[str, str]) -> RedTeamClient | None:
    """The live judge, or ``None`` because there is not one.

    Deliberately not a lookup that could succeed by accident: this repository
    configures no red-team judge, self-hosted or otherwise, so the honest
    return is ``None`` and the run reports it. Wiring one is a change to this
    function under review, which is the point — a judge that could appear from
    an environment variable is a live model call one export away.
    """
    del env
    return None


def plan(cases: Sequence[str], out: TextIO | None = None) -> int:
    """Enumerate what the nightly would judge. Touches no seam, calls nothing."""
    stream = sys.stdout if out is None else out
    print(f"nightly red team: {len(cases)} cases from {BLUEPRINT.name}", file=stream)
    for case_id in cases:
        print(f"  {case_id}", file=stream)
    print("plan only: no judge was consulted and no model was called", file=stream)
    return EXIT_OK


def run(
    env: Mapping[str, str],
    *,
    factory: ClientFactory | None = None,
    cases: Sequence[str] | None = None,
) -> int:
    """The live lane. Budget first, judge second, and on this tree it stops.

    ``factory`` is the client seam, injectable so a test can prove it is never
    consulted when the budget refuses. It defaults to :func:`client_from_env`,
    which returns ``None``.
    """
    budget = read_budget(env)  # before anything else, deliberately
    resolve: ClientFactory = client_from_env if factory is None else factory
    client = resolve(env)
    selected = load_cases() if cases is None else tuple(cases)
    if client is None:
        print(
            "nightly red team: refusing — no judge is configured in this repository, "
            f"so nothing was invoked. Budget {budget.usd} USD / {budget.max_calls} calls "
            f"was accepted for {len(selected)} cases and spent nothing.",
            file=sys.stderr,
        )
        return EXIT_NO_JUDGE
    for case_id in selected[: budget.max_calls]:
        client.judge(case_id, blueprint_line())
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nightly_red_team",
        description="INT-102 nightly LLM red team. --plan calls nothing; --run "
        "requires both budget caps and refuses without a configured judge.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="enumerate cases; call nothing")
    mode.add_argument("--run", action="store_true", help="the live lane (budgeted)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.plan:
            return plan(load_cases())
        return run(os.environ)
    except RedTeamRefused as refusal:
        print(f"nightly red team: {refusal}", file=sys.stderr)
        return EXIT_BUDGET


if __name__ == "__main__":  # pragma: no cover - the console entry point
    raise SystemExit(main())
