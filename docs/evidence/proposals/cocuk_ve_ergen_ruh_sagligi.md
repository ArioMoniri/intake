# Çocuk ve Ergen Ruh Sağlığı (Child & Adolescent Psychiatry) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk ve Ergen Ruh Sağlığı (Child &
Adolescent Psychiatry)
Purpose: patient-owned, Turkish-first **pre-visit intake** (supportive context capture for a
clinician-ready note) — **not** diagnosis, not triage authority, **not** a screening instrument.
This is a **paediatric** specialty: the pre-visit questions are addressed to the **parent /
guardian (proxy)**. This file is a *proposal for a clinician to sign off*. It assigns **no**
authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- **Paediatric proxy intake.** The pre-visit questions below are written for the **parent or
  guardian** answering on the child's behalf, in warm, person-first, B1 Turkish. Whether and how the
  adolescent's **own** voice is captured (and any confidentiality boundary) is a clinical/consent
  decision, left open — see §4 gap 5.
- **Supportive, non-stigmatizing only.** Wording never labels the child (no "depresyon", "hasta",
  "hiperaktif" as a description of the child), never blames the parent, and never asserts diagnosis,
  treatment or prognosis (invariant 2). It captures what the family has noticed and what support they
  are seeking.
- **No crisis / self-harm / suicide screening here — by design.** Any consent-independent crisis or
  self-harm path is **out of scope for this pre-visit intake** and belongs to the base life-threat
  layer (`base.life_threat`, invariant 7 — a sibling set nothing may extend) and the crisis-lexicon
  work (**HB-C17**, still open). C-SSRS is licence-**BLOCKED** (**HB-L2**; and its only Turkish
  validation is adolescents 12–18 only) and WHO-5 is licence-**BLOCKED** (**HB-L3**). This file
  introduces **no** RED, **no** crisis trigger, and **no** self-harm/suicide item. If a family
  volunteers crisis content, that is handled by the signed life-threat layer, not by anything
  proposed here.
- **Not an instrument.** NICE NG134 (S1), NICE NG87 (S2) and the AACAP anxiety CPG (S3) are cited
  **as sources for question topics only**. Nothing is embedded, scored, or reproduced as an
  instrument item; an instrument whose licence is not `GO` does not compile (clinical-content rule).
  PHQ-2/GAD-2 are **not** described as "Turkish-validated" (they have no Turkish validation);
  paediatric PHQ-9/GAD-7 applicability and cut-offs are age- and language-dependent and not asserted
  here (cf. HB-L24). The candidate questions are original B1 Turkish wording, not instrument items.
- **Triage:** per invariant 1, only `packages/protocols/triage` rules can produce RED/YELLOW.
  Nothing here is flagged; every item is ordinary supportive intake. **No `candidate_flag` is
  raised** in this specialty proposal.
- **Source-tier caveat (Türkiye-first).** The L0 pack header for `cocuk_ve_ergen_ruh_sagligi`
  (files/09 §2) names **T.C. Sağlık Bakanlığı klinik protokolleri / HSGM rehberleri** and **ilgili
  uzmanlık derneği kılavuzları** (Türkiye Çocuk ve Genç Psikiyatrisi Derneği — ÇOGEPDER) as the
  intended sources, and records that files/04 and files/09 name **no specific guideline title** for
  the `mental_health` cluster — selection *awaits the branch clinician*. No versioned Türkiye-first
  clinical assessment guideline was retrieved verbatim on 2026-09-20 (only ÇOGEPDER society/journal
  landing pages — see §4). The sources below are therefore **real, retrieved NICE/AACAP guideline
  text used as interim topic grounding** and must be **reconciled against, or replaced by, the
  Türkiye-first primary** before sign-off.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval. The NICE quotes were retrieved via an **NCBI Bookshelf mirror** because
  `nice.org.uk` returned HTTP 403 to automated fetch; the recommendation *numbers* reported by the
  mirror (e.g. some 1.1.x numbers may reflect the legacy CG28 layout) MUST be reconciled against the
  current primary NICE text and committed as a **verbatim source snapshot** before any `source:`
  block is finalised. Until then any derived content stays `status: draft_needs_source` and does not
  compile.
