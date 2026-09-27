# Hemşirelik / Eğitim Poliklinikleri (Nurse-led Education Clinics) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research subagent (guideline researcher) · Date: 2026-09-26 · Specialty: Hemşirelik / eğitim poliklinikleri
Taxonomy id: `hemsirelik_egitim_poliklinikleri` (branches.yaml — cluster `allied_and_reports`).
Purpose: patient-owned, Turkish-first **pre-visit intake** that tells the nurse educator what the
patient wants to learn and what they already do at home — **not** diagnosis, not triage authority, not
a competence assessment. Addressed to the patient (self) in formal **`siz`**. This file is a *proposal
for a clinician (and the lead education nurse) to sign off*. It assigns **no** RED/YELLOW/GREEN level
and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every claim below quotes a **real source that was actually retrieved** on 2026-09-26. Where no
  source was found the row reads **"NO SOURCE FOUND"**. Nothing was invented.
- **Turkish first:** the *Hemşirelik Yönetmeliği* (HE-S1) defines the education role of nurses,
  including diabetes, dialysis and paediatric nurses. The WHO Regional Office for Europe guide on
  **therapeutic patient education** (HE-S2, 2023) is the international source for what to find out
  before teaching.
- **Topic-agnostic by design.** The clinics cover diabetes, stoma, wound, inhaler, dialysis and
  breastfeeding teaching and more. The pack asks *what* the patient wants to learn and *how*; the
  topic-specific content belongs to the relevant specialty pack.
- **Not repeated from base:** medications, allergies, caregiver presence (`caregiver_present`), living
  situation, patient goals (`patient_goals`).
- **Q10 asks for an accommodation, not a measure; voice.** HE-S2 names health literacy as part of the
  "educational diagnosis" and says education is "adapted to the patient"; that supports asking for the
  accommodation, not measuring literacy. The earlier wording ("okuyup anlamakta zorlanır mısınız?") had
  the shape of the published single-item literacy screeners and was replaced by a preference: whether
  written information should also be read aloud. Reading and learning difficulty is a category owner
  decision D3 approved, so Q10 needs its INT-349 row (the answer is a literacy proxy). It is `voice`,
  not D3's `text_first`, because a reading-difficulty item shown as text first cannot reach the patient
  it is for; **the owner confirms this departure from D3's delivery line.** No health-literacy
  instrument (e.g. REALM, NVS, HLS-EU) is reproduced.
- **Held for a missing item-level source:** Q7 (learning format) and Q8 (sensory barriers), §4 gap 3.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger.
- **Verification caveat:** HE-S1 was captured with WebFetch from a nursing-education society's copy
  (model-rendered); HE-S2 was downloaded to a scratch directory (never the repo) and extracted locally.
  Before sign-off each sentence MUST be re-checked against the primary text and committed as a verbatim
  snapshot with `source: {guideline_id, version, date, url, retrieved_on}`.
- This file does **not** edit `packages/protocols/specialty/hemsirelik_egitim_poliklinikleri.yaml` or
  any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### HE-S1 — *Hemşirelik Yönetmeliği* (Türkiye)
- **guideline_id (proposed):** `RG-2010-27515-HEMSIRELIK` (regulation)
- **Resmî Gazete:** 08.03.2010, sayı 27515 · **Amendment:** 19.04.2011, sayı 27910
- **URL retrieved:** https://www.hemed.org.tr/yasa-ve-yonetmelikler/hemsirelik-yonetmeligi/ (Hemşirelik
  Eğitimi Derneği copy) · official text: https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=13830&MevzuatTur=7&MevzuatTertip=5 (not fetched)
- **Verbatim (duty annex, as rendered by the fetch):**
  > "Hemşirelikle ilgili eğitim, danışmanlık, araştırma faaliyetlerini yürütür."
  > "Hastaların öz bakımını yapması için teşvik eder, destekler, gerektiğinde yapar."
  > Diabetes nurse: "Diyabetli bireyin gereksinimleri doğrultusunda grup veya bireysel eğitimleri
  > planlar, uygular, değerlendirir ve kaydeder."
  > Dialysis nurse: "Hasta ve hasta yakınlarına diyaliz işlemi, diyaliz süresi konularında gerekli
  > eğitimi verir."
  > Paediatric nurse: "Çocuk ve ailesini, hastaneye yattığı andan itibaren taburculuğa ve evde bakıma
  > hazırlar."
- **Confidence: MEDIUM.** Society-hosted copy; the fetch labelled the annex "Ek-2" while the original
  duty annex is Ek-1 — annex number and each sentence to be re-checked against the Resmî Gazete.

