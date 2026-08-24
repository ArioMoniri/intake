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
| **Open with a genuine uninterrupted turn; budget ~2 minutes** | Langewitz, *BMJ* 2002: mean spontaneous talking time **92 s**, median **59 s**, **78 % finish within 2 minutes**, only 7 of 335 exceeded 5 minutes |
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

**Any prosody, vocal-biomarker or acoustic-affect feature feeding a clinical output makes the product a device outright, and Criterion 1 failures cannot be rescued by documentation. Transcription only.** This independently confirms the decision to cut the `affect` and `acoustic` observer lanes.

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
