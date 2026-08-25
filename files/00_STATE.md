# 00 · STATE — living context file

> **Purpose.** This file exists so that a lost session, a killed agent, or a fresh context window does not lose what we decided and why. It is the **first file to read** and the **first file to update**. Everything here is either a decision, a verified fact, an open question with an owner, or a blocker on a named person.
>
> **Update discipline.** Update this file *in the same commit* as the change it describes. If a decision is reversed, do not delete the old row — mark it withdrawn and say why. The withdrawn rows are the most valuable part of this file, because they stop the same wrong idea being re-proposed.
>
> Last updated: **25 Aug 2026**. Repo: `ArioMoniri/intake`, branch `main`, private, **never pushed** (13 local commits).

---

## 0. Read this first if you are picking up cold

Three things about this project are counterintuitive and get re-derived wrongly every time:

1. **The observer lanes are RETAINED.** An earlier draft proposed cutting `affect` and `acoustic` on cost and PHI-egress grounds. **That was wrong and is withdrawn** — see §3. Do not re-propose it.
2. **"Clinician-only" is the *unsafe* direction, not the safe one.** For the affect lane, showing output to a clinician is what creates a medical-device function. Not-rendered-at-all is safe. §4.7 of `03` originally had this backwards.
3. **The binding regulator is MDR/TİTCK, not FDA.** FDA's CDS guidance has a statutory device *exclusion* (§520(o)(1)(E)) that has **no EU/TR equivalent** — there is no Criterion 1 to fail because there is no carve-out to qualify for. This is *worse* for us, not better.

---

## 1. Model pins — current state

**Status key:** ✅ confirmed · ⚠️ pinned but unverified · 🔬 under active research · ❌ known broken

### Voice profiles

| Profile | Component | Current pin | Status | Note |
|---|---|---|---|---|
| `cascade_fast` | STT | Soniox `stt-rt-v5` | 🔬 | $0.12/hr. **Realtime diarization bundled free** — never switched on. Also the backend Inworld routes to. |
| `cascade_fast` | TTS | Soniox `tts-rt-v2` | 🔬 | Turkish quality unverified |
| `cascade_fast` | affect | Inworld voice profiling | ⚠️ | **Same-request flag**, not a second stream — see §3. 18 languages incl. Turkish. Gated on written EU/TR region + ZDR confirmation. |
| `s2s_cloud` | S2S | GPT-Realtime-2.1 | 🔬 | Profile itself deferred; no published latency target (correctly) |
| `residency_tr` | ASR | Qwen3-ASR on vLLM | 🔬 | Encoder already resident in GPU — candidate for lane consolidation |
| `residency_tr` | TTS | Chatterbox (version-pinned) | 🔬 | Turkish support may be incidental rather than real. Streaming latency figure in the blueprint belongs to Resemble's **paid hosted** service; open weights publish none. |
| `residency_tr` | affect | emotion2vec-class open SER | ⚠️ | No published Turkish evaluation |
| `typed` | — | n/a | ✅ | Always available; never a dead end |

### Observer lanes

| Lane | Model | Status | Blocking issue |
|---|---|---|---|
| `acoustic` | Kintsugi DAM (Apache-2.0) | ❌ **encoder mismatch** | Backbone is **`whisper-small.en` — English-only**. Model card restricts to *"a single voice speaking English."* Recalibration cannot fix an encoder that never saw Turkish phonology. See §5 Q3. |
| `affect` | open SER (emotion2vec+) | ⚠️ | No Turkish eval. Candidate: consolidate onto an encoder already in the stack. |
| `linguistic` | rule-based Turkish lexicon | ✅ | Text-only, local, no transfer |
| `asr_quality` | STT confidence | ✅ | Highest value/risk ratio of all five lanes |
| `engagement` | local heuristics | ✅ | Local in all profiles |
| *(new)* diarization | Soniox v5 bundled + local ECAPA | ✅ available | Two-estimator gate; **$0 marginal cost** |

---

## 2. Verified facts ledger

Numbers that keep circulating wrongly. Each is checked; do not restate a different value without re-checking.

