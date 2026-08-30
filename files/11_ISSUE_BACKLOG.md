# 11 · ISSUE BACKLOG — generated rendering, do not edit by hand

> Generated from `docs/backlog/issues.yaml` by `scripts/backlog/render_backlog.py`
> (INT-004). Regenerate with `uv run python scripts/backlog/render_backlog.py`;
> a CI test diffs the two. The YAML is the source of record; the GitHub issues
> are its sync target. One issue == one PR (`07 §3.11`).

**214 issues.** By phase: P0 125 · P1 47 · P2 37 · P3 5. By status: awaiting-human 3 · doing 7 · done 87 · todo 116 · withdrawn 1.

## P0

| id | title | epic | depends on | labels | status |
|---|---|---|---|---|---|
| INT-001 | Monorepo bootstrap: workspaces, Makefile, pre-commit, compose.dev | E00-governance | — | area:platform | done |
| INT-002 | CI base + zero-placeholder and evidence gates | E00-governance | INT-001 | area:ci | done |
| INT-003 | ADR-000..023 written; blueprint at files/ indexed | E00-governance | INT-001 | area:docs | done |
| INT-004 | Backlog machinery: issues.yaml -> GitHub issues/labels/milestones/project; loop runner | E00-governance | INT-002 | area:ci | done |
| INT-010 | packages/intake_platform/health: /healthz /readyz /metrics /version + contract test | E01-platform | INT-001 | area:platform | done |
| INT-011 | packages/intake_platform/otel: shared tracing/metrics/logs + PII redaction processor | E01-platform | INT-010 | area:platform | done |
| INT-012 | packages/intake_platform/security: headers, rate limiter, idempotency keys | E01-platform | INT-010 | area:security | done |
| INT-013 | Tokenization service + identity vault (TCKN/phone never in clear) | E01-platform | INT-012, INT-017 | area:security, risk:security | done |
| INT-014 | Envelope encryption (OpenBao Transit) + rotation + crypto-shredding | E01-platform | INT-017 | area:security, risk:security | done |
| INT-015 | De-identification service: Presidio + Turkish recognizers + leak-rate corpus | E01-platform | INT-011 | area:security, risk:security | done |
| INT-016 | Hash-chained audit log + WORM export + daily verifier | E01-platform | INT-014 | area:security | doing |
| INT-017 | OpenBao dev server + per-service policies + dynamic DB creds | E01-platform | INT-001 | area:security | done |
| INT-018 | Egress proxy with vendor allow-list + transfer log | E01-platform | INT-001 | area:security, risk:legal | doing |
| INT-019 | security.yml CI job: full gate set + signing | E01-platform | INT-002 | area:ci, risk:security | doing |
| INT-020 | Threat model + incident runbook + PR linkage | E01-platform | INT-003 | area:security, risk:legal | doing |
| INT-021 | SLO files + Prometheus rules + Grafana dashboards as code + runbooks | E01-platform | INT-011 | area:observability | doing |
| INT-022 | services/probes: synthetic checks + self-hosting registry + release gate | E01-platform | INT-010, INT-021 | area:observability | done |
| INT-023 | Observability stack profile: OTel+Prom+Loki+Tempo+Grafana (or SigNoz), Unleash, Keycloak, GlitchTip | E01-platform | INT-011 | area:observability | done |
| INT-024 | k6 smoke + lk load-test recipe + chaos harness (vendor kill -> typed <=2s) | E01-platform | INT-022 | area:observability | done |
| INT-025 | Metrics catalogue as code + completeness test | E01-platform | INT-011 | area:observability | done |
| INT-030 | Postgres schema + Alembic + RLS per tenant + pgaudit | E02-data | INT-013, INT-014 | area:data | done |
| INT-031 | clinical-schemas: pydantic models + TS codegen + event schemas | E02-data | INT-030 | area:data | done |
| INT-033 | HAPI FHIR exchange: mappers internal<->R4 + validation | E02-data | INT-031 | area:data | done |
| INT-034 | MinIO document store: signed URLs + AV hook + WORM audit bucket | E02-data | INT-016 | area:data | done |
| INT-035 | Redis streams event bus + consumer framework + DLQ | E02-data | INT-031 | area:platform | done |
| INT-036 | Retention & destruction engine (policy as code, 6-month periodic destruction, logs) | E02-data | INT-030 | area:data, risk:legal | done |
| INT-037 | DSAR endpoints: export (FHIR+PDF), delete (crypto-shred, 30-day grace), rectify + 30-day SLA tracker | E02-data | INT-014, INT-033 | area:data, risk:legal | done |
| INT-038 | Consent service: versioned objects, consent_guard middleware, re-prompt on change | E02-data | INT-030 | area:data, risk:legal | done |
| INT-040 | Protocol DSL: schema, loader, validator (extends, monotonic red flags, voice fields) | E03-protocols | INT-031 | area:protocols | done |
| INT-041 | Compiler: FHIR Questionnaire + openEHR bindings + Pydantic + TS + clip manifest, deterministic | E03-protocols | INT-040, INT-033 | area:protocols | done |
| INT-042 | Taxonomy: all MHRS branches + clusters + visit types + coverage CLI | E03-protocols | INT-040 | area:protocols | done |
| INT-043 | base.intake pack (tr/en) complete per 04 §1 - FRONT-LOADED: unblocks 78 of 175 | E03-protocols | INT-041 | area:protocols, risk:clinical, approval:human-clinical | awaiting-human |
| INT-044 | Cluster pack: medical | E03-protocols | INT-043 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-045 | Cluster pack: surgical | E03-protocols | INT-043 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-046 | Cluster pack: sensory | E03-protocols | INT-043 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-047 | Cluster pack: womens_health | E03-protocols | INT-043 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-048 | Cluster pack: child_health (guardian proxy, age bands) | E03-protocols | INT-043, INT-133 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-049 | Cluster pack: mental_health | E03-protocols | INT-043 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-050 | Cluster pack: dental | E03-protocols | INT-043 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-051 | Cluster pack: allied_and_reports | E03-protocols | INT-043 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-052 | Cluster excluded: Acil refusal + 112 routing copy | E03-protocols | INT-043 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-053 | Deep pack: internal_medicine | E03-protocols | INT-044 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-054 | Deep pack: gastroenterology + overlay.oncology_patient | E03-protocols | INT-044 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-055 | Deep pack: rheumatology | E03-protocols | INT-044 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-056 | Patient overlays set (8) + overlay_monotonicity property test | E03-protocols | INT-043 | area:protocols, risk:clinical | todo |
| INT-057 | Protocol Authoring Agent: L0 drafts for every branch + no-serve guard | E03-protocols | INT-042 | area:protocols | done |
| INT-058 | Signed protocol bundles: cosign sign + runtime verification + per-session hash pin | E03-protocols | INT-041, INT-019 | area:protocols, risk:security | todo |
| INT-059 | Triage golden suite >=200 + mutation tests | E03-protocols | INT-080 | area:protocols, risk:clinical | done |
| INT-060 | Clip cache builder per voice + MinIO + coverage test | E03-protocols | INT-041, INT-034 | area:voice | done |
| INT-080 | Deterministic triage engine (levels, monotonic merge, action scripts) | E04-engines | INT-040 | area:safety, risk:clinical | done |
| INT-081 | IntakeEngine FSM: step kinds, ask-ahead/reconcile-behind, delta mode, overlays | E04-engines | INT-080, INT-258 | area:engine | done |
| INT-082 | Patient simulator: personas + scenarios IM-01..IM-14 headless | E04-engines | INT-081 | area:engine | todo |
| INT-083 | Extraction Work: schema-constrained LLM behind gateway + data boundary + eval set | E04-engines | INT-081, INT-015 | area:ai | todo |
| INT-084 | Note composer + renderers (SOAP, PDF watermark-ready, FHIR bundle) + provenance + disclaimer | E04-engines | INT-083, INT-033 | area:engine, risk:legal | todo |
| INT-085 | Patient summary (B1 Turkish) + reading-level check | E04-engines | INT-084 | area:engine | todo |
| INT-090 | LiveKit server+TURN dev; per-session tokens (10-min minimal grants); audio_retention_guard | E05-voice | INT-001 | area:voice, risk:security | done |
| INT-091 | Talker: six-tool registry + introspection test + streaming PolicyGuard + insertion-window scheduler + clip player | E05-voice | INT-060, INT-090 | area:voice, risk:clinical | done |
| INT-092 | Backend Agent: FIFO Work queue, serialized SessionState, delivery semantics, idempotent | E05-voice | INT-081, INT-035 | area:voice | todo |
| INT-093 | RED preemption path: stop <=150ms, e2e <=300ms (fake clocks) | E05-voice | INT-091, INT-092, INT-080 | area:voice, risk:clinical | todo |
| INT-094 | Runtime invariants 1-11 + RT-01..08 + latency harness | E05-voice | INT-093, INT-110 | area:voice | todo |
| INT-096 | Profile typed (full parity fallback) | E05-voice | INT-081 | area:voice | todo |
| INT-101 | Session budgets + cost metering per component/profile | E05-voice | INT-092 | area:voice | todo |
| INT-110 | Lane framework: budgets, backpressure, ObserverState, per-lane consent, type-level read-only | E06-lanes | INT-092, INT-038 | area:lanes, risk:clinical | todo |
| INT-112 | linguistic lane: TR lexicons + prosody stats + crisis bypass to triage | E06-lanes | INT-110, INT-080 | area:lanes, risk:clinical | todo |
| INT-116 | Wellbeing engine: PHQ-2/GAD-2 -> PHQ-9/GAD-7 -> C-SSRS, crisis script, verbatim items, clinician-only outputs | E06-lanes | INT-081, INT-112 | area:clinical, risk:clinical, approval:human-clinical | todo |
| INT-117 | device_functions flag: MDSW boundary enforced (Stage A non-device vs investigation mode) | E06-lanes | INT-116, INT-093, INT-038 | area:legal, risk:legal, approval:human-legal | todo |
| INT-120 | Upload pipeline: ClamAV, sniffing, limits, sandboxed OCR | E07-records | INT-034 | area:records, risk:security | done |
| INT-121 | Document extraction -> FHIR with provenance + confirm cards + eval corpus | E07-records | INT-120, INT-083 | area:records | todo |
| INT-130 | Expo app shell: SDK 57 dev build, navigation map per 02, i18n tr-first, theme, a11y base | E08-mobile | INT-001 | area:mobile | done |
| INT-131 | Onboarding & auth: OTP + attestation + DPoP + biometrics + SecureStore + pinning + FLAG_SECURE | E08-mobile | INT-130, INT-012, INT-013 | area:mobile, risk:security | done |
| INT-132 | Consent UI: layered, versioned, lane sub-toggles, learning, satisfaction; who-sees-what | E08-mobile | INT-038, INT-130 | area:mobile, risk:legal, approval:human-legal | done |
| INT-133 | Profiles, companions, guardian flows (minors), proxy acknowledgement | E08-mobile | INT-131, INT-223 | area:mobile, risk:legal | done |
| INT-134 | Visits: create (manual + MHRS SMS OCR), branch picker from taxonomy, visit types | E08-mobile | INT-130, INT-042 | area:mobile | done |
| INT-136 | Typed intake UI (Detayli) + chips + instruments verbatim | E08-mobile | INT-096, INT-130 | area:mobile | todo |
| INT-137 | Review & send + Doctor Link QR + CSAT prompt | E08-mobile | INT-084, INT-240 | area:mobile | todo |
| INT-138 | Records screens: upload, processing, confirm cards, provenance viewer | E08-mobile | INT-121, INT-130 | area:mobile | todo |
| INT-139 | Share centre: active shares, revoke <=1min, access log | E08-mobile | INT-150 | area:mobile | todo |
| INT-140 | Me: consents, connectors, language, security, export/delete, learned facts | E08-mobile | INT-037, INT-170 | area:mobile | todo |
| INT-150 | Doctor Link: 128-bit token + OTP + expiry + view limit + revoke + watermark + access log + no-index | E09-clinician | INT-084, INT-016 | area:clinician, risk:security | todo |
| INT-151 | Note views: SOAP, red flags (mode-aware), provenance, consented wellbeing, AI labels + 1-click feedback | E09-clinician | INT-150, INT-117 | area:clinician | todo |
| INT-170 | PatientOverlay: store, confirmation rules, /me/learned API, engine integration | E11-learning | INT-031, INT-081 | area:learning | todo |
| INT-176 | Idempotency keys must be scoped by authenticated principal + tenant (cross-user replay/PHI disclosure) | E01-platform | INT-017 | area:security, risk:security | done |
| INT-177 | Rate limiter: replace per-process monotonic clock with Redis TIME in the Lua script | E01-platform | INT-017 | area:security, risk:security | done |
| INT-178 | Redact traces and metrics pipelines (app-side span scrubbing + collector processors) — errors are not a side channel | E01-platform | INT-013 | area:security, risk:security | done |
| INT-179 | Mobile flow shells: typed-intake chips + review-and-send on fixture data (Mobbin-grounded designs) | E08-mobile | INT-130 | area:mobile | doing |
| INT-193 | Premium visual pass: Liquid Glass + Oura register, working add-visit, language switching, standardized clinician brief; first simulator smoke | E08-mobile | INT-179 | area:mobile | done |
| INT-194 | Editable review, dev-lane voice notes via own whisper-tr ASR, department-based intake packs | E08-mobile | INT-193 | area:mobile | done |
| INT-195 | Design pass 3: Oura-register glass layering, kicker/hairline anatomy, guidance-block empty states, Fraunces leading, AA fix | E08-mobile | INT-194 | area:mobile | done |
| INT-196 | Design pass 4: js-tabs floating pill rail, Oura-measured register (radius, padding, Inter body), Tabs.Protected consent gate | E08-mobile | INT-195 | area:mobile | done |
| INT-198 | Department intake packs: 10 branches at full OLDCARTS depth, canonical anamnesis order, severity in words | E08-mobile | INT-194 | area:mobile | done |
| INT-199 | Voice-first intake entry: speak freely -> whisper transcript -> schema-bound extract -> per-question confirm flow with verbatim provenance | E08-mobile | INT-194 | area:mobile, area:voice | done |
| INT-208 | Device health connectors: HealthKit/Health Connect behind capability detection and consent, device-local only | E08-mobile | INT-193 | area:mobile | done |
| INT-209 | Design pass 5: numeric focal point (PrepGauge), Oura table anatomy, stack headers, serif weight and accent budget | E08-mobile | INT-196 | area:mobile | done |
| INT-197 | Dev-tier API slice: dev-bearer accounts, visits/notes/documents over RLS with audit, consent and envelope encryption | E01-platform | INT-030, INT-034 | area:api | done |
| INT-229 | Records upload UI: picker to scanned document list over the real pipeline | E07-records | INT-120, INT-197 | area:mobile | done |
| INT-232 | Patient-facing consent routes: snapshot, grant, withdraw - seam-faithful to the INT-132 client | E01-platform | INT-038, INT-131 | area:api | done |
| INT-233 | Spoken intake dialogue (dev tier): agent asks aloud, barge-in, per-turn confirm - LiveKit Talker remains the production path | E08-mobile | INT-198, INT-199 | area:mobile, area:voice | done |
| INT-234 | Design pass 6: CTA saturation register (bone pill), tonal secondaries, focused-flow exits, glyph-badge empty states | E08-mobile | INT-209 | area:mobile | done |
| INT-180 | Admin shell: Keycloak RBAC/ABAC, audit on every action, IP allow-list, 4-eyes primitives | E12-admin | INT-023, INT-016 | area:admin, risk:security | todo |
| INT-181 | Modules: Overview + Ops + Reliability (real dev telemetry) | E12-admin | INT-180, INT-021, INT-022 | area:admin | todo |
| INT-183 | Models & self-hosting registry module + release gate surface | E12-admin | INT-022, INT-180 | area:admin | todo |
| INT-210 | Legal document set v1 (tr primary): aydinlatma x5, acik riza per purpose, gizlilik, kullanim kosullari, KVKK basvuru formu, cookie | E14-legal | INT-038 | area:legal, risk:legal, approval:human-legal | todo |
| INT-211 | VERBIS registration pack + data inventory generated from schema annotations + irtibat kisisi | E14-legal | INT-031, INT-210 | area:legal, risk:legal, approval:human-legal | todo |
| INT-212 | Retention & destruction policy doc (DEST-2017) bound to the engine | E14-legal | INT-036, INT-210 | area:legal, risk:legal, approval:human-legal | todo |
| INT-216 | MDSW file: intended purpose, qualification (MDCG 2019-11 Rev.1), Rule 11 classification (Class IIb), device/non-device boundary table | E14-legal | INT-117 | area:legal, risk:legal, approval:human-legal | todo |
| INT-223 | Minor & guardian rules engine (age gates, guardian consent, adolescent policy) as code | E14-legal | INT-038 | area:legal, risk:legal, approval:human-legal | done |
| INT-240 | CSAT/NPS/clinician-pulse events + endpoints + rollups | E16-experience | INT-035, INT-031 | area:experience | done |
| INT-236 | Adaptive dev packs (askIf, DSL-mirrored) + Hizli/Detayli modes with privacy deferral and instant checkpoint | E08-mobile | INT-198, INT-233 | area:mobile | done |
| INT-235 | Voice chat surface: two-sided live transcript with ask-ahead dialogue and realtime section panel | E08-mobile | INT-233 | area:mobile | done |
| INT-237 | TTS delivery shaping: sentence splitting, boundary gaps, silence trim - and the measurement that identified the voice model as the dominant cause | E08-mobile | INT-233 | area:mobile | done |
| INT-238 | Kaynaklar ingest defect: the virus scanner slot was never wired, so every upload stuck in quarantine | E02-data | INT-120, INT-034 | area:data | done |
| INT-239 | Dialogue-only intake with answer-driven dev packs: delete the two-button chooser, branch every department on prior answers | E08-mobile | INT-235, INT-236 | area:mobile | done |
| INT-243 | Serve the intended production TTS tier (VoxCPM2) behind a licence-verified registry row, with the fallback voice kept | E05-voice | INT-237 | area:voice | done |
| INT-254 | DSL/life-threat reconciliation: tense_anchor is a slot reference, explicit rule status, source note, secondary action — and the validator AttributeError INT-041 routed around | E03-protocols | INT-040, INT-041 | area:protocols | done |
| INT-255 | Model the eleven life-threat delivery annotations the DSL still refuses (audio/register, the crisis path, paediatric proxy, document-level blocks) | E03-protocols | INT-254 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-246 | Make a dead voice lane announce itself in development, and add a host probe that measures rather than pings | E08-mobile | INT-239 | area:mobile | done |
| INT-247 | Carried-forward facts must be confirmable before they read as current (the client half of INT-170) | E11-learning | INT-133 | area:mobile | done |
| INT-248 | PolicyGuard precision: Turkish morphology, and the disclaimer the guard was rejecting | E05-voice | INT-091 | area:voice | done |
| INT-249 | Latency-aware voice lane selection: a health check that answers is not a lane that can speak | E05-voice | INT-243 | area:voice | done |
| INT-261 | Voice intake mixes with the typed form: a clip that cannot be spoken ends the whole conversation, and the spoken turn reads the typed form's control copy | E08-mobile | INT-239, INT-249 | area:mobile, area:voice | done |
| INT-258 | Overlay composition mechanism + monotonicity property test (content stays with INT-056) | E03-protocols | INT-041 | area:protocols | done |
| INT-260 | Görünüm: an in-app appearance screen, and the four mechanisms that make its controls do something | E08-mobile | INT-144, INT-193 | area:mobile | done |
| INT-263 | Content a patient cannot scroll to is content the app did not show: a scroll container for every screen the appearance work did not reach | E08-mobile | INT-260 | area:mobile, area:a11y | todo |
| INT-264 | The OTP abuse suite's clock is seeded from the wall clock, so a rate-limit refusal depends on the minute CI starts | E08-mobile | INT-131 | area:api, risk:security | done |
| INT-265 | OTP request budgets are fixed hourly windows, so a caller gets twice the limit across a boundary while files/10 §2 says per hour | E08-mobile | INT-131, INT-264 | area:api, risk:security | todo |

