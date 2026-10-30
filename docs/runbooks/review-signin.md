# Runbook — the App Store review sign-in (INT-488)

> Owner decision **D39** (files/00_STATE.md §3, 30 Oct 2026, "B Y"): App Review signs in to a
> release build with one reserved reviewer number and one fixed code. The number never sends an
> SMS. The code is generated on the host and lives only in OpenBao. It works only on the synthetic
> host's synthetic tenant, only while the review window is open, and it lands a synthetic reviewer
> patient. Every use is audited and alerts. **No agent types the code into Apple's service: the
> owner pastes it.**

## What runs where

| part | where | what it does |
|---|---|---|
| the reviewer account | OpenBao `secret/api/review_signin` | `{"number", "code", "revealed"}`, written by `--generate` from the host's CSPRNG, one version kept. The API's token may read it and nothing more (`infra/staging/openbao/intake-api-policy.hcl`) |
| what the API holds | `intake_api.review_signin` | the number's pseudonym and the code's HMAC under the OTP pepper, read once at start; never the values. An OpenBao that cannot answer at start logs a warning and sets `review_signin_document_unreadable` to 1 |
| the gate, at start | `review_gate` | `INTAKE_ENV=staging`, the image's baked `INTAKE_DEPLOYMENT_DATA_CLASS=synthetic`, `INTAKE_API_TRIAGE_TENANT_KIND=synthetic` (the tenant's real-patient flag) and `INTAKE_API_TRIAGE_DEPLOYMENT` set. Anything else refuses the reviewer and names the fact that failed |
| the guards, on every step | `intake_api.review_window.ReviewGuards` | the model-lane control's bound data class is not `real_phi` (ADR-035; unreadable reads `real_phi`), and the reviewer tenant's kill switch is engaged, so no hosted model lane carries what the reviewer types |
| the reviewer's record and notice | `docs/legal/store/review/` | [`review-signin.yaml`](../legal/store/review/review-signin.yaml), the processing record, and [`app-review-signin-notes.en.md`](../legal/store/review/app-review-signin-notes.en.md), the review notes with the reviewer's notice, hash-bound by the record's `notice_sha256` (`intake_api.review_record`) |
| the review window | Redis `auth:review:window` | default OFF. An unreadable, garbled, non-finite or future-dated window reads closed. Each opening has a fresh id: its own reviewer patient, and sessions bound to it. It closes itself 14 days after `--on` (below) |
| the sign-in | `intake_api.review_flow` | INT-578's code record, attempt budget and lockout, with no SMS. Fifteen counted misses on one code close the window by themselves |
| the erasure | `intake_api.review_reset` | the DSAR erasure (`intake_api.dsar.shred`) of every reviewer subject left in the reviewer tenant: the reviewer is a real person, and nothing they enter outlives their review. Only the owner's command and the API's own sweep run it, never a reviewer's request |
| the sweep | the API, once a minute | records a close whose audit row was lost, closes a window whose 14 days ran out, and retries an erasure still pending while no window is open |
| `ReviewSignInUsed` (ticket) | `infra/observability/security-rules.yaml` | any use of the reviewer number |
| `ReviewSignInRefused` (page) | the same file | any refusal of it |
| `ReviewResetFailing` (page) | the same file | an unattended erasure failed in the last 10 minutes |

The reviewer number is reserved wherever the document can be read: a request for it never reaches
Netgsm, whatever the window says. A request on a closed window, or one the gate or a guard refuses,
gets the answer any request gets, and nothing is minted. The verify is refused. With the window open
and no usable code in OpenBao, both answer `503 review_signin_unconfigured`.

## Before the first review

Three things must be true before `--on` opens a window. It refuses, and names what is missing,
until they are.

1. **Hosted lanes off for the reviewer tenant.** The synthetic host may route model lanes to hosted
   providers (ADR-035), as synthetic, non-personal traffic. The App Review reviewer is a real
   person, so their tenant must not use them. Once, in the admin console's **Voice controls**,
   engage the kill switch for the reviewer tenant `c64d3008-bc6c-564d-a9fe-9a46e88807c6`
   (`REVIEW_TENANT_ID`, a fixed UUIDv5; `--on` names it when it refuses). The kill switch also
   keeps that tenant on the typed profile. Every reviewer step refuses while the switch is off or
   unreadable.
