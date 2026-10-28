# ADR-043 · The four-eyes step-up is a Keycloak re-authentication the API verifies

Status: Accepted, 28 Oct 2026 (number allocated and design approved by the orchestrator for INT-563, GitHub #952; amends the admin console's CSP for one origin)

## Context

files/08 §2.3 says *"Step-up is a fresh, single-use WebAuthn assertion at the moment of the
action."* Until INT-563 no approval met it. The nine approve and countersign routes (break-glass,
voice release, profile and canary, the deploy-freeze lift, the three model-lane widenings, the
access-review countersignature) took an `assertion_id` the API never checked: `FourEyesService`
spent any unused string. The approver block carried the credential the console session had logged
in with, possibly hours before. So four-eyes' "different credential" compared two old logins, and
the approval was a second click, not a second key. The console showed every **Onayla** button
disabled. Three facts constrain the fix:

- The console is script-free under a nonce CSP with no `unsafe-*` (D26 withdrawn), so it cannot
  call `navigator.credentials.get`.
- The API holds no WebAuthn public keys. Keycloak holds them, and runs the staff browser flow.
  That flow's WebAuthn step, the INT-378 `intake-webauthn-session-notes` provider, is REQUIRED
  (INT-550). It writes the asserted credential's id and AAGUID as user-session notes.
- Keycloak imports a realm once. A realm change reaches the live host only through an idempotent
  admin-API script, and a `PUT` on a flow without each execution's priority zeroes them. That
  broke deploy e19640d2.

**What `amr` proves, from Keycloak 26.1.4 and 26.7.4 source.** `oidc-amr-mapper`
(`AmrProtocolMapper.getAmr`) reads the user session's `AUTHENTICATORS_COMPLETED` note. Through
`AmrUtils` it emits each completed execution's `default.reference.value` while
`authTime + default.reference.maxAge >= now`. The realm sets `amr hwk` with a maxAge of 28800 on
the WebAuthn execution. So `amr` reliably contains `hwk` when the WebAuthn step completed in this
Keycloak session within eight hours. It does not prove that the step ran in *this* login.
`AuthenticationManager` rewrites the session's `AUTH_TIME` note on every non-SSO authentication
(`isSSOAuthentication` false), and `prompt=login` makes the re-authentication non-SSO. `auth_time`
is therefore the freshness evidence. The credential notes are rewritten by the same new assertion,
and they name which key made it. `TokenManager.generateIDToken` sets `typ=ID`, `aud` and `azp` to
the client, `nonce`, and `sid` (the same user session, because a different user re-authenticating
in it is refused).

## Decision

**A second key is presented only as a step-up grant the API issued after verifying a fresh Keycloak
re-authentication. There is no other path.**

1. **The API owns the ceremony.** `POST /admin/step-up {action_id}` first refuses an approval that
   could never pass: the action is unknown, decided or expired, the caller holds no approver role
   for it, or the caller is the requester, which is counted as self-approval. It then opens a
   ceremony bound to the caller's subject, Keycloak session (`sid`) and that one action, for two
   minutes, with `state`, `nonce` and a PKCE S256 verifier that never leaves the API. It answers an
   authorization URL for the public client `admin-web-stepup` with `prompt=login` and `max_age=0`.
2. **The console carries it without script.** **Onayla** posts to `/step-up/start`. The console
   follows the URL only if it is the configured Keycloak origin's authorization endpoint for that
   client, with `prompt=login` and `max_age=0`. Keycloak returns to `/step-up/callback`, which
   relays `{state, code}` to `POST /admin/step-up/complete`, then presents the grant on the
   action's own approve route from a closed table.
3. **The API verifies, fail closed.** It redeems the code at the internal token endpoint with the
   verifier. It verifies the ID token RS256 against the same mirrored key set as the console bearer
   (no key is fetched at approval time), plus issuer, audience, expiry, `typ=ID`, `azp`, the
   ceremony's `nonce`, the caller's `sub` *and* `sid`, and `auth_time` no earlier than the
   ceremony's start less 30 s. It also requires `hwk` in `amr`, a well-formed `credential_id`, an
   id-shaped `aaguid`, and a `jti` never spent before. **We verify `amr hwk` and a fresh
   `auth_time` together. The `credential_id`/`aaguid` notes identify the key; they are not the
   freshness evidence.** Any failure refuses with a code. The cases include an unreachable token
   endpoint, a reused code or state, an unknown or expired ceremony, and a sub or sid mismatch.
   The old `assertion_id` path is deleted, and a body still carrying it is refused.
4. **The grant is one approval of one action by one caller.** `sug_` plus 128 random bits. It is
   bound to subject, session and action, lives two minutes, and is spent by the first approval
   presenting it. A foreign presentation is refused without burning it. The approver block carries
   the credential and AAGUID just asserted. Four-eyes spends `stepup:<sha256(jti)[:32]>` as the
   assertion id.
5. **Audit and metrics.** `admin.four_eyes.step_up.granted` and `…redeemed` go on the hash-chained
   log. The use is written ahead of the approval. Both name the action and the hashed token id,
   never the grant or a credential. `admin_step_up_total{stage,outcome}` counts every stage and
   refusal, and is the alert of the new tier-1 action `admin.four_eyes.step_up`.
6. **The realm client reaches the host through the deploy path.** `admin-web-stepup` is a public
   client with the standard flow only, PKCE S256, the console callback as its one redirect URI and
   no web origins. Its three mappers put `aaguid`, `credential_id` and `amr` in the ID token only.
   `infra/staging/keycloak/step_up_client.py` adds it when it is absent and verifies it when it is
   present. Any difference is refused for a human to look at. The script never reads or writes a
   flow or an execution. `deploy.sh` runs it after the staff flow settles, and `smoke.sh`
   re-checks it read-only.
7. **The CSP widens by one origin.** `form-action` becomes `'self'` plus the configured Keycloak
   origin (`INTAKE_ADMIN_STEP_UP_ORIGIN`), because browsers hold a form's redirects to
   `form-action`. Nothing else in the CSP changes, and with no origin configured it stays
   `'self'`.

## Consequences

The **Onayla** buttons work, and an approval now means a person re-authenticated with their passkey
for that one action within two minutes. The credential four-eyes compares is the one they just
used. A stolen console bearer can no longer approve anything without the victim's passkey, and a
console bug cannot mint a grant: the PKCE verifier and the token verification are the API's. An
approval costs one Keycloak round trip, and an approval without a configured step-up answers `503`
(`step_up_unconfigured`), with no fallback. `tests/admin/test_step_up.py` and
`tests/admin/test_step_up_routes.py` hold these properties with near misses: each is the honest
ceremony with one thing changed, including the pre-INT-563 unused-string approval, now refused.
`tests/infra/test_staging_step_up_client.py` holds the deploy path, and `e2e/step-up.spec.ts` the
console.

The residual risk is stated, not hidden. The step-up proves the WebAuthn step ran in the fresh login
only while the staff browser flow keeps it REQUIRED. If an operator made it optional in the live
realm, a password-only re-authentication would carry the earlier assertion's notes and `hwk` (within
its eight-hour reference age) with a fresh `auth_time`. `staff_flow check` holds the flow on every
deploy and every smoke, and its failure is a deploy stop. Storage is process-local, like
`FourEyesService`, so a restart drops every ceremony and grant, which refuses rather than grants.
