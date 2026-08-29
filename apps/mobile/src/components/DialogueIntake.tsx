/**
 * Voice chat surface (INT-235, ask-ahead pass). The transcript IS the
 * screen: agent turns as quiet left-aligned surface bubbles (the question
 * the agent speaks — the TEXT is there instantly, audio catches up),
 * patient turns as right-aligned tonal bubbles that appear at the mic and
 * are replaced IN PLACE by the ASR text. State lives INSIDE the stream —
 * the listening pulse, the "Yazıya dökülüyor…" shimmer on the pending
 * bubble, the quiet end-of-dialogue settling row. Never a takeover.
 *
 * ASK-AHEAD: the next question speaks the moment an utterance is taken;
 * extraction reconciles behind into the section panel (the "Not oluşuyor"
 * strip → muayene-section sheet, pack-driven labels). A landed suggestion
 * gets a quick spoken confirm turn — candidate pre-selected as inline
 * chips, one tap on the bone CTA. The persistent composer makes voice and
 * text ONE conversation: a typed message is an utterance without the ASR
 * hop (ChatGPT voice register — see docs/design/mobile-ui.md "Voice chat
 * surface" for the Mobbin pull).
 *
 * DISTURBABLE unchanged: a tap on the SPEAKING bubble stops playback in
 * the same JS tick (player.pause() before dispatch) and opens the mic.
 *
 * Honesty + invariants, carried from INT-233:
 * - Nothing here is triage or a diagnosis; candidates are suggestions the
 *   patient confirms (chat confirm turn, panel row, or the manual steps
 *   after handoff) — nothing auto-commits (invariant 1 posture).
 * - Patient quotes are DISPLAYED as text, never synthesized; the numeral
 *   guard sits before every /synthesize call (invariant 22 mirror).
 * - Agent clips are cache files deleted on unmount and session end;
 *   PATIENT recordings keep lib/voice.ts's delete-after-upload posture
 *   (invariant 3 governs those, and it is untouched here).
 * - Any hard service failure lands in the existing manual steps via the
 *   outer machine, committed answers intact; a settled dialogue with
 *   questions left hands ONLY those to the manual steps, suggestions
 *   riding along as prefill.
 *
 * DEV-TIER: this is the honest in-app dev dialogue over the HTTP bridges;
 * the production path is the LiveKit Talker (files/03 §4.9, files/13).
 */
import { useRouter } from "expo-router";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ActivityIndicator,
  Animated,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
  useColorScheme,
} from "react-native";
import { SymbolView } from "expo-symbols";

import { GLASS_BAR_CLEARANCE, GlassBar } from "@/components/GlassBar";
import { Kicker } from "@/components/Kicker";
import { SectionSheet, SectionStrip } from "@/components/SectionPanel";
import {
  AppText,
  PrimaryButton,
  SecondaryButton,
  useFontScale,
  useTheme,
} from "@/components/Themed";
import { sectionPanelModel } from "@/lib/dialogue/sectionPanel";
import type { StreamEntry } from "@/lib/dialogue/stream";
import { useDialogueSession } from "@/lib/dialogue/useDialogueSession";
import { t } from "@/lib/i18n";
import { optionLabelKey, type IntakeQuestion } from "@/lib/intake/questions";
import type { PrefillMap } from "@/lib/intake/voiceFirst";
import { useSession } from "@/lib/session";
import { fonts, radius, scaledSize, spacing } from "@/lib/theme";

/** The dialogue bar stacks the strip, up to two CTAs and the composer. */
const DIALOGUE_BAR_CLEARANCE = GLASS_BAR_CLEARANCE + 176;

interface DialogueIntakeProps {
  visitId: string | undefined;
  questions: readonly IntakeQuestion[];
  /** The pack label the extract daemon receives (the visit's department). */
  packName: string;
  /** Hard service failure — the manual steps show the honest notice.
   * Prior answers are already committed per confirm. */
  onFailed: () => void;
  /** Dialogue over with questions left (or left by choice): the manual
   * steps take ONLY those, unconfirmed suggestions riding as prefill. */
  onHandoff: (prefill: PrefillMap) => void;
}

/** Option ids → catalog labels; free text passes through verbatim. */
function valueLabels(questionId: string, values: readonly string[]): string {
  return values
    .map((value) => {
      const key = optionLabelKey(questionId, value);
      return key ? t(key) : value;
    })
    .join(", ");
}

