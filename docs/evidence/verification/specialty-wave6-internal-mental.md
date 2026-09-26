# Verification of the wave 6 specialty proposals (internal medicine + mental health) — awaiting-clinical-review

Reviewer: independent clinical-content verifier (challenger), 2026-09-26. Every clinical item here is `awaiting-clinical-review`; passing this review is not a physician signature. No clinical value was authored by the reviewer.

Scope: `docs/evidence/proposals/{gogus_hastaliklari, nefroloji, romatoloji, hematoloji, ruh_sagligi_ve_hastaliklari, klinik_psikoloji_poliklinigi, sigara_birakma_poliklinigi, obezite_poliklinigi}.md`.

Method: every question was parsed with `extract_questions` from `scripts/dev/gen_specialty_packs.py` (96 of 96 parse, 0 refusals) and run through the shipped Turkish PolicyGuard (`policy_guard_for(locale="tr")`, `inspect_sentence`). Every replacement text below went through the same guard and is clean. Source support was checked against each proposal's own §1 quotes; sources were not fetched again.

## BLUF

- **96 questions reviewed**: 8 reason-for-visit items and 88 pack items. Q1 passes in all eight files.
- **None of the 88 pack items has a `gen:` line.** All 88 would be emitted as opaque `soru_N` string slots, including 76 yes/no questions. 24 of them also need new text:

  | file | new text | gen line only |
  |---|---|---|
  | göğüs | 7 | 4 |
  | nefroloji | 0 | 11 |
  | romatoloji | 6 | 5 |
  | hematoloji | 3 | 8 |
  | ruh sağlığı | 2 | 9 |
  | klinik psikoloji | 2 | 9 |
  | sigara | 2 | 9 |
  | obezite | 2 | 9 |
  | **total** | **24** | **64** |

- **Breaches:**
  - One compound ask that PolicyGuard cannot detect (romatoloji Q5).
  - Three dependent items have no `ask_if`: sigara Q5 and obezite Q4 (already known), and ruh Q9 (found here). Göğüs Q7 assumed the patient had a symptom; it is reworded instead of gated.
  - Four items must be `text_first` under files/13 §13, but the generator cannot emit `delivery`, so they would be spoken aloud.
  - Two items collect non-alcohol substance use (ruh Q12, klinik Q11). That is a personal-data category with no inventory row, so CLAUDE.md requires stopping to ask a human.
  - Copyright:
    - Göğüs Q2–Q4 are the TTD page's own words.
    - Romatoloji Q4, Q6, Q7 and Q11 closely follow TRD booklet wording.
- **Copyright rewrites done:** 9 items reworded in our own words, one question each, with the clinical meaning kept and a clean guard result:
  - göğüs Q2, Q3, Q4
  - romatoloji Q4, Q5, Q6, Q7, Q10, Q11
- **Clean:**
  - No digits. The longest sentence is 14 words. No `sen` forms. PolicyGuard is clean on all 96 questions.
  - No triage level and no RED rule. Nothing extends `base.life_threat`: all eight L0 drafts extend `cluster.medical` or `cluster.mental_health`.
  - No PHQ-9, GAD-7, C-SSRS or WHO-5 item. No low-mood or loss-of-interest item. No suicide question.
  - PHQ-2 and GAD-2 are never called Turkish-validated, and the GAD-7 Turkish cut-off is stated correctly as 8.
- **Found in passing:** the guard's register arm rejects the everyday word *odun* ("wood"). This was verified directly and is routed to the HB-C23 lexicon owner.

## A. Findings

