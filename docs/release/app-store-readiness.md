# App Store readiness: Önvizit (INT-613)

This file lists every App Store Connect item for the iOS app in
`apps/mobile` and the state each one is in on main `5d6984a7`, read on
2026-11-17. It builds on the open store lane and repeats none of it:

| PR | issue | what it holds |
|---|---|---|
| #860 | INT-495 | the served App Store listing (`docs/legal/store/listing/`), the submission answers (`docs/legal/store/submission/app-store.yaml`), `store.config.json` and the INT-495 draft writer (`scripts/store/`) |
| #1009 | INT-502 | the Turkish captures from build 7, the frame layout and renderer, and the caption draft. It is stacked on #860 |
| #1010 | INT-595 | the iOS binary declares only Turkish (`expo.locales` and `CFBundleDevelopmentRegion`) |

Each row has exactly one of five states:

- `done`: on main, and nothing is left;
- `open PR #n`: delivered on that open PR;
- `missing`: engineering work nobody has done yet;
- `needs credentials`: only the owner's Apple or Expo login can do it (HB-A3);
- `needs a human`: a person's decision or text, under the HUMAN_BLOCKERS id named.

Store requirements are cited from INT-495's dated reading of Apple's pages
(docs/evidence/INT-495.md §1 on #860, 2026-10-16, re-read by INT-502 on
2026-10-29). None is recalled from memory.

## Checklist

