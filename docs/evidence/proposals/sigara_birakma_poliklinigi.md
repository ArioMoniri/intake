# Sigara Bırakma Polikliniği (Smoking Cessation Clinic) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research agent (medical guideline researcher) · Date: 2026-09-26 · Specialty: Sigara Bırakma
polikliniği (tobacco-dependence treatment unit, adults)
Taxonomy id: `sigara_birakma_poliklinigi` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (smoking history and quit-attempt context for a
clinician-ready note) — **not** diagnosis, not triage authority, **not** a dependence test. This file is a
*proposal for a clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no**
clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL + verbatim
  text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must supply"**.
  Nothing was invented.
- **Turkish first:** the primary source is the **T.C. Sağlık Bakanlığı "Tütün Bağımlılığı İle Mücadele El Kitabı
  (Hekimler İçin)" (2010)**, a physician-facing Ministry handbook built on the 5A approach (SB-S1). It is
  supported by the Ministry's **ALO 171 Sigara Bırakma Danışma Hattı** site (SB-S2) and the TPD nicotine page
  (SB-S3). NICE NG209 (last updated February 2025) is the international corroboration. SB-S1 is dated 2010, so a
  current versioned Turkish clinical guideline is still a gap (§4 gap 1).
- **Non-judgemental by source.** SB-S1 instructs: "Bireye sigara içme durumunu sorarken yargılayıcı ve kınayıcı
  ifadelerden kaçınmaya çalışılmalıdır." Every question below follows that rule.
- **The Fagerström test stays in an instrument path.** SB-S1 (Tablo 4) and the ALO 171 "Ne kadar Bağımlıyım?"
  page both carry the Fagerström Nikotin Bağımlılık Ölçeği. Its items, including *cigarettes per day* and *time
  to first cigarette after waking*, are **not** reproduced or paraphrased here. The instrument is `UNKNOWN` in
  `packages/protocols/src/protocols/licences.py`, so it fails closed until a licence verdict and a Turkish
  validation are recorded. The ALO 171 "Bırakmaya hazır mıyım?" *kararlılık testi* is likewise not reproduced.
- **Invariant 22:** daily amount and pack-years are numeric. They need a structured `quantity` slot with
  `confirm_required` (the `base/intake.yaml` `weight_kg` pattern), never free patient text. Not drafted (§4 gap 3).
- **Already collected by `base/intake.yaml`:** `smoking_status`, `alcohol_use`, `pregnancy_status`, medications
  and allergies. They are not repeated.
- **Triage:** per invariant 1, only `packages/protocols/triage` rules produce RED/YELLOW. Nothing here assigns a
  level. §2.3 lists red-flag candidates **for physician review only — not encoded**.
