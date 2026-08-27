# 05 · Roadmap — v2.1 (rebuilt 25 Aug 2026 after external verification; reconciled 27 Aug 2026)

> **What changed from v1.4, and why.** v1.4 was a *date-driven* plan: P0 in weeks 0–3, P1 by week 12, a hospital pilot by month 7. Four independent verification passes — clinical, architecture, vendor-facts and Turkish regulatory — established that those dates were not achievable and, more importantly, that **the calendar was never the binding constraint**. Three things bind, in this order:
>
> 1. **Your review capacity.** 101 of 175 issues sit behind a human gate.
> 2. **CI throughput.** 175 issues × a realistic 35–60 min PR gate ≈ 100–175 CPU-hours. The autonomous loop is bounded by CI, not by the model.
> 3. **The clinical-investigation clock.** 7–12 months, strictly sequential, and not compressible by adding engineers.
>
> v2.0 is therefore **gate-driven**: phases advance when evidence exists, not when a date arrives. Every duration below is a forecast under stated assumptions, never a commitment, and each phase names the artefact that ends it.
>
> **The single most consequential correction: the medical-device classification is Class IIb, not Class IIa** (`06 §0.3`). That re-prices Stage B and should be resolved before anything else is budgeted.
>
> **v2.1 reconciliation, 27 Aug 2026.** Four things this plan still assumed have changed, and each is corrected in place below rather than removed: **(1) all models are self-hosted** — `cascade_fast` and `s2s_cloud` cease to exist, so P1's profile is `residency_tr` and the `s2s_cloud → P3` line becomes a withdrawal; **(2) `03 §4.9.1` is the single source of truth for the model stack**, so no phase, KPI or assumption row here pins a model — where one did, it now points at a row number; **(3) Kintsugi DAM is dropped (D14)** — the `acoustic` lane survives, the model does not, which changes what the Turkish validation track is *for*; **(4) the P2 integration counterparty is the hospital group's own technology arm**, already corrected under the phase table. Phase **gates** — the evidence that ends a phase — are now stated explicitly in **§1a**, because "the exit artefact" was a column and needed to be a checklist.

---

## 0. The five facts that shape this plan

### F1 — 58 % of the backlog is behind a human
Parsing `docs/backlog/issues.yaml` (175 issues; after the v2.0 graph fixes: no cycles, no missing dependencies, no phase inversions), **101 issues are gated on a human decision, directly or transitively.** The autonomous loop can complete **47 of the 91 P0 issues** unattended and then stops.

`./loop.sh 40` would stall around iteration 25–30, and v1.4's LOOP.md gave it no way to say why: `awaiting-human` is not `done`, so every dependent silently never becomes Ready.

### F2 — One issue unblocks 78 others

| Issue | Unblocks | Gate | Depth on the critical path |
|---|---|---|---|
| **INT-043 `base.intake` pack** | **78 of 175** | clinical | 9 |
| INT-116 Wellbeing engine | 12 | clinical | 15 |
| INT-117 `device_functions` flag | 10 | legal | 16 |
| INT-044 `cluster.medical` pack | 8 | clinical | 10 |
| INT-210 Legal document set | 7 | legal | — |

v1.4 placed INT-043 at depth 9, so the agent would work for days before you ever saw the thing that unblocks everything else. **v2.0 front-loads all five.**

### F3 — The clinical investigation is 7–12 months and strictly sequential
TCKAY (RG 31890, 08.07.2022): **m.8/2** requires the ethics decision to be submitted *as part of* the TİTCK application — they cannot run in parallel. **m.5/2(a)** requires non-clinical validation *before* submission (for software, a documented bench and retrospective validation of the triage engine — a work package v1.4 did not show). **m.5/6** restricts sites to a **university** health application & research centre, an approved university-affiliated R&D centre, or an MoH training & research hospital — **a general private Acıbadem hospital does not qualify.** The study must sit at Acıbadem Mehmet Ali Aydınlar Üniversitesi's research centre; KAEK is that university's committee, so this is workable, but the site must be named.

| phase | statutory clock | realistic |
|---|---|---|
| Non-clinical validation + protocol + ICF(tr) + Annex XV Pt II + risk file | — | 8–14 wk |
| Insurance (parallel) · site + PI + budget contracting (parallel, often the real bottleneck) | — | 2–4 wk · 4–8 wk |
| KAEK ethics | ~30 d | **4–12 wk** (monthly agendas) |
| TİTCK | 20 iş günü | 4 wk clean; **8–14 wk with one eksiklik yazısı** |
| Site initiation → first participant | — | 2–4 wk |

**≈ 9 months is the sensible plan; 6 months is an aggressive best case.**

### F4 — Cost is load-independent, and the vendor bill is noise
~**€2,800–4,400/month fixed** once `residency_tr` exists, and **≈ €0 marginal** for the 300-session pilot (≈ 5 sessions/working day; the GPU sits at < 1 % utilisation). That is **€10–15 of infrastructure per pre-visit**.

Vendor cost is **$0.13–0.28 per session ⇒ $40–85 for the entire pilot**, of which the extraction LLM is 70–80 % (reducible by caching the invariant slot schema instead of re-sending it on all 18 turns). The clip cache is the design's single best cost decision and it works.

The security and observability tiers alone (22 GB RAM) exceed the entire application tier. **Every cost lever that matters is in the self-hosting decision, not the vendor decision** — the opposite of where `08` directs attention.

### F5 — Two instruments are licence-blocked
- **C-SSRS**: Clario holds an *exclusive* RFMH licence for "any electronic format" — $40,000 start-up + $7,500/yr + $5,000 per certified version + **$4 per administration**. Columbia's free route covers healthcare providers embedding it in their own EHR; we are a for-profit vendor shipping a patient-self-completed electronic Turkish version, which is neither. Training is *not* the issue — the electronic sublicence is. Also: the only Turkish validation is **adolescents 12–18 only**.
- **WHO-5**: copyright transferred to WHO in 2024 and published **CC BY-NC-SA 3.0 IGO — NonCommercial**. Embedding it in a for-profit product is outside the licence, and ShareAlike imposes a copyleft obligation on any adaptation (reformatting for mobile counts).

Both are **BLOCKED** until written permission exists. **HAQ-DI** is NEEDS-PERMISSION: Stanford's "public domain" statement covers the **English** version only, and under FSEK a Turkish translation is an *işlenme eser* with its own rights holder.

---

## 1. Phase table (gate-driven)

| Phase | Theme | Ends when — the exit **artefact** | Forecast |
|---|---|---|---|
| **P0 Foundation** | Monorepo, CI, the four safety guards, protocol DSL + compiler, deterministic triage, voice-runtime core on mocks, typed-mode intake end-to-end, **`base.life_threat` universal rule set**, admin skeleton | `make check` + `make safety` + `make security` green from a clean clone · every branch resolves to a reviewed pack · runtime invariants 1–12 pass on fake clocks · **a deliberately broken RED rule fails the suite and is reverted, on record** · issue machinery live | **12–20 weeks** |
| **P1 Fast mode, device-off** | Turkish voice intake E2E (⚠ **`residency_tr` — `cascade_fast` no longer exists**, `00 §0b`), **`residency_tr_media` — SFU + TURN + API + Postgres in İstanbul (§2.1)**, records ingestion, patient summary, clinician note via Doctor Link, CSAT/NPS, real telemetry | 20 internal users × 3 specialties · **client-side measured** round-trip meets §4 targets · note acceptance ≥ 70 % · DPIA v1 signed · ⚠ **Art. 9 standard contracts: none required on the PHI path** — under self-hosting there is no cloud vendor in use, which is the strongest form this control can take. The row survives as an audit statement, not as work | **+10–16 weeks** |
| **P2 Hospital pilot** | Detailed mode, check-in, clinic console, **bilateral integration with the pilot group's own technology arm** (⚠ *corrected — see the note under this table; the FHIR connector is an outbound export, not the integration*), companions, top-10 deep packs | Pilot at one hospital group · ≥ 300 real pre-visits · clinician read rate ≥ 80 % · CSAT ≥ 4.2 · zero PHI incidents · external pen-test passed, findings closed | **+4–6 months** |
| **P2b Clinical investigation** *(parallel track — starts in P0)* | The only lawful route to `device_functions=on` | KAEK approval **then** TİTCK permission, recorded against a named study id **and protocol version** · insurance in force · first participant enrolled | **≈ 9 months from protocol drafting** |
| **P3 The record that travels** | e-Nabız application, HBYS.API connector, consented visit recording, longitudinal timeline, **openEHR added as an export**, `residency_tr_models` when a public tenant signs **and a signed GPU capacity contract exists** (`residency_tr_media` ships in P1, §2.1) | 2nd hospital group · e-Nabız sandbox or a formal decision · published evaluation report | **+6–9 months** |
| **P4 CE + scale** | Class **IIb** conformity assessment, ÜTS registration, B2B2C white-label | Notified-body certificate · `device_functions=on` commercially | Gated on P2b evidence |

