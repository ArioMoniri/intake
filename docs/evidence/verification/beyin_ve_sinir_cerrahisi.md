# Verification — Beyin ve Sinir Cerrahisi (beyin_ve_sinir_cerrahisi) · INT-427 dynamic wave — awaiting-clinical-review

## 1. Author submission (output only)

Proposal: `docs/evidence/proposals/beyin_ve_sinir_cerrahisi.md` (§1 S7–S8, §4, §8). Items 15 → 20; 21 after the fix round.

### Changed items

| Q | slot | gate | change |
|---|---|---|---|
| Q5 | `ani_cok_siddetli_bas_agrisi` (boolean) | — (ungated) | reworded |
| Q8 | `idrar_diski_kontrol_degisimi` (boolean) | — (ungated) | reworded |
| Q10a | `bacakta_uyusma_karincalanma` (boolean) | `bacaga_yayilan_bel_agrisi == true` | added |
| Q10b | `ayaga_inen_agri` (boolean) | `bacaga_yayilan_bel_agrisi == true` | added |
| Q10c | `oksurunce_artan_bacak_agrisi` (boolean) | `bacaga_yayilan_bel_agrisi == true` | added |
| Q12a | `bas_darbesi_tarihi` (date) | `yakin_bas_darbesi == true` | added |
| Q13a | `beyin_omurga_tanisi_adi` (string) | `beyin_omurga_tanisi == true` | added |
| Q5 | `ani_cok_siddetli_bas_agrisi` (boolean) | — (ungated) | reworded (fix round) |
| Q10d | `iki_bacaga_yayilan_agri` (boolean) | — (ungated) | added (fix round) |
| Q12 | `yakin_bas_darbesi` (boolean) | — (ungated) | reworded (fix round) |

New sources: S7 `NHS-SCIATICA`, S8 `RCEM-NG232-ANTICOAG-2023`. Held items: none.

### Red-flag proposals (not active rules)

| # | proposed id | trigger idea in slot ids | source id + verbatim quote | status | when | decider |
|---|---|---|---|---|---|---|
| 1 | `rf.beyin_ve_sinir_cerrahisi_kauda_ekina` | `idrar_diski_kontrol_degisimi == true` \|\| `makat_uyusmasi == true` \|\| `iki_bacakta_guc_kaybi == true` \|\| `iki_bacaga_yayilan_agri == true`; placement: `base.life_threat` owner (invariant 7) | S1: "Bilateral sciatica" · "Perianal, perineal or genital sensory loss (saddle anaesthesia or paraesthesia)" | `status: draft_needs_source` | `TODO: cauda equina trigger combination, EK-4 level, register and location requires clinical sign-off` | HB-C1 |
| 2 | `rf.beyin_ve_sinir_cerrahisi_bas_darbesi_antikoagulan` | `yakin_bas_darbesi == true` and base `anticoagulant_use` (code) reports use, aspirin monotherapy excluded; `bas_darbesi_tarihi` gives the date | S8 (NG232 1.2.4): "Community health services (GPs, ambulance crews, NHS walk-in or minor injury centres, dental practitioners) and inpatient units without an emergency department should refer people who have sustained a head injury to a hospital emergency department, using the ambulance service if necessary, if there are any of these risk factors." · "“Current anticoagulant and antiplatelet treatment” are listed as a risk factor." · "It should be noted that aspirin monotherapy alone is not an indication for referral." | `status: draft_needs_source` | `TODO: head-injury recency, anticoagulant_use code values (aspirin monotherapy excluded) and route requires clinical sign-off` | HB-C1 |
| 3 | `rf.beyin_ve_sinir_cerrahisi_ani_siddetli_bas_agrisi` | `ani_cok_siddetli_bas_agrisi == true`; placement: base `rf_thunderclap_headache` (invariant 7) | S3: "A 'thunderclap' headache (a sudden severe headache, typically peaking in intensity within 1 to 5 minutes) is a red-flag symptom of subarachnoid haemorrhage." | `status: draft_needs_source` | `TODO: thunderclap trigger, register and location requires clinical sign-off` | HB-C1 |
| 4 | `rf.beyin_ve_sinir_cerrahisi_yeni_fokal_defisit` | `tek_tarafli_guc_kaybi == true` \|\| `konusma_anlama_guclugu == true`, with base `time_last_known_well`; placement: base `rf_stroke_fast` / `rf_new_neuro_deficit_subacute` (invariant 7) | S5: "Vücudun tek tarafında yüz, kol ve/veya bacakta olan hissizlik ve/veya kuvvet kaybı" | `status: draft_needs_source` | `TODO: focal-deficit time window, register and location requires clinical sign-off` | HB-C1 |
| 5 | `rf.beyin_ve_sinir_cerrahisi_artan_bas_agrisi_kusma` | `giderek_artan_bas_agrisi == true` && `bas_agrisi_ile_bulanti_kusma == true` | S6: "Progressive headache and atypical presentations"; S2: "severe or increasing headache, or persistent vomiting" | `status: draft_needs_source` | `TODO: raised-pressure headache pattern, EK-4 level and route requires clinical sign-off` | HB-C1 |
| 6 | `rf.beyin_ve_sinir_cerrahisi_spinal_metastaz_basisi` | a known cancer (no slot exists) together with `bacaga_yayilan_bel_agrisi == true` \|\| `iki_bacakta_guc_kaybi == true` \|\| `idrar_diski_kontrol_degisimi == true` | NICE NG234: not retrieved on 2026-10-02 (HTTP 403); no verbatim quote | `status: draft_needs_source` | `TODO: metastatic spinal cord compression pattern, EK-4 level and route requires clinical sign-off` | HB-C1 |

