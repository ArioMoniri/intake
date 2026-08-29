/**
 * Guidance block (design pass 3, after Oura's "Guidance and tips"): a
 * kickered informational section ABOUT THE PRODUCT — how a space will work,
 * the privacy promise, who controls sharing. Kicker pill, serif display
 * title, quiet body on the solid ground. Strictly non-clinical product copy
 * (no instruments, no advice — HB-L2 stays blocked); the block frames empty
 * spaces instead of a lone "nothing here" card.
 *
 * Design pass 6: an optional quiet geometric mark — Oura's permission
 * primers (Mobbin d1c03e40, 3f29d971, 6b8646ec) open with a glyph inside a
 * hairline-outlined rounded square (~56 pt, 1 px outline, ~24 pt glyph)
 * above the title. One mark per screen, on the block the screen is about;
 * the glyph is soft ink, never the accent.
 */
import { StyleSheet, View } from "react-native";
import { SymbolView } from "expo-symbols";

import { Kicker } from "@/components/Kicker";
import { AppText, useTheme } from "@/components/Themed";
import { t, type MessageKey } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

interface GuidanceBlockProps {
  kickerKey: MessageKey;
  titleKey: MessageKey;
  bodyKey: MessageKey;
  /** The one block per screen that carries the accent kicker. */
  accent?: boolean;
  /** SF Symbol for the outlined-badge mark; set it on ONE block per screen. */
  icon?: string;
}

export function GuidanceBlock({
  kickerKey,
  titleKey,
  bodyKey,
  accent = false,
  icon,
}: GuidanceBlockProps) {
  const theme = useTheme();
  return (
    <View style={styles.block}>
      {icon ? (
        <View
          accessibilityElementsHidden
          importantForAccessibility="no"
          style={[styles.badge, { borderColor: theme.border }]}
        >
          <SymbolView name={icon as never} size={24} tintColor={theme.inkSoft} />
        </View>
      ) : null}
      <Kicker label={t(kickerKey)} tone={accent ? "accent" : "neutral"} />
      {/* A guidance block is a titled section, so its title is a heading
          (SC 1.3.1): the heading rotor is how a screen-reader user moves
          between blocks instead of reading all of them in sequence. */}
      <AppText role="title" heading>
        {t(titleKey)}
      </AppText>
      <AppText role="body" color="inkSoft">
        {t(bodyKey)}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: spacing.sm },
  // The Oura primer badge: 56 pt outlined rounded square, glyph centred.
  badge: {
    width: 56,
    height: 56,
    borderRadius: 16,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xs,
  },
});
