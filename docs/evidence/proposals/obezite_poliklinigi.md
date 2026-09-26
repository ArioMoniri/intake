# Obezite Polikliniği (Obesity Clinic) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research agent (medical guideline researcher) · Date: 2026-09-26 · Specialty: Obezite polikliniği
(adult weight-management clinic)
Taxonomy id: `obezite_poliklinigi` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (weight history, eating pattern, sleep and readiness
context for a clinician-ready note) — **not** diagnosis, not triage authority, **not** an eating or sleep
questionnaire. This file is a *proposal for a clinician to sign off*. It assigns **no** authoritative
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL + verbatim
  text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must supply"**.
  Nothing was invented.
- **Turkish first, and versioned:** the primary source is the **TEMD Obezite Tanı ve Tedavi Kılavuzu 2024**
  (11. Baskı, Kasım 2024), whose §5.4 *Obeziteli bireylerde anamnez özellikleri* and Tablo 1 are close to a
  ready-made intake list (O-S1). The TPD eating-disorder lay page (O-S2) adds the purging safety context. NICE
  NG246 (January 2025, updated January 2026) is the international corroboration (O-S3).
- **Non-stigmatising by source.** TEMD asks clinicians to assess "yargılayıcı tutum takınmadan" and NG246 asks
  for non-stigmatising language and for permission before discussing weight (1.9.2). So Q1 does not use the word
  *obezite*, no question names a condition, and the clinician decides whether the flow should open with an
  explicit permission question (§4 gap 8).
- **Instruments stay out.** Epworth, Pittsburgh, STOP-Bang, Berlin, the *Yeme Tutum Testi*, Edmonton staging and
  TEMD Tablo 3's motivation staging item are **not** reproduced or paraphrased. Each is `UNKNOWN` in
  `packages/protocols/src/protocols/licences.py` and fails closed. **Depression screening** that TEMD requires
  belongs to the licensed PHQ-9 path (INT-116), not to this pack. ⚠️ TEMD states that PHQ-9 is "Türkçe
  geçerliliği test edilmiş ve onaylanmış". **The repo's recorded position differs** (PHQ-9 Turkish evidence is a
  reliability study only, HB-L24), so that claim is **not adopted** here.
- **Invariant 22:** weight, height, waist and BMI are measured or structured values (`base/intake.yaml`
  `weight_kg` has `confirm_required`). No question asks for a number.
- **Already collected by `base/intake.yaml`:** medications, allergies, smoking, alcohol, pregnancy status and the
  optional weight. They are not repeated.
- **Triage:** per invariant 1, only `packages/protocols/triage` rules produce RED/YELLOW. Nothing here assigns a
  level. §2.3 lists red-flag candidates **for physician review only — not encoded**.
