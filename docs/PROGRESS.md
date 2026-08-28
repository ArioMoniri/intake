# PROGRESS — one entry per LOOP iteration (template in LOOP.md)

### 2026-08-27T16:20:00+03:00 · INT-001 · done
- Goal: Monorepo bootstrap — workspaces, Makefile, pre-commit, compose.dev, plus the 07 §3 governing documents and the 175-issue backlog, per the 07 §4 cold-start order.
- Plan: failing smoke suite first; extract 07 §3 files byte-for-byte (verbatim pinned by test); author issues.yaml from 07 §3.11 with D8 corrected in place; implement workspaces/Makefile/compose; prove the vendor-call gate can fail.
- Tests added (with the near-miss negative for any safety rule): tests/smoke/test_make_check.py (18 tests; no safety rules in scope — the compose test carries a negative control asserting EHRbase is absent per D8); scripts/ci/assert_no_vendor_calls.sh proven red on a planted vendor host, then reverted.
- Result: `make check` green (ruff, ruff-format, mypy --strict, pytest 18/18, eslint, tsc, vitest 3/3); `make setup` exit 0; `make dev` all four containers healthy (pgvector 0.8.6 live, HAPI serving a CapabilityStatement). `make safety`/`make security` do not exist yet (arrive with INT-002/INT-019/INT-059).
- Invariants touched and still passing: none of the runtime invariants are exercised by this change; DoD list-A items satisfied are recorded in the evidence file.
- Decisions / ADRs / 00_STATE.md rows: D8 applied in place to INT-001/022/032/037 (00 §8 row); repo-pushed header fix; HB-I3 closed; HB-I1 fact recorded; owner's AWS-box directive recorded (00 §8 + runbook).
- Blocked on (human + one sentence + HUMAN_BLOCKERS id): owner — free 80–100 GB disk and raise Docker RAM for the obs/security tiers and model pulls (HB-I1, HB-I2). Non-blocking note: confirm the Apache-2.0/proprietary licence split (07 §4).
- Next: INT-002 CI base + zero-placeholder and evidence gates.
- LOOP_STATUS: CONTINUE

### 2026-08-27T17:10:00+03:00 · INT-002 · done
- Goal: CI base — ci.yml (check-py/check-ts/gates, cached, vendor-free), no_placeholders + evidence_check gates, coverage floors per invariant 8.
- Plan: failing tests first (16), then the two gate scripts + allow-list + coverage_thresholds.yaml + ci.yml + Makefile/vitest floor enforcement.
- Tests added: tests/ci/test_no_placeholders.py (incl. per-token detection and the permitted clinical form as its negative-control pair), tests/ci/test_evidence_check.py, tests/ci/test_coverage_floors.py (only-rise pinning). Planted TODO proved red at repo level, reverted (evidence file).
- Result: pytest 34 passed; make check fully green incl. new coverage floors (py branch cov ≥ 85 on intake_platform; ts v8 coverage 100 against floor 85).
- Invariants touched and still passing: 17 (now enforced), 8 (pinned only-rise), 14 (partial — full set INT-019).
- Decisions / 00 rows: intake_platform shares the api coverage floor (85) — recorded in evidence; coverage_thresholds.yaml added to the hook-protected list.
- Blocked on: nothing new. PR merges are gated by the harness classifier this session — PRs stack (int-2 based on int-1); owner merges bottom-up or grants `gh pr merge`.
- Next: INT-003 ADRs + blueprint index.
- LOOP_STATUS: CONTINUE

### 2026-08-27T17:55:00+03:00 · INT-003 · done
- Goal: ADR-000 template + ADR-001..023 Accepted (07 §3.12), blueprint indexed from docs/index.md.
- Plan: failing tests/docs/test_adr_index.py first (existence, three sections, amendment notes, content anchors on the high-stakes decisions, index completeness), then the 24 ADRs + docs/index.md.
- Tests added: tests/docs/test_adr_index.py (7 tests incl. content anchors — an ADR that says the wrong thing is worse than a missing one).
- Result: pytest 41 passed; make check green; no_placeholders green (after fixing the gate's self-reference trip — landed on INT-002's open PR, where the gate lives).
- Invariants touched and still passing: none at runtime; ADRs record their rationale. No accuracy claim in any ADR (D16).
- Decisions / 00 rows: none new — the ADRs transcribe already-settled decisions (D1–D17); INT-003's acceptance count corrected in place (020 → 023 per §3.12).
- Blocked on: nothing new.
- Next: INT-004 backlog machinery (issues.yaml → GitHub, loop runner).
- LOOP_STATUS: CONTINUE

