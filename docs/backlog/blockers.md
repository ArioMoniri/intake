# Blockers — what is waiting on a named human

> Format (LOOP.md step 7): one row per ask. `HUMAN_BLOCKERS.md` is the register
> of record — every row here cross-references its HB id. A row leaves this file
> when the HB row closes, never because a workaround was found.

| issue | status | who | the one sentence they must answer | HB id |
|---|---|---|---|---|
| INT-001 | awaiting-human (container evidence) | owner | Free 80–100 GB of disk and raise Docker RAM so `make dev` + the obs/security tiers can run — 18 GiB free and 14.1 GB Docker RAM today. | HB-I1, HB-I2 |
| INT-038 | awaiting-human (consent texts; mechanism shipped, fails closed) | owner + counsel (via INT-210) | Author the eleven Turkish açık rıza texts (core, voice, wellbeing, lane:affect, lane:linguistic, documents, learning:personal, learning:service_improvement, satisfaction, share, research) into `docs/legal/consents/` in the loader contract (`---` / `consent_text_version: <v>` / `---` / copy; filename = purpose with `:`→`.` + `.tr.md`) — until then every NEW grant refuses fail-closed (ConsentTextMissingError) and the dev tier runs on unbound seed grants only. | HB-L27 |
| INT-210 | awaiting-human (the whole legal document set; mechanism shipped, every gate closed) | Turkish counsel (KVKK / health-law), instructed by the owner | Author the twenty-one Turkish documents of `docs/legal/` — the five per-channel aydınlatma metinleri (app, kiosk, clinician, admin, web), the eleven açık rıza texts, the gizlilik politikası, the kullanım koşulları, the KVKK başvuru formu, the çerez politikası and the files/06 §7 fixed strings — each with its plain-language summary, and record your sign-off (name, date, `docs/evidence/INT-210.md#counsel-sign-off`) into `docs/legal/documents.yaml`, because until a row is signed every document in the set is unservable, no new consent can be granted and no acceptance can be recorded. | HB-L27 |
| INT-221 | awaiting-human (Genelge 2019/12 attestation; mechanism shipped, legal content empty, fails closed) | Turkish counsel (KVKK / health-law), instructed by the owner | Is the in-country, vendor-free posture legally *attestable* under KVKK Art. 9 (physical vs legal residency; control-plane siting), and — once you rule it is — author and sign the Turkish attestation statement for Genelge 2019/12? Until then `GenelgeResidencyAttestation` carries the machine-checkable vendor-free conformance but its legal statement and signatory are empty and `render()` refuses (`AttestationUnsigned`). The registry assertion, the DDO Rehber control mapping doc and the USVS conformance suite all ship and pass; only the legal attestation is blocked. | HB-L11 (signature regime: HB-L27) |
| INT-016 | awaiting-human (anchor destination; verifier shipped, fails closed) | owner | Which organisation's object store, or which named Turkish TSP, receives the hourly audit-chain head — and who signs that arrangement? Until one is named the verifier has nothing independent to check against, so it sets `sec_audit_chain_ok` 0 and exits 3 rather than reporting a chain that merely agrees with itself. | HB-I12 |
| INT-016 | awaiting-human (production WORM target) | owner | Accept MinIO with a documented CVE-watch and a paid-support escape hatch, or move audit WORM to a purpose-built target — Garage implements no S3 Object Lock and would void the 10-year guarantee silently? Dev/CI WORM is proven server-side; production has no configured target. | HB-I9 |
| INT-260 | awaiting-human (persistence basis; mechanism shipped, device-local, no egress) | DPO / counsel owner via HUMAN_BLOCKERS | May text scale, theme, on-screen motion and visit start-mode persist device-locally under {category: device preference, purpose: accessibility, basis: contract, retention: until uninstall or reset, recipients: none}? — the record lives in this device's keychain slot with WHEN_UNLOCKED_THIS_DEVICE_ONLY, so it is excluded from backups and never syncs; returning every control to its default deletes it. | — (no HB row exists for device-local preference persistence; raise one if the answer is anything other than yes) |
| INT-230 | awaiting-human (no study exists; pipeline shipped, fails closed) | owner + counsel, after HB-L1 | Record the KAEK decision for our study into `packages/intake_platform/src/intake_platform/research/study_registry.yaml` — `ethics_approval_id` (the decision id for OUR study, not the committee's own `2025-KAEK-51`), `approval_date`, `approval_valid_until` (enforced with no grace day), `protocol_version` and the closed `recipients` list — because until one row exists every research export refuses `UnknownStudyError`. | HB-R1 (site: HB-L1) |
| INT-230 | awaiting-human (retention; the second, independent refusal) | owner + counsel (via INT-212) | State the retention period for `research_extracts` from the ethics protocol, because files/06 §3 says only "per ethics protocol" and the export gate refuses to create data whose destruction date nobody can state. | HB-I8 |
| INT-230 | awaiting-human (legal basis of the export itself) | Turkish counsel | Confirm whether a consented, pseudonymised research export is lawful under KSVY m.16 — and under which limb — given that m.16(1) requires anonymisation and this pipeline produces a keyed pseudonym, so nothing may be described as anonymised until you answer. | HB-L26 |
| INT-231 | awaiting-human (blinded exports; mechanism shipped, fails closed) | owner + counsel, after HB-L1 | Register the study whose extract the blinded-export tooling would blind — `BlindedExportGate` wraps INT-230's export gate, so with the empty study registry there is nothing to be blinded from and it refuses `UnknownStudyError`, exactly as HB-R1 records for INT-231. | HB-R1 (site: HB-L1) |
| INT-231 | awaiting-human (validation corpus; notebook harness shipped, refuses without it) | owner + clinician | Supply the held-out Turkish clinical corpus the validation notebooks (triage validation, note quality, psychiatric-signal validation) score against — until then `NotebookRunner.run` refuses each with `ResourceUnavailableError` naming the corpus, and no corpus or accuracy figure is invented. | HB-C10 (with HB-R1) |
| INT-231 | awaiting-human (BLOCKED instruments for the psychiatric-signal track) | owner + counsel | C-SSRS and WHO-5 are licence-BLOCKED, so the psychiatric-signal notebook names them as unavailable resources and the runner refuses to run it; it carries no instrument content and compiles against none. Resolve the licences or drop the instruments. | HB-L2, HB-L3 |
| INT-113, INT-114 | awaiting-human (no lawful basis; the lane framework refuses them fail-closed) | counsel + owner | Which consent purpose do the `asr_quality` and `engagement` observer lanes run under — `core`, `voice`, or a new purpose added to files/06 §2 with its own Turkish text — given that files/03 §4.7 says every lane is its own purpose while files/06 §2's closed list names only `lane:affect` and `lane:linguistic`? Until you answer, `LaneRuntime.admit` raises `LaneConsentUndeclared` for both lanes rather than attaching them to a basis nobody chose. | HB-L22 |
| INT-112 | awaiting-human (lexicon content; the mechanism ships and fails closed) | physician of record (Dr Efe Onganer) + a Turkish-speaking clinical psychologist | Which Turkish surface forms belong in each of the four marker lexicons — `negative_affect`, `hopelessness`, `anhedonia`, `somatic_worry` — and against which committed Turkish source? Until you answer, all four are `draft_needs_source` with no terms, `compile_lexicon` refuses them, and the lane emits timing statistics and no lexicon key at all. | HB-C16 |
| INT-112, INT-116 | awaiting-human (crisis content AND its destination) | physician of record + counsel | Which Turkish phrases must trigger a consent-independent crisis response, and is that response deterministic **signposting** (`04 §4.2` defect 3: "not a screener, not a score") or an instrument cascade (the INT-112 backlog line's "C-SSRS path", which is licence-BLOCKED and which `03 §4.7.1` puts under `device_functions`)? Until you answer, `CrisisBypass` refuses to build at all rather than never firing silently. | HB-C17 (with HB-C8, HB-L2) |
| INT-112, INT-084 | awaiting-human (renderability, not computation) | physician of record + the clinician-copy owner | What are the Turkish population reference ranges for speech rate, articulation rate and pause ratio — or is the `03 §4.7.6` "Konuşma özellikleri" block not rendered to a clinician at all? The measures are computed; printing one beside no reference range is the accuracy-claim failure mode invariant 20 exists for. | HB-C18 |
| INT-111 | awaiting-human (SER model + held-out Turkish eval corpus; mechanism ships and fails closed) | physician of record (**Dr Efe Onganer**) + owner (corpus collection & labelling) | Collect and label the held-out Turkish clinical affect corpus, evaluate row 14's licence-clean SER weights against it (`ASLP-lab/Emotion2Vec-S` or an ordinal head on WavLM-large / XLS-R-300m), and record the clinician sign-off into `services/voice-runtime/src/intake_voice_runtime/observers/affect_enablement.yaml` (`model_ref`, `corpus`, `evaluated_on`, `sign_off` — never an accuracy figure) — because until one evaluation is recorded `admit_affect` refuses every model, no `AffectLane` can be built, and the lane is disabled by default; no open SER model has a published Turkish evaluation (files/00 §5 Q5), and the measurement lives in `docs/evidence/`, never in copy (invariant 20). | HB-C11 |
| INT-095 | awaiting-human (model provenance; adapters ship, PHI gate fails closed) | owner | Read the raw LICENSE blob at a pinned revision and hash the mirrored weight files for `qwen3.5-9b` (files/03 §4.9.1 row 7) and `whisper-tr-medical` (row 2), so their `observability/registry.yaml` rows carry `model_id@revision` + `weights_sha256` + `licence_verified_at` + the blob url and sha — because row 7 records its blob reading in prose and row 2 records `UNVERIFIED`, and `require_phi_path_pin` therefore refuses both for the PHI path. | HB-I10 |
| INT-095 | awaiting-human (row 1 unobtained; the ASR adapter ships and runs on row 2) | owner + model-stack author | Is `nvidia/nemotron-3.5-asr-streaming-0.6b` (files/03 §4.9.1 row 1, the *primary* ASR) obtained, mirrored, hashed and served — or is the row withdrawn and row 2 promoted, given that row 2's evidence is three speakers and 120 clips? | HB-I11 |
| INT-095 | awaiting-human (on-hardware evidence; a real turn ran, on a dev bridge) | owner (procurement) | The acceptance closes only on a real turn **on the target GPU**; there is no pilot card and no signed capacity contract, so `make live-smoke` records `target=dev-bridge` and the issue stays open. | HB-I4, HB-I5 |
| INT-380 (split from INT-121, 27 Sep 2026) | awaiting-human (no corpus; the harness ships and refuses) | owner, with the DPO/counsel | Which named, dated, licensed set of Turkish documents is the records eval corpus, and on which machine or store does it live — given that a lab report is a patient record and `06 §5` forbids PHI in this repository and in CI, so it may not be committed here? Until you answer, `records_corpus_root()` refuses, `LoincUnitMeasurement` cannot be built without a named corpus and two dates, and no accuracy figure exists anywhere. | HB-A13 (with HB-A10, HB-A2) |
| INT-121, INT-124 | awaiting-human (unit expectations; the guard ships with an EMPTY table and fails closed) | physician of record (**Dr Efe Onganer**) with a clinical biochemist | For which analytes, in which unit and which magnitude band, and against which committed Turkish source, should ingestion check a printed lab value — given that `03 §4.9.6`'s own worked examples are two published Turkish handbooks that printed the unit wrong by 1000x, so the document cannot be its own authority? The guard (`intake_platform.records.unit_guard`, INT-124) flags and never converts; with no expectation authored every value is flagged `no_expectation`, a value that reads two ways (`12.500`) stops rather than being read, and every analyte it did not check is named in `units_unchecked`. A row of the table must cite `{guideline_id, version, date, url, retrieved_on}` or it cannot be built. | HB-C24 |
| INT-123 | todo (index, per-patient RLS, confirmed-only indexing, consent refusal, erasure and the `retrieve_records` Work ship; no embedding model is pinned, so every index Work and every retrieval refuses) | owner (model-stack author) | Which open-weights, commercially usable text-embedding model — Turkish-capable, its licence read from the raw LICENSE blob, pinned `model_id@revision + sha256`, served in-country — becomes the files/03 §4.9.1 row for the record index, given that §4.9.1 names none today (row 18 is a *speaker* embedding, ephemeral and never persisted under invariant 15, and may not be used)? Until you answer, `RECORD_EMBEDDING_ROW` is `None`, the default embedder raises `EmbeddingModelUnregistered`, every index receipt says so, no vector exists anywhere, and `retrieve_records` stays unregistered in the composition root. | — (no HB row; coordinator to allocate) |
| INT-381 | todo, blocked on GPU capacity (INT-124's adapter, pin and guard ship; the PHI gate refuses while no host serves row 9) | owner (procurement; the AWS G-quota cases) | Which host serves the pinned row-9 model `Qwen/Qwen3.6-35B-A3B@995ad96` — on the target GPU, and in-country before it reads a patient's document — so INT-381 can mirror and re-hash the 26 shards against the registry, flip `self_hosted_now` and measure row 9's "< 3 s" target, given that the us-east-1 and eu-central-1 G-quota requests are still `CASE_OPENED`? | HB-I4, HB-I5 (PHI residency: HB-L11) |
| INT-136 | awaiting-human (ordinal anchors; the overlay ships and reports itself not-ready) | physician of record (**Dr Efe Onganer**) | Under `overlay.low_literacy`, which three or four Turkish ordinal anchors stand in for the eleven-point pain score — or is the numeric scale simply not asked of a patient running that overlay, given that files/02 §3 requires severity to be **numeracy-free** and `packages/protocols`' own base layer records that no anchor wording is authored for either end of that scale? | — (no HB row; ids move under concurrent merges, so the coordinator should allocate one) |
| INT-160 | note (mechanism shipped; registry empty and refusing) | owner + counsel (DPA), `platform_owner` (approval), owner (OpenBao) | Register the first connector destination — which hospital endpoint, under which executed DPA, approved by which recorded tier-3 decision, with the application credential and the mTLS client material already written to OpenBao paths under `connectors/`, and does that hospital's agreement state that it honours an `Idempotency-Key`? Until all five exist `infra/connectors/destinations.yaml` holds zero rows and every push refuses; the fifth has no default, because an undeclared receiver turns an ambiguous outcome into a `needs_human` parking rather than an automatic retry that could duplicate a clinical record. | **HB-A15** (allocated by the coordinator; HB-A5 covers the *adapter* half — what interfaces a given hospital exposes — and this is the destination half) |
| INT-162 | awaiting-human (USVS code bindings; the mapping mechanism ships and refuses to serve a draft) | physician of record (**Dr Efe Onganer**) with a clinical biochemist, and the DPO/counsel | Which committed, dated USVS (Ulusal Sağlık Veri Sözlüğü) data-dictionary — element ids and code bindings — do the inbound observation codes map to, and against which source, given that no USVS dictionary is committed to this repository? Until you answer, every row in `usvs_map.yaml`'s `usvs_code_bindings` is `draft_needs_source` with no code and no element, `served_bindings()` excludes them, and an inbound lab resolves to an item with **no code** rather than a guessed one. | — (no HB row; coordinator to allocate, alongside HB-A5 for which codes a given hospital sends) |
| INT-162 | awaiting-human (KTS required-document list; the pack generator ships and reports itself not complete) | owner + counsel | What is the current SBSGM-published KTS (SBYS Kayıt Tescil) required-document list, so the application pack can enumerate every artefact a registration needs — given that files/06 §63 says to *track the live list* and no committed source holds it? Until you answer, `build_kts_pack()` marks the list item `blocked`, `is_complete()` is `false`, and `docs/regulatory/kts_pack.md` names what is missing rather than claiming readiness. | — (no HB row; coordinator to allocate) |
| INT-162 | awaiting-human (executed processor-role DPA + first inbound source; the kit ships and refuses every message) | owner + counsel (the DPA), `platform_owner` (the approval) | Register the first inbound hospital feed — which HBYS/SBYS source, over which transport (and, if `lan_plaintext`, with which separate recorded approval that special-category data may cross a shared LAN in the clear), under which executed processor-role DPA, approved by which recorded tier-3 decision — because until those exist `infra/connectors/inbound_sources.yaml` holds zero rows and every ingest refuses. | **HB-A15** (the destination half is the executed-DPA analogue) + **HB-A5** (which interfaces a given hospital exposes, still UNVERIFIED) |
| INT-320 | awaiting-human (COUNSEL-VETTED embed consent texts; LOCAL dev flow now works on dev placeholders) | Turkish counsel (KVKK / health-law), via INT-210 | Author the embed tenant's counsel-vetted consent document set under its committed `legal_root` (docs/legal/embed/&lt;tenant&gt;/), hash-bound like the rest of docs/legal — the branded intake's consent step now renders end-to-end in LOCAL dev only, from clearly-marked dev placeholders in the dev-legal tree (INT-320 follow-up: the `core` service consent from the global dev consents dir + a per-tenant `partner_processor` disclosure), while this committed tree stays empty and the consent step fails closed (503 `embed_consent_unavailable`) for any tree without your signed texts. Dev placeholders are NOT counsel-vetted and never ship. | HB-L27 |
| INT-320 | awaiting-human (real partner onboarding; registry ships dev-only, prod rows refuse) | owner + counsel (the DPA), `platform_owner` (the OpenBao signing key) | For a real partner embed tenant: the executed data-processing agreement (`dpa_ref`) with the controller/processor determination, the recorded brand-use permission (`brand_permission_ref`), the per-tenant signing key with its production custody/rotation (the DEV key is now seedable locally with `scripts/dev/seed_embed_dev_key.py`, but that path is dev-tier only and refuses a prod tenant), and a shared (Redis) nonce store for multi-replica single-use — none of which an engineer may supply, so `infra/tenants/embed_registry.yaml` ships dev-only and a `prod` row is refused without those facts. | — (no HB row; coordinator to allocate, alongside HB-A15 for the connector-side DPA) |
| INT-320 | awaiting-human (new personal-data category + recipient; out of scope, built as nothing) | owner + DPO / Turkish counsel | Is a partner-supplied patient identifier linked to an Önvizit patient — the correlation that lets the clinician note flow back to a specific partner record — a new category of personal data and a new recipient, and under which {category, purpose, basis, retention, recipients} may it be processed? Until answered it stays OUT of the handshake: the ticket carries no patient identifier and nothing is linked or disclosed (invariant 18; a plausible basis is not invented). | — (no HB row; coordinator to allocate) |
| INT-190 | awaiting-human (prices and budget limits; module shipped, fails closed) | owner | Fill `infra/costs/unit-prices.yaml`: for each component — ASR audio second, dynamic-TTS character, Talker and extraction token, ElevenLabs clip-synthesis character, SMS message (and which SMS provider), the AWS `onvizit-api` host hour and the team GPU server host hour — the USD rate together with the invoice, contract or quote it comes from and its date; and for each vendor and for all vendors together a daily and a monthly USD budget with the same provenance. Until then every component renders "price not configured", every budget "budget not configured", and `CostBudgetNotConfigured` fires for each budget. | HB-O8 (b); the day/month spend budgets are the same owner's second half of that ask — do not mint a new id |
| INT-186 | awaiting-human (branch/profile/clinic filter; module shipped, filter fails closed) | owner + compliance_officer | May the experience aggregates — the CSAT/NPS/clinician-pulse rollups and the SDS-01 export — carry the visit's branch / clinic (and a voice profile) so the console can filter by branch/profile/clinic, given that branch × narrow window × small clinic is files/08 §0c F9's re-identification case and adding the dimension is a data-inventory decision under invariant 18? Until you answer, the three filter dimensions ship `unavailable` and the module fails closed; the SDS-01 export and the rollup projection are fully delivered. | — (no HB row; the same ask as docs/evidence/INT-241.md "Values refused" #3, extended to the satisfaction rollups and to `profile` — do not mint a new id) |
| INT-349 | awaiting-human (the legal half of each register row; answers are already encrypted at rest and the serve gate is closed) | Turkish counsel (KVKK / health-law) with the DPO, instructed by the owner | For each of the eight owner-approved D3 categories in `docs/legal/data-categories.yaml` (personal_safety, sexual_health, substance_use, household, relatives_health, partner_fertility, occupational, literacy), what are the KVKK m.6 basis, the retention, the recipients and the consent scope, and, for household, relatives_health and partner_fertility, the separate basis and notice for the other person who is the data subject? Record them there with your review date (`counsel_reviewed_at`). Until a row is complete, the compiler refuses to serve any slot that carries its category, and the VERBİS entry (INT-211) has nothing to be built from. | — (no HB row exists for the D3 categories yet; agents do not mint HB ids, so one is raised when this is triaged) |
| INT-364 | awaiting-human (the controller's organisational measures of KVKK Board decision 2018/10; the mapping, the source snapshot and the auditor packet ship, and no measure reads as implemented) | owner | Which records close the seventeen `owner` gaps in `docs/legal/special-category-measures.yaml` — the adopted special-category security policy (measure 1), the training and signed confidentiality records (2a, 2b), the named role-grant register and signed periodic access reviews (2c, 2ç), the same-day offboarding and inventory-return checklist (2d), the production OpenBao unseal-key custody (3b), the data-centre environmental and entry evidence (4a, 4b), the e-mail, removable-media and paper transfer rules (5a, 5b, 5ç) and the external penetration test (3ç, 3d) — given that no software control discharges any of them and each stays open, with its one question, until you supply the evidence? The audit-anchor, WORM-target and second-backup-location gaps (3c, 5c) are the existing HB-I12, HB-I9 and HB-I8 asks. | — (no HB row for the 2018/10 organisational measures; agents do not mint HB ids, so the coordinator allocates one) |
| INT-364 | awaiting-human (four readings of the decision) | Turkish counsel (KVKK / health-law), instructed by the owner | Does mutually authenticated TLS between servers in different physical environments satisfy measure 5(c)'s "VPN or sFTP", may a `lan_plaintext` inbound feed ever carry special-category data under it, does a phone one-time code plus an attested device-bound key amount to "en az iki kademeli kimlik doğrulama" under 3(e) for a patient reaching their own data, and what must the staff confidentiality undertaking of 2(b) say? Each is a `counsel` gap in `docs/legal/special-category-measures.yaml` and stays open until answered there. | — (no HB row; coordinator to allocate) |
| INT-359 | awaiting-human (device audit; the report is generated and every row is gated, the Not Evaluated rows wait on a device) | owner | Run the eight scripted walkthroughs in `docs/compliance/accessibility-conformance-report.md` §5 (DA-01 to DA-08: VoiceOver, TalkBack, external keyboard, Switch Control, the largest text size, a real SMS code) on a release build, and record the device, OS, build, date and what you observed for each. Until then, ten WCAG criteria and six EN 301 549 clauses stay Not Evaluated, and the statement cannot give a review date. | HB-L9 |
| INT-359 | awaiting-human (publication; the statement source restates the report and is marked not for publication) | owner (feedback channel) + Turkish counsel (statement text and enforcement route) | Which address does a patient write to about an accessibility barrier, and with what response commitment (owner)? What is the escalation route under 5378 sayılı Kanun and Genelge 2025/10, and what is the Turkish text of the statement, built from `docs/legal/accessibility-statement.md` §4 (counsel)? Until these are answered, the statement is published neither in the app nor on the web, and like every legal text it serves only once signed under the HB-L27 regime. | HB-L9 (signature regime: HB-L27) |
| INT-021 | awaiting-human (docs/slo/workers.yaml; every existing service, tier and job is covered and gated) | owner (backlog) | Does the worker tier become `services/workers`, under which issue, and what objective does each worker SLI that files/08 §4 A leaves open carry (upload promotion, retention-destruction runs, event-bus dead letters, notification dispatch)? The acceptance names `docs/slo/workers.yaml`, but no directory, process or backlog row exists for it, the work it would host is library code nothing runs, and its one spec objective (note ready within 60 s for 99 %) reads `note_time_to_ready_s`, which is planned and not emitted; an SLI over series nobody serves is an objective nobody could breach, so none is written. `observability/slo_coverage.yaml` records the gap, and `tests/observability/test_slo_files.py` requires the file the moment `services/workers` appears. | — (no HB row; agents do not mint HB ids, so the coordinator allocates one) |
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
| INT-203 | awaiting-human (no container runtime; the tier is built, rendered from one policy, licence-verified and was MEASURED against the real engine on 3 Sep 2026 before the constraint) | owner | Where may the edge tier run — a cluster, a container runtime on a machine we are allowed to install one on, or is the acceptance descoped — given that "WAF blocks OWASP CRS suite; CrowdSec scenarios on; certs automated" is a property of a RUNNING Traefik + Coraza + CrowdSec + cert-manager, the laptop may run no Docker at all and the GPU server is itself a pod with no runtime nested inside it? Until you answer, the corpus in `tests/fixtures/waf/corpus.yaml` has nowhere to be decided, and no clause is claimed from a config file. | HB-I13, HB-I14 |

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

---

## INT-203 — the edge has nowhere to run

**What is blocked is a *place*, not a build.** The tier exists, renders from one policy, is
licence-verified against raw LICENSE blobs, and on **3 Sep 2026** it was booted and
**measured**: twelve corpus cases decided by a real Traefik 3.3.7 + Coraza + OWASP CRS
4.0.0, seven CRS families refused and five ordinary Turkish clinical turns served, from a
cold `docker compose up` to green in 28 seconds. `docs/evidence/INT-203.md` §3–§5 records
that run with its date, in the repository's usual form: a measurement of one stack on one
day, never a property of the product.

Then the owner removed the only machine it could run on — no Docker on the laptop at all —
and the GPU server turned out to have no container runtime either, being itself a pod.
Installing one on a box several other people share, to make one issue pass, is not a
decision an agent takes.

**The consequence, stated plainly.** "WAF blocks OWASP CRS suite; CrowdSec scenarios on;
certs automated" is a property of a **running** tier. Nothing in a YAML file can stand in
for it: a middleware that returns 403 to everything satisfies a config-file assertion and
takes the product off the air, and that is precisely the failure the corpus's five Turkish
negative controls exist to catch. So no clause is claimed from configuration, and the issue
stays open at `awaiting-human` with `blocked:runtime`.

**Nothing is built around it.** The suite that decides the corpus is committed and
unmarked-as-skipped — `tests/infra/test_edge_stack_integration.py` boots its own tier and
**fails**, naming `make edge-plugin`, when the artefact is absent. It does not skip, because
a WAF suite that silently does not run is worse than no suite. It will go green the moment
there is somewhere to run it.

**What does NOT need a runtime is merged and green** and is most of the value of the issue:
the policy schema that refuses `DetectionOnly`, a loosened threshold and a wide or expired
exclusion; the renderer that keeps five enforcement points from drifting; the edge log
boundary (`EdgeEvent`), which came out of a real captured line in which Coraza quoted a
patient's Turkish utterance back into the log; and the whole prod-egress-proxy half —
registered destinations, denied ranges, resolve-once-and-pin with re-validation on connect,
redirects disabled, and the denial metric — decided with a local resolver stub and recorded
fixtures, with no container anywhere.

**The id is the coordinator's to allocate.** It is emphatically *not* HB-I1/HB-I2: those are
disk and RAM on a machine that may now run nothing at all regardless of how much of either
it has.

---

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

## INT-319 — a cloud TTS vendor is used for OFFLINE clip-gen; the terms are a human call

**Raised:** 4 Sep 2026 · **Named human:** owner + Turkish counsel · **HUMAN_BLOCKERS id:** _to be
assigned by the coordinator (do not mint an HB id in this session)_

INT-319 / ADR-028 reintroduces a cloud vendor (ElevenLabs) for **offline** clip generation of
the FIXED, non-patient, verbatim scripted set. The mechanism is shipped and fails closed: the
runtime cannot reach a vendor (`refuse_external_host`), the key is env-only and never logged,
the live call is spend-gated on `EVAL_BUDGET_USD`, the vendor normaliser is disabled (inv 22)
and the text is verbatim (inv 10). Three asks are a human's, not an agent's:

- **(a) Vendor licence / commercial-use terms.** *"May we commercially use
  ElevenLabs-generated Turkish audio of our scripted questions, including the voice identity,
  under their terms?"* This is a vendor-contract decision (CLAUDE.md "When to stop and ask the
  human"). — owner.
- **(b) KVKK Art. 9 transfer.** *"Is sending our (non-PHI) scripted protocol text to a US
  vendor for offline synthesis acceptable, and under which basis?"* — Turkish counsel.
- **(c) The Turkish voice id.** The supplied key is a scoped TTS key with no `voices_read`, so
  the voice library cannot be browsed; the small-run used a stable public multilingual voice.
  *"Which warm Turkish ElevenLabs voice id should the fixed set be built with?"* — owner.

Also open and separate: a **fresh on-hardware on-prem run** over `int319-scripted-tr-v1` waits
on GPU access (server unreachable this build, `gpu`); a production `make clips VOICE=<elevenlabs-…>`
end-to-end waits on served packs (HB-C1); and **CosyVoice2** stays a blocked benchmark candidate
(files/00_STATE.md line 99 rules it out for Turkish, LICENSE blob unread). The delivered harness,
adapter and offline clip-gen mechanism are green and do not wait on any of these.
## INT-308 — the carrier/geo authority has no source, and a vendor lookup has no contract

**Raised:** 4 Sep 2026 · **Named human:** owner (the list), owner + counsel (the vendor half)
· **HUMAN_BLOCKERS id:** to be allocated by the coordinator — this session may not mint one

files/10 §2 has always named *"carrier/geo sanity checks against SMS pumping"*. INT-263 found
that no code honoured it. INT-308 built the control and it runs on the OTP request path, in
two halves that are in very different states:

- **Geo is enforced and always was.** `normalise_tr_phone` admits a Turkish mobile and nothing
  else, so the international premium ranges pumping actually profits from never reach a
  delivery adapter. INT-308's contribution to that half is a test that pins it.
- **Carrier is wired and inert.** `intake_api.carrier_geo` derives the operator prefix of an
  already-normalised `+90` number in memory and asks `infra/security/msisdn_allocation.yaml`
  whether it is allocated. That file declares **zero prefixes**, so the authority answers "I
  cannot say" and every request is admitted.

**One sentence closes the first half:** which `5XX` prefixes has the BTK allocated to a Turkish
mobile operator, and against which published document — authority, title, publication date, URL
and retrieval date — was that list read?

It is not a lookup an agent may do from memory, and the failure direction is the expensive one:
a prefix wrongly recorded as unallocated refuses every real subscriber behind it, silently, with
a 422 that reads to the patient like a typo in their own number. The loader therefore **refuses
a non-empty prefix list that carries no `source` block**, so the list cannot be typed in without
the refusal being visible in the diff, and `exhaustive` has no default — a partial list marked
complete is the same failure with a wider blast radius.

**The second half is a separate decision and costs more.** A live per-number lookup (HLR, number
portability) answers a stronger question than prefix allocation, needs a contracted vendor, and
sends the patient's own phone number to a third party. That is a decision to disclose a new
category of personal data and a licence question under CLAUDE.md invariant 19 — not a
configuration change — so the `MsisdnAuthority` seam is deliberately narrower than any such
vendor: it is handed a country code and an operator prefix and never the subscriber number, and
a vendor that needs the whole MSISDN cannot be dropped in behind it without that conversation.
**One sentence closes it:** is a per-number carrier lookup wanted at all, and if so under which
contracted provider, which licence, and which lawful basis for sending a patient's number to it?

**Nothing is built around either.** The check fails **open** on every lookup it cannot make, which
is the acceptance's own requirement rather than a workaround; the empty table is the shipping
state and `test_the_shipped_allocation_table_declares_no_prefixes_and_cannot_refuse` pins it, so
supplying the list is a visible change and not a silent one. What stands against SMS pumping
today is what files/10 §2 now says stands against it: the rolling request budgets and the
Turkish-mobile-only normalisation.

## INT-401 (split from INT-187) — a rollback button needs something to roll back

**Named human:** the owner (where continuous delivery runs), with whoever administers the target.

**What shipped.** `/cicd` renders recent GitHub Actions runs per workflow with their failing
jobs, every PR-triggered gate on `main` and on the open PRs, releases with their signing
outcome, this deployment's stamped `/version`, the error budget and the deploy freeze. The
freeze is enforced where deploys actually happen: `infra/staging/deploy.sh` runs a release
gate before it restarts anything, and refuses while deploys are frozen, while an SLO's error
budget is exhausted, or while the freeze cannot be read. Freezing is one key; lifting is four
eyes (files/08 §8.2).

**What waits is the rollback button (4-eyes).** files/08 §3 and §9 describe CD as GitOps
through Argo CD, where a rollback moves an Application to an earlier revision and a canary is
an Argo Rollout. Neither exists: `infra/` holds no Argo CD Application, no Rollout, and there is
no cluster to run them on — the same siting question HB-I13 asks for the edge tier. The only
deploy path is the operator running `deploy.sh` on the host over SSM, which the console cannot
command. A two-key ceremony whose approval changes nothing is not a control, so the button is
rendered **disabled, with that reason**, and the canary tile says "not deployed" rather than
painting a state that does not exist. `tests/admin/test_cicd_console.py` fails the day an
Argo CD manifest lands under `infra/`, so the tile gets wired instead of left claiming absence.

**One sentence closes it:** where does continuous delivery run — a cluster with Argo CD (and
Argo Rollouts for the canary), and on which host — or is `deploy.sh` the release path for the
foreseeable future, in which case "rollback" becomes "redeploy a previous release through
`deploy.sh`", which the console can gate (a four-eyes pin the gate enforces) but not execute?

**The id is the coordinator's to allocate.** HB-I13 is the nearest existing row (a place to
run a cluster), but it is about the edge tier; a CD-tier row, or a widening of HB-I13, is a
coordinator decision, not one an agent mints.
