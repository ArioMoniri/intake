# Çocuk İmmünolojisi ve Alerjisi (Paediatric Immunology & Allergy) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk İmmünolojisi ve Alerjisi
(`branch: cocuk_immunolojisi_ve_alerjisi`, cluster `child_health`)
Purpose: patient-owned, Turkish-first **pre-visit intake** for a **paediatric** clinic (symptom
capture for a clinician-ready note) — **not** diagnosis, not triage authority. Because the patient is
a child, every question is addressed to the **parent/guardian (proxy)** about the child
(*çocuğunuz*). This file is a *proposal for a clinician to sign off*. It assigns **no** authoritative
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's
  own wording is quoted verbatim; no level is asserted.
- **Emergencies stay in `base.life_threat` (invariant 7):** **anaphylaxis** is a life-threatening
  presentation owned by `packages/protocols/base/intake.yaml` (`rf.anaphylaxis`, currently
  `TODO: … requires clinical sign-off` — a `draft_needs_source` clinical value, not a fabricated
  one). This specialty pack does **not** author, extend, relax or duplicate that rule. The questions
  below only **feed** it (history of a prior severe reaction, known trigger, whether an adrenaline
  auto-injector has been prescribed/is carried); they never carry the RED.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch/WebSearch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived
  rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_immunolojisi_ve_alerjisi.yaml`,
  `base.life_threat`, or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — Jeffrey Modell Foundation "10 Warning Signs of Primary Immunodeficiency" (children) (International; primary awareness tool)
- **guideline_id (proposed):** `JMF-10WARNINGSIGNS-CHILD` (awareness/screening list, NOT a clinical
  guideline document)
- **Publishing body:** Jeffrey Modell Foundation (JMF) Medical Advisory Board
- **Version / year:** list undated on the retrieved page — see §4 gap
- **URL (mirror used for verbatim text):** https://immunodeficiency.ca/primary-immunodeficiency/10-warning-signs/
- **retrieved_on:** 2026-09-20
- **Verbatim (the ten signs, children):**
  > "Four or more new ear infections within 1 year"
  > "Two or more serious sinus infections within 1 year"
  > "Two or more months on antibiotics with little effect"
  > "Two or more pneumonias within 1 year"
  > "Failure of an infant to gain weight or grow normally"
  > "Recurrent, deep skin or organ abscesses"
  > "Persistent thrush in mouth or fungal infection on skin"
  > "Need for intravenous antibiotics to clear infections"
  > "Two or more deep-seated infections including septicemia"
  > "A family history of Primary Immunodeficiency"
- **Verbatim (threshold statement):**
  > "If your child has two or more of these signs, ask your doctor about Primary Immunodeficiency."
- **Confidence: MEDIUM.** Widely reproduced JMF awareness list, retrieved from a national PI
  charity's mirror. It is an awareness tool, not a versioned clinical guideline; the primary JMF
  source and any Turkish adaptation MUST be confirmed before sign-off.

### S2 — EAACI *Anaphylaxis (2021 update)* guideline (International; primary)
- **guideline_id (proposed):** `EAACI-ANAPHYLAXIS-2021`
- **Publishing body:** European Academy of Allergy and Clinical Immunology (EAACI)
- **Version / year:** 2021 update (published in *Allergy*, 2022)
- **Citation:** Muraro A, et al. *EAACI guidelines: Anaphylaxis (2021 update).* Allergy.
  2022;77(2):357–377.
- **URL:** https://onlinelibrary.wiley.com/doi/10.1111/all.15032 · DOI: 10.1111/all.15032
- **retrieved_on:** 2026-09-20
- **Retrieved summary (adrenaline / autoinjector):** the guideline recommends the prompt use of
  intramuscular adrenaline as first-line management, and the availability of adrenaline autoinjectors
  to patients at risk in the community, together with structured training for people at risk of
  anaphylaxis.
- **Confidence: MEDIUM.** The autoinjector/first-line-adrenaline direction was captured via automated
  fetch/search summary; the Wiley full text and hub page returned HTTP 403 to automated fetch, so a
  **clean verbatim recommendation sentence was NOT captured** — see §4 gap. Used here only to justify
  *asking about* prior anaphylaxis and autoinjector possession, never to author a rule.

### S3 — Türkiye Ulusal Alerji ve Klinik İmmünoloji Derneği (AİD) — public patient education (Turkey; LOW confidence)
- **guideline_id (proposed):** `AID-COCUK-ALERJI` (public patient-education page, NOT a versioned
  clinical guideline document)
- **Publishing body:** Türkiye Ulusal Alerji ve Klinik İmmünoloji Derneği (AİD)
- **Version / year:** page undated in the retrieved excerpt — see §4 gap
- **URL:** https://www.aid.org.tr/hastaliklar/alerji-ile-ilgili-oneriler-ve-bazi-ipuclari/cocuklarda-alerji/
- **retrieved_on:** 2026-09-20
- **Verbatim (Turkish — anaphylaxis is the severe end of the spectrum):**
  > "Belirtileri de hafif ürtiker gibi olabileceği gibi ağır yaşamı tehdit eden ANAFİLAKSİ'de
  > görülebilir."
- **Verbatim (Turkish — carrying an adrenaline auto-injector):**
  > "Bu çocuklarımız yanlarında mutlaka ilk müdahale için adrenalin oto-enjektör taşımaları
  > gerekmektedir."
- **Verbatim (Turkish — accidental exposure risk):**
  > "Kazara besin alımı riski çocuğumuz büyüdükçe artmaktadır."
- **Confidence: LOW.** Single-source, retrieved via automated fetch from a public-facing education
  page (not a versioned guideline). Must be re-verified on the live page and, ideally, backed by a
  **T.C. Sağlık Bakanlığı** primary document before it grounds any patient-facing script.

### S4 — NICE CG116 *Food allergy in under 19s: assessment and diagnosis* (International; primary — partial retrieval)
- **guideline_id (proposed):** `NICE-CG116`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / year:** 2011 (CG116)
- **URL (canonical):** https://www.nice.org.uk/guidance/cg116/chapter/Recommendations
  (nice.org.uk returns HTTP 403 to automated fetch)
- **retrieved_on:** 2026-09-20
- **Retrieved (recommendation phrasing, via web-search synthesis — NOT a clean verbatim page fetch):**
  the guideline advises to *consider the possibility of food allergy in children and young people who
  have one or more signs and symptoms* — skin (pruritus, erythema, urticaria, angioedema, atopic
  eczema), gastrointestinal and respiratory symptoms — and to pay particular attention to persistent
  symptoms involving different organ systems, with referral to secondary/specialist care for problems
  such as faltering growth and systemic reactions.
- **Confidence: LOW–MEDIUM.** The primary NICE page and the ThermoFisher/BJGP mirrors did not yield a
  clean, quotable verbatim block to automated retrieval (403 / encoded PDF / nav-only). The exact
  CG116 signs-and-symptoms table therefore stays a **§4 gap**; §3 uses CG116 only to justify *asking
  about* food-triggered symptoms, not to author any rule or threshold.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes**. Per its own header, a slot whose leaf path is not yet
authored carries **`openehr_deferred_reason`** (INT-032, P3 export tier) — it is **not** invented. So
each item below binds to an archetype **root**; the specific leaf path is **deferred**, never
fabricated. (HB-C12 tracks the leaf-path authoring; this proposal does not close it.)

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the child's current complaint (story of present illness) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Recurrent ear infections (S1, sign 1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Recurrent pneumonia / serious sinus infections (S1, signs 2 & 4) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Infections needing prolonged / IV antibiotics with little effect (S1, signs 3 & 8) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Faltering growth / persistent thrush / recurrent abscesses (S1, signs 5, 6, 7) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Food-triggered skin/GI/respiratory reaction (S4; S3 triggers) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Prior severe allergic reaction / anaphylaxis history (S2; S3) — feeds `base.life_threat` | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 9 | Known triggers (foods, drugs, insect venom) — allergy/adverse-reaction risk (S2; S3) | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 10 | Adrenaline auto-injector prescribed / carried (S2; S3) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 11 | Known allergy / immunodeficiency diagnosis | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 12 | Current regular medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 13 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 14 | **Family history of primary immunodeficiency** (S1, sign 10) | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 14: the committed `.opt` exposes no family-history archetype root (`CLUSTER.provenance` is the
  only CLUSTER named in files/03 §7 and is itself ABSENT from the template). Capturing family history
  therefore has no export target today → **export blocked (INT-041 posture)**; do not invent an
  at-code path. The JMF list's tenth sign ("family history of Primary Immunodeficiency") is real and
  worth asking, but has **nowhere to bind for export** — clinician/architecture decision needed
  (candidate: INT-032 archetype addition). A question is drafted (Q10) and its export limitation is
  stated inline.
- Items 8 & 9 use `EVALUATION.adverse_reaction_risk.v1`; item 10 (the auto-injector) is an
  `ACTION.medication.v1` (a prescribed/carried medication), not the reaction risk itself.

---

## 3. Candidate B1 Turkish pre-visit questions (proxy — addressed to the parent/guardian)

Register: formal **`siz`** throughout, addressed to the **parent/guardian** about the child
(*çocuğunuz*); one concern per question (invariant 2: one question per turn); empathetic; **no
diagnosis/treatment/prognosis language** — the feared condition is **never named** to the parent; the
questions ask only about observable symptoms/history. Any numeral is written in words per invariant 22
(the compiler must expand every digit to Turkish orthography before TTS; the drafts already spell such
values out — e.g. "dört", "iki", "bir yıl"). **All marked "CANDIDATE — clinician to approve wording".**

> Triage note for every symptom item: any level is a **`candidate_flag` (max `YELLOW_REVIEW`), pending
> clinician + rules-engine confirmation — NOT authoritative**. The authoritative RED/YELLOW must come
> from `packages/protocols/triage` with a committed `source` snapshot and all three RED axes (route ×
> register × location, invariant 21), none supplied here. **Anaphylaxis** is owned by
> `base.life_threat`, not by this pack.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü görüşmede çocuğunuzla ilgili sizi en çok düşündüren konu nedir? Kısaca anlatabilir
> misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Story of the complaint** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu şikâyet ne zaman başladı ve o günden bu yana nasıl bir seyir izledi?"
CANDIDATE — clinician to approve wording.

**Q3 — Recurrent ear infections** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (JMF sign 1,
"Four or more new ear infections within 1 year")
> "Çocuğunuz son bir yıl içinde dört ya da daha fazla kez kulak enfeksiyonu geçirdi mi?"
CANDIDATE — clinician to approve wording.

**Q4 — Recurrent pneumonia / sinus infections** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S1 (JMF signs 2 & 4, "Two or more serious sinus infections"/"Two or more pneumonias within 1 year")
> "Çocuğunuz son bir yıl içinde iki ya da daha fazla kez zatürre (akciğer enfeksiyonu) ya da ağır
> sinüzit geçirdi mi?"
CANDIDATE — clinician to approve wording.

**Q5 — Infections needing prolonged / IV antibiotics** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 (JMF signs 3 & 8, "Two or more months on antibiotics with little effect"/"Need for
intravenous antibiotics to clear infections")
> "Çocuğunuzun enfeksiyonları, uzun süreli ya da damardan verilen antibiyotiklere rağmen zor mu
> geçiyor?"
CANDIDATE — clinician to approve wording.

**Q6 — Growth / thrush / abscesses** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (JMF
signs 5, 6, 7 — "Failure of an infant to gain weight or grow normally"; "Recurrent, deep skin or organ
abscesses"; "Persistent thrush in mouth or fungal infection on skin")
> "Çocuğunuzda kilo alamama ya da beklenen şekilde büyüyememe, ya da ağızda geçmeyen pamukçuk veya
> tekrarlayan cilt apseleri fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Note: this bundles three related JMF signs into one
parent-observable concern; the clinician may prefer to split it.

**Q7 — Food-triggered reaction** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 (NICE CG116,
food-allergy signs) + S3 (AİD, common triggers inek sütü/yumurta)
> "Çocuğunuzda belirli bir yiyeceği yedikten kısa süre sonra döküntü, kaşıntı ya da dudak-yüz
> şişmesi gibi tepkiler oldu mu?"
CANDIDATE — clinician to approve wording.

**Q8 — Prior severe allergic reaction (feeds `base.life_threat`)** · archetype:
`EVALUATION.adverse_reaction_risk.v1` · source: S2 (EAACI 2021) + S3 (AİD, ANAFİLAKSİ)
> "Çocuğunuzda daha önce nefes darlığı, yaygın döküntü ya da baygınlıkla giden ağır bir alerjik tepki
> oldu mu?"
CANDIDATE — clinician to approve wording. This history feeds the existing `base.life_threat`
anaphylaxis rule; it does not itself carry any triage level, and the question does not name a
diagnosis.

**Q9 — Known triggers** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: S2 (EAACI 2021,
triggers) + S3 (AİD)
> "Çocuğunuzun uzak durması gereken, bilinen bir besin, ilaç ya da arı sokması alerjisi var mı?"
CANDIDATE — clinician to approve wording.

**Q10 — Family history (immunodeficiency)** · archetype: **no root — export blocked (INT-041 posture)**
· source: S1 (JMF sign 10, "A family history of Primary Immunodeficiency")
> "Ailenizde bağışıklık sistemiyle ilgili kalıtsal bir hastalık tanısı alan biri oldu mu?"
CANDIDATE — clinician to approve wording. **Export limitation:** no family-history archetype root
exists in the committed `.opt`, so this answer has nowhere to bind for openEHR export today (item 14);
do not invent an at-code path.

**Q11 — Adrenaline auto-injector** · archetype: `ACTION.medication.v1` · source: S2 (EAACI 2021,
autoinjector availability) + S3 (AİD verbatim, "adrenalin oto-enjektör taşımaları gerekmektedir")
> "Çocuğunuza daha önce bir adrenalin oto-enjektör (örneğin kalem şeklinde acil iğne) reçete edildi mi
> ve yanında bulunduruyor mu?"
CANDIDATE — clinician to approve wording. History capture only (does not advise treatment).

**Q12 — Current medications** · archetype: `ACTION.medication.v1` · source: general intake (history)
> "Çocuğunuzun şu anda düzenli olarak kullandığı ilaçlar var mı?"
CANDIDATE — clinician to approve wording.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned clinical guideline (T.C. Sağlık Bakanlığı / AİD)** — only a public
   patient-education page (S3, LOW confidence) was retrievable; **no versioned Turkish clinical
   guideline document was located** for paediatric allergy/immunodeficiency. **NO SOURCE FOUND —
   clinician must supply** the correct Türkiye-first primary source and its version/date.
2. **NICE CG116 signs-and-symptoms table — clean verbatim** — the primary NICE page (403), the
   ThermoFisher PDF (encoded), and the BJGP summary (nav-only) did not yield a quotable verbatim
   block to automated retrieval. The §1-S4 phrasing is a web-search synthesis, not a verified verbatim
   quote. **NO SOURCE FOUND (verbatim) — clinician must supply** the exact CG116 recommendation text
   and number.
3. **EAACI 2021 — clean verbatim recommendation sentence** — the autoinjector/first-line-adrenaline
   direction was captured only as a retrieved summary (Wiley/EAACI hub returned 403). **NO SOURCE
   FOUND (verbatim) — clinician must supply** the exact recommendation sentence before it grounds any
   patient-facing script.
4. **Anaphylaxis red-flag wording / adrenaline action script** — deliberately **NOT authored here**;
   it lives in `base.life_threat` (invariant 7; `rf.anaphylaxis` is `draft_needs_source`). The exact
   verbatim source, the RED register/location axes (invariant 21) and the action script are the base
   pack's / clinician's responsibility, not this file's. **Out of scope — do not duplicate.**
5. **JMF list — version/date and any Turkish adaptation** — the "10 Warning Signs" list is undated on
   the retrieved mirror and is an awareness tool, not a versioned guideline. **NO SOURCE FOUND
   (versioned/primary) — clinician to confirm** the primary JMF source and whether a Turkish-validated
   adaptation should be used instead.
6. **Numeric thresholds ("four or more", "two or more", "within 1 year")** — carried here only as the
   verbatim JMF wording to justify *asking*; they are **not** proposed as triage cut-offs. Any cut-off
   is a clinical value: **clinician + `packages/protocols/triage` must supply**, not this file.
7. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must supply**,
   with committed `source` snapshots, before anything compiles.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032 /
   HB-C12); not fabricated. Family history (item 14 / Q10) has **no archetype root** → export blocked
   (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules
  engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, proxy-addressed to the
  parent, no diagnosis/treatment/prognosis; the feared condition is never named; marked CANDIDATE.
- **Inv. 7** — anaphylaxis kept in `base.life_threat`; this pack neither extends nor relaxes it, only
  feeds it.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — numerals in drafts are spelled out; compiler must expand before TTS; no free numeric
  entry proposed on the clinical critical path.
- **Clinical content rule** — each symptom-derived rule needs `source: {guideline_id, version, date,
  url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S4 for
  that block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
