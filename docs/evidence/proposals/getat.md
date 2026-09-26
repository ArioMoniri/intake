# GETAT — Geleneksel ve Tamamlayıcı Tıp (Traditional & Complementary Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research subagent (guideline researcher) · Date: 2026-09-26 · Specialty: GETAT (Geleneksel ve Tamamlayıcı Tıp)
Taxonomy id: `getat` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** that records which complementary practices
the patient has used, and the history the GETAT physician needs for **interaction and safety** —
**not** diagnosis, not triage authority, and **not** an endorsement of any practice. This file is a
*proposal for a clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and pins **no**
clinical value.

---

## 0. Posture / what this document is and is not

- **Neutral by design.** Nothing in patient copy says or implies that a practice works, is safe, is
  natural or is recommended. The questions record *use*, *where* and *what happened*, and whether the
  treating physician knows — the safety information both GETAT and conventional clinicians need.
  Professional bodies dispute the evidence base (a Türk Tabipleri Birliği statement on the 2026
  regulation was seen in search results only and is **not** quoted); neutrality is the only defensible
  wording. No efficacy claim appears anywhere in this file (invariant 20 spirit).
- **The 2014 regulation is repealed.** The task brief named the *GETAT Uygulamaları Yönetmeliği* of
  27/10/2014. It was **repealed** by the new *Geleneksel ve Tamamlayıcı Tıp Uygulamaları Yönetmeliği*,
  Resmî Gazete 28/04/2026, sayı 33237 (GT-S1 Madde 19). GT-S1 is used; the SB information pages
  (GT-S2, GT-S3) date from 2017, under the old regulation, and must be re-checked against the 2026
  *uygulama kılavuzları*.
- Every clinical claim quotes a **real source that was actually retrieved** on 2026-09-26; where none
  was found the row reads **"NO SOURCE FOUND"**. Nothing was invented.
- **Not repeated from base** (`packages/protocols/base/intake.yaml`): herbal and non-prescription
  products (`otc_herbal` — this covers fitoterapi products), blood thinners (`anticoagulant_use`),
  pregnancy (`pregnancy_status`), allergies (`allergies`), medications.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger.
- **Verification caveat:** GT-S1 was read from a print of the Resmî Gazete page (hosted by OHSAD),
  downloaded to a scratch directory (never the repo) and extracted locally with `pdftotext`; its annexes
  (Ek-1 … Ek-5) were **not** in the print. GT-S2 … GT-S5 were captured with WebFetch (model-rendered).
  Before sign-off each sentence MUST be re-checked against the primary text and committed as a verbatim
  snapshot with `source: {guideline_id, version, date, url, retrieved_on}`.
