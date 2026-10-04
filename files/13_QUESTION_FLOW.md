# 13 · Question selection, ordering and adaptivity (25 Aug 2026)

> **The question this answers:** which questions do we ask, in what order, and how does the next question change given the previous answer?
>
> **The short answer:** keep the deterministic protocol. Make it **more expressive, not more adaptive**. Author it as SDC-conformant FHIR `Questionnaire` resources, administer PHQ-9 and GAD-7 verbatim, put the red-flag battery *outside* any optimiser, and measure **elicitation coverage** rather than entropy efficiency.
>
> Every empirical claim below is cited. Tiers: **[STD]** standardised · **[IMPL]** implemented and reachable today · **[RES]** research-only.

---

## 1. Algorithm comparison

| approach | determinism | auditability | testability | regulatory defensibility | **works with a TTS clip cache?** |
|---|---|---|---|---|---|
| **Static protocol + `ask_if`/`skip_if`** *(what we have)* | **total** — same answers → byte-identical path, forever | **total** — the YAML *is* the audit trail: diffable, reviewable, signable | **total** — path space finite; 100 % branch coverage achievable | **best.** Maps 1:1 onto IEC 62304 requirement→design→test traceability | ✅ **perfect** — question set closed at build time |
| **Decision tree / published clinical rule** | total | total, plus the rule's own published provenance | total, plus testable against the rule's validation set | **best.** NHS 111 online — the UK's national triage service — is a deterministic decision tree. Regulators have seen this shape | ✅ perfect |
| **Bayesian network / information gain** | deterministic given the model, but the path is *emergent* — a 0.001 parameter change reroutes the interview | **weak** — you can log the posterior, but "why this question" is a number, not a rationale an auditor can inspect | **poor** — combinatorial path space; you can test outcomes, not paths | **untested.** No published guidance covers verifying an entropy-driven selector; 62304 traceability has nothing to attach to | ⚠️ partial — the node set is closed so all clips can be pre-rendered, but you cannot pre-*fetch* the next one |
| **IRT / CAT** | deterministic given bank + calibration + seed | moderate — θ and SE defensible to a psychometrician, opaque to a clinician | good — validated by simulation against the full bank | **mixed.** Excellent pedigree, but see §3 | ⚠️ partial — bank is closed (PROMIS Depression 28 items) so trivially cacheable, but order is unpredictable |
| **LLM chooses the next question** | **none** — non-deterministic even at temperature 0; a model version bump reroutes everything | **very weak** — chain-of-thought is a post-hoc narrative, not a decision record | **very weak** — infinite question space; every model update invalidates the suite | **worst.** Weissman et al., *npj Digit Med* 2025;8:148 — LLMs prompted *explicitly* to comply with FDA CDS guidance still produced device-like output. **You cannot bound scope with a prompt** | ❌ **breaks it** — text is generated, so no clip exists; live TTS on the critical path |

### 1.1 Two findings that should dominate this table

**Information gain deletes exactly the questions that keep patients alive.** Sutaria et al., *BMC Health Serv Res* 2025;25:1263 — 51 vignettes, 77 defined red flags:

| | red flags actually asked |
|---|---|
| Symptomate | 17.5 % |
| **Ada** | **26.6 %** |
| **Babylon** | **42.9 %** |
| Healthily | 60.4 % |
| **PCPs** | **71.8 %** |

Ada and Babylon are the *probabilistic, adaptive* tools in that set and they asked the **fewest** red flags. Emergency sensitivity was statistically comparable to PCPs (76.9 % vs 85.7 %, p = 0.299) but specificity was significantly worse (83.3 % vs 91.9 %, **p = 0.024**) — **the adaptive tools bought sensitivity with over-triage, not with better questioning.**

The mechanism is simple and it is not fixable by tuning: **a low-prior, high-consequence question contributes near-zero expected information gain.** Nelson (*Psychol Rev* 2005) is the normative caution — information gain, probability gain, impact and Bayesian diagnosticity **strongly disagree** in identifiable regimes, and entropy is indifferent to whether the uncertainty being resolved is between two self-care conditions or between self-care and pulmonary embolism.

**Prompting an LLM to ask questions makes it worse.** MediQ (Li et al., NeurIPS 2024): *"directly prompting state-of-the-art LLMs to ask questions degrades performance."* What helped was **abstention** — better confidence about *whether* to ask — improving diagnostic accuracy by **22.3 %**. **The hard problem is the stopping rule, not the selection rule.**

### 1.2 And there is no evidence adaptivity wins

**No RCT and no prospective real-patient study compares adaptive or information-gain question selection against a fixed questionnaire on triage accuracy or outcomes.** Not thin — absent. The prospective symptom-checker RCTs measure something else entirely; the Berlin Ada-vs-usual-care ED trial's primary endpoint was *patient satisfaction with the patient–physician interaction*.

The deployed systems are less adaptive than their marketing suggests: **NHS 111 online is a rule-based decision tree**; Infermedica claims value-of-information selection in vendor docs and two US patents but has never published or been independently evaluated; Babylon's published Bayesian work (*Nat Commun* 2020;11:3923) is about **which disease to output, not which question to ask next**.

Google's AMIE is the strongest counter-evidence and it does not reach deployment: three Nature-family papers, all on **simulated patient-actors or scenarios** (159 case scenarios; 105 simulated telehealth consultations; 100 virtual-OSCE scenarios), with Google's own framing in all three that it is **not ready for clinical use**. Cite AMIE for architecture ideas — uncertainty-conditioned state-aware history-taking — never as deployment precedent.

---

## 2. FHIR SDC verdict: adopt the representation, reject the runtime

**[STD]** SDC **4.0.0 (STU 4)**, FHIR R4, published on hl7.org 2026-03-24, content frozen 2025-10. Adaptive questionnaires are an **SDC-only** feature — core FHIR has no such operation.

### 2.1 What `$next-question` actually is

