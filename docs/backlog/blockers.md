# Blockers — what is waiting on a named human

> Format (LOOP.md step 7): one row per ask. `HUMAN_BLOCKERS.md` is the register
> of record — every row here cross-references its HB id. A row leaves this file
> when the HB row closes, never because a workaround was found.

| issue | status | who | the one sentence they must answer | HB id |
|---|---|---|---|---|
| INT-001 | awaiting-human (container evidence) | owner | Free 80–100 GB of disk and raise Docker RAM so `make dev` + the obs/security tiers can run — 18 GiB free and 14.1 GB Docker RAM today. | HB-I1, HB-I2 |
| INT-038 | awaiting-human (consent texts; mechanism shipped, fails closed) | owner + counsel (via INT-210) | Author the eleven Turkish açık rıza texts (core, voice, wellbeing, lane:affect, lane:linguistic, documents, learning:personal, learning:service_improvement, satisfaction, share, research) into `docs/legal/consents/` in the loader contract (`---` / `consent_text_version: <v>` / `---` / copy; filename = purpose with `:`→`.` + `.tr.md`) — until then every NEW grant refuses fail-closed (ConsentTextMissingError) and the dev tier runs on unbound seed grants only. | — (legal-text authoring is INT-210's deliverable; no HB row exists for it) |
| INT-016 | awaiting-human (anchor destination; verifier shipped, fails closed) | owner | Which organisation's object store, or which named Turkish TSP, receives the hourly audit-chain head — and who signs that arrangement? Until one is named the verifier has nothing independent to check against, so it sets `sec_audit_chain_ok` 0 and exits 3 rather than reporting a chain that merely agrees with itself. | HB-I8 |
| INT-016 | awaiting-human (production WORM target) | owner | Accept MinIO with a documented CVE-watch and a paid-support escape hatch, or move audit WORM to a purpose-built target — Garage implements no S3 Object Lock and would void the 10-year guarantee silently? Dev/CI WORM is proven server-side; production has no configured target. | HB-I9 |
| INT-260 | awaiting-human (persistence basis; mechanism shipped, device-local, no egress) | DPO / counsel owner via HUMAN_BLOCKERS | May text scale, theme, on-screen motion and visit start-mode persist device-locally under {category: device preference, purpose: accessibility, basis: contract, retention: until uninstall or reset, recipients: none}? — the record lives in this device's keychain slot with WHEN_UNLOCKED_THIS_DEVICE_ONLY, so it is excluded from backups and never syncs; returning every control to its default deletes it. | — (no HB row exists for device-local preference persistence; raise one if the answer is anything other than yes) |
| INT-230 | awaiting-human (no study exists; pipeline shipped, fails closed) | owner + counsel, after HB-L1 | Record the KAEK decision for our study into `packages/intake_platform/src/intake_platform/research/study_registry.yaml` — `ethics_approval_id` (the decision id for OUR study, not the committee's own `2025-KAEK-51`), `approval_date`, `approval_valid_until` (enforced with no grace day), `protocol_version` and the closed `recipients` list — because until one row exists every research export refuses `UnknownStudyError`. | HB-R1 (site: HB-L1) |
| INT-230 | awaiting-human (retention; the second, independent refusal) | owner + counsel (via INT-212) | State the retention period for `research_extracts` from the ethics protocol, because files/06 §3 says only "per ethics protocol" and the export gate refuses to create data whose destruction date nobody can state. | HB-I8 |
| INT-230 | awaiting-human (legal basis of the export itself) | Turkish counsel | Confirm whether a consented, pseudonymised research export is lawful under KSVY m.16 — and under which limb — given that m.16(1) requires anonymisation and this pipeline produces a keyed pseudonym, so nothing may be described as anonymised until you answer. | HB-L21 |
| INT-113, INT-114 | awaiting-human (no lawful basis; the lane framework refuses them fail-closed) | counsel + owner | Which consent purpose do the `asr_quality` and `engagement` observer lanes run under — `core`, `voice`, or a new purpose added to files/06 §2 with its own Turkish text — given that files/03 §4.7 says every lane is its own purpose while files/06 §2's closed list names only `lane:affect` and `lane:linguistic`? Until you answer, `LaneRuntime.admit` raises `LaneConsentUndeclared` for both lanes rather than attaching them to a basis nobody chose. | HB-L22 |
| INT-112 | awaiting-human (lexicon content; the mechanism ships and fails closed) | physician of record (Dr Efe Onganer) + a Turkish-speaking clinical psychologist | Which Turkish surface forms belong in each of the four marker lexicons — `negative_affect`, `hopelessness`, `anhedonia`, `somatic_worry` — and against which committed Turkish source? Until you answer, all four are `draft_needs_source` with no terms, `compile_lexicon` refuses them, and the lane emits timing statistics and no lexicon key at all. | HB-C16 |
| INT-112, INT-116 | awaiting-human (crisis content AND its destination) | physician of record + counsel | Which Turkish phrases must trigger a consent-independent crisis response, and is that response deterministic **signposting** (`04 §4.2` defect 3: "not a screener, not a score") or an instrument cascade (the INT-112 backlog line's "C-SSRS path", which is licence-BLOCKED and which `03 §4.7.1` puts under `device_functions`)? Until you answer, `CrisisBypass` refuses to build at all rather than never firing silently. | HB-C17 (with HB-C8, HB-L2) |
| INT-112, INT-084 | awaiting-human (renderability, not computation) | physician of record + the clinician-copy owner | What are the Turkish population reference ranges for speech rate, articulation rate and pause ratio — or is the `03 §4.7.6` "Konuşma özellikleri" block not rendered to a clinician at all? The measures are computed; printing one beside no reference range is the accuracy-claim failure mode invariant 20 exists for. | HB-C18 |
| INT-095 | awaiting-human (model provenance; adapters ship, PHI gate fails closed) | owner | Read the raw LICENSE blob at a pinned revision and hash the mirrored weight files for `qwen3.5-9b` (files/03 §4.9.1 row 7) and `whisper-tr-medical` (row 2), so their `observability/registry.yaml` rows carry `model_id@revision` + `weights_sha256` + `licence_verified_at` + the blob url and sha — because row 7 records its blob reading in prose and row 2 records `UNVERIFIED`, and `require_phi_path_pin` therefore refuses both for the PHI path. | HB-I10 |
| INT-095 | awaiting-human (row 1 unobtained; the ASR adapter ships and runs on row 2) | owner + model-stack author | Is `nvidia/nemotron-3.5-asr-streaming-0.6b` (files/03 §4.9.1 row 1, the *primary* ASR) obtained, mirrored, hashed and served — or is the row withdrawn and row 2 promoted, given that row 2's evidence is three speakers and 120 clips? | HB-I11 |
| INT-095 | awaiting-human (on-hardware evidence; a real turn ran, on a dev bridge) | owner (procurement) | The acceptance closes only on a real turn **on the target GPU**; there is no pilot card and no signed capacity contract, so `make live-smoke` records `target=dev-bridge` and the issue stays open. | HB-I4, HB-I5 |
| INT-136 | awaiting-human (ordinal anchors; the overlay ships and reports itself not-ready) | physician of record (**Dr Efe Onganer**) | Under `overlay.low_literacy`, which three or four Turkish ordinal anchors stand in for the eleven-point pain score — or is the numeric scale simply not asked of a patient running that overlay, given that files/02 §3 requires severity to be **numeracy-free** and `packages/protocols`' own base layer records that no anchor wording is authored for either end of that scale? | — (no HB row; ids move under concurrent merges, so the coordinator should allocate one) |
| licensing | note (non-blocking) | owner | Confirm the split "Apache-2.0 for packages/protocols, proprietary for everything else" (07 §4) — bootstrapped that way pending your word. | — |

## INT-254 — no CODEOWNERS file, so the protocols review requirement has no mechanism

**Raised:** 29 Aug 2026 · **PR:** #329 (open, all four CI checks green) · **Named human:** owner

CLAUDE.md, Clinical content rules: *"Any change under `packages/protocols/**` requires: golden tests updated with a near-miss negative control, `make safety` green, CODEOWNER review."* The first two are met on #329. The third cannot be: **`.github/CODEOWNERS` does not exist**, and `main` carries no branch protection, so no review is requested, required or recorded on any protocols PR — including every one already merged (INT-040, INT-041, INT-042, INT-043, INT-060).

**The one sentence the owner must answer:** who is the CODEOWNER for `packages/protocols/**` and `files/protocols/**`, and should `.github/CODEOWNERS` plus branch protection be created so the requirement is enforced rather than stated?

This is not INT-254's content to fix and it does not block the work, which is complete and green. It blocks only the *merge decision*, and it is recorded here because the requirement is currently unenforceable repo-wide rather than just on this PR. Related: the same PR found that `make check-golden` and `make security` are named in CLAUDE.md and absent from the Makefile, and that of the invariant-14 scanner set only gitleaks and semgrep run — as pre-commit hooks, not in `ci.yml`.

## INT-084 — two note-schema decisions the composer refused to take

**Raised:** 2 Sep 2026 · **Named human:** physician of record / note-schema owner

1. **HB-C14 — may a patient-entered *measured* vital appear in the clinician note, and under which field?** INT-084 added `PreVisitNote.measurements` for the anthropometry the intake surface actually collects (height, weight) because `04 §5` had no key for it at all and INT-282 was forced to render those values into a mobile-only section. It stopped there: `02 §2` promises "vitals entry" in Detaylı while INT-282 asserted by name that pulse, blood pressure and respiration are clinician-measured rows a patient is never asked. `MeasureCode` has exactly two members and widening it is the decision.
2. **HB-C15 — confirm or overturn the note's definition of "missing".** The engine counts a `must_ask` step whose gate is TRUE *or UNKNOWN* as obliged; mobile keeps gate-TRUE only. INT-084 took the engine's definition (`NoteGapReason.UNRESOLVED_PRECONDITION` exists) because under-reporting what is absent is the dangerous direction on a checkpointed note. Live the moment INT-096 puts compiled packs behind both surfaces.

Neither blocks this issue: the mechanism ships, the enum is closed, and both choices are recorded in `docs/evidence/INT-084.md`.
| INT-208 | deferred (merge ordering, not a blocker) | coordinator | `int-200-health-connectors` carries device-local Apple Health / Health Connect and is nine source conflicts behind main, including `apps/mobile/src/lib/intake/note.ts` and its tests — which INT-084's note composer is rewriting right now. Resolving those conflicts against a file being rewritten would produce a merge nobody can review. Package it AFTER INT-084 lands, then re-resolve from the new note shape. Branch is intact at `13feef7`; nothing is lost. |

## INT-085 — one patient-facing decision the summary refused to take

**Raised:** 2 Sep 2026 · **Named human:** physician of record

**HB-C20 — may a RED patient keep a patient summary?** (filed as HB-C16; renumbered 3 Sep when INT-112 was found to hold that id) INT-085 refused to render one.
Invariant 21 makes RED three axes (route × register × location) with its script
pre-positioned on the device and triggered over the data channel; a card set is none of
those three, and a RED sentence whose register is decided by page layout is the default
the invariant forbids. So `SUMMARY_TRIAGE_LEVELS` is `(GREEN, YELLOW)`, there is no
`patient_summary.triage_message.red` key, and `build_patient_summary` raises.

**The one sentence the physician of record must answer:** should a patient whose session
produced a RED still see the "Anlattıklarınız" card set, and if so under which register?

It does not block: the RED patient still gets the RED script over the channel that has a
register, and reversing the decision is one catalogue key plus one deleted raise. Recorded
because it is a product decision taken inside an engineering issue.
| — | resolved (no action) | coordinator | **Branch names do not identify their issue.** `int-200-health-connectors` carries INT-208 (done, merged 28 Aug as PR #239) and `int-201-design-pass5` carries INT-209 (done, PrepGauge and mobile-ui.md verified present on main). Both branch names point at *unrelated* todo issues — INT-200 is the residency compose profile, INT-201 is k8s. Squash-merged branches stay ahead of `main` by reachability forever, so a commit count proves nothing. **Check the issue the branch's evidence file names, not the number in the branch name**, and confirm content presence on main before treating a branch as unmerged. Sending an agent to "rescue" INT-208 cost about an hour. **Third instance, 3 Sep:** `int-250-history-sections` carries the work that merged as **INT-256** (PR #360) — `docs/evidence/INT-256.md` on main is the same 413-line document the branch calls `INT-250.md`, and main is 513 insertions *ahead* of the branch in `questions.ts` and `note.ts`. Main's INT-250 is tenant onboarding, so landing that evidence file under its own name would have filed a mobile history-section document against a release issue. This branch has **no PR of its own**, so the merged-PR test that clears the other two does not clear it — for a branch with no PR, compare the evidence file's opening line against `docs/evidence/` on main. |

## INT-208 — the deferral filed here on 2 Sep was against work that had already merged

**Raised:** 2 Sep 2026 · **Retracted:** 2 Sep 2026 · **Named human:** none — this was never a blocker

A row was appended to this file deferring INT-208 (*"nine source conflicts behind main …
package it AFTER INT-084 lands, then re-resolve from the new note shape"*). It was wrong. It
is retracted here rather than deleted, because a deleted mistake is one that gets made again
— and this one already cost a second agent a full re-read of the branch.

**INT-208 merged on 28 Aug 2026 as PR #239 (`e9600d8`).** Every file it touched is on `main`:
`apps/mobile/src/lib/health/*` and `src/components/HealthSection.tsx` byte-identical to the
branch; the `healthLines` / `attachHealth` / `device_health` path in
`src/lib/intake/note.ts`, carried through INT-084's and INT-282's rewrites and now rendered
after the `measurements` block; every `health.*` and `consent.health*` key in `tr.ts` and
`en.ts`; the three Android health permissions and the Turkish `NSHealthShareUsageDescription`
in `app.json`; both native dependencies in `package.json` and `pnpm-lock.yaml`;
`INT-208 status: done` in `issues.yaml` and `files/11`; and the
`2026-08-28T08:00:00+03:00 · INT-208 · done` entry in `docs/PROGRESS.md`.

**How the mistake happened, and the one command that catches it.** `git merge origin/main` on
`int-200-health-connectors` really does conflict in nine source files — not because the work
is unmerged, but because the branch predates INT-084, INT-282 and several design passes that
rewrote those same files for unrelated reasons. **Conflict count measures divergence, not
unmerged content.** Resolving every conflict in main's favour yields tree `409e0431`, which
*is* `origin/main`'s tree: the branch contributes nothing. Before treating a stale branch as
unlanded work, run `git log origin/main --oneline --grep '<ID>'`.

## INT-140 — the export ANSWER cannot be delivered, so the issue stays open

**Raised:** 3 Sep 2026 · **Named human:** none new — this is INT-210's content

INT-140 delivers two of the three obligations in its acceptance line: the erasure
flow (file, grace, withdraw, tracker) and the learned-fact ledger (provenance,
per-field share scope, delete). The third — handing the patient the copy of their
record — is not delivered, and the client deliberately never calls
`GET /v1/me/dsar/export/{id}`.

Three facts make the call wrong today rather than merely unbuilt. The route marks
the KVKK m.13 obligation **completed at the moment of delivery**, so calling it
without handing anything over would record an answer nobody received. It cannot
succeed in any case: the document renders only from the hash-bound fixed strings
in `docs/legal/strings.yaml`, which does not exist, so the route answers
`503 legal_strings_missing`. And the app has no path that hands a file to a
patient — building one is a security decision needing its own files/10 §9 row and
a licence-audited dependency.

**Nothing is owed by a human that is not already owed:** INT-210 (`status: todo`,
`approval:human-legal`) owns the strings. When they land, the remaining work is
one unit — retrieval plus a delivery channel — and INT-140 closes on it.

One product finding for the **clinical copy owner**, flagged rather than fixed: an
overlay key (`chronic.hipertansiyon`) has no patient-readable Turkish label
anywhere in the repo. The ledger renders the fact's own recorded phrase where the
value is one and a catalogue label where it is not, and never the slot ref — every
other files/09 §3 promise is kept for those rows. Authoring the label vocabulary
is clinical copy against the packs' slot definitions.
| INT-296 | awaiting-human (KVKK category of a second locale; column shipped, registry holds only `tr`) | DPO / Turkish counsel (with the owner) | Under which KVKK category, lawful basis, retention and recipients does `sessions.locale` sit once a second language is offered — given that with `tr` alone the column records the service's own language and states nothing about the patient, but a language choice among several can proxy ethnic origin (m.6 special category)? | HB-L25 |

## INT-136 — instruments render verbatim, and nothing renders

**Raised:** 3 Sep 2026 · **Named human:** none new — this is HB-C1 and HB-L2/HB-L3

The typed intake's instrument half is built and fails closed. There is exactly
one route from a pack's `text_tr` to the screen; it copies nothing (proved by
byte identity against an injected instrument, with an NFD near-miss control);
the licence is checked before the content, so a fully-authored blocked
instrument is still refused; and a refusal is rendered as copy rather than as
`null`, because a step that renders nothing looks finished.

**No instrument item renders**, because none exists to render.
`apps/mobile/src/lib/intake/instruments.ts` ships `INSTRUMENT_ITEMS = {}` for
three independent reasons, none of them fixable in this repo: **HB-C1** leaves
every pack unsigned, so all 93 are `maturity: L0` and none is servable
(docs/evidence/INT-096.md F4); **HB-L2** and **HB-L3** block C-SSRS and WHO-5;
and `packages/protocols/base/intake.yaml` states the third itself — *"Instrument
ITEM text is not authored here: the verbatim Turkish items belong to the
instrument engine (INT-116)"*.

Nothing extra is owed by a human. When a pack authors a `GO` instrument,
`apps/mobile/e2e/typed_intake.spec.ts` fails until the app registry carries it
verbatim, which is how it lands. INT-136 stays `todo` meanwhile.

Separately, and this one **is** a new ask: the pain score. See the table row
above. `lowLiteracyReadiness` reports the Detaylı pack as not ready and names
`numeral_anchored:pain_score` rather than inventing a recoding, which is
HUMAN_BLOCKERS.md rule 1 applied to a scale rather than to a threshold.
