# Aşı (Vaccination / immunization clinic) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Aşı (Vaccination / immunization clinic)
Purpose: patient-owned, Turkish-first **pre-visit intake** (pre-vaccination screening history for a
clinician-ready note) — **not** diagnosis, not triage authority, not an eligibility decision. This
file is a *proposal for a clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN
level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**,
  written as *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. A
  vaccine "contraindication" or "precaution" is a **screening** concept, not a triage level; the
  source's own wording is quoted verbatim and no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval. Before sign-off each verbatim sentence MUST be re-checked against the
  **primary published text** and committed as a **verbatim source snapshot** with a full `source:
  {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule stays
  `status: draft_needs_source` and does **not** compile into a served pack (matches the served
  `packages/protocols/specialty/asi.yaml` L0 stub, `generated-l0-awaiting-clinical-review`).
- This file does **not** edit `packages/protocols/specialty/asi.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — CDC General Best Practice: Contraindications and Precautions
- **guideline_id (proposed):** `CDC-CONTRAIND-PRECAUT`
- **Publishing body:** U.S. Centers for Disease Control and Prevention (CDC)
- **Version / year:** page **last reviewed July 25, 2024**
- **URL:** https://www.cdc.gov/vaccines/hcp/imz-best-practices/contraindications-precautions.html
- **Verbatim (contraindication, all vaccines):**
  > "Severe allergic reaction (e.g., anaphylaxis) after a previous dose or to a vaccine component"
- **Verbatim (precaution — acute illness):**
  > "The presence of a moderate or severe acute illness with or without a fever is a precaution to
  > administration of all vaccines."
  > "Vaccination should be deferred for persons with a moderate or severe acute illness."
- **Verbatim (immune status — live vaccines):**
  > "Severely immunocompromised persons generally should not receive live vaccines."
- **Confidence:** HIGH for the retrieval (three distinct verbatim statements captured); still
  requires primary-text re-verification and a committed snapshot before it grounds any rule.

### S2 — T.C. Sağlık Bakanlığı — Genişletilmiş Bağışıklama Programı / Aşı Portalı
- **guideline_id (proposed):** `TCSB-GBP` (Türkiye-first national immunization programme)
- **Publishing body:** T.C. Sağlık Bakanlığı (Turkish Ministry of Health) — Aşı Portalı /
  Genişletilmiş Bağışıklama Programı Genelgesi
- **Version / year:** GBP Genelgesi (2008 revision located; a current revision must be confirmed)
- **URLs:** https://asi.saglik.gov.tr/genel-bilgiler/47-aşıların-yapılmaması-gereken-insanlar-var-mıdır.html ·
  https://www.saglik.gov.tr/TR-11080/genisletilmis-bagisiklama-programi-genelgesi.html · primary PDF:
  https://dosyasb.saglik.gov.tr/Eklenti/1117/0/gbpgenelge2008pdf.pdf
- **Retrieved content (NOT verbatim — see confidence):** a previous-dose anaphylaxis to a vaccine
  means later doses of that vaccine are not given; anaphylaxis to a **component** means other
  vaccines containing that substance are not given; in physician-determined **severe immune
  deficiency** (disease or medication) **live vaccines (BCG, KKK/MMR, oral polio, suçiçeği) are not
  administered**.
- **Confidence: LOW.** The Turkish page returned **HTTP 404 to automated fetch**; the content above
  is a **web-search-engine summary, not a verbatim Turkish quote**. It corroborates S1 (CDC) closely
  and is the correct **Türkiye-first** authority, but the **verbatim Turkish text and the current
  revision/date MUST be re-verified against the primary PDF** before it grounds any RED/alarm action
  script (§4 gap). Mirrors the cardiology proposal's low-confidence Turkish-source posture.

### S3 — Corroboration on live vaccines in immunosuppression (retrieved as summary, not verbatim)
- **Publishing bodies retrieved:** UK Health Security Agency "Green Book" chapter 6 (Contraindications
  and special considerations); Immunize.org contraindications guide; WHO position (live attenuated
  vaccines in severe immunodeficiency).
