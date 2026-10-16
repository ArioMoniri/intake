# 11 · ISSUE BACKLOG — generated rendering, do not edit by hand

> Generated from `docs/backlog/issues.yaml` by `scripts/backlog/render_backlog.py`
> (INT-004). Regenerate with `uv run python scripts/backlog/render_backlog.py`;
> a CI test diffs the two. The YAML is the source of record; the GitHub issues
> are its sync target. One issue == one PR (`07 §3.11`).

**366 issues.** By phase: P0 182 · P1 130 · P2 47 · P3 7. By status: awaiting-human 38 · doing 7 · done 246 · todo 74 · withdrawn 1.

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
| INT-016 | Hash-chained audit log + WORM export + daily verifier | E01-platform | INT-014 | area:security | done |
| INT-017 | OpenBao dev server + per-service policies + dynamic DB creds | E01-platform | INT-001 | area:security | done |
| INT-018 | Egress proxy with vendor allow-list + transfer log | E01-platform | INT-001 | area:security, risk:legal | done |
| INT-019 | security.yml CI job: full gate set + signing | E01-platform | INT-002 | area:ci, risk:security | awaiting-human |
| INT-020 | Threat model + incident runbook + PR linkage | E01-platform | INT-003 | area:security, risk:legal | done |
| INT-021 | SLO files + Prometheus rules + Grafana dashboards as code + runbooks | E01-platform | INT-011 | area:observability | done |
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
| INT-082 | Patient simulator: personas + scenarios IM-01..IM-14 headless | E04-engines | INT-081 | area:engine | done |
| INT-083 | Extraction Work: schema-constrained LLM behind gateway + data boundary + eval set | E04-engines | INT-081, INT-015 | area:ai | done |
| INT-084 | Note composer + renderers (SOAP, PDF watermark-ready, FHIR bundle) + provenance + disclaimer | E04-engines | INT-083, INT-033 | area:engine, risk:legal | done |
| INT-085 | Patient summary (B1 Turkish) + reading-level check | E04-engines | INT-084 | area:engine | done |
| INT-090 | LiveKit server+TURN dev; per-session tokens (10-min minimal grants); audio_retention_guard | E05-voice | INT-001 | area:voice, risk:security | done |
| INT-091 | Talker: six-tool registry + introspection test + streaming PolicyGuard + insertion-window scheduler + clip player | E05-voice | INT-060, INT-090 | area:voice, risk:clinical | done |
| INT-092 | Backend Agent: FIFO Work queue, serialized SessionState, delivery semantics, idempotent | E05-voice | INT-081, INT-035 | area:voice | done |
| INT-093 | RED preemption path: stop <=150ms, e2e <=300ms (fake clocks) | E05-voice | INT-091, INT-092, INT-080 | area:voice, risk:clinical | done |
| INT-094 | Runtime invariants 1-11 + RT-01..08 + latency harness | E05-voice | INT-093, INT-110 | area:voice | done |
| INT-096 | Profile typed (full parity fallback) | E05-voice | INT-081 | area:voice | done |
| INT-101 | Session budgets + cost metering per component/profile | E05-voice | INT-092 | area:voice | awaiting-human |
| INT-110 | Lane framework: budgets, backpressure, ObserverState, per-lane consent, type-level read-only | E06-lanes | INT-092, INT-038 | area:lanes, risk:clinical | done |
| INT-112 | linguistic lane: TR lexicons + prosody stats + crisis bypass to triage | E06-lanes | INT-110, INT-080 | area:lanes, risk:clinical, approval:human-clinical | awaiting-human |
| INT-116 | Wellbeing engine: PHQ-2/GAD-2 -> PHQ-9/GAD-7 -> C-SSRS, crisis script, verbatim items, clinician-only outputs | E06-lanes | INT-081, INT-112 | area:clinical, risk:clinical, approval:human-clinical | todo |
| INT-117 | device_functions flag: MDSW boundary enforced (Stage A non-device vs investigation mode) | E06-lanes | INT-116, INT-093, INT-038 | area:legal, risk:legal, approval:human-legal | todo |
| INT-120 | Upload pipeline: ClamAV, sniffing, limits, sandboxed OCR | E07-records | INT-034 | area:records, risk:security | done |
| INT-121 | Document extraction -> FHIR with provenance + confirm cards + eval corpus | E07-records | INT-120, INT-083 | area:records | done |
| INT-130 | Expo app shell: SDK 57 dev build, navigation map per 02, i18n tr-first, theme, a11y base | E08-mobile | INT-001 | area:mobile | done |
| INT-131 | Onboarding & auth: OTP + attestation + DPoP + biometrics + SecureStore + pinning + FLAG_SECURE | E08-mobile | INT-130, INT-012, INT-013 | area:mobile, risk:security | done |
| INT-132 | Consent UI: layered, versioned, lane sub-toggles, learning, satisfaction; who-sees-what | E08-mobile | INT-038, INT-130 | area:mobile, risk:legal, approval:human-legal | done |
| INT-133 | Profiles, companions, guardian flows (minors), proxy acknowledgement | E08-mobile | INT-131, INT-223 | area:mobile, risk:legal | done |
| INT-134 | Visits: create (manual + MHRS SMS OCR), branch picker from taxonomy, visit types | E08-mobile | INT-130, INT-042 | area:mobile | done |
| INT-136 | Typed intake UI (Detayli) + chips + instruments verbatim | E08-mobile | INT-096, INT-130 | area:mobile | done |
| INT-137 | Review & send + Doctor Link QR + CSAT prompt | E08-mobile | INT-084, INT-240 | area:mobile | done |
| INT-138 | Records screens: upload, processing, confirm cards, provenance viewer | E08-mobile | INT-121, INT-130 | area:mobile | done |
| INT-139 | Share centre: active shares, revoke <=1min, access log | E08-mobile | INT-150 | area:mobile | done |
| INT-140 | Me: consents, connectors, language, security, export/delete, learned facts | E08-mobile | INT-037, INT-170 | area:mobile | done |
| INT-150 | Doctor Link: 128-bit token + OTP + expiry + view limit + revoke + watermark + access log + no-index | E09-clinician | INT-084, INT-016 | area:clinician, risk:security | done |
| INT-151 | Note views: SOAP, red flags (mode-aware), provenance, consented wellbeing, AI labels + 1-click feedback | E09-clinician | INT-150, INT-117 | area:clinician | todo |
| INT-170 | PatientOverlay: store, confirmation rules, /me/learned API, engine integration | E11-learning | INT-031, INT-081 | area:learning | done |
| INT-176 | Idempotency keys must be scoped by authenticated principal + tenant (cross-user replay/PHI disclosure) | E01-platform | INT-017 | area:security, risk:security | done |
| INT-177 | Rate limiter: replace per-process monotonic clock with Redis TIME in the Lua script | E01-platform | INT-017 | area:security, risk:security | done |
| INT-178 | Redact traces and metrics pipelines (app-side span scrubbing + collector processors) — errors are not a side channel | E01-platform | INT-013 | area:security, risk:security | done |
| INT-179 | Mobile flow shells: typed-intake chips + review-and-send on fixture data (Mobbin-grounded designs) | E08-mobile | INT-130 | area:mobile | done |
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
| INT-180 | Admin shell: Keycloak RBAC/ABAC, audit on every action, IP allow-list, 4-eyes primitives | E12-admin | INT-023, INT-016 | area:admin, risk:security | done |
| INT-181 | Modules: Overview + Ops + Reliability (real dev telemetry) | E12-admin | INT-180, INT-021, INT-022 | area:admin | done |
| INT-183 | Models & self-hosting registry module + release gate surface | E12-admin | INT-022, INT-180 | area:admin | done |
| INT-210 | Legal document set v1 (tr primary): aydinlatma x5, acik riza per purpose, gizlilik, kullanim kosullari, KVKK basvuru formu, cookie | E14-legal | INT-038 | area:legal, risk:legal, approval:human-legal | awaiting-human |
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
| INT-244 | Name the physician of record in the clinical blocker ledger, and record what a name does and does not unlock | E00-governance | — | area:governance | done |
| INT-254 | DSL/life-threat reconciliation: tense_anchor is a slot reference, explicit rule status, source note, secondary action — and the validator AttributeError INT-041 routed around | E03-protocols | INT-040, INT-041 | area:protocols | done |
| INT-255 | Model the eleven life-threat delivery annotations the DSL still refuses (audio/register, the crisis path, paediatric proxy, document-level blocks) | E03-protocols | INT-254 | area:protocols, risk:clinical, approval:human-clinical | done |
| INT-245 | Counsel factual annex for INT-210: what the software actually does | E14-legal | — | area:legal, risk:legal | done |
| INT-246 | Make a dead voice lane announce itself in development, and add a host probe that measures rather than pings | E08-mobile | INT-239 | area:mobile | done |
| INT-247 | Carried-forward facts must be confirmable before they read as current (the client half of INT-170) | E11-learning | INT-133 | area:mobile | done |
| INT-248 | PolicyGuard precision: Turkish morphology, and the disclaimer the guard was rejecting | E05-voice | INT-091 | area:voice | done |
| INT-249 | Latency-aware voice lane selection: a health check that answers is not a lane that can speak | E05-voice | INT-243 | area:voice | done |
| INT-261 | Voice intake mixes with the typed form: a clip that cannot be spoken ends the whole conversation, and the spoken turn reads the typed form's control copy | E08-mobile | INT-239, INT-249 | area:mobile, area:voice | done |
| INT-285 | The OTP abuse suite's clock is seeded from the wall clock, so a rate-limit refusal depends on the minute CI starts | E08-mobile | INT-131 | area:api, risk:security | done |
| INT-263 | OTP request budgets are fixed hourly windows, so a caller gets twice the limit across a boundary while files/10 §2 says per hour | E08-mobile | INT-131, INT-285 | area:api, risk:security | done |
| INT-258 | Overlay composition mechanism + monotonicity property test (content stays with INT-056) | E03-protocols | INT-041 | area:protocols | done |
| INT-260 | Görünüm: an in-app appearance screen, and the four mechanisms that make its controls do something | E08-mobile | INT-144, INT-193 | area:mobile | done |
| INT-284 | The screens INT-260 did not reach: content that overflows the safe area at both ends, and a glass bar that reserves less room than it occupies | E08-mobile | INT-260 | area:mobile, area:a11y | done |
| INT-293 | Answers given on the dialogue surface never reach the note | E08-mobile | INT-261, INT-282 | area:mobile, area:engine, risk:clinical | done |
| INT-286 | Open-ended asking: the pack declares how each question is asked, and the option list becomes the value space rather than the interaction | E08-mobile | INT-083, INT-239, INT-256, INT-282 | area:mobile, area:voice | done |
| INT-291 | The patient cannot interrupt by speaking: voice barge-in, a measured chunk floor, and a turn-yielding contour | E05-voice | INT-237, INT-249 | area:voice, area:mobile | done |
| INT-294 | TTS lane admission consumes the clip deadline, and the resulting mute latches for the session | E08-mobile | INT-243, INT-249, INT-261 | area:mobile, area:voice | done |
| INT-296 | Session locale: one language per session, chosen rather than detected, and a resource layer that refuses an incomplete one | E01-platform | — | area:platform, area:i18n | done |
| INT-298 | PolicyGuard refuses a locale it has no signed lexicon for, at the type level | E04-engines | INT-296 | area:engine, area:safety, area:i18n | done |
| INT-299 | A translated answer is not the patient's words: the note gains a `translated` attribution class and keeps the original verbatim | E04-engines | INT-296, INT-084 | area:engine, area:clinical, area:i18n | done |
| INT-302 | Which language binds: the legal status of a translated aydınlatma metni, and what the app may show when they differ | E14-legal | INT-296, INT-210 | area:legal, area:i18n, approval:human-legal | todo |
| INT-304 | The share scope can express three sections and the note has eight, so a withheld section is not recorded anywhere | E08-mobile | INT-137 | area:mobile, area:api, risk:legal | done |
| INT-303 | One numeric carrier end to end: a Decimal slot value that reads Unknown to every gate that compares it, and the float it crossed the seam as | E03-protocols | INT-080, INT-083 | area:protocols, area:voice | done |
| INT-313 | Nothing carries an extraction to the phone: the confirm-card transport is owned by no issue | E07-records | INT-121, INT-138 | area:records, area:api | done |
| INT-312 | A TCKN said aloud is not masked: the redactors match a contiguous eleven-digit run and speech arrives as groups or as words | E01-platform | INT-102 | area:security, area:platform, area:voice | done |
| INT-324 | Agent WAV framing lives in voice-clips so the invariant-3 audio guard passes on main | E05-voice | — | area:voice, risk:security | done |
| INT-325 | Production refuses dev bypass flags, file-dev KEK and in-code default credentials | E01-platform | — | area:api, risk:security | done |
| INT-326 | George clip route: authenticated, catalogue-only, rate-limited, absent in production | E05-voice | INT-324, INT-325 | area:voice, area:api, risk:security, risk:legal | done |
| INT-328 | Release builds use a configured https API base and never probe the LAN | E08-mobile | — | area:mobile, risk:security | done |
| INT-344 | App Attest: server verification and iOS client for OTP and session | E08-mobile | INT-325 | area:mobile, area:api, risk:security | done |
| INT-345 | Staging backend artefact: API + Postgres + Redis + OpenBao + TLS proxy on the AWS host, synthetic patients only | E13-infra | INT-325 | area:infra, risk:security, risk:legal | done |
| INT-346 | Restore main CI to green after the billing outage | E13-infra | — | area:ci | done |
| INT-347 | Replace the withdrawn minio/minio image with an owner-approved, digest-pinned S3-compatible store | E13-infra | INT-346 | area:infra, risk:security | awaiting-human |
| INT-348 | Play Integrity verification and a real-device OTP login smoke on TestFlight and Play | E08-mobile | INT-344 | area:mobile, area:api, risk:security | awaiting-human |
| INT-349 | Sensitive slot categories: per-slot data-category tag, encrypted storage, fail-closed register gate | E02-data | INT-327 | area:data, risk:legal, risk:security | doing |
| INT-350 | CI part 2: check-integration builds the pinned edge plugin; osv findings fixed | E13-infra | INT-346 | area:ci | todo |
| INT-352 | Production API on the dedicated AWS host, TLS, stress test and GPU-quota watch (backup until the Frankfurt host) | E13-infra | INT-345, INT-347, INT-325 | area:infra, risk:security, risk:legal | done |
| INT-354 | Consolidate int-demo into main; main becomes the TestFlight build source | E17-release | INT-328, INT-344 | area:mobile, area:release | todo |
| INT-355 | Gated questions never asked: resolve bare ask_if slot names across the pack chain | E04-engines | — | area:engine, risk:clinical | done |
| INT-356 | Counsel completes the data-category register (basis, retention, recipients, consent scope, other-subject notice) | E14-legal | INT-349 | area:legal, risk:legal | awaiting-human |
| INT-357 | Staging passes App Attest and SMS configuration to the API; fail closed when unset | E13-infra | INT-345 | area:infra, risk:security | done |
| INT-358 | SMS vendor decision: DPA, KVKK cross-border mechanism and the egress allow-list row for OTP delivery | E14-legal | INT-329 | area:legal, risk:legal, risk:security | awaiting-human |
| INT-376 | Move the production API host to Frankfurt (eu-central-1) when the GPU quota is approved | E13-infra | INT-352 | area:infra, risk:legal | todo |
| INT-392 | Deleting a session removes its previsit outputs in every erasure and retention path | E02-data | INT-036, INT-037, INT-317 | area:data, risk:legal | done |
| INT-393 | Patient erasure removes Doctor Links, and the retention source text matches the post-INT-317 tree | E02-data | INT-036, INT-037, INT-150, INT-392 | area:data, risk:legal | done |
| INT-390 | Keycloak upgraded to a patched release, and the committed realm imports on it | E12-admin | INT-023, INT-365 | area:admin, risk:security | done |
| INT-382 | The compiler refuses a chain pack's suppress_slot that removes a slot a red-flag rule reads | E03-protocols | INT-258 | area:protocols, risk:clinical | done |
| INT-429 | Unblock the vulnerabilities gate: brace-expansion + urllib3 upgrades, time-boxed node-forge exception | E13-infra | — | area:ci | done |
| INT-395 | DSAR erasure and export cover every patient-deletable table (notification preferences, Doctor Links) | E02-data | INT-037, INT-141, INT-150, INT-393 | area:data, risk:legal | done |
| INT-406 | RED acknowledgement: clinic Safety inbox within 60 s, acknowledgement clock and SLA paging (invariant 49) | E09-clinician | INT-025, INT-080, INT-092, INT-093, INT-180 | area:clinician, risk:clinical | done |
| INT-432 | Clinical decisions register — guideline/openEHR-sourced, agent-authored, independently agent-verified (owner decision D18) | E03-protocols | INT-353 | area:protocols, risk:clinical | done |
| INT-448 | Clinical decisions batch 3 — resolve the #642 sign-off packet items (197) from sourced guidelines | E03-protocols | INT-432 | area:protocols, risk:clinical | done |
| INT-421 | Production release: full stack from main on the AWS host + EAS store builds | E13-infra | INT-352 | area:infra | doing |
| INT-500 | Lockfile advisories since 4 Oct: shell-quote, compression, source-map-js and next upgraded, plus mako | E13-infra | INT-429 | area:security | done |
| INT-453 | voice-runtime RED path picks its script from rule_ids[0] — must use the firing rule's own script | E05-voice | INT-080, INT-093 | area:voice, risk:clinical | done |
| INT-446 | RED end-to-end in the app — rules-engine hop on the dialogue lane, pre-positioned RED screen mounted | E08-mobile | INT-080, INT-103, INT-333 | area:mobile, risk:clinical | done |
| INT-465 | generic RED active from CD-24, and the red rule set signed with a synthetic-only test key | E03-protocols | INT-432, INT-446, INT-453 | area:protocols, risk:clinical, risk:security | done |
| INT-544 | A pull request clears CI in under 20 minutes on the intake-aws-ci pool: cache seed, sharded check-py, path-scoped lanes, queued main runs collapse | E13-infra | INT-467, INT-524 | area:ci, approval:human-infra | done |
| INT-430 | Agent council for dynamic questioning: a post-bind verifier that only appends scripted re-asks and confirm-backs; the deterministic engine adjudicates; on-prem or API models | E05-voice | INT-081, INT-083, INT-092, INT-095, INT-101 | area:voice, risk:clinical | doing |
| INT-428 | Hosted model lanes (OpenAI or similar) switchable from the admin panel, with a GPU switch-over | E05-voice | INT-182, INT-187, INT-018 | area:api, area:voice, risk:security | awaiting-human |
| INT-485 | Admin oauth2-proxy logs no staff email or client IP (invariant 6) | E13-infra | INT-421 | area:infra | done |
| INT-441 | base.intake gates compare code slots against values the slot can carry (proxy_reported, lmp_date) | E03-protocols | INT-043 | area:protocols, risk:clinical | done |
| INT-518 | Live extraction gets the committed value table, so every code slot a red-flag rule reads can bind | E03-protocols | INT-083, INT-432 | area:protocols | done |
| INT-521 | The live voice and typed session evaluates triage on every bound answer, so a RED fires from the conversation | E05-voice | INT-518, INT-093 | area:voice | done |
| INT-522 | chest_pain.onset_at binds from its closed-choice answer, so the K2 rule's tense anchor is known live | E03-protocols | INT-518, INT-521 | area:protocols | done |
| INT-540 | The onset anchor always resolves, so K2 cannot stay silent | E05-voice | INT-522 | area:voice | done |
| INT-531 | A RED evaluated between turns reaches the patient within the 300 ms budget without waiting for the next turn | E05-voice | INT-521 | area:voice | done |
| INT-550 | A new staff user enrols a passkey after the password step | E12-admin | INT-378, INT-421, INT-538 | area:security | done |