### HE-S2 — WHO Regional Office for Europe, *Therapeutic patient education: an introductory guide* (international)
- **guideline_id (proposed):** `WHO-EURO-TPE-2023`
- **Date:** 14 November 2023 · **ISBN:** 9789289060219
- **URL:** https://www.who.int/europe/publications/i/item/9789289060219 (PDF:
  https://iris.who.int/server/api/core/bitstreams/975d3f29-516d-41ba-9875-5dfc8d70f7aa/content)
- **Verbatim (extracted locally):**
  > "Therapeutic patient education is a structured person-centred learning process that supports
  > individuals living with chronic conditions to self-manage their own health by drawing on their own
  > resources, supported by their carers and families. It is carried out by trained health
  > professionals and is adapted to the patient and their condition"
  > "It is important for the health professional to work collaboratively with the patient to understand
  > the patient's circumstances and perspective in order to build a common understanding of the
  > patient's situation, needs (what matters most to the patient) and adaptive processes: this is
  > sometimes referred to as an educational diagnosis."
  > "It can also include understanding the stage of the patient's acceptance of their chronic condition,
  > as well as their emotional status, cognitive function, health literacy level, and family and social
  > circumstances."
  > "They may be involved in administering medicines or using the equipment needed to monitor a
  > condition, preparing food, or enabling an individual to exercise and attend hospital appointments."
  > (carers and families)
  > "The nurse starts by finding out about Henrik's life, listening to him, noticing his distress and
  > anxiety, and asking him about what is important to him and what concerns him most" (Box 6, worked example)
