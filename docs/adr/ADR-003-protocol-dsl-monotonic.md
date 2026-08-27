# ADR-003 · Protocol DSL with monotonic red flags

Status: Accepted

## Context

Clinical content must be authored by clinicians in a reviewable, diffable form, and safety rules must survive composition: a specialty pack or a patient overlay must never be able to weaken a base rule, because that is precisely the silent failure a reviewer cannot see.

## Decision

Protocols are a YAML DSL with extends: inheritance compiled to FHIR Questionnaire + Pydantic + TS types. Red-flag rules are monotonic across inheritance — children and overlays add or tighten, never remove or relax — and base.life_threat is a sibling rule set outside the chain that nothing may extend.

## Consequences

The compiler is the enforcement point (INT-040/041); overlay_monotonicity property tests and the golden suite with near-miss negatives (docs/TDD.md) are the evidence. Authoring stays clinician-shaped (E4).