- **URL (one primary located):** https://assets.publishing.service.gov.uk/media/5a82ce28e5274a2e8ab5970f/Greenbook_chapter_6.pdf
- **Retrieved content (NOT verbatim):** severe immunosuppression is a contraindication to live
  attenuated vaccines; anaphylaxis to a previous dose or to a component applies to every vaccine;
  where the offending constituent (e.g. gelatine, neomycin, egg protein, yeast) is known, a product
  without it may be suitable.
- **Confidence: LOW (corroboration only).** These were returned as **search summaries, not verbatim
  quotes**; a specific WHO document URL was **not** retrieved verbatim (§4 gap). Used only to
  corroborate S1; not a standalone citing source.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` pins the composition and archetype **roots** only, with **no at-code (`atNNNN`)
leaf nodes** (INT-041; INT-032/HB-C12). Each item binds to an archetype **root**; the leaf path is
**deferred** (`openehr_deferred_reason`, INT-032), never fabricated.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit (which vaccine / why) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| 2 | Prior vaccination history / free narrative | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Severe reaction after a previous vaccine dose (S1/S2) | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 4 | Allergy to a vaccine component (egg, gelatine, neomycin, yeast) (S1/S2/S3) | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 5 | Feeling unwell / fever today (S1 precaution) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Immune-suppressing condition — immune status (S1/S2/S3) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 7 | Immune-suppressing medications (steroids, chemo) (S1/S3) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 8 | Pregnancy / breastfeeding status | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 9 | Candidate triage outcome (max `YELLOW_REVIEW`; authoritative = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Notes:
- No family-history item is proposed for vaccination, so the family-history export gap (present in
  other specialty proposals) does not arise here.
- `EVALUATION.triage_outcome.v1` and the composition root are LOCAL archetypes nobody has authored
  (HB-C12) — listed for binding completeness only.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; one concern per question (invariant 2); empathetic; no
diagnosis/treatment/prognosis language; capture-only (no "you should / should not be vaccinated"
instruction). **All marked "CANDIDATE — clinician to approve wording".** Per invariant 22 the
compiler must expand any digit before TTS; the drafts below contain **no bare numerals**.

> Triage note for every alarm-derived item: the level shown is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. A
> contraindication/precaution is a *screening* concept; the authoritative RED/YELLOW must come from
> `packages/protocols/triage` with a committed `source` snapshot and all three RED axes (invariant
> 21), none supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün hangi aşıyı yaptırmayı planlıyorsunuz? Kısaca yazabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Prior vaccination narrative** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Daha önce yaptırdığınız aşılarla ilgili bize iletmek istediğiniz bir konu var mı?"
CANDIDATE — clinician to approve wording.

**Q3 — Severe reaction after a previous vaccine dose** · archetype:
`EVALUATION.adverse_reaction_risk.v1` · source: S1 ("Severe allergic reaction (e.g., anaphylaxis)
after a previous dose ...") + S2 (Türkiye-first, LOW confidence)
> "Daha önce bir aşı olduktan sonra ciddi bir alerjik tepki yaşadınız mı? Örneğin yüzde şişme ya da
> soluk almada zorluk."
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)**, per S1 verbatim.

**Q4 — Allergy to a vaccine component** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source:
S1 ("... or to a vaccine component") + S3 (gelatine/neomycin/egg/yeast) + S2
> "Yumurta, jelatin ya da bir ilaca karşı ciddi bir alerjiniz olduğu size söylendi mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)**, per S1 component wording.

**Q5 — Feeling unwell / fever today** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
("moderate or severe acute illness with or without a fever is a precaution")
> "Bugün kendinizi hasta hissediyor musunuz ya da ateşiniz var mı?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** — S1 wording is a *precaution* (defer),
not a hard contraindication; the clinician/rules engine decides.

**Q6 — Immune status: immune-suppressing condition** · archetype:
`EVALUATION.problem_diagnosis.v1` · source: S1 ("Severely immunocompromised persons generally should
not receive live vaccines") + S2 (severe immune deficiency → no live vaccines) + S3
> "Bağışıklık sisteminizi zayıflatan bir rahatsızlığınız olduğu size söylendi mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** — relevant specifically to live
vaccines, per S1/S2.

**Q7 — Immune-suppressing medications** · archetype: `ACTION.medication.v1` · source: S1 (altered
immunocompetence) + S3
> "Bağışıklık sisteminizi baskılayan bir tedavi görüyor musunuz? Örneğin yüksek doz kortizon ya da
> kemoterapi."
CANDIDATE — clinician to approve wording.

**Q8 — Pregnancy / breastfeeding** · archetype: `EVALUATION.problem_diagnosis.v1` · source:
**NO SOURCE FOUND (verbatim)** — see §4; asked here as general screening only
> "Şu anda hamile misiniz ya da bebeğinizi emziriyor musunuz?"
CANDIDATE — clinician to approve wording. Note: the live-vaccine-in-pregnancy precaution was **not
retrieved verbatim**; this item stays general-screening until a source is committed (§4 gap).

*(8 candidate questions. Requested topics covered: prior reactions Q3, allergies Q4, current illness/
fever Q5, immune status Q6–Q7. Q8 pregnancy added but source-pending.)*

---

## 4. Gaps — every place NO SOURCE was found or verbatim was not retrieved (clinician/human must supply)

1. **Türkiye-first verbatim + current revision** — S2 (T.C. Sağlık Bakanlığı GBP / Aşı Portalı) is
   the correct Türkiye-first authority but its page returned **HTTP 404 to automated fetch**; the
   content is a **search-engine summary, not a verbatim Turkish quote**, and only a **2008** revision
   was located. **Clinician must supply** the verbatim Turkish text and confirm the current revision
   and date from the primary PDF.
2. **WHO primary source** — no specific WHO position-paper URL was retrieved verbatim; the WHO/Green
   Book/Immunize.org material (S3) is **corroboration by summary only**. **NO SOURCE FOUND
   (WHO verbatim) — clinician to supply** if WHO is to be a citing source.
3. **Live-vaccine-in-pregnancy precaution (Q8)** — **NOT retrieved verbatim** from CDC or MoH.
   **NO SOURCE FOUND (verbatim) — clinician must supply**; until then Q8 is general screening, not a
   sourced alarm.
4. **The specific component-allergy list** (egg, gelatine, neomycin, yeast, and their vaccine
   mappings, e.g. KKK/MMR) — grounded on S3 summary + S2 summary, **not verbatim**. **Clinician must
   confirm** the exact list and vaccine mapping before Q4 becomes a sourced alarm.
5. **"Moderate/severe" threshold for Q5** — S1 uses the words "moderate or severe acute illness";
   what counts as moderate/severe (and the defer-then-vaccinate timing) is a **clinical judgement**,
   not asserted here. **Clinician + rules engine must supply.**
6. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned. **Clinician + `packages/protocols/triage` rules must supply.**
7. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032); not fabricated (cross-ref HB-C12).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending
  rules engine; contraindication/precaution treated as screening, not triage.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/
  prognosis; capture-only (no "get / don't get vaccinated" instruction); marked CANDIDATE.
- **Inv. 10** — scripted/alarm wording will need verbatim `text_tr`; not finalised here.
- **Inv. 13** — the served `asi.yaml` is an L0 stub (`generated-l0-awaiting-clinical-review`); this
  proposal does not promote it.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — drafts contain no bare numerals; compiler must expand any number before TTS.
- **Clinical content rule** — each alarm rule needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate source S1
  (verbatim, CDC) and S2/S3 (Türkiye-first / corroboration, summary-only) but does not itself commit
  a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
