# Cerrahi Onkoloji (Surgical Oncology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Cerrahi Onkoloji (Surgical
Oncology)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom + history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no**
clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**,
  written as *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The
  guideline's own referral wording is quoted verbatim; no level is asserted.
- **Not a diagnosis.** The word *kanser* (cancer) never appears in a patient-facing question as an
  attribution about the patient's own condition; questions capture symptoms and history in neutral,
  B1 language (invariant 2, PolicyGuard). Asking whether the patient has *previously received* a
  diagnosis is intake history, not diagnosing.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / search summary). The NICE NG12 recommendation **numbers** and
  the exact **age thresholds/wording** in particular MUST be re-checked against the **primary
  published text** and committed as a **verbatim source snapshot** with a full `source:
  {guideline_id, version, date, url, retrieved_on}` block before sign-off. Until then any derived
  rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- **No accuracy claims** (invariant 20): no sensitivity/specificity/AUROC/PPV figure is reproduced
  here, even where a source stated one (NG12's 3% PPV threshold is referenced only as the reason
  children have a lower threshold, never as a product property).
- This file does **not** edit `packages/protocols/specialty/cerrahi_onkoloji.yaml` (an L0 draft that
  raises if served) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG12 Suspected cancer: recognition and referral (adult referral red flags)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** NG12, first published June 2015, updated (recommendations dated 2015 / 2023 /
  2025 in the retrieved text)
- **Citation:** NICE. *Suspected cancer: recognition and referral (NG12).*
- **URL:** https://www.nice.org.uk/guidance/ng12 · accessible mirror (retrieved):
  https://www.ncbi.nlm.nih.gov/books/NBK555330/
- **Verbatim (breast lump, rec. 1.4.1):**
  > "Refer people using a suspected cancer pathway referral for breast cancer if they are aged 30
  > and over and have an unexplained breast lump with or without pain"
- **Verbatim (dysphagia, rec. 1.2.1):**
  > "Refer people using a suspected cancer pathway referral for oesophageal cancer if they have
  > dysphagia"
- **Verbatim (post-menopausal bleeding, rec. 1.5.10):**
  > "Refer women using a suspected cancer pathway referral for endometrial cancer if they are aged
  > 55 and over with post-menopausal bleeding"
- **Verbatim (visible haematuria, rec. 1.6.4):**
  > "Refer people using a suspected cancer pathway referral for bladder cancer if they are aged 45
  > and over and have unexplained visible haematuria without urinary tract infection"
- **Verbatim (haemoptysis, rec. 1.1.x):**
  > "Refer people using a suspected cancer pathway referral for lung cancer if they are aged 40 and
  > over with unexplained haemoptysis."
- **Verbatim (safety-netting, rec. 1.15.2):**
  > "Consider a review for people with any symptom that is associated with an increased risk of
  > cancer, but who do not meet the criteria for referral or other investigative action."
- **Retrieved (unexplained weight loss, rec. 1.13.2 — captured with ellipsis, NOT a clean
  page-verbatim string):** the guideline directs urgent investigation / a suspected-cancer pathway
  referral for people with unexplained weight loss (a symptom shared by several cancers). Exact
  wording and the age/context qualifiers were returned abbreviated → see §4 gap 1.
- **Retrieved (change in bowel habit / rectal bleeding, rec. 1.3.1 — abbreviated):** the guideline
  offers quantitative faecal immunochemical testing (FIT) to adults with an unexplained change in
  bowel habit and to those aged 50 and over with unexplained rectal bleeding. Exact wording → §4
  gap 1.
- **Confidence: MEDIUM–HIGH** for the six clean verbatim referral sentences (each returned as a
  complete, well-formed recommendation); **the recommendation numbers and the weight-loss / FIT
  wording require primary-text re-verification** before any `source` snapshot is committed.

### S2 — WHO cancer early diagnosis (general "know the symptoms and seek care" framing)
- **guideline_id (proposed):** `WHO-EARLY-DX-2017` (WHO news/programme item, **not** a versioned
  clinical guideline)
- **Publishing body:** World Health Organization
- **Version / year:** 2017 launch of the *Guide to cancer early diagnosis*
- **URL:** https://www.who.int/news/item/03-02-2017-early-cancer-diagnosis-saves-lives-cuts-treatment-costs ·
  programme: https://www.who.int/activities/promoting-cancer-early-diagnosis
- **Verbatim (step one of early diagnosis):**
  > "improve public awareness of different cancer symptoms and encourage people to seek care when
  > these arise"
- **Retrieved (warning-sign families — from the retrieved summary, NOT a page-verbatim list):**
  unusual bleeding or discharge, sores that do not heal, changes in bowel or bladder habits, and
  lumps in the breast or other parts of the body.
