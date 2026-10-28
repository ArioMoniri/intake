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
| `OtpSmsDeliveryFailing` (page) | `infra/observability/security-rules.yaml` | over half the last 30 minutes' `otp_sms_delivery_total` not `accepted`, and at least 3, for 5 minutes |

The caps are the owner's, D37 in files/00_STATE.md (28 Oct 2026): 1000 a day globally, 120 an
hour globally and 120 an hour per tenant, a breach stopping every send until the owner looks.
They sit well above the pilot's planned volume; the daily one is the spend ceiling.

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
4. Release it. The command appends `sms.spend.kill_switch.released` to the hash-chained audit
   log first and releases the switch only when the row is written; if the audit store is down
   it prints that the release could not be audited, exits 1 and the switch stays engaged. Fix
   the audit store (Postgres), then run it again:

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

## OTP SMS is not being delivered

Since INT-579 the code is sent after the request's `202`, so the route says nothing when the
vendor refuses it or cannot be reached: the patient is told the code was sent and none arrives.
The signal is `otp_sms_delivery_total{vendor,outcome}`; every outcome other than `accepted` is a
code that did not leave. `OtpSmsDeliveryFailing` pages when over half the last 30 minutes' sends
were not accepted and at least 3 were refused, held for 5 minutes, so one number Netgsm will not
reach never pages on its own.

1. Split it: `sum by (outcome) (increase(otp_sms_delivery_total[1h]))`. One outcome dominating
   names the cause.
2. `credentials_refused`, `sender_refused`, `otp_package_missing`: the Netgsm account. The
   credentials in OpenBao (`secret/api/netgsm`), the approved sender name and the OTP package
   are the owner's to check in the Netgsm panel; nothing in the API changes it.
3. `egress_denied`, `timeout`, `unreachable`, `vendor_unavailable`: the path to Netgsm. Check the
   SMS proxy and the egress allow-list row, then Netgsm's own status.
4. `send_limit_exceeded`: the account's own sending limit, not ours. Our caps (D37) sit below
   the account's or this would not appear; raise it with the owner.
5. `unparseable_response`, `accepted_without_job_id`, `unknown_vendor_code`: Netgsm's answer
   changed shape. These are never retried, because the code may have gone out. The owner
   captures the new shape with `infra/staging/netgsm_test_otp.sh --shape`, which sends one real
   SMS to the owner's own number and prints only the answer's structure; the parser is then
   updated in a reviewed change.
6. `number_refused`: numbers Netgsm will not reach. A steady small share is expected and is the
   budget's reason to exist; a sudden rise across many numbers is worth a ticket to Netgsm.

Each failure is also on the hash chain as `auth.otp.delivery_failed`, by request id and with no
number, so a patient's report ("no code came") can be matched to a cause by the time and id.
