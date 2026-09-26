# Çocuk Göğüs Hastalıkları (Pediatric Pulmonology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Göğüs Hastalıkları (Pediatric Pulmonology)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. This specialty is **pediatric**, so every question
is addressed to the **parent/guardian (proxy)** about *çocuğunuz* (your child). This file is a
*proposal for a clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and
pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence/label + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Pediatric proxy:** all patient-facing text is addressed to the parent/guardian in formal **`siz`**;
  the subject is the child. No question asks the child directly.
- **Acute respiratory emergencies stay in `base.life_threat` (invariant 7).** Severe respiratory
  distress, apnoea and central cyanosis are life-threats owned by the `base.life_threat`
  sibling set (e.g. `rf.dyspnoea_rest`, `rf.anaphylaxis`, `rf.sepsis_like`) — this specialty pack
  neither authors nor relaxes them. The alarm questions below only **feed** those base gates; they do
  **not** create a new RED rule in `specialty.cocuk_gogus_hastaliklari` and do not extend
  `base.life_threat`.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. No level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebSearch/WebFetch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived
  rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_gogus_hastaliklari.yaml` (an L0
  draft) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG143 Fever in under 5s (respiratory distress traffic-light signs)
- **guideline_id (proposed):** `NICE-NG143`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / year:** NG143, published 2019 (an update dated 2021 is referenced — confirm exact
  revision date, see §4 gap)
- **Citation:** NICE. *Fever in under 5s: assessment and initial management.* NICE guideline NG143.
- **URL (primary):** https://www.nice.org.uk/guidance/ng143 — returned **HTTP 403** on fetch;
  verbatim captured from the NCBI Bookshelf mirror table `cha.tab2`:
  https://www.ncbi.nlm.nih.gov/books/NBK552086/table/cha.tab2/
- **Verbatim (Traffic light table — RED / high-risk, Respiratory):**
  > "Grunting"
  > "Tachypnoea: respiratory rate >60 breaths/minute"
  > "Moderate or severe chest indrawing"
- **Verbatim (RED / high-risk, Colour):**
  > "Pale/mottled/ashen/blue"
- **Verbatim (AMBER / intermediate-risk, Respiratory):**
  > "Nasal flaring"
  > "Oxygen saturation ≤95% in air"
- **Applicability note:** NG143 is a **fever** guideline; the respiratory-distress *signs*
  (grunting, fast breathing, chest indrawing, colour change) are the layperson-observable red flags a
  clinician can re-use for a non-febrile pulmonology intake, but that re-use is a clinical judgement
  the signing clinician must confirm. Numbers appear here only inside the quote; per invariant 22 no
  numeral reaches TTS and the drafted questions in §3 carry no digits.

### S2 — AAP 2016 BRUE (apnoea / cyanosis / pallor in infants)
- **guideline_id (proposed):** `AAP-BRUE-2016`
- **Publishing body:** American Academy of Pediatrics (AAP)
- **Version / year:** 2016
- **Citation:** Tieder JS, et al. *Brief Resolved Unexplained Events (Formerly Apparent
  Life-Threatening Events) and Evaluation of Lower-Risk Infants.* Pediatrics. 2016;137(5):e20160590.
- **URL:** https://publications.aap.org/pediatrics/article/137/5/e20160590/52195/
- **Verbatim (BRUE definition — the observed event is ≥1 of):**
  > "cyanosis or pallor"
  > "absent, decreased, or irregular breathing"
  > "marked change in tone (hyper- or hypotonia)"
  > "altered level of responsiveness"
- **Confidence: LOW–MED.** Definition captured via an automated web-search summary of the AAP page
  (the publisher page is fetch-gated); the "<1 year, <1 minute" scope means it is infant-specific.
  Re-verify verbatim from the primary article and confirm applicability beyond infancy before it
  grounds any action script.

### S3 — ERS 2020 / CHEST specific cough pointers (chronic cough in children)
- **guideline_id (proposed):** `ERS-COUGH-2020` (with CHEST/Marchant–Chang pointer set)
- **Publishing body:** European Respiratory Society (ERS); pointer set from CHEST (Marchant et al.
  2006; Chang et al. 2015)
- **Version / year:** ERS 2020
- **Citation:** Morice AH, et al. *ERS guidelines on the diagnosis and treatment of chronic cough in
  adults and children.* Eur Respir J. 2020;55(1):1901136.
- **URL:** https://publications.ersnet.org/content/erj/55/1/1901136 · pointer list captured from the
  open-access review https://pmc.ncbi.nlm.nih.gov/articles/PMC9051232/ (Table 1, citing Marchant 2006
  / Chang 2015)
- **Verbatim (specific cough pointers / red flags):**
  > "Wet cough"
  > "Exertional dyspnea"
  > "Recurrent pneumonia"
  > "Hemoptysis"
  > "Cough associated swallowing" / "Feeding difficulties"
  > "Failure to thrive"
- **Note:** the ERS 2020 statement recommends assessing for "specific cough pointers or 'red flags'";
  the enumerated pointer list above was retrieved verbatim from the review (not the ERS PDF itself).
  Re-verify against the ERS/CHEST primary text before sign-off.

### S4 — Türk Toraks Derneği Çocukluk Çağı Astım Tanı ve Tedavi Rehberi (Turkish source, wheeze/asthma)
- **guideline_id (proposed):** `TTD-COCUK-ASTIM`
- **Publishing body:** Türk Toraks Derneği (Turkish Thoracic Society)
- **Version / year:** El Kitapçığı 2021 (guide first published 2000; updated 2009/2010/2014/2015/2020)
- **URL:** https://toraks.org.tr/site/sf/books/2021/03/8c2f27a3341592993b66b63b86d69ac4b49dda278194835b0bfb8a0d8b617cc6.pdf
- **Verbatim:** **NOT CAPTURED.** Only the search-result listing was retrieved; no verbatim sentence
  was fetched from the PDF. Listed here as the **Türkiye-first candidate** to ground the wheeze/asthma
  symptom-capture questions (cough / *hışıltı* / breathlessness). **Confidence: LOW** until a verbatim
  snapshot is committed — see §4 gap.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes** (INT-032, P3 export tier). Each item below binds to an
archetype **root**; the specific leaf path is **deferred** (`openehr_deferred_reason`), never
fabricated.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern (parent-reported) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of current respiratory complaint | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Cough — presence / duration (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Wet cough / sputum (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Wheeze / *hışıltı* (S4 candidate) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Exertional breathlessness (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Respiratory distress — fast breathing / chest indrawing / grunting (S1) — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Central cyanosis — blue lips/tongue (S1 colour; S2) — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Apnoea / pauses in breathing (S2) — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Recurrent pneumonia / chest infections (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Feeding-related cough / choking (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 12 | Known respiratory diagnoses (asthma, cystic fibrosis, prematurity/BPD) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 13 | Current respiratory medications / inhalers | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 14 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 15 | Depression screening (parent/adolescent, if consented) | `openEHR-EHR-OBSERVATION.phq9.v1` | OBSERVATION | deferred (INT-032) |
| 16 | Anxiety screening (parent/adolescent, if consented) | `openEHR-EHR-OBSERVATION.gad7.v1` | OBSERVATION | deferred (INT-032) |
| 17 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 18 | **Family history of asthma / atopy / allergy** | **no archetype root — export blocked (INT-041 posture)** | — | — |
| 19 | **Environmental tobacco-smoke exposure (passive smoking at home)** | **no archetype root — export blocked (INT-041 posture)** | — | — |

Notes:
- Items 18–19: the committed `.opt` exposes **no family-history and no environmental/social-exposure
  archetype root** (the only CLUSTER named in files/03 §7, `CLUSTER.provenance`, is itself ABSENT from
  the template). Capturing family history of atopy or a home smoke-exposure fact therefore has no
  export target today → **export blocked (INT-041 posture)**; do not invent an at-code path.
  Clinician/architecture decision needed (candidate: INT-032 archetype addition). Both are clinically
  important in pediatric pulmonology, so the gap is real, not cosmetic.
- Items 15–16 (PHQ-9/GAD-7) are the consented wellbeing instruments, included only for completeness of
  binding; their content/cut-offs are out of scope for this respiratory proposal (and are age-gated —
  a young child is not the respondent).

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian** about the child
(*çocuğunuz*); one concern per question (invariant 2: one question per turn); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".**
Per invariant 22, none of the drafts below contains a numeral; the protocol compiler must still expand
any future digit to Turkish orthography before TTS.

> Triage note for every alarm-derived item (Q7–Q12): the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED for acute respiratory distress / apnoea / cyanosis stays in `base.life_threat`
> with a committed `source` snapshot and all three RED axes (route × register × location, invariant
> 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Renumbering, old → new — sections outside §3 still use the old
numbers: Q1 → Q1 · Q2 → Q2 (cough) + Q3 (how long, if Q2) · Q3 → Q4 (if Q2) · Q4 → Q5 (held) · Q5 →
Q6 · Q6 → Q7 (fast breathing) + Q8 (chest indrawing) + Q9 (grunting) · Q7 → Q10 · Q8 → Q11 · Q9 →
Q12 · Q10 → Q13 · Q11 → Q14 · Q12 → Q15.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün hekime getiren en önemli konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Cough (presence)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("wet cough" / chronic cough)
> "Çocuğunuzun öksürüğü var mı?"
gen: slot=oksuruk; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q3–Q4.

**Q3 — Cough (duration)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (chronic cough)
> "Bu öksürük ne zamandır sürüyor?"
gen: slot=oksuruk_suresi; type=duration; ask_if=oksuruk == true
CANDIDATE — clinician to approve wording.

**Q4 — Wet cough** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("Wet cough")
> "Çocuğunuzun öksürüğü balgamlı gibi mi geliyor?"
gen: slot=balgamli_oksuruk; type=boolean; ask_if=oksuruk == true
CANDIDATE — clinician to approve wording. "sümük" is gone: it confounds with nasal discharge.

**Q5 — Wheeze** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 candidate (verbatim not yet captured — see §4)
> "Çocuğunuz nefes alıp verirken hırıltı ya da ıslık gibi bir ses çıkarıyor mu?"
gen: hold=S4 verbatim not captured; text passes, re-source before lifting
CANDIDATE — clinician to approve wording. HOLD until S4 is captured verbatim; the reviewer passes the
text.

**Q6 — Exertional breathlessness** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("Exertional dyspnea")
> "Çocuğunuz oyun oynarken ya da koşarken yaşıtlarına göre daha çabuk yoruluyor veya nefesi
> daralıyor mu?"
gen: slot=eforla_nefes_darligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Fast breathing** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (tachypnoea) — **feeds `base.life_threat`**
> "Çocuğunuz şu sıralarda her zamankinden hızlı nefes alıyor mu?"
gen: slot=hizli_nefes; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician
+ rules-engine confirmation — NOT authoritative)**; the authoritative RED is owned by
`base.life_threat` (invariant 7), not this pack.

**Q8 — Chest indrawing** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("chest indrawing") — **feeds `base.life_threat`**
> "Nefes alırken çocuğunuzun kaburgalarının arası içeri çekiliyor mu?"
gen: slot=gogus_ice_cekilmesi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: as Q7.

**Q9 — Grunting** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Grunting") — **feeds `base.life_threat`**
> "Çocuğunuz nefes verirken inler gibi bir ses çıkarıyor mu?"
gen: slot=inleme; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: as Q7.

**Q10 — Central cyanosis** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Pale/mottled/ashen/blue"); S2 ("cyanosis or pallor") — **feeds `base.life_threat`**
> "Çocuğunuzun dudaklarında ya da dilinde morarma fark ettiniz mi?"
gen: slot=morarma; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; RED owned by `base.life_threat`.

**Q11 — Apnoea / pauses in breathing** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("absent, decreased, or irregular breathing") — **feeds `base.life_threat`**
> "Çocuğunuzun nefesinin bir an durduğu ya da kesildiği oldu mu?"
gen: slot=nefes_durmasi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; RED owned by `base.life_threat`. S2 (BRUE) is defined for infants, so the reviewer
wants an infant-age `ask_if`; the age cut-off is a clinical value, so the gate is a clinician decision
pending and no age is proposed here.

**Q12 — Recurrent chest infections** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("Recurrent pneumonia")
> "Çocuğunuz sık sık zatürre ya da göğüs enfeksiyonu geçirdi mi?"
gen: slot=sik_gogus_enfeksiyonu; type=boolean
CANDIDATE — clinician to approve wording.

**Q13 — Feeding-related cough / choking** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("Cough associated swallowing" / "Feeding difficulties")
> "Çocuğunuz beslenirken öksürüyor ya da tıkanıyor mu?"
gen: slot=beslenirken_oksurme; type=boolean
CANDIDATE — clinician to approve wording.

**Q14 — Known respiratory diagnoses** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general intake (history)
> "Çocuğunuza daha önce astım ya da kistik fibrozis gibi bir solunum tanısı kondu mu?"
gen: slot=solunum_tanisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q15 — Current respiratory medications** · archetype: `ACTION.medication.v1` · source: general intake (history)
> "Çocuğunuz solunumu için düzenli bir ilaç ya da nefes açıcı kullanıyor mu?"
gen: slot=solunum_ilaci
CANDIDATE — clinician to approve wording. Respiratory-specific, so kept alongside base meds;
free-text slot so the medicine is captured.

*(15 candidate items after revision: fourteen emitted, Q5 held. Family history of atopy and home smoke
exposure — openEHR items 18–19 — are clinically relevant but deliberately NOT drafted as questions
here because they have no export target; export blocked, INT-041 posture, pending an archetype
decision.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned pediatric pulmonology guideline (verbatim)** — the Türk Toraks Derneği
   childhood-asthma guide (S4) was **identified but not verbatim-retrieved**; only the search listing
   was seen. **NO SOURCE FOUND (verbatim) — clinician must supply** the exact Turkish wording, version
   and date (ideally a **T.C. Sağlık Bakanlığı** primary document where one exists).
2. **NICE NG143 exact revision date** — published 2019 with a 2021 update referenced; the precise
   `version/date` must be confirmed against the primary before it grounds any rule. **Confirm current
   version.**
3. **Applicability of NG143 respiratory signs to a non-febrile pulmonology intake** — NG143 is a fever
   guideline; whether its grunting/indrawing/tachypnoea red flags transfer unchanged to a chronic
   respiratory intake is a **clinical judgement — clinician must confirm.**
4. **AAP BRUE age scope** — S2 is defined for infants under one year; the age boundary for an
   apnoea/pauses question in older children is **NO SOURCE FOUND — clinician must supply.**
5. **Wheeze / preschool-wheeze urgency threshold** — no verbatim red-flag threshold for wheeze alone
   was retrieved. **NO SOURCE FOUND (verbatim) — clinician must supply** (candidate: ERS preschool
   wheeze task force; GINA; TTD).
6. **Sleep-disordered breathing / snoring (OSA) screening** — not sourced here; if the branch wants an
   OSA screen, the instrument and its Turkish wording are **NO SOURCE FOUND — clinician must supply.**
7. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned. The acute respiratory life-threats remain owned by
   `base.life_threat` (invariant 7); `packages/protocols/triage` + clinician must supply, with
   committed `source` snapshots, before anything compiles.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032);
   not fabricated. Family history of atopy (item 18) and environmental smoke exposure (item 19) have
   **no archetype root** → export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules
  engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, addressed to the
  parent/guardian, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — acute respiratory emergencies (distress / apnoea / cyanosis) stay in `base.life_threat`;
  this pack only feeds those gates and neither adds to nor relaxes them.
- **Inv. 10** — scripted/alarm wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — the drafted questions contain no numerals; source quotes with numbers are quotes only,
  and the compiler must expand any digit before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S4 for
  that block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
