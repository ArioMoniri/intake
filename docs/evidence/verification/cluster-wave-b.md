# Verification of the cluster proposals, wave B (child health, mental health, dental, allied and reports) — awaiting-clinical-review

Reviewer: independent clinical-content verifier (challenger), 2026-09-26. Every clinical item here is `awaiting-clinical-review`; passing this review is not a physician signature. No clinical value was authored by the reviewer.

Scope:

- `docs/evidence/proposals/{cluster_child_health, cluster_mental_health, cluster_dental, cluster_allied_and_reports}.md`
- Read against: CLAUDE.md invariants 2, 7, 10, 17, 18, 21, 22 and the clinical content rules; files/04 §2.1; `packages/protocols/base/intake.yaml`; owner decisions D3 (`owner-decisions-2026-09-26.md`); files/13 §13; the 91 review packs in `packages/protocols/review/specialty/` and every proposal in `docs/evidence/proposals/`.
- No cluster pack exists yet, so every fix lands in the proposal.

Method:

- Each proposal was parsed with `extract_questions` and `extract_pack_options` from `scripts/dev/gen_specialty_packs.py`. All 65 items parse, and none carries `hold=` as drafted.
- `build_pack` was run with base slots and a stand-in draft (`extends: base.intake`), because `packages/protocols/specialty/cluster_*.yaml` does not exist (§E-1). All four build.
- Every ask, follow-up and pack-line text went through the shipped Turkish guard: `policy_guard_for(locale="tr", profile=residency_tr)` and `inspect_sentence`. Each was also checked for word count, digits and question marks.
- Every cluster slot id and ask text was compared with every review pack and every proposal. Each match was classed: same id and text; same id with another text or type; same text under another id. The specialty packs of each cluster were also read by eye for one fact asked under two ids.
- Every replacement in §C was applied to scratch copies, re-parsed, rebuilt with `build_pack` and guard-checked. Every new gate was parsed with `protocols.triage.expr.parse_when`, including `subject_role == 'kendim'`, the literal base `proxy_reported` already uses.
- Sources were checked against each proposal's own §1 quotes. One external check was made for child Q10: WHO's definition of chest indrawing, as quoted in Clin Infect Dis 2017;65(9):1560 (§G).

## BLUF

- **65 items reviewed:** 17 child health, 18 mental health, 18 dental and 12 allied. The three `pack:` duration lines (child, mental, allied) were also checked.
- **6 REVISE, 58 PASS, 1 open owner decision** (dental Q10).

  | file | items | PASS | REVISE | open | notes |
  |---|---|---|---|---|---|
  | cluster_child_health | 17 | 15 | 2 (Q10 text, Q13 gate) | 0 | pack line kept |
  | cluster_mental_health | 18 | 14 | 4 (Q15, Q16 gate; Q17, Q18 hold) | 0 | pack line kept |
  | cluster_dental | 18 | 17 | 0 | 1 (Q10 airway posture) | fixed duration ask kept |
  | cluster_allied_and_reports | 12 | 12 | 0 | 0 | pack line kept; Q3 D3 scope note |
  | **total** | **65** | **58** | **6** | **1** | |

- **Breaches:**
  - **Chest-indrawing text describes the wrong sign** (MEDIUM, child Q10). "kaburgalarının arası" is intercostal indrawing. WHO IMCI, whose charts CH-S1 adapts, defines chest indrawing as inward movement of the lower chest wall below the ribs. A parent who sees that sign may answer "hayır".
  - **A gate can close the highest-stakes rash item** (MEDIUM, child Q13). A parent who does not call petechiae "döküntü" answers "no" to Q12, and Q13 is then never asked. The specialty `cocuk_sagligi_ve_hastaliklari` asks Q13 ungated.
  - **Two non-D3 sensitive items are emitted without a hold** (MEDIUM, mental Q17, Q18). The proposal itself says they need the owner.
    - Q17 cannot separate a persecutory belief from a real threat, so it elicits a safeguarding disclosure, which files/13 §13 forbids.
    - Q18 is the proposal's own risk-to-others item. No base rule reads it, and no D3 category covers it.
    - Wave 9 held non-D3 items (hava ve uzay Q15, halk sağlığı Q10); these two are held the same way.
  - **Sensitive self-report items reach adult proxy sessions** (MEDIUM, invariant 18, mental Q15, Q16). A relative at AMATEM who hears "…kullanıyor musunuz?" answers about themselves. Their own substance use or psychotic experience then lands in the patient's record, and D3 open item 3 has no basis for that. Each is gated `subject_role == 'kendim'`.
  - **The proxy note is wrong about inheritance** (MEDIUM, mental §0(c)). ÇEMATEM is left out, although its pack speaks to the parent. "Run its own L1 pack" does not help, because `_merge_chain` (`slots.update`) still passes all 17 cluster slots to an L1 specialty.
  - **Collision lists are incomplete** (MEDIUM). One fact is asked twice once these specialties extend the cluster:
    - child: neonatoloji (fever, drowsiness), çocuk metabolizma, çocuk genetik, plus four packs with opposite polarity;
    - mental: klinik psikoloji (medicine, prior therapy), AMATEM (support, functioning);
    - dental: endodonti (thermal pain).
  - **Airway question misaddressed in pedodonti** (MEDIUM, latent). The gate opens on the child's pain, because pedodonti re-declares `dis_agrisi` for the child. The parent then hears a self-addressed airway question and answers for themselves. It stays latent while INT-223 refuses every under-18 path.
  - **Base questions reach the guardian in child sessions** (MEDIUM, routed to the base owner). These include `pregnancy_status` ("Şu anda gebe olma ihtimaliniz var mı?"), the HPI "Şikâyetiniz…" items and `weight_kg`. The guardian's own data would enter the child's record.
  - **The generator cannot emit a cluster** (MEDIUM, engineering). `gen()` skips any slug without `packages/protocols/specialty/<slug>.yaml`. It writes only to `review/specialty` and hard-codes `layer: specialty`. The proposals name the layer and `extends` problems but not the missing-draft skip.
  - **Minor prose defects** (LOW):
    - The mental §0 does not record files/04 §2.1's "full PHQ-9/GAD-7 by default" as a delivery requirement.
    - The allied §0 offers `suppress_slot` as a way to make base HPI conditional. On a `must_ask` slot that op is a hard compile error.
