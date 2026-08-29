"""packages/protocols/triage — the deterministic triage engine (INT-080).

CLAUDE.md invariant 1 names this package: "Triage RED/YELLOW can only be
produced by ``packages/protocols/triage`` rules. LLM output may contain
``candidate_flags`` → max ``YELLOW_REVIEW``." Everything here is a pure
function of ``(rules, context, location)``; there is no LLM, no vendor
client and no network anywhere below this package (asserted transitively
by the import-boundary test).
"""

from __future__ import annotations

from protocols.triage.context import SlotAnswer, TriageContext, canonical_scalar, temporal_within
from protocols.triage.engine import (
    DraftRuleError,
    TriageEngineError,
    TriageEvaluation,
    evaluate_triage,
    rule_truth,
    when_truth,
    with_candidates,
)
from protocols.triage.expr import (
    Truth,
    WhenGrammarError,
    parse_when,
    referenced_slots,
)

__all__ = [
    "DraftRuleError",
    "SlotAnswer",
    "TriageContext",
    "TriageEngineError",
    "TriageEvaluation",
    "Truth",
    "WhenGrammarError",
    "canonical_scalar",
    "evaluate_triage",
    "parse_when",
    "referenced_slots",
    "rule_truth",
    "temporal_within",
    "when_truth",
    "with_candidates",
]
