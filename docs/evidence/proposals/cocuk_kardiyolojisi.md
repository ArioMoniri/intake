# Çocuk Kardiyolojisi (Paediatric Cardiology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Kardiyolojisi (Paediatric
Cardiology)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. Paediatric: every question is addressed to the
**parent/guardian (proxy)**. This file is a *proposal for a clinician to sign off*. It assigns **no**
authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Türkiye-first sourcing achieved for this specialty.** S1–S3 are all drawn verbatim from a single
  genuine Turkish specialty-society document: the **Türkiye Milli Pediatri Derneği** ×
  **Türk Pediatrik Kardiyoloji ve Kalp Cerrahisi Derneği ortak kılavuzu** (*Çocuk Sağlığı ve
  Hastalıklarında Tanı ve Tedavi Kılavuzları (3)*, Aralık 2014) — exactly the "İlgili uzmanlık derneği
  kılavuzları" tier that the L0 pack header and files/09 §2 name for the `child_health` cluster.
- **Life-threatening cardiac emergencies stay in `base.life_threat` (invariant 7).** A **hipoksik /
  hipersiyanotik nöbet** (cyanotic spell) in a duct-dependent lesion, a **hayatı tehdit eden siyanoz**
  when the ductus closes, and a haemodynamically unstable **aritmi** (SVT/VT) are life-threatening; per
  invariant 7 the `base.life_threat` sibling set is authoritative and *nothing may extend it*. This
  proposal **only feeds intake questions** that surface the early symptoms for the clinician and the
  rules engine — it does **not** author, relax or duplicate any life-threat threshold, and it speaks
  **no** RED action script or emergency number.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's own
  wording is quoted verbatim; no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated PDF text extraction (`pdftotext`) of the retrieved document. Before sign-off, each verbatim
  sentence MUST be re-checked against the **primary published text** and committed as a **verbatim
  source snapshot** with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until
  then any derived rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_kardiyolojisi.yaml` (an L0 draft that
  never serves) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

All three sub-sources are chapters of the **same** retrieved document; they share one URL and are cited
as distinct chapters (as the paediatric-endocrinology proposal cites distinct chapters of ÇEDD 2026).

- **Publishing body:** Türkiye Milli Pediatri Derneği (TMPD) & Türk Pediatrik Kardiyoloji ve Kalp
  Cerrahisi Derneği (TPKKCD) — ortak kılavuz.
- **Document:** *Çocuk Sağlığı ve Hastalıklarında Tanı ve Tedavi Kılavuzları (3)*, Aralık 2014.
- **URL:** https://millipediatri.org.tr/Custom/Upload/files/kilavuzlar/kilavuz-3.pdf
- **Version / year:** Kılavuz (3), Aralık 2014.
- **Confidence: MEDIUM-HIGH.** Genuine Turkish specialty-society guideline retrieved as PDF and
  text-extracted; page numbers below are from the extracted layout — reconcile against the primary PDF.

### S1 — TMPD×TPKKCD 2014, Bölüm 1 "Siyanotik Yenidoğana Yaklaşım" (Doç. Dr. İlkay Erdoğan)
- **guideline_id (proposed):** `TMPD-TPKKCD-2014-SIYANOZ`
- **Verbatim (giriş — santral siyanoz):**
  > "Yenidoğanda sık karşılaşılan bir bulgu olmasına rağmen santral siyanoz ciddi ve hayatı tehdit
  > eden bir hastalığın varlığına işaret edebilir ve hızlı bir değerlendirme yapılmasını gerektirir."
- **Verbatim (santral siyanoz — patolojik):**
  > "Santral siyanoz mukozalar ve dilde daha belirgin olmak üzere tüm vücutta görülür. … Persistan
  > siyanoz her zaman patolojiktir ve ayrıntılı bir araştırma gerektirir."
- **Verbatim (duktus-bağımlı lezyon — BAT):**
  > "İnterventriküler septumda yeterli bir defekt olmadığında foramen ovale ve duktus arteriyozus
  > kapandığında doğumdan sonra saatler veya günler içerisinde hayatı tehdit eden siyanoz ortaya çıkar."

### S2 — TMPD×TPKKCD 2014, Bölüm 2 "Çocuklarda Konjestif Kalp Yetmezliği" (Prof. Dr. R. Ertürk Levent)
- **guideline_id (proposed):** `TMPD-TPKKCD-2014-KKY`
- **Verbatim (klinik bulgular — öykü):**
  > "Kalp yetmezliği hastalarında öykü önemlidir. Kötü ve zayıf beslenme, kilo almada azlık ve soğuk
  > terleme özellikle infantlarda sıktır. Daha büyük çocuklarda solunum sıkıntısı, kolay yorulma ve
  > gözkapaklarında şişlik diğer bulgular olabilir."
- **Verbatim (konjesyon bulguları — özet):** miyokard performans bozukluğuna bağlı "taşikardi";
  pulmoner konjesyona bağlı "takipne, dispne"; sistemik venöz konjesyona bağlı "hepatomegali … göz
  kapaklarında ödem".

### S3 — TMPD×TPKKCD 2014, Bölüm 3 "Çarpıntılı Çocuk Hastaya Yaklaşım" (Prof. Dr. Naci Ceviz)
- **guideline_id (proposed):** `TMPD-TPKKCD-2014-CARPINTI`
- **Verbatim (senkop ilişkisi):**
  > "Senkop veya presenkopun eşlik ettiği çarpıntı yakınması ciddi aritmi yönünden dikkatli
  > incelenmelidir."
- **Verbatim (egzersiz ilişkisi — genetik aritmi):**
  > "Bazı ciddi kardiyak aritmilerin egzersiz ile tetiklenebileceğini bilmek önemlidir. Özellikle efor
  > sırasında ortaya çıkan çarpıntıya senkop da eşlik ediyor ise katekolaminerjik polimorfik VT ve uzun
  > QT sendromu gibi genetik aritmi sendromları hatırlanmalıdır."
- **Verbatim (aritmi lehine klinik ipuçları — liste):**
  > "…ani başlayıp biten yüksek hızlı çarpıntı, eforla ortaya çıkan çarpıntı, senkop, presenkopun eşlik
  > ettiği çarpıntı, geri döndürülmüş ani ölüm hikayesi, yapısal kalp hastalığının varlığı…"
- **Verbatim (yönlendirme):**
  > "Senkopun eşlik ettiği çarpıntı yakınması olan, yapısal kalp hastalığı olan ve kardiyak cerrahi
  > geçirmiş olan hastalarda çarpıntının sebebinin bir kardiyak aritmi olma ihtimali daha yüksektir. Bu
  > hastalar çocuk kardiyolojisi birimlerinde değerlendirilmeli…"

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
| 3 | Central cyanosis / bluish lips-tongue-nailbeds (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Feeding fatigue / sweating with feeds — infant (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Poor weight gain / slow growth (S2 "kilo almada azlık") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Breathlessness / easy fatigue / eyelid swelling (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Palpitations (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Palpitation / faint on exertion (S3 high-risk) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Syncope / near-syncope (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Known cardiac diagnosis / prior cardiac surgery (S3 referral) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current cardiac medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine / `base.life_threat` only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 13 | **Family history of sudden death at young age / inherited arrhythmia (S3 "geri döndürülmüş ani ölüm hikayesi")** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 13: as in the cardiology and endocrinology proposals, the committed `.opt` exposes **no
  family-history archetype root**, so capturing family history of sudden cardiac death has **no export
  target today → export blocked (INT-041 posture)**; do not invent an at-code path. The *reason-for-visit*
  framing of the concern (Q10) still binds via `EVALUATION.reason_for_encounter.v1`, but the family-history
  fact does not. Clinician/architecture decision needed (candidate: INT-032 archetype addition).
- **Growth measurement (item 5).** The *concern* binds to `symptom_sign`/`reason_for_encounter`, but a
  measured height/weight/percentile has **no anthropometry archetype root** in the committed `.opt` →
  numeric growth capture is **export blocked (INT-041 posture)**; not fabricated here.
- **PHQ-9 / GAD-7 not bound here.** Those are the *adult* consented-wellbeing screens; paediatric
  applicability is age-dependent and out of scope for this cardiac red-flag proposal.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian (proxy)** about *çocuğunuz*;
one concern per question (invariant 2: one question per turn); empathetic; no diagnosis/treatment/
prognosis language. **All marked "CANDIDATE — clinician to approve wording".** No bare numerals appear
(invariant 22); no emergency number or action script is spoken here — RED action scripts belong to
`base.life_threat` / triage, never to an intake question.

> Triage note for every red-flag-derived item: the level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. The authoritative RED for a
> cyanotic spell / duct-dependent life-threatening cyanosis / unstable arrhythmia comes from
> `base.life_threat` with all three RED axes (route × register × location, invariant 21), none of which
> are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Renumbering, old → new — sections outside §3 still use the old numbers: Q1
unchanged · Q2 removed (duplicates base `hpi.onset_date` + `hpi.trajectory`) · Q3 → Q2 · Q4 → Q3
(feeding fatigue) + Q4 (sweating with feeds) · Q5 → Q5 · Q6 → Q6 (fatigue) + Q7 (breathing) + Q8
(eyelid swelling) · Q7 → Q9 · Q9 → Q10 · Q8 → Q11 (moved after syncope; if Q9 or Q10 yes) · Q10 →
Q12 (sudden death) + Q13 (inherited rhythm disease) · Q11 → Q14 (diagnosis) + Q15 (surgery) · Q12 →
Q16.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün getiren temel konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Central cyanosis** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("santral siyanoz …
hayatı tehdit eden bir hastalığın varlığına işaret edebilir")
> "Çocuğunuzun dudaklarında, dilinde ya da tırnaklarında morarma fark ettiniz mi?"
gen: slot=morarma; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician
+ rules-engine confirmation — NOT authoritative)** per S1; a duct-dependent life-threatening cyanosis /
cyanotic spell is owned by `base.life_threat`.

**Q3 — Feeding fatigue (infant heart failure)** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S2 ("Kötü ve zayıf beslenme … soğuk terleme özellikle infantlarda sıktır")
> "Çocuğunuz emerken ya da mama alırken çabuk yoruluyor mu?"
gen: slot=beslenirken_yorulma; type=boolean
CANDIDATE — clinician to approve wording. The reviewer asks for an infant-age `ask_if` on Q3/Q4; the
age cut-off is a clinical value, so the gate is a clinician decision pending and no age is proposed
here.

**Q4 — Sweating with feeds (infant heart failure)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S2 ("soğuk terleme özellikle infantlarda sıktır")
> "Çocuğunuz beslenirken terliyor mu?"
gen: slot=beslenirken_terleme; type=boolean
CANDIDATE — clinician to approve wording. Infant-age gate: clinician decision pending (as Q3).

**Q5 — Poor weight gain / slow growth** · archetype: `OBSERVATION.symptom_sign.v1` (measured value
export-blocked, §2 item 5) · source: S2 ("kilo almada azlık")
> "Çocuğunuzun kilo alması ya da büyümesi size yavaş mı geliyor?"
gen: slot=yavas_kilo_alma; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Easy fatigue** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("Daha büyük çocuklarda
solunum sıkıntısı, kolay yorulma ve gözkapaklarında şişlik")
> "Çocuğunuz son zamanlarda her zamankinden çabuk yoruluyor mu?"
gen: slot=cabuk_yorulma; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Breathlessness** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("solunum sıkıntısı")
> "Çocuğunuz son zamanlarda nefes almakta zorlanıyor mu?"
gen: slot=nefes_darligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — Eyelid swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("gözkapaklarında
şişlik")
> "Çocuğunuzun göz kapaklarında şişlik oluyor mu?"
gen: slot=goz_kapagi_sislik; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Palpitations** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (çarpıntı değerlendirmesi)
> "Çocuğunuzun kalbinin hızlı, düzensiz ya da çok güçlü çarptığı oldu mu?"
gen: slot=carpinti; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Syncope / near-syncope** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("Senkop veya
presenkopun eşlik ettiği çarpıntı … ciddi aritmi yönünden dikkatli incelenmelidir")
> "Çocuğunuz hiç bayıldı ya da bayılacak gibi olduğunu hissetti mi?"
gen: slot=bayilma; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)** when
accompanying palpitation/exertion, per S3.

**Q11 — Palpitation / faint on exertion (if Q9 or Q10 yes)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S3 ("efor sırasında ortaya çıkan çarpıntıya senkop da eşlik
ediyor ise … genetik aritmi sendromları")
> "Bu çarpıntı ya da baygınlık koşarken ya da oyun oynarken oluyor mu?"
gen: slot=eforla_carpinti_bayilma; type=boolean; ask_if=carpinti == true || bayilma == true
CANDIDATE — clinician to approve wording. Moved after the syncope item because it refers to fainting.
Candidate_flag: **YELLOW_REVIEW (candidate, …)** per S3; exertional palpitation with syncope points to
a genetic arrhythmia — the emergency is owned by `base.life_threat`.

**Q12 — Family history of sudden death at young age** · archetype:
`EVALUATION.reason_for_encounter.v1` (family-history fact export-blocked, §2 item 13) · source: S3
("geri döndürülmüş ani ölüm hikayesi")
> "Ailenizde genç yaşta nedeni bilinmeyen ani ölüm yaşandı mı?"
gen: slot=ailede_ani_olum; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)** per S3.

**Q13 — Family history of inherited rhythm disease** · archetype:
`EVALUATION.reason_for_encounter.v1` (family-history fact export-blocked, §2 item 13) · source: S3
("genetik aritmi sendromları")
> "Ailenizde kalıtsal bir kalp ritmi hastalığı olan biri var mı?"
gen: slot=ailede_ritim_hastaligi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)** per S3.

**Q14 — Known cardiac diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S3
(referral: "yapısal kalp hastalığı")
> "Çocuğunuza daha önce bir kalp hastalığı tanısı kondu mu?"
gen: slot=kalp_tanisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q15 — Prior cardiac surgery** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S3 (referral:
"kardiyak cerrahi geçirmiş")
> "Çocuğunuz daha önce kalp ameliyatı oldu mu?"
gen: slot=kalp_ameliyati; type=boolean
CANDIDATE — clinician to approve wording.

**Q16 — Current medications (cardiac)** · archetype: `ACTION.medication.v1` · source: general intake
(history)
> "Çocuğunuzun kalbi ya da başka bir durumu için düzenli kullandığı ilaçlar var mı?"
gen: slot=duzenli_ilac; type=boolean
CANDIDATE — clinician to approve wording.

*(16 candidate questions; red-flag-derived — Q2, Q10, Q11, Q12, Q13 — plus general intake and
history.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **T.C. Sağlık Bakanlığı primary protocol** — S1–S3 are Türkiye-first *society* (TMPD×TPKKCD 2014)
   sources, not a Bakanlık klinik protokolü. If files/09 §2 requires the MoH tier for this cluster,
   **NO SOURCE FOUND (MoH) — clinician must supply**.
2. **Hipoksik / hipersiyanotik nöbet (cyanotic "tet spell") verbatim** — S1 covers the *cyanotic
   newborn* and duct-dependent life-threatening cyanosis, but a verbatim description of the classic
   hypercyanotic spell (crying/feeding-triggered deep cyanosis, squatting, morning spells in
   tetralogy of Fallot) was **NOT retrieved** verbatim from the accessible chapter. **NO SOURCE FOUND
   (verbatim) — clinician to supply** (candidate: TPKKCD / AHA paediatric CHD).
3. **International named-body corroborator for exertional syncope / family sudden death** — the
   **2017 ACC/AHA/HRS Syncope Guideline** (DOI 10.1161/cir.0000000000000499) has a paediatric section
   covering exactly these red flags, but ahajournals.org returned **HTTP 403** to automated fetch, so
   no verbatim was captured. **NO SOURCE FOUND (verbatim, corroborator) — clinician to reconcile** from
   the primary text. (The Türkiye-first S3 already grounds these flags; a corroborator only strengthens.)
4. **Paediatric chest pain red flags** — no question is proposed for chest pain because **no source was
   retrieved**; S1–S3 do not enumerate paediatric chest-pain alarm features. **NO SOURCE FOUND —
   clinician to supply** if a chest-pain item is wanted (candidate: AAP / AHA).
5. **Standalone palpitations urgency threshold** — S3 links serious risk to palpitation *with* syncope
   or *with* exertion, or to structural heart disease; a cut-off for palpitations alone is **NO SOURCE
   FOUND — clinician to supply**.
6. **Kılavuz page/figure reconciliation** — S1–S3 quotes were captured via `pdftotext` layout
   extraction; the exact page/section numbers MUST be re-verified against the primary PDF and a verbatim
   snapshot committed before sign-off.
7. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here; the cyanotic spell / duct-dependent cyanosis / unstable
   arrhythmia are owned by `base.life_threat` (invariant 7). **`packages/protocols/triage` +
   `base.life_threat` must supply**, with committed `source` snapshots, before anything compiles.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032);
   not fabricated. Family history (item 13) and the numeric growth value (item 5) have **no archetype
   root** → export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 7** — life-threatening cardiac emergencies (cyanotic spell, duct-dependent cyanosis, unstable
  arrhythmia) are left to `base.life_threat`; this proposal only feeds questions and neither extends nor
  relaxes that sibling set.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, addressed to the parent/guardian
  (proxy), B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in questions; the compiler must still expand any numeral before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies Türkiye-first candidate
  sources S1–S3 (TMPD×TPKKCD 2014) for that block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served. `cocuk_kardiyolojisi.yaml` is an L0 draft
  and is untouched.
