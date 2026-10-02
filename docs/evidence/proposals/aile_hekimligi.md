# Aile Hekimliği (Family Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Aile Hekimliği (Family Medicine)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign
off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

Branch: `aile_hekimligi` (`taxonomy/branches.yaml` — cluster `medical`, all visit types). Family
medicine is the branch where patient-initiated pre-visit intake fits **most** naturally: an
undifferentiated primary-care contact where the job is to capture the presenting concern and screen
for the small number of alarm ("red-flag") symptoms that a clinician would want surfaced early.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**,
  and is written as *"candidate, pending clinician + rules-engine confirmation — NOT
  authoritative"*. The guideline's own urgency wording is quoted verbatim; no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebSearch/WebFetch). The NICE NG12 recommendation sentences in S1 were
  returned by the fetch **with `...` ellipses**, meaning the small extraction model may have elided
  intervening text; before sign-off each verbatim sentence MUST be re-checked against the **primary
  published NG12 text** and committed as a **verbatim source snapshot** with a full
  `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule
  stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/**` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG12 Suspected cancer: recognition and referral (primary-care alarm symptoms)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), United Kingdom
- **Version / year:** NG12 (first published 2015; the retrieved NCBI full-text render carried a
  "January 2026" line and a search result referenced a 15 April 2026 weight-loss update — the exact
  current version/date MUST be reconciled before sign-off; see §4 gap).
- **Citation:** NICE. *Suspected cancer: recognition and referral.* NICE guideline [NG12].
- **URLs:** https://www.nice.org.uk/guidance/ng12 · full text https://www.ncbi.nlm.nih.gov/books/NBK555330/
- **Verbatim (captured with ellipses — re-verify against primary text):**
  > Rec 1.13.2: "For people with unexplained weight loss...offer urgent investigation or a suspected
  > cancer pathway referral."
  > Rec 1.1.1: "Refer people using a suspected cancer pathway referral for lung cancer if
  > they...are aged 40 and over with unexplained haemoptysis."
  > Rec 1.2.1: "Refer people using a suspected cancer pathway referral for oesophageal cancer if
  > they have dysphagia"
  > Rec 1.3.1: "Offer quantitative faecal immunochemical testing (FIT)...to guide referral for
  > suspected colorectal cancer in adults aged 50 and over with any of the following unexplained
  > symptoms: rectal bleeding"
  > Rec 1.4.1: "Refer people using a suspected cancer pathway referral for breast cancer if
  > they...are aged 30 and over and have an unexplained breast lump with or without pain"
  > Rec 1.5.10: "Refer women using a suspected cancer pathway referral for endometrial cancer if
  > they are aged 55 and over with post-menopausal bleeding"
- **Superseded (2026-10-02):** the Rec 1.13.2 and Rec 1.5.10 quotes above are not in the current
  NG12 text. Current wording: S3 rec 1.13.2 ("[2026]") and S3 rec 1.5.12 ("[2015, amended 2026]").
- **Note:** the age thresholds (40/50/30/55) live **inside the English source quotes**; they are not
  spoken to the patient. The Turkish questions in §3 capture the *symptom*, never a numeric
  threshold — the referral age/threshold is a clinician + rules-engine decision, not a patient-facing
  utterance (invariant 22).

### S2 — WHO Sepsis (fever safety-netting context only, NOT a patient-facing red-flag list)
- **Note:** for a **fever** intake item (§3 Q3) I looked for a patient-facing "seek urgent care if
  your fever is X" threshold. NICE NG51 (suspected sepsis) is built around **clinician**
  risk-stratification (high / moderate-to-high / low risk) and safety-netting, and returned **no**
  patient-facing numeric red-flag sentence. So the fever question is captured as **general symptom
  intake with no threshold asserted**; the sepsis/fever escalation threshold is **NO SOURCE FOUND
  (patient-facing) — clinician + rules engine must supply** (see §4).

