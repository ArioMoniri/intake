# AMATEM (Addiction / Substance-use Treatment) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: AMATEM (Alkol ve Madde
Bağımlılığı — addiction / substance-use treatment)
Purpose: patient-owned, Turkish-first **pre-visit intake** (supportive context capture for a
clinician-ready note) — **not** diagnosis, not triage authority, **not** a screening instrument.
This file is a *proposal for a clinician to sign off*. It assigns **no** authoritative
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- **Supportive, non-stigmatizing intake only.** Wording is person-first, warm and B1; it never
  labels the person, never uses "bağımlı/madde bağımlısı" as a description of the patient, and never
  asserts diagnosis, treatment or prognosis (invariant 2). NICE CG115 (S3) is quoted verbatim as the
  basis for this stance: work *"in a supportive, empathic and non-judgemental manner"*.
- **No crisis / self-harm / suicide screening here — by design.** Any consent-independent crisis or
  self-harm path is **out of scope for this pre-visit intake** and belongs to the base life-threat
  layer (`base.life_threat`, invariant 7) and the crisis-lexicon work (**HB-C17**, still open;
  C-SSRS is licence-BLOCKED, **HB-L2**). This file introduces **no** RED, **no** crisis trigger, and
  **no** suicide item. If a patient volunteers crisis content, that is handled by the signed
  life-threat layer, not by anything proposed here.
- **Not an instrument.** WHO ASSIST and WHO AUDIT are cited **as sources for question topics only**.
  They are not embedded, scored, or reproduced verbatim (an instrument whose licence is not `GO`
  does not compile — clinical-content rule). The candidate questions below are original B1 Turkish
  wording, not instrument items.
- **Triage:** per invariant 1, only `packages/protocols/triage` rules can produce RED/YELLOW.
  Nothing here is flagged; every item is ordinary supportive intake. No `candidate_flag` is raised
  in this specialty proposal.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval. Before sign-off each verbatim sentence MUST be re-checked against the
  **primary published text** and committed as a **verbatim source snapshot** with a full `source:`
  block. Until then any derived content stays `status: draft_needs_source` and does not compile.
- **No accuracy claims** (invariant 20): no sensitivity/specificity/AUROC figure is reproduced here,
  even where a source stated one.
