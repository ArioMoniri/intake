# Runbook — model benchmark trigger (`admin.models.benchmark.run`)

**Alert:** `admin.model_benchmark_requested_total{outcome="planned"}` rising
outside a change window, or any sustained rate at all.
**Surface:** `POST /admin/models/{component}/benchmark`, the *Models &
self-hosting registry* module (files/08 §148, §8).
**Tier:** 2 — two keys for execution. Actor roles `platform_owner`,
`platform_admin`, `sre_oncall`; approvers `platform_owner`, `qms_owner`,
`compliance_officer`.

## What the trigger does today

It **plans and does not execute.** The route resolves which component, which
probe, which `budget_ms` and — critically — the *named basis* any resulting
measurement would carry, then returns that plan with `state: "planned"` and
`executes: false`. Nothing is dialled, no capacity is spent, no number is
produced.

That is the delivered state, not a gap:

- The **quality lane always refuses** with `no_named_corpus`. There is no
  Turkish clinical evaluation corpus (`files/HUMAN_BLOCKERS.md` **HB-C10**;
  **HB-A13** for the records side). A quality figure over an unnamed set is
  exactly the accuracy claim CLAUDE.md invariant 20 exists to prevent, so the
  lane refuses rather than measuring something it cannot name.
- The **latency lane plans** and stops there. No benchmark runner exists in
  this repository; the tier-2 ceremony this action registers is what will
  guard one when it does.

## If this alerts

1. **Confirm the actor.** `admin.model_benchmark_requested_total` carries the
   staff subject. Cross-check the hash-chained audit entry for
   `admin.models.benchmark` — the route is audited whether it succeeds or
   refuses, so a refused burst is visible too.
2. **A burst of `outcome="refused"` with `kind="quality"`** is somebody
   discovering HB-C10 the hard way. Nothing is wrong with the system. Point
   them at this file.
3. **A burst of `outcome="planned"`** is a read loop, not a resource
   incident, because planning executes nothing. Treat it as an access
   question, not a capacity one.
4. **When a runner exists**, this section grows the capacity half: a benchmark
   against a PHI-path model host competes with live sessions, which is why the
   action is tier 2 and why it must never run during a clinic window.

## What must be true before the quality lane is opened

A human names a corpus: an id, a description, the date it was obtained, and
its licence. `intake_probes.console.BENCHMARK_CORPORA` is empty until then and
a plausible entry there would be an invented value (invariant 17).

## Related

- `observability/registry.yaml` — the registry the module renders.
- `docs/adr/ADR-015-admin-console-catalogue-gate.md` — why the registry is the
  release gate's surface.
- `docs/adr/ADR-022-no-accuracy-claims.md` — why a measurement carries a
  corpus and a date, and why a claim never appears at all.
