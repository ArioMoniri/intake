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