| Fact | Value | Source |
|---|---|---|
| Device classification | **Class IIb**, not IIa | MDCG 2019-11 Annex IV names the depression-scoring case verbatim under Rule 11(a) |
| Turkish triage | **5 acuity levels** in 3 colours / 3 zones | RG 13/9/2022 s.31952 EK-4. The 2009 Tebliğ is **repealed**. |
| MTS → EK-4 mapping | MTS Orange → **KIRMIZI**, not SARI | A naïve 3↔3 map systematically **under-triages** |
| 182 | MHRS **appointment** line | NOT a crisis line |
| C-SSRS | **BLOCKED** | Clario exclusive electronic licence: $40k + $7.5k/yr + $4/administration. Turkish validation is **adolescents 12–18 only**. |
| WHO-5 | **BLOCKED** | CC BY-NC-SA 3.0 IGO — **NonCommercial** since 2024 |
| Backlog | 175 issues, 0 cycles, 0 missing deps | **INT-043 unblocks 78**; 101/175 human-gated; loop completes only 47/91 P0 |
| Latency floor | **~420 ms structural** | 250 ms VAD+EOU + ~140 ms transport, before any decision. Transport term 🔬 under verification. |
| Dynamic turn latency | p50 ~1000 ms / p95 2000 ms | The blueprint's old "thinking ≤ 700 ms" is **wrong** and must be deleted from `02 §5.2` |
| Session cost | $0.12–0.25 (after fixes) | Down from $0.13–0.28 *while keeping both lanes and adding diarization* |
| Stream-minutes | 8.4 → **4.4** (−48%) | Collapsing the accidental second audio stream |
| Cutting `affect` would have saved | **$2.40 across the entire 300-session pilot** | Against fixed infra of €1,550–1,900/month. This arithmetic settles the cost argument. |
| DAM validation study | n ≈ **800**, €120–250k, 12–18 months | Powered on sensitivity 0.75 ±0.08. **The 300-session P2 pilot cannot validate this lane** — off by ~3×. |
| AI Act Art. 50(3) | **applies from 2 Aug 2026** — NOT deferred | Reg. (EU) 2026/1744 deferred Annex III high-risk to 2 Dec 2027, but not transparency |
| Kintsugi DAM | **audio-classification**, not STT | `base_model: openai/whisper-small.en` used as encoder. Never produces text. No STT minutes, no per-stream billing. |

---

## 3. Decisions — including withdrawn ones

| # | Decision | Status | Why |
|---|---|---|---|
| D1 | Cut the `affect` and `acoustic` observer lanes | ❌ **WITHDRAWN 25 Aug** | Rested on a misreading of `03 §4.7`. `acoustic` is open-weights self-hosted in every profile — no vendor, no second stream, no cross-border transfer. `affect` already had a self-hosted path specified for `residency_tr`. Cost was $2.40/pilot. Latency was never an objection — lanes are off the critical path with an invariant that tests it. |
| D2 | Run the open SER path in **all** profiles, not only `residency_tr` | ✅ adopted | Removes the second vendor stream, the transfer, and the consent complexity at once |
| D3 | Exactly **one** outbound audio stream per session | ✅ adopted | Enforced at the egress proxy + invariant 12 + `consent_vendor_parity` (inv. 25) so it cannot recur |
| D4 | `acoustic` is an **investigational device module** | ✅ adopted | Clinician-visible in a commercial tenant before CE/TİTCK is **not lawful**. Lawful home is MDR Art. 62 ff. / TCY m.61 ff. Genuinely unreachable outside the study — no shadow mode. |
| D5 | Replace the clinician-note `affect_summary` with an objective "Konuşma özellikleri" block | ✅ adopted | The prose sentence is what converts a non-device module into MDSW. Objective measures assert no clinical construct and give the clinician *more* usable information. |
| D6 | Turkish DAM validation track **promoted**, not deferred | ✅ adopted | It is the gate on the lane becoming clinician-visible; its lead time determines when the lane ships |
| D7 | FDA Device Example 14 = **module bounding**, not a cut justification | ✅ adopted | Classification finding about the *function*, not the deployment. Cite as addressed adverse authority. |
| D8 | openEHR cut from P0/P1, kept as a P3 export | ✅ adopted | OPT has no `invariants` element; Task Planning **RETIRED** ("the model is not really workable"); GDL2 is stateless |
| D9 | Adopt FHIR SDC representation, **reject `$next-question` as runtime** | ✅ adopted | `Questionnaire.url` and `version` are both `..0` — no slot for `protocol_hash` |
| D10 | Roadmap is **gate-driven, not date-driven** | ✅ adopted | Three real constraints: review capacity (101/175 human-gated), CI throughput, and the 7–12 month clinical-investigation clock |

---

## 4. Open blockers on the product owner

