# Spor Hekimliği (Sports Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Spor Hekimliği (Sports Medicine)
Taxonomy id: `spor_hekimligi` (branches.yaml — cluster `medical`, all visit types).
Purpose: patient-owned, Turkish-first **pre-visit intake** (sport, injury and pre-participation
history for a clinician-ready note) — **not** diagnosis, not triage authority, and **not** a
fitness-to-play verdict. This file is a *proposal for a clinician to sign off*. It assigns **no**
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the primary source is the new **Sporcu Sağlık Raporları Yönetmeliği** (Sağlık
  Bakanlığı and Gençlik ve Spor Bakanlığı, RG 11 Ağustos 2026, sayı 33337), whose EK-1 is the
  statutory pre-participation health declaration. The Türk Tabipleri Birliği guide prepared with the
  Türkiye Spor Hekimleri Derneği (2018) is the second Turkish source. The ESC 2020 sports cardiology
  guideline was located but **no verbatim text was captured** (§4 gap 2), so it supports nothing here.
- **The pack is not the statutory declaration and does not duplicate it.** SP-S1 Madde 6 makes the
  EK-1 form, filled on e-Devlet or the health information system, the basis of the report. This pack
  captures complementary history for the visit. It must not be presented, stored or exported as EK-1.
  **Legal-reviewer decision required** on how the two are shown side by side.
- **Fitness-to-play is the physician's report.** SP-S1 Madde 4 (g) defines the sporcu sağlık raporu
  as the result of a physician's examination and evaluation (EK-3). The pack never implies a verdict.
- **Exertional fainting and exertional chest discomfort — clinician decision.** An earlier draft said
  these "belong to base". That was wrong: base has only an acute chest-pain probe
  (`rf_chest_pain_acute`) and no exertional-syncope rule, so as drafted the two central
  pre-participation cardiac items reached no note. Q14 and Q15 are now drafted from sourced wording
  (SP-S2 items 13 and 14, a non-OCR source; SP-S1 EK-1 items 5 and 6) as **history inputs only**: no
  rule reads them and they do not extend `base.life_threat` (invariant 7). They carry
  `hold=clinician decision — base.life_threat posture`, so they are recorded but not emitted until
  the clinician decides.
- **No validated instrument is reproduced.** EK-1 opens with four mental-health items scored over the
  last fortnight (the PHQ-2 / GAD-2 pattern). They are **not** reproduced and **not** described as
  Turkish-validated; mental-health screening stays with the consented wellbeing module.
- **Not repeated from base:** medications and supplements (`otc_herbal`), allergies, smoking,
  alcohol, pregnancy and last menstrual period.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger. EK-1's own "refer if yes" notes are statutory
  report-routing, not acuity, and are not encoded.
- **Verification caveat (every quote in §1):** SP-S1's main text was downloaded with `curl` from the
  Resmî Gazete HTML (raw text). **SP-S1 EK-1 is a scanned image PDF**: it was read with `tesseract`
  using the English model (no Turkish data installed), so Turkish letters were lost and **the EK-1
  quotes below have diacritics restored by hand — they MUST be re-read against the image**. SP-S2 was
  extracted locally with `pdftotext`. Before sign-off each sentence MUST be committed as a verbatim
  snapshot with `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived
  rule stays `status: draft_needs_source`. The wave 9 verification re-fetch of SP-S1's Resmî Gazete
  page failed TLS verification, so SP-S1 and its EK-1 remain **unverified**.
- **OCR-only items (Q2, Q3, Q7, Q8, Q9, Q10).** Each rests only on the OCR'd EK-1 text. They are kept
  because the topics are standard pre-participation topics and the asks are own words, but none may be
  promoted, or cited by a rule, until the EK-1 image is re-read and snapshotted.
- This file does **not** edit `packages/protocols/specialty/spor_hekimligi.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### SP-S1 — Sporcu Sağlık Raporları Yönetmeliği and EK-1 "Spora Katılım Sağlık Durumu Değerlendirme Formu" (Türkiye)
- **guideline_id (proposed):** `TR-YON-SPORCU-SAGLIK-RAPORLARI-2026` (regulation)
- **Publishing body:** Sağlık Bakanlığı ve Gençlik ve Spor Bakanlığı
- **Version / date:** Resmî Gazete 11 Ağustos 2026, sayı 33337; in force on publication (Madde 11)
- **URLs:** text https://www.resmigazete.gov.tr/eskiler/2026/08/20260811-2.htm · annexes (scanned)
  https://www.resmigazete.gov.tr/eskiler/2026/08/20260811-2-1.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim — Madde 4 (ç) and (g):**
  > "Spora katılım sağlık durumu değerlendirme formu: Sporcu sağlık raporu veya sağlık durum belgesi
  > başvurusu öncesinde doldurulan ve kişisel sağlık durumu hakkında kişinin beyanını içeren EK-1’de
  > yer alan formu,"
  > "bir veya birden çok tabip tarafından yapılan muayene ve değerlendirme sonucunda tespit edildiği
  > durum bildirir EK-3’te yer alan sağlık raporunu"
