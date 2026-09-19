# Diş Hekimliği (General Dentistry) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher subagent · Date: 2026-09-20 · Specialty: Diş Hekimliği (General Dentistry) ·
Branch slug: `dis_hekimligi` (cluster: dental)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom / history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's own
  urgency wording is quoted verbatim; **no level is asserted**.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / WebSearch / a saved PDF read locally). The **live nice.org.uk
  chapter page returned HTTP 403**; the verbatim NICE text below was read from the **NCBI Bookshelf
  mirror** of NG12 (NBK555330). Before sign-off, each verbatim sentence and **every recommendation
  number** MUST be re-checked against the **primary published text** and committed as a **verbatim source
  snapshot** with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any
  derived rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- **Airway emergencies stay in `base.life_threat` (invariant 7).** Facial / mouth-floor swelling with
  breathing or swallowing difficulty (spreading odontogenic infection / Ludwig's angina) is a **universal
  life-threat family** — `rf.dyspnoea_rest` and `rf.anaphylaxis` in `packages/protocols/base/intake.yaml`
  — a sibling set outside the inheritance chain that **nothing may extend**. This dentistry proposal
  therefore adds **no** airway red flag of its own; the airway screen (Q3) is written only to *route the
  patient into the base family*, and §4 flags the RED script/axes for the base owner.
- **Türkiye-first gap (up front):** the served pack `packages/protocols/specialty/dis_hekimligi.yaml` is
  an **L0 draft** (`extends: cluster.dental`) whose header requires the branch clinician to source rules
  from **T.C. Sağlık Bakanlığı / HSGM** protocols and **Turkish specialty-society** guidelines. A
  dedicated Turkish search on 2026-09-20 returned only private-hospital marketing pages and one
  specialty-society **public** page (AÇBİD) — **no versioned Türkiye-first clinical guideline document**
  (see §4). The sources below are therefore international, pending Türkiye-first replacement.
- This file does **not** edit the served L0 pack, `previsit_intake.v1.opt`, `base/intake.yaml`, or any
  other served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG12 Suspected cancer: recognition and referral (oral cancer red flags)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), England
- **Version / year:** NG12, published June 2015 (updated — confirm current update date on sign-off)
- **Citation:** NICE. *Suspected cancer: recognition and referral.* NICE guideline NG12.
- **URL:** https://www.nice.org.uk/guidance/ng12 · verbatim read from NCBI Bookshelf mirror
  https://www.ncbi.nlm.nih.gov/books/NBK555330/ (live nice.org.uk chapter returned HTTP 403)
- **Verbatim (rec. 1.8.2):**
  > "Consider a suspected cancer pathway referral for oral cancer in people with either: unexplained
  > ulceration in the oral cavity lasting for more than 3 weeks or a persistent and unexplained lump in
  > the neck."
- **Verbatim (rec. 1.8.3):**
  > "Consider an urgent referral (for an appointment within 2 weeks) for assessment for possible oral
  > cancer by a dentist in people who have either: a lump on the lip or in the oral cavity or a red or
  > red and white patch in the oral cavity consistent with erythroplakia or erythroleukoplakia."
- **Corroboration:** the ">3 weeks unexplained ulceration" threshold was returned identically by an
  independent web-search summary and by Turkish public pages (a Türkiye source phrased the escalation as
  "2 haftadan fazla sürmesi" — a *different* number, so only the NICE "3 weeks" is quoted as the
  threshold; the Turkish page is noted, not used, in §4). Primary-text re-verification of the exact
  recommendation numbers still required.

### S2 — Ludwig's angina / spreading odontogenic infection (AIRWAY EMERGENCY → base.life_threat)
- **guideline_id (proposed):** `ADAM-LUDWIG` — **patient-education encyclopedia, NOT a clinical
  guideline** (A.D.A.M. / MedlinePlus medical encyclopedia)
- **Publishing body:** A.D.A.M., Inc. (MedlinePlus, U.S. National Library of Medicine)
- **URL:** https://medlineplus.gov/ency/article/001047.htm (also A.D.A.M. text at
  https://ufhealth.org/conditions-and-treatments/ludwig-angina)
- **Verbatim (When to Contact a Medical Professional):**
  > "Breathing difficulty is an emergency situation. Go to the emergency room or contact the local
  > emergency number (such as 911) right away."
- **Verbatim (description):**
  > "The infected area swells quickly. This may block the airway or prevent you from swallowing saliva.
  > Ludwig angina can be life threatening."
