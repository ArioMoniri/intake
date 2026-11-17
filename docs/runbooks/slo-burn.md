# SLO burn-rate alerts — every service

Every burn-rate alert in `infra/observability/prometheus-rules.yaml` links one of the
headings below, and `tests/observability/test_slo_generator.py` holds every link true.
The SLOs themselves live in `docs/slo/<service>.yaml`. The rules and the golden-signal
dashboards are generated from those files, so neither is edited by hand. The policy
numbers come from files/10 §6 and files/08 §5. Until the INT-021 close-out only the
api's six alerts existed; the other six SLO files had objectives and no alert.

## How to read a burn-rate page

A burn rate of `N` means the service is consuming its error budget `N` times faster
than the objective allows. Every SLO here uses a 28-day window, so the budgets are:

| service | SLO | objective | budget ratio | what the budget buys in 28 days |
|---|---|---|---|---|
| api | availability | 99.9 % | 0.001 | about 40 minutes of total outage |
| api | latency (≤ 500 ms) | 99 % | 0.01 | about 6.7 hours in which every request is slow |
| voice-runtime | availability | 99.5 % | 0.005 | about 3.4 hours of total outage |
| probes | availability | 99.5 % | 0.005 | about 3.4 hours of total outage |
| metrics | availability | 99.5 % | 0.005 | about 3.4 hours of total outage |
| learning | availability | 99.5 % | 0.005 | about 3.4 hours of total outage |
| langfuse | trace_emission | 99.9 % | 0.001 | one refused span field per 1,000 values that reach the boundary |
| siem | alert_scrub | 99.9 % | 0.001 | one refused detector alert per 1,000 that reach the boundary |

Every SLO has the same three lanes. An alert fires only when BOTH its long and its short
window burn above the threshold. The short window is what lets the alert reset quickly
once the cause is fixed.

| lane | threshold | windows | severity | what it means |
|---|---|---|---|---|
| fast | 14.4x | 1 h and 5 m | page | about 2 % of the 28-day budget is gone every hour |
| slow | 6x | 6 h and 30 m | page | about 5 % of the budget is gone every 6 hours |
| ticket | 1x | 3 d and 6 h | ticket | left alone, the window ends short of its objective |

Severity `page` interrupts a human now. Severity `ticket` files work for the next
business day.

**A readiness 503 counts as an error.** The HTTP SLIs count every 5xx the shared
middleware (`intake_platform.metrics.mount_http_metrics`) records, including `/readyz`
answering 503. For the api that is the right reading: an unready replica is one the
load balancer stops using. For voice-runtime, probes, metrics and learning, the four
health endpoints are almost all the HTTP traffic there is, so a replica that stays
unready burns the budget on its own. The `route` label is the route template, so the
errors panel tells the two cases apart. When every 5xx is `route="/readyz"`, the
process is alive and the `/readyz` body names the dependency it is waiting for.

## First five minutes

For every alert on this page:

1. Open the service's Grafana dashboard, `intake-<service>-slo`. Each one is generated
   into `infra/observability/grafana/dashboards/<service>-slo-dashboard.json`. The top
   rows show each SLO's burn and error ratio per window, and the rows below show the
   golden signals.
2. Check the deploy timeline. If a rollout matches the burn onset, roll back first and
   diagnose second. Canary plus automatic rollback is the default posture
   (files/10 §5).
3. Check `/readyz` on the service's replicas. A failing readiness check names the
   dependency in its response body.
4. Check the errors panel (`5xx by status`). It separates a total outage from a single
   failing route, and the `route` label names the endpoint without carrying any request
   data.

## api

`docs/slo/api.yaml`, dashboard `intake-api-slo`. The api carries the patient app, the
clinician web, the admin console's `/admin/*` routes and the embed routes.

### api availability fast burn

`ApiAvailabilityFastBurn` fires when the error ratio is above 14.4x the 0.001 budget over
1h AND 5m. At this rate 2 % of the 28-day budget disappears every hour, and an
unattended day ends the budget.

- Treat it as an outage until shown otherwise. Roll back the api's newest deploy even
  before the root cause is known.
- If `/readyz` blames a dependency, fail over or restart that dependency first. The api
  counts a 5xx for every request it cannot serve.
- If only one route burns, weigh disabling that route against the budget. The SLI counts
  every request equally.
- Escalate to the platform on-call lead if the 5m window has not dropped below the
  threshold within 30 minutes.

