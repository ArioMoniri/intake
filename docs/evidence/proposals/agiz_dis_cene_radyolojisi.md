# Ağız-Diş-Çene Radyolojisi (Oral & Maxillofacial Radiology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher subagent · Date: 2026-09-20 · Specialty: Ağız, Diş ve Çene Radyolojisi
(Oral & Maxillofacial Radiology) · Branch slug: `agiz_dis_cene_radyolojisi`
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom / imaging-context capture for a
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
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / WebSearch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived
  rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- **Türkiye-first gap (up front):** the served pack `packages/protocols/specialty/agiz_dis_cene_radyolojisi.yaml`
  is an **L0 draft** (`extends: cluster.dental`) whose header already states the branch clinician must
  source rules from **T.C. Sağlık Bakanlığı / HSGM** protocols and **Turkish specialty-society**
  guidelines, and that "files/04 and files/09 name no specific guideline title for the 'dental'
  cluster". A dedicated Turkish search on 2026-09-20 returned only private-hospital marketing pages and
  a specialty-society public page — **no versioned Türkiye-first clinical guideline document was
  located** (see §4). The sources below are therefore international, pending Türkiye-first replacement.
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
  independent web-search summary and by Turkish public-education pages ("en fazla üç hafta içinde
  iyileşmeyen bir yara") → higher confidence on the *concept*; primary-text re-verification still
  required for exact recommendation numbers.

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

### S3 — SEDENTEXCT / EC Radiation Protection No 172 (justification for dental/maxillofacial imaging)
- **guideline_id (proposed):** `EC-RP172-SEDENTEXCT`
- **Publishing body:** European Commission, Radiation Protection series No 172 (SEDENTEXCT project +
  European Academy of DentoMaxilloFacial Radiology)
- **Version / year:** 2012 (Definitive Guidelines; supersedes 2009 provisional)
- **Citation:** European Commission. *Radiation Protection N° 172. Cone Beam CT for Dental and
  Maxillofacial Radiology: Evidence Based Guidelines.* Luxembourg: EC, 2012.
- **URL:** http://sedentexct.eu/files/radiation_protection_172.pdf (retrieved as PDF; text read from the
  saved copy)
- **Verbatim (§1.1 Imaging in dentistry and the dental and maxillofacial specialties):**
  > "Radiology is essential to dentists for determining the presence and extent of disease in patients
  > for whom a thorough patient history and examination has been performed."
- **Verbatim (§1.1):**
  > "No exposure to X-rays can be considered completely free of risk, so the use of radiation by
  > dentists is accompanied by a responsibility to ensure appropriate protection."
- **Verbatim (§1.1):**
  > "Unlike most medical imaging, dentists use radiology to a relatively greater extent on children and
  > young adults, so the need for judicious use is paramount."
- **Note:** the numbered "20 basic principles" (justification, incl. the well-known "history and
  clinical examination" / "benefits outweigh the risks" statements) are in §3 of RP172 and were **not**
  quoted verbatim here — confirm on sign-off. §1.1 above already grounds justification.

### S4 — ADA/FDA selection of patients for dental radiographic examinations (justification + pregnancy)
- **guideline_id (proposed):** `ADA-FDA-DENTALRAD-2004` (as summarised in ADA Council on Scientific
  Affairs report)
- **Publishing body:** U.S. FDA + American Dental Association (ADA Council on Scientific Affairs)
- **Version / year:** FDA/ADA selection criteria "Rev. ed. 2004"; summary report JADA 2006
- **Citation:** ADA Council on Scientific Affairs. *The use of dental radiographs: Update and
  recommendations.* JADA. 2006;137:1304–1312.
- **URL:** https://radiation.ncdhhs.gov/xray/documents/dental%20ADArad.pdf (verbatim text read from the
  saved copy) · FDA source page:
  https://www.fda.gov/radiation-emitting-products/medical-x-ray-imaging/selection-patients-dental-radiographic-examinations
