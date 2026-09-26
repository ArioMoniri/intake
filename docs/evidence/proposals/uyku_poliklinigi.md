# Uyku Polikliniği (Sleep Clinic) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Uyku polikliniği (Sleep Medicine)
Taxonomy id: `uyku_poliklinigi` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  short verbatim fragment + citation). Where no source was found, the row reads **"NO SOURCE FOUND —
  clinician must supply"**. Nothing was invented.
- **Turkish first:** the primary sources are the Türk Nöroloji Derneği (TND) "Uyku Tıbbı" public page
  and the Türk Toraks Derneği (TTD) "Uykuda Solunum Bozuklukları" page — **lay, undated**. The
  Türk Uyku Tıbbı Derneği (TUTD) site was reached but its disease pages returned navigation only (§4).
  The AASM clinical guidelines (2008 insomnia evaluation; 2017 OSA diagnostic testing) are the
  international clinical corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted only in §2.3.
- **Invariant 7:** sleepiness while driving, breathing pauses with chest pain or breathlessness at rest,
  and injurious night-time behaviour are **`base.life_threat` / physician territory** (§2.2). None is
  asked here and nothing extends `base.life_threat`.
- **Bed-partner reports:** snoring, breathing pauses and night-time movements are usually noticed by
  someone else (U-S2, U-S3). Items Q7, Q8 and Q12 therefore ask whether *someone has told* the patient,
  keeping self-address (`siz`). A partner or relative answering for the patient is handled by base
  `subject_role` / `proxy_reported` (runtime), not authored here.
- **Validated instruments are NOT reproduced or paraphrased:** Epworth Sleepiness Scale, STOP-Bang,
  Berlin, Pittsburgh Sleep Quality Index, Insomnia Severity Index and similar belong to the instrument
  engine (INT-116) behind the licence gate. TUTD lists Turkish sleep forms at https://tutd.org.tr/olcekler
  (link seen, content not read). No item below uses an instrument's situations, scoring or cut-offs
  (e.g., no "dozing while reading/watching TV" situations, no neck size, no body-mass item).
- **Base overlap avoided:** medicines (including sleeping pills), alcohol, smoking, weight, occupation
  and living situation are collected by `packages/protocols/base/intake.yaml` and are **not**
  repeated. Low mood and anxiety are left to base `screening` (PHQ-2/9, GAD-2/7, text_only).
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; AASM PDFs
  extracted with `pdftotext` into the session scratchpad, no copy kept in the repo). Before sign-off
  each fragment MUST be re-checked against the primary text and committed as a verbatim snapshot with
  `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule stays
  `status: draft_needs_source`.
- **Copyright:** questions are written in our own words; sources are quoted as short fragments only.
- This file does **not** edit `packages/protocols/specialty/uyku_poliklinigi.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### U-S1 — TND, "Uyku Tıbbı" (Türkiye)
- **guideline_id (proposed):** `TND-HALK-UYKU-TIBBI` (lay page, NOT a guideline) · **Date:** none shown
- **Publishing body:** Türk Nöroloji Derneği · **URL:** https://noroloji.org.tr/menu/98/uyku-tibbi ·
  **retrieved_on:** 2026-09-26
- **Verbatim fragments:**
  > "Uykuya dalamama, uykuyu sürdürememe ya da sabah erken uyanıp tekrar uykuya dalamama şikayetleri uykusuzluk hastalığının (insomni) bulguları olabilir."
  > "En sık belirtisi uykuda azalma-artış ile seyreden şiddetli horlama ve aralarda kesintilerin (tanıklı apne) olmasıdır."
  > "Gün içinde de uykulu hisseder, dikkatini yoğunlaştıramaz ve bu durum trafik ve iş kazalarının yaşanmasına neden olur."
  > "Hastalar geceleri dayanılmaz şekilde bacaklarını hareket ettirme isteği duyarlar."
  > "Hareketsiz şekilde oturmak ve yatmak bacaklardaki bu hoş olmayan hisleri artırır. Bacakları hareket ettirmek ve germek ise yakınmaları geçici ve kısa bir süre için azaltır."
  > "yatak içinde oturma etrafa bakma, garip hareketler yapma, bağırma, çığlık atma ve vurma gibi pek çok şekilde ortaya çıkabilir"
  > "Bu da hastaların hem kendisine hem de yakınlarına zarar verebilir."
  > "Vardiyalı çalışma saatleri de uykusuzluğa neden olabilir."
  > "Uykusuzluk şikayetleri bir aydan daha uzun süredir devam ediyor ise ve günlük işlevleri bozuyorsa uyku bozuklukları ile ilgilenen bir hekime başvurmak gerekir." (duration stays in the source; `sikayet_suresi` captures duration)
