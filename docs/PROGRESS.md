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
