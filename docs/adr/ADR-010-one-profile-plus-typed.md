# ADR-010 · One production voice profile, residency_tr, plus typed, under one contract

Status: Accepted (amended — v1.4 had three profiles including two cloud ones; 00 §0b)

## Context

The owner's constraint is that all models are self-hostable on our own servers. Every model cascade_fast and s2s_cloud named is cloud-only, and the S2S shape was independently unsafe: no clip cache, no verbatim scripted text, PolicyGuard degraded to after-the-fact retraction.

## Decision

Exactly two profiles exist: residency_tr (production voice) and typed (full-parity fallback and kill-switch target). cascade_fast and s2s_cloud do not exist; the profile registry is closed and constructing any other profile id raises (INT-098). A reference to a deleted profile or vendor anywhere outside files/ is a build failure (grep gate).

## Consequences

No Art. 9 transfer at all, no vendor DPA chain, the two-stream defect structurally impossible; the costs are recorded honestly in 00 §0b (biasing becomes a build; diarization replaced by track separation + AEC).
