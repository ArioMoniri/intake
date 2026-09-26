# Çocuk Ürolojisi (Paediatric Urology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Ürolojisi (Paediatric Urology)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. Paediatric: every question is addressed to the
**parent/guardian (proxy)** about *çocuğunuz*. This file is a *proposal for a clinician to sign off*.
It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Acute surgical/urological emergencies stay in `base.life_threat` (invariant 7).** Testicular
  torsion (the acute scrotum) is a time-critical emergency. Per invariant 7 the `base.life_threat`
  sibling set is authoritative and *nothing may extend it*; this specialty proposal therefore **only
  feeds intake questions** that surface the symptom for the clinician and the rules engine — it does
  **not** author, relax or duplicate any life-threat threshold.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**,
  written as *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The
  guideline's own urgency wording is quoted verbatim; no level is asserted.
- **Source-tier caveat (Türkiye-first).** The L0 pack header for `cocuk_urolojisi` (files/09 §2)
  names **T.C. Sağlık Bakanlığı klinik protokolleri / HSGM rehberleri** and **ilgili uzmanlık
  derneği kılavuzları** (Türk Çocuk Ürolojisi Derneği / Türk Üroloji Derneği) as the intended
  sources, and records that files/04 and files/09 name **no specific guideline title** for the
  `child_health` cluster — selection *awaits the branch clinician*. Neither a versioned MoH protocol
  nor a retrievable Turkish-society clinical guideline was obtained verbatim on 2026-09-20 (the one
  Turkish-society PDF located returned as non-extractable binary — see §4). The sources below are
  therefore **real, retrieved EAU-ESPU (European) guideline text used as interim grounding** — each
  must be **reconciled against, or replaced by, the Türkiye-first primary** before sign-off (§4).
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch). Before sign-off, each verbatim sentence MUST be re-checked
  against the **primary published text** and committed as a **verbatim source snapshot** with a full
  `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule stays
  `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_urolojisi.yaml` (an L0 draft that
  raises if served — `maturity: L0`, `status: generated-l0-awaiting-clinical-review`) or any served
  pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — EAU-ESPU Guidelines on Paediatric Urology — Acute Scrotum (testicular torsion)
- **guideline_id (proposed):** `EAU-ESPU-PAED-URO-ACUTE-SCROTUM`
- **Publishing body:** European Association of Urology (EAU) with the European Society for Paediatric
  Urology (ESPU), Paediatric Urology Guidelines Panel
- **Version / year:** online guideline chapter (2024/2025 update cycle) — exact edition to be pinned
- **URL:** https://uroweb.org/guidelines/paediatric-urology/chapter/acute-scrotum
- **Verbatim (Recommendation):**
  > "Testicular torsion is a paediatric urological emergency and requires immediate treatment."
- **Verbatim (Recommendation):**
  > "Perform urgent surgical exploration in all cases of testicular torsion as soon as possible."
- **Verbatim (Clinical presentation):**
  > "The sudden onset of severe pain in combination with a vagal reaction (e.g. nausea, vomiting) is
  > typical for torsion of the testis or appendix testis."
- **Verbatim (Clinical presentation):**
  > "Torsion of the testis occurs most often in the neonatal period and around puberty, whereas
  > torsion of the appendix testis occurs over a wider age range."
- **Verbatim (Summary of evidence):**
  > "The earlier surgical intervention for testicular torsion is performed, the better the outcome
  > for testicular histology. Ideally within 4-6 hours after the onset of symptoms."
- **Confidence: MEDIUM.** Real EAU-ESPU guideline chapter retrieved live; **not** Türkiye-first. The
  emergency itself is owned by `base.life_threat`; this grounds the *intake question* only.

### S2 — EAU-ESPU Guidelines on Paediatric Urology — Monosymptomatic Nocturnal Enuresis (bedwetting)
- **guideline_id (proposed):** `EAU-ESPU-PAED-URO-MNE`
- **Publishing body:** European Association of Urology (EAU) / European Society for Paediatric
  Urology (ESPU)
- **Version / year:** online guideline chapter (2024/2025 update cycle) — exact edition to be pinned
- **URL:** https://uroweb.org/guidelines/paediatric-urology/chapter/monosymptomatic-nocturnal-enuresis-bedwetting
- **Verbatim (Definition):**
  > "Monosymptomatic nocturnal enuresis (NE), also known as bedwetting, is defined as an unvoluntary
  > nocturnal incontinence."
- **Verbatim (Recommendation, age):**
  > "Do not treat children less than five years of age in whom spontaneous cure is likely, but rather
  > inform the family about the involuntary nature, the high incidence of spontaneous resolution and
  > the fact that punishment will not help to improve the condition."
- **Verbatim (History):**
  > "Focused questions to differentiate monosymptomatic versus non-monosymptomatic, primary versus
  > secondary, comorbid factors, such as behavioural or psychological problems and sleep disorder
  > breathing, should be asked."
- **Verbatim (Voiding/drinking diary):**
  > "a two-day complete micturition and drinking diary, which records daytime bladder function and
  > drinking habits, will further exclude comorbid factors such as LUTS and polydipsia."
- **Verbatim (Bowel):**
  > "Specific attention should be paid regarding bowel movements as irregular bowel movements can
  > change the diagnosis."
- **Confidence: MEDIUM.** Real EAU-ESPU chapter retrieved live; not Türkiye-first. Grounds the
  bedwetting, daytime-LUTS and bowel intake questions (no urgency asserted).

### S3 — EAU-ESPU Guidelines on Paediatric Urology — Urinary Tract Infections in Children
- **guideline_id (proposed):** `EAU-ESPU-PAED-URO-UTI`
- **Publishing body:** European Association of Urology (EAU) / European Society for Paediatric
  Urology (ESPU)
- **Version / year:** online guideline chapter (2024/2025 update cycle) — exact edition to be pinned
- **URL:** https://uroweb.org/guidelines/paediatric-urology/chapter/urinary-tract-infections-in-children
- **Verbatim (Pyelonephritis / upper tract):**
  > "A diffuse pyogenic infection of the renal pelvis and parenchyma. The onset of pyelonephritis is
  > generally abrupt."
- **Verbatim (Signs & symptoms of upper-tract UTI):**
  > "Clinical signs and symptoms include fever (> 38°C), chills, costovertebral angle or flank pain,
  > and tenderness."
- **Verbatim (Neonates / infants):**
  > "Neonates with severe UTIs can present with non-specific symptoms, such as failure to thrive,
  > jaundice and hyperexcitability, even in the absence of a fever."
- **Verbatim (Common presenting symptoms):**
  > "The most common presenting symptoms for UTI include fever, vomiting, lethargy and/or
  > irritability."
- **Verbatim (Significance of febrile UTI — captured as a fragment):**
  > "Febrile UTIs … usually involve the upper tract … These are the UTIs of greatest interest in
  > terms of the risk of developing renal damage."
- **Confidence: MEDIUM (fragment LOW).** Real EAU-ESPU chapter retrieved live; the febrile-UTI
  "risk of renal damage" line was returned as a **fragment/table cell** and MUST be reconciled
  against the primary text before it grounds any wording. Not Türkiye-first.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots-only binding, leaf `atNNNN` paths **deferred** (`openehr_deferred_reason`, INT-032 / HB-C12);
nothing fabricated. The committed `.opt` pins the composition and the archetype **roots** only, with
**no at-code leaf nodes** — so each item binds to an archetype **root** and the specific leaf path is
**deferred**, never invented. Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL
archetype). All items capture the **parent/guardian's proxy report**.

| # | Proposed captured item (proxy report) | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the current complaint (onset/course) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Painful / burning urination — dysuria (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Fever accompanying urinary symptoms (S3, febrile UTI) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Daytime wetting / urgency / frequency (S2 daytime bladder function, LUTS) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Night-time bedwetting (S2 monosymptomatic NE) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Bowel habits / constipation (S2 bowel movements) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Sudden severe testicular/groin pain with nausea/vomiting (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Scrotal swelling / redness / testicle not felt in the sac (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Blood in the urine — haematuria (**NO SOURCE FOUND**) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Current medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 13 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine / `base.life_threat` only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 14 | **Antenatal / prenatal hydronephrosis or renal ultrasound finding (birth history)** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 14: the committed `.opt` exposes no antenatal/birth-history archetype root, so a prenatal
  hydronephrosis capture has **no export target today → export blocked (INT-041 posture)**; do not
  invent an at-code path. Clinician/architecture decision needed (candidate: INT-032 archetype
  addition).
- **PHQ-9 / GAD-7 not bound here.** Those are the *adult* consented-wellbeing screens; their
  paediatric applicability is age-dependent and out of scope for this urology proposal — no
  paediatric wellbeing instrument is asserted.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian (proxy)** about
*çocuğunuz*; one concern per question (invariant 2: one question per turn); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".**
No bare numerals appear (invariant 22); no emergency number or action script is spoken here — RED
action scripts belong to `base.life_threat` / triage, never to an intake question.

> Triage note for every red-flag-derived item: the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED for testicular torsion comes from `base.life_threat` with all three RED axes
> (route × register × location, invariant 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Renumbering, old → new — sections outside §3 still use the old numbers: Q1
unchanged · Q2 removed (duplicates base `hpi.onset_date` + `hpi.trajectory`) · Q3 → Q2 · Q5 → Q3 ·
Q4 → Q4 (moved after daytime wetting so that its gate, Q2 or Q3, is already answered) · Q6 → Q5 ·
Q7 → Q6 · Q8 → Q7 (sudden severe pain) + Q8 (nausea / vomiting, if Q7 yes) · Q9 → Q9 (swelling /
redness) + Q10 (testis not felt) · Q10 → Q11 (on hold, no source) · Q11 removed (duplicates base
`meds_confirmed`) · Q12 removed (duplicates base `allergies`).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün getiren temel şikâyet nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Painful / burning urination** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (UTI
presenting symptoms)
> "Çocuğunuz idrar yaparken yanma, ağrı ya da rahatsızlık hissediyor mu?"
gen: slot=idrarda_yanma; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Daytime wetting / frequency** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
(daytime bladder function; LUTS)
> "Çocuğunuz gündüzleri idrar kaçırıyor ya da çok sık tuvalete gidiyor mu?"
gen: slot=gunduz_idrar_kacirma; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Fever with urinary symptoms (if Q2 or Q3 yes)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S3 (febrile UTI usually involves the upper tract)
> "İdrar şikâyetleriyle birlikte çocuğunuzun ateşi de oluyor mu?"
gen: slot=idrar_sikayetiyle_ates; type=boolean; ask_if=idrarda_yanma == true || gunduz_idrar_kacirma == true
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)**; per S3 a febrile UTI "usually involve[s]
the upper tract" and carries "the risk of developing renal damage" (fragment — still needs
re-verification).

**Q5 — Night-time bedwetting** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (monosymptomatic
nocturnal enuresis; "less than five years … spontaneous cure is likely")
> "Çocuğunuz gece uykusunda altını ıslatıyor mu?"
gen: slot=gece_altini_islatma; type=boolean
CANDIDATE — clinician to approve wording. Note: per S2, below the age of five spontaneous resolution
is likely — the *age* threshold is a clinician judgement, not asserted here.

**Q6 — Bowel habits / constipation** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("Specific
attention should be paid regarding bowel movements")
> "Çocuğunuzun bağırsak alışkanlıklarında, örneğin kabızlık, bir sorun var mı?"
gen: slot=bagirsak_sorunu; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Sudden severe testicular / groin pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
> "Çocuğunuzun testis ya da kasık bölgesinde aniden başlayan şiddetli bir ağrı oldu mu?"
gen: slot=ani_siddetli_testis_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician
+ rules-engine confirmation — NOT authoritative)**; per S1, sudden severe pain with a vagal reaction is
typical for torsion, which "is a paediatric urological emergency" — the emergency is owned by
`base.life_threat`.

**Q8 — Nausea / vomiting with the pain (if Q7 yes)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 (vagal reaction with sudden severe pain)
> "Bu ağrıyla birlikte bulantı ya da kusma oldu mu?"
gen: slot=agriyla_bulanti_kusma; type=boolean; ask_if=ani_siddetli_testis_agrisi == true
CANDIDATE — clinician to approve wording.

**Q9 — Scrotal swelling / redness** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(acute-scrotum presentation)
> "Çocuğunuzun testis torbasında şişlik ya da kızarıklık fark ettiniz mi?"
gen: slot=testis_torbasi_sislik; type=boolean
CANDIDATE — clinician to approve wording. The sex gate the verifier asks for on Q9/Q10 is a clinical
value: clinician decision pending; no gate is authored here.

**Q10 — Testis not felt in the scrotum** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(acute-scrotum presentation)
> "Çocuğunuzun testislerinden birini torbada elle bulamadığınız oldu mu?"
gen: slot=testis_ele_gelmiyor; type=boolean
CANDIDATE — clinician to approve wording. Sex gate: clinician decision pending (as Q9).
Undescended-testis *referral timing* has **NO SOURCE FOUND** (§4); this captures the parent's
observation only.

**Q11 — Blood in the urine** · archetype: `OBSERVATION.symptom_sign.v1` · source: **NO SOURCE FOUND**
> "Çocuğunuzun idrarında kan ya da olağandışı bir renk fark ettiniz mi?"
gen: hold=no source found for a paediatric haematuria red flag; clinician must supply before serving
CANDIDATE — clinician to approve wording. **HOLD (verification §B); the text passes.** **NO SOURCE
FOUND** for a paediatric haematuria red-flag threshold — clinician must supply before any flag is
derived.

*(11 candidate questions; 2 red-flag-derived — Q4 (S3), Q7 (S1) — further EAU-grounded functional
items (Q2, Q3, Q5, Q6, Q8, Q9, Q10), one NO-SOURCE item on hold (Q11), plus general intake.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first primary source (T.C. Sağlık Bakanlığı protocol or Türk Çocuk Ürolojisi Derneği /
   Türk Üroloji Derneği guideline)** — the one Turkish-society document located (a 2016 Türk Üroloji
   Derneği "Çocuklarda Fonksiyonel İşeme Bozuklukları" certification PDF) returned as **non-extractable
   binary** on automated fetch, and only society/journal landing pages surfaced otherwise. **NO SOURCE
   FOUND (Türkiye-first verbatim) — clinician must supply** and reconcile every S1–S3 row against it.
2. **Febrile-UTI "risk of renal damage" line (S3)** — captured as a **fragment/table cell**, not a
   clean sentence. **Re-verify against the primary EAU-ESPU text** before it grounds any wording.
3. **Paediatric haematuria red-flag threshold** (gross vs microscopic; with/without pain; with
   trauma) — **NO SOURCE FOUND — clinician must supply**; Q10 captures it as history only.
4. **Undescended testis (cryptorchidism) referral / operative timing** — the 6–24-month window quoted
   on Turkish hospital pages is **not** a retrievable versioned guideline; Q9 captures the observation
   only. **NO SOURCE FOUND (versioned) — clinician must supply** (candidate: TÇÜD / EAU-ESPU).
5. **Nocturnal-enuresis age threshold** — S2 says spontaneous cure is likely below five years but the
   exact age at which evaluation/treatment begins is a **clinician judgement not asserted here**.
6. **Vesicoureteral reflux, antenatal hydronephrosis follow-up, and voiding-diary numeric norms** —
   no verbatim threshold retrieved; item 14 (antenatal finding) additionally has **no archetype root**
   → export blocked (INT-041 posture). **Clinician must supply.**
7. **EAU-ESPU exact edition / year and recommendation grades** — the chapters were retrieved as live
   online text without a pinned edition; **clinician to pin** the exact version/date for each
   `source` block.
8. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here; testicular torsion is owned by `base.life_threat`
   (invariant 7). **`packages/protocols/triage` + `base.life_threat` must supply**, with committed
   `source` snapshots, before anything compiles.
9. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032 /
   HB-C12); not fabricated. Antenatal finding (item 14) has **no archetype root** → export blocked
   (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 7** — testicular torsion (the acute scrotum) is left to `base.life_threat`; this proposal
  only feeds questions and neither extends nor relaxes that sibling set.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, addressed to the parent/guardian
  (proxy), B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in questions; the compiler must still expand any numeral before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate interim sources
  S1–S3 (EAU-ESPU) for that block but does not itself commit a snapshot, and flags the Türkiye-first
  primary as the required replacement.
- **HB-C1** — this pack awaits clinician sign-off; NOT served. `cocuk_urolojisi.yaml` is an L0 draft
  and is untouched.
