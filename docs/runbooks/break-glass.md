# Runbook — break-glass (`admin.break_glass_opened_total`, `sec.break_glass_total`)

**Owner:** `compliance_officer` · **Issue:** INT-180 · **Spec:** files/08 §2.5, §2.6, §5 ·
**Threat-model row:** `admin-console`

## What fires

| signal | condition | severity |
|---|---|---|
| `admin.break_glass_opened_total{actor,reason_class}` | > 3 per actor per 30 days, **or** any out-of-hours grant with no open P1 | page |
| `admin.break_glass_patient_log_lag_h` | > 24 | page |
| `admin.four_eyes_self_approval_attempt_total` | > 0 | page — **intrusion signal, not hygiene** |
| `admin.pending_action_expired_total` | trend only | ticket |

files/08 §2.5 is explicit that the rate limit is the intrusion detector, not a
hygiene control. Nobody attempts to approve their own action by accident twice.

## What break-glass is

One governed path to patient content, replacing four ungoverned ones (Langfuse
spans, Grafana Explore over Loki/Tempo, `replay(event_log)`, and the old
console view). The ceremony:

1. A closed-category reason plus ≥ 20 characters of free text.
2. A **distinct** human approver — different account, different WebAuthn
   credential, different session — presenting a fresh single-use assertion:
   the approver opens `/step-up?action_id={action_id}` on the console and
   presses **Onayla**, a new password-and-passkey login whose one-time grant
   is the only thing the approve route accepts (INT-563,
   docs/runbooks/four-eyes-step-up.md).
3. A `controller_instruction_ref`, because as a processor we may act only on
   documented controller instruction.
4. Scoped to one session id, TTL ≤ 60 minutes, single use.
5. The audit row is written **before** the read.

## Triage

1. **Read the approval brief** — `GET /admin/break-glass/{action_id}`. It
   carries the requester's identity block, the tier, the target session, the
   reason class, the full justification, the controller-instruction reference
   and the evidence. If the brief does not justify the access, it should not
   have been approved; treat it as an incident, not a process complaint.
2. **Check the approver against the requester.** The server enforces distinct
   account, credential and session. It cannot enforce *distinct human* — see
   the limit below — so an unusually reciprocal actor/approver pairing is a
   finding a person has to make.
3. **Check the patient's access log.** The grant must appear in the patient's
   own log within 24 h (`admin.break_glass_patient_log_lag_h`). A grant that
   does not is a KVKK m.11/m.13 failure, independent of whether the access
   itself was justified.
4. **Self-approval attempt:** treat as attempted privilege escalation. Suspend
   the actor's session, preserve the audit range, and escalate to the security
   owner.

## The limit this control does not cover

Four-eyes proves a second **account**, credential and session. Nothing in an
OIDC claim set proves a second **person**. Two accounts held by one human pass
every check the ceremony can make. Closing that needs identity proofing at
enrolment, or an approver pool the actor cannot enrol into — an operating
control, not another field. `tests/admin/test_four_eyes.py` asserts the
acceptance so the limit stays visible rather than being read as covered.

## Fail-closed states you may hit

| symptom | cause | correct response |
|---|---|---|
| every `/admin/*` route answers 503 `admin_console_unconfigured` | no OIDC claims verifier is wired | wire one; do not weaken the tier |
| every request answers 403 `source_ip_refused` | the console IP allow-list is empty, which is the shipping state (files/08 §2.3 names no range) | supply the deployment's ranges; never a guessed address |
| `422 tenant_deployment_unknown` | no controller/processor answer is recorded for that tenant | answer it per tenant; it decides the lawful basis |
| `422 no_lawful_basis` | the tenant is a **controller** deployment | **do not route around this.** files/08 §2.6 and HUMAN_BLOCKERS **HB-L6**: no staff-access purpose exists in files/06 §2, so invariant 4 has no scope to check |

## Related

- `docs/evidence/INT-180.md` — what was built and what was refused.
- HUMAN_BLOCKERS **HB-L6** (counsel: staff access, controller instruction, the
  24-hour notice window) and **HB-I12** (where the audit chain's head is
  published, outside the `platform_admin` blast radius).
