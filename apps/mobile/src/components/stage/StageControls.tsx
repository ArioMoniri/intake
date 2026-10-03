/**
 * The chat stage's controls (ADR-039 S3 to S5, INT-466;
 * docs/design/liquid-glass-research.md).
 *
 * Glass is for the control layer that floats above content, as Apple's
 * guidance says. Content is never glass.
 *
 * - `StageGlassGroup`: one GlassContainer for the stage's floating controls,
 *   so neighbouring glass merges, as the field and its control do in Messages.
 * - `GlassComposer`: the composer field and its one control, as two glass
 *   shapes in that group (no glass on glass). Send, the primary action, is
 *   tinted; the mic and stop are not.
 * - `StageButton`: a turn action, as a glass capsule. Only the prominent
 *   (primary) one is tinted.
 * - `AnswerCard`: an answer, as content: a SOLID card, filled with the accent
 *   and checked when selected, so selection never rests on colour alone.
 *
 * Every glass surface is the regular variant, takes the app's resolved scheme
 * and is interactive (the system's own press response, ADR-039 S4). The
 * sign-in screens pass `interactive={false}` (ADR-039 S7): they add no
 * motion, so their glass is inert and a press shows only the opacity step.
 * Under Reduce Transparency (`mode !== "liquid"`) every surface is a solid
 * stage fill instead, so nothing is see-through.
 */