- **Verbatim (FDA guidelines, Table 1 footnote):**
  > "The recommendations in this table are subject to clinical judgment and may not apply to every
  > patient. They are to be used by dentists only after reviewing the patient's health history and
  > completing a clinical examination."
- **Verbatim (Table 1 footnote, protection):**
  > "Because every precaution should be taken to minimize radiation exposure, protective thyroid collars
  > and aprons should be used whenever possible. This practice is strongly recommended for children,
  > women of childbearing age and pregnant women."
- **Verbatim (Patient Selection Criteria, pregnancy):**
  > "Dental radiographs may be prescribed for pregnant patients with careful adherence to the FDA
  > selection criteria guidelines."
- **Verbatim (Patient Selection Criteria, prior imaging):**
  > "For new or referred patients, clinicians should obtain recent dental radiographs from the patient's
  > previous dental health care provider."
- **Note:** US source. The Table 1 "positive clinical signs/symptoms" list (indications for a
  radiograph) explicitly names "swelling, evidence of dental/facial trauma … pain and/or dysfunction of
  the temporomandibular joint, facial asymmetry … unexplained bleeding" — grounds Q9/Q11 as legitimate
  imaging-context items, not as triage.
- **Reviewer note (finding 7):** the thyroid-collar sentence above is the 2004 FDA / 2006 ADA
  recommendation. The ADA's 2024 radiation-safety recommendations (JADA 2024) reportedly
  discontinue routine thyroid collars and aprons; verify before any wording relies on it. The
  shielding rationale is dropped from patient text, and pregnancy is asked by base
  `pregnancy_status`.

### S6 — AAOMS Position Paper on Medication-Related Osteonecrosis of the Jaws (antiresorptive + jaw bone)
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

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Same posture as the cardiology proposal: the committed `.opt` is deliberately **shallow** — it pins the
composition and the archetype **roots** only, with **no at-code (`atNNNN`) leaf nodes**. Each item below
binds to an archetype **root**; the specific leaf path is **deferred** (`openehr_deferred_reason`,
INT-032), never fabricated. Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL).

