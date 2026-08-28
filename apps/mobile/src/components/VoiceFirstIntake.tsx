/**
 * Voice-first intake entry (INT-199): the FIRST step of a fresh intake when
 * the dev-lane voice is available — the patient tells the complaint in their
 * own words, we transcribe (whisper bridge, INT-194) and ask the extract
 * daemon for per-question ANSWER SUGGESTIONS, then hand over to the normal
 * one-question-per-turn steps with each suggestion pre-selected and the
 * patient's verbatim words as provenance.
 *
 * Honesty rules: the waiting states say what is happening and can take a
 * while; the manual path ("Yazarak devam edin") stays visible in every
 * phase; any failure lands in the exact manual flow — never a dead end.
 * Recording files are deleted right after upload, and on skip (invariant 3
 * posture — see lib/voice.ts).
 */
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { AudioModule, RecordingPresets, useAudioRecorder } from "expo-audio";

import { GLASS_BAR_CLEARANCE, GlassBar } from "@/components/GlassBar";
import { Kicker } from "@/components/Kicker";
import { AppText, PrimaryButton, SecondaryButton, useTheme } from "@/components/Themed";
import { configuredServiceCandidates } from "@/lib/dev/expoHosts";
import { EXTRACT_PORT, extractFromCandidates } from "@/lib/extract";
import { t } from "@/lib/i18n";
import type { IntakeQuestion } from "@/lib/intake/questions";
import {
  prefillForPack,
  type VoiceIntakeAction,
  type VoiceIntakeState,
} from "@/lib/intake/voiceFirst";
import { discardRecording, reachableAsrBaseUrl, transcribeRecording } from "@/lib/voice";
import { spacing } from "@/lib/theme";

interface VoiceFirstIntakeProps {
  state: Exclude<VoiceIntakeState, { phase: "steps" } | { phase: "dialogue" }>;
  dispatch: (action: VoiceIntakeAction) => void;
  questions: readonly IntakeQuestion[];
  /** The pack label the daemon receives (the visit's department). */
  packName: string;
}

export function VoiceFirstIntake({ state, dispatch, questions, packName }: VoiceFirstIntakeProps) {
  const theme = useTheme();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [denied, setDenied] = useState(false);
  const cancelledRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  const phase = state.phase;

  useEffect(() => {
    if (phase !== "gate") {
      return;
    }
    let stale = false;
    reachableAsrBaseUrl().then((base) => {
      if (!stale) {
        dispatch(base !== null ? { type: "voice_ready" } : { type: "voice_unavailable" });
      }
    });
    return () => {
      stale = true;
    };
  }, [phase, dispatch]);

  const start = async () => {
    const permission = await AudioModule.requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setDenied(true);
      return;
    }
    setDenied(false);
    await AudioModule.setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
    dispatch({ type: "record" });
  };

  const stopAndProcess = async () => {
    dispatch({ type: "stop" });
    await recorder.stop();
    const uri = recorder.uri;
    if (uri === null) {
      dispatch({ type: "failure" });
      return;
    }
    if (cancelledRef.current) {
      await discardRecording(uri);
      return;
    }
    let transcript = "";
    try {
      transcript = await transcribeRecording(uri);
    } catch {
      dispatch({ type: "failure" });
      return;
    }
    if (cancelledRef.current) {
      return;
    }
    if (transcript.length === 0) {
      dispatch({ type: "failure" });
      return;
    }
    dispatch({ type: "transcript" });
    const controller = new AbortController();
    abortRef.current = controller;
    const result = await extractFromCandidates(
      configuredServiceCandidates(EXTRACT_PORT),
      transcript,
      packName,
      questions,
      { signal: controller.signal },
    );
    if (cancelledRef.current) {
      return;
    }
    if (result.ok) {
      dispatch({ type: "candidates", prefill: prefillForPack(questions, result.candidates) });
    } else if (result.reason !== "aborted") {
      dispatch({ type: "failure" });
    }
  };

  const skip = async () => {
    cancelledRef.current = true;
    abortRef.current?.abort();
    if (phase === "recording") {
      await recorder.stop();
      const uri = recorder.uri;
      if (uri !== null) {
        await discardRecording(uri);
      }
    }
    dispatch({ type: "skip" });
  };

  const busy = phase === "transcribing" || phase === "extracting";
  const status =
    phase === "gate"
      ? t("voiceFirst.checking")
      : phase === "recording"
        ? t("voiceFirst.listening")
        : phase === "transcribing"
          ? t("voiceFirst.transcribing")
          : phase === "extracting"
            ? t("voiceFirst.preparing")
            : denied
              ? t("voice.permission")
              : null;

  return (
    <>
      <View style={styles.content}>
        <Kicker label={t("voiceFirst.kicker")} tone="accent" />
        <AppText role="hero">{t("voiceFirst.title")}</AppText>
        <AppText role="body" color="inkSoft">
          {t("voiceFirst.body")}
        </AppText>
        {phase === "gate" || phase === "offer" ? (
          <AppText role="caption" color="inkFaint">
            {t("dialogue.offerHint")}
          </AppText>
        ) : null}
        {status !== null ? (
          <View style={styles.statusRow}>
            {busy ? <ActivityIndicator color={theme.primary} /> : null}
            <AppText role="label" color={phase === "recording" ? "primary" : "inkSoft"}>
              {status}
            </AppText>
          </View>
        ) : null}
        {phase === "extracting" ? (
          <AppText role="caption" color="inkFaint">
            {t("voiceFirst.preparingHint")}
          </AppText>
        ) : null}
        <View style={styles.skipRow}>
          <SecondaryButton
            label={busy ? t("voiceFirst.cancel") : t("voiceFirst.typeInstead")}
            onPress={skip}
          />
        </View>
      </View>
      {phase === "gate" || phase === "offer" || phase === "recording" ? (
        <GlassBar>
          {phase === "recording" ? (
            <PrimaryButton label={t("voiceFirst.stop")} onPress={stopAndProcess} />
          ) : (
            // Two primary voice paths (INT-233): the one-shot "tell it all
            // at once" stays first; the turn-by-turn spoken dialogue is the
            // second door into the same pack. Both gate on the ASR probe.
            <View style={styles.pathStack}>
              <PrimaryButton
                label={t("voiceFirst.start")}
                disabled={phase === "gate"}
                onPress={start}
              />
              <SecondaryButton
                label={t("dialogue.start")}
                disabled={phase === "gate"}
                onPress={() => dispatch({ type: "dialogue" })}
              />
            </View>
          )}
        </GlassBar>
      ) : null}
    </>
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
  skipRow: { marginTop: spacing.md },
  pathStack: { gap: spacing.sm },
});
