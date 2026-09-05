# Runbook — safety-flag governance (INT-188)

Alert: `admin.four_eyes_self_approval_attempt_total > 0` on a
`admin.flags.safety.enable` ceremony, or a `device_flag_gate_guard` flag-store
scan finding a safety key in the generic store.

This runbook covers the flag module's governance layer. It does **not** cover
the device-mode registration surface (that is `docs/runbooks/*` for INT-117 /
files/08 §0b F2); a `device_functions` change also runs the study-registry
checks documented there.

## What a "safety flag" is

The safety list is `intake_platform.flags.SAFETY_FLAG_DEFAULTS` — the single
source of truth shared by the read facade and the write governor:
`device_functions`, `s2s`, `learning_apply`, `satisfaction_prompts`,
`guardian_link`, `commercial_messaging`. Every one reads `False` and cannot be
defaulted open.

Two invariants bound these flags:

- **invariant 34** — no safety-list key exists in the generic (Unleash /
  in-memory) flag store. Unleash API tokens flip flags with no audit row and CI
  runners hold them, so a safety key there is a governance hole regardless of
  its value. A safety flag is decided only by the ceremony below.
- **invariant 12** — a flag governs rollout/exposure, never clinical semantics.
  A flag can never modify red-flag levels, instruments, consent texts, the
  Talker tool list, PolicyGuard or profile routing. Those surfaces are not
  nameable as flag keys.

## Enabling a safety flag (the dangerous direction — two keys)

`admin.flags.safety.enable` is tier 3. Enabling a safety-list capability opens
a four-eyes pending action and applies **only** after a second, distinct human
approves:

1. A requester (`platform_owner` or `clinical_lead`) opens the change with a
   mandatory closed-category reason and a real explanation.
2. A distinct approver from `{clinical_lead, qms_owner, compliance_officer}`,
   on a **different account, WebAuthn credential and session**, from a
   **different organisation**, presents a fresh single-use assertion.
3. Both identities and both assertions land in `admin_audit.v1` **before** the
   flag takes effect (write-ahead).

A self-approval, a shared credential, a shared session or a same-organisation
approver is refused and the flag stays in its safe state. A self-approval
attempt is metered — it is an intrusion signal, not hygiene.

## Disabling a safety flag (the safe direction — one key)

Turning a safety flag **off** takes a single eligible key
(`clinical_lead`, `sre_oncall` or `platform_owner`) with a change reason. There
is no second-approver step: a ceremony on the safe direction is an availability
control on a safety control (files/08 §0c F17). Use this in an incident to pull
a capability without waiting for a second approver at 03:00.

## If the flag-store scan finds a safety key in the generic store

Treat it as a control-plane incident: an Unleash write path or a seed has
placed a safety key where invariant 34 forbids it. Remove the key from the
generic store, rotate the Unleash token that could reach it, and confirm the
effective safety state from the gated store (`FlagGovernor.effective_safety`),
which is unaffected by the generic store.
