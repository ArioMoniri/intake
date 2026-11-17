# Pedodonti (Paediatric Dentistry) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1) and a paediatric reviewer's signature (HB-C3); NOT served; no fabricated values.**

Author: medical-researcher agent (dental guideline researcher) · Date: 2026-09-26 · Specialty:
Pedodonti (children's dentistry) · Branch slug: `pedodonti` (cluster: dental)
Purpose: patient-owned, Turkish-first **pre-visit intake** (history and symptom capture for a
clinician-ready note) **answered by a parent on behalf of a child** — **not** diagnosis, not triage
authority. Every question addresses the parent with `siz` and refers to the child as
**"çocuğunuz"**. This file is a *proposal for a clinician to sign off*. It assigns **no**
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below cites a **real source that was actually retrieved on 2026-09-26** (URL +
  page locator + a short verbatim anchor). Where no source was found, the row reads **"NO SOURCE FOUND
  — clinician must supply"**. Nothing was invented.
- **Turkish first:** the Türk Pedodonti Derneği (TPD) fluoride status report (2019 update) and the TDB
  protocol book (2012) are the Türkiye anchors. AAPD best practices (2022–2025 revisions) and the UK
  *Delivering better oral health* toolkit carry the detail.
- **Quoting policy:** verbatim anchors are short term-level fragments; the rest is paraphrase (§4 gap 8).
- **Triage:** per invariant 1, nothing here assigns a level, route, register or location. §2.2 names
  what stays with `base.life_threat` or the physician; §2.3 lists red-flag candidates **for physician
  review — not encoded**.
- **Proxy session:** base intake records `subject_role` / `proxy_reported`. Base medications, allergies
  and blood-thinner questions already cover the child; the adult base items (pregnancy, smoking,
  alcohol) do not apply to the child and are a base-pack concern. None is repeated here.
- **Verification caveat:** PDFs were streamed to a scratch directory outside the repo and
  text-extracted with `pdftotext`; page numbers are **PDF page indices**. Re-check every anchor before
  sign-off; until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/pedodonti.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with locators

### PE-S1 — TPD *Florür Durum Raporu Güncelleme* (Türkiye; primary)
- **guideline_id (proposed):** `TPD-FLORUR-2019` · Türk Pedodonti Derneği; first prepared 2016 by TPD
  and the TDB Eğitim Komisyonu, updated by TPD in 2019.
- **URL:** https://archive.tdb.org.tr/ekler/Florur_Durum_Raporu_2019.pdf (the listed
  `www.tdb.org.tr/ekler/…` address now redirects here)
- **Locators:**
  - PDF p. 2 — caries-causing bacteria and "aşırı şeker tüketimi" upset the balance in the mouth.
  - PDF p. 6 — Tablo 1: fluoride toothpaste for every age band, twice a day, in an age-set amount.
  - PDF p. 8 — brushing twice a day with an age-appropriate fluoride toothpaste reduces decay (anchor
    "Günde 2 kere yaşa uygun"); fluoride use should follow any "özel gereksinimleri".
- **Confidence: HIGH** (Turkish specialty society, primary PDF).

### PE-S2 — TDB *Dişhekimliğinde Tanı ve Tedavi Protokolleri* (Türkiye; national reference)
- **guideline_id (proposed):** `TDB-TTP-2012` · Türk Dişhekimleri Birliği commission; İstanbul
  Dişhekimleri Odası Eğitim Dizisi-17, **Mart 2012** (adapted from Swiss Dental Association guidelines).
