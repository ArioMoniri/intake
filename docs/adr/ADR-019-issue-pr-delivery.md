# ADR-019 · Issue→PR delivery with zero-placeholder/evidence gates and human-approval labels

Status: Accepted

## Context

An autonomous loop optimises for green, and green is cheap to fake: stubs, skipped tests, silently reduced scope, invented clinical values. The delivery model has to make faking more expensive than doing.

## Decision

All work flows issue → branch → PR → squash merge, one issue at a time in backlog order, strict TDD with the red run recorded in an evidence file. no_placeholders forbids stubs outside tests/fixtures (sole exception: the literal unfilled-clinical-value form under packages/protocols); evidence_check refuses a PR without its red run; approval:human-* labels leave PRs open for the named human; awaiting-human satisfies dependencies for the non-gated part so 58 % of the backlog does not silently freeze.

## Consequences

INT-002 (gates) and INT-004 (machinery) implement this ADR; docs/DoD.md list B names what a machine may never self-certify.
