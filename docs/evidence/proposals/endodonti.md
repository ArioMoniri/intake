# Endodonti (Endodontics — Root Canal) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher subagent · Date: 2026-09-20 · Specialty: Endodonti (Endodontics —
root canal) · Branch slug: `endodonti`
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom / history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no**
clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's own
  urgency wording is quoted verbatim; **no level is asserted**.
- **Airway / spreading-infection emergency stays in `base.life_threat` (invariant 7).** The
  life-threatening odontogenic-infection presentation (mouth-floor / neck swelling with difficulty
  breathing or swallowing — Ludwig's angina) is an **airway emergency** that belongs to the sibling
  **`base.life_threat`** set (the life-threat `red_flags` block in
  `packages/protocols/base/intake.yaml`, e.g. `rf.dyspnoea_rest` / `rf.sepsis_like`, all currently
  `draft_needs_source`). Per invariant 7 that set is **outside the inheritance chain and nothing may
  extend it** — so the endodonti specialty pack must **neither add nor relax** an airway/spreading-
  infection RED. The airway screen below (Q8) is an **intake screen that routes into that existing
  base mechanism**, not a new specialty red-flag.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / WebSearch, and `pdftotext` over the fetched PDFs). Before
  sign-off, each verbatim sentence MUST be re-checked against the **primary published text** and
  committed as a **verbatim source snapshot** with a full `source: {guideline_id, version, date, url,
  retrieved_on}` block. Until then any derived rule stays `status: draft_needs_source` and does **not**
  compile into a served pack.
- **Türkiye-first gap (up front):** the served pack `packages/protocols/specialty/endodonti.yaml` is an
  **L0 draft** (`extends: cluster.dental`, `maturity: L0`,
  `status: generated-l0-awaiting-clinical-review`) whose header already states the branch clinician
  must source rules from **T.C. Sağlık Bakanlığı klinik protokolleri / HSGM rehberleri** and **İlgili
  uzmanlık derneği kılavuzları**, and that files/04 and files/09 name **no** specific 'dental' cluster
  guideline title. A dedicated Turkish search on 2026-09-20 returned only private-hospital marketing
  pages — **no versioned Türkiye-first clinical guideline document was located** (see §4). The sources
  below are therefore international (ESE / AAE / RCEM), pending Türkiye-first replacement.
- This file does **not** edit the served L0 pack, `previsit_intake.v1.opt`, `base.life_threat`, or any
  other served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — AAE Consensus Conference Recommended Diagnostic Terminology (endodontic pain / abscess descriptors)
- **guideline_id (proposed):** `AAE-DXTERM-2009`
- **Publishing body:** American Association of Endodontists (AAE) Consensus Conference, published in the
  Journal of Endodontics
- **Version / year:** 2009 (AAE consensus terminology, still the standard reference set)
- **Citation:** American Association of Endodontists. *AAE Consensus Conference Recommended Diagnostic
  Terminology.* J Endod. 2009;35(12):1634. (Glossary reproduced by AAE.)
- **URL:** https://www.aae.org/specialty/wp-content/uploads/sites/2/2017/07/aaeconsensusconferencerecommendeddiagnosticterminology.pdf
  (PDF fetched; text extracted verbatim via `pdftotext`)
- **Verbatim (Pulpal — Symptomatic irreversible pulpitis):**
  > "A clinical diagnosis based on subjective and objective findings indicating that the vital inflamed
  > pulp is incapable of healing. Additional descriptors: lingering thermal pain, spontaneous pain,
  > referred pain."
- **Verbatim (Apical — Symptomatic apical periodontitis):**
  > "Inflammation, usually of the apical periodontium, producing clinical symptoms including a painful
  > response to biting and/or percussion or palpation. It might or might not be associated with an
  > apical radiolucent area."
