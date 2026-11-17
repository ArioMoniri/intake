# İş ve Meslek Hastalıkları (Occupational Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: İş ve Meslek Hastalıkları (Occupational Diseases)
Taxonomy id: `is_ve_meslek_hastaliklari` (branches.yaml — cluster `medical`, all visit types).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom and work-history capture for a
clinician-ready note) — **not** diagnosis, not triage authority, **not** a decision that a disease is
work-related, and **not** a fitness-to-work verdict. This file is a *proposal for a clinician to sign
off*. It assigns **no** RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the primary source is the Çalışma ve Sosyal Güvenlik Bakanlığı İSGGM diagnosis
  guide for occupational and work-related diseases (IM-S1), which contains its own history-taking
  section. The İş Sağlığı ve Güvenliği Kanunu (IM-S3) frames the fitness-to-work visit. The ILO list
  (IM-S2) is the international corroboration of the disease groups.
- **Fitness-to-work and work-relatedness are physician decisions.** Visits to this clinic often end in
  a report (işe giriş / periyodik muayene raporu, or a meslek hastalığı assessment with legal and
  social-security consequences). The pack captures history only. Q2 records the **patient's own
  belief** that work is involved; it never asserts that it is.
- **Data-category line (invariant 18) — approved under D3; `text_first`; INT-349 row.** The persona
  research in files/02 names the employer as a person patients fear will see their data, and IM-S3
  requires the worker's health information to be kept confidential. Owner decision D3
  (`docs/evidence/verification/owner-decisions-2026-09-26.md`) approved "employer / occupational
  exposure" as a category for the review-queue candidates. Therefore:
  - **Work-history items are `delivery: text_first`:** the patient's belief that work is involved
    (Q2), co-workers' complaints (Q4), the yes/no hazard classes (Q5, Q7, Q9, Q11), psychosocial
    exposure (Q14) and the items formerly held under invariant 18: named agents (Q6), employer (Q15),
    protective equipment (Q16), work-related sick leave (Q17) and tenure (Q18). Each needs its
    data-inventory row: invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row
    pending counsel review (INT-349).
  - D3 names "employer / occupational exposure"; Q17 (sick leave) and Q18 (tenure) are read as within
    that line. The owner narrows it if not.
  - **Symptom items stay `voice`:** Q3, Q8, Q10, Q12, Q13.
  - D3 does not settle storage, encryption, the per-category legal basis or slot tagging; those stay
    open under INT-349 and must close before any of these items is served.
- **Report and screening visits may carry no complaint.** Q2a asks whether a health complaint exists
  now; Q2–Q4, which presume one, are gated on it. The owner may drop the gate if this clinic sees only
  symptomatic referrals; Q2–Q4 then lose their `ask_if`.
- **Not repeated from base:** occupation itself (`occupation`: "Ne iş yapıyorsunuz?"), medications,
  allergies, smoking, alcohol and pregnancy are asked by base intake.
- **No validated instrument is reproduced.** Q14 asks about the psychosocial exposure IM-S1 names
  ("Aşırı iş yükü"), in line with the pack's other hazard items. The earlier "tükenmiş hissediyor
  musunuz" wording had the shape of the Maslach Burnout Inventory's emotional-exhaustion item and was
  replaced. Mood and burnout screening stay with the consented wellbeing module.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger.
