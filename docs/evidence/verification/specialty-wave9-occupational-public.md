# Verification of the wave 9 specialty proposals (occupational, fitness, public-health and administrative clinics) — awaiting-clinical-review

Reviewer: independent clinical-content verifier (challenger), 2026-09-26. Every clinical item here is `awaiting-clinical-review`; passing this review is not a physician signature. No clinical value was authored by the reviewer.

Scope:

- `docs/evidence/proposals/{is_ve_meslek_hastaliklari, hava_ve_uzay_hekimligi, sualti_ve_hiperbarik_tip, spor_hekimligi, halk_sagligi, saglik_kurulu, hemsirelik_egitim_poliklinikleri, getat, tibbi_ekoloji_ve_hidroklimatoloji, odyoloji}.md`
- None of the ten has a review pack yet (`packages/protocols/review/specialty/<slug>.yaml` is absent), so every fix below lands in the proposal and takes effect on the next generator run.

Method:

- Every proposal was parsed with `extract_questions` and `extract_pack_options` from `scripts/dev/gen_specialty_packs.py`. 116 of 127 drafted items parse; the other 11 carry `hold=`. `build_pack` (base slots included) succeeds for all ten.
- Every ask, follow-up and fixed generator text was run through the shipped Turkish PolicyGuard (`policy_guard_for(locale="tr")`, `inspect_sentence`), with a word count and a digit check. The 11 held texts were checked the same way.
- Every replacement below was applied to scratch copies of the proposals, re-parsed and rebuilt with `build_pack`, and guard-checked. All ten rebuild. Every replacement ask and follow-up is guard-clean, at most fifteen words per sentence, digit-free, and has exactly one question mark.
- Source support was checked against each proposal's own §1 quotes. In addition, eight source pages were fetched again as a spot check (results in §F).
- Owner decision D3 (`docs/evidence/verification/owner-decisions-2026-09-26.md`) was applied: the sensitive-data categories it lists are no longer held; each such item is `delivery=text_first` and needs its data-inventory row under INT-349. Holds for a missing source, a legal boundary or a duplicate stay.

## BLUF

- **127 items reviewed**: 10 reason-for-visit items and 117 pack items. The two fixed texts the generator adds to every pack (the reason follow-up and the duration ask) were also checked for all ten.
- **47 REVISE, 80 PASS.** Eight held items are released under D3. Seven items are held after review (six for a missing source or a legal boundary, one as a duplicate), plus one new held split.

  | file | items | PASS | REVISE | released (D3) | held after review | duration ask |
  |---|---|---|---|---|---|---|
  | is_ve_meslek_hastaliklari | 18 | 3 | 15 | 5 | 0 | fixed ask kept |
  | hava_ve_uzay_hekimligi | 15 | 10 | 5 | 0 | 1 (legal) | clinician wording or omit |
  | sualti_ve_hiperbarik_tip | 13 | 8 | 5 | 0 | 0 | fixed ask kept |
  | spor_hekimligi | 13 | 8 | 5 | 0 | 0 | fixed ask kept |
  | halk_sagligi | 11 | 6 | 5 | 1 | 1 (source) | clinician wording or omit |
  | saglik_kurulu | 10 | 5 | 5 | 1 | 3 (2 source, 1 duplicate) | clinician wording or omit |
  | hemsirelik_egitim_poliklinikleri | 11 | 8 | 3 | 1 | 2 (source) | clinician wording or omit |
  | getat | 12 | 11 | 1 | 0 | 0 | fixed ask kept |
  | tibbi_ekoloji_ve_hidroklimatoloji | 12 | 11 | 1 | 0 | 0 | fixed ask kept |
  | odyoloji | 12 | 10 | 2 | 0 | 0 | fixed ask kept |
  | **total** | **127** | **80** | **47** | **8** | **7 (6 + 1 duplicate)** | |

  Proposed additions, not counted above: one gate item (iş ve meslek Q2a, part of a fix) and three clinician-decision items (spor Q14, Q15; odyoloji Q13).

- **Breaches:**
  - **Two items have the shape of a validated instrument item** (MEDIUM):
    - iş ve meslek Q14 is the Maslach Burnout Inventory's "burned out from my work" item as a yes/no.
    - hemşirelik Q10 is a single-item health-literacy screener. It also contradicts the proposal's own §0, which says health literacy is not measured.
  - **Four unsourced items were not held** (MEDIUM). The proposals themselves say there is no item-level or verbatim source for sağlık kurulu Q8 and Q9 and hemşirelik Q7 and Q8.
  - **One work-capacity self-judgement** (MEDIUM): hava ve uzay Q11 asks whether an injury "makes your duty harder", which is the regulatory unfitness trigger (MED.A.020(b)(3)), put to the patient.
  - **Complaint presumed in report visits** (MEDIUM): iş ve meslek Q2–Q4 assume a complaint that a periodic or pre-employment examinee may not have. A gate is added.
  - **Two posture statements are factually wrong** (MEDIUM), so each clinic's most important item reaches nobody's note:
    - spor §0 says exertional fainting and exertional chest pain "belong to base". Base has only an acute chest-pain probe and no exertional-syncope rule.
    - odyoloji §0 says sudden hearing loss is "left to base.life_threat". No such rule exists; the proposal's own §2.2 says so.

    Sourced wording is offered for the clinician (§C). Adding these items adds inputs only; it does not extend `base.life_threat`.
  - **OCR-only sources** (MEDIUM): six spor items (Q2, Q3, Q7, Q8, Q9, Q10) rest only on EK-1 text read by an English-model OCR with diacritics restored by hand. Four more (Q4, Q5, Q11, Q13) cite text that §1 does not quote. None is held, but none may be promoted, or cited by a rule, until the EK-1 image is re-read.
  - **Wrong tense** in sağlık kurulu Q2: "aldığınızı" says the report has already been obtained.