> **P3 is currently unplanned.** It holds 2 issues while its own description covers e-Nabız, HBYS.API, diarised visit recording and the longitudinal timeline. Either scope it or stop calling it a phase.

> 🔵 **P2 aimed its connector effort at the wrong counterparty. This is a strategy correction, not a footnote.** **ACIBADEM TEKNOLOJİ A.Ş. is #2 on SBSGM's Aktif HBYS Listesi** — the pilot partner *is its own HBYS vendor*. The active list carries exactly **57 firms (31 Jul 2026)** and **the passive list is empty**, so that is the complete registered universe; **Grup Florence Nightingale, Hisar and Gaziantep Özel self-register the same way.**
>
> Therefore: **for private hospital groups — which is the entire go-to-market (`01 §3`) — the integration counterparty is the group's own technology arm, not a third-party HBYS vendor.** Akgün, Sisoft, Probel and Monad matter for **public** hospitals, and that is a later and different motion with a different sales cycle: a şartname and a tender rather than a commercial agreement with the group that already runs the estate. P2's connector work is a **bilateral, per-tenant integration with Acıbadem Teknoloji** — endpoints registered out-of-band at onboarding and bound to the signed DPA (`03 §12`, `10 §9.1` inv. 46) — most likely HL7 v2 feeds or the arm's own API.
>
> ⚠️ **UNVERIFIED: what interfaces Acıbadem Teknoloji actually exposes.** Only its registration status is confirmed. Do not size the P2 connector, or promise a payload shape, before that conversation happens — and note that it is a conversation with the pilot partner we already have, which is the cheap part of this correction.

---

## 1a. Phase gates — the Definition of Done at phase scale

The per-issue DoD lives in `07 §3.3` and is checked by CI on every PR. **This section is the phase-level equivalent**, and it exists because the phase table's "exit artefact" column was one cell wide and a phase gate is not a sentence. A phase ends when **every** line below is true and the evidence is committed — not when the work "feels" finished, not when the calendar says so, and not when the remaining items are "only" human-gated.

**Three rules that apply to all four gates.**

1. **The evidence is a file, not a claim.** Every line resolves to something committed under `docs/evidence/` or `docs/regulatory/` with a date. "We ran it and it passed" is not an exit artefact; the recorded run is.
2. **Human-gated items do not close a phase early.** A gate line that reads *"a named clinician has signed"* is not satisfied by a green test suite, a self-review, or a note saying the content was drafted carefully. See `HUMAN_BLOCKERS.md` — that file exists so the gate can name who.
3. **Gates only tighten.** A phase gate is never relaxed to let a phase close. If a line cannot be met, the phase does not end and the line is not edited; what changes is the plan, and the change is recorded in `00 §3` with its reason.

### P0 — Foundation

- [ ] `make check`, `make safety` and `make security` green **from a clean clone**, not incrementally, with the runs committed.
- [ ] Runtime invariants **1–12** pass on fake clocks; the six-tool introspection test exists and a temporary seventh tool makes it fail (proved, reverted).
- [ ] **A deliberately broken RED rule fails `make safety` and is reverted, on record — both runs in the evidence file.** This is the P0 exit artefact and it is not optional: it is the only proof that the golden suite is load-bearing rather than decorative. **A suite that stays green through a broken RED rule is worse than no suite, because it is trusted.**
- [ ] Every RED golden has its **near-miss negative control**, and the suite fails if one is missing. The positive passes by construction and only detects under-triggering; **over-triggering is invisible in production** and surfaces months later as alert fatigue, by which time the rule that caused it cannot be identified.
- [ ] The compiler rejects a RED rule with no `register`, and one whose action does not resolve for `REMOTE`, `ON_SITE` and `UNKNOWN` (proved, reverted).
- [ ] The clip-manifest round-trip gate — synthesise → **independent** ASR → normalised diff — fails the build on a planted unexpanded numeral (proved, reverted).
- [ ] Every branch in `taxonomy/branches.yaml` resolves to a reviewed pack; resolving an L0 pack for a session raises.
- [ ] A pack referencing a non-`GO` instrument fails the build; a pack with an unfilled `clinical_signoff` block cannot emit an L1 bundle.
- [ ] Issue machinery live end-to-end: backlog on GitHub with labels and milestones, `no_placeholders` and `evidence_check` each proved on a planted violation and reverted.
- [ ] `00_STATE.md` has a row for every decision taken during the phase, in the commit that took it.
- [ ] **Human-gated and therefore not self-certifiable:** `base.intake` and `base.life_threat` signed by a named licensed physician (paediatric rules by a paediatrician) — HB-C1…C7. **P0 does not end without this, however green CI is.**

### P1 — Fast mode, device-off

- [ ] Round-trip latency **measured client-side on real devices, reported per network profile** (`02 §8.1`) — never as a single number, because publishing one floor for a distribution this wide is itself the mistake.
- [ ] Note acceptance ≥ 70 % on real clinician review; DPIA v1 signed; VERBİS registered.
- [ ] **Per-rule extraction sensitivity and specificity against a Turkish clinical reference standard** — covering agglutinative negation and evidentiality, second-language speakers, and a "did not understand" state distinct from "no". **This gates P1 exit**: without it the triage engine's inputs are unvalidated and the "deterministic rules engine" claim is unsupported, because a deterministic engine over probabilistic inputs is not deterministic. Recorded as a dated internal measurement — **never as a published accuracy claim** (ADR-022).
- [ ] `residency_tr_media` live: the **testable** claim is that patient audio bytes never leave Türkiye on the media path, asserted by a test, not by a diagram.
- [ ] Network telemetry collected from session one for the four **UNVERIFIED** transport unknowns — Turkish mobile packet loss, hospital guest wifi, handset mic-capture buffer, NetEq concealment-versus-delay — and the `02 §8.1` NFRs **re-derived after 100 sessions**.
- [ ] De-identification reported as **recall per entity class on a held-out, human-labelled, real-transcript corpus with a published confusion matrix** — not as a single "< 0.1 % leak rate" measured on a corpus we authored, which is unfalsifiable as defined.
- [ ] Mutation testing on the triage evaluator has run and its findings are closed.

### P2 — Hospital pilot · P2b — Clinical investigation

- [ ] ≥ 300 real pre-visits; clinician read rate ≥ 80 %; CSAT ≥ 4.2; **zero PHI incidents**; external pen-test passed with findings closed.
- [ ] **Primary safety metric reported as misses, not false positives** — zero clinician-confirmed missed time-critical conditions, measured by **chart-linked follow-up of a sample of GREEN sessions**, not clinician self-report, which under-detects.
- [ ] Per-rule false-RED rates published internally and reviewed rule by rule through the console queue.
- [ ] The integration is **bilateral with the group's own technology arm**, bound to the signed DPA, with endpoints registered out-of-band at onboarding — not a third-party HBYS connector, and not sized before that conversation has happened (HB-A5).
- [ ] The self-hosting release gate is **enforced** from here (the registry and the gate were built in P0).
- [ ] **P2b, and it is a separate clock:** KAEK approval **then** TİTCK permission — they cannot run in parallel — recorded against a named study id **and protocol version**, with insurance in force, at a **qualifying university research centre** (HB-L1). ⚠ **The 300-session pilot cannot validate the `acoustic` lane**: that study is n ≈ 800, and the pilot is off by ~3×.

