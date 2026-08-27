# ADR-005 · No raw audio retention — extended to core dumps, swap and crash reports

Status: Accepted

## Context

Raw patient audio is the highest-sensitivity artefact in the system, and 'we do not store it' is false comfort while a 30–60 s PCM buffer can leak through a core dump, a swap page or a crash reporter (the product ships GlitchTip).

## Decision

Raw audio is never written to disk, DB, object store or logs, and is never reachable through a crash artefact: RLIMIT_CORE=0, mlocked buffers ≤ 60 s, explicit zeroization on every trigger — each an assertion, not a convention.

## Consequences

audio_no_write/no_core/no_swap/zeroization/no_telemetry guards in make safety, including a real-crash test (a fake filesystem cannot see a core dump). Replay works from the event log, never audio (lane signals are recorded inputs).
