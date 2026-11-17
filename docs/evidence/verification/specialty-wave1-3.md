# Verification of the wave 1–3 specialty proposals + four surgical proposals — awaiting-clinical-review

Reviewer: independent clinical-content verifier (challenger) subagent, 2026-09-26. Read-only review of
`docs/evidence/proposals/<slug>.md` for 29 wave 1–3 slugs and 4 new surgical slugs (`genel_cerrahi`,
`gogus_cerrahisi`, `kalp_ve_damar_cerrahisi`, `plastik_rekonstruktif_ve_estetik_cerrahi`). Every item
here is `awaiting-clinical-review`; passing this review is not a physician signature. The reviewer
authored no clinical value: no threshold, level or cut-off is proposed below, and every replacement
text only rewords, splits or removes what the proposal already sourced.

State of the tree at review time: commit 32ca8d6e landed mid-review. The served
`packages/protocols/specialty/<slug>.yaml` files are now byte-exact `generate-l0` drafts (L0). The
wave 1–3 candidates were moved verbatim into `packages/protocols/review/specialty/`, and
`scripts/dev/gen_specialty_packs.py` now writes only into that review queue. The four new slugs have
no review candidate yet. In the moved wave 1–3 candidates, `soru_N` = proposal Q(N+1) and Q1 =
`basvuru_nedeni`, so the Q numbers below map directly onto the current candidates.

## BLUF

- **380 items reviewed**: 332 across 29 wave 1–3 proposals and 48 across the 4 new proposals.
  **Wave 1–3: 153 REVISE, 8 gate/type-only, 55 duplicates of a base or fixed slot (remove or bind),
  7 HOLD, 109 PASS. New four: 3 REVISE, 3 gate-only, 42 PASS.**
- **Invariant 2 breaches.** 47 asks carry two question marks. The generator refuses all 47, so the
  loss is silent coverage, not a served breach. A further ~64 asks put two or more questions under one
  question mark (`;`, "… mı ya da … mu?", when+how, two concerns joined under one particle). These pass
  the generator's only check, which counts `?`. The proposals' own §3 headers say "one concern per
  question", and these asks contradict that.
- **Top systemic issue (HIGH, generator).** When Q1 is refused, `build_pack` silently promotes the next
  surviving question into the required `basvuru_nedeni` slot. As the proposals are written this
  happens in 23 of the 29 wave 1–3 slugs. In `agiz_dis_ve_cene_cerrahisi` and `dis_hekimligi` the
  airway question becomes the visit-reason slot. `soru_N` numbering also shifts after every refusal.
- **Second systemic issue (MEDIUM).** Specialty proposals re-ask what the universal base layer already
  asks: medications, allergies, anticoagulants, pregnancy, immunosuppression, onset and trajectory,
  goals and location. That is 55 duplicates. The generator's fixed `basvuru_nedeni`/`sikayet_suresi`
  slots also duplicate base `chief_complaint_text`, `onset_date` and `duration`.
- **Clean.** Nothing extends `base.life_threat`, and no RED or level is authored. No digits appear,
  and nothing uses `sen`. No PHQ-9/GAD-7/C-SSRS/WHO-5 item is reproduced. No suicide or self-harm item
  appears in `amatem`, `cematem` or `cocuk_ve_ergen_ruh_sagligi`. Every paediatric proposal addresses
  the parent or proxy consistently.
- **Clinical-language defects to fix before any candidate is regenerated.** Two Turkish homographs
  change the meaning: "soluyor" and "susuyor". One translation is wrong: "idrar kaçağı (reflü)" for
  VUR. "bez" in a paediatric pack reads as "diaper". "uyuşturucu iğnesi" reads as "narcotic". One
  patient-copy threshold contradicts its own source: "beş günden uzun" vs NG143 "5 days or longer". One
  rationale rests on a superseded dental-shielding recommendation.

## A. Findings

