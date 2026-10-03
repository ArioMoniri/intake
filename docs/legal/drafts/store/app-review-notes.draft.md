> TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force

# Önvizit — App Review and Play review: what the owner needs (INT-482)

Prepared on 2026-10-04 by a drafting agent for the legal lane (GitHub #825). It is pending
legal-lane review. This file is for the owner and the reviewer of this PR. The text the store
reviewers read is in `app-store.submission.draft.yaml` (`review_notes`) and in
`google-play.submission.draft.yaml` (`app_access_instructions`). Nothing here is submitted.

## 1 · Do not submit until each of these holds

Each item names who owes it. App Review reads the notes as true on the day of submission, so a
missing item is a reason to wait. It is not something to describe around.

| # | what must hold | owed by |
|---|---|---|
| 1 | The app shows the fixed 112 notice at its static points. Its text is the files/06 §7 static safety line, rendered from the signed `docs/legal/strings.yaml`. The notes and the listing say that the app shows it. Today the app does not. | INT-117 (static 112 text at fixed points), HB-L27 (the fixed strings) |
| 2 | A signed privacy policy (`gizlilik`) and the URL it is served at. The privacy link binds to its sha256 (`intake_platform.store.eas_metadata.bind_legal_link`). | HB-L27, HB-L21(e) |
| 3 | The seller's legal entity, the support contact and the KVKK contact. | HB-L21(e) |
| 4 | Whether microphone audio counts as *collected* on each store's form. This answer fills the voice row of `privacy-answers.draft.yaml`. | HB-L21(a) |
| 5 | The app is called Önvizit in the binary, not only on the store. | INT-420 (PR #729) |
| 6 | Phone sign-in works on the production host: an SMS vendor with a signed DPA, and the App Attest team id. | owner (docs/release/production-checklist.md §6) |
| 7 | A way for a reviewer to sign in (§2). | owner decision, then an engineering issue |
| 8 | Release stays manual, and the public release waits. The production host receives simulated patients only until an in-country host or counsel's cross-border decision exists. Use TestFlight internal testing and the Play internal track until then. `store.config.json` pins `automaticRelease: false`. | HB-I5, HB-L11 |

## 2 · The reviewer account

**Facts.** Sign-in is by phone number and a one-time code sent by SMS (INT-131). A release build has no
other way in: the development sign-in is compiled out (`apps/mobile/src/app/(auth)/welcome.tsx`).
An App Review or Play reviewer cannot receive a code sent to a phone they do not hold. So no
reviewer sign-in exists today. Adding one changes authentication on the production host. That
needs its own issue and the security reviewer. This draft does not add one.

**Once that path exists, the owner creates the account:**

1. On the production host, which holds simulated patients only, create one simulated patient for
   the reviewer. It carries no real person's data. Give it one simulated visit, so the intake,
   the note and the share screens have something to show.
2. Enter the sign-in details in App Store Connect, under App Review Information, with "Sign-in
   required" ticked. For Play, enter them in the Play Console, under App content, then App access.
   They are never written into this repository, `store.config.json`, an issue, a PR or a chat.
   `store.config.json` carries the review notes and nothing else from the `review` block.
3. When the review is finished, retire the account the way the dev fixture was retired: audited,
   by id (docs/release/production-checklist.md §3).

## 3 · Emergencies: what the app does about 112

- **Builds sent to the stores run with `device_functions` off** (files/06 §0.3, Stage A). In that
  mode the app gives no automated urgency advice and no automated severity label. Answers that
  match a red-flag rule reach the clinician as the patient's own report, and triage runs only in
  shadow. INT-117 is the issue that makes this a tested property.
- **A fixed notice** at static points tells the user to call 112 or go to the nearest emergency
  department. It is the files/06 §7 static safety line, verbatim. It is a legal fixed string, so
  it renders only from `docs/legal/strings.yaml` with its hash. That file is unsigned (HB-L27), and
  today no screen shows the line (§1 item 1).
- **The RED screen** (a pre-positioned script, triggered over the data channel; the 112 control
  never mounts on site; invariant 21) belongs to `device_functions` on. That needs a CE certificate
  or an approved clinical investigation. It is not part of a store build, and the notes do not
  describe it.

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

Apple: `advisory` in `app-store.submission.draft.yaml`. It has one sourced answer per key of the EAS
schema, and two answers carry a note for the legal lane. Google Play (IARC): the facts in
`google-play.submission.draft.yaml`. Counsel gives the answers (HB-L21(c)).

## 6 · Screenshots

INT-425 builds them (PR #738, still open), and this draft does not copy them. Once #738 merges,
`docs/store/screenshots/app-store-screenshots.json` exists. Then the INT-482 tests run its captions
through the same claims and device-claim gates as the listing. The Play frames are iPhone captures.
#738 says to replace them with Android captures before submitting to Play.
