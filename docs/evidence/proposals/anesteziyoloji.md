# Anesteziyoloji (Anaesthesiology — pre-operative assessment) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Anesteziyoloji (Anaesthesiology, pre-operative assessment)
Purpose: patient-owned, Turkish-first **pre-visit intake** (pre-operative history capture for a
clinician-ready note) — **not** diagnosis, not triage authority, not a fitness-for-surgery decision.
This file is a *proposal for a clinician to sign off*. It assigns **no** authoritative
RED/YELLOW/GREEN level and pins **no** clinical value (no fasting hour, no dose, no cut-off is
asserted as authoritative).

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**,
  written as *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The
  source's own wording is quoted verbatim; no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / WebSearch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any
  derived rule stays `status: draft_needs_source` and does **not** compile into a served pack
  (matches the served `packages/protocols/specialty/anesteziyoloji.yaml` L0 stub, which is itself
  `generated-l0-awaiting-clinical-review`).
- This file does **not** edit `packages/protocols/specialty/anesteziyoloji.yaml` or any served pack.
- **Türkiye-first gap up front:** no versioned Turkish anaesthesia-society (e.g. TARD) or T.C.
  Sağlık Bakanlığı pre-operative guideline was retrieved verbatim. The sources below are ASA / ESAIC
  / BJA Education (international). A Türkiye-first primary source is a **NO SOURCE FOUND** gap (§4).

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — ESAIC perioperative fasting (aspiration risk; fasting intervals)
- **guideline_id (proposed):** `ESAIC-FASTING-2011`
- **Publishing body:** European Society of Anaesthesiology and Intensive Care (ESAIC)
- **Version / year:** 2011
- **URL:** https://esaic.org/guideline/perioperative-fasting-in-adults-and-children/
- **Verbatim (fasting intervals):**
  > "adults and children should be encouraged to drink clear fluids up to 2 h before elective surgery"
  > "Breast milk is safe up to 4 h"
  > "other milks up to 6 h"
  > "Solid food should be prohibited for 6 h before elective surgery in adults and children"
- **Full bibliographic citation:** the journal citation (author, *Eur J Anaesthesiol*, volume, pages)
  was **not retrieved verbatim** — confirm against the primary before sign-off (§4 gap).
- **Corroboration:** an independent web-search summary attributed the **same** intervals (clear
  liquids two hours, breast milk four hours, non-human milk / solids six hours) to the **ASA 2017
  Practice Guidelines for Preoperative Fasting** (*Anesthesiology* 2017), with a 2023 modular update.
  The **ASA primary text was NOT retrieved verbatim** (asahq.org PDF returned as binary; the
  *Anesthesiology* fulltext returned HTTP 402 paywall) → **verbatim gap (§4)**, but two independent
  guideline bodies agreeing on the intervals raises confidence in the *content*.

### S2 — ASA Practice Advisory for Preanesthesia Evaluation (history content)
- **guideline_id (proposed):** `ASA-PREANES-EVAL-2012`
- **Publishing body:** American Society of Anesthesiologists (ASA) Task Force on Preanesthesia
  Evaluation
- **Version / year:** Updated Report, 2012
- **URL:** https://www.guidelinecentral.com/guideline/8964/ (summary) · primary PDF:
  https://www.asahq.org/~/media/sites/asahq/files/public/resources/standards-guidelines/practice-advisory-for-preanesthesia-evaluation.pdf
- **Verbatim (content of the preanesthetic history):**
  > "may include, but should not be limited to, (1) a description of current diagnoses; (2)
  > treatments, including medications and alternative therapies used; and (3) determination of the
  > patient's medical condition(s)."
- **Verbatim (directed examination):**
  > "a minimum, a focused preanesthetic physical examination should include an assessment of the
  > airway, lungs, and heart, with documentation of vital signs."
- **Note (paraphrase, NOT verbatim → gap):** a web-search summary reported that the advisory has
  allergies to drugs/latex documented "to prevent anaphylactic reactions" and current medications
  "including anticoagulants" assessed for interaction/perioperative risk. This is **not a verbatim
  quote** and MUST be confirmed against the primary PDF before it grounds the allergy (Q6) or
  anticoagulant (Q5) items (§4 gap).