## 2. Independent verification

Reviewer: independent clinical-content verifier (challenger), 2026-10-02. Every item is awaiting-clinical-review; this is not a physician signature.

Method:
- `check_proposal.py docs/evidence/proposals/beyin_ve_sinir_cerrahisi.md` (engineer worktree): `== beyin_ve_sinir_cerrahisi: 20 items parsed` … `OK`.
- `verify_chain.py` (same file): `chain base.intake -> cluster.surgical -> specialty.beyin_ve_sinir_cerrahisi; 5 gates in this pack` / `OK`.
- Merged order dump (read-only scratch helper over the resolver): every new child (Q10a–c, Q12a, Q13a) is asked directly after its parent.
- Proposed fixes tested on a scratch copy: `check_proposal.py` gave `21 items parsed … OK`, and `verify_chain.py` gave `5 gates … OK`.
- Slot collisions: grepped `packages/protocols/{base,review,specialty}`. The five new ids exist only here. `iki_bacaga_yayilan_agri` (proposed in V-BVSC-1) already exists in `ortopedi_ve_travmatoloji` with the same meaning and wording.
- Sources re-fetched 2026-10-02:
  - S7, nhs.uk/conditions/sciatica (WebFetch): all four quotes are present. Last reviewed 03 December 2024; next review 03 December 2027. The same page's urgent list includes "have sciatica on both sides".
  - S8, RCEM PDF (WebFetch saved the PDF; I ran `pdftotext`): the 1.5.13 text and the "risk factor" sentence are present word for word. 1.2.4 is also reproduced there. The document is dated "23rd October 2023".
  - S1, MPS page (WebFetch, dated 02/05/2018): the revised CKS list has six bullets, and the first is "Bilateral sciatica". §1 S1 quotes only the other five.
  - NICE NG234, metastatic spinal cord compression (for the additional proposal): nice.org.uk returned HTTP 403, so it was not retrieved.
- D3: no new sensitive category this wave.

