"""INT-100 — vendor failover: breakers, a registry-read order, a 2 s typed fallback.

Three modules, one rule each:

- :mod:`~intake_voice_runtime.resilience.breaker` — one circuit breaker per
  vendor component, shared across sessions, on an injected clock.
- :mod:`~intake_voice_runtime.resilience.order` — the failover order is the
  registry's ``fallback`` chain; on the PHI path it holds self-hosted lanes
  only, and a cloud row is refused rather than skipped (CLAUDE.md
  invariant 19).
- :mod:`~intake_voice_runtime.resilience.failover` — the lanes tried in that
  order under one 2 s budget, sticky per session; when none is left the Talker
  moves the session to ``typed`` inside the same turn.

sec_row: ``resilience`` (docs/security/threat-model.md; files/10 §5 LLM10).
"""

from __future__ import annotations

from intake_voice_runtime.resilience.breaker import (
    BreakerBoard,
    BreakerPolicy,
    BreakerState,
    CircuitBreaker,
    NowMs,
)
from intake_voice_runtime.resilience.failover import (
    TYPED_FALLBACK_DEADLINE_MS,
    TYPED_LANE,
    AttemptOutcome,
    BoundedSynthesizer,
    FailoverSynthesizer,
    LaneAttempt,
    LaneBindingMismatch,
    LaneFailover,
    SpeechLanesExhausted,
)
from intake_voice_runtime.resilience.order import (
    CloudFailoverRefused,
    FailoverChainBroken,
    FailoverOrder,
    FailoverRefused,
    LaneOffPhiPath,
    LaneRow,
    NoServingLane,
    ProfileHasNoSpeechLanes,
    SelfHostedNotFirst,
    build_failover_order,
    failover_order,
    load_lane_rows,
)

__all__ = [
    "TYPED_FALLBACK_DEADLINE_MS",
    "TYPED_LANE",
    "AttemptOutcome",
    "BoundedSynthesizer",
    "BreakerBoard",
    "BreakerPolicy",
    "BreakerState",
    "CircuitBreaker",
    "CloudFailoverRefused",
    "FailoverChainBroken",
    "FailoverOrder",
    "FailoverRefused",
    "FailoverSynthesizer",
    "LaneAttempt",
    "LaneBindingMismatch",
    "LaneFailover",
    "LaneOffPhiPath",
    "LaneRow",
    "NoServingLane",
    "NowMs",
    "ProfileHasNoSpeechLanes",
    "SelfHostedNotFirst",
    "SpeechLanesExhausted",
    "build_failover_order",
    "failover_order",
    "load_lane_rows",
]
