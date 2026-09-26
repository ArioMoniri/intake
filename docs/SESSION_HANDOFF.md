# Önvizit — Session Handoff (updated 2026-09-26, evening)

> For the NEXT agent/session. Read `CLAUDE.md`, `files/00_STATE.md` and `files/HUMAN_BLOCKERS.md` first; they win over this doc.
> The production audit is `docs/audit/2026-09-26-production-audit.md`. The owner's decisions are recorded in `docs/evidence/verification/owner-decisions-2026-09-26.md`.

## TL;DR
- **The API is live** at https://3-211-2-143.sslip.io with production-strict config.
  - Host: a dedicated g6.2xlarge `i-0e489e48739f5de98`, us-east-1c.
  - Evidence: `docs/evidence/INT-352.md` (smoke passed; k6 50 VUs at 0 % failures, p95 8.7 ms).
  - **Synthetic data only.** Real patients need an in-country host or counsel's cross-border decision (HB-I5, HB-L11).
- **Quotas:** GPU quota requests are open (us-east-1 → 16, eu-central-1 → 8). Move the host to Frankfurt when eu-central-1 is approved.
- **Question sets:** 8 cluster candidates and 91 specialty candidates sit in `packages/protocols/review/`.
  - The chain validates with 0 findings. It is never served: a loader guard enforces that.
  - The owner signs all of them at the end (HB-C1).
  - The pipeline is research → verifier → solver → `scripts/dev/gen_specialty_packs.py`.
- **TestFlight build source:** branch `int-354-build-source`, which is int-demo + main + INT-344.
  - It carries the App Attest entitlement and binds the EAS `production` environment.
  - That environment sets `EXPO_PUBLIC_API_BASE_URL=https://3-211-2-143.sslip.io`.
  - Build it once #551 is merged and deployed.
  - It carries demo-scoped server code (F06), so it **never targets main**.

## Merged to main today
#545, #520, #548, #561, #522, #554, #546, #553, #567, #549, #569, #517, #521.

## Open PRs
| PR | issue | state |
|---|---|---|
| #551 | INT-344 App Attest | in merge queue |
| #566 | INT-355 bare-gate resolution (every gated question was never asked) | in queue; owner approved the protocol change |
| #564 | INT-349 sensitive slot categories (encrypt + fail-closed register) | in queue; owner approved; counsel values are INT-356 (#568) |
| #563 | INT-353 review queue (99 candidates) + generator + verification trail | in queue; owner approved |
| #570 | INT-331 reduce-motion store | in queue |
| #572 | INT-341 press-opacity tokens | in queue (add/add on `motion.spec.ts` with #570: keep one header, append) |
| #573 | INT-352 part 1: staging passes App Attest and SMS config | `Refs #558`; hold until #551 and the Twilio adapter are both on main |
| #571 | INT-332 ADR-033 Motion system v1 | **Proposed**, awaiting owner ratification (Q1–Q5) |
| #514 | metric catalogue follow-up | conflicts; low priority |
| #481, #185 | older | untouched |

## Blocked on the owner
- **INT-350:** the one-line `.github/workflows/ci.yml` step (`make edge-plugin` before `make check-integration`). The permission prompt was denied. The change is uncommitted in branch `int-350-ci-part-2`. `check-integration` is red on every PR until it lands.
- **Twilio:** the SID, token and FROM number, plus a DPA for sending real phone numbers through us-east-1.
- **App Attest Team ID:** the value is `APPLE_TEAM_ID`, already in `~/.intake-secrets.env`. Put it on the host only after #551 and the Twilio adapter are on main (see #573).
- **Counsel:** the `docs/legal/data-categories.yaml` values (INT-356).
- **Clinical decisions:**
  - the dental airway posture;
  - mental-health Q17/Q18 (persecutory belief, risk to others);
  - duration wording where no source exists;
  - the two a11y register findings and the `dialogue.openInvite` removal (INT-354).
- **Store:** the `FOREGROUND_SERVICE` store-label row (Android).
- **Owner:** ratify ADR-033 (#571).
- **Final physician sign-off** on every candidate pack.

## Next agent work
- **Motion:** INT-335 (after #570), then INT-339.
- **INT-354:** land int-demo commits on main as one-issue PRs; strip the F06 demo code.
- **INT-352:** stamp `sbom_digest` in `/version` (F18); move the host to Frankfurt after quota approval.
- **INT-351:** admin ops console (in progress).
- **Question-set §F sibling rebinds:** the slot-id collisions listed in `docs/evidence/verification/cluster-wave-*.md`.

## Rules learned today
- Spawn code agents with `isolation: "worktree"`. Never call `EnterWorktree` while agents are editing.
- **Relayed approvals don't count.** The permission classifier ignores an owner decision relayed through an agent. Ask the owner directly and cite the record.
- **Stale CI after a merge.** After `main` moves, a PR shows `mergeable UNKNOWN` and CI may run on a stale merge ref. Wait until it reports `MERGEABLE`, then close and reopen the PR.
- **GitHub API DNS.** `api.github.com` DNS can fail from the laptop while `git` still works. Push and retry `gh` later.