| # | where | finding | severity |
|---|---|---|---|
| 1 | `gen_specialty_packs.py` `build_pack` | `questions[0]` becomes `basvuru_nedeni` whatever its Q number. A refused Q1 promotes Q2, or later, into the required reason slot. As written that hits 23/29 wave 1–3 slugs: the airway ask in `agiz_dis_ve_cene_cerrahisi` and `dis_hekimligi`, the pregnancy ask in `agiz_dis_cene_radyolojisi`, the alertness ask in `cocuk_sagligi_ve_hastaliklari`, the sputum ask in `cocuk_gogus_hastaliklari` and the joint-swelling ask in `cocuk_romatolojisi`. `soru_{i}` comes from `enumerate`, so ids shift after every refusal. Fix: bind Q1 by label number, fail the slug if Q1 is refused, and derive `soru_{n-1}` from the Q number (or require `gen: slot=`). | HIGH |
| 2 | 29 wave 1–3 proposals | 47 asks with two `?` (generator refuses them, so coverage is silently lost). Every one of the 23 Q1s ending "…? Kısaca anlatabilir misiniz?" is among them. | HIGH |
| 3 | 29 wave 1–3 + 2 new | ~64 multi-question asks with one `?`: 13 when+how ("ne zaman … ve … nasıl"), `;`-joined (cocuk_enf Q7, cocuk_endo Q9), "… mı ya da … mu?", "yoksa" either/or (cocuk_enf Q4/Q11, cocuk_romato Q3, kalp Q8, plastik Q11) and two concerns under one particle. The generator's `q.count("?") != 1` misses all of them. | HIGH |
| 4 | generator fixed slots vs `base/intake.yaml` | `basvuru_nedeni` duplicates base `reason_for_visit.chief_complaint_text`, and `sikayet_suresi` duplicates base `hpi.onset_date` + `hpi.duration`. Resolution is base → cluster → specialty, and `packages/protocols/src` has no concept-level de-dup, so every generated pack double-asks reason and duration. Decide once: drop the fixed slots, or bind them to the base ids. | MEDIUM |
| 5 | 27 proposals | 55 items re-ask a base slot: `meds_confirmed`/`meds_new_or_stopped`, `allergies`/`allergy_reaction`, `anticoagulant_use`, `pregnancy_status`, `immunosuppression`, `patient_goals`, `onset_date` + `trajectory`, `location_text`, `timing_pattern`, `otc_herbal`. Marked **D** per slug: remove, or bind to the base id. Specialty-specific medication or allergy asks (latex, local anaesthetic, anti-seizure, insulin/cortisone, antiresorptive, auto-injector, special formula) are kept. | MEDIUM |
| 6 | 4 new proposals | Gates live only in prose ("Ask only if Q2 is yes"). No `gen:` line exists, so the generator drops the gate and asks "Bu şişlik…" / "Protezinizin…" unconditionally. Exact `gen:` lines are in §C. | MEDIUM |
| 7 | `agiz_dis_cene_radyolojisi` Q4 / S4 | The rationale ("ek korumanın uygulanabilmesi için") rests on the 2004 FDA / 2006 ADA thyroid-collar sentence. The ADA's 2024 radiation-safety recommendations (JADA 2024) reportedly discontinue routine thyroid collars and aprons; verify. Drop the rationale sentence and bind to base `pregnancy_status`. | MEDIUM |
| 8 | `cocuk_enfeksiyon_hastaliklari` Q3 | Patient text "beş günden uzun" contradicts NG143 1.2.14 "5 days or longer" (boundary). "kaç gündür" asks for a number in a string slot (invariant 22). Split into boolean + `duration`, and keep the boundary in the rule. | HIGH |
| 9 | `cocuk_nefrolojisi` Q9 | "idrar kaçağı (reflü)" means urinary incontinence, not VUR (S1 says VUR). Mistranslation. | HIGH |
| 10 | `cocuk_cerrahisi` Q4 | "soluyor" reads as solumak (breathing hard) as easily as solmak (going pale). S3's sign is pallor. Use "benzi sararıyor". | HIGH |
| 11 | `cocuk_endokrinolojisi` Q4 | "susuyor" reads as susmak (falls silent) as easily as susamak (is thirsty). | HIGH |
| 12 | `cocuk_hematolojisi_ve_onkolojisi` Q8 | "ele gelen bir bez" reads as "diaper" in a paediatric pack; the sentence is also 20 words. | MEDIUM |
| 13 | `agiz_dis_ve_cene_cerrahisi` Q12, `dis_hekimligi` Q12 | "uyuşturucu (lokal anestezi) iğnesi" reads as a narcotic, the same defect as wave 4–5 endodonti soru_11. | MEDIUM |
| 14 | 6 items | "kitle" (tumour connotation, alarming) → "sertlik": radyoloji Q7, agiz_cer Q7, dis Q6, aile Q8, hemato Q9, genel Q10. | LOW |
| 15 | `cocuk_hematolojisi_ve_onkolojisi` Q7 | "özellikle geceleri uykudan uyandıran" is not in NG12 1.10.3 ("persistent or unexplained bone pain"). An unsourced qualifier narrows the ask. | MEDIUM |
| 16 | `cocuk_norolojisi` Q7 | Regression is marked NO SOURCE FOUND, but `cocuk_genetik_hastaliklari` S1 carries the regression quote ("loss of previously gained skills … urgent"). Cross-cite. The same applies to `cocuk_metabolizma` Q8(a). | LOW |
| 17 | `aile_hekimligi` Q8, `cerrahi_onkoloji` Q3 | A whole-body lump is cited to NG12 1.4.1 (breast). The soft-tissue lump recommendation in NG12 (unexplained lump increasing in size) is the better anchor. Verify and re-cite. | LOW |
| 18 | `asi` Q8 | Marked NO SOURCE FOUND. S1's own contraindication table very likely lists pregnancy for live vaccines. Re-retrieve before HOLD is lifted; breastfeeding stays HOLD. | LOW |
| 19 | `anesteziyoloji` Q9 | "Ameliyat gününüzde en son ne zaman…" is asked at pre-visit, typically days before surgery, so the answer is meaningless then. It also puts two concerns in 19 words and asks for a time as free text (invariant 22). Split, type as date, and serve only in a day-of-surgery context; the clinician decides. S1 is ESAIC 2011 (adults); ESAIC 2022 updated the paediatric clear-fluid interval. That matters only to the rule. | MEDIUM |
| 20 | `anesteziyoloji` Q5, Q10 | `candidate_flag: YELLOW_REVIEW` is attached to planning facts (anticoagulant use, anaesthesia family history), not acuity. Remove. Q5 duplicates base `anticoagulant_use`. | LOW |
| 21 | `adli_tip` Q3–Q5 | IPV safety, companion and strangulation answers are a new sensitive data category on a patient-owned device that may be shared with the perpetrator. S2 (IFAS Box A) says "seeing the patient alone when taking history"; Q4 invites a companion. **Stop-and-ask** (CLAUDE.md: new personal-data categories), legal-reviewer + clinician. HOLD Q3/Q4. | HIGH |
| 22 | `deri_ve_zuhrevi_hastaliklari` Q9 | Genital-symptom (sexual-health) data. The proposal itself requires consent scope + inventory annotation + DPO sign-off (invariant 18). HOLD. | HIGH |
| 23 | `cocuk_ve_ergen_ruh_sagligi` Q3/Q4; base `screening.phq2/phq9/gad2/gad7` | Q3 (interest/mood change) and Q4 ("sık sık endişeli, kaygılı") track PHQ-9 items 1–2 and GAD-7 item 1 semantics, with a frequency framing. Base delivers those instruments. This is a paraphrase risk, not a verbatim breach. Reword to non-item observation (§B). | MEDIUM |
| 24 | `amatem` Q4/Q5/Q7/Q8 | These track WHO ASSIST items 2/3/6/7 one-for-one, including ASSIST's three-month window in Q4. The proposal says "topics only", ASSIST verbatim was not captured, and no ASSIST licence or Turkish-validation record exists. Drop the window, keep the items as history (not scored), and have the clinician decide whether ASSIST should instead be delivered verbatim through the instrument path (new licence row if so). | MEDIUM |
| 25 | paediatric proposals, `cematem`, `cocuk_ve_ergen_ruh_sagligi`, `asi` | Proxy addressing is consistent inside each proposal. No proposal gates on base `subject_role != 'kendim'`, so an adolescent answering for themselves hears "çocuğunuz". Adolescent self-report and confidentiality are left open (cematem §4 gap 4, ruh sağlığı §4 gap 5) → legal-reviewer (minors). `asi` addresses the vaccinee only; it needs proxy variants like wave 4–5 evde_saglik. | MEDIUM |
| 26 | `dis_hekimligi` Q3 vs `agiz_dis_cene_radyolojisi` Q9 | dis says the airway item "belongs to `base.life_threat` … the dental pack does not carry it" yet lists it. radyoloji says it is "carried across the `dental` cluster as a universal safety screen". Pick one posture. This review applies the wave 4–5 endodonti soru_7 form (ungated breathing/swallowing ask). | MEDIUM |
| 27 | `dis_hekimligi` Q8 | Avulsed permanent tooth is time-critical (IADT). A pre-visit capture has no sourced action path, so the clinician must decide whether a pre-visit ask helps at all. | LOW |
| 28 | voice-first wording | Typed-only verbs in a voice intake: "yazabilirsiniz" (adli Q1), "yazabilir misiniz" (anest Q1/Q4, asi Q1). "bu bölümü boş bırakabilirsiniz" (adli Q2). Parentheses and slashes read badly without a normaliser (invariant 22 disables it): 24 items. | LOW |
| 29 | Turkish grammar | "Çocuğunuz … kullandığı bir ilaç var mı?" (genetik Q11, sağlığı Q11). "Bebeğinizin doğduğunda" (metab Q3). "kustuğunda içinde" (gastro Q4). "Bebeğiniz" breaks the "Çocuğunuz" register (kardiyo Q5, metab Q3). "soruyorum" (genetik Q6) vs "soruyoruz" (radyoloji Q4): the system voice needs one person. | LOW |
| 30 | > 15 words | 58 sentences over the B1 limit, all in wave 1–3 proposals; each is fixed or removed in §B. | MEDIUM |
| 31 | generator fixed Q1 follow-up | `REASON_FOLLOW_UP_*` always says "şikâyetiniz"/"randevunuzun sebebi" and cannot be overridden by `gen:`. That is off-register for aşı, adli tıp, AMATEM/ÇEMATEM, ruh sağlığı and anesteziyoloji. Allow a `gen: follow_up=` on Q1. | LOW |
| 32 | `packages/protocols/review/specialty/*` (42 files) | The moved wave 1–3 candidates still declare `maturity: L1` and "clinician-DIRECTED (Dr. A. Moniri)". Only gastroenteroloji, kardiyoloji and noroloji were reworded. They are not loaded by `resolve_branch`, so nothing is served, but a candidate copied into the served tree would carry L1 without the HB-C1 block. Set L0 in the queue, or let the promotion step alone write L1. | LOW |
| 33 | all 33 | Nothing extends `base.life_threat`, and no RED, level or three-axis action is authored. `candidate_flag: YELLOW_REVIEW` annotations (22 proposals) stay within invariant 1's ceiling, and the generator does not carry them. The 4 new proposals carry none (preferred). No digits, no `sen`. | PASS |
| 34 | spot-checked quotes that support the ask | NG12 1.8.2/1.8.3; NG143 1.2.14/1.2.18; NG1 1.1.4/1.1.19; CG99 1.3.6 (48 h meconium); cocuk_romato S2 (night pain not responsive to simple analgesia); algoloji S2 (weight loss / unwell / nocturnal pain) + S4 (eyer anestezisi); IFAS Box B; JMF signs; cocuk_cerrahisi S3 (paroxysmal pain, pallor); cocuk_genetik S1 (regression); GEN-S1/S3/S7; TOR-S1/S2/S6; KVC-S1 A-3/S4/S5/S7; PRC-S3/S7/S8. | PASS |