- **URL:** https://www.ido.org.tr/userfiles/files/egitimdizisi_17.pdf
- **Locators (Bölüm 4 Çocuk Dişhekimliği):**
  - PDF p. 66 — children with aching teeth and oral infections need care plus diet guidance (anchor
    "Dişleri ağrıyan").
  - PDF p. 70 — children who find treatment very hard are approached carefully (anchor "Tedaviyi çok
    zor kabul eden").
  - PDF p. 72 — trauma management starts from the history, including the child's sports.
- **Confidence: MEDIUM** (2012; no newer edition found).

### PE-S3 — AAPD *Caries-risk Assessment and Management for Infants, Children, and Adolescents* (International)
- **guideline_id (proposed):** `AAPD-CRA-2022` · latest revision 2022; Reference Manual 2025:325–31.
- **URL:** https://www.aapd.org/media/Policies_Guidelines/BP_CariesRiskAssessment.pdf
- **Locators:** PDF p. 2, Table 1 (0–5 years) — risk factors include frequent "between-meal
  sugar-containing" snacks or drinks, a bottle or cup with sugar at bedtime, and special health care
  needs; protective factors include daily brushing with fluoride toothpaste and regular dental care.
  PDF p. 4 — parental supervision of brushing.
- **Confidence: HIGH.** The form is a clinician tool; its numeric cut-offs stay out of patient text.

### PE-S4 — AAPD *Pulp Therapy for Primary and Immature Permanent Teeth* (International)
- **guideline_id (proposed):** `AAPD-PULP-2025` · latest revision 2025; Reference Manual 2025:487–96.
- **URL:** https://www.aapd.org/globalassets/media/policies_guidelines/bp_pulptherapy.pdf
- **Locator:** PDF p. 2 — signs that change management include "spontaneous unprovoked pain", a sinus
  tract (a small gum boil that drains) and soft-tissue inflammation.
- **Confidence: HIGH.** Used only to choose which symptoms to ask about.

### PE-S5 — AAPD *Antibiotic Prophylaxis for Dental Patients at Risk for Infection* (International)
- **guideline_id (proposed):** `AAPD-ABX-2022` · latest revision 2022; Reference Manual 2025:564–70.
  Table 4 is reprinted from the AHA scientific statement (Wilson WR et al. Circulation
  2021;143(20):e963–e978; DOI 10.1161/CIR.0000000000000969; PMID 33853363).
- **URL:** https://www.aapd.org/globalassets/media/policies_guidelines/bp_prophylaxis.pdf
- **Locator:** PDF p. 4, Table 4 — highest-risk conditions include prosthetic valves, "Previous,
  relapse, or recurrent IE", certain congenital heart disease and heart transplant with valve disease.
- **Confidence: HIGH.** The parent is asked only whether a heart problem exists; the clinician decides
  whether it is in the table.

### PE-S6 — OHID *Delivering better oral health*, version 4 (International; UK government)
- **guideline_id (proposed):** `DBOH-V4` · Office for Health Improvement and Disparities; published 12
  June 2014, last updated 10 September 2025.
- **URL:** https://www.gov.uk/government/publications/delivering-better-oral-health-an-evidence-based-toolkit-for-prevention/chapter-2-summary-guidance-tables-for-dental-teams
- **Locators:** Tables 1a and 1b — parents or carers brush young children's teeth twice a day with
  fluoride toothpaste; minimise how much and how often sugary food and drink are consumed.
- **Confidence: HIGH** (government toolkit).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032; HB-C12), never invented.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit (parent-reported) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Child complains of toothache | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Pain starts on its own | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Gum swelling or gum boil | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Frequent sugary snacks or drinks between meals | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); no diet archetype in the OPT |
| Q6 | Bottle with milk or sugary drink when falling asleep | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Teeth brushed morning and evening | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Toothpaste contains fluoride | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Fear or strong worry about the dentist | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q10a | Long-term health condition or special need (yes/no) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q10b | Description of the condition or need | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q11a | Heart condition present from birth or past heart surgery (yes/no) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q11b | Description of the heart condition | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q12 | Past injury to the teeth | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Left to `base.life_threat` or the physician (NOT extended — invariant 7)

- **Spreading facial swelling with breathing or swallowing difficulty** stays in the sibling
  `base.life_threat` set. For children, `files/protocols/base.life_threat.yaml` records the paediatric
  rules as absent (**HB-C3**, needs a paediatrician). This pack asks nothing about it and adds no rule.
