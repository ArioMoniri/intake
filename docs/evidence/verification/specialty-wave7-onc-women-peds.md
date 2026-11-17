# Verification of the wave 7 specialty proposals (oncology, women's health, paediatrics, genetics, immunology) and two hand-authored review packs — awaiting-clinical-review

Reviewer: independent clinical-content verifier (challenger), 2026-09-26. Every clinical item here is `awaiting-clinical-review`; passing this review is not a physician signature. No clinical value was authored by the reviewer.

Scope:

- `docs/evidence/proposals/{tibbi_onkoloji, radyasyon_onkolojisi, jinekolojik_onkoloji, nukleer_tip, gebe_poliklinigi, perinatoloji, ureme_endokrinolojisi_ve_infertilite, neonatoloji, gelisimsel_pediatri, sosyal_pediatri, tibbi_genetik, immunoloji_ve_alerji}.md`
- the hand-authored review packs `packages/protocols/review/specialty/{gastroenteroloji, noroloji}.yaml`. The generator never overwrites them (`eligible()` returns "hand-authored"), so every fix in §D is a hand edit.

Method:

- Every proposal was parsed with `extract_questions` and `extract_pack_options` from `scripts/dev/gen_specialty_packs.py`. 149 of 149 parse, 0 are refused, and `build_pack` succeeds for all 12.
- Every ask, follow-up and fixed generator text was run through the shipped Turkish PolicyGuard (`policy_guard_for(locale="tr")`, `inspect_sentence`), with a word count and a digit check.
- Both hand-authored packs were loaded as `ProtocolPack` and run through the validator's voice findings. Their slots were also checked against the compiler's openEHR binding rule (`compile/resolve.py`).
- Every replacement below was applied to scratch copies of the proposals, re-parsed and rebuilt with `build_pack` (base slots included), and guard-checked. All 12 rebuild, and every replacement text and follow-up is guard-clean, at most fifteen words per sentence, digit-free, and has exactly one question mark.
- Source support was checked against each proposal's own §1 quotes. Sources were not fetched again.

## BLUF

- **172 items reviewed.** That is 149 proposal questions (12 reason-for-visit items and 137 pack items) plus 23 slots in the two hand-authored packs. The two fixed texts the generator adds to every pack (the reason follow-up and the duration ask) were also checked for all 12 packs.
- **80 REVISE, 92 PASS.** 21 of the 80 are invariant-18 holds.

  | file | items | PASS | REVISE | of which hold | pack line |
  |---|---|---|---|---|---|
  | tibbi_onkoloji | 12 | 8 | 4 | 1 | — |
  | radyasyon_onkolojisi | 12 | 11 | 1 | 0 | — |
  | jinekolojik_onkoloji | 12 | 5 | 7 | 1 | — |
  | nukleer_tip | 12 | 7 | 5 | 1 | clinician wording needed |
  | gebe_poliklinigi | 12 | 4 | 8 | 0 | proposed |
  | perinatoloji | 12 | 6 | 6 | 0 | proposed |
  | ureme_endokrinolojisi_ve_infertilite | 12 | 2 | 10 | 1 | proposed (moves Q2) |
  | neonatoloji | 12 | 9 | 3 | 0 | proposed |
  | gelisimsel_pediatri | 13 | 8 | 5 | 2 | proposed |
  | sosyal_pediatri | 13 | 9 | 4 | 3 | proposed |
  | tibbi_genetik | 13 | 3 | 10 | 9 | clinician wording needed |
  | immunoloji_ve_alerji | 14 | 11 | 3 | 2 | — |
  | gastroenteroloji.yaml (hand) | 12 | 5 | 7 | 1 (remove) | n/a |
  | noroloji.yaml (hand) | 11 | 4 | 7 | 0 | n/a |
  | **total** | **172** | **92** | **80** | **21** | |

- **Breaches:**
  - **Two follow-ups invert their slot's polarity** (tibbi_onkoloji Q4, nukleer_tip Q9). A patient who says "evet" to the clarification is recorded as the opposite fact.
  - **Twenty new-category items carry no `hold=` (invariant 18)**:
    - family history of relatives: 10 items
    - consanguinity: 3
    - partner data: 3, including ureme Q12, which its own proposal says must not be generated before a human decides
    - household data: 4, including nukleer Q12, where a household member's pregnancy is third-party health data

    The hand-authored gastroenteroloji pack adds one more family-history slot, for 21 in all.
  - **25 items need `delivery=text_first` under files/13 §13 and lack it**: reproductive or sexual history, genital symptoms, pregnancy dating and lactation.
  - **Seven boolean slots rely on a follow-up to collect free-text detail**, which a boolean slot cannot store.
  - **Four dependent items have no usable gate**: perinatoloji Q8, gebe Q9, perinatoloji Q12, and noroloji `bas_agrisi_ates`.
  - **Both hand-authored packs:**
    - The validator refuses them: `MISSING_FOLLOW_UP_TR` on `basvuru_nedeni`.
    - All 23 of their slots would be refused by the compiler: `OPENEHR_BINDING_UNDECLARED`.
    - They carry three two-question asks (invariant 2).
    - They have one 19-word sentence (the noroloji thunderclap ask).
    - The guard flags `norolojik_tani` as DIAGNOSIS.
- **Duration ask:** the fixed "Bu şikâyetiniz ne zamandır var?" does not fit eight packs.
  - In the three paediatric packs it addresses the parent's own complaint.
  - In ureme it duplicates Q2.
  - For nükleer tıp and genetics no wording is sourced, so clinician wording is needed and the generator should allow the slot to be left out (§E).
