# Blockers — what is waiting on a named human

> Format (LOOP.md step 7): one row per ask. `HUMAN_BLOCKERS.md` is the register
> of record — every row here cross-references its HB id. A row leaves this file
> when the HB row closes, never because a workaround was found.

| issue | status | who | the one sentence they must answer | HB id |
|---|---|---|---|---|
| INT-001 | awaiting-human (container evidence) | owner | Free 80–100 GB of disk and raise Docker RAM so `make dev` + the obs/security tiers can run — 18 GiB free and 14.1 GB Docker RAM today. | HB-I1, HB-I2 |
| INT-038 | awaiting-human (consent texts; mechanism shipped, fails closed) | owner + counsel (via INT-210) | Author the eleven Turkish açık rıza texts (core, voice, wellbeing, lane:affect, lane:linguistic, documents, learning:personal, learning:service_improvement, satisfaction, share, research) into `docs/legal/consents/` in the loader contract (`---` / `consent_text_version: <v>` / `---` / copy; filename = purpose with `:`→`.` + `.tr.md`) — until then every NEW grant refuses fail-closed (ConsentTextMissingError) and the dev tier runs on unbound seed grants only. | HB-L27 |
| INT-210 | awaiting-human (the whole legal document set; mechanism shipped, every gate closed) | Turkish counsel (KVKK / health-law), instructed by the owner | Author the twenty-one Turkish documents of `docs/legal/` — the five per-channel aydınlatma metinleri (app, kiosk, clinician, admin, web), the eleven açık rıza texts, the gizlilik politikası, the kullanım koşulları, the KVKK başvuru formu, the çerez politikası and the files/06 §7 fixed strings — each with its plain-language summary, and record your sign-off (name, date, `docs/evidence/INT-210.md#counsel-sign-off`) into `docs/legal/documents.yaml`, because until a row is signed every document in the set is unservable, no new consent can be granted and no acceptance can be recorded. | HB-L27 |
| INT-016 | awaiting-human (anchor destination; verifier shipped, fails closed) | owner | Which organisation's object store, or which named Turkish TSP, receives the hourly audit-chain head — and who signs that arrangement? Until one is named the verifier has nothing independent to check against, so it sets `sec_audit_chain_ok` 0 and exits 3 rather than reporting a chain that merely agrees with itself. | HB-I12 |
| INT-016 | awaiting-human (production WORM target) | owner | Accept MinIO with a documented CVE-watch and a paid-support escape hatch, or move audit WORM to a purpose-built target — Garage implements no S3 Object Lock and would void the 10-year guarantee silently? Dev/CI WORM is proven server-side; production has no configured target. | HB-I9 |
| INT-260 | awaiting-human (persistence basis; mechanism shipped, device-local, no egress) | DPO / counsel owner via HUMAN_BLOCKERS | May text scale, theme, on-screen motion and visit start-mode persist device-locally under {category: device preference, purpose: accessibility, basis: contract, retention: until uninstall or reset, recipients: none}? — the record lives in this device's keychain slot with WHEN_UNLOCKED_THIS_DEVICE_ONLY, so it is excluded from backups and never syncs; returning every control to its default deletes it. | — (no HB row exists for device-local preference persistence; raise one if the answer is anything other than yes) |
| INT-230 | awaiting-human (no study exists; pipeline shipped, fails closed) | owner + counsel, after HB-L1 | Record the KAEK decision for our study into `packages/intake_platform/src/intake_platform/research/study_registry.yaml` — `ethics_approval_id` (the decision id for OUR study, not the committee's own `2025-KAEK-51`), `approval_date`, `approval_valid_until` (enforced with no grace day), `protocol_version` and the closed `recipients` list — because until one row exists every research export refuses `UnknownStudyError`. | HB-R1 (site: HB-L1) |
| INT-230 | awaiting-human (retention; the second, independent refusal) | owner + counsel (via INT-212) | State the retention period for `research_extracts` from the ethics protocol, because files/06 §3 says only "per ethics protocol" and the export gate refuses to create data whose destruction date nobody can state. | HB-I8 |
| INT-230 | awaiting-human (legal basis of the export itself) | Turkish counsel | Confirm whether a consented, pseudonymised research export is lawful under KSVY m.16 — and under which limb — given that m.16(1) requires anonymisation and this pipeline produces a keyed pseudonym, so nothing may be described as anonymised until you answer. | HB-L26 |
| INT-113, INT-114 | awaiting-human (no lawful basis; the lane framework refuses them fail-closed) | counsel + owner | Which consent purpose do the `asr_quality` and `engagement` observer lanes run under — `core`, `voice`, or a new purpose added to files/06 §2 with its own Turkish text — given that files/03 §4.7 says every lane is its own purpose while files/06 §2's closed list names only `lane:affect` and `lane:linguistic`? Until you answer, `LaneRuntime.admit` raises `LaneConsentUndeclared` for both lanes rather than attaching them to a basis nobody chose. | HB-L22 |
| INT-112 | awaiting-human (lexicon content; the mechanism ships and fails closed) | physician of record (Dr Efe Onganer) + a Turkish-speaking clinical psychologist | Which Turkish surface forms belong in each of the four marker lexicons — `negative_affect`, `hopelessness`, `anhedonia`, `somatic_worry` — and against which committed Turkish source? Until you answer, all four are `draft_needs_source` with no terms, `compile_lexicon` refuses them, and the lane emits timing statistics and no lexicon key at all. | HB-C16 |
| INT-112, INT-116 | awaiting-human (crisis content AND its destination) | physician of record + counsel | Which Turkish phrases must trigger a consent-independent crisis response, and is that response deterministic **signposting** (`04 §4.2` defect 3: "not a screener, not a score") or an instrument cascade (the INT-112 backlog line's "C-SSRS path", which is licence-BLOCKED and which `03 §4.7.1` puts under `device_functions`)? Until you answer, `CrisisBypass` refuses to build at all rather than never firing silently. | HB-C17 (with HB-C8, HB-L2) |
| INT-112, INT-084 | awaiting-human (renderability, not computation) | physician of record + the clinician-copy owner | What are the Turkish population reference ranges for speech rate, articulation rate and pause ratio — or is the `03 §4.7.6` "Konuşma özellikleri" block not rendered to a clinician at all? The measures are computed; printing one beside no reference range is the accuracy-claim failure mode invariant 20 exists for. | HB-C18 |
| INT-095 | awaiting-human (model provenance; adapters ship, PHI gate fails closed) | owner | Read the raw LICENSE blob at a pinned revision and hash the mirrored weight files for `qwen3.5-9b` (files/03 §4.9.1 row 7) and `whisper-tr-medical` (row 2), so their `observability/registry.yaml` rows carry `model_id@revision` + `weights_sha256` + `licence_verified_at` + the blob url and sha — because row 7 records its blob reading in prose and row 2 records `UNVERIFIED`, and `require_phi_path_pin` therefore refuses both for the PHI path. | HB-I10 |
| INT-095 | awaiting-human (row 1 unobtained; the ASR adapter ships and runs on row 2) | owner + model-stack author | Is `nvidia/nemotron-3.5-asr-streaming-0.6b` (files/03 §4.9.1 row 1, the *primary* ASR) obtained, mirrored, hashed and served — or is the row withdrawn and row 2 promoted, given that row 2's evidence is three speakers and 120 clips? | HB-I11 |
| INT-095 | awaiting-human (on-hardware evidence; a real turn ran, on a dev bridge) | owner (procurement) | The acceptance closes only on a real turn **on the target GPU**; there is no pilot card and no signed capacity contract, so `make live-smoke` records `target=dev-bridge` and the issue stays open. | HB-I4, HB-I5 |
| INT-121 | awaiting-human (no corpus; the harness ships and refuses) | owner, with the DPO/counsel | Which named, dated, licensed set of Turkish documents is the records eval corpus, and on which machine or store does it live — given that a lab report is a patient record and `06 §5` forbids PHI in this repository and in CI, so it may not be committed here? Until you answer, `records_corpus_root()` refuses, `LoincUnitMeasurement` cannot be built without a named corpus and two dates, and no accuracy figure exists anywhere. | HB-A13 (with HB-A10, HB-A2) |
| INT-121, INT-124 | awaiting-human (unit expectations; the guard ships and reports itself unchecked) | physician of record (**Dr Efe Onganer**) with a clinical biochemist | For which analytes, in which unit, and against which committed Turkish source, should ingestion check a printed unit token — given that `03 §4.9.6`'s own worked examples are two published Turkish handbooks that printed the unit wrong by 1000x, so the document cannot be its own authority? The guard flags and never converts; with no expectation authored it checks nothing, and every analyte it did not check is named in `units_unchecked` rather than passing silently. | HB-C24 |
| INT-136 | awaiting-human (ordinal anchors; the overlay ships and reports itself not-ready) | physician of record (**Dr Efe Onganer**) | Under `overlay.low_literacy`, which three or four Turkish ordinal anchors stand in for the eleven-point pain score — or is the numeric scale simply not asked of a patient running that overlay, given that files/02 §3 requires severity to be **numeracy-free** and `packages/protocols`' own base layer records that no anchor wording is authored for either end of that scale? | — (no HB row; ids move under concurrent merges, so the coordinator should allocate one) |
| INT-160 | note (mechanism shipped; registry empty and refusing) | owner + counsel (DPA), `platform_owner` (approval), owner (OpenBao) | Register the first connector destination — which hospital endpoint, under which executed DPA, approved by which recorded tier-3 decision, with the application credential and the mTLS client material already written to OpenBao paths under `connectors/`, and does that hospital's agreement state that it honours an `Idempotency-Key`? Until all five exist `infra/connectors/destinations.yaml` holds zero rows and every push refuses; the fifth has no default, because an undeclared receiver turns an ambiguous outcome into a `needs_human` parking rather than an automatic retry that could duplicate a clinical record. | **HB-A15** (allocated by the coordinator; HB-A5 covers the *adapter* half — what interfaces a given hospital exposes — and this is the destination half) |
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
Filed as **HB-C22** (physician of record).

## INT-101 — the budgets have no numbers, and the cost has no price

**Raised:** 3 Sep 2026 · **Named humans:** the owner (both asks) · **HUMAN_BLOCKERS.md id: HB-O8** — allocated by the
coordinator; the two asks below are the rows verbatim, and neither is a re-ask
of an existing one.

The mechanism ships and fails closed. `intake_voice_runtime.metering` decides which
*kind* of object each budget is — a cap for extraction tokens, a target for TTS
characters, accounting for audio seconds — meters all three axes per session and per
profile, and refuses the elective model lane when no cap is declared. Nothing a patient
is owed is ever refused. What is missing is two numbers, and neither may be engineered:

**Ask 1 — the per-session limits.** files/10 §5 names the control (*"per-session
token/char/audio budgets"*) and **no file in this repository states a number for it**.
`PUBLISHED_BUDGETS` therefore ships every `limit` unset with the sentence that says why,
and the consequence is deliberate: with no declared cap the elective lane is refused
outright, because an unknown budget is not a licence to spend. One sentence closes it:
*how many extraction tokens and how many synthesised characters may one session spend
before the discretionary lane is cut, on the deployment we are actually buying?* It is a
spend decision about hardware that does not exist yet, which is why it sits behind
**HB-I4** and **HB-I5** rather than beside them.

**Ask 2 — the price.** `cost.per_session` is denominated in USD (files/08 §4 J). Under
CLAUDE.md invariant 19 every model is self-hosted, so there is no vendor list price to
read a per-token or per-character rate off; and there is no GPU-hour rate either, because
**HB-I4** records that no card has been bought and **HB-I5** that no capacity contract
naming a provider or an SKU exists. `PriceBook` ships empty, `priced_cost` raises
`CostNotPriced` rather than returning a zero (a zero is a claim that a session was free),
no `Gauge` is declared for the name, and the catalogue row stays `planned`. One sentence
closes it: *what USD rate per token, per character and per audio second should a session
be costed at, and from which invoice or amortisation does it come?*

**Consequence for the issue.** One acceptance line of three is not met —
*"cost.per_session emitted"* — so **INT-101 stays `todo`**. The other two are met with the
mechanism rather than with numbers, which docs/evidence/INT-101.md sets out line by line.

Two smaller findings, reported rather than fixed, because closing either means minting a
metric id the spec has not settled:

- **Backend extraction tokens have no catalogued series.** files/08 §4 group B's
  `voice.talker_tokens` is *the Talker's* LLM per turn; `extract_slots` is Layer B Work.
  Group J states *"tokens/chars/audio-seconds by vendor"* **without an id**, and the
  catalogue's own trailing comment already records that row as id-less. The ledger counts
  them; no series carries them.
- **`voice.stt_audio_s` has no source in this tree.** Nothing in `services/voice-runtime`
  sees patient audio — the Talker is handed transcripts, and the ASR adapter takes opaque
  bytes with no declared sample format. `charge_audio_seconds` therefore takes a *measured*
  duration and has no byte-length overload, because a duration inferred from a guessed
  sample rate would be an invented number about a recording CLAUDE.md invariant 3 says does
  not exist. The row stays `planned` until the media plane supplies a duration.

---

## INT-122 · e-Nabız export / MHRS SMS screenshot — two asks, both the owner's

Both are the same shape and neither may be engineered: **nobody on this project has seen
either source document**, and inventing what one looks like is the records-path form of
inventing a clinical value. The parsers ship and refuse; what is missing is two artefacts,
and one of them already has a HUMAN_BLOCKERS.md row that names this issue by number.

**Ask 1 — the e-Nabız PDF, and it is already filed as HB-A1.** That row states it in terms:
*"does the e-Nabız PDF have a **text layer** or is it a scanned image, and does it
**normalise units**?"*, both UNVERIFIED, obtainable only from an authenticated e-Devlet
citizen login, with the standing instruction *"Do not assume a text layer"* — and it names
what it blocks as *"INT-122's acceptance; the OCR-vs-text-extraction fork in `03 §10`"*.
Nothing is re-asked here. What this issue adds to the row is that the fail-closed shape is
now built: the table parser reads `TextRegion[]` and is agnostic to which seam produced
them, so the answer changes which seam is wired and changes no line of the parser.

**Ask 2 — one redacted MHRS appointment SMS, and its printed date order.** One sentence
closes it: *what does an MHRS appointment SMS actually say, and does it print the date as
`gg.aa.yyyy` or in some other order?* Two consequences today, both fail-closed rather than
guessed:

- **No message shape is encoded anywhere in this change.** There is no label vocabulary, no
  field order and no regex over a body layout, because writing one would be describing a
  message nobody has read. Values are recognised by their own shape and against committed
  vocabularies — the branch against `packages/protocols/taxonomy/branches.yaml`, the date
  against the printed-date guard — which is the only recognition that does not require
  having seen the message. The cost is that a field an SMS states in a form neither of
  those recognises comes back empty and named, rather than read.
- **`parse_mhrs_sms` passes no `order`**, so a printed date whose day and month are both
  ≤ 12 is refused outright — a little under half of all dates. `DateOrder` exists as the
  seam and has **no default and no `TURKISH` member**: a default would be one engineer
  choosing once, for every future patient, between two readings a month apart. The wrong
  choice sends a patient to the hospital on the wrong day and there is no diff that makes
  it look wrong.

The **HUMAN_BLOCKERS.md id for Ask 2 is for the coordinator to allocate** rather than minted
here; Ask 1 needs no id, it is HB-A1.

**Consequence for the issue.** One acceptance clause of three is fully met — *"no scraping
of e-Nabiz … legal note enforced"*, and mechanically rather than by assertion — so
**INT-122 stays `todo`**. `docs/evidence/INT-122.md` sets the line out clause by clause.

Two findings, reported rather than fixed:

- **`files/02 §3`'s *"Hekiminize ne iletildi"* bullet still cites the repealed KSVY m.10.**
  `files/06 §1` flags it in those words — *"Flagged rather than edited, because `02` is not
  this file's to change"* — and 00_STATE §2 marks the class of error *"Fix before any legal
  review"*. INT-122's own backlog row carried the same citation and **is** corrected here
  (to `KSVY-5,KSVY-6`) with a test pinning it, because that row is this issue's.
- **A visit has no time.** `VisitCreate.date` is an ISO date string and the store has no
  time column, so an appointment *time* read off a screenshot has nowhere to go. The
  candidate and the confirmed reading both carry it — dropping it silently would leave a
  patient unable to check the one field they remember — and `as_visit_fields()` carries only
  what the API has a field for. Giving the visit a time is a schema change and an issue of
  its own; no id is minted for it here.

---

## INT-161 · A FHIR push has nowhere to smoke against, and a SMART row costs four facts HB-A15 does not name

**The ask, in one sentence each.**

**Ask 1 — a partner FHIR sandbox, and it is already covered twice.** INT-161's fourth
acceptance clause is *"live smoke against a partner sandbox recorded before close"*, and
there is no sandbox: **HB-A5** records that Acıbadem Teknoloji A.Ş.'s own interfaces are
**UNVERIFIED** — whether it exposes FHIR at all is the open question — with the standing
instruction not to size the connector or promise a payload shape until that conversation
happens; **HB-A15** records that no destination exists at all (no executed DPA, no recorded
tier-3 approval, no OpenBao credential path, no `receiver_idempotency` declaration). A live
smoke needs all of that before it needs a test. **Nothing is re-asked here** and no id is
minted for it: it is HB-A5 plus HB-A15.

**Ask 2 — the four SMART facts, which HB-A15 does not name.** HB-A15's five facts are all
**mTLS-shaped** (`dpa_ref`, `approval_ref`, `credential_ref`, `client_cert_ref`,
`receiver_idempotency`). A `smart_backend_services` destination needs four more, and none
is an engineer's to supply:

| field | what it asserts | who |
|---|---|---|
| `token_host` + `token_path` | the hospital's SMART **authorization server**, registered out-of-band. It is a *second host* and it is never discovered: reading `/.well-known/smart-configuration` would let the receiver nominate where our client credential is sent | owner, from the hospital |
| `client_id` (OpenBao) | the client identifier that hospital issued us at registration | owner, from the hospital |
| the registered **public key** | the public half of the signing key must already be registered with the hospital (JWKS or by-value); the private half goes to OpenBao under `connectors/` | owner (OpenBao) + the hospital |
| `smart_scope` | the `system/...` scope that hospital's DPA actually grants, e.g. `system/Bundle.c` — the token request asks for exactly this and a grant that does not cover it stops the push | owner + counsel, from the DPA |

**The HUMAN_BLOCKERS.md id for Ask 2 is for the coordinator to allocate** rather than minted
here; Ask 1 needs no id, it is HB-A5 and HB-A15.

**Consequence for the issue.** Three acceptance clauses of four are met, mechanically rather
than by assertion, so **INT-161 stays open** at `status: awaiting-human`.
`docs/evidence/INT-161.md` §7 sets the line out clause by clause, including the one limit
worth stating on the clause that *is* met: the HAPI contract tests are recorded fixtures and
no HAPI container is run, because a container would prove our client against *a* FHIR
server rather than against *the partner's* — which is precisely what HB-A5 says is unknown.

**Nothing is built around either blocker.** The registry still holds zero rows, every push
still refuses, and the SMART path fails closed at each of its own gates: an unregistered
token host is refused by the egress guard, an unloadable key never reaches the wire, and a
grant narrower than the row declares stops the push before a byte of the bundle leaves.

## INT-019 — two CI gates are wired to a workflow file this session may not edit

**Raised:** 3 Sep 2026 · **Named human:** owner · **HUMAN_BLOCKERS id:** HB-O6

`.github/workflows/security.yml` is hook-protected, so INT-019 could diagnose the `gitleaks`
and `vulnerabilities` failures and fix neither. Three one-line edits, all proven rather than
guessed, all written out verbatim in HB-O6 and in docs/evidence/INT-019.md: the `gitleaks`
job's missing `pull-requests: read`, the osv-scanner action path plus its removed `--skip-git`
flag, and `trivyignores: .trivyignore.yaml` on the trivy step.

**What is NOT the cause, so it is not re-investigated:** gitleaks does not need a
`GITLEAKS_LICENSE` — the action logs *"[ArioMoniri] is an individual user. No license key is
required"* before it crashes — and it does not need a version bump. It needs the
`pull-requests: read` scope that the workflow's top-level `permissions: contents: read`
takes away.

**Why (c) exists at all:** trivy 0.74 auto-detects the plain-text `.trivyignore` and not the
YAML form, so a PURL-scoped ignore row is inert unless the path is passed explicitly. The row
had been drafted in the INT-019 worktree, never committed and never exercised, so it did
nothing — `make security` now passes `--ignorefile` and a test pins that, but the CI side
needs the action input.

**What lands the moment (b) is applied:** the `vulnerabilities` job starts working and
immediately reports 8 real npm advisories (1 Critical, 3 High) that no gate in this repo has
ever run against. That is the gate doing its job on a tree that has never been scanned, not a
regression from INT-019. Bumping `vitest`, `vite`, `uuid`, `esbuild` and `decode-uri-component`
is a `pnpm-lock.yaml` change that races every open branch and needs its own issue.