2. **An erasure role that can erase.** Which database role erases is the open decision INT-394
   (#650). Until it is answered, the erasure runs as the app role, and INT-395's preflight finds
   the grants it lacks. It then refuses, typed, and appends one `auth.review.reset_blocked` row
   per missing grant, and `--on` refuses naming INT-394. No reviewer data is collected before it
   can be erased. Once INT-394 is answered, either grant the app role what the decision says, or
   put the decided role's URL in `INTAKE_API_ERASURE_DB_URL` (`ApiSettings.erasure_db_url`).
   Nothing else changes.
3. **A complete processing record.**
   [`docs/legal/store/review/review-signin.yaml`](../legal/store/review/review-signin.yaml) needs
   every field set, and `notice_sha256` must be the notes file's sha256. Today `transfer_route` is
   counsel's (INT-528's open questions, HB-L11), and `reviewed_by` and `reviewed_on` belong to
   the lawyer who signs the record. `--on` names those fields.

## The window closes itself after 14 days

A review window stays open for **14 days** after `--on`, then closes itself. This is an
**engineering default**, set fail closed so that a window nobody remembers to close still ends. It
is long enough for an App Review round and a resubmission. It is not a D39 value and not a
clinical one. The owner may change it: it is `REVIEW_WINDOW_S` in
`services/api/src/intake_api/review_window.py`, and changing it is a reviewed diff.

- **From the instant the 14 days are up, the window reads closed** to every reviewer step and
  session, before anything else happens.
- **The API then closes it the way `--off` does.** First it removes the window document. Then it
  appends `auth.review.window.closed` with the actor `system:review-expiry`. This happens on the
  next reviewer step or within a minute through the sweep. The erasure follows on the sweep, never
  on a reviewer's request. Its rows also name `system:review-expiry`.
- **Nothing reopens it.** The next review needs a fresh `--on`, ideally after a `--generate`.
  An `--on` that finds an expired window still stored closes it the way `--off` does first.
- `--status` shows when the window closes itself and how long is left.

## The owner's script

`infra/staging/review_signin.sh` runs as root on the synthetic host, through an interactive SSM
session, one mode per run and no other argument. Nothing secret is ever on its command line, and
it turns tracing off (`set +x`) before anything runs:

```sh
aws ssm start-session --region us-east-1 --target i-0e489e48739f5de98 --document-name AWS-StartInteractiveCommand --parameters 'command=["sudo /opt/intake/infra/staging/review_signin.sh --status"]'
```

| mode | what it does | prints |
|---|---|---|
| `--generate` | Re-applies the API's OpenBao policy. Appends `auth.review.code.rotated` first, so no code goes live without its row. Keeps one version of the document, so no old code lingers. Keeps a well-formed reviewer number, or draws one. Draws a fresh 6-digit code. Writes all three fields to `bao kv put` on stdin, with a check-and-set against the version it read. Then restarts the API, which reads the document at start, and waits for it. A new code voids the old one, and the reveal is unused again | nothing |
| `--on` | Opens the review window, inside the API container (`python -m intake_api.review_cli on`). It refuses unless all of the following hold: the gate and the guards admit this deployment; OpenBao holds a well-formed number and code; and the processing record is complete and bound to the notice. It erases anything a reviewer left in the reviewer tenant, and refuses to open if it cannot (INT-394, above). Then it appends `auth.review.window.opened`, and opens only if that row was written | the window's state |
| `--off` | Closes the window first, because that is the safer state. Then it appends `auth.review.window.closed` and erases the reviewer tenant. Every reviewer session ends. If the row fails, the close is remembered and the sweep records it once the audit store answers. If the erasure fails, the sweep retries it. Either failure is reported, and the command exits 1; the window stays closed | the window's state |
| `--status` | Reads the window | the window's state; while it is open, when it closes itself and how long is left (`13d 23h 0m`) |
| `--reveal-to-owner` | Shows the reviewer number and the code **once**, on the owner's terminal and nowhere else. It refuses unless stdin and stdout are a terminal. It also refuses if the notes file is not the bytes the record's `notice_sha256` names; that check runs before the reveal is used up. Before anything is printed, it records the reveal in OpenBao, with a check-and-set, and appends `auth.review.code.revealed`. If either fails, nothing is printed. Then it prints the number, the code and the notes file byte for byte. A second reveal is refused until `--generate` makes a new code. After you press Enter, it clears the screen and the scrollback | the number, the code and the review notes, once |

**Before `--reveal-to-owner`, check that Session Manager does not log sessions.** If the account's
Session Manager preferences send session output to S3 or CloudWatch Logs, the reveal lands there.
Turn session logging off, or skip the reveal. Never pipe or redirect the script's output.

**Who ran it.** Every row the script causes names `operator:host`. The person is the IAM principal
of the SSM session, so find it in CloudTrail's `StartSession` event at the row's time.

