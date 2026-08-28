/**
 * Spoken dialogue intake screen (INT-233): turn-by-turn voice conversation
 * over the department pack. Per step the agent SPEAKS the question
 * (FreyaTTS clip synthesized ONCE per session from catalog tr strings —
 * never LLM output, never patient words), then LISTENS; the transcript is
 * extracted against that single question and the candidate comes back as
 * a spoken confirmation with the answer pre-selected. Tap to confirm, or
 * speak the correction.
 *
 * The imperative side (reducer, playback, recorder, extract, teardown)
 * lives in lib/dialogue/useDialogueSession.ts; this file renders state and
 * stores answers. DISTURBABLE: during agent speech a tap anywhere on the
 * speech surface stops playback instantly and opens the mic; during
 * listening, "Bitirdim" or a tap on the surface stops.
 *
 * Honesty + invariants:
 * - Nothing here is triage or a diagnosis; candidates are suggestions the
 *   patient confirms (invariant 1 posture, same as INT-199).
 * - Patient quotes are DISPLAYED as text, never synthesized; the numeral
 *   guard sits before every /synthesize call (invariant 22 mirror).
 * - Agent clips are cache files deleted on unmount and session end;
 *   PATIENT recordings keep lib/voice.ts's delete-after-upload posture
 *   (invariant 3 governs those, and it is untouched here).
 * - Text is the fallback everywhere: "Yazarak yanıtlayın" skips the voice
 *   loop for the current step only; any service failure lands in the
 *   existing manual steps via the outer machine, answers intact.
 *
 * DEV-TIER: this is the honest in-app dev dialogue over the HTTP bridges;
 * the production path is the LiveKit Talker (files/03 §4.9, files/13).
 */
import { useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
  useColorScheme,
} from "react-native";

import { GLASS_BAR_CLEARANCE, GlassBar } from "@/components/GlassBar";
import { Kicker } from "@/components/Kicker";
import {
  AppText,
  Card,
  PrimaryButton,
  SecondaryButton,
  useFontScale,
  useTheme,
} from "@/components/Themed";
import { useDialogueSession } from "@/lib/dialogue/useDialogueSession";
import { t } from "@/lib/i18n";
import type { IntakeQuestion } from "@/lib/intake/questions";
import { useSession } from "@/lib/session";
import { fonts, radius, scaledSize, spacing } from "@/lib/theme";

interface DialogueIntakeProps {
  visitId: string | undefined;
  questions: readonly IntakeQuestion[];
  /** The pack label the extract daemon receives (the visit's department). */
  packName: string;
  /** Leave the dialogue: "failure" shows the notice in the manual steps,
   * "skip" lands there quietly. Prior answers are already committed. */
  onExit: (reason: "failure" | "skip") => void;
}

