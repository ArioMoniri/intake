# Production release checklist (INT-421)

This checklist releases a commit of `main` to the AWS host and the mobile
stores. Run it top to bottom. Each step says who runs it and what "done"
looks like. The host is `i-0e489e48739f5de98` (us-east-1c), serving
`https://3-211-2-143.sslip.io`.

**Synthetic patients only.** us-east-1 receives simulated patients and
nothing else, until an in-country host or counsel's cross-border decision
exists (HB-I5, HB-L11). Secrets live only in `/etc/intake-staging/` on the
host (0600 root). Never print them, paste them or put them in a URL or a
commit.

## 0. Before you start

| check | who | done when |
|---|---|---|
| The AWS CLI on the operator's machine is signed in | owner (`aws login`) | `aws sts get-caller-identity` answers |
| `main` is green in CI, and the release commit is chosen | operator | the commit's checks are all green |
| The console's deploy freeze is open | operator | `deploy.sh`'s release gate logs "allowed" (INT-187) |

## 1. Deploy

The host runs `infra/staging/deploy.sh` from a `git archive` of the release commit.

1. Build the archive: `git archive --format=tar.gz --prefix=intake/ -o onvizit-<sha>.tgz <sha>`.
   - `REVISION` is stamped by export-subst, so `/version` names the commit.
2. Upload it with `aws s3 cp` to the private bucket `onvizit-deploy-artefacts-235229001983`.
   - The bucket blocks public access, uses SSE, and expires objects after 7 days.
3. Presign the object for 30 minutes: `aws s3 presign … --expires-in 1800`.
4. Send `AWS-RunShellScript` through SSM. The script is a bash heredoc that:
   1. fetches the archive and extracts it to `/opt/onvizit-releases/<sha>-<epoch>`;
   2. points `/opt/intake` at the new release;
   3. runs `STAGING_HOSTNAME=3-211-2-143.sslip.io ./init.sh` (idempotent);
   4. runs `./deploy.sh`;
   5. runs `bash ./smoke.sh`.

`deploy.sh` stops before it restarts anything if any of these fails:

- the syft or object-store pin;
- the swap guard;
- the SBOM;
- the release gate;
- a migration.

When it stops, the previous release keeps serving. Section 1 of docs/evidence/INT-421.md has a real example.

## 2. Verify

| check | done when |
|---|---|
| `smoke.sh` | the last line reads `smoke: all checks passed for <sha>` |
| `/version` | `git_sha` is the release commit. `sbom_digest` is `sha256:` + the sha256 of `/etc/intake-staging/releases/<sha>/api-<image>.spdx.json` |
| Admin tier | smoke passes these checks: the realm issuer is `https://auth.<host>/realms/intake`; `/admin/` and the master realm answer 404; the console's `/healthz` answers 200 with a strict CSP; `/ops` redirects to the Keycloak login; the API's `/admin/ops` refuses an anonymous caller |
| Evidence | the run's SSM command id, the smoke lines, the SHA and the SBOM digest are recorded in the issue's evidence file |

## 3. One-time steps after the first deploy of this release

1. **Retire the dev fixture.** This is the owner's directive: "in production don't include deneme hastası". It was done on the AWS host on 2 Oct 2026 (docs/evidence/INT-421.md §3), so a re-run there reports `absent`. On any other host, as root, in `/opt/intake/infra/staging`, run:
   ```bash
   source ./lib.sh && load_env && stamp_revision && stamp_sbom_from_disk && \
     compose run --rm --no-deps -T api python -m intake_api.dev_fixture_retire
   ```
   - Expect `dev fixture: retired and audited (consents 3, patient 1, tenant 1; …)`. On a re-run, expect `absent, nothing to retire`.
   - Exit 3 means it refused, and nothing was removed. The message names the table holding a row the seed did not write. An operator decides what happens next. Never delete rows with raw SQL: the audit chain must show every removal.
