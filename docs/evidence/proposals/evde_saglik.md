# Evde Sağlık (Home Health Care) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Evde Sağlık (Home Health Care)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. Many home-health patients are dependent
(bed-bound, cognitively impaired), so questions are drafted for **adult self OR a caregiver /
proxy** as noted per item. This file is a *proposal for a clinician to sign off*. It assigns **no**
authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**,
  written as *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The
  guideline's own urgency wording is quoted verbatim; no level is asserted.
- **Acute deterioration stays in `base.life_threat` (invariant 7).** A newly-arising emergency at
  home — collapse, unresponsiveness, acute breathing difficulty, chest pain, stroke signs — is not
  a specialty-pack rule. The MoH regulation says the same in law: *"Yeni oluşan acil haller evde
  sağlık hizmetinin kapsamına girmez"* (H1, Madde 21(7)). `files/protocols/base.life_threat.yaml`
  is the universal sibling set and nothing in a specialty pack may extend it. This proposal captures
  the *symptom* so a clinician + the rules engine can act; it does **not** author an emergency
  script and does **not** add anything to the life-threat set.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / WebSearch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any
  derived rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/evde_saglik.yaml` (an L0 draft) or any
  served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### H1 — T.C. Sağlık Bakanlığı Evde Sağlık Hizmetleri Yönetmeliği (deterioration → 112) · retrieved VERBATIM
- **guideline_id (proposed):** `TR-MoH-EVDE-YONET`
- **Publishing body:** T.C. Sağlık Bakanlığı (Turkish Ministry of Health)
- **Version / year:** retrieved text is the "Sağlık Bakanlığı ve Bağlı Kuruluşları Tarafından Evde
  Sağlık Hizmetlerinin Sunulmasına Dair Yönetmelik" (article numbering Madde 12/19/21). A **newer**
  regulation — "Evde Sağlık ve Palyatif Bakım Hizmetlerinin Sunumu ve Koordinasyonuna İlişkin
  Yönetmelik", **Resmî Gazete 2 Haziran 2023, sayı 32209** — was reported by search and may
  supersede or renumber these articles. **Which regulation and article numbers are current MUST be
  reconciled on sign-off (§4).**
- **URL:** https://www.aile.gov.tr/eyhgm/mevzuat/ulusal-mevzuat/yonetmelikler/saglik-bakanligi-ve-bagli-kuruluslari-tarafindan-evde-saglik-hizmetlerinin-sunulmasina-dair-yonetmelik/
  (2023 revision: https://resmigazete.gov.tr/eskiler/2023/06/20230602-1.htm — returned an SSL
  certificate error to automated fetch)
- **Verbatim (Madde 12, fıkra 2):**
  > "Acil sağlık hizmetine gereksinim duyan evde sağlık hastası, 112 acil hizmetlerinden yararlandırılır."
- **Verbatim (Madde 21, fıkra 7):**
  > "Yeni oluşan acil haller evde sağlık hizmetinin kapsamına girmez. Bu durumlarda acil sağlık
  > hizmetlerine dair mevzuata göre işlem tesis edilir."
- **Verbatim (Madde 19, fıkra 1-ç — caregiver/family information):**
  > "Hastanın ve ailesinin, evde bakım sürecinde üstlenebilecekleri görevler ile hastalık ve bakım
  > süreçleri hakkında bilgilendirilmesini"
- **Confidence: MEDIUM.** Text was fetched from the aile.gov.tr mirror of the regulation; the exact
  Resmî Gazete date/number and whether these article numbers survive the 2023 revision need
  primary re-verification. This is a **service/scope regulation**, not a clinical red-flag guideline
  — it grounds *when a home-health case is routed to 112*, not a triage level.

### H2 — NICE CG179 Pressure ulcers: prevention and management (skin assessment) · skin-assessment retrieved VERBATIM
- **guideline_id (proposed):** `NICE-PU-CG179`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** CG179, published 23 April 2014 (updated 2015)
- **Citation:** NICE. *Pressure ulcers: prevention and management (CG179).*
- **URL:** https://www.nice.org.uk/guidance/cg179 · skin-assessment text retrieved via NCBI mirror
  https://www.ncbi.nlm.nih.gov/books/NBK333153/
- **Verbatim (skin-assessment recommendation — the healthcare professional should check for):**
  > "skin integrity in areas of pressure"
  > "colour changes or discoloration"
  > "variations in heat, firmness and moisture (for example, because of incontinence, oedema, dry or
  > inflamed skin)"
- **Verbatim (same recommendation — patient-reported):**
  > "take into account any pain or discomfort reported by the patient"
- **Risk factors + repositioning (SEARCH SUMMARY — not a verbatim fetch):** risk factors reported
  as *significantly limited mobility, significant loss of sensation, a previous or current pressure
  ulcer, nutritional deficiency, the inability to reposition themselves, or significant cognitive
  impairment*; validated scales named as *Braden, Waterlow, Norton*; repositioning *"at least every
  6 hours"* (adults at risk). **These specific items are UNVERIFIED VERBATIM (§4).**
- **Confidence: HIGH** for the skin-assessment sentences (fetched from NCBI full-text mirror);
  **MEDIUM / unverified** for risk-factor and repositioning wording. Recommendation numbers need
  primary re-verification (nice.org.uk returned HTTP 403 to automated fetch).

### H3 — NICE CG161 Falls in older people (case identification) · retrieved VERBATIM
- **guideline_id (proposed):** `NICE-FALLS-CG161`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** CG161 (June 2013). A newer NICE guideline **NG249** (2024) covers falls and
  may supersede CG161 — confirm current version on sign-off (§4).
- **Citation:** NICE. *Falls in older people: assessing risk and prevention (CG161).*
- **URL:** https://www.nice.org.uk/guidance/cg161 · retrieved via NCBI mirror
  https://www.ncbi.nlm.nih.gov/books/NBK258885/
- **Verbatim (recommendation 1.1.1.1):**
  > "Older people in contact with healthcare professionals should be asked routinely whether they
  > have fallen in the past year and asked about the frequency, context and characteristics of the
  > fall/s."
- **Verbatim (recommendation 1.1.1.2):**
  > "Older people reporting a fall or considered at risk of falling should be observed for balance
  > and gait deficits and considered for their ability to benefit from interventions to improve
  > strength and balance."
- **Verbatim (recommendation 1.1.2.1):**
  > "Older people who present for medical attention because of a fall, or report recurrent falls in
  > the past year, or demonstrate abnormalities of gait and/or balance should be offered a
  > multifactorial falls risk assessment."
- **Confidence: HIGH** for the quoted recommendations (fetched from NCBI full-text mirror); confirm
  whether NG249 (2024) changes the wording on sign-off.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: composition + archetype **roots** only, **no
at-code (`atNNNN`) leaf nodes** (INT-032; HB-C12). Each item below binds to an archetype **root**
actually present in the template; the leaf path is **deferred** (`openehr_deferred_reason`), never
fabricated. Roots present: `reason_for_encounter.v1`, `story.v1`, `symptom_sign.v1`,
`problem_diagnosis.v1`, `medication.v1`, `adverse_reaction_risk.v1`, `phq9.v1`, `gad7.v1`,
`triage_outcome.v1`.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for the home-health visit / need | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of current situation / who answers | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Recent worsening of general condition (H1 → 112) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | New / worsening breathlessness (acute → base.life_threat) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Skin colour change / discolouration over pressure areas (H2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Broken skin / open sore over bony areas (H2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Pain / discomfort over pressure areas (H2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Fall in the past year (H3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Balance / gait / walking difficulty (H3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Existing wound / burn being cared for (H1 scope) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Current medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Known diagnoses / chronic conditions | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| — | Repositioning ability / mobility & ADL dependence (H2 risk factor) | **no archetype root in `.opt` — export blocked (INT-041 posture)** | — | — |
| — | Caregiver identity / caregiver information given (H1 Madde 19) | **no archetype root in `.opt` — export blocked (INT-041 posture)** | — | — |

Notes:
- Mobility / repositioning-ability / ADL-dependence and caregiver identity have **no matching
  archetype root** in the committed `.opt` → **export blocked (INT-041 posture)**; do not invent an
  at-code path. Clinician / architecture decision needed (candidate: INT-032 / HB-C12 addition).
- Items 3–4 (deterioration, breathlessness) are captured for the note only; their authoritative
  emergency handling belongs to `base.life_threat` + the rules engine (invariant 7), and — for a
  home-health case — to the 112 route named in law (H1), not to this pack.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; one concern per question (invariant 2: one question per
turn); empathetic; no diagnosis/treatment/prognosis language. Each item marks whether it is drafted
for **adult self** or a **caregiver / proxy** (many home-health patients are dependent). Proxy
delivery register (files/02 §5.3 CALM) is a runtime concern and is **not** set here. **All marked
"CANDIDATE — clinician to approve wording".** Per invariant 22 no bare numeral appears; quantities
are spelled out in Turkish orthography and the compiler must expand them before TTS; there is **no
free numeric text entry** on the clinical critical path.

> Triage note for every red-flag-derived item: the level shown is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED/YELLOW must come from `packages/protocols/triage` with a committed `source`
> snapshot and all three RED axes (route × register × location, invariant 21), none of which are
> supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave4-5.md §B (reviewer's replacement
texts used verbatim). The former Q2 (who answers / situation narrative) is removed: base
`identity_check` / `subject_role` already cover it. Renumbering, old → new: Q1 unchanged · Q2 removed ·
Q3 → Q2 · Q4 → Q3 · Q5 → Q4 · Q6 → Q5 · Q7 → Q6 · Q8 → Q7 (fall) + Q8 (circumstances, if Q7 yes) ·
Q9–Q12 unchanged. Self/proxy variants keyed on base `subject_role` are still open (reviewer finding,
LOW; no replacement text supplied).

**Q1 — Reason for visit** · self/proxy · archetype: `EVALUATION.reason_for_encounter.v1` · source: n/a (general intake)
> "Bugünkü evde sağlık görüşmesinde en çok hangi konuda desteğe ihtiyacınız var?"
CANDIDATE — clinician to approve wording. Proxy variant: "…hastanızın en çok hangi konuda desteğe ihtiyacı var?"

**Q2 — Recent worsening of general condition** · self/proxy · archetype: `OBSERVATION.symptom_sign.v1` ·
source: H1 (Madde 12(2) / 21(7) — acil → 112)
> "Son günlerde hastanın genel durumunda kötüleşme oldu mu? Örneğin aşırı uykuya eğilim ya da uyandırmakta zorlanma."
gen: slot=genel_durum_kotulesmesi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: a newly-arising emergency is out of
home-health scope by law (H1) and belongs to `base.life_threat` + the 112 route (inv 7); no level
asserted here.

**Q3 — New / worsening breathlessness** · self/proxy · archetype: `OBSERVATION.symptom_sign.v1` ·
source: acute deterioration → `base.life_threat` (inv 7); H1 (112 route)
> "Hastada yeni başlayan ya da giderek artan bir nefes darlığı fark ettiniz mi?"
gen: slot=nefes_darligi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: acute breathlessness is acute
deterioration — handled by `base.life_threat` + 112 (H1), not by this pack; captured for the note
only.

**Q4 — Skin colour change over pressure areas** · self/proxy · archetype: `OBSERVATION.symptom_sign.v1` ·
source: H2 ("colour changes or discoloration")
> "Hastanın uzun süre üzerinde yattığı ya da oturduğu yerlerde ciltte renk değişikliği var mı?"
gen: slot=basi_bolgesi_renk_degisimi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: feeds H2 pressure-area review; no
standalone level.

**Q5 — Broken skin / open sore over bony areas** · self/proxy · archetype: `OBSERVATION.symptom_sign.v1` ·
source: H2 ("skin integrity in areas of pressure")
> "Hastanın topuk, kalça ya da kuyruk sokumu gibi yerlerinde açık yara var mı?"
gen: slot=basi_yarasi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** for an established pressure injury, pending clinician + rules engine.

**Q6 — Pain / discomfort over pressure areas** · self/proxy · archetype: `OBSERVATION.symptom_sign.v1` ·
source: H2 ("take into account any pain or discomfort reported by the patient")
> "Hasta, uzun süre baskı altında kalan bölgelerde ağrı ya da rahatsızlık ifade ediyor mu?"
gen: slot=basi_bolgesi_agrisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Fall in the past year** · self/proxy · archetype: `OBSERVATION.symptom_sign.v1` ·
source: H3 (rec 1.1.1.1 — "fallen in the past year")
> "Hasta son bir yıl içinde hiç düştü mü?"
gen: slot=son_yil_dusme; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: recurrent falls feed H3's multifactorial
assessment (rec 1.1.2.1); no standalone level asserted here.

**Q8 — Fall circumstances (if Q7 yes)** · self/proxy · archetype: `OBSERVATION.symptom_sign.v1` ·
source: H3 (rec 1.1.1.1 — "fallen in the past year")
> "Bu düşmelerin hangi durumlarda olduğunu anlatır mısınız?"
gen: slot=dusme_durumlari; type=string; ask_if=son_yil_dusme == true
CANDIDATE — clinician to approve wording. Narrative answer, so the slot stays a string.

**Q9 — Balance / gait / walking difficulty** · self/proxy · archetype: `OBSERVATION.symptom_sign.v1` ·
source: H3 (rec 1.1.1.2 — "balance and gait deficits")
> "Hastanın dengesinde ya da yürümesinde zorluk fark ettiniz mi?"
gen: slot=denge_yurume_guclugu; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Existing wound / burn being cared for** · self/proxy · archetype: `OBSERVATION.symptom_sign.v1` ·
source: H1 (home-health wound-care scope)
> "Hastanın evde bakımı yapılan bir yarası ya da yanığı var mı?"
gen: slot=evde_yara_bakimi; type=boolean
CANDIDATE — clinician to approve wording. Note: wound-care as a home-health service is named in the
MoH regulation scope (H1); the specific clinical wound-assessment criteria are **NO SOURCE FOUND**
(§4).

**Q11 — Current medications** · self/proxy · archetype: `ACTION.medication.v1` · source: n/a (history)
> "Hasta şu anda düzenli olarak hangi ilaçları kullanıyor?"
CANDIDATE — clinician to approve wording.

**Q12 — Known diagnoses / chronic conditions** · self/proxy · archetype: `EVALUATION.problem_diagnosis.v1` ·
source: n/a (history)
> "Hastanın daha önce tanı aldığı süregelen (kronik) hastalıkları var mı?"
gen: slot=kronik_hastalik; type=boolean
CANDIDATE — clinician to approve wording.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Which MoH regulation is current, and its article numbers** — the verbatim Madde 12(2)/19/21(7)
   quotes came from the aile.gov.tr mirror; the 2023 revision (Resmî Gazete 2 Haziran 2023, sayı
   32209) returned an **SSL certificate error** to automated fetch. **Reconcile the current
   regulation, its RG date/number and article numbering on sign-off.**
2. **A clinical (not scope) Turkish deterioration guideline** — H1 grounds *"acil → 112"* as
   service scope, not a clinical deterioration threshold (e.g. an early-warning-score equivalent).
   **NO SOURCE FOUND (clinical threshold) — clinician must supply**; acute deterioration itself is
   `base.life_threat` (invariant 7).
3. **NICE CG179 risk-factor list + repositioning frequency, verbatim** — captured only via
   web-search summary; the skin-assessment recommendation was fetched verbatim but the risk factors
   / Braden-Waterlow-Norton / "every 6 hours" wording was not. **NO SOURCE FOUND (verbatim) —
   clinician must supply** from primary CG179, with recommendation numbers.
4. **Pressure-ulcer staging / "when to seek help" thresholds** and **wound-assessment criteria** —
   H2 gives what to *look for* on the skin, not a red-flag level; wound-care criteria for Q10 are
   unsourced. **NO SOURCE FOUND (verbatim) — clinician must supply.**
5. **NICE CG161 current version** — NG249 (2024) may supersede CG161; confirm which wording is
   current. **Clinician to confirm current version.**
6. **A Türkiye-first pressure-ulcer / falls clinical guideline** (T.C. Sağlık Bakanlığı / HSGM /
   uzmanlık derneği) — none located in retrievable, versioned form; NICE CG179/CG161 used as the
   allowed fallback per the task's "Turkish MoH else NICE" rule. **NO SOURCE FOUND (Turkish primary)
   — clinician must supply** if a Türkiye-first source is preferred.
7. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant
   21) — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must
   supply**, with committed `source` snapshots, before anything compiles.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032 / HB-C12); not fabricated. Mobility/repositioning-ability/ADL and caregiver identity
   have **no archetype root** → export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/
  prognosis; marked CANDIDATE. Deterioration questions ask about the *symptom* neutrally and never
  name a disease.
- **Inv. 7** — acute deterioration (collapse, acute breathlessness, chest pain, stroke signs) stays
  in `base.life_threat`; a newly-arising emergency is also out of home-health scope by law (H1,
  Madde 21(7)). This proposal adds nothing to the life-threat set and only captures the symptom for
  the note.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in drafts; compiler must expand before TTS; no free numeric entry.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources H1–H3
  (H1 + H2-skin + H3 verbatim; H2 risk-factors unverified) but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