### P3 / P4

- [ ] `residency_tr_models` ships only against a **signed GPU capacity contract naming provider and SKUs** — and **no availability date is published before that contract exists** (HB-I5).
- [ ] e-Nabız: a formal Ministry decision on the **deposit** path, or a recorded decline. Not a read path — there is no mechanism and no category for one.
- [ ] Class **IIb** conformity assessment with a clinical evaluation report per MDCG 2020-1; ÜTS registration; `device_functions=on` commercially only after the notified-body certificate.
- [ ] Throughout: **no accuracy claim** has entered `docs/regulatory/`, `docs/legal/`, marketing or a store listing — the `claims-scan` CI gate has been green on every release build since P0.

---

## 2. What P0 builds — and what was cut

### 2.1 Cut from P0/P1 (≈ 29–39 engineer-weeks recovered) — ⚠ and one item **pulled forward** on measurement

| Cut | Why | Recovered |
|---|---|---|
| **openEHR / EHRbase → P3; FHIR-only until then** | **No P0/P1 feature issues an AQL query.** Every real consumer — Doctor Link, HBYS.API, e-Nabız, SGK, the clinician note, the app — is FHIR / ICD-10 / LOINC / ATC / text. `03 §7` already concedes SNOMED CT is unavailable in Türkiye, removing much of openEHR's semantic advantage before you start. No Python library generates Operational Templates; OPT authoring is a Java / Archetype-Designer activity. And round-trip goldens over a lossy openEHR↔FHIR mapping would pass only because we wrote them to match the mapper — **a test that cannot fail, which `07 §TDD` explicitly forbids.** **Keep the archetype-path annotation on every slot**: it costs nothing and *is* the migration plan. | 14–20 wk |
| **`residency_tr_models` → P3** ⚠ **split 25 Aug 2026 — see below** | vLLM + TTS + observer lanes in Türkiye. `06` makes residency mandatory for **public** hospitals; the pilot is Acıbadem — **private**. This half builds a GPU datacentre to run at < 1 % utilisation for 300 sessions. Keep the gateway abstraction and profile-parity tests so the swap stays a config change. | 8–12 wk + €1.2–2.5k/mo |
| **`residency_tr_media` → P1** ⚠ **NEW — pulled forward, not cut** | LiveKit SFU + TURN + API + Postgres in İstanbul. **This is a latency *win*, not a cost**: −39 ms p50 / −47 ms p95 of round-trip media time, measured (`03 §4.4`). It is also a genuine KVKK strengthening and **needs no GPU**. AWS opened `eu-central-1-ist-1a` (Local Zone, GA May 2026) with C7i/M7i/R7i, EBS, VPC, ECS, EKS, ALB, Direct Connect and S3 One Zone-IA — exactly this tier's shape. LiveKit Cloud has no Turkish region, so we self-host the Apache-2.0 server, **which makes us the operator of TURN as well**. | — (net negative latency; ~€0.3–0.6k/mo) |
| ~~`affect` + `acoustic` observer lanes~~ — **NOT CUT. Retained and hardened.** | ⚠️ An earlier draft of this table proposed cutting these on cost and PHI-egress grounds. **That was based on a misreading of `03 §4.7` and is withdrawn.** The `acoustic` lane is a **Kintsugi DAM-class model with open weights, self-hosted, in every profile** — there is no vendor, no second audio stream and no cross-border transfer. And `affect` **already has a self-hosted implementation specified** (open SER, emotion2vec-class) for `residency_tr`; the vendor route applies only to `cascade_fast`. `linguistic`, `asr_quality` and `engagement` are local in all profiles. **And neither lane is an STT cost in the first place.** Kintsugi DAM is an *audio-classification* model — `audio-classification`, `base_model: openai/whisper-small.en` — which uses Whisper as an **encoder/feature extractor, not a transcriber**. It emits ordinal severity heads and never produces text, so it consumes no STT minutes and no per-stream vendor billing; its only marginal cost is GPU time on hardware already provisioned. Inworld's voice profiling likewise runs as a **parallel model on an existing STT stream**, not a separate transcription job — so whether `affect` costs a second stream is purely a routing question, and since Inworld now covers Turkish natively for both STT and profiling, the two-vendor configuration may be avoidable without touching the open-SER question at all. Latency was never an objection: the lanes are off the critical path by design, with an invariant that tests it. | — (see §2.3) |
| ~~`s2s_cloud` → P3~~ — ⚠ **WITHDRAWN outright, 27 Aug 2026, not deferred** | Two independent reasons, either sufficient. **(1)** Every model it named is cloud-only, and all models are now self-hosted (`00 §0b`) — there is no S2S profile to defer. **(2)** It was already the wrong shape: it cannot meet the contract ADR-009/010 says every profile shares — no clip cache, no verbatim scripted text, and PolicyGuard degrades to *after-the-fact* retraction, meaning **the patient already heard the diagnostic sentence**. It is faster **and** less safe, presented as an upgrade. The durable form of this withdrawal is a **closed profile registry plus a grep gate** (INT-098), not a paragraph. ⚠ Note also that the async-tool-calling argument that once justified it was **profile-local, not architectural**: `submit_utterance` returning a `work_id` is trivially non-blocking on an ordinary text LLM. | 3 wk |
| **Heavy security tier → P1** | Defer Wazuh (12 GB + a part-time SRE), Harbor + Kyverno + cosign admission (there is no cluster in P0), CrowdSec, the service mesh, MobSF. **Keep every invariant** — they are enforced by tests, and the tests are what P0 ships. | ~4 wk |

> ⚠ **`residency_tr` was one P2/P3 item. It is two items with completely different risk, and the cheap half was being held hostage by the expensive half.**
>
> - **`residency_tr_media`** — SFU + TURN + API + Postgres in İstanbul. **Ship in P1.** A latency win, a genuine KVKK strengthening, no GPU required. One honest caveat travels with it: **physical residency ≠ legal residency** — the Local Zone's control plane is in Frankfurt and the operator is **AWS EMEA SARL**, so whether it satisfies KVKK Art. 9 is a question for counsel (`06 §1`). The narrow **testable** claim is that the patient's audio bytes never leave Türkiye on the media path.
> - **`residency_tr_models`** — vLLM + TTS + observer lanes in Türkiye. **Gate on a signed capacity contract naming the provider and the GPU SKUs. Do not publish a `residency_tr` availability date before that contract exists.** Re-evaluate when the Google Türkiye region opens.

**And record the supply constraint plainly: GPU supply in Türkiye is thin.**

| option | what is actually available |
|---|---|
| **AWS İstanbul Local Zone** (`eu-central-1-ist-1a`, GA May 2026) | **C7i / M7i / R7i only — no G / P / Inf family.** Perfect for the media tier, useless for the model tier |
| **Azure** | **no Türkiye region** |
| **Google Cloud Türkiye** | announced 20 Nov 2025 with Turkcell — **no opening date and no published accelerator plan** |
| **Huawei Cloud Türkiye** | live (İstanbul + Ankara DR), but its accelerators are **Ascend, not CUDA** — the vLLM stack of `03 §4.9.1` does not port |
| **Türk Telekom GPUaaS** | sold, with **no published model, capacity or price** |
| İstanbul resellers | advertise H100 / H200 / A100 but publish **no capacity commitment** — **UNVERIFIED** |