### 2026-08-27T18:40:00+03:00 · INT-004 · done
- Goal: backlog machinery — schema validation, deterministic LOOP selector, GitHub sync (issues/labels/milestones/board), templates, backlog-status, files/11 as a generated rendering.
- Plan: failing tests first (7), then backlog_lib + next_issue + sync_issues (hermetic dry-run planner + live gh apply) + render_backlog + backlog_status + feature.yml + pull_request_template.md + Makefile targets.
- Tests added: tests/backlog/test_schema.py (schema, cycle proof, selector incl. the awaiting-human-satisfies-deps rule and WAITING_HUMAN listing), tests/backlog/test_sync_dryrun.py (planner, labels/milestones/board columns, templates, files/11 drift check, status report).
- Result: pytest 51 passed; make check green; live sync run against ArioMoniri/intake (175 issues; output in evidence).
- Invariants touched and still passing: none at runtime; ADR-019's machinery is complete.
- Decisions / 00 rows: files/11 becomes the generated rendering of issues.yaml (its header says so; drift is a test failure); allow-list pinned set grew by docs/adr/ with the reason stated.
- Blocked on: PR merges remain owner-side (harness classifier); board creation may need `gh auth refresh -s project`.
- Next: INT-043 — draft base.intake and put it in the owner's inbox (unblocks 78 of 175).
- LOOP_STATUS: CONTINUE

### 2026-08-27T20:40:00+03:00 · INT-010 · done
- Goal: the monitoring-contract entry points — mount_health (healthz/readyz/metrics/version) + the service-enumeration contract.
- Plan: failing tests first (collection error — module and fastapi absent), then health.py (ReadinessCheck with per-check timeout, VersionInfo.from_env, Prometheus exposition, discover_services + verify_service_declarations) and the good/bad fixture services proving the contract can fail.
- Tests added: tests/platform/test_health_contract.py (11 — liveness-vs-readiness split, error/timeout reporting, version fields, metrics exposition, enumeration incl. the failing fixture and the repo-wide binding test).
- Result: 62 passed on branch; make check green; intake_platform coverage 100 % branch vs floor 85.
- Invariants touched and still passing: 15 (now structurally enforced), 8.
- Decisions / 00 rows: none — implements 10 §6 as specified.
- Blocked on: nothing.
- Next: INT-011 OTel + PII redaction processor.
- LOOP_STATUS: CONTINUE

### 2026-08-27T21:20:00+03:00 · INT-011 · done
- Goal: shared OTel setup + the two-layer PII redaction (app JSON formatter + collector config) with propagated ids.
- Plan: failing tests first (collection error), then redaction.py (TCKN checksum, 05x phone, TR IBAN), otel.py (bind_log_context with boundary-hashed session id, JsonLogFormatter with attribute allow-list, local-only setup_otel), otel-collector.yaml whose statements the test extracts and runs on fixture logs.
- Tests added: tests/platform/test_redaction.py (10 — checksum positive/negative, per-pattern masking, fixture-log sweeps app-side AND from the committed collector YAML, context propagation with raw-session-never-logs assertion, allow-list drop, local-only default).
- Result: 72 passed on branch; make check green; mypy strict with a scoped override for the optional OTLP exporter import.
- Invariants touched and still passing: 6 (first mechanical layers), 8, 15.
- Decisions / 00 rows: none — implements 10 §6/07 §6 as specified; free-text name NER deliberately deferred to INT-015 (stated in evidence).
- Blocked on: nothing.
- Next: INT-012 security middleware (headers, rate limiter, idempotency keys).
- LOOP_STATUS: CONTINUE

### 2026-08-27T21:55:00+03:00 · INT-012 · done
- Goal: the API security middleware baseline — headers, Redis token-bucket limiter (user/ip/tenant), idempotency keys for POSTs.
- Plan: failing tests first (collection error), then the hook-protected security package: pure-ASGI headers middleware, atomic-Lua token bucket with injected clock, idempotency middleware with replay/409-in-flight/422-body-mismatch/retryable-failure semantics.
- Tests added: tests/platform/test_rate_limit.py (4 — capacity, refill, isolation, ceiling), tests/platform/test_idempotency.py (6 — headers quartet, replay-without-reexecution, key isolation, body-mismatch 422, passthroughs).
- Result: 82 passed on branch; make check green; mypy --strict clean; coverage 89.97 % vs floor 85.
- Invariants touched and still passing: 14 (baseline layer), 6, 8, 15.
- Decisions / 00 rows: none — implements 10 §2 as specified. Protected-path initial authorship recorded in evidence.
- Blocked on: nothing.
- Next: INT-017 (OpenBao dev server + policies) or INT-018 (egress proxy) — both now the only remaining unblocked deps for the data chain.
- LOOP_STATUS: CONTINUE

