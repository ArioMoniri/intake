# Google Play — deferred, and what it will need (INT-496)

**Status: deferred.** The owner said on 16 Oct 2026: *"dont do google for now"* (GitHub #847). No
Play submission, Play API client or Play listing file is built. This page lists every item Play
will need, and who or what owns each one. When Play is picked up, start here.

Nothing below changes the iOS work. INT-495 (#846) fills App Store Connect. The Android build
profile already exists in `apps/mobile/eas.json`: production builds an app bundle, and submits to
the internal track.

## 1 · Accounts and credentials (owner only)

| item | what it is | where it comes from |
|---|---|---|
| Play Console developer account and the app record `com.ariomoniri.intakemobile` | the account and the app entry | owner (HUMAN_BLOCKERS HB-A3) |
| **service-account JSON** for the Play Developer API | lets `eas submit --platform android` upload a build; access is granted per app in the Play Console | owner: create it in Google Cloud, grant it in the Play Console, and keep it outside the repo. Like the App Store key, it is supplied at submit time from the owner's machine or EAS, and is never committed or pasted in chat (`docs/release/production-checklist.md` §5) |
| Play Integrity | the Android half of attestation; it fails closed until it is configured | owner (HB-A3) |

## 2 · Store listing

| item | source in the repo | notes |
|---|---|---|
| title, short description, full description (Turkish, English) | `docs/legal/drafts/store/google-play.tr.draft.yaml`, `docs/legal/drafts/store/google-play.en-US.draft.yaml` (INT-482) | Same source as the App Store text, and a test holds them equal. The Play limits are 30 / 80 / 4,000 characters (support.google.com/googleplay/android-developer/answer/9859152, retrieved 2026-10-16); the drafts are within them. |
| app icon | the INT-495 app icon export | 512 × 512, 32-bit PNG (support.google.com/googleplay/android-developer/answer/9866151, retrieved 2026-10-16) |
| **feature graphic** | not made yet | 1024 × 500, JPEG or 24-bit PNG with no alpha (answer/9866151, retrieved 2026-10-16). INT-425 (PR #738) built one from the earlier design, so it must be redone from the new one. |
| **phone screenshots** | not captured yet | At least two are needed to publish, and up to 8 per device type. JPEG or 24-bit PNG with no alpha; each side between 320 and 3840 px, and the long side at most twice the short side. Four portrait shots at 1080 × 1920 or larger are recommended (answer/9866151, retrieved 2026-10-16). |
| contact e-mail, privacy-policy URL | seller identity and the signed `gizlilik` document | HB-L21(e), HB-L27. Never a stand-in URL. |

**Reusing the iOS assets (INT-495).** The listing copy is shared already. The screenshots are not:
iPhone frames show iOS chrome. PR #738 itself says its Play frames were iPhone captures and must be
replaced with Android captures. The App Store product-page header (21:9) has no Play equivalent,
so the feature graphic is its own asset. Take every Android capture from a release build on an
Android device or emulator, with the same rules as iOS: simulated patients only, and no
development fixture, development chrome or demo labels.

## 3 · Forms in the Play Console

| form | source in the repo | still open |
|---|---|---|
| **Data safety** | `docs/legal/drafts/store/privacy-answers.draft.yaml`, derived by `packages/intake_platform/src/intake_platform/store/answers.py`. It has one row per inventory fact, including `flow:phone_sign_in` and `flow:voice_audio`. | The Data safety vocabulary comes from a committed snapshot of the form (HB-A12) through `intake_platform.store.declaration`. Whether audio counts as collected is HB-L21(a). The SMS vendor and its DPA are INT-358. |
| **IARC** content rating | the facts in `docs/legal/drafts/store/google-play.submission.draft.yaml` (`content_rating_facts`) | The answers belong to the legal lane (HB-L21(c)), and the questionnaire wording is not recalled (HB-A12). |
| Health apps declaration | `health_apps_facts` in the same file | Whether the policy applies is HB-L21(b). |
| App access (reviewer sign-in) | `app_access_instructions` in the same file | A reviewer cannot receive an SMS code. The reviewer sign-in path is INT-488 (#829). |
| Target audience, ads, government app, financial features | not drafted | Answer from the same sourced facts when Play is picked up. The privacy sheet's `product` rows already say there is no advertising and no tracking. |

## 4 · Before anything reaches Play

The same conditions apply as for iOS (`docs/legal/drafts/store/app-review-notes.draft.md` §1):

- INT-117 renders the static 112 notice;
- voice is reachable in a release build (INT-440, INT-454);
- a reviewer can sign in (INT-488);
- the HB-L21 items are answered.

The host receives simulated patients only (HB-I5, HB-L11), so the internal testing track is the
only track until that changes.