| where | finding | severity |
|---|---|---|
| all 8 files, 88 items | No `gen:` line. Every item becomes `soru_N` with `type: string`, so 76 yes/no answers are untyped and no slot has a meaningful id. This is the same defect wave 4–5 fixed elsewhere. | HIGH |
| göğüs Q2, Q3, Q4 | The patient copy is the TTD page's own self-check wording. The proposal's §4 gap 4 records that permission was not sought. Replaced with our own wording (§C). The three questions still follow the shape of a count-scored self-check, so the page's "three or more yes" advice must never be attached to them. | HIGH (IP) |
| romatoloji Q7, Q11 (near-verbatim); Q4, Q6 (close wording); Q5, Q10 (partial) | TRD booklets forbid quotation without the Society's permission. Replaced (§C). Q11 also named a condition to the patient and called the plaques white; it now describes only the white scale. | HIGH (IP) |
| romatoloji Q5 | Two claims share one answer: worse at rest, better with movement. A patient with only one of the two cannot answer, and the question assumes back pain. The guard does not catch this. Split into a gate question and two gated items. | HIGH (inv 2) |
| sigara Q5; obezite Q4 | Both depend on the previous item but have no `ask_if` (the proposals say so themselves). Once gated, sigara Q5 drops its "if you tried" lead-in. Obezite Q3 becomes a yes/no gate plus an open item. | HIGH |
| ruh Q12; klinik Q11; romatoloji Q9; hematoloji Q7 | files/13 §13 makes substance use and sexual or reproductive history `text_first`. The DSL has a `delivery` field (`dsl.py`), but the generator never emits it, and `_parse_gen` silently ignores keys it does not know. | HIGH |
| ruh Q12; klinik Q11 | Substance use beyond alcohol and tobacco carries criminal-law exposure. It is a personal-data category with no inventory annotation (invariant 18) and no HB row; CLAUDE.md makes a new category a stop-and-ask. Ruh Q12's "herhangi bir madde" (any substance) would also catch prescribed medicines, so it is reworded to "keyif verici bir madde" (recreational substance). Both items may stay in the review queue but must not be served until a human records the category. | HIGH (legal) |
| göğüs Q7 | The question assumes a symptom, and the possessive attaches to only one of its two nouns. Reworded to ask whether symptoms occur at night or early morning, so no gate is needed. The new wording also avoids the night-waking item shape used by asthma-control questionnaires. | MEDIUM |
| ruh Q9 | A yes/no answer to "was anything helpful?" loses what the source asks for: response to previous treatment. Now an open item, gated on Q8. | MEDIUM |
| hematoloji Q7 | The conditional lead-in stays because no slot can gate this item. Base has no sex or menstrual-status slot, and `lmp_date` is only asked when `pregnancy_status != 'hayir'`, so a gate on it would close for most women. The question particle is moved onto the verb. The missing slot is a gap for the base owner (HB-C6 family). | MEDIUM |
| göğüs Q12 | Assumes a bed partner ("yanınızda uyuyan"). Use obezite Q8's wording and the shared slot `tanikli_apne`. | MEDIUM |
| sigara, obezite | The generator's fixed `sikayet_suresi` question ("Bu şikâyetiniz ne zamandır var?") does not fit these clinics. In sigara it invites a number of smoking years (proposal gap 6, invariant 22). In obezite it frames weight as a complaint (O-S3 1.1.5). The generator needs a per-pack override or a way to leave it out (§D). | MEDIUM |
| göğüs Q9 / PolicyGuard | *odun* trips the `sen` register arm (verified: "Evde odun yaktınız mı?" returns REGISTER). Q9 follows GH-S1's own list and stays sourced, but patient copy is being bent around a guard false positive. Route to the lexicon owner (HB-C23) rather than working around it silently. | MEDIUM |
| romatoloji §1; göğüs §1 | Short provenance fragments are acceptable in an evidence file. No verbatim TRD snapshot may be committed until permission is recorded (romatoloji gap 2). No HB row exists for TTD or TRD permission; the owner must register one, because this review creates no ids. | MEDIUM |
| hematoloji Q2 | "çabuk yorulmuş hissediyor" is ungrammatical. Reuse the verified diyabet wording so both packs share one audio clip. | LOW |
| hematoloji Q6 | "kanamanız uzun sürdü mü" assumes the patient has had a procedure. Reworded. | LOW |
| göğüs Q5 / sigara Q3 | One concept with two wordings: göğüs asks "ever", sigara asks "recently" and leaves out spitting blood. Use one shared text and the slot `balgamda_kan`. | LOW |
| göğüs Q10 | "İşinizde" reads as the current job, but exposure relevant to COPD is lifetime. Base `occupation` already asks about the current job. | LOW |
| klinik Q2 | Putting the question particle on "hekim" assumes someone referred the patient. Now a neutral yes/no. It is routing information only and never an access or triage gate (proposal gap 2). | LOW |
| klinik Q12 | A yes/no answer without the preference itself. Now a yes/no item plus a gated open item. | LOW |
| obezite Q6 | The evidential-plus-converb construction ("durduramıyormuş gibi hissederek") is above B1, and "olur mu" can also be heard as "is that all right?". Simplified. | LOW |
| klinik Q10 | Cites "P-S4 (current lifestyle, sleep)", but klinik §1 quotes no such item. Re-cite to `ruh_sagligi_ve_hastaliklari.md` R-S5 1.2.7. | LOW |
| hematoloji Q8 | The source quote (H-S1) supports melena (black, tarry stool) but not fresh blood in the stool. | LOW |
| ruh Q4/Q5; klinik Q10 | These ask about sleep and appetite, which the PHQ-9 also covers. They are not the PHQ-9 items: there is no recall window and no frequency scale, and they ask about a change. Type them boolean and never score them or map them to PHQ-9. The proposal's "free-text" note should say boolean. | NOTE |
| ruh Q6; klinik Q5/Q6 | Together they cover work, daily responsibilities and relationships, which are the domains of the unscored difficulty item on PHQ-9 and GAD-7. The wording and answer form differ. Never map them to it. | NOTE |
| ruh Q11 | Resembles an item of a published mood-disorder screening questionnaire (a period of less need for sleep). The wording follows the TPD lay page (R-S4). The clinician should confirm. | NOTE |
| obezite Q8 (= göğüs Q12) | Witnessed breathing pauses in sleep is also an item on the sleep-apnoea screeners the proposal puts out of scope. Keep it as history and never build a score from pack answers. | NOTE |
| göğüs Q11, hematoloji Q11 | Capture the same fact as the base probe `rf_weight_loss_unintentional`, which cannot be asked today. Remove the duplicate once HB-C1 writes that probe. | NOTE |
| ruh Q3; klinik Q3 | Overlap the base slots `trajectory` and `patient_goals`. Drop them if the base history questions run in the same session. | NOTE |
| alarm inputs: göğüs Q5; nefroloji Q5; hematoloji Q4/Q5/Q8; romatoloji Q7/Q12; sigara Q3 | These answers reach the clinician note only; no rule acts on them (HB-C1, by design). Two have no `base.life_threat` rule at all: nefroloji Q5 (little or no urine) and romatoloji Q12 (possible giant-cell arteritis; BSR says same working day). That is for the `base.life_threat` owner and is not extended here (inv 7). | NOTE |
| sigara Q8; obezite Q12 | "ne kadar hazır" (how ready) may be answered with a number. That is acceptable in a string slot because it is not a clinical quantity. A choices list would be cleaner, but the generator has no `choices_tr`. | NOTE |
| `diyabet_tanisi` wording | Two versions are in use, with and without "(diyabet)". Nefroloji Q9 matches the göz version. Pick one audio clip for all packs. | NOTE |
| all 8 files | 0 digits, at most 14 words, 0 `sen` forms, guard-clean, exactly one "?" each. No `;`-joined asks, no "… mı ya da … mu?" and no when+how double asks. | PASS |
| all 8 files | No triage level and no RED rule. The generator writes only the stub rule, which carries the pending-value literal with `draft_needs_source` and is never compiled. Nothing extends or relaxes `base.life_threat`. | PASS |
| ruh, klinik | No instrument item, no PHQ-2 core item and no suicide question. The C-SSRS (HB-L2) and WHO-5 (HB-L3) blocks are stated correctly. Obezite correctly declines TEMD's PHQ-9 validity claim. | PASS |
| out of scope: `packages/protocols/review/specialty/amatem.yaml` | Several asks contain two questions, and three items follow the shape of the WHO ASSIST: past-three-months frequency, strong urge, and others' concern. Not in this wave; it needs its own verification. | observed |
| out of scope: base `alcohol_use` | Has no `delivery: text_first`, although files/13 §13 lists substance use. | observed |