### 2026-08-27T22:50:00+03:00 · INT-015 · done (pending release-asset upload for CI)
- Goal: the de-identification boundary — TCKN/phone/IBAN/email recognizers, Turkish date shifting, names+addresses NER, leak-rate gates in CI, egress fail-closed contract.
- Plan: red tests; offset-exact authored corpus + two vendored synthetic corpora (Apache-2.0 + CC-BY-4.0 held-out sample, attributed, pinned); pattern tier in intake_platform.deid; licence audit of off-the-shelf TR NER (all failed the raw-blob gate) → trained our own DistilBERTurk head on the H200 inside /data/intake under the resource guard; artefact with provenance.json + SHA256SUMS distributed as a pinned repo release; make deid-model + CI cache.
- Tests added: tests/security/test_deid_leak_rate.py (9 — leak gate <0.1 %, over-masking guard, vendored spaced-format corpus, date-shift determinism/bounds/intervals, egress fails closed), tests/security/test_deid_ner.py (4 — provenance, egress opens with model, ≥0.97 held-out recall gate, tier interplay).
- Result: 95 passed; make check green; mypy strict clean. Model: token recall ≥0.9994 all classes on synthetic held-out (internal measurement, D16; Turkish clinical eval set stays HB-C10).
- Invariants touched and still passing: 6, 8, 14, 15.
- Decisions / 00 rows: engine implements the acceptance's recognizer set without the Presidio dependency chain — stated inline in issues.yaml + evidence for reviewer; own-trained NER per the D14 philosophy (we hold the design history).
- Blocked on: nothing (release upload finishing; PR merges after CI fetches the artefact).
- Next: INT-017 OpenBao dev server + policies.
- LOOP_STATUS: CONTINUE

### 2026-08-27T23:59:00+03:00 · INT-017 · done
- Goal: OpenBao in the dev tier — fail-closed secrets boot, per-service policies, dynamic Postgres creds at 24h TTL; the docker tier gets its own CI lane.
- Plan: red tests; SecretsProvider (prod refuses missing/dev-shaped/unreachable backends at boot; dev reads only the .env pointer); compose openbao service; setup script (database engine + 3 roles @24h + 3 least-privilege policies); integration marker + make check-integration + its CI job (05 §3).
- Tests added: tests/security/test_openbao_wiring.py — 5 unit (fail-closed trio, dev defaults, env-template pin) + 2 integration (KV roundtrip, dynamic creds with lease==86400 proven by a real psycopg connect; policy presence).
- Result: unit lane 100 passed; integration lane 2 passed locally against real containers. Two real defects caught by the failing tests (heredoc-swallowing exec, LIST verb).
- Invariants touched and still passing: 13 (now mechanical), 14, 15.
- Decisions / 00 rows: none — implements 10 §2 as specified.
- Blocked on: nothing.
- Next: INT-013 tokenization (deps now satisfied) or INT-018 egress proxy — file order says INT-013.
- LOOP_STATUS: CONTINUE

### 2026-08-28T00:40:00+03:00 · INT-013 · done
- Goal: identifiers never in clear — keyed pseudonyms for joins, Transit-encrypted identity vault behind a dedicated pg role, pseudonym[:8] in logs, rotation semantics, and the raw-column grep gate.
- Plan: red tests; Tokenizer (HMAC-SHA-256, key ids, normalisation, log_ref) + IdentityVault (Transit encrypt/decrypt via the secrets client, psycopg store/fetch); identity_vault.sql with REVOKEs; setup script gains transit + vault DDL; grep gate over all committed SQL.
- Tests added: tests/security/test_tokenization_roundtrip.py — 8 unit (keyed determinism, normalisation, irreversibility, log_ref, rotation old-key linkage, unknown-key refusal, grep gate, DDL shape) + 1 integration (roundtrip at rest + app-role InsufficientPrivilege).
- Result: 108 unit green; integration lane 3/3; make check green.
- Invariants touched and still passing: 13, 6, 14, 15.
- Decisions / 00 rows: none — implements 10 §2; per-tenant DEK/rewrap engine deliberately left to INT-014 (stated in evidence).
- Blocked on: nothing.
- Next: INT-014 envelope encryption (Transit) + rotation + crypto-shredding.
- LOOP_STATUS: CONTINUE

### 2026-08-28T01:30:00+03:00 · INT-014 · done
- Goal: field-level envelope encryption — per-tenant DEKs wrapped by Transit, file-KEK for the unit lane, rewrap rotation, crypto-shred as the KVKK-7 hard delete.
- Plan: red tests; EnvelopeCipher + EncryptedField (pack/unpack) + KekProvider protocol with FileKekProvider (unit) and TransitKekProvider (integration + mock-transport unit coverage of the HTTP contract).
- Tests added: tests/security/test_envelope_encryption.py (7 unit + 1 integration) + test_envelope_transit_unit.py (4 — version parsing, rotation tracking, destroy two-step, missing-key→shred mapping).
- Result: 119 unit green, make check GREEN; integration lane 4/4 incl. live Transit destroy.
- Invariants touched and still passing: 14, 13, 6, 15; coverage floor held.
- Decisions / 00 rows: none — implements 10 §2 as specified.
- Blocked on: nothing.
- Next: INT-016 audit chain (deps INT-014 now satisfied) per file order.
- LOOP_STATUS: CONTINUE

