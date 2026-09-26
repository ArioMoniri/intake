# Diyabet polikliniği (Diabetes clinic) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Diyabet polikliniği (Diabetes clinic)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. Adult, addressed to the patient (self). This file is
a *proposal for a clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and
pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Türkiye-first sourcing achieved for this specialty.** S1 and S2 are drawn verbatim from the
  **TEMD (Türkiye Endokrinoloji ve Metabolizma Derneği) Diabetes Mellitus ve Komplikasyonlarının
  Tanı, Tedavi ve İzlem Kılavuzu — 2024** (16. Baskı), exactly the kind of Turkish specialty-society
  source files/09 names. S3 (NHS) is a named-body, patient-facing corroborator for the DKA red flag.
- **Life-threatening acute complications stay in `base.life_threat` (invariant 7).** **Diyabetik
  ketoasidoz (DKA)** and **ağır (ciddi) hipoglisemi** are life-threatening; per invariant 7 the
  `base.life_threat` sibling set is authoritative and *nothing may extend it*. This proposal **only
  feeds intake questions** that surface the early/warning symptoms for the clinician and the rules
  engine — it does **not** author, relax or duplicate any life-threat threshold, and it speaks no
  emergency action script.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's
  own wording is quoted verbatim; no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated PDF text-extraction / web retrieval. Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived
  rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/diyabet_poliklinigi.yaml` or any served
  pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — TEMD Diabetes Mellitus 2024 — classic diabetes symptoms + DKA/ketone warning (Türkiye-first)
- **guideline_id (proposed):** `TEMD-DM-2024`
- **Publishing body:** Türkiye Endokrinoloji ve Metabolizma Derneği (TEMD), Diyabet Bilimsel Çalışma
  Grubu
- **Version / year:** 16. Baskı (Çevrim içi), 2024 · Kasım 2024, Ankara · ISBN 978-625-99759-2-4
- **URL:** https://file.temd.org.tr/Uploads/publications/guides/documents/diabetesmellitus2024.pdf
- **Verbatim (TABLO 1.2: Diyabet semptomları — Klasik semptomlar):**
  > "Poliüri … Polidipsi … Polifaji veya iştahsızlık … Halsizlik, çabuk yorulma … Ağız kuruluğu …
  > Noktüri"
- **Verbatim (TABLO 1.2 — Daha az görülen semptomlar):**
  > "Bulanık görme … Açıklanamayan ağırlık kaybı … İnatçı enfeksiyonlar … Tekrarlayan mantar
  > enfeksiyonları … Kaşıntı"
- **Verbatim (keton bakılması — DKA warning):**
  > "Hiperglisemi semptomlarına bulantı, kusma, karın ağrısı ve ateş eşlik ettiğinde; ayrıca solukta
  > aseton kokusu hissedildiğinde ketona bakılmalıdır."
- **Confidence: MEDIUM-HIGH.** Türkiye-first society guideline retrieved as PDF and text-extracted;
  the symptom list was captured from Tablo 1.2 — reconcile the exact table/page number against the
  primary text and commit a verbatim snapshot before sign-off.

### S2 — TEMD Diabetes Mellitus 2024 — hypoglycaemia symptoms & classification (Türkiye-first)
- **guideline_id (proposed):** `TEMD-DM-2024` (§12.4 Hipoglisemi)
- **Publishing body / version / URL:** as S1 (same document, §12.4.1 "Tanı ve Klinik Bulgular")
- **Verbatim (hipoglisemi sınırı):**
  > "Amerikan Endokrin Cemiyeti (The Endocrine Society), Amerikan Diyabet Derneği (ADA) gibi
  > kuruluşlar diyabetli hastalar için hipoglisemi sınırının <70 mg/dL olarak kabul edilmesini
  > önermektedirler."
- **Verbatim (Adrenerjik / nörojenik belirti ve bulgular):**
  > "Titreme … Soğuk terleme … Anksiyete … Bulantı … Çarpıntı … Acıkma … Uyuşma"
- **Verbatim (Nöroglikopenik belirti ve bulgular):**
  > "Baş dönmesi … Baş ağrısı … Konsantre olamama … Konuşmada güçlük … Halsizlik … Konfüzyon"
- **Verbatim (ağır hipoglisemi — life-threat, belongs to `base.life_threat`):**
  > "Ağır hipoglisemi ise hastanın dışarıdan yardım almasını ve parenteral tedavi edilmesini
  > gerektiren ve komaya neden olabilen bir tablodur."
- **Note:** the "<70 mg/dL" numeral is kept **only inside this source block**; it never enters
  patient-facing copy (invariant 22). Ağır (ciddi) hipoglisemi is a life-threat owned by
  `base.life_threat` (invariant 7); the intake only surfaces the early adrenergic/neuroglycopenic
  symptoms. **Confidence: MEDIUM-HIGH** (text-extracted; reconcile before sign-off).

### S3 — NHS — Diabetic ketoacidosis (named-body, patient-facing corroborator)
- **guideline_id (proposed):** `NHS-DKA` (public patient-education page, NOT a versioned clinical
  guideline document)
- **Publishing body:** National Health Service (NHS, UK)
- **Version / year:** Page last reviewed 08 June 2023; next review due 08 June 2026
- **URL:** https://www.nhs.uk/conditions/diabetic-ketoacidosis/
- **Verbatim (symptoms):**
  > "Symptoms of diabetic ketoacidosis (DKA) include: feeling thirsty, needing to pee more often,
  > stomach pain, feeling sick or being sick, diarrhoea, breathing more deeply than usual, breath
  > that smells fruity (like pear drop sweets or nail polish remover), feeling tired, sleepy or
  > confused, blurred vision."
- **Verbatim (emergency action — life-threat, belongs to `base.life_threat`, NOT spoken in intake):**
  > "Call 999 or go to A&E if: … you do not know your ketone levels but have symptoms of diabetic
  > ketoacidosis, such as feeling thirsty and needing to pee more often, feeling sleepy or confused,
  > and breath that smells fruity …"
- **Confidence: LOW-MEDIUM.** Named-body but a public education page, not a versioned guideline;
  corroborates S1's DKA-warning cluster. The emergency ("Call 999 / A&E") action is a life-threat and
  is left to `base.life_threat` — it is quoted here for provenance only, never as an intake question.

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
| 3 | Polyuria / nocturia — passing more urine (S1 classic) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Polydipsia / dry mouth — excessive thirst (S1 classic) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Unexplained weight loss (S1 "Açıklanamayan ağırlık kaybı") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Fatigue / feeling easily tired (S1 "Halsizlik, çabuk yorulma") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Blurred vision (S1 "Bulanık görme") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Hypoglycaemia warning symptoms — shakiness/sweating/palpitation/hunger (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | DKA warning cluster — nausea/vomiting/abdominal pain/deep breathing/fruity breath (S1, S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Known diabetes diagnosis / type & duration | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current diabetes medications (insulin / oral agents) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 13 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine / `base.life_threat` only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 14 | **Family history of diabetes (first-degree)** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 14: the committed `.opt` exposes no family-history archetype root, so capturing family history
  of diabetes has **no export target today → export blocked (INT-041 posture)**; do not invent an
  at-code path. Clinician/architecture decision needed (candidate: INT-032 archetype addition).
- **PHQ-9 / GAD-7 not bound here.** Diabetes-distress / depression screening is clinically relevant
  (S1 §"Ruhsal durum değerlendirmesi" names it) but the consented-wellbeing instruments and their
  cut-offs are out of scope for this red-flag intake proposal; if consented they bind to
  `OBSERVATION.phq9.v1` / `OBSERVATION.gad7.v1` per the cardiology proposal.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the adult patient (self); one concern per
question (invariant 2: one question per turn); empathetic; no diagnosis/treatment/prognosis language.
**All marked "CANDIDATE — clinician to approve wording".** No bare numerals appear (invariant 22); no
emergency number or action script is spoken here — RED action scripts belong to `base.life_threat` /
triage, never to an intake question.

> Triage note for every red-flag-derived item: the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED for DKA / severe hypoglycaemia comes from `base.life_threat` with all three RED
> axes (route × register × location, invariant 21), none of which are supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü görüşmede sizi en çok rahatsız eden konu nedir? Kısaca anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Onset / course** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu durum ne zaman başladı ve o günden bu yana nasıl bir seyir izledi?"
CANDIDATE — clinician to approve wording.

**Q3 — Polyuria / nocturia** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Poliüri …
Noktüri")
> "Son zamanlarda her zamankinden daha sık idrara çıkıyor ya da gece idrara kalkıyor musunuz?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** when combined with Q4/Q5, per S1.

**Q4 — Polydipsia / dry mouth** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Polidipsi …
Ağız kuruluğu")
> "Alışılmadık şekilde çok su içiyor ya da ağzınızda kuruluk hissediyor musunuz?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**, per S1.

**Q5 — Unexplained weight loss** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
("Açıklanamayan ağırlık kaybı")
> "Beslenmenizde bir değişiklik olmadığı hâlde son zamanlarda kilo verdiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**, per S1.

**Q6 — Fatigue** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Halsizlik, çabuk yorulma")
> "Son zamanlarda alışılmadık şekilde halsiz ya da çabuk yoruluyor musunuz?"
CANDIDATE — clinician to approve wording.

**Q7 — Blurred vision** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Bulanık görme")
> "Gözlerinizde son zamanlarda bulanık görme fark ettiniz mi?"
CANDIDATE — clinician to approve wording.

**Q8 — Hypoglycaemia warning symptoms** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
(adrenerjik: "Titreme … Soğuk terleme … Çarpıntı … Acıkma")
> "Kan şekeriniz düştüğünde titreme, soğuk terleme, çarpıntı ya da ani açlık gibi belirtiler yaşıyor
> musunuz?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**, per S2;
**ağır (ciddi) hipoglisemi is a life-threat owned by `base.life_threat` (invariant 7)** — the intake
surfaces early symptoms only, never an emergency script.

**Q9 — DKA warning cluster** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Hiperglisemi
semptomlarına bulantı, kusma, karın ağrısı ve ateş eşlik ettiğinde …") + S3 (NHS DKA symptoms)
> "Bu belirtilere bulantı, kusma, karın ağrısı ya da derin ve hızlı nefes alma eşlik ediyor mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**; per S1/S3
this cluster warns of progression toward **DKA — the emergency is owned by `base.life_threat`**
(invariant 7), not by this intake.

**Q10 — Known diabetes diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general
intake (history)
> "Daha önce şeker hastalığı (diyabet) tanısı aldınız mı? Aldıysanız ne zamandır takip ediliyorsunuz?"
CANDIDATE — clinician to approve wording.

**Q11 — Current diabetes medications** · archetype: `ACTION.medication.v1` · source: general intake
(history)
> "Şu anda şekeriniz için düzenli kullandığınız ilaçlar (örneğin insülin ya da ağızdan alınan
> haplar) var mı?"
CANDIDATE — clinician to approve wording.

**Q12 — Drug allergy** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: general intake
> "Bilinen bir ilaç alerjiniz ya da bir ilaca karşı gelişmiş bir tepkiniz var mı?"
CANDIDATE — clinician to approve wording.

*(12 candidate questions; 5 red-flag-derived — Q3, Q4, Q5, Q8, Q9 — plus general intake.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **T.C. Sağlık Bakanlığı primary protocol** — S1/S2 are a Türkiye-first *society* (TEMD) source, not
   a Bakanlık klinik protokolü. A MoH-tier document exists as a candidate (TÜSEB/TÜHKE "Birinci
   Basamak Diyabet Eğitim Programı", files.tuseb.gov.tr) but was **not extracted verbatim**. **NO
   SOURCE FOUND (MoH verbatim) — clinician must supply.**
2. **NICE NG28 (type 2) / NG17 (type 1) verbatim** — nice.org.uk returned HTTP 403 to automated
   fetch; the NHS DKA page (S3) is a patient-education proxy, not the guideline itself. The NG28
   "sudden vision loss → urgent ophthalmology referral" recommendation and the NG17 DKA text were
   **not retrieved verbatim**. **NO SOURCE FOUND (NICE verbatim) — clinician to reconcile.**
3. **Hyperosmolar hyperglycaemic state (HHS) warning threshold** — S1 names "hiperozmolar
   hiperglisemik" acil among hyperglycaemic emergencies but the HHS-specific verbatim warning was
   **not extracted**. **NO SOURCE FOUND (verbatim) — clinician to supply.**
4. **Diabetic foot acute red flags** (new ulcer, spreading infection, acute hot/swollen foot /
   Charcot) — a diabetes-clinic-relevant red flag; **NOT retrieved** verbatim (candidate: NICE NG19 /
   TEMD diyabetik ayak). **NO SOURCE FOUND — clinician to supply.**
5. **Severe-hypoglycaemia and DKA numeric thresholds and emergency action scripts** — deliberately
   **not** authored here; they are life-threats owned by `base.life_threat` (invariant 7). The
   "<70 mg/dL" figure and the NHS "Call 999 / A&E" wording are quoted only in §1 for provenance.
   **`base.life_threat` + `packages/protocols/triage` must supply**, with committed `source`
   snapshots.
6. **TEMD table/page reconciliation** — the S1 classic-symptom list (Tablo 1.2) and the S2
   hypoglycaemia symptom lists (§12.4.1) were captured via PDF text extraction; the exact
   table/figure numbers and pages MUST be re-verified against the primary PDF and a verbatim snapshot
   committed before sign-off.
7. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must
   supply**, with committed `source` snapshots, before anything compiles.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032); not fabricated. Family history of diabetes (item 14) has **no archetype root** → export
   blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 7** — DKA and ağır (ciddi) hipoglisemi are left to `base.life_threat`; this proposal only
  feeds questions and neither extends nor relaxes that sibling set.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, adult self, B1, no
  diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in patient-facing questions; the verbatim "<70 mg/dL" (S2) is
  retained only inside the §1 source block, and the compiler must still expand any numeral before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies Türkiye-first candidate
  sources S1–S2 (TEMD-DM-2024) and named-body corroborator S3 (NHS) for that block but does not itself
  commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served. `diyabet_poliklinigi.yaml` (if present)
  is untouched.