- **Holds leave tibbi_genetik with Q1 and three items.** Family and partner history is the core of that clinic, so one owner decision on these data categories decides whether the pack is useful at all. The question for the owner is at the end of §A.
- **Clean:**
  - No digits, no `sen` forms, and at most fifteen words in every proposal sentence. PolicyGuard is clean on all 149 proposal asks as written.
  - Dates are `type=date`: the due date in both pregnancy files, the baby's date of birth, and the end of previous radiotherapy. The trying-to-conceive time is `type=duration`.
  - No triage level and no RED rule. Nothing extends `base.life_threat`: all twelve L0 drafts extend a `cluster.*` pack.
  - No GİDR, Denver II, ASQ, M-CHAT, Hunger Vital Sign, PHQ, GAD, ACT or ACQ item is reproduced. Immunology Q6 is the one exception by shape (§A).
  - Safeguarding and HEEADSSS are correctly not asked of the caregiver.
- **Found in passing (PolicyGuard defect):** in a question, a comma after any word beginning with *mi/mı/mu/mü* counts as a second question. Verified examples:
  - "Ailenizde mide, bağırsak ya da sindirim sistemi kanseri olan var mı?" → MULTI_QUESTION
  - "Mutfakta, evde ya da işte düştünüz mü?" → MULTI_QUESTION

  Route to the PolicyGuard owner (`_is_interrogative` prefix match; lexicon HB-C23).

## A. Findings

