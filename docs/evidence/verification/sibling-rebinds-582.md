# Verification of PR #582, sibling slot-id rebinds (INT-353 extension) — awaiting-clinical-review

Reviewer: independent verifier (challenger), 2026-09-26. The reviewer did not write the PR and assumed it could be wrong. Every clinical item here is `awaiting-clinical-review`. Passing this review is not a physician signature, and the reviewer authored no Turkish text and no clinical value.

Scope:

- PR head `5c79ebce` on `int-353-sibling-rebinds`, one commit on `066fb8a5`.
- 22 proposals under `docs/evidence/proposals/`, the 22 matching candidates under `packages/protocols/review/specialty/`, `tests/protocols/test_gen_specialty_packs.py`, and the `docs/evidence/INT-353.md` extension.
- Checked against the §F lists of `cluster-wave-a.md` and `cluster-wave-b.md`, wave 8 §A and §C (`kemik_ilaci`), and the proposals `cluster_dental.md` §4 gap 6 and `cluster_womens_health.md` §4 gap 6.
- The earlier `specialty-wave*.md` files have no rebind list. Their §F sections are checklists. Their slot-id rows (wave 7 §A, wave 8 §A) cover clip sharing between two siblings, outside any extends chain, except `kemik_ilaci`, which is in scope here.

Method:

- **Diff.** Every candidate was loaded at `HEAD~1` and `HEAD`. Removed and added ids, and changed `type`, `ask_if`, `delivery`, ask and follow-up, were listed per pack.
- **Same fact.** Every re-declared cluster slot was compared field by field with its cluster candidate (`review/cluster/<name>.yaml`).
- **Gates.** Each chain was merged the way `_merge_chain` merges it: the cluster first, then the branch with `slots.update`, so an override keeps the cluster's position. Every gate atom was then checked to be declared at an earlier position, or in base. The same check was run on the `HEAD~1` tree.
- **Other trees.** The old ids were grepped across `review/`, `specialty/` and `base/`.
- **Near twins.** A near-twin scan over all 91 chains used `difflib` ratio ≥ 0.80 on the ask text.
- **Text.** Every changed Turkish string was byte-compared (`od -c`) with the verification text.
- **Regeneration.** `gen_specialty_packs.py` was run for the 22 slugs, then for every proposal, and `git status` was checked after each.
- **Tests and chain.** `uv run pytest tests/protocols -q` was run. Chain validation used a copied scratch tree (`base/`, `review/cluster` as `cluster/`, `review/specialty` as `specialty/`), `load_registry` and `validate_packs`.
- **Mutations.** Six mutations were made on candidates backed up with `cp`, each followed by the test file. Every file was restored from its backup, `cmp` was clean, and `git status` was empty afterwards.

## BLUF

- **Verdict: PASS-with-fixes.** Defects: 0 HIGH, 2 MEDIUM, 6 LOW. The NOTE rows are for the owner and the clinician.
- **§F coverage is complete and exact.**
  - All 37 rebinds, the `kemik_ilaci` split, both chest-indrawing texts and both `subject_role == 'kendim'` gates match the documents.
  - Nothing was invented beyond §F. Every item §F leaves to a human was left alone, including the four hydration twins.
- **Regeneration is byte-identical.** The 22 candidates and the INT-297 baseline match the generator output. A full run of all 96 proposals changed nothing, and the served trees are untouched.
- **Tests and chain.** `tests/protocols` passes (685). The chain validates with 0 findings. The PR also removes two gate-order defects and two type clashes that the validator cannot see (§E).
- **MEDIUM 1: ic_hastaliklari Q4 is not the same fact.**
  - Its ask is "nedenini bilmediğiniz" (unexplained) fever over "son zamanlarda". It now replaces the cluster's unconditional "Son günlerde ateşiniz oldu mu?" in that chain.
  - A patient whose fever has a known cause now records no fever at all.
  - The commit message's "(identical asks only)" is true for göz only.
- **MEDIUM 2: the rebind tests are blind to a swap.** Swapping two rebound ids inside one pack stays green, reproduced twice (Mutation runs, below). The tests never pin which question an id binds to.
- **Owner-visible delivery and gate changes** (§C):
  - gebe Q11 and perinatoloji Q11 go from `text_first` to voice, and the cluster's `gebelik_dogrulandi == true` gate drops for both;
  - KBB `ani_isitme_azalmasi` loses its `isitme_azalmasi_tikaniklik == true` gate;
  - ağız, diş ve çene cerrahisi `agiz_acma_guclugu` loses its `yuz_cene_sisligi == true || dis_agrisi == true` gate;
  - two substance items gain `subject_role == 'kendim'`;
  - 25 cluster asks are replaced by branch wording in their chains.