`POST [base]/Questionnaire/$next-question`, **type-level only**, FMM 4, `trial-use`, **`date` unchanged since 2018-08-29**. The entire protocol is one resource shape: a `QuestionnaireResponse` with a `contained` Questionnaire that accretes items, round-tripped whole. No session id, no cursor, no θ. Terminates when the server sets `status = completed`.

### 2.2 Why we should not build on it

- **No SDC actor has a `SHALL` to implement it as a server.** It appears in exactly two CapabilityStatements, both as **client** expectations, both at `SHOULD`.
- **The one production server in the world is a payer prior-authorization product** (Smile CDR). The only reference client is a prior-auth SMART app.
- **Zero implementations** in HAPI FHIR, lforms/LHC-Forms, Google android-fhir, CSIRO Smart Forms, Medplum or Firely — verified by code search returning 0 hits for `next-question` against non-zero controls.
- HL7's own SDC Implementations registry (20+ products, updated 2026-01-27) contains **zero** occurrences of "adaptive", "next-question", "PROMIS" or "Assessment Center".
- **The HL7 US Patient Reported Outcomes FHIR IG was formally WITHDRAWN on 2026-04-10** — *"before an initial publication due to a lack of support and interested parties with the capacity to complete."* The IG meant to wire PROMIS CAT to FHIR is dead.
- **Its stated purpose in the only IG that mandates it (Da Vinci DTR) is concealing proprietary logic** — *"Payers licensing their decision logic from third parties and are concerned about disclosing licensed IP may find adaptive forms a helpful mechanism to conceal logic rules."* That is the opposite of what a clinical-evaluation dossier needs.
- **It puts an unpredictable network round-trip on the critical path of a voice turn.** DTR §spec-38 sets the conformance target at **5 s first call, 1 s subsequent, at ≥ 90 %** — five to twenty-five times the human turn-taking gap.

### 2.3 What to adopt instead

Author the protocol as **SDC-conformant `Questionnaire` resources**:

| need | mechanism |
|---|---|
| simple gating | `enableWhen` + `enableBehavior` — but know the ceiling: **exactly 7 operators** (`exists`, `=`, `!=`, `>`, `<`, `>=`, `<=`), a **flat** AND-of-comparisons or OR-of-comparisons, no nesting, no arithmetic, no counts, nothing outside the QuestionnaireResponse |
| everything past that | `enableWhenExpression` + `variable` (**FHIRPath, not CQL** — SDC: *"FHIRPath is more widely implemented than CQL, so questionnaires that only make use of FHIRPath will typically be more widely supported"*) |
| scoring | `itemWeight` + `calculatedExpression` — a declarative PHQ-9 total |
| cross-item invariants | `targetConstraint` — *"All 'error' constraints SHALL evaluate to 'true' before setting a QuestionnaireResponse to complete"* |
| pre-fill from records | **continuous population locally**, not `$populate`. No server operation needed |
| emit on completion | `$extract` (definition- or observation-based) — the one SDC operation with broad real implementation |

**Steal SDC's own determinism rule verbatim into the architecture doc:**

> *"Information gleaned from other types of external sources (e.g. launch context, fhir-x-query, etc.) SHOULD only be used for `initialExpression` and `calculatedExpression` logic and that any other desired behavior (`enableWhen`, `answerExpression`, etc.) SHOULD always be driven off of answers within the Questionnaire (even if they're hidden answers that are populated from an initialExpression) because launchContext and search results may vary between edit sessions and will also be different (or perhaps non-existent) when validating the Questionnaire."*

That is exactly the replayability property a safety-critical intake needs, stated by the standard itself.

Follow **DTR §spec-36/37** as an architectural rule even outside DTR: *"return as many items in a single call as possible… Calling `$next-question` SHOULD only be necessary when the client requires invocation of more complex or non-disclosable logic."* Resolve locally, in one step.

**There is no FHIR IG for patient intake, ROS or triage in any realm.** US Core v9.0.0 has **no Questionnaire profile at all**; IPS has no Questionnaire content; the registry's entire "Forms Management" category is three entries. And the registry contains **no Turkish IG**.

### 2.4 CQF / PlanDefinition

`PlanDefinition/$apply` composes with, rather than substitutes for, adaptive questionnaires: **PlanDefinition chooses *which instrument* to administer and when; the Questionnaire chooses *which item within it* comes next.** CPG-on-FHIR formalises the hook (`CPGCollectInformationActivity`, `cpg-collectWith`). But `$apply` is a **batch evaluation against a subject**, with no notion of "the answer I just got", and it emits *requests*, not questions. Use it for section-level gating; never for turn-by-turn.

---

## 3. Instruments: administer PHQ-9 and GAD-7 verbatim

**Do not substitute a CAT-shortened measure.** Six independent reasons, each sufficient alone:

1. **Licensing runs backwards from the usual assumption.** PHQ-9/GAD-7 are **public domain** — *"No permission is required to reproduce, translate, display or distribute."* PROMIS gates commercial use, CAT integration **and translation** behind written Northwestern approval and possible fees: *"Users wishing to integrate instruments into proprietary technological systems… must seek written approval. Proprietary technological systems include, but are not limited to, computerized adaptive tests, apps, and web portals."* Every clause is triggered by this product.
2. **There is no Turkish depression or anxiety item bank.** Querying the HealthMeasures library directly for Turkish returns **123 measures — of which 15 are item banks, and the 11 PROMIS ones are Fatigue, Cognitive Function, Mobility, Physical Function, Upper Extremity and paediatric/proxy variants.** Turkish depression and anxiety exist **only as fixed short forms**. And **every one of the 123 lists `Paper` as its sole administration platform** — no API, no CAT app.
3. **The crosswalk is not warranted for individuals.** PROsetta's authors: *"the ultimate goal of our project was to compare summed scores of **samples (not individuals)**"* — SE for a sample of 75 is 0.63; **for a single individual it is 5.78**. A PHQ-9 of 18 maps to T = 69.2 with a **95 % CI of 62.9–75.4**, against a PROMIS MID of ~3.5 T-points. **Linking error is roughly double the minimally important difference.** The tables also run legacy→PROMIS only; there is no published table converting a CAT T-score back to a PHQ-9 total.
4. **CMS159 hard-codes PHQ-9.** *"initial PHQ-9 or PHQ-9M score greater than nine"*. No converted score is accepted.
5. **A CAT can finish without ever asking about suicide.** Pilkonis et al. 2011, verbatim: *"Nine depression items were eliminated on this basis, and they were items **primarily reflecting suicidality**."* Swapping PHQ-9 for a CAT silently deletes the suicide-screening trigger. That is a patient-safety break, not a psychometric one.
6. **There is no efficiency win.** PHQ-9 is 9 items. A live PROMIS Depression CAT averages **8.13**; Anxiety **9.98**. You would buy r = 0.977 over r = 0.958 for the price of a licence, an IRT engine, and a score no clinician recognises.

