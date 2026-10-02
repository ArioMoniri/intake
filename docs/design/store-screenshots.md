# Store screenshots: design choices (INT-425)

| | |
|---|---|
| Status | **Draft for owner and legal review** (store listing is INT-146, `approval:human-legal`). Nothing here is uploaded. |
| Tool | The owner-requested [app-store-screenshots](https://github.com/ParthJadhav/app-store-screenshots) skill (MIT), template pinned at `8bd7520`. |
| Source | `docs/store/screenshots/`: the project file, the captures, the brand icon and the two build tools. |
| Exports | `docs/store/screenshots/export/`: iPhone 6.9", 6.5", 6.3" and 6.1"; Google Play phone; the Play feature graphic. |

## What each frame says

One benefit per frame, in the order a patient meets them. Each headline is two short lines of B1 Turkish in the `siz` register, with no claim about results and no health promise.

| # | Capture (real app, refreshed UI) | Eyebrow | Headline (tr) | Headline (en, held for a bilingual listing) |
|---|---|---|---|---|
| 1 | Bugün: the next visit and its preparation | Önvizit | Muayeneye hazır gidin. | Arrive at your visit ready. |
| 2 | Karşılıklı konuşma: a spoken turn and its transcript | Sesle ya da yazarak | Anlatın, biz not alalım. | You talk, we take notes. |
| 3 | Typed step after the INT-433 redesign: the thin progress bar and "Soru 1 / 10", the patient's own words in the filled field, a checked capsule chip, glass bars | Adım adım | Her seferde tek soru. | One question at a time. |
| 4 | Review: sections with "Paylaşılıyor" and "Düzenleyin" | Hekiminize gidecek not | Paylaşılanı siz seçin. | You choose what is shared. |
| 5 | Review: earlier facts waiting for the patient's answer | Önceki kayıtlar | Eski bilgiler size sorulur. | Old details are checked with you. |
| 6 | Visit: the note status ladder after sending | Not durumu | Notunuzun durumunu görün. | See where your note is. |
| 7 | Share link: "Yalnızca bu ekranda" | Paylaşım bağlantısı | Hekiminize gösterin. | Show it to your doctor. |
| 8 | Görünüm in dark mode, larger text: the full size ladder with the chosen step, clear of the tab rail | Görünüm | Yazı boyu size göre. | Text sized for you. |

## Why it looks like this

- **The app is the picture.** Every frame is a full simulator capture of the refreshed UI (INT-422, INT-423) in a complete device frame. Nothing inside a phone was drawn, edited or mocked.
- **One grid, one type system.** The eyebrow and headline sit flush-left on an 8 % margin, and the phone sits centred below them at the same size on every frame. Apple frames use SF Pro, Android frames use Roboto, at one headline weight with tight display leading.
- **Two colours from the app's own tokens.** The ground is `systemGroupedBackground` `#F2F2F7` and the eyebrow is the accent `#0B7366`, both from `apps/mobile/src/lib/theme.ts`. The appearance frame inverts to the app's dark ground `#000000` with the dark accent `#4FC3B1`, to show dark mode honestly.
- **No decoration.** There are no gradients, blooms, glass cards, 3D shapes, stock people or badges. The template's iPhone bezel is desaturated to a neutral grey, and its geometry is unchanged.
- **Brand.** The first frame carries the current V-mark icon (INT-420) and the name Önvizit. The retired name appears nowhere in the copy or the captures.
- **No case transform.** Eyebrows are sentence case, because uppercasing Turkish breaks `i/İ` and `ı/I`.

## Data in the captures

Only the synthetic dev account (`apps/mobile/src/lib/dev/accounts.ts`) and typed simulated-patient answers were used. For the capture session only, never committed, the fixture's real hospital names were replaced with "Örnek Hastanesi" and the visit moved to an upcoming date. The voice frame was made with local stubs that answer the dev lanes' health check and return silence. No patient spoke and no audio was recorded. No frame shows a demo-account label, a RED or crisis screen, or a real person.

## What the owner still has to do

1. ~~Approve the Turkish headlines.~~ Done: the owner approved the Turkish store copy on 2 Oct 2026, recorded verbatim in docs/evidence/INT-425.md. INT-146's `approval:human-legal` label is not changed by that record. Turkish is the store copy. To publish the English set too, add `"en"` to `locales` and export again.
2. **Android:** no emulator was available, so the Play set frames the iOS captures in an Android device. Before submitting to Play, replace `captures/` with Android emulator or device captures of the same eight screens and export again.
3. Upload the PNGs to App Store Connect (the 6.9" set is enough, and Apple scales it down) and to the Play Console with the feature graphic.
4. Voice frame: a text caret is visible in the composer. Replace the capture if you want it gone.

## Recapture after INT-433 (3 Oct 2026)

The owner found the question screen in frame 3 not native enough (the dot row, the outlined box and chips). INT-433 (#740) redesigned it, and that branch is merged here so the frame shows the shipped screen. Two captures were replaced:

- **Frame 3:** the redesigned question screen, from the same flow and dev account, with a simulated-patient answer.
- **Frame 8:** the INT-425 capture had the floating tab rail over the selected text-size row. The new capture is scrolled so the whole ladder and the chosen step sit clear of the rail.

The headlines, eyebrows, grid, theme and the other six captures are unchanged. The export was re-run with the same editor build, pressing **Export bundle** headlessly. The six unchanged frames came out byte-identical at every size, and only frames 3 and 8 changed, in every iPhone size and the Play phone size.

## How to regenerate

```bash
git clone https://github.com/ParthJadhav/app-store-screenshots /tmp/ass && git -C /tmp/ass checkout 8bd7520
python3 docs/store/screenshots/tools/gen_project.py iphone      # or android / feature-graphic
python3 docs/store/screenshots/tools/build_editor.py /tmp/ass /tmp/onvizit-editor
cd /tmp/onvizit-editor && pnpm install --ignore-workspace && pnpm dev
```

Open the editor and press **Export bundle**. It renders the deck named in the project file. Unzip the bundle into `docs/store/screenshots/export/`.
