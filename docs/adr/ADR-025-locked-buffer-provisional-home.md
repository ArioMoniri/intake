# ADR-025 · Locked-buffer and process-hardening primitives live provisionally in `voice-clips`

Status: Accepted (provisional placement; the destination is named below)

## Context

ADR-005 decided that raw audio is never reachable through a core dump, a swap page or a crash report, and files/10 §3 specifies the mechanism — a page-aligned `mmap(MAP_ANONYMOUS|MAP_PRIVATE)` region plus `mlock`, `RLIMIT_CORE=(0,0)` and `prctl(PR_SET_DUMPABLE, 0)`. INT-094 found that none of it existed: `services/voice-runtime/.../observers/buffer.py` holds plain `bytearray` frames, so invariant 3's *mlocked* clause was unimplemented rather than merely untested, and INT-278 could not "test mlock" without first building the primitive. INT-278's change owns `packages/voice-clips/**` and no other package, so the primitive had to be written there or not at all, and "not at all" leaves the four rows of files/10 §9.1 (16, 17, 19, 28) unproved for another cycle.

## Decision

`voice_clips.locked_buffer` and `voice_clips.process_hardening` are the repository's locked-region and process-hardening primitives, and they are **provisionally** housed in `packages/voice-clips`: they import nothing from `voice_clips`, are re-exported by nothing, add no dependency to that package, hold no speech of any kind, and are therefore movable by a rename. Their destination is `packages/intake_platform` (process hardening, beside `intake_platform.errors`) and `services/voice-runtime/src/intake_voice_runtime/observers/` (the frame allocation), and the move plus the wiring — `harden_process()` at worker start, `Frame.samples` allocated from a `LockedBuffer` — is a follow-up issue, not an optional tidy-up: until it lands, the mechanism is proved and the product is not hardened.

## Consequences

`tests/voice/test_audio_memory_hygiene.py` proves the mechanism with a control for each property and discharges the four `not_covered_here` rows INT-094 recorded, so files/10 §9.1 invariants 16, 17, 19 and 28 now have tests under their own names. What stays open is recorded in docs/evidence/INT-278.md and in that suite's own docstring rather than implied: the runtime's lane frames are still ordinary `bytearray`s; `infra/` declares no `cap_drop`, `no-new-privileges` or non-root user for any service, so invariant 28's container half is unasserted; and `kernel.yama.ptrace_scope` is a node setting no test can set. The placement here is a debt with a named payer — a reviewer who finds these modules still in `voice-clips` after the follow-up should treat that as the defect this ADR predicted.
