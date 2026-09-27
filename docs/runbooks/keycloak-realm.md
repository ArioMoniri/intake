# Runbook — the deployed Keycloak realm the admin console trusts

**Owner:** `platform_owner` · **Issue:** INT-373 · **Spec:** files/08 §2, §8 rule a, §8.1 ·
**Threat-model row:** `admin-console` · **Keycloak:** 26.1.4 (the tag `infra/docker-compose.obs.yml` pins)

`infra/keycloak/dev-realm.json` is the laptop fixture, and no deployed environment is seeded
from it. This runbook is what the owner applies by hand to the deployed realm, so that a
staff token carries every claim the console reads. Until it is applied, the console refuses
every staff token. That is the fail-closed direction and it is intended: the answer is `401`
or `403`, never an admission with a guessed value.

`tests/admin/test_realm_claim_mappers.py` holds the table in §2 against the committed realm,
so this page cannot drift from the file.

## 1. What the console reads, and from where

| claim | read by | where Keycloak gets it |
|---|---|---|
| `aud` ∋ `api` | `KeycloakClaimsVerifier` (`INTAKE_ADMIN_OIDC_AUDIENCE=api`) | the audience mapper, naming the bearer-only client `api` |
| `org` | `principal_from_claims` → audit actor block | the user's `org` attribute |
| `tenant` (absent for platform roles) | `principal_from_claims` → tenant scope (files/08 §8 rule a) | the user's `tenant` attribute |
| `aaguid` | audit actor block, four-eyes "distinct authenticator" | a user-session note that **no stock authenticator writes** (§3) |
| `credential_id` | audit actor block, four-eyes "distinct credential" | a user-session note that **no stock authenticator writes** (§3) |

Every value must match the console's id shape `[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}`, or the token
is refused as malformed. `sub`, `sid` and `realm_access.roles` come from Keycloak's built-in
scopes and need no mapper.

## 2. Mappers on the console client (`admin-web`, or the deployed console client)

Clients → the console client → **Client scopes** → the dedicated scope → **Add mapper → By
configuration**. Every mapper below sets *Add to access token* **on**, *Add to token
introspection* **on**, *Add to ID token* **off** and *Add to userinfo* **off**. The console reads
only the access token, and the ID token goes to the browser.

| mapper name | mapper type (`protocolMapper`) | source | claim | settings |
|---|---|---|---|---|
| `audience api` | `oidc-audience-mapper` | `api` | `aud` | *Included Client Audience* = `api` |
| `org` | `oidc-usermodel-attribute-mapper` | `org` | `org` | *User Attribute* = `org`, JSON type `String`, multivalued **off**, aggregate **off** |
| `tenant` | `oidc-usermodel-attribute-mapper` | `tenant` | `tenant` | *User Attribute* = `tenant`, JSON type `String`, multivalued **off**, aggregate **off** |
| `aaguid` | `oidc-usersessionmodel-note-mapper` | `intake.webauthn.aaguid` | `aaguid` | *User Session Note* = `intake.webauthn.aaguid`, JSON type `String` |
| `credential_id` | `oidc-usersessionmodel-note-mapper` | `intake.webauthn.credential_id` | `credential_id` | *User Session Note* = `intake.webauthn.credential_id`, JSON type `String` |

Then set, on the API host, `INTAKE_ADMIN_OIDC_AUDIENCE=api`, `INTAKE_ADMIN_OIDC_ISSUER` to the
realm's issuer URL, and `INTAKE_ADMIN_OIDC_JWKS_PATH` to the mirrored JWKS.

**Check:** sign in as a staff account, decode the access token, and confirm that `aud` contains
`api` and that `org` and `tenant` are present as plain strings, not arrays.

## 3. `aaguid` and `credential_id` — Keycloak cannot emit these today

Keycloak 26.1.4's WebAuthn authenticator verifies the assertion, then records the credential id
only as an **event detail** (`public_key_credential_id`). It sets no authentication note and no
user-session note, and no stock protocol mapper reads event details. The AAGUID is stored on
the credential (`WebAuthnCredentialModel`) but is copied nowhere at login. So no configuration
of a stock realm puts either value in a token. The two mappers in §2 read notes that nothing
writes yet. They emit nothing, and the console refuses the token. Nothing is faked.

**The smallest mechanism that closes this.** One Keycloak provider jar, installed under
`/opt/keycloak/providers`, that registers an authenticator wrapping the stock
`webauthn-authenticator`. After the stock assertion **succeeds**, it:

- looks up the stored credential the assertion matched;
- calls `setUserSessionNote("intake.webauthn.aaguid", <credential AAGUID, UUID text>)`;
- calls `setUserSessionNote("intake.webauthn.credential_id", <credential id, base64url without
  padding>)`.

`TokenManager.attachAuthenticationSession` then copies both into the user session, and the §2
mappers emit them. The credential id must be **base64url without padding**. Keycloak stores it
as standard Base64 (`+`, `/`, `=`), and `+` and `=` fall outside the console's id shape. The
event detail already uses the unpadded base64url form. The provider replaces the stock
execution in the realm's second-factor subflow. It is not added beside it.

This provider is **not in the repository**. Building and signing it is its own issue.

**Owner decision needed first.** INT-365 lets the six roles that never reach patient content sign
in with TOTP instead of WebAuthn. A TOTP credential has no AAGUID, and the console requires
`aaguid` on every token. So until the owner decides what `aaguid` means for a TOTP login, the
console will refuse every TOTP sign-in. The options are to require WebAuthn for every console
role, or to give the actor block a TOTP-specific value. The provider waits on that decision.

## 4. Who may write `org` and `tenant` — the user profile

The two attributes decide the token's organisation and tenant scope. A staff member who could
edit their own `tenant` could move themselves into another tenant. In Keycloak 26 an attribute
not declared in the user profile is *unmanaged*, and with the default policy (`DISABLED`) an
administrator cannot set it either. So declare both:

Realm settings → **User profile** → **Create attribute**, once for `org` and once for `tenant`:

- **Who can edit:** Admin only. **Who can view:** Admin only. The user can then read their own
  value only by decoding their token.
- **Multivalued:** off.
- **Validator** `pattern`: `^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$`, the console's id shape. A
  malformed value is then refused at the moment it is saved, not at the next login.
- **Required:** off. A platform role carries no `tenant`.
- Leave **Unmanaged attributes** at *Disabled*.

`tenant` is the tenant's UUID as the API database knows it. The console scopes tenant reads by
parsing the claim as a UUID. A claim that does not parse scopes the read to no rows, and it is
not refused.

Set both values **on the user**, never on a group. When the user has no value, Keycloak's
attribute mapper falls back to the first group that has one
(`KeycloakModelUtils.resolveAttribute`). A user in two tenant groups would then get whichever
tenant the store returned first.

## 5. When a staff token is refused

| response | meaning | fix |
|---|---|---|
| `401 {"error":"unauthorized"}` | the verifier refused the token. `aud` without `api` is one cause; issuer, key and expiry are the others | §2 row `audience api`, `INTAKE_ADMIN_OIDC_AUDIENCE`, `INTAKE_ADMIN_OIDC_ISSUER` |
| `403 {"error":"forbidden"}` | no console role, or `org`, `aaguid` or `credential_id` absent or not id-shaped | §2, §4 for `org`; §3 for the WebAuthn pair |
| admitted, but tenant pages are empty; break-glass answers `422 tenant_required` | `tenant` absent, or not the tenant's UUID, for a tenant-scoped role | §4: set `tenant` on the user |

The refusal body carries a code, never the claim value (invariant 6). Decode the token yourself
to see which claim is missing.