- This file does **not** edit `packages/protocols/specialty/getat.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### GT-S1 — *Geleneksel ve Tamamlayıcı Tıp Uygulamaları Yönetmeliği* (Türkiye)
- **guideline_id (proposed):** `RG-2026-33237-GETAT` (regulation)
- **Publishing body:** T.C. Sağlık Bakanlığı · **Resmî Gazete:** 28 Nisan 2026, sayı 33237 (in force on publication)
- **URLs:** https://www.resmigazete.gov.tr/eskiler/2026/04/20260428-2.htm (as printed on the retrieved
  copy) · copy retrieved: https://ohsad.org/wp-content/uploads/2026/04/getat-yonetmeligi-28-Nisan-2026.pdf ·
  SB notice (SHGM GETAT Daire, 28 Nisan 2026): https://shgmgetatdb.saglik.gov.tr/TR-82169/geleneksel-ve-tamamlayici-tip-uygulamalari-yonetmeligi.html
  ("28.04.2026 tarihli ve 33237 sayılı Resmi Gazetede yayımlanarak yürürlüğe giren Yönetmelik")
- **Verbatim (extracted locally):**
  > Madde 1(1): "Bu Yönetmeliğin amacı, insan sağlığına yönelik geleneksel ve tamamlayıcı tıp uygulama
  > yöntemlerini belirlemek, bu yöntemleri uygulayacak kişilerin yetkilendirilmeleri ile bu yöntemlerin
  > uygulanacağı sağlık kuruluşlarının çalışma ve denetlenmesine ilişkin usul ve esasları düzenlemektir."
  > Madde 8(1): "Uygulamalar Ek-2'de belirlenen alanlarla sınırlıdır."
  > Madde 9(1): "Uygulamalar, Bakanlıkça yetkilendirilmiş uygulama merkezi veya uygulama ünitelerinde,
  > ilgili uygulama alanında Bakanlıkça tescil edilmiş sertifikaya sahip olan GETAT uygulayıcıları
  > tarafından yapılır."
  > Madde 11(1): "Hastalık durumunda tanı konulması ve tedavi planının oluşturulması, 1219 sayılı Kanun
  > hükümleri uyarınca yalnızca tabip veya diş tabibi tarafından gerçekleştirilir;"
  > Madde 11(3): "Uygulamalar diğer tıbbi tedavileri aksatacak veya geciktirecek şekilde yapılamaz.
  > GETAT uygulayıcısı, uygulamanın mevcut tıbbi tedavinin bir alternatifi değil tamamlayıcısı olduğu
  > ve hastalığın devam eden tedavisinin yerine geçmeyeceği hususunu hastaya açık ve anlaşılır bir
  > dille sözlü olarak anlatmak ve yaptığı bilgilendirmeyi hasta bilgilendirme formu ile kayıt altına
  > almakla yükümlüdür."
  > Madde 11(7): "Uygulama öncesinde hasta bilgilendirme formu hazırlanır ve uygulama yapılacak tüm
  > hastalardan rıza alınır."
  > Madde 11(8): "Uygulama merkezi ve uygulama ünitelerinde yapılan uygulamalara bağlı olarak hastalarda
  > istenmeyen etkilerin ortaya çıkması durumunda Ek-5'te yer alan istenmeyen etki bildirim formu
  > elektronik ortamda doldurularak yirmi dört saat içinde Bakanlığa bildirilir."
  > Madde 19(1): "27/10/2014 tarihli ve 29158 sayılı Resmî Gazete'de yayımlanan Geleneksel ve
  > Tamamlayıcı Tıp Uygulamaları Yönetmeliği yürürlükten kaldırılmıştır."
- **Confidence: HIGH** for the article text (print of the official page). **Ek-2 (the list of permitted
  practices) was NOT retrieved** — see §4 gap 1.

### GT-S2 — SB SHGM GETAT Daire Başkanlığı, "Kupa Uygulaması Hakkında Bilgilendirme" (Türkiye)
- **guideline_id (proposed):** `SB-GETAT-KUPA-BILGI-2017` (information page)
- **Date:** 12 Haziran 2017 (pre-dates GT-S1)
- **URL:** https://shgmgetatdb.saglik.gov.tr/TR,24670/kupa-uygulamasi-hakkinda-bilgilendirme.html
- **Verbatim (list items where kupa is not applied, as rendered by the fetch):**
  > "Damar tıkanması" · "Derin kansızlık" · "Aktif yaralar" · "Yeni cerrahi yaralar" · "Kalp hastalığı"
  > · "Varislerin doğrudan üzerine uygulanması"
  > "Gebelerde dikkatlice kullanılmalı"
- **Confidence: MEDIUM** — official page, list items only, written under the repealed regulation.

### GT-S3 — SB SHGM GETAT Daire Başkanlığı, "Mezoterapi Uygulaması Hakkında Bilgilendirme" (Türkiye)
- **guideline_id (proposed):** `SB-GETAT-MEZOTERAPI-BILGI-2017` · **Date:** 12 Haziran 2017
- **URL:** https://shgmgetatdb.saglik.gov.tr/TR,24676/mezoterapi-uygulamasi-hakkinda-bilgilendirme.html
- **Verbatim (as rendered by the fetch):**
  > Side effects: "Taşikardi-Hipertansiyon, Anksiyete, Ciltte laserasyon, Allerji-lokal kızarıklık,
  > kaşıntı, Ağrı, Enfeksiyon gelişimi, Nekroz, Hematom"
  > Not applied in: "Akut enfeksiyonlar, Derin ven trombozu, İnstabil kan basıncı, Kalp krizi, Senkop
  > sonrası epizod, Açık yaralar, Son dönem kalp ytmezliği, Diabetes mellitus, Antikoagülan tedavi
  > altındaki hastalar, Böbrek yetmezliği, İlaçlara karşı aşırı duyarlılığı olan hastalarda, Hamilelikte"
- **Confidence: MEDIUM** — official page; "ytmezliği" is as rendered.

### GT-S4 — NCCIH, "Are You Considering a Complementary Health Approach?" (international)
- **guideline_id (proposed):** `NCCIH-CONSIDERING-CHA` · **Last updated:** September 2016 (as shown)
- **URL:** https://www.nccih.nih.gov/health/are-you-considering-a-complementary-health-approach
- **Verbatim:**
  > "Tell all your health care providers—complementary and conventional—about all the health approaches
  > you use."
  > "Do not use a product or practice that has not been proven to be effective to postpone seeing your
  > health care provider for your condition."
  > "Before using any dietary supplement or herbal product, make sure you find out about potential side
  > effects or interactions with medications you may be taking."
- **Confidence: MEDIUM–HIGH** (US federal patient page).

### GT-S5 — NCCIH, "4 Tips: Start Talking With Your Health Care Providers About Complementary Health Approaches" (international)
- **guideline_id (proposed):** `NCCIH-4-TIPS-TALKING` · **Last updated:** rendered by the fetch as
  26 September 2026 (the retrieval date — **treat as unverified**)
- **URL:** https://www.nccih.nih.gov/health/tips/tips-start-talking-with-your-health-care-providers-about-complementary-health-approaches
- **Verbatim:**
  > "When completing the patient history form, be sure to include everything you use—from acupuncture
  > to zinc."
  > "Some complementary health approaches can have an effect on conventional medicine, so your provider
  > needs to know."

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Leaf paths are **deferred** (`openehr_deferred_reason`, INT-032), never invented. The OPT has no
procedure root, so practice history is narrative.

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Reason for visit | `EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2 | Any complementary practice used | `OBSERVATION.story.v1` (narrative only) | deferred; no procedure root |
| Q3 | Which practices | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q4 | Still ongoing | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q5 | Done in a health facility | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q6 | Unexpected problem after a practice | `EVALUATION.adverse_reaction_risk.v1` | deferred (INT-032) |
| Q7 | Paused a physician-recommended treatment | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q8 | Treating physician aware | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q9 | Open or new surgical wound | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q10 | Past clot or vessel blockage | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q11 | Past severe anaemia | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q12 | Known heart disease | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Item | Source | base item | This proposal's role |
|---|---|---|---|
| Heavy bleeding after wet cupping or leech application | GT-S2 (bleeding context) | `rf.severe_bleeding` (named gap) | Not asked here; base owns it |
| Fainting or chest symptoms after an application | GT-S3 ("Senkop", "Kalp krizi" listed) | `rf.chest_pain_*` / base probes | Not asked here |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Adverse effect after a GETAT application (infection, necrosis, haematoma) | "istenmeyen etkilerin ortaya çıkması durumunda … yirmi dört saat içinde Bakanlığa bildirilir" · "Enfeksiyon gelişimi, Nekroz, Hematom" | GT-S1 Madde 11(8), GT-S3 |
| Conventional treatment paused or delayed for a practice | "Uygulamalar diğer tıbbi tedavileri aksatacak veya geciktirecek şekilde yapılamaz." | GT-S1 Madde 11(3) |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22); **no efficacy or
safety claim and no endorsement**. **All CANDIDATE — clinician to approve wording.** No item carries a
triage level. Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün geleneksel ve tamamlayıcı tıp polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Any complementary practice used** · archetype: `OBSERVATION.story.v1` · source: GT-S1 Madde 8(1) (practices limited to Ek-2), GT-S5 ("from acupuncture to zinc")
> "Daha önce akupunktur, kupa, sülük ya da ozon gibi bir uygulama yaptırdınız mı?"
gen: slot=onceki_getat_uygulamasi; type=boolean
CANDIDATE — clinician to approve wording. The four examples are neutral illustrations, not a list of
approved practices; the Ek-2 list must be checked (§4 gap 1). Herbal products are asked by base.