### api availability slow burn

`ApiAvailabilitySlowBurn` fires when the error ratio is above 6x the budget over 6h AND
30m, about 5 % of the monthly budget per 6 hours. The diagnosis path is the same as for
the fast burn, but there is room to prefer diagnosis over rollback. Look for a partial
failure: one pod, one dependency timeout, one tenant's traffic pattern. Silence it only
with an owner and an end time.

### api availability ticket burn

`ApiAvailabilityTicketBurn` fires when the error ratio is above the budget itself over
3d AND 6h. Nothing is on fire, but left alone the window ends short of its objective.
File the investigation, find the background error source (retries masking a flaky
dependency, a noisy client, a slow leak) and fix it inside the sprint. If the monthly
budget is exhausted, the deploy freeze in the error-budget policy below applies.

### api latency fast burn

`ApiLatencyFastBurn` fires when the share of requests slower than 500 ms is above 14.4x
the 0.01 budget over 1h AND 5m.

- Check the saturation panel first. CPU throttling, memory pressure or file-descriptor
  exhaustion slow every route at once.
- Compare p95 with p50. A p95-only rise points at a dependency timing out. Both moving
  together points at load or a slow deploy.
- Check traffic. A step in requests per second with flat capacity calls for scaling,
  not a code fix.
- Rolling back the newest deploy remains the cheapest hypothesis test.

### api latency slow burn

`ApiLatencySlowBurn` fires when the latency error ratio is above 6x the budget over 6h
AND 30m. It is usually a regression that shipped hours ago, or slow drift in a
dependency. Compare route-level p95 with the previous day, then bisect the deploys
inside the burn window.

### api latency ticket burn

`ApiLatencyTicketBurn` fires when the latency error ratio is above the budget over 3d
AND 6h. This is chronic slowness: a query missing an index, an N+1 on one route, payload
growth. File it with the route-level evidence from the dashboard and land the fix before
the window closes.

## voice-runtime

`docs/slo/voice-runtime.yaml`, dashboard `intake-voice-runtime-slo`. The SLO covers the
service's HTTP surface, which is the four health endpoints. The Talker's
conversation itself runs over LiveKit, not HTTP. The per-turn objectives (round trip,
RED preemption latency, delivery duplicates; files/08 §4 B and C) are not SLOs yet,
because their series carry no data until the worker runs a real session.

The four readiness checks are `clip_store`, `speech_synthesizer`, `room_token` and
`voice_controls`. Each one reports not-ready rather than falling back when its binding
is missing. A `typed` worker needs none of them.

### voice-runtime availability fast burn

`VoiceRuntimeAvailabilityFastBurn` fires when the error ratio is above 14.4x the 0.005
budget over 1h AND 5m.

- Read the `/readyz` body on each replica. `voice_controls` not-ready is the dangerous
  one, because a speech worker that cannot read the kill-switch store cannot honour the
  kill switch.
- If voice sessions are failing, move the affected tenants to `typed` with the kill
  switch (`docs/runbooks/voice-kill-switch.md`). That is the safe direction, so it takes
  one key (`sre_oncall`, `clinical_lead` or `platform_owner`, audited). Diagnose after.
- Check the dependencies the dashboard cannot see: the `voice-runtime` probe row (the
  LiveKit room join), the GPU hosts (`ops_gpu_host_up` on the ops console), and the TTS
  endpoint named by `INTAKE_TTS_ENDPOINT`.
- Roll back the newest voice-runtime deploy if its rollout matches the onset.

### voice-runtime availability slow burn

`VoiceRuntimeAvailabilitySlowBurn` fires when the error ratio is above 6x the budget
over 6h AND 30m. Look for one replica stuck unready, a flapping dependency (the
voice-controls Redis, the TTS endpoint), or a canary weight that routes a share of new
sessions to a bad build. Releasing the kill switch or moving a canary weight toward
voice is a two-person ceremony (INT-182). Do not do either to clear this page.

### voice-runtime availability ticket burn

`VoiceRuntimeAvailabilityTicketBurn` fires when the error ratio is above the budget over
3d AND 6h. Usually a replica has been left unready for days: a deployment that never set
a binding, or a readiness check that fails intermittently. File it with the `/readyz`
bodies and the `route` split from the errors panel.

## probes

