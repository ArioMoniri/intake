# 11 · Issue backlog — every feature as an issue, every issue as one PR (v2.0, 27 Aug 2026)

> This file is the human-readable rendering of `docs/backlog/issues.yaml`, which the master prompt (07 §3.11) embeds verbatim and which `scripts/backlog/sync_issues.py` pushes to GitHub. Delivery rules live in 07 (LOOP/DoD/TDD): one issue at a time, tests first, no placeholders, no demos in product code, no postponement — an issue blocked on a key or hardware stays open with a `blocked:*` label and a line in `docs/backlog/blockers.md`; it is never closed by mocking the missing piece. Labels: `approval:human-*` means the PR is left open for the named human decision (clinical sign-off, legal counsel, vendor contract, infra spend); `live-smoke` and `gpu` mean the issue only closes with recorded evidence from the real vendor or the real hardware. `legal:` codes resolve in `06 §1`; `sec_row:` names the row in `10 §9`.

> ⚠ **Reconciled 27 Aug 2026 against `00_STATE.md`.** Seven issues carried acceptance criteria referencing deleted model pins, a profile that no longer exists, or a superseded device classification. **Every one is corrected in place with the correction stated inline; none is deleted**, because a deleted issue reappears in three weeks carrying the same wrong acceptance. The corrected ids are **INT-095, INT-097, INT-098 (withdrawn-in-place), INT-111, INT-115, INT-124, INT-216**, and **INT-043 is front-loaded**. The full reconciliation note is at the foot of this file.
>
> Before deciding an issue is blocked, read **`HUMAN_BLOCKERS.md`** — it says who can unblock it and what one sentence they must answer. `blocked:*` lines in `docs/backlog/blockers.md` carry the matching `HB-*` id.

Phase counts: P0: 91 · P1: 45 · P2: 36 · P3: 3 · total 175 issues — ⚠ **P2 36 / P3 3, not 37 / 2**: INT-097 (`residency_tr_models`) moves to P3 with D11's media/model split. INT-098 is withdrawn in place, so **174 workable**.


## E00-governance

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-001 | P0 | Monorepo bootstrap: workspaces, Makefile, pre-commit, compose.dev | — | — | pnpm>=9 + uv workspaces per 07 §2 layout; `make setup` from a clean clone on macOS `make check` = ruff + mypy --strict + pytest + eslint + tsc + vitest across all packages docker-compose.dev.yml: postgres16+pgvector, redis, ehrbase, hapi, minio; `make dev` healthy with real containers (no stub services) pre-commit: gitleaks, semgrep, ruff, eslint; Convent... | KVKK-12 | platform |
| INT-002 | P0 | CI base + zero-placeholder and evidence gates | INT-001 | — | ci.yml runs make check on every PR with caching and no vendor network scripts/ci/no_placeholders.sh fails on TODO|FIXME|XXX|NotImplementedError|pytest.mark.skip|xfail|it.skip|test.todo|`pass  #`|lorem|placeholder|dummy|demo-only outside tests/fixtures allow-list scripts/ci/evidence_check.sh: PR must contain docs/evidence/<ISSUE>.md with red-run + green-ru... | — | cicd |
| INT-003 | P0 | ADR-000..020 written; blueprint mirrored to docs/blueprint | INT-001 | — | docs/adr/ has ADR-000 template and 001..020 Accepted, one paragraph each (list in 07 §3.12) docs/blueprint/ contains files 01..11 verbatim; docs/index.md links everything | — | — |
| INT-004 | P0 | Backlog machinery: issues.yaml -> GitHub issues/labels/milestones/project; loop runner | INT-002 | — | docs/backlog/issues.yaml (this backlog) validated by schema test; scripts/backlog/sync_issues.py creates/updates GitHub issues via gh with labels ph:*, area:*, risk:*, approval:*, milestones P0..P3 and a Project board Backlog/Ready/In progress/In review/Blocked/Done .github/ISSUE_TEMPLATE/feature.yml + pull_request_template.md with the DoD checklist and m... | — | — |

## E01-platform

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-010 | P0 | packages/intake_platform/health: /healthz /readyz /metrics /version + contract test | INT-001 | — | mount_health(app, readiness=[...]) for FastAPI, workers, voice-runtime; /version returns git_sha, built_at, sbom_digest health_contract test enumerates every service in the repo and fails on a missing endpoint or missing probe registration | — | monitoring-contract |
| INT-011 | P0 | packages/intake_platform/otel: shared tracing/metrics/logs + PII redaction processor | INT-010 | — | propagates trace_id, hashed session_id, tenant_id, protocol_hash, prompt_version; JSON logs; no-PHI invariant OTel collector config with redaction (TCKN checksum regex, 05x phone, IBAN, names allow-list) unit-tested on fixture logs | KVKK-12 | observability-pipeline |
| INT-012 | P0 | packages/intake_platform/security: headers, rate limiter, idempotency keys | INT-010 | — | security headers middleware (CSP, HSTS, nosniff, frame-deny); Redis token-bucket limiter per user/IP/tenant with tests; idempotency-key middleware for POSTs | KVKK-12 | api |
| INT-013 | P0 | Tokenization service + identity vault (TCKN/phone never in clear) | INT-012, INT-017 | risk:security | HMAC-SHA-256 keyed pseudonym for joins; encrypted value in identity_vault readable only by the tokenization role; logs get pseudonym[:8] roundtrip + key-rotation tests; grep-test proves no app table stores raw TCKN/phone | KVKK-6,KVKK-12,2018-10 | identifiers |
| INT-014 | P0 | Envelope encryption (OpenBao Transit) + rotation + crypto-shredding | INT-017 | risk:security | AES-256-GCM per-field with per-tenant DEKs wrapped by OpenBao Transit; file-KEK provider for tests; rewrap rotation; destroy-key == hard delete tamper detection test; rotation test; crypto-shred proves ciphertext unrecoverable | KVKK-7,KVKK-12,2018-10 | data-at-rest |
| INT-015 | P0 | De-identification service: Presidio + Turkish recognizers + leak-rate corpus | INT-011 | risk:security | recognizers: TCKN (checksum), TR phone, IBAN, names (TR NER), addresses, date shifting; sits in front of every cloud model call and Loop-2 exports synthetic corpus with labels; measured leak rate < 0.1 percent gate in CI | KVKK-9,KVKK-16 | cloud-boundary |
| INT-016 | P0 | Hash-chained audit log + WORM export + daily verifier | INT-014 | — | audit.v1 events chained (prev-hash), verifier job, MinIO object-lock bucket copy; patient-visible access-log view model tamper test flips one row and the verifier detects it | KVKK-12,KSVY-7 | audit |
| INT-017 | P0 | OpenBao dev server + per-service policies + dynamic DB creds | INT-001 | — | compose service; api/workers/voice-runtime read secrets from OpenBao; .env holds only address/token in dev; dynamic Postgres creds TTL 24h test proves a service boots with OpenBao and fails closed without it in prod mode | KVKK-12,2018-10 | secrets |
| INT-018 | P0 | Egress proxy with vendor allow-list + transfer log | INT-001 | risk:legal | forward proxy in dev compose; only allow-listed vendor hosts reachable from PHI-path services; every egress logged {host,purpose,bytes,ts} feeding the vendor-transfer register; denial emits sec.egress_denied test: call to unlisted host is refused and logged | KVKK-9,TRANSFER-2024 | cloud-boundary |
| INT-019 | P0 | security.yml CI job: full gate set + signing | INT-002 | risk:security | gitleaks, semgrep+bandit, eslint-security, trivy fs/image/IaC + osv-scanner fail on critical/high, checkov, license allow-list (AGPL flagged), syft SBOM artifact, cosign keyless signing + SLSA provenance for images and protocol bundles on tags, schemathesis fuzz, PHI-pattern scan of fixtures `make security` runs the same list locally; planted secret, plan... | KVKK-12,2018-10 | cicd |
| INT-020 | P0 | Threat model + incident runbook + PR linkage | INT-003 | risk:legal | docs/security/threat-model.md STRIDE+LINDDUN seeded from 10 §9; docs/security/incident-runbook.md includes KVKK Board 72h form flow (2019/10), data-subject notice templates, USOM/Siber Guvenlik Baskanligi report per 7545, hospital DPA notice PR template requires the 10 §9 row link; missing link fails evidence_check | KVKK-12-breach,7545 | incident-response |
| INT-021 | P0 | SLO files + Prometheus rules + Grafana dashboards as code + runbooks | INT-011 | — | docs/slo/{api,voice-runtime,workers}.yaml with SLIs/objectives/burn-rate alerts (14.4x/1h, 6x/6h page; 1x/3d ticket); generator emits Prometheus rules; golden-signal dashboards provisioned; runbook per alert | — | monitoring-contract |
| INT-022 | P0 | services/probes: synthetic checks + self-hosting registry + release gate | INT-010, INT-021 | — | registry table {component,self_hostable,self_hosted_now,host,license,probe,budget_ms,fallback,phi_path}; 60s runner with real dev checks (DB, Redis, MinIO, EHRbase, HAPI, OpenBao seal, LiveKit room join, cert expiry, backup freshness) release-gate script blocks when an enabled phi_path component lacks a healthy self-hosted fallback | G2019-12 | self-hosting |
| INT-023 | P0 | Observability stack profile: OTel+Prom+Loki+Tempo+Grafana (or SigNoz), Unleash, Keycloak, GlitchTip | INT-011 | — | compose profile obs; flags via OpenFeature with in-memory provider default and Unleash provider behind config; Keycloak realm export for dev; GlitchTip DSN wired behind flag with PHI-scrub tests | — | observability-pipeline |
| INT-024 | P0 | k6 smoke + lk load-test recipe + chaos harness (vendor kill -> typed <=2s) | INT-022 | — | k6 API smoke in CI (staging profile); documented lk load-test recipe; chaos harness kills a mock vendor adapter and asserts typed fallback within 2s and metrics emitted | — | resilience |
| INT-025 | P0 | Metrics catalogue as code + completeness test | INT-011 | — | packages/clinical-schemas/metrics_catalog.yaml holds every id/unit/target/owner from 08 §4; emitting an uncatalogued metric fails make check (proved then reverted in evidence) | — | monitoring-contract |

