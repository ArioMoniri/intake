# Verification of the wave 8 specialty proposals (geriatrics, older-adult health, sleep, clinical neurophysiology, dental) — awaiting-clinical-review

Reviewer: independent clinical-content verifier (challenger), 2026-09-26. Every clinical item here is `awaiting-clinical-review`; passing this review is not a physician signature. No clinical value was authored by the reviewer.

Scope:

- `docs/evidence/proposals/{geriatri, yasli_sagligi_poliklinigi, uyku_poliklinigi, klinik_norofizyoloji, ortodonti, pedodonti, periodontoloji, protetik, restoratif}.md`
- None of the nine has a review-queue candidate yet, so every fix below is a proposal edit that takes effect when `scripts/dev/gen_specialty_packs.py` generates the pack.

Method:

- Every proposal was parsed with `extract_questions` and `extract_pack_options` from the generator. 111 of 111 parse, none is refused or held, and `build_pack` (base slots included) succeeds for all nine.
- Every ask, every follow-up and the three fixed generator texts of each pack were run through the shipped Turkish PolicyGuard (`policy_guard_for(locale="tr", profile=residency_tr)`, `inspect_sentence`). Each was also checked for word count, digits, `;`, a second question particle ("… mı ya da … mu?") and when+how.
- Every replacement below was applied to scratch copies of the proposals, which were then re-parsed and rebuilt with `build_pack`. Each rebuilt pack was loaded as `ProtocolPack` and run through the validator's voice findings, with 0 findings. After the splits there are 118 items. All are guard-clean, at most 13 words per sentence, digit-free, and have exactly one question mark.
- The one new `||` gate (uyku Q5) parses with `protocols.triage.expr.parse_when`. `compile/emit_fhir._project` maps a top-level `||` to `enableBehavior: any`.
- Source support was checked against each proposal's own §1 quotes and locators. Sources were not fetched again.
- Shared slot ids and texts were checked against `packages/protocols/review/specialty/*.yaml` and the earlier verification files.

## BLUF

- **111 items reviewed.** That is 9 reason-for-visit items and 102 pack items. The three fixed texts the generator adds to every pack were also checked for all nine packs: the reason follow-up, the duration ask and the duration follow-up.
- **24 REVISE, 87 PASS.** Seven of the 24 are splits, which add 7 items.

  | file | items | PASS | REVISE | duration slot |
  |---|---|---|---|---|
  | geriatri | 13 | 9 | 4 | fits a complaint; may be omitted for a CGA referral |
  | yasli_sagligi_poliklinigi | 12 | 6 | 6 | clinician wording needed |
  | uyku_poliklinigi | 13 | 10 | 3 | pack line proposed (units) |
  | klinik_norofizyoloji | 13 | 11 | 2 | fits |
  | ortodonti | 12 | 11 | 1 | clinician wording needed |
  | pedodonti | 12 | 10 | 2 | pack line proposed (parent address) |
  | periodontoloji | 12 | 9 | 3 | fits a complaint; may be omitted for recall visits |
  | protetik | 12 | 11 | 1 | clinician wording needed |
  | restoratif | 12 | 10 | 2 | fits |
  | **total** | **111** | **87** | **24** | |

- **Breaches:**
  - **Invariant 18: one item, klinik_norofizyoloji Q13** (family history of epilepsy).
    - Relatives' health is the category wave 7 held.
    - The owner has approved such items with `text_first` delivery. The item stays, but it needs `delivery=text_first` and a row in the sensitive-data register (INT-349).
    - It is the only new-category item in this wave.
  - **Invariant 2: one item, restoratif Q10.** It asks about twice-daily brushing and fluoride toothpaste in one question with one answer. PolicyGuard cannot detect this.
  - **Six boolean slots rely on a follow-up to collect a name or a narrative**, which a boolean slot cannot store (the wave 7 defect again):
    - ortodonti Q9
    - pedodonti Q10, Q11
    - periodontoloji Q11, Q12
    - protetik Q11
  - **One dependent item has no gate** (uyku Q5).
  - **Three follow-ups record a different fact from their ask** (klinik Q7, yasli Q7, yasli Q9). Six LOW follow-up mismatches are also fixed.
  - **Two asks drift from their own source**:
    - geriatri Q6 asks about impact where WFG asks about worry.
    - periodontoloji Q12 says "surgery" where AHA lists valve prostheses and repair material, including catheter-implanted valves.
