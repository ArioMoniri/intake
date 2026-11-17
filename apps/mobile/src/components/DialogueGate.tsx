/**
 * The intake door (INT-239). Entering a fresh intake lands here for one
 * beat — the ASR probe — and then goes STRAIGHT into the spoken dialogue.
 * There is no chooser: karşılıklı konuşma is the entry, and mic permission
 * is asked by the dialogue session itself on its first clip.
 *
 * Typed intake stays reachable as the quiet second door ("Yazarak devam
 * edin"): the blueprint's `typed` profile (files/03 §4.9.1) is an
 * accessibility path for patients who cannot speak, not a co-equal first
 * button — and inside the dialogue the always-present composer covers
 * mixed use, so nobody has to choose a mode up front.
 *
 * An unreachable voice lane falls to the typed steps quietly, without a
 * failure notice: nothing was attempted yet, so there is nothing to
 * apologise for (the notice belongs to a voice run that actually broke).
 *
 * INT-246 keeps that argument intact for patients and adds nothing to this
 * screen. The probe now reports its DETAIL (which bases, how each failed)
 * through `onProbe`; the intake screen hands that to DevVoiceBanner, which
 * renders only under `__DEV__`. It could not live here in any case — this
 * component unmounts the instant the fallback fires.
 */
import { useEffect } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { AnnouncedRegion } from "@/components/Announced";
import { Kicker } from "@/components/Kicker";
import { AppText, useTheme } from "@/components/Themed";
import { verticalSlop } from "@/lib/a11y/target";
import type { ReachabilityReport } from "@/lib/dev/hosts";
import { t } from "@/lib/i18n";
import type { VoiceIntakeAction } from "@/lib/intake/voiceFirst";
import { probeAsrReachability } from "@/lib/voice";
import { spacing } from "@/lib/theme";

interface DialogueGateProps {
  dispatch: (action: VoiceIntakeAction) => void;
  /**
   * Diagnostic sink for the probe result (INT-246). Must be a stable
   * reference — a fresh closure on every render would re-run the effect and
   * re-probe a host already known to be dead.
   */
  onProbe?: (report: ReachabilityReport) => void;
}

export function DialogueGate({ dispatch, onProbe }: DialogueGateProps) {
  const theme = useTheme();
  // INT-284: the gate reserved `GLASS_BAR_CLEARANCE` for a bar it does not
  // render — intake.tsx shows the gate, the dialogue OR the typed steps, and
  // only the latter two carry a bar, so that was padding with no referent.
  // What the gate does own is the physical bottom edge (the flow drops the
  // bottom safe edge), so the home-indicator zone is its own to clear.
  const insets = useSafeAreaInsets();

  useEffect(() => {
    let stale = false;
    void probeAsrReachability().then((report) => {
      if (!stale) {
        onProbe?.(report);
        dispatch(report.base !== null ? { type: "voice_ready" } : { type: "voice_unavailable" });
      }
    });
    return () => {
      stale = true;
    };
  }, [dispatch, onProbe]);

  return (
    // A hero line, a body paragraph and two rows: at the largest text step
    // that is taller than the flow's body box, and a View cannot be moved.
    <ScrollView
      contentContainerStyle={[
        styles.content,
        { paddingBottom: spacing.xl + Math.max(insets.bottom, spacing.md) },
      ]}
    >
      <Kicker label={t("dialogue.kicker")} tone="accent" />
      <AppText role="hero" heading>
        {t("dialogue.entryTitle")}
      </AppText>
      <AppText role="body" color="inkSoft">
        {t("dialogue.entryBody")}
      </AppText>
      {/* The probe is a wait, and a spinner is invisible to a screen
          reader — the row announces itself instead (SC 4.1.2, 4.1.3), on
          both platforms since INT-362. */}
      <AnnouncedRegion
        tone="status"
        merged
        message={t("voiceFirst.checking")}
        style={styles.statusRow}
      >
        <ActivityIndicator color={theme.primary} />
        <AppText role="label" color="inkSoft">
          {t("voiceFirst.checking")}
        </AppText>
      </AnnouncedRegion>
      <View style={styles.typedRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("voiceFirst.typeInstead")}
          accessibilityHint={t("a11y.typedHint")}
          // A lone 18 pt caption line: slop lifts the target to the floor
          // without turning the quiet second door into a button.
          hitSlop={verticalSlop(18)}
          onPress={() => dispatch({ type: "skip" })}
        >
          <AppText role="caption" color="inkFaint">
            {t("voiceFirst.typeInstead")}
          </AppText>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  // `flexGrow`, never `flex`: the column is shorter than the box at the small
  // steps and taller at the large ones, and flexGrow is the one rule that
  // fills the box while it fits and scrolls once it does not.
  content: {
    flexGrow: 1,
    gap: spacing.md,
    padding: spacing.screen,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  typedRow: { marginTop: spacing.md },
});
