# Nükleer Tıp (Nuclear Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Nükleer Tıp (Nuclear Medicine)
Taxonomy id: `nukleer_tip` (branches.yaml — cluster `medical`; files/09 §1 "Nükleer Tıp (konsültasyon)").
Purpose: patient-owned, Turkish-first **pre-visit intake** (history and safety capture for a
clinician-ready note before imaging or radionuclide therapy) — **not** diagnosis, not triage authority.
This file is a *proposal for a clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN
level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  short verbatim fragment + citation). Where no source was found, the row reads **"NO SOURCE FOUND —
  clinician must supply"**. Nothing was invented.
- **Turkish first:** all three primary sources are from the **Türkiye Nükleer Tıp Derneği (TSNM/TNTD)**:
  the 2020 F-18 FDG PET/BT oncology guideline (a versioned, peer-published society guideline), the
  2015 I-131 hyperthyroidism therapy guideline v2.0, and the society's public "Radyoiyot (Atom)" page.
  No international source was needed for the drafted items.
- **Scope:** a nuclear-medicine visit is mostly *preparation and safety* (glucose, lactation, recent
  contrast, prior treatment, ability to lie still, contamination and household exposure). Questions are
  therefore history items, not symptom hunts.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level; no level is asserted. Several items are **procedure-safety flags for the
  nuclear-medicine team**, not patient emergencies (§2.3).
- **Invariant 7:** low blood sugar in a fasting patient with diabetes, myelosuppression after
  radionuclide therapy (neutropenic fever) and spinal cord compression in patients with bone disease are
  **`base.life_threat` / physician territory** (§2.2). None is asked here.
- **Base overlap avoided:** pregnancy status, medications (including insulin and thyroid drugs),
  allergies (including contrast allergy), immunosuppression, smoking and weight are collected by
  `packages/protocols/base/intake.yaml` and are **not** repeated. Lactation is **not** in base and is
  asked here (Q3).
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; the FDG
  guideline PDF extracted locally with `pdftotext`, no copy kept in the repo). NT-S2 fragments were
  returned with ellipses by the fetch and must be re-read in full. Before sign-off each fragment MUST be
  re-checked against the primary text and committed as a verbatim snapshot with `source:
  {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule stays
  `status: draft_needs_source`.
- **Copyright:** questions are written in our own words; sources are quoted as short fragments only.
- This file does **not** edit `packages/protocols/specialty/nukleer_tip.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### NT-S1 — TSNM, "F-18 FDG PET/BT Onkolojik Uygulama Kılavuzu" (Türkiye)
- **guideline_id (proposed):** `TSNM-FDG-PETBT-ONKOLOJI-2020`
- **Citation:** Soydal Ç, Burak Z, Uçmak G, Bozkurt MF, Atasever T, Demirci E, Ak Sivrikoz İ.
  *Nucl Med Semin.* 2020;6:339-357. DOI 10.4274/nts.galenos.2020.0028 · © 2020 Türkiye Nükleer Tıp Derneği
- **URL:** https://tsnm.org/dosyalar/kilavuzlar/2020-0028.pdf · **retrieved_on:** 2026-09-26
- **Verbatim fragments (Anamnez; Hasta Hazırlığı ve Önlemler):**
  > "Onkolojik öykü ve ilişkili komorbiteler (enfeksiyon/enflamasyon, diyabet)"
  > "Yakın zamanda varsa travma öyküsü"
  > "en son kemoterapi tarihi, cerrahi girişim geçirmiş ise tarihi, radyoterapi almış ise tarihi randevu öncesinde bilinmelidir."
  > "PET/BT öncesinde 24-48 saat içinde iv kontrast ajan kullanıldı ise not edilmeli"
  > "emziren kadınlarda meme dokusu F-18 FDG tutulumu gösterdiği için anne ve bebeğin yakın temasının 12 saat süre ile kesilmesi"
  > "Hasta PET/BT çekim süresi boyunca (20-45 dk) sırt üstü yatabiliyor olmalıdır."
  > "olası klostrofobisinin sorgulanması, tanısal olmayan çalışmaları ve tetkik iptallerini azaltacak"
- **Confidence: HIGH** for provenance (versioned society guideline, primary PDF). Numbers above stay in
  this section only and never enter patient copy (invariant 22).

