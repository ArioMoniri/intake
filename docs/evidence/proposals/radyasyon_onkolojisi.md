# Radyasyon Onkolojisi (Radiation Oncology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Radyasyon Onkolojisi (Radiation Oncology)
Taxonomy id: `radyasyon_onkolojisi` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  short verbatim fragment + citation). Where no source was found, the row reads **"NO SOURCE FOUND —
  clinician must supply"**. Nothing was invented.
- **Turkish first:** the Turkish sources are two Türk Radyasyon Onkolojisi Derneği (TROD) patient
  pages and two Türk Tıbbi Onkoloji Derneği (TTOD) public pages. They are **undated lay pages, not
  versioned guidelines**; no TROD clinical guideline for consultation intake was found (§4 gap 1). The
  AAPM TG-203 report (implanted cardiac devices), the ESTRO/EORTC re-irradiation consensus, the NCI
  side-effects page and MSK patient-education pages are the international corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level; no level is asserted.
- **Invariant 7:** metastatic spinal cord compression, superior vena cava obstruction, neutropenic fever
  during concurrent chemotherapy and heavy bleeding are **`base.life_threat` / physician territory**
  (§2.2). None is asked here and nothing extends `base.life_threat`.
- **Base overlap avoided:** pregnancy, medications, blood thinners, allergies, smoking, immunosuppression
  and weight are collected by `packages/protocols/base/intake.yaml` and are **not** repeated.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; journal
  abstracts via the PubMed API). Before sign-off each fragment MUST be re-checked against the primary
  text and committed as a verbatim snapshot with `source: {guideline_id, version, date, url,
  retrieved_on}`. Until then any derived rule stays `status: draft_needs_source`.
