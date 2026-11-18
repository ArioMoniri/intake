# Çocuk Metabolizma Hastalıkları (Paediatric Metabolic Diseases) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Metabolizma Hastalıkları
(Paediatric Metabolic Diseases / inborn errors of metabolism)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. Paediatric: every question is addressed to the
**parent/guardian (proxy)**. This file is a *proposal for a clinician to sign off*. It assigns **no**
authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Türkiye-first sourcing achieved for this specialty.** S1 is the **T.C. Sağlık Bakanlığı** (Halk
  Sağlığı Genel Müdürlüğü) *Yenidoğan Tarama Programı* page — the MoH tier that files/09 §2 and the L0
  pack header name first. S3 is the **Çocuk Beslenme ve Metabolizma Derneği (CBMD)** — a genuine Turkish
  specialty society. S2 (BIMDG) is an international named-body corroborator for the decompensation red
  flag.
- **Life-threatening metabolic emergencies stay in `base.life_threat` (invariant 7).** Acute
  **metabolik dekompansasyon** — e.g. hyperammonaemic **encephalopathy** in a urea-cycle disorder, an
  organic-acidaemia crisis, or hypoglycaemic collapse — is life-threatening; per invariant 7 the
  `base.life_threat` sibling set is authoritative and *nothing may extend it*. This proposal **only feeds
  intake questions** that surface the early symptoms for the clinician and the rules engine — it does
  **not** author, relax or duplicate any life-threat threshold, and it speaks **no** RED action script or
  emergency number.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's own
  wording is quoted verbatim; no level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch) / PDF text extraction (`pdftotext`). Before sign-off, each verbatim
  sentence MUST be re-checked against the **primary published text** and committed as a **verbatim source
  snapshot** with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any
  derived rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_metabolizma_hastaliklari.yaml` (an L0
  draft that never serves) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — T.C. Sağlık Bakanlığı (HSGM) — Yenidoğan Tarama Programı (Türkiye-first, MoH)
- **guideline_id (proposed):** `TCSB-HSGM-NTP`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü (HSGM)
- **Version / year:** page current 2026; panel dates as quoted below
- **URL:** https://hsgm.saglik.gov.tr/tr/tarama-programlari/ntp.html
- **Verbatim (program başlangıcı):**
  > "Ulusal Yenidoğan Tarama Programı ise Fenilketonüri taramasına Konjenital Hipotiroidi taramasının
  > eklenmesi ile 25.12.2006 tarihinde başlatılmıştır."
- **Verbatim (panele eklemeler):**
  > "2008 Ekim'de Biyotinidaz eksikliği, Ocak 2015'den itibaren ise Kistik Fibrozis taraması panele
  > eklenmiştir."
  > "Tarama paneline 09.05.2022 tarihi itibariyle Spinal Müsküler Atrofi (SMA) eklenmiştir."
- **Verbatim (topuk kanı):**
  > "İl genelindeki tüm sağlık birimlerinde Yenidoğan Tarama Programı için alınacak topuk kanları, İl
  > Sağlık Müdürlüğünde toplanarak, Ankara ve İstanbul Tarama Laboratuvarlarına gönderilmektedir."
- **Verbatim (şüpheli sonuç):**
  > "…tarama sonucu şüpheli çıkan bebekler ilgili kliniklere yönlendirilmektedir."
- **Confidence: MEDIUM-HIGH (content), MEDIUM (exact-URL provenance).** Retrieved via automated fetch;
  the fetcher reported a canonical-URL ambiguity between `.../tarama-programlari/ntp.html` and
  `.../cocukergen-tp-liste/yenidogan_tarama_programi.html` — reconcile the exact live URL before sign-off.

### S2 — BIMDG — "Undiagnosed Hyperammonaemia: Diagnosis and Immediate Management" (named-body corroborator)
- **guideline_id (proposed):** `BIMDG-UNDIAG-HYPERAMMONAEMIA`
- **Publishing body:** British Inherited Metabolic Disease Group (BIMDG)
- **Version / year:** © BIMDG 2008; **"Last reviewed April 2017"**
- **URL:** https://bimdg.org.uk/wp-content/uploads/2024/12/Hyperammonaemiaand_manage_2016_415469_09092016.pdf
  · index: https://bimdg.org.uk/emergency-guides/
- **Verbatim (clinical presentation):**
  > "The symptoms are highly variable. Neonates often have an overwhelming illness, although respiratory
  > alkalosis is an early sign. In infants the symptoms are more often 'gastro-intestinal' such as
  > vomiting and anorexia combined with slow developmental progress. In older children neurological
  > symptoms usually predominate with episodes of encephalopathy, often combined with slow developmental
  > progress."
- **Verbatim (urgency):**
  > "In any patient values in excess of 200 mol/l require urgent attention."
- **Note:** the differential lists urea-cycle enzyme defects, organic acidurias and (with hypoglycaemia
  predominating) fatty-acid oxidation disorders. **Confidence: HIGH (content).** The companion
  BIMDG "Undiagnosed problems" HTML page (https://bimdg.org.uk/emergency-guides/undiagnosed-problems/)
  returned HTTP 404 to automated fetch — the PDF above was extracted verbatim instead.

### S3 — Çocuk Beslenme ve Metabolizma Derneği (CBMD) — "Kalıtsal Metabolik Hastalıklar Hakkında Bilgilendirme" (Türkiye-first society)
- **guideline_id (proposed):** `CBMD-KMH-BILGILENDIRME`
- **Publishing body:** Çocuk Beslenme ve Metabolizma Derneği (CBMD)
- **Version / year:** patient/family information page, undated in the retrieved excerpt — see §4 gap
- **URL:** https://cbmd.org.tr/kalitsal-metabolik-hastaliklar-hakkinda-bilgilendirme
- **Verbatim (akraba evliliği — Türkiye riski):**
  > "Akraba evliliğinin sık görüldüğü ülkemizde dünya ortalamasına göre hastalığın görülme sıklığı çok
  > daha fazladır."
- **Verbatim (stres/enfeksiyon tetikleyicisi — biyotinidaz):**
  > "enfeksiyon gibi stresli olaylarda hastalık belirtileri ortaya çıkabilir"
- **Verbatim (beslenme tetikli belirti — herediter fruktoz intoleransı):**
  > "fruktoz alımı ile kusma, iştahsızlık, halsizlik"
- **Confidence: LOW.** Retrieved via automated fetch that resolved toward the site root
  (`http://cbmd.org.tr/`); the per-disease page URL and each verbatim MUST be re-verified on the live
  CBMD page before sign-off. Included as a Türkiye-first *society* corroborator only; it grounds **no**
  hard threshold.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes**. A slot whose leaf path is not yet authored carries