- **Duration ask:**
  - The fixed "Bu şikâyetiniz ne zamandır var?" fits the complaint-driven packs: geriatri, uyku, klinik, periodontoloji and restoratif.
  - Pedodonti needs the parent-addressed line (the same text as neonatoloji).
  - Uyku keeps the ask, but its follow-up needs month and year units (U-S1).
  - Yaşlı sağlığı, ortodonti and protetik see periodic, alignment or recall visits, and no source supports a duration question there. They need clinician wording, or the slot left out once wave 7 §E-2 lands.
- **Clean:**
  - Parsing and generation:
    - 111/111 parse, none refused or held, and all nine build.
    - Every non-Q1 item has a `gen:` line with a semantic slot id and a type. All yes/no items are boolean, and the two narrative items are strings.
  - Patient copy:
    - PolicyGuard is clean on every ask, follow-up and fixed text.
    - No digits, no `sen` forms, no `;`, no two-particle asks and no when+how asks.
    - At most 14 words per sentence (13 after the fixes).
  - No base duplicates: medicines, allergies, blood thinners, smoking, alcohol, pregnancy, living situation and caregiver are all left to `base.intake`. The antiresorptive item stays, as in wave 1–3.
  - Triage and invariant 7:
    - No triage level and no RED rule.
    - All nine L0 drafts extend `cluster.medical` or `cluster.dental`, and nothing extends `base.life_threat`.
  - Instruments:
    - No MMSE/MoCA, Epworth, STOP-Bang, GDS, Katz/Lawton or PSQI item is reproduced or paraphrased.
    - Construct overlaps are NOTE rows in §A: capture them, never score them.
  - Pedodonti addresses the parent with "çocuğunuz" in every item.
- **Cross-wave (outside scope, routed to the owner):**
  - Twelve relatives-health or consanguinity slots in earlier-wave review packs still have no `delivery: text_first`, while the wave 7 packs now do.
  - `kemik_ilaci` is typed `string` in two wave 1–3 packs and boolean here.
  - The dental cluster has two airway postures.
  - Two PolicyGuard false positives were confirmed (§A).

## A. Findings