## A review, from start to finish

1. Deploy a tree that carries INT-488 (`./deploy.sh`). The deploy re-applies the policy with the
   `secret/api/review_signin` read grant.
2. Make the three things in "Before the first review" true.
3. `--generate`. It prints nothing, and the API restarts.
4. `--on`.
5. `--reveal-to-owner`. In App Store Connect, open the build's **App Review Information** and tick
   **Sign-in required**. Paste the number as the user name and the code as the password. Paste the
   review notes the reveal prints, exactly: they are
   [`docs/legal/store/review/app-review-signin-notes.en.md`](../legal/store/review/app-review-signin-notes.en.md),
   the sign-in steps and the reviewer's notice. Then press Enter, and the screen clears.
6. Submit. Each sign-in is a `ReviewSignInUsed` ticket and an `auth.review.signed_in` row. If
   the review runs past 14 days, the window closes itself; run `--on` again.
7. When the review ends, `--off`, then `--generate`. The first erases what the reviewer entered
   and ends their sessions; the second voids the code still sitting in App Store Connect.

The number and the code never go into this repository, an issue, a PR, a chat or a store config
file. If the code is lost before it is pasted, run `--generate` again. It keeps the number, so the
user name in App Store Connect stays the same. Then reveal the new code. Only App Store Connect
users with access to the app can see the demo credentials; keep that role list short.

To change the review notes or the notice, edit the notes file and the record's `notice_sha256`
together, through the legal lane. The reveal refuses notes the record does not pin.

## The review sign-in was used

`ReviewSignInUsed`: someone used the reserved reviewer number in the last 5 minutes.

1. Is a review window open on purpose? `--status`. If it is open, this is App Review at work.
2. Find each use on the hash chain: `auth.review.requested`, `auth.review.signed_in`,
   `auth.review.refused` and `auth.review.verify_refused`. The number appears only as its
   8-character log ref.
3. If no review is under way, close the window (`--off`) and continue with the next section.

## The review sign-in refused a use

`ReviewSignInRefused`: a use of the reviewer number was refused. The `outcome` label of
`sec_review_signin_total` says why:

| outcome | meaning | do |
|---|---|---|
| `window_closed` | the number was tried with the window off, or after its 14 days ran out | If the review is still under way, run `--on` again. If no review is due, someone outside App Review holds the number. Run `--generate` to rotate the code and keep the window off. The number itself stays reserved |
| `not_synthetic` | the deployment is not the synthetic host's synthetic tenant, or its model-lane control is bound `real_phi` or unreadable | Expected nowhere. The API's start log names the failed fact (`environment`, `data_class`, `tenant_kind`, `deployment`). Never "fix" this by changing a flag on a host that may hold real patients |
| `hosted_lanes_open` | the reviewer tenant's kill switch is off or unreadable | Engage it in the console (above) |
| `unconfigured` | the window is open, but the API holds no usable code | Run `--generate`, which restarts the API, then reveal and re-paste |
| `invalid`, `unbound`, `missing`, `exhausted`, `locked` | a wrong, stray, spent or expired code, or the INT-578 lockout (five misses lock the number for an hour) | One or two during a review are typing mistakes. A run of them is guessing. At fifteen misses on one code, the window closes itself (`auth.review.window.closed` by `system:review-guard`), and the sweep erases the reviewer tenant. Rotate with `--generate` and look at the source on the chain before opening again |
| `code_retired` | the code reached the miss cap; reopening the window does not revive it | Run `--generate`, then `--on`, reveal and re-paste |
| `withheld`, `limited` | the number's budget (3 codes an hour, with resend backoff) or the caller's | Wait for the window to roll, as for any number |

## The reviewer erasure is failing

`ReviewResetFailing`: the sweep's erasure of the reviewer tenant failed in the last 10 minutes. A
reviewer subject is unerased, no window is open, and the sweep retries every minute.

- The first failure of an episode appends `auth.review.reset_failed` (`system:review-expiry`).
  `review_reset_failures_total` counts every failed attempt.
- `auth.review.reset_blocked` rows name the grants the erasure role lacks. That is INT-394 (#650):
  answer it, then grant the role or set `INTAKE_API_ERASURE_DB_URL`.
- Any other cause is in the API's log, by type only: the object store, or the database.
- The page clears once a sweep erases the tenant. Keep `--on` shut until then, which it is
  anyway.

## What this does not do

- It does not create the reviewer's demo content. Each window's reviewer patient starts with no
  visits and no consents, like any new account.
- Google Play's reviewer access is out of scope, because Play is deferred (INT-496).