BLUF: I reviewed 8 items (Q5, Q8, Q10a, Q10b, Q10c, Q12a, Q13a, plus Q12, which predates this wave and is touched by S8): 6 PASS, 2 REVISE, 0 HOLD. One item is missing (V-BVSC-1). I checked 5 gates; all are plain yes-gates, and every alarm feeder (Q3–Q9, Q11) is still ungated. Findings: 1 HIGH, 3 MEDIUM, 2 LOW.

| # | item (Q, slot) | finding | severity | fix | decider |
|---|---|---|---|---|---|
| V-BVSC-1 | missing item and RF #1 (cauda equina) | The first bullet of the CKS cauda-equina list S1 relies on, "Bilateral sciatica", is left out of §1 S1, of the questions and of RF #1's trigger. A patient whose only sign is pain spreading into both legs never reaches the proposed trigger. | HIGH | §1 S1: add the bullet `> "Bilateral sciatica"`. After Q10c add `**Q10d — Pain spreading to both legs** · source: S1 ("Bilateral sciatica"), S7 ("have sciatica on both sides")` / `> "Bacak ağrınız son günlerde her iki bacağınıza birden yayıldı mı?"` / `gen: slot=iki_bacaga_yayilan_agri; type=boolean` (ungated; same id and wording as ortopedi_ve_travmatoloji). In RF #1, add `iki_bacaga_yayilan_agri == true` as an alternative trigger. | author |
| V-BVSC-2 | Q5 `ani_cok_siddetli_bas_agrisi` | The new wording no longer says the headache was severe: "en şiddetli hâline ulaşan" only says how fast it peaked. S3 defines the symptom as "a sudden severe headache", and the slot id still says "çok şiddetli". The question now feeds RF #3 with a broader fact than the slot name claims. | MEDIUM | `> "Saniyeler ya da birkaç dakika içinde çok şiddetlenen ani bir baş ağrınız oldu mu?"` (14 words) | author |
| V-BVSC-3 | Q12 `yakin_bas_darbesi` (predates this wave) | "ciddi" leaves minor knocks out of the parent question. NG232 1.2.4 and 1.5.13, which this wave added via S8, apply to any head injury in someone on anticoagulant or antiplatelet treatment. Because of the gate, Q12a and RF #2 never see those patients. | MEDIUM | `> "Son zamanlarda başınıza hafif de olsa bir darbe aldınız mı?"` (gen line unchanged) | author |
| V-BVSC-4 | RF #2 and Q12a `bas_darbesi_tarihi` | RF #2 rests on the 1.5.13 window "within 8 hours", which is a CT decision made in the emergency department, and `bas_darbesi_tarihi` is `type=date`, so it cannot express hours. The recommendation that fits a pre-visit, community setting is 1.2.4, which I verified in the same PDF. | MEDIUM | Re-source RF #2 to S8: `> "1.2.4 Community health services (GPs, ambulance crews, NHS walk-in or minor injury centres, dental practitioners) and inpatient units without an emergency department should refer people who have sustained a head injury to a hospital emergency department, using the ambulance service if necessary, if there are any of these risk factors."` + `> "It should be noted that aspirin monotherapy alone is not an indication for referral."`. Trigger: `yakin_bas_darbesi == true` and base `anticoagulant_use`. Set `when` to `TODO: head-injury recency, anticoagulant_use code values (aspirin monotherapy excluded) and route requires clinical sign-off`. Keep Q12a as it is. | HB-C1: "Does a recent head injury in a patient on an anticoagulant or a non-aspirin antiplatelet, reported before a neurosurgery visit, route to the emergency department, and within what recency?" |
| V-BVSC-5 | §1 S8 metadata | The version and date line says "October 2023 (file name)", but the document itself prints "23rd October 2023". S8 is also a secondary reproduction of NG232, and the recommendation numbers cannot be checked against nice.org.uk (403). | LOW | Change the S8 version/date to `23 October 2023 (printed on p. 3)`. Keep the "secondary reproduction" label until the NG232 primary text is snapshotted. | author |
| V-BVSC-6 | scope gaps (no item) | Common neurosurgery outpatient situations have no input: a known cancer with new back pain or leg symptoms (metastatic spinal cord compression), a brain shunt in place, and a first seizure. | LOW | none until sourced (NG234 not retrieved, 403) | clinician: "Should the neurosurgery pre-visit ask about a known cancer, an existing brain shunt and a first-ever seizure?" |