| # | item | state | evidence / owner |
|---|---|---|---|
| 1 | App record in App Store Connect | done | `eas.json` `submit.production.ios.ascAppId` 6814005465. TestFlight builds 3–7 were processed against it (INT-592, INT-502) |
| 2 | Bundle id `com.ariomoniri.intakemobile` | done | `app.json` `ios.bundleIdentifier`. `asc_submit.py --dry-run` checks it against the metadata and against `eas.json` |
| 3 | Name (tr, en-US): Önvizit | open PR #860 | served listing `title`. `approval:human-legal` is not recorded yet, see row 33 |
| 4 | Subtitle (tr, en-US) | open PR #860 | served listing `subtitle`, 26 characters each |
| 5 | Keywords (tr, en-US) | open PR #860 | served listing. tr is 98 of 100 bytes, en-US 80 |
| 6 | Description (tr, en-US) | open PR #860 | served listing. The en-US text says the app is Turkish only (INT-495, re-checked on #1009) |
| 7 | Promotional text (tr, en-US) | open PR #860 | served listing, re-checked by INT-502 B4 |
| 8 | Release notes (What's New) | done | Nothing to supply: App Store Connect does not offer What's New for the first version (INT-495 §1). Both locales are `null` in the metadata |
| 9 | Machine-readable metadata (deliver-shaped) with a limits, claims and source test | done | `docs/release/app-store-metadata.yaml`, `tests/release/test_app_store_metadata.py` (this PR) |
| 10 | Primary category: MEDICAL | open PR #860 | `submission/app-store.yaml` `categories`. The legal lane confirms the category |
| 11 | Age rating questionnaire | open PR #860 | `advisory` and `advisory_asc`: alcohol, tobacco or drug references and medical information are INFREQUENT_OR_MILD; every other content descriptor is NONE; healthOrWellnessTopics is true; `ageRatingOverrideV2` is EIGHTEEN_PLUS while no guardian flow exists (INT-502 B8). Notes on three answers wait for the legal lane |
| 12 | Content rights declaration | open PR #860 | USES_THIRD_PARTY_CONTENT, for the OFL fonts. The legal lane confirms |
| 13 | Privacy nutrition labels | needs a human | HB-A12 (dated snapshot of Apple's App Privacy types) and HB-L21 (a), also tracked as HB-L26a (is transmitted-never-written audio "collected"?). On main, `intake_platform.store.declaration.declaration_for_store(repo, "apple")` raises `StoreTaxonomyMissingError`. The facts module yields 14 facts, and #860's `store/answers.py` renders the sheet. ASC has no API for the labels, so the owner enters them (HB-A3) |
| 14 | Privacy policy URL | needs a human | HB-L27 (the signed `gizlilik politikası`) and HB-L21 (e). `privacy_url` is `null` |
| 15 | Support URL | needs a human | HB-L21 (e). `support_url` is `null` |
| 16 | Copyright (seller's legal entity) | needs a human | HB-L21 (e) (the seller's identity). The repo names no legal entity. `copyright` is `null` |
| 17 | Export compliance: `ITSAppUsesNonExemptEncryption` | needs a human | `app.json` declares `false`, and `expo config --type introspect` shows it in Info.plist. But the app also encrypts with `@noble/ciphers` (`src/lib/intake/offline/envelope.ts`, `src/lib/kiosk/kioskState.ts`). Whether that use is exempt is a legal determination. The owner or counsel confirms that `false` is the true answer before submission |
| 18 | Purpose string: NSMicrophoneUsageDescription | done | `src/locales/app-tr.json`, used by voice (expo-audio, LiveKit). The base Info.plist carries Expo's English default, which tr.lproj overrides. #1010 makes tr the development region |
| 19 | Purpose string: NSCameraUsageDescription | done | `app-tr.json`, used by the records screen's single-image camera capture (INT-138) |
| 20 | Purpose strings: NSHealthShareUsageDescription, NSHealthUpdateUsageDescription | done | the HealthKit plugin options and `app-tr.json` (INT-592, `tests/legal/test_ios_purpose_strings.py`). The connector requests read types only |
| 21 | Purpose string: NSFaceIDUsageDescription | missing | `expo config --type introspect` shows Expo's English default, "Allow $(PRODUCT_NAME) to use Face ID", and no Turkish string, yet `src/lib/auth/biometrics.ts` calls `authenticateAsync`. A generic purpose string is what guideline 5.1.1 asks about. A Turkish string needs the legal lane and PolicyGuard, like INT-592 |
| 22 | Purpose string: NSPhotoLibraryUsageDescription | missing | the same introspection shows Expo's English default "Allow $(PRODUCT_NAME) to access your photos", added by expo-image-picker. The app never opens the photo library (`withVoiceAudio.js`, INT-138). Remove the key, or give it a true Turkish string |
| 23 | No background audio mode | missing | the introspected Info.plist has `UIBackgroundModes: ["audio"]`. `withVoiceAudio.js` strips the mode, but expo-audio's plugin (`enableBackgroundPlayback` defaults to true) runs its mod after that and adds it back. INT-103 requires no background capture, and `apps/mobile/e2e/voice.spec.ts` checks only the plugin source, not the resolved plist. Fix: pass `enableBackgroundPlayback: false` to expo-audio, and test the introspected config |
| 24 | Languages the binary declares | open PR #1010 | INT-595: only `tr.lproj`, while `LOCALE_REGISTRY` is Turkish only |
| 25 | Screenshots, iPhone 6.9" (1320×2868) | open PR #1009 | four Turkish captures from build 7 (`docs/store/asc/captures/tr/`, provenance hashes). They carry the simulator's alpha mask, so only the framed export (`make asc-frames`) can be uploaded, and that waits for the legal lane to promote the caption draft. `asc_submit.py` refuses a file with alpha |
| 26 | Screenshots, iPhone 6.5" (1284×2778) | open PR #1009 | a target of INT-502's renderer (`frames.yaml`). Apple uses this group only when the 6.9" set is missing. The owner asked for it, so the metadata requires it |
| 27 | Screenshots, medium Dynamic Island (1206×2622) | open PR #1009 | the one group Apple's page requires (INT-495 §1). It is an INT-502 render target |
| 28 | Screenshots, iPad | done | not applicable: `ios.supportsTablet` is false |
| 29 | App Review notes | open PR #860 | `submission/app-store.yaml` `review_notes`, held by `review_notes_hold` until INT-117 Stage A, INT-488, INT-587, the release-voice owners and a malware scanner on the review host make it true. INT-488's sign-in notice is `docs/legal/store/review/app-review-signin-notes.en.md` on its branch |
| 30 | Demo sign-in for App Review (D39) | needs a human | INT-488 (issue #829) is not merged: it is on `backup/int-488-review-signin`, with no open PR. The security reviewer and the legal lane approve it, then the owner runs `review_signin.sh --generate`, `--on` and `--reveal-to-owner` and pastes the number and code into App Review Information. No agent types the code (D39). `asc_submit.py` refuses the demo-account fields |
| 31 | Sign-in test for the reviewer path | done | `scripts/release/review_signin_harness.py` and `tests/release/test_review_signin_harness.py`, against main's API in process. The no-SMS check fails closed until INT-488 lands. Plan: `docs/release/review-signin-test-plan.md` |
| 32 | Sign-in proven on a device (App Attest, real host) | needs credentials | INT-348: a TestFlight build signs in against the synthetic host with real attestation. The device steps are in the test plan |
| 33 | `approval:human-legal` recorded for each listing string | needs a human | the legal lane approved the text in synthetic scope (#828). The listing is public, so a named human records the approval in `app-store-metadata.yaml` `approvals`. `--live` refuses until then |
| 34 | HealthKit justification | open PR #860 | the review notes' Apple Health paragraph (read-only: steps, resting heart rate, sleep; never for advertising). The entitlement `com.apple.developer.healthkit` is true. Clinical Health Records is not declared (INT-224 check). Background delivery is off (`background: false`) |
| 35 | Guideline 1.4.1 (medical apps) | needs a human | no accuracy claim (invariant 20; both claim gates pass on the metadata); `device_functions` defaults off. The build sent for review must run INT-117 Stage A (a static 112 notice, no patient-facing RED on the review host). That is a hold condition with named owners |
| 36 | Guideline 5.1.1 (data collection and storage) | missing | account deletion is in the app (Profile > Your data). Still open: the privacy policy URL (row 14) and the Face ID and photo-library strings (rows 21, 22) |
| 37 | Version string | done | `app.json` `expo.version` 0.1.0, read by `asc_submit.py` |
| 38 | Build number | done | `eas.json` `cli.appVersionSource` "remote", `build.production.autoIncrement` true: EAS assigns it |
| 39 | Production build from main (`eas build -p ios --profile production`) | needs credentials | `EXPO_TOKEN` and the Apple distribution certificate (HB-A3). INT-354 still has main becoming the TestFlight build source as `todo` |
| 40 | Create the App Store version and upload metadata and screenshots | needs credentials | `scripts/release/asc_submit.py` (this PR). `--dry-run` passes with 0 invalid and 18 blocked. `--live` needs `ASC_KEY_ID`, `ASC_ISSUER_ID` and `ASC_PRIVATE_KEY` and zero blockers. It never submits for review |
| 41 | TestFlight (internal testing) | needs credentials | `eas submit -p ios --profile production` (ascAppId set). Build 6 was rejected with ITMS-90683, fixed by INT-592. Build 7 was processed |
| 42 | Pricing and availability (free; territories) | needs a human | an owner decision. The INT-495 writer refuses pricing and availability by design |
| 43 | Submit for review | needs a human | the owner, in App Store Connect, once rows 13–17, 21–23, 30, 33 and 35 are closed. No script here can submit |

## Counts

| state | rows |
|---|---|
| done | 11 |
| open PR | 14 |
| missing | 4 |
| needs credentials | 4 |
| needs a human | 10 |

`tests/release/test_app_store_readiness.py` recounts the table and fails if
these counts drift or a row uses any other state.

## What only the owner's credentials can do

- `EXPO_TOKEN`, plus the Apple Developer account's distribution certificate
  and provisioning: `eas build` (row 39) and `eas submit`/TestFlight (row 41).
- An App Store Connect API key (`ASC_KEY_ID`, `ASC_ISSUER_ID`,
  `ASC_PRIVATE_KEY`, App Manager role): `asc_submit.py --live` (row 40).
- A browser session in App Store Connect: the privacy labels (row 13, which
  has no API), App Review Information (row 30) and Submit for Review (row 43).
- A TestFlight device: INT-348's attested sign-in (row 32).