And the macro constraint settles it: **Türkiye's entire commercial data-centre capacity was ~120–160 MW at end-2025** — one hyperscale AI facility elsewhere draws 100+ MW on its own — with private generation above the exempt threshold needing **EMRA licensing**, and **June 2026 amendments restricting unlicensed surplus sales.** This is why `residency_tr_models` is gated on a contract rather than a date.

### 2.2 Added to P0 — safety work that was missing

- **`base.life_threat`** — a rule set evaluated on **every session regardless of booked branch**. In v1.4, cauda equina, testicular torsion, limb ischaemia, acute angle-closure, sudden vision loss, neutropenic fever, GCA and stridor lived in *cluster or specialty* packs, so each was evaluated only if the patient happened to book into that branch. **Patients do not present according to their booking** — the MHRS booking-to-visit lag is days to weeks and intake runs at T-24h. CI property test: `every_RED_rule_is_reachable_from_every_branch`.
- **`CLINICIAN_ONLY` disposition** — safeguarding needs a flag invisible to the patient *and to the proxy*. Child maltreatment, domestic violence and elder abuse appear **zero times** in v1.4's clinical content, and the product is voice-first and speaks aloud. Add a discreet exit control and text-mode-first for any section that could elicit a disclosure.
- **Three-state answers** — `asked_present | asked_absent | not_asked` (+ `unclear`, `declined`), type-enforced. A flat `negatives[]` reads to a clinician as *elicited*; this is the canonical mechanism by which generated clinical documentation causes harm, and it is directly foreseeable with an 18-turn cap and a "bunu atla" control.
- **`source:` on every red-flag rule** — `{guideline_id, version, date, url, retrieved_on}`, with a CI test that every RED rule has one. A grep of v1.4 for NICE / IDSA / USPSTF / Ottawa / BSR / ESVS identifiers returns **no hits**: the rules carry no provenance at all, and MDCG 2020-1 clinical evaluation must rest on cited, current sources.
- **Mandatory universal fields** — pregnancy status and LMP for every reproductive-age female patient (ruptured ectopic classically presents in a woman who does not know she is pregnant; and NG255 is scoped to *pregnant or recently pregnant, any age*, so sepsis routing needs it too); immunosuppression (chemo ≤ 6 weeks, biologic, steroid, transplant, asplenia); weight; vitals; time-last-known-well as a structured timestamp.
- **`tense` on every rule** — `now | today | within_7d | within_30d | ever`, each with its own `action_tr`. Real anaphylaxis is a five-minute event; nobody completes a pre-visit intake through one, so in practice that rule fires on *past* reactions and needs a different action.
- **A guideline-currency job** that diffs each cited guideline's *update-information chapter*, not its header date. NICE's header "last updated" misses real clinical changes: CG84's IV fluid bolus moved 20 → 10 ml/kg as a "minor change", and CG89 has a March 2026 text change the header does not show.

### 2.3 Observer lanes — retained, and what hardening them actually requires

The lanes stay. They are a differentiating capability and the two objections raised against them (cost, PHI egress) applied only to one implementation of one lane. Five things genuinely need fixing, none of which is a scope cut:

| # | defect | fix |
|---|---|---|
| 1 | **No diarization.** The `acoustic` lane requires a ≥ 30 s **single-speaker** window, and there is no diarizer anywhere in the design — while companion and proxy profiles are a first-class feature. A companion in the room silently contaminates the window, and the model was trained single-speaker | Specify a diarization gate on the **self-hosted** path with a confidence threshold and a defined multi-speaker behaviour. Note this interacts with a separate finding: a third party present is the **largest single moderator of disclosure** in two meta-analyses, so detecting one has value beyond the acoustic lane |
| 2 | **Transient audio exposure through crash artifacts** — *not* storage. Raw audio is never persisted: invariant 9 forbids it, `audio_retention_guard` proves there are no write paths, and §4.7 keeps the window in memory only and zeroes it after scoring. But a 30-second PCM buffer can still leak through a **core dump, a swap page, or a crash report** — and the product ships GlitchTip. **A fake-fs test cannot see a core dump** | `RLIMIT_CORE=0`, `mlock` on the lane buffer, explicit zeroization after scoring — each with an assertion rather than a convention. This is a narrower defect than "audio at rest", and it does not weaken the no-retention guarantee |
| 3 | ⚠ **Rewritten 27 Aug 2026 — the problem is not calibration.** This row used to read *"DAM is US-English at ~71 % sensitivity/specificity, so design the Turkish calibration study."* **Kintsugi DAM is dropped (D14)**: the vendor dissolved Feb 2026 after failing FDA De Novo, so Apache-2.0 would convey the weights and make us the legal manufacturer of a Class IIb function **with no design history file** — no training-data provenance, no subject demographics, no bias analyses, no verification records, and nobody left to ask. And **threshold recalibration could never have fixed it anyway**: refitting a threshold is a **monotone transform**, so AUC and the ROC curve are invariant under it. You cannot threshold your way out of a discrimination problem. | **The lane survives; the model does not.** Train an **ordinal head ourselves** on an Apache-2.0/MIT SSL encoder (`03 §4.9.1` row 19), tapping an **intermediate layer, not the final one** — four independent papers, and DAM pooled the final layer, which is Whisper's *worst* for cross-lingual transfer. **We then hold the design history file because we created it**, which converts an unanswerable regulatory question into an ordinary, expensive, tractable one. The study still has to be designed — n, labels, ethics route — but it is now a validation of our own device, not a calibration of someone else's orphan. |
| 4 | **Determinism.** Lane output depends on dropped frames and load-adaptive sampling, so the same session cannot be replayed — contradicting the "pure, replayable" claim and the reproducible-sessions goal | Lane signals become **recorded inputs**, not re-executed computations. The forward-bring of PHQ-2/GAD-2 is then a deterministic function of the recorded signal, and replay replays the signal, never the audio |
| 5 | **Compute isolation.** §4.7 says *"asyncio tasks with per-lane CPU/GPU budgets (or a separate worker pool)"* | **Make the parenthetical the requirement.** Parallel work is only free if the isolation is real — asyncio tasks sharing an event loop with the voice runtime is how "off the critical path" quietly stops being true. Specify the pool, the budgets, the backpressure policy, and a test that turn latency is unchanged under lane saturation |

**On the regulatory frame, one distinction to keep clean.** Self-hosting is decisive for **KVKK Art. 9** (no cross-border transfer at all), for **Genelge 2019/12** residency with public-hospital tenants, and for the DPIA. It is **not** an answer to medical-device classification: FDA Device Example 14 concerns the *function* — analysing a signal or pattern — regardless of where it runs, and Criterion 1 failures cannot be documented away. The answer there is **MDCG 2019-11 Rev. 1 §7 module bounding** — *"It is the obligation of the manufacturer to identify the boundaries and the interfaces of the different modules"* — so that the lanes carry their own classification without dragging the rest of the intake into MDSW scope. Two separate threads; do not let one stand in for the other.

**And the output has to be worth it.** One `affect_summary` sentence in the clinician note is a poor return on a continuously-running lane. The lanes already read the stream; what else is defensibly derivable — pacing and modality adaptation, ASR-confidence-driven confirm-by-card, engagement-driven break offers, detection of distress that should pause the interview — is a design question worth answering properly rather than a reason to switch them off.

---

## 3. Delivery model — corrected

**One issue → one PR** stays. Three things change.

1. **Front-load the human gates.** New P0 order: INT-001…004 (machinery) → **INT-043 drafted and in your inbox on day 2** → INT-044…052 cluster packs → then the platform / data / protocol chain. The agent drafts; you review. This turns *"agent works three days then stalls two weeks"* into *"you have review work from day 2."*
2. **`awaiting-human` must stop blocking dependents.** Make it a satisfiable dependency state for issues that depend only on the non-gated part, and make the loop print `WAITING_HUMAN` with the exact list rather than silently skipping.
3. **Split `make check`.** As one target it is 25–50 min cold. Decompose into `check-py` / `check-ts` / `check-golden` / `check-integration` as parallel CI jobs (keep `make check` as a local fan-out alias); run `mypy --strict` on `packages/` + `services/api` only with changed-package scoping plus a full nightly; move the docker-compose tier to its own required job. **Then < 10 min wall-clock is real.** Without this, P0's 91 issues alone are ≈ 68 hours of serial CI.