- **Verification caveat (every quote in §1):** captured by automated retrieval (curl + `pdftotext`; NICE pages
  HTTP 200). Before sign-off each sentence MUST be re-checked against the primary text and committed as a
  verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule
  stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/obezite_poliklinigi.yaml` (L0) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### O-S1 — TEMD, "Obezite Tanı ve Tedavi Kılavuzu 2024" (Türkiye)
- **guideline_id (proposed):** `TEMD-OBEZITE-2024`
- **Publishing body:** Türkiye Endokrinoloji ve Metabolizma Derneği — Obezite, Lipid Metabolizması,
  Hipertansiyon Çalışma Grubu
- **Version / date:** 11. Baskı (çevrim içi), Kasım 2024
- **URL:** https://file.temd.org.tr/Uploads/publications/guides/documents/obezitetanitedavikilavizu-2024.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (approach, §5.1, p. 49):**
  > "sağlık çalışanlarının obezitenin karmaşık ve çok faktörlü patogenezinin farkında olması, yargılayıcı tutum
  > takınmadan, hastalarının motivasyonlarını iyi değerlendirmesi ve her hastayı bireysel olarak ve uygun
  > biçimde değerlendirmesi gereklidir."
  > "Hastanın tıbbi, psikolojik ve sosyokültürel durumu; komorbid hastalıkları ve kilo artışına neden olabilecek
  > ilaçları sorgulanmalıdır."
- **Verbatim (Tablo 1, "Obezite hastasında değerlendirilmesi gerekli faktörler", p. 51 — list items):**
  > "Obezite öyküsü, çocukluk, gençlik, evlilik öncesi ve sonrası, doğum sonrası ağırlıkları"
  > "Yeme bozuklukları" · "Uyku düzeni" · "Kilo artışına sebep olabilecek ilaçlar (Bkz. Tablo 2)"
  > "Obezitesi/kilo fazlalığı olan aile bireyleri"
  > "Gıdaları kimin seçtiği ve alışverişi kimin yaptığı, yemeğini kimin pişirdiği vb."
  > "Yaşam ortamı, kimlerle birlikte yaşadığı, yemeğini evde mi, dışarıda mı yediği"
  > "Egzersiz alışkanlığı (egzersiz süresi, şiddeti ve sıklığı)"
- **Verbatim (Beslenme öyküsü, p. 51):**
  > "Hastanın daha önceki kilo verme girişimleri sorgulanmalıdır."
  > "zayıflama konusunda başarılı olup olamadığı ve başarısızlığına neden olan sebepler not edilmelidir."
- **Verbatim (Yeme davranışı bozuklukları, pp. 52–53):**
  > "Obezite hastalarında çok sık gözlenen yeme davranış bozuklukları sorgulanmalı ve saptandığında mutlaka
  > tedavi edilmelidir."
  > "Tıkanırcasına yeme bozukluğu hastaları genellikle bu aşırı yeme atakları sonrasında kendini kaybedebilir,
  > utanç ve suçluluk duyarlar."
  > "Bulimia nervoza ise tıkanırcasına yeme atakları ve bunları takip eden kendini kusturma, laksatif kullanımı,
  > diüretik kullanımı, fazladan egzersiz yapma, aç kalma veya çok sıkı diyet yapma gibi davranış döngüleri ile
  > seyreder."
  > "Gece yeme sendromu hastalarında ise yemek yeme arzusu ile uykudan uyanma ve bir şeyler yemeden tekrar
  > uyuyamama atakları tipiktir"
- **Verbatim (Uyku bozuklukları, p. 53):**
  > "Obeziteli bireylere sorulabilecek yatma zamanı, kalkma zamanı, yatakta geçirilen süre, gece horlamalarının
  > olup olmadığı, gün içi uykusuzluk çekip çekmediği gibi temel birkaç soru ile hastalar uyku bozuklukları
  > açısından rahatça sorgulanabilmektedir."
- **Verbatim (sleep and OSAS, §4.10–4.11 p. 34; §5.7 p. 55):**
  > "Belirtiler; gürültülü horlama, tanıklı apne, boğulma hissi ile uyanma, gündüz aşırı uyku hali, sabahları
  > baş ağrısı, konsantrasyon güçlüğü ve yaşam kalitesinde azalmadır."
  > "Ayrıca hastanın horlama ve apne süreçleri özellikle birlikte yaşadığı kişilere sorulabilir."
  > "gündüz uyku haline bağlı çeşitli kazalara yol açabilmesi nedeniyle tanı ve tedavisi oldukça önemlidir."
- **Verbatim (Fiziksel aktivite sorgulaması, p. 53):**
  > "düzenli egzersiz yapıp yapmadığı" · "kas-iskelet sistemi, kalp-akciğer rahatsızlıkları veya spor yapmasını
  > diğer kısıtlayıcı hastalıklarının olup olmadığı sorgulanmalıdır."
- **Verbatim (Motivasyon, §5.8 p. 56):**
  > "Bu aşamalardan sonra son olarak hastanın obezite ile mücadeleye ne derece hazır olduğu sorgulanmalıdır."
- **Verbatim (endocrine causes, §2 p. 13, and Tablo 1 items there):**
  > "Nispeten nadir görülse de obeziteli bireyler değerlendirilirken endokrin hastalıklar sorgulanmalı, gerekirse
  > biyokimyasal testlerle araştırılmalıdır."
  > "Cushing sendromu/hastalığı" · "Ciddi hipotiroidizm" · "Hipogonadizm" · "Polikistik over sendromu"
- **Verbatim (Tablo 2 of the pharmacotherapy chapter, p. 95, GLP-1RA rows, column "Uyarı / Monitorizasyon"):**
  > "Akut pankreatit"
- **Not reproduced:** Tablo 3 (motivation staging, which contains numerals), the kilo-aldıran drug list in
  detail, and any scale.
- **Confidence: HIGH** (primary society PDF, versioned, dated). Page numbers are the printed ones.

### O-S2 — TPD halka yönelik, "Yeme Bozuklukları" (Türkiye, lay page)
- **guideline_id (proposed):** `TPD-HALK-YEME` · **Date:** not shown
- **URL:** https://psikiyatri.org.tr/halka-yonelik/32/yeme-bozukluklari
- **Verbatim:**
  > "Bu değişiklikler, açlık durumu veya çıkarma davranışlarına bağlıdır ve geri dönüşümlüdür."
  > "Çıkarma davranışları sonucu düşük potasyum düzeyleri gelişir. Bu durumda kalple ilgili sorunlar çıkabilir."
- **Confidence: MEDIUM** (society lay page, undated). Used for §2.3 safety context only.

### O-S3 — NICE NG246, "Overweight and obesity management" (international)
- **guideline_id (proposed):** `NICE-NG246` · **Published:** 14 January 2025 · **Last updated:** 8 January 2026
- **URL:** https://www.nice.org.uk/guidance/ng246/chapter/General-principles-of-care (HTTP 200) ·
  https://www.nice.org.uk/guidance/ng246/chapter/Identifying-and-assessing-overweight-obesity-and-central-adiposity
- **Verbatim (1.1.1 list items):**
  > "weight history and previous experiences of managing overweight or obesity"
  > "practicality of addressing weight and readiness to engage with change"
  > "how any medicines the person is taking may affect their weight or appetite"
  > "current or previous experiences of eating disorders or disordered eating"
  > "experiences of weight stigma"
- **Verbatim (1.1.2 list item):** > "that people can be affected by an eating disorder at any weight"
- **Verbatim (1.1.5, language):** > "using non-stigmatising language (for example, 'living with overweight')"
- **Verbatim (1.9.2):** > "Ask for permission each time before discussing overweight, obesity or central
  adiposity and before taking measurements."

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032), never invented. The OPT has **no
body-weight / anthropometry root** and **no social-history root**, so measurements are not bound here and
lifestyle items are narrative only.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Life period when weight gain began | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Previous weight-loss attempts | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | What made those attempts hard | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Where meals are mostly eaten | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no social-history root |
| Q6 | Loss-of-control eating | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Self-induced vomiting after eating | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Witnessed pauses in breathing during sleep | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Falling asleep unintentionally in the daytime | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | New medicine when weight gain began | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q11 | Regular walking or exercise | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no social-history root |
| Q12 | Readiness to change habits | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm | Source | base.life_threat item | This proposal's role |
|---|---|---|---|
| Severe abdominal pain on GLP-1RA treatment (possible pancreatitis) | O-S1 Tablo 2 ("Akut pankreatit") | no specific rule; general acute-abdomen handling outside this pack | Not drafted; §2.3 |
| Low potassium with cardiac effects after purging | O-S2 | **absent** from base.life_threat | Q7 is a history input only |
| Self-harm statements in the context of eating or mood | base only | `rf.crisis_disclosure_signposting` (`draft_needs_source`; HB-C17) | No question drafted |

### 2.3 Red-flag candidates — for physician review, not encoded

| Candidate | Source (verbatim in §1) | Notes |
|---|---|---|
| Daytime sleepiness with a risk of accidents (for example while driving) | O-S1 §5.7 ("çeşitli kazalara yol açabilmesi") | Q9 is a history input; route unassigned |
| Witnessed apnoea / waking with a choking feeling | O-S1 §4.11 | Q8 is a history input |
| Purging (self-induced vomiting, laxatives, diuretics) | O-S1 (bulimia sentence); O-S2 (potassium, cardiac) | Q7 covers vomiting only (§4 gap 4) |
| Eating disorder at any weight | O-S3 1.1.2 | clinician review; no screen here |
| Features of an endocrine cause (e.g. Cushing, severe hypothyroidism) | O-S1 §2 Tablo 1 | work-up question, not triage |
| Severe abdominal pain on GLP-1RA | O-S1 Tablo 2 | overlaps gastroenteroloji / genel cerrahi |
| Rapid weight gain with swelling or breathlessness (possible fluid) | **NO SOURCE FOUND** | clinician must supply |
| Complications after bariatric surgery (persistent vomiting, dumping) | O-S1 mentions dumping for BPD-DS only; no alarm list | **NO SOURCE FOUND (alarm list)** |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
non-stigmatising and non-judgemental (O-S1 §5.1, O-S3 1.1.5); no diagnosis/treatment/prognosis language; no
numerals (invariant 22). **All CANDIDATE — clinician to approve wording.** No item carries a triage level or
raises a `candidate_flag`, and no item is an item of any sleep, eating or motivation scale. Q1 binds to the pack's
`basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake; O-S3 1.1.5 (non-stigmatising language)
> "Bugün bu polikliniğe gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording. The clinic name is deliberately not spoken.

