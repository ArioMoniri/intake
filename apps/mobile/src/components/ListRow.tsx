/**
 * Grouped list primitives (design pass 5): the Oura settings/contributor
 * anatomy measured off the Mobbin captures — rows of 52+ pt inside ONE
 * rounded group (radius.group, squarer than content cards), 17 pt sans
 * labels, quiet trailing values, a small "›" only on rows that navigate,
 * hairlines between rows (never around them). Group headers are the
 * existing Kicker rendered OUTSIDE the group by the host screen.
 *
 * Colour never carries meaning alone (02 §8.2): trailing state is always a
 * labelled element, and the chevron is an affordance, not a state.
 *
 * ── The flex contract (the consent-screen collapse) ────────────────────────
 *
 * This is the app's paired shape — ONE label beside ONE trailing control —
 * and every settings, consent, records and share row is one. It used to
 * declare `flex: 1` on the label column and NOTHING on the trailing slot, and
 * React Native gives a child `flexShrink: 0` by default, so the control kept
 * its intrinsic width and the label absorbed the entire deficit. On the
 * narrowest phone the app supports, "Sesli görüşme" beside "Metin
 * hazırlanıyor" already needs more room than the row has at fontScale 1.0 —
 * the DEFAULT text size — and the purpose name came down the screen one
 * letter at a time. The label did not overflow, it was SQUEEZED, and breaking
 * a Turkish word mid-syllable is what 00 §2 forbids tree-wide.
 *
 * Three terms repair it, and all three are decided in lib/a11y/pairedRow.ts
 * where the node suite can hold them:
 *
 * - the label column carries a `minWidth` derived from its OWN longest
 *   unbreakable token, so a short label reserves almost nothing while a long
 *   Turkish compound reserves exactly what it needs;
 * - the trailing slot never shrinks — a control's box is its target, and a
 *   control that shrinks stops being one;
 * - when those two can no longer both hold, the ROW CHANGES FORM and the
 *   control takes the line under the words it governs. It never clamps the
 *   text harder and it never truncates (00 §2).
 *
 * Every dimension leaves through `scaledControl`, which shares theme.ts's
 * single [0.5, 2.0] clamp — the icon well, its glyph and the chevron
 * included, which sat at 36, 17 and 13 beside words that reach 34. That is
 * the owner's "navbar and sizes dont match" one level down, and
 * `scaledControl` exists for it.
 */
import { useCallback, useState, type ReactNode } from "react";
import { Pressable, StyleSheet, View, type LayoutChangeEvent } from "react-native";
import { SymbolView } from "expo-symbols";

import { AppText, Hairline, useFontScale, useScheme, useTheme } from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import {
  CHEVRON_BASE,
  ICON_GLYPH_BASE,
  ICON_WELL_BASE,
  ROW_GAP,
  ROW_INSET_PADDING,
  ROW_PADDING,
  TRAILING_SLOT_FLEX,
  labelColumnStyle,
  pairedRowMetrics,
} from "@/lib/a11y/pairedRow";
import { palette, radius, scaledControl, shadow, spacing } from "@/lib/theme";

/** Action name for the row's nested trailing control. */
const SECONDARY_ACTION = "secondary";

export function ListGroup({ children, footer }: { children: ReactNode; footer?: string }) {
  const scheme = useScheme();
  const theme = palette[scheme];
  const depth = shadow[scheme];
  const rows: ReactNode[] = [];
  const items = Array.isArray(children) ? children : [children];
  items
    .filter((child) => child !== null && child !== undefined && child !== false)
    .forEach((child, index) => {
      if (index > 0) {
        rows.push(<Hairline key={`hairline-${index}`} style={styles.hairlineInset} />);
      }
      rows.push(child);
    });
  return (
    <View style={styles.wrap}>
      <View
        style={[
          styles.group,
          {
            backgroundColor: theme.surface,
            borderColor: scheme === "dark" ? "transparent" : theme.border,
            shadowColor: depth.color,
            shadowOpacity: depth.opacity,
            shadowRadius: depth.radius,
            shadowOffset: { width: 0, height: depth.offsetY },
          },
        ]}
      >
        {rows}
      </View>
      {footer ? (
        <AppText role="caption" color="inkFaint" style={styles.footer}>
          {footer}
        </AppText>
      ) : null}
    </View>
  );
}