| where | finding | severity |
|---|---|---|
| tibbi_onkoloji Q4 | The ask means "can you do your own self-care?" (evet = independent). The follow-up means "do you need someone's help?" (evet = dependent). A follow-up is only a clarification of the same slot (files/04 §1; dsl.py `follow_up_tr`), so a yes to it records independence for a dependent patient. | HIGH |
| nukleer_tip Q9 | Same inversion. The ask "can you lie still?" gives evet = able. The follow-up "does lying flat cause pain or breathlessness?" gives evet = unable. Adopt radyasyon Q6's wording and slot, whose follow-up has the same polarity as its ask. | HIGH |
| ureme Q12 | Partner semen analysis. §4 gap 4 of the proposal says a human must decide before the item is generated, but the `gen:` line has no `hold=`, so the generator would emit it. | HIGH (inv 18) |
| 20 proposal items + gastroenteroloji `aile_gis_kanser` | New personal-data categories with no inventory annotation and no human decision (CLAUDE.md stop-and-ask; invariant 18). All need `hold=` (§C) or removal (§D). Where a gate is held, its dependants must be held too, or `build_pack` refuses the whole pack.<br>• **Relatives' health:** tibbi_onkoloji Q12; jinekolojik Q12; gelişimsel Q12; genetik Q5, Q6, Q11, Q12, Q13; immünoloji Q10, Q14<br>• **Consanguinity:** gelişimsel Q13; genetik Q7, Q8<br>• **Partner:** ureme Q12; genetik Q9, Q10 (genetik Q8 is also partner and marital data)<br>• **Household:** nukleer Q12; sosyal Q11, Q12, Q13 | HIGH (inv 18) |
| earlier waves | This rule was not applied in earlier verifications. Wave 6 kept nefroloji Q11 and hematoloji Q12 (family history), and wave 1–3 approved a consanguinity item in cocuk_metabolizma. One owner decision should cover every wave. INT-256 decision 13 (is family history a sensitive section?) is still open. No HB row exists for this; the owner must register one, because this review creates no ids. | HIGH (consistency) |
| jinekolojik Q2, Q3, Q4, Q5, Q10, Q11; gebe Q2, Q3, Q4, Q5, Q8, Q10; perinatoloji Q2, Q4, Q8; ureme Q2, Q3, Q4, Q5, Q8, Q9, Q10, Q11; nukleer Q3; gelişimsel Q5 | files/13 §13 makes sexual and reproductive history and pregnancy/LMP `text_first`. These items cover:<br>• menstrual status<br>• postmenopausal bleeding<br>• intercourse<br>• genital discharge or lesions<br>• cervical screening<br>• obstetric history, losses and caesarean<br>• fertility treatment<br>• pelvic infection<br>• the due date (the lmp_date analogue)<br>• lactation<br>• pregnancy health<br>The generator now emits `delivery` from the `gen:` line. Ureme Q2 moves into the pack's duration slot, which cannot carry `delivery` yet (§E-2). | HIGH |
| gebe Q4, Q6; perinatoloji Q5, Q8, Q9; ureme Q11; neonatoloji Q4 | Each boolean slot has a follow-up that asks for narrative ("…kısaca anlatır mısınız?", "…adını söyleyebilir misiniz?"). The proposals rely on it ("Free-text detail is captured by the follow-up only"), but the runtime uses a follow-up only on `clarification_needed` and writes the answer into the same boolean slot. The detail is lost. Split each into a boolean plus a gated string item. | MEDIUM |
| perinatoloji Q8 | Asks about losses in previous pregnancies with no gate on having had one. Add the shared `onceki_gebelik` gate (gebe Q3 wording). | MEDIUM |
| gebe Q9; perinatoloji Q12 | The conditional lead-in ("hissediyorsanız, …") makes "hayır" ambiguous: not yet felt, or no reduction. Split into a patient-reported gate and a gated item. The gestational threshold stays with the clinician (HB-C4). | MEDIUM |
| gelişimsel Q1; sosyal Q1 | The ask ends in "anlatır mısınız?", so the generator gives it the follow-up "Sizi hekime getiren en önemli şikâyetiniz nedir?", which addresses the parent's own complaint. End Q1 with "nedir?" so the neutral follow-up ("Bugünkü randevunuzun sebebini…") is used. | MEDIUM |
| neonatoloji, gelişimsel, sosyal (fixed `sikayet_suresi`) | "Bu şikâyetiniz ne zamandır var?" addresses the parent. Neonatoloji §4 gap 7 already noted this. A pack line is proposed in §C. | MEDIUM |
| gebe, perinatoloji (fixed `sikayet_suresi`) | A routine or referral antenatal visit has no complaint (gebe gap 7). Neutral pack lines are proposed in §C. They restate the fixed ask without "şikâyet" and carry no clinical content; the clinician confirms. | MEDIUM |
| ureme Q2 + `sikayet_suresi` | Two duration asks in one pack. Move the Q2 text into the pack line. It is sourced (UI-S1 rec 1.16.5, UI-S2, UI-S5), and the slot stays `type: duration`. It cannot be `text_first` until §E-2 lands. | MEDIUM |
| nukleer_tip; tibbi_genetik (`sikayet_suresi`) | These are preparation or counselling visits with no complaint, and no source supports a duration question. Clinician wording is needed; until then the fixed ask stays, and §E-2 should let a pack leave the slot out. Q1 is reworded so the follow-up no longer says "şikâyetiniz". | MEDIUM (nukleer Q1, genetik Q1: LOW) |
| neonatoloji Q11 | "uyandırması zor" is the wrong voice: it means *its waking someone*, not *being woken*. Reworded as one noun-phrase question. | MEDIUM |
| immünoloji Q6 | Night waking caused by cough or wheeze, answered yes/no, is the shape of the GINA symptom-control item and of the Asthma Control Test night-waking item, which is licensed. Wave 6 reworded göğüs Q7 for the same reason. Use the same wording and shared slot. | MEDIUM (instrument) |
| gastroenteroloji, noroloji `basvuru_nedeni` | A required slot without `follow_up_tr`. Verified: `_voice_findings` returns MISSING_FOLLOW_UP_TR for both. | HIGH |
| gastroenteroloji, noroloji (all 23 slots) | No slot carries `openehr_path` or `openehr_deferred_reason`, so `compile/resolve.py` refuses each one with OPENEHR_BINDING_UNDECLARED. | HIGH (blocks promotion) |
| gastroenteroloji `sikayet_suresi`, `kullanilan_ilaclar`; noroloji `sikayet_suresi` | Two question marks in one ask (invariant 2). The guard reports MULTI_QUESTION. The two `sikayet_suresi` asks repeat the generator defect wave 4–5 found; the generator has since been fixed, but these hand-authored copies never picked up the fix. `kullanilan_ilaclar` is a separate case. | HIGH |
| noroloji `ani_siddetli_bas_agrisi` | 19 words in one sentence (the guard reports JARGON through the length arm). The NG228 timing (S3: "within 1 to 5 minutes") is kept by moving it into a lead sentence. | MEDIUM |
| noroloji `bas_agrisi_ates` | "Baş ağrınıza ateş de eşlik ediyor mu?" assumes a headache that no earlier slot establishes. Reworded so that it does not. | MEDIUM |
| noroloji `norolojik_tani`; gastroenteroloji `sindirim_tanisi` | Yes/no questions typed `string`. The noroloji ask also trips the guard's DIAGNOSIS arm (verified) and uses "nörolojik". Split into a boolean plus a gated string item. | MEDIUM |
| noroloji, gastroenteroloji `kullanilan_ilaclar` | Duplicates base `meds_confirmed`, `meds_new_or_stopped` and `anticoagulant_use`. Remove it. Gastroenteroloji keeps an NSAID item, using nefroloji Q12's wording and slot. | LOW |
| noroloji `tek_tarafli_gucsuzluk` | "kolunuzun … tek tarafında" reads as *one side of your arm*. Reworded so that "one side" means one side of the body. | LOW |
| gastroenteroloji `kilo_kaybi`, `bagirsak_degisiklik` | "özellikle çabalamadığınız hâlde" is ambiguous; §D replaces it with the shared `istemsiz_kilo_kaybi` wording. The bowel item puts a parenthesis in spoken copy; the §D replacement drops it. | LOW |
| tibbi_onkoloji Q3, Q11; jinekolojik Q10; gelişimsel Q4 | The follow-up is not a restatement of the ask:<br>• Q3's focus particle assumes the patient rests.<br>• Q11 swaps "appetite or taste" for "eating less".<br>• Q10 swaps in different signs.<br>• Q4 gives a yes/no to a string slot.<br>Each follow-up is restated. | LOW |
| jinekolojik Q4 | "kanama olduğu oluyor mu" is clumsy. | LOW |
| ureme Q7 | "Hamile olmadığınız ya da emzirmediğiniz halde" lets a woman who is breastfeeding but not pregnant answer yes. The logic needs "and". | LOW |
| radyasyon Q5 | "…gibi bir cihaz" also takes in insulin pumps and other devices, but the slot is `kalp_cihazi`. | LOW |
| nukleer Q2, Q3 | Q2 should use the shared slot `diyabet_tanisi` (same text as nefroloji). Q3's "bebeğinizi" presumes a baby for every patient. There is no sex slot to gate on (HB-C6 family, as in wave 6 hematoloji Q7). | LOW |
| neonatoloji Q7 | Polarity is inverted and documented ("hayır" is the concern). Flip it so that every symptom slot in the pack means *true = concern*, and HB-C3 rule authors cannot mis-test it. | LOW |
| gebe Q2, perinatoloji Q2 | The follow-up "…bakabilir misiniz?" is a yes/no request that returns no date. | LOW |
| tibbi_onkoloji Q3, Q4 | ECOG grade descriptors (TO-S5, public domain) are captured as patient report only. Never compute an ECOG grade from them. | NOTE |
| jinekolojik Q6–Q9 | Bloating, early fullness, pelvic pain and urinary urgency are the constructs of a published ovarian symptom index. They carry no frequency or duration scale. Never score them. | NOTE |
| immünoloji Q13 | Jeffrey Modell warning signs (an awareness list). The counts stay out of patient copy. Never compute "two or more signs" from pack answers. | NOTE |
| gelişimsel Q3 | Close to the CDC checklist question in GP-S2. CDC material is US federal public domain and the checklist is not a validated screener. Acceptable. | NOTE |
| radyasyon Q6 (and nukleer Q9 after the fix) | The follow-up picks up breathlessness when lying flat. That is a clinical symptom, and it reaches the note only; no rule reads it (invariant 7). | NOTE |
| alarm inputs with no rule | These answers reach the clinician note only. Placement is for the base owner, and nothing is extended here (invariant 7).<br>• **Pregnancy set (HB-C4, which does not exist):** gebe Q8, Q9, Q11, Q12; perinatoloji Q11, Q12.<br>• **In no HB list at all:** gebe Q7 (hyperemesis) and Q10 (membranes); perinatoloji Q10 (preterm labour); neonatoloji Q8/Q9 (jaundice).<br>• **Paediatric set (HB-C3):** neonatoloji Q6, Q7, Q10, Q11, Q12.<br>• **Absent from `base.life_threat`:** the oncology emergencies (spinal cord compression, SVC obstruction, hypercalcaemia) and ovarian hyperstimulation (ureme). | NOTE |
| slot ids across packs | Optional, for sharing clips:<br>• gelişimsel Q7 `yenidogan_yogun_bakim` and neonatoloji `yogun_bakim_yatisi` are one fact under two ids.<br>• immünoloji Q5 could reuse göğüs `hisiltili_solunum` and its text.<br>• radyasyon Q7 and nukleer Q10 share `kapali_alan_huzursuzluk` with two different texts. | NOTE |
| neonatoloji Q2; proxy sessions | Q2 may duplicate the identity record (proposal gap 3). Base adult items (`pregnancy_status`, `lmp_date`) in a proxy session about a baby or child are a base-pack concern, not this wave's. | observed |
| all 12 proposals | 0 digits, at most 15 words per sentence, 0 `sen` forms, guard-clean, exactly one "?" each. No `;`-joined ask, no "… mı ya da … mu?" and no when+how ask. | PASS |
| all 12 proposals | No triage level and no RED rule. The generator writes only the stub rule, which carries the pending-value literal with `draft_needs_source` and is never compiled. Every draft extends `cluster.medical`, `cluster.womens_health` or `cluster.child_health`, and nothing extends `base.life_threat`. | PASS |
| gelişimsel, sosyal | No developmental screener item and no Hunger Vital Sign, ACE or caregiver-depression item. There is no abuse, neglect or safety question. HEEADSSS is left to the adolescent alone (SP-S2 Y33). This is consistent with files/13 §13 (safeguarding is `text_only` and nothing is extracted). | PASS |

