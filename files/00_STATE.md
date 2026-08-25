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

| Profile | Component | Current pin | Verdict | Note |
|---|---|---|---|---|
| `cascade_fast` | STT | Soniox `stt-rt-v5` | ✅ **KEEP** | Only candidate clearing all four hard criteria at once: Turkish named explicitly, biasing API, true streaming (~250 ms to final segment), **and free realtime diarization**. Diarization is the tiebreaker. **No published Turkish WER** — nobody publishes one. |
| `cascade_fast` | TTS | Soniox `tts-rt-v2` | ⚠️ **REPLACE or gate** | **Shipped 11 Aug 2026 — 14 days old.** No published TTFB, no Turkish evaluation of any kind, no per-language quality tiering, and `03 §4.5` allocates it 75–150 ms **on faith**. Challenger: ElevenLabs Flash v2.5 (~75 ms). **Counterweight: dynamic `speech_tr` carries PHI, so a second TTS vendor is a second PHI processor** — a real cost against D3/B4. Decide on a Turkish dose-pronunciation gate, not on brand. |
| `s2s_cloud` | S2S | **GPT-Realtime-2.1** | ✅ **KEEP** | The only realtime model with **async / non-blocking function calling**, which the six-tool Talker structurally requires (`submit_utterance` must return a `work_id` without blocking). EU residency via `eu.api.openai.com`. ⚠️ Async exists **only on the GA interface**, not beta. |
| — | S2S alternative | ~~Gemini 3.1 Flash Live~~ | ❌ **NOT co-equal** | *"Function calling is sequential only."* `NON_BLOCKING` exists only on the **older** 2.5 Flash Live — adopting Gemini would mean adopting the older model to get the property the architecture depends on. |
| `residency_tr` | ASR | Qwen3-ASR-1.7B | ✅ **KEEP**, 3 corrections | Apache-2.0, Turkish, vLLM streaming, context biasing — all confirmed. **(a) Pin the exact repo**: `Qwen/Qwen3-ASR-1.7B` (vLLM) and `-hf` (transformers) are **different artefacts** created five months apart. **(b) Streaming is vLLM-only** → vLLM is a hard dependency, not an optimisation. **(c) Biasing is a soft `prompt` string with no published evaluation** (open upstream issue #157 asks for real hotwords) — needs its own eval. |
| `residency_tr` | TTS | Chatterbox | ⚠️ **KEEP — nothing else qualifies** | Pin **`ResembleAI/chatterbox` at a revision hash**: `ResembleAI/chatterbox-multilingual` **404s**, and "Multilingual V3" is a model-card name, not a repo. Turkish is **not** among the six languages given dedicated Single Language Packs. **No open-weights TTFB published**, so the `§4.5` 600–900 ms budget has nothing behind it. |
| `typed` | — | n/a | ✅ | Always available; never a dead end |

### Ruled out — record permanently, these keep recirculating

| Candidate | Why it is out |
|---|---|
| **Qwen3.5-Omni-Flash** | **Genuinely the best Turkish S2S that exists** — Turkish in *and* out, 235 ms first packet, function calling. **Served only from Alibaba Cloud regions: no EU, no TR.** Routing patient audio there is a KVKK Art. 9 transfer to a jurisdiction with no adequacy decision. **The best Turkish S2S model on the market is not available to this product** — not a close call, and not a negotiation you win. |
| **Qwen3-Omni-30B-A3B** (open) | 19 input languages incl. Turkish, but **10 output languages and Turkish is not one**. Cannot be the Talker. Usable only as audio-in → text. 78.85–144.81 GB VRAM bf16. |
| **Qwen3-TTS-12Hz** | **10 languages, no Turkish.** The obvious Apache-2.0 rescue for `residency_tr` TTS is Turkish-incapable. Most important negative finding of the survey. |
| **"qwen3.8 voice"** | **Does not exist.** No such model, checkpoint, API id or repo. Almost certainly means Qwen3.5-Omni (30 Mar 2026). |
| `qwen-audio-agent` | A **Node.js runtime, not a model.** Already the architectural template for `03 §4.2–4.3`; adds no model option. |
| Qwen-Audio / Qwen2-Audio | Superseded twice; `en`/`zh` only. |
| **NVIDIA Parakeet / Canary** | **Turkish not among the 25 European languages.** Recirculates constantly as "open and SOTA"; simply inapplicable here. |
| **Mistral Voxtral** | 13 STT languages, **Turkish absent**. |
| **Deepgram Flux Multilingual** | Their conversational model with integrated turn detection — exactly what you'd want — went multilingual to 10 languages on 29 Apr 2026 and **Turkish is not among them**. Turkish is in Nova-3, the wrong product line. |
| **XTTS-v2** | CPML non-commercial, and **Coqui is dissolved — no entity remains that can grant a commercial licence.** Permanently, not temporarily, unusable. |
| **F5-TTS**, `facebook/mms-tts-tur` | Both `cc-by-nc-4.0`. MMS-tur is recommended in several "open Turkish TTS" guides that don't check the licence. |
| `hcsolakoglu/Orkhon-TTS` | ⚠️ **Licence risk** — tagged Apache-2.0 while being an `f5-tts` model whose upstream weights are CC-BY-NC-4.0. Needs a derivation review before adoption. |
| Kokoro / Orpheus / IndexTTS-2 / CosyVoice2 / OpenAudio S1-mini | **No Turkish** in any of them. |
| Moshi / Hibiki | English only, and no tool calling. |
| "Whisper large-v4" | **Does not exist.** Latest open checkpoints are large-v3 (Nov 2023) and large-v3-turbo (Oct 2024). |

### Observer lanes

| Lane | Model | Status | Blocking issue |
|---|---|---|---|
| `acoustic` | Kintsugi DAM (Apache-2.0) | ❌ **worse than an encoder mismatch** — bounded as investigational-device module M3 | **Two** `whisper-small.en` encoders. One is bit-identical frozen English ASR weights + an English-fitted LoRA (r=32) — verified against the pretrained safetensors, **max abs diff `0.000e+00`**. The other, `llma`, is **"Large Language Model Approximation"**: a fully-trained network regressing onto **BERT embeddings of English transcriptions**. On Turkish audio it predicts the BERT embedding of an English transcript that does not exist. **Roughly half the 1536-d representation has no Turkish referent.** See §5 Q3. |
| `affect` | open SER (emotion2vec+) | ⚠️ | No Turkish eval. Candidate: consolidate onto an encoder already in the stack. |
| `linguistic` | rule-based Turkish lexicon | ✅ | Text-only, local, no transfer |
| `asr_quality` | STT confidence | ✅ | Highest value/risk ratio of all five lanes |
| `engagement` | local heuristics | ✅ | Local in all profiles |
| *(new)* diarization | Soniox v5 bundled + local ECAPA | ✅ applied | Two-estimator gate; **$0 marginal cost** |
| *(new)* ASR shadow / `residency_tr` fallback | `turkmedstt/whisper-large-v3-turkish-medical` | ⚠️ thin evidence | The **only** Turkish medical ASR artefact that exists. WER 8.54% real-voice medical, 7.95% general — but **3 speakers, 120 clips**, synthetic-TTS training data, a 2026 capstone, 113 lifetime downloads. **Do not quote to a clinician.** Use as `asr_quality` shadow and as the `residency_tr` fallback, where it strictly dominates the currently-specified faster-whisper large-v3-turbo. |

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
| **DAM's own model card is contradicted by the vendor's own paper** | ⚠️ **documented discrepancy** | The card claims DAM works *"without reliance on linguistic content or transcription"* and *"operates exclusively on the acoustic properties."* arXiv 2605.09908 shows AUC **0.79 → 0.67–0.69** when linguistic content is standardised **within English**, and a **text-only BERT model (0.747) beats the audio-only model (0.740)**. In a Class IIb qualification file this is a discrepancy you want to have noticed first. |
| **DAM's ternary band is unstable to the elicitation prompt** | **28.8%** of subjects flip depression band, **36.2%** anxiety — on a *prompt change alone*, same session, same PHQ-9 | Measured on Kintsugi's released val+test, n=3,163. Test-retest paired SD **0.338** against a band width of **0.379**. Mean score spread across the 12 prompts is **0.582** — larger than the entire threshold gap. **This needs no Turkish data and is actionable now.** |
| Threshold recalibration cannot fix discrimination | **mathematical, not empirical** | Threshold refit is a **monotone transform**: AUC, the ROC curve and Sn=Sp are invariant under it. Recalibration moves the operating point *along* a fixed ROC curve; it cannot move the curve. You cannot threshold your way out of AUC 0.503. |
| DAM's training duration distribution | mean **56.4 s**, median 56.7 s, **0% under 30 s** | Our `03 §4.7.3` gate admits **≥30.0 s**, the extreme bottom tail of what DAM ever saw. **A language-independent degradation source we are currently designing in** — consider ≥45 s and accept lower yield. |
| Qwen3-ASR AuT encoder as a biomarker backbone | ⚠️ weaker than it looks | **12.5 Hz token rate** (Whisper and WavLM are 50 Hz) — coarse for the prosodic and micro-timing features a biomarker head needs. And **vLLM does not expose audio-encoder frame-level states**; the "already in memory" consolidation win is **operational (fewer model families to version, pin, hash), not VRAM**. |
| `facebook/mms-1b` | ❌ **CC-BY-NC-4.0** | Excluded outright as an encoder candidate. |
| **DEPAC** — the only speech corpus labelled with **both PHQ-9 and GAD-7** | proprietary to Winterlight Labs, **never distributed** | Copy the published protocol as a collection template; the data is unobtainable. Most other depression corpora (DAIC-WOZ, E-DAIC, Androids, AVEC, CMDC, MODMA) are research/non-commercial only — **and several restrict derived *weights*, not just data.** Counsel must read each EULA before a model touches the data. |
| KVKK Art. 6 | **amended by Law No. 7499**, RG 32487, in force 1 Jun 2024 | The old health-data carve-out was removed and the regime aligned to GDPR Art. 9. **Anything citing pre-2024 Art. 6 is out of date.** |

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
| ~~Q1~~ | Best Turkish ASR | `SpeechStack` | ✅ **ANSWERED** — keep both pins; see §1 |
| ~~Q2~~ | Qwen vs GPT-Realtime | `SpeechStack` | ✅ **ANSWERED** — keep GPT-Realtime-2.1 on async tool calling; Qwen ruled out on residency and Turkish output |
| ~~Q3~~ | Turkish encoder for the biomarker head | `EncoderTransfer` | ✅ **ANSWERED** — Option B (re-encode) is the only route to a shippable lane; the gate is **data, not compute**. Shortlist on licence first: XLS-R-300m, WavLM Base+ **and** Large (bigger is not better — WavLM-Large failed on *every* Mandarin condition where Base+ held), whisper-large-v3 encoder. **Tap an intermediate layer, not the final one** — four independent papers; DAM pools the final layer, which is Whisper's *worst* for cross-lingual transfer. |
| **Q11** | **Three cheap tests, ~€0, before any study.** (a) The 28.8% prompt-instability finding needs no Turkish data — pre-specify it as a limitation and fix the elicitation prompt. (b) **Ablate the `llma` branch** and re-baseline from AUC 0.740, not 0.788 — this may change what the bilingual study should even measure, so do it first. (c) Ask Utrecht for the **full** Turkish BD corpus and score the **acted-depression controls** — 49 healthy speakers × {neutral, acted mania, acted depression} is a free adversarial specificity set, and a model that scores acted depression like real depression is doing acting-detection. | unassigned | ⏳ **do these first** |
| **Q12** | **Bilingual invariance study — redesigned.** My original proposal was invalid: **read passages are the wrong elicitation** (DAM trained purely on free autobiographical narrative; the vendor's own ablation costs 0.10–0.12 AUC on read literary passages), and **content-matching biases toward the null** because a faithful translation preserves BERT semantics and so *helps* the `llma` branch match. Fixed design: n=48 (analyse ≥40), free-response translated prompts, order-counterbalanced Latin square, **TOST at ±0.10 score units**, co-primary = band-flip rate benchmarked against the 28.8% within-English prompt baseline. ~€8–15k, 6–10 weeks with ethics. **It tests invariance, not validity** — its real value is as a kill switch on Option A2. | unassigned | ⏳ |
| ~~Q4~~ | Best Turkish TTS + clip-cache split | `SpeechStack` | ✅ **ANSWERED** — keep Chatterbox (nothing else qualifies); **two tiers, same vendor and same voice id**, because two vendors break voice identity mid-session |
| **Q9** | **Build a 3–5 h Turkish spontaneous clinical-speech eval set** — code-switched English medical terms, dosages, units. FLEURS-tr and Common Voice tr are **both read speech** and both overstate performance on the real workload. **No vendor publishes Turkish per-language numbers, so this must be built.** ~2 weeks; unblocks the ASR, TTS and `§4.5` budget questions at once. | **unassigned — highest-value open task** | ⏳ |
| **Q10** | **Turkish text normalisation must move into the protocol compiler** — expand every digit, unit and drug name to Turkish orthography so **no TTS in any profile ever sees a numeral**. No open TTS documents Turkish normalisation; only Azure/Google give declarative control. Add a **compile-time round-trip gate**: synthesise → transcribe back → diff → fail the build on mismatch. Turns "a mispronounced dose is a hazard" into a CI invariant at zero runtime cost. | unassigned | ⏳ |
| Q5 | Is SER cross-lingually valid at all for Turkish? What Turkish emotional-speech corpora exist, and are they acted or spontaneous? | `SERBiomarker` | 🔬 restart needed |
| Q6 | Can we get the interleaved text+audio single-decode property? **Suspected answer: no, and it may not matter** — most turns are pre-rendered clips, and the text must be a faithful clinical record, which an S2S text head does not guarantee. | `RealtimeArch` | 🔬 restart needed |
| Q7 | Real Turkish mobile RTT p50/p95/p99, and does data residency *help* latency? | `NetworkEng` | 🔬 restart needed — had strong RIPE Atlas data when killed |
| Q8 | **The `02 §2` fast-mode content list is 16–21 turns against a ≤18-turn budget** — inconsistent even in the clean case, with zero clarifications. Reconcile by cutting content, raising the budget, or compounding questions (which carries its own voice data-quality cost). | `ClinicalAuthor` | ⏳ open, surfaced not invented |

---

## 6. Work queue

### Landed and applied
- ✅ **Product/market review applied** to `01`, `02` — MoH named as the real competitor (`01 §3b`), window-closes responses (`§4b`), moat re-argued with the record stated as *weak*, marketing-law contradiction as the first `§5` risk with B2B2C adopted; personas + Fears column, `§2b` visit lifecycle, `§5.2a` rail rules, `§5.3` four RED registers, `§7` consent temporal unbundling, `§8` NFR restructure
- ✅ **Observer-lane hardening applied** to `03`, `04`, `06`, `10` — one-stream collapse (`03 §4.7.2`), diarization gate (`§4.7.3`), four-module boundary (`§4.7.1`, `06 §0.6`), investigational-device route (`§4.7.4`, `06 §0.7`), AI Act (`06 §10`), crash-artefact hardening (`10 §3`), replay determinism (`03 §4.8`), per-lane consent (`06 §2.1–2.4`), **18 new invariants 12–29** catalogued in `10 §9.1`
- ✅ Roadmap rebuilt as v2.0 gate-driven; lane cut withdrawn; DAM track promoted; STT/storage framings corrected
- ✅ `13 §6` FDA Example 14 reframed as module bounding
- ✅ Rule 11 → Class IIb; triage colour semantics; instrument licensing; guideline currency

### Reviewed, **not yet applied**

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
| 25 Aug 2026 | **DAM diagnosed by direct checkpoint verification.** Two encoders, one of them an English *text-semantics* approximator; model card contradicted by the vendor's own paper; ternary band flips for 28.8% of subjects on a prompt change alone. Option B is the only route; the gate is data, not compute. |
| 25 Aug 2026 | **Main speech path answered.** Keep Soniox STT, GPT-Realtime-2.1, Qwen3-ASR, Chatterbox; replace-or-gate Soniox TTS. Qwen3.5-Omni is the best Turkish S2S and is unusable on KVKK residency. Qwen3-TTS has no Turkish. Gemini 3.1 Flash Live disqualified on sequential-only tool calls. |
| 25 Aug 2026 | Product/market review applied to 01/02; MoH named as competitor; B2C freemium replaced by B2B2C on marketing-law grounds |
| 25 Aug 2026 | Lane hardening applied to 03/04/06/10; 18 invariants added; `affect_summary` deleted from every note schema; `Observation`/`dataAbsentReason` deleted; Class IIa contradiction in `06 §1` corrected |
| 25 Aug 2026 | Kintsugi identified as audio-classification on an **English-only** encoder — the sharpest open risk in the stack |
