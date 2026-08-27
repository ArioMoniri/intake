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
import { SafeAreaView } from "react-native-safe-area-context";

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

// Fraunces is guaranteed loaded before the tree renders (root layout gates
// on useFonts); the platform serif remains only as a defensive fallback.
const DISPLAY_FONT = fonts.display ?? Platform.select(fonts.displayFallback);

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
  return (
    <Text
      // Sizes come from scaledSize; RN's own multiplier is disabled so the
      // 2.0 cap (layout-survival, 02 §8.2) is applied in exactly one place.
      allowFontScaling={false}
      style={[
        {
          color: theme[color],
          fontSize: scaledSize(role, fontScale),
          lineHeight: lineHeight(role, fontScale),
        },
        display ? { fontFamily: DISPLAY_FONT } : null,
        style,
      ]}
    >
      {children}
    </Text>
  );
}

export function Screen({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const theme = useTheme();
  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: theme.background }, style]}>
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
      <AppText role="label" color="onPrimary" style={styles.buttonLabel}>
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
      <AppText role="label" color="ink" style={styles.buttonLabel}>
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
    padding: spacing.md,
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
    // Touch target ≥48dp (02 §8.2) even at fontScale 1.0.
    minHeight: 52,
    justifyContent: "center",
  },
  buttonLabel: { fontWeight: "600", letterSpacing: 0.2 },
});
