"""The latency harness `make runtime-sim` drives (INT-094).

files/03 §7 places the *"latency harness with fake clocks (asserts §4.6
invariants without vendors)"* in ``packages/llm-evals`` alongside the patient
simulator. That package does not exist and its other two halves — the LLM
role-play simulator and the rubric runner — are not this issue's scope, so the
harness lands beside the runtime it measures and moves when the package is
built. What is here is only the part that is not a test double: the published
budget table, the scenario catalogue and the report. The doubles the scenarios
run against stay in ``tests/voice`` (CLAUDE.md invariant 17).
"""

from __future__ import annotations

from intake_voice_runtime.simulator.budgets import (
    DISPLACED_FLOOR,
    IN_COUNTRY_FLOOR,
    MID_LTE_DYNAMIC_P95_ITEMISED_MS,
    RESIDENCY_TR_P95_BAND_MS,
    VENDOR_HOP_SAVING_P50_MS,
    VENDOR_HOP_SAVING_P95_MS,
    BudgetNotPublished,
    NetworkProfile,
    PublishedBudget,
    StructuralFloor,
    TurnClass,
    displaced_baseline_dynamic,
    published_budget,
)
from intake_voice_runtime.simulator.report import (
    ParityTrace,
    ScenarioReport,
    TurnRecord,
    render_report,
)
from intake_voice_runtime.simulator.scenarios import (
    SCENARIOS,
    RuntimeScenario,
    ScenarioNotRunnable,
    runnable_scenarios,
)

__all__ = [
    "DISPLACED_FLOOR",
    "IN_COUNTRY_FLOOR",
    "MID_LTE_DYNAMIC_P95_ITEMISED_MS",
    "RESIDENCY_TR_P95_BAND_MS",
    "SCENARIOS",
    "VENDOR_HOP_SAVING_P50_MS",
    "VENDOR_HOP_SAVING_P95_MS",
    "BudgetNotPublished",
    "NetworkProfile",
    "ParityTrace",
    "PublishedBudget",
    "RuntimeScenario",
    "ScenarioNotRunnable",
    "ScenarioReport",
    "StructuralFloor",
    "TurnClass",
    "TurnRecord",
    "displaced_baseline_dynamic",
    "published_budget",
    "render_report",
    "runnable_scenarios",
]