| where | finding | severity |
|---|---|---|
| klinik_norofizyoloji Q13 | Family history of epilepsy is health data about relatives, the invariant 18 category wave 7 held. The owner has approved such items with `text_first` delivery. The `gen:` line has no `delivery`, and no register row exists. Add `delivery=text_first`. Record {category, purpose, basis, retention, recipients} in the sensitive-data register (INT-349) before promotion; this review creates no ids. The follow-up also narrows "Ailenizde" to parents and siblings, which KN-S3 ("Ailede nöbet, epilepsi öyküsü") does not. | HIGH (inv 18) |
| ortodonti Q9; pedodonti Q10, Q11; periodontoloji Q11, Q12; protetik Q11 | These are boolean slots whose follow-up asks for a name or a narrative ("…adını söyleyebilir misiniz?", "…kısaca anlatır mısınız?"). The runtime uses a follow-up only on `clarification_needed` and writes the reply into the same boolean slot, so the detail is lost. Wave 7 found this defect in seven items. Split each into a boolean and a gated string item. | MEDIUM |
| uyku Q5 | "Uykunuzdaki bu sorun" presupposes the insomnia complaint that Q2–Q4 establish, but it has no gate. A patient referred only for snoring hears a question about "this problem". U-S3 ties daytime impairment to "the nighttime sleep difficulty". Gate on any of Q2–Q4 with `\|\|`. | MEDIUM |
| restoratif Q10 | Two concerns share one answer: brushing twice a day, and fluoride toothpaste. A patient who does one but not the other answers "hayır", and the note cannot say which. The guard cannot see this, and the proposal itself allows the split. Use pedodonti's two slots (`sabah_aksam_fircalama`, `florurlu_macun`), addressed to the patient. | MEDIUM (inv 2) |
| klinik_norofizyoloji Q7 | The ask concerns a diagnosed clotting disorder (KN-S1; KN-S5 "hemophilia"). The follow-up asks whether a small cut bleeds long, which is a symptom. A yes to the follow-up records a diagnosis the patient does not have, and the slot feeds the needle-EMG safety check. The follow-up is restated. | MEDIUM |
| yasli Q7 | "Bu düşmede" assumes a single fall after Q6's "hiç düştünüz mü?". The follow-up ("bir yeriniz incindi ya da kırıldı mı?") lowers the threshold from an injury needing a doctor (YS-S5) to any sprain. The slot is the gate input for the §2.3 fall-with-injury candidate. Both texts are reworded. | MEDIUM |
| yasli Q9 | The ask says "bu yıl"; the follow-up says "son grip mevsiminde". Asked in September, a patient vaccinated the previous November answers no to one and yes to the other. YS-S1 gives no window (proposal gap 4), so the follow-up now restates the ask, and the window stays with the clinician. | MEDIUM |
| geriatri Q6 | GE-S8, the WFG key question, asks whether the person worries about falling. The ask asks whether fear affects daily life, and the follow-up asks about avoiding activities. A worried patient who has not changed any activity answers "hayır", and the case-finding fact is lost. Reworded to the worry construct. | MEDIUM |
| periodontoloji Q12 | "kalp kapağı ameliyatı" leaves out catheter-implanted valves and valve-repair material, both of which PD-S5's own locator lists ("prosthetic valves or valve-repair material"). A patient with a catheter-implanted valve answers "hayır" to a highest-risk care-planning item. "kalp kapağınızla ilgili bir işlem" covers both. The narrative follow-up is split as well (row above). | MEDIUM |
| pedodonti (fixed `sikayet_suresi`) | "Bu şikâyetiniz" addresses the parent's own complaint (proposal gap 6). The pack line uses neonatoloji's parent-addressed wording, so one clip serves both. The line changes the address only and carries no clinical content. | MEDIUM |
| yasli, ortodonti, protetik (fixed `sikayet_suresi`) | These visits often have no complaint to time: periodic review (the YS-S1 guideline; geriatri GE-S1 quotes its "en az yılda bir kez"), an alignment concern (ortodonti gap 6), or a denture recall (PR-S3 annual check). No source supports a duration question for them. They need clinician wording, or the slot left out once wave 7 §E-2 lands. Geriatri (CGA referral) and periodontoloji (maintenance recall, PD-S1 p. 33) may use the same option. | MEDIUM |
| ortodonti (all items) | Many orthodontic patients are children (proposal gap 2), but every ask addresses the patient, so in a proxy session the parent hears "dişlerinizin". One of two is needed: a self/proxy variant keyed on base `subject_role`, or a confirmation that the pack is self-report only. This is an owner and clinician decision, not a per-item REVISE. | MEDIUM |
| dental cluster posture | Waves 1–3 (finding 26) and 4–5 put an ungated airway ask into dis_hekimligi, endodonti, agiz_dis_ve_cene_cerrahisi and agiz_dis_cene_radyolojisi, under two slot ids (`nefes_yutkunma_guclugu`, `nefes_yutma_zorlugu`). These five dental proposals leave it to "base.life_threat (rf.dyspnoea_rest, rf.sepsis_like)". Both are named-gap stubs in `base/intake.yaml`, with no `ask_tr` and a pending trigger. `files/protocols/base.life_threat.yaml` holds four rules, none of them an adult airway rule, and its paediatric airway exemplar is `draft_needs_source`. So no layer asks about the airway in these five packs. The items this matters for are periodontoloji Q6 (pus; PD-S2 notes systemic spread) and pedodonti Q4 (gum swelling). Choosing one posture for the cluster is the owner's decision (§D-2). Nothing is extended here. | MEDIUM (consistency) |
| yasli Q1 | Periodic-review and prevention visits (YS-S1; YS-S3 "koruyucu hekimlik") have no complaint, yet the "anlatır mısınız?" ending selects the follow-up "…en önemli şikâyetiniz nedir?". End Q1 with "nedir?", as wave 7 did for nükleer tıp. | LOW |
| geriatri Q4 | The slot is `dusme_sonrasi_kalkamama`, and both sources say inability ("Düşme sonrası kalkamama"; "no capacity to get up"). The ask says "kalkmakta zorlandınız" (struggled). A rule author reading the slot name would treat struggling as inability. The ask now matches the source. | LOW |
| geriatri Q9 | "gaz ya da dışkı": flatus is in neither GE-S1 nor GE-S2, and the slot is `diski_kacirma`, so gas alone would be recorded as faecal incontinence. | LOW |
| geriatri Q13 | "yattığınız ya da oturduğunuz yerlerde" reads as the places (bed, chair) as easily as the body sites. The follow-up drops redness, so a patient with redness only answers "hayır". Reworded. The follow-up uses the evde_saglik body sites (topuk, kalça, kuyruk sokumu). | LOW |
| yasli Q2, Q5, Q11 (follow-ups) | Each follow-up asks a different fact from its ask:<br>• Q2 asks "can no longer do" for an ask about struggling.<br>• Q5 asks about pain for an ask about difficulty eating.<br>• Q11 names wrist, hip and spine, which the YS-S1 quote does not.<br>Each follow-up now restates its ask. | LOW |
| uyku Q6 | The same fact as obezite Q9 (`gunduz_istemsiz_uyuma`, "Gün içinde istemeden uyuyakaldığınız oluyor mu?") under another id and text. Share both so one clip serves both packs. | LOW |
| uyku Q7 (follow-up) | "Birlikte kaldığınız kişi" presumes that someone lives with the patient. Wave 6 göğüs Q12 had the same issue. | LOW |
| uyku (fixed `sikayet_suresi`) | The ask fits, but the follow-up offers only "gün ya da hafta". U-S1's own threshold is over a month, and U-S3's complaint is chronic. The pack line offers weeks, months and years. The threshold itself stays in the source. | LOW |
| periodontoloji Q9 | Use the shared slot `diyabet_tanisi` and the wording already shared by nefroloji, göz and nükleer tıp, so one clip serves all of them. This also drops the parenthesis. | LOW |
| restoratif Q7 | "içer misiniz?" is also the everyday form of an offer ("Çay içer misiniz?"). In voice, the habitual reading is not guaranteed. Use "içiyor musunuz?". | LOW |
| PolicyGuard false positives (verified) | Two history questions trip the guard:<br>• "Size istenen testin adını…" trips REGISTER (klinik §5 already reports this).<br>• "…bir hastalığınız var mı?" trips DIAGNOSIS.<br>The proposals work around both ("test adını"; "…tanısı konuldu mu?"). Route to the lexicon owner (HB-C23) so patient copy is not bent around the guard. | LOW (observed) |
| incontinence: geriatri Q8, Q9; yasli Q8 | Not on files/13 §13's `text_first` list. However, GE-S1 itself names "utanç, damgalanma", and older adults are often accompanied (the §13 third-party-present moderator). `delivery=text_first` is offered as optional (§D-1), because text may be harder for a patient with poor vision (yasli Q3) or low literacy. Clinician choice; not counted. | NOTE |
| instrument constructs | None of these reproduces an item's wording, recall window or answer scale:<br>• **uyku:** Q2–Q5 follow the ICSD/AASM insomnia definition (U-S3), which is also the construct of ISI items 1–3 and 5. Q6 is the construct of the Epworth scale and the STOP-Bang "tired" item, with no situation named. Q7–Q9 are the STOP-Bang "snoring" and "observed" items and Berlin category 1. Q10–Q11 are the IRLSSG criteria. Q12 is the construct of the single-question RBD screen, without dream enactment.<br>• **geriatri:** Q2, Q5 and Q6 are the WFG/STEADI three key questions. Q10–Q11 are a subjective memory complaint (the construct of AD8 item 8 and the GDS-15 memory item).<br>• **ortodonti:** Q4–Q6 are the 3Q/TMD and AAOP screening constructs, with no frequency.<br>• **chewing:** ortodonti Q3, yasli Q5, protetik Q8 and periodontoloji Q8 are the GOHAI/OHIP chewing construct.<br>• **pedodonti:** Q5–Q8 and Q10 are AAPD caries-risk factors (PE-S3).<br>Never score these items. Never assemble a STOP-Bang, ISI, WFG risk group, 3Q/TMD or caries-risk category from pack answers. | NOTE |
| yasli Q4 (follow-up) | The follow-up ("asking people to repeat") could not be compared with YS-S1's hearing-screen table, because the proposal does not reproduce the table. The clinician confirms that it is not a table item. | NOTE |
| alarm inputs with no rule | These answers reach the clinician note only. Placement is for the base owner, and nothing is extended here (invariant 7):<br>• geriatri Q3's narrative may carry loss of consciousness or a head injury.<br>• geriatri Q4 and yasli Q7 feed §2.3 candidates.<br>• uyku Q9 overlaps nocturnal breathlessness (base `rf_dyspnoea_rest` stub).<br>• klinik Q8 may reveal a first seizure (KN-S3; absent from base).<br>• periodontoloji Q6 and Q7 are the abscess and necrotising patterns.<br>• pedodonti Q3 and Q4.<br>Sleepiness while driving (uyku §2.2) is asked nowhere. | NOTE |
| slot ids across packs | Optional, for sharing clips:<br>• `cigneme_zorlugu` has three texts (ortodonti Q3, periodontoloji Q8, protetik Q8).<br>• `dis_eti_kanamasi` has three texts (dis_hekimligi, ortodonti Q12, periodontoloji Q2).<br>• `kemik_ilaci` is `type: string` in agiz_dis_cene_radyolojisi and agiz_dis_ve_cene_cerrahisi but boolean here. Align those two packs to boolean plus `kemik_ilaci_adi`.<br>• Pedodonti `kalp_sorunu` covers what cocuk_kardiyolojisi splits into `kalp_tanisi` and `kalp_ameliyati`.<br>• `son_yil_dusme`, `onceki_dis_travmasi` and `ara_ogun_seker` differ only by self or proxy address. That is acceptable. | NOTE |
| relatives-health slots in earlier waves | The owner's decision is visible in the tree: the wave 7 relatives-health and consanguinity slots now carry `delivery: text_first`. Twelve earlier-wave slots do not:<br>• anesteziyoloji `ailede_anestezi_sorunu`<br>• cerrahi_onkoloji `ailede_kanser`<br>• cocuk_genetik_hastaliklari `ailede_genetik_hastalik`, `akraba_evliligi`, `ailede_ureme_kaybi`<br>• cocuk_immunolojisi_ve_alerjisi `ailede_bagisiklik_hastaligi`<br>• cocuk_kardiyolojisi `ailede_ani_olum`, `ailede_ritim_hastaligi`<br>• cocuk_metabolizma_hastaliklari `ailede_metabolizma_hastaligi`, `ebeveyn_akrabaligi`<br>• hematoloji `ailede_kan_hastaligi`<br>• nefroloji `ailede_bobrek_hastaligi`<br>Consanguinity is also one fact under three ids (`anne_baba_akrabaligi`, `ebeveyn_akrabaligi`, `akraba_evliligi`). Outside this wave; route to the owner so every such slot gets the same delivery and a register row. | NOTE (consistency) |
| pedodonti | Pedodonti extends `cluster.dental`, not `cluster.child_health`, so it inherits no paediatric cluster content (HB-C3). As wave 1–3 finding 25 noted, an adolescent who answers for themselves still hears "çocuğunuz". | observed |
| all 9 proposals | 0 digits, at most 14 words per sentence, 0 `sen` forms, guard-clean, exactly one "?" each. No `;`-joined ask, no "… mı ya da … mu?" and no when+how ask. Every non-Q1 item has a semantic slot id and a type. | PASS |
| all 9 proposals | No triage level and no RED rule. The generator writes only the stub rule, which carries the pending-value literal with `draft_needs_source` and is never compiled (verified: `pack_compilable` excludes it in all nine). Nothing extends `base.life_threat`. `candidate_flag` appears only in §3 prose, within invariant 1's `YELLOW_REVIEW` ceiling, and the generator does not carry it. | PASS |
| all 9 proposals | No base.intake duplicates. The specialty-only medicine item (antiresorptives, periodontoloji Q11 and protetik Q11) is kept, as agreed in wave 1–3 finding 5. | PASS |