- **Clean:**
  - No digits, no `sen` forms, at most fifteen words per sentence and exactly one "?" per ask. The guard is clean on all 65 asks, the two follow-ups, the three pack lines and every replacement.
  - No triage level, route, register, location or trigger. Nothing extends or relaxes `base.life_threat`.
  - No PHQ-9, GAD-7, C-SSRS or WHO-5 item is reproduced or paraphrased. No low-mood or loss-of-interest item and no suicide or self-harm question appear in any of the four.
  - Every yes/no item is `boolean` with a semantic slot id, and every dependent item is gated. The one ungating in §C is deliberate, for safety.
  - Every files/04 §2.1 topic is covered or explicitly deferred. The child cluster's guardian proxy, age bands and adolescent private section are recorded as engineering requirements, correctly apart from the additions in §D.
- **Owner decisions still needed:**
  1. Mental Q17: whether any persecutory-ideation item can be asked without eliciting safeguarding (psychiatrist and owner).
  2. Mental Q18: the "risk to others" category. Also whether the app should ask about harm to others at all, given that the cluster declines self-harm because the app cannot respond (owner and psychiatrist).
  3. Mental Q16: the verifier reads it as ordinary special-category health data and releases it. The owner confirms, or holds it.
  4. Dental airway posture (wave 8 decision 1). The cluster adds a third option: asked, gated on pain or swelling.
  5. Allied Q3: D3's "report purpose" names sağlık kurulu, but the cluster reaches seven branches including Adli Tıp. It is read as within D3, and the owner narrows it if not.
  6. The self/proxy ADR (wave 8 §E-4), and whether the `subject_role` gates in §C are lifted once it lands.

## A. Findings

### A.1 cluster_child_health