- **Verbatim (Apical — Acute apical abscess):**
  > "An inflammatory reaction to pulpal infection and necrosis characterized by rapid onset, spontaneous
  > pain, tenderness of the tooth to pressure, pus formation, and swelling of associated tissues."
- **Verbatim (Apical — Chronic apical abscess):**
  > "An inflammatory reaction to pulpal infection and necrosis characterized by gradual onset, little or
  > no discomfort, and the intermittent discharge of pus through an associated sinus tract."
- **Confidence: HIGH** (direct PDF text extraction). Grounds the endodontic **symptom-quality** intake
  questions (thermal sensitivity + lingering pain, spontaneous pain, pain on biting/pressure, swelling /
  pus / sinus-tract discharge). These are **symptom descriptors** used only to phrase patient questions —
  **no diagnosis is asserted to the patient**.

### S2 — ESE position statement: the use of antibiotics in endodontics (systemic involvement / spreading infection)
- **guideline_id (proposed):** `ESE-ANTIBIOTICS-2018`
- **Publishing body:** European Society of Endodontology (ESE)
- **Version / year:** 2018
- **Citation:** Segura-Egea JJ, Gould K, Şen BH, Jonasson P, Cotti E, Mazzoni A, Sunay H, Tjäderhane L,
  Dummer PMH. *European Society of Endodontology position statement: the use of antibiotics in
  endodontics.* Int Endod J. 2018;51(1):20–25. DOI: 10.1111/iej.12781 · PMID: 28436043.
- **URL (mirror fetched):** https://personal.us.es/segurajj/documentos/PTD-III/Art%C3%ADculos%20segundo%20parcial/99-IEJ-ESE%20Position%20statement%20Antibiotics-2018.pdf
  (author-hosted copy; text extracted verbatim via `pdftotext`. Publisher page
  https://onlinelibrary.wiley.com/doi/10.1111/iej.12781 returned HTTP 403 on retrieval.)
- **Verbatim (indications for adjunctive systemic antibiotics, items 2–3):**
  > "Acute apical abscess with systemic involvement (localized fluctuant swellings, elevated body
  > temperature >38°C, malaise, lymphadenopathy, trismus)"
  > "Progressive infections (rapid onset of severe infection in <24 h, cellulitis or a spreading
  > infection, osteomyelitis) where onward referral to oral surgeons"
- **Confidence: MEDIUM–HIGH.** Retrieved verbatim from an author-hosted mirror PDF; the systemic-
  involvement wording was **independently corroborated** by S5 (AAE) and by a web-search summary →
  higher confidence on the *concept*. Re-capture from the **primary Wiley text** on sign-off. Grounds
  the fever-with-swelling (Q7) and trismus (Q9) intake screens. The antibiotic decision itself is
  clinician-facing and out of scope for patient intake.

### S3 — RCEM Learning: Dental Emergencies (odontogenic-infection airway compromise / Ludwig's angina)
- **guideline_id (proposed):** `RCEM-DENTAL-EMERG-2023`
- **Publishing body:** Royal College of Emergency Medicine (RCEM) Learning (educational reference, not a
  formal clinical guideline)
- **Version / year:** last updated 25/09/2023 (authors: Chris Connolly, Katherine Rankin)
- **URL:** https://www.rcemlearning.co.uk/reference/dental-emergencies/
- **Verbatim (airway assessment):**
  > "The presence of any of the following may indicate actual or impending airway compromise and should
  > prompt an urgent senior anaesthetic assessment: Stridor, Difficulty in breathing, Dysphagia,
  > Dysphonia (alteration in the character of the voice)."
