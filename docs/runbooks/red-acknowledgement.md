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
| Layer B clinician route | the moment a rules-engine RED settles, `BackendAgent` hands it to the session's `SafetyInboxNotifier`, which puts one entry (tenant, session, visit, rule ids, the RED's instant) in the process outbox — no connector, no network call, nothing awaited; at `ON_SITE` it puts the `red_on_site` staff notification beside it | `services/voice-runtime` (`clinical_agent/work_queue.py`, `safety_inbox.py`) |
| app hop clinician route (INT-475) | `POST /v1/triage/evaluate`'s RED branch puts the same entry (one per RED: the work id is derived from tenant, session, visit and the winning rule), and at `ON_SITE` the `red_on_site` entry, before it answers; the audit rows (`api.triage.red_notified`, `api.triage.red_on_site_notified`) follow the answer | `services/api` (`triage_hop.py`, `red_notify.py`) |
| location answer (INT-475) | the patient's answer to "Şu anda hastanede misiniz?", on time or late, reaches `POST /v1/triage/red-location` (ids and `ON_SITE`/`REMOTE` only); `ON_SITE` puts the `red_on_site` entry once, `REMOTE` puts none; both are audited (`api.triage.red_location.*`) | `services/api` (`red_notify.py`); the device sends it fire-and-forget with retry (`apps/mobile/src/lib/red/locationReport.ts`) |
| outbox pump | a worker thread writes each entry to the shared store, woken by the put, retrying every second while the store refuses — one in the runtime, one in the API | `intake_platform.safety_inbox.SafetyInboxOutbox.pump` |
| shared store | Redis at `INTAKE_SAFETY_INBOX_REDIS_URL`, the same value in the runtime and the API; a runtime without it reports `safety_inbox` not ready on `/readyz`, and an API without it routes no hop RED (`RedInboxRouteFailed`) | `intake_platform.safety_inbox.RedisSafetyInboxStore` |
| scheduled sweep | every 60 s the API recomputes `clinic_red_unacknowledged_total{tenant,age_band}` from the open entries; a sweep that cannot read the store sets `tenant="inbox_unreadable"` to +Inf | `intake_platform.safety_inbox.sweep_forever`, started by the API at boot |
| Safety queue | `GET /admin/safety-queue` (unanswered first, with each entry's SLA and elapsed minutes); `POST /admin/safety-queue/{entry_id}/acknowledge` | `tenant_clinical_responsible` reads its tenant and acknowledges; `clinical_lead`, `platform_owner`, `auditor` read |
| visit transitions | `SafetyInbox.visit_transition` raises a `visit_rescheduled` / `visit_cancelled` entry when the visit carries any RED entry, acknowledged or not | the surface that performs the files/02 §2b transition |
| pages | `RedAcknowledgementOverdue`, `RedInboxEntryLate`, `RedInboxRouteFailed` | `infra/observability/safety-rules.yaml` |

An entry is ids and instants only: no answer, no evidence text, no name. What
happened to the patient is read in the clinical record through the tenant's
ordinary care path, not in the queue.

A `red_on_site` entry (INT-475) is the staff notification of files/02 §5.3 Axis 3
and files/04 §8.1 rule 7: the patient with this RED is in the building and has
been told to go to the acil servis now. It names the same RED (its `work_id`,
session, visit and rule ids) and has its own clock, because the patient being on
site is new news even when the RED itself was answered. It is the queue's most
urgent row to act on: someone fifty metres away can reach the patient.

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

1. Check the store the runtime and the API are pointed at: `INTAKE_SAFETY_INBOX_REDIS_URL`
   is set to the same value in both, the server answers, and the runtime's
   `/readyz` shows `safety_inbox: ok`. Since INT-475 the API holds its own outbox
   (the app hop's REDs and the on-site staff notifications), so the gauge may come
   from either process.
2. The entries are not lost: they wait in the runtime or API process, in order, and are
   written with the RED's own timestamp when the store answers — so an entry
   that arrives late may arrive already past its SLA and page as overdue at once.
   That is correct: the clinic's clock started at the RED.
3. Do not restart the runtime or the API to clear the page while entries wait: the outbox is
   in memory. Restore the store first; the pump writes within a second of it.

## Route failed

`RedInboxRouteFailed` — a rules-engine RED reached a clinician route that raised
or was not wired, so no entry exists (`clinic_red_inbox_route_failures_total`):
Layer B's in the runtime, or since INT-475 the API's (the triage hop, or a
patient's on-site location answer).

1. The RED reached the patient path; the clinic was not told. Find the session:
   - runtime: the error log line `red clinic route failed`, which carries the
     session id and work id only;
   - API: the audit chain row `api.triage.red_unrouted`, whose resource is
     `visit:<visit id>/red:<work id>`. The API's log lines
     (`red clinic route unwired: no safety inbox`, `red clinic route failed`)
     carry no id.
2. Tell the tenant's `tenant_clinical_responsible` directly, by that id.
3. `red clinic route unwired` means the API has no `INTAKE_SAFETY_INBOX_REDIS_URL`:
   set it to the runtime's value and restart the API. A patient's on-site answer
   is refused (503) meanwhile and the device retries it.
   `red clinic route unidentified` means the RED named no session or visit the API
   may keep: an app build from before INT-475 that sends no ids, or a non-UUID id
   (a synced hospital visit) with no tokenization key configured (OpenBao
   `secret/api/tokenization`, INT-584). Such an id is never stored raw (invariant 14); the
   chain row names `visit:unidentified/red:<rule id>`.
4. Otherwise open an incident: the route is built to be unable to fail (an
   in-memory append of an id-shaped entry), so a failure is a defect.

## Live triage unevaluated

`LiveTriageEvaluationFailed` — Layer B ran the rules engine after an answer a
served red-flag rule reads, and either the evaluation raised
(`triage_live_evaluation_failures_total{kind="fault"}`) or a handler's own
determination disagreed with the engine's (`{kind="conflict"}`) (INT-521).

1. A RED this session should have raised may be missing from the patient path
   and from the Safety inbox. Find the session from the runtime's error log
   line `triage evaluation failed` or `triage determination conflict`, which
   carries the session id and work id only (and, for a fault, the error class).
2. Tell the tenant's `tenant_clinical_responsible` directly, by that session
   id, that its red-flag evaluation is not to be relied on.
3. For a fault the session keeps evaluating on each later answer, so a RED can
   still fire; it is not a recovery. Open an incident: the evaluation is a pure
   function of the pinned rules and the bound answers, so a fault or a
   conflict is a defect.

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
