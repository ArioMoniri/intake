# Adli Tıp (Forensic Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Adli Tıp (Forensic Medicine)
Purpose: patient-owned, Turkish-first **pre-visit intake** (context capture for a clinician-ready
note) — **not** diagnosis, not triage authority, **not** a medico-legal statement. This file is a
*proposal for a clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and
pins **no** clinical value.

Branch: `adli_tip` (`taxonomy/branches.yaml` — cluster `allied_and_reports`, `visit_types: [report]`).

---

## 0. Applicability — read this first (why this pack is deliberately minimal)

**Patient-initiated pre-visit intake has genuinely limited applicability to forensic medicine.** An
adli muayene / adli rapor contact is a **medico-legal, report-type** visit (the taxonomy pins
`visit_types: [report]`): it is directed by a legal or institutional process, its "questions" are
governed by the examination protocol and the law, and the authoritative account of an incident must
be taken **in person, by a trained clinician**, not extracted by an automated pre-visit assistant.
Two consequences shape everything below:

- **We do not try to take the medico-legal history pre-visit.** Pressing an unaccompanied person for
  the details of an assault through an app risks re-traumatisation, contaminates the legal account,
  and is exactly what the WHO medico-legal guidance reserves for a trained interviewer (see §1 S3 and
  §4). The one narrative item (§3 Q2) is an **optional, skippable** "anything you'd like the doctor
  to know beforehand" — never a demand for the story of the incident.
- **The pack is therefore minimal:** a small general-intake set (reason, optional note, chronic
  conditions, medications, allergies) **plus** two carefully-sourced, empathetic safety items
  (feeling-safe inquiry; a neck-injury/strangulation symptom safety-net) drawn from real
  international guidance. Nothing here decides urgency; any escalation is a rules-engine + clinician
  decision.

Everything else follows the same evidence discipline as the other proposals: every clinical claim
quotes a **real source that was actually retrieved**; where none was found the row reads **"NO SOURCE
FOUND"**; nothing was invented.

- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written
  as *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*.
