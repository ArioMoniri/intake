# Göğüs Hastalıkları (Pulmonology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Göğüs Hastalıkları (Pulmonology)
Taxonomy id: `gogus_hastaliklari` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the primary sources are the Türk Toraks Derneği (TTD) patient-information pages
  (KOAH, astım, akciğer kanseri, verem, uykuda solunum bozuklukları). They are **undated lay pages**
  (site footer "2026 © Türk Toraks Derneği"), not versioned clinical guidelines. TTD's versioned PDFs
  (KOAH raporu 2014, Astım rehberi 2020) returned **HTTP 404** at every URL tried. The GINA 2026 Summary
  Guide and the Scottish suspected-cancer referral guide are the international corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7:** acute breathlessness at rest, chest pain, anaphylaxis, massive haemoptysis and
  sepsis-like pneumonia are **`base.life_threat` territory** (§2.2). This proposal does not add to or
  extend `base.life_threat`; related questions below are **gate inputs only**.
- **Base-intake overlap avoided:** smoking ("Sigara kullanıyor musunuz?"), occupation ("Ne iş
  yapıyorsunuz?"), weight, medications and allergies are already asked by
  `packages/protocols/base/intake.yaml` and are **not** repeated.
- **Verification caveat (every quote in §1):** captured by automated retrieval on 2026-09-26 (HTML read
  as text; the GINA and Scottish PDFs text-extracted locally with `pdftotext` from the fetch tool's
  cached copy). Before sign-off each sentence MUST be re-checked against the primary text and committed
  as a verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`. Until then
  any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/gogus_hastaliklari.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### GH-S1 — TTD, "Kronik Obstrüktif Akciğer Hastalığı (KOAH)" (Türkiye)
- **guideline_id (proposed):** `TTD-HASTA-KOAH` (lay patient page, NOT a guideline)
- **Publishing body:** Türk Toraks Derneği · **Date:** none shown (footer "2026 © Türk Toraks Derneği")
- **URL:** https://toraks.org.tr/bilgilendirici-kaynaklar/hastaliklar/kronik-obstruktif-akciger-hastaligi-koah
- **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "KOAH'da en sık görülen yakınmalar nefes darlığı, öksürük ve balgam çıkarmadır."
  > "ısınma ya da yemek pişirme amacıyla çalı, çırpı ya da tezek yakmak ve bunların dumanına maruz
  > kalmak KOAH gelişimine neden olur."
  > "iş yeri ortamında organik-inorganik toz, duman ve gazlara maruz kalma sonucunda KOAH daha sık
  > görülmektedir."
- **Verbatim (the page's own patient self-check questions):**
  > "Haftanın çoğu günü sık sık öksürüyor musunuz?"
  > "Haftanın çoğu günü balgam çıkarıyor musunuz?"
  > "Yaşıtlarınıza göre nefesiniz daha kolay mı daralıyor?"
- **Note:** the page follows these with a count-based advice line (three or more "evet" → see a chest
  physician for spirometry). That is a **screening score, not intake** — it is quoted here for
  provenance only and is **not** encoded (§4 gap 3).
- **Confidence: MEDIUM.** Turkish society, undated lay page.

### GH-S2 — TTD, "Astım" (Türkiye)
- **guideline_id (proposed):** `TTD-HASTA-ASTIM` · **Date:** none shown
- **URL:** https://toraks.org.tr/bilgilendirici-kaynaklar/hastaliklar/astim · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Toz, duman koku gibi uyaranlar ile hemen öksürük, nefes darlığı ve göğüste baskı hissi gibi
  > yakınmalar ortaya çıkar."
  > "Genellikle gece veya sabaha karşı ortaya çıkar."
  > (history list) "Belirtilerin özellikle gece veya sabaha karşı olması"
  > (history list) "Egzersiz sonrası öksürük ya da hışıltılı solunum olması"

### GH-S3 — TTD, "Akciğer Kanseri" (Türkiye)
- **guideline_id (proposed):** `TTD-HASTA-AKCIGER-KANSERI` · **Date:** none shown
- **URL:** https://toraks.org.tr/bilgilendirici-kaynaklar/hastaliklar/akciger-kanseri · **retrieved_on:** 2026-09-26
- **Verbatim (list "Tümörün kendisinin ve göğüs içi yayılımına bağlı en sık görülenler", items):**
  > "Devamlı yoğun öksürük" · "Kanlı balgam ve kan tükürme" · "Nefes darlığı" · "Ses kısıklığı" ·
  > "Hışıltılı solunum" · "Tekrarlayan bronşit veya zatürre atakları"
  > (second list) "İştah kaybı, açıklanamayan kilo kaybı"

### GH-S4 — TTD, "Verem" (Türkiye)
- **guideline_id (proposed):** `TTD-HASTA-VEREM` · **Date:** none shown
- **URL:** https://toraks.org.tr/bilgilendirici-kaynaklar/hastaliklar/verem · **retrieved_on:** 2026-09-26
- **Verbatim (list items):**
  > "Balgamında kan görülmesi" · "Ateş" · "Gece terlemesi" · "Kilo kaybı, İştahsızlık"
  > "Tüberkülozun erken tanısı için 2-3 haftadan uzun süre öksürüğü olan kişilerin en kısa sürede
  > göğüs hastalıkları polikliniğine veya verem savaşı dispanserine başvurmaları gerekir."

### GH-S5 — TTD, "Uykuda Solunum Bozuklukları" (Türkiye)
- **guideline_id (proposed):** `TTD-HASTA-UYKU-APNE` · **Date:** none shown
- **URL:** https://toraks.org.tr/bilgilendirici-kaynaklar/hastaliklar/uykuda-solunum-bozukluklari · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "En önemli bulgu, eşinin veya yakınlarının tarif ettiği ve tanıklı apne dediğimiz uykuda nefes
  > durmasıdır."
  > "gündüz aşırı uyuklaması olanların tedavi başlayana kadar araba kullanmamaları"

### GH-S6 — GINA, *Summary Guide for Asthma Management and Prevention*, Updated 2026 (international)
- **guideline_id (proposed):** `GINA-SUMMARY-2026`
- **Publishing body:** Global Initiative for Asthma · **Version:** "Updated 2026" (© 2026)
- **URL:** https://ginasthma.org/wp-content/uploads/2026/07/GINA-Summary-Guide-2026-WEB-WMS.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (Table 1, p. 8):**
  > "Typical asthma symptoms are wheeze, shortness of breath, chest tightness, and cough."
  > "Symptoms often occur or worsen at night or when the person wakes up."
  > "Symptoms are often triggered by exercise, laughter, allergens, or cold air."
- **Verbatim (p. 9, occupational asthma):**
  > "If a patient's asthma started in adulthood, ask if there are allergens or irritants in the air at
  > work or at home"
- **Verbatim (p. 10, older adults):**
  > "If patients have a history of smoking or exposure to biomass fuel, consider the possibility of
  > chronic obstructive pulmonary disease (COPD)"
- **Verbatim (Figure 9, p. 36, severe presentation):**
  > "Unable to speak, drink or lie down" · "ACUTELY LIFE-THREATENING if drowsy, confused, cyanosed."
- **Confidence: HIGH** for wording (primary PDF). GINA is a strategy report, not a Turkish guideline.

### GH-S7 — Scottish Referral Guidelines for Suspected Cancer, Quick Reference Guide (international)
- **guideline_id (proposed):** `SCOT-USC-QRG-2019-01` (same document as KBB proposal K-S6)
- **Publishing body:** Scottish Primary Care Cancer Group / Scottish Government · **Version:** January 2019
- **URL:** https://www.gov.scot/binaries/content/documents/govscot/publications/advice-and-guidance/2019/01/scottish-referral-guidelines-suspected-cancer-january-2019-quick-reference/documents/00545248-pdf/00545248-pdf/govscot:document/00545248.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (LUNG CANCER — URGENT, "Urgent suspicion of cancer chest X-ray"):**
  > "• Any unexplained haemoptysis"
  > "• Unexplained and persistent (more than three weeks): • change in cough or new cough • dyspnoea
  > • chest/shoulder pain • loss of appetite • weight loss • chest signs"
  > "• New or not previously documented finger clubbing" · "• Persistent or recurrent chest infection"
- **Verbatim ("Urgent suspicion of cancer referral"):**
  > "• Persistent haemoptysis in smokers/ex-smokers over 40 years of age"
- **Confidence: HIGH** for the text (primary PDF); a UK referral guide, not a Turkish source.

### GH-S8 — NICE NG114, *Chronic obstructive pulmonary disease (acute exacerbation): antimicrobial prescribing* (international)
- **guideline_id (proposed):** `NICE-NG114`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), United Kingdom
- **Version / date:** NG114 · "Published: 05 December 2018" (page header)
- **URL:** https://www.nice.org.uk/guidance/ng114/chapter/Recommendations
- **retrieved_on:** 2026-10-02
- **Verbatim (rec 1.1.2):**
  > "Consider an antibiotic (see the recommendations on choice of antibiotic) for people with an acute
  > exacerbation of COPD, but only after taking into account: the severity of symptoms, particularly
  > sputum colour changes and increases in volume or thickness beyond the person's normal day-to-day
  > variation"

### GH-S9 — NICE NG245, *Asthma: diagnosis, monitoring and chronic asthma management* (BTS, NICE, SIGN; international)
- **guideline_id (proposed):** `NICE-NG245`
- **Publishing body:** NICE with the British Thoracic Society and SIGN, United Kingdom
- **Version / date:** NG245 · "Published: 27 November 2024" (page header)
- **URL:** https://www.nice.org.uk/guidance/ng245/chapter/Recommendations
- **retrieved_on:** 2026-10-02
- **Verbatim (rec 1.1.1, list items):**
  > "Obtain a structured clinical history in people with suspected asthma. Specifically, check for:" ·
  > "reported wheeze, noisy breathing, cough, breathlessness or chest tightness, and any variation (for
  > example, worse during the night or early morning, or seasonal) in these symptoms" · "any triggers
  > that make symptoms worse"
- **Verbatim (rec 1.4.1):**
  > "In people with adult-onset asthma, poorly controlled established asthma, or reappearance of
  > childhood asthma, check for a possible occupational component by asking: Are symptoms the same,
  > better or worse on days away from work? Are symptoms the same, better or worse when on holiday
  > (time away from work, longer than usual breaks, at weekends or between shifts)?"
- **Verbatim (rec 1.4.2):**
  > "Refer people with suspected occupational asthma to an occupational asthma specialist."

### GH-S10 — NICE NG12, *Suspected cancer: recognition and referral* (international)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), United Kingdom
- **Version / date:** NG12 · "Published: 23 June 2015" · "Last updated: 15 April 2026" (page header)
- **URL:** https://www.nice.org.uk/guidance/ng12/chapter/Recommendations-organised-by-site-of-cancer
- **retrieved_on:** 2026-10-02
- **Verbatim (rec 1.1.1):**
  > "Refer people using a suspected cancer pathway referral for lung cancer if they: have chest X‑ray
  > findings that suggest lung cancer, or are aged 40 and over with unexplained haemoptysis."

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Frequent cough most days | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Sputum most days | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Breathlessness compared with peers | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Blood in sputum | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Wheeze | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Night / early-morning symptoms | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Triggers (dust, smoke, smells, cold air) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Biomass smoke exposure | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); **no exposure archetype in the OPT** — see §4 |
| Q10 | Workplace dust / fume / gas exposure | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); **no exposure archetype in the OPT** — see §4 |
| Q11 | Unintended weight loss | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Witnessed breathing pauses in sleep | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q2a | Duration of cough | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3a | Change in sputum colour, amount or thickness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5a | Blood in sputum more than once | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6a | Cough or wheeze worse after exercise | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6b | Cough or wheeze worse in certain seasons | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10a | Symptoms ease away from work | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Chest alarm sign | Source | base.life_threat item | This proposal's role |
|---|---|---|---|
| Breathlessness at rest / severe asthma attack (cannot speak, drowsy, confused, cyanosed) | GH-S6 Fig. 9 | `rf.dyspnoea_rest` (named gap) | Q4, Q6 are gate **inputs** only |
| Chest pain or chest tightness | GH-S2 ("göğüste baskı hissi"), GH-S7 ("chest/shoulder pain") | `rf.chest_pain_cardiac_features`, `rf.chest_pain_no_cardiac_history` | Not drafted as a pack item; left to base |
| Heavy / massive haemoptysis | GH-S3, GH-S7 | `rf.severe_bleeding` (named gap) | Q5 is a gate **input** only |
| Pneumonia with fever and systemic illness | GH-S4 ("Ateş") | `rf.sepsis_like` (named gap) | Not drafted; flagged |
| Allergic airway reaction | — | `rf.anaphylaxis` (named gap) | Not drafted; base covers |
| Pulmonary embolism; pneumothorax | NO SOURCE retrieved | **absent** from base.life_threat | Not drafted; §4 gap for the base.life_threat owner |

### 2.3 Red-flag candidates found — **for physician review — not encoded**

None of these is a rule, a level or a route. They are the sources' own urgency statements, listed so
the reviewing clinician can decide whether any becomes a `draft_needs_source` rule.

| # | Candidate | Source (verbatim anchor) |
|---|---|---|
| RF-1 | Any unexplained blood in sputum | GH-S7 "Any unexplained haemoptysis"; GH-S3 "Kanlı balgam ve kan tükürme" |
| RF-2 | Persistent haemoptysis in a current or former smoker aged over forty | GH-S7 "Persistent haemoptysis in smokers/ex-smokers over 40 years of age" |
| RF-3 | Unexplained, persistent (more than three weeks) new/changed cough, breathlessness, chest/shoulder pain, appetite or weight loss | GH-S7 lung urgent list |
| RF-4 | New finger clubbing; persistent or recurrent chest infection | GH-S7 |
| RF-5 | Cough lasting longer than two to three weeks (tuberculosis work-up) | GH-S4 "2-3 haftadan uzun süre öksürüğü olan kişilerin en kısa sürede … başvurmaları gerekir" |
| RF-6 | Severe or life-threatening asthma presentation | GH-S6 Fig. 9 — **base.life_threat** (`rf.dyspnoea_rest`) |
| RF-7 | Adult-onset asthma with workplace exposure (refer without delay) | GH-S6 p. 9 |
| RF-8 | Excessive daytime sleepiness in a driver (safety counselling, not triage) | GH-S5 "araba kullanmamaları" |

---

## 3. Candidate B1 Turkish pre-visit questions (18)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Q2–Q4 ask about the same three
complaints as the TTD page's self-check (GH-S1) but in our own wording (verification wave 6); the TTD
sentences are no longer reused in patient copy. The page's count-based advice is **not** encoded and
must never be attached to these three items (§4 gap 3). Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün göğüs hastalıkları polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Frequent cough most days** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S1 (complaint only; own wording), GH-S3 ("Devamlı yoğun öksürük"), GH-S6
> "Günlerin çoğunda öksürüğünüz oluyor mu?"
gen: slot=cogu_gun_oksuruk; type=boolean
CANDIDATE — clinician to approve wording. Own wording; the TTD self-check sentence is not reused (§4 gap 4).

**Q2a — Duration of cough** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S4 ("2-3 haftadan uzun süre öksürüğü olan kişilerin en kısa sürede … başvurmaları gerekir"), GH-S7 ("Unexplained and persistent (more than three weeks): • change in cough or new cough")
> "Öksürüğünüz ne zamandır sürüyor?"
gen: slot=oksuruk_suresi; type=duration; ask_if=cogu_gun_oksuruk == true; follow_up=Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?
CANDIDATE — clinician to approve wording. No duration threshold in patient copy.

**Q3 — Sputum most days** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S1 (complaint only; own wording)
> "Günlerin çoğunda balgamınız oluyor mu?"
gen: slot=cogu_gun_balgam; type=boolean
CANDIDATE — clinician to approve wording. Own wording.

**Q3a — Change in sputum colour, amount or thickness** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S8 (NG114 rec 1.1.2, "sputum colour changes and increases in volume or thickness beyond the person's normal day-to-day variation")
> "Son zamanlarda balgamınızın rengi, miktarı ya da koyuluğu değişti mi?"
gen: slot=balgam_degisikligi; type=boolean; ask_if=cogu_gun_balgam == true
CANDIDATE — clinician to approve wording.

**Q4 — Breathlessness compared with peers (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S1 (complaint only; own wording), GH-S6 ("shortness of breath")
> "Aynı yaştaki kişilerden daha çabuk nefes nefese kalıyor musunuz?"
gen: slot=akranlardan_cabuk_nefes_darligi; type=boolean
CANDIDATE — clinician to approve wording. Own wording. **Overlap: `rf.dyspnoea_rest` (§2.2)** —
breathlessness at rest is base.life_threat's determination, not this pack's.

**Q5 — Blood in sputum (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S3 ("Kanlı balgam ve kan tükürme"), GH-S4 ("Balgamında kan görülmesi"), GH-S7, GH-S10 (NG12 rec 1.1.1, "are aged 40 and over with unexplained haemoptysis")
> "Son zamanlarda balgamınızda kan gördüğünüz ya da kan tükürdüğünüz oldu mu?"
gen: slot=balgamda_kan; type=boolean
CANDIDATE — clinician to approve wording. Same text and slot as `sigara_birakma_poliklinigi.md` Q3
(one audio clip). **Overlap: `rf.severe_bleeding` (§2.2).** Source urgency quoted only (RF-1, RF-2);
no level asserted.

**Q5a — Blood in sputum more than once** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S7 ("• Persistent haemoptysis in smokers/ex-smokers over 40 years of age")
> "Balgamınızda ya da tükürüğünüzde birden fazla kez kan gördünüz mü?"
gen: slot=balgamda_kan_tekrari; type=boolean; ask_if=balgamda_kan == true
CANDIDATE — clinician to approve wording. No age threshold in patient copy.

**Q6 — Wheeze (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S2 ("hışıltılı solunum"), GH-S3 ("Hışıltılı solunum"), GH-S6 ("wheeze")
> "Nefes alıp verirken göğsünüzden hışıltı ya da hırıltı sesi geliyor mu?"
gen: slot=hisiltili_solunum; type=boolean
CANDIDATE — clinician to approve wording. Distinct from the KBB stridor item (throat, on breathing in).

**Q6a — Cough or wheeze worse after exercise** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S2 ("Egzersiz sonrası öksürük ya da hışıltılı solunum olması"), GH-S6 ("Symptoms are often triggered by exercise, laughter, allergens, or cold air.")
> "Egzersiz yaptıktan sonra öksürüğünüz ya da hışıltınız artıyor mu?"
gen: slot=egzersizle_artis; type=boolean; ask_if=cogu_gun_oksuruk == true || hisiltili_solunum == true
CANDIDATE — clinician to approve wording.

**Q6b — Cough or wheeze worse in certain seasons** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S9 (NG245 rec 1.1.1, "any variation (for example, worse during the night or early morning, or seasonal) in these symptoms")
> "Öksürüğünüz ya da hışıltınız belli mevsimlerde artıyor mu?"
gen: slot=mevsimsel_solunum_artisi; type=boolean; ask_if=cogu_gun_oksuruk == true || hisiltili_solunum == true
CANDIDATE — clinician to approve wording.

**Q7 — Night or early-morning symptoms** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S2 ("gece veya sabaha karşı"), GH-S6 ("at night or when the person wakes up")
> "Gece veya sabaha karşı öksürük ya da nefes darlığı yaşıyor musunuz?"
gen: slot=gece_sabah_solunum_sikayeti; type=boolean
CANDIDATE — clinician to approve wording. Asks whether the symptoms occur at night or early morning,
so it assumes no symptom and needs no gate.

**Q8 — Triggers** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S2 ("Toz, duman koku gibi uyaranlar"), GH-S6 ("allergens, or cold air")
> "Toz, duman, koku ya da soğuk hava şikâyetlerinizi başlatıyor mu?"
gen: slot=tetikleyici_uyaranlar; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Biomass smoke exposure** · archetype: `OBSERVATION.story.v1` (narrative only) · source: GH-S1 ("çalı, çırpı ya da tezek yakmak"), GH-S6 p. 10 ("exposure to biomass fuel")
> "Evde ısınmak veya yemek için uzun süre tezek ya da çalı yaktınız mı?"
gen: slot=biyokutle_dumani; type=boolean
CANDIDATE — clinician to approve wording. The word *odun* is deliberately absent — see §5 (lexicon
false positive, routed to the HB-C23 lexicon owner). Risk-factor context only; not a flag.

**Q10 — Work-related dust, fume or gas exposure** · archetype: `OBSERVATION.story.v1` (narrative only) · source: GH-S1 ("toz, duman ve gazlara maruz kalma"), GH-S6 p. 9 (occupational asthma)
> "Çalıştığınız işlerde uzun süre toz, duman ya da gaz soludunuz mu?"
gen: slot=mesleki_toz_duman_gaz; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Asks about every job held, not only the current one (base
intake's `occupation` already asks the current job); not a flag.

**Q10a — Symptoms ease away from work** · archetype: `OBSERVATION.story.v1` (narrative only) · source: GH-S9 (NG245 rec 1.4.1, "Are symptoms the same, better or worse on days away from work? Are symptoms the same, better or worse when on holiday")
> "Hâlâ böyle bir işte çalışıyorsanız, şikâyetleriniz işe gitmediğiniz günlerde ya da tatilde azalıyor mu?"
gen: slot=is_disinda_azalma; type=boolean; ask_if=mesleki_toz_duman_gaz == true; delivery=text_first
CANDIDATE — clinician to approve wording.

**Q11 — Unintended weight loss** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S3 ("açıklanamayan kilo kaybı"), GH-S4 ("Kilo kaybı"), GH-S7 ("weight loss")
> "Son aylarda istemeden kilo kaybettiniz mi?"
gen: slot=istemsiz_kilo_kaybi; type=boolean
CANDIDATE — clinician to approve wording. No weight or time threshold is pinned into patient copy.
Captures the same fact as the base probe `rf_weight_loss_unintentional`; remove this duplicate once
HB-C1 writes that probe.

**Q12 — Witnessed breathing pauses in sleep** · archetype: `OBSERVATION.symptom_sign.v1` · source: GH-S5 ("tanıklı apne")
> "Uyurken nefesinizin durduğunu fark eden biri oldu mu?"
gen: slot=tanikli_apne; type=boolean
CANDIDATE — clinician to approve wording. Same text and slot as `obezite_poliklinigi.md` Q8; it no
longer assumes a bed partner. Daytime sleepiness while driving (RF-8) is a clinician counselling item,
not drafted.

*(18 candidate questions: 12 ungated, 6 gated detail items (Q2a, Q3a, Q5a, Q6a, Q6b, Q10a; §6).)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish clinical guideline** (TTD KOAH raporu, TTD Astım rehberi, T.C. Sağlık Bakanlığı
   protocol) — every TTD PDF / library URL returned **HTTP 404**; only undated TTD lay pages were
   retrievable. **NO SOURCE FOUND (verbatim) — clinician must supply** the current versioned source.
2. **GOLD 2026 report / pocket guide** — located (goldcopd.org) but the PDFs exceed the fetch tool's
   size limit and were **not downloaded** (a download needs user approval). The "key indicators" list
   is **not** quoted. **NO SOURCE FOUND (verbatim).**
3. **TTD three-of-four self-check score** (GH-S1) — a screening rule, not intake. Not encoded; the
   clinician decides whether it belongs anywhere.
4. **Permission for TTD wording** — resolved for patient copy: Q2–Q4 were reworded in our own words
   (verification wave 6), so no TTD sentence is spoken to the patient. Permission is still needed
   before any verbatim TTD snapshot is committed; it was not sought, and no HB row exists for it yet.
   The owner must register one.
5. **NICE NG12 lung recommendations** — closed 2026-10-02: nice.org.uk reachable; rec 1.1.1 recorded
   as GH-S10.
6. **Sourced but not drafted** (to stay at twelve): chest tightness (GH-S2, GH-S6; also chest-pain
   overlap), night sweats and fever (GH-S4), hoarseness (GH-S3), recurrent chest infections (GH-S3,
   GH-S7), snoring and daytime sleepiness (GH-S5). Clinician may swap them in.
7. **Pulmonary embolism, pneumothorax** — absent from `base.life_threat`; no source retrieved.
   **NO SOURCE FOUND — base.life_threat owner / clinician.**
8. **Exposure items (Q9, Q10)** — the OPT has no exposure archetype; bound to `OBSERVATION.story.v1`
   as narrative only. Structured export needs an INT-032 archetype decision (INT-041 posture).
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (route × register × location, invariant 21) are
   **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words, no
  diagnosis/treatment/prognosis wording, no lexicon jargon (e.g. *dispne* avoided). Checked against the
  Turkish PolicyGuard arms (INT-248 lexicon). **Lexicon finding:** the common word *odun* matches the
  `sen`-past arm (`…dun` like *geldin*) and would be rejected; Q9 avoids it. Routed to the lexicon owner (HB-C23).
- **Inv. 7** — breathlessness at rest, chest pain, severe bleeding, sepsis left in `base.life_threat` (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question; source thresholds stay in §1–§2 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources GH-S1…GH-S7 only.
- **HB-C1** — awaits clinician sign-off; NOT served.

---

## 6. INT-427 dynamic wave — change log (2026-10-02)

| item | change | gate | source id |
|---|---|---|---|
| Q2a `oksuruk_suresi` | added (duration; follow-up) | `cogu_gun_oksuruk == true` | GH-S4, GH-S7 |
| Q3a `balgam_degisikligi` | added | `cogu_gun_balgam == true` | GH-S8 |
| Q5a `balgamda_kan_tekrari` | added; reworded in fix round (V-GH-3): "Balgamınızda ya da tükürüğünüzde birden fazla kez kan gördünüz mü?" | `balgamda_kan == true` | GH-S7 |
| Q6a `egzersizle_artis` | added | `cogu_gun_oksuruk == true \|\| hisiltili_solunum == true` | GH-S2, GH-S6 |
| Q6b `mevsimsel_solunum_artisi` | added | `cogu_gun_oksuruk == true \|\| hisiltili_solunum == true` | GH-S9 |
| Q10a `is_disinda_azalma` | added; reworded in fix round (V-GH-1): "Hâlâ böyle bir işte çalışıyorsanız, şikâyetleriniz işe gitmediğiniz günlerde ya da tatilde azalıyor mu?"; delivery set to `text_first` (V-GH-2) | `mesleki_toz_duman_gaz == true` | GH-S9 |
| Q10 `mesleki_toz_duman_gaz` | delivery set to `text_first` (fix round, V-GH-2); text unchanged | — (ungated) | GH-S1, GH-S6 |
| Q5 `balgamda_kan` | source line adds GH-S10 (fix round, V-GH-4); text unchanged | — (ungated) | GH-S10 |
| §1 GH-S9 | rec 1.4.2 quote added (red-flag row 4) | — | GH-S9 |
| §1 GH-S10 | added (NG12 rec 1.1.1; V-GH-4) | — | GH-S10 |
| §4 gap 5 | closed (V-GH-4) | — | GH-S10 |
