# Beslenme ve Diyet (Nutrition & Dietetics) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Beslenme ve Diyet (Nutrition & Dietetics)
Taxonomy id: `beslenme_ve_diyet` (branches.yaml — cluster `allied_and_reports`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
dietitian/clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins
**no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage (invariant 1):** RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's own
  urgency wording is quoted verbatim; no level is asserted.
- **Weight-loss caveat.** Unintentional weight loss is the single alarm signal in this branch that a
  guideline treats as urgent. It overlaps the branch-independent gate `rf.weight_loss_unintentional`
  (base.life_threat, `draft_needs_source`). Per invariant 7 this proposal does **not** author, extend
  or relax that rule; it only proposes the intake question that **feeds** it.
- **Verification caveat (applies to every quote in §1):** quotes were captured on 2026-09-20 via
  automated retrieval (WebFetch / pdftotext of the published PDF). Before sign-off each verbatim
  sentence MUST be re-checked against the **primary published text** and committed as a **verbatim
  source snapshot** with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until
  then any derived rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- **Invariant 22 (numbers).** Patient copy below is written in words, not numerals. No numeric
  weight/BMI is collected as free patient text entry on the clinical critical path; anthropometry is a
  **captured measurement**, flagged in §2. Percentage/time thresholds in the quotes are the source's
  own and the compiler must expand any digit to Turkish orthography before TTS.
- This file does **not** edit `packages/protocols/specialty/beslenme_ve_diyet.yaml` (if/when authored)
  or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — ESPEN LLL Programme, Modül 3.1 "Nütrisyonel Tarama ve Değerlendirme" (Turkish, hosted by KEPAN)
- **guideline_id (proposed):** `ESPEN-LLL-3.1-TR-2021`
- **Publishing body:** ESPEN Life Long Learning Programme; Turkish translation hosted by **KEPAN**
  (Klinik Enteral Parenteral Nütrisyon Derneği). Authors: Rémy Meier, Yitshal Berner, Lubos Sobotka.
  Çeviri (translation): Derya Hopancı Bıçaklı. **Copyright © ESPEN LLL Programme 2021.**
- **Type:** educational module (NOT a versioned clinical guideline) — but it is a **Turkish-language**
  restatement of the GLIM diagnostic criteria and ESPEN-recommended screening tools.
- **URL:** https://kepan.org.tr/files/pdf/M3.1%20N%C3%BCtrisyonel%20Tarama%20ve%20De%C4%9Ferlendirme.pdf
- **Verbatim (GLIM fenotipik kriter — kilo kaybı):**
  > "Fenotipik kriterler, istemsiz kilo kaybının (zorunlu) ve düşük BKİ veya düşük yağsız doku kütle
  > indeksinden (FFMI) en az birinin birleşik bulgusunu içerir. Kilo kaybı, süresiz olarak alışılmış
  > ağırlığın >%10'u veya 3 ay boyunca >%5'i olabilir."
- **Verbatim (severity table — Aşama 1 / Orta):**
  > "Son 6 ay içinde %5-10 veya %10-20 6 ay ötesinde"
- **Verbatim (severity table — Aşama 2 / Ciddi):**
  > "Son 6 ay içinde >%10 veya >%20 6 ay ötesinde"
- **Verbatim (tarama araçlarının ele aldığı temel sorular):**
  > "Son zamanlardaki kilo kaybı; Mevcut beden kütle indeksi; Son zamanlardaki besin alımı; Hastalık
  > şiddeti."
- **⚠ internal discrepancy for the clinician:** the body text says weight loss ">%5 over **3 months**"
  while the severity table uses **6-month** windows (matching the primary GLIM). Both are quoted above
  verbatim; the clinician must reconcile which window the served pack uses. Do not silently pick one.

### S2 — GLIM consensus, 5-year update (primary, English)
- **guideline_id (proposed):** `GLIM-2025-UPDATE`
- **Publishing body:** Global Leadership Initiative on Malnutrition (GLIM); endorsed by ESPEN, ASPEN,
  FELANPE, PENSA.
- **Citation:** Jensen GL, Cederholm T, Correia MITD, et al. *GLIM consensus approach to diagnosis of
  malnutrition: A 5-year update.* J Parenter Enteral Nutr (JPEN). 2025;49(4):414–427.
- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC12053077/
- **Verbatim (phenotypic — weight loss):**
  > ">5% within past 6 mo, or >10% beyond 6 mo"
- **Verbatim (phenotypic — low BMI):**
  > "<20 if <70 y old, or <22 if ≥70 y old"
- **Verbatim (etiologic — reduced food intake/assimilation):**
  > "≤50% of ERs for >1 week, or any reduction for >2 weeks, or any chronic GI condition that adversely
  > impacts food assimilation"
- **Note:** malnutrition requires **at least one phenotypic AND one etiologic** criterion. These are
  clinician-side scoring thresholds, NOT patient-facing cut-offs; no patient question here asks the
  patient to compute a percentage.

### S3 — NICE NG12 Suspected cancer: recognition and referral (weight loss / dysphagia as referral triggers)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE).
- **Version / year:** guideline last updated **15 December 2021** in the retrieved PDF (recommendations
  tagged [2015]); a later 2026 update to the non-site-specific weight-loss recommendation exists — see §4.
- **URL:** https://www.nice.org.uk/guidance/ng12 (retrieved via the published PDF mirror
  https://docs.bvsalud.org/biblioref/2022/02/1355289/suspected-cancer-recognition-and-referral-pdf-1837268071621.pdf)
- **Verbatim (Rec 1.2.1 — dysphagia / weight loss, oesophageal):**
  > "Offer urgent, direct access upper gastrointestinal endoscopy (to be done within 2 weeks) to assess
  > for oesophageal cancer in people: with dysphagia or aged 55 and over with weight loss and any of the
  > following: upper abdominal pain, reflux, dyspepsia."
- **Verbatim (Rec 1.2.5 — weight loss, pancreatic):**
  > "Consider an urgent direct access CT scan (to be done within 2 weeks), or an urgent ultrasound scan
  > if CT is not available, to assess for pancreatic cancer in people aged 60 and over with weight loss
  > and any of the following: diarrhoea, back pain, abdominal pain, nausea, vomiting, constipation."
- **Verbatim (Rec 1.13.2 — unexplained weight loss, non-site-specific):**
  > "For people with unexplained weight loss, which is a symptom of several cancers including
  > colorectal, gastro-oesophageal, lung, prostate, pancreatic and urological cancer: carry out an
  > assessment for additional symptoms, signs or findings that may help to clarify which cancer is most
  > likely and offer urgent investigation or a suspected cancer pathway referral (for an appointment
  > within 2 weeks)."
- **Purpose here:** grounds the *unintentional weight loss* and *dysphagia* alarm questions as real
  urgent-referral triggers. It is an **international** source; a Türkiye-first equivalent was not
  located (see §4).

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes**. Each item below binds to an archetype **root**; the
specific leaf path is **deferred** (`openehr_deferred_reason`, INT-032), never fabricated.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| 2 | Nutrition goal / usual eating pattern (narrative) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Unintentional weight loss (S1/S2 phenotypic; alarm) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Reduced appetite / reduced food intake (S2 etiologic) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Swallowing difficulty / dysphagia (S3 Rec 1.2.1; alarm) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | GI symptoms affecting intake — nausea/vomiting/diarrhoea/constipation (S2 assimilation) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Known conditions affecting nutrition (diabetes, renal, GI) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 8 | Current medications / supplements | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 9 | Food allergy / intolerance | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 10 | Dietary restrictions (health/belief/preference) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 12 | **Anthropometry — measured weight / height / BMI** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- **Item 12:** the shallow `.opt` exposes no `OBSERVATION.body_weight` / `.height` / `.body_mass_index`
  archetype root — the same posture as the cardiology family-history gap. Anthropometry therefore has no
  export target today → **export blocked (INT-041 posture)**; do not invent an at-code path. It is also
  the invariant-22 sensitive slot: weight/BMI is a **captured measurement**, never free numeric patient
  text on the critical path (⚠ TTS 10× mis-verbalisation hazard, cf. base.life_threat `weight_kg`).
  Clinician/architecture decision needed (candidate: INT-032 archetype addition).
- PHQ-9/GAD-7 wellbeing roots exist in the `.opt` but are **out of scope** for this branch and not
  drafted here.

---

## 3. Candidate B1 Turkish pre-visit questions (11)

Register: formal **`siz`** throughout; one concern per question (invariant 2); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".**
No numerals appear in patient copy (invariant 22).

> Triage note for the alarm items (Q3, Q5–Q6): the level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. Authoritative RED/YELLOW must
> come from `packages/protocols/triage` (or `base.life_threat` for `rf.weight_loss_unintentional`) with
> a committed `source` snapshot and all three RED axes (route × register × location, invariant 21),
> none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Renumbering, old → new — sections outside §3 still use the old
numbers: Q1–Q4 keep their numbers · Q5 → Q5 (swallowing) + Q6 (food sticking) · Q6 → Q7 · Q7 → Q8 ·
Q8 removed (base meds + `otc_herbal`) · Q9 → Q9 · Q10 → Q10 · Q11 → Q11.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün beslenme ve diyet bölümüne gelme nedeninizi kendi cümlelerinizle kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Nutrition goal (narrative)** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Beslenmenizle ilgili en çok neyi değiştirmek istersiniz?"
gen: slot=beslenme_hedefi
CANDIDATE — clinician to approve wording.

**Q3 — Unintentional weight loss (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (GLIM
"istemsiz kilo kaybı — zorunlu"), S2 (">5% within past 6 mo"), S3 (NG12 unexplained weight loss)
> "Son aylarda, çaba göstermediğiniz hâlde kilo verdiniz mi?"
gen: slot=istemsiz_kilo_kaybi; type=boolean; follow_up=Giysileriniz size eskisinden bol gelmeye başladı mı?
CANDIDATE — clinician to approve wording. **Overlap: base `rf_weight_loss_unintentional` (§4).** The
base slot has no `ask_tr`, so this ask is kept and binds there (the reviewer's direction). Candidate_flag:
**YELLOW_REVIEW (candidate, pending clinician + rules-engine confirmation — NOT authoritative)**. Asked
qualitatively; the S1/S2 percentages are clinician-side scoring, not asked of the patient.

**Q4 — Reduced appetite / intake** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (etiologic
"reduced food intake"), S1 ("son zamanlardaki besin alımı")
> "Son zamanlarda iştahınız azaldı ya da daha az yemeye başladınız mı?"
gen: slot=istah_azalmasi; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Swallowing difficulty (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (NG12 Rec
1.2.1, "with dysphagia … urgent … endoscopy … within 2 weeks")
> "Yemek yerken ya da bir şey içerken yutmakta zorlanıyor musunuz?"
gen: slot=yutma_guclugu; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician
+ rules-engine confirmation — NOT authoritative)** per NG12 dysphagia as a standalone urgent trigger;
feeds a base/GI gate, this pack asserts no level.

**Q6 — Food sticking in the throat (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3
(NG12 Rec 1.2.1)
> "Yediğiniz lokmanın boğazınızda takıldığını hissediyor musunuz?"
gen: slot=lokma_takilmasi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: as Q5.

**Q7 — GI symptoms affecting intake** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("any
chronic GI condition that adversely impacts food assimilation")
> "Son zamanlarda yemenizi etkileyen bulantı, kusma, ishal ya da kabızlık gibi bir sorun yaşıyor musunuz?"
gen: slot=sindirim_sikayeti; type=boolean
CANDIDATE — clinician to approve wording. Note: bundles related GI concerns; the reviewer passes it,
and the clinician may still split it per symptom.

**Q8 — Known conditions affecting nutrition** · archetype: `EVALUATION.problem_diagnosis.v1` · source:
general intake (S2 "inflammation/disease burden" gives clinical relevance)
> "Şeker hastalığı ya da böbrek hastalığı gibi, beslenmenizi etkileyen bir hastalığınız var mı?"
gen: slot=beslenmeyi_etkileyen_hastalik; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Food allergy / intolerance** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: general intake
> "Size dokunan ya da alerji yapan bir yiyecek var mı?"
gen: slot=besin_alerjisi
CANDIDATE — clinician to approve wording. Free-text slot so the food is captured.

**Q10 — Dietary restrictions** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Sağlık, inanç ya da tercih nedeniyle yemediğiniz besinler var mı?"
gen: slot=diyet_kisitlamasi
CANDIDATE — clinician to approve wording. Free-text slot so the foods are captured.

**Q11 — Usual daily eating pattern** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Sıradan bir gününüzde genellikle neler yiyip içtiğinizi kısaca anlatabilir misiniz?"
gen: slot=gunluk_beslenme_duzeni
CANDIDATE — clinician to approve wording.

*(11 candidate questions after revision.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned clinical guideline for adult malnutrition screening** — the only Turkish
   verbatim located (S1) is an **ESPEN LLL 2021 educational module** hosted by KEPAN, not a T.C. Sağlık
   Bakanlığı or KEPAN *versioned clinical guideline*. T.C. Sağlık Bakanlığı's **TÜBER** (Türkiye
   Beslenme Rehberi) is a population dietary-guidance document, not a malnutrition red-flag guideline.
   **NO SOURCE FOUND (versioned Turkish clinical guideline) — clinician must supply** the correct
   Türkiye-first primary source and its version/date.
2. **Weight-loss window reconciliation** — S1 quotes both ">%5 over 3 months" (body text) and 6-month
   windows (table). The clinician must decide the served window; **do not** pick silently. Neither is
   invented here — both are quoted.
3. **NG12 2026 non-site-specific weight-loss update** — a later NICE update to Rec 1.13.2 (age-60/≥5%
   over 6 months framing) is reported but was **not retrieved verbatim** from the primary text.
   **NO SOURCE FOUND (verbatim, current version) — clinician to confirm current wording.**
4. **Dysphagia as a nutrition-branch red flag vs an ENT/GI/neuro red flag** — S3 sources dysphagia as an
   urgent oesophageal-cancer trigger; whether it fires here or is routed to another branch/`base` gate
   is a **clinician/architecture decision — NO SOURCE FOUND in-repo** for the routing.
5. **All candidate_flag levels, and all three RED axes** (route × register × location, invariant 21) —
   deliberately **not** assigned. **Clinician + `packages/protocols/triage` (and `base.life_threat` for
   `rf.weight_loss_unintentional`) must supply**, with committed `source` snapshots, before anything
   compiles.
6. **openEHR anthropometry archetype** (weight/height/BMI) — no root in the shallow `.opt` → export
   blocked (INT-041 posture); not fabricated (item 12).
7. **PHQ-9/GAD-7 disordered-eating / wellbeing overlap** — any eating-disorder screening is consent-gated
   wellbeing content and out of scope; no instrument content proposed (cf. C-SSRS/WHO-5 BLOCKED, HB-L2/HB-L3).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; alarm items (Q3, Q5) are max `YELLOW_REVIEW`,
  pending rules engine.
- **Inv. 2 / patient-copy rules** — questions are one-concern (Q6 flagged for possible split), `siz`,
  ≤ B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — `rf.weight_loss_unintentional` (base.life_threat) is fed, not authored/extended.
- **Inv. 10** — scripted/alarm wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no numerals in patient copy; anthropometry is a captured measurement, not free numeric
  entry; compiler must expand any digit before TTS.
- **Clinical-content rule** — each alarm needs `source: {guideline_id, version, date, url, retrieved_on}`
  against a committed verbatim snapshot; until supplied, rules stay `status: draft_needs_source` and do
  not compile. This proposal supplies candidate sources S1–S3 but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician (dietitian + physician of record) sign-off; NOT served.