---

## 4. KPIs — corrected targets

Changes are marked ⚠. Unmarked targets carry over from v1.4.

### Speech & feel
v1.4's budget table omitted **every network term**. Recomputed — and, as of 25 Aug 2026, **measured**: 674,774 Ookla mobile tests / 338,416 devices, Türkiye 2026 Q2, plus 24 h of continuous RIPE Atlas ping from 11 Turkish anchors (`03 §4.5.1`).

| metric | v1.4 | ⚠ v2.0 | why |
|---|---|---|---|
| scripted p50 / p95 | ≤ 400 / ≤ 1200 ms | **per network profile — `02 §8.1`**; mid-LTE **≤ 450 / ≤ 680 ms** | the structural floor is **not a single number**: 376 ms p50 / 481 ms p95 with a Frankfurt SFU, 338 / 434 in-country. **Publishing one floor for a distribution this wide is the mistake** |
| dynamic p50 / p95 | ≤ 700 / ≤ 1200 ms | **per network profile — `02 §8.1`**; mid-LTE **≤ 1000 / ≤ 2100 ms** | ⚠ **the flat `p95 ≤ 2000 ms` is not achievable on Turkish mobile as architected and would fail from day one** — mid-LTE p95 arithmetic sums to **2055 ms**. `residency_tr_models` removes 141 ms p95 of vendor-hop RTT and brings it to **≈ 1914 ms** |
| `residency_tr` p50 | ≤ 900 ms | **≤ 1300 ms** (≤ 900 ms with a small Talker) | v1.4 put a 30B MoE in the Talker slot; Layer A only needs to speak ≤ 2 sentences. Note the **transport** half of this profile is a **win**, not a cost |
| RED preemption | ≤ 300 ms p99 *in production* | **≤ 300 ms p99 in production — via the data channel, not the audio path** | ⚠ **revised.** Downlink p95 is 206 ms before the clip's first sample is even scheduled, so a streamed RED script cannot hold 300 ms at p95. The script is **pre-positioned on the device** and triggered by a data-channel message (`03 §4.6` inv. 4). The old "fires continuously from day one and gets silenced" objection is answered by changing the mechanism, not the target |

**The transport lever is bigger than the VAD lever, and it is measured.** Running SFU + TURN in Türkiye is worth **−39 ms p50 / −47 ms p95** on media alone and **−156 / −188** once the models move too — more than dropping `min_silence_duration` 250 → 150 ms (**−100 ms**, and that drop is now **adaptive**: 150 ms when measured uplink jitter p95 < 30 ms, 250 ms otherwise, so we do not cut patients off in the waiting room — `03 §4.5b`). v2.0's earlier **−70 ms** estimate had the right sign and was ~1.8× overstated. This is the *opposite* of v1.4's "use EU regions, LiveKit Cloud EU" prescription — and it is free KVKK benefit, because media never leaves Türkiye.

> ⚠ **Withdrawn: "on 4G, p95 RTT runs 3–4× p50."** Measured Türkiye p95/p50 is **2.23** — *tighter* than Germany (2.42), Poland (2.43) or Spain (2.69). More generally, **"Turkish networks are bad" is false and no argument here may lean on it** (`00 §2`). Same dataset, same quarter, same method: Türkiye p50 **22 ms** against Germany 24, UK 31, Italy 32, Spain 29 — **the joint-lowest median mobile RTT of the set.** The honest statement is *"mobile radio has a 2× tail everywhere, and Türkiye's is at the better end of Europe."* The real risk is **loaded** latency, not idle latency: 646 ms p50 / 1747 p95 under downlink load, 835 / 2232 under uplink load (`03 §4.5.2`).

### Safety
⚠ **The false-RED ≤ 2 % target is deleted.** It is arithmetically incompatible with the rule set (~30 RED rules at ~0.1 % each ≈ 3 %; the Ottawa SAH criteria carry ~15 % specificity *by design*; `rf.dyspnoea_rest` alone plausibly exceeds 2 % because "speaking in short sentences" is the *baseline* for advanced COPD). Worse, a hard ceiling creates continuous pressure to weaken rules — the exact failure the monotonicity guardrails exist to prevent. The symptom-checker literature is unambiguous: apps that became less risk-averse between 2015 and 2020 ended up missing **over 40 %** of emergencies.

Replaced by three:
- **Primary metric: misses, not false positives.** Zero clinician-confirmed missed time-critical conditions, measured by **chart-linked follow-up of a sample of GREEN sessions** — not clinician self-report, which under-detects.
- **Un-bundle RED into tiers**, so a ceiling applies where it belongs: `EMERGENCY_NOW` (call 112 — target ≤ 0.5 %, tight) · `SAME_DAY_ACIL` (several % is acceptable) · `EXPEDITE`. The current binary forces every rule to either shout 112 or say nothing.
- **Per-rule false-RED rates with per-rule review.** The console's false-RED queue already exists; make it the unit of governance.

⚠ **New:** per-rule **extraction sensitivity and specificity against a Turkish clinical reference standard**. A deterministic rules engine over probabilistic inputs is not deterministic — v1.4 audits the LLM's *output* while treating its *input to the safety layer* as ground truth. Must cover agglutinative negation and evidentiality (*"ağrım yok değil hani"*, *"kanama yoktu, sadece siyahtı"*, `-mış`), second-language Turkish speakers, and a **"did not understand" state distinct from "no"**.

### Coverage & learning
⚠ **G7 softened.** From *"100 % of booked branches served by an L1+ pack"* to *"no patient ever runs on bare `base.intake`, and every patient is evaluated against the universal `base.life_threat` set."* The former is true only in a sense that will not survive contact with a cardiologist: `cluster.medical` puts ~30 branches from Kardiyoloji to Dermatoloji to Tıbbi Genetik through a single HPI.

### Operability
⚠ The self-hosting **release gate applies from P2**, when a tenant actually requires it — not from P0. Build the **registry and the gate** in P0, because that is the artefact hospital CIOs audit; stand up the stack when it is needed.

### Unchanged
Activation 45 % · fast-mode completion ≥ 80 %, median ≤ 4 min · clinician acceptance ≥ 70 % → ≥ 85 % · must-ask coverage ≥ 95 % · Turkish medical WER ≤ 10 % · CSAT ≥ 4.3, NPS ≥ 40 · note ready ≤ 60 s · SLO attainment, MTTR < 4 h, change-failure rate < 10 % · vulnerability SLAs · zero PHI in logs.

---

## 5. Regulatory & partnership track — re-planned

### P0 — starts now, not later
- **Written notified-body classification opinion.** ~€5–15k, and it determines the entire Stage B budget and timeline. Do this **before INT-217's scope is fixed**; a IIa → IIb surprise at classification review is a ~9–12 month schedule break.
- **Begin the clinical-investigation dossier.** Non-clinical validation of the triage engine (TCKAY m.5/2(a) requires it *before* submission), protocol, ICF(tr), a named PI holding uzmanlık or doktora in the field, **the qualifying university site**, and insurance.
- **Clear the instrument licences.** C-SSRS: written scope confirmation from RFMH / Kelly Posner. WHO-5: commercial permission via who.int/copyright, or drop it. HAQ-DI: clear the **Turkish translation** with Küçükdeveci's group and confirm the "unmodified" condition against our mobile layout.
- **A counsel question that is separate from Rule 11.** May device-off mode say, immediately after a symptom question, *"Bu belirtiyi bildirdiniz. Bu tür belirtilerde beklemeyin — 112'yi arayın veya en yakın acile gidin"*? That is arguably health signposting, not automated urgency classification of an individual. **If the answer is no, we must stop asking red-flag questions in device-off mode** — asking and then answering with silence is iatrogenic false reassurance, and worse than not asking at all.

