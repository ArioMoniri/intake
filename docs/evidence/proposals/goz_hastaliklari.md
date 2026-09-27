# Göz Hastalıkları (Ophthalmology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Göz Hastalıkları (Ophthalmology)
Taxonomy id: `goz_hastaliklari` (branches.yaml — cluster `sensory`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the primary sources are the Türk Oftalmoloji Derneği (TOD) official patient
  information site and TOD unit pages. They are **lay patient-education pages (2012 or undated)**, not
  versioned clinical guidelines; the AAO Preferred Practice Pattern benchmarks (December 2024) are cited
  as the international clinical corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7:** sudden vision loss (retinal artery occlusion as a stroke equivalent), giant-cell
  arteritis and acute angle-closure are **`base.life_threat` territory** (§2.2). This proposal does not
  add to or extend `base.life_threat`; the related questions below are **gate inputs only**.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; AAO PDF text
  extracted locally with `pdftotext`). Before sign-off each sentence MUST be re-checked against the
  primary text and committed as a verbatim snapshot with `source: {guideline_id, version, date, url,
  retrieved_on}`. Until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/goz_hastaliklari.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### G-S1 — TOD, "Mutlaka kapsamlı bir göz muayenesi gereken durumlar nelerdir?" (Türkiye)
- **guideline_id (proposed):** `TOD-GOZSAGLIGI-MUAYENE-2012` (lay patient page, NOT a guideline)
- **Publishing body:** Türk Oftalmoloji Derneği — "TOD Resmi Hasta Bilgilendirme Sitesi"
- **Date:** 11 Haziran 2012
- **URL:** https://gozsagligi.todnet.org/mutlaka-kapsamli-bir-goz-muayenesi-gereken-durumlar-nelerdir/index.html
- **Verbatim (lead sentence and the relevant list items, as rendered by the fetch):**
  > "Ancak aşağıdaki durumlarda zaman geçirilmeden göz hekimine başvurunuz:"
  > - "Görmede azalma ( gelip geçici olsa bile )"
  > - "Göz önünde yüzen, uçuşan cisimler ( siyah kılcıklar, tüycükler, noktalar, benekler, lekeler…)"
  > - "Olmayan ışık çakmaları görme"
  > - "Bir perde arkasından bakıyormuş gibi görme hissi"
  > - "Işıkların çevresinde renkli halkalar görme"
  > - "Gözde ve göz çevresinde ağrı hissi"
  > - "Göz çevresindeki deride ve gözde kızarıklık"
  > - "Çift görme"
  > - "Şeker hastalığı"
  > - "Ailede herhangi bir göz hastalığının olması"
- **Confidence: MEDIUM.** Turkish society, but a 2012 lay page; list numbering vs bullets must be
  re-checked on the live page.

### G-S2 — TOD, "Ani görme kaybı nedendir?" (Türkiye)
- **guideline_id (proposed):** `TOD-GOZSAGLIGI-ANI-GORME-KAYBI-2012` (lay page)
- **Date:** 16 Mayıs 2012 · **URL:** https://gozsagligi.todnet.org/ani-gorme-kaybi-nedendir/index.html
- **Verbatim (fragments returned by the fetch):**
  > "ister tek gözde ister iki gözde ani görme kaybı"
  > "acilen göz doktoruna muayene olmak gereklidir"
  > "Birkaç saat içinde göz doktorunun görmesi gerekir"
- **Confidence: MEDIUM** — fragments, not full sentences; re-verify full sentences before use.

### G-S3 — TOD, "Gelip geçici görme kaybı önemli bir hastalığın bulgusu olabilir mi?" (Türkiye)
- **Date:** 16 Mayıs 2012 · **URL:** https://gozsagligi.todnet.org/gelip-gecici-gorme-kaybi-onemli-bir-hastaligin-bulgusu-olabilir-mi/index.html
- **Verbatim:**
  > "Saniyeler veya dakikalar süren tek veya çift gözde perde inmesi, kararma veya beneklenme şeklinde
  > görme kaybı"
  > "Acilen göz ve kalp doktorunun görmesi gereklidir."

