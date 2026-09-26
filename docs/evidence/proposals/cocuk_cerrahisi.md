# Çocuk Cerrahisi (Paediatric Surgery) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Cerrahisi (Paediatric Surgery)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. Paediatric: every question is addressed to the
**parent/guardian (proxy)**. This file is a *proposal for a clinician to sign off*. It assigns **no**
authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Acute surgical emergencies stay in `base.life_threat` (invariant 7).** Bilious/green vomiting
  with suspected malrotation-volvulus, testicular torsion, an incarcerated/irreducible inguinal
  hernia, and intussusception with bowel ischaemia are life-threatening presentations. Per invariant
  7 the `base.life_threat` sibling set is authoritative and *nothing may extend it*; this specialty
  proposal therefore **only feeds intake questions** that surface the symptom for the clinician and
  the rules engine — it does **not** author, relax or duplicate any life-threat threshold.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**,
  written as *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The
  guideline's own urgency wording is quoted verbatim; no level is asserted.
- **Source-tier caveat (Türkiye-first).** Files/04 §8 and files/09 §2 name **T.C. Sağlık Bakanlığı**
  klinik protokolleri and **Türkiye Çocuk Cerrahisi Derneği** society guidelines as the intended
  sources. Neither a versioned MoH protocol nor a retrievable TÇCD clinical guideline (only a
  patient-information leaflet title and private-hospital pages surfaced) was obtained verbatim on
  2026-09-20. The sources below are therefore **real, retrieved international/NHS clinical guidelines
  used as interim grounding** — each must be **reconciled against, or replaced by, the Türkiye-first
  primary** before sign-off (see §4).
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / PDF extraction). Before sign-off, each verbatim sentence MUST
  be re-checked against the **primary published text** and committed as a **verbatim source
  snapshot** with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then
  any derived rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_cerrahisi.yaml` (an L0 draft that
  never serves) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NHS Thames Valley & Wessex Neonatal ODN — bilious vomiting / malrotation pathway
- **guideline_id (proposed):** `NHS-TVW-BILIOUS-VOMITING-2017`
- **Publishing body:** Thames Valley & Wessex Neonatal Operational Delivery Network (NHS, hosted by
  University Hospital Southampton NHS Foundation Trust)
- **Document:** *Wessex Care Pathway for Term Infants Referred with Bilious Vomiting for Exclusion of
  Malrotation.* Date of publication February 2015; last reviewed April 2017, v1.9; authors Melanie
  Drewett (CNS, Neonatal Surgery) and Mr Charles Keys (Consultant Paediatric & Neonatal Surgeon).
- **URL:** https://www.piernetwork.org/uploads/4/7/8/1/47810883/wessex_bilious_vomiting_pathway_-_malrotation_guideline_rvwd_apr_17_v1.9_being_reviewed_2022.pdf
- **Verbatim (Introduction):**
  > "Any term neonate with bilious vomiting should have the diagnosis of malrotation and volvulus
  > considered and mandates immediate assessment and evaluation. In the absence of a clear diagnosis
  > the safe approach is to rule out the possibility of malrotation first."
- **Verbatim (Introduction):**
  > "Bilious vomiting is the initial symptom, but abdominal distension is often absent."
- **Verbatim (Executive Summary):**
  > "Unless treated in a timely manner there may be extensive ischaemic damage and loss of small
  > bowel resulting in short gut syndrome and parenteral nutrition dependence or death."
- **Confidence: MEDIUM.** Real, versioned NHS network care pathway retrieved as a PDF; **not** a
  Türkiye-first source and **not** NICE/APSA. Grounds the *bilious-vomiting* intake question only;
  the emergency itself lives in `base.life_threat`.

### S2 — RCH Melbourne — Acute Scrotal Pain or Swelling (testicular torsion, irreducible hernia)
- **guideline_id (proposed):** `RCH-ACUTE-SCROTUM-2026`
- **Publishing body:** The Royal Children's Hospital Melbourne — Clinical Practice Guidelines
- **Version / year:** last updated January 2026
- **URL:** https://www.rch.org.au/clinicalguide/guideline_index/Acute_Scrotal_Pain_or_Swelling/
- **Verbatim:**
  > "Testicular torsion and irreducible hernia are emergencies and if suspected, require urgent
  > surgical evaluation"
- **Verbatim:**
  > "If suspected, or cannot be confidently excluded, urgent surgical review"
- **Note (presentation):** the presentation descriptors captured for torsion — pain "Severe … Usually
  sudden onset … May radiate to iliac fossa or thigh" and nausea/vomiting "Common (90%)" — were
  returned as **table cells**; the exact table row/label MUST be reconciled against the primary page
  before sign-off. **Confidence: MEDIUM** (real CPG; not Türkiye-first / not NICE-APSA).

### S3 — RCH Melbourne — Intussusception
- **guideline_id (proposed):** `RCH-INTUSSUSCEPTION-2026`
- **Publishing body:** The Royal Children's Hospital Melbourne — Clinical Practice Guidelines
- **Version / year:** last updated February 2026
- **URL:** https://www.rch.org.au/clinicalguide/guideline_index/intussusception/
- **Verbatim:**
  > "Children most commonly present to the ED with paroxysmal (colicky) abdominal pain and/or
  > vomiting (70% of presentations)"
- **Verbatim:**
  > "The typical paroxysmal pain is described as severe, cyclic or cramping."
- **Verbatim:**
  > "Intermittent pain or distress, the child may appear very well between episodes"
- **Verbatim:**
  > "Rectal bleeding or the classic 'red currant jelly' stool are late, less common signs suggesting
  > bowel ischemia and infarction"
- **Confidence: MEDIUM** (real CPG; not Türkiye-first / not NICE-APSA).

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes**. A slot whose leaf path is not yet authored carries
**`openehr_deferred_reason`** (INT-032, P3 export tier) — it is **not** invented. So each item below
binds to an archetype **root**; the specific leaf path is **deferred**, never fabricated.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the current complaint (onset/course) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Abdominal pain — presence | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Colicky/intermittent pain with pallor (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Vomiting — presence | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Bilious/green vomit (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Blood / red-currant-jelly stool (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Sudden severe testicular/groin pain (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Groin/scrotal swelling or irreducible lump (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Prior surgical diagnosis (undescended testis, hernia) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 13 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine / `base.life_threat` only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 14 | **Feeding history / last meal before surgery (pre-op fasting)** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 14: the committed `.opt` exposes no fasting/observation-of-feeding archetype root, so a
  pre-operative "last oral intake" capture has **no export target today → export blocked (INT-041
  posture)**; do not invent an at-code path. Clinician/architecture decision needed (candidate:
  INT-032 archetype addition).
- **PHQ-9 / GAD-7 not bound here.** Those instruments are the *adult* consented-wellbeing screens;
  their paediatric applicability is age-dependent and out of scope for this surgical red-flag
  proposal — no paediatric wellbeing instrument is asserted.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian (proxy)** about
*çocuğunuz*; one concern per question (invariant 2: one question per turn); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".**
No bare numerals appear (invariant 22); no emergency number or action script is spoken here — RED
action scripts belong to `base.life_threat` / triage, never to an intake question.

> Triage note for every red-flag-derived item: the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED for an acute surgical emergency comes from `base.life_threat` with all three RED
> axes (route × register × location, invariant 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Findings 10 and 14 apply. Renumbering, old → new — sections
outside §3 still use the old numbers: Q1 → Q1 · Q2 removed (base `onset_date` + `trajectory`; the
reviewer's C2 trajectory fallback only if those base slots are not served) · Q3 → Q2 · Q4 → Q3
(attacks, if Q2) + Q4 (pallor during attacks, if Q3) · Q5 → Q5 · Q6 → Q6 (if Q5) · Q7 → Q7 · Q8 → Q8
· Q9 → Q9 (swelling) + Q10 (goes back in, if Q9) · Q10 → Q11 · Q11 removed (base meds) · Q12 removed
(base `allergies`).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün getiren temel şikâyet nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Abdominal pain presence** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
(feeds S3)
> "Çocuğunuzun karın ağrısı oluyor mu?"
gen: slot=karin_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q3.

**Q3 — Pain comes in attacks** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("paroxysmal
(colicky) abdominal pain"; "Intermittent pain or distress")
> "Karın ağrısı gelip geçen ataklar hâlinde mi oluyor?"
gen: slot=atak_seklinde_karin_agrisi; type=boolean; ask_if=karin_agrisi == true
CANDIDATE — clinician to approve wording.

**Q4 — Pallor during the attacks** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (pallor
during episodes)
> "Bu ağrı ataklarında çocuğunuzun benzi sararıyor mu?"
gen: slot=ataklarda_benzi_sararma; type=boolean; ask_if=atak_seklinde_karin_agrisi == true
CANDIDATE — clinician to approve wording. Replaces "soluyor", which reads as "breathing hard" as
easily as "going pale" (finding 10). Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)**, per S3.

**Q5 — Vomiting presence** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
(feeds S1/S3)
> "Çocuğunuz son zamanlarda kustu mu?"
gen: slot=kusma; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q6.

**Q6 — Bilious / green vomit** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
> "Kusmuğun rengi yeşil ya da sarımsı yeşil miydi?"
gen: slot=yesil_kusma; type=boolean; ask_if=kusma == true
CANDIDATE — clinician to approve wording. The jargon "safra" is gone. Candidate_flag: **YELLOW_REVIEW
(candidate, pending clinician + rules-engine confirmation — NOT authoritative)**; per S1, bilious
vomiting "mandates immediate assessment" — the emergency itself is owned by `base.life_threat`.

**Q7 — Blood / red-currant-jelly stool** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3
> "Çocuğunuzun dışkısında kan ya da reçel kıvamında koyu kırmızı bir görünüm fark ettiniz mi?"
gen: slot=diskida_kan; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**; per S3 a
"late, less common" sign of bowel ischaemia.

**Q8 — Sudden testicular / groin pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
> "Çocuğunuzun testis ya da kasık bölgesinde aniden başlayan şiddetli bir ağrı oldu mu?"
gen: slot=ani_testis_kasik_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**; per S2
torsion "if suspected … require urgent surgical evaluation" — the emergency is owned by
`base.life_threat`.

**Q9 — Groin / scrotal swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (irreducible
hernia)
> "Çocuğunuzun kasığında ya da testis torbasında bir şişlik var mı?"
gen: slot=kasik_testis_sislik; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q10.

**Q10 — Swelling goes back in** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
(irreducibility; mirrors genel_cerrahi Q2/Q3)
> "Bu şişlik elle bastırınca ya da çocuk uzanınca içeri giriyor mu?"
gen: slot=sislik_iceri_giriyor; type=boolean; ask_if=kasik_testis_sislik == true
CANDIDATE — clinician to approve wording. A "no" answer is a gate input only; per S2 irreducible
hernia is an emergency owned by `base.life_threat`.

**Q11 — Prior surgical diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general
intake (history)
> "Çocuğunuza daha önce kasık fıtığı ya da inmemiş testis gibi bir tanı kondu mu?"
gen: slot=onceki_cerrahi_tani; type=boolean
CANDIDATE — clinician to approve wording.

*(11 candidate questions after revision; red-flag-derived: Q3–Q4, Q6–Q8, Q9–Q10.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first primary source (T.C. Sağlık Bakanlığı protocol or Türkiye Çocuk Cerrahisi Derneği
   guideline)** — only a TÇCD *patient-information leaflet* title ("Kasık Fıtığı ve Hidrosel: Hasta
   Bilgilendirme Rehberi") and private-hospital marketing pages surfaced; **no versioned Turkish
   clinical guideline document was retrieved verbatim**. **NO SOURCE FOUND (Türkiye-first) — clinician
   must supply** and reconcile every S1–S3 row against it.
2. **NICE / APSA equivalent for each red flag** — the named international bodies (NICE, APSA) were not
   retrieved verbatim (NICE CKS returned HTTP 403 to automated fetch). **NO SOURCE FOUND (named body)
   — clinician to supply** the NICE CKS "Scrotal pain and swelling", a NICE/APSA malrotation source,
   and a NICE/APSA intussusception source.
3. **Acute appendicitis red flags** (migrating right-iliac-fossa pain, pain-before-vomiting, guarding)
   — no versioned guideline was retrieved verbatim; Q3 captures abdominal pain generically only.
   **NO SOURCE FOUND (verbatim) — clinician must supply** (candidate: NICE/RCS paediatric acute
   abdomen pathway).
4. **Pyloric stenosis** (projectile *non-bilious* vomiting in the young infant, hunger after vomiting)
   — distinct from the S1 bilious pathway; **NO SOURCE FOUND (verbatim) — clinician must supply**.
5. **Undescended testis referral timing** (the 6–24-month operative window quoted on Turkish
   hospital pages is **not** a retrievable versioned guideline) — Q10 captures it only as history.
   **NO SOURCE FOUND (versioned) — clinician must supply** (candidate: TÇCD / EAU-ESPU).
6. **Incarcerated inguinal hernia** as a stand-alone verbatim threshold — grounded here only via S2's
   "irreducible hernia … emergencies" clause; a dedicated paediatric hernia guideline was **NOT
   FOUND** verbatim. **Clinician to supply.**
7. **RCH torsion presentation table** (row labels / percentages captured as table cells) — reconcile
   against the primary page before any wording is finalised.
8. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here; acute surgical emergencies are owned by `base.life_threat`
   (invariant 7). **`packages/protocols/triage` + `base.life_threat` must supply**, with committed
   `source` snapshots, before anything compiles.
9. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032); not fabricated. Pre-op fasting / last oral intake (item 14) has **no archetype root** →
   export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 7** — acute surgical emergencies (malrotation-volvulus, torsion, incarcerated hernia,
  intussusception with ischaemia) are left to `base.life_threat`; this proposal only feeds questions
  and neither extends nor relaxes that sibling set.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, addressed to the parent/guardian
  (proxy), B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in questions; the compiler must still expand any numeral before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate interim sources
  S1–S3 for that block but does not itself commit a snapshot, and flags the Türkiye-first primary as
  the required replacement.
- **HB-C1** — this pack awaits clinician sign-off; NOT served. `cocuk_cerrahisi.yaml` is an L0 draft
  and is untouched.