**The owner's question (one sentence), for the legal/privacy owner with the physician of record (HB-C1):**

> May Önvizit persist, in the patient-owned record, (a) health facts about the patient's relatives, (b) consanguinity of the patient's parents or couple, (c) facts about a partner, and (d) household composition and economic facts — and if so, under which {category, purpose, basis, retention, recipients}?

Until the owner answers, every item listed above stays on hold. Holding an item does not delete it: its text stays in the proposal and it can be released by removing `hold=`.

## B. How to read §C

- Every item takes the `gen:` line shown, on its own line under its `> "…"` quote. Q1 takes none.
- "text unchanged" means only the `gen:` line changes. "follow-up only" means only the `follow_up=` value changes.
- A split item gets its own header in the order shown (`**Q4a — …**`, `**Q4b — …**`), each with its own quote and `gen:` line.
- A `pack:` line goes on its own line **inside §3**, before Q1. The generator only reads it inside the Candidate section, and its two texts must be one question each with no digit.
- `ask_if` uses `==` against a slot declared earlier in the same pack.
- A held gate holds its dependants too.
- Hold reasons contain no `;`.

## C. Replacement lists

### tibbi_onkoloji — 3 follow-ups, 1 hold

- Q3 follow-up only · `gen: slot=gunduz_yatakta_dinlenme; type=boolean; follow_up=Gün içinde çoğu zaman uzanıp dinlenmeniz gerekiyor mu?`
- Q4 follow-up only (polarity) · `gen: slot=kisisel_bakim_bagimsiz; type=boolean; follow_up=Yıkanma ve giyinmeyi kimseden yardım almadan yapabiliyor musunuz?`
- Q11 follow-up only · `gen: slot=istah_tat_degisiklik; type=boolean; follow_up=İştahınız ya da yemeklerin tadı eskisinden farklı mı?`
- Q12 text unchanged · `gen: slot=ailede_kanser_oykusu; type=boolean; hold=invariant 18 relatives health data category awaiting owner decision`
- PASS: Q1, Q2, Q5, Q6, Q7, Q8, Q9, Q10.

### radyasyon_onkolojisi — 1 text

- Q5 → "Vücudunuzda kalp pili ya da şok cihazı takılı mı?" · `gen: slot=kalp_cihazi; type=boolean; follow_up=Göğsünüzde deri altına takılmış bir kalp cihazı var mı?`
- PASS: Q1, Q2, Q3, Q4, Q6, Q7, Q8, Q9, Q10, Q11, Q12.

### jinekolojik_onkoloji — 1 text, 1 follow-up, 6 delivery, 1 hold

- Q2 text unchanged · `gen: slot=adet_kesildi; type=boolean; follow_up=Menopoza girdiniz mi?; delivery=text_first`
- Q3 text unchanged · `gen: slot=menopoz_sonrasi_kanama; type=boolean; ask_if=adet_kesildi == true; follow_up=Menopozdan sonra az da olsa kan gördünüz mü?; delivery=text_first`
- Q4 → "Cinsel ilişki sırasında ya da sonrasında kanamanız oluyor mu?" · `gen: slot=iliski_sonrasi_kanama; type=boolean; follow_up=İlişkiden sonra lekelenme fark ettiğiniz oldu mu?; delivery=text_first`
- Q5 text unchanged · `gen: slot=anormal_akinti; type=boolean; follow_up=Akıntınızın renginde ya da kokusunda bir değişiklik var mı?; delivery=text_first`
- Q10 text unchanged · `gen: slot=dis_genital_bulgu; type=boolean; follow_up=Genital bölgenin dış kısmında uzun süredir geçmeyen kaşıntı, yara ya da şişlik var mı?; delivery=text_first`
  - The source's colour change and lump (JO-S4) leave the follow-up. The clinician may add them as their own item.
