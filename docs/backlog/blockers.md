# Blockers — what is waiting on a named human

> Format (LOOP.md step 7): one row per ask. `HUMAN_BLOCKERS.md` is the register
> of record — every row here cross-references its HB id. A row leaves this file
> when the HB row closes, never because a workaround was found.

| issue | status | who | the one sentence they must answer | HB id |
|---|---|---|---|---|
| INT-001 | awaiting-human (container evidence) | owner | Free 80–100 GB of disk and raise Docker RAM so `make dev` + the obs/security tiers can run — 18 GiB free and 14.1 GB Docker RAM today. | HB-I1, HB-I2 |
| INT-038 | awaiting-human (consent texts; mechanism shipped, fails closed) | owner + counsel (via INT-210) | Author the eleven Turkish açık rıza texts (core, voice, wellbeing, lane:affect, lane:linguistic, documents, learning:personal, learning:service_improvement, satisfaction, share, research) into `docs/legal/consents/` in the loader contract (`---` / `consent_text_version: <v>` / `---` / copy; filename = purpose with `:`→`.` + `.tr.md`) — until then every NEW grant refuses fail-closed (ConsentTextMissingError) and the dev tier runs on unbound seed grants only. | — (legal-text authoring is INT-210's deliverable; no HB row exists for it) |
| licensing | note (non-blocking) | owner | Confirm the split "Apache-2.0 for packages/protocols, proprietary for everything else" (07 §4) — bootstrapped that way pending your word. | — |

## INT-254 — no CODEOWNERS file, so the protocols review requirement has no mechanism

**Raised:** 29 Aug 2026 · **PR:** #329 (open, all four CI checks green) · **Named human:** owner

CLAUDE.md, Clinical content rules: *"Any change under `packages/protocols/**` requires: golden tests updated with a near-miss negative control, `make safety` green, CODEOWNER review."* The first two are met on #329. The third cannot be: **`.github/CODEOWNERS` does not exist**, and `main` carries no branch protection, so no review is requested, required or recorded on any protocols PR — including every one already merged (INT-040, INT-041, INT-042, INT-043, INT-060).

**The one sentence the owner must answer:** who is the CODEOWNER for `packages/protocols/**` and `files/protocols/**`, and should `.github/CODEOWNERS` plus branch protection be created so the requirement is enforced rather than stated?

This is not INT-254's content to fix and it does not block the work, which is complete and green. It blocks only the *merge decision*, and it is recorded here because the requirement is currently unenforceable repo-wide rather than just on this PR. Related: the same PR found that `make check-golden` and `make security` are named in CLAUDE.md and absent from the Makefile, and that of the invariant-14 scanner set only gitleaks and semgrep run — as pre-commit hooks, not in `ci.yml`.