**Q3 — Which practices (if Q2 yes)** · archetype: `OBSERVATION.story.v1` · source: GT-S4 ("Tell all your health care providers")
> "Hangi uygulamaları yaptırdığınızı kısaca anlatır mısınız?"
gen: slot=getat_uygulama_turleri; type=string; ask_if=onceki_getat_uygulamasi == true
CANDIDATE — clinician to approve wording.

**Q4 — Still ongoing (if Q2 yes)** · archetype: `OBSERVATION.story.v1` · source: GT-S5 ("can have an effect on conventional medicine")
> "Bu uygulamalardan herhangi birine şu anda da devam ediyor musunuz?"
gen: slot=suren_getat_uygulamasi; type=boolean; ask_if=onceki_getat_uygulamasi == true
CANDIDATE — clinician to approve wording.

**Q5 — Done in a health facility (if Q2 yes)** · archetype: `OBSERVATION.story.v1` · source: GT-S1 Madde 9(1) ("Bakanlıkça yetkilendirilmiş uygulama merkezi veya uygulama ünitelerinde")
> "Bu uygulamalar bir hastanede ya da sağlık kuruluşunda mı yapıldı?"
gen: slot=saglik_kurulusunda_yapildi; type=boolean; ask_if=onceki_getat_uygulamasi == true
CANDIDATE — clinician to approve wording. Records setting only; the patient is not judged.

