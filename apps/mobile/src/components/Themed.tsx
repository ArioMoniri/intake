/**
 * Themed primitives (INT-130; native refresh INT-422,
 * docs/design/system-refresh.md): the only place components read the
 * palette, fontScale and type roles. Screens compose these; none of them
 * hardcode a colour or a font size, so the 02 §5.2 rules (single accent,
 * dynamic type, no ALL-CAPS transforms) hold by construction.
 *
 * The register is Apple's: the platform face at Dynamic Type sizes, cells on
 * a grouped ground with no shadow, 12-pt continuous corners, the tinted
 * filled button for the one focal action and the grey button for the rest.
 * The colours follow the in-app theme AND the OS Increase Contrast request.
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

import { useIncreasedContrast } from "@/lib/a11y/prefs";
import { getLocale } from "@/lib/i18n";
import { CTA_MIN_HEIGHT, effectiveFontScale, resolveScheme } from "@/lib/prefs/appearance";
import { useAppearance } from "@/lib/prefs/AppearanceProvider";
import {
  colorsFor,
  fonts,
  lineHeight,
  motion,
  radius,
  ROUNDED_ROLES,
  roleWeight,
  scaledSize,
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

/**
 * SF Pro Rounded on iOS, the system sans elsewhere, for the roles
 * `ROUNDED_ROLES` names: a screen's Large Title and the one numeral. The
 * rounded design is the warmth the refresh keeps (SwiftUI's
 * `.fontDesign(.rounded)`), and it is a face, not a flourish. Every other
 * role takes the platform face, which synthesises no weight.
 */
const ROUNDED_FONT = Platform.select(fonts.rounded);

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

/**
 * The colours to render: the resolved scheme (the patient's Tema choice or
 * the OS) and the OS Increase Contrast request (INT-422). The one place a
 * palette is chosen, so a component that takes its colours from here follows
 * both settings, live.
 */
export function useTheme(): ThemeColors {
  return colorsFor(useScheme(), useIncreasedContrast());
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
 * The top bar for pushed screens: the iOS inline navigation bar, a centred
 * body-sized semibold title and a "‹" back with no label, on the grouped
 * ground and shadowless so it reads as part of the page. Screens that use
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
      fontWeight: "600",
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
  children: ReactNode;
}

export function AppText({
  role = "body",
  color = "ink",
  style,
  heading = false,
  live,
  spokenAs,
  children,
}: AppTextProps) {
  const theme = useTheme();
  const fontScale = useFontScale();
  // The role's Dynamic Type size and weight in the platform face; the one
  // Large Title and the numeral take SF Pro Rounded. A caller's own weight
  // still wins.
  const flat: TextStyle = StyleSheet.flatten([
    {
      color: theme[color],
      fontSize: scaledSize(role, fontScale),
      lineHeight: lineHeight(role, fontScale),
      fontWeight: roleWeight[role],
    },
    ROUNDED_ROLES.includes(role) ? { fontFamily: ROUNDED_FONT } : null,
    style,
  ]);
  return (
    // Sizes come from scaledSize; RN's own multiplier is disabled so the
    // 2.0 cap (layout-survival, 02 §8.2) is applied in exactly one place.
    <Text
      allowFontScaling={false}
      accessibilityRole={heading ? "header" : live !== undefined ? "alert" : undefined}
      accessibilityLiveRegion={live}
      accessibilityLabel={spokenAs}
      accessibilityLanguage={SPEECH_LANGUAGE[getLocale()]}
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
  /** A tinted fill behind the content, for the one card a screen is about. */
  wash?: "none" | "primary";
}

export function Card({ children, style, wash = "none" }: CardProps) {
  const theme = useTheme();
  // A grouped cell: the surface on the grouped ground, with no edge and no
  // shadow, in both schemes; the tone step carries the separation. Its padding is the 16 pt content margin at
  // every text size, so a long Turkish word keeps the card's whole measure
  // at 200 % (INT-260: "Hastalıkla / rı" is the break 00 §2 forbids).
  return (
    <View
      style={[
        styles.card,
        { backgroundColor: wash === "primary" ? theme.primarySoft : theme.surface },
        style,
      ]}
    >
      {children}
    </View>
  );
}

/**
 * Hairline row divider INSIDE cards and groups: the iOS separator, quieter
 * than the control border so it separates without boxing.
 */
export function Hairline({ style }: { style?: StyleProp<ViewStyle> }) {
  const theme = useTheme();
  return (
    <View
      style={[styles.hairline, { backgroundColor: theme.separator }, style]}
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
 * The ONE focal action a screen gets: the tinted, filled button (SwiftUI's
 * `.borderedProminent`, UIKit's filled configuration) at full width, with a
 * 12-pt continuous corner. The accent is spent here, once per screen.
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
 * Every other action: the grey button with a tinted label (SwiftUI's
 * `.bordered`), so a secondary action reads as one without competing with
 * the focal one.
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
      <AppText role="body" color="primary" style={styles.buttonLabel}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: spacing.screen },
  card: {
    borderRadius: radius.card,
    borderCurve: "continuous",
    padding: spacing.md,
    gap: spacing.sm,
  },
  hairline: {
    height: StyleSheet.hairlineWidth,
    alignSelf: "stretch",
  },
  primaryButton: {
    borderRadius: radius.control,
    borderCurve: "continuous",
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    // Touch target ≥48dp (02 §8.2). INT-284 moved the number to
    // lib/prefs/appearance.ts, because the glass bar's clearance has to
    // predict this height and a second copy of it would drift.
    minHeight: CTA_MIN_HEIGHT,
    justifyContent: "center",
  },
  buttonLabel: { fontWeight: "600" },
});
