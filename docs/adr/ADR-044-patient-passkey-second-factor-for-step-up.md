# ADR-044 · A patient passkey is the second factor, and it is used for step-up only

Status: Accepted, 30 Oct 2026 (owner decision D36, 28 Oct 2026; id allocated by the orchestrator for INT-582, GitHub #981)

## Context

A patient signs in with a phone OTP (INT-131), and a SIM swap hands the attacker that SMS. The
OTP proves who holds the number and nothing more. Without a second factor, everything an OTP
session can do, an attacker who controls the number can also do: issue a Doctor Link that
releases the note to whoever holds it, read the KVKK m.13 export, or schedule the erasure of the
record. D36 (owner, 28 Oct 2026) allows the server to store patient passkey public keys. It also
names four actions that step up to the passkey: issuing a Doctor Link, changing the phone number,
data export and data delete. Four forces make this a decision rather than a preference:

- **The verifier is security code on the PHI path.** It has to be either a library or something
  small enough to audit line by line.
- **A step-up must not become a lockout.** Most patients will never enrol, and a patient who
  cannot prove a passkey they never made would lose a statutory right (KVKK m.11).
- **Recovery reopens the attack.** A lost phone needs a way back. If the OTP alone is that way
  back, it is also the way in for whoever holds the SMS.
- **Configuration can fail.** When the tier is not configured, the system must choose between
  refusing a patient and quietly downgrading them.

## Decision

The passkey is a second factor for **step-up**, never a sign-in replacement:

1. **Sign-in and step-up.** Sign-in stays OTP + DPoP. A grant from a passkey assertion is
   required, per action and per request, on the routes `intake_api.passkey.gate.STEP_UP_ROUTES`
   names (D36's four, plus removing a passkey and cancelling a recovery). The grant is
   single-use, lives 120 s, and is bound to the tenant, the patient, the DPoP device session
   and the action.
2. **Registration** happens only from an OTP-verified DPoP session.
3. **Hand-rolled verifier.** The verifier is a small, hand-rolled WebAuthn Level 3 check,
   `intake_api.passkey.webauthn`, built on `cbor2` and `cryptography`. Both are already
   licence-verified for App Attest (INT-344), and the strict-decoder style follows
   `app_attest_decode.py`. `webauthn` 3.0.1 (Duo Labs, BSD-3-Clause, LICENSE blob read on
   30 Oct 2026) was weighed and rejected: it adds `pyOpenSSL`, `pyasn1` and `pyasn1-modules`
   to the API image for attestation formats this decision refuses.
4. **Only ES256 and `fmt: none` are accepted.** Credential parameters offer COSE −7 alone,
   which every platform passkey supports. Anything else is refused: RS256, EdDSA, any other
   format, or a non-empty `attStmt`. The server does not verify which device made the
   passkey; it verifies that the same key signs each time, with user verification. The signature
   counter follows WebAuthn §6.1.1: a counter that does not move forward is refused as a clone,
   and 0 against 0 passes, which is the synced passkey's case.
5. **No passkey means no change.** A patient without a passkey is not stepped up. The tier that
   stood before (the OTP session) still applies. The gate says so on every such response with
   `X-Intake-Passkey-Enrolment: offered`, and each pass is audited (`step_up.otp_tier`). The
   app offers enrolment.
6. **Never downgrade.** If the patient has a passkey and the tier is unconfigured (no RP ID or
   origins, or no OTP-tier Redis), the action is refused with **503** and the manual path. It
   is never answered by the OTP tier.
7. **Every refusal made on the step-up signal alone names the manual path**,
   `kvkk_m13_application`: a person reviews it, under KVKK m.11(1)(g).
8. **Recovery from a lost phone** is the OTP tier plus a **72 h cool-off**. The cool-off is an
   engineering default for the owner to confirm, held in one constant (`RECOVERY_COOLOFF_S`).
   The passkey keeps guarding the actions throughout the cool-off, and its holder can cancel
   the recovery with a step-up. When the cool-off ends, the passkey is deleted and audited,
   and the patient is offered enrolment again.

A route that serves one of D36's actions without `require_step_up` violates this ADR. So does a
code path that answers an enrolled patient with the OTP tier.

## Consequences

**What becomes easier.** A SIM swap no longer reaches D36's actions for an enrolled patient.
To get there it must also hold the number unnoticed through the whole cool-off, while D35's push
notice reaches the patient's signed-in devices (INT-583 builds that channel).

**What becomes harder.** Every new sensitive route has to be added to `STEP_UP_ROUTES`. The
phone-change route, when it is built, is held to this by
`test_no_route_changes_the_phone_number_without_the_gate`. The relying party is D34's synthetic
host, so moving to the production domain at real launch invalidates every passkey made before
it, because a passkey is bound to its RP ID. That move needs its own decision and a re-enrolment
path. Android has no allowed origin yet, so it stays on the OTP tier until its
`android:apk-key-hash:` origin is configured. Stored data is the public half only: a credential
id, a public key, the counter, BE/BS, and an opaque per-patient user handle. This is a new
personal-data category, `authentication_credential`, on the proposed KVKK m.12/1 security basis,
for the legal lane to confirm. The DSAR export lists it and the erasure removes it.

**What enforces it.**
- `tests/api/test_passkey_webauthn.py`: every check, each with its near miss.
- `tests/api/test_passkey_challenges.py`.
- `tests/api/test_passkey_step_up.py`: the served-route map, replay, another action, another
  session, the counter, another account, a stale challenge, and no passkey.
- `tests/api/test_passkey_enrolment.py` and `tests/api/test_passkey_edges.py`: the 503 posture,
  recovery, and ids-only audit.
- `tests/data/test_inventory.py`.
- The app side under `apps/mobile/src/lib/auth/passkey/` and `apps/mobile/src/lib/shares/`.

**Where it is recorded.** files/00_STATE.md D36 records the owner's decision. This ADR records
how it is carried out. docs/evidence/INT-582.md holds the licence reads.