- **Verbatim — Madde 6 (2):**
  > "Değerlendirme için spora katılım sağlık durumu değerlendirme formunda kişinin kendisi, velisi
  > veya vasisi tarafından verilen beyan ve genel tıbbi muayene esas alınır."
- **Verbatim — EK-1 (OCR, diacritics restored by hand — re-verify):**
  > "Hangi spor dalı için talep edildiği"
  > "5. Egzersiz sırasında veya sonrasında hiç bayıldınız mı veya bayılmak üzere oldunuz mu?"
  > "6. Egzersiz sırasında göğsünüzde hiç rahatsızlık, ağrı, sıkışma veya basınç oldu mu?"
  > "7. Egzersiz sırasında çarpıntı veya düzensiz atış hissettiniz mi?"
  > "8. Bir hekim size hiç kalp sorununuzun olduğunu söyledi mi?"
  > "11. Hiç nöbet geçirdiniz mi?"
  > "12. … kalp sorunlarından ölen oldu mu veya beklenmedik veya açıklanamayan ani bir ölüm yaşadı mı"
  > "16. Sizi rahatsız eden bir kemik, kas, bağ veya eklem yaralanmanız var mı?"
  > "17. Egzersiz sırasında veya sonrasında öksürüyor, hırıltılı nefes alıyor veya nefes almada
  > zorluk çekiyor musunuz?"
  > "21. … bir beyin sarsıntısı veya baş yaralanması geçirdiniz mi?"
  > "23. Sıcakta egzersiz yaparken hiç hastalandınız mı?"
  > "26. Kilonuz konusunda endişeleniyor musunuz?"
  > "Herhangi biri “Evet” ise spor hekimi veya aile hekimine yönlendirilmelidir."
- **Confidence: HIGH** for the main text (regulation HTML, raw); **MEDIUM** for EK-1 wording (OCR
  of a scan, diacritics restored). The family-history item uses an age threshold that is not put
  into patient copy (§4 gap 3).

### SP-S2 — TTB Aile Hekimliği Kolu with Türkiye Spor Hekimleri Derneği, "Birinci Basamak Sağlık Hizmetlerinde Spora Katılım Belgesi Hazırlama Rehberi" (Türkiye)
- **guideline_id (proposed):** `TTB-TSHD-SPORA-KATILIM-REHBERI-2018`
- **Publishing body:** Türk Tabipleri Birliği; foreword by the Türkiye Spor Hekimleri Derneği
  president · **Version / date:** Ocak 2018, ISBN 978-605-9665-26-1
- **URL:** https://www.ttb.org.tr/kutuphane/sporcu_sagligi.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "“Öykü Alma” spora katılım öncesi muayenenin en önemli bölümünü oluşturmaktadır."
  > "Bu muayenenin amacı, kişileri spordan ya da yarışlardan yoksun kılmak, uzak tutmak değil"
  > "Yaşamı tehdit edecek durumların saptanması,"
- **Verbatim — Form-1 history items:**
  > "8. Daha önce spor yaralanması geçirdiniz mi?"
  > "13. Antrenman sırasında veya sonrasında hiç bayıldınız mı?"
  > "14. Antrenman sırasında veya sonrasında göğüs ağrınız oldu mu?"
  > "20. Daha önce nöbet (epilepsi/sara nöbeti, vb.) geçirdiniz mi?"
  > "22. İştahsızlık veya kilo alamama yakınmanız var mı?"
- **Confidence: MEDIUM–HIGH** for text (primary PDF, extracted locally). Written for primary care,
  predates SP-S1 and uses a different family-history age threshold. A numeric performance claim in
  its foreword is deliberately **not** quoted (invariant 20).

### Cited in §3 but not yet quoted here
- EK-1 item 15 (Q4), EK-1 item 29 (Q13, the "yeme düzeni" half) and SP-S2 item 19 (Q11) are cited by
  §3 items but their text was not captured in this section. SP-S2 item 8's treatment phrase appears
  only in Q5's source line. Each must be quoted verbatim here, from the primary text, before its item
  is promoted; for Q13 the alternative is to cut the ask to weight only.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Sport played | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; **no physical-activity archetype in the OPT** |
