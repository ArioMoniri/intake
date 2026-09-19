# Algoloji (Pain Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Algoloji (Pain Medicine / Ağrı)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign
off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**,
  written as *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The
  guideline's own urgency wording is quoted verbatim; no level is asserted. The cauda-equina items
  in particular are known neurological emergencies whose authoritative RED (route × register ×
  location, invariant 21) must come from the rules engine, not from this file.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch/WebSearch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and, per the clinical-content rule, committed as
  a **verbatim source snapshot** with a full `source: {guideline_id, version, date, url,
  retrieved_on}` block. Until then any derived rule stays `status: draft_needs_source` and does
  **not** compile into a served pack.
- **No accuracy claims** (invariant 20): no sensitivity/specificity/AUROC figure is reproduced here,
  even where a source stated one.
- This file does **not** edit `packages/protocols/specialty/algoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG59 Low back pain and sciatica in over 16s (serious-pathology exclusion + cauda equina emergency)
- **guideline_id (proposed):** `NICE-NG59`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** NG59 — first published 2016, updated; the retrieved NCBI reprint header showed
  "December 11, 2020". **Exact publication/last-updated dates MUST be reconciled against nice.org.uk
  before sign-off** (see §4 gap).
- **Citation:** NICE. *Low back pain and sciatica in over 16s: assessment and management (NG59).*
- **URL:** https://www.nice.org.uk/guidance/ng59 · reprint: https://www.ncbi.nlm.nih.gov/books/NBK562933/
- **Verbatim (recommendation 1.1.1):**
  > "Think about alternative diagnoses when examining or reviewing people with low back pain,
  > particularly if they develop new or changed symptoms. Exclude specific causes of low back pain,
  > for example, cancer, infection, trauma or inflammatory disease such as spondyloarthritis."
- **Verbatim (scope / emergency note):**
  > "This guideline does not cover the evaluation or care of people with sciatica with progressive
  > neurological deficit or cauda equina syndrome. All clinicians involved in the management of
  > sciatica should be aware of these potential neurological emergencies and know when to refer to an
  > appropriate specialist."
- **Note:** NG59 names cancer/infection/trauma/inflammatory disease as things to exclude but refers
  the detailed cauda-equina / malignancy warning-sign lists out to other NICE guidance — those
  enumerated lists were **NOT** in the retrieved text (see §4 gaps 1–2).

### S2 — RCEMLearning "Acute Lower Back Pain" red-flag list (cites Kendrick, BMJ 2001)
- **guideline_id (proposed):** `RCEM-LBP` (education reference, **not** a versioned clinical guideline)
- **Publishing body:** Royal College of Emergency Medicine — RCEMLearning reference page
- **Underlying citation on the page:** Kendrick D, Fielding K, et al., *BMJ* 2001 (reference 3 on page)
- **URL:** https://www.rcemlearning.co.uk/reference/lower-back-pain/
- **Verbatim (History / Clinical Assessment red flags):**
  > "Onset at age <20 or >55"
  > "Thoracic pain – could be due to a thoracic aortic aneurysm"
  > "Weight loss – a constitutional symptom that raises the possibility of an underlying malignancy"
  > "Widespread neurological symptoms especially sphincter disturbance"
  > "Feeling generally unwell – consider underlying infection or malignancy"
- **Verbatim (malignancy indicators):**
  > "middle/thoracic spine pain, progressive lumbar pain, severe unrelenting pain, pain worsened by
  > straining, localized tenderness, and nocturnal pain disrupting sleep."
- **Confidence: MEDIUM.** A teaching reference, not a primary guideline; its own citation (BMJ 2001)
  should be retrieved and snapshotted before it grounds any rule. Numerals ("<20 or >55") are
  guideline-internal thresholds, not patient-facing text.

### S3 — WHO 2018 Cancer pain guidelines (pain assessment principles)
- **guideline_id (proposed):** `WHO-CANCERPAIN-2018`
- **Publishing body:** World Health Organization
- **Version / year:** 2018 (first update since 1996)
- **Citation:** WHO. *WHO Guidelines for the Pharmacological and Radiotherapeutic Management of
  Cancer Pain in Adults and Adolescents.* Geneva: WHO; 2018.
- **URL:** https://www.ncbi.nlm.nih.gov/books/NBK537483/
- **Verbatim (guiding principles — assessment):**
  > "The assessment should be as comprehensive as possible consistent with the patient's comfort and
  > should include a detailed history, physical examination, assessment of psychological
  > circumstances, an assessment of pain severity using an appropriate pain measurement tool and
  > indicated diagnostic procedures."
- **Verbatim (guiding principles — reassessment):**
  > "Assessment and re-assessment at regular intervals are key to ensuring that treatment is
  > appropriate and safe, as well as minimizing and addressing side-effects over the course of a
  > patient's care plan."
- **Use here:** grounds only the *pain-severity / interference* intake item (Q9). It is a
  management guideline, not a red-flag list — no urgency threshold is drawn from it.

### S4 — Türkçe kaynak: bel ağrısında kırmızı bayrak (Fizyodemi eğitim sayfası)
- **guideline_id (proposed):** `TR-LBP-REDFLAG-FIZYODEMI` (Turkish-language **education page**, NOT a
  versioned clinical guideline)
- **Publishing body:** Fizyodemi (fizyoterapi eğitim içeriği)
- **Version / year:** page dated 1 Ekim 2023
- **URL:** https://www.fizyodemi.com/bel-agrisinda-kirmizi-bayrak/
- **Verbatim (Türkçe, kırmızı bayrak bulguları):**
  > "Açıklanamayan kilo kaybı"
  > "Kanser öyküsü"
  > "Gece ağrısı"
  > "Eyer şeklinde anestezi"
  > "İdrar yapmakta zorluk"
  > "İlerleyici nörolojik defisit"
- **Verbatim (Türkçe, tanımlanan patolojiler):**
  > "Neoplastik sorunlar, enfeksiyon, kauda ekina sendromu ve travma (kırık) gibi patolojileri
  > düşündüren semptomlardır."
- **Confidence: LOW.** Single Turkish-language education page, not a versioned guideline. Türk
  Algoloji (Ağrı) Derneği (algoloji.org.tr) is the correct Türkiye-first candidate primary source
  but the specific page fetched returned HTTP 404 — **a versioned Türk Algoloji Derneği / T.C.
  Sağlık Bakanlığı primary document must replace or back this before any RED action script** (§4
  gap 4). Used here only to confirm that the Turkish-clinical vocabulary for these red flags exists
  (eyer anestezisi, kauda ekina, idrar yapmakta zorluk).

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` pins the composition and the archetype **roots** only, with **no at-code
(`atNNNN`) leaf nodes** (INT-041 refused to invent them; INT-032 held that line — see HB-C12). So
each item binds to an archetype **root**; the specific leaf path is **deferred**
(`openehr_deferred_reason`, INT-032), never fabricated.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the current pain complaint (story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Pain location / region | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Pain onset / duration / pattern | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Night pain / rest pain (S2, S4 red-flag context) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Unexplained weight loss / feeling generally unwell (S2, S4) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Bladder/bowel change or saddle (perineal) numbness — cauda equina (S1, S4) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Progressive leg weakness / numbness (S2 "sphincter disturbance"/neuro; S4 "ilerleyici nörolojik defisit") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Pain severity / interference with sleep & daily life (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Known diagnoses incl. cancer history (S2, S4 red-flag context) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current pain / analgesic medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Notes:
- All leaf `atNNNN` paths are **deferred** per INT-032 / HB-C12; none are invented.
- No item needs a family-history or provenance CLUSTER root here, so the INT-041 "export blocked"
  case (as seen in the cardiology proposal) does not arise for this set.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; one concern per question (invariant 2: one question per
turn); empathetic; no diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician
to approve wording".** Per invariant 22 no bare digit appears in the text; the protocol compiler
must expand any spelled numeral before TTS.

> Triage note for every red-flag-derived item: the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED/YELLOW must come from `packages/protocols/triage` with a committed `source`
> snapshot and all three RED axes (route × register × location, invariant 21), none supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü görüşmede sizi en çok rahatsız eden ağrı nedir? Kısaca anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Pain narrative (story)** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Ağrınızın ne zaman ve nasıl başladığını kendi sözlerinizle anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q3 — Pain location** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
> "Ağrıyı en çok vücudunuzun hangi bölgesinde hissediyorsunuz?"
CANDIDATE — clinician to approve wording.

**Q4 — Onset / duration / pattern** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
> "Bu ağrı ne kadar süredir devam ediyor ve gün içinde artıp azalıyor mu?"
CANDIDATE — clinician to approve wording.

**Q5 — Night / rest pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("nocturnal pain
disrupting sleep"), S4 ("Gece ağrısı")
> "Ağrınız geceleri ya da dinlenirken de oluyor mu, uykunuzu bölüyor mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: none by itself; contributes context to a
clinician-set red-flag pattern per S2/S4.

**Q6 — Weight loss / feeling unwell** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
("Weight loss …", "Feeling generally unwell …"), S4 ("Açıklanamayan kilo kaybı")
> "Son zamanlarda istemediğiniz halde kilo verdiniz mi ya da kendinizi genel olarak halsiz hissettiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** per S2 malignancy/infection wording.

**Q7 — Bladder/bowel or saddle numbness (cauda equina)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 (cauda equina emergency note), S4 ("Eyer şeklinde anestezi", "İdrar yapmakta zorluk")
> "Son günlerde idrarınızı ya da bağırsağınızı kontrol etmekte zorluk yaşadınız mı, ya da oturduğunuz bölgede uyuşma fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)**; this maps to a known neurological
emergency (S1), so the authoritative level and RED action script must be set by the rules engine.

**Q8 — Progressive leg weakness / numbness** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
("Widespread neurological symptoms especially sphincter disturbance"), S4 ("İlerleyici nörolojik defisit")
> "Bacaklarınızda giderek artan güçsüzlük ya da uyuşma hissediyor musunuz?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** per S2/S4.

**Q9 — Severity / interference** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (comprehensive
assessment incl. "assessment of pain severity using an appropriate pain measurement tool")
> "Ağrınız günlük işlerinizi, çalışmanızı ya da uykunuzu ne ölçüde etkiliyor?"
CANDIDATE — clinician to approve wording. Note: a validated pain-severity scale (e.g. an NRS) is a
clinician/instrument decision, not set here.

**Q10 — Known diagnoses / cancer history** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S2
/ S4 ("Kanser öyküsü")
> "Daha önce kanser ya da başka önemli bir hastalık tanısı aldınız mı?"
CANDIDATE — clinician to approve wording. Note: prior-cancer history is a documented red-flag
context (S2/S4); the level stays with the rules engine.

**Q11 — Current pain medications** · archetype: `ACTION.medication.v1` · source: general intake (S3
supports capturing current management)
> "Şu anda ağrınız için düzenli olarak kullandığınız ilaç var mı?"
CANDIDATE — clinician to approve wording.

**Q12 — Drug allergy / adverse reaction** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source:
general intake
> "Herhangi bir ilaca karşı alerjiniz ya da daha önce yaşadığınız kötü bir ilaç tepkiniz oldu mu?"
CANDIDATE — clinician to approve wording.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Enumerated cauda-equina warning-sign list from a NICE primary document** — NG59 (S1) names the
   syndrome as an emergency but refers the detailed sign list out to other guidance; that enumerated
   verbatim list was **NOT retrieved**. **NO SOURCE FOUND (primary/verbatim) — clinician must
   supply** (candidate: NICE spinal-cord-compression / suspected-cancer guidance, or a Turkish
   equivalent).
2. **Enumerated malignancy / infection / fracture red-flag set from a primary guideline** — S2 is a
   teaching reference citing BMJ 2001; the underlying BMJ paper and any current Türkiye-first primary
   were **NOT retrieved verbatim**. **NO SOURCE FOUND (primary/verbatim) — clinician must supply.**
3. **"When to seek urgent help / call emergency services" verbatim, Turkish** — no Türkiye-first
   authoritative sentence (e.g. T.C. Sağlık Bakanlığı) was retrieved for the cauda-equina / acute
   red-flag path. **NO SOURCE FOUND — clinician must supply** before any RED action script.
4. **Türk Algoloji (Ağrı) Derneği / T.C. Sağlık Bakanlığı versioned clinical guideline** — the
   Derneği site (algoloji.org.tr) exists but the target page returned HTTP 404; only a low-confidence
   education page (S4) was retrievable. **NO SOURCE FOUND (versioned primary) — clinician must
   supply** the correct Türkiye-first source with its version/date.
5. **Neuropathic-pain screening basis** (e.g. DN4 / painDETECT Turkish validation and licence
   status) — not researched or retrieved here; any neuropathic-specific item is out of scope until
   a licence-verified instrument is confirmed. **NO SOURCE FOUND — clinician must supply.**
6. **A validated Turkish pain-severity scale and its licence** (S3 requires "an appropriate pain
   measurement tool") — Q9 deliberately asks about interference in plain language and pins **no**
   scale. **NO SOURCE FOUND (licence-verified instrument) — clinician must supply.**
7. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must
   supply**, with committed `source` snapshots, before anything compiles.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032 / HB-C12); not fabricated.
9. **Exact NICE NG59 publication / last-updated dates** — the reprint header and search summaries
   disagreed; **clinician/curator must confirm** against nice.org.uk before the `source` block is
   committed.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine (cauda-equina items flagged as emergencies to be owned by triage rules).
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/
  prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 20** — no accuracy/performance figures reproduced.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare digits in patient text; compiler must expand any spelled numeral before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S4 for
  that block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
</content>
</invoke>
