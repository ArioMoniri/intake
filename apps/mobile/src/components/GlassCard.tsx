/**
 * Liquid Glass surface (INT-193, upgraded design pass 3): the system
 * material on iOS 26+, and a REAL BlurView + soft tint wash + hairline
 * everywhere else — the wash alone read as flat plastic; the blur underneath
 * is what makes it glass. Glass stays a garnish, never a ground — body text
 * sits on solid surfaces for contrast (02 §8.2); glass carries hero cards
 * and floating chrome only. The tab rail is native glass via NativeTabs.
 */
import { type ReactNode } from "react";
import {
  StyleSheet,
  View,
  useColorScheme,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import { BlurView } from "expo-blur";
import { GlassView, isLiquidGlassAvailable } from "expo-glass-effect";

import { useTheme } from "@/components/Themed";
import { glassFallback, radius, spacing } from "@/lib/theme";

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
        { borderColor: fallback.borderColor },
        // hairline shadow only in light mode; dark separates tonally
        scheme === "light" ? { shadowColor: theme.ink, ...styles.lightShadow } : null,
        style,
      ]}
    >
      <BlurView
        intensity={50}
        tint={scheme === "dark" ? "dark" : "light"}
        style={StyleSheet.absoluteFill}
      />
      <View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { backgroundColor: fallback.backgroundColor }]}
      />
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
