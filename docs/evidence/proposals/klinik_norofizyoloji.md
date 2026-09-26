# Klinik Nörofizyoloji (Clinical Neurophysiology — EEG/EMG) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Klinik Nörofizyoloji (EEG/EMG)
Taxonomy id: `klinik_norofizyoloji` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  short verbatim fragment + citation). Where no source was found, the row reads **"NO SOURCE FOUND —
  clinician must supply"**. Nothing was invented.
- **What this clinic sees:** patients are *referred for a test* — mainly EMG/nerve conduction (numbness,
  tingling, weakness, cramps) or EEG (episodes of altered awareness). The pack therefore asks the
  complaint behind the referral, the test named on the referral, the symptoms the tests address, and
  the few safety facts the EMG sources say the doctor must know. It does not interpret any test.
- **Turkish first:** the primary sources are Türk Nöroloji Derneği (TND) patient consent/information
  forms for EMG and video-EEG (2012), the TND Epilepsi Çalışma Grubu *Epilepsi Rehberi* (2007) and the
  Türk Epilepsi ile Savaş Derneği (TEİSD) first-aid page. The Türkiye Klinik Nörofizyoloji EEG-EMG
  Derneği site (tkneed.org) was reached but no patient material was found (§4). AANEM patient pages are
  the international corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted only in §2.3.
- **Invariant 7:** sudden weakness or numbness (stroke), a seizure in progress or a cluster of seizures,
  a first-ever seizure and fast-spreading weakness are **`base.life_threat` / physician territory**
  (§2.2). None is asked as such here and nothing extends `base.life_threat`.
- **Witnesses:** KN-S2 and KN-S3 say the account of someone who saw the episode matters. Q9 asks whether
  such a person exists; a relative answering for the patient is handled by base `subject_role` /
  `proxy_reported` (runtime), not authored here. Every item keeps self-address (`siz`).
- **No instruments** are involved; no seizure-classification or neuropathy score is reproduced.
- **Base overlap avoided:** medicines, blood thinners (`anticoagulant_use` — KN-S1 and KN-S5 name them
  as a test safety fact), allergies, smoking, alcohol and pregnancy are collected by
  `packages/protocols/base/intake.yaml` and are **not** repeated.
- **Preparation advice is not intake:** hair/skin preparation, "do not change your medicine doses" (KN-S2)
  and similar are instructions, not questions; they belong to appointment messaging, not this pack.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; PDFs extracted
  with `pdftotext` into the session scratchpad, no copy kept in the repo). Before sign-off each fragment
  MUST be re-checked against the primary text and committed as a verbatim snapshot with
  `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule stays
  `status: draft_needs_source`.
- **Copyright:** questions are written in our own words; sources are quoted as short fragments only.
- This file does **not** edit `packages/protocols/specialty/klinik_norofizyoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### KN-S1 — TND, "EMG (Elektromyografi) Hasta Bilgilendirilmiş Onam Formu" (Türkiye)
- **guideline_id (proposed):** `TND-ONAM-EMG-2012` (patient consent/information form, NOT a guideline)
- **Publishing body:** Türk Nöroloji Derneği · **Date:** PDF metadata created 6 April 2012; no printed
  version · **retrieved_on:** 2026-09-26
- **URL:** https://noroloji.org.tr/TNDData/Uploads/files/EMG%20(ELEKTROMYOGRAF%C4%B0)%20HASTA%20B%C4%B0LG%C4%B0LEND%C4%B0R%C4%B0LM%C4%B0%C5%9E%20ONAM%20FORMU.pdf
- **Verbatim fragments:**
  > "EMG (elektromyografi} kasların, sinirlerin ve sinir köklerinin elektriksel özelliklerinin ölçülmesi yoluyla bu yapıların sağlık durumlarının değerlendirildiği bir muayene yöntemidir." (brace as printed)
  > "İleri derecede kan pıhtılaşma bozukluğu olan veya kan pıhtılaşmasını engelleyen ilaç kullanan hastalarda zorunlu olmadıkça EMG incelemesi yapılmaz."
  > "hastada kalp pili veya beyin pili bulunması EMG yapılmasına engel değildir."
- **Confidence: MEDIUM** — Turkish society form, 2012; text extracted from the PDF.

