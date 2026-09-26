# Gebe Polikliniği (Routine antenatal clinic) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Gebe polikliniği (routine antenatal care)
Taxonomy id: `gebe_poliklinigi` (branches.yaml — cluster `womens_health`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) for a **pregnant adult answering for herself** — **not** diagnosis, not triage
authority. This file is a *proposal for a clinician to sign off*. It assigns **no** RED/YELLOW/GREEN
level (not even a candidate flag) and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below cites a **real source that was actually retrieved on 2026-09-26** (URL +
  recommendation or page locator + a short verbatim anchor). Where no source was found, the row reads
  **"NO SOURCE FOUND — clinician must supply"**. Nothing was invented.
- **Quoting policy:** verbatim anchors are kept to short term-level fragments (copyright: the Ministry
  and NICE texts are copyrighted; see §4 gap 6). The full sentence for each anchor must be captured
  into a committed verbatim snapshot at sign-off.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, a route, a register or a location. Obstetric emergencies (bleeding,
  reduced fetal movements, pre-eclampsia symptoms, fluid leakage) are asked **neutrally** as symptom
  capture only; §2.2 names the rules they would feed, and §2.3 lists red-flag candidates **for physician
  review — not encoded**.
- **No duplication of base intake:** `pregnancy_status`, `lmp_date`, medications, allergies and
  smoking are already asked by `packages/protocols/base/intake.yaml`; they are not repeated here.
- **Verification caveat:** PDFs were streamed and text-extracted with `pdftotext` (nothing saved to
  disk); page numbers are **PDF page indices**, not printed page numbers. Re-check every anchor against
  the primary text before sign-off. Until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/gebe_poliklinigi.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with locators

### GP-S1 — T.C. Sağlık Bakanlığı *Doğum Öncesi Bakım Yönetim Rehberi* (Türkiye-first; primary)
- **guideline_id (proposed):** `TR-SB-DOBYR-2018`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü, Kadın ve Üreme Sağlığı
  Dairesi Başkanlığı · **Version:** Ankara, 2018 · Sağlık Bakanlığı Yayın No: 925
- **URL (retrieved copy, WHO MCA policy repository):**
  https://platform.who.int/docs/default-source/mca-documents/policy-documents/guideline/TUR-MN-21-01-GUIDELINE-2018-tur-Antenatal-Care-Management-Guidelines.pdf
- **Locators and short anchors:**
  - PDF p. 12 (2.4 Tıbbi öykü): chronic systemic disease list opens "Kronik sistemik hastalıklar
    (epilepsi,diyabet, hipertansiyon," and continues with thyroid, cardiac and kidney disease.
  - PDF p. 13 (2.5 Obstetrik ve üreme sağlığı öyküsü): gravida/parity, outcome of every previous
    pregnancy, and "Maternal komplikasyonlar (kanama, preeklampsi," among others.
  - PDF p. 14 (2.6 Mevcut gebelik öyküsü): "Tahmini doğum tarihi"; pregnancy complaints to assess
    include nausea and vomiting ("bulantı, kusma").
  - PDF p. 21 (danger signs to teach): list includes "Şiddetli bulantı kusma", "Vajinal kanama",
    "Şiddetli Başağrısı", "Yüz, el ve bacaklarda şişme", "Bebek hareketlerinde azalma", "Su gelmesi".
  - PDF p. 28 (third visit, oedema check): upper-body oedema — anchor "(eller, göz kapakları)" — may be
    the first sign of pre-eclampsia.
  - PDF p. 37 (Gebelikte Risk Değerlendirme Formu, B-1): "Geçirilmiş Uterin Cerrahi: Sezaryen,".
- **Confidence: HIGH** for content (Ministry primary document). **Caveat:** 2018 edition via the WHO
  mirror; the current edition must be confirmed on the Ministry e-library (§4 gap 1).

### GP-S2 — NICE NG201 *Antenatal care* (International; primary)
- **guideline_id (proposed):** `NICE-NG201` · **Version:** Published 19 August 2021
- **URL:** https://www.nice.org.uk/guidance/ng201/resources/antenatal-care-pdf-66143709695941
- **Locators:**
  - Rec 1.2.1: at booking, ask about "her medical history, obstetric history and family history" and
    about previous or current mental health concerns.
  - Rec 1.2.34: after the stated gestational threshold, ask about concerns with the baby's movements and
    advise contact for "reduced fetal movements".
  - Recs 1.4.1–1.4.7: nausea and vomiting; rec 1.4.7 considers inpatient care "if vomiting is severe".
- **Confidence: HIGH** (primary PDF).

### GP-S3 — NICE NG133 *Hypertension in pregnancy: diagnosis and management* (International; primary)
- **guideline_id (proposed):** `NICE-NG133` · **Version:** Published 25 June 2019; last updated
  17 April 2023
- **URL:** https://www.nice.org.uk/guidance/ng133/resources/hypertension-in-pregnancy-diagnosis-and-management-pdf-66141717671365
- **Locator:** Rec 1.1.1 — symptoms of pre-eclampsia include "severe headache" and "sudden swelling of
  the face, hands or feet" (also vision problems, pain below the ribs, vomiting).
- **Confidence: HIGH** (primary PDF). Corroborates GP-S1's Türkiye-first list.

### GP-S4 — Türk Perinatoloji Derneği, "Erken doğum belirtileri" (Türkiye; lay patient page)
- **guideline_id (proposed):** `TPD-ERKEN-DOGUM-BELIRTILERI` (lay page, NOT a guideline)
- **URL:** https://www.perinatoloji.org.tr/erken-dogum-belirtileri · **Date:** none shown on the page
- **Anchors (as returned by a WebFetch extraction):** list items "suların gelmesi" and "kanama gelmesi".
- **Confidence: MEDIUM–LOW** — undated lay page, extracted by an automated fetch; Turkish-society
  corroboration of GP-S1 only.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Estimated due date (date) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); no pregnancy archetype in the OPT |