## A. Findings

| where | finding | severity |
|---|---|---|
| ic_hastaliklari Q4 → `son_gunlerde_ates` | **Not a same-fact merge.**<br>• Branch: "Son zamanlarda nedenini bilmediğiniz bir ateşiniz oldu mu?" (NG12 rec 1.10.1, unexplained fever).<br>• Cluster medical Q12: "Son günlerde ateşiniz oldu mu?" (any recent fever).<br>• The branch narrows the construct to unexplained fever and moves the window from days to an open "son zamanlarda".<br>• Before the PR the ic chain asked both. Now a patient with a known-cause fever, such as a known infection, answers "hayır", and the chain holds no fever input.<br>• `son_gunlerde_ates` is the slot cluster-wave-a §A names for the base `rf_fever_high_persistent` probe binding.<br>• The PR followed cluster-wave-a §F's row literally, so the error starts in §F. The commit message's "(identical asks only)" does not hold for this row. | MEDIUM |
| tests, `SIBLING_REBINDS` | **A wrong binding inside one pack passes.**<br>• The test checks four things: the new id exists, the old id is gone, the cluster declares the id with the same type, and no gate reads the old id. It never checks which question carries the id.<br>• Swapping `istemsiz_kilo_kaybi` ↔ `son_gunlerde_ates` in ic_hastaliklari: 63 passed.<br>• Swapping `donme_hissi` ↔ `ses_kisikligi` in KBB: 63 passed.<br>• `test_no_chain_asks_one_text_under_two_ids` catches a swap only where the text is identical to the cluster's. That leaves ic, KBB, and the non-identical rows in neonatoloji, çocuk enfeksiyon, klinik psikoloji and AMATEM exposed. | MEDIUM |
| ic_hastaliklari Q5 → `gece_terlemesi` | "Geceleri sizi uyandıracak kadar çok terlediğiniz oldu mu?" has no recency frame, and its threshold is waking. Cluster Q14 asks "Son zamanlarda … çarşafınızı ıslatacak kadar". The window widens to ever and the threshold changes, and the branch text now replaces the cluster's in this chain. | LOW |
| KBB Q5 → `donme_hissi` | "Başınızın ya da etrafın döndüğünü hissettiğiniz oldu mu?" drops the "Son zamanlarda" that cluster-wave-a §C added to sensory Q12, so that an old vertigo episode does not answer yes to a stroke-family input. In the KBB chain the window is now ever again. | LOW |
| KBB Q7 → `boyunda_sislik` | "…kendiliğinden kaybolmayan bir şişlik ya da kitle…" (persistent) replaces the cluster's "yeni fark ettiğiniz … şişlik ya da sertlik" (new). The time framing differs, and the unexplained jargon "kitle" (wave 1–3 finding 14, still open) replaces plain text in this chain. The INT-353 row names "kitle" but not the replacement. | LOW |
| amatem Q6 → `islevsellik_etkilenimi` | "Bu durum günlük yaşamınızı ya da sağlığınızı etkiliyor mu?" puts health harm into the cluster's functioning slot ("işinizi ya da günlük sorumluluklarınızı"). One slot now carries two facts in the AMATEM chain. | LOW |
| klinik_psikoloji Q8 → `onceki_ruh_sagligi_destegi` | The branch asks regular sessions with a psychologist or psychiatrist. The cluster asks about support from a physician or a psychologist. The narrower answer now opens the cluster's `onceden_iyi_gelen` gate, so a patient who had support without regular sessions no longer hears "what helped". | LOW |
| commit message; INT-353.md delivery note | The commit says the ic, KBB and göz `gen:` lines are "identical asks only". Only göz Q7, Q9 and Q11 are identical; ic Q3–Q5 and KBB Q2, Q5, Q7, Q8 are not. The INT-353 delivery note reports the `text_first` → voice change for gebe and perinatoloji but not the dropped `gebelik_dogrulandi == true` gate. | LOW (evidence accuracy) |
| 37 rebinds, all of them | Every rebind §F calls for is applied with the id §F names. For ic and KBB the pairing is positional, and it matches the PR. The dental targets come from cluster_dental §4 gap 6, which §F cites. No rebind is outside §F. | PASS |
| göz Q2, Q3, Q4, Q5, Q8 | These are left unassigned, and the INT-353 row says why. The deferral is correct: Q4 and Q5 cannot share `isik_cakmasi_ucusan_cisim` (duplicate id refused), Q3 includes transient loss, which cluster Q3 does not, and Q8 includes the skin around the eye. The göz chain still asks vision change, floaters or flashes, and redness twice, and göz Q6 and Q10 have no cluster twin. | NOTE (clinician, HB-C1) |
| hydration twins | neonatoloji `beslenmede_azalma` and `islak_bez_azalmasi`, çocuk gastroenteroloji `az_cis` and çocuk nefroloji `idrar_azalmasi` are unchanged, and a test pins them. No rename inverts polarity anywhere in the PR. | PASS |
| type changes | The ten `soru_N` slots (ic 3, KBB 4, göz 3) go from `string` to `boolean`, matching the cluster. `kemik_ilaci` goes from `string` to `boolean`, plus `kemik_ilaci_adi` (`string`), per wave 8 §C. No other type changes. | PASS |
| widened or narrowed, as §F anticipated | These are recorded for the rule author and the clinician, with no change asked:<br>• `uykulu_tepkisiz` gains "halsiz" in çocuk metabolizma, çocuk genetik and çocuk enfeksiyon. In çocuk enfeksiyon, "hard to wake" stays in Q8 `uyandirma_zorlugu`.<br>• `ates_var_mi` is "oldu mu" in çocuk enfeksiyon and "fark ettiniz mi" in neonatoloji, against the cluster's "var mı" (B §A.1 Q2).<br>• `suregen_tani` narrows to a chronic-disease diagnosis.<br>• `dis_hassasiyeti` drops "tatlı" and uses "ağrıyor", where the cluster uses "sızlıyor".<br>• `islem_sonrasi_uzun_kanama` gains "ya da yaralanma".<br>• `ses_kisikligi` gains "ya da değişiklik".<br>• KBB's ungated `ani_isitme_azalmasi` has no "fullness" half, which cluster-wave-a §A anticipated for odyoloji.<br>• diyabet `istemsiz_kilo_kaybi` uses "son zamanlarda" where the cluster uses "son aylarda". | NOTE |
| fiziksel_tip_ve_rehabilitasyon | Outside §F. `ates_var_mi` "Son zamanlarda ateşiniz oldu mu?" is a near twin of cluster medical `son_gunlerde_ates` (ratio 0.84), and fizik tedavi extends `cluster.medical`. The fever is asked twice in that chain. The exact-text test cannot see it, and the PR correctly did not invent the rebind. Route to the cluster-wave-a owner. | NOTE |
| kadın hastalıkları ve doğum | Outside the PR and present before it. Four re-declared cluster slots keep their cluster position but gate on `gebelik_durumu`, a branch slot merged after them. `validate_packs` does not check merged order. | NOTE |
| generator ↔ candidates | No test regenerates a candidate and compares it with the committed file. That was checked by hand here (§E). | NOTE |

