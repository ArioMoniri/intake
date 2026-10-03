/**
 * Dev-lane voice note button (INT-194): record → our whisper-tr ASR on the
 * team box → transcript into the patient-note field. Faceless, calm — a
 * quiet pill that breathes text, not an orb persona (the real conversation
 * surface is INT-132/135). Gated by the voice consent AND __DEV__ (this is
 * the demo bridge, not the product voice runtime — see lib/voice.ts).
 */
import { useState } from "react";
import { Pressable, StyleSheet } from "react-native";
import { AudioModule, RecordingPresets, useAudioRecorder } from "expo-audio";

import { AppText, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { transcribeRecording } from "@/lib/voice";
import { radius, spacing } from "@/lib/theme";

type Phase = "idle" | "recording" | "processing" | "unreachable" | "denied";

export function VoiceNote({ onTranscript }: { onTranscript: (text: string) => void }) {
  const theme = useTheme();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [phase, setPhase] = useState<Phase>("idle");

  const start = async () => {
    const permission = await AudioModule.requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setPhase("denied");
      return;
    }
    await AudioModule.setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
    setPhase("recording");
  };

  const stop = async () => {
    setPhase("processing");
    await recorder.stop();
    const uri = recorder.uri;
    if (!uri) {
      setPhase("idle");
      return;
    }
    try {
      const text = await transcribeRecording(uri);
      if (text.length > 0) {
        onTranscript(text);
      }
      setPhase("idle");
    } catch {
      setPhase("unreachable");
    }
  };

  const label =
    phase === "recording"
      ? t("voice.listening")
      : phase === "processing"
        ? t("voice.processing")
        : phase === "unreachable"
          ? t("voice.unreachable")
          : phase === "denied"
            ? t("voice.permission")
            : t("voice.speakToAdd");

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={phase === "processing"}
      onPress={phase === "recording" ? stop : start}
      style={[
        styles.pill,
        // INT-433: a filled, tinted capsule like the chips beside it, not an
        // outline. Recording inverts to the filled tint, and its label
        // changes too, so the state is never the colour alone.
        { backgroundColor: phase === "recording" ? theme.primary : theme.primarySoft },
      ]}
    >
      <AppText role="label" color={phase === "recording" ? "onPrimary" : "primary"}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pill: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    alignSelf: "flex-start",
    minHeight: 44,
    justifyContent: "center",
  },
});