- **A recent injury that knocked out a permanent tooth** is a time-critical dental emergency for the
  physician/dentist pathway. The Ministry announced a revised *Dental Travma Klinik Protokolü*
  (SHGM, announced 17.07.2025 via gazido.org.tr); **the protocol text itself was not retrieved** (§4
  gap 2). Q12 asks only about *past* injury as history.
- Q4 (gum swelling) captures a local sign only; it feeds no life-threat rule.

### 2.3 Red-flag candidates — for physician review — not encoded

No level, route, register or location is proposed (invariants 1, 7, 21). The paediatric register
(`CALM`) and any age band are HB-C3's.

| Candidate | Source | Status |
|---|---|---|
| Toothache that starts on its own, or a gum boil | PE-S4 PDF p. 2 | not encoded; dentist decides urgency |
| Heart condition on the highest-risk list before a gum or root procedure | PE-S5 Table 4 | not encoded; a care-planning flag, not triage |

---

## 3. Candidate B1 Turkish pre-visit questions (14)

Register: formal **siz**, addressed to the **parent**; the child is always "çocuğunuz"; one concern and
exactly one question mark per turn; at most fifteen words per sentence; no diagnosis/treatment/prognosis
language; no numerals (invariant 22); written in our own words. **All CANDIDATE — clinician
(paediatric dentist) to approve wording.** No item carries a triage level. Q1 binds to
`basvuru_nedeni`. Checked by hand and by script against the Turkish PolicyGuard arms (unsigned —
HB-C23).

The pack line below replaces the fixed duration ask, which addressed the parent's own complaint (§4
gap 6). It is addressed to the parent and about the child, with the same text as neonatoloji so one clip
serves both. It changes the address only and carries no clinical content.

pack: duration_ask=Bu durumu ne zamandır fark ediyorsunuz?; duration_follow_up=Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün çocuğunuzu diş hekimine getiren en önemli konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Child complains of toothache** · archetype: `OBSERVATION.symptom_sign.v1` · source: PE-S2 PDF p. 66 ("Dişleri ağrıyan"); PE-S4 PDF p. 2
> "Çocuğunuz son zamanlarda diş ağrısından yakınıyor mu?"
gen: slot=dis_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q3.

**Q3 — Pain starts on its own** · archetype: `OBSERVATION.symptom_sign.v1` · source: PE-S4 PDF p. 2 ("spontaneous unprovoked pain")
> "Bu ağrı, çocuğunuz bir şey yemezken de kendiliğinden başlıyor mu?"
gen: slot=kendiliginden_agri; type=boolean; ask_if=dis_agrisi == true
CANDIDATE — clinician to approve wording. See §2.3.

**Q4 — Gum swelling or gum boil** · archetype: `OBSERVATION.symptom_sign.v1` · source: PE-S4 PDF p. 2 (sinus tract; soft-tissue inflammation)
> "Çocuğunuzun diş etinde şişlik ya da sivilce gibi bir kabarcık var mı?"
gen: slot=dis_eti_sisligi; type=boolean
CANDIDATE — clinician to approve wording. "Sivilce gibi bir kabarcık" is the everyday picture of a
draining gum boil.

**Q5 — Frequent sugary snacks or drinks between meals** · archetype: `OBSERVATION.story.v1` · source: PE-S3 Table 1 ("between-meal sugar-containing"); PE-S1 PDF p. 2 ("aşırı şeker tüketimi"); PE-S6 Table 1b
> "Çocuğunuz öğün aralarında şekerli yiyecek ya da içecekleri sık tüketiyor mu?"
gen: slot=ara_ogun_seker; type=boolean
CANDIDATE — clinician to approve wording. PE-S3's frequency cut-off stays in any rule, never in patient
text (invariant 22).

