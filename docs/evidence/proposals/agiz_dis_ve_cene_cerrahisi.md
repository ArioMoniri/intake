# Ağız, Diş ve Çene Cerrahisi (Oral & Maxillofacial Surgery) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher subagent · Date: 2026-09-20 · Specialty: Ağız, Diş ve Çene Cerrahisi
(Oral & Maxillofacial Surgery) · Branch slug: `agiz_dis_ve_cene_cerrahisi`
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom / history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's own
  urgency wording is quoted verbatim; **no level is asserted**.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / WebSearch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot** with
  a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule
  stays `status: draft_needs_source` and does **not** compile into a served pack.
- **Türkiye-first gap (up front):** the served pack `packages/protocols/specialty/agiz_dis_ve_cene_cerrahisi.yaml`
  is an **L0 draft** (`extends: cluster.dental`) whose header already states the branch clinician must
  source rules from **T.C. Sağlık Bakanlığı / HSGM** protocols and **Turkish specialty-society**
  guidelines, and that no specific 'dental' cluster guideline title is named in files/04 or files/09. A
  dedicated Turkish search on 2026-09-20 returned only private-hospital marketing pages and one
  specialty-society **public** page (AÇBİD — Türk Ağız, Diş ve Çene Cerrahisi Derneği) — **no versioned
  Türkiye-first clinical guideline document was located** (see §4). The sources below are therefore
  international, pending Türkiye-first replacement.
- This file does **not** edit the served L0 pack, `previsit_intake.v1.opt`, or any other served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG12 Suspected cancer: recognition and referral (oral cancer red flags)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), England
- **Version / year:** NG12, published June 2015 (updated — confirm current update date on sign-off)
- **Citation:** NICE. *Suspected cancer: recognition and referral.* NICE guideline NG12.
- **URL:** https://www.nice.org.uk/guidance/ng12 · retrieved verbatim via NCBI Bookshelf mirror
  https://www.ncbi.nlm.nih.gov/books/NBK555330/
- **Verbatim (rec. 1.8.2):**
  > "Consider a suspected cancer pathway referral for oral cancer in people with either: unexplained
  > ulceration in the oral cavity lasting for more than 3 weeks or a persistent and unexplained lump in
  > the neck."
- **Verbatim (rec. 1.8.3):**
  > "Consider an urgent referral (for an appointment within 2 weeks) for assessment for possible oral
  > cancer by a dentist in people who have either: a lump on the lip or in the oral cavity or a red or
  > red and white patch in the oral cavity consistent with erythroplakia or erythroleukoplakia."
- **Corroboration:** the ">3 weeks unexplained ulceration" threshold was returned identically by an
  independent web-search summary and by Turkish public-education pages → higher confidence on the
  *concept*; primary-text re-verification still required for exact recommendation numbers.

### S2 — Ludwig's angina / spreading odontogenic infection (airway emergency)
- **guideline_id (proposed):** `ADAM-LUDWIG` — **patient-education encyclopedia, NOT a clinical
  guideline** (A.D.A.M. medical encyclopedia, hosted by UF Health)
- **Publishing body:** A.D.A.M., Inc. / VeriMed Healthcare Network (reviewer: Ashutosh Kacker, MD,
  FACS, Weill Cornell), last reviewed 2025-01-29
- **URL:** https://ufhealth.org/conditions-and-treatments/ludwig-angina (A.D.A.M. text; also MedlinePlus
  ency/article/001047)
- **Verbatim (When to Contact a Medical Professional):**
  > "Breathing difficulty is an emergency situation. Go to the emergency room or contact your local
  > emergency number (such as 911) right away."
- **Verbatim (symptoms captured):** "Breathing difficulty" · "Difficulty swallowing" · "Drooling" ·
  "Tongue swelling or protrusion of the tongue out of the mouth" · "Neck swelling"