## B. Rebind ledger (branch ask against cluster ask)

"Same" means same fact, polarity, type and window, allowing for wording. The cluster text is the committed `review/cluster` candidate.

| # | branch, Q | old → new | comparison | verdict |
|---|---|---|---|---|
| 1 | enfeksiyon Q2 | `ates_var_mi` → `son_gunlerde_ates` | identical ask; cluster follow-up not carried | same |
| 2 | diyabet Q5 | `aciklanamayan_kilo_kaybi` → `istemsiz_kilo_kaybi` | "beslenmenizde bir değişiklik olmadığı hâlde, son zamanlarda" against "istemeden, son aylarda" | same (NOTE window) |
| 3 | tıbbi ekoloji Q8 | `yuksek_tansiyon_oykusu` → `yuksek_tansiyon_tanisi` | "olduğu söylendi mi" against "tanısı konuldu mu" | same |
| 4 | ic Q3 | `soru_2` → `istemsiz_kilo_kaybi` | "son aylarda diyet yapmadan" against "son aylarda istemeden" | same |
| 5 | ic Q4 | `soru_3` → `son_gunlerde_ates` | unexplained fever over "son zamanlarda" against any fever over "son günlerde" | **narrowed** (MEDIUM) |
| 6 | ic Q5 | `soru_4` → `gece_terlemesi` | ever and waking, against recent and drenching | window (LOW) |
| 7 | el cerrahisi Q2 | `yaralanma_sonrasi_basladi` → `travma_sonrasi_basladi` | hand or wrist complaint after an injury, against a complaint after a fall, blow or injury | same |
| 8 | KBB Q2 | `soru_1` → `ani_isitme_azalmasi` | ungated sudden hearing loss, against the gated "birden mi başladı" | same core (NOTE) |
| 9 | KBB Q5 | `soru_4` → `donme_hissi` | no recency frame | window (LOW) |
| 10 | KBB Q7 | `soru_6` → `boyunda_sislik` | persistent "kitle" against a new "sertlik" | LOW |
| 11 | KBB Q8 | `soru_7` → `ses_kisikligi` | adds "ya da değişiklik" | NOTE |
| 12–14 | göz Q7, Q9, Q11 | `soru_6`, `soru_8`, `soru_10` → `goz_agrisi`, `isik_cevresinde_halka`, `kontakt_lens` | identical | same |
| 15 | gebe Q11 | `siddetli_bas_agrisi` → `gebelikte_siddetli_bas_agrisi` | identical text | same (§C) |
| 16 | perinatoloji Q11 | `gorme_bulanikligi` → `gebelikte_gorme_bozuklugu` | "ışık çakmaları" against "gözünüzün önünde ışık çakması" | same (§C) |
| 17 | jinekolojik onkoloji Q8 | `kasik_alt_karin_agrisi` → `alt_karin_agrisi` | same regions; "oluyor mu" against "var mı" | same |
| 18 | neonatoloji Q10 | `ates` → `ates_var_mi` | "fark ettiniz mi" against "var mı" | same (NOTE) |
| 19 | neonatoloji Q11 | `asiri_uykululuk` → `uykulu_tepkisiz` | no "tepkisiz" | same |
| 20 | çocuk metabolizma Q6 (Q7 gate) | `uykulu_halsiz` → `uykulu_tepkisiz` | adds "halsiz" | NOTE |
| 21 | çocuk genetik Q9 | `alisilmadik_halsizlik` → `uykulu_tepkisiz` | adds "halsiz" | NOTE |
| 22 | çocuk enfeksiyon Q2 (Q3 gate) | `ates_oldu` → `ates_var_mi` | "oldu mu" against "var mı" | NOTE (B §A.1 Q2) |
| 23 | çocuk enfeksiyon Q7 | `asiri_uykulu_halsiz` → `uykulu_tepkisiz` | adds "halsiz" | NOTE |
| 24 | çocuk enfeksiyon Q11 | `suregen_hastalik_tanisi` → `suregen_tani` | drops "önemli bir tanı" | NOTE |
| 25 | çocuk göğüs Q8 | `gogus_ice_cekilmesi` → `gogus_icine_cekilme` | identical, the §C Q10 text | same |
| 26 | klinik psikoloji Q9 | `psikiyatrik_ilac_kullanimi` → `ruh_sagligi_ilaci` | "hekimin verdiği" against "düzenli kullandığınız" | same |
| 27 | klinik psikoloji Q8 | `onceki_psikoterapi` → `onceki_ruh_sagligi_destegi` | regular sessions against any support | narrowed (LOW) |
| 28 | AMATEM Q12 | `destek_cevresi` → `sosyal_destek` | same construct | same |
| 29 | AMATEM Q6 | `gunluk_yasam_etkisi` → `islevsellik_etkilenimi` | adds "sağlığınızı" | two facts (LOW) |
| 30 | endodonti Q3 (Q4 gate) | `sicak_soguk_agri` → `dis_hassasiyeti` | no "tatlı"; "ağrıyor" | NOTE |
| 31–35 | ağız, diş ve çene cerrahisi Q2, Q3, Q4 (gate), Q5, Q10 | gap 6 ids | Q2, Q3, Q4 and Q5 identical; Q10 adds "ya da yaralanma" | same / NOTE |
| 36–37 | ağız, diş ve çene radyolojisi Q8, Q9 | gap 6 ids | identical | same |

