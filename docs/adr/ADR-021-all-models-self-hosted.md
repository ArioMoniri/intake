# ADR-021 · All models self-hosted, open weights, licence verified from the raw LICENSE blob

Status: Accepted

## Context

Owner constraint (00 §0b): all models run on our own servers. Separately, four laundered-licence cases proved that badges, model-card tags and READMEs are claims, not grants.

## Decision

Every model is open-weights, commercially usable (Apache-2.0/MIT/CC-BY), self-hosted, and verified from the raw LICENSE blob via the HF API — never a badge — with licence_verified_at recorded in the registry. 03 §4.9.1 is the single source of truth for the stack: a model not in that table is not pinned, and no other file restates a pin.

## Consequences

CI fails a release when a PHI-path row lacks licence_verified_at (E8); the licence-auditor agent runs on every model/dependency addition; the ruled-out table in 00 §1 is a regression gate — re-adding a ruled-out candidate is a defect.
