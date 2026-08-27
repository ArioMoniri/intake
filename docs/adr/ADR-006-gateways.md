# ADR-006 · Provider-agnostic speech/LLM gateways

Status: Accepted

## Context

Model choice churns (00 §1's displaced-pins table is the proof), and every model swap that touches call sites is a regression risk across the safety surface.

## Decision

All STT/TTS/LLM access goes through SpeechGateway/LLMGateway adapter interfaces with recorded-fixture contract tests. A model or profile swap is a config change proven by contract tests and profile-parity simulator runs (E3). The anthropic|openai|google adapters exist as the mock/dev path only and are blocked on the PHI path by the egress allow-list.

## Consequences

CI never calls a vendor; adapters close only on live-smoke/gpu evidence; the canonical pin for every adapter is 03 §4.9.1 — no other file pins a model.
