# Çocuk Nefrolojisi (Paediatric Nephrology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Nefrolojisi (Paediatric
Nephrology)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. Paediatric: every question is addressed to the
**parent/guardian (proxy)**. This file is a *proposal for a clinician to sign off*. It assigns **no**
authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Türkiye-first sourcing achieved for this specialty.** S1 is drawn verbatim from the **Çocuk
  Nefroloji Derneği 2026** guideline, published with the Türkiye Milli Pediatri Derneği (*Çocuk
  Sağlığı ve Hastalıklarında Tanı ve Tedavi Kılavuzları 2026*) — a genuine Turkish specialty-society
  source of exactly the kind files/09 §2 names. S2 (IPNA 2022) and S3 (NICE NG224) are international
  named-body corroborators.
- **Life-threatening renal emergencies stay in `base.life_threat` (invariant 7).** **Akut böbrek
  hasarı (AKI)** with anuria/volume overload, and **hypertensive emergency** are life-threatening;
  per invariant 7 the `base.life_threat` sibling set is authoritative and *nothing may extend it*.
  This proposal **only feeds intake questions** that surface early symptoms for the clinician and the
  rules engine — it does **not** author, relax or duplicate any life-threat threshold.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's
  own wording is quoted verbatim; no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / PDF text extraction). Before sign-off, each verbatim sentence
  MUST be re-checked against the **primary published text** and committed as a **verbatim source
  snapshot** with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then
  any derived rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_nefrolojisi.yaml` (an L0 draft that
  never serves — `maturity: L0`, `status: generated-l0-awaiting-clinical-review`) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — Çocuk Nefroloji Derneği 2026 — Çocuklarda İdrar Yolu Enfeksiyonlarının Tanı ve Tedavisi (Türkiye-first)
- **guideline_id (proposed):** `CND-2026-IYE`
- **Publishing body:** Çocuk Nefroloji Derneği, with Türkiye Milli Pediatri Derneği — *Çocuk Sağlığı
  ve Hastalıklarında Tanı ve Tedavi Kılavuzları 2026*, "Çocuk Nefroloji Derneği Kılavuzu 2026", Bölüm
  1 "Çocuklarda İdrar Yolu Enfeksiyonlarının Tanı ve Tedavisi" (yazar: Dr. Alper Soylu, Dokuz Eylül
  Üniversitesi Tıp Fakültesi, Çocuk Nefroloji Bilim Dalı, İzmir).
- **Version / year:** 2026
- **URL:** https://millipediatri.org.tr/Custom/Upload/files/kilavuzlar/kilavuz-13.pdf
- **Verbatim (akut sistit — işeme semptomları):**
  > "Dizüri, sıkışma, suprapubik ağrı, idrar inkontinansı, kötü kokulu idrar gibi semptomlar ile
  > karakterizedir."
- **Verbatim (pyelonefrit / küçük çocukta ateş):**
  > "Pyelonefrit düşündüren bulgular karın ağrısı, yan ağrısı, ateş, halsizlik, bulantı, kusma ve
  > nadiren diyaredir. Ancak, küçük çocuklarda ateş tek bulgu olabilir."
- **Verbatim (yenidoğanda özgün olmayan belirtiler):**
  > "Yenidoğanlarda beslenme bozukluğu, huzursuzluk, sarılık ve kilo kaybı gibi İYE'ye özgü olmayan
  > semptomlar olabilir."
- **Verbatim (altta yatan üriner sistem patolojisine işaret):**
  > "İdrar yolu enfeksiyonu, mesane disfonksiyonu ve VUR gibi altta yatan bir üriner sistem
  > patolojisine işaret edebilir."
- **Verbatim (tekrarlayan enfeksiyon → skar/komplikasyon):**
  > "Tekrarlayan enfeksiyonlar da renal skar ve bununla ilişkili komplikasyonlara (hipertansiyon,
  > böbrek yetmezliği gibi) yol açabilir."
- **Verbatim (antenatal hidronefroz bölümü — karında kitle):**
  > "Fizik muayenede karında kitle olması obstrüktif üropati veya multikistik displastik böbrek
  > nedeniyle büyüyen böbreklerden kaynaklanabilir."
- **Confidence: MEDIUM-HIGH.** Türkiye-first society guideline retrieved as PDF and text-extracted;
  the exact section/figure numbers MUST be reconciled against the primary PDF before sign-off.

### S2 — IPNA 2022 — Steroid-sensitive nephrotic syndrome (named-body corroborator; oedema)
- **guideline_id (proposed):** `IPNA-SSNS-2022`
- **Publishing body:** International Pediatric Nephrology Association (IPNA)
- **Version / year:** 2022 (published in *Pediatric Nephrology*)
- **Citation:** *IPNA clinical practice recommendations for the diagnosis and management of children
  with steroid-sensitive nephrotic syndrome.* Pediatric Nephrology. 2022. DOI:
  10.1007/s00467-022-05739-3 · PMID: 36269406. (Full author list to be reconciled against the primary
  text before sign-off — see §4.)
- **URL:** https://theipna.org/wp-content/uploads/2023/01/IPNA.GL_.SSNS_.PedNeph22.pdf ·
  https://link.springer.com/article/10.1007/s00467-022-05739-3
- **Verbatim (introduction — defining features):**
  > "Idiopathic nephrotic syndrome (INS), characterized by massive proteinuria, hypoalbuminemia,
  > and/or concomitant edema is the most frequent glomerular disease in children."
- **Verbatim (Table 1 — definition of nephrotic syndrome):**
  > "Nephrotic-range proteinuria and either hypoalbuminemia (serum albumin < 30 g/L) or edema"
- **Verbatim (Table 1 — severe relapse requiring hospitalization):**
  > "A relapse requiring hospitalization due to one or more of the following: severe edema, …"
- **Confidence: HIGH (content), MEDIUM (author-list / exact-page provenance).** Retrieved as PDF and
  text-extracted; used only to ground the **oedema** intake item, not to assert any threshold.

### S3 — NICE NG224 — Urinary tract infection in under 16s (named-body corroborator)
- **guideline_id (proposed):** `NICE-NG224`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** NG224, published 27 July 2022
- **URL:** https://www.nice.org.uk/guidance/ng224 ·
  https://www.nice.org.uk/guidance/ng224/chapter/Recommendations
- **Retrieved (NICE overview, NOT verbatim recommendation text):** the guideline "covers diagnosing
  and managing … urinary tract infection (UTI) in babies, children and young people under 16" and
  names **dysuria, urinary frequency, loin tenderness and bedwetting** among the symptoms/signs that
  raise the likelihood of a UTI.
- **Note:** nice.org.uk returned **HTTP 403** to automated fetch; the sentence above is from the
  public NICE *overview* summary, **not** a verbatim recommendation. The verbatim symptom table and
  recommendation numbers **must be reconciled against the primary NICE page** before sign-off.
  **Confidence: MEDIUM (existence + topic), LOW (verbatim provenance).** S1 already supplies the
  Türkiye-first verbatim symptom set; S3 is corroboration only.

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
| 3 | Oedema / swelling — periorbital, face, legs (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Change in urine colour / visible blood in urine (haematuria) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Dysuria — pain/burning on passing urine (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Urinary frequency / new daytime or night wetting (S1, S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Fever with flank/abdominal pain (pyelonephritis pattern, S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Reduced urine output (feeds AKI gate — `base.life_threat`) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Known renal / urinary-tract diagnosis (VUR, hydronephrosis, nephrotic syndrome) (S1) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 10 | Current medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 11 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 12 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine / `base.life_threat` only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 13 | **Blood-pressure / growth measurement (hypertension, S1 complication)** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 13: the committed `.opt` exposes **no blood-pressure / anthropometry archetype root** (no
  `OBSERVATION.blood_pressure`, `.height`, `.body_weight`), so a numeric BP or growth capture has
  **no export target today → export blocked (INT-041 posture)**; do not invent an at-code path. The
  *reason-for-visit* framing of a blood-pressure concern can still bind via
  `EVALUATION.reason_for_encounter.v1`, but the measured value does not. Clinician/architecture
  decision needed (candidate: INT-032 archetype addition).
- **Family history of renal disease** (e.g. reflux, cystic kidney disease, dialysis/transplant) — as
  in the cardiology and endocrinology proposals, the committed `.opt` exposes no family-history
  archetype root → capturing it has **no export target → export blocked (INT-041 posture)**; not
  captured as a question here.
- **PHQ-9 / GAD-7 not bound here.** Those are the *adult* consented-wellbeing screens; paediatric
  applicability is age-dependent and out of scope for this nephrology red-flag proposal.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian (proxy)** about
*çocuğunuz*; one concern per question (invariant 2: one question per turn); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".**
No bare numerals appear (invariant 22); no emergency number or action script is spoken here — RED
action scripts belong to `base.life_threat` / triage, never to an intake question.

> Triage note for every red-flag-derived item: the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED for AKI / hypertensive emergency comes from `base.life_threat` with all three RED
> axes (route × register × location, invariant 21), none of which are supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün getiren temel konu nedir? Kısaca anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Onset / course** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu durum ne zaman başladı ve o günden bu yana nasıl bir seyir izledi?"
CANDIDATE — clinician to approve wording.

**Q3 — Oedema / swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("concomitant
edema" — defining feature of nephrotic syndrome)
> "Çocuğunuzun göz çevresinde, yüzünde, bacaklarında ya da karnında şişlik fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)**, per S2 (oedema with proteinuria =
nephrotic syndrome).

**Q4 — Urine colour change / visible blood (haematuria)** · archetype: `OBSERVATION.symptom_sign.v1`
· source: **NO SOURCE FOUND (verbatim red flag) — clinician must supply** (see §4; candidate: KDIGO
glomerülonefrit / Çocuk Nefroloji Derneği akut nefritik sendrom bölümü — not retrieved verbatim)
> "Çocuğunuzun idrarının rengi koyulaştı, kırmızı-kahverengi bir renk aldı ya da içinde kan
> gördünüz mü?"
CANDIDATE — clinician to approve wording. Candidate_flag: **not assigned** — no sourced threshold;
the concern is captured for the clinician, who must supply the acute-nephritic / macroscopic-
haematuria source before any flag.

**Q5 — Dysuria** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Dizüri … suprapubik ağrı")
> "Çocuğunuz idrar yaparken yanma, ağrı ya da rahatsızlık hissettiğini söylüyor mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)** with
Q6/Q7, per S1.

**Q6 — Urinary frequency / new wetting** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
("sıkışma … idrar inkontinansı") + S3 (frequency, bedwetting)
> "Çocuğunuz her zamankinden daha sık idrara çıkıyor, yeniden altını ıslatmaya başladı ya da idrarını
> tutmakta zorlanıyor mu?"
CANDIDATE — clinician to approve wording.

**Q7 — Fever with flank / abdominal pain (pyelonephritis pattern)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S1 ("Pyelonefrit düşündüren bulgular karın ağrısı, yan ağrısı,
ateş …")
> "Çocuğunuzda ateşle birlikte karın ya da yan (bel) ağrısı da var mı?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**; per S1
these suggest pyelonephritis (upper-tract infection).

**Q8 — Reduced urine output** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
(feeds the AKI gate — owned by `base.life_threat`; no threshold asserted here)
> "Çocuğunuzun idrar miktarı belirgin şekilde azaldı ya da neredeyse hiç idrar yapmıyor mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **not assigned** — reduced/absent urine
output feeds the acute-kidney-injury determination, which is owned by `base.life_threat` (invariant 7).

**Q9 — Known renal / urinary-tract diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` ·
source: S1 (VUR / underlying urinary-tract pathology; hydronephrosis chapter)
> "Çocuğunuzun daha önce böbrek ya da idrar yolu ile ilgili bir tanısı oldu mu? Örneğin idrar
> kaçağı (reflü), böbrekte genişleme ya da tekrarlayan idrar yolu enfeksiyonu."
CANDIDATE — clinician to approve wording.

