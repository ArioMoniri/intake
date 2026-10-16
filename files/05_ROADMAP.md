# 05 · Roadmap — v2.1 (rebuilt 25 Aug 2026 after external verification; reconciled 27 Aug 2026)

> **What changed from v1.4, and why.** v1.4 was a *date-driven* plan: P0 in weeks 0–3, P1 by week 12, a hospital pilot by month 7. Four independent verification passes — clinical, architecture, vendor-facts and Turkish regulatory — established that those dates were not achievable and, more importantly, that **the calendar was never the binding constraint**. Three things bind, in this order:
>
> 1. **Your review capacity.** 101 of 175 issues sit behind a human gate.
> 2. **CI throughput.** 175 issues × a realistic 35–60 min PR gate ≈ 100–175 CPU-hours. The autonomous loop is bounded by CI, not by the model.
> 3. **The clinical-investigation clock.** 7–12 months, strictly sequential, and not compressible by adding engineers.
>
> v2.0 is therefore **gate-driven**: phases advance when evidence exists, not when a date arrives. Every duration below is a forecast under stated assumptions, never a commitment, and each phase names the artefact that ends it.
>
> **The single most consequential correction: the medical-device classification is Class IIb, not Class IIa** (`06 §0.3`). That re-prices Stage B and should be resolved before anything else is budgeted.
>
> **v2.1 reconciliation, 27 Aug 2026.** Four things this plan still assumed have changed, and each is corrected in place below rather than removed: **(1) all models are self-hosted** — `cascade_fast` and `s2s_cloud` cease to exist, so P1's profile is `residency_tr` and the `s2s_cloud → P3` line becomes a withdrawal; **(2) `03 §4.9.1` is the single source of truth for the model stack**, so no phase, KPI or assumption row here pins a model — where one did, it now points at a row number; **(3) Kintsugi DAM is dropped (D14)** — the `acoustic` lane survives, the model does not, which changes what the Turkish validation track is *for*; **(4) the P2 integration counterparty is the hospital group's own technology arm**, already corrected under the phase table. Phase **gates** — the evidence that ends a phase — are now stated explicitly in **§1a**, because "the exit artefact" was a column and needed to be a checklist.
>
> **Live status, 16 Oct 2026 (INT-452).** The counts in §0 and §1 below are the v2.0 analysis of 25 Aug 2026 and are kept as the reasoning record. Where each phase stands today — done, in flight, blocked and todo, each with its owner — is the generated section that follows. It is rendered from the backlog and a committed GitHub snapshot, and a test fails when it is stale, so it is never edited by hand.

---

<!-- BEGIN generated live status (scripts/backlog/render_roadmap.py) — do not edit by hand -->
## Live status — generated from the backlog and GitHub

> **Generated; do not edit this section by hand.** `scripts/backlog/render_roadmap.py` renders it from `docs/backlog/issues.yaml`, `docs/backlog/epics.yaml`, `files/HUMAN_BLOCKERS.md`, `docs/backlog/blockers.md` and the GitHub snapshot `docs/backlog/github_snapshot.json`, captured **2026-10-16T03:13:48Z** against main `be6c09c1e03c`. `make roadmap-snapshot` refreshes the GitHub state and is the only step that calls GitHub; `make backlog-render` re-renders; `tests/backlog/test_roadmap.py` fails CI when this section is stale.
>
> **States.** done · in flight (an open PR names the id, or the row is `doing`) · blocked (`awaiting-human`/`blocked`, or a `blocked:*` label) · todo (`ready` when every dependency is satisfied, LOOP.md step 1) · withdrawn. **Owner** is who acts next: for a blocked item the named human from its blocker record, otherwise the agent role its area implies plus any human sign-off (`scripts/backlog/roadmap_lib.py`).

| phase | rows | done | in flight | blocked | todo | withdrawn | open PRs, no row on main | open issues, no row anywhere |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 | 172 | 133 | 4 | 10 | 25 | 0 | 8 | 0 |
| P1 | 142 | 81 | 4 | 25 | 32 | 0 | 34 | 7 |
| P2 | 47 | 14 | 5 | 3 | 24 | 1 | 1 | 3 |
| P3 | 7 | 2 | 1 | 1 | 3 | 0 | 0 | 0 |
| — | 0 | 0 | 0 | 0 | 0 | 0 | 10 | 0 |
| **all** | **368** | **230** | **14** | **39** | **84** | **1** | **53** | **10** |

### Live · P0 — Foundation

| epic | done | in flight | blocked | todo |
|---|---:|---:|---:|---:|
| E00-governance | 5 | 0 | 0 | 0 |
| E01-platform | 23 | 0 | 1 | 0 |
| E02-data | 12 | 1 | 1 | 0 |
| E03-protocols | 13 | 1 | 1 | 14 |
| E04-engines | 9 | 0 | 0 | 1 |
| E05-voice | 12 | 0 | 1 | 1 |
| E06-lanes | 1 | 0 | 1 | 2 |
| E07-records | 4 | 0 | 0 | 0 |
| E08-mobile | 37 | 0 | 1 | 0 |
| E09-clinician | 2 | 0 | 0 | 1 |
| E11-learning | 2 | 0 | 0 | 0 |
| E12-admin | 4 | 0 | 0 | 0 |
| E13-infra | 6 | 2 | 1 | 1 |
| E14-legal | 2 | 0 | 3 | 4 |
| E16-experience | 1 | 0 | 0 | 0 |
| E17-release | 0 | 0 | 0 | 1 |

Remaining, in file order (39):

