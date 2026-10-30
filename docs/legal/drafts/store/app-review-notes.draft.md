> TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force

# Önvizit — App Review and Play review: what the owner needs (INT-482)

Prepared on 2026-10-04 by a drafting agent for the legal lane (GitHub #825). It is pending
legal-lane review. This file is for the owner and the reviewer of this PR. The text the store
reviewers read is in the served `docs/legal/store/submission/app-store.yaml` (`review_notes`;
promoted by INT-495) and in
`google-play.submission.draft.yaml` (`app_access_instructions`). Nothing here is submitted.

## 1 · Do not submit until each of these holds

Each item names who owes it. App Review reads the notes as true on the day of submission, so a
missing item is a reason to wait. It is not something to describe around.

| # | what must hold | owed by |
|---|---|---|
| 1 | The app shows the fixed 112 notice at its static points. Its text is the files/06 §7 static safety line, rendered from `docs/legal/strings.yaml` once counsel has written and signed it. The notes and the listing say that the app shows it. Today the app does not. | INT-117 (static 112 text at fixed points), HB-L27 (the fixed strings) |
| 2 | A signed privacy policy (`gizlilik`) and the URL it is served at. The privacy link binds to its sha256 (`intake_platform.store.eas_metadata.bind_legal_link`). | HB-L27, HB-L21(e) |
| 3 | The seller's legal entity, the support contact and the KVKK contact. | HB-L21(e) |
| 4 | Whether microphone audio counts as *collected* on each store's form. This answer fills the voice row of `privacy-answers.draft.yaml`. | HB-L21(a) |
| 5 | The app is called Önvizit in the binary, not only on the store. | INT-420 (PR #729) |
| 6 | Phone sign-in works on the production host: an SMS vendor with a signed DPA, and the App Attest team id. | owner (docs/release/production-checklist.md §6) |
| 7 | A way for a reviewer to sign in (§2). | INT-488 (#829), then the owner creates the account |
| 8 | Voice intake can be reached in a release build. It must go through the streaming path (`apps/mobile/src/lib/livekit`), which writes no file. Today `voiceEligible` requires `__DEV__` (`apps/mobile/src/app/(tabs)/visits/[visitId]/intake.tsx`), and `createLiveVoiceSession` has no caller. The notes describe voice, so they wait for it. The listing no longer does (INT-502 legal review B1). | INT-440 (#768), INT-454 (#769) |
| 9 | Release stays manual, and the public release waits. The production host receives simulated patients only until an in-country host or counsel's cross-border decision exists. Use TestFlight internal testing and the Play internal track until then. `store.config.json` pins `automaticRelease: false`. | HB-I5, HB-L11 |
| 10 | The note the patient sends reaches the clinician they choose. The notes say the app "sends it only to the clinician the user chooses". The listing promo, the store frames and the review notes may promise delivery only once it works. Until then, the review notes stay out of App Store Connect (INT-502 legal review, B4 and B5). | INT-587 (#988) |
| 11 | No patient-facing RED or urgency screen in the build sent for review, on the host it uses. The notes say the app 'does not tell the user how urgent a complaint is'. | INT-117 (`tests/legal/test_device_functions_gate.py`) |
| 12 | Document upload completes on the host the review build uses. The notes say a photographed report 'can be uploaded'; today the host has no malware scanner and upload fails closed. | the host's scanner (docs/runbooks/staging.md) |
| 13 | The submitted build ships only `tr.lproj`, verified on the uploaded build's own localizations. The App Store's Languages row is read from them (Apple QA1828), and the en-US listing says the app is in Turkish only. Build 7 predates INT-595: a local build of its sha carries `en.lproj` beside `tr.lproj`, so it is not the build to submit. | INT-595 (#1008) |

## 2 · The reviewer account

**Facts.** Sign-in is by phone number and a one-time code sent by SMS (INT-131). A release build has no
other way in: the development sign-in is compiled out (`apps/mobile/src/app/(auth)/welcome.tsx`).
An App Review or Play reviewer cannot receive a code sent to a phone they do not hold. So no
reviewer sign-in exists today. Adding one changes authentication on the production host, so it
has its own issue, INT-488 (#829), and goes to the security reviewer. This draft does not add one.

**Once that path exists, the owner creates the account:**

1. On the production host, which holds simulated patients only, create one simulated patient for
   the reviewer. It carries no real person's data. Give it one simulated visit, so the intake,
   the note and the share screens have something to show.
2. Enter the sign-in details in App Store Connect, under App Review Information, with "Sign-in
   required" ticked. For Play, enter them in the Play Console, under App content, then App access.
   They are never written into this repository, `store.config.json`, an issue, a PR or a chat.
   `store.config.json` carries no review notes while they are held (INT-502 legal review B5).
3. When the review is finished, retire the account the way the dev fixture was retired: audited,
   by id (docs/release/production-checklist.md §3).

## 3 · Emergencies: what the app does about 112

- **Builds sent for review must run with `device_functions` off** (files/06 §0.3, Stage A). Today they do not: the synthetic host serves the signed `base.life_threat` set (infra/staging/compose.yaml) and the RED layer mounts at the app root (apps/mobile/src/app/_layout.tsx), so a store build pointed at it can show a patient-facing RED with 112. INT-117 makes Stage A a tested property.
- **A fixed notice** at static points tells the user to call 112 or go to the nearest emergency
  department. It is the files/06 §7 static safety line, verbatim. It is a legal fixed string, so
  it renders only from `docs/legal/strings.yaml` with its hash. That file does not exist yet:
  counsel writes and signs it (HB-L27). Today no screen shows the line (§1 item 1).
- **The RED screen** (a pre-positioned script, triggered over the data channel; the 112 control
  never mounts on site; invariant 21) belongs to `device_functions` on. That needs a CE certificate
  or an approved clinical investigation. It must not be reachable in a build sent for review; today it is (§1 item 11).

## 4 · How the notes answer the guideline sections #825 names

Only our own facts are listed here. The stores' current wording is not recalled (HB-A12). The one
verbatim quotation the repo holds is App Review 1.4.1, in ADR-022 under `docs/adr/`.

| section named in #825 | the fact the notes state | where it is true |
|---|---|---|
| Apple 1.4.1 | no performance claim of any kind | invariant 20; ADR-022; the strict claims scan in the INT-482 tests |
| Apple 5.1.1 | camera, microphone and Health are each used for one stated purpose; in-app deletion | `intake_platform.store.facts` permission classification; `apps/mobile/src/lib/dsar/requests.ts` |
| Apple 5.1.2 | data goes only to the clinician the patient chooses; no tracking, no advertising | `privacy-answers.draft.yaml` (`product`) |
| Apple 5.1.3 | Health data is read only, never written back, and never used for advertising | `apps/mobile/src/lib/health/healthKitConnector.ts` |
| Play Health apps policy | whether it applies, and what it asks, is HB-L21(b) | `google-play.submission.draft.yaml` (`health_apps_facts`) |

## 5 · Age rating

Apple: `advisory` and `advisory_asc` in `docs/legal/store/submission/app-store.yaml`. That file has
one sourced answer for each key of the EAS schema, and one for each live App Store Connect key beyond
it. The answers that carry a note are judgements for the legal lane.

Google Play (IARC): the facts are in `google-play.submission.draft.yaml`. Counsel gives the answers
(HB-L21(c)).

## 6 · Screenshots

The App Store header and screenshots for the new design are INT-502 (#856). INT-502 captures them
from a release build, once the design stack has merged. The slots and sizes are in
`docs/store/asc/assets.yaml`, and the checks are in `scripts/store/asc_assets.py`.

INT-425 (PR #738, still open) captured the earlier design, and this draft does not copy it. Once #738
merges, `docs/store/screenshots/app-store-screenshots.json` exists. Then the INT-482 tests run its
captions through the same claims and device-claim gates as the listing. The Play frames are iPhone
captures, and #738 says to replace them with Android captures before submitting to Play.