- **No accuracy claims** (invariant 20): no sensitivity/specificity/AUROC/cut-off figure is
  reproduced here.
- This file does **not** edit `packages/protocols/specialty/cocuk_ve_ergen_ruh_sagligi.yaml` (an L0
  draft that raises if served — `maturity: L0`, `status: generated-l0-awaiting-clinical-review`) or
  any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG134: Depression in children and young people (identification & assessment domains)
- **guideline_id (proposed):** `NICE-NG134-DEPRESSION-CYP`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** NG134, published 25 June 2019 (replaces CG28)
- **URL (primary, returned HTTP 403 on fetch):** https://www.nice.org.uk/guidance/ng134/chapter/recommendations ·
  retrieved via NCBI Bookshelf mirror: https://www.ncbi.nlm.nih.gov/books/NBK547251/
- **Verbatim (assessment context — reported as rec 1.1.11; reconcile numbering):**
  > "When assessing a child or young person with depression, healthcare professionals should
  > routinely consider, and record in the patient's notes, potential comorbidities, and the social,
  > educational and family context for the patient and family members."
- **Verbatim (family involvement — reported as rec 1.1.1):**
  > "Children and young people and their families need good information, given as part of a
  > collaborative and supportive relationship with healthcare professionals, and need to be able to
  > give fully informed consent."
- **Verbatim (recognition/identification — reported as rec 1.4.1):**
  > "Children and young people of 11 years or older referred to CAMHS without a diagnosis of
  > depression should be routinely screened with a self-report questionnaire for depression as part
  > of a general assessment procedure."
- **Confidence: MEDIUM.** Real NICE guideline retrieved via a mirror; the **recommendation numbers**
  (some 1.1.x may be legacy CG28 layout) and exact current wording MUST be re-verified against the
  primary NICE text (§4 gap 1). Used to justify *which domains* a proxy intake may cover (mood in its
  social/educational/family context; family involvement) — **no self-harm/risk item is drawn from
  this source.**

### S2 — NICE NG87: Attention deficit hyperactivity disorder — diagnosis and management (recognition)
- **guideline_id (proposed):** `NICE-NG87-ADHD`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** NG87, published March 2018 (with later updates)
- **URL (primary, returned HTTP 403 on fetch):** https://www.nice.org.uk/guidance/ng87 ·
  retrieved via NCBI Bookshelf mirror: https://www.ncbi.nlm.nih.gov/books/NBK493361/
- **Verbatim (pervasiveness — reported as rec 1.3.3):**
  > "be pervasive, occurring in 2 or more important settings including social, familial, educational
  > and/or occupational settings."
- **Verbatim (impairment — reported as rec 1.3.3):**
  > "cause at least moderate psychological, social and/or educational or occupational impairment based
  > on interview and/or direct observation in multiple settings"
- **Verbatim (developmental history — reported as rec 1.3.1):**
  > "a full developmental and psychiatric history"
- **Verbatim (early life — Context section):**
  > "Symptoms should be evident in early life, if only in retrospect; for ICD-10, by age 7 years and
  > for DSM-5, by age 12 years."
- **Verbatim (coexisting conditions — Context section):**
  > "in children include disorders of mood, conduct, learning, motor control, language and
  > communication, and anxiety disorders"
- **Confidence: MEDIUM.** Real NICE guideline retrieved via a mirror; recommendation numbers/wording
  to be re-verified against the primary NICE text. Used to justify *asking about attention/activity
  across more than one setting (home and school), developmental history, functioning/impairment, and
  common coexisting mood/anxiety concerns* — none scored, none diagnosed.

