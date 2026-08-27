# INT-xxx: <title>

Closes #<n>

## DoD — list A (self-assessed; the full walk lives in the evidence file)

- [ ] One issue, one PR; branch `int-<n>-<slug>`; squash merge only
- [ ] docs/evidence/INT-xxx.md quotes the acceptance verbatim and records the **red run**, the **green run**, and the `make check` / `make safety` / `make security` output
- [ ] The red run is real — a test that could not have failed is a rejected PR
- [ ] Gates green from a clean clone; coverage floors met or raised, never lowered
- [ ] Invariant 17 clean (`no_placeholders` green); mocks in tests only
- [ ] No new PHI egress path — every outbound call enumerated in the evidence file
- [ ] New metrics catalogued; new services carry the monitoring contract
- [ ] Licences verified from the raw LICENSE blob for any new dependency/model (`licence_verified_at` for PHI-path rows)
- [ ] **No accuracy claim** in docs/regulatory/, docs/legal/, or user-facing copy (ADR-022)
- [ ] `tr` strings first; no `text-transform`; no mid-word truncation
- [ ] `files/10 §9` row: <row name or “—”>
- [ ] Legal codes re-read (`files/06 §1`): <codes or “—”>
- [ ] Blueprint files touched by this change updated in this PR; `00_STATE.md` row for any decision
- [ ] Commit message says what changed **and why**

## DoD — list B (cannot be self-certified; PR stays open if any applies)

- [ ] Clinical content → named licensed physician under CODEOWNERS (`approval:human-clinical`)
- [ ] Legal text / consent / intended purpose → counsel or owner (`approval:human-legal`)
- [ ] Vendor (`live-smoke`) or on-hardware (`gpu`) evidence
- [ ] HUMAN_BLOCKERS.md rows touched: <ids or “—”>

## Evidence

docs/evidence/INT-xxx.md
