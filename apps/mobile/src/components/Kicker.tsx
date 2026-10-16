/**
 * Section header (INT-422, docs/design/system-refresh.md): the iOS grouped
 * list header, a quiet Footnote line ABOVE a section or inside a card's top.
 * No dot, no tracking and no case transform: the tracked, dotted eyebrow was
 * the most generic of the old styling, and ALL-CAPS is banned outright (İ/ı,
 * 00 §2). Sentence case at Footnote size is what Apple's own lists use.
 */
import { StyleSheet } from "react-native";

import { AppText } from "@/components/Themed";
import { spacing } from "@/lib/theme";

interface KickerProps {
  label: string;
  /** accent = the section the screen is about; neutral = everything else. */
  tone?: "accent" | "neutral";
  /**
   * A grouped list's header (INT-472): inset to the rows' text, as iOS
   * Settings aligns a section header with the cells under it.
   */
  inset?: boolean;
}

export function Kicker({ label, tone = "neutral", inset = false }: KickerProps) {
  const accent = tone === "accent";
  return (
    <AppText
      role="caption"
      color={accent ? "primary" : "inkSoft"}
      style={[styles.label, inset ? styles.inset : null]}
    >
      {label}
    </AppText>
  );
}

const styles = StyleSheet.create({
  label: { alignSelf: "flex-start", fontWeight: "600" },
  inset: { paddingHorizontal: spacing.md },
});