- **Q1 follow-up:** a Q1 ending in "anlatır mısınız?" gets "Sizi hekime getiren en önemli şikâyetiniz nedir?". That misframes a board visit (MEDIUM) and fitness or report visits (LOW). Five Q1s are reworded to end in "nedir?" so the neutral follow-up is used.
- **Duration ask:** the fixed "Bu şikâyetiniz ne zamandır var?" fits poorly in five packs: hava ve uzay, halk sağlığı, sağlık kurulu, hemşirelik and spor report visits. No source supports any other wording, so no `pack:` line is proposed. The generator still has no way to leave the slot out: wave 7 §E-2 is not implemented, and `PACK_KEYS` holds only `duration_ask` and `duration_follow_up` (§E).
- **Two D3 scope points for the owner:**
  - hava ve uzay Q15 (earlier certification restriction) is not a D3 category. It stays held, but for the statutory-declaration boundary, a legal reason.
  - hemşirelik Q10 is proposed as `voice`, not D3's `text_first`, because showing a reading-difficulty item as text first defeats it.
- **Clean:**
  - No digits, no `sen` forms, and at most fifteen words in every sentence. No `;`-joined ask, no "… mı ya da … mu?" and no when+how ask. PolicyGuard is clean on all 116 parsed asks and all 11 held texts as written.
  - No triage level, no RED rule, and no fitness, disability or eligibility verdict in patient copy. After the §C fixes, no work-capacity judgement is asked of the patient.
  - Nothing extends `base.life_threat`. The drafts extend `cluster.medical`, `cluster.allied_and_reports` or `cluster.sensory`.
  - GETAT and spa copy are neutral: no efficacy, safety or endorsement wording.
  - No PHQ-4, PAR-Q+, UHMS/WRSTC, HHIE-S, GPAQ, IPAQ or REALM/NVS/HLS-EU item is reproduced.
  - All yes/no items are `boolean` with semantic slot ids, and every dependent item is gated with `ask_if`.

## A. Findings