- **Copyright:** questions are written in our own words; sources are quoted as short fragments only.
- This file does **not** edit `packages/protocols/specialty/radyasyon_onkolojisi.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### RT-S1 — TROD, "Radyoterapi Sırasında Dikkat Edilmesi Gerekenler" (Türkiye)
- **guideline_id (proposed):** `TROD-HASTA-RT-SIRASINDA` (lay patient page, NOT a guideline)
- **Publishing body:** Türk Radyasyon Onkolojisi Derneği · **Date:** none shown · **retrieved_on:** 2026-09-26
- **URL:** https://www.trod.org.tr/radyoterapi-sirasinda-dikkat-edilmesi-gerekenler
- **Verbatim fragments:**
  > "Tedavi alanını ılık su ve nemlendirici sabun ile yıkayınız"
  > "Düşük enerji hissiniz olabilir"
  > "Tedavi başladıktan sonra hissettiğiniz değişiklikleri net olarak ifade edip, radyoterapiye bağlı olup olmadığını lütfen öğreniniz"
- **Confidence: MEDIUM** — Turkish society, undated lay page.

### RT-S2 — TROD, "Eksternal Radyoterapi Nedir ve Nasıl Uygulanılır?" (Türkiye)
- **guideline_id (proposed):** `TROD-HASTA-EKSTERNAL-RT` · **Date:** none shown
- **URL:** https://www.trod.org.tr/eksternal-radyoterapi-nedir-ve-nasil-uygulanilir
- **Verbatim fragment:**
  > "Simülasyon ve günlük tedavi sırasında hastanın tam olarak aynı pozisyonda ve de hareketsiz olmasına dikkat edilmesi gerekir."
- The page also describes head-and-neck masks and vacuum beds (paraphrase of the fetch, not quoted).
- **Confidence: MEDIUM.**

### RT-S3 — TTOD, "Baş ve Boyun Kanseri Tedavisi" (kanser.org public page)
- **guideline_id (proposed):** `TTOD-TOPLUM-BAS-BOYUN-TEDAVI` · **Date:** none shown
- **URL:** https://www.kanser.org/saglik/toplum/kanser-turleri-alt-kategori/bas-ve-boyun-kanseri-tedavisi
- **Verbatim fragment:**
  > "ağız kuruluğu, yutma güçlüğü ve cilt hasarına"
- **Confidence: LOW–MEDIUM** — fragment only.

### RT-S4 — TTOD, "Yumurtalık (Over) Kanseri Radyoterapi" (kanser.org public page)
- **guideline_id (proposed):** `TTOD-TOPLUM-OVER-RT` · **Date:** none shown
- **URL:** https://www.kanser.org/saglik/toplum/kanser-turleri-alt-kategori/yumurtalik-over-kanseri-radyoterapi
- **Verbatim fragments:**
  > "tedavi edilen bölgedeki cilt, güneş yanığı gibi görünebilir"
  > "pelvis tedavi ediliyorsa bazen akıntıyla birlikte vajinal tahriş"
- The page lists nausea/vomiting and diarrhoea as side effects (single-word items).

### RT-S5 — NCI, "Radiation Therapy Side Effects" (international, public domain)
- **guideline_id (proposed):** `NCI-RT-SIDE-EFFECTS` · **Updated:** 15 May 2025
- **URL:** https://www.cancer.gov/about-cancer/treatment/types/radiation-therapy/side-effects
- **Verbatim (table, by treated area):** Head and neck and chest — "Fatigue", "Skin changes"; pelvis
  and rectum — "Diarrhea", "Fatigue", "Skin changes" plus urinary and bladder changes.
  > "Radiation not only kills or slows the growth of cancer cells, it can also affect nearby healthy cells."

### RT-S6 — Memorial Sloan Kettering, "About Radiation Therapy to Your Pelvis"
- **guideline_id (proposed):** `MSK-PE-RT-PELVIS` · **Last updated:** 12 June 2025
- **URL:** https://www.mskcc.org/cancer-care/patient-education/radiation-therapy-pelvis
- **Verbatim fragments:**
  > "Do not move once your simulation starts. It's important that you stay in the same position."
  > "you may need to urinate (pee) often and feel a burning sensation when you urinate."
  > "Many people develop diarrhea (loose, watery bowel poop)"

### RT-S7 — Memorial Sloan Kettering, "About External Beam Radiation Therapy"
- **guideline_id (proposed):** `MSK-PE-EBRT` · **Last updated:** 9 June 2023
- **URL:** https://www.mskcc.org/cancer-care/patient-education/external-beam-radiation-therapy
- **Verbatim fragment:**
  > "Tell a member of your care team if you think you will be uncomfortable lying still"
- **Confidence: LOW** — the automated fetch returned this sentence while also reporting the topic as
  absent; re-verify on the live page before use.

### RT-S8 — AAPM TG-203, implanted cardiac devices in radiotherapy (international)
- **guideline_id (proposed):** `AAPM-TG203-2019`
- **Citation:** Miften M, Mihailidis D, Kry SF, et al. Management of radiotherapy patients with
  implanted cardiac pacemakers and defibrillators: A Report of the AAPM TG-203. *Med Phys.*
  2019;46(12):e757-e788. DOI 10.1002/mp.13838 (abstract retrieved via the PubMed API, PMID 31571229)
- **Verbatim (abstract):**
  > "Managing radiotherapy patients with implanted cardiac devices (implantable cardiac pacemakers and implantable cardioverter-defibrillators) has been a great practical and procedural challenge in radiation oncology practice."
  > "lays out the methodology for patient management in a comprehensive and concise way, in every step of the entire radiotherapy process."
- Full report (Wiley) not retrieved; step-level text must be snapshotted before use.

### RT-S9 — ESTRO/EORTC consensus on re-irradiation (international)
- **guideline_id (proposed):** `ESTRO-EORTC-REIRRADIATION-2022`
- **Citation:** Andratschke N, Willmann J, Appelt AL, et al. *Lancet Oncol.* 2022;23(10):e469-e478.
  DOI 10.1016/S1470-2045(22)00447-8 (abstract via the PubMed API, PMID 36174633)
- **Verbatim (abstract):**
  > "Re-irradiation can be considered for local recurrence or new tumours adjacent to a previously irradiated site"
  > "Our consensus on re-irradiation aims to assist in re-irradiation decision making, and to standardise the classification of different forms of re-irradiation and reporting."

### RT-S10 — TSNM, F-18 FDG PET/BT guideline — **cross-specialty support for Q7 only**
- Soydal Ç, et al. *Nucl Med Semin.* 2020;6:339-357 (full entry in `nukleer_tip.md` NT-S1).
  > "olası klostrofobisinin sorgulanması, tanısal olmayan çalışmaları ve tetkik iptallerini azaltacak"

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Previous radiotherapy | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no procedure-history archetype in the OPT — §4 |
| Q3 | Site of previous radiotherapy | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; as Q2 |
| Q4 | End date of previous radiotherapy | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; as Q2 |
| Q5 | Implanted cardiac device | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no device archetype in the OPT — §4 |
| Q6 | Difficulty lying flat and still | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q7 | Distress in closed spaces / face covered | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q8 | Fatigue limiting daily activities | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Skin reaction in the treated area | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Dry mouth or difficulty swallowing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Burning or frequent urination | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Diarrhoea or bowel change | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm | Source | base item | This proposal's role |
|---|---|---|---|
| New back pain with leg weakness, numbness or loss of bladder/bowel control (spinal cord compression; common reason for urgent palliative radiotherapy) | NICE NG234 **HTTP 403** — **NO SOURCE FOUND (verbatim)** | **absent**; nearest `rf_new_neuro_deficit_subacute` probe | **Not asked here** |
| Face, neck or arm swelling with breathlessness (superior vena cava obstruction) | **NO SOURCE FOUND (verbatim)** | **absent**; nearest `rf.dyspnoea_rest` | **Not asked here** |
| Fever during concurrent chemoradiotherapy (neutropenic fever) | `tibbi_onkoloji.md` TO-S1 (**SECONDARY**) | neutropenic fever (six-rule list) | **Not asked here** |
| Mouth or throat pain stopping eating or drinking | `tibbi_onkoloji.md` TO-S1 (**SECONDARY**) | **absent** (dehydration family) | Q10 captures presence only (gate input) |
| Diarrhoea with weakness | `tibbi_onkoloji.md` TO-S1 (**SECONDARY**) | **absent** | Q12 captures presence only (gate input) |
| Heavy bleeding from a treated area | **NO SOURCE FOUND (verbatim)** | `rf.severe_bleeding` (named gap) | **Not asked here** |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Implanted pacemaker or defibrillator before planning (device-safety alert, not a patient emergency) | "implanted cardiac devices (implantable cardiac pacemakers and implantable cardioverter-defibrillators)" | RT-S8 |
| Previous radiotherapy to or near the planned area (cumulative-dose alert) | "previously irradiated site" | RT-S9 |
| Spinal cord compression, SVC obstruction | **NO SOURCE FOUND (verbatim)** | clinician must supply |
| Sudden numbness or movement problem; new breathlessness; fever during chemotherapy | see `tibbi_onkoloji.md` §2.3 (**SECONDARY**) | TO-S1 |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Q1 binds to the pack's
`basvuru_nedeni` slot. "Işın tedavisi" is used as the plain-language name for radiotherapy. Each draft
was run through the Turkish PolicyGuard `inspect_sentence` arms (INT-248 lexicon) with zero findings.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün radyasyon onkolojisi polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Previous radiotherapy** · archetype: `OBSERVATION.story.v1` · source: RT-S9 ("previously irradiated site")
> "Daha önce vücudunuzun herhangi bir bölgesine ışın tedavisi uygulandı mı?"
gen: slot=onceki_isin_tedavisi; type=boolean; follow_up=Daha önce radyoterapi aldınız mı?
CANDIDATE — clinician to approve wording. History item; gates Q3, Q4 and Q9.

**Q3 — Site of previous radiotherapy** · archetype: `OBSERVATION.story.v1` · source: RT-S9 ("standardise the classification … and reporting")
> "Önceki ışın tedavisi vücudunuzun hangi bölgesine uygulandı?"
gen: slot=onceki_isin_bolgesi; type=string; ask_if=onceki_isin_tedavisi == true; follow_up=Işın tedavisi hangi organa ya da bölgeye yapıldı?
CANDIDATE — clinician to approve wording. Dose and technique come from records, never from the patient.

**Q4 — When previous radiotherapy ended** · archetype: `OBSERVATION.story.v1` · source: RT-S9
> "Önceki ışın tedaviniz ne zaman bitti?"
gen: slot=onceki_isin_bitis; type=date; ask_if=onceki_isin_tedavisi == true; follow_up=Ay ve yıl olarak yaklaşık söyleyebilir misiniz?
CANDIDATE — clinician to approve wording. Date slot; no numeral is spoken back (invariant 22).

**Q5 — Implanted cardiac device** · archetype: `OBSERVATION.story.v1` · source: RT-S8 ("implanted cardiac devices")
> "Vücudunuzda kalp pili ya da şok cihazı gibi bir cihaz var mı?"
gen: slot=kalp_cihazi; type=boolean; follow_up=Göğsünüzde deri altına takılmış bir kalp cihazı var mı?
CANDIDATE — clinician to approve wording. "Şok cihazı" is the lay name for an implanted defibrillator.

**Q6 — Difficulty lying flat and still** · archetype: `OBSERVATION.story.v1` · source: RT-S2 ("aynı pozisyonda ve de hareketsiz"), RT-S6 ("stay in the same position"), RT-S7
> "Bir süre sırtüstü ve hareketsiz yatmak sizin için zor olur mu?"
gen: slot=hareketsiz_yatma_zorlugu; type=boolean; follow_up=Sırtüstü yatınca ağrı ya da nefes darlığı oluyor mu?
CANDIDATE — clinician to approve wording.

**Q7 — Distress in closed spaces or with the face covered** · archetype: `OBSERVATION.story.v1` · source: RT-S2 (head-and-neck masks), RT-S10 ("klostrofobisinin sorgulanması")
> "Kapalı alanlarda ya da yüzünüz örtülüyken kendinizi çok huzursuz hisseder misiniz?"
gen: slot=kapali_alan_huzursuzluk; type=boolean; follow_up=Dar ve kapalı yerlerde bunaldığınız olur mu?
CANDIDATE — clinician to approve wording. Radiotherapy-specific Turkish source for this item: **NO
SOURCE FOUND** (§4 gap 4).

**Q8 — Fatigue limiting daily activities** · archetype: `OBSERVATION.symptom_sign.v1` · source: RT-S1 ("Düşük enerji hissiniz olabilir"), RT-S5 ("Fatigue")
> "Son zamanlarda günlük işlerinizi zorlaştıran bir yorgunluk var mı?"
gen: slot=yorgunluk_gunluk_is; type=boolean; follow_up=Gün içinde sık sık dinlenme ihtiyacı duyuyor musunuz?
CANDIDATE — clinician to approve wording.

**Q9 — Skin reaction in the treated area** · archetype: `OBSERVATION.symptom_sign.v1` · source: RT-S4 ("güneş yanığı gibi görünebilir"), RT-S1 ("Tedavi alanını"), RT-S5 ("Skin changes")
> "Işın uygulanan bölgedeki derinizde kızarıklık, kaşıntı ya da soyulma var mı?"
gen: slot=isin_bolgesi_cilt; type=boolean; ask_if=onceki_isin_tedavisi == true; follow_up=Işın uygulanan bölgede deriniz güneş yanığı gibi görünüyor mu?
CANDIDATE — clinician to approve wording. Asked only when Q2 is yes (on-treatment or follow-up visits).

**Q10 — Dry mouth or difficulty swallowing (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: RT-S3 ("ağız kuruluğu, yutma güçlüğü"), RT-S5 (head and neck)
> "Ağız kuruluğu ya da yutkunurken zorlanma yaşıyor musunuz?"
gen: slot=agiz_kurulugu_yutma; type=boolean; follow_up=Yemek yutarken takılma ya da acı hissediyor musunuz?
CANDIDATE — clinician to approve wording. Inability to eat or drink is §2.2; presence only here.

**Q11 — Burning or frequent urination** · archetype: `OBSERVATION.symptom_sign.v1` · source: RT-S6 ("urinate (pee) often and feel a burning sensation"), RT-S5 (pelvis)
> "İdrar yaparken yanma ya da sık sık tuvalete gitme ihtiyacı oluyor mu?"
gen: slot=idrar_yanma_siklik; type=boolean; follow_up=Her zamankinden daha sık idrara çıkıyor musunuz?
CANDIDATE — clinician to approve wording. Turkish source for pelvic urinary effects: **NO SOURCE FOUND** (§4 gap 5).

**Q12 — Diarrhoea or bowel change (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: RT-S4 (diarrhoea listed), RT-S6 ("Many people develop diarrhea"), RT-S5
> "Son zamanlarda ishal ya da dışkılama alışkanlığınızda bir değişiklik oldu mu?"
gen: slot=ishal_diskilama_degisiklik; type=boolean; follow_up=Dışkınız her zamankinden daha sık ya da daha sulu mu?
CANDIDATE — clinician to approve wording.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish clinical guideline** (TROD kılavuzu or T.C. Sağlık Bakanlığı protocol) for the
   radiotherapy consultation history — only TROD/TTOD **lay** pages were retrievable; the TROD
   consent-form and patient pages at `app_members_consent_forms` and `app_society_patient?id=6`
   returned 404. **NO SOURCE FOUND — clinician must supply.**
2. **AAPM TG-203 full report (RT-S8)** — abstract only; step-level device workflow not quoted.
3. **Spinal cord compression, SVC obstruction** — NICE NG234 returned HTTP 403; no Turkish society
   patient text found. **NO SOURCE FOUND (verbatim) — base.life_threat owner / clinician decide placement.**
4. **Closed-space distress for radiotherapy (Q7)** — supported only by TROD's mask description and the
   nuclear-medicine PET guideline; no radiotherapy-specific Turkish sentence retrieved.
5. **Pelvic urinary and bowel effects in Turkish** — TROD page did not cover them; Q11 rests on
   MSK/NCI, Q12 on TTOD RT-S4 plus MSK/NCI.
6. **Connective-tissue disease and other radiosensitivity history** — clinically discussed but **NO
   SOURCE FOUND** in this retrieval; not drafted. **Clinician decision.**
7. **Sourced but not drafted (to stay within twelve):** nausea/vomiting (RT-S4), hair loss in the
   treated area (RT-S5), vaginal irritation with discharge (RT-S4), cough or breathing change after
   chest radiotherapy (RT-S5). Clinician may swap them in.
8. **Procedure and device history (Q2–Q7)** — no procedure-history or device archetype in the OPT; bound
   to `OBSERVATION.story.v1` as narrative only (INT-032 decision needed).
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (route × register × location, invariant 21) are
   **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE and checked against the Turkish PolicyGuard arms.
- **Inv. 7** — spinal cord compression, SVC obstruction, neutropenic fever and heavy bleeding left to
  base / physician (§2.2); none asked here.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question; Q4 is a date slot, never spoken as digits.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources RT-S1…RT-S10 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
