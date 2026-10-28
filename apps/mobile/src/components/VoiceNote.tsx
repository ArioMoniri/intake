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
 * close the microphone and zero the buffer without sending anything — through
 * the same one-microphone holder the dialogue uses (lib/capture/microphone.ts),
 * so a discard that lands while the audio session switches or the stream
 * starts reaches that open too (the review of #964).
 */
import { useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet } from "react-native";
import { AudioModule } from "expo-audio";

import { AppText, useTheme } from "@/components/Themed";
import { useAppStateChange } from "@/lib/capture/appState";
import { createExpoPcmStream } from "@/lib/capture/expoStream";
import { createMicrophone, type Microphone } from "@/lib/capture/microphone";
import { createCaptureTurn } from "@/lib/capture/turn";
import { t } from "@/lib/i18n";
import { transcribeSegment } from "@/lib/voice";
import { radius, spacing } from "@/lib/theme";

type Phase = "idle" | "recording" | "processing" | "unreachable" | "denied";

export function VoiceNote({ onTranscript }: { onTranscript: (text: string) => void }) {
  const theme = useTheme();
  const [phase, setPhase] = useState<Phase>("idle");
  const closedRef = useRef(false);
  const microphoneRef = useRef<Microphone | null>(null);
  const microphone = (): Microphone => {
    microphoneRef.current ??= createMicrophone({
      prepare: () =>
        AudioModule.setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true }),
      createTurn: (closed) =>
        createCaptureTurn({
          createStream: createExpoPcmStream,
          transcribe: transcribeSegment,
          closed,
        }),
      closed: () => closedRef.current,
    });
    return microphoneRef.current;
  };

  // Unmount: the microphone closes and the buffer zeroes; nothing is sent.
  useEffect(() => {
    return () => {
      closedRef.current = true;
      microphoneRef.current?.discard();
    };
  }, []);

  // Leaving the foreground is the same trigger, an open still in flight
  // included; the pill goes back to idle rather than pretend it still holds
  // what was said.
  useAppStateChange((status) => {
    const mic = microphoneRef.current;
    if (status !== "active" && mic !== null) {
      const held = mic.current() !== null;
      mic.discard();
      if (held) {
        setPhase("idle");
      }
    }
  });

  const start = async () => {
    // Asked before the microphone's open, so the system prompt's own
    // `inactive` does not abandon the open it is asking for.
    const permission = await AudioModule.requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setPhase("denied");
      return;
    }
    let opened = false;
    try {
      opened = await microphone().open();
    } catch {
      opened = false; // the input could not be opened: nothing happened, the pill stays idle
    }
    setPhase(opened ? "recording" : "idle");
  };

  const stop = async () => {
    const turn = microphoneRef.current?.take() ?? null;
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