| Q3 | Current sports injury | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Past injury that cost training or matches | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q5 | Surgery for that injury | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; **no procedure archetype in the OPT** |
| Q6 | Past concussion or head injury | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Cough / wheeze / hard breathing with exercise | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Unwell while exercising in the heat | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Fast or irregular heartbeat during sport | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Heart problem previously named by a doctor | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q11 | Young sudden or cardiac death in the family | **no root — export blocked (INT-041)** | — | — |
| Q12 | Past epileptic seizure | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q13 | Worry about weight or eating | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q14 | HELD (clinician decision) — fainting or near-fainting with exercise | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q15 | HELD (clinician decision) — chest discomfort with exercise | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm sign | Source | base item | This proposal's role |
|---|---|---|---|
| Fainting or near-fainting during or after exercise | SP-S1 EK-1 item 5, SP-S2 item 13 | **absent** (no exertional-syncope rule in base) | History input; no rule (Q14, held: clinician decision) |
| Chest pain or pressure on exercise | SP-S1 EK-1 item 6, SP-S2 item 14 | only the acute probe `rf_chest_pain_acute`; no exertional item | History input; no rule (Q15, held: clinician decision) |
| Heat illness happening now | SP-S1 EK-1 item 23 | **absent** from base.life_threat | **Not asked.** Q8 is past history only |
| New weakness or numbness after a head or neck impact now | SP-S1 EK-1 item 22 | `rf.stroke_fast` / `rf.new_neuro_deficit_subacute` | **Not asked.** Q6 is past history only |
| Breathlessness at rest | — | `rf.dyspnoea_rest` | Q7 is exercise-related history only |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21). EK-1's statutory
referral notes are quoted as provenance, not adopted as triage.

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Exertional fainting or near-fainting (Q14, held) | "Egzersiz sırasında veya sonrasında hiç bayıldınız mı veya bayılmak üzere oldunuz mu?" | SP-S1 EK-1 item 5 |
| Exertional chest discomfort (Q15, held) | "Egzersiz sırasında göğsünüzde hiç rahatsızlık, ağrı, sıkışma veya basınç oldu mu?" | SP-S1 EK-1 item 6 |
| Palpitations during exercise (Q9) | "Egzersiz sırasında çarpıntı veya düzensiz atış hissettiniz mi?" | SP-S1 EK-1 item 7 |
| Young sudden or cardiac death in the family (Q11) | "beklenmedik veya açıklanamayan ani bir ölüm yaşadı mı" | SP-S1 EK-1 item 12 |
| Past concussion or head injury (Q6) | "bir beyin sarsıntısı veya baş yaralanması geçirdiniz mi?" | SP-S1 EK-1 item 21 |
| Statutory routing on any cardiac "yes" | "Herhangi biri “Evet” ise spor hekimi veya aile hekimine yönlendirilmelidir." | SP-S1 EK-1 |

---

## 3. Candidate B1 Turkish pre-visit questions (15 drafted: 13 active, 2 held)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE —
clinician to approve wording.** Own words throughout; EK-1 and Form-1 are sources, not scripts. No
item carries a triage level. Q1 binds to the pack's `basvuru_nedeni` slot and ends in "nedir?" so the
generator's neutral follow-up is used, not the complaint follow-up. Duration comes from the pack's
`sikayet_suresi` slot, whose fixed ask fits injury visits. For pre-participation report visits there
is no sourced alternative wording: **clinician decision pending** (no `pack:` line is written).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün spor hekimliği polikliniğine gelme nedeniniz nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Sport played** · archetype: `OBSERVATION.story.v1` · source: SP-S1 EK-1 ("Hangi spor dalı için talep edildiği")
> "Hangi sporu yapıyorsunuz?"
gen: slot=spor_dali; type=string
CANDIDATE — clinician to approve wording. Open answer; the risk group (A/B/C, SP-S1 Madde 4 (c)) is set by the ministry list, not by the patient.
OCR-only source — re-read the scan before promotion.

**Q3 — Current sports injury** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S1 EK-1 item 16
> "Şu anda sizi rahatsız eden bir spor yaralanmanız var mı?"
gen: slot=guncel_spor_yaralanmasi; type=boolean
CANDIDATE — clinician to approve wording. Site and character come from base `location_text` / `character_text`.
OCR-only source — re-read the scan before promotion.

