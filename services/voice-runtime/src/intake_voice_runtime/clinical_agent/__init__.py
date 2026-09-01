"""Layer B, the Clinical Backend Agent: the deterministic IntakeEngine FSM.

files/03 §4 puts the engine in ``clinical_agent/`` behind the per-session
FIFO Work queue; INT-081 delivers the FSM itself — step kinds, ask-ahead /
reconcile-behind, delta mode from ``PatientOverlay``, and computed
``must_ask`` coverage. There is no LLM inside and no seam for one: the
package's only inputs are a resolved protocol, the session clock and the
patient's confirmed facts.

INT-092 adds the queue the engine sits behind: :mod:`work_queue` holds the
per-session FIFO, the state/background lane split of files/12 §7.4, and the
double guard that serialises every write to the engine.
"""

from __future__ import annotations

from intake_voice_runtime.clinical_agent.coverage import (
    COVERED_STATES,
    MustAskCoverage,
    must_ask_coverage,
)
from intake_voice_runtime.clinical_agent.delta import (
    DeltaDecision,
    DeltaMode,
    DeltaPrefill,
    decide_delta,
)
from intake_voice_runtime.clinical_agent.fsm import (
    MAX_CLARIFICATION_ATTEMPTS,
    EngineError,
    IntakeEngine,
)
from intake_voice_runtime.clinical_agent.plan import (
    EngineStep,
    IntakePlan,
    PlanError,
    StepPriority,
    build_plan,
)
from intake_voice_runtime.clinical_agent.work_queue import (
    LANE_OF,
    BackendAgent,
    BackgroundEffect,
    BackgroundHandler,
    EffectClass,
    QueueSealed,
    ReadOnlyContext,
    StateContext,
    StateEffect,
    StateHandler,
    UnregisteredWorkType,
    WorkLane,
    WorkRecord,
)

__all__ = [
    "COVERED_STATES",
    "LANE_OF",
    "MAX_CLARIFICATION_ATTEMPTS",
    "BackendAgent",
    "BackgroundEffect",
    "BackgroundHandler",
    "DeltaDecision",
    "DeltaMode",
    "DeltaPrefill",
    "EffectClass",
    "EngineError",
    "EngineStep",
    "IntakeEngine",
    "IntakePlan",
    "MustAskCoverage",
    "PlanError",
    "QueueSealed",
    "ReadOnlyContext",
    "StateContext",
    "StateEffect",
    "StateHandler",
    "StepPriority",
    "UnregisteredWorkType",
    "WorkLane",
    "WorkRecord",
    "build_plan",
    "decide_delta",
    "must_ask_coverage",
]
