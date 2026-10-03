# Runbook — the deployed Keycloak realm the admin console trusts

**Owner:** `platform_owner` · **Issues:** INT-373, INT-378 · **Spec:** files/08 §2, §8 rule a, §8.1 ·
**Threat-model row:** `admin-console` · **Keycloak:** 26.7.4 (the tag and digest `infra/docker-compose.obs.yml` pins)

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
| `aaguid` | audit actor block, four-eyes "distinct authenticator" | a user-session note the INT-378 provider writes (§3) |
| `credential_id` | audit actor block, four-eyes "distinct credential" | a user-session note the INT-378 provider writes (§3) |

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

## 3. `aaguid` and `credential_id` — the WebAuthn session-notes provider (INT-378)

Stock Keycloak (26.1.4 and 26.7.4 alike) cannot emit either value. Its WebAuthn authenticator verifies the
assertion, then records the credential id only as an **event detail**
(`public_key_credential_id`), and no stock protocol mapper reads event details. The AAGUID is
stored on the credential (`WebAuthnCredentialModel`) but copied nowhere at login.

**The provider.** `infra/keycloak/providers/webauthn-session-notes` builds one jar,
`intake-webauthn-session-notes-1.0.0.jar`, which registers the authenticator
`intake-webauthn-session-notes`. It is the stock `webauthn-authenticator` (a subclass of
`WebAuthnAuthenticator`, same factory settings), and after the stock `action` returns with
`SUCCESS` it:

- looks up the stored WebAuthn credential whose id is the asserted one;
- calls `setUserSessionNote("intake.webauthn.aaguid", <that credential's AAGUID, UUID text>)`;
- calls `setUserSessionNote("intake.webauthn.credential_id", <the credential id, base64url
  without padding>)`.

On any other outcome it writes nothing. `TokenManager.attachAuthenticationSession` copies both
notes into the user session, and the §2 mappers emit them. The credential id is base64url
without padding, the form the stock authenticator already uses in its event detail and on its
login page. Keycloak stores it as standard Base64 (`+`, `/`, `=`), and `+` and `=` fall
outside the console's id shape.

**Build and check.** `make keycloak-provider` builds the jar with the module's Maven wrapper
(Maven 3.9.16, pinned by sha256), refuses any artefact whose sha256 is not in the module's
`.mvn/checksums/`, runs the provider's tests, and checks the jar against
`infra/keycloak/providers/webauthn-session-notes.sha256`:

```
896d66982867ae23c3668df8138fde257feb61f9e30ac224d74a80a9e78f86df  intake-webauthn-session-notes-1.0.0.jar
```

The build is reproducible, so the owner can rebuild from the tagged source and get the same
bytes. The required CI job `check-py` does exactly that, as a step, on every PR. A source change changes
the hash. Update the pin in the same PR, with a new recording (**Proof, recorded**, below).

**Deploy it to the deployed Keycloak.**

1. Run `make keycloak-provider` on the commit being deployed. It prints
   `intake-webauthn-session-notes-1.0.0.jar: OK` only when the jar matches the pin.
2. Copy that jar to `/opt/keycloak/providers/` on the Keycloak host or image. Copy nothing
   else from `target/`.
3. Re-augment: `bin/kc.sh build` (or start without `--optimized`, which builds first). An
   optimized server that is not rebuilt never loads the provider. At start Keycloak logs
   `KC-SERVICES0047` for it; that warning is expected for any custom authenticator.
4. In the realm's staff browser flow, the second-factor subflow's WebAuthn execution must be
   `intake-webauthn-session-notes`, not `webauthn-authenticator`. Keycloak cannot change an
   execution's provider in place. Add the new execution to the subflow, give it the `amr hwk`
   reference config (`default.reference.value: hwk`, `default.reference.maxAge: 28800`), set it
   ALTERNATIVE at the stock execution's position, then delete the stock execution.
5. Sign in with a WebAuthn staff account and decode the access token. `aaguid` must equal the
   AAGUID the admin console shows for that credential (Users → Credentials → Show data), and
   `credential_id` must be its id in base64url. A TOTP sign-in carries neither (below).

**Proof, recorded.** `scripts/keycloak/record_webauthn_login.py` logs a synthetic staff account
in to a real Keycloak 26.7.4 twice: once through this realm and once through a twin that runs
the stock `webauthn-authenticator`. It uses a software authenticator and needs no browser.
`tests/admin/fixtures/keycloak_webauthn_login.json` is its output, which
`tests/admin/test_webauthn_session_notes_provider.py` replays through the console. The first
login is admitted with both ids, and the stock one is refused. `docs/evidence/INT-378.md` has
the commands.

**Credential ids the console refuses.** A base64url id can start with `-` or `_` (2 in 64 ids),
and one longer than 96 bytes encodes to more than 128 characters. Both fall outside the
console's id shape, so such a login is refused (fail closed) even with the provider. Until the
console's rule changes, re-register the key for that staff member, which mints a new id.

**Owner decision still needed.** INT-365 lets the six roles that never reach patient content
sign in with TOTP instead of WebAuthn. A TOTP login has no AAGUID, so the provider writes
nothing and the console refuses the token. The choices are (a) require WebAuthn for every
console role, or (b) require `aaguid` only when `amr` contains `hwk`. The console's rule is
unchanged until the owner records the choice (INT-389, issue #644).

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