**Q4 — Past injury that cost training or matches** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SP-S1 EK-1 item 15, SP-S2 item 8
> "Daha önce antrenman ya da maç kaçırmanıza yol açan bir yaralanma geçirdiniz mi?"
gen: slot=gecmis_spor_yaralanmasi; type=boolean
CANDIDATE — clinician to approve wording. EK-1 item 15 is cited but not quoted in §1; quote it before
promotion.

**Q5 — Surgery for that injury (if Q4 yes)** · archetype: `OBSERVATION.story.v1` · source: SP-S2 item 8 ("tedavinizi (ameliyat, alçı, fizik tedavi")
> "Bu yaralanma için ameliyat oldunuz mu?"
gen: slot=yaralanma_ameliyati; type=boolean; ask_if=gecmis_spor_yaralanmasi == true
CANDIDATE — clinician to approve wording. The SP-S2 item 8 phrase is not yet quoted in §1; quote it
before promotion.

**Q6 — Past concussion or head injury** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S1 EK-1 item 21
> "Daha önce beyin sarsıntısı ya da baş yaralanması geçirdiniz mi?"
gen: slot=beyin_sarsintisi_oykusu; type=boolean
CANDIDATE — clinician to approve wording. Past event only (§2.2). Follows the source construct:
a concussion without lasting symptoms is still pre-participation history.

**Q7 — Cough, wheeze or hard breathing with exercise** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S1 EK-1 item 17
> "Egzersiz sırasında ya da sonrasında öksürük, hırıltı ya da nefes almada zorluk oluyor mu?"
gen: slot=egzersizle_solunum_belirtisi; type=boolean
CANDIDATE — clinician to approve wording. Exercise-related history; breathlessness at rest is base (§2.2).
OCR-only source — re-read the scan before promotion.

**Q8 — Unwell while exercising in the heat** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S1 EK-1 item 23
> "Sıcak havada spor yaparken hiç fenalaştığınız oldu mu?"
gen: slot=sicakta_fenalasma; type=boolean
CANDIDATE — clinician to approve wording. Past event only (§2.2).
OCR-only source — re-read the scan before promotion.

**Q9 — Fast or irregular heartbeat during sport** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S1 EK-1 item 7
> "Spor yaparken kalbinizin çok hızlı ya da düzensiz attığını hissettiniz mi?"
gen: slot=sporda_carpinti; type=boolean
CANDIDATE — clinician to approve wording. §2.3 candidate; no level.
OCR-only source — re-read the scan before promotion.

**Q10 — Heart problem previously named by a doctor** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SP-S1 EK-1 item 8
> "Bir doktor size daha önce kalbinizle ilgili bir sorun olduğunu söyledi mi?"
gen: slot=bilinen_kalp_sorunu; type=boolean
CANDIDATE — clinician to approve wording. EK-1's broader "kalp sorunu" suits sports cardiology.
OCR-only source — re-read the scan before promotion.

**Q11 — Young sudden or cardiac death in the family** · archetype: **no root — export blocked (INT-041)** · source: SP-S1 EK-1 item 12, SP-S2 item 19
> "Ailenizde genç yaşta aniden ya da kalp hastalığı nedeniyle kaybettiğiniz biri oldu mu?"
gen: slot=ailede_genc_yasta_ani_olum; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. "Genç yaşta" replaces the sources' age thresholds, which
differ (§4 gap 3). The softer "kaybettiğiniz" follows tibbi_genetik's `ailede_ani_aciklanamayan_kayip`.
SP-S2 item 19 is cited but not quoted in §1; quote it before promotion. Relatives' health data, so
`text_first`. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending
counsel review (INT-349).

**Q12 — Past epileptic seizure** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SP-S1 EK-1 item 11, SP-S2 item 20
> "Daha önce hiç sara, yani epilepsi nöbeti geçirdiniz mi?"
gen: slot=epilepsi_nobeti_oykusu; type=boolean
CANDIDATE — clinician to approve wording. "Sara, yani epilepsi nöbeti" avoids the shift-duty sense of
"nöbet" and keeps a parenthesis out of spoken copy (TTS, invariant 10).

**Q13 — Worry about weight or eating** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S1 EK-1 items 26 and 29, SP-S2 item 22
> "Kilonuz ya da yeme düzeniniz konusunda sizi kaygılandıran bir durum var mı?"
gen: slot=kilo_yeme_kaygisi; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Not a screening scale; the word "bozukluk" is not put to the
patient. An eating-behaviour disclosure, and athletes are often accompanied by a coach or parent, so
`text_first`. EK-1 item 29 (the "yeme düzeni" half) is not quoted in §1: quote it, or cut the ask to
weight only (clinician decision pending).