**Q2 — Life period when weight gain began** · archetype: `OBSERVATION.story.v1` · source: O-S1 Tablo 1 ("Obezite öyküsü, çocukluk, gençlik, evlilik öncesi ve sonrası, doğum sonrası ağırlıkları"), O-S3 1.1.1 (weight history)
> "Kilo almaya hayatınızın hangi döneminde başladınız?"
CANDIDATE — clinician to approve wording.

**Q3 — Previous weight-loss attempts** · archetype: `OBSERVATION.story.v1` · source: O-S1 ("Hastanın daha önceki kilo verme girişimleri sorgulanmalıdır."), O-S3 1.1.1
> "Daha önce kilo vermek için neler denediniz?"
CANDIDATE — clinician to approve wording.

**Q4 — What made those attempts hard** · archetype: `OBSERVATION.story.v1` · source: O-S1 ("başarısızlığına neden olan sebepler not edilmelidir")
> "Bu denemelerde sizi en çok zorlayan şey neydi?"
CANDIDATE — clinician to approve wording. Neutral framing; avoids the word *başarısızlık*. Depends on Q3, so
it needs an `ask_if` on Q3 when the pack is built (the generator's default `soru_N` slots carry none).

**Q5 — Where meals are mostly eaten** · archetype: `OBSERVATION.story.v1` (narrative only) · source: O-S1 Tablo 1 ("yemeğini evde mi, dışarıda mı yediği"; Beslenme öyküsü, eating places)
> "Öğünlerinizi çoğunlukla nerede yiyorsunuz?"
CANDIDATE — clinician to approve wording. Open wording, so the answer is not forced into an either/or.

**Q6 — Loss-of-control eating** · archetype: `OBSERVATION.symptom_sign.v1` · source: O-S1 (tıkanırcasına yeme: "kendini kaybedebilir"), O-S3 1.1.1 (disordered eating)
> "Kendinizi durduramıyormuş gibi hissederek kısa sürede çok fazla yediğiniz olur mu?"
CANDIDATE — clinician to approve wording. Original wording; not an item of any eating-behaviour scale.

**Q7 — Self-induced vomiting after eating** · archetype: `OBSERVATION.symptom_sign.v1` · source: O-S1 (bulimia: "kendini kusturma"), O-S2, O-S3 1.1.2
> "Yediklerinizi çıkarmak için kendinizi kusturduğunuz oldu mu?"
CANDIDATE — clinician to approve wording. **Sensitive:** the clinician may prefer to ask it in person (§4 gap 4).

**Q8 — Witnessed pauses in breathing during sleep** · archetype: `OBSERVATION.symptom_sign.v1` · source: O-S1 §4.11 ("tanıklı apne"; "birlikte yaşadığı kişilere sorulabilir")
> "Uyurken nefesinizin durduğunu fark eden biri oldu mu?"
CANDIDATE — clinician to approve wording.

**Q9 — Falling asleep unintentionally in the daytime** · archetype: `OBSERVATION.symptom_sign.v1` · source: O-S1 ("gündüz aşırı uyku hali"; "gün içi uykusuzluk çekip çekmediği"; §5.7 accidents)
> "Gün içinde istemeden uyuyakaldığınız oluyor mu?"
CANDIDATE — clinician to approve wording.

**Q10 — New medicine when weight gain began** · archetype: `ACTION.medication.v1` · source: O-S1 (§5.1 "kilo artışına neden olabilecek ilaçları sorgulanmalıdır"; Tablo 1), O-S3 1.1.1 (medicines and weight)
> "Kilo almaya başladığınız dönemde yeni bir ilaç kullanmaya başladınız mı?"
CANDIDATE — clinician to approve wording. The current medication list is confirmed by `base/intake.yaml`.

**Q11 — Regular walking or exercise** · archetype: `OBSERVATION.story.v1` (narrative only) · source: O-S1 ("düzenli egzersiz yapıp yapmadığı"; Tablo 1 "Egzersiz alışkanlığı")
> "Düzenli olarak yürüyüş ya da egzersiz yapıyor musunuz?"
CANDIDATE — clinician to approve wording.

**Q12 — Readiness to change habits** · archetype: `OBSERVATION.story.v1` · source: O-S1 §5.8 ("ne derece hazır olduğu sorgulanmalıdır"), O-S3 1.1.1 (readiness to engage with change)
> "Yaşam alışkanlıklarınızı değiştirmeye kendinizi ne kadar hazır hissediyorsunuz?"
CANDIDATE — clinician to approve wording. Open wording; not TEMD Tablo 3's staging item.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **T.C. Sağlık Bakanlığı obesity protocol** (e.g. the national obesity programme or an obesity-centre
   standard) — not retrieved. **NO SOURCE FOUND — clinician must supply** if a Ministry source must outrank
   TEMD.
