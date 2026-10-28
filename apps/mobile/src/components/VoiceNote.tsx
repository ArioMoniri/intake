/**
 * Dev-lane voice note button (INT-194): speak → our whisper-tr ASR on the
 * team box → transcript into the patient-note field. Faceless, calm — a
 * quiet pill that breathes text, not an orb persona (the real conversation
 * surface is INT-132/135). Gated by the voice consent AND __DEV__ (this is
 * the demo bridge, not the product voice runtime — see lib/voice.ts).
 *
 * INT-559: the pill runs one capture turn (lib/capture/turn.ts) — expo-audio's
 * PCM stream into a bounded in-memory buffer, handed to the ASR daemon as
 * bytes. No recorder, no file. Unmount and the app leaving the foreground
 * close the microphone and zero the buffer without sending anything.
 */
import { useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet } from "react-native";
import { AudioModule } from "expo-audio";

import { AppText, useTheme } from "@/components/Themed";
import { useAppStateChange } from "@/lib/capture/appState";
import { createExpoPcmStream } from "@/lib/capture/expoStream";
import { createCaptureTurn, type CaptureTurn } from "@/lib/capture/turn";
import { t } from "@/lib/i18n";
import { transcribeSegment } from "@/lib/voice";
import { radius, spacing } from "@/lib/theme";

type Phase = "idle" | "recording" | "processing" | "unreachable" | "denied";

export function VoiceNote({ onTranscript }: { onTranscript: (text: string) => void }) {
  const theme = useTheme();
  const [phase, setPhase] = useState<Phase>("idle");
  const turnRef = useRef<CaptureTurn | null>(null);
  const closedRef = useRef(false);

  // Unmount: the microphone closes and the buffer zeroes; nothing is sent.
  useEffect(() => {
    return () => {
      closedRef.current = true;
      turnRef.current?.discard();
      turnRef.current = null;
    };
  }, []);

  // Leaving the foreground is the same trigger; the pill goes back to idle
  // rather than pretend it still holds what was said.
  useAppStateChange((status) => {
    if (status !== "active" && turnRef.current !== null) {
      turnRef.current.discard();
      turnRef.current = null;
      setPhase("idle");
    }
  });

  const start = async () => {
    const permission = await AudioModule.requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setPhase("denied");
      return;
    }
    await AudioModule.setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    const turn = createCaptureTurn({
      createStream: createExpoPcmStream,
      transcribe: transcribeSegment,
      closed: () => closedRef.current,
    });
    turnRef.current = turn;
    let opened = false;
    try {
      opened = await turn.open();
    } catch {
      opened = false; // the input could not be opened: nothing happened, the pill stays idle
    }
    if (!opened) {
      turnRef.current = null;
      setPhase("idle");
      return;
    }
    setPhase("recording");
  };

  const stop = async () => {
    const turn = turnRef.current;
    turnRef.current = null;
    if (turn === null) {
      setPhase("idle");
      return;
    }
    setPhase("processing");
    try {
      const text = await turn.finish();
      if (text !== null && text.length > 0) {
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
        {
          backgroundColor: phase === "recording" ? theme.primarySoft : theme.surface,
          borderColor: phase === "recording" ? theme.primary : theme.border,
        },
      ]}
    >
      <AppText role="label" color={phase === "recording" ? "primary" : "inkSoft"}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pill: {
    borderRadius: radius.chip,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    alignSelf: "flex-start",
    minHeight: 44,
    justifyContent: "center",
  },
});