**Q14 — Fainting or near-fainting with exercise** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S2 item 13, SP-S1 EK-1 item 5
> "Spor yaparken ya da hemen sonra hiç bayıldınız ya da bayılacak gibi oldunuz mu?"
gen: slot=egzersizde_bayilma; type=boolean; hold=clinician decision — base.life_threat posture
CANDIDATE — HELD for the clinician decision (§0). History input only; no rule reads it and it does
not extend `base.life_threat`. SP-S2 is a pdftotext extraction, not OCR.

**Q15 — Chest discomfort with exercise** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S2 item 14, SP-S1 EK-1 item 6
> "Spor yaparken göğsünüzde ağrı, sıkışma ya da baskı hissettiniz mi?"
gen: slot=egzersizde_gogus_rahatsizligi; type=boolean; hold=clinician decision — base.life_threat posture
CANDIDATE — HELD for the clinician decision (§0). History input only; no rule reads it and it does
not extend `base.life_threat`. SP-S2 is a pdftotext extraction, not OCR.

*(15 drafted: 13 active, 2 held.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye Spor Hekimleri Derneği versioned guideline** for pre-participation or sports-injury
   history — only the 2018 TTB guide (with a TSHD foreword) was found. **NO SOURCE FOUND
   (versioned) — clinician must supply.**
2. **ESC 2020 Guidelines on sports cardiology** (Pelliccia et al., *Eur Heart J* 2021;42:17–96) —
   title and citation were retrieved, but the screening text was not; **not quoted and not used.**
   IOC pre-participation consensus not retrieved.
3. **Family-history age threshold** — SP-S1 EK-1 and SP-S2 use different ages; the patient text says
   "genç yaşta". A clinician must choose the threshold for any rule.
4. **EK-1 wording** — read by English-model OCR from a scan; every EK-1 quote must be re-verified
   against the image before a snapshot is committed. Q2, Q3, Q7, Q8, Q9 and Q10 rest on that text
   alone and may not be promoted, or cited by a rule, until it is.
5. **Statutory declaration boundary** — how pack answers sit next to the EK-1 declaration on
   e-Nabız. **Legal-reviewer decision required.**
6. **Female athlete items** (SP-S1 EK-1 items 30–33, SP-S2 item 23: menstrual history) — not drafted;
   base captures the last period, and reproductive history is a text-first category. Clinician to
   decide with the base owner.
7. **Missing paired organ, groin pain or hernia, recurrent skin rash, blood disorder, vision problems,
   inherited heart conditions by name** (SP-S1 EK-1 items 13, 18–20, 24–25) — not drafted to stay
   near twelve items; clinician may swap them in.
8. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. All three
   RED axes (route × register × location, invariant 21) are **deliberately unassigned**.
9. **openEHR leaf paths (at-codes)**, a **physical-activity archetype** and a **family-history
   archetype** — deferred (`openehr_deferred_reason`, INT-032; INT-041 for Q11).
10. **Exertional fainting and exertional chest discomfort (Q14, Q15)** — drafted from SP-S2 items 13
    and 14 as history inputs with no rule; held until the clinician decides the base.life_threat
    posture. Any rule placement stays with the base owner (invariant 7).
11. **Quotes cited but not captured** — EK-1 items 15 and 29, SP-S2 item 19 and SP-S2 item 8's
    treatment phrase (Q4, Q13, Q11, Q5; §1). Quote each before its item is promoted.
12. **Duration ask for report visits** — the fixed `sikayet_suresi` ask fits injury visits; no sourced
    wording exists for pre-participation report visits. **Clinician decision pending.**

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE.
- **Inv. 7** — heat illness now and new neurological signs after impact left to `base.life_threat`
  and the physician (§2.2). Exertional fainting and exertional chest discomfort are drafted as history
  inputs (Q14, Q15), held for the clinician's decision; nothing extends `base.life_threat`.
- **Inv. 18** — Q11 (relatives' health) and Q13 (eating-behaviour disclosure) are `text_first`; Q11
  needs its INT-349 row under D3.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Instruments** — EK-1's four mental-health items (PHQ-2 / GAD-2 pattern) are not reproduced and
  not described as Turkish-validated.
- **Inv. 20** — no performance figure from SP-S2's foreword is quoted.
- **Inv. 21** — RED axes intentionally unspecified (gap 8).
- **Inv. 22** — no numerals in any candidate question; age thresholds stay out of patient copy.
- **Fitness-to-play** — history capture only; the EK-3 report is the physician's.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources SP-S1…SP-S2 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