- **Confidence: HIGH** for text (primary PDF). International; no Turkish equivalent was retrieved.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Leaf paths are **deferred** (`openehr_deferred_reason`, INT-032), never invented. The OPT has no
education or learning-needs root; all items are narrative.

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Topic to learn | `EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2 | Prior teaching on this topic | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q3 | Self-performed care at home | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q4 | Difficulty with that care | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q5 | Question about a device or meter | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q6 | Main worry | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q7 | Preferred way of learning (HELD — no item-level source) | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q8 | Vision or hearing barrier to teaching (HELD — no item-level source) | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q9 | Wants a relative to attend | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q10 | Wants written information also read aloud (accommodation preference) | no candidate archetype | deferred (INT-032) |
| Q11 | Recent discharge | `OBSERVATION.story.v1` (narrative only) | deferred |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

No education-clinic alarm item exists. Acute symptoms disclosed here (for example low blood sugar or a
wound infection) are handled by the base red-flag probes and by the relevant specialty pack.

### 2.3 Red-flag candidates — for physician review — NOT encoded

None proposed. The sources describe roles and teaching method and carry no clinical urgency wording.

---

## 3. Candidate B1 Turkish pre-visit questions (11)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE —
clinician and lead education nurse to approve wording.** No item carries a triage level or a score.
Q1 binds to the pack's `basvuru_nedeni` slot.

**Duration ask — clinician decision pending.** An education visit is not a complaint visit, so the
generator's fixed `sikayet_suresi` ask ("Bu şikâyetiniz ne zamandır var?") fits poorly, and no source
supports another wording. No `pack:` line is written. The clinician supplies the wording, or the slot
is omitted once the generator can leave it out (gap 6).

**Q1 — Topic to learn** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake; HE-S1 ("eğitim, danışmanlık")
> "Bugün hemşire eğitim polikliniğinde öğrenmek istediğiniz konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Prior teaching** · archetype: `OBSERVATION.story.v1` · source: HE-S1 ("eğitimleri planlar, uygular, değerlendirir ve kaydeder"), HE-S2 (educational diagnosis)
> "Bu konuda daha önce bir sağlık çalışanından eğitim aldınız mı?"
gen: slot=onceki_egitim; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Self-performed care at home** · archetype: `OBSERVATION.story.v1` · source: HE-S1 ("öz bakımını yapması için teşvik eder, destekler"), HE-S2 ("using the equipment needed to monitor a condition")
> "Evde kendiniz yaptığınız iğne, pansuman ya da ölçüm gibi bir uygulama var mı?"
gen: slot=evde_oz_uygulama; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Difficulty with that care (if Q3 yes)** · archetype: `OBSERVATION.story.v1` · source: HE-S2 (educational diagnosis — "needs")
> "Bu uygulamayı yaparken zorlandığınız ya da emin olmadığınız bir nokta var mı?"
gen: slot=uygulamada_zorluk; type=boolean; ask_if=evde_oz_uygulama == true
CANDIDATE — clinician to approve wording. Not a skill assessment; the nurse observes technique in person.

**Q5 — Question about a device or meter** · archetype: `OBSERVATION.story.v1` · source: HE-S2 ("using the equipment needed to monitor a condition")
> "Kullandığınız bir ölçüm aletiyle ya da tıbbi cihazla ilgili bir sorunuz var mı?"
gen: slot=cihaz_sorusu; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Main worry** · archetype: `OBSERVATION.story.v1` · source: HE-S2 Box 6 ("what concerns him most")
> "Durumunuzla ilgili sizi en çok düşündüren konu nedir?"
gen: slot=en_cok_dusundiren; type=string
CANDIDATE — clinician to approve wording. "Düşündüren" is used instead of a worry word so the prompt
does not suggest there is cause for alarm.

**Q7 — Preferred way of learning** · archetype: `OBSERVATION.story.v1` · source: HE-S2 ("adapted to the patient and their condition" — general; no verbatim on formats)
> "Yeni bilgileri en kolay nasıl öğrenirsiniz, örneğin dinleyerek, izleyerek ya da okuyarak?"
gen: slot=ogrenme_tercihi; type=string; hold=no item-level source for learning format (gap 3)
HELD — no item-level source (§4 gap 3); HE-S2's "adapted to the patient" is a principle, not an item.
A preference, not a literacy measure.

**Q8 — Vision or hearing barrier** · archetype: `OBSERVATION.story.v1` · source: HE-S2 ("adapted to the patient and their condition" — general; **no verbatim on sensory barriers**)
> "Görme ya da işitmenizle ilgili, eğitimi takip etmenizi zorlaştıracak bir durum var mı?"
gen: slot=gorme_isitme_engeli; type=boolean; hold=no item-level source for sensory barriers (gap 3)
HELD — no item-level source (§4 gap 3).

**Q9 — Wants a relative to attend** · archetype: `OBSERVATION.story.v1` · source: HE-S2 ("supported by their carers and families"), HE-S1 ("Çocuk ve ailesini … evde bakıma hazırlar")
> "Eğitime sizinle birlikte bir yakınınızın da katılmasını ister misiniz?"
gen: slot=yakin_katilimi; type=boolean
CANDIDATE — clinician to approve wording. A yes/no preference only; no relative's details are asked.

**Q10 — Written information also read aloud (accommodation preference)** · archetype: none · source: HE-S2 ("health literacy level"; "adapted to the patient and their condition")
> "Yazılı bilgilerin size ayrıca sesli olarak anlatılmasını ister misiniz?"
gen: slot=sesli_anlatim_tercihi; type=boolean; delivery=voice
CANDIDATE — clinician to approve wording. Released under D3 (reading and learning difficulty) and
reframed as an accommodation the nurse acts on, not a literacy measure (§0). `voice` on purpose: a
reading-difficulty item shown as text first cannot reach the patient it is for; the owner confirms
this departure from D3's `text_first` line. The answer is a literacy proxy, so it still needs its
row. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending counsel
review (INT-349).

**Q11 — Recent discharge** · archetype: `OBSERVATION.story.v1` · source: HE-S1 ("taburculuğa ve evde bakıma hazırlar" — paediatric nurse duty, generalised)
> "Hastaneden yakın zamanda taburcu oldunuz mu?"
gen: slot=yakin_taburculuk; type=boolean
CANDIDATE — clinician to approve wording. The booking's `post_discharge` visit type may already record
the discharge; kept, because base `new_diagnoses_since_last_visit` does not.

*(11 candidate questions; 9 generate, 2 held.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Turkish standard for nurse-led patient education visits** (SB or Türk Hemşireler Derneği) — not
   found. **NO SOURCE FOUND — clinician/lead nurse must supply.**
2. **Primary text of HE-S1** — society copy only; annex number and wording to be re-checked.
3. **Learning-format and sensory-barrier items (Q7, Q8)** — only the general "adapted to the patient"
   principle is sourced. **NO SOURCE FOUND (item-level).** Both are held until one is quoted.
4. **Topic-specific teaching needs** (insulin, stoma, inhaler, dialysis, breastfeeding) — deliberately
   left to the specialty packs; the routing from this clinic to them is a product decision.
5. **Emotional status and acceptance** (HE-S2) — not drafted; a mood item risks becoming an unvalidated
   wellbeing screen (CLAUDE.md clinical content rules on instruments). Clinician to decide.
6. **The generator's standard `sikayet_suresi` slot** — fits an education visit poorly and no sourced
   wording exists. **Clinician decision pending:** clinician wording, or omit the slot once the
   generator supports it.
7. **EK-4 acuity** — no level proposed; RED axes (invariant 21) deliberately unassigned.
8. **openEHR leaf paths** — deferred (INT-032); no education root in the OPT (INT-041).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no triage content.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; no worry-inducing wording; each draft marked CANDIDATE.
- **Inv. 7** — nothing added to or extending `base.life_threat`.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval.
- **Inv. 18** — Q10 released under D3 as an accommodation preference with its INT-349 row; `voice`,
  not `text_first`, which the owner confirms (§0). Q7 and Q8 are held for a missing item-level source.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals in any candidate question.
- **Instruments** — no health-literacy or self-efficacy instrument reproduced.
- **HB-C1** — awaits clinician sign-off; NOT served.
