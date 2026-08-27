# ADR-016 · Self-hosted observability/eval stack

Status: Accepted

## Context

Telemetry and eval traces route through patient content; a SaaS observability vendor would be a PHI processor and an Art. 9 transfer — the exact thing the architecture removes.

## Decision

OTel everywhere with a PII-redaction processor → Prometheus/Loki/Tempo/Grafana (or SigNoz); Langfuse self-hosted for LLM traces and annotation queues; Unleash/OpenFeature for flags; Keycloak for identity; GitHub Actions self-hosted runners in the TR DC; Argo CD for CD.

## Consequences

No telemetry leaves our infrastructure; Langfuse spans are one of the four managed read paths into patient content and route through break-glass (HB-L6). Cost: the obs+security tiers alone need 22 GB RAM (HB-I2).