- **Confidence: LOW–MEDIUM.** A patient-education encyclopedia, not a versioned clinical/airway
  guideline. Must be re-verified and, ideally, replaced by a primary source (e.g. a deep-neck-space
  infection / airway guideline, or a **T.C. Sağlık Bakanlığı / AÇBİD** document) before it grounds any
  RED action script. The `112` affordance for Türkiye is **not** sourced here (see §4).

### S5 — SDCEP Management of Dental Patients Taking Anticoagulants or Antiplatelet Drugs (bleeding risk)
- **guideline_id (proposed):** `SDCEP-ANTICOAG-2022`
- **Publishing body:** Scottish Dental Clinical Effectiveness Programme (SDCEP), NHS Education for
  Scotland
- **Version / year:** 2nd edition; Quick Reference Guide March 2022
- **Citation:** SDCEP. *Management of Dental Patients Taking Anticoagulants or Antiplatelet Drugs.* 2nd
  ed. Quick Reference Guide, March 2022.
- **URL:** https://www.sdcep.org.uk/media/imrflqss/sdcep-anticoagulants-quick-reference-guide-2nd-edition.pdf
  (retrieved as PDF; text read from the saved copy)
- **Verbatim (Environmental Considerations — confirm history in advance):**
  > "Confirm the details of the patient's medical history in advance (e.g. by phone) to check for any
  > changes that could impact treatment and require postponement."
- **Verbatim (Antiplatelet dual therapy — bleeding expectation):**
  > "Expect prolonged bleeding; limit initial treatment area and consider staging extensive or complex
  > procedures; strongly consider suturing and packing."
- **Verbatim (General Advice — do not interrupt therapy for):**
  > "Do not interrupt anticoagulant or antiplatelet therapy for: patients with prosthetic metal heart
  > valves or coronary stents; patients who have had a pulmonary embolism or deep vein thrombosis in the
  > last three months; patients on anticoagulant therapy for cardioversion."
- **Note:** UK source. Grounds a **pre-visit medication/bleeding-history** question (Q9/Q10). The
  clinical decisions themselves (INR, dose timing) are clinician-facing and out of scope for patient
  intake.

### S6 — AAOMS Position Paper on Medication-Related Osteonecrosis of the Jaws (antiresorptive + extraction)
- **guideline_id (proposed):** `AAOMS-MRONJ-2022`
- **Publishing body:** American Association of Oral and Maxillofacial Surgeons (AAOMS)
- **Version / year:** 2022 Update
- **Citation:** Ruggiero SL, et al. *AAOMS' Position Paper on Medication-Related Osteonecrosis of the
  Jaws—2022 Update.* J Oral Maxillofac Surg. 2022;80(5):920–943. (PubMed 35300956)
- **URL (primary):** https://www.joms.org/article/S0278-2391(22)00148-3/fulltext ·
  https://aaoms.org/wp-content/uploads/2024/03/mronj_position_paper.pdf **(both returned HTTP 403 on
  retrieval — primary verbatim NOT captured)**
- **Verbatim (secondary source, quoting AAOMS):** via PMC9317393 (Kim et al.),
  https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9317393/ —
  > "The American Association of Oral and Maxillofacial Surgery (AAOMS) position paper states that tooth
  > extraction is a common predisposing event."
- **Confidence: MEDIUM.** The antiresorptive/tooth-extraction risk relationship is well established and
  was corroborated by an independent web-search summary, but the **primary AAOMS sentence was not
  directly retrieved** (publisher 403). Re-capture from the primary PDF on sign-off. Included here only
  to justify a **medication-history** question, never a triage level.

### S4 — ADA/FDA selection of patients for dental radiographic examinations (medical-history posture)
- **guideline_id (proposed):** `ADA-FDA-DENTALRAD-2004`
- **Publishing body:** U.S. FDA + American Dental Association (ADA Council on Scientific Affairs)
- **Citation:** ADA Council on Scientific Affairs. *The use of dental radiographs: Update and
  recommendations.* JADA. 2006;137:1304–1312.
- **URL:** https://radiation.ncdhhs.gov/xray/documents/dental%20ADArad.pdf (verbatim text read from the
  saved copy)
