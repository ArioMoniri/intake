# Odyoloji (Audiology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research subagent (guideline researcher) · Date: 2026-09-26 · Specialty: Odyoloji (Audiology)
Taxonomy id: `odyoloji` (branches.yaml — cluster `sensory`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (hearing and ear history before a hearing
assessment) — **not** diagnosis, not triage authority, not a hearing test. Addressed to the patient
(self) in formal **`siz`**; a parent answering for a child is handled by base `subject_role`. This
file is a *proposal for a clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and pins
**no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim quotes a **real source that was actually retrieved** on 2026-09-26; where none
  was found the row reads **"NO SOURCE FOUND"**. Nothing was invented.
- **Sources:** the WHO *Primary ear and hearing care: training manual* (2023) gives a step-by-step
  history-taking practical, which structures this pack (OD-S1). Turkish corroboration comes from lay
  pages of the Kulak Burun Boğaz ve Baş Boyun Cerrahisi Vakfı (TKBBV; OD-S2 … OD-S4). **No Türk Odyoloji
  Derneği or SB audiology document was found** (§4 gap 1). NICE NG98 is cited only through a secondary
  source because nice.org.uk returned HTTP 403 (not bypassed).
- **Sudden hearing loss is NOT asked here.** It is left to `base.life_threat` and the physician (see
  §2.2 and the sibling `kulak_burun_bogaz_hastaliklari.md`, which carries the sudden-loss item). This
  pack asks about hearing difficulty in daily life, never about onset speed.
- **No validated instrument is reproduced.** OD-S3 and OD-S4 list lay self-check questions; Q2 is
  written in our own words and is not an item of HHIE-S or any other hearing-handicap scale.
- **Not repeated from base:** medications (ototoxic drugs are covered by the medication list),
  allergies, occupation (noise *exposure* is asked, not the job).
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger.
- **Verification caveat:** OD-S1 was downloaded to a scratch directory (never the repo) and extracted
  locally with `pdftotext`; OD-S2 … OD-S5 were captured with WebFetch (model-rendered). Before sign-off
  each sentence MUST be re-checked and committed as a verbatim snapshot with `source: {guideline_id,
  version, date, url, retrieved_on}`.
- This file does **not** edit `packages/protocols/specialty/odyoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### OD-S1 — WHO, *Primary ear and hearing care: training manual* (international)
- **guideline_id (proposed):** `WHO-PEHC-MANUAL-2023`
- **Publishing body:** World Health Organization · **Date:** 2 March 2023 · **ISBN:** 978-92-4-006915-2
- **URL:** https://www.who.int/publications/i/item/9789240069152 (PDF:
  https://iris.who.int/server/api/core/bitstreams/429d890f-0380-474d-9ad7-b64679c3d27a/content)
- **Verbatim — Practical A, "Taking a history of ear and hearing problems" (extracted locally):**
  > "Ask what the problem is with the ear. It could be hearing loss, discharge from the ear, pain in the
  > ear, or something else."
  > "You will need to record details of each symptom mentioned, and whether one or both ears are affected."
  > "Is there also a persistent ringing or buzzing sensation in the ear (tinnitus)?"
  > "Is there any history of hearing loud noise for a long time (such as working in a factory)?"
  > "Is there any history of hospitalization or prolonged drug therapy?"
  > "Ask about other symptoms, such as dizziness, sound in the ear (tinnitus), or itching in the ear."
  > NOTE: "It is important to make sure that you ask the person if they have put any foreign objects in
  > their ear, or used any home remedies, such as hot oil."
- **Verbatim — genetic causes and Annex 3:**
  > "Hearing loss can be hereditary and carried through generations of a family."
  > "If tinnitus or dizziness are the main symptom, and they have continued for more than a few weeks,
  > the person should be referred to a specialist."
  > Hearing loss, normal otoscopy, inner-ear hearing loss: "If sudden, refer urgently"
- **Verbatim — mastoiditis (module 4.7):** "Refer urgently to a hospital where the patient can receive
  prompt care. Mastoiditis needs urgent management!"
- **Confidence: HIGH** for text (primary PDF). Primary-care manual, not a specialist guideline.

### OD-S2 — TKBBV, "Ani işitme kaybı nedir? – Prof. Dr. İbrahim Sayın" (Türkiye)
- **guideline_id (proposed):** `TKBBV-ANI-ISITME-KAYBI` (lay page) · **Date:** none shown
- **URL:** https://tkbbv.org.tr/ani-isitme-kaybi-nedir-prof-dr-ibrahim-sayin/
- **Verbatim:**
  > "işitme azlığı olarak fark edilebileceği gibi, aniden ortaya çıkan çınlama uğultu ya da kulakta
  > dolgunluk hissi şeklinde de belirti verebilir. Baş dönmesi bu belirtilere eşlik edebilir."
  > "Böyle bir durum fark ettiğinizde ilk yapmanız gereken şey size en yakın kulak burun boğaz
  > hastalıkları uzmanına hemen başvurmak olmalıdır."
- **Confidence: LOW–MEDIUM** — foundation lay page, undated. Also cited as K-S1 in
  `kulak_burun_bogaz_hastaliklari.md`.

### OD-S3 — TKBBV, "İşitme kaybı nedir? – Yrd. Doç. Dr. Selman Sarıca" (Türkiye)
- **guideline_id (proposed):** `TKBBV-ISITME-KAYBI` (lay page) · **Date:** none shown
- **URL:** https://tkbbv.org.tr/isitme-kaybi-nedir-yrd-doc-dr-selman-sarica/
- **Verbatim (the page's own lay self-check questions — quoted for provenance, NOT reused as items):**
  > "Gürültülü ortamlarda konuşulanları anlamakta güçlük çekiyor musunuz?"
  > "Konuşulanlarının tekrar edilmesini sık sık istiyor musunuz?"
- **Confidence: LOW–MEDIUM** — lay page, undated.

### OD-S4 — TKBBV, "İşitme testi nedir? – Levent Küfeciler" (Türkiye)
- **guideline_id (proposed):** `TKBBV-ISITME-TESTI` (lay page) · **Date:** none shown
- **URL:** https://tkbbv.org.tr/isitme-testi-nedir-levent-kufeciler/
- **Verbatim (signs listed as reasons for a hearing test):**
  > "Arabada, restoranda veya herhangi bir gürültülü ortamda konuşulanı anlamakta zorluk çekiyorsanız"
  > "Aileniz ve arkadaşlarınız size bir işitme probleminiz var mı diye soruyorsa"
- **Confidence: LOW–MEDIUM** — lay page, undated.

### OD-S5 — NICE NG98, *Hearing loss in adults: assessment and management* — SECONDARY quotation only (international)
- **guideline_id (proposed):** `NICE-NG98`
- **Primary URL:** https://www.nice.org.uk/guidance/ng98 — **HTTP 403**, not bypassed.
- **Secondary source retrieved:** Easton G, Leverton T. *Supporting adults with hearing loss in primary
  care: new NICE guideline.* Br J Gen Pract. 2018;68(676):516–517 — https://pmc.ncbi.nlm.nih.gov/articles/PMC6193776/
- **Verbatim (as quoted by the secondary source):**
  > "GPs should refer all adults, regardless of their age, who present for the first time with hearing
  > difficulties, or in whom you suspect hearing difficulties, to audiology services for an assessment."
- NG98's unilateral/asymmetric, tinnitus, vertigo and facial-droop referral criteria were seen **only in
  search summaries** and are **not** quoted.
- **Confidence: MEDIUM–LOW** until the NG98 primary text is snapshotted.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Leaf paths are **deferred** (`openehr_deferred_reason`, INT-032), never invented.

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Reason for visit | `EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2 | Difficulty following speech, especially in noise | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q3 | One ear hears less than the other | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q4 | Ringing or buzzing | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q5 | Dizziness or imbalance | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q6 | Ear discharge | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q7 | Ear pain | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q8 | Long exposure to loud sound | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q9 | Current hearing-aid use | `OBSERVATION.story.v1` (narrative only) | deferred; no device root |
| Q10 | Hearing loss in the family | **no root — export blocked (INT-041)** | — |
| Q11 | Something put in the ear at home | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q12 | Past prolonged in-hospital drug treatment | `OBSERVATION.story.v1` (narrative only) | deferred |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm sign | Source | base item | This proposal's role |
|---|---|---|---|
| Sudden hearing loss | OD-S1 ("If sudden, refer urgently"), OD-S2 ("hemen başvurmak"), OD-S5 | not a base rule; physician / KBB pack | **Not asked here** — left to base.life_threat owner and physician |
| Sudden one-sided hearing loss with facial droop | NG98 wording seen in search summaries only | `rf.stroke_fast` (named gap) | Not asked; see `noroloji.md` |
| Mastoiditis (pain behind the ear, fever, discharge) | OD-S1 ("Refer urgently … Mastoiditis needs urgent management!") | **absent** from base.life_threat | Q6, Q7 are history inputs only; §4 gap for the base owner |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Sudden hearing loss | "If sudden, refer urgently" · "hemen başvurmak olmalıdır" | OD-S1, OD-S2 |
| Signs of mastoiditis | "Mastoiditis needs urgent management!" | OD-S1 |
| Tinnitus or dizziness persisting as the main symptom | "continued for more than a few weeks, the person should be referred to a specialist" | OD-S1 |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE —
clinician to approve wording.** No item carries a triage level. Q1 binds to the pack's
`basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake; OD-S1 ("Ask what the problem is with the ear")
> "Bugün odyoloji, yani işitme polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Difficulty following speech** · archetype: `OBSERVATION.symptom_sign.v1` · source: OD-S3, OD-S4 ("gürültülü ortamda konuşulanı anlamakta zorluk")
> "Konuşulanları, özellikle kalabalık ya da gürültülü ortamlarda anlamakta zorlanıyor musunuz?"
gen: slot=konusmayi_anlamada_zorluk; type=boolean
CANDIDATE — clinician to approve wording. Own words; not an HHIE-S item.

**Q3 — One ear hears less** · archetype: `OBSERVATION.symptom_sign.v1` · source: OD-S1 ("whether one or both ears are affected")
> "Bir kulağınız diğerine göre daha az mı duyuyor?"
gen: slot=tek_kulakta_daha_az_duyma; type=boolean
CANDIDATE — clinician to approve wording. Onset speed is not asked (§2.2).

**Q4 — Ringing or buzzing** · archetype: `OBSERVATION.symptom_sign.v1` · source: OD-S1 ("persistent ringing or buzzing sensation in the ear"), OD-S2 ("çınlama uğultu")
> "Kulağınızda çınlama ya da uğultu gibi bir ses duyuyor musunuz?"
gen: slot=kulak_cinlamasi; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Dizziness or imbalance** · archetype: `OBSERVATION.symptom_sign.v1` · source: OD-S1 ("dizziness"), OD-S2 ("Baş dönmesi bu belirtilere eşlik edebilir.")
> "Baş dönmesi ya da dengesizlik yaşıyor musunuz?"
gen: slot=bas_donmesi_dengesizlik; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Ear discharge** · archetype: `OBSERVATION.symptom_sign.v1` · source: OD-S1 ("discharge from the ear")
> "Kulağınızdan akıntı geliyor mu?"
gen: slot=kulak_akintisi; type=boolean
CANDIDATE — clinician to approve wording. Same wording as `kulak_burun_bogaz_hastaliklari.md`.

**Q7 — Ear pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: OD-S1 ("pain in the ear")
> "Kulağınızda ağrı var mı?"
gen: slot=kulak_agrisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — Long exposure to loud sound** · archetype: `OBSERVATION.story.v1` · source: OD-S1 ("hearing loud noise for a long time (such as working in a factory)")
> "İşinizde ya da günlük hayatınızda uzun süre yüksek sesli ortamlarda bulunuyor musunuz?"
gen: slot=yuksek_sese_maruziyet; type=boolean
CANDIDATE — clinician to approve wording. Exposure only; the job itself comes from base `occupation`.

**Q9 — Current hearing-aid use** · archetype: `OBSERVATION.story.v1` · source: OD-S1 ("use of hearing aids and cochlear implants")
> "Şu anda işitme cihazı kullanıyor musunuz?"
gen: slot=isitme_cihazi_kullanimi; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Hearing loss in the family** · archetype: **no root — export blocked (INT-041)** · source: OD-S1 ("Hearing loss can be hereditary and carried through generations of a family.")
> "Ailenizde işitme kaybı olan biri var mı?"
gen: slot=ailede_isitme_kaybi; type=boolean
CANDIDATE — clinician to approve wording. Relatives' condition only, never their identity.

**Q11 — Something put in the ear at home** · archetype: `OBSERVATION.story.v1` · source: OD-S1 NOTE ("put any foreign objects in their ear, or used any home remedies, such as hot oil")
> "Kulağınıza evde yağ ya da başka bir şey koyduğunuz oldu mu?"
gen: slot=kulaga_evde_uygulama; type=boolean
CANDIDATE — clinician to approve wording.

**Q12 — Past prolonged in-hospital drug treatment** · archetype: `OBSERVATION.story.v1` · source: OD-S1 ("history of hospitalization or prolonged drug therapy")
> "Daha önce hastanede yatarak uzun süre ilaç tedavisi aldınız mı?"
gen: slot=uzun_sureli_hastane_ilac_tedavisi; type=boolean
CANDIDATE — clinician to approve wording. Ototoxic-drug context; current medicines come from base.

*(12 candidate questions; all 12 generate.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Turkish audiology source** (Türk Odyoloji Derneği, Odyoloji ve Konuşma Bozuklukları Derneği, or an
   SB protocol for adult hearing assessment) — not found; only TKBBV lay pages. **NO SOURCE FOUND —
   clinician must supply.**
2. **NICE NG98 primary text** — HTTP 403; unilateral/asymmetric and tinnitus/vertigo criteria not quoted.
3. **Children** — the HSGM newborn and school hearing-screening programmes were seen only in search
   summaries (the HSGM pages returned 404); paediatric milestones (OD-S1 has them) are not drafted. A
   paediatric variant needs a paediatrician's sign-off.
4. **Mastoiditis and sudden hearing loss** — neither is a `base.life_threat` rule today; placement is for
   the base owner and physician (invariant 7). This pack asks neither.
5. **Hearing-aid detail** (type, side, satisfaction) and **cochlear implant** — not drafted.
6. **Prior ear surgery** — no verbatim source retrieved; not drafted.
7. **EK-4 acuity** — no level proposed; RED axes (invariant 21) deliberately unassigned.
8. **openEHR leaf paths** — deferred (INT-032); no family-history or device root in the OPT (INT-041).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE.
- **Inv. 7** — sudden hearing loss and mastoiditis left to `base.life_threat` / physician (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals in any candidate question.
- **Instruments** — no HHIE-S or other hearing-handicap item reproduced.
- **HB-C1** — awaits clinician sign-off; NOT served.