| id | title | epic | state | PR · blocker · dependencies | owner |
|---|---|---|---|---|---|
| INT-019 | security.yml CI job: full gate set + signing | E01-platform | blocked | HB-O6 | HB-O6: owner (protected path) |
| INT-043 | base.intake pack (tr/en) complete per 04 §1 - FRONT-LOADED: unblocks 78 of 175 | E03-protocols | blocked | HB-C1 · HB-C5 · HB-C6 · PR #185 `int-43-flat` conflicting | HB-C1: Dr Efe Onganer (physician of record) + a paediatrician for the paedia… |
| INT-044 | Cluster pack: medical | E03-protocols | todo | ready | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-045 | Cluster pack: surgical | E03-protocols | todo | ready | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-046 | Cluster pack: sensory | E03-protocols | todo | ready | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-047 | Cluster pack: womens_health | E03-protocols | todo | ready | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-048 | Cluster pack: child_health (guardian proxy, age bands) | E03-protocols | todo | ready | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-049 | Cluster pack: mental_health | E03-protocols | todo | ready | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-050 | Cluster pack: dental | E03-protocols | todo | ready | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-051 | Cluster pack: allied_and_reports | E03-protocols | todo | ready | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-052 | Cluster excluded: Acil refusal + 112 routing copy | E03-protocols | todo | ready | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-053 | Deep pack: internal_medicine | E03-protocols | todo | waits on INT-044 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-054 | Deep pack: gastroenterology + overlay.oncology_patient | E03-protocols | todo | waits on INT-044 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-055 | Deep pack: rheumatology | E03-protocols | todo | waits on INT-044 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-056 | Patient overlays set (8) + overlay_monotonicity property test | E03-protocols | todo | ready | agent · clinical-reviewer |
| INT-058 | Signed protocol bundles: cosign sign + runtime verification + per-session hash pin | E03-protocols | in flight | #579 `int-058-signed-bundles` conflicting | agent · clinical-reviewer |
| INT-101 | Session budgets + cost metering per component/profile | E05-voice | blocked | HB-O8 | HB-O8: owner (both) |
| INT-112 | linguistic lane: TR lexicons + prosody stats + crisis bypass to triage | E06-lanes | blocked | HB-C16 | physician of record (Dr Efe Onganer) + a Turkish-speaking clinical ps… |
| INT-116 | Wellbeing engine: PHQ-2/GAD-2 -> PHQ-9/GAD-7 -> C-SSRS, crisis script, verbatim items, clinician-only outputs | E06-lanes | todo | ready | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-117 | device_functions flag: MDSW boundary enforced (Stage A non-device vs investigation mode) | E06-lanes | todo | waits on INT-116 | agent · legal-reviewer; sign-off: counsel |
| INT-151 | Note views: SOAP, red flags (mode-aware), provenance, consented wellbeing, AI labels + 1-click feedback | E09-clinician | todo | waits on INT-117 | agent |
| INT-210 | Legal document set v1 (tr primary): aydinlatma x5, acik riza per purpose, gizlilik, kullanim kosullari, KVKK… | E14-legal | blocked | HB-L27 | Turkish counsel (KVKK / health-law), instructed by the owner |
| INT-211 | VERBIS registration pack + data inventory generated from schema annotations + irtibat kisisi | E14-legal | todo | ready | agent · legal-reviewer; sign-off: counsel |
| INT-212 | Retention & destruction policy doc (DEST-2017) bound to the engine | E14-legal | todo | ready | agent · legal-reviewer; sign-off: counsel |
| INT-216 | MDSW file: intended purpose, qualification (MDCG 2019-11 Rev.1), Rule 11 classification (Class IIb), device/n… | E14-legal | todo | waits on INT-117 | agent · legal-reviewer; sign-off: counsel |
| INT-302 | Which language binds: the legal status of a translated aydınlatma metni, and what the app may show when they… | E14-legal | todo | ready | agent · legal-reviewer; sign-off: counsel |
| INT-347 | Replace the withdrawn minio/minio image with an owner-approved, digest-pinned S3-compatible store | E13-infra | blocked | no blocker record | owner — no blocker record names it |
| INT-348 | Play Integrity verification and a real-device OTP login smoke on TestFlight and Play | E08-mobile | blocked | HB-A3 | HB-A3: owner |
| INT-349 | Sensitive slot categories: per-slot data-category tag, encrypted storage, fail-closed register gate | E02-data | in flight | doing; no open PR | agent · legal-reviewer |
| INT-350 | CI part 2: check-integration builds the pinned edge plugin; osv findings fixed | E13-infra | in flight | #731 `int-350-ci-edge-plugin-tests` | agent · security-reviewer |
| INT-354 | Consolidate int-demo into main; main becomes the TestFlight build source | E17-release | todo | ready | agent (mobile) |
| INT-356 | Counsel completes the data-category register (basis, retention, recipients, consent scope, other-subject noti… | E14-legal | blocked | no blocker record | owner — no blocker record names it |
| INT-358 | SMS vendor decision: DPA, KVKK cross-border mechanism and the egress allow-list row for OTP delivery | E14-legal | blocked | no blocker record | owner — no blocker record names it |
| INT-376 | Move the production API host to Frankfurt (eu-central-1) when the GPU quota is approved | E13-infra | todo | ready | agent · sre-reviewer |
| INT-394 | Owner decision — the database role that runs erasure and retention | E02-data | blocked | no blocker record | owner — no blocker record names it |
| INT-416 | triage context refuses an empty unit at construction, so RED evaluation can never raise mid-rule | E04-engines | todo | ready | agent · clinical-reviewer |
| INT-441 | base.intake gates compare code slots against values the slot can carry (proxy_reported, lmp_date) | E03-protocols | todo | ready | agent · clinical-reviewer |
| INT-454 | spoken-answer loop end to end on the hosted lanes (ASR → extract → next question), measured | E05-voice | todo | ready | agent · runtime-reviewer |
| INT-421 | Production release: full stack from main on the AWS host + EAS store builds | E13-infra | in flight | doing; no open PR | agent · sre-reviewer |

### Live · P1 — Fast mode, device-off

| epic | done | in flight | blocked | todo |
|---|---:|---:|---:|---:|
| E00-governance | 3 | 1 | 0 | 1 |
| E01-platform | 1 | 0 | 2 | 0 |
| E02-data | 5 | 0 | 1 | 0 |
| E03-protocols | 5 | 1 | 1 | 6 |
| E04-engines | 2 | 0 | 0 | 0 |
| E05-voice | 6 | 0 | 2 | 4 |
| E06-lanes | 0 | 0 | 3 | 0 |
| E07-records | 4 | 0 | 4 | 2 |
| E08-mobile | 23 | 0 | 1 | 8 |
| E09-clinician | 0 | 0 | 0 | 2 |
| E10-connectors | 3 | 1 | 1 | 0 |
| E11-learning | 1 | 0 | 0 | 1 |
| E12-admin | 14 | 0 | 4 | 2 |
| E13-infra | 5 | 1 | 4 | 1 |
| E14-legal | 5 | 0 | 2 | 4 |
| E16-experience | 3 | 0 | 0 | 0 |
| E17-release | 1 | 0 | 0 | 1 |

Remaining, in file order (61):

| id | title | epic | state | PR · blocker · dependencies | owner |
|---|---|---|---|---|---|
| INT-095 | Profile residency_tr with real self-hosted adapters (03 §4.9.1 rows 1-2, 7, 10-11) + on-hardware smoke | E05-voice | blocked | HB-I10 | owner |
| INT-099 | Backchannels + ack styles + preemptive generation + per-profile NFR harness in CI | E05-voice | todo | ready | agent · runtime-reviewer |
| INT-111 | affect lane: self-hosted SER on the agent worker (03 §4.9.1 row 14) + Turkish eval set | E06-lanes | blocked | HB-C11 | physician of record (Dr Efe Onganer) + owner (corpus collection & lab… |
| INT-113 | asr_quality lane: shadow-STT disagreement + confirm-by-card trigger | E06-lanes | blocked | HB-L22 | counsel + owner |
| INT-114 | engagement lane -> satisfaction proxies + pacing hints | E06-lanes | blocked | HB-L22 | counsel + owner |
| INT-135 | Voice intake UI (Hizli): states, recording indicator, inline cards, barge-in, RED UI, typed fallback | E08-mobile | todo | waits on INT-117 | agent (mobile) |
| INT-144 | Accessibility WCAG 2.2 AA pass + TR screen-reader labels + conformance report | E08-mobile | blocked | no blocker record | owner — no blocker record names it |
| INT-146 | EAS builds + OTA code signing + MobSF gate + store listings/privacy labels | E08-mobile | todo | ready | agent (mobile); sign-off: counsel |
| INT-152 | Clinic console: today list, statuses, read receipts, tenant isolation, SSO | E09-clinician | todo | waits on INT-151 | agent |
| INT-153 | Clinician feedback -> Langfuse annotation queues + acceptance metrics | E09-clinician | todo | waits on INT-151 | agent |
| INT-161 | FHIR push adapter (hospital FHIR/HAPI; SMART backend services auth) | E10-connectors | blocked | HB-A17 | HB-A17: owner (from the hospital) + counsel (the scope, from the DPA) |
| INT-186 | Experience & satisfaction module (CSAT/NPS/pulse/waits + SDS-01 export) | E12-admin | blocked | blockers.md | owner + compliance_officer |
| INT-190 | Cost module | E12-admin | blocked | HB-O8 | owner |
| INT-202 | Backups: pgBackRest PITR encrypted + MinIO replication + automated restore drill + evidence | E13-infra | in flight | #682 `int-202-restore-drill` conflicting | agent · sre-reviewer |
| INT-203 | Edge: Traefik + Coraza CRS + CrowdSec + cert-manager + prod egress proxy | E13-infra | blocked | HB-I13 · HB-I14 | owner |
| INT-206 | GitHub Actions self-hosted runners in TR DC + no-PHI-in-CI policy | E13-infra | blocked | HB-I7 | HB-I7: owner (spend + the choice of facility); counsel for the residency cla… |
| INT-213 | DPIA v1 + vendor transfer register + SCC set + Board notification workflow (5 business days) + hospital DPA t… | E14-legal | todo | ready | agent · legal-reviewer; sign-off: counsel |
| INT-214 | Breach machinery: KVKK 72h Board form automation + data-subject notices + USOM report (7545) + hospital notic… | E14-legal | todo | ready | agent · legal-reviewer |
| INT-217 | QMS core (ISO 13485): quality manual, design controls, ISO 14971 risk file, IEC 62304 class B plan, IEC 62366… | E14-legal | todo | waits on INT-216 | agent · legal-reviewer; sign-off: counsel |
| INT-218 | Clinical investigation package: protocol + ICF(tr) + KAEK ethics submission + TITCK application + insurance +… | E14-legal | todo | waits on INT-217 | agent · legal-reviewer; sign-off: counsel |
| INT-252 | Release process: semver, changelog, signed artifacts, store submission checklist, release-gate checklist in c… | E17-release | todo | ready | agent · legal-reviewer |
| INT-308 | carrier/geo sanity checks against SMS pumping are named in the security spec and implemented nowhere | E01-platform | blocked | blockers.md § | named in blockers.md § INT-308 |
| INT-317 | previsit output store + hospital read-back: one frozen versioned document per completed previsit, fetched by… | E10-connectors | in flight | doing; no open PR | agent · sre-reviewer |
| INT-319 | Dev on-prem expressive-TTS lane for scripted questions + latency assessment harness | E05-voice | blocked | blockers.md § | owner (the target GPU host) |
| INT-327 | Specialty-pack generator assembles the pending-value marker so no_placeholders stays green | E03-protocols | in flight | doing; no open PR | agent · clinical-reviewer |
| INT-330 | Motion: native-stack transition policy — 120 ms on every stack, legal instant, intake gesture-locked | E08-mobile | todo | ready | agent (mobile) |
| INT-332 | ADR: Motion system v1 (opacity-only ≤ 120 ms, arbiter order, no-motion surfaces, haptics policy, RED as root… | E00-governance | in flight | #571 `int-332-motion-adr` conflicting | agent (mobile); sign-off: owner |
| INT-343 | Mobile George client authenticates and requests only compiled-pack clip text | E08-mobile | todo | ready | agent (mobile) |
| INT-359 | Accessibility device audit (DA-01..DA-08) and the statement published in-app and web | E14-legal | blocked | HB-L9 | owner |
| INT-364 | Board 2018/10 organisational measures: the owner's evidence and counsel's four readings | E14-legal | blocked | blockers.md | owner |
| INT-369 | schemathesis API fuzzing runs in CI instead of being recorded as deferred | E13-infra | todo | ready | agent · sre-reviewer |
| INT-389 | Owner decision: second factor for console roles outside the patient-content set (TOTP vs aaguid) | E12-admin | blocked | no blocker record | owner — no blocker record names it |
| INT-380 | Extraction eval score on a named, dated, licensed corpus (INT-121 clause 3) | E07-records | blocked | HB-A13 · HB-A10 · HB-A2 | owner, with the DPO/counsel |
| INT-381 | On-hardware latency and live smoke for the row-9 extraction model (INT-124 clause: target < 3 s) | E07-records | todo | ready | agent · legal-reviewer; sign-off: owner (the target GPU host) |
| INT-401 | Rollback from the console (4-eyes) once a CD target exists | E12-admin | blocked | blockers.md § | named in blockers.md § INT-401 |
| INT-402 | Record-embedding model for the patient record index (files/03 §4.9.1) | E07-records | blocked | no blocker record | owner — no blocker record names it |
| INT-403 | What withdrawing documents consent does to the patient's record vectors | E02-data | blocked | no blocker record | owner — no blocker record names it |
| INT-408 | Workers tier SLOs: the owner decides the tier and its targets | E01-platform | blocked | no blocker record | owner — no blocker record names it |
| INT-398 | Document engine for records (files/03 rows 20-21): choose, verify the licence, register, sandbox | E07-records | blocked | no blocker record | owner — no blocker record names it |
| INT-399 | Real e-Nabiz export and MHRS SMS samples for the import parsers (HB-A1, Ask 2) | E07-records | blocked | HB-A1 | HB-A1: owner only — it is a citizen login |
| INT-374 | Step-up WebAuthn for privileged console actions outside the patient-content roles | E12-admin | todo | ready | agent · security-reviewer |
| INT-383 | Generated red-flag stubs anchor their timing on a duration slot the engine cannot read | E03-protocols | blocked | HB-C1 | HB-C1: Dr Efe Onganer (physician of record) + a paediatrician for the paedia… |
| INT-417 | share centre never shows another visit's grants, and an unreachable read never prints the empty-log footer | E08-mobile | todo | ready | agent (mobile) |
| INT-418 | privacy hide — the 'gizle' control and the third-party auto-hide (02 §5.2a rule 6) | E08-mobile | todo | waits on INT-338 | agent (mobile) |
| INT-419 | licence gate verifies native (Maven/CocoaPods) dependencies against the raw LICENSE, not only package.json | E00-governance | todo | ready | agent · security-reviewer |
| INT-434 | admin Council section — member selection with 4-eyes via flag_governance, per-member latency/tokens/agreement | E05-voice | todo | ready | agent · security-reviewer |
| INT-435 | council production composition — ModelAssignment adapter, triage re-run, clinician inbox sink, CD-07 binding | E05-voice | todo | ready | agent · sre-reviewer |
| INT-436 | offline Loop-2 yield_table proposal (replaces the cut runtime ranker) | E11-learning | todo | ready | agent · clinical-reviewer |
| INT-437 | document rules on the parse_document path — add/arm only, staleness, contested, identity match | E07-records | todo | ready | agent · sre-reviewer |
| INT-438 | deterministic red-flag lexicon, speaker attribution and backchannel lexicon | E03-protocols | todo | ready | agent · clinical-reviewer |
| INT-444 | model identity & drift hardening — /identity, drift canary, model@revision recording keys, schema lint, guard… | E05-voice | todo | ready | agent · sre-reviewer |
| INT-445 | hosted/self-hosted lanes wired into the mobile release build | E08-mobile | todo | ready | agent (mobile) |
| INT-456 | Spoken clip text carries markdown emphasis and an unresolved {{tenant.acil_location_tr}} placeholder into the… | E03-protocols | todo | ready | agent · clinical-reviewer |
| INT-457 | ON_SITE 112 gate checks the flag, numbers and action codes but not the spoken script text (decision: INT-432/… | E03-protocols | todo | ready | agent · clinical-reviewer |
| INT-458 | expand_tr passes ½ through unexpanded, and an over-long digit run crashes the build instead of refusing | E03-protocols | todo | ready | agent · clinical-reviewer |
| INT-476 | kiosk wipe clears the RED store, and the RED screen-reader cover does not hide the kiosk idle warning | E08-mobile | todo | ready | agent (mobile) |
| INT-487 | probe emitters use fullmatch for id, ref and sha shapes (invariant 6) | E12-admin | todo | ready | agent · security-reviewer |
| INT-489 | proxy-path gaps outside the packs — subject_role literal mismatch, mid-session speaker switch, carer route in… | E03-protocols | todo | ready | agent · clinical-reviewer |
| INT-493 | proxy mechanism follow-ups before any proxy content lands (from the INT-483 review) | E03-protocols | todo | ready | agent · clinical-reviewer |
| INT-463 | All CI jobs on the AWS self-hosted runner | E13-infra | blocked | HB-I7 | owner |
| INT-467 | A pool of three ephemeral intake-aws-ci runners, each isolated as runner 1 is | E13-infra | blocked | HB-I7 | owner |

### Live · P2 — Hospital pilot

| epic | done | in flight | blocked | todo |
|---|---:|---:|---:|---:|
| E01-platform | 1 | 0 | 0 | 0 |
| E03-protocols | 0 | 0 | 0 | 13 |
| E06-lanes | 0 | 0 | 1 | 0 |
| E07-records | 1 | 0 | 0 | 0 |
| E08-mobile | 3 | 4 | 0 | 0 |
| E10-connectors | 3 | 1 | 0 | 0 |
| E11-learning | 3 | 0 | 0 | 1 |
| E12-admin | 1 | 0 | 0 | 1 |
| E13-infra | 0 | 0 | 0 | 4 |
| E14-legal | 0 | 0 | 1 | 4 |
| E15-research | 2 | 0 | 1 | 0 |
| E17-release | 0 | 0 | 0 | 1 |

Remaining, in file order (32):

| id | title | epic | state | PR · blocker · dependencies | owner |
|---|---|---|---|---|---|
| INT-061 | Deep pack: cardiology | E03-protocols | todo | waits on INT-044 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-062 | Deep pack: neurology | E03-protocols | todo | waits on INT-044 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-063 | Deep pack: endocrinology | E03-protocols | todo | waits on INT-044 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-064 | Deep pack: urology | E03-protocols | todo | waits on INT-045 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-065 | Deep pack: ophthalmology | E03-protocols | todo | waits on INT-046 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-066 | Deep pack: ent | E03-protocols | todo | waits on INT-046 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-067 | Deep pack: orthopaedics | E03-protocols | todo | waits on INT-045 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-068 | Deep pack: dermatology | E03-protocols | todo | waits on INT-044 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-069 | Deep pack: obgyn | E03-protocols | todo | waits on INT-047 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-070 | Deep pack: paediatrics | E03-protocols | todo | waits on INT-048 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-071 | Deep pack: psychiatry | E03-protocols | todo | waits on INT-049 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-072 | Deep pack: oncology | E03-protocols | todo | waits on INT-044 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-073 | Deep pack: dentistry_general | E03-protocols | todo | waits on INT-050 | agent · clinical-reviewer; sign-off: physician of record (D18 agent lane for simulated patients) |
| INT-115 | acoustic lane (M3, investigational device module): our own ordinal head, in-memory window, zeroing, study ass… | E06-lanes | blocked | no blocker record | physician of record (D18 agent lane for simulated patients) |
| INT-174 | DSPy+GEPA offline optimisation (extraction, note modules only) with clinician-edit metric + held-out | E11-learning | todo | waits on INT-153 | agent |
| INT-191 | Tenants module + onboarding flow | E12-admin | todo | waits on INT-250 | agent · security-reviewer |
| INT-200 | Residency compose profile (GPU) + runbooks | E13-infra | todo | waits on INT-097 | agent · sre-reviewer; sign-off: owner (the target GPU host) |
| INT-201 | k8s: k3s + Argo CD + Kyverno/Sigstore admission + PSS restricted + default-deny + Harbor | E13-infra | todo | ready | agent · sre-reviewer; sign-off: owner (infrastructure) |
| INT-204 | Mesh mTLS (Linkerd) + default-deny NetworkPolicies | E13-infra | todo | waits on INT-201 | agent · sre-reviewer |
| INT-207 | Chaos suite (monthly) + load to pilot x3 + autoscaling rules | E13-infra | todo | waits on INT-201 | agent · sre-reviewer |
| INT-219 | Technical documentation (Annex II/III) + clinical evaluation (MDCG 2020-1) + PMCF + notified-body selection | E14-legal | todo | waits on INT-217 | agent · legal-reviewer; sign-off: counsel |
| INT-220 | Registrations: UTS (TCKKD-KLVZ-03) + UDI; KTS (SBYS) pack; BTK yer saglayici; traffic-log retention 5651 | E14-legal | todo | waits on INT-219 | agent · legal-reviewer; sign-off: counsel |
| INT-221 | Public-hospital pack: Genelge 2019/12 residency attestation + DDO Rehber mapping + USVS conformance | E14-legal | blocked | HB-L11 · HB-L27 | Turkish counsel (KVKK / health-law), instructed by the owner |
| INT-222 | Consumer/commercial: mesafeli sozlesme pre-info + withdrawal (if paid tier), IYS integration for marketing, T… | E14-legal | todo | ready | agent · legal-reviewer; sign-off: counsel |
| INT-227 | AI governance file: model cards, TR bias/fairness eval (dialect, gender, age), transparency labels, EU AI Act… | E14-legal | todo | waits on INT-116 | agent · legal-reviewer |
| INT-231 | Study tooling: instruments + analysis notebooks for tracks 1-6 (voice vs typed, triage validation, note quali… | E15-research | blocked | HB-R1 · HB-L1 | owner + counsel, after HB-L1 |
| INT-250 | Tenant onboarding: config, branding, packs, DPA signature via KEP/e-imza, runbook | E17-release | todo | waits on INT-213 | agent · legal-reviewer |
| INT-320 | Embeddable white-label integration: partner 'Start pre-visit' button + tenant handshake (ADR + scaffold) | E10-connectors | in flight | doing; no open PR | agent · legal-reviewer; sign-off: counsel |
| INT-336 | Motion: presence orb — one UI-thread state visual replacing PulseDot and the dialogue spinners | E08-mobile | in flight | #716 `int-336-presence-orb` conflicting | agent (mobile) |
| INT-337 | Motion: dialogue transients wired to the arbiter | E08-mobile | in flight | #717 `int-337-dialogue-transients` conflicting | agent (mobile) |
| INT-338 | Motion: section sheet — measured fade budget, instant privacy and RED closes | E08-mobile | in flight | #703 `int-338-section-sheet` | agent (mobile) |
| INT-340 | Haptics: one policy, sticky suppression, server-confirmed success | E08-mobile | in flight | #710 `int-340-haptics-policy` conflicting | agent (mobile) |

### Live · P3 — The record that travels

| epic | done | in flight | blocked | todo |
|---|---:|---:|---:|---:|
| E02-data | 2 | 0 | 0 | 0 |
| E05-voice | 0 | 0 | 1 | 0 |
| E08-mobile | 0 | 1 | 0 | 1 |
| E14-legal | 0 | 0 | 0 | 1 |
| E17-release | 0 | 0 | 0 | 1 |

Remaining, in file order (5):

| id | title | epic | state | PR · blocker · dependencies | owner |
|---|---|---|---|---|---|
| INT-097 | residency_tr_models tier on GPU: compose.residency, node sizing, on-hardware latency evidence | E05-voice | blocked | HB-I5 | HB-I5: owner |
| INT-225 | ISO 27001 ISMS: scope, SoA, risk register, policies, internal audit, certification audit | E14-legal | todo | ready | agent · legal-reviewer; sign-off: counsel |
| INT-251 | Billing: hospital e-Fatura via provider; patient subscription via PSP (iyzico/PayTR); never store PAN | E17-release | todo | waits on INT-222 | agent · legal-reviewer; sign-off: counsel |
| INT-341 | Motion: press-opacity tokens | E08-mobile | todo | waits on INT-330 | agent (mobile) |
| INT-342 | Motion: content reveal and a static skeleton | E08-mobile | in flight | #704 `int-342-content-reveal` | agent (mobile) |

### Open PRs whose id has no row on main

| PR | id | phase | branch | rows the branch adds | title |
|---|---|---|---|---|---|
| #481 (conflicting) | INT-316 | — | `int-316-paired-row` | INT-316 | INT-316: A paired row has no flex contract, so the label collapses while the trailing control keeps its width |
| #615 (conflicting) | INT-371 | P1 | `int-371-intake-finish-to-review` | INT-371 | INT-371: Intake flow — Bitirdim finishes to review, the open hint shows once, typed-to-handoff proven |
| #620 (conflicting) | INT-375 | P1 | `int-375-compiler-ask-order` | INT-375 | INT-375: protocol compiler refuses a gate that reads a later slot (files/13 §9.5) |
| #628 (conflicting) | INT-379 | P1 | `int-379-generator-capabilities` | INT-379 | INT-379: generator capabilities — duration=omit, code answers, skip_if |
| #633 (conflicting) | INT-384 | P1 | `int-384-admin-flat-error-code` | INT-384 | INT-384: Admin console reads the API's flat refusal code, so an IP or unconfigured refusal is named as itself |
| #642 (conflicting) | INT-388 | P1 | `int-388-signoff-packets` | INT-388 | INT-388: physician sign-off packets per department from the review queue and verification trail |
| #725 (conflicting) | INT-422 | P1 | `int-422-design-system-refresh` | INT-422 | INT-422: design system refresh — native Apple feel, restrained palette, SF Symbols, no AI-generic styling |
| #728 | INT-423 | P1 | `int-423-chat-rhythm` | INT-422, INT-423 | INT-423: chat interface — natural rhythm and Liquid Glass materials (HIG), content stays solid |
| #729 | INT-420 | P0 | `int-420-onvizit-rebrand` | INT-420 | INT-420: Önvizit everywhere — finish the Vizite→Önvizit rebrand on main |
| #734 | INT-424 | P1 | `int-424-voice-profiles-v2` | INT-424 | INT-424: ElevenLabs delivery profiles v2 — sample-tuned naturalness + expressive-model ADR proposal |
| #737 | INT-427 | P1 | `int-427-specialty-wave` | INT-427 | INT-427: dynamic department question sets — next specialty/cluster wave (author, verifier, engineer) |
| #738 | INT-425 | P1 | `int-425-store-screenshots` | INT-422, INT-423, INT-425, INT-433 | INT-425: App Store / Play screenshots — story-led, real captures, app-store-screenshots skill |
| #740 | INT-433 | P1 | `int-433-question-screen` | INT-422, INT-423, INT-433 | INT-433: question screen redesign — native progress, filled inputs, capsule chips, Liquid Glass bars (Mobbin-… |
| #741 (conflicting) | INT-430 | P0 | `int-430-agent-council` | INT-430 | INT-430: agent council for dynamic questioning — answers + documents drive follow-ups, deterministic engine a… |
| #751 | INT-428 | P0 | `int-428-hosted-lanes` | INT-428 | INT-428: hosted model lanes (OpenAI or similar) switchable from the admin panel, with a GPU switch-over |
| #761 | INT-439 | P0 | `int-439-spend-cap` | INT-428, INT-439 | INT-439: HB-O8 closed — 80 USD/month elective model-spend cap (warn at 80 %), every hosted call charged, sour… |
| #766 | INT-446 | P0 | `int-446-red-e2e` | INT-446 | INT-446: RED end to end in the app — rules-engine hop on both lanes, pre-positioned RED screen mounted |
| #768 | INT-440 | P0 | `int-440-voice-first-e2e` | INT-440 | INT-440: Voice-first end-to-end test on the iOS simulator + fixes |
| #771 (conflicting) | INT-451 | P1 | `int-451-mobile-interactions` | INT-422, INT-423, INT-433, INT-451 | INT-451: mobile interaction patterns within ADR-033 — row press highlight, glass nav bar, ADR-037 proposal |
| #773 | INT-453 | P0 | `int-453-red-path-winner` | INT-446, INT-453 | INT-453: voice-runtime RED path triggers the winning rule's own script, not rule_ids[0] |
| #774 | INT-442 | P1 | `int-442-egress-proxy` | INT-428, INT-442 | INT-442: egress forward proxy for the synthetic AWS host (hosted lanes reach only allow-listed vendors) |
| #775 | INT-443 | P1 | `int-443-elevenlabs-hosted-tts` | INT-424, INT-428, INT-442, INT-443 | INT-443: ElevenLabs as hosted TTS provider, default on the synthetic AWS host (v2 delivery profiles) |
| #776 | INT-450 | P1 | `int-450-admin-ui` | INT-450 | INT-450: admin-web UI upgrade with owner-listed component libraries (licence-checked) |
| #782 (conflicting) | INT-455 | — | `int-455-tr-numeral-suffix` | INT-455 | INT-455: expand_tr expands a numeral's apostrophe suffix (112'yi), so the life-threat RED REMOTE script compi… |
| #784 | INT-459 | P1 | `int-459-admin-premium` | INT-450, INT-459 | INT-459: admin-web premium redesign |
| #788 (conflicting) | INT-461 | — | `int-461-adr-038-motion-amendment` | INT-461 | INT-461: ADR-038 — ADR-033 amendment: spring-in bubbles, selection haptics on chips and the mic, in-tree dete… |
| #792 | INT-462 | — | `int-462-native-chat` | INT-422, INT-423, INT-433, INT-451, INT-461, INT-462 | INT-462: native chat — Liquid Glass capsule composer with mic and send inside, spring-in bubbles, checked cap… |
| #796 (conflicting) | INT-465 | P0 | `int-465-generic-red-active` | INT-446, INT-453, INT-465 | INT-465: generic RED active from CD-24, and the red rule set signed with a synthetic-only test key |
| #797 | INT-466 | — | `int-466-chat-stage` | INT-422, INT-423, INT-433, INT-451, INT-461, INT-462, INT-466 | INT-466: chat stage — ADR-039 and the live dialogue on the new visual language |
| #801 | INT-464 | — | `int-464-native-welcome` | INT-422, INT-423, INT-433, INT-451, INT-461, INT-462, INT-464, INT-466 | INT-464: native welcome and sign-in in the stage language (ADR-039 S7) |
| #804 (conflicting) | INT-470 | P1 | `int-470-owner-question-clinical` | INT-470 | INT-470: resolve INT-448's owner questions — clinical ones under D18 (CD-110), product and data ones by owner… |
| #806 | INT-472 | — | `int-472-review-grouped` | INT-422, INT-423, INT-433, INT-451, INT-461, INT-462, INT-464, INT-466, INT-472 | INT-472: review and send as iOS grouped inset lists |
| #808 | INT-473 | — | `int-473-detent-sheet` | INT-422, INT-423, INT-433, INT-451, INT-461, INT-462, INT-464, INT-466, INT-472, INT-473 | INT-473: in-tree detent sheet (ADR-038 A3) for the dialogue's section sheet |
| #809 (conflicting) | INT-471 | P1 | `int-471-legal-lane` | INT-470, INT-471 | INT-471: legal lane — sourced legal-author agent and independent legal reviewer decide legal items (D25, synt… |
| #813 | INT-468 | P1 | `int-468-red-clinical-values` | INT-468 | INT-468: CD-111 — the cardiac RED do-not lines and the unanswered location wait, sourced under D18 |
| #816 | INT-469 | P1 | `int-469-adli-tip-no-report-purpose` | INT-469 | INT-469: Adli Tıp pack drops the allied report-purpose item (rapor_amaci), per LD-01 |
| #818 | INT-474 | P1 | `int-474-deployment-role-gate` | INT-474 | INT-474: deployment-role gate for relatives', household and partner data categories before any register row i… |
| #819 | INT-477 | P1 | `int-477-capture-solid-chrome` | INT-422, INT-423, INT-433, INT-451, INT-461, INT-462, INT-464, INT-466, INT-472, INT-473, INT-477 | INT-477: solid chrome on capture-protected screens (owner: "solid"), never Liquid Glass |
| #821 | INT-478 | P1 | `int-478-capture-protection-refcount` | INT-478 | INT-478: hold screen-capture protection until the last protected screen closes |
| #828 | INT-482 | P1 | `int-482-store-listing` | INT-482 | INT-482: store listing readiness — EAS metadata, privacy answers, review notes, as Önvizit |
| #833 | INT-483 | P1 | `int-483-self-proxy` | INT-483 | INT-483: self/proxy answering — ADR-040 and the subject_role addressing mechanism |
| #834 (conflicting) | INT-485 | — | `int-485-admin-proxy-no-email-logs` | INT-485 | INT-485: admin oauth2-proxy logs no staff email or client IP (invariant 6) |
| #835 | INT-484 | P1 | `int-484-ld06` | INT-470, INT-471, INT-484 | INT-484: LD-06 — what admin research and improvement analytics may hold (step 1, synthetic/test scope) |
| #840 | INT-481 | P1 | `int-481-observability-stack` | INT-481 | INT-481: staff observability stack — Grafana dashboards and admin alerts on the AWS host |
| #842 | INT-491 | P1 | `int-491-orb-variants` | INT-422, INT-423, INT-433, INT-451, INT-461, INT-462, INT-464, INT-466, INT-472, INT-473, INT-491 | INT-491: the lens is the orb — every orb layer turns one way (ADR-039 amendment, D29) |
| #843 | INT-492 | P1 | `int-492-progress-micro` | INT-422, INT-423, INT-433, INT-451, INT-461, INT-462, INT-464, INT-466, INT-472, INT-473, INT-492 | INT-492: question progress and micro-interactions — segmented capsule, chip check slot, press response, still… |
| #845 (conflicting) | INT-486 | — | `int-486-ops-prom-label-fullmatch` | INT-486 | INT-486: ops_prom label check uses fullmatch, so a trailing newline is refused |
| #854 | INT-496 | P2 | `int-496-play-later` | INT-482, INT-496 | INT-496: Google Play deferred — the list of everything Play will need |
| #855 | INT-475 | P1 | `int-475-red-staff-notify` | INT-446, INT-453, INT-465, INT-475 | INT-475: RED staff notification on the typed hop and the device's location answer reach the server |
| #860 | INT-495 | P1 | `int-495-asc-listing` | INT-482, INT-495, INT-496, INT-502 | INT-495: App Store listing for Önvizit — the App Store Connect draft writer and the promoted App Store copy |
| #861 | INT-494 | P1 | `int-494-apply-cd111` | INT-446, INT-453, INT-465, INT-468, INT-494 | INT-494: apply CD-111 to the served cardiac RED rule — decided do-not lists, re-signed synthetic rule set |
| #863 | INT-490 | P1 | `int-490-research-analytics` | INT-490 | INT-490: research and improvement analytics in the admin panel, anonymised aggregates within LD-06 |
| #866 | INT-497 | P1 | `int-497-voice-experience` | INT-497, INT-504, INT-505 | INT-497: voice experience — the turn ends on silence, one queue per turn, one loudness, measured |

### Open PRs that name no backlog id

| PR | branch | title |
|---|---|---|
| #514 | `fix-catalogue-connector-inbound-metric` | fix(observability): catalogue connector_inbound_messages_total (INT-162 follow-up) |

### Open issues with no row on main or on any open PR branch

| issue | id | phase | title |
|---|---|---|---|
| #822 | INT-479 | P2 | INT-479: INT-465 RED review follow-ups (non-blocking, from the round-5 approval) |
| #823 | INT-480 | P2 | INT-480: legal lane follow-ups (non-blocking, from the INT-471 round-3 approval) |
| #829 | INT-488 | P1 | INT-488: store-review sign-in path for release builds (synthetic tenant only), security-reviewed |
| #850 | INT-498 | P1 | INT-498: feature audit on the AWS synthetic stack — every requested feature working end to end, nothing demo |
| #849 | INT-499 | P1 | INT-499: apply ADR-039 and the Liquid Glass research to the remaining screens — visits list, documents, share… |
| #853 | INT-501 | P1 | INT-501: fix node-forge, braces and http-cache-semantics before their time-boxed scanner exceptions expire (1… |
| #857 | INT-503 | P1 | INT-503: RED staff-notification follow-ups (from the INT-475 approval) — three must land before the voice lan… |
| #862 | INT-506 | P2 | INT-506: App Store listing follow-ups from the INT-495 legal approval (non-blocking) |
| #864 | INT-507 | P1 | INT-507: per-question, platform and triage-share analytics from anonymous-at-source counters (no per-person r… |
| #865 | INT-508 | P1 | INT-508: node-forge and braces have no upstream fix — renew their time-boxed exceptions or replace the depend… |

### Drift the generator sees — reported here, never repaired by it

- **`done` rows whose GitHub issue is still open** (68; `make backlog-sync` closes them, and the live sync is the operator's): INT-016 (#14), INT-018 (#16), INT-022 (#20), INT-023 (#21), INT-024 (#22), INT-025 (#23), INT-030 (#24), INT-031 (#25), INT-032 (#26), INT-033 (#27), INT-034 (#28), INT-035 (#29), INT-036 (#30), INT-037 (#31), INT-038 (#32), INT-040 (#33), INT-041 (#34), INT-042 (#35), INT-057 (#50), INT-059 (#52), INT-060 (#53), INT-080 (#67), INT-081 (#68), INT-082 (#69), INT-083 (#70), INT-084 (#71), INT-085 (#72), INT-090 (#73), INT-091 (#74), INT-092 (#75), INT-093 (#76), INT-094 (#77), INT-096 (#79), INT-102 (#85), INT-103 (#86), INT-110 (#87), INT-120 (#95), INT-131 (#101), INT-132 (#102), INT-133 (#103), INT-134 (#104), INT-136 (#106), INT-137 (#107), INT-139 (#109), INT-140 (#110), INT-141 (#111), INT-145 (#115), INT-150 (#117), INT-160 (#121), INT-170 (#125), INT-171 (#126), INT-172 (#127), INT-175 (#130), INT-228 (#252), INT-180 (#131), INT-205 (#149), INT-223 (#165), INT-224 (#166), INT-230 (#170), INT-240 (#172), INT-241 (#173), INT-242 (#174), INT-253 (#178), INT-254 (#291), INT-255 (#328), INT-263 (#364), INT-353 (#559), INT-452 (#765)
- **`todo`/`doing` rows with a merged INT PR** (8; `scripts/backlog/reconcile.py` decides whether they are done): INT-202 (#321), INT-317 (#602), INT-320 (#485, #486, #489), INT-330 (#553), INT-336 (#702), INT-341 (#572), INT-349 (#564), INT-421 (#723)
- **`todo` rows with an open PR** (8; shown in flight above): INT-058, INT-332, INT-336, INT-337, INT-338, INT-340, INT-342, INT-350
- **`doing` rows with no open PR** (5): INT-317, INT-320, INT-327, INT-349, INT-421
- **`awaiting-human` rows no blocker record names** (10): INT-144, INT-347, INT-356, INT-358, INT-389, INT-402, INT-403, INT-408, INT-398, INT-394

<!-- END generated live status -->

---

## 0. The five facts that shape this plan

### F1 — 58 % of the backlog is behind a human
Parsing `docs/backlog/issues.yaml` (175 issues; after the v2.0 graph fixes: no cycles, no missing dependencies, no phase inversions), **101 issues are gated on a human decision, directly or transitively.** The autonomous loop can complete **47 of the 91 P0 issues** unattended and then stops.

`./loop.sh 40` would stall around iteration 25–30, and v1.4's LOOP.md gave it no way to say why: `awaiting-human` is not `done`, so every dependent silently never becomes Ready.

### F2 — One issue unblocks 78 others

| Issue | Unblocks | Gate | Depth on the critical path |
|---|---|---|---|
| **INT-043 `base.intake` pack** | **78 of 175** | clinical | 9 |
| INT-116 Wellbeing engine | 12 | clinical | 15 |
| INT-117 `device_functions` flag | 10 | legal | 16 |
| INT-044 `cluster.medical` pack | 8 | clinical | 10 |
| INT-210 Legal document set | 7 | legal | — |

v1.4 placed INT-043 at depth 9, so the agent would work for days before you ever saw the thing that unblocks everything else. **v2.0 front-loads all five.**

### F3 — The clinical investigation is 7–12 months and strictly sequential
TCKAY (RG 31890, 08.07.2022): **m.8/2** requires the ethics decision to be submitted *as part of* the TİTCK application — they cannot run in parallel. **m.5/2(a)** requires non-clinical validation *before* submission (for software, a documented bench and retrospective validation of the triage engine — a work package v1.4 did not show). **m.5/6** restricts sites to a **university** health application & research centre, an approved university-affiliated R&D centre, or an MoH training & research hospital — **a general private Acıbadem hospital does not qualify.** The study must sit at Acıbadem Mehmet Ali Aydınlar Üniversitesi's research centre; KAEK is that university's committee, so this is workable, but the site must be named.

| phase | statutory clock | realistic |
|---|---|---|
| Non-clinical validation + protocol + ICF(tr) + Annex XV Pt II + risk file | — | 8–14 wk |
| Insurance (parallel) · site + PI + budget contracting (parallel, often the real bottleneck) | — | 2–4 wk · 4–8 wk |
| KAEK ethics | ~30 d | **4–12 wk** (monthly agendas) |
| TİTCK | 20 iş günü | 4 wk clean; **8–14 wk with one eksiklik yazısı** |
| Site initiation → first participant | — | 2–4 wk |

**≈ 9 months is the sensible plan; 6 months is an aggressive best case.**

### F4 — Cost is load-independent, and the vendor bill is noise
~**€2,800–4,400/month fixed** once `residency_tr` exists, and **≈ €0 marginal** for the 300-session pilot (≈ 5 sessions/working day; the GPU sits at < 1 % utilisation). That is **€10–15 of infrastructure per pre-visit**.

Vendor cost is **$0.13–0.28 per session ⇒ $40–85 for the entire pilot**, of which the extraction LLM is 70–80 % (reducible by caching the invariant slot schema instead of re-sending it on all 18 turns). The clip cache is the design's single best cost decision and it works.

The security and observability tiers alone (22 GB RAM) exceed the entire application tier. **Every cost lever that matters is in the self-hosting decision, not the vendor decision** — the opposite of where `08` directs attention.

### F5 — Two instruments are licence-blocked
- **C-SSRS**: Clario holds an *exclusive* RFMH licence for "any electronic format" — $40,000 start-up + $7,500/yr + $5,000 per certified version + **$4 per administration**. Columbia's free route covers healthcare providers embedding it in their own EHR; we are a for-profit vendor shipping a patient-self-completed electronic Turkish version, which is neither. Training is *not* the issue — the electronic sublicence is. Also: the only Turkish validation is **adolescents 12–18 only**.
- **WHO-5**: copyright transferred to WHO in 2024 and published **CC BY-NC-SA 3.0 IGO — NonCommercial**. Embedding it in a for-profit product is outside the licence, and ShareAlike imposes a copyleft obligation on any adaptation (reformatting for mobile counts).

Both are **BLOCKED** until written permission exists. **HAQ-DI** is NEEDS-PERMISSION: Stanford's "public domain" statement covers the **English** version only, and under FSEK a Turkish translation is an *işlenme eser* with its own rights holder.

---

## 1. Phase table (gate-driven)

| Phase | Theme | Ends when — the exit **artefact** | Forecast |
|---|---|---|---|
| **P0 Foundation** | Monorepo, CI, the four safety guards, protocol DSL + compiler, deterministic triage, voice-runtime core on mocks, typed-mode intake end-to-end, **`base.life_threat` universal rule set**, admin skeleton | `make check` + `make safety` + `make security` green from a clean clone · every branch resolves to a reviewed pack · runtime invariants 1–12 pass on fake clocks · **a deliberately broken RED rule fails the suite and is reverted, on record** · issue machinery live | **12–20 weeks** |
| **P1 Fast mode, device-off** | Turkish voice intake E2E (⚠ **`residency_tr` — `cascade_fast` no longer exists**, `00 §0b`), **`residency_tr_media` — SFU + TURN + API + Postgres in İstanbul (§2.1)**, records ingestion, patient summary, clinician note via Doctor Link, CSAT/NPS, real telemetry | 20 internal users × 3 specialties · **client-side measured** round-trip meets §4 targets · note acceptance ≥ 70 % · DPIA v1 signed · ⚠ **Art. 9 standard contracts: none required on the PHI path** — under self-hosting there is no cloud vendor in use, which is the strongest form this control can take. The row survives as an audit statement, not as work | **+10–16 weeks** |
| **P2 Hospital pilot** | Detailed mode, check-in, clinic console, **bilateral integration with the pilot group's own technology arm** (⚠ *corrected — see the note under this table; the FHIR connector is an outbound export, not the integration*), companions, top-10 deep packs | Pilot at one hospital group · ≥ 300 real pre-visits · clinician read rate ≥ 80 % · CSAT ≥ 4.2 · zero PHI incidents · external pen-test passed, findings closed | **+4–6 months** |
| **P2b Clinical investigation** *(parallel track — starts in P0)* | The only lawful route to `device_functions=on` | KAEK approval **then** TİTCK permission, recorded against a named study id **and protocol version** · insurance in force · first participant enrolled | **≈ 9 months from protocol drafting** |
| **P3 The record that travels** | e-Nabız application, HBYS.API connector, consented visit recording, longitudinal timeline, **openEHR added as an export**, `residency_tr_models` when a public tenant signs **and a signed GPU capacity contract exists** (`residency_tr_media` ships in P1, §2.1) | 2nd hospital group · e-Nabız sandbox or a formal decision · published evaluation report | **+6–9 months** |
| **P4 CE + scale** | Class **IIb** conformity assessment, ÜTS registration, B2B2C white-label | Notified-body certificate · `device_functions=on` commercially | Gated on P2b evidence |

> **P3 is currently unplanned.** It holds 2 issues while its own description covers e-Nabız, HBYS.API, diarised visit recording and the longitudinal timeline. Either scope it or stop calling it a phase.

> 🔵 **P2 aimed its connector effort at the wrong counterparty. This is a strategy correction, not a footnote.** **ACIBADEM TEKNOLOJİ A.Ş. is #2 on SBSGM's Aktif HBYS Listesi** — the pilot partner *is its own HBYS vendor*. The active list carries exactly **57 firms (31 Jul 2026)** and **the passive list is empty**, so that is the complete registered universe; **Grup Florence Nightingale, Hisar and Gaziantep Özel self-register the same way.**
>
> Therefore: **for private hospital groups — which is the entire go-to-market (`01 §3`) — the integration counterparty is the group's own technology arm, not a third-party HBYS vendor.** Akgün, Sisoft, Probel and Monad matter for **public** hospitals, and that is a later and different motion with a different sales cycle: a şartname and a tender rather than a commercial agreement with the group that already runs the estate. P2's connector work is a **bilateral, per-tenant integration with Acıbadem Teknoloji** — endpoints registered out-of-band at onboarding and bound to the signed DPA (`03 §12`, `10 §9.1` inv. 46) — most likely HL7 v2 feeds or the arm's own API.
>
> ⚠️ **UNVERIFIED: what interfaces Acıbadem Teknoloji actually exposes.** Only its registration status is confirmed. Do not size the P2 connector, or promise a payload shape, before that conversation happens — and note that it is a conversation with the pilot partner we already have, which is the cheap part of this correction.

---

## 1a. Phase gates — the Definition of Done at phase scale

The per-issue DoD lives in `07 §3.3` and is checked by CI on every PR. **This section is the phase-level equivalent**, and it exists because the phase table's "exit artefact" column was one cell wide and a phase gate is not a sentence. A phase ends when **every** line below is true and the evidence is committed — not when the work "feels" finished, not when the calendar says so, and not when the remaining items are "only" human-gated.

**Three rules that apply to all four gates.**

1. **The evidence is a file, not a claim.** Every line resolves to something committed under `docs/evidence/` or `docs/regulatory/` with a date. "We ran it and it passed" is not an exit artefact; the recorded run is.
2. **Human-gated items do not close a phase early.** A gate line that reads *"a named clinician has signed"* is not satisfied by a green test suite, a self-review, or a note saying the content was drafted carefully. See `HUMAN_BLOCKERS.md` — that file exists so the gate can name who.
3. **Gates only tighten.** A phase gate is never relaxed to let a phase close. If a line cannot be met, the phase does not end and the line is not edited; what changes is the plan, and the change is recorded in `00 §3` with its reason.

### P0 — Foundation

- [ ] `make check`, `make safety` and `make security` green **from a clean clone**, not incrementally, with the runs committed.
- [ ] Runtime invariants **1–12** pass on fake clocks; the six-tool introspection test exists and a temporary seventh tool makes it fail (proved, reverted).
- [ ] **A deliberately broken RED rule fails `make safety` and is reverted, on record — both runs in the evidence file.** This is the P0 exit artefact and it is not optional: it is the only proof that the golden suite is load-bearing rather than decorative. **A suite that stays green through a broken RED rule is worse than no suite, because it is trusted.**
- [ ] Every RED golden has its **near-miss negative control**, and the suite fails if one is missing. The positive passes by construction and only detects under-triggering; **over-triggering is invisible in production** and surfaces months later as alert fatigue, by which time the rule that caused it cannot be identified.
- [ ] The compiler rejects a RED rule with no `register`, and one whose action does not resolve for `REMOTE`, `ON_SITE` and `UNKNOWN` (proved, reverted).
- [ ] The clip-manifest round-trip gate — synthesise → **independent** ASR → normalised diff — fails the build on a planted unexpanded numeral (proved, reverted).
- [ ] Every branch in `taxonomy/branches.yaml` resolves to a reviewed pack; resolving an L0 pack for a session raises.
- [ ] A pack referencing a non-`GO` instrument fails the build; a pack with an unfilled `clinical_signoff` block cannot emit an L1 bundle.
- [ ] Issue machinery live end-to-end: backlog on GitHub with labels and milestones, `no_placeholders` and `evidence_check` each proved on a planted violation and reverted.
- [ ] `00_STATE.md` has a row for every decision taken during the phase, in the commit that took it.
- [ ] **Human-gated and therefore not self-certifiable:** `base.intake` and `base.life_threat` signed by a named licensed physician (paediatric rules by a paediatrician) — HB-C1…C7. **P0 does not end without this, however green CI is.**

### P1 — Fast mode, device-off

- [ ] Round-trip latency **measured client-side on real devices, reported per network profile** (`02 §8.1`) — never as a single number, because publishing one floor for a distribution this wide is itself the mistake.
- [ ] Note acceptance ≥ 70 % on real clinician review; DPIA v1 signed; VERBİS registered.
- [ ] **Per-rule extraction sensitivity and specificity against a Turkish clinical reference standard** — covering agglutinative negation and evidentiality, second-language speakers, and a "did not understand" state distinct from "no". **This gates P1 exit**: without it the triage engine's inputs are unvalidated and the "deterministic rules engine" claim is unsupported, because a deterministic engine over probabilistic inputs is not deterministic. Recorded as a dated internal measurement — **never as a published accuracy claim** (ADR-022).
- [ ] `residency_tr_media` live: the **testable** claim is that patient audio bytes never leave Türkiye on the media path, asserted by a test, not by a diagram.
- [ ] Network telemetry collected from session one for the four **UNVERIFIED** transport unknowns — Turkish mobile packet loss, hospital guest wifi, handset mic-capture buffer, NetEq concealment-versus-delay — and the `02 §8.1` NFRs **re-derived after 100 sessions**.
- [ ] De-identification reported as **recall per entity class on a held-out, human-labelled, real-transcript corpus with a published confusion matrix** — not as a single "< 0.1 % leak rate" measured on a corpus we authored, which is unfalsifiable as defined.
- [ ] Mutation testing on the triage evaluator has run and its findings are closed.

### P2 — Hospital pilot · P2b — Clinical investigation

- [ ] ≥ 300 real pre-visits; clinician read rate ≥ 80 %; CSAT ≥ 4.2; **zero PHI incidents**; external pen-test passed with findings closed.
- [ ] **Primary safety metric reported as misses, not false positives** — zero clinician-confirmed missed time-critical conditions, measured by **chart-linked follow-up of a sample of GREEN sessions**, not clinician self-report, which under-detects.
- [ ] Per-rule false-RED rates published internally and reviewed rule by rule through the console queue.
- [ ] The integration is **bilateral with the group's own technology arm**, bound to the signed DPA, with endpoints registered out-of-band at onboarding — not a third-party HBYS connector, and not sized before that conversation has happened (HB-A5).
- [ ] The self-hosting release gate is **enforced** from here (the registry and the gate were built in P0).
- [ ] **P2b, and it is a separate clock:** KAEK approval **then** TİTCK permission — they cannot run in parallel — recorded against a named study id **and protocol version**, with insurance in force, at a **qualifying university research centre** (HB-L1). ⚠ **The 300-session pilot cannot validate the `acoustic` lane**: that study is n ≈ 800, and the pilot is off by ~3×.

### P3 / P4

- [ ] `residency_tr_models` ships only against a **signed GPU capacity contract naming provider and SKUs** — and **no availability date is published before that contract exists** (HB-I5).
- [ ] e-Nabız: a formal Ministry decision on the **deposit** path, or a recorded decline. Not a read path — there is no mechanism and no category for one.
- [ ] Class **IIb** conformity assessment with a clinical evaluation report per MDCG 2020-1; ÜTS registration; `device_functions=on` commercially only after the notified-body certificate.
- [ ] Throughout: **no accuracy claim** has entered `docs/regulatory/`, `docs/legal/`, marketing or a store listing — the `claims-scan` CI gate has been green on every release build since P0.

---

## 2. What P0 builds — and what was cut

### 2.1 Cut from P0/P1 (≈ 29–39 engineer-weeks recovered) — ⚠ and one item **pulled forward** on measurement

| Cut | Why | Recovered |
|---|---|---|
| **openEHR / EHRbase → P3; FHIR-only until then** | **No P0/P1 feature issues an AQL query.** Every real consumer — Doctor Link, HBYS.API, e-Nabız, SGK, the clinician note, the app — is FHIR / ICD-10 / LOINC / ATC / text. `03 §7` already concedes SNOMED CT is unavailable in Türkiye, removing much of openEHR's semantic advantage before you start. No Python library generates Operational Templates; OPT authoring is a Java / Archetype-Designer activity. And round-trip goldens over a lossy openEHR↔FHIR mapping would pass only because we wrote them to match the mapper — **a test that cannot fail, which `07 §TDD` explicitly forbids.** **Keep the archetype-path annotation on every slot**: it costs nothing and *is* the migration plan. | 14–20 wk |
| **`residency_tr_models` → P3** ⚠ **split 25 Aug 2026 — see below** | vLLM + TTS + observer lanes in Türkiye. `06` makes residency mandatory for **public** hospitals; the pilot is Acıbadem — **private**. This half builds a GPU datacentre to run at < 1 % utilisation for 300 sessions. Keep the gateway abstraction and profile-parity tests so the swap stays a config change. | 8–12 wk + €1.2–2.5k/mo |
| **`residency_tr_media` → P1** ⚠ **NEW — pulled forward, not cut** | LiveKit SFU + TURN + API + Postgres in İstanbul. **This is a latency *win*, not a cost**: −39 ms p50 / −47 ms p95 of round-trip media time, measured (`03 §4.4`). It is also a genuine KVKK strengthening and **needs no GPU**. AWS opened `eu-central-1-ist-1a` (Local Zone, GA May 2026) with C7i/M7i/R7i, EBS, VPC, ECS, EKS, ALB, Direct Connect and S3 One Zone-IA — exactly this tier's shape. LiveKit Cloud has no Turkish region, so we self-host the Apache-2.0 server, **which makes us the operator of TURN as well**. | — (net negative latency; ~€0.3–0.6k/mo) |
| ~~`affect` + `acoustic` observer lanes~~ — **NOT CUT. Retained and hardened.** | ⚠️ An earlier draft of this table proposed cutting these on cost and PHI-egress grounds. **That was based on a misreading of `03 §4.7` and is withdrawn.** The `acoustic` lane is a **Kintsugi DAM-class model with open weights, self-hosted, in every profile** — there is no vendor, no second audio stream and no cross-border transfer. And `affect` **already has a self-hosted implementation specified** (open SER, emotion2vec-class) for `residency_tr`; the vendor route applies only to `cascade_fast`. `linguistic`, `asr_quality` and `engagement` are local in all profiles. **And neither lane is an STT cost in the first place.** Kintsugi DAM is an *audio-classification* model — `audio-classification`, `base_model: openai/whisper-small.en` — which uses Whisper as an **encoder/feature extractor, not a transcriber**. It emits ordinal severity heads and never produces text, so it consumes no STT minutes and no per-stream vendor billing; its only marginal cost is GPU time on hardware already provisioned. Inworld's voice profiling likewise runs as a **parallel model on an existing STT stream**, not a separate transcription job — so whether `affect` costs a second stream is purely a routing question, and since Inworld now covers Turkish natively for both STT and profiling, the two-vendor configuration may be avoidable without touching the open-SER question at all. Latency was never an objection: the lanes are off the critical path by design, with an invariant that tests it. | — (see §2.3) |
| ~~`s2s_cloud` → P3~~ — ⚠ **WITHDRAWN outright, 27 Aug 2026, not deferred** | Two independent reasons, either sufficient. **(1)** Every model it named is cloud-only, and all models are now self-hosted (`00 §0b`) — there is no S2S profile to defer. **(2)** It was already the wrong shape: it cannot meet the contract ADR-009/010 says every profile shares — no clip cache, no verbatim scripted text, and PolicyGuard degrades to *after-the-fact* retraction, meaning **the patient already heard the diagnostic sentence**. It is faster **and** less safe, presented as an upgrade. The durable form of this withdrawal is a **closed profile registry plus a grep gate** (INT-098), not a paragraph. ⚠ Note also that the async-tool-calling argument that once justified it was **profile-local, not architectural**: `submit_utterance` returning a `work_id` is trivially non-blocking on an ordinary text LLM. | 3 wk |
| **Heavy security tier → P1** | Defer Wazuh (12 GB + a part-time SRE), Harbor + Kyverno + cosign admission (there is no cluster in P0), CrowdSec, the service mesh, MobSF. **Keep every invariant** — they are enforced by tests, and the tests are what P0 ships. | ~4 wk |

> ⚠ **`residency_tr` was one P2/P3 item. It is two items with completely different risk, and the cheap half was being held hostage by the expensive half.**
>
> - **`residency_tr_media`** — SFU + TURN + API + Postgres in İstanbul. **Ship in P1.** A latency win, a genuine KVKK strengthening, no GPU required. One honest caveat travels with it: **physical residency ≠ legal residency** — the Local Zone's control plane is in Frankfurt and the operator is **AWS EMEA SARL**, so whether it satisfies KVKK Art. 9 is a question for counsel (`06 §1`). The narrow **testable** claim is that the patient's audio bytes never leave Türkiye on the media path.
> - **`residency_tr_models`** — vLLM + TTS + observer lanes in Türkiye. **Gate on a signed capacity contract naming the provider and the GPU SKUs. Do not publish a `residency_tr` availability date before that contract exists.** Re-evaluate when the Google Türkiye region opens.

**And record the supply constraint plainly: GPU supply in Türkiye is thin.**

| option | what is actually available |
|---|---|
| **AWS İstanbul Local Zone** (`eu-central-1-ist-1a`, GA May 2026) | **C7i / M7i / R7i only — no G / P / Inf family.** Perfect for the media tier, useless for the model tier |
| **Azure** | **no Türkiye region** |
| **Google Cloud Türkiye** | announced 20 Nov 2025 with Turkcell — **no opening date and no published accelerator plan** |
| **Huawei Cloud Türkiye** | live (İstanbul + Ankara DR), but its accelerators are **Ascend, not CUDA** — the vLLM stack of `03 §4.9.1` does not port |
| **Türk Telekom GPUaaS** | sold, with **no published model, capacity or price** |
| İstanbul resellers | advertise H100 / H200 / A100 but publish **no capacity commitment** — **UNVERIFIED** |

And the macro constraint settles it: **Türkiye's entire commercial data-centre capacity was ~120–160 MW at end-2025** — one hyperscale AI facility elsewhere draws 100+ MW on its own — with private generation above the exempt threshold needing **EMRA licensing**, and **June 2026 amendments restricting unlicensed surplus sales.** This is why `residency_tr_models` is gated on a contract rather than a date.

### 2.2 Added to P0 — safety work that was missing

- **`base.life_threat`** — a rule set evaluated on **every session regardless of booked branch**. In v1.4, cauda equina, testicular torsion, limb ischaemia, acute angle-closure, sudden vision loss, neutropenic fever, GCA and stridor lived in *cluster or specialty* packs, so each was evaluated only if the patient happened to book into that branch. **Patients do not present according to their booking** — the MHRS booking-to-visit lag is days to weeks and intake runs at T-24h. CI property test: `every_RED_rule_is_reachable_from_every_branch`.
- **`CLINICIAN_ONLY` disposition** — safeguarding needs a flag invisible to the patient *and to the proxy*. Child maltreatment, domestic violence and elder abuse appear **zero times** in v1.4's clinical content, and the product is voice-first and speaks aloud. Add a discreet exit control and text-mode-first for any section that could elicit a disclosure.
- **Three-state answers** — `asked_present | asked_absent | not_asked` (+ `unclear`, `declined`), type-enforced. A flat `negatives[]` reads to a clinician as *elicited*; this is the canonical mechanism by which generated clinical documentation causes harm, and it is directly foreseeable with an 18-turn cap and a "bunu atla" control.
- **`source:` on every red-flag rule** — `{guideline_id, version, date, url, retrieved_on}`, with a CI test that every RED rule has one. A grep of v1.4 for NICE / IDSA / USPSTF / Ottawa / BSR / ESVS identifiers returns **no hits**: the rules carry no provenance at all, and MDCG 2020-1 clinical evaluation must rest on cited, current sources.
- **Mandatory universal fields** — pregnancy status and LMP for every reproductive-age female patient (ruptured ectopic classically presents in a woman who does not know she is pregnant; and NG255 is scoped to *pregnant or recently pregnant, any age*, so sepsis routing needs it too); immunosuppression (chemo ≤ 6 weeks, biologic, steroid, transplant, asplenia); weight; vitals; time-last-known-well as a structured timestamp.
- **`tense` on every rule** — `now | today | within_7d | within_30d | ever`, each with its own `action_tr`. Real anaphylaxis is a five-minute event; nobody completes a pre-visit intake through one, so in practice that rule fires on *past* reactions and needs a different action.
- **A guideline-currency job** that diffs each cited guideline's *update-information chapter*, not its header date. NICE's header "last updated" misses real clinical changes: CG84's IV fluid bolus moved 20 → 10 ml/kg as a "minor change", and CG89 has a March 2026 text change the header does not show.

### 2.3 Observer lanes — retained, and what hardening them actually requires

The lanes stay. They are a differentiating capability and the two objections raised against them (cost, PHI egress) applied only to one implementation of one lane. Five things genuinely need fixing, none of which is a scope cut:

| # | defect | fix |
|---|---|---|
| 1 | **No diarization.** The `acoustic` lane requires a ≥ 30 s **single-speaker** window, and there is no diarizer anywhere in the design — while companion and proxy profiles are a first-class feature. A companion in the room silently contaminates the window, and the model was trained single-speaker | Specify a diarization gate on the **self-hosted** path with a confidence threshold and a defined multi-speaker behaviour. Note this interacts with a separate finding: a third party present is the **largest single moderator of disclosure** in two meta-analyses, so detecting one has value beyond the acoustic lane |
| 2 | **Transient audio exposure through crash artifacts** — *not* storage. Raw audio is never persisted: invariant 9 forbids it, `audio_retention_guard` proves there are no write paths, and §4.7 keeps the window in memory only and zeroes it after scoring. But a 30-second PCM buffer can still leak through a **core dump, a swap page, or a crash report** — and the product ships GlitchTip. **A fake-fs test cannot see a core dump** | `RLIMIT_CORE=0`, `mlock` on the lane buffer, explicit zeroization after scoring — each with an assertion rather than a convention. This is a narrower defect than "audio at rest", and it does not weaken the no-retention guarantee |
| 3 | ⚠ **Rewritten 27 Aug 2026 — the problem is not calibration.** This row used to read *"DAM is US-English at ~71 % sensitivity/specificity, so design the Turkish calibration study."* **Kintsugi DAM is dropped (D14)**: the vendor dissolved Feb 2026 after failing FDA De Novo, so Apache-2.0 would convey the weights and make us the legal manufacturer of a Class IIb function **with no design history file** — no training-data provenance, no subject demographics, no bias analyses, no verification records, and nobody left to ask. And **threshold recalibration could never have fixed it anyway**: refitting a threshold is a **monotone transform**, so AUC and the ROC curve are invariant under it. You cannot threshold your way out of a discrimination problem. | **The lane survives; the model does not.** Train an **ordinal head ourselves** on an Apache-2.0/MIT SSL encoder (`03 §4.9.1` row 19), tapping an **intermediate layer, not the final one** — four independent papers, and DAM pooled the final layer, which is Whisper's *worst* for cross-lingual transfer. **We then hold the design history file because we created it**, which converts an unanswerable regulatory question into an ordinary, expensive, tractable one. The study still has to be designed — n, labels, ethics route — but it is now a validation of our own device, not a calibration of someone else's orphan. |
| 4 | **Determinism.** Lane output depends on dropped frames and load-adaptive sampling, so the same session cannot be replayed — contradicting the "pure, replayable" claim and the reproducible-sessions goal | Lane signals become **recorded inputs**, not re-executed computations. The forward-bring of PHQ-2/GAD-2 is then a deterministic function of the recorded signal, and replay replays the signal, never the audio |
| 5 | **Compute isolation.** §4.7 says *"asyncio tasks with per-lane CPU/GPU budgets (or a separate worker pool)"* | **Make the parenthetical the requirement.** Parallel work is only free if the isolation is real — asyncio tasks sharing an event loop with the voice runtime is how "off the critical path" quietly stops being true. Specify the pool, the budgets, the backpressure policy, and a test that turn latency is unchanged under lane saturation |

**On the regulatory frame, one distinction to keep clean.** Self-hosting is decisive for **KVKK Art. 9** (no cross-border transfer at all), for **Genelge 2019/12** residency with public-hospital tenants, and for the DPIA. It is **not** an answer to medical-device classification: FDA Device Example 14 concerns the *function* — analysing a signal or pattern — regardless of where it runs, and Criterion 1 failures cannot be documented away. The answer there is **MDCG 2019-11 Rev. 1 §7 module bounding** — *"It is the obligation of the manufacturer to identify the boundaries and the interfaces of the different modules"* — so that the lanes carry their own classification without dragging the rest of the intake into MDSW scope. Two separate threads; do not let one stand in for the other.

**And the output has to be worth it.** One `affect_summary` sentence in the clinician note is a poor return on a continuously-running lane. The lanes already read the stream; what else is defensibly derivable — pacing and modality adaptation, ASR-confidence-driven confirm-by-card, engagement-driven break offers, detection of distress that should pause the interview — is a design question worth answering properly rather than a reason to switch them off.

---

## 3. Delivery model — corrected

**One issue → one PR** stays. Three things change.

1. **Front-load the human gates.** New P0 order: INT-001…004 (machinery) → **INT-043 drafted and in your inbox on day 2** → INT-044…052 cluster packs → then the platform / data / protocol chain. The agent drafts; you review. This turns *"agent works three days then stalls two weeks"* into *"you have review work from day 2."*
2. **`awaiting-human` must stop blocking dependents.** Make it a satisfiable dependency state for issues that depend only on the non-gated part, and make the loop print `WAITING_HUMAN` with the exact list rather than silently skipping.
3. **Split `make check`.** As one target it is 25–50 min cold. Decompose into `check-py` / `check-ts` / `check-golden` / `check-integration` as parallel CI jobs (keep `make check` as a local fan-out alias); run `mypy --strict` on `packages/` + `services/api` only with changed-package scoping plus a full nightly; move the docker-compose tier to its own required job. **Then < 10 min wall-clock is real.** Without this, P0's 91 issues alone are ≈ 68 hours of serial CI.

---

## 4. KPIs — corrected targets

Changes are marked ⚠. Unmarked targets carry over from v1.4.

### Speech & feel
v1.4's budget table omitted **every network term**. Recomputed — and, as of 25 Aug 2026, **measured**: 674,774 Ookla mobile tests / 338,416 devices, Türkiye 2026 Q2, plus 24 h of continuous RIPE Atlas ping from 11 Turkish anchors (`03 §4.5.1`).

| metric | v1.4 | ⚠ v2.0 | why |
|---|---|---|---|
| scripted p50 / p95 | ≤ 400 / ≤ 1200 ms | **per network profile — `02 §8.1`**; mid-LTE **≤ 450 / ≤ 680 ms** | the structural floor is **not a single number**: 376 ms p50 / 481 ms p95 with a Frankfurt SFU, 338 / 434 in-country. **Publishing one floor for a distribution this wide is the mistake** |
| dynamic p50 / p95 | ≤ 700 / ≤ 1200 ms | **per network profile — `02 §8.1`**; mid-LTE **≤ 1000 / ≤ 2100 ms** | ⚠ **the flat `p95 ≤ 2000 ms` is not achievable on Turkish mobile as architected and would fail from day one** — mid-LTE p95 arithmetic sums to **2055 ms**. `residency_tr_models` removes 141 ms p95 of vendor-hop RTT and brings it to **≈ 1914 ms** |
| `residency_tr` p50 | ≤ 900 ms | **≤ 1300 ms** (≤ 900 ms with a small Talker) | v1.4 put a 30B MoE in the Talker slot; Layer A only needs to speak ≤ 2 sentences. Note the **transport** half of this profile is a **win**, not a cost |
| RED preemption | ≤ 300 ms p99 *in production* | **≤ 300 ms p99 in production — via the data channel, not the audio path** | ⚠ **revised.** Downlink p95 is 206 ms before the clip's first sample is even scheduled, so a streamed RED script cannot hold 300 ms at p95. The script is **pre-positioned on the device** and triggered by a data-channel message (`03 §4.6` inv. 4). The old "fires continuously from day one and gets silenced" objection is answered by changing the mechanism, not the target |

**The transport lever is bigger than the VAD lever, and it is measured.** Running SFU + TURN in Türkiye is worth **−39 ms p50 / −47 ms p95** on media alone and **−156 / −188** once the models move too — more than dropping `min_silence_duration` 250 → 150 ms (**−100 ms**, and that drop is now **adaptive**: 150 ms when measured uplink jitter p95 < 30 ms, 250 ms otherwise, so we do not cut patients off in the waiting room — `03 §4.5b`). v2.0's earlier **−70 ms** estimate had the right sign and was ~1.8× overstated. This is the *opposite* of v1.4's "use EU regions, LiveKit Cloud EU" prescription — and it is free KVKK benefit, because media never leaves Türkiye.

> ⚠ **Withdrawn: "on 4G, p95 RTT runs 3–4× p50."** Measured Türkiye p95/p50 is **2.23** — *tighter* than Germany (2.42), Poland (2.43) or Spain (2.69). More generally, **"Turkish networks are bad" is false and no argument here may lean on it** (`00 §2`). Same dataset, same quarter, same method: Türkiye p50 **22 ms** against Germany 24, UK 31, Italy 32, Spain 29 — **the joint-lowest median mobile RTT of the set.** The honest statement is *"mobile radio has a 2× tail everywhere, and Türkiye's is at the better end of Europe."* The real risk is **loaded** latency, not idle latency: 646 ms p50 / 1747 p95 under downlink load, 835 / 2232 under uplink load (`03 §4.5.2`).

### Safety
⚠ **The false-RED ≤ 2 % target is deleted.** It is arithmetically incompatible with the rule set (~30 RED rules at ~0.1 % each ≈ 3 %; the Ottawa SAH criteria carry ~15 % specificity *by design*; `rf.dyspnoea_rest` alone plausibly exceeds 2 % because "speaking in short sentences" is the *baseline* for advanced COPD). Worse, a hard ceiling creates continuous pressure to weaken rules — the exact failure the monotonicity guardrails exist to prevent. The symptom-checker literature is unambiguous: apps that became less risk-averse between 2015 and 2020 ended up missing **over 40 %** of emergencies.

Replaced by three:
- **Primary metric: misses, not false positives.** Zero clinician-confirmed missed time-critical conditions, measured by **chart-linked follow-up of a sample of GREEN sessions** — not clinician self-report, which under-detects.
- **Un-bundle RED into tiers**, so a ceiling applies where it belongs: `EMERGENCY_NOW` (call 112 — target ≤ 0.5 %, tight) · `SAME_DAY_ACIL` (several % is acceptable) · `EXPEDITE`. The current binary forces every rule to either shout 112 or say nothing.
- **Per-rule false-RED rates with per-rule review.** The console's false-RED queue already exists; make it the unit of governance.

⚠ **New:** per-rule **extraction sensitivity and specificity against a Turkish clinical reference standard**. A deterministic rules engine over probabilistic inputs is not deterministic — v1.4 audits the LLM's *output* while treating its *input to the safety layer* as ground truth. Must cover agglutinative negation and evidentiality (*"ağrım yok değil hani"*, *"kanama yoktu, sadece siyahtı"*, `-mış`), second-language Turkish speakers, and a **"did not understand" state distinct from "no"**.

### Coverage & learning
⚠ **G7 softened.** From *"100 % of booked branches served by an L1+ pack"* to *"no patient ever runs on bare `base.intake`, and every patient is evaluated against the universal `base.life_threat` set."* The former is true only in a sense that will not survive contact with a cardiologist: `cluster.medical` puts ~30 branches from Kardiyoloji to Dermatoloji to Tıbbi Genetik through a single HPI.

### Operability
⚠ The self-hosting **release gate applies from P2**, when a tenant actually requires it — not from P0. Build the **registry and the gate** in P0, because that is the artefact hospital CIOs audit; stand up the stack when it is needed.

### Unchanged
Activation 45 % · fast-mode completion ≥ 80 %, median ≤ 4 min · clinician acceptance ≥ 70 % → ≥ 85 % · must-ask coverage ≥ 95 % · Turkish medical WER ≤ 10 % · CSAT ≥ 4.3, NPS ≥ 40 · note ready ≤ 60 s · SLO attainment, MTTR < 4 h, change-failure rate < 10 % · vulnerability SLAs · zero PHI in logs.

---

## 5. Regulatory & partnership track — re-planned

### P0 — starts now, not later
- **Written notified-body classification opinion.** ~€5–15k, and it determines the entire Stage B budget and timeline. Do this **before INT-217's scope is fixed**; a IIa → IIb surprise at classification review is a ~9–12 month schedule break.
- **Begin the clinical-investigation dossier.** Non-clinical validation of the triage engine (TCKAY m.5/2(a) requires it *before* submission), protocol, ICF(tr), a named PI holding uzmanlık or doktora in the field, **the qualifying university site**, and insurance.
- **Clear the instrument licences.** C-SSRS: written scope confirmation from RFMH / Kelly Posner. WHO-5: commercial permission via who.int/copyright, or drop it. HAQ-DI: clear the **Turkish translation** with Küçükdeveci's group and confirm the "unmodified" condition against our mobile layout.
- **A counsel question that is separate from Rule 11.** May device-off mode say, immediately after a symptom question, *"Bu belirtiyi bildirdiniz. Bu tür belirtilerde beklemeyin — 112'yi arayın veya en yakın acile gidin"*? That is arguably health signposting, not automated urgency classification of an individual. **If the answer is no, we must stop asking red-flag questions in device-off mode** — asking and then answering with silence is iatrogenic false reassurance, and worse than not asking at all.

### P1
VERBİS registration · DPIA v1 · Art. 9 standard contracts with 5-iş-günü Board notification · hospital DPA template · **KAEK submission**.

### P2
**TİTCK application** · external pen-test · ISO 27001 gap assessment · KTS (SBYS) registration.

### P3
e-Nabız application to SBSGM · **public-hospital** HBYS vendor partnership (Akgün / Sisoft / Probel / **Monad**) — ⚠ **Tiga removed: it is not on the Aktif HBYS Listesi at all**, it is an interoperability contractor, so three of the four former targets were right and the fourth was a category error; private groups are reached through their own technology arm instead (§1) · ISO 13485 QMS · MoH AI Approval Unit engagement.

### P4
Class **IIb** conformity assessment · clinical evaluation report per MDCG 2020-1 · ÜTS registration under TCKKD-KLVZ-03.

### ⚠ Missing from v1.4's statutory map — added
- **Sağlık Hizmetlerinde Tanıtım ve Bilgilendirme Faaliyetleri Hakkında Yönetmelik** (RG 32263, 29.07.2023; reportedly replaced 12.11.2025 — verify the new RG number)
- **Tıbbi Cihaz Satış, Reklam ve Tanıtım Yönetmeliği** (RG 29001, 15.05.2014, amended 26.05.2023)

Together these prohibit promoting uncertified device functionality and heavily restrict health-service advertising to the Turkish public — including by parties without a health-service licence, i.e. us. *"Coming soon: AI triage"*, pilot press releases and investor decks that reach the public are all exposure. **We have PolicyGuard for in-app strings and no claims-control gate for marketing.** This is the single most likely source of an early enforcement letter for a consumer health app in Türkiye.

Also added: **KVKK Özel Nitelikli Kişisel Veriler Rehberi (26.02.2025)** — the current special-category posture rests on Karar 2018/10, which predates the m.6 rewrite by six years; **KSVY amendment RG 33096, 03.12.2025**; **ETBİS registration** for the paid tier; **TCK 133 and 134** for recording consent.

---

## 6. Research tracks

1. **Turkish medical ASR benchmark** — ⚠ **upgraded from a research track to a GATE.** `00 §5` Q9: a 3–5 h Turkish **spontaneous** clinical-speech eval set with code-switched English medical terms, dosages and units. FLEURS-tr and Common Voice tr are **both read speech** and both overstate performance on the real workload; the only published Turkish WER in this project (11.17–12.34) is read speech, and the only Turkish *medical* ASR artefact in existence was trained on **3 speakers and 120 clips**. No vendor publishes Turkish per-language numbers, so this must be built. ~2 weeks, and **it unblocks the ASR, TTS and `03 §4.5` budget questions at once** (HB-C10).
2. **Turkish acoustic-biomarker validation** — ⚠ **promoted, not deferred; and rewritten 27 Aug 2026.** The `acoustic` lane is retained and **Kintsugi DAM is dropped (D14)** — this track now validates **our own ordinal head**, not a vendor's orphaned model. It remains the **gate** on the lane becoming clinician-visible: its lead time, not the engineering, determines when the lane can ship, and D4 means there is no shadow mode to ship in the meantime. Three cheap things come first, at ~€0 and before any study (`00 §5` Q11): **(a)** the **28.8 % band-instability on a prompt change alone** needs no Turkish data — pre-specify it as a limitation and fix the elicitation prompt; **(b)** ablate the text branch and re-baseline, because a **text-only BERT model beat the audio-only model** in the vendor's own paper, which may change what the study should measure at all; **(c)** score **acted-depression controls** as a free adversarial specificity set — a model that scores acted depression like real depression is doing acting-detection. ⚠ **Scale reality check: the DAM-class validation study is n ≈ 800, €120–250k, 12–18 months. The 300-session P2 pilot cannot validate this lane — it is off by ~3×.** And there is **no Turkish vocal biomarker model in existence**, open or commercial, so there is nothing to adopt and no baseline to beat.
3. **Pre-visit note usefulness (RCT-lite)** — ⚠ now gates the `considerations[]` block. An AI-generated pattern list rendered above the clinician's own reasoning is a differential diagnosis functionally, and it will anchor. Do not ship it until a prospective study shows it improves rather than degrades diagnostic accuracy.
4. **Protocol library** — clinician-authored packs; open-source the DSL and base protocols (Apache-2.0).
5. **Conversational feel study** — ⚠ **rewritten 27 Aug 2026.** `s2s_cloud` is withdrawn and `cascade_fast` no longer exists, so the comparison is **`residency_tr` vs `typed`** — which is the comparison that was always worth making, because `typed` is the kill-switch fallback and the question is what the voice path actually buys.
6. **Voice-based psychiatric signal validation** — unchanged, research-only.
7. ⚠ **NEW — Turkish clinical-extraction accuracy.** Per-rule sensitivity and specificity of slot extraction against a clinician-labelled Turkish reference standard. **Gates P1 exit**; without it the triage engine's inputs are unvalidated and the "deterministic rules engine" claim is unsupported.
8. ⚠ **NEW — network telemetry from session one.** Four transport unknowns are **UNVERIFIED** and none is obtainable from a public dataset: **Turkish mobile packet loss**, **hospital guest wifi**, the **handset mic-capture buffer distribution**, and the **NetEq concealment-versus-delay curve** (`03 §4.4a`, `§4.4b`, `§4.5.1`, `§4.5a`). All four are cheap to collect in production from `RTCStatsReport`. Re-derive the `02 §8.1` per-profile NFRs after 100 sessions.

---

## 7. Assumptions register (re-verified 25 Aug 2026)

| assumption | status | evidence |
|---|---|---|
| ~~Soniox `stt-rt-v5`~~ — ⚠ **MOOT under self-hosting.** The finding was verified; the pin is **displaced** (`00 §1`). Retained as the record of what was lost: its structured `ContextObject` medical-term biasing and its **free bundled realtime diarization**, the latter load-bearing for the acoustic lane's two-estimator gate | **verified, then displaced** | v4 aliases to v5, removed 30 Jun 2026 with auto-routing |
| ~~Soniox TTS is full-duplex Turkish~~ — ⚠ **MOOT under self-hosting** | **verified, then displaced** | the model is **`tts-rt-v2`**; `tts-rt-v1` removed 31 Aug 2026 |
| LiveKit Turn Detector v1 is audio-based with Turkish among 14 languages | **verified precisely** | `LOCAL_LANGUAGES` has exactly 14 keys incl. `"tr": 0.2550` |
| …and is available self-hosted on CPU | **FALSE** | `detector.py:59` resolves to **`v1-mini`** unless hosted; `v1` requires `cloud_opts`; **backchannel probabilities are cloud-only, so backchannels are impossible in `residency_tr`**; and using v1 streams patient audio to LiveKit Inference — **an undeclared PHI egress hop**, absent from the allow-list, the DPIA and the transfer register |
| The `livekit-agents` code snippet as written | **verified, with a migration warning** | all packages at 1.7.0 and the imports are valid — but `turn_detection`, `preemptive_generation`, `allow_interruptions`, `min/max_endpointing_delay` and `keyterms_options` are **deprecated in 1.7.0** → `turn_handling=TurnHandlingOptions(...)`, `stt_context_options=STTContextOptions(...)`. Writing P1 against the old signature buys an immediate migration |
| Open, commercially usable Turkish TTS with ~200 ms streaming | **partly false — and superseded by a better answer.** ⚠ The TTS pin is now `openbmb/VoxCPM2` (`03 §4.9.1` rows 10–11): Apache-2.0, ungated, **the only model in the survey where Turkish is *evaluated* rather than listed**, TTFT 0.14 s, official vLLM-Omni serving. Chatterbox is held as a third option only. **Both candidate TTS models ship a Turkish-hostile normaliser that must be disabled** | Chatterbox Multilingual V3 (10 Jun 2026, MIT, 23 languages incl. tr) is real, but **PyPI ships only `chatterbox-tts` 0.1.7**, and the ~200 ms figure belongs to Resemble's **paid hosted service**. The open weights publish no streaming latency. `residency_tr`'s TTS budget is an **open measurement**, not an assumption |
| Open Turkish streaming ASR with context biasing | **verified, and better than assumed** | Qwen3-ASR ships as **0.6B and 1.7B** (Apache-2.0, 28 Jan 2026, 52 languages incl. tr). The 0.6B is the CPU-budget option and was missing from v1.4 |
| Expo SDK 57 is safe to pin | **verified, with a hard caveat** | expo `latest` = 57.0.16; SDK 57 → RN 0.86.2 / React 19.2.3 exactly. **But SDK 57.0.0 still carried the Hermes V1 memory regression** — expo/expo#46519 is still open and PR #48887 states the fixed hermes versions "weren't backported… (including on 57)". **Pin `expo@57.0.9+` and the exact RN patch, gate CI on `npx expo-doctor`, keep `useHermesV1: false` as a live fallback.** A 1.1 GB-RSS app is an OOM-kill on the mid-range Android a Turkish hospital kiosk will be |
| Node ≥ 22.13 | **false** | **Node ≥ 20.19.4** |
| Device attestation is available in Expo | **effectively false** | `expo-app-integrity` was last published **2023-04-09** with peers pinned to SDK 48/49-era — **it cannot install alongside SDK 57**. `react-native-app-attest` is iOS-only. **DPoP has no Expo module at all.** Budget **4–6 engineer-weeks** for a first-party config-plugin; this work is currently invisible in the backlog |
| Certificate pinning in the Expo managed workflow | **partly true** | no first-party API; needs a config-plugin (TrustKit / OkHttp), a dev or production build, and expo-dev-client's network inspector disabled on iOS. A `fetch`-patching shim will **not** pin the WebRTC/DTLS path — i.e. most PHI traffic |
| De-identification before every cloud model call | ⚠ **the objection dissolves — there is no cloud model call** | The finding stands as an argument and is worth keeping, because it is *why* self-hosting is the right control: in a cascade the first cloud call **is the STT audio stream**, and audio cannot be Presidio-redacted, so the control could only ever have been contractual — and a contractual control is not a technical one. Self-hosting makes it structural. De-identification still applies to Loop-2 exports and any dev-path model call. Also **spaCy ships no Turkish model** (`tr_core_news_sm`/`md` both 404), so Presidio needs the `transformers` or `stanza` extra plus custom recognizers |
| < 0.1 % de-identification leak rate | **unfalsifiable as defined** | measured "on the synthetic corpus" *we author*. Realistic conversational-Turkish recall is 0.85–0.95 given oblique cases (*Ahmet'in*, *Ayşe'ye*); 3–8 identifiers per intake ⇒ **≈ 0.3–1.0 expected leaks per session**. Redefine as **recall per entity class on a held-out, human-labelled, real-transcript corpus** with a published confusion matrix: TCKN ≥ 0.99 (checksum-verifiable), names and addresses ~0.90, stated honestly |
| MinIO is a safe root of trust for a 10-year WORM audit log | **at risk** | newest Docker Hub tag is **RELEASE.2025-09-07** (~12 months stale), and the named fallback **Garage does not implement S3 Object Lock** — silently voiding the WORM guarantee |
| MedGemma is open-weights and self-hostable in Türkiye | **licence-false — and now a deleted pin, not merely a risk** | **every** MedGemma model, 1.5-4B included, is **Health AI Developer Foundations** licensed — none is Apache-2.0. This conflicts with the CI Apache/MIT/BSD allow-list, which has no verdict for HAI-DEF |
| MedGemma 27B "1.5" exists | **false** (unchanged) | 1.5 is 4B only |
| Open-weights S2S with Turkish speech **output** | **not yet** (unchanged) | Qwen3-Omni is Turkish speech-**in** only; Qwen3.5-Omni is API-only |
| ~~OpenAI Realtime is EU-residency eligible for `s2s_cloud`~~ — ⚠ **MOOT: `s2s_cloud` is withdrawn** | **partly** | `/v1/realtime` is an eligible EEA+CH endpoint, **but tracing for `/v1/realtime` is not EU-residency compliant**, and residency requires ZDR / Modified Abuse Monitoring approval. Also **GPT-Realtime-2 is superseded by GPT-Realtime-2.1 (6 Jul 2026)** |
| ~~Vertex Live API residency controls are contractable~~ — ⚠ **MOOT: `s2s_cloud` is withdrawn** | **unverified** | 70 languages and affective dialog are confirmed; the residency terms are not. Confirm with Google before `s2s_cloud` leaves the flag |
| **Rule 11 → Class IIa** | **FALSE — the most consequential correction in the bundle** | **IIb for both device functions.** MDCG 2019-11 Annex IV states the depression-scoring case is IIb almost verbatim; IMDRF N12 defines "drive clinical management" as including *triage*; and the failure mode to assess is the **false negative**, which is the Class III limb |
| KAEK and TİTCK can run in parallel | **false** | TCKAY m.8/2 — the ethics decision is submitted **as part of** the TİTCK application |
| The Acıbadem pilot hospital can host the investigation | **false as stated** | TCKAY m.5/6 restricts sites to **university** research centres or MoH training & research hospitals. Name the qualifying university centre |
| TCKAY covers "observational" studies | **terminology false** | TCKAY has no *gözlemsel* category; only **retrospective** studies are out of scope (m.2/2), and the post-market route (m.10) is defined **only for CE-marked devices** — unavailable to us |
| C-SSRS is free with Columbia permission | **false** | **Clario holds an exclusive electronic licence.** Training is not the issue; the electronic sublicence is |
| WHO-5 is free to use | **false since 2024** | **CC BY-NC-SA 3.0 IGO — NonCommercial**, plus copyleft ShareAlike |
| PHQ-9 / GAD-7 are Turkish-validated | **weaker than assumed** | the PHQ-9 Turkish evidence is a **reliability study only** (n=96, no sensitivity/specificity, no validated cut-off, journal not PubMed-indexed). **PHQ-2 and GAD-2 have no Turkish validation at all** — do not describe them as "Turkish-validated". GAD-7's Turkish cut-off is **8**, not 10 |
| NICE NG51 is the sepsis reference | **replaced 19 Nov 2025** | by **NG253 / NG254 / NG255**. Each only *partially* replaces NG51 — and **NG255 covers pregnant or recently pregnant people of any age, carved out of both others**, so the engine must route on `{age_band, pregnancy_status}`. All three have updates in progress (PCT, PEWS, MEWS) |
| Surviving Sepsis Campaign 2021 is the reference | **superseded 23 Mar 2026** | **SSC 2026** (Crit Care Med 2026;54(4):725–812 / Intensive Care Med 2026;52(5):863–936). The qSOFA position did **not** reverse — it was re-expressed positively: *"we recommend using NEWS, NEW2, MEWS, or SIRS **over** qSOFA as a single tool to screen for sepsis"* (strong, moderate certainty). New Statement 5 directly supports our disjunctive rewrite: *"Sepsis is a clinical diagnosis and should not be ruled in or ruled out using a single biomarker or diagnostic test"* |
| ACC/AHA 2017 hypertension is the reference | **superseded 14 Aug 2025** | **2025 AHA/ACC multisociety HBP guideline** — and **"hypertensive urgency" is a retired term**, replaced by **"severe hypertension"** (>180/120 *without* acute target organ damage). **Class 1, LOE B-R: treat it in the OUTPATIENT setting.** Any rule routing asymptomatic BP >180/120 to Acil now contradicts a Class 1 recommendation. Note ≥ 4 published corrections exist — cite the corrected version |
| IDSA 2010 is the febrile-neutropenia reference | **archived** | idsociety.org shows an explicit ARCHIVED banner. The only CURRENT IDSA-branded product is ASCO/IDSA 2018, whose scope is *outpatient low-risk only* and does **not** replace the inpatient content. **Cite NICE CG151 instead** — it is current, and NG253 actively defers to it |
| GIRFT cauda equina pathway (Feb 2023) | **nine revisions stale** | current version is **March 2026**. GIRFT keeps the "February 2023" title date and *appends* update dates, so a "Feb 2023" citation looks superficially plausible — **exactly the trap the guideline-currency job must catch** |
| EAU acute scrotum, "operate within 6 hours" | **misattribution** | current edition is **2026**. EAU's actual strong recommendation is *"urgent surgical exploration in all cases… as soon as possible"*; the 4–6 h window is **descriptive pathophysiology**, not a recommended target |
| USPSTF recommendations are current guidance | **true, but qualify the date** | all three (depression B, suicide risk **I — insufficient evidence**, anxiety B/I) stand as at **20 Jun 2023**. But USPSTF is mid-overhaul: meetings cancelled Jul 2025, Nov 2025 and Mar 2026; **both co-chairs dismissed 11 May 2026**; ~a dozen drafts stalled. Use a dated "as at" qualifier, never open-ended "current USPSTF guidance" |
| WHO opioid-overdose guidance is stable | **replacement imminent** | selected recommendations updated **2 Apr 2026**; the full guideline is expected late 2026 / early 2027. Do not build fixed content assuming the 2014 text persists |
| Ottawa SAH reduces unnecessary imaging | **false** | 2025 meta-analysis (Acad Emerg Med 32(10):1111–1121): pooled sensitivity 99 % (92–100), **specificity 23 % (16–32)** — and **neither Ottawa nor the Emerald rule meaningfully reduces CT utilisation** (pooled OR 1.15, 95 % CI 0.62–2.13). The rule is designed to be non-specific; budget for that in the false-RED tiering rather than treating it as a defect |
| NICE NG126 as cited (2019) | **stale** | **updated 17 Jun 2026** with a substantive anti-D immunoglobulin reversal |
| NICE NG59 covers cauda equina | **false** | NG59's Context chapter explicitly excludes CES. The authority is the **GIRFT national CES pathway (Feb 2023)**. NG59 was also **updated 29 Jul 2026**, withdrawing its psychological-therapy recommendations |
| NICE "Early Value Assessment (EVA)" | **renamed** | now **early-use HealthTech guidance** under **PMG48** (14 Jul 2025, updated 17 Dec 2025). ECD7 remains current but frozen since Aug 2022 and is *not* referenced by PMG48 — "we meet NICE ESF" and "we are ready for NICE HealthTech evaluation" are now two separate claims |
| MHRS ≈ 79 branches | **verified, attribution corrected** | Minister Memişoğlu via Anadolu Ajansı, **26 Nov 2025**. The "Feb 2025" attribution has no traceable source |
| e-Nabız 28k facilities / 240k physicians | **unsourced — removed** | no Ministry or e-Nabız primary source found. Do not use in investor or tender material |
| Epic "Smarter Check-In" arrives 2027 | **verified — the strategic thesis holds** | this is the load-bearing competitive claim and it stands |
| Epic Cosmos Curiosity is GA | **false** | launches **March 2027** |
| Langfuse is self-hostable with an MIT core | **verified** | acquired by ClickHouse 16 Jan 2026; still open source and self-hostable |
| OpenBao, Coraza, CrowdSec, Wazuh, Falco, Kyverno, Harbor, Sigstore, Presidio are self-hostable OSS | **verified** | OpenBao MPL-2.0 v2.6.2 (18 Aug 2026). **Presidio still needs Turkish recognizers built and measured** |
| Turkish mobile networks are a latency problem for this product | **FALSE — withdraw any argument leaning on it** | Türkiye mobile RTT p50 **22 ms** vs Germany 24, UK 31, Italy 32, Spain 29 — joint-lowest median of the set, with a **tighter** tail (p95/p50 = 2.23) than Germany, Poland or Spain. 674,774 Ookla tests / 338,416 devices, 2026 Q2 |
| GPU capacity is procurable in Türkiye when `residency_tr_models` is needed | **thin — gate on a contract, not a date. ⚠ But the *scale* framing was wrong: this is a 1-to-8-GPU problem, not a 120–160 MW problem** — cache-aware streaming ASR does 240 realtime streams per H100 where buffered Parakeet 1.1B manages 14, a 17× difference that collapses what would otherwise dominate. **Buy one card and build the pilot**; the contract gate applies only to the 50-concurrent tier. Two of our own numbers here are also corrected: Turkish DC capacity is **~250 MW, not 120–160**, and **KSVY does *not* mandate in-country hosting** | No hyperscaler GPU in-country: AWS İstanbul Local Zone is C7i/M7i/R7i only, Azure has no TR region, Google Cloud TR has no date and no accelerator plan, Huawei is Ascend-not-CUDA, Türk Telekom GPUaaS publishes nothing. Reseller H100/H200/A100 claims are **UNVERIFIED**. National commercial DC capacity **~120–160 MW at end-2025**, with EMRA licensing above the exempt generation threshold and June 2026 amendments restricting unlicensed surplus sales |
| Turkish mobile packet-loss rate | **UNVERIFIED — no public dataset carries it** | Opensignal is paywalled (403). 3GPP targets ≤ 1 % residual BLER so steady state is normally < 0.5 %, but **the losses that matter are handover bursts, which are guaranteed rather than probabilistic.** Instrument from session one; re-derive after 100 sessions |
| Hospital guest wifi is a usable media path | **UNVERIFIED — and probably the wrong default** | Turkish mobile p50 is 20 ms in İstanbul, 19 ms in Ankara, better than most enterprise guest wifi anywhere. `03 §4.4b` **prefers cellular inside a hospital**. Probe the pilot site before P2 |
| P0 fits in 3 weeks | **false** | 91 issues ÷ 15 working days = 6/day, each with a recorded red run, a green run, three gate suites, an evidence file and a PR — before counting ≈ 68 hours of serial CI. **12–20 weeks.** |

---

## 8. Cross-reference note — where this plan defers (files not owned by this one)

Added 27 Aug 2026, because four of the corrections above were caused by the same failure: **a fact restated in two places drifts, and the copy nobody is looking at is the one that gets used.**

- **`00_STATE.md` is the authority.** Where this roadmap disagrees with it, `00` wins and the line here is a defect to fix — not a difference of emphasis.
- **`03 §4.9.1` is the single source of truth for the model stack.** Nothing in this file pins a model. Where a phase, KPI or assumption row used to name one, it now points at a row number, and **a model that is not in that table is not pinned** whatever a deploy guide says.
- **`HUMAN_BLOCKERS.md`** carries every non-technical blocker with its owner and what it holds up. Phase gates reference it by `HB-*` id rather than restating the ask, so there is exactly one place the owner has to look.
- **`07 §3.3` (DoD) and `07 §3.4` (TDD)** are the per-issue working method; **§1a above is the phase-scale equivalent**. They are deliberately different documents: the per-issue DoD is what CI can check, and the phase gate is mostly what it cannot.
- **`10 §9.1`** catalogues invariants 12–49 (1–11 are in `03 §4.6`). ⚠ **See `10 §9.2` — 50–65 are RESERVED and enforce nothing; only 53 has a written specification and it is prose, not a test. A citation to any other number in that range is a build-review finding.** Invariants 50–65 are proposed for the data-import path and are not yet catalogued**, while `03 §4.9.6` and `§10` already cite **invariant 53** as though it exists. Cataloguing that range is a prerequisite for the P1 records-ingestion work, and it is not currently an issue in the backlog.