**`openehr_deferred_reason`** (INT-032, P3 export tier) — it is **not** invented. So each item below
binds to an archetype **root**; the specific leaf path is **deferred**, never fabricated.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the current complaint (onset/course) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Newborn-screening (topuk kanı) suspicious result (S1) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 4 | Vomiting / refusal to feed (S2, S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Unusual drowsiness / lethargy / hard to rouse (S2 encephalopathy) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Symptoms triggered/worsened by illness / fever / fasting (S2, S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Developmental regression / slow progress (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Known inherited-metabolic-disease diagnosis (S2) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 9 | Special diet / metabolic formula (S3) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 10 | Current medications / supplements (carnitine, vitamins) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 11 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 12 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine / `base.life_threat` only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 13 | **Family history of metabolic disease + consanguinity (S3 "akraba evliliği")** | **no archetype fits — export blocked (INT-041 posture)** | — | — |

Notes:
- Item 13: as in the cardiology and endocrinology proposals, the committed `.opt` exposes **no
  family-history archetype root**, so capturing family history of metabolic disease and consanguinity
  (akraba evliliği) has **no export target today → export blocked (INT-041 posture)**; do not invent an
  at-code path. The *reason-for-visit* framing of the concern (Q4) still binds via
  `EVALUATION.reason_for_encounter.v1`, but the family-history/consanguinity fact does not.
  Clinician/architecture decision needed (candidate: INT-032 archetype addition).
- **Growth / anthropometry** (failure to thrive is common in IEM) has **no archetype root** in the
  committed `.opt` → any measured value would be **export blocked (INT-041 posture)**; not captured as a
  numeric item here.
- **PHQ-9 / GAD-7 not bound here.** Those are the *adult* consented-wellbeing screens; paediatric
  applicability is age-dependent and out of scope for this metabolic red-flag proposal.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian (proxy)** about *çocuğunuz*;
one concern per question (invariant 2: one question per turn); empathetic; no diagnosis/treatment/
prognosis language. **All marked "CANDIDATE — clinician to approve wording".** No bare numerals appear
(invariant 22); no emergency number or action script is spoken here — RED action scripts belong to
`base.life_threat` / triage, never to an intake question.

> Triage note for every red-flag-derived item: the level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. The authoritative RED for acute
> metabolic decompensation / hyperammonaemic encephalopathy comes from `base.life_threat` with all three
> RED axes (route × register × location, invariant 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Renumbering, old → new — sections outside §3 still use the old numbers: Q1
unchanged · Q2 removed (duplicates base `hpi.onset_date` + `hpi.trajectory`) · Q3 → Q2 · Q4 → Q3
(family history) + Q4 (consanguinity) · Q5 → Q5 · Q6 → Q6 · Q7 → Q7 (if Q5 or Q6 yes) · Q8 → Q8
(loss of skills) + Q9 (slowed development) · Q9 → Q10 · Q10 → Q11 · Q11 → Q12 · Q12 removed
(duplicates base `allergies`).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün getiren temel konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Newborn-screening (topuk kanı) result** · archetype: `EVALUATION.problem_diagnosis.v1` · source:
S1 ("tarama sonucu şüpheli çıkan bebekler ilgili kliniklere yönlendirilmektedir")
> "Çocuğunuzun doğumdan sonra yapılan topuk kanı taramasında bir sorun bildirildi mi?"
gen: slot=topuk_kani_sorunu; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Family history of metabolic disease** · archetype: `EVALUATION.reason_for_encounter.v1`
(family-history fact export-blocked, §2 item 13) · source: S3 ("Akraba evliliğinin sık görüldüğü
ülkemizde … görülme sıklığı çok daha fazladır")
> "Ailenizde kalıtsal bir metabolizma hastalığı olan biri var mı?"
gen: slot=ailede_metabolizma_hastaligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Parental consanguinity** · archetype: `EVALUATION.reason_for_encounter.v1` (consanguinity fact
export-blocked, §2 item 13) · source: S3 ("Akraba evliliğinin sık görüldüğü ülkemizde … görülme
sıklığı çok daha fazladır")
> "Bu soruyu yalnızca sağlık değerlendirmesi için soruyoruz: anne ile baba arasında akrabalık var mı?"
gen: slot=ebeveyn_akrabaligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Vomiting / refusal to feed** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("vomiting
and anorexia") + S3 ("kusma, iştahsızlık")
> "Çocuğunuz son zamanlarda sık sık kusuyor ya da beslenmeyi reddediyor mu?"
gen: slot=kusma_beslenme_reddi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician
+ rules-engine confirmation — NOT authoritative)** per S2; when part of a decompensation the emergency is
owned by `base.life_threat`.

**Q6 — Unusual drowsiness / lethargy** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
("episodes of encephalopathy")
> "Çocuğunuz alışılmadık şekilde uykulu, halsiz ya da zor uyandırılır hâle geldi mi?"
gen: slot=uykulu_tepkisiz; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)** per S2;
altered consciousness / encephalopathy is owned by `base.life_threat`.

**Q7 — Symptoms triggered by illness / fasting (if Q5 or Q6 yes)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S2 (decompensation with intercurrent illness) + S3 ("enfeksiyon
gibi stresli olaylarda hastalık belirtileri ortaya çıkabilir")
> "Bu belirtiler çocuğunuz hastalandığında ya da uzun süre aç kaldığında artıyor mu?"
gen: slot=hastalik_aclikla_artis; type=boolean; ask_if=kusma_beslenme_reddi == true || uykulu_tepkisiz == true
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, …)** per S2/S3;
metabolic stress can precipitate decompensation — the emergency is owned by `base.life_threat`.

**Q8 — Developmental regression (loss of skills)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: cross-cited from `cocuk_genetik_hastaliklari.md` S1 (NHS GeNotes: "developmental regression
(loss of previously gained skills) are red flags that require urgent further assessment") —
verification finding 16
> "Çocuğunuz daha önce yapabildiği oturma, yürüme ya da konuşma gibi becerileri kaybetti mi?"
gen: slot=beceri_kaybi; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Slowed developmental progress** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 ("slow
developmental progress")
> "Çocuğunuzun gelişimi son zamanlarda yavaşladı mı?"
gen: slot=gelisim_yavaslamasi; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Known metabolic diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S2 (history)
> "Çocuğunuzun daha önce konmuş bir metabolizma hastalığı tanısı var mı?"
gen: slot=metabolizma_tanisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q11 — Special diet / special formula** · archetype: `ACTION.medication.v1` · source: general intake
(S3 context)
> "Çocuğunuz özel bir diyet ya da özel bir mama kullanıyor mu?"
gen: slot=ozel_diyet_mama; type=boolean
CANDIDATE — clinician to approve wording.

**Q12 — Current medications / supplements** · archetype: `ACTION.medication.v1` · source: general intake
(history)
> "Çocuğunuzun düzenli kullandığı bir ilaç, vitamin ya da takviye var mı?"
gen: slot=ilac_vitamin_takviye; type=boolean
CANDIDATE — clinician to approve wording. Kept as a specialty-specific (supplement / special formula)
ask (verification finding 5).

*(12 candidate questions; 3 red-flag-derived — Q5, Q6, Q7 — plus screening, family history, and general
intake.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first *decompensation* red-flag verbatim** — S1 (MoH) covers *screening*, not the acute
   decompensation warning signs; the decompensation flags (Q5–Q7) are grounded on the international
   named-body S2 (BIMDG) plus the LOW-confidence society S3 (CBMD). A **Türkiye MoH / uzmanlık derneği**
   verbatim specifically for acute metabolic decompensation warning signs (kusma, bilinç değişikliği,
   enfeksiyon/açlık tetiklemesi, acil başvuru) is **NO SOURCE FOUND — clinician to supply** (candidates:
   a CBMD acute-management guideline; a TMPD congress guideline; T.C. Sağlık Bakanlığı klinik protokolü).
2. **CBMD (S3) page/URL and verbatim reconciliation** — the S3 quotes were captured by an automated
   fetch that resolved toward the site root; the exact per-disease page URL and each verbatim MUST be
   re-verified on the live CBMD site before sign-off. **Confidence LOW.**
3. **MoH (S1) canonical URL reconciliation** — the fetcher reported ambiguity between
   `.../tarama-programlari/ntp.html` and `.../cocukergen-tp-liste/yenidogan_tarama_programi.html`;
   reconcile the exact live URL and re-verify the panel dates against the primary page.
4. **Full national screening panel (MSUD, homosistinüri, galaktozemi, KAH)** — search summaries mention
   additional panel diseases, but the S1 page fetch returned verbatim only for FKU, konjenital
   hipotiroidi, biyotinidaz, kistik fibrozis and SMA. Any wider panel claim is **NO SOURCE FOUND
   (verbatim) — clinician to reconcile** against the primary MoH page.
5. **Characteristic urine/body odour red flag** (e.g. maple-syrup odour in MSUD, sweaty-feet odour in
   isovaleric acidaemia) — a classic IEM sign, but **NO SOURCE was retrieved** verbatim, so no odour
   question is proposed. **NO SOURCE FOUND — clinician to supply** (candidate: SSIEM / BIMDG condition
   guideline).
6. **Hypoglycaemia red flags** — BIMDG has a dedicated "undiagnosed hypoglycaemia" guideline, but it was
   not retrieved verbatim here (the undiagnosed-problems index 404'd to automated fetch). **NO SOURCE
   FOUND (verbatim) — clinician to supply.**
7. **Emergency-regimen / "sick day rules" verbatim for a KNOWN IEM child** — the concept that a child
   with a known IEM who is unwell/vomiting/not feeding needs urgent measures is central to Q7 but was not
   captured verbatim (BIMDG paediatric-guidelines page 404'd to automated fetch). **NO SOURCE FOUND
   (verbatim) — clinician to supply** (candidate: BIMDG paediatric emergency regimen).
8. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21) —
   deliberately **not** assigned here; acute metabolic decompensation / hyperammonaemic encephalopathy is
   owned by `base.life_threat` (invariant 7). **`packages/protocols/triage` + `base.life_threat` must
   supply**, with committed `source` snapshots, before anything compiles.
9. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032);
   not fabricated. Family history / consanguinity (item 13) and any growth measurement have **no
   archetype root** → export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 7** — life-threatening metabolic emergencies (acute decompensation, hyperammonaemic
  encephalopathy, hypoglycaemic collapse) are left to `base.life_threat`; this proposal only feeds
  questions and neither extends nor relaxes that sibling set.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, addressed to the parent/guardian
  (proxy), B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in questions; the compiler must still expand any numeral before TTS.
  (The verbatim S2 quote "in excess of 200 mol/l" and the S1 panel dates are retained only inside the §1
  source block, never in patient-facing copy.)
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies Türkiye-first candidate source
  S1 (MoH/HSGM), Türkiye-first society corroborator S3 (CBMD, LOW confidence) and international
  named-body corroborator S2 (BIMDG) for that block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served. `cocuk_metabolizma_hastaliklari.yaml` is
  an L0 draft and is untouched.