## C. Owner-visible override side effects

A branch slot with a cluster id replaces the whole cluster slot: text, follow-up, gate and delivery. The rows below are new in this PR. Overrides that existed before it are not listed.

| chain | slot | change the rebind introduces |
|---|---|---|
| gebe polikliniği | `gebelikte_siddetli_bas_agrisi` | `text_first` → voice. Cluster gate `gebelik_dogrulandi == true` dropped. |
| perinatoloji | `gebelikte_gorme_bozuklugu` | `text_first` → voice. Cluster gate `gebelik_dogrulandi == true` dropped. Branch text. |
| KBB | `ani_isitme_azalmasi` | Cluster gate `isitme_azalmasi_tikaniklik == true` dropped; now asked of everyone. Branch text. |
| ağız, diş ve çene cerrahisi | `agiz_acma_guclugu` | Cluster gate `yuz_cene_sisligi == true \|\| dis_agrisi == true` dropped; now asked of everyone. |
| ruh sağlığı; klinik psikoloji | `diger_madde_kullanimi`; `zorlanmada_madde_kullanimi` | Gate `subject_role == 'kendim'` added, as cluster-wave-b §F gives it. |
| tıbbi ekoloji | `yuksek_tansiyon_tanisi` | Branch text. It now opens cluster `evde_tansiyon_olcumu`. Cluster follow-up dropped. |
| neonatoloji | `ates_var_mi` | Branch text. It now opens cluster `ates_suresi`. |
| klinik psikoloji | `ruh_sagligi_ilaci`; `onceki_ruh_sagligi_destegi` | Branch texts. They now open cluster `ilac_atlama` and `ilac_yan_etkisi`, and `onceden_iyi_gelen`. |
| enfeksiyon; diyabet; ic ×2; KBB `donme_hissi` | fever, weight loss, vertigo | Cluster follow-up dropped. The branch declares none. |
| every other §B row not marked identical | text | The branch wording replaces the cluster's in that chain; 25 asks in all. §B verdicts apply. |
| ağız, diş ve çene cerrahisi and radyolojisi | `nefes_yutkunma_guclugu` | No change today: cluster Q10 is `hold=`. If the owner releases it gated, these two ungated re-declarations override the gate in their chains. |