## E02-data

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-030 | P0 | Postgres schema + Alembic + RLS per tenant + pgaudit | INT-013, INT-014 | — | core tables (patients pseudonymised, sessions, slots, notes, consents, shares, documents, events) with RLS by tenant and role; pgaudit on; least-privilege roles RLS tests prove tenant A cannot read tenant B even with SQL | KVKK-12,KSVY-7 | data-at-rest |
| INT-031 | P0 | clinical-schemas: pydantic models + TS codegen + event schemas | INT-030 | — | PreVisitNote, PatientSummary, ExtractedRecordItem, ConsentScope, TriageResult, SessionState, PatientOverlay, ObserverState, Proposal; events csat.v1, nps.v1, clinician_pulse.v1, audit.v1, security.v1; TS generated from OpenAPI | — | — |
| INT-032 | P0 | EHRbase canonical store: OPT templates + client + roundtrip | INT-031 | — | intake composition template (OPT) uploaded on boot; write/read composition per session; contribution audit integration test writes and reads a composition against EHRbase container | KSVY-5 | clinical-core |
| INT-033 | P0 | HAPI FHIR exchange: mappers internal<->R4 + validation | INT-031 | — | QuestionnaireResponse, Observation, Condition, MedicationStatement, AllergyIntolerance, RiskAssessment, Flag, Composition, Bundle; hypothesis roundtrip; Bundle validates on HAPI container | — | — |
| INT-034 | P0 | MinIO document store: signed URLs + AV hook + WORM audit bucket | INT-016 | — | short-TTL signed URLs; server-side encryption; object-lock on audit bucket; bucket policies least-privilege | KVKK-12 | documents |
| INT-035 | P0 | Redis streams event bus + consumer framework + DLQ | INT-031 | — | typed producers/consumers with retries, DLQ, exactly-once handlers via idempotency keys; consumer lag metric | — | — |
| INT-036 | P0 | Retention & destruction engine (policy as code, 6-month periodic destruction, logs) | INT-030 | risk:legal | policy file mirrors 06 §3 retention matrix; scheduled destruction runs at most every 6 months per DEST-2017; destruction log kept 3 years; lane windows zeroing verified; raw-audio guard extended time-travel tests prove each class purges on schedule | KVKK-7,DEST-2017 | retention |
| INT-037 | P0 | DSAR endpoints: export (FHIR+PDF), delete (crypto-shred, 30-day grace), rectify + 30-day SLA tracker | INT-014, INT-033 | risk:legal | /export bundles openEHR+FHIR+PDF; /me delete schedules shred with grace and cancels shares; rectification writes audit; SLA clock per KVKK-13 with console queue | KVKK-11,KVKK-13 | dsar |
| INT-038 | P0 | Consent service: versioned objects, consent_guard middleware, re-prompt on change | INT-030 | risk:legal | purposes exactly as 06 §4 (core, voice, wellbeing, lane:*, documents, learning:*, satisfaction, share:*, research); text_hash binds shown text; route-table scan test proves every data route declares scopes; withdrawal cascades within 1 min consents are free, specific, informed, unbundled: UI cannot pre-tick, cannot gate core service on optional purposes (... | KVKK-5,KVKK-6,AYD-2018 | consent |

## E03-protocols

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-040 | P0 | Protocol DSL: schema, loader, validator (extends, monotonic red flags, voice fields) | INT-031 | — | yaml schema with sections/slots/red_flags/overlays/visit_types/voice fields; validator enforces monotonicity, follow_up_tr presence, instruments allow_paraphrase=false | — | protocol-registry |
| INT-041 | P0 | Compiler: FHIR Questionnaire + openEHR bindings + Pydantic + TS + clip manifest, deterministic | INT-040, INT-033 | — | two runs produce identical hashes; resolved-protocol hash pinned per session; compile artifacts under packages/protocols/dist | — | — |
| INT-042 | P0 | Taxonomy: all MHRS branches + clusters + visit types + coverage CLI | INT-040 | — | taxonomy/branches.yaml seeded from 09 §1 with verify_live_list true; every branch resolves to a cluster; `protocols coverage` matrix; unknown booked branch fails a test | — | — |
| INT-043 ⭐ | P0 | **base.intake pack (tr/en) complete per `04 §1` — FRONT-LOADED: unblocks 78 of 175.** *Drafted immediately after INT-001…004 and in the owner's inbox on day 2; v1.4 put it at depth 9, so the agent would work for days before the owner saw the thing everything else waits on. The agent drafts; a **named licensed physician** signs. Adds the six slots `base.life_threat` needs (HB-C6), and the fast-mode turn-budget reconciliation is a **clinical** decision an agent may not make (HB-C5).* | INT-041 | risk:clinical, approval:human-clinical | all base sections/slots/red-flag families/action scripts in B1 Turkish + English; goldens; clip-manifest entries | HHY-15,1219-8 | clinical-content |
| INT-044 | P0 | Cluster pack: medical | INT-043 | risk:clinical, approval:human-clinical | content per 04 §2.1 medical; goldens; compiles clean | HHY-15 | clinical-content |
| INT-045 | P0 | Cluster pack: surgical | INT-043 | risk:clinical, approval:human-clinical | content per 04 §2.1 surgical; goldens | HHY-15 | clinical-content |
| INT-046 | P0 | Cluster pack: sensory | INT-043 | risk:clinical, approval:human-clinical | content per 04 §2.1 sensory; goldens | HHY-15 | clinical-content |
| INT-047 | P0 | Cluster pack: womens_health | INT-043 | risk:clinical, approval:human-clinical | LMP-first ordering, pregnancy-aware asks; goldens | HHY-15 | clinical-content |
| INT-048 | P0 | Cluster pack: child_health (guardian proxy, age bands) | INT-043, INT-133 | risk:clinical, approval:human-clinical | guardian-proxy flow, age-banded items, adolescent private section semantics; goldens | HHY-24,TMK-339 | clinical-content |
| INT-049 | P0 | Cluster pack: mental_health | INT-043 | risk:clinical, approval:human-clinical | full instruments by default, C-SSRS path, safety scripts; goldens | HHY-15 | clinical-content |
| INT-050 | P0 | Cluster pack: dental | INT-043 | risk:clinical, approval:human-clinical | per 04 §2.1 dental incl. anticoagulant/bisphosphonate asks; goldens | HHY-15 | clinical-content |
| INT-051 | P0 | Cluster pack: allied_and_reports | INT-043 | risk:clinical, approval:human-clinical | report visit types, documents checklist, no wellbeing unless opted; goldens | HHY-15 | clinical-content |
| INT-052 | P0 | Cluster excluded: Acil refusal + 112 routing copy | INT-043 | risk:clinical, approval:human-clinical | app refuses pre-visit intake for Acil and shows fixed 112 guidance; test asserts refusal | 1219-8 | clinical-content |
| INT-053 | P0 | Deep pack: internal_medicine | INT-044 | risk:clinical, approval:human-clinical | per 04 §2.2; goldens; L1 after physician approval | HHY-15 | clinical-content |
| INT-054 | P0 | Deep pack: gastroenterology + overlay.oncology_patient | INT-044 | risk:clinical, approval:human-clinical | per 04 §2.2 incl. rf.gi_bleed, rf.neutropenic_fever; goldens | HHY-15 | clinical-content |
| INT-055 | P0 | Deep pack: rheumatology | INT-044 | risk:clinical, approval:human-clinical | per 04 §2.2 incl. HAQ-DI-TR (detailed), DMARD/biologic asks; goldens | HHY-15 | clinical-content |
| INT-056 | P0 | Patient overlays set (8) + overlay_monotonicity property test | INT-043 | risk:clinical | overlays per 04 §2.3 add/tighten only; property test across random compositions | — | learning-loops |
| INT-057 | P0 | Protocol Authoring Agent: L0 drafts for every branch + no-serve guard | INT-042 | — | `protocols generate-l0 --branch <id>` scaffolds from cluster+template with citation placeholders resolved to named Turkish guidance sources; L0 resolution for a live session raises; regeneration idempotent agent has zero access to patient data (import-boundary test) | — | learning-loops |
| INT-058 | P0 | Signed protocol bundles: cosign sign + runtime verification + per-session hash pin | INT-041, INT-019 | risk:security | compiler emits bundle.tar.gz signed; runtime refuses unsigned/tampered; note meta shows protocol hash | — | protocol-registry |
| INT-059 | P0 | Triage golden suite >=200 + mutation tests | INT-080 | risk:clinical | goldens across base+clusters+deep; a deliberately broken RED rule fails the suite (proved, reverted) | — | triage |
| INT-060 | P0 | Clip cache builder per voice + MinIO + coverage test | INT-041, INT-034 | — | all scripted text pre-synthesised per voice at compile keyed sha256(text_tr,voice_id); mock TTS in CI; coverage report per pack | — | voice-runtime |
| INT-061 | P2 | Deep pack: cardiology | INT-044 | risk:clinical, approval:human-clinical | L1 pack for cardiology per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-062 | P2 | Deep pack: neurology | INT-044 | risk:clinical, approval:human-clinical | L1 pack for neurology per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-063 | P2 | Deep pack: endocrinology | INT-044 | risk:clinical, approval:human-clinical | L1 pack for endocrinology per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-064 | P2 | Deep pack: urology | INT-045 | risk:clinical, approval:human-clinical | L1 pack for urology per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-065 | P2 | Deep pack: ophthalmology | INT-046 | risk:clinical, approval:human-clinical | L1 pack for ophthalmology per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-066 | P2 | Deep pack: ent | INT-046 | risk:clinical, approval:human-clinical | L1 pack for ent per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-067 | P2 | Deep pack: orthopaedics | INT-045 | risk:clinical, approval:human-clinical | L1 pack for orthopaedics per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-068 | P2 | Deep pack: dermatology | INT-044 | risk:clinical, approval:human-clinical | L1 pack for dermatology per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-069 | P2 | Deep pack: obgyn | INT-047 | risk:clinical, approval:human-clinical | L1 pack for obgyn per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-070 | P2 | Deep pack: paediatrics | INT-048 | risk:clinical, approval:human-clinical | L1 pack for paediatrics per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-071 | P2 | Deep pack: psychiatry | INT-049 | risk:clinical, approval:human-clinical | L1 pack for psychiatry per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-072 | P2 | Deep pack: oncology | INT-044 | risk:clinical, approval:human-clinical | L1 pack for oncology per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |
| INT-073 | P2 | Deep pack: dentistry_general | INT-050 | risk:clinical, approval:human-clinical | L1 pack for dentistry_general per 09 §2 maturity; goldens; clip coverage | HHY-15 | clinical-content |

## E04-engines

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-080 | P0 | Deterministic triage engine (levels, monotonic merge, action scripts) | INT-040 | risk:clinical | rules only; LLM candidates cap at YELLOW_REVIEW and can never lower a level (type-level); action scripts verbatim | 1219-8,TCY-R11 | triage |
| INT-081 | P0 | IntakeEngine FSM: step kinds, ask-ahead/reconcile-behind, delta mode, overlays | INT-080, INT-056 | — | no LLM inside; answered_pending + follow_up_tr semantics; delta mode driven by PatientOverlay; must_ask coverage computed | — | intake-typed |
| INT-082 | P0 | Patient simulator: personas + scenarios IM-01..IM-14 headless | INT-081 | — | 12+ scripted personas incl. proxy, low-literacy, crisis, oncology; runs in typed and mock voice; used by CI | — | — |
| INT-083 | P0 | Extraction Work: schema-constrained LLM behind gateway + data boundary + eval set | INT-081, INT-015 | — | transcripts wrapped as delimited data; output validated against slot schemas; recorded-fixture contract tests; Langfuse scores wiring (self-hosted) | KVKK-9 | llm-boundary |
| INT-084 | P0 | Note composer + renderers (SOAP, PDF watermark-ready, FHIR bundle) + provenance + disclaimer | INT-083, INT-033 | risk:legal | every fact carries source span; fixed legal disclaimer text (06 §7 wording: hasta beyanina dayanir, hekim degerlendirmesinin yerine gecmez) rendered on note+PDF; golden note snapshots | 1219-8,HHY-15 | notes |
| INT-085 | P0 | Patient summary (B1 Turkish) + reading-level check | INT-084 | — | plain-language summary excludes wellbeing signals; readability metric gate | HHY-15 | — |

## E05-voice

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-090 | P0 | LiveKit server+TURN dev; per-session tokens (10-min minimal grants); audio_retention_guard | INT-001 | risk:security | room tokens grant join+publish mic+subscribe agent only; rooms ephemeral; no recording features enabled; guard test proves no audio write paths anywhere | USHY-12,KVKK-5 | voice-runtime |
| INT-091 | P0 | Talker: six-tool registry + introspection test + streaming PolicyGuard + insertion-window scheduler + clip player | INT-060, INT-090 | risk:clinical | exactly protocol_next, submit_utterance, cancel_work, request_repeat_or_clarify, patient_memory, respond_permission; adding a seventh fails introspection; PolicyGuard <=20ms per sentence | — | voice-runtime |
| INT-092 | P0 | Backend Agent: FIFO Work queue, serialized SessionState, delivery semantics, idempotent | INT-081, INT-035 | — | one Work in flight per session; results {inline,speech_tr,priority}; duplicates impossible (test) | — | voice-runtime |
| INT-093 | P0 | RED preemption path: stop <=150ms, e2e <=300ms (fake clocks) | INT-091, INT-092, INT-080 | risk:clinical | only rules-engine RED carries priority preempt; playback cancel and script start measured on fake clock | — | triage |
| INT-094 | P0 | Runtime invariants 1-11 + RT-01..08 + latency harness | INT-093, INT-110 | — | all invariant tests incl. lanes-stalled-30s; harness reports per-turn budgets per profile | — | voice-runtime |
| INT-095 ⚠ | P1 | **Profile `residency_tr` with real self-hosted adapters (`03 §4.9.1` rows 1–2, 7, 10–11) + on-hardware smoke** — *corrected 27 Aug: was "cascade_fast with Soniox/ElevenLabs"; that profile ceases to exist under the all-self-hosted constraint and every vendor it named is unreachable by construction. The work survives, repointed; the label moves from `approval:human-vendor`/`live-smoke` to `approval:human-infra`/`gpu`, because the evidence that closes it is now on-hardware rather than from a vendor.* | INT-094, INT-018 | approval:human-infra, gpu | real adapters with recorded-fixture contract tests; preemptive_generation on; `make live-smoke PROFILE=cascade_fast` runs one real turn when keys present and stores evidence (latency numbers) — issue closes only with that evidence vendor calls pass egress allow-list and de-identification where text leaves | KVKK-9,TRANSFER-2024 | voice-runtime |
| INT-096 | P0 | Profile typed (full parity fallback) | INT-081 | — | entire intake completable typed; kill-switch target; parity simulator run | — | intake-typed |
| INT-097 ⚠ | P3 | **`residency_tr_models` tier on GPU: compose.residency, node sizing, on-hardware latency evidence** — *corrected 27 Aug. Three defects in the old text: the pins are superseded (`03 §4.9.1` is canonical and this file pins nothing); **Piper `tr_TR` is deleted on licence** — its training set is CC BY-NC-SA 4.0 and the voice is finetuned from a US-English speaker — and Chatterbox has no streaming server; and a **flat `p50 ≤ 900 ms` is the mistake the network work corrected**, targets are per network profile (`02 §8.1`). D11 also split this: the **media half ships in P1 and needs no GPU**; this is only the model half, **gated on a signed capacity contract, never on a date** (HB-I5).* | INT-094, INT-095 | approval:human-infra, gpu, blocked:contract | compose.residency GPU profile; adapters + contract tests; p50<=900ms dynamic measured on target hardware and recorded in evidence — not closable on laptop mocks | G2019-12 | voice-runtime |
| INT-098 🚫 | P2 | **WITHDRAWN in place — `s2s_cloud`. Replaced by a test proving no cloud/S2S profile can be constructed.** *Not deleted, because a deleted issue reappears. Two independent reasons, either sufficient: (1) every model it named is cloud-only, and all models are self-hosted; (2) it was already the wrong shape — an S2S profile cannot meet the contract every profile shares (no clip cache, no verbatim scripted text, and PolicyGuard degrades to **after-the-fact retraction**, meaning the patient already heard the diagnostic sentence). It is faster **and** less safe, presented as an upgrade. Gemini was separately disqualified on sequential-only function calling, and the async-tool-calling argument for GPT-Realtime was **profile-local, not architectural**.* | INT-094 | risk:security | off by default; enabling requires eval gate policy>=99 must-ask>=95 and 4-eyes; retraction path tested; DPIA addendum linked | KVKK-9,TRANSFER-2024,DPIA | voice-runtime |
| INT-099 | P1 | Backchannels + ack styles + preemptive generation + per-profile NFR harness in CI | INT-095 | — | A/B flag; NFR thresholds from 02 §8 asserted per profile with mock and recorded runs | — | — |
| INT-100 | P1 | Vendor failover + circuit breakers + typed fallback <=2s + chaos test | INT-095, INT-024 | — | breaker per vendor; failover order from probes registry; chaos kill proves <=2s | — | resilience |
| INT-101 | P0 | Session budgets + cost metering per component/profile | INT-092 | — | token/char/audio-second budgets enforced; cost.per_session emitted; exhaustion degrades gracefully | — | llm-boundary |
| INT-102 | P1 | Adversarial suite RT-09..14 in make safety + nightly LLM red-team job | INT-094, INT-083 | risk:security | injection by speech and hidden-PDF text, triage manipulation, proxy impersonation, spoken TCKN masking, vendor failover — all pass; nightly job budgeted | — | llm-boundary |
| INT-103 | P1 | Mobile voice client: LiveKit RN, permissions, network-quality per turn, reconnect, background | INT-130, INT-090 | — | mic permission copy per store rules; RTT/jitter/loss attached to turns; reconnect resumes session; background pauses safely | STORE | mobile |

## E06-lanes

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-110 | P0 | Lane framework: budgets, backpressure, ObserverState, per-lane consent, type-level read-only | INT-092, INT-038 | risk:clinical | lanes cannot write slots/triage (compile-time); stalled lanes never delay speech (fake clock); frames dropped under load with metric | KVKK-6 | observer-lanes |
| INT-111 ⚠ | P1 | **affect lane: self-hosted SER in-process on the agent worker (`03 §4.9.1` row 14) + a required Turkish eval set** — *corrected 27 Aug: the Inworld vendor adapter is gone (D2 already put the open SER path in every profile; the self-hosting constraint removed the socket). Note **`emotion2vec+` is disqualified on licence** — FunASR MODEL_LICENSE v1.1, "reference and learning purposes only", with a **speech-conduct revocation clause** and a unilateral amendment clause, and its GitHub MIT badge is decorative because the repo has no LICENSE file. Label moves to `approval:human-clinical`: what gates this lane is a Turkish evaluation, not a contract.* | INT-110 | approval:human-clinical | confidence>=0.6, accent ignored; per-section aggregate only; Turkish eval report checked in before enabling by default | KVKK-6-lane | observer-lanes |
| INT-112 | P0 | linguistic lane: TR lexicons + prosody stats + crisis bypass to triage | INT-110, INT-080 | risk:clinical | crisis lexicon hits route deterministically to C-SSRS path (test); markers aggregate per section | — | observer-lanes |
| INT-113 | P1 | asr_quality lane: shadow-STT disagreement + confirm-by-card trigger | INT-110, INT-095 | — | sampled turns compared; wer proxy metric; low-confidence medical terms trigger confirm cards | — | — |
| INT-114 | P1 | engagement lane -> satisfaction proxies + pacing hints | INT-110 | — | answer latency, interruptions, silence ratio into engagement{} and metrics | — | — |
| INT-115 ⚠ | P2 | **acoustic lane (M3, investigational device module): our own ordinal head, in-memory window, zeroing, study assertion** — *corrected 27 Aug, three defects. **(a) "DAM weights" — Kintsugi DAM is DROPPED (D14)**: the vendor dissolved Feb 2026 after failing FDA De Novo, so Apache-2.0 would hand us the weights and make us the legal manufacturer of a Class IIb function **with no design history file** and nobody left to ask. The lane survives; the model does not. **(b) "research flag / research tenants" understates the gate** — this is an investigational device module (D4) whose only lawful home is MDR Art. 62 ff. / TCY m.61 ff.; there is no shadow mode. **(c) "indeterminate band preserved" mislabels the output** — the released thresholds are a severity trichotomy against PHQ-9 cutpoints and there is **no indeterminate band anywhere in them**, so the wording implied a safety hedge that does not exist; and the **anxiety head is quaternary, not ternary**.* | INT-110, INT-117 | risk:clinical, approval:human-clinical, blocked:study-site | flag confined to research tenants with `research` consent; window zeroed after scoring (test); indeterminate band preserved; no patient-facing output | KVKK-6-lane,ETİK | observer-lanes |
| INT-116 | P0 | Wellbeing engine: PHQ-2/GAD-2 -> PHQ-9/GAD-7 -> C-SSRS, crisis script, verbatim items, clinician-only outputs | INT-081, INT-112 | risk:clinical, approval:human-clinical | validated Turkish items verbatim; scoring deterministic; crisis path completion tested end-to-end; outputs never in patient summary | HHY-15,MDSW | wellbeing |
| INT-117 | P0 | device_functions flag: MDSW boundary enforced (Stage A non-device vs investigation mode) | INT-116, INT-093, INT-038 | risk:legal, approval:human-legal | with flag off (commercial default until CE): no automated patient-facing triage advice and no automated severity interpretation; static 112 text at fixed points; red-flag answers shown to clinician as patient-reported data; shadow triage logged for clinical evaluation with flag on (investigation tenants only, bound to an approved study id): full RED preem... | TCY-R11,TCKAY,3359-Ek10 | device-boundary |

## E07-records

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-120 | P0 | Upload pipeline: ClamAV, sniffing, limits, sandboxed OCR | INT-034 | risk:security | AV scan before processing; OCR in seccomp-sandboxed worker; malformed/fuzz PDFs never crash host | KVKK-12 | records |
| INT-121 | P0 | Document extraction -> FHIR with provenance + confirm cards + eval corpus | INT-120, INT-083 | — | labs/meds/diagnoses extracted with source boxes; patient confirms before use; accuracy metric on corpus >=90 percent LOINC+unit | — | records |
| INT-122 | P1 | e-Nabız export/PDF import parser + MHRS SMS screenshot OCR | INT-121 | — | patient-exported e-Nabiz documents parsed; MHRS SMS screenshot -> visit fields; no scraping of e-Nabiz (no third-party API exists; legal note enforced) | KSVY-9,KSVY-10 | records |
| INT-123 | P1 | pgvector record index (RLS, per-patient namespace) + retrieval Work | INT-030, INT-121 | — | embeddings scoped by patient+consent; retrieval cited into notes with provenance | — | records |
| INT-124 ⚠ | P2 | **Lab-report→JSON via the self-hosted extraction LLM (`03 §4.9.1` row 9) + Turkish unit-resolution eval** — *corrected 27 Aug: **MedGemma fails the licence constraint outright** — every MedGemma model, 1.5-4B included, is Health AI Developer Foundations licensed, and 27B is additionally gated, `license: other` and tagged `en`. (There is no MedGemma 1.5 27B; 1.5 is 4B only.) The eval now has to carry the Turkish document hazards: **never substring-match `üre`** (Üre vs BUN differ by 2.14× and `Üre Nitrojeni` means BUN), magnitude outranks the printed unit token, and the decimal separator is resolved **per value**, not per document.* | INT-121 | gpu | adapter behind gateway; eval vs corpus; HAI-DEF terms recorded in model registry | — | records |

## E08-mobile

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-130 | P0 | Expo app shell: SDK 57 dev build, navigation map per 02, i18n tr-first, theme, a11y base | INT-001 | — | navigation exactly per 02 §4 incl. me/learned; tr+en resource files; dynamic type | 805 | mobile |
| INT-131 | P0 | Onboarding & auth: OTP + attestation + DPoP + biometrics + SecureStore + pinning + FLAG_SECURE | INT-130, INT-012, INT-013 | risk:security | OTP limits per 10 §2; App Attest/Play Integrity on OTP+session; refresh rotation with reuse detection; biometric gate; clinical screens FLAG_SECURE; jailbreak -> typed+warn | KVKK-6,KVKK-12 | onboarding |
| INT-132 | P0 | Consent UI: layered, versioned, lane sub-toggles, learning, satisfaction; who-sees-what | INT-038, INT-130 | risk:legal, approval:human-legal | texts loaded from docs/legal with hash binding; unbundled toggles; withdrawal instant; re-prompt on version change; Turkish primary | KVKK-5,KVKK-6,AYD-2018 | consent |
| INT-133 | P0 | Profiles, companions, guardian flows (minors), proxy acknowledgement | INT-131, INT-223 | risk:legal | under-18 only via guardian account with guardian consent; adolescent private-section policy implemented per 06 §6; proxy-reported flag on every record | TMK-339,HHY-24 | companions |
| INT-134 | P0 | Visits: create (manual + MHRS SMS OCR), branch picker from taxonomy, visit types | INT-130, INT-042 | — | branch list from taxonomy; unknown branch -> cluster with notice; OCR path behind documents consent | — | visits |
| INT-135 | P1 | Voice intake UI (Hizli): states, recording indicator, inline cards, barge-in, RED UI, typed fallback | INT-103, INT-096, INT-117 | risk:clinical | recording indicator always visible; RED UI per device_functions mode; fallback switch <=2s visible | USHY-12 | intake-voice |
| INT-136 | P0 | Typed intake UI (Detayli) + chips + instruments verbatim | INT-096, INT-130 | — | instrument items rendered verbatim; low-literacy chips; progress + resume | — | intake-typed |
| INT-137 | P0 | Review & send + Doctor Link QR + CSAT prompt | INT-084, INT-240 | — | section-level scope UI; consent summary; send; status timeline; one-tap CSAT with reason chips; never blocks send | KVKK-5 | review-send |
| INT-138 | P0 | Records screens: upload, processing, confirm cards, provenance viewer | INT-121, INT-130 | — | camera+file upload; AV/processing states; confirm-before-use; provenance boxes | — | records |
| INT-139 | P0 | Share centre: active shares, revoke <=1min, access log | INT-150 | — | revocation cascades to tokens within 1 min (test); patient sees access log | KVKK-11 | share-centre |
| INT-140 | P0 | Me: consents, connectors, language, security, export/delete, learned facts | INT-037, INT-170 | — | export/delete flows wired to DSAR; learned facts editable/deletable with provenance | KVKK-11 | dsar |
| INT-141 | P1 | Notifications: content-free reminders, quiet hours, opt-out; transactional-only | INT-130 | risk:legal | no PHI in push; reminders classified transactional (no IYS consent needed); any marketing path requires IYS consent and is off by default | 6563-IYS | notifications |
| INT-142 | P1 | Offline drafts + sync + resilience | INT-136 | — | drafts encrypted at rest; sync conflict rules; airplane-mode e2e | — | mobile |
| INT-143 | P1 | Kiosk mode: MDM lockdown, clinic PIN, 60s auto-wipe, privacy layout | INT-136 | risk:security | no persistence; wipe on idle/background; tamper alert; large-type layout | KVKK-12 | kiosk |
| INT-144 | P1 | Accessibility WCAG 2.2 AA pass + TR screen-reader labels + conformance report | INT-130 | risk:legal | axe/a11y CI checks; VoiceOver/TalkBack scripts; docs/legal/accessibility-statement.md (EN 301 549 mapping) | 5378,EN301549 | mobile |
| INT-145 | P1 | Client telemetry: GlitchTip crash (PHI-scrubbed), perf, RUM web | INT-023, INT-130 | — | crash-free metric wired; scrub tests; cold-start p95 tracked | KVKK-12 | mobile |
| INT-146 | P1 | EAS builds + OTA code signing + MobSF gate + store listings/privacy labels | INT-131, INT-224 | risk:legal, approval:human-legal | signed OTA; MobSF report gate; Apple privacy nutrition + Google Data safety filled from the data inventory and asserted against schema annotations | STORE,KVKK-10 | mobile |

## E09-clinician

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-150 | P0 | Doctor Link: 128-bit token + OTP + expiry + view limit + revoke + watermark + access log + no-index | INT-084, INT-016 | risk:security | entropy/expiry tests; watermark carries recipient+timestamp; robots/noindex; every open audited and visible to patient | KVKK-12,HHY-23 | doctor-link |
| INT-151 | P0 | Note views: SOAP, red flags (mode-aware), provenance, consented wellbeing, AI labels + 1-click feedback | INT-150, INT-117 | — | device_functions off: red-flag answers shown as patient-reported without automated urgency labels; AI-generated sections labelled; feedback event wired | 1219-8 | doctor-link |
| INT-152 | P1 | Clinic console: today list, statuses, read receipts, tenant isolation, SSO | INT-151, INT-030 | — | Keycloak SSO; RLS-backed isolation tests; read-receipt events | KVKK-12 | clinic-console |
| INT-153 | P1 | Clinician feedback -> Langfuse annotation queues + acceptance metrics | INT-151, INT-175 | — | accept/edit/reject with section reasons into note_quality queue; note.acceptance_rate live | — | learning-loops |

## E10-connectors

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-160 | P1 | Connector framework: adapters, OpenBao creds, idempotency, receipts, allow-listed endpoints, mTLS | INT-018, INT-035 | risk:security | per-tenant endpoint allow-list; push receipts stored; replay-safe | KVKK-8/9 | connectors |
| INT-161 | P1 | FHIR push adapter (hospital FHIR/HAPI; SMART backend services auth) | INT-160, INT-033 | approval:human-vendor, live-smoke | contract tests vs HAPI; SMART backend client credentials; scoped by share consent token; live smoke against a partner sandbox recorded before close | KVKK-8 | connectors |
| INT-162 | P2 | HBYS/SBYS adapter kit (HL7v2 ORU / file drop / FHIR) + USVS mapping + KTS registration pack | INT-160 | risk:legal, approval:human-legal | mapping tables to USVS data dictionary; KTS (SBYS Kayit Tescil) application pack generated from repo docs; processor-role DPA references | SBYS-6,USVS | connectors |
| INT-163 | P2 | Check-in: signed QR payload + desk verification + checkin_to_seen metric | INT-160, INT-143 | — | QR payload signed+short-lived; desk verification flow; wait metric emitted | — | kiosk |

## E11-learning

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-170 | P0 | PatientOverlay: store, confirmation rules, /me/learned API, engine integration | INT-031, INT-081 | — | facts commit only with patient/clinician confirmation (type-level); 12-month reconfirm; provenance shown; delta-mode works in simulator | KVKK-11 | learning-loops |
| INT-171 | P2 | De-identified analytics views + k-anonymity helper + rollups | INT-015, INT-030 | risk:legal | k>=10 enforced at query layer; refusals metered; no free-text outside review UI | KVKK-16,KSVY-16 | learning-loops |
| INT-172 | P2 | services/learning Inspector->Architect + proposal schema + evidence bundles + PR bot (open-not-merge) | INT-171, INT-004 | risk:clinical | proposal_scope CI test blocks forbidden paths (red-flag levels, instruments, consent texts, Talker tools, PolicyGuard, residency routing); sandboxed job read-only creds no egress; signed proposals | — | learning-loops |
| INT-173 | P2 | Canary/rollback controller on guardrail KPIs (5/25/100) | INT-172, INT-025 | — | auto-rollback on acceptance -5, safety blocks +50 percent, completion -5, CSAT -0.3; simulated dip test | — | learning-loops |
| INT-174 | P2 | DSPy+GEPA offline optimisation (extraction, note modules only) with clinician-edit metric + held-out | INT-153, INT-172 | — | single-module runs; Pareto selection; Langfuse experiment links in evidence bundle; Talker/safety prompts excluded by scope test | — | learning-loops |
| INT-175 | P1 | Langfuse self-hosted + annotation queues (note_quality, hallucination_audit, false_red_review) + CI experiment gate | INT-023 | — | compose profile; OTel span export; CI job runs recorded simulator experiment and gates on scores | — | observability-pipeline |

## E12-admin

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-180 | P0 | Admin shell: Keycloak RBAC/ABAC, audit on every action, IP allow-list, 4-eyes primitives | INT-023, INT-016 | risk:security | roles per 08 §2; break-glass with reason+approver; role-matrix contract tests for /admin/* | KVKK-12 | admin-console |
| INT-181 | P0 | Modules: Overview + Ops + Reliability (real dev telemetry) | INT-180, INT-021, INT-022 | — | SLO tiles, burn rates, probe matrix, dependency health from live dev stack (not mock JSON) | — | admin-console |
| INT-182 | P1 | Voice module + kill switch + profile switch + canary weights (4-eyes) | INT-181, INT-094 | risk:clinical | per-profile metrics; kill switch flips tenant to typed without deploy (test) | — | admin-console |
| INT-183 | P0 | Models & self-hosting registry module + release gate surface | INT-022, INT-180 | — | registry rendered; benchmark trigger; red cell blocks release visibly | G2019-12 | self-hosting |
| INT-184 | P2 | Protocols module: coverage, review queue, proposals, canary, clips | INT-042, INT-172, INT-180 | — | branch x maturity matrix; approve/reject with 4-eyes; clip coverage per voice | — | admin-console |
| INT-185 | P1 | Clinical quality & safety module + annotation-queue links | INT-175, INT-180 | — | triage events, false-RED queue, PolicyGuard classes, acceptance by specialty | — | admin-console |
| INT-186 | P1 | Experience & satisfaction module (CSAT/NPS/pulse/waits + SDS-01 export) | INT-240, INT-180 | — | filters by branch/profile/clinic; SDS-01-style export for hospital tenants | — | admin-console |
| INT-187 | P1 | CI/CD & releases module (GH API + Argo CD + gates + freeze) | INT-181 | — | pipelines, eval gates, deploy health, canary state, rollback button (4-eyes), deploy-freeze on budget exhaustion | — | cicd |
| INT-188 | P1 | Flags module (Unleash) + 4-eyes on safety flags | INT-023, INT-180 | — | change reasons mandatory; safety flags list incl. device_functions, s2s, learning-apply | — | admin-console |
| INT-189 | P1 | Compliance module: consents, vendor register, audit search, DSAR queue, retention, DPIA, residency, evidence exports | INT-036, INT-037, INT-038, INT-180 | risk:legal | vendor-transfer register auto-filled from egress logs with notification due-dates (5 business days rule); evidence export bundles for audits | KVKK-9,TRANSFER-2024 | compliance-evidence |
| INT-190 | P1 | Cost module | INT-101, INT-180 | — | per-session cost by component/vendor/profile; budgets + alerts | — | admin-console |
| INT-191 | P2 | Tenants module + onboarding flow | INT-180, INT-250 | — | tenant CRUD, connectors, pack enablement, branding, key rotation | — | admin-console |
| INT-192 | P1 | Security module: SIEM feeds, vulns vs SLA, rotations, drills, integrity | INT-205, INT-180 | risk:security | Wazuh/Falco/CrowdSec summaries; egress denials; audit-chain status; pen-test findings tracker | — | admin-console |

## E13-infra

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-200 | P2 | Residency compose profile (GPU) + runbooks | INT-097 | gpu | single-host GPU deployment documented and probed; capacity notes | G2019-12 | self-hosting |
| INT-201 | P2 | k8s: k3s + Argo CD + Kyverno/Sigstore admission + PSS restricted + default-deny + Harbor | INT-019 | risk:security, approval:human-infra | unsigned image rejected by admission (test in kind); GitOps envs dev/staging/tr-residency | — | cicd |
| INT-202 | P1 | Backups: pgBackRest PITR encrypted + MinIO replication + automated restore drill + evidence | INT-030, INT-034 | risk:security | RPO 15min/RTO 4h demonstrated in a drill script whose output is stored as evidence; quarterly schedule | KVKK-12 | backups |
| INT-203 | P1 | Edge: Traefik + Coraza CRS + CrowdSec + cert-manager + prod egress proxy | INT-018 | risk:security | WAF blocks OWASP CRS suite; CrowdSec scenarios on; certs automated | KVKK-12 | edge |
| INT-204 | P2 | Mesh mTLS (Linkerd) + default-deny NetworkPolicies | INT-201 | risk:security | all service-to-service traffic mTLS; policy tests | KVKK-12 | edge |
| INT-205 | P1 | Wazuh + Falco deployment + rules + console feed | INT-023 | risk:security | auth anomalies, k8s audit, container runtime alerts wired to Security module | 7545 | incident-response |
| INT-206 | P1 | GitHub Actions self-hosted runners in TR DC + no-PHI-in-CI policy | INT-002 | — | runner heartbeats probed; CI uses synthetic fixtures only (scan) | G2019-12 | cicd |
| INT-207 | P2 | Chaos suite (monthly) + load to pilot x3 + autoscaling rules | INT-024, INT-201 | — | SFU drop, backend stall, vendor kill, DB failover scenarios green; k6+lk evidence at 3x pilot concurrency | — | resilience |

## E14-legal

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-210 | P0 | Legal document set v1 (tr primary): aydinlatma x5, acik riza per purpose, gizlilik, kullanim kosullari, KVKK basvuru formu, cookie | INT-038 | risk:legal, approval:human-legal | docs/legal/ versioned with hashes; rendered in-app from source; acceptance evidence stored; plain-language summaries; counsel sign-off recorded in evidence file before merge | KVKK-10,AYD-2018,805 | consent |
| INT-211 | P0 | VERBIS registration pack + data inventory generated from schema annotations + irtibat kisisi | INT-031, INT-210 | risk:legal, approval:human-legal | every model field annotated {category,purpose,basis,retention,recipients}; inventory export matches VERBIS categories; registration checklist done | KVKK-16v | compliance-evidence |
| INT-212 | P0 | Retention & destruction policy doc (DEST-2017) bound to the engine | INT-036, INT-210 | risk:legal, approval:human-legal | policy document generated from the same policy-as-code the engine runs; periodic destruction report template | KVKK-7,DEST-2017 | retention |
| INT-213 | P1 | DPIA v1 + vendor transfer register + SCC set + Board notification workflow (5 business days) + hospital DPA template | INT-018, INT-210 | risk:legal, approval:human-legal | DPIA per processing map; SCCs per vendor from Board template; notification workflow with due-date tracking in console; DPA with mandatory clauses (KVKK-8/12, security annex mapping 10, sub-processor list, audit rights, breach notice, deletion) | KVKK-9,TRANSFER-2024 | compliance-evidence |
| INT-214 | P1 | Breach machinery: KVKK 72h Board form automation + data-subject notices + USOM report (7545) + hospital notices | INT-020 | risk:legal | runbook executable: incident record -> prefilled Board form -> notices; drill test produces the full packet within 72h simulated clock | KVKK-12-breach,7545 | incident-response |
| INT-215 | P1 | Special-category adequate measures (Board 2018/10) mapping + evidence export | INT-019, INT-023 | risk:legal | each 2018/10 measure mapped to a control and a live signal; export produces the auditor packet | 2018-10 | compliance-evidence |
| INT-216 ⚠ | P0 | **MDSW file: intended purpose, qualification (MDCG 2019-11 **Rev.1**), Rule 11 classification (**Class IIb**), device/non-device boundary table** — *corrected 27 Aug: **IIb, not IIa** — MDCG 2019-11 Annex IV names the depression-scoring case almost verbatim under Rule 11(a), IMDRF N12 counts triage as "driving clinical management", and the failure mode to assess is the **false negative**, which is the Class III limb. **This re-prices Stage B.** Also: cite **Rev.1 in English from TİTCK's own hosting** — TİTCK separately hosts a Turkish translation of the 2019 original — and note Rev.1 §3.1 **closes the "simple search" safe harbour for NLP by name**, so the intended-purpose wording is load-bearing in a way it was not before. **No accuracy claim appears anywhere in this file.*** | INT-117 | risk:legal, approval:human-legal | docs/regulatory/intended-purpose.md exact wording; boundary table lists every feature as device or non-device and binds to device_functions flag; classification rationale reviewed | TCY-R11 | device-boundary |
| INT-217 | P1 | QMS core (ISO 13485): quality manual, design controls, ISO 14971 risk file, IEC 62304 class B plan, IEC 62366-1 usability, IEC 81001-5-1 security lifecycle, PMS plan, PRRC | INT-216 | risk:legal, approval:human-legal | docs/qms/ under document control in-repo; design-control gates wired into PR template for device-flagged issues; PRRC appointment recorded | TCY,ISO13485 | device-boundary |
| INT-218 | P1 | Clinical investigation package: protocol + ICF(tr) + KAEK ethics submission + TITCK application + insurance + registration | INT-217 | risk:legal, approval:human-legal | Stage-A pilot runs only under approved study id; approvals recorded before device_functions can be enabled for the pilot tenant (gate test) | TCKAY,3359-Ek10 | device-boundary |
| INT-219 | P2 | Technical documentation (Annex II/III) + clinical evaluation (MDCG 2020-1) + PMCF + notified-body selection | INT-217 | risk:legal, approval:human-legal | tech-file skeleton auto-assembles from repo artifacts (SBOM, risk file, V&V evidence, SOUP list from lockfiles) | TCY | device-boundary |
| INT-220 | P2 | Registrations: UTS (TCKKD-KLVZ-03) + UDI; KTS (SBYS) pack; BTK yer saglayici; traffic-log retention 5651 | INT-219, INT-162 | risk:legal, approval:human-legal | packs generated from repo; 5651 traffic logs (IP,ts) separated from PHI, retained 1y max 2y with auto-purge test | UTS,SBYS-6,5651-5 | compliance-evidence |
| INT-221 | P2 | Public-hospital pack: Genelge 2019/12 residency attestation + DDO Rehber mapping + USVS conformance | INT-183, INT-162 | risk:legal | tr-residency tenants provably vendor-free on PHI path (registry assertion); Rehber control mapping doc; USVS conformance tests | G2019-12,DDO,USVS | self-hosting |
| INT-222 | P2 | Consumer/commercial: mesafeli sozlesme pre-info + withdrawal (if paid tier), IYS integration for marketing, Turkish-language compliance | INT-210 | risk:legal, approval:human-legal | paid flows blocked until pre-information + withdrawal implemented; marketing sends blocked without IYS consent record | 6502-MSY,6563-IYS,805 | billing |
| INT-223 | P0 | Minor & guardian rules engine (age gates, guardian consent, adolescent policy) as code | INT-038 | risk:legal, approval:human-legal | age from verified DOB; under-18 requires guardian account+consent; adolescent private-section share policy per 06 §6; tests for each age band | TMK-339,HHY-24 | companions |
| INT-224 | P1 | Store compliance: Apple health guidelines + Google Play Health policy + Data safety/privacy labels + IARC | — | risk:legal, approval:human-legal | checklists as tests where automatable; labels generated from the data inventory (single source) | STORE | mobile |
| INT-225 | P3 | ISO 27001 ISMS: scope, SoA, risk register, policies, internal audit, certification audit | INT-215, INT-192 | risk:legal, approval:human-legal | SoA maps Annex A to implemented controls with evidence links; internal audit executed; certification scheduled | ISO27001,SBYS-6 | compliance-evidence |
| INT-226 | P1 | Accessibility conformance report (WCAG 2.2 AA / EN 301 549) + statement page | INT-144 | — | report generated from a11y CI results; statement published in-app and web | 5378,EN301549 | — |
| INT-227 | P2 | AI governance file: model cards, TR bias/fairness eval (dialect, gender, age), transparency labels, EU AI Act readiness note | INT-095, INT-116 | risk:legal | model card per registry entry; fairness eval report on the Turkish eval sets; AI-generated labels asserted in UI tests | AI-ACT-EU | llm-boundary |

## E15-research

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-230 | P2 | Research data pipeline: anonymisation (KSVY-16), research consent gating, export for studies | INT-015, INT-038 | risk:legal, approval:human-legal | exports only with research consent + ethics id; anonymisation validated on corpus; register of research extracts | KVKK-16,KSVY-16,ETİK | learning-loops |
| INT-231 | P2 | Study tooling: instruments + analysis notebooks for tracks 1-6 (voice vs typed, triage validation, note quality, psychiatric-signal validation) | INT-230 | — | pre-registered analysis scripts; blinded exports; reproducible notebooks under tests | ETİK | — |

## E16-experience

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-240 | P0 | CSAT/NPS/clinician-pulse events + endpoints + rollups | INT-035, INT-031 | — | csat.v1 (1-5 + reason enum + optional text), nps.v1, clinician_pulse.v1; POST /sessions/{id}/csat, /feedback/nps; rollups in services/metrics | KVKK-5-satisfaction | experience |
| INT-241 | P1 | Wait-time metrics end-to-end + SDS-01 style exports | INT-240, INT-025 | — | time_to_first_question, note_ready_after_wrapup, doctor_link_first_open, checkin_to_seen (connector), records_processing emitted and dashboarded | — | experience |
| INT-242 | P1 | NPS scheduling + clinician pulse survey cadence | INT-240 | — | monthly NPS prompt honoring quiet hours; quarterly pulse; opt-outs respected | 6563-IYS | experience |

## E17-release

| id | ph | title | depends | labels | acceptance (summary) | legal | 10 §9 |
|---|---|---|---|---|---|---|---|
| INT-250 | P2 | Tenant onboarding: config, branding, packs, DPA signature via KEP/e-imza, runbook | INT-189, INT-213 | risk:legal | tenant cannot go live without signed DPA + residency attestation recorded (gate test) | KVKK-8,DPA | tenants |
| INT-251 | P3 | Billing: hospital e-Fatura via provider; patient subscription via PSP (iyzico/PayTR); never store PAN | INT-222 | risk:legal, approval:human-legal | PSP-hosted payment; webhooks verified; invoices archived per tax rules; PAN absence proved by scan | 6502-MSY,VUK | billing |
| INT-252 | P1 | Release process: semver, changelog, signed artifacts, store submission checklist, release-gate checklist in console | INT-019, INT-183 | — | `make release` assembles evidence (tests, safety, security, evals, latency, coverage, self-host matrix, legal deltas) and blocks on any red | — | cicd |
| INT-253 | P1 | Localization completeness: tr 100 percent, en 100 percent; ar planned P3 with RTL audit | INT-130 | — | i18n lint fails on missing keys; clinical tr reviewed flag enforced | 805 | — |

---

## Reconciliation note — 27 Aug 2026

**Why nothing was deleted.** A deleted issue reappears. Someone reads an older architecture section, notices the capability is missing from the backlog, and re-raises it — with the original acceptance criteria, because those are what they remember. So every invalidated issue above keeps its id, keeps its row, and carries the correction inline. `INT-098` is *withdrawn in place* and its replacement acceptance is a test that the thing cannot be built: a closed profile registry plus a grep gate that fails the build on `cascade_fast`, `s2s_cloud`, `soniox`, `inworld`, `elevenlabs` or `piper` outside `docs/blueprint/`. **That is the durable form of a withdrawal** — a paragraph decays, a failing build does not.

**What made these seven wrong, in one line each.**

| id | the invalidating fact | where it is recorded |
|---|---|---|
| INT-095 | `cascade_fast` no longer exists; all models are self-hosted | `00 §0b`, `03 §4.9` |
| INT-097 | pins superseded; Piper `tr_TR` deleted on licence; a flat p50 target is wrong; `residency_tr` split media/models | `00 §1`, D11, `03 §4.9.2(b)`, `02 §8.1` |
| INT-098 | S2S is cloud-only **and** cannot meet the shared profile contract | `00 §0b`, `05 §2.1` |
| INT-111 | no vendor socket; `emotion2vec+` disqualified on licence | D2, `00 §2`, `03 §4.9.2(c)` |
| INT-115 | Kintsugi DAM dropped; the lane is an investigational device module; the band description was wrong in two ways | D14, D4, `00 §2` |
| INT-124 | every MedGemma is HAI-DEF licensed, and 27B is gated | `00 §2`, `03 §4.9.2(a)` |
| INT-216 | Rule 11 → **Class IIb**, not IIa; MDCG Rev.1 closes the NLP safe harbour | `00 §2`, `06 §0.3` |

**Three standing rules for anyone editing this backlog.**

1. **This file is a rendering, not a source.** The source is `docs/backlog/issues.yaml`, embedded verbatim in `07 §3.11`, and a test diffs the two. **Edit the YAML and regenerate** — an edit made only here is silently reverted by the next regeneration.
2. **An acceptance criterion may not name a model.** `03 §4.9.1` is canonical; issues reference it **by row number**. Every pin restated in a second place is a pin that will drift, and this backlog is where seven of them drifted.
3. **A `blocked:*` label carries an `HB-*` id.** If you cannot name the human and the one sentence they must answer, the issue is not blocked — it is unfinished. See `HUMAN_BLOCKERS.md`.

### Cross-reference note (files not owned by this one)

- **`03 §4.9.1`** is the single source of truth for the model stack; nothing here pins a model.
- **`10 §9.1`** catalogues invariants 12–49; 1–11 are in `03 §4.6`. ⚠ **Invariants 50–65 are proposed for the data-import path and are not yet catalogued** — `03 §4.9.6` and `§10` already cite **invariant 53** (`unit_resolution_guard`) as though it exists. **INT-121 and INT-124 should not be worked before that range is catalogued in `10 §9.1`.**
- **`02 §5.3` / `04 §8.1`** define the three RED axes. Any protocol issue whose acceptance predates them (INT-04x, INT-05x, INT-08x) needs `register` and `location` added to its rule-schema criteria — **that sweep is not yet done and is listed as outstanding in the handover.**