- **Confidence: LOW–MEDIUM.** A public-awareness programme item, not a versioned clinical guideline.
  Used only to ground the *neutral "if you notice X, it is worth telling us" framing*, never a
  referral threshold. Re-verify on the live page before it grounds any script.

### S3 — Türkiye-first versioned clinical guideline (surgical oncology / suspected-cancer referral)
- **Status: NO SOURCE FOUND (versioned primary).** Searches returned only T.C. Sağlık Bakanlığı /
  society *service-description* and public-awareness pages, not a versioned, dated clinical
  guideline document with citable referral wording. See §4 gap 4. No verbatim clinical sentence is
  drawn from any Turkish source here; the branch clinician must supply the correct Türkiye-first
  primary source (T.C. Sağlık Bakanlığı HSGM / Türk Cerrahi Onkoloji Derneği) and its version/date.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots-only binding; the committed `.opt` pins the composition and archetype **roots** with **no
at-code (`atNNNN`) leaf nodes**, so each item binds to a **root** and the leaf path is **deferred**
(`openehr_deferred_reason`, INT-032 / HB-C12) — never fabricated. Composition root:
`openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the current complaint (story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | New lump / swelling / mass (S1 1.4.1; S2 "lumps") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Unexplained weight loss (S1 1.13.2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Unexplained bleeding — rectal / urinary / other (S1 1.3.1/1.5.10/1.6.4; S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Difficulty swallowing — dysphagia (S1 1.2.1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Change in bowel / bladder habit (S1 1.3.1; S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Persistent / worsening pain (S2 general "seek care") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Known cancer diagnosis / prior surgery, radiotherapy, chemotherapy | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 10 | Current medications (incl. anticoagulants, relevant pre-op) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 11 | Drug / substance allergy or serious adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 12 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 13 | **Family history of cancer** (relevant to surgical oncology) | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 13: the committed `.opt` exposes no family-history archetype root, so capturing family
  cancer history has **no export target today → export blocked (INT-041 posture)**; do not invent an
  at-code path. Clinician/architecture decision needed (cross-ref HB-C12, candidate INT-032
  archetype addition).
- PHQ-9 / GAD-7 wellbeing archetypes (`OBSERVATION.phq9.v1` / `OBSERVATION.gad7.v1`) exist in the
  `.opt` and may be added later under consent; their content is out of scope for this surgical-
  oncology symptom proposal and no question for them is drafted here.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; one concern per question (invariant 2: one question per
turn); empathetic; no diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician
to approve wording".** No bare digits appear in the patient text (invariant 22); any numeral in the
English source quotes above is source text, not TTS copy.

> Triage note for every red-flag-derived item: the level shown is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED/YELLOW must come from `packages/protocols/triage` with a committed `source`
> snapshot and all three RED axes (route × register × location, invariant 21), none of which are
> supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Findings 14 and 17 apply. Renumbering, old → new — sections outside §3
still use the old numbers: Q1–Q8 keep their numbers · Q9 → Q9 (earlier cancer diagnosis) + Q10
(treated for it, if Q9) · Q10 removed (base meds + `anticoagulant_use`) · Q11 removed (base
`allergies` + `allergy_reaction`) · Q12 → Q11.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü görüşmede sizi hekime getiren en önemli konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Narrative / story** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu durumu nasıl fark ettiğinizi kendi sözlerinizle anlatır mısınız?"
gen: slot=nasil_fark_edildi
CANDIDATE — clinician to approve wording. "When" is asked by base `onset_date`.

**Q3 — New lump / swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (rec.
1.4.1 unexplained lump — re-cite pending, see note) + S2 (WHO "lumps in the breast or other parts of the body")
> "Vücudunuzda yeni fark ettiğiniz bir şişlik ya da sertlik var mı?"
gen: slot=yeni_sislik_sertlik; type=boolean
CANDIDATE — clinician to approve wording. Finding 17: a whole-body lump is better anchored on the
NG12 soft-tissue lump recommendation (unexplained lump increasing in size) than on the breast
recommendation; verify and re-cite before sign-off. Candidate_flag: **YELLOW_REVIEW (candidate,
pending clinician + rules-engine confirmation — NOT authoritative)** if an unexplained lump, per S1.

**Q4 — Unexplained weight loss** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (rec. 1.13.2)
> "Son zamanlarda istemediğiniz hâlde kilo verdiğinizi fark ettiniz mi?"
gen: slot=istemsiz_kilo_kaybi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** per S1 unexplained weight loss (exact NG12 wording pending re-verification, §4).

**Q5 — Unexplained bleeding** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (rectal 1.3.1 /
post-menopausal 1.5.10 / visible haematuria 1.6.4) + S2
> "Son zamanlarda dışkıda, idrarda ya da başka bir yerden beklenmedik kanama oldu mu?"
gen: slot=beklenmedik_kanama; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** per the S1 unexplained-bleeding referral routes.

**Q6 — Difficulty swallowing (dysphagia)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(rec. 1.2.1 "if they have dysphagia")
> "Yemek ya da içecekleri yutarken güçlük yaşıyor musunuz?"
gen: slot=yutma_guclugu; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** per S1 dysphagia (NG12 routes dysphagia with no age threshold).

**Q7 — Change in bowel / bladder habit** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (rec.
1.3.1 change in bowel habit) + S2 (WHO "changes in bowel or bladder habits")
> "Bağırsak ya da idrar alışkanlığınızda son zamanlarda geçmeyen bir değişiklik oldu mu?"
gen: slot=bagirsak_idrar_aliskanligi_degisimi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: candidate only (S1 change-in-bowel-habit
wording pending re-verification, §4); the authoritative level is the rules engine's.

**Q8 — Persistent / worsening pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 general
("encourage people to seek care when these arise"); **NICE site-specific abdominal-pain criteria are
age- and site-specific — NOT captured verbatim (§4 gap 2)**
> "Geçmeyen ya da giderek artan bir ağrınız var mı?"
gen: slot=gecmeyen_agri; type=boolean
CANDIDATE — clinician to approve wording. No candidate_flag from S2 alone; a specific pain red flag
needs the primary NG12 site/age text (§4).

**Q9 — Known cancer diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: n/a (history)
> "Daha önce size kanser tanısı konuldu mu?"
gen: slot=onceki_kanser_tanisi; type=boolean
CANDIDATE — clinician to approve wording. History item: it asks about a *prior* diagnosis and does not
diagnose. Naming "kanser" is inconsistent with deri and hematoloji, which avoid it; confirm that the
PolicyGuard diagnosis arm tells asking about a known diagnosis apart from asserting one.

**Q10 — Prior cancer treatment** · archetype: `EVALUATION.problem_diagnosis.v1` · source: n/a (history)
> "Bunun için ameliyat, ışın ya da ilaç tedavisi gördünüz mü?"
gen: slot=onceki_kanser_tedavisi; type=boolean; ask_if=onceki_kanser_tanisi == true
CANDIDATE — clinician to approve wording.

**Q11 — Family history of cancer** · archetype: **export blocked (INT-041 posture)** · source: general
intake
> "Ailenizde kanser tanısı almış yakın akrabalarınız var mı?"
gen: slot=ailede_kanser; type=boolean
CANDIDATE — clinician to approve wording. Note: **no openEHR export target** (item 13, §2) — capture
is proposed but export is blocked until an archetype root is authored.

*(11 candidate questions after revision.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **NG12 unexplained-weight-loss and FIT/change-in-bowel-habit exact wording + recommendation
   numbers** — returned abbreviated (with ellipsis) rather than as clean page-verbatim strings.
   **NO SOURCE FOUND (clean verbatim) — clinician must re-capture** from the primary NG12 text and
   commit the snapshot; the six clean verbatim sentences (S1) still need their recommendation
   numbers reconciled.
2. **NICE site-specific pain / abdominal-mass red-flag criteria** (e.g. abdominal pain + age +
   associated symptom for colorectal/pancreatic/ovarian) — **NOT captured verbatim**; NG12 states
   these are age- and site-specific and the enumerated criteria were not returned. **NO SOURCE
   FOUND (verbatim) — clinician must supply** from the primary text.
3. **"Seek urgent care / call emergency services" verbatim as a red-flag action script** — NG12 is a
   *referral* guideline for clinicians, not a patient "when to seek help" script, and no verbatim
   patient-facing emergency instruction was retrieved. **NO SOURCE FOUND (patient action verbatim) —
   clinician must supply**, ideally from a T.C. Sağlık Bakanlığı primary document.
4. **Türkiye-first versioned clinical guideline (surgical oncology / suspected-cancer referral)** —
   only service-description and public-awareness pages were retrievable; **no versioned, dated
   Turkish clinical guideline** was located (S3). **NO SOURCE FOUND — clinician must supply** the
   correct Türkiye-first primary source (T.C. Sağlık Bakanlığı HSGM / Türk Cerrahi Onkoloji Derneği)
   and its version/date.
5. **ESMO / site-specific society guideline verbatim** — not retrieved in this pass. **NO SOURCE
   FOUND (verbatim) — clinician to add** the relevant ESMO / specialty-society guideline if it is to
   ground a rule.
6. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant
   21) — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must
   supply**, with committed `source` snapshots, before anything compiles.
7. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032 / HB-C12); not fabricated. Family history (item 13) has **no archetype root** → export
   blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, empathetic, no diagnosis/
  treatment/prognosis; "kanser" never used as an attribution about the patient's condition; marked
  CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 20** — no accuracy/PPV/performance figures reproduced as product properties.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare digits in patient text; compiler must expand any number before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S2
  but does not itself commit a snapshot; S3 (Türkiye-first) is an open gap.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