- **Verbatim (Ludwig's angina):**
  > "Ludwig's Angina is a potentially life threatening complication of untreated dental infection. It is
  > a rapidly progressing submaxillary, submandibular, and sublingual necrotizing cellulitis and can
  > lead to airway obstruction and death."
- **Confidence: MEDIUM.** Authoritative body (RCEM), but an educational reference page rather than a
  versioned guideline. Grounds the **airway/spreading-infection screen (Q8)** whose RED belongs to
  `base.life_threat` (invariant 7). Re-verify; ideally back with a primary deep-neck-space-infection /
  airway guideline and a **T.C. Sağlık Bakanlığı** source.

### S4 — Ludwig's angina (A.D.A.M. medical encyclopedia — "go to the emergency room")
- **guideline_id (proposed):** `ADAM-LUDWIG` — **patient-education encyclopedia, NOT a clinical
  guideline** (A.D.A.M., Inc. / VeriMed Healthcare Network, hosted by UF Health)
- **Version / year:** last reviewed 2025-01-29 (reviewer: Ashutosh Kacker, MD, FACS, Weill Cornell)
- **URL:** https://ufhealth.org/conditions-and-treatments/ludwig-angina (A.D.A.M. text; also MedlinePlus
  ency/article/001047)
- **Verbatim (When to Contact a Medical Professional):**
  > "Breathing difficulty is an emergency situation. Go to the emergency room or contact your local
  > emergency number (such as 911) right away."
- **Verbatim (symptoms captured):** "Breathing difficulty" · "Difficulty swallowing" · "Drooling" ·
  "tongue swelling" · "neck swelling"
- **Confidence: LOW–MEDIUM.** A patient-education encyclopedia, not a versioned airway guideline. The
  Türkiye `112` affordance is **not** sourced here (see §4). Must be re-verified / replaced by a primary
  source before it grounds any RED action script. (Same source used by the oral-surgery sibling
  proposal.)

### S5 — AAE Guidance on the Use of Systemic Antibiotics in Endodontics (corroborates S2)
- **guideline_id (proposed):** `AAE-SYSANTIBIOTICS`
- **Publishing body:** American Association of Endodontists (AAE) Committee on Antibiotic Use in
  Endodontics
- **URL:** https://www.aae.org/specialty/wp-content/uploads/sites/2/2017/06/aae_systemic-antibiotics.pdf
  (PDF fetched; text extracted verbatim via `pdftotext`)
- **Verbatim (systemic involvement):**
  > "in cases with evidence of systemic involvement (fever, malaise, cellulitis and/or lymphadenopathies)
  > following adequate endodontic disinfection and abscess drainage if swelling is present"
- **Note:** cited only to **corroborate S2's systemic-involvement sign list**; the antibiotic-prescribing
  decision is clinician-facing and out of scope for patient intake.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Same posture as the cardiology / oral-surgery proposals: the committed `.opt` is deliberately **shallow**
— composition and archetype **roots** only, **no at-code (`atNNNN`) leaf nodes**. Each item binds to an
archetype **root**; the leaf path is **deferred** (`openehr_deferred_reason`, INT-032; HB-C12), never
fabricated. Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL).

| # | Proposed captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's endodontic visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| 2 | Narrative of the tooth complaint (story of present complaint) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Tooth pain with hot/cold, lingering (S1 — symptomatic irreversible pulpitis) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Spontaneous / unprovoked tooth pain, incl. at night (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Pain on biting / chewing / pressure (S1 — symptomatic apical periodontitis) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Gum swelling / pus / bad-taste discharge — "gum boil" / sinus tract (S1 — acute & chronic apical abscess) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Facial/jaw swelling **with fever** (S2 systemic involvement; S5) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Difficulty breathing/swallowing + mouth-floor/neck swelling — **airway (Ludwig's)** (S3, S4) → screen routes to `base.life_threat` | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Limited mouth opening / trismus (S2; S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Prior root-canal / known dental diagnosis on this tooth (S1 — "Previously treated") | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current medications, incl. any antibiotic already started for this tooth | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug / local-anaesthetic / latex allergy | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate triage outcome (rules engine only; max `YELLOW_REVIEW` from LLM) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Note: the **airway RED itself** (item 8) is authored in `base.life_threat`, not here (invariant 7); the
intake item captures the *screen answer* and routes it to that base mechanism. Systemic-history items
(diabetes affecting healing, pregnancy, immunosuppression) would bind to
`EVALUATION.problem_diagnosis.v1`; they are held for clinician addition (§4) rather than fabricated as
leaf paths here.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; **one concern per question** (invariant 2: one question per
turn); empathetic; **no diagnosis/treatment/prognosis** language (PolicyGuard-clean — questions describe
*symptoms*, never name a disease). Numerals are **spelled out** (invariant 22: the compiler must expand
every digit before TTS; these drafts avoid digits and carry no time threshold — the unsourced
"yarım dakika" example was dropped on review). **All marked "CANDIDATE — clinician to approve
wording".**

