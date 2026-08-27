# ADR-013 · All-branch taxonomy, cluster packs and maturity model

Status: Accepted

## Context

Patients book into ≈ 79 MHRS branches and do not present according to their booking. Serving only hand-built specialty packs leaves most branches on bare base intake — or worse, unrouted.

## Decision

taxonomy/branches.yaml lists every MHRS-registered branch mapped to one of nine cluster packs; maturity runs L0 (agent-generated, never served) → L1 (branch physician review) → L2 (pilot-validated) → L3 (published). A branch without an L1 pack runs its reviewed cluster pack; every patient is evaluated against base.life_threat regardless of branch (G7).

## Consequences

protocols coverage prints the matrix and CI fails on an unrouted branch; resolving an L0 pack for a live session raises. The live MHRS list stays verify_live_list: true until the owner confirms it (HB-A11).
