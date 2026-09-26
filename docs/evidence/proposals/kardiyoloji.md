# Kardiyoloji (Cardiology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-19 · Specialty: Kardiyoloji (Cardiology)
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
  and is written as *"candidate, pending clinician + rules-engine confirmation — NOT
  authoritative"*. The guideline's own urgency wording is quoted verbatim; no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-19 via
  automated web retrieval (WebFetch). Before sign-off, each verbatim sentence MUST be re-checked
  against the **primary published text** and, per the clinical-content rule, committed as a
  **verbatim source snapshot** with a full `source: {guideline_id, version, date, url,
  retrieved_on}` block. Until then any derived rule stays `status: draft_needs_source` and does
  **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/kardiyoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — ESC 2023 Acute Coronary Syndromes (chest pain red flags)
- **guideline_id (proposed):** `ESC-ACS-2023`
- **Publishing body:** European Society of Cardiology (ESC), Task Force on ACS
- **Version / year:** 2023 guideline, published Vol 13 Issue 1, January 2024
- **Citation:** Byrne RA, et al. *2023 ESC Guidelines for the management of acute coronary
  syndromes.* European Heart Journal: Acute Cardiovascular Care. 2024;13(1):55–161.
- **URL:** https://academic.oup.com/ehjacc/article/13/1/55/7280662 · DOI: 10.1093/ehjacc/zuad107
- **Verbatim (§3.1.1 Clinical Presentation):**
  > "It is important that awareness of the symptoms associated with ACS is high among the general
  > population, in particular red flag symptoms such as prolonged chest pain (>15 min) and/or
  > recurrent pain within 1 h, which should prompt patients or other members of the public to seek
  > urgent medical help."
- **Verbatim (§3.1.1 Clinical Presentation):**
  > "Chest pain-equivalent symptoms include dyspnoea, epigastric pain, and pain in the left or
  > right arm or neck/jaw."
- **Corroboration:** the ">15 min / recurrent within 1 h" wording was returned identically by an
  independent web search summary and the page fetch → higher confidence. Still requires primary-text
  re-verification.

### S2 — ESC 2018 Syncope (high-risk features)
- **guideline_id (proposed):** `ESC-SYNCOPE-2018`
- **Publishing body:** European Society of Cardiology (ESC)
- **Version / year:** 2018
- **Citation:** Brignole M, et al. *2018 ESC Guidelines for the diagnosis and management of
  syncope.* European Heart Journal. 2018;39(21):1883–1948.
- **URL:** https://academic.oup.com/eurheartj/article/39/21/1883/4939241 · DOI: 10.1093/eurheartj/ehy037
- **Verbatim (high-risk features):**
  > "Syncope during exertion or when supine"
  > "Sudden onset palpitation immediately followed by syncope"
  > "Family history of unexplained sudden death at young age"
  > "Presence of structural heart disease or coronary artery disease"
  > "Syncope without prodrome"
  > "Palpitations at the time of syncope"
- **Note:** these are individual high-risk row labels captured from the guideline's high-risk
  feature tables (reported by the fetch as Table 5/6/7). The exact table number for each row MUST be
  reconciled against the primary text before sign-off.

### S3 — ESC 2021 Heart Failure (cardinal symptoms)
- **guideline_id (proposed):** `ESC-HF-2021`
- **Publishing body:** European Society of Cardiology (ESC) with the Heart Failure Association (HFA)
- **Version / year:** 2021 (a 2023 Focused Update exists — see §4 gap)
- **Citation:** McDonagh TA, et al. *2021 ESC Guidelines for the diagnosis and treatment of acute
  and chronic heart failure.* European Heart Journal. 2021;42(36):3599–3726.
- **URL:** https://academic.oup.com/eurheartj/article/42/36/3599/6358045 · DOI: 10.1093/eurheartj/ehab368
- **Verbatim (§3.1):**
  > "Heart failure is not a single pathological diagnosis, but a clinical syndrome consisting of
  > cardinal symptoms (e.g. breathlessness, ankle swelling, and fatigue)"
- **Note:** orthopnoea and paroxysmal nocturnal dyspnoea were NOT captured verbatim from the
  accessible excerpt — see §4 gap.