**Q6 — Bottle with milk or a sugary drink when falling asleep** · archetype: `OBSERVATION.story.v1` · source: PE-S3 Table 1 (bottle or cup with sugar at bedtime)
> "Çocuğunuz uykuya dalarken biberonla süt ya da şekerli bir içecek içiyor mu?"
gen: slot=gece_biberon; type=boolean
CANDIDATE — clinician to approve wording. Relevant to young children; any age gate is a clinical value
(§4 gap 4).

**Q7 — Teeth brushed morning and evening** · archetype: `OBSERVATION.story.v1` · source: PE-S1 PDF p. 8 ("Günde 2 kere yaşa uygun"); PE-S6 Table 1a; PE-S3 protective factors
> "Çocuğunuzun dişleri her gün sabah ve akşam fırçalanıyor mu?"
gen: slot=sabah_aksam_fircalama; type=boolean
CANDIDATE — clinician to approve wording. "Sabah ve akşam" carries the twice-a-day advice without a
numeral.

**Q8 — Toothpaste contains fluoride** · archetype: `OBSERVATION.story.v1` · source: PE-S1 PDF p. 6 (Tablo 1); PE-S3 protective factors; PE-S6 Table 1a
> "Çocuğunuzun diş macununda florür var mı?"
gen: slot=florurlu_macun; type=boolean; follow_up=Macunun kutusunda florür yazıyor mu?
CANDIDATE — clinician to approve wording. The strength and amount by age stay clinician-side.

**Q9 — Fear or strong worry about the dentist** · archetype: `OBSERVATION.story.v1` · source: PE-S2 PDF p. 70 ("Tedaviyi çok zor kabul eden"); PE-S3 Table 1 footnote (cooperation)
> "Çocuğunuz diş hekimine gitmekten korkuyor ya da çok kaygılanıyor mu?"
gen: slot=dis_hekimi_kaygisi; type=boolean
CANDIDATE — clinician to approve wording. Helps the team plan the visit; it is not a wellbeing screen.

**Q10a — Long-term health condition or special need** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PE-S3 Table 1 ("special health care needs"); PE-S1 PDF p. 8
> "Çocuğunuzun sürekli takip edilen bir sağlık sorunu ya da özel gereksinimi var mı?"
gen: slot=ozel_saglik_gereksinimi; type=boolean
CANDIDATE — clinician to approve wording. Yes/no gate for Q10b.

**Q10b — Description of the condition or need** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PE-S3 Table 1; PE-S1 PDF p. 8
> "Çocuğunuzun bu durumunu kısaca anlatır mısınız?"
gen: slot=ozel_saglik_gereksinimi_aciklama; type=string; ask_if=ozel_saglik_gereksinimi == true
CANDIDATE — clinician to approve wording. Split from Q10 (wave 8 verification): a boolean slot cannot
store the description, so it has its own string slot.

**Q11a — Heart condition from birth or past heart surgery** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PE-S5 PDF p. 4, Table 4 (AHA 2021)
> "Çocuğunuzda doğuştan gelen bir kalp sorunu ya da geçirilmiş kalp ameliyatı var mı?"
gen: slot=kalp_sorunu; type=boolean
CANDIDATE — clinician to approve wording. Base intake does not ask this. The clinician decides whether
the answer falls in Table 4 (§2.3). Yes/no gate for Q11b.

**Q11b — Description of the heart condition** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PE-S5 PDF p. 4, Table 4 (AHA 2021)
> "Çocuğunuzun kalp sorununu kısaca anlatır mısınız?"
gen: slot=kalp_sorunu_aciklama; type=string; ask_if=kalp_sorunu == true
CANDIDATE — clinician to approve wording. Split from Q11 (wave 8 verification), for the same reason as
Q10b.

**Q12 — Past injury to the teeth** · archetype: `OBSERVATION.story.v1` · source: PE-S2 PDF p. 72 (trauma history); AAPD periodicity PDF p. 5 (injuries are frequent; see §4 gap 3)
> "Çocuğunuzun dişleri daha önce bir düşme ya da darbeyle zarar gördü mü?"
gen: slot=onceki_dis_travmasi; type=boolean
CANDIDATE — clinician to approve wording. History only; a fresh knocked-out tooth is §2.2.