**Decisions for the owner.** The first two need a physician of record (HB-C1); the paediatric reviewer (HB-C3) also joins the airway decision for pedodonti.

1. **Dental airway posture.** Should every dental pack carry the ungated airway ask that four sibling packs already carry, under one shared slot id? Or should none carry it, and it wait for `base.life_threat`?
2. **Ortodonti.** Is the pack self-report only, or does it need a parent-addressed variant?
3. **Duration slot (generator).** Wave 7 §E-2's `duration=omit` would serve yaşlı sağlığı, ortodonti and protetik here.

## B. How to read §C

- Every item takes the `gen:` line shown, on its own line under its `> "…"` quote. Q1 takes none.
- "text unchanged" means only the `gen:` line changes. "follow-up only" means only the `follow_up=` value changes.
- A split item gets its own header in the order shown (`**Q9a — …**`, `**Q9b — …**`), each with its own quote and `gen:` line. Update the §2.1 table row for each new item.
- A `pack:` line goes on its own line **inside §3**, before Q1. The generator reads it only inside the Candidate section, and each of its two texts must be one question with no digit.
- `ask_if` reads a slot declared earlier in the same pack. `||` is a top-level disjunction.
- Every text below was applied to scratch copies, rebuilt and guard-checked (see Method).

## C. Replacement lists

