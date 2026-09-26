# Romatoloji (Rheumatology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Romatoloji (Rheumatology)
Taxonomy id: `romatoloji` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the primary sources are the Türkiye Romatoloji Derneği (TRD) patient booklets
  (romatoid artrit, ankilozan spondilit, Behçet, ailesel Akdeniz ateşi, sedef romatizması) and TRD's
  "Romatolog Kimdir?" page. The booklets are **undated lay documents**, not versioned guidelines. The
  British Society for Rheumatology (BSR) 2020 giant-cell arteritis guideline is the international
  source for the GCA item.
- **Quotation notice:** each TRD booklet states that public quotation requires the Society's
  permission. Quotes below are therefore kept to **short fragments** for provenance, and committing a
  verbatim snapshot needs TRD permission (§4 gap 2).
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7:** giant-cell arteritis and cauda equina are in `base.life_threat`'s six-rule named-gap
  list; sudden vision loss is `rf.stroke_fast` territory (§2.2). This proposal does not add to or extend
  `base.life_threat`; Q7 and Q12 are **gate inputs only**.
- **Verification caveat (every quote in §1):** captured by automated retrieval on 2026-09-26 (TRD PDFs
  text-extracted locally with `pdftotext` from the fetch tool's cached copy). The booklets use a legacy
  Turkish font encoding; glyphs were normalised (› → ı, ﬂ → ş, ¤ → ğ, ‹ → İ) and **must be re-checked
  against the rendered PDF**. Before sign-off each sentence MUST be committed as a verbatim snapshot with
  `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule stays
  `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/romatoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### R-S1 — TRD, *Romatoid Artrit ve Tedavisi* (patient booklet, Türkiye)
- **guideline_id (proposed):** `TRD-HASTA-RA` (lay booklet, NOT a guideline) · **Date:** none shown
- **URL:** https://www.romatoloji.org/Dokumanlar/HastaKitapciklari/RAT.pdf · **retrieved_on:** 2026-09-26
- **Verbatim fragments (p. 3, "Romatoid Artrit Ne Tür Yakınmalara Neden Olur?"):**
  > "eklemlerde ağrı, tutukluk ve şişlik gelişir"
  > "küçük eklemleri çift taraflı olarak tutmaktadır"
  > "Sabahları ve uzun süreli hareketsizlikten sonra eklemlerde tutukluk (katılık/sertlik) görülür."
- **Confidence: MEDIUM** — Turkish rheumatology society, undated patient booklet.

### R-S2 — TRD, *Ankilozan Spondilit ve Tedavisi* (patient booklet, Türkiye)
- **guideline_id (proposed):** `TRD-HASTA-AS` · **Date:** none shown
- **URL:** https://www.romatoloji.org/Dokumanlar/HastaKitapciklari/AST.pdf · **retrieved_on:** 2026-09-26
- **Verbatim fragments (inflammatory back pain features, list items):**
  > "Kırk yaştan önce başlaması" · "Sinsi başlangıç göstermesi"
  > "Dinlenmeyle, özellikle gecenin 2. yarısında veya sabaha karşı ortaya çıkması ve hareketle
  > azalması"
  > "Özellikle sabahları ilk kalkışta ortaya çıkan topuk veya ayak tabanı ağrısı"
  > "Gözün beyaz kısmında birkaç gün veya daha uzun süren kızarıklık, ağrı veya bulanık görme (üveit)"

### R-S3 — TRD, *Behçet Hastalığı* (patient booklet, Türkiye)
- **guideline_id (proposed):** `TRD-HASTA-BEHCET` · **Date:** none shown
- **URL:** https://www.romatoloji.org/Dokumanlar/HastaKitapciklari/BHT.pdf · **retrieved_on:** 2026-09-26
- **Verbatim fragments:**
  > "Ağız yaralarına hemen hemen her hastada rastlanır"
  > "Genellikle ayda bir veya birkaç kez tekrar eder"
  > (genital) "Tıpkı ağız yaraları gibi ağrılı olurlar."
  > (eye) "Bulanık görme, görmede azalma, ani görme kaybı, gözde ağrı, kanlanma ve ışıktan rahatsızlık
  > duyma gibi yakınmalara neden olabilir."
  > (vessels) "En sık bacaklardaki toplardamarlarda iltihap görülür ve ani şişlik ile ortaya çıkar"

### R-S4 — TRD, *Ailesel Akdeniz Ateşi* (patient booklet, Türkiye)
- **guideline_id (proposed):** `TRD-HASTA-FMF` · **Date:** none shown
- **URL:** https://www.romatoloji.org/Dokumanlar/HastaKitapciklari/AAAT.pdf · **retrieved_on:** 2026-09-26
- **Verbatim fragments ("Hastalığın Belirtileri Nelerdir?"):**
  > "Hastalık ataklar ile seyreder."
  > "ateşin eşlik ettiği karın ağrısı, göğüs ağrısı ve eklemlerde ağrı, şişme olur ve 3-4 gün içinde
  > kendiliğinden geçer."
  > "bazen hastanın acil servise başvurmasına yol açacak kadar şiddetli olabilir."

### R-S5 — TRD, *Sedef Romatizması ve Tedavisi* (patient booklet, Türkiye)
- **guideline_id (proposed):** `TRD-HASTA-PSA` · **Date:** none shown
- **URL:** https://www.romatoloji.org/Dokumanlar/HastaKitapciklari/SRT.pdf · **retrieved_on:** 2026-09-26
- **Verbatim fragments:**
  > "Deride pullanma gösteren beyaz renkli sedef lezyonları genellikle romatizmadan önce ortaya çıkar."
  > "saçlı deride, genital (cinsel) bölgede ve tırnaklarda da gelişebilir."

### R-S6 — TRD, "Romatolog Kimdir?" (Türkiye; scope of the specialty)
- **guideline_id (proposed):** `TRD-ROMATOLOG-KIMDIR` · **Date:** none shown (text says "2019 yılı itibariyle")
- **URL:** https://www.romatoloji.org/OgrenmeMerkezi/HastalarIcin/RomatologKimdir · **retrieved_on:** 2026-09-26
- **Verbatim (scope list):**
  > "Romatoid artrit, ankilozan spondilit, sedef romatizması, behçet hastalığı, ailevi akdeniz ateşi,
  > sistemik lupus eritematozus (SLE), gut, skleroderma, çocukluk çağında başlayan romatizmal
  > hastalıklar, sjögren sendromu"
- **Use:** scope check only — SLE, gut, skleroderma and Sjögren are in scope but have **no TRD
  booklet**; see §4 gap 4.

### R-S7 — BSR, *Guideline on diagnosis and treatment of giant cell arteritis: executive summary* (2020)
- **guideline_id (proposed):** `BSR-GCA-2020`
- **Citation:** Mackie SL, et al. *Rheumatology (Oxford)*. 2020;59(3):487–494. doi:10.1093/rheumatology/kez664
- **URL:** https://academic.oup.com/rheumatology/article/59/3/487/5714025 · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "headache; scalp tenderness/hyperaesthesia jaw or tongue claudication; temporal artery tenderness,
  > nodularity or reduced pulsation; visual manifestations including diplopia or changes to colour
  > vision; limb claudication; PMR (pain and stiffness of the shoulder and hip girdles) and fevers,
  > sweats or weight loss."
  > "patients should be evaluated by a specialist ideally on the same working day if possible and in all
  > cases within 3 working days."
  > "Patients presenting with a history of new visual loss (transient or permanent) or double vision
  > should be evaluated as soon as possible on the same calendar day by an ophthalmologist."
- **Confidence: MEDIUM–HIGH** — publisher page read via fetch summary; re-verify against the PDF.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Joint swelling | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Small joints of hands or feet | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Morning joint stiffness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5a | Back pain present (gate) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5b | Back pain worse at rest | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5c | Back pain eased by movement | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Heel / sole pain on first steps | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Red, painful white of the eye | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Recurrent painful mouth sores | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Painful genital sores | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Self-limiting fever attacks | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Scaly skin patches (white scale) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Jaw pain or tiredness on chewing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Rheumatology alarm sign | Source | base.life_threat item | This proposal's role |
|---|---|---|---|
| Giant-cell arteritis features (jaw claudication, new headache, scalp tenderness, visual symptoms) | R-S7 | GCA (six-rule named gap) | Q12 is a gate **input** only |
| Sudden vision loss or double vision (GCA, Behçet uveitis) | R-S3 ("ani görme kaybı"), R-S7 | `rf.stroke_fast` (named gap); GCA | Q7 is a gate **input** only; see göz proposal Q3 |
| Back pain with bladder/bowel or saddle symptoms | NO SOURCE retrieved | cauda equina (six-rule named gap) | Not drafted; left to base |
| Sudden painful leg swelling (Behçet vein inflammation) | R-S3 | **absent** (no venous-thrombosis rule) | Not drafted; §4 gap for the base.life_threat owner |
| Hot swollen joint with fever | NO SOURCE retrieved | `rf.sepsis_like` (named gap) | Not drafted; §4 gap |

### 2.3 Red-flag candidates found — **for physician review — not encoded**

None of these is a rule, a level or a route.

| # | Candidate | Source (verbatim anchor) |
|---|---|---|
| RF-1 | Suspected GCA — specialist same working day if possible, within three working days | R-S7 |
| RF-2 | New visual loss or double vision with suspected GCA — ophthalmology same calendar day | R-S7 |
| RF-3 | Behçet eye involvement including sudden vision loss | R-S3 "ani görme kaybı" |
| RF-4 | Behçet leg-vein inflammation with sudden swelling, severe pain, difficulty walking | R-S3 |
| RF-5 | FMF attack severe enough to need the emergency department (may mimic appendicitis) | R-S4 |
| RF-6 | Recurrent eye redness, pain or blurred vision in spondyloarthritis (uveitis) | R-S2 |

---

## 3. Candidate B1 Turkish pre-visit questions (14)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Duration thresholds from the
sources (stiffness length, back-pain duration, attack length) are **not** put into patient copy; the
pack's `sikayet_suresi` slot captures duration. Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün romatoloji polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Joint swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S1 ("eklemlerde ağrı, tutukluk ve şişlik"), R-S4 ("eklemlerde ağrı, şişme")
> "Eklemlerinizde şişlik fark ettiniz mi?"
gen: slot=eklem_sisligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Small joints of hands or feet** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S1 ("küçük eklemleri çift taraflı")
> "Ellerinizin ya da ayaklarınızın küçük eklemlerinde ağrı veya şişlik var mı?"
gen: slot=kucuk_eklem_agri_sislik; type=boolean
CANDIDATE — clinician to approve wording. Symmetry is a clinician follow-up.

**Q4 — Morning joint stiffness** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S1 (morning joint stiffness; own wording)
> "Sabah uyandığınızda eklemlerinizde sertlik hissediyor musunuz?"
gen: slot=sabah_eklem_sertligi; type=boolean
CANDIDATE — clinician to approve wording. Own wording (TRD quotation notice, §0). The booklet's
duration figure is not asked (§4 gap 6).

**Q5a — Back pain present** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S2 (inflammatory back pain; own wording)
> "Belinizde ya da sırtınızda ağrı var mı?"
gen: slot=bel_sirt_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q5b and Q5c, so neither assumes back pain. The
former Q5 joined two claims in one answer; it is split into one claim per item (verification wave 6).

**Q5b — Back pain worse at rest** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S2 (worse with rest; own wording)
> "Bu ağrı dinlendiğinizde artıyor mu?"
gen: slot=bel_agrisi_dinlenince_artar; type=boolean; ask_if=bel_sirt_agrisi == true
CANDIDATE — clinician to approve wording. Asked only when Q5a is yes.

**Q5c — Back pain eased by movement** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S2 (eased by movement; own wording)
> "Bu ağrı hareket ettiğinizde hafifliyor mu?"
gen: slot=bel_agrisi_hareketle_azalir; type=boolean; ask_if=bel_sirt_agrisi == true
CANDIDATE — clinician to approve wording. Asked only when Q5a is yes.

**Q6 — Heel or sole pain on first steps** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S2 (heel or sole pain on first rising; own wording)
> "Sabah yataktan kalkıp yere bastığınızda topuğunuz ya da ayağınızın altı ağrıyor mu?"
gen: slot=sabah_topuk_taban_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Own wording (TRD quotation notice, §0).

**Q7 — Red, painful white of the eye (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S2 (redness or pain of the white of the eye; own wording), R-S3 (Behçet eye)
> "Gözünüzün akında günlerce geçmeyen kızarıklık ya da ağrı oldu mu?"
gen: slot=goz_akinda_kizariklik_agri; type=boolean
CANDIDATE — clinician to approve wording. Own wording (TRD quotation notice, §0). **Overlap: sudden
vision loss stays with base → `rf.stroke_fast` / GCA (§2.2).**

**Q8 — Recurrent painful mouth sores** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S3 ("Ağız yaralarına hemen hemen her hastada rastlanır"; "tekrar eder")
> "Ağzınızda sık sık tekrarlayan ağrılı yaralar çıkıyor mu?"
gen: slot=tekrarlayan_agiz_yarasi; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Painful genital sores** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S3 ("Cinsel Bölge Yaraları … ağrılı olurlar")
> "Cinsel bölgenizde ağrılı yaralar çıktığı oldu mu?"
gen: slot=genital_agrili_yara; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Sensitive item: files/13 §13 makes sexual or reproductive
history `text_first`, so it is shown as text first rather than spoken.

**Q10 — Self-limiting fever attacks** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S4 (attacks that resolve on their own; own wording)
> "Ara ara gelen ve birkaç günde kendi kendine geçen ateşleriniz oluyor mu?"
gen: slot=kendiliginden_gecen_ates; type=boolean
CANDIDATE — clinician to approve wording. Own wording (TRD quotation notice, §0). Accompanying
abdominal, chest or joint pain is a clinician follow-up (one concern per turn).

**Q11 — Scaly skin patches** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S5 (white scaling skin lesions; own wording)
> "Derinizde üzeri beyaz pullarla kaplı lekeler oldu mu?"
gen: slot=pullu_deri_lekesi; type=boolean
CANDIDATE — clinician to approve wording. Own wording (TRD quotation notice, §0); describes only the
white scale and names no condition to the patient. Nail changes (R-S5) are a follow-up.

**Q12 — Jaw pain or tiredness on chewing (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S7 ("jaw or tongue claudication")
> "Yemek çiğnerken çenenizde ağrı ya da yorulma oluyor mu?"
gen: slot=cignerken_cene_agrisi; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: GCA (§2.2).** Source urgency quoted only (RF-1);
no level asserted. Age context is read from the record, not asked here.

*(14 candidate questions after revision: Q5 split into Q5a–Q5c.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish clinical guideline** — the TRD RA national treatment recommendations (RAED
   Dergisi, doi raed.18.18022) were seen only as a search hit and are treatment-focused; not retrieved.
   No TRD diagnostic/referral guideline was found. **NO SOURCE FOUND (verbatim) — clinician must
   supply.**
2. **TRD quotation permission** — the booklets restrict public quotation without the Society's
   permission. Committed verbatim snapshots (clinical content rule) need **TRD permission — human**.
   Patient copy no longer follows TRD wording: Q4–Q7, Q10 and Q11 were reworded in our own words
   (verification wave 6), and the §1 fragments stay minimal provenance only. No HB row exists for TRD
   permission yet; the owner must register one.
3. **EULAR 2016 early-arthritis recommendations** — identified (Combe B, et al. Ann Rheum Dis
   2017;76(6):948–959, doi:10.1136/annrheumdis-2016-210602) but only the abstract was retrieved, which
   carries no recommendation text. **Not quoted.** NICE NG100 (RA) not retrieved (nice.org.uk HTTP 403).
4. **SLE, Sjögren, systemic sclerosis, gout** — in TRD's scope (R-S6) but no source retrieved for
   rash/photosensitivity, dry eyes/mouth, Raynaud or acute gout. **NO SOURCE FOUND.** Not drafted.
5. **Sourced but not drafted** (to stay at twelve): polymyalgia (shoulder/hip-girdle pain and
   stiffness), new headache, scalp tenderness (R-S7); FMF abdominal/chest pain (R-S4); nail changes
   (R-S5); leg-vein swelling (R-S3); family history of FMF (R-S4 genetics section).
6. **Duration thresholds** (morning-stiffness length, back-pain duration, attack length) — present in
   R-S1/R-S2/R-S4 but **not** pinned into patient copy. **Clinician must choose** whether any becomes a
   follow-up.
7. **Septic arthritis, cauda equina, venous thrombosis** — **NO SOURCE retrieved**; the latter two are
   named gaps / absent in `base.life_threat`. **base.life_threat owner / clinician.**
8. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
9. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words, no
  diagnosis/treatment/prognosis wording; *üveit*, *entezit*, *artrit* kept out of patient copy. Checked
  against the Turkish PolicyGuard arms (INT-248 lexicon).
- **Inv. 7** — GCA, sudden vision loss and cauda equina left in `base.life_threat` (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 8).
- **Inv. 22** — no numerals in any candidate question; source durations stay in §1 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources R-S1…R-S7 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
