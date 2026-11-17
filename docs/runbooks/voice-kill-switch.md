# Runbook — voice kill switch, profile switch and canary (INT-182)

Alert: `admin.voice_control_changes_total` (any `applied` or `refused`
outcome), `voice_kill_switch_flips_total{outcome="not_armed"}` > 0, or
`voice_control_read_failures_total` > 0.

The Voice module (`/voice` in the console, `GET /admin/voice`) controls how a
tenant's patients are asked their questions: by voice (`residency_tr`) or on
the screen (`typed`). There are exactly two profiles (CLAUDE.md invariant 19);
anything else is refused before a request opens.

## Where the control lives

One record per tenant in Redis, under `intake:voice-control:v1:<tenant>`,
written only by `services/api/admin` and read by the voice runtime at **every
session start** and on a 1 s poll for live sessions. Both services must point
`INTAKE_VOICE_CONTROL_REDIS_URL` at the same Redis.

- A tenant with **no** record is `typed`. Voice is enabled per tenant by a
  profile switch, never by the absence of a row, so a Redis that lost its keys
  falls every tenant to the keyboard.
- A record the runtime cannot read starts the session `typed` and counts
  `voice_control_read_failures_total{phase="start"}`. On the poll, live
  sessions keep their last-known state and count `{phase="poll"}`.
- The kill switch is **not** an Unleash flag (files/08 §3, invariant 34).

## Pulling the kill switch (the safe direction — one key)

`admin.voice.kill_switch.engage`, tier 1. Any single `sre_oncall`,
`clinical_lead` or `platform_owner` may do it alone, with a reason class and a
real explanation (≥ 12 characters). There is no second approver: a second key
at 03:00 on the safe direction is an availability control on a safety control
(files/08 §0c F17).

- New sessions for that tenant start `typed` from the next session start. No
  deploy, no restart.
- Live voice sessions move to the keyboard within one poll (≤ 1 s, inside
  INT-100's 2 s typed-fallback budget), through the same `fall_back_to_typed`
  path the failover ladder uses. Every slot is kept; the clinician's note is
  marked `modality_degraded`.
- A live session with no screen bound cannot fall back and stays in voice
  rather than going silent; it is counted once as `not_armed`. Investigate the
  deployment: every production voice session should carry a screen.

## Releasing it, switching the default, setting a canary (two keys)

`admin.voice.kill_switch.release`, `admin.voice.profile.switch` and
`admin.voice.canary.set` are tier 2. A `platform_owner` or `clinical_lead`
requests; a **different human** — `platform_owner`, `clinical_lead` or
`qms_owner`, on a different account, WebAuthn credential and session, with a
fresh single-use assertion — approves within 15 minutes. Nothing changes at
request time.

- A self-approval is refused and meters
  `admin.four_eyes_self_approval_attempt_total` — treat it as an intrusion
  signal.
- An approval is refused (`voice_control_changed`) if the tenant's control
  moved after the request — for example the kill switch was pulled. Re-request
  against the current state.
- Canary weights are integer percentages 0..100, default 0. A canary of the
  default profile is refused. Routing is a hash of the session id, so a replay
  routes the same session the same way.

## Reading the module

- **Sessions** — starts by profile and reason (`default`, `canary`,
  `kill_switch`, `control_unreadable`).
- **Turn latency** — `voice.round_trip_ms` p50/p95 per profile. Unknown until
  an emitter lands; unknown is never shown as zero.
- **Speech errors** — `voice_speech_calls_total` failed ÷ dialled, per
  registry component (ASR and TTS).
- **Failovers / breakers** — INT-100's `vendor_failovers_total` and
  `vendor_breaker_state`.

Every tile fails closed to unknown on its own source. The console shows ids,
roles and counts only — never patient content (invariant 6).
