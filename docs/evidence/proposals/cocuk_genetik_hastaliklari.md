# Çocuk Genetik Hastalıkları (Pediatric Genetics) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Çocuk Genetik Hastalıkları (Pediatric Genetics)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This specialty is **pediatric**, so
every question is addressed to the **parent/guardian (proxy)** about *çocuğunuz* (your child). Genetics
intake leans heavily on **family history** and **consanguinity**, asked sensitively. This file is a
*proposal for a clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins
**no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence/label + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Pediatric proxy:** all patient-facing text is addressed to the parent/guardian in formal **`siz`**;
  the subject is the child. The consanguinity question is framed sensitively and states *why* it is
  asked.
- **Acute life-threats stay in `base.life_threat` (invariant 7).** Genetics is overwhelmingly a
  non-acute referral specialty, but a child with a known or suspected inborn error of metabolism can
  present in acute metabolic decompensation (lethargy, repeated vomiting, poor feeding, altered
  consciousness) — that emergency is owned by the `base.life_threat` sibling set (e.g. `rf.sepsis_like`
  and the altered-consciousness/vomiting life-threats), **not** by this pack. The one alarm question
  below (Q9) only **feeds** those base gates; it does not create a new RED rule here and does not
  extend `base.life_threat`.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. No level is asserted.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebSearch/WebFetch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived
  rule stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/cocuk_genetik_hastaliklari.yaml` (an L0
  draft) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NHS GeNotes: "Patient with developmental delay" (genetic referral red flags; regression)
- **guideline_id (proposed):** `GENOTES-DEVDELAY`
- **Publishing body:** National Genomics Education Programme, NHS England (GeNotes: In the Clinic)
- **Version / year:** undated in the retrieved excerpt — confirm (see §4 gap)
- **Citation:** NHS England, National Genomics Education Programme. *GeNotes — Presentation: Patient
  with developmental delay (In the Clinic).*
- **URL:** https://www.genomicseducation.hee.nhs.uk/genotes/in-the-clinic/patient-with-developmental-delay/
- **Verbatim (developmental regression — urgent):**
  > "Developmental arrest (normal initial development followed by failure to gain further skills) and
  > developmental regression (loss of previously gained skills) are red flags that require urgent
  > further assessment."
- **Verbatim (flags for an underlying genetic diagnosis):**
  > "Flags for an underlying genetic diagnosis include: family history of developmental delay;
  > parental consanguinity; dysmorphic features; and hypotonia."
- **Confidence: MED.** UK educational resource (not a Turkish document, not a formal guideline). It is
  the cleanest retrieved statement pairing **consanguinity + family history + dysmorphism** as genetic
  red flags and naming **regression** as urgent. Re-verify against a primary guideline / Türkiye-first
  source before sign-off.

### S2 — T.C. Sağlık Bakanlığı / HSGM Ulusal Yenidoğan Tarama Programı (Turkish MoH newborn screening)
- **guideline_id (proposed):** `HSGM-NTP`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü (HSGM)
- **Version / year:** program page (living); milestones dated in-text (1987 → 2022)
- **URL:** https://hsgm.saglik.gov.tr/tr/tarama-programlari/ntp.html
- **Verbatim (purpose, Turkish):**
  > "yenidoğanların belirlenen hastalıklar için taranması, oluşacak zeka geriliği, beyin hasarları ve
  > geri dönüşümsüz zararların engellenerek"
- **Verbatim (panel additions, Turkish):**
  > "2008 Ekim'de Biyotinidaz eksikliği, Ocak 2015'den itibaren ise Kistik Fibrozis taraması panele
  > eklenmiştir."
  > "Tarama paneline 09.05.2022 tarihi itibariyle Spinal Müsküler Atrofi (SMA) eklenmiştir."
- **Verbatim (referral, Turkish):**
  > "tarama sonucu şüpheli çıkan bebekler ilgili kliniklere yönlendirilmektedir."
- **Confidence: MED.** Official MoH program page (a Türkiye-first anchor), but a *program* page, not a
  versioned clinical guideline. Grounds the newborn-screening-result intake question (Q8). Re-verify
  the live page and pin a version/date before sign-off.

### S3 — Inborn Errors of Metabolism in the Emergency Department (acute decompensation signs)
- **guideline_id (proposed):** none — this is a **review article**, not a guideline
- **Publishing body / citation:** *Inborn Errors of Metabolism in the Emergency Department
  (Undiagnosed and Management of the Known).* PubMed 29622328.
- **URL:** https://pubmed.ncbi.nlm.nih.gov/29622328/ (see also BIMDG emergency guidelines:
  https://bimdg.org.uk/emergency-guides/)
- **Verbatim (via automated web-search summary — NOT fetched from primary):**
  > "any young child who presents with altered mental status and vomiting"
  > "poor feeding, frequent vomiting, irritability, seizures, abnormal tone, jaundice, and lethargy,
  > especially if seen during periods of fasting, stress, or acute illness"
- **Confidence: LOW.** Captured only as a search summary of a review; wording must be re-verified
  against the primary text and, preferably, replaced by a **Türkiye-first** metabolic-emergency source
  (T.C. Sağlık Bakanlığı / Türk uzmanlık derneği) or a committed BIMDG snapshot. The acute emergency
  itself belongs to `base.life_threat` (invariant 7); S3 only shapes the layperson-answerable
  intake question that feeds it.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes** (INT-032, P3 export tier). Each item below binds to an
archetype **root**; the specific leaf path is **deferred** (`openehr_deferred_reason`), never
fabricated. Genetics is the specialty where the **family-history export gap is most acute**: three of
its most load-bearing items have **no archetype root at all**.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for referral / main concern (parent-reported) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative (pregnancy / birth / developmental history) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Developmental delay — milestones not reached (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Developmental regression — loss of acquired skills (S1, urgent) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Dysmorphic features noticed by parent (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Growth / head-size concern | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Acute metabolic decompensation — lethargy / vomiting / poor feeding (S3) — **feeds `base.life_threat`** | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Newborn-screening (topuk kanı) result — suspicious/abnormal (S2) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 9 | Prior genetic test / known diagnosis | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 10 | Current medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 11 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 12 | Depression screening (parent/adolescent, if consented) | `openEHR-EHR-OBSERVATION.phq9.v1` | OBSERVATION | deferred (INT-032) |
| 13 | Anxiety screening (parent/adolescent, if consented) | `openEHR-EHR-OBSERVATION.gad7.v1` | OBSERVATION | deferred (INT-032) |
| 14 | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |
| 15 | **Family history of inherited / genetic disease (pedigree)** | **no archetype root — export blocked (INT-041 posture)** | — | — |
| 16 | **Parental consanguinity (akraba evliliği)** | **no archetype root — export blocked (INT-041 posture)** | — | — |
| 17 | **Recurrent pregnancy loss / stillbirth / unexplained infant death in the family** | **no archetype root — export blocked (INT-041 posture)** | — | — |

Notes:
- Items 15–17: the committed `.opt` exposes **no family-history archetype root** (the only CLUSTER
  named in files/03 §7, `CLUSTER.provenance`, is itself ABSENT from the template). Family history,
  consanguinity and family reproductive history are the **core of a genetics intake**, yet have **no
  export target today** → **export blocked (INT-041 posture)**; do not invent an at-code path. This is
  the specialty where the INT-041 gap bites hardest — a genetics pack that cannot export its pedigree
  is materially incomplete. Clinician/architecture decision needed (candidate: INT-032 archetype
  addition, e.g. `CLUSTER.family_history`/`EVALUATION.family_history`, sourced not invented).
- Items 12–13 (PHQ-9/GAD-7) are the consented wellbeing instruments, included only for completeness of
  binding; their content/cut-offs are out of scope for this proposal and are age-gated.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the **parent/guardian** about the child
(*çocuğunuz*); one concern per question (invariant 2: one question per turn); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".**
Per invariant 22, none of the drafts below contains a numeral. The consanguinity item (Q6) is phrased
sensitively and states its clinical purpose.

> Triage note for the alarm-derived items (Q9–Q10): the level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. The authoritative RED for acute
> metabolic decompensation stays in `base.life_threat` with a committed `source` snapshot and all
> three RED axes (route × register × location, invariant 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Finding 29 applies. Renumbering, old → new — sections outside §3 still use
the old numbers: Q1–Q8 keep their numbers (Q6 now uses one system voice, "soruyoruz") · Q9 → Q9
(unusually listless or sleepy) + Q10 (repeated vomiting or unable to feed) · Q10 → Q11 · Q11 removed
(base meds).

**Q1 — Reason for referral** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzun bugün genetik bölümüne yönlendirilmesinin sebebini kısaca anlatabilir misiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — Developmental delay** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (developmental delay flag)
> "Çocuğunuz yaşıtlarına göre oturma, yürüme ya da konuşma gibi gelişim basamaklarında geride
> kaldı mı?"
gen: slot=gelisim_geriligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Developmental regression** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("loss of previously gained skills … require urgent further assessment")
> "Çocuğunuz daha önce yapabildiği bir beceriyi, örneğin yürümeyi ya da konuşmayı, sonradan
> kaybetti mi?"
gen: slot=beceri_kaybi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician
+ rules-engine confirmation — NOT authoritative)** — S1 calls regression a red flag requiring *urgent*
assessment; the authoritative level stays with the rules engine.

**Q4 — Dysmorphic features** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("dysmorphic features")
> "Çocuğunuzun yüz görünümünde ya da vücut yapısında size farklı gelen bir özellik fark ettiniz mi?"
gen: slot=farkli_gorunum; type=boolean
CANDIDATE — clinician to approve wording. (Sensitive wording; no judgemental phrasing.)

**Q5 — Family history of genetic disease** · archetype: **no root — export blocked (INT-041)** · source: S1 ("family history")
> "Ailenizde kalıtsal ya da genetik bir hastalık tanısı almış bir kişi var mı?"
gen: slot=ailede_genetik_hastalik; type=boolean
CANDIDATE — clinician to approve wording. **Export blocked (INT-041 posture): no family-history
archetype root.**

**Q6 — Parental consanguinity (sensitive)** · archetype: **no root — export blocked (INT-041)** · source: S1 ("parental consanguinity")
> "Bu soruyu yalnızca sağlık değerlendirmesi için soruyoruz: anne ile baba arasında akrabalık var mı?"
gen: slot=akraba_evliligi; type=boolean
CANDIDATE — clinician to approve wording. Sensitive framing states the clinical purpose; "soruyoruz"
gives one system voice (finding 29). **Export blocked (INT-041 posture): no family-history archetype
root.**

**Q7 — Family reproductive history** · archetype: **no root — export blocked (INT-041)** · source: general intake (genetics family-history capture)
> "Ailenizde tekrarlayan düşük, ölü doğum ya da bebeklik döneminde açıklanamayan bir kayıp yaşandı mı?"
gen: slot=ailede_ureme_kaybi; type=boolean
CANDIDATE — clinician to approve wording. **Export blocked (INT-041 posture): no family-history
archetype root.** Not an alarm — no guideline threshold asserted.

**Q8 — Newborn-screening result** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S2 (HSGM Ulusal Yenidoğan Tarama Programı)
> "Çocuğunuzun yenidoğan döneminde yapılan topuk kanı taramasında şüpheli ya da anormal bir sonuç
> çıktı mı?"
gen: slot=topuk_kani_sonucu; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Unusually listless or sleepy (acute metabolic decompensation)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("altered mental status and vomiting"; "poor feeding … lethargy") — **feeds `base.life_threat`**
> "Çocuğunuz şu sıralarda alışılmadık şekilde halsiz ya da uykulu mu?"
gen: slot=uykulu_tepkisiz; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate — NOT
authoritative)**; the authoritative RED for acute metabolic decompensation is owned by
`base.life_threat` (invariant 7). Source caveat: S3 is a LOW-confidence review summary — re-source
(ideally Türkiye-first) before sign-off.

**Q10 — Repeated vomiting or unable to feed (acute metabolic decompensation)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("altered mental status and vomiting"; "poor feeding … lethargy") — **feeds `base.life_threat`**
> "Çocuğunuz şu sıralarda tekrar tekrar kusuyor ya da beslenemiyor mu?"
gen: slot=tekrarlayan_kusma_beslenememe; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag and source caveat: as Q9.

**Q11 — Prior genetic testing** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general intake (history)
> "Çocuğunuza daha önce genetik bir test, örneğin kromozom ya da DNA testi, yapıldı mı?"
gen: slot=onceki_genetik_test; type=boolean
CANDIDATE — clinician to approve wording.

*(11 candidate questions after revision. Q5–Q7 are the family-history / consanguinity /
reproductive-history items; they are drafted because they are core to a genetics intake, but each is
flagged export-blocked (INT-041) — captured for the clinician, with no openEHR export target until an
archetype is added.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned pediatric-genetics referral guideline (verbatim)** — the retrieved
   red-flag statement is UK NHS GeNotes (S1), and the Turkish anchor (S2) is a newborn-screening
   *program* page, not a referral guideline. **NO SOURCE FOUND (Türkiye-first, versioned) — clinician
   must supply** (candidate bodies: T.C. Sağlık Bakanlığı / HSGM; Türk Tıbbi Genetik Derneği).
2. **AAP 2025 clinical report on genetic evaluation of the child with intellectual disability / global
   developmental delay** (Pediatrics 2025;156(1):e2025072219) — a strong primary source identified in
   search but **not verbatim-retrieved** (publisher page fetch-gated). **Retrieve and quote verbatim
   before sign-off.**
3. **Consanguinity risk framing / threshold** — S1 names parental consanguinity as a red flag, but no
   Türkiye-first verbatim on how to *phrase* or *act on* it was retrieved. The sensitive wording in Q6
   is a draft. **NO SOURCE FOUND (Türkiye-first) — clinician must supply.**
4. **Metabolic-emergency (acute decompensation) red-flag wording (verbatim)** — S3 is a LOW-confidence
   review summary only. **NO SOURCE FOUND (verbatim guideline) — clinician must supply** a committed
   BIMDG snapshot or a Türkiye-first metabolic-emergency source. The emergency stays in
   `base.life_threat` (invariant 7).
5. **Family reproductive-history (recurrent loss / stillbirth) as a sourced genetics indication** —
   Q7 is drafted as general family-history capture; a verbatim guideline indication was **NO SOURCE
   FOUND — clinician must supply.**
6. **GeNotes version/date** — the retrieved excerpt was undated. **Confirm version/date.**
7. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21)
   — deliberately **not** assigned. `packages/protocols/triage` + clinician must supply, with
   committed `source` snapshots, before anything compiles.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032);
   not fabricated. **Family history, parental consanguinity and family reproductive history (items
   15–17) have no archetype root at all** → export blocked (INT-041 posture); this is the largest
   structural gap for the genetics branch and needs an architecture decision (sourced archetype
   addition, never invented).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules
  engine.
- **Inv. 2 / patient copy rules** — questions are one-concern, `siz`, B1, addressed to the
  parent/guardian, no diagnosis/treatment/prognosis; the consanguinity question is framed sensitively
  with its clinical purpose stated; marked CANDIDATE.
- **Inv. 7** — acute metabolic decompensation stays in `base.life_threat`; this pack only feeds that
  gate and neither adds to nor relaxes it.
- **Inv. 10** — scripted/alarm wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — the drafted questions contain no numerals; source quotes with dates/numbers are quotes
  only, and the compiler must expand any digit before TTS.
- **INT-041** — family history, consanguinity and family reproductive history have no openEHR archetype
  root → export blocked; captured for the clinician but not exportable until an archetype is added
  (INT-032 candidate).
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S3 for
  that block but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