- This file does **not** edit `packages/protocols/specialty/amatem.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — WHO ASSIST V3.0 (topics: substances used, frequency, craving, concern from others, cutting down)
- **guideline_id (proposed):** `WHO-ASSIST-V3`
- **Publishing body:** World Health Organization (ASSIST Working Group)
- **Version / year:** V3.0; development paper 2002
- **Citation:** WHO ASSIST Working Group. *The Alcohol, Smoking and Substance Involvement Screening
  Test (ASSIST): development, reliability and feasibility.* Addiction. 2002;97(9):1183–1194. PMID
  12199834.
- **URL (tool page):** https://www.who.int/publications/i/item/978924159938-2 · **development
  paper:** https://pubmed.ncbi.nlm.nih.gov/12199834/
- **Retrieved (structure, from search-result summary — NOT a page-verbatim string):**
  the ASSIST comprises questions covering tobacco, alcohol, cannabis, cocaine, amphetamine-type
  stimulants, inhalants, sedatives, hallucinogens, opioids and "other drugs"; it screens for all
  levels of problem or risky substance use, with an initial lifetime-use screening question followed
  by questions about the preceding three months (use frequency, strong desire/urge, problems,
  concern expressed by others, and attempts to cut down).
- **Confidence: MEDIUM for structure, gap for verbatim.** The instrument PDF is copyrighted and was
  returned as binary/encoded on every retrieval attempt, so **exact item wording was NOT captured**
  and is **not** reproduced (see §4 gap 1). Used only to justify *which topics* an intake may cover.

### S2 — WHO AUDIT (topic: alcohol — consumption, dependence indicators, harm incl. concern from others)
- **guideline_id (proposed):** `WHO-AUDIT`
- **Publishing body:** World Health Organization
- **Version / year:** WHO/MSD/MSB/01.6a (2001, 2nd ed.)
- **Citation:** Babor TF, Higgins-Biddle JC, Saunders JB, Monteiro MG. *AUDIT: The Alcohol Use
  Disorders Identification Test — Guidelines for Use in Primary Care.* 2nd ed. WHO; 2001.
- **URL:** https://www.who.int/publications/i/item/WHO-MSD-MSB-01.6a
- **Retrieved (domain structure, verbatim from retrieved summary):**
  > "Questions 1 to 3 ask about consumption of alcohol (frequency, quantity … and consumption likely
  > to cause impairment); Questions 4 to 6 address possible dependence on alcohol; and Questions 7–10
  > address harmful alcohol use, including concern expressed by others."
- **Confidence: MEDIUM for domains, gap for verbatim items.** The exact 10-item wording could not be
  retrieved from a clean primary page (PDFs returned binary) and is **not** reproduced here (§4 gap
  2). AUDIT-C (first three items) is noted as the short form; no cut-off/score is used here.

### S3 — NICE CG115 Alcohol-use disorders (supportive, non-judgemental assessment; goals; motivation)
- **guideline_id (proposed):** `NICE-CG115`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** CG115, published 2011 (updated); retrieved reprint noted a 2013 evidence update
- **Citation:** NICE. *Alcohol-use disorders: diagnosis, assessment and management of harmful drinking
  (high-risk drinking) and alcohol dependence (CG115).*
- **URL:** https://www.nice.org.uk/guidance/cg115/chapter/Recommendations · reprint:
  https://www.ncbi.nlm.nih.gov/books/NBK552038/
- **Verbatim (approach):**
  > "in a supportive, empathic and non-judgemental manner"
  > "stigma and discrimination are often associated with alcohol misuse"
- **Verbatim (motivational intervention):**
  > "For all people who misuse alcohol, a motivational intervention should be carried out as part of
  > the initial assessment."
  > "a persuasive and supportive rather than an argumentative and confrontational position"
- **Retrieved (comprehensive assessment — summary):** covers history of alcohol and other substance
  use, severity of dependence, need for assisted withdrawal, risk, and comorbid mental/physical
  conditions.
- **Confidence: MEDIUM–HIGH** for the quoted approach sentences (returned consistently); exact
  recommendation numbers and the comprehensive-assessment wording MUST be reconciled against the
  primary text before sign-off.

### S4 — T.C. Sağlık Bakanlığı AMATEM (service description — referral/how-to-apply, NOT a clinical guideline)
- **guideline_id (proposed):** `TR-AMATEM-SERVICE` (public service-description pages, **not** a
  versioned clinical guideline)
- **Publishing body:** T.C. Sağlık Bakanlığı hospital pages (e.g. AMATEM birimleri)
- **Version / year:** undated service pages
- **URL:** https://mehmetakifinaneah.saglik.gov.tr/TR-590101/alkol-ve-madde-bagimliligi-tedavi-merkezi-amatem.html ·
  https://torosdh.saglik.gov.tr/TR-621671/madde-bagimliligi-tedavi-merkezi-amatem.html
- **Retrieved (service description — summary, NOT a clinical red-flag):** AMATEM is the MoH unit
  where alcohol/substance-use care is delivered by a team of physician, psychologist and social
  worker; application is via MHRS/182 to the psychiatry or addiction clinic.
- **Confidence: LOW.** Service/wayfinding pages only. **No versioned Türkiye-first clinical
  assessment guideline was retrieved** (§4 gap 3); no verbatim clinical sentence is drawn from these
  pages. Used only to confirm the AMATEM care-team framing that the intake copy should respect.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots-only binding, leaf `atNNNN` paths **deferred** (`openehr_deferred_reason`, INT-032 / HB-C12);
nothing fabricated. Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / what support is wanted | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative in the person's own words (story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Which substances the person wishes to talk about (S1 lifetime-use topic) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Frequency of use in the recent period (S1/S2 consumption topic) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Strong urge / craving (S1 topic) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Effect on daily life / health the person wants help with (S1/S2 harm topic) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Concern expressed by people close to them (S1/S2 "concern from others") | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Previous attempts to cut down / what helped (S1 topic; strengths-based) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Goals / hopes from this visit (S3 motivation & goals) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| 10 | Prior support received & known health conditions (S3 comprehensive assessment) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Support around the person (family / friends) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate triage outcome (**none raised in this specialty**; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Notes:
- No `symptom_sign` item here is a red-flag; they capture supportive context, not urgency.
- `adverse_reaction_risk` root is available if the clinician wants a medication-allergy item; it is
  omitted from the 12 to keep the set focused on supportive substance-use intake.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; one concern per question (invariant 2); warm, supportive,
**non-stigmatizing**, no diagnosis/treatment/prognosis language, no alarming wording. **All marked
"CANDIDATE — clinician to approve wording".** No bare digits (invariant 22). **No crisis/self-harm
item appears — by design (see §0).**

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Findings 24 and 28 apply. Renumbering, old → new — sections outside
§3 still use the old numbers: Q1–Q7 keep their numbers · Q8 → Q8 (tried to cut down) + Q9 (what
helped, if Q8) · Q9 removed (base `patient_goals`) · Q10 → Q10 (prior support) + Q11 (other health
conditions) · Q11 removed (base meds) · Q12 → Q12.

**Q1 — Reason for visit / support wanted** · archetype: `EVALUATION.reason_for_encounter.v1` · source:
general intake (S3 supportive framing)
> "Bugün hangi konuda destek almak istersiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Own-words narrative** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Yaşadıklarınızı kendi sözlerinizle, rahat hissettiğiniz kadar anlatabilir misiniz?"
gen: slot=kendi_sozleriyle
CANDIDATE — clinician to approve wording.

**Q3 — Which substances to talk about** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (topic:
substances used)
> "Bugün hangi madde ya da alışkanlıkla ilgili konuşmak istersiniz?"
gen: slot=konusulacak_madde
CANDIDATE — clinician to approve wording. Non-stigmatizing; no label applied to the person.

**Q4 — Frequency in recent period** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (frequency
topic) / S2 (consumption domain)
> "Son zamanlarda bunu ne sıklıkla kullandığınızı anlatır mısınız?"
gen: slot=kullanim_sikligi
CANDIDATE — clinician to approve wording. ASSIST's three-month window and the yes/no "paylaşmak ister
misiniz" mismatch are dropped (finding 24). Kept as history, not scored. ASSIST shadow: whether ASSIST
should instead be delivered verbatim through the instrument path (with a new licence row) is a
clinician decision pending.

**Q5 — Craving / strong urge** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (craving topic)
> "Bazen kullanmak için güçlü bir istek ya da dürtü hissediyor musunuz?"
gen: slot=guclu_istek; type=boolean
CANDIDATE — clinician to approve wording. ASSIST shadow (finding 24): clinician decision pending, as
Q4.

**Q6 — Effect on daily life / health** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1/S2 (harm
topic)
> "Bu durum günlük yaşamınızı ya da sağlığınızı etkiliyor mu?"
gen: slot=gunluk_yasam_etkisi; type=boolean
CANDIDATE — clinician to approve wording. Supportive, non-judgemental (S3).

**Q7 — Concern from people close to them** · archetype: `OBSERVATION.story.v1` · source: S1/S2 ("concern
expressed by others")
> "Yakınlarınızdan biri bu konuda size endişesini dile getirdi mi?"
gen: slot=yakin_endisesi; type=boolean
CANDIDATE — clinician to approve wording. Gentle, no blame. ASSIST shadow (finding 24): clinician
decision pending, as Q4.

**Q8 — Prior attempts to cut down** · archetype: `OBSERVATION.story.v1` · source: S1 (cutting-down topic)
> "Daha önce azaltmayı ya da bırakmayı denediniz mi?"
gen: slot=azaltma_denemesi; type=boolean
CANDIDATE — clinician to approve wording. ASSIST shadow (finding 24): clinician decision pending, as
Q4.

**Q9 — What helped (strengths-based)** · archetype: `OBSERVATION.story.v1` · source: S1 (cutting-down
topic)
> "O zaman size en çok ne iyi geldi?"
gen: slot=iyi_gelen; ask_if=azaltma_denemesi == true
CANDIDATE — clinician to approve wording. Strengths-based framing.

**Q10 — Prior support** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S3 (comprehensive
assessment)
> "Daha önce bu konuda bir destek aldınız mı?"
gen: slot=onceki_destek; type=boolean
CANDIDATE — clinician to approve wording. "destek" (support), not "tedavi", to stay PolicyGuard-clean
and supportive.

**Q11 — Other known health conditions** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S3
(comprehensive assessment)
> "Bilmemizi istediğiniz başka bir sağlık durumunuz var mı?"
gen: slot=diger_saglik_durumu
CANDIDATE — clinician to approve wording.

**Q12 — Support around the person** · archetype: `OBSERVATION.story.v1` · source: general intake (S3
supportive relationship)
> "Bu süreçte yanınızda olan, size destek olan kişiler var mı?"
gen: slot=sosyal_destek; type=boolean
CANDIDATE — clinician to approve wording.

*(12 candidate questions after revision — all supportive intake; none is a crisis/red-flag item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **WHO ASSIST V3.0 exact item wording** — the questionnaire PDF is copyrighted and returned as
   binary/encoded on every retrieval attempt, so verbatim item text was **NOT captured** and is
   deliberately **not** reproduced (and would not be embedded even if captured — instrument-licence
   rule). **NO SOURCE FOUND (verbatim item text) — clinician must supply** from a licensed copy if
   any instrument is ever to be used; the candidate questions above are original, not ASSIST items.
2. **WHO AUDIT exact 10-item wording** — only the domain structure (Q1–3 / Q4–6 / Q7–10) was
   retrieved; clean primary item text was **NOT captured**. **NO SOURCE FOUND (verbatim item text) —
   clinician must supply.**
3. **Türkiye-first versioned clinical guideline for substance-use assessment** — only MoH AMATEM
   service/wayfinding pages (S4, LOW confidence) and international guidance were retrievable. A
   versioned T.C. Sağlık Bakanlığı / Türkiye Psikiyatri Derneği assessment guideline was **NOT
   located**. **NO SOURCE FOUND (versioned primary) — clinician must supply** the correct
   Türkiye-first source and its version/date.
4. **Turkish-validation status of any screening instrument for this specialty** (ASSIST-tr, AUDIT-tr
   and their licence terms) — not confirmed here; no instrument is proposed for compilation. **NO
   SOURCE FOUND (licence + Turkish validation) — clinician must supply** before any instrument is
   used. (Cross-ref: instruments without `GO` licence do not compile.)
5. **Crisis / self-harm handling** — intentionally **absent** from this proposal; it belongs to
   `base.life_threat` (invariant 7) and the crisis-lexicon work (**HB-C17**, open; C-SSRS BLOCKED,
   **HB-L2**). Not a gap to fill *here* — noted so a reviewer does not mistake its absence for an
   oversight.
6. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032 / HB-C12); not fabricated.
7. **Exact NICE CG115 recommendation numbers / dates** — the quoted approach sentences were retrieved
   consistently, but recommendation numbering and publication/update dates MUST be reconciled against
   the primary text before the `source` block is committed.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no `candidate_flag` raised (supportive intake only).
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, warm, non-stigmatizing, no
  diagnosis/treatment/prognosis; marked CANDIDATE. "destek" preferred over "tedavi".
- **Inv. 7** — crisis/self-harm deliberately left to the base life-threat layer; nothing here
  extends or relaxes it.
- **Inv. 10** — no scripted red-flag `text_tr` is proposed (there are no red-flags in this set).
- **Inv. 20** — no accuracy/performance figures reproduced.
- **Inv. 22** — no bare digits in patient text (the three-month window was dropped from Q4, finding 24); compiler must expand before TTS.
- **Clinical content rule / instrument licence** — ASSIST/AUDIT cited as topic sources only, not
  embedded or scored; an instrument without a `GO` licence does not compile.
- **HB-C1** — this pack awaits clinician sign-off; NOT served. **HB-C17 / HB-L2** — crisis path and
  C-SSRS remain human-blocked and out of scope here.