Revised 2026-09-26 per docs/evidence/verification/specialty-wave4-5.md §B (reviewer's replacement
texts used verbatim). Renumbering, old → new — sections outside §3 still use the old numbers: Q1, Q2
unchanged · Q3 → Q3 (thermal pain) + Q4 (lingering, if Q3 yes) · Q4 → Q5 · Q5 → Q6 · Q6 → Q7 (gum
swelling) + Q8 (discharge) · Q7 → Q9 (swelling) + Q10 (fever, if Q9 yes) · Q8 → Q11 · Q9 → Q12 ·
Q10 → Q13 · Q11 → Q14 (medications) + Q15 (antibiotic) · Q12 → Q16.

> Triage note for every red-flag-derived item: any level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. Authoritative RED/YELLOW must come
> from `packages/protocols/triage` with a committed `source` snapshot and all three RED axes
> (route × register × location, invariant 21), none of which are supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü randevunuzda sizi hekime getiren asıl şikâyetiniz nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Complaint narrative (story)** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu şikâyetiniz başladığından bu yana nasıl değişti?"
CANDIDATE — clinician to approve wording.

**Q3 — Thermal sensitivity** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (AAE —
symptomatic irreversible pulpitis: "lingering thermal pain")
> "Sıcak ya da soğuk bir şey yiyip içtiğinizde dişiniz ağrıyor mu?"
gen: slot=dis_hassasiyeti; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Lingering thermal pain (if Q3 yes)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(AAE — symptomatic irreversible pulpitis: "lingering thermal pain")
> "Bu ağrı, yiyecek ya da içecek ağzınızdan gittikten sonra da sürüyor mu?"
gen: slot=agri_sonra_suruyor; type=boolean; ask_if=dis_hassasiyeti == true
CANDIDATE — clinician to approve wording. No duration threshold is asked: AAE says only "lingering".

**Q5 — Spontaneous pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (AAE —
"spontaneous pain")
> "Dişiniz hiçbir neden yokken kendiliğinden ağrıyor mu?"
gen: slot=kendiliginden_agri; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Pain on biting / pressure** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (AAE —
symptomatic apical periodontitis: "a painful response to biting and/or percussion or palpation")
> "Bu dişinizle ısırdığınızda, çiğnediğinizde ya da üzerine bastırdığınızda ağrı hissediyor musunuz?"
gen: slot=isirinca_agri; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Gum swelling / "gum boil"** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (AAE —
acute apical abscess: "pus formation, and swelling of associated tissues")
> "Dişinizin yanındaki diş etinde şişlik ya da sivilce gibi bir kabarcık var mı?"
gen: slot=dis_eti_sisligi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: none by itself; feeds Q9–Q11 if accompanied
by fever or breathing/swallowing difficulty.

**Q8 — Discharge / bad taste** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (AAE — chronic
apical abscess: "discharge of pus through an associated sinus tract")
> "Ağzınıza kötü tadı olan bir akıntı geldiğini fark ettiniz mi?"
gen: slot=kotu_tatli_akinti; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: none by itself.