### KN-S2 — TND, "Video-EEG Monitorizasyonu Hasta Bilgilendirilmiş Onam Formu" (Türkiye)
- **guideline_id (proposed):** `TND-ONAM-VEEG-2012` · **Date:** PDF metadata 2012 (title "VIDEO-EEG TND-son")
- **URL:** https://noroloji.org.tr/TNDData/Uploads/files/V%C4%B0DEO-EEG%20MON%C4%B0TOR%C4%B0ZASYONU%20HASTA%20B%C4%B0LG%C4%B0LEND%C4%B0R%C4%B0LM%C4%B0%C5%9E%20ONAM%20FORMU.pdf
- **Verbatim fragments:**
  > "Gelmeden önceki gece, uykusuz veya aç kalmanıza gerek yoktur."
  > "tanıyı zorlaştıracağından ilaç dozlarını az almak ya da almamak gibi davranışlara kesinlikle girmemelisiniz."
  > "nöbetlerinizi iyi bilen, hastalığınız hakkında bilgi verebilecek" (on the companion who should attend)
- **Confidence: MEDIUM** — inpatient video-EEG form; used only for the witness principle and §0.

### KN-S3 — TND Epilepsi Çalışma Grubu, "TND Epilepsi Rehberi" (Türkiye)
- **guideline_id (proposed):** `TND-EPILEPSI-REHBERI-2007`
- **Publishing body:** Türk Nöroloji Derneği Epilepsi Çalışma Grubu (editör Canan Aykut Bingöl) ·
  **Version:** title page "2007"; PDF created 28 October 2008 · **retrieved_on:** 2026-09-26
- **URL:** https://noroloji.org.tr/html/file/epilepsi.pdf
- **Verbatim fragments:**
  > "Epileptik bir atak olduğu konusundaki klinik karar atağın tarifine ve semptomlarına bağlı olarak verilmelidir."
  > "nöbet düşünülen her hastada EEG çekilmelidir."
  > "Hastanın hem kendisinden, hem de olaya tanıklık eden aile bireyleri, bakıcı ya da arkadaşlarından ayrıntılı bilgi alınmalıdır."
  > "Tanıya varmada, hastaların video kayıtlarını ve yazılı açıklamalarını istemek yararlı olabilir."
  > "Öykü:(hastadan ve olayı gören bir kişiden) Hangi durumda olduğu; tetikleyen bir neden; … yaralanma, dil ısırma;" (algorithm box)
  > "Ailede nöbet, epilepsi öyküsü" (algorithm box)
  > "Provoke edici nedenlerin varlığında; uykusuzluk, alkol alımı, hipoksi, kemoterapi"
  > "İlk kez nöbet geçiren her hastanın … en kısa zamanda … bir nöroloji uzmanı tarafından görülmesi sağlanmalıdır." (§2.3 only)
- **Confidence: MEDIUM** — Turkish society guideline, but 2007; confirm whether a newer TND epilepsy
  guideline supersedes it.

### KN-S4 — TEİSD, "Epilepsi ve İlk Yardım" (Türkiye)
- **guideline_id (proposed):** `TEISD-ILK-YARDIM` · **Date:** none shown · **URL:** https://turkepilepsi.org.tr/menu/41/epilepsi-ve-ilk-yardim
- **Verbatim (ambulance list, fragments):**
  > "Kişi yaralanmışsa, gebe ise veya diyabetik ise"
  > "İkinci nöbet, ilk nöbet bittikten çok kısa bir süre sonra başlıyorsa"
  > "Kasılmalar bittikten sonra kişinin bilinci açılmıyorsa"
  > (a further item carries a numeric duration; it stays in the source, never in patient copy)
- **Use:** §2.3 only. **Confidence: MEDIUM** — undated lay page.

### KN-S5 — AANEM, "FAQs Before EDX Testing" (international)
- **guideline_id (proposed):** `AANEM-PATIENT-FAQ-EDX` · **Date:** none shown
- **URL:** https://www.aanem.org/clinical-practice-resources/patient-information/faqs-before-edx-testing · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "You are being sent to the EMG lab because you have numbness, tingling, pain, weakness, or muscle cramping."
  > "Tell the EMG doctor if you are taking aspirin, blood thinners (like Coumadin®), have a pacemaker, or have hemophilia."
  > "Take a bath or shower to remove oil from your skin. Do not use body lotion on the day of the test."
