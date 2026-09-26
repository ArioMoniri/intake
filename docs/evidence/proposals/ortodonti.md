# Ortodonti (Orthodontics) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent (dental guideline researcher) · Date: 2026-09-26 · Specialty:
Ortodonti (orthodontics — tooth and jaw alignment) · Branch slug: `ortodonti` (cluster: dental)
Purpose: patient-owned, Turkish-first **pre-visit intake** (history and symptom capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below cites a **real source that was actually retrieved on 2026-09-26** (URL +
  page locator + a short verbatim anchor). Where no source was found, the row reads **"NO SOURCE FOUND
  — clinician must supply"**. Nothing was invented.
- **Turkish first:** the Türk Dişhekimleri Birliği (TDB) protocol book (2012) is the Türkiye anchor. A
  search for a versioned Türk Ortodonti Derneği (TOD) clinical guideline found only society pages and
  clinic marketing (§4 gap 1). AAPD best practices (2024 revisions) carry the symptom detail.
- **Quoting policy:** verbatim anchors are short term-level fragments; the rest is paraphrase. A
  committed snapshot needs the publishers' permission (§4 gap 7).
- **Triage:** per invariant 1, nothing here assigns a level, route, register or location. §2.2 names
  what stays with `base.life_threat` or the physician; §2.3 lists red-flag candidates **for physician
  review — not encoded**.
- **Base intake already asks** medications, OTC products, blood thinners, allergies, pregnancy,
  immunosuppression, smoking, alcohol, onset, trajectory and goals. None of these is repeated here.
- **Verification caveat:** PDFs were streamed to a scratch directory outside the repo and
  text-extracted with `pdftotext`; page numbers are **PDF page indices**. Re-check every anchor before
  sign-off; until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/ortodonti.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with locators

### OR-S1 — TDB *Dişhekimliğinde Tanı ve Tedavi Protokolleri* (Türkiye; primary national reference)
- **guideline_id (proposed):** `TDB-TTP-2012` · Türk Dişhekimleri Birliği Tanı-Tedavi Protokolleri ve
  Kodlama Sistemleri Komisyonu; published as İstanbul Dişhekimleri Odası Eğitim Dizisi-17, **Mart 2012**
  (translated and adapted from Swiss Dental Association quality guidelines).
- **URL:** https://www.ido.org.tr/userfiles/files/egitimdizisi_17.pdf
- **Locators (Bölüm 5 Ortodonti):**
  - PDF p. 77 — a good result meets the specialty's criteria and the patient's wishes (anchor
    "hastanın isteklerini").
  - PDF p. 78 — space and arch stability after traumatic tooth loss (anchor "travmatik diş
    kayıplarından").
  - PDF p. 79 — planning that ignores dental and gum health is graded poor (anchor "Sağlıksız dental ve
    periodontal koşullar").
- **Confidence: MEDIUM.** National professional body, but 2012 and adapted from a Swiss source; no
  newer edition was found (§4 gap 1).

### OR-S2 — AAPD *Management of the Developing Dentition and Occlusion in Pediatric Dentistry* (International)
- **guideline_id (proposed):** `AAPD-DEVDENT-2024` · American Academy of Pediatric Dentistry; latest
  revision 2024; Reference Manual 2025:497–515.
- **URL:** https://www.aapd.org/globalassets/media/policies_guidelines/bp_developdentition.pdf
- **Locators:**
  - PDF p. 2 — the functional analysis should "detect deleterious habits" and detect jaw-joint
    dysfunction; the facial analysis weighs esthetics and "self-image".
  - PDF p. 4 — oral habits include non-nutritive sucking, bruxism and tongue thrust; bruxism is defined
    by "tooth clenching and grinding"; "impaired nasal respiration" may contribute to malocclusion;
    history findings of sleep apnoea include "snoring, observed apnea".
- **Confidence: HIGH** (society best practice, primary PDF).

### OR-S3 — AAPD *Temporomandibular Disorders in Children and Adolescents* (International)
- **guideline_id (proposed):** `AAPD-TMD-2024` · latest revision 2024; Reference Manual 2025:516–26.
- **URL:** https://www.aapd.org/globalassets/media/policies_guidelines/bp_tempdisorders.pdf
- **Locator:** PDF p. 3, "Screening for TMJ health" — a screening history asks about difficulty
  opening, "noises within your jaw joint", pain when chewing or opening wide, and whether the jaw
  locks.
- **Confidence: HIGH.** The list is a screening history, not a scored instrument; Q4–Q6 below are in
  our own words and are not scored.

### OR-S4 — AAPD *Periodicity of Examination … Anticipatory Guidance* (International)
- **guideline_id (proposed):** `AAPD-PERIODICITY-2022` · latest revision 2022.
- **URL:** https://www.aapd.org/globalassets/media/policies_guidelines/bp_periodicity.pdf
- **Locators:** PDF p. 4 — counselling about existing habits (anchor "fingernail biting, clenching,
  bruxism"); PDF p. 5 — traumatic dental injuries are frequent in children.
- **Confidence: HIGH.**

### OR-S5 — Lobbezoo et al. *International consensus on the assessment of bruxism* (International)
- **guideline_id (proposed):** `BRUXISM-CONSENSUS-2018` · J Oral Rehabil. 2018;45(11):837–844.
  DOI 10.1111/joor.12663 · PMID 29926505 (retrieved via the PubMed API).
- **Locator:** abstract — bruxism can be assessed by non-instrumental approaches, "notably
  self-report".
- **Confidence: HIGH** (consensus paper). Grounds asking the patient directly (Q7).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032; HB-C12), never invented.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Bothered by the look of teeth or smile | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Difficulty biting or chewing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Jaw-joint noise | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Jaw pain on chewing or wide opening | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Jaw catching or limited opening | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Clenching or grinding (self-report) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Mouth breathing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Oral habits | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); no habit archetype in the OPT |
| Q10 | Past injury to front teeth | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Previous orthodontic treatment | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Gums bleed on brushing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Left to `base.life_threat` or the physician (NOT extended — invariant 7)

- **Spreading facial swelling with breathing or swallowing difficulty** stays in the sibling
  `base.life_threat` set (`rf.dyspnoea_rest`, `rf.sepsis_like`; `packages/protocols/base/intake.yaml`).
  This pack asks nothing about it and adds no rule.
- **A recent injury that knocked out a permanent tooth** is a time-critical dental emergency for the
  physician/dentist pathway, not an orthodontic intake item. Q10 asks only about *past* injury as
  history.
- No item in this pack feeds a life-threat rule.

### 2.3 Red-flag candidates — for physician review — not encoded

No level, route, register or location is proposed (invariants 1, 7, 21).

| Candidate | Source | Status |
|---|---|---|
| Jaw that locks, or cannot open fully | OR-S3 PDF p. 3 | not encoded; physician/dentist decides |
| Snoring or observed pauses in breathing during sleep (possible sleep apnoea) | OR-S2 PDF p. 4 | not encoded; interdisciplinary referral is a clinician decision |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and exactly one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22); written in our own
words. **All CANDIDATE — clinician to approve wording.** No item carries a triage level. Q1 binds to
`basvuru_nedeni`. Checked by hand and by script against the Turkish PolicyGuard arms (unsigned —
HB-C23).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake; OR-S1 PDF p. 77 ("hastanın isteklerini")
> "Diş ve çene düzeninizle ilgili sizi bugün getiren asıl konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Bothered by the look of teeth or smile** · archetype: `OBSERVATION.story.v1` · source: OR-S2 PDF p. 2 ("self-image"); OR-S1 PDF p. 77
> "Dişlerinizin ya da gülüşünüzün görünümü sizi rahatsız ediyor mu?"
gen: slot=gorunum_rahatsizligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Difficulty biting or chewing** · archetype: `OBSERVATION.symptom_sign.v1` · source: OR-S2 PDF p. 2 (functional analysis)
> "Yiyecekleri ısırırken ya da çiğnerken zorlanıyor musunuz?"
gen: slot=cigneme_zorlugu; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Jaw-joint noise** · archetype: `OBSERVATION.symptom_sign.v1` · source: OR-S3 PDF p. 3 ("noises within your jaw joint")
> "Ağzınızı açıp kaparken kulağınızın önündeki çene ekleminden ses geliyor mu?"
gen: slot=cene_eklemi_ses; type=boolean
CANDIDATE — clinician to approve wording. "Kulağınızın önündeki" explains where the jaw joint is.

**Q5 — Jaw pain on chewing or wide opening** · archetype: `OBSERVATION.symptom_sign.v1` · source: OR-S3 PDF p. 3
> "Çiğnerken ya da ağzınızı genişçe açarken çenenizde ağrı oluyor mu?"
gen: slot=cene_agrisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Jaw catching or limited opening** · archetype: `OBSERVATION.symptom_sign.v1` · source: OR-S3 PDF p. 3 (difficulty opening; jaw locks)
> "Çenenizin takılıp kaldığı ya da ağzınızı tam açamadığınız oldu mu?"
gen: slot=cene_takilma; type=boolean
CANDIDATE — clinician to approve wording. See §2.3.

**Q7 — Clenching or grinding** · archetype: `OBSERVATION.symptom_sign.v1` · source: OR-S2 PDF p. 4 ("tooth clenching and grinding"); OR-S5 (self-report)
> "Dişlerinizi sıktığınızı ya da gıcırdattığınızı fark ettiniz mi?"
gen: slot=dis_sikma_gicirdatma; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — Mouth breathing** · archetype: `OBSERVATION.symptom_sign.v1` · source: OR-S2 PDF p. 4 ("impaired nasal respiration")
> "Burnunuz yerine çoğunlukla ağzınızdan nefes alıyor musunuz?"
gen: slot=agizdan_nefes; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Oral habits** · archetype: `OBSERVATION.story.v1` · source: OR-S2 PDF p. 4 (habits); OR-S4 PDF p. 4 ("fingernail biting, clenching, bruxism")
> "Parmak emme, dudak ya da tırnak ısırma gibi bir alışkanlığınız var mı?"
gen: slot=agiz_aliskanligi; type=boolean; follow_up=Hangi alışkanlık olduğunu söyleyebilir misiniz?
CANDIDATE — clinician to approve wording.

**Q10 — Past injury to front teeth** · archetype: `OBSERVATION.story.v1` · source: OR-S1 PDF p. 78 ("travmatik diş kayıplarından"); OR-S4 PDF p. 5
> "Ön dişleriniz daha önce bir darbe ya da kaza sonucu zarar gördü mü?"
gen: slot=onceki_dis_travmasi; type=boolean
CANDIDATE — clinician to approve wording. History only; a fresh knocked-out tooth is §2.2.

**Q11 — Previous orthodontic treatment** · archetype: `OBSERVATION.story.v1` · source: general orthodontic history; OR-S1 PDF p. 77 (result may still change after treatment)
> "Daha önce diş teli ya da şeffaf plakla tedavi gördünüz mü?"
gen: slot=onceki_ortodonti; type=boolean
CANDIDATE — clinician to approve wording.

**Q12 — Gums bleed on brushing** · archetype: `OBSERVATION.symptom_sign.v1` · source: OR-S1 PDF p. 79 ("Sağlıksız dental ve periodontal koşullar")
> "Dişlerinizi fırçalarken diş etleriniz kanıyor mu?"
gen: slot=dis_eti_kanamasi; type=boolean
CANDIDATE — clinician to approve wording.

*(12 candidate questions: Q1 general intake; Q2–Q12 source-backed; no candidate flag on any item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first orthodontic guideline.** No versioned TOD or Ministry orthodontic guideline was found
   on 2026-09-26; OR-S1 (TDB, 2012, adapted from a Swiss source) is the only Türkiye document. **NO
   SOURCE FOUND (current Turkish orthodontic guideline) — clinician must supply** if one exists.
2. **Minors and proxy sessions.** Many orthodontic patients are children. These asks address the
   patient; a parent-voiced variant ("çocuğunuz") keyed on base `subject_role` is needed. **Clinician
   and product decision.**
3. **Omitted to stay at twelve — sourced, clinician may swap in:** snoring or observed breathing pauses
   in sleep (OR-S2 PDF p. 4); tongue thrust (OR-S2 PDF p. 4); earlier treatment for a jaw-joint problem
   (OR-S3 PDF p. 3).
4. **Antiresorptive medicines and tooth movement.** Not asked here. SDCEP's MRONJ guidance (cited in the
   periodontoloji and protetik proposals) says to ask every dental patient; whether orthodontics needs
   its own item is **a clinician decision — NO SOURCE FOUND (orthodontic-specific)**.
5. **Nickel or metal sensitivity to appliances.** Base `allergies` asks about drugs and substances; a
   dedicated appliance-metal item was not sourced. **NO SOURCE FOUND — clinician to decide.**
6. **Standard duration slot.** The generator adds `sikayet_suresi` ("Bu şikâyetiniz ne zamandır
   var?"), which fits a complaint but reads oddly for an alignment concern. **Clinician to decide**
   (generator-level).
7. **Copyright / snapshot licence.** AAPD texts are © AAPD; the TDB book is a professional
   publication. A committed verbatim snapshot needs **permission or a legal-review decision.**
8. **Every triage level and all three RED axes** (invariant 21) — deliberately **not** assigned.
9. **openEHR** — leaf paths deferred (INT-032, HB-C12); no habit or lifestyle archetype in the OPT.
10. **PolicyGuard lexicon is itself unsigned (HB-C23).**

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy** — `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording; each item CANDIDATE.
- **Inv. 7** — spreading infection with airway signs stays in `base.life_threat`; this pack adds no
  rule and asks nothing that extends it.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at sign-off.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals in patient text.
- **HB-C1** — awaits clinician sign-off; NOT served.