2. **Create staff accounts in Keycloak** (owner). The realm `intake` ships with no users.
   1. Over SSM, run `docker compose -p intake-staging exec keycloak /opt/keycloak/bin/kcadm.sh`. Log in to `http://localhost:8080` as `intake-bootstrap`. Its password is `KEYCLOAK_ADMIN_PASSWORD` in the host's root-only env file; read it on the host, never in chat.
   2. Create each user with a verified email.
   3. Grant the role from the realm's role list.
   4. Set the required action `webauthn-register`, so each person enrols their own security key or passkey. The staff browser flow refuses a login without a second factor.
      - The console admits only a WebAuthn login: that token carries `aaguid` and `credential_id` (INT-378).
      - It refuses a TOTP login until the owner decides INT-389 (#644).
      - The deploy has already switched the live realm to the provider that writes the two ids (`ensure_staff_webauthn_notes`), and `smoke.sh` check 7 confirms it.
3. **Network access to the console is open by decision.** The owner decided D19 on 2 Oct 2026: *"dont make admin access ip restricted"*. The API's `/admin` allow-list is the committed `0.0.0.0/0,::/0`. What gates the console is the Keycloak login (password plus a second factor) and the role matrix. Do not narrow the list without a new owner decision.

## 4. Roll back

- **No console rollback exists.** INT-401 ("rollback from the console, 4-eyes") is `awaiting-human` and not merged.
- **To roll back today:** re-point `/opt/intake` at the previous release directory under `/opt/onvizit-releases/`, then re-run `./deploy.sh` and `./smoke.sh`.
  - The previous image and its SBOM are still on the host, so `/version` names the old commit again.
- **Migrations are forward-only.** A release whose migration has run cannot be rolled back past that migration. Choose the target accordingly.
- **To pause releases without rolling back,** use the deploy freeze (INT-187, docs/runbooks/deploy-freeze.md).

## 5. Mobile store builds

These run from `apps/mobile`, using `eas.json`'s `production` profile.

1. **Prerequisites (owner only):**
   - Apple Developer Program membership and App Store Connect access for app `6814005465` (HB-A3);
   - a Google Play developer account and the app record for `com.ariomoniri.intakemobile` (HB-A3);
   - an Expo account with access to project `307d4cf2-c447-4855-8110-da59fb5ed170`.
2. **Identity:** the iOS build needs INT-420 merged, which brings the Önvizit name and `ios.bundleIdentifier`. `expo config --type public` must show both before you build.
3. **Credentials:** the owner runs `eas login`, or sets `EXPO_TOKEN`, and then runs `eas credentials` for each platform. EAS stores the signing material on its own servers. Nothing goes into the repo.
4. **Build:**
   - command: `eas build --profile production --platform all --non-interactive --no-wait`;
   - record the two build URLs in the evidence.
5. **Submit:**
   - command: `eas submit --profile production --platform ios`, then `--platform android`, with Android going to the internal track first;
   - the App Store Connect API key and the Play service-account key are supplied at submit time, from the owner's machine or EAS. They are never committed.
6. **Store listing (INT-482, INT-495):** the App Store copy and its answers are now served. The legal lane approved them on #828, and INT-495 promoted them on 16 Oct 2026. The Google Play copy stays a draft, because the owner deferred Play (INT-496, `docs/store/google-play-later.md`).

   | artefact | file | state |
   |---|---|---|
   | App Store listing for Önvizit, Turkish | `docs/legal/store/listing/app-store.tr.yaml` | served |
   | App Store listing for Önvizit, English | `docs/legal/store/listing/app-store.en-US.yaml` | served |
   | App Store category, age rating (`advisory`, `advisory_asc`), content rights and App Review notes | `docs/legal/store/submission/app-store.yaml` | served |
   | Google Play listing, Turkish (same text as the App Store) | `docs/legal/drafts/store/google-play.tr.draft.yaml` | draft; Play deferred |
   | Google Play listing, English | `docs/legal/drafts/store/google-play.en-US.draft.yaml` | draft; Play deferred |
   | Play App access text, IARC facts, Health apps facts | `docs/legal/drafts/store/google-play.submission.draft.yaml` | draft; Play deferred |
   | App Privacy and Data safety answers, one row per inventory fact | `docs/legal/drafts/store/privacy-answers.draft.yaml` | entered by hand: App Privacy has no App Store Connect API resource |
   | what must hold before submission, the reviewer account, the 112 behaviour | `docs/legal/drafts/store/app-review-notes.draft.md` | the owner's guide |
   | the App Store creative-asset slots (header, iPhone screenshots) | `docs/store/asc/assets.yaml` | no captures yet; INT-502 (#856) |
   | the captions on the screenshots and the header, Turkish and English | `docs/legal/drafts/store/app-store.screenshots.draft.yaml` | draft for the legal lane; export reads only its served copy (INT-502) |
   | which screens are captured, how a frame is laid out, the sizes rendered | `docs/store/asc/frames.yaml` | INT-502: `scripts/store/capture_frames.py`, then `scripts/store/render_frames.py` |

   - **Render.** `make store-config` runs `scripts/release/render_store_config.py`, which wrote `apps/mobile/store.config.json` from the served files only. It prints each field it had to leave out together with the blocker that owes it. `make store-config-check` fails on drift. The file pins `automaticRelease: false`, so an approval never publishes the app by itself, and it never carries a reviewer contact or sign-in.
   - **App Store Connect draft (INT-495).**
     - `make asc-plan` prints the dry-run plan: resources and field names, never a value, and every blocked field. It needs no credentials.
     - The owner writes the draft with one command, after their own yes: `make asc-draft EAS_JSON=<your eas.json that holds ascApiKeyPath>`. It reads the key file, key id, issuer id and app id from that file at run time. It writes only the draft fields on the next editable version, and logs field names and HTTP statuses only. It never submits for review, releases, or touches pricing, availability, agreements or the App Review sign-in.
     - Upload the header and the screenshots with INT-502 (#856), once the design stack has merged and they are captured. Until then the plan lists those slots as blocked.
     - `eas metadata:push` (run from `apps/mobile`, after `eas submit` has uploaded a binary) is the other route for the EAS-schema fields. `make asc-draft` covers everything it covers, plus the live age-rating keys and the content-rights answer. While the review notes are held (`review_notes_hold` in the submission), `store.config.json` carries no `review` block, so neither route sends them (INT-502 legal review B5).
   - **Before you submit for review,** each item in `app-review-notes.draft.md` §1 must hold. Three of them matter most:
     - INT-117 must render the static 112 notice from the signed fixed strings (HB-L27). The notes say the app shows it, and today it does not.
     - A reviewer must be able to sign in. Phone sign-in cannot reach a reviewer, and INT-488 (#829) builds the reviewer path.
     - Voice intake must be reachable in a release build through the streaming path (`lib/livekit`), which writes no file. Today `voiceEligible` requires `__DEV__` (`intake.tsx`). Owed by INT-440 (#768) and INT-454 (#769). The review notes describe voice, so they wait for this. The listing no longer does (INT-502 legal review B1).
   - **Still open:** HB-L21 (a) audio as collected, (b) the Play Health apps policy, (c) the IARC answers, (e) the seller's identity, which leaves the support URL, the privacy-policy URL and the copyright line empty. Also HB-L27 (the signed `gizlilik` and fixed strings) and HB-A12 (the vendor snapshots).
   - **Synthetic scope.** The host receives simulated patients only (HB-I5, HB-L11). Builds go to TestFlight internal testing. No public release goes live while that scope holds.
   - **Screenshots** for the new design are INT-502 (#856). INT-425 (PR #738, open) captured the earlier design and is not copied here. Once #738 merges, the INT-482 tests run its captions through the same gates as the listing.

7. **Owner asks for the stores, one line each:**
   1. Expo: run `eas login` on the build machine, or set `EXPO_TOKEN` to an Expo access token for project `307d4cf2-c447-4855-8110-da59fb5ed170`.
   2. Apple: give App Store Connect access (App Manager or Admin) for app `6814005465` under an Apple Developer Program membership (HB-A3).
   3. Google: give Google Play Console access to the app `com.ariomoniri.intakemobile` (HB-A3).
   4. Rename: after INT-420 (PR #729) merges, set the name to Önvizit in App Store Connect (App Information, both `tr` and `en-US`) and in the Google Play Console (Main store listing, App name).
   5. App Store Connect draft: after your own yes, run `make asc-draft EAS_JSON=<your eas.json that holds ascApiKeyPath>`; it writes the editable draft only.
   6. App Privacy: enter the answers by hand in App Store Connect from `docs/legal/drafts/store/privacy-answers.draft.yaml`, because the API has no resource for it.

## 6. Owner-only steps

These are named once here. Each is a single action.

1. Keep the AWS CLI signed in on the operator's machine (`aws login`). Each deploy needs it.
2. Provide Apple Developer and App Store Connect access, and a Google Play Console account (HB-A3).
3. Provide an Expo token (`EXPO_TOKEN`), or log in to Expo on the build machine.
4. Name the production domain and the ACME mailbox (HB-I14). Until then the host uses `sslip.io`.
5. Choose an SMS vendor with a signed DPA, and set the App Attest team id. Phone sign-in needs both.
6. Hosted model lanes for simulated patients are being built separately (INT-428). Voice has no backup lane on this host until INT-428 lands.
7. Decide whether a workers tier exists (INT-408).
