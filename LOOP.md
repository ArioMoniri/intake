# LOOP — autonomous iteration protocol (one issue → one PR per run)
Inputs read every iteration: CLAUDE.md, files/00_STATE.md, files/HUMAN_BLOCKERS.md, docs/backlog/issues.yaml, docs/backlog/blockers.md, docs/PROGRESS.md (last 5 entries), docs/adr/ (titles), open PRs (`gh pr list`).
1. Select: first issue in file order (phase P0→P3) with `status: todo`, all `depends_on` satisfied, and no `blocked:*` label. `awaiting-human` **satisfies** a dependency for an issue that depends only on the non-gated part of it — this is deliberate, and without it 58 % of the backlog silently never becomes Ready. If none todo and no open PRs → `LOOP_STATUS: DONE`; if only blocked/awaiting-human remain → `LOOP_STATUS: WAITING_HUMAN` with the exact list and the HUMAN_BLOCKERS.md ids.
2. Mark `status: doing`; `gh issue edit` → In progress; branch `int-<n>-<slug>`.
3. Restate the acceptance criteria verbatim in the PROGRESS entry; write the test plan; create docs/evidence/INT-xxx.md.
4. TDD: failing tests → record the red run → implement minimally → record the green run → refactor → `make check` → `make safety` → `make security`.
5. Update every doc the change touches — blueprint sections, runbooks, the metrics catalogue, legal annotations — and `00_STATE.md` in the same commit as any decision. Update issues.yaml `status: done` + `evidence:`.
6. Commit (Conventional Commits; the message says what changed and why). Push. `gh pr create` with the template filled (issue link, `10 §9` row, legal codes, evidence).
7. Merge policy: all gates green **and** no `approval:human-*`, `live-smoke` or `gpu` label → `gh pr merge --squash`; close the issue. Otherwise leave the PR open, set `status: awaiting-human`, append the ask to docs/backlog/blockers.md with the named human, the one sentence they must answer, and the HUMAN_BLOCKERS.md id — then continue with the next issue.
8. Append the PROGRESS entry. Print `LOOP_STATUS: CONTINUE`.
Blocked: two honest attempts failing, or a missing key/hardware/decision → label the issue `blocked:<what>`, write blockers.md, `status: blocked`, continue with the next issue. **Do not stop the loop for one blocker; stop only when nothing is workable.**
Never: close an issue on mocks, weaken a gate, skip a test, reduce acceptance, batch issues into one PR, invent a clinical value, or build a bypass around an open blocker.
Guardrails: never edit CLAUDE.md, LOOP.md, DoD.md, TDD.md, coverage thresholds, red-flag semantics, the Talker tool list, CI security gates, or `packages/intake_platform/{health,security}` inside the loop; never delete tests; never skip `make safety` or `make security`; never touch `.env` or OpenBao policies; never run destructive git commands; never `git add -A`.

## PROGRESS entry template
### <ISO datetime> · <task id> · <status>
- Goal:
- Plan:
- Tests added (with the near-miss negative for any safety rule):
- Result (`make check` / `make safety` / `make security` summary):
- Invariants touched and still passing:
- Decisions / ADRs / `00_STATE.md` rows:
- Blocked on (human + one sentence + HUMAN_BLOCKERS id):
- Next:
- LOOP_STATUS: CONTINUE|DONE|BLOCKED|WAITING_HUMAN
