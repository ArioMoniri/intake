/**
 * The quiet mode row (INT-236; extracted and rebuilt here by INT-295).
 *
 * Two controls and a status line: the "Hastanedeyim" switch (02 §2 table —
 * the Detaylı trigger) and, while Detaylı is on, the persistent "Sıranız
 * geldi" affordance (02 §34), with the mode's own state written underneath.
 * Both controls stay caption-register chips — mode is context, never the
 * screen's subject — and nothing about the design language changes here.
 * What changes is where the row puts them.
 *
 * The defect INT-293 photographed: all three were ONE row that could not
 * wrap, could not scroll and could not change form, with the checkpoint chip
 * pinned to the right by an auto margin. As the labels grew, the chip walked
 * off the edge — on the captured iPhone 16 Pro it leaves the row at text
 * scale 1.20 and is fully gone by 2.0 — and "I have been called in, give me
 * my note now" became unreachable in the one mode that exists for standing
 * in a hospital corridor.
 *
 * Three changes, each answering one way the row could lose a control:
 *
 *   1. The status caption leaves the row. It is prose about the switch, not
 *      a control, and it belongs on the line below with the deferral notice
 *      it already shares a register with. That alone gives the row back a
 *      third of its width.
 *   2. The row wraps and its chips shrink. RN flex children do neither by
 *      default, which is why the overflow left the screen instead of
 *      breaking a line; with `flexWrap` a chip that no longer fits drops to
 *      the next line, where it is still a control.
 *   3. At the app's one large-text threshold the row changes FORM rather
 *      than clamping the text (00 §2), exactly as the segmented control and
 *      the tab rail do: each chip takes its own full-width line.
 *
 * The chips reach the touch floor by BOX now instead of by slop. A row that
 * can put two chips four points apart VERTICALLY is the case lib/a11y/target.ts
 * refuses horizontally — overlapping slop trading one target for a worse one.
 *
 * `e2e/modeBar.spec.ts` holds the property: every item of this row lands
 * inside the screen, at every text size the app can be set to, in both
 * catalogues, on both phone widths — measured in the face the app ships.
 */
import { Pressable, StyleSheet, View } from "react-native";

import { AppText, useFontScale, useTheme } from "@/components/Themed";
import { MIN_TAP } from "@/lib/a11y/target";
import { t } from "@/lib/i18n";
import { isLargeText } from "@/lib/prefs/appearance";
import { radius, spacing } from "@/lib/theme";

export interface ModeBarProps {
  detayli: boolean;
  /** Show the calm one-liner that private questions are deferred (02 §33). */
  deferredNotice: boolean;
  onToggleMode: () => void;
  onQueueCalled: () => void;
}

export function ModeBar({ detayli, deferredNotice, onToggleMode, onQueueCalled }: ModeBarProps) {
  const theme = useTheme();
  const stacked = isLargeText(useFontScale());
  const chipStyle = [styles.modeChip, stacked ? styles.modeChipStacked : styles.modeChipInline];
  return (
    <View style={styles.modeBlock}>
      <View style={[styles.modeRow, stacked ? styles.modeRowStacked : styles.modeRowInline]}>
        <Pressable
          accessibilityRole="switch"
          accessibilityLabel={t("intake.mode.hastanedeyim")}
          accessibilityState={{ checked: detayli }}
          onPress={onToggleMode}
          style={[
            ...chipStyle,
            { backgroundColor: detayli ? theme.primarySoft : theme.surfaceRaised },
          ]}
        >
          <AppText role="caption" color={detayli ? "primary" : "inkSoft"}>
            {t("intake.mode.hastanedeyim")}
          </AppText>
        </Pressable>
        {detayli ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("intake.queue.called")}
            onPress={onQueueCalled}
            style={[...chipStyle, { backgroundColor: theme.surfaceRaised }]}
          >
            <AppText role="caption" color="primary">
              {t("intake.queue.called")}
            </AppText>
          </Pressable>
        ) : null}
      </View>
      {detayli ? (
        <AppText role="caption" color="inkFaint">
          {t("intake.mode.detayliOn")}
        </AppText>
      ) : null}
      {deferredNotice ? (
        <AppText role="caption" color="inkFaint">
          {t("intake.privacy.deferredInfo")}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  modeBlock: { gap: spacing.xs },
  modeRow: { gap: spacing.xs },
  // `flexWrap` is the whole difference between a chip that moves down a line
  // and a chip that is drawn where the screen is not.
  modeRowInline: { flexDirection: "row", flexWrap: "wrap", alignItems: "center" },
  modeRowStacked: { flexDirection: "column", alignItems: "stretch" },
  modeChip: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
    // By box, not by slop: these chips can end up one above the other.
    minHeight: MIN_TAP,
    alignItems: "center",
    justifyContent: "center",
  },
  // So a label longer than the line shrinks its chip and wraps inside it,
  // rather than carrying the chip past the edge.
  modeChipInline: { flexShrink: 1 },
  modeChipStacked: { alignSelf: "stretch" },
});