### P1
VERBİS registration · DPIA v1 · Art. 9 standard contracts with 5-iş-günü Board notification · hospital DPA template · **KAEK submission**.

### P2
**TİTCK application** · external pen-test · ISO 27001 gap assessment · KTS (SBYS) registration.

### P3
e-Nabız application to SBSGM · **public-hospital** HBYS vendor partnership (Akgün / Sisoft / Probel / **Monad**) — ⚠ **Tiga removed: it is not on the Aktif HBYS Listesi at all**, it is an interoperability contractor, so three of the four former targets were right and the fourth was a category error; private groups are reached through their own technology arm instead (§1) · ISO 13485 QMS · MoH AI Approval Unit engagement.

### P4
Class **IIb** conformity assessment · clinical evaluation report per MDCG 2020-1 · ÜTS registration under TCKKD-KLVZ-03.

### ⚠ Missing from v1.4's statutory map — added
- **Sağlık Hizmetlerinde Tanıtım ve Bilgilendirme Faaliyetleri Hakkında Yönetmelik** (RG 32263, 29.07.2023; reportedly replaced 12.11.2025 — verify the new RG number)
- **Tıbbi Cihaz Satış, Reklam ve Tanıtım Yönetmeliği** (RG 29001, 15.05.2014, amended 26.05.2023)

Together these prohibit promoting uncertified device functionality and heavily restrict health-service advertising to the Turkish public — including by parties without a health-service licence, i.e. us. *"Coming soon: AI triage"*, pilot press releases and investor decks that reach the public are all exposure. **We have PolicyGuard for in-app strings and no claims-control gate for marketing.** This is the single most likely source of an early enforcement letter for a consumer health app in Türkiye.

Also added: **KVKK Özel Nitelikli Kişisel Veriler Rehberi (26.02.2025)** — the current special-category posture rests on Karar 2018/10, which predates the m.6 rewrite by six years; **KSVY amendment RG 33096, 03.12.2025**; **ETBİS registration** for the paid tier; **TCK 133 and 134** for recording consent.

---

## 6. Research tracks

1. **Turkish medical ASR benchmark** — ⚠ **upgraded from a research track to a GATE.** `00 §5` Q9: a 3–5 h Turkish **spontaneous** clinical-speech eval set with code-switched English medical terms, dosages and units. FLEURS-tr and Common Voice tr are **both read speech** and both overstate performance on the real workload; the only published Turkish WER in this project (11.17–12.34) is read speech, and the only Turkish *medical* ASR artefact in existence was trained on **3 speakers and 120 clips**. No vendor publishes Turkish per-language numbers, so this must be built. ~2 weeks, and **it unblocks the ASR, TTS and `03 §4.5` budget questions at once** (HB-C10).
2. **Turkish acoustic-biomarker validation** — ⚠ **promoted, not deferred; and rewritten 27 Aug 2026.** The `acoustic` lane is retained and **Kintsugi DAM is dropped (D14)** — this track now validates **our own ordinal head**, not a vendor's orphaned model. It remains the **gate** on the lane becoming clinician-visible: its lead time, not the engineering, determines when the lane can ship, and D4 means there is no shadow mode to ship in the meantime. Three cheap things come first, at ~€0 and before any study (`00 §5` Q11): **(a)** the **28.8 % band-instability on a prompt change alone** needs no Turkish data — pre-specify it as a limitation and fix the elicitation prompt; **(b)** ablate the text branch and re-baseline, because a **text-only BERT model beat the audio-only model** in the vendor's own paper, which may change what the study should measure at all; **(c)** score **acted-depression controls** as a free adversarial specificity set — a model that scores acted depression like real depression is doing acting-detection. ⚠ **Scale reality check: the DAM-class validation study is n ≈ 800, €120–250k, 12–18 months. The 300-session P2 pilot cannot validate this lane — it is off by ~3×.** And there is **no Turkish vocal biomarker model in existence**, open or commercial, so there is nothing to adopt and no baseline to beat.
3. **Pre-visit note usefulness (RCT-lite)** — ⚠ now gates the `considerations[]` block. An AI-generated pattern list rendered above the clinician's own reasoning is a differential diagnosis functionally, and it will anchor. Do not ship it until a prospective study shows it improves rather than degrades diagnostic accuracy.
4. **Protocol library** — clinician-authored packs; open-source the DSL and base protocols (Apache-2.0).
5. **Conversational feel study** — ⚠ **rewritten 27 Aug 2026.** `s2s_cloud` is withdrawn and `cascade_fast` no longer exists, so the comparison is **`residency_tr` vs `typed`** — which is the comparison that was always worth making, because `typed` is the kill-switch fallback and the question is what the voice path actually buys.
6. **Voice-based psychiatric signal validation** — unchanged, research-only.
7. ⚠ **NEW — Turkish clinical-extraction accuracy.** Per-rule sensitivity and specificity of slot extraction against a clinician-labelled Turkish reference standard. **Gates P1 exit**; without it the triage engine's inputs are unvalidated and the "deterministic rules engine" claim is unsupported.
8. ⚠ **NEW — network telemetry from session one.** Four transport unknowns are **UNVERIFIED** and none is obtainable from a public dataset: **Turkish mobile packet loss**, **hospital guest wifi**, the **handset mic-capture buffer distribution**, and the **NetEq concealment-versus-delay curve** (`03 §4.4a`, `§4.4b`, `§4.5.1`, `§4.5a`). All four are cheap to collect in production from `RTCStatsReport`. Re-derive the `02 §8.1` per-profile NFRs after 100 sessions.

---

## 7. Assumptions register (re-verified 25 Aug 2026)

