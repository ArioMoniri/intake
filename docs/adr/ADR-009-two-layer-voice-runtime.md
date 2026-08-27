# ADR-009 · Two-layer voice runtime: Realtime Talker + Clinical Backend Agent

Status: Accepted

## Context

A voice agent that waits on clinical processing produces dead air; one that lets clinical logic into the conversational loop produces an unauditable mixture. The two concerns have different latency budgets, different failure modes and different review regimes. Prior art for the shape: github.com/QwenAudio/qwen-audio-agent docs/architecture.md.

## Decision

Layer A (Realtime Talker) owns the duplex audio loop with exactly six tools (protocol_next, submit_utterance, cancel_work, request_repeat_or_clarify, patient_memory, respond_permission), speaks ≤ 2 sentences, plays pre-synthesised clips, and never awaits Backend Work — submit_utterance returns a work_id immediately. Layer B owns extraction, the IntakeEngine FSM, triage, records and notes behind a per-session FIFO with one Work in flight; results deliver only at a safe insertion window, and only a rules-engine RED carries preemption.

## Consequences

Invariants 9–11 and the six-tool introspection test; RED preemption ≤ 300 ms via the data channel with no media transport (D12). The async-function-calling vendor dependency evaporates — a work_id return is trivially non-blocking on an ordinary text LLM.
