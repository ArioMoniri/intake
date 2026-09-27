# Verification of the cluster packs, wave A (medical, surgical, sensory, women's health) — awaiting-clinical-review

Reviewer: independent clinical-content verifier (challenger), 2026-09-26. Every clinical item here is `awaiting-clinical-review`. Passing this review is not a physician signature, and the reviewer authored no clinical value.

Scope:

- `docs/evidence/proposals/{cluster_medical, cluster_surgical, cluster_sensory, cluster_womens_health}.md`.
- No cluster pack exists yet, under `packages/protocols/` or anywhere else in the repository. Every fix below lands in a proposal, except the owner items in §E.

Method:

- **Parsing.** Every proposal was parsed with `extract_questions` and `extract_pack_options` from `scripts/dev/gen_specialty_packs.py`, then built with `build_pack` against `base_slot_names()`.
  - All 72 items parse (18 per file). No `hold=` is present.
  - All four packs build. §E-2 records what they build *as*.
- **Patient copy.** Every ask, follow-up and fixed generator text went through the shipped Turkish PolicyGuard (`policy_guard_for(locale="tr")`, `filter(scripted=True)`). Each was also checked for words per sentence, digits, question marks and `sen` forms.
- **Replacements.** Every replacement in §C was applied to scratch copies and re-parsed, rebuilt and guard-checked. All four rebuild. Every replacement ask and follow-up is guard-clean, at most fifteen words per sentence, digit-free, and has exactly one question mark.
- **Gates.** Each `ask_if` was evaluated with the runtime's own parser (`protocols.triage.expr`), using the lookup shape of `IntakeEngine._lookup`. One gate was then run end to end through a real `IntakeEngine` (§A-1).
- **Collisions.** Slot ids were compared with every `gen:` line in all 99 proposals (1,258 parsed items). The comparison was made against the resolver's merge rule in `protocols/compile/resolve.py` `_merge_chain`:
  - a child section with the same id updates the parent's slots key by key;
  - so a branch slot with the same id replaces the cluster slot;
  - and a different id for the same fact is asked twice.
- **Sources.** Five sources were re-fetched and grepped (§H). Owner decision D3 was applied.

## BLUF

- **72 items reviewed**: 4 reason-for-visit items and 68 pack items. The generator's fixed follow-up and duration texts were checked for each file too.
- **20 REVISE, 52 PASS.** Proposed additions are not counted: women's health Q14a and Q14b (recommended), and medical Q19 (a clinician decision).

  | file | items | PASS | REVISE | REVISE items |
  |---|---|---|---|---|
  | cluster_medical | 18 | 11 | 7 | Q1, Q4, Q5, Q6, Q8, Q10, Q18 |
  | cluster_surgical | 18 | 13 | 5 | Q1, Q6, Q9, Q12, Q14 |
  | cluster_sensory | 18 | 14 | 4 | Q9, Q10, Q11, Q12 |
  | cluster_womens_health | 18 | 14 | 4 | Q1, Q2, Q14, Q16 |
  | **total** | **72** | **52** | **20** | |