- **Verbatim (Table 1 footnote — used only after history + clinical exam):**
  > "They are to be used by dentists only after reviewing the patient's health history and completing a
  > clinical examination."
- **Note:** cited only to ground the general posture that intake **history precedes** any imaging /
  procedure decision (supports Q1–Q2). Not a surgery-specific red flag.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Same posture as the cardiology proposal: the committed `.opt` is deliberately **shallow** — composition
and archetype **roots** only, **no at-code (`atNNNN`) leaf nodes**. Each item binds to an archetype
**root**; the leaf path is **deferred** (`openehr_deferred_reason`, INT-032), never fabricated.
Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL).

| # | Proposed captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's surgical visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| 2 | Narrative of the complaint (story of present complaint) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Facial/mouth-floor swelling + breathing/swallowing difficulty (S2, airway) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Fever with facial/jaw swelling (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Limited mouth opening / trismus (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Non-healing mouth/lip ulcer > 3 weeks (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Lump in mouth, lip or neck (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Red / red-white patch in mouth (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Blood-thinning (anticoagulant/antiplatelet) medication (S5) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 10 | History of prolonged bleeding after extraction/injury (S5) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Antiresorptive / antiangiogenic bone medication (S6) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug / local-anaesthetic / latex allergy | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate triage outcome (rules engine only; max `YELLOW_REVIEW` from LLM) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Note: known prior diagnoses (e.g. diabetes affecting healing) and pregnancy would bind to
`EVALUATION.problem_diagnosis.v1`; they are held for clinician addition (§4) rather than fabricated as
leaf paths here.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; **one concern per question** (invariant 2: one question per
turn); empathetic; **no diagnosis/treatment/prognosis** language (PolicyGuard-clean). Numerals are
**spelled out** (invariant 22: the compiler must expand every digit before TTS; after this revision no number word remains in patient text, because the ulcer boundary moved to the rule). **All marked "CANDIDATE — clinician to approve wording".**

> Triage note for every red-flag-derived item: any level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. Authoritative RED/YELLOW must
> come from `packages/protocols/triage` with a committed `source` snapshot and all three RED axes
> (route × register × location, invariant 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Findings 13, 14 and 26 apply. Renumbering, old → new — sections outside
§3 still use the old numbers: Q1 → Q1 · Q2 removed (base `trajectory`; the reviewer's C2 fallback
only if that base slot is not served) · Q3 → Q2 (swelling) + Q3 (breathing or swallowing, not gated)
· Q4 → Q4 (fever, if Q2) · Q5 → Q5 · Q6 → Q6 (non-healing sore) + Q7 (how long, if Q6) · Q7 → Q8 ·
Q8 → Q9 · Q9 removed (base `anticoagulant_use`) · Q10 → Q10 · Q11 → Q11 · Q12 → Q12.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
(S4: history precedes decisions)
> "Bugünkü randevunuzda sizi hekime getiren asıl şikâyetiniz nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Facial/jaw/under-tongue swelling (airway pair, part one)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S2 (Ludwig symptom labels — "Neck swelling"; "Tongue swelling or protrusion …")
> "Yüzünüzde, çenenizde ya da dilinizin altında şişlik var mı?"
gen: slot=yuz_cene_sisligi; type=boolean
CANDIDATE — clinician to approve wording. Airway pair in the wave 4–5 endodonti soru_7 form; the
jargon "ağız tabanı" is gone. Gate for Q4.

**Q3 — Breathing or swallowing difficulty (airway pair, part two; not gated)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S2 (Ludwig — "Breathing difficulty is an emergency situation";
"Difficulty swallowing")
> "Nefes almakta ya da yutkunmakta zorlanıyor musunuz?"
gen: slot=nefes_yutkunma_guclugu; type=boolean
CANDIDATE — clinician to approve wording. Deliberately **not** gated on Q2. Candidate_flag:
**candidate acute-airway concern, pending clinician + rules-engine confirmation — NOT
authoritative**; source is patient-education (S2, LOW–MEDIUM); RED script/axes NOT supplied (§4).
This is the key spreading-infection/airway screen.

**Q4 — Fever with the swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (Ludwig —
"dental pain, fever, trismus … swelling")
> "Bu şişlikle birlikte ateşiniz de var mı?"
gen: slot=sislik_ile_ates; type=boolean; ask_if=yuz_cene_sisligi == true
CANDIDATE — clinician to approve wording. Candidate_flag: **candidate — NOT authoritative** (systemic
sign of spreading infection); source S2 (LOW–MEDIUM).

**Q5 — Limited mouth opening / trismus** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (Ludwig —
"trismus")
> "Son zamanlarda ağzınızı açmakta zorlanıyor musunuz?"
gen: slot=agiz_acma_guclugu; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **candidate — NOT authoritative**; source S2.

**Q6 — Non-healing mouth/lip sore** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(NICE NG12 1.8.2 — "unexplained ulceration … lasting for more than 3 weeks")
> "Ağzınızda ya da dudağınızda iyileşmeyen bir yara var mı?"
gen: slot=iyilesmeyen_agiz_yarasi; type=boolean
CANDIDATE — clinician to approve wording. The NG12 duration boundary moves to the rule and is no
longer in patient text; Q7 captures the duration. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** when the rule's S1 boundary is met.

**Q7 — How long the sore has been present** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 1.8.2)
> "Bu yara ne zamandır var?"
gen: slot=agiz_yarasi_suresi; type=duration; ask_if=iyilesmeyen_agiz_yarasi == true
CANDIDATE — clinician to approve wording.

