# Sualtı ve Hiperbarik Tıp (Undersea and Hyperbaric Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Sualtı Hekimliği ve Hiperbarik Tıp
Taxonomy id: `sualti_ve_hiperbarik_tip` (branches.yaml — cluster `medical`, all visit types).
Purpose: patient-owned, Turkish-first **pre-visit intake** (diving history, pressure-related symptoms
and pre-chamber history for a clinician-ready note) — **not** diagnosis, not triage authority, **not**
a fitness-to-dive verdict and **not** a decision that hyperbaric oxygen is indicated. This file is a
*proposal for a clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and pins **no**
clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Two patient groups share this clinic:** (a) divers and diver candidates (dalışa uygunluk
  muayenesi, follow-up after a diving injury) and (b) patients referred for hyperbaric oxygen
  treatment (HBOT, "basınç odası tedavisi"). Q2–Q5 are the diving block (Q3–Q5 gated on Q2); Q6–Q10
  apply to both groups; Q11–Q13 capture history relevant to common HBOT referrals.
- **Turkish first:** the Sualtı ve Hiperbarik Tıp Derneği position statement (SH-S1), the Profesyonel
  Sualtıadamları Yönetmeliği (SH-S2), the ÇSGB İSGGM occupational-disease guide's pressure chapter
  (SH-S3) and a Sağlık Bakanlığı hospital HBOT page (SH-S4). International corroboration: the
  ECHM/COST B14 code of practice (SH-S5), the UHMS/WRSTC diver questionnaire (SH-S6, cited for
  domains only, not reproduced) and the UHMS indications manual (SH-S7, chapter titles only).
- **Fitness-to-dive is a physician report.** SH-S1 and SH-S2 place the dalışa uygunluk raporu with
  the Sualtı Hekimliği ve Hiperbarik Tıp specialist. The pack captures history only and never implies
  that a person may or may not dive, or may or may not enter the chamber.
- **Acute emergencies are not asked here (invariant 7, §2.2):** decompression illness or arterial gas
  embolism happening now, carbon-monoxide poisoning, sudden vision loss and an untreated collapsed
  lung. Q3, Q8 and Q9 ask about the **past** only.
- **No validated instrument is reproduced.** The UHMS/WRSTC Diver Medical Participant Questionnaire is
  copyrighted and scored by its own rules; no item is translated. Our questions are own words and
  carry no referral logic.