- **Confidence: MEDIUM** — Turkish society, undated lay page; sentences returned by the fetch in
  sections, re-check order and completeness on the live page.

### U-S2 — TTD, "Uykuda Solunum Bozuklukları" (Türkiye)
- **guideline_id (proposed):** `TTD-HASTA-UYKU-APNE` (same page as `gogus_hastaliklari.md` GH-S5) · **Date:** none shown
- **URL:** https://toraks.org.tr/bilgilendirici-kaynaklar/hastaliklar/uykuda-solunum-bozukluklari · **retrieved_on:** 2026-09-26
- **Verbatim fragments:**
  > "yorgun uyanma ve gündüz aşırı uykululuk gözlenir" · "sabah baş ağrısı" · "sık idrar yapma, idrar kaçırma"
  > "ağız kuruluğu" · "yaptığı işe kendini verememe, unutkanlık, sinirlilik"
  > "gündüz aşırı uyuklaması olanların tedavi başlayana kadar araba kullanmamaları"
- **Confidence: LOW–MEDIUM** — undated lay page; fragments only.

### U-S3 — AASM, Clinical Guideline for the Evaluation and Management of Chronic Insomnia in Adults (international)
- **guideline_id (proposed):** `AASM-INSOMNIA-EVAL-2008`
- **Citation:** Schutte-Rodin S, Broch L, Buysse D, Dorsey C, Sateia M. *J Clin Sleep Med* 2008;4(5):487-504.
- **URL:** https://aasm.org/resources/clinicalguidelines/040515.pdf (bundled behind an AASM notice dated
  February 2017 about the separate pharmacologic guideline, Sateia MJ et al., *J Clin Sleep Med.*
  2017;13(2):307–349, which is about treatment and is not used here)
- **Verbatim fragments:**
  > "The sleep history should cover specific insomnia complaints, pre-sleep conditions, sleep-wake patterns, other sleep-related symptoms, and daytime consequences."
  > "A complaint of difficulty initiating sleep, difficulty maintaining sleep, or waking up too early, or sleep that is chronically nonrestorative or poor in quality."
  > "At least one of the following forms of daytime impairment related to the nighttime sleep difficulty is reported by the patient:"
  > "Patient and bed partner reports may also help to identify nocturnal signs, symptoms and behaviors associated with breathing-related sleep disorders (snoring, gasping, coughing), sleep related movement disorders (kicking, restlessness), parasomnias (behaviors or vocalization)"
  > "risk factors for insomnia include increasing age, female sex, comorbid (medical, psychiatric, sleep, and substance use) disorders, shift work"
  > "Proneness for errors/accidents at work or while driving;"
- **Confidence: MEDIUM–HIGH** — society guideline, but 2008; confirm it is still AASM's current
  evaluation guidance on sign-off.

### U-S4 — AASM, Clinical Practice Guideline for Diagnostic Testing for Adult Obstructive Sleep Apnea (international)
- **guideline_id (proposed):** `AASM-OSA-DX-2017`
- **Citation:** Kapur VK, Auckley DH, Chowdhuri S, et al. *J Clin Sleep Med.* 2017;13(3):479–504.
  DOI 10.5664/jcsm.6506