- Q11 text unchanged · `gen: slot=rahim_agzi_tarama; type=boolean; follow_up=Rahim ağzından hücre alınan bir tarama testi yaptırdınız mı?; delivery=text_first`
- Q12 text unchanged · `gen: slot=ailede_jinekolojik_kanser; type=boolean; hold=invariant 18 relatives health data category awaiting owner decision`
- PASS: Q1, Q6, Q7, Q8, Q9.

### nukleer_tip — 3 text, 1 slot id, 1 hold; duration: clinician wording needed

- Q1 → "Bugün nükleer tıp polikliniğine gelme nedeniniz nedir?" (no `gen:`; the "nedir?" ending selects the neutral follow-up)
- Q2 text unchanged · `gen: slot=diyabet_tanisi; type=boolean; follow_up=Kan şekerinizin yüksek olduğu size söylendi mi?`
- Q3 → "Şu anda emziriyor musunuz?" · `gen: slot=emzirme; type=boolean; follow_up=Şu anda bir bebeği anne sütüyle besliyor musunuz?; delivery=text_first`
- Q9 → "Bir süre sırtüstü ve hareketsiz yatmak sizin için zor olur mu?" · `gen: slot=hareketsiz_yatma_zorlugu; type=boolean; follow_up=Sırtüstü yatınca ağrı ya da nefes darlığı oluyor mu?`
  - Same text and slot as radyasyon Q6. NT-S1 still supports it. Delete the proposal's "evet means able" note.
- Q12 text unchanged · `gen: slot=evde_cocuk_gebe; type=boolean; hold=invariant 18 household data category awaiting owner decision`
  - NT-S2 asks that radiation-safety information be *given*. That can be given to every therapy patient without asking about who is in the household.
- Duration: no source supports a duration question for a scan or therapy visit. Clinician wording needed, or leave the slot out once §E-2 lands.
- PASS: Q4, Q5, Q6, Q7, Q8, Q10, Q11.

### gebe_poliklinigi — 3 splits, 1 follow-up, 6 delivery, pack line

- Pack line: `pack: duration_ask=Bu konu ne zamandır devam ediyor?; duration_follow_up=Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?`
  - A neutral restatement of the fixed ask; the clinician confirms.
- Q2 follow-up · `gen: slot=tahmini_dogum_tarihi; type=date; follow_up=Ultrason raporunuzdaki tahmini doğum tarihini söyler misiniz?; delivery=text_first`
- Q3 text unchanged · `gen: slot=onceki_gebelik; type=boolean; delivery=text_first`
- Q4 → two items:
  - Q4a text unchanged · `gen: slot=onceki_gebelik_sorunu; type=boolean; ask_if=onceki_gebelik == true; delivery=text_first`
  - Q4b "Yaşadığınız sorunu kısaca anlatır mısınız?" · `gen: slot=onceki_gebelik_sorunu_aciklama; type=string; ask_if=onceki_gebelik_sorunu == true; delivery=text_first`
- Q5 text unchanged · `gen: slot=rahim_ameliyati; type=boolean; delivery=text_first`
- Q6 → two items:
  - Q6a text unchanged · `gen: slot=suregelen_saglik_sorunu; type=boolean`
  - Q6b "Bu sağlık sorununun adını söyleyebilir misiniz?" · `gen: slot=suregelen_saglik_sorunu_adi; type=string; ask_if=suregelen_saglik_sorunu == true`
- Q8 text unchanged · `gen: slot=gebelikte_kanama; type=boolean; delivery=text_first`
- Q9 → two items:
  - Q9a "Bebeğinizin hareketlerini hissetmeye başladınız mı?" · `gen: slot=bebek_hareketi_hissediliyor; type=boolean`
  - Q9b "Son günlerde bebeğinizin hareketlerinde azalma oldu mu?" · `gen: slot=bebek_hareketlerinde_azalma; type=boolean; ask_if=bebek_hareketi_hissediliyor == true`
- Q10 text unchanged · `gen: slot=su_gelmesi; type=boolean; delivery=text_first`
- PASS: Q1, Q7, Q11, Q12.
- Section-level `text_first` (13 §13 allows it per section) may be simpler for this whole pack. That is the owner's choice. The generator is per-slot only.

### perinatoloji — 4 splits (one adds a gate), 1 follow-up, 3 delivery, pack line

- Pack line: `pack: duration_ask=Bu durumu ne zamandır biliyorsunuz?; duration_follow_up=Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?`
  - Neutral: it asks how long the referral reason has been known. The clinician confirms.
- Q2 follow-up · `gen: slot=tahmini_dogum_tarihi; type=date; follow_up=Ultrason raporunuzdaki tahmini doğum tarihini söyler misiniz?; delivery=text_first`
- Q4 text unchanged · `gen: slot=tedavi_yardimiyla_gebelik; type=boolean; delivery=text_first`
- Q5 → two items:
  - Q5a text unchanged · `gen: slot=gebelik_oncesi_saglik_sorunu; type=boolean`
  - Q5b "Bu sorunun adını söyleyebilir misiniz?" · `gen: slot=gebelik_oncesi_saglik_sorunu_adi; type=string; ask_if=gebelik_oncesi_saglik_sorunu == true`
- Q8 → three items:
  - Q8a "Bu gebelikten önce hiç hamile kaldınız mı?" · `gen: slot=onceki_gebelik; type=boolean; delivery=text_first` (same text as gebe Q3)
  - Q8b text unchanged · `gen: slot=onceki_gebelik_kaybi; type=boolean; ask_if=onceki_gebelik == true; delivery=text_first`
  - Q8c "İsterseniz bunu kısaca anlatır mısınız?" · `gen: slot=onceki_gebelik_kaybi_aciklama; type=string; ask_if=onceki_gebelik_kaybi == true; delivery=text_first`