**Q6 — Unexpected problem afterwards (if Q2 yes)** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: GT-S1 Madde 11(8), GT-S3 (side-effect list)
> "Bir uygulamadan sonra beklemediğiniz bir yakınma ya da sorun yaşadınız mı?"
gen: slot=uygulama_sonrasi_sorun; type=boolean; ask_if=onceki_getat_uygulamasi == true
CANDIDATE — clinician to approve wording. See §2.3.

**Q7 — Paused a recommended treatment (if Q2 yes)** · archetype: `OBSERVATION.story.v1` · source: GT-S1 Madde 11(3) ("diğer tıbbi tedavileri aksatacak veya geciktirecek"), GT-S4 ("to postpone seeing your health care provider")
> "Bu uygulamalar nedeniyle hekiminizin önerdiği bir tedaviye ara verdiniz mi?"
gen: slot=tibbi_tedaviye_ara; type=boolean; ask_if=onceki_getat_uygulamasi == true
CANDIDATE — clinician to approve wording. Asked without blame; see §2.3.

**Q8 — Treating physician aware (if Q2 yes)** · archetype: `OBSERVATION.story.v1` · source: GT-S4 ("Tell all your health care providers"), GT-S5
> "Sizi takip eden hekiminiz bu uygulamaları yaptırdığınızı biliyor mu?"
gen: slot=hekim_haberdar; type=boolean; ask_if=onceki_getat_uygulamasi == true
CANDIDATE — clinician to approve wording.

**Q9 — Open or new surgical wound** · archetype: `OBSERVATION.symptom_sign.v1` · source: GT-S2 ("Aktif yaralar", "Yeni cerrahi yaralar"), GT-S3 ("Açık yaralar")
> "Cildinizde açık bir yara ya da yeni bir ameliyat yarası var mı?"
gen: slot=acik_yara; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Past clot or vessel blockage** · archetype: `EVALUATION.problem_diagnosis.v1` · source: GT-S2 ("Damar tıkanması"), GT-S3 ("Derin ven trombozu")
> "Size daha önce damar tıkanıklığı ya da bacakta pıhtı olduğu söylendi mi?"
gen: slot=damar_tikanikligi_oykusu; type=boolean
CANDIDATE — clinician to approve wording.

**Q11 — Past severe anaemia** · archetype: `EVALUATION.problem_diagnosis.v1` · source: GT-S2 ("Derin kansızlık")
> "Size daha önce ağır kansızlık olduğu söylendi mi?"
gen: slot=agir_kansizlik_oykusu; type=boolean
CANDIDATE — clinician to approve wording.

**Q12 — Known heart disease** · archetype: `EVALUATION.problem_diagnosis.v1` · source: GT-S2 ("Kalp hastalığı"), GT-S3 ("Kalp krizi", "Son dönem kalp ytmezliği")
> "Size daha önce bir kalp hastalığı olduğu söylendi mi?"
gen: slot=kalp_hastaligi_oykusu; type=boolean
CANDIDATE — clinician to approve wording.

*(12 candidate questions; all 12 generate.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Ek-2 of GT-S1 (the permitted practice list)** — not in the retrieved print; the mevzuat.gov.tr
   copy failed TLS verification and was not fetched. The practice names in Q2 come from the SB GETAT
   pages and common usage, **not** from a verbatim Ek-2. **Re-snapshot Ek-2 before sign-off.**
2. **2026 uygulama kılavuzları** (per-practice guides named in GT-S1 Madde 4(ı)) — not retrieved; GT-S2
   and GT-S3 are 2017 pages under the repealed regulation. **NO SOURCE FOUND (current).**
3. **Leech and wet-cupping specific history** (bleeding tendency, varicose veins, skin disease) — only
   partly sourced; varicose-vein and bleeding-tendency items not drafted. Blood thinners are in base.
4. **Diabetes, kidney failure, unstable blood pressure** (GT-S3 list) — sourced but not drafted, to stay
   at twelve; the clinician may swap them in.
5. **Herbal-drug interaction detail** — left to base `otc_herbal`; whether GETAT needs a fuller herbal
   inventory is a clinician decision (TİTCK licensing, GT-S1 Madde 14(2), noted only).
6. **EK-4 acuity** — no level proposed; RED axes (invariant 21) deliberately unassigned.
7. **openEHR leaf paths** — deferred (INT-032); no procedure root in the OPT (INT-041).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording, no endorsement or efficacy wording; each draft marked CANDIDATE.
- **Inv. 7** — bleeding and cardiac events left to `base.life_threat`; nothing extends it.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval.
- **Inv. 20** — no efficacy, safety-rate or accuracy claim about any practice.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals in any candidate question.
- **HB-C1** — awaits clinician sign-off; NOT served.