### G-S4 — TOD Glokom Birimi, "Primer Açı Kapanması Glokomu" (Türkiye)
- **guideline_id (proposed):** `TOD-GLOKOM-PAKG` · **Date:** undated in the retrieved page
- **URL:** https://www.todnet.org/glokom/pakg.htm
- **Verbatim (acute attack symptoms):**
  > "Hastalarda şiddetli ağrı, görmede azalma, atak olan göz tarafında alın, baş ağrısı bulantı kusma olur."
- **Confidence: LOW–MEDIUM** — undated; the fetch also reported the phrase "acil olarak tedavi için bir
  merkeze başvurması" without its full sentence (not relied on here).

### G-S5 — TOD Lens Bilgilendirme Projesi, "lens problemleri" (Türkiye)
- **guideline_id (proposed):** `TOD-LENS-PROBLEMLERI` · **Date:** none shown on the page
- **URL:** https://www.todnet.org/todlens/default2.asp?sayfa=lens_problemleri
- **Verbatim:**
  > "Kontakt lens kullanımına bağlı olarak korneal ülser gelişen hastalarda artan ağrı, kızarıklık,
  > akıntı, sulanma ve ışığa hassasiyet gibi önemli şikayetler ortaya çıkar."
  > "Bu durumda hastaların hemen kontakt lenslerini çıkararak acilen göz hekimine başvurmaları
  > gerekmektedir."
  > "Kornea enfeksiyonları, kontakt lense bağlı komplikasyonlar içinde göz kaybına neden olabilen en
  > önemli sorunlardan bir tanesidir."

### G-S6 — AAO, Summary Benchmarks for Preferred Practice Pattern® Guidelines (international)
- **guideline_id (proposed):** `AAO-PPP-BENCHMARKS-2024-12`
- **Publishing body:** American Academy of Ophthalmology · **Version:** December 2024 (© 2024)
- **URL:** https://www.aao.org/Assets/6adc45e7-6709-4075-a6e9-cd8c350929c9/638748982174000000/ppp-summary-benchmarks-24-full-set-pdf
- **Verbatim — PVD, Retinal Breaks and Lattice Degeneration (Management):**
  > "Patients should be advised to contact ophthalmologist promptly if they have a substantial change in
  > symptoms such as flashes, floaters, peripheral visual field loss, or decreased visual acuity"
- **Verbatim — Retinal and Ophthalmic Artery Occlusions (Care Management):**
  > "Acute, symptomatic OAO, CRAO, and BRAO from embolic etiologies should prompt an immediate referral
  > to the nearest stroke center or emergency department for prompt assessment for consideration of
  > intervention"
  > "Physicians should first consider GCA in patients 50 years of age or older"
- **Verbatim — Primary Angle-Closure Disease (History; Patient Education):**
  > "Ocular history (e.g., blurred vision, halos around lights, eye pain, headache, eye redness)"
  > "Patients should be informed about the symptoms of AACC and instructed to notify their
  > ophthalmologist immediately if symptoms occur"
- **Verbatim — Conjunctivitis (Initial Exam History) and Bacterial Keratitis (Patient Education):**
  > "Contact lens wear (lens type, hygiene and use regimen)"
  > "Educate patients with contact lenses about increased risk of infection associated with contact
  > lens, overnight wear, and importance of adherence to techniques to promote contact lens hygiene"