The women's-health delivery choice stays the owner's per-slot decision (`cluster_womens_health.md` §4 gap 6). These two ids join gebe's `bebek_hareketi_hissediliyor`, `bebek_hareketlerinde_azalma` and `yuz_el_sisligi` on that list.

## D. Exact corrections (not applied here)

1. **ic Q4 (MEDIUM).**
   - Delete `gen: slot=son_gunlerde_ates; type=boolean` under Q4 in `docs/evidence/proposals/ic_hastaliklari.md` and regenerate `ic_hastaliklari`. That restores `soru_3`, and the cluster fever ask returns to the chain.
   - Remove the row `("ic_hastaliklari", "soru_3", "son_gunlerde_ates")` from `SIBLING_REBINDS`.
   - Add an INT-353 row: "awaiting-human (HB-C1). ic Q4 asks NG12 unexplained fever. The clinician either adopts cluster Q12's text for `son_gunlerde_ates`, or keeps Q4 under its own id."
   - Note in cluster-wave-a §F that the Q4 pairing is a near duplicate, as that doc already does for odyoloji.
2. **Test binding (MEDIUM).** Add the proposal question number to each `SIBLING_REBINDS` row, as `(slug, qnum, old, new)`. Parse the branch proposal with `GEN.extract_questions`, then assert both of these:
   - the question numbered `qnum` has `slot == new`;
   - `slots[new]["ask_tr"]["tr"]` equals that question's text.

   The two swaps under Mutation runs then go red, and no Turkish is duplicated in the test.
3. **LOW rows ic Q5, KBB Q5, KBB Q7, AMATEM Q6, klinik psikoloji Q8.** Record each in the INT-353 table as awaiting-human (HB-C1; psychiatrist for the last two). The choice is one of two: the branch adopts the cluster's verified text verbatim, or the item keeps its own id. The reviewer authors no text.
4. **Evidence (LOW).**
   - Add to the INT-353 delivery note: "The cluster's `gebelik_dogrulandi == true` gate no longer applies to these two ids in these chains."
   - In the squash-merge message, replace "(identical asks only)" with "(göz identical; ic and KBB as cluster-wave-a §F pairs them)".

## E. Checklist (runs on `5c79ebce`)