2. **Depression screening** that TEMD requires — belongs to the licensed PHQ-9 path; TEMD's "Türkçe geçerliliği"
   claim conflicts with the repo's HB-L24 record and is not adopted. Clinician confirms the path.
3. **Sleep and eating instruments** (Epworth, Pittsburgh, STOP-Bang, Berlin, *Yeme Tutum Testi*) and Edmonton
   staging — licence `UNKNOWN`, fail-closed; Turkish validation not recorded. **NO SOURCE FOUND (licence).**
4. **Purging beyond vomiting** (laxatives, diuretics — O-S1) and **night eating** (O-S1) — sourced but not
   drafted, to keep one concern per question and stay within twelve. Clinician may swap them in.
5. **Family history, food shopping and cooking, activity-limiting conditions** (O-S1 Tablo 1 and p. 53) — sourced,
   not drafted. Family history has no OPT root (INT-041 posture).
6. **Anthropometry** (weight, height, waist, neck, BMI) — measured, never asked as free numbers (invariant 22); no
   body-weight archetype in the OPT (INT-032).
7. **Rapid weight gain with oedema or breathlessness; post-bariatric alarm list** — **NO SOURCE FOUND.**
8. **Permission to discuss weight** (O-S3 1.9.2) — whether booking the clinic counts as permission, or whether the
   flow opens with an explicit permission question, is a clinician decision. Not drafted.
9. **Weight-stigma experiences** (O-S3 1.1.1) — sourced, not drafted for unsupervised pre-visit use.
10. **EASO guidance** — not retrieved; NG246 used instead.
11. **EK-4 acuity** — no snapshot; **no level proposed**; RED axes (invariant 21) unassigned.
12. **openEHR leaf paths (at-codes)** — deferred (INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1**: no RED/YELLOW asserted; no `candidate_flag` raised; §2.3 is a review list only.
- **Inv. 2 / patient copy**: `siz`, B1, one question mark per turn, non-stigmatising, no
  diagnosis/treatment/prognosis wording; no condition is named to the patient.
- **Inv. 7**: nothing extends `base.life_threat`; crisis content stays with the base layer.
- **Inv. 10 / instrument fidelity**: no sleep, eating, motivation or mood scale item reproduced or paraphrased.
- **Inv. 20**: no accuracy or prevalence figure reproduced; TEMD's PHQ-9 validation claim explicitly not adopted.
- **Inv. 22**: no numerals in any question; no numeric answer requested.
- **Clinical content rule**: sources O-S1…O-S3 are candidates; rules stay `status: draft_needs_source` until
  verbatim snapshots are committed.
- **HB-C1**: awaits clinician sign-off; NOT served.
