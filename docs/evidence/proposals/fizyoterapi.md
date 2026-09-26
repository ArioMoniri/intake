# Fizyoterapi (Physiotherapy) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Fizyoterapi (Physiotherapy /
musculoskeletal)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign
off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**,
  written as *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The
  guideline's own urgency wording is quoted verbatim; no level is asserted.
- **Acute deterioration stays in `base.life_threat` (invariant 7).** A neurological emergency such
  as **cauda equina** (new urinary retention / incontinence, saddle anaesthesia, rapidly
  progressive bilateral leg weakness) is not a specialty-pack rule: `files/protocols/base.life_threat.yaml`
  is the universal sibling set evaluated on every session and nothing in a specialty pack may
  extend it. This proposal captures the *symptom* so a clinician + the rules engine can act; it does
  **not** author an emergency script and does **not** add anything to the life-threat set.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / WebSearch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and, per the clinical-content rule, committed as
  a **verbatim source snapshot** with a full `source: {guideline_id, version, date, url,
  retrieved_on}` block. Until then any derived rule stays `status: draft_needs_source` and does
  **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/fizyoterapi.yaml` (an L0 draft) or any
  served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG59 Low back pain and sciatica (serious underlying pathology) · retrieved VERBATIM
- **guideline_id (proposed):** `NICE-LBP-NG59`
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** NG59, published 30 Nov 2016, last updated 11 Dec 2020 (the retrieved excerpt
  reported "December 11, 2020"; confirm current update date on sign-off)
- **Citation:** NICE. *Low back pain and sciatica in over 16s: assessment and management (NG59).*
- **URL:** https://www.nice.org.uk/guidance/ng59 · retrieved via NCBI mirror
  https://www.ncbi.nlm.nih.gov/books/NBK562933/
- **Verbatim (recommendation 1.1.1):**
  > "Think about alternative diagnoses when examining or reviewing people with low back pain,
  > particularly if they develop new or changed symptoms."
- **Verbatim (specific causes named for exclusion):**
  > "specific causes of low back pain, for example, cancer, infection, trauma or inflammatory
  > disease such as spondyloarthritis."
- **Verbatim (scope limitation — supports the invariant-7 note above):**
  > "the evaluation or care of people with sciatica with progressive neurological deficit or cauda
  > equina syndrome" [are NOT covered] … clinicians should recognise these as "potential
  > neurological emergencies" requiring specialist referral.
- **Confidence: HIGH** for the recommendation-1.1.1 wording (fetched from NCBI full-text mirror).
  The exact recommendation numbering ("1.1.1") and the current update date still need primary
  re-verification against nice.org.uk (which returned HTTP 403 to automated fetch — see §4).

### S2 — NICE spinal metastases / metastatic spinal cord compression (spinal red flags) · SEARCH SUMMARY ONLY
- **guideline_id (proposed):** `NICE-MSCC-NG234` (supersedes CG75)
- **Publishing body:** National Institute for Health and Care Excellence (NICE)
- **Version / year:** NG234 "Spinal metastases and metastatic spinal cord compression" (2023);
  predecessor CG75 (2008)
- **URL:** https://www.nice.org.uk/guidance/ng234
- **Content captured (via web-search summary — NOT a verbatim page fetch; both candidate PDFs were
  binary/FlateDecode and could not be parsed):** symptoms suggestive of spinal metastases that
  prompt urgent action were reported as: *pain in the middle (thoracic) or upper (cervical) spine,
  progressive lower (lumbar) spinal pain, severe unremitting lower spinal pain, spinal pain
  aggravated by straining, localised spinal tenderness, and nocturnal spinal pain preventing sleep*;
  neurological symptoms (limb weakness, difficulty walking, sensory loss, bladder or bowel
  dysfunction) warrant whole-spine MRI.
- **Confidence: MEDIUM / UNVERIFIED VERBATIM.** This wording came through a search-engine summary,
  not a direct retrieval of the guideline text. It MUST be re-captured verbatim from the primary
  NICE NG234 text (with recommendation numbers) before it grounds any rule. Treated below as a
  candidate anchor, never as a committed snapshot.

### S3 — (context) T.C. Sağlık Bakanlığı / uzmanlık derneği MSK guideline · NO SOURCE FOUND
- No versioned Türkiye-first (T.C. Sağlık Bakanlığı / HSGM / uzmanlık derneği) clinical guideline for
  fizyoterapi / bel–boyun MSK red flags was located in retrievable form. The generated L0 pack
  header itself records that "files/04 and files/09 name no specific guideline title for the
  'allied_and_reports' cluster — selection awaits the branch clinician". **NO SOURCE FOUND —
  clinician must supply** the correct Turkish primary source and its version/date.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes** (INT-032; HB-C12). So each item below binds to an
archetype **root** actually present in the template; the specific leaf path is **deferred**
(`openehr_deferred_reason`), never fabricated. Roots present in the committed `.opt`:
`reason_for_encounter.v1`, `story.v1`, `symptom_sign.v1`, `problem_diagnosis.v1`, `medication.v1`,
`adverse_reaction_risk.v1`, `phq9.v1`, `gad7.v1`, `triage_outcome.v1`.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / referral reason | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the current MSK complaint (site, onset) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Pain — location / with movement | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Symptom duration / new-or-changed (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Night / unremitting spinal pain (S2 candidate) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Recent trauma / injury (S1 "trauma") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | New limb weakness / difficulty walking (S2 neuro) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Bladder / bowel change, saddle numbness (cauda equina → base.life_threat) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Fever with back pain (S1 "infection") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Unexplained weight loss / feeling unwell (S1 "cancer") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Known MSK diagnoses / prior surgery | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 12 | Current medications (incl. steroids/anticoagulants) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| — | Functional status / ADL / work impact | **no archetype root in `.opt` — export blocked (INT-041 posture)** | — | — |

Notes:
- The functional-status / ADL item has **no matching archetype root** in the committed `.opt`
  (no `OBSERVATION.functional_status`-type root is exposed). Capturing it therefore has no export
  target today → **export blocked (INT-041 posture)**; do not invent an at-code path. Clinician /
  architecture decision needed (candidate: INT-032 / HB-C12 archetype addition).
- Item 8 (cauda equina symptom) is captured for the note only; its authoritative emergency handling
  belongs to `base.life_threat` + the rules engine (invariant 7), not to this pack.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; one concern per question (invariant 2: one question per
turn); empathetic; no diagnosis/treatment/prognosis language; **adult self-report** (physiotherapy
patients are typically self-reporting adults). **All marked "CANDIDATE — clinician to approve
wording".** Per invariant 22 no bare numeral appears; any quantity is spelled out in Turkish
orthography and the compiler must expand it before TTS; there is **no free numeric text entry** on
the clinical critical path.

> Triage note for every red-flag-derived item: the level shown is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED/YELLOW must come from `packages/protocols/triage` with a committed `source`
> snapshot and all three RED axes (route × register × location, invariant 21), none of which are
> supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave4-5.md §B (reviewer's replacement
texts used verbatim). Renumbering, old → new: Q1–Q7 unchanged · Q8 → Q8 (bladder) + Q9 (saddle
numbness) · Q9 → Q10 · Q10 → Q11 · Q11 → Q12 (diagnosis) + Q13 (surgery) · Q12 → Q14. Q5 and Q7 are
held (S2 unverified verbatim). Q8/Q9 are re-cited to the GIRFT CES pathway (March 2026) as
`ortopedi_ve_travmatoloji.md` S1 cites it, which supersedes §4 gap 1 for these two items.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: n/a (general intake)
> "Sizi bugün fizik tedaviye getiren en önemli şikâyetiniz nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Complaint site** · archetype: `OBSERVATION.story.v1` · source: n/a (general intake)
> "Ağrınızı ya da rahatsızlığınızı en çok vücudunuzun hangi bölgesinde hissediyorsunuz?"
CANDIDATE — clinician to approve wording. Onset is asked by the fixed `sikayet_suresi` slot.

**Q3 — Pain with movement / function** · archetype: `OBSERVATION.symptom_sign.v1` · source: n/a (general intake)
> "Bu ağrı günlük hareketlerinizi (yürümek, oturmak, eğilmek gibi) etkiliyor mu?"
gen: slot=gunluk_hareket_etkileniyor; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — New or changed symptoms** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(rec 1.1.1: "new or changed symptoms")
> "Son zamanlarda şikâyetinizde bir değişiklik ya da yeni bir belirti oldu mu?"
gen: slot=yeni_ya_da_degisen_belirti; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: feeds a clinician review of "alternative
diagnoses" per S1; no standalone level.

**Q5 — Night spinal pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2
(SEARCH SUMMARY — "nocturnal spinal pain preventing sleep")
> "Sırt ya da bel ağrınız sizi geceleri uykudan uyandırıyor mu?"
gen: slot=gece_uyandiran_agri; type=boolean; hold=S2 NG234 is unverified verbatim - held until the NG234 verbatim is snapshotted
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending
clinician + rules-engine confirmation — NOT authoritative)** — but S2 is UNVERIFIED VERBATIM (§4);
until re-captured from primary NICE text this stays `draft_needs_source`.

**Q6 — Recent trauma / injury** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("trauma")
> "Bu ağrı bir düşme, çarpma ya da kaza sonrasında mı başladı?"
gen: slot=travma_sonrasi_basladi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: feeds S1 serious-pathology review; no
standalone level here.

**Q7 — New limb weakness / difficulty walking** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S2 (SEARCH SUMMARY — neurological symptoms)
> "Son zamanlarda bacaklarınızda ya da kollarınızda yeni bir güçsüzlük veya yürümekte zorlanma fark
> ettiniz mi?"
gen: slot=yeni_guc_kaybi; type=boolean; hold=S2 NG234 is unverified verbatim - held until the NG234 verbatim is snapshotted
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; S2 UNVERIFIED VERBATIM (§4).

**Q8 — New bladder difficulty or incontinence** · archetype: `OBSERVATION.symptom_sign.v1` · source:
GIRFT National Suspected Cauda Equina Syndrome Pathway, March 2026 (as cited in
`ortopedi_ve_travmatoloji.md` S1: "difficulty initiating micturition or impaired sensation of urinary
flow which may lead to incontinence"); emergency handling → `base.life_threat` (inv 7)
> "Son günlerde idrar yapmakta yeni bir zorluk ya da idrar kaçırma oldu mu?"
gen: slot=yeni_idrar_zorlugu; type=boolean
CANDIDATE — clinician to approve wording. **Layperson-answerable and clinically critical**, so the
question is drafted; but the authoritative red-flag wording and level for cauda equina must come
from a committed source + `base.life_threat` + the rules engine, NOT from this proposal. NG59 is not
cited here: it excludes cauda equina.

**Q9 — New saddle numbness** · archetype: `OBSERVATION.symptom_sign.v1` · source: GIRFT National
Suspected Cauda Equina Syndrome Pathway, March 2026 (as cited in `ortopedi_ve_travmatoloji.md` S1:
"altered perianal, perineal or genital sensation"); emergency handling → `base.life_threat` (inv 7)
> "Bacaklarınızın arasında ya da makat çevresinde yeni bir uyuşma fark ettiniz mi?"
gen: slot=yeni_makat_uyusmasi; type=boolean
CANDIDATE — clinician to approve wording. Same ownership note as Q8: the cauda equina emergency
belongs to `base.life_threat` + the rules engine.

**Q10 — Fever with back pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("infection")
> "Sırt ya da bel ağrınızla birlikte ateşiniz de oluyor mu?"
gen: slot=bel_agrisi_ile_ates; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: feeds S1 "infection" review; the specific
fever + back-pain red-flag threshold is **NO SOURCE FOUND** (§4).

**Q11 — Unexplained weight loss / feeling unwell** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 ("cancer")
> "Sebebini bilmediğiniz kilo kaybı ya da kendinizi genel olarak halsiz hissetme durumunuz var mı?"
gen: slot=aciklanamayan_kilo_kaybi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: feeds S1 "cancer" review; the specific
weight-loss threshold is **NO SOURCE FOUND** (§4).

**Q12 — Known MSK diagnoses** · archetype: `EVALUATION.problem_diagnosis.v1` · source: n/a (history)
> "Daha önce kas, kemik ya da eklemlerinizle ilgili bir tanı aldınız mı?"
gen: slot=kas_iskelet_tanisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q13 — Prior MSK surgery** · archetype: `EVALUATION.problem_diagnosis.v1` · source: n/a (history)
> "Daha önce kas, kemik ya da eklemlerinizden ameliyat oldunuz mu?"
gen: slot=kas_iskelet_ameliyati; type=boolean
CANDIDATE — clinician to approve wording.

**Q14 — Current medications** · archetype: `ACTION.medication.v1` · source: n/a (history)
> "Şu anda düzenli olarak kullandığınız ilaçlar var mı? Örneğin kan sulandırıcı ya da kortizon içeren ilaçlar."
gen: slot=duzenli_ilac; type=boolean
CANDIDATE — clinician to approve wording.

*(14 candidate questions; Q5 and Q7 held.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Cauda equina red flags, verbatim** (urinary retention/incontinence, saddle anaesthesia,
   bilateral progressive leg weakness) — the canonical NICE source (CKS "Sciatica (lumbar
   radiculopathy)") returned **HTTP 403** to automated fetch, and NG59 explicitly does **not** cover
   cauda equina. **NO SOURCE FOUND (verbatim) — clinician must supply**; the emergency itself belongs
   to `base.life_threat` (invariant 7), not this pack.
2. **NICE NG234 / MSCC spinal red flags, verbatim** — S2 exists but was captured only via a
   web-search summary (both candidate PDFs were binary/FlateDecode). **NO SOURCE FOUND (verbatim) —
   clinician must supply** from the primary NG234 text, with recommendation numbers, before Q5/Q7
   ground any rule.
3. **NG59 recommendation numbering + current update date** — "1.1.1" and "11 Dec 2020" came from an
   NCBI full-text mirror; nice.org.uk was not directly retrievable (403). **Re-verify against the
   primary NICE page on sign-off.**
4. **Fever + back-pain infection threshold** and **unexplained-weight-loss cancer threshold** — S1
   names "infection" and "cancer" as causes but supplies no layperson red-flag cut-off. **NO SOURCE
   FOUND (verbatim) — clinician must supply.**
5. **Türkiye-first primary guideline (T.C. Sağlık Bakanlığı / HSGM / uzmanlık derneği)** for MSK red
   flags — none located in retrievable, versioned form (S3). **NO SOURCE FOUND — clinician must
   supply** the correct Turkish primary source and its version/date.
6. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant
   21) — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must
   supply**, with committed `source` snapshots, before anything compiles.
7. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032 / HB-C12); not fabricated. Functional status / ADL has **no archetype root** → export
   blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/
  prognosis; marked CANDIDATE. Cauda-equina / red-flag questions ask about the *symptom* neutrally
  and never name a disease to the patient.
- **Inv. 7** — acute deterioration (cauda equina, cord compression) stays in `base.life_threat`;
  this proposal adds nothing to that sibling set and only captures the symptom for the note.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare numerals in drafts; compiler must expand before TTS; no free numeric entry.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S2 for
  that block (S1 verbatim, S2 unverified) but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
