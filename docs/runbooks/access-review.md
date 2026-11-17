# Runbook — quarterly access review, offboarding and the 60-day auto-disable (INT-366)

> files/08 §2.7: *"The review is produced by the console from Keycloak, the role
> grants and the audit log, not assembled by hand into a spreadsheet […] a review
> older than 100 days downgrades every `platform_owner` and `tenant_admin`
> session to read-only and pages."*
> files/08 §2.4: *"An SCIM/HR-triggered disable revokes OIDC sessions and OpenBao
> leases and the Grafana / Langfuse / Unleash accounts in one action […] 60-day
> auto-disable on no login."*

## What runs where

| entry point | what it does | who |
|---|---|---|
| `GET /admin/access/review` | generates the review from the Keycloak admin API and the audit chain: every staff account, its effective realm roles, enabled flag, last login, last console action, and each section's last countersignature | `compliance_officer`, `qms_owner`, `auditor`, `platform_owner`; a `tenant_clinical_responsible` sees only their tenant's clinician section |
| `POST /admin/access/review/sign` → `POST /admin/access/review/sign/{action_id}/countersign` | the tier-2 ceremony: the section's reviewer signs its digest, a second person countersigns; the countersignature writes `admin.access_review.signed` onto the chain | signer per section (below); countersigner `compliance_officer` or `qms_owner` |
| `POST /admin/access/offboard` | the one-action offboarding (tier 1): Keycloak account disabled, its sessions ended, the OpenBao identity disabled and its tokens (and so their leases) revoked, every other console account listed | `sre_oncall`, `compliance_officer`, `platform_owner` |
| `POST /admin/access/offboard/{offboarding_id}/confirm` | closes one manual step of an offboarding, audited | same three roles |
| `make access-hygiene` (`python -m intake_platform.access_hygiene`) | the 60-day auto-disable: offboards every staff account with no login for 60 days, through the same pipeline, audited as `svc:access-hygiene` | the scheduler, once a day |
| `AccessReviewOverdue`, `OffboardingIncomplete` (`infra/observability/security-rules.yaml`) | page when the review is past 100 days; ticket when an offboarding ends with a system still open | Prometheus |

## The review

### Sections and who signs them

| section | holders | signs | countersigns |
|---|---|---|---|
| `platform_owner` | every `platform_owner` | `compliance_officer` | `compliance_officer` or `qms_owner` from **another organisation** — §2.7's "external signature" |
| `console_roles` | every other console-role holder | `compliance_officer` | `compliance_officer` or `qms_owner`, a second person |
| `clinicians:<tenant>` | the tenant's clinician accounts | that tenant's `tenant_clinical_responsible` | `compliance_officer` or `qms_owner` |
| `clinicians:unscoped` | clinician accounts with no tenant attribute (should be none) | `compliance_officer` | as above |

1. Open `/admin/access/review`. For each section, read the holders, their
   roles, last login and last console action. Anyone who should no longer hold
   access: offboard them (below) or remove the role in Keycloak, then reload —
   the section's `review_digest` changes with every grant or removal.
2. Sign: `POST /admin/access/review/sign` with `{"section": …, "review_digest":
   …}` exactly as the page shows it. A digest that no longer matches the
   population is refused (`access_review_changed`): reload and read again.
3. The second person countersigns within 24 hours:
   `POST /admin/access/review/sign/{action_id}/countersign` with a fresh
   WebAuthn `assertion_id`. It is refused if the population changed since the
   signature, if it is the signer, or — for `platform_owner` — if the
   countersigner is in the signer's organisation.
4. Record the KEP/e-imza signature of the review document where the owner keeps
   signed reviews. That record is organisational and outside the console
   (docs/legal/special-category-measures.yaml, gap `access-review-performed`).

The console review is the `platform_owner` and `console_roles` sections. Its
age is the older of their two countersignatures; `admin_access_review_age_days`
reports it. Clinician sections show their own age on the page.

### Read-only past 100 days

When the console review is older than 100 days — or was never countersigned —
every write reached only through `platform_owner` or `tenant_admin` answers 403
`access_review_overdue`, audited like any refusal. Reads still work, and every
other role still writes, so the reviewers can always redo the review: sign and
countersign both console sections and the writes come back at once, on every
replica (the state is read from the audit chain on each write).

### Overdue

`AccessReviewOverdue` pages when `admin_access_review_age_days` is above 100
on every replica. `+Inf` means no review was ever countersigned, or the API has
not read the chain since it started. Run the review above. If the API cannot
read the chain, the audit writer is the incident, not the review.

## Offboarding

`POST /admin/access/offboard` with `{"subject": "<Keycloak user id>",
"reason_class": "departure" | "role_change" | "access_review" |
"security_incident"}`. The steps run in this order, each audited before and
after (`admin.offboarding.<system>.intent`, then `.revoked` or `.failed`):

1. `keycloak_account` — the account is disabled: no new login, no refresh of an
   offline token;
2. `keycloak_sessions` — every session is ended;
3. `openbao_leases` — the OpenBao entity whose alias is the Keycloak user id is
   disabled and every token it holds is revoked, which revokes their leases;
