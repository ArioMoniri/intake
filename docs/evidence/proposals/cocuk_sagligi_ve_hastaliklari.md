# Çocuk Sağlığı ve Hastalıkları (General Paediatrics) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Sağlığı ve Hastalıkları (General Paediatrics)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) — **not** diagnosis, not triage authority. This specialty is **pediatric**, so every question
is addressed to the **parent/guardian (proxy)** about *çocuğunuz* (your child). This file is a
*proposal for a clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and
pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence/label + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Pediatric proxy:** all patient-facing text is addressed to the parent/guardian in formal **`siz`**;
  the subject is the child. No question asks the child directly.
- **Acute paediatric emergencies stay in `base.life_threat` (invariant 7).** Sepsis and the
  meningococcal/serious-illness picture NICE NG143 flags in its RED column (non-blanching rash, bulging
  fontanelle, neck stiffness, status epilepticus, focal neurological signs, the "appears ill / does not
  wake" activity signs, grunting / severe chest indrawing, age < 3 months with fever) are life-threats
  owned by the `base.life_threat` sibling set — this general-paediatrics pack neither authors nor
  relaxes them. The alarm questions below only **feed** those base gates; they do **not** create a new
  RED rule in `specialty.cocuk_sagligi_ve_hastaliklari` and do not extend `base.life_threat`. HB-C1 is
  the open blocker on the `clinical_signoff` block of `base.life_threat.yaml` (paediatric reviewer
  field included).
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. No level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebSearch/WebFetch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived
  rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_sagligi_ve_hastaliklari.yaml` (an L0
  generated draft, `status: generated-l0-awaiting-clinical-review`) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG143 Fever in under 5s (traffic-light RED / AMBER signs)
- **guideline_id (proposed):** `NICE-NG143`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / year:** NG143, published 2019 (a 2021 update is referenced — confirm exact revision, §4 gap)
- **Citation:** NICE. *Fever in under 5s: assessment and initial management.* NICE guideline NG143.
- **URL (primary):** https://www.nice.org.uk/guidance/ng143 — returned **HTTP 403** on fetch; verbatim
  captured from the NCBI Bookshelf mirror table `cha.tab2`:
  https://www.ncbi.nlm.nih.gov/books/NBK552086/table/cha.tab2/
- **Verbatim (Traffic light table — RED / high-risk):**
  > Colour: "Pale/mottled/ashen/blue"
  > Activity: "No response to social cues" · "Appears ill to a healthcare professional" · "Does not
  > wake or if roused does not stay awake" · "Weak, high-pitched or continuous cry"
  > Respiratory: "Grunting" · "Tachypnoea: respiratory rate >60 breaths/minute" · "Moderate or severe
  > chest indrawing"
  > Circulation and hydration: "Reduced skin turgor"
  > Other: "Age <3 months, temperature ≥38°C" · "Non-blanching rash" · "Bulging fontanelle" · "Neck
  > stiffness" · "Status epilepticus" · "Focal neurological signs" · "Focal seizures"
- **Verbatim (Traffic light table — AMBER / intermediate-risk):**
  > Colour: "Pallor reported by parent/carer"
  > Activity: "Not responding normally to social cues" · "No smile" · "Wakes only with prolonged
  > stimulation" · "Decreased activity"
  > Respiratory: "Nasal flaring" · "Oxygen saturation ≤95% in air" · "Crackles in the chest"
  > Circulation and hydration: "Capillary refill time ≥3 seconds" · "Dry mucous membranes" · "Poor
  > feeding in infants" · "Reduced urine output"
  > Other: "Age 3-6 months, temperature ≥39°C" · "Fever for >5 days" · "Rigors" · "Swelling of a limb
  > or joint" · "Non-weight bearing limb/not using an extremity"
- **Applicability note:** these are the layperson-observable signs a parent can report; several RED
  rows (colour change, "appears ill / does not wake", grunting/severe indrawing, age < 3 months with
  fever, non-blanching rash, neck stiffness, bulging fontanelle, seizures) are **life-threats owned by
  `base.life_threat`**, not RED rules for this pack. Numbers appear only inside the quotes; per
  invariant 22 no numeral reaches TTS and the §3 drafts carry no digits. NG143 is scoped to under-5s;
  any extension to older children is a clinical judgement the signing clinician must confirm (§4).

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes** (INT-032, P3 export tier). Each item below binds to an
archetype **root**; the specific leaf path is **deferred** (`openehr_deferred_reason`), never
fabricated.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern (parent-reported) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the current problem | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Fever — presence / duration (S1 "Fever for >5 days") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Activity / alertness change (S1 RED activity signs) — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Breathing difficulty — fast breathing / grunting / chest indrawing (S1 RED respiratory) — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Colour change — pale / mottled / blue (S1 RED colour) — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Non-blanching rash (S1 RED "Non-blanching rash") — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Neck stiffness / bulging fontanelle / seizure (S1 RED "Other") — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Feeding / fluid intake and urine output (S1 AMBER hydration) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Swelling of a limb/joint or non-weight-bearing (S1 AMBER "Other") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Known chronic diagnoses / significant medical history | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 12 | Current regular medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 13 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 14 | Depression screening (adolescent/parent, if consented) | `openEHR-EHR-OBSERVATION.phq9.v1` | OBSERVATION | deferred (INT-032) |
| 15 | Anxiety screening (adolescent/parent, if consented) | `openEHR-EHR-OBSERVATION.gad7.v1` | OBSERVATION | deferred (INT-032) |
| 16 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 17 | **Immunisation / vaccination status** | **no archetype root — export blocked (INT-041 posture)** | — | — |
| 18 | **Growth / feeding history (weight gain, growth concern)** | **no archetype root — export blocked (INT-041 posture)** | — | — |

Notes:
- Items 17–18: the committed `.opt` exposes **no immunisation and no growth/anthropometry archetype
  root** (the only CLUSTER named in files/03 §7, `CLUSTER.provenance`, is itself ABSENT from the
  template). Capturing vaccination status or a growth-faltering fact therefore has no export target
  today → **export blocked (INT-041 posture)**; do not invent an at-code path. Both are core to a
  general-paediatrics intake, so the gap is real, not cosmetic. Clinician/architecture decision needed
  (candidate: INT-032 archetype addition).
- Items 14–15 (PHQ-9/GAD-7) are the consented wellbeing instruments, included only for completeness of
  binding; their content/cut-offs are out of scope for this general-paediatrics proposal (and are
  age-gated — a young child is not the respondent).

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian** about the child
(*çocuğunuz*); one concern per question (invariant 2: one question per turn); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".**
Per invariant 22, none of the drafts below contains a numeral; the protocol compiler must still expand
any future digit to Turkish orthography before TTS.

> Triage note for every alarm-derived item (Q4–Q12, new numbering): the level is a **`candidate_flag` (max
> `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT authoritative**. The
> authoritative RED for the NG143 RED-column picture (sepsis / meningococcal disease / severe
> respiratory distress) stays in `base.life_threat` (invariant 7) with a committed `source` snapshot
> and all three RED axes (route × register × location, invariant 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Renumbering, old → new — sections outside §3 still use the old numbers: Q1
unchanged · Q2 → Q2 (fever) + Q3 (how long, if Q2 yes) · Q3 → Q4 · Q4 → Q5 (fast breathing) + Q6
(chest indrawing) + Q7 (grunting) — the three items of `cocuk_gogus_hastaliklari` Q6 · Q5 → Q8 · Q6 →
Q9 · Q7 → Q10 (neck) + Q11 (fontanelle) + Q12 (seizure) · Q8 → Q13 (feeding / drinking) + Q14 (urine) ·
Q9 → Q15 (limb swelling) + Q16 (not using a limb) · Q10 → Q17 · Q11 removed (duplicates base
`meds_confirmed`).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün hekime getiren en önemli konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Fever presence** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Fever for >5 days")
> "Çocuğunuzun ateşi var mı?"
gen: slot=ates_var_mi; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Fever duration (if Q2 yes)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("Fever
for >5 days")
> "Çocuğunuzun ateşi ne zamandır sürüyor?"
gen: slot=ates_suresi; type=duration; ask_if=ates_var_mi == true
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician
+ rules-engine confirmation — NOT authoritative)** if the fever is prolonged (S1 AMBER); the NG143
boundary stays in the rule, never in the patient text, and any age scaling is for the clinician +
rules engine.

**Q4 — Activity / alertness change** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 RED activity ("Does not wake or if roused does not stay awake" / "Appears ill") — **feeds `base.life_threat`**
> "Çocuğunuz her zamankinden daha uykulu, güç uyandırılan ya da size karşı tepkisiz mi görünüyor?"
gen: slot=uykulu_tepkisiz; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; the "appears ill / does not wake" picture is owned by `base.life_threat`.

**Q5 — Fast breathing** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 RED respiratory (tachypnoea) — **feeds `base.life_threat`**
> "Çocuğunuz şu sıralarda her zamankinden hızlı nefes alıyor mu?"
gen: slot=hizli_nefes; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; severe respiratory distress is owned by `base.life_threat`.

**Q6 — Chest indrawing** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 RED respiratory ("Moderate or severe chest indrawing") — **feeds `base.life_threat`**
> "Nefes alırken çocuğunuzun kaburgalarının altı ya da arası içeri çekiliyor mu?"
gen: slot=gogus_icine_cekilme; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; RED owned by `base.life_threat`. Text is cluster_child_health Q10's: the IMCI
lower-chest-wall sign plus intercostal indrawing (verification cluster-wave-b §C, §F). The
paediatrician confirms the text against the IMCI source (cluster-wave-b §A.1).

**Q7 — Grunting** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 RED respiratory ("Grunting") — **feeds `base.life_threat`**
> "Çocuğunuz nefes verirken inler gibi bir ses çıkarıyor mu?"
gen: slot=inleme; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; RED owned by `base.life_threat`.

**Q8 — Colour change** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 RED colour ("Pale/mottled/ashen/blue") — **feeds `base.life_threat`**
> "Çocuğunuzun cildinde, dudaklarında ya da dilinde solukluk, benekli bir görünüm veya morarma fark
> ettiniz mi?"
gen: slot=renk_degisikligi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; RED owned by `base.life_threat`.

**Q9 — Non-blanching rash** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 RED "Other" ("Non-blanching rash") — **feeds `base.life_threat`**
> "Çocuğunuzun cildinde, üzerine bastırınca solmayan kırmızı ya da mor renkli döküntüler oldu mu?"
gen: slot=solmayan_dokuntu; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; a non-blanching rash with fever (meningococcal concern) is owned by
`base.life_threat`.

**Q10 — Neck stiffness** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 RED "Other" ("Neck stiffness") — **feeds `base.life_threat`**
> "Çocuğunuz boynunu öne eğmekte zorlanıyor mu?"
gen: slot=boyun_sertligi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; owned by `base.life_threat`.

**Q11 — Bulging fontanelle** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 RED "Other" ("Bulging fontanelle") — **feeds `base.life_threat`**
> "Çocuğunuzun bıngıldağı kabarık ya da gergin görünüyor mu?"
gen: slot=bingildak_kabarik; type=boolean
CANDIDATE — clinician to approve wording. The verifier asks for an infant-age `ask_if` here; the age
cut-off is a clinical value, so the gate is a clinician decision pending and no age is proposed.
Candidate_flag: **YELLOW_REVIEW (candidate — NOT authoritative)**; owned by `base.life_threat`.

**Q12 — Seizure during this illness** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 RED "Other" ("Focal seizures") — **feeds `base.life_threat`**
> "Çocuğunuz bu hastalık sırasında havale geçirdi mi?"
gen: slot=havale; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; owned by `base.life_threat`.

**Q13 — Feeding / fluid intake** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 AMBER hydration ("Poor feeding in infants" / "Dry mucous membranes")
> "Çocuğunuz her zamanki kadar beslenip bir şeyler içebiliyor mu?"
gen: slot=beslenme_sivi_alimi; type=boolean
CANDIDATE — clinician to approve wording.

**Q14 — Urine output** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 AMBER hydration ("Reduced urine output")
> "Çocuğunuz her zamankinden daha az çiş yapıyor mu?"
gen: slot=az_cis; type=boolean
INT-432 decision CD-10: `true` is the concern; renamed from `cis_miktari` (the old question made `false` the alarm direction).
CANDIDATE — clinician to approve wording. The earlier "bezini" wording was dropped.

**Q15 — Limb / joint swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 AMBER "Other" ("Swelling of a limb or joint")
> "Çocuğunuzun bir kolunda ya da bacağında şişlik var mı?"
gen: slot=kol_bacak_sislik; type=boolean
CANDIDATE — clinician to approve wording.

**Q16 — Not using a limb** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 AMBER "Other" ("Non-weight bearing limb/not using an extremity")
> "Çocuğunuz bir kolunu ya da bacağını kullanmaktan kaçınıyor mu?"
gen: slot=kol_bacak_kullanmama; type=boolean
CANDIDATE — clinician to approve wording.

**Q17 — Known chronic diagnoses** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general intake (history)
> "Çocuğunuzun bilinen süregelen bir hastalığı ya da daha önce konmuş önemli bir tanısı var mı?"
gen: slot=suregen_tani; type=boolean
CANDIDATE — clinician to approve wording.

*(17 candidate questions. Immunisation status and growth/feeding history — openEHR items 17–18 — are
core to a general-paediatrics intake but are deliberately NOT drafted as questions here because they
have no export target; export blocked, INT-041 posture, pending an archetype decision.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned general-paediatrics fever/red-flag guideline (verbatim)** — two
   Türkiye-first candidates were **identified but not verbatim-retrieved**: the **Türk Pediatri Kurumu
   "Çocukluk Çağında Ateş Yaklaşımı (2023)"** and the **Çocuk Enfeksiyon Hastalıkları ve Bağışıklama
   Derneği Ateş Kılavuzu** (http://www.cocukenfeksiyondernegi.org/upload/documents/AtesKilavuzu.pdf —
   the PDF fetch returned only binary, no readable text). **NO SOURCE FOUND (verbatim) — clinician must
   supply** the exact Turkish wording, version and date (ideally a **T.C. Sağlık Bakanlığı / HSGM**
   primary document, per the pack header). Any temperature/age thresholds seen only in AI search
   summaries are explicitly **not** quoted here — they are not verbatim and must not be used.
2. **NICE NG143 exact revision date** — published 2019 with a 2021 update referenced; the precise
   `version/date` must be confirmed against the primary before it grounds any rule. **Confirm current
   version.**
3. **Applicability of NG143 to children over five** — NG143 is scoped to **under-5s**; general
   paediatrics spans to adolescence. Whether the traffic-light signs transfer unchanged to older
   children, and what replaces the infant-specific rows (fontanelle, age-banded temperature/RR/HR
   cut-offs), is a **clinical judgement — clinician must confirm.**
4. **Dehydration / reduced-urine-output threshold** — S1 gives AMBER hydration signs qualitatively;
   any quantitative "when to seek help" threshold for reduced intake/output is **NO SOURCE FOUND —
   clinician must supply.**
5. **Immunisation-status red flags and growth-faltering thresholds** — core general-paediatrics fields
   (items 17–18) but no sourced rule and no export target. **NO SOURCE FOUND — clinician must supply**
   (and an archetype decision, INT-041/INT-032).
6. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned. The acute febrile/sepsis life-threats remain owned by
   `base.life_threat` (invariant 7; HB-C1 open); `packages/protocols/triage` + clinician must supply,
   with committed `source` snapshots, before anything compiles.
7. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032);
   not fabricated. Immunisation status (item 17) and growth/feeding history (item 18) have **no
   archetype root** → export blocked (INT-041 posture).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules
  engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, addressed to the
  parent/guardian, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — the acute febrile / sepsis / meningococcal life-threats (NG143 RED column) stay in
  `base.life_threat`; this pack only feeds those gates and neither adds to nor relaxes them.
- **Inv. 10** — scripted/alarm wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — the drafted questions contain no numerals; source quotes with numbers are quotes only,
  and the compiler must expand any digit before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate source S1 for that
  block but does not itself commit a snapshot; no Türkiye-first source was retrieved verbatim (§4.1).
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
