# Hava ve Uzay Hekimliği (Aerospace Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Hava ve Uzay Hekimliği (Aerospace Medicine)
Taxonomy id: `hava_ve_uzay_hekimligi` (branches.yaml — cluster `medical`, all visit types).
Purpose: patient-owned, Turkish-first **pre-visit intake** (flight-related symptom and history
capture for a clinician-ready note) — **not** diagnosis, not triage authority, and **not** a
fitness-to-fly verdict. This file is a *proposal for a clinician to sign off*. It assigns **no**
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the primary source is the SHGM Havacılık Sağlık Talimatı (SHT-MED, revision 4),
  which is based on ICAO Annex 1 Chapter 6 and EU Part-MED. The Havacılık Tıbbı Derneği pages and the
  Sağlık Bakanlığı travel-health page supply the flight-related symptom content. ICAO Doc 8984 and
  the EASA acceptable means of compliance were **not retrieved** (§4).
- **The fitness decision is the examiner's, by regulation.** HU-S1 MED.A.025(b)(1) gives the AeMC /
  AME / Yetkili Tabip the duty to tell the applicant whether they are fit. The pack captures history
  only and never implies a verdict or a certificate class.
- **The pack is not the statutory declaration.** HU-S1 MED.A.035(b)(2) requires a signed medical
  history declaration, and MED.A.025(a)(3) makes an incomplete or false declaration reportable to the
  licensing authority. Pre-visit answers must not be presented, stored or exported as that
  declaration. **Legal-reviewer decision required** before this pack is served to licence holders.
- **Data-category line (invariant 18):** the applicant's certification history (earlier restriction
  or unfit decision, HU-S1 MED.A.035(b)(2)(iii)) is a licensing record, not health history. Q15 is
  therefore **held**. Q2 records only whether an earlier aviation medical took place, to gate the
  "since your last examination" items.
- **Not repeated from base:** occupation (pilot, cabin crew or air traffic controller is captured by
  base `occupation`), medications (HU-S1 MED.A.020(b)(2)), pregnancy (MED.A.020(b)(5)), hospital
  admission since the last visit (base `new_diagnoses_since_last_visit` follow-up), alcohol and
  smoking.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger.
