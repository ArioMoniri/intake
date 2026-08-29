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

### 2026-08-28T14:30:00+03:00 · INT-131 · done (PR #258) — wave 3 closed
- Onboarding/auth merged CI-green: OTP per files/10 §2 (all windows clock-injected), tokens as hashed opaque randoms bound to the client key thumbprint, DPoP with single-use jti + ath, refresh rotation where replay revokes the family (audited) but wrong-key presentation refuses without revocation; pseudonym-only patient rows; X-Intake-Auth-Tier honest (otp vs dev, dev accounts pinned working). Mobile onboarding in the pass-5 register with biometric gate/SecureStore/FLAG_SECURE/jailbreak-warn; cert-pinning config plugin wired for the next dev build.
- The INT-038 route scan refused the new auth routes as designed; resolved with an explicit pre_auth() declaration the scan accepts only under /v1/auth (exact-list + negative-control pins) — no silent routes, no borrowed exemptions.
- Awaiting-human (recorded): SMS vendor, App Attest/Play Integrity keys (HB-A3), pin certs, hardware-backed DPoP key module, consent texts (INT-210), #233 workflow command, Xcode iOS platform (disk-gated).
- Session tally: 16 issues landed end-to-end this session.
- LOOP_STATUS: CONTINUE

### 2026-08-28T16:45:00+03:00 · demo lane live-verified + INT-035/INT-040 merged (PRs #262, #264, #260)
- Owner's "still shows as demo" complaint root-caused live in the simulator: a STALE Metro from an outdated branch held port 8081 (killed; fresh tunnel on current main), all four model-lane SSH forwards were down (re-attached: LLM/ASR/TTS/extract healthy), and the API was not running (now up: migrations at head, OpenBao transit, OTP tier enabled, dev gates explicit-yes).
- Live-proven on a REAL OTP account end-to-end: phone → challenge → attested OTP → DPoP tokens → Bugün with the pass-5 PrepGauge and correct zero-consent empty state. A device-found navigation race (verify success bounced back to the phone screen) fixed as PR #260 and merged. Server auth flow independently proven by a full python replication (challenge/attestation/DPoP/verify → 200 + consent_required on data routes, exactly right for a zero-consent account).
- Voice lane: intake opens with Sesli anlatın on the real account; synthesized Turkish patient speech (own TTS) recorded through the mic; transcription + the honest extracting state ran; the exact audio proven through whisper → /extract in 11.7s (pain/days/pressure/exertion/sweating/metoprolol with verbatim quotes, onset honestly dropped). One remaining app-side prefill-render gap has a dedicated debug agent (int-199-fix-prefill) with the full repro.
- INT-035 event bus merged (#262): at-least-once delivery with exactly-once side effects over the INT-176 idempotency scheme, group-local retry streams (multi-group correctness), DLQ reason codes; fakeredis covered everything (finding: fakeredis miscounts XINFO lag — counted directly). Pre-existing wall-clock flake found in test_otp_abuse near top-of-hour — follow-up owed.
- INT-040 Protocol DSL merged (#264): the invariant-1/7/10/21/22 mechanism with 28 golden fixtures and 99.89% branch coverage; zero clinical content; instruments licence registry fails closed (C-SSRS/WHO-5 BLOCKED per HB-L2/L3).
- INT-132 consent UI in PR #266. Extract server on the box shows 4 external SIGTERM restarts (self-heals ≤60s; box-owner question).
- LOOP_STATUS: CONTINUE

### 2026-08-28T17:00:00+03:00 · INT-132 · done (PR #266) — wave 4 closed
- Consent UI merged CI-green: layered İzinleriniz in the 06 §2 structure (core as info never a switch; lane sub-toggles with the affect/linguistic asymmetry; learning as honest default-on opt-outs; share deliberately absent as anti-bundling; lane:acoustic refused by name); fail-closed everywhere the legal texts are missing (INT-210), with e2e pins that no legal copy is bundled in src/. First-run after OTP verify routes through consent disclosure; coexists with the #260 nav-race guard.
- Server gap recorded by the builder: services/api lacks patient-facing consent routes (GET /v1/consents, grant/withdraw) — needs its own issue next wave.
- Wave 4 closed: INT-040, INT-035, INT-132 + the #260 device-found fix. Session total: 21 issues landed end-to-end.
- LOOP_STATUS: CONTINUE

### 2026-08-28T17:40:00+03:00 · voice-lane prefill fix merged (PR #268) + daemon hardening
- Device-found and root-caused: the extract daemon's warm-up window answers /health 200 while /extract returns a valid-but-empty envelope, and the reducer recorded that as a SUCCESSFUL voice run — the patient landed in manual-looking steps with no notice. Client fix at the state-machine seam (empty prefill = failed:true, honest notice) with the live daemon envelope pinned verbatim as a regression fixture (8/9 questions prefill with provenance). Server hardened in tandem on the box: /extract now answers 503 extract_unavailable while the LLM upstream is unreachable, never 200-empty (extract_server.py patched, supervisor-restarted, health re-verified).
- The wire contract itself was proven innocent both directions (byte-exact app request replayed → all eight candidates with verbatim quotes).
- Also flagged by the debugger: the pinned deid artefact is per-checkout (make deid-model fetches it) and a cross-test state bleed makes test_otp_abuse's per-phone-limit flake under the full suite near top-of-hour — follow-up owed.
- LOOP_STATUS: CONTINUE

### 2026-08-28T17:55:00+03:00 · INT-232 · done (PR #270)
- Patient-facing consent routes merged CI-green, seam-faithful to the merged INT-132 client (seam won over the sketch, divergences reported): snapshot with the closed six-value reason list and fail-closed empty texts; grant re-checks the bound row after the fact so a mid-flight text move rolls back; withdraw cascades via INT-038. consent_management scan declaration accepted only under /v1/consents at a path-segment boundary — stricter than pre_auth, lookalike-prefix pinned.
- Records upload UI (INT-229 label) delivered by its builder and queued for PR: real picker → sha256 → API ingest (presigned MinIO URLs are server-loopback, never fetched from the device) → honest Taranıyor/Hazır/Reddedildi states → download via browser; dev-tier accounts keep the synthetic list with no fake upload affordance, pinned.
- LOOP_STATUS: CONTINUE

### 2026-08-28T18:40:00+03:00 · INT-080 · done (PR #276) + voice-lane hardening merged (#274)
- Deterministic triage engine merged CI-green: Kleene three-valued when-grammar with per-construct blueprint citations and load-time refusal of anything undefined; Decimal-exact comparisons; temporal guards Unknown on undated anchors; contested slots per-world OR-joined; monotonic merge proven by exhaustive enumeration (32 subsets, 32×32 pairs, 120 permutations byte-identical); LLM candidates capped type-level (Literal YELLOW_REVIEW, separate field, identity-asserted passthrough); action scripts returned as the rule's own frozen objects (is-asserted — no paraphrase path exists); AST import-boundary proof that nothing under packages/protocols touches an LLM client. Triage branch coverage 100.00% ENFORCED as its own check-py lane. Zero clinical content — mechanism only.
- #274: extract client rides the shared box's daemon-kill window (single 8s retry); server side already 503s while degraded, supervisor fast-restarts in 5s, SIGTERM-attribution logger armed (box-owner question pending its next strike).
- Design pass 6 delivered on its branch (PR follows #278): the CTA saturation finding (Oura bone pill ~6% sat vs our teal slab 36% — five passes never measured it), tonal secondaries, focused-flow exits, glyph-badge empty states, tabular figures; 347/347 post-merge.
- INT-233 spoken dialogue in PR #278: agent asks aloud, synchronous barge-in (no speaking+listening state representable), per-turn extract+confirm, digit guard swept across all ten packs, clip-cache lifecycle with the invariant-3 distinction stated.
- LOOP_STATUS: CONTINUE

### 2026-08-28T19:10:00+03:00 · INT-233 + INT-234 · done (PRs #278, #280) — wave 6 closed
- Spoken intake dialogue merged: the owner's "disturbable voice interaction" at the dev tier — agent asks aloud from catalog tr strings, synchronous barge-in (no speaking+listening state representable), per-turn transcribe→extract→spoken confirm, per-turn text fallback, digit guard swept across all ten packs, session clip-cache with the invariant-3 distinction stated; production dialogue remains the LiveKit Talker.
- Design pass 6 merged: the CTA saturation register (Oura bone pill ~6% sat vs our 36% teal slab — the loudest element, unmeasured by five passes), tonal borderless secondaries, back affordances on focused flows, glyph-badge empty states, tabular figures; zero existing hexes changed, added cta/onCta AA-pinned.
- Wave 7 building: INT-042 taxonomy, INT-033 FHIR mappers, INT-024 chaos harness. Hızlı/Detaylı modes agent queued for the next free slot (02 §22-34).
- Session tally: 30 issues landed end-to-end.
- LOOP_STATUS: CONTINUE

## 2026-08-28 — INT-042 merged (PR #282)
- Taxonomy landed: taxonomy/branches.yaml seeds all MHRS branches from 09 §1 (verify_live_list true), every branch resolves to a cluster, `protocols coverage` CLI renders the honest zero-coverage matrix, and an unknown booked branch fails the pinned test. Invariant 13's "every branch resolves" gate is now mechanical.
- Wave 7 remainder: INT-024 chaos re-merged after a .PHONY union conflict (CI re-running); INT-033 FHIR mappers resumed after a watchdog stall; INT-235 voice-chat UI and INT-236 adaptive packs + Hızlı/Detaylı modes building.
- LOOP_STATUS: CONTINUE

## 2026-08-28 — INT-024 merged (PR #284)
- Chaos harness landed: `make chaos EXPERIMENT=<id>` runs staged fault experiments; the vendor-kill experiment proves the typed fallback engages in ~2 µs against the 2 s bound, recorded as a measurement in docs/evidence/ (invariant 20 wording respected). Re-merged after a .PHONY union conflict with the taxonomy PR.
- LOOP_STATUS: CONTINUE

## 2026-08-28 — INT-033 merged (PR #286)
- FHIR R4 exchange landed: bidirectional mappers for all nine acceptance resources, seven hypothesis roundtrip properties over wire JSON, live HAPI $validate zero error/fatal in check-integration. Triage honesty pinned: LLM candidates can never enter a bundle; the RiskAssessment subset has no probability element (invariant 20 by construction). C-SSRS stays out of exchange (HB-L2); GAD-2 carries only a local coding — no verifiable LOINC total-score code exists.
- CI note: check-py red was the known OTP rate-limit flake; gates red was the PR-title format (reruns keep the stale event payload — close/reopen refreshes it).
- INT-041 (protocol compiler chain) is now unblocked.
- LOOP_STATUS: CONTINUE

## 2026-08-28 — INT-236 merged (PR #288)
- Owner directive landed at the dev tier: askIf adaptive gates as serializable data mirroring the DSL (four structurally-obvious gates; clinical-judgment gates refused and listed for pack owners), dynamic applicable-question progress, Hızlı/Detaylı modes per 02 §22-34 — privacy self-check with the verbatim deferral marker, instant Sıranız geldi checkpoint to a v2-partial review with zero lost answers. Pack-layer helpers exported; the dialogue surface inherits gating through them.
- LOOP_STATUS: CONTINUE

## 2026-08-28 — INT-235 merged (PR #290)
- The karşılıklı konuşma surface landed: two-sided live transcript with in-place ASR replacement and inline states, ask-ahead turn advance with reconcile-behind by work id (the "soru hazırlanıyor" wait eliminated), multi-question extract absorption with skip-of-answered, session clip pre-warm, persistent typed composer, realtime "Not oluşuyor" section sheet with quote provenance. Union with INT-236 proven: 456/456 mobile tests. Simulator visual pass deferred to the next design round.
- LOOP_STATUS: CONTINUE

## 2026-08-28 — INT-057 merged (PR #293)
- Protocol Authoring Agent landed: generate-l0 scaffolds guideline-cited L0 draft packs for all 91 intake branches (excluded cluster refused), citation placeholders carry the blueprint's named guidance categories with all eight cluster-specific titles marked awaiting-human, pack_compilable refuses every stub, import-boundary AST scan proves zero patient-data access, regeneration idempotent. The department-question content chain now has its scaffold tier for every branch.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-223 merged (PR #295)
- Minor & guardian rules landed fail-closed: age/actor resolution enforced inside ensure_consent (single enforcement point), typed 403 leaking neither DOB nor band, no DOB collected or persisted, every non-adult path guardian-gated, non-TR subjects refused rather than judged against TR thresholds, guardian_links behind a shut flag with awaiting-human basis/retention. Nine contested legal values refused and filed as HB-L20 for Turkish health-law counsel.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-059 merged (PR #299)
- Triage golden suite: 206 goldens / 272 tests with the derivation held as data and asserted, 18/18 mutations detected, and the acceptance's broken-RED run proved on disk then reverted (16 failed / 20 errors → clean 255 after checkout). Adds the `make safety` target CLAUDE.md names, which did not exist.
- Three findings recorded: base-RED edits are caught at build time by tighten_rule's verbatim parent pin (invariant 7 by construction); the rules file's own LT-01-N negative control cannot catch a gate loosening because its three-day anchor is masked by the tense guard (same-day near misses added); the route axis was nearly left unpinned — the first draft documented an assertion it did not make.
- Honest headroom: no cluster or deep pack exists yet, so "clusters+deep" waits on INT-044..052/INT-061+.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-134 merged (PR #297)
- The demo department list is gone: GET /v1/taxonomy/branches projects branches.yaml (9 clusters, 92 branches, name_tr verbatim) with version = sha256 of the served bytes, 503 rather than an empty picker, and a device fallback chain of server feed → cached last-good → bundled seed pinned field-for-field to the YAML. A third scan marker, reference_data, is caged to /v1/taxonomy by the same segment-boundary rule as pre_auth and consent_management; unguarded_data_routes() stays empty. Merged cleanly with INT-223's age gate and re-verified.
- MHRS SMS paste-parse ships whole (raw SMS never persisted — cleared in the same reducer action that parses it); image OCR is wired fail-closed behind documents consent AND an honestly-false licence flag per 03 §4.9.2(f). Visit date is optional per 02 §2b.
- Gate defect corrected: nav.spec.ts matched filler tokens case-insensitively while the canonical no_placeholders.sh is case-sensitive, so the real branch name "Ortodonti" tripped it.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-238 merged (PR #301)
- Owner bug "kaynaklar cant be added" root-caused and fixed: app.py built its Scanner slot from the dev stub alone, unconstructible without an opt-in env var, so on any normal stack the slot was None and DocumentStore fell back to no-scan-configured — while a healthy ClamAV sat on 3310 and INT-120's tested ClamAvScanner sat unreferenced. Every upload stuck in quarantine forever. Scanner precedence is now strongest-first so the stub can never shadow a live clamd; a scanner that cannot produce a verdict returns a typed 503 with the row left quarantined instead of an uncaught 500. Proved end to end on the live stack including an EICAR rejection. The api harness injecting a clean scanner into every case is exactly why no test caught the slot the service builds at boot.
- SECOND HARD STOP, surfaced not worked around: docs/legal/ does not exist, so the consent catalogue is empty and no scope can be granted through the app at all (INT-210, owner + counsel). On a real device this independently disables documents, records and sharing.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-239 merged (PR #303)
- Owner directive answered on both counts. The two co-equal buttons and the entire one-shot record→transcribe→extract path are DELETED (VoiceFirstIntake.tsx, prefillForPack, four reducer phases, two actions, eight catalog keys), with tests asserting the keys are gone from both catalogs and the reachable phases are exactly gate|dialogue|steps. Typed intake stays reachable from four places as the accessibility path.
- The fixed nine are gone: each department carries 9-13 questions of which 7-9 open the flow, the rest gated in the DSL's ask-if shape, with second-level chains. A test pins the exact symmetric difference of the asked sets for two divergent first answers in ten departments, three of them diverging in both directions. One predicate drives typed steps, spoken dialogue and the section panel; only a confirmed answer opens a gate; progress no longer implies a fixed total.
- Clinical-judgment gates refused and listed for pack owners (chest-pain red flags, cauda equina battery, thunderclap headache, pregnancy as a universal gate, and the text-only safeguarding set files/13 §13 requires — a delivery field the dev tier does not have).
- Recorded deviation: questions.ts is 1378 lines against the 500-line convention; the per-department split is queued separately.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-228 (PR #305) and INT-041 (PR #309) merged
- INT-228: document keys are now bounded by construction — base64url(sha256(domain||pseudonym)), 43 chars, the floor for 256 bits in that alphabet. No truncation, so collision resistance stays at the pseudonym's own bound instead of becoming a function of config (~2^80 vs ~2^20 across key ids). A SECOND latent defect surfaced in the same arithmetic: three 40-char segments exceeded the audit log's 128-char cap, so a key could be built, used to write an object, then rejected by AuditChain.append — an object existing outside the tamper-evident record (invariant 4). The INT-197 patient-id workaround is removed at all three call sites, and the old-key-still-downloadable test was proved worth having by mutation.
- INT-041: the compiler, with 82 issues transitively downstream. Deterministic emit (two runs byte-identical by diff -r, hash bound to SessionState at type level) and ~20 fail-closed refusals each with a named test — empty clinical sign-off, missing paediatrician signature, any draft_needs_source rule, RED without a register or whose action does not resolve for all three locations, ON_SITE offering 112, UNKNOWN asking other than exactly one question, a child lowering inherited acuity, extending the sealed life-threat set, conflicting overlays as errors naming every writer, paraphrasable instruments, text-only slots declaring voice. Refused to invent archetype at-codes, drug orthography, FHIR extension URLs, guideline ids or any default register. Four INT-040 schema gaps and a validator crash found and filed rather than patched; ADR-024 closes the gate/when reconciliation.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-103 merged (PR #307)
- Mobile LiveKit voice client against the real INT-090 contract: room per session, 600 s token cap, canPublishData pinned false — so the client is a data-channel RECEIVER only, and the RED packet carries ids and axes, which is what lets a RED render with media torn down (invariant 21, test-pinned). 105 new tests.
- Two defects its own suite caught: a double token fetch inside the refresh margin, and invariant-3/9 source scans matching their own explanatory comments — fixed by stripping comments, because a gate that cannot tell an explanation from a call pushes reasoning out of the source to stay green.
- Two judgement calls: the microphone purpose string claimed the app records what you say ("kaydetmek"/"to record") and was corrected in both locales — the product never records (invariant 3), and a store purpose string promising a recording we do not make is the wrong kind of inaccurate. And the vendor's usual webrtc config plugin was refused because it declares CAMERA (no video path) and the iOS background-audio mode, which would let capture continue behind a backgrounded medical app; plugins/withVoiceAudio.js does audio-only and strips both.
- Not worked around: mint_room_token still has no HTTP route, so a session refuses to start with token_unavailable rather than using a stubbed or locally synthesised JWT. Turn-taking events stay unmapped (INT-091/092 own that wire protocol).
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-237 merged (PR #313)
- Owner complaint "tts is so awkward" answered with measurement before change. Sixteen probes established the dev voice is band-limited to 3040-3445 Hz across ALL of them — a 405 Hz spread from one-word to 153-character utterances, so Turkish ş/s/ç/z/f fricative energy is absent — and that its duration head allocates erratically (two 31/33-char strings 1.9x apart in rate).
- The safety finding: the three RED imperatives sent as one string ran at 15.38 c/s against 6.4-8.8 c/s separately — the same words 2.4x faster, 90 ms apart, on an emergency script. Now 6.87 c/s at 320 ms apart.
- Client-seam shaping: sentence-boundary splitting with verbatim preservation test-pinned (invariant 10), guaranteed terminal punctuation, 15 ms head/tail trim with an 8 ms fade, consistent 300-320 ms boundaries; median cost +0.21 s/turn. Rate is NOT improved and one composed question got worse — kept in the evidence as the counter-example rather than dropped.
- Verdict recorded: the band limit and the duration head are architectural properties of the pinned artefact and unreachable from any client seam. That artefact is 03 §4.9.1 row 12, the fallback — not the production tier. INT-243 acts on it.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-243 merged (PR #315)
- The intended production TTS tier is served, with the fallback voice left running so a failed rollout costs nothing. Licence cleared by audit: neither weights repo carries a LICENSE file at all (404 on every variant — only a card tag, which invariant 19 forbids trusting), but the vendor source repo carries stock unmodified Apache-2.0 with an irrevocable grant and no acceptable-use rider. The blob is vendored beside the mirrored weights with a checked SHA256SUMS so the grant travels with the artefact; the registry row records model@revision, both weight digests, the blob url and digest, the date read, and a note stating the weights repo has no licence file.
- A/B on the INT-237 corpus (dated, named, measurements not quality claims): rolloff99 median 3280 → 6069 Hz, energy above 4 kHz 0.0029 → 0.0283, lead silence 100 → 10 ms. Two caveats kept in the open: five probes come in duller than the fallback (variance a fixed band limit does not have), and a one-word RED imperative arrives wrapped in 1.2 s of silence — INT-060 pins the compile-time trim.
- Normaliser proven disabled by load-time and per-synthesis assertions that fail the request rather than speak. The positive control demonstrates invariant 22's harm concretely: with it engaged, a blood pressure reads as a fraction and the Turkish question particle becomes a unit of distance.
- VRAM was the binding limit and was not forced — the GPU is a MIG slice with 3.4 of 71 GiB free, so the device ladder chose CPU and we added zero VRAM. Compile-time clips are served; dynamic synthesis stays VRAM-blocked and takes CUDA on the next restart when the slice frees.
- Also corrects the fallback voice's registry row to self_hosted_now: true — it has been serving since INT-233, and a fallback the release gate believes is down is a fiction.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-037 merged (PR #311)
- KVKK data-subject rights: export (FHIR + PDF), erasure by destroying wrapped DEKs with the 30-day grace and cancelling live shares, rectification with hash-chained audit, and the m.13 SLA tracker carrying ids only.
- The CI failure was the branch's own test and the implementation was wrong, not the assertion: events.session_id is a FK with no ON DELETE clause, so erasing a subject's sessions violated the constraint on Postgres while SQLite silently allowed it — which is how it reached a green first commit. Erasure now de-links telemetry (session_id → NULL) rather than orphaning or sweeping it: telemetry has its own clock and is PHI-free by construction, so the row survives with the pointer to the erased session cut.
- Nine further defects from a mid-flight review, three of them serious: object bytes were removed INSIDE the row transaction, so one storage failure rolled back the shred while earlier objects were already gone (now a pass before the transaction opens, matching INT-036); an unencodable character made a patient permanently un-exportable — a 500 on every future GET against a duty to produce the document; and every erasure would have registered as an m.13 breach because the grace window and the response window are both 30 days, so a scheduled delete went overdue the moment its grace ended. Also six DELETEs missing tenant_id, a downgrade dropping the parent before its child, and FastAPI's default 422 echoing patient free text into logs (invariant 6, repo-wide).
- Fails closed where the law's text does not exist: export refuses while docs/legal/strings.yaml is unauthored, BUT the request row is created and its clock runs, so an unanswerable obligation stays visible. The PDF writer raises rather than transliterate a Turkish character.
- Recorded, not hidden: erasure writes no DEST-2017 destruction record yet, and execute_due_shreds has no production caller (no services/workers tree), so it is reachable from tests only. A fourth human ask was added — an erased subject remains re-identifiable through identity_vault, which is keyed by the pseudonym erasure deliberately keeps.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-043 merged (PR #317), status awaiting-human
- base.intake landed complete in STRUCTURE and empty in CLINICAL VALUE: 8 sections, 56 slots, 13 red-flag families, 116 English mirror entries. The compiler refuses to serve it — 14 refusals, and with an unsigned sign-off two more. That refusal is the acceptance, not a failure. Status is awaiting-human, not done: a named licensed physician still owes, per family, the trigger and its wording, the EK-4 level, route, register, the three location action blocks, tense anchors with a distinct script per tense, and excluded criteria.
- TWO OWNER DECISIONS REFUSED RATHER THAN RESOLVED. (1) The fast-mode turn budget is arithmetically impossible as specified: ceiling <=18, baseline 16-21 before three universally-required additions, so even the floor is 19 (21-26 with the two ungated slots). Five options costed in the evidence; none chosen; the PHQ-2/GAD-2 lever is already spent. (2) packages/protocols/sources/ does not exist at all — no committed snapshot for any family, and base.life_threat.yaml already cites a path inside it. That is why all 13 families are draft_needs_source rather than only the clinically incomplete ones.
- Deviation endorsed: no family declares a register or action block. Invariant 21 binds RED rules; no family is RED yet, and a register chosen by an engineer before the acuity exists is exactly the default the invariant forbids. The gate is proved by a test that promotes a family to KIRMIZI_K2 and asserts the compiler then demands the register and all three locations.
- Four DSL gaps reported: no English field, no priority-class field (13 §14.13's gatekeeper promotion is inexpressible), no fast/detailed mode marker, and no datetime type — so a stroke window has no exact representation.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-060 merged (PR #319)
- Clip cache builder: make clips VOICE=<id> walks the compiled manifest, synthesises each scripted string and stores Opus in MinIO under the manifest's own key. 151 tests at 100% line and branch; verified live against compose MinIO (13 rows → 13 objects, keys identical, objects start OggS).
- Key parity is structural rather than asserted: the builder carries no hasher at all, and two AST scans prove no hashlib, no sha* attribute and no tr-orthography helper is reachable from the package. A builder that re-derived the key with different normalisation would miss the cache at runtime; now it cannot.
- Silence trimmed at build time, where invariant 21 says it belongs: bounds asserted on the DECODED STORED clip because encoder priming adds samples an intermediate buffer would not show. INT-243's 3000 ms RED shape becomes 659.6 ms at 19.9 / 24.5 ms.
- LICENCE FINDING: PyAV rejected — its wheel's libavcodec link-edits GPL libx264/libx265 while avcodec_license() self-reports LGPL, via a packaging patch upstream configure refuses to produce, and it ships no licence blob for any bundled binary. Switched to soundfile (BSD-3 + LGPL-2.1, blobs shipped and sha256'd) and recorded so it is not re-proposed.
- Two guards were hit and NEITHER weakened: the protocols package is I/O-free and audio-free by construction, so the code moved to a new packages/voice-clips workspace package (git diff on packages/protocols is empty). The INT-090 audio ban list was then STRENGTHENED — six more libraries banned, one enumerated per-file grant, and the allow-list test became an equality pin so a second grant cannot slip in.
- Unblocks INT-091, the Talker.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-202 merged (PR #321), status stays doing
- Encrypted PITR, replication and the drill land as a standalone profile-gated overlay; infra/docker-compose.dev.yml diff vs main is zero lines and a test asserts it.
- The drill itself did NOT run: make backup-drill exits 3 — 11 GiB free against 80 needed, 0 GiB container memory against 22. Blocked against HB-I1/HB-I2, no RTO figure produced, the drill was not shrunk to fit, acceptance box unchecked, issue stays doing.
- HB-I8 raised, and it reaches beyond this issue: a backup OUTLIVES the crypto-shredding it is subject to, so a restore can resurrect an erased subject — KVKK-7 / DEST-2017, not an ops preference. files/10 §3 states RPO and RTO but no retention, and 06 §3's matrix has no row for backup copies at all. Meanwhile the repository expires nothing (loses nothing) and the drill refuses to run without an explicit retention value rather than choosing one. Second question in the row: "a second location in Türkiye" names no site, provider or region, so the DR endpoint has no default and minio-dr is labelled a stand-in.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-144 merged (PR #323), status awaiting-human
- WCAG 2.2 pass with Turkish screen-reader labels: 710 → 729 tests, 52 criterion assertions, 25 tr keys with en mirrors, no existing test modified and no palette hex changed.
- THREE DEFECTS an independent post-green review caught, each of which made the app unusable with a screen reader: the consent switch nested in a pressable row was NOT FOCUSABLE ON iOS, so there was no way to withdraw a KVKK consent; live="assertive" is Android-only, so all four error lines were MUTE under VoiceOver; and accessibilityViewIsModal is silently dropped by RN on Modal, so the suite had been certifying a no-op. The review also caught a "Hata: " prefix leaking into visible copy — reverted, spoken only.
- THE RED SCRIPT RENDERS FOR NOBODY: red.ts decodes and session.ts emits, but no consumer exists anywhere in the app. Documented with the seven requirements its dedicated issue must carry, including that the 112 affordance is ABSENT FROM THE ACCESSIBILITY TREE under ON_SITE rather than dimmed.
- Honest conformance: 16 verified, 5 by inspection, 6 not applicable, 8 unverifiable without a device screen-reader run (including on-focus/on-input — the OTP screen moves focus per keystroke without advising the patient), 4 not met and named. Contrast measured across the palette and pinned at its measured floors rather than repainted.
- awaiting-human: the BK1-31 mapping is derived from the forced 1:1 with WCAG 2.2 Level A, not transcribed from the Ministry checklist, so the report must not reach the İnceleme Komisyonu yet. The public statement is written and marked not-for-publication.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-091 merged (PR #325): the Talker exists
- services/voice-runtime is created. 246 voice tests at 97.52% statement+branch; unit lane 1964; mypy --strict over 138 files; make check and make safety both exit 0 — and make safety now actually runs the PolicyGuard suite it always claimed to.
- Invariant 9 proven, not asserted. Six tools: set EQUALITY against the real registry, with the gate's own ability to fail proven against synthetic registries of seven and five. Never-awaits: structural (no awaitable member, checked by introspection so adding one later fails) AND measured on a virtual clock — identical turn time against backends stalled 0 s, 10 s and 10 000 s. Insertion window: the 12 §6 ladder with per-conjunct negative controls and an expiry that writes the note flag first and rolls back if it fails. RED-preempt-only: the type cannot spell RED from an LLM candidate, and provenance requires the rule id to belong to the pinned pack.
- Two behavioural reds were real defects: the scheduler stamped arrival at first tick rather than at enqueue, silently resetting the delivery ladder on a quiet session; and the displaced-profile scan flagged its own docstring, so it now walks the AST — prose may name a displaced profile, code may not.
- Fails closed on what is absent rather than stubbing: no TTS adapter (INT-095), no room-token route (INT-103's finding), HMAC attestation belongs to INT-093. Two clinician questions recorded: the safe-bridge sentence when PolicyGuard drops a whole turn (silent until then, asserted), and delivery deadlines for the non-urgent classes, which 12 §6 does not state.
- The voice chain is now complete end to end in the repo: compiler → clip cache → LiveKit transport → Talker, with the production voice serving.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-254 (PR #329), open and green, NOT merged

- The four schema gaps INT-041 found between INT-040's `RedFlagRule` and `files/protocols/base.life_threat.yaml`, plus the real defect found in the same pass. The reproduction goes from **21 validation errors to 13**, and the residue is pinned open by a test rather than absorbed.
- `tense_anchor` was the one with a plausible wrong answer. It is a slot REFERENCE, not a bare key, and the proof is in the code: the `when` tokenizer takes dotted idents, `triage/engine.py` unions the anchor into `referenced_slots(when)`, and `TriageContext.answers` is documented as keyed "by the dotted slot reference exactly as the when predicate spells it". The anchor and the predicate were one namespace at runtime and two in the type. One `SLOT_REF_PATTERN` in `protocols/types.py` now feeds both the DSL constraint and the tokenizer's `ident` group, with a test asserting the tokenizer really uses it. Bare anchors stay valid, so base.intake, all 79 specialty packs and every fixture are untouched.
- **A live workaround was removed, not left beside the fix.** INT-059's golden corpus had already hit this and rewrote `.` → `__`, so the safety suite evaluated the life-threat anchors under a name the document never writes while its mutation test claimed verbatim carriage. It also defaulted `status` to `active`. Both are gone; the goldens now run on the document's own spellings.
- `status` stays REQUIRED with no default and the two sourced exemplars carry `status: active`. A default makes a FORGOTTEN status read active — the unsafe direction, and ~30 rules are still to be pasted against this file. A test asserts `is_required()` so the shortcut cannot be taken quietly later.
- `SourceBlock.note` and `LocationAction.secondary` added as optional. `secondary` opens no second carrier for the ON_SITE 112 affordance (tested), but the residual IS recorded rather than closed: action codes are open SCREAMING_SNAKE strings, so a 112-bearing CODE under ON_SITE is not structurally excluded — for `primary` either, which predates this issue and needs an enumerated set no blueprint writes down.
- The validator defect was worse than a crash: `validate_packs` iterates every pack, so the `AttributeError` at `validator.py:351` **took every remaining finding with it** — a broken action masked the numeral and follow_up_tr checks on its own pack. All three location branches are guarded now (the same defect sat on `remote`/`on_site` two lines above), and an incomplete RED action produces `RED_ACTION_UNRESOLVED` naming the rule, matching the guard `compile/resolve.py:229` already carried. INT-041 had routed around it by ordering; ordering holds only for callers that happen to run the compiler's check first.
- **THE DOCUMENT STILL DOES NOT LOAD, and that is stated rather than smoothed.** Thirteen errors remain, every one a delivery/safety annotation the DSL does not model: `audio{}`/`suppress_attention_interrupt` (the 02 §5.3 register axis — the airway exemplar is KIRMIZI_K1 *and* CALM because alarm is the harm), the 04 §4.2 crisis path fields, paediatric proxy, and two document-level blocks. A test asserts the list is EXACTLY those thirteen, so a silently shrinking list — an `extra: allow` anywhere in the chain — fails rather than passes. INT-255 owns them; no new human blocker was raised because the content behind each is already on HB-C3, HB-C8 and HB-C9.
- Two stale documents corrected in place: ADR-024 claimed as a consequence that the life-threat file "needs no edit to be loadable", which was false when written (21 errors) and went uncaught because no test loaded the blueprint document at all; and the file's own `schema_reconciliation` block still read `OPEN — decide before the compiler is written` after ADR-024 decided two of its items and INT-040 implemented a third.
- FOUND, NOT FIXED: `make check-golden` and `make security` are named in CLAUDE.md and **do not exist in the Makefile**. Precisely: gitleaks and semgrep DO run, but as pre-commit hooks rather than in ci.yml, so they gate the laptop and not the merge; bandit, trivy, osv, checkov, license, sbom, phi-scan and claims-scan run nowhere at all. Invariant 14 calls that set "never skipped" — it is unimplemented, which is quieter than skipped. The golden suite itself does run, under `make safety` and inside check-py, so `check-golden` is a naming gap rather than a coverage one.
- Gates: check-py, safety, check-ts and the CI gate scripts all exit 0. check-integration PASSES in CI against a clean database; the 14 local errors were the shared dev postgres being stamped at `0005_int141`, a migration that exists only in the int141-wt worktree. The volume was not reset; another session is on it.
- NOT MERGED, and the reason is a finding rather than a gate failure. All four CI checks are green (check-py, check-ts, check-integration, gates). But CLAUDE.md requires CODEOWNER review for any change under `packages/protocols/**`, and **there is no CODEOWNERS file in the repository** — `.github/CODEOWNERS` does not exist and main is unprotected, so that requirement has no mechanism behind it. Two of its three clauses ARE met (near-miss negative controls added, `make safety` green); the third cannot be satisfied by anything in the repo today. Same class as the missing `make security` target: a rule the constitution states and the repo does not enforce. Recorded rather than self-merged around.
- LOOP_STATUS: WAITING_HUMAN
## 2026-08-29 — INT-145 merged (PR #334)
- Client crash reporting built as a DENY-BY-DEFAULT allow-list of 17 keys read out of the untrusted event, never a regex blocklist. The exception message is not sent; the wire carries an error code. Thirteen tag keys are split by who supplies them, each with its own shape — load-bearing, because an allow-listed key is not enough when "05321234567" is a well-formed string. Breadcrumbs carry a route template, never a URL.
- Adversarially proven: a Turkish symptom sentence, a phone number, a checksum-valid TCKN and a patient-named document title planted into message, exception values, frame vars and source context, frame module and function, three breadcrumbs including a full network URL with query, on-list and off-list tags, extra, contexts, user, request and attachments — all asserted absent from the envelope BYTES including percent-encoded forms, with a blanket rule that no character above ASCII 126 appears at all. The suite was then MUTATED THREE WAYS AND REVERTED to prove it bites.
- No dependency added: deny-by-default and "replay unreachable rather than unconfigured" ruled a vendor SDK out. No metric promoted — all four ids stay planned because an RN client serves no /metrics. No default endpoint; nothing buffers to disk.
- Finding: the repo has no third-party npm licence sink at all; licence_verified_at exists only in the model registry.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-133 merged (PR #331)
- Profiles, companions and guardian flows on INT-223's rules engine. NO UNDER-18 IS SERVED BY ANY PATH: under-12 and 12-17 refuse with guardian_consent_required, a self-declared DOB refuses, a non-TR subject refuses, and the guardian sees nothing of an adolescent-private section without a recorded clinic policy. Each refusal records which HB-L20 question gates it — SERVER-SIDE ONLY, because a body or a screen printing "adolescent_self_consent" would itself disclose the subject's age band.
- All four INT-223 refusals hold under test, including a sweep of every role x speaker x acknowledgement for a 14-year-old and an inspection proving no emancipation affordance exists anywhere in src/.
- No new personal-data category: the attribution facts already existed on ScreeningProvenance and already exported to FHIR, lifted to the session so one flag cannot drift into three. Nothing identifies the companion.
- Honest omission: no metric emitted, because the catalogue names no id for the proxy-reported share and invariant 13 forbids emitting what the catalogue does not hold.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-175 (PR #336) and INT-141 (PR #340) merged
- INT-175: Langfuse and annotation queues, with REDACTION DELIBERATELY REJECTED as the primary control. The second red run proves why — with the plausible wrong implementation in place, 24 tests fail because a Turkish symptom sentence carries no identifier for redact_text to match and sails straight through. So the boundary refuses a CARRIER: LlmSpan is a frozen closed set of id-shaped fields into which a sentence cannot be constructed. Content mode is ABSENT, not off — no flag, no env var, the module reads no configuration at all (AST-asserted), and opening it means adding a type and deleting the tests that say it does not exist. All three queues are shut because two preconditions are missing: HB-L6 is open AND no purpose in 06 §2 covers staff access, so there is no basis to check against. Langfuse is open core, so the MIT claim was verified against the ee/ carve-out: annotation queues are not among the eight enterprise features. Never booted — every compose assertion is static, and that is stated.
- INT-141: content-freedom as VOCABULARY CLOSURE rather than a denylist — every token of a payload must already exist in the committed template corpus, so any interpolation fails including the symptom nobody thought to forbid. Attacks included the adversarial patient whose branch shares a word with generic copy, a branch made only of generic words, and Turkish casing (KADIN lowercases to kadin in Python but kadın in Turkish, so folding maps İ→i and I→ı first). İYS has four independent locks, the strongest being that the consent record type is abstract with zero concrete subclasses, so the commercial send cannot be written. The preference route carries its own marker rather than a consent scope: gate it on consent and a patient who withdrew core can no longer reach the switch that stops the messages. Quiet-hours baseline REFUSES rather than guessing 22:00.
- Cross-branch break caught in CI: INT-133 made three session columns NOT NULL, and INT-240's cascade test writes raw SQL by design (it proves the DDL guarantees erasure rather than a sweeper), so the ORM defaults never ran.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-240 merged (PR #338)
- Satisfaction free text treated as clinical text: the sentence lives in its own envelope-encrypted table rather than events.payload, whose "id-shaped, PHI-free" declaration the rollups depend on. Erasure reaches it by FOREIGN KEY CASCADE, not a sweeper someone must remember. The rollup test TAMPERS the stored payloads to re-insert patient text — the realistic future regression — and proves the projection type has no text member to leak from.
- services/metrics created, pulling in the full invariant-15 contract.
- Packaging took four corrections, each a real cross-branch interaction rather than a flake: a raw-SQL fixture that predated three NOT NULL columns INT-133 added; a textual union that fused two model classes into one broken block (rebuilt as main's file with the class grafted whole); a dropped import from that rebuild; and finally two alembic heads once INT-141 landed, caught by the RLS integration lane and re-pointed to 0008.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-253 merged (PR #342)
- A negative result worth recording: five parallel i18n branches landed in one day with ZERO mirror drift, ZERO hardcoded user-visible strings, no untranslated mirrors, no duplicate keys and no bare "sen". 672 = 672, matching line-for-line. The drift was 21 orphan keys whose screens were removed, and a clinical [REVIEW] mark that only landed on the Turkish side.
- The completeness gate is wired into make check as check-i18n, with every flag list asserted by EXACT EQUALITY so new violations fail and fixed ones must be struck. It also pins the shipped locale set — ar is P3 behind an RTL audit, so an ar catalogue or any forceRTL reach fails the build.
- THREE FINDINGS FLAGGED, NOT SILENTLY FIXED. (1) Nine keys reserved rather than deleted, because the gap is a product one: the LiveKit session enters connecting/reconnecting/backgrounded/interrupted and NO SURFACE TELLS THE PATIENT — a dropped voice visit is silent. (2) 34 instructional strings use the short imperative where 00 §2 asks for -iniz, and no -iniz verb exists in the catalogue at all; 19 of them are what VoiceOver speaks, where brevity is an accessibility property, so it is one decision for the copy owner rather than a partial rewrite. (3) 23 PolicyGuard findings claimed to be guard defects rather than copy defects — including a sen-detector that matches the polite imperative "edin", which would stop the Talker saying "Devam edin". That claim is being verified independently before any safety guard is touched.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-171 merged (PR #344)
- The k-anonymity helper is a GATE, not a utility: a view that cannot satisfy k refuses to materialise. Twelve adversarial attacks refused, including one patient wearing 40 sessions (rows are not people), a crossing of three coarse dimensions, REFUSAL AS AN ORACLE (empty and single-subject refuse identically, or "refused" means "someone was there"), and REFUSAL AS DISCLOSURE (metric labels pinned so a refusal cannot publish the cell it withheld).
- Free text is refused the label de-identified entirely — not redacted, not scrubbed, absent from the DDL and unreachable at the grant, with HB-L6 cited at three places. k = 10 was not invented; four blueprint sections state it.
- Scope addition: the Loop-2 opt-out is enforced, because an opt-out nothing checks is the decoration this issue exists to remove.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-205 merged (PR #348)
- SIEM feed where alerts CANNOT carry narrative: SecurityAlert has no field narrative can occupy, and the normaliser projects vendor payloads onto a closed key tuple rather than filtering them. Fourteen tests plant a Turkish symptom sentence across nine vendor fields including a filename carrying a patient's name and — the sharp case — Wazuh's rule.description, which the vendor interpolates event fields into, so rule names now resolve from committed XML by id and never from the event.
- Licence ancestry mattered: wazuh-indexer forks OpenSearch, not Elasticsearch — the wrong ancestor would have put SSPL on the PHI path. Wazuh manager is GPL-2.0-only with an OpenSSL exception and a redistribution-scoped derivative-work reading, which is why the ruleset is written from scratch in the user id range. Falco's engine and its rules repo were read separately. All tags dereferenced first, because Wazuh's are annotated and an undereferenced ref 404s into a silent "no licence".
- Not exercised and not shrunk to fit: the tier needs 80 GiB against 14 free, so the deploy exits 3 naming the blockers. No correlation window and no alert retention invented; the deploy exits 2 naming the retention ask.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-249 merged (PR #356): the voice no longer hangs
- Measured on live daemons, both /health-green: the preferred lane answered its health probe in 0.14 s and took 3.99 s for one word and 6.12 s for a sentence, while the fallback took ~1 s. Selection on health alone chose the slow one, so the patient watched a spinner.
- Worse than reported: the cap was 30 s applied PER SENTENCE SEQUENTIALLY with no synthesis-time fallback, so a two-sentence clip held ~60 s and then dispatched a TERMINAL failure into the manual steps.
- The budget is the blueprint's, and the obvious number was wrong: §4.5's 520 ms is a time-to-first-token figure for a STREAMING path these daemons do not have — gating on it would have rejected the tier the blueprint itself designates as the acceptable fallback and left the app with NO VOICE AT ALL. Used §4.4's round-trip band for the only production profile instead: 1684 ms to admit, 2364 ms in flight. The reasoning is in the code because 520 ms is the obvious wrong answer.
- Ask-ahead was already correct and is now PINNED — there are no RN render tests, so gating the body on `playing` would have passed the whole suite; three identity tests prove a late result cannot rebuild the turn and restart the clip.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-242, INT-247, INT-248 merged
- INT-242 (PR #346): an NPS invitation is classified COMMERCIAL under 6563 — it concerns nothing about the care received and asks whether the patient would recommend us — so with no İYS consent it cannot send, and that is what ships. Five independent constructions stop it, and a stub registry that DOES answer clears the gate in tests, proving the gate is a real check. Nine values refused with named humans; sampling rate and cool-off refused as CONCEPTS, since an always-refusing knob is theatre and a set one is invented.
- INT-247 (PR #354): a carried medication can no longer masquerade as current. Confirmation is enforced in the TYPE — the carried type has no field readable as current, and undecided facts sit in a type the renderer cannot accept. "Stopped" renders distinguishably from "absent" because they mean different things to a clinician. The demo seed was proved unable to reach a real account, and that proof is now pinned rather than merely true.
- INT-248 (PR #350): PolicyGuard could not say "Devam edin" and reported its own disclaimer as a diagnosis claim; two RED action scripts were affected through "gidin". The guard is narrowed on real morphology — the past suffix surfaces voiceless only after a voiceless obstruent — and coverage of genuine informal address STRICTLY INCREASED. Catalogue findings 23 → 1.
- HB-C12b raised from that work and it is the session's most serious finding: two RED why_tr blocks state something about the PATIENT'S CONDITION ("Anlattığınız belirtiler kalple ilgili olabilir"), against the pack's own header. The paediatric one cannot be served; THE CHEST-PAIN ONE IS FULLY SOURCED AND WOULD COMPILE.
- Recorded honestly: I broke main earlier this evening by letting a resolution script commit through a failed YAML check, putting conflict markers into the backlog. Repaired, and the practice changed — resolve from git's own conflict list, sweep for markers, validate, and chain with &&.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-246 merged (PR #352): the last of the wave
- A dead voice lane now announces itself in development instead of degrading silently. Production behaviour is unchanged and pinned: the diagnostic returns nothing for every report shape, so production is the banner having no content rather than a hidden element.
- `make voice-doctor` answers "is voice up?" in one command, one line per lane, non-zero when a required lane is down — every verdict in its suite taken against a real local socket rather than a mocked error. Its own suite caught it printing "every lane answered" while a lane was refused.
- This exists because of a real incident: the owner reported the voice interface missing for hours while it was built, merged and running. Two causes stacked — a Metro bundler that had served the previous evening's bundle all day (its file watcher never fires under /private/tmp), and a dead tunnel to the speech server. Both now have standing guards: Metro auto-refreshes on every main change, and the lane probe is one command.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-224 done: store compliance, and the label that would have lied
- The finding, and it is the whole issue: **"labels generated from the data inventory" is FALSE if the inventory means the schema.** The invariant-18 annotations cover 111 columns and no audio row — because invariant 3 forbids writing raw audio anywhere — so a Data safety / App Privacy declaration derived from `Column.info` states that this product **does not process voice**, about a product whose central feature is a spoken intake and whose manifest asks for RECORD_AUDIO. False in the one direction a store reviewer notices, and nothing would have flagged it. Three more flows fall in the same hole: HealthKit/Health Connect reads (on-device), document bytes (object store), crash diagnostics (no endpoint).
- Fix: an inventory row is a **shape, not a table**. `store/facts.py` carries the same five fields for the four off-schema flows, each citing a repo file that states them, and the app's own manifest is cross-checked **both ways** — a capability with no row fails, and a row for a capability the manifest dropped fails too. Nine capabilities, all classified.
- **No vendor policy was written from memory.** Apple's App Privacy types, Google's Data safety categories, the Play Health apps policy and the IARC questionnaire all move; the loader takes only a dated verbatim snapshot bound by sha256 to the machine-readable file, and none is committed, so every label path fails closed (**HB-A12**, new). The derivation is complete and exercised end-to-end against fixture taxonomies.
- Invariant 20's gate is now **one pattern set in one place** (`intake_platform.legal.claims`): both suites that predated it — INT-020's over docs/security and INT-240's satisfaction scan — read their groups from it, and a test asserts neither can grow a local copy back; `docs/legal` and `docs/regulatory` are declared trees, so the store artefacts under `docs/legal/store/` are inside the scan by where they live. It caught my own README on the first run, which is the shortest proof the tree is really in scope.
- Device-claim gate: a listing describing automated triage or automated instrument interpretation fails closed rather than waiting for App Review — by then it is published. Phrase-shaped, not token-shaped, **because of Turkish**: the required fixed copy contains "tanı" twice and the permitted safety line contains 112. Denials are exempt in both directions (Turkish negates after, English before) and stop at a contrastive conjunction, so "triyaj yapmaz ama aciliyet düzeyi belirler" still reports the second claim.
- The sharpest red of the issue: run against **files/01 §4's own pitch** — "vizit öncesi **not** ve **triyaj** bayrağı" — the gate reported nothing, because **"not" is Turkish for "note"** and a bare English \bnot\b was in the denial set. The product's own promise line carried the token that exempted the claim beside it. Second time in one issue that a general text rule met Turkish and failed silently in the unsafe direction. Also dropped -sız/-siz from the denial set: it is privative, so "kesintisiz triyaj" is a claim.
- Recorded rather than smoothed: files/01 sells "realtime triage" and a "triage flag" while files/06 §0.3 Stage A runs every commercial tenant with device_functions OFF. **The strategy file's own pitch is copy this gate refuses** — which is exactly why §3b calls a marketing claims-control gate a P1 deliverable.
- Checklist: 15 rows, 5 satisfied, 10 blocked, 0 failing. A row with a check must cite a repo file; a row whose obligation is a vendor's published requirement may cite nothing and must name a HUMAN_BLOCKERS id that exists.
- Refused with named asks: the four store taxonomies (HB-A12); whether ephemeral audio is "collected", the Play Health scoping question, the IARC answers, the KVKK ground for crash diagnostics, and **INTAKE's legal entity — which the repo names nowhere** (HB-L21, new).
- **INT-257 filed**: files/01 §3b calls the marketing claims-control gate a P1 deliverable and no issue existed for it. Backlog 203 → 204.
- `make check` exit 0 (baseline on origin/main also 0). `make security` has no rule yet — INT-019; the gates that exist ran clean on the staged tree.
## 2026-08-29 — INT-241 merged (PR #358)
- Wait-time metrics landed as a NEGATIVE RESULT made structural. The acceptance names five intervals; only `records_processing` has both of its instants (upload → scan verdict, inside one handler) and is actually measurable. The other four are missing an end: `time_to_first_question_s` (sessions.started_at has no writer AND the Talker keeps the turn in memory), `note_ready_after_wrapup_s` (nothing ever sets sessions.completed_at), `doctor_link_first_open_h` (no share-redemption route — INT-150), `checkin_to_seen_min` (packages/connectors does not exist — INT-163). Two of those four had NO issue claiming them.
- Rather than emit plausible numbers, WAIT_SOURCES states the fact once and three artefacts are held against it in BOTH directions: catalogue status is live iff measurable, the Prometheus family must exist, `record_wait` raises. Landing an instant without promoting the row, or promoting without a writer, now fails CI. INT-241 stays open per invariant 17 for the four unbuilt intervals.
- Small-cohort discipline carried from INT-240 by IMPORT, not by copy: MIN_COHORT shared, a per-document_type breakdown suppressed WHOLE when any cell falls short (a total plus all-but-one cell gives the missing cell by subtraction), no min/max at any cohort size, and nothing observed raw into a histogram (a scrape after one observation leaks the value through _sum over _count). Patients who refused learning:service_improvement are dropped by the same evaluator the route guard uses.
- Refused with asks (all owner): histogram bucket boundaries (files/08 §4 G states none), a branch dimension on the export (branch × narrow window is the re-identification shape and a new personal-data field), and which issue owns the two unowned lifecycle instants.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-256 merged (PR #360)
- The universal history block — allergies, current medications, past medical history, family/social — authored ONCE and COMPOSED onto every department pack by packForVisit(department, profile), inserted in files/04 §1 order between the last anamnesis dimension and the free note. Mirrors what the protocol registry already does (base → cluster → specialty), which is why the blast radius on the existing suite was four assertions rather than forty. 18 steps; the pmh and family blocks are Detaylı-only and the gating is asserted.
- The line held: asking "do you have any allergies?" is product copy an agent may write; deciding what an answer MEANS is clinical. The guideline-grounded per-department content is INT-043 → INT-044..051, still awaiting-human on HB-C1. Every refusal is listed with its owner in the evidence §6.
- The merge itself would have shipped a bug: git auto-merged INT-247's unfiltered review block back in ALONGSIDE the per-kind one, so the medications section would have rendered twice and a carried ALLERGY would have appeared inside the medication list. factStateKey/factNoteMarkerKey stay kind-aware for the same reason — the medication-only wording prints "hasta bıraktığını söyledi" against a penicillin allergy, a false clinical statement rather than an awkward one.
- Filed under the wrong id at first: INT-250 is the blueprint's tenant-onboarding issue. Renumbered every reference the branch added; main's INT-250 untouched. Checking main alone is not enough to pick a free id — PR #329's branch already carried INT-254 and INT-255 in its own issues.yaml.
- LOOP_STATUS: CONTINUE

## 2026-08-29 — INT-254 merged (PR #329)
- DSL/life-threat reconciliation: tense_anchor is a slot reference, and validate_packs stops raising.
- LOOP_STATUS: CONTINUE

## 2026-08-30 — INT-032 merged (PR #362)
- openEHR export tier against a live ehrbase 2.35.1: ensure_template (idempotent, byte-for-byte, 409 = present), write/read composition, contribution audit. Both acceptance lines met; 35 unit + 8 integration tests.
- THE EXPORT CARRIES NO CLINICAL CONTENT, and that is the finding rather than a shortcut. previsit_intake.v1.opt holds archetype ROOTS only; a root path addresses an ENTRY, not a datum, and no committed source states a leaf path. session_composition refuses every answered slot — the intended fail-closed state. A grep test proves no atNNNN is invented anywhere, and a second test reads packages/protocols/base/intake.yaml directly so the premise cannot rot silently. HB-C12 needs a clinical-informatics author plus the physician of record.
- SECOND FINDING, filed as INT-257: the committed template cannot be uploaded to a real CDR at all — no root carries <occurrences> and EHRbase answers 500. The roundtrip is green only because the test patches the bytes first. Choosing a tighter cardinality is a modelling decision nobody has taken.
- LOOP_STATUS: CONTINUE
