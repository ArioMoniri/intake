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