- **Not repeated from base:** medications, allergies, smoking, alcohol, pregnancy (SH-S6 itself
  advises against diving in pregnancy; base `pregnancy_status` covers it) and occupation (a
  professional diver is captured by base `occupation`).
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger.
- **Verification caveat (every quote in §1):** SH-S1, SH-S2, SH-S3, SH-S5, SH-S6 and SH-S7 were
  downloaded and extracted locally with `pdftotext`; SH-S4, SH-S8 and SH-S9 were downloaded with
  `curl` and their HTML stripped locally (raw text). Source typos are kept as printed. Before sign-off
  each sentence MUST be re-checked against the primary text and committed as a verbatim snapshot with
  `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule stays
  `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/sualti_ve_hiperbarik_tip.yaml` or any
  served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### SH-S1 — Sualtı ve Hiperbarik Tıp Derneği, "Dalışa Uygunluk Muayeneleri ile İlgili Görüş Bildirisi" (Türkiye)
- **guideline_id (proposed):** `SHTD-DALISA-UYGUNLUK-GORUS-2025-12` (society position statement)
- **Publishing body:** Sualtı ve Hiperbarik Tıp Derneği Yönetim Kurulu · **Date:** PDF created
  5 December 2025 (upload folder 2025/12)
- **URL:** https://sualti.org/wp-content/uploads/2025/12/Dalisa_Uygunluk_Raporu_Hk.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Sualtı Hekimliği ve Hiperbarik Tıp uzmanları, ilgili mevzuata uygun olarak tek hekim imzası ile
  > dalışa uygunluk raporu düzenlemeye yetkilidir, heyet raporu gerekli değildir."
  > "Dalışa uygunluk muayenelerinde hak edilmemiş dekompresyon hastalığı öyküsü veya sağ-sol şantı
  > düşündürecek başka bir neden yok ise ekokardiyografi (EKO) tetkiki gerekli değildir."
- **Confidence: HIGH** for text (primary PDF, one page). A position statement, not a clinical
  guideline; it names the history item behind Q3.

### SH-S2 — Profesyonel Sualtıadamları Yönetmeliği, Madde 12–16 "Sağlık Kuralları" (Türkiye)
- **guideline_id (proposed):** `TR-YON-PROFESYONEL-SUALTIADAMLARI` (regulation)
- **Version / date:** consolidated text with amendments RG 15/2/2008-26788 and RG 4/6/2020-31145
- **Canonical URL:** https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=5689&MevzuatTur=7&MevzuatTertip=5
- **Copy retrieved:** https://iskenderunliman.uab.gov.tr/uploads/pages/gemi-insanlari-servisi/profesyonel-sualtiadamlari-yonetmeligi.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim — Madde 14 (1) Solunum Sistemi:**
  > "hava hapsine yol açacak bir lezyon (kist, kavern, kavite v.b.) bulunmamalıdır."
- **Verbatim — Madde 14 (3) Sinir Sistemi:**
  > "çocuk çağı febril konvülsiyonları hariç her türlü nöbet epizodları"
  > "açıklanamayan geçici bilinç kayıplar"
  > "dalışa bağlı kalıcı MSS sekelleri"
- **Verbatim — Madde 15 Kulak-Burun-Boğaz Sistemi (typos as printed):**
  > "Ora kulak basınç eşitlesini engelleyen patolojiler ile orta kulak cerrahi operasyonu geçirmiş
  > (stapedektomi, protez vb.) olanlar"
- **Confidence: HIGH** for text (regulation; port-authority copy — re-snapshot from mevzuat.gov.tr).
  Applies to professional divers; used here only as history-domain evidence.

### SH-S3 — ÇSGB İSGGM, "Meslek Hastalıkları ve İş ile İlgili Hastalıklar Tanı Rehberi", Basınçlı hava chapter (Türkiye)
- **guideline_id (proposed):** `CSGB-ISGGM-MESLEK-HASTALIKLARI-TANI-REHBERI-2012` (same document as
  `is_ve_meslek_hastaliklari.md` IM-S1) · PDF created 1 February 2012 · pp. 147–152
- **URL:** https://guvenlitarim.csgb.gov.tr/media/4l0jo25f/meslek-hastal%C4%B1klar%C4%B1-ve-i%C5%9F-ile-ilgili-hastal%C4%B1klar-rehberi.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim — barotrauma:**
  > "Orta kulaklar: Öncelikle etkilenirler." · "Kulaklarda ağrıyla başlar."
  > "Sinüsler: Ostiumların blokajı ağrı ve burun kanamasına neden olabilir."
- **Verbatim — decompression sickness (§2.2 context only):**
  > "Odyovestibüler: Başdönmesi, kulak çınlaması, nistagmus, işitme kaybı görülebilir."
  > "Dekompresyon hastalığı maruziyetten sonraki 10 dakika ile 2 hafta arasında ortaya çıkabilir."
- **Verbatim — flying after diving:**
  > "Ancak dalıştan hemen sonra uçuş, risklidir."
- **Confidence: MEDIUM–HIGH** (government guide, extracted locally; occupational scope).

### SH-S4 — Adana Şehir Eğitim ve Araştırma Hastanesi (T.C. Sağlık Bakanlığı), "Hiperbarik Oksijen Tedavisi" (Türkiye)
- **guideline_id (proposed):** `SB-ADANA-SEHIR-HBOT-2022` (hospital patient page, NOT a guideline)
- **Date:** 06 Aralık 2022 · **URL:** https://adanasehir.saglik.gov.tr/TR-877178/hiperbarik-oksijen-tedavisi.html
- **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Hastalar koltuklara yerleştikten sonra basınç odasının kapıları kapatılır ve tedavi başlatılır."
  > "Hastalara artan basınç esnasında kulaklarındaki basıncı nasıl eşitleyecekleri anlatılır."
  > "En sık görülen yan etki basınç değişikliğinin kulak ve sinüslerde yaptığı etkidir."
- **Verbatim — indication list items (as printed):**
  > "-Yara iyileşmesinin geciktiği durumlar (Şeker hastalığı ya da diğer durumlar)"
  > "-Ani işitme kaybı" · "-Radyasyon tedavisi geç dönem hasarları"
  > "-Vurgun hastalığı (Dekompresyon)" · "-Karbonmonoksit zehirlenmesi, akut duman solunumu" ·
  > "-Ani görme kaybı(damar tıkanıklığına bağlı)"
- **Confidence: MEDIUM** — Ministry hospital page for patients.

### SH-S5 — ECHM / COST Action B14, "A European Code of Good Practice for Hyperbaric Oxygen Therapy" (international)
- **guideline_id (proposed):** `ECHM-ECGP-HBO-2004-05`
- **Publishing body:** Working Group "Safety", COST Action B14 · **Version:** May 2004
- **URL:** http://www.echm.org/documents/ECGP%20for%20HBO%20-%20May%202004.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim — risk table "Insufficient warning of side effects" (cells as extracted):**
  > "Missing selection of high risk patients" · "Claustrophobia," · "Barotrauma)"
- **Verbatim — Annex 6, Patient Management 1.5:**
  > "Pre-treatment clinical assessment for other medical conditions which might be affected by
  > hyperbaric treatment including possible relative and absolute contraindications for hyperbaric
  > therapy."
- **Verbatim — Annex 4, emergency procedures:** > "3.1.3. convulsions"
- **Confidence: MEDIUM** — 2004 code of practice; it names the screening domains but lists no
  contraindication items. See gap 2.

### SH-S6 — UHMS / WRSTC, "Diver Medical | Participant Questionnaire" (international) — domains only
- **guideline_id (proposed):** `UHMS-WRSTC-DMPQ-2026-01-01` (screening form, © 2026; NOT reproduced)
- **Version:** 2026-01-01 · **URL:** https://uhms.org/images/Recreational-Diving-Medical-Screening-System/forms/Diver_Medical_Participant_Questionnaire_10346_EN_English_2026-01-01.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (one sentence):**
  > "Recreational scuba diving and freediving requires good physical and mental health."
- **Use:** confirms the domains our own-words items touch (lungs and chest surgery, ears and
  sinuses, loss of consciousness and seizures). No item wording, order or referral rule is used.

### SH-S7 — UHMS, "Hyperbaric Oxygen Therapy Indications", 14th edition (international) — chapter titles only
- **guideline_id (proposed):** `UHMS-HBO2-INDICATIONS-14ED-2019` · © 2019, R. E. Moon (ed.)
- **URL (copy retrieved from the society site):** https://uhms.org/images/UHMS-Reference-Material.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (table of contents):**
  > "B. Hyperbaric Oxygen Therapy for Selected Problem Wounds" · "7. Decompression Sickness" ·
  > "8. Delayed Radiation Injuries (Soft Tissue and Bony Necrosis)" · "9. Sudden Sensorineural
  > Hearing Loss"
- **Use:** corroborates SH-S4's indication list for Q11–Q13. The retrieved file appears to be an
  excerpt; the full manual was not read.

### SH-S8 — T.C. Sağlık Bakanlığı Seyahat Sağlığı, "Hava Yolculuğu için Sağlık Önerileri" (Türkiye)
- **URL:** https://www.seyahatsagligi.gov.tr/SeyahatOnerileri/havayolculugu · **Date:** not shown ·
  **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Skuba dalıcıları dalış yaptıktan sonra kısa süre içinde hava yolculuğuna çıkmamalıdırlar"

### SH-S9 — Havacılık Tıbbı Derneği, "Havayoluyla hasta taşınması ilkeleri" (Türkiye)
- **URL:** https://www.hvtd.org/?p=994 · **Date:** not shown · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "uçuş veya kapalı yer korkusu olan, panik ataklar gösteren hastaların"
  > "Dalgıçlardan son 24 saat içinde dalış yapanlar uçmamalıdırlar."
- **Note:** SH-S3, SH-S8 and SH-S9 give different waiting times; none is put into patient copy.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Has ever dived (scuba or breath-hold) | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q3 | Past diving illness ("vurgun") | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q4 | Ear pain / hearing change / ringing with diving | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Flying on the dive day or the next day | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q6 | Difficulty equalising ear pressure | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Cold / blocked nose / sinus complaint now | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Past collapsed lung or chest surgery | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q9 | Past seizure or unexplained fainting | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q10 | Distress in closed, narrow spaces | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Slow-healing or non-healing wound | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Recent sudden drop in hearing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q13 | Past radiotherapy | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; **no procedure archetype in the OPT** |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm sign | Source | base item | This proposal's role |
|---|---|---|---|
| Decompression illness or arterial gas embolism now (after a dive) | SH-S3, SH-S4, SH-S7 ch. 7 | **absent** from base.life_threat | **Not asked.** Q3 asks about the past only; base owner / physician |
| Carbon-monoxide poisoning / smoke inhalation | SH-S4 | **absent** from base.life_threat | **Not asked.** |
| Sudden vision loss (arterial occlusion) | SH-S4 ("Ani görme kaybı(damar tıkanıklığına bağlı)") | `rf.stroke_fast` (named gap) | **Not asked.** |
| Collapsed lung now | SH-S2 (air-trapping lesion), SH-S5 (absolute contraindications) | `rf.dyspnoea_rest` / physician | **Not asked.** Q8 is past history only |
| Seizure now | SH-S5 ("convulsions") | base / physician | **Not asked.** Q9 is past history only |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Past diving illness without an explaining dive profile (Q3) | "hak edilmemiş dekompresyon hastalığı öyküsü" | SH-S1 |
| Past collapsed lung, chest surgery or air-trapping lung lesion (Q8) | "hava hapsine yol açacak bir lezyon (kist, kavern, kavite v.b.) bulunmamalıdır." | SH-S2 |
| Past seizure or unexplained loss of consciousness (Q9) | "açıklanamayan geçici bilinç kayıplar" | SH-S2 |
| Difficulty equalising ear pressure (Q6) | "Ora kulak basınç eşitlesini engelleyen patolojiler" | SH-S2 |
| Recent sudden hearing loss (Q12) — time-sensitive referral content | "-Ani işitme kaybı" | SH-S4, SH-S7 ch. 9 |

---

## 3. Candidate B1 Turkish pre-visit questions (13)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE —
clinician to approve wording.** Lay terms are used: "vurgun" for decompression sickness, "akciğer
sönmesi" for pneumothorax, "basınç odası" for the chamber, "ışın tedavisi" for radiotherapy. No item
carries a triage level. Q1 binds to the pack's `basvuru_nedeni` slot; duration comes from the pack's
`sikayet_suresi` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün sualtı ve hiperbarik tıp polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording. The clinic's own name is kept so the patient recognises it.

**Q2 — Has ever dived** · archetype: `OBSERVATION.story.v1` · source: SH-S1 (dalışa uygunluk), SH-S6 ("scuba diving and freediving")
> "Daha önce hiç tüplü dalış ya da serbest dalış yaptınız mı?"
gen: slot=dalis_deneyimi; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q3–Q5.

**Q3 — Past diving illness (if Q2 yes)** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SH-S1 ("hak edilmemiş dekompresyon hastalığı öyküsü"), SH-S2 ("dalışa bağlı kalıcı MSS sekelleri")
> "Dalıştan sonra daha önce vurgun ya da benzeri bir rahatsızlık geçirdiniz mi?"
gen: slot=vurgun_oykusu; type=boolean; ask_if=dalis_deneyimi == true
CANDIDATE — clinician to approve wording. Past event only; illness now is §2.2.

**Q4 — Ear pain, hearing change or ringing with diving (if Q2 yes)** · archetype: `OBSERVATION.symptom_sign.v1` · source: SH-S3 ("Kulaklarda ağrıyla başlar."; "kulak çınlaması … işitme kaybı")
> "Dalış sırasında ya da sonrasında kulağınızda ağrı, işitme azalması veya çınlama oldu mu?"
gen: slot=dalista_kulak_sorunu; type=boolean; ask_if=dalis_deneyimi == true
CANDIDATE — clinician to approve wording.

**Q5 — Flying soon after diving (if Q2 yes)** · archetype: `OBSERVATION.story.v1` · source: SH-S3 ("dalıştan hemen sonra uçuş, risklidir"), SH-S8, SH-S9
> "Dalış yaptığınız gün ya da ertesi gün uçağa bindiğiniz oluyor mu?"
gen: slot=dalis_sonrasi_ucus; type=boolean; ask_if=dalis_deneyimi == true
CANDIDATE — clinician to approve wording. No waiting time is stated to the patient; sources differ (§1 note).

**Q6 — Difficulty equalising ear pressure** · archetype: `OBSERVATION.symptom_sign.v1` · source: SH-S2 Madde 15, SH-S4 ("kulaklarındaki basıncı nasıl eşitleyecekleri")
> "Kulaklarınızdaki basıncı eşitlemekte, örneğin uçak inerken, zorlandığınız olur mu?"
gen: slot=basinc_esitleme_zorlugu; type=boolean
CANDIDATE — clinician to approve wording. The example makes the question answerable for people who have never dived.

**Q7 — Cold, blocked nose or sinus complaint now** · archetype: `OBSERVATION.symptom_sign.v1` · source: SH-S3 ("Sinüsler: Ostiumların blokajı ağrı"), SH-S4 ("kulak ve sinüslerde")
> "Şu anda nezle, burun tıkanıklığı ya da sinüs şikâyetiniz var mı?"
gen: slot=guncel_ust_solunum_sikayeti; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — Past collapsed lung or chest surgery** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SH-S2 Madde 14 (1), SH-S5 (Annex 6 1.5)
> "Daha önce akciğer sönmesi ya da göğüs ameliyatı geçirdiniz mi?"
gen: slot=akciger_sonmesi_gogus_ameliyati; type=boolean
CANDIDATE — clinician to approve wording. Past history only (§2.2).

**Q9 — Past seizure or unexplained fainting** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SH-S2 Madde 14 (3), SH-S5 ("convulsions")
> "Daha önce hiç epilepsi (sara) nöbeti ya da nedeni bilinmeyen bayılma geçirdiniz mi?"
gen: slot=nobet_bayilma_oykusu; type=boolean
CANDIDATE — clinician to approve wording. "Epilepsi (sara)" avoids the shift-duty sense of "nöbet".

**Q10 — Distress in closed, narrow spaces** · archetype: `OBSERVATION.symptom_sign.v1` · source: SH-S5 ("Claustrophobia"), SH-S4 ("basınç odasının kapıları kapatılır"), SH-S9 ("kapalı yer korkusu")
> "Kapalı ve dar yerlerde bulunmak sizi çok huzursuz eder mi?"
gen: slot=kapali_alan_huzursuzlugu; type=boolean
CANDIDATE — clinician to approve wording. Not a phobia label; no scale.

**Q11 — Slow-healing or non-healing wound** · archetype: `OBSERVATION.symptom_sign.v1` · source: SH-S4 ("Yara iyileşmesinin geciktiği durumlar"), SH-S7 ("Selected Problem Wounds")
> "İyileşmesi uzun süren ya da kapanmayan bir yaranız var mı?"
gen: slot=iyilesmeyen_yara; type=boolean
CANDIDATE — clinician to approve wording.

**Q12 — Recent sudden drop in hearing** · archetype: `OBSERVATION.symptom_sign.v1` · source: SH-S4 ("-Ani işitme kaybı"), SH-S7 ch. 9
> "Son zamanlarda işitmenizde ani bir azalma oldu mu?"
gen: slot=ani_isitme_azalmasi; type=boolean
CANDIDATE — clinician to approve wording. Time-sensitive content for the physician (§2.3); no level here.

**Q13 — Past radiotherapy** · archetype: `OBSERVATION.story.v1` · source: SH-S4 ("Radyasyon tedavisi geç dönem hasarları"), SH-S7 ch. 8
> "Daha önce ışın tedavisi, yani radyoterapi, aldınız mı?"
gen: slot=radyoterapi_oykusu; type=boolean
CANDIDATE — clinician to approve wording. Body site is left to the clinician's follow-up.

*(13 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish clinical guideline** for fitness-to-dive history or HBOT pre-treatment
   screening — SH-S1 is a one-page statement and SH-S4 a hospital page. The TSSF Donanımlı Dalış
   Talimatı health rules (named in SH-S1) were not retrieved. **NO SOURCE FOUND (versioned) —
   clinician must supply.**
2. **HBOT contraindication list** (untreated pneumothorax as absolute; relative contraindications) —
   the StatPearls "Hyperbaric Patient Selection" page returned a CAPTCHA (not bypassed) and the full
   UHMS / ECHM texts were not read. SH-S5 names the assessment but lists no items. **NO SOURCE FOUND
   (verbatim) for a contraindication list.**
3. **SGK / SUT reimbursable HBOT indications and the Ministry HBOT facility regulation** — not
   retrieved. **NO SOURCE FOUND.**
4. **Waiting time before flying after diving** — SH-S3, SH-S8 and SH-S9 disagree; not put into
   patient copy (invariant 22). Clinician to choose one source if a rule needs it.
5. **Dive experience, depth and profile of a past illness** — not drafted (numeric answers; no free
   numeric entry on the clinical path, invariant 22). Clinician follow-up.
6. **Middle-ear surgery, eardrum perforation, heart and lung disease, diabetes** (SH-S2, SH-S6
   domains) — not drafted to stay near twelve items; clinician may swap them in.
7. **Chemotherapy agents relevant to HBOT** — base medications capture them; no specialty item.
8. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. All three
   RED axes (route × register × location, invariant 21) are **deliberately unassigned**.
9. **openEHR leaf paths (at-codes)** and a **procedure archetype** (radiotherapy) — deferred
   (`openehr_deferred_reason`, INT-032).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; lay terms for vurgun, akciğer sönmesi and ışın tedavisi; each draft marked CANDIDATE.
- **Inv. 7** — decompression illness / gas embolism now, carbon-monoxide poisoning, sudden vision
  loss, collapsed lung now and seizure now left to `base.life_threat` and the physician (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Instruments** — the UHMS/WRSTC questionnaire is not reproduced (SH-S6 used for domains only).
- **Inv. 21** — RED axes intentionally unspecified (gap 8).
- **Inv. 22** — no numerals in any candidate question; waiting times and onset windows stay in §1.
- **Fitness-to-dive / chamber suitability** — history capture only; the report and the treatment
  decision are the specialist's.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources SH-S1…SH-S9 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
