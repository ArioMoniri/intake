# Deri ve Zührevi Hastalıkları (Dermatology & Venereology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher subagent · Date: 2026-09-20 · Specialty: Deri ve Zührevi Hastalıkları
(Dermatology & Venereology) · Branch slug: `deri_ve_zuhrevi_hastaliklari` (cluster: medical)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom / history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no**
clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's own
  urgency wording is quoted verbatim; **no level is asserted**.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / WebSearch). The **live nice.org.uk chapter page returned HTTP 403**;
  the verbatim NICE text below was read from the **NCBI Bookshelf mirror** of NG12 (NBK555330).
  Before sign-off, each verbatim sentence and **every recommendation number** MUST be re-checked against
  the **primary published NICE text** and committed as a **verbatim source snapshot** with a full
  `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule stays
  `status: draft_needs_source` and does **not** compile into a served pack.
- **Airway / anaphylaxis stays in `base.life_threat` (invariant 7).** Severe drug eruption or urticaria
  with breathing difficulty / lip-tongue swelling is a **universal life-threat family**
  (`rf.anaphylaxis`, `rf.dyspnoea_rest` in `packages/protocols/base/intake.yaml`), a sibling set outside
  the inheritance chain that **nothing may extend**. This dermatology proposal therefore adds **no**
  airway/anaphylaxis red flag of its own; §4 flags it for the base owner only.
- **Türkiye-first gap (up front):** the served pack `packages/protocols/specialty/deri_ve_zuhrevi_hastaliklari.yaml`
  is an **L0 draft** (`extends: cluster.medical`) whose header requires the branch clinician to source
  rules from **T.C. Sağlık Bakanlığı / HSGM** protocols and **Turkish specialty-society** guidelines.
  A dedicated Turkish search on 2026-09-20 found one **T.C. Sağlık Bakanlığı HSGM public awareness page**
  (S3, LOW confidence) and otherwise only private-hospital marketing pages — **no versioned Türkiye-first
  clinical guideline document** (see §4). The primary red-flag sources below are therefore international
  (NICE NG12), pending Türkiye-first replacement.
- This file does **not** edit the served L0 pack, `previsit_intake.v1.opt`, `base/intake.yaml`, or any
  other served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG12 Suspected cancer: recognition and referral (melanoma / changing-bleeding mole)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), England
- **Version / year:** NG12, published June 2015 (updated — confirm current update date on sign-off)
- **Citation:** NICE. *Suspected cancer: recognition and referral.* NICE guideline NG12.
- **URL:** https://www.nice.org.uk/guidance/ng12 · verbatim read from NCBI Bookshelf mirror
  https://www.ncbi.nlm.nih.gov/books/NBK555330/ (live nice.org.uk chapter returned HTTP 403)
- **Verbatim (skin cancers — melanoma referral, recommendation number as mirrored 1.7.1 — RE-VERIFY):**
  > "Refer people using a suspected cancer pathway referral for melanoma if they have a suspicious
  > pigmented skin lesion with a weighted 7-point checklist score of 3 or more."
- **Verbatim (weighted 7-point checklist — major features, 2 points each):**
  > "change in size, irregular shape, irregular colour"
- **Verbatim (weighted 7-point checklist — minor features, 1 point each):**
  > "largest diameter 7 mm or more, inflammation, oozing, change in sensation"
- **Corroboration:** the checklist features (change in size / irregular shape / irregular colour; oozing;
  change in sensation) were returned identically by an independent web-search summary → higher confidence
  on the *concept*; the exact recommendation number (1.7.1 vs a 1.9.x numbering in other NG12 versions)
  still requires primary-text re-verification.
- **Note on "7 mm":** the "largest diameter 7 mm or more" minor feature is a **clinician-measured**
  criterion, not a patient self-report threshold — it is **not** turned into a patient-facing question
  here (see §4 gap; consistent with the base-pack posture that a measured/counted value is not a
  layperson trigger).

### S2 — NICE NG12 Suspected cancer: recognition and referral (SCC / BCC — non-healing / suspicious lesion)
- **guideline_id (proposed):** `NICE-NG12`
- **URL:** https://www.ncbi.nlm.nih.gov/books/NBK555330/ (same mirror as S1)
- **Verbatim (squamous cell carcinoma, recommendation as mirrored 1.7.4 — RE-VERIFY):**
  > "Consider a suspected cancer pathway referral for people with a skin lesion that raises the suspicion
  > of squamous cell carcinoma."
- **Verbatim (basal cell carcinoma, recommendation as mirrored 1.7.5 — RE-VERIFY):**
  > "Consider routine referral for people if they have a skin lesion that raises the suspicion of a basal
  > cell carcinoma."
- **Note:** grounds a general **non-healing / new-or-growing skin lesion** intake question (Q8/Q9). BCC
  is *routine* referral in the guideline's own words — so nothing here justifies any elevated candidate
  flag; it is symptom capture only.

### S3 — T.C. Sağlık Bakanlığı HSGM "Cilt Kanseri Farkındalık" (Türkiye-first, PUBLIC awareness page)
- **guideline_id (proposed):** `HSGM-CILT-FARKINDALIK` — **public patient-education / awareness page,
  NOT a versioned clinical guideline**
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü (HSGM), Kanser Dairesi Başkanlığı
- **Version / year:** page undated in the retrieved excerpt — see §4 gap
- **URL:** https://hsgm.saglik.gov.tr/tr/haberler-kanser/cilt-kanseri-farkindalik-ayi.html
- **Verbatim (dikkat edilmesi gereken belirtiler):**
  > "Yeni oluşmuş veya boyut, şekil, renk değiştirmiş benler, lekeler"
  > "Kızarıklık, şişlik, pullanma, düzensizlik, sıvı sızması, kanama"
- **Verbatim (doktora başvuru zamanı):**
  > "Her cilt değişikliği kanser anlamına gelmez; ancak şüpheli bir değişiklik fark edildiğinde vakit
  > kaybetmeden doktora başvurulması önerilir."
- **Confidence: LOW.** Türkiye-first but a public awareness page, not a versioned clinical/guideline
  document. It corroborates the *concepts* of S1 in Turkish (changing mole; bleeding = "kanama") and is a
  useful Türkiye-first anchor, but must be re-verified on the live page and, before it grounds any rule,
  replaced or backed by a **T.C. Sağlık Bakanlığı / HSGM** primary clinical document (see §4).

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Same posture as the cardiology proposal: the committed `.opt` is deliberately **shallow** — composition
and archetype **roots** only, **no at-code (`atNNNN`) leaf nodes**. Each item binds to an archetype
**root** that actually exists in the committed `.opt`; the leaf path is **deferred**
(`openehr_deferred_reason`, INT-032), never fabricated.
Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL).

| # | Proposed captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| 2 | Narrative of the skin/venereology complaint (story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Complaint duration | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Mole/spot changed in size, shape or colour (S1 major features) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Mole/spot bleeding, oozing or crusting (S1 minor: oozing) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Mole/spot itching, inflamed or altered sensation (S1 minor: inflammation, change in sensation) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Non-healing skin sore / lesion (S2 SCC context) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | New or growing skin lump / patch (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Genital / anogenital sore, rash or discharge (venereology — sensitive) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Known skin diagnoses / prior skin cancer / immunosuppression | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current medications (incl. immunosuppressants, new drug before rash) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug / topical / contact allergy | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate triage outcome (rules engine only; max `YELLOW_REVIEW` from LLM) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Notes:
- Item 9 (venereology) captures a **sensitive category** of personal data (sexual health). Per invariant
  18 it needs an inventory annotation `{category, purpose, basis, retention, recipients}` and a
  **consent-scope** decision before capture; per the "stop and ask" rule that decision is a clinician /
  DPO sign-off, not an engineering default — flagged in §4, not resolved here.
- `OBSERVATION.phq9.v1` / `gad7.v1` are **not** present in this committed `.opt` and are not relevant to
  a dermatology red-flag proposal — no wellbeing binding is asserted.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; **one concern per question** (invariant 2: one question per
turn); empathetic; **no diagnosis/treatment/prognosis** language (PolicyGuard-clean — no "kanser",
"melanom" or any diagnostic label in patient copy). Numerals are **spelled out** (invariant 22: the
compiler must expand every digit before TTS; these drafts already do so — e.g. "iki hafta"). **All marked
"CANDIDATE — clinician to approve wording".**

> Triage note for every red-flag-derived item: any level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. Authoritative RED/YELLOW must come
> from `packages/protocols/triage` with a committed `source` snapshot and all three RED axes
> (route × register × location, invariant 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Renumbering, old → new — sections outside §3 still use the old numbers: Q1
unchanged · Q2 removed (duplicates base `hpi.trajectory`; C2 fallback only if that base slot is not
served: "Cilt şikâyetiniz başladığından bu yana nasıl değişti?") · Q3 removed (duplicates the fixed
`sikayet_suresi` slot) · new Q2 (mole/spot gate) · Q4 → Q3 · Q5 → Q4 · Q6 → Q5 (Q3–Q5 asked only if
Q2 yes) · Q7 → Q6 · Q8 → Q7 · Q9 → Q8 (on hold, invariant 18) · Q10 → Q9 · Q11 → current medications
removed (duplicates base `meds_confirmed`) + Q10 (new medication) · Q12 → Q11.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü randevunuzda sizi en çok rahatsız eden cilt sorununu kısaca anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Mole / spot of concern (gate)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (gate
for the S1 pigmented-lesion items Q3–Q5; added per verification §B because "Bu ben ya da leke" had no
antecedent)
> "Cildinizde sizi endişelendiren bir ben ya da leke var mı?"
gen: slot=endiselendiren_ben_leke; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Mole/spot changed in size, shape or colour (if Q2 yes)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG12 major features: "change in size, irregular
shape, irregular colour"); S3 corroborates in TR ("boyut, şekil, renk değiştirmiş benler")
> "Bir beniniz ya da lekeniz son zamanlarda boyut, şekil veya renk olarak değişti mi?"
gen: slot=ben_degisimi; type=boolean; ask_if=endiselendiren_ben_leke == true
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** if a pigmented lesion is changing, per S1 major features.

**Q4 — Mole/spot bleeding, oozing or crusting (if Q2 yes)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S1 (minor feature "oozing"); S3 ("sıvı sızması, kanama")
> "Bu ben ya da lekeden kanama, sıvı sızması ya da kabuklanma oldu mu?"
gen: slot=ben_kanama_sizinti; type=boolean; ask_if=endiselendiren_ben_leke == true
CANDIDATE — clinician to approve wording. Candidate_flag: **candidate — NOT authoritative** (contributes
to the S1 checklist; a single minor feature is not sufficient on its own per S1's score-of-3 rule).

**Q5 — Mole/spot itching, inflamed or altered sensation (if Q2 yes)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S1 (minor features "inflammation", "change in sensation")
> "Bu ben ya da lekede kaşıntı, kızarıklık ya da his değişikliği fark ettiniz mi?"
gen: slot=ben_kasinti_his; type=boolean; ask_if=endiselendiren_ben_leke == true
CANDIDATE — clinician to approve wording. Candidate_flag: **candidate — NOT authoritative** (S1 minor
features).

**Q6 — Non-healing skin sore / lesion** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (NICE
NG12 SCC — "a skin lesion that raises the suspicion of squamous cell carcinoma")
> "Cildinizde uzun süredir iyileşmeyen bir yara ya da kabuk var mı?"
gen: slot=iyilesmeyen_yara; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **candidate — NOT authoritative**; the "how
long" threshold for a skin lesion is **NO SOURCE FOUND** (§4) — NICE NG12 gives no explicit skin-lesion
duration cut-off (unlike the oral-cavity ">3 weeks"), so no numeric threshold is asserted.

**Q7 — New or growing skin lump / patch** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
> "Cildinizde yeni çıkan ya da büyüyen bir kabartı veya leke fark ettiniz mi?"
gen: slot=yeni_buyuyen_kabarti; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — Genital / anogenital sore, rash or discharge (venereology)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: **general intake (venereology symptom capture)** — no
STI-specific guideline threshold retrieved (§4); sensitive category (see §2 note)
> "Genital bölgenizde yara, döküntü ya da olağandışı bir akıntı gibi bir şikâyetiniz var mı?"
gen: slot=genital_sikayet; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. **HOLD (verification finding 22).** Sensitive data: capture
only under an explicit consent scope + inventory annotation (invariant 18); clinician/DPO sign-off
required before this question is enabled.

**Q9 — Known skin diagnoses** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general history
> "Daha önce size bir cilt hastalığı tanısı konuldu mu?"
gen: slot=cilt_tanisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Newly started medication** · archetype: `ACTION.medication.v1` · source: general history (a new
drug before a rash is history the clinician needs; no dose/decision asserted)
> "Son zamanlarda yeni başladığınız bir ilaç oldu mu?"
gen: slot=yeni_ilac; type=boolean
CANDIDATE — clinician to approve wording. Regular medications come from base `meds_confirmed` /
`meds_new_or_stopped`.

**Q11 — Drug / topical / contact allergy** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source:
general intake
> "Herhangi bir ilaca ya da cildinize sürdüğünüz bir ürüne karşı alerjiniz olduğunu fark ettiniz mi?"
gen: slot=ilac_urun_alerjisi; type=boolean
CANDIDATE — clinician to approve wording.

*(11 candidate questions: Q2–Q7 source-derived skin-lesion context (S1/S2); Q8 venereology symptom
capture (unsourced threshold, sensitive, on hold); Q1, Q9–Q11 general intake / history.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first versioned clinical guideline (MoH / HSGM / specialty society, e.g. Türk Dermatoloji
   Derneği).** Only the LOW-confidence HSGM **public awareness** page (S3) and private-hospital marketing
   pages were retrievable. **NO SOURCE FOUND (versioned, authoritative) — clinician must supply** the
   correct **T.C. Sağlık Bakanlığı / HSGM** or Turkish specialty-society document and its version/date, as
   the served L0 pack header itself requires.
2. **Melanoma "7 mm" minor feature as a patient-answerable question.** The S1 minor feature "largest
   diameter 7 mm or more" is a clinician-measured criterion; a layperson self-report form for it is
   **NO SOURCE FOUND — clinician must supply** (or confirm it should stay clinician-side only).
3. **Skin-lesion "non-healing" duration threshold.** Unlike the oral-cavity ">3 weeks", NICE NG12's skin
   recommendations give no explicit duration cut-off for a non-healing skin lesion. Any threshold for Q7
   is **NO SOURCE FOUND — clinician must supply**.
4. **NICE NG12 skin recommendation numbers.** Captured from the NCBI Bookshelf mirror as 1.7.1 (melanoma),
   1.7.4 (SCC), 1.7.5/1.7.6 (BCC); other NG12 versions number skin recommendations differently.
   **Re-verify exact numbers against the primary NICE text on sign-off.**
5. **Venereology (zührevi) STI red-flag thresholds + consent scope.** No STI-specific guideline (e.g. a
   Turkish CYBH / sexual-health guideline or the relevant MoH document) was retrieved. Q9's threshold and
   its **sensitive-data consent scope / inventory annotation** (invariant 18) are **NO SOURCE FOUND —
   clinician + DPO must supply**.
6. **Anaphylaxis / severe drug eruption with breathing difficulty.** This is a **`base.life_threat`**
   family (`rf.anaphylaxis`, `rf.dyspnoea_rest`), which nothing may extend (invariant 7). Its trigger,
   EK-4 acuity, register and RED action scripts are unsupplied **in the base pack** and are the base
   owner's responsibility — **not** added here. Per invariant 21 the RED axes (register × location) are
   not set; under ON_SITE the 112 affordance must be absent, not de-emphasised.
7. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032);
   not fabricated.
8. **Every candidate_flag level and all three RED axes** (route × register × location, invariant 21) —
   deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must supply**, with
   committed `source` snapshots, before anything compiles.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules engine.
- **Inv. 2 / patient-copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/prognosis (no "kanser"/"melanom" in patient copy); marked CANDIDATE.
- **Inv. 7** — airway/anaphylaxis kept in `base.life_threat`; this specialty proposal adds no life-threat rule and does not extend the base set.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 13** — the specialty pack is **L0** (`deri_ve_zuhrevi_hastaliklari.yaml`); an L0 pack resolved for a live session raises. This proposal is review-queue input only, not a promotion.
- **Inv. 18** — venereology (Q9) is a sensitive category: needs `{category, purpose, basis, retention, recipients}` + consent scope before capture; flagged, not resolved.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — numerals in drafts are spelled out; compiler must expand before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S3 for that block but does not itself commit a snapshot, and does not edit the served pack.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