- Q9 → two items:
  - Q9a text unchanged · `gen: slot=ultrason_bulgusu; type=boolean`
  - Q9b "Size söylenenleri kısaca anlatır mısınız?" · `gen: slot=ultrason_bulgusu_aciklama; type=string; ask_if=ultrason_bulgusu == true`
- Q12 → two items, the same as gebe Q9a/Q9b (same texts and slots):
  - Q12a "Bebeğinizin hareketlerini hissetmeye başladınız mı?" · `gen: slot=bebek_hareketi_hissediliyor; type=boolean`
  - Q12b "Son günlerde bebeğinizin hareketlerinde azalma oldu mu?" · `gen: slot=bebek_hareketlerinde_azalma; type=boolean; ask_if=bebek_hareketi_hissediliyor == true`
- PASS: Q1, Q3, Q6, Q7, Q10, Q11.
- Proposal prose: §4 gap 5 is resolved as `text_first`. The distress-routing question stays with the clinician.

### ureme_endokrinolojisi_ve_infertilite — Q2 moves, 1 text, 1 split, 7 delivery, 1 hold

- Pack line (replaces Q2): `pack: duration_ask=Ne zamandır korunmadan gebe kalmayı deniyorsunuz?; duration_follow_up=Ay ya da yıl olarak yaklaşık söyleyebilir misiniz?`
  - Delete Q2 from §3. Its sources move with it.
  - It should be `text_first` and cannot be until §E-2 lands, so do not promote the pack before then.
- Q3 text unchanged · `gen: slot=adet_duzenli; type=boolean; delivery=text_first`
- Q4 text unchanged · `gen: slot=agrili_adet; type=boolean; delivery=text_first`
- Q5 text unchanged · `gen: slot=iliski_sirasinda_agri; type=boolean; delivery=text_first`
- Q7 → "Emzirmediğiniz ve hamile olmadığınız halde memenizden süt geliyor mu?" · `gen: slot=memeden_sut_gelmesi; type=boolean`
- Q8 text unchanged · `gen: slot=onceki_gebelik; type=boolean; delivery=text_first`
- Q9 text unchanged · `gen: slot=dusuk_ya_da_dis_gebelik; type=boolean; ask_if=onceki_gebelik == true; delivery=text_first`
- Q10 text unchanged · `gen: slot=pelvik_iltihap; type=boolean; delivery=text_first`
- Q11 → two items:
  - Q11a text unchanged · `gen: slot=onceki_tedavi; type=boolean; delivery=text_first`
  - Q11b "Hangi tedavileri gördüğünüzü kısaca anlatır mısınız?" · `gen: slot=onceki_tedavi_aciklama; type=string; ask_if=onceki_tedavi == true; delivery=text_first`
- Q12 text unchanged · `gen: slot=partner_sperm_tahlili; type=boolean; hold=invariant 18 partner data category awaiting owner decision`
- PASS: Q1, Q6.

### neonatoloji — 2 text, 1 split, pack line

- Pack line: `pack: duration_ask=Bu durumu ne zamandır fark ediyorsunuz?; duration_follow_up=Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?`
  - Addressed to the parent and about the baby (gap 7).
- Q4 → two items:
  - Q4a text unchanged · `gen: slot=yogun_bakim_yatisi; type=boolean`
  - Q4b "Yoğun bakımda neden yattığını kısaca anlatır mısınız?" · `gen: slot=yogun_bakim_nedeni; type=string; ask_if=yogun_bakim_yatisi == true`
- Q7 → "Bebeğinizin bezi her zamankinden daha seyrek mi ıslanıyor?" · `gen: slot=islak_bez_azalmasi; type=boolean`
  - The polarity is now *true = concern*. Update §2.2 and the Q7 note, because an HB-C3 rule now tests `== true`.
- Q11 → "Bebeğinizde her zamankinden fazla uyku hali ya da uyanmakta zorlanma var mı?" · `gen: slot=asiri_uykululuk; type=boolean`
- PASS: Q1, Q2, Q3, Q5, Q6, Q8, Q9, Q10, Q12. "Bebeğiniz" is used consistently.

### gelisimsel_pediatri — 1 text, 1 follow-up, 1 delivery, 2 holds, pack line

- Pack line: `pack: duration_ask=Bu durumu ne zamandır fark ediyorsunuz?; duration_follow_up=Ay ya da yıl olarak yaklaşık söyleyebilir misiniz?`
- Q1 → "Çocuğunuzu bugün gelişimsel pediatri polikliniğine getiren konu nedir?" (no `gen:`)
- Q4 follow-up only · `gen: slot=kaybedilen_beceri; type=string; ask_if=beceri_kaybi == true; follow_up=Konuşma, yürüme ya da oyun gibi hangi beceride değişiklik oldu?`
- Q5 text unchanged · `gen: slot=gebelikte_saglik_sorunu; type=boolean; delivery=text_first`
  - This is pregnancy history, and the respondent is often the mother.
- Q12 text unchanged · `gen: slot=ailede_gelisim_gecikmesi; type=boolean; hold=invariant 18 relatives health data category awaiting owner decision`
- Q13 text unchanged · `gen: slot=anne_baba_akrabaligi; type=boolean; delivery=text_first; hold=invariant 18 family consanguinity category awaiting owner decision`
- PASS: Q2, Q3, Q6, Q7, Q8, Q9, Q10, Q11. "Çocuğunuz" is used consistently.

### sosyal_pediatri — 1 text, 3 holds, pack line