| where | finding | severity |
|---|---|---|
| Q10 | The text describes intercostal indrawing only. WHO IMCI defines chest indrawing as "abnormal inward movement of subcostal tissue … during inspiration" (CID 2017, §G), and IMCI training separates it from intercostal retraction. CH-S1's "Göğüs çekintisi" comes from the IMCI charts, so the item does not describe the sign its source names. Adding "altı" captures both. The reviewer did not re-fetch CH-S1; the paediatrician confirms against the text around CH-S1 PDF p. 103. The same fix belongs in cocuk_sagligi_ve_hastaliklari Q6 and cocuk_gogus_hastaliklari (§F). Otherwise their re-declaration replaces the cluster text with the narrower one. | MEDIUM (source fidelity; alarm item) |
| Q13 | Gated on `dokuntu_var`. Non-blanching rash often starts as pin-point spots that parents call "nokta" or "benek", not "döküntü" (cocuk_hematolojisi asks them as "noktalar"). A "no" to Q12 would then close the highest-stakes item. The specialty asks it ungated, so the cluster and the specialty would behave differently. Ungated in §C. Alternative for the paediatrician: keep the gate and widen Q12 to "döküntü, leke ya da nokta". | MEDIUM (gate on an alarm item) |
| §4 gap 8 | Incomplete. See the full list in §F.<br>• Missing same-polarity twins: neonatoloji `ates` and `asiri_uykululuk`; cocuk_metabolizma `uykulu_halsiz`; cocuk_genetik `alisilmadik_halsizlik`.<br>• Missing overlaps: `sivi_tutamama`, `kusma_beslenme_reddi` and `tekrarlayan_kusma_beslenememe`, against `her_seyi_kusma` and `beslenme_sivi_alimi`. Four growth items also overlap with `buyume_endisesi`.<br>• Missing opposite-polarity twins: `beslenmede_azalma`, `islak_bez_azalmasi`, `az_cis` and `idrar_azalmasi`. | MEDIUM |
| Q5, Q7 | Polarity: `false` is the alarm direction, unlike every other symptom slot in the pack. Four specialty twins use the opposite polarity, so renaming them to the cluster id would silently invert them. The paediatrician picks one polarity for hydration items across child_health before any rename. Q5 also merges two constructs: CH-S1's danger sign is inability to drink or breastfeed, while NG143 1.2.6 has "poor feeding" (amber). A febrile child who eats less but drinks well answers "hayır". The paediatrician chooses the construct. The collision with `emebiliyor_icebiliyor` forces one choice anyway. | NOTE (clinician decision) |
| §0 adolescent private section | Recorded correctly as an engineering requirement, with no item drafted. That is fail-closed, and HB-L20 `adolescent_private_guardian_default` is named. Two additions, in §D:<br>• CH-S1 requires the interview "ergenle yalnız", so the requirement is a channel the guardian can neither see nor hear, not only a switch of speaker. files/13 §13 names third-party presence as the largest moderator.<br>• INT-223 refuses every under-18 path today (docs/PROGRESS.md), so the whole cluster is unreachable until HB-L20 relaxes.<br>`text_only` for the whole section is stricter than files/13 §13 requires for substance and sexual items. That is acceptable, and it means no clip. | PASS (with prose additions) |
| §0 guardian proxy | Proxy-only address is recorded correctly, and the self variant needs the wave 8 §E-4 ADR. But base's self-addressed `must_ask` items reach the guardian in every child_health session:<br>• `pregnancy_status`, which is `text_first`;<br>• the HPI "Şikâyetiniz…" items;<br>• `weight_kg`, `smoking_status` and `alcohol_use`.<br>The guardian's own answers would then enter the child's record, which is D3 open item 3. The proposal's "Not repeated from base: … pregnancy" assumes base covers the child; it does not. Route to the base owner with the §E-4 ADR. | MEDIUM (base owner) |
| §0 age input | The age input the cluster needs is already asked as a clinical `date` slot in neonatoloji Q2 (`bebegin_dogum_tarihi`). Whether a clinical birth-date slot may feed an age band is HB-L20 `dob_collection_mandatory` / `unverified_dob`, not an engineering choice. Record that in §0. | NOTE |
| Q2 | "var mı" misses a fever that settled today, and Q3 then never opens. cocuk_enfeksiyon uses "oldu mu". Resolving the `ates_oldu` collision picks one text; the paediatrician decides. | NOTE |
| Q14 | "Bilmiyorum" is a common true answer about vaccinations, and a boolean cannot store it. Base `anticoagulant_use` uses a code with bilmiyorum. The generator has no `code` type, so no change is made; the paediatrician may ask for one. | NOTE |
| breadth | Eleven acute danger-sign items are asked ungated at every visit, including routine chronic follow-ups (endocrine, genetics, urology). Gating them on a parent's "is the child ill?" would suppress capture of the signs themselves, so they stay ungated. Ordering and budget belong to the frontier engine. | NOTE |
| Q1–Q17, pack line | Every ask is reused from a verified child_health pack, except Q12. Four texts are new and clean: Q12, the Q14 and Q16 follow-ups, which restate their asks, and the pack follow-up, which adds "ay" to the gastroenteroloji text and carries no clinical content. | PASS |

### A.2 cluster_mental_health