PASS without change: Q8 (14 words; "yeni" keeps the recency), Q10a, Q10b and Q10c (they ask straight after Q10; S7 verified), Q12a wording (date is enough for a pre-visit), and Q13a.

Red-flag proposals reviewed

| # | proposed id | verdict | note |
|---|---|---|---|
| 1 | `rf.beyin_ve_sinir_cerrahisi_kauda_ekina` | revise | Add `iki_bacaga_yayilan_agri == true` as an alternative trigger and the "Bilateral sciatica" bullet to its source (V-BVSC-1). Placement stays with the `base.life_threat` owner (invariant 7). The status and `TODO` form are correct. |
| 2 | `rf.beyin_ve_sinir_cerrahisi_bas_darbesi_antikoagulan` | revise | Re-source to NG232 1.2.4 via S8, drop the hours window and reword `when` (V-BVSC-4). Its input widens with V-BVSC-3. |
| 3 | `rf.beyin_ve_sinir_cerrahisi_ani_siddetli_bas_agrisi` | keep as proposal | Placement is base `rf_thunderclap_headache`. The input wording must keep "çok şiddet-" (V-BVSC-2). S3 is carried from noroloji.md and is not re-verified (nice.org.uk 403). |
| 4 | `rf.beyin_ve_sinir_cerrahisi_yeni_fokal_defisit` | keep as proposal | Placement is base `rf_stroke_fast` / `rf_new_neuro_deficit_subacute`. |
| 5 | `rf.beyin_ve_sinir_cerrahisi_artan_bas_agrisi_kusma` | keep as proposal | — |
| add | `rf.beyin_ve_sinir_cerrahisi_spinal_metastaz_basisi` | additional, `status: draft_needs_source` | Trigger idea: a known cancer (no slot yet; V-BVSC-6) together with (`bacaga_yayilan_bel_agrisi == true` or `iki_bacakta_guc_kaybi == true` or `idrar_diski_kontrol_degisimi == true`). Source: NICE NG234, not retrieved on 2026-10-02 (403), so there is no verbatim quote. `when: 'TODO: metastatic spinal cord compression pattern, EK-4 level and route requires clinical sign-off'`. Decider: HB-C1. |

## 3. Fix log

| finding | action (fixed / open) | where |
|---|---|---|
| V-BVSC-1 | fixed | proposal §1 S1, S7; §4 Q10d; §8; verification §1 RF #1 |
| V-BVSC-2 | fixed | proposal §4 Q5; §8 |
| V-BVSC-3 | fixed | proposal §4 Q12; §8 |
| V-BVSC-4 | open (HB-C1 question); RF #2 row re-sourced to NG232 1.2.4 per the red-flag verdict; Q12a unchanged | proposal §1 S8; verification §1 RF #2 |
| V-BVSC-5 | fixed | proposal §1 S8 |
| V-BVSC-6 | open (clinician) | — |
| RF #1 revise | fixed | verification §1 RF #1 |
| RF #2 revise | fixed | verification §1 RF #2 |
| RF #3 keep as proposal | fixed (kept unchanged) | verification §1 RF #3 |
| RF #4 keep as proposal | fixed (kept unchanged) | verification §1 RF #4 |
| RF #5 keep as proposal | fixed (kept unchanged) | verification §1 RF #5 |
| RF add `rf.beyin_ve_sinir_cerrahisi_spinal_metastaz_basisi` | fixed (added as RF #6); open (no verbatim quote: NG234 HTTP 403; no known-cancer slot) | verification §1 RF #6 |