### S3 — BJA Education: family history of anaesthetic problems (malignant hyperthermia)
- **guideline_id (proposed):** `BJAED-MH-2021` — **education review, NOT a formal guideline** (weight
  accordingly)
- **Publishing body:** BJA Education (British Journal of Anaesthesia education journal)
- **Version / year:** 2021
- **Citation:** Gupta PK, Bilmen JG, Hopkins PM. *Anaesthetic management of a known or suspected
  malignant hyperthermia susceptible patient.* BJA Educ. 2021;21(6):218–224.
- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC8134759/ · DOI: 10.1016/j.bjae.2021.01.003
- **Verbatim (Key points):**
  > "Enquiry about a family history of problems with anaesthesia is a mandatory part of the
  > anaesthetic history."
- **Verbatim (identification):**
  > "MH-susceptible patients may have had several uneventful anaesthetics, which is why a family
  > history of anaesthetic problems is a mandatory part of the anaesthetic history."
- **Confidence:** MODERATE — a peer-reviewed education review, not a versioned society guideline;
  it grounds *asking the question*, not any triage threshold.
- **Added verbatim (INT-427, retrieved_on: 2026-10-02, same URL):**
  > "Information from patients regarding the suspected episode may be useful, including the timing
  > of the event (during surgery, in the postoperative recovery room, in the surgical ward); the
  > clinical features of the episode; treatment given; whether unplanned treatment in intensive care
  > was needed; and the cause of the event provided at the time."
  > "Details of the family member tested and a family tree will be required in order to ascertain
  > the risk for the patient."

### S4 — TARD Anestezi Uygulama Kılavuzları: Preoperatif Değerlendirme (Türkiye; primary)
- **guideline_id (proposed):** `TARD-PREOP-2015`
- **Publishing body:** Türk Anesteziyoloji ve Reanimasyon Derneği (TARD), Hasta Güvenliği Bilimsel
  Komitesi
- **Version:** "PREOPERATİF DEĞERLENDİRME (2015)" (cover) · **date:** 2015
- **URL:** https://www.tard.org.tr/assets/kilavuz/preoperatifdegerlendirme.pdf
- **retrieved_on:** 2026-10-02 (PDF text-extracted with `pdftotext`; page numbers are PDF page indices)
- **Verbatim:**
  > p. 3: "Önceki anestezi deneyimini ve tıbbi tedavilerini tartışmak"
  > p. 8: "Öyküde, önceki anestezi tecrübeleri, zor hava yolu öyküsünün olup olmadığı sorgulanmalı."
  > p. 8: "Zor hava yolu belirteçlerinden iki veya daha fazlası mevcutsa potansiyel zor hava yolu olarak
  > değerlendirilmeli ve hasta bu konuda bilgilendirilmelidir."
  > p. 9: "OSAS’sı olan hastalar potansiyel zor hava yolu açısından preop değerlendirilmelidirler ve
  > postop ilk 12 saatte yakın solunumsal takip ile izlenmelidir, CPAP/BİBAP uygulanmalıdır."
  > p. 18: "Daha önceki anestezi uygulamasındaki alerji öyküsü"
- **Added verbatim (INT-427 fix round, retrieved_on: 2026-10-02, same URL):**
  > p. 9: "Göğüs radyografisi: rutin olarak önerilmemektedir. Sigara içimi, yakın zamanda üst solunum
  > yolu enfeksiyonu ( ciddi semptomlu hastalarda operasyon 1 ay ertelenmeli), KOAH, kalp hastalığı
  > olanlarda önerilir."
  > p. 10: "Üst solunum yolu enfeksiyonu: Özellikle çocuklarda geçirilmiş veya aktif enfeksiyon varsa
  > elektif cerrahi ertelenir."
- **Note:** the same document is `cluster_surgical.md` SUR-S1 (retrieved 2026-09-26).

### S5 — ASA 2022 Practice Guidelines for Management of the Difficult Airway
- **guideline_id (proposed):** `ASA-DIFFICULT-AIRWAY-2022`
- **Publishing body:** American Society of Anesthesiologists, with ESAIC and nine further societies
  (cover list)
