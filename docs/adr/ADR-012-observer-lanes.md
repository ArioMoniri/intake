# ADR-012 · Observer lanes: parallel, read-only, off the critical path

Status: Accepted

## Context

Affect, acoustic, linguistic, asr_quality and engagement signals have clinical and product value, but any lane that can touch the conversation is a safety surface, and the acoustic lane is an investigational device function (D4). An earlier proposal to cut the lanes was withdrawn (D1) — the cost argument was $2.40 per pilot.

## Decision

The five lanes run in parallel to the conversation, write only ObserverState (never slots or triage — type-level), drop frames under backpressure rather than delaying speech, and merge at section boundaries as normal Work. acoustic is unreachable unless {study_id, protocol_version, ICF_version, approval_date} all assert and fails closed on protocol amendment; there is no shadow mode. Crisis lexicon hits bypass the lanes into deterministic triage regardless of wellbeing consent.

## Consequences

Invariants 11–12 and 23; the lanes-stalled-30s fake-clock test; must_ask_invariance proves read-only is true rather than true-on-a-technicality. Kintsugi DAM is dropped (D14) — the lane's model is a head we train ourselves (03 §4.9.1 row 19).