## P1

| id | title | epic | depends on | labels | status |
|---|---|---|---|---|---|
| INT-095 | Profile residency_tr with real self-hosted adapters (03 §4.9.1 rows 1-2, 7, 10-11) + on-hardware smoke | E05-voice | INT-094, INT-018 | area:voice, approval:human-infra, gpu | awaiting-human |
| INT-099 | Backchannels + ack styles + preemptive generation + per-profile NFR harness in CI | E05-voice | INT-095 | area:voice | todo |
| INT-100 | Vendor failover + circuit breakers + typed fallback <=2s + chaos test | E05-voice | INT-095, INT-024 | area:voice | done |
| INT-102 | Adversarial suite RT-09..14 in make safety + nightly LLM red-team job | E05-voice | INT-094, INT-083 | area:safety, risk:security | done |
| INT-103 | Mobile voice client: LiveKit RN, permissions, network-quality per turn, reconnect, background | E05-voice | INT-130, INT-090 | area:mobile | done |
| INT-111 | affect lane: self-hosted SER on the agent worker (03 §4.9.1 row 14) + Turkish eval set | E06-lanes | INT-110 | area:lanes, approval:human-clinical | awaiting-human |
| INT-113 | asr_quality lane: shadow-STT disagreement + confirm-by-card trigger | E06-lanes | INT-110, INT-095 | area:lanes, approval:human-legal | awaiting-human |
| INT-114 | engagement lane -> satisfaction proxies + pacing hints | E06-lanes | INT-110 | area:lanes, approval:human-legal | awaiting-human |
| INT-122 | e-Nabız export/PDF import parser + MHRS SMS screenshot OCR | E07-records | INT-121 | area:records | done |
| INT-123 | pgvector record index (RLS, per-patient namespace) + retrieval Work | E07-records | INT-030, INT-121 | area:records | done |
| INT-135 | Voice intake UI (Hizli): states, recording indicator, inline cards, barge-in, RED UI, typed fallback | E08-mobile | INT-103, INT-096, INT-117 | area:mobile, risk:clinical | todo |
| INT-141 | Notifications: content-free reminders, quiet hours, opt-out; transactional-only | E08-mobile | INT-130 | area:mobile, risk:legal | done |
| INT-142 | Offline drafts + sync + resilience | E08-mobile | INT-136 | area:mobile | done |
| INT-143 | Kiosk mode: MDM lockdown, clinic PIN, 60s auto-wipe, privacy layout | E08-mobile | INT-136 | area:mobile, risk:security | done |
| INT-144 | Accessibility WCAG 2.2 AA pass + TR screen-reader labels + conformance report | E08-mobile | INT-130 | area:mobile, risk:legal | awaiting-human |
| INT-145 | Client telemetry: GlitchTip crash (PHI-scrubbed), perf, RUM web | E08-mobile | INT-023, INT-130 | area:mobile | done |
| INT-146 | EAS builds + OTA code signing + MobSF gate + store listings/privacy labels | E08-mobile | INT-131, INT-224 | area:mobile, risk:legal, approval:human-legal | todo |
| INT-152 | Clinic console: today list, statuses, read receipts, tenant isolation, SSO | E09-clinician | INT-151, INT-030 | area:clinician | todo |
| INT-153 | Clinician feedback -> Langfuse annotation queues + acceptance metrics | E09-clinician | INT-151, INT-175 | area:clinician | todo |
| INT-160 | Connector framework: adapters, OpenBao creds, idempotency, receipts, allow-listed endpoints, mTLS | E10-connectors | INT-018, INT-035 | area:connectors, risk:security | done |
| INT-161 | FHIR push adapter (hospital FHIR/HAPI; SMART backend services auth) | E10-connectors | INT-160, INT-033 | area:connectors, approval:human-vendor, live-smoke | awaiting-human |
| INT-175 | Langfuse self-hosted + annotation queues (note_quality, hallucination_audit, false_red_review) + CI experiment gate | E11-learning | INT-023 | area:observability | done |
| INT-228 | Tokenizer pseudonyms exceed DocumentStore key-segment bound: integrate or widen the shape | E02-data | INT-034 | area:data | done |
| INT-182 | Voice module + kill switch + profile switch + canary weights (4-eyes) | E12-admin | INT-181, INT-094 | area:admin, risk:clinical | done |
| INT-185 | Clinical quality & safety module + annotation-queue links | E12-admin | INT-175, INT-180 | area:admin | done |
| INT-186 | Experience & satisfaction module (CSAT/NPS/pulse/waits + SDS-01 export) | E12-admin | INT-240, INT-180 | area:admin, approval:human-legal | awaiting-human |
| INT-187 | CI/CD & releases module (GH API + Argo CD + gates + freeze) | E12-admin | INT-181 | area:admin | done |
| INT-188 | Flags module (Unleash) + 4-eyes on safety flags | E12-admin | INT-023, INT-180 | area:admin | done |
| INT-189 | Compliance module: consents, vendor register, audit search, DSAR queue, retention, DPIA, residency, evidence exports | E12-admin | INT-036, INT-037, INT-038, INT-180 | area:admin, risk:legal | done |
| INT-190 | Cost module | E12-admin | INT-101, INT-180 | area:admin | awaiting-human |
| INT-192 | Security module: SIEM feeds, vulns vs SLA, rotations, drills, integrity | E12-admin | INT-205, INT-180 | area:admin, risk:security | done |
| INT-202 | Backups: pgBackRest PITR encrypted + MinIO replication + automated restore drill + evidence | E13-infra | INT-030, INT-034 | area:infra, risk:security | doing |
| INT-203 | Edge: Traefik + Coraza CRS + CrowdSec + cert-manager + prod egress proxy | E13-infra | INT-018 | area:infra, risk:security, blocked:runtime | awaiting-human |
| INT-205 | Wazuh + Falco deployment + rules + console feed | E13-infra | INT-023 | area:infra, risk:security | done |
| INT-206 | GitHub Actions self-hosted runners in TR DC + no-PHI-in-CI policy | E13-infra | INT-002 | area:infra, approval:human-infra, blocked:contract | awaiting-human |
| INT-213 | DPIA v1 + vendor transfer register + SCC set + Board notification workflow (5 business days) + hospital DPA template | E14-legal | INT-018, INT-210 | area:legal, risk:legal, approval:human-legal | todo |
| INT-214 | Breach machinery: KVKK 72h Board form automation + data-subject notices + USOM report (7545) + hospital notices | E14-legal | INT-020 | area:legal, risk:legal | todo |
| INT-215 | Special-category adequate measures (Board 2018/10) mapping + evidence export | E14-legal | INT-019, INT-023 | area:legal, risk:legal | done |
| INT-217 | QMS core (ISO 13485): quality manual, design controls, ISO 14971 risk file, IEC 62304 class B plan, IEC 62366-1 usability, IEC 81001-5-1 security lifecycle, PMS plan, PRRC | E14-legal | INT-216 | area:legal, risk:legal, approval:human-legal | todo |
| INT-218 | Clinical investigation package: protocol + ICF(tr) + KAEK ethics submission + TITCK application + insurance + registration | E14-legal | INT-217 | area:legal, risk:legal, approval:human-legal | todo |
| INT-224 | Store compliance: Apple health guidelines + Google Play Health policy + Data safety/privacy labels + IARC | E14-legal | — | area:legal, risk:legal, approval:human-legal | done |
| INT-226 | Accessibility conformance report (WCAG 2.2 AA / EN 301 549) generated from the a11y CI results | E14-legal | INT-144 | area:legal | done |
| INT-241 | Wait-time metrics end-to-end + SDS-01 style exports | E16-experience | INT-240, INT-025 | area:experience | done |
| INT-242 | NPS scheduling + clinician pulse survey cadence | E16-experience | INT-240 | area:experience | done |
| INT-252 | Release process: semver, changelog, signed artifacts, store submission checklist, release-gate checklist in console | E17-release | INT-019, INT-183 | area:release | todo |
| INT-253 | Localization completeness: tr 100 percent, en 100 percent; ar planned P3 with RTL audit | E17-release | INT-130 | area:release | done |
| INT-256 | Universal history sections (allergy, medication, PMH, family) composed onto every department pack | E04-engines | INT-247 | area:engine | done |
| INT-282 | Base-layer questions from the HBYS schema, and department branching on the answers | E04-engines | INT-256 | area:engine, risk:clinical | done |
| INT-295 | The Detayli mode bar puts 'Siraniz geldi' off the screen, and nothing scrolls sideways to bring it back | E08-mobile | INT-284 | area:mobile, area:a11y | done |
| INT-297 | The DSL's `*_tr` fields become per-locale maps, mechanically and with `tr` still required | E03-protocols | INT-296 | area:protocols, area:i18n | done |
| INT-300 | A locale without pinned, licence-verified speech models is text-only, and a locale without a number expander cannot speak a numeral at all | E05-voice | INT-296, INT-297 | area:voice, area:i18n | done |
| INT-301 | Language choice at first run and inside a visit, the switch that does not lose the session, and right-to-left | E08-mobile | INT-296 | area:mobile, area:a11y, area:i18n | done |
| INT-305 | One-tap CSAT cannot form a csat.v1 event, because the schema requires a reason the first tap has not given | E16-experience | INT-240, INT-137 | area:experience, area:mobile | done |
| INT-306 | The schema records a visit DATE and the expiry rule needs a visit DATETIME | E02-data | — | area:data | done |
| INT-308 | carrier/geo sanity checks against SMS pumping are named in the security spec and implemented nowhere | E01-platform | INT-263 | area:security, area:platform | awaiting-human |
| INT-309 | A Decimal still loses its type at three boundaries: the FHIR scalar mapper, the overlay store, and a JSON round trip | E02-data | INT-303 | area:data | done |
| INT-310 | Eight npm advisories block make security, including vitest at CVSS 9.8 | E13-infra | INT-019 | area:security, area:ci | done |
| INT-311 | Nobody owns issuing a Doctor Link from the patient's phone, and three issues have refused it in a row | E08-mobile | INT-150, INT-139 | area:mobile, area:security | done |
| INT-314 | Four spoken fields are still Turkish-only, so a red-flag action script cannot yet be per-locale | E03-protocols | INT-297 | area:protocols, area:i18n, area:safety | done |
| INT-315 | assert_restore_target_outside_workspace resolves the target and not the workspace, so a symlinked directory INSIDE the repo reads as outside | E13-infra | — | area:infra, area:security | done |
| INT-317 | previsit output store + hospital read-back: one frozen versioned document per completed previsit, fetched by patient number under a consent scope and an audit entry | E10-connectors | — | area:connectors, area:api, area:data, area:security | doing |
| INT-318 | Acıbadem appointments read source, /v1/visits/sync and the phone-first login it feeds | E10-connectors | INT-160, INT-131 | area:connectors, area:api, risk:security | done |
| INT-319 | Dev on-prem expressive-TTS lane for scripted questions + latency assessment harness | E05-voice | — | area:voice, area:lanes, gpu, approval:human-vendor | awaiting-human |
| INT-321 | Intake asks its mode up front; 'Sıranız geldi' becomes 'Bitirdim' and the per-question mode row is retired | E08-mobile | INT-295, INT-286 | area:mobile, area:a11y | done |
| INT-323 | Department-dynamic previsit routing: inbound department → branch → served pack | E03-protocols | INT-042, INT-134 | area:protocols, area:connectors | done |
| INT-327 | Specialty-pack generator assembles the pending-value marker so no_placeholders stays green | E03-protocols | — | area:protocols | doing |
| INT-329 | Twilio SMS delivery adapter: async, egress-guarded, secrets from OpenBao, fail-closed outside dev | E01-platform | INT-325 | area:api, risk:security, risk:legal | done |
| INT-330 | Motion: native-stack transition policy — 120 ms on every stack, legal instant, intake gesture-locked | E08-mobile | — | area:mobile | todo |
| INT-331 | Motion: one fail-closed reduce-motion store bridged to Reanimated | E08-mobile | INT-330 | area:mobile | done |
| INT-332 | ADR: Motion system v1 (opacity-only ≤ 120 ms, arbiter order, no-motion surfaces, haptics policy, RED as root layer) | E00-governance | — | area:mobile, approval:owner | todo |
| INT-333 | Motion: RED contract — zero motion, first paint as a root layer never behind a navigator, no haptic | E08-mobile | INT-330, INT-332 | area:mobile, risk:clinical | done |
| INT-343 | Mobile George client authenticates and requests only compiled-pack clip text | E08-mobile | INT-326 | area:mobile, area:voice, risk:security | todo |
| INT-351 | Admin ops console: server health, GPU quota and model hosts, model usage, ElevenLabs clip cache/usage, wait time, CSAT, CI/CD | E12-admin | INT-181, INT-186, INT-187 | area:admin | done |
| INT-353 | Land the specialty review queue, generator and verification trail on main | E03-protocols | INT-327 | area:protocols | done |
| INT-359 | Accessibility device audit (DA-01..DA-08) and the statement published in-app and web | E14-legal | INT-226 | area:legal, risk:legal | awaiting-human |
| INT-360 | WCAG 1.3.4: the app is not locked to portrait unless a screen's orientation is essential | E08-mobile | INT-226 | area:mobile, risk:legal | done |
| INT-361 | WCAG 3.3.8: the OTP field accepts a pasted or autofilled code | E08-mobile | INT-226 | area:mobile, risk:legal | done |
| INT-362 | WCAG 3.3.1 / 4.1.3: error and status lines are announced under VoiceOver as well as TalkBack | E08-mobile | INT-226 | area:mobile, risk:legal | done |
| INT-363 | WCAG 2.2.1: the kiosk idle wipe warns before it clears and lets the patient extend | E08-mobile | INT-226 | area:mobile, risk:legal | done |
| INT-364 | Board 2018/10 organisational measures: the owner's evidence and counsel's four readings | E14-legal | INT-215 | area:legal, risk:legal | awaiting-human |
| INT-365 | Staff second factor and session bounds: the console refuses a token issued without a second factor | E12-admin | INT-215 | area:admin, risk:security | done |
| INT-366 | Quarterly access review generated by the console, and one-action offboarding with a 60-day auto-disable | E12-admin | INT-365 | area:admin, risk:security | done |
| INT-367 | Scheduled quarterly key rotation that emits sec_secret_rotation_due_days | E02-data | INT-215 | area:security, risk:security | done |
| INT-368 | Continuous dependency security updates (Renovate) for every lockfile | E13-infra | INT-215 | area:infra, risk:security | done |
| INT-369 | schemathesis API fuzzing runs in CI instead of being recorded as deferred | E13-infra | INT-215 | area:infra, risk:security | todo |
| INT-372 | Visit-card chevron clears long department names | E08-mobile | — | area:mobile | done |
| INT-370 | Visits calendar view and Geçmiş (past) list on Vizitlerim | E08-mobile | INT-341 | area:mobile | done |
| INT-378 | Keycloak WebAuthn provider writes aaguid and credential_id session notes for the console's claims | E12-admin | INT-373, INT-365 | area:admin, risk:security | done |
| INT-389 | Owner decision: second factor for console roles outside the patient-content set (TOTP vs aaguid) | E12-admin | INT-378, INT-365 | area:admin, risk:security | awaiting-human |
| INT-377 | /admin/models and /admin/ops fail closed on a malformed probe-results file | E12-admin | INT-183, INT-351 | area:admin | done |
| INT-373 | Keycloak realm emits the claims the admin console requires (aud=api, org, tenant, aaguid, credential_id) | E12-admin | INT-180 | area:admin, risk:security | done |
| INT-380 | Extraction eval score on a named, dated, licensed corpus (INT-121 clause 3) | E07-records | INT-121, INT-381 | area:records, risk:clinical | awaiting-human |
| INT-381 | On-hardware latency and live smoke for the row-9 extraction model (INT-124 clause: target < 3 s) | E07-records | INT-124 | area:records, gpu | todo |
| INT-385 | Record quantities render with the Turkish decimal comma as one number+unit atom | E07-records | INT-121 | area:records, risk:clinical | done |
| INT-391 | The console accepts every valid WebAuthn credential id (leading - or _, and longer than 96 bytes) | E12-admin | INT-180, INT-365 | area:admin, risk:security | done |
| INT-386 | Clinical quantities in the typed lane, note, patient summary and FHIR document text use the locale decimal separator | E07-records | INT-385 | area:records, risk:clinical | done |
| INT-387 | The accessibility conformance report reflects the INT-361, INT-362 and INT-363 fixes | E14-legal | INT-226, INT-361, INT-362, INT-363 | area:legal | done |
| INT-397 | WCAG 4.1.3: the last three status lines are announced (notifications pending, review sent, consent queue) | E08-mobile | INT-362, INT-387 | area:mobile, risk:legal | done |
| INT-396 | Backlog rows match what merged: status reconciliation and a guard against drift | E00-governance | INT-004 | area:platform | done |
| INT-401 | Rollback from the console (4-eyes) once a CD target exists | E12-admin | INT-187 | area:admin, risk:security | awaiting-human |
| INT-402 | Record-embedding model for the patient record index (files/03 §4.9.1) | E07-records | INT-123 | area:records, risk:security | awaiting-human |
| INT-403 | What withdrawing documents consent does to the patient's record vectors | E02-data | INT-123 | area:data, risk:legal | awaiting-human |
| INT-405 | The backlog sync pages past 500 issues and keeps issue state in step with rows | E00-governance | INT-004, INT-396 | area:platform | done |
| INT-408 | Workers tier SLOs: the owner decides the tier and its targets | E01-platform | INT-021 | area:observability | awaiting-human |
| INT-398 | Document engine for records (files/03 rows 20-21): choose, verify the licence, register, sandbox | E07-records | INT-122 | area:records, risk:security | awaiting-human |
| INT-399 | Real e-Nabiz export and MHRS SMS samples for the import parsers (HB-A1, Ask 2) | E07-records | INT-122 | area:records | awaiting-human |
| INT-400 | The on-device MHRS SMS parser refuses an ambiguous date, as the server does | E08-mobile | INT-122 | area:mobile, risk:clinical | done |
| INT-409 | The visits list uses the real date, not a pinned TODAY_FIXTURE, in every build | E08-mobile | INT-370 | area:mobile, risk:clinical | done |
| INT-410 | Release bundles carry no synthetic seed accounts (audit F30) | E08-mobile | INT-130 | area:mobile, risk:security | done |
| INT-412 | Apple-native chrome: SF Symbols with Android fallbacks, Liquid Glass rail honouring Reduce Transparency, layered icon proposal | E08-mobile | INT-360 | area:mobile | done |
| INT-413 | Counsel drafts for the open legal texts (data categories, SMS transfer, accessibility statement, org measures, breach notices) | E14-legal | INT-215 | area:legal, risk:legal | done |
| INT-404 | Triage rule evidence strings render quantities with the locale decimal separator | E03-protocols | INT-386 | area:protocols, risk:clinical | done |
| INT-415 | ElevenLabs delivery profiles per question context + on-prem TTS wiring guide | E05-voice | INT-326 | area:voice | done |
| INT-431 | The embed sample's test builds its JWT fixture at runtime, so secret scanners see no token at rest | E10-connectors | INT-320 | area:release, risk:security | done |
| INT-426 | CI on AWS: gate runner via S3+SSM with commit status, no workflow edits | E13-infra | INT-352 | area:ci | done |
| INT-407 | Visit lifecycle state machine (02 §2b): a RED visit cannot silently move | E02-data | INT-197, INT-150, INT-306, INT-406 | area:api, risk:clinical | done |
| INT-414 | Conversational question delivery — warm opener, context- and affect-aware lead-ins, questions verbatim | E08-mobile | INT-415 | area:mobile | done |
| INT-447 | Clinical decisions batch 2 — verify INT-414's 48 delivery lines (PolicyGuard, B1, siz, sourced) | E08-mobile | INT-432 | area:mobile, risk:clinical | done |
| INT-449 | Turkish voice casting: the best native Turkish ElevenLabs voice and model, natural intonation | E05-voice | INT-415 | area:voice | done |
| INT-463 | All CI jobs on the AWS self-hosted runner | E13-infra | INT-206, INT-426 | area:ci, approval:human-infra | awaiting-human |
| INT-467 | A pool of three ephemeral intake-aws-ci runners, each isolated as runner 1 is | E13-infra | INT-463 | area:ci, approval:human-infra | awaiting-human |
| INT-460 | Second admin approver for synthetic staging: a second Keycloak user, never a second dev bearer | E12-admin | INT-180, INT-325, INT-365 | area:admin, risk:security | done |
| INT-524 | CI cancels a pull request's superseded runs (concurrency group), so the three-runner pool runs only current heads | E13-infra | INT-467 | area:ci, approval:human-infra | done |
| INT-501 | http-cache-semantics lifted to 4.3.0, so its time-boxed osv exception can go before it expires | E13-infra | INT-500 | area:security | done |
| INT-508 | node-forge and braces have no upstream fix: renew their time-boxed exceptions or replace the dependents before 1 Nov 2026 | E13-infra | INT-500 | area:security | todo |
| INT-424 | ElevenLabs delivery profiles v2 — sample-tuned naturalness + expressive-model ADR proposal | E05-voice | INT-415 | area:voice | done |
| INT-475 | RED staff notification on the typed hop and the device's location answer reach the server | E09-clinician | INT-432 | area:api, risk:clinical | done |
| INT-538 | One laptop command creates a staff user on the synthetic host: temporary password via SSM, passkey registration required | E13-infra | INT-460 | area:infra | done |
| INT-442 | Egress forward proxy for the synthetic AWS host (hosted lanes reach only allow-listed vendors) | E05-voice | INT-428, INT-018 | area:infra, risk:security | awaiting-human |
| INT-443 | ElevenLabs as the hosted TTS provider, default on the synthetic AWS host (v2 delivery profiles) | E05-voice | INT-442, INT-428, INT-424, INT-326 | area:voice, risk:security | awaiting-human |

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
| INT-124 | Lab-report->JSON via the self-hosted extraction LLM (03 §4.9.1 row 9) + Turkish unit-resolution eval | E07-records | INT-121 | area:records | done |
| INT-162 | HBYS/SBYS adapter kit (HL7v2 ORU / file drop / FHIR) + USVS mapping + KTS registration pack | E10-connectors | INT-160 | area:connectors, risk:legal, approval:human-legal | done |
| INT-163 | Check-in: signed QR payload + desk verification + checkin_to_seen metric | E10-connectors | INT-160, INT-143 | area:connectors | done |
| INT-171 | De-identified analytics views + k-anonymity helper + rollups | E11-learning | INT-015, INT-030 | area:learning, risk:legal | done |
| INT-172 | services/learning Inspector->Architect + proposal schema + evidence bundles + PR bot (open-not-merge) | E11-learning | INT-171, INT-004 | area:learning, risk:clinical | done |
| INT-173 | Canary/rollback controller on guardrail KPIs (5/25/100) | E11-learning | INT-172, INT-025 | area:learning | done |
| INT-174 | DSPy+GEPA offline optimisation (extraction, note modules only) with clinician-edit metric + held-out | E11-learning | INT-153, INT-172 | area:learning | todo |
| INT-184 | Protocols module: coverage, review queue, proposals, canary, clips | E12-admin | INT-042, INT-172, INT-180 | area:admin | done |
| INT-191 | Tenants module + onboarding flow | E12-admin | INT-180, INT-250 | area:admin | todo |
| INT-200 | Residency compose profile (GPU) + runbooks | E13-infra | INT-097 | area:infra, gpu | todo |
| INT-201 | k8s: k3s + Argo CD + Kyverno/Sigstore admission + PSS restricted + default-deny + Harbor | E13-infra | INT-019 | area:infra, risk:security, approval:human-infra | todo |
| INT-204 | Mesh mTLS (Linkerd) + default-deny NetworkPolicies | E13-infra | INT-201 | area:infra, risk:security | todo |
| INT-207 | Chaos suite (monthly) + load to pilot x3 + autoscaling rules | E13-infra | INT-024, INT-201 | area:infra | todo |
| INT-219 | Technical documentation (Annex II/III) + clinical evaluation (MDCG 2020-1) + PMCF + notified-body selection | E14-legal | INT-217 | area:legal, risk:legal, approval:human-legal | todo |
| INT-220 | Registrations: UTS (TCKKD-KLVZ-03) + UDI; KTS (SBYS) pack; BTK yer saglayici; traffic-log retention 5651 | E14-legal | INT-219, INT-162 | area:legal, risk:legal, approval:human-legal | todo |
| INT-221 | Public-hospital pack: Genelge 2019/12 residency attestation + DDO Rehber mapping + USVS conformance | E14-legal | INT-183, INT-162 | area:legal, risk:legal | awaiting-human |
| INT-222 | Consumer/commercial: mesafeli sozlesme pre-info + withdrawal (if paid tier), IYS integration for marketing, Turkish-language compliance | E14-legal | INT-210 | area:legal, risk:legal, approval:human-legal | todo |
| INT-227 | AI governance file: model cards, TR bias/fairness eval (dialect, gender, age), transparency labels, EU AI Act readiness note | E14-legal | INT-095, INT-116 | area:legal, risk:legal | todo |
| INT-230 | Research data pipeline: anonymisation (KSVY-16), research consent gating, export for studies | E15-research | INT-015, INT-038 | area:research, risk:legal, approval:human-legal | done |
| INT-231 | Study tooling: instruments + analysis notebooks for tracks 1-6 (voice vs typed, triage validation, note quality, psychiatric-signal validation) | E15-research | INT-230 | area:research, approval:human-legal | awaiting-human |
| INT-262 | Research extracts: differencing gate across the register (a second extract over an overlapping window re-identifies) | E15-research | INT-230 | area:research, risk:legal, approval:human-legal | done |
| INT-250 | Tenant onboarding: config, branding, packs, DPA signature via KEP/e-imza, runbook | E17-release | INT-189, INT-213 | area:release, risk:legal | todo |
| INT-307 | publish_wait / roll_up_wait handle only the labelled records_processing family, so an unlabelled wait series has nowhere to be written | E01-platform | — | area:platform, area:observability | done |
| INT-320 | Embeddable white-label integration: partner 'Start pre-visit' button + tenant handshake (ADR + scaffold) | E10-connectors | INT-250 | area:release, risk:security, risk:legal, approval:human-legal | doing |
| INT-322 | Embed handshake: intake mode (hastanede/brief) bound inside the signed launch ticket | E10-connectors | INT-320 | area:release, risk:security, risk:legal | done |
| INT-334 | Motion: arbiter and commit windows (pure) | E08-mobile | INT-333 | area:mobile | done |
| INT-335 | Motion: Reanimated hygiene gates before the first Reanimated consumer | E08-mobile | INT-331 | area:mobile | done |
| INT-336 | Motion: presence orb — one UI-thread state visual replacing PulseDot and the dialogue spinners | E08-mobile | INT-332, INT-334, INT-335 | area:mobile, risk:clinical | todo |
| INT-337 | Motion: dialogue transients wired to the arbiter | E08-mobile | INT-334, INT-335, INT-336 | area:mobile | todo |
| INT-338 | Motion: section sheet — measured fade budget, instant privacy and RED closes | E08-mobile | INT-331, INT-334, INT-335 | area:mobile | todo |
| INT-339 | Motion: typed lane, fallback and completion | E08-mobile | INT-330, INT-335 | area:mobile | done |
| INT-340 | Haptics: one policy, sticky suppression, server-confirmed success | E08-mobile | INT-332, INT-333 | area:mobile, risk:legal | todo |

## P3

| id | title | epic | depends on | labels | status |
|---|---|---|---|---|---|
| INT-032 | EHRbase export tier: OPT templates + client + roundtrip (P3 export per D8) | E02-data | INT-031 | area:data | done |
| INT-257 | openEHR OPT: the committed template has no occurrences and a live CDR rejects it | E02-data | INT-032 | area:data | done |
| INT-097 | residency_tr_models tier on GPU: compose.residency, node sizing, on-hardware latency evidence | E05-voice | INT-094, INT-095 | area:voice, approval:human-infra, gpu, blocked:contract | todo |
| INT-225 | ISO 27001 ISMS: scope, SoA, risk register, policies, internal audit, certification audit | E14-legal | INT-215, INT-192 | area:legal, risk:legal, approval:human-legal | todo |
| INT-251 | Billing: hospital e-Fatura via provider; patient subscription via PSP (iyzico/PayTR); never store PAN | E17-release | INT-222 | area:release, risk:legal, approval:human-legal | todo |
| INT-341 | Motion: press-opacity tokens | E08-mobile | INT-330 | area:mobile | todo |
| INT-342 | Motion: content reveal and a static skeleton | E08-mobile | INT-331, INT-334, INT-335 | area:mobile | todo |