**Q9 — Facial/jaw swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (ESE — "Acute
apical abscess with systemic involvement …") + S5 (AAE — "fever, malaise")
> "Yüzünüzde ya da çenenizde şişlik var mı?"
gen: slot=yuz_cene_sisligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Fever with the swelling (if Q9 yes)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
(ESE — "Acute apical abscess with systemic involvement … elevated body temperature >38°C") + S5 (AAE —
"fever, malaise")
> "Bu şişlikle birlikte ateşiniz de var mı?"
gen: slot=sislik_ile_ates; type=boolean; ask_if=yuz_cene_sisligi == true
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** if swelling with fever, per S2/S5 (systemic involvement). Level/axes NOT supplied (§4).

**Q11 — Difficulty breathing or swallowing (AIRWAY — Ludwig's)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S3 (RCEM — "actual or impending airway compromise … Stridor,
Difficulty in breathing, Dysphagia") + S4 (A.D.A.M. — "Breathing difficulty is an emergency situation. Go
to the emergency room…")
> "Nefes almakta ya da yutkunmakta zorlanıyor musunuz?"
gen: slot=nefes_yutkunma_guclugu; type=boolean
CANDIDATE — clinician to approve wording. No longer narrowed to floor-of-mouth/neck swelling: RCEM
lists any of breathing difficulty or dysphagia. Candidate_flag: **candidate acute-airway concern, pending
clinician + rules-engine confirmation — NOT authoritative**. **This is the airway/spreading-infection
screen; its RED belongs to `base.life_threat` (invariant 7) — NOT a specialty red-flag.** RED script,
register and the REMOTE/ON_SITE/UNKNOWN location scripts (invariant 21) are **not** supplied here; the
Türkiye `112` affordance is unsourced (§4).

**Q12 — Limited mouth opening / trismus** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (ESE —
"trismus") + S3 (RCEM)
> "Son zamanlarda ağzınızı açmakta zorlanıyor musunuz?"
gen: slot=agiz_acma_guclugu; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **candidate — NOT authoritative**; source S2/S3.

**Q13 — Prior root canal / known dental diagnosis on this tooth** · archetype:
`EVALUATION.problem_diagnosis.v1` · source: S1 (AAE — "Previously treated" category) + general history
> "Bu dişinize daha önce kanal tedavisi ya da başka bir diş tedavisi yapıldı mı?"
gen: slot=onceki_dis_tedavisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q14 — Current medications** · archetype: `ACTION.medication.v1` · source: general intake
> "Şu anda düzenli kullandığınız ilaçlar var mı?"
gen: slot=duzenli_ilac; type=boolean
CANDIDATE — clinician to approve wording. Medication history only; no instruction to start/stop any
medication is given here (that is a clinician decision).

**Q15 — Antibiotic already started for this tooth** · archetype: `ACTION.medication.v1` · source:
general intake (S2 context — antibiotics)
> "Bu diş için son günlerde antibiyotik kullanmaya başladınız mı?"
gen: slot=yeni_antibiyotik; type=boolean
CANDIDATE — clinician to approve wording. Medication history only; no instruction to start/stop any
medication is given here (that is a clinician decision).

**Q16 — Drug / local-anaesthetic / latex allergy** · archetype: `EVALUATION.adverse_reaction_risk.v1` ·
source: general intake
> "Herhangi bir ilaca, diş uyuşturma iğnesine ya da lateks eldivene alerjiniz var mı?"
gen: slot=ilac_alerjisi; type=boolean
CANDIDATE — clinician to approve wording.

*(16 candidate questions: Q3–Q12 source-derived symptom/red-flag context; Q1–Q2/Q13–Q16 general intake /
history. Q10 fever-with-swelling and Q12 trismus cite ESE (S2); Q11 airway cites RCEM (S3) + A.D.A.M.
(S4) and routes to `base.life_threat`; Q3–Q8 cite AAE terminology (S1).)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first versioned clinical guideline (MoH / HSGM / specialty society).** A dedicated Turkish
   search (2026-09-20) returned only private-hospital marketing pages — **NO SOURCE FOUND (versioned,
   authoritative) — clinician must supply** the correct **T.C. Sağlık Bakanlığı klinik protokolleri /
   HSGM rehberleri** or Turkish specialty-society (e.g. Türk Endodonti Derneği) document and its
   version/date, as the served L0 pack header itself requires. Turkish endodontic diagnostic terminology
   equivalents for S1 must also be clinician-confirmed.
2. **Türkiye emergency affordance ("112" for airway / spreading infection).** Only the LOW–MEDIUM
   patient-education S4 (US "911") was retrieved. **NO SOURCE FOUND (primary / Türkiye) — clinician must
   supply**; and per invariant 21 the RED script + register + REMOTE/ON_SITE/UNKNOWN location axes are
   **not** set here (under ON_SITE the 112 affordance must be **absent, not de-emphasised**). The RED
   itself lives in `base.life_threat` (invariant 7), which this proposal does not touch.
3. **Airway / spreading-odontogenic-infection RED as a versioned Türkiye clinical source.** S3 (RCEM) is
   an educational reference and S4 (A.D.A.M.) is a patient encyclopedia. **NO SOURCE FOUND (versioned
   Türkiye clinical guideline) — clinician must supply** a primary deep-neck-space-infection / Ludwig's
   angina source.
4. **ESE position statement primary verbatim (S2).** Retrieved from an author-hosted mirror PDF; the
   Wiley publisher page returned HTTP 403. **Primary Wiley verbatim NOT retrieved — re-capture on
   sign-off** and reconcile the exact indication numbering.
5. **Post-treatment / abscess "when to seek help" escalation threshold for patients.** S2/S5 ground
   clinician-facing antibiotic decisions, not a patient-facing post-op escalation threshold (e.g.
   worsening swelling after a root canal). **NO SOURCE FOUND (patient escalation) — clinician must
   supply.**
6. **Fever numeric threshold in patient copy.** S2's ">38°C" is a *clinician* criterion; the patient
   question (Q7) deliberately asks about "ateş" without a number. Whether any numeric threshold should be
   surfaced to the patient (and, if so, spelled out per invariant 22) is **a clinician decision — NO
   SOURCE FOUND for a patient-facing number.**
7. **Dental-trauma history (avulsion / luxation → pulp necrosis).** Relevant to endodontics but not
   captured verbatim here; a time-critical avulsion pathway would need an **IADT** source. **NO SOURCE
   FOUND (this proposal) — clinician to decide whether to add** (candidate: IADT trauma guidelines).
8. **Systemic-history items relevant to endodontic treatment (diabetes, pregnancy, immunosuppression,
   anticoagulants for surgical endodontics).** Held for clinician addition; bind to `problem_diagnosis` /
   `medication` (§2). **NO SOURCE FOUND (specific thresholds) — clinician must supply** any that should
   carry a flag (cf. the oral-surgery sibling's SDCEP anticoagulant source).
9. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032;
   HB-C12); not fabricated.
10. **Every candidate_flag level and all three RED axes** (route × register × location, invariant 21) —
    deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must supply**,
    with committed `source` snapshots, before anything compiles.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules engine.
- **Inv. 2 / patient-copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/prognosis (symptoms described, never a disease named); marked CANDIDATE.
- **Inv. 7** — the airway/spreading-infection emergency stays in the sibling `base.life_threat` set; this proposal neither adds nor relaxes it, and Q8 is only an intake screen routing into that base mechanism.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 13** — the specialty pack is **L0** (`endodonti.yaml`, `extends: cluster.dental`); an L0 pack resolved for a live session raises. This proposal is review-queue input only, not a promotion.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap; ON_SITE 112-affordance rule noted.
- **Inv. 22** — numerals in drafts are spelled out / avoided; compiler must expand before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S5 for that block but does not itself commit a snapshot, and does not edit the served pack.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
