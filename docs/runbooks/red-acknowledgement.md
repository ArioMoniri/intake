# Runbook — RED acknowledgement: the clinic Safety inbox and its pages (INT-406)

> files/02 §8.2: *"Safety response time: RED → clinic inbox ≤ 60 s. RED → human
> acknowledgement within a tenant SLA, default 4 business hours, with a
> documented out-of-hours path — and both hold regardless of connector presence
> (§5.3)."*
> files/10 §9.1 invariant 49 `red_acknowledgement_sla_guard`: *"every RED
> produces a clinic inbox entry ≤ 60 s regardless of connector presence; the ack
> clock starts; unacknowledged past SLA pages; `02 §2b` visit-state transitions
> on a RED visit raise an entry"*.

## What runs where

| piece | what it does | where |
|---|---|---|
| Layer B clinician route | the moment a rules-engine RED settles, `BackendAgent` hands it to the session's `SafetyInboxNotifier`, which puts one entry (tenant, session, visit, rule ids, the RED's instant) in the process outbox — no connector, no network call, nothing awaited | `services/voice-runtime` (`clinical_agent/work_queue.py`, `safety_inbox.py`) |
| outbox pump | a worker thread writes each entry to the shared store, woken by the put, retrying every second while the store refuses | `intake_platform.safety_inbox.SafetyInboxOutbox.pump` |
| shared store | Redis at `INTAKE_SAFETY_INBOX_REDIS_URL`, the same value in the runtime and the API; a runtime without it reports `safety_inbox` not ready on `/readyz` | `intake_platform.safety_inbox.RedisSafetyInboxStore` |
| scheduled sweep | every 60 s the API recomputes `clinic_red_unacknowledged_total{tenant,age_band}` from the open entries; a sweep that cannot read the store sets `tenant="inbox_unreadable"` to +Inf | `intake_platform.safety_inbox.sweep_forever`, started by the API at boot |
| Safety queue | `GET /admin/safety-queue` (unanswered first, with each entry's SLA and elapsed minutes); `POST /admin/safety-queue/{entry_id}/acknowledge` | `tenant_clinical_responsible` reads its tenant and acknowledges; `clinical_lead`, `platform_owner`, `auditor` read |
| visit transitions | `SafetyInbox.visit_transition` raises a `visit_rescheduled` / `visit_cancelled` entry when the visit carries any RED entry, acknowledged or not | the surface that performs the files/02 §2b transition |
| pages | `RedAcknowledgementOverdue`, `RedInboxEntryLate`, `RedInboxRouteFailed` | `infra/observability/safety-rules.yaml` |

An entry is ids and instants only: no answer, no evidence text, no name. What
happened to the patient is read in the clinical record through the tenant's
ordinary care path, not in the queue.

## Overdue

`RedAcknowledgementOverdue` — a Safety inbox entry of tenant `{{ tenant }}` has
been open longer than the tenant's acknowledgement SLA.

1. Tell the tenant's `tenant_clinical_responsible` through the tenant's
   out-of-hours path (see [Owner values](#owner-values)); the page carries the
   tenant id, never a patient.
2. They open `/admin/safety-queue`, read the entry (kind, rule ids, elapsed
   minutes) and act on the patient through their clinical process.
3. They acknowledge it: `POST /admin/safety-queue/{entry_id}/acknowledge` with no
   body. The route is tier 1 (one key, `admin.safety_queue.acknowledge`), audited
   write-ahead on the chain as `safety_inbox.acknowledge` naming the entry, and
   the gauge drops on the next sweep. A second acknowledgement is refused (409).
4. `tenant="inbox_unreadable"` means the sweep could not read the store: treat
   every tenant as having an unanswered RED until the store answers — see
   [Inbox entry late](#inbox-entry-late) for the store checks — then confirm the
   next sweep clears it.

Acknowledging says a human saw the RED. It does not resolve it: a later
reschedule or cancel of that visit still raises a new entry.

## Inbox entry late

`RedInboxEntryLate` — a RED recorded on the RED path has waited more than 60 s
for the shared store (`clinic_red_inbox_pending_age_s`).

1. Check the store the runtime is pointed at: `INTAKE_SAFETY_INBOX_REDIS_URL` is
   set, the server answers, and the runtime's `/readyz` shows `safety_inbox: ok`.
2. The entries are not lost: they wait in the runtime process, in order, and are
   written with the RED's own timestamp when the store answers — so an entry
   that arrives late may arrive already past its SLA and page as overdue at once.
   That is correct: the clinic's clock started at the RED.
3. Do not restart the runtime to clear the page while entries wait: the outbox is
   in memory. Restore the store first; the pump writes within a second of it.

## Route failed

`RedInboxRouteFailed` — Layer B handed a rules-engine RED to the clinician route
and the route raised, so no entry exists (`clinic_red_inbox_route_failures_total`).

1. The RED reached the patient path; the clinic was not told. Find the session
   from the runtime's error log line `red clinic route failed`, which carries
   the session id and work id only.
2. Tell the tenant's `tenant_clinical_responsible` directly, by that session id.
3. Open an incident: the route is built to be unable to fail (an in-memory
   append of an id-shaped entry), so a failure is a defect.

## Owner values

These are not set anywhere in the repository and must not be guessed:

- **The paging route.** Every rule above carries `severity: page`. No
  Alertmanager configuration or receiver ships here; a deployment routes
  `severity: page` to its on-call pager.
- **The tenant's business-hours calendar.** files/02 §8.2 says *"default 4
  business hours"* and no file states which hours those are. Until a tenant's
  calendar is recorded the SLA is counted as four wall-clock hours — never
  later than the business-hours reading, so the page can only come early.
- **The documented out-of-hours path.** files/02 §8.2 requires one per tenant;
  step 1 of [Overdue](#overdue) uses it.
- **A tenant SLA other than the default.** `AckSlaPolicy.per_tenant` ships empty.
- **Retention of answered entries.** Entries sit in the store with no expiry;
  how long an answered entry is kept, and how a patient erasure reaches it, is
  a files/06 §3 question for the data owner.
