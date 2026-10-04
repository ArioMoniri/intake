# INTAKE — documentation index

Read order for any session: [files/00_STATE.md](../files/00_STATE.md) (the
authority — where any file disagrees, 00 wins), then
[files/HUMAN_BLOCKERS.md](../files/HUMAN_BLOCKERS.md), then the blueprint file
for the task in hand. For the model stack, `files/03 §4.9.1` is canonical.

## Governing documents

- [CLAUDE.md](../CLAUDE.md) — the engineering constitution (invariants 1–22)
- [LOOP.md](../LOOP.md) — the autonomous iteration protocol · [PROMPT.md](../PROMPT.md) · [loop.sh](../loop.sh)
- [GOALS.md](GOALS.md) · [DoD.md](DoD.md) · [TDD.md](TDD.md)
- [PROGRESS.md](PROGRESS.md) — one entry per iteration
- Backlog: [issues.yaml](backlog/issues.yaml) · [epics.yaml](backlog/epics.yaml) · [blockers.md](backlog/blockers.md)
- Evidence: [docs/evidence/](evidence/) — red/green runs per issue
- Runbooks: [model-server-aws.md](runbooks/model-server-aws.md) · [staging-observability.md](runbooks/staging-observability.md) — the staging host's telemetry tier and staff Grafana (INT-481)
- Voice: [on-prem-tts-wiring.md](voice/on-prem-tts-wiring.md) — the delivery profiles on the self-hosted `residency_tr` TTS (INT-415)

## Blueprint (files/ — the source of record, verbatim)

- [00_STATE.md](../files/00_STATE.md) — decisions, verified facts, gotchas
- [HUMAN_BLOCKERS.md](../files/HUMAN_BLOCKERS.md) — what waits on a named human
- [01_MARKET_AND_STRATEGY.md](../files/01_MARKET_AND_STRATEGY.md)
- [02_PRODUCT_SPEC.md](../files/02_PRODUCT_SPEC.md)
- [03_ARCHITECTURE.md](../files/03_ARCHITECTURE.md) — §4.9.1 is the model-stack authority
- [04_CLINICAL_PROTOCOLS.md](../files/04_CLINICAL_PROTOCOLS.md)
- [05_ROADMAP.md](../files/05_ROADMAP.md) — gate-driven phases
- [06_COMPLIANCE_TR.md](../files/06_COMPLIANCE_TR.md)
- [07_CLAUDE_CODE_MASTER_PROMPT.md](../files/07_CLAUDE_CODE_MASTER_PROMPT.md) — the cold-start prompt
- [08_ADMIN_CONSOLE_AND_OBSERVABILITY.md](../files/08_ADMIN_CONSOLE_AND_OBSERVABILITY.md)
- [09_SPECIALTY_COVERAGE_AND_LEARNING.md](../files/09_SPECIALTY_COVERAGE_AND_LEARNING.md)
- [10_SECURITY_AND_TECHNICAL_MONITORING.md](../files/10_SECURITY_AND_TECHNICAL_MONITORING.md) — §9.1 invariant catalogue
- [11_ISSUE_BACKLOG.md](../files/11_ISSUE_BACKLOG.md) — human-readable backlog rendering
- [12_DSL_V2_AND_RUNTIME_SPEC.md](../files/12_DSL_V2_AND_RUNTIME_SPEC.md)
- [13_QUESTION_FLOW.md](../files/13_QUESTION_FLOW.md)
- [protocols/base.life_threat.yaml](../files/protocols/base.life_threat.yaml) — the universal rule set (unsigned; D17)

## Architecture Decision Records

- [ADR-000 Template](adr/ADR-000-template.md)
- [ADR-001 Expo + LiveKit for realtime voice](adr/ADR-001-expo-livekit.md)
- [ADR-002 FHIR R4 canonical; openEHR → P3 export](adr/ADR-002-fhir-canonical-openehr-export.md) *(amended; D8)*
- [ADR-003 Protocol DSL with monotonic red flags](adr/ADR-003-protocol-dsl-monotonic.md)
- [ADR-004 Deterministic triage, LLM as extractor](adr/ADR-004-deterministic-triage-llm-extracts.md)
- [ADR-005 No raw audio retention](adr/ADR-005-no-raw-audio.md)
- [ADR-006 Provider-agnostic speech/LLM gateways](adr/ADR-006-gateways.md)
- [ADR-007 TR residency split: media P1 / models P3](adr/ADR-007-residency-split.md) *(amended; D11)*
- [ADR-008 Doctor Link as universal connector](adr/ADR-008-doctor-link.md)
- [ADR-009 Two-layer voice runtime](adr/ADR-009-two-layer-voice-runtime.md)
- [ADR-010 One production profile + typed](adr/ADR-010-one-profile-plus-typed.md) *(amended; 00 §0b)*
- [ADR-011 Clip cache and ask-ahead/reconcile-behind](adr/ADR-011-clip-cache-ask-ahead.md)
- [ADR-012 Observer lanes](adr/ADR-012-observer-lanes.md)
- [ADR-013 Taxonomy, cluster packs, maturity](adr/ADR-013-taxonomy-clusters-maturity.md)
- [ADR-014 Two learning loops](adr/ADR-014-two-learning-loops.md)
- [ADR-015 Admin console + catalogue + self-hosting gate](adr/ADR-015-admin-console-catalogue-gate.md)
- [ADR-016 Self-hosted observability/eval stack](adr/ADR-016-self-hosted-observability.md)
- [ADR-017 Security architecture baseline](adr/ADR-017-security-baseline.md)
- [ADR-018 Technical-monitoring baseline](adr/ADR-018-monitoring-baseline.md)
- [ADR-019 Issue→PR delivery with gates](adr/ADR-019-issue-pr-delivery.md)
- [ADR-020 Device boundary; Class IIb](adr/ADR-020-device-boundary.md) *(amended)*
- [ADR-021 All models self-hosted, licence from the raw blob](adr/ADR-021-all-models-self-hosted.md)
- [ADR-022 No accuracy claims](adr/ADR-022-no-accuracy-claims.md)
- [ADR-023 RED three axes](adr/ADR-023-red-three-axes.md)
- [ADR-024 life_threat schema reconciliation](adr/ADR-024-life-threat-schema-reconciliation.md)
- [ADR-025 One egress allow-list, two enforcers, a purpose on every call](adr/ADR-025-egress-one-list-two-enforcers.md)
- [ADR-026 Connector destinations: a second list, one engine](adr/ADR-026-connector-destinations-second-list-one-engine.md)
- [ADR-027 SMART backend services: a second auth mode, a second host](adr/ADR-027-smart-second-auth-mode-second-host.md)
- [ADR-029 Embeddable white-label handshake](adr/ADR-029-embeddable-white-label-handshake.md)
- [ADR-040 A staff Grafana over Prometheus only, on the synthetic staging host](adr/ADR-040-staff-grafana-over-prometheus-only.md)