### S4 — Türk Kardiyoloji Derneği public education ("call 112")
- **guideline_id (proposed):** `TKD-TURKIYENINKALBI` (public patient-education page, NOT a clinical
  guideline document)
- **Publishing body:** Türk Kardiyoloji Derneği (Turkish Cardiology Association)
- **Version / year:** page undated in the retrieved excerpt — see §4 gap
- **URL:** https://turkiyeninkalbi.com/toplum/
- **Verbatim (Turkish):**
  > "Belirtiler kalp krizini düşündürüyorsa vakit kaybetmeden 112'yi arayın."
- **Confidence: LOW.** Single-source, retrieved via automated fetch from a public-facing education
  page (not a versioned guideline). Must be re-verified on the live page and, ideally, replaced or
  backed by a **T.C. Sağlık Bakanlığı** primary document before it grounds any RED action script.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes**. Per its own header, a slot whose leaf path is not
yet authored carries **`openehr_deferred_reason`** (INT-032, P3 export tier) — it is **not**
invented. So each item below binds to an archetype **root**; the specific leaf path is **deferred**,
never fabricated.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of current cardiac complaint (story of present illness) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Chest pain — presence | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Chest pain — duration / recurrence (S1 red flag) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Dyspnoea / breathlessness (S1 equivalent; S3 cardinal) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Syncope / near-syncope (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Syncope on exertion (S2 high-risk) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Palpitations (S2 links palpitation→syncope) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Ankle / leg swelling — oedema (S3 cardinal) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Known cardiac diagnoses (prior MI, HF, arrhythmia, hypertension) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current cardiac / blood-pressure medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 13 | Depression screening (if consented, wellbeing) | `openEHR-EHR-OBSERVATION.phq9.v1` | OBSERVATION | deferred (INT-032) |
| 14 | Anxiety screening (if consented, wellbeing) | `openEHR-EHR-OBSERVATION.gad7.v1` | OBSERVATION | deferred (INT-032) |
| 15 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 16 | **Family history of sudden death at young age** (S2 high-risk) | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 16: the committed `.opt` exposes no family-history archetype root (`CLUSTER.provenance` is the
  only CLUSTER named in files/03 §7 and is itself ABSENT from the template). Capturing family history
  therefore has no export target today → **export blocked (INT-041 posture)**; do not invent an
  at-code path. Clinician/architecture decision needed (candidate: INT-032 archetype addition).
- Items 13–14 (PHQ-9/GAD-7) are the consented wellbeing instruments, included only for completeness of
  binding; their content/cut-offs are out of scope for this cardiology red-flag proposal.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; one concern per question (invariant 2: one question per
turn); empathetic; no diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to
approve wording".** Any numeral shown is written for readability only; per invariant 22 the protocol
compiler must expand every digit to Turkish orthography before TTS (e.g. `15` → "on beş") — the
drafts below already spell such values out.

> Triage note for every red-flag-derived item: the level shown is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED/YELLOW must come from `packages/protocols/triage` with a committed `source`
> snapshot and all three RED axes (route × register × location, invariant 21), none of which are
> supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: n/a (intake)
> "Bugünkü görüşmede sizi en çok rahatsız eden konu nedir?"
CANDIDATE — clinician to approve wording. Revised 2026-09-26 per
docs/evidence/verification/specialty-wave4-5.md §C (one question per turn).

**Q2 — Chest pain presence** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
> "Son zamanlarda göğsünüzde ağrı, baskı ya da sıkışma hissi oldu mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: none by itself; feeds Q3.

**Q3 — Chest pain duration / recurrence** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(">15 min and/or recurrent within 1 h")
> "Göğüs ağrınız olduğunda genellikle ne kadar sürüyor?"
gen: slot=gogus_agrisi_suresi; type=duration; follow_up=Yaklaşık kaç dakika sürdüğünü söyleyebilir misiniz?
CANDIDATE — clinician to approve wording. Revised 2026-09-26 per
docs/evidence/verification/specialty-wave4-5.md §C: the either/or prompt is dropped because it left a
gap and primed the unsigned cut-off; the follow-up is the reviewer's text. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** if "on beş dakikadan uzun" and/or
recurrent within one hour, per S1 verbatim.

**Q4 — Dyspnoea** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (equivalent) + S3 (cardinal)
> "Son günlerde nefes darlığı yaşadınız mı? Örneğin yürürken ya da dinlenirken."
CANDIDATE — clinician to approve wording.

**Q5 — Syncope / near-syncope** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
> "Son zamanlarda bayıldığınız ya da bayılacak gibi olduğunuz oldu mu?"
CANDIDATE — clinician to approve wording.

**Q6 — Syncope on exertion** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("Syncope during
exertion or when supine")
> "Bu baygınlık ya da göz kararması hissi, yürürken veya merdiven çıkarken mi oldu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)**, per S2 high-risk feature.

**Q7 — Palpitations** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (palpitation→syncope)
> "Kalbinizin hızlı, düzensiz ya da çok güçlü çarptığını fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Note: standalone palpitation urgency threshold has **NO
SOURCE FOUND** (§4); S2 only links palpitation *immediately followed by syncope*.

**Q8 — Ankle / leg swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("ankle swelling")
> "Ayak bileklerinizde ya da bacaklarınızda şişlik fark ettiniz mi?"
CANDIDATE — clinician to approve wording.

**Q9 — Known cardiac diagnoses** · archetype: `EVALUATION.problem_diagnosis.v1` · source: n/a (history)
> "Daha önce kalbinizle ilgili bir tanı aldınız mı? Örneğin kalp yetmezliği, ritim bozukluğu ya da
> yüksek tansiyon."
CANDIDATE — clinician to approve wording.

**Q10 — Current cardiac medications** · archetype: `ACTION.medication.v1` · source: n/a (history)
> "Şu anda kalbiniz ya da tansiyonunuz için düzenli kullandığınız ilaçlar var mı?"
CANDIDATE — clinician to approve wording.

*(10 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **"Call an ambulance / do not travel yourself" as an ESC-sourced verbatim statement** — the ESC
   ACS accessible text fetch returned **NOT FOUND** for a verbatim "call emergency medical services
   rather than travelling yourself" sentence. The Turkish "112'yi arayın" wording exists only via the
   LOW-confidence TKD public page (S4). **NO SOURCE FOUND (primary/authoritative) — clinician must
   supply**, ideally a **T.C. Sağlık Bakanlığı** primary document.
2. **ESC ACS high-risk-features list for immediate ED referral** (continuing chest pain,
   haemodynamic instability, severe dyspnoea, syncope, palpitations as a set) — **NOT FOUND** in the
   accessible excerpt (guideline mentions "very high-risk and high-risk ACS features" in §3.1.2 but
   the enumerated list was truncated). **NO SOURCE FOUND (verbatim) — clinician must supply** from
   the primary PDF.
3. **Standalone palpitations urgency threshold** — S2 sources palpitation only *immediately followed
   by syncope*. A cut-off/red-flag for palpitations alone (e.g. sustained, with chest pain or
   syncope) is **NO SOURCE FOUND — clinician must supply**.
4. **Orthopnoea / paroxysmal nocturnal dyspnoea verbatim** — S3 confirms the "cardinal symptoms"
   sentence but the accessible excerpt did not yield verbatim orthopnoea/PND text. **NO SOURCE FOUND
   (verbatim) — clinician must supply** (candidate: ESC-HF-2021 Table 6).
5. **Acute decompensated heart-failure "when to seek help" threshold** — **NO SOURCE FOUND (verbatim)
   — clinician must supply**.
6. **T.C. Sağlık Bakanlığı / TKD primary clinical guideline (Turkish, versioned)** — only private
   hospital marketing pages and a TKD public-education page were retrievable; **no versioned Turkish
   clinical guideline document was located**. **NO SOURCE FOUND — clinician must supply** the correct
   Türkiye-first primary source and its version/date.
7. **ESC 2023 Focused Update of the HF guideline** — exists (PubMed 37622666) but was not retrieved
   verbatim; confirm whether it supersedes any S3 wording. **NO SOURCE FOUND (verbatim) — clinician
   to confirm current version.**
8. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must
   supply**, with committed `source` snapshots, before anything compiles.
9. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032); not fabricated. Family history (item 16) has **no archetype root** → export blocked
   (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules
  engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/
  prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — numerals in drafts are spelled out; compiler must expand before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S4 for
  that block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
