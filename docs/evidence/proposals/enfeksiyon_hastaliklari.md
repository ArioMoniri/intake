# Enfeksiyon Hastalıkları (Infectious Diseases) — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

- Specialty / branch: **Enfeksiyon Hastalıkları (Infectious Diseases)** — `specialty.enfeksiyon_hastaliklari` · cluster `medical` · `extends: cluster.medical`
- Author (drafting researcher): medical-researcher agent · moniriario@gmail.com · Date: 2026-09-20
- Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
  note) — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign
  off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.
- **Adult self-report posture:** the patient is an adult answering for themselves, in formal **siz**.
- Scope guard: this document does **not** edit any served pack. The served L0 stub
  `packages/protocols/specialty/enfeksiyon_hastaliklari.yaml`
  (maturity L0, `status: generated-l0-awaiting-clinical-review`) is left untouched.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage (inv. 1):** RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's
  own urgency wording is quoted verbatim; no level is asserted.
- **Life-threatening families stay in `base.life_threat` (inv. 7).** Sepsis-like illness, severe
  bleeding, high/persistent fever and anaphylaxis already live in
  `packages/protocols/base/intake.yaml` as universal families (`rf.sepsis_like`, `rf.severe_bleeding`,
  `rf.fever_high_persistent`, `rf.anaphylaxis`). Meningococcal disease (fever + non-blanching rash)
  presents as a sepsis-like emergency and belongs with `rf.sepsis_like`. This proposal does **not**
  author, tighten or relax any of them; where a candidate question surfaces one of those signs it is
  flagged **"→ base.life_threat (inv. 7); not leveled here"**. Red-flag rules are monotonic across
  inheritance — a specialty pack may add or tighten, never remove or relax, and nothing may extend
  `base.life_threat`.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / PDF read). Before sign-off each verbatim sentence MUST be
  re-checked against the **primary published text** and, per the clinical-content rule, committed as
  a **verbatim source snapshot** under `packages/protocols/sources/` with a full
  `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule stays
  `status: draft_needs_source` and does **not** compile into a served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE sepsis guideline *Suspected sepsis: recognition, diagnosis and early management* (International; primary)
- **guideline_id (proposed):** `NICE-NG51-SEPSIS` (see version note)
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / date:** the NCBI Bookshelf mirror read identifies itself as **"NICE Guideline, No. 51 …
  London: NICE; 2024 Mar 19."** **Version caveat:** an independent web search reports that NG51 has
  since been split into and replaced by **NG253** (people aged 16 or over), **NG254** (under 16s) and
  **NG255** (pregnant or recently pregnant). The branch clinician MUST confirm the current guideline
  number and re-quote from it before sign-off (see §5, G2).
- **URL (canonical):** https://www.nice.org.uk/guidance/ng51/chapter/recommendations
  (nice.org.uk returns HTTP 403 to automated fetch; verbatim text below verified via the NCBI
  Bookshelf mirror)
- **URL (mirror used):** https://www.ncbi.nlm.nih.gov/books/NBK553314/ · retrieved_on: 2026-09-20
- **Verbatim (risk classification, rec 1.11.5):**
  > "a score of 7 or more suggests high risk of severe illness or death from sepsis"
- **Verbatim (clinical-concern indicators, rec 1.11.6):**
  > "mottled or ashen appearance"
  > "non-blanching petechial or purpuric rash"
  > "cyanosis of skin, lips or tongue"
- **Verbatim (emergency referral, rec 1.12.1):**
  > "If they meet any high risk criteria, refer people aged 16 or over with suspected sepsis … for
  > emergency medical care … Use the most appropriate means of transport (usually 999 ambulance)."
- **Note:** the NEWS2 threshold (rec 1.11.5) is a clinician-computed score, **not** a patient-report
  item, so it grounds no intake question — it is quoted only to show the guideline's own urgency
  language. The patient-observable clinical-concern signs (mottled/ashen skin, non-blanching rash,
  cyanosis) are the ones that feed questions below, and each is a **sepsis-like emergency owned by
  `base.life_threat` (inv. 7)**.

### S2 — NICE NG240 *Meningitis (bacterial) and meningococcal disease: recognition, diagnosis and management* (International; primary)
- **guideline_id (proposed):** `NICE-NG240`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / date:** NICE Guideline No. 240, published **19 March 2024**
- **URL (canonical):** https://www.nice.org.uk/guidance/ng240/chapter/Recommendations
  (nice.org.uk returns HTTP 403 to automated fetch; verbatim text below verified via the NCBI
  Bookshelf mirror)
- **URL (mirror used):** https://www.ncbi.nlm.nih.gov/books/NBK604183/ · retrieved_on: 2026-09-20
- **Verbatim (bacterial-meningitis red-flag combination, rec 1.1.4):**
  > "Strongly suspect bacterial meningitis in people with all the symptoms in the red flag
  > combination: fever, headache, neck stiffness, altered level of consciousness or cognition
  > (including confusion or delirium)."
- **Verbatim (meningococcal-disease red flags, rec 1.1.9):**
  > "Strongly suspect meningococcal disease in people with any of these red flag symptoms:
  > haemorrhagic, non-blanching rash with lesions larger than 2 mm (purpura); rapidly progressive
  > and/or spreading non-blanching petechial or purpuric rash; any symptoms and signs of bacterial
  > meningitis … when combined with a non-blanching petechial or purpuric rash."
- **Verbatim (rash caveat, rec 1.1.10):**
  > "Do not rule out meningococcal disease just because a person does not have a rash."
- **Verbatim (emergency transfer, rec 1.1.7 / 1.2.1):**
  > "If you suspect or strongly suspect bacterial meningitis, transfer the person to hospital as an
  > emergency."
- **Verbatim (safety-netting / return advice, rec 1.1.12 / 1.1.16):**
  > "Tell the person and their family members or carers to look out for any changes in the rash,
  > because it can change from blanching to non-blanching."
  > "Ask them to return for further assessment if they develop new symptoms, if a rash changes from
  > blanching to non-blanching, or if existing symptoms get worse."

### S3 — T.C. Sağlık Bakanlığı HSGM *Deprem Bölgesinde Erişkin ve Çocuk Hastalarda Akut İshal Rehberi* (Türkiye; primary body, **disaster-scoped**)
- **guideline_id (proposed):** `TR-HSGM-AKUT-ISHAL-2023`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü (HSGM) — "Deprem Sonrası
  Halk Sağlığı Komisyonu"
- **Version / date:** **Mart 2023, Ankara** (title page); read directly from the PDF
- **URL:** https://deprem.saglik.gov.tr/depo/deprem/rehberler/revize/hsgm-deprem-bolgesinde-akut-ishal-rehberi.pdf
  · retrieved_on: 2026-09-20
- **Verbatim (Tablo 5 — "Akut İshalli Erişkinlerde Yakın Takip Gereken Durumlar", erişkin/adult
  column, selected rows):**
  > "İleri yaş" · "Kronik tıbbi durum veya eşzamanlı hastalık öyküsü" · "Ateş >39 °C" · "Dışkıda gözle
  > görülür kan" · "Sık (>8) ve önemli miktarda dışkılama" · "Sürekli kusma" · "Dehidrasyon ile uyumlu
  > belirtiler (çökük gözler, azalmış gözyaşı, kuru mukoz membranlar, ortostatik hipotansiyon veya
  > azalmış idrar çıkışı)" · "Zihinsel durumda değişiklik (sinirlilik, ilgisizlik veya uyuşukluk)" ·
  > "Halihazırda uygulanan oral rehidrasyon tedavisine yetersiz cevap veya oral rehidrasyon
  > tedavisinin uygulanamaması"
- **Verbatim (Tablo 4 — "Dehidratasyon bulguları", ağır dehidratasyon column):**
  > "Şuur değişikliği" · "İdrar koyulaşması /azalması" · "Hızlı, zayıf nabız; TA düşük veya
  > saptanamaz" · "Periferik siyanoz"
- **Verbatim (recent-antibiotic / C. difficile trigger):**
  > "Son bir ay içinde antibiyotik kullanım öyküsü olan ishalli hastalarda C. difficile toksini
  > araştırılır (lateral flow, ELISA, PCR)"
- **Confidence: MEDIUM, context caveat.** This IS a versioned T.C. Sağlık Bakanlığı / HSGM document
  with a dedicated **adult** section, but it is **disaster (deprem) scoped**, not a routine national
  infectious-disease intake protocol. Its adult danger-sign table is clinically general and
  patient-relevant, yet the branch clinician must confirm applicability to a routine pre-visit
  setting (see §5, G1).

### Türkiye routine-guideline status (honest gap)
- No **routine (non-disaster) T.C. Sağlık Bakanlığı klinik protokolü** or graded **Türk Klinik
  Mikrobiyoloji ve İnfeksiyon Hastalıkları Derneği (KLİMİK) / EKMUD kılavuzu** stating adult
  infectious-disease red-flag thresholds (fever/sepsis danger signs) was located in this session.
  S3 (HSGM) is real MoH but **disaster-scoped**; S1/S2 are international. → **gap G1**. This matches
  the served L0 stub's own note that files/04 and files/09 "name no specific guideline title for the
  'medical' cluster — selection awaits the branch clinician."

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` pins the composition and archetype **roots** only, with **no at-code (`atNNNN`)
leaf nodes** (files/12 §8.1; INT-032). It contains exactly these roots:
`COMPOSITION.intake_previsit.v1`, `EVALUATION.reason_for_encounter.v1`,
`EVALUATION.problem_diagnosis.v1`, `EVALUATION.adverse_reaction_risk.v1`,
`EVALUATION.triage_outcome.v1`, `ACTION.medication.v1`, `OBSERVATION.story.v1`,
`OBSERVATION.symptom_sign.v1`. There is **no** travel/exposure, immunisation or family-history root.
Each item below binds to an archetype **root**; the leaf path stays deferred
(`openehr_deferred_reason`, INT-032) — never fabricated.

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for today's visit | `EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Duration / story of present illness | `OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Fever — presence & duration (S1, S2, S3) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Rigors / feeling severely unwell (S1) → base.life_threat | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | New confusion / drowsiness (S2, S1) → base.life_threat | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Severe headache with neck stiffness (S2) → base.life_threat | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Non-blanching rash (S1, S2) → base.life_threat | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Diarrhoea / visible blood in stool (S3) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Persistent vomiting (S3) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Recent travel / exposure history | **weak — `OBSERVATION.story.v1` fallback** | OBSERVATION | deferred (INT-032) |
| Q11 | Immunosuppression / known chronic disease (S1, S3) | `EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q12 | Current medications / recent antibiotics (S3) | `ACTION.medication.v1` | ACTION | deferred (INT-032) |

Notes:
- **Q10 travel/exposure:** the committed `.opt` exposes no travel-history or exposure archetype root.
  Narrative capture under `OBSERVATION.story.v1` is a **candidate fallback only, pending
  clinician/modeller confirmation** (INT-032); otherwise treat as **"no archetype fits — export
  blocked (INT-041 posture)"** and do not invent an at-code path. → gap G4.
- **Q11 immunosuppression:** `base.intake` already carries an `immunosuppression` slot as one of the
  six additions awaiting authoring (HUMAN_BLOCKERS.md HB-C6); the specialty layer must not duplicate
  or pre-empt that slot. Binding shown is for the openEHR export target only.
- Wellbeing instruments (PHQ-9/GAD-7) have no root in this template and are out of scope for an
  infectious-disease red-flag proposal.
- `triage_outcome` is written by the rules engine, never by an intake question (inv. 1).

---

## 3. Candidate B1 Turkish pre-visit questions (adult self, formal `siz`)

Register: formal **`siz`** throughout; one concern per question (inv. 2: one question per turn);
empathetic; no diagnosis/treatment/prognosis language (PolicyGuard). **All marked "CANDIDATE —
clinician to approve wording".** Per inv. 22 no bare digit reaches TTS — every number in these drafts
is spelled out in Turkish orthography, and there is no free numeric entry on the clinical critical
path (yes/no + optional narrative).

> Triage note for every alarm item: the level is a **`candidate_flag` (max `YELLOW_REVIEW`), pending
> clinician + rules-engine confirmation — NOT authoritative**. Items marked **→ base.life_threat** are
> life-threatening families that already live in `base.intake` (inv. 7) and are **not** leveled here.

**Q1 — Başvuru nedeni** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün sizi kliniğe getiren en önemli şikâyetinizi kendi cümlelerinizle kısaca anlatır mısınız?"
> _CANDIDATE — clinician to approve._

**Q2 — Şikâyet süresi** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu şikâyetiniz ne zaman başladı? Yaklaşık olarak gün ya da hafta olarak söyleyebilir misiniz?"
> _CANDIDATE — clinician to approve. (No free numeric entry on the critical path — narrative only; inv. 22.)_

**Q3 — Ateş ve süresi** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (HSGM "Ateş >39 °C"); S1/S2 (fever within the sepsis / meningitis red-flag combinations)
> "Ateşiniz oldu mu? Olduysa kaç gündür sürdüğünü ve çok yüksek hissedip hissetmediğinizi söyleyebilir misiniz?"
> _CANDIDATE — clinician to approve. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician + rules-engine confirmation — NOT authoritative)** for high or persistent fever, per S3. A high/persistent-fever emergency also lives in `base.life_threat` (`rf.fever_high_persistent`, inv. 7); the numeric temperature threshold is a clinician-set cut-off, surfaced qualitatively — the patient is not asked for a number._

**Q4 — Şiddetli halsizlik / titreme** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE sepsis clinical-concern picture) · **→ base.life_threat (inv. 7); not leveled here**
> "Ateşle birlikte titreme, üşüme ya da kendinizi çok kötü, güçten düşmüş hissetme oldu mu?"
> _CANDIDATE — clinician to approve. Sepsis-like family (`rf.sepsis_like`) lives in base.intake; this question only surfaces the sign._

**Q5 — Yeni ortaya çıkan bilinç bulanıklığı / aşırı uyku** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (NICE NG240 rec 1.1.4 "altered level of consciousness or cognition (including confusion or delirium)"); S3 (HSGM "Zihinsel durumda değişiklik") · **→ base.life_threat (inv. 7); not leveled here**
> "Son zamanlarda kendinizde ya da yakınlarınızın fark ettiği bir bilinç bulanıklığı, aşırı uyku hali veya kafa karışıklığı oldu mu?"
> _CANDIDATE — clinician to approve. Surfaces the sign only; owned by base sepsis-like / meningitis emergency families._

**Q6 — Şiddetli baş ağrısı ile ense sertliği** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (NICE NG240 rec 1.1.4 "fever, headache, neck stiffness …") · **→ base.life_threat (inv. 7); not leveled here**
> "Şiddetli baş ağrınızla birlikte boynunuzu öne eğmekte zorlanma ya da ense sertliği fark ettiniz mi?"
> _CANDIDATE — clinician to approve. NG240 groups these into a red-flag combination; the disease name is not in patient copy (PolicyGuard). Clinician may split headache and neck stiffness into two turns._

**Q7 — Solmayan döküntü** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (NICE NG240 rec 1.1.9 "non-blanching petechial or purpuric rash"); S1 (NICE sepsis rec 1.11.6 "non-blanching petechial or purpuric rash") · **→ base.life_threat (inv. 7); not leveled here**
> "Cildinizde, üzerine bardakla ya da parmakla bastırdığınızda solmayan (kaybolmayan) kırmızı veya mor döküntü fark ettiniz mi?"
> _CANDIDATE — clinician to approve. Describes the sign only; owned by base sepsis-like family. NG240 rec 1.1.10 verbatim warns a rash may be absent, so a "no" here does not clear the emergency — a clinician matter, not an intake level._

**Q8 — İshal ve dışkıda kan** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (HSGM "Dışkıda gözle görülür kan", "Sık (>8) ve önemli miktarda dışkılama")
> "İshaliniz var mı? Varsa dışkınızda gözle görülür kan fark ettiniz mi?"
> _CANDIDATE — clinician to approve. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician + rules-engine confirmation — NOT authoritative)** for visible blood in stool, per S3. Heavy/active bleeding is owned by `base.life_threat` (`rf.severe_bleeding`, inv. 7) and is not leveled here._

**Q9 — Sürekli kusma** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (HSGM "Sürekli kusma")
> "Geçmeyen ya da sık sık tekrarlayan kusmanız oluyor mu?"
> _CANDIDATE — clinician to approve._

**Q10 — Yakın zamanda seyahat / temas** · archetype: `OBSERVATION.story.v1` (weak; export target unresolved — gap G4) · source: general intake (infectious-disease relevance; no red-flag threshold)
> "Son zamanlarda yurt dışına ya da başka bir şehre seyahat ettiniz mi, veya benzer şikâyeti olan biriyle yakın temasınız oldu mu?"
> _CANDIDATE — clinician to approve. Archetype binding unresolved — do not export until G4 is closed. Clinician may split travel and contact into two turns._

**Q11 — Bağışıklık durumu / bilinen süregen hastalık** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S1 (NICE sepsis — immunosuppression raises risk); S3 (HSGM "Kronik tıbbi durum veya eşzamanlı hastalık öyküsü")
> "Bağışıklık sisteminizi etkileyen bir durumunuz ya da daha önce konulmuş süregen bir hastalık tanınız var mı?"
> _CANDIDATE — clinician to approve. `base.intake` already reserves an `immunosuppression` slot (HB-C6); the specialty layer must not duplicate it._

**Q12 — Kullanılan ilaçlar / son bir ayda antibiyotik** · archetype: `ACTION.medication.v1` · source: S3 (HSGM "Son bir ay içinde antibiyotik kullanım öyküsü olan ishalli hastalarda C. difficile toksini araştırılır")
> "Şu anda düzenli kullandığınız ilaçlar var mı? Son bir ay içinde antibiyotik kullandınız mı?"
> _CANDIDATE — clinician to approve. Clinician may split "düzenli ilaç" and "son ay antibiyotik" into two turns._

*(12 candidate questions, Q1–Q12. All tagged CANDIDATE; none served.)*

---

## 4. Candidate triage mapping — NOT authoritative

Per inv. 1, intake output may at most carry `candidate_flags` → `YELLOW_REVIEW`; the
`packages/protocols/triage` engine alone produces RED/YELLOW. Below, the **guideline's own urgency
words are quoted verbatim**; the INTAKE level is a **candidate pending clinician confirmation** only.
Life-threatening rows are owned by `base.life_threat` (inv. 7) and carry no level here.

| Alarm item | Guideline urgency (verbatim) | Source | Disposition |
|------------|------------------------------|--------|-------------|
| Non-blanching rash (± fever) | "Strongly suspect meningococcal disease in people with any of these red flag symptoms: … rapidly progressive and/or spreading non-blanching petechial or purpuric rash"; "transfer the person to hospital as an emergency" | S2 rec 1.1.9 / 1.1.7 | **→ base.life_threat (rf.sepsis_like); not leveled here** |
| Fever + headache + neck stiffness + altered consciousness | "Strongly suspect bacterial meningitis in people with all the symptoms in the red flag combination: fever, headache, neck stiffness, altered level of consciousness or cognition" | S2 rec 1.1.4 | **→ base.life_threat (rf.sepsis_like); not leveled here** |
| Mottled/ashen skin, cyanosis (sepsis picture) | "mottled or ashen appearance"; "cyanosis of skin, lips or tongue" | S1 rec 1.11.6 | **→ base.life_threat (rf.sepsis_like); not leveled here** |
| High or persistent fever | "Ateş >39 °C" | S3 Tablo 5 | candidate `YELLOW_REVIEW` — also owned by `rf.fever_high_persistent`; temperature cut-off is clinician's (G3) |
| Visible blood in stool | "Dışkıda gözle görülür kan" | S3 Tablo 5 | candidate `YELLOW_REVIEW` — heavy/active bleeding → `rf.severe_bleeding` (base); clinician to confirm |
| Persistent vomiting | "Sürekli kusma" | S3 Tablo 5 | candidate `YELLOW_REVIEW` — clinician to confirm |
| Severe dehydration (impaired consciousness, weak pulse, cyanosis) | "Şuur değişikliği … Hızlı, zayıf nabız; TA düşük veya saptanamaz … Periferik siyanoz" | S3 Tablo 4 | **→ base.life_threat (rf.sepsis_like / severe dehydration); not leveled here** |

All three RED axes (route × register × location, inv. 21) are deliberately **not** assigned here.

---

## 5. Gaps — every NO-SOURCE / unresolved item (clinician/human must supply)

- **G1 — Turkish routine authoritative guideline:** no routine (non-disaster) T.C. Sağlık Bakanlığı
  protocol or graded Turkish infectious-disease society guideline (KLİMİK / EKMUD) with adult
  fever/sepsis danger-sign red-flag thresholds was located. S3 (HSGM) is real MoH but
  **disaster-scoped**. **Clinician / branch owner must name the authoritative Türkiye-first routine
  source** and its version/date. → HB-C1.
- **G2 — NICE sepsis version:** the mirror read identifies as **NG51 (2024-03-19)**, but web search
  reports NG51 has been replaced by **NG253 / NG254 / NG255**. Re-verify the current guideline number
  and re-quote the adult high-risk criteria from the current primary text before sign-off. The classic
  patient-reportable high-risk items reported for the pre-2024 NG51 (new altered mental state, not
  passed urine, respiratory rate ≥ a set threshold) were **NOT captured verbatim from the primary
  this session** — clinician must supply.
- **G3 — Fever temperature cut-off:** S3 gives ">39 °C" for adults; INTAKE must **not** hard-code a
  numeric cut-off on the critical path (inv. 22). The Turkish-pathway threshold is the clinician's to
  set; surfaced qualitatively in Q3.
- **G4 — Travel/exposure archetype (Q10):** no travel-history or exposure archetype in
  `previsit_intake.v1.opt`. Binding to `OBSERVATION.story.v1` is a candidate only; otherwise
  **"no archetype fits — export blocked"** → INT-032 / clinician-modeller confirmation.
- **G5 — Every candidate_flag level and all three RED axes** (route × register × location, inv. 21)
  — deliberately **not** assigned. Clinician + `packages/protocols/triage` rules must supply, with
  committed `source` snapshots, before anything compiles.
- **G6 — Verbatim `text_tr` for any approved red-flag script** — must be authored by the clinician
  and spoken verbatim (inv. 10); not drafted here.
- **G7 — `packages/protocols/sources/` snapshot** — each S1–S3 quote must be committed there verbatim
  before any rule may carry a `source` block.

---

## 6. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules engine.
- **Inv. 2 / patient copy** — questions are one-concern, `siz`, B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — sepsis-like / meningococcal / severe bleeding / severe dehydration remain in `base.life_threat`; this proposal neither extends nor relaxes them.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (route/register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare digit in patient copy (all spelled out); no free numeric entry on the critical path.
- **Clinical content rule** — each alarm needs `source: {guideline_id, version, date, url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S3 but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
