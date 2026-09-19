# Proposal — Admin observability panel (director / clinician)

Status: proposal (not yet in `docs/backlog/issues.yaml`). Epic: **E12-admin**.
Author lane: platform. Seeds a director/clinician landing view over the operational
and quality signals the platform already emits, and extends the existing E12-admin
issues (INT-181 Overview/Ops/Reliability, INT-182 Voice, INT-187 CI/CD, INT-190 Cost,
INT-186 Experience) rather than replacing them.

## Governing rules (from CLAUDE.md — non-negotiable here)

- **Invariant 6 — no PHI/PII anywhere.** Every tile is an aggregate or an id.
  Metric labels are enumerable identifiers only (service, method, route *template*,
  status class, vendor, profile, tenant id); a free-text or patient label never
  reaches a chart. The wired read path (`apps/admin-web/src/status`) refuses a
  whole `/metrics` scrape that carries any `PHI_RISK_LABEL_NAMES` label.
- **Invariant 15 — nothing emits uncatalogued.** Every metric named below is
  mapped to `observability/metrics_catalog.yaml`: **exists** (already catalogued,
  `live` or `planned`) or **NEW** (a catalog entry this proposal adds). Only one
  NEW entry was required — see group (c). Health/version/gate signals that are
  *endpoints or CI artifacts, not Prometheus series* are marked **endpoint** and
  need no catalog row.
- **Invariant 20 — no accuracy/target claims on the surface.** Figures are
  operational readings over a stated window; SLO objectives live in
  `docs/slo/*.yaml` and are never rendered as a pass/fail badge beside a number.
- **k-anonymity floor** (files/06 §8; files/08 §0c F9): satisfaction / experience
  aggregates suppress below k≥10 (`intake_metrics.rollups.MIN_COHORT`); only the
  count survives a small cohort. No branch × narrow-window × small-clinic slice.

Legend: `live` = real code emits it today · `planned` = catalogued, emitter not
landed · **NEW** = catalog entry added by this proposal · **endpoint** = read from
an HTTP endpoint / external API, not a Prometheus series.

---

## SPEC — what to track

### (a) Live service status — per service: api, voice-runtime, workers, metrics, probes

| Signal | Metric / source | Catalog status |
|---|---|---|
| Liveness | `/healthz` 200 | **endpoint** (`intake_platform.health`) |
| Readiness + per-check state | `/readyz` `{checks:{...}}` | **endpoint** |
| Build identity (git_sha, built_at, sbom_digest) | `/version` | **endpoint** |
| Synthetic probe up/down per component | `probe_status{component}` | exists (planned) |
| Probe latency per component | `probe_latency_ms{component}` | exists (planned) |
| Per-service RED signals | `svc_latency_ms`, `svc_rps`, `svc_error_ratio`, `svc_saturation` | exists (planned) |
| Request volume + status split (availability SLI) | `http_requests_total{service,method,route,status}` | exists (**live**) |
| Request latency (latency SLI) | `http_request_duration_seconds{service,method,route}` | exists (**live**) |
| Process health | `process_resident_memory_bytes`, `process_cpu_seconds_total`, `process_open_fds`, `process_start_time_seconds` | exists (**live**) |

Scrape reachability itself is derived from the fetch succeeding (Prometheus `up` is
scraper-generated, not app-emitted); the read path fails closed to "down" when a
service's `/metrics` does not answer. The two **live** families + the process gauges
are exactly what the wired page renders today.

### (b) Model / lane usage — ASR / TTS / extract: call count, latency, error rate

| Signal | Metric | Catalog status |
|---|---|---|
| ASR audio-seconds / duration per turn | `voice_stt_audio_s`, `voice_stt_duration_ms` | exists (planned) |
| ASR confidence / WER proxy | `voice_asr_confidence_mean`, `voice_asr_wer_proxy` | exists (planned) |
| ASR/TTS **call count** | histogram `_count` of `voice_stt_duration_ms` / `voice_tts_ttfb_ms` | exists (derived, no new metric) |
| TTS time-to-first-byte | `voice_tts_ttfb_ms` | exists (planned) |
| TTS characters synthesised (cost proxy) | `voice_tts_chars` | exists (**live**) |
| Extract served / refused / accuracy | `research_extract_served_total`, `research_extract_refused_total` (live); `records_extraction_accuracy`, `hallucination_audit_rate` (planned) | exists |
| Document ingest pipeline | `document_upload_pipeline` | exists (**live**) |
| **Error / fallback rate** per vendor | `vendor_adapter_failures_total{vendor}`, `vendor_adapter_fallbacks_total{vendor}`, `vendor_fallback_latency_seconds` | exists (**live**) |

Error rate = `vendor_adapter_failures_total` / call-count `_count`; no dedicated
`*_calls_total` counter is needed because every latency histogram carries `_count`.

### (c) ElevenLabs TTS cache — hit/miss ratio, synth count, cost proxy

