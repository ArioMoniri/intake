# Restoratif Diş Tedavisi (Restorative Dentistry) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent (dental guideline researcher) · Date: 2026-09-26 · Specialty:
Restoratif diş tedavisi (decay, fillings, sensitivity and tooth wear) · Branch slug: `restoratif`
(cluster: dental)
Purpose: patient-owned, Turkish-first **pre-visit intake** (history and symptom capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below cites a **real source that was actually retrieved on 2026-09-26** (URL +
  page locator + a short verbatim anchor). Where no source was found, the row reads **"NO SOURCE FOUND
  — clinician must supply"**. Nothing was invented.
- **Turkish first:** the TDB protocol book (2012; preventive and restorative chapters) and the Türk
  Pedodonti Derneği fluoride report (2019, which also covers adults) are the Türkiye anchors. No
  versioned Turkish restorative-dentistry society guideline was found (§4 gap 1). The UK *Delivering
  better oral health* toolkit (updated 2025), the FDI dentine-hypersensitivity statement, the EFCD
  erosive-wear consensus and AAE patient information carry the detail.
- **Quoting policy:** verbatim anchors are short term-level fragments; the rest is paraphrase (§4 gap 7).
- **Triage:** per invariant 1, nothing here assigns a level, route, register or location. §2.2 names
  what stays with `base.life_threat` or the physician; §2.3 lists red-flag candidates **for physician
  review — not encoded**.
- **Base intake already asks** medications, OTC products, blood thinners, allergies, pregnancy,
  immunosuppression, smoking, alcohol, pain character, aggravating factors and severity. None is
  repeated; the asks below are specific tooth-level symptoms and habits.
- **Verification caveat:** PDFs were streamed to a scratch directory outside the repo and
  text-extracted with `pdftotext`; page numbers are **PDF page indices**. Consensus-paper anchors come
  from PubMed abstracts retrieved through the PubMed API. Re-check every anchor before sign-off; until
  then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/restoratif.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with locators

### RE-S1 — TDB *Dişhekimliğinde Tanı ve Tedavi Protokolleri* (Türkiye; national reference)
- **guideline_id (proposed):** `TDB-TTP-2012` · Türk Dişhekimleri Birliği commission; İstanbul
  Dişhekimleri Odası Eğitim Dizisi-17, **Mart 2012** (adapted from Swiss Dental Association guidelines).
- **URL:** https://www.ido.org.tr/userfiles/files/egitimdizisi_17.pdf
- **Locators:**
  - PDF p. 50 (Bölüm 3 Koruyucu) — the history covers diet ("Beslenme anamnezi"), saliva, general
    health and medicines; many medicines reduce saliva (anchor "Birçok ilacın tükürük").
  - PDF p. 57 — for erosion linked to diet, ask about acidic food and drink (anchor "asitli
    yiyecek").
  - PDF p. 89 (Bölüm 6 Restoratif) — the restoration level is set after the history and the patient's
    wishes (anchor "Hastanın istekleri doğrultusunda").
  - PDF p. 99 — brown or black discolouration and the decay history inform diagnosis (anchor
    "renkleşme kombinasyonlarına").
- **Confidence: MEDIUM** (2012; no newer edition found).

### RE-S2 — TPD *Florür Durum Raporu Güncelleme* (Türkiye)
- **guideline_id (proposed):** `TPD-FLORUR-2019` · Türk Pedodonti Derneği with TDB; 2016, updated 2019.
- **URL:** https://archive.tdb.org.tr/ekler/Florur_Durum_Raporu_2019.pdf
- **Locators:** PDF p. 2 — excess sugar upsets the mouth's balance ("aşırı şeker tüketimi"); PDF p. 8 —
  brushing twice a day with fluoride toothpaste reduces decay, and TPD/TDB extend fluoride use to adults
  and older people.
- **Confidence: HIGH** (primary PDF).

### RE-S3 — OHID *Delivering better oral health*, version 4 (International; UK government)
- **guideline_id (proposed):** `DBOH-V4` · Office for Health Improvement and Disparities; published 12
  June 2014, last updated 10 September 2025.
- **URLs:** chapter 2 — https://www.gov.uk/government/publications/delivering-better-oral-health-an-evidence-based-toolkit-for-prevention/chapter-2-summary-guidance-tables-for-dental-teams ·
  chapter 7 — https://www.gov.uk/government/publications/delivering-better-oral-health-an-evidence-based-toolkit-for-prevention/chapter-7-tooth-wear
- **Locators:** chapter 2, Table 1f — adults brush twice daily with fluoride toothpaste, spit rather than
  rinse, and cut how much and how often they have sugary food and drink. Chapter 7 — tooth wear comes
  from "extrinsic acid" (food, drink, medicines), "intrinsic acid" (reflux, vomiting), tooth-to-tooth
  wear and bruxism; loss of crown height is a sign.
- **Confidence: HIGH** (government toolkit).

### RE-S4 — FDI Policy Statement *Dentin Hypersensitivity* (International)
- **guideline_id (proposed):** `FDI-DH-2009` · FDI World Dental Federation; adopted September 2009
  (Singapore).
- **URL:** https://www.fdiworlddental.org/dentin-hypersensitivity
- **Locator:** definition — "Short sharp pain arising from exposed dentin" in response to thermal,
  evaporative, tactile, osmotic or chemical stimuli; gum recession and enamel loss are causes. The
  definition originates in the Canadian consensus (J Can Dent Assoc 2003;69:221–6; PMID 12662460).
- **Confidence: HIGH** for the definition; 2009 policy — check for an update (§4 gap 2).

### RE-S5 — AAE patient information *Cracked Teeth* (International)
- **guideline_id (proposed):** `AAE-CRACKED-PATIENT` · American Association of Endodontists; undated
  public page.
- **URL:** https://www.aae.org/patients/dental-symptoms/cracked-teeth/
- **Locator:** cracked teeth cause erratic pain when chewing, possibly "with the release of biting
  pressure", or pain with temperature extremes.
- **Confidence: MEDIUM** (patient-education page; the AAE clinician newsletter PDF could not be
  fetched — §4 gap 3).

### RE-S6 — Carvalho et al. *EFCD consensus report: erosive tooth wear — diagnosis and management* (International)
- **guideline_id (proposed):** `EFCD-ETW-2015` · Clin Oral Investig. 2015;19(7):1557–61.
  DOI 10.1007/s00784-015-1511-7 · PMID 26121968.
- **Locator (abstract):** patient-related factors include "reflux, vomiting, drinking and eating
  habits", medicines and supplements; management starts with evaluating all causes.
- **Confidence: HIGH** (consensus report; abstract via the PubMed API).

### RE-S7 — AAPD *Caries-risk Assessment and Management* (International; adolescent form)
- **guideline_id (proposed):** `AAPD-CRA-2022` · latest revision 2022; Reference Manual 2025:325–31.
- **URL:** https://www.aapd.org/media/Policies_Guidelines/BP_CariesRiskAssessment.pdf
- **Locator:** PDF p. 3, Table 2 (≥ 6 years) — risk factors include "hyposalivatory medication(s)", low
  salivary flow and "defective restorations".
- **Confidence: HIGH.** Paediatric/adolescent form; used here only to corroborate RE-S1.

### RE-S8 — Lobbezoo et al. *International consensus on the assessment of bruxism* (International)
- **guideline_id (proposed):** `BRUXISM-CONSENSUS-2018` · J Oral Rehabil. 2018;45(11):837–844.
  DOI 10.1111/joor.12663 · PMID 29926505.
- **Locator (abstract):** clenching or grinding can be assessed by "self-report".
- **Confidence: HIGH.**

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032; HB-C12), never invented.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Twinge with cold, hot or sweet | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Sudden pain on biting or on release | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Broken tooth, crack or lost filling | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Hole or dark spot noticed | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Teeth look worn, thinner or shorter | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Frequent acidic drinks | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); no diet archetype in the OPT |
| Q8 | Sour or bitter fluid rising into the mouth | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Frequent sugary snacks or drinks between meals | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Brushes morning and evening with fluoride toothpaste | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Dry mouth | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Clenching or grinding | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Left to `base.life_threat` or the physician (NOT extended — invariant 7)

