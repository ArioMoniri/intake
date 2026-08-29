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
 */
import { useEffect } from "react";
import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import { GLASS_BAR_CLEARANCE } from "@/components/GlassBar";
import { Kicker } from "@/components/Kicker";
import { AppText, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import type { VoiceIntakeAction } from "@/lib/intake/voiceFirst";
import { reachableAsrBaseUrl } from "@/lib/voice";
import { spacing } from "@/lib/theme";

interface DialogueGateProps {
  dispatch: (action: VoiceIntakeAction) => void;
}

export function DialogueGate({ dispatch }: DialogueGateProps) {
  const theme = useTheme();

  useEffect(() => {
    let stale = false;
    void reachableAsrBaseUrl().then((base) => {
      if (!stale) {
        dispatch(base !== null ? { type: "voice_ready" } : { type: "voice_unavailable" });
      }
    });
    return () => {
      stale = true;
    };
  }, [dispatch]);

  return (
    <View style={styles.content}>
      <Kicker label={t("dialogue.kicker")} tone="accent" />
      <AppText role="hero">{t("dialogue.entryTitle")}</AppText>
      <AppText role="body" color="inkSoft">
        {t("dialogue.entryBody")}
      </AppText>
      <View style={styles.statusRow}>
        <ActivityIndicator color={theme.primary} />
        <AppText role="label" color="inkSoft">
          {t("voiceFirst.checking")}
        </AppText>
      </View>
      <View style={styles.typedRow}>
        <Pressable accessibilityRole="button" onPress={() => dispatch({ type: "skip" })}>
          <AppText role="caption" color="inkFaint">
            {t("voiceFirst.typeInstead")}
          </AppText>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  content: {
    flex: 1,
    gap: spacing.md,
    padding: spacing.screen,
    paddingBottom: GLASS_BAR_CLEARANCE,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  typedRow: { marginTop: spacing.md },
});
