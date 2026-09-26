# Protetik Diş Tedavisi (Prosthodontics) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent (dental guideline researcher) · Date: 2026-09-26 · Specialty:
Protetik diş tedavisi (dentures, crowns, bridges and implant-borne teeth) · Branch slug: `protetik`
(cluster: dental)
Purpose: patient-owned, Turkish-first **pre-visit intake** (history and symptom capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below cites a **real source that was actually retrieved on 2026-09-26** (URL +
  page locator + a short verbatim anchor). Where no source was found, the row reads **"NO SOURCE FOUND
  — clinician must supply"**. Nothing was invented.
- **Turkish first:** the Ministry of Health (HSGM) older-adult oral-health page and the TDB protocol
  book (2012) are the Türkiye anchors. A search for a versioned Türk Prostodonti ve İmplantoloji
  Derneği (TPİD) guideline found only congress pages (§4 gap 1). ACP, SDCEP, the 2017 World Workshop,
  the EFP S3 peri-implant guideline and ISOO-MASCC-ASCO carry the detail.
- **Quoting policy:** verbatim anchors are short term-level fragments; the rest is paraphrase (§4 gap 7).
- **Triage:** per invariant 1, nothing here assigns a level, route, register or location. §2.2 names
  what stays with `base.life_threat` or the physician; §2.3 lists red-flag candidates **for physician
  review — not encoded**.
- **Base intake already asks** medications, OTC products, blood thinners, allergies, pregnancy,
  immunosuppression, smoking and alcohol. None is repeated. Antiresorptive medicines and head-and-neck
  radiotherapy are **not** in base, so they are asked here (Q11, Q12).
- **Verification caveat:** PDFs were streamed to a scratch directory outside the repo and
  text-extracted with `pdftotext`; page numbers are **PDF page indices**. Consensus-paper anchors come
  from PubMed abstracts retrieved through the PubMed API. Re-check every anchor before sign-off; until
  then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/protetik.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with locators

### PR-S1 — T.C. Sağlık Bakanlığı HSGM, Yaşlı Sağlığı: *Ağız ve Diş Sağlığı* (Türkiye; Ministry public page)
- **guideline_id (proposed):** `HSGM-YASLI-ADS` · Halk Sağlığı Genel Müdürlüğü; page © 2025, no version.
- **URL:** https://hsgm.saglik.gov.tr/tr/yasli-sagligi/agiz-ve-dis-sagligi.html
- **Anchors:** dentures that no longer fit and cause pain ("ağrıya neden olan protezler"); dry mouth
  also harms denture retention ("protezlerin tutuculuğunu"); older people who report chewing or
  swallowing difficulty.
- **Confidence: MEDIUM** (Ministry public-information page, not a versioned clinical guideline).

### PR-S2 — TDB *Dişhekimliğinde Tanı ve Tedavi Protokolleri* (Türkiye; national reference)
- **guideline_id (proposed):** `TDB-TTP-2012` · İstanbul Dişhekimleri Odası Eğitim Dizisi-17, Mart 2012
  (adapted from Swiss Dental Association guidelines).
- **URL:** https://www.ido.org.tr/userfiles/files/egitimdizisi_17.pdf
- **Locators:**
  - PDF p. 152 (Bölüm 9 Sabit Protez) — plan around the patient's wishes on chewing, looks and comfort
    (anchor "bireysel konforu ile ilgili").
  - PDF p. 164 (Bölüm 10 Hareketli Protezler) — start with "Genel ve oral anamnez"; saliva quantity and
    quality affect retention (anchor "protezin tutuculuğunu"); jaw-muscle and joint problems are treated
    first (anchor "Myoarthropati sorunlarının").
- **Confidence: MEDIUM** (2012; no newer edition found).

### PR-S3 — ACP *Evidence-Based Guidelines for the Care and Maintenance of Complete Dentures* (International)
- **guideline_id (proposed):** `ACP-DENTURE-CARE-2011` · Felton D et al. J Prosthodont.
  2011;20 Suppl 1:S1–S12. DOI 10.1111/j.1532-849X.2010.00683.x.
- **URL:** https://www.prosthodontics.org/assets/1/7/7._JOP_Denture_Care_Guidelines_Supplement1.pdf
- **Locators (PDF p. 3, guidelines 13–15):** needing "increasing amounts of adhesives" is a reason to
  have the fit checked; dentures should not be worn "24 hours per day"; wearers should be checked
  annually, including for oral lesions.
- **Confidence: HIGH** (primary PDF). Dated 2011; check for an ACP update (§4 gap 2).

### PR-S4 — SDCEP *Oral Health Management of Patients at Risk of Medication-related Osteonecrosis of the Jaw* (International)
- **guideline_id (proposed):** `SDCEP-MRONJ-2017` · March 2017, confirmed extant after the March 2024
  review.
- **URL:** https://www.sdcep.org.uk/media/xzffda1g/sdcep-mronj-guidance-in-brief-extant-2024.pdf
- **Locators:** PDF p. 3 — ask about "past, current, or possible future use" of anti-resorptive or
  anti-angiogenic drugs; PDF p. 4 — adjust or replace "poorly fitting dentures" to limit mucosal injury.
- **Confidence: HIGH** (primary PDF).

### PR-S5 — Peterson et al. *Prevention and Management of Osteoradionecrosis …: ISOO-MASCC-ASCO Guideline* (International)
- **guideline_id (proposed):** `ISOO-MASCC-ASCO-ORN-2024` · J Clin Oncol. 2024;42(16):1975–1996.
  DOI 10.1200/JCO.23.02750 · PMID 38691821.
- **Locator (abstract):** covers osteoradionecrosis of the jaw "secondary to head and neck radiation
  therapy", with strong evidence for prevention practice.
- **Confidence: MEDIUM.** Only the abstract was read; the specific dental recommendations were not
  captured (§4 gap 3). Used only to justify asking about past radiotherapy.

### PR-S6 — Berglundh et al. *Peri-implant diseases and conditions* — 2017 World Workshop (International)
- **guideline_id (proposed):** `WW2017-PERIIMPLANT` · J Periodontol. 2018;89 Suppl 1:S313–S318.
  DOI 10.1002/JPER.17-0739 · PMID 29926955.
- **Locator (abstract):** peri-implantitis sites show inflammation, "bleeding on probing, and/or
  suppuration".
- **Confidence: HIGH** (consensus report; abstract via the PubMed API).

### PR-S7 — Herrera et al. *Prevention and treatment of peri-implant diseases — the EFP S3 guideline* (International)
- **guideline_id (proposed):** `EFP-S3-PERIIMPLANT-2023` · J Clin Periodontol. 2023;50 Suppl 26:4–76.
  DOI 10.1111/jcpe.13823 · PMID 37271498.
- **Locator (abstract):** once implants are in function, a supportive care programme with "periodical
  assessment of peri-implant tissue health" is recommended.
- **Confidence: HIGH.**

### PR-S8 — Lobbezoo et al. *International consensus on the assessment of bruxism* (International)
- **guideline_id (proposed):** `BRUXISM-CONSENSUS-2018` · J Oral Rehabil. 2018;45(11):837–844.
  DOI 10.1111/joor.12663 · PMID 29926505.
- **Locator (abstract):** bruxism is "repetitive masticatory muscle activity characterised by clenching
  or grinding"; it can be assessed by "self-report".
- **Confidence: HIGH.**

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032; HB-C12), never invented.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Wears a removable denture | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); no device archetype in the OPT |
| Q3 | Denture rubs or hurts somewhere | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Denture moves or holds less well | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Denture kept in at night | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Has a dental implant | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Bleeding or discharge around the implant | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Chewing difficulty | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Dry mouth | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Clenching or grinding | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Medicine for bone thinning or other bone problems (ever) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q12 | Past radiotherapy to head or neck | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); no procedure archetype in the OPT |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Left to `base.life_threat` or the physician (NOT extended — invariant 7)