CAT-MH is better founded than PROMIS for this use (published pricing, named in MIPS #134, CASSY AUC 0.87 for suicide attempt at 3 months across 14 EDs) — but it is **not FDA-cleared, has no verifiable CE mark, and exists only in English, Spanish and Chinese.**

---

## 4. Ordering rules — each with its justification

**The mnemonics are not evidence.** `OLDCARTS` returns **zero PubMed records**; `SOCRATES[Title] AND pain` returns three papers about the philosopher; `OPQRST` returns five narrative pieces and **zero validation studies**. No RCT compares mnemonic orderings on any patient outcome. **Treat them as coverage schemas to satisfy, not sequences to follow.**

| rule | justification |
|---|---|
| **Open with a genuine uninterrupted turn; budget ~90 s, one turn** | Langewitz, *BMJ* 2002: mean spontaneous talking time **92 s**, median **59 s**, **78 % finish within 2 minutes**, only 7 of 335 exceeded 5 minutes. ⚠️ **But justify it correctly — it does NOT elicit more symptoms.** Bent et al., *Ann Intern Med* 2006, randomised, N = 214: a 53-item checklist elicited **238 adverse events (77 % of patients)**; an open-ended question elicited **11 (14 %)**; p < 0.001. The open turn buys **agenda completeness** (Marvel 1999: late-arising concerns 34.9 % unsolicited vs 14.9 % solicited, at a cost of ~6 seconds) and it **retires structured steps**. Claim that, not symptom yield, or it will not survive a clinician's first challenge |
| **Optimise for *asking*, not for silence** | Dyche & Swiderski, *JGIM* 2005: agenda completed 84.6 % vs interrupted 82.4 % (**p = .83, n.s.**) — but **never solicited 59.2 %** (p = .014). *"Interruption does not curtail ability to identify patient concerns, but failure to ask for the patient's agenda associates with a 24 % reduction in physician understanding."* A voice agent that reliably solicits already beats the human baseline (36–75 % solicitation) |
| **Say "Is there *something* else?" — never "*anything* else"** | Heritage et al., *JGIM* 2007, randomised wording: "something" eliminated **78 % of unmet concerns (OR 0.154, p = .001)**; "anything" was indistinguishable from control (p = .122). Neither lengthened the visit. **The cheapest verified win available** |
| **Backchannel freely** | 70.4 % of consultant interruptions are backchannels; **82.9 % of interruptions overall are cooperative** (Plug 2022; Mulder-Vos 2023). They also mask processing latency |
| **General before specific** | Huang & Cornell, *Psychol Assess* 2015 — two randomised experiments, **17,301 students**: specific probes *before* the general item raised prevalence **29–76 %** |
| **Never place graded variants of the same item adjacently** | Pérez-Romero 2023: separating two adjacent risk-perception items moved endorsement **+63 % to +83 %** |
| **Pregnancy/LMP early, universally** | Ruptured ectopic classically presents in a woman who does not know she is pregnant; and NICE **NG255** scopes sepsis to *pregnant or recently pregnant people of any age*, so sepsis routing needs it |
| **Immunosuppression early, universally** | Neutropenic sepsis is a one-hour emergency and must not depend on an overlay that may not exist |
| **Freeze and version the order** | Brookes et al., *Trials* 2018 — RCT, 116 patients + 71 professionals: order alone changed which items survived to the next round for **26–29 % of items**, and changed completion by **31.3 pp (p = 0.001)**. Changing order between releases silently breaks longitudinal comparability |
| **Keep the ROS short** | Verdon & Siemens 1997: ROS case-finding yield **10.5 %**, individual questions 0.0–1.6 %, **PPV of a given "yes" = 3.3 %**, some items PPV 0.0. CMS 2021 removed the billing reason to be exhaustive |
| **Instruments verbatim, explicit option selection** | An LLM inferring a PHQ-9 score from narrative is not the PHQ-9 |

**"Rapport first, sensitive last" is untested convention.** A PubMed search for sensitive-question placement returns two irrelevant records; practitioner guidance variously says halfway, two-thirds through, and at the end — three different answers. AAPOR prescribes no position. What actually drives disclosure is **perceived social presence and confidentiality**, not position.

---

## 5. Voice-specific constraints

### 5.1 Spoken rating scales show **primacy**, not recency — the folk rule is wrong

The canonical "visual → primacy, auditory → recency" split comes from **categorical** questions. For **rating scales** — which is what PHQ-9, GAD-7 and most symptom items are — Krosnick & Presser state it plainly:

> *"If satisficing respondents consider the options on a rating scale sequentially, they may select the first one that falls in their latitude of acceptance, yielding a **primacy effect under both visual and oral presentation**… the two studies of rating scales that used oral presentation found primacy effects as well."*

Three independent lines converge: theory, two oral-mode experiments (Kalton 1978; Mingay & Greenwell 1989), and the largest health-PRO mode trial (Lee et al. 2021 found primacy in IVR).

**Consequence:** reading *"hiç / birkaç gün / haftanın yarısından fazlası / neredeyse her gün"* in that order biases toward **"hiç"** — the low-severity end. Which is exactly the observed deficit: **Turvey et al. 2012, PHQ-9 by IVR mean 2.8 (SD 3.1) vs paper 4.1 (SD 4.5), ICC 0.65** — authors recommend **a lower cut-point when administered by voice**. A spoken PHQ-9 at ≥ 10 will under-detect.

Mingay & Greenwell also found the primacy effect **stronger among people with more limited cognitive skills** and **unrelated to the speed at which the question was read** — so slowing the TTS will not fix it.

### 5.2 Voice is the worst of the common modes on data quality

Lee, Beebe, Yost et al., *J Patient Rep Outcomes* 2021 — randomised, **n = 1,780 cancer patients**, paper vs tablet vs IVR: no differential item functioning, **but score levels did not hold for IVR** (paper-vs-tablet 29/37 CIs within equivalence margins; IVR only 14/37 and 9/37). IVR fatigue scores **5.69 points lower** than tablet. Missing data **IVR 2.3–6.5 % vs 0.7–3.3 %**.

Bennett et al. 2016, three-mode crossover: IVR **16.3 s per item vs 10.3 paper**, total 5.8 min vs 4.0, *"no problems"* 72 % vs 98 %, and **would prefer for home use: IVR 10 %, tablet 59 %**.

**Breakoff is the dominant failure mode of voice.** Pew 2021: web 5 % / IVR short form 11 % / **IVR long form 20 %**. **Every item added costs more in voice than in any other mode.**

### 5.3 How many spoken options can someone hold?

**This is the largest hole in the evidence base for this product.** No study experimentally varies the number of spoken response categories in a health questionnaire and measures data quality. Krosnick & Presser say so in print: *"most of the literature on number of points involves visual administration."*

Capacity theory points low — Cowan 2001, **~4 chunks** when rehearsal and chunking are blocked — and a survey respondent is *storing and evaluating* each option, a heavier dual load.

The one directly relevant oral experiment, Courser & Lavrakas 2012 (RDD telephone, three 10-point formats):

| format | item nonresponse |
|---|---|
| 1–10 | 19.4 % / 20.6 % |
| 0–10 | 16.1 % / 20.3 % |
| **0–5–10, verbally anchored midpoint** | **11.7 % / 13.9 %** |

**Long numeric scales delivered orally produce 12–21 % item nonresponse — enormous by clinical standards — and verbally anchoring the midpoint recovers 66 % of it.**

**Design pattern: branch, don't enumerate.** Krosnick & Berent: a **two-item branching format took *less* time by telephone** than the equivalent one-item 7-point scale. Two 2–3-option questions beat one 7-option question on both time and order exposure.

⚠️ The widely-quoted "3–7 options max, 5 across and 3 deep" IVR guidance has **no primary source** — it traces to vendor blogs. Do not put it in a regulatory document.

### 5.4 Mitigations to build in

- **Counterbalance response-option order in exactly two arrangements, forward and reverse** — never randomise, which destroys ordinality.
- Use **words or short phrases** as option labels, never full sentences, and keep options mutually exclusive (Holbrook 2007's two strongest moderators).
- **Verbally anchor endpoints and midpoint** on any numeric scale.
- **Offer a text/keypad path for the sensitive block**, and A/B it — this also serves the safeguarding requirement that nothing sensitive is read aloud. Same mitigation, two independent justifications.
- **Treat a spoken negative on PHQ-9 item 9 as weaker evidence than a typed one**, and validate the mode-specific cut-point before trusting ≥ 10.

### 5.5 The accessibility tension, stated plainly

ACASI's disclosure advantage comes from the **dual channel** — audio *plus* visible text *plus* private response. An audio-only product discards half of it. And response-order bias is concentrated in exactly the population a voice-first product is usually pitched as helping: recency effects largest among the **least educated** (Holbrook 2007), primacy stronger among those with **more limited cognitive skills** (Mingay & Greenwell). **Spoken administration transfers measurement error preferentially onto low-literacy and cognitively-impaired patients.** Say this out loud in any product claim.

### 5.6 ISPOR: we cannot inherit the paper validation

Coons et al., *Value Health* 2009 classifies **paper → IVRS as a MODERATE modification requiring formal equivalence testing**: *"The auditory presentation of IVR systems departs from the visual medium in which most PRO measures were developed."* **We owe an equivalence study for every instrument delivered by voice.** The 2023 update relaxes re-testing where comparability evidence exists — but whether that extends to auditory modes is unverified.

---

## 6. Where an LLM may and may not sit

**May:** ASR normalisation · free-text → coded concept mapping · paraphrase and repair ("bunu tam anlayamadım") · ordering *within* a set of safety-equivalent questions · drafting the clinician-facing narrative.

**Must not:** choose or skip a red flag · produce a disposition or urgency recommendation · generate novel question text at runtime · **analyse the audio signal.**

That last one is a bright line with a verbatim citation. **FDA CDS guidance was reissued 29 January 2026, superseding the 6 January 2026 version — check you are reading the current PDF.** Device Example 14:

> *"Software function that analyzes sound waves captured when users cough or recite certain sentences to diagnose bronchitis or sinus infection. **This software is a device function.** It does not meet Criterion 1 because it is intended to analyze a signal or pattern."*

**Any prosody, vocal-biomarker or acoustic-affect feature feeding a clinical output makes that function a device outright, and Criterion 1 failures cannot be rescued by documentation.**

⚠️ **This is a classification finding, not an argument for deleting the lanes — an earlier draft read it as one and that reading is withdrawn.** Three things about it are worth stating precisely, because they are routinely conflated:

1. **It is about the *function*, not the deployment.** Self-hosting the model inside Türkiye is decisive for KVKK Art. 9 and the DPIA and changes nothing here. A signal-analysis function is a device function whether it runs on Kintsugi's servers or ours.
2. **It bites on *"feeding a clinical output"*, not on *existing*.** Example 14's software *diagnoses* bronchitis. An observer lane whose output is quarantined — never entering `SessionState`, never opening a gate, never reaching triage, never rendered to a clinician — is not analysing a signal *to* produce a clinical determination. That quarantine is exactly what `03 §4.7` already specifies, and it is what invariants 10–11 exist to prove.
3. **The instrument is `device_functions`, which the design already has.** This is precisely the boundary that flag was built to draw, and the mechanism for drawing it is **MDCG 2019-11 Rev. 1 §7 module bounding**: the acoustic and affect lanes sit in a bounded module that is *off* in Stage A and enters scope only in Stage B, alongside the clinical investigation that would be needed to validate them anyway.

So the FDA text is not a reason to cut the lanes. It is the reason the lanes **must not be wired to any output before Stage B** — and, separately, the reason **`13`'s "must not" list keeps *"analyse the audio signal"* as a bright line for the *LLM*,** which is a different actor from a bounded, quarantined observer model. Note also that FDA is persuasive-only here: the binding regime is MDR/TİTCK, where the same conclusion arrives via Rule 11 rather than via the CDS criteria.

Two further hard stops from the same document: *"Software functions that support or provide recommendations to **patients or caregivers – not HCPs – meet the definition of a device.**"* And **threshold-triggered alerts fail Criteria 3 and 4** — so suicide escalation must be a **staffed workflow with a live human path, not an automated alarm the software raises**, with crisis triage carved *out* of any CDS claim in labelling.

---

## 7. The safety gate that replaces entropy efficiency

**Put the red-flag battery outside any optimiser and always ask it.** This follows directly from §1.1: low-prior, high-consequence questions have near-zero expected information gain, so any optimiser will drop them.

**Adopt elicitation coverage against a defined red-flag standard set as a CI release gate.** Coverage — not efficiency, not entropy, not average items-to-completion — is the safety KPI.

---

## 8. What to instrument, because these gaps are real

Each of these is a genuine void in the literature, not a search failure, and each is measurable inside the product:

- No experimental study varies the **number of spoken response categories** in a health questionnaire.
- No study measures **patient comprehension or error rates** for spoken administration of PHQ-9 or GAD-7.
- No verified **perceived-latency threshold** for a machine turn. (Stivers et al., *PNAS* 2009 established that human responses peak within **200 ms** across 10 languages — but that is a *production* universal, not a demonstrated tolerance for machine delay. The circulating "exceeding 200–300 ms triggers neurological stress responses" claim appears only in vendor marketing with no primary source. **Do not repeat it.**)
- No study of **ROS item order** changing symptom endorsement.
- **Whether a synthetic conversational voice counts as an "interviewer" for disclosure purposes.** This is the single highest-value open question for this product and it must be settled by an in-product A/B, not by analogy.
- No **RCT or prospective real-patient study** showing adaptive selection beats a fixed protocol on triage accuracy.

Instrument from day one: breakoff by item position · item nonresponse by option count · response-order effects under forward/reverse counterbalancing · **red-flag elicitation coverage**.

---

# PART II · THE ENGINE DESIGN

> **A reframing that changes which criterion actually discriminates.** "Pre-synthesisable" is not about *predicting* the next question — it is about whether the **set of possible utterances is closed at compile time**. If it is (a few hundred `ask_tr` strings in a compiled pack), you pre-synthesise *all* of them and the scripted-turn hit ratio is 1.0 by construction, however exotic the selection rule. **Four of the five candidates have closed utterance sets. Only LLM-chooses-next does not** — which is where the latency argument lands with full force, and nowhere else.
>
> What a **bounded frontier** buys is different and still essential: **device-side prefetch.** A bounded top-K frontier lets the runtime push the next K clip ids down the data channel while the patient is still answering, so the clip is resident before it is needed. Unbounded candidate sets break prefetch, not synthesis.

## 9. The chosen design: a guarded, priority-ordered agenda over a static DAG with a K-bounded frontier

A decision *tree* is the wrong top-level shape — it forces a single active path, while real intake has several independent obligations pending at once (a red-flag probe armed, a must-ask unfilled, a follow-up queued). Modelling that as a tree means duplicating subtrees, which is where skip-logic bugs live. **A DAG of gated steps plus a priority agenda is a superset**; a tree is what you get at K = 1 with re-entry forbidden.

### 9.1 Nine priority classes, one total order

`SAFETY_SCRIPT (0)` — not a question, a RED action script · `GATEKEEPER (1)` — universal facts other *rules* depend on · `OPEN_NARRATIVE (2)` — exactly one step · `REENTRY (3)` — clarification and contradiction reconcile · `RF_PROBE_ARMED (4)` — a red-flag probe whose arming evidence now exists · `MUST_ASK (5)` · `INSTRUMENT_ITEM (6)` — verbatim block, never interleaved · `DETAIL (7)` · `WRAP_UP (8)`.

Sort key is `(priority_class, order, id)` — a **total** order with no floats.

### 9.2 The frontier

```python
def frontier(S: SessionState, k: int = 8) -> tuple[Step, ...]:
    cands = [s for s in S.protocol.steps
             if S.state_of(s) in (NOT_ASKED, UNCLEAR)
             and S.eval(s.gate) is TRUE          # UNKNOWN does NOT open a gate
             and S.eval(s.retire_if) is not TRUE
             and not S.budget.suppresses(s)]
    cands.sort(key=lambda s: (int(s.priority), s.order, s.id))
    return tuple(cands[:k])
```

Three properties fall out, each a CI test:

- **Purity.** `frontier` reads only `S`, and `S = fold(init(protocol_hash, reference_time), events)`. **No wall clock** — `now` is `S.reference_time`, stamped at `SessionStarted` — so replay is exact.
- **Boundedness ⇒ prefetch.** `protocol_next` returns `{step, prefetch: [clip_id for frontier[1:k]]}`.
- **Interleaving is emergent, not policy.** A red-flag probe surfaces at class 4 the instant its gate goes TRUE. Nobody writes an interleaving rule.

### 9.3 Seven answer states

`NOT_ASKED` · `ASKED_PENDING` (ask-ahead bookkeeping) · `ASKED_PRESENT` · `ASKED_ABSENT` — **the only state that may enter `ros_pertinent`** · `UNCLEAR` · `DECLINED` · **`CONTESTED`** (new — two irreconcilable answers; *both* appear in the note).

**An eighth state, `NOT_ASKED_PROXY`** (INT-483, `docs/adr/ADR-040-subject-aware-addressing-for-proxy-sessions.md`; owner decision D24 answer 1Y). Someone answers for the patient, and the pack marks the item skipped in a proxy session. The state is never offered and binds nothing. It carries no value, so every gate and rule reads it as Unknown. It counts against must-ask coverage, and the note shows it as the gap `not_asked_proxy`, never as a negative.

### 9.4 The budget governor — and which way it yields

Let `R = |{must_ask steps still unasked whose gate is TRUE or UNKNOWN}|`. When `turns_remaining ≤ R`, classes 6–8 are filtered out and the UI shows *"birkaç kısa soru kaldı"*. **Class ≤ 1 is never suppressible.**

> **If the budget would still be exhausted, the budget yields — not the safety set.** Emit `BudgetExceeded`, offer continue or pause. An 18-turn cap that can silently drop a must-ask is precisely the mechanism by which this product would generate a note asserting an unelicited negative.

### 9.5 `GuardExpr` — deliberately weaker than FHIRPath

Total, decidable, side-effect-free. Types are `bool, int, decimal(scale), string, code(valueset), date, duration, enum, set` — **no floats anywhere**, `Decimal` with declared scale and exact comparison, because floats are how two machines disagree about the same session. A closed function whitelist (`age_years`, `sex_at_birth`, `overlay`, `section_done`, `any`, `count`, `days_since`, `turns_used`, `turns_remaining`, `mode`). **No user functions, no recursion, no iteration, no fixpoint.**

**Kleene three-valued logic is the type-level fix for the `negatives[]` problem.** A predicate over a `NOT_ASKED` slot returns `UNKNOWN`, never `false`; `TRUE && UNKNOWN = UNKNOWN`, `FALSE && UNKNOWN = FALSE`; **a gate opens only on TRUE.**

Contrast SDC, which concedes its own expression evaluation may need *"iterative updating of expressions until values reach a stable state - or until an unstable looping condition is detected"*, and that a questionnaire can be built where an answer depends indirectly on itself. **We make that unrepresentable rather than detectable.**

**Five CI-blocking compiler checks:** typing and scope · **stratified acyclicity** (a gate on step *S* may reference only slots owned by steps of strictly lower `(priority, order)`) · **`must_ask` reachability** by finite-domain enumeration — this extends `every_RED_rule_is_reachable_from_every_branch` from rules to *steps* · **termination** (every turn strictly decreases `|NOT_ASKED| + |queued re-entries|`, and re-entries are attempt-capped) · **clip and delivery coverage** — every voice step has a clip for every configured voice, and **every `text_only` step has none**, which makes "nothing sensitive can be accidentally spoken" a build-time guarantee.

### 9.6 Where information gain is allowed — the whole answer in one line

**It may choose the *authored* order. It may not choose the *asked* order.**

- **Tier 0 — runtime selection: forbidden.** Not for latency (the item set is closed) but because the selection policy would become a performance characteristic needing V&V, and because its characteristic failure mode is **confidently skipping** a question the model is sure it knows the answer to — which produces a note reading as *elicited* when it was *inferred*.
- **Tier 1 — a frozen integer yield table: permitted, narrowly.** Within `DETAIL` only, and only among steps in the same section, a compiled `yield_table: dict[StepId, int]` may replace `order` as the sort key. Integers, a build artefact, **covered by `protocol_hash` and the cosign signature** — so selection stays a pure function of `(protocol_hash, events)` and replays exactly. It never touches classes 0–6.
- **Tier 2 — offline, in Loop 2: encouraged.** Compute conditional entropy reduction over de-identified completed intakes at the existing k ≥ 10 / ≥ 2 clinics / 2-week thresholds, and emit **proposals** — regenerate the yield table, reorder within a class, add a gate, retire a zero-yield DETAIL step. Add `yield_table` to `proposal_scope`'s allowed list and **`must_ask` to its forbidden list**.

## 10. Why `$next-question` fails as the flow contract — the structural reason

Seven reasons in the research above; this is the one that settles it.

> **On `sdc-questionnaire-adapt`, `Questionnaire.url` and `Questionnaire.version` are both `..0` — prohibited.** The only durable identity is one `derivedFrom` canonical.

**There is no slot on the wire for the pack version, the rule-set version, or the flow-logic version.** `protocol_hash` pinning is the single artefact that makes the "pure, replayable" claim true and that unlocks MDCG 2020-1 §4.4's module-level clinical-performance re-validation — *"validation of the CLINICAL PERFORMANCE is also permissible on module level when the functionality of the modules is independent."* `$next-question` cannot carry it, so adopting it **forfeits the modular validation allowance**.

(The IG's own examples violate this: both contained Questionnaires carry `"version": "0.0.1"` despite `version` being max-0, and the contained `id` *changes* mid-conversation.)

Three more that matter operationally: the spec is **silent on determinism** and does not even declare `affectsState`; the server **"may silently retract" previously-sent unanswered questions** — in a form a field disappears, in a *voice* product it means retracting a question the patient has already heard and is answering, with no defined client behaviour; and it puts sequencing behind a network hop carrying the full growing history each turn, when the RED preemption must fire **agent-side at ≤ 300 ms** and cannot wait for a remote sequencer.

**And it buys zero interoperability.** A global GitHub search for `"$next-question"` returns **four repositories, all Da Vinci DTR**.

### 10.1 `enableWhen` cannot reorder anything — five confirmations

This is why answer-dependent *ordering* must live in the application layer regardless:

1. R4 §2.37.5 and R5 §2.5.6, verbatim and identical: *"The order of questions within groups… **must be retained for display and capture**."* Unconditional MUST, no `enableWhen` carve-out.
2. The element is defined purely as enablement — *"enabled (displayed/allow answers to be captured)"*.
3. Is-modifier semantics are deletion, not relocation; survivors keep relative order.
4. R5's `disabledDisplay` has exactly two codes, and `protected` — *"should still be visible"* — **exists specifically so a disabled item stays in position**.
5. SDC v4.0.0: *"All questions get displayed in order."*

Core FHIR concedes it outright: *"Specific controls on dynamic display of groups, questions, etc. based on the answers to other questions is outside the scope of the base resource."*

### 10.2 What the one real CAT engine had to do

Northwestern's PROMIS Assessment Center exposes `POST …/Questionnaire/{id}/next-q` — **no `$` sigil, instance-level** where SDC is strictly type-level, so a conformant SDC client cannot talk to it. And it carries θ and SE in **six extensions minted inside HL7's own namespace that do not exist** (`questionnaire-scores`, `/theta`, `/standarderror`, `-expirationTime`, `-finishedTime`, `-optionScore`, `-displayOrder` all 404). Sample data `lastUpdated: 2019-10-01`.

**The one organisation running CAT at scale had to squat HL7's namespace to carry the state the operation cannot express — and then froze it.**

### 10.3 What to adopt instead

Keep FHIR R4 `Questionnaire`/`QuestionnaireResponse` as the export. **Add a post-hoc adaptive export** — after the session, render the *realised path* as a `sdc-questionnaireresponse-adapt` with the contained Questionnaire being the steps actually asked and `derivedFrom` our canonical, `questionnaire-derivationType = compliesWith`. That is honest ("this patient was asked this subset") and is what a hospital integrator will want. New endpoint `GET /protocols/{id}/questionnaire?profile=adapt`.

**Compiler gate:** emit `enableWhen` where projectable, `enableWhenExpression` (FHIRPath) otherwise, and **fail the build if a gate is expressible in neither** — that keeps `GuardExpr` inside a projectable subset. CI asserts the export is never fed back into the engine: it is documentation, not an executable form.

**Offer `$populate` as a *server*, P2** — a genuine procurement asset, cheap once the compiler emits Questionnaires, and populated answers arrive as **unconfirmed** slots that generate `confirm` steps, which is exactly our confirm-don't-reask semantics.

## 11. Follow-up, contradiction, and the ask-ahead race

### 11.1 Clarification → a class-3 re-entry, bounded at 2 attempts

The re-entry uses the origin slot's **`follow_up_tr`**, already mandatory on every required slot — so it is **pre-synthesised, and a follow-up is a clip hit, not a TTS miss**. After 2 attempts the slot becomes `UNCLEAR` and enters `data_gaps[]` and `suggested_focus_questions[]`. There is no third attempt: an unbounded clarification loop is both a turn-budget bomb and a CSAT failure (*"beni anlamadı"* is an existing reason chip).

### 11.2 Contradiction — and it can never lower triage

A contradiction is an update to an already-elicited slot whose new value is not `subsumes`-compatible with the old, where `subsumes` is a declared per-type relation. *"üç gün" → "72 saat"* is a refinement; *"ateşim yok" → "dün 38.5 vardı"* is a reversal.

The engine **does not overwrite**. It emits `ContradictionDetected`, sets `CONTESTED`, and **re-evaluates triage under a worst-case union — if either value would fire a rule, the rule fires.** Monotonic: a contradiction can never lower a level, and that must be a type-level guarantee rather than a convention. A class-3 reconcile step follows. **On non-resolution the slot stays `CONTESTED`, both values appear in the note labelled as conflicting, the section is excluded from `patient_confirmed_sections`, and the worst case stands.**

**Recency never silently wins.** That is the difference between a note a clinician can trust and one they cannot.

### 11.3 ⚠️ The ask-ahead race that is currently a fabricated-data path

Step *n* = *"Ateşiniz var mı?"*; step *n+1*, already asked ahead, = *"Kaç gündür ateşiniz var?"*; then *n* extracts to `fever = absent`. **The answer to *n+1* is now meaningless — and if stored, it is fabricated clinical data.** This case is not in the current spec.

**Rule:** emit `StepInvalidated{step_id, invalidated_by}`, **discard** the answer rather than storing it, record nothing for that slot.

**Prevention is computed, not authored.** `ask_ahead_eligible` is derived by the compiler from the gate dependency graph it already builds for the acyclicity check: **false** iff the step's gate references a slot owned by the immediately preceding step, or it is an instrument item, or `priority ≤ 1`. When `frontier[1]` is ineligible the Talker plays a **cached one-word bridge** (*"Anladım."*) — one ~330 ms scripted turn, a clip hit, correctness preserved. Track `ask_ahead_stalls_per_session`.

### 11.4 Replay

The trick is simple: **the nondeterministic component is recorded as an input, never re-executed.** Events carry `SessionStarted{protocol_hash, pack_signature, reference_time, …}`, `FrontierComputed{basis_event_seq, optimistic_assumption?, k, step_ids}`, `StepAsked{clip_id | dynamic_text_hash, presentation_order_variant, delivery}`, `ExtractionLanded{model_id, prompt_version, …}`, `ContradictionDetected`, `StepInvalidated`, `TriageEvaluated{rule_ids, level, inputs_hash}`.

Contract: `fold(engine_init(protocol_hash, reference_time), events) == final_state`, exactly. Replay needs **no LLM and no clock**.

The payoff is a regression surface: **a nightly job replays de-identified production sessions against a candidate pack and diffs the question sequence.** That diff is the review artefact for every protocol PR — and it is precisely the *"objective evidence that the MDSW specifications conform to user needs… and that the requirements implemented can be consistently fulfilled"* that MDCG 2020-1 §4.3 asks for.

## 12. Corrections to widely-repeated figures

Three claims in circulation are wrong as usually stated, and two of them would land in a clinical evaluation file.

| claim | actually |
|---|---|
| **"NICE CG151 requires antibiotics within 1 hour"** | **CG151 contains no one-hour threshold anywhere.** Rec 1.4.1.1 says *"offer empiric antibiotic therapy **immediately**"*; its only clock is 1.5.1.1, risk assessment *"within 24 hours"*. The one-hour figure is **NG255 rec 1.7.2**, and **the clock starts at meeting high-risk criteria, not at the door**. IDSA's *"within 2 h"* is ungraded narrative text. `rf.neutropenic_fever.source` must cite CG151 1.4.1.1 — **a fabricated one-hour threshold in a clinical evaluation file is a finding waiting to happen** |
| **Beckman's "18 seconds"** | not verifiable from the abstract. Use **Marvel 1999's 23.1 s**, or Coyle 2022's pooled 18.2 s — and note the coincidence trap: those are different figures that happen to look alike |
| **Miller's "7±2" as a spoken-options limit** | Miller explicitly *separated* absolute judgment from immediate memory and called seven *"only a pernicious, Pythagorean coincidence."* The applicable figure is **Cowan 2010: "3 or 4 longer verbal chunks, such as idioms or short sentences"** — which is what response options are. The "3–5 IVR menu options" rule has **no traceable primary source**; mark it folklore |

Also: **Krosnick & Alwin 1987 tested *visual* show-card presentation and found *primacy*.** Auditory recency is their theoretical *prediction*, not their finding — cite Schwarz et al. 1991/1992 for the mode contrast.

## 13. The safeguarding exception — where the honest design is to under-ask

Fincher et al. 2015 (RCT, N = 368) found **face-to-face produced *more* IPV disclosure than computer** — prior-year any IPV aOR 2.02, **sexual IPV aOR 4.31**. The plausible mechanism is that IPV disclosure is **help-seeking directed at a person who can respond**, not a confession to be extracted. A voice agent that cannot respond may **suppress** exactly the disclosure we most need.

**Therefore, for safeguarding the product should not attempt to elicit a disclosure at all.** Present a discreet, text-only *route to help*; keep the `CLINICIAN_ONLY` disposition invisible to the patient and to any proxy; provide the discreet exit; and **measure nothing.**

`delivery: voice | text_first | text_only` becomes a DSL field per section and per slot. `screening` (PHQ/GAD/C-SSRS) is **`text_only`**; substance use, sexual and reproductive history, and pregnancy/LMP are **`text_first`**; safeguarding is **`text_only` with no extraction attempted**.

**And reading it aloud is not a mitigation** — adding audio to a silent computer bought nothing (ACASI-vs-CASI moderator γ = −0.01 and −0.03, both ns). **`text_only` must mean text only: no clip, no `speech_tr`, ever** — enforced by the compiler check in §9.5.

**The highest-value trigger, and the least implemented:** a **third party detected present** switches every sensitive section to text. Presence of others is the largest single moderator in two meta-analyses (Ω 1.61 alone vs 1.18 with others, ΔR² = .50; predicted d 0.12 vs 0.65; OR 3.0 in households with children). The current companion flow treats a third party as a **feature**; for sensitive sections it is a **confound**.

## 14. What this changes in `03`

1. `next_step()` → **`frontier(k=8)`**, with the nine classes and the total sort key.
2. `AnswerState` gains **`CONTESTED`** (seven states).
3. Add the **`GuardExpr` specification** — grammar, types, Kleene semantics, closed whitelist, and the explicit prohibitions (no floats, no wall clock, no hash-map iteration order, no fixpoint).
4. Add the **five compiler checks** as CI-blocking.
5. Add the **budget governor**, including *the budget yields before the safety set does*.
6. Add the **event-log types** and the replay contract.
7. **Ask-ahead becomes conditional on `ask_ahead_eligible`**, compiler-derived — a concrete amendment to §4.1's blanket ask-ahead.
8. Add **`StepInvalidated`** semantics (§11.3).
9. `protocol_next` gains **`prefetch`**, **`delivery`**, **`presentation_order_variant`**. The six-tool surface is unchanged.
10. **New invariant 12** (replay equality) and **13** (no `text_only` clip).
11. FHIR export fidelity gate; post-hoc adaptive export; `$populate` **as a server**, P2; `$next-question` **not** as an internal contract.
12. Compiler emits the **`yield_table`** and the two fixed presentation-order variants.
13. In `04`: promote **pregnancy/LMP** and **immunosuppression** to class-1 gatekeepers with a compiler assertion that each precedes every step whose gate references it; fix `rf.neutropenic_fever.source`; branch sepsis across NG253/NG254/NG255 by age and pregnancy; add the compound-turn form (≤ 4 items, "hayır" default) for the unarmed life-threat block.
14. New KPIs: **`turns_to_RED` p50/p90 split by `device_functions`** · `steps_retired_by_open_narrative` · `contradictions_per_session` · `ask_ahead_stalls_per_session` · `frontier_recompute p99 ≤ 5 ms` · `text_mode_entry_rate` · **per-section disclosure delta between voice and text delivery**, which is the in-product A/B that would actually validate the 5–16 pp claim rather than assuming it.

**New ADR-021 — "Deterministic frontier engine; no runtime information-gain; `$next-question` rejected as the flow contract."**
