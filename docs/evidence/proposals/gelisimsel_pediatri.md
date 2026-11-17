# Gelişimsel Pediatri (Developmental Paediatrics) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Gelişimsel Pediatri (Developmental Paediatrics)
Taxonomy id: `gelisimsel_pediatri` (branches.yaml — cluster `child_health`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (history capture for a clinician-ready
note) — **not** diagnosis, not a developmental screen, not triage authority. The respondent is the
**parent/caregiver (proxy)**; every question is addressed to them in formal **`siz`** about
*çocuğunuz*. This file is a *proposal for a clinician to sign off*. It assigns **no**
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the primary source is the T.C. Sağlık Bakanlığı / Türkiye Halk Sağlığı Kurumu
  *Bebek, Çocuk, Ergen İzlem Protokolleri* — prepared, per its own front matter, "Gelişimsel Pediatri
  Derneği, Sosyal Pediatri Derneği … bilimsel katkıları ile". CDC *Learn the Signs. Act Early.* and NHS
  GeNotes are the international corroboration. AAP (Lipkin & Macias 2020) and NICE CG128 returned
  HTTP 403 and are **not quoted** (§4).
- **Validated developmental screeners are NOT reproduced or paraphrased here.** GİDR (Gelişimi İzleme
  ve Destekleme Rehberi — the Turkish validated tool in the MoH protocol, GP-S1), Denver II, ASQ and
  M-CHAT are instruments with their own validation and licence terms. None of their items is asked or
  reworded below; they are **delivered elsewhere** (clinician-administered, or through the
  instrument lane once `instrument_licence_gate` returns `GO`). Licence status of each is
  **unverified here** — see §4 gap 3. Q1–Q13 are history items (who noticed, loss of skills,
  perinatal history, hearing/vision concern, prior assessment, family history), not milestone items.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger. Sources' own urgency wording is quoted verbatim in
  §2.3 for physician review only.
- **Invariant 7:** acute paediatric presentations (seizure, lethargy, poor feeding, breathing
  difficulty) are `base.life_threat` / base paediatric territory (§2.2) — the base file itself records
  its paediatric rules as absent. This proposal does not add to or extend `base.life_threat`.
- **Verification caveat (every quote in §1):** GP-S1 was extracted locally with `pdftotext` from the
  fetched PDF; the web pages were captured with WebFetch, whose output is model-rendered. Before
  sign-off each sentence MUST be re-checked against the primary text and committed as a verbatim
  snapshot with `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived
  rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/gelisimsel_pediatri.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### GP-S1 — T.C. Sağlık Bakanlığı / THSK, *Bebek, Çocuk, Ergen İzlem Protokolleri* (Türkiye)
- **guideline_id (proposed):** `THSK-IZLEM-PROTOKOLLERI-2015`
- **Publishing body:** Türkiye Halk Sağlığı Kurumu (T.C. Sağlık Bakanlığı); front matter: "Bu rehber;
  Çocuk Nefroloji Derneği, Çocuk Acil Tıp ve Yoğun Bakım Derneği, Gelişimsel Pediatri Derneği, Sosyal
  Pediatri Derneği, Türk Neonatoloji Derneği ve Türk Oftalmoloji Derneği'nin bilimsel katkıları ile
  hazırlanmıştır"
- **Date:** no printed date; PDF metadata created 10 June 2015. An HSGM 2018 edition exists
  (`Bebek_Cocuk_Ergen_Izlem_Protokolleri_2018.pdf`) but exceeded the fetch size limit and was **not
  retrieved** — clinician must confirm the 2018 text is unchanged (§4 gap 1).
- **URL:** https://dosyaism.saglik.gov.tr/Eklenti/9010,bebek-cocuk-izlem-protokolleripdf.pdf
- **Verbatim — Y15 GİDR Uygulama Kılavuzu, "Ailenin kaygılarının öğrenilmesi" (p. 152):**
  > "Yapılan araştırmalar, ailelerin kaygılarını öğrenmenin gelişimsel sorunların tanısı ve
  > sağaltımında önemli olduğunu göstermiştir."
- **Verbatim — Y15, prematurity and corrected age (p. 151):**
  > "Prematüre doğan (37 hafta ve altı) bebekler için iki ya da üç yaşa kadar düzeltilmiş yaş
  > kullanılmalıdır."
- **Verbatim — Y15, common causes of delay (p. 155):**
  > "Örneğin ev ortamında uygun uyaranların ve şefkatli bakımın eksikliği, malnutrisyon, demir
  > eksikliği, işitme ve görme kayıpları, kronik hastalıklar, annede depresyon gibi psikososyal
  > sorunlar, perinatal riskler, gelişimsel gecikmelerin sık rastlanan nedenleridir."
- **Verbatim — Y15, services (p. 155):**
  > "… erken destek programları, kreş, konuşma terapisi, özel eğitim, fizyoterapi, rehabilitasyon gibi
  > hizmetler ve bunları sağlayacak olan değerlendirmeler konuşulabilir."
- **Verbatim — Y15, GİDR is a validated instrument (p. 149):**
  > "GİDR'nin Türk çocuklarında standardizasyon, güvenilirlik, geçerlilik araştırmaları 2008 yılında
  > tamamlanmış, uluslararası literatürde yer almıştır."
- **Verbatim — Y8 İşitme Taraması (p. 124):**
  > "Her yenidoğan bebek mutlaka işitme taramasına yönlendirilmeli ve tarama yapılması sağlanmalıdır."
  > Risk list items: "Prematürite (<37 hafta)" · "2 günden daha fazla YDYBÜ'de kalma" · "Hiperbilirubinemi"
- **Confidence: MEDIUM–HIGH** — Ministry protocol with the Gelişimsel Pediatri Derneği as named
  contributor; text extracted locally from the primary PDF. Edition question open (gap 1).

### GP-S2 — CDC, *Learn the Signs. Act Early.* — "CDC's Developmental Milestones" (international)
- **guideline_id (proposed):** `CDC-LTSAE-MILESTONES` (public parent page, NOT a guideline)
- **Publishing body:** US Centers for Disease Control and Prevention · **Page updated:** Feb. 16, 2026
- **URL:** https://www.cdc.gov/act-early/milestones/index.html
- **Verbatim:**
  > "If your child is not meeting one or more milestones, has lost skills he or she once had, or you
  > have other concerns, act early."
  > "Talk with your child's doctor, share your concerns, and ask about developmental screening."
- **Companion page (2 years):** https://www.cdc.gov/act-early/milestones/2-years.html (date not captured)
  > "Has your child lost any skills he/she once had? Does your child have any special healthcare needs
  > or was he/she born prematurely?"
- **Confidence: MEDIUM** — named public-health body, parent-facing page.

### GP-S3 — NHS England GeNotes, "Patient with developmental delay" (international)
- **guideline_id (proposed):** `GENOTES-DEVELOPMENTAL-DELAY` · **Last reviewed:** 06/02/2026
- **Publishing body:** NHS England Genomics Education Programme
- **URL:** https://www.genomicseducation.hee.nhs.uk/genotes/in-the-clinic/patient-with-developmental-delay/
- **Verbatim:**
  > "developmental regression (loss of previously gained skills) are red flags that require urgent
  > further assessment."
  > "Flags for an underlying genetic diagnosis include: family history of developmental delay; parental
  > consanguinity; dysmorphic features…and hypotonia"
  > "Take a thorough patient history, including family history, mother's health during pregnancy,
  > delivery, neonatal health, milestones in other domains and any loss of milestones."
- **Confidence: MEDIUM** — clinician-education page (also cited by `cocuk_genetik_hastaliklari.md` S1).

### GP-S4 — Gelişimsel Pediatri Derneği, home page (Türkiye)
- **URL:** https://www.gelisimselpediatridernegi.org.tr/ · **Date:** society founded 22 Mart 2010; page undated
- **Verbatim (fragment as rendered):**
  > "Gelişimsel Pediatri, çocukların gelişimlerinin izlenmesi, desteklenmesi, gelişimle ilgili
  > zorlukların önlenmesi…"
  > "Her çocuğun gelişiminin desteklenmesi onun en temel hakkıdır"
- **Confidence: LOW** — scope statement only; **no warning-sign list or versioned guideline** on the
  site (§4 gap 2).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Who first noticed the concern | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Loss of a previously gained skill | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Which skill was lost | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Health problem during pregnancy | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q6 | Born preterm | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q7 | Neonatal intensive care stay | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q8 | Caregiver concern about hearing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Caregiver concern about vision | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Prior developmental assessment | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Current therapy / special education | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Family history of delayed development | **no root — export blocked (INT-041)** | — | — |
| Q13 | Parental consanguinity | **no root — export blocked (INT-041)** | — | — |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

Medications, allergies, weight and the proxy/subject-role check are collected by
`packages/protocols/base/intake.yaml` (`subject_role`, `proxy_reported`) and are not repeated here.

### 2.2 Overlap with `base.life_threat` and with instruments (flagged; NOT proposed for extension — invariant 7)

| Item | Source | base / other owner | This proposal's role |
|---|---|---|---|
| Seizure, lethargy, poor feeding, breathing difficulty in a child | NO SOURCE retrieved here | `base.life_threat` `paediatric_rules` — recorded there as **absent** | Not drafted; left to base owner + paediatric reviewer |
| Developmental regression | GP-S3 ("urgent further assessment"), GP-S2 | none — not a life-threat | Q3 captures presence only; urgency is for the clinician (§2.3) |
| Milestone-by-milestone developmental status | GP-S1 (GİDR is validated) | **instrument** — GİDR / Denver II / ASQ / M-CHAT | **Not asked.** Delivered elsewhere; licence-gated (§4 gap 3) |
| Autism-specific signs (joint attention, name response, pointing) | NICE CG128 / AAP — HTTP 403 | **instrument** territory (M-CHAT items) | **Not asked**, to avoid paraphrasing a screener |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Loss of previously gained skills | "developmental regression (loss of previously gained skills) are red flags that require urgent further assessment." | GP-S3; GP-S2 ("has lost skills he or she once had … act early") |
| Newborn hearing screen not done, or hearing-loss risk factor present | "Her yenidoğan bebek mutlaka işitme taramasına yönlendirilmeli ve tarama yapılması sağlanmalıdır." | GP-S1 Y8 |
| Preterm birth (corrected-age interpretation) | "Prematüre doğan (37 hafta ve altı) bebekler için … düzeltilmiş yaş kullanılmalıdır." | GP-S1 Y15 — a clinician interpretation rule, not an intake flag |

---

## 3. Candidate B1 Turkish pre-visit questions (13)

Register: formal **siz**, addressed to the parent/caregiver about *çocuğunuz*; one concern and one
question mark per turn; at most fifteen words per sentence; no diagnosis/treatment/prognosis
language; no numerals (invariant 22). **All CANDIDATE — clinician to approve wording.** No item
carries a triage level. Duration is captured by the pack's `sikayet_suresi` slot, so no age or time
threshold appears in patient copy. Q1 binds to the pack's `basvuru_nedeni` slot. No item is taken
from, or reworded from, GİDR, Denver II, ASQ or M-CHAT.

The pack line below replaces the fixed duration ask, which addressed the parent's own complaint. It is
addressed to the parent and about the child (wave 7).

pack: duration_ask=Bu durumu ne zamandır fark ediyorsunuz?; duration_follow_up=Ay ya da yıl olarak yaklaşık söyleyebilir misiniz?

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün gelişimsel pediatri polikliniğine getiren konu nedir?"
CANDIDATE — clinician to approve wording. Ends in "nedir?" so the generator uses the neutral reason
follow-up, not one about the parent's own complaint (wave-7 fix).

**Q2 — Who first noticed** · archetype: `OBSERVATION.story.v1` · source: GP-S1 Y15 ("ailelerin kaygılarını öğrenmenin … önemli olduğunu"), GP-S2 ("share your concerns")
> "Bu konuyu ilk kez kim fark etti?"
gen: slot=ilk_fark_eden; type=string; follow_up=Bunu ilk kimin fark ettiğini söyleyebilir misiniz?
CANDIDATE — clinician to approve wording. Parent, relative, teacher or doctor are all valid answers.

**Q3 — Loss of a skill** · archetype: `OBSERVATION.symptom_sign.v1` · source: GP-S3 ("loss of previously gained skills"), GP-S2 ("has lost skills he or she once had")
> "Çocuğunuz daha önce yapabildiği bir beceriyi sonradan kaybetti mi?"
gen: slot=beceri_kaybi; type=boolean
CANDIDATE — clinician to approve wording. Presence only; urgency is a clinician decision (§2.3).

**Q4 — Which skill (if Q3 yes)** · archetype: `OBSERVATION.story.v1` · source: GP-S3 ("any loss of milestones")
> "Hangi beceride bu değişikliği fark ettiniz?"
gen: slot=kaybedilen_beceri; type=string; ask_if=beceri_kaybi == true; follow_up=Konuşma, yürüme ya da oyun gibi hangi beceride değişiklik oldu?
CANDIDATE — clinician to approve wording. The follow-up restates the ask and no longer invites a yes/no
answer to a string slot (wave-7 fix).

**Q5 — Pregnancy history** · archetype: `OBSERVATION.story.v1` (narrative only) · source: GP-S3 ("mother's health during pregnancy"), GP-S1 Y15 ("perinatal riskler")
> "Çocuğunuzun doğumundan önce, hamilelik sırasında önemli bir sağlık sorunu yaşandı mı?"
gen: slot=gebelikte_saglik_sorunu; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Worded so that it reads correctly whoever the caregiver is.
Pregnancy history, and the respondent is often the mother, so `text_first`.

**Q6 — Preterm birth** · archetype: `EVALUATION.problem_diagnosis.v1` · source: GP-S1 Y15 (düzeltilmiş yaş), GP-S1 Y8 ("Prematürite"), GP-S2 ("born prematurely")
> "Çocuğunuz zamanından önce, yani erken doğdu mu?"
gen: slot=erken_dogum; type=boolean
CANDIDATE — clinician to approve wording. Gestational week is not asked (no free numeric entry,
invariant 22); the clinician takes it from records.

**Q7 — Neonatal intensive care** · archetype: `OBSERVATION.story.v1` (narrative only) · source: GP-S1 Y8 ("YDYBÜ'de kalma"), GP-S3 ("neonatal health")
> "Doğumdan sonra çocuğunuz yenidoğan yoğun bakımında kaldı mı?"
gen: slot=yenidogan_yogun_bakim; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — Hearing concern** · archetype: `OBSERVATION.symptom_sign.v1` · source: GP-S1 Y15 ("işitme ve görme kayıpları"), GP-S1 Y8
> "Çocuğunuzun işitmesiyle ilgili bir endişeniz var mı?"
gen: slot=isitme_endisesi; type=boolean
CANDIDATE — clinician to approve wording. Newborn-screen result is taken from records, not asked.

**Q9 — Vision concern** · archetype: `OBSERVATION.symptom_sign.v1` · source: GP-S1 Y15 ("işitme ve görme kayıpları")
> "Çocuğunuzun görmesiyle ilgili bir endişeniz var mı?"
gen: slot=gorme_endisesi; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Prior developmental assessment** · archetype: `OBSERVATION.story.v1` · source: GP-S2 ("ask about developmental screening"), GP-S1 Y15
> "Çocuğunuzun gelişimi daha önce bir uzman tarafından değerlendirildi mi?"
gen: slot=onceki_gelisim_degerlendirmesi; type=boolean
CANDIDATE — clinician to approve wording. Reports can be uploaded through the document lane.

**Q11 — Current support services** · archetype: `OBSERVATION.story.v1` · source: GP-S1 Y15 ("kreş, konuşma terapisi, özel eğitim, fizyoterapi, rehabilitasyon")
> "Çocuğunuz şu anda özel eğitim, konuşma terapisi ya da fizyoterapi gibi bir destek alıyor mu?"
gen: slot=gelisim_destegi_aliyor; type=boolean
CANDIDATE — clinician to approve wording.

**Q12 — Family history of delayed development** · archetype: **no root — export blocked (INT-041)** · source: GP-S3 ("family history of developmental delay")
> "Çocuğunuzun ailesinde gelişimi ya da konuşması geç kalan başka biri var mı?"
gen: slot=ailede_gelisim_gecikmesi; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Relatives' health data, so `text_first`. invariant 18:
owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

**Q13 — Parental consanguinity (sensitive)** · archetype: **no root — export blocked (INT-041)** · source: GP-S3 ("parental consanguinity")
> "Bu soruyu her aileye soruyoruz. Çocuğunuzun anne ve babası arasında akrabalık var mı?"
gen: slot=anne_baba_akrabaligi; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. The lead-in says the question is routine, so it does not
read as a judgement. Duplicates `cocuk_genetik_hastaliklari` Q6 if both packs run — dedupe at merge.
Consanguinity, so `text_first`. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register
row pending counsel review (INT-349).

*(13 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **2018 edition of the MoH protocol** — `Bebek_Cocuk_Ergen_Izlem_Protokolleri_2018.pdf` (HSGM)
   exceeded the fetch size limit; GP-S1 quotes come from the 2015 THSK PDF. **Clinician must confirm
   the 2018 text or supply the current edition.**
2. **Versioned Gelişimsel Pediatri Derneği or Türkiye Milli Pediatri Derneği guideline** on
   developmental warning signs — none found (the society site carries a scope statement only).
   **NO SOURCE FOUND — clinician must supply.**
3. **Developmental instruments** — GİDR, Denver II, ASQ and M-CHAT are validated screeners; their
   licence status for electronic delivery was **not verified** here. They stay out of this pack and
   must pass `instrument_licence_gate` before any lane delivers them. **Owner + counsel.**
4. **AAP clinical report** (Lipkin PH, Macias MM. *Pediatrics* 2020;145(1):e20193449) and **NICE CG128**
   (autism recognition) — both HTTP 403; seen in search summaries only. **NOT quoted.**
5. **Seizures, feeding/swallowing difficulty, sleep and behaviour** — common in this clinic but not
   drafted: no verbatim developmental-paediatrics source was retrieved for them. **Clinician may add.**
6. **Teacher / nursery report** — useful context, but no verbatim source retrieved. Not drafted.
7. **Gestational age, birth weight, age at each milestone** — numbers; not asked (invariant 22). The
   clinician takes them from records or a structured, non-free-text control.
8. **Family history and consanguinity (Q12, Q13)** — no family-history archetype in the OPT; export
   blocked (INT-041 posture) until an INT-032 archetype decision.
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (route × register × location, invariant 21) are
   **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, caregiver-addressed, B1, one question mark per turn, no
  diagnosis/treatment/prognosis wording; each draft marked CANDIDATE.
- **Inv. 7** — acute paediatric life-threats left to base (§2.2); nothing extends `base.life_threat`.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Instruments** — no validated screener item reproduced or paraphrased (§0, §2.2, gap 3).
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question; source ages and weeks stay in §1 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources GP-S1…GP-S4 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