4. every system in `infra/admin/console-accounts.yaml`: listed as
   `manual_pending`.

The person's pending four-eyes requests expire in the same call (§2.4).
A failed step is reported `failed` and the rest still run; send the same
request again once the cause is fixed — a new offboarding id, the same
subject, and disabling a disabled account is harmless.

The offboarding is `complete` only when every automatic step is `revoked` and
every manual step is confirmed. Confirm each manual step after doing it:
`POST /admin/access/offboard/{offboarding_id}/confirm` with `{"system": …}`.
Open offboardings are listed under `pending_offboardings` in the review.

### Grafana

files/08 §0b F1 keeps Grafana out of browser reach, so staff should hold no
Grafana account. In Grafana's server admin (Administration → Users and access
→ Users), find a user whose login is the person's Keycloak username. If there
is one, disable it and delete their API keys and any service-account tokens
they created. Then confirm `grafana` — also when there was nothing to remove.

### Langfuse

As Grafana: no staff account is expected. In the self-hosted Langfuse admin,
remove the person from every organisation and project and revoke any API key
they created. Then confirm `langfuse`.

### Unleash

As Grafana: no staff account is expected, and safety flags are not in Unleash
(invariant 34). In Unleash's admin (Admin → Users), delete or deactivate the
person's user and revoke their personal access tokens. Then confirm `unleash`.

### Incomplete

`OffboardingIncomplete` raises a ticket whenever an offboarding ends with a
system still open: a failed step, or manual steps awaiting confirmation. Close
the manual steps above; re-run a failed one.

## The 60-day auto-disable

`make access-hygiene` reads every staff account (console roles and
`clinician`), and offboards each enabled one whose last login — or, if it never
logged in, whose creation — is 60 days old or more, with reason `dormant_60d`.
Its manual steps appear in the review like any other offboarding. `--dry-run`
lists who would be disabled and changes nothing.

It refuses — exit 4, nobody disabled — when the realm does not record LOGIN
events for at least 60 days (Keycloak has no last-login field; the events store
is the login history, and an expired login looks like no login). It also exits
4 when it is not configured or the directory cannot be read, and exit 2 when a
step failed for an account.

## Owner steps

Nothing in this repository wires the review, the offboarding or the job to a
real Keycloak or OpenBao, and nothing runs the job on a clock. Until the owner
does, the review and offboarding routes answer 503 — **and the console is
read-only for `platform_owner` and `tenant_admin`**, because no review has been
countersigned. That is the fail-closed direction §2.7 asks for.

1. **A confidential Keycloak client for the console**, e.g.
   `intake-access-admin`, with service accounts enabled and only these
   `realm-management` roles: `view-users`, `query-users`, `manage-users`
   (disable and logout), `view-events` (last login) and `view-realm` (events
   configuration). Store its id and secret in OpenBao KV at
   `secret/admin/keycloak-access` (`client_id`, `client_secret`).
2. **Login events kept for at least 60 days** in the production realm: user
   events on, `LOGIN` among the saved types, expiration ≥ 5 184 000 s. The dev
   realm (`infra/keycloak/dev-realm.json`) keeps exactly that and nothing else.
   Keycloak stores the client IP with each event; the retention of that staff
   data is the owner's decision.
3. **The environment**, for the API and the job: `INTAKE_ADMIN_KEYCLOAK_URL`
   (https origin), `INTAKE_ADMIN_KEYCLOAK_REALM`, and
   `INTAKE_ADMIN_OPENBAO_ALIAS_MOUNT_ACCESSOR` — the accessor of the OpenBao
   JWT/OIDC auth mount whose alias names are Keycloak user ids.
4. **OpenBao capabilities** on the token the API and the job run with, in
   addition to their existing policy:

   ```hcl
   path "secret/data/admin/keycloak-access" { capabilities = ["read"] }
   path "identity/lookup/entity"            { capabilities = ["update"] }
   path "identity/entity/id/*"              { capabilities = ["update"] }
   path "auth/token/accessors"              { capabilities = ["list", "sudo"] }
   path "auth/token/lookup-accessor"        { capabilities = ["update"] }
   path "auth/token/revoke-accessor"        { capabilities = ["update"] }
   ```

   Listing token accessors needs `sudo`; whether the API's own token carries
   this or a dedicated offboarding token does is a key-management decision.
5. **A daily trigger** for the job, with `INTAKE_API_AUDIT_DB_URL` pointing at
   the `svc_audit_writer` role (the only INSERT grant on the audit table):

   ```cron
   30 3 * * *  cd /srv/intake && make access-hygiene   # daily, 03:30 UTC
   ```

   A non-zero exit is a failed run the scheduler should report.
6. **The first review**: sign and countersign `platform_owner` and
   `console_roles` (the `platform_owner` countersigner from another
   organisation), which lifts the read-only downgrade.
7. **Grafana, Langfuse and Unleash** stay manual steps until the owner decides
   to give the console an admin credential for each; an adapter then replaces
   the manual entry in `infra/admin/console-accounts.yaml`.
