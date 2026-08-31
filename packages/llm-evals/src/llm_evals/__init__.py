"""The extraction eval set (INT-083) — the package the repo map names.

Two modules and a corpus of committed JSON:

* :mod:`llm_evals.corpus` — the case and schema loaders, with a closed key set
  so a corpus file that grew a prompt or a completion field fails to load
  rather than being quietly ignored.
* :mod:`llm_evals.runner` — replays each case through the real extraction
  boundary and emits the structural rows INT-175's recorded-experiment gate
  judges.
* :mod:`llm_evals.adversarial` — the RT-09…RT-14 harness (INT-102): a PDF
  whose payload is in the text layer and not on the page, and the shapes an
  identifier takes once it has been said out loud.
* :mod:`llm_evals.judge` — the nightly LLM-judge job for those scenarios,
  which refuses to run without a budget and a judge client.

Nothing here calls a model. ``make eval-live`` is the only live path in this
repository and it is not reachable from this package.
"""

from __future__ import annotations

from llm_evals.corpus import CorpusError, ExtractionCase, load_cases
from llm_evals.judge import (
    BudgetRefused,
    JudgeBudget,
    JudgeUnavailable,
    NightlyJudgeJob,
    judge_budget_from_env,
)
from llm_evals.runner import (
    CollectingSpanSink,
    recorded_gateway_for,
    run_case,
    run_corpus,
    run_corpus_rows,
)

__all__ = [
    "BudgetRefused",
    "CollectingSpanSink",
    "CorpusError",
    "ExtractionCase",
    "JudgeBudget",
    "JudgeUnavailable",
    "NightlyJudgeJob",
    "judge_budget_from_env",
    "load_cases",
    "recorded_gateway_for",
    "run_case",
    "run_corpus",
    "run_corpus_rows",
]