- Pack line: `pack: duration_ask=Bu konu ne zamandır devam ediyor?; duration_follow_up=Hafta ya da ay olarak yaklaşık söyleyebilir misiniz?`
- Q1 → "Çocuğunuzu bugün sosyal pediatri polikliniğine getiren konu nedir?" (no `gen:`)
- Q11 text unchanged · `gen: slot=temel_ihtiyac_zorlugu; type=boolean; delivery=text_first; hold=invariant 18 household data category awaiting owner decision`
- Q12 text unchanged · `gen: slot=temel_ihtiyac_destegi; type=boolean; ask_if=temel_ihtiyac_zorlugu == true; delivery=text_first; hold=invariant 18 household data category awaiting owner decision`
- Q13 text unchanged · `gen: slot=ailede_onemli_degisiklik; type=boolean; hold=invariant 18 household data category awaiting owner decision`
- PASS: Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q9, Q10.
- Proposal §4 gap 5 already names this decision. The `gen:` lines now encode it.

### tibbi_genetik — 1 text, 9 holds; duration: clinician wording needed

- Q1 → "Bugün sizi tıbbi genetik polikliniğine getiren konu nedir?" (no `gen:`)
- Q5 text unchanged · `gen: slot=ailede_genetik_hastalik; type=boolean; hold=invariant 18 relatives health data category awaiting owner decision`
- Q6 text unchanged · `gen: slot=ailedeki_hastalik_adi; type=string; ask_if=ailede_genetik_hastalik == true; follow_up=Adını bilmiyorsanız nasıl bir sorun olduğunu anlatır mısınız?; hold=invariant 18 relatives health data category awaiting owner decision`
- Q7 text unchanged · `gen: slot=anne_baba_akrabaligi; type=boolean; delivery=text_first; hold=invariant 18 family consanguinity category awaiting owner decision`
- Q8 text unchanged · `gen: slot=es_akrabaligi; type=boolean; delivery=text_first; hold=invariant 18 partner data category awaiting owner decision`
  - Also presumes a spouse. A gate on marital status would itself be a new category.
- Q9 text unchanged · `gen: slot=evlilik_oncesi_tasiyicilik; type=boolean; delivery=text_first; hold=invariant 18 partner data category awaiting owner decision`
  - "siz ya da eşiniz" also leaves unclear whose result it is.
- Q10 text unchanged · `gen: slot=tekrarlayan_gebelik_kaybi; type=boolean; delivery=text_first; hold=invariant 18 partner data category awaiting owner decision`
- Q11 text unchanged · `gen: slot=ailede_dogustan_sorun; type=boolean; hold=invariant 18 relatives health data category awaiting owner decision`
- Q12 text unchanged · `gen: slot=ailede_erken_kanser; type=boolean; hold=invariant 18 relatives health data category awaiting owner decision`
- Q13 text unchanged · `gen: slot=ailede_ani_aciklanamayan_kayip; type=boolean; hold=invariant 18 relatives health data category awaiting owner decision`
- Duration: clinician wording needed, or leave the slot out once §E-2 lands.
- PASS: Q2, Q3, Q4. The emitted pack is Q1 plus these three until the owner decides (§A).

### immunoloji_ve_alerji — 1 text, 2 holds

- Q6 → "Gece veya sabaha karşı öksürük ya da nefes darlığı yaşıyor musunuz?" · `gen: slot=gece_sabah_solunum_sikayeti; type=boolean`
  - Same text and slot as wave 6 göğüs Q7. IA-S2 ("Uykudan uyandıran öksürük ve hışıltı") still supports the night-time construct.
- Q10 text unchanged · `gen: slot=ailede_sislik_ataklari; type=boolean; ask_if=sislik_ataklari == true; hold=invariant 18 relatives health data category awaiting owner decision`
- Q14 text unchanged · `gen: slot=ailede_bagisiklik_yetmezligi; type=boolean; ask_if=tekrarlayan_enfeksiyon == true; hold=invariant 18 relatives health data category awaiting owner decision`
- PASS: Q1, Q2, Q3, Q4, Q5, Q7, Q8, Q9, Q11, Q12, Q13.
- Q12 assumes a past sting. A patient who has never been stung answers no, so it is acceptable without a gate.

## D. Hand-authored packs — exact YAML edits

Both files are hand edits.

**Every slot in both packs** also needs `openehr_deferred_reason`, or the compiler refuses it (OPENEHR_BINDING_UNDECLARED). Use the generator's form, built by `_deferred_reason(slug, archetype)` with the archetype that `docs/evidence/proposals/<slug>.md` lists for that item:

> INT-032: openEHR binding deferred to the P3 export; candidate archetype <root> recorded in docs/evidence/proposals/<slug>.md

### gastroenteroloji.yaml — 7 REVISE, of which 1 is removed

- `basvuru_nedeni`: keep `ask_tr` and add the follow-up.
  ```yaml
        follow_up_tr:
          tr: Sizi hekime getiren en önemli şikâyetiniz nedir?
  ```
- `sikayet_suresi`: replace both texts.
  ```yaml
        ask_tr:
          tr: Bu şikâyetiniz ne zamandır var?
        follow_up_tr:
          tr: Gün, hafta ya da ay olarak yaklaşık söyleyebilir misiniz?
  ```
- `kilo_kaybi` → rename the slot to `istemsiz_kilo_kaybi`, the shared id used by göğüs Q11 and hematoloji Q11.
  ```yaml
        ask_tr:
          tr: Son aylarda istemeden kilo kaybettiniz mi?
  ```
- `bagirsak_degisiklik`:
  ```yaml
        ask_tr:
          tr: Son zamanlarda dışkılama düzeninizde ishal ya da kabızlık gibi bir değişiklik oldu mu?
  ```
- `kullanilan_ilaclar` → delete the slot, because base covers medicines and blood thinners. Add the NSAID item in its place, with nefroloji Q12's wording and slot:
  ```yaml
      duzenli_agri_kesici:
        type: boolean
        required: false
        ask_tr:
          tr: Ağrı kesici ilaçları sık ya da uzun süre kullanıyor musunuz?
  ```
