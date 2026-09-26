# Çocuk Hematolojisi ve Onkolojisi (Paediatric Haematology-Oncology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Hematolojisi ve Onkolojisi
(`branch: cocuk_hematolojisi_ve_onkolojisi`, cluster `child_health`)
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
  own urgency wording is quoted verbatim; no level is asserted.
- **Emergencies stay in `base.life_threat` (invariant 7):** **febrile neutropenia / neutropenic
  sepsis** in a child on chemotherapy is a life-threatening, one-hour emergency and is owned by
  `packages/protocols/base/intake.yaml` (`base.life_threat`, the sibling set outside the inheritance
  chain — see the neutropenic-fever gate around lines 515/567). This specialty pack does **not**
  author, extend, relax or duplicate that rule. The questions below only **feed** the existing base
  rule (history of a blood/cancer diagnosis, current treatment, fever); they never carry the RED.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch/WebSearch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived
  rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_hematolojisi_ve_onkolojisi.yaml`,
  `base.life_threat`, or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG12 *Suspected cancer: recognition and referral* — childhood cancers (International; primary)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / year:** originally 2015, recommendations amended through 2025; NCBI Bookshelf mirror
  shows the guideline text current at retrieval.
- **URL (canonical):** https://www.nice.org.uk/guidance/ng12/chapter/recommendations-organised-by-site-of-cancer
  (nice.org.uk returns HTTP 403 to automated fetch)
- **URL (mirror used for verbatim text):** https://www.ncbi.nlm.nih.gov/books/NBK555330/
- **retrieved_on:** 2026-09-20
- **Verbatim (leukaemia — immediate assessment, rec. 1.10.2):**
  > "Refer children and young people for immediate specialist assessment for leukaemia if they have
  > unexplained petechiae or hepatosplenomegaly."
- **Verbatim (leukaemia — very urgent full blood count, rec. 1.10.3):**
  > "Offer a very urgent full blood count (within 48 hours) to assess for leukaemia in children and
  > young people with any of the following: pallor, persistent fatigue, unexplained fever, unexplained
  > persistent infection, generalised lymphadenopathy, persistent or unexplained bone pain,
  > unexplained bruising, unexplained bleeding."
- **Verbatim (non-Hodgkin's lymphoma, rec. 1.10.7):**
  > "Consider a very urgent referral (for an appointment within 48 hours) for specialist assessment
  > for non-Hodgkin's lymphoma in children and young people presenting with unexplained
  > lymphadenopathy or splenomegaly."
- **Verbatim (bone sarcoma, recs. 1.11.2 / 1.11.3):**
  > "Consider a very urgent referral (for an appointment within 48 hours) for specialist assessment
  > for children and young people if an X-ray suggests the possibility of bone sarcoma. Consider a
  > very urgent direct access X-ray (to be done within 48 hours) to assess for bone sarcoma in
  > children and young people with unexplained bone swelling or pain."
- **Verbatim (neuroblastoma, rec. 1.12.1):**
  > "Consider very urgent referral (for an appointment within 48 hours) for specialist assessment for
  > neuroblastoma in children with a palpable abdominal mass or unexplained enlarged abdominal organ."
- **Verbatim (retinoblastoma, rec. 1.12.2):**
  > "Consider referral for ophthalmological assessment using a suspected cancer pathway referral for
  > retinoblastoma in children with an absent fundal ('red') reflex."
- **Verbatim (brain/CNS cancer, rec. 1.9.2):**
  > "Consider a very urgent referral (for an appointment within 48 hours) for suspected brain or
  > central nervous system cancer in children and young people with newly abnormal cerebellar or
  > other central neurological function."
- **Corroboration:** the leukaemia FBC list and the "immediate specialist assessment" wording were
  returned identically by an independent web-search summary and by the NCBI Bookshelf page fetch →
  higher confidence. Still requires primary-text re-verification and exact recommendation-number
  reconciliation against the current NG12 revision.

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
| 3 | Unexplained bruising (S1, 1.10.3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Unexplained bleeding / petechiae (S1, 1.10.2 + 1.10.3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Pallor + persistent fatigue (S1, 1.10.3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Persistent/unexplained fever + persistent infection (S1, 1.10.3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Persistent / unexplained bone or joint pain (S1, 1.10.3 + 1.11.3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Enlarged glands / lump neck-armpit-groin — lymphadenopathy (S1, 1.10.7 + 1.10.3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Abdominal swelling / palpable mass (S1, 1.12.1 + 1.10.2 hepatosplenomegaly) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | White pupil glow / absent 'red' reflex in photos (S1, 1.12.2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Known blood/oncology diagnosis + current treatment (feeds `base.life_threat` neutropenic-fever gate) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 12 | Current regular medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 13 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 14 | **Family history of childhood cancer / haematological disease** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 14: the committed `.opt` exposes no family-history archetype root (`CLUSTER.provenance` is the
  only CLUSTER named in files/03 §7 and is itself ABSENT from the template). Capturing family history
  therefore has no export target today → **export blocked (INT-041 posture)**; do not invent an
  at-code path. Clinician/architecture decision needed (candidate: INT-032 archetype addition).
  This proposal accordingly does **not** raise a family-history question (would have nowhere to bind).
- Item 13 is bound only for completeness; the authoritative level is the rules engine's, never this
  file's.

---

## 3. Candidate B1 Turkish pre-visit questions (proxy — addressed to the parent/guardian)

Register: formal **`siz`** throughout, addressed to the **parent/guardian** about the child
(*çocuğunuz*); one concern per question (invariant 2: one question per turn); empathetic; **no
diagnosis/treatment/prognosis language** — the feared condition is **never named** to the parent; the
questions ask only about observable symptoms. Any numeral is written in words per invariant 22 (the
compiler must expand every digit to Turkish orthography before TTS). **All marked "CANDIDATE —
clinician to approve wording".**

> Triage note for every symptom item: any level is a **`candidate_flag` (max `YELLOW_REVIEW`), pending
> clinician + rules-engine confirmation — NOT authoritative**. The authoritative RED/YELLOW must come
> from `packages/protocols/triage` with a committed `source` snapshot and all three RED axes (route ×
> register × location, invariant 21), none supplied here. Life-threatening presentations (e.g.
> febrile neutropenia) are owned by `base.life_threat`, not by this pack.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Findings 12, 14 and 15 apply. Renumbering, old → new — sections
outside §3 still use the old numbers: Q1 → Q1 · Q2 removed (base `onset_date` + `trajectory`) · Q3
→ Q2 · Q4 → Q3 (nose or gum bleeding) + Q4 (pinpoint spots) · Q5 → Q5 (pallor) + Q6 (persistent
tiredness) · Q6 → Q7 · Q7 → Q8 · Q8 → Q9 · Q9 → Q10 · Q10 → Q11 · Q11 → Q12 (earlier diagnosis) +
Q13 (on regular treatment, if Q12) · Q12 removed (base meds).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün çocuğunuzla ilgili sizi en çok düşündüren konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Unexplained bruising** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 1.10.3,
"unexplained bruising")
> "Çocuğunuzun vücudunda nedeni belli olmayan morluklar fark ettiniz mi?"
gen: slot=nedensiz_morluk; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: feeds a symptom cluster; no standalone level
asserted here.

**Q3 — Unexplained nose or gum bleeding** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(NG12 1.10.3 "unexplained bleeding")
> "Çocuğunuzda nedeni belli olmayan burun ya da diş eti kanaması oldu mu?"
gen: slot=burun_dis_eti_kanamasi; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Petechiae** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 1.10.2 "petechiae")
> "Çocuğunuzun cildinde iğne başı büyüklüğünde kırmızı ya da mor noktalar fark ettiniz mi?"
gen: slot=ciltte_kirmizi_mor_nokta; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Pallor** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 1.10.3 "pallor")
> "Çocuğunuz son zamanlarda her zamankinden solgun görünüyor mu?"
gen: slot=solukluk; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Persistent fatigue** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 1.10.3
"persistent fatigue")
> "Çocuğunuz son zamanlarda geçmeyen bir yorgunluk yaşıyor mu?"
gen: slot=gecmeyen_yorgunluk; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Persistent fever / infections** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12
1.10.3 "unexplained fever, unexplained persistent infection")
> "Çocuğunuzda nedeni açıklanamayan, uzun süren ateş ya da sık tekrarlayan enfeksiyonlar oldu mu?"
gen: slot=uzun_ates_sik_enfeksiyon; type=boolean
CANDIDATE — clinician to approve wording. (If the child has a known diagnosis and is on treatment —
see Q12–Q13 — a current fever is handled by the `base.life_threat` neutropenic-fever gate, not here.)

**Q8 — Bone pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 1.10.3
"persistent or unexplained bone pain"; 1.11.3 "unexplained bone swelling or pain")
> "Çocuğunuz geçmeyen ya da nedeni belli olmayan bir kemik ağrısından yakınıyor mu?"
gen: slot=kemik_agrisi; type=boolean
CANDIDATE — clinician to approve wording. The night-waking qualifier is removed: it is not in NG12
1.10.3 and narrowed the ask (finding 15).

**Q9 — Enlarged glands** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 1.10.7
"unexplained lymphadenopathy or splenomegaly"; 1.10.3 "generalised lymphadenopathy")
> "Çocuğunuzun boynunda, koltuk altında ya da kasığında geçmeyen bir şişlik fark ettiniz mi?"
gen: slot=boyun_koltuk_kasik_sislik; type=boolean
CANDIDATE — clinician to approve wording. "bez" is gone: in a paediatric pack it reads as "diaper"
(finding 12).

**Q10 — Abdominal swelling / mass** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12
1.12.1 "palpable abdominal mass or unexplained enlarged abdominal organ"; 1.10.2 "hepatosplenomegaly")
> "Çocuğunuzun karnında şişlik ya da elinize gelen bir sertlik fark ettiniz mi?"
gen: slot=karinda_sislik_sertlik; type=boolean
CANDIDATE — clinician to approve wording. "kitle" replaced by "sertlik" (finding 14).

**Q11 — White pupil glow (retinoblastoma cue)** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S1 (NG12 1.12.2, "absent fundal ('red') reflex")
> "Çocuğunuzun fotoğraflarında göz bebeğinin beyaz parladığını fark ettiniz mi?"
gen: slot=goz_bebegi_beyaz_parlama; type=boolean
CANDIDATE — clinician to approve wording. Note: absent red reflex is normally an examination finding;
this question captures only what a parent can observe (e.g. in flash photographs).

**Q12 — Known serious diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general
intake (history; feeds `base.life_threat`)
> "Çocuğunuza daha önce kanla ilgili ya da başka ciddi bir hastalık tanısı kondu mu?"
gen: slot=onceki_ciddi_tani; type=boolean
CANDIDATE — clinician to approve wording. Widened beyond blood disease: children with a solid tumour
on treatment carry the same neutropenic-fever context.

**Q13 — Current regular treatment** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general
intake (history; feeds `base.life_threat`)
> "Çocuğunuz şu anda bu hastalık için düzenli bir tedavi görüyor mu?"
gen: slot=duzenli_tedavi; type=boolean; ask_if=onceki_ciddi_tani == true
CANDIDATE — clinician to approve wording. This history feeds the existing `base.life_threat`
neutropenic-fever gate; it does not itself carry any triage level.

*(13 candidate questions after revision.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned clinical guideline (T.C. Sağlık Bakanlığı / TPHOD — Türk Pediatrik
   Hematoloji ve Onkoloji Derneği)** — only private-hospital patient-information pages and a
   physician's education blog were retrievable for paediatric leukaemia/cancer warning signs; **no
   versioned Turkish clinical guideline document was located**. **NO SOURCE FOUND — clinician must
   supply** the correct Türkiye-first primary source and its version/date. (This mirrors the
   kardiyoloji proposal's Turkish-source gap.)
2. **Febrile neutropenia / neutropenic sepsis red-flag wording** — deliberately **NOT authored here**;
   it lives in `base.life_threat` (invariant 7). The exact verbatim source and thresholds for that
   base rule are the base pack's responsibility, not this file's. **Out of scope — do not duplicate.**
3. **Exact NG12 recommendation numbers / current revision** — the numbers in §1 (1.9.2, 1.10.2,
   1.10.3, 1.10.7, 1.11.2/1.11.3, 1.12.1, 1.12.2) were captured from the NCBI Bookshelf mirror and
   MUST be reconciled against the live NG12 chapter before sign-off. **Clinician/editor to confirm.**
4. **Age banding** — NG12 says "children and young people"; the precise paediatric age bounds for this
   pack (and any overlay vs. `cocuk_sagligi_ve_hastaliklari`) are **NOT decided here**. Clinician to
   specify.
5. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must supply**,
   with committed `source` snapshots, before anything compiles.
6. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032 /
   HB-C12); not fabricated. Family history (item 14) has **no archetype root** → export blocked
   (INT-041 posture); no family-history question was raised.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules
  engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, proxy-addressed to the
  parent, no diagnosis/treatment/prognosis; the feared condition is never named; marked CANDIDATE.
- **Inv. 7** — febrile neutropenia / neutropenic sepsis kept in `base.life_threat`; this pack neither
  extends nor relaxes it, only feeds it.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — numerals in drafts are spelled out; compiler must expand before TTS; no free numeric
  entry proposed on the clinical critical path.
- **Clinical content rule** — each symptom-derived rule needs `source: {guideline_id, version, date,
  url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate source S1 for that
  block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