### geriatri — 4 text

- Q4 → "Düştükten sonra yerden kendi başınıza kalkamadığınız oldu mu?" · `gen: slot=dusme_sonrasi_kalkamama; type=boolean; ask_if=son_yil_dusme == true; follow_up=Düştükten sonra kalkmak için birinin yardımı gerekti mi?`
- Q6 → "Düşmekten endişe ediyor musunuz?" · `gen: slot=dusme_korkusu; type=boolean; follow_up=Düşme korkusu yaşadığınız oluyor mu?`
  - This is the GE-S8 construct. Update the proposal note "the WFG item is not translated literally": the new wording names the construct in four words and still follows no source sentence.
- Q9 → "İstemeden dışkı kaçırdığınız oluyor mu?" · `gen: slot=diski_kacirma; type=boolean; follow_up=Bağırsaklarınızı tutmakta zorlandığınız oluyor mu?`
  - Update the §2.1 label to "Faecal incontinence".
- Q13 → "Uzun süre yatmaktan ya da oturmaktan cildinizde kızarıklık ya da yara var mı?" · `gen: slot=basi_bolgesi_cilt; type=boolean; follow_up=Topuğunuzda, kalçanızda ya da kuyruk sokumunuzda kızarıklık ya da yara fark ettiniz mi?`
- Duration: the fixed ask fits a complaint visit. For a comprehensive geriatric assessment (CGA) referral, it can be left out once wave 7 §E-2 lands.
- PASS: Q1, Q2, Q3, Q5, Q7, Q8, Q10, Q11, Q12. Q8 and Q9 have an optional `text_first` line (§D-1).