### 2026-08-28T03:10:00+03:00 · INT-130 · in-review
- Goal: the Expo app shell — SDK 57, nav exactly per 02 §4 (incl. me/learned), tr-first typed i18n, warm-paper theme with the RED discipline, dynamic type to 200 %, synthetic dev accounts.
- Plan: create-expo-app scaffold pruned; pure-TS design system (theme/i18n/session rules) so the binding rules are unit-testable in node; native tabs with the consent-gated wellbeing trigger; nav.spec pins the route tree bidirectionally.
- Tests added: apps/mobile e2e/nav.spec.ts (25) + theme/i18n/session/accounts unit (22); planted-mutation red run on the consent gate (2 fail) recorded in docs/evidence/INT-130.md.
- Result: typecheck + expo lint + 47 vitest green; make check-ts GREEN; no_placeholders OK. Design decisions + Mobbin references in docs/design/mobile-ui.md.
- Invariants touched and still passing: 5 (tr-first), 17 (zero placeholders), 18 (patient-facing strings [REVIEW]-marked, none signed).
- Decisions / 00 rows: teal accent + warm paper (not state-blue, not clinical white); wellbeing hidden-not-disabled; session memory-only until consent design lands.
- Blocked on: nothing for the shell; orb surface waits on INT-132.
- Next: demo model serving on the team GPU box (vLLM Qwen3.5-9B fp8 capped + faster-whisper), then INT-016 audit chain.
- LOOP_STATUS: CONTINUE