- **Confidence: LOW–MEDIUM.** A patient-education encyclopedia, not a versioned airway/clinical
  guideline. **Because this is an airway life-threat, it belongs in `base.life_threat` (invariant 7), not
  in the dental specialty pack.** The `112` affordance for Türkiye is **not** sourced here (the source
  says US "911"); see §4. Must be re-verified and, ideally, replaced by a primary source (deep-neck-space
  infection / airway guideline, or a **T.C. Sağlık Bakanlığı / AÇBİD** document) before it grounds any
  RED action script.

### S3 — IADT 2020 guidelines: Avulsion of permanent teeth (dental trauma — knocked-out tooth)
- **guideline_id (proposed):** `IADT-AVULSION-2020`
- **Publishing body:** International Association of Dental Traumatology (IADT)
- **Version / year:** 2020
- **Citation:** Fouad AF, Abbott PV, Tsilingaridis G, et al. *International Association of Dental
  Traumatology guidelines for the management of traumatic dental injuries: 2. Avulsion of permanent
  teeth.* Dental Traumatology. 2020;36(4):331–342. ISSN 1600-4469. (PubMed 32460393)
- **URL:** https://onlinelibrary.wiley.com/doi/10.1111/edt.12573 · verbatim read from the open White Rose
  eprints copy https://eprints.whiterose.ac.uk/id/eprint/161687/1/IADT%20guidelines%20-%20Avulsion%20of%20permanent%20teeth.pdf
- **Verbatim (Introduction):**
  > "Avulsion of permanent teeth is one of the most serious dental injuries. Prompt and correct emergency
  > management is essential for attaining the best outcome after this injury."
- **Verbatim (first aid at the accident site):**
  > "Immediate replantation of the avulsed tooth is the best treatment at the place of the accident."
- **Note:** grounds a **recent dental-trauma / knocked-out permanent tooth** intake question (Q8). The
  time-critical first-aid content is clinician/patient-education, quoted here only to justify capturing
  the *event*; **no triage level is asserted** and this is a **dental** emergency, not an airway
  life-threat (so it does not touch `base.life_threat`).

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Same posture as the cardiology proposal: the committed `.opt` is deliberately **shallow** — composition
and archetype **roots** only, **no at-code (`atNNNN`) leaf nodes**. Each item binds to an archetype
**root** that actually exists in the committed `.opt`; the leaf path is **deferred**
(`openehr_deferred_reason`, INT-032), never fabricated.
Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL).

| # | Proposed captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's dental visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| 2 | Narrative of the dental complaint (story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Facial/mouth-floor swelling + breathing/swallowing difficulty (S2 — routes to base.life_threat) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Fever with facial/jaw swelling (S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Non-healing mouth/lip sore > 3 weeks (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Lump in mouth, lip or neck (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Red / red-white patch in mouth (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Recent knocked-out (avulsed) permanent tooth (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Toothache / dental pain (chief dental complaint) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Bleeding gums / prolonged bleeding after dental work | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Current medications (incl. blood thinners) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug / local-anaesthetic / latex allergy | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate triage outcome (rules engine only; max `YELLOW_REVIEW` from LLM) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Notes:
- Item 3 is an **airway screen only**: its purpose is to *route* the patient into the universal
  `base.life_threat` family (`rf.dyspnoea_rest` / `rf.anaphylaxis`), which this proposal does not extend
  (invariant 7). Known systemic diagnoses (e.g. diabetes affecting healing) would bind to
  `EVALUATION.problem_diagnosis.v1`; held for clinician addition (§4) rather than fabricated here.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; **one concern per question** (invariant 2: one question per
turn); empathetic; **no diagnosis/treatment/prognosis** language (PolicyGuard-clean — no "kanser" or any
diagnostic label in patient copy). Numerals are **spelled out** (invariant 22: the compiler must expand
every digit before TTS; these drafts already do so — e.g. "üç hafta"). **All marked "CANDIDATE —
clinician to approve wording".**

