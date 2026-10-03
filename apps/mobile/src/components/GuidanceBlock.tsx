/**
 * Guidance block (design pass 3, after Oura's "Guidance and tips"): a
 * kickered informational section ABOUT THE PRODUCT — how a space will work,
 * the privacy promise, who controls sharing. Kicker pill, serif display
 * title, quiet body on the solid ground. Strictly non-clinical product copy
 * (no instruments, no advice — HB-L2 stays blocked); the block frames empty
 * spaces instead of a lone "nothing here" card.
 *
 * An optional mark: one SF Symbol, bare and in the tint, above the title, the
 * way Apple's own privacy and onboarding primers open (INT-422). No outlined
 * box or illustration around it. One mark per screen, on the block the screen
 * is about.
 */
import { StyleSheet, View } from "react-native";

import { Icon } from "@/components/Icon";
import { Kicker } from "@/components/Kicker";
import { AppText, useTheme } from "@/components/Themed";
import { t, type MessageKey } from "@/lib/i18n";
import type { SymbolKey } from "@/lib/symbols";
import { spacing } from "@/lib/theme";

interface GuidanceBlockProps {
  kickerKey: MessageKey;
  titleKey: MessageKey;
  bodyKey: MessageKey;
  /** The one block per screen that carries the accent kicker. */
  accent?: boolean;
  /** Symbol registry row for the block's mark; set it on ONE block per screen. */
  icon?: SymbolKey;
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
        <View accessibilityElementsHidden importantForAccessibility="no" style={styles.mark}>
          <Icon name={icon} size={36} tintColor={theme.primary} />
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
  mark: { alignSelf: "flex-start", marginBottom: spacing.xs },
});
