# İç Hastalıkları (Internal Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: İç Hastalıkları (Internal Medicine)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) for an **adult patient answering for themselves** — **not** diagnosis, not triage authority.
This file is a *proposal for a clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level
(not even a candidate flag) and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. This proposal assigns **no triage level**. Questions derived from an alarm symptom are
  marked *"feeds `base.life_threat` / rules engine — no level assigned here"*. Sepsis stays in
  `base.life_threat` (invariant 7); nothing here extends or relaxes it.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-26 by
  automated retrieval — NICE PDFs and the TEMD PDF were downloaded and text-extracted with
  `pdftotext`; the HSGM page was fetched as HTML and tag-stripped. Line breaks inside quotes are
  from extraction. Before sign-off, each verbatim sentence MUST be re-checked against the
  **primary published text** and committed as a **verbatim source snapshot** with a full
  `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule
  stays `status: draft_needs_source` and does **not** compile into a served pack.
- This file does **not** edit `packages/protocols/specialty/ic_hastaliklari.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG12 *Suspected cancer: recognition and referral* (International; primary)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE, UK)
- **Version / year:** Published 23 June 2015 · **Last updated 15 April 2026** (as printed on the
  retrieved PDF cover)
- **URLs:** https://www.nice.org.uk/guidance/ng12 · PDF
  https://www.nice.org.uk/guidance/ng12/resources/suspected-cancer-recognition-and-referral-pdf-1837268071621
- **Verbatim (Rec 1.2.1, p. 11 — oesophageal cancer):**
  > "Refer people using a suspected cancer pathway referral for oesophageal cancer if they:
  > • have dysphagia, or • are aged 55 and over, with weight loss, and they have any of the
  > following: － upper abdominal pain － reflux － dyspepsia. [2015, amended 2025]"
- **Verbatim (Rec 1.3.1, pp. 14–15 — colorectal cancer, FIT; excerpt of the bullet list):**
  > "• aged under 50 with rectal bleeding and either of the following unexplained symptoms:
  > － abdominal pain － weight loss, or • aged 50 and over with any of the following unexplained
  > symptoms: － rectal bleeding － abdominal pain － weight loss, or"
- **Verbatim (Rec 1.10.1, p. 28 — leukaemia in adults):**
  > "Consider a very urgent full blood count to assess for leukaemia in adults with any of the
  > following: • pallor • persistent fatigue • unexplained fever • unexplained persistent or
  > recurrent infection • generalised lymphadenopathy • unexplained bruising • unexplained
  > bleeding • unexplained petechiae • hepatosplenomegaly. [2015]"
- **Verbatim (Rec 1.10.8, p. 30 — Hodgkin lymphoma in adults):**
  > "Consider a suspected cancer pathway referral for Hodgkin lymphoma in adults presenting with
  > unexplained lymphadenopathy. When considering referral, take into account any associated
  > symptoms, particularly fever, night sweats, shortness of breath, pruritus, weight loss or
  > alcohol-induced lymph node pain. [2015]"
- **Verbatim (Rec 1.13.2, p. 33 — symptoms of concern in adults):**
  > "For people aged 60 and over with unexplained weight loss (greater than 5% mean weight loss
  > within a 6-month period), which is a symptom of several cancers including colorectal,
  > gastro-oesophageal, lung, prostate, pancreatic and urological cancer:"
- **Confidence: HIGH** for wording (primary PDF, text-extracted). Note: NG12's age and percentage
  thresholds are **referral criteria for clinicians**; they are quoted here for provenance only
  and are **not** asked of the patient and **not** pinned as rule values.

### S2 — TEMD *Diabetes Mellitus ve Komplikasyonlarının Tanı, Tedavi ve İzlem Kılavuzu-2024* (Türkiye-first)
- **guideline_id (proposed):** `TEMD-DM-2024`
- **Publishing body:** Türkiye Endokrinoloji ve Metabolizma Derneği (TEMD), Diyabet Bilimsel
  Çalışma Grubu
- **Version / year:** 16. Baskı (Çevrim içi), Kasım 2024, Ankara · ISBN 978-625-99759-2-4
- **URL:** https://file.temd.org.tr/Uploads/publications/guides/documents/diabetesmellitus2024.pdf
- **Verbatim (TABLO 1.2: Diyabet semptomları, p. 16):**
  > "Klasik semptomlar: Poliüri · Polidipsi · Polifaji veya iştahsızlık · Halsizlik, çabuk
  > yorulma · Ağız kuruluğu · Noktüri" — "Daha az görülen semptomlar: Bulanık görme ·
  > Açıklanamayan ağırlık kaybı · İnatçı enfeksiyonlar · Tekrarlayan mantar enfeksiyonları ·
  > Kaşıntı"