### NT-S2 — TNTD, "I-131 ile Hipertiroidizm Tedavi Uygulama Kılavuzu 2.0" (Türkiye)
- **guideline_id (proposed):** `TNTD-I131-HIPERTIROIDI-2.0-2015`
- **Citation:** Özdoğan Ö, Töre G, Özkılıç H, Kır M, Yüksel D. *Nucl Med Semin.* 2015;1(1):44-49.
  DOI 10.4274/nts.2015.009 · **Version:** 2.0 (March 2015)
- **URL:** https://nukleertipseminerleri.org/tr/makaleler/tntd-i-131-ile-hipertiroidizm-tedavi-uygulama-kilavuzu-20/doi/nts.2015.009
- **Verbatim fragments (as returned by the fetch):**
  > "İnkontinansı olan hastalar tedavi öncesi değerlendirilmeli ve radyasyon güvenliği yönünden gerekli ek önlemler alınmalıdır"
  > "Hastalara tedavi öncesi çocukların ve diğer aile fertlerinin radyasyondan korunmasıyla ilgili gerekli bilgiler verilmelidir"
  > "İyot içeren tüm ilaç … kontrast madde … I-131 tutulumunu değişik sürelerle engelleyebilirler."
- **Confidence: MEDIUM** — versioned society guideline, but fragments came back abridged; re-read full text.

### NT-S3 — TSNM, "Radyoiyot (Atom)" (public information page)
- **guideline_id (proposed):** `TSNM-HALK-RADYOIYOT` (lay page, NOT a guideline) · **Date:** none shown
- **URL:** https://tsnm.org/en/halkimiza-yonelik/radyoiyot-atom/
- **Verbatim fragments:**
  > "Emziren annelere ancak emzirmeyi kestikten sonra radyoiyod tedavisi uygulanabilir."
  > "İçerisinde iyod olan tüm yiyecek, içecek ve ilaçlar tedaviden önce kesilmelidir."
  > "Özellikle bebeklere, küçük çocuklara ve hamilelere … yakın ve uzun süre birlikte olunmamalı onları öpmemelidir."
- **Confidence: MEDIUM** — Turkish society, undated lay page. The distance figure is omitted here.

### NT-S4 — TSNM guideline index (inventory only)
- **URL:** https://tsnm.org/en/uygulama-kilavuzlari/ · lists 2020 and 2024 guidelines (FDG PET/BT, PSMA,
  Lu-177 PSMA, PRRT, Y-90, cardiac, sentinel node, paediatric). The current index shows **no**
  radioiodine-therapy, thyroid-scintigraphy or bone-scintigraphy guideline (§4 gap 1).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Known diabetes | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q3 | Currently breastfeeding | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no lactation archetype in the OPT — §4 |
| Q4 | Recent contrast-enhanced scan | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no procedure-history archetype — §4 |
| Q5 | Previous radioactive iodine therapy | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; as Q4 |
| Q6 | Previous radiotherapy | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; as Q4 |
| Q7 | Recent surgery or needle biopsy | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; as Q4 |
| Q8 | Recent fall, blow or fracture | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q9 | Difficulty lying flat and still | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q10 | Distress in closed spaces | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q11 | Urinary leakage | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Young children or pregnant person at home | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; social context only |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm | Source | base item | This proposal's role |
|---|---|---|---|
| Low blood sugar in a fasting patient on insulin before PET | NT-S1 discusses insulin timing; hypoglycaemia urgency wording **NO SOURCE FOUND (verbatim)** | **absent** | Q2 is a preparation input only; insulin itself is in base medications |
| Fever after radionuclide therapy (myelosuppression) | `tibbi_onkoloji.md` TO-S1 (**SECONDARY**); TSNM Lu-177 PSMA / PRRT guidelines identified, not quoted | neutropenic fever (six-rule list) | **Not asked here** |
| New back pain with leg weakness in bone disease (spinal cord compression) | **NO SOURCE FOUND (verbatim)** | **absent** | **Not asked here**; Q8 is recent trauma for image reading only |
| Pregnancy before a radionuclide | NT-S1 "Gebelik" section; NT-S3 | base `pregnancy_status` collects it | **Not asked here** |

### 2.3 Red-flag candidates — for physician review — NOT encoded

