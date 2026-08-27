/**
 * Liquid Glass surface (INT-193): the system material on iOS 26+, a
 * translucent fallback wash everywhere else. Glass is a garnish here, not a
 * ground — body text stays on solid surfaces for contrast (02 §8.2); glass
 * carries hero cards and floating chrome only. The rail itself is native
 * glass for free via NativeTabs.
 */
import { type ReactNode } from "react";
import { StyleSheet, View, type StyleProp, type ViewStyle } from "react-native";
import { GlassView, isLiquidGlassAvailable } from "expo-glass-effect";

import { useTheme } from "@/components/Themed";
import { glassFallback, radius, spacing } from "@/lib/theme";
import { useColorScheme } from "react-native";

let liquidGlass = false;
try {
  liquidGlass = isLiquidGlassAvailable();
} catch {
  liquidGlass = false;
}

interface GlassCardProps {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}

export function GlassCard({ children, style }: GlassCardProps) {
  const theme = useTheme();
  const scheme = useColorScheme() === "dark" ? "dark" : "light";
  if (liquidGlass) {
    return (
      <GlassView glassEffectStyle="regular" style={[styles.card, style]}>
        {children}
      </GlassView>
    );
  }
  const fallback = glassFallback(scheme);
  return (
    <View
      style={[
        styles.card,
        styles.fallbackBorder,
        { backgroundColor: fallback.backgroundColor, borderColor: fallback.borderColor },
        // hairline shadow only in light mode; dark separates tonally
        scheme === "light" ? { shadowColor: theme.ink, ...styles.lightShadow } : null,
        style,
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.hero,
    padding: spacing.md,
    gap: spacing.sm,
    overflow: "hidden",
  },
  fallbackBorder: { borderWidth: StyleSheet.hairlineWidth },
  lightShadow: {
    shadowOpacity: 0.07,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 8 },
  },
});