## P1

| id | title | epic | depends on | labels | status |
|---|---|---|---|---|---|
| INT-095 | Profile residency_tr with real self-hosted adapters (03 §4.9.1 rows 1-2, 7, 10-11) + on-hardware smoke | E05-voice | INT-094, INT-018 | area:voice, approval:human-infra, gpu | todo |
| INT-099 | Backchannels + ack styles + preemptive generation + per-profile NFR harness in CI | E05-voice | INT-095 | area:voice | todo |
| INT-100 | Vendor failover + circuit breakers + typed fallback <=2s + chaos test | E05-voice | INT-095, INT-024 | area:voice | todo |
| INT-102 | Adversarial suite RT-09..14 in make safety + nightly LLM red-team job | E05-voice | INT-094, INT-083 | area:safety, risk:security | todo |
| INT-103 | Mobile voice client: LiveKit RN, permissions, network-quality per turn, reconnect, background | E05-voice | INT-130, INT-090 | area:mobile | done |
| INT-111 | affect lane: self-hosted SER on the agent worker (03 §4.9.1 row 14) + Turkish eval set | E06-lanes | INT-110 | area:lanes, approval:human-clinical | todo |
| INT-113 | asr_quality lane: shadow-STT disagreement + confirm-by-card trigger | E06-lanes | INT-110, INT-095 | area:lanes | todo |
| INT-114 | engagement lane -> satisfaction proxies + pacing hints | E06-lanes | INT-110 | area:lanes | todo |
| INT-122 | e-Nabız export/PDF import parser + MHRS SMS screenshot OCR | E07-records | INT-121 | area:records | todo |
| INT-123 | pgvector record index (RLS, per-patient namespace) + retrieval Work | E07-records | INT-030, INT-121 | area:records | todo |
| INT-135 | Voice intake UI (Hizli): states, recording indicator, inline cards, barge-in, RED UI, typed fallback | E08-mobile | INT-103, INT-096, INT-117 | area:mobile, risk:clinical | todo |
| INT-141 | Notifications: content-free reminders, quiet hours, opt-out; transactional-only | E08-mobile | INT-130 | area:mobile, risk:legal | done |
| INT-142 | Offline drafts + sync + resilience | E08-mobile | INT-136 | area:mobile | todo |
| INT-143 | Kiosk mode: MDM lockdown, clinic PIN, 60s auto-wipe, privacy layout | E08-mobile | INT-136 | area:mobile, risk:security | todo |
| INT-144 | Accessibility WCAG 2.2 AA pass + TR screen-reader labels + conformance report | E08-mobile | INT-130 | area:mobile, risk:legal | awaiting-human |
| INT-145 | Client telemetry: GlitchTip crash (PHI-scrubbed), perf, RUM web | E08-mobile | INT-023, INT-130 | area:mobile | done |
| INT-146 | EAS builds + OTA code signing + MobSF gate + store listings/privacy labels | E08-mobile | INT-131, INT-224 | area:mobile, risk:legal, approval:human-legal | todo |
| INT-152 | Clinic console: today list, statuses, read receipts, tenant isolation, SSO | E09-clinician | INT-151, INT-030 | area:clinician | todo |
| INT-153 | Clinician feedback -> Langfuse annotation queues + acceptance metrics | E09-clinician | INT-151, INT-175 | area:clinician | todo |
| INT-160 | Connector framework: adapters, OpenBao creds, idempotency, receipts, allow-listed endpoints, mTLS | E10-connectors | INT-018, INT-035 | area:connectors, risk:security | todo |
| INT-161 | FHIR push adapter (hospital FHIR/HAPI; SMART backend services auth) | E10-connectors | INT-160, INT-033 | area:connectors, approval:human-vendor, live-smoke | todo |
| INT-175 | Langfuse self-hosted + annotation queues (note_quality, hallucination_audit, false_red_review) + CI experiment gate | E11-learning | INT-023 | area:observability | done |
| INT-228 | Tokenizer pseudonyms exceed DocumentStore key-segment bound: integrate or widen the shape | E02-data | INT-034 | area:data | done |
| INT-182 | Voice module + kill switch + profile switch + canary weights (4-eyes) | E12-admin | INT-181, INT-094 | area:admin, risk:clinical | todo |
| INT-185 | Clinical quality & safety module + annotation-queue links | E12-admin | INT-175, INT-180 | area:admin | todo |
| INT-186 | Experience & satisfaction module (CSAT/NPS/pulse/waits + SDS-01 export) | E12-admin | INT-240, INT-180 | area:admin | todo |
| INT-187 | CI/CD & releases module (GH API + Argo CD + gates + freeze) | E12-admin | INT-181 | area:admin | todo |
| INT-188 | Flags module (Unleash) + 4-eyes on safety flags | E12-admin | INT-023, INT-180 | area:admin | todo |
| INT-189 | Compliance module: consents, vendor register, audit search, DSAR queue, retention, DPIA, residency, evidence exports | E12-admin | INT-036, INT-037, INT-038, INT-180 | area:admin, risk:legal | todo |
| INT-190 | Cost module | E12-admin | INT-101, INT-180 | area:admin | todo |
| INT-192 | Security module: SIEM feeds, vulns vs SLA, rotations, drills, integrity | E12-admin | INT-205, INT-180 | area:admin, risk:security | todo |
| INT-202 | Backups: pgBackRest PITR encrypted + MinIO replication + automated restore drill + evidence | E13-infra | INT-030, INT-034 | area:infra, risk:security | doing |
| INT-203 | Edge: Traefik + Coraza CRS + CrowdSec + cert-manager + prod egress proxy | E13-infra | INT-018 | area:infra, risk:security | todo |
| INT-205 | Wazuh + Falco deployment + rules + console feed | E13-infra | INT-023 | area:infra, risk:security | done |
| INT-206 | GitHub Actions self-hosted runners in TR DC + no-PHI-in-CI policy | E13-infra | INT-002 | area:infra, approval:human-infra, blocked:contract | awaiting-human |
| INT-213 | DPIA v1 + vendor transfer register + SCC set + Board notification workflow (5 business days) + hospital DPA template | E14-legal | INT-018, INT-210 | area:legal, risk:legal, approval:human-legal | todo |
| INT-214 | Breach machinery: KVKK 72h Board form automation + data-subject notices + USOM report (7545) + hospital notices | E14-legal | INT-020 | area:legal, risk:legal | todo |
| INT-215 | Special-category adequate measures (Board 2018/10) mapping + evidence export | E14-legal | INT-019, INT-023 | area:legal, risk:legal | todo |
| INT-217 | QMS core (ISO 13485): quality manual, design controls, ISO 14971 risk file, IEC 62304 class B plan, IEC 62366-1 usability, IEC 81001-5-1 security lifecycle, PMS plan, PRRC | E14-legal | INT-216 | area:legal, risk:legal, approval:human-legal | todo |
| INT-218 | Clinical investigation package: protocol + ICF(tr) + KAEK ethics submission + TITCK application + insurance + registration | E14-legal | INT-217 | area:legal, risk:legal, approval:human-legal | todo |
| INT-224 | Store compliance: Apple health guidelines + Google Play Health policy + Data safety/privacy labels + IARC | E14-legal | — | area:legal, risk:legal, approval:human-legal | done |
| INT-226 | Accessibility conformance report (WCAG 2.2 AA / EN 301 549) + statement page | E14-legal | INT-144 | area:legal | todo |
| INT-241 | Wait-time metrics end-to-end + SDS-01 style exports | E16-experience | INT-240, INT-025 | area:experience | done |
| INT-242 | NPS scheduling + clinician pulse survey cadence | E16-experience | INT-240 | area:experience | done |
| INT-252 | Release process: semver, changelog, signed artifacts, store submission checklist, release-gate checklist in console | E17-release | INT-019, INT-183 | area:release | todo |
| INT-253 | Localization completeness: tr 100 percent, en 100 percent; ar planned P3 with RTL audit | E17-release | INT-130 | area:release | done |
| INT-256 | Universal history sections (allergy, medication, PMH, family) composed onto every department pack | E04-engines | INT-247 | area:engine | done |