### yasli_sagligi_poliklinigi — 2 text, 4 follow-ups; duration: clinician wording needed

- Q1 → "Bugün yaşlı sağlığı polikliniğine gelme nedeniniz nedir?" (no `gen:`; the "nedir?" ending selects the neutral follow-up)
- Q2 follow-up only · `gen: slot=gunluk_islerde_yeni_zorluk; type=boolean; follow_up=Eskiden kolayca yaptığınız bir işte artık zorlandığınız oluyor mu?`
- Q5 follow-up only · `gen: slot=agiz_dis_sorunu; type=boolean; follow_up=Dişleriniz ya da protezinizle yemek yerken zorlandığınız oluyor mu?`
- Q7 → "Düştüğünüzde hekime görünmenizi gerektiren bir yaralanma oldu mu?" · `gen: slot=dusme_yaralanma; type=boolean; ask_if=son_yil_dusme == true; follow_up=Düştükten sonra yaralandığınız için hekime gitmeniz gerekti mi?`
- Q9 follow-up only · `gen: slot=grip_asisi; type=boolean; follow_up=Bu yıl içinde size grip aşısı yapıldı mı?`
  - Gap 4 stays open: the clinician sets the window (calendar year or season).
- Q11 follow-up only · `gen: slot=hafif_kazada_kirik; type=boolean; follow_up=Basit bir düşme sonrasında vücudunuzda herhangi bir kemik kırıldı mı?`
- Duration: no source supports a duration question for a periodic review. Clinician wording is needed, or the slot is left out once wave 7 §E-2 lands.
- PASS: Q3, Q4, Q6, Q8, Q10, Q12. Q8 has an optional `text_first` line (§D-1).

### uyku_poliklinigi — 1 gate, 1 text, 1 follow-up, pack line

- Pack line: `pack: duration_ask=Bu şikâyetiniz ne zamandır var?; duration_follow_up=Hafta, ay ya da yıl olarak yaklaşık söyleyebilir misiniz?`
  - The ask is unchanged. The follow-up offers the units that U-S1's month-scale threshold needs, and the threshold stays in the source.
- Q5 text unchanged · `gen: slot=gunduz_islev_etkisi; type=boolean; ask_if=uykuya_dalma_guclugu == true || gece_uyanip_uyuyamama == true || erken_uyanma == true; follow_up=Kötü uyuduğunuz günlerde gün içinde kendinizi yorgun hissediyor musunuz?`
- Q6 → "Gün içinde istemeden uyuyakaldığınız oluyor mu?" · `gen: slot=gunduz_istemsiz_uyuma; type=boolean; follow_up=Gündüz uyanık kalmakta zorlanıyor musunuz?`
  - Same text and slot as obezite Q9. The note "names no situation" still holds.
- Q7 follow-up only · `gen: slot=yuksek_sesle_horlama; type=boolean; follow_up=Başkaları yüksek sesle horladığınızı söylüyor mu?`
- PASS: Q1, Q2, Q3, Q4, Q8, Q9, Q10, Q11, Q12, Q13.
  - Q8 already uses the shared `tanikli_apne` text.
  - Proposal gap 7 (children in the sleep clinic) stays open.

### klinik_norofizyoloji — 2 follow-ups, 1 delivery