- **Confidence: MEDIUM** — professional society patient page, undated.

### KN-S6 — AANEM, "Types of Tests" (international)
- **URL:** https://www.aanem.org/clinical-practice-resources/patient-information/types-of-tests
- **Verbatim:** "Painless tests that check the nerve pathways through the spinal cord or from the eyes and ears." (evoked potentials)
- **Use:** confirms evoked potentials fall in scope of Q2's test name; no item derives from it.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit (complaint behind the referral) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Test named on the referral | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no service-request archetype in the OPT — §4 |
| Q3 | Numbness or tingling in limbs | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Weakness in limbs | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Muscle cramps or pain | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Implanted pacemaker or brain stimulator | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no device archetype in the OPT — §4 |
| Q7 | Known bleeding / clotting disorder | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q8 | Episodes of lost or altered awareness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | A witness who can describe the episodes | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Phone video of an episode | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Tongue biting during an episode | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Episodes more frequent after sleep loss | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q13 | Epilepsy in the family | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no family-history archetype in the OPT — §4 |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm | Source | base item | This proposal's role |
|---|---|---|---|
| Sudden one-sided weakness or numbness, speech or face change | general (stroke); see `noroloji.md` Q3 | `rf.stroke_fast` (named gap); `rf_new_neuro_deficit_subacute` probe | **Not asked as such**; Q3/Q4 capture referral symptoms, whose tempo is the clinician's |
| Seizure lasting long, a second seizure soon after, not waking after a seizure | KN-S4 | **absent** from base.life_threat | **Not asked here** |
| First-ever seizure | KN-S3 | **absent** | **Not asked here**; Q8 captures episodes for the note only |
| Weakness spreading over days, or with breathing or swallowing difficulty | **NO SOURCE FOUND (verbatim)** | **absent**; nearest `rf.dyspnoea_rest` | **Not asked here** |
| Bleeding risk for needle EMG | KN-S1; KN-S5 | base `anticoagulant_use` (not a red flag) | Q7 adds a known bleeding disorder only |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Repeated seizure soon after the first | "İkinci nöbet, ilk nöbet bittikten çok kısa bir süre sonra başlıyorsa" | KN-S4 |
| Not regaining awareness after convulsions | "Kasılmalar bittikten sonra kişinin bilinci açılmıyorsa" | KN-S4 |
| Seizure with injury, in pregnancy or with diabetes | "Kişi yaralanmışsa, gebe ise veya diyabetik ise" | KN-S4 |
| Prolonged seizure | numeric duration in KN-S4 — stays in the source | KN-S4 |
| First seizure needs prompt neurologist review | "İlk kez nöbet geçiren her hastanın … en kısa zamanda … bir nöroloji uzmanı tarafından görülmesi sağlanmalıdır." | KN-S3 |
| Rapidly progressive weakness | **NO SOURCE FOUND (verbatim)** | clinician must supply |

---

