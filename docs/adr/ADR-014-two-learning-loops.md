# ADR-014 · Two learning loops: per-patient deterministic; cross-patient proposal-only

Status: Accepted

## Context

The product must improve from use without ever becoming a system whose clinical behaviour changed silently. Those are two different kinds of learning with two different trust models.

## Decision

Loop 1 (PatientOverlay) is deterministic, learned only from patient- or clinician-confirmed facts, patient-visible and editable, and may only add or tighten red flags. Loop 2 (services/learning) emits proposals — PRs with evidence bundles — through clinician approval and 5/25/100 canary with auto-rollback; it can never change red-flag levels, instruments, consent texts, Talker tools, PolicyGuard or profile routing.

## Consequences

Invariant 12 and the proposal_scope CI test; overlay monotonicity property tests; learned_fact_provenance. Improvement is auditable because it ships as diffs.