- **URL:** https://aasm.org/resources/clinicalguidelines/diagnostic-testing-osa.pdf · **retrieved_on:** 2026-09-26
- **Verbatim fragments:**
  > "The examiner should pay particular attention to observations regarding snoring, witnessed apneas, nocturnal choking or gasping, restlessness, and excessive sleepiness."
  > "(e.g., unrefreshing sleep, daytime sleepiness, fatigue or insomnia, awakening with a gasping or choking sensation, loud snoring, or witnessed apneas)"
  > "It is also important that other aspects of a sleep history be collected, as many patients suffer from more than one sleep disorder"
- **Note:** the same guideline states that questionnaires alone lack sufficient diagnostic accuracy;
  nothing here scores or classifies. **Confidence: HIGH.**

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Difficulty falling asleep | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Difficulty returning to sleep after waking | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Early-morning waking | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Daytime impact of poor sleep | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred; no functional-status archetype in the OPT — §4 |
| Q6 | Falling asleep unintentionally in the day | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Loud snoring reported by others | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Witnessed breathing pauses | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Waking with choking or gasping | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Evening urge to move the legs | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Relief of leg urge with movement | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Shouting or limb movements in sleep reported by others | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q13 | Night or shift work | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; social history has no root in the OPT — §4 |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Sleep-clinic alarm | Source | base item | This proposal's role |
|---|---|---|---|
| Sleepiness while driving | U-S1 ("trafik ve iş kazalarının"), U-S2 ("araba kullanmamaları"), U-S3 | **absent** from base.life_threat | **Not asked here**; Q6 captures daytime sleepiness in general |
| Night-time breathlessness or chest pain | general | `rf.dyspnoea_rest`, `rf.chest_pain_*` | **Not asked here** |
| Injury to self or bed partner during sleep behaviours | U-S1 ("hem kendisine hem de yakınlarına zarar verebilir") | **absent** | **Not asked here**; Q12 captures presence only |
| Thoughts of self-harm with insomnia | general | `rf.crisis_disclosure_signposting`; `rf_suicidal_*` probes | **Not asked here**; base owns it |
| Sudden sleep attacks with falls or collapse | **NO SOURCE FOUND (verbatim)** | **absent** | **Not asked here** |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Excessive sleepiness in a driver | "gündüz aşırı uyuklaması olanların tedavi başlayana kadar araba kullanmamaları" · "Proneness for errors/accidents at work or while driving" | U-S2; U-S3 |
| Accidents from daytime sleepiness | "trafik ve iş kazalarının yaşanmasına neden olur" | U-S1 |
| Injurious night-time behaviour | "hem kendisine hem de yakınlarına zarar verebilir" | U-S1 |
| Occupational driving / safety-critical work | **NO SOURCE FOUND (Turkish licensing rule not retrieved)** | clinician / legal must supply |

---