- **Verification caveat (every quote in §1):** captured by automated retrieval (curl + `pdftotext`; NICE pages
  HTTP 200). Before sign-off each sentence MUST be re-checked against the primary text and committed as a
  verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule
  stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/sigara_birakma_poliklinigi.yaml` (L0) or any served
  pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### SB-S1 — T.C. Sağlık Bakanlığı, "Tütün Bağımlılığı İle Mücadele El Kitabı (Hekimler İçin)" (Türkiye)
- **guideline_id (proposed):** `TR-SB-TUTUN-ELKITABI-2010`
- **Publishing body:** T.C. Sağlık Bakanlığı Temel Sağlık Hizmetleri Genel Müdürlüğü · Sağlık Bakanlığı Yayın No: 796
- **Version / date:** 2010
- **URL:** https://havanikoru.saglik.gov.tr/depo/Dokumanlar/Yayinlar/Tutun_Bagimliligi_ile_Mucadele_El_Kitabi.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (products used in Türkiye):**
  > "Türkiye’de de en çok sigara olmak üzere, nargile, az miktarda puro ve pipo ile yerel olarak sarmalık türün
  > ve Maraş otu tüketilmektedir."
- **Verbatim (5A, "a. Değerlendir (Ask-Öğren/Sor)", p. 54):**
  > "Bireye sigara içme durumunu sorarken yargılayıcı ve kınayıcı ifadelerden kaçınmaya çalışılmalıdır."
  > "Sadece sigarayı da düşünmeyin “örneğin pipo, puro gibi herhangi bir tütün mamulü içtiniz mi ya da düzenli
  > olarak içtiniz mi?”"
  > "Günde kaç sigara içiyor? Ne zaman başlamış? Ne zaman bir paketin üzerine çıkmış? Bırakmayı denemiş mi? Ne
  > olmuş? Ailede içenler var mı? gibi."
- **Verbatim ("c. Derecelendir", pp. 56–58):**
  > "1.Bırakma isteğini sorun."
  > "Sigarayı neden bırakmak istiyorsunuz? sorusunu sorarak en önemli nedeni belirleyin."
- **Verbatim ("4. Geçmiş bırakma deneyimlerini değerlendirin", p. 60):**
  > "Daha önce sigarayı bırakma konusunda ciddi bir girişiminiz oldu mu?"
  > "neden bırakmayı denedikleri, hangi yöntemleri kullandıkları (birden kesme, giderek azaltma, farmakolojik
  > yardımcılar gibi), yardım yöntemleri ve neden nüks olduğu belirlenmelidir."
  > "Sigara içmeye teşvik eden tetikleyicileri ve yüksek riskli durumları nasıl anlayacağı ve nasıl kaçınacağı
  > hususunu açıklığa kavuşturulması."
- **Verbatim (bupropion contraindications, pp. 73–74, fragments):**
  > "konvulsiyon ve konvulsiyon eşiğini düşüren ilaç (alkol, nöroleptik) kullanımı veya MSS travması öyküsü veren
  > olgularda"
  > "anoreksi ya da bulumia gibi yeme bozuklukları ve MAO inhibitörü kullanma öyküsü olanlarda"
  > "bipolar hastalığı olanlarda"
- **Verbatim (varenicline and all quit attempts, p. 76):**
  > "ilacın prospektüsüne vareniklinin nöropsikiyatrik semptomları arttırabileceği, ajitasyon, depresif durum,
  > intihar eğilimi ve varolan psikiyatrik durumun kötüleşebileceği bilgileri eklenmiştir."
  > "İlaç kullansın kullanmasın bütün sigara bırakma girişiminde bulunan olgular hekimi ve yakınları tarafından
  > bu tür semptomların ve duygulanım farklılıkların oluşumu açısından yakından gözlenmelidir."
- **Table cells (table "Farmakolojik Tedavi Seçenekleri", column "Kontrendike olduğu durumlar", p. 79; the
  product row each cell belongs to was lost in text extraction and must be re-checked on the page):**
  > "Miyokard infarktüsü" · "Stabil olmayan anjina" · "Ağır kardiyak aritmi"
- **Not reproduced:** Tablo 4 (Fagerström) items and scoring.
- **Confidence: HIGH** for the text (primary Ministry PDF); **MEDIUM for currency** (2010; drug content predates
  later label changes and cytisinicline).

### SB-S2 — T.C. Sağlık Bakanlığı, ALO 171 Sigara Bırakma Danışma Hattı (Türkiye)
- **guideline_id (proposed):** `TR-SB-ALO171` (public service pages, **not** a clinical guideline)
- **URLs:** https://alo171.saglik.gov.tr/TR-66747/daha-once-denedim.html (page date 10 Ekim 2020) ·
  https://alo171.saglik.gov.tr/TR-66752/nasil-destek-alabilirim-.html (21 Haziran 2023) ·
  https://alo171.saglik.gov.tr/TR-74780/ne-kadar-bagimliyim-.html (Fagerström-form test; not reproduced)
- **Verbatim ("Daha önce denedim"):**
  > "Her sigarayı bırakma deneyiminiz, bir sonraki bırakma girişiminiz için yol gösterici olabilir."
  > "Siz içmeme konusundaki kararlılığınızı sürdürürseniz hatırlatıcı çevresel unsurlar (yemek sonrası, cay,
  > kahve, vs) ile sigara arasındaki güçlenmiş bağ zayıflayacaktır."
- **Verbatim ("Nasıl destek alabilirim?"):**
  > "Size en yakın Sigara Bırakma Polikliniği’ni ziyaret edebilirsiniz."
- **Confidence: MEDIUM** (Ministry lay pages; cite for patient-facing framing only).

### SB-S3 — TPD halka yönelik, "Nikotin (Sigara) bağımlılığı" (Türkiye, lay page)
- **guideline_id (proposed):** `TPD-HALK-NIKOTIN` · **Date:** not shown
- **URL:** https://psikiyatri.org.tr/halka-yonelik/46/nikotin-sigara-bagimliligi
- **Verbatim:**
  > "Ulaşılma kolaylığı, fiyatı, evde sigara kullananların, özellikle bağımlıların bulunması, yaşam olayları ve
  > stres etkenleri kullanmayı artıran başlıca etkenlerdir."
  > "Sigara içenlerde psikiyatrik bozukluklar toplum geneline göre daha yaygındır."
  > "Sigara ve tütün kullanımı olanlar hayatlarında birkaç kez bırakma girişiminde bulunmuş olabilirler."
  > "Kilo alacağı endişesi: Sigara ve tütün ürünlerinin bırakılmasıyla mutlaka kilo alınmaz."
- **Confidence: MEDIUM** (society lay page, undated).

### SB-S4 — NICE NG209, "Tobacco: preventing uptake, promoting quitting and treating dependence" (international)
- **guideline_id (proposed):** `NICE-NG209` · **Published:** 30 November 2021 · **Last updated:** 4 February 2025
- **URL:** https://www.nice.org.uk/guidance/ng209/chapter/Treating-tobacco-dependence (HTTP 200)
- **Verbatim:**
  > 1.11.1 "At every opportunity, ask people if they smoke or have recently stopped smoking."
  > 1.11.3 "Discuss any stop-smoking aids the person has used before, including personally purchased
  > nicotine-containing products."
  > 1.11.5 "find out about the person's smoking behaviour and level of nicotine dependence by asking how many
  > cigarettes they smoke – and how soon after waking"
  > 1.11.8 "At the earliest opportunity, ask if any of the following people smoke:" … "anyone else in the
  > household."
  > 1.12.7 "their preferences, health and social circumstances" · "any medicines they are taking" · "any
  > contraindications and the potential for adverse effects" · "their previous experience of stop-smoking aids."
- **Note:** NG209's e-cigarette advice rests on UK regulation (MHRA / TRPR 2016) and does not transfer to
  Türkiye; only the history-taking items are used.

### SB-S5 — NICE NG12, "Suspected cancer: recognition and referral" (international) — for §2.3 only
- **guideline_id (proposed):** `NICE-NG12` · **Published:** 23 June 2015 · **Last updated:** 15 April 2026
- **URL:** https://www.nice.org.uk/guidance/ng12/chapter/Recommendations-organised-by-site-of-cancer (HTTP 200)
- **Verbatim:**
  > 1.1.1 "are aged 40 and over with unexplained haemoptysis."
  > 1.1.2 "Offer an urgent, direct access chest X‑ray to assess for lung cancer in people aged 40 and over if they
  > have 2 or more of the following unexplained symptoms, or if they have ever smoked and have 1 or more of the
  > following unexplained symptoms:" (cough, fatigue, shortness of breath, chest pain, weight loss, appetite loss)
- **Confidence: HIGH** (primary page); UK referral thresholds, not a Turkish source.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032), never invented. **The OPT has no
tobacco / social-history root** (same posture as `base/intake.yaml` `smoking_status`), so smoking-history items
bind to `OBSERVATION.story.v1` as narrative only.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Other tobacco / nicotine products | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no tobacco root |
| Q3 | Blood in sputum (gate input) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Previous serious quit attempt | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | What made quitting hard | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Stop-smoking aids used before | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q7 | Main reason for quitting | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q8 | Readiness to quit | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Triggers / high-risk situations | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Smoker in the household | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no social-history root |
| Q11 | Prior mental-health care | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q12 | Seizure history | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm | Source | base.life_threat item | This proposal's role |
|---|---|---|---|
| Suicidal thoughts during a quit attempt | SB-S1 (p. 76, "intihar eğilimi") | `rf.crisis_disclosure_signposting` (`draft_needs_source`; HB-C17) | No question drafted |
| Chest pain in a smoker | SB-S5 1.1.2 (chest pain listed); SB-S1 NRT table (MI, unstable angina) | `rf.chest_pain_cardiac_features` / `rf.chest_pain_no_cardiac_history` | Not drafted; base covers acute chest pain |

### 2.3 Red-flag candidates — for physician review, not encoded

| Candidate | Source (verbatim in §1) | Notes |
|---|---|---|
| Unexplained haemoptysis, age forty or over | SB-S5 1.1.1 | Q3 is a gate input only; UK age threshold not pinned |
| Ever smoked plus unexplained cough, fatigue, breathlessness, chest pain, weight loss or appetite loss | SB-S5 1.1.2 | not drafted; overlaps göğüs hastalıkları pack |
| New agitation, low mood or suicidal thoughts during a quit attempt | SB-S1 p. 76 | crisis part is base.life_threat only |
| Recent myocardial infarction, unstable angina, severe arrhythmia | SB-S1 NRT table | pharmacotherapy safety; column attribution to re-check |
| Seizure history, CNS trauma, eating disorder, MAOI use, bipolar illness | SB-S1 pp. 73–74 | bupropion contraindications; Q12 and Q11 are history inputs only |
| Pregnancy or breastfeeding | SB-S1 (NRT and bupropion text) | already asked by `base/intake.yaml` `pregnancy_status` |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
non-judgemental (SB-S1); no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE
— clinician to approve wording.** No item carries a triage level. Only Q3 is an alarm item, and it may at most
feed a `candidate_flag` (max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. No item is a
Fagerström item or paraphrase. Q1 binds to the pack's `basvuru_nedeni` slot.

**Duration ask override pending clinician wording.** The generator's fixed `sikayet_suresi` question ("Bu
şikâyetiniz ne zamandır var?") does not fit this clinic: it invites a number of smoking years (gap 6,
invariant 22). The verification report gives no replacement text, so no pack-level duration override is set
here; a clinician must supply the branch-appropriate wording.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün sigara bırakma polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Other tobacco or nicotine products** · archetype: `OBSERVATION.story.v1` (narrative only) · source: SB-S1 (nargile, puro, pipo, sarmalık; "herhangi bir tütün mamulü"), SB-S4 1.11.3 (nicotine-containing products)
> "Sigara dışında nargile, sarma tütün ya da elektronik sigara gibi bir ürün kullanıyor musunuz?"
gen: slot=diger_tutun_nikotin_urunu; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Blood in sputum (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: SB-S5 1.1.1 ("unexplained haemoptysis")
> "Son zamanlarda balgamınızda kan gördüğünüz ya da kan tükürdüğünüz oldu mu?"
gen: slot=balgamda_kan; type=boolean
CANDIDATE — clinician to approve wording. Same text and slot as `gogus_hastaliklari.md` Q5 (one audio clip);
it now also covers spitting blood. May at most feed a `candidate_flag` (max `YELLOW_REVIEW`) pending
clinician + rules engine; the source's age threshold is **not** pinned into patient copy. No level asserted.

**Q4 — Previous serious quit attempt** · archetype: `OBSERVATION.story.v1` · source: SB-S1 ("Daha önce sigarayı bırakma konusunda ciddi bir girişiminiz oldu mu?"), SB-S3
> "Daha önce sigarayı bırakmak için ciddi bir girişiminiz oldu mu?"
gen: slot=onceki_birakma_girisimi; type=boolean
CANDIDATE — clinician to approve wording. Almost word for word the Ministry handbook's question (SB-S1); a
short functional question, so the IP risk is low. Gate for Q5.

**Q5 — What made quitting hard** · archetype: `OBSERVATION.story.v1` · source: SB-S1 ("neden nüks olduğu belirlenmelidir"), SB-S2 ("yol gösterici olabilir")
> "Bırakmayı denediğinizde sizi en çok zorlayan şey neydi?"
gen: slot=birakmayi_zorlastiran; type=string; ask_if=onceki_birakma_girisimi == true
CANDIDATE — clinician to approve wording. Asked only when Q4 is yes, so the "if you tried" lead-in is dropped.

**Q6 — Stop-smoking aids used before** · archetype: `ACTION.medication.v1` · source: SB-S1 ("farmakolojik yardımcılar"), SB-S4 1.11.3 and 1.12.7 (previous experience of stop-smoking aids)
> "Bırakmak için daha önce ilaç, nikotin bandı ya da sakız kullandınız mı?"
gen: slot=onceki_birakma_yardimcisi; type=boolean
CANDIDATE — clinician to approve wording. History only; names products, recommends none.

**Q7 — Main reason for quitting** · archetype: `EVALUATION.reason_for_encounter.v1` · source: SB-S1 ("Sigarayı neden bırakmak istiyorsunuz? … en önemli nedeni belirleyin.")
> "Sigarayı bırakmak istemenizin en önemli nedeni nedir?"
gen: slot=birakma_nedeni; type=string
CANDIDATE — clinician to approve wording.

**Q8 — Readiness to quit** · archetype: `OBSERVATION.story.v1` · source: SB-S1 ("1.Bırakma isteğini sorun."), SB-S4 1.12.7 (preferences)
> "Sigarayı bırakmaya kendinizi ne kadar hazır hissediyorsunuz?"
gen: slot=birakmaya_hazirlik; type=string
CANDIDATE — clinician to approve wording. Open wording; not the ALO 171 *kararlılık testi*. The answer may be
a number; that is acceptable in a string slot because it is not a clinical quantity. A choices list would be
cleaner, but the generator has no `choices_tr`.

**Q9 — Triggers and high-risk situations** · archetype: `OBSERVATION.story.v1` · source: SB-S1 ("tetikleyicileri ve yüksek riskli durumları"), SB-S2 ("yemek sonrası, cay, kahve"), SB-S3 ("yaşam olayları ve stres etkenleri")
> "Hangi durumlarda sigara içme isteğiniz artıyor?"
gen: slot=sigara_istegini_artiran_durumlar; type=string
CANDIDATE — clinician to approve wording.

**Q10 — Smoker in the household** · archetype: `OBSERVATION.story.v1` (narrative only) · source: SB-S1 ("Ailede içenler var mı?"), SB-S3 ("evde sigara kullananların"), SB-S4 1.11.8 ("anyone else in the household.")
> "Evde sizinle birlikte yaşayan ve sigara içen biri var mı?"
gen: slot=evde_sigara_icen; type=boolean
CANDIDATE — clinician to approve wording.

**Q11 — Prior mental-health care** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SB-S1 (bupropion: "bipolar hastalığı olanlarda"; varenicline p. 76), SB-S3 ("psikiyatrik bozukluklar … daha yaygındır"), SB-S4 1.12.7 (contraindications)
> "Daha önce ruh sağlığınızla ilgili bir hekimden destek aldınız mı?"
gen: slot=onceki_ruh_sagligi_hekim_destegi; type=boolean
CANDIDATE — clinician to approve wording. Pharmacotherapy-safety context for the physician; not a screen. A
different slot id from ruh Q8, because this item leaves out psychologists.

**Q12 — Seizure history** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SB-S1 (bupropion: "konvulsiyon … öyküsü veren olgularda")
> "Daha önce hiç nöbet ya da havale geçirdiniz mi?"
gen: slot=nobet_oykusu; type=boolean
CANDIDATE — clinician to approve wording. Pharmacotherapy-safety history; not a flag by itself.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Current versioned Turkish clinical guideline for tobacco-dependence treatment**: SB-S1 is from 2010. The
   Türk Toraks Derneği 2025 PDF found by search (toraks.org.tr, "Tütün Ürünleri ve Nikotin Bağımlılığında…") and
   its older "Sigara Bırakma Tanı ve Tedavi" PDF both returned **HTTP 404**. **NO SOURCE FOUND (current
   versioned) — clinician must supply.**
2. **Fagerström test** — licence `UNKNOWN` in the registry (fail-closed), Turkish validation not recorded; items
   not reproduced. Owner (licensing) + clinician (validation), HB-L24 posture.
3. **Daily amount and pack-years** — numeric; needs a structured `quantity` slot with `confirm_required`
   (invariant 22), not free text. Also an FTND item (gap 2). Not drafted.
4. **Tobacco / social-history archetype** — absent from the OPT; Q2 and Q10 are narrative-only (INT-032).
5. **Cytisinicline and current drug labels** — SB-S1 predates them. SB-S4 lists cytisinicline, but no Turkish
   licensing status was retrieved. Nothing here names a drug to take.
6. **When smoking began, and worry about weight gain** — sourced (SB-S1 "Ne zaman başlamış?"; SB-S3 "Kilo
   alacağı endişesi") but not drafted. The start question overlaps the generator's automatic `sikayet_suresi`
   slot and invites a free numeric answer (invariant 22), so it belongs with the structured pack-years slot
   (gap 3). Clinician may swap weight-gain worry in. Duration ask override pending clinician wording (§3).
7. **Adolescent smoking-cessation clinics** — seen only in a news report (not a primary source; not used).
   Minors are out of scope here (HB-L20).
8. **WHO 2024 clinical treatment guideline for tobacco cessation**: retrieval was not attempted, because WHO
   IRIS returned a JavaScript page instead of a PDF for another WHO document in this session. **NO SOURCE FOUND
   (verbatim).**
9. **EK-4 acuity** — no snapshot; **no level proposed**; RED axes (invariant 21) unassigned.
10. **openEHR leaf paths (at-codes)** — deferred (INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1**: no RED/YELLOW asserted; Q3 may at most feed a `candidate_flag` (max `YELLOW_REVIEW`); §2.3 is a
  review list only.
- **Inv. 2 / patient copy**: `siz`, B1, one question mark per turn, non-judgemental, no
  diagnosis/treatment/prognosis wording; Q6 names past aids as history and recommends nothing.
- **Inv. 7**: crisis and acute chest pain left to `base.life_threat`; nothing extended.
- **Inv. 10 / instrument fidelity**: no Fagerström or *kararlılık testi* item reproduced or paraphrased.
- **Inv. 22**: no numerals in any candidate question; numeric smoking quantities deferred to a structured slot.
- **Clinical content rule**: sources SB-S1…SB-S5 are candidates; rules stay `status: draft_needs_source` until
  verbatim snapshots are committed.
- **HB-C1**: awaits clinician sign-off; NOT served.