## B. Replacement texts

Conventions (as in wave 4–5):
- Q numbers are the proposal's. In today's review-queue candidates, Q1 = `basvuru_nedeni` and
  soru_N = Q(N+1).
- **R** = revise (exact Turkish below). **D** = duplicate: remove, or bind to the named base slot.
  **G** = text passes; add a gate or type only. **H** = hold (source or consent).
- "(a)/(b)" = split into separate `**Q**` items, each with its own `gen:` line. "(b, if a)" =
  `gen: ask_if=<(a) slot> == true`. `[boolean]`/`[duration]`/`[date]` = `gen: type=`.
- Give every split item a semantic `gen: slot=` so renumbering cannot shift ids.
- An infant age gate, sex gate or visit-type gate is a clinical value. The cut-off stays the
  pending-value literal until signed; no age is proposed here.
- A kept ask that sets aside a threshold the proposal had put in the patient text moves that threshold
  to the rule; it is not deleted.
- Recurring forms:
  - **C2 trajectory fallback** (only if base `hpi.trajectory` is not served in the same session):
    "Şikâyetiniz başladığından bu yana nasıl değişti?"
  - **Airway pair** (wave 4–5 endodonti soru_7): (a) "Yüzünüzde, çenenizde ya da dilinizin altında
    şişlik var mı?" [boolean] · (b, NOT gated) "Nefes almakta ya da yutkunmakta zorlanıyor musunuz?"
    [boolean]
  - **Oral-ulcer split** (threshold moves to the rule, NG12 1.8.2): (a) "Ağzınızda ya da dudağınızda
    iyileşmeyen bir yara var mı?" [boolean] · (b, if a) "Bu yara ne zamandır var?" [duration]