- **Breaches:**
  1. **Bare-name gates never open at runtime** (HIGH; an engine defect, not a proposal defect).
     - The FSM keys answers by `<section>.<slot>`. It looks up a gate atom verbatim, so `diyabet_tanisi == true` reads Unknown and the step is never offered.
     - End-to-end result: after "evet" to the gate, the dependent step is absent from the frontier. With `sorular.diyabet_tanisi == true` it is offered.
     - Affected here: 28 gated items (medical 6, surgical 8, sensory 4, women's health 10), plus base's own `proxy_reported` and `lmp_date`. The whole post-op block, every pregnancy item and every chronic-disease delta are unreachable.
     - Nothing catches it. The generator's gate check and the FHIR emitter both accept bare names, and `protocols/types.py` documents bare atoms as legal.
     - Fix in the engine (§E-1). No `gen:` line changes for this.
  2. **The generator cannot emit a cluster candidate** (MEDIUM; fails closed).
     - `gen()` skips a slug with no `specialty/<slug>.yaml` draft.
     - Forced through `build_pack`, every cluster comes out wrong in five ways:
       - `layer: specialty`;
       - `extends: cluster.medical`, which for the medical cluster extends itself;
       - an id taken from a draft that does not exist;
       - a stub rule `rf.cluster_<x>_l0_taslak`;
       - output written under `review/specialty/`.
     - No `cluster.*` pack exists anywhere, yet all 91 specialty drafts extend one. The proposals report only the `extends` default.
  3. **Slot-id collisions** (MEDIUM). The same fact under a different id is asked twice once a branch pack resolves over its cluster.
     - **Fixed in the clusters (six):**
       - medical Q5/Q6 against nefroloji `yuksek_tansiyon_tanisi` (identical ask);
       - surgical Q6 against anesteziyoloji `onceki_anestezi_sorunu`;
       - surgical Q9 against anesteziyoloji `suregelen_rahatsizlik`;
       - sensory Q11 against odyoloji and sualtı `ani_isitme_azalmasi` (wave 9);
       - women's health Q16 against jinekolojik onkoloji `anormal_akinti`.
     - **Twelve rebinds are owed by sibling proposals** (§F).
  4. **One PolicyGuard hit** (MEDIUM). Surgical Q9 "…süregen bir hastalığınız var mı?" matches the diagnosis arm (`hastalığınız \w+`). It is the only guard failure in 72 asks and their follow-ups. Its follow-up also presumes a yes and asks for a name, which a boolean slot cannot hold.
  5. **A follow-up used as a second question** (MEDIUM).
     - `follow_up_tr` is spoken only after the extractor returns `clarification_needed`, and its answer binds to the same slot (`fsm._clarify`). It is a re-ask, not a coverage path.
     - Four items rely on it for a different fact:
       - sensory Q10: ear fullness, the presentation SEN-S7 calls primary for sudden hearing loss;
       - women's health Q14: post-menopausal bleeding;
       - medical Q18: change in function rather than current limitation;
       - medical Q4: redness or cracks rather than a non-healing wound.
     - A patient who answers the ask clearly never hears the follow-up.
  6. **Breadth** (MEDIUM).
     - While every branch draft is L0, the cluster is the pack a member branch is served (invariant 13).
     - `cluster.medical` also serves seven examination, report or prevention clinics: spor, sualtı, hava ve uzay, iş ve meslek, halk sağlığı, sigara bırakma and obezite. `cluster.surgical` serves anesteziyoloji, whose only visit type is `preop`.
     - Their Q1 plus the generator follow-up "Sizi hekime getiren en önemli şikâyetiniz nedir?" presume a complaint. Women's health Q1 says "konu, not şikâyet" and then inherits the same follow-up. Three Q1s are reworded to end in "nedir?".
     - The fixed duration ask still presumes a complaint (wave 9 §E-1, open).
- **Pregnancy first** (§G): the proposal misstates how it fails. Under the current engine `pregnancy_status` is always asked before any cluster item. The real failures are breach 1 and an unanswered `pregnancy_status`.
- **Researcher's notes** (§H): both hold.
  - HSGM's evaluation threshold is SKB ≥ 180 **or** DKB ≥ 110, verbatim. files/04 §2.1 says 180/120. Report only; the value belongs to the rule.
  - NG12 post-menopausal bleeding is now recs 1.5.12 and 1.5.14, "[2015, amended 2026]". `aile_hekimligi` and `cerrahi_onkoloji` still cite 1.5.10, which is now the ovarian-ultrasound recommendation.
- **Clean:**
  - No digits, no `sen` forms, no parentheses or slashes, at most fifteen words per sentence, and exactly one question mark per text.
  - No triage level, route, register, location or `candidate_flag` anywhere. The §2.1 red flags appear only as unencoded candidate rows, in all four files.
  - D3 items are `text_first`: surgical Q7 and Q11, and 16 women's health items. Medical and sensory collect no D3 category.
  - Every dependent item carries an `ask_if`, and every yes/no item is `boolean`.
  - No validated instrument item is reproduced (NOTE rows in §A).
  - Nothing extends `base.life_threat`.

## A. Findings

| where | finding | severity |
|---|---|---|
| all four; base | **§A-1. Bare-name gates never open at runtime.**<br>• `IntakeEngine._lookup(ref)` reads `self._states.get(ref)`, whose keys are `<section>.<slot>` step ids.<br>• A bare `diyabet_tanisi` is therefore Unknown, and `gate_truth` opens only on TRUE.<br>• Reproduced with a two-slot resolved protocol: after `sorular.diyabet_tanisi` = true, the frontier was `[]` for the gate `diyabet_tanisi == true` and `['sorular.hipoglisemi_atagi']` for the gate `sorular.diyabet_tanisi == true`.<br>• The engine tests use only qualified atoms (`oyku.belirti_var`), so this was never exercised.<br>• All 28 gates in these files are bare. So is every gate in every generated specialty pack, and base's `subject_role != 'kendim'` and `pregnancy_status != 'hayir'`.<br>• The proposals follow the documented DSL (types.py: "Section-qualified … or bare"), so the defect sits in the engine. | HIGH (engine; §E-1) |
| all four | **§A-2. The generator cannot emit clusters**, for the reasons in BLUF breach 2.<br>• Proposal gaps 9, 9, 7 and 10 name only the `extends` default.<br>• The fix needs a cluster mode: `layer: cluster`, `extends: base.intake`, `id: cluster.<name>`, output under `review/cluster/`, and no draft precondition.<br>• An emitted pack also needs the promotion story. `base.intake` is L0 and cannot build a plan today, because its red-flag probe slots carry no `ask_tr`, so `build_plan` raises. That is HB-C1 working as intended, and it means no chain in this review runs end to end yet. | MEDIUM (generator; §E-2) |
| all four; engine | **§A-3. Wrap-up is asked before every cluster item.**<br>• The frontier sorts by (priority, order). Base must-asks, including `open_questions`, `anything_else` and `summary_confirmed`, sort as MUST_ASK. Every generated slot sorts as DETAIL, including `basvuru_nedeni` (required but not `must_ask`).<br>• So the patient confirms the summary and then answers the reason question and 10–19 cluster items.<br>• The engine carries a WRAP_UP class at 8 but never mints it (plan.py docstring). | MEDIUM (engine; §E-1) |
| medical Q5, Q6 | `hipertansiyon_tanisi` is the same fact, with the identical ask, as nefroloji Q8 `yuksek_tansiyon_tanisi`, and nefroloji extends this cluster. Adopt the member's id; Q6's gate follows. tibbi_ekoloji `yuksek_tansiyon_oykusu` must rebind too (§F). | MEDIUM (collision) |
| surgical Q6 | `anestezi_sorunu` is the same fact as anesteziyoloji Q5 `onceki_anestezi_sorunu`, a cluster member. Adopt the member's id. | MEDIUM (collision) |
| surgical Q9 | Four defects:<br>• (a) PolicyGuard diagnosis hit on "hastalığınız var".<br>• (b) The follow-up "Bu hastalığın adını söyleyebilir misiniz?" presumes a yes and asks for a string, but the slot is a boolean.<br>• (c) anesteziyoloji Q3 `suregelen_rahatsizlik` is the same fact.<br>• (d) The §1 anchor (TARD PDF p. 7) names heart failure, ischaemic heart, stroke and kidney disease. "akciğer" and "şeker" are supported only on p. 9 (KOAH) and p. 11 ("İnsulin gerektiren diyabet"), which §1 does not quote.<br>Reworded to "rahatsızlığınız" with the member's id and a restating follow-up. Add the p. 9 and p. 11 quotes to §1. p. 11 also lists "İnme veya geçici iskemik atak", which no item asks; the clinician decides. | MEDIUM |
| sensory Q11 | `ani_isitme_kaybi` is the fact wave 9 standardised as `ani_isitme_azalmasi`: sualtı Q12, and odyoloji Q13 if adopted. odyoloji extends this cluster. Adopt `ani_isitme_azalmasi`; odyoloji's ungated definition then replaces the cluster's gated one. | MEDIUM (collision) |
| sensory Q10 | The "blocked ear" presentation of sudden hearing loss (SEN-S7: "The primary presenting symptom of SHL is a full or blocked ear") lives only in the follow-up, which a clear "hayır" never reaches (§BLUF 5). The gate now asks hearing loss or ear fullness in one concern, the pattern of `cinlama_isitme_azalmasi`. The slot is renamed, because no sibling uses `isitme_azalmasi`. The follow-up restates. Q11 is reworded to fit both. | MEDIUM |
| women's health Q14 | The follow-up "Âdetleriniz tamamen kesildiyse…" is the proposal's only route to post-menopausal bleeding (WH-S10). As a follow-up it is heard only after an unclear answer, and it binds a different fact to `adet_disi_kanama`. The siblings keep it separate: kadın hastalıkları Q6, jinekolojik onkoloji Q2–Q3 and aile Q8 all use `menopoz_sonrasi_kanama`. The follow-up now restates; Q14a and Q14b restore the fact under the sibling ids. | MEDIUM |
| women's health Q16 | `vajinal_akinti` is the same fact as jinekolojik onkoloji Q5 `anormal_akinti`, a member. Adopt the member's id. | MEDIUM (collision) |
| medical Q1; surgical Q1 | Breadth (§BLUF 6). The cluster is the served pack for preventive, report and preop members, and "hangi sağlık sorununuz için" / "hangi sorun için randevu aldığınızı" plus the complaint follow-up misframe those visits. Now kadın hastalıkları Q1's neutral text, ending in "nedir?". | MEDIUM (medical) / LOW (surgical) |
| women's health Q1 | The proposal chose "konu, not şikâyet", but a Q1 ending in "anlatır mısınız?" gets the generator's "…en önemli şikâyetiniz nedir?". Now kadın hastalıkları Q1's text. | MEDIUM |
| women's health Q2 | "Gebeliğiniz … doğrulandı mı?" presumes a pregnancy, yet the gate opens on "emin değilim". Now neutral: "Bir gebelik testi ya da ultrason gebe olduğunuzu gösterdi mi?". | LOW |
| medical Q18 | The ask is current limitation, which is what MED-S2 p. 67 and GINA support. The follow-up ("eskisinden daha çok") and the note ("whether function has changed") make it a change item. Follow-up restated as the state; the note's wording must follow. yaşlı sağlığı `gunluk_islerde_yeni_zorluk` is the change item, a different fact (NOTE, §F). | LOW |
| medical Q4 | The follow-up (redness, cracks, colour change) asks a broader fact than "non-healing wound" and binds it to `ayak_yarasi`. Restated. | LOW |
| medical Q8 | "KOAH" in the ask is unexplained; the proposal's gloss sits only in the follow-up (clinical content rule: no jargon without explanation). The follow-up "Böyle bir tanı" also narrows to KOAH only. Both reworded. | LOW |
| medical Q10 | "süregen" is above B1 and the pack's own gloss is "uzun süren" (Q8). Reworded. | LOW |
| surgical Q12 | The follow-up asks for a box name for a boolean. Mapping a brand name to "anti-inflammatory" is then a clinical classification by the extractor. Now a yes/no with generic examples; drug names pass the compiler's orthography expansion (invariant 22). | LOW |
| surgical Q14 | The follow-up narrows "any discharge" to purulent, so clear serous discharge could bind false. Now SUR-S3's own words, "sıvı … veya irin". | LOW |
| sensory Q9 | The follow-up drops the flashes half of the ask. Restated with both. | LOW |
| sensory Q12 | No recency frame, unlike every other symptom item. A vertigo episode years ago answers yes, which blurs its role as a stroke-family input (§2.2). "Son zamanlarda" added. | LOW |
| medical | files/04 §2.1 lists the CKD delta among the chronic-disease deltas. Q10 is a diagnosis gate only, and §4 gap 5 defers the thyroid delta but says nothing about CKD. Add a gap row. | LOW (prose) |
| medical | §2.1's "hyperglycaemia with vomiting" is the only medical red flag with no input item in the cluster (§4 gap 3 covers placement, not input). diyabet_poliklinigi already has a verified item for it (Q19 below, a clinician decision). | NOTE |
| surgical §2.2 | "Q2 uses the same slot id as four sibling proposals": only two do (ortopedi, fizyoterapi). el_cerrahisi uses `yaralanma_sonrasi_basladi` for the same fact (§F). | LOW (prose) |
| medical Q12, Q13; women's health Q4 | Base declares unaskable probe slots `rf_fever_high_persistent`, `rf_weight_loss_unintentional` and `rf_pregnancy_bleeding_pain`. When HB-C1 authors their wording, the base owner must read `son_gunlerde_ates`, `istemsiz_kilo_kaybi` and `gebelikte_kanama`, or give the probes those ids. Otherwise the patient hears both questions. | NOTE (base owner) |
| surgical, sensory §2.3 | Consistent with base: no neutral probe is drafted for rigidity, ischaemia, compartment syndrome, torsion, stridor or post-tonsillectomy bleeding. While the cluster is the served pack, those patterns therefore have no input. Sibling items exist for the clinician: ortopedi `orantisiz_agri`, `uyusma_solukluk_soguk`; uroloji `ani_siddetli_testis_agrisi`; KBB Q10 (stridor, `soru_N`). | NOTE (clinician) |
| women's health Q13, Q14 | Asked of pregnant patients (gap 9). The generator has no `skip_if` (`GEN_KEYS`). An available `ask_if` would be `pregnancy_status == 'hayir' \|\| gebelik_dogrulandi == false`. It hides the items when `pregnancy_status` is unanswered (Kleene Unknown), and it is inert until §A-1 is fixed. Keep them ungated; the clinician decides. | NOTE |
| women's health Q9 | NG133 and WH-S1 both include the feet or legs and NG133 says "sudden". The ask drops both and adds eyelids. The rationale (common late-pregnancy ankle oedema) is clinical, so the clinician confirms it. | NOTE |
| medical Q15 | "fails open toward asking" holds for the answer "bilmiyorum" only. An unanswered `immunosuppression` is Unknown and the gate stays shut. For a "bilmiyorum" answerer the ask's "tedavi sırasında" presumes treatment. | NOTE |
| medical Q9, Q18 | These are the constructs of GINA symptom-control items 3 and 4 (reliever use, activity limitation), in own words, with no frequency and no score. Never assemble a GINA control category from pack answers. | NOTE (instrument) |
| medical Q16 | Follows NICE CG76 rec 1.2.2 (missed doses, specific period, no blame). The MMAS-4/-8 adherence scales are licensed and similar in shape. Add no further adherence items and never score. | NOTE (instrument) |
| surgical Q8 | The STOP-Bang "snoring" and "observed" constructs in one yes/no (wave 8 precedent). Capture only; never score. | NOTE (instrument) |
| sensory | Every member branch inherits all 18 items. An odyoloji patient hears six ungated eye items and a göz patient seven ungated ENT items. Domain gates would cut this, but would also close cross-domain inputs such as sudden vision loss in an ENT booking. Clinician decision (HB-C5); no text proposed. | NOTE |
| all four | Turn cost. Unconditional cluster turns, including reason and duration: medical 13, surgical 11, sensory 15, women's health 9 (10 with Q14a). These come on top of base's 27 must-ask steps, against the fast-mode ceiling of 18 turns (04 §1), and before any branch items. HB-C5. | NOTE (clinician) |
| all four | Wave 1–3 finding 4 is still open: the generator's `basvuru_nedeni` and `sikayet_suresi` re-ask base `chief_complaint_text`, `onset_date` and `duration`. The women's health `pack:` line (copied from gebe polikliniği, accepted in wave 7) does not change that. | NOTE |
| gebe polikliniği; anesteziyoloji | An override replaces the whole slot, delivery included. gebe's voice `bebek_hareketi_hissediliyor`, `bebek_hareketlerinde_azalma` and `yuz_el_sisligi`, and anesteziyoloji's voice `ailede_anestezi_sorunu` (a D3 relatives item), silently undo the cluster's `text_first`. The women's health gap 6 decision must be made per slot id. | NOTE |
| all four | Proxy wording (gaps 10/10/8/11): no `subject_role`-keyed variants. Base's own `proxy_reported` gate is inert under §A-1. | NOTE |
| all four | D3: every `text_first` item needs its INT-349 row. Encryption, slot tagging and counsel's per-category basis must close before any is served (owner decisions, D3 "Not decided"). | NOTE (legal) |
| all four | 0 digits, 0 `sen`, 0 parentheses or slashes, at most 14 words per ask sentence, exactly one "?" per text. No `;`-joined ask and no "… mı ya da … mu?". Guard-clean apart from surgical Q9. | PASS |
| all four | No triage level, route, register or location. The §2.1 red flags appear as candidate rows only. `base.life_threat` is untouched. | PASS |

## B. How to read §C

- Every item takes the `gen:` line shown, on its own line under its `> "…"` quote. A Q1 takes none.
- "text unchanged" means only the `gen:` line changes.
- An added item gets its own header (`**Q14a — …**`) in the position shown, with its own quote and `gen:` line.
- Gates stay bare, per the documented DSL. If the engine owner chooses qualification instead of fixing `_lookup` (§E-1), the rewrite is mechanical: prefix pack slots with `sorular.` and base slots with their section, for example `pmh_fh_sh.pregnancy_status`. The generator's gate check accepts both forms.
- Q1 rewrites exist only to switch the generator's reason follow-up through its "nedir?" suffix rule. With a `reason_follow_up` pack key (wave 9 §E-2) they would not be needed.

## C. Replacement lists

### cluster_medical — 7 REVISE

- Q1 → "Bugünkü randevunuzda en çok konuşmak istediğiniz konu nedir?" (no `gen:`)
  - This is kadın hastalıkları Q1's text. The follow-up becomes "Bugünkü randevunuzun sebebini kısaca anlatır mısınız?".
- Q4 text unchanged · `gen: slot=ayak_yarasi; type=boolean; ask_if=diyabet_tanisi == true; follow_up=Ayağınızda uzun süredir kapanmayan bir yara ya da açıklık var mı?`
- Q5 text unchanged · `gen: slot=yuksek_tansiyon_tanisi; type=boolean; follow_up=Doktorunuz tansiyonunuzun yüksek olduğunu söyledi mi?`
- Q6 text unchanged · `gen: slot=evde_tansiyon_olcumu; type=boolean; ask_if=yuksek_tansiyon_tanisi == true`
- Q8 → "Size daha önce astım ya da KOAH denen akciğer hastalığı tanısı konuldu mu?" · `gen: slot=astim_koah_tanisi; type=boolean; follow_up=Doktorunuz size astım ya da KOAH olduğunu söyledi mi?`
- Q10 → "Size daha önce uzun süren bir böbrek hastalığı tanısı konuldu mu?" · `gen: slot=bobrek_hastaligi_tanisi; type=boolean; follow_up=Doktorunuz böbreklerinizin iyi çalışmadığını söyledi mi?`
- Q18 text unchanged · `gen: slot=gunluk_islev_kisitlanmasi; type=boolean; follow_up=Yemek, giyinme ya da ev işleri gibi günlük işlerde zorlanıyor musunuz?`
  - The note under Q18 should say "whether daily activities are limited", not "whether function has changed".
- PASS: Q2, Q3, Q7, Q9, Q11, Q12, Q13, Q14, Q15, Q16, Q17.
- Addition, a clinician decision (§A). Append in §3 after Q18:
  - **Q19 — Hyperglycaemia symptoms with vomiting** · source MED-S3 PDF p. 66 and Tablo 12.1 · "Çok susama ya da sık idrara çıkmayla birlikte bulantı, kusma veya karın ağrısı oluyor mu?" · `gen: slot=hiperglisemi_bulanti_kusma; type=boolean`
  - Same text and id as diyabet_poliklinigi Q8, so that pack overrides it cleanly.
  - It is ungated there. Gating it on `diyabet_tanisi` is the clinician's call.
- Duration: the fixed ask misfits the preventive and report members (§A). No sourced alternative exists; wave 9 §E-1 is still needed.

### cluster_surgical — 5 REVISE

- Q1 → "Bugünkü randevunuzda en çok konuşmak istediğiniz konu nedir?" (no `gen:`)
- Q6 text unchanged · `gen: slot=onceki_anestezi_sorunu; type=boolean; ask_if=onceki_ameliyat == true; follow_up=Uyanmakta güçlük, alerji ya da nefes sorunu gibi bir şey oldu mu?`
- Q9 → "Kalp, akciğer, böbrek ya da şeker hastalığı gibi süregelen bir rahatsızlığınız var mı?" · `gen: slot=suregelen_rahatsizlik; type=boolean; follow_up=Doktorunuzun söylediği, uzun süredir devam eden bir sağlık sorununuz var mı?`
  - Add TARD PDF p. 9 ("KOAH") and p. 11 ("İnsulin gerektiren diyabet", "İnme veya geçici iskemik atak") to SUR-S1's anchors. Stroke stays unasked unless the clinician adds it.
- Q12 text unchanged · `gen: slot=iltihap_giderici_kullanimi; type=boolean; follow_up=İbuprofen, naproksen ya da diklofenak gibi bir ağrı kesici kullandınız mı?`
  - The clinician may choose other generic examples. Brand names are not used.
- Q14 text unchanged · `gen: slot=yara_akintisi; type=boolean; ask_if=ameliyat_sonrasi_kontrol == true; follow_up=Ameliyat yaranızdan sıvı ya da irin gibi bir şey sızıyor mu?`
- PASS: Q2, Q3, Q4, Q5, Q7, Q8, Q10, Q11, Q13, Q15, Q16, Q17, Q18.
- Duration: fits complaint visits. It misfits anesteziyoloji (`preop` only) and post-op checks, and no sourced alternative exists (wave 9 §E-1).

### cluster_sensory — 4 REVISE

- Q9 text unchanged · `gen: slot=isik_cakmasi_ucusan_cisim; type=boolean; follow_up=Gözünüzün önünde ışık çakması ya da sinek gibi uçuşan şekiller oluyor mu?`
- Q10 → "Son zamanlarda işitmenizde azalma ya da kulağınızda tıkanıklık hissi oldu mu?" · `gen: slot=isitme_azalmasi_tikaniklik; type=boolean; follow_up=Eskisinden daha az duyuyor ya da kulağınızda dolgunluk hissediyor musunuz?`
- Q11 → "İşitmenizdeki bu değişiklik birden mi başladı?" · `gen: slot=ani_isitme_azalmasi; type=boolean; ask_if=isitme_azalmasi_tikaniklik == true`
  - The id now means "sudden onset of reduced hearing or ear fullness". That is the clinical intent SEN-S7 supports; the rule author reads it that way.
- Q12 → "Son zamanlarda kendinizin ya da çevrenizin döndüğü hissini yaşadınız mı?" · `gen: slot=donme_hissi; type=boolean; follow_up=Hareket etmediğiniz hâlde dönme ya da sallanma hissi oldu mu?`
- PASS: Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q13, Q14, Q15, Q16, Q17, Q18.
- Duration: complaint-led members, so the fixed ask fits.

### cluster_womens_health — 4 REVISE, 2 recommended additions

- Q1 → "Bugünkü randevunuzda en çok konuşmak istediğiniz konu nedir?" (no `gen:`)
- Q2 → "Bir gebelik testi ya da ultrason gebe olduğunuzu gösterdi mi?" · `gen: slot=gebelik_dogrulandi; type=boolean; ask_if=pregnancy_status != 'hayir'; follow_up=Evde ya da hastanede yapılan gebelik testi pozitif çıktı mı?; delivery=text_first`
- Q14 text unchanged · `gen: slot=adet_disi_kanama; type=boolean; follow_up=Âdet günleriniz dışında az da olsa kanama ya da lekelenme oldu mu?; delivery=text_first`
- Q16 text unchanged · `gen: slot=anormal_akinti; type=boolean; delivery=text_first`
- Additions, recommended (the clinician confirms). Insert after Q14:
  - **Q14a — Periods stopped for good (gate)** · archetype `OBSERVATION.story.v1` · source WH-S10 recs 1.5.12, 1.5.14 · "Menopoza girdiğiniz için âdetleriniz tamamen kesildi mi?" · `gen: slot=adet_kesildi; type=boolean; follow_up=Âdetleriniz yaş nedeniyle ya da bir ameliyattan sonra tamamen durdu mu?; delivery=text_first`
  - **Q14b — Bleeding after the menopause** · archetype `OBSERVATION.symptom_sign.v1` · source WH-S10 recs 1.5.12, 1.5.14 · "Âdetleriniz kesildikten sonra hiç lekelenme ya da kanama oldu mu?" · `gen: slot=menopoz_sonrasi_kanama; type=boolean; ask_if=adet_kesildi == true; follow_up=Menopozdan sonra az da olsa kan gördünüz mü?; delivery=text_first`
  - These are the jinekolojik onkoloji ids, so that pack overrides cleanly. Q14b's ask and follow-up are that proposal's own texts.
  - Q14a names the menopause on purpose. jinekolojik onkoloji's "Adet kanamalarınız tamamen kesildi mi?" is answered "evet" by a pregnant patient, which would file pregnancy bleeding as post-menopausal bleeding.
- PASS: Q3, Q4, Q5, Q6, Q7, Q8, Q9, Q10, Q11, Q12, Q13, Q15, Q17, Q18.
- Duration: the `pack:` line stands (wave 7 accepted the same line for gebe polikliniği).

## D. Proposal prose that must change with §C

- **cluster_medical:**
  - §2.2: record the nefroloji and enfeksiyon collisions (§F).
  - §3 counter: 18 drafted, plus Q19 if adopted.
  - §4: add a CKD-delta gap. Gap 9 is superseded by §E-2.
  - Q18 note: see §C.
- **cluster_surgical:**
  - §1 SUR-S1: add the p. 9 and p. 11 anchors.
  - §2.2: the sibling claim becomes "two proposals, and el_cerrahisi under another id".
  - Gap 9 is superseded by §E-2.
- **cluster_sensory:**
  - §2.1 row Q10: "hearing loss or ear fullness".
  - §2.2: the collision with odyoloji and sualtı is resolved by Q11's id.
  - §4 gap 4: drop "ear fullness", which Q10 now carries.
  - Gap 7 is superseded by §E-2.
- **cluster_womens_health:**
  - §0 and §4 gap 2: restate as §G.
  - §2.1: add rows Q14a and Q14b.
  - §2.2: add the collisions in §F.
  - Q14 note: post-menopausal bleeding moves to Q14b.
  - §3 counter: 20 items, 18 `text_first`.
  - Gap 10 is superseded by §E-2.

## E. Owner routing

1. **Engine (services/voice-runtime), two defects.**
   - `fsm._lookup` must resolve a bare atom to the unique step whose slot key matches, as `emit_fhir` already does (`links.update({slot.key: …})`). It must refuse a bare key that is ambiguous across sections. The alternative is to forbid bare atoms in the DSL and the generator.
   - Add a test with a bare gate.
   - Mint the WRAP_UP class for base's `expectations_wrapup`, so wrap-up follows pack items (§A-3).
   - Both cut across every pack. They need an issue, not a proposal edit.
2. **Generator (`scripts/dev/gen_specialty_packs.py`).**
   - Add a cluster mode (§A-2).
   - Carried over from wave 9 §E and still open: `duration=omit`, a `reason_follow_up` pack key, `;` inside hold values, and section-level delivery.
   - Also: `skip_if` is in the DSL but not in `GEN_KEYS` (women's health gap 9).
3. **Base owner.** Probe-slot binding for fever, weight loss and pregnancy bleeding (§A).
   - `lmp_date` cannot be widened for women's health by any pack: no op in the closed set writes `ask_if` (`set_attr` targets only the tightening table).
   - `vs.pregnancy_status` and `vs.immunosuppression` have no definition anywhere in the repository. The `'hayir'` literal in three gates (base `lmp_date`, medical Q15, women's health Q2) is unverified (proposal gaps 8 and 4).
4. **Taxonomy owner.** Seven examination, report or prevention clinics resolve to `cluster.medical`, and anesteziyoloji (`preop` only) to `cluster.surgical`. `cluster.allied_and_reports` is the pack files/04 §2.1 designed for purpose-of-visit flows. Should any of them move? One sentence answers it.

## F. Sibling rebinds (same fact, different id; the branch extends the cluster)

| cluster slot | sibling | sibling id | action |
|---|---|---|---|
| medical `son_gunlerde_ates` (= aile_hekimligi) | enfeksiyon_hastaliklari Q2 (identical ask) | `ates_var_mi` | enfeksiyon rebinds, and its Q3 gate follows |
| medical `istemsiz_kilo_kaybi` (8 siblings) | diyabet_poliklinigi Q5 | `aciklanamayan_kilo_kaybi` | diyabet rebinds |
| medical `yuksek_tansiyon_tanisi` (after §C) | tibbi_ekoloji Q8 | `yuksek_tansiyon_oykusu` | tibbi_ekoloji rebinds |
| medical `gece_terlemesi`, `istemsiz_kilo_kaybi`, `son_gunlerde_ates` | ic_hastaliklari Q5, Q3, Q4 | `soru_N` (no `gen:` lines, wave 9) | ic_hastaliklari adds `gen:` lines with the cluster ids. NOTE: Q4 (unexplained fever) is a near duplicate of `son_gunlerde_ates`, not the same fact; the clinician keeps or merges (PR #582 review §D-1) |
| surgical `travma_sonrasi_basladi` | el_cerrahisi Q2 | `yaralanma_sonrasi_basladi` | el_cerrahisi rebinds, or the clinician keeps the hand-specific fact |
| sensory `ani_isitme_azalmasi`, `donme_hissi`, `ses_kisikligi`, `boyunda_sislik` | kulak_burun_bogaz Q2, Q5, Q8, Q7 | `soru_N` | KBB adds `gen:` lines. Its Q7 still says "kitle" (wave 1–3 finding 14) |
| sensory Q2–Q9 | goz_hastaliklari Q2–Q11 (Q9 and Q11 identical to cluster Q7 and Q8) | `soru_N` | göz adds `gen:` lines with the cluster ids |
| sensory `donme_hissi` | odyoloji Q5 | `bas_donmesi_dengesizlik` (broader: dizziness or imbalance) | NOTE: near-duplicate; the clinician keeps or merges |
| women's health `gebelikte_siddetli_bas_agrisi` (= kadın hastalıkları) | gebe_poliklinigi Q11 (identical ask) | `siddetli_bas_agrisi` | gebe rebinds |
| women's health `gebelikte_gorme_bozuklugu` (= kadın hastalıkları) | perinatoloji Q11 | `gorme_bulanikligi` | perinatoloji rebinds |
| women's health `alt_karin_agrisi` (= kadın hastalıkları) | jinekolojik_onkoloji Q8 | `kasik_alt_karin_agrisi` | jinekolojik onkoloji rebinds |
| medical `gunluk_islev_kisitlanmasi` | yasli_sagligi Q2 | `gunluk_islerde_yeni_zorluk` (change, not state) | NOTE: different facts after §C |

Correct as claimed: `diyabet_tanisi`, `son_gunlerde_ates` (aile), `istemsiz_kilo_kaybi`, `gece_terlemesi` (hematoloji), `ailede_anestezi_sorunu`, `uzamis_kanama_oykusu`, `yutma_guclugu`, `tahmini_dogum_tarihi`, `bebek_hareketi_hissediliyor`, `bebek_hareketlerinde_azalma`, `yuz_el_sisligi`, `onceki_gebelik`, `gebelikte_kanama`, `adet_disi_kanama`.

## G. Pregnancy first (women's health): what base ordering allows

Facts from the resolver and the engine. No mechanism is proposed.

1. **Section order.** `_merge_chain` inserts sections root first, so every cluster or branch section follows all eight base sections. `pregnancy_status` sits in base section 6.
2. **Priority.** The frontier sorts by (priority, order). `pregnancy_status` is `must_ask`, so it is MUST_ASK class. Every generated slot is DETAIL.
   - So `pregnancy_status` is always offered before any women's health cluster item.
   - It is the 23rd of 27 base must-ask steps, after identity, the complaint, the HPI, medicines and new diagnoses.
   - The GATEKEEPER class (1) exists in the engine but nothing mints it. That is the DSL change base's header records (files/13 §14 item 13).
3. **What a cluster could do.** The closed op set's `reorder` permutes slots within one section. At most, a cluster could put `pregnancy_status` ahead of `new_diagnoses_since_last_visit` inside section 6. The generator emits no ops.
4. **The proposal's gap 2 misstates the failure.** "Q2–Q9 may run before pregnancy_status has an answer" does not happen under this engine. The real failures are:
   - (a) §A-1: the bare `pregnancy_status` gate never opens, so Q2–Q9 are never asked;
   - (b) a patient who leaves the `text_first` `pregnancy_status` unanswered reads Unknown, so Q2–Q9 stay shut. That fails closed toward *not* asking pregnancy items, and it is the clinician's to accept.
   - The ectopic candidate still reads base, as the proposal says.
5. **LMP for every women's health patient** (gap 2) needs a base edit (§E-3).

## H. The researcher's notes, judged

- **HSGM hypertension threshold.** The note is correct.
  - Re-fetched `ht-tarama-izlem-kilavuzu.pdf` (14 pp.). Verbatim: "SKB ≥ 180 mmHg veya DKB ≥ 110 mmHg olan hasta, hipertansif acil ve hipertansif ivedi durumlar açısından değerlendirmelidir." and "Semptomları bulunan hastalar hipertansif acil kabul edilip üst basamağa sevk edilmelidir."
  - files/04 §2.1 says "BP ≥ 180/120 with symptoms". The Ministry's diastolic figure is 110 and the condition is an OR. The diagnosis scheme above it cites "Türk Hipertansiyon Uzlaşı Raporu, 2019".
  - Report only. The value belongs to the rule (HB-C7); ACC/AHA 2025 is on the 04 §8.4 watch list.
  - Three further constraints for whoever writes the rule:
    - (a) 04 §8.1 rule 1 allows a trigger only on a BP the patient measured.
    - (b) Whether a patient-entered measured vital may appear in a note at all is HB-C14.
    - (c) The pack collects no BP value, and invariant 22 forbids free numeric entry. So the rule has no input except an e-Nabız or device import, which proposal gap 2 already says.
  - HSGM's "semptomları bulunan" names no symptoms; the rule author must source the list.
- **NICE NG12 renumbering.** The note is correct.
  - Re-fetched NG12 (last updated 15 April 2026). Post-menopausal bleeding is rec 1.5.12 (aged 55 and over) and rec 1.5.14 (under 55), both "[2015, amended 2026]". Rec 1.5.10 is now "If an ultrasound scan suggests ovarian cancer…".
  - Stale citations: `aile_hekimligi.md` (lines 59 and 171) and `cerrahi_onkoloji.md` (lines 57, 120 and 185). aile's quote "Refer women using a suspected cancer pathway referral for endometrial cancer if…" is also no longer verbatim: 2026 reads "Refer women, and trans men and non-binary people with female reproductive organs using…". Both need a re-snapshot.

## I. Checklist

- **Source spot-check.** Five sources were re-fetched and every quoted anchor checked was found:
  - HSGM hypertension guide: 4 of 4.
  - NICE NG12: 8 of 8, including 1.10.1, 1.10.6, 1.8.1, 1.8.2, 1.11.4 and 1.13.2.
  - TARD preoperative guideline: 6 of 6. p. 3 is the only page quoted in §1 that was not re-checked; pp. 9 and 11 support surgical Q9 but are not quoted.
  - TOD "Mutlaka kapsamlı bir göz muayenesi…": 6 of 6, plus the "perde" item named in gap 4.
  - Doğum Öncesi Bakım Yönetim Rehberi 2018: all eight danger signs and "Tahmini doğum tarihi".
  - Not re-fetched, and checked against each proposal's §1 only: GINA 2026, NICE NG253, NG125, CG76, NG126, NG133, NG201, NG194 and NG88, BSH 2008, AAO-HNS, TKBBV, TEMD and HYP.
  - The cited wave 1–3 findings 4, 5, 13, 14, 19, 20 and 25 exist and say what the proposals say.
- **Instruments.** No PHQ, GAD, C-SSRS, HAQ-DI, WHO-5, GINA ACT, MMAS, STOP-Bang, HHIE-S or DHI item is reproduced. Construct overlaps are NOTE rows: capture them, never score them.
- **Monotonicity.** Nothing removed or relaxed, and nothing extends `base.life_threat`. Every alarm input stays an input only.
- **RED axes.** No rules exist. Register and location are unassigned by design.
- **Patient copy.**
  - `siz`, B1 and one question per turn in every text.
  - Jargon is glossed after §C: KOAH (medical Q8), dren (surgical Q17).
  - "narkoz", "ultrason" and "menopoz" are lay words.
- **Invariant 22.** No numeral anywhere. The due date is a date picker; no week, BP, glucose or stop interval is spoken.
- **Invariant 18 (D3).** After §C, 20 `text_first` items: surgical Q7 and Q11, and 18 in women's health. Each needs an INT-349 row before it is served.
- **Goldens.** No rules, so no near-miss controls. `make safety` and CODEOWNER review apply once a cluster candidate can be generated (§E-2).