| assumption | status | evidence |
|---|---|---|
| ~~Soniox `stt-rt-v5`~~ — ⚠ **MOOT under self-hosting.** The finding was verified; the pin is **displaced** (`00 §1`). Retained as the record of what was lost: its structured `ContextObject` medical-term biasing and its **free bundled realtime diarization**, the latter load-bearing for the acoustic lane's two-estimator gate | **verified, then displaced** | v4 aliases to v5, removed 30 Jun 2026 with auto-routing |
| ~~Soniox TTS is full-duplex Turkish~~ — ⚠ **MOOT under self-hosting** | **verified, then displaced** | the model is **`tts-rt-v2`**; `tts-rt-v1` removed 31 Aug 2026 |
| LiveKit Turn Detector v1 is audio-based with Turkish among 14 languages | **verified precisely** | `LOCAL_LANGUAGES` has exactly 14 keys incl. `"tr": 0.2550` |
| …and is available self-hosted on CPU | **FALSE** | `detector.py:59` resolves to **`v1-mini`** unless hosted; `v1` requires `cloud_opts`; **backchannel probabilities are cloud-only, so backchannels are impossible in `residency_tr`**; and using v1 streams patient audio to LiveKit Inference — **an undeclared PHI egress hop**, absent from the allow-list, the DPIA and the transfer register |
| The `livekit-agents` code snippet as written | **verified, with a migration warning** | all packages at 1.7.0 and the imports are valid — but `turn_detection`, `preemptive_generation`, `allow_interruptions`, `min/max_endpointing_delay` and `keyterms_options` are **deprecated in 1.7.0** → `turn_handling=TurnHandlingOptions(...)`, `stt_context_options=STTContextOptions(...)`. Writing P1 against the old signature buys an immediate migration |
| Open, commercially usable Turkish TTS with ~200 ms streaming | **partly false — and superseded by a better answer.** ⚠ The TTS pin is now `openbmb/VoxCPM2` (`03 §4.9.1` rows 10–11): Apache-2.0, ungated, **the only model in the survey where Turkish is *evaluated* rather than listed**, TTFT 0.14 s, official vLLM-Omni serving. Chatterbox is held as a third option only. **Both candidate TTS models ship a Turkish-hostile normaliser that must be disabled** | Chatterbox Multilingual V3 (10 Jun 2026, MIT, 23 languages incl. tr) is real, but **PyPI ships only `chatterbox-tts` 0.1.7**, and the ~200 ms figure belongs to Resemble's **paid hosted service**. The open weights publish no streaming latency. `residency_tr`'s TTS budget is an **open measurement**, not an assumption |
| Open Turkish streaming ASR with context biasing | **verified, and better than assumed** | Qwen3-ASR ships as **0.6B and 1.7B** (Apache-2.0, 28 Jan 2026, 52 languages incl. tr). The 0.6B is the CPU-budget option and was missing from v1.4 |
| Expo SDK 57 is safe to pin | **verified, with a hard caveat** | expo `latest` = 57.0.16; SDK 57 → RN 0.86.2 / React 19.2.3 exactly. **But SDK 57.0.0 still carried the Hermes V1 memory regression** — expo/expo#46519 is still open and PR #48887 states the fixed hermes versions "weren't backported… (including on 57)". **Pin `expo@57.0.9+` and the exact RN patch, gate CI on `npx expo-doctor`, keep `useHermesV1: false` as a live fallback.** A 1.1 GB-RSS app is an OOM-kill on the mid-range Android a Turkish hospital kiosk will be |
| Node ≥ 22.13 | **false** | **Node ≥ 20.19.4** |
| Device attestation is available in Expo | **effectively false** | `expo-app-integrity` was last published **2023-04-09** with peers pinned to SDK 48/49-era — **it cannot install alongside SDK 57**. `react-native-app-attest` is iOS-only. **DPoP has no Expo module at all.** Budget **4–6 engineer-weeks** for a first-party config-plugin; this work is currently invisible in the backlog |
| Certificate pinning in the Expo managed workflow | **partly true** | no first-party API; needs a config-plugin (TrustKit / OkHttp), a dev or production build, and expo-dev-client's network inspector disabled on iOS. A `fetch`-patching shim will **not** pin the WebRTC/DTLS path — i.e. most PHI traffic |
| De-identification before every cloud model call | ⚠ **the objection dissolves — there is no cloud model call** | The finding stands as an argument and is worth keeping, because it is *why* self-hosting is the right control: in a cascade the first cloud call **is the STT audio stream**, and audio cannot be Presidio-redacted, so the control could only ever have been contractual — and a contractual control is not a technical one. Self-hosting makes it structural. De-identification still applies to Loop-2 exports and any dev-path model call. Also **spaCy ships no Turkish model** (`tr_core_news_sm`/`md` both 404), so Presidio needs the `transformers` or `stanza` extra plus custom recognizers |
| < 0.1 % de-identification leak rate | **unfalsifiable as defined** | measured "on the synthetic corpus" *we author*. Realistic conversational-Turkish recall is 0.85–0.95 given oblique cases (*Ahmet'in*, *Ayşe'ye*); 3–8 identifiers per intake ⇒ **≈ 0.3–1.0 expected leaks per session**. Redefine as **recall per entity class on a held-out, human-labelled, real-transcript corpus** with a published confusion matrix: TCKN ≥ 0.99 (checksum-verifiable), names and addresses ~0.90, stated honestly |
| MinIO is a safe root of trust for a 10-year WORM audit log | **at risk** | newest Docker Hub tag is **RELEASE.2025-09-07** (~12 months stale), and the named fallback **Garage does not implement S3 Object Lock** — silently voiding the WORM guarantee |
| MedGemma is open-weights and self-hostable in Türkiye | **licence-false — and now a deleted pin, not merely a risk** | **every** MedGemma model, 1.5-4B included, is **Health AI Developer Foundations** licensed — none is Apache-2.0. This conflicts with the CI Apache/MIT/BSD allow-list, which has no verdict for HAI-DEF |
| MedGemma 27B "1.5" exists | **false** (unchanged) | 1.5 is 4B only |
| Open-weights S2S with Turkish speech **output** | **not yet** (unchanged) | Qwen3-Omni is Turkish speech-**in** only; Qwen3.5-Omni is API-only |
| ~~OpenAI Realtime is EU-residency eligible for `s2s_cloud`~~ — ⚠ **MOOT: `s2s_cloud` is withdrawn** | **partly** | `/v1/realtime` is an eligible EEA+CH endpoint, **but tracing for `/v1/realtime` is not EU-residency compliant**, and residency requires ZDR / Modified Abuse Monitoring approval. Also **GPT-Realtime-2 is superseded by GPT-Realtime-2.1 (6 Jul 2026)** |
| ~~Vertex Live API residency controls are contractable~~ — ⚠ **MOOT: `s2s_cloud` is withdrawn** | **unverified** | 70 languages and affective dialog are confirmed; the residency terms are not. Confirm with Google before `s2s_cloud` leaves the flag |
| **Rule 11 → Class IIa** | **FALSE — the most consequential correction in the bundle** | **IIb for both device functions.** MDCG 2019-11 Annex IV states the depression-scoring case is IIb almost verbatim; IMDRF N12 defines "drive clinical management" as including *triage*; and the failure mode to assess is the **false negative**, which is the Class III limb |
| KAEK and TİTCK can run in parallel | **false** | TCKAY m.8/2 — the ethics decision is submitted **as part of** the TİTCK application |
| The Acıbadem pilot hospital can host the investigation | **false as stated** | TCKAY m.5/6 restricts sites to **university** research centres or MoH training & research hospitals. Name the qualifying university centre |
| TCKAY covers "observational" studies | **terminology false** | TCKAY has no *gözlemsel* category; only **retrospective** studies are out of scope (m.2/2), and the post-market route (m.10) is defined **only for CE-marked devices** — unavailable to us |
| C-SSRS is free with Columbia permission | **false** | **Clario holds an exclusive electronic licence.** Training is not the issue; the electronic sublicence is |
| WHO-5 is free to use | **false since 2024** | **CC BY-NC-SA 3.0 IGO — NonCommercial**, plus copyleft ShareAlike |
| PHQ-9 / GAD-7 are Turkish-validated | **weaker than assumed** | the PHQ-9 Turkish evidence is a **reliability study only** (n=96, no sensitivity/specificity, no validated cut-off, journal not PubMed-indexed). **PHQ-2 and GAD-2 have no Turkish validation at all** — do not describe them as "Turkish-validated". GAD-7's Turkish cut-off is **8**, not 10 |
| NICE NG51 is the sepsis reference | **replaced 19 Nov 2025** | by **NG253 / NG254 / NG255**. Each only *partially* replaces NG51 — and **NG255 covers pregnant or recently pregnant people of any age, carved out of both others**, so the engine must route on `{age_band, pregnancy_status}`. All three have updates in progress (PCT, PEWS, MEWS) |
| Surviving Sepsis Campaign 2021 is the reference | **superseded 23 Mar 2026** | **SSC 2026** (Crit Care Med 2026;54(4):725–812 / Intensive Care Med 2026;52(5):863–936). The qSOFA position did **not** reverse — it was re-expressed positively: *"we recommend using NEWS, NEW2, MEWS, or SIRS **over** qSOFA as a single tool to screen for sepsis"* (strong, moderate certainty). New Statement 5 directly supports our disjunctive rewrite: *"Sepsis is a clinical diagnosis and should not be ruled in or ruled out using a single biomarker or diagnostic test"* |
| ACC/AHA 2017 hypertension is the reference | **superseded 14 Aug 2025** | **2025 AHA/ACC multisociety HBP guideline** — and **"hypertensive urgency" is a retired term**, replaced by **"severe hypertension"** (>180/120 *without* acute target organ damage). **Class 1, LOE B-R: treat it in the OUTPATIENT setting.** Any rule routing asymptomatic BP >180/120 to Acil now contradicts a Class 1 recommendation. Note ≥ 4 published corrections exist — cite the corrected version |
| IDSA 2010 is the febrile-neutropenia reference | **archived** | idsociety.org shows an explicit ARCHIVED banner. The only CURRENT IDSA-branded product is ASCO/IDSA 2018, whose scope is *outpatient low-risk only* and does **not** replace the inpatient content. **Cite NICE CG151 instead** — it is current, and NG253 actively defers to it |
| GIRFT cauda equina pathway (Feb 2023) | **nine revisions stale** | current version is **March 2026**. GIRFT keeps the "February 2023" title date and *appends* update dates, so a "Feb 2023" citation looks superficially plausible — **exactly the trap the guideline-currency job must catch** |
| EAU acute scrotum, "operate within 6 hours" | **misattribution** | current edition is **2026**. EAU's actual strong recommendation is *"urgent surgical exploration in all cases… as soon as possible"*; the 4–6 h window is **descriptive pathophysiology**, not a recommended target |
| USPSTF recommendations are current guidance | **true, but qualify the date** | all three (depression B, suicide risk **I — insufficient evidence**, anxiety B/I) stand as at **20 Jun 2023**. But USPSTF is mid-overhaul: meetings cancelled Jul 2025, Nov 2025 and Mar 2026; **both co-chairs dismissed 11 May 2026**; ~a dozen drafts stalled. Use a dated "as at" qualifier, never open-ended "current USPSTF guidance" |
| WHO opioid-overdose guidance is stable | **replacement imminent** | selected recommendations updated **2 Apr 2026**; the full guideline is expected late 2026 / early 2027. Do not build fixed content assuming the 2014 text persists |
| Ottawa SAH reduces unnecessary imaging | **false** | 2025 meta-analysis (Acad Emerg Med 32(10):1111–1121): pooled sensitivity 99 % (92–100), **specificity 23 % (16–32)** — and **neither Ottawa nor the Emerald rule meaningfully reduces CT utilisation** (pooled OR 1.15, 95 % CI 0.62–2.13). The rule is designed to be non-specific; budget for that in the false-RED tiering rather than treating it as a defect |
| NICE NG126 as cited (2019) | **stale** | **updated 17 Jun 2026** with a substantive anti-D immunoglobulin reversal |
| NICE NG59 covers cauda equina | **false** | NG59's Context chapter explicitly excludes CES. The authority is the **GIRFT national CES pathway (Feb 2023)**. NG59 was also **updated 29 Jul 2026**, withdrawing its psychological-therapy recommendations |
| NICE "Early Value Assessment (EVA)" | **renamed** | now **early-use HealthTech guidance** under **PMG48** (14 Jul 2025, updated 17 Dec 2025). ECD7 remains current but frozen since Aug 2022 and is *not* referenced by PMG48 — "we meet NICE ESF" and "we are ready for NICE HealthTech evaluation" are now two separate claims |
| MHRS ≈ 79 branches | **verified, attribution corrected** | Minister Memişoğlu via Anadolu Ajansı, **26 Nov 2025**. The "Feb 2025" attribution has no traceable source |
| e-Nabız 28k facilities / 240k physicians | **unsourced — removed** | no Ministry or e-Nabız primary source found. Do not use in investor or tender material |
| Epic "Smarter Check-In" arrives 2027 | **verified — the strategic thesis holds** | this is the load-bearing competitive claim and it stands |
| Epic Cosmos Curiosity is GA | **false** | launches **March 2027** |
| Langfuse is self-hostable with an MIT core | **verified** | acquired by ClickHouse 16 Jan 2026; still open source and self-hostable |
| OpenBao, Coraza, CrowdSec, Wazuh, Falco, Kyverno, Harbor, Sigstore, Presidio are self-hostable OSS | **verified** | OpenBao MPL-2.0 v2.6.2 (18 Aug 2026). **Presidio still needs Turkish recognizers built and measured** |
| Turkish mobile networks are a latency problem for this product | **FALSE — withdraw any argument leaning on it** | Türkiye mobile RTT p50 **22 ms** vs Germany 24, UK 31, Italy 32, Spain 29 — joint-lowest median of the set, with a **tighter** tail (p95/p50 = 2.23) than Germany, Poland or Spain. 674,774 Ookla tests / 338,416 devices, 2026 Q2 |
| GPU capacity is procurable in Türkiye when `residency_tr_models` is needed | **thin — gate on a contract, not a date. ⚠ But the *scale* framing was wrong: this is a 1-to-8-GPU problem, not a 120–160 MW problem** — cache-aware streaming ASR does 240 realtime streams per H100 where buffered Parakeet 1.1B manages 14, a 17× difference that collapses what would otherwise dominate. **Buy one card and build the pilot**; the contract gate applies only to the 50-concurrent tier. Two of our own numbers here are also corrected: Turkish DC capacity is **~250 MW, not 120–160**, and **KSVY does *not* mandate in-country hosting** | No hyperscaler GPU in-country: AWS İstanbul Local Zone is C7i/M7i/R7i only, Azure has no TR region, Google Cloud TR has no date and no accelerator plan, Huawei is Ascend-not-CUDA, Türk Telekom GPUaaS publishes nothing. Reseller H100/H200/A100 claims are **UNVERIFIED**. National commercial DC capacity **~120–160 MW at end-2025**, with EMRA licensing above the exempt generation threshold and June 2026 amendments restricting unlicensed surplus sales |
| Turkish mobile packet-loss rate | **UNVERIFIED — no public dataset carries it** | Opensignal is paywalled (403). 3GPP targets ≤ 1 % residual BLER so steady state is normally < 0.5 %, but **the losses that matter are handover bursts, which are guaranteed rather than probabilistic.** Instrument from session one; re-derive after 100 sessions |
| Hospital guest wifi is a usable media path | **UNVERIFIED — and probably the wrong default** | Turkish mobile p50 is 20 ms in İstanbul, 19 ms in Ankara, better than most enterprise guest wifi anywhere. `03 §4.4b` **prefers cellular inside a hospital**. Probe the pilot site before P2 |
| P0 fits in 3 weeks | **false** | 91 issues ÷ 15 working days = 6/day, each with a recorded red run, a green run, three gate suites, an evidence file and a PR — before counting ≈ 68 hours of serial CI. **12–20 weeks.** |

