# Önvizit — Session Handoff (updated 2026-09-26)

> For the NEXT agent/session. Read `CLAUDE.md`, `files/00_STATE.md`, `files/HUMAN_BLOCKERS.md` first — they win over this doc.
> The full production audit is `docs/audit/2026-09-26-production-audit.md` (12 P0 / 14 P1 / 8 P2, ordered action plan with DoD).

## TL;DR
- App **Önvizit** is on TestFlight (ASC app 6814005465, bundle `com.ariomoniri.intakemobile`). A store build cannot log in yet. It needs:
  - a public API (#549 + an AWS deploy);
  - the release API base (#546, EAS env `EXPO_PUBLIC_API_BASE_URL`);
  - App Attest (#551, env `INTAKE_APP_ATTEST_TEAM_ID`);
  - Twilio credentials.
- Specialty question packs live in the **review queue** `packages/protocols/review/specialty/` (52 candidates). They are never served until the physician of record signs (HB-C1). The owner has said he will sign them all at the end. The served tree `packages/protocols/specialty/` stays byte-identical to `protocols generate-l0` output (L0 guard).
- CI runs again. Billing was fixed on 2026-09-26. Main is red on pre-existing failures that #520 and #548 fix, apart from the MinIO image (INT-347, owner decision).

## Open PRs (merge order; the classifier forbids the assistant from merging: the owner merges)
| # | PR | issue | note |
|---|---|---|---|
| 1 | #545 | backlog rows INT-324..348 | merge first: the sec_row gate of every PR below reads these rows |
| 2 | #520 | INT-324 audio guard | makes `make safety` green |
| 3 | #548 | INT-346 main CI green | ruff, vitest GHSA, fixtures, i18n; MinIO left to INT-347 |
| 4 | #521 | INT-325 non-dev envs refuse dev flags / file-dev KEK / default creds / fake SMS | readyz dev check only in dev |
| 5 | #522 | INT-326 George route: auth + catalogue-only + rate limit, absent in prod | mobile follow-up INT-343 |
| 6 | #546 | INT-328 release API base (https only, no LAN probing) | owner sets `EXPO_PUBLIC_API_BASE_URL` |
| 7 | #551 | INT-344 App Attest server + iOS client | Android is INT-348 (HB-A3) |
| 8 | #549 | INT-345 staging artefact (compose, OpenBao server mode, Caddy TLS) | depends on INT-347 (MinIO) |

## Specialty packs: the loop (repeat until every branch has a verified candidate)
1. **Research agent** writes `docs/evidence/proposals/<slug>.md`, in the format documented in `scripts/dev/gen_specialty_packs.py`:
   - questions go in the section whose heading contains "Candidate";
   - each item is `**Q<n>`, then `> "…"`, then an optional `gen:` line;
   - one question per item, no digits, a valid Q1.
2. **Verifier agent** writes `docs/evidence/verification/<wave>.md`, with a replacement text and a `gen:` line for every item it flags.
3. **Solver agent** applies that verification to the proposals.
4. **Coordinator** runs `uv run python scripts/dev/gen_specialty_packs.py <slugs…>`, then `uv run pytest -q tests/protocols`, then commits.

- **Done and verified:** waves 1–5 plus the surgery wave.
- **In flight:**
  - The internal/mental wave is at the solver stage.
  - The oncology, women's health/newborn and paediatrics/genetics waves are at the verifier stage.
  - Geriatric/sleep/neurophysiology, dental, occupational/special and public-health/admin are at the research stage.
- **Hand-authored candidates:** kardiyoloji, gastroenteroloji and noroloji (the generator never overwrites these).
- **Held items (need an owner decision under invariant 18, new data categories):**
  - forensic safety (adli_tip Q3–Q5);
  - genital symptoms (deri Q8);
  - non-alcohol substance use (ruh Q12, klinik psikoloji Q11);
  - household basic needs (sosyal pediatri);
  - relatives' family history (tıbbi genetik);
  - partner data (infertility Q12);
  - employer/exposure details.

## Human decisions outstanding
- **AWS deploy:** add the permission rules `Bash(aws ec2:*)`, `Bash(aws ssm:*)`, `Bash(aws s3:*)` and `Bash(aws s3api:*)`, or run `docs/runbooks/staging.md` (on #549). us-east-1 is **synthetic patients only** (HB-I5).
- **INT-347:** replace the withdrawn `minio/minio` image. The options are the `pgsty/minio` fork, a source build, or SeaweedFS.
- **Twilio:** SID, auth token and FROM, with the Turkey geo-permission, in `~/.intake-secrets.env`. Plus the DPA and cross-border decision (INT-329).
- **App Attest:** set `INTAKE_APP_ATTEST_TEAM_ID` and add the App Attest entitlement. Android needs HB-A3.
- **Copy owner:** the 4 kiosk/shares register findings recorded in #548.
- **TTD/TRD permission:** the göğüs and romatoloji wording has been rewritten into our own words.
- **Rotate** `EXPO_TOKEN` and the ElevenLabs key (both were pasted in chat).
- **Physician-of-record sign-off:** needed for every review candidate (HB-C1). The repo currently names Dr Efe Onganer; the owner intends to sign.

## Hard gates — do NOT cross
- **Triage acuity** follows EK-4 law plus the physician of record. Never fabricate a trigger, level or citation. RED stays in `base.life_threat` (invariant 7).
- **No PHI to ElevenLabs.** Only catalogue `text_tr` is sent (#522). Patient STT stays on-prem.
- **Nothing on the laptop:** no local Docker; containers run only on the AWS host.
- **Worktrees:** spawn code agents with `isolation: "worktree"`. Never call `EnterWorktree` while agents are editing, because it re-pins every agent.