## P2

| id | title | epic | depends on | labels | status |
|---|---|---|---|---|---|
| INT-061 | Deep pack: cardiology | E03-protocols | INT-044 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-062 | Deep pack: neurology | E03-protocols | INT-044 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-063 | Deep pack: endocrinology | E03-protocols | INT-044 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-064 | Deep pack: urology | E03-protocols | INT-045 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-065 | Deep pack: ophthalmology | E03-protocols | INT-046 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-066 | Deep pack: ent | E03-protocols | INT-046 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-067 | Deep pack: orthopaedics | E03-protocols | INT-045 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-068 | Deep pack: dermatology | E03-protocols | INT-044 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-069 | Deep pack: obgyn | E03-protocols | INT-047 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-070 | Deep pack: paediatrics | E03-protocols | INT-048 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-071 | Deep pack: psychiatry | E03-protocols | INT-049 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-072 | Deep pack: oncology | E03-protocols | INT-044 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-073 | Deep pack: dentistry_general | E03-protocols | INT-050 | area:protocols, risk:clinical, approval:human-clinical | todo |
| INT-098 | WITHDRAWN - Profile s2s_cloud. Replaced by a test that proves no S2S/cloud profile can be constructed | E05-voice | INT-094 | area:voice, risk:security | withdrawn |
| INT-115 | acoustic lane (M3, investigational device module): our own ordinal head, in-memory window, zeroing, study assertion | E06-lanes | INT-110, INT-117 | area:lanes, risk:clinical, approval:human-clinical, blocked:study-site | todo |
| INT-124 | Lab-report->JSON via the self-hosted extraction LLM (03 §4.9.1 row 9) + Turkish unit-resolution eval | E07-records | INT-121 | area:records, gpu | todo |
| INT-162 | HBYS/SBYS adapter kit (HL7v2 ORU / file drop / FHIR) + USVS mapping + KTS registration pack | E10-connectors | INT-160 | area:connectors, risk:legal, approval:human-legal | todo |
| INT-163 | Check-in: signed QR payload + desk verification + checkin_to_seen metric | E10-connectors | INT-160, INT-143 | area:connectors | todo |
| INT-171 | De-identified analytics views + k-anonymity helper + rollups | E11-learning | INT-015, INT-030 | area:learning, risk:legal | done |
| INT-172 | services/learning Inspector->Architect + proposal schema + evidence bundles + PR bot (open-not-merge) | E11-learning | INT-171, INT-004 | area:learning, risk:clinical | done |
| INT-173 | Canary/rollback controller on guardrail KPIs (5/25/100) | E11-learning | INT-172, INT-025 | area:learning | todo |
| INT-174 | DSPy+GEPA offline optimisation (extraction, note modules only) with clinician-edit metric + held-out | E11-learning | INT-153, INT-172 | area:learning | todo |
| INT-184 | Protocols module: coverage, review queue, proposals, canary, clips | E12-admin | INT-042, INT-172, INT-180 | area:admin | todo |
| INT-191 | Tenants module + onboarding flow | E12-admin | INT-180, INT-250 | area:admin | todo |
| INT-200 | Residency compose profile (GPU) + runbooks | E13-infra | INT-097 | area:infra, gpu | todo |
| INT-201 | k8s: k3s + Argo CD + Kyverno/Sigstore admission + PSS restricted + default-deny + Harbor | E13-infra | INT-019 | area:infra, risk:security, approval:human-infra | todo |
| INT-204 | Mesh mTLS (Linkerd) + default-deny NetworkPolicies | E13-infra | INT-201 | area:infra, risk:security | todo |
| INT-207 | Chaos suite (monthly) + load to pilot x3 + autoscaling rules | E13-infra | INT-024, INT-201 | area:infra | todo |
| INT-219 | Technical documentation (Annex II/III) + clinical evaluation (MDCG 2020-1) + PMCF + notified-body selection | E14-legal | INT-217 | area:legal, risk:legal, approval:human-legal | todo |
| INT-220 | Registrations: UTS (TCKKD-KLVZ-03) + UDI; KTS (SBYS) pack; BTK yer saglayici; traffic-log retention 5651 | E14-legal | INT-219, INT-162 | area:legal, risk:legal, approval:human-legal | todo |
| INT-221 | Public-hospital pack: Genelge 2019/12 residency attestation + DDO Rehber mapping + USVS conformance | E14-legal | INT-183, INT-162 | area:legal, risk:legal | todo |
| INT-222 | Consumer/commercial: mesafeli sozlesme pre-info + withdrawal (if paid tier), IYS integration for marketing, Turkish-language compliance | E14-legal | INT-210 | area:legal, risk:legal, approval:human-legal | todo |
| INT-227 | AI governance file: model cards, TR bias/fairness eval (dialect, gender, age), transparency labels, EU AI Act readiness note | E14-legal | INT-095, INT-116 | area:legal, risk:legal | todo |
| INT-230 | Research data pipeline: anonymisation (KSVY-16), research consent gating, export for studies | E15-research | INT-015, INT-038 | area:research, risk:legal, approval:human-legal | done |
| INT-231 | Study tooling: instruments + analysis notebooks for tracks 1-6 (voice vs typed, triage validation, note quality, psychiatric-signal validation) | E15-research | INT-230 | area:research | todo |
| INT-262 | Research extracts: differencing gate across the register (a second extract over an overlapping window re-identifies) | E15-research | INT-230 | area:research, risk:legal, approval:human-legal | todo |
| INT-250 | Tenant onboarding: config, branding, packs, DPA signature via KEP/e-imza, runbook | E17-release | INT-189, INT-213 | area:release, risk:legal | todo |

## P3

| id | title | epic | depends on | labels | status |
|---|---|---|---|---|---|
| INT-032 | EHRbase export tier: OPT templates + client + roundtrip (P3 export per D8) | E02-data | INT-031 | area:data | done |
| INT-257 | openEHR OPT: the committed template has no occurrences and a live CDR rejects it | E02-data | INT-032 | area:data | todo |
| INT-097 | residency_tr_models tier on GPU: compose.residency, node sizing, on-hardware latency evidence | E05-voice | INT-094, INT-095 | area:voice, approval:human-infra, gpu, blocked:contract | todo |
| INT-225 | ISO 27001 ISMS: scope, SoA, risk register, policies, internal audit, certification audit | E14-legal | INT-215, INT-192 | area:legal, risk:legal, approval:human-legal | todo |
| INT-251 | Billing: hospital e-Fatura via provider; patient subscription via PSP (iyzico/PayTR); never store PAN | E17-release | INT-222 | area:release, risk:legal, approval:human-legal | todo |