> Triage note for every red-flag-derived item: any level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. Authoritative RED/YELLOW must come
> from `packages/protocols/triage` with a committed `source` snapshot and all three RED axes
> (route × register × location, invariant 21), none of which are supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü randevunuzda sizi diş hekimine getiren asıl şikâyetiniz nedir? Kısaca anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Complaint narrative (story)** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu şikâyetiniz nasıl başladı ve o zamandan bu yana nasıl seyretti? Biraz anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q3 — Facial/mouth-floor swelling with breathing or swallowing difficulty** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S2 (Ludwig — "Breathing difficulty is an emergency situation";
"This may block the airway or prevent you from swallowing saliva")
> "Yüzünüzde ya da ağız tabanınızda şişlikle birlikte nefes almakta veya yutkunmakta zorlanıyor
> musunuz?"
CANDIDATE — clinician to approve wording. Candidate_flag: **candidate acute-airway concern, pending
clinician + rules-engine confirmation — NOT authoritative**. This is an **airway life-threat** and
belongs to `base.life_threat` (`rf.dyspnoea_rest`/`rf.anaphylaxis`, invariant 7); the dental pack does
not carry it. Source is patient-education (S2, LOW–MEDIUM); RED script/axes NOT supplied (§4).

**Q4 — Fever with facial/jaw swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (Ludwig —
spreading infection with swelling)
> "Yüzünüzdeki ya da çenenizdeki şişliğe ateş de eşlik ediyor mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **candidate — NOT authoritative** (systemic
sign of spreading infection); source S2 (LOW–MEDIUM).

**Q5 — Non-healing mouth/lip sore > 3 weeks** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(NICE NG12 1.8.2 — "unexplained ulceration in the oral cavity lasting for more than 3 weeks")
> "Ağzınızda ya da dudağınızda üç haftadan uzun süredir iyileşmeyen bir yara var mı?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** if "üç haftadan uzun", per S1 verbatim.

**Q6 — Lump in mouth, lip or neck** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG12
1.8.2/1.8.3 — "a lump on the lip or in the oral cavity", "persistent and unexplained lump in the neck")
> "Ağzınızda, dudağınızda ya da boynunuzda geçmeyen bir şişlik veya kitle fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** per S1.

**Q7 — Red / red-white patch in mouth** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE
NG12 1.8.3 — "a red or red and white patch in the oral cavity consistent with erythroplakia or
erythroleukoplakia")
> "Ağzınızın içinde geçmeyen kırmızı ya da kırmızı-beyaz bir leke fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)** per S1.

