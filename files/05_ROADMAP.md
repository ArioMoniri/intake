# 05 · Roadmap — v2.0 (rebuilt 25 Aug 2026 after external verification)

> **What changed from v1.4, and why.** v1.4 was a *date-driven* plan: P0 in weeks 0–3, P1 by week 12, a hospital pilot by month 7. Four independent verification passes — clinical, architecture, vendor-facts and Turkish regulatory — established that those dates were not achievable and, more importantly, that **the calendar was never the binding constraint**. Three things bind, in this order:
>
> 1. **Your review capacity.** 101 of 175 issues sit behind a human gate.
> 2. **CI throughput.** 175 issues × a realistic 35–60 min PR gate ≈ 100–175 CPU-hours. The autonomous loop is bounded by CI, not by the model.
> 3. **The clinical-investigation clock.** 7–12 months, strictly sequential, and not compressible by adding engineers.
>
> v2.0 is therefore **gate-driven**: phases advance when evidence exists, not when a date arrives. Every duration below is a forecast under stated assumptions, never a commitment, and each phase names the artefact that ends it.
>
> **The single most consequential correction: the medical-device classification is Class IIb, not Class IIa** (`06 §0.3`). That re-prices Stage B and should be resolved before anything else is budgeted.

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
TCKAY (RG 31890, 08.07.2022): **m.8/2** requires the ethics decision to be submitted *as part of* the TİTCK application — they cannot run in parallel. **m.5/2(a)** requires non-clinical validation *before* submission (for software, a documented bench and retrospective validation of the triage engine — a work package v1.4 did not show). **m.5/6** restricts sites to a **university** health application & research centre, an approved university-affiliated R&D centre, or an MoH training & research hospital — **a general private Acıbadem hospital does not qualify.** The study must sit at Acıbadem Mehmet Ali Aydınlar Üniversitesi's research centre; ATADEK is that university's committee, so this is workable, but the site must be named.

| phase | statutory clock | realistic |
|---|---|---|
| Non-clinical validation + protocol + ICF(tr) + Annex XV Pt II + risk file | — | 8–14 wk |
| Insurance (parallel) · site + PI + budget contracting (parallel, often the real bottleneck) | — | 2–4 wk · 4–8 wk |
| ATADEK ethics | ~30 d | **4–12 wk** (monthly agendas) |
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
| **P1 Fast mode, device-off** | Turkish voice intake E2E (`cascade_fast`), records ingestion, patient summary, clinician note via Doctor Link, CSAT/NPS, real telemetry | 20 internal users × 3 specialties · **client-side measured** round-trip meets §4 targets · note acceptance ≥ 70 % · DPIA v1 signed · Art. 9 standard contracts signed **and notified within 5 iş günü** for every cloud vendor in use | **+10–16 weeks** |
| **P2 Hospital pilot** | Detailed mode, check-in, clinic console, FHIR connector, companions, top-10 deep packs | Pilot at one hospital group · ≥ 300 real pre-visits · clinician read rate ≥ 80 % · CSAT ≥ 4.2 · zero PHI incidents · external pen-test passed, findings closed | **+4–6 months** |
| **P2b Clinical investigation** *(parallel track — starts in P0)* | The only lawful route to `device_functions=on` | ATADEK approval **then** TİTCK permission, recorded against a named study id **and protocol version** · insurance in force · first participant enrolled | **≈ 9 months from protocol drafting** |
| **P3 The record that travels** | e-Nabız application, HBYS.API connector, consented visit recording, longitudinal timeline, **openEHR added as an export**, `residency_tr` when a public tenant signs | 2nd hospital group · e-Nabız sandbox or a formal decision · published evaluation report | **+6–9 months** |
| **P4 CE + scale** | Class **IIb** conformity assessment, ÜTS registration, B2B2C white-label | Notified-body certificate · `device_functions=on` commercially | Gated on P2b evidence |