| Q3 | Any previous pregnancy | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Problems in previous pregnancies/births | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Previous caesarean / uterine surgery | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); no procedure archetype in the OPT |
| Q6 | Ongoing chronic condition | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q7 | Nausea/vomiting limiting intake | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Vaginal bleeding/spotting in pregnancy | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Reduced fetal movements | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Fluid leakage | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Severe persistent headache | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | New swelling of face/hands/eyelids | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Which life-threat rules the neutral symptom questions would feed (NOT extended — invariant 7)

`files/protocols/base.life_threat.yaml` records `pregnancy_rules: status: NOT IN THIS FILE`
(HUMAN_BLOCKERS **HB-C4**: the pregnancy rule set does not exist at all). `base/intake.yaml` carries a
boolean probe `rf_pregnancy_bleeding_pain` whose trigger is unsigned. So every item below currently
has **no rule to feed**; the questions only capture the symptom.

| Question | Symptom captured | Would feed (when a clinician authors it) | This proposal's role |
|---|---|---|---|
| Q8 | Bleeding/spotting in pregnancy | HB-C4 "pregnancy + heavy bleeding / severe pain"; base probe `rf_pregnancy_bleeding_pain` | input only |
| Q9 | Reduced fetal movements | HB-C4 "reduced fetal movements" | input only |
| Q11, Q12 | Headache; face/hand/eyelid swelling | HB-C4 "pre-eclampsia pattern" | input only |
| Q10 | Fluid leakage (possible membrane rupture) | **absent** from HB-C4's list and from `base.life_threat` | input only; §4 gap 3 |
| Q7 | Vomiting limiting food/fluid | **absent** from `base.life_threat` | input only; §4 gap 3 |

### 2.3 Red-flag candidates — for physician review — not encoded

No level, route, register (ALERT/CALM/SILENT/DEFERRED_CLINICIAN) or location is proposed for any row
(invariants 1, 7, 21). These are *pointers* for the clinician authoring HB-C4.

| Candidate | Source | Status |
|---|---|---|
| Vaginal bleeding in pregnancy | GP-S1 PDF p. 21 ("Vajinal kanama"); GP-S4 | not encoded; HB-C4 |
| Reduced fetal movements | GP-S1 PDF p. 21; GP-S2 rec 1.2.34 | not encoded; HB-C4; gestational gate is clinician's |
| Pre-eclampsia symptoms (severe headache, visual change, sudden face/hand swelling) | GP-S1 PDF p. 21, p. 28; GP-S3 rec 1.1.1 | not encoded; HB-C4 |
| Fluid leakage / possible rupture of membranes | GP-S1 PDF p. 21 ("Su gelmesi"); GP-S4 | not encoded; not in HB-C4's list |
| Severe vomiting unable to keep fluids down | GP-S1 PDF p. 21; GP-S2 rec 1.4.7 | not encoded |
| Fever in pregnancy | GP-S1 PDF p. 21 (danger-sign list) | not asked here (base/sepsis territory); not encoded |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and exactly one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22); written in our own
words (no society questionnaire copied). **All CANDIDATE — clinician to approve wording.** No item
carries a triage level. Q1 binds to the pack's `basvuru_nedeni` slot. Wording was checked by hand
against the Turkish PolicyGuard arms (`guard_lexicons/tr.py`, itself unsigned — HB-C23).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü gebelik kontrolünüzde en çok konuşmak istediğiniz konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Estimated due date** · archetype: `OBSERVATION.story.v1` · source: GP-S1 PDF p. 14 ("Tahmini doğum tarihi")
> "Size söylenen tahmini doğum tarihiniz nedir?"
gen: slot=tahmini_dogum_tarihi; type=date; follow_up=Tarihi bilmiyorsanız son ultrason raporunuza bakabilir misiniz?
CANDIDATE — clinician to approve wording. Date picker only, never free numeric text (invariant 22).
Distinct from base `lmp_date`, which is not repeated here.