import { GlassContainer, GlassView } from "expo-glass-effect";
import { type ReactNode } from "react";
import {
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { useGlassMode } from "@/components/glassMode";
import { Icon } from "@/components/Icon";
import { AppText, useFontScale, useScheme } from "@/components/Themed";
import { MIN_TAP } from "@/lib/a11y/target";
import type { StagePalette } from "@/lib/stage/palette";
import { STAGE_RADIUS, STAGE_SIZE, capsule } from "@/lib/stage/shape";
import type { SymbolKey } from "@/lib/symbols";
import { fonts, motion, scaledSize, spacing } from "@/lib/theme";

const ROUNDED = Platform.select(fonts.rounded);

/** How close two glass shapes come before they merge (GlassContainer spacing). */
const MERGE_SPACING = spacing.sm;

/** One glass surface, or its solid answer under Reduce Transparency. */
function Pane({
  palette,
  tint,
  interactive = true,
  style,
  children,
}: {
  palette: StagePalette;
  tint?: string;
  /** False on the sign-in screens: glass without the system press response. */
  interactive?: boolean;
  style: StyleProp<ViewStyle>;
  children?: ReactNode;
}) {
  const mode = useGlassMode();
  const scheme = useScheme();
  if (mode !== "liquid") {
    return (
      <View
        style={[
          style,
          {
            backgroundColor: tint ?? palette.card,
            borderWidth: palette.cardBorder !== null && tint === undefined ? 1 : 0,
            borderColor: palette.cardBorder ?? "transparent",
          },
        ]}
      >
        {children}
      </View>
    );
  }
  // The label's floor (ADR-039 S3, palette.test.ts): the pane carries the
  // control veil under its glass, so a label never depends on the glass
  // having drawn. On a clinical screen iOS draws no Liquid Glass at all:
  // INT-131's capture protection (expo-screen-capture) moves the window into
  // a secure layer, where glass has nothing to sample. A white label on
  // nothing would fail AA; on the veil it passes.
  const floor = tint ?? veilColor(palette);
  return (
    <GlassView
      glassEffectStyle="regular"
      colorScheme={scheme}
      isInteractive={interactive}
      tintColor={tint}
      style={[style, { backgroundColor: floor }]}
    >
      {children}
    </GlassView>
  );
}

/** The palette's control veil as one colour (#RRGGBBAA). */
function veilColor(palette: StagePalette): string {
  const alpha = Math.round(palette.controlVeil.alpha * 255)
    .toString(16)
    .padStart(2, "0");
  return `${palette.controlVeil.color}${alpha}`;
}

/** The stage's floating controls, merged as one glass group. */
export function StageGlassGroup({ children }: { children: ReactNode }) {
  const mode = useGlassMode();
  if (mode !== "liquid") {
    return <View style={styles.group}>{children}</View>;
  }
  return (
    <GlassContainer spacing={MERGE_SPACING} style={styles.group}>
      {children}
    </GlassContainer>
  );
}

export function StageButton({
  palette,
  label,
  onPress,
  prominent = false,
  disabled = false,
  interactive = true,
}: {
  palette: StagePalette;
  label: string;
  onPress: () => void;
  prominent?: boolean;
  disabled?: boolean;
  /** ADR-039 S7: false where a screen adds no motion (the sign-in flow). */
  interactive?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      // Inert glass has no press response of its own, so the press is the
      // instant opacity step (ADR-037 P1's second cue); interactive glass
      // answers the finger itself.
      style={({ pressed }) => [
        styles.actionTarget,
        disabled
          ? { opacity: motion.press.disabledOpacity }
          : pressed && !interactive
            ? { opacity: motion.press.opacity }
            : null,
      ]}
    >
      <Pane
        palette={palette}
        tint={prominent ? palette.cardSelected : undefined}
        interactive={interactive}
        style={styles.action}
      >
        <AppText
          role="body"
          style={[
            styles.rounded,
            styles.actionLabel,
            { color: prominent ? palette.cardInkSelected : palette.ink },
          ]}
        >
          {label}
        </AppText>
      </Pane>
    </Pressable>
  );
}

export type ComposerControl = "mic" | "send" | "stop";

const CONTROL_SYMBOL: Record<ComposerControl, SymbolKey> = {
  mic: "mic.fill",
  send: "arrow.up",
  stop: "stop.fill",
};

export function GlassComposer({
  palette,
  value,
  onChangeText,
  onFocus,
  onBlur,
  onSubmit,
  prompt,
  promptHint,
  focused,
  control,
  controlLabel,
  controlHint,
  controlDisabled,
  onControl,
}: {
  palette: StagePalette;
  value: string;
  onChangeText: (next: string) => void;
  onFocus: () => void;
  onBlur: () => void;
  onSubmit: () => void;
  /** The field's name, also drawn as its prompt while it is empty. */
  prompt: string;
  promptHint: string;
  focused: boolean;
  control: ComposerControl;
  controlLabel: string;
  controlHint?: string;
  controlDisabled: boolean;
  onControl: () => void;
}) {
  const fontScale = useFontScale();
  const glyph = control === "send" ? palette.cardInkSelected : palette.ink;
  return (
    <View style={styles.composerRow}>
      <Pane
        palette={palette}
        style={[
          styles.field,
          // The focus ring: the accent, as INT-433's filled field draws it.
          { borderWidth: focused ? 2 : 0, borderColor: palette.accent },
        ]}
      >
        <TextInput
          accessibilityLabel={prompt}
          accessibilityHint={promptHint}
          // The field applies scaledSize itself, so the OS multiplier must be
          // off or a 200 % setting becomes 400 % (SC 1.4.4).
          allowFontScaling={false}
          value={value}
          onChangeText={onChangeText}
          onFocus={onFocus}
          onBlur={onBlur}
          returnKeyType="send"
          onSubmitEditing={onSubmit}
          style={[styles.input, { color: palette.ink, fontSize: scaledSize("body", fontScale) }]}
        />
        {value.length === 0 ? (
          // The empty field's prompt, drawn over it: the field's own hint prop
          // is a banned filler token in the app source (invariant 17 scan),
          // and the field already speaks these words as its name.
          <View
            pointerEvents="none"
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
            style={styles.promptWrap}
          >
            <AppText role="body" style={[styles.rounded, { color: palette.inkSoft }]}>
              {prompt}
            </AppText>
          </View>
        ) : null}
      </Pane>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={controlLabel}
        accessibilityHint={controlHint}
        accessibilityState={{ disabled: controlDisabled }}
        disabled={controlDisabled}
        onPress={onControl}
        style={[
          styles.controlTarget,
          controlDisabled ? { opacity: motion.press.disabledOpacity } : null,
        ]}
      >
        <Pane
          palette={palette}
          tint={control === "send" ? palette.cardSelected : undefined}
          style={styles.control}
        >
          <Icon
            name={CONTROL_SYMBOL[control]}
            size={scaledSize("body", fontScale)}
            tintColor={glyph}
          />
        </Pane>
      </Pressable>
    </View>
  );
}

export function AnswerCard({
  palette,
  label,
  selected,
  role,
  hint,
  onPress,
}: {
  palette: StagePalette;
  label: string;
  selected: boolean;
  /** A checkbox says "you may pick several"; a single-answer turn is a radio. */
  role: "radio" | "checkbox";
  hint: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole={role}
      accessibilityState={{ checked: selected }}
      accessibilityLabel={label}
      accessibilityHint={hint}
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        {
          backgroundColor: selected ? palette.cardSelected : palette.card,
          borderWidth: palette.cardBorder !== null && !selected ? 1 : 0,
          borderColor: palette.cardBorder ?? "transparent",
          opacity: pressed ? motion.press.rowOpacity : 1,
        },
      ]}
    >
      <AppText
        role="body"
        style={[
          styles.rounded,
          styles.cardLabel,
          { color: selected ? palette.cardInkSelected : palette.ink },
        ]}
      >
        {label}
      </AppText>
      <View
        style={[
          styles.check,
          selected
            ? { backgroundColor: palette.cardInkSelected }
            : { borderWidth: 1.5, borderColor: palette.inkSoft },
        ]}
      >
        {selected ? <Icon name="checkmark" size={12} tintColor={palette.cardSelected} /> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  rounded: { fontFamily: ROUNDED },
  group: { gap: spacing.sm },
  actionTarget: { minHeight: MIN_TAP },
  action: {
    minHeight: STAGE_SIZE.action,
    borderRadius: capsule(STAGE_SIZE.action),
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.lg,
    overflow: "hidden",
  },
  actionLabel: { fontWeight: "600", textAlign: "center" },
  // The field and its control sit side by side, close enough to merge.
  composerRow: { flexDirection: "row", alignItems: "flex-end", gap: MERGE_SPACING },
  field: {
    flex: 1,
    minHeight: STAGE_SIZE.composer,
    borderRadius: capsule(STAGE_SIZE.composer),
    justifyContent: "center",
    paddingHorizontal: spacing.md + 4,
    overflow: "hidden",
  },
  input: { fontFamily: ROUNDED, paddingVertical: spacing.sm + 2 },
  promptWrap: { position: "absolute", left: spacing.md + 4, right: spacing.md + 4 },
  controlTarget: {
    width: STAGE_SIZE.composer,
    height: STAGE_SIZE.composer,
    minHeight: MIN_TAP,
  },
  control: {
    width: STAGE_SIZE.composer,
    height: STAGE_SIZE.composer,
    borderRadius: capsule(STAGE_SIZE.composer),
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  card: {
    minHeight: MIN_TAP,
    borderRadius: STAGE_RADIUS.card,
    borderCurve: "continuous",
    paddingLeft: spacing.md + 2,
    paddingRight: spacing.sm + 6,
    paddingVertical: spacing.sm + 4,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm + 2,
    // A wrap item gets no shrink in React Native: bound it so a long option
    // label wraps inside the card instead of running off-screen (INT-136).
    maxWidth: "100%",
  },
  cardLabel: { flexShrink: 1, fontWeight: "600" },
  check: {
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
  },
});
