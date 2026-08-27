# ADR-007 · TR residency split into residency_tr_media (P1) and residency_tr_models (P3)

Status: Accepted (amended — 00 §3 D11)

## Context

residency_tr was one item with two risk profiles, and the cheap half was hostage to the expensive half. Media residency (SFU + TURN + API + Postgres in İstanbul) is measured as a latency WIN (−39 ms p50 / −47 ms p95) and needs no GPU; model residency needs in-country GPUs that no hyperscaler offers today.

## Decision

Split: residency_tr_media ships in P1. residency_tr_models ships in P3, gated on a signed GPU capacity contract naming provider and SKUs — never on a date, and no availability date is published before that contract exists (HB-I5).

## Consequences

The largest transport lever lands early; the KVKK Art. 9 posture strengthens; the honest caveat travels with it (physical ≠ legal residency — counsel question, HB-L11). Heavy dev/model work meanwhile runs on the team AWS box, dev/synthetic data only (docs/runbooks/model-server-aws.md).