## B. How to read §C

- Every non-Q1 item takes the `gen:` line shown, on its own line under the `> "…"` quote. Q1 needs none because it fills `basvuru_nedeni`.
- "text unchanged" means only the `gen:` line is added.
- A split item gets its own header in the order shown (`**Q5a — …**`, `**Q5b — …**`), each with its own quote and `gen:` line.
- `delivery=text_first` is required by files/13 §13, but the generator ignores it today (§D-1). Keep it in the line so it takes effect once D-1 lands.
- `ask_if` uses the closed gate grammar (`==`, `||`). Every slot it names sits earlier in the same pack.

## C. Replacement lists

### gogus_hastaliklari — 7 text, 4 gen only

- Q2 → "Günlerin çoğunda öksürüğünüz oluyor mu?" · `gen: slot=cogu_gun_oksuruk; type=boolean` (own wording)
- Q3 → "Günlerin çoğunda balgamınız oluyor mu?" · `gen: slot=cogu_gun_balgam; type=boolean` (own wording)
- Q4 → "Aynı yaştaki kişilerden daha çabuk nefes nefese kalıyor musunuz?" · `gen: slot=akranlardan_cabuk_nefes_darligi; type=boolean` (own wording)
- Q5 → "Son zamanlarda balgamınızda kan gördüğünüz ya da kan tükürdüğünüz oldu mu?" · `gen: slot=balgamda_kan; type=boolean` (same text as sigara Q3)
- Q6 text unchanged · `gen: slot=hisiltili_solunum; type=boolean`
- Q7 → "Gece veya sabaha karşı öksürük ya da nefes darlığı yaşıyor musunuz?" · `gen: slot=gece_sabah_solunum_sikayeti; type=boolean`
- Q8 text unchanged · `gen: slot=tetikleyici_uyaranlar; type=boolean`
- Q9 text unchanged · `gen: slot=biyokutle_dumani; type=boolean`
- Q10 → "Çalıştığınız işlerde uzun süre toz, duman ya da gaz soludunuz mu?" · `gen: slot=mesleki_toz_duman_gaz; type=boolean`
- Q11 text unchanged · `gen: slot=istemsiz_kilo_kaybi; type=boolean`
- Q12 → "Uyurken nefesinizin durduğunu fark eden biri oldu mu?" · `gen: slot=tanikli_apne; type=boolean` (same text as obezite Q8)
- Proposal prose: update the §3 intro sentence and §4 gap 4, because Q2–Q4 no longer reuse TTD wording. Keep the statement that no count rule is encoded.

