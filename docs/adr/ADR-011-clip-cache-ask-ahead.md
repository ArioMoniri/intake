# ADR-011 · Protocol clip cache and ask-ahead/reconcile-behind

Status: Accepted

## Context

≈ 70 % of fast-mode turns are scripted protocol text. Synthesising them at runtime spends latency and money on sentences known at compile time, and runtime TTS is where Turkish numeral corruption enters (C6).

## Decision

Scripted text is pre-synthesised at compile time per voice (clip_id = sha256(text_tr + voice_id)) after the compiler's Turkish normalisation has expanded every numeral, unit and drug name; the engine asks ahead and reconciles behind so the conversation never stalls on extraction.

## Consequences

0 ms TTS on scripted turns; the clip round-trip gate (synthesise → independent ASR → normalised diff, invariant 43) blocks the build on a mispronounced clip; voice identity holds because both tiers use the same weights and voice_id.
