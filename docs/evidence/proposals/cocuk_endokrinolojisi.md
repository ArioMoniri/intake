# Çocuk Endokrinolojisi (Paediatric Endocrinology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Endokrinolojisi (Paediatric
Endocrinology)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. Paediatric: every question is addressed to the
**parent/guardian (proxy)**. This file is a *proposal for a clinician to sign off*. It assigns **no**
authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Türkiye-first sourcing achieved for this specialty.** S1 and S2 are drawn verbatim from the
  **Çocuk Endokrinolojisi ve Diyabet Derneği (ÇEDD) 2026** guideline, published with the Türkiye
  Milli Pediatri Derneği — a genuine Turkish specialty-society source of exactly the kind files/09
  §2 names. S3 (NICE NG18) is an international named-body corroborator for the diabetes red flag.
- **Life-threatening endocrine emergencies stay in `base.life_threat` (invariant 7).** New-onset
  type-1 diabetes progressing to **diyabetik ketoasidoz (DKA)** and **adrenal kriz** are
  life-threatening; per invariant 7 the `base.life_threat` sibling set is authoritative and *nothing
  may extend it*. This proposal **only feeds intake questions** that surface the early symptoms for
  the clinician and the rules engine — it does **not** author, relax or duplicate any life-threat
  threshold.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**,
  written as *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The
  guideline's own wording is quoted verbatim; no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / PDF extraction). Before sign-off, each verbatim sentence MUST
  be re-checked against the **primary published text** and committed as a **verbatim source
  snapshot** with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then
  any derived rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_endokrinolojisi.yaml` (an L0 draft
  that never serves) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — ÇEDD 2026 — Çocukluk Çağında Diyabetik Ketoasidoz (Türkiye-first)
- **guideline_id (proposed):** `CEDD-2026-DKA`
- **Publishing body:** Çocuk Endokrinolojisi ve Diyabet Derneği (ÇEDD), with Türkiye Milli Pediatri
  Derneği — *Çocuk Sağlığı ve Hastalıklarında Tanı ve Tedavi Kılavuzları 2026*, Bölüm 7 "Çocukluk
  Çağında Diyabetik Ketoasidoz" (yazarlar: Prof. Dr. Hakan Döneray, Doç. Dr. Ayşe Özden).
- **Version / year:** 2026
- **URL:** https://millipediatri.org.tr/Custom/Upload/files/kilavuzlar/kilavuz-4.pdf
- **Verbatim (klinik öykü — DKA değerlendirme tablosu, s. 74):**
  > "Poliüri, polidipsi … Bulantı, kusma … Takipne, karın ağrısı, zayıflık … Kilo kaybı, konfüzyon …
  > Bilinç düzeyinde gerileme"
- **Verbatim (fizyopatoloji):**
  > "Sık ve bol miktarda idrara çıkma, osmotik diürezi düşündüren tipik bir bulgudur. Su kaybı ise
  > aşırı su içme (polidipsi) ile dengelenmeye çalışılır. Kandaki keton cisimleri kritik bir eşiği
  > geçtiğinde kusma ve şiddetli karın ağrısı ortaya çıkar."
- **Verbatim (neden — erken tanı):**
  > "Yeni tanı almış T1DM olgularında DKA gelişiminin başlıca nedeni, hastaların ve ailelerinin
  > hastalığın erken belirtilerine yeterince aşina olmamalarıdır. Bu grupta DKA'nın temel nedeni,
  > tanının gecikmesidir."
- **Confidence: MEDIUM-HIGH.** Türkiye-first society guideline retrieved as PDF and text-extracted;
  the "klinik öykü" list was captured from a management-algorithm table — reconcile the exact figure
  number against the primary text before sign-off.

### S2 — ÇEDD 2026 — Adrenal Yetmezliklere Acil Yaklaşım (Türkiye-first)
- **guideline_id (proposed):** `CEDD-2026-ADRENAL`
- **Publishing body:** Çocuk Endokrinolojisi ve Diyabet Derneği (ÇEDD) Adrenal Çalışma Grubu, with
  Türkiye Milli Pediatri Derneği — 2026 kılavuzu, Bölüm 1 "Adrenal Yetmezliklere Acil Yaklaşım"
  (yazarlar: Doç. Dr. Emine Çamtosun, Prof. Dr. Zeynep Şıklar).
- **Version / year:** 2026
- **URL:** https://millipediatri.org.tr/Custom/Upload/files/kilavuzlar/kilavuz-4.pdf
- **Verbatim (giriş):**
  > "Adrenal yetmezlik, tanı ve tedavisi geciktiğinde hayatı tehdit edebilen, adrenal bezlerden
  > kortizol salınımında yetersizliğe bağlı gelişen bir durumdur."
- **Verbatim (klinik bulgular):**
  > "Bu olgularda vücut ağırlığında azalma, halsizlik, yorgunluk, iştahsızlık, bulantı, kusma gibi
  > özgün olmayan semptomlar bulunabilir."
- **Verbatim (adrenal kriz):**
  > "Daha önce adrenal yetmezlik tanısı almış bir olguda, tedaviye uyumsuzluk varsa, adrenal kriz
  > gelişebileceği unutulmamalıdır."
- **Verbatim (stres durumu):**
  > "Stres durumlarında, içinde bulunulan koşulların gerektirdiği düzeyde, doz artırımları
  > yapılmadığında hastada adrenal kriz gelişebilir ve hızla tedavi edilmezse koma, hatta ölümle
  > sonuçlanabilir."
- **Confidence: MEDIUM-HIGH** (Türkiye-first society guideline; text-extracted — reconcile against
  primary before sign-off).

### S3 — NICE NG18 — Diabetes (type 1 and type 2) in children and young people (named-body corroborator)
- **guideline_id (proposed):** `NICE-NG18`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** NG18 (published 2015, updated; recommendations current)
- **URL:** https://www.nice.org.uk/guidance/ng18/chapter/Recommendations · mirror (retrieved):
  https://www.ncbi.nlm.nih.gov/books/NBK343420/
- **Verbatim (awareness of characteristics; NICE numbering ~1.1.1 — reconcile):**
  > "Be aware that the characteristics of type 1 diabetes in children and young people include:
  > hyperglycaemia (random plasma glucose more than 11 mmol/litre), polyuria, polydipsia, weight
  > loss, excessive tiredness."
- **Verbatim (same-day referral; NICE numbering ~1.1.2 — reconcile):**
  > "Refer children and young people with suspected type 1 diabetes immediately (on the same day) to
  > a multidisciplinary paediatric diabetes team with the competencies needed to confirm diagnosis
  > and to provide immediate care."
- **Note:** nice.org.uk returned HTTP 403 to automated fetch; the verbatim above was retrieved from
  the NCBI Bookshelf mirror. Recommendation numbers MUST be reconciled against the primary NICE page
  before sign-off. **Confidence: HIGH (content), MEDIUM (exact rec-number provenance).**

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
| 3 | Polyuria / more frequent urination (S1, S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Polydipsia / excessive thirst (S1, S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Weight loss (S1, S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Excessive tiredness (S3, S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Nausea / vomiting / abdominal pain (S1 DKA warning) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Known adrenal insufficiency on steroid replacement (S2) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 9 | Vomiting / unable to take usual medicine when unwell (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Puberty timing concern (ÇEDD 2026 §9 topic) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Current medications (insulin / steroid) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 13 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine / `base.life_threat` only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 14 | **Growth concern — height/weight/percentile (short stature, ÇEDD 2026 §8)** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 14: the committed `.opt` exposes **no anthropometry / growth archetype root** (no
  `OBSERVATION.height`, `.body_weight` or growth-percentile CLUSTER), so a numeric growth capture has
  **no export target today → export blocked (INT-041 posture)**; do not invent an at-code path. The
  *reason-for-visit* framing of a growth concern (Q10) still binds via
  `EVALUATION.reason_for_encounter.v1`, but the measured value does not. Clinician/architecture
  decision needed (candidate: INT-032 archetype addition).
- **Family history of autoimmune/endocrine disease** (e.g. type-1 diabetes, thyroid, adrenal) — as in
  the cardiology proposal, the committed `.opt` exposes no family-history archetype root → capturing
  it has **no export target → export blocked (INT-041 posture)**; not captured as a question here.
- **PHQ-9 / GAD-7 not bound here.** Those are the *adult* consented-wellbeing screens; paediatric
  applicability is age-dependent and out of scope for this endocrine red-flag proposal.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian (proxy)** about
*çocuğunuz*; one concern per question (invariant 2: one question per turn); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".**
No bare numerals appear (invariant 22); no emergency number or action script is spoken here — RED
action scripts belong to `base.life_threat` / triage, never to an intake question.

> Triage note for every red-flag-derived item: the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED for DKA / adrenal crisis comes from `base.life_threat` with all three RED axes
> (route × register × location, invariant 21), none of which are supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün getiren temel konu nedir? Kısaca anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Onset / course** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu durum ne zaman başladı ve o günden bu yana nasıl bir seyir izledi?"
CANDIDATE — clinician to approve wording.

**Q3 — Polyuria** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Poliüri … Sık ve bol
miktarda idrara çıkma") + S3 ("polyuria")
> "Çocuğunuz son zamanlarda her zamankinden daha sık ve daha bol idrara çıkıyor ya da yeniden altını
> ıslatmaya başladı mı?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** when combined with Q4/Q5, per S1/S3.

**Q4 — Polydipsia** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("polidipsi … aşırı su
içme") + S3 ("polydipsia")
> "Çocuğunuz alışılmadık şekilde çok su içiyor ya da sürekli susuyor mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**, per S1/S3.

**Q5 — Weight loss** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Kilo kaybı") + S3
("weight loss")
> "Çocuğunuz iyi beslenmesine rağmen son zamanlarda kilo kaybetti ya da zayıfladı mı?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**, per S1/S3.

**Q6 — Excessive tiredness** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("excessive
tiredness") + S1 ("halsizlik, zayıflık")
> "Çocuğunuz son zamanlarda alışılmadık şekilde yorgun ya da halsiz mi?"
CANDIDATE — clinician to approve wording.

**Q7 — Nausea / vomiting / abdominal pain (DKA warning)** · archetype: `OBSERVATION.symptom_sign.v1`
· source: S1 ("Kandaki keton cisimleri kritik bir eşiği geçtiğinde kusma ve şiddetli karın ağrısı
ortaya çıkar")
> "Bu belirtilere bulantı, kusma ya da karın ağrısı da eşlik ediyor mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**; per S1
these mark progression toward DKA — the emergency is owned by `base.life_threat`.

**Q8 — Known adrenal insufficiency / steroid treatment** · archetype:
`EVALUATION.problem_diagnosis.v1` · source: S2 (history)
> "Çocuğunuzun böbrek üstü bezi yetmezliği gibi bir tanısı ya da düzenli kullandığı bir kortizon
> (hidrokortizon) tedavisi var mı?"
CANDIDATE — clinician to approve wording.

**Q9 — Vomiting / unable to take medicine when unwell (adrenal-crisis risk)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S2 ("kusma … adrenal kriz")
> "Böyle bir tanısı varsa; şu anda kusuyor, ilacını alamıyor ya da belirgin şekilde halsiz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**; per S2
vomiting/non-adherence can precipitate adrenal crisis — the emergency is owned by `base.life_threat`.

**Q10 — Growth / puberty concern** · archetype: `EVALUATION.reason_for_encounter.v1` (growth measure
itself export-blocked, §2 item 14) · source: general intake (ÇEDD 2026 §8 "Boy kısalığı ve büyüme
geriliği" and §9 "Puberte" name these topics; no alarm threshold cited → general)
> "Çocuğunuzun boyu, büyümesi ya da ergenlik gelişimi yaşıtlarına göre sizi endişelendiriyor mu?"
CANDIDATE — clinician to approve wording.

**Q11 — Current medications** · archetype: `ACTION.medication.v1` · source: general intake (history)
> "Çocuğunuzun düzenli kullandığı ilaçlar (örneğin insülin ya da kortizon) var mı?"
CANDIDATE — clinician to approve wording.

**Q12 — Drug allergy** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: general intake
> "Çocuğunuzun bilinen bir ilaç alerjisi ya da ilaca karşı gelişmiş bir tepkisi var mı?"
CANDIDATE — clinician to approve wording.

*(12 candidate questions; 5 red-flag-derived — Q3, Q4, Q5, Q7, Q9 — plus general intake.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **T.C. Sağlık Bakanlığı primary protocol** — S1/S2 are Türkiye-first *society* (ÇEDD) sources, not
   a Bakanlık klinik protokolü. If files/09 §2 requires the MoH tier, **NO SOURCE FOUND (MoH) —
   clinician must supply**.
2. **ÇEDD table/figure reconciliation** — the S1 "klinik öykü" red-flag list was captured from a
   management-algorithm table via PDF text extraction; the exact figure number and page MUST be
   re-verified against the primary PDF, and a verbatim snapshot committed, before sign-off.
3. **NICE NG18 recommendation numbers** — content retrieved via the NCBI mirror (nice.org.uk 403 to
   automated fetch); the exact recommendation ids (≈1.1.1 / 1.1.2) **must be reconciled** against the
   primary NICE page.
4. **Congenital adrenal hyperplasia (CAH) neonatal presentation / salt-wasting crisis** — S2 covers
   adrenal crisis generally; a CAH-specific verbatim red flag (ambiguous genitalia, neonatal
   salt-wasting) was **NOT retrieved** verbatim. **NO SOURCE FOUND — clinician to supply** (candidate:
   ÇEDD CAH guideline / ESPE).
5. **Hypoglycaemia red flags** (ÇEDD 2026 §6 "Çocuklarda ve yenidoğanlarda hipoglisemiye yaklaşım"
   exists as a chapter but was not extracted verbatim) — **NO SOURCE FOUND (verbatim) — clinician to
   supply**.
6. **Thyroid emergency (thyroid storm) / goitre red flags** (ÇEDD 2026 §5 tiroid hastalıkları) — not
   extracted verbatim. **NO SOURCE FOUND (verbatim) — clinician to supply.**
7. **Short-stature / precocious-puberty referral thresholds** — Q10 captures the concern generically;
   no numeric threshold is asserted, and the growth measurement has no openEHR export target
   (§2 item 14). **NO SOURCE FOUND (threshold) — clinician to supply** (candidate: ÇEDD 2026 §8/§9).
8. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here; DKA and adrenal crisis are owned by `base.life_threat`
   (invariant 7). **`packages/protocols/triage` + `base.life_threat` must supply**, with committed
   `source` snapshots, before anything compiles.
9. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032); not fabricated. Growth measurement (item 14) and family history have **no archetype
   root** → export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 7** — life-threatening endocrine emergencies (DKA, adrenal crisis) are left to
  `base.life_threat`; this proposal only feeds questions and neither extends nor relaxes that sibling
  set.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, addressed to the parent/guardian
  (proxy), B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in questions; the compiler must still expand any numeral before TTS.
  (The verbatim S3 quote "more than 11 mmol/litre" is retained only inside the §1 source block, never
  in patient-facing copy.)
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies Türkiye-first candidate
  sources S1–S2 (ÇEDD 2026) and named-body corroborator S3 (NICE NG18) for that block but does not
  itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served. `cocuk_endokrinolojisi.yaml` is an L0
  draft and is untouched.