### S3 — AACAP Clinical Practice Guideline: Anxiety disorders in children & adolescents (topics only)
- **guideline_id (proposed):** `AACAP-ANXIETY-CPG-2020`
- **Publishing body:** American Academy of Child and Adolescent Psychiatry (AACAP)
- **Version / year:** 2020 (Walter HJ et al., J Am Acad Child Adolesc Psychiatry, October 2020)
- **URL (AACAP PDF; non-extractable binary on fetch):**
  https://www.aacap.org/App_Themes/AACAP/docs/practice_parameters/JAACAP_Anxiety_2007.pdf · mirror
  (also non-extractable): https://njaap.org/wp-content/uploads/2023/06/Walter-et-al.-ClinicalPracticeGuidelinefortheAssessmentand-TreatmentofChildrenandAdolescentsWithAnxiety-Disorders.pdf
- **Retrieved (topic domains — from the search-result summary, NOT a page-verbatim string):**
  the AACAP anxiety CPG emphasises early assessment, **gathering information from multiple sources**,
  assessing **comorbid disorders**, and evaluating **severity and functional impairment**; if
  screening indicates significant anxiety, a formal evaluation determines the disorder, severity and
  functional impairment.
- **Confidence: LOW (topic-only).** The primary/mirror PDFs returned as **non-extractable binary**,
  so the above is a **search-result summary, not a clean page-verbatim string** (§4 gap 2). Used only
  to justify *asking a parent about the child's worries/fears and their effect on school and social
  life* — the instrument items and any reported psychometrics are **not** reproduced (invariant 20).

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots-only binding, leaf `atNNNN` paths **deferred** (`openehr_deferred_reason`, INT-032 / HB-C12);
nothing fabricated. Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).
All items capture the **parent/guardian's proxy report**; **none is a red-flag** and none raises a
`candidate_flag`.

| # | Proposed captured item (proxy report) | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for the visit / support the family is seeking | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | What the parent has noticed, in their own words (story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Change in mood / loss of interest, as the parent observes it (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Worries / fears / anxiety the parent has noticed (S3 topic) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Attention / activity level, seen in more than one setting (S2 pervasiveness) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Sleep changes | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Effect on school / daily functioning (S2 impairment; S1 educational context) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Changes in relationships with friends / family (S1 social & family context) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 9 | When first noticed / course (S2 developmental history, "evident in early life") | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Prior support/care received or known conditions (S2 coexisting conditions) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current medications the child takes | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug allergy / serious adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate triage outcome (**none raised in this specialty**; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 13 | **Family mental-health history** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- No `symptom_sign` item here is a red-flag; they capture supportive proxy context, not urgency.
- Item 13: the committed `.opt` exposes no family-history archetype root (`CLUSTER.provenance` is the
  only CLUSTER named in files/03 §7 and is itself ABSENT from the template), so family mental-health
  history has **no export target today → export blocked (INT-041 posture)**; do not invent an at-code
  path. Clinician/architecture decision needed (candidate: INT-032 archetype addition).
- **PHQ-9 / GAD-7 not bound as active screens.** Paediatric applicability is age- and
  language-dependent (cf. HB-L24); C-SSRS and WHO-5 are licence-BLOCKED (HB-L2 / HB-L3). No
  paediatric wellbeing instrument is asserted or scored here.
- The adolescent's **own-report** items are **not** modelled here — capturing the young person's own
  voice, and any confidentiality boundary, is deferred to a clinical/consent decision (§4 gap 5).

---

## 3. Candidate B1 Turkish pre-visit questions (addressed to the parent / guardian)

Register: formal **`siz`** throughout, addressed to the **parent/guardian** about *çocuğunuz*; one
concern per question (invariant 2); warm, supportive, **non-stigmatizing**, no
diagnosis/treatment/prognosis language, no alarming wording, no blame. **All marked "CANDIDATE —
clinician to approve wording".** No bare digits (invariant 22). **No crisis/self-harm/suicide item
appears — by design (see §0).**

