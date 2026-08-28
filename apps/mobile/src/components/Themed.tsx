/**
 * Themed primitives (INT-130, premium pass INT-193): the only place
 * components read the palette, fontScale and type roles. Screens compose
 * these; none of them hardcode a colour or a font size, so the 02 §5.2
 * rules (single accent, dynamic type, no ALL-CAPS transforms) hold by
 * construction. Hero and title text carry the serif display face (the
 * Oura/Tiimo signature); light-mode cards float on a soft wide shadow,
 * dark mode separates tonally.
 */
import { type ReactNode } from "react";
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
import { SafeAreaView, type Edge } from "react-native-safe-area-context";

import {
  fonts,
  lineHeight,
  palette,
  radius,
  scaledSize,
  shadow,
  spacing,
  type ThemeColors,
  type TypeRole,
} from "@/lib/theme";

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

export function useTheme(): ThemeColors {
  const scheme = useColorScheme();
  return palette[scheme === "dark" ? "dark" : "light"];
}

export function useFontScale(): number {
  return useWindowDimensions().fontScale;
}

interface AppTextProps {
  role?: TypeRole;
  color?: keyof ThemeColors;
  style?: StyleProp<TextStyle>;
  children: ReactNode;
}

export function AppText({ role = "body", color = "ink", style, children }: AppTextProps) {
  const theme = useTheme();
  const fontScale = useFontScale();
  const display = role === "hero" || role === "title";
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
    <Text allowFontScaling={false} style={flat}>
      {children}
    </Text>
  );
}

/**
 * Screens under the floating tab rail (design pass 4) drop the bottom safe
 * edge so content scrolls UNDER the pill to the physical edge (Oura chrome);
 * they pad their scroll content with TAB_BAR_CLEARANCE instead.
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
  const scheme = useColorScheme() === "dark" ? "dark" : "light";
  const theme = palette[scheme];
  const depth = shadow[scheme];
  return (
    <View
      style={[
        styles.card,
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
}

/** The ONE saturated CTA a screen gets (02 §5.2: single accent). Pill form. */
export function PrimaryButton({ label, onPress, disabled = false }: ButtonProps) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.primaryButton,
        { backgroundColor: theme.primary, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
      ]}
    >
      <AppText role="body" color="onPrimary" style={styles.buttonLabel}>
        {label}
      </AppText>
    </Pressable>
  );
}

/** Oura-register quiet pill for secondary actions: surface + hairline. */
export function SecondaryButton({ label, onPress, disabled = false }: ButtonProps) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.primaryButton,
        {
          backgroundColor: theme.surface,
          borderWidth: 1,
          borderColor: theme.border,
          opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
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
    // the Oura CTA register (design pass 4).
    minHeight: 56,
    justifyContent: "center",
  },
  buttonLabel: { fontWeight: "600", letterSpacing: 0.2 },
});
