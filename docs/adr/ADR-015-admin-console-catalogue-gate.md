# ADR-015 · Admin console, metrics catalogue as code, self-hosting matrix as release gate

Status: Accepted

## Context

Hospital CIOs audit operability, not promises; and a metric that exists only in code is a metric nobody governs. The self-hosting posture is the artefact they read first.

## Decision

Every metric lives in packages/clinical-schemas/metrics_catalog.yaml (emit-without-catalogue fails CI); every model/service on the PHI path declares self_hostable with a 60 s probe in a registry rendered in apps/admin-web; the release gate blocks when an enabled PHI-path component lacks a healthy self-hosted fallback. Registry and gate are built in P0; the gate is enforced from P2.

## Consequences

Invariant 13/15; INT-022/INT-025/INT-183. The console is mock-data in P0 and real-telemetry from INT-181 on.