**Q1 — Reason for visit / support wanted** · archetype: `EVALUATION.reason_for_encounter.v1` · source:
general intake
> "Bugün çocuğunuz için sizi buraya getiren konu nedir? Hangi konuda destek almak istersiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Parent's own-words narrative** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Fark ettiklerinizi kendi sözlerinizle, rahat hissettiğiniz kadar anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q3 — Change in mood / interest** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (mood in its
social/educational/family context)
> "Son zamanlarda çocuğunuzun keyfinde ya da eskiden sevdiği şeylere ilgisinde bir değişiklik fark
> ettiniz mi?"
CANDIDATE — clinician to approve wording. Non-stigmatizing; describes an observation, not a diagnosis.

**Q4 — Worries / fears / anxiety** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (AACAP
anxiety topic; LOW/topic-only)
> "Çocuğunuz sık sık endişeli, kaygılı ya da korkulu göründüğü zamanlar oluyor mu?"
CANDIDATE — clinician to approve wording.

**Q5 — Attention / activity across settings** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
("pervasive, occurring in 2 or more important settings")
> "Çocuğunuzun dikkatini toplamakta ya da hareketliliğinde zorlandığını hem evde hem de okulda fark
> ediyor musunuz?"
CANDIDATE — clinician to approve wording. "hem evde hem de okulda" reflects the more-than-one-setting
framing without asserting any diagnosis.

**Q6 — Sleep changes** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
> "Çocuğunuzun uyku düzeninde bir değişiklik var mı? Örneğin uykuya dalmakta güçlük ya da sık
> uyanma."
CANDIDATE — clinician to approve wording.

**Q7 — Effect on school / daily functioning** · archetype: `OBSERVATION.story.v1` · source: S2
(impairment "in multiple settings") + S1 (educational context)
> "Bu durumun çocuğunuzun okuldaki ya da günlük yaşamındaki işlerini etkilediğini düşünüyor musunuz?"
CANDIDATE — clinician to approve wording.

**Q8 — Relationships with friends / family** · archetype: `OBSERVATION.story.v1` · source: S1 (social &
family context)
> "Çocuğunuzun arkadaşlarıyla ya da ailesiyle ilişkilerinde son zamanlarda bir değişiklik oldu mu?"
CANDIDATE — clinician to approve wording. Gentle, no blame.

**Q9 — When first noticed / course** · archetype: `OBSERVATION.story.v1` · source: S2 (developmental
history; "evident in early life")
> "Bu değişiklikleri ilk ne zaman fark ettiniz ve o günden bu yana nasıl bir seyir izledi?"
CANDIDATE — clinician to approve wording.

**Q10 — Prior support / known conditions** · archetype: `EVALUATION.problem_diagnosis.v1` · source:
general intake (history); S2 (coexisting conditions)
> "Çocuğunuz daha önce bu konuda bir destek aldı mı, ya da bilmemizi istediğiniz başka bir sağlık ya
> da gelişim durumu var mı?"
CANDIDATE — clinician to approve wording. "destek" (support), not "tedavi", to stay PolicyGuard-clean
and supportive.

**Q11 — Current medications** · archetype: `ACTION.medication.v1` · source: general intake (history)
> "Çocuğunuzun şu anda düzenli olarak kullandığı herhangi bir ilaç var mı?"
CANDIDATE — clinician to approve wording.

**Q12 — Drug allergy / adverse reaction** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source:
general intake
> "Çocuğunuzun herhangi bir ilaca karşı alerjisi ya da daha önce yaşadığı ciddi bir yan etki oldu mu?"
CANDIDATE — clinician to approve wording.

