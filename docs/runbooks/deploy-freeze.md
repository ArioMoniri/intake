# Runbook — deploy freeze and the release gate (INT-187)

Alert: `admin.deploy_freeze_changes_total` (any `applied` or `refused`
outcome), and any refusal of `infra/staging/deploy.sh` by the release gate.

The CI/CD & releases module (`/cicd` in the console, `GET /admin/cicd`) shows
recent GitHub Actions runs per workflow with their failing jobs, the required
gates on `main` and on the open PRs, the releases and their signing state, this
deployment's `/version`, Argo CD and a deploy canary (both **not deployed** —
there is no Argo CD in `infra/`), the error budget, and the deploy freeze.

## Where the freeze lives

One record per deployment in that deployment's own Redis, under
`intake:release-freeze:v1`, written only by `services/api/admin` and read by
the release gate. The API is pointed at it by `INTAKE_RELEASE_FREEZE_REDIS_URL`
(staging and the production host: `infra/staging/compose.yaml` sets it from the
generated Redis password).

- A deployment that never froze has **no** record, and that reads as not
  frozen: the normal state.
- A record the gate cannot read — the variable unset or not a `redis://` URL,
  Redis unreachable, a record that is not the model — **refuses the deploy**.
  A deploy path that cannot see the freeze does not get to assume there is
  none.
- The freeze is **not** an Unleash flag (files/08 §3, invariant 34): Unleash
  tokens flip flags with no audit row and CI runners hold them, so a freeze
  kept there could be lifted by the pipeline it holds.

## Where it is enforced

`infra/staging/deploy.sh` — the only deploy path this repository has — runs
`require_release_not_frozen` after it builds the image and stamps its SBOM,
and **before** the first `compose up`. That runs

```bash
compose run --rm --no-deps -T api python -m intake_api.admin.release_gate
```

in a one-off container of the new image on the project network. Exit 0 lets
the deploy continue; exit 3 stops it with the gate's own lines; any other exit
means the gate did not run, and the deploy stops too. Argo CD would be the
second enforcement point; it is not deployed, and the console lists it as such.

The gate refuses on any of:

| code | meaning |
|---|---|
| `deploy_freeze_engaged` | someone froze deploys in the console |
| `error_budget_exhausted` | an SLO in `docs/slo/*.yaml` has spent its whole budget over its window |
| `error_budget_unreadable` | a Prometheus is declared (`INTAKE_OPS_PROMETHEUS_URL`) but it, or the SLO files, cannot answer |
| `release_freeze_unconfigured` / `_misconfigured` / `_unreachable` / `_malformed` | the freeze record cannot be read |

and notes, without refusing:

- `error_budget_not_configured` — this tier declares no Prometheus, so the
  error-budget freeze is not evaluated here. Staging runs this way today.
- `error_budget_unmeasured` — some SLOs have no series yet. They are not
  counted as within budget; they are simply not measured.

## Freezing deploys (the safe direction — one key)

`admin.cicd.freeze.engage`, tier 1. Any single `sre_oncall`, `clinical_lead`
or `platform_owner` may do it alone, with a reason class and a real explanation
(≥ 12 characters). There is no second approver: a second key at 03:00 on the
safe direction is an availability control on a safety control (files/08 §0c
F17). Freezing a frozen deployment changes nothing and says so.

## Lifting a freeze (two keys)

`admin.cicd.freeze.lift`, tier 2. A `platform_owner` or `platform_admin`
requests; a **different human** — `platform_owner` or `qms_owner`, on a
different account, WebAuthn credential and session, with a fresh single-use
assertion — approves within 15 minutes. Nothing changes at request time.

- A self-approval is refused and meters
  `admin.four_eyes_self_approval_attempt_total` — treat it as an intrusion
  signal.
- An approval is refused (`release_freeze_changed`) if the freeze moved after
  the request — for example it was lifted and engaged again for a new
  incident. Re-request against the current state.
- A lift does not clear an exhausted error budget. While any SLO is over its
  budget the gate keeps refusing, whatever the freeze says; the budget recovers
  as its window moves past the bad period (`docs/runbooks/slo-burn.md`).

## When deploy.sh refuses

1. Read the gate's lines: every refusal is listed with its code.
2. `deploy_freeze_engaged`: find the freeze in the console (who, when, the
   reason class; the free text is on the audit chain). If the reason has
   passed, open a lift request and have a second person approve it. Do not
   work around the gate on the host.
3. `error_budget_exhausted`: the release waits for the budget. Ship only the
   fix for the burning SLO, through a lift *and* a budget that has recovered.
4. `release_freeze_*` or `error_budget_unreadable`: fix the source (Redis up,
   `INTAKE_RELEASE_FREEZE_REDIS_URL` set, Prometheus reachable), then re-run.

Every tile on the page fails closed to unknown on its own source, and the page
shows ids, roles and codes only — never patient content (invariant 6).
