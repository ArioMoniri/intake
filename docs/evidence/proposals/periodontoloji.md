# Periodontoloji (Periodontology — Gum Health) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent (dental guideline researcher) · Date: 2026-09-26 · Specialty:
Periodontoloji (gum and tooth-support disease) · Branch slug: `periodontoloji` (cluster: dental)
Purpose: patient-owned, Turkish-first **pre-visit intake** (history and symptom capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below cites a **real source that was actually retrieved on 2026-09-26** (URL +
  page locator + a short verbatim anchor). Where no source was found, the row reads **"NO SOURCE FOUND
  — clinician must supply"**. Nothing was invented.
- **Turkish first:** the Türk Periodontoloji Derneği (TPD) Turkish translation of the EFP S3 guideline,
  with the 2017 AAP/EFP classification chapter, is the primary source. The TDB protocol book (2012) and
  international consensus papers corroborate.
- **Quoting policy:** verbatim anchors are short term-level fragments; the rest is paraphrase (§4 gap 7).
- **Triage:** per invariant 1, nothing here assigns a level, route, register or location. §2.2 names
  what stays with `base.life_threat` or the physician; §2.3 lists red-flag candidates **for physician
  review — not encoded**.
- **Base intake already asks** medications, OTC products, blood thinners, allergies, pregnancy,
  immunosuppression, smoking and alcohol. Smoking is a grading factor in PD-S1 but is **not** re-asked;
  the base `smoking_status` answer is reused. Diabetes, antiresorptive medicines and endocarditis-risk
  heart conditions are **not** in base, so they are asked here (Q9, Q11, Q12).
- **Verification caveat:** PDFs were streamed to a scratch directory outside the repo and
  text-extracted with `pdftotext`; page numbers are **PDF page indices**. Consensus-paper anchors come
  from PubMed abstracts retrieved through the PubMed API. Re-check every anchor before sign-off; until
  then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/periodontoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with locators

### PD-S1 — TPD *Evre I–III Periodontitisin Tedavisi – EFP S3 Seviye Klinik Uygulama Kılavuzu* (Türkiye; primary)
- **guideline_id (proposed):** `TPD-EFP-S3-TR` · Türk Periodontoloji Derneği; Turkish translation of
  the EFP S3 treatment guideline for stage I–III periodontitis, reviewed by Prof. Dr. Nurcan Buduneli
  (foreword, PDF p. 2). Landing page dated 10 August 2022; PDF uploaded November 2023.
- **URL:** https://turkperio.org/wp-content/uploads/2023/11/periodontal_hastalik_tedavi_kilavuzu.pdf
  (landing: https://turkperio.org/periodontal-hastalik-tedavi-kilavuzu/)
- **Locators:**
  - PDF p. 4 — smoking and diabetes enter the 2017 classification as risk factors (anchor "Risk
    faktörleri: Sigara ve diyabet").
  - PDF p. 5 — Tablo 2 (stages): complexity factors include tooth mobility, "Çiğneme bozukluğu" and
    "dişlerde kayma".
  - PDF p. 6 — Tablo 3 (grades): risk modifiers are smoking and diabetes.
  - PDF p. 19 — periodontitis features include pockets and "dişeti kanaması".
  - PDF p. 33 — after treatment, a patient is reclassified as stable or not (anchor "stabil
    periodontitis hastası").
  - PDF p. 34 — differential diagnosis lists localised gum recession after trauma, "Periodontal
    apseler" and necrotising periodontal disease.
- **Confidence: HIGH** (Turkish specialty society translation of a European S3 guideline).

### PD-S2 — Papapanou et al. *Periodontitis: Consensus report of workgroup 2 of the 2017 World Workshop* (International)
- **guideline_id (proposed):** `WW2017-PERIODONTITIS` · J Periodontol. 2018;89 Suppl 1:S173–S182.
  DOI 10.1002/JPER.17-0721 · PMID 29926951.
- **Locators (abstract):** necrotising periodontal disease shows "papilla necrosis, bleeding, and pain"
  and is linked to impaired host immunity; a periodontal abscess is a "localized accumulation of pus"
  with risk of systemic spread.
- **Confidence: HIGH** (consensus report; abstract via the PubMed API).

### PD-S3 — Sanz et al. *Periodontal diseases and diabetes* — EFP/IDF joint workshop (International)
- **guideline_id (proposed):** `EFP-IDF-DIABETES-2018` · J Clin Periodontol. 2018;45(2):138–149.
  DOI 10.1111/jcpe.12808 · PMID 29280174.
- **Locator (abstract):** diabetes and periodontitis have a "bidirectional relationship"; the report
  gives co-management guidance for physicians and oral-health teams.
- **Confidence: HIGH.**

### PD-S4 — SDCEP *Oral Health Management of Patients at Risk of Medication-related Osteonecrosis of the Jaw* (International)
- **guideline_id (proposed):** `SDCEP-MRONJ-2017` · Scottish Dental Clinical Effectiveness Programme;
  March 2017, confirmed extant after the March 2024 review.
- **URL:** https://www.sdcep.org.uk/media/xzffda1g/sdcep-mronj-guidance-in-brief-extant-2024.pdf
- **Locator:** PDF p. 3 — ask about "past, current, or possible future use" of anti-resorptive or
  anti-angiogenic drugs when taking a medical history.
- **Confidence: HIGH** (primary PDF).

### PD-S5 — AHA *Prevention of Viridans Group Streptococcal Infective Endocarditis* (International)
- **guideline_id (proposed):** `AHA-IE-2021` · Wilson WR et al. Circulation. 2021;143(20):e963–e978.
  DOI 10.1161/CIR.0000000000000969 · PMID 33853363. Condition table read from the AAPD reprint:
  https://www.aapd.org/globalassets/media/policies_guidelines/bp_prophylaxis.pdf (PDF p. 4, Table 4).
- **Locator:** highest-risk conditions include prosthetic valves or valve-repair material, "Previous,
  relapse, or recurrent IE", some congenital heart disease and heart transplant with valve disease.
- **Confidence: HIGH** for the list; the ESC 2023 endocarditis guideline was not retrieved (§4 gap 3).

### PD-S6 — TDB *Dişhekimliğinde Tanı ve Tedavi Protokolleri* (Türkiye; national reference)
- **guideline_id (proposed):** `TDB-TTP-2012` · İstanbul Dişhekimleri Odası Eğitim Dizisi-17, Mart 2012.
- **URL:** https://www.ido.org.tr/userfiles/files/egitimdizisi_17.pdf
- **Locator:** PDF p. 132 (Bölüm 8 Periodontoloji) — loss of supporting bone leads to "dişlerde
  sallanma" and drifting.
- **Confidence: MEDIUM** (2012).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032; HB-C12), never invented.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Gums bleed on brushing or flossing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Gum recession noticed | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Loose tooth | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Teeth drifting or gaps opening | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Pus from the gum | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Painful sores at the gum tips between teeth | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Chewing difficulty from gums or teeth | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Diabetes | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q10 | Previous gum treatment | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q11a | Medicine for bone thinning or other bone problems (ever) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q11b | Name of that medicine | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q12a | Heart-valve procedure or previous endocarditis | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q12b | Description of that heart condition | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Left to `base.life_threat` or the physician (NOT extended — invariant 7)

- **Spreading facial swelling with breathing or swallowing difficulty** stays in the sibling
  `base.life_threat` set (`rf.dyspnoea_rest`, `rf.sepsis_like`). A periodontal abscess can spread
  (PD-S2), but this pack asks only the local sign (Q6) and adds no rule.
- **A recent injury that knocked out a permanent tooth** is a time-critical dental emergency for the
  physician/dentist pathway, not a periodontal intake item.
- No item in this pack feeds a life-threat rule.

### 2.3 Red-flag candidates — for physician review — not encoded

No level, route, register or location is proposed (invariants 1, 7, 21).

| Candidate | Source | Status |
|---|---|---|
| Painful, bleeding sores at the gum tips (necrotising pattern), which the consensus links to impaired immunity | PD-S2 abstract | not encoded; physician/dentist decides |
| Pus from the gum (possible periodontal abscess) | PD-S2 abstract; PD-S1 PDF p. 34 | not encoded; spreading signs stay in `base.life_threat` |
| Diabetes with gum disease — co-management with the physician | PD-S3 abstract | not encoded; a care-planning flag, not triage |
| Antiresorptive medicine before gum surgery | PD-S4 PDF p. 3 | not encoded; care-planning flag |
| Heart condition on the highest-risk list before scaling or surgery | PD-S5 Table 4 | not encoded; care-planning flag |

---

## 3. Candidate B1 Turkish pre-visit questions (14)

Register: formal **siz**; one concern and exactly one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22); written in our own
words. **All CANDIDATE — clinician to approve wording.** No item carries a triage level. Q1 binds to
`basvuru_nedeni`. Checked by hand and by script against the Turkish PolicyGuard arms (unsigned —
HB-C23).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün sizi diş eti muayenesine getiren asıl şikâyetiniz nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Gums bleed on brushing or flossing** · archetype: `OBSERVATION.symptom_sign.v1` · source: PD-S1 PDF p. 19 ("dişeti kanaması")
> "Dişlerinizi fırçalarken ya da diş ipi kullanırken diş etleriniz kanıyor mu?"
gen: slot=dis_eti_kanamasi; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Gum recession noticed** · archetype: `OBSERVATION.symptom_sign.v1` · source: PD-S1 PDF p. 34 (gum recession in the differential)
> "Diş etlerinizin çekildiğini, yani dişlerinizin eskisinden uzun göründüğünü fark ettiniz mi?"
gen: slot=dis_eti_cekilmesi; type=boolean
CANDIDATE — clinician to approve wording. "Yani … uzun göründüğünü" explains *diş eti çekilmesi* in
plain words.

**Q4 — Loose tooth** · archetype: `OBSERVATION.symptom_sign.v1` · source: PD-S1 PDF p. 5 (Tablo 2, mobility); PD-S6 PDF p. 132 ("dişlerde sallanma")
> "Dişlerinizden herhangi biri sallanıyor mu?"
gen: slot=dis_sallanmasi; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Teeth drifting or gaps opening** · archetype: `OBSERVATION.symptom_sign.v1` · source: PD-S1 PDF p. 5 (Tablo 2, "dişlerde kayma")
> "Dişlerinizin yer değiştirdiğini ya da aralarının açıldığını fark ettiniz mi?"
gen: slot=dis_kaymasi; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Pus from the gum** · archetype: `OBSERVATION.symptom_sign.v1` · source: PD-S2 abstract ("localized accumulation of pus"); PD-S1 PDF p. 34 ("Periodontal apseler")
> "Diş etinizden iltihaplı bir akıntı geldiğini fark ettiniz mi?"
gen: slot=dis_eti_akinti; type=boolean
CANDIDATE — clinician to approve wording. See §2.3.

**Q7 — Painful sores at the gum tips between teeth** · archetype: `OBSERVATION.symptom_sign.v1` · source: PD-S2 abstract ("papilla necrosis, bleeding, and pain")
> "Dişlerinizin arasındaki diş eti uçlarında ağrılı yaralar var mı?"
gen: slot=agrili_dis_eti_yarasi; type=boolean
CANDIDATE — clinician to approve wording. "Dişlerinizin arasındaki diş eti uçları" describes the papilla
without the term. See §2.3.

**Q8 — Chewing difficulty from gums or teeth** · archetype: `OBSERVATION.symptom_sign.v1` · source: PD-S1 PDF p. 5 (Tablo 2, "Çiğneme bozukluğu")
> "Diş etleriniz ya da dişleriniz yüzünden çiğnemekte zorlanıyor musunuz?"
gen: slot=cigneme_zorlugu; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Diabetes** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PD-S1 PDF pp. 4, 6 (diabetes as a grading factor); PD-S3 abstract ("bidirectional relationship")
> "Size daha önce şeker hastalığı tanısı konuldu mu?"
gen: slot=diyabet_tanisi; type=boolean
CANDIDATE — clinician to approve wording. Base intake does not ask this. The HbA1c cut-off in PD-S1
Tablo 3 is a number: it comes from records, never from patient speech (invariant 22). Same text and
slot as nefroloji, göz and nükleer tıp, so one clip serves all of them.

**Q10 — Previous gum treatment** · archetype: `OBSERVATION.story.v1` · source: PD-S1 PDF p. 33 ("stabil periodontitis hastası")
> "Daha önce size diş eti tedavisi yapıldı mı?"
gen: slot=onceki_dis_eti_tedavisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q11a — Medicine for bone thinning or other bone problems (ever)** · archetype: `ACTION.medication.v1` · source: PD-S4 PDF p. 3 ("past, current, or possible future use")
> "Kemik erimesi ya da başka bir kemik sorunu için hiç ilaç kullandınız mı?"
gen: slot=kemik_ilaci; type=boolean
CANDIDATE — clinician to approve wording. Wording follows the wave 1–3 reviewer text
(docs/evidence/verification/specialty-wave1-3.md) so the dental packs share one form. Past use counts.
Yes/no gate for Q11b. PD-S4 also names possible future use, which this text does not capture; a
planned-use item is a clinician decision.

**Q11b — Name of that medicine** · archetype: `ACTION.medication.v1` · source: PD-S4 PDF p. 3
> "Hatırlıyorsanız bu ilacın adını söyleyebilir misiniz?"
gen: slot=kemik_ilaci_adi; type=string; ask_if=kemik_ilaci == true
CANDIDATE — clinician to approve wording. Split from Q11 (wave 8 verification): a boolean slot cannot
store the medicine's name, so it has its own string slot. Same pair as protetik Q11a/Q11b.

**Q12a — Heart-valve procedure or previous endocarditis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PD-S5 Table 4 (AHA 2021)
> "Kalp kapağınızla ilgili bir işlem ya da kalp iç zarı iltihabı geçirdiniz mi?"
gen: slot=kalp_kapagi_endokardit; type=boolean
CANDIDATE — clinician to approve wording. Base intake does not ask this. "Kalp kapağınızla ilgili bir
işlem" covers valve surgery, catheter-implanted valves and valve-repair material, all of which PD-S5's
list includes ("prosthetic valves or valve-repair material"). Congenital heart disease is not named here
to stay within B1 length; see §4 gap 3. Yes/no gate for Q12b.

**Q12b — Description of that heart condition** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PD-S5 Table 4 (AHA 2021)
> "Bu kalp durumunu kısaca anlatır mısınız?"
gen: slot=kalp_kapagi_endokardit_aciklama; type=string; ask_if=kalp_kapagi_endokardit == true
CANDIDATE — clinician to approve wording. Split from Q12 (wave 8 verification), for the same reason as
Q11b.

*(14 candidate questions: Q1 general intake; Q2–Q12 source-backed, with Q11 and Q12 each split into a
yes/no item and a free-text item; no candidate flag on any item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Turkish patient-facing symptom list.** PD-S1 is clinician-facing; no TPD patient-facing list of gum
   symptoms (bleeding, recession, bad breath) was retrieved. **NO SOURCE FOUND (Turkish patient-facing)
   — clinician may supply.**
2. **Bad breath and family history of early tooth loss.** Not asked: no retrieved source ties either to
   a patient question (PD-S1 mentions familial tendency only when describing the retired 1999
   classification). **NO SOURCE FOUND — clinician to decide.**
3. **Endocarditis list.** Only AHA 2021 (via the AAPD reprint) was read; the ESC 2023 endocarditis
   guideline PDF could not be retrieved. Congenital heart disease on the list is not named in Q12.
   **Clinician to confirm the European list and whether a separate congenital item is needed.**
4. **Omitted to stay at twelve — sourced, clinician may swap in:** swollen or red gums (PD-S1
   definitions); interdental cleaning habit (DBOH v4 Table 2b, cited in `restoratif.md`).
5. **Numeric values** (PD-S1 bone-loss ratios, cigarette counts, HbA1c; PD-S4 years of bisphosphonate
   use) belong in any rule or record, never in patient text (invariant 22).
6. **AAOMS MRONJ position paper (2022).** Not retrieved here (publisher 403 in the sibling proposal);
   PD-S4 is used instead.
7. **Copyright / snapshot licence.** TPD, AAPD, AHA and journal texts are copyrighted. A committed
   verbatim snapshot needs **permission or a legal-review decision.**
8. **Every triage level and all three RED axes** (invariant 21) — deliberately **not** assigned.
9. **openEHR** — leaf paths deferred (INT-032, HB-C12).
10. **PolicyGuard lexicon is itself unsigned (HB-C23).**
11. **Dental airway ask.** §2.2 leaves spreading swelling with breathing or swallowing difficulty to
    `base.life_threat`, but `rf.dyspnoea_rest` and `rf.sepsis_like` are named-gap stubs there with no
    ask, so no layer asks about the airway in this pack; Q6 (pus, which PD-S2 links to systemic spread)
    is the item this matters for. Four sibling dental packs carry an ungated airway ask instead.
    Whether every dental pack carries it under one shared slot id, or none does, is an owner and
    physician decision (wave 8 verification §A, owner decision 1). No item is added here — **clinician
    decision pending**.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy** — `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording; recession and papilla explained in plain words; each item
  CANDIDATE.
- **Inv. 7** — spreading infection with airway signs stays in `base.life_threat`; this pack adds no
  rule.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at sign-off.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals; HbA1c and cigarette counts come from records and base slots.
- **HB-C1** — awaits clinician sign-off; NOT served.