| where | finding | severity |
|---|---|---|
| iş ve meslek Q14 | "İş yükünüz ya da iş stresiniz yüzünden kendinizi tükenmiş hissediyor musunuz?" is the Maslach Burnout Inventory emotional-exhaustion item ("I feel burned out from my work"), which is licensed and is also used on its own as a single-item burnout screen. As a yes/no it becomes an unvalidated wellbeing screen outside the consented module. Reworded as the psychosocial exposure IM-S1 names ("Aşırı iş yükü"), in line with the pack's other hazard items. | MEDIUM (instrument) |
| hemşirelik Q10 | "Yazılı bilgileri okuyup anlamakta zorlanır mısınız?" has the shape of the published single-item literacy screeners. Released as written, the pack would measure health literacy, which §0 says it does not. Reframed as an accommodation preference (read aloud as well), which is what the nurse acts on. D3 covers the category, so the item needs an INT-349 row. `text_first` is not used: a reading-difficulty item shown as text first cannot reach the patient it is for. **The owner confirms this departure from D3's delivery line.** | MEDIUM |
| sağlık kurulu Q8 | §1 and §4 gap 3 of the proposal say there is no verbatim source for an assistive-device item (ICF is "context only"). Held until one is quoted. | MEDIUM (sourcing) |
| sağlık kurulu Q9 | Its only source is SK-S2 Madde 6, which §1 marks as "paraphrased by the fetch, not verbatim". Held until Madde 6 is snapshotted. The item is also a boolean whose content ("which concern?") would be lost, so it is split into a boolean and a gated string, both held and both `text_first` (mental health). | MEDIUM (sourcing) |
| hemşirelik Q7, Q8 | The proposal's §4 gap 3 says "NO SOURCE FOUND (item-level)" for learning format and sensory barriers. HE-S2's "adapted to the patient" is a principle, not an item. Held. | MEDIUM (sourcing) |
| hava ve uzay Q11 | "…görevinizi yapmanızı zorlaştıran bir yaralanma…" asks the pilot or controller to judge their own capacity for duty. That judgement is the MED.A.020(b)(3) trigger and the examiner's call (MED.A.025). Reworded to the source's neutral "önemli bir yaralanma". | MEDIUM (verdict) |
| iş ve meslek Q2–Q4 | "Şikâyetinizin…", "şikâyetleriniz azalıyor mu", "benzer şikâyetler" presume a complaint. The draft serves `report` and `screening` visits (işe giriş, periyodik muayene), where there may be none, and "şikâyetim yok" is then an ambiguous "hayır". A gate item Q2a is added and Q2–Q4 read it. | MEDIUM |
| spor §0, §2.2 | Exertional fainting (EK-1 item 5; SP-S2 item 13) and exertional chest discomfort (EK-1 item 6; SP-S2 item 14) are left out because they "belong to base rf.chest_pain_*". Base `rf_chest_pain_acute` is an acute probe, and exertional syncope is absent from base (the proposal's own §2.2 says so). As drafted, the two central pre-participation cardiac items reach no note. Sourced items Q14 and Q15 are offered for the clinician. They are inputs only, no rule reads them, and they do not extend `base.life_threat`. | MEDIUM (coverage; clinician decision) |
| odyoloji §0 | "Sudden hearing loss is NOT asked here. It is left to base.life_threat". No such base rule exists (§2.2: "not a base rule"), and an audiology booking is where sudden hearing loss often first presents. Q13 is offered with sualtı Q12's text and slot. It is an input only; placement of any rule stays with the base owner. | MEDIUM (coverage; clinician decision) |
| spor Q2, Q3, Q7, Q8, Q9, Q10 | Supported only by EK-1 text read with the English OCR model and diacritics restored by hand (§0 verification caveat). The topics are standard pre-participation topics and the asks are own words, so they are not held. Before promotion, the EK-1 image must be re-read and snapshotted, and no rule may cite the OCR text. | MEDIUM (source quality) |
| spor Q4, Q5, Q11, Q13 | Each cites text that §1 does not quote: EK-1 item 15 (Q4), SP-S2 item 8's "tedavinizi (ameliyat, alçı, fizik tedavi" (Q5), SP-S2 item 19 (Q11) and EK-1 item 29 (Q13, the "yeme düzeni" half). Add the quotes to §1, or drop the unsupported half of Q13. | LOW (proposal prose) |
| spor Q6 | The ask ("uzun süren baş ağrısı ya da unutkanlık") narrows the source construct, which is concussion or head injury history (EK-1 item 21). A concussion without lasting symptoms is still pre-participation history. Reworded to the source construct. | LOW |
| sağlık kurulu Q1 | The generator's follow-up "Sizi hekime getiren en önemli şikâyetiniz nedir?" misframes a legal board process. Reworded to end in "nedir?". | MEDIUM |
| iş ve meslek Q1, hava ve uzay Q1, sualtı Q1, spor Q1 | Report and fitness visits get the complaint follow-up. Each is reworded to end in "nedir?". This is the wave-7 workaround; §E-2 removes the need for it. | LOW |
| sağlık kurulu Q2 | Released under D3 (report purpose). "Bu raporu hangi amaçla aldığınızı" puts the report in the past. Reworded. SK-S1 Madde 8 bars the purpose from the report itself unless criteria exist, so the legal-reviewer must keep `rapor_amaci` out of any report export; the note may carry it. | MEDIUM (text) / NOTE (legal) |
| sağlık kurulu Q10 | With Q2 released, the yes/no employment link duplicates the purpose answer. Held as superseded; the text stays. | LOW |
| hava ve uzay Q15 | Certification history is not among D3's categories. Separately, it is literally a MED.A.035(b)(2)(iii) declaration item, and an inconsistency is reportable under MED.A.025(a)(3). The hold is therefore restated as a legal hold (gap 4). The text is also fixed now, removing the "engel" label, so that release needs only the legal answer. | MEDIUM (legal) |
| halk sağlığı Q10 | Travel plans: unsourced ("NO SOURCE FOUND") and not a D3 category. The hold reason is restated as the source gap. The SB Seyahat Sağlığı site already used by HU-S6 and SH-S8 is the obvious place to look. | LOW |
| iş ve meslek Q6, Q15–Q18; halk sağlığı Q11 | Released under D3 (employer and occupational exposure; household contacts), each `text_first` with an INT-349 row. Q6 no longer asks for the sector as well: base `occupation` and Q15 cover it, and the double object left a single string slot holding either of two facts. Q16 is gated on an exposure. D3 names "employer / occupational exposure"; Q17 (sick leave) and Q18 (tenure) are read as within that line. The owner narrows it if not. | NOTE (D3) |
| iş ve meslek Q2, Q4, Q5, Q7, Q9, Q11, Q14 | Work history is the files/02 employer-fear category, and IM-S3 requires confidentiality. The kept yes/no hazard items fall under D3's "occupational exposure", so they become `text_first` with the released ones. Symptom items (Q3, Q8, Q10, Q12, Q13) stay `voice`. | MEDIUM (delivery) |
| halk sağlığı Q4; spor Q11; odyoloji Q10 | Relatives' health history (D3): `text_first` and an INT-349 row, the same treatment as wave-7 tibbi_onkoloji Q12. | MEDIUM (delivery) |
| spor Q13 | Worry about weight or eating is an eating-behaviour disclosure, and athletes are often accompanied by a coach or parent. `text_first` is recommended (files/13 §13 does not require it; compare wave-6 obezite Q7). | LOW |
| spor Q11 | "…kalp hastalığından ölen biri oldu mu?" is blunt. The softer "kaybettiğiniz" is used, as in tibbi_genetik's `ailede_ani_aciklanamayan_kayip`. | LOW |
| iş ve meslek Q11 | "İşiniz … gerektiriyor mu?" presumes a current job and misses past work, which Q5, Q7 and Q9 cover. Reworded with one predicate. | LOW |
| iş ve meslek Q13 | "kuruma veya çatlama" is not in the IM-S1 quote ("kızarıklık, kaşıntı, … lokal şişlik"). Aligned with the quote; the clinician may add dryness back with a source. | LOW |
| hava ve uzay Q11, Q12 | "Son muayenenizden" can mean any medical visit when heard alone. Now "Son havacılık muayenenizden", as in Q10. | LOW |
| hava ve uzay Q5; iş ve meslek Q8 | One fact under two ids and two texts. Hava ve uzay adopts iş ve meslek's text and slot `cinlama_isitme_azalmasi`. | LOW |
| sualtı Q5 | "Dalış yaptığınız gün ya da ertesi gün" puts a waiting window into the question although §1 says the sources disagree and none is stated. Now SH-S8's own words, "kısa süre sonra". | LOW |
| sualtı Q9; spor Q12 | "epilepsi (sara)" puts a parenthesis into spoken copy (TTS and invariant 10). Now "sara, yani epilepsi nöbeti", the "yani" pattern already used in sualtı Q13 and odyoloji Q1. | LOW |
| sualtı Q10, Q13 | The shared slots exist already: `kapali_alan_huzursuzluk` (nükleer tıp, radyasyon onkolojisi) and `onceki_isin_tedavisi` (radyasyon, nükleer). Sualtı adopts the nükleer tıp texts and ids. | LOW |
| tıbbi ekoloji Q11 | Uses the shared `diyabet_tanisi` text (nefroloji; nükleer tıp after wave 7). | LOW |
| getat Q11 | "ağır kansızlık" asks the patient to grade severity. Now tıbbi ekoloji Q10's text and slot, `kansizlik_oykusu`. The clinician grades severity against GT-S2. | LOW |
| halk sağlığı Q6 | "Haftanın çoğu günü" turns HS-S4's weekly-minutes threshold into a frequency cut-off that no quote supports. Replaced with "düzenli olarak"; the clinician sets any threshold. | LOW |
| halk sağlığı Q8 | "Şekerli ya da gazlı" also captures sparkling mineral water. The source is "şekerli gazlı içecekler". Now "Kola, gazoz gibi şekerli içecekler". | LOW |
| odyoloji Q8 | Present tense only. OD-S1 asks for a *history* of long loud-noise exposure. Reworded to "ever". | LOW |
| hava ve uzay, spor, sağlık kurulu | Each proposal says its pack must not be presented, stored or exported as the statutory declaration (MED.A.035; EK-1; kişisel sağlık bilgi formu). This is a pack-level legal-reviewer gate before promotion. | NOTE (legal) |
| sağlık kurulu Q7 | Overlaps base `caregiver_present`. Base asks whether someone helps; Q7 asks whether help is needed, and a board needs the second fact. Kept. There is no score, no ICF qualifier and no inference. | NOTE |
| hemşirelik Q11 | The booking's `post_discharge` visit type may already record the discharge. Kept, because base `new_diagnoses_since_last_visit` does not. | NOTE |
| getat Q2 | The example practices (akupunktur, kupa, sülük, ozon) come from the repealed 2014 list. Before promotion, check each against the 2026 Ek-2 (gap 1). A practice absent from Ek-2 must not be named as an example. | NOTE |
| getat Q5; iş ve meslek Q16 | Polarity: `true` is the protective answer (done in a facility; wears protection), unlike the symptom slots. Record this where HB-C rule authors will see it. | NOTE |
| spor (EK-1 lineage) | EK-1's cardiac and injury items appear to follow the pre-participation physical evaluation history form, which was not retrieved and is not verified here. The pack's asks are own words, EK-1 is a Resmî Gazete annex, and no scoring or referral logic is used. PAR-Q+'s distinctive items (medically supervised activity, balance loss from dizziness, prescribed medicine for a chronic condition) are absent. EK-1's four mental-health items (the PHQ-4 pattern) are correctly not reproduced. | NOTE (instrument) |
| sualtı Q8 | Pairs collapsed lung with chest surgery, as the UHMS/WRSTC questionnaire's domains do. The pairing matches a domain only, with no wording, order or referral rule. Acceptable. | NOTE |
| odyoloji Q2 | A generic speech-in-noise item, not an HHIE-S item. It is close to the TKBBV lay self-check that §1 quotes "for provenance". Acceptable. | NOTE |
| alarm inputs with no rule | These answers reach the clinician note only; placement is for the base owner, and nothing is extended here (invariant 7):<br>• halk sağlığı Q9 (rabies-risk contact) and Q11 (TB household contact)<br>• sualtı Q12 and odyoloji Q13 (sudden hearing loss)<br>• spor Q14 and Q15 (if adopted)<br>• hava ve uzay Q13 (fainting history)<br>• tıbbi ekoloji Q6 (fever before a cure) | NOTE |
| slot ids across packs | Optional, for sharing clips:<br>• seizure and fainting use four ids: spor `epilepsi_nobeti_oykusu`, sualtı `nobet_bayilma_oykusu`, hava ve uzay `bayilma_bilinc_kaybi_oykusu`, sigara `nobet_oykusu`<br>• spor Q11 is close to tibbi_genetik `ailede_ani_aciklanamayan_kayip`<br>• spor Q10 ("kalp sorunu") and getat Q12 ("kalp hastalığı") stay apart, because EK-1's broader wording suits sports cardiology<br>• hava ve uzay Q4 and sualtı Q7 already share `guncel_ust_solunum_sikayeti` | NOTE |
| all ten proposals | 0 digits, at most 15 words per sentence, 0 `sen` forms, guard-clean, exactly one "?" each. No `;` join, no "… mı ya da … mu?", no when+how ask. | PASS |
| all ten proposals | No triage level and no RED rule. The generator writes only the stub rule, which carries the pending-value literal with `draft_needs_source` and is never compiled. | PASS |
| getat; tıbbi ekoloji | No efficacy, safety or endorsement wording. Practices are recorded as use, setting and outcome only. Tıbbi ekoloji records TE-S2's own "hala tartışmalıdır" and promises nothing. | PASS |

## B. How to read §C

- Every item takes the `gen:` line shown, on its own line under its `> "…"` quote. A Q1 takes none.
- "text unchanged" means only the `gen:` line changes.
- A new or split item gets its own header in the order shown (`**Q2a — …**`), with its own quote and `gen:` line, inside §3.
- `ask_if` reads a slot declared earlier in the same pack. `||` is accepted; the scratch rebuild confirmed it.
- Hold reasons contain no `;`, because `_parse_gen` splits on it (§E-3).
- Every item marked `text_first` under D3 also needs its data-inventory row under INT-349. The note line under the item should say so, in the wording wave 7 used: "invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349)."

## C. Replacement lists

### is_ve_meslek_hastaliklari — 1 gate added, 5 released, 5 text, 12 delivery

- Q1 → "Bugün iş ve meslek hastalıkları polikliniğine gelme nedeniniz nedir?" (no `gen:`)
- Insert before Q2, **Q2a — Current health complaint (gate)** · archetype `OBSERVATION.story.v1` · source: IM-S1 short list (asked of a worker with a health problem):
  - "Şu anda sizi rahatsız eden bir sağlık şikâyetiniz var mı?" · `gen: slot=guncel_saglik_sikayeti; type=boolean`
  - The owner may drop the gate if this clinic sees only symptomatic referrals. Q2–Q4 then lose their `ask_if`.
- Q2 text unchanged · `gen: slot=isten_kaynaklandigi_dusuncesi; type=boolean; ask_if=guncel_saglik_sikayeti == true; delivery=text_first`
- Q3 text unchanged · `gen: slot=tatilde_azalma; type=boolean; ask_if=guncel_saglik_sikayeti == true`
- Q4 text unchanged · `gen: slot=is_arkadaslarinda_benzer_sikayet; type=boolean; ask_if=guncel_saglik_sikayeti == true; delivery=text_first`
- Q5 text unchanged · `gen: slot=toz_kimyasal_maruziyeti; type=boolean; delivery=text_first`
- Q6 (released) → "Karşılaştığınız toz, duman, gaz ya da kimyasalların adlarını söyleyebilir misiniz?" · `gen: slot=maruziyet_ayrintisi; type=string; ask_if=toz_kimyasal_maruziyeti == true; follow_up=Adlarını bilmiyorsanız nasıl maddeler olduğunu anlatır mısınız?; delivery=text_first`
- Q7 text unchanged · `gen: slot=gurultulu_ortam; type=boolean; delivery=text_first`
- Q9 text unchanged · `gen: slot=titresimli_alet; type=boolean; delivery=text_first`
- Q11 → "Şimdiye kadar yaptığınız işler ağır yük ya da sık tekrarlanan hareket gerektirdi mi?" · `gen: slot=agir_yuk_tekrarli_hareket; type=boolean; delivery=text_first`
- Q13 → "Ellerinizde ya da kollarınızda kaşıntı, kızarıklık ya da şişlik oluyor mu?" · `gen: slot=el_kol_cilt_belirtileri; type=boolean`
- Q14 → "İşinizde aşırı iş yükü ya da stres yaşıyor musunuz?" · `gen: slot=asiri_is_yuku_stres; type=boolean; delivery=text_first`
  - Relabel it "Excess workload or stress at work (psychosocial exposure)". Mood and burnout screening stay with the consented wellbeing module.
- Q15 (released) text unchanged · `gen: slot=is_yeri; type=string; delivery=text_first`
- Q16 (released) text unchanged · `gen: slot=kisisel_koruyucu; type=boolean; ask_if=toz_kimyasal_maruziyeti == true || gurultulu_ortam == true; delivery=text_first`
- Q17 (released) text unchanged · `gen: slot=isle_ilgili_rapor; type=boolean; delivery=text_first`
- Q18 (released) text unchanged · `gen: slot=is_suresi; type=duration; delivery=text_first`
- PASS: Q8, Q10, Q12.
- Duration: the fixed ask fits the symptom-driven visits this clinic mostly sees. No sourced alternative exists for periodic examinations.

### hava_ve_uzay_hekimligi — 4 text, 1 slot id, 1 hold restated

- Q1 → "Bugün hava ve uzay hekimliği polikliniğine gelme nedeniniz nedir?" (no `gen:`)
- Q5 → "Kulaklarınızda çınlama ya da işitmenizde azalma fark ettiniz mi?" · `gen: slot=cinlama_isitme_azalmasi; type=boolean`
- Q11 → "Son havacılık muayenenizden bu yana önemli bir yaralanma geçirdiniz mi?" · `gen: slot=son_muayeneden_beri_yaralanma; type=boolean; ask_if=onceki_havacilik_muayenesi == true`
- Q12 → "Son havacılık muayenenizden bu yana ilk kez gözlük ya da lens kullanmaya başladınız mı?" · `gen: slot=ilk_kez_gozluk_lens; type=boolean; ask_if=onceki_havacilik_muayenesi == true`
- Q15 → "Önceki bir havacılık muayenesinde size kısıtlama ya da olumsuz bir karar verildi mi?" · `gen: slot=onceki_kisitlama_karari; type=boolean; ask_if=onceki_havacilik_muayenesi == true; delivery=text_first; hold=statutory declaration boundary awaits the legal-reviewer (gap 4)`
  - The text is ready for release; only the legal answer is missing. Certification history is not a D3 category, so the owner also confirms it before release.
- PASS: Q2, Q3, Q4, Q6, Q7, Q8, Q9, Q10, Q13, Q14.
- Duration: an examination visit has no complaint, and no source supports another wording. Clinician wording is needed, or omit the slot once §E-1 lands.

### sualti_ve_hiperbarik_tip — 3 text, 2 shared slots

- Q1 → "Bugün sualtı ve hiperbarik tıp polikliniğine gelme nedeniniz nedir?" (no `gen:`)
- Q5 → "Dalıştan kısa süre sonra uçağa bindiğiniz oluyor mu?" · `gen: slot=dalis_sonrasi_ucus; type=boolean; ask_if=dalis_deneyimi == true`
- Q9 → "Daha önce hiç sara, yani epilepsi nöbeti ya da nedeni bilinmeyen bayılma geçirdiniz mi?" · `gen: slot=nobet_bayilma_oykusu; type=boolean`
- Q10 → "Kapalı ya da dar alanlarda bulunmak sizi çok huzursuz eder mi?" · `gen: slot=kapali_alan_huzursuzluk; type=boolean`
- Q13 → "Daha önce vücudunuzun herhangi bir bölgesine ışın tedavisi uygulandı mı?" · `gen: slot=onceki_isin_tedavisi; type=boolean; follow_up=Daha önce radyoterapi aldınız mı?`
  - Same text, slot and follow-up as radyasyon onkolojisi and nükleer tıp. The follow-up has the same polarity as the ask.
- PASS: Q2, Q3, Q4, Q6, Q7, Q8, Q11, Q12.
- Duration: the fixed ask fits hyperbaric referrals (wound, sudden hearing loss), where onset time matters. Fitness-to-dive visits answer "none".

### spor_hekimligi — 4 text, 2 delivery, 2 additions for the clinician

- Q1 → "Bugün spor hekimliği polikliniğine gelme nedeniniz nedir?" (no `gen:`)
- Q6 → "Daha önce beyin sarsıntısı ya da baş yaralanması geçirdiniz mi?" · `gen: slot=beyin_sarsintisi_oykusu; type=boolean`
- Q11 → "Ailenizde genç yaşta aniden ya da kalp hastalığı nedeniyle kaybettiğiniz biri oldu mu?" · `gen: slot=ailede_genc_yasta_ani_olum; type=boolean; delivery=text_first`
- Q12 → "Daha önce hiç sara, yani epilepsi nöbeti geçirdiniz mi?" · `gen: slot=epilepsi_nobeti_oykusu; type=boolean`
- Q13 text unchanged · `gen: slot=kilo_yeme_kaygisi; type=boolean; delivery=text_first`
  - Quote EK-1 item 29 in §1, or cut the ask to weight only.
- PASS: Q2, Q3, Q4, Q5, Q7, Q8, Q9, Q10.
  - Q2, Q3, Q7, Q8, Q9 and Q10 pass on content, but their only source is OCR (§A).
  - Q4 and Q5 need their source quotes added to §1.
- Additions, a clinician decision (§A). Append in §3 after Q13:
  - **Q14 — Fainting or near-fainting with exercise** · source SP-S2 item 13, SP-S1 EK-1 item 5 · "Spor yaparken ya da hemen sonra hiç bayıldınız ya da bayılacak gibi oldunuz mu?" · `gen: slot=egzersizde_bayilma; type=boolean`
  - **Q15 — Chest discomfort with exercise** · source SP-S2 item 14, SP-S1 EK-1 item 6 · "Spor yaparken göğsünüzde ağrı, sıkışma ya da baskı hissettiniz mi?" · `gen: slot=egzersizde_gogus_rahatsizligi; type=boolean`
  - SP-S2 is text extracted locally with pdftotext, not OCR, so both additions have a non-OCR source. §2.2's "Not asked" rows change to "history input; no rule".
- Duration: fits injury visits. For pre-participation report visits there is no sourced alternative (§E-1).

### halk_sagligi — 2 text, 1 released, 1 delivery, 1 hold restated

- Q4 text unchanged · `gen: slot=ailede_kalin_bagirsak_kanseri; type=boolean; delivery=text_first`
- Q6 → "Nefesinizi biraz hızlandıran yürüyüş gibi hareketleri düzenli olarak yapıyor musunuz?" · `gen: slot=duzenli_fiziksel_aktivite; type=boolean`
- Q8 → "Kola, gazoz gibi şekerli içecekleri sık içer misiniz?" · `gen: slot=sekerli_icecek; type=boolean`
- Q10 text unchanged · `gen: slot=yurt_disi_seyahat_plani; type=boolean; delivery=text_first; hold=no travel-health source retrieved (gap 4)`
  - When a source is found, release also needs the owner, because travel plans are not a D3 category.
- Q11 (released) text unchanged · `gen: slot=evde_verem_temasi; type=boolean; delivery=text_first`
- PASS: Q1, Q2, Q3, Q5, Q7, Q9.
  - Q7's "her gün" is a plain daily question; the clinician may prefer "sık", as in Q8.
- Duration: a preventive visit has no complaint (gap 7). No sourced wording exists; clinician wording is needed, or omit the slot (§E-1).

### saglik_kurulu — 2 text, 1 released, 2 source holds (one split), 1 duplicate hold

- Q1 → "Kurulda değerlendirilecek sağlık sorunlarınız nedir?" (no `gen:`)
- Q2 (released) → "Bu raporun hangi amaçla istendiğini kısaca söyler misiniz?" · `gen: slot=rapor_amaci; type=string; delivery=text_first`
  - Keep it out of the report text (SK-S1 Madde 8); the legal-reviewer decides the export boundary.
- Q8 text unchanged · `gen: slot=yardimci_arac; type=boolean; hold=no verbatim source for an assistive-device item (gap 3)`
- Q9 → two items, both held:
  - Q9 (a) text unchanged · `gen: slot=ek_brans_konusu; type=boolean; delivery=text_first; hold=SK-S2 Madde 6 was captured as a paraphrase not a verbatim quote`
  - insert **Q9b** "Bu konuyu kısaca anlatır mısınız?" · `gen: slot=ek_brans_konusu_aciklama; type=string; ask_if=ek_brans_konusu == true; delivery=text_first; hold=same as Q9a`
- Q10 text unchanged · `gen: slot=is_icin_rapor; type=boolean; delivery=text_first; hold=superseded by Q2 which records the report purpose`
- PASS: Q3, Q4, Q5, Q6, Q7.
- The emitted pack is Q1 plus Q2 through Q7: six items.
- Duration: a board visit (gap 7). No sourced wording exists; clinician wording is needed, or omit the slot (§E-1).

### hemsirelik_egitim_poliklinikleri — 1 released and reframed, 2 source holds

- Q7 text unchanged · `gen: slot=ogrenme_tercihi; type=string; hold=no item-level source for learning format (gap 3)`
- Q8 text unchanged · `gen: slot=gorme_isitme_engeli; type=boolean; hold=no item-level source for sensory barriers (gap 3)`
- Q10 (released) → "Yazılı bilgilerin size ayrıca sesli olarak anlatılmasını ister misiniz?" · `gen: slot=sesli_anlatim_tercihi; type=boolean`
  - `voice` on purpose (§A). It still needs an INT-349 row, because the answer is a literacy proxy.
  - HE-S2's "health literacy level" and "adapted to the patient" support asking for the accommodation. They do not support measuring literacy.
- PASS: Q1, Q2, Q3, Q4, Q5, Q6, Q9, Q11.
- Duration: an education visit (gap 6). No sourced wording exists; clinician wording is needed, or omit the slot (§E-1).

### getat — 1 text and slot

- Q11 → "Size daha önce kansızlık olduğu söylendi mi?" · `gen: slot=kansizlik_oykusu; type=boolean`
- PASS: Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q9, Q10, Q12. Neutral throughout; see the Q2 note on Ek-2 (§A).
- Duration: patients come with a complaint, so the fixed ask fits.

### tibbi_ekoloji_ve_hidroklimatoloji — 1 text and slot

- Q11 → "Size daha önce şeker hastalığı tanısı konuldu mu?" · `gen: slot=diyabet_tanisi; type=boolean`
- PASS: Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q9, Q10, Q12.
- Duration: spa referrals are for chronic complaints, and Q4 relies on this slot. The fixed ask fits.

### odyoloji — 1 text, 1 delivery, 1 addition for the clinician

- Q8 → "İşte ya da günlük hayatta uzun süre çok gürültülü ortamlarda bulunduğunuz oldu mu?" · `gen: slot=yuksek_sese_maruziyet; type=boolean`
- Q10 text unchanged · `gen: slot=ailede_isitme_kaybi; type=boolean; delivery=text_first`
- PASS: Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q9, Q11, Q12.
- Addition, a clinician decision (§A). Append in §3 after Q12:
  - **Q13 — Recent sudden drop in hearing** · source OD-S1 ("If sudden, refer urgently"), OD-S2 ("hemen başvurmak") · "Son zamanlarda işitmenizde ani bir azalma oldu mu?" · `gen: slot=ani_isitme_azalmasi; type=boolean`
  - Same text and slot as sualtı Q12. If the clinician declines it, correct §0: base.life_threat has no sudden-hearing-loss rule.
- Duration: a hearing complaint, so the fixed ask fits.

## D. Proposal prose that must change with §C

- **iş ve meslek:**
  - §0: the data-category bullets now read "approved under D3; `text_first`; INT-349 row".
  - §2.1: add Q2a and relabel Q14.
  - §3: the counter becomes "19 drafted, all active".
  - §4 gap 3: now "resolved by D3, except the INT-349 open items".
  - §5: the Inv. 18 line changes to match.
- **hava ve uzay:**
  - §0 and §4 gap 5: Q15 is held for the statutory-declaration boundary (gap 4), not for the data category.
- **spor:**
  - §0: the exertional bullet is incorrect (§A). Either adopt Q14 and Q15 or restate the reason.
  - §1: quote EK-1 items 15 and 29, SP-S2 item 19 and the SP-S2 item 8 treatment phrase.
  - Q11: add the D3/INT-349 note.
- **halk sağlığı:**
  - §0, §2.2 and §5: Q11 is released under D3. Q10 stays held for its source only.
  - The counter changes to match.
- **sağlık kurulu:**
  - §0: "Purpose of the report is not asked (Q2 held)" becomes "asked under D3; kept out of the report itself (SK-S1 Madde 8)".
  - Record the Q8, Q9 and Q10 holds and update the counter.
- **hemşirelik:**
  - §0: "Health literacy is not measured … Q10 is held" becomes "Q10 asks for an accommodation, not a measure; voice".
  - Record the Q7 and Q8 holds and update the counter.
- **odyoloji:**
  - §0: correct the sudden-hearing-loss bullet.
  - §2.2: the role column says "history input" if Q13 is adopted.

## E. Generator changes (scripts/dev/gen_specialty_packs.py)

1. **`duration=omit` pack key** (wave 7 §E-2, still not implemented). It is needed by hava ve uzay, halk sağlığı, sağlık kurulu and hemşirelik, and optionally by spor report visits. Validate it the way `delivery` is validated.
2. **`reason_follow_up` pack key** (wave 7 §E-1, still not implemented). Five Q1 rewrites in this wave exist only to switch the follow-up through the "nedir?" suffix rule.
3. **Hold values and `;`.** `_parse_gen` splits the hold reason at `;`, so iş ve meslek's original hold reasons silently lost their second clause. Either refuse a `;` inside a gen value, or read `hold=` to the end of the line.
4. **A `pack:` or section-level delivery.** Iş ve meslek needs twelve per-slot `text_first` flags. A section-level key would be harder to get wrong. files/13 §13 allows delivery per section.

## F. Checklist

- **Source spot-check.** Eight pages were fetched again:
  - Every quoted phrase checked was found on seven: HS-S2, HS-S6, HU-S3, SH-S4, GT-S2, OD-S2 and the SK-S1 SB notice.
  - SP-S1's Resmî Gazete page failed TLS verification and is **unverified**, together with its OCR-only EK-1.
  - The other quotes were checked against the proposals' own §1 only.
- **Instruments:** Iş ve meslek Q14 (Maslach shape) and hemşirelik Q10 (literacy-screener shape) are reworded (§C). No PHQ-4, PAR-Q+, UHMS/WRSTC, HHIE-S, GPAQ, IPAQ or literacy-instrument item is reproduced. The EK-1 lineage is a NOTE.
- **Monotonicity:** nothing is removed or relaxed, and nothing extends `base.life_threat`. Alarm items are inputs only (§A).
- **RED axes:** there are no RED rules.
- **Verdicts:** no fitness, disability, eligibility or work-capacity language remains after hava ve uzay Q11 and Q15 are fixed. No score or ICF qualifier is computed anywhere.
- **Patient copy:**
  - `siz` throughout, at most B1 and one question per turn.
  - Clinic names in Q1 are spoken as booked. "hidroklimatoloji" is the only unglossed technical name; odyoloji glosses its own name.
- **Invariant 22:** no numerals. Tenure is `type=duration`, and no waiting time, age threshold or programme interval is spoken.
- **Invariant 18 (D3):**
  - Eight items are released and eighteen emitted items are `text_first`.
  - Every such item needs its INT-349 row. Before any of them is served, D3 also requires encrypted storage, the counsel decisions per category, and slot tagging.
- **Goldens:** there are no rules, so no near-miss controls are needed. `make safety` and CODEOWNER review apply when the packs are generated.
- **Found in passing:**
  - Six review packs carry most of their yes/no asks as generic `soru_N` `string` slots because their proposals have no `gen:` lines: ic_hastaliklari, goz_hastaliklari, gogus_cerrahisi, kulak_burun_bogaz_hastaliklari, plastik_rekonstruktif_ve_estetik_cerrahi and kalp_ve_damar_cerrahisi. KBB's sudden-hearing-loss item is `soru_1` (string), so no shared id existed for the sualtı and odyoloji item.
  - Route this to the generator owner.