### S3 — NICE NG12 Suspected cancer: recognition and referral (current text, INT-427)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), United Kingdom
- **Version / date:** NG12 · "Published: 23 June 2015" · "Last updated: 15 April 2026" (page header)
- **URL:** https://www.nice.org.uk/guidance/ng12/chapter/Recommendations-organised-by-site-of-cancer
- **retrieved_on:** 2026-10-02
- **Verbatim:**
  > Rec 1.13.2: "For people aged 60 and over with unexplained weight loss (greater than 5% mean weight
  > loss within a 6-month period)" … "[2026]"
  > Rec 1.4.2: "Consider a suspected cancer pathway referral for breast cancer in people: with skin
  > changes that suggest breast cancer, or aged 30 and over with an unexplained lump in the axilla."
  > Rec 1.11.4: "Consider an urgent, direct access ultrasound scan to assess for soft tissue sarcoma in
  > adults with an unexplained lump that is increasing in size."
  > Rec 1.5.12: "Refer women, and trans men and non-binary people with female reproductive organs
  > using a suspected cancer pathway referral for endometrial cancer if they are aged 55 and over with
  > unexplained post-menopausal bleeding that cannot be attributed to hormone replacement therapy
  > (HRT)." "[2015, amended 2026]"
  > Rec 1.1.1: "Refer people using a suspected cancer pathway referral for lung cancer if they: have
  > chest X‑ray findings that suggest lung cancer, or are aged 40 and over with unexplained
  > haemoptysis."
  > Rec 1.2.1: "Refer people using a suspected cancer pathway referral for oesophageal cancer if they:
  > have dysphagia" … "[2015, amended 2025]"
  > Rec 1.3.1: "Offer quantitative faecal immunochemical testing (FIT) using HM‑JACKarc or OC‑Sensor
  > to guide referral for suspected colorectal cancer in adults:" … "aged 50 and over with any of the
  > following unexplained symptoms: rectal bleeding"

### S4 — NHS, "High temperature (fever) in adults" (patient page, NOT a guideline)
- **guideline_id (proposed):** `NHS-FEVER-ADULTS`
- **Publishing body:** NHS (England), nhs.uk
- **Version / date:** "Page last reviewed: 24 May 2023" ("Next review due: 24 May 2026"; overdue at
  retrieval)
- **URL:** https://www.nhs.uk/symptoms/fever-in-adults/
- **retrieved_on:** 2026-10-02
- **Verbatim:**
  > "a thermometer says your temperature is 38C or above"
  > "You do not need to take your temperature using a thermometer, but you can if you have one."
  > "Ask for an urgent GP appointment or get help from NHS 111 if you have:" · "a high temperature and
  > you've been treating it at home but it's not getting better or is getting worse"

### S5 — Aile Hekimliği Uygulama Yönetmeliği (Türkiye)
- **guideline_id (proposed):** `RG-28539-AILE-HEKIMLIGI-UYGULAMA-YONETMELIGI`
- **Publishing body:** T.C. Sağlık Bakanlığı · Resmî Gazete
- **Version / date:** Resmî Gazete 25 Ocak 2013, Sayı 28539 (original publication text). Consolidated
  text (mevzuat.gov.tr, MevzuatNo 17051) carries amendments through "RG-9/4/2026-33219"; Madde 4(3)(f)
  is unchanged there.
- **URL:** https://www.resmigazete.gov.tr/eskiler/2013/01/20130125-26.htm · consolidated
  https://www.mevzuat.gov.tr/MevzuatMetin/yonetmelik/7.5.17051.pdf