### G-S7 — AAO PPP 2024, "Posterior Vitreous Detachment, Retinal Breaks, and Lattice Degeneration"
- **Publishing body:** AAO PPP Retina/Vitreous Committee · **Version:** 2024 (published in *Ophthalmology*)
- **URL:** https://www.aao.org/education/preferred-practice-pattern/posterior-vitreous-detachment-retinal-breaks-latti
- **Verbatim:**
  > "An early diagnosis of a rhegmatogenous retinal detachment (RRD) is important because the rate of
  > successful retinal reattachment is higher and the visual results are better when repaired early,
  > especially before the RRD involves the macula."

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Reduced / blurred vision | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Sudden or transient vision loss | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Floaters | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Flashes (photopsia) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Curtain / shadow over vision | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Eye / periocular pain | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Eye / periocular redness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Coloured halos around lights | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Double vision | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Contact-lens wear | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); **no structured device-use archetype in the OPT** — see §4 |
| Q12 | Known diabetes | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

`files/protocols/base.life_threat.yaml` names, in `known_named_gaps`, the six rules that motivated the
pack, including **acute angle-closure** and **GCA**, and separately `rf.stroke_fast`.

| Eye alarm sign | Source | base.life_threat item | This proposal's role |
|---|---|---|---|
| Sudden painless vision loss (retinal artery occlusion) | G-S2, G-S3, G-S6 ("nearest stroke center") | `rf.stroke_fast` (named gap) | Q3 is a gate **input** only |
| Older adult with sudden vision loss (GCA) | G-S6 ("consider GCA … 50 years of age or older") | GCA (six-rule list) | Not drafted; flagged for clinician placement |
| Acute angle-closure (pain, halos, redness, reduced vision, nausea) | G-S4, G-S6 | acute angle-closure (six-rule list) | Q7, Q8, Q9 are gate **inputs** only |
| Sudden double vision | G-S1 | `rf.stroke_fast` (neuro overlap; see noroloji.md Q8) | Q10 is a gate **input** only |
| Chemical injury / penetrating eye trauma | NO verbatim retrieved (TOD first-aid page titles only) | **absent** from base.life_threat | Not drafted; §4 gap for the base.life_threat owner |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Q1 binds to the pack's
`basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün göz polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Reduced or blurred vision** · archetype: `OBSERVATION.symptom_sign.v1` · source: G-S1 ("Görmede azalma")
> "Görmenizde son zamanlarda bir azalma ya da bulanıklık fark ettiniz mi?"
CANDIDATE — clinician to approve wording.

**Q3 — Sudden or transient vision loss (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: G-S1 ("gelip geçici olsa bile"), G-S2, G-S3, G-S6 (RAO)
> "Kısa sürüp geçse bile gözünüzde ani bir görme kaybı ya da kararma oldu mu?"
CANDIDATE — clinician to approve wording. **Overlap: `rf.stroke_fast` / GCA (§2.2).** Source urgency
quoted only ("Birkaç saat içinde göz doktorunun görmesi gerekir"); no level asserted.

**Q4 — Floaters (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: G-S1 ("uçuşan cisimler"), G-S6 (PVD)
> "Gözünüzün önünde uçuşan noktalar ya da benekler görüyor musunuz?"
CANDIDATE — clinician to approve wording. New-versus-longstanding follow-up is a clinician item (§4).

**Q5 — Flashes of light (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: G-S1 ("Olmayan ışık çakmaları görme"), G-S6 (PVD)
> "Gerçekte ışık yokken gözünüzde ışık çakması ya da şimşek gibi parlamalar görüyor musunuz?"
CANDIDATE — clinician to approve wording.

**Q6 — Curtain or shadow over vision (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: G-S1 ("Bir perde arkasından bakıyormuş gibi görme hissi"), G-S6 ("peripheral visual field loss"), G-S7
> "Görüşünüzün bir kısmını perde ya da gölge kapatıyormuş gibi bir his oldu mu?"
CANDIDATE — clinician to approve wording.

**Q7 — Eye pain (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: G-S1 ("Gözde ve göz çevresinde ağrı hissi"), G-S4, G-S6 (PACD "eye pain")
> "Gözünüzde ya da göz çevresinde ağrı var mı?"
gen: slot=goz_agrisi; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: acute angle-closure (§2.2).**

**Q8 — Eye redness (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: G-S1 ("Göz çevresindeki deride ve gözde kızarıklık"), G-S6 (PACD "eye redness")
> "Gözünüzde ya da göz çevresindeki deride kızarıklık var mı?"
CANDIDATE — clinician to approve wording. **Overlap: acute angle-closure (§2.2).**

**Q9 — Coloured halos around lights (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: G-S1 ("Işıkların çevresinde renkli halkalar görme"), G-S6 (PACD "halos around lights")
> "Işıkların çevresinde renkli halkalar görüyor musunuz?"
gen: slot=isik_cevresinde_halka; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: acute angle-closure (§2.2).**

**Q10 — Double vision (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: G-S1 ("Çift görme")
> "Nesneleri çift görüyor musunuz?"
CANDIDATE — clinician to approve wording. **Overlap: `rf.stroke_fast` when sudden (§2.2).**

**Q11 — Contact-lens wear** · archetype: `OBSERVATION.story.v1` (narrative only) · source: G-S5, G-S6 (Conjunctivitis history; Bacterial Keratitis education)
> "Kontakt lens kullanıyor musunuz?"
gen: slot=kontakt_lens; type=boolean
CANDIDATE — clinician to approve wording. Risk-factor context for Q7/Q8 (G-S5); not a flag by itself.

**Q12 — Known diabetes** · archetype: `EVALUATION.problem_diagnosis.v1` · source: G-S1 ("Şeker hastalığı")
> "Size daha önce şeker hastalığı tanısı konuldu mu?"
CANDIDATE — clinician to approve wording. History item; no flag.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish clinical guideline** (TOD kılavuzu or T.C. Sağlık Bakanlığı protocol) for acute
   visual symptoms, red eye and flashes/floaters — only TOD **lay** pages from 2012 or undated were
   retrievable. **NO SOURCE FOUND — clinician must supply** the current versioned Turkish source.
2. **NICE CKS "Red eye" red flags** — `cks.nice.org.uk` returned HTTP 403; the red-flag list was seen
   only in search-engine summaries, so it is **not** quoted. **NO SOURCE FOUND (verbatim).**
3. **RCOphth guidance** on emergency eye referral — not retrieved. **NO SOURCE FOUND (verbatim).**
4. **AHA 2021 CRAO scientific statement** — `ahajournals.org` / `professional.heart.org` returned
   HTTP 403; only search summaries seen, **not** quoted. G-S6 (AAO RAO) is used instead.
5. **Per-symptom onset/duration follow-ups** (e.g., new versus longstanding floaters; how fast vision
   fell) — not drafted; no time threshold is pinned into patient copy. **Clinician must author.**
6. **Chemical injury and penetrating eye trauma** — universal emergencies absent from
   `base.life_threat`; TOD first-aid pages exist (titles seen) but no verbatim was retrieved.
   **NO SOURCE FOUND (verbatim) — base.life_threat owner / clinician to decide placement.**
7. **Family history of eye disease, hypertension, kidney disease** (G-S1 list items) — sourced but
   not drafted to stay within twelve questions. Clinician may swap them in.
8. **Contact-lens wear (Q11)** — the OPT has no device-use archetype; bound to `OBSERVATION.story.v1`
   as narrative only. Structured export needs an INT-032 archetype decision (INT-041 posture).
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) for eye presentations — no snapshot in repo; **no level
   proposed**. Every `candidate_flag` level and all three RED axes (route × register × location,
   invariant 21) are **deliberately unassigned** — clinician + `packages/protocols/triage` must supply.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE. Checked against the Turkish PolicyGuard arms (INT-248 lexicon).
- **Inv. 7** — sudden vision loss, GCA and acute angle-closure left in `base.life_threat` (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources G-S1…G-S7 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