- **Verification caveat (every quote in §1):** HU-S1 was downloaded and extracted locally with
  `pdftotext`; HU-S2 is a WebFetch rendering; HU-S3…HU-S6 were downloaded with `curl` and their HTML
  stripped locally (raw text, not model-rendered). Before sign-off each sentence MUST be re-checked
  against the primary text and committed as a verbatim snapshot with `source: {guideline_id, version,
  date, url, retrieved_on}`. Until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/hava_ve_uzay_hekimligi.yaml` or any
  served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### HU-S1 — SHGM, "Havacılık Sağlık Talimatı (SHT-MED)", Revizyon 4 (Türkiye)
- **guideline_id (proposed):** `SHGM-SHT-MED-REV4`
- **Publishing body:** T.C. Ulaştırma ve Altyapı Bakanlığı, Sivil Havacılık Genel Müdürlüğü (SHGM)
- **Version / date:** Revision 4; the PDF sits under `/talimatlar/2021/` and carries no printed date;
  HU-S2 dates the revision announcement 1 January 2022. Amendments cited inside: 11/09/2020 - 8243.
- **URL:** https://web.shgm.gov.tr/documents/sivilhavacilik/files/mevzuat/sektorel/talimatlar/2021/SHT-MED-Rev4.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim — basis (Madde 3):**
  > "(2) Şikago Konvansiyonu Ek-1 Bölüm 6 gereklilikleri esas alınmıştır."
- **Verbatim — MED.A.020 "Tıbbi uygunlukta azalma" (b):**
  > "Ayrıca, lisans ve sertifika sahipleri aşağıda belirtilen durumlarda vakit kaybetmeksizin bir
  > AeMC, AME, Yetkili tabip, GMP veya OHMP'ye başvurmalıdırlar:"
  > "1)Herhangi bir cerrahi operasyona ya da invaziv müdahaleye maruz kaldıkları takdirde,"
  > "3)Uçuş ekibi üyesi veya Hava Trafik Kontrolörü olarak görevlerini yapmayı engelleyici önemli
  > bir yaralanmaya veya sakatlanmaya maruz kaldıkları takdirde,"
  > "7)İlk kez düzeltici merceğe ihtiyaç duyduklarında."
- **Verbatim — MED.A.025 (examiner duties):**
  > "1)Kişiye sağlığının uçuşa veya göreve uygun olduğu ya da olmadığını bildirmeli"
  > "3)Başvuru sahibi tıbbi öyküsüyle ilgili eksik, kusurlu veya yanlış beyanda bulunursa, Lisans
  > veren otorite ve AMS'yi bilgilendirir"
- **Verbatim — MED.A.035 (application declaration, b)(2)):**
  > "ii)Daha önce sağlık sertifikası muayenesine tabi tutulup tutulmadıklarını"
  > "iii)Kısıtlamalı uçuşa elverişlilik durumu olup olmadığını, sağlık açısından uçuşa veya göreve
  > uygun olmadıklarının tespit edilmiş olup olmadığını"
- **Verbatim — MED.B.065 "Nöroloji":**
  > "2)Nedeni belli olmayan ve tekrar eden bilinç bozukluğu ve kaybı nöbetleri,"
  > "6)Migren,"
  > "7)Nedeni belli olmayan ve bir kere yaşanan bilinç bozukluğu ve kaybı nöbeti,"
- **Verbatim — MED.B.080 "Kulak-burun-boğaz" (d):**
  > "1)Hipoakuzi," · "4)Östaki Tüpü fonksiyon bozukluğu," · "5)Vestibül fonksiyon bozukluğu," ·
  > "7)Sinüs disfonksiyonu,"
- **Confidence: HIGH** for text (primary regulator PDF, extracted locally); MEDIUM for the revision
  date (taken from HU-S2, not printed in the PDF).

### HU-S2 — SHGM announcement, "Havacılık Sağlık Talimatı (SHT-MED) Revize Edilmiştir" (Türkiye)
- **URL:** https://web.shgm.gov.tr/tr/mevzuat/6741-havacilik-saglik-talimati-sht-med-revize-edilmistir
- **Date:** 1 January 2022 (as rendered) · **retrieved_on:** 2026-09-26 (WebFetch rendering)
- **Verbatim (as rendered):**
  > "01.01.2022 tarihi itibarı ile … sağlık muayene raporları ilk kez düzenlenmeleri de dahil olmak
  > üzere doğrudan havacılık tıp merkezleri tarafından düzenlenebilecektir."
- **Use:** date provenance for HU-S1 only. **Confidence: MEDIUM** (model-rendered; re-snapshot).

### HU-S3 — Havacılık Tıbbı Derneği, "Pilotların mesleki hastalıkları" (Türkiye)
- **guideline_id (proposed):** `HVTD-PILOT-MESLEK-HASTALIKLARI` (society article, NOT a guideline)
- **URL:** https://www.hvtd.org/?p=360 · **Date:** not shown · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "hafif bir nezle bile, irtifadaki basınç değişimleri nedeniyle dayanılmaz kulak ve sinüs
  > ağrılarına dönüşebilir"
  > "Özellikle sık sık kıtalararası uçuşlar yapan pilotların günlük biyolojik ritimleri de bozulur;"
  > "kümülatif/kronik yorgunluğa ve tükenmişliğe neden olabilir."
  > "uzun süreli oturma, vibrasyon ve gerginliğe bağlı olan omurga ağrıları rapor edilmektedir."
  > "vestibüler ve görsel illüzyonlar sivil havacılıkta da bazı kazaların nedeni olmaktadır."
  > "(örn. tansiyon düşmesine bağlı basit senkop), uçuşta pilotun başına geldiğinde çok tehlikeli
  > hale dönüşebilir"
- **Confidence: MEDIUM** — Turkish specialty society, undated article.

### HU-S4 — Havacılık Tıbbı Derneği, "Havayoluyla hasta taşınması ilkeleri" (Türkiye)
- **URL:** https://www.hvtd.org/?p=994 · **Date:** not shown · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Orta kulak, sinüs ve dişlerde hapsedilmiş gazların genişlemeleri ise, şiddetli ağrıdan kulak
  > zarı yırtılmalarına kadar bir dizi problem yaratabilir."
  > "Uçak tutması olgularının sağ ve orta bölmelere yerleştirilmeleri"
- **Confidence: MEDIUM** — society article, undated.

### HU-S5 — Havacılık Tıbbı Derneği, "Havacılıkta gürültü ve vibrasyon" (Türkiye)
- **URL:** https://www.hvtd.org/?p=525 · **Date:** not shown · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "yıllarca süren kronik gürültü ise işitme kayıplarıyla sonuçlanır."
  > "kulak ağrısı, kulak zarı yırtılması, çınlama, iç kulak sinirsel tip kalıcı işitme kaybı yapar."
- **Confidence: MEDIUM** — society article, undated.

### HU-S6 — T.C. Sağlık Bakanlığı Seyahat Sağlığı, "Hava Yolculuğu için Sağlık Önerileri" (Türkiye)
- **guideline_id (proposed):** `SB-SEYAHAT-SAGLIGI-HAVA-YOLCULUGU` (public health page, NOT a guideline)
- **URL:** https://www.seyahatsagligi.gov.tr/SeyahatOnerileri/havayolculugu · **Date:** not shown ·
  **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Uçak alçalırken havanın orta kulak ve sinüslere girmesi sağlanmalıdır, böylece basınç
  > farklılıkları da eşitlenmiş olur."
  > "Kulak, burun ve sinüs enfeksiyonları olan hastalar hava yolculuğu yapmaktan kaçınmalıdırlar"
  > "uyku kalıplarının ve vücudun iç saatini oluşturan biyolojik ritmin bozulması anlamına gelir."
  > "nadiren araç tutmasından şikayet ederler."
- **Confidence: MEDIUM** — Ministry page for passengers; applies to crew by extension only.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Earlier aviation medical (yes/no) | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q3 | Ear / sinus pain in flight | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Cold / blocked nose / sinus complaint now | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Reduced hearing / ringing ears | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Nausea / dizziness / disorientation in flight | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Sleep disrupted by shifts / time zones | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Fatigue not relieved by rest | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Back pain from long sitting | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Surgery or procedure since last exam | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; **no procedure archetype in the OPT** |
| Q11 | Significant injury since last exam | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q12 | First glasses or lenses since last exam | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q13 | Fainting / loss of consciousness ever | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q14 | Recurrent throbbing headaches | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q15 | HELD — earlier restriction or unfit decision | — | — | — |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm sign | Source | base item | This proposal's role |
|---|---|---|---|
| Chest pain, stroke signs or sudden incapacitation now | HU-S3 (in-flight incapacitation list) | `rf.chest_pain_*`, `rf.stroke_fast` | **Not asked.** |
| Exertional collapse / syncope | — | base / physician | **Not asked.** Q13 is a lifetime-history gate input only |
| Decompression illness after a rapid cabin-pressure loss | HU-S3 (sudden pressure loss section) | **absent** from base.life_threat | **Not asked.** Left to the base owner / physician |
| Ear drum rupture with severe pain | HU-S4, HU-S5 | not a base rule | Q3 is history only |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Any MED.A.020(b) event since the last examination (Q10–Q12) | "vakit kaybetmeksizin bir AeMC, AME, Yetkili tabip, GMP veya OHMP'ye başvurmalıdırlar" | HU-S1 |
| Unexplained or recurrent loss of consciousness (Q13) | "Nedeni belli olmayan ve tekrar eden bilinç bozukluğu ve kaybı nöbetleri," | HU-S1 MED.B.065 |
| Ear or sinus pain in flight with a current cold (Q3 + Q4) | "hafif bir nezle bile … dayanılmaz kulak ve sinüs ağrılarına dönüşebilir" | HU-S3, HU-S6 |
| Migraine (Q14) | "6)Migren," | HU-S1 MED.B.065(c) |

---

## 3. Candidate B1 Turkish pre-visit questions (15 drafted: 14 active, 1 held)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE —
clinician to approve wording.** No item carries a triage level. Q1 binds to the pack's
`basvuru_nedeni` slot; duration comes from the pack's `sikayet_suresi` slot. Q10–Q12 are gated on
Q2 so a first-time applicant is not asked about a "last examination" they never had.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün hava ve uzay hekimliği polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Earlier aviation medical** · archetype: `OBSERVATION.story.v1` · source: HU-S1 MED.A.035(b)(2)(ii)
> "Daha önce bir havacılık sağlık muayenesi oldunuz mu?"
gen: slot=onceki_havacilik_muayenesi; type=boolean
CANDIDATE — clinician to approve wording. Fact of an earlier examination only; the result is Q15 (held).

**Q3 — Ear or sinus pain in flight** · archetype: `OBSERVATION.symptom_sign.v1` · source: HU-S4 ("Orta kulak, sinüs … şiddetli ağrıdan"), HU-S6 ("Uçak alçalırken"), HU-S1 MED.B.080(d)
> "Uçuş sırasında, özellikle inişte, kulaklarınızda ya da sinüslerinizde ağrı oluyor mu?"
gen: slot=ucusta_kulak_sinus_agrisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Cold, blocked nose or sinus complaint now** · archetype: `OBSERVATION.symptom_sign.v1` · source: HU-S3 ("hafif bir nezle bile"), HU-S6 ("Kulak, burun ve sinüs enfeksiyonları")
> "Şu anda nezle, burun tıkanıklığı ya da sinüs şikâyetiniz var mı?"
gen: slot=guncel_ust_solunum_sikayeti; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Reduced hearing or ringing ears** · archetype: `OBSERVATION.symptom_sign.v1` · source: HU-S5 ("çınlama", "işitme kayıplarıyla"), HU-S1 MED.B.080(d)(1) ("Hipoakuzi")
> "İşitmenizde azalma ya da kulaklarınızda çınlama fark ettiniz mi?"
gen: slot=isitme_azalma_cinlama; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Nausea, dizziness or disorientation in flight** · archetype: `OBSERVATION.symptom_sign.v1` · source: HU-S3 ("vestibüler ve görsel illüzyonlar"), HU-S4 ("Uçak tutması"), HU-S6 ("araç tutması"), HU-S1 MED.B.080(d)(5)
> "Uçuş sırasında bulantı, baş dönmesi ya da yönünüzü şaşırma hissi yaşıyor musunuz?"
gen: slot=ucusta_bulanti_bas_donmesi; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Sleep disrupted by shifts or time zones** · archetype: `OBSERVATION.symptom_sign.v1` · source: HU-S3 ("günlük biyolojik ritimleri de bozulur"), HU-S6 ("biyolojik ritmin bozulması")
> "Vardiyalı çalışma ya da saat farkı yüzünden uyku düzeniniz bozuluyor mu?"
gen: slot=uyku_duzeni_bozulmasi; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — Fatigue not relieved by rest** · archetype: `OBSERVATION.symptom_sign.v1` · source: HU-S3 ("kümülatif/kronik yorgunluğa")
> "Dinlenmekle geçmeyen bir yorgunluk hissediyor musunuz?"
gen: slot=gecmeyen_yorgunluk; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Back pain from long sitting** · archetype: `OBSERVATION.symptom_sign.v1` · source: HU-S3 ("uzun süreli oturma … omurga ağrıları")
> "Uzun süre oturmaya bağlı sırt ya da bel ağrınız var mı?"
gen: slot=oturmaya_bagli_sirt_bel_agrisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Surgery or procedure since the last examination (if Q2 yes)** · archetype: `OBSERVATION.story.v1` · source: HU-S1 MED.A.020(b)(1)
> "Son havacılık muayenenizden bu yana ameliyat ya da benzeri bir tıbbi işlem geçirdiniz mi?"
gen: slot=son_muayeneden_beri_ameliyat; type=boolean; ask_if=onceki_havacilik_muayenesi == true
CANDIDATE — clinician to approve wording. "Benzeri bir tıbbi işlem" stands in for "invaziv müdahale".

**Q11 — Significant injury since the last examination (if Q2 yes)** · archetype: `OBSERVATION.story.v1` · source: HU-S1 MED.A.020(b)(3)
> "Son muayenenizden bu yana görevinizi yapmanızı zorlaştıran bir yaralanma geçirdiniz mi?"
gen: slot=son_muayeneden_beri_yaralanma; type=boolean; ask_if=onceki_havacilik_muayenesi == true
CANDIDATE — clinician to approve wording.

**Q12 — First glasses or contact lenses since the last examination (if Q2 yes)** · archetype: `OBSERVATION.story.v1` · source: HU-S1 MED.A.020(b)(7)
> "Son muayenenizden bu yana ilk kez gözlük ya da lens kullanmaya başladınız mı?"
gen: slot=ilk_kez_gozluk_lens; type=boolean; ask_if=onceki_havacilik_muayenesi == true
CANDIDATE — clinician to approve wording.

**Q13 — Fainting or loss of consciousness, ever (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: HU-S1 MED.B.065(b)(2), (c)(7); HU-S3 ("basit senkop")
> "Daha önce hiç bayıldığınız ya da kısa süreli bilinç kaybı yaşadığınız oldu mu?"
gen: slot=bayilma_bilinc_kaybi_oykusu; type=boolean
CANDIDATE — clinician to approve wording. Lifetime history; **exertional collapse stays with base / physician (§2.2)**.

**Q14 — Recurrent throbbing headaches** · archetype: `OBSERVATION.symptom_sign.v1` · source: HU-S1 MED.B.065(c)(6) ("Migren")
> "Tekrarlayan, zonklayan tarzda baş ağrılarınız oluyor mu?"
gen: slot=tekrarlayan_zonklayan_bas_agrisi; type=boolean
CANDIDATE — clinician to approve wording. The word "migren" is not put to the patient, so no label is suggested.

**Q15 — Earlier restriction or unfit decision** · archetype: none · source: HU-S1 MED.A.035(b)(2)(iii)
> "Önceki bir havacılık muayenesinde size kısıtlama ya da engel kararı verildi mi?"
gen: slot=onceki_kisitlama_karari; type=boolean; ask_if=onceki_havacilik_muayenesi == true; hold=invariant 18 — certification history is a licensing record and a new data category; owner and legal decision required
CANDIDATE — HELD. The answer overlaps the statutory declaration (§0).

*(15 drafted: 14 active, 1 held.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **ICAO Doc 8984, Manual of Civil Aviation Medicine (3rd ed., 2012)** — sold by the ICAO store; not
   retrieved and not quoted. **NO SOURCE FOUND (verbatim).**
2. **EASA Part-MED acceptable means of compliance / guidance material and the EASA application form
   history items** — not retrieved. HU-S1 is the Turkish transposition and is used instead.
3. **Havacılık Tıbbı Derneği versioned guideline** — only undated society articles (HU-S3…HU-S5) were
   found. **NO SOURCE FOUND (versioned) — clinician must supply.**
4. **Statutory declaration boundary** — whether any pre-visit answer may be shown to the AeMC / AME
   next to the MED.A.035 declaration, and how an inconsistency is handled (MED.A.025(a)(3)).
   **Legal-reviewer decision required.**
5. **Certification history (Q15)** — held under invariant 18; owner decision and HB row required.
6. **Hypoxia, cabin decompression and cosmic-radiation exposure history** — mentioned in HU-S3; not
   drafted (no patient-answerable wording sourced).
7. **Psychiatric and substance items** (HU-S1 psychiatry and psychology sections) — not drafted;
   sensitive categories need text-first delivery and an owner decision.
8. **Cardiovascular, vision and colour-vision history** (HU-S1 MED.B sections) — not drafted to stay
   near twelve active items; clinician may swap them in.
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. All three
   RED axes (route × register × location, invariant 21) are **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** and a **procedure / device-use archetype** — deferred
    (`openehr_deferred_reason`, INT-032).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE.
- **Inv. 7** — in-flight incapacitation, exertional collapse and decompression illness left to
  `base.life_threat` and the physician (§2.2); nothing extends it.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 18** — Q15 held (certification history); statutory-declaration boundary flagged (§0, gap 4).
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question; regulation item numbers stay in §1 only.
- **Fitness-to-fly** — history capture only; the decision is the examiner's by regulation (HU-S1
  MED.A.025).
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources HU-S1…HU-S6 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