**Q3 — Any previous pregnancy** · archetype: `OBSERVATION.story.v1` · source: GP-S1 PDF p. 13 (obstetric history); GP-S2 rec 1.2.1
> "Bu gebelikten önce hiç hamile kaldınız mı?"
gen: slot=onceki_gebelik; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q4.

**Q4 — Problems in previous pregnancies or births** · archetype: `OBSERVATION.story.v1` · source: GP-S1 PDF p. 13 (maternal complications); GP-S2 rec 1.2.1
> "Önceki gebeliklerinizde ya da doğumlarınızda bir sorun yaşadınız mı?"
gen: slot=onceki_gebelik_sorunu; type=boolean; ask_if=onceki_gebelik == true; follow_up=Yaşadığınız sorunu kısaca anlatır mısınız?
CANDIDATE — clinician to approve wording. Free-text detail is captured by the follow-up only.

**Q5 — Previous caesarean or uterine surgery** · archetype: `OBSERVATION.story.v1` · source: GP-S1 PDF p. 37 (risk form B-1)
> "Daha önce sezaryen ya da rahminizden başka bir ameliyat oldunuz mu?"
gen: slot=rahim_ameliyati; type=boolean
CANDIDATE — clinician to approve wording. Not gated on Q3: uterine surgery can precede a first pregnancy.

**Q6 — Ongoing chronic condition** · archetype: `EVALUATION.problem_diagnosis.v1` · source: GP-S1 PDF p. 12 (chronic systemic disease); GP-S2 rec 1.2.1
> "Şeker, tansiyon ya da tiroid gibi süregelen bir sağlık sorununuz var mı?"
gen: slot=suregelen_saglik_sorunu; type=boolean; follow_up=Bu sağlık sorununun adını söyleyebilir misiniz?
CANDIDATE — clinician to approve wording. Lay terms chosen on purpose; no jargon.

**Q7 — Nausea or vomiting limiting food and fluid** · archetype: `OBSERVATION.symptom_sign.v1` · source: GP-S1 PDF p. 14 and p. 21 ("Şiddetli bulantı kusma"); GP-S2 recs 1.4.1–1.4.7
> "Bulantı ya da kusma yüzünden yemek yemekte ya da su içmekte zorlanıyor musunuz?"
gen: slot=bulanti_kusma_zorlanma; type=boolean
CANDIDATE — clinician to approve wording. Symptom capture only (§2.2).

**Q8 — Bleeding or spotting in this pregnancy** · archetype: `OBSERVATION.symptom_sign.v1` · source: GP-S1 PDF p. 21 ("Vajinal kanama"); GP-S4
> "Bu gebelikte vajinal kanamanız ya da lekelenmeniz oldu mu?"
gen: slot=gebelikte_kanama; type=boolean
CANDIDATE — clinician to approve wording. **Feeds HB-C4 / `rf_pregnancy_bleeding_pain` (§2.2)** — no level assigned here.

**Q9 — Reduced fetal movements** · archetype: `OBSERVATION.symptom_sign.v1` · source: GP-S1 PDF p. 21 ("Bebek hareketlerinde azalma"); GP-S2 rec 1.2.34
> "Bebeğinizin hareketlerini hissediyorsanız, son günlerde bu hareketlerde azalma oldu mu?"
gen: slot=bebek_hareketlerinde_azalma; type=boolean
CANDIDATE — clinician to approve wording. The conditional lead lets an early-pregnancy patient answer;
the gestational gate itself is the clinician's (§4 gap 4). **Feeds HB-C4 (§2.2).**