*(12 candidate questions — all supportive proxy intake; none is a crisis/red-flag item and none
raises a `candidate_flag`. Q3, Q5, Q7, Q8, Q9 are grounded in NICE NG134 / NG87 topic domains; Q4 in
the AACAP anxiety CPG (topic-only, LOW); the rest are general intake.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **NICE NG134 / NG87 exact current wording and recommendation numbers** — retrieved via an **NCBI
   Bookshelf mirror** because `nice.org.uk` returned **HTTP 403** to automated fetch; some reported
   1.1.x numbers may reflect the legacy CG28 layout. **NO SOURCE FOUND (primary-page verbatim) —
   clinician must re-capture** from the current NICE text and commit the snapshot before any `source`
   block is finalised.
2. **AACAP anxiety CPG exact page wording** — the primary and mirror PDFs returned as
   **non-extractable binary**, so the S3 topic sentences are a **search-result summary, not a clean
   page-verbatim string**. **NO SOURCE FOUND (page verbatim) — clinician must re-capture** from the
   primary text/journal.
3. **Türkiye-first versioned clinical guideline for child/adolescent mental-health assessment** —
   only ÇOGEPDER (Türkiye Çocuk ve Genç Psikiyatrisi Derneği) society/journal landing pages were
   retrievable; a versioned T.C. Sağlık Bakanlığı / ÇOGEPDER assessment guideline was **NOT located**.
   **NO SOURCE FOUND (versioned primary) — clinician must supply** the correct Türkiye-first source
   and its version/date, and reconcile every S1–S3 row against it.
4. **Any wellbeing instrument for this age group** — no instrument is proposed for compilation. PHQ-9/
   GAD-7 paediatric applicability, licence and Turkish validation are unconfirmed (cf. HB-L24), and
   C-SSRS / WHO-5 are licence-BLOCKED (HB-L2 / HB-L3). **NO SOURCE FOUND (paediatric licence + Turkish
   validation) — clinician must supply** before any instrument is used (instruments without a `GO`
   licence do not compile).
5. **Proxy vs. adolescent self-report, and confidentiality** — this proposal addresses the
   **parent/guardian**. Whether, when and how the adolescent answers directly, and the confidentiality
   boundary for a minor's own disclosures, is a **clinical/legal decision NOT made here**. **Clinician
   + counsel must decide** (cross-ref HB-L20 minors/consent handling; legal invariants).
6. **Crisis / self-harm / suicide handling** — intentionally **absent** from this proposal; it belongs
   to `base.life_threat` (invariant 7) and the crisis-lexicon work (**HB-C17**, open; C-SSRS BLOCKED,
   **HB-L2**). Not a gap to fill *here* — noted so a reviewer does not mistake its absence for an
   oversight.
7. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032 /
   HB-C12); not fabricated. Family mental-health history (item 13) has **no archetype root** → export
   blocked (INT-041 posture). The adolescent's own-report items are not modelled (gap 5).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no `candidate_flag` raised (supportive proxy intake only).
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, warm, non-stigmatizing, no
  diagnosis/treatment/prognosis, no blame; addressed to the parent/guardian; "destek" preferred over
  "tedavi"; marked CANDIDATE.
- **Inv. 7** — crisis/self-harm/suicide deliberately left to the base life-threat layer; nothing here
  extends or relaxes it (and `base.life_threat` is a sibling set nothing may extend).
- **Inv. 10** — no scripted red-flag `text_tr` is proposed (there are no red-flags in this set).
- **Inv. 20** — no accuracy/performance/cut-off figures reproduced; PHQ-2/GAD-2 not described as
  Turkish-validated.
- **Inv. 22** — no bare digits in patient text; compiler must expand any number before TTS.
- **Clinical content rule / instrument licence** — NICE NG134/NG87 & AACAP cited as topic sources
  only, not embedded or scored; an instrument without a `GO` licence does not compile.
- **Legal / minors** — proxy vs. adolescent self-report and confidentiality left as an explicit
  clinical/legal decision (§4 gap 5; cf. HB-L20).
- **HB-C1** — this pack awaits clinician sign-off; NOT served. **HB-C17 / HB-L2 / HB-L3** — crisis
  path, C-SSRS and WHO-5 remain human-blocked and out of scope here.
