# SLO burn-rate alerts — api

Every burn-rate alert in `infra/observability/prometheus-rules.yaml` links one
of the headings below (`tests/observability/test_slo_generator.py` holds the
links true). The SLOs themselves live in `docs/slo/api.yaml`; policy numbers
come from files/10 §6 and files/08 §5.

## How to read a burn-rate page

A burn rate of `N` means the service is consuming its error budget `N` times
faster than the objective allows. Budgets over the 28-day window:

- **availability 99.9 %** → budget ratio 0.001 (~40 minutes of full outage
  per 28 days).
- **latency 99 % within 500 ms** → budget ratio 0.01 (~6.7 hours in which
  every request is slow, per 28 days).

The alert fires only when BOTH the long and the short window burn above the
threshold — the short window is what lets the alert reset quickly once the
cause is fixed. Severity `page` interrupts a human now; severity `ticket`
files work for the next business day.

First five minutes, for every alert here:

1. Open the Grafana dashboard `intake-api-slo` (dashboard as code:
   `infra/observability/grafana/api-slo-dashboard.json`).
2. Check the deploy timeline: if a rollout correlates with the burn onset,
   roll back first and diagnose second (canary + automatic rollback is the
   default posture, files/10 §5).
3. Check `/readyz` of the api pods — a failing readiness check names the
   dependency (DB, Redis, queue, OpenBao) in its response body.
4. Check the error panel (`5xx by status`) to separate a total outage from a
   single failing route; the `route` label is the template, so it names the
   endpoint without carrying any request data.

## api availability fast burn

`ApiAvailabilityFastBurn` — error ratio above 14.4x the 0.001 budget over 1h
AND 5m. At this rate 2 % of the 28-day budget disappears every hour; an
unattended day ends the budget.

- Treat as an outage until shown otherwise. Roll back the newest deploy of
  the api even before root cause is known.
- If `/readyz` blames a dependency, fail over or restart that dependency
  first; the api counts a 5xx for every request it cannot serve.
- If only one route burns, weigh disabling that route against the budget:
  the SLI counts every request equally.
- Escalate to the platform on-call lead if the 5m window has not dropped
  below threshold within 30 minutes.

## api availability slow burn

`ApiAvailabilitySlowBurn` — error ratio above 6x budget over 6h AND 30m
(~5 % of the monthly budget per 6 hours). Same diagnosis path as the fast
burn, but with room to prefer diagnosis over rollback: look for partial
failure — one pod, one dependency timeout, one tenant's traffic pattern.
Silence only with an owner and an end time.

## api availability ticket burn

`ApiAvailabilityTicketBurn` — error ratio above the budget itself over 3d AND
6h. Nothing is on fire; left alone, the window ends short of its objective.
File the investigation, find the background error source (retries masking a
flaky dependency, a noisy client, a slow leak) and fix it inside the sprint.
If the monthly budget is exhausted, the deploy freeze in the error-budget
policy below applies.

## api latency fast burn

`ApiLatencyFastBurn` — share of requests slower than 500 ms above 14.4x the
0.01 budget over 1h AND 5m.

- Check saturation panels first: CPU throttling, memory pressure or fd
  exhaustion slow every route at once.
- Check p95 vs p50: p95-only degradation points at a dependency timing out;
  both moving together points at load or a slow deploy.
- Check traffic: a step in rps with flat capacity is a scaling action, not a
  code fix.
- Rolling back the newest deploy remains the cheapest hypothesis test.

## api latency slow burn

`ApiLatencySlowBurn` — latency error ratio above 6x budget over 6h AND 30m.
Usually a regression that shipped hours ago or slow dependency drift. Compare
route-level p95 against the previous day, then bisect deploys within the
burn window.

## api latency ticket burn

`ApiLatencyTicketBurn` — latency error ratio above budget over 3d AND 6h.
Chronic slowness: a query missing an index, an N+1 on one route, payload
growth. File it with the route-level evidence from the dashboard and land the
fix before the window closes.

## Error-budget policy

When a 28-day budget is exhausted, deploys to the affected service freeze
except for fixes that repay the budget (files/10 §6). The freeze is lifted by
the platform owner once the burn rate has stayed under 1x for 24 hours.

## After the incident

- Record the timeline and the budget spent in the incident notes.
- If the alert was noise, do not widen thresholds ad hoc: propose the change
  against `docs/slo/api.yaml` — rules and dashboards regenerate from it, and
  objectives may tighten, never silently loosen.
- Verify the alert resolved in Alertmanager and the burn panels returned
  under 1x.
