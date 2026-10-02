# Verification — Anesteziyoloji (anesteziyoloji) · INT-427 dynamic wave — awaiting-clinical-review

## 1. Author submission (output only)

Proposal: `docs/evidence/proposals/anesteziyoloji.md` (§1 S3–S5, §3, §4 gap 1, §6). Items 9 → 16; 17 after the fix round.

### Changed items

| Q | slot | gate | change |
|---|---|---|---|
| Q3a | `suregelen_rahatsizlik_adlari` (string) | `suregelen_rahatsizlik == true` | added |
| Q3b | `uyku_apnesi_tanisi` (boolean) | — | added |
| Q3c | `uyku_solunum_cihazi` (boolean) | `uyku_apnesi_tanisi == true` | added |
| Q5a | `onceki_anestezi_sorunu_aciklama` (string) | `onceki_anestezi_sorunu == true` | added |
| Q6a | `zor_entubasyon_belgesi` (boolean) | `zor_entubasyon_oykusu == true` | added |
| Q9 | `ailede_anestezi_sorunu` (boolean) | — | `delivery=text_first` added |
| Q9a | `ailede_anestezi_sorunu_aciklama` (string, `text_first`) | `ailede_anestezi_sorunu == true` | added |
| Q9b | `ailede_anestezi_testi` (boolean, `text_first`) | `ailede_anestezi_sorunu == true` | added |
| Q3a | `suregelen_rahatsizlik_adlari` (string) | `suregelen_rahatsizlik == true` | reworded (fix round) |
| Q3d | `yakin_solunum_yolu_enfeksiyonu` (boolean) | — | added (fix round) |
| Q5a | `onceki_anestezi_sorunu_aciklama` (string) | `onceki_anestezi_sorunu == true` | reworded (fix round) |
| Q6a | `zor_entubasyon_belgesi` (boolean) | `zor_entubasyon_oykusu == true` | source quote added (fix round) |
| Q9a | `ailede_anestezi_sorunu_aciklama` (string, `text_first`) | `ailede_anestezi_sorunu == true` | reworded (fix round) |
| Q9b | `ailede_anestezi_testi` (boolean, `text_first`) | `ailede_anestezi_sorunu == true` | reworded (fix round) |

New sources: S4 `TARD-PREOP-2015`, S5 `ASA-DIFFICULT-AIRWAY-2022`; S3 `BJAED-MH-2021` gained two
verbatim quotes. Held items: none.

### Red-flag proposals (not active rules)

| # | proposed id | trigger idea in slot ids | source id + verbatim quote | status | when | decider |
|---|---|---|---|---|---|---|
| — | none proposed | — | — | — | — | — |

## 2. Independent verification

Reviewer: independent clinical-content verifier (challenger), 2026-10-02. Every item is awaiting-clinical-review; this is not a physician signature.

Method:
- `check_proposal.py docs/evidence/proposals/anesteziyoloji.md` (engineer worktree): `== anesteziyoloji: 16 items parsed` … `OK`. Every ask and follow-up passed the shipped Turkish PolicyGuard, and every sentence is 15 words or fewer.
- `verify_chain.py` (same file): `chain base.intake -> cluster.surgical -> specialty.anesteziyoloji; 6 gates in this pack` / `OK`.
- Runtime order: I dumped the merged base → cluster → candidate slot order using the resolver's own `_merge_chain`/`_apply_ops`, with a read-only scratch helper. The FSM asks in `(priority, authored order)` (`clinical_agent/plan.py` `sort_key`). When a pack overrides a cluster slot (`suregelen_rahatsizlik`, `onceki_anestezi_sorunu`, `ailede_anestezi_sorunu`), the override stays in the cluster's position, and the new gated children are appended after every cluster slot (finding V-A-1).
- Proposed fixes tested on a scratch copy with the same file name: `check_proposal.py` gave `17 items parsed … OK`, and `verify_chain.py` gave `6 gates … OK`.
- Slot collisions: grepped `packages/protocols/{base,review,specialty}`. The seven new ids and `yakin_solunum_yolu_enfeksiyonu` occur only in this pack.
- Sources re-fetched 2026-10-02:
  - S3, PMC8134759 (WebFetch): all three quotes are present, and the citation matches (BJA Educ 2021;21(6):218–224).
  - S4, TARD PDF (WebFetch saved the PDF; I ran `pdftotext`): all five quotes are present. The page indices match (3, 8, 8, 9, 18), and the cover reads "PREOPERATİF DEĞERLENDİRME (2015)".
  - S5, shanahq ASA 2022 PDF (WebFetch, then `pdftotext`): both quotes are present. The footer reads "Anesthesiology 2021; XXX:00–00" with DOI 10.1097/ALN.0000000000004002, so this is the online-first version; the print volume and pages are not in the file.