`docs/slo/probes.yaml`, dashboard `intake-probes-slo`. The probes service serves the
health endpoints and the `/metrics` that carries the ops collector's series (GPU hosts,
CI runs, clip builds). Its 60-second runner writes the sweep the admin console and the
release gate read. Until the INT-021 close-out the service did not mount the request
middleware at all, so this SLO read a series nobody served.

### probes availability fast burn

`ProbesAvailabilityFastBurn` fires when the error ratio is above 14.4x the 0.005 budget
over 1h AND 5m. While it lasts, the console's probe matrix goes stale (a result older
than three sweeps reads as unknown), and the release gate cannot see a healthy fallback
it has no result for, so it blocks releases. The gate is failing closed, which is right,
but it also blocks the fix you might want to ship.

- `/readyz` has one check, `registry`. If it fails, the last change to
  `observability/registry.yaml` does not validate, and the schema error names the row.
  Revert that change.
- If `/metrics` is the failing route, look at the ops collector's sources
  (`ops_collector_source_up{source}`, shown on the admin console's ops page). A source
  that hangs should read as down, not break the scrape.
- Roll back the newest probes deploy if it matches the onset.

### probes availability slow burn

`ProbesAvailabilitySlowBurn` fires when the error ratio is above 6x the budget over 6h
AND 30m. Look for a partial failure: one replica serving a stale registry path
(`INTAKE_REGISTRY_PATH`), or a slow collector source that times out some scrapes. A
blocked release is the visible symptom. Treat the probes service as the cause before you
treat the gate as wrong.

### probes availability ticket burn

`ProbesAvailabilityTicketBurn` fires when the error ratio is above the budget over 3d
AND 6h. Chronic scrape or readiness failures make every sweep less trustworthy. File it
with the route split and the collector source states.

## metrics

`docs/slo/metrics.yaml`, dashboard `intake-metrics-slo`. The experience rollup service
(INT-240). A late rollup is a stale satisfaction dashboard, not a patient waiting,
which is why the objective is 99.5 % rather than the api's 99.9 %.

### metrics availability fast burn

`MetricsAvailabilityFastBurn` fires when the error ratio is above 14.4x the 0.005 budget
over 1h AND 5m.

- `/readyz` has one check, `events_db`. It fails when `INTAKE_METRICS_EVENTS_DB_URL` is
  unset or the events database refuses a `SELECT 1`. Fix the connection first. The
  rollups read the PHI-free events column and nothing else.
- Roll back the newest metrics deploy if it matches the onset.
- No patient-facing path depends on this service. Page the platform on-call lead only
  if the burn persists past an hour.

### metrics availability slow burn

`MetricsAvailabilitySlowBurn` fires when the error ratio is above 6x the budget over 6h
AND 30m. The usual cause is an events database that is intermittently unreachable, or
one replica with a stale connection setting. Compare the replicas' `/readyz` bodies.

### metrics availability ticket burn

`MetricsAvailabilityTicketBurn` fires when the error ratio is above the budget over 3d
AND 6h. File it. The experience module's figures for the affected days may be
incomplete, so note the window on the ticket so nobody reads those days' CSAT as a
trend.

## learning

`docs/slo/learning.yaml`, dashboard `intake-learning-slo`. Loop 2 runs weekly
(files/09 §4). A late run is a review queue that fills a day late, not a patient
waiting. This service can never modify red-flag levels, instruments, consent texts,
the Talker tool list, PolicyGuard or profile routing (invariant 12), so no page here
touches patient safety.

### learning availability fast burn

`LearningAvailabilityFastBurn` fires when the error ratio is above 14.4x the 0.005
budget over 1h AND 5m.

- Check the errors panel's `route` split first. `/readyz` has one check,
  `promotion_thresholds`, and it reports not-ready for as long as the effect-size floor
  files/09 §4 requires is unstated. That is an open question to the clinical lead
  (`intake_learning.architect.PromotionThresholds.from_blueprint`). If every 5xx is
  `route="/readyz"` with that body, the service is behaving as designed. Silence the
  alert with the owner's name and that question, and do not "fix" it by choosing a
  number.
- Any other 5xx: roll back the newest learning deploy.

### learning availability slow burn

`LearningAvailabilitySlowBurn` fires when the error ratio is above 6x the budget over 6h
AND 30m. Same split as the fast burn. If the errors are not readiness answers, look at
the analytics-view reader (the service holds `SELECT` on the de-identified views and
nothing else, files/09 §7).

### learning availability ticket burn

`LearningAvailabilityTicketBurn` fires when the error ratio is above the budget over 3d
AND 6h. File it. A week's proposals may arrive late, and that is all. Never lower a
promotion threshold to make a run finish.

## langfuse

`docs/slo/langfuse.yaml`, dashboard `intake-langfuse-slo`. The SLO is not Langfuse's
uptime, which is a probe (`langfuse`, `langfuse-clickhouse`). It is the emission
boundary in `intake_platform.observability.spans`: the share of span field values the
boundary refused because they were not identifiers. Langfuse stores what it receives
verbatim, so a refusal means a caller tried to put narrative into a transcript store
(files/08 §6, HB-L6).

### langfuse trace_emission fast burn

`LangfuseTraceEmissionFastBurn` fires when the refusal ratio is above 14.4x the 0.001
budget over 1h AND 5m. The boundary is working, since it refused, but a caller is
pushing values it must not.

- Split the refusals by field in Prometheus:
  `sum by (field) (rate(llm_trace_fields_refused_total[5m]))`. The field names the
  attribute a caller filled with something that is not an identifier. The dashboard's
  traffic row shows the totals only.
- Find the deploy that started emitting it and roll it back. A new span attribute that
  carries text is a code regression.
- Never widen the boundary's identifier rules to make the ratio fall. That would turn
  the page into a leak.

### langfuse trace_emission slow burn

`LangfuseTraceEmissionSlowBurn` fires when the refusal ratio is above 6x the budget
over 6h AND 30m. Usually one code path hands the boundary a free-text value only on
some inputs, for example an error message or an unusual document type. Find the field,
then the caller, and make the caller pass an id.

### langfuse trace_emission ticket burn

`LangfuseTraceEmissionTicketBurn` fires when the refusal ratio is above the budget over
3d AND 6h. File it with the field split. A steady trickle of refusals is still callers
trying to send the store something it must not hold.

## siem

`docs/slo/siem.yaml`, dashboard `intake-siem-slo`. The SLO is the scrub boundary in
`intake_platform.siem.normalise`: the share of detector alerts it refused because it
could not reduce them to identifiers, for example an unknown Falco priority, a Wazuh
level off the 0 to 15 scale, or a payload with no rule block. Each refusal is an alert
the Security module never shows, so a rising ratio is a detection gap. That is why both
burn lanes page. The manager, the indexer and Falco being up is a separate question,
answered by the probe rows `wazuh-manager`, `wazuh-indexer` and `falco`.

### siem alert_scrub fast burn

`SiemAlertScrubFastBurn` fires when the refusal ratio is above 14.4x the 0.001 budget
over 1h AND 5m.

- Split the refusals in Prometheus:
  `sum by (source, reason) (rate(siem_alerts_refused_total[5m]))`. A single reason from
  a single source almost always means that detector changed its output: a Wazuh or
  Falco upgrade, or a new rule set.
- Until the scrubber understands the new shape, the refused alerts are visible only in
  the detector's own console. Watch it there for the duration, because the monitor is
  still watching and we are not reading it.
- Teach `intake_platform.siem.normalise` the new shape as ids, or pin the detector back.
  Do not pass unknown fields through: the boundary exists because detector payloads can
  carry request content.

### siem alert_scrub slow burn

`SiemAlertScrubSlowBurn` fires when the refusal ratio is above 6x the budget over 6h
AND 30m. Usually one rarely firing rule emits a shape the scrubber does not know. Find
the rule id in the detector's console, then extend the scrubber for it.

### siem alert_scrub ticket burn

`SiemAlertScrubTicketBurn` fires when the refusal ratio is above the budget over 3d AND
6h. File it with the source and reason split. Detection coverage itself, meaning
whether the manager still receives events at all, needs a synthetic injected event and
is recorded as a gap in `docs/evidence/INT-205.md`. This alert does not measure it.

## Error-budget policy

When a 28-day budget is exhausted, deploys to the affected service freeze, except for
fixes that repay the budget (files/10 §6). The platform owner lifts the freeze once the
burn rate has stayed under 1x for 24 hours.

## After the incident

- Record the timeline and the budget spent in the incident notes.
- If the alert was noise, do not widen thresholds ad hoc. Propose the change against
  `docs/slo/<service>.yaml`: rules and dashboards regenerate from it, and objectives may
  tighten, never silently loosen.
- Verify the alert resolved in Alertmanager and the burn panels returned under 1x.