- **Verbatim (p. 15):**
  > "… klasik hiperglisemi semptomlarının (poliüri, polidipsi, açıklanamayan ağırlık kaybı ya da
  > hiperglisemik kriz) eşlik ettiği durumlarda rastgele PG düzeyleri ile konulabilir."
- **Confidence: MEDIUM-HIGH** (Türkiye-first society guideline; PDF text-extracted in two-column
  layout — the table's column pairing must be re-checked against the primary).

### S3 — T.C. Sağlık Bakanlığı HSGM Kanser Dairesi Başkanlığı — *Mart Ayı Kolorektal (Kalın Bağırsak) Kanser Farkındalık Ayı* (Türkiye-first; public education)
- **guideline_id (proposed):** `TR-HSGM-KOLOREKTAL-FARKINDALIK` (public patient-education page,
  NOT a versioned clinical guideline)
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü, Kanser Dairesi Başkanlığı
- **Version / year:** page undated (footer "Copyright © 2025") — see §4 gap
- **URL:** https://hsgm.saglik.gov.tr/tr/haberler-kanser/mart-ayi-kolorektal-kalin-bagirsak-kanser-farkindalik-ayi-2.html
- **Verbatim ("Kolorektal Kanser Belirtileri Nelerdir?"):**
  > "Görülebilecek belirtiler genel olarak şunlardır: İstemsiz kilo kaybı · Uzun süren kabızlık,
  > ishal · Dışkılama alışkanlığında değişiklik · Kansızlık (anemi), halsizlik · … · Dışkı
  > renginde değişiklik · Dışkıda kan görülmesi ya da dışkılamadan sonra makattan kan gelmesi"
- **Confidence: MEDIUM.** Ministry body, but an awareness page rather than a clinical protocol.
  Used as Türkiye-first **patient-language** corroboration of S1, not as a threshold source.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes**. A slot whose leaf path is not yet authored carries
**`openehr_deferred_reason`** (INT-032, P3 export tier) — it is **not** invented.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Course of the complaint since onset | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Unintended weight loss (S1 1.13.2; S2; S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Unexplained fever (S1 1.10.1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Night sweats (S1 1.10.8) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Persistent fatigue (S1 1.10.1; S2; S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Blood in stool / rectal bleeding (S1 1.3.1; S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Dysphagia (S1 1.2.1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Excessive thirst / frequent urination (S2 Tablo 1.2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Known long-term conditions | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 11 | Current regular medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 12 | Drug allergy / adverse reaction | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| 13 | Triage outcome (authoritative level = rules engine only; **none proposed here**) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the adult patient (self); one concern per
question and exactly one question mark per turn (invariant 2); empathetic; no diagnosis/treatment/
prognosis language; no PolicyGuard jargon terms (no *hipoglisemi*, *poliüri*, *dispne* …); every
sentence ≤ fifteen words. **All marked "CANDIDATE — clinician to approve wording".** No numerals
appear (invariant 22). No emergency number or action script is spoken here — RED action scripts
belong to `base.life_threat` / triage, never to an intake question.

> Triage note: **no level is assigned to any question below.** An item marked *feeds
> `base.life_threat`* only supplies a slot the rules engine may read; the authoritative RED and
> all three RED axes (route × register × location, invariant 21) come from
> `packages/protocols/triage` / `base.life_threat`, none of which are supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün sizi doktora getiren en önemli şikâyetiniz nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Course since onset** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu şikâyetiniz başladığından beri zamanla nasıl bir değişim gösterdi?"
CANDIDATE — clinician to approve wording. (Onset/duration itself is the generator's standard
`sikayet_suresi` slot, so it is not repeated here.)

**Q3 — Unintended weight loss** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 Rec 1.13.2
("unexplained weight loss"); S2 ("Açıklanamayan ağırlık kaybı"); S3 ("İstemsiz kilo kaybı")
> "Son aylarda diyet yapmadan kilo verdiğinizi fark ettiniz mi?"
gen: slot=istemsiz_kilo_kaybi; type=boolean
CANDIDATE — clinician to approve wording. The S1 magnitude/age threshold is a clinician criterion,
not asked here and not pinned (§4 gap 3).

**Q4 — Unexplained fever** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 Rec 1.10.1
("unexplained fever")
> "Son zamanlarda nedenini bilmediğiniz bir ateşiniz oldu mu?"
CANDIDATE — clinician to approve wording. Feeds `base.life_threat` (sepsis stays there,
invariant 7) — no level assigned here.

**Q5 — Night sweats** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 Rec 1.10.8 ("fever,
night sweats, shortness of breath, pruritus, weight loss")
> "Geceleri sizi uyandıracak kadar çok terlediğiniz oldu mu?"
CANDIDATE — clinician to approve wording.

**Q6 — Persistent fatigue** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 Rec 1.10.1
("persistent fatigue"); S2 ("Halsizlik, çabuk yorulma"); S3 ("Kansızlık (anemi), halsizlik")
> "Uzun süredir devam eden bir yorgunluk ya da halsizlik hissediyor musunuz?"
CANDIDATE — clinician to approve wording.

**Q7 — Blood in stool** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 ("Dışkıda kan
görülmesi ya da dışkılamadan sonra makattan kan gelmesi"); S1 Rec 1.3.1 ("rectal bleeding")
> "Dışkınızda kan ya da dışkılamadan sonra kan geldiğini fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Heavy/active bleeding is `base.life_threat`
(`rf.severe_bleeding`, currently unsourced there) — no level assigned here. Black/tarry stool is
NOT asked: no verbatim source was retrieved (§4 gap 4).

**Q8 — Difficulty swallowing** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 Rec 1.2.1
("have dysphagia")
> "Yemek yerken lokmanın boğazınızda ya da göğsünüzde takıldığını hissediyor musunuz?"
CANDIDATE — clinician to approve wording.

**Q9 — Excessive thirst / frequent urination** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S2 Tablo 1.2 ("Poliüri", "Polidipsi")
> "Son zamanlarda aşırı susama ya da çok sık idrara çıkma fark ettiniz mi?"
CANDIDATE — clinician to approve wording. One concern (the classic hyperglycaemia pair, S2);
plain words replace the jargon terms, which PolicyGuard would reject.

**Q10 — Known long-term conditions** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general
intake (history)
> "Doktorunuzun daha önce söylediği uzun süreli bir rahatsızlığınız var mı? Örneğin şeker hastalığı, yüksek tansiyon ya da böbrek rahatsızlığı."
CANDIDATE — clinician to approve wording. Examples are prompts, not a checklist.

**Q11 — Current medications** · archetype: `ACTION.medication.v1` · source: general intake (history)
> "Şu anda düzenli olarak kullandığınız ilaçlar var mı?"
CANDIDATE — clinician to approve wording.

**Q12 — Drug allergy / adverse reaction** · archetype: `EVALUATION.adverse_reaction_risk.v1` ·
source: general intake
> "Herhangi bir ilaca karşı alerjiniz ya da kötü bir tepkiniz oldu mu?"
CANDIDATE — clinician to approve wording.

*(12 candidate questions: 7 guideline-sourced — Q3–Q9 — and 5 general intake.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first internal-medicine guideline** — no versioned T.C. Sağlık Bakanlığı or Türkiye
   İç Hastalıkları society document listing adult general-medicine alarm symptoms was located. The
   HSGM general "Kanser belirtileri" page named by search results returned **HTTP 404** on
   2026-09-26. **NO SOURCE FOUND — clinician must supply** the Türkiye-first primary source, its
   version and date.
2. **S3 is undated** (awareness page, footer "Copyright © 2025" only). **NO SOURCE FOUND (version/
   date) — clinician to confirm** or replace with a dated HSGM protocol.
3. **Weight-loss threshold** — S1 1.13.2's "greater than 5% … within a 6-month period" and age cut-offs
   are clinician referral criteria; a patient-reportable threshold is **NO SOURCE FOUND —
   clinician must supply** if any is wanted. Not pinned here.
4. **Melaena (black/tarry stool)** — no verbatim guideline sentence was retrieved (S3 says only
   "Dışkı renginde değişiklik"). **NO SOURCE FOUND — clinician must supply** before a melaena
   question is added.
5. **Fever duration / sepsis signs** — S1 sources "unexplained fever" only; any duration threshold
   or sepsis pattern is **NO SOURCE FOUND here** and belongs to `base.life_threat`
   (`rf.sepsis_like`, currently unsourced there per its own `known_named_gaps`).
6. **Night-sweats and fatigue standalone significance** — S1 names both only as associated
   symptoms / FBC triggers, not as standalone red flags. **NO SOURCE FOUND** for a standalone
   urgency; no level is implied.
7. **Chest pain / breathlessness / syncope** — intentionally not duplicated; they belong to
   `base.life_threat` and the kardiyoloji/göğüs packs.
8. **Every triage level and all three RED axes** (invariant 21) — deliberately **not** assigned.
   **Clinician + `packages/protocols/triage` rules must supply**, with committed `source` snapshots.
9. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.
10. **PolicyGuard lexicon is itself unsigned (HB-C23)** — the questions were checked against the
    current arms, but the arms await a named clinician's signature.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy rules** — one concern, one question mark, `siz`, ≤ B1, no diagnosis/
  treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — sepsis and severe bleeding stay in `base.life_threat`; this pack only feeds slots.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at clinician sign-off.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals in any question; NG12 numerals appear only inside §1 source quotes.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; this proposal supplies candidates S1–S3 but
  commits no snapshot.
- **HB-C1** — awaits clinician sign-off; NOT served.