| # | Proposed captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's imaging visit / referral | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| 2 | Narrative of the complaint prompting imaging (story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Complaint duration | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Pregnancy / possibility of pregnancy (radiation protection, S3/S4) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred; **no dedicated pregnancy/reproductive archetype in the committed .opt** — flagged for INT-041/INT-032 review |
| 5 | Recent prior imaging elsewhere (S4 justification) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Non-healing mouth/lip ulcer > 3 weeks (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Lump/swelling in mouth, jaw or neck (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Red / red-white patch in mouth (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Facial/jaw swelling + breathing/swallowing difficulty (S2, airway) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Antiresorptive / bone medication (S6) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 11 | Recent facial/jaw trauma (S4 indication) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 12 | Drug / imaging-contrast allergy or prior reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate triage outcome (rules engine only; max `YELLOW_REVIEW` from LLM) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Note: item 4 (pregnancy) has no dedicated archetype root in the committed template; binding to
`problem_diagnosis` is provisional, pending a clinician/architecture decision (candidate: INT-032). Do not
invent an at-code path.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; **one concern per question** (invariant 2: one question per
turn); empathetic; **no diagnosis/treatment/prognosis** language (PolicyGuard-clean). Numerals are
**spelled out** (invariant 22: the compiler must expand every digit to Turkish orthography before TTS;
after this revision no number word remains in patient text, because the ulcer boundary moved to the rule). **All marked "CANDIDATE — clinician to approve wording".**

> Triage note for every red-flag-derived item: any level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. Authoritative RED/YELLOW must
> come from `packages/protocols/triage` with a committed `source` snapshot and all three RED axes
> (route × register × location, invariant 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Findings 7 and 14 apply. Renumbering, old → new — sections outside §3
still use the old numbers: Q1 → Q1 · Q2 → Q2 · Q3 removed (duplicates the pack's fixed
`sikayet_suresi`; two question marks) · Q4 removed (binds to base `pregnancy_status`; the shielding
rationale is dropped, finding 7) · Q5 → Q3 · Q6 → Q4 (non-healing sore) + Q5 (how long, if Q4) ·
Q7 → Q6 · Q8 → Q7 · Q9 → Q8 (swelling) + Q9 (breathing or swallowing, not gated) · Q10 → Q10 ·
Q11 → Q11 · Q12 removed (binds to base `allergies`; if contrast history matters, the clinician adds
it).

**Q1 — Reason for imaging visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü görüntüleme randevunuzun asıl sebebi nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Region to be imaged** · archetype: `OBSERVATION.story.v1` · source: general intake (S3/S4: imaging follows history)
> "Görüntüleme, ağzınızın ya da çenenizin hangi bölgesi için istendi?"
gen: slot=goruntuleme_bolgesi
CANDIDATE — clinician to approve wording.

**Q3 — Recent prior imaging elsewhere** · archetype: `OBSERVATION.story.v1` · source: S4 ("clinicians
should obtain recent dental radiographs from the patient's previous … provider")
> "Son zamanlarda başka bir yerde ağzınızın, dişlerinizin ya da çenenizin filmi çekildi mi?"
gen: slot=onceki_goruntuleme; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Non-healing mouth/lip sore** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(NICE NG12 1.8.2 — "unexplained ulceration in the oral cavity lasting for more than 3 weeks")
> "Ağzınızda ya da dudağınızda iyileşmeyen bir yara var mı?"
gen: slot=iyilesmeyen_agiz_yarasi; type=boolean
CANDIDATE — clinician to approve wording. The NG12 duration boundary moves to the rule and is no
longer in patient text; Q5 captures the duration. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** when the rule's S1 boundary is met.

**Q5 — How long the sore has been present** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 1.8.2)
> "Bu yara ne zamandır var?"
gen: slot=agiz_yarasi_suresi; type=duration; ask_if=iyilesmeyen_agiz_yarasi == true
CANDIDATE — clinician to approve wording.

**Q6 — Lump/swelling in mouth, jaw or neck** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(NICE NG12 1.8.2/1.8.3 — "lump … in the oral cavity", "unexplained lump in the neck")
> "Ağzınızda, çenenizde ya da boynunuzda elinize gelen bir şişlik ya da sertlik var mı?"
gen: slot=agiz_cene_boyun_sislik; type=boolean
CANDIDATE — clinician to approve wording. "kitle" replaced by "sertlik" (finding 14). Candidate_flag:
**YELLOW_REVIEW (candidate — NOT authoritative)** per S1.

**Q7 — Red / red-white patch in mouth** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE
NG12 1.8.3 — "red or red and white patch … consistent with erythroplakia or erythroleukoplakia")
> "Ağzınızın içinde geçmeyen kırmızı ya da kırmızı-beyaz bir leke fark ettiniz mi?"
gen: slot=kirmizi_beyaz_leke; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** per S1.

**Q8 — Facial/jaw/under-tongue swelling (airway pair, part one)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S2 (Ludwig symptom labels — "Neck swelling"; "Tongue swelling or protrusion …")
> "Yüzünüzde, çenenizde ya da dilinizin altında şişlik var mı?"
gen: slot=yuz_cene_dil_alti_sislik; type=boolean
CANDIDATE — clinician to approve wording. Airway pair in the wave 4–5 endodonti soru_7 form.

**Q9 — Breathing or swallowing difficulty (airway pair, part two; not gated)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S2 (Ludwig — "Breathing difficulty is an emergency situation")
> "Nefes almakta ya da yutkunmakta zorlanıyor musunuz?"
gen: slot=nefes_yutma_zorlugu; type=boolean
CANDIDATE — clinician to approve wording. Deliberately **not** gated on Q8. Candidate_flag:
**candidate acute-airway concern, pending clinician + rules-engine confirmation — NOT
authoritative**; source is patient-education (S2, LOW–MEDIUM), RED script/axes NOT supplied (§4).
Whether the dental cluster carries this screen in every dental pack is still open (finding 26).

**Q10 — Antiresorptive / bone medication** · archetype: `ACTION.medication.v1` · source: S6 (AAOMS MRONJ —
antiresorptive medication + jaw bone; relevant to jaw imaging interpretation)
> "Kemik erimesi ya da başka bir kemik sorunu için hiç ilaç kullandınız mı?"
gen: slot=kemik_ilaci
CANDIDATE — clinician to approve wording. Past use counts for MRONJ; medication history only, no
diagnosis asserted. Kept as a free-text slot so the drug name is captured.

**Q11 — Recent facial/jaw trauma** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 (Table 1
positive clinical sign: "evidence of dental/facial trauma")
> "Son zamanlarda yüzünüze ya da çenenize bir darbe veya yaralanma oldu mu?"
gen: slot=yuz_cene_darbe; type=boolean
CANDIDATE — clinician to approve wording.

*(11 candidate questions after revision: Q4–Q9 source-derived red-flag context; Q3/Q10/Q11 sourced
imaging context; Q1–Q2 general intake. Pregnancy and allergy are asked by the base layer.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first versioned clinical guideline (MoH / HSGM / specialty society).** A dedicated Turkish
   search (2026-09-20) returned only private-hospital marketing pages (Acıbadem, Anadolu, Memorial,
   Medical Park) and a specialty-society **public patient page** (AÇBİD, acbid.org). **NO SOURCE FOUND
   (versioned, authoritative) — clinician must supply** the correct **T.C. Sağlık Bakanlığı / HSGM** or
   Turkish specialty-society document and its version/date, as the served L0 pack header itself requires.
2. **Türkiye emergency affordance ("112" for airway/spreading infection).** Only the LOW–MEDIUM
   patient-education S2 (US "911") was retrieved. **NO SOURCE FOUND (primary/Türkiye) — clinician must
   supply**; and per invariant 21 the RED script + register + location axes are **not** set here.
3. **Airway / spreading-infection red flag as a versioned clinical source.** S2 is an A.D.A.M.
   encyclopedia entry, not a guideline. **NO SOURCE FOUND (clinical guideline) — clinician must supply**
   a primary deep-neck-space-infection / airway source (candidate: AÇBİD / MoH).
4. **CBCT justification "20 basic principles" verbatim (RP172 §3).** §1.1 was captured; the numbered
   justification principles were **not** quoted verbatim. **NO SOURCE FOUND (verbatim, §3) — re-capture
   from the primary PDF on sign-off.**
5. **AAOMS MRONJ primary verbatim (S6).** Publisher returned HTTP 403; only a secondary-source
   paraphrase-quote was captured. **Primary verbatim NOT retrieved — re-capture on sign-off.**
6. **Pregnancy-specific dental-radiograph safety wording beyond S4.** The S4 "may be prescribed … with
   careful adherence" and thyroid-collar sentences were captured; a stronger Türkiye/ICRP-anchored
   statement is **NO SOURCE FOUND — clinician may supply.**
7. **Contrast-material (iodinated) reaction threshold for maxillofacial imaging.** Q12 is general
   allergy intake only. **NO SOURCE FOUND (specific) — clinician must supply** if contrast imaging is in
   scope.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032);
   not fabricated. Pregnancy (item 4) has no dedicated archetype root → flagged for INT-041/INT-032.
9. **Every candidate_flag level and all three RED axes** (route × register × location, invariant 21) —
   deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must supply**,
   with committed `source` snapshots, before anything compiles.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules engine.
- **Inv. 2 / patient-copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 13** — the specialty pack is **L0** (`agiz_dis_cene_radyolojisi.yaml`); an L0 pack resolved for a live session raises. This proposal is review-queue input only, not a promotion.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — numerals in drafts are spelled out; compiler must expand before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S6 for that block but does not itself commit a snapshot, and does not edit the served pack.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
