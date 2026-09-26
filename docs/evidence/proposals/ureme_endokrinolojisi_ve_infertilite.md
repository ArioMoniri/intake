# Üreme Endokrinolojisi ve İnfertilite (Reproductive endocrinology & infertility) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Üreme Endokrinolojisi ve İnfertilite
Taxonomy id: `ureme_endokrinolojisi_ve_infertilite` (branches.yaml — cluster `womens_health`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (history capture for a clinician-ready note)
for an **adult with female reproductive organs, answering for herself**, who is concerned about
conceiving — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign
off*. It assigns **no** RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below cites a **real source that was actually retrieved on 2026-09-26** (URL +
  recommendation or page locator + a short verbatim anchor). Where no source was found, the row reads
  **"NO SOURCE FOUND — clinician must supply"**. Nothing was invented.
- **Quoting policy:** verbatim anchors are kept to short term-level fragments (copyright; see §4 gap 6).
- **Turkish first, honestly:** no versioned Turkish infertility guideline (TSRM, TJOD or Ministry) was
  retrievable (§4 gap 1). The only Türkiye source is the Ministry antenatal guideline's history items
  (UI-S5). The clinical backbone is therefore **NICE NG257 (March 2026)** and the **WHO 2025 infertility
  guideline**, with NICE NG73 and the 2023 international PCOS guideline for specific symptoms.
- **Triage:** per invariant 1, nothing here assigns a level, route, register or location. This clinic's
  emergencies (ectopic pregnancy after conception, severe ovarian hyperstimulation after treatment) are
  **not** asked here; §2.2/§2.3 record where they belong.
- **No duplication of base intake:** `pregnancy_status`, `lmp_date`, medications, allergies, smoking,
  alcohol and weight are asked by `packages/protocols/base/intake.yaml`; they are not repeated here.
- **Verification caveat:** PDFs were streamed and text-extracted with `pdftotext`, and the PCOS
  recommendations read from the Europe PMC full-text API (nothing saved to disk). Re-check every anchor
  before sign-off; until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/ureme_endokrinolojisi_ve_infertilite.yaml`.

---

## 1. Sources found (real, retrieved) with locators

### UI-S1 — NICE NG257 *Fertility problems: assessment and treatment* (International; primary)
- **guideline_id (proposed):** `NICE-NG257` · **Version:** Published 31 March 2026 (supersedes CG156)
- **URL:** https://www.nice.org.uk/guidance/ng257/resources/fertility-problems-assessment-and-treatment-pdf-66144022104517
- **Locators:**
  - Rec 1.16.1 — offer an initial assessment; "Ask about lifestyle and sexual history".
  - Rec 1.16.5 — not conceived "after 1 year of unprotected vaginal sexual intercourse" → offer "both
    partners further clinical assessment and investigation".
  - Rec 1.16.7 — a "miscarriage or ectopic pregnancy" during the trying period does not restart the clock.
  - Rec 1.17.1 — semen analysis compared with WHO reference values.
  - Rec 1.18.6 — ask "about the frequency and regularity of their menstrual cycles".
  - Rec 1.18.11 — prolactin only with an ovulatory disorder, "galactorrhoea" or a pituitary tumour.
  - Rec 1.18.13 — comorbidities "such as pelvic inflammatory disease, previous ectopic pregnancy or
    endometriosis" change the tubal work-up.
  - Rec 1.46 — OHSS prevention is delegated to the ESHRE ovarian-stimulation guideline (not retrieved).
- **Confidence: HIGH** (primary PDF).

### UI-S2 — WHO *Guideline for the prevention, diagnosis and treatment of infertility: summary of recommendations* (International; primary)
- **guideline_id (proposed):** `WHO-INFERTILITY-2025` · **Version:** © World Health Organization 2025
  (launched November 2025); recommendations also published in *Human Reproduction* 41(1),
  doi:10.1093/humrep/deaf212 (metadata seen only)
- **URL:** https://iris.who.int/server/api/core/bitstreams/ad3b700d-2c90-44fc-bd6f-fd93227b6a5a/content
- **Locators:** Introduction — infertility defined as "failure to achieve a pregnancy after 12 months
  of regular unprotected" intercourse. Ovulatory-dysfunction recommendations — ovulation work-up differs
  when history is normal "(including regular menstrual cycles)"; good-practice statement that test
  choice rests on "a comprehensive medical history and physical examination".
- **Confidence: HIGH** (WHO primary PDF).

### UI-S3 — NICE NG73 *Endometriosis: diagnosis and management* (International; primary)
- **guideline_id (proposed):** `NICE-NG73` · Published 6 September 2017; last updated 11 November 2024
- **URL:** https://www.nice.org.uk/guidance/ng73/resources/endometriosis-diagnosis-and-management-pdf-1837632548293
- **Locator:** Rec 1.3.1 — suspect endometriosis with period-related pain "affecting daily activities",
  "deep pain during or after sexual intercourse", or "infertility in association with" these.
- **Confidence: HIGH** (primary PDF).

### UI-S4 — *Recommendations from the 2023 International Evidence-based Guideline for the Assessment and Management of PCOS* (International; primary)
- **guideline_id (proposed):** `PCOS-INTL-2023`
- **Citation:** Teede HJ et al. *J Clin Endocrinol Metab* 2023;108(10):2447–2469, doi:10.1210/clinem/dgad463
  (PMC10505534); parallel publication *Eur J Endocrinol* 2023;189(2):G43–G64, doi:10.1093/ejendo/lvad096
- **URL (retrieved):** https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10505534/fullTextXML
- **Locators:** Rec 1.3.1 — "The presence of hirsutism alone should be considered predictive" of
  biochemical hyperandrogenism and PCOS in adults. Rec 1.3.3 — history and examination should cover
  acne, female pattern hair loss and hirsutism. Rec 1.1.1 — definitions of irregular cycles.
- **Confidence: HIGH** (full text via Europe PMC; the Monash-hosted PDF blocked scripted download).

### UI-S5 — T.C. Sağlık Bakanlığı *Doğum Öncesi Bakım Yönetim Rehberi* (Türkiye; antenatal context only)
- **guideline_id (proposed):** `TR-SB-DOBYR-2018` · Ankara, 2018 · Yayın No: 925
- **URL (WHO mirror):** https://platform.who.int/docs/default-source/mca-documents/policy-documents/guideline/TUR-MN-21-01-GUIDELINE-2018-tur-Antenatal-Care-Management-Guidelines.pdf
- **Locators:** PDF p. 13 — "İnfertilite hikayesi mevcut ise süresi, gördüğü tedaviler (IVF vb.)";
  PDF p. 14 — "Adet düzeni"; risk form PDF pp. 36–37 — B-3 "Tekrarlayan Düşük", B-13 "Ektopik Gebelik".
- **Confidence: HIGH** for content, **LOW** for fit: it is an antenatal guideline, used only as a
  Türkiye anchor for which history items a Turkish clinician records.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032), never invented.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Time trying to conceive (duration; now the pack's `sikayet_suresi` slot via the §3 pack line) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Menstrual regularity | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); no menstrual archetype in the OPT |
| Q4 | Period pain limiting daily life | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Deep pain with intercourse | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Increased unwanted hair growth | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Nipple milk discharge when not pregnant/breastfeeding | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Any previous pregnancy | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Miscarriage or ectopic pregnancy | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Previous pelvic infection | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q11 | Previous fertility treatment | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); no procedure archetype in the OPT |
| Q12 | Partner semen analysis done | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032); partner data is a second data subject (§4 gap 4) |

### 2.2 Overlap with `base.life_threat` (NOT extended — invariant 7)

No question in this pack is an emergency symptom. Two clinic-specific emergencies are recorded so they
are not lost:

| Emergency | Where it belongs | Status |
|---|---|---|
| Ectopic pregnancy after conception (pain or bleeding in early pregnancy) | `rf.ectopic_possible` — named in `base.life_threat` `known_named_gaps` (no-ceiling list) and in HB-C4 | not asked here; owned by `base.life_threat` |
| Severe ovarian hyperstimulation after stimulation treatment | **absent** from `base.life_threat` and HB-C4 | not asked here; §4 gap 3 |

### 2.3 Red-flag candidates — for physician review — not encoded

No level, route, register or location is proposed (invariants 1, 7, 21).

| Candidate | Source | Status |
|---|---|---|
| Possible ectopic pregnancy (positive test or possible pregnancy with pain/bleeding) | UI-S1 rec 1.16.7 names ectopic pregnancy; symptom list is in NICE NG126 (cited in `kadin_hastaliklari_ve_dogum.md` S3) | not encoded; `rf.ectopic_possible` / HB-C4 |
| Severe ovarian hyperstimulation symptoms after treatment | UI-S1 rec 1.46 defers to the ESHRE ovarian-stimulation guideline — **NO SOURCE FOUND (verbatim symptom list)** | not encoded |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and exactly one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22); written in our own
words. **All CANDIDATE — clinician to approve wording.** No item carries a triage level. Q1 binds to the
pack's `basvuru_nedeni` slot. Checked by hand against the Turkish PolicyGuard arms (unsigned — HB-C23).

Duration (was Q2, moved in wave 7 so the pack has one duration ask, not two): the time trying to
conceive becomes the pack's `sikayet_suresi` slot, which stays `type: duration` (a duration picker, not
free numeric text, invariant 22). Sources: UI-S1 rec 1.16.5; UI-S2 (definition); UI-S5 PDF p. 13. The
twelve-month threshold is the clinician's, never spoken. This is reproductive history and should be
`text_first`, but the duration slot cannot carry `delivery` until the generator gains a duration
delivery key (wave-7 verification §E-2). Do not promote this pack before then.

pack: duration_ask=Ne zamandır korunmadan gebe kalmayı deniyorsunuz?; duration_follow_up=Ay ya da yıl olarak yaklaşık söyleyebilir misiniz?

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake; UI-S1 rec 1.16.1
> "Bugün bu polikliniğe gelirken en çok konuşmak istediğiniz konu nedir?"
CANDIDATE — clinician to approve wording.

**Q3 — Menstrual regularity** · archetype: `OBSERVATION.story.v1` · source: UI-S1 rec 1.18.6; UI-S2 (ovulatory dysfunction); UI-S4 rec 1.1.1; UI-S5 PDF p. 14 ("Adet düzeni")
> "Adetleriniz genellikle her ay düzenli olarak geliyor mu?"
gen: slot=adet_duzenli; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Note the polarity: "evet" is the expected answer.

**Q4 — Period pain limiting daily life** · archetype: `OBSERVATION.symptom_sign.v1` · source: UI-S3 rec 1.3.1 ("affecting daily activities")
> "Adet dönemlerinizde günlük işlerinizi zorlaştıran ağrılar oluyor mu?"
gen: slot=agrili_adet; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording.

**Q5 — Deep pain with intercourse** · archetype: `OBSERVATION.symptom_sign.v1` · source: UI-S3 rec 1.3.1 ("deep pain during or after sexual intercourse"); UI-S1 rec 1.16.1 (sexual history)
> "Cinsel ilişki sırasında ya da sonrasında derin bir ağrı hissediyor musunuz?"
gen: slot=iliski_sirasinda_agri; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Sensitive: `text_first` (§4 gap 5, resolved in wave 7).

**Q6 — Increased unwanted hair growth** · archetype: `OBSERVATION.symptom_sign.v1` · source: UI-S4 recs 1.3.1 and 1.3.3
> "Yüzünüzde ya da vücudunuzda istenmeyen kıllanmada artış fark ettiniz mi?"
gen: slot=killanma_artisi; type=boolean
CANDIDATE — clinician to approve wording. "Kıllanma" is the lay term; no jargon.

**Q7 — Milk from the breast when not pregnant or breastfeeding** · archetype: `OBSERVATION.symptom_sign.v1` · source: UI-S1 rec 1.18.11 ("galactorrhoea")
> "Emzirmediğiniz ve hamile olmadığınız halde memenizden süt geliyor mu?"
gen: slot=memeden_sut_gelmesi; type=boolean
CANDIDATE — clinician to approve wording. "ve" (not "ya da") so that a woman who is breastfeeding but
not pregnant does not answer yes (wave-7 fix).

**Q8 — Any previous pregnancy** · archetype: `OBSERVATION.story.v1` · source: UI-S1 rec 1.16.7; UI-S5 PDF p. 13 (obstetric history)
> "Daha önce hiç hamile kaldınız mı?"
gen: slot=onceki_gebelik; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Gate for Q9.

**Q9 — Miscarriage or ectopic pregnancy** · archetype: `OBSERVATION.story.v1` · source: UI-S1 recs 1.16.7 and 1.18.13; UI-S5 risk form B-3, B-13
> "Gebeliklerinizden herhangi biri düşük ya da dış gebelikle sonuçlandı mı?"
gen: slot=dusuk_ya_da_dis_gebelik; type=boolean; ask_if=onceki_gebelik == true; delivery=text_first
CANDIDATE — clinician to approve wording. "Dış gebelik" is the lay Turkish term. No count is asked
(no numeric entry, invariant 22); the number of losses is for the consultation.

**Q10 — Previous pelvic infection** · archetype: `EVALUATION.problem_diagnosis.v1` · source: UI-S1 rec 1.18.13 ("pelvic inflammatory disease")
> "Daha önce rahim, tüp ya da yumurtalıklarınızda iltihap geçirdiniz mi?"
gen: slot=pelvik_iltihap; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording.

**Q11a — Previous fertility treatment** · archetype: `OBSERVATION.story.v1` · source: UI-S5 PDF p. 13 ("gördüğü tedaviler (IVF vb.)"); UI-S2
> "Daha önce gebe kalmak için bir tedavi gördünüz mü?"
gen: slot=onceki_tedavi; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Gate for Q11b.

**Q11b — Which treatments** · archetype: `OBSERVATION.story.v1` · source: UI-S5 PDF p. 13 ("gördüğü tedaviler (IVF vb.)"); UI-S2
> "Hangi tedavileri gördüğünüzü kısaca anlatır mısınız?"
gen: slot=onceki_tedavi_aciklama; type=string; ask_if=onceki_tedavi == true; delivery=text_first
CANDIDATE — clinician to approve wording. The narrative has its own string slot (wave-7 split).

**Q12 — Partner semen analysis** · archetype: `OBSERVATION.story.v1` · source: UI-S1 recs 1.16.5 ("both partners") and 1.17.1; UI-S2 (male-factor recommendations)
> "Eşinize ya da partnerinize daha önce sperm tahlili yapıldı mı?"
gen: slot=partner_sperm_tahlili; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Records only whether a test was done, not its result.
Partner data, so `text_first`. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register
row pending counsel review (INT-349).

*(12 candidate questions: 12 source-backed; none is an emergency symptom. After wave 7, Q2 is the pack's
duration line and Q11 is split, so §3 carries twelve Q items.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish infertility guideline** — TSRM (tsrm.org.tr) lists reviews ("derlemeler") but no
   versioned assessment guideline was found; no TJOD or Ministry infertility-assessment guideline was
   retrieved; the ÜTCD textbook PDF seen in search results is a book, not a guideline. **NO SOURCE
   FOUND — clinician must supply** a Türkiye-first source to outrank UI-S1/UI-S2.
2. **ESHRE guidelines** (endometriosis 2022, recurrent pregnancy loss 2022, ovarian stimulation) — not
   retrieved; UI-S3 (NICE NG73) is used for endometriosis symptoms instead. **NO SOURCE FOUND (verbatim)**.
3. **Ovarian hyperstimulation is absent from `base.life_threat`** and from HB-C4. A patient mid-treatment
   could book this clinic with it. **Clinician must decide** placement; the symptom list needs the ESHRE
   source (gap 2).
4. **Partner data (Q12)** — the partner is a second data subject. Per invariant 18 every new data field
   needs the inventory annotation {category, purpose, basis, retention, recipients}, and persisting a
   new category of personal data needs a human decision (CLAUDE.md "When to stop and ask"). **Human
   (legal/privacy owner) must decide** before Q12 is generated into a pack. Decided: invariant 18:
   owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349). Q12 is
   generated as `text_first`. Wording for patients without a partner or using donor sperm is still a
   clinician decision.
5. **Sensitive-disclosure delivery** — Q5 (and Q9) touch sexual and reproductive loss history. Resolved
   in wave 7 under files/13 §13: Q3–Q5 and Q8–Q12 are `text_first`; the duration line waits on §E-2.
6. **Copyright / snapshot licence** — NICE and journal texts are copyrighted; WHO is CC BY-NC-SA. A
   committed verbatim snapshot needs a **legal-review decision** on reproduction rights.
7. **Omitted to stay at twelve — sourced, clinician may swap in:** acne and scalp hair loss (UI-S4 rec
   1.3.3); first-degree relative with endometriosis (UI-S3 rec 1.3.2); previous pelvic surgery; thyroid
   symptoms (UI-S2 mentions TSH by presentation). Age is not asked — it is derived from the record.
8. **Every triage level and all three RED axes** (invariant 21) — deliberately **not** assigned.
9. **openEHR** — no menstrual, procedure or partner archetype root in the OPT; leaf paths deferred (INT-032).
10. **PolicyGuard lexicon is itself unsigned (HB-C23).**

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy** — `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording; each item marked CANDIDATE.
- **Inv. 7** — ectopic pregnancy stays in `base.life_threat` (`rf.ectopic_possible`); this pack adds no rule.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at clinician sign-off.
- **Inv. 18** — Q12 is a new data category (partner): owner-approved 2026-09-26; the inventory
  annotation / VERBİS register row is pending counsel review (INT-349) (§4 gap 4).
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals; trying-time is a duration picker; no count or lab value is requested.
- **HB-C1** — awaits clinician sign-off; NOT served.