- `sindirim_tanisi` → make it boolean and add a gated string slot.
  - The organ order avoids the guard's comma-after-"mide" defect (§A). The defect is routed to the guard owner, not hidden.
  ```yaml
      sindirim_tanisi:
        type: boolean
        required: false
        ask_tr:
          tr: Daha önce karaciğeriniz, bağırsağınız ya da midenizle ilgili size bir hastalık tanısı konuldu mu?
      sindirim_tanisi_adi:
        type: string
        required: false
        ask_if: "sindirim_tanisi == true"
        ask_tr:
          tr: Bu hastalığın adını söyleyebilir misiniz?
  ```
- `aile_gis_kanser` → remove it from the pack. This is the hand-authored equivalent of `hold=`: the invariant 18 relatives-health category, the same owner decision as §A. It also trips the guard defect ("mide,"). Keep the text in `docs/evidence/proposals/gastroenteroloji.md`.
- PASS: `disfaji`, `hematemez_melena`, `rektal_kanama`, `sarilik`, `inatci_kusma`.

### noroloji.yaml — 7 REVISE

- `basvuru_nedeni`: keep `ask_tr` and add the follow-up.
  ```yaml
        follow_up_tr:
          tr: Sizi hekime getiren en önemli şikâyetiniz nedir?
  ```
- `sikayet_suresi`:
  ```yaml
        ask_tr:
          tr: Bu şikâyetiniz ne zamandır var?
        follow_up_tr:
          tr: Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?
  ```
- `tek_tarafli_gucsuzluk`:
  ```yaml
        ask_tr:
          tr: Yüzünüzde, kolunuzda ya da bacağınızda, yalnızca bir tarafta güçsüzlük veya uyuşma oldu mu?
  ```
- `ani_siddetli_bas_agrisi`: two sentences and one question, with 13 and 11 words. The S3 timing is kept.
  ```yaml
        ask_tr:
          tr: Bazı baş ağrıları saniyeler ya da birkaç dakika içinde en şiddetli hâline ulaşır. Hiç böyle ani ve çok şiddetli bir baş ağrınız oldu mu?
  ```
- `bas_agrisi_ates`:
  ```yaml
        ask_tr:
          tr: Son zamanlarda ateşle birlikte baş ağrınız oldu mu?
  ```
- `kullanilan_ilaclar` → delete the slot (base `meds_confirmed` and `meds_new_or_stopped` cover it).
- `norolojik_tani` → make it boolean and add a gated string slot. The replacement is guard-clean and has no "nörolojik".
  ```yaml
      norolojik_tani:
        type: boolean
        required: false
        ask_tr:
          tr: Daha önce size inme ya da sara gibi bir sinir sistemi hastalığı tanısı konuldu mu?
      norolojik_tani_adi:
        type: string
        required: false
        ask_if: "norolojik_tani == true"
        ask_tr:
          tr: Bu hastalığın adını söyleyebilir misiniz?
  ```
- PASS: `konusma_guclugu`, `nobet_bilinc_kaybi`, `ani_gorme_kaybi`, and `baslangic_sekli`.
  - `baslangic_sekli` is an either/or question ("aniden mi yoksa … yavaş yavaş mı"), not two questions. The base `subject_role` uses the same shape.
  - A code slot with `choices_tr` would constrain the answer, but it needs a valueset. That is optional.

## E. Generator changes (scripts/dev/gen_specialty_packs.py)

1. **`reason_follow_up` pack key.** Today the Q1 follow-up is chosen by whether the ask ends in "nedir?". That forced four Q1 rewrites here (two of them parent-addressed). An explicit key, or a parent-addressed default for `cluster.child_health`, removes the suffix rule.
2. **Duration slot options.** Two pack keys are needed:
   - `duration=omit`, for genetics and nükleer tıp and optionally for routine antenatal and newborn visits.
   - `duration_delivery=text_first`, for ureme, whose duration is reproductive history.

   Both are validated the way `delivery` is.
3. **Refuse a narrative follow-up on a boolean slot.** A boolean slot's `follow_up` must restate the question. One that ends in "anlatır mısınız?" or asks for a name is mechanically detectable, and it caught seven items here.
4. **Name the held gate.** When a dependant's `ask_if` reads a held slot, `build_pack` already refuses the pack (fails closed). The message should say that the gate is held rather than "undeclared".
5. **Validate the review tree in CI**, including hand-authored packs. `MISSING_FOLLOW_UP_TR` and OPENEHR_BINDING_UNDECLARED on gastroenteroloji and noroloji go unseen today because those files are neither generated nor validated.

## F. Checklist

- **Instruments:** none reproduced.
  - Immünoloji Q6 has the shape of a night-waking item and is reworded (§C).
  - The ECOG, ovarian-symptom and Jeffrey Modell constructs are NOTE rows: capture them, never score them.
  - GİDR, Denver II, ASQ, M-CHAT, the Hunger Vital Sign and ACE items are absent.
- **Monotonicity:** nothing is removed or relaxed, and nothing extends `base.life_threat`. Alarm items are inputs only; they feed HB-C3, HB-C4 or nothing, as listed in §A.
- **RED axes:** there are no RED rules.
- **Sourcing:** every kept item is supported by its proposal's §1. Items that rest on weaker sources (PR-S4 and GP-S4 lay pages; TG-S4 news item; radyasyon Q7's cross-specialty support) are flagged in their proposals and stay CANDIDATE. No rule is proposed.
- **Patient copy:**
  - `siz` throughout, at most B1, one question per turn after the §D fixes, nothing alarming.
  - Cancer is named only in items that are now held.
  - Parent address is consistent once the §C pack lines and Q1 rewrites land.
- **Invariant 22:** no numerals. Every date is `type=date`, and the trying-to-conceive time is `type=duration`.
- **Invariant 18:** 21 items are held or removed pending one owner decision (§A). Every slot that is emitted still needs its inventory annotation at promotion, as in every wave.
- **Goldens:** there are no rules, so no near-miss controls are needed. `make safety` and CODEOWNER review still apply when the packs are regenerated or edited.