**Q8 — Recent knocked-out (avulsed) permanent tooth** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S3 (IADT 2020 — "Avulsion of permanent teeth is one of the most serious dental injuries. Prompt
and correct emergency management is essential")
> "Yakın zamanda bir darbe sonucu kalıcı (sürekli) dişlerinizden biri tamamen yerinden çıktı mı?"
CANDIDATE — clinician to approve wording. Candidate_flag: **candidate time-critical dental emergency,
pending clinician + rules-engine confirmation — NOT authoritative**; a **dental** emergency, not an
airway life-threat. The patient-facing first-aid script (replant / storage medium) is **NO SOURCE FOUND
as a delivered script** (§4) — no action script is written here.

**Q9 — Toothache / dental pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
> "Dişinizde ya da diş etinizde ağrı var mı? Varsa ne zamandır sürüyor?"
CANDIDATE — clinician to approve wording. (Two clauses share one concern — pain and its duration; split
into two turns if the reviewer prefers strict one-question-per-turn.)

**Q10 — Bleeding gums / prolonged bleeding** · archetype: `OBSERVATION.symptom_sign.v1` · source: general
intake
> "Diş etlerinizde kanama ya da bir diş işlemi sonrasında olağandan uzun süren kanamanız oldu mu?"
CANDIDATE — clinician to approve wording.

**Q11 — Current medications (incl. blood thinners)** · archetype: `ACTION.medication.v1` · source:
general history
> "Şu anda düzenli kullandığınız ilaçlar var mı? Örneğin kanı sulandıran bir ilaç kullanıyor musunuz?"
CANDIDATE — clinician to approve wording. Medication history only; the patient is **not** told to stop
any medication here (that is a clinician decision).

**Q12 — Drug / local-anaesthetic / latex allergy** · archetype: `EVALUATION.adverse_reaction_risk.v1` ·
source: general intake
> "Herhangi bir ilaca, uyuşturucu (lokal anestezi) iğnesine ya da lateks gibi bir maddeye karşı
> alerjiniz var mı?"
CANDIDATE — clinician to approve wording.

*(12 candidate questions: Q3–Q4 airway/spreading-infection screen (S2 — routes to base.life_threat);
Q5–Q7 oral-cancer red-flag context (S1); Q8 dental-trauma (S3); Q1–Q2, Q9–Q12 general intake / history.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first versioned clinical guideline (MoH / HSGM / specialty society, e.g. Türk Diş Hekimleri
   Birliği).** A dedicated Turkish search (2026-09-20) returned only private-hospital marketing pages and
   a specialty-society **public** page (AÇBİD, acbid.org). **NO SOURCE FOUND (versioned, authoritative) —
   clinician must supply** the correct **T.C. Sağlık Bakanlığı / HSGM** or Turkish specialty-society
   document and its version/date, as the served L0 pack header itself requires. (Note: a Turkish public
   page phrased the oral-lesion escalation as "2 haftadan fazla" — a *different* threshold from NICE's
   "3 weeks"; the discrepancy is exactly why the Türkiye-first primary source is required and no Turkish
   threshold was adopted here.)
2. **Airway / spreading-odontogenic-infection RED as a versioned clinical source + `base.life_threat`
   content.** S2 is a MedlinePlus/A.D.A.M. encyclopedia entry, not a guideline. The airway family lives in
   `base.life_threat` (`rf.dyspnoea_rest`/`rf.anaphylaxis`), which nothing may extend (invariant 7); its
   trigger, EK-4 acuity, register and RED action scripts are unsupplied **in the base pack** and are the
   base owner's responsibility — **not** added here. **NO SOURCE FOUND (clinical guideline) — clinician
   must supply** a primary deep-neck-space-infection / Ludwig's angina source (candidate: AÇBİD / MoH).
3. **Türkiye emergency affordance ("112" for airway/spreading infection).** Only the LOW–MEDIUM
   patient-education S2 (US "911") was retrieved. **NO SOURCE FOUND (primary/Türkiye) — clinician must
   supply**; per invariant 21 the RED script + register + location axes are **not** set here (under
   ON_SITE the 112 affordance must be absent, not de-emphasised).
4. **Avulsed-tooth patient-facing first-aid / escalation script.** S3 grounds capturing the *event* and
   its time-critical nature, but the delivered patient-facing action script (replant, milk/saliva storage,
   time window) is **NO SOURCE FOUND as an approved `text_tr` script — clinician must supply** (and it
   must be spoken verbatim per invariant 10).
5. **Oral-cancer duration threshold discrepancy.** NICE ">3 weeks" (S1) vs a Turkish public page's "2
   weeks". **Clinician must confirm** which threshold the Türkiye-first source sets before Q5 grounds a
   rule.
6. **NICE NG12 oral recommendation numbers.** Captured from the NCBI Bookshelf mirror as 1.8.2/1.8.3.
   **Re-verify exact numbers against the primary NICE text on sign-off.**
7. **Bleeding-risk / anticoagulant management source for dentistry.** Q10/Q11 are framed as general
   history; a dental bleeding-risk guideline (candidate: SDCEP anticoagulant/antiplatelet QRG, as used in
   the oral-surgery proposal) was **not re-retrieved here**. **NO SOURCE FOUND (this retrieval) —
   clinician must supply / re-capture** if a flag is desired.
8. **Systemic-history items relevant to dentistry (diabetes, pregnancy, immunosuppression,
   antiresorptive medication).** Held for clinician addition; bind to `problem_diagnosis` / `medication`.
   **NO SOURCE FOUND (specific thresholds) — clinician must supply** any that should carry a flag.
9. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032);
   not fabricated.
10. **Every candidate_flag level and all three RED axes** (route × register × location, invariant 21) —
    deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must supply**,
    with committed `source` snapshots, before anything compiles.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules engine.
- **Inv. 2 / patient-copy rules** — questions are one-concern, `siz`, B1, no diagnosis/treatment/prognosis (no "kanser" in patient copy); marked CANDIDATE (Q9's two clauses flagged for optional split).
- **Inv. 7** — airway/spreading-infection kept in `base.life_threat`; this specialty proposal adds no life-threat rule and does not extend the base set; Q3 only routes into it.
- **Inv. 10** — scripted/red-flag wording (incl. the avulsed-tooth first-aid script) will need verbatim `text_tr`; not finalised here.
- **Inv. 13** — the specialty pack is **L0** (`dis_hekimligi.yaml`); an L0 pack resolved for a live session raises. This proposal is review-queue input only, not a promotion.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap; ON_SITE 112 affordance rule noted.
- **Inv. 22** — numerals in drafts are spelled out; compiler must expand before TTS.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1, S2, S3 for that block but does not itself commit a snapshot, and does not edit the served pack.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