### nefroloji — 0 text, 11 gen only

- Q2 · `gen: slot=ayak_goz_kapagi_sisligi; type=boolean`
- Q3 · `gen: slot=kopuklu_idrar; type=boolean`
- Q4 · `gen: slot=idrar_renk_degisikligi; type=boolean`
- Q5 · `gen: slot=idrar_miktari_azalmasi; type=boolean`
- Q6 · `gen: slot=gecmeyen_kasinti; type=boolean`
- Q7 · `gen: slot=istahsizlik_bulanti; type=boolean`
- Q8 · `gen: slot=yuksek_tansiyon_tanisi; type=boolean`
- Q9 · `gen: slot=diyabet_tanisi; type=boolean`
- Q10 · `gen: slot=bobrek_tasi_oykusu; type=boolean`
- Q11 · `gen: slot=ailede_bobrek_hastaligi; type=boolean` — family history is health data about third parties. It exports as narrative only (proposal gap 8), the same posture as the family-history items already in the review queue.
- Q12 · `gen: slot=duzenli_agri_kesici; type=boolean`

### romatoloji — 6 text, 5 gen only

- Q2 text unchanged · `gen: slot=eklem_sisligi; type=boolean`
- Q3 text unchanged · `gen: slot=kucuk_eklem_agri_sislik; type=boolean`
- Q4 → "Sabah uyandığınızda eklemlerinizde sertlik hissediyor musunuz?" · `gen: slot=sabah_eklem_sertligi; type=boolean` (own wording)
- Q5 → three items (own wording, one claim each):
  - Q5a "Belinizde ya da sırtınızda ağrı var mı?" · `gen: slot=bel_sirt_agrisi; type=boolean`
  - Q5b "Bu ağrı dinlendiğinizde artıyor mu?" · `gen: slot=bel_agrisi_dinlenince_artar; type=boolean; ask_if=bel_sirt_agrisi == true`
  - Q5c "Bu ağrı hareket ettiğinizde hafifliyor mu?" · `gen: slot=bel_agrisi_hareketle_azalir; type=boolean; ask_if=bel_sirt_agrisi == true`
