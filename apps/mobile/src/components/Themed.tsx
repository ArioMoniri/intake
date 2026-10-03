/**
 * Themed primitives (INT-130, premium pass INT-193): the only place
 * components read the palette, fontScale and type roles. Screens compose
 * these; none of them hardcode a colour or a font size, so the 02 §5.2
 * rules (single accent, dynamic type, no ALL-CAPS transforms) hold by
 * construction. Hero and title text carry the serif display face (the
 * Oura/Tiimo signature); light-mode cards float on a soft wide shadow,
 * dark mode separates tonally.
 */
import { type ComponentProps, type ReactNode, type Ref } from "react";
import {
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
  useColorScheme,
  useWindowDimensions,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from "react-native";
import { Stack } from "expo-router";
import { SafeAreaView, type Edge } from "react-native-safe-area-context";

import { getLocale } from "@/lib/i18n";
import {
  CTA_MIN_HEIGHT,
  effectiveFontScale,
  isLargeText,
  resolveScheme,
} from "@/lib/prefs/appearance";
import { useAppearance } from "@/lib/prefs/AppearanceProvider";
import {
  fonts,
  lineHeight,
  motion,
  palette,
  radius,
  scaledSize,
  shadow,
  spacing,
  type ColorScheme,
  type ThemeColors,
  type TypeRole,
} from "@/lib/theme";

/**
 * BCP-47 tags for the two catalogs (INT-144; WCAG 2.2 SC 3.1.1, BK24).
 *
 * A Turkish sentence read by an English voice is not "accented" — "İzinleriniz"
 * comes out unintelligible. iOS honours `accessibilityLanguage` per element,
 * which matters here because the locale is an in-app switch and need not match
 * the device's. Android has no per-node equivalent in React Native and picks
 * the TTS locale itself: that half is a real gap, recorded as such in
 * docs/compliance/accessibility-conformance.md rather than claimed.
 */
const SPEECH_LANGUAGE = { tr: "tr-TR", en: "en-GB" } as const;

// The faces are guaranteed loaded before the tree renders (root layout gates
// on useFonts); the platform serif remains only as a defensive fallback.
const DISPLAY_FONT = fonts.display ?? Platform.select(fonts.displayFallback);

/**
 * Sans roles carry Inter (design pass 4, Oura register). Custom fonts on iOS
 * do not synthesize weights, so the effective fontWeight in the flattened
 * style picks the loaded family and the weight itself is dropped.
 */
function sansFamily(weight: TextStyle["fontWeight"]): string {
  switch (weight) {
    case "600":
    case "700":
    case "bold":
    case 600:
    case 700:
      return fonts.sansSemiBold;
    case "500":
    case 500:
      return fonts.sansMedium;
    default:
      return fonts.sans;
  }
}

/**
 * The scheme to render (INT-260). This is the ONLY place the app asks the OS,
 * so the patient's own Tema choice has somewhere to be applied; every other
 * component takes this hook. `useColorScheme` imported anywhere else is a
 * control that silently does nothing on that surface, which is why
 * e2e/appearance.spec.ts pins the import site.
 */
export function useScheme(): ColorScheme {
  const os = useColorScheme();
  const { prefs } = useAppearance();
  return resolveScheme(prefs.theme, os);
}

export function useTheme(): ThemeColors {
  return palette[useScheme()];
}

/**
 * The app's text scale (INT-260).
 *
 * Redefined in place rather than joined by a sibling hook, and the stored step
 * REPLACES the OS value instead of multiplying it. Two multipliers is exactly
 * what `allowFontScaling={false}` below exists to prevent, and composition
 * under theme.ts's [0.5, 2.0] clamp would hand a patient already at OS 2.0 a
 * control where every step renders the same size. `scaledSize`, `lineHeight`,
 * the clamp and `AppText` are untouched: one input changed, so "text scales
 * once, never twice" stays true by construction.
 */
export function useFontScale(): number {
  const os = useWindowDimensions().fontScale;
  const { prefs } = useAppearance();
  return effectiveFontScale(prefs.textStep, os);
}

type StackScreenOptions = NonNullable<ComponentProps<typeof Stack.Screen>["options"]>;

/**
 * Oura-register top bar for pushed screens (design pass 5): centred
 * body-sized semibold sans title, "‹" back with no label, ground-coloured and
 * shadowless so it reads as part of the page, not chrome. Screens that use
 * it drop the top safe edge — the header owns that inset.
 *
 * INT-260: the size was a hardcoded 17 while react-navigation's own
 * `allowFontScaling` defaulted ON — so six screen titles ignored the app's
 * scale and doubled the OS one. Both halves are fixed together: sizing from
 * `scaledSize` without turning the platform multiplier off is the doubled
 * scale a11y.spec.ts already forbids for TextInput.
 */
export function useStackHeader(): (title: string) => StackScreenOptions {
  const theme = useTheme();
  const fontScale = useFontScale();
  return (title: string) => ({
    headerShown: true,
    title,
    headerTitleAlign: "center",
    headerTitleStyle: {
      fontFamily: fonts.sansSemiBold,
      fontSize: scaledSize("body", fontScale),
      color: theme.ink,
    },
    headerTitleAllowFontScaling: false,
    headerStyle: { backgroundColor: theme.background },
    headerShadowVisible: false,
    headerTintColor: theme.ink,
    headerBackButtonDisplayMode: "minimal",
  });
}

interface AppTextProps {
  role?: TypeRole;
  color?: keyof ThemeColors;
  style?: StyleProp<TextStyle>;
  /**
   * Mark this line as a heading (INT-144; WCAG 2.2 SC 1.3.1, Ministry BK5).
   *
   * Type size is a sighted cue only — a 34 pt serif line and a 13 pt caption
   * arrive at a screen reader identically unless the structure is declared.
   * Setting `heading` puts the line in VoiceOver's and TalkBack's heading
   * rotor, which is how a non-sighted patient skips a screen instead of
   * reading every element of it. It lives on AppText rather than in each
   * screen so a screen cannot spell the platform prop wrong.
   */
  heading?: boolean;
  /**
   * Announce this line when it appears or changes — errors and status lines
   * that a sighted user notices by their position and colour. `assertive`
   * interrupts (a validation error the patient must fix before continuing);
   * `polite` waits for a gap (a background status).
   *
   * This is the ANDROID half only. Set it through `AnnouncedText`
   * (src/components/Announced.tsx), which also posts the iOS announcement;
   * e2e/a11y.spec.ts fails on a `live` set anywhere else (INT-362).
   */
  live?: "polite" | "assertive";
  /**
   * What a screen reader says for this line when it differs from the visible
   * words — an error line is spoken with "Hata" first (SC 3.3.1). Set only by
   * `AnnouncedText`, so the live region, the VoiceOver announcement and the
   * element's own name all say the same thing.
   */
  spokenAs?: string;
  /** The line can be selected and copied (INT-465: the 112 number, files/02 §5.3). */
  selectable?: boolean;
  children: ReactNode;
}

export function AppText({
  role = "body",
  color = "ink",
  style,
  heading = false,
  live,
  spokenAs,
  selectable = false,
  children,
}: AppTextProps) {
  const theme = useTheme();
  const fontScale = useFontScale();
  const display = role === "display" || role === "hero" || role === "title";
  const flat: TextStyle = StyleSheet.flatten([
    {
      color: theme[color],
      fontSize: scaledSize(role, fontScale),
      lineHeight: lineHeight(role, fontScale),
    },
    display ? { fontFamily: DISPLAY_FONT } : null,
    style,
  ]);
  if (!display) {
    flat.fontFamily = sansFamily(flat.fontWeight);
    delete flat.fontWeight;
  }
  return (
    // Sizes come from scaledSize; RN's own multiplier is disabled so the
    // 2.0 cap (layout-survival, 02 §8.2) is applied in exactly one place.
    <Text
      allowFontScaling={false}
      accessibilityRole={heading ? "header" : live !== undefined ? "alert" : undefined}
      accessibilityLiveRegion={live}
      accessibilityLabel={spokenAs}
      accessibilityLanguage={SPEECH_LANGUAGE[getLocale()]}
      selectable={selectable}
      style={flat}
    >
      {children}
    </Text>
  );
}

/**
 * Screens under the floating tab rail (design pass 4) drop the bottom safe
 * edge so content scrolls UNDER the pill to the physical edge (Oura chrome);
 * they pad their scroll content with `useTabBarClearance()` instead.
 */
export const RAIL_EDGES: readonly Edge[] = ["top", "left", "right"];

export function Screen({
  children,
  style,
  edges,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  edges?: readonly Edge[];
}) {
  const theme = useTheme();
  // No layout direction is set: every shipped locale is left-to-right (React
  // Native's default), and right-to-left layout waits for INT-253's P3 audit
  // (owner decision 2026-09-26, INT-346).
  return (
    <SafeAreaView
      edges={edges as Edge[] | undefined}
      style={[styles.screen, { backgroundColor: theme.background }, style]}
    >
      {children}
    </SafeAreaView>
  );
}

interface CardProps {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  /** Soft semantic wash behind the content (Oura's tinted cards). */
  wash?: "none" | "primary";
}

export function Card({ children, style, wash = "none" }: CardProps) {
  const scheme = useScheme();
  const theme = palette[scheme];
  const depth = shadow[scheme];
  // INT-260: at the large-text scale a card gives its MEASURE priority over
  // its air. 00 §2's own arithmetic is that a long Turkish word can need more
  // width than a 200 % line has, and React Native breaks a word it cannot fit
  // — "İç Hastalıkları" rendered as "Hastalıkla / rı" on the visit card, which
  // is the mid-word break that ruling exists to prevent. Sixteen points back
  // from each side is the cheapest width there is, and unlike shrinking the
  // text it takes nothing away from the patient who chose the size.
  const tight = isLargeText(useFontScale());
  return (
    <View
      style={[
        styles.card,
        tight ? styles.cardTight : null,
        {
          backgroundColor: wash === "primary" ? theme.primarySoft : theme.surface,
          // Dark cards are borderless — tonal surface against near-black
          // ground carries the separation (Oura register, design pass 3);
          // light keeps the hairline under its soft shadow.
          borderColor: scheme === "dark" ? "transparent" : theme.border,
          shadowColor: depth.color,
          shadowOpacity: depth.opacity,
          shadowRadius: depth.radius,
          shadowOffset: { width: 0, height: depth.offsetY },
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

/**
 * Hairline row divider INSIDE cards (Oura settings rhythm, design pass 3):
 * quieter than the border token so it separates without boxing.
 */
export function Hairline({ style }: { style?: StyleProp<ViewStyle> }) {
  const theme = useTheme();
  return (
    <View
      style={[styles.hairline, { backgroundColor: theme.border }, style]}
      accessibilityElementsHidden
      importantForAccessibility="no"
    />
  );
}

interface ButtonProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  /**
   * What happens on activation, when the label alone does not say it.
   * Spoken after the name and a pause; never a substitute for the label
   * (SC 2.5.3 — the visible words stay the accessible name).
   */
  hint?: string;
  /**
   * The button's host view, for a screen that must move the screen reader's
   * focus onto it (INT-363: the kiosk idle warning's extend action).
   */
  ref?: Ref<View>;
}

/**
 * The ONE focal CTA a screen gets — full-width pill on the NEUTRAL `cta`
 * tone (design pass 6: Oura's forward action is a bone pill on dark in
 * every Mobbin capture — d1c03e40, 19cf723a, 96fb49c7 — never a saturated
 * slab; light mode carries the inverse ink pill). The teal accent (02 §5.2:
 * single accent) now lives in selection, progress and status moments.
 */
export function PrimaryButton({ label, onPress, disabled = false, hint, ref }: ButtonProps) {
  const theme = useTheme();
  return (
    <Pressable
      ref={ref}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      // Declared rather than left to RN's implicit merge: a dimmed CTA the
      // patient cannot use must SAY it is unavailable, not just look it
      // (SC 1.4.1 — the disabled opacity is the sighted half of this signal).
      accessibilityState={{ disabled }}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.primaryButton,
        {
          backgroundColor: theme.cta,
          opacity: disabled ? motion.press.disabledOpacity : pressed ? motion.press.opacity : 1,
        },
      ]}
    >
      <AppText role="body" color="onCta" style={styles.buttonLabel}>
        {label}
      </AppText>
    </Pressable>
  );
}

/**
 * Oura-register quiet pill for secondary actions: a tonal FILL one step
 * above the ground, borderless (design pass 6 measurement — Oura's quiet
 * buttons and tag chips are filled, never outlined; the pass-5 hairline
 * outline was our invention).
 */
export function SecondaryButton({ label, onPress, disabled = false, hint, ref }: ButtonProps) {
  const theme = useTheme();
  return (
    <Pressable
      ref={ref}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      accessibilityState={{ disabled }}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.primaryButton,
        {
          backgroundColor: theme.surfaceRaised,
          opacity: disabled ? motion.press.disabledOpacity : pressed ? motion.press.opacity : 1,
        },
      ]}
    >
      <AppText role="body" color="ink" style={styles.buttonLabel}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: spacing.screen },
  card: {
    borderRadius: radius.card,
    borderWidth: 1,
    // lg padding (design pass 4): Oura's card interiors breathe at ~24, and
    // 16 read cramped once the radius went to 24.
    padding: spacing.lg,
    gap: spacing.sm,
  },
  cardTight: { padding: spacing.md },
  hairline: {
    height: StyleSheet.hairlineWidth,
    alignSelf: "stretch",
    opacity: 0.9,
  },
  primaryButton: {
    borderRadius: radius.control,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    // Touch target ≥48dp (02 §8.2); 56 with a body-size semibold label is
    // the Oura CTA register (design pass 4). INT-284 moved the number to
    // lib/prefs/appearance.ts, because the glass bar's clearance has to
    // predict this height and a second copy of it would drift.
    minHeight: CTA_MIN_HEIGHT,
    justifyContent: "center",
  },
  buttonLabel: { fontWeight: "600", letterSpacing: 0.2 },
});
