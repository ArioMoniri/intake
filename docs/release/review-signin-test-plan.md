# App Review sign-in: test plan (INT-613, D39)

App Review signs in to a release build with a reserved reviewer number and a
fixed code. The decision is D39 (files/00_STATE.md §3, owner, 30 Oct 2026),
and INT-488 (issue #829) builds it. This plan says what is proven
automatically without any Apple credential, what INT-488 must add, and what
only a device can prove (INT-348).

## 1. Automated, no Apple credential: runs in CI today

`tests/release/test_review_signin_harness.py` runs
`scripts/release/review_signin_harness.py` against main's real API app, in
process. The app is wired like the dev tier: the dev attestation tier, the dev
peek route, and a counting delivery adapter as the SMS probe. Every number is
synthetic.

| case | expected |
|---|---|
| a synthetic patient signs in | the steps run in order: `otp.request` 202, one delivery, the code, `otp.verify` 200 with `token_type` DPoP, `token.refresh` 200, then an authenticated `GET /v1/me/profile` that is not 401 (403 `consent_required` before the core consent) |
| the report | holds no number, code or token |
| near miss: a wrong code | fails at `otp.verify` |
| near miss: no dev tier (a public host) | the unattested payload is refused with 403 `attestation_unverified`, and nothing is sent |
| D39: the reserved number never sends an SMS | **fails closed against main**: main reserves no number, so the check reports `sms_sent` |
| the command line | refuses a full sign-in against a host, never probes with the reviewer number, and takes no code argument (`REVIEW_SIGNIN_CODE` is read from the environment, and only when it is needed) |

## 2. What INT-488 adds when it merges

INT-488's own suites (`tests/security/test_review_signin*.py` on its branch)
hold the server side. When it lands, add one harness case here: the reserved
number, with the review window open, run with `expect_no_sms=True` against
a wiring that reads the reviewer document. That case must pass: zero
deliveries, a session bound to the reviewer tenant. Its near misses: the
window closed, a non-synthetic tenant, and a wrong code counted under INT-578.

## 3. Against the synthetic host, run by the owner

```sh
SIGNIN_PROBE_NUMBER=<a synthetic number that is not the reviewer's> \
  uv run python scripts/release/review_signin_harness.py \
  --base-url https://3-211-2-143.sslip.io --probe-unattested
```

This proves only that the public host refuses a sign-in without App Attest.
That is INT-348's rule: INTAKE_DEV_ALLOW_UNATTESTED is never set on a public
host. The probe never uses the reviewer number, because every use of it pages
(`ReviewSignInUsed`, `ReviewSignInRefused`). No agent runs it.

## 4. Only a device can prove these (INT-348)

On a TestFlight build of the review commit, with the review window open
(`review_signin.sh --on`):

1. App Attest: the build registers its key and every OTP call carries an
   assertion the host verifies. A server harness cannot fake this.
2. The reviewer signs in with the number and code exactly as App Review
   Information holds them, and lands the synthetic reviewer patient.
3. No SMS arrives on any handset, and the host's audit log shows
   `auth.review.*` rows with ids only.
4. iOS OTP autofill (D34) is not offered for the reviewer code. No SMS exists
   to offer it from.
5. The review notes the reviewer reads match `notice_sha256`.
6. `--off` ends the session on the device, and the reviewer tenant is erased.

Record each run in docs/evidence/INT-348.md with the build number, the date
and the audit row ids. Never record the number, the code or a token.
