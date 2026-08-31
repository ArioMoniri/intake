# Blockers — what is waiting on a named human

> Format (LOOP.md step 7): one row per ask. `HUMAN_BLOCKERS.md` is the register
> of record — every row here cross-references its HB id. A row leaves this file
> when the HB row closes, never because a workaround was found.

| issue | status | who | the one sentence they must answer | HB id |
|---|---|---|---|---|
| INT-001 | awaiting-human (container evidence) | owner | Free 80–100 GB of disk and raise Docker RAM so `make dev` + the obs/security tiers can run — 18 GiB free and 14.1 GB Docker RAM today. | HB-I1, HB-I2 |
| INT-038 | awaiting-human (consent texts; mechanism shipped, fails closed) | owner + counsel (via INT-210) | Author the eleven Turkish açık rıza texts (core, voice, wellbeing, lane:affect, lane:linguistic, documents, learning:personal, learning:service_improvement, satisfaction, share, research) into `docs/legal/consents/` in the loader contract (`---` / `consent_text_version: <v>` / `---` / copy; filename = purpose with `:`→`.` + `.tr.md`) — until then every NEW grant refuses fail-closed (ConsentTextMissingError) and the dev tier runs on unbound seed grants only. | — (legal-text authoring is INT-210's deliverable; no HB row exists for it) |
| INT-260 | awaiting-human (persistence basis; mechanism shipped, device-local, no egress) | DPO / counsel owner via HUMAN_BLOCKERS | May text scale, theme, on-screen motion and visit start-mode persist device-locally under {category: device preference, purpose: accessibility, basis: contract, retention: until uninstall or reset, recipients: none}? — the record lives in this device's keychain slot with WHEN_UNLOCKED_THIS_DEVICE_ONLY, so it is excluded from backups and never syncs; returning every control to its default deletes it. | — (no HB row exists for device-local preference persistence; raise one if the answer is anything other than yes) |
| INT-230 | awaiting-human (no study exists; pipeline shipped, fails closed) | owner + counsel, after HB-L1 | Record the KAEK decision for our study into `packages/intake_platform/src/intake_platform/research/study_registry.yaml` — `ethics_approval_id` (the decision id for OUR study, not the committee's own `2025-KAEK-51`), `approval_date`, `approval_valid_until` (enforced with no grace day), `protocol_version` and the closed `recipients` list — because until one row exists every research export refuses `UnknownStudyError`. | HB-R1 (site: HB-L1) |
| INT-230 | awaiting-human (retention; the second, independent refusal) | owner + counsel (via INT-212) | State the retention period for `research_extracts` from the ethics protocol, because files/06 §3 says only "per ethics protocol" and the export gate refuses to create data whose destruction date nobody can state. | HB-I8 |
| INT-230 | awaiting-human (legal basis of the export itself) | Turkish counsel | Confirm whether a consented, pseudonymised research export is lawful under KSVY m.16 — and under which limb — given that m.16(1) requires anonymisation and this pipeline produces a keyed pseudonym, so nothing may be described as anonymised until you answer. | HB-L21 |
| licensing | note (non-blocking) | owner | Confirm the split "Apache-2.0 for packages/protocols, proprietary for everything else" (07 §4) — bootstrapped that way pending your word. | — |

## INT-254 — no CODEOWNERS file, so the protocols review requirement has no mechanism

**Raised:** 29 Aug 2026 · **PR:** #329 (open, all four CI checks green) · **Named human:** owner

CLAUDE.md, Clinical content rules: *"Any change under `packages/protocols/**` requires: golden tests updated with a near-miss negative control, `make safety` green, CODEOWNER review."* The first two are met on #329. The third cannot be: **`.github/CODEOWNERS` does not exist**, and `main` carries no branch protection, so no review is requested, required or recorded on any protocols PR — including every one already merged (INT-040, INT-041, INT-042, INT-043, INT-060).

**The one sentence the owner must answer:** who is the CODEOWNER for `packages/protocols/**` and `files/protocols/**`, and should `.github/CODEOWNERS` plus branch protection be created so the requirement is enforced rather than stated?

This is not INT-254's content to fix and it does not block the work, which is complete and green. It blocks only the *merge decision*, and it is recorded here because the requirement is currently unenforceable repo-wide rather than just on this PR. Related: the same PR found that `make check-golden` and `make security` are named in CLAUDE.md and absent from the Makefile, and that of the invariant-14 scanner set only gitleaks and semgrep run — as pre-commit hooks, not in `ci.yml`.

## INT-202 — the restore drill refuses, by name, and that is the correct state

**Raised:** 30 Aug 2026 (the row was owed by INT-202's own evidence and never written) · **Named human:** owner, with counsel via INT-212 · **HUMAN_BLOCKERS id:** HB-I8

The drill was **run**, not reasoned about: `scripts/backup/restore_drill.sh --run` prints its plan and then refuses — *"no backup retention window is configured … Set `PGBACKREST_REPO1_RETENTION_FULL` once the owner answers files/HUMAN_BLOCKERS.md HB-I8 — a guessed window is not a default."* Behind that sits a host preflight that refuses again on HB-I1 (disk) and HB-I2 (container memory).

So the mechanism is built and fails closed by name, and `tests/infra/test_restore_drill.py` passes 72 tests — but read what they pin: config parsing, `repo1-cipher-type=aes-256-cbc`, credential-literal scans, the replication plan, the compose tier's static shape, the PHI-safety refusals, the preflight, the `--dry-run` path and eleven near-miss negative controls. **The restore itself is never exercised**, no drill output exists in the tree, and there is no quarterly workflow (the cron is in `docs/runbooks/restore-drill.md`, which states plainly that the workflow needs `runs-on: [self-hosted, tr-dc]` — HB-I7).

**The one sentence the owner must answer** is HB-I8's, unchanged: *(a) how many full backups does the pgBackRest repository keep, and for how long is the WAL archive retained — a KVKK-7 / DEST-2017 question, since a backup outlives the crypto-shredding it is subject to; and (b) what is the named second location in Türkiye?*

Nothing depends on INT-202, so this costs no roadmap throughput. It is recorded because the acceptance's own words are *"RPO 15 min / RTO 4 h **demonstrated** in a drill script whose output is stored as evidence"*, and a drill that has never completed has not demonstrated anything.

## INT-020 — the mechanism is done; the four notice texts are counsel's

**Raised:** 30 Aug 2026 · **Named human:** Turkish counsel, plus the owner to decide the issue split · **HUMAN_BLOCKERS id:** HB-L22

The threat model (1019 lines, one section per `sec_row`, bound both ways so a stale section fails), the incident runbook's eight sections and the PR-template Sec-Row gate are all complete and test-bound. What is missing is the acceptance's **data-subject notice templates** — legal texts, which invariant 18 renders only from `docs/legal/` with hash binding and which CLAUDE.md's stop-and-ask list reserves.

**The one sentence:** *"Do the Board-form content, the data-subject breach notice, the USOM/7545 report and the hospital DPA notice belong to INT-020 — or to INT-214, in which case INT-020's acceptance should be amended and the issue closed?"* Both answers are defensible and an agent may not pick.

## INT-085 — the readability gate reports structure and claims no reading level

**Raised:** 31 Aug 2026 · **Named human:** clinical copy owner (files/09 §2 role L2) · **HUMAN_BLOCKERS id:** HB-C17

The acceptance asks for a "readability metric gate". A metric was deliberately **not** chosen. Flesch–Kincaid is an English formula and Turkish is agglutinative, so applying it and reporting the result as a B1 level would be a fabricated measurement — precisely what invariant 20 exists to stop. `grep -in "readab\|okunab"` over `files/` returns nothing, so the blueprint names no formula either.

What ships instead is five **structural** checks that block a release — sentence length, one idea per sentence, the `sen` register, jargon without a gloss, and `-iniz` in instructional prose with the RED inversion (`Tutun · Arayın` is correct under RED, and `-iniz` is a finding there). The length bound is not a number chosen by an agent: it mirrors `policy_guard.B1_MAX_WORDS_PER_SENTENCE`, and a test pins the two equal so they cannot drift.

`SCORED_METRICS` is empty, `ReadabilityMetric` refuses any row without a committed `formula_source`, and `ReadabilityReport.asserts_b1_level` is permanently `False`. **The gate reports structure and claims no level.**

**The one sentence:** *"Which published Turkish readability formula does patient copy get measured against, what is its B1 cut-off, and against which committed, dated snapshot of that formula do we read it?"*

This blocks nothing — the structural gate is live and fails closed on authored copy.

## INT-019 — the security workflow is written and one protected `git mv` from installed

**Raised:** 31 Aug 2026 · **Named human:** owner · **HUMAN_BLOCKERS id:** HB-I9 (related, not identical)

`.github/workflows/security.yml` is **hook-protected** by `scripts/hooks/guard-protected-files.sh`. The agent respected the guard rather than routing around it through Bash — the guard *is* the permission system, and an instruction from a caller is not the `ALLOW_PROTECTED=1` sanction it asks for. That is the correct behaviour and it is why the file is not in place. It refused PR #233 in August for the same reason.

The byte-final workflow is committed at `scripts/ci/security_workflow.yml`, and `tests/ci/test_security_gates.py::test_workflow_is_installed` stays **RED** until it moves.

**The one command the owner must run:**

```
ALLOW_PROTECTED=1 git mv scripts/ci/security_workflow.yml .github/workflows/security.yml
```

Note this is *separate from* HB-I9: clearing the Actions billing makes the workflow **run**; this `git mv` makes it **exist**. Neither substitutes for the other, and until both are done `make security` locally is the only security gate this repo has.

**Also needing a human, from the same issue:**
- `infra/ci/no-phi-policy.yaml`'s `artefact_paths` is empty, so the workflow uploads nothing rather than evading a gate. The exact YAML is in the evidence.
- Three debt baselines record pre-existing findings (eslint-security 272, bandit 4, checkov 3). Every rule stays at `error` and a new finding fails. **The one worth looking at first is `detect-unsafe-regex` in `apps/mobile/src/lib/telemetry/scrub.ts`** — a backtracking regex in a redaction path is a denial-of-service reachable from patient text.

**Correction — there is no second protected file.** An earlier revision of this section claimed `.pre-commit-config.yaml` was denied by the session's permission layer and that INT-019's two commit hooks were therefore unwired. That was wrong: the denials were of the *compound command form* I used, not of the path, and a plain `git add -- .pre-commit-config.yaml` succeeds. The `phi-scan` and `claims-scan` hooks are wired and committed. Only `.github/workflows/security.yml` is genuinely hook-protected, and only the `git mv` above is owed.