```
$ uv run python scripts/dev/gen_specialty_packs.py <the 22 slugs>          22 × OK   rc=0
$ git status --short                                                       (empty)
$ uv run python scripts/dev/gen_specialty_packs.py                          96 OK, 3 hand-authored skipped   rc=0
$ git status --short                                                       (empty)
$ git diff --stat HEAD~1 HEAD -- packages/protocols/specialty packages/protocols/base \
    packages/protocols/review/cluster tests/fixtures/protocols files/protocols scripts
                                                                           (empty)
$ git diff --shortstat HEAD~1 HEAD -- packages/protocols/review/specialty  22 files, +72 −56
$ uv run pytest tests/protocols -q -o addopts=""                           685 passed   rc=0
$ uv run ruff check / ruff format --check (test file)                      clean
chain validation (scratch copy; load_registry + validate_packs)
  packs loaded: 100 {'base': 1, 'cluster': 8, 'specialty': 91}
  findings: 0
merged-order gate and type check (reviewer's script)
  HEAD~1: 8  (kemik_ilaci type ×2; cocuk_enfeksiyon ates_suresi→ates_oldu and
             endodonti agri_sonra_suruyor→sicak_soguk_agri read a later slot;
             kadin_hastaliklari ×4)
  HEAD:   4  (kadin_hastaliklari ×4, outside the PR)
```

- **Old ids.** No proposal or candidate the PR touched still names an old id. Where an old id remains elsewhere, it sits outside the chain the rebind served:
  - `ates_var_mi` in kadın hastalıkları ve doğum, and in fizik tedavi (the §A near twin);
  - `siddetli_bas_agrisi` in enfeksiyon;
  - `aciklanamayan_kilo_kaybi` in fizyoterapi (allied cluster);
  - `destek_cevresi` and `gunluk_yasam_etkisi` in ÇEMATEM (structural, B §E-3);
  - `uzamis_kanama_oykusu` in cluster surgical.
- **Turkish strings.** The PR changes exactly two, each in its proposal and its candidate. Both are byte-equal to their source:
  - "Nefes alırken çocuğunuzun kaburgalarının altı ya da arası içeri çekiliyor mu?" matches cluster-wave-b §C Q10;
  - "Hatırlıyorsanız bu ilacın adını söyleyebilir misiniz?" matches wave 8 §C Q11b.
- **`gen:` lines.** The `kemik_ilaci`, `kemik_ilaci_adi` and `subject_role == 'kendim'` lines match wave 8 §C and cluster-wave-b §F character for character. No other Turkish was added.
- **Invariants.**
  - No red-flag rule, level, route or `candidate_flag` changes.
  - Nothing extends `base.life_threat`.
  - No numeral is added.
  - No `hold=` is added or removed.

## F. Mutation runs (`tests/protocols/test_gen_specialty_packs.py`)

Each candidate was copied with `cp` before its mutation and restored from that copy afterwards. `cmp` was clean for all six mutated files, and `git status` was empty at the end.

| mutation | result |
|---|---|
| enfeksiyon: `son_gunlerde_ates` back to `ates_var_mi` (slot and gate) | 2 failed: its rebind row, and `test_no_chain_asks_one_text_under_two_ids` |
| çocuk genetik: `uykulu_tepkisiz` renamed to another boolean cluster id (`inleme`) | its rebind row failed |
| neonatoloji: `beslenmede_azalma` renamed to `beslenme_sivi_alimi` | the polarity control failed |
| ruh sağlığı: `subject_role == 'kendim'` gate removed | the self-report gate test failed |
| ic: `istemsiz_kilo_kaybi` ↔ `son_gunlerde_ates` swapped | **63 passed** (MEDIUM, §A) |
| KBB: `donme_hissi` ↔ `ses_kisikligi` swapped | **63 passed** (MEDIUM, §A) |

## Verdict

**PASS-with-fixes.**

- The PR applies every §F rebind with the exact ids, and does nothing beyond §F.
- It regenerates byte-identically, leaves the served trees untouched, and keeps `tests/protocols` green and the chain at 0 findings. It also clears two type clashes and two gate-order defects.
- Before merge, it needs two changes:
  - ic Q4 reverted and routed to the clinician (§D-1);
  - the rebind test pinned to the question each id binds (§D-2).
- The six LOW rows are evidence and routing entries.
- The delivery and gate changes in §C are the owner's to accept.