- **Version:** 2022 update · **date:** online first 2021 (PDF footer "Anesthesiology 2021; XXX:00–00");
  DOI 10.1097/ALN.0000000000004002. Print volume and pages not retrieved — confirm against primary.
- **Citation:** Apfelbaum JL, Hagberg CA, Connis RT, et al. *2022 American Society of
  Anesthesiologists Practice Guidelines for Management of the Difficult Airway.* Anesthesiology.
- **URL:** https://www.shanahq.com/main/sites/default/files/shana_library/2022%20ASA%20Practice%20Guidelines%20for%20Management%20of%20the%20Difficult%20Airway.pdf
- **retrieved_on:** 2026-10-02
- **Verbatim (Recommendations for Follow-up Care):**
  > "Inform the patient or a responsible person of the airway difficulty that was encountered to
  > provide the patient (or responsible person) with a role in guiding and facilitating the delivery
  > of future care."
  > "Document the presence and nature of the airway difficulty in the medical record to guide and
  > facilitate the delivery of future care."
- **Added verbatim (INT-427 fix round, retrieved_on: 2026-10-02, same URL; Follow-up Care section):**
  > "Follow-up care includes the topics of: (1) postextubation care (i.e., steroids, racemic
  > epinephrine), (2) postextubation counseling (i.e., informing and advising the patient or responsible
  > individual of the occurrence and potential complications associated with a difficult airway), (3)
  > documentation of difficult airway and management in the medical record and to the patient, and (4)
  > registration with a difficult airway notification service."

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` pins the composition and archetype **roots** only, with **no at-code (`atNNNN`)
leaf nodes** (INT-041 refused to invent leaf codes; INT-032/HB-C12 held that line). So each item
binds to an archetype **root**; the specific leaf path is **deferred** (`openehr_deferred_reason`,
INT-032), never fabricated.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit (upcoming operation) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| 2 | Narrative before anaesthesia (free story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Known chronic conditions / comorbidities | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 4 | Current regular medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 5 | Blood-thinner / anticoagulant use (S2) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 6 | Drug / latex allergy (S2) | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 7 | Prior problem during patient's own anaesthesia (S3) | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 8 | Difficult-airway / intubation-problem history (S2 airway) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Last time ate / drank before operation (S1 fasting) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Candidate triage outcome (max `YELLOW_REVIEW`; authoritative = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 11 | **Family history of severe reaction to anaesthesia** (S3 / MH) | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 11: like the cardiology proposal's family-history row, the committed `.opt` exposes **no
  family-history archetype root**, so capturing a family history of anaesthetic reactions has no
  export target today → **export blocked (INT-041 posture)**; do not invent an at-code path.
  Clinician/architecture decision needed (candidate: INT-032 archetype addition; cross-ref HB-C12).
- `EVALUATION.triage_outcome.v1` and the composition root are LOCAL archetypes nobody has authored
  (HB-C12) — listed for binding completeness only.

---

## 3. Candidate B1 Turkish pre-visit questions (17)

Register: formal **`siz`** throughout; one concern per question (invariant 2: one question per
turn); empathetic; no diagnosis/treatment/prognosis language; capture-only (a fasting *instruction*
would be treatment-adjacent, so Q7–Q8 ask *when the patient last ate or drank*; they do not tell them to fast).
**All marked "CANDIDATE — clinician to approve wording".** Per invariant 22 the protocol compiler
must expand every digit to Turkish orthography before TTS; the drafts below contain **no bare
numerals**.

> Triage note for every alarm-derived item: the level shown is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED/YELLOW must come from `packages/protocols/triage` with a committed `source`
> snapshot and all three RED axes (route × register × location, invariant 21), none supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Findings 19, 20 and 28 apply. Renumbering, old → new — sections outside
§3 still use the old numbers: Q1 → Q1 · Q2 → Q2 · Q3 → Q3 · Q4 removed (base meds; two question marks,
typed verb) · Q5 removed (base `anticoagulant_use`; its candidate_flag is dropped, finding 20) · Q6 →
Q4 · Q7 → Q5 · Q8 → Q6 · Q9 → Q7 (last solid food) + Q8 (last drink) · Q10 → Q9 (candidate_flag
dropped, finding 20).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Hangi ameliyat ya da işlem için anestezi görüşmesine geldiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Free narrative before anaesthesia** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Anestezi hazırlığıyla ilgili bize önceden iletmek istediğiniz bir konu var mı?"
gen: slot=anestezi_oncesi_not
CANDIDATE — clinician to approve wording.

**Q3 — Chronic conditions / comorbidities** · archetype: `EVALUATION.problem_diagnosis.v1` · source:
general intake (comorbidity capture; S2 lists "current diagnoses" as history content)
> "Şeker hastalığı, tansiyon ya da astım gibi süregelen bir rahatsızlığınız var mı?"
gen: slot=suregelen_rahatsizlik; type=boolean
CANDIDATE — clinician to approve wording.

**Q3a — Names of the chronic conditions** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S2
("a description of current diagnoses"), S4 (p. 3)
> "Süregelen rahatsızlıklarınızın adlarını söyleyebilir misiniz?"
gen: slot=suregelen_rahatsizlik_adlari; type=string; ask_if=suregelen_rahatsizlik == true
CANDIDATE — clinician to approve wording.

**Q3b — Diagnosed sleep apnoea** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S4 (p. 9,
"OSAS’sı olan hastalar potansiyel zor hava yolu açısından preop değerlendirilmelidirler")
> "Size uykuda nefes durması, yani uyku apnesi tanısı konuldu mu?"
gen: slot=uyku_apnesi_tanisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q3c — Breathing device at night** · archetype: `OBSERVATION.story.v1` · source: S4 (p. 9,
"CPAP/BİBAP")
> "Uyurken nefes almanıza yardım eden bir cihaz kullanıyor musunuz?"
gen: slot=uyku_solunum_cihazi; type=boolean; ask_if=uyku_apnesi_tanisi == true
CANDIDATE — clinician to approve wording.

**Q3d — Recent cold or febrile illness** · archetype: `OBSERVATION.story.v1` · source: S4 (p. 9,
"yakın zamanda üst solunum yolu enfeksiyonu"; p. 10, "geçirilmiş veya aktif enfeksiyon")
> "Son haftalarda nezle, grip ya da ateşli bir hastalık geçirdiniz mi?"
gen: slot=yakin_solunum_yolu_enfeksiyonu; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Drug / latex allergy** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: S2
(allergies documented — see S2 verbatim + paraphrase caveat)
> "Herhangi bir ilaca ya da lateks eldivene alerjiniz var mı?"
gen: slot=ilac_lateks_alerjisi
CANDIDATE — clinician to approve wording. Latex is specialty-specific, so kept alongside base
`allergies`; free-text slot so the drug is captured.

**Q5 — Prior problem during own anaesthesia** · archetype: `EVALUATION.adverse_reaction_risk.v1` ·
source: S3 (previous anaesthetic experiences are part of the anaesthetic history)
> "Daha önce anestezi aldıysanız, o sırada beklenmedik bir sorun yaşandığı size söylendi mi?"
gen: slot=onceki_anestezi_sorunu; type=boolean
CANDIDATE — clinician to approve wording.

**Q5a — What happened during that anaesthesia** · archetype: `EVALUATION.adverse_reaction_risk.v1` ·
source: S3 ("Information from patients regarding the suspected episode may be useful"), S4 (p. 8,
p. 18)
> "Önceki anestezide yaşanan sorunu size anlatıldığı kadarıyla söyler misiniz?"
gen: slot=onceki_anestezi_sorunu_aciklama; type=string; ask_if=onceki_anestezi_sorunu == true
CANDIDATE — clinician to approve wording.

**Q6 — Difficult-airway / intubation history** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S2 (airway is a required part of the assessment)
> "Önceki bir ameliyatta soluk borunuza tüp yerleştirilirken zorluk yaşandığı size iletildi mi?"
gen: slot=zor_entubasyon_oykusu; type=boolean
CANDIDATE — clinician to approve wording.

**Q6a — Written record of the airway difficulty** · archetype: `OBSERVATION.story.v1` · source: S5
("documentation of difficult airway and management in the medical record and to the patient";
"Inform the patient or a responsible person of the airway difficulty"), S4 (p. 8, "hasta bu konuda
bilgilendirilmelidir")
> "Bu zorlukla ilgili size yazılı bir belge verildi mi?"
gen: slot=zor_entubasyon_belgesi; type=boolean; ask_if=zor_entubasyon_oykusu == true
CANDIDATE — clinician to approve wording.

**Q7 — Fasting: last solid food** · archetype: `OBSERVATION.story.v1` · source: S1 (aspiration
risk; ESAIC fasting intervals)
> "En son ne zaman katı bir şey yediniz?"
gen: slot=son_kati_gida; type=date
CANDIDATE — clinician to approve wording. Capture-only; it does **not** instruct the patient to fast
(PolicyGuard). Finding 19: asked at pre-visit, days before surgery, the answer means nothing, so this
item should be served only in a day-of-surgery context. The pack has no visit-type variable for
`ask_if`, so where it is served is a clinician decision pending. The interval thresholds live in the
rules engine; S1 is ESAIC 2011 (adults), and ESAIC 2022 updated the paediatric clear-fluid interval,
which matters only to the rule.

**Q8 — Fasting: last drink** · archetype: `OBSERVATION.story.v1` · source: S1 (aspiration risk; ESAIC
fasting intervals)
> "En son ne zaman bir şey içtiniz?"
gen: slot=son_sivi; type=date
CANDIDATE — clinician to approve wording. Same day-of-surgery caveat as Q7: clinician decision
pending.

**Q9 — Family history of anaesthesia reactions** · archetype: **no archetype root — export blocked
(INT-041 posture)** · source: S3 ("family history of problems with anaesthesia is a mandatory part
of the anaesthetic history")
> "Ailenizde anestezi aldıktan sonra ciddi bir sorun yaşayan biri olduğunu biliyor musunuz?"
gen: slot=ailede_anestezi_sorunu; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. This is a planning fact, not acuity: no candidate_flag
(finding 20). S3 makes asking about a family history of malignant-hyperthermia-type reactions
mandatory; any threshold or action is the clinician's + rules engine's.

**Q9a — What happened to the relative** · archetype: **no archetype root — export blocked (INT-041
posture)** · source: S3 ("Information from patients regarding the suspected episode may be useful")
> "Ailenizdeki kişinin anesteziyle ilgili yaşadığı sorunu biliyorsanız kısaca anlatır mısınız?"
gen: slot=ailede_anestezi_sorunu_aciklama; type=string; ask_if=ailede_anestezi_sorunu == true; delivery=text_first
CANDIDATE — clinician to approve wording.

**Q9b — Relative tested** · archetype: **no archetype root — export blocked (INT-041 posture)** ·
source: S3 ("Details of the family member tested and a family tree will be required")
> "Ailenizde anestezi sorunu nedeniyle özel bir test yaptıran biri oldu mu?"
gen: slot=ailede_anestezi_testi; type=boolean; ask_if=ailede_anestezi_sorunu == true; delivery=text_first
CANDIDATE — clinician to approve wording.

*(17 candidate questions after the INT-427 wave. Pre-op topics covered: allergies Q4, prior
anaesthesia problems Q5–Q6a + Q9–Q9b, comorbidities Q3–Q3c, recent infection Q3d, fasting Q7–Q8;
medications and anticoagulants are asked by the base layer.)*

---

## 4. Gaps — every place NO SOURCE was found or verbatim was not retrieved (clinician/human must supply)

1. **Türkiye-first primary anaesthesia guideline** — no versioned T.C. Sağlık Bakanlığı or Turkish
   anaesthesia-society (e.g. TARD) pre-operative guideline was retrieved. **NO SOURCE FOUND
   (Türkiye-first) — clinician must supply** the correct primary source, version and date.
   INT-427 (2026-10-02): TARD 2015 *Preoperatif Değerlendirme* retrieved as S4 (history items only;
   no fasting value is taken from it). A current TARD edition was not found.
2. **ASA 2017/2023 Preoperative Fasting primary verbatim** — the asahq.org PDF returned as binary
   and the *Anesthesiology* fulltext returned HTTP 402 (paywall). The intervals are grounded on
   **ESAIC 2011 (S1, verbatim)** plus a web-search summary of ASA; the **ASA primary sentence was
   NOT retrieved verbatim**. **Verbatim gap — clinician to confirm** the ASA text (and the current
   2023 modular-update wording) if ASA is to be the citing source.
3. **ESAIC full bibliographic citation** — the guideline title, body and year were retrieved from
   the ESAIC page, but the journal citation (authors, *Eur J Anaesthesiol*, volume, pages) was
   **not retrieved verbatim**. **Confirm against primary before sign-off.**
4. **ASA preanesthesia allergy / anticoagulant specifics** — the "allergies documented to prevent
   anaphylactic reactions" and "anticoagulants ... perioperative risk" statements grounding Q5/Q6
   came from a **web-search summary, not a verbatim quote**. **Verbatim gap — clinician must confirm**
   the exact ASA advisory sentences.
5. **Any fasting hour / dose / cut-off as an authoritative value** — deliberately **not** pinned
   here (no served value). **Clinician + rules engine must supply**, with a committed `source`.
6. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned. **Clinician + `packages/protocols/triage` rules must supply**.
7. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032); not fabricated. Family history (item 11) has **no archetype root** → export blocked
   (INT-041 posture; cross-ref HB-C12).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending
  rules engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/
  prognosis; the fasting item is capture-only (no instruction); marked CANDIDATE.
- **Inv. 10** — scripted/alarm wording will need verbatim `text_tr`; not finalised here.
- **Inv. 13** — the served `anesteziyoloji.yaml` is an L0 stub (`generated-l0-awaiting-clinical-review`);
  this proposal does not promote it.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — drafts contain no bare numerals; compiler must expand any number before TTS.
- **Clinical content rule** — each alarm rule needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S3
  but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.

---

## 6. INT-427 dynamic wave — change log (2026-10-02)

| item | change | gate | source id |
|---|---|---|---|
| Q3a `suregelen_rahatsizlik_adlari` | added | `suregelen_rahatsizlik == true` | S2, S4 |
| Q3b `uyku_apnesi_tanisi` | added (ungated parent) | — | S4 |
| Q3c `uyku_solunum_cihazi` | added | `uyku_apnesi_tanisi == true` | S4 |
| Q5a `onceki_anestezi_sorunu_aciklama` | added | `onceki_anestezi_sorunu == true` | S3, S4 |
| Q6a `zor_entubasyon_belgesi` | added | `zor_entubasyon_oykusu == true` | S5, S4 |
| Q9 `ailede_anestezi_sorunu` | delivery set to `text_first` | — | S3 |
| Q9a `ailede_anestezi_sorunu_aciklama` | added, `text_first` | `ailede_anestezi_sorunu == true` | S3 |
| Q9b `ailede_anestezi_testi` | added, `text_first` | `ailede_anestezi_sorunu == true` | S3 |
| §1 S3 | verbatim quotes added | — | S3 |
| §1 S4, S5 | sources added | — | S4, S5 |
| §4 gap 1 | updated (S4 retrieved) | — | S4 |
| Q3a `suregelen_rahatsizlik_adlari` | reworded (fix round, V-A-1) | `suregelen_rahatsizlik == true` | S2, S4 |
| Q3d `yakin_solunum_yolu_enfeksiyonu` | added (fix round, V-A-2) | — | S4 |
| Q5a `onceki_anestezi_sorunu_aciklama` | reworded (fix round, V-A-1) | `onceki_anestezi_sorunu == true` | S3, S4 |
| Q6a `zor_entubasyon_belgesi` | source quote added (fix round, V-A-3) | `zor_entubasyon_oykusu == true` | S5 |
| Q9a `ailede_anestezi_sorunu_aciklama` | reworded (fix round, V-A-1) | `ailede_anestezi_sorunu == true` | S3 |
| Q9b `ailede_anestezi_testi` | reworded (fix round, V-A-1) | `ailede_anestezi_sorunu == true` | S3 |
| §1 S4, S5 | verbatim quotes added (fix round) | — | S4, S5 |