### 2026-08-28T04:30:00+03:00 · demo-models + security-review · done
- Goal: working demo model stack on the team GPU box (owner directive) + fold the two agent reviews into the tracker.
- Result: Qwen3.5-9B @c202236 serving on loopback :8801 (transformers bf16, ~26% of the slice, guarded, Turkish smoke green); whisper-tr-medical @0e74ec8 ct2/fp16 GPU transcription word-perfect — with the INVERTED task-token finding (task="translate" ⇒ Turkish; the default silently yields an English translation) recorded in the runbook; Freya-TTS deferred (needs commit-pinned git install — owner approval) with its licence upgraded to "README asserts Apache-2.0" pending blob verification.
- Platform facts learned: pod driver is CUDA 12.8, nvidia-smi blocked; torch must be 2.11.0+cu128; every current vLLM wheel is CUDA-13-built and cannot run here — vLLM stays the plan for target hardware (INT-095/097), transformers is the demo backend.
- Reviews: clinical pre-review posted to PR #185 (headline: KIRMIZI_K2 acuity on the crisis rule is an unsurfaced clinical decision; TR-EK4 snapshot missing; LT-01-N tense confound; intake/red_flags NOT covered — physician still required). Security review filed as issue #195; the three HIGHs are now INT-176 (idempotency principal scoping), INT-177 (rate-limiter Redis TIME), INT-178 (trace/metric redaction) — backlog count consciously 175→178.
- INT-130 merged (PR #194) — status flipped to done.
- Invariants: 17, 19 (licence findings recorded, not waved through), 8 (floors untouched).
- Blocked on: owner — Freya-TTS pinned-install approval; physician review of #185; whisper-tr/Freya LICENSE blobs.
- Next: INT-016 audit chain, then INT-018/019; INT-176..178 queued P0.
- LOOP_STATUS: CONTINUE

### 2026-08-28T05:40:00+03:00 · INT-179 · doing→in PR
- Goal: fixture-backed flow shells (owner directive): typed-intake chips + review-and-send + status ladder + richer demo accounts; Expo QR handed to owner.
- Plan: spec first (e2e/flows.spec.ts — genuine red: modules absent), then pure lib (questions/note reducer) + three screens under visits/[visitId]/.
- Tests added: flows.spec 13 (routes, fixture shape, note builder, scope rules, send-never-blocked, source facts); register sweep fixed sen-form imperatives in the catalog.
- Result: 62 mobile tests green; typecheck + expo lint clean. Backlog consciously 178→179 (INT-179 filed with reason).
- Invariants: 5, 17 (dropped RN placeholder prop rather than allow-listing the token), 18.
- Blocked on: nothing.
- Next: INT-176/177 security fixes, then INT-016.
- LOOP_STATUS: CONTINUE

### 2026-08-28T06:50:00+03:00 · INT-176 + INT-177 + INT-178 · done
- Goal: close the three HIGHs from the platform security review (#195) as first-class TDD iterations.
- Result: INT-176 (PR #203) — idempotency keys sha256-scoped by (tenant, subject, method, path, key) via a required principal_fn; 60s in-flight TTL vs 24h record TTL; base64 + 256KiB-capped stored bodies with an honest 409 for oversize replays. INT-177 (PR #202) — rate-limiter refill moved to redis.call('TIME') inside the Lua script; negative elapsed clamps (skew immunity + no starvation proven without injected clocks). INT-178 (this PR) — RedactingSpanExporter wraps every attached exporter (name/attributes/events/status all pass redact_text; record_exception covered) and the collector's transform/redact now runs in traces AND metrics pipelines with span/spanevent/datapoint statements.
- Tests: +7 rate-limit/idempotency-scoping (202/203) and +4 trace-redaction; suite at 130 py green; mypy --strict clean throughout.
- Invariants: 6, 14; coverage floor held; no gate touched.
- Blocked on: nothing; the review's mediums remain listed on #195 for the issues that own their files.
- Next: INT-016 audit chain (deps satisfied), then INT-018 egress proxy.
- LOOP_STATUS: CONTINUE

### 2026-08-28T07:50:00+03:00 · INT-193 · done (+ INT-016 core in PR)
- Goal: owner directives — Oura/Liquid-Glass premium pass, functional demo (add-visit, language switching), standardized clinician brief, full iOS-simulator smoke of every screen and button; roadmap continued in parallel.
- Result: serif heroes + deep Oura dark + GlassCard/teal rail live; add-visit writes session state end-to-end; tr/en switch remounts the tree (verified: whole UI incl. tab labels); brief restructured CC→HPI→Meds with [REVIEW] provenance line and stable section codes for INT-084. Smoke run walked both personas through all five tabs, intake, review, scopes, send, ladder, records, consents — and caught two real device bugs unit tests could not see (missing per-tab Stack under native tabs swallowed cross-tab pushes; module-level t() needed a locale-keyed root). 67 vitest + typecheck + lint + make check green.
- Parallel roadmap: INT-016 audit-chain core built by subagent (23 tests, audit.py 100% branch coverage, suite 153 passed) — PR #205; INT-016 stays doing pending the integration slice.
- Phone QR: LAN failed for the owner; tunnel (exp.direct) QR delivered instead + Expo Go update guidance.
- Invariants: 1 (no triage faked in UI), 5, 17, 18; backlog consciously 179→180 (INT-193 filed with reason).
- Blocked on: physician (#185); owner: Freya pin approval, licence blobs.
- Next: merge #205 and this PR; then INT-018 egress proxy.
- LOOP_STATUS: CONTINUE

### 2026-08-28T09:00:00+03:00 · INT-194 · done (+ INT-021 core in PR)
- Goal: owner directives — "bilgiler düzenlenemiyor" (editable review), "ses kısmı çalışmıyor" (working voice), "not department-based / too short" (branch packs).
- Result: review pencils reopen questions prefilled (single-select edits return straight to the review); __DEV__ voice pill → own whisper-tr ASR daemon on the GPU box over the Mac's SSH forward (curl-proven word-perfect Turkish; in-sim plumbing verified; recording deleted after upload — invariant 3 posture); department packs: cardio/internal 6 steps (character/trigger/associated), neuro (onset/severity-in-words/assoc), KBB (side/assoc), fallback core — all feeding labelled HPI lines in the clinician brief. Unicode pack-matching bug caught by tests (combining-mark regex vs tr-TR lowercasing).
- Parallel roadmap: INT-021 SLO stack built by subagent (branch int-21-slo: schema+generator, prometheus rules round-trip-tested, dashboard as code, runbook, make slo-report; 162 py tests, coverage 88.17%) — PR next; INT-021 stays doing (live stack lands with INT-023).
- Invariants: 3 (posture documented), 5, 17, 22 (severity words, no numerals); backlog consciously 180→181.
- Blocked on: owner — Freya-TTS pinned install approval (the "robotic" voice heard was macOS say, not our TTS); physician #185.
- Next: merge this + int-21-slo + #205; then INT-018.
- LOOP_STATUS: CONTINUE

### 2026-08-28T02:20:00+03:00 · merge wave: INT-016/018/021 cores + INT-194 · done (parallel-agent iteration)
- Fleet (≤3 concurrent per CLAUDE.md): INT-018 egress policy library (PR #214), INT-020 threat model + Sec-Row gate (PR #217, in CI — the new gate's first catch was the coordinator's own wrong Sec-Row line), INT-021 SLO stack (PR #212), INT-016 audit chain core (PR #205), INT-194 flows/voice/packs (PR #210), all merged with local full-green gates during a GitHub Actions event outage; every late-arriving CI run subsequently confirmed GREEN.
- TTS lane live on the team box: FreyaTTS-small @146d36c1 (code Apache-2.0 blob-verified), normaliser disabled + digit rejection (invariant 22), VRAM pre-check, supervised; smoke wav delivered. Findings: Freya weights + VoxCPM2 weights lack licence blobs (licence-auditor queue); shared tmux session leaks another tenant's HF_TOKEN (owner to be informed).
- Design pass 3 running as a dedicated agent (BlurView glass, Kicker/Hairline/Guidance patterns, Fraunces display face) live in the simulator.
- Next: merge #217; INT-019 security CI + INT-022 probe registry agents in flight; then INT-023 observability deploy.
- LOOP_STATUS: CONTINUE

### 2026-08-28T03:20:00+03:00 · INT-195 · done
- Goal: dedicated design-agent pass to the Oura register ("more liquid glass; fonting and framing differ" — owner, with a side-by-side).
- Result: real BlurView glass fallback + GlassBar floating CTAs (intake/review), Kicker/Hairline/GuidanceBlock anatomy across all seven screens, borderless tonal dark cards, Fraunces display leading 1.2 pinned, guidance-block empty states in product copy (tr+en). The pass FOUND and fixed a real AA regression (primary/primarySoft 4.41→4.63) and pinned the pair into the contrast suite. 72/72 green, no invariant weakened; verified by the agent in dark+light with its own screenshots.
- Invariants: 5, 17, 18 (product copy only), 02 §5.2 motion budget kept (static gradients only).
- Next: merge; INT-019 + INT-022 agents still building.
- LOOP_STATUS: CONTINUE

### 2026-08-28T04:30:00+03:00 · merge wave: INT-022/INT-023/INT-030 + INT-034 built · done
- Merged with CI validated on main: #221 INT-022 (probe registry + release gate, honest 6-gap exit 1), #225 INT-023 (observability compose profile, 13 services, `make obs`), #227 INT-030 (postgres schema + alembic + tenant RLS live-proven under FORCE RLS, SqlAlchemyAuditStore, 67/67 inventory annotations, db 100% coverage). #223's branch kept dropping CI events even after fresh pushes — replaced by #228 (identical commits, fresh ref int-19-secgates); INT-019 stays doing until it lands.
- INT-034 delivered by subagent on int-34-minio-docs (7d2fcbd): WORM audit bucket with COMPLIANCE retention proven against live MinIO (version delete refused server-side), signed-URL contract suite, quarantine→clean AV hook failing closed (DevNullScanner only behind INTAKE_DEV_ALLOW_UNSCANNED=explicit-yes), documents.py 100% stmt+branch, suite 343 py green at 91.96%. PR next.
- Fleet: design pass 4 (js-tabs + FloatingTabBar pill, rail yields on intake/review) and voice-extract server (/extract on :8804, schema-bound candidates, injection probe) in flight.
- Invariants: 4, 13, 14, 15, 18; no gate touched; backlog flips INT-022/023/030→done, INT-019/034→doing.
- Blocked on: physician (#185); owner: licence blobs (whisper-tr, Freya weights, VoxCPM2 weights).
- Next: merge #228; INT-034 PR; wire voice-extract app half after design pass lands.
- LOOP_STATUS: CONTINUE

### 2026-08-28T05:10:00+03:00 · INT-196 · done
- Goal: owner directive round 4 — "still ui and fonts n shapes not close enough to oura ui … simulate and copy the oura style as much as possible" (dedicated design agent, Mobbin-measured).
- Result: FloatingTabBar pill on expo-router/js-tabs (native tabs superseded — owner decision recorded in-file + docs/design/mobile-ui.md; the red that forced it: @react-navigation/bottom-tabs is not installed under Expo Router 57). Rail unmounts on intake/review; GlassBar owns the physical bottom; wellbeing route UNREGISTERED via Tabs.Protected when consent is off (verified live). Measured register deltas: card radius 24 / hero 32, Card padding 24, scrim 0.55, unboxed kickers, chevrons on tappable cards, dark filled chips, serif record titles, welcome quiet-secondary CTA, Inter (OFL) body with explicit weight map, Newsreader display kept. No palette hex changed → pinned AA suite untouched. 74/74 vitest + typecheck green; full live walkthrough on the simulator.
- Invariants: 5 (no key changes), 17, 18 (none touched), motion budget 120 ms fades kept; backlog consciously 182→183 (INT-196 filed with reason).
- Fleet: dept-packs agent (INT-198 scope) building; /extract server live on :8804 (schema-bound candidates, injection probe held); INT-034 PR #230 open.
- Blocked on: physician (#185); owner: licence blobs.
- Next: merge this + #230 + #228; API slice (INT-197) and voice-first intake (INT-199) agents.
- LOOP_STATUS: CONTINUE

### 2026-08-28T05:45:00+03:00 · INT-034 · done (PR #230) + INT-196 merged (PR #232)
- INT-034 merged CI-green after two coordinator fixes: check-integration now boots minio (the compose service existed; the --wait list did not include it) and a setup-uv manifest-fetch flake re-run. WORM retention proven against live MinIO in CI as well as locally.
- INT-196 (design pass 4) merged CI-green after the evidence gate correctly demanded a make check record — ran the full local fan-out (exit 0) and recorded it rather than paraphrasing.
- INT-019: #223 and #228 refs both drop CI events; work rebased onto current main (fresh shas, .PHONY union resolved, 46/46 tests/ci green post-rebase) and reopened as #233.
- Fleet 3/3: dept packs (INT-198 scope), voice-first intake (INT-199 scope), API slice (INT-197 scope).
- LOOP_STATUS: CONTINUE

### 2026-08-28T06:40:00+03:00 · INT-198 · done
- Goal: owner directive — "questions asked in previsit per department is not complete or correct … too short and not department based".
- Result: 10 department packs at full OLDCARTS depth (Kardiyoloji/İç Hastalıkları 9, Nöroloji 9, KBB 8, Ortopedi 9, Dermatoloji 9, Göğüs 9, Kadın-Doğum 8, Üroloji 8, Göz 9, Gastro 9 steps), folded-ASCII regex resolution tested through Turkish diacritic spellings, allQuestions as canonical anamnesis order with every pack a pinned subsequence (HPI lines follow interview order), no numerals in any label (invariant 22 pinned), ~140 tr keys with key-for-key en mirror. note.ts unchanged — ordering authority lives in allQuestions. 102 mobile tests green; make check exit 0 after main merge.
- Clinical-reviewer flags recorded in evidence (hemoptysis omission, ischemic radiation descriptors, neutral gyn/weight-loss options) — packs carry no red-flag logic by design (invariant 1).
- Invariants: 1, 5, 17, 22; backlog consciously 183→184.
- LOOP_STATUS: CONTINUE

### 2026-08-28T07:20:00+03:00 · INT-199 · done
- Goal: owner directive — "voice part and voice parsing is at the end and so minimal … mostly is text based" — voice becomes the FIRST-CLASS intake entry.
- Result: fresh intake with voice consent opens with "Sesli anlatın": live ASR probe gate (fail → silent manual fallback) → free-speech recording → whisper transcript (invariant-3 file deletion, now also on the unreachable-base path — strictly tighter) → dev /extract with the visit's pack → client-re-validated candidates → one-question-per-turn confirm flow with the patient's verbatim words as provenance ("Söylediğiniz: …"); saved answers beat suggestions; every failure lands in the exact manual flow. 44 new tests; after INT-198 merge three stale cardio-pack expectations updated; 146 mobile tests + make check green.
- Invariants: 1 (candidates are suggestions, never triage), 3, 5, 17; backlog consciously 184→185.
- LOOP_STATUS: CONTINUE

### 2026-08-28T08:00:00+03:00 · INT-208 · done
- Goal: owner directive — "the app should be ready to use with if possible apple and google health connectors".
- Result: typed HealthConnector layer with a test-pinned availability matrix (Expo Go → needs_dev_build calm guidance; dynamic-import failure → needs_dev_build; iOS HealthKit unavailable → platform_unsupported; refused auth → permission_denied); HealthKit + Health Connect adapters behind dynamic imports (Expo Go never crashes); app.json config-plugin wiring with Turkish NSHealthShareUsageDescription ready for the dev-client simulator build; consent-gated "Sağlık verileri" on Profilim (health scope, default off); steps/resting-HR/sleep formatted useGrouping:false with number+unit as one non-breaking atom; patient-confirmed attach into the note draft as a labelled device_health section (scope-off honored, sent notes immutable). NO server call/analytics/persistence for health data — persisting a new personal-data category stays with the human. Licences from blobs: react-native-health-connect MIT (in-package); @kingstinct/react-native-healthkit MIT (upstream blob; absent in-package — recorded).
- Note: filed as INT-208 — INT-200/201 turned out to be blueprint E13-infra ids; coordinator renumbered before PR (id-collision caught by make check duplicate-ids assertion).
- Invariants: 2 (numbers shown never interpreted), 5, 6, 17, 18 (no new persisted fields); backlog consciously 185→186.
- LOOP_STATUS: CONTINUE

### 2026-08-28T09:30:00+03:00 · INT-197 · done
- Goal: owner directive — "deneme hesapları … users should be really able to use and connect and upload their files or use this app in real".
- Result: services/api dev-tier slice — dev-bearer for exactly two synthetic accounts (fail-closed 503 without env tokens, X-Intake-Auth-Tier: dev, real OIDC stays INT-131); visits as sessions rows + visit.* slots (zero schema changes); notes envelope-encrypted at rest with status derived from live shares, share = consent-checked TTL row with only scoped-on sections; documents presign/list/download over INT-034 plus a content-ingest endpoint running the INT-034 pipeline (409 until scanned, AV posture unweakened); everything audited on one hash chain; invariant-15 endpoints via shared helpers. 490 unit tests, api 98% coverage, 5 live RLS+MinIO integration tests; make check exit 0.
- Filed INT-228 (todo): real Tokenizer pseudonyms exceed the document-store key-segment bound — the INT-197 workaround (row UUID as segment) must be replaced by a test-pinned integration.
- Invariants: 4, 6, 8, 14, 15, 18; backlog consciously 186→188 (INT-197 done + INT-228 finding).
- LOOP_STATUS: CONTINUE

### 2026-08-28T10:15:00+03:00 · INT-197 + INT-120 merged (PRs #240, #243)
- INT-197 dev-tier API slice merged CI-green (one gates rerun: the sub-issue label had failed silently, leaving a dangling Closes reference — recreated and re-triggered). INT-120 upload pipeline merged CI-green right after; the two branches' Makefile edits auto-merged cleanly.
- The demo tier now has the full real path: dev-bearer accounts → visits/notes over RLS with envelope encryption and consent-checked TTL shares → presigned uploads → ClamAV scan (EICAR-proven) → clean promotion → presigned downloads, all on one audit hash chain.
- INT-120 flip to done here; INT-197 was filed done in its own PR. OCR engine + sandbox tech need an ADR (builder refused to embed a parser in-process — correct per files/10).
- Fleet 3/3: INT-025 metrics catalogue, INT-031 clinical schemas, INT-036 retention engine. Design pass 5 (INT-209) packaging next.
- LOOP_STATUS: CONTINUE

### 2026-08-28T10:45:00+03:00 · INT-209 · done
- Goal: owner directive, fifth repetition — "still ui and fonts n shapes not close enough to oura ui … copy the oura style as much as possible" (dedicated design agent, measurement-first).
- Result: the biggest structural gap closed — Bugün now leads with a numeric focal point (pure-View PrepGauge semicircle, 56pt serif completion numeral via Intl.NumberFormat percent, fontScale-safe); Profilim/Kayıtlarım moved from card stacks to Oura table anatomy (ListGroup/ListRow, 56pt rows, icon wells, inset hairlines, chevrons, headers outside groups); pushed screens gained stack headers with back affordances (a real navigation gap); display serif 600→500; accent budget cut to ~one teal moment per screen (gauge in ink); surfaceRaised tokens added with the AA suite extended — zero existing hexes changed. 181/181 tests + make check green with INT-197/198/199/208/120 all merged in.
- Found and frozen honestly: light success/successSoft measures 4.35:1 (shipped since INT-130) — needs a dedicated palette iteration, flagged in docs/design/mobile-ui.md.
- Invariants: 5 (keys added only), 17, 18; motion budget kept; backlog consciously 188→189.
- LOOP_STATUS: CONTINUE

### 2026-08-28T11:45:00+03:00 · INT-025 · done (PR #247); INT-031/INT-036 in PR
- INT-025 merged CI-green: all 135 metric ids files/08 §4 names catalogued (planned until their services exist), 26 spec targets pinned, the spec section parsed by the test itself, enforcement proved-then-reverted per acceptance. Coordinator merge finds: INT-120's entry used the _total exposition form vs its code literal (gate right, entry aligned); the live-emitted check passed on pytest collection-order luck — emitter imports now explicit and self-correcting.
- INT-031 clinical-schemas in PR #249: nine blueprint-cited models with invariants 1/11/12/21 enforced in the type system, five event schemas (audit.v1 asserted against the INT-016 dataclass), deterministic committed codegen with drift gates; refused-fields list recorded instead of invention; sec_row clinical-core linked (inv 16).
- INT-036 retention engine in PR #251: files/06 §3 row-cited policy classes, DEST-2017 6-month floor read from the hash chain, 3-year indestructible destruction log, two draft_needs_source classes refusing destruction pending the human (consumer-tenant consent duration; research extracts / HB-L1).
- Simulator dev-client build blocked on host Xcode: iOS 26.1 platform not installed and only 14 GB disk free — owner informed with the exact fix; Expo Go lane unaffected.
- LOOP_STATUS: CONTINUE

### 2026-08-28T12:20:00+03:00 · INT-031 + INT-036 · done (PRs #249, #251)
- INT-031 clinical-schemas merged CI-green: nine blueprint-cited pydantic models with invariants 1/11/12/21 in the type system (LLM triage candidates capped YELLOW_REVIEW type-level; RED requires register+location with no default), five versioned event schemas (audit.v1 asserted against the INT-016 dataclass), deterministic committed codegen with byte-compare drift gates; refused-fields list instead of invention; workspace unions with INT-197 resolved (pyproject members/mypy, Makefile check-py, uv.lock regenerated).
- INT-036 retention engine merged CI-green: files/06 §3 row-cited policy classes; DEST-2017 6-month floor read from the engine's own hash-chain entries; 3-year destruction log indestructible three separate ways; raw_audio never_written + lane_windows memory_only pinned; two draft_needs_source classes REFUSE destruction pending the human (consumer-tenant consent duration; research extracts per ethics protocol — HB-L1); 44 time-travel tests, zero sleeps.
- Fleet 3/3 (wave 3): INT-038 consent service, INT-090 LiveKit dev voice infra, INT-131 real onboarding/auth (owner's create-accounts directive).
- LOOP_STATUS: CONTINUE

### 2026-08-28T13:00:00+03:00 · INT-090 · done (PR #254)
- LiveKit dev tier merged CI-green: HS256 room tokens with the exact minimal grant surface (canPublishData explicitly false — livekit defaults absence to true; mic source only; TTL ≤600s), live-proven against the pinned v1.13.6 server (signature accepted, ListRooms permissions-denied, corrupted signature rejected). Audio-retention guard in three layers under INT-036's policy guard; recording made structurally impossible (no redis bus = egress workers cannot register). Apache-2.0 from the raw blob at the tag; zero new deps; room_tokens.py 100% stmt+branch.
- Fleet: INT-038 consent service + INT-131 onboarding/auth still building.
- LOOP_STATUS: CONTINUE

### 2026-08-28T13:40:00+03:00 · INT-038 · done (PR #256)
- Consent service merged CI-green: purpose registry verbatim from files/06 §2 (lane:acoustic rejected by name — ICF), text_hash bound to exact docs/legal bytes with fail-closed loading, withdrawal cascade synchronous in-transaction with a 30s-grid sweep bounding the crash window at 55s (schedule-property + fake-clock proofs), route-table scan pinning unguarded_data_routes == [] across the lazy included routers, structural unbundling pin. One evaluator serves guard and record checks so staleness cannot fork.
- Awaiting-human recorded: docs/legal/consents texts do not exist (owner + counsel; blockers row) — every grant fails closed until they land; no consent copy was written by the machine.
- Fleet: INT-131 onboarding/auth still building (last of wave 3).
- LOOP_STATUS: CONTINUE