- **Spreading facial swelling with breathing or swallowing difficulty** stays in the sibling
  `base.life_threat` set (`rf.dyspnoea_rest`, `rf.sepsis_like`). This pack asks nothing about it and
  adds no rule.
- **A recent injury that knocked out a permanent tooth** is a time-critical dental emergency for the
  physician/dentist pathway, not a restorative intake item.
- No item in this pack feeds a life-threat rule.

### 2.3 Red-flag candidates — for physician review — not encoded

No level, route, register or location is proposed (invariants 1, 7, 21).

| Candidate | Source | Status |
|---|---|---|
| Sudden pain on biting or release (possible crack) | RE-S5 | not encoded; dentist decides; lingering or spontaneous pain is captured by `endodonti.md` |
| Tooth wear with frequent reflux or vomiting — may need medical or supportive referral | RE-S3 ch. 7 (conversations may reveal issues that need supportive referral); RE-S6 abstract | not encoded; clinician decides |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and exactly one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22); written in our own
words. **All CANDIDATE — clinician to approve wording.** No item carries a triage level. Q1 binds to
`basvuru_nedeni`. Checked by hand and by script against the Turkish PolicyGuard arms (unsigned —
HB-C23).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake; RE-S1 PDF p. 89 (patient's wishes)
> "Bugün sizi diş hekimine getiren asıl diş sorununuz nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Twinge with cold, hot or sweet** · archetype: `OBSERVATION.symptom_sign.v1` · source: RE-S4 (thermal and osmotic stimuli)
> "Soğuk, sıcak ya da tatlı bir şey yiyip içtiğinizde dişleriniz sızlıyor mu?"
gen: slot=dis_hassasiyeti; type=boolean
CANDIDATE — clinician to approve wording. "Sızlamak" is the everyday word for a short sharp twinge.

**Q3 — Sudden pain on biting or on release** · archetype: `OBSERVATION.symptom_sign.v1` · source: RE-S5 ("with the release of biting pressure")
> "Isırdığınızda ya da ısırmayı bıraktığınızda dişinizde ani bir ağrı oluyor mu?"
gen: slot=isirinca_ani_agri; type=boolean
CANDIDATE — clinician to approve wording. See §2.3.

**Q4 — Broken tooth, crack or lost filling** · archetype: `OBSERVATION.symptom_sign.v1` · source: RE-S1 PDF p. 50 (state of existing restorations); RE-S7 ("defective restorations")
> "Dişinizde kırık, çatlak ya da düşmüş bir dolgu var mı?"
gen: slot=kirik_dis_dolgu; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Hole or dark spot noticed** · archetype: `OBSERVATION.symptom_sign.v1` · source: RE-S1 PDF p. 99 ("renkleşme kombinasyonlarına")
> "Dişlerinizde oyuk ya da koyu renkli bir leke fark ettiniz mi?"
gen: slot=oyuk_leke; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Teeth look worn, thinner or shorter** · archetype: `OBSERVATION.symptom_sign.v1` · source: RE-S3 ch. 7 (loss of crown height); RE-S6 abstract
> "Dişlerinizin aşınıp incelmiş ya da kısalmış göründüğünü fark ettiniz mi?"
gen: slot=dis_asinmasi; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Frequent acidic drinks** · archetype: `OBSERVATION.story.v1` · source: RE-S1 PDF p. 57 ("asitli yiyecek"); RE-S3 ch. 7 ("extrinsic acid"); RE-S6 abstract
> "Gazlı içecek ya da meyve suyu gibi asitli içecekleri sık içer misiniz?"
gen: slot=asitli_icecek; type=boolean
CANDIDATE — clinician to approve wording. No frequency number is asked (invariant 22).

**Q8 — Sour or bitter fluid rising into the mouth** · archetype: `OBSERVATION.symptom_sign.v1` · source: RE-S3 ch. 7 ("intrinsic acid", reflux); RE-S6 abstract ("reflux")
> "Mideden ağzınıza sık sık ekşi ya da acı su geliyor mu?"
gen: slot=reflu; type=boolean
CANDIDATE — clinician to approve wording. Describes reflux without naming it. Vomiting is not asked
here (§4 gap 4).

**Q9 — Frequent sugary snacks or drinks between meals** · archetype: `OBSERVATION.story.v1` · source: RE-S3 ch. 2 Table 1f; RE-S2 PDF p. 2 ("aşırı şeker tüketimi"); RE-S1 PDF p. 57
> "Öğün aralarında şekerli yiyecek ya da içecekleri sık tüketiyor musunuz?"
gen: slot=ara_ogun_seker; type=boolean
CANDIDATE — clinician to approve wording. RE-S1's frequency cut-off stays in any rule, never in patient
text (invariant 22).

**Q10 — Brushes morning and evening with fluoride toothpaste** · archetype: `OBSERVATION.story.v1` · source: RE-S3 ch. 2 Table 1f; RE-S2 PDF p. 8
> "Dişlerinizi her gün sabah ve akşam florürlü macunla fırçalıyor musunuz?"
gen: slot=florurlu_fircalama; type=boolean
CANDIDATE — clinician to approve wording. One sourced habit (RE-S3 states it as a single
recommendation); the reviewer may split frequency and fluoride into two items.

**Q11 — Dry mouth** · archetype: `OBSERVATION.symptom_sign.v1` · source: RE-S1 PDF p. 50 ("Birçok ilacın tükürük"); RE-S7 ("hyposalivatory medication(s)")
> "Ağzınızda sık sık kuruluk hissediyor musunuz?"
gen: slot=agiz_kurulugu; type=boolean
CANDIDATE — clinician to approve wording. Medicines themselves come from the base medication slots.

**Q12 — Clenching or grinding** · archetype: `OBSERVATION.symptom_sign.v1` · source: RE-S3 ch. 7 (bruxism); RE-S8 abstract (self-report)
> "Dişlerinizi sıktığınızı ya da gıcırdattığınızı fark ettiniz mi?"
gen: slot=dis_sikma_gicirdatma; type=boolean
CANDIDATE — clinician to approve wording.

*(12 candidate questions: Q1 general intake; Q2–Q12 source-backed; no candidate flag on any item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first restorative guideline.** No versioned Turkish restorative-dentistry society or
   Ministry guideline was found on 2026-09-26; RE-S1 dates from 2012. **NO SOURCE FOUND (current
   Turkish restorative guideline) — clinician must supply** if one exists.
2. **FDI dentine-hypersensitivity statement (2009).** Not checked for a later revision. **Clinician to
   confirm** it is current.
3. **AAE clinician source for cracked teeth.** The AAE *Endodontics: Colleagues for Excellence* PDF on
   cracked teeth could not be fetched; RE-S5 is a patient page. **Re-capture before any rule uses Q3.**
4. **Vomiting and eating disorders.** RE-S3 ch. 7 and RE-S6 list vomiting and eating disorders as acid
   sources. Asking about them touches a sensitive category and the consented wellbeing flow; **not
   asked here — clinician and legal decision.**
5. **Omitted to stay at twelve — sourced, clinician may swap in:** dissatisfaction with the colour or
   shape of teeth (RE-S1 PDF p. 89); cleaning between the teeth (RE-S3 ch. 2 Table 2b); spitting rather
   than rinsing after brushing (RE-S3 ch. 2 Table 1f).
6. **Overlap with `endodonti.md`.** Lingering and spontaneous tooth pain are asked in the endodontic
   pack; Q2 here asks only the short twinge. **Clinician to decide** how the dental cluster shares these
   slots.
7. **Copyright / snapshot licence.** TDB, TPD, FDI, AAE, AAPD and journal texts are copyrighted; DBOH is
   UK Crown copyright. A committed verbatim snapshot needs **permission or a legal-review decision.**
8. **Every triage level and all three RED axes** (invariant 21) — deliberately **not** assigned.
9. **openEHR** — leaf paths deferred (INT-032, HB-C12); no diet or oral-hygiene archetype in the OPT.
10. **PolicyGuard lexicon is itself unsigned (HB-C23).**

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy** — `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording; reflux and sensitivity described in plain words; each item
  CANDIDATE.
- **Inv. 7** — spreading infection with airway signs stays in `base.life_threat`; this pack adds no
  rule.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at sign-off.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals; no frequency or toothpaste strength is asked as a number.
- **HB-C1** — awaits clinician sign-off; NOT served.