These are **procedure-safety flags** for the nuclear-medicine team, not emergencies. No level, route,
register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Breastfeeding before FDG or radioiodine | "Emziren annelere ancak emzirmeyi kestikten sonra radyoiyod tedavisi uygulanabilir." | NT-S3; NT-S1 |
| Recent iodinated contrast before radioiodine or PET | "iv kontrast ajan kullanıldı ise not edilmeli" | NT-S1; NT-S2 |
| Urinary incontinence before radionuclide therapy | "İnkontinansı olan hastalar tedavi öncesi değerlendirilmeli" | NT-S2 |
| Young children or pregnant people at home after radioiodine | "çocukların ve diğer aile fertlerinin radyasyondan korunmasıyla ilgili gerekli bilgiler verilmelidir" | NT-S2; NT-S3 |
| Hypoglycaemia, myelosuppression, spinal cord compression | **NO SOURCE FOUND (verbatim)** | clinician must supply |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Q1 binds to the pack's
`basvuru_nedeni` slot. Hours, days and weeks from the guidelines are **not** placed in patient copy;
"son haftalarda / son aylarda" is used instead and the exact interval is the team's call. Each draft was
run through the Turkish PolicyGuard `inspect_sentence` arms (INT-248 lexicon) with zero findings.
Duration: no pack line is set here. The duration ask override is pending clinician wording: no source
supports a duration question for a scan or therapy visit, so the fixed `sikayet_suresi` ask stays until
a clinician words one or the generator lets the slot be left out (wave-7 verification §E-2).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün nükleer tıp polikliniğine gelme nedeniniz nedir?"
CANDIDATE — clinician to approve wording. Ends in "nedir?" so the neutral reason follow-up is used, not
one that says "şikâyetiniz".

**Q2 — Known diabetes** · archetype: `EVALUATION.problem_diagnosis.v1` · source: NT-S1 ("komorbiteler (enfeksiyon/enflamasyon, diyabet)")
> "Size daha önce şeker hastalığı tanısı konuldu mu?"
gen: slot=diyabet_tanisi; type=boolean; follow_up=Kan şekerinizin yüksek olduğu size söylendi mi?
CANDIDATE — clinician to approve wording. Preparation input; insulin and tablets come from base medications.

**Q3 — Currently breastfeeding** · archetype: `OBSERVATION.story.v1` · source: NT-S1 (Emzirme section), NT-S3 ("Emziren annelere ancak emzirmeyi kestikten sonra")
> "Şu anda emziriyor musunuz?"
gen: slot=emzirme; type=boolean; follow_up=Şu anda bir bebeği anne sütüyle besliyor musunuz?; delivery=text_first
CANDIDATE — clinician to approve wording. Asked of every patient; clinician may add a sex/age gate (§4 gap 5).
No longer presumes a baby ("bebeğinizi"). Lactation is reproductive history, so `text_first`.

**Q4 — Recent contrast-enhanced scan** · archetype: `OBSERVATION.story.v1` · source: NT-S1 ("iv kontrast ajan kullanıldı ise not edilmeli"), NT-S2 ("kontrast madde … I-131 tutulumunu … engelleyebilirler"), NT-S3
> "Son haftalarda damardan ilaç verilerek tomografi ya da başka bir film çekildi mi?"
gen: slot=yakin_kontrastli_cekim; type=boolean; follow_up=Son zamanlarda ilaçlı tomografi çektirdiniz mi?
CANDIDATE — clinician to approve wording. "İlaçlı film" is the common lay term for a contrast study.

**Q5 — Previous radioactive iodine therapy** · archetype: `OBSERVATION.story.v1` · source: NT-S3 (page title "Radyoiyot (Atom)"), NT-S2
> "Daha önce atom tedavisi olarak bilinen radyoaktif iyot tedavisi aldınız mı?"
gen: slot=onceki_radyoiyot; type=boolean; follow_up=Daha önce atom tedavisi aldınız mı?
CANDIDATE — clinician to approve wording. History item; activity and dates come from records.

**Q6 — Previous radiotherapy** · archetype: `OBSERVATION.story.v1` · source: NT-S1 ("radyoterapi almış ise tarihi randevu öncesinde bilinmelidir")
> "Daha önce vücudunuzun herhangi bir bölgesine ışın tedavisi uygulandı mı?"
gen: slot=onceki_isin_tedavisi; type=boolean; follow_up=Daha önce radyoterapi aldınız mı?
CANDIDATE — clinician to approve wording. The date is a clinician/record follow-up (§4 gap 4).

**Q7 — Recent surgery or needle biopsy** · archetype: `OBSERVATION.story.v1` · source: NT-S1 ("cerrahi girişim geçirmiş ise tarihi")
> "Son aylarda ameliyat ya da iğneyle parça alma işlemi oldunuz mu?"
gen: slot=yakin_ameliyat_biyopsi; type=boolean; follow_up=Yakın zamanda biyopsi yaptırdınız mı?
CANDIDATE — clinician to approve wording.