interface ListRowProps {
  label: string;
  /** Quiet caption under the label (dates, notes). */
  sublabel?: string;
  /** Leading 36 pt tonal icon well (SF Symbol name) — Oura's row anchor. */
  icon?: string;
  /** Trailing element: a value chip, pill group — rendered as-is. */
  trailing?: ReactNode;
  /**
   * The trailing control's own visible word, when it has one ("Açık", "Metin
   * hazırlanıyor"). It lets the row choose its form on the FIRST frame rather
   * than after a measurement, so nothing is seen re-laying itself out — which
   * matters most on the consent screen, where INT-210 leaves every purpose
   * showing the same long "Metin hazırlanıyor" until the texts land.
   *
   * Omit it for a slot with no single word (a group of pills) and the slot's
   * own `onLayout` supplies the width one frame later.
   */
  trailingText?: string;
  /** "›" affordance; set it ONLY on rows that navigate. */
  chevron?: boolean;
  /** Nested child row (INT-132 lane sub-toggles): indented text column. */
  inset?: boolean;
  onPress?: () => void;
  /**
   * What activating the row does (INT-144). A row and a switch nested in its
   * trailing slot are two different controls that used to carry the same
   * accessible name; the hint is what separates "open the consent text" from
   * "withdraw the consent" for a screen-reader user.
   */
  hint?: string;
  /**
   * Context spoken after the visible label — a date, a trailing value — for
   * rows whose label alone is ambiguous once position is gone. The visible
   * label always comes FIRST (SC 2.5.3 Label in Name).
   */
  labelContext?: string;
  /**
   * The row's SECOND action, when a control is nested in `trailing`
   * (INT-144).
   *
   * A pressable row is `accessible` by default, which merges its whole
   * subtree into one element — so a `Pressable` in the trailing slot is not
   * focusable at all on iOS and its role, state and target are inert. That
   * is how the consent switch became unreachable: a screen-reader user could
   * open a purpose's text but could not withdraw the consent.
   *
   * A custom accessibility action is the platform's answer: VoiceOver
   * surfaces it in the actions rotor and TalkBack in its local context menu,
   * so both reach the toggle without the row having to stop being one
   * element. The trailing control stays exactly as it is for pointer use.
   */
  secondaryAction?: { label: string; onPress: () => void };
}