**Q8 — Lump in mouth, lip or neck** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG12
1.8.2/1.8.3 — "a lump on the lip or in the oral cavity", "unexplained lump in the neck")
> "Ağzınızda, dudağınızda ya da boynunuzda geçmeyen bir şişlik ya da sertlik var mı?"
gen: slot=agiz_dudak_boyun_sislik; type=boolean
CANDIDATE — clinician to approve wording. "kitle" replaced by "sertlik" (finding 14). Candidate_flag:
**YELLOW_REVIEW (candidate — NOT authoritative)** per S1.

**Q9 — Red / red-white patch in mouth** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE
NG12 1.8.3 — "red or red and white patch … consistent with erythroplakia or erythroleukoplakia")
> "Ağzınızın içinde geçmeyen kırmızı ya da kırmızı-beyaz bir leke fark ettiniz mi?"
gen: slot=kirmizi_beyaz_leke; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** per S1.

**Q10 — History of prolonged bleeding** · archetype: `OBSERVATION.symptom_sign.v1` · source: S5 (SDCEP —
bleeding-risk assessment; "Expect prolonged bleeding")
> "Daha önce bir diş çekimi ya da yaralanma sonrasında olağandan uzun süre kanamanız oldu mu?"
gen: slot=islem_sonrasi_uzun_kanama; type=boolean
CANDIDATE — clinician to approve wording. Anticoagulant use itself is asked by base
`anticoagulant_use`; patients must **not** be told to stop such medication here (S5).

**Q11a — Antiresorptive / bone medication** · archetype: `ACTION.medication.v1` · source: S6 (AAOMS MRONJ —
"tooth extraction is a common predisposing event"; antiresorptive medication)
> "Kemik erimesi ya da başka bir kemik sorunu için hiç ilaç kullandınız mı?"
gen: slot=kemik_ilaci; type=boolean
CANDIDATE — clinician to approve wording. Past use counts (was twenty-four words with two particles).
Medication history only. Yes/no gate for Q11b, the same `kemik_ilaci` boolean the dental cluster and
periodontoloji and protetik declare (verification wave 8 §A, cluster-wave-b §F).

