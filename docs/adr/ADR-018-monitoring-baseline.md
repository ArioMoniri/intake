# ADR-018 · Technical-monitoring baseline

Status: Accepted

## Context

A service that cannot say whether it is healthy is a service whose failures are discovered by patients. The monitoring contract must be structural, not aspirational.

## Decision

Every service exposes /healthz /readyz /metrics /version via packages/intake_platform/health, emits OTel through the shared setup, declares SLOs with error budgets and burn-rate alerts (14.4x/1h, 6x/6h page; 1x/3d ticket), has a synthetic probe every 60 s, and chaos/load runs gate releases.

## Consequences

Invariant 15; a new service without the contract fails make check (INT-010's health_contract test enumerates services). Runbook per alert; MTTR < 4 h target (E7).