## 3. Candidate B1 Turkish pre-visit questions (13)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE —
clinician to approve wording.** No item carries a triage level; items may at most feed a
`candidate_flag` (max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Duration is
captured by the pack's `sikayet_suresi` slot, so U-S1's duration wording stays out of patient copy.
Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün uyku polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Difficulty falling asleep** · archetype: `OBSERVATION.symptom_sign.v1` · source: U-S1 ("Uykuya dalamama"), U-S3 ("difficulty initiating sleep")
> "Geceleri uykuya dalmakta zorlanıyor musunuz?"
gen: slot=uykuya_dalma_guclugu; type=boolean; follow_up=Yattıktan sonra uykuya dalmanız uzun sürüyor mu?
CANDIDATE — clinician to approve wording. No minutes threshold in patient copy.

**Q3 — Difficulty returning to sleep after waking** · archetype: `OBSERVATION.symptom_sign.v1` · source: U-S1 ("uykuyu sürdürememe"), U-S3 ("difficulty maintaining sleep")
> "Gece uyandıktan sonra yeniden uyumakta zorlandığınız oluyor mu?"
gen: slot=gece_uyanip_uyuyamama; type=boolean; follow_up=Gece uyanınca bir daha uykuya dalmanız zor oluyor mu?
CANDIDATE — clinician to approve wording.

**Q4 — Early-morning waking** · archetype: `OBSERVATION.symptom_sign.v1` · source: U-S1 ("sabah erken uyanıp tekrar uykuya dalamama"), U-S3 ("waking up too early")
> "Sabah istediğinizden çok erken uyanıp bir daha uyuyamadığınız oluyor mu?"
gen: slot=erken_uyanma; type=boolean; follow_up=Sabahları erkenden uyanıp yatakta uyanık kaldığınız oluyor mu?
CANDIDATE — clinician to approve wording.

**Q5 — Daytime impact of poor sleep** · archetype: `OBSERVATION.story.v1` · source: U-S1 ("günlük işlevleri bozuyorsa"), U-S3 ("daytime impairment"), U-S2 ("yaptığı işe kendini verememe")
> "Uykunuzdaki bu sorun gündüz işlerinizi yapmanızı zorlaştırıyor mu?"
gen: slot=gunduz_islev_etkisi; type=boolean; follow_up=Kötü uyuduğunuz günlerde gün içinde kendinizi yorgun hissediyor musunuz?
CANDIDATE — clinician to approve wording. Not an item of any insomnia severity scale.

**Q6 — Falling asleep unintentionally in the day** · archetype: `OBSERVATION.symptom_sign.v1` · source: U-S2 ("gündüz aşırı uykululuk"), U-S4 ("excessive sleepiness"), U-S1
> "Gün içinde istemediğiniz anlarda uyuyakaldığınız oluyor mu?"
gen: slot=gunduz_uyuklama; type=boolean; follow_up=Gündüz uyanık kalmakta zorlanıyor musunuz?
CANDIDATE — clinician to approve wording. Deliberately names no situation, so no Epworth item is
paraphrased; sleepiness while driving is §2.2.

**Q7 — Loud snoring reported by others** · archetype: `OBSERVATION.symptom_sign.v1` · source: U-S1 ("şiddetli horlama"), U-S3 ("bed partner reports"), U-S4 ("loud snoring")
> "Size uykuda yüksek sesle horladığınızı söyleyen oldu mu?"
gen: slot=yuksek_sesle_horlama; type=boolean; follow_up=Birlikte kaldığınız kişi horlamanızdan şikâyet ediyor mu?
CANDIDATE — clinician to approve wording.

**Q8 — Witnessed breathing pauses** · archetype: `OBSERVATION.symptom_sign.v1` · source: U-S1 ("aralarda kesintilerin (tanıklı apne)"), U-S4 ("witnessed apneas")
> "Uyurken nefesinizin durduğunu fark eden biri oldu mu?"
gen: slot=tanikli_apne; type=boolean; follow_up=Uykuda nefesinizin bir süre kesildiğini söyleyen oldu mu?
CANDIDATE — clinician to approve wording. Presence only; no count or duration asked.

**Q9 — Waking with choking or gasping** · archetype: `OBSERVATION.symptom_sign.v1` · source: U-S4 ("awakening with a gasping or choking sensation"), U-S3 ("gasping")
> "Uykudan boğulur gibi ya da nefes nefese uyandığınız oluyor mu?"
gen: slot=bogulma_hissiyle_uyanma; type=boolean; follow_up=Gece nefesiniz kesilmiş gibi hissederek uyandığınız oluyor mu?
CANDIDATE — clinician to approve wording.

**Q10 — Evening urge to move the legs** · archetype: `OBSERVATION.symptom_sign.v1` · source: U-S1 ("geceleri dayanılmaz şekilde bacaklarını hareket ettirme isteği"; "Hareketsiz şekilde oturmak ve yatmak … artırır"), U-S3 ("restlessness")
> "Akşamları otururken ya da yatarken bacaklarınızı hareket ettirme isteği duyuyor musunuz?"
gen: slot=bacaklarda_huzursuzluk; type=boolean; follow_up=Dinlenirken bacaklarınızda rahatsız edici bir his oluyor mu?
CANDIDATE — clinician to approve wording.

**Q11 — Relief of leg urge with movement** · archetype: `OBSERVATION.symptom_sign.v1` · source: U-S1 ("Bacakları hareket ettirmek ve germek ise yakınmaları … azaltır")
> "Bu his bacaklarınızı hareket ettirince ya da yürüyünce azalıyor mu?"
gen: slot=hareketle_rahatlama; type=boolean; ask_if=bacaklarda_huzursuzluk == true; follow_up=Kalkıp yürüdüğünüzde bacaklarınız rahatlıyor mu?
CANDIDATE — clinician to approve wording. Asked only when Q10 is yes.

**Q12 — Shouting or limb movements in sleep reported by others** · archetype: `OBSERVATION.symptom_sign.v1` · source: U-S1 ("garip hareketler yapma, bağırma, çığlık atma ve vurma"), U-S3 ("parasomnias (behaviors or vocalization)")
> "Uykunuzda bağırdığınızı ya da kol ve bacaklarınızı savurduğunuzu söyleyen oldu mu?"
gen: slot=uykuda_hareket_davranis; type=boolean; follow_up=Uyurken garip hareketler yaptığınızı gören oldu mu?
CANDIDATE — clinician to approve wording. Injury during these episodes is §2.3, not asked here.

**Q13 — Night or shift work** · archetype: `OBSERVATION.story.v1` · source: U-S1 ("Vardiyalı çalışma saatleri de uykusuzluğa neden olabilir."), U-S3 ("shift work")
> "Gece ya da vardiyalı bir işte çalışıyor musunuz?"
gen: slot=vardiyali_calisma; type=boolean; follow_up=İş saatleriniz gece ile gündüz arasında değişiyor mu?
CANDIDATE — clinician to approve wording. Complements base `occupation`; does not repeat it.

*(13 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish sleep-medicine guideline** (TUTD or T.C. Sağlık Bakanlığı) — the TUTD site
   (https://www.tutd.org.tr/, https://tutd.org.tr/hastaliklar) returned navigation only; no disease
   text was retrieved. **NO SOURCE FOUND — clinician must supply** the current versioned source.
2. **Currency of U-S3** — the 2008 AASM evaluation guideline; confirm no newer AASM evaluation
   guidance supersedes it. The 2017 and 2021 AASM insomnia guidelines are about treatment.
3. **Driving and occupational licensing** for sleepy drivers in Türkiye — **NO SOURCE FOUND**; §2.3
   candidate only. **Clinician + legal to decide** whether and how the pack may ask about driving.
4. **Narcolepsy features** (sudden muscle weakness with emotion, sleep paralysis, dream-like images at
   sleep onset) — U-S1 names narcolepsy but the fetch returned no symptom text beyond sleep attacks.
   **NO SOURCE FOUND (verbatim) — not drafted.**
5. **Sourced but not drafted (to stay near twelve):** morning headache, dry mouth, night-time urination
   (U-S2). Clinician may swap them in.
6. **Validated instruments** (Epworth, STOP-Bang, Berlin, PSQI, ISI, sleep diary) — not drafted; licence
   status not verified here. **Instrument engine (INT-116) + licence gate decide.**
7. **Children seen in the sleep clinic** — items are adult-worded; paediatric wording and proxy variants
   need a paediatrician (HB-C1). **Not drafted.**
8. **Social history archetype** for shift work (Q13) — none in the OPT; narrative only (INT-032).
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words, no
  diagnosis/treatment/prognosis wording; each draft marked CANDIDATE. Every ask and follow-up was run
  through the Turkish PolicyGuard `inspect_sentence` arms with zero findings.
- **Inv. 7** — drowsy driving, night-time breathlessness, injurious sleep behaviour and self-harm left
  to base / physician (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 20** — no questionnaire accuracy figure reproduced.
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question; source durations stay in §1.
- **Clinical content rule** — no instrument item reproduced or paraphrased; every red-flag needs a
  committed verbatim snapshot, until then `status: draft_needs_source`. Sources U-S1…U-S4 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
