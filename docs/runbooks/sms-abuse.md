# Runbook — SMS pumping and the spend kill switch (INT-577)

> The owner's order of 28 Oct 2026: *"have all security measures to stop sms hijacking, sms
> loading, hacking, overuse and data hijacking over sms"*. INT-577 is the overuse half: what one
> request, one caller and the whole platform may cost in SMS.

## What runs where

| control | where | what it does |
|---|---|---|
| per-number, per-device, per-IP budgets | `intake_api.auth_store` | 3 codes a number, 3 a device (the App Attest key it proved), 10 an address (a keyed hash), in any rolling hour |
| exponential resend backoff | `intake_api.auth_store.resend_wait` | after a number's first code its next waits 60 s, after the second 120 s; the 202 says how long |
| tenant hour budget, global hour cap | `intake_api.sms_spend` | 120 codes a tenant and 120 in all, in any rolling hour; a refusal is a 429 and rolls on |
| global day cap and the kill switch | `intake_api.sms_spend` | 1000 codes in any rolling day; reaching it **latches** the spend kill switch |
| the kill switch | Redis `auth:otp:kill` | while engaged, every OTP request answers `503 otp_delivery_unavailable` and nothing is sent; an unreadable switch counts as engaged |
| `SmsSpendKillSwitchEngaged` (page) | `infra/observability/security-rules.yaml` | `max(sms_spend_kill_switch_engaged) == 1` |
| `OtpRequestSpike` (ticket) | the same file | the last hour's requests over 3 × the day's hourly rate and over 20 |
| the ops console's `sms` tile | `GET /admin/ops` | the same spike test, the switch, the last hour and day |

The caps are engineering defaults sized well above the pilot's planned volume; the daily one is
the spend ceiling, and it is the owner's number to set (docs/evidence/INT-577.md).

## The kill switch is engaged

1. Read why, on the host (it prints the reason and the instant, never a number):

   ```sh
   docker compose -p intake-staging exec -T api python -m intake_api.sms_spend status
   ```

   `reason=day_cap` means the platform reached its day cap; `reason=manual` means an operator
   engaged it; `reason=unreadable_state` means the stored switch did not parse, which counts as
   engaged.
2. Look at what spent the cap before releasing anything: the ops console's `sms` tile and
   `sec_otp_abuse_blocks{dimension}` (which budgets were refusing), the Netgsm account's own
   usage report, and `otp_sms_delivery_total{outcome}`.
3. If the spend was an attack, leave the switch engaged until the source is blocked (the edge, the
   WAF, or a tightened budget in a reviewed change). Patients cannot sign in by SMS code meanwhile;
   existing sessions are unaffected.
4. Release it, which appends `sms.spend.kill_switch.released` to the hash-chained audit log:

   ```sh
   docker compose -p intake-staging exec -T api python -m intake_api.sms_spend release
   ```

   Rolling the day window over does not release it, by design.

To stop all SMS at once for any other reason, `... python -m intake_api.sms_spend engage`
(one operator; it only ever makes the system safer).

## An OTP request spike

The last hour holds more than 3 × the day's hourly rate of OTP requests, and more than 20.
Pumping spreads its requests over many numbers, devices and addresses so that each stays inside
its own budget; the global caps are what bound it.

1. `sec_otp_abuse_blocks{dimension}` says which budgets are refusing; `sec_otp_requests_total`
   by `outcome` says how much was admitted.
2. If the admitted share is climbing toward the day cap, engage the kill switch now rather than
   waiting for the cap to trip it.
3. A spike of `phone_invalid` is a caller probing number ranges; it costs no SMS.
