/**
 * Themed primitives (INT-130): the only place components read the palette,
 * fontScale and type roles. Screens compose these; none of them hardcode a
 * colour or a font size, so the 02 §5.2 rules (single accent, dynamic type,
 * no ALL-CAPS transforms) hold by construction.
 */
import { type ReactNode } from "react";
import {
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
  lineHeight,
  palette,
  radius,
  scaledSize,
  spacing,
  type ThemeColors,
  type TypeRole,
} from "@/lib/theme";

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

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const theme = useTheme();
  return (
    <View
      style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }, style]}
    >
      {children}
    </View>
  );
}

interface PrimaryButtonProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}

export function PrimaryButton({ label, onPress, disabled = false }: PrimaryButtonProps) {
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

const styles = StyleSheet.create({
  screen: { flex: 1, padding: spacing.md },
  card: {
    borderRadius: radius.card,
    borderWidth: 1,
    padding: spacing.md,
    gap: spacing.sm,
  },
  primaryButton: {
    borderRadius: radius.control,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    // Touch target ≥48dp (02 §8.2) even at fontScale 1.0.
    minHeight: 48,
    justifyContent: "center",
  },
  buttonLabel: { fontWeight: "600" },
});
