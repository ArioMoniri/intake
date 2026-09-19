# ÇEMATEM (Child & Adolescent Addiction / Substance-use Treatment) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: ÇEMATEM (Çocuk ve Ergen Madde
Bağımlılığı Tedavi Merkezi — child & adolescent addiction / substance-use treatment)
Purpose: patient-owned, Turkish-first **pre-visit intake** (supportive context capture for a
clinician-ready note) — **not** diagnosis, not triage authority, **not** a screening instrument.
This is a **paediatric** specialty: the pre-visit questions are addressed to the **parent /
guardian (proxy)**. This file is a *proposal for a clinician to sign off*. It assigns **no**
authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- **Paediatric proxy intake.** ÇEMATEM serves children and adolescents (T.C. Sağlık Bakanlığı
  service pages describe 12–18 yaş — see S3); the pre-visit questions below are written for the
  **parent or guardian** answering on the child's behalf, in warm, person-first, B1 Turkish. Whether
  and how the adolescent's **own** voice is captured (and any confidentiality boundary) is a
  clinical/consent decision, left open — see §4 gap 4.
- **Supportive, non-stigmatizing only.** Wording never labels the child ("bağımlı" / "madde
  bağımlısı" is never used as a description of the child), never blames the parent, and never asserts
  diagnosis, treatment or prognosis (invariant 2). It captures what the family has noticed and what
  support they are seeking.
- **No crisis / self-harm / suicide screening here — by design.** Any consent-independent crisis or
  self-harm path is **out of scope for this pre-visit intake** and belongs to the base life-threat
  layer (`base.life_threat`, invariant 7 — a sibling set nothing may extend) and the crisis-lexicon
  work (**HB-C17**, still open; C-SSRS is licence-BLOCKED, **HB-L2**). This file introduces **no**
  RED, **no** crisis trigger, and **no** self-harm item. If a family volunteers crisis content, that
  is handled by the signed life-threat layer, not by anything proposed here.
- **Not an instrument.** AACAP's practice parameter (S1) and CRAFFT (S2) are cited **as sources for
  question topics only**. Nothing is embedded, scored, or reproduced verbatim (an instrument whose
  licence is not `GO` does not compile — clinical-content rule; CRAFFT's Turkish validation and
  licence are unconfirmed, §4 gap 5). The candidate questions are original B1 Turkish wording, not
  instrument items.
- **Triage:** per invariant 1, only `packages/protocols/triage` rules can produce RED/YELLOW.
  Nothing here is flagged; every item is ordinary supportive intake. **No `candidate_flag` is
  raised** in this specialty proposal.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval. Before sign-off each verbatim sentence MUST be re-checked against the
  **primary published text** and committed as a **verbatim source snapshot** with a full `source:`
  block. Until then any derived content stays `status: draft_needs_source` and does not compile.
- **No accuracy claims** (invariant 20): no sensitivity/specificity/AUROC figure is reproduced here,
  even though the CRAFFT literature (S2) reports them.
- This file does **not** edit `packages/protocols/specialty/cematem.yaml` (an L0 draft that raises
  if served) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — AACAP Practice Parameter: Assessment & Treatment of Children/Adolescents With SUDs (assessment domains & what to ask)
- **guideline_id (proposed):** `AACAP-SUD-2005`
- **Publishing body:** American Academy of Child and Adolescent Psychiatry (AACAP)
- **Version / year:** 2005 (J Am Acad Child Adolesc Psychiatry, 44(6):609–621)
- **Citation:** Bukstein OG, et al. *Practice Parameter for the Assessment and Treatment of Children
  and Adolescents With Substance Use Disorders.* J Am Acad Child Adolesc Psychiatry.
  2005;44(6):609–621.
- **URL (primary PDF, returned HTTP 403 on fetch):**
  https://www.aacap.org/App_Themes/AACAP/docs/practice_parameters/substance_abuse_practice_parameter.pdf ·
  journal: https://www.sciencedirect.com/science/article/abs/pii/S0890856709616415
- **Retrieved (assessment domains — from the search-result summary, NOT a page-verbatim string):**
  > "Assessment domains include psychiatric/behavioral, family, school/vocational,
  > recreational/leisure, and medical domains."
- **Retrieved (what screening/assessment asks — from the search-result summary, NOT a page-verbatim
  string):**
  > "asking about substance use, including quantity and frequency, the presence of adverse
  > consequences of use, and the adolescent's attitude toward use."
- **Confidence: MEDIUM for structure, gap for verbatim.** The primary PDF returned **HTTP 403** on
  every retrieval attempt, so the above are **search-result summaries, not clean page-verbatim
  strings**, and **exact page wording was NOT captured** (§4 gap 1). Used only to justify *which
  domains/topics* a proxy intake may cover.

### S2 — CRAFFT 2.1 (topics only: recent use, riding with an impaired driver, use to relax, use alone, forgetting, concern from family/friends, trouble)
- **guideline_id (proposed):** `CRAFFT-2.1`
- **Publishing body:** The Center for Adolescent Substance Use and Addiction Research (Boston
  Children's Hospital)
- **Version / year:** 2.1 (provider manual, 2018)
- **URL:** https://crafft.org/ · manual (PDF):
  https://crafft.org/wp-content/uploads/2018/08/FINAL-CRAFFT-2.1_provider_manual_with-CRAFFTN_2018-04-23.pdf
- **Retrieved (item domains — from the search-result summary, NOT reproduced instrument items):**
  the CRAFFT is a short adolescent screen whose six letters stand for **C**ar (riding with / driving
  under the influence), **R**elax (using to relax or feel better), **A**lone (using alone),
  **F**orget (forgetting things done while using), **F**amily/**F**riends (family or friends saying
  the young person should cut down), **T**rouble (getting into trouble while using).
- **Confidence: MEDIUM for domains; instrument NOT used.** Only the *topic areas* are drawn on; the
  instrument items are **not** reproduced or scored (licence + Turkish-validation status unconfirmed
  — §4 gap 5), and **no accuracy figure from the CRAFFT literature is reproduced** (invariant 20).
  Several CRAFFT items are adolescent self-report; here they inform only what a *parent/guardian* may
  reasonably be asked to describe (e.g. concern voiced by family, trouble noticed).

### S3 — T.C. Sağlık Bakanlığı ÇEMATEM (service description — patient + family, age band; NOT a clinical guideline)
- **guideline_id (proposed):** `TR-CEMATEM-SERVICE` (public service-description pages, **not** a
  versioned clinical guideline)
- **Publishing body:** T.C. Sağlık Bakanlığı hospital pages (ÇEMATEM birimleri)
- **Version / year:** undated service pages
- **URL:** https://mehmetakifinaneah.saglik.gov.tr/TR-590102/cocuk-ve-ergen-madde-bagimliligi-tedavi-merkezi-cematem.html ·
  https://konyabeyhekimeah.saglik.gov.tr/TR-770037/cocuk-ergen-madde-bagimliligi-tedavi-merkezi-cematem.html
- **Retrieved (service description — summary, NOT a clinical red-flag):** ÇEMATEM is the MoH unit
  providing outpatient and inpatient care for children/adolescents (service pages describe a 12–18
  yaş band) with substance-use problems **and their families**, delivered by a team including
  physician, psychologist, nurse and social worker.
- **Confidence: LOW.** Service/wayfinding pages only. **No versioned Türkiye-first clinical
  assessment guideline was retrieved** (§4 gap 3); no verbatim clinical sentence is drawn from these
  pages. Used only to confirm the **family-inclusive, paediatric** framing the intake copy respects.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots-only binding, leaf `atNNNN` paths **deferred** (`openehr_deferred_reason`, INT-032 / HB-C12);
nothing fabricated. Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).
All items capture the **parent/guardian's proxy report**; none is a red-flag.

| # | Proposed captured item (proxy report) | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for the visit / support the family is seeking | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | What the parent has noticed, in their own words (story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Which substance/behaviour the family wishes to discuss (S1/S2 topic) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Changes noticed at home/school/with friends (S1 school & family domains) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 5 | How often, in the recent period, as far as the parent knows (S1 frequency) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Effects on the child's daily life/health the family is concerned about (S1 adverse consequences) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Concern raised by school or others (S1 school domain; S2 family/friends, trouble) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Prior support/care the child has received (S1 comprehensive assessment) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 9 | Current medications the child takes | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 10 | Drug allergy / serious adverse reaction (S1 medical domain) | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 11 | Goals / hopes the family has for this visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| 12 | Support around the family (people who help) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate triage outcome (**none raised in this specialty**; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Notes:
- No `symptom_sign` item here is a red-flag; they capture supportive proxy context, not urgency.
- The adolescent's **own-report** items (some CRAFFT domains are self-report) are **not** modelled
  here — capturing the young person's own voice, and any confidentiality boundary, is deferred to a
  clinical/consent decision (§4 gap 4).

---

## 3. Candidate B1 Turkish pre-visit questions (addressed to the parent / guardian)

Register: formal **`siz`** throughout, addressed to the **parent/guardian**; one concern per
question (invariant 2); warm, supportive, **non-stigmatizing**, no diagnosis/treatment/prognosis
language, no alarming wording, no blame. **All marked "CANDIDATE — clinician to approve wording".**
No bare digits (invariant 22). **No crisis/self-harm item appears — by design (see §0).**

**Q1 — Reason for visit / support wanted** · archetype: `EVALUATION.reason_for_encounter.v1` · source:
general intake (S3 family-inclusive framing)
> "Bugün çocuğunuz için sizi buraya getiren konu nedir? Hangi konuda destek almak istersiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Parent's own-words narrative** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Fark ettiklerinizi kendi sözlerinizle, rahat hissettiğiniz kadar anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q3 — Which substance / behaviour to discuss** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(substances-used topic) / S2 (topic areas)
> "Bugün çocuğunuzla ilgili hangi madde ya da alışkanlık konusunda konuşmak istersiniz?"
CANDIDATE — clinician to approve wording. Non-stigmatizing; no label applied to the child.

**Q4 — Changes noticed at home/school/with friends** · archetype: `OBSERVATION.story.v1` · source: S1
(school/family/recreational domains)
> "Son zamanlarda çocuğunuzun evdeki, okuldaki ya da arkadaşlarıyla ilişkilerindeki bir değişikliği fark ettiniz mi?"
CANDIDATE — clinician to approve wording.

**Q5 — How often, recent period (proxy knowledge)** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S1 (frequency topic)
> "Bildiğiniz kadarıyla, son zamanlarda bu ne sıklıkla oluyor?"
CANDIDATE — clinician to approve wording. "Bildiğiniz kadarıyla" keeps it a proxy report, not a
demand for certainty.

**Q6 — Effects on the child the family is concerned about** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 (adverse consequences of use)
> "Bu durumun çocuğunuzun günlük yaşamını ya da sağlığını etkilediğini düşündüğünüz, yardım almak istediğiniz bir yön var mı?"
CANDIDATE — clinician to approve wording. Supportive, non-judgemental.

**Q7 — Concern raised by school or others** · archetype: `OBSERVATION.story.v1` · source: S1 (school
domain) / S2 (family/friends, trouble)
> "Okuldan ya da çevrenizden biri bu konuda size endişesini dile getirdi mi?"
CANDIDATE — clinician to approve wording. Gentle, no blame.

**Q8 — Prior support / care received** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S1
(comprehensive assessment)
> "Çocuğunuz daha önce bu konuda bir destek aldı mı, ya da bilmemizi istediğiniz başka bir sağlık durumu var mı?"
CANDIDATE — clinician to approve wording. "destek" (support), not "tedavi", to stay PolicyGuard-clean
and supportive.

**Q9 — Current medications the child takes** · archetype: `ACTION.medication.v1` · source: S1 (medical
domain)
> "Çocuğunuzun şu anda düzenli olarak kullandığı herhangi bir ilaç var mı?"
CANDIDATE — clinician to approve wording.

**Q10 — Drug allergy / adverse reaction** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source:
S1 (medical domain)
> "Çocuğunuzun herhangi bir ilaca karşı alerjisi ya da daha önce yaşadığı ciddi bir yan etki oldu mu?"
CANDIDATE — clinician to approve wording.

**Q11 — Goals / hopes from the visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source:
general intake (S3 supportive framing)
> "Bu görüşmeden ve önümüzdeki süreçten en çok ne elde etmeyi umuyorsunuz?"
CANDIDATE — clinician to approve wording.

**Q12 — Support around the family** · archetype: `OBSERVATION.story.v1` · source: general intake (S3
family-inclusive care)
> "Bu süreçte size ve çocuğunuza destek olan kişiler var mı?"
CANDIDATE — clinician to approve wording.

*(12 candidate questions — all supportive proxy intake; none is a crisis/red-flag item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **AACAP practice-parameter exact page wording** — the primary PDF returned **HTTP 403** on every
   retrieval attempt, so the S1 domain/ask sentences are **search-result summaries, not clean
   page-verbatim strings**. **NO SOURCE FOUND (page verbatim) — clinician must re-capture** from the
   primary text (PDF or journal) and commit the snapshot before any `source` block is finalised.
2. **CRAFFT verbatim item text** — deliberately **not** reproduced (instrument-licence rule; and the
   items are largely adolescent self-report, not a proxy questionnaire). The candidate questions
   above are original wording, not CRAFFT items. **NO SOURCE FOUND (verbatim item text) — and none
   is needed here** unless a licensed instrument is later adopted.
3. **Türkiye-first versioned clinical guideline for child/adolescent substance-use assessment** —
   only MoH ÇEMATEM service/wayfinding pages (S3, LOW confidence) and international guidance were
   retrievable. A versioned T.C. Sağlık Bakanlığı / Türkiye Psikiyatri Derneği / Çocuk-Ergen
   Psikiyatrisi assessment guideline was **NOT located**. **NO SOURCE FOUND (versioned primary) —
   clinician must supply** the correct Türkiye-first source and its version/date.
4. **Proxy vs. adolescent self-report, and confidentiality** — this proposal addresses the
   **parent/guardian**. Whether, when and how the adolescent answers directly, and the
   confidentiality boundary for a minor's own disclosures, is a **clinical/legal decision NOT made
   here**. **Clinician + counsel must decide** (cross-ref minors/consent handling; legal invariants).
5. **CRAFFT (or any screen) licence + Turkish-validation status for this age group** — not
   confirmed; no instrument is proposed for compilation. **NO SOURCE FOUND (licence + Turkish
   validation) — clinician must supply** before any instrument is used (instruments without a `GO`
   licence do not compile).
6. **Crisis / self-harm handling** — intentionally **absent** from this proposal; it belongs to
   `base.life_threat` (invariant 7) and the crisis-lexicon work (**HB-C17**, open; C-SSRS BLOCKED,
   **HB-L2**). Not a gap to fill *here* — noted so a reviewer does not mistake its absence for an
   oversight.
7. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032 / HB-C12); not fabricated. The adolescent's own-report items are not modelled (gap 4).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no `candidate_flag` raised (supportive proxy intake only).
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, warm, non-stigmatizing, no
  diagnosis/treatment/prognosis, no blame; addressed to the parent/guardian; "destek" preferred over
  "tedavi"; marked CANDIDATE.
- **Inv. 7** — crisis/self-harm deliberately left to the base life-threat layer; nothing here
  extends or relaxes it (and `base.life_threat` is a sibling set nothing may extend).
- **Inv. 10** — no scripted red-flag `text_tr` is proposed (there are no red-flags in this set).
- **Inv. 20** — no accuracy/performance figures reproduced (CRAFFT's reported psychometrics are not
  restated).
- **Inv. 22** — no bare digits in patient text; compiler must expand any number before TTS.
- **Clinical content rule / instrument licence** — AACAP & CRAFFT cited as topic sources only, not
  embedded or scored; an instrument without a `GO` licence does not compile.
- **Legal / minors** — proxy vs. adolescent self-report and confidentiality left as an explicit
  clinical/legal decision (§4 gap 4).
- **HB-C1** — this pack awaits clinician sign-off; NOT served. **HB-C17 / HB-L2** — crisis path and
  C-SSRS remain human-blocked and out of scope here.
