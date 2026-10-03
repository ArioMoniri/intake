# Liquid Glass: Apple's guidance, applied to the chat stage (INT-466)

Read on 3 Oct 2026, from Apple's documentation and the Expo docs, before any further glass code. Quotes are short, and everything else is summarised.

## What Apple says

1. **Glass is the navigation and controls layer, floating above content.** "Don't use Liquid Glass in the content layer." (HIG, Materials.) "Liquid Glass is best reserved for the navigation layer that floats above the content" (WWDC25 *Meet Liquid Glass*). The one exception: transient controls such as sliders and toggles may take the glass look *while activated*.
2. **Use it sparingly.** "Avoid overusing Liquid Glass effects" on custom controls, and keep it for the most important functional elements (*Adopting Liquid Glass*). Too many effects on screen costs performance, so group them in one `GlassEffectContainer` (*Applying Liquid Glass to custom views*).
3. **Regular, not clear.** Regular is adaptive and legible over any content. Clear is permanently more transparent, and only for elements over media-rich content. It needs a dimming layer (35 % dark over bright content), and it is never mixed with regular.
4. **No glass on glass.** Stacking glass on glass looks cluttered. An element on top of glass is a fill, transparency or vibrancy, not a second glass (*Meet Liquid Glass*).
5. **Tint only for emphasis.** Colour belongs on the glass of primary actions and status, applied "to the background rather than to symbols or text". Do not colour the backgrounds of several controls (HIG, Color). "Avoid tinting all your elements" (*Meet Liquid Glass*).
6. **Merging and morphing.** Inside a `GlassEffectContainer`, neighbouring shapes blend once they come within its spacing. `glassEffectID` morphs one shape into another. `interactive` makes a custom control react to touch.
7. **Scroll edge effects replace dividers.** Use one per view, soft on iOS, and only where floating UI meets content. Remove background colours from custom bars (WWDC25 *Get to know the new design system*).
8. **Accessibility is built in for system glass.** Reduce Transparency makes glass frostier, Increase Contrast makes it black or white with a border, and Reduce Motion removes elastic effects. Custom elements must still be tested under each.
9. **Motion must serve a purpose.** Avoid it on frequent interactions, make it optional, and never use it as the only signal (HIG, Motion). Avoid sustained oscillation near 0.2 Hz (the HIG's visionOS note).
10. **Typography.** Use Dynamic Type styles. Large Title is 34 pt and bold when emphasised. SF Pro Rounded suits soft, rounded UI. Avoid thin weights, and make layouts adapt at every size (HIG, Typography).

## What it means for the chat screen

| Element | Layer | Treatment |
|---|---|---|
| Back button and the "Not oluşuyor" pill | Navigation | The native bar. The back button is system glass, and the pill is a bar item, so iOS 26 gives it glass and groups it with the back button. Soft scroll edge at the top |
| Composer field and its control | Controls | Two regular-glass shapes in one `GlassContainer`, so they merge: a field capsule and a round control. Send is tinted because it is the primary action; the mic is untinted. Interactive |
| Turn actions ("Onaylayın", "Bitirdim", "Düzeltmeyi söyleyin") | Controls | Regular glass capsules in the same container. Only the primary one is tinted |
| Question text | Content | **No glass.** Large rounded text sits directly on the backdrop |
| Agent and patient messages | Content | **No glass.** Solid fills, as in Messages: the patient's in the accent, the agent's in the card colour |
| Answer cards (chips) | Content | **No glass**, following Apple rather than the owner's request. Solid cards: the selected one is filled with the accent and checked, and an unselected one shows an outline circle |
| Voice orb | A status indicator in the floating dock | The gradient sphere is content-like decoration, under a clear lens. It is the dock's only glass, with no glass behind it and no text on it. It moves only while speaking, listening or thinking |
| Backdrop | Behind everything | A still gradient wash. Under Reduce Transparency it becomes a solid fill |
| Bottom edge | Where content meets the dock | One soft fade from the backdrop colour, our stand-in for the bottom scroll edge effect |

**Where this departs from the earlier request:** Apple says content stays off glass, so answer cards and the question panel stay solid. The glass goes on the bars and controls instead, and those now merge in one container.

## Sources

- HIG Materials: https://developer.apple.com/design/human-interface-guidelines/materials
- HIG Color: https://developer.apple.com/design/human-interface-guidelines/color
- HIG Motion: https://developer.apple.com/design/human-interface-guidelines/motion
- HIG Typography: https://developer.apple.com/design/human-interface-guidelines/typography
- Adopting Liquid Glass: https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass
- Applying Liquid Glass to custom views: https://developer.apple.com/documentation/swiftui/applying-liquid-glass-to-custom-views
- WWDC25 Meet Liquid Glass: https://developer.apple.com/videos/play/wwdc2025/219/
- WWDC25 Get to know the new design system: https://developer.apple.com/videos/play/wwdc2025/356/
- Expo GlassEffect: https://docs.expo.dev/versions/latest/sdk/glass-effect/
- Expo UI (SwiftUI): https://docs.expo.dev/versions/latest/sdk/ui/swift-ui/