| # | Needs | Why it blocks |
|---|---|---|
| B1 | **Free 80–100 GB disk** | 19 GiB free of 926 GiB. Hard blocker on any local build. |
| B2 | **Raise Docker RAM** | 15.1 GB is undersized; security + observability tiers alone need 22 GB |
| B3 | Decide on **Mobbin** | MCP requires a paid plan |
| B4 | **Inworld written confirmation**: EU or TR processing region + zero data retention, and Soniox named as sub-processor in the DPA | Without it, the one-stream Option A is dead on KVKK Art. 9 grounds and Option B (local SER) is forced. Contract question on the critical path. |
| B5 | Name the **clinical investigation site** | Must be Acıbadem MAA Üniversitesi's uygulama ve araştırma merkezi — a general private Acıbadem hospital does **not** qualify under TCKAY m.5/6 |
| B6 | Decide **C-SSRS and WHO-5** | Both licence-blocked. Either obtain written permission or drop the instruments. |
| B7 | Counsel on **B2C freemium vs Turkish marketing law** | `01` sells a funnel that `05 §5` says we may not advertise. Business model and compliance file are in direct conflict. |

---

## 5. Open questions with owners

| # | Question | Owner | Status |
|---|---|---|---|
| Q1 | Best Turkish streaming ASR — keep Qwen3-ASR and Soniox, or replace? Medical-term biasing is a **hard requirement**. | `TurkishASR` | 🔬 restart needed |
| Q2 | Are Qwen3-Omni / Qwen-Audio better than GPT-Realtime-2.1? Separately for Turkish and for the self-hosted case. **Tool-calling reliability in the audio path is disqualifying if absent.** | `RealtimeS2S` | 🔬 restart needed |
| Q3 | Turkish-capable encoder for the biomarker head. Is DAM's signal language-dependent? Decisive test: bilingual speakers, content-matched passages, same session. | `EncoderTransfer` | 🔬 restart needed |
| Q4 | Best self-hostable Turkish TTS — is the Chatterbox pin still right? Does the clip cache justify a **two-model split** (quality for cached clips, speed for dynamic)? | `TurkishTTS` | 🔬 restart needed |
| Q5 | Is SER cross-lingually valid at all for Turkish? What Turkish emotional-speech corpora exist, and are they acted or spontaneous? | `SERBiomarker` | 🔬 restart needed |
| Q6 | Can we get the interleaved text+audio single-decode property? **Suspected answer: no, and it may not matter** — most turns are pre-rendered clips, and the text must be a faithful clinical record, which an S2S text head does not guarantee. | `RealtimeArch` | 🔬 restart needed |
| Q7 | Real Turkish mobile RTT p50/p95/p99, and does data residency *help* latency? | `NetworkEng` | 🔬 restart needed — had strong RIPE Atlas data when killed |

---

## 6. Work queue

### Landed and applied
- ✅ Roadmap rebuilt as v2.0 gate-driven; lane cut withdrawn; DAM track promoted; STT/storage framings corrected
- ✅ `13 §6` FDA Example 14 reframed as module bounding
- ✅ Rule 11 → Class IIb; triage colour semantics; instrument licensing; guideline currency

### Reviewed, **not yet applied**
- ⏳ **Observer-lane hardening** → `03`, `04`, `06`, `10`. One-stream collapse, diarization gate, four-module boundary, investigational-device route, AI Act, crash-artefact hardening, replay determinism, per-lane consent, **18 new invariants (12–29)**
- ⏳ **Product/market review** → `01`, `02`. MoH as the real competitor, moat re-argument, marketing-law contradiction, personas + Fears column, RED delivery registers, consent temporal unbundling, visit lifecycle, NFR rewrite

### Still owed
- ⏳ `ClinicalAuthor`: `base.intake` additions block + golden-test table
- ⏳ Assemble `base.life_threat.yaml` from parts 1–3 (all received)
- ⏳ Apply `SystemDesigner` migration notes to the backlog (INT-04x, INT-08x, INT-09x, INT-2xx; INT-032 → INT-032a)

---

## 7. Gotchas

- **File is `01_MARKET_AND_STRATEGY.md`**, not `01_VISION_AND_MARKET.md`. Cost an agent a wasted read.
- **Do not run more than ~3 agents concurrently.** A 5-agent batch on 25 Aug hit the session limit and **all seven running agents died at once**, losing ~40 minutes of research with no partial output recoverable.
- Agents that yield a one-line non-report need an explicit "deliver the full report" follow-up; this has happened twice.
- A `re.sub` intended to drop a dependency once deleted the whole of INT-187. **Always `git diff` after a scripted edit** and check the issue count.
- Perl one-liners fail on `[]` and `{}` escaping here — use Python `pathlib` + `str.replace` with an assertion on the match count.

---

## 8. Changelog

| Date | Change |
|---|---|
| 25 Aug 2026 | State file created after a session-limit wipe killed 7 agents mid-flight |
| 25 Aug 2026 | Observer-lane cut withdrawn (D1); DAM track promoted (D6); Example 14 reframed (D7) |
| 25 Aug 2026 | Kintsugi identified as audio-classification on an **English-only** encoder — the sharpest open risk in the stack |