| where | finding | severity |
|---|---|---|
| Q17 | "Başkalarının size zarar vermek istediğini düşündüğünüz oluyor mu?" A person under real threat (partner violence, stalking) truthfully answers "yes". The item cannot tell persecutory ideation from a threat, so it elicits a safeguarding disclosure. files/13 §13 says the product "should not attempt to elicit a disclosure at all". No lay wording separates the two; that separation is interview work. Held. **Category:** persecutory ideation, which in lay answers merges with personal safety. D3 approves forensic and personal safety only for adli_tip's own design. **Owner and psychiatrist decision needed.** | MEDIUM (safeguarding; held) |
| Q18 | The proposal's own "safety of others" item. `base.life_threat` has no risk-to-others rule (§4 gap 4), so a "yes" has no response path. The cluster declines a self-harm item for that reason (NG222 1.2.8: the clinician asks directly). **Category:** aggression and risk to others, which is not a D3 category; the closest, forensic and personal safety, covers the patient as a victim, not as a risk. Rewording it as a symptom ("çabuk sinirlenme") would shadow GAD-7's irritability item. Held. **Owner and psychiatrist decision needed.** | MEDIUM (category; held) |
| Q16 | **Category, as the verifier reads it:** psychiatric symptom history. That is ordinary special-category health data, which every symptom slot already carries (`Slot` inventory annotation `special_category_health`). It is not a D3-type new category, so no category decision is needed, and it is released `text_first`. The owner may overrule and hold it. The wording resembles the auditory-hallucination items of the MINI psychosis module and the Prodromal Questionnaire ("hear things other people cannot"). No lay wording of the construct avoids that. It is capture only, never scored and never summed with Q17, as with wave 6's mood-questionnaire note. | NOTE (instrument); owner confirms category |
| Q15, Q16 | Both are self-addressed and ask about the answerer's own sensitive behaviour or experience. In an adult proxy session, such as a relative at AMATEM, the relative answers about themselves. That third person's data would land in the patient's record, and D3 open item 3 says another data subject needs a separate basis. Gated `ask_if=subject_role == 'kendim'`, the literal base `proxy_reported` uses. This fails closed until the proxy ADR lands. `ruh_sagligi_ve_hastaliklari` Q12 re-declares `diger_madde_kullanimi` ungated and needs the same gate (§F). Q15 is otherwise D3-approved (non-alcohol substance use), `text_first`, and needs its INT-349 row. | MEDIUM (invariant 18) |
| §0(c), §4 gap 9 | Two errors, corrected in §D and §E-3:<br>• ÇEMATEM is omitted, although its pack speaks to the parent ("çocuğunuz"), as Çocuk ve Ergen Ruh Sağlığı's does.<br>• "Until then that branch must suppress these items or run its own L1 pack" does not work. An L1 specialty still inherits all 17 cluster slots through `_merge_chain`, and before L1 the branch runs the cluster directly.<br>Latent today, because INT-223 refuses every under-18 path. | MEDIUM |
| collisions (none listed) | The proposal says "nothing is asked twice". That holds for ruh_sagligi_ve_hastaliklari only:<br>• klinik psikoloji `psikiyatrik_ilac_kullanimi` duplicates Q11 `ruh_sagligi_ilaci`, and cluster Q12 and Q13 then gate on the wrong twin;<br>• klinik psikoloji `onceki_psikoterapi` duplicates Q8;<br>• AMATEM `destek_cevresi` duplicates Q7;<br>• AMATEM `gunluk_yasam_etkisi` duplicates Q6.<br>Renames are in §F. | MEDIUM |
| §0 instrument path | files/04 §2.1 sets "full PHQ-9/GAD-7 by default" for this cluster. Base `screening` gates PHQ-9 and GAD-7 behind PHQ-2 and GAD-2 (files/04 §1). The proposal does not record the difference as a delivery requirement for the engineer. C-SSRS "full" is correctly left out as BLOCKED (HB-L2). | LOW |
| Q3, Q4, Q5, Q6, Q14, Q18 | These share constructs with instrument items:<br>• Q3, Q4 and Q5 with PHQ-9's sleep, appetite and energy items;<br>• Q6 with the unscored PHQ-9 and GAD-7 difficulty item;<br>• Q14 with a mood-disorder questionnaire item;<br>• Q18 with GAD-7's irritability item.<br>Recall and answer form differ, and none is a PHQ-2 core item. Wave 6 recorded the same notes. Engineering must also make sure confirm-don't-reask never maps these answers onto an instrument item or pre-fills one. | NOTE |
| Q9 | Near base `treatments_tried`, but distinct: base asks what was tried for this complaint; Q9 asks what helped among past treatments. | NOTE |
| Q1–Q14 | No low mood, no loss of interest and no suicide or self-harm item. No PHQ-9, GAD-7, C-SSRS or WHO-5 text. Q12's lead-in is MH-S7's no-blame framing and gives no advice. | PASS |

### A.3 cluster_dental

| where | finding | severity |
|---|---|---|
| Q10 | The **open owner decision** (wave 8 §A, decision 1). Waves 1–3 ask it ungated; wave 8's five packs leave it to `base.life_threat`, which has no adult airway rule. The cluster offers a third posture, gated on pain or swelling.<br>• If the owner chooses to ask, the cluster closes the wave 8 gap: periodontoloji, protetik, restoratif, ortodonti and pedodonti declare no airway slot and would inherit this one.<br>• Not gating on trismus is correct (DE-S7).<br>• The gate on Q7 includes "dilinizin altında", which fits sublingual spread.<br>The three possible `gen:` lines are in §C. | OPEN (owner) |
| Q10 in pedodonti | Pedodonti re-declares `dis_agrisi` for the child, so the gate opens on the child's pain. The parent then hears "Nefes almakta ya da yutkunmakta zorlanıyor musunuz?" and answers for themselves: a "no" about the wrong person on an airway item. If the owner keeps Q10, pedodonti must re-declare `nefes_yutkunma_guclugu` with wave 8's proxy text (§F) before any under-18 path opens. | MEDIUM (latent: INT-223) |
| pedodonti (other items) | The other self-addressed items would record the parent's own history in the child's record: bleeding after dental work, bone medicine, knocked-out teeth. The proposal's §0(c) records this. It is the wave 8 §E-4 owner decision, and latent under INT-223. | NOTE |
| §4 gap 6 | Incomplete:<br>• endodonti `sicak_soguk_agri` asks cluster Q3's fact (`dis_hassasiyeti`) under another id, so thermal pain is asked twice;<br>• restoratif `isirinca_ani_agri` (pain on release) is related to Q6 but a distinct sign; keep it;<br>• `kemik_ilaci` is `string` in agiz_dis_ve_cene_cerrahisi and agiz_dis_cene_radyolojisi. Cluster Q17's gate `kemik_ilaci == true` would then compare a string, so in those two packs either the chain is refused or `kemik_ilaci_adi` is never asked. Wave 8 §E-3 applies. | MEDIUM |
| duration | The fixed "Bu şikâyetiniz ne zamandır var?" is kept, and recall visits have no complaint to time. No sourced alternative exists; `duration=omit` (wave 7 §E-2) is still not built. | NOTE |
| Q13 | DE-S6's "other relevant medical complications" supports a bleeding-history item only indirectly. The text is dis_hekimligi's, already verified. | NOTE |
| Q1–Q9, Q11–Q18 | Texts are reused from verified dental packs. Dependents are gated. Q16 covers past and current use (DE-S5). Q18 is never scored, and no dental-anxiety scale item is reproduced. | PASS |