> **P3 is currently unplanned.** It holds 2 issues while its own description covers e-Nabız, HBYS.API, diarised visit recording and the longitudinal timeline. Either scope it or stop calling it a phase.

---

## 2. What P0 builds — and what was cut

### 2.1 Cut from P0/P1 (≈ 29–39 engineer-weeks recovered)

| Cut | Why | Recovered |
|---|---|---|
| **openEHR / EHRbase → P3; FHIR-only until then** | **No P0/P1 feature issues an AQL query.** Every real consumer — Doctor Link, HBYS.API, e-Nabız, SGK, the clinician note, the app — is FHIR / ICD-10 / LOINC / ATC / text. `03 §7` already concedes SNOMED CT is unavailable in Türkiye, removing much of openEHR's semantic advantage before you start. No Python library generates Operational Templates; OPT authoring is a Java / Archetype-Designer activity. And round-trip goldens over a lossy openEHR↔FHIR mapping would pass only because we wrote them to match the mapper — **a test that cannot fail, which `07 §TDD` explicitly forbids.** **Keep the archetype-path annotation on every slot**: it costs nothing and *is* the migration plan. | 14–20 wk |
| **`residency_tr` → P3** | `06` makes it mandatory for **public** hospitals. The pilot is Acıbadem — **private**. This builds a GPU datacentre to run at < 1 % utilisation for 300 sessions. Keep the gateway abstraction and profile-parity tests so the swap stays a config change. | 8–12 wk + €1.2–2.5k/mo |
| ~~`affect` + `acoustic` observer lanes~~ — **NOT CUT. Retained and hardened.** | ⚠️ An earlier draft of this table proposed cutting these on cost and PHI-egress grounds. **That was based on a misreading of `03 §4.7` and is withdrawn.** The `acoustic` lane is a **Kintsugi DAM-class model with open weights, self-hosted, in every profile** — there is no vendor, no second audio stream and no cross-border transfer. And `affect` **already has a self-hosted implementation specified** (open SER, emotion2vec-class) for `residency_tr`; the vendor route applies only to `cascade_fast`. `linguistic`, `asr_quality` and `engagement` are local in all profiles. The cost and egress objections therefore reduce to one narrow change — **run the open SER path in all profiles, not only `residency_tr`** — which removes the second vendor stream, the doubled STT cost and the transfer simultaneously. Latency was never an objection: the lanes are off the critical path by design, with an invariant that tests it. | — (see §2.3) |
| **`s2s_cloud` → P3** | It cannot meet the contract ADR-010 says all three profiles share: no clip cache, no verbatim scripted text, and PolicyGuard degrades to *after-the-fact* retraction — meaning the patient already heard the diagnostic sentence. It is faster **and** less safe, presented as an upgrade. | 3 wk |
| **Heavy security tier → P1** | Defer Wazuh (12 GB + a part-time SRE), Harbor + Kyverno + cosign admission (there is no cluster in P0), CrowdSec, the service mesh, MobSF. **Keep every invariant** — they are enforced by tests, and the tests are what P0 ships. | ~4 wk |

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
| 2 | **Raw audio at rest in memory.** The rolling PCM window is visible in a core dump, in swap, and in a crash report — and the product ships GlitchTip. `audio_retention_guard` is a static scan plus a fake-fs test, and **a fake-fs test cannot see a core dump** | `RLIMIT_CORE=0`, `mlock` on the lane buffer, explicit zeroization after scoring — each with an assertion, not a convention |
| 3 | **Turkish calibration.** DAM is US-English at ~71 % sensitivity/specificity. `03 §4.7` already says *"Turkish calibration required before any use"* — that study needs designing, not deferring | Design it: n, labels, ethics route, and the AUROC and calibration that would move the lane from research-flag to clinician-visible. The Turkish audio-visual bipolar corpus (Çiftçi et al., ACII Asia 2018) is a secondary reference, not a substitute |
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
v1.4's budget table omitted **every network term**. Recomputed for Istanbul → Frankfurt on 4G, including radio access, SFU hops, vendor round-trips and the client jitter buffer:

| metric | v1.4 | ⚠ v2.0 | why |
|---|---|---|---|
| scripted p50 / p95 | ≤ 400 / ≤ 1200 ms | **≤ 550 / ≤ 900 ms** | structural floor is 280 ms (the mandated 250 ms VAD + EOU) + 140 ms transport = **420 ms before any decision-making happens**. Sub-420 ms is arithmetically impossible with a Frankfurt SFU |
| dynamic p50 / p95 | ≤ 700 / ≤ 1200 ms | **≤ 1000 / ≤ 2000 ms** | measured build-up ≈ 975 ms; on 4G, p95 RTT runs 3–4× p50 and NetEq grows to 150–250 ms under loss |
| `residency_tr` p50 | ≤ 900 ms | **≤ 1300 ms** (≤ 900 ms with a small Talker) | v1.4 put a 30B MoE in the Talker slot; Layer A only needs to speak ≤ 2 sentences |
| RED preemption | ≤ 300 ms p99 *in production* | **≤ 300 ms agent-side (fake clock); ≤ 600 ms p99 in production** | the same ~140 ms of transport applies, plus a jitter-buffer flush. **As written, this alert fires continuously from day one of P1 and will be silenced — which is how you lose the one alert that matters** |

**Two changes would nearly recover the headline numbers:** drop `min_silence_duration` from 250 → 150 ms and let the audio turn detector carry the false-positive load (**−100 ms**); and **run the SFU in Türkiye even for `cascade_fast`** (**−70 ms**). LiveKit server is Apache-2.0; only STT / LLM / TTS need to leave the country, and those are agent↔vendor hops, not media hops. Together: dynamic ≈ 800 ms, scripted ≈ 330 ms. This is the *opposite* of v1.4's "use EU regions, LiveKit Cloud EU" prescription — and it is free KVKK benefit, because media never leaves Türkiye.

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
VERBİS registration · DPIA v1 · Art. 9 standard contracts with 5-iş-günü Board notification · hospital DPA template · **ATADEK submission**.

### P2
**TİTCK application** · external pen-test · ISO 27001 gap assessment · KTS (SBYS) registration.

### P3
e-Nabız application to SBSGM · HBYS vendor partnership (Akgün / Sisoft / Probel / Tiga) · ISO 13485 QMS · MoH AI Approval Unit engagement.

### P4
Class **IIb** conformity assessment · clinical evaluation report per MDCG 2020-1 · ÜTS registration under TCKKD-KLVZ-03.

### ⚠ Missing from v1.4's statutory map — added
- **Sağlık Hizmetlerinde Tanıtım ve Bilgilendirme Faaliyetleri Hakkında Yönetmelik** (RG 32263, 29.07.2023; reportedly replaced 12.11.2025 — verify the new RG number)
- **Tıbbi Cihaz Satış, Reklam ve Tanıtım Yönetmeliği** (RG 29001, 15.05.2014, amended 26.05.2023)

Together these prohibit promoting uncertified device functionality and heavily restrict health-service advertising to the Turkish public — including by parties without a health-service licence, i.e. us. *"Coming soon: AI triage"*, pilot press releases and investor decks that reach the public are all exposure. **We have PolicyGuard for in-app strings and no claims-control gate for marketing.** This is the single most likely source of an early enforcement letter for a consumer health app in Türkiye.

Also added: **KVKK Özel Nitelikli Kişisel Veriler Rehberi (26.02.2025)** — the current special-category posture rests on Karar 2018/10, which predates the m.6 rewrite by six years; **KSVY amendment RG 33096, 03.12.2025**; **ETBİS registration** for the paid tier; **TCK 133 and 134** for recording consent.

---

## 6. Research tracks