- Q7 follow-up only · `gen: slot=kanama_bozuklugu; type=boolean; follow_up=Kanınızın geç pıhtılaştığı size daha önce söylendi mi?`
- Q13 text unchanged · `gen: slot=ailede_epilepsi; type=boolean; follow_up=Akrabalarınızdan sara hastalığı olan ya da nöbet geçiren biri var mı?; delivery=text_first`
  - Add a register row (INT-349, relatives' health) before promotion.
  - The follow-up keeps KN-S3's "nöbet, epilepsi" pair without narrowing the family.
- PASS: Q1, Q2, Q3, Q4, Q5, Q6, Q8, Q9, Q10, Q11, Q12. Q9–Q12 are correctly gated on Q8.
- Proposal gap 5 stands: EMG items are also asked of EEG referrals, and the reverse. A structured test-type slot needs a value set.

### ortodonti — 1 split; duration: clinician wording needed

- Q9 → two items:
  - Q9a text unchanged · `gen: slot=agiz_aliskanligi; type=boolean`
  - Q9b "Hangi alışkanlığınız olduğunu söyleyebilir misiniz?" · `gen: slot=agiz_aliskanligi_turu; type=string; ask_if=agiz_aliskanligi == true`
- Duration: gap 6 is confirmed. No source supports a duration question for an alignment concern. Clinician wording is needed, or the slot is left out once wave 7 §E-2 lands.
- PASS: Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q10, Q11, Q12.
  - Q11 cites "general orthodontic history" plus OR-S1 p. 77. That is weak but adequate for a history item.
  - The proxy variant is an owner decision (§A).

### pedodonti — 2 splits, pack line

- Pack line: `pack: duration_ask=Bu durumu ne zamandır fark ediyorsunuz?; duration_follow_up=Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?`
  - Same text as neonatoloji. Addressed to the parent and about the child. Resolves proposal gap 6.
- Q10 → two items:
  - Q10a text unchanged · `gen: slot=ozel_saglik_gereksinimi; type=boolean`
  - Q10b "Çocuğunuzun bu durumunu kısaca anlatır mısınız?" · `gen: slot=ozel_saglik_gereksinimi_aciklama; type=string; ask_if=ozel_saglik_gereksinimi == true`
- Q11 → two items:
  - Q11a text unchanged · `gen: slot=kalp_sorunu; type=boolean`
  - Q11b "Çocuğunuzun kalp sorununu kısaca anlatır mısınız?" · `gen: slot=kalp_sorunu_aciklama; type=string; ask_if=kalp_sorunu == true`
- PASS: Q1–Q9, Q12. "Çocuğunuz" is used consistently, and Q1's "nedir?" ending selects the neutral follow-up.

### periodontoloji — 1 text, 1 split, 1 text and split

- Q9 → "Size daha önce şeker hastalığı tanısı konuldu mu?" · `gen: slot=diyabet_tanisi; type=boolean`
  - Same text and slot as nefroloji, göz and nükleer tıp.
- Q11 → two items (same as protetik Q11):
  - Q11a text unchanged · `gen: slot=kemik_ilaci; type=boolean`
  - Q11b "Hatırlıyorsanız bu ilacın adını söyleyebilir misiniz?" · `gen: slot=kemik_ilaci_adi; type=string; ask_if=kemik_ilaci == true`
  - PD-S4 also asks about "possible future use". The wave 1–3 text captures past and current use only. The clinician may add a planned-use item.
- Q12 → two items:
  - Q12a "Kalp kapağınızla ilgili bir işlem ya da kalp iç zarı iltihabı geçirdiniz mi?" · `gen: slot=kalp_kapagi_endokardit; type=boolean`
  - Q12b "Bu kalp durumunu kısaca anlatır mısınız?" · `gen: slot=kalp_kapagi_endokardit_aciklama; type=string; ask_if=kalp_kapagi_endokardit == true`
  - Proposal gap 3 stays open: the congenital heart items and the European list.
- PASS: Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q10.

### protetik — 1 split; duration: clinician wording needed

- Q11 → two items (same as periodontoloji Q11):
  - Q11a text unchanged · `gen: slot=kemik_ilaci; type=boolean`
  - Q11b "Hatırlıyorsanız bu ilacın adını söyleyebilir misiniz?" · `gen: slot=kemik_ilaci_adi; type=string; ask_if=kemik_ilaci == true`
- Duration: a denture recall (PR-S3) or a new-denture visit has no complaint. Clinician wording is needed, or the slot is left out once wave 7 §E-2 lands.
- PASS: Q1–Q10, Q12.
  - Q3–Q5 and Q7 are correctly gated.
  - Proposal gap 5 (diabetes and endocarditis risk before implant surgery) stays a clinician decision.

### restoratif — 1 text, 1 split

- Q7 → "Gazlı içecek ya da meyve suyu gibi asitli içecekleri sık içiyor musunuz?" · `gen: slot=asitli_icecek; type=boolean`
- Q10 → two items, with pedodonti's slots and self-address:
  - Q10a "Dişlerinizi her gün sabah ve akşam fırçalıyor musunuz?" · `gen: slot=sabah_aksam_fircalama; type=boolean`
  - Q10b "Kullandığınız diş macununda florür var mı?" · `gen: slot=florurlu_macun; type=boolean; follow_up=Macunun kutusunda florür yazıyor mu?`
- PASS: Q1, Q2, Q3, Q4, Q5, Q6, Q8, Q9, Q11, Q12.
- Proposal gap 4: the owner has since approved sensitive items with `text_first`. If the clinician adds a vomiting item, it goes in as `delivery=text_first`, and the register (INT-349) records whether it is a new category. The clinician decision remains.

## D. Optional lines (not counted)

1. **Incontinence, `text_first`** (clinician choice, §A):
   - geriatri Q8 · `gen: slot=idrar_kacirma; type=boolean; follow_up=Tutamadan ya da farkında olmadan idrarınızın geldiği oluyor mu?; delivery=text_first`
   - geriatri Q9 (after §C) · `gen: slot=diski_kacirma; type=boolean; follow_up=Bağırsaklarınızı tutmakta zorlandığınız oluyor mu?; delivery=text_first`
   - yasli Q8 · the same line as geriatri Q8
2. **Dental airway ask** (only if the owner chooses the wave 1–3 posture, §A):
   - The source is endodonti.md's RCEM quote (wave 4–5 soru_7), cross-cited.
   - Use one slot id for the whole cluster. `nefes_yutkunma_guclugu` is the id in dis_hekimligi and endodonti.
   - periodontoloji, protetik, restoratif and ortodonti: "Nefes almakta ya da yutkunmakta zorlanıyor musunuz?" · `gen: slot=nefes_yutkunma_guclugu; type=boolean`
   - pedodonti: "Çocuğunuz nefes almakta ya da yutkunmakta zorlanıyor mu?" · `gen: slot=nefes_yutkunma_guclugu; type=boolean`. The paediatric reviewer (HB-C3) signs.
   - Both texts are guard-clean.

## E. Generator changes (scripts/dev/gen_specialty_packs.py)

1. **Refuse a narrative follow-up on a boolean slot** (wave 7 §E-3, not yet built). It would have caught all six items here.
2. **`duration=omit`** (wave 7 §E-2, not yet built). Needed for yaşlı sağlığı, ortodonti and protetik, and optional for geriatri CGA referrals and periodontal recall visits.
3. **Cross-pack slot-id check.** Across the review tree:
   - Refuse one slot id declared with two types (`kemik_ilaci`: string versus boolean).
   - Report one id with several texts, so clips can be shared.
4. **Self/proxy variants.** Geriatri, yaşlı sağlığı, ortodonti and uyku all need a parent- or relative-addressed text keyed on base `subject_role`. That is a DSL change and needs an ADR. Until then, each pack is self-address only.

## F. Checklist

- **Instruments:** none reproduced or paraphrased.
  - MMSE/MoCA, Epworth, STOP-Bang, GDS, Katz/Lawton and PSQI items are absent.
  - Construct overlaps (ISI, STOP-Bang, Berlin, IRLSSG, RBD single question, WFG/STEADI, AD8, 3Q/TMD, GOHAI/OHIP, AAPD caries-risk) are NOTE rows: capture them, never score them.
- **Monotonicity:** nothing is removed or relaxed, and nothing extends `base.life_threat`. Alarm inputs reach the note only (§A).
- **RED axes:** there are no RED rules.
- **Sourcing:**
  - Every kept item is supported by its proposal's §1.
  - Four asks are brought back to their source (geriatri Q4, Q6, Q9; periodontoloji Q12), and yasli Q11's follow-up drops body sites its source does not name (§C).
  - Weaker anchors are flagged and stay CANDIDATE: ortodonti Q11; the abstract-only PR-S5 and PD-S2; the undated lay pages GE-S2/S3/S5, U-S1/S2 and KN-S4.
- **Patient copy:**
  - `siz` throughout, at most B1, and one question per turn after the restoratif Q10 split.
  - No diagnosis, treatment or prognosis wording, and nothing alarming.
  - Pedodonti addresses the parent consistently once the pack line lands.
- **Invariant 18:**
  - One relatives-health item (klinik Q13) takes `text_first` and a register row.
  - Every slot that is emitted still needs its inventory annotation at promotion, as in every wave.
- **Invariant 22:** no numerals. The duration slots are `type: duration`, and no count, age or dose is asked as a number.
- **Goldens:** there are no rules, so no near-miss controls are needed. `make safety` and CODEOWNER review still apply when the packs are generated.
