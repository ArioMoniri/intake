# Runbook — cost budget alerts (INT-190; runbook links added by the INT-021 close-out)

Every alert in `infra/observability/cost-rules.yaml` links one of the five headings
below. The file is generated from `infra/costs/unit-prices.yaml` and the metrics
catalogue by `intake_platform.cost.cost_rule_groups`, and
`tests/observability/test_cost_rules.py` fails on drift. So a change here is a change to
the price file, followed by a re-emit:

```sh
uv run python scripts/observability/cost_rules.py --emit infra/observability/cost-rules.yaml
uv run python scripts/dev/record_cost_fixture.py
```

Every cost alert is severity `ticket`. A budget overrun costs money, not patient
safety, so it files work and never pages. Each alert carries `budget_id`, `scope` (a
vendor id or `all_vendors`) and `period` (`day` is a rolling 1 d, `month` a rolling
30 d). The admin console's `GET /admin/cost` composite shows the same budgets and their
verdicts.

## Budget not configured

`CostBudgetNotConfigured` has the expression `vector(1)`. It fires for every budget
whose `limit.usd` in `infra/costs/unit-prices.yaml` is empty, and it keeps firing until
someone sets the limit. That is deliberate. A missing alert would read as "within
budget", and a missing limit is not the same thing as an unlimited budget.

- Nothing in the running system is wrong. The spend in `scope` over `period` is simply
  not being watched.
- The fix is the owner's, not an engineer's. The limit, its `source` (a contract,
  invoice or quote reference) and its `as_of` date go into the price file together
  (files/HUMAN_BLOCKERS.md HB-O8 (b); `docs/backlog/blockers.md` INT-190). No agent
  writes a number there, and a plausible invented limit is worse than an empty one.
- Once the limit is set and the rules are re-emitted, this alert disappears for that
  `budget_id`. `CostBudgetExceeded` takes its place, together with
  `CostBudgetIncomplete` if any in-scope component still cannot be counted.

## Budget exceeded

`CostBudgetExceeded` fires when the spend over the budget's window is above
`limit.usd`. The spend is a lower bound: it is the sum of `(usage or vector(0)) * price`
over every in-scope component that has both a price and a live usage series. A lower
bound above the limit is therefore a real overrun, never an artefact of missing data.

1. Open the cost module (`GET /admin/cost`) for the same window. It breaks the spend
   down per component, vendor and profile, and names the component that moved.
2. Check whether usage or price changed. A price edit shows up in the price file's
   history (`source`, `as_of`). A usage step usually matches a deploy, a load test left
   running, or a traffic change.
3. If one voice vendor's spend drives it, the tenant-level kill switch
   (`docs/runbooks/voice-kill-switch.md`) moves sessions to `typed` without a deploy.
   Doing so is a product decision with a patient-facing effect, so the owner makes it,
   not the on-call.
4. Raising the limit is an owner edit of the price file with a new `source` and
   `as_of`. It is never an edit of `cost-rules.yaml`, which the drift test would
   reject anyway.

## Budget incomplete

`CostBudgetIncomplete` has the expression `vector(1)`. Its `missing` annotation lists
the in-scope components the lower bound cannot see, each with a reason:

- `price not configured`: the owner has not supplied the rate (HB-O8 (b)).
- `usage not metered`: no catalogued series meters the component. The fix is an
  emitter plus a catalogue entry, which is engineering work, and the component's
  `usage_note` in the price file says why none exists yet.
- `usage series <name> not emitted yet`: the component is metered by a series the
  catalogue still lists as `planned`.

While this alert is open, a quiet `CostBudgetExceeded` means "the counted part is under
the limit", not "the budget holds". Close each listed reason at its source. The alert
clears for that `budget_id` when nothing in scope is left uncounted.

## Spend cap warning

`ModelSpendCapWarning` fires when `max(model_spend_month_usd)` reaches the cap's
`warn_ratio` (80 % of the 80 USD monthly cap, i.e. 64 USD) and is still below the cap
(INT-439; 00_STATE §3 D19). The series is the voice runtime's month-to-date total of
model spend in the UTC calendar month, counted by
`intake_voice_runtime.metering.spend.MonthlySpendLedger`.

- Read the admin console's cost module: the `spend_caps` row shows the month's spend,
  the warning point and the limit.
- Nothing is refused yet. Elective work (council verifier members, hosted lanes) keeps
  running until the cap itself is reached.
- If the month will overrun, the owner decides: raise `spend_caps[].limit.usd` in
  `infra/costs/unit-prices.yaml` with a new `source` and `as_of`, or let the cap refuse
  elective work for the rest of the month. An engineer does not raise it.

## Spend cap reached

`ModelSpendCapReached` fires when `max(model_spend_month_usd)` reaches the cap's
`limit.usd`. From that moment every **elective** model call is refused at admission
(`AdmissionReason.MONTHLY_CAP_REACHED`) until the UTC month ends. **Obligatory** work —
the first extraction of an answer the patient has just given — is never refused; it is
still counted, so the spend can pass the limit by that amount.

- Confirm the refusals in `model_spend_cap_events_total{event="refused_cap_reached"}`.
- A refusal with `refused_store_unavailable` instead means the shared spend store could
  not be read. Elective work fails closed until it can be; restore the store.
- Only the owner raises the cap, as above.
