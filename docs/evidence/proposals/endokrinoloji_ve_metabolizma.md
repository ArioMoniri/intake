# Endokrinoloji ve Metabolizma (Endocrinology & Metabolism) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Endokrinoloji ve Metabolizma
(Endocrinology & Metabolism)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. Adult, addressed to the patient (self). This is a
broad medical specialty; this proposal covers the highest-yield endocrine presentations (thyroid,
adrenal, glucose/metabolic) and their warning symptoms. It is a *proposal for a clinician to sign
off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Türkiye-first sourcing achieved for this specialty.** S1 is drawn verbatim from the **TEMD
  (Türkiye Endokrinoloji ve Metabolizma Derneği) Tiroid Hastalıkları Tanı ve Tedavi Kılavuzu — 2025**
  and S3 from the **TEMD Diabetes Mellitus 2024** guideline — exactly the kind of Turkish
  specialty-society source files/09 names. S2 (NHS) is a named-body, patient-facing corroborator for
  the adrenal-crisis red flag.
- **Life-threatening endocrine emergencies stay in `base.life_threat` (invariant 7).** **Tiroid
  fırtınası (thyroid storm)**, **adrenal kriz** and **ağır (ciddi) hipoglisemi** are
  life-threatening; per invariant 7 the `base.life_threat` sibling set is authoritative and *nothing
  may extend it*. This proposal **only feeds intake questions** that surface early/warning symptoms
  for the clinician and the rules engine — it does **not** author, relax or duplicate any life-threat
  threshold, and speaks no emergency action script.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's
  own wording is quoted verbatim; no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated PDF text-extraction / web retrieval. Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived
  rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/endokrinoloji_ve_metabolizma.yaml` or any
  served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — TEMD Tiroid Hastalıkları 2025 — thyrotoxicosis / hypothyroidism symptoms + thyroid storm (Türkiye-first)
- **guideline_id (proposed):** `TEMD-TIROID-2025`
- **Publishing body:** Türkiye Endokrinoloji ve Metabolizma Derneği (TEMD), Tiroid Çalışma Grubu
- **Version / year:** 2025 · ISBN 978-625-95378-1-8
- **URL:** https://file.temd.org.tr/Uploads/publications/guides/documents/tiroid2025_11042025.pdf
- **Verbatim (Tablo 9.1 — Tirotoksikozun klinik bulguları):**
  > "Kalp hızında artış (Taşikardi) … Aritmiler (supraventriküler taşikardi, atrial fibrilasyon) …
  > Sıcak intoleransı … Terleme … Kilo kaybı … Sinirlilik, emosyonel labilite, hiperkinezi … İnce
  > tremor … Güçsüzlük, halsizlik … Göz kapağı retraksiyonu … Bağırsak hareketlerinde hızlanma …
  > Adet düzensizliği … Nefes darlığı"
- **Verbatim (Hipotiroidi belirti ve bulguları, s. 88):**
  > "Hipotiroidide görülen belirti ve bulgular hipotiroidiye özgü değildir. En sık görülenleri; cilt
  > kuruluğu, kolay üşüme, yorgunluk, seste değişiklik ve kabızlıktır."
- **Verbatim (tiroid nodülü — bası bulguları):**
  > "… nodülün hızlı büyümesi ve disfaji, disfoni, dispne, ses kısıklığı ve öksürük gibi bası
  > bulguları ile ilişkili olabilecek semptomlar …"
- **Verbatim (Tiroid Fırtınası — life-threat, belongs to `base.life_threat`):**
  > "Ciddi tirotoksikoz ve sistemik dekompensasyonu olan olgularda klinik olarak tanı konur."
  (Burch–Wartofsky puanlaması: vücut ısısı, taşikardi, AF ve kalp yetmezliği, GİS yakınmaları
  "bulantı, kusma, ishal, karaciğer yetmezliği", santral sinir sistemi "ajitasyon, delirium, stupor,
  koma"; "Mortalitesi %8-25 arası bildirilmektedir.")
- **Confidence: MEDIUM-HIGH.** Türkiye-first society guideline retrieved as PDF and text-extracted;
  reconcile the exact table/page numbers against the primary text and commit a verbatim snapshot
  before sign-off. Tiroid fırtınası is a life-threat owned by `base.life_threat` (invariant 7).

### S2 — NHS — Addison's disease / adrenal crisis (named-body, patient-facing corroborator)
- **guideline_id (proposed):** `NHS-ADDISON` (public patient-education page, NOT a versioned clinical
  guideline document)
- **Publishing body:** National Health Service (NHS, UK)
- **Version / year:** Page last reviewed 19 September 2025; next review due 19 September 2028
- **URL:** https://www.nhs.uk/conditions/addisons-disease/
- **Verbatim (adrenal crisis onset):**
  > "During adrenal crisis your symptoms get worse very quickly."
- **Verbatim (warning symptoms + emergency action — life-threat, belongs to `base.life_threat`, NOT spoken in intake):**
  > "Call 999 if: You have Addison's disease and the symptoms suddenly get worse or you: have a fast
  > heart rate, feel very dizzy or light-headed (particularly when standing up after sitting or lying
  > down), have severe tummy pain or pain in the side, have muscle weakness, pain or spasms, have a
  > headache that does not go away, feel sick (nausea) or vomit, feel very drowsy, irritable or
  > confused, have a seizure (fit), lose consciousness."
- **Verbatim (interpretation):**
  > "These could be signs of adrenal crisis."
- **Confidence: LOW-MEDIUM.** Named-body but a public education page, not a versioned guideline. The
  emergency ("Call 999") action is a life-threat left to `base.life_threat` (invariant 7) — quoted
  here for provenance only, never as an intake question. A Türkiye-first adrenal source (TEMD /
  Bakanlık) should replace/back this before sign-off.

### S3 — TEMD Diabetes Mellitus 2024 — hypoglycaemia symptoms (Türkiye-first, metabolic red flag)
- **guideline_id (proposed):** `TEMD-DM-2024` (§12.4 Hipoglisemi)
- **Publishing body:** Türkiye Endokrinoloji ve Metabolizma Derneği (TEMD), Diyabet Bilimsel Çalışma
  Grubu · 16. Baskı, Kasım 2024 · ISBN 978-625-99759-2-4
- **URL:** https://file.temd.org.tr/Uploads/publications/guides/documents/diabetesmellitus2024.pdf
- **Verbatim (Adrenerjik / nörojenik belirti ve bulgular):**
  > "Titreme … Soğuk terleme … Anksiyete … Bulantı … Çarpıntı … Acıkma … Uyuşma"
- **Verbatim (Nöroglikopenik belirti ve bulgular):**
  > "Baş dönmesi … Baş ağrısı … Konsantre olamama … Konuşmada güçlük … Halsizlik … Konfüzyon"
- **Verbatim (ağır hipoglisemi — life-threat, belongs to `base.life_threat`):**
  > "Ağır hipoglisemi ise hastanın dışarıdan yardım almasını ve parenteral tedavi edilmesini
  > gerektiren ve komaya neden olabilen bir tablodur."
- **Confidence: MEDIUM-HIGH** (Türkiye-first society guideline; text-extracted — reconcile against
  primary before sign-off). Ağır (ciddi) hipoglisemi is a life-threat owned by `base.life_threat`
  (invariant 7); the intake surfaces early adrenergic/neuroglycopenic symptoms only.

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
| 3 | Unexplained weight change — loss or gain (S1 hyper/hypo) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Heat vs cold intolerance (S1 "Sıcak intoleransı" / "kolay üşüme") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Palpitations / rapid heartbeat (S1 "Taşikardi") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Tremor / nervousness (S1 "İnce tremor … Sinirlilik") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Fatigue / feeling easily tired (S1 hypo "yorgunluk"; hyper "halsizlik") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Neck swelling / difficulty swallowing or hoarse voice (S1 "bası bulguları") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Known adrenal insufficiency on steroid + now unwell/vomiting (S2) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 10 | Hypoglycaemia warning symptoms — shakiness/sweating/palpitation/confusion (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Current medications (thyroid drug / steroid / insulin) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 13 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine / `base.life_threat` only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 14 | **Family history of endocrine/autoimmune disease (thyroid, MEN, diabetes)** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 14: the committed `.opt` exposes no family-history archetype root (S1 explicitly records
  taking "tiroid hastalıklarına ait aile hikayesi" and cancer-syndrome history), so capturing it has
  **no export target today → export blocked (INT-041 posture)**; do not invent an at-code path.
  Clinician/architecture decision needed (candidate: INT-032 archetype addition).
- **Anthropometry / goitre size measurement** — a measured neck-mass size or weight has no numeric
  archetype root bound in the shallow `.opt` (same posture as the paediatric-endocrinology proposal's
  growth item) → the measured value is **export blocked (INT-041 posture)**; only the *reason-for-visit*
  framing (Q8) binds, via `symptom_sign` / `reason_for_encounter`.
- **PHQ-9 / GAD-7 not bound here.** Those consented-wellbeing screens are out of scope for this
  endocrine red-flag proposal; if consented they bind to `OBSERVATION.phq9.v1` / `OBSERVATION.gad7.v1`.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the adult patient (self); one concern per
question (invariant 2: one question per turn); empathetic; no diagnosis/treatment/prognosis language.
**All marked "CANDIDATE — clinician to approve wording".** No bare numerals appear (invariant 22); no
emergency number or action script is spoken here — RED action scripts belong to `base.life_threat` /
triage, never to an intake question.

> Triage note for every red-flag-derived item: the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED for thyroid storm / adrenal crisis / severe hypoglycaemia comes from
> `base.life_threat` with all three RED axes (route × register × location, invariant 21), none of
> which are supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü görüşmede sizi en çok rahatsız eden konu nedir? Kısaca anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Onset / course** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu durum ne zaman başladı ve o günden bu yana nasıl bir seyir izledi?"
CANDIDATE — clinician to approve wording.

**Q3 — Unexplained weight change** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Kilo
kaybı" hipertiroidi / "kilo alma" hipotiroidi)
> "Beslenmenizde belirgin bir değişiklik olmadığı hâlde son zamanlarda kilo verdiniz ya da kilo
> aldınız mı?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)**, per S1.

**Q4 — Heat / cold intolerance** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Sıcak
intoleransı" / "kolay üşüme")
> "Son zamanlarda sıcağa ya da soğuğa karşı alışılmadık şekilde duyarlı hâle geldiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**, per S1.

**Q5 — Palpitations** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Kalp hızında artış
(Taşikardi)")
> "Kalbinizin hızlı ya da düzensiz çarptığını fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**, per S1.

**Q6 — Tremor / nervousness** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("İnce tremor …
Sinirlilik, emosyonel labilite")
> "Ellerinizde ince bir titreme ya da alışılmadık bir gerginlik, huzursuzluk hissediyor musunuz?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**, per S1.

**Q7 — Fatigue** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (hipotiroidi "yorgunluk";
hipertiroidi "Güçsüzlük, halsizlik")
> "Son zamanlarda alışılmadık şekilde yorgun ya da halsiz mi hissediyorsunuz?"
CANDIDATE — clinician to approve wording.

**Q8 — Neck swelling / compression** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("nodülün
hızlı büyümesi ve disfaji, disfoni, dispne, ses kısıklığı … bası bulguları")
> "Boynunuzda bir şişlik ya da yutkunurken zorlanma, ses kısıklığı fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**, per S1
(rapidly enlarging neck mass with compressive symptoms).

**Q9 — Known adrenal insufficiency / steroid + now unwell** · archetype:
`EVALUATION.problem_diagnosis.v1` · source: S2 (adrenal crisis warning)
> "Böbrek üstü bezi yetmezliği tanınız ya da düzenli kullandığınız bir kortizon (hidrokortizon)
> tedaviniz var mı; varsa şu anda kusuyor ya da belirgin şekilde halsiz misiniz?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**; per S2
vomiting/inability to take steroid can precipitate **adrenal crisis — the emergency is owned by
`base.life_threat`** (invariant 7), not by this intake.

**Q10 — Hypoglycaemia warning symptoms** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3
(adrenerjik: "Titreme … Soğuk terleme … Çarpıntı"; nöroglikopenik: "Konfüzyon")
> "Açlık hâlinde ya da öğün atladığınızda titreme, soğuk terleme, çarpıntı ya da zihinsel bulanıklık
> yaşıyor musunuz?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**, per S3;
**ağır (ciddi) hipoglisemi is a life-threat owned by `base.life_threat`** (invariant 7).

**Q11 — Current medications** · archetype: `ACTION.medication.v1` · source: general intake (history)
> "Şu anda düzenli kullandığınız ilaçlar (örneğin tiroid ilacı, kortizon ya da insülin) var mı?"
CANDIDATE — clinician to approve wording.

**Q12 — Drug allergy** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: general intake
> "Bilinen bir ilaç alerjiniz ya da bir ilaca karşı gelişmiş bir tepkiniz var mı?"
CANDIDATE — clinician to approve wording.

*(12 candidate questions; 6 red-flag-derived — Q3, Q4, Q5, Q6, Q8, Q9, Q10 feed thyroid/adrenal/
hypoglycaemia gates — plus general intake.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **T.C. Sağlık Bakanlığı primary protocol** — S1/S3 are Türkiye-first *society* (TEMD) sources, not
   a Bakanlık klinik protokolü; S2 is an NHS patient-education proxy, not a Turkish adrenal guideline.
   **NO SOURCE FOUND (MoH / Türkiye-first adrenal) — clinician must supply.**
2. **Adrenal crisis — Türkiye-first verbatim** — the adrenal-crisis warning cluster is sourced only
   from NHS (S2). A TEMD/Bakanlık adrenal-yetmezlik verbatim was **not retrieved**. **NO SOURCE FOUND
   (Türkiye-first) — clinician to supply** (candidate: TEMD Adrenal / Hipofiz kılavuzu).
3. **Pituitary emergencies (pituitary apoplexy: sudden severe headache + visual disturbance) and
   hypercalcaemic crisis / hyperparathyroidism red flags** — endocrine emergencies not retrieved
   verbatim (S1 lists "Hiperkalsemi" only as a thyrotoxicosis sign). **NO SOURCE FOUND — clinician to
   supply.**
4. **Phaeochromocytoma paroxysm (headache + palpitations + sweating triad)** — a metabolic/endocrine
   red flag overlapping Q5/Q6 but not sourced as a distinct verbatim cluster. **NO SOURCE FOUND —
   clinician to supply.**
5. **Thyroid-storm, adrenal-crisis and severe-hypoglycaemia numeric thresholds and emergency action
   scripts** — deliberately **not** authored here; they are life-threats owned by `base.life_threat`
   (invariant 7). The "%8-25" mortality figure and the NHS "Call 999" wording are quoted only in §1
   for provenance. **`base.life_threat` + `packages/protocols/triage` must supply**, with committed
   `source` snapshots.
6. **TEMD table/page reconciliation** — S1 lists (Tablo 9.1 thyrotoxicosis; s. 88 hypothyroidism;
   nodül bası bulguları) and the S3 hypoglycaemia lists (§12.4.1) were captured via PDF text
   extraction; exact table/figure numbers and pages MUST be re-verified against the primary PDFs and
   verbatim snapshots committed before sign-off.
7. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must
   supply**, with committed `source` snapshots, before anything compiles.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032); not fabricated. Family history (item 14) and any goitre/weight measurement have **no
   archetype root** → export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 7** — thyroid storm, adrenal crisis and ağır (ciddi) hipoglisemi are left to
  `base.life_threat`; this proposal only feeds questions and neither extends nor relaxes that sibling
  set.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, adult self, B1, no
  diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in patient-facing questions; the verbatim "%8-25" (S1) is retained
  only inside the §1 source block, and the compiler must still expand any numeral before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies Türkiye-first candidate
  sources S1 (TEMD-TIROID-2025) and S3 (TEMD-DM-2024) and named-body corroborator S2 (NHS) for that
  block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
  `endokrinoloji_ve_metabolizma.yaml` (if present) is untouched.