- **retrieved_on:** 2026-10-02
- **Verbatim (Madde 4(3)(f)):**
  > "Kayıtlı kişilerin yaş, cinsiyet ve hastalık gruplarına yönelik izlem ve taramaları (kanser,
  > kronik hastalıklar, gebe, lohusa, yenidoğan, bebek, çocuk sağlığı, adölesan (ergen), erişkin, yaşlı
  > sağlığı ve benzeri) yapmak."

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes**. Per its own header, a slot whose leaf path is not
yet authored carries **`openehr_deferred_reason`** (INT-032, P3 export tier) — it is **not**
invented. So each item below binds to an archetype **root**; the specific leaf path is **deferred**,
never fabricated.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the present complaint (onset / course) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Fever (general symptom capture; no threshold) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Unexplained weight loss (S1 alarm) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Haemoptysis — blood in sputum (S1 alarm) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Dysphagia — difficulty swallowing (S1 alarm) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Rectal bleeding (S1 alarm) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | New unexplained lump (S1: breast lump; broader lumps NO SOURCE) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Post-menopausal bleeding (S1 alarm; women) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Known chronic diagnoses (e.g. diabetes, hypertension) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current regular medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug / substance allergy | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 13 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| §3 Q2a | Fever measured with a thermometer | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| §3 Q2b | Fever still present | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| §3 Q3a | Duration of weight loss | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| §3 Q7a | Site of the new lump | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| §3 Q7b | Lump increasing in size | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| §3 Q9a | Name of the long-term condition | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |

Notes:
- All leaf paths are **deferred** (`openehr_deferred_reason`, INT-032); none is fabricated.
- Item 8: NG12's captured verbatim is specifically an *unexplained breast lump* (S1 Rec 1.4.1). A
  broader "any new unexplained lump" question is reasonable primary-care intake, but the referral
  threshold for non-breast lumps was **not** captured verbatim → tagged **general intake** with the
  breast-lump source noted; broader-lump thresholds are **NO SOURCE FOUND** (§4).

---

## 3. Candidate B1 Turkish pre-visit questions (15)

Register: formal **`siz`** throughout; one concern per question (invariant 2: one question per
turn); empathetic; no diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to
approve wording".** No numeral appears in any question text; per invariant 22 the protocol compiler
must in any case expand every digit to Turkish orthography before TTS.