- Q6 → "Sabah yataktan kalkıp yere bastığınızda topuğunuz ya da ayağınızın altı ağrıyor mu?" · `gen: slot=sabah_topuk_taban_agrisi; type=boolean` (own wording)
- Q7 → "Gözünüzün akında günlerce geçmeyen kızarıklık ya da ağrı oldu mu?" · `gen: slot=goz_akinda_kizariklik_agri; type=boolean` (own wording; sudden vision loss stays with base)
- Q8 text unchanged · `gen: slot=tekrarlayan_agiz_yarasi; type=boolean`
- Q9 text unchanged · `gen: slot=genital_agrili_yara; type=boolean; delivery=text_first`
- Q10 → "Ara ara gelen ve birkaç günde kendi kendine geçen ateşleriniz oluyor mu?" · `gen: slot=kendiliginden_gecen_ates; type=boolean` (own wording)
- Q11 → "Derinizde üzeri beyaz pullarla kaplı lekeler oldu mu?" · `gen: slot=pullu_deri_lekesi; type=boolean` (own wording; no condition named)
- Q12 text unchanged · `gen: slot=cignerken_cene_agrisi; type=boolean`
- Proposal prose: keep the §1 TRD fragments to the minimum. Gap 2 stands for any future snapshot.

### hematoloji — 3 text, 8 gen only

- Q2 → "Son zamanlarda kendinizi alışılmadık şekilde halsiz ya da yorgun hissediyor musunuz?" · `gen: slot=halsizlik_yorgunluk; type=boolean` (same text as diyabet)
- Q3 · `gen: slot=eforla_nefes_darligi; type=boolean`
- Q4 · `gen: slot=kolay_morarma; type=boolean`
- Q5 · `gen: slot=burun_dis_eti_kanamasi; type=boolean`
- Q6 → "Diş çekimi ya da ameliyat sonrasında uzun süren bir kanamanız oldu mu?" · `gen: slot=islem_sonrasi_uzun_kanama; type=boolean`
- Q7 → "Adet görüyorsanız, adet kanamanız çok fazla ya da uzun süreli oluyor mu?" · `gen: slot=yogun_uzun_adet_kanamasi; type=boolean; delivery=text_first` (no `ask_if` is possible; see §A)
- Q8 · `gen: slot=diskida_kan_siyah_renk; type=boolean`
- Q9 · `gen: slot=boyun_koltuk_kasik_sisligi; type=boolean`
- Q10 · `gen: slot=gece_terlemesi; type=boolean`
- Q11 · `gen: slot=istemsiz_kilo_kaybi; type=boolean`
- Q12 · `gen: slot=ailede_kan_hastaligi; type=boolean` (family history; same posture as nefroloji Q11)
- Q4–Q6 rest on a source about one rare disorder (H-S2; proposal gap 2). Keep them as symptom capture only and never build a bleeding score from them.

