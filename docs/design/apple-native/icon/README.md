# Önvizit app icon: a layered proposal for Icon Composer

| | |
|---|---|
| Status | **Proposal.** Nothing in `apps/mobile/assets` or `app.json` changes on this branch, because the rebrand is owner-held. |
| Grounding | The owner's Önvizit mark (a teal field and a white V with rounded ends, committed by INT-420 as `apps/mobile/assets/images/onvizit-logo.svg`) and the app's own tokens (`lib/theme.ts`). HIG and Icon Composer rules are in [../research.md §9](../research.md). |
| Why now | Until INT-420 the iOS icon was the **Expo template**: `app.json → ios.icon` pointed at `assets/expo.icon`, which holds the Expo "A" on a blue gradient (research A5). INT-420 dropped that override, so iOS now builds from the owner's flat V-logo `icon.png`. Icon Composer is how an iOS 26 app gets the system's glass treatment and its dark, clear and tinted appearances. |

![The four appearances, flat previews](previews/sheet.png)

*Left to right: default, dark, tinted, clear. These are **flat approximations** made for review. The system adds specular highlights, refraction and the real mask. Check the final look in Icon Composer's preview and on a device (see "Owner steps").*

## Files

| File | What it is | Goes into Icon Composer? |
|---|---|---|
| `10-arm-left.svg` | Foreground layer 1 (back): the left arm of the V, as a filled capsule | **Yes**, as group 1 |
| `20-arm-right.svg` | Foreground layer 2 (front): the right arm, as a filled capsule | **Yes**, as group 2 |
| `00-background.svg` | The default background gradient, for reference | **No.** Set the background as the icon's **Fill** in Icon Composer (values below). Apple's export guidance says to leave background colours and gradients out of the layers. |
| `mark-flat.svg` | Flat composite of background and both arms | No. Use it for marketing, the web favicon and, later, the Android adaptive icon (spec F5). |
| `previews/*.png` | Flat review renders at 512 px, plus `sheet.png` | No |

Every layer is a 1024×1024 square with no mask, holds vector shapes only (no strokes, text, effects or raster), and is numbered back to front, as Apple's export rules ask.

## The design, in four decisions

1. **It keeps the owner's mark.** It uses the same V, the same rounded ends, the same stroke weight (104 at 1024) and the same teal. It is re-centred on the canvas and scaled 1.12× so it holds at home-screen size: about 53 % of the width, where the flat mark used 48 %.
2. **One stroke becomes two overlapping filled shapes.** HIG asks for *"filled, overlapping shapes"* and for varied opacity in foreground layers to *"increase the sense of depth"*. Each arm is its own Icon Composer group, so the system renders them as two glass layers. Where they cross, at the valley, the front arm refracts the back one. Read as a mark, the point of the V is where two paths meet: the patient's account and the clinician's reading arriving at one visit.
3. **No baked effects.** The files carry no highlight, shadow, glow or bevel. Icon Composer and the system supply those, and they update per appearance. Baked-in effects stay static and fight the system's (HIG App icons).
4. **No borrowed glyphs.** The mark is original geometry: two capsules. It does not use, trace or approximate any SF Symbol. SF Symbols may not appear in app icons or logos (research §3).

## Colours per appearance

| Appearance | Background (Fill) | Group 1: left arm | Group 2: right arm |
|---|---|---|---|
| Default | Gradient, top `#12A597` → bottom `#0B7468` (from the owner's `#0E9C8F` toward the app's primary `#0F7B6C`) | `#FFFFFF`, 100 % | `#FFFFFF`, 88 % |
| Dark | Gradient, top `#1C1B18` → bottom `#0F0E0C` (the app's dark surface and ground) | `#6CCFC1`, 100 % | `#4FA79A` (the app's dark-mode primary), 92 % |
| Mono (Clear and Tinted) | Let the system derive it | `#FFFFFF`, 100 % | `#FFFFFF`, 78 % |

The right arm stays a little lighter than the left in every appearance. That keeps the overlap readable once tinted or clear glass flattens the colour to one hue.

## Owner steps (macOS)

Icon Composer ships with Xcode 26 (*Xcode › Open Developer Tool › Icon Composer*) and as a standalone download from [developer.apple.com/icon-composer](https://developer.apple.com/icon-composer/). The standalone page lists macOS Tahoe 26.4 or later. The steps follow Apple's [Creating your app icon using Icon Composer](https://developer.apple.com/documentation/Xcode/creating-your-app-icon-using-icon-composer).

1. **New file.** Open Icon Composer, then *File › Save* as `onvizit.icon`.
2. **Platforms.** Click the Document button and keep **iOS** (the app is iPhone-only, `supportsTablet: false`).
3. **Import.** Drag `10-arm-left.svg` and `20-arm-right.svg` from Finder into the sidebar. Each becomes a layer. Put each layer in its **own group**, with group 1 holding the left arm and group 2 the right arm. Icon Composer orders groups alphabetically, and the numeric prefixes keep that order back to front.
4. **Background.** Select the icon in the sidebar. Under *Style › Color*, choose **Gradient** and set From `#12A597` and To `#0B7468`, then drag the canvas dots so the gradient runs top to bottom.
5. **Layer colours and opacity.** Select each layer and set its fill and opacity from the Default row of the table.
6. **Liquid Glass per group.** Start from Icon Composer's defaults: Specular **Automatic**, Refraction on, and Shadow **neutral**. On **group 2** (the right arm), give Translucency a moderate value, so the overlap at the valley reads as glass over glass. Leave Blur at its default. Adjust by eye in the canvas preview.
7. **Dark.** Switch the canvas to **Dark**. For the background fill and each layer's colour, choose *Vary for Dark* and enter the Dark row.
8. **Mono.** Switch to **Mono** and check both **Clear** and **Tinted** (*Options* toggles Tinted and picks a tint colour). Set the layer colours from the Mono row, and confirm the overlap is still visible at the smallest preview size.
9. **Save**, then copy `onvizit.icon` to `apps/mobile/assets/onvizit.icon`.
10. **Point Expo at it.** In `app.json`, set `expo.ios.icon` to `"./assets/onvizit.icon"` (INT-420 removed the old `./assets/expo.icon` override, so the key is absent until then). Expo SDK 57 passes a `.icon` straight to Xcode. Xcode then uses it instead of an `AppIcon` asset catalog, and generates flattened images for iOS versions before 26.
11. **Build and look.** Make a development build (`eas build --profile development` or `npx expo run:ios`) on an **iOS 26 or later device**. Long-press the Home Screen, open *Edit › Customize*, and check **Default, Dark, Clear and Tinted**, in both light and dark Clear/Tinted. Save a screenshot of each to `docs/design/apple-native/evidence/` (see [../evidence.md](../evidence.md), device step D1).
12. **Retire the template.** Delete `assets/expo.icon`, which nothing references since INT-420. `icon.png` is the owner's flat V-logo since INT-420; the Android adaptive layers and the splash are still Expo template art on `main`, and should be regenerated from `mark-flat.svg` (spec F5).

## Checks before adopting

- At 60 px (the Home Screen at 3×, 180 px physical), is the V still legible in Tinted, with the overlap visible and not reading as a smudge?
- In Clear, over a busy wallpaper, does the mark hold its edge? If not, raise group 2's opacity before touching the background.
- Put Default beside the Files, Health and Calendar icons. It should sit with system icons, not shout. HIG asks for dark and tinted variants that sit naturally beside the system's own.