## 3. Candidate B1 Turkish pre-visit questions (13)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE —
clinician to approve wording.** No item carries a triage level; items may at most feed a
`candidate_flag` (max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Duration is
captured by the pack's `sikayet_suresi` slot. Q1 binds to the pack's `basvuru_nedeni` slot; it names
the complaint, not the clinic, because "klinik nörofizyoloji" is jargon for most patients.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün sizi bu teste yönlendiren şikâyetinizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Test named on the referral** · archetype: `OBSERVATION.story.v1` · source: KN-S1 (EMG), KN-S2 (video-EEG), KN-S6 (evoked potentials)
> "Size istenen test adını biliyorsanız söyler misiniz?"
gen: slot=istenen_test_adi; type=string; follow_up=Sevk belgenizde yazan test adını okuyabilir misiniz?
CANDIDATE — clinician to approve wording. Free text; the referral record is authoritative. (The
genitive "testin" was avoided: the Turkish PolicyGuard register arm reads it as singular address — §5.)

**Q3 — Numbness or tingling in limbs** · archetype: `OBSERVATION.symptom_sign.v1` · source: KN-S5 ("numbness, tingling"), KN-S1 ("sinirlerin")
> "Kollarınızda ya da bacaklarınızda uyuşma veya karıncalanma var mı?"
gen: slot=uyusma_karincalanma; type=boolean; follow_up=Ellerinizde ya da ayaklarınızda iğnelenme hissi oluyor mu?
CANDIDATE — clinician to approve wording. Sudden one-sided numbness is §2.2, not this item.

**Q4 — Weakness in limbs** · archetype: `OBSERVATION.symptom_sign.v1` · source: KN-S5 ("weakness"), KN-S1 ("kasların")
> "Kollarınızda ya da bacaklarınızda güçsüzlük hissediyor musunuz?"
gen: slot=kol_bacak_gucsuzluk; type=boolean; follow_up=Bir şeyi tutarken ya da merdiven çıkarken zorlanıyor musunuz?
CANDIDATE — clinician to approve wording. Sudden or spreading weakness is §2.2.

**Q5 — Muscle cramps or pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: KN-S5 ("pain … or muscle cramping")
> "Kaslarınızda kramp ya da ağrı oluyor mu?"
gen: slot=kas_kramp_agri; type=boolean; follow_up=Kaslarınızın kasılıp tutulduğu oluyor mu?
CANDIDATE — clinician to approve wording.

**Q6 — Implanted pacemaker or brain stimulator** · archetype: `OBSERVATION.story.v1` · source: KN-S5 ("have a pacemaker"), KN-S1 ("kalp pili veya beyin pili")
> "Vücudunuzda kalp pili ya da beyin pili gibi bir cihaz var mı?"
gen: slot=implante_cihaz; type=boolean; follow_up=Göğsünüzde ya da vücudunuzda takılı bir pil veya cihaz bulunuyor mu?
CANDIDATE — clinician to approve wording. KN-S1 says a device does not rule EMG out; KN-S5 says the
doctor must be told. A test-planning fact, never a flag.

**Q7 — Known bleeding or clotting disorder** · archetype: `EVALUATION.problem_diagnosis.v1` · source: KN-S1 ("İleri derecede kan pıhtılaşma bozukluğu"), KN-S5 ("have hemophilia")
> "Size daha önce kanın pıhtılaşmasıyla ilgili bir hastalık tanısı konuldu mu?"
gen: slot=kanama_bozuklugu; type=boolean; follow_up=Küçük bir kesikte kanamanızın durması uzun sürüyor mu?
CANDIDATE — clinician to approve wording. Blood thinners stay with base `anticoagulant_use`.

**Q8 — Episodes of lost or altered awareness** · archetype: `OBSERVATION.symptom_sign.v1` · source: KN-S3 ("Epileptik bir atak …"; "nöbet düşünülen her hastada EEG"), KN-S2
> "Kendinizden geçtiğiniz ya da çevrenizi fark etmediğiniz ataklar oluyor mu?"
gen: slot=bilinc_degisikligi_atak; type=boolean; follow_up=Bir süre ne olduğunu hatırlamadığınız anlar yaşıyor musunuz?
CANDIDATE — clinician to approve wording. Neutral "atak" rather than a diagnostic label; a first or
ongoing seizure is §2.2.

**Q9 — A witness who can describe the episodes** · archetype: `OBSERVATION.story.v1` · source: KN-S3 ("olaya tanıklık eden aile bireyleri, bakıcı ya da arkadaşlarından ayrıntılı bilgi alınmalıdır"), KN-S2
> "Bu atakları görmüş ve anlatabilecek bir yakınınız var mı?"
gen: slot=atak_tanigi; type=boolean; ask_if=bilinc_degisikligi_atak == true; follow_up=Atak sırasında yanınızda olan biri size neler olduğunu anlattı mı?
CANDIDATE — clinician to approve wording. Asked only when Q8 is yes.

**Q10 — Phone video of an episode** · archetype: `OBSERVATION.story.v1` · source: KN-S3 ("hastaların video kayıtlarını … istemek yararlı olabilir")
> "Bu ataklardan birinin telefonla çekilmiş bir videosu var mı?"
gen: slot=atak_videosu; type=boolean; ask_if=bilinc_degisikligi_atak == true; follow_up=Bir yakınınız atak sırasında sizi videoya çekti mi?
CANDIDATE — clinician to approve wording. Asks only whether a video exists; any upload runs under
the document-ingestion consent path, not this pack.

**Q11 — Tongue biting during an episode** · archetype: `OBSERVATION.symptom_sign.v1` · source: KN-S3 ("yaralanma, dil ısırma")
> "Atak sırasında dilinizi ısırdığınız oldu mu?"
gen: slot=atakta_dil_isirma; type=boolean; ask_if=bilinc_degisikligi_atak == true; follow_up=Ataktan sonra dilinizde yara ya da ağrı fark ettiniz mi?
CANDIDATE — clinician to approve wording. History only; its weight is the clinician's.

**Q12 — Episodes more frequent after sleep loss** · archetype: `OBSERVATION.story.v1` · source: KN-S3 ("Provoke edici nedenlerin varlığında; uykusuzluk")
> "Uykusuz kaldığınız dönemlerde bu ataklar artıyor mu?"
gen: slot=uykusuzlukla_atak; type=boolean; ask_if=bilinc_degisikligi_atak == true; follow_up=Az uyuduğunuz günlerden sonra atak geçirdiğiniz oluyor mu?
CANDIDATE — clinician to approve wording. Alcohol, the other trigger KN-S3 names, stays with base.

**Q13 — Epilepsy in the family** · archetype: `OBSERVATION.story.v1` · source: KN-S3 ("Ailede nöbet, epilepsi öyküsü")
> "Ailenizde sara (epilepsi) hastalığı olan biri var mı?"
gen: slot=ailede_epilepsi; type=boolean; follow_up=Anne, baba ya da kardeşlerinizden nöbet geçiren var mı?
CANDIDATE — clinician to approve wording. Which relative and which type is a clinician follow-up.

*(13 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye Klinik Nörofizyoloji EEG-EMG Derneği (TKNEED)** — https://www.tkneed.org/ returned
   navigation, events and publication links only; **no patient information or practice standard was
   retrieved. NO SOURCE FOUND — clinician must supply** a current society standard if one exists.
2. **Currency of KN-S1/KN-S2 (2012) and KN-S3 (2007)** — confirm on sign-off whether TND has newer
   consent forms or a newer epilepsy guideline.
3. **International EEG/EMG practice guidance** (ACNS, IFCN, EAN, NICE NG217 epilepsies) — not retrieved;
   **no verbatim quoted**.
4. **Rapidly progressive weakness, weakness with breathing or swallowing difficulty** — **NO SOURCE
   FOUND (verbatim)**; absent from base. **base.life_threat owner / clinician decide placement.**
5. **Test-specific gating** — EMG items (Q3–Q7) and EEG items (Q8–Q13) are not gated on the test named
   in Q2, because Q2 is free text. A structured test-type slot needs a value set. **Clinician/product
   decision.**
6. **Sourced but not drafted (to stay near twelve):** past head injury, childhood fever convulsions,
   earlier brain infection (KN-S3 algorithm box). Clinician may swap them in.
7. **Myasthenia-related medicine timing before EDX testing** — AANEM mentions it but the fetch returned
   no verbatim sentence. **NO SOURCE FOUND (verbatim) — not drafted.**
8. **Archetypes** — no service-request (Q2), device (Q6) or family-history (Q13) archetype in the OPT;
   bound to `OBSERVATION.story.v1` as narrative only (INT-032 decision needed).
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words, no
  diagnosis/treatment/prognosis wording; each draft marked CANDIDATE. Every ask and follow-up was run
  through the Turkish PolicyGuard `inspect_sentence` arms with zero findings after two rewordings
  (Q7 "hastalığınız var" hit the diagnosis arm; Q2 "testin" hit the register arm — the latter looks like
  a lexicon false positive on a genitive noun, reported for the lexicon owner, not worked around in code).
- **Inv. 4** — Q10 asks only whether a video exists; sharing one is a consent-scoped document flow.
- **Inv. 7** — stroke signs, seizure emergencies, first seizure and progressive weakness left to base /
  physician (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question; KN-S4's duration stays in the source.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot, until then
  `status: draft_needs_source`. Sources KN-S1…KN-S6 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
