# Runbook — daily audit-chain verification (INT-016; alert added by the INT-021 close-out)

`AuditChainVerificationFailed` (`infra/observability/security-rules.yaml`) links the
heading below. files/08 §5 pages on "audit-chain verification failure", and the
INT-016 job (`python -m intake_platform.audit_verifier`, `make audit-verify`) has always
set `sec_audit_chain_ok` to 0 when it cannot verify the chain. Until the INT-021
close-out, no rule read that gauge.

## What runs where

| entry point | what it does | where it runs |
|---|---|---|
| `make audit-verify ANCHOR=<64-hex>` (`python -m intake_platform.audit_verifier --anchor-head …`) | reads the chain with a read-only role, checks it against the head that was published outside the `platform_admin` blast radius, and sets `sec_audit_chain_ok` to 1 or 0. With `WORM=1` it then copies a verified bundle into the object-locked bucket | the scheduler, once a day (files/10 §3) |
| `AuditChainVerificationFailed` | pages while `sec_audit_chain_ok == 0` | the Prometheus that evaluates `infra/observability/` rules |

The gauge lives in the process that ran the verification. This is the same export gap
`docs/runbooks/key-rotation.md` records for the rotation countdown. Until the
verification runs inside a process Prometheus scrapes, the page has no series to fire
on, and `observability/slo_coverage.yaml` records that as a gap.

The job prints only counts, `seq` positions and hashes. It never prints an actor, a
resource reference or a timestamp from a row, and neither does this runbook's
procedure (invariant 6).

## Verification failed

The gauge is 0 for one of two reasons. The exit code of the last run tells them apart,
and so does a re-run:

```sh
make audit-verify ANCHOR=<the head published for the last full hour>
echo $?   # 0 intact · 2 chain broken · 3 no anchor · 4 invocation unusable
```

**Exit 3: no anchor, or an anchor that is not 64 lowercase hex.** The chain may be
perfectly intact. Nothing independent says so, so the run refuses to report it intact.
No publisher for the anchored head exists yet. Where the head is published is the
owner's open decision (files/HUMAN_BLOCKERS.md HB-I12, `docs/backlog/blockers.md`
INT-016). While HB-I12 is open, every scheduled run lands here and the page is
standing:

- Do not "fix" it by passing the chain's own tail as the anchor. That is the verifier
  that always passes, and the reason the job refuses.
- Silence it only with the owner's name, HB-I12 and an end date. The silence ends when
  the anchor destination is decided and a run verifies against it.

**Exit 2: the chain does not hold.** The run names the first bad `seq` and the reason
(hash mismatch, a `seq` gap, or a tail that does not reach the anchored head). Treat it
as a P1 security incident from this moment, not as a data-quality ticket:

1. Follow `docs/security/incident-runbook.md` from its *First 15 minutes* section. The
   audit chain is the evidence, so its *Evidence preservation* section applies before
   anything else is touched.
2. Do not repair, re-hash or re-write any row, and do not re-run with `WORM=1`. The job
   already refuses to archive a broken chain, because the object lock would keep the
   attacker's version for ten years.
3. Compare the store against the last bundle that was verified and archived to the
   WORM bucket, and against the published anchors for the hours in between. The first
   bad `seq` and the last good anchor bound the window.
4. The *Notification pointers* section of the incident runbook decides whether the
   KVKK Board 72-hour clock has started (files/10 §7).

**Exit 4: the invocation or the environment is unusable.** For example,
`INTAKE_DATABASE_URL` is unset or the anchor file cannot be read. This is not a
verification result. Fix the scheduler's environment and re-run. A gauge left at 0 by
an earlier run keeps paging until a run succeeds.

## After the page clears

A run that exits 0 sets the gauge to 1, and the page resolves on the next evaluation.
Record the first bad `seq`, the outcome and the run's exit code in the incident notes.
Never record a row's content there.