export function ListRow({
  label,
  sublabel,
  icon,
  trailing,
  trailingText,
  chevron = false,
  inset = false,
  onPress,
  hint,
  labelContext,
  secondaryAction,
}: ListRowProps) {
  const theme = useTheme();
  const fontScale = useFontScale();
  const [rowWidth, setRowWidth] = useState<number | null>(null);
  const [trailingWidth, setTrailingWidth] = useState<number | null>(null);
  const hasTrailing = trailing !== undefined && trailing !== null;

  const onRowLayout = useCallback((event: LayoutChangeEvent) => {
    const width = Math.floor(event.nativeEvent.layout.width);
    setRowWidth((previous) => (previous === width ? previous : width));
  }, []);
  // Monotone on purpose: a recorded trailing width only ever grows, and
  // growing it can only move the row toward the stacked form. That is what
  // makes measure → re-layout → measure settle in one pass instead of
  // oscillating between the two forms.
  const onTrailingLayout = useCallback((event: LayoutChangeEvent) => {
    const width = Math.ceil(event.nativeEvent.layout.width);
    setTrailingWidth((previous) => (previous !== null && previous >= width ? previous : width));
  }, []);

  // The well is a LEADING fixture, not part of the paired split, so it comes
  // off the row before the label and the control divide what is left. Rows
  // carrying an icon AND a trailing control exist — a share row is an icon, an
  // unbounded recipient name and a state caption — so this is declared rather
  // than assumed away.
  const iconWell = icon ? scaledControl(ICON_WELL_BASE, fontScale) : 0;
  const metrics = pairedRowMetrics(
    {
      label,
      trailingText,
      trailingWidth: hasTrailing ? (trailingWidth ?? 0) : 0,
      leading: iconWell === 0 ? 0 : iconWell + ROW_GAP,
      chevron,
      inset,
    },
    fontScale,
    rowWidth,
  );
  // The app-wide large-text ruling is about a CONTROL that must not sit beside
  // wrapped words. A chevron is an affordance, not a control, so a navigation
  // row holds its form until the geometry genuinely runs out; stacking on the
  // scale term alone would put a "›" on a line of its own under every settings
  // row at 1.6, which nothing gains from.
  const stacked = hasTrailing ? metrics.form === "stacked" : metrics.reason === "no-room";

  const body = (
    <>
      {icon ? (
        <View
          style={[
            styles.iconWell,
            {
              backgroundColor: theme.surfaceRaised,
              width: iconWell,
              height: iconWell,
            },
          ]}
        >
          <SymbolView
            name={icon as never}
            size={scaledControl(ICON_GLYPH_BASE, fontScale)}
            tintColor={theme.inkSoft}
          />
        </View>
      ) : null}
      <View
        style={[styles.labels, stacked ? styles.labelsStacked : labelColumnStyle(label, fontScale)]}
      >
        <AppText role="body">{label}</AppText>
        {sublabel ? (
          // Tabular figures: sublabels are mostly dates, and stacked rows
          // should hold a steady numeric column (design pass 6).
          <AppText role="caption" color="inkFaint" style={styles.sublabel}>
            {sublabel}
          </AppText>
        ) : null}
      </View>
      {hasTrailing ? (
        <View
          onLayout={onTrailingLayout}
          style={[TRAILING_SLOT_FLEX, stacked ? styles.trailingStacked : null]}
        >
          {trailing}
        </View>
      ) : null}
      {chevron ? (
        <SymbolView
          name="chevron.right"
          size={scaledControl(CHEVRON_BASE, fontScale)}
          tintColor={theme.inkFaint}
        />
      ) : null}
    </>
  );
  // Declared as a named array rather than inlined: the SC 2.5.8 gate in
  // e2e/a11y.spec.ts follows exactly one hop through `const <name>Style = [`
  // to find a Pressable's declared height floor, and a style expression it
  // cannot resolve is reported as a target with no floor at all.
  const rowStyle = [
    styles.row,
    stacked ? styles.rowStacked : styles.rowBeside,
    inset ? styles.rowInset : null,
  ];
  if (onPress) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={withContext(label, labelContext, sublabel)}
        accessibilityHint={hint}
        accessibilityActions={
          secondaryAction
            ? [{ name: SECONDARY_ACTION, label: secondaryAction.label }]
            : undefined
        }
        onAccessibilityAction={
          secondaryAction
            ? (event) => {
                if (event.nativeEvent.actionName === SECONDARY_ACTION) {
                  secondaryAction.onPress();
                }
              }
            : undefined
        }
        onLayout={onRowLayout}
        onPress={onPress}
        style={({ pressed }) => [...rowStyle, { opacity: pressed ? 0.7 : 1 }]}
      >
        {body}
      </Pressable>
    );
  }
  return (
    <View onLayout={onRowLayout} style={rowStyle}>
      {body}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  group: {
    borderRadius: radius.group,
    borderWidth: 1,
    overflow: "hidden",
  },
  row: {
    // The gap, the padding and the inset are read from the module that does
    // the fit arithmetic. A row that renders 16 where the model reserves 12 is
    // the reserved number and the rendered number free to drift.
    gap: ROW_GAP,
    // A FLOOR, not a height: at large scales the wrapped label makes the row
    // taller on its own, which is the growth the patient asked for. The row IS
    // the target (SC 2.5.8) and 56 is the app's list rhythm.
    minHeight: 56,
    paddingHorizontal: ROW_PADDING,
    paddingVertical: spacing.sm + 2,
  },
  rowBeside: { flexDirection: "row", alignItems: "center" },
  // Column form: the control sits UNDER the words it governs and left-aligned
  // with them. A control pinned to the right of two wrapped Turkish lines
  // reads as an afterthought rather than as the control for them.
  rowStacked: { flexDirection: "column", alignItems: "flex-start" },
  labels: { gap: 2 },
  labelsStacked: { alignSelf: "stretch", gap: 2 },
  sublabel: { fontVariant: ["tabular-nums"] },
  // Intrinsic width, left-aligned — never stretched, so the width the slot
  // reports is the same number in both forms and the monotone rule holds.
  trailingStacked: { alignSelf: "flex-start" },
  // Nested child rows shift the whole content column one step right.
  rowInset: { paddingLeft: ROW_INSET_PADDING },
  // Oura hairlines start at the text column, not the group edge.
  hairlineInset: { marginLeft: spacing.md },
  // Size comes from the scale at render (INT-260): a 36 pt well holding a
  // 17 pt glyph beside a 34 pt body line is the register clash the owner
  // named. `radius.chip` keeps it a circle at every size, where the literal
  // 18 that used to sit here was a second copy of "half of 36".
  iconWell: {
    borderRadius: radius.chip,
    alignItems: "center",
    justifyContent: "center",
  },
  footer: { paddingHorizontal: spacing.md },
});
