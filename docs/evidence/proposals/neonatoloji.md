# Neonatoloji (Neonatology outpatient / newborn follow-up) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1) and a paediatrician's signature (HB-C3); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Neonatoloji (newborn follow-up clinic)
Taxonomy id: `neonatoloji` (branches.yaml — cluster `child_health`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (history and symptom capture for a
clinician-ready note) **answered by a parent on behalf of a newborn** — **not** diagnosis, not triage
authority. Every question addresses the parent with `siz` and refers to the child as **"bebeğiniz"**.
This file is a *proposal for a clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and
pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below cites a **real source that was actually retrieved on 2026-09-26** (URL +
  recommendation or page locator + a short verbatim anchor). Where no source was found, the row reads
  **"NO SOURCE FOUND — clinician must supply"**. Nothing was invented.
- **Turkish first:** three Türk Neonatoloji Derneği (TND) guidelines (2023, 2023, 2018) are the primary
  sources; NICE CG98 and NG194 corroborate.
- **Quoting policy:** verbatim anchors are kept to short term-level fragments. TND guidelines forbid
  copying "kısmen veya tamamen" without written permission (§4 gap 6).
- **Triage:** per invariant 1, nothing here assigns a level, route, register or location. Newborn
  emergencies (fever, poor feeding, jaundice, breathing difficulty, hard to wake) are asked **neutrally**
  as symptom capture; §2.2 names the rules they would feed (all currently absent — HB-C3) and §2.3 lists
  red-flag candidates **for physician review — not encoded**.
- **Proxy session:** base intake records `subject_role` / `proxy_reported`; the base adult items
  (`pregnancy_status`, `lmp_date`, smoking, alcohol) do not apply to the baby and are a base-pack
  concern, not repeated here.
- **Verification caveat:** PDFs were streamed and text-extracted with `pdftotext` (nothing saved to
  disk); page numbers are **PDF page indices**. Re-check every anchor before sign-off; until then any
  derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/neonatoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with locators

### NE-S1 — TND *Yenidoğan Sarılıklarında Yaklaşım, İzlem ve Tedavi Rehberi — 2023 Güncellemesi* (Türkiye; primary)
- **guideline_id (proposed):** `TND-SARILIK-2023` · **Authors:** Çoban A, Kaynak Türkmen M, Gürsoy T ·
  Türk Neonatoloji Derneği, © 2023
- **URL:** https://neonatology.org.tr/uploads/content/tan%C4%B1-tedavi/yenidogan_sarilik.pdf
  (index: https://neonatology.org.tr/tani-tedavi-protokolleri)
- **Locators:**
  - PDF p. 8 — assessing jaundice needs the baby's "gebelik haftası, postnatal yaşı, riskleri".
  - PDF p. 12 — an adequately fed baby wets several nappies a day in the first days (anchor
    "bez ıslatır"); dark urine may reflect direct hyperbilirubinaemia.
  - PDF p. 13 — late-preterm babies are at high risk of "beslenme yetersizliği ve sarılık"; jaundice is
    visible in the whites of the eyes (anchor "gözün bu beyaz dokuları sarıya boyanır").
  - PDF p. 16 — risk factors include "kardeşlerde sarılık öyküsü" and poor breastfeeding.
  - PDF p. 21 — in prolonged jaundice, ask about stool colour "(açık renk)" and urine colour.
- **Confidence: HIGH** (society guideline, primary PDF).

### NE-S2 — TND *Yenidoğan Enfeksiyonları Tanı ve Tedavi Rehberi — 2023 Güncellemesi* (Türkiye; primary)
- **guideline_id (proposed):** `TND-ENFEKSIYON-2023` · **Authors:** Satar M, Arısoy AE, Çelik İH ·
  Türk Neonatoloji Derneği, 2023
- **URL:** https://neonatology.org.tr/uploads/content/tan%C4%B1-tedavi/enfeksiyon_rehberi_2023_.pdf
- **Locator:** PDF p. 12, "Tablo 1. Yenidoğan sepsisinde klinik bulgular" — general signs include
  "beslenme güçlüğü, emmeme" and temperature instability; respiratory signs include "inleme"; nervous
  system signs include "uykuya eğilim".
- **Confidence: HIGH** (clinician-facing table; used only to source which symptoms to ask about).

### NE-S3 — TND *Yüksek Riskli Bebek İzlem Rehberi — 2018 Güncellemesi* (Türkiye; primary)
- **guideline_id (proposed):** `TND-YRBI-2018` · **Authors:** Acunaş B, Baş AY, Uslu S; eds. Koç E, Vural M
- **URL:** https://neonatology.org.tr/uploads/content/tan%C4%B1-tedavi/17_min.pdf
- **Locators:** PDF pp. 6–7, "Tablo 1. Yenidoğanda risk kategorileri" — categories include
  "YYBÜ’de yatan" and "Geç preterm". PDF p. 8 — before discharge the family should be able to recognise
  illness signs (anchor "ateş, iyi emmeme, kusma, ishal, sarılık, uykuya meyil").
- **Confidence: HIGH.** Oldest of the three (2018); check for an update (§4 gap 1).

### NE-S4 — NICE CG98 *Jaundice in newborn babies under 28 days* (International; primary)
- **guideline_id (proposed):** `NICE-CG98` · Published 19 May 2010; last updated 31 October 2023
- **URL:** https://www.nice.org.uk/guidance/cg98/resources/jaundice-in-newborn-babies-under-28-days-pdf-975756073669
- **Locators:** Rec 1.1.1 — tell parents to check nappies for "dark urine or pale chalky stools".
  Rec 1.2.1 — risk factors include "gestational age under 38 weeks" and "a previous sibling with
  neonatal jaundice requiring phototherapy". Rec 1.7.1 — in prolonged jaundice, "look for pale chalky
  stools".
- **Confidence: HIGH** (primary PDF).

### NE-S5 — NICE NG194 *Postnatal care* (International; primary)
- **guideline_id (proposed):** `NICE-NG194` · Published 20 April 2021; last updated 9 June 2026
- **URL:** https://www.nice.org.uk/guidance/ng194/resources/postnatal-care-pdf-66142082148037
- **Locators:** Rec 1.4.1 — treat parents' concerns as an important indicator of possible serious
  illness. Rec 1.4.7 — note "refusing feeds or a change in the level of responsiveness". Rec 1.4.9 —
  red flags include "unresponsive or unrousable", "grunting respirations" and abnormal temperature.
  Rec 1.5.14 — feeding assessment asks about parents' feeding concerns and "the number of wet and
  dirty nappies".
- **Confidence: HIGH** (primary PDF).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032), never invented.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit (parent-reported) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Baby's date of birth (date) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); may duplicate the identity record (§4 gap 3) |
| Q3 | Born before the expected date | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Neonatal intensive-care stay | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Feeding method | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Feeding less than usual | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Nappies wet as often as usual | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Yellowing of skin or eyes | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Very pale / chalky stool | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Fever | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Unusually sleepy / hard to wake | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Laboured breathing / grunting | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Which life-threat rules the neutral symptom questions would feed (NOT extended — invariant 7)

`files/protocols/base.life_threat.yaml` records `paediatric_rules: status: NOT IN THIS FILE`, naming as
absent "fever under 3 months, lethargy/poor feeding in an infant, breathing difficulty with retractions
… dehydration signs" (HUMAN_BLOCKERS **HB-C3**, which needs a **paediatrician**). Retraction *grading* is
a forbidden trigger (04 §8.1 rule 1), so Q12 asks only the parent-reportable form. No item has a rule
to feed today.

| Question | Symptom captured | Would feed (when a paediatrician authors it) | This proposal's role |
|---|---|---|---|
| Q10 | Fever in a newborn | HB-C3 "fever under 3 months" | input only |
| Q6, Q11 | Feeding less; unusually sleepy / hard to wake | HB-C3 "lethargy/poor feeding in an infant" | input only |
| Q12 | Laboured breathing / grunting | HB-C3 "breathing difficulty" (parent-reportable form) | input only |
| Q7 | Fewer wet nappies | HB-C3 "dehydration signs" | input only |
| Q8, Q9 | Jaundice; pale stool | **absent** from HB-C3's list and from `base.life_threat` | input only; §4 gap 2 |

### 2.3 Red-flag candidates — for physician review — not encoded

No level, route, register or location is proposed (invariants 1, 7, 21). Paediatric register (`CALM`)
and age bands are HB-C3's.

| Candidate | Source | Status |
|---|---|---|
| Fever or low temperature in a newborn | NE-S3 PDF p. 8; NE-S5 rec 1.4.9 | not encoded; HB-C3 |
| Poor feeding / refusing feeds | NE-S2 Tablo 1; NE-S3 PDF p. 8; NE-S5 rec 1.4.7 | not encoded; HB-C3 |
| Unresponsive, unrousable or unusually sleepy | NE-S2 Tablo 1; NE-S3 PDF p. 8; NE-S5 rec 1.4.9 | not encoded; HB-C3 |
| Grunting or laboured breathing | NE-S2 Tablo 1; NE-S5 rec 1.4.9 | not encoded; HB-C3 |
| Jaundice in the first day of life, or with pale stool / dark urine | NE-S1 PDF pp. 12, 21; NE-S4 recs 1.1.1, 1.7.1 | not encoded; not in HB-C3's list |
| Too few wet nappies (dehydration) | NE-S1 PDF p. 12; NE-S5 rec 1.5.14 | not encoded; HB-C3 |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**, addressed to the **parent**; the child is always "bebeğiniz"; one concern and
exactly one question mark per turn; at most fifteen words per sentence; no diagnosis/treatment/prognosis
language; no numerals (invariant 22); written in our own words. **All CANDIDATE — clinician
(paediatrician) to approve wording.** No item carries a triage level. Q1 binds to `basvuru_nedeni`.
Checked by hand against the Turkish PolicyGuard arms (unsigned — HB-C23).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake; NE-S5 rec 1.4.1
> "Bugün bebeğiniz için en çok konuşmak istediğiniz konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Baby's date of birth** · archetype: `OBSERVATION.story.v1` · source: NE-S1 PDF p. 8 ("postnatal yaşı")
> "Bebeğiniz hangi tarihte doğdu?"
gen: slot=bebegin_dogum_tarihi; type=date
CANDIDATE — clinician to approve wording. Date picker only (invariant 22). Drop if the proxy record
already carries the baby's date of birth (§4 gap 3).

**Q3 — Born early** · archetype: `OBSERVATION.story.v1` · source: NE-S1 PDF pp. 8, 13 ("gebelik haftası"; late preterm); NE-S3 Tablo 1 ("Geç preterm"); NE-S4 rec 1.2.1
> "Bebeğiniz beklenen doğum tarihinden erken mi doğdu?"
gen: slot=erken_dogum; type=boolean
CANDIDATE — clinician to approve wording. The number of weeks is not asked (invariant 22); it comes
from the discharge summary via document ingestion.

**Q4 — Neonatal intensive-care stay** · archetype: `OBSERVATION.story.v1` · source: NE-S3 Tablo 1 ("YYBÜ’de yatan")
> "Bebeğiniz doğduktan sonra yenidoğan yoğun bakımında yattı mı?"
gen: slot=yogun_bakim_yatisi; type=boolean; follow_up=Yoğun bakımda neden yattığını kısaca anlatır mısınız?
CANDIDATE — clinician to approve wording.

**Q5 — Feeding method** · archetype: `OBSERVATION.story.v1` · source: NE-S1 PDF p. 16 (breastfeeding as a risk context); NE-S4 rec 1.2.1; NE-S5 rec 1.5.14
> "Bebeğinizi şu anda nasıl besliyorsunuz?"
gen: slot=beslenme_sekli; type=string; follow_up=Anne sütü, mama ya da ikisini birlikte mi veriyorsunuz?
CANDIDATE — clinician to approve wording. Neutral about feeding choice; no judgement implied.

**Q6 — Feeding less than usual** · archetype: `OBSERVATION.symptom_sign.v1` · source: NE-S2 Tablo 1 ("beslenme güçlüğü, emmeme"); NE-S3 PDF p. 8 ("iyi emmeme"); NE-S5 rec 1.4.7
> "Bebeğiniz son günlerde her zamankinden daha az mı besleniyor?"
gen: slot=beslenmede_azalma; type=boolean
CANDIDATE — clinician to approve wording. **Feeds HB-C3 poor feeding (§2.2).**

**Q7 — Nappies wet as often as usual** · archetype: `OBSERVATION.symptom_sign.v1` · source: NE-S1 PDF p. 12 ("bez ıslatır"); NE-S5 rec 1.5.14 ("wet and dirty nappies")
> "Bebeğinizin bezleri her zamanki kadar sık ıslanıyor mu?"
gen: slot=bez_islanmasi_yeterli; type=boolean
CANDIDATE — clinician to approve wording. **Inverted polarity:** "hayır" is the concerning answer; any
rule reading this slot must test `== false`. **Feeds HB-C3 dehydration (§2.2).**

**Q8 — Yellowing of skin or eyes** · archetype: `OBSERVATION.symptom_sign.v1` · source: NE-S1 PDF p. 13 (whites of the eyes); NE-S4 rec 1.1.1
> "Bebeğinizin cildinde ya da gözlerinin beyaz kısmında sararma fark ettiniz mi?"
gen: slot=sararma; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q9.

**Q9 — Very pale or chalky stool** · archetype: `OBSERVATION.symptom_sign.v1` · source: NE-S1 PDF p. 21 ("gaita rengi (açık renk)"); NE-S4 recs 1.1.1 and 1.7.1 ("pale chalky stools")
> "Bebeğinizin kakası çok açık renkli ya da tebeşir gibi beyaz mı?"
gen: slot=acik_renkli_kaka; type=boolean; ask_if=sararma == true
CANDIDATE — clinician to approve wording. "Kaka" is the everyday parent word; a stool-colour card
(visual, no numbers) would help and is a design decision for the clinician.

**Q10 — Fever** · archetype: `OBSERVATION.symptom_sign.v1` · source: NE-S3 PDF p. 8 ("ateş"); NE-S5 rec 1.4.9 (abnormal temperature)
> "Bebeğinizde ateş olduğunu fark ettiniz mi?"
gen: slot=ates; type=boolean
CANDIDATE — clinician to approve wording. No temperature value is requested (invariant 22). NE-S5 rec
1.4.4 warns fever may be absent in a seriously ill baby, so a "hayır" here is not reassurance.
**Feeds HB-C3 fever under three months (§2.2).**

**Q11 — Unusually sleepy or hard to wake** · archetype: `OBSERVATION.symptom_sign.v1` · source: NE-S2 Tablo 1 ("uykuya eğilim"); NE-S3 PDF p. 8 ("uykuya meyil"); NE-S5 rec 1.4.9 ("unresponsive or unrousable")
> "Bebeğiniz her zamankinden daha uykulu ya da uyandırması zor mu?"
gen: slot=asiri_uykululuk; type=boolean
CANDIDATE — clinician to approve wording. **Feeds HB-C3 lethargy (§2.2).**

**Q12 — Laboured breathing or grunting** · archetype: `OBSERVATION.symptom_sign.v1` · source: NE-S2 Tablo 1 ("inleme"); NE-S5 rec 1.4.9 ("grunting respirations")
> "Bebeğinizin nefes alırken zorlandığını ya da inlediğini fark ettiniz mi?"
gen: slot=nefes_zorlanmasi; type=boolean
CANDIDATE — clinician to approve wording. Parent-reportable form only; no retraction grading
(04 §8.1 rule 1). **Feeds HB-C3 breathing difficulty (§2.2).**

*(12 candidate questions: 12 source-backed; 6 neutral symptom captures for newborn emergencies —
Q6, Q7, Q8, Q10, Q11, Q12.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **NE-S3 is 2018** — no newer TND high-risk follow-up guideline was listed on the TND index on
   2026-09-26. A Ministry newborn follow-up protocol (Bebek, Çocuk, Ergen İzlem Protokolleri) was **not
   retrieved**. **NO SOURCE FOUND (Ministry source) — clinician must supply** if it should outrank TND.
2. **Jaundice is absent from HB-C3's named paediatric list** (fever under three months, lethargy/poor
   feeding, breathing difficulty, rash, dehydration, ingestion, age bands). Q8/Q9 feed nothing even after
   HB-C3 closes. **Paediatrician must decide.**
3. **Q2 may duplicate the identity record** — if the proxy session already carries the baby's date of
   birth, Q2 should be dropped. **Product/clinician decision.**
4. **Omitted to stay at twelve — sourced, clinician may swap in:** sibling who needed phototherapy for
   jaundice (NE-S1 PDF p. 16; NE-S4 rec 1.2.1); dark urine (NE-S1 PDF p. 12; NE-S4 rec 1.1.1); vomiting
   and diarrhoea (NE-S3 PDF p. 8; NE-S5 rec 1.4.9); weak or high-pitched cry, colour change, rash,
   seizures (NE-S5 rec 1.4.9). Birth weight and gestational weeks are numeric — never asked as free text
   (invariant 22); they come from the discharge summary.
5. **Parent wellbeing** — postnatal mood of the answering parent is out of scope for this pack and
   belongs to the consented wellbeing-screening flow. **Clinician to decide** whether to link it.
6. **Copyright / snapshot licence** — TND guidelines forbid copying "kısmen veya tamamen" without
   written permission and citation; NICE texts are © NICE. A committed verbatim snapshot needs **TND's
   written permission or a legal-review decision.** **Human must supply.**
7. **Standard duration slot wording** — the generator adds `sikayet_suresi` ("Bu şikâyetiniz ne zamandır
   var?"), which addresses the parent's own complaint; for a proxy session it should refer to the baby.
   **Clinician to decide** (generator-level, not this proposal).
8. **Every triage level and all three RED axes** (invariant 21), and the paediatric age bands —
   deliberately **not** assigned; **paediatrician** (HB-C3) must supply.
9. **openEHR** — leaf paths deferred (INT-032); no newborn-specific archetype root in the OPT.
10. **PolicyGuard lexicon is itself unsigned (HB-C23).**

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy** — `siz` to the parent, "bebeğiniz" throughout, ≤ B1, one question mark per
  item, ≤ fifteen words per sentence, no diagnosis/treatment/prognosis wording; each item CANDIDATE.
- **Inv. 7** — newborn emergencies stay in `base.life_threat` paediatric rules (HB-C3); this pack adds
  no rule.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at sign-off.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals; no temperature, weight or week count is requested; date of birth is a
  date picker.
- **HB-C1 / HB-C3** — awaits clinician sign-off and a paediatrician's signature; NOT served.