> Triage note for every alarm-derived item: no level is assigned here. Any level is a
> **`candidate_flag` (max `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT
> authoritative**. The authoritative RED/YELLOW must come from `packages/protocols/triage` with a
> committed `source` snapshot and all three RED axes (route × register × location, invariant 21),
> none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Findings 14 and 17 apply. Renumbering, old → new — sections outside §3
still use the old numbers: Q1 → Q1 · Q2 removed (base `onset_date` + `trajectory`) · Q3 → Q2 · Q4 →
Q3 · Q5 → Q4 · Q6 → Q5 · Q7 → Q6 · Q8 → Q7 · Q9 → Q8 · Q10 → Q9 · Q11 removed (base meds) · Q12
removed (base `allergies`).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake (no clinical threshold)
> "Bugünkü görüşmede sizi en çok rahatsız eden konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Fever** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake (no clinical threshold; sepsis/fever escalation threshold NO SOURCE FOUND, §4)
> "Son günlerde ateşiniz oldu mu?"
gen: slot=son_gunlerde_ates; type=boolean
CANDIDATE — clinician to approve wording. No urgency threshold asserted.

**Q2a — Fever measured with a thermometer** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 ("a thermometer says your temperature is 38C or above"; "You do not need to take your temperature using a thermometer, but you can if you have one.")
> "Ateşinizi termometreyle ölçtünüz mü?"
gen: slot=ates_olcumu; type=boolean; ask_if=son_gunlerde_ates == true
CANDIDATE — clinician to approve wording.

**Q2b — Fever still present** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 ("a high temperature and you've been treating it at home but it's not getting better or is getting worse")
> "Ateşiniz hâlâ devam ediyor mu?"
gen: slot=ates_devam_ediyor; type=boolean; ask_if=son_gunlerde_ates == true
CANDIDATE — clinician to approve wording. No urgency threshold asserted.

**Q3 — Unexplained weight loss** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (NG12 rec 1.13.2, "For people aged 60 and over with unexplained weight loss (greater than 5% mean weight loss within a 6-month period)")
> "Son aylarda, beslenmenizde bir değişiklik olmadığı hâlde, istemeden kilo verdiniz mi?"
gen: slot=istemsiz_kilo_kaybi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** if unexplained weight loss is reported,
per S1.

**Q3a — Duration of weight loss** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (NG12 rec 1.13.2, "unexplained weight loss (greater than 5% mean weight loss within a 6-month period)")
> "Kilo kaybınız ne zamandır sürüyor?"
gen: slot=kilo_kaybi_suresi; type=duration; ask_if=istemsiz_kilo_kaybi == true; follow_up=Hafta ya da ay olarak yaklaşık söyleyebilir misiniz?
CANDIDATE — clinician to approve wording. No amount or period threshold in patient copy. Same text
and slot as hematoloji Q11a (one audio clip).

**Q4 — Haemoptysis (blood when coughing)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 Rec 1.1.1, "unexplained haemoptysis")
> "Öksürürken balgamınızda ya da tükürüğünüzde kan fark ettiniz mi?"
gen: slot=balgamda_kan; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)**, per S1.

**Q5 — Dysphagia (difficulty swallowing)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 Rec 1.2.1, "dysphagia")
> "Yemek ya da içecekleri yutarken takılma veya zorlanma yaşıyor musunuz?"
gen: slot=yutma_guclugu; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)**, per S1.

**Q6 — Rectal bleeding** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 Rec 1.3.1, "rectal bleeding")
> "Dışkınızda ya da tuvalete gittikten sonra kan fark ettiniz mi?"
gen: slot=diskida_kan; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)**, per S1.

**Q7 — New unexplained lump** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 Rec 1.4.1, "unexplained breast lump" — re-cite pending, see note); broader-lump threshold NO SOURCE FOUND (§4)
> "Vücudunuzda nedenini bilmediğiniz yeni bir şişlik ya da sertlik fark ettiniz mi?"
gen: slot=yeni_sislik_sertlik; type=boolean
CANDIDATE — clinician to approve wording. "kitle" replaced by "sertlik" (finding 14). Finding 17: a
whole-body lump is better anchored on the NG12 soft-tissue lump recommendation (unexplained lump
increasing in size) than on the breast recommendation; verify and re-cite before sign-off.

**Q7a — Site of the new lump** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (NG12 rec 1.4.2, "an unexplained lump in the axilla"; rec 1.11.4, "an unexplained lump that is increasing in size")
> "Bu şişliği vücudunuzun neresinde fark ettiniz?"
gen: slot=sislik_yeri; type=string; ask_if=yeni_sislik_sertlik == true
CANDIDATE — clinician to approve wording.

**Q7b — Lump increasing in size** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (NG12 rec 1.11.4, "an unexplained lump that is increasing in size")
> "Fark ettiğinizden bu yana bu şişlik büyüdü mü?"
gen: slot=sislik_buyumesi; type=boolean; ask_if=yeni_sislik_sertlik == true
CANDIDATE — clinician to approve wording. Same text and slot as hematoloji Q9b (one audio clip).

**Q8 — Post-menopausal bleeding** (women; conditional) · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (NG12 rec 1.5.12, "unexplained post-menopausal bleeding that cannot be attributed to hormone replacement therapy (HRT)")
> "Adet dönemleriniz tamamen sona erdikten sonra herhangi bir kanamanız oldu mu?"
gen: slot=menopoz_sonrasi_kanama; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. The reviewer wants an `ask_if` on sex; the gate is a
clinician decision pending, so no gate expression is written here. Candidate_flag: **YELLOW_REVIEW
(candidate, pending clinician + rules-engine confirmation — NOT authoritative)**, per S1.

**Q9 — Known chronic diagnoses** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S5 (Madde 4(3)(f), "kronik hastalıklar"); general intake (no clinical threshold)
> "Şimdiye kadar söylediklerinizin dışında süregelen bir rahatsızlığınız var mı?"
gen: slot=suregelen_hastalik; type=boolean
CANDIDATE — clinician to approve wording.

**Q9a — Name of the long-term condition** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S5 (Madde 4(3)(f), "hastalık gruplarına yönelik izlem ve taramaları (kanser, kronik hastalıklar, …)")
> "Bu rahatsızlığın adını söyleyebilir misiniz?"
gen: slot=suregelen_hastalik_adi; type=string; ask_if=suregelen_hastalik == true
CANDIDATE — clinician to approve wording.

*(15 candidate questions after the INT-427 wave: 6 alarm-symptom items sourced to S1 (Q3–Q8), 3
general-intake items (Q1, Q2, Q9), 6 gated detail items (Q2a, Q2b, Q3a, Q7a, Q7b, Q9a; §6).)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **NG12 current version/date** — closed 2026-10-02: S3 records the nice.org.uk page header,
   "Published: 23 June 2015" · "Last updated: 15 April 2026".
2. **NG12 verbatim with ellipses** — every S1 sentence was returned **with `...`**; the contiguous
   primary-text wording MUST be re-captured and committed as a verbatim snapshot. **Re-verification
   required.**
3. **Fever / sepsis patient-facing escalation threshold** — NICE NG51 is clinician
   risk-stratification + safety-netting, not a patient-facing "seek urgent care if…" list. **NO
   SOURCE FOUND (patient-facing) — clinician + rules engine must supply.**
4. **Broader "new lump" referral threshold** (non-breast: neck, skin/melanoma, testicular, etc.) —
   only breast lump was captured verbatim (S1 Rec 1.4.1). **NO SOURCE FOUND (verbatim, non-breast) —
   clinician must supply.**
5. **Türkiye-first primary source** — a **T.C. Sağlık Bakanlığı / TAHUD (Türkiye Aile Hekimleri
   Uzmanlık Derneği)** versioned primary-care alarm-symptom guideline was **not** retrieved
   verbatim; only public-education pages (HSGM "kanser belirtileri") and undated draft "Birinci
   Basamağa Yönelik Tanı ve Tedavi Rehberleri" mirrors were located. **NO SOURCE FOUND (versioned,
   verbatim) — clinician must supply** the correct Türkiye-first primary source and its
   version/date.
6. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant
   21) — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must
   supply**, with committed `source` snapshots, before anything compiles.
7. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending
  rules engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, no
  diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/alarm wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no numeral appears in any question text; age thresholds live only inside English
  source quotes, never spoken.
- **Clinical content rule** — each alarm needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate source S1 for
  that block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.

---

## 6. INT-427 dynamic wave — change log (2026-10-02)

| item | change | gate | source id |
|---|---|---|---|
| Q2a `ates_olcumu` | added | `son_gunlerde_ates == true` | S4 |
| Q2b `ates_devam_ediyor` | added | `son_gunlerde_ates == true` | S4 |
| Q3a `kilo_kaybi_suresi` | added (duration; follow-up) | `istemsiz_kilo_kaybi == true` | S3 |
| Q7a `sislik_yeri` | added (string) | `yeni_sislik_sertlik == true` | S3 |
| Q7b `sislik_buyumesi` | added | `yeni_sislik_sertlik == true` | S3 |
| Q9 `suregelen_hastalik` | reworded: "Şimdiye kadar söylediklerinizin dışında süregelen bir rahatsızlığınız var mı?" (fix round, V-AH-3; first pass: "hastalığınız" → "rahatsızlığınız"); source line cites S5 | — (ungated) | S5 |
| Q9a `suregelen_hastalik_adi` | added (string) | `suregelen_hastalik == true` | S5 |
| Q3 `istemsiz_kilo_kaybi` | source line re-cited to S3 rec 1.13.2 (fix round, V-AH-2); text unchanged | — (ungated) | S3 |
| Q8 `menopoz_sonrasi_kanama` | delivery set to `text_first` (V-AH-1); source line re-cited to S3 rec 1.5.12 (V-AH-2); text unchanged | — (ungated) | S3 |
| §1 S1 | rec 1.13.2 and rec 1.5.10 quotes marked superseded (V-AH-2) | — | S3 |
| §1 S3 | recs 1.5.12, 1.1.1, 1.2.1, 1.3.1 added (V-AH-2; red-flag rows A1–A4) | — | S3 |
| §1 S4, S5 | version lines updated (V-AH-4) | — | S4, S5 |
| §4 gap 1 | closed with S3 header dates (V-AH-2) | — | S3 |