### A.4 cluster_allied_and_reports

| where | finding | severity |
|---|---|---|
| Q3 | D3 approves "report purpose" naming sağlık kurulu. The cluster carries it to seven branches, including Adli Tıp, where the purpose is forensic. Read as within D3, as wave 9 read iş ve meslek Q17–Q18, and the owner narrows it if not. Q1 already asks the topic in free text, so Q3 adds little extra elicitation there. The legal-reviewer confirms two things: whether AL-S1 governs forensic reports at all, and that the export bar (Madde 8(5)) covers Adli Tıp. | NOTE (D3 scope; legal) |
| §0 minimal HPI | "files/12 ops (`suppress_slot`) … could make the base HPI conditional" is wrong. `suppress_slot` on a `must_ask` slot is a hard compile error (`SuppressSlotOp`, files/12 §3.2). What remains is a base-level gate owned by the base owner, or a visit-type rule. | LOW (prose) |
| Evde Sağlık (proxy) | The Evde Sağlık pack speaks to the carer ("Hastanın…"). Cluster Q7 and Q10–Q12 are self-addressed, so a carer would report their own function, not the patient's. In a report context that is false functional data. Wave 8 §E-4 owner decision. | MEDIUM (owner) |
| Q11 | AL-S2 Madde 8(1)(ı) names the wheelchair; "baston, yürüteç" are examples beyond the quote. The item stays within AL-S1 Madde 8(6)'s "fonksiyon kaybı". Sağlık kurulu Q8, held in wave 9, uses the same id with a broader, still unsourced text (hearing aid, prosthesis). If it is released, it replaces this text in sağlık kurulu, so release it with the cluster text or keep it held. | NOTE |
| Q2 | Always "yes" in the report-only branches (Sağlık Kurulu, Adli Tıp). One wasted turn. | LOW |
| Q10 | Base `caregiver_present` asks whether someone helps; Q10 asks whether help is needed (AL-S2). Both are kept, as in wave 9. | NOTE |
| Q7 | Aşı `bugun_hasta` ("Bugün kendinizi hasta hissediyor musunuz?") is near Q7. It is kept as the vaccine-deferral construct, but the patient may hear a repeat. | LOW |
| pack line | Neutral ("Bu konu ne zamandır devam ediyor?", sosyal_pediatri's ask), with no clinical content. For a vaccination visit the real fix is `duration=omit`. | NOTE |
| Q1–Q12 | No score, no ICF code, no "bağımlı" status and no verdict. Q5 records only whether the official form was filled. | PASS |

### A.5 Across all four

| where | finding | severity |
|---|---|---|
| generator | `gen(slug)` returns "skip: no L0 draft" for every cluster slug, because `packages/protocols/specialty/cluster_*.yaml` does not exist. It would also write into `review/specialty/` with `layer: specialty`. The proposals note `layer` and `extends` only (§E-1). | MEDIUM (engineering) |
| fixed slots | `basvuru_nedeni` and `sikayet_suresi` duplicate base `chief_complaint_text`, `onset_date` and `duration` (wave 1–3 finding 4, still open). A cluster extends base directly, so every cluster double-asks reason and duration. | NOTE |
| cross-cluster ids | None of the 65 slot ids collides with `cluster_medical`, `cluster_sensory`, `cluster_surgical` or `cluster_womens_health`. | PASS |
| patient copy | `siz` throughout, and the child cluster addresses the parent. At most fifteen words, one "?", no digits. Guard-clean. | PASS |
| triage, invariants 1, 7, 21 | No level, route, register, location or trigger. §2.3 of each file is a review list only. Nothing extends `base.life_threat`. | PASS |

## B. How to read §C

- Each item takes the `gen:` line shown, on its own line under its `> "…"` quote. "Text unchanged" means only the `gen:` line changes.
- The `subject_role == 'kendim'` gate reuses the literal of base `proxy_reported` (`subject_role != 'kendim'`). If the value-set code changes, both change together. It is an interim fail-closed gate until the self/proxy ADR (wave 8 §E-4); the owner may lift it then.
- Hold reasons contain no `;`, because `_parse_gen` splits on it (wave 9 §E-3).
- Every `text_first` item needs its data-inventory row under INT-349. For D3 items, the note line uses the wave 7 wording: "invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349)."

## C. Replacement lists

### cluster_child_health — 1 text, 1 gate removed

- Q10 → "Nefes alırken çocuğunuzun kaburgalarının altı ya da arası içeri çekiliyor mu?" · `gen: slot=gogus_icine_cekilme; type=boolean`
  - Eleven words, guard-clean. The slot id is kept.
  - Replace the note's "Same text as cocuk_sagligi_ve_hastaliklari" with: "IMCI lower-chest-wall sign plus intercostal indrawing. cocuk_sagligi and cocuk_gogus to adopt this text (verification cluster-wave-b §F)."
- Q13 text unchanged · `gen: slot=solmayan_dokuntu; type=boolean`
  - The note becomes: "Ungated, as in cocuk_sagligi_ve_hastaliklari. A parent may not call pin-point spots a rash."
  - Q12's note drops "Gate for Q13".
- PASS: Q1–Q9, Q11, Q12, Q14–Q17, and the pack line.

### cluster_mental_health — 2 gates, 2 holds

- Q15 text unchanged · `gen: slot=diger_madde_kullanimi; type=boolean; ask_if=subject_role == 'kendim'; delivery=text_first`
  - Keep the D3 and INT-349 note.
- Q16 text unchanged · `gen: slot=baskalarinin_duymadigi_sesler; type=boolean; ask_if=subject_role == 'kendim'; delivery=text_first`
  - Note: "invariant 18: special_category_health like every symptom slot (verifier's reading, owner may overrule). INT-349 storage and encryption prerequisites apply. Capture only, never scored, never summed with any other item."
- Q17 text unchanged · `gen: slot=zarar_gorme_kuskusu; type=boolean; ask_if=subject_role == 'kendim'; delivery=text_first; hold=a yes cannot separate a persecutory belief from a real threat so the item elicits a safeguarding disclosure (files/13 §13) and awaits a psychiatrist and the owner`
- Q18 text unchanged · `gen: slot=ofke_kontrol_guclugu; type=boolean; ask_if=subject_role == 'kendim'; delivery=text_first; hold=risk to others is not a D3 category and base.life_threat has no rule for it so it awaits the owner and a psychiatrist`
- PASS: Q1–Q14 and the pack line.
- The emitted pack has 16 items: Q1 plus Q2–Q16. The scratch rebuild confirms it; both holds report as warnings.

### cluster_dental — no text change; one open decision

- Q10, by the owner's airway decision (wave 8 decision 1):
  - **ask, gated (as drafted):** `gen: slot=nefes_yutkunma_guclugu; type=boolean; ask_if=yuz_cene_sisligi == true || dis_agrisi == true`
  - **ask, ungated (waves 1–3 posture):** `gen: slot=nefes_yutkunma_guclugu; type=boolean`
  - **leave to base.life_threat:** delete Q10, its §2.1 row and its §2.2 row, and change the counter to 17.
  - In the two "ask" cases, pedodonti must re-declare the slot for the child (§F).
- PASS: Q1–Q9 and Q11–Q18.

### cluster_allied_and_reports — no change

- PASS: Q1–Q12 and the pack line. Q3's D3 scope is the owner's (§A.4).

## D. Proposal prose that must change with §C

- **cluster_child_health:**
  - §0, adolescent private section. Add: "The section runs only on a channel the guardian can neither see nor hear (CH-S1 'ergenle yalnız'; files/13 §13 third-party moderator). INT-223 refuses every under-18 path today, so this cluster is unreachable until HB-L20 relaxes."
  - §0, age bands. Add: "neonatoloji Q2 already asks a birth date as a clinical slot. Whether a clinical date may feed the age band is HB-L20 (`dob_collection_mandatory`, `unverified_dob`)."
  - §0, "Not repeated from base". Add: "Base's self-addressed `must_ask` items (HPI, `pregnancy_status`, `weight_kg`) reach the guardian in every session of this cluster. That is a base-owner defect (verification cluster-wave-b §A.1), and this cluster does not fix it."
  - §4 gap 8: replace with the §F child list.
  - §2.1: add "(IMCI lower-chest-wall sign)" to Q10's row.
- **cluster_mental_health:**
  - §0, sensitive items: "Q15 (D3) and Q16 (ordinary special-category health data, verifier's reading) are `text_first` and gated to self-report. Q17 is held for the safeguarding boundary and Q18 for the category. Both await the owner."
  - §0(c):
    - name ÇEMATEM beside Çocuk ve Ergen Ruh Sağlığı;
    - replace "or run its own L1 pack" with "an L1 pack still inherits every cluster slot (`_merge_chain`). Each branch needs `suppress_slot` on all cluster slots, and must not run the cluster directly, before any under-18 path opens (verification §E-3)";
    - add the missing requirement: "files/04 §2.1 sets full PHQ-9 and GAD-7 by default for this cluster, which is a delivery setting on the instrument path. C-SSRS stays BLOCKED (HB-L2)."
  - Add a §4 collision gap with the §F mental list.
  - §3: the counter becomes "18 drafted, 16 active, 2 held".
  - §5 Inv. 18: match the §0 wording above.
- **cluster_dental:**
  - §4 gap 6: add endodonti `sicak_soguk_agri` and the `kemik_ilaci` gate consequence.
  - §0 airway bullet: add "In pedodonti the gate opens on the child's pain and the ask addresses the parent. Pedodonti must re-declare the slot for the child."
- **cluster_allied_and_reports:**
  - §0 minimal HPI: replace "files/12 ops (`suppress_slot`)" with "a base-level gate (suppress_slot on a must_ask slot is a hard compile error, files/12 §3.2)".
  - §0 report purpose: add "D3 names sağlık kurulu. Carrying Q3 to Adli Tıp and the other allied branches is read as within D3, and the owner narrows it if not. The legal-reviewer confirms whether AL-S1 governs forensic reports."
  - §0(c): name Evde Sağlık's carer address as a live adult-proxy case, not only a child one.

## E. Structural and generator requirements (engineer and owner)

1. **A cluster path in the generator.** `gen()` needs `packages/protocols/specialty/<slug>.yaml` and writes `review/specialty/<slug>.yaml` with `layer: specialty` and a default `extends: cluster.medical`. Emitting a cluster needs:
   - a cluster slug to pack id mapping (`cluster_child_health` → `cluster.child_health`);
   - `layer: cluster` and `extends: base.intake`;
   - a review location for clusters.

   Until then none of the four can be generated.
2. **The self/proxy ADR** (wave 8 §E-4) is now blocking in six places: the pedodonti airway item, ÇEMATEM, Çocuk ve Ergen Ruh Sağlığı, Evde Sağlık, AMATEM relatives, and base `must_ask` items in child sessions. The §C gates cover only the two sensitive self-report items.
3. **Branch exclusion from a cluster.** For ÇEMATEM and Çocuk ve Ergen Ruh Sağlığı, each L1 pack needs `suppress_slot` (allowed on non-`must_ask` slots) on every cluster slot. Before L1, the branch runs the cluster directly, so it must not be routed to `cluster.mental_health` until then. That conflicts with invariant 13's "resolves to an L1+ pack or its cluster pack". INT-223's under-18 refusal keeps the conflict latent; the owner decides before HB-L20 relaxes.
4. **`duration=omit`** (wave 7 §E-2, still not built): the dental recall visit and allied vaccination and education visits need it.
5. **Refuse one slot id declared with two types** (wave 8 §E-3). `kemik_ilaci` now also breaks the cluster's Q17 gate in two packs.
6. **Instrument-path settings.**
   - mental_health: full PHQ-9 and GAD-7 by default.
   - allied_and_reports: screening off unless the person opts in.
   - Confirm-don't-reask must never map mental Q3–Q6, Q14 or Q18 onto an instrument item.
7. **Concept-level de-duplication against base** (wave 1–3 finding 4): `basvuru_nedeni` and `sikayet_suresi`.

## F. Specialty-side follow-ups (not counted above; route to each proposal's owner)

A same-polarity twin takes the cluster id and keeps its own text, so its re-declaration replaces the cluster slot and the fact is asked once. An opposite-polarity twin must not be renamed until the paediatrician fixes one polarity; a rename would invert it.

**child_health:**

- Same polarity; rename to the cluster id:
  - neonatoloji Q10 `ates` → `ates_var_mi`
  - neonatoloji Q11 `asiri_uykululuk` → `uykulu_tepkisiz`
  - cocuk_metabolizma_hastaliklari `uykulu_halsiz` → `uykulu_tepkisiz`
  - cocuk_genetik_hastaliklari `alisilmadik_halsizlik` → `uykulu_tepkisiz`
  - cocuk_enfeksiyon_hastaliklari `ates_oldu` → `ates_var_mi`, with its `ates_suresi` gate becoming `ates_var_mi == true`
  - cocuk_enfeksiyon_hastaliklari `asiri_uykulu_halsiz` → `uykulu_tepkisiz`. The paediatrician decides whether `uyandirma_zorlugu` stays separate.
  - cocuk_enfeksiyon_hastaliklari `suregen_hastalik_tanisi` → `suregen_tani`
  - cocuk_gogus_hastaliklari `gogus_ice_cekilmesi` → `gogus_icine_cekilme`, with the §C Q10 text
- Same id, text to align: cocuk_sagligi_ve_hastaliklari Q6 takes the §C Q10 text.
- Opposite polarity; a polarity decision comes first:
  - neonatoloji `beslenmede_azalma` and `islak_bez_azalmasi`
  - cocuk_gastroenterolojisi `az_cis`
  - cocuk_nefrolojisi `idrar_azalmasi`
- Construct choice for the paediatrician: `emebiliyor_icebiliyor` (CH-S1's danger sign) against `beslenme_sivi_alimi` (feeding as usual).
- Overlaps; the paediatrician decides whether the cluster item stays where a specialty asks its own:
  - vomiting: `sivi_tutamama`, `kusma_beslenme_reddi`, `tekrarlayan_kusma_beslenememe` against `her_seyi_kusma`
  - growth: `buyume_ergenlik_endisesi`, `yavas_kilo_alma`, `buyume_geriligi`, `kilo_alamama` against `buyume_endisesi`
  - breathing: neonatoloji `nefes_zorlanmasi` against `inleme` and `gogus_icine_cekilme`
- The branch-diagnosis items (`kalp_tanisi`, `noroloji_tanisi` and the rest) are narrower than `suregen_tani`. Acceptable.

**mental_health:**

- Rename to the cluster id:
  - klinik_psikoloji_poliklinigi `psikiyatrik_ilac_kullanimi` → `ruh_sagligi_ilaci`. Cluster Q12 and Q13 then gate correctly.
  - klinik_psikoloji_poliklinigi `onceki_psikoterapi` → `onceki_ruh_sagligi_destegi`
  - amatem `destek_cevresi` → `sosyal_destek`
  - amatem `gunluk_yasam_etkisi` → `islevsellik_etkilenimi`
- Add `ask_if=subject_role == 'kendim'` to ruh_sagligi_ve_hastaliklari Q12 (`diger_madde_kullanimi`) and klinik psikoloji `zorlanmada_madde_kullanimi`.
- ÇEMATEM and Çocuk ve Ergen Ruh Sağlığı: structural, not a rename (§E-3).

**dental:**

- endodonti `sicak_soguk_agri` → `dis_hassasiyeti`, with its `agri_sonra_suruyor` gate becoming `dis_hassasiyeti == true`.
- agiz_dis_ve_cene_cerrahisi and agiz_dis_cene_radyolojisi: `kemik_ilaci` becomes boolean plus `kemik_ilaci_adi` (wave 8 §C). Then apply the proposal's gap 6 renames: `nefes_yutma_zorlugu`, `yuz_cene_dil_alti_sislik`, `sislikle_ates`, `agiz_acma_zorlugu` and `uzamis_kanama_oykusu`.
- pedodonti, if the owner keeps the airway ask: "Çocuğunuz nefes almakta ya da yutkunmakta zorlanıyor mu?" · `gen: slot=nefes_yutkunma_guclugu; type=boolean`. This is wave 8 §D-2's text, and the paediatric reviewer (HB-C3) signs it.

**allied_and_reports:**

- saglik_kurulu Q8, held: release it only with the cluster Q11 text, or keep the hold.

## G. Checklist

- **Sources.**
  - Every item was checked against its proposal's §1 quotes, and each item is supported by the quote it cites.
    - Allied Q11's examples go beyond AL-S2's wheelchair.
    - Dental Q13 is indirect.
    - Child Q17 and mental Q1 are general history.
  - One external check, for child Q10. Clin Infect Dis 2017;65(9):1560 (academic.oup.com/cid/article/65/9/1560/3865856) quotes WHO IMCI's definition as inward movement of subcostal tissue, and treats intercostal retraction as a separate sign.
  - CH-S1 itself was not re-fetched.
  - The verbatim-snapshot requirement stands for every source before sign-off.
- **Instruments:**
  - No PHQ-9, GAD-7, C-SSRS, WHO-5, GİDR or dental-anxiety scale item is reproduced or paraphrased.
  - Construct resemblances are NOTE rows: mental Q3–Q6, Q14, Q16 and Q18, and dental Q18. None is scored or summed.
  - PHQ-2 and GAD-2 are never called Turkish-validated, and GAD-7's Turkish cut-off is stated as 8.
- **Monotonicity:** nothing is removed or relaxed, and nothing extends `base.life_threat`. Alarm items are inputs only.
- **RED axes:** there are no RED rules. The child cluster's CALM reference restates files/02 §5.3 and assigns nothing.
- **Patient copy:** `siz`, B1, one question per turn, at most fifteen words, and no diagnosis, treatment or prognosis wording. Child items address the parent.
- **Invariant 22:** no numerals. Fever and complaint durations are `type=duration`. No weight, temperature, count or dose is asked.
- **Invariant 18:**
  - Mental Q15 is D3-approved and Q16 is ordinary health data by the verifier's reading; both are `text_first`, gated to self-report, and need INT-349 rows.
  - Mental Q17 and Q18 are held for the owner.
  - Allied Q3 is D3 and note-only, and its export bar is the legal-reviewer's.
  - D3's open items (encryption, counsel per category, slot tagging) apply before any is served.
- **Goldens:** there are no rules, so no near-miss controls are needed. `make safety` and CODEOWNER review apply when the packs are generated.
