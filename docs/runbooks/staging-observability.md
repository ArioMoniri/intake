# Staging telemetry tier — runbook (INT-481)

The synthetic staging host (`i-0e489e48739f5de98`, us-east-1) runs a telemetry tier next to the
staging stack and the CI runner slots: `infra/staging/compose.obs.yaml`. **Synthetic patients only**
(HB-I5, HB-L11).

| service | what it does | where to look |
|---|---|---|
| prometheus | scrapes the API, the host and the synthetic probes every 30 s; evaluates every rule file | Grafana; `prom_value` in `lib.sh` from the host |
| alertmanager | holds alert state; one receiver, `console`, that sends nothing | the admin console's **Alerts** page (`/alerts`) |
| node-exporter | host CPU, memory, root disk, load; the deploy markers | Grafana, *Staging — alerts, probes, host and deploys* |
| blackbox-exporter | probes each service's own health endpoint inside the host | the same dashboard, *Synthetic probes* |
| grafana | the staff dashboards, Prometheus as its only datasource | `https://grafana.<host>/` |
| oauth2-proxy-grafana | Grafana's login gate | — |

Nothing in the tier publishes a port or has a route to the internet. Retention is 30 days or 4 GB,
whichever comes first.

## Access

- Open `https://grafana.<host>/` (on the AWS host, `https://grafana.3-211-2-143.sslip.io/`). Sign in
  with your staff Keycloak account: password and second factor, as for the admin console.
- You get in if your account holds a role that may read the ops console: `platform_owner`,
  `platform_admin`, `sre_oncall`, `auditor`, `clinical_lead`, `compliance_officer`, `qms_owner` or
  `researcher`. Anyone else is refused by the gate before Grafana sees the request.
- Everyone is a Grafana **Viewer**. There is no Grafana password, no admin account, no Explore and no
  editing: dashboards are generated (`intake_platform.ops_dashboards`,
  `intake_platform.slo_dashboards`) and change only by a PR.
- A disabled Keycloak account loses Grafana within five minutes (the gate re-checks the session
  every five minutes; sessions last at most eight hours).
- The admin console's **Alerts** page links Grafana. It is a plain link, never a frame.

## Dashboards

| dashboard | reads |
|---|---|
| Staging — alerts, probes, host and deploys (home) | `ALERTS`, `probe_success`, `probe_duration_seconds`, `node_*`, `prometheus_tsdb_*` |
| SLOs, error budgets and latency — API and voice | every SLO in `docs/slo` over its own window, the `slo:` recording rules, `http_request_duration_seconds`, `voice_*_ms`, `work_latency_ms` |
| Model lanes — usage, failures and spend | `work_latency_ms`, `work_failed_total`, `voice_tts_chars`, `vendor_adapter_*`, the `CostBudget*` alerts |
| Triage and RED safety — aggregate only | `triage_events_total` by level, `clinic_red_*`, `policyguard_blocks_total`, `preempt_red_latency_ms` |
| CI runner — queue, durations and gates | `ops_cicd_*`, `ops_collector_source_up`, host CPU |
| SLOs folder (one per service) | the burn-rate rules and golden signals (INT-021) |

A panel whose series nothing on this host emits reads **No data**, and its description says so. That
is the true state: no figure is ever filled in.

Every dashboard draws two deploy markers: **Deploy started** (orange, after the release gate admits a
deploy) and **Deploy completed** (green, after `/healthz` and `/readyz` answer over public HTTPS). A
started with no completed is a deploy that stopped; read `deploy.sh`'s output for why.

## On the host

As root, in `/opt/intake/infra/staging` (over SSM):

```bash
source ./lib.sh && load_env
compose ps prometheus alertmanager node-exporter blackbox-exporter grafana oauth2-proxy-grafana
prom_value 'min(up)'                    # 1: every scrape target answers
prom_value 'min(probe_success)'         # 1: every synthetic probe passes
compose logs --tail 50 prometheus       # never paste a log into a ticket without reading it first
```

`deploy.sh` recreates every telemetry service that reads a config file on each deploy, so the tier
always runs the release's own configuration. Data volumes survive.

## HostDiskBelowCiGuard

The root disk has less than 25 GB free, the CI runner's own start guard (`docs/ci/aws-ci.md`), so
every CI job is now refused.

1. Read *Root disk free* on the home dashboard: is it falling steadily or did it drop at a deploy?
2. On the host, `df -h /` and `docker system df`. The CI slots' dind stores are the usual growth
   (`docs/ci/aws-ci.md`, "Disk").
3. Prune what the CI runbook allows. Never delete a staging volume (`pgdata`, `openbao-data`,
   `minio-data`) or `prometheus-data` to make room.

## HostDiskNearlyFull

Less than 5 % of the root disk is free. Postgres, OpenBao and MinIO stop writing when it fills.

1. Do the steps under HostDiskBelowCiGuard now.
2. If CI is running, stop the CI runner unit (`docs/ci/aws-ci.md`) until there is room.
3. Prometheus cannot be the cause on its own: it is capped at 4 GB.

## HostMemoryLow

Less than 10 % of the host's memory is available for 10 minutes. The CI slots are first in line for
the OOM killer (`oom_score_adj: 500`), staging is not.

1. Read *Host CPU busy and memory used* and compare with the CI dashboard: is a CI run in flight?
2. `docker stats --no-stream` on the host. The telemetry tier is capped at 1.4 GiB in total.
3. If no CI run explains it, look for the staging service that grew and restart it during a quiet
   window.

## SyntheticProbeFailing

A staging service's own health endpoint (the alert's `component`) has failed its probe for five
minutes. The probes run inside the host, so this is the service, not the network.

| component | endpoint | first look |
|---|---|---|
| `api` | `api:8000/readyz` | `/readyz` names the failing check; `docs/runbooks/staging.md` |
| `admin-web` | `admin-web:3000/healthz` | `compose logs admin-web` |
| `admin-login`, `grafana-login` | the two oauth2-proxies' `/ping` | `compose ps`; Keycloak must be healthy |
| `keycloak` | `keycloak:9000/health/ready` | `docs/runbooks/keycloak-realm.md` |
| `grafana`, `alertmanager`, `prometheus` | their own health endpoints | `compose logs <service>` |

## SyntheticProbeUnmeasured

The blackbox exporter did not answer Prometheus, so no probe result exists. `compose ps
blackbox-exporter`; `compose up -d --no-build blackbox-exporter`. Until it answers, a service could
be down without SyntheticProbeFailing firing.

## ScrapeTargetDown

Prometheus cannot scrape a target (`component` is the scrape job: `api`, `node` or `prometheus`).
For `api`, the API itself is down: `docs/runbooks/staging.md`. For `node`, the host figures and the
deploy markers stop: `compose up -d --no-build node-exporter`.

## PrometheusStorageNearCap

Prometheus has used 80 % of its 4 GB cap, so the oldest data will soon be dropped before 30 days.
Read *Series in memory*: a jump is a cardinality change, usually a new label value. Every scrape job
keeps the reviewed label keys only (invariant 6), so the growth is in values; find the family and
fix the emitter. Do not raise the cap without a PR.

## PrometheusConfigReloadFailed

Prometheus is running on a configuration it could not load. `compose logs --tail 50 prometheus`
names the line. The fix is a PR to `infra/staging/observability/`, then a deploy; the deploy
recreates Prometheus on the release's file.
