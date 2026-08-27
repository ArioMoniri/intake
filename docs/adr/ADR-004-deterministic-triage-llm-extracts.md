# ADR-004 · Deterministic triage, LLM as extractor

Status: Accepted

## Context

Triage decisions must be reproducible, auditable and clinically signed. An LLM cannot carry that burden: its output is not stable across versions, and a notified body cannot review a prompt the way it reviews a rule.

## Decision

Triage RED/YELLOW is produced only by the deterministic rules engine over typed slots. The LLM extracts structure from speech and may propose at most YELLOW_REVIEW candidates; it can never set or lower a level (type-level enforcement).

## Consequences

Invariant 1; replay determinism over the event log; the rules engine is the only thing that may preempt speech (invariant 9). The cost is honest: extraction quality bounds triage quality, which is why per-rule extraction sensitivity gates P1 exit (GOALS S4).
