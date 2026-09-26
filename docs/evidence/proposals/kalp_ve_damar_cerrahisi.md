# Kalp ve Damar Cerrahisi (Cardiovascular Surgery) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Kalp ve Damar Cerrahisi (Cardiovascular Surgery)
Taxonomy id: `kalp_ve_damar_cerrahisi` (branches.yaml — cluster `surgical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation), or is explicitly marked **SECONDARY** (quoted from a sibling proposal, not
  re-retrieved here). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Turkish first:** the primary source is a **versioned Turkish national guideline** — *Periferik Arter
  ve Ven Hastalıkları Ulusal Tedavi Kılavuzu 2021* of the Türk Kalp ve Damar Cerrahisi Derneği (TKDCD),
  Ulusal Vasküler ve Endovasküler Cerrahi Derneği and Fleboloji Derneği — retrieved as PDF and read
  locally. It is a clinician guideline, so NHS patient pages are cited for lay wording. **No Turkish
  source was found for the cardiac-surgery (valve / bypass) items** (§4 gap 2).
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7:** acute limb ischaemia, ruptured aortic aneurysm, pulmonary embolism after DVT,
  TIA/stroke from carotid disease and aortic dissection are **`base.life_threat` / base red-flag
  territory** (§2.2). This proposal does not add to or extend `base.life_threat`; related questions are
  **gate inputs only**.
- **Verification caveat (every quote in §1):** TKDCD text extracted locally with `pdftotext`; NHS text
  via WebFetch. Before sign-off each sentence MUST be re-checked against the primary text and committed
  as a verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`. Until then any
  derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/kalp_ve_damar_cerrahisi.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### KVC-S1 — TKDCD / UVEC / Fleboloji Derneği, *Periferik Arter ve Ven Hastalıkları Ulusal Tedavi Kılavuzu 2021* (Türkiye)
- **guideline_id (proposed):** `TKDCD-PAVH-UTK-2021`
- **Publishing body:** Türk Kalp Damar Cerrahisi Derneği, Ulusal Vasküler ve Endovasküler Cerrahi
  Derneği, Fleboloji Derneği · **Editor:** Prof. Dr. A. Kürşat Bozkurt · **Version/date:** 2021, printed
  Nisan 2021 · ISBN 978-605-69205-2-3 (first edition 2016)
- **URL:** https://www.tkdcd.org/uploads/content/pdf/kilavuzlar/Ulusal_Tedavi_Kilavuzu_2021.pdf
  (announcement: https://www.tkdcd.org/icerik/tkdcd-duyurulari-2/periferik-arter-ve-ven-hastaliklari-ulusal-tedavi-kilavuzu-2021-887)
- **Verbatim — Tablo A-3, "Baldır aralıklı klodikasyo" row (cells, in reading order):**
  > "Baldır kasları" · "Kramp, ağrı, huzursuzluk" · "Egzersizle artar" · "Hızla kaybolur"
- **Verbatim — III.D Akut bacak iskemisi:**
  > "Akut bacak iskemisi, PAH hastalarında görülebilen, bacağa giden kan akımının ani olarak
  > kesilmesiyle oluşan ve uzuv kaybına kadar gidebilen kritik bir durumdur."
  > "Hastalarda en sık görülen semptomlar istirahat ağrısı (%71.3), solukluk (%10.2), parestezi (%7.5)
  > ve paralizi (%2.4) olmuştur."
  > "Buna göre geçirilmiş alt ekstremite revaskülarizasyonu, önceden atriyal fibrilasyon varlığı …"
- **Verbatim — IV Tarama (PAD presentation):**
  > "Bu durum, hastalarda sıklıkla bacak ağrısıyla kendini gösterir, fakat doğrudan doku kaybı veya
  > gangren kliniğiyle başvuran hastalar olabilmektedir."
- **Verbatim — WIfI table, Yara (W) = 0:** > "Ülser yarası yok (istirahat ağrısı var)"
- **Verbatim — D. AAA, Klinik:**
  > "Abdominal aort anevrizması rüptüre olduğundaki dramatik belirtilerinden önce çoğunlukla sessizdir."
  > "Atipik abdomen veya sırt ağrısı bulunabilir. Fizik muayene sırasında pulsatil abdomen kitlesi
  > farkedilebilir, ancak duyarlılığı zayıftır. Akut abdomen ağrısı ve şok bulguları, rüptüre AAA
  > olgularında görülür."
- **Verbatim — F. Kronik venöz hastalık, Klinik:**
  > "Venöz yetersizliğin klinikte en yaygın görülen şekilleri telenjektazi, retiküler veya variköz
  > venlerdir. Ağrı, şişkinlik hissi, yanma, gece krampları, karıncalanma, kaşıntı, huzursuz bacak,
  > pigmentasyon artışı ve ülsere bağlı yakınmalar görülebilir. Trombofilebit ve kanama daha nadir,
  > ancak ciddi klinik bulgulardır."
  > "Ödem, genellikle ayak bileği etrafında görülüp, ayak veya bacağa kadar uzanmaktadır."
- **Verbatim — G. VTE, Tanı:**
  > "Bacakta veya üst ekstremitede ağrı, şişlik, ödem ve risk faktörleri varlığında şüphelenilmeli ve
  > klinik değerlendirme yapılmalıdır."
- **Verbatim — B. Karotis:** > "Geçici iskemik atak genellikle bir “uyarı inmesi” veya “mini inme”
  olarak tanımlansa da etkileri uzun süreli değildir ve sekel bırakmaz."
- **Confidence: HIGH** for text (primary PDF, Turkish national guideline). Percentages above are source
  text only; none is carried into patient copy or any rule.

### KVC-S2 — NHS, "Peripheral arterial disease (PAD)" (international, patient page)
- **guideline_id (proposed):** `NHS-PAD` · **Last reviewed:** 10 April 2026
- **URL:** https://www.nhs.uk/conditions/peripheral-arterial-disease-pad/
- **Verbatim:**
  > "a painful ache in their legs when they walk, which usually disappears after a few minutes' rest"
  > "ulcers (open sores) on your feet and legs, which do not heal"
  > "If you think you're developing symptoms of CLI, contact a GP immediately."

### KVC-S3 — NHS, "Varicose veins" (international, patient page)
- **guideline_id (proposed):** `NHS-VARICOSE` · **Last reviewed:** 01 July 2024
- **URL:** https://www.nhs.uk/conditions/varicose-veins/
- **Verbatim:**
  > "pain, aching or a feeling of heaviness" · "swollen ankles or legs"
  > "Ask for an urgent GP appointment or get help from NHS 111 if: you have varicose veins that are bleeding"

### KVC-S4 — NHS, "Deep vein thrombosis (DVT)" (international, patient page)
- **guideline_id (proposed):** `NHS-DVT` · **Last reviewed:** 30 April 2026
- **URL:** https://www.nhs.uk/conditions/deep-vein-thrombosis-dvt/
- **Verbatim:**
  > "swelling in 1 leg (rarely both legs)"
  > Call 999 if DVT symptoms and you "feel short of breath" or "have chest pain"

### KVC-S5 — NHS, "Abdominal aortic aneurysm" (international, patient page)
- **guideline_id (proposed):** `NHS-AAA` · **Last reviewed:** 14 June 2023
- **URL:** https://www.nhs.uk/conditions/abdominal-aortic-aneurysm/
- **Verbatim:** > "a pulsing feeling in your tummy" · Call 999: "sudden, severe pain in your tummy or back"

### KVC-S6 — NHS, "Heart valve replacement — Why it's done" (international, patient page)
- **guideline_id (proposed):** `NHS-VALVE-WHY` · **Last reviewed:** 17 July 2025
- **URL:** https://www.nhs.uk/tests-and-treatments/heart-valve-replacement/why-its-done/
- **Verbatim:** > "chest pain, feeling dizzy, shortness of breath, heart palpitations and feeling tired"

### KVC-S7 — NHS, "Coronary artery bypass graft — Risks" (international, patient page)
- **guideline_id (proposed):** `NHS-CABG-RISKS` · **Last reviewed:** 3 July 2025
- **URL:** https://www.nhs.uk/conditions/coronary-artery-bypass-graft-cabg/risks/
- **Verbatim:**
  > "pain or redness around your wound that's getting worse or not getting better"
  > "bleeding or pus from your wound"

### KVC-S8 — ESC 2021 Heart Failure — **SECONDARY**
- Quoted as retrieved in `kardiyoloji.md` S3; **not re-retrieved here**.
  > "a clinical syndrome consisting of cardinal symptoms (e.g. breathlessness, ankle swelling, and fatigue)"

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Walking leg pain relieved by rest | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Foot pain at rest / at night | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Non-healing foot / leg wound | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Visible varicose veins | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Leg heaviness / burning | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Ankle / leg swelling | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | One leg or both | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Pulsing feeling in abdomen | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Exertional breathlessness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Previous heart / vessel surgery or stent | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); no procedure-history archetype — §4 |
| Q12 | Worsening surgical-wound redness / discharge | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

Smoking, medications, anticoagulants and allergies are already collected by
`packages/protocols/base/intake.yaml` (KVC-S1 §V.B lists smoking as a PAD risk factor) and are not repeated.

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm sign | Source | base item | This proposal's role |
|---|---|---|---|
| Acute limb ischaemia (sudden rest pain, pallor, paraesthesia, paralysis) | KVC-S1 III.D | **absent** — "limb ischaemia" is a named missing rule (HB-C2) | Not drafted as a current-symptom question; Q3 is chronic rest pain, gate **input** only |
| Ruptured AAA (sudden severe abdominal / back pain, shock) | KVC-S1 D; KVC-S5 | **absent** | Q9 is a gate **input** only |
| DVT with breathlessness or chest pain (PE) | KVC-S4 | `rf.dyspnoea_rest`, `rf.chest_pain_acute` | Q7/Q8 are gate **inputs** only |
| TIA / stroke (carotid) | KVC-S1 B | `rf.stroke_fast` | Not drafted; base owns it |
| Bleeding varicose vein | KVC-S1 F; KVC-S3 | `rf.severe_bleeding` (named gap) | Not drafted |
| Post-operative wound infection with fever | KVC-S7 | `rf.sepsis_like` (named gap) | Q12 is a gate **input** only |
| Acute aortic dissection | **NO SOURCE retrieved** | `rf.chest_pain_acute` (partial) | Not drafted; §4 gap 5 |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Sudden cold, pale, numb or weak leg | "bacağa giden kan akımının ani olarak kesilmesiyle oluşan ve uzuv kaybına kadar gidebilen kritik bir durumdur" | KVC-S1 III.D |
| Rest pain, non-healing ulcer or gangrene | "doğrudan doku kaybı veya gangren kliniğiyle başvuran hastalar"; "contact a GP immediately" | KVC-S1 IV; KVC-S2 |
| Sudden severe abdominal or back pain in a known/suspected AAA | "Akut abdomen ağrısı ve şok bulguları, rüptüre AAA olgularında görülür." | KVC-S1 D; KVC-S5 |
| One swollen painful leg, especially with breathlessness or chest pain | "swelling in 1 leg"; Call 999 "feel short of breath" | KVC-S4; KVC-S1 G |
| Bleeding varicose vein; thrombophlebitis | "Trombofilebit ve kanama daha nadir, ancak ciddi klinik bulgulardır." | KVC-S1 F; KVC-S3 |
| Transient neurological symptoms | "“uyarı inmesi” veya “mini inme”" | KVC-S1 B |
| Worsening wound redness, pus, fever after heart surgery | "bleeding or pus from your wound" | KVC-S7 |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. No walking distance or duration
threshold appears in patient copy; the pack's `sikayet_suresi` slot captures duration. Q1 binds to the
pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün kalp ve damar cerrahisi polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Walking leg pain relieved by rest** · archetype: `OBSERVATION.symptom_sign.v1` · source: KVC-S1 Tablo A-3 ("Kramp, ağrı, huzursuzluk"; "Egzersizle artar"; "Hızla kaybolur"), KVC-S2
> "Yürürken baldırınızda ya da kalçanızda dinlenince geçen bir ağrı oluyor mu?"
CANDIDATE — clinician to approve wording.

**Q3 — Foot pain at rest (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: KVC-S1 ("istirahat ağrısı"; WIfI "Ülser yarası yok (istirahat ağrısı var)"), KVC-S2
> "Dinlenirken ya da gece yatarken ayağınızda ağrı oluyor mu?"
CANDIDATE — clinician to approve wording. **Overlap: limb ischaemia (§2.2)** if sudden; no level asserted.

**Q4 — Non-healing foot or leg wound (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: KVC-S1 ("doğrudan doku kaybı veya gangren"), KVC-S2 ("ulcers (open sores) on your feet and legs, which do not heal")
> "Ayağınızda ya da bacağınızda uzun süredir iyileşmeyen bir yara var mı?"
CANDIDATE — clinician to approve wording.

**Q5 — Visible varicose veins** · archetype: `OBSERVATION.symptom_sign.v1` · source: KVC-S1 F ("telenjektazi, retiküler veya variköz venlerdir"), KVC-S3
> "Bacaklarınızda kıvrımlı ve şişkin görünen damarlar var mı?"
CANDIDATE — clinician to approve wording.

**Q6 — Leg heaviness or burning** · archetype: `OBSERVATION.symptom_sign.v1` · source: KVC-S1 F ("Ağrı, şişkinlik hissi, yanma, gece krampları"), KVC-S3 ("a feeling of heaviness")
> "Gün sonunda bacaklarınızda ağırlık ya da yanma hissi oluyor mu?"
CANDIDATE — clinician to approve wording.

**Q7 — Ankle or leg swelling (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: KVC-S1 F ("Ödem, genellikle ayak bileği etrafında görülüp"), KVC-S1 G, KVC-S3, KVC-S8
> "Ayak bileklerinizde ya da bacaklarınızda şişlik oluyor mu?"
gen: slot=bacak_sislik; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — One leg only (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: KVC-S4 ("swelling in 1 leg (rarely both legs)"), KVC-S1 G
> "Bu şişlik yalnızca tek bacağınızda mı?"
gen: slot=tek_bacak_sislik; type=boolean; ask_if=bacak_sislik == true
CANDIDATE — clinician to approve wording. Ask only if Q7 is yes. Revised 2026-09-26 per
docs/evidence/verification/specialty-wave1-3.md §C: the earlier either/or ask left "evet" ambiguous in
voice, and there is no enum slot type. **Overlap: DVT / PE (§2.2).**

**Q9 — Pulsing feeling in the abdomen (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: KVC-S1 D ("pulsatil abdomen kitlesi"), KVC-S5 ("a pulsing feeling in your tummy")
> "Karnınızda nabız gibi atan bir his fark ettiniz mi?"
CANDIDATE — clinician to approve wording. **Overlap: ruptured AAA (§2.2)** when with sudden pain.

**Q10 — Exertional breathlessness** · archetype: `OBSERVATION.symptom_sign.v1` · source: KVC-S6 ("shortness of breath"), KVC-S8 ("breathlessness")
> "Yürürken ya da merdiven çıkarken nefesiniz eskisinden daha çabuk daralıyor mu?"
CANDIDATE — clinician to approve wording. Breathlessness at rest belongs to `rf.dyspnoea_rest`.
Turkish source: **NO SOURCE FOUND** (§4 gap 2).

**Q11 — Previous heart or vessel surgery, or stent** · archetype: `OBSERVATION.story.v1` (narrative only) · source: KVC-S1 III.D ("geçirilmiş alt ekstremite revaskülarizasyonu")
> "Daha önce kalp ya da damar ameliyatı veya stent işlemi geçirdiniz mi?"
CANDIDATE — clinician to approve wording. History item; no flag.

**Q12 — Worsening surgical-wound redness or discharge (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: KVC-S7 ("pain or redness around your wound that's getting worse"; "bleeding or pus from your wound")
> "Ameliyat yaranızda giderek artan kızarıklık ya da akıntı var mı?"
gen: hold=belongs to the post_discharge/followup visit-type layer, not the specialty pack (no visit-type variable in ask_if)
CANDIDATE — clinician to approve wording. Intended for `post_discharge` / `followup` visits only.
**HOLD (verification §C):** the committed packs show no visit-type variable in `ask_if`, so this item
is kept out of the specialty pack and belongs in the `post_discharge`/`followup` visit-type layer. **Overlap: `rf.sepsis_like` with fever (§2.2).**

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Acute limb ischaemia rule** — absent from base (HB-C2 names "limb ischaemia"). ESVS 2020 ALI
   guideline returned HTTP 403 (ejves.com); the "six Ps" were seen only in a search summary and are
   **not** quoted. KVC-S1 III.D is the retrieved source. **base.life_threat owner + clinician.**
2. **Cardiac-surgery items in Turkish** (valve symptoms, exertional breathlessness, sternal wound) — no
   TKDCD patient page or guideline found; ESC/EACTS 2021 valvular guideline not retrieved. Q10 and Q12
   rest on NHS pages and a SECONDARY ESC quote. **NO SOURCE FOUND (Turkish) — clinician must supply.**
3. **TKDCD/UVEC/Fleboloji VTE national guideline** (TGKDC, https://tgkdc.dergisi.org/abstract.php?lang=tr&id=3544)
   — located, not read; KVC-S1 §G used instead.
4. **Walking-distance or claudication severity** — no threshold pinned into patient copy; clinician may
   author a follow-up.
5. **Acute aortic dissection / thoracic aortic syndromes** — KVC-S1 §E exists but its presentation text
   was not extracted. **NO SOURCE (verbatim)**; not drafted.
6. **Sourced but not drafted (to stay within twelve):** ankle skin pigmentation / hardening (KVC-S1 C4),
   Raynaud colour change (KVC-S1 III.E.2), known diabetes (KVC-S1 V.C). Clinician may swap them in.
7. **Q11 procedure history** — no procedure-history archetype in the OPT; narrative only (INT-032).
8. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
9. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; Q8 is a single yes/no (formerly either/or); each draft marked CANDIDATE.
- **Inv. 7** — limb ischaemia, ruptured AAA, PE, TIA, bleeding varix and dissection left to base (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 8).
- **Inv. 22** — no numerals in any candidate question; guideline percentages stay in §1 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources KVC-S1…KVC-S8 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