**Q10 — Fluid leakage** · archetype: `OBSERVATION.symptom_sign.v1` · source: GP-S1 PDF p. 21 ("Su gelmesi"); GP-S4 ("suların gelmesi")
> "Bu gebelikte iç çamaşırınızı ıslatan su gibi bir akıntı oldu mu?"
gen: slot=su_gelmesi; type=boolean
CANDIDATE — clinician to approve wording. No rule exists to feed (§2.2, §4 gap 3).

**Q11 — Severe persistent headache** · archetype: `OBSERVATION.symptom_sign.v1` · source: GP-S1 PDF p. 21 ("Şiddetli Başağrısı"); GP-S3 rec 1.1.1 ("severe headache")
> "Son günlerde geçmeyen şiddetli bir baş ağrınız oldu mu?"
gen: slot=siddetli_bas_agrisi; type=boolean
CANDIDATE — clinician to approve wording. **Feeds HB-C4 pre-eclampsia pattern (§2.2).**

**Q12 — New swelling of face, hands or eyelids** · archetype: `OBSERVATION.symptom_sign.v1` · source: GP-S1 PDF p. 21 ("Yüz, el ve bacaklarda şişme") and p. 28; GP-S3 rec 1.1.1
> "Yüzünüzde, ellerinizde ya da göz kapaklarınızda yeni bir şişlik fark ettiniz mi?"
gen: slot=yuz_el_sisligi; type=boolean
CANDIDATE — clinician to approve wording. Upper-body focus follows GP-S1 p. 28; ankle swelling late in
pregnancy is common and deliberately not asked. **Feeds HB-C4 pre-eclampsia pattern (§2.2).**

*(12 candidate questions: 11 guideline-sourced — Q2–Q12 — and 1 general intake; 5 are neutral
symptom captures for obstetric emergencies — Q8–Q12.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **GP-S1 current edition** — only the 2018 edition (WHO mirror) was retrieved. **NO SOURCE FOUND
   (confirmation of current edition) — clinician to confirm** on the Ministry e-library.
2. **TJOD guidance on routine antenatal history / danger signs** — no versioned TJOD document was
   retrieved. **NO SOURCE FOUND — clinician must supply** if a TJOD text should outrank GP-S2/GP-S3.
   WHO ANC 2016 recommendations were not retrieved either.
3. **Membrane rupture and hyperemesis are not in HB-C4's named list** (bleeding/pain, pre-eclampsia,
   reduced fetal movements, post-partum fever/bleeding, ectopic). Q7 and Q10 therefore feed nothing
   even after HB-C4 closes. **Clinician (HB-C4 owner) must decide** whether to add them.
4. **Gestational gating** (GP-S2 rec 1.2.34 threshold; GP-S1 fetal-movement gate) — Q9 uses a
   conditional lead instead of a threshold; no week is pinned in patient copy. **Clinician must supply**
   the `ask_if` rule if one is wanted (a gestational-age slot would be derived from Q2 or base `lmp_date`).
5. **Omitted to stay at twelve — sourced, clinician may swap in:** visual disturbance (GP-S1 p. 21
   "Görmede bulanıklık"; GP-S3 rec 1.1.1 — asked in `perinatoloji.md` Q11); breathing difficulty and
   fever (GP-S1 p. 21); unexplained itching (GP-S1 p. 21); mood / previous mental health (GP-S2 rec
   1.2.1) — the latter should route to the consented wellbeing-screening flow, not an ad-hoc question.
6. **Copyright / snapshot licence** — GP-S1 states it may not be quoted without citation and may not be
   reproduced even in part; NICE texts are © NICE. Committing a full verbatim snapshot (clinical content
   rule) needs a **legal-review decision** on reproduction rights. **Human must supply.**
7. **Standard duration slot wording** — the generator adds `sikayet_suresi` ("Bu şikâyetiniz ne
   zamandır var?"); for a routine check with no complaint it may read oddly. **Clinician to decide.**
8. **Every triage level and all three RED axes** (invariant 21) — deliberately **not** assigned.
9. **openEHR** — no pregnancy or procedure archetype root in the OPT; leaf paths deferred (INT-032).
10. **PolicyGuard lexicon is itself unsigned (HB-C23)** — wording was checked against the current arms,
    which await a named clinician's signature.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy** — `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording; each item marked CANDIDATE.
- **Inv. 7** — pregnancy emergencies stay in `base.life_threat` (HB-C4); this pack adds no rule.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at clinician sign-off.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals in any question; the due date is a date picker.
- **Clinical content rule** — every red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; this proposal supplies candidates only.
- **HB-C1 / HB-C4** — awaits clinician sign-off and the pregnancy rule set; NOT served.
