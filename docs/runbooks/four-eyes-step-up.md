# Runbook — the four-eyes step-up (INT-563, ADR-043)

Alert: `admin.step_up_total` — any run of `step_up_token_refused`,
`step_up_replayed` or `four_eyes_self_approval` outcomes, and any
`step_up_unconfigured` on a deployment that should approve.

Every second key in the console — voice release, profile and canary, the
deploy-freeze lift, the three model-lane widenings, break-glass and the access
review's countersignature — is presented through one step-up: a fresh WebAuthn
re-authentication at Keycloak, proven to the API by the ID token, spent once
on the one pending action it was opened for. files/08 §2.3: *"Step-up is a
fresh, single-use WebAuthn assertion at the moment of the action."*

## What the approver does

1. Open the module page (`/voice`, `/cicd` or `/model-lanes`) and read the
   pending action's row. The brief is `GET /admin/<module>/pending/{action_id}`
   (`/admin/break-glass/{action_id}` for break-glass).
2. Press **Onayla**. The console asks the API to open a step-up for that action
   and sends the browser to Keycloak, which asks for the password and the
   passkey again — even inside a live session (`prompt=login`, `max_age=0`).
3. Keycloak returns to `/step-up/callback`. The console hands the code to the
   API, receives a one-time grant, and presents it on the action's approve
   route. The page comes back with the outcome: `approved`, or a refusal code.

A break-glass approval or an access-review countersignature has no button on a
module page. Open `/step-up?action_id=<id>` on the console: it shows the
action id and the same **Onayla** button, and runs the same sequence.

The grant cannot be typed, copied or reused: it is bound to the approver's
Keycloak subject and session and to the one action, lives two minutes, and is
spent by the first approval that presents it. An approval body that still
carries the old `assertion_id` is refused (`422`).

## Refusal codes

| code | meaning | what to do |
|---|---|---|
| `four_eyes_self_approval` | the requester tried to approve their own action (another tab counts) | a different person approves; two in a row from one account is an incident |
| `four_eyes_approver_role` | this role is no second key for this action | an approver role listed in the brief approves |
| `four_eyes_expired`, `four_eyes_already_decided` | the action is no longer pending | open a new request |
| `step_up_unknown` | no live ceremony or grant for this caller (expired, spent, another person's) | press Onayla again |
| `step_up_not_fresh` | Keycloak's `auth_time` predates the ceremony: a remembered login, not a new one | press Onayla again; if it repeats, check Keycloak honours `prompt=login` |
| `step_up_without_webauthn` | the re-authentication carried no `hwk` | the staff flow's WebAuthn step is not REQUIRED: run `staff_flow check` (below) |
| `step_up_token_refused` | the ID token did not verify or names another account, session or ceremony | treat a run of these as an attack; check the JWKS mirror after a key rotation |
| `step_up_replayed` | that ID token was already spent | an attack signal: nobody replays a token by accident |
| `step_up_exchange_failed` | Keycloak would not redeem the code, or could not be reached | check Keycloak health and the client (below) |
| `step_up_unconfigured` | the API has no step-up wired, so nothing can be approved | set the two variables below and restart the api |

## Configuration

The API reads two variables beside the console's OIDC settings
(`infra/staging/compose.yaml`):

- `INTAKE_ADMIN_STEP_UP_REDIRECT_URI` — the console's `/step-up/callback`, an
  exact redirect URI of the realm's `admin-web-stepup` client.
- `INTAKE_ADMIN_STEP_UP_EXCHANGE_URL` — the realm's token endpoint on the internal
  network (`http://keycloak:8080/realms/intake/protocol/openid-connect/token`).

Both or neither. Neither leaves every approval answering `503`; one without the
other, or plain http to a public host, leaves it unconfigured with a warning.
The ID token is verified against the same mirrored key set as the console's
bearer (`/run/intake/keycloak-jwks.json`), so a key rotation needs the
deploy's `mirror_keycloak_jwks` before step-ups pass again.

## The Keycloak client

Keycloak imports a realm once, so the committed `admin-web-stepup` client
reaches a live realm through `infra/staging/keycloak/step_up_client.py`, run by
`deploy.sh` (`ensure_step_up_client`) after the staff flow is checked and
re-checked read-only by `smoke.sh`. It adds the client when it is absent and
fails when a live client differs from the committed one — a per-client flow
override, a role scope or an extra default scope included; it never touches a
flow. `staff_flow check` also holds the realm's browser flow and the steps
around the second factor. To check by hand:

```bash
cd infra/staging && source lib.sh && step_up_client check
```

A refusal names the field that differs. Fix the live client in the Keycloak
admin console to match `intake-realm.json`, or delete it and let the next
deploy add it.

## What it proves, and what it does not

- `auth_time` no older than the ceremony proves a new interactive login.
- `amr` containing `hwk` proves the WebAuthn step completed in this Keycloak
  session within its eight-hour reference age — not that it ran *now*. What
  makes the new login include it is the staff flow: WebAuthn is REQUIRED, and
  `staff_flow check` holds that on every deploy and smoke.
- `credential_id` and `aaguid` name the key; the approver block carries them,
  so four-eyes' "different credential" compares the key used for the approval.
  The audit chain names the action and a hash of the token id, never the
  credential.