| Signal | Metric | Catalog status |
|---|---|---|
| Production scripted-clip cache hit ratio | `voice_clip_cache_hit_ratio` | exists (planned) |
| Production synth chars (cost proxy) | `voice_tts_chars` | exists (**live**) |
| Per-session cost by component | `cost_per_session{component}` | exists (planned) |
| **Dev-lane George/ElevenLabs on-demand cache hit/miss + synth count + cost proxy** | `dev_george_clip_requests_total{result}` (result=hit\|miss) | **NEW — added by this proposal** (planned) |

The dev-lane on-demand cache (ADR-028, `services/api/dev_voice.py`) reports its result
today only via the `X-George-Cache: hit|miss` response header and constructs no
Prometheus family. `dev_george_clip_requests_total{result}` was added to the catalog
(status `planned`, closed `{hit,miss}` label, no per-turn tenant/profile/branch series
because invariant 19 keeps ElevenLabs off the PHI path): `miss` is the synth count and
the vendor-cost proxy, `hit/(hit+miss)` is the cache hit ratio. Making it emit is
group (c)'s roadmap issue.

### (d) Patient experience — wait time, turn latency, completion/abandon, satisfaction

| Signal | Metric | Catalog status |
|---|---|---|
| Wait to first question / answer latency | `wait_time_to_first_question_s`, `wait_answer_latency_s` | exists (planned) |
| Check-in → seen / records processing | `wait_checkin_to_seen_min`, `wait_records_processing_s` | exists (**live**) |
| Note ready after wrap-up / doctor-link first open | `wait_note_ready_after_wrapup_s`, `wait_doctor_link_first_open_h` | exists (planned) |
| Turn latency (round-trip / TTFT / insertion wait) | `voice_round_trip_ms`, `voice_talker_ttft_ms` (planned); `delivery_insertion_wait_ms` (**live**) | exists |
| Completion / abandon / duration / repeats | `session_completion_rate`, `session_abandon_step`, `session_duration_s`, `session_repeat_requests` | exists (planned) |
| **Satisfaction signal (yes, one exists)** | `csat_score`, `csat_reason`, `nps_monthly`, `clinician_pulse` | exists (**live**) |

Satisfaction / experience tiles are the INT-186 rollups behind the k≥10 floor; the
console projection (`apps/admin-web/src/experience`) already refuses a small-cohort
figure, a free-text leak, a target beside a figure, and a branch/clinic slice.

### (e) CI/CD & SLO — SLO burn from docs/slo/*.yaml, gate pass/fail

| Signal | Metric / source | Catalog status |
|---|---|---|
| SLO burn rate / error budget | `slo_burn_rate{window}`, `slo_error_budget_remaining` | exists (planned) |
| Named SLO objectives | `slo_api_availability`, `slo_voice_session_success`, `slo_note_ready_within_60s`, `slo_doctor_link_open_p95` | exists (planned) |
| SLI expressions + burn-rate alert rules | `docs/slo/<service>.yaml` → `infra/observability/prometheus-rules.yaml` | source (generated) |
| Deploy frequency / change-failure / rollbacks | `deploy_frequency`, `deploy_change_failure_rate`, `deploy_rollbacks_total` | exists (planned) |
| **CI gate pass/fail** | GitHub Actions run status via GH API | **endpoint** (CI artifact, not a Prometheus series — read by the INT-187 module) |
| Chaos / load posture | `chaos_experiment_runs_total` (live), `chaos_last_result`, `load_max_concurrent_sessions` (planned) | exists |

Gate pass/fail is deliberately **not** a new metric: CI gates run in GitHub Actions,
not a scraped long-lived service, so the CI/CD module reads run/gate status from the
GH API (as INT-187 already scopes) rather than a pushed counter.

---

## ROADMAP — issues to build the full panel

Format matches `docs/backlog/issues.yaml`. **IDs are `INT-xxx-PROPOSED` placeholders.**
Do not edit `issues.yaml` from this proposal: real INT ids must be minted by the
backlog machinery at intake time (concurrent id allocation collides otherwise —
see memory *"Parallel agents collide on numbered artifacts"*). Ordering is
dependency-first.

