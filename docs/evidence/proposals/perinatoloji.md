# Perinatoloji (Maternal–fetal medicine / high-risk pregnancy) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Perinatoloji (maternal–fetal medicine)
Taxonomy id: `perinatoloji` (branches.yaml — cluster `womens_health`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (risk-history and symptom capture for a
clinician-ready note) for a **pregnant adult referred to a high-risk pregnancy clinic, answering for
herself** — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign
off*. It assigns **no** RED/YELLOW/GREEN level (not even a candidate flag) and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below cites a **real source that was actually retrieved on 2026-09-26** (URL +
  recommendation or page locator + a short verbatim anchor). Where no source was found, the row reads
  **"NO SOURCE FOUND — clinician must supply"**. Nothing was invented.
- **Quoting policy:** verbatim anchors are kept to short term-level fragments (copyright; see §4 gap 7).
  The full sentence for each anchor must be captured into a committed verbatim snapshot at sign-off.
- **Scope split with `gebe_poliklinigi.md`:** that pack captures routine antenatal history and the
  classic danger signs; this pack captures the **risk factors that bring a patient to perinatology**
  (multiple pregnancy, assisted conception, pre-existing and pregnancy-onset hypertension/diabetes,
  adverse previous outcome, ultrasound concern) plus three neutral symptom captures.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route, register or location. §2.2 names the rules the neutral symptom
  questions would feed; §2.3 lists red-flag candidates **for physician review — not encoded**.
- **No duplication of base intake:** `pregnancy_status`, `lmp_date`, medications, allergies and smoking
  are asked by `packages/protocols/base/intake.yaml`; they are not repeated here.
- **Verification caveat:** PDFs were streamed and text-extracted with `pdftotext` (nothing saved to
  disk); page numbers are **PDF page indices**. Two sources were read through an automated WebFetch
  summariser and are marked so. Re-check every anchor before sign-off; until then any derived rule stays
  `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/perinatoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with locators

### PR-S1 — T.C. Sağlık Bakanlığı *Doğum Öncesi Bakım Yönetim Rehberi* — risk form (Türkiye-first; primary)
- **guideline_id (proposed):** `TR-SB-DOBYR-2018` · Ankara, 2018 · Sağlık Bakanlığı Yayın No: 925
- **URL (retrieved copy, WHO MCA policy repository):**
  https://platform.who.int/docs/default-source/mca-documents/policy-documents/guideline/TUR-MN-21-01-GUIDELINE-2018-tur-Antenatal-Care-Management-Guidelines.pdf
- **Locators — "Gebelikte Risk Değerlendirme Formu" (PDF pp. 35–38):**
  - A (medical history): A-3 "Diabetes Mellitus", A-8 "Kronik Hipertansiyon", A-1 cardiovascular disease.
  - B (obstetric history): B-3 "Tekrarlayan Düşük", B-6 "Ölü Doğum", B-8 "Erken Doğum",
    B-20 "Yeni Doğan Ölümü".
  - C (current pregnancy): C-4 "Çoğul Gebelik", C-8 "Gestasyonel Diyabet", C-12
    "Polihidramnios-Oligohidramnios", C-13 "Anomalili Fetüs", C-16 "Preeklampsi-Eklampsi",
    C-26 "İnfertilite Tedavisi Sonrası Gebelik", C-29 "İntrauterin Gelişme Geriliği".
  - PDF p. 21 (danger signs): "Görmede bulanıklık", "Bebek hareketlerinde azalma".
- **Confidence: HIGH** (Ministry primary document). Current-edition check: §4 gap 1.

### PR-S2 — T.C. Sağlık Bakanlığı *Riskli Gebelikler Yönetim Rehberi* (Türkiye; primary)
- **guideline_id (proposed):** `TR-SB-RGYR-2014`
- **Publishing body:** T.C. Sağlık Bakanlığı Türkiye Halk Sağlığı Kurumu, Kadın ve Üreme Sağlığı Daire
  Başkanlığı · **Version:** Ankara, 2014 · Sağlık Bakanlığı Yayın No: 926
- **URL (retrieved copy — third-party host, Türk Hemşireler Derneği):**
  https://www.thd.org.tr/thdData/Books/942/riskli-gebelikler-yonetim-rehberi.pdf
  (Ministry catalogue entry https://ekutuphane.saglik.gov.tr/Yayin/464 was seen in search results only;
  the Ministry-hosted PDF link returned no content.)
- **Locators:** Sunuş (PDF p. 6) — the guideline comprises VTE, cardiovascular, epilepsy, diabetic and
  asthmatic pregnancy management guides (anchor "Diyabetik Gebe Yönetim Rehberi"). VTE section
  "Tablo-1: Risk Faktörleri" (PDF p. 15) row "Çoğul gebelik, yardımcı üreme teknikleri".
- **Confidence: MEDIUM** — Ministry text, but a third-party copy; the extraction renders Ş/İ as Ģ/Ġ
  (normalised in the anchors above). Confirm against the Ministry copy and current edition.

### PR-S3 — T.C. Sağlık Bakanlığı *Acil Obstetrik Bakım Yönetim Rehberi* (Türkiye; primary, clinician-facing)
- **guideline_id (proposed):** `TR-SB-AOBYR-2018` · Ankara, 2018 · Sağlık Bakanlığı Yayın No: 930
- **URL (retrieved copy, WHO MCA policy repository):**
  https://platform.who.int/docs/default-source/mca-documents/policy-documents/guideline/TUR-MN-21-02-GUIDELINE-2018-tur-Emergency-Obstetric-Care-Management-Guidelines.pdf
- **Locator:** "Tablo 1. Preeklampsi Sınıflaması" (PDF p. 50) — severe-feature rows include
  "Şiddetli ve sürekli başağrısı" and "Yeni başlangıçlı görme bozukluğu". Quoted for provenance only;
  the thresholds in that table are clinician criteria and are **not** used here.
- **Confidence: HIGH** for content.

### PR-S4 — Türk Perinatoloji Derneği lay patient pages (Türkiye; society, undated)
- **guideline_id (proposed):** `TPD-YRG-TAKIBI` and `TPD-ERKEN-DOGUM-BELIRTILERI` (lay pages, NOT guidelines)
- **URLs:** https://www.perinatoloji.org.tr/yuksek-riskli-gebelik-takibi ·
  https://www.perinatoloji.org.tr/erken-dogum-belirtileri · **Date:** none shown on either page
- **Anchors (as returned by a WebFetch extraction — verify):** high-risk list includes "Çoğul ve ikiz
  gebelikler", "Bebekte gelişme geriliği", "Annenin tekrarlayan düşükleri var ise"; preterm-labour list
  opens with "Kasıklarda sık sık bası hissi ve ağrı hissedilmesi".
- **Confidence: MEDIUM–LOW** — undated, summariser-extracted; Turkish-society corroboration only.

### PR-S5 — NICE NG133 *Hypertension in pregnancy* (International; primary)
- **guideline_id (proposed):** `NICE-NG133` · Published 25 June 2019; last updated 17 April 2023
- **URL:** https://www.nice.org.uk/guidance/ng133/resources/hypertension-in-pregnancy-diagnosis-and-management-pdf-66141717671365
- **Locator:** Rec 1.1.1 — pre-eclampsia symptoms include "problems with vision, such as blurring or
  flashing before the eyes" and "severe headache".
- **Confidence: HIGH** (primary PDF).

### PR-S6 — NICE NG25 *Preterm labour and birth* (International; primary)
- **guideline_id (proposed):** `NICE-NG25` · Published 20 November 2015; last updated 10 June 2022
- **URL:** https://www.nice.org.uk/guidance/ng25/resources/preterm-labour-and-birth-pdf-1837333576645
- **Locators:** Recs 1.2.1–1.2.2 use "a history of spontaneous preterm birth … or loss" as an
  eligibility criterion; the glossary defines "Symptoms of preterm labour" as reported symptoms before
  term "(such as abdominal pain)" before any clinical assessment.
- **Confidence: HIGH** (primary PDF).

### PR-S7 — NICE NG201 *Antenatal care* (International; primary)
- **guideline_id (proposed):** `NICE-NG201` · Published 19 August 2021
- **URL:** https://www.nice.org.uk/guidance/ng201/resources/antenatal-care-pdf-66143709695941
- **Locator:** Rec 1.2.34 — ask about concerns with the baby's movements; "reduced fetal movements".
- **Confidence: HIGH** (primary PDF).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032), never invented.
Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for referral | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Estimated due date (date) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); no pregnancy archetype in the OPT |
| Q3 | Multiple pregnancy | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Conception with fertility treatment | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Pre-existing diabetes/hypertension/cardiac condition | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q6 | Told BP is high in this pregnancy | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q7 | Told blood sugar is high in this pregnancy | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q8 | Previous preterm birth, pregnancy loss or baby loss | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Ultrasound concern about the baby | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Frequent pelvic pressure / tightening | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Visual disturbance | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Reduced fetal movements | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Which life-threat rules the neutral symptom questions would feed (NOT extended — invariant 7)

`files/protocols/base.life_threat.yaml` records `pregnancy_rules: status: NOT IN THIS FILE`
(HUMAN_BLOCKERS **HB-C4**). The items below have **no rule to feed** today.

| Question | Symptom captured | Would feed (when a clinician authors it) | This proposal's role |
|---|---|---|---|
| Q11 | Blurred vision / flashing lights | HB-C4 "pre-eclampsia pattern" | input only |
| Q12 | Reduced fetal movements | HB-C4 "reduced fetal movements" | input only |
| Q10 | Frequent pelvic pressure / tightening (possible preterm labour) | **absent** from HB-C4's list and from `base.life_threat` | input only; §4 gap 3 |
| Q6, Q7 | Known pregnancy hypertension / high sugar | context for the pre-eclampsia pattern; not a trigger | history only |

### 2.3 Red-flag candidates — for physician review — not encoded

No level, route, register or location is proposed (invariants 1, 7, 21).

| Candidate | Source | Status |
|---|---|---|
| New visual disturbance or severe persistent headache in pregnancy | PR-S1 PDF p. 21; PR-S3 Tablo 1; PR-S5 rec 1.1.1 | not encoded; HB-C4 |
| Reduced fetal movements | PR-S1 PDF p. 21; PR-S7 rec 1.2.34 | not encoded; HB-C4; gestational gate is clinician's |
| Symptoms of preterm labour (pelvic pressure, tightening, fluid, bleeding) | PR-S4 lay list; PR-S6 glossary | not encoded; not in HB-C4's list |
| Vaginal bleeding / fluid leakage in pregnancy | PR-S1 PDF p. 21; PR-S4 | asked in `gebe_poliklinigi.md` Q8/Q10, not here; not encoded |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and exactly one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22); written in our own
words. **All CANDIDATE — clinician to approve wording.** No item carries a triage level. Q1 binds to the
pack's `basvuru_nedeni` slot. Checked by hand against the Turkish PolicyGuard arms (unsigned — HB-C23).

The pack line below replaces the fixed duration ask, which says "şikâyet" although a referral visit may
have no complaint. It asks how long the referral reason has been known and carries no clinical content;
the clinician confirms it.

pack: duration_ask=Bu durumu ne zamandır biliyorsunuz?; duration_follow_up=Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?

**Q1 — Reason for referral** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün sizi bu polikliniğe yönlendiren durum nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Estimated due date** · archetype: `OBSERVATION.story.v1` · source: PR-S1 (current-pregnancy history, "Tahmini doğum tarihi", PDF p. 14)
> "Size söylenen tahmini doğum tarihiniz nedir?"
gen: slot=tahmini_dogum_tarihi; type=date; follow_up=Ultrason raporunuzdaki tahmini doğum tarihini söyler misiniz?; delivery=text_first
CANDIDATE — clinician to approve wording. Date picker only (invariant 22); anchors every other answer in time.
Pregnancy dating is `text_first` (files/13 §13).

**Q3 — Multiple pregnancy** · archetype: `OBSERVATION.story.v1` · source: PR-S1 risk form C-4; PR-S2 VTE Tablo-1; PR-S4
> "Bu gebelikte ikiz ya da daha fazla bebek mi bekliyorsunuz?"
gen: slot=cogul_gebelik; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Conception with fertility treatment** · archetype: `OBSERVATION.story.v1` · source: PR-S1 risk form C-26; PR-S2 VTE Tablo-1 ("yardımcı üreme teknikleri")
> "Bu gebelik tüp bebek ya da başka bir tedavi yardımıyla mı oldu?"
gen: slot=tedavi_yardimiyla_gebelik; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. "Tüp bebek" is the lay Turkish term for IVF.

**Q5a — Condition that began before pregnancy** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PR-S1 risk form A-1, A-3, A-8; PR-S2 Sunuş; PR-S4
> "Hamilelikten önce başlayan şeker, tansiyon ya da kalp gibi bir sorununuz var mı?"
gen: slot=gebelik_oncesi_saglik_sorunu; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q5b.

**Q5b — Name of that condition** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PR-S1 risk form A-1, A-3, A-8; PR-S2 Sunuş; PR-S4
> "Bu sorunun adını söyleyebilir misiniz?"
gen: slot=gebelik_oncesi_saglik_sorunu_adi; type=string; ask_if=gebelik_oncesi_saglik_sorunu == true
CANDIDATE — clinician to approve wording. Epilepsy and asthma (PR-S2) are captured here; the name has its
own string slot (wave-7 split).

**Q6 — High blood pressure in this pregnancy** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PR-S1 risk form C-16; PR-S5
> "Bu gebelikte size tansiyonunuzun yüksek olduğu söylendi mi?"
gen: slot=gebelikte_yuksek_tansiyon; type=boolean
CANDIDATE — clinician to approve wording. Asks what the patient was told; no reading is requested.

**Q7 — High blood sugar in this pregnancy** · archetype: `EVALUATION.problem_diagnosis.v1` · source: PR-S1 risk form C-8; PR-S2 Sunuş ("Diyabetik Gebe Yönetim Rehberi")
> "Bu gebelikte size kan şekerinizin yüksek olduğu söylendi mi?"
gen: slot=gebelikte_yuksek_seker; type=boolean
CANDIDATE — clinician to approve wording. No value is requested (invariant 22).

**Q8a — Any previous pregnancy** · archetype: `OBSERVATION.story.v1` · source: PR-S1 risk form B-3, B-6, B-8, B-20; PR-S6 recs 1.2.1–1.2.2
> "Bu gebelikten önce hiç hamile kaldınız mı?"
gen: slot=onceki_gebelik; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Same text and slot as gebe_poliklinigi Q3. Gate for Q8b.

**Q8b — Previous preterm birth, pregnancy loss or baby loss** · archetype: `OBSERVATION.story.v1` · source: PR-S1 risk form B-3, B-6, B-8, B-20; PR-S6 recs 1.2.1–1.2.2; PR-S4
> "Bu soru zor gelebilir. Önceki gebeliklerinizde erken doğum, düşük ya da bebek kaybı yaşadınız mı?"
gen: slot=onceki_gebelik_kaybi; type=boolean; ask_if=onceki_gebelik == true; delivery=text_first
CANDIDATE — clinician to approve wording. Two sentences, one question; the lead sentence acknowledges
the subject without alarm. Asked only after a previous pregnancy (Q8a); `text_first` (§4 gap 5).

**Q8c — What happened, if the patient wishes** · archetype: `OBSERVATION.story.v1` · source: PR-S1 risk form B-3, B-6, B-8, B-20; PR-S6 recs 1.2.1–1.2.2; PR-S4
> "İsterseniz bunu kısaca anlatır mısınız?"
gen: slot=onceki_gebelik_kaybi_aciklama; type=string; ask_if=onceki_gebelik_kaybi == true; delivery=text_first
CANDIDATE — clinician to approve wording. Optional narrative in its own string slot (wave-7 split).

**Q9a — Ultrasound concern about the baby** · archetype: `OBSERVATION.story.v1` · source: PR-S1 risk form C-12, C-13, C-29; PR-S4 ("Bebekte gelişme geriliği")
> "Ultrasonda bebeğinizle ilgili size özel bir durum söylendi mi?"
gen: slot=ultrason_bulgusu; type=boolean
CANDIDATE — clinician to approve wording. Reported history only; the scan report itself comes through
document ingestion. Gate for Q9b.

**Q9b — What the patient was told** · archetype: `OBSERVATION.story.v1` · source: PR-S1 risk form C-12, C-13, C-29; PR-S4 ("Bebekte gelişme geriliği")
> "Size söylenenleri kısaca anlatır mısınız?"
gen: slot=ultrason_bulgusu_aciklama; type=string; ask_if=ultrason_bulgusu == true
CANDIDATE — clinician to approve wording. The narrative has its own string slot (wave-7 split).

**Q10 — Frequent pelvic pressure or tightening** · archetype: `OBSERVATION.symptom_sign.v1` · source: PR-S4 ("Kasıklarda sık sık bası hissi"); PR-S6 glossary ("Symptoms of preterm labour")
> "Kasıklarınızda sık sık gelen bası ya da kasılma hissi oluyor mu?"
gen: slot=kasik_basi_kasilma; type=boolean
CANDIDATE — clinician to approve wording. Neutral symptom capture; no rule to feed (§2.2).

**Q11 — Visual disturbance** · archetype: `OBSERVATION.symptom_sign.v1` · source: PR-S1 PDF p. 21 ("Görmede bulanıklık"); PR-S3 Tablo 1; PR-S5 rec 1.1.1
> "Son günlerde görmenizde bulanıklık ya da ışık çakmaları oldu mu?"
gen: slot=gorme_bulanikligi; type=boolean
CANDIDATE — clinician to approve wording. **Feeds HB-C4 pre-eclampsia pattern (§2.2).**

**Q12a — Fetal movements felt yet** · archetype: `OBSERVATION.story.v1` · source: PR-S1 PDF p. 21 ("Bebek hareketlerinde azalma"); PR-S7 rec 1.2.34
> "Bebeğinizin hareketlerini hissetmeye başladınız mı?"
gen: slot=bebek_hareketi_hissediliyor; type=boolean
CANDIDATE — clinician to approve wording. Patient-reported gate for Q12b; it replaces the conditional
lead, whose "hayır" was ambiguous. The gestational threshold stays with the clinician (§4 gap 6, HB-C4).

**Q12b — Reduced fetal movements** · archetype: `OBSERVATION.symptom_sign.v1` · source: PR-S1 PDF p. 21 ("Bebek hareketlerinde azalma"); PR-S7 rec 1.2.34
> "Son günlerde bebeğinizin hareketlerinde azalma oldu mu?"
gen: slot=bebek_hareketlerinde_azalma; type=boolean; ask_if=bebek_hareketi_hissediliyor == true
CANDIDATE — clinician to approve wording. **Feeds HB-C4 (§2.2).** Same texts and slots as gebe_poliklinigi Q9a/Q9b.

*(12 candidate questions, 17 items after the wave-7 splits of Q5, Q8, Q9 and Q12: 11 guideline-sourced —
Q2–Q12 — and 1 general intake; 3 neutral symptom captures — Q10–Q12.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Current editions** — PR-S1 (2018) and PR-S2 (2014; its own Sunuş commits to review at least every
   two years) were retrieved only as mirror/third-party copies. **NO SOURCE FOUND (current edition) —
   clinician to confirm** on the Ministry e-library.
2. **Türk Perinatoloji Derneği / TMFTP versioned guideline** — only undated lay pages (PR-S4) were
   retrieved; a PUDER preterm-labour guideline PDF and a TMFTP guideline index appeared in search
   results but were not opened. **NO SOURCE FOUND (versioned Turkish society guideline) — clinician
   must supply** if one should outrank PR-S5/PR-S6.
3. **Preterm-labour symptoms are not in HB-C4's named list** (bleeding/pain, pre-eclampsia, reduced
   fetal movements, post-partum fever/bleeding, ectopic). Q10 feeds nothing even after HB-C4 closes.
   **Clinician (HB-C4 owner) must decide.**
4. **Omitted to stay at twelve — sourced, clinician may swap in:** vaginal bleeding and fluid leakage
   (asked in `gebe_poliklinigi.md`); severe headache (PR-S3, PR-S5); pain below the ribs (PR-S5);
   Rh incompatibility (PR-S1 C-3); previous caesarean/uterine surgery (PR-S1 B-1).
5. **Sensitive-disclosure delivery** — Q8 asks about pregnancy and baby loss. Resolved in wave 7: Q8a–Q8c
   are `text_first` (as base `pregnancy_status` is). What a disclosure of distress routes to stays a
   **clinician decision**; no script is proposed here.
6. **Gestational thresholds** (PR-S6 week bounds; PR-S7 fetal-movement threshold) — not pinned in
   patient copy. **Clinician must supply** any gating rule.
7. **Copyright / snapshot licence** — Ministry texts forbid reproduction even in part without
   permission; NICE texts are © NICE. A committed verbatim snapshot needs a **legal-review decision**.
8. **Every triage level and all three RED axes** (invariant 21) — deliberately **not** assigned.
9. **openEHR** — no pregnancy archetype root in the OPT; leaf paths deferred (INT-032).
10. **PolicyGuard lexicon is itself unsigned (HB-C23).**

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy** — `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording; each item marked CANDIDATE.
- **Inv. 7** — pregnancy emergencies stay in `base.life_threat` (HB-C4); this pack adds no rule.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at clinician sign-off.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals; no blood-pressure or glucose value is requested; the due date is a date picker.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; candidates only here.
- **HB-C1 / HB-C4** — awaits clinician sign-off and the pregnancy rule set; NOT served.