---

## 8. Cross-reference note — where this plan defers (files not owned by this one)

Added 27 Aug 2026, because four of the corrections above were caused by the same failure: **a fact restated in two places drifts, and the copy nobody is looking at is the one that gets used.**

- **`00_STATE.md` is the authority.** Where this roadmap disagrees with it, `00` wins and the line here is a defect to fix — not a difference of emphasis.
- **`03 §4.9.1` is the single source of truth for the model stack.** Nothing in this file pins a model. Where a phase, KPI or assumption row used to name one, it now points at a row number, and **a model that is not in that table is not pinned** whatever a deploy guide says.
- **`HUMAN_BLOCKERS.md`** carries every non-technical blocker with its owner and what it holds up. Phase gates reference it by `HB-*` id rather than restating the ask, so there is exactly one place the owner has to look.
- **`07 §3.3` (DoD) and `07 §3.4` (TDD)** are the per-issue working method; **§1a above is the phase-scale equivalent**. They are deliberately different documents: the per-issue DoD is what CI can check, and the phase gate is mostly what it cannot.
- **`10 §9.1`** catalogues invariants 12–49 (1–11 are in `03 §4.6`). ⚠ **See `10 §9.2` — 50–65 are RESERVED and enforce nothing; only 53 has a written specification and it is prose, not a test. A citation to any other number in that range is a build-review finding.** Invariants 50–65 are proposed for the data-import path and are not yet catalogued**, while `03 §4.9.6` and `§10` already cite **invariant 53** as though it exists. Cataloguing that range is a prerequisite for the P1 records-ingestion work, and it is not currently an issue in the backlog.