### adli_tip — R2 · D2 · H2
- R Q1 → "Bugünkü randevunuzun konusu nedir?"
- R Q2 (soru_1) → "İsterseniz bu soruyu geçebilirsiniz. Doktorun önceden bilmesini istediğiniz bir şey var mı?"
- H Q3 (soru_2) — IPV safety inquiry. S1 non-universal caveat not captured verbatim; new sensitive data category; finding 21.
- H Q4 (soru_3) — companion invitation vs IFAS Box A "seeing the patient alone"; clinician + legal decision.
- D Q7 (soru_6) → base `meds_confirmed`/`meds_new_or_stopped`.
- D Q8 (soru_7) → base `allergies`.
- PASS: Q5 (IFAS Box B supports voice change + dysphagia; stays under finding 21's data decision), Q6.

### agiz_dis_cene_radyolojisi — R6 · D3
- R Q1 → "Bugünkü görüntüleme randevunuzun asıl sebebi nedir?"
- R Q2 (soru_1) → "Görüntüleme, ağzınızın ya da çenenizin hangi bölgesi için istendi?"
- D Q3 (soru_2) → remove (duplicates `sikayet_suresi`; two `?`).
- D Q4 (soru_3) → bind base `pregnancy_status`. Drop the shielding rationale (finding 7).
- R Q6 (soru_5) → oral-ulcer split.
- R Q7 (soru_6) → "Ağzınızda, çenenizde ya da boynunuzda elinize gelen bir şişlik ya da sertlik var mı?"
- R Q9 (soru_8) → airway pair.
- R Q10 (soru_9) → "Kemik erimesi ya da başka bir kemik sorunu için hiç ilaç kullandınız mı?" (past use counts for MRONJ; was 19 words)
- D Q12 (soru_11) → base `allergies` (20 words). If contrast history matters, the clinician adds it.
- PASS: Q5, Q8, Q11.

### algoloji — R5 · D3
- R Q1 → "Bugün sizi en çok hangi ağrınız rahatsız ediyor?"
- R Q2 (soru_1) → "Ağrınızın nasıl başladığını kendi sözlerinizle anlatır mısınız?" ("when" is base `onset_date`)
- D Q3 (soru_2) → base `location_text`.
- D Q4 (soru_3) → base `duration` + `timing_pattern`.
- R Q5 (soru_4)
  - (a) "Ağrınız dinlenirken ya da geceleri de oluyor mu?" [boolean]
  - (b, if a) "Ağrınız sizi geceleri uykudan uyandırıyor mu?" [boolean]
- R Q6 (soru_5)
  - (a) "Son zamanlarda istemeden kilo verdiniz mi?" [boolean]
  - (b) "Son zamanlarda kendinizi genel olarak halsiz ya da hasta hissediyor musunuz?" [boolean]
- R Q7 (soru_6)
  - (a) "Son günlerde idrar ya da dışkı kontrolünüzde yeni bir sorun oldu mu?" [boolean]
  - (b) "Bacaklarınızın arasında ya da makat çevresinde yeni bir uyuşma fark ettiniz mi?" [boolean]
  - Anchor on S4/GIRFT, not NG59 (NG59 excludes CES detail; wave 4–5 fizyoterapi finding).
- D Q12 (soru_11) → base `allergies` + `allergy_reaction` (16 words).
- PASS: Q8, Q9, Q10, Q11.

### amatem — R5 · D2
- R Q1 → "Bugün hangi konuda destek almak istersiniz?"
- R Q4 (soru_3) → "Son zamanlarda bunu ne sıklıkla kullandığınızı anlatır mısınız?" (drops ASSIST's three-month window and the yes/no "paylaşmak ister misiniz" mismatch)
- R Q6 (soru_5) → "Bu durum günlük yaşamınızı ya da sağlığınızı etkiliyor mu?"
- R Q8 (soru_7)
  - (a) "Daha önce azaltmayı ya da bırakmayı denediniz mi?" [boolean]
  - (b, if a) "O zaman size en çok ne iyi geldi?"
- D Q9 (soru_8) → base `patient_goals`.
- R Q10 (soru_9)
  - (a) "Daha önce bu konuda bir destek aldınız mı?" [boolean]
  - (b) "Bilmemizi istediğiniz başka bir sağlık durumunuz var mı?"
- D Q11 (soru_10) → base meds.
- PASS: Q2, Q3, Q5, Q7, Q12. Q5/Q7 carry the ASSIST-shadow note (finding 24); the clinician decides.

### beslenme_ve_diyet — R7 · D1
- R Q2 (soru_1) → "Beslenmenizle ilgili en çok neyi değiştirmek istersiniz?"
- R Q3 (soru_2) → "Son aylarda, çaba göstermediğiniz hâlde kilo verdiniz mi?" [boolean]
  - `gen: follow_up=Giysileriniz size eskisinden bol gelmeye başladı mı?`
  - Overlaps base `rf_weight_loss_unintentional`; the base slot has no `ask_tr`, so keep this ask and bind it there.
- R Q4 (soru_3) → "Son zamanlarda iştahınız azaldı ya da daha az yemeye başladınız mı?"
- R Q5 (soru_4)
  - (a) "Yemek yerken ya da bir şey içerken yutmakta zorlanıyor musunuz?" [boolean]
  - (b) "Yediğiniz lokmanın boğazınızda takıldığını hissediyor musunuz?" [boolean]
- R Q7 (soru_6) → "Şeker hastalığı ya da böbrek hastalığı gibi, beslenmenizi etkileyen bir hastalığınız var mı?"
- D Q8 (soru_7) → base meds + `otc_herbal`.
- R Q9 (soru_8) → "Size dokunan ya da alerji yapan bir yiyecek var mı?"
- R Q10 (soru_9) → "Sağlık, inanç ya da tercih nedeniyle yemediğiniz besinler var mı?"
- PASS: Q1, Q6, Q11.

### cocuk_cerrahisi — R5 · D3
- R Q1 → "Çocuğunuzu bugün getiren temel şikâyet nedir?"
- D Q2 (soru_1) → base `onset_date` + `trajectory` (C2 fallback if the base slots are not served).
- R Q4 (soru_3) — "soluyor" homograph.
  - (a, if Q3) "Karın ağrısı gelip geçen ataklar hâlinde mi oluyor?" [boolean]
  - (b, if a) "Bu ağrı ataklarında çocuğunuzun benzi sararıyor mu?" [boolean]
- R Q6 (soru_5) → "Kusmuğun rengi yeşil ya da sarımsı yeşil miydi?" [boolean], ask_if Q5
- R Q9 (soru_8)
  - (a) "Çocuğunuzun kasığında ya da testis torbasında bir şişlik var mı?" [boolean]
  - (b, if a) "Bu şişlik elle bastırınca ya da çocuk uzanınca içeri giriyor mu?" [boolean] (S2 irreducibility; mirrors genel_cerrahi Q2/Q3)
- R Q10 (soru_9) → "Çocuğunuza daha önce kasık fıtığı ya da inmemiş testis gibi bir tanı kondu mu?"
- D Q11 (soru_10) → base meds.
- D Q12 (soru_11) → base `allergies`.
- PASS: Q3, Q5, Q7, Q8.

### agiz_dis_ve_cene_cerrahisi — R8 · D2
- R Q1 → "Bugünkü randevunuzda sizi hekime getiren asıl şikâyetiniz nedir?"
- D Q2 (soru_1) → base `trajectory` (C2 fallback).
- R Q3 (soru_2) → airway pair.
- R Q4 (soru_3) → "Bu şişlikle birlikte ateşiniz de var mı?" [boolean], ask_if Q3(a)
- R Q5 (soru_4) → "Son zamanlarda ağzınızı açmakta zorlanıyor musunuz?"
- R Q6 (soru_5) → oral-ulcer split.
- R Q7 (soru_6) → "Ağzınızda, dudağınızda ya da boynunuzda geçmeyen bir şişlik ya da sertlik var mı?"
- D Q9 (soru_8) → base `anticoagulant_use`.
- R Q11 (soru_10) → "Kemik erimesi ya da başka bir kemik sorunu için hiç ilaç kullandınız mı?" (was 24 words, two particles)
- R Q12 (soru_11) → "Herhangi bir ilaca, diş uyuşturma iğnesine ya da lateks eldivene alerjiniz var mı?"
- PASS: Q8, Q10.

### aile_hekimligi — R3 · G1 · D3
- R Q1 → "Bugünkü görüşmede sizi en çok rahatsız eden konu nedir?"
- D Q2 (soru_1) → base `onset_date` + `trajectory`.
- R Q8 (soru_7) → "Vücudunuzda nedenini bilmediğiniz yeni bir şişlik ya da sertlik fark ettiniz mi?" (re-cite, finding 17)
- G Q9 (soru_8) → ask_if on sex (clinician); text passes.
- R Q10 (soru_9) → "Şeker hastalığı ya da yüksek tansiyon gibi süregelen bir hastalığınız var mı?"
- D Q11, Q12 → base meds, `allergies`.
- PASS: Q3–Q7.

### cocuk_enfeksiyon_hastaliklari — R8 · D1
- D Q2 (soru_1) → remove (duplicates `sikayet_suresi`; two `?`).
- R Q3 (soru_2) — threshold moves to the rule as "five days or longer" (finding 8).
  - (a) "Çocuğunuzun ateşi oldu mu?" [boolean]
  - (b, if a) "Çocuğunuzun ateşi ne zamandır sürüyor?" [duration]
- R Q4 (soru_3) → "Çocuğunuz her zamanki gibi emebiliyor ya da bir şeyler içebiliyor mu?"
- R Q6 (soru_5) → "Çocuğunuz bu hastalık sırasında havale ya da nöbet geçirdi mi?"
- R Q7 (soru_6)
  - (a) "Çocuğunuz her zamankinden çok uykulu ya da halsiz mi?" [boolean]
  - (b) "Çocuğunuzu uyandırmakta zorlanıyor musunuz?" [boolean]
- R Q8 (soru_7) → "Çocuğunuzun cildinde, üzerine bastırınca solmayan kırmızı ya da mor bir döküntü var mı?"
- R Q10 (soru_9)
  - (a) "Çocuğunuza daha önce konulmuş süregen bir hastalık tanısı var mı?" [boolean]
  - (b) "Çocuğunuz erken mi doğdu?" [boolean] (S3 "Prematürite")
  - Immune status goes to base `immunosuppression`.
- R Q11 (soru_10) → "Bildiğiniz kadarıyla, çocuğunuzun eksik kalan bir aşısı var mı?"
- R Q12 (soru_11)
  - (a) → base meds (D)
  - (b) "Çocuğunuz son bir ay içinde antibiyotik kullandı mı?" [boolean] (S3)
- PASS: Q1, Q5, Q9.

### anesteziyoloji — R4 · D2
- R Q1 → "Hangi ameliyat ya da işlem için anestezi görüşmesine geldiniz?"
- R Q3 (soru_2) → "Şeker hastalığı, tansiyon ya da astım gibi süregelen bir rahatsızlığınız var mı?"
- D Q4 (soru_3) → base meds (two `?`, typed verb).
- D Q5 (soru_4) → base `anticoagulant_use`; drop the candidate_flag.
- R Q6 (soru_5) → "Herhangi bir ilaca ya da lateks eldivene alerjiniz var mı?"
- R Q9 (soru_8) — finding 19; serve only in a day-of-surgery context.
  - (a) "En son ne zaman katı bir şey yediniz?" [date]
  - (b) "En son ne zaman bir şey içtiniz?" [date]
- PASS: Q2, Q7, Q8, Q10. Drop Q10's candidate_flag.

### asi — R3 · D1 · H1
- R Q1 → "Bugün hangi aşıyı yaptırmayı planlıyorsunuz?"
- R Q3 (soru_2) → "Daha önce bir aşıdan sonra ciddi bir alerjik tepki yaşadınız mı?" [boolean]
  - `gen: follow_up=Bu tepkide yüzünüzde şişme ya da nefes almada zorluk oldu mu?`
- R Q5 (soru_4)
  - (a) "Bugün kendinizi hasta hissediyor musunuz?" [boolean]
  - (b) "Bugün ateşiniz var mı?" [boolean]
- D Q7 (soru_6) → base `immunosuppression` (near-verbatim duplicate).
- H Q8 (soru_7) — pregnancy → base `pregnancy_status`. Breastfeeding "Şu anda bebeğinizi emziriyor musunuz?" stays on hold until sourced (finding 18).
- PASS: Q2, Q4, Q6. Add proxy variants keyed on `subject_role` (finding 25).

### cocuk_hematolojisi_ve_onkolojisi — R9 · D2
- R Q1 → "Bugün çocuğunuzla ilgili sizi en çok düşündüren konu nedir?"
- D Q2 (soru_1) → base `onset_date` + `trajectory`.
- R Q3 (soru_2) → "Çocuğunuzun vücudunda nedeni belli olmayan morluklar fark ettiniz mi?"
- R Q4 (soru_3)
  - (a) "Çocuğunuzda nedeni belli olmayan burun ya da diş eti kanaması oldu mu?" [boolean]
  - (b) "Çocuğunuzun cildinde iğne başı büyüklüğünde kırmızı ya da mor noktalar fark ettiniz mi?" [boolean]
- R Q5 (soru_4)
  - (a) "Çocuğunuz son zamanlarda her zamankinden solgun görünüyor mu?" [boolean]
  - (b) "Çocuğunuz son zamanlarda geçmeyen bir yorgunluk yaşıyor mu?" [boolean]
- R Q7 (soru_6) → "Çocuğunuz geçmeyen ya da nedeni belli olmayan bir kemik ağrısından yakınıyor mu?"
- R Q8 (soru_7) → "Çocuğunuzun boynunda, koltuk altında ya da kasığında geçmeyen bir şişlik fark ettiniz mi?"
- R Q9 (soru_8) → "Çocuğunuzun karnında şişlik ya da elinize gelen bir sertlik fark ettiniz mi?"
- R Q10 (soru_9) → "Çocuğunuzun fotoğraflarında göz bebeğinin beyaz parladığını fark ettiniz mi?"
- R Q11 (soru_10) — solid-tumour patients on treatment carry the same neutropenic-fever context.
  - (a) "Çocuğunuza daha önce kanla ilgili ya da başka ciddi bir hastalık tanısı kondu mu?" [boolean]
  - (b, if a) "Çocuğunuz şu anda bu hastalık için düzenli bir tedavi görüyor mu?" [boolean]
- D Q12 (soru_11) → base meds.
- PASS: Q6.

### cematem — R3 · D3
- R Q1 → "Bugün çocuğunuz için hangi konuda destek almak istersiniz?"
- R Q6 (soru_5) → "Bu durum çocuğunuzun günlük yaşamını ya da sağlığını etkiliyor mu?"
- R Q8 (soru_7)
  - (a) "Çocuğunuz daha önce bu konuda bir destek aldı mı?" [boolean]
  - (b) "Bilmemizi istediğiniz başka bir sağlık durumu var mı?"
- D Q9 (soru_8) → base meds.
- D Q10 (soru_9) → base `allergies` + `allergy_reaction` (17 words).
- D Q11 (soru_10) → base `patient_goals`.
- PASS: Q2, Q3, Q4, Q5, Q7, Q12. Adolescent voice and confidentiality → finding 25.

### cerrahi_onkoloji — R5 · D2
- R Q1 → "Bugünkü görüşmede sizi hekime getiren en önemli konu nedir?"
- R Q2 (soru_1) → "Bu durumu nasıl fark ettiğinizi kendi sözlerinizle anlatır mısınız?"
- R Q3 (soru_2) → "Vücudunuzda yeni fark ettiğiniz bir şişlik ya da sertlik var mı?" (re-cite, finding 17)
- R Q5 (soru_4) → "Son zamanlarda dışkıda, idrarda ya da başka bir yerden beklenmedik kanama oldu mu?"
- R Q9 (soru_8)
  - (a) "Daha önce size kanser tanısı konuldu mu?" [boolean]
  - (b, if a) "Bunun için ameliyat, ışın ya da ilaç tedavisi gördünüz mü?" [boolean]
- D Q10 (soru_9) → base meds + `anticoagulant_use`.
- D Q11 (soru_10) → base `allergies` + `allergy_reaction`.
- PASS: Q4, Q6, Q7, Q8, Q12.
- Naming "kanser" in a history ask is inconsistent with deri/hematoloji, which avoid it. Confirm the PolicyGuard diagnosis arm distinguishes asking about a known diagnosis from asserting one.

### cocuk_gogus_hastaliklari — R5 · G1 · H1
- R Q1 → "Çocuğunuzu bugün hekime getiren en önemli konu nedir?"
- R Q2 (soru_1)
  - (a) "Çocuğunuzun öksürüğü var mı?" [boolean]
  - (b, if a) "Bu öksürük ne zamandır sürüyor?" [duration]
- R Q3 (soru_2) → "Çocuğunuzun öksürüğü balgamlı gibi mi geliyor?", ask_if Q2(a) ("sümük" confounds with nasal discharge)
- H Q4 (soru_3) — S4 verbatim not captured; text passes.
- R Q6 (soru_5)
  - (a) "Çocuğunuz şu sıralarda her zamankinden hızlı nefes alıyor mu?" [boolean]
  - (b) "Nefes alırken çocuğunuzun kaburgalarının arası içeri çekiliyor mu?" [boolean]
  - (c) "Çocuğunuz nefes verirken inler gibi bir ses çıkarıyor mu?" [boolean]
- G Q8 (soru_7) → ask_if on infant age (BRUE scope; clinician value).
- R Q12 (soru_11) → "Çocuğunuz solunumu için düzenli bir ilaç ya da nefes açıcı kullanıyor mu?"
- PASS: Q5, Q7, Q9, Q10, Q11.

### cocuk_genetik_hastaliklari — R1 · D1
- R Q9 (soru_8) — S3 is LOW-confidence; re-source before sign-off.
  - (a) "Çocuğunuz şu sıralarda alışılmadık şekilde halsiz ya da uykulu mu?" [boolean]
  - (b) "Çocuğunuz şu sıralarda tekrar tekrar kusuyor ya da beslenemiyor mu?" [boolean]
- D Q11 (soru_10) → base meds. If kept, fix the grammar: "Çocuğunuzun şu anda düzenli kullandığı bir ilaç var mı?"
- PASS: Q1–Q8, Q10. Q6: pick one system voice ("soruyoruz").

### cocuk_norolojisi — R5 · G2 · D2
- R Q1 → "Çocuğunuzu bugün getiren temel konu nedir?"
- D Q2 (soru_1) → base `onset_date` + `trajectory`.
- R Q3 (soru_2) → "Çocuğunuz bilincini kaybettiği ya da vücudunun istemsiz kasılıp titrediği bir nöbet geçirdi mi?"
- G Q4 (soru_3) → ask_if Q3.
- G Q6 (soru_5) → ask_if Q5 (presupposes headache).
- R Q7 (soru_6)
  - (a) "Çocuğunuz yürüme ya da konuşma gibi becerilerde yaşıtlarından geride mi?" [boolean]
  - (b) "Çocuğunuz daha önce yapabildiği bir beceriyi sonradan kaybetti mi?" [boolean] (cite cocuk_genetik S1)
- R Q8 (soru_7) → "Çocuğunuza daha önce epilepsi gibi bir sinir sistemi hastalığı tanısı kondu mu?"
- R Q9 (soru_8) → "Çocuğunuzun nöbet ilacı gibi düzenli kullandığı bir ilaç var mı?"
- D Q10 (soru_9) → base `allergies`.
- PASS: Q5.

### cocuk_kardiyolojisi — R8 · D1
- R Q1 → "Çocuğunuzu bugün getiren temel konu nedir?"
- D Q2 (soru_1) → base `onset_date` + `trajectory`.
- R Q4 (soru_3) — ask_if on infant age.
  - (a) "Çocuğunuz emerken ya da mama alırken çabuk yoruluyor mu?" [boolean]
  - (b) "Çocuğunuz beslenirken terliyor mu?" [boolean]
- R Q5 (soru_4) → "Çocuğunuzun kilo alması ya da büyümesi size yavaş mı geliyor?"
- R Q6 (soru_5)
  - (a) "Çocuğunuz son zamanlarda her zamankinden çabuk yoruluyor mu?" [boolean]
  - (b) "Çocuğunuz son zamanlarda nefes almakta zorlanıyor mu?" [boolean]
  - (c) "Çocuğunuzun göz kapaklarında şişlik oluyor mu?" [boolean]
- R Q7 (soru_6) → "Çocuğunuzun kalbinin hızlı, düzensiz ya da çok güçlü çarptığı oldu mu?"
- R Q8 (soru_7) → "Bu çarpıntı ya da baygınlık koşarken ya da oyun oynarken oluyor mu?" [boolean]
  - ask_if Q7 or Q9 is yes; move it after Q9 (it refers to fainting before Q9 asks it).
- R Q10 (soru_9)
  - (a) "Ailenizde genç yaşta nedeni bilinmeyen ani ölüm yaşandı mı?" [boolean]
  - (b) "Ailenizde kalıtsal bir kalp ritmi hastalığı olan biri var mı?" [boolean]
- R Q11 (soru_10)
  - (a) "Çocuğunuza daha önce bir kalp hastalığı tanısı kondu mu?" [boolean]
  - (b) "Çocuğunuz daha önce kalp ameliyatı oldu mu?" [boolean]
- PASS: Q3, Q9, Q12.

### deri_ve_zuhrevi_hastaliklari — R2 · G2 · D2 · H1
- D Q2 (soru_1) → base `trajectory` (C2 fallback: "Cilt şikâyetiniz başladığından bu yana nasıl değişti?").
- D Q3 (soru_2) → remove (duplicates `sikayet_suresi`; two `?`).
- G Q5, Q6 (soru_4, soru_5) — "Bu ben ya da leke" has no antecedent.
  - Add a gate item "Cildinizde sizi endişelendiren bir ben ya da leke var mı?" [boolean].
  - ask_if Q4–Q6 on that gate.
- H Q9 (soru_8) — sexual-health data; finding 22.
- R Q10 (soru_9) → "Daha önce size bir cilt hastalığı tanısı konuldu mu?"
- R Q11 (soru_10)
  - (a) → base meds (D)
  - (b) "Son zamanlarda yeni başladığınız bir ilaç oldu mu?" [boolean]
- PASS: Q1, Q4, Q7, Q8, Q12.

### cocuk_endokrinolojisi — R6 · G1 · D2
- R Q1 → "Çocuğunuzu bugün getiren temel konu nedir?"
- D Q2 (soru_1) → base `onset_date` + `trajectory`.
- R Q3 (soru_2)
  - (a) "Çocuğunuz son zamanlarda her zamankinden sık ve bol idrara çıkıyor mu?" [boolean]
  - (b) "Çocuğunuz yeniden altını ya da yatağını ıslatmaya başladı mı?" [boolean]
- R Q4 (soru_3) → "Çocuğunuz son zamanlarda alışılmadık şekilde çok su içiyor mu?" ("susuyor" homograph)
- G Q7 (soru_6) → ask_if Q3, Q4 or Q5 is yes.
- R Q8 (soru_7) → "Çocuğunuz böbrek üstü bezi sorunu ya da başka bir nedenle düzenli kortizon ilacı kullanıyor mu?"
- R Q9 (soru_8) → "Çocuğunuzun şu anda kusması, belirgin halsizliği ya da ilacını alamama durumu var mı?", ask_if Q8
- R Q11 (soru_10) → "Çocuğunuzun insülin ya da kortizon gibi düzenli kullandığı bir ilaç var mı?"
- D Q12 (soru_11) → base `allergies`.
- PASS: Q5, Q6, Q10.

### cocuk_nefrolojisi — R4 · H1 · D3
- R Q1 → "Çocuğunuzu bugün getiren temel konu nedir?"
- D Q2 (soru_1) → base `onset_date` + `trajectory`.
- H Q4 (soru_3) — NO SOURCE FOUND. If sourced: "Çocuğunuzun idrarında kan ya da kola rengine benzer bir koyulaşma gördünüz mü?"
- R Q6 (soru_5)
  - (a) "Çocuğunuz her zamankinden daha sık idrara çıkıyor mu?" [boolean]
  - (b) "Çocuğunuz yeniden altını ya da yatağını ıslatmaya başladı mı?" [boolean]
  - (c) "Çocuğunuz idrarını tutmakta zorlanıyor mu?" [boolean]
- R Q7 (soru_6) → "Çocuğunuzda ateşle birlikte karın ağrısı ya da belinin yan tarafında ağrı var mı?"
- R Q9 (soru_8) → "Çocuğunuza daha önce böbrek ya da idrar yollarıyla ilgili bir tanı kondu mu?" (finding 9)
- D Q10, Q11 → base meds, `allergies`.
- PASS: Q3, Q5, Q8.

### cocuk_romatolojisi — R4
- R Q1 → "Çocuğunuzu bugün hekime getiren en önemli konu nedir?"
- R Q3 (soru_2) → "Bu eklem şişliği ne zamandır sürüyor?" [duration], ask_if Q2 (the six-week boundary stays in the rule)
- R Q7 (soru_6)
  - (a) "Çocuğunuzun ağrısı onu geceleri uykudan uyandırıyor mu?" [boolean]
  - (b) "Çocuğunuzun ağrısı ağrı kesiciye rağmen devam ediyor mu?" [boolean] (S2 supports both)
- R Q9 (soru_8) → "Şu sıralarda çocuğunuzun bir eklemi aniden sıcak, kızarık ve çok ağrılı hâle geldi mi?"
- PASS: Q2, Q4, Q5, Q6, Q8, Q10, Q11, Q12.

### cocuk_gastroenterolojisi — R6 · D1
- D Q2 (soru_1) → remove (duplicates `sikayet_suresi`; two `?`).
- R Q4 (soru_3) → "Çocuğunuzun kusmuğunda kan ya da kahve telvesi gibi koyu bir şey gördünüz mü?"
- R Q5 (soru_4) → "Çocuğunuz beslendikten sonra giderek artan ya da fışkırır gibi kusuyor mu?"
  - ask_if on infant age (NG1 cut-off is a clinical value; take "iki aylıktan küçükse" out of the text).
- R Q6 (soru_5) → "Çocuğunuzun dışkısında kan ya da katran gibi siyah bir renk gördünüz mü?"
- R Q8 (soru_7)
  - (a) "Çocuğunuzun ağzı kuru ya da gözleri çökük görünüyor mu?" [boolean]
  - (b) "Çocuğunuz her zamankinden daha az çiş yapıyor mu?" [boolean]
- R Q11 (soru_10) — CG99 48 h stays in the rule.
  - (a) "Çocuğunuzun kabızlığı bebekliğinin ilk haftalarında başladı mı?" [boolean]
  - (b) "Doğumdan sonra çocuğunuzun ilk kakasının geciktiği size söylendi mi?" [boolean]
- R Q12 (soru_11)
  - (a) "Çocuğunuza daha önce mide, bağırsak ya da karaciğerle ilgili bir tanı kondu mu?" [boolean]
  - (b) → base meds (D)
- PASS: Q1, Q3, Q7, Q9, Q10.

### cocuk_immunolojisi_ve_alerjisi — R7 · D2
- R Q1 → "Bugün çocuğunuzla ilgili sizi en çok düşündüren konu nedir?"
- D Q2 (soru_1) → base `onset_date` + `trajectory`.
- R Q4 (soru_3)
  - (a) "Çocuğunuz son bir yıl içinde iki ya da daha fazla kez zatürre geçirdi mi?" [boolean]
  - (b) "Çocuğunuz son bir yıl içinde iki ya da daha fazla kez ağır sinüzit geçirdi mi?" [boolean]
- R Q5 (soru_4)
  - (a) "Çocuğunuz uzun süre antibiyotik kullanmasına rağmen enfeksiyonları geçmekte zorlandı mı?" [boolean]
  - (b) "Çocuğunuzun enfeksiyonları için damardan antibiyotik vermek gerekti mi?" [boolean]
- R Q6 (soru_5)
  - (a) "Çocuğunuzun kilo alması ya da büyümesi yaşıtlarından geri mi?" [boolean]
  - (b) "Çocuğunuzun ağzında geçmeyen pamukçuk ya da ciltte mantar oldu mu?" [boolean]
  - (c) "Çocuğunuzda tekrar eden, derin iltihaplı çıbanlar oldu mu?" [boolean]
- R Q7 (soru_6) → "Çocuğunuzda bir yiyecekten kısa süre sonra döküntü, kaşıntı ya da şişlik oldu mu?"
- R Q8 (soru_7) → "Çocuğunuz daha önce ağır bir alerjik tepki geçirdi mi?" [boolean]
  - `gen: follow_up=Bu tepkide nefes darlığı ya da bayılma oldu mu?`
- R Q11 (soru_10)
  - (a) "Çocuğunuza daha önce kalem şeklinde bir adrenalin iğnesi yazıldı mı?" [boolean]
  - (b, if a) "Çocuğunuz bu kalemi yanında taşıyor mu?" [boolean]
- D Q12 (soru_11) → base meds.
- PASS: Q3, Q9, Q10. The JMF counts in Q3/Q4 are sourced and kept as boolean thresholds.

### cocuk_ve_ergen_ruh_sagligi — R6 · D3
- R Q1 → "Bugün çocuğunuz için hangi konuda destek almak istersiniz?"
- R Q3 (soru_2) → "Çocuğunuzun son zamanlardaki ruh hâlinde sizi düşündüren bir değişiklik oldu mu?" (finding 23)
- R Q4 (soru_3) → "Çocuğunuzun sizi düşündüren korkuları ya da endişeleri var mı?" (drops the GAD-style frequency framing)
- R Q5 (soru_4)
  - (a) "Çocuğunuz dikkatini toplamakta ya da yerinde durmakta zorlanıyor mu?" [boolean]
  - (b, if a) "Bu durum hem evde hem de okulda oluyor mu?" [boolean]
- R Q6 (soru_5) → "Çocuğunuzun uykuya dalmasında ya da uykusunda bir değişiklik oldu mu?"
- D Q9 (soru_8) → base `onset_date` + `trajectory` (when+how, 16 words).
- R Q10 (soru_9)
  - (a) "Çocuğunuz daha önce bu konuda bir destek aldı mı?" [boolean]
  - (b) "Bilmemizi istediğiniz başka bir sağlık ya da gelişim durumu var mı?"
- D Q11, Q12 → base meds, `allergies` (Q12 is 17 words).
- PASS: Q2, Q7, Q8. No suicide or self-harm item: confirmed.

### cocuk_urolojisi — R4 · G1 · H1 · D3
- R Q1 → "Çocuğunuzu bugün getiren temel şikâyet nedir?"
- D Q2 (soru_1) → base `onset_date` + `trajectory`.
- G Q4 (soru_3) → ask_if Q3 or Q5. The S3 fragment still needs re-verification.
- R Q5 (soru_4) → "Çocuğunuz gündüzleri idrar kaçırıyor ya da çok sık tuvalete gidiyor mu?"
- R Q8 (soru_7)
  - (a) "Çocuğunuzun testis ya da kasık bölgesinde aniden başlayan şiddetli bir ağrı oldu mu?" [boolean]
  - (b, if a) "Bu ağrıyla birlikte bulantı ya da kusma oldu mu?" [boolean]
- R Q9 (soru_8) — sex gate is a clinical value.
  - (a) "Çocuğunuzun testis torbasında şişlik ya da kızarıklık fark ettiniz mi?" [boolean]
  - (b) "Çocuğunuzun testislerinden birini torbada elle bulamadığınız oldu mu?" [boolean]
- H Q10 (soru_9) — NO SOURCE FOUND; text passes.
- D Q11, Q12 → base meds, `allergies`.
- PASS: Q3, Q6, Q7.

### cocuk_metabolizma_hastaliklari — R7 · D2
- R Q1 → "Çocuğunuzu bugün getiren temel konu nedir?"
- D Q2 (soru_1) → base `onset_date` + `trajectory`.
- R Q3 (soru_2) → "Çocuğunuzun doğumdan sonra yapılan topuk kanı taramasında bir sorun bildirildi mi?"
- R Q4 (soru_3)
  - (a) "Ailenizde kalıtsal bir metabolizma hastalığı olan biri var mı?" [boolean]
  - (b) "Bu soruyu yalnızca sağlık değerlendirmesi için soruyoruz: anne ile baba arasında akrabalık var mı?" [boolean]
- R Q7 (soru_6) → "Bu belirtiler çocuğunuz hastalandığında ya da uzun süre aç kaldığında artıyor mu?", ask_if Q5 or Q6
- R Q8 (soru_7)
  - (a) "Çocuğunuz daha önce yapabildiği oturma, yürüme ya da konuşma gibi becerileri kaybetti mi?" [boolean] (cite cocuk_genetik S1)
  - (b) "Çocuğunuzun gelişimi son zamanlarda yavaşladı mı?" [boolean] (S2)
- R Q10 (soru_9) → "Çocuğunuz özel bir diyet ya da özel bir mama kullanıyor mu?"
- R Q11 (soru_10) → "Çocuğunuzun düzenli kullandığı bir ilaç, vitamin ya da takviye var mı?"
- D Q12 (soru_11) → base `allergies`.
- PASS: Q5, Q6, Q9.

### dis_hekimligi — R9 · D2
- R Q1 → "Bugünkü randevunuzda sizi diş hekimine getiren asıl şikâyetiniz nedir?"
- D Q2 (soru_1) → base `trajectory` (C2 fallback).
- R Q3 (soru_2) → airway pair; resolve the posture (finding 26).
- R Q4 (soru_3) → "Bu şişlikle birlikte ateşiniz de var mı?" [boolean], ask_if Q3(a)
- R Q5 (soru_4) → oral-ulcer split.
- R Q6 (soru_5) → "Ağzınızda, dudağınızda ya da boynunuzda geçmeyen bir şişlik ya da sertlik var mı?"
- R Q8 (soru_7) → "Yakın zamanda bir darbeyle kalıcı dişlerinizden biri tamamen yerinden çıktı mı?" (finding 27)
- R Q9 (soru_8)
  - (a) "Dişinizde ya da diş etinizde ağrı var mı?" [boolean]
  - (b, if a) "Bu ağrı ne zamandır sürüyor?" [duration]
- R Q10 (soru_9)
  - (a) "Diş etleriniz kanıyor mu?" [boolean]
  - (b) "Daha önce bir diş işleminden sonra olağandan uzun süre kanamanız oldu mu?" [boolean]
- D Q11 (soru_10) → base meds + `anticoagulant_use`.
- R Q12 (soru_11) → "Herhangi bir ilaca, diş uyuşturma iğnesine ya da lateks eldivene alerjiniz var mı?"
- PASS: Q7.

### cocuk_sagligi_ve_hastaliklari — R6 · D1
- R Q1 → "Çocuğunuzu bugün hekime getiren en önemli konu nedir?"
- R Q2 (soru_1) — the NG143 boundary stays in the rule.
  - (a) "Çocuğunuzun ateşi var mı?" [boolean]
  - (b, if a) "Çocuğunuzun ateşi ne zamandır sürüyor?" [duration]
- R Q4 (soru_3) → the three items of cocuk_gogus Q6.
- R Q7 (soru_6)
  - (a) "Çocuğunuz boynunu öne eğmekte zorlanıyor mu?" [boolean]
  - (b, ask_if infant age) "Çocuğunuzun bıngıldağı kabarık ya da gergin görünüyor mu?" [boolean]
  - (c) "Çocuğunuz bu hastalık sırasında havale geçirdi mi?" [boolean]
- R Q8 (soru_7)
  - (a) "Çocuğunuz her zamanki kadar beslenip bir şeyler içebiliyor mu?" [boolean]
  - (b) "Çocuğunuz her zamanki kadar çiş yapıyor mu?" [boolean]
- R Q9 (soru_8)
  - (a) "Çocuğunuzun bir kolunda ya da bacağında şişlik var mı?" [boolean]
  - (b) "Çocuğunuz bir kolunu ya da bacağını kullanmaktan kaçınıyor mu?" [boolean]
- D Q11 (soru_10) → base meds. If kept, fix the grammar as in cocuk_genetik Q11.
- PASS: Q3, Q5, Q6, Q10.

## C. The four new surgical proposals

These are the cleanest in the set: one `?` per ask, all asks ≤ 15 words, no time threshold in the
patient text, no candidate flags, and quotes that support each ask. What remains is the gates the
generator cannot see, plus two either/or asks.

### genel_cerrahi — R1 · G1
- G Q2/Q3 → add:
  - Q2 `gen: slot=kasik_karin_sislik; type=boolean`
  - Q3 `gen: slot=sislik_uzaninca_kuculuyor; type=boolean; ask_if=kasik_karin_sislik == true`
- R Q10 → "Boynunuzun ön tarafında bir şişlik ya da sertlik var mı?"
- PASS: Q1–Q9, Q11, Q12. Q7 stays ungated unless the clinician gates it.

### gogus_cerrahisi — 0
- PASS: all 12.
- Optional for the clinician: Q9 could add the Türkiye-specific household exposure term for
  environmental asbestos ("ak toprak"). That needs its own source; do not add it unsourced.

### kalp_ve_damar_cerrahisi — R1 · G1
- R Q8 → "Bu şişlik yalnızca tek bacağınızda mı?" [boolean]
  - Q7 `gen: slot=bacak_sislik; type=boolean`
  - Q8 `gen: slot=tek_bacak_sislik; type=boolean; ask_if=bacak_sislik == true`
  - An either/or ask leaves "evet" ambiguous in voice, and there is no enum slot type.
- G Q12 → the committed packs show no visit-type variable in `ask_if`. Place Q12 in the
  `post_discharge`/`followup` visit-type layer instead of the specialty pack.
- PASS: Q1–Q7, Q9–Q11.

### plastik_rekonstruktif_ve_estetik_cerrahi — R1 · G1
- G Q6 → add:
  - Q5 `gen: slot=meme_protezi; type=boolean`
  - Q6 `gen: slot=protez_tarafi_sislik; type=boolean; ask_if=meme_protezi == true`
- R Q11 → "Son aylarda kilonuzda belirgin bir değişiklik oldu mu?" [boolean] (either/or, as kalp Q8)
- PASS: Q1–Q5, Q7–Q10, Q12.

## D. Checklist

- **Instruments.** No PHQ-9, GAD-7, C-SSRS or WHO-5 item is reproduced, and no licence-BLOCKED
  instrument is referenced as content. Instrument-shadow items: ruh sağlığı Q3/Q4 (reworded above) and
  amatem Q4/Q5/Q7/Q8 (ASSIST; clinician decision).
- **Crisis.** No suicide or self-harm item in amatem, cematem or cocuk_ve_ergen_ruh_sagligi. All three
  leave crisis to `base.life_threat` + HB-C17.
- **Monotonicity.** No proposal adds, removes or relaxes a red flag. Nothing extends
  `base.life_threat`, and items marked "feeds `base.life_threat`" only capture a sign.
- **RED axes.** No RED rule is authored.
- **Sourcing holds.** adli_tip Q3/Q4; asi Q8; cocuk_gogus Q4; deri Q9; cocuk_nefro Q4; cocuk_uro Q10.
  Re-source before sign-off: cocuk_genetik Q9 (S3 LOW), agiz_dis_cene_radyolojisi S4 (finding 7),
  aile Q8 and cerrahi_onkoloji Q3 (finding 17).
- **Patient copy.** `siz` throughout, no digits. Spelled-out thresholds that stay in patient text are
  all sourced: JMF counts, "son bir ay" (HSGM), and "üç hafta" only if the oral-ulcer split is not
  adopted.
- **Jargon to remove or explain.** mekonyum, hidrokortizon, metabolik formül, karnitin, serebral
  palsi, oto-enjektör, apse, ağız tabanı, safra.
- **Goldens.** There are no rules, so there are no per-rule near-miss controls. The change process
  still applies to any regenerated candidate: `make safety`, CODEOWNER review, and the HB-C1 sign-off
  before L1.