- **Spreading facial swelling with breathing or swallowing difficulty** stays in the sibling
  `base.life_threat` set (`rf.dyspnoea_rest`, `rf.sepsis_like`). This pack asks nothing about it and
  adds no rule.
- **A recent injury that knocked out a permanent tooth** is a time-critical dental emergency for the
  physician/dentist pathway, not a prosthodontic intake item.
- No item in this pack feeds a life-threat rule.

### 2.3 Red-flag candidates — for physician review — not encoded

No level, route, register or location is proposed (invariants 1, 7, 21).

| Candidate | Source | Status |
|---|---|---|
| A denture sore that does not heal — oral-lesion check | PR-S3 PDF p. 3 (annual check for oral lesions); the non-healing-ulcer threshold sits in NICE NG12 as cited in `dis_hekimligi.md` S1 (not re-retrieved here) | not encoded; physician/dentist decides |
| Antiresorptive medicine with a poorly fitting denture or planned extraction/implant | PR-S4 PDF pp. 3–4 | not encoded; care-planning flag |
| Past head-and-neck radiotherapy before extraction or implant surgery | PR-S5 abstract | not encoded; care-planning flag |
| Bleeding or pus around an implant | PR-S6 abstract; PR-S7 abstract | not encoded; dentist decides |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and exactly one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22); written in our own
words. **All CANDIDATE — clinician to approve wording.** No item carries a triage level. Q1 binds to
`basvuru_nedeni`. Checked by hand and by script against the Turkish PolicyGuard arms (unsigned —
HB-C23).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake; PR-S2 PDF p. 152 (patient's wishes)
> "Bugün sizi diş protezi muayenesine getiren asıl konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Wears a removable denture** · archetype: `OBSERVATION.story.v1` · source: PR-S2 PDF p. 164 ("Genel ve oral anamnez"); PR-S3
> "Şu anda çıkarıp takılan bir protez, yani takma diş kullanıyor musunuz?"
gen: slot=hareketli_protez; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q3–Q5.

**Q3 — Denture rubs or hurts somewhere** · archetype: `OBSERVATION.symptom_sign.v1` · source: PR-S1 ("ağrıya neden olan protezler"); PR-S4 PDF p. 4 ("poorly fitting dentures")
> "Protezinizin vurduğu ya da ağrıttığı bir yer var mı?"
gen: slot=protez_vurugu; type=boolean; ask_if=hareketli_protez == true
CANDIDATE — clinician to approve wording. See §2.3.

**Q4 — Denture moves or holds less well** · archetype: `OBSERVATION.symptom_sign.v1` · source: PR-S3 PDF p. 3 ("increasing amounts of adhesives"); PR-S1 ("protezlerin tutuculuğunu")
> "Protezinizin yerinden oynadığını ya da eskisi kadar iyi tutmadığını hissediyor musunuz?"
gen: slot=protez_tutmuyor; type=boolean; ask_if=hareketli_protez == true
CANDIDATE — clinician to approve wording.

**Q5 — Denture kept in at night** · archetype: `OBSERVATION.story.v1` · source: PR-S3 PDF p. 3 ("24 hours per day")
> "Takma dişlerinizi geceleri de ağzınızda tutuyor musunuz?"
gen: slot=protez_gece; type=boolean; ask_if=hareketli_protez == true
CANDIDATE — clinician to approve wording. Captures a habit; no advice is given here.

**Q6 — Has a dental implant** · archetype: `OBSERVATION.story.v1` · source: PR-S7 abstract (supportive care after implants); PR-S2 PDF p. 164
> "Ağzınızda implant, yani çene kemiğine yerleştirilmiş yapay diş kökü var mı?"
gen: slot=implant; type=boolean
CANDIDATE — clinician to approve wording. "Yani … yapay diş kökü" explains *implant*. Gate for Q7.

**Q7 — Bleeding or discharge around the implant** · archetype: `OBSERVATION.symptom_sign.v1` · source: PR-S6 abstract ("bleeding on probing, and/or suppuration"); PR-S7 abstract
> "İmplantınızın çevresindeki diş etinde kanama ya da akıntı var mı?"
gen: slot=implant_cevresi_kanama; type=boolean; ask_if=implant == true
CANDIDATE — clinician to approve wording. See §2.3.

**Q8 — Chewing difficulty** · archetype: `OBSERVATION.symptom_sign.v1` · source: PR-S1 (chewing or swallowing difficulty); PR-S2 PDF p. 152
> "Eksik dişleriniz ya da protezinizle çiğnemekte zorlanıyor musunuz?"
gen: slot=cigneme_zorlugu; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Dry mouth** · archetype: `OBSERVATION.symptom_sign.v1` · source: PR-S1 ("protezlerin tutuculuğunu"); PR-S2 PDF p. 164 (saliva and retention)
> "Ağzınızda sık sık kuruluk hissediyor musunuz?"
gen: slot=agiz_kurulugu; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Clenching or grinding** · archetype: `OBSERVATION.symptom_sign.v1` · source: PR-S8 abstract (clenching or grinding; self-report)
> "Dişlerinizi sıktığınızı ya da gıcırdattığınızı fark ettiniz mi?"
gen: slot=dis_sikma_gicirdatma; type=boolean
CANDIDATE — clinician to approve wording.

**Q11 — Medicine for bone thinning or other bone problems (ever)** · archetype: `ACTION.medication.v1` · source: PR-S4 PDF p. 3 ("past, current, or possible future use")
> "Kemik erimesi ya da başka bir kemik sorunu için hiç ilaç kullandınız mı?"
gen: slot=kemik_ilaci; type=boolean; follow_up=Hatırlıyorsanız ilacın adını söyleyebilir misiniz?
CANDIDATE — clinician to approve wording. Wording follows the wave 1–3 reviewer text
(docs/evidence/verification/specialty-wave1-3.md). Past use counts. See §2.3.

**Q12 — Past radiotherapy to head or neck** · archetype: `OBSERVATION.story.v1` · source: PR-S5 abstract ("secondary to head and neck radiation therapy")
> "Baş ya da boyun bölgenize hiç ışın tedavisi (radyoterapi) uygulandı mı?"
gen: slot=bas_boyun_isin_tedavisi; type=boolean
CANDIDATE — clinician to approve wording. Base intake does not ask this. It names no disease. See §2.3.

*(12 candidate questions: Q1 general intake; Q2–Q12 source-backed; no candidate flag on any item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first prosthodontic guideline.** No versioned TPİD or Ministry prosthodontic guideline was
   found on 2026-09-26; PR-S1 is a public page and PR-S2 dates from 2012. **NO SOURCE FOUND (current
   Turkish prosthodontic guideline) — clinician must supply** if one exists.
2. **ACP denture-care guideline date.** PR-S3 is from 2011; no update was checked. **Clinician to
   confirm** it is current.
3. **ISOO-MASCC-ASCO recommendations.** Only the abstract was read; the full recommendations on dental
   care after radiotherapy were not captured. **Re-capture before any rule uses Q12.**
4. **Omitted to stay at twelve — sourced, clinician may swap in:** jaw-joint pain or noise (PR-S2 PDF
   p. 164, "Myoarthropati"; see `ortodonti.md` OR-S3 for the screening wording); fixed crowns or
   bridges present (PR-S2 Bölüm 9); dissatisfaction with how teeth or denture look (PR-S2 PDF p. 152);
   denture that has changed colour, worn or keeps breaking (PR-S1).
5. **Endocarditis-risk heart conditions and diabetes before implant surgery.** Not asked here; both are
   asked in `periodontoloji.md` (Q9, Q12). **Clinician to decide** whether the prosthodontic pack
   repeats them or the cluster shares one slot.
6. **Numeric values** (PR-S4 years of bisphosphonate use; any radiation dose) belong in records, never
   in patient text (invariant 22).
7. **Copyright / snapshot licence.** ACP, SDCEP, ASCO and journal texts are copyrighted. A committed
   verbatim snapshot needs **permission or a legal-review decision.**
8. **Every triage level and all three RED axes** (invariant 21) — deliberately **not** assigned.
9. **openEHR** — leaf paths deferred (INT-032, HB-C12); no device or procedure archetype in the OPT.
10. **PolicyGuard lexicon is itself unsigned (HB-C23).**

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy** — `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording; *implant* and *takma diş* explained in plain words; each
  item CANDIDATE.
- **Inv. 7** — spreading infection with airway signs stays in `base.life_threat`; this pack adds no
  rule.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at sign-off.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals in patient text.
- **HB-C1** — awaits clinician sign-off; NOT served.