### ruh_sagligi_ve_hastaliklari — 2 text, 9 gen only

- Q2 · `gen: slot=baslangic_oncesi_zorlayici_olay; type=boolean` — boolean on purpose: it asks whether an event happened, not what happened, so no trauma narrative is drawn out.
- Q3 · `gen: slot=sikayet_seyri; type=string` (drop if base `trajectory` runs in the same session)
- Q4 · `gen: slot=uyku_duzeni_degisikligi; type=boolean`
- Q5 · `gen: slot=istah_degisikligi; type=boolean`
- Q6 · `gen: slot=islevsellik_etkilenimi; type=boolean`
- Q7 · `gen: slot=sosyal_destek; type=boolean`
- Q8 · `gen: slot=onceki_ruh_sagligi_destegi; type=boolean`
- Q9 → "Daha önce denediğiniz ilaç ya da yöntemlerden size en çok ne iyi geldi?" · `gen: slot=onceden_iyi_gelen; type=string; ask_if=onceki_ruh_sagligi_destegi == true`
- Q10 · `gen: slot=psikiyatrik_yatis_oykusu; type=boolean`
- Q11 · `gen: slot=yukselmis_duygudurum_donemi; type=boolean`
- Q12 → "Alkol ve sigara dışında keyif verici bir madde kullanıyor musunuz?" · `gen: slot=diger_madde_kullanimi; type=boolean; delivery=text_first` — review queue only; not servable until a human records the data category (§A).
- Proposal prose: the Q4 and Q5 notes should read "boolean history item; never scored, never mapped to a PHQ-9 item".

### klinik_psikoloji_poliklinigi — 2 text, 9 gen only

- Q2 → "Bu görüşmeye gelmeniz için bir hekim sizi yönlendirdi mi?" · `gen: slot=hekim_yonlendirmesi; type=boolean` (routing context only; never a gate for access or triage)
- Q3 · `gen: slot=beklenen_degisiklik; type=string`
- Q4 · `gen: slot=baslangic_oncesi_zorlayici_olay; type=boolean`
- Q5 · `gen: slot=islevsellik_etkilenimi; type=boolean`
- Q6 · `gen: slot=iliskilere_etki; type=boolean`
- Q7 · `gen: slot=basa_cikma_yollari; type=string`
- Q8 · `gen: slot=onceki_psikoterapi; type=boolean`
- Q9 · `gen: slot=psikiyatrik_ilac_kullanimi; type=boolean`
- Q10 · `gen: slot=uyku_duzeni_degisikligi; type=boolean` (re-cite to ruh R-S5 1.2.7)
- Q11 · `gen: slot=zorlanmada_madde_kullanimi; type=boolean; delivery=text_first` (same data-category hold as ruh Q12)
- Q12 → two items:
  - Q12a text unchanged · `gen: slot=kisisel_kulturel_tercih; type=boolean`
  - Q12b "Bu tercihinizi kısaca anlatır mısınız?" · `gen: slot=kisisel_kulturel_tercih_aciklama; type=string; ask_if=kisisel_kulturel_tercih == true`

### sigara_birakma_poliklinigi — 2 text, 9 gen only

- Q2 · `gen: slot=diger_tutun_nikotin_urunu; type=boolean`
- Q3 → "Son zamanlarda balgamınızda kan gördüğünüz ya da kan tükürdüğünüz oldu mu?" · `gen: slot=balgamda_kan; type=boolean` (same text as göğüs Q5)
- Q4 · `gen: slot=onceki_birakma_girisimi; type=boolean` — almost word for word the Ministry handbook's question (SB-S1). It is a short functional question, so the IP risk is low; recorded for completeness.
- Q5 → "Bırakmayı denediğinizde sizi en çok zorlayan şey neydi?" · `gen: slot=birakmayi_zorlastiran; type=string; ask_if=onceki_birakma_girisimi == true`
- Q6 · `gen: slot=onceki_birakma_yardimcisi; type=boolean`
- Q7 · `gen: slot=birakma_nedeni; type=string`
- Q8 · `gen: slot=birakmaya_hazirlik; type=string`
- Q9 · `gen: slot=sigara_istegini_artiran_durumlar; type=string`
- Q10 · `gen: slot=evde_sigara_icen; type=boolean`
- Q11 · `gen: slot=onceki_ruh_sagligi_hekim_destegi; type=boolean` (a different id from ruh Q8, because this item leaves out psychologists)
- Q12 · `gen: slot=nobet_oykusu; type=boolean`