- D3: Q9, Q9a and Q9b (relatives' anaesthesia history) carry `delivery=text_first`. The category is the approved "relatives' family health history", and it matches the cluster's `ailede_anestezi_sorunu`.

BLUF: I reviewed 8 items (Q3a, Q3b, Q3c, Q5a, Q6a, Q9 delivery, Q9a, Q9b): 4 PASS, 4 REVISE, 0 HOLD. I checked 6 gates; all are plain yes-gates on an earlier boolean and none gates an alarm item. Findings: 0 HIGH, 2 MEDIUM, 1 LOW. No fasting hour, digit, instrument item shape (STOP-Bang, ASA class) or diagnosis language appears anywhere.

| # | item (Q, slot) | finding | severity | fix | decider |
|---|---|---|---|---|---|
| V-A-1 | Q3a `suregelen_rahatsizlik_adlari`, Q5a `onceki_anestezi_sorunu_aciklama`, Q9a `ailede_anestezi_sorunu_aciklama`, Q9b `ailede_anestezi_testi` | These four follow-ups point back to an earlier question ("Bu", "O sırada", "bu kişi", "bu nedenle"). Each parent overrides a cluster slot and is asked in the cluster's position, while the child is appended at the end. So Q3a comes 4 turns after Q3, directly after the Q2 free-text question. Q5a comes at least 9 turns after Q5, directly after the allergy question; Q9 sits between them, so "O sırada" can be answered about the relative. Q9a and Q9b come at least 11 turns after Q9, directly after "En son ne zaman bir şey içtiniz?". The answers can bind to the wrong event. | MEDIUM | Q3a `> "Süregelen rahatsızlıklarınızın adlarını söyleyebilir misiniz?"` · Q5a `> "Önceki anestezide yaşanan sorunu size anlatıldığı kadarıyla söyler misiniz?"` · Q9a `> "Ailenizdeki kişinin anesteziyle ilgili yaşadığı sorunu biliyorsanız kısaca anlatır mısınız?"` · Q9b `> "Ailenizde anestezi sorunu nedeniyle özel bir test yaptıran biri oldu mu?"` (gen lines unchanged) | author |
| V-A-2 | new item after Q3c (S4 p. 9) | The pre-op history has no question about a recent respiratory infection. S4, which this wave added and I re-verified, says on p. 9: "Göğüs radyografisi: rutin olarak önerilmemektedir. Sigara içimi, yakın zamanda üst solunum yolu enfeksiyonu ( ciddi semptomlu hastalarda operasyon 1 ay ertelenmeli)…" and "Özellikle çocuklarda geçirilmiş veya aktif enfeksiyon varsa elektif cerrahi ertelenir." The question is ungated and gives no time threshold. | MEDIUM | `**Q3d — Recent cold or febrile illness** · source: S4 (p. 9, "yakın zamanda üst solunum yolu enfeksiyonu")` / `> "Son haftalarda nezle, grip ya da ateşli bir hastalık geçirdiniz mi?"` / `gen: slot=yakin_solunum_yolu_enfeksiyonu; type=boolean` | author (wording), clinician (whether a postponement window is ever ruled on) |
| V-A-3 | Q6a `zor_entubasyon_belgesi` (source) | The two S5 quotes support informing the patient and recording in the chart. Neither says that a written record is given to the patient. The same PDF's Follow-up Care section does say so: "documentation of difficult airway and management in the medical record and to the patient". The item wording is fine. | LOW | Add to §1 S5: `> "Follow-up care includes the topics of: … (3) documentation of difficult airway and management in the medical record and to the patient, and (4) registration with a difficult airway notification service."` and cite it on Q6a | author |

PASS without change: Q3b (diagnosed OSA, ungated, not a STOP-Bang item), Q3c (CPAP gate presupposes the diagnosis), Q6a wording, and Q9 (`text_first` now matches the cluster).

Red-flag proposals reviewed

| # | proposed id | verdict | note |
|---|---|---|---|
| — | none proposed | keep as none | Finding 20 (specialty-wave1-3) stands: prior anaesthetic problems, malignant-hyperthermia family history, difficult airway, OSA and anticoagulants are planning facts, not acuity. The recent-infection item (V-A-2) is a postponement question and not a red flag. Acute cardiorespiratory alarms stay in base (`rf_chest_pain_acute`, `rf_dyspnoea_rest`; invariant 7). The verifier proposes nothing further. |

## 3. Fix log

| finding | action (fixed / open) | where |
|---|---|---|
| V-A-1 | fixed | proposal §3 Q3a, Q5a, Q9a, Q9b; §6 |
| V-A-2 | fixed (wording); open (clinician: postponement window) | proposal §1 S4 (p. 9, p. 10), §3 Q3d; §6 |
| V-A-3 | fixed | proposal §1 S5, §3 Q6a; §6 |
| red-flag table: none proposed (keep as none) | fixed (kept as none) | verification §1 |