- **Verification caveat:** quotes were captured on 2026-09-20 via automated web retrieval
  (WebSearch/WebFetch + a direct read of the IFAS PDF). Before sign-off each verbatim sentence MUST
  be re-checked against the primary published text and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block; until then any
  derived rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/**` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — WHO 2013 clinical & policy guidelines on IPV / sexual violence (safety, first-line support)
- **guideline_id (proposed):** `WHO-VAW-2013`
- **Publishing body:** World Health Organization (WHO), Geneva
- **Version / year:** 2013 (WHO/RHR/13.10)
- **Citation:** WHO. *Responding to intimate partner violence and sexual violence against women:
  WHO clinical and policy guidelines.* Geneva: WHO; 2013.
- **URLs:** https://www.who.int/publications-detail-redirect/WHO-RHR-13.10 · full text
  https://www.ncbi.nlm.nih.gov/books/NBK174251/
- **Verbatim (Recommendation 1 — first-line support; strength: strong, indirect evidence):**
  > "Women who disclose any form of violence by an intimate partner (or other family member) or
  > sexual assault by any perpetrator should be offered immediate support."
  > "Health-care providers should, as a minimum, offer first-line support when women disclose
  > violence."
- **Verbatim (Recommendation 3 — clinical inquiry; strength: strong, indirect evidence):**
  > "Health-care providers should ask about exposure to intimate partner violence when assessing
  > conditions that may be caused or complicated by intimate partner violence"
- **Important caveat (paraphrase from the guideline summary — verbatim NOT captured):** WHO does
  **not** recommend *universal screening* ("routine enquiry") of all women; inquiry is advised **when
  assessing conditions that may be caused or complicated by violence**. A forensic/adli contact is
  plausibly such a condition, but the exact non-universal-screening wording MUST be re-verified
  before this grounds any served question (see §4).

### S2 — IFAS 2024 clinical management of non-fatal strangulation (neck-injury red flags)
- **guideline_id (proposed):** `IFAS-NFS-2024`
- **Publishing body:** Institute for Addressing Strangulation (IFAS), UK — produced by Prof. Catherine
  White; endorsed by an intercollegiate group incl. Royal College of Emergency Medicine, Royal
  College of General Practitioners, Royal College of Nursing, ENT UK, Faculty of Forensic & Legal
  Medicine, Royal College of Surgeons, Royal College of Radiologists, RCPCH, British Psychological
  Society, College of Paramedics, UK Association of Forensic Nurses & Paramedics.
- **Version / year:** February 2024 (review date February 2025).
- **Citation:** IFAS. *Guidelines for clinical management of non-fatal strangulation in acute and
  emergency care services.* Feb 2024.
- **URL:** https://ifas.org.uk/wp-content/uploads/2024/02/Non-Fatal-Strangulation-Guidelines_AcuteEmergency_Feb24.pdf
- **Verbatim (Box A):**
  > "Patients are unlikely to spontaneously give a history of strangulation."
  > "50% of victims will have no visible external injury to their neck/head as a result of the
  > strangulation"
  > "A lack of visible injury MUST NOT influence decision-making around proceeding with radiological
  > investigation."
  > "A trauma informed approach is required, including seeing the patient alone when taking history to
  > ensure safety and privacy."
- **Verbatim (Box B — "Red flags related to the strangulation", symptom labels):**
  > "Dysphagia or odynophagia (difficulty or pain on swallowing)"
  > "Neck swelling or tenderness of larynx/ trachea"
  > "Dyspnoea (objective signs/symptoms)/ voice changes"
  > "Loss or near loss of consciousness"
  > "Amnesia or altered mental state (dizzy, confused, loss of memory or awareness)"
  > "Incontinence (bladder and/or bowels)"
  > "Petechial haemorrhages on face/neck/oral/conjunctival"
  > "Any degree of bruising to neck or ligature marks (Note 50% have no mark so absence is not
  > reassuring)"
- **Verbatim (Box F — discharge safety-netting):**
  > "Provide patient/carer with information regarding strangulation including signs and symptoms to
  > watch out for that would need urgent medical assessment"
- **Relevance:** non-fatal strangulation is common in domestic and sexual assault (an adli context),
  external signs are frequently absent, and symptoms can be delayed — which is exactly why a
  symptom safety-net item that says "if you notice any of these, seek urgent care rather than wait
  for the report appointment" is justified. The specific urgency **action** (register/location/112),
  however, is a rules-engine decision, not asserted here (invariant 21).

### S3 — WHO 2003 medico-legal care for victims of sexual violence (history-taking posture)
- **guideline_id (proposed):** `WHO-MEDICOLEGAL-2003`
- **Publishing body:** World Health Organization (WHO), Geneva
- **Version / year:** 2003
- **Citation:** WHO. *Guidelines for medico-legal care for victims of sexual violence.* Geneva; 2003.
- **URL:** https://iris.who.int/handle/10665/42788
- **Status: referenced, NOT verbatim.** A clean verbatim sentence was **not** captured (the WHO IRIS
  copy is a large scanned PDF that did not parse). The search-level summary indicates the guideline
  requires that anyone taking the account be **trained**, that victims may have a support person
  present, and that distress be minimised during history, examination and documentation. This
  grounds the **posture** of §0 (do not take the incident history pre-visit) but MUST be replaced by
  a committed verbatim snapshot before it grounds any served text (see §4).

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes**. Per its own header, a slot whose leaf path is not
yet authored carries **`openehr_deferred_reason`** (INT-032, P3 export tier) — it is **not**
invented. Each item below binds to an archetype **root**; the specific leaf path is **deferred**.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for the appointment / report | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Optional "anything to share beforehand" note | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Feeling-safe inquiry (S1 first-line support / inquiry) | `openEHR-EHR-OBSERVATION.story.v1` (imperfect fit — see note) | OBSERVATION | deferred (INT-032) |
| 4 | A trusted support person available (S1 first-line support) | `openEHR-EHR-OBSERVATION.story.v1` (imperfect fit — see note) | OBSERVATION | deferred (INT-032) |
| 5 | Neck-injury / strangulation symptom safety-net (S2 Box B) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Known chronic diagnoses (S2 Box A: other conditions alongside) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 7 | Current regular medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 8 | Drug / substance allergy | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 9 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Notes:
- **Items 3–4 (safety / support):** none of the seven allowed archetype roots is a clean fit for a
  psychosocial safety / safeguarding concept; `OBSERVATION.story.v1` is the least-bad root (contextual
  narrative) and is used here **provisionally**. A dedicated safeguarding/psychosocial archetype is
  an architecture decision (candidate: INT-032 archetype addition); until then, treat the export
  target as **provisional — clinician/architecture confirmation needed**, and do not fabricate an
  at-code path.
- All leaf paths are **deferred** (`openehr_deferred_reason`, INT-032); none is fabricated.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout; one concern per question (invariant 2: one question per
turn); empathetic; no diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to
approve wording".** No numeral appears in any question text (invariant 22). Given the sensitivity of
this branch, the wording is deliberately gentle, non-leading, and — for the narrative and safety
items — explicitly **skippable**.

> Triage note for every safety-net item: no level is assigned here. Any level is a
> **`candidate_flag` (max `YELLOW_REVIEW`), pending clinician + rules-engine confirmation — NOT
> authoritative**. The authoritative RED/YELLOW and its action (route × register × location,
> invariant 21) must come from `packages/protocols/triage`.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Findings 21 and 28 apply. Q1–Q6 keep their numbers. Q7 (medications)
and Q8 (allergies) are removed: they duplicate base `meds_confirmed`/`meds_new_or_stopped` and
`allergies`. Q3, Q4 and Q5 are held under invariant 18 (finding 21): feeling-safe, companion and
strangulation answers are a new sensitive data category on a patient-owned device that may be shared
with the perpetrator. That is a stop-and-ask item (new categories of personal data) for the owner, the
legal-reviewer and the clinician; none of the three is served until it is decided.

Revised 2026-10-04 (INT-469, GitHub #810): the allied cluster's report-purpose item `rapor_amaci`
(cluster Q3, "Bu raporun hangi amaçla istendiğini kısaca söyler misiniz?") is **not carried** to Adli
Tıp. Legal decision LD-01 (the INT-471 legal lane, GitHub #800) holds that a forensic examination and
report are made on a competent authority's proper request and must answer that authority's questions
(Sağlık Raporları Yönetmeliği, RG 19/5/2026 sayı 33258, Madde 40(4) and 50(4)), so the purpose of an
adli rapor is the authority's, not something the person examined declares; Madde 50(1) and 48(1) keep
every intake answer out of an adli rapor. The `pack:` line below makes the generator emit one
`suppress_slot` op for the inherited slot (files/12 §3.1); the rest of the cluster's report items
stay, and the other allied branches, Sağlık Kurulu among them, keep `rapor_amaci`. Nothing is asked in
its place: LD-01 leaves the replacement item undecided.

pack: suppress=sorular.rapor_amaci

Also applied 2026-10-04 (INT-469): CD-105 (wave 1-3 finding 21) rejects Q3, Q4 and Q5 pre-visit.
Q4 already carried a `hold=` line; Q3 and Q5 were marked HOLD in prose only, so the generator emitted
them. Both now carry a `hold=` line like Q4's, and none of the three reaches the candidate.

**Q1 — Reason for the appointment** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake (no clinical threshold)
> "Bugünkü randevunuzun konusu nedir?"
CANDIDATE — clinician to approve wording. The typed-only "yazabilirsiniz" is gone (voice-first,
finding 28).

**Q2 — Optional note for the doctor** · archetype: `OBSERVATION.story.v1` · source: general intake (posture informed by S3 — do NOT press for the incident account)
> "İsterseniz bu soruyu geçebilirsiniz. Doktorun önceden bilmesini istediğiniz bir şey var mı?"
gen: slot=doktora_onceden_not
CANDIDATE — clinician to approve wording. **Must not** be turned into a demand for the details of any
incident; detailed account-taking is for the trained clinician in person (S3). The skip offer now
works in voice; "boş bırakabilirsiniz" was typed-only (finding 28).

**Q3 — Feeling safe now** · archetype: `OBSERVATION.story.v1` (provisional) · source: S1 (Rec 1 first-line support; Rec 3 inquiry)
> "Şu anda kendinizi güvende hissediyor musunuz?"
gen: slot=su_an_guvende; type=boolean; delivery=text_first; hold=CD-105 rejects it pre-visit — safeguarding enquiry for trained staff in private (NICE PH50), invariant 18
CANDIDATE — clinician to approve wording. HOLD (finding 21). Also open: S1's non-universal-screening
caveat is not captured verbatim (§4 gap 3). If the hold is lifted, a "no" answer may at most feed a
candidate_flag **YELLOW_REVIEW (candidate, pending clinician + rules-engine confirmation — NOT
authoritative)**.

**Q4 — A trusted support person** · archetype: `OBSERVATION.story.v1` (provisional) · source: S1 (Rec 1 first-line support)
> "Randevuya sizinle birlikte gelmesini istediğiniz, güvendiğiniz biri var mı?"
gen: hold=clinician and legal decision — companion invitation conflicts with S2 Box A (see alone)
CANDIDATE — clinician to approve wording. HOLD (finding 21). Also open: inviting a companion
conflicts with S2 Box A, which asks for the patient to be seen alone when the history is taken. That
conflict is a clinician + legal decision.

**Q5 — Neck-injury / strangulation symptom safety-net** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (IFAS Box B — airway red flags)
> "Boynunuza baskı uygulanan bir olaydan sonra ses kısıklığı ya da yutkunmada zorlanma fark ettiniz mi?"
gen: slot=boyun_baski_sonrasi_belirti; type=boolean; delivery=text_first; hold=CD-105 rejects it pre-visit — the clinician asks it at the visit (NICE PH50), invariant 18
CANDIDATE — clinician to approve wording. The reviewer passes the text (IFAS Box B supports voice
change + dysphagia) but keeps it under finding 21's data decision, so it is held with Q3–Q4. If the
hold is lifted: candidate_flag **YELLOW_REVIEW (candidate, pending clinician + rules-engine
confirmation — NOT authoritative)** per S2. **Scope note:** this captures only the airway pair
(voice change / swallowing) as one concern; the fuller IFAS red-flag set (breathing difficulty, neck
swelling, loss of consciousness, memory change, incontinence, petechiae, visual symptoms) is **not** a
single pre-visit question — it belongs to the clinician + rules-engine red-flag rule, and IFAS itself
notes external signs are absent in half of cases (S2 Box A).

**Q6 — Known chronic diagnoses** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general intake (context noted by S2 Box A, "patients may have other injuries and/or medical conditions alongside")
> "Doktorun bilmesi gereken, süregelen bir hastalığınız var mı?"
gen: slot=suregelen_hastalik; type=boolean
CANDIDATE — clinician to approve wording.

*(After revision: six candidate items. Three are emitted (Q1, Q2, Q6) and three are held under
invariant 18 (Q3–Q5); Q7–Q8 were removed as base duplicates. No item is added to raise the count:
none is sourced, and whether this pack belongs in a report-type pathway at all is still open (§4
gap 1).)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Applicability itself** — whether an automated **patient-owned** pre-visit intake belongs in a
   forensic/adli (report-type) pathway at all is a **clinical + legal governance decision**, not a
   technical one. This proposal assumes a minimal, safety-first, non-account-taking role; that
   assumption needs explicit clinician + legal sign-off. **Awaiting-human.**
2. **WHO 2003 medico-legal care — verbatim** — the IRIS scanned PDF did not parse; only a
   search-level summary was obtained (S3). A committed verbatim snapshot (history-taking / trained
   interviewer / support-person principles) MUST replace it. **NO SOURCE FOUND (verbatim) — clinician
   must supply.**
3. **WHO 2013 non-universal-screening wording — verbatim** — the "do not screen all women routinely;
   inquire when assessing conditions that may be caused/complicated by violence" caveat is currently
   a paraphrase. **Re-verification required** before Q3/Q4 ground any served text.
4. **The full strangulation red-flag list as a triage rule** — S2 supplies verbatim red-flag labels
   but this proposal deliberately captures only one airway pair as a pre-visit question. The full
   rule (with the urgency action, register, location per invariant 21, and the "seek urgent
   assessment" script) is **NO SOURCE FOUND (as a triage rule) — clinician + `packages/protocols/
   triage` must supply.**
5. **Türkiye-first primary source** — a **T.C. Sağlık Bakanlığı** adli-muayene / kadına yönelik
   şiddet clinician guideline, or an **Adli Tıp Kurumu** primary document, was **not** retrieved
   verbatim; only society/NGO materials (e.g. Mor Çatı, İSTAHED, a society-hosted Turkish translation
   of the WHO sexual-violence care guide) were located. **NO SOURCE FOUND (versioned, verbatim) —
   clinician must supply** the correct Türkiye-first primary source and its version/date.
6. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant
   21) — deliberately **not** assigned here. **Clinician + `packages/protocols/triage` rules must
   supply**, with committed `source` snapshots, before anything compiles.
7. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`,
   INT-032). Items 3–4 (safety/support) have **no clean archetype root** among the allowed set →
   export target **provisional**, do not fabricate an at-code path.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending
  rules engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, no
  diagnosis/treatment/prognosis; the sensitive items are gentle and skippable; marked CANDIDATE.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) and any urgency action intentionally unspecified →
  flagged as a gap; no "call 112"/emergency script is asserted in this proposal.
- **Inv. 22** — no numeral appears in any question text.
- **Clinical content rule** — each safety item needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S2
  (verbatim) and S3 (referenced, not verbatim) but does not itself commit a snapshot.
- **Data-protection / sensitivity** — safety, safeguarding and any account of violence are
  special-category data; per the constitution, persisting new categories of personal data and any
  consent-text change are **stop-and-ask-the-human** items. This proposal captures nothing; it only
  proposes candidate questions for review.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