**Q11b — Name of that medicine** · archetype: `ACTION.medication.v1` · source: S6 (AAOMS MRONJ)
> "Hatırlıyorsanız bu ilacın adını söyleyebilir misiniz?"
gen: slot=kemik_ilaci_adi; type=string; ask_if=kemik_ilaci == true
CANDIDATE — clinician to approve wording. Split from Q11: a boolean slot cannot store the medicine's
name, so it has its own string slot. Text and pair as periodontoloji and protetik Q11a/Q11b
(verification wave 8 §C).

**Q12 — Drug / local-anaesthetic / latex allergy** · archetype: `EVALUATION.adverse_reaction_risk.v1` ·
source: general intake
> "Herhangi bir ilaca, diş uyuşturma iğnesine ya da lateks eldivene alerjiniz var mı?"
gen: slot=ilac_lokal_anestezik_lateks_alerjisi
CANDIDATE — clinician to approve wording. "uyuşturucu iğnesi" read as "narcotic" and is replaced
(finding 13). Specialty-specific allergy, so kept alongside base `allergies`.

*(13 candidate questions after revision, Q11 split into Q11a and Q11b: Q2–Q9 source-derived red-flag
context; Q10–Q11 sourced bleeding/medication history; Q1/Q12 general intake.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first versioned clinical guideline (MoH / HSGM / specialty society).** A dedicated Turkish
   search (2026-09-20) returned only private-hospital marketing pages and a specialty-society **public
   patient page** (AÇBİD, acbid.org — Türk Ağız, Diş ve Çene Cerrahisi Derneği). **NO SOURCE FOUND
   (versioned, authoritative) — clinician must supply** the correct **T.C. Sağlık Bakanlığı / HSGM** or
   Turkish specialty-society document and its version/date, as the served L0 pack header itself requires.
2. **Türkiye emergency affordance ("112" for airway/spreading infection).** Only the LOW–MEDIUM
   patient-education S2 (US "911") was retrieved. **NO SOURCE FOUND (primary/Türkiye) — clinician must
   supply**; and per invariant 21 the RED script + register + location axes are **not** set here (note:
   under ON_SITE the 112 affordance must be absent, not de-emphasised).
3. **Airway / spreading-odontogenic-infection red flag as a versioned clinical source.** S2 is an
   A.D.A.M. encyclopedia entry, not a guideline. **NO SOURCE FOUND (clinical guideline) — clinician must
   supply** a primary deep-neck-space-infection / Ludwig's angina source (candidate: AÇBİD / MoH).
4. **Post-extraction bleeding "when to seek help" threshold for patients.** S5 grounds clinician-facing
   bleeding management, not a patient-facing post-op escalation threshold. **NO SOURCE FOUND (patient
   escalation) — clinician must supply.**
5. **AAOMS MRONJ primary verbatim (S6).** Publisher returned HTTP 403; only a secondary-source
   paraphrase-quote was captured. **Primary verbatim NOT retrieved — re-capture on sign-off.**
6. **Facial-trauma red flags (fracture / significant injury) as a sourced set.** Not captured verbatim.
   **NO SOURCE FOUND — clinician must supply** (candidate: a maxillofacial-trauma guideline).
7. **Systemic-history items relevant to surgery (diabetes, pregnancy, immunosuppression).** Held for
   clinician addition; bind to `problem_diagnosis` (§2). **NO SOURCE FOUND (specific thresholds) —
   clinician must supply** any that should carry a flag.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032);
   not fabricated.
9. **Every candidate_flag level and all three RED axes** (route × register × location, invariant 21) —
   deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must supply**,
   with committed `source` snapshots, before anything compiles.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules engine.
- **Inv. 2 / patient-copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 13** — the specialty pack is **L0** (`agiz_dis_ve_cene_cerrahisi.yaml`); an L0 pack resolved for a live session raises. This proposal is review-queue input only, not a promotion.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap; ON_SITE 112 affordance rule noted.
- **Inv. 22** — numerals in drafts are spelled out; compiler must expand before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1, S2, S4, S5, S6 for that block but does not itself commit a snapshot, and does not edit the served pack.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
