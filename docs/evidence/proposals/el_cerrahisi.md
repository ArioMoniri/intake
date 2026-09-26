# El Cerrahisi (Hand Surgery) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: El Cerrahisi (Hand Surgery)
Taxonomy id: `el_cerrahisi` (branches.yaml — cluster `surgical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage (invariant 1):** RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's own
  urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7 + base.life_threat — the defining constraint of this branch.** The acute alarm named in
  the task — **acute compartment syndrome** (and the related **acute limb ischaemia** it feeds) — is a
  branch-independent **life-threat** owned by the sibling set `base.life_threat`, which nothing may
  extend or relax. `base.life_threat`'s own pending note names **"limb ischaemia"** among "the six rules that
  motivated this pack existing at all" (04 §8); acute compartment syndrome of the forearm/hand is an
  acute-limb-threat presentation that path owns. This proposal therefore **does NOT author any RED rule,
  does NOT assign RED, and does NOT add anything to `base.life_threat`.** It proposes **intake questions
  and slots** that (a) feed those existing/planned life-threat gates as inputs, and (b) support
  non-emergency urgent-referral candidate flags (e.g. hand infection / flexor tenosynovitis). The overlap
  is catalogued in §2.
- **Invariant 9/10 (delivery).** These are pre-visit **intake questions**, not red-flag action scripts
  and not RED scripts. No 112 affordance, no action text, no location routing is proposed here — that is
  `base.life_threat`'s job and is pre-positioned on the device.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch/WebSearch). Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and, per the clinical-content rule, committed as a
  **verbatim source snapshot** with a full `source: {guideline_id, version, date, url, retrieved_on}`
  block. Until then any derived rule stays `status: draft_needs_source` and does **not** compile into a
  served pack.
- **No accuracy claims** (invariant 20): no sensitivity/specificity/AUROC figure is reproduced here, even
  where a source stated one (the StatPearls Kanavel-sign sensitivity figures are deliberately omitted).
- **Invariant 22 (numbers).** Patient copy is written in words, not numerals; no free numeric entry is
  proposed on the clinical critical path. Any digit in a quote is the source's own and the compiler must
  expand it to Turkish orthography before TTS.
- This file does **not** edit `packages/protocols/specialty/el_cerrahisi.yaml` (if/when authored) or any
  served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — ASSH "Hand Infection: Types and Treatment" (patient-facing warning signs) **[retrieved 2026-09-20]**
- **guideline_id (proposed):** `ASSH-HANDCARE-HANDINFECTION` (patient-education page, **not** a versioned
  clinical guideline).
- **Publishing body:** American Society for Surgery of the Hand (ASSH) — HandCare patient resource. Named
  by the task as the international fallback for hand surgery.
- **URL (primary):** https://www.assh.org/handcare/condition/hand-infection — the canonical page returns
  a JavaScript shell ("Find a Hand Surgeon") to automated fetch; body text retrieved via the ASSH
  Salesforce mirror https://assh.my.site.com/handcare/condition/hand-infection .
- **Verbatim (signs):**
  > "Cellulitis is a skin infection that can cause skin redness, warmth, and pain."
  > "Patients with cellulitis may have a fever, chills, or feel sick."
  > "A finger with a tendon sheath infection is swollen, red, and tender over the palm side."
- **Verbatim (urgency):**
  > "The infection can spread rapidly throughout the limb or into the bloodstream, and therefore prompt
  > treatment is important."
  > "Thus, how quickly you seek treatment is important."
  > "Prompt treatment is recommended, as this infection can cause severe stiffness or even destroy and
  > injure the tendon."
- **Confidence: MEDIUM.** Authoritative body, but a patient-education page (undated in the retrieved
  excerpt) reached via a mirror. Re-verify against the live ASSH page and record its date before it
  grounds any question wording or gate.

### S2 — StatPearls "Pyogenic Flexor Tenosynovitis" (Kanavel cardinal signs; surgical emergency) **[retrieved 2026-09-20]**
- **guideline_id (proposed):** `STATPEARLS-PFT` (peer-reviewed reference chapter, NCBI Bookshelf — a
  teaching reference, **not** a society guideline).
- **Publishing body:** StatPearls Publishing (NCBI Bookshelf). **Version / date:** "Updated August 13,
  2026" per the retrieved header.
- **URL:** https://www.ncbi.nlm.nih.gov/books/NBK576414/
- **Verbatim (the four Kanavel cardinal signs):**
  > "The 4 cardinal Kanavel signs of PFT include: Symmetrical (fusiform) swelling of the affected digit;
  > The affected digit is held in a flexed position; Pain with any attempt at passive digital extension;
  > Tenderness along the course of the flexor tendon sheath from the distal phalanx to the level of the
  > A1 pulley"
- **Verbatim (surgical emergency):**
  > "Pyogenic flexor tenosynovitis is an emergency that requires timely diagnosis and prompt treatment."
- **Verbatim (consequence of delay):**
  > "Delayed recognition can lead to tendon necrosis, adhesions, digital stiffness, horseshoe abscess
  > formation, ischemia, amputation, and permanent functional impairment."
- **Confidence: MEDIUM.** StatPearls is a widely used teaching reference, not a primary society
  guideline. Grounds the *flexor-tenosynovitis / loss-of-function* feeding questions; the sensitivity
  figures on the page are deliberately NOT reproduced (invariant 20). Re-verify before any gate.

### S3 — BOAST "Diagnosis and Management of Compartment Syndrome of the Extremities" (pain out of proportion) **[retrieved 2026-09-20]**
- **guideline_id (proposed):** `BOAST-COMPARTMENT`
- **Publishing body:** British Orthopaedic Association (BOA) with BAPRAS — BOA Standard for Trauma (BOASt).
- **Version / date:** "Last Updated July 2025 (Originally Published July 2014)" per the retrieved header.
- **URL:** https://www.boa.ac.uk/resource/boast-10-pdf.html
- **Verbatim (key clinical signs):**
  > "Key clinical findings include pain out of proportion to the associated injury and pain on passive
  > movement of the muscles of the involved compartments."
- **Verbatim (time-critical):**
  > "Immediate surgical decompression should follow a diagnosis of compartment syndrome."
- **Corroboration:** ASSH's Handthology chapter on hand compartment syndrome independently describes it
  as "a true surgical emergency … If not treated, tissue necrosis with permanent loss of function may
  occur" and names "pain with passive stretch of compartment" and skin "pallor, blistering, mottled
  appearance" (https://handthology.assh.org/ — summary retrieved via search, not fetched verbatim).
- **Confidence: MEDIUM.** BOAST is a real, authoritative orthopaedic standard (BOA/BAPRAS), not ASSH or a
  Turkish society; it grounds the *pain-out-of-proportion / pain-on-passive-stretch* vocabulary that
  **feeds the base.life_threat limb-ischaemia gate** (§2). Re-verify the verbatim against the primary PDF.

### S4 — Türkçe kaynak: el enfeksiyonu belirtileri (Bursa El Cerrahisi eğitim sayfası) **[retrieved 2026-09-20]**
- **guideline_id (proposed):** `TR-HANDINFECTION-BURSAEL` (Turkish-language **education page**, NOT a
  versioned clinical guideline).
- **Publishing body:** Bursa El Cerrahisi ve Mikro Cerrahi (özel klinik eğitim içeriği).
- **URL:** https://bursaelcerrahisi.tr/el-enfeksiyonlari/
- **Verbatim (Türkçe, belirtiler):**
  > "Kızarıklık ve şişlik"
  > "Ağrı ve hassasiyet"
  > "Isı artışı"
  > "Yara veya abse oluşumu"
  > "Hareket kısıtlılığı"
- **Verbatim (Türkçe, uyarı):**
  > "Eğer elinize bir yaralanma olduysa veya enfeksiyon belirtileri (kızarıklık, şişlik, aşırı ağrı,
  > ateş) yaşıyorsanız, en kısa sürede bir sağlık profesyoneline başvurmanız önemlidir."
- **Confidence: LOW.** Single Turkish-language private-clinic education page, not a versioned guideline.
  **Türk El ve Üst Ekstremite Cerrahisi Derneği** (turkelcerrahisidernegi.com) is the correct
  Türkiye-first candidate primary source, but only generic "hakkımızda" text was retrievable there (no
  versioned patient-facing red-flag document) — see §5 gap 1. Used here only to confirm that the
  Turkish-clinical vocabulary for hand-infection signs exists (kızarıklık, şişlik, ısı artışı, hareket
  kısıtlılığı).

---

## 2. Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

`files/protocols/base.life_threat.yaml` is a branch-independent sibling set, `served: false`,
`maturity: L0`, sign-off block empty (HB-C1). It carries a hard deny-prefix (`/life_threat`) that makes
it unreachable from any overlay op — that is what makes composition monotone. Its own pending note already names
the relevant alarm as a missing universal rule. It is **base.life_threat territory, not hand-surgery
overlay territory** — this proposal must not, and does not, add or extend it:

| Hand-surgery alarm | Named in base.life_threat as | This proposal's role |
|---|---|---|
| **Acute compartment syndrome** of forearm/hand (severe pain out of proportion, pain on passive finger stretch) | subsumed by **`limb ischaemia`** — one of "the six rules that motivated this pack" (04 §8); currently lives in cluster/specialty packs | Intake questions as gate **inputs** only (Q7, Q8) |
| **Acute limb / digit ischaemia** (new pallor, coldness, colour change of hand/fingers) | **`limb ischaemia`** (04 §8 six-rule list) | Intake questions as gate **inputs** only (Q8) |

**Consequence:** for the emergency-grade signs above, the intake questions here may at most emit a
`candidate_flag`. The authoritative acute determination (RED, register, location, 112/acil routing) is
made by the rules engine / `base.life_threat` after a **named physician** signs HB-C1 and each
`draft_needs_source` rule is sourced. Nothing in this file is a substitute for that. **No RED is assigned
here** (task constraint restated).

Note: **pyogenic flexor tenosynovitis / hand infection** (S1, S2, S4) is a *surgical urgency*, not one of
the six universal life-threats. It is proposed here as a specialty candidate_flag (max `YELLOW_REVIEW`),
whose authoritative acuity likewise stays with the clinician + rules engine — but it is not
base.life_threat territory the way limb ischaemia is.

---

## 3. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes** (INT-041 refused to invent them; INT-032 held that line —
HB-C12). Each question binds at the **archetype-root** level; the specific leaf path is **deferred**
(`openehr_deferred_reason`, INT-032), never fabricated. No proposed question requires an archetype outside
this set, so **no "no archetype fits — export blocked" row is needed** (contrast the cardiology proposal's
family-history item).

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the current hand complaint (story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Complaint location / region of hand or arm | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Redness / swelling / warmth (S1, S4 infection signs) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Finger held flexed / pain on straightening — flexor tenosynovitis (S2 Kanavel) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Fever / feeling unwell with the hand problem (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Severe pain out of proportion / pain on moving fingers (S3 — FEEDS compartment gate) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | New numbness / pallor / coldness of hand or fingers (S3, ASSH — FEEDS limb-ischaemia gate) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Loss of movement / function of hand or fingers (S1, S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Injury event — cut / bite / puncture (S1 infection risk context) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Known diagnoses (diabetes / immunosuppression / prior hand surgery) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 12 | Current medications (incl. blood thinners) | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| — | Drug allergy / adverse reaction (available; not drafted here) | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | **output only** — never an intake question |

Notes:
- All leaf `atNNNN` paths are **deferred** per INT-032 / HB-C12; none are invented.
- No item needs a family-history or provenance CLUSTER root, so the INT-041 "export blocked" case does
  not arise for this set.

---

## 4. Candidate B1 Turkish pre-visit questions (16)

Register: formal **`siz`** throughout; one concern per question (invariant 2: one question per turn);
empathetic; no diagnosis/treatment/prognosis language (PolicyGuard). **All marked "CANDIDATE — clinician
to approve wording".** No numerals appear in patient copy (invariant 22); the compiler must expand any
spelled numeral before TTS.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave4-5.md §D: every item is now one
question with sentences of at most fifteen words. The reviewer supplied no replacement text for §D, so
the split wording reuses each original item's own words. Q2 keeps only the "how" half; "when" is asked
by the generator's fixed `sikayet_suresi` slot. The former Q11's immune-system clause is left to the
base `immunosuppression` slot (HB-C6), as the reviewer ruled for enfeksiyon_hastaliklari. Renumbering,
old → new — §2, §6 and §7 still use the old numbers: Q1–Q4 unchanged · Q5 → Q5 (pain on straightening)
+ Q6 (finger held bent) · Q6 → Q7 (fever) + Q8 (feeling ill) · Q7 → Q9 (pain out of proportion) + Q10
(worse on moving fingers) · Q8 → Q11 · Q9 → Q12 · Q10 → Q13 · Q11 → Q14 (diabetes) + Q15 (prior hand
surgery) · Q12 → Q16.

> Triage note for every alarm-derived item: the level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. The authoritative RED/YELLOW must
> come from `packages/protocols/triage` (and, for compartment/limb-ischaemia, `base.life_threat`) with a
> committed `source` snapshot and all three RED axes (route × register × location, invariant 21), none of
> which are supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün el cerrahisi bölümüne gelme nedeninizi kendi cümlelerinizle kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording. Candidate level: none (orientation question).

**Q2 — Onset after an injury** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Elinizdeki ya da bileğinizdeki şikâyet bir yaralanmadan sonra mı başladı?"
gen: slot=yaralanma_sonrasi_basladi; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Complaint location** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
> "Ağrı ya da rahatsızlığı en çok elinizin veya kolunuzun hangi bölgesinde hissediyorsunuz?"
CANDIDATE — clinician to approve wording.

**Q4 — Redness / swelling / warmth (infection signs)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 (ASSH "skin redness, warmth, and pain"; "swollen, red, and tender over the palm side"), S4
("Kızarıklık ve şişlik", "Isı artışı")
> "Elinizde ya da parmağınızda kızarıklık, şişlik veya sıcaklık artışı fark ettiniz mi?"
gen: slot=kizariklik_sislik_sicaklik; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)** per S1 infection wording ("prompt treatment is
important").

**Q5 — Pain on straightening the finger (flexor tenosynovitis)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S2 (Kanavel: "Pain with any attempt at passive digital
extension")
> "Parmağınızı düzeltmeye çalıştığınızda belirgin bir ağrınız oluyor mu?"
gen: slot=duzeltince_parmak_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)**; S2 names PFT "an emergency that requires timely
diagnosis and prompt treatment", so the authoritative acuity stays with the clinician + rules engine.

**Q6 — Finger held bent (flexor tenosynovitis)** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S2 (Kanavel: "The affected digit is held in a flexed position")
> "Parmağınız kendiliğinden bükülü mü duruyor?"
gen: slot=bukulu_duran_parmak; type=boolean
CANDIDATE — clinician to approve wording. Split from Q5 (one question per turn); same candidate_flag
note as Q5.

**Q7 — Fever with the hand problem** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("may have
a fever, chills, or feel sick"), S4 ("Ateş ve genel halsizlik")
> "El şikâyetinizle birlikte ateşiniz çıktı mı?"
gen: slot=el_sikayeti_ile_ates; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: contributes context to an infection pattern
(S1/S4); level set by the rules engine.

**Q8 — Feeling unwell with the hand problem** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
("may have a fever, chills, or feel sick"), S4 ("Ateş ve genel halsizlik")
> "El şikâyetinizle birlikte kendinizi genel olarak hasta hissettiniz mi?"
gen: slot=genel_hastalik_hissi; type=boolean
CANDIDATE — clinician to approve wording. Split from Q7 (one question per turn); contributes context to
an infection pattern (S1/S4).

**Q9 — Severe pain out of proportion (FEEDS compartment gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S3 (BOAST "pain out of proportion to the associated injury")
> "Elinizdeki ya da ön kolunuzdaki ağrı, beklediğinizden çok daha şiddetli mi?"
gen: slot=orantisiz_agri; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: base.life_threat `limb ischaemia` / acute compartment
syndrome (§2).** Candidate_flag → max `YELLOW_REVIEW`; the acute RED determination is base.life_threat's,
not this pack's. **NO RED assigned** (task constraint).

**Q10 — Pain worse on moving the fingers (FEEDS compartment gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S3 (BOAST "pain on passive movement of the muscles of the
involved compartments")
> "Parmaklarınızı hareket ettirdiğinizde elinizdeki ağrı belirgin şekilde artıyor mu?"
gen: slot=parmak_hareketiyle_artan_agri; type=boolean
CANDIDATE — clinician to approve wording. Split from Q9 (one question per turn). **Overlap:
base.life_threat `limb ischaemia` / acute compartment syndrome (§2).** **NO RED assigned.**

**Q11 — New numbness / colour change / coldness of hand or fingers (FEEDS limb-ischaemia gate)** ·
archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (BOAST "sensory deficits or paresthesias"; ASSH
Handthology "pallor … mottled appearance")
> "Elinizde ya da parmaklarınızda yeni uyuşma, solukluk, morarma veya soğukluk var mı?"
gen: slot=uyusma_renk_degisimi_soguk; type=boolean
CANDIDATE — clinician to approve wording. Shortened to fifteen words or fewer (§D). **Overlap:
base.life_threat `limb ischaemia`.** Candidate_flag only; **NO RED assigned.**

**Q12 — Loss of movement / function** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("loss of
motion"), S2 ("permanent functional impairment")
> "Elinizi ya da parmaklarınızı her zamanki gibi hareket ettirmekte veya günlük işlerinizi yapmakta zorlanıyor musunuz?"
gen: slot=hareket_islev_kaybi; type=boolean
CANDIDATE — clinician to approve wording. Candidate level: none by itself; contributes to the
infection/compartment picture.

**Q13 — Injury event (cut / bite / puncture)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(hand infections follow wounds/bites; "The infection can spread rapidly")
> "Son zamanlarda elinize bir kesik, ısırık ya da delici bir yaralanma oldu mu?"
gen: slot=kesik_isirik_delici_yaralanma; type=boolean
CANDIDATE — clinician to approve wording. Clinician follow-up (hayvan/insan ısırığı, çürük/pas, yüksek
basınçlı sıvı) kept as sub-turns to preserve one concern per turn.

**Q14 — Known diabetes** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S2 (Kanavel signs
"less evident in patients with compromised immune systems, diabetes mellitus")
> "Size daha önce şeker hastalığı (diyabet) tanısı konuldu mu?"
gen: slot=diyabet_tanisi; type=boolean
CANDIDATE — clinician to approve wording (reuses the reviewer's diyabet_poliklinigi wording). Candidate
level: none (history question); documented as a context that can mask infection signs (S2).
Immunosuppression is asked by the base `immunosuppression` slot (HB-C6), not here.

**Q15 — Prior hand surgery** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general intake
> "Daha önce elinizden ameliyat oldunuz mu?"
gen: slot=onceki_el_ameliyati; type=boolean
CANDIDATE — clinician to approve wording. Candidate level: none (history question).

**Q16 — Current medications (incl. blood thinners)** · archetype: `ACTION.medication.v1` · source: general
intake (base slot `anticoagulant_use`, base.life_threat `base_intake_additions`)
> "Şu anda düzenli olarak kullandığınız ilaçlar var mı?"
gen: slot=duzenli_ilac; type=boolean
CANDIDATE — clinician to approve wording. Clinician follow-up: "kan sulandırıcı bir ilaç kullanıyor
musunuz?" — supports the `anticoagulant_use` slot that bleeding/injury gates reference.

*(16 candidate questions.)*

---

## 5. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned hand-surgery clinical/patient source** — the correct society is **Türk El
   ve Üst Ekstremite Cerrahisi Derneği** (turkelcerrahisidernegi.com), but only generic "hakkımızda"
   text was retrievable; no versioned patient-facing red-flag or hand-infection document was located. The
   only Turkish verbatim (S4) is a private-clinic education page. **NO SOURCE FOUND (versioned Turkish
   society/T.C. Sağlık Bakanlığı) — clinician must supply**, with version/date.
2. **ASSH hand-infection page date/version** — S1 body text was reached via the ASSH Salesforce mirror;
   the canonical page returns a JS shell to automated fetch and is undated in the excerpt. **Re-verify
   against the live www.assh.org page and record its date before sign-off.**
3. **A primary society/guideline verbatim for hand/forearm compartment syndrome** — S3 (BOAST, BOA/BAPRAS)
   is a real orthopaedic standard, not ASSH or a Turkish source, and its verbatim was captured from a
   PDF-resource landing page. **Re-verify against the primary BOAST PDF; a Turkish equivalent (e.g.
   TOTBİD) would be preferable** as the Türkiye-first source. NO Turkish compartment-syndrome verbatim was
   retrieved. **NO SOURCE FOUND (Turkish primary) — clinician must supply.**
4. **Enumerated "when to go to the emergency department" verbatim, Turkish** — no Türkiye-first
   authoritative sentence (e.g. T.C. Sağlık Bakanlığı / EK-4) was retrieved for the hand-infection or
   compartment-syndrome acute path. **NO SOURCE FOUND — clinician must supply** before any RED action
   script.
5. **T.C. Sağlık Bakanlığı EK-4 acuity mapping for hand emergencies** — no verbatim in-repo snapshot found
   (`packages/protocols/sources/TR-EK4-2022.txt` is referenced by base.life_threat but absent in this
   worktree). Any Turkish acuity level (KIRMIZI/SARI) must be sourced from EK-4 by the clinician; none
   proposed here.
6. **High-pressure injection injury / specific bite-wound red-flag thresholds** — recognised hand-surgery
   emergencies, but no primary verbatim was retrieved this session for their patient-reportable form.
   **NO SOURCE FOUND — clinician must supply.**
7. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21) —
   deliberately **not** assigned here. **Clinician + `packages/protocols/triage` / `base.life_threat`
   must supply**, with committed `source` snapshots, before anything compiles.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032 /
   HB-C12); not fabricated.

---

## 6. base.life_threat overlap summary (do not extend — invariant 7)

- **Acute compartment syndrome** (Q7) and **acute limb/digit ischaemia** (Q8) map to base.life_threat
  `limb ischaemia` (one of the six motivating rules, 04 §8). Overlap flagged; not authored/extended; **NO
  RED assigned** (task constraint). Q12's `anticoagulant_use` follow-up feeds the same family of gates.
- Hand infection / flexor tenosynovitis (Q4–Q6, Q9, Q10) is a specialty urgency, **not** a base
  life-threat; proposed as candidate_flag only, level owned by the clinician + rules engine.

## 7. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; alarm items are max `YELLOW_REVIEW`, pending the
  rules engine.
- **Inv. 2 / patient-copy rules** — questions are one-concern (Q7 flagged for possible split), `siz`,
  ≤ B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — acute compartment syndrome / limb ischaemia are **fed, not authored/extended**; nothing
  added to `base.life_threat`.
- **Inv. 9/10** — intake questions only; no RED script, no 112 affordance, no location routing proposed.
- **Inv. 20** — no accuracy/performance figures reproduced (StatPearls sensitivity figures omitted).
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare digits in patient text; compiler must expand any spelled numeral before TTS.
- **Clinical-content rule** — each alarm item needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S4 but does
  not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician (physician of record; hand surgeon) sign-off; NOT served.