- **Verification caveat (every quote in §1):** IM-S1, IM-S2 and IM-S3 were downloaded and their text
  extracted locally with `pdftotext`. Before sign-off each sentence MUST be re-checked against the
  primary text and committed as a verbatim snapshot with `source: {guideline_id, version, date, url,
  retrieved_on}`. Until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/is_ve_meslek_hastaliklari.yaml` or any
  served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### IM-S1 — ÇSGB İSGGM, "Meslek Hastalıkları ve İş ile İlgili Hastalıklar Tanı Rehberi" (Türkiye)
- **guideline_id (proposed):** `CSGB-ISGGM-MESLEK-HASTALIKLARI-TANI-REHBERI-2012`
- **Publishing body:** T.C. Çalışma ve Sosyal Güvenlik Bakanlığı, İş Sağlığı ve Güvenliği Genel
  Müdürlüğü; prepared under the EU–Türkiye İSGİP project (TR0702.20-01/001).
- **Version / date:** no edition number printed; PDF metadata created 1 February 2012, modified
  8 February 2012 (350 pages). The preface states non-commercial use is free.
- **URL:** https://guvenlitarim.csgb.gov.tr/media/4l0jo25f/meslek-hastal%C4%B1klar%C4%B1-ve-i%C5%9F-ile-ilgili-hastal%C4%B1klar-rehberi.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim — ANAMNEZ, causal-relation questions (p. 11):**
  > "Semptomlar işten uzaklaşmakla(tatil veya iş değişikliği) düzeliyor mu?"
  > "İş arkadaşlarında da aynı maruziyetler aynı semptomlara neden oluyor mu?"
- **Verbatim — ANAMNEZ, short screening list (p. 11):**
  > "Sağlık sorununuzun işinizle ilgili olduğunu düşünüyor musunuz?"
  > "kimyasallar, tozlar, metaller, radyasyon, gürültü veya sık tekrarlanan hareketler"
  > "Bunların herhangi birine geçmişte maruz kaldınız mı?"
  > "İşyerinde kişisel koruyucu kullanıyor musunuz?"
- **Verbatim — ŞİMDİKİ İŞ / ÖNCEKİ İŞLER (p. 12) — the source of the held items:**
  > "İş türü / Endüstri / İşveren adı / Adres"
  > "Bu işte çalışmaya ne zaman başladınız?"
  > "rapor kullandınız mı, işten ayrıldınız mı ya da işsiz kaldınız mı?"
- **Verbatim — noise (Gürültü, p. 133):**
  > "Çoğu zaman kulak çınlaması da eşlik eder."
  > "Nörosensoriyal etkiler başdönmesi, kulak çınlaması, işitmenin azalmasıdır"
- **Verbatim — hand-arm vibration (pp. 140–141):**
  > "Ataklar dakikalar, saatler sürer ve soğuk maruziyetiyle veya emosyonel stresle artar."
  > "Parmak ve ellerde uyuşma ve karıncalanma vardır."
- **Verbatim — occupational asthma (p. 230):**
  > "Öksürük, nefes darlığı, hışıltılı solunum, göğüste tıkanıklık hissi yakınmaları en sık görülen
  > semptomlardır."
  > "“iş dışı ortamlarda, tatillerde rahat mısınız ?” sorusu sorulmalıdır."
- **Verbatim — occupational skin disease (p. 266):**
  > "Mesleki dermatitler sıklıkla ellerde başlar ve önkola yayılır."
  > "Ciltte kızarıklık, kaşıntı, inflamasyon, hassasiyet, lokal şişlik"
- **Verbatim — cumulative trauma disorders (p. 279, Tablo 1 heading and row):**
  > "Birikimsel travma hastalıklarına neden olan risk faktörleri"
  > "Hasta taşıma, inşaat malzemesi taşıma, gıda ve yemek taşıma"
- **Verbatim — burnout (p. 315):**
  > "Tükenmişlik sendromu hizmet sektöründe, özellikle sağlık çalışanlarında daha sık görülür."
  > "Aşırı iş yükü"
- **Verbatim — acute inhalation hazard (p. 13), base.life_threat context only:**
  > "Bazı asfiksanlar yüksek konsantrasyonlarda, oksijenle yer değiştirerek saniyeler içinde ölüme
  > neden olabilirler."
- **Confidence: MEDIUM–HIGH** for text (primary government PDF, extracted locally). It is a
  diagnosis guide, not a versioned clinical guideline; its scope is mining, metal and construction.
  Page numbers are the printed page numbers seen in the extraction; re-check.

### IM-S2 — ILO, "List of Occupational Diseases (revised 2010)" (international)
- **guideline_id (proposed):** `ILO-LIST-OCCUPATIONAL-DISEASES-2010`
- **Publishing body:** International Labour Office, Geneva · **Version:** revised 2010 (annex to
  Recommendation No. 194)
- **URL:** https://www.ilo.org/sites/default/files/wcmsp5/groups/public/@ed_protect/@protrav/@safework/documents/publication/wcms_125137.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (list headings):**
  > "1.2.1. Hearing impairment caused by noise"
  > "1.2.2. Diseases caused by vibration (disorders of muscles, tendons, bones, joints, peripheral
  > blood vessels or peripheral nerves)"
  > "2.1. Respiratory diseases" · "2.2. Skin diseases" · "2.3. Musculoskeletal disorders" ·
  > "2.4. Mental and behavioural disorders"
- **Confidence: HIGH** for text (primary PDF, extracted locally). A list of recognised diseases, not
  a history-taking guide; used only to corroborate the organ groups covered by Q5–Q14.

### IM-S3 — 6331 sayılı İş Sağlığı ve Güvenliği Kanunu, Madde 15 "Sağlık gözetimi" (Türkiye)
- **guideline_id (proposed):** `TR-KANUN-6331-MADDE-15` (law, not a clinical guideline)
- **Version / date:** Kabul 20/6/2012; RG 30/6/2012 sayı 28339; consolidated text including the
  9/1/2025 amendment (7538 sayılı Kanun md. 21)
- **URL:** https://www.mevzuat.gov.tr/MevzuatMetin/1.5.6331.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "1) İşe girişlerinde." · "2) İş değişikliğinde."
  > "Sağlık muayenesi yaptırılan çalışanın özel hayatı ve itibarının korunması açısından sağlık
  > bilgileri gizli tutulur."
- **Use:** frames the fitness-to-work visit types and supports the §0 hold line. No question is
  derived from it.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2a | Current health complaint (gate) | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q2 | Patient believes work is involved | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q3 | Better away from work | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Similar complaints in co-workers | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q5 | Dust / fume / gas / chemical exposure (yes/no) | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; **no exposure archetype in the OPT** |
| Q6 | Names of the agents (if Q5 yes) | no candidate archetype | — | deferred (INT-032) |
| Q7 | Noisy workplace (yes/no) | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q8 | Ringing ears / reduced hearing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Vibrating hand tools (yes/no) | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q10 | Finger whitening / numbness in the cold | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Heavy lifting / repetitive movement (yes/no) | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q12 | Cough / wheeze / breathlessness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q13 | Hand / forearm skin symptoms | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q14 | Excess workload or stress at work (psychosocial exposure) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q15–Q18 | Employer, protective equipment, work-related sick leave, tenure | no candidate archetype | — | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm sign | Source | base item | This proposal's role |
|---|---|---|---|
| Acute gas / fume inhalation, asphyxiant or carbon monoxide exposure now | IM-S1 ("saniyeler içinde ölüme neden olabilirler") | **absent** from base.life_threat | **Not asked.** Left to the base owner / physician |
| Breathlessness at rest | IM-S1 (occupational asthma symptoms) | `rf.dyspnoea_rest` | Q12 is history only; no "now at rest" item |
| Chest pain | — | `rf.chest_pain_*` | Not asked here |
| Work accident / acute trauma | — | not a branch concern | Not asked here |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Symptoms improve away from work (possible occupational asthma or dermatitis) | "Semptomlar işten uzaklaşmakla(tatil veya iş değişikliği) düzeliyor mu?" | IM-S1 |
| Several co-workers with the same complaint (cluster) | "İş arkadaşlarında da aynı maruziyetler aynı semptomlara neden oluyor mu?" | IM-S1 |
| Finger whitening with vibration exposure | "soğuk maruziyetiyle veya emosyonel stresle artar" | IM-S1 |
| Hearing loss or tinnitus with noise exposure | "Çoğu zaman kulak çınlaması da eşlik eder." | IM-S1, IM-S2 1.2.1 |

---

## 3. Candidate B1 Turkish pre-visit questions (19 drafted, all active)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE —
clinician to approve wording.** Own words throughout; the IM-S1 screening list is a source, not a
script. No item carries a triage level. Q1 binds to the pack's `basvuru_nedeni` slot; duration comes
from the pack's `sikayet_suresi` slot, whose fixed ask fits the symptom-driven visits this clinic
mostly sees (no sourced alternative exists for periodic examinations). Q1 ends in "nedir?" so the
generator's neutral follow-up is used, not the complaint follow-up. "Şu anki ya da önceki
işlerinizde" is used because relevant exposure can be lifetime (IM-S1 "geçmişte maruz kaldınız mı").
Work-history items are `text_first` under owner decision D3 (§0).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün iş ve meslek hastalıkları polikliniğine gelme nedeniniz nedir?"
CANDIDATE — clinician to approve wording.

**Q2a — Current health complaint (gate)** · archetype: `OBSERVATION.story.v1` · source: IM-S1 short list (asked of a worker with a health problem)
> "Şu anda sizi rahatsız eden bir sağlık şikâyetiniz var mı?"
gen: slot=guncel_saglik_sikayeti; type=boolean
CANDIDATE — clinician to approve wording. Report and screening visits (işe giriş, periyodik muayene)
may carry no complaint; Q2–Q4 read this gate. The owner may drop the gate if this clinic sees only
symptomatic referrals, and Q2–Q4 then lose their `ask_if`.

**Q2 — Patient's belief that work is involved (if Q2a yes)** · archetype: `OBSERVATION.story.v1` · source: IM-S1 (short list)
> "Şikâyetinizin yaptığınız işten kaynaklanıyor olabileceğini düşünüyor musunuz?"
gen: slot=isten_kaynaklandigi_dusuncesi; type=boolean; ask_if=guncel_saglik_sikayeti == true; delivery=text_first
CANDIDATE — clinician to approve wording. Records the patient's view only; never a work-relatedness
decision. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

**Q3 — Better away from work (if Q2a yes)** · archetype: `OBSERVATION.symptom_sign.v1` · source: IM-S1 (causal question; occupational-asthma advice to ask about holidays)
> "İşten uzak kaldığınız tatil günlerinde şikâyetleriniz azalıyor mu?"
gen: slot=tatilde_azalma; type=boolean; ask_if=guncel_saglik_sikayeti == true
CANDIDATE — clinician to approve wording. Symptom pattern, so `voice`.

**Q4 — Similar complaints in co-workers (if Q2a yes)** · archetype: `OBSERVATION.story.v1` · source: IM-S1 (causal question; short list)
> "İş arkadaşlarınızda da benzer şikâyetler var mı?"
gen: slot=is_arkadaslarinda_benzer_sikayet; type=boolean; ask_if=guncel_saglik_sikayeti == true; delivery=text_first
CANDIDATE — clinician to approve wording. No co-worker is identified. invariant 18: owner-approved
2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

**Q5 — Dust, fume, gas or chemical exposure** · archetype: `OBSERVATION.story.v1` · source: IM-S1 ("kimyasallar, tozlar, metaller"), IM-S2 (2.1, 2.2)
> "Şu anki ya da önceki işlerinizde toz, duman, gaz veya kimyasal maddeyle karşılaştınız mı?"
gen: slot=toz_kimyasal_maruziyeti; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Yes/no hazard class (§0). invariant 18: owner-approved
2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

**Q6 — Names of the agents (if Q5 yes)** · archetype: none · source: IM-S1 ("kimyasallar, tozlar, metaller")
> "Karşılaştığınız toz, duman, gaz ya da kimyasalların adlarını söyleyebilir misiniz?"
gen: slot=maruziyet_ayrintisi; type=string; ask_if=toz_kimyasal_maruziyeti == true; follow_up=Adlarını bilmiyorsanız nasıl maddeler olduğunu anlatır mısınız?; delivery=text_first
CANDIDATE — clinician to approve wording. Released under D3. The sector is no longer asked here: base
`occupation` and Q15 cover it, and the double object left one string slot holding either of two
facts. Free text can still name the employer. invariant 18: owner-approved 2026-09-26;
VERBİS/data-category register row pending counsel review (INT-349).

**Q7 — Noisy workplace** · archetype: `OBSERVATION.story.v1` · source: IM-S1 (Gürültü), IM-S2 (1.2.1)
> "Şu anki ya da önceki işlerinizde gürültülü bir ortamda çalıştınız mı?"
gen: slot=gurultulu_ortam; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. invariant 18: owner-approved 2026-09-26;
VERBİS/data-category register row pending counsel review (INT-349).

**Q8 — Ringing in the ears or reduced hearing** · archetype: `OBSERVATION.symptom_sign.v1` · source: IM-S1 ("kulak çınlaması, işitmenin azalması")
> "Kulaklarınızda çınlama ya da işitmenizde azalma fark ettiniz mi?"
gen: slot=cinlama_isitme_azalmasi; type=boolean
CANDIDATE — clinician to approve wording. Not gated on Q7; hearing loss has other work causes.
Hava ve uzay hekimliği Q5 shares this text and slot.

**Q9 — Vibrating hand tools** · archetype: `OBSERVATION.story.v1` · source: IM-S1 (el-kol titreşimi), IM-S2 (1.2.2)
> "Şu anki ya da önceki işlerinizde titreşen el aletleri kullandınız mı?"
gen: slot=titresimli_alet; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. invariant 18: owner-approved 2026-09-26;
VERBİS/data-category register row pending counsel review (INT-349).

**Q10 — Finger whitening or numbness in the cold (if Q9 yes)** · archetype: `OBSERVATION.symptom_sign.v1` · source: IM-S1 (vibration white finger; "uyuşma ve karıncalanma")
> "Soğukta parmaklarınızda beyazlaşma, uyuşma ya da karıncalanma oluyor mu?"
gen: slot=parmak_beyazlasma_uyusma; type=boolean; ask_if=titresimli_alet == true
CANDIDATE — clinician to approve wording.

**Q11 — Heavy lifting or repetitive movement** · archetype: `OBSERVATION.story.v1` · source: IM-S1 ("sık tekrarlanan hareketler"; Birikimsel travma, Tablo 1), IM-S2 (2.3)
> "Şimdiye kadar yaptığınız işler ağır yük ya da sık tekrarlanan hareket gerektirdi mi?"
gen: slot=agir_yuk_tekrarli_hareket; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Covers past work as well as the current job, like Q5, Q7 and
Q9, with one predicate. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row
pending counsel review (INT-349).

**Q12 — Cough, wheeze or breathlessness** · archetype: `OBSERVATION.symptom_sign.v1` · source: IM-S1 (occupational asthma symptoms), IM-S2 (2.1)
> "Öksürük, hırıltılı nefes ya da nefes darlığı yaşıyor musunuz?"
gen: slot=solunum_belirtileri; type=boolean
CANDIDATE — clinician to approve wording. History only; **overlap `rf.dyspnoea_rest` (§2.2)**.

**Q13 — Hand or forearm skin symptoms** · archetype: `OBSERVATION.symptom_sign.v1` · source: IM-S1 ("sıklıkla ellerde başlar ve önkola yayılır"; "Ciltte kızarıklık, kaşıntı, … lokal şişlik"), IM-S2 (2.2)
> "Ellerinizde ya da kollarınızda kaşıntı, kızarıklık ya da şişlik oluyor mu?"
gen: slot=el_kol_cilt_belirtileri; type=boolean
CANDIDATE — clinician to approve wording. Aligned with the IM-S1 quote; the clinician may add dryness
or cracking back with a source.

**Q14 — Excess workload or stress at work (psychosocial exposure)** · archetype: `OBSERVATION.symptom_sign.v1` · source: IM-S1 ("Aşırı iş yükü"), IM-S2 (2.4)
> "İşinizde aşırı iş yükü ya da stres yaşıyor musunuz?"
gen: slot=asiri_is_yuku_stres; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. An exposure item, like Q5, Q7, Q9 and Q11; not a scale item,
no score. Mood and burnout screening stay with the consented wellbeing module. invariant 18:
owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

**Q15 — Employer or workplace** · archetype: none · source: IM-S1 ("İşveren adı / Adres")
> "Hangi iş yerinde çalıştığınızı söyleyebilir misiniz?"
gen: slot=is_yeri; type=string; delivery=text_first
CANDIDATE — clinician to approve wording. Released under D3. IM-S3 confidentiality and the files/02
employer fear apply. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row
pending counsel review (INT-349).

**Q16 — Protective equipment at work (if Q5 or Q7 yes)** · archetype: none · source: IM-S1 ("İşyerinde kişisel koruyucu kullanıyor musunuz?")
> "İş yerinde maske, eldiven ya da kulak koruyucu kullanıyor musunuz?"
gen: slot=kisisel_koruyucu; type=boolean; ask_if=toz_kimyasal_maruziyeti == true || gurultulu_ortam == true; delivery=text_first
CANDIDATE — clinician to approve wording. Released under D3; gated on an exposure. The answer
describes the employer's practice as well as the patient's exposure. Polarity: `true` is the
protective answer, unlike the symptom slots; rule authors (HB-C) must read it that way. invariant 18:
owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

**Q17 — Sick leave for a work-related health problem** · archetype: none · source: IM-S1 ("rapor kullandınız mı, işten ayrıldınız mı")
> "İşle ilgili bir sağlık sorunu yüzünden daha önce rapor aldınız mı?"
gen: slot=isle_ilgili_rapor; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Released under D3, read as within "employer / occupational
exposure"; the owner narrows it if not. invariant 18: owner-approved 2026-09-26; VERBİS/data-category
register row pending counsel review (INT-349).

**Q18 — Time in the current job** · archetype: none · source: IM-S1 ("Bu işte çalışmaya ne zaman başladınız?")
> "Şu anki işinizde ne zamandır çalışıyorsunuz?"
gen: slot=is_suresi; type=duration; delivery=text_first
CANDIDATE — clinician to approve wording. Released under D3, read as within "employer / occupational
exposure"; the owner narrows it if not. Clinically useful for latency; `type=duration`, so no free
numeric entry. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending
counsel review (INT-349).

*(19 drafted, all active.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish clinical guideline** for occupational history-taking in a hospital clinic —
   IM-S1 is a 2012 diagnosis guide aimed at workplace physicians in three sectors. No Türk Toraks
   Derneği or İş ve Meslek Hastalıkları society guideline was retrieved. **NO SOURCE FOUND
   (versioned) — clinician must supply.**
2. **İşe giriş / periyodik muayene content** — IM-S3 names the visit types, but the Ministry's
   periodic-examination rules (Çalışanların Sağlık Gözetimi) were not retrieved. **NO SOURCE FOUND.**
3. **Data-category decisions (invariant 18)** — resolved by D3 (owner, 2026-09-26), except the
   INT-349 open items: per-item data-inventory rows, encrypted storage, counsel's per-category legal
   basis, retention, recipients and VERBİS entry, and slot tagging. All work-history items are
   `text_first` (§0). No inventory annotation exists yet for any of these fields.
4. **Latency and exposure-duration thresholds** (e.g., how long after starting a job symptoms
   appear) — present in IM-S1 as numbers; **not put into patient copy** (invariant 22); a clinician
   must decide whether a rule needs them.
5. **Psychosocial risk and mental-health items beyond workload** (ILO 2.4.1 post-traumatic stress) —
   not drafted. Clinician may add, with PolicyGuard review; mood and burnout screening stay with the
   consented wellbeing module.
6. **Occupational cancer and ionising-radiation history** (IM-S1 chapters; ILO 1.2.4, section 3) —
   not drafted to stay near twelve active items.
7. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. All three
   RED axes (route × register × location, invariant 21) are **deliberately unassigned**.
8. **openEHR leaf paths (at-codes)** and an **occupational-exposure archetype** — deferred
   (`openehr_deferred_reason`, INT-032); exposure items bind to `OBSERVATION.story.v1` as narrative.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE.
- **Inv. 7** — acute inhalation / asphyxiant exposure and breathlessness at rest left to
  `base.life_threat` and the physician (§2.2); nothing extends it.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 18** — employer and occupational-exposure items approved under D3 (2026-09-26): the five
  formerly held items (Q6, Q15–Q18) are released, and every work-history item (Q2, Q4, Q5, Q6, Q7,
  Q9, Q11, Q14, Q15–Q18) is `text_first`. Each needs its INT-349 row; storage, encryption, the
  counsel decisions and slot tagging stay open under INT-349.
- **Instruments** — Q14 is a psychosocial-exposure item, not the Maslach emotional-exhaustion item.
- **Inv. 21** — RED axes intentionally unspecified (gap 7).
- **Inv. 22** — no numerals in any candidate question; source numbers stay in §1 only.
- **Fitness-to-work** — history capture only; the report and any work-relatedness decision are the
  physician's.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources IM-S1…IM-S3 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