/** Quiet pulse for the open-mic turn — a single fading element, within
 * the 02 §5.2a budget (fades only, one animated element at a time). */
function PulseDot() {
  const theme = useTheme();
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.3, duration: 700, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);
  return <Animated.View style={[styles.pulseDot, { backgroundColor: theme.primary, opacity }]} />;
}

export function DialogueIntake({
  visitId,
  questions,
  packName,
  onFailed,
  onHandoff,
}: DialogueIntakeProps) {
  const router = useRouter();
  const theme = useTheme();
  const dark = useColorScheme() === "dark";
  const fontScale = useFontScale();
  const { account, updateNote } = useSession();

  const session = useDialogueSession({
    questions,
    packName,
    onDone: () => router.replace(`/(tabs)/visits/${visitId}/review`),
    onFailed,
    onHandoff: (leftovers) => {
      // Confirmed answers are already in the note; the rest of the pack
      // goes to the manual steps with the suggestions as prefill.
      const prefill: PrefillMap = {};
      for (const [questionId, candidate] of Object.entries(leftovers)) {
        prefill[questionId] = { values: [...candidate.values], quote: candidate.quote };
      }
      onHandoff(prefill);
    },
  });
  const { state } = session;
  const { turn } = state;

  // On-screen selection for the live confirm turn (seeded pre-selected).
  const [selected, setSelected] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  // Seed the chips when a confirm turn opens (candidate pre-selected).
  const seedKeyRef = useRef("");
  useEffect(() => {
    const step = "step" in turn ? turn.step : -1;
    const key = `${turn.phase}:${step}`;
    if (seedKeyRef.current === key || step < 0) {
      return;
    }
    seedKeyRef.current = key;
    if (turn.phase === "confirming" || (turn.phase === "speaking" && turn.intent === "confirm")) {
      setSelected([...turn.candidate.values]);
    }
  }, [turn]);

  // The conversation reads bottom-up: keep the newest turn in view.
  const streamLength = state.stream.length;
  useEffect(() => {
    const frame = requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
    return () => cancelAnimationFrame(frame);
  }, [streamLength, turn.phase]);

  const step = "step" in turn ? turn.step : -1;
  const question = step >= 0 ? questions[step] : null;

  /** The confirm tap: store the answer, then let the machine skip ahead. */
  const confirmTurn = () => {
    if (turn.phase !== "confirming" || question === null) {
      return;
    }
    const values = question.kind === "text" ? [...turn.candidate.values] : [...selected];
    if (visitId) {
      updateNote(visitId, { type: "answer", questionId: question.id, values });
    }
    session.confirm(values);
  };

  /** Panel-row confirm of one pending suggestion (invariant 1: this tap
   * IS the patient's confirm — nothing commits without it). */
  const confirmRow = (questionId: string) => {
    const candidate = state.pending[questionId];
    if (candidate === undefined) {
      return;
    }
    if (visitId) {
      updateNote(visitId, { type: "answer", questionId, values: [...candidate.values] });
    }
    session.confirmPending(questionId);
  };

  const send = () => {
    const text = draft;
    setDraft("");
    void session.sendTyped(text);
  };

  const exitToSteps = async () => {
    const leftovers = state.pending;
    await session.leave();
    const prefill: PrefillMap = {};
    for (const [questionId, candidate] of Object.entries(leftovers)) {
      prefill[questionId] = { values: [...candidate.values], quote: candidate.quote };
    }
    onHandoff(prefill);
  };

  if (turn.phase === "done" || turn.phase === "failed" || turn.phase === "handoff") {
    return null; // terminal callbacks route away / hand over
  }

  const model = sectionPanelModel(questions, state, account?.medications ?? []);
  const chipsOpen = turn.phase === "confirming" && question !== null && question.kind !== "text";
  // While the agent speaks, the LAST logged agent turn is the live bubble.
  const liveAgentIndex = turn.phase === "speaking" ? state.stream.length - 1 : -1;

  const renderAgentBubble = (entry: StreamEntry, index: number) => {
    const live = index === liveAgentIndex;
    const bubbleStyle = [
      styles.bubble,
      styles.agentBubble,
      { backgroundColor: theme.surface, borderColor: dark ? "transparent" : theme.border },
    ];
    let body: ReactNode = null;
    if (entry.kind === "agent_question") {
      const q = questions.find((item) => item.id === entry.questionId);
      if (q === undefined) {
        return null;
      }
      body = (
        <>
          <AppText role="body">{t(q.titleKey)}</AppText>
          {q.hintKey ? (
            <AppText role="caption" color="inkSoft">
              {t(q.hintKey)}
            </AppText>
          ) : null}
        </>
      );
    } else if (entry.kind === "agent_confirm") {
      const q = questions.find((item) => item.id === entry.questionId);
      body =
        q?.kind === "text" ? (
          <AppText role="body">{t("dialogue.confirmTextGeneric")}</AppText>
        ) : (
          <>
            <AppText role="caption" color="inkSoft">
              {t("dialogue.confirmIntro")}
            </AppText>
            <AppText role="body">{valueLabels(entry.questionId, entry.values)}</AppText>
            <AppText role="caption" color="inkSoft">
              {t("dialogue.confirmAsk")}
            </AppText>
          </>
        );
    }
    if (!live) {
      return (
        <View key={index} style={bubbleStyle}>
          {body}
        </View>
      );
    }
    // The speaking bubble: tap = barge-in, playback stops in this tick.
    // The question TEXT is already on screen — audio only catches up.
    return (
      <Pressable
        key={index}
        accessibilityRole="button"
        accessibilityLabel={t("dialogue.speakingHint")}
        onPress={session.bargeIn}
        style={({ pressed }) => [...bubbleStyle, { opacity: pressed ? 0.7 : 1 }]}
      >
        {body}
        <View style={styles.stateRow}>
          {session.playing ? (
            <PulseDot />
          ) : (
            <ActivityIndicator size="small" color={theme.inkFaint} />
          )}
          <AppText role="caption" color="inkFaint">
            {session.playing ? t("dialogue.speakingHint") : t("dialogue.preparing")}
          </AppText>
        </View>
      </Pressable>
    );
  };

  const renderEntry = (entry: StreamEntry, index: number) => {
    if (entry.kind === "agent_question" || entry.kind === "agent_confirm") {
      return renderAgentBubble(entry, index);
    }
    // Patient turns, keyed by work id. A transcribing bubble is the
    // in-place stand-in the ASR text will replace (never a takeover).
    if (entry.status === "transcribing") {
      return (
        <View
          key={`w-${entry.workId}`}
          style={[styles.bubble, styles.patientBubble, { backgroundColor: theme.surfaceRaised }]}
        >
          <View style={styles.stateRow}>
            <ActivityIndicator size="small" color={theme.inkFaint} />
            <AppText role="caption" color="inkSoft">
              {t("dialogue.transcribing")}
            </AppText>
          </View>
        </View>
      );
    }
    return (
      <View
        key={`w-${entry.workId}`}
        style={[styles.bubble, styles.patientBubble, { backgroundColor: theme.surfaceRaised }]}
      >
        <AppText role="body">{entry.text}</AppText>
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        <Kicker label={t("dialogue.kicker")} tone="accent" />

        {state.stream.map(renderEntry)}

        {turn.phase === "listening" ? (
          // The open-mic turn, inside the stream: pulse + tap-to-stop.
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("voiceFirst.listening")}
            onPress={() => void session.finishListening()}
            style={({ pressed }) => [
              styles.bubble,
              styles.patientBubble,
              styles.listeningBubble,
              {
                backgroundColor: theme.primarySoft,
                borderColor: dark ? "transparent" : theme.primary,
                opacity: pressed ? 0.7 : 1,
              },
            ]}
          >
            <View style={styles.stateRow}>
              <PulseDot />
              <AppText role="body" color="primary">
                {t("voiceFirst.listening")}
              </AppText>
            </View>
            <AppText role="caption" color="inkFaint">
              {t("dialogue.listeningHint")}
            </AppText>
          </Pressable>
        ) : null}

        {turn.phase === "settling" ? (
          // The one honest wait: everything is asked, the last answers are
          // still being worked into the note — quiet, in-stream.
          <View style={styles.stateRow}>
            <ActivityIndicator size="small" color={theme.inkFaint} />
            <AppText role="caption" color="inkSoft">
              {t("voiceFirst.preparing")}
            </AppText>
          </View>
        ) : null}

        {chipsOpen && question !== null ? (
          // The inline confirm chips on the agent's follow-up turn: the
          // candidate arrives pre-selected; the patient adjusts, then
          // confirms on the bar (nothing auto-commits).
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

        <Pressable accessibilityRole="button" onPress={() => void exitToSteps()}>
          <AppText role="caption" color="inkFaint">
            {t("voiceFirst.typeInstead")}
          </AppText>
        </Pressable>
      </ScrollView>

      <View style={styles.bottomStack}>
        <GlassBar floating={false}>
          <SectionStrip
            filled={model.filled}
            total={model.total}
            onPress={() => setSheetOpen(true)}
          />
          {turn.phase === "listening" ? (
            <View style={styles.barItem}>
              <PrimaryButton
                label={t("voiceFirst.stop")}
                onPress={() => void session.finishListening()}
              />
            </View>
          ) : null}
          {turn.phase === "confirming" ? (
            <View style={[styles.barItem, styles.barStack]}>
              <PrimaryButton
                label={t("dialogue.confirm")}
                // A text answer may be confirmed as spoken; option turns
                // need at least one selection.
                disabled={question !== null && question.kind !== "text" && selected.length === 0}
                onPress={confirmTurn}
              />
              <SecondaryButton
                label={t("dialogue.speakCorrection")}
                onPress={session.speakCorrection}
              />
            </View>
          ) : null}
          {/* The persistent composer: typing is always available — voice
              and text are one conversation, never two modes. */}
          <View style={styles.composerRow}>
            <View style={styles.composerFieldWrap}>
              <TextInput
                accessibilityLabel={t("dialogue.typeThisStep")}
                value={draft}
                onChangeText={setDraft}
                returnKeyType="send"
                onSubmitEditing={send}
                style={[
                  styles.composerField,
                  {
                    backgroundColor: theme.surface,
                    borderColor: dark ? "transparent" : theme.border,
                    color: theme.ink,
                    fontSize: scaledSize("body", fontScale),
                  },
                ]}
              />
              {draft.length === 0 ? (
                // The field's own hint prop is a banned filler token in the
                // app source (invariant 17 scan) — an overlaid caption
                // carries the affordance instead.
                <View pointerEvents="none" style={styles.composerHintWrap}>
                  <AppText role="body" color="inkFaint">
                    {t("dialogue.typeThisStep")}
                  </AppText>
                </View>
              ) : null}
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("dialogue.send")}
              disabled={draft.trim().length === 0}
              onPress={send}
              style={({ pressed }) => [
                styles.sendButton,
                {
                  backgroundColor: theme.cta,
                  opacity: draft.trim().length === 0 ? 0.4 : pressed ? 0.85 : 1,
                },
              ]}
            >
              <SymbolView name="arrow.up" size={17} tintColor={theme.onCta} />
            </Pressable>
          </View>
        </GlassBar>
      </View>

      <SectionSheet
        visible={sheetOpen}
        model={model}
        onClose={() => setSheetOpen(false)}
        onConfirmRow={confirmRow}
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  content: {
    gap: spacing.md,
    padding: spacing.screen,
    paddingBottom: DIALOGUE_BAR_CLEARANCE,
  },
  bubble: {
    maxWidth: "84%",
    borderRadius: radius.group,
    padding: spacing.md,
    gap: spacing.xs,
  },
  agentBubble: {
    alignSelf: "flex-start",
    borderBottomLeftRadius: 6,
    borderWidth: 1,
  },
  patientBubble: {
    alignSelf: "flex-end",
    borderBottomRightRadius: 6,
  },
  listeningBubble: { borderWidth: 1 },
  stateRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  pulseDot: { width: 8, height: 8, borderRadius: radius.chip },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    borderRadius: radius.chip,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    minHeight: 44,
    justifyContent: "center",
  },
  bottomStack: { position: "absolute", left: 0, right: 0, bottom: 0 },
  barItem: { marginBottom: spacing.sm },
  barStack: { gap: spacing.sm },
  composerRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  composerFieldWrap: { flex: 1, justifyContent: "center" },
  composerField: {
    borderRadius: radius.control,
    borderWidth: 1,
    minHeight: 44,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontFamily: fonts.sans,
  },
  composerHintWrap: {
    position: "absolute",
    left: spacing.md,
    right: spacing.md,
  },
  sendButton: {
    width: 44,
    height: 44,
    borderRadius: radius.control,
    alignItems: "center",
    justifyContent: "center",
  },
});