### obezite_poliklinigi — 2 text, 9 gen only

- Q2 · `gen: slot=kilo_alma_donemi; type=string`
- Q3 → two items:
  - Q3a "Daha önce kilo vermeyi denediniz mi?" · `gen: slot=onceki_kilo_verme_denemesi; type=boolean`
  - Q3b current Q3 text unchanged · `gen: slot=kilo_verme_yontemleri; type=string; ask_if=onceki_kilo_verme_denemesi == true`
- Q4 text unchanged · `gen: slot=kilo_vermeyi_zorlastiran; type=string; ask_if=onceki_kilo_verme_denemesi == true`
- Q5 · `gen: slot=ogun_yeri; type=string`
- Q6 → "Kendinizi durduramadan kısa sürede çok fazla yediğiniz oluyor mu?" · `gen: slot=kontrolsuz_yeme; type=boolean`
- Q7 · `gen: slot=kendini_kusturma; type=boolean; delivery=text_first` — files/13 §13 does not require this. It is recommended because the proposal itself says the item may be better asked in person; the clinician may drop it.
- Q8 · `gen: slot=tanikli_apne; type=boolean`
- Q9 · `gen: slot=gunduz_istemsiz_uyuma; type=boolean`
- Q10 · `gen: slot=kilo_alimi_doneminde_yeni_ilac; type=boolean`
- Q11 · `gen: slot=duzenli_egzersiz; type=boolean`
- Q12 · `gen: slot=aliskanlik_degisimine_hazirlik; type=string`

## D. Generator changes before these eight are regenerated

1. **Emit `delivery`.** Read `delivery` from the `gen:` line (voice, text_first or text_only, validated) and refuse any key it does not know. Today a `delivery=` or a misspelt `ask_if` key is dropped without a warning.
2. **Check `ask_if` targets.** Confirm that every name in an `ask_if` is an earlier slot in the same pack or a declared base slot. Today an unknown name either fails the FHIR emit (`GATE_NOT_PROJECTABLE`) or never opens in the runtime plan, because a gate opens only on TRUE and an unknown slot evaluates UNKNOWN. Either way the question never appears; the generator should catch this when it writes the pack.
3. **Allow overriding `sikayet_suresi`.** Let a proposal replace or leave out the fixed duration question (needed for sigara and obezite).
4. **Optional: support `choices=`** for short closed answers (sigara Q8, obezite Q12).

Everything else in these eight files generates correctly: 96 of 96 parse and none is refused.

## E. Checklist

- **Instruments:** none reproduced or paraphrased. Construct overlaps are listed as NOTE rows in §A. Licence statements are correct (C-SSRS HB-L2, WHO-5 HB-L3, PHQ-2/GAD-2 not Turkish-validated, GAD-7 Turkish cut-off 8).
- **Monotonicity:** nothing is removed or relaxed, and nothing extends `base.life_threat`.
- **RED axes:** there are no RED rules.
- **Sourcing:** every item's cited source supports it, with the klinik Q10 and hematoloji Q8 caveats above. No rules are proposed.
- **Patient copy:** `siz` throughout, B1, no diagnosis, treatment or prognosis language, nothing alarming. Obezite never names the condition, and romatoloji Q11 no longer names one.
- **Copyright:** 9 rewrites (göğüs 3, romatoloji 6). No TTD or TRD sentence remains in patient copy.
- **Goldens:** there are no rules, so no per-rule near-miss controls are needed. `make safety` and CODEOWNER review still apply when the packs are regenerated.
