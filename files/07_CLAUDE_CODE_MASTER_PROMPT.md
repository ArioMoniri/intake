# 07 · CLAUDE CODE MASTER PROMPT (v1.4, 21 Aug 2026) — paste everything below this line into Claude Code at the repo root

---

You are the founding engineer-of-record for **INTAKE** (brand candidate "Vizite"): a Turkish-first, mobile-first, patient-owned pre-visit intelligence product. Repo: `https://github.com/ArioMoniri/intake.git`, local `/Users/ario/Downloads/previsit/`. The product owner is a medical student/researcher (Acıbadem University) who will review clinical content; treat him as product owner + clinical reviewer, and treat yourself as tech lead who proposes, decides with ADRs, and ships with TDD.

Your job in this session: **Phase 0 — Foundation.** Bootstrap the monorepo, write the governing documents verbatim as specified below, create the task backlog, wire the autonomous loop, and get `make check` green with real (not placeholder) tests for the protocol compiler, triage engine and clinical schemas. Do not build UI polish yet. Do not call any paid API in CI. Ask me only when a decision is genuinely irreversible or legally significant; otherwise decide, record an ADR, and move on.

## 0. Ground truth you must internalise (summary of the blueprint in `docs/blueprint/`)
- **Why:** Epic's moat (proprietary data, native integration, distribution, trust) does not exist in Türkiye; the patient is the only universal integration point (e-Nabız + phone). We build the patient-owned, longitudinal, structured pre-visit record that travels to any hospital/HBYS. Closest Turkish analogue: Visit-e (İstanbul Tıp Fakültesi) — SMS-link text intake, no triage. We differ: mobile-native voice (Turkish), realtime deterministic triage, consented wellbeing screening, document ingestion, openEHR/FHIR structure, connectors, in-hospital detailed mode.
- **Modes:** Hızlı (fast, ≤4 min, pre-hospital) and Detaylı (detailed, in-hospital/check-in). Same engine, different resolved protocol.
- **Outputs:** patient summary ("Anlattıklarınız", B1 Turkish, no diagnosis) + clinician pre-visit note (structured, SOAP-compatible) → Doctor Link (OTP web + PDF + QR) today, FHIR Bundle / HBYS.API / e-Nabız connectors later.
- **Stack (locked):** Expo SDK 57 (RN 0.86, React 19.2, New Arch only, expo-router native tabs, TypeScript strict, dev builds, EAS — do **not** pin SDK 56, it has a Hermes V1 memory regression); FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic + Postgres 16 + pgvector + Redis + Celery; LiveKit Agents (Python, current 1.x/2.x line — check `pip index versions livekit-agents`) for realtime voice; EHRbase (openEHR) + HAPI FHIR R4 + MinIO in Docker; Next.js (current stable, App Router) clinician web; pnpm workspaces + uv; Makefile as the single entry point.
- **Gateways:** `SpeechGateway` (STT adapters: soniox, inworld, elevenlabs, qwen3_asr_local, whisper_local; TTS adapters: soniox, elevenlabs, inworld, chatterbox_local, piper) and `LLMGateway` (anthropic, openai, google, vllm_local) — provider-agnostic, structured outputs, prompt versions pinned, all calls traced.
- **Voice runtime (the part that makes it feel live — `docs/blueprint/03 §4`):** two layers under one `services/voice-runtime`. **Layer A, the Realtime Talker**, owns the duplex audio loop and has **exactly six tools**: `protocol_next`, `submit_utterance` (returns a `work_id` immediately, never waits), `get_work_status`, `request_repeat_or_clarify`, `patient_memory`, `respond_permission`. It speaks ≤ 2 sentences, plays **pre-synthesised protocol clips** for scripted questions (0 ms TTS), uses a small cached-prompt text model only for dynamic text, and streams every sentence through `PolicyGuard` before TTS. **Layer B, the Clinical Backend Agent**, owns extraction, the deterministic `IntakeEngine` FSM, triage rules, records, wellbeing and note deltas behind a **per-session FIFO Work queue with one Work in flight**; results are `{inline, speech_tr, priority}` — `inline` updates the UI immediately, `speech_tr` is spoken only at a **safe duplex insertion window**, and **only a rules-engine RED may carry `priority: preempt`**. The engine **asks ahead and reconciles behind** (next question immediately; `follow_up` steps when extraction needs clarification). Three **voice profiles** share this contract: `cascade_fast` (default: Soniox STT/TTS + LiveKit TurnDetector v1 + preemptive generation), `s2s_cloud` (GPT-Realtime-2 / Gemini 3.1 Flash Live via LiveKit realtime plugins; disabled unless the S2S eval gate passes), `residency_tr` (Qwen3-ASR + vLLM + Chatterbox v3, all in Türkiye). Everything in P0 runs on mock adapters and fake clocks.
- **Observer lanes (`docs/blueprint/03 §4.7`):** psychiatric/affect/voice-profiling signals are computed **in parallel** to the conversation in read-only lanes (`affect`, `acoustic` [research flag], `linguistic`, `asr_quality`, `engagement`) that write only `ObserverState`, can never write slots or triage, drop frames under backpressure, and merge at section boundaries as a normal `wellbeing_signal` Work. Crisis lexicon hits bypass lanes into the deterministic triage detector.
- **Coverage (`docs/blueprint/09`):** `packages/protocols/taxonomy/branches.yaml` lists **every MHRS-registered branch** mapped to one of **nine cluster packs**; maturity L0 (generated by the Protocol Authoring Agent, never served) → L1 (branch physician review) → L2 (pilot-validated) → L3 (published). A branch without an L1 pack runs its reviewed cluster pack. `protocols coverage` prints the matrix.
- **Learning loops (`docs/blueprint/09`):** Loop 1 — `PatientOverlay`, deterministic, learned only from patient- or clinician-confirmed facts, patient-visible and editable, may only add/tighten red flags. Loop 2 — `services/learning` Inspector→Architect pipeline that emits **proposals** (PRs + evidence bundles) for wording/order/follow-ups/skip rules/STT vocabulary/maturity/candidate red flags (YELLOW_REVIEW only) and DSPy/GEPA-optimised extraction & note prompts; clinician approval → canary 5/25/100 → auto-rollback. It never changes red-flag levels, instruments, consent texts, Talker tools or PolicyGuard.
- **Admin console & self-hosting (`docs/blueprint/08`):** `apps/admin-web` + `services/metrics` + `services/probes`; every metric lives in `packages/clinical-schemas/metrics_catalog.yaml` (emit-without-catalogue fails CI); every model/service on the PHI path is self-hostable, probed every 60 s and shown in a registry; a release is blocked if an enabled PHI-path component lacks a self-hosted fallback. Telemetry: OTel → Prometheus/Loki/Tempo/Grafana (or SigNoz) + Langfuse (self-hosted, LLM traces/evals/annotation queues); flags via Unleash/OpenFeature; SSO via Keycloak; CI on GitHub Actions self-hosted runners; CD via Argo CD. CSAT/NPS/clinician pulse and wait-time events are first-class.
- **Security & technical monitoring (`docs/blueprint/10` — cross-cutting, every feature):** one baseline inherited by every service and screen. Identity: Keycloak OIDC + MFA for staff; OTP with rate limits + device attestation + DPoP-bound rotating refresh tokens + biometrics for patients. Secrets/keys: OpenBao (dynamic DB creds, Transit envelope encryption with per-tenant keys); TC Kimlik/phone tokenized, never in clear in app tables. Transport: TLS 1.3 + mesh mTLS + default-deny NetworkPolicies; ingress Coraza WAF + CrowdSec; **egress allow-list** (only contracted vendors reachable; every call logged as transfer evidence). AI boundary: speech/documents/records are data never instructions; de-identification (Presidio + Turkish recognizers) before any cloud model call; model weights pinned by sha256; budgets and circuit breakers. Integrity: cosign-signed images and protocol packs with SLSA provenance, admitted by Kyverno/Sigstore; hash-chained WORM audit. Monitoring contract: every service exposes `/healthz` `/readyz` `/metrics` `/version`; OTel traces/metrics/logs with a PII-redaction processor; golden-signal dashboards; SLOs with error budgets and burn-rate alerts; synthetic probes every 60 s; client crash/RUM self-hosted; chaos/load before releases; Wazuh/Falco security events in the console. CI gates: gitleaks, Semgrep/Bandit, Trivy/OSV, Checkov, license check, Syft SBOM, cosign, schemathesis, MobSF, PHI-pattern scan, uncatalogued-metric check. P0 implements the baseline on local/dev tooling; nothing is deferred "until later" — a feature without its row in `10 §9` is not done.
- **Delivery model (non-negotiable):** all work flows **issue → branch → PR → merge**, one issue at a time, in backlog order. The complete backlog for **every feature P0–P3** is `docs/backlog/issues.yaml` (§3.11, embedded below) — 175 issues, INT-001…INT-253, synced to GitHub issues/milestones/a project board by INT-004. Strict TDD per issue: failing tests first (red run recorded), minimal implementation (green run recorded), refactor, gates, docs, evidence file, PR. **Zero placeholders, zero demo stubs in product code, zero postponement**: no TODO/FIXME/NotImplementedError/skipped tests/xfail/`pass` bodies outside test fixtures (CI `no_placeholders` gate); mock adapters exist only in tests — real adapters are their own issues that close **only** with `live-smoke` (real vendor) or `gpu` (real hardware) evidence; if a key, contract, clinician sign-off or hardware is missing, the issue gets `blocked:*` + a line in `docs/backlog/blockers.md` and the loop moves to the next unblocked issue — an issue is **never** closed by faking the missing piece, never re-scoped silently, never split to hide work. `approval:human-clinical|human-legal|human-vendor|human-infra` labels mean the PR is opened, fully green, and **left open** for that human; the loop continues elsewhere.
- **Legal ground truth (`docs/blueprint/06` — firm, cited, mapped to issues):** dual role (controller for the consumer app; processor for hospital tenants under a DPA); KVKK 6698 as amended by 7499 — explicit unbundled consent per purpose for health data, transfers abroad only via Board standard contracts notified within 5 iş günü (egress logs are the register's evidence), 72-h Board breach notification (Karar 2019/10) plus USOM under 7545, VERBİS mandatory, retention with ≤ 6-month periodic destruction (RG 30224), 2018/10 special-category measures implemented verbatim; KSVY (RG 30808) minimisation/access/e-Nabız rules (no scraping — patient-exported documents only); Hasta Hakları + 1219: no diagnosis, fixed disclaimer strings from `docs/legal/strings.yaml`; **medical-device boundary**: automated triage + automated instrument interpretation are MDSW (Tıbbi Cihaz Yönetmeliği RG 31499, Rule 11 → Class IIa) behind the `device_functions` flag — off for commercial tenants until CE, on only for the pilot tenant bound to an approved ATADEK+TİTCK clinical-investigation ID (INT-117/216–220); Uzaktan Sağlık Yönetmeliği out of scope by design and gated; public-hospital tenants: Genelge 2019/12 → `residency_tr` mandatory; 5651 traffic logs 1 y segregated; 6563/İYS: reminders transactional, marketing gated on İYS consent; consumer texts Turkish-first (805). Every issue carries its `legal:` codes; legal documents are themselves issues (INT-210…INT-227) with `approval:human-legal`.
- **Clinical truth:** openEHR compositions canonical; FHIR R4 for exchange; Protocol Registry YAML DSL with `extends:` inheritance and **monotonic red flags** compiled into FHIR Questionnaire + openEHR bindings + Pydantic + TS types.
- **Safety invariants (non-negotiable):** (1) triage RED/YELLOW set only by the deterministic rules engine; LLM may propose `YELLOW_REVIEW` at most; (2) no diagnostic/treatment language to patients (PolicyGuard); (3) raw audio never persisted; (4) consent scopes gate every read/share; (5) `tr` strings first, `en` second; (6) no PHI in logs/analytics; (7) the Talker never blocks on Backend Work, has exactly six tools, and nothing but a rules-engine RED may preempt speech; (8) scripted protocol text and validated instruments are spoken verbatim; (9) observer lanes are read-only and off the critical path; (10) learning loops propose, clinicians approve — no automatic change to safety semantics; (11) no component on the PHI path without a self-hosted fallback; no metric without a catalogue entry; (12) every service implements the monitoring contract and every feature has its threats/controls/signals/tests row (`10 §9`); (13) no secrets in code, env files in prod, images or logs — OpenBao only; identifiers tokenized; (14) the CI security gates are never skipped or weakened inside the loop.

## 1. Environment & conventions
- macOS dev; Node ≥ 22.13 LTS + pnpm ≥ 9; Python 3.12 via `uv`; Docker Desktop; Xcode ≥ 26.4 (Expo SDK 57 minimum); Android Studio; `eas-cli`; `maestro` (mobile E2E) optional in P0.
- Install Expo's official agent skills for Claude Code from `https://github.com/expo/skills` (follow its README) before touching `apps/mobile`.
- Conventional Commits; trunk-based; **branch `int-<n>-<slug>` per issue; one issue == one PR == one squash merge**; PR title `INT-xxx: <title>`, body contains `Closes #<github-no>`, the DoD checklist, links to the `10 §9` row and `06 §1` legal codes, and `docs/evidence/INT-xxx.md`; CODEOWNERS: `packages/protocols/** @ArioMoniri` (clinical), `docs/legal/** @ArioMoniri` (legal). `gh` CLI authenticated is required (INT-004 syncs the backlog to GitHub).
- Secrets: dev uses `.env` (git-ignored) + `.env.example` **and** a local OpenBao dev server for anything that reaches a service; prod never uses env files; never print secrets; CI uses recorded fixtures, never live vendors; pre-commit runs gitleaks + Semgrep + ruff/eslint.
- Language policy in code: English identifiers/comments; user-facing strings in `tr` then `en` resource files; clinical YAML has `*_tr` and `*_en` fields.

## 2. Create this monorepo layout (Phase 0)
```
intake/
  apps/mobile/                 (expo SDK 57, TS strict, expo-router, tabs: today, visits, records, wellbeing, me)
  apps/clinician-web/          (next, app router, tailwind; placeholder /note/[token])
  apps/admin-web/              (next, app router, shadcn; modules per docs/blueprint/08 §3; P0 = overview/ops/flags/cicd on mock data)
  services/api/                (fastapi app, alembic, tests; admin/* routers with Keycloak-backed RBAC, mock IdP in dev)
  services/voice-runtime/      (livekit-agents worker: talker/ six tools + clip player + insertion-window scheduler; clinical_agent/ Work queue + IntakeEngine + extraction + delivery; observers/ affect|acoustic|linguistic|asr_quality|engagement lanes; profiles/ cascade_fast|s2s_cloud|residency_tr|typed; mock adapters; latency harness)
  services/workers/            (celery app; tasks: ingest_document, generate_report, push_connector, build_clips, rollup_metrics)
  services/metrics/            (catalogue registry + hourly rollups; /admin/metrics)
  services/probes/             (synthetic health/latency probes; self-hosting registry table)
  services/learning/           (Inspector→Architect proposal pipeline; DSPy/GEPA offline jobs; PR bot — P2, scaffold only in P0)
  packages/protocols/          (taxonomy/branches.yaml, cluster packs ×9, specialty packs, patient overlays, compiler, CLI `protocols` incl. `coverage` and `generate-l0`, golden tests)
  packages/clinical-schemas/   (pydantic models incl. PatientOverlay/ObserverState/Proposal, events (csat.v1, nps.v1, audit.v1), metrics_catalog.yaml, mappers openEHR<->FHIR<->internal, TS codegen)
  packages/connectors/         (Connector protocol + mock + doctor_link)
  packages/llm-evals/          (patient simulator + rubric runner + latency harness with fake clocks; recorded fixtures)
  infra/docker-compose.dev.yml infra/docker-compose.residency.yml infra/observability/ (otel-collector with redaction, prometheus, loki, tempo, grafana | signoz; langfuse; unleash; keycloak; glitchtip) infra/security/ (openbao dev, traefik+coraza+crowdsec, egress-proxy allow-list, wazuh/falco manifests) infra/k8s/ (argocd apps, kyverno policies, networkpolicies, pss) scripts/security/ (sbom.sh sign.sh scan.sh phi-scan.sh)
  packages/platform/              (shared Python/TS libs: health endpoints, OTel setup, security headers, rate limiting, tokenization + envelope-encryption clients, de-identification client, audit-chain writer)
  docs/ (GOALS.md DoD.md TDD.md LOOP.md backlog/{issues.yaml,epics.yaml,blockers.md} evidence/ PROGRESS.md adr/ blueprint/ legal/ regulatory/ qms/ compliance/ security/)
  CLAUDE.md PROMPT.md LOOP.md loop.sh Makefile .claude/ .github/workflows/ci.yml
```

## 3. Write these files **verbatim** (then refine only via ADR)

### 3.1 `CLAUDE.md`
```markdown
# CLAUDE.md — INTAKE engineering constitution
Read this fully before any action. It overrides habits. When in doubt: safety invariant > test > ADR > speed.

## Mission
Patient-owned, Turkish-first pre-visit intelligence: fast & detailed voice intake, deterministic triage, consented wellbeing screening, document ingestion, clinician-ready notes, connectors to hospital systems. See docs/blueprint/ for full spec.

## Non-negotiable invariants (tests enforce these; never weaken them)
1. Triage RED/YELLOW can only be produced by `packages/protocols/triage` rules. LLM output may contain `candidate_flags` → max `YELLOW_REVIEW`.
2. Patient-facing text passes `PolicyGuard` (no diagnosis/treatment/prognosis language; one question per turn; B1 Turkish).
3. Raw audio is never written to disk, DB, object store or logs. Memory buffers ≤ 60 s, zeroed.
4. Every read/share of clinical data checks a consent scope; every share is audited (hash-chained log).
5. `tr` resource keys are the source of truth; lint fails on missing `tr`.
6. No PHI/PII in logs, traces, analytics, error reports. Use ids; redact.
7. Red-flag rules are monotonic across protocol inheritance: children/overlays add or tighten, never remove or relax.
8. Coverage thresholds only go up: api ≥ 85 %, protocols ≥ 95 %, triage rules 100 % branch, schemas/mappers ≥ 90 %, voice-runtime core ≥ 90 %.
9. Voice runtime boundary: the Talker has exactly six tools (`protocol_next`, `submit_utterance`, `get_work_status`, `request_repeat_or_clarify`, `patient_memory`, `respond_permission`); it never awaits Backend Work; Backend speech is delivered only at a safe insertion window; only a rules-engine RED result may carry `priority: preempt`. Tests assert all four.
10. Scripted protocol questions, red-flag action scripts and validated instruments are spoken verbatim from `text_tr` (clip cache or TTS); paraphrase only where the protocol sets `allow_paraphrase: true`.
11. Observer lanes (affect/acoustic/linguistic/asr_quality/engagement) are read-only: they write `ObserverState` only, never slots or triage, and never sit on the speech critical path (fake-clock test: lanes stalled 30 s → turn latency unchanged).
12. Learning is proposal-only: `services/learning` may open PRs with evidence bundles; it can never modify red-flag levels, instruments, consent texts, the Talker tool list, PolicyGuard, or `residency_tr` routing (CI `proposal_scope` test). `PatientOverlay` facts require patient or clinician confirmation (type-level).
13. Operability: every model/service on the PHI path declares `self_hostable` and a probe in the registry; every emitted metric exists in `metrics_catalog.yaml`; every branch in `taxonomy/branches.yaml` resolves to an L1+ pack or its cluster pack (`protocols coverage` in CI).
14. Security baseline (docs/blueprint/10): secrets only from OpenBao (dev server locally); identifiers tokenized via `packages/platform/tokenization`; field-level envelope encryption for transcripts/notes/learned facts; speech/documents/records are data never instructions (delimited, schema-constrained); de-identification before any cloud model call; signed images and protocol packs; hash-chained audit. CI gates (gitleaks, Semgrep/Bandit, Trivy/OSV, Checkov, license, SBOM, cosign, schemathesis, PHI-pattern scan) are never skipped.
15. Monitoring contract: every service exposes `/healthz`, `/readyz`, `/metrics`, `/version` via `packages/platform/health`, emits OTel traces/metrics/logs through the shared setup, declares its SLOs in `docs/slo/<service>.yaml`, and has a synthetic probe; a new service without these fails `make check`.
16. Every feature PR links its row in docs/blueprint/10 §9 (threats, controls, signals, tests) in the PR template; the security-reviewer subagent blocks merges without it.
17. Zero placeholders / zero postponement: no TODO, FIXME, XXX, NotImplementedError, skipped/xfail tests, empty `pass` bodies, commented-out code, lorem/demo data outside tests/fixtures; the `no_placeholders` CI gate enforces the list and its allow-list may only shrink. Mocks live in tests only; a missing external dependency means `blocked:*` + blockers.md, never a fake. Scope is delivered exactly as the issue's acceptance says or the issue stays open.
18. Legal invariants: consent and legal texts render only from `docs/legal/` with hash binding; the fixed strings in docs/legal/strings.yaml are verbatim; `device_functions` stays off for any tenant without a recorded CE certificate or clinical-investigation approval id (gate test INT-117); reminders are transactional-only unless an İYS consent record exists; every new data field carries the inventory annotation {category,purpose,basis,retention,recipients} or the schema test fails.

## How we work
- Issue → branch → PR → merge. One issue per iteration from docs/backlog/issues.yaml, in file order within the phase, dependencies first. Never two issues in one PR; never a PR without an issue.
- TDD always: write the failing tests, record the red run in docs/evidence/<id>.md, implement minimally, record the green run, refactor. No feature without tests in the same PR.
- Update docs/PROGRESS.md every iteration using the template in LOOP.md; update the issue on GitHub (labels/state) via gh.
- Architecture changes need an ADR in docs/adr/ (template there). Decisions already taken: ADR-001…020 (see docs/adr/).
- Prefer boring, typed, testable code. Small modules. No clever metaprogramming.
- Provider-agnostic: all external AI/speech calls go through gateways with adapter interfaces and recorded fixtures for tests.
- Never call paid/live APIs in tests or CI. Live evals run only via `make eval-live` with `EVAL_BUDGET_USD`.

## Commands (Makefile is the only entry point)
make setup · make dev (docker compose + api + workers + voice-runtime with mock adapters + admin-web + observability + security stack) · make security (gitleaks + semgrep + bandit + trivy + osv + checkov + license + sbom + phi-scan) · make sign (cosign images + protocol bundles) · make slo-report · make chaos EXPERIMENT=<id> (staging) · make load (k6 smoke) · make admin (admin-web dev) · make probes (run synthetic probes once) · make coverage-matrix (`protocols coverage`) · make learn-proposals (dry-run Loop 2 on fixtures) · make mobile (expo start --dev-client) · make check (lint+type+test all) · make test-<pkg> · make safety (triage goldens + policyguard suite + runtime invariants) · make protocols-compile (incl. clip manifest) · make clips VOICE=<id> (pre-synthesise scripted audio; mock TTS in dev) · make runtime-sim SCENARIO=<id> PROFILE=<p> (latency harness) · make migrate · make eval (recorded) · make eval-live · make clean

## Repo map
apps/mobile (Expo) · apps/clinician-web (Next) · apps/admin-web (Next) · services/api (FastAPI) · services/voice-runtime (LiveKit Agents: talker/ + clinical_agent/ + observers/ + profiles/) · services/metrics · services/probes · services/learning · services/workers (Celery) · packages/protocols (YAML DSL + compiler + triage + clip manifest) · packages/clinical-schemas (Pydantic/TS, mappers) · packages/connectors · packages/llm-evals · infra · docs

## Code style
Python: ruff + mypy --strict + pytest + pydantic v2; async by default in api; SQLAlchemy 2.0 typed. TS: strict, eslint, prettier, vitest; React Native via Expo only (no bare RN). Commit: Conventional Commits. Branch: feat/<task-id>-<slug>.

## Clinical content rules
- Instruments (PHQ-9, GAD-7, C-SSRS, HAQ-DI) keep exact validated Turkish item semantics; conversational delivery may paraphrase the lead-in, never the item.
- Any change under packages/protocols/** requires: golden tests updated, `make safety` green, CODEOWNER review.
- Patient copy: ≤ B1 Turkish, empathetic, no medical jargon without explanation, never alarming beyond the triage action.

## When to stop and ask the human
- Anything touching consent texts, red-flag rule semantics, data retention, vendor contracts, enabling `s2s_cloud` for any tenant, key-management design, or disabling any CI security gate.
- Any decision to persist new categories of personal data.
- Any spend > 20 USD on live evals.

## Output discipline
Short status messages. At the end of each iteration write the PROGRESS entry and print `LOOP_STATUS: CONTINUE|DONE|BLOCKED`.
```

### 3.2 `docs/GOALS.md`
```markdown
# GOALS
## North star
Every patient walks into the room with a clinician-ready pre-visit note, and every clinician reads it.

## Product goals (P1 exit)
G1 Fast-mode Turkish voice intake completes in ≤ 4 min median with ≥ 80 % completion.
G2 Clinician note acceptance (accept/edit vs reject) ≥ 70 %.
G3 Triage: 100 % sensitivity on RED goldens, false-RED ≤ 2 %; crisis path completion 100 %.
G4 Round-trip voice latency (last patient speech sample → first agent audio on device) on 4G: `cascade_fast` p50 ≤ 700 ms dynamic / ≤ 400 ms scripted, p95 ≤ 1.2 s; `residency_tr` p50 ≤ 900 ms; RED preemption ≤ 300 ms; the Talker never waits on Backend Work.
G5 Records ingestion: ≥ 90 % of lab values extracted with correct LOINC+unit on the test corpus.
G6 Zero PHI incidents; DPIA v1 approved; consent opt-in ≥ 70 % for voice.
G7 Coverage: 100 % of booked branches served by an L1+ pack (cluster or deep) from P1; top-10 branches deep at L1/L2 by P2.
G8 Experience: CSAT ≥ 4.3, time-to-first-question ≤ 3 s, note ready ≤ 60 s after wrap-up; all tracked in the admin console.

## Engineering goals
E1 `make check` < 10 min in CI; flaky tests = 0 tolerated (quarantine + fix within 48 h).
E2 Every LLM/speech call traced with prompt/model/version; reproducible sessions via protocol hash.
E3 Provider or voice-profile swap (STT/TTS/LLM/S2S) is a config change, proven by contract tests per adapter and profile-parity simulator runs.
E4 New specialty pack authored by a clinician in YAML, compiled and tested without engineering help; L0 drafts for every branch regenerate from the taxonomy in one command.
E5 Every model/service on the PHI path self-hostable and probed; the release gate enforces it.
E6 Learning proposals ship as PRs with evidence bundles and pass through clinician approval and canary — never as silent changes.
E7 Security & reliability: zero PHI in telemetry (scan pass 100 %); vulnerability SLAs met (critical 72 h / high 7 d); SLO attainment reported monthly; MTTR < 4 h; restore drill each quarter; pen-test before pilot with findings closed.

## Delivery goals (how we ship — enforced, not aspirational)
D1 One issue at a time, in order; every merged PR maps to exactly one issue with recorded red→green evidence.
D2 Nothing merged with placeholders, skipped tests, demo stubs or silently reduced scope; `no_placeholders` and `evidence_check` gates stay green on every PR.
D3 Blocked ≠ done: vendor/GPU/human-gated issues close only with live-smoke / on-hardware / sign-off evidence; blockers are listed for the human, never worked around.
D4 Legal and regulatory artefacts (INT-210…INT-227) ship as issues with the same rigor — the tenant gate (INT-250) refuses go-live without them.
D5 Docs move with code: blueprint files, CLAUDE.md pointers, runbooks and the metrics catalogue are updated in the same PR that changes behavior.

## Anti-goals
Not a symptom checker that diagnoses. Not an AI scribe competing in Epic shops. Not storing voice. Not a chatbot that chats — it collects, structures, routes.
```

### 3.3 `docs/DoD.md`
```markdown
# Definition of Done (per issue == per PR; enforced by PR template + CI gates)
- [ ] PR maps to exactly one issue (`INT-xxx:` title, `Closes #n`); branch `int-<n>-<slug>`; squash merge only.
- [ ] docs/evidence/INT-xxx.md exists with: red run (failing tests before implementation), green run, `make check` + `make safety` + `make security` outputs, coverage delta, and — where labelled — live-smoke/on-hardware output or the named human's sign-off note.
- [ ] Zero placeholders: `no_placeholders` gate green; no skipped/xfail tests; no mocks outside tests; acceptance criteria met verbatim (quoted in the evidence file with a check per line).
- [ ] Failing test written first; all tests pass locally and in CI; coverage thresholds met or raised.
- [ ] `make check` and `make safety` green.
- [ ] Types clean (mypy --strict / tsc --noEmit); lint clean.
- [ ] Public interfaces documented (docstrings + OpenAPI); generated TS types updated if schemas changed.
- [ ] `tr` and `en` strings added; Turkish clinical copy marked for clinician review if patient-facing.
- [ ] Security: no PHI in logs; inputs validated; consent scope checked on new data access paths; secrets from OpenBao only; identifiers tokenized; new external call passes the egress allow-list and de-identification; `make security` green; the feature's row in docs/blueprint/10 §9 exists or is updated.
- [ ] Safety: no change to triage semantics unless ADR + clinician sign-off; PolicyGuard suite passes.
- [ ] Observability: new flows emit catalogued metrics + traces; errors carry ids not payloads; new service implements `/healthz` `/readyz` `/metrics` `/version`, declares SLOs and has a probe; dashboard panel + alert rule added when a new SLO or critical path is introduced.
- [ ] Legal: the issue's `legal:` codes re-read in docs/blueprint/06 §1; new personal-data fields annotated for the inventory; consent scopes declared on new routes; legal strings only from docs/legal/strings.yaml; device-boundary check when the feature touches triage/instruments.
- [ ] Docs: PROGRESS.md entry; issues.yaml status + GitHub issue updated; blueprint/docs touched by the change updated in the same PR; ADR if architecture changed; CHANGELOG line.
- [ ] Demo: task's acceptance can be shown via a command or a simulator scenario (`make demo-<id>`).
- [ ] Accessibility (UI tasks): labels, contrast, large-text checked.
- [ ] No new external dependency without license check (Apache/MIT/BSD preferred) and pinning.
```

### 3.4 `docs/TDD.md`
```markdown
# TDD & test strategy
## Pyramid
1. Unit (pytest/vitest): pure logic — slot schemas, mappers, rule evaluator, compiler, reducers, components.
2. Contract: adapter interfaces (STT/TTS/LLM/connectors) against recorded fixtures; OpenAPI schema tests (schemathesis) for the API.
3. Golden: protocol resolution → expected Questionnaire/OPT/slot schema snapshots; triage cases (≥200) → expected level + rule ids; note renderers → snapshot PDFs/HTML (text-diffed).
4. Simulation: LLM patient simulator (recorded in CI, live nightly) → rubric: must-ask coverage, safety, tone, one-question-per-turn.
5. Integration: docker compose up (api+db+redis+ehrbase+hapi+minio) → session lifecycle with Mock adapters.
6. E2E (P1+): Maestro flows on iOS simulator for onboarding → typed intake → review → share.
8. Console & learning: contract tests for `/admin/*` with role matrices; `metrics_catalog` completeness test; probe registry test; `proposal_scope`, `k_anonymity`, `canary_rollback`, `overlay_monotonicity`, `learned_fact_provenance`, `taxonomy_coverage` (docs/blueprint/09 §6).
7. Runtime simulation (fake clocks, mock adapters): the voice-runtime invariants in docs/blueprint/03 §4.6 — non-blocking Talker, six-tool surface, RED-only preemption ≤ 300 ms, FIFO + single in-flight + serialised writes, idempotent insertion-window delivery, verbatim scripted text, profile parity (`typed`, `cascade_fast`, `residency_tr`; `s2s_cloud` only behind the eval gate).

## Rules
- Tests-first is auditable: the evidence file quotes the red run. A PR whose tests could not have failed (assert True, tautologies) is rejected by test-writer review.
- No skipped, xfail, quarantined-forever or commented tests. A flaky test is fixed or deleted-with-ADR within 48 h.
- Real integrations are tested three ways: unit (pure), contract (recorded fixtures, in CI), live smoke (`make live-smoke`, only with keys, output stored as evidence). An adapter issue is not done on fixtures alone when labelled live-smoke.
- Red/green/refactor; commit the red test first when practical.
- Tests are deterministic: freeze time, seed randomness, record network (vcrpy / msw).
- Fixtures: `tests/fixtures/audio/tr/*.wav` (synthetic/consented), `tests/fixtures/transcripts/*.json`, `tests/fixtures/docs/*.pdf` (synthetic Turkish lab reports), `tests/fixtures/fhir/*.json`.
- Property tests (hypothesis) for mappers (round-trip) and rule evaluator (monotonicity: adding rules never lowers level).
- Mutation testing (mutmut) on triage evaluator before P1 exit.
- Flaky → quarantine label + issue + fix within 48 h.

## Safety suite (`make safety`)
- triage_goldens: all RED goldens → RED; all GREEN goldens → not RED; YELLOW within tolerance.
- policyguard_suite: corpus of forbidden patient-facing phrasings (tr/en) must be blocked; allowed phrasings pass.
- audio_retention_guard: static scan + runtime fake-fs test proving no audio write paths.
- consent_guard: every clinical read endpoint has a consent check (AST/route-table scan + tests).
- runtime_invariants: RT-01…RT-08 scenarios from docs/blueprint/04 §6 run on the latency harness; any regression in preemption latency, tool surface, or delivery idempotency fails the build.
- adversarial_suite: RT-09…RT-14 (injection by speech/document, triage manipulation, proxy impersonation, spoken TC Kimlik, vendor failover) pass in typed and mock voice profiles.

## Security & monitoring suite (`make security`, runs in CI on every PR)
- gitleaks · Semgrep (+ Bandit) · ESLint security · Trivy fs/image/IaC + OSV-Scanner (fail on critical/high) · Checkov · license allow-list · Syft SBOM attached · cosign signing + provenance on release builds · schemathesis fuzz · MobSF on mobile builds (P1) · PHI-pattern scan on fixtures/logs · `metrics_catalog` completeness · `health_contract` test (every service has the four endpoints and a probe) · `audit_chain` verifier test · `tokenization_roundtrip` + `envelope_encryption` tests · `egress_allowlist` test (a call to an unlisted host is refused and logged) · `deid_leak_rate` test (< 0.1 % on the synthetic corpus).
```

### 3.5 `LOOP.md`
```markdown
# LOOP — autonomous iteration protocol (one issue → one PR per run)
Inputs read every iteration: CLAUDE.md, docs/backlog/issues.yaml, docs/backlog/blockers.md, docs/PROGRESS.md (last 5 entries), docs/adr/ (titles), open PRs (`gh pr list`).
1. Select: first issue in file order (phase P0→P3) with `status: todo`, all `depends_on` done, and no `blocked:*` label. If none todo and no open PRs → `LOOP_STATUS: DONE`; if only blocked/awaiting-human remain → `LOOP_STATUS: WAITING_HUMAN` with the list.
2. Mark `status: doing`; `gh issue edit` → In progress; branch `int-<n>-<slug>`.
3. Restate the acceptance criteria verbatim in the PROGRESS entry; write the test plan; create docs/evidence/INT-xxx.md.
4. TDD: write failing tests → record red run in evidence → implement minimally → record green run → refactor → `make check` → `make safety` (clinical/triage/policy paths) → `make security`.
5. Update every doc the change touches (blueprint file sections, runbooks, metrics catalogue, legal annotations). Update issues.yaml `status: done` + `evidence:` path.
6. Commit (Conventional Commits, scoped to the issue). Push. `gh pr create` with the template filled (issue link, 10 §9 row, legal codes, evidence).
7. Merge policy: if all gates green **and** the issue has no `approval:human-*`, `live-smoke` or `gpu` label → `gh pr merge --squash`; close the issue. If it has such a label and the non-human parts are green → leave the PR open, set `status: awaiting-human`, append the ask to docs/backlog/blockers.md, and continue with the next issue.
8. Append PROGRESS entry. Print `LOOP_STATUS: CONTINUE`.
Blocked: two honest attempts failing, or a missing key/hardware/decision → label the GitHub issue `blocked:<what>`, write blockers.md, `status: blocked`, continue with the next issue (do not stop the loop for one blocker); stop only when nothing is workable.
Never: close an issue on mocks, weaken a gate, skip a test, reduce acceptance, or batch issues into one PR.
Guardrails: never edit CLAUDE.md, LOOP.md, DoD.md, coverage thresholds, red-flag semantics, the Talker tool list, CI security gates, or `packages/platform/{health,security}` contracts inside the loop; never delete tests; never skip `make safety` or `make security`; never touch `.env` or OpenBao policies; never run destructive git commands.

## PROGRESS entry template
### <ISO datetime> · <task id> · <status>
- Goal:
- Plan:
- Tests added:
- Result (`make check` / `make safety` output summary):
- Decisions / ADRs:
- Next:
- LOOP_STATUS: CONTINUE|DONE|BLOCKED
```

### 3.6 `PROMPT.md` (the per-iteration prompt used by loop.sh)
```markdown
You are running one iteration of LOOP.md in the INTAKE repo. Read CLAUDE.md, LOOP.md, docs/backlog/issues.yaml, docs/backlog/blockers.md and the last 5 entries of docs/PROGRESS.md. Execute exactly one issue following LOOP.md steps 1–8 with strict TDD, evidence file, and the issue→PR→merge policy. Respect every invariant in CLAUDE.md. Do not ask questions; if a human decision is required, mark the task blocked with a precise question and stop. Finish by appending the PROGRESS entry and printing LOOP_STATUS.
```

### 3.7 `loop.sh`
```bash
#!/usr/bin/env bash
# Run inside a devcontainer/VM — this bypasses permission prompts. Verify flags with `claude --help` first.
set -euo pipefail
MAX="${1:-5}"
for i in $(seq 1 "$MAX"); do
  echo "=== INTAKE LOOP $i/$MAX $(date -Iseconds) ==="
  claude -p "$(cat PROMPT.md)" --dangerously-skip-permissions --max-turns 80 --output-format text || true
  if grep -q "LOOP_STATUS: DONE" <(tail -n 30 docs/PROGRESS.md); then echo "Backlog complete."; exit 0; fi
  if grep -q "LOOP_STATUS: WAITING_HUMAN" <(tail -n 30 docs/PROGRESS.md); then echo "Only human-gated work remains — see docs/backlog/blockers.md and open PRs."; exit 3; fi
  if grep -q "LOOP_STATUS: BLOCKED" <(tail -n 30 docs/PROGRESS.md); then echo "Blocked — human input needed."; exit 2; fi
done
```
Safer alternative (no permission bypass): `claude -p "$(cat PROMPT.md)" --allowedTools "Read,Edit,Write,Bash(make *),Bash(pnpm *),Bash(uv *),Bash(git *),Bash(pytest *)"`.

### 3.8 `.claude/settings.json`
```json
{
  "permissions": {
    "allow": ["Bash(make *)", "Bash(pnpm *)", "Bash(npx expo *)", "Bash(uv *)", "Bash(pytest *)", "Bash(git status*)", "Bash(git add *)", "Bash(git commit *)", "Bash(git checkout *)", "Bash(git switch *)", "Bash(git push*)", "Bash(git branch*)", "Bash(gh issue *)", "Bash(gh pr *)", "Bash(gh label *)", "Bash(gh project *)", "Bash(docker compose *)", "Read", "Edit", "Write", "Grep", "Glob"],
    "deny": ["Bash(rm -rf *)", "Bash(git push --force*)", "Bash(git reset --hard*)", "Read(./.env)", "Edit(./.env)", "Write(./.env)"]
  },
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "scripts/hooks/guard-bash.sh"}]},
      {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "scripts/hooks/guard-protected-files.sh"}]}
    ],
    "PostToolUse": [
      {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "scripts/hooks/format-changed.sh"}]}
    ],
    "Stop": [
      {"matcher": "", "hooks": [{"type": "command", "command": "scripts/hooks/assert-progress-entry.sh"}]}
    ]
  }
}
```
`guard-bash.sh`: block `rm -rf`, `git push --force`, `curl|sh`, writes to `.env`. `guard-protected-files.sh`: block edits to `CLAUDE.md`, `LOOP.md`, `docs/DoD.md`, `packages/protocols/base/red_flags.yaml`, `services/voice-runtime/talker/tools.py` (the six-tool registry), `.github/workflows/security.yml`, `infra/security/egress-allowlist.yaml`, `packages/platform/security/**`, coverage config unless `ALLOW_PROTECTED=1`. `format-changed.sh`: run ruff/prettier on changed files. `assert-progress-entry.sh`: warn if PROGRESS.md not updated in this session (non-blocking). Hooks read tool input from stdin JSON; exit 2 to block.

### 3.9 `.claude/commands/` (slash commands)
- `next-issue.md`: "Run one LOOP.md iteration now (issue → PR)."
- `issue-start.md`: "For $ARGUMENTS: restate acceptance verbatim, write the test plan and the failing tests, create docs/evidence/$ARGUMENTS.md with the red run. Do not implement yet."
- `pr-open.md`: "Fill the PR template for the current branch: issue link, DoD, 10 §9 row, legal codes, evidence path; gh pr create."
- `legal-review.md`: "Check the diff against docs/blueprint/06: consent scopes on new routes, inventory annotations, legal strings from docs/legal/strings.yaml, device_functions boundary, transfer/egress implications. Output findings with file:line and the 06 §1 codes."
- `backlog-status.md`: "Print phase progress, open PRs awaiting humans, blockers, and the next 5 issues."
- `ship.md`: "Run make check && make safety; update CHANGELOG; commit; open PR with DoD checklist."
- `clinical-review.md`: "Review the diff under packages/protocols/** against docs/blueprint/04_CLINICAL_PROTOCOLS.md: instrument fidelity, monotonic red flags, B1 Turkish, golden tests. Output a review table."
- `security-review.md`: "Scan the diff for PHI in logs, missing consent checks, audio persistence, secrets. Output findings with file:line."
- `new-pack.md`: "Scaffold a specialty protocol pack YAML with sections/slots/red_flags/overlays/voice hints + golden test skeleton for $ARGUMENTS."
- `threat-model.md`: "Update docs/security/threat-model.md (STRIDE + LINDDUN) for $ARGUMENTS: new assets, entry points, threats, controls, and the docs/blueprint/10 §9 row; list the tests that prove each control."
- `slo.md`: "Define or update docs/slo/$ARGUMENTS.yaml (SLIs, targets, burn-rate alert rules, dashboard panel, runbook link) and register the synthetic probe."
- `runtime-review.md`: "Review the diff under services/voice-runtime/** against docs/blueprint/03 §4.6 and the qwen-audio-agent checklist: can the Talker still converse while Work is queued? did any Talker API learn about Work internals? is anything spoken before a Work is completed? can interruption postpone speech without cancelling Work? Output a pass/fail table."

### 3.10 `.claude/agents/` (subagents, YAML frontmatter + body)
- `clinical-reviewer`: description "Use after any change in packages/protocols or patient-facing copy"; tools Read, Grep, Glob; body = checklist from 04_CLINICAL_PROTOCOLS + PolicyGuard rules.
- `security-reviewer`: description "Use before every PR"; tools Read, Grep, Glob, Bash(make safety), Bash(make security); body = CLAUDE.md invariants 3–6 and 13–16 + OWASP ASVS 5.0 L2 + MASVS 2.x + OWASP LLM Top 10 2025 mapping from docs/blueprint/10 §5 + the 10 §9 row check.
- `sre-reviewer`: description "Use when adding a service, endpoint, queue, model or vendor"; tools Read, Grep, Glob, Bash(make slo-report); body = monitoring contract (10 §6), SLO/alert/probe/runbook checklist, capacity notes.
- `runtime-reviewer`: description "Use after any change under services/voice-runtime"; tools Read, Grep, Glob, Bash(make runtime-sim *); body = invariants 9–10 + docs/blueprint/03 §4.6 checklist.
- `test-writer`: description "Use at the start of each issue to draft failing tests"; tools Read, Write, Edit; body = docs/TDD.md pyramid + fixture conventions + tautology check (a test that cannot fail is rejected).
- `legal-reviewer`: description "Use on every PR touching data, consent, sharing, vendors, notifications, minors, triage or store artefacts"; tools Read, Grep, Glob; body = docs/blueprint/06 §1 statutory map + §7 fixed strings + the issue's legal codes; blocks when an obligation lacks its test.
- `qa-gatekeeper`: description "Use before every merge"; tools Read, Grep, Glob, Bash(scripts/ci/no_placeholders.sh), Bash(scripts/ci/evidence_check.sh); body = DoD checklist; hunts placeholders, skipped tests, unmet acceptance lines, missing evidence.

### 3.11 `docs/backlog/` — the complete issue backlog (every feature, P0→P3; source of the GitHub issues)
Write `docs/backlog/issues.yaml` **verbatim** with the content below (schema test in INT-004 validates it), plus `docs/backlog/blockers.md` (empty template) and `docs/backlog/epics.yaml` (id → one-line charter from the epic names). `scripts/backlog/sync_issues.py` pushes it to GitHub (issues, labels `ph:* area:* risk:* approval:* blocked:* live-smoke gpu`, milestones P0–P3, project board). The human-readable rendering is `docs/blueprint/11_ISSUE_BACKLOG.md` — regenerate whenever issues.yaml changes (a test diffs them).

```yaml
# docs/backlog/issues.yaml — the complete backlog. One issue == one PR. Order == delivery order within a phase.
# labels: ph:*, area:*, risk:*, approval:human-* (PR left open for the human), live-smoke (vendor evidence required), gpu (target-hardware evidence required)
- id: INT-001
  epic: E00-governance
  phase: P0
  title: "Monorepo bootstrap: workspaces, Makefile, pre-commit, compose.dev"
  depends_on: []
  labels: [area:platform]
  status: todo
  acceptance:
    - "pnpm>=9 + uv workspaces per 07 §2 layout; `make setup` from a clean clone on macOS"
    - "`make check` = ruff + mypy --strict + pytest + eslint + tsc + vitest across all packages"
    - "docker-compose.dev.yml: postgres16+pgvector, redis, ehrbase, hapi, minio; `make dev` healthy with real containers (no stub services)"
    - "pre-commit: gitleaks, semgrep, ruff, eslint; Conventional Commits enforced by commitlint"
  tests: [tests/smoke/test_make_check.py, scripts/ci/assert_no_vendor_calls.sh]
  legal: "KVKK-12"
  sec_row: "platform"
- id: INT-002
  epic: E00-governance
  phase: P0
  title: "CI base + zero-placeholder and evidence gates"
  depends_on: [INT-001]
  labels: [area:ci]
  status: todo
  acceptance:
    - "ci.yml runs make check on every PR with caching and no vendor network"
    - "scripts/ci/no_placeholders.sh fails on TODO|FIXME|XXX|NotImplementedError|pytest.mark.skip|xfail|it.skip|test.todo|`pass  #`|lorem|placeholder|dummy|demo-only outside tests/fixtures allow-list"
    - "scripts/ci/evidence_check.sh: PR must contain docs/evidence/<ISSUE>.md with red-run + green-run + gate outputs; PR title must be `INT-xxx: ...` and body must contain `Closes #<n>`"
    - "coverage thresholds enforced (py>=90 pkg-core, ts>=85) and may only rise"
  tests: [tests/ci/test_no_placeholders.py, tests/ci/test_evidence_check.py]
  sec_row: "cicd"
- id: INT-003
  epic: E00-governance
  phase: P0
  title: "ADR-000..020 written; blueprint mirrored to docs/blueprint"
  depends_on: [INT-001]
  labels: [area:docs]
  status: todo
  acceptance:
    - "docs/adr/ has ADR-000 template and 001..020 Accepted, one paragraph each (list in 07 §3.12)"
    - "docs/blueprint/ contains files 01..11 verbatim; docs/index.md links everything"
  tests: [tests/docs/test_adr_index.py]
- id: INT-004
  epic: E00-governance
  phase: P0
  title: "Backlog machinery: issues.yaml -> GitHub issues/labels/milestones/project; loop runner"
  depends_on: [INT-002]
  labels: [area:ci]
  status: todo
  acceptance:
    - "docs/backlog/issues.yaml (this backlog) validated by schema test; scripts/backlog/sync_issues.py creates/updates GitHub issues via gh with labels ph:*, area:*, risk:*, approval:*, milestones P0..P3 and a Project board Backlog/Ready/In progress/In review/Blocked/Done"
    - ".github/ISSUE_TEMPLATE/feature.yml + pull_request_template.md with the DoD checklist and mandatory links (issue, 10 §9 row, 06 legal codes, evidence file)"
    - "loop.sh implements LOOP.md: pick next Ready issue by order with deps done and no blocked label; branch int-<n>-<slug>; on gates green open PR via gh; auto-merge squash only when no approval:human-* label; else leave open and continue"
    - "docs/backlog/blockers.md format + `make backlog-status` report"
  tests: [tests/backlog/test_schema.py, tests/backlog/test_sync_dryrun.py]
- id: INT-010
  epic: E01-platform
  phase: P0
  title: "packages/platform/health: /healthz /readyz /metrics /version + contract test"
  depends_on: [INT-001]
  labels: [area:platform]
  status: todo
  acceptance:
    - "mount_health(app, readiness=[...]) for FastAPI, workers, voice-runtime; /version returns git_sha, built_at, sbom_digest"
    - "health_contract test enumerates every service in the repo and fails on a missing endpoint or missing probe registration"
  tests: [tests/platform/test_health_contract.py]
  sec_row: "monitoring-contract"
- id: INT-011
  epic: E01-platform
  phase: P0
  title: "packages/platform/otel: shared tracing/metrics/logs + PII redaction processor"
  depends_on: [INT-010]
  labels: [area:platform]
  status: todo
  acceptance:
    - "propagates trace_id, hashed session_id, tenant_id, protocol_hash, prompt_version; JSON logs; no-PHI invariant"
    - "OTel collector config with redaction (TCKN checksum regex, 05x phone, IBAN, names allow-list) unit-tested on fixture logs"
  tests: [tests/platform/test_redaction.py]
  legal: "KVKK-12"
  sec_row: "observability-pipeline"
- id: INT-012
  epic: E01-platform
  phase: P0
  title: "packages/platform/security: headers, rate limiter, idempotency keys"
  depends_on: [INT-010]
  labels: [area:security]
  status: todo
  acceptance:
    - "security headers middleware (CSP, HSTS, nosniff, frame-deny); Redis token-bucket limiter per user/IP/tenant with tests; idempotency-key middleware for POSTs"
  tests: [tests/platform/test_rate_limit.py, tests/platform/test_idempotency.py]
  legal: "KVKK-12"
  sec_row: "api"
- id: INT-013
  epic: E01-platform
  phase: P0
  title: "Tokenization service + identity vault (TCKN/phone never in clear)"
  depends_on: [INT-012, INT-017]
  labels: [area:security, risk:security]
  status: todo
  acceptance:
    - "HMAC-SHA-256 keyed pseudonym for joins; encrypted value in identity_vault readable only by the tokenization role; logs get pseudonym[:8]"
    - "roundtrip + key-rotation tests; grep-test proves no app table stores raw TCKN/phone"
  tests: [tests/security/test_tokenization_roundtrip.py]
  legal: "KVKK-6,KVKK-12,2018-10"
  sec_row: "identifiers"
- id: INT-014
  epic: E01-platform
  phase: P0
  title: "Envelope encryption (OpenBao Transit) + rotation + crypto-shredding"
  depends_on: [INT-017]
  labels: [area:security, risk:security]
  status: todo
  acceptance:
    - "AES-256-GCM per-field with per-tenant DEKs wrapped by OpenBao Transit; file-KEK provider for tests; rewrap rotation; destroy-key == hard delete"
    - "tamper detection test; rotation test; crypto-shred proves ciphertext unrecoverable"
  tests: [tests/security/test_envelope_encryption.py]
  legal: "KVKK-7,KVKK-12,2018-10"
  sec_row: "data-at-rest"
- id: INT-015
  epic: E01-platform
  phase: P0
  title: "De-identification service: Presidio + Turkish recognizers + leak-rate corpus"
  depends_on: [INT-011]
  labels: [area:security, risk:security]
  status: todo
  acceptance:
    - "recognizers: TCKN (checksum), TR phone, IBAN, names (TR NER), addresses, date shifting; sits in front of every cloud model call and Loop-2 exports"
    - "synthetic corpus with labels; measured leak rate < 0.1 percent gate in CI"
  tests: [tests/security/test_deid_leak_rate.py]
  legal: "KVKK-9,KVKK-16"
  sec_row: "cloud-boundary"
- id: INT-016
  epic: E01-platform
  phase: P0
  title: "Hash-chained audit log + WORM export + daily verifier"
  depends_on: [INT-014]
  labels: [area:security]
  status: todo
  acceptance:
    - "audit.v1 events chained (prev-hash), verifier job, MinIO object-lock bucket copy; patient-visible access-log view model"
    - "tamper test flips one row and the verifier detects it"
  tests: [tests/security/test_audit_chain.py]
  legal: "KVKK-12,KSVY-7"
  sec_row: "audit"
- id: INT-017
  epic: E01-platform
  phase: P0
  title: "OpenBao dev server + per-service policies + dynamic DB creds"
  depends_on: [INT-001]
  labels: [area:security]
  status: todo
  acceptance:
    - "compose service; api/workers/voice-runtime read secrets from OpenBao; .env holds only address/token in dev; dynamic Postgres creds TTL 24h"
    - "test proves a service boots with OpenBao and fails closed without it in prod mode"
  tests: [tests/security/test_openbao_wiring.py]
  legal: "KVKK-12,2018-10"
  sec_row: "secrets"
- id: INT-018
  epic: E01-platform
  phase: P0
  title: "Egress proxy with vendor allow-list + transfer log"
  depends_on: [INT-001]
  labels: [area:security, risk:legal]
  status: todo
  acceptance:
    - "forward proxy in dev compose; only allow-listed vendor hosts reachable from PHI-path services; every egress logged {host,purpose,bytes,ts} feeding the vendor-transfer register; denial emits sec.egress_denied"
    - "test: call to unlisted host is refused and logged"
  tests: [tests/security/test_egress_allowlist.py]
  legal: "KVKK-9,TRANSFER-2024"
  sec_row: "cloud-boundary"
- id: INT-019
  epic: E01-platform
  phase: P0
  title: "security.yml CI job: full gate set + signing"
  depends_on: [INT-002]
  labels: [area:ci, risk:security]
  status: todo
  acceptance:
    - "gitleaks, semgrep+bandit, eslint-security, trivy fs/image/IaC + osv-scanner fail on critical/high, checkov, license allow-list (AGPL flagged), syft SBOM artifact, cosign keyless signing + SLSA provenance for images and protocol bundles on tags, schemathesis fuzz, PHI-pattern scan of fixtures"
    - "`make security` runs the same list locally; planted secret, planted critical CVE and planted PHI each fail (proved in evidence, then reverted)"
  tests: [tests/ci/test_security_gates.py]
  legal: "KVKK-12,2018-10"
  sec_row: "cicd"
- id: INT-020
  epic: E01-platform
  phase: P0
  title: "Threat model + incident runbook + PR linkage"
  depends_on: [INT-003]
  labels: [area:security, risk:legal]
  status: todo
  acceptance:
    - "docs/security/threat-model.md STRIDE+LINDDUN seeded from 10 §9; docs/security/incident-runbook.md includes KVKK Board 72h form flow (2019/10), data-subject notice templates, USOM/Siber Guvenlik Baskanligi report per 7545, hospital DPA notice"
    - "PR template requires the 10 §9 row link; missing link fails evidence_check"
  tests: [tests/docs/test_threat_model_rows.py]
  legal: "KVKK-12-breach,7545"
  sec_row: "incident-response"
- id: INT-021
  epic: E01-platform
  phase: P0
  title: "SLO files + Prometheus rules + Grafana dashboards as code + runbooks"
  depends_on: [INT-011]
  labels: [area:observability]
  status: todo
  acceptance:
    - "docs/slo/{api,voice-runtime,workers}.yaml with SLIs/objectives/burn-rate alerts (14.4x/1h, 6x/6h page; 1x/3d ticket); generator emits Prometheus rules; golden-signal dashboards provisioned; runbook per alert"
  tests: [tests/observability/test_slo_generator.py]
  sec_row: "monitoring-contract"
- id: INT-022
  epic: E01-platform
  phase: P0
  title: "services/probes: synthetic checks + self-hosting registry + release gate"
  depends_on: [INT-010, INT-021]
  labels: [area:observability]
  status: todo
  acceptance:
    - "registry table {component,self_hostable,self_hosted_now,host,license,probe,budget_ms,fallback,phi_path}; 60s runner with real dev checks (DB, Redis, MinIO, EHRbase, HAPI, OpenBao seal, LiveKit room join, cert expiry, backup freshness)"
    - "release-gate script blocks when an enabled phi_path component lacks a healthy self-hosted fallback"
  tests: [tests/observability/test_probe_registry.py, tests/observability/test_release_gate.py]
  legal: "G2019-12"
  sec_row: "self-hosting"
- id: INT-023
  epic: E01-platform
  phase: P0
  title: "Observability stack profile: OTel+Prom+Loki+Tempo+Grafana (or SigNoz), Unleash, Keycloak, GlitchTip"
  depends_on: [INT-011]
  labels: [area:observability]
  status: todo
  acceptance:
    - "compose profile obs; flags via OpenFeature with in-memory provider default and Unleash provider behind config; Keycloak realm export for dev; GlitchTip DSN wired behind flag with PHI-scrub tests"
  tests: [tests/observability/test_flags_provider.py]
  sec_row: "observability-pipeline"
- id: INT-024
  epic: E01-platform
  phase: P0
  title: "k6 smoke + lk load-test recipe + chaos harness (vendor kill -> typed <=2s)"
  depends_on: [INT-022]
  labels: [area:observability]
  status: todo
  acceptance:
    - "k6 API smoke in CI (staging profile); documented lk load-test recipe; chaos harness kills a mock vendor adapter and asserts typed fallback within 2s and metrics emitted"
  tests: [tests/chaos/test_vendor_kill_fallback.py]
  sec_row: "resilience"
- id: INT-025
  epic: E01-platform
  phase: P0
  title: "Metrics catalogue as code + completeness test"
  depends_on: [INT-011]
  labels: [area:observability]
  status: todo
  acceptance:
    - "packages/clinical-schemas/metrics_catalog.yaml holds every id/unit/target/owner from 08 §4; emitting an uncatalogued metric fails make check (proved then reverted in evidence)"
  tests: [tests/observability/test_metrics_catalog.py]
  sec_row: "monitoring-contract"
- id: INT-030
  epic: E02-data
  phase: P0
  title: "Postgres schema + Alembic + RLS per tenant + pgaudit"
  depends_on: [INT-013, INT-014]
  labels: [area:data]
  status: todo
  acceptance:
    - "core tables (patients pseudonymised, sessions, slots, notes, consents, shares, documents, events) with RLS by tenant and role; pgaudit on; least-privilege roles"
    - "RLS tests prove tenant A cannot read tenant B even with SQL"
  tests: [tests/data/test_rls.py]
  legal: "KVKK-12,KSVY-7"
  sec_row: "data-at-rest"
- id: INT-031
  epic: E02-data
  phase: P0
  title: "clinical-schemas: pydantic models + TS codegen + event schemas"
  depends_on: [INT-030]
  labels: [area:data]
  status: todo
  acceptance:
    - "PreVisitNote, PatientSummary, ExtractedRecordItem, ConsentScope, TriageResult, SessionState, PatientOverlay, ObserverState, Proposal; events csat.v1, nps.v1, clinician_pulse.v1, audit.v1, security.v1; TS generated from OpenAPI"
  tests: [tests/schemas/test_roundtrip.py]
- id: INT-032
  epic: E02-data
  phase: P0
  title: "EHRbase canonical store: OPT templates + client + roundtrip"
  depends_on: [INT-031]
  labels: [area:data]
  status: todo
  acceptance:
    - "intake composition template (OPT) uploaded on boot; write/read composition per session; contribution audit"
    - "integration test writes and reads a composition against EHRbase container"
  tests: [tests/integration/test_ehrbase_roundtrip.py]
  legal: "KSVY-5"
  sec_row: "clinical-core"
- id: INT-033
  epic: E02-data
  phase: P0
  title: "HAPI FHIR exchange: mappers internal<->R4 + validation"
  depends_on: [INT-031]
  labels: [area:data]
  status: todo
  acceptance:
    - "QuestionnaireResponse, Observation, Condition, MedicationStatement, AllergyIntolerance, RiskAssessment, Flag, Composition, Bundle; hypothesis roundtrip; Bundle validates on HAPI container"
  tests: [tests/integration/test_fhir_validation.py]
- id: INT-034
  epic: E02-data
  phase: P0
  title: "MinIO document store: signed URLs + AV hook + WORM audit bucket"
  depends_on: [INT-016]
  labels: [area:data]
  status: todo
  acceptance:
    - "short-TTL signed URLs; server-side encryption; object-lock on audit bucket; bucket policies least-privilege"
  tests: [tests/data/test_signed_urls.py]
  legal: "KVKK-12"
  sec_row: "documents"
- id: INT-035
  epic: E02-data
  phase: P0
  title: "Redis streams event bus + consumer framework + DLQ"
  depends_on: [INT-031]
  labels: [area:platform]
  status: todo
  acceptance:
    - "typed producers/consumers with retries, DLQ, exactly-once handlers via idempotency keys; consumer lag metric"
  tests: [tests/platform/test_event_bus.py]
- id: INT-036
  epic: E02-data
  phase: P0
  title: "Retention & destruction engine (policy as code, 6-month periodic destruction, logs)"
  depends_on: [INT-030]
  labels: [area:data, risk:legal]
  status: todo
  acceptance:
    - "policy file mirrors 06 §3 retention matrix; scheduled destruction runs at most every 6 months per DEST-2017; destruction log kept 3 years; lane windows zeroing verified; raw-audio guard extended"
    - "time-travel tests prove each class purges on schedule"
  tests: [tests/legal/test_retention_engine.py]
  legal: "KVKK-7,DEST-2017"
  sec_row: "retention"
- id: INT-037
  epic: E02-data
  phase: P0
  title: "DSAR endpoints: export (FHIR+PDF), delete (crypto-shred, 30-day grace), rectify + 30-day SLA tracker"
  depends_on: [INT-014, INT-033]
  labels: [area:data, risk:legal]
  status: todo
  acceptance:
    - "/export bundles openEHR+FHIR+PDF; /me delete schedules shred with grace and cancels shares; rectification writes audit; SLA clock per KVKK-13 with console queue"
  tests: [tests/legal/test_dsar_flows.py]
  legal: "KVKK-11,KVKK-13"
  sec_row: "dsar"
- id: INT-038
  epic: E02-data
  phase: P0
  title: "Consent service: versioned objects, consent_guard middleware, re-prompt on change"
  depends_on: [INT-030]
  labels: [area:data, risk:legal]
  status: todo
  acceptance:
    - "purposes exactly as 06 §4 (core, voice, wellbeing, lane:*, documents, learning:*, satisfaction, share:*, research); text_hash binds shown text; route-table scan test proves every data route declares scopes; withdrawal cascades within 1 min"
    - "consents are free, specific, informed, unbundled: UI cannot pre-tick, cannot gate core service on optional purposes (tests)"
  tests: [tests/legal/test_consent_guard.py, tests/legal/test_consent_unbundled.py]
  legal: "KVKK-5,KVKK-6,AYD-2018"
  sec_row: "consent"
- id: INT-040
  epic: E03-protocols
  phase: P0
  title: "Protocol DSL: schema, loader, validator (extends, monotonic red flags, voice fields)"
  depends_on: [INT-031]
  labels: [area:protocols]
  status: todo
  acceptance:
    - "yaml schema with sections/slots/red_flags/overlays/visit_types/voice fields; validator enforces monotonicity, follow_up_tr presence, instruments allow_paraphrase=false"
  tests: [tests/protocols/test_validator.py]
  sec_row: "protocol-registry"
- id: INT-041
  epic: E03-protocols
  phase: P0
  title: "Compiler: FHIR Questionnaire + openEHR bindings + Pydantic + TS + clip manifest, deterministic"
  depends_on: [INT-040, INT-033]
  labels: [area:protocols]
  status: todo
  acceptance:
    - "two runs produce identical hashes; resolved-protocol hash pinned per session; compile artifacts under packages/protocols/dist"
  tests: [tests/protocols/test_compiler_determinism.py]
- id: INT-042
  epic: E03-protocols
  phase: P0
  title: "Taxonomy: all MHRS branches + clusters + visit types + coverage CLI"
  depends_on: [INT-040]
  labels: [area:protocols]
  status: todo
  acceptance:
    - "taxonomy/branches.yaml seeded from 09 §1 with verify_live_list true; every branch resolves to a cluster; `protocols coverage` matrix; unknown booked branch fails a test"
  tests: [tests/protocols/test_taxonomy_coverage.py]
- id: INT-043
  epic: E03-protocols
  phase: P0
  title: "base.intake pack (tr/en) complete per 04 §1"
  depends_on: [INT-041]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "all base sections/slots/red-flag families/action scripts in B1 Turkish + English; goldens; clip-manifest entries"
  tests: [tests/protocols/goldens/base]
  legal: "HHY-15,1219-8"
  sec_row: "clinical-content"
- id: INT-044
  epic: E03-protocols
  phase: P0
  title: "Cluster pack: medical"
  depends_on: [INT-043]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "content per 04 §2.1 medical; goldens; compiles clean"
  tests: [tests/protocols/goldens/cluster_medical]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-045
  epic: E03-protocols
  phase: P0
  title: "Cluster pack: surgical"
  depends_on: [INT-043]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "content per 04 §2.1 surgical; goldens"
  tests: [tests/protocols/goldens/cluster_surgical]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-046
  epic: E03-protocols
  phase: P0
  title: "Cluster pack: sensory"
  depends_on: [INT-043]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "content per 04 §2.1 sensory; goldens"
  tests: [tests/protocols/goldens/cluster_sensory]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-047
  epic: E03-protocols
  phase: P0
  title: "Cluster pack: womens_health"
  depends_on: [INT-043]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "LMP-first ordering, pregnancy-aware asks; goldens"
  tests: [tests/protocols/goldens/cluster_womens]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-048
  epic: E03-protocols
  phase: P0
  title: "Cluster pack: child_health (guardian proxy, age bands)"
  depends_on: [INT-043, INT-133]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "guardian-proxy flow, age-banded items, adolescent private section semantics; goldens"
  tests: [tests/protocols/goldens/cluster_child]
  legal: "HHY-24,TMK-339"
  sec_row: "clinical-content"
- id: INT-049
  epic: E03-protocols
  phase: P0
  title: "Cluster pack: mental_health"
  depends_on: [INT-043]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "full instruments by default, C-SSRS path, safety scripts; goldens"
  tests: [tests/protocols/goldens/cluster_mental]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-050
  epic: E03-protocols
  phase: P0
  title: "Cluster pack: dental"
  depends_on: [INT-043]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "per 04 §2.1 dental incl. anticoagulant/bisphosphonate asks; goldens"
  tests: [tests/protocols/goldens/cluster_dental]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-051
  epic: E03-protocols
  phase: P0
  title: "Cluster pack: allied_and_reports"
  depends_on: [INT-043]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "report visit types, documents checklist, no wellbeing unless opted; goldens"
  tests: [tests/protocols/goldens/cluster_allied]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-052
  epic: E03-protocols
  phase: P0
  title: "Cluster excluded: Acil refusal + 112 routing copy"
  depends_on: [INT-043]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "app refuses pre-visit intake for Acil and shows fixed 112 guidance; test asserts refusal"
  tests: [tests/protocols/test_acil_refusal.py]
  legal: "1219-8"
  sec_row: "clinical-content"
- id: INT-053
  epic: E03-protocols
  phase: P0
  title: "Deep pack: internal_medicine"
  depends_on: [INT-044]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "per 04 §2.2; goldens; L1 after physician approval"
  tests: [tests/protocols/goldens/im]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-054
  epic: E03-protocols
  phase: P0
  title: "Deep pack: gastroenterology + overlay.oncology_patient"
  depends_on: [INT-044]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "per 04 §2.2 incl. rf.gi_bleed, rf.neutropenic_fever; goldens"
  tests: [tests/protocols/goldens/gastro]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-055
  epic: E03-protocols
  phase: P0
  title: "Deep pack: rheumatology"
  depends_on: [INT-044]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "per 04 §2.2 incl. HAQ-DI-TR (detailed), DMARD/biologic asks; goldens"
  tests: [tests/protocols/goldens/rheum]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-056
  epic: E03-protocols
  phase: P0
  title: "Patient overlays set (8) + overlay_monotonicity property test"
  depends_on: [INT-043]
  labels: [area:protocols, risk:clinical]
  status: todo
  acceptance:
    - "overlays per 04 §2.3 add/tighten only; property test across random compositions"
  tests: [tests/protocols/test_overlay_monotonicity.py]
  sec_row: "learning-loops"
- id: INT-057
  epic: E03-protocols
  phase: P0
  title: "Protocol Authoring Agent: L0 drafts for every branch + no-serve guard"
  depends_on: [INT-042]
  labels: [area:protocols]
  status: todo
  acceptance:
    - "`protocols generate-l0 --branch <id>` scaffolds from cluster+template with citation placeholders resolved to named Turkish guidance sources; L0 resolution for a live session raises; regeneration idempotent"
    - "agent has zero access to patient data (import-boundary test)"
  tests: [tests/protocols/test_l0_guard.py]
  sec_row: "learning-loops"
- id: INT-058
  epic: E03-protocols
  phase: P0
  title: "Signed protocol bundles: cosign sign + runtime verification + per-session hash pin"
  depends_on: [INT-041, INT-019]
  labels: [area:protocols, risk:security]
  status: todo
  acceptance:
    - "compiler emits bundle.tar.gz signed; runtime refuses unsigned/tampered; note meta shows protocol hash"
  tests: [tests/protocols/test_bundle_signature.py]
  sec_row: "protocol-registry"
- id: INT-059
  epic: E03-protocols
  phase: P0
  title: "Triage golden suite >=200 + mutation tests"
  depends_on: [INT-080]
  labels: [area:protocols, risk:clinical]
  status: todo
  acceptance:
    - "goldens across base+clusters+deep; a deliberately broken RED rule fails the suite (proved, reverted)"
  tests: [tests/safety/test_triage_goldens.py]
  sec_row: "triage"
- id: INT-060
  epic: E03-protocols
  phase: P0
  title: "Clip cache builder per voice + MinIO + coverage test"
  depends_on: [INT-041, INT-034]
  labels: [area:voice]
  status: todo
  acceptance:
    - "all scripted text pre-synthesised per voice at compile keyed sha256(text_tr,voice_id); mock TTS in CI; coverage report per pack"
  tests: [tests/voice/test_clip_manifest.py]
  sec_row: "voice-runtime"
- id: INT-061
  epic: E03-protocols
  phase: P2
  title: "Deep pack: cardiology"
  depends_on: [INT-044]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for cardiology per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/cardiology]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-062
  epic: E03-protocols
  phase: P2
  title: "Deep pack: neurology"
  depends_on: [INT-044]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for neurology per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/neurology]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-063
  epic: E03-protocols
  phase: P2
  title: "Deep pack: endocrinology"
  depends_on: [INT-044]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for endocrinology per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/endocrinology]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-064
  epic: E03-protocols
  phase: P2
  title: "Deep pack: urology"
  depends_on: [INT-045]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for urology per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/urology]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-065
  epic: E03-protocols
  phase: P2
  title: "Deep pack: ophthalmology"
  depends_on: [INT-046]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for ophthalmology per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/ophthalmology]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-066
  epic: E03-protocols
  phase: P2
  title: "Deep pack: ent"
  depends_on: [INT-046]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for ent per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/ent]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-067
  epic: E03-protocols
  phase: P2
  title: "Deep pack: orthopaedics"
  depends_on: [INT-045]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for orthopaedics per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/orthopaedics]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-068
  epic: E03-protocols
  phase: P2
  title: "Deep pack: dermatology"
  depends_on: [INT-044]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for dermatology per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/dermatology]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-069
  epic: E03-protocols
  phase: P2
  title: "Deep pack: obgyn"
  depends_on: [INT-047]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for obgyn per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/obgyn]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-070
  epic: E03-protocols
  phase: P2
  title: "Deep pack: paediatrics"
  depends_on: [INT-048]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for paediatrics per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/paediatrics]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-071
  epic: E03-protocols
  phase: P2
  title: "Deep pack: psychiatry"
  depends_on: [INT-049]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for psychiatry per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/psychiatry]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-072
  epic: E03-protocols
  phase: P2
  title: "Deep pack: oncology"
  depends_on: [INT-044]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for oncology per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/oncology]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-073
  epic: E03-protocols
  phase: P2
  title: "Deep pack: dentistry_general"
  depends_on: [INT-050]
  labels: [area:protocols, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "L1 pack for dentistry_general per 09 §2 maturity; goldens; clip coverage"
  tests: [tests/protocols/goldens/dentistry_general]
  legal: "HHY-15"
  sec_row: "clinical-content"
- id: INT-080
  epic: E04-engines
  phase: P0
  title: "Deterministic triage engine (levels, monotonic merge, action scripts)"
  depends_on: [INT-040]
  labels: [area:safety, risk:clinical]
  status: todo
  acceptance:
    - "rules only; LLM candidates cap at YELLOW_REVIEW and can never lower a level (type-level); action scripts verbatim"
  tests: [tests/safety/test_triage_engine.py]
  legal: "1219-8,TCY-R11"
  sec_row: "triage"
- id: INT-081
  epic: E04-engines
  phase: P0
  title: "IntakeEngine FSM: step kinds, ask-ahead/reconcile-behind, delta mode, overlays"
  depends_on: [INT-080, INT-056]
  labels: [area:engine]
  status: todo
  acceptance:
    - "no LLM inside; answered_pending + follow_up_tr semantics; delta mode driven by PatientOverlay; must_ask coverage computed"
  tests: [tests/engine/test_fsm.py]
  sec_row: "intake-typed"
- id: INT-082
  epic: E04-engines
  phase: P0
  title: "Patient simulator: personas + scenarios IM-01..IM-14 headless"
  depends_on: [INT-081]
  labels: [area:engine]
  status: todo
  acceptance:
    - "12+ scripted personas incl. proxy, low-literacy, crisis, oncology; runs in typed and mock voice; used by CI"
  tests: [tests/sim/test_scenarios.py]
- id: INT-083
  epic: E04-engines
  phase: P0
  title: "Extraction Work: schema-constrained LLM behind gateway + data boundary + eval set"
  depends_on: [INT-081, INT-015]
  labels: [area:ai]
  status: todo
  acceptance:
    - "transcripts wrapped as delimited data; output validated against slot schemas; recorded-fixture contract tests; Langfuse scores wiring (self-hosted)"
  tests: [tests/ai/test_extraction_contract.py]
  legal: "KVKK-9"
  sec_row: "llm-boundary"
- id: INT-084
  epic: E04-engines
  phase: P0
  title: "Note composer + renderers (SOAP, PDF watermark-ready, FHIR bundle) + provenance + disclaimer"
  depends_on: [INT-083, INT-033]
  labels: [area:engine, risk:legal]
  status: todo
  acceptance:
    - "every fact carries source span; fixed legal disclaimer text (06 §7 wording: hasta beyanina dayanir, hekim degerlendirmesinin yerine gecmez) rendered on note+PDF; golden note snapshots"
  tests: [tests/engine/test_note_golden.py]
  legal: "1219-8,HHY-15"
  sec_row: "notes"
- id: INT-085
  epic: E04-engines
  phase: P0
  title: "Patient summary (B1 Turkish) + reading-level check"
  depends_on: [INT-084]
  labels: [area:engine]
  status: todo
  acceptance:
    - "plain-language summary excludes wellbeing signals; readability metric gate"
  tests: [tests/engine/test_patient_summary.py]
  legal: "HHY-15"
- id: INT-090
  epic: E05-voice
  phase: P0
  title: "LiveKit server+TURN dev; per-session tokens (10-min minimal grants); audio_retention_guard"
  depends_on: [INT-001]
  labels: [area:voice, risk:security]
  status: todo
  acceptance:
    - "room tokens grant join+publish mic+subscribe agent only; rooms ephemeral; no recording features enabled; guard test proves no audio write paths anywhere"
  tests: [tests/voice/test_room_tokens.py, tests/voice/test_audio_retention_guard.py]
  legal: "USHY-12,KVKK-5"
  sec_row: "voice-runtime"
- id: INT-091
  epic: E05-voice
  phase: P0
  title: "Talker: six-tool registry + introspection test + streaming PolicyGuard + insertion-window scheduler + clip player"
  depends_on: [INT-060, INT-090]
  labels: [area:voice, risk:clinical]
  status: todo
  acceptance:
    - "exactly protocol_next, submit_utterance, get_work_status, request_repeat_or_clarify, patient_memory, respond_permission; adding a seventh fails introspection; PolicyGuard <=20ms per sentence"
  tests: [tests/voice/test_six_tools.py, tests/voice/test_policyguard_latency.py]
  sec_row: "voice-runtime"
- id: INT-092
  epic: E05-voice
  phase: P0
  title: "Backend Agent: FIFO Work queue, serialized SessionState, delivery semantics, idempotent"
  depends_on: [INT-081, INT-035]
  labels: [area:voice]
  status: todo
  acceptance:
    - "one Work in flight per session; results {inline,speech_tr,priority}; duplicates impossible (test)"
  tests: [tests/voice/test_work_queue.py]
  sec_row: "voice-runtime"
- id: INT-093
  epic: E05-voice
  phase: P0
  title: "RED preemption path: stop <=150ms, e2e <=300ms (fake clocks)"
  depends_on: [INT-091, INT-092, INT-080]
  labels: [area:voice, risk:clinical]
  status: todo
  acceptance:
    - "only rules-engine RED carries priority preempt; playback cancel and script start measured on fake clock"
  tests: [tests/voice/test_red_preemption.py]
  sec_row: "triage"
- id: INT-094
  epic: E05-voice
  phase: P0
  title: "Runtime invariants 1-11 + RT-01..08 + latency harness"
  depends_on: [INT-093, INT-110]
  labels: [area:voice]
  status: todo
  acceptance:
    - "all invariant tests incl. lanes-stalled-30s; harness reports per-turn budgets per profile"
  tests: [tests/voice/test_invariants.py]
  sec_row: "voice-runtime"
- id: INT-095
  epic: E05-voice
  phase: P1
  title: "Profile cascade_fast with real adapters (Soniox STT v5 tr, Soniox TTS v2 or ElevenLabs Flash, cached-prompt LLM) + live smoke"
  depends_on: [INT-094, INT-018]
  labels: [area:voice, approval:human-vendor, live-smoke]
  status: todo
  acceptance:
    - "real adapters with recorded-fixture contract tests; preemptive_generation on; `make live-smoke PROFILE=cascade_fast` runs one real turn when keys present and stores evidence (latency numbers) — issue closes only with that evidence"
    - "vendor calls pass egress allow-list and de-identification where text leaves"
  tests: [tests/voice/adapters/test_cascade_contracts.py]
  legal: "KVKK-9,TRANSFER-2024"
  sec_row: "voice-runtime"
- id: INT-096
  epic: E05-voice
  phase: P0
  title: "Profile typed (full parity fallback)"
  depends_on: [INT-081]
  labels: [area:voice]
  status: todo
  acceptance:
    - "entire intake completable typed; kill-switch target; parity simulator run"
  tests: [tests/voice/test_typed_parity.py]
  sec_row: "intake-typed"
- id: INT-097
  epic: E05-voice
  phase: P2
  title: "Profile residency_tr on GPU (Qwen3-ASR vLLM, Chatterbox v3/Piper, Qwen3-30B-A3B) + on-hardware latency evidence"
  depends_on: [INT-094]
  labels: [area:voice, approval:human-infra, gpu]
  status: todo
  acceptance:
    - "compose.residency GPU profile; adapters + contract tests; p50<=900ms dynamic measured on target hardware and recorded in evidence — not closable on laptop mocks"
  tests: [tests/voice/adapters/test_residency_contracts.py]
  legal: "G2019-12"
  sec_row: "voice-runtime"
- id: INT-098
  epic: E05-voice
  phase: P2
  title: "Profile s2s_cloud (GPT-Realtime-2 EU, Gemini Live Vertex EU) flag-gated + eval gate + PolicyGuard retraction"
  depends_on: [INT-094, INT-102]
  labels: [area:voice, approval:human-vendor, live-smoke]
  status: todo
  acceptance:
    - "off by default; enabling requires eval gate policy>=99 must-ask>=95 and 4-eyes; retraction path tested; DPIA addendum linked"
  tests: [tests/voice/adapters/test_s2s_gate.py]
  legal: "KVKK-9,TRANSFER-2024,DPIA"
  sec_row: "voice-runtime"
- id: INT-099
  epic: E05-voice
  phase: P1
  title: "Backchannels + ack styles + preemptive generation + per-profile NFR harness in CI"
  depends_on: [INT-095]
  labels: [area:voice]
  status: todo
  acceptance:
    - "A/B flag; NFR thresholds from 02 §8 asserted per profile with mock and recorded runs"
  tests: [tests/voice/test_nfr_harness.py]
- id: INT-100
  epic: E05-voice
  phase: P1
  title: "Vendor failover + circuit breakers + typed fallback <=2s + chaos test"
  depends_on: [INT-095, INT-024]
  labels: [area:voice]
  status: todo
  acceptance:
    - "breaker per vendor; failover order from probes registry; chaos kill proves <=2s"
  tests: [tests/chaos/test_vendor_failover.py]
  sec_row: "resilience"
- id: INT-101
  epic: E05-voice
  phase: P0
  title: "Session budgets + cost metering per component/profile"
  depends_on: [INT-092]
  labels: [area:voice]
  status: todo
  acceptance:
    - "token/char/audio-second budgets enforced; cost.per_session emitted; exhaustion degrades gracefully"
  tests: [tests/voice/test_budgets.py]
  sec_row: "llm-boundary"
- id: INT-102
  epic: E05-voice
  phase: P1
  title: "Adversarial suite RT-09..14 in make safety + nightly LLM red-team job"
  depends_on: [INT-094, INT-083]
  labels: [area:safety, risk:security]
  status: todo
  acceptance:
    - "injection by speech and hidden-PDF text, triage manipulation, proxy impersonation, spoken TCKN masking, vendor failover — all pass; nightly job budgeted"
  tests: [tests/safety/test_adversarial_rt09_14.py]
  sec_row: "llm-boundary"
- id: INT-103
  epic: E05-voice
  phase: P1
  title: "Mobile voice client: LiveKit RN, permissions, network-quality per turn, reconnect, background"
  depends_on: [INT-130, INT-090]
  labels: [area:mobile]
  status: todo
  acceptance:
    - "mic permission copy per store rules; RTT/jitter/loss attached to turns; reconnect resumes session; background pauses safely"
  tests: [apps/mobile/e2e/voice.spec.ts]
  legal: "STORE"
  sec_row: "mobile"
- id: INT-110
  epic: E06-lanes
  phase: P0
  title: "Lane framework: budgets, backpressure, ObserverState, per-lane consent, type-level read-only"
  depends_on: [INT-092, INT-038]
  labels: [area:lanes, risk:clinical]
  status: todo
  acceptance:
    - "lanes cannot write slots/triage (compile-time); stalled lanes never delay speech (fake clock); frames dropped under load with metric"
  tests: [tests/lanes/test_isolation.py]
  legal: "KVKK-6"
  sec_row: "observer-lanes"
- id: INT-111
  epic: E06-lanes
  phase: P1
  title: "affect lane: Inworld adapter (cascade) + open SER (residency) + Turkish eval"
  depends_on: [INT-110]
  labels: [area:lanes, approval:human-vendor, live-smoke]
  status: todo
  acceptance:
    - "confidence>=0.6, accent ignored; per-section aggregate only; Turkish eval report checked in before enabling by default"
  tests: [tests/lanes/test_affect_contract.py]
  legal: "KVKK-6-lane"
  sec_row: "observer-lanes"
- id: INT-112
  epic: E06-lanes
  phase: P0
  title: "linguistic lane: TR lexicons + prosody stats + crisis bypass to triage"
  depends_on: [INT-110, INT-080]
  labels: [area:lanes, risk:clinical]
  status: todo
  acceptance:
    - "crisis lexicon hits route deterministically to C-SSRS path (test); markers aggregate per section"
  tests: [tests/lanes/test_crisis_bypass.py]
  sec_row: "observer-lanes"
- id: INT-113
  epic: E06-lanes
  phase: P1
  title: "asr_quality lane: shadow-STT disagreement + confirm-by-card trigger"
  depends_on: [INT-110, INT-095]
  labels: [area:lanes]
  status: todo
  acceptance:
    - "sampled turns compared; wer proxy metric; low-confidence medical terms trigger confirm cards"
  tests: [tests/lanes/test_asr_quality.py]
- id: INT-114
  epic: E06-lanes
  phase: P1
  title: "engagement lane -> satisfaction proxies + pacing hints"
  depends_on: [INT-110]
  labels: [area:lanes]
  status: todo
  acceptance:
    - "answer latency, interruptions, silence ratio into engagement{} and metrics"
  tests: [tests/lanes/test_engagement.py]
- id: INT-115
  epic: E06-lanes
  phase: P2
  title: "acoustic lane (research flag): DAM weights, 30s in-memory window, zeroing, research tenants only"
  depends_on: [INT-110]
  labels: [area:lanes, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "flag confined to research tenants with `research` consent; window zeroed after scoring (test); indeterminate band preserved; no patient-facing output"
  tests: [tests/lanes/test_acoustic_window_zeroing.py]
  legal: "KVKK-6-lane,ETİK"
  sec_row: "observer-lanes"
- id: INT-116
  epic: E06-lanes
  phase: P0
  title: "Wellbeing engine: PHQ-2/GAD-2 -> PHQ-9/GAD-7 -> C-SSRS, crisis script, verbatim items, clinician-only outputs"
  depends_on: [INT-081, INT-112]
  labels: [area:clinical, risk:clinical, approval:human-clinical]
  status: todo
  acceptance:
    - "validated Turkish items verbatim; scoring deterministic; crisis path completion tested end-to-end; outputs never in patient summary"
  tests: [tests/clinical/test_wellbeing_paths.py]
  legal: "HHY-15,MDSW"
  sec_row: "wellbeing"
- id: INT-117
  epic: E06-lanes
  phase: P0
  title: "device_functions flag: MDSW boundary enforced (Stage A non-device vs investigation mode)"
  depends_on: [INT-116, INT-093, INT-038]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "with flag off (commercial default until CE): no automated patient-facing triage advice and no automated severity interpretation; static 112 text at fixed points; red-flag answers shown to clinician as patient-reported data; shadow triage logged for clinical evaluation"
    - "with flag on (investigation tenants only, bound to an approved study id): full RED preemption + scored instruments; enabling requires study id + ethics + TITCK approval recorded"
    - "tests prove both modes and that no code path leaks device behavior when off"
  tests: [tests/legal/test_device_functions_gate.py]
  legal: "TCY-R11,TCKAY,3359-Ek10"
  sec_row: "device-boundary"
- id: INT-120
  epic: E07-records
  phase: P0
  title: "Upload pipeline: ClamAV, sniffing, limits, sandboxed OCR"
  depends_on: [INT-034]
  labels: [area:records, risk:security]
  status: todo
  acceptance:
    - "AV scan before processing; OCR in seccomp-sandboxed worker; malformed/fuzz PDFs never crash host"
  tests: [tests/records/test_upload_pipeline.py]
  legal: "KVKK-12"
  sec_row: "records"
- id: INT-121
  epic: E07-records
  phase: P0
  title: "Document extraction -> FHIR with provenance + confirm cards + eval corpus"
  depends_on: [INT-120, INT-083]
  labels: [area:records]
  status: todo
  acceptance:
    - "labs/meds/diagnoses extracted with source boxes; patient confirms before use; accuracy metric on corpus >=90 percent LOINC+unit"
  tests: [tests/records/test_extraction_eval.py]
  sec_row: "records"
- id: INT-122
  epic: E07-records
  phase: P1
  title: "e-Nabız export/PDF import parser + MHRS SMS screenshot OCR"
  depends_on: [INT-121]
  labels: [area:records]
  status: todo
  acceptance:
    - "patient-exported e-Nabiz documents parsed; MHRS SMS screenshot -> visit fields; no scraping of e-Nabiz (no third-party API exists; legal note enforced)"
  tests: [tests/records/test_enabiz_pdf.py]
  legal: "KSVY-9,KSVY-10"
  sec_row: "records"
- id: INT-123
  epic: E07-records
  phase: P1
  title: "pgvector record index (RLS, per-patient namespace) + retrieval Work"
  depends_on: [INT-030, INT-121]
  labels: [area:records]
  status: todo
  acceptance:
    - "embeddings scoped by patient+consent; retrieval cited into notes with provenance"
  tests: [tests/records/test_vector_rls.py]
  sec_row: "records"
- id: INT-124
  epic: E07-records
  phase: P2
  title: "Lab-report->JSON via MedGemma 1.5 4B (residency option) + eval"
  depends_on: [INT-121]
  labels: [area:records, gpu]
  status: todo
  acceptance:
    - "adapter behind gateway; eval vs corpus; HAI-DEF terms recorded in model registry"
  tests: [tests/records/test_labjson_eval.py]
  sec_row: "records"
- id: INT-130
  epic: E08-mobile
  phase: P0
  title: "Expo app shell: SDK 57 dev build, navigation map per 02, i18n tr-first, theme, a11y base"
  depends_on: [INT-001]
  labels: [area:mobile]
  status: todo
  acceptance:
    - "navigation exactly per 02 §4 incl. me/learned; tr+en resource files; dynamic type"
  tests: [apps/mobile/e2e/nav.spec.ts]
  legal: "805"
  sec_row: "mobile"
- id: INT-131
  epic: E08-mobile
  phase: P0
  title: "Onboarding & auth: OTP + attestation + DPoP + biometrics + SecureStore + pinning + FLAG_SECURE"
  depends_on: [INT-130, INT-012, INT-013]
  labels: [area:mobile, risk:security]
  status: todo
  acceptance:
    - "OTP limits per 10 §2; App Attest/Play Integrity on OTP+session; refresh rotation with reuse detection; biometric gate; clinical screens FLAG_SECURE; jailbreak -> typed+warn"
  tests: [apps/mobile/e2e/auth.spec.ts, tests/security/test_otp_abuse.py]
  legal: "KVKK-6,KVKK-12"
  sec_row: "onboarding"
- id: INT-132
  epic: E08-mobile
  phase: P0
  title: "Consent UI: layered, versioned, lane sub-toggles, learning, satisfaction; who-sees-what"
  depends_on: [INT-038, INT-130]
  labels: [area:mobile, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "texts loaded from docs/legal with hash binding; unbundled toggles; withdrawal instant; re-prompt on version change; Turkish primary"
  tests: [apps/mobile/e2e/consent.spec.ts]
  legal: "KVKK-5,KVKK-6,AYD-2018"
  sec_row: "consent"
- id: INT-133
  epic: E08-mobile
  phase: P0
  title: "Profiles, companions, guardian flows (minors), proxy acknowledgement"
  depends_on: [INT-131, INT-223]
  labels: [area:mobile, risk:legal]
  status: todo
  acceptance:
    - "under-18 only via guardian account with guardian consent; adolescent private-section policy implemented per 06 §6; proxy-reported flag on every record"
  tests: [apps/mobile/e2e/guardian.spec.ts]
  legal: "TMK-339,HHY-24"
  sec_row: "companions"
- id: INT-134
  epic: E08-mobile
  phase: P0
  title: "Visits: create (manual + MHRS SMS OCR), branch picker from taxonomy, visit types"
  depends_on: [INT-130, INT-042]
  labels: [area:mobile]
  status: todo
  acceptance:
    - "branch list from taxonomy; unknown branch -> cluster with notice; OCR path behind documents consent"
  tests: [apps/mobile/e2e/visits.spec.ts]
  sec_row: "visits"
- id: INT-135
  epic: E08-mobile
  phase: P1
  title: "Voice intake UI (Hizli): states, recording indicator, inline cards, barge-in, RED UI, typed fallback"
  depends_on: [INT-103, INT-096, INT-117]
  labels: [area:mobile, risk:clinical]
  status: todo
  acceptance:
    - "recording indicator always visible; RED UI per device_functions mode; fallback switch <=2s visible"
  tests: [apps/mobile/e2e/voice_intake.spec.ts]
  legal: "USHY-12"
  sec_row: "intake-voice"
- id: INT-136
  epic: E08-mobile
  phase: P0
  title: "Typed intake UI (Detayli) + chips + instruments verbatim"
  depends_on: [INT-096, INT-130]
  labels: [area:mobile]
  status: todo
  acceptance:
    - "instrument items rendered verbatim; low-literacy chips; progress + resume"
  tests: [apps/mobile/e2e/typed_intake.spec.ts]
  sec_row: "intake-typed"
- id: INT-137
  epic: E08-mobile
  phase: P0
  title: "Review & send + Doctor Link QR + CSAT prompt"
  depends_on: [INT-084, INT-240]
  labels: [area:mobile]
  status: todo
  acceptance:
    - "section-level scope UI; consent summary; send; status timeline; one-tap CSAT with reason chips; never blocks send"
  tests: [apps/mobile/e2e/review_send.spec.ts]
  legal: "KVKK-5"
  sec_row: "review-send"
- id: INT-138
  epic: E08-mobile
  phase: P0
  title: "Records screens: upload, processing, confirm cards, provenance viewer"
  depends_on: [INT-121, INT-130]
  labels: [area:mobile]
  status: todo
  acceptance:
    - "camera+file upload; AV/processing states; confirm-before-use; provenance boxes"
  tests: [apps/mobile/e2e/records.spec.ts]
  sec_row: "records"
- id: INT-139
  epic: E08-mobile
  phase: P0
  title: "Share centre: active shares, revoke <=1min, access log"
  depends_on: [INT-150]
  labels: [area:mobile]
  status: todo
  acceptance:
    - "revocation cascades to tokens within 1 min (test); patient sees access log"
  tests: [apps/mobile/e2e/shares.spec.ts]
  legal: "KVKK-11"
  sec_row: "share-centre"
- id: INT-140
  epic: E08-mobile
  phase: P0
  title: "Me: consents, connectors, language, security, export/delete, learned facts"
  depends_on: [INT-037, INT-170]
  labels: [area:mobile]
  status: todo
  acceptance:
    - "export/delete flows wired to DSAR; learned facts editable/deletable with provenance"
  tests: [apps/mobile/e2e/me.spec.ts]
  legal: "KVKK-11"
  sec_row: "dsar"
- id: INT-141
  epic: E08-mobile
  phase: P1
  title: "Notifications: content-free reminders, quiet hours, opt-out; transactional-only"
  depends_on: [INT-130]
  labels: [area:mobile, risk:legal]
  status: todo
  acceptance:
    - "no PHI in push; reminders classified transactional (no IYS consent needed); any marketing path requires IYS consent and is off by default"
  tests: [apps/mobile/e2e/notifications.spec.ts]
  legal: "6563-IYS"
  sec_row: "notifications"
- id: INT-142
  epic: E08-mobile
  phase: P1
  title: "Offline drafts + sync + resilience"
  depends_on: [INT-136]
  labels: [area:mobile]
  status: todo
  acceptance:
    - "drafts encrypted at rest; sync conflict rules; airplane-mode e2e"
  tests: [apps/mobile/e2e/offline.spec.ts]
  sec_row: "mobile"
- id: INT-143
  epic: E08-mobile
  phase: P1
  title: "Kiosk mode: MDM lockdown, clinic PIN, 60s auto-wipe, privacy layout"
  depends_on: [INT-136]
  labels: [area:mobile, risk:security]
  status: todo
  acceptance:
    - "no persistence; wipe on idle/background; tamper alert; large-type layout"
  tests: [apps/mobile/e2e/kiosk.spec.ts]
  legal: "KVKK-12"
  sec_row: "kiosk"
- id: INT-144
  epic: E08-mobile
  phase: P1
  title: "Accessibility WCAG 2.2 AA pass + TR screen-reader labels + conformance report"
  depends_on: [INT-130]
  labels: [area:mobile, risk:legal]
  status: todo
  acceptance:
    - "axe/a11y CI checks; VoiceOver/TalkBack scripts; docs/legal/accessibility-statement.md (EN 301 549 mapping)"
  tests: [apps/mobile/e2e/a11y.spec.ts]
  legal: "5378,EN301549"
  sec_row: "mobile"
- id: INT-145
  epic: E08-mobile
  phase: P1
  title: "Client telemetry: GlitchTip crash (PHI-scrubbed), perf, RUM web"
  depends_on: [INT-023, INT-130]
  labels: [area:mobile]
  status: todo
  acceptance:
    - "crash-free metric wired; scrub tests; cold-start p95 tracked"
  tests: [tests/mobile/test_crash_scrub.py]
  legal: "KVKK-12"
  sec_row: "mobile"
- id: INT-146
  epic: E08-mobile
  phase: P1
  title: "EAS builds + OTA code signing + MobSF gate + store listings/privacy labels"
  depends_on: [INT-131, INT-224]
  labels: [area:mobile, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "signed OTA; MobSF report gate; Apple privacy nutrition + Google Data safety filled from the data inventory and asserted against schema annotations"
  tests: [tests/mobile/test_privacy_labels_match_inventory.py]
  legal: "STORE,KVKK-10"
  sec_row: "mobile"
- id: INT-150
  epic: E09-clinician
  phase: P0
  title: "Doctor Link: 128-bit token + OTP + expiry + view limit + revoke + watermark + access log + no-index"
  depends_on: [INT-084, INT-016]
  labels: [area:clinician, risk:security]
  status: todo
  acceptance:
    - "entropy/expiry tests; watermark carries recipient+timestamp; robots/noindex; every open audited and visible to patient"
  tests: [tests/clinician/test_doctor_link.py]
  legal: "KVKK-12,HHY-23"
  sec_row: "doctor-link"
- id: INT-151
  epic: E09-clinician
  phase: P0
  title: "Note views: SOAP, red flags (mode-aware), provenance, consented wellbeing, AI labels + 1-click feedback"
  depends_on: [INT-150, INT-117]
  labels: [area:clinician]
  status: todo
  acceptance:
    - "device_functions off: red-flag answers shown as patient-reported without automated urgency labels; AI-generated sections labelled; feedback event wired"
  tests: [apps/clinician-web/e2e/note.spec.ts]
  legal: "1219-8"
  sec_row: "doctor-link"
- id: INT-152
  epic: E09-clinician
  phase: P1
  title: "Clinic console: today list, statuses, read receipts, tenant isolation, SSO"
  depends_on: [INT-151, INT-030]
  labels: [area:clinician]
  status: todo
  acceptance:
    - "Keycloak SSO; RLS-backed isolation tests; read-receipt events"
  tests: [apps/clinician-web/e2e/console.spec.ts]
  legal: "KVKK-12"
  sec_row: "clinic-console"
- id: INT-153
  epic: E09-clinician
  phase: P1
  title: "Clinician feedback -> Langfuse annotation queues + acceptance metrics"
  depends_on: [INT-151, INT-175]
  labels: [area:clinician]
  status: todo
  acceptance:
    - "accept/edit/reject with section reasons into note_quality queue; note.acceptance_rate live"
  tests: [tests/clinician/test_feedback_pipeline.py]
  sec_row: "learning-loops"
- id: INT-160
  epic: E10-connectors
  phase: P1
  title: "Connector framework: adapters, OpenBao creds, idempotency, receipts, allow-listed endpoints, mTLS"
  depends_on: [INT-018, INT-035]
  labels: [area:connectors, risk:security]
  status: todo
  acceptance:
    - "per-tenant endpoint allow-list; push receipts stored; replay-safe"
  tests: [tests/connectors/test_framework.py]
  legal: "KVKK-8/9"
  sec_row: "connectors"
- id: INT-161
  epic: E10-connectors
  phase: P1
  title: "FHIR push adapter (hospital FHIR/HAPI; SMART backend services auth)"
  depends_on: [INT-160, INT-033]
  labels: [area:connectors, approval:human-vendor, live-smoke]
  status: todo
  acceptance:
    - "contract tests vs HAPI; SMART backend client credentials; scoped by share consent token; live smoke against a partner sandbox recorded before close"
  tests: [tests/connectors/test_fhir_push.py]
  legal: "KVKK-8"
  sec_row: "connectors"
- id: INT-162
  epic: E10-connectors
  phase: P2
  title: "HBYS/SBYS adapter kit (HL7v2 ORU / file drop / FHIR) + USVS mapping + KTS registration pack"
  depends_on: [INT-160]
  labels: [area:connectors, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "mapping tables to USVS data dictionary; KTS (SBYS Kayit Tescil) application pack generated from repo docs; processor-role DPA references"
  tests: [tests/connectors/test_usvs_mapping.py]
  legal: "SBYS-6,USVS"
  sec_row: "connectors"
- id: INT-163
  epic: E10-connectors
  phase: P2
  title: "Check-in: signed QR payload + desk verification + checkin_to_seen metric"
  depends_on: [INT-160, INT-143]
  labels: [area:connectors]
  status: todo
  acceptance:
    - "QR payload signed+short-lived; desk verification flow; wait metric emitted"
  tests: [tests/connectors/test_checkin.py]
  sec_row: "kiosk"
- id: INT-170
  epic: E11-learning
  phase: P0
  title: "PatientOverlay: store, confirmation rules, /me/learned API, engine integration"
  depends_on: [INT-031, INT-081]
  labels: [area:learning]
  status: todo
  acceptance:
    - "facts commit only with patient/clinician confirmation (type-level); 12-month reconfirm; provenance shown; delta-mode works in simulator"
  tests: [tests/learning/test_overlay_provenance.py]
  legal: "KVKK-11"
  sec_row: "learning-loops"
- id: INT-171
  epic: E11-learning
  phase: P2
  title: "De-identified analytics views + k-anonymity helper + rollups"
  depends_on: [INT-015, INT-030]
  labels: [area:learning, risk:legal]
  status: todo
  acceptance:
    - "k>=10 enforced at query layer; refusals metered; no free-text outside review UI"
  tests: [tests/learning/test_k_anonymity.py]
  legal: "KVKK-16,KSVY-16"
  sec_row: "learning-loops"
- id: INT-172
  epic: E11-learning
  phase: P2
  title: "services/learning Inspector->Architect + proposal schema + evidence bundles + PR bot (open-not-merge)"
  depends_on: [INT-171, INT-004]
  labels: [area:learning, risk:clinical]
  status: todo
  acceptance:
    - "proposal_scope CI test blocks forbidden paths (red-flag levels, instruments, consent texts, Talker tools, PolicyGuard, residency routing); sandboxed job read-only creds no egress; signed proposals"
  tests: [tests/learning/test_proposal_scope.py]
  sec_row: "learning-loops"
- id: INT-173
  epic: E11-learning
  phase: P2
  title: "Canary/rollback controller on guardrail KPIs (5/25/100)"
  depends_on: [INT-172, INT-025]
  labels: [area:learning]
  status: todo
  acceptance:
    - "auto-rollback on acceptance -5, safety blocks +50 percent, completion -5, CSAT -0.3; simulated dip test"
  tests: [tests/learning/test_canary_rollback.py]
  sec_row: "learning-loops"
- id: INT-174
  epic: E11-learning
  phase: P2
  title: "DSPy+GEPA offline optimisation (extraction, note modules only) with clinician-edit metric + held-out"
  depends_on: [INT-153, INT-172]
  labels: [area:learning]
  status: todo
  acceptance:
    - "single-module runs; Pareto selection; Langfuse experiment links in evidence bundle; Talker/safety prompts excluded by scope test"
  tests: [tests/learning/test_gepa_scope.py]
  sec_row: "learning-loops"
- id: INT-175
  epic: E11-learning
  phase: P1
  title: "Langfuse self-hosted + annotation queues (note_quality, hallucination_audit, false_red_review) + CI experiment gate"
  depends_on: [INT-023]
  labels: [area:observability]
  status: todo
  acceptance:
    - "compose profile; OTel span export; CI job runs recorded simulator experiment and gates on scores"
  tests: [tests/observability/test_langfuse_gate.py]
  sec_row: "observability-pipeline"
- id: INT-180
  epic: E12-admin
  phase: P0
  title: "Admin shell: Keycloak RBAC/ABAC, audit on every action, IP allow-list, 4-eyes primitives"
  depends_on: [INT-023, INT-016]
  labels: [area:admin, risk:security]
  status: todo
  acceptance:
    - "roles per 08 §2; break-glass with reason+approver; role-matrix contract tests for /admin/*"
  tests: [tests/admin/test_rbac_matrix.py]
  legal: "KVKK-12"
  sec_row: "admin-console"
- id: INT-181
  epic: E12-admin
  phase: P0
  title: "Modules: Overview + Ops + Reliability (real dev telemetry)"
  depends_on: [INT-180, INT-021, INT-022]
  labels: [area:admin]
  status: todo
  acceptance:
    - "SLO tiles, burn rates, probe matrix, dependency health from live dev stack (not mock JSON)"
  tests: [apps/admin-web/e2e/overview.spec.ts]
  sec_row: "admin-console"
- id: INT-182
  epic: E12-admin
  phase: P1
  title: "Voice module + kill switch + profile switch + canary weights (4-eyes)"
  depends_on: [INT-181, INT-094]
  labels: [area:admin, risk:clinical]
  status: todo
  acceptance:
    - "per-profile metrics; kill switch flips tenant to typed without deploy (test)"
  tests: [tests/admin/test_kill_switch.py]
  sec_row: "admin-console"
- id: INT-183
  epic: E12-admin
  phase: P0
  title: "Models & self-hosting registry module + release gate surface"
  depends_on: [INT-022, INT-180]
  labels: [area:admin]
  status: todo
  acceptance:
    - "registry rendered; benchmark trigger; red cell blocks release visibly"
  tests: [apps/admin-web/e2e/models.spec.ts]
  legal: "G2019-12"
  sec_row: "self-hosting"
- id: INT-184
  epic: E12-admin
  phase: P2
  title: "Protocols module: coverage, review queue, proposals, canary, clips"
  depends_on: [INT-042, INT-172, INT-180]
  labels: [area:admin]
  status: todo
  acceptance:
    - "branch x maturity matrix; approve/reject with 4-eyes; clip coverage per voice"
  tests: [apps/admin-web/e2e/protocols.spec.ts]
  sec_row: "admin-console"
- id: INT-185
  epic: E12-admin
  phase: P1
  title: "Clinical quality & safety module + annotation-queue links"
  depends_on: [INT-175, INT-180]
  labels: [area:admin]
  status: todo
  acceptance:
    - "triage events, false-RED queue, PolicyGuard classes, acceptance by specialty"
  tests: [apps/admin-web/e2e/safety.spec.ts]
  sec_row: "admin-console"
- id: INT-186
  epic: E12-admin
  phase: P1
  title: "Experience & satisfaction module (CSAT/NPS/pulse/waits + SDS-01 export)"
  depends_on: [INT-240, INT-180]
  labels: [area:admin]
  status: todo
  acceptance:
    - "filters by branch/profile/clinic; SDS-01-style export for hospital tenants"
  tests: [apps/admin-web/e2e/experience.spec.ts]
  sec_row: "admin-console"
- id: INT-187
  epic: E12-admin
  phase: P1
  title: "CI/CD & releases module (GH API + Argo CD + gates + freeze)"
  depends_on: [INT-181, INT-201]
  labels: [area:admin]
  status: todo
  acceptance:
    - "pipelines, eval gates, deploy health, canary state, rollback button (4-eyes), deploy-freeze on budget exhaustion"
  tests: [apps/admin-web/e2e/cicd.spec.ts]
  sec_row: "cicd"
- id: INT-188
  epic: E12-admin
  phase: P1
  title: "Flags module (Unleash) + 4-eyes on safety flags"
  depends_on: [INT-023, INT-180]
  labels: [area:admin]
  status: todo
  acceptance:
    - "change reasons mandatory; safety flags list incl. device_functions, s2s, learning-apply"
  tests: [tests/admin/test_flag_governance.py]
  sec_row: "admin-console"
- id: INT-189
  epic: E12-admin
  phase: P1
  title: "Compliance module: consents, vendor register, audit search, DSAR queue, retention, DPIA, residency, evidence exports"
  depends_on: [INT-036, INT-037, INT-038, INT-180]
  labels: [area:admin, risk:legal]
  status: todo
  acceptance:
    - "vendor-transfer register auto-filled from egress logs with notification due-dates (5 business days rule); evidence export bundles for audits"
  tests: [apps/admin-web/e2e/compliance.spec.ts]
  legal: "KVKK-9,TRANSFER-2024"
  sec_row: "compliance-evidence"
- id: INT-190
  epic: E12-admin
  phase: P1
  title: "Cost module"
  depends_on: [INT-101, INT-180]
  labels: [area:admin]
  status: todo
  acceptance:
    - "per-session cost by component/vendor/profile; budgets + alerts"
  tests: [apps/admin-web/e2e/cost.spec.ts]
  sec_row: "admin-console"
- id: INT-191
  epic: E12-admin
  phase: P2
  title: "Tenants module + onboarding flow"
  depends_on: [INT-180, INT-250]
  labels: [area:admin]
  status: todo
  acceptance:
    - "tenant CRUD, connectors, pack enablement, branding, key rotation"
  tests: [apps/admin-web/e2e/tenants.spec.ts]
  sec_row: "admin-console"
- id: INT-192
  epic: E12-admin
  phase: P1
  title: "Security module: SIEM feeds, vulns vs SLA, rotations, drills, integrity"
  depends_on: [INT-205, INT-180]
  labels: [area:admin, risk:security]
  status: todo
  acceptance:
    - "Wazuh/Falco/CrowdSec summaries; egress denials; audit-chain status; pen-test findings tracker"
  tests: [apps/admin-web/e2e/security.spec.ts]
  sec_row: "admin-console"
- id: INT-200
  epic: E13-infra
  phase: P2
  title: "Residency compose profile (GPU) + runbooks"
  depends_on: [INT-097]
  labels: [area:infra, gpu]
  status: todo
  acceptance:
    - "single-host GPU deployment documented and probed; capacity notes"
  tests: [tests/infra/test_residency_profile.py]
  legal: "G2019-12"
  sec_row: "self-hosting"
- id: INT-201
  epic: E13-infra
  phase: P2
  title: "k8s: k3s + Argo CD + Kyverno/Sigstore admission + PSS restricted + default-deny + Harbor"
  depends_on: [INT-019]
  labels: [area:infra, risk:security, approval:human-infra]
  status: todo
  acceptance:
    - "unsigned image rejected by admission (test in kind); GitOps envs dev/staging/tr-residency"
  tests: [tests/infra/test_admission_policy.py]
  sec_row: "cicd"
- id: INT-202
  epic: E13-infra
  phase: P1
  title: "Backups: pgBackRest PITR encrypted + MinIO replication + automated restore drill + evidence"
  depends_on: [INT-030, INT-034]
  labels: [area:infra, risk:security]
  status: todo
  acceptance:
    - "RPO 15min/RTO 4h demonstrated in a drill script whose output is stored as evidence; quarterly schedule"
  tests: [tests/infra/test_restore_drill.py]
  legal: "KVKK-12"
  sec_row: "backups"
- id: INT-203
  epic: E13-infra
  phase: P1
  title: "Edge: Traefik + Coraza CRS + CrowdSec + cert-manager + prod egress proxy"
  depends_on: [INT-018]
  labels: [area:infra, risk:security]
  status: todo
  acceptance:
    - "WAF blocks OWASP CRS suite; CrowdSec scenarios on; certs automated"
  tests: [tests/infra/test_waf_rules.py]
  legal: "KVKK-12"
  sec_row: "edge"
- id: INT-204
  epic: E13-infra
  phase: P2
  title: "Mesh mTLS (Linkerd) + default-deny NetworkPolicies"
  depends_on: [INT-201]
  labels: [area:infra, risk:security]
  status: todo
  acceptance:
    - "all service-to-service traffic mTLS; policy tests"
  tests: [tests/infra/test_mesh_mtls.py]
  legal: "KVKK-12"
  sec_row: "edge"
- id: INT-205
  epic: E13-infra
  phase: P1
  title: "Wazuh + Falco deployment + rules + console feed"
  depends_on: [INT-023]
  labels: [area:infra, risk:security]
  status: todo
  acceptance:
    - "auth anomalies, k8s audit, container runtime alerts wired to Security module"
  tests: [tests/infra/test_siem_feed.py]
  legal: "7545"
  sec_row: "incident-response"
- id: INT-206
  epic: E13-infra
  phase: P1
  title: "GitHub Actions self-hosted runners in TR DC + no-PHI-in-CI policy"
  depends_on: [INT-002]
  labels: [area:infra]
  status: todo
  acceptance:
    - "runner heartbeats probed; CI uses synthetic fixtures only (scan)"
  tests: [tests/infra/test_ci_no_phi.py]
  legal: "G2019-12"
  sec_row: "cicd"
- id: INT-207
  epic: E13-infra
  phase: P2
  title: "Chaos suite (monthly) + load to pilot x3 + autoscaling rules"
  depends_on: [INT-024, INT-201]
  labels: [area:infra]
  status: todo
  acceptance:
    - "SFU drop, backend stall, vendor kill, DB failover scenarios green; k6+lk evidence at 3x pilot concurrency"
  tests: [tests/chaos/test_suite.py]
  sec_row: "resilience"
- id: INT-210
  epic: E14-legal
  phase: P0
  title: "Legal document set v1 (tr primary): aydinlatma x5, acik riza per purpose, gizlilik, kullanim kosullari, KVKK basvuru formu, cookie"
  depends_on: [INT-038]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "docs/legal/ versioned with hashes; rendered in-app from source; acceptance evidence stored; plain-language summaries; counsel sign-off recorded in evidence file before merge"
  tests: [tests/legal/test_text_hash_binding.py]
  legal: "KVKK-10,AYD-2018,805"
  sec_row: "consent"
- id: INT-211
  epic: E14-legal
  phase: P0
  title: "VERBIS registration pack + data inventory generated from schema annotations + irtibat kisisi"
  depends_on: [INT-031, INT-210]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "every model field annotated {category,purpose,basis,retention,recipients}; inventory export matches VERBIS categories; registration checklist done"
  tests: [tests/legal/test_data_inventory_complete.py]
  legal: "KVKK-16v"
  sec_row: "compliance-evidence"
- id: INT-212
  epic: E14-legal
  phase: P0
  title: "Retention & destruction policy doc (DEST-2017) bound to the engine"
  depends_on: [INT-036, INT-210]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "policy document generated from the same policy-as-code the engine runs; periodic destruction report template"
  tests: [tests/legal/test_policy_doc_sync.py]
  legal: "KVKK-7,DEST-2017"
  sec_row: "retention"
- id: INT-213
  epic: E14-legal
  phase: P1
  title: "DPIA v1 + vendor transfer register + SCC set + Board notification workflow (5 business days) + hospital DPA template"
  depends_on: [INT-018, INT-210]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "DPIA per processing map; SCCs per vendor from Board template; notification workflow with due-date tracking in console; DPA with mandatory clauses (KVKK-8/12, security annex mapping 10, sub-processor list, audit rights, breach notice, deletion)"
  tests: [tests/legal/test_transfer_register.py]
  legal: "KVKK-9,TRANSFER-2024"
  sec_row: "compliance-evidence"
- id: INT-214
  epic: E14-legal
  phase: P1
  title: "Breach machinery: KVKK 72h Board form automation + data-subject notices + USOM report (7545) + hospital notices"
  depends_on: [INT-020]
  labels: [area:legal, risk:legal]
  status: todo
  acceptance:
    - "runbook executable: incident record -> prefilled Board form -> notices; drill test produces the full packet within 72h simulated clock"
  tests: [tests/legal/test_breach_drill.py]
  legal: "KVKK-12-breach,7545"
  sec_row: "incident-response"
- id: INT-215
  epic: E14-legal
  phase: P1
  title: "Special-category adequate measures (Board 2018/10) mapping + evidence export"
  depends_on: [INT-019, INT-023]
  labels: [area:legal, risk:legal]
  status: todo
  acceptance:
    - "each 2018/10 measure mapped to a control and a live signal; export produces the auditor packet"
  tests: [tests/legal/test_2018_10_mapping.py]
  legal: "2018-10"
  sec_row: "compliance-evidence"
- id: INT-216
  epic: E14-legal
  phase: P0
  title: "MDSW file: intended purpose, qualification (MDCG 2019-11 TR), Rule 11 classification (Class IIa), device/non-device boundary table"
  depends_on: [INT-117]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "docs/regulatory/intended-purpose.md exact wording; boundary table lists every feature as device or non-device and binds to device_functions flag; classification rationale reviewed"
  tests: [tests/legal/test_boundary_table_matches_flags.py]
  legal: "TCY-R11"
  sec_row: "device-boundary"
- id: INT-217
  epic: E14-legal
  phase: P1
  title: "QMS core (ISO 13485): quality manual, design controls, ISO 14971 risk file, IEC 62304 class B plan, IEC 62366-1 usability, IEC 81001-5-1 security lifecycle, PMS plan, PRRC"
  depends_on: [INT-216]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "docs/qms/ under document control in-repo; design-control gates wired into PR template for device-flagged issues; PRRC appointment recorded"
  tests: [tests/legal/test_qms_doc_control.py]
  legal: "TCY,ISO13485"
  sec_row: "device-boundary"
- id: INT-218
  epic: E14-legal
  phase: P1
  title: "Clinical investigation package: protocol + ICF(tr) + ATADEK ethics submission + TITCK application + insurance + registration"
  depends_on: [INT-217]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "Stage-A pilot runs only under approved study id; approvals recorded before device_functions can be enabled for the pilot tenant (gate test)"
  tests: [tests/legal/test_investigation_gate.py]
  legal: "TCKAY,3359-Ek10"
  sec_row: "device-boundary"
- id: INT-219
  epic: E14-legal
  phase: P2
  title: "Technical documentation (Annex II/III) + clinical evaluation (MDCG 2020-1) + PMCF + notified-body selection"
  depends_on: [INT-217]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "tech-file skeleton auto-assembles from repo artifacts (SBOM, risk file, V&V evidence, SOUP list from lockfiles)"
  tests: [tests/legal/test_techfile_assembly.py]
  legal: "TCY"
  sec_row: "device-boundary"
- id: INT-220
  epic: E14-legal
  phase: P2
  title: "Registrations: UTS (TCKKD-KLVZ-03) + UDI; KTS (SBYS) pack; BTK yer saglayici; traffic-log retention 5651"
  depends_on: [INT-219, INT-162]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "packs generated from repo; 5651 traffic logs (IP,ts) separated from PHI, retained 1y max 2y with auto-purge test"
  tests: [tests/legal/test_5651_traffic_logs.py]
  legal: "UTS,SBYS-6,5651-5"
  sec_row: "compliance-evidence"
- id: INT-221
  epic: E14-legal
  phase: P2
  title: "Public-hospital pack: Genelge 2019/12 residency attestation + DDO Rehber mapping + USVS conformance"
  depends_on: [INT-183, INT-162]
  labels: [area:legal, risk:legal]
  status: todo
  acceptance:
    - "tr-residency tenants provably vendor-free on PHI path (registry assertion); Rehber control mapping doc; USVS conformance tests"
  tests: [tests/legal/test_residency_attestation.py]
  legal: "G2019-12,DDO,USVS"
  sec_row: "self-hosting"
- id: INT-222
  epic: E14-legal
  phase: P2
  title: "Consumer/commercial: mesafeli sozlesme pre-info + withdrawal (if paid tier), IYS integration for marketing, Turkish-language compliance"
  depends_on: [INT-210]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "paid flows blocked until pre-information + withdrawal implemented; marketing sends blocked without IYS consent record"
  tests: [tests/legal/test_distance_contract_gate.py]
  legal: "6502-MSY,6563-IYS,805"
  sec_row: "billing"
- id: INT-223
  epic: E14-legal
  phase: P0
  title: "Minor & guardian rules engine (age gates, guardian consent, adolescent policy) as code"
  depends_on: [INT-038]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "age from verified DOB; under-18 requires guardian account+consent; adolescent private-section share policy per 06 §6; tests for each age band"
  tests: [tests/legal/test_minor_rules.py]
  legal: "TMK-339,HHY-24"
  sec_row: "companions"
- id: INT-224
  epic: E14-legal
  phase: P1
  title: "Store compliance: Apple health guidelines + Google Play Health policy + Data safety/privacy labels + IARC"
  depends_on: [INT-146]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "checklists as tests where automatable; labels generated from the data inventory (single source)"
  tests: [tests/legal/test_store_labels.py]
  legal: "STORE"
  sec_row: "mobile"
- id: INT-225
  epic: E14-legal
  phase: P3
  title: "ISO 27001 ISMS: scope, SoA, risk register, policies, internal audit, certification audit"
  depends_on: [INT-215, INT-192]
  labels: [area:legal, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "SoA maps Annex A to implemented controls with evidence links; internal audit executed; certification scheduled"
  tests: [tests/legal/test_soa_links.py]
  legal: "ISO27001,SBYS-6"
  sec_row: "compliance-evidence"
- id: INT-226
  epic: E14-legal
  phase: P1
  title: "Accessibility conformance report (WCAG 2.2 AA / EN 301 549) + statement page"
  depends_on: [INT-144]
  labels: [area:legal]
  status: todo
  acceptance:
    - "report generated from a11y CI results; statement published in-app and web"
  tests: [tests/legal/test_a11y_report.py]
  legal: "5378,EN301549"
- id: INT-227
  epic: E14-legal
  phase: P2
  title: "AI governance file: model cards, TR bias/fairness eval (dialect, gender, age), transparency labels, EU AI Act readiness note"
  depends_on: [INT-095, INT-116]
  labels: [area:legal, risk:legal]
  status: todo
  acceptance:
    - "model card per registry entry; fairness eval report on the Turkish eval sets; AI-generated labels asserted in UI tests"
  tests: [tests/legal/test_model_cards_complete.py]
  legal: "AI-ACT-EU"
  sec_row: "llm-boundary"
- id: INT-230
  epic: E15-research
  phase: P2
  title: "Research data pipeline: anonymisation (KSVY-16), research consent gating, export for studies"
  depends_on: [INT-015, INT-038]
  labels: [area:research, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "exports only with research consent + ethics id; anonymisation validated on corpus; register of research extracts"
  tests: [tests/research/test_export_gates.py]
  legal: "KVKK-16,KSVY-16,ETİK"
  sec_row: "learning-loops"
- id: INT-231
  epic: E15-research
  phase: P2
  title: "Study tooling: instruments + analysis notebooks for tracks 1-6 (voice vs typed, triage validation, note quality, psychiatric-signal validation)"
  depends_on: [INT-230]
  labels: [area:research]
  status: todo
  acceptance:
    - "pre-registered analysis scripts; blinded exports; reproducible notebooks under tests"
  tests: [tests/research/test_notebooks_run.py]
  legal: "ETİK"
- id: INT-240
  epic: E16-experience
  phase: P0
  title: "CSAT/NPS/clinician-pulse events + endpoints + rollups"
  depends_on: [INT-035, INT-031]
  labels: [area:experience]
  status: todo
  acceptance:
    - "csat.v1 (1-5 + reason enum + optional text), nps.v1, clinician_pulse.v1; POST /sessions/{id}/csat, /feedback/nps; rollups in services/metrics"
  tests: [tests/experience/test_csat_flow.py]
  legal: "KVKK-5-satisfaction"
  sec_row: "experience"
- id: INT-241
  epic: E16-experience
  phase: P1
  title: "Wait-time metrics end-to-end + SDS-01 style exports"
  depends_on: [INT-240, INT-025]
  labels: [area:experience]
  status: todo
  acceptance:
    - "time_to_first_question, note_ready_after_wrapup, doctor_link_first_open, checkin_to_seen (connector), records_processing emitted and dashboarded"
  tests: [tests/experience/test_wait_metrics.py]
  sec_row: "experience"
- id: INT-242
  epic: E16-experience
  phase: P1
  title: "NPS scheduling + clinician pulse survey cadence"
  depends_on: [INT-240]
  labels: [area:experience]
  status: todo
  acceptance:
    - "monthly NPS prompt honoring quiet hours; quarterly pulse; opt-outs respected"
  tests: [tests/experience/test_survey_cadence.py]
  legal: "6563-IYS"
  sec_row: "experience"
- id: INT-250
  epic: E17-release
  phase: P2
  title: "Tenant onboarding: config, branding, packs, DPA signature via KEP/e-imza, runbook"
  depends_on: [INT-189, INT-213]
  labels: [area:release, risk:legal]
  status: todo
  acceptance:
    - "tenant cannot go live without signed DPA + residency attestation recorded (gate test)"
  tests: [tests/release/test_tenant_gate.py]
  legal: "KVKK-8,DPA"
  sec_row: "tenants"
- id: INT-251
  epic: E17-release
  phase: P3
  title: "Billing: hospital e-Fatura via provider; patient subscription via PSP (iyzico/PayTR); never store PAN"
  depends_on: [INT-222]
  labels: [area:release, risk:legal, approval:human-legal]
  status: todo
  acceptance:
    - "PSP-hosted payment; webhooks verified; invoices archived per tax rules; PAN absence proved by scan"
  tests: [tests/release/test_no_pan.py]
  legal: "6502-MSY,VUK"
  sec_row: "billing"
- id: INT-252
  epic: E17-release
  phase: P1
  title: "Release process: semver, changelog, signed artifacts, store submission checklist, release-gate checklist in console"
  depends_on: [INT-019, INT-183]
  labels: [area:release]
  status: todo
  acceptance:
    - "`make release` assembles evidence (tests, safety, security, evals, latency, coverage, self-host matrix, legal deltas) and blocks on any red"
  tests: [tests/release/test_release_gate.py]
  sec_row: "cicd"
- id: INT-253
  epic: E17-release
  phase: P1
  title: "Localization completeness: tr 100 percent, en 100 percent; ar planned P3 with RTL audit"
  depends_on: [INT-130]
  labels: [area:release]
  status: todo
  acceptance:
    - "i18n lint fails on missing keys; clinical tr reviewed flag enforced"
  tests: [tests/release/test_i18n_complete.py]
  legal: "805"
```

### 3.12 `docs/adr/` — write ADR-000 (template) and ADR-001…020 as Accepted, one paragraph context/decision/consequences each:
001 Expo + LiveKit for realtime voice · 002 openEHR canonical, FHIR exchange · 003 Protocol DSL with monotonic red flags · 004 Deterministic triage, LLM as extractor · 005 No raw audio retention · 006 Provider-agnostic speech/LLM gateways · 007 TR-residency deployment profile · 008 Doctor Link as universal connector · 009 Two-layer voice runtime (Realtime Talker with six tools + Clinical Backend Agent with FIFO Work queue; non-blocking; safe insertion window; RED is the only preemption) — cite github.com/QwenAudio/qwen-audio-agent docs/architecture.md as prior art · 010 Voice profiles (`cascade_fast` default, `s2s_cloud` eval-gated opt-in, `residency_tr`) under one contract · 011 Protocol clip cache and ask-ahead/reconcile-behind · 012 Observer lanes (parallel psychiatric/affect signals; read-only; off the critical path) · 013 All-branch taxonomy, cluster packs and maturity model · 014 Two learning loops (per-patient deterministic; cross-patient proposal-only with clinician gate and canary) · 015 Admin console, metrics catalogue as code, self-hosting matrix as release gate · 016 Self-hosted observability/eval stack (OTel + Grafana/SigNoz, Langfuse, Unleash, Keycloak, Argo CD) · 017 Security architecture baseline (Keycloak + OTP/attestation/DPoP; OpenBao envelope encryption + tokenization; mesh mTLS; WAF + egress allow-list; de-identification gateway; signed artifacts + admission control; WORM audit; Wazuh/Falco/CrowdSec) · 018 Technical-monitoring baseline (health/ready/metrics/version contract; OTel everywhere; SLOs + error budgets + burn-rate alerts; synthetic probes; chaos/load gates) · 019 Issue→PR delivery with zero-placeholder/evidence gates and human-approval labels · 020 Medical-device boundary behind `device_functions` (Stage A clinical investigation; Stage B CE Class IIa) and the firm legal map (06).

## 4. Phase 0 execution order (do this now)
1. `git init` (or verify clone), create layout, write all §3 files verbatim, create `scripts/hooks/*` and make them executable, write `.github/workflows/ci.yml`, `Makefile`, `.env.example`, `.gitignore`, `LICENSE` (Apache-2.0 for packages/protocols; proprietary for apps/services unless told otherwise — ask me once via a blocked note if unsure, then continue).
2. Copy `docs/blueprint/` from `/Users/ario/Downloads/previsit/intake-blueprint/` if present; otherwise create `docs/blueprint/README.md` pointing to this prompt.
3. Execute **INT-001 → INT-004** in this session, each as its own branch+PR+merge with full TDD and evidence files (INT-004 ends with the whole backlog live on GitHub and the board populated). Then continue straight into **INT-010 → INT-025** the same way for as long as the session allows; stop at a clean issue boundary and print: merged PRs, open human-gated PRs, test counts, coverage, blockers.
4. Write `docs/PROGRESS.md` entries per LOOP.md for each issue. Set `LOOP_STATUS: CONTINUE`.
5. Tell me how to run `./loop.sh 40` to walk the rest of P0 in order, and list exactly which `approval:human-*`, `live-smoke` and `gpu` items will wait for me (clinician pack sign-offs INT-043…055, legal texts INT-210/211/212, vendor keys for INT-095/111/161, GPU for INT-097). CI stays vendor-free; the clip cache uses the mock voice until INT-095's live smoke.

## 5. Quality bar for this session (self-check before you say "done")
- A fresh clone + `make setup && make check` passes on macOS with Docker running.
- `protocols resolve --department ROMATOLOJI --visit-type followup --context tests/fixtures/context/oncology_patient.json` prints a resolved protocol whose red flags include both rheumatology and oncology-overlay rules, and whose hash is stable across runs.
- `make safety` runs ≥ 200 triage goldens; a deliberately broken RED rule makes it fail (prove with a temporary mutation, then revert).
- Schemas round-trip FHIR ↔ internal under hypothesis; one Bundle validates on HAPI in the integration job.
- No file in the repo writes audio; `audio_retention_guard` exists even before any audio code.
- `make runtime-sim SCENARIO=RT-03 PROFILE=cascade_fast` (Backend stalled 10 s on a fake clock) shows the Talker still answering within budget; `SCENARIO=RT-02` shows RED preemption ≤ 300 ms; the six-tool introspection test exists and a temporary seventh tool makes it fail (prove, then revert).
- `protocols compile --voice mock` produces the same clip manifest hashes on two runs.
- `protocols coverage` shows every branch in `taxonomy/branches.yaml` resolving to a cluster pack; resolving an L0 pack for a session raises; `overlay_monotonicity` passes.
- `make admin` serves the console with mock data; the release-gate script blocks when a PHI-path component is marked non-self-hostable; a metric emitted outside the catalogue fails `make check` (prove with a temporary metric, then revert).
- `make security` is green; a planted secret, a critical CVE in a pinned test dependency, and a PHI pattern in a fixture each fail it (prove, then revert); images and the protocol bundle are signed on a tag build.
- Every service answers `/healthz` `/readyz` `/metrics` `/version`; `make slo-report` prints SLO definitions and current (mock) attainment; a call from the api to an unlisted host is refused and logged; the audit-chain verifier detects a tampered row.
- Issue machinery works end-to-end: `gh issue list` shows the backlog with labels/milestones; the first PRs are merged with `Closes #n`; `scripts/ci/no_placeholders.sh` fails on a planted TODO and a planted `pytest.mark.skip` (proved, reverted); `evidence_check` fails a PR without a red-run section (proved, reverted); `make backlog-status` prints phases, blockers and awaiting-human PRs.
- All docs from §3 exist verbatim; ADRs 000–020 written; issues.yaml statuses current; docs/blueprint/11 regenerated and matching; PROGRESS.md has entries.

## 6. Reference snippets (verified 20 Aug 2026 — still re-check each vendor doc the day you implement the adapter; APIs move monthly)
**LiveKit Agents — `cascade_fast` session sketch (P1):**
```python
from livekit.agents import AgentSession, Agent, inference
from livekit.plugins import silero, soniox            # confirm plugin names with `pip index versions livekit-plugins-soniox`
session = AgentSession(
    vad=silero.VAD.load(min_silence_duration=0.25),
    turn_detection=inference.TurnDetector(),          # v1 audio-based EOU, Turkish supported (text-based plugin is deprecated)
    stt=soniox.STT(model="stt-rt-v5", language_hints=["tr"], context=medical_terms, enable_endpoint_detection=True),
    llm=llm_gateway.talker_model(),                   # small, cached prompt, speech-text only
    tts=soniox.TTS(language="tr"),                    # or elevenlabs / inworld; clip player bypasses TTS for scripted steps
    preemptive_generation=True,
)
```
**`s2s_cloud` (flagged):** the same `AgentSession` with `llm=openai.realtime.RealtimeModel(model="gpt-realtime-2")` (EU base URL / EU residency project) or `google.realtime.RealtimeModel(model="gemini-3.1-flash-live-preview")` on a Vertex EU region; keep `turn_detection=inference.TurnDetector()` with a separate STT so endpointing stays vendor-independent; register the **same six tools**; run the output-transcript monitor for PolicyGuard.
**Soniox direct (P1):** WebSocket `wss://stt-rt.soniox.com/transcribe-websocket`, config `{"model":"stt-rt-v5","language_hints":["tr"],"enable_endpoint_detection":true,"context":{"terms":[...from packages/protocols/vocab/tr_medical.txt...]}}`; TTS v2 is full-duplex on one socket (text in, audio out).
**Inworld STT with voice profiling (P1, affect tap only):** `wss://api.inworld.ai/stt/v1/transcribe:streamBidirectional`, first message `{"transcribeConfig":{"modelId":"soniox/stt-rt-v5","audioEncoding":"LINEAR16","sampleRateHertz":16000,"language":"tr-TR","voiceProfileConfig":{"enableVoiceProfile":true,"topN":3},"inworldConfig":{"voiceProfileThreshold":0.6}}}`, then `{"audioChunk":{"content":"<base64 100ms pcm>"}}`, `{"endTurn":{}}`, `{"closeStream":{}}` — verify field names before implementing.
**`residency_tr` serving (P2):** `vllm serve Qwen/Qwen3-ASR-1.7B` via the Qwen3-ASR toolkit's streaming server (language `tr`, context text = medical vocab); `vllm serve Qwen/Qwen3-30B-A3B-Instruct-2507` (or `google/medgemma-27b-text-it` under HAI-DEF terms) with JSON-schema-constrained decoding for extraction; Chatterbox Multilingual v3 (`pip install chatterbox-tts`, `language_id="tr"`, streaming; or the NVIDIA NIM container) for TTS; Piper `tr_TR` as fallback; self-hosted LiveKit server + TURN in the Turkish DC. Optional prosody-aware understanding: Qwen3-Omni-30B-A3B-Instruct with audio in → text out (Turkish speech input is supported; do **not** use its speech output for Turkish).
**Clip cache (P1):** `protocols compile --voice <voice_id>` → for each scripted `text_tr`: `clip_id = sha256(text_tr + voice_id)`; synthesise once via `SpeechGateway.tts` (mock in dev/CI), store Opus in MinIO `clips/<voice_id>/<clip_id>.opus`, write `clip_manifest.json`; Talker plays from manifest when `kind=scripted|confirm|follow_up` and the hash matches, else falls back to TTS.
**DAM (P3 research only):** `KintsugiHealth/dam` pipeline expects ≥ 30 s single-speaker audio; output `{depression, anxiety}` ordinal; keep the indeterminate band; never in patient UI.
**Langfuse self-hosted (P1):** docker compose from `github.com/langfuse/langfuse` (Postgres + ClickHouse + Redis + MinIO/S3); send LLM spans via the OTel endpoint; create annotation queues `note_quality`, `hallucination_audit`, `false_red_review`; run experiments in CI with the Langfuse GitHub Action and gate on scores; alerts on p95 latency and eval scores.
**Probe registry row (P0):** `{"component":"stt.qwen3_asr","self_hostable":true,"self_hosted_now":false,"host":"vllm://tr-dc-gpu-1","license":"Apache-2.0","probe":"POST /v1/audio/transcriptions (1 s tr wav)","budget_ms":800,"fallback":["stt.whisper_local"],"phi_path":true}`.
**Loop 2 proposal sketch (P2):** Inspectors (LLM, de-identified traces) → findings JSON; Architect aggregates with `k>=10, clinics>=2, weeks>=2` → `Proposal{type, diff, evidence:{stats, exemplars_deid, simulator_run, goldens, latency, shadow_replay, langfuse_experiment}}` → `gh pr create` against `packages/protocols`; GEPA job: `dspy.GEPA(metric=clinician_edit_distance_judge, trainset=accepted_notes_deid, valset=heldout)` on the extraction module only.
**Health contract (P0):** `from platform.health import mount_health; mount_health(app, readiness=[db_check, redis_check, queue_check])` → `/healthz` 200 always when process alive; `/readyz` 503 with `{"checks":{"db":"ok","redis":"timeout"}}` on failure; `/version` `{"git_sha":..,"built_at":..,"sbom_digest":..}`.
**OTel collector redaction (P0):** `processors: {transform/redact: {log_statements: [{context: log, statements: ["replace_all_patterns(attributes, \"value\", \"\\b[1-9][0-9]{10}\\b\", \"[TCKN]\")", "replace_all_patterns(attributes, \"value\", \"\\b0?5[0-9]{9}\\b\", \"[PHONE]\")"]}]}}` plus an attribute allow-list; unit-test the pipeline with fixture logs.
**Envelope encryption (P0):** `dek = openbao.transit.generate_data_key(name=f"tenant-{tenant_id}")`; encrypt field with AES-256-GCM (`cryptography`), store `ciphertext || nonce || wrapped_dek || key_version`; rotation = rewrap; crypto-shredding = destroy the tenant/patient key.
**Tokenization (P0):** `pseudonym = hmac_sha256(key_id, tckn)`; app tables store `pseudonym`; `identity_vault` stores `(pseudonym, encrypted_tckn)`; only the tokenization service role can read the vault; logs get `pseudonym[:8]`.
**Egress allow-list (P0):** Envoy/Traefik forward-proxy with `allowed_hosts: [api.soniox.com, api.inworld.ai, api.elevenlabs.io, api.anthropic.com, api.openai.com, generativelanguage.googleapis.com]` per profile; everything else 403 + `security.egress_denied` event; the list is hook-protected and changes require the vendor-transfer register entry.
**CI security job (P0):** `gitleaks detect` → `semgrep ci` → `bandit -r services packages` → `trivy fs --severity CRITICAL,HIGH --exit-code 1 .` → `osv-scanner -r .` → `checkov -d infra` → `syft . -o cyclonedx-json > sbom.json` → (on tags) `cosign sign --yes $IMAGE` + `actions/attest-build-provenance`; `cosign sign-blob packages/protocols/dist/bundle.tar.gz`.
**SLO file (P0):** `docs/slo/voice-runtime.yaml`: `slis: {session_success: {good: sessions_first_question_total, total: sessions_started_total}}`, `objective: 0.995`, `window: 30d`, `alerts: [{burn_rate: 14.4, long: 1h, short: 5m, severity: page}, {burn_rate: 6, long: 6h, short: 30m, severity: page}, {burn_rate: 1, long: 3d, short: 6h, severity: ticket}]`, `runbook: docs/runbooks/voice-session-success.md`.
**MHRS taxonomy seed:** list in `docs/blueprint/09 §1`; keep `verify_live_list: true` until the product owner confirms against the live MHRS branch list.
**Corrections to older notes:** there is no MedGemma 1.5 27B — 1.5 is 4B only (useful as a lab-report→JSON extractor candidate); 27B is MedGemma 1. Qwen3.5-Omni is API-only (not residency). OpenAI's Realtime *beta* interface was removed on 12 May 2026 — target the GA session shape.

Begin with a 10-line plan, then execute. Keep messages terse. Do not pause for approval unless §0 "When to stop" applies.
