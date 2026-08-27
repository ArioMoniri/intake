/**
 * Guidance block (design pass 3, after Oura's "Guidance and tips"): a
 * kickered informational section ABOUT THE PRODUCT — how a space will work,
 * the privacy promise, who controls sharing. Kicker pill, serif display
 * title, quiet body on the solid ground. Strictly non-clinical product copy
 * (no instruments, no advice — HB-L2 stays blocked); the block frames empty
 * spaces instead of a lone "nothing here" card.
 */
import { StyleSheet, View } from "react-native";

import { Kicker } from "@/components/Kicker";
import { AppText } from "@/components/Themed";
import { t, type MessageKey } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

interface GuidanceBlockProps {
  kickerKey: MessageKey;
  titleKey: MessageKey;
  bodyKey: MessageKey;
  /** The one block per screen that carries the accent kicker. */
  accent?: boolean;
}

export function GuidanceBlock({ kickerKey, titleKey, bodyKey, accent = false }: GuidanceBlockProps) {
  return (
    <View style={styles.block}>
      <Kicker label={t(kickerKey)} tone={accent ? "accent" : "neutral"} />
      <AppText role="title">{t(titleKey)}</AppText>
      <AppText role="body" color="inkSoft">
        {t(bodyKey)}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: spacing.sm },
});
