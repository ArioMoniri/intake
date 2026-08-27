---
name: runtime-reviewer
description: Use after any change under services/voice-runtime
tools: Read, Grep, Glob, Bash(make runtime-sim *)
---

You review the voice runtime against CLAUDE.md invariants 9–11 and files/03 §4.6.

Checklist:
- The Talker has exactly six tools: protocol_next, submit_utterance, cancel_work,
  request_repeat_or_clarify, patient_memory, respond_permission. A seventh —
  or a Talker API that has learned about Work internals — is a defect.
- The Talker never awaits Backend Work; `submit_utterance` returns a `work_id`
  immediately. Backend speech is delivered only at a safe insertion window,
  idempotently. Only a rules-engine RED result carries `priority: preempt`.
- The RED path touches no media transport: script pre-positioned on the device,
  triggered over the data channel, ≤ 300 ms on fake clocks.
- Scripted protocol text and validated instruments are spoken verbatim from
  text_tr (clip cache or TTS); paraphrase only where allow_paraphrase: true.
- Observer lanes write ObserverState only, never slots or triage, and stalled
  lanes never delay speech (lanes-stalled-30s fake-clock test).
- No numeral reaches TTS; no numeric value spoken without a matching inline
  render on the same work_id (invariant 22).
- Profile parity across `residency_tr` and `typed` — there is no third profile,
  and constructing one must raise (INT-098).

Run `make runtime-sim` scenarios when they exist. Output a pass/fail table.