export function DialogueIntake({ visitId, questions, packName, onExit }: DialogueIntakeProps) {
  const router = useRouter();
  const theme = useTheme();
  const dark = useColorScheme() === "dark";
  const fontScale = useFontScale();
  const { updateNote } = useSession();

  const session = useDialogueSession({
    questions,
    packName,
    onDone: () => router.replace(`/(tabs)/visits/${visitId}/review`),
    onFailed: () => onExit("failure"),
  });
  const { state } = session;

  // On-screen answer state for the current step (seeded from the candidate
  // when a confirm turn opens; editable by the patient before confirming).
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");

  // Seed the on-screen answer when a confirm or typing context opens.
  const seedKeyRef = useRef("");
  useEffect(() => {
    const step = "step" in state ? state.step : -1;
    const key = `${state.phase}:${step}:${state.phase === "speaking" ? state.intent : ""}`;
    if (seedKeyRef.current === key) {
      return;
    }
    seedKeyRef.current = key;
    if (step < 0) {
      return;
    }
    const question = questions[step];
    const candidate =
      state.phase === "confirming" || (state.phase === "speaking" && state.intent === "confirm")
        ? state.candidate
        : state.phase === "typing"
          ? state.prefill
          : null;
    if (question.kind === "text") {
      setText(candidate?.values.join(" ") ?? "");
    } else {
      setSelected(candidate?.values ?? []);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed dedupe above; questions is stable
  }, [state]);

  const step = "step" in state ? state.step : questions.length - 1;
  const question = questions[step];
  const last = step === questions.length - 1;

  /** Store this step's answer, then let the machine advance. */
  const commit = (kind: "confirm" | "commit") => {
    const values =
      question.kind === "text" ? (text.trim().length > 0 ? [text.trim()] : []) : [...selected];
    if (visitId) {
      updateNote(visitId, { type: "answer", questionId: question.id, values });
    }
    session.advance(kind);
  };

  const exitToTyping = async () => {
    await session.leave();
    onExit("skip");
  };

  if (state.phase === "done" || state.phase === "failed") {
    return null; // terminal callbacks route away / hand over
  }

  const busy = state.phase === "transcribing" || state.phase === "extracting";
  const surfaceActive = state.phase === "speaking" || state.phase === "listening";
  const confirmOpen = state.phase === "confirming";
  const candidateQuote =
    state.phase === "confirming" || (state.phase === "speaking" && state.intent === "confirm")
      ? state.candidate.quote
      : null;

  return (
    <>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: GLASS_BAR_CLEARANCE }]}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        <Kicker label={t("dialogue.kicker")} tone="accent" />
        <View style={styles.progressRow}>
          {questions.map((item, i) => (
            <View
              key={item.id}
              style={[
                styles.progressDot,
                { backgroundColor: i <= step ? theme.primary : theme.border },
              ]}
            />
          ))}
          <AppText role="caption" color="inkFaint">
            {step + 1} / {questions.length}
          </AppText>
        </View>

        <AppText role="hero">{t(question.titleKey)}</AppText>
        {question.hintKey ? (
          <AppText role="body" color="inkSoft">
            {t(question.hintKey)}
          </AppText>
        ) : null}

        {surfaceActive ? (
          // The speech surface: one large target. During agent speech a tap
          // is the barge-in; during listening it is tap-to-stop.
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={
              state.phase === "speaking" ? t("dialogue.speakingHint") : t("voiceFirst.listening")
            }
            onPress={state.phase === "speaking" ? session.bargeIn : session.finishListening}
            style={[
              styles.surface,
              {
                backgroundColor: state.phase === "listening" ? theme.primarySoft : theme.surface,
                borderColor: state.phase === "listening" ? theme.primary : theme.border,
              },
            ]}
          >
            {state.phase === "speaking" && !session.playing ? (
              <ActivityIndicator color={theme.primary} />
            ) : null}
            <AppText role="title" color={state.phase === "listening" ? "primary" : "ink"}>
              {state.phase === "listening"
                ? t("voiceFirst.listening")
                : session.playing
                  ? t("dialogue.speaking")
                  : t("dialogue.preparing")}
            </AppText>
            <AppText role="caption" color="inkFaint">
              {state.phase === "speaking"
                ? t("dialogue.speakingHint")
                : t("dialogue.listeningHint")}
            </AppText>
          </Pressable>
        ) : null}

        {busy ? (
          <View style={styles.statusRow}>
            <ActivityIndicator color={theme.primary} />
            <AppText role="label" color="inkSoft">
              {state.phase === "transcribing"
                ? t("voiceFirst.transcribing")
                : t("voiceFirst.preparing")}
            </AppText>
          </View>
        ) : null}

        {candidateQuote !== null && candidateQuote.length > 0 ? (
          // Provenance, verbatim and DISPLAY-ONLY: the patient's words are
          // rendered as text here and are never sent to the TTS.
          <Card>
            <AppText role="caption" color="inkFaint">
              {t("voiceFirst.saidLabel")}
            </AppText>
            <AppText role="body" color="inkSoft">
              “{candidateQuote}”
            </AppText>
          </Card>
        ) : null}

        {(confirmOpen || state.phase === "typing") && question.kind !== "text" ? (
          <View style={styles.chipWrap}>
            {question.options!.map((option) => {
              const on = selected.includes(option.id);
              return (
                <Pressable
                  key={option.id}
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: on }}
                  onPress={() =>
                    setSelected((prev) =>
                      question.kind === "single"
                        ? [option.id]
                        : prev.includes(option.id)
                          ? prev.filter((x) => x !== option.id)
                          : [...prev, option.id],
                    )
                  }
                  style={[
                    styles.chip,
                    {
                      backgroundColor: on ? theme.primarySoft : theme.surface,
                      borderColor: on ? theme.primary : dark ? "transparent" : theme.border,
                    },
                  ]}
                >
                  <AppText role="label" color={on ? "primary" : "ink"}>
                    {t(option.labelKey)}
                  </AppText>
                </Pressable>
              );
            })}
          </View>
        ) : null}

        {(confirmOpen || state.phase === "typing") && question.kind === "text" ? (
          <TextInput
            accessibilityLabel={t(question.titleKey)}
            value={text}
            onChangeText={setText}
            multiline
            style={[
              styles.textField,
              {
                backgroundColor: theme.surface,
                borderColor: theme.border,
                color: theme.ink,
                fontSize: scaledSize("body", fontScale),
              },
            ]}
          />
        ) : null}

        {state.phase !== "typing" ? (
          // Text is the fallback everywhere: quiet, always present, and it
          // skips the voice loop for THIS step only.
          <View style={styles.fallbackRow}>
            <SecondaryButton
              label={t("dialogue.typeThisStep")}
              onPress={() => void session.typeThisStep()}
            />
          </View>
        ) : null}
        <Pressable accessibilityRole="button" onPress={() => void exitToTyping()}>
          <AppText role="caption" color="inkFaint">
            {t("voiceFirst.typeInstead")}
          </AppText>
        </Pressable>
      </ScrollView>

      {state.phase === "listening" ? (
        <GlassBar>
          <PrimaryButton
            label={t("voiceFirst.stop")}
            onPress={() => void session.finishListening()}
          />
        </GlassBar>
      ) : null}
      {confirmOpen ? (
        <GlassBar>
          <View style={styles.barStack}>
            <PrimaryButton
              label={t("dialogue.confirm")}
              // Text steps may be confirmed empty (the pack says the free
              // note is optional); option steps need a selection.
              disabled={question.kind === "text" ? false : selected.length === 0}
              onPress={() => commit("confirm")}
            />
            <SecondaryButton
              label={t("dialogue.speakCorrection")}
              onPress={session.speakCorrection}
            />
          </View>
        </GlassBar>
      ) : null}
      {state.phase === "typing" ? (
        <GlassBar>
          <PrimaryButton
            label={last ? t("intake.finish") : t("intake.next")}
            disabled={question.kind === "text" ? false : selected.length === 0}
            onPress={() => commit("commit")}
          />
        </GlassBar>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, padding: spacing.screen },
  progressRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  progressDot: { width: 8, height: 8, borderRadius: radius.chip },
  surface: {
    borderRadius: radius.control,
    borderWidth: 1,
    minHeight: 160,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    padding: spacing.md,
  },
  statusRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    borderRadius: radius.chip,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    minHeight: 44,
    justifyContent: "center",
  },
  textField: {
    borderRadius: radius.control,
    borderWidth: 1,
    minHeight: 120,
    padding: spacing.md,
    textAlignVertical: "top",
    fontFamily: fonts.sans,
  },
  fallbackRow: { marginTop: spacing.sm },
  barStack: { gap: spacing.sm },
});
