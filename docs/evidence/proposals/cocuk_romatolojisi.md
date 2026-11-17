# Çocuk Romatolojisi (Pediatric Rheumatology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Romatolojisi (Pediatric Rheumatology)
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
- **Acute rheumatologic emergencies stay in `base.life_threat` (invariant 7).** An acutely hot, red,
  swollen and immobile joint with fever (septic arthritis), sepsis, and the musculoskeletal
  presentation of malignancy (e.g. leukaemia presenting as bone/joint pain) are life-threats owned by
  the `base.life_threat` sibling set — this specialty pack neither authors nor relaxes them. The alarm
  questions below only **feed** those base gates; they do **not** create a new RED rule in
  `specialty.cocuk_romatolojisi` and do not extend `base.life_threat`. HB-C1 is the open blocker on
  the `clinical_signoff` block of `base.life_threat.yaml` (paediatric reviewer field included).
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. No level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebSearch/WebFetch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived
  rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_romatolojisi.yaml` (an L0 generated
  draft, `status: generated-l0-awaiting-clinical-review`) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — JIA definition (joint swelling / arthritis ≥ 6 weeks, age < 16, exclusion)
- **guideline_id (proposed):** `JIA-DEF-ILAR` (definition originates in the ILAR classification, Petty
  et al. 2001; verbatim below captured from a StatPearls textbook restatement, not the ILAR primary —
  see §4 gap)
- **Publishing body:** StatPearls (NCBI Bookshelf), restating the ILAR (International League of
  Associations for Rheumatology) classification
- **Version / year:** StatPearls entry, current; ILAR criteria: Second Revision, Edmonton 2001
- **URL:** https://www.ncbi.nlm.nih.gov/books/NBK554605/
- **Verbatim:**
  > "Juvenile idiopathic arthritis (JIA) is a heterogeneous group of idiopathic inflammatory arthritis
  > affecting children younger than 16 and lasting 6 weeks or longer."
  > "A diagnosis of JIA is considered in any children younger than 16 years with arthritis for at least
  > six weeks and exclusion of other causes of chronic arthritis."
- **Applicability note:** this grounds the "**persistent joint swelling**" alarm — the clinically
  meaningful signal for a rheumatology intake is joint swelling that **persists** (weeks), not a
  transient/traumatic swelling. The exact "six weeks" boundary is a **classification** criterion, not
  an urgency threshold; it belongs to the clinician's diagnostic reasoning, not to a triage rule here.
  Numbers appear only inside the quote; per invariant 22 no numeral reaches TTS and the §3 drafts carry
  no digits.

### S2 — PMM (Paediatric Musculoskeletal Matters) red flags — serious paediatric MSK pathology
- **guideline_id (proposed):** `PMM-REDFLAGS`
- **Publishing body:** Paediatric Musculoskeletal Matters (PMM), a free, peer-reviewed e-resource
  **endorsed by PReS** (Paediatric Rheumatology European Society) as an educational resource; lead
  author Helen Foster. Underpinned by pGALS (paediatric Gait Arms Legs Spine).
- **Version / year:** live resource (launched Nov 2014); pGALS basis: Foster HE, Jandial S.
  *pGALS — paediatric Gait Arms Legs and Spine: a simple examination of the musculoskeletal system.*
  Pediatric Rheumatology. 2013;11:44.
- **URL:** https://www.pmmonline.org/doctor/clinical-assessment/red-flags/ · pGALS:
  https://link.springer.com/article/10.1186/1546-0096-11-44
- **Verbatim (red flags for serious MSK pathology — malignancy, infection, inflammatory disease, NAI):**
  > "Malaise and / or systemic upset" (fever, reduced appetite, weight loss, sweating, lethargy,
  > pallor, lymphadenopathy, organomegaly)
  > "Night pains - not responsive to simple (e.g., paracetamol [acetaminophen] or ibuprofen)
  > analgesia; persistent as opposed to intermittent pain is more worrying."
  > "Bone pain - often described as deep and throbbing in nature. Usually located in bones rather than
  > joints."
  > "Acute joint pain - often severe and inconsolable, can be a feature of infection"
  > "Bony tenderness - on examination and may occur with inflammatory conditions, infection and
  > malignancy."
  > "Swollen joint(s) - may be subtle or difficult to appreciate on examination"
- **Confidence: MED.** Captured via WebFetch of the PMM "Red Flags" page. PMM is an educational
  resource (PReS-endorsed), not a formal clinical guideline; re-verify the exact wording and, where a
  primary guideline exists (PReS/RCPCH), prefer it before grounding any action script.

### S3 — NICE NG143 Fever in under 5s (limb/joint swelling; non-weight-bearing; prolonged fever)
- **guideline_id (proposed):** `NICE-NG143`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / year:** NG143, published 2019 (a 2021 update is referenced — confirm exact revision, §4 gap)
- **Citation:** NICE. *Fever in under 5s: assessment and initial management.* NICE guideline NG143.
- **URL (primary):** https://www.nice.org.uk/guidance/ng143 — returned **HTTP 403** on fetch; verbatim
  captured from the NCBI Bookshelf mirror table `cha.tab2`:
  https://www.ncbi.nlm.nih.gov/books/NBK552086/table/cha.tab2/
- **Verbatim (AMBER / intermediate-risk, "Other"):**
  > "Swelling of a limb or joint"
  > "Non-weight bearing limb/not using an extremity"
  > "Fever for >5 days"
- **Applicability note:** NG143 is a **fever** guideline for under-5s; these layperson-observable signs
  (a swollen limb/joint, a child not using a limb, prolonged fever) are the ones a parent can report
  and a clinician can re-use for a febrile-child rheumatology intake. That re-use, and any age
  extension beyond five years, is a clinical judgement the signing clinician must confirm. The number
  appears only inside the quote; §3 drafts carry no digits.

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
| 2 | Narrative of current musculoskeletal complaint | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Joint swelling — presence (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Joint swelling — persistence / duration (S1: arthritis ≥ 6 weeks) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Joint pain and morning stiffness / "gelling" | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Limp / refusal to bear weight / not using a limb (S3) — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Night pain / bone pain, poorly responsive to simple analgesia (S2) — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Persistent / recurrent fever with the joint complaint (S2 systemic upset; S3 prolonged fever) — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Acutely hot, red, immobile joint with fever (septic arthritis) (S2 "acute joint pain") — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Systemic upset — weight loss / poor appetite / pallor / lethargy (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Rash accompanying the joint symptoms | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 12 | Red / painful eye or vision change (JIA-associated uveitis — source gap, §4) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 13 | Known rheumatologic / autoimmune diagnoses | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 14 | Current medications (incl. NSAIDs / DMARDs / steroids) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 15 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 16 | Depression screening (adolescent/parent, if consented) | `openEHR-EHR-OBSERVATION.phq9.v1` | OBSERVATION | deferred (INT-032) |
| 17 | Anxiety screening (adolescent/parent, if consented) | `openEHR-EHR-OBSERVATION.gad7.v1` | OBSERVATION | deferred (INT-032) |
| 18 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 19 | **Family history of autoimmune / rheumatic disease, psoriasis, uveitis, IBD** | **no archetype root — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 19: the committed `.opt` exposes **no family-history archetype root** (the only CLUSTER named in
  files/03 §7, `CLUSTER.provenance`, is itself ABSENT from the template). Capturing a family history of
  autoimmune/rheumatic disease therefore has no export target today → **export blocked (INT-041
  posture)**; do not invent an at-code path. Family history (e.g. psoriasis, enthesitis-related /
  HLA-B27 conditions, uveitis, IBD) is clinically important in paediatric rheumatology, so the gap is
  real, not cosmetic. Clinician/architecture decision needed (candidate: INT-032 archetype addition).
- Items 16–17 (PHQ-9/GAD-7) are the consented wellbeing instruments, included only for completeness of
  binding; their content/cut-offs are out of scope for this rheumatology proposal (and are age-gated —
  a young child is not the respondent).

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian** about the child
(*çocuğunuz*); one concern per question (invariant 2: one question per turn); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".**
Per invariant 22, none of the drafts below contains a numeral; the protocol compiler must still expand
any future digit to Turkish orthography before TTS.

> Triage note for every alarm-derived item (Q6–Q10, new numbering): the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED for septic arthritis, sepsis and MSK-presenting malignancy stays in
> `base.life_threat` (invariant 7) with a committed `source` snapshot and all three RED axes
> (route × register × location, invariant 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Renumbering, old → new — sections outside §3 still use the old numbers: Q1–Q6
unchanged (Q3 now asked only if Q2 yes) · Q7 → Q7 (night waking) + Q8 (pain despite analgesia) · Q8 →
Q9 · Q9 → Q10 · Q10 → Q11 · Q11 → Q12 · Q12 → Q13.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün hekime getiren en önemli konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Joint swelling (presence)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (JIA definition — "arthritis")
> "Çocuğunuzun bir ya da birden fazla ekleminde şişlik fark ettiniz mi?"
gen: slot=eklem_sisligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Joint swelling persistence / duration (if Q2 yes)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("lasting 6 weeks or longer")
> "Bu eklem şişliği ne zamandır sürüyor?"
gen: slot=eklem_sisligi_suresi; type=duration; ask_if=eklem_sisligi == true
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician
+ rules-engine confirmation — NOT authoritative)** if the swelling is persistent (weeks), per S1; the
"six weeks" boundary stays in the rule (a classification criterion for the clinician), never in the
patient text.

**Q4 — Joint pain and morning stiffness** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake (symptom characterisation; specific stiffness threshold NO SOURCE FOUND — §4)
> "Çocuğunuz sabahları ya da uzun süre hareketsiz kaldıktan sonra eklemlerinde tutukluk veya ağrı
> yaşıyor mu?"
gen: slot=sabah_tutuklugu; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Reduced function of a joint** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake (functional impact)
> "Çocuğunuz günlük hareketlerinde, örneğin yürürken, giyinirken ya da oyun oynarken zorlanıyor mu?"
gen: slot=gunluk_hareket_guclugu; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Limp / refusal to bear weight** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("Non-weight bearing limb/not using an extremity") — **feeds `base.life_threat`**
> "Çocuğunuz aksıyor, ayağına basmaktan kaçınıyor ya da bir kolunu veya bacağını kullanmak istemiyor mu?"
gen: slot=aksama_kullanmama; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; the authoritative RED is owned by `base.life_threat` (invariant 7), not this pack.

**Q7 — Night pain waking the child** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("Night pains ... persistent ... more worrying") — **feeds `base.life_threat`**
> "Çocuğunuzun ağrısı onu geceleri uykudan uyandırıyor mu?"
gen: slot=gece_uyandiran_agri; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; persistent night/bone pain can signal infection or malignancy (S2) — RED owned by
`base.life_threat`.

**Q8 — Pain persisting despite analgesia** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (night pain not responsive to simple analgesia; "Bone pain") — **feeds `base.life_threat`**
> "Çocuğunuzun ağrısı ağrı kesiciye rağmen devam ediyor mu?"
gen: slot=agri_kesiciye_ragmen_agri; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**, per S2 — RED owned by `base.life_threat`.

**Q9 — Persistent / recurrent fever with joint symptoms** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (systemic upset — "fever"); S3 ("Fever for >5 days") — **feeds `base.life_threat`**
> "Çocuğunuzun eklem şikâyetleriyle birlikte uzun süredir devam eden ya da tekrarlayan ateşi oldu mu?"
gen: slot=eklemle_ates; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; the systemic-JIA quotidian-fever threshold is a §4 gap; acute febrile emergencies
(sepsis) are owned by `base.life_threat`.

**Q10 — Acutely hot, red, painful joint** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("Acute joint pain ... can be a feature of infection") — **feeds `base.life_threat`**
> "Şu sıralarda çocuğunuzun bir eklemi aniden sıcak, kızarık ve çok ağrılı hâle geldi mi?"
gen: slot=ani_sicak_kizarik_eklem; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; an acutely hot joint with fever (septic arthritis) is a life-threat owned by
`base.life_threat` (invariant 7), not a RED authored here.

**Q11 — Systemic upset (weight loss / appetite / pallor)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("Malaise and / or systemic upset")
> "Çocuğunuzda son zamanlarda kilo kaybı, iştahsızlık, solukluk ya da alışılmadık bir hâlsizlik fark
> ettiniz mi?"
gen: slot=genel_durum_bozuklugu; type=boolean
CANDIDATE — clinician to approve wording.

**Q12 — Rash with joint symptoms** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake (symptom characterisation)
> "Çocuğunuzun eklem şikâyetleriyle birlikte ciltte döküntü ortaya çıktı mı?"
gen: slot=eklemle_dokuntu; type=boolean
CANDIDATE — clinician to approve wording. Note: a specific rash red-flag threshold for this specialty
is **NO SOURCE FOUND** (§4); a non-blanching rash with fever is owned by `base.life_threat`.

**Q13 — Known rheumatologic diagnoses** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general intake (history)
> "Çocuğunuza daha önce romatizmal ya da bağışıklık sistemiyle ilgili bir hastalık tanısı kondu mu?"
gen: slot=romatizmal_tani; type=boolean
CANDIDATE — clinician to approve wording.

*(13 candidate questions. Family history of autoimmune/rheumatic disease and JIA-associated uveitis
screening — openEHR items 19 and 12 — are clinically relevant but the former has no export target
[export blocked, INT-041 posture] and the latter lacks a retrieved source [§4]; neither is advanced
beyond the binding table without a clinician decision.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned paediatric-rheumatology guideline (verbatim)** — **NO SOURCE FOUND.** No
   Turkish MoH or specialty-society (e.g. a Çocuk Romatoloji / Türk pediatrik romatoloji) versioned
   guideline document was retrieved. Per the pack's own header the expected sources are **T.C. Sağlık
   Bakanlığı klinik protokolleri / HSGM rehberleri** and **ilgili uzmanlık derneği kılavuzları** —
   **clinician must supply** the exact Turkish wording, version and date (never an invented citation,
   files/04 §8.1 rule 3).
2. **ILAR primary text (verbatim) for the JIA and systemic-JIA definitions** — S1's "under 16 / ≥ 6
   weeks / exclusion" wording was captured from a **StatPearls textbook restatement**, not the ILAR
   primary (Petty et al., *J Rheumatol* 2004;31:390). The `jrheum` PDF fetch did not yield the verbatim
   ILAR "Systemic arthritis" and "Arthritis" definitions. **NO SOURCE FOUND (primary, verbatim) —
   clinician must supply** from the ILAR paper.
3. **Systemic JIA (Still) fever criterion — "quotidian fever of at least 2 weeks"** — repeatedly
   referenced by web-search summaries (e.g. "at least 15 days of fever, quotidian pattern") but **not
   captured verbatim** from a primary/authoritative source. **NO SOURCE FOUND (verbatim) — clinician
   must supply**; until then the persistent-fever alarm (Q8) leans on S2/S3 only and asserts no
   threshold.
4. **Morning stiffness / "gelling" threshold** — a recognised inflammatory feature, but no verbatim
   red-flag threshold (duration, "> X minutes") was retrieved. **NO SOURCE FOUND — clinician must
   supply**; Q4 captures the symptom without a threshold.
5. **JIA-associated uveitis screening** (asymptomatic anterior uveitis is common and sight-threatening
   in oligoarticular ANA-positive JIA) — the screening interval / red-flag wording was **not
   retrieved**. **NO SOURCE FOUND — clinician must supply** (candidate: AAP/ACR ophthalmologic
   screening guidance); Q12/item 12 hold the binding but no sourced rule.
6. **Applicability of NG143 (S3) beyond age five and to a non-febrile MSK intake** — NG143 is a
   fever-in-under-5s guideline; whether its "swelling of a limb/joint" and "non-weight bearing" signs
   transfer to older children and to a rheumatology context is a **clinical judgement — clinician must
   confirm.** NG143's exact 2021 revision date must also be confirmed.
7. **PMM status** — S2 is a **PReS-endorsed educational resource**, not a formal guideline; before it
   grounds any action script the clinician should confirm the wording against a primary PReS/RCPCH
   document. **Confirm source tier.**
8. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned. Septic arthritis, sepsis and MSK-presenting malignancy remain owned
   by `base.life_threat` (invariant 7; HB-C1 open); `packages/protocols/triage` + clinician must
   supply, with committed `source` snapshots, before anything compiles.
9. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032);
   not fabricated. Family history of autoimmune/rheumatic disease (item 19) has **no archetype root** →
   export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules
  engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, addressed to the
  parent/guardian, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — septic arthritis, sepsis and MSK-presenting malignancy stay in `base.life_threat`; this
  pack only feeds those gates and neither adds to nor relaxes them.
- **Inv. 10** — scripted/alarm wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — the drafted questions contain no numerals; source quotes with numbers are quotes only,
  and the compiler must expand any digit before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S3 for
  that block but does not itself commit a snapshot; no Türkiye-first source was located (§4.1).
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