*(14 candidate questions: Q1 general intake; Q2–Q12 source-backed, with Q10 and Q11 each split into a
yes/no item and a description item; no candidate flag on any item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Current Türkiye-first paediatric dental guideline.** Beyond PE-S1 (TPD 2019) and PE-S2 (TDB 2012),
   no versioned TPD or Ministry caries-risk or history guideline was found on 2026-09-26. **NO SOURCE
   FOUND — clinician must supply** if one exists.
2. **Ministry *Dental Travma Klinik Protokolü* (revised, announced 17.07.2025).** Only the announcement
   was read (https://www.gazido.org/haber_detay.asp?id=99, pointing to
   https://shgmargestddb.saglik.gov.tr/TR-103681/tamamlananlar.html). **Protocol text NOT retrieved —
   clinician to supply** before any trauma item beyond Q12 is added.
3. **AAPD periodicity** (latest revision 2022; https://www.aapd.org/globalassets/media/policies_guidelines/bp_periodicity.pdf)
   is cited only for Q12 and gap 5; it was read for habits and injury prevention.
4. **Age gates.** Q6 (bottle at sleep) matters for young children; the cut-off age is a clinical value
   and is **not** proposed here (paediatric reviewer, HB-C3).
5. **Omitted to stay at twelve — sourced, clinician may swap in:** an adult helps or supervises brushing
   (PE-S3 PDF p. 4; PE-S6 Table 1a); pacifier or thumb-sucking habit (AAPD periodicity PDF p. 4; AAPD
   developing-dentition best practice, cited in `ortodonti.md` OR-S2); earlier dental visits (PE-S3
   "dental home/regular dental care"); sports and mouthguard use (PE-S2 PDF p. 72; AAPD periodicity PDF
   p. 5).
6. **Standard duration slot wording.** The generator adds `sikayet_suresi` ("Bu şikâyetiniz ne zamandır
   var?"), which addresses the parent's own complaint; for a proxy session it should refer to the child.
   Resolved by the `pack:` line in §3 (wave 8 verification): neonatoloji's parent-addressed text, which
   changes the address only.
7. **Numeric cut-offs** (PE-S3 sugar-exposure frequency; PE-S1 toothpaste strength and amount by age)
   belong in any rule or clinician note, never in patient text (invariant 22).
8. **Copyright / snapshot licence.** TPD, TDB and AAPD texts are copyrighted; DBOH is UK Crown copyright.
   A committed verbatim snapshot needs **permission or a legal-review decision.**
9. **Every triage level and all three RED axes** (invariant 21), and the paediatric age bands —
   deliberately **not** assigned; **paediatric reviewer** (HB-C3) must supply.
10. **openEHR** — leaf paths deferred (INT-032, HB-C12); no diet or oral-hygiene archetype in the OPT.
11. **PolicyGuard lexicon is itself unsigned (HB-C23).**
12. **Dental airway ask.** §2.2 leaves spreading swelling with breathing or swallowing difficulty to
    `base.life_threat`, whose paediatric airway rule is `draft_needs_source` (HB-C3), so no layer asks
    about the airway in this pack; Q4 (gum swelling) is the item this matters for. Four sibling dental
    packs carry an ungated airway ask instead. Whether every dental pack carries it under one shared
    slot id, or none does, is an owner and physician decision, joined by the paediatric reviewer
    (wave 8 verification §A, owner decision 1). No item is added here — **clinician decision pending**.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy** — `siz` to the parent, "çocuğunuz" throughout, ≤ B1, one question mark per
  item, ≤ fifteen words per sentence, no diagnosis/treatment/prognosis wording; each item CANDIDATE.
- **Inv. 7** — child emergencies stay in `base.life_threat` paediatric rules (HB-C3); this pack adds no
  rule.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at sign-off.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals; no frequency, strength or age is requested as a number.
- **HB-C1 / HB-C3** — awaits clinician sign-off and a paediatric reviewer's signature; NOT served.