**Q10 — Current medications** · archetype: `ACTION.medication.v1` · source: general intake (history)
> "Çocuğunuzun düzenli kullandığı ilaçlar var mı?"
CANDIDATE — clinician to approve wording.

**Q11 — Drug allergy** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: general intake
> "Çocuğunuzun bilinen bir ilaç alerjisi ya da ilaca karşı gelişmiş bir tepkisi var mı?"
CANDIDATE — clinician to approve wording.

*(11 candidate questions; 4 red-flag-derived — Q3, Q5, Q6, Q7 — plus Q4/Q8 concern-capture with no
sourced flag, and general intake.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Macroscopic (gross) haematuria red flag** — Q4 captures the concern, but neither S1 (a UTI +
   hydronephrosis guideline) nor S2 (IPNA SSNS) supplies a verbatim macroscopic-haematuria /
   acute-nephritic-syndrome red-flag sentence. **NO SOURCE FOUND (verbatim) — clinician must supply**
   (candidate: KDIGO Glomerülonefrit Klinik Uygulama Kılavuzu (Türkçe) / a Çocuk Nefroloji Derneği
   akut nefritik / post-streptokoksik glomerülonefrit bölümü).
2. **Nephrotic-syndrome onset red-flag as a Türkiye-first source** — S2 (IPNA) is used for the oedema
   item; a Türkiye-first (Çocuk Nefroloji Derneği) nefrotik sendrom bölümü was **not retrieved
   verbatim**. **NO SOURCE FOUND (Türkiye-first, verbatim) — clinician to supply.**
3. **IPNA author list / exact page provenance** — the S2 title, journal, year, DOI and PMID were
   retrieved, but the full author list and section/page for each quote **must be reconciled** against
   the primary text before a snapshot is committed.
4. **NICE NG224 verbatim symptom table + recommendation numbers** — nice.org.uk returned HTTP 403; the
   S3 symptom set (dysuria, frequency, loin tenderness, bedwetting) is from the NICE *overview*
   summary, not verbatim. **Must be reconciled** against the primary NICE page.
5. **T.C. Sağlık Bakanlığı primary protocol** — S1 is a Türkiye-first *society* (Çocuk Nefroloji
   Derneği / Milli Pediatri) source, not a Bakanlık klinik protokolü. If files/09 §2 requires the MoH
   tier, **NO SOURCE FOUND (MoH) — clinician must supply**.
6. **Paediatric hypertension threshold / hypertensive-emergency red flag** — S1 names hypertension as
   a *complication* of renal scarring but supplies no paediatric BP threshold; the BP measurement also
   has no openEHR export target (§2 item 13). **NO SOURCE FOUND (threshold) — clinician to supply**
   (candidate: Çocuk Nefroloji Derneği / ESH-ESC paediatric HT). Hypertensive emergency remains
   `base.life_threat` territory.
7. **Acute kidney injury (AKI) — anuria / volume-overload emergency** — Q8 feeds this as an input;
   the acute determination is owned by `base.life_threat` (invariant 7). No AKI threshold is asserted
   here.
8. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here; AKI and hypertensive emergency are owned by `base.life_threat`
   (invariant 7). **`packages/protocols/triage` + `base.life_threat` must supply**, with committed
   `source` snapshots, before anything compiles.
9. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032); not fabricated. Blood-pressure/growth measurement (item 13) and family history have **no
   archetype root** → export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 7** — life-threatening renal emergencies (AKI with anuria/volume overload, hypertensive
  emergency) are left to `base.life_threat`; this proposal only feeds questions and neither extends
  nor relaxes that sibling set.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, addressed to the parent/guardian
  (proxy), B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in questions; the compiler must still expand any numeral before TTS.
  (The verbatim S2 quote "serum albumin < 30 g/L" and the S1 "≥39°C" wording are retained only inside
  the §1 source block, never in patient-facing copy.)
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies Türkiye-first candidate
  source S1 (Çocuk Nefroloji Derneği 2026) and named-body corroborators S2 (IPNA 2022) / S3 (NICE
  NG224) for that block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served. `cocuk_nefrolojisi.yaml` is an L0 draft
  and is untouched.