**Q8 — Recent fall, blow or fracture** · archetype: `OBSERVATION.story.v1` · source: NT-S1 ("Yakın zamanda varsa travma öyküsü")
> "Son zamanlarda düşme, darbe ya da kemik kırığı yaşadınız mı?"
gen: slot=yakin_travma; type=boolean; follow_up=Yakın zamanda bir yerinizi incittiniz mi?
CANDIDATE — clinician to approve wording. Image-reading context only; not an injury triage question.

**Q9 — Difficulty lying flat and still** · archetype: `OBSERVATION.story.v1` · source: NT-S1 ("sırt üstü yatabiliyor olmalıdır")
> "Bir süre sırtüstü ve hareketsiz yatmak sizin için zor olur mu?"
gen: slot=hareketsiz_yatma_zorlugu; type=boolean; follow_up=Sırtüstü yatınca ağrı ya da nefes darlığı oluyor mu?
CANDIDATE — clinician to approve wording. Same text and slot as radyasyon_onkolojisi Q6; the ask and the
follow-up now share one polarity ("evet" means difficulty).

**Q10 — Distress in closed spaces** · archetype: `OBSERVATION.story.v1` · source: NT-S1 ("olası klostrofobisinin sorgulanması")
> "Kapalı ya da dar alanlarda bulunmak sizi çok huzursuz eder mi?"
gen: slot=kapali_alan_huzursuzluk; type=boolean; follow_up=Dar ve kapalı yerlerde bunaldığınız olur mu?
CANDIDATE — clinician to approve wording.

**Q11 — Urinary leakage** · archetype: `OBSERVATION.symptom_sign.v1` · source: NT-S2 ("İnkontinansı olan hastalar tedavi öncesi değerlendirilmeli")
> "İdrarınızı tutmakta zorlandığınız ya da kaçırdığınız oluyor mu?"
gen: slot=idrar_kacirma; type=boolean; follow_up=Tuvalete yetişemediğiniz oluyor mu?
CANDIDATE — clinician to approve wording. Radiation-safety planning input.

**Q12 — Young children or a pregnant person at home** · archetype: `OBSERVATION.story.v1` · source: NT-S2 ("çocukların ve diğer aile fertlerinin radyasyondan korunması"), NT-S3 ("bebeklere, küçük çocuklara ve hamilelere")
> "Evinizde küçük çocuk ya da gebe biri yaşıyor mu?"
gen: slot=evde_cocuk_gebe; type=boolean; follow_up=Evde bakımını üstlendiğiniz bir bebek ya da küçük çocuk var mı?; delivery=text_first
CANDIDATE — clinician to approve wording. Complements base `living_situation`; captures no identities.
Household data, including a household member's pregnancy, so `text_first`. invariant 18: owner-approved
2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Radioiodine therapy for thyroid cancer, thyroid scintigraphy and bone scintigraphy** — the current
   TSNM guideline index (NT-S4) lists none; older TSNM versions were not located. SNMMI/EANM
   differentiated-thyroid-cancer (2022) and EANM benign-thyroid (2010) guidelines were **identified but
   not quoted**. **Clinician must select and snapshot.**
2. **Hypoglycaemia risk in fasting patients with diabetes** — NT-S1 covers insulin timing, but urgency
   wording **NO SOURCE FOUND (verbatim)**; not drafted.
3. **Lu-177 PSMA, PRRT and Y-90 therapy intake** (TSNM 2020 guidelines 0031, 0033, 0034) — identified,
   not retrieved; therapy-specific items (for example kidney or blood-count history) are not drafted.
4. **Dates of last chemotherapy, radiotherapy and surgery** — NT-S1 requires them; only booleans are
   drafted (Q6, Q7) because chemotherapy overlaps base `immunosuppression` and dates come from records.
5. **Sex/age gating of Q3** — not drafted; clinician decides whether to gate lactation.
6. **Iodine-rich diet and supplements before radioiodine** (NT-S3) — preparation *instruction*, not an
   intake question; supplements are already in base `otc_herbal`. Not drafted.
7. **Procedure, lactation and household items** — no matching archetypes in the OPT; bound to
   `OBSERVATION.story.v1` as narrative only (INT-032 decision needed).
8. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (route × register × location, invariant 21) are
   **deliberately unassigned**.
9. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE and checked against the Turkish PolicyGuard arms.
- **Inv. 7** — hypoglycaemia, myelosuppression and spinal cord compression left to base / physician (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 8).
- **Inv. 22** — no numerals in any candidate question; the guideline's hours, minutes and distances stay in §1.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources NT-S1…NT-S4 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