```yaml
- id: INT-330-PROPOSED   # lands the wired read path
  epic: E12-admin
  phase: P1
  title: "Live service-status read path + Overview status tiles (api/voice-runtime/workers/metrics/probes)"
  depends_on: [INT-181]
  labels: [area:admin]
  status: proposed
  acceptance:
    - "GET /admin/status composite polls each service /metrics + /healthz + /readyz + /version and returns a per-service {reachable, live, build, request/error tally, process gauges} projection — no PHI, aggregate/id only (invariant 6)"
    - "Overview page renders a status tile per service from the composite; a dead /metrics fails closed to 'down' with the reason shown, never silently dropped"
    - "renders the http_requests_total 5xx share and process_resident_memory_bytes as readings with an 'as of' time and NO target/SLA badge (invariant 20)"
  tests: [apps/admin-web/e2e/status.spec.ts, tests/admin/test_status_composite.py]
  sec_row: "admin-console"

- id: INT-331-PROPOSED
  epic: E12-admin
  phase: P1
  title: "Model & lane-usage panel: ASR/TTS/extract call count, latency, error+fallback rate"
  depends_on: [INT-330-PROPOSED, INT-182]
  labels: [area:admin]
  status: proposed
  acceptance:
    - "per-lane tiles project voice_stt_* / voice_tts_* / records extraction + document_upload_pipeline; call count from the histogram _count, error rate from vendor_adapter_failures_total over that count"
    - "vendor fallback rate + vendor_fallback_latency_seconds surfaced per vendor; labels closed to {tenant,profile,branch,vendor} (invariant 13)"
  tests: [apps/admin-web/e2e/lane_usage.spec.ts]
  sec_row: "admin-console"

- id: INT-332-PROPOSED
  epic: E12-admin
  phase: P1
  title: "TTS cache & synth-cost panel incl. dev-lane George (ElevenLabs) cache"
  depends_on: [INT-330-PROPOSED, INT-190]
  labels: [area:admin]
  status: proposed
  acceptance:
    - "dev_george_clip_requests_total{result} emitted by services/api dev_voice on every hit/miss (turn the catalogued planned entry live on the dev lane); hit ratio + synth count (miss) + cost proxy rendered"
    - "production tiles project voice_clip_cache_hit_ratio + voice_tts_chars + cost_per_session; ElevenLabs stays dev-lane only (invariant 19) — the panel labels it as such"
  tests: [tests/api/test_dev_george_cache_metric.py, apps/admin-web/e2e/tts_cache.spec.ts]
  sec_row: "admin-console"

- id: INT-333-PROPOSED
  epic: E12-admin
  phase: P1
  title: "Patient-experience panel: waits, turn latency, completion/abandon, CSAT/NPS/pulse"
  depends_on: [INT-186]
  labels: [area:admin, approval:human-legal]
  status: proposed
  acceptance:
    - "wait_* / voice turn-latency / session completion+abandon rollups joined to the INT-186 experience module; every figure behind the k>=10 floor, small cohorts keep only the count (files/06 §8; files/08 §0c F9)"
    - "no branch/profile/clinic slice unless the INT-241 data-inventory decision lands; the filter mechanism stays fail-closed"
  tests: [apps/admin-web/e2e/experience.spec.ts]
  sec_row: "admin-console"

- id: INT-334-PROPOSED
  epic: E12-admin
  phase: P1
  title: "SLO burn & CI/CD health panel (docs/slo + burn rate + deploy signals + gate status)"
  depends_on: [INT-330-PROPOSED, INT-187]
  labels: [area:admin]
  status: proposed
  acceptance:
    - "burn-rate tiles from slo_burn_rate{window} + slo_error_budget_remaining, objectives read from docs/slo/*.yaml and shown as objectives, never as a pass/fail verdict beside a live number (invariant 20)"
    - "deploy_frequency/change_failure/rollbacks tiles; CI gate pass/fail read from the GH API (not a Prometheus series); deploy-freeze state on budget exhaustion"
  tests: [apps/admin-web/e2e/slo_cicd.spec.ts]
  sec_row: "cicd"

- id: INT-335-PROPOSED
  epic: E12-admin
  phase: P2
  title: "Director/clinician single-pane Overview stitching the panels with role-scoped tiles"
  depends_on: [INT-330-PROPOSED, INT-331-PROPOSED, INT-332-PROPOSED, INT-333-PROPOSED, INT-334-PROPOSED]
  labels: [area:admin, risk:security]
  status: proposed
  acceptance:
    - "one landing view composes the five panels; tiles scoped by RBAC/ABAC role (director sees ops+cost+SLO+experience rollups, clinician sees quality+experience) through the INT-180 shell — no new audited route bypasses it (invariant 4)"
    - "no figure crosses a role it is not scoped for; all aggregate/id only (invariant 6)"
  tests: [apps/admin-web/e2e/overview_director.spec.ts, tests/admin/test_overview_rbac.py]
  sec_row: "admin-console"
```

---

## What was wired in this pass (read-only, TDD)

`apps/admin-web/src/status/` — the first admin module that reads **live** telemetry
rather than a recorded composite:

- `prometheus.ts` — dependency-free Prometheus text-exposition parser (handles
  `# HELP`/`# TYPE`, scientific-notation gauges, and route-template braces inside a
  label value).
- `module.ts` — `renderServiceStatus(samples)` projects `http_requests_total` +
  `process_*` into a per-service {reachable, live, request/5xx tally, gauges}
  presentation; refuses a scrape carrying a PHI-risk label (`PhiLabelPresent`,
  invariant 6) or `http_requests_total` with a non-catalogued label
  (`ForbiddenMetricLabel`, invariant 13). `fetchServiceStatus(baseUrl)` fetches the
  api `/metrics` on `:8000`, fails closed to "down" on any error, and takes an
  injected fetch so tests never dial a live endpoint.
- `e2e/status.spec.ts` (+ `fixtures/status.metrics.txt`, a recorded exposition) —
  9 tests incl. two negative controls (PHI label, drifted label). Full admin-web
  suite green (126/126); `tsc --noEmit` and eslint clean;
  `tests/observability/test_metrics_catalog.py` green after the NEW catalog entry.
