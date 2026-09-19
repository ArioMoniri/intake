# Çocuk Nörolojisi (Paediatric Neurology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Nörolojisi (Paediatric
Neurology)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. Paediatric: every question is addressed to the
**parent/guardian (proxy)**. This file is a *proposal for a clinician to sign off*. It assigns **no**
authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Türkiye-first sourcing achieved for this specialty.** S1 is drawn verbatim from the **Türkiye
  Çocuk Nörolojisi Derneği** guideline, published with the Türkiye Milli Pediatri Derneği (*Çocuk
  Sağlığı ve Hastalıklarında Tanı ve Tedavi Kılavuzları*) — a genuine Turkish specialty-society source
  of exactly the kind files/09 §2 names. S2 (NICE NG217) is an international named-body corroborator.
- **Life-threatening neurological emergencies stay in `base.life_threat` (invariant 7).** **Status
  epileptikus** (a prolonged / non-stopping seizure) and the **meningitis pattern** (headache with
  fever ± neck stiffness) are life-threatening; per invariant 7 the `base.life_threat` sibling set is
  authoritative and *nothing may extend it*. This proposal **only feeds intake questions** that surface
  early symptoms for the clinician and the rules engine — it does **not** author, relax or duplicate
  any life-threat threshold. Overlap is catalogued in §2.1.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's
  own wording is quoted verbatim; no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / PDF text extraction). Before sign-off, each verbatim sentence
  MUST be re-checked against the **primary published text** and committed as a **verbatim source
  snapshot** with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then
  any derived rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_norolojisi.yaml` (an L0 draft that
  never serves — `maturity: L0`, `status: generated-l0-awaiting-clinical-review`) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — Türkiye Çocuk Nörolojisi Derneği — Çocuk Nörolojisi Kılavuzu (Türkiye-first)
- **guideline_id (proposed):** `TCND-KILAVUZ` (multi-chapter; per-chapter sub-ids below)
- **Publishing body:** Türkiye Çocuk Nörolojisi Derneği, with Türkiye Milli Pediatri Derneği — *Çocuk
  Sağlığı ve Hastalıklarında Tanı ve Tedavi Kılavuzları* (bölüm yazarları: Prof. Dr. Semra Hız, Doç.
  Dr. Uluç Yiş, Doç. Dr. Nihal Olgaç Dündar; Prof. Dr. Şenay Haspolat; Prof. Dr. Sarenur Gökben,
  Prof. Dr. Gül Serdaroğlu, Prof. Dr. Muzaffer Polat, Doç. Dr. Ayşe Tosun; Prof. Dr. Kürşat Aydın,
  Prof. Dr. Ayşe Serdaroğlu, Doç. Dr. Tuğba Hirfanoğlu, Doç. Dr. Ebru Arhan).
- **Version / year:** to be reconciled (this collection was created 2014 and updated 2026 — see §4).
- **URL:** https://millipediatri.org.tr/Custom/Upload/files/kilavuzlar/kilavuz-7.pdf

- **S1a — Febril Konvülziyon (`TCND-FK`) — verbatim (tanım):**
  > "… tanımlanmış bir neden ve öncesinde afebril konvülziyon öyküsü olmadan ateşle birlikte ortaya
  > çıkan nöbetlerdir."
- **S1a — verbatim (basit vs komplike):**
  > "Basit febril konvülziyon; 15 dakikadan kısa süren, 24 saat içinde tekrarlamayan jeneralize tipte
  > nöbet olarak tanımlanır."
  > "Konvülziyonun 10-15 dakika ve daha uzun sürmesi, nöbetin fokal olması ve aynı hastalık süresince
  > birden fazla görülmesi komplike febril konvülziyon kriterleridir."
- **S1a — verbatim (yaş):**
  > "En sık görülme yaşı 6 ay-3 yaş arası olup 18. ayda pik yapmaktadır."

- **S1b — Çocukluk Çağı Başağrıları (`TCND-BAS`) — verbatim (yaş ve ciddiyet):**
  > "Çocuğun yaşı ne kadar küçükse başağrısının ciddi bir nedeni olma olasılığı o kadar yüksektir."
- **S1b — verbatim (uyarıcı belirti → görüntüleme):**
  > "Ciddi başağrısı için uyarıcı belirti ve bulgular dikkatle değerlendirilmeli ve bu durumlarda
  > görüntüleme yapılmalıdır."
- **S1b — verbatim (fizik muayenede alarm bulguları):**
  > "Fizik muayenede ateş, hipertansiyon, deri döküntü ve lekeleri, meningeal irritasyon işaretleri,
  > papil stazı, nörolojik kusurlar ve kafa travması izleri özellikle akut ve ilerleyici
  > başağrılarında nedeni belirlemeye yardımcıdır."
- **S1b — verbatim (ikincil/organik başağrısı nedenleri):**
  > "Çocukluk çağında en sık ikincil başağrısı nedenleri ekstrakraniyal ve intrakraniyal
  > enfeksiyonlar, travma, vasküler bozukluklar, hidrosefali ve neoplaziler … epileptik
  > bozukluklardır."

- **S1c — Motor Gelişim Geriliği (`TCND-MGG`) — verbatim (öykünün önceliği):**
  > "İnce ve kaba motor gelişim geriliği dahil olmak üzere genel gelişim geriliği riski taşıyan süt
  > çocuklarının saptanmasında en erken ve en iyi bilgi öyküden elde edilir."
- **S1c — verbatim (nörolojik muayene uyarıcı bulguları):**
  > "Nörolojik muayenede, göz teması kurmama, obje takibinin yeterli olmaması, ışığa tepkisizlik …
  > kraniyal sinirlerin patolojilerini düşündürür."

- **S1d — Status Epileptikus (`TCND-SE`) — verbatim (tanım; EMERGENCY → base.life_threat):**
  > "Status epileptikus (SE), klinik veya elektrografik olarak tanımlanmış epileptik nöbetin, 30
  > dakikadan daha uzun sürmesi veya aralarda bilinç açılmaksızın 30 dakikadan uzun süreyle
  > tekrarlayan nöbetlerin görülmesi olarak kabul edilmektedir."
- **S1d — verbatim (erken sonlandırma gereği):**
  > "… jeneralize tonik-klonik nöbetlerde 5-10 dk. içerisinde kendiliğinden durmayan nöbetlerin SE'
  > ye dönüşme ihtimalinin çok yüksek olduğu bilinmelidir."

- **Confidence: MEDIUM-HIGH.** Türkiye-first society guideline retrieved as PDF and text-extracted;
  the exact edition year, chapter/figure numbers and page for each quote MUST be reconciled against
  the primary PDF before sign-off (see §4).

### S2 — NICE NG217 — Epilepsies in children, young people and adults (named-body corroborator)
- **guideline_id (proposed):** `NICE-NG217`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** NG217, 2022 (updated 2025)
- **URL:** https://www.nice.org.uk/guidance/ng217/chapter/1-Diagnosis-and-assessment-of-epilepsy
- **Verbatim (Rec ~1.1.1 — first suspected seizure, urgent referral):**
  > "Refer children, young people and adults urgently (for an appointment within 2 weeks) for an
  > assessment after a first suspected seizure."
- **Note:** this verbatim was previously retrieved in-repo (see `docs/evidence/proposals/noroloji.md`
  S4) via the NCBI Bookshelf route because nice.org.uk returns HTTP 403 to automated fetch; the exact
  recommendation number **must be reconciled** against the primary NICE page. **Confidence: HIGH
  (content), MEDIUM (exact rec-number provenance).** The "within 2 weeks" window is a *service
  referral* window quoted verbatim, not a patient-facing cut-off.

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
| 3 | Seizure / convulsion episode (S1a, S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Fever with the seizure (febrile-convulsion pattern) (S1a) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Headache — recent onset / acute or progressive (S1b) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Headache with fever (feeds meningitis gate — `base.life_threat`) (S1b) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Developmental concern — not reaching / losing milestones (S1c) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Known neurological diagnosis (epilepsy, cerebral palsy) (S1) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 9 | Current medications (incl. antiseizure) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 10 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 11 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine / `base.life_threat` only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 12 | **Head circumference / growth measurement (S1c developmental work-up)** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 12: the committed `.opt` exposes **no anthropometry archetype root** (no
  `OBSERVATION.head_circumference`, `.height`, `.body_weight`), so a numeric growth/head-circumference
  capture has **no export target today → export blocked (INT-041 posture)**; do not invent an at-code
  path. Clinician/architecture decision needed (candidate: INT-032 archetype addition).
- **Family history of epilepsy / neurological disease** — as in the cardiology and endocrinology
  proposals, the committed `.opt` exposes no family-history archetype root → capturing it has **no
  export target → export blocked (INT-041 posture)**; not captured as a question here (S1a notes
  familial transmission of febrile convulsion, so a clinician may want it later).
- **PHQ-9 / GAD-7 not bound here.** Those are the *adult* consented-wellbeing screens; paediatric
  applicability is age-dependent and out of scope for this neurology red-flag proposal.

### 2.1 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

`files/protocols/base.life_threat.yaml` is a branch-independent sibling set (`served: false`,
`maturity: L0`, HB-C1 sign-off empty). These paediatric neurology alarm signs are **its** territory,
not this pack's — this proposal must not, and does not, add or extend them:

| Neurology alarm sign | base.life_threat territory | This proposal's role |
|---|---|---|
| Status epilepticus / prolonged (non-stopping) seizure (S1d: "30 dakikadan daha uzun"; GTC "5-10 dk. içerisinde kendiliğinden durmayan") | active/prolonged-seizure life-threat rule | Q3/Q4 provide the seizure-episode intake as a gate **input** only |
| Headache with fever ± neck stiffness (S1b: "meningeal irritasyon işaretleri") | `rf.meningitis_pattern` (named in base.life_threat) | Q6 provides fever-with-headache intake as a gate **input** only |
| Paediatric airway / choking (the one drafted paediatric exemplar) | `rf.paediatric_airway_obstruction` | out of scope for this neurology set |

**Consequence:** for the emergency-grade signs above, the intake questions here may at most emit a
`candidate_flag`. The authoritative acute determination (RED, register, location, 112/acil routing)
is made by the rules engine / `base.life_threat` after a **named paediatrician** signs HB-C1 and each
`draft_needs_source` rule is sourced. Nothing in this file is a substitute for that.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian (proxy)** about
*çocuğunuz*; one concern per question (invariant 2: one question per turn); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".**
No bare numerals appear (invariant 22); no emergency number or action script is spoken here — RED
action scripts belong to `base.life_threat` / triage, never to an intake question.

> Triage note for every red-flag-derived item: the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED for status epilepticus / meningitis comes from `base.life_threat` with all three
> RED axes (route × register × location, invariant 21), none of which are supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün getiren temel konu nedir? Kısaca anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Onset / course** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu durum ne zaman başladı ve o günden bu yana nasıl bir seyir izledi?"
CANDIDATE — clinician to approve wording.

**Q3 — Seizure / convulsion episode** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1a
(febril konvülziyon tanımı) + S2 (NG217 first suspected seizure)
> "Çocuğunuz bilincini kaybettiği ya da vücudunda istemsiz kasılma-titreme olan bir atak (nöbet)
> geçirdi mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** — per S2 a first suspected seizure
warrants urgent (within-two-weeks) specialist assessment; a prolonged/active seizure remains
`base.life_threat` (status epilepticus, S1d) territory.

**Q4 — Fever with the seizure (febrile-convulsion pattern)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S1a ("ateşle birlikte ortaya çıkan nöbetlerdir")
> "Bu nöbet sırasında çocuğunuzun ateşi de var mıydı?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)**; per S1a
distinguishes febrile convulsion — the prolonged/complex form and status epilepticus are owned by
`base.life_threat`.

**Q5 — Headache, recent onset / worsening** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1b
("akut ve ilerleyici başağrılarında"; "Çocuğun yaşı ne kadar küçükse … ciddi bir nedeni olma
olasılığı o kadar yüksektir")
> "Çocuğunuzun son zamanlarda yeni başlayan ya da giderek kötüleşen bir baş ağrısı oldu mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)** for an
acute/progressive pattern, per S1b (which points such headaches to imaging).

**Q6 — Headache with fever** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1b (fizik
muayenede "ateş … meningeal irritasyon işaretleri"; ikincil neden: "intrakraniyal enfeksiyonlar")
> "Çocuğunuzun baş ağrısına ateş de eşlik ediyor mu?"
CANDIDATE — clinician to approve wording. **Overlap: `base.life_threat` meningitis pattern (§2.1).**
A companion neck-stiffness item ("ensesini öne eğerken zorlanıyor mu?") is *flagged, not drafted*, to
keep one concern per turn. Candidate_flag only; acute decision deferred to `base.life_threat`.

**Q7 — Developmental concern (not reaching / losing milestones)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S1c (developmental-delay work-up) — *delay* is sourced;
*regression* (loss of acquired skills) is **NO SOURCE FOUND (verbatim)**, see §4
> "Çocuğunuzun yürüme, konuşma ya da diğer gelişim basamaklarında yaşıtlarına göre geriden geldiğini
> ya da önceden kazandığı bir beceriyi kaybettiğini fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **not assigned** — S1c covers developmental
*delay* assessment; a regression-specific red-flag threshold is not sourced (§4).

**Q8 — Known neurological diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general
intake (history; S1 chapters name epilepsy/febrile convulsion)
> "Çocuğunuzun daha önce konmuş nörolojik bir tanısı var mı? Örneğin epilepsi (sara) ya da serebral
> palsi."
CANDIDATE — clinician to approve wording.

**Q9 — Current medications** · archetype: `ACTION.medication.v1` · source: general intake (history)
> "Çocuğunuzun düzenli kullandığı ilaçlar (örneğin nöbet ilacı) var mı?"
CANDIDATE — clinician to approve wording.

**Q10 — Drug allergy** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: general intake
> "Çocuğunuzun bilinen bir ilaç alerjisi ya da ilaca karşı gelişmiş bir tepkisi var mı?"
CANDIDATE — clinician to approve wording.

*(10 candidate questions; 4 red-flag-derived — Q3, Q4, Q5, Q6 — plus Q7 concern-capture with no
sourced flag, and general intake.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Developmental regression (loss of acquired skills) red flag** — Q7 captures the concern, but S1c
   supplies verbatim text on developmental *delay* (gelişim geriliği), **not** a regression-specific
   red flag. **NO SOURCE FOUND (verbatim, regression) — clinician must supply** (candidate: a Türkiye
   Çocuk Nörolojisi Derneği nörodejeneratif / regresyon bölümü, or an international source).
2. **Enumerated headache "red-flag" list** — S1b gives a general "uyarıcı belirti ve bulgular" +
   secondary-cause statement + a physical-exam alarm sentence, but not a single enumerated
   patient-answerable red-flag list (e.g. night waking, morning vomiting, worse on straining). **The
   enumerated list must be reconciled** from the guideline's table before sign-off; no such list is
   asserted here.
3. **S1 edition year / chapter & page provenance** — this Milli Pediatri collection was created 2014
   and updated 2026; the exact edition of the retrieved PDF and the chapter/figure/page for each S1
   quote **MUST be reconciled** against the primary PDF, and a verbatim snapshot committed, before
   sign-off.
4. **NICE NG217 recommendation number** — S2 content is reused from the in-repo `noroloji.md` (NICE
   403 to automated fetch); the exact recommendation id **must be reconciled** against the primary
   NICE page, or NG217 confirmed as the adopted reference.
5. **T.C. Sağlık Bakanlığı primary protocol** — S1 is a Türkiye-first *society* (Türkiye Çocuk
   Nörolojisi Derneği / Milli Pediatri) source, not a Bakanlık klinik protokolü. If files/09 §2
   requires the MoH tier, **NO SOURCE FOUND (MoH) — clinician must supply**.
6. **Status epilepticus / prolonged seizure emergency** — Q3/Q4 feed this as inputs; the acute
   determination is owned by `base.life_threat` (invariant 7), per S1d. No SE threshold is asserted
   here.
7. **Meningitis pattern (headache + fever + neck stiffness)** — Q6 feeds it; the companion
   neck-stiffness item is flagged, not drafted; the acute determination is owned by
   `base.life_threat` (§2.1).
8. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here; status epilepticus and meningitis are owned by
   `base.life_threat` (invariant 7). **`packages/protocols/triage` + `base.life_threat` must supply**,
   with committed `source` snapshots, before anything compiles.
9. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032); not fabricated. Head-circumference/growth measurement (item 12) and family history have
   **no archetype root** → export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 7** — life-threatening neurological emergencies (status epilepticus, meningitis pattern) are
  left to `base.life_threat`; this proposal only feeds questions and neither extends nor relaxes that
  sibling set (§2.1).
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, addressed to the parent/guardian
  (proxy), B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in questions; the compiler must still expand any numeral before TTS.
  (The verbatim S1 wording "15 dakikadan kısa", "6 ay-3 yaş", "30 dakikadan daha uzun" and S2 "within
  2 weeks" are retained only inside the §1 source block, never in patient-facing copy.)
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies Türkiye-first candidate
  source S1 (Türkiye Çocuk Nörolojisi Derneği) and named-body corroborator S2 (NICE NG217) for that
  block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served. A **paediatrician** must sign
  paediatric rules (per `base.life_threat` posture). `cocuk_norolojisi.yaml` is an L0 draft and is
  untouched.