1. **Turkish medical ASR benchmark** — unchanged; decides STT per profile.
2. **Turkish DAM validation** — ⚠ moves behind track 1. The acoustic lane is cut from P0/P1 and nothing depends on it until P3.
3. **Pre-visit note usefulness (RCT-lite)** — ⚠ now gates the `considerations[]` block. An AI-generated pattern list rendered above the clinician's own reasoning is a differential diagnosis functionally, and it will anchor. Do not ship it until a prospective study shows it improves rather than degrades diagnostic accuracy.
4. **Protocol library** — clinician-authored packs; open-source the DSL and base protocols (Apache-2.0).
5. **Conversational feel study** — ⚠ drops `s2s_cloud` (cut to P3); becomes `cascade_fast` vs `residency_tr` vs typed.
6. **Voice-based psychiatric signal validation** — unchanged, research-only.
7. ⚠ **NEW — Turkish clinical-extraction accuracy.** Per-rule sensitivity and specificity of slot extraction against a clinician-labelled Turkish reference standard. **Gates P1 exit**; without it the triage engine's inputs are unvalidated and the "deterministic rules engine" claim is unsupported.

---

## 7. Assumptions register (re-verified 25 Aug 2026)

| assumption | status | evidence |
|---|---|---|
| Soniox `stt-rt-v5` (16 Jun 2026), Turkish, semantic endpointing, context biasing | **verified** | v4 aliases to v5, removed 30 Jun 2026 with auto-routing |
| Soniox TTS is full-duplex Turkish | **verified, id corrected** | the model is **`tts-rt-v2`**; `tts-rt-v1` removed 31 Aug 2026 |
| LiveKit Turn Detector v1 is audio-based with Turkish among 14 languages | **verified precisely** | `LOCAL_LANGUAGES` has exactly 14 keys incl. `"tr": 0.2550` |
| …and is available self-hosted on CPU | **FALSE** | `detector.py:59` resolves to **`v1-mini`** unless hosted; `v1` requires `cloud_opts`; **backchannel probabilities are cloud-only, so backchannels are impossible in `residency_tr`**; and using v1 streams patient audio to LiveKit Inference — **an undeclared PHI egress hop**, absent from the allow-list, the DPIA and the transfer register |
| The `livekit-agents` code snippet as written | **verified, with a migration warning** | all packages at 1.7.0 and the imports are valid — but `turn_detection`, `preemptive_generation`, `allow_interruptions`, `min/max_endpointing_delay` and `keyterms_options` are **deprecated in 1.7.0** → `turn_handling=TurnHandlingOptions(...)`, `stt_context_options=STTContextOptions(...)`. Writing P1 against the old signature buys an immediate migration |
| Open, commercially usable Turkish TTS with ~200 ms streaming | **partly false** | Chatterbox Multilingual V3 (10 Jun 2026, MIT, 23 languages incl. tr) is real, but **PyPI ships only `chatterbox-tts` 0.1.7**, and the ~200 ms figure belongs to Resemble's **paid hosted service**. The open weights publish no streaming latency. `residency_tr`'s TTS budget is an **open measurement**, not an assumption |
| Open Turkish streaming ASR with context biasing | **verified, and better than assumed** | Qwen3-ASR ships as **0.6B and 1.7B** (Apache-2.0, 28 Jan 2026, 52 languages incl. tr). The 0.6B is the CPU-budget option and was missing from v1.4 |
| Expo SDK 57 is safe to pin | **verified, with a hard caveat** | expo `latest` = 57.0.16; SDK 57 → RN 0.86.2 / React 19.2.3 exactly. **But SDK 57.0.0 still carried the Hermes V1 memory regression** — expo/expo#46519 is still open and PR #48887 states the fixed hermes versions "weren't backported… (including on 57)". **Pin `expo@57.0.9+` and the exact RN patch, gate CI on `npx expo-doctor`, keep `useHermesV1: false` as a live fallback.** A 1.1 GB-RSS app is an OOM-kill on the mid-range Android a Turkish hospital kiosk will be |
| Node ≥ 22.13 | **false** | **Node ≥ 20.19.4** |
| Device attestation is available in Expo | **effectively false** | `expo-app-integrity` was last published **2023-04-09** with peers pinned to SDK 48/49-era — **it cannot install alongside SDK 57**. `react-native-app-attest` is iOS-only. **DPoP has no Expo module at all.** Budget **4–6 engineer-weeks** for a first-party config-plugin; this work is currently invisible in the backlog |
| Certificate pinning in the Expo managed workflow | **partly true** | no first-party API; needs a config-plugin (TrustKit / OkHttp), a dev or production build, and expo-dev-client's network inspector disabled on iOS. A `fetch`-patching shim will **not** pin the WebRTC/DTLS path — i.e. most PHI traffic |
| De-identification before every cloud model call | **structurally impossible on the first hop** | in `cascade_fast` the first cloud call **is the STT audio stream**, and audio cannot be Presidio-redacted. Control it with contract + residency + ZDR, not a technical control that does not exist. Also **spaCy ships no Turkish model** (`tr_core_news_sm`/`md` both 404), so Presidio needs the `transformers` or `stanza` extra plus custom recognizers |
| < 0.1 % de-identification leak rate | **unfalsifiable as defined** | measured "on the synthetic corpus" *we author*. Realistic conversational-Turkish recall is 0.85–0.95 given oblique cases (*Ahmet'in*, *Ayşe'ye*); 3–8 identifiers per intake ⇒ **≈ 0.3–1.0 expected leaks per session**. Redefine as **recall per entity class on a held-out, human-labelled, real-transcript corpus** with a published confusion matrix: TCKN ≥ 0.99 (checksum-verifiable), names and addresses ~0.90, stated honestly |
| MinIO is a safe root of trust for a 10-year WORM audit log | **at risk** | newest Docker Hub tag is **RELEASE.2025-09-07** (~12 months stale), and the named fallback **Garage does not implement S3 Object Lock** — silently voiding the WORM guarantee |
| MedGemma is open-weights and self-hostable in Türkiye | **licence-false** | **every** MedGemma model, 1.5-4B included, is **Health AI Developer Foundations** licensed — none is Apache-2.0. This conflicts with the CI Apache/MIT/BSD allow-list, which has no verdict for HAI-DEF |
| MedGemma 27B "1.5" exists | **false** (unchanged) | 1.5 is 4B only |
| Open-weights S2S with Turkish speech **output** | **not yet** (unchanged) | Qwen3-Omni is Turkish speech-**in** only; Qwen3.5-Omni is API-only |
| OpenAI Realtime is EU-residency eligible for `s2s_cloud` | **partly** | `/v1/realtime` is an eligible EEA+CH endpoint, **but tracing for `/v1/realtime` is not EU-residency compliant**, and residency requires ZDR / Modified Abuse Monitoring approval. Also **GPT-Realtime-2 is superseded by GPT-Realtime-2.1 (6 Jul 2026)** |
| Vertex Live API residency controls are contractable | **unverified** | 70 languages and affective dialog are confirmed; the residency terms are not. Confirm with Google before `s2s_cloud` leaves the flag |
| **Rule 11 → Class IIa** | **FALSE — the most consequential correction in the bundle** | **IIb for both device functions.** MDCG 2019-11 Annex IV states the depression-scoring case is IIb almost verbatim; IMDRF N12 defines "drive clinical management" as including *triage*; and the failure mode to assess is the **false negative**, which is the Class III limb |
| ATADEK and TİTCK can run in parallel | **false** | TCKAY m.8/2 — the ethics decision is submitted **as part of** the TİTCK application |
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
| P0 fits in 3 weeks | **false** | 91 issues ÷ 15 working days = 6/day, each with a recorded red run, a green run, three gate suites, an evidence file and a PR — before counting ≈ 68 hours of serial CI. **12–20 weeks.** |
