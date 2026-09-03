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
 *   outer machine, committed answers intact AND the unconfirmed suggestions
 *   riding as prefill (INT-261 — the same thing a hand-over carries, since
 *   both exits go to the same place); a settled dialogue with questions left
 *   hands ONLY those to the manual steps, suggestions riding along.
 * - A TTS outage is NOT such a failure (INT-261). The agent goes silent for
 *   the session, the transcript says so once, and every turn continues:
 *   the question text was never waiting on audio in the first place.
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

import { GlassBar, useGlassBarClearance } from "@/components/GlassBar";
import { Kicker } from "@/components/Kicker";
import { SectionSheet, SectionStrip } from "@/components/SectionPanel";
import {
  AppText,
  PrimaryButton,
  SecondaryButton,
  useFontScale,
  useTheme,
} from "@/components/Themed";
import { joinParts, spoken } from "@/lib/a11y/labels";
import { loopingDecorationEnabled, scrollAnimated } from "@/lib/a11y/motion";
import { useLiveAnnouncement, useReducedMotion } from "@/lib/a11y/prefs";
import { MIN_TAP, verticalSlop } from "@/lib/a11y/target";
import { sectionPanelModel } from "@/lib/dialogue/sectionPanel";
import { questionAsideTr } from "@/lib/dialogue/speech";
import type { StreamEntry } from "@/lib/dialogue/stream";
import { useDialogueSession } from "@/lib/dialogue/useDialogueSession";
import { t } from "@/lib/i18n";
import { optionLabelKey, type IntakeQuestion } from "@/lib/intake/questions";
import type { PrefillMap } from "@/lib/intake/voiceFirst";
import { useSession } from "@/lib/session";
import { fonts, radius, scaledSize, spacing } from "@/lib/theme";

interface DialogueIntakeProps {
  visitId: string | undefined;
  questions: readonly IntakeQuestion[];
  /** The pack label the extract daemon receives (the visit's department). */
  packName: string;
  /** Hard service failure — the manual steps show the honest notice.
   * Prior answers are already committed per confirm; the unconfirmed
   * suggestions ride along as prefill exactly as in a hand-over (INT-261). */
  onFailed: (prefill: PrefillMap) => void;
  /** Dialogue over with questions left (or left by choice): the manual
   * steps take ONLY those, unconfirmed suggestions riding as prefill. */
  onHandoff: (prefill: PrefillMap) => void;
}

/** Candidate map → the prefill shape the typed steps take. Both dialogue
 * exits — the tidy hand-over and a hard failure — hand over the same thing
 * (INT-261), so they build it the same way. */
function toPrefill(leftovers: Record<string, { values: readonly string[]; quote: string }>) {
  const prefill: PrefillMap = {};
  for (const [questionId, candidate] of Object.entries(leftovers)) {
    prefill[questionId] = { values: [...candidate.values], quote: candidate.quote };
  }
  return prefill;
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
  const reduceMotion = useReducedMotion();
  const animate = loopingDecorationEnabled(reduceMotion);
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    if (!animate) {
      // SC 2.2.2: this loop runs for the whole open-mic turn — far past the
      // five seconds the criterion allows — and carries nothing the adjacent
      // "Sizi dinliyorum" line does not already say. Under reduce-motion it
      // rests at full opacity: the dot stays, the movement goes.
      opacity.setValue(1);
      return undefined;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.3, duration: 700, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [animate, opacity]);
  return (
    <Animated.View
      // Pure decoration: the state it signals is spoken by the text beside
      // it, so announcing the dot as well would say everything twice.
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.pulseDot, { backgroundColor: theme.primary, opacity }]}
    />
  );
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
    onFailed: (leftovers) => onFailed(toPrefill(leftovers)),
    onHandoff: (leftovers) => {
      // Confirmed answers are already in the note; the rest of the pack
      // goes to the manual steps with the suggestions as prefill.
      onHandoff(toPrefill(leftovers));
    },
  });
  const { state } = session;
  const { turn } = state;

  // On-screen selection for the live confirm turn (seeded pre-selected).
  const [selected, setSelected] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  // INT-284: the bar reports its own height. This one stacks the section
  // strip, up to two CTAs and the composer, and which of those are present
  // depends on the turn — so the room reserved for it used to be the typed
  // steps' constant plus a literal 176, a guess with a plus sign in it. Only
  // the measurement sees a wrapped label or a second button, and it is the
  // same hook the typed steps now use.
  const [barHeight, setBarHeight] = useState<number | null>(null);
  const barClearance = useGlassBarClearance(barHeight);

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
  const reduceMotion = useReducedMotion();
  useEffect(() => {
    const frame = requestAnimationFrame(() =>
      scrollRef.current?.scrollToEnd({ animated: scrollAnimated(reduceMotion) }),
    );
    return () => cancelAnimationFrame(frame);
  }, [streamLength, turn.phase, reduceMotion]);

  /**
   * The turn state, as one Turkish sentence (INT-144).
   *
   * A sighted patient reads the conversation's state off a pulsing dot, a
   * spinner and a bubble's position. None of those reach a screen reader, so
   * the state is announced instead — politely, so it waits for a gap rather
   * than cutting across the question the patient is being read.
   *
   * Everything announced here is text already rendered on this screen; the
   * announcement never composes a new clinical statement (PolicyGuard
   * posture, invariant 2).
   */
  const pendingTranscription = state.stream.some(
    (entry) => entry.kind === "patient" && entry.status === "transcribing",
  );
  // ASK-AHEAD makes two of these CONCURRENT: the next question starts
  // speaking in the same tick the utterance is taken, while ASR runs behind
  // it. The turn phase therefore wins — "Vizite konuşuyor" is what the
  // patient must act on, and reporting the background transcription instead
  // would describe the quieter of two simultaneous truths and never announce
  // the louder one at all. Transcribing is announced only when nothing else
  // is happening.
  const liveStatus =
    turn.phase === "listening"
      ? t("voiceFirst.listening")
      : turn.phase === "speaking"
        ? session.playing
          ? t("a11y.dialogue.speaking")
          : t("a11y.dialogue.preparing")
        : turn.phase === "settling"
          ? t("a11y.dialogue.settling")
          : pendingTranscription
            ? t("a11y.dialogue.transcribing")
            : null;
  useLiveAnnouncement(liveStatus);

  const step = "step" in turn ? turn.step : -1;
  const question = step >= 0 ? questions[step] : null;

  /** The confirm tap: store the answer, then let the machine skip ahead. */
  const confirmTurn = () => {
    if (turn.phase !== "confirming" || question === null) {
      return;
    }
    const values = question.kind === "text" ? [...turn.candidate.values] : [...selected];
    if (visitId) {
      // INT-286: the quote travels WITH the answer now. It was already the
      // patient's verbatim words behind this candidate and it was already on
      // screen as provenance; dropping it at the commit was what made an
      // open-ended turn read, in the note, exactly like a tapped card. A
      // `text` step's value IS the words, so it carries none separately.
      updateNote(visitId, {
        type: "answer",
        questionId: question.id,
        values,
        words: question.kind === "text" ? undefined : turn.candidate.quote,
      });
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
    const rowQuestion = questions.find((q) => q.id === questionId);
    if (visitId) {
      updateNote(visitId, {
        type: "answer",
        questionId,
        values: [...candidate.values],
        words: rowQuestion?.kind === "text" ? undefined : candidate.quote,
      });
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
    onHandoff(toPrefill(leftovers));
  };

  if (turn.phase === "done" || turn.phase === "failed" || turn.phase === "handoff") {
    return null; // terminal callbacks route away / hand over
  }

  const model = sectionPanelModel(questions, state, account?.carriedFacts ?? []);
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
    // The same words the bubble renders, in reading order, so the spoken
    // name is the visible turn and never a summary of it.
    let said: string[] = [];
    if (entry.kind === "agent_question") {
      const q = questions.find((item) => item.id === entry.questionId);
      if (q === undefined) {
        return null;
      }
      // The bubble shows what the agent SAYS — the question and its aside
      // (speech.ts). It used to show the pack's `hintKey` instead, which is
      // the TYPED lane's control copy: "Birden fazla seçebilirsiniz" under a
      // spoken question with no chips on screen was the reported defect
      // (INT-261). One composition now feeds the clip and the bubble, so
      // they cannot say different things — which is what makes a silenced
      // session readable rather than lossy.
      const aside = questionAsideTr(q);
      said = [t(q.titleKey), aside ?? ""];
      body = (
        <>
          <AppText role="body">{t(q.titleKey)}</AppText>
          {aside !== null ? (
            <AppText role="caption" color="inkSoft">
              {aside}
            </AppText>
          ) : null}
        </>
      );
    } else if (entry.kind === "agent_confirm") {
      const q = questions.find((item) => item.id === entry.questionId);
      said =
        q?.kind === "text"
          ? [t("dialogue.confirmTextGeneric")]
          : [
              t("dialogue.confirmIntro"),
              valueLabels(entry.questionId, entry.values),
              t("dialogue.confirmAsk"),
            ];
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
    // Who spoke is the sighted reader's left/right alignment and nothing
    // else. No screen reader conveys alignment, so every turn is attributed
    // in its own name — one bubble, one accessible element, one voice.
    const name = spoken(t("a11y.speaker.agent"), ...said);
    if (!live) {
      return (
        <View key={index} accessible accessibilityLabel={name} style={bubbleStyle}>
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
        // The QUESTION is the name. Before INT-144 the barge-in copy was the
        // label, which replaced the question with "tap to stop" and left the
        // agent's actual words unreachable to a screen reader — the one
        // defect on this screen that could lose a clinical answer.
        // SC 2.5.3: the name ends with the bubble's own VISIBLE caption,
        // not a private paraphrase of it, so voice control can reach the
        // control by what is written on it. The turn state reaches a screen
        // reader through useLiveAnnouncement above — this element is NOT a
        // live region, because its label contains the whole question and
        // TalkBack would re-read all of it on every playback flip.
        accessibilityLabel={joinParts(
          name,
          session.playing ? t("dialogue.speakingHint") : t("dialogue.preparing"),
        )}
        accessibilityHint={t("a11y.dialogue.bargeInHint")}
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
          accessible
          // The bubble's own visible words (SC 2.5.3). The transition is
          // announced once by useLiveAnnouncement; a live region here would
          // say it a second time.
          accessibilityLabel={spoken(t("a11y.speaker.patient"), t("dialogue.transcribing"))}
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
        accessible
        accessibilityLabel={spoken(t("a11y.speaker.patient"), entry.text)}
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
        // SC 1.3.1: the conversation is a named region, so a screen-reader
        // user knows the scroller they landed in is the transcript and not
        // the page.
        accessibilityLabel={t("a11y.dialogue.transcript")}
        contentContainerStyle={[styles.content, { paddingBottom: barClearance }]}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        <Kicker label={t("dialogue.kicker")} tone="accent" />

        {state.voiceMuted ? (
          // INT-261: the agent lost its voice and the conversation carried
          // on. Saying so once is the whole apology — the patient can see
          // the questions and answer them; what they cannot see is WHY the
          // sound stopped, and silence with no explanation reads as broken.
          //
          // NOT a live region, deliberately. This screen announces exactly
          // one thing through useLiveAnnouncement (the turn state), and the
          // a11y suite pins that there is no second channel. It also does
          // not need one here: a screen-reader user never heard the agent
          // clip in the first place — VoiceOver was already reading them
          // the bubble — so the mute changes nothing for them. It stands at
          // the head of the transcript as a condition of the session.
          <View accessible>
            <AppText role="caption" color="inkFaint">
              {t("dialogue.voiceMuted")}
            </AppText>
          </View>
        ) : null}

        {state.stream.map(renderEntry)}

        {turn.phase === "listening" ? (
          // The open-mic turn, inside the stream: pulse + tap-to-stop.
          <Pressable
            accessibilityRole="button"
            // SC 2.5.3: the bubble reads "Sizi dinliyoruz." and so must its
            // name — an a11y-only paraphrase would put the control out of
            // reach of a voice-control user saying what they can see.
            accessibilityLabel={spoken(t("a11y.speaker.patient"), t("voiceFirst.listening"))}
            accessibilityHint={t("a11y.dialogue.stopHint")}
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
          <View accessible style={styles.stateRow}>
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
                  // A checkbox tells the reader "you may pick several". On a
                  // single-answer turn that is false, and the handler below
                  // enforces the opposite — the role must agree with it.
                  accessibilityRole={question.kind === "single" ? "radio" : "checkbox"}
                  accessibilityLabel={t(option.labelKey)}
                  accessibilityHint={t("a11y.selectHint")}
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

        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("voiceFirst.typeInstead")}
          accessibilityHint={t("a11y.dialogue.exitHint")}
          hitSlop={verticalSlop(18)}
          onPress={() => void exitToSteps()}
        >
          <AppText role="caption" color="inkFaint">
            {t("voiceFirst.typeInstead")}
          </AppText>
        </Pressable>
      </ScrollView>

      <View style={styles.bottomStack}>
        <GlassBar floating={false} onHeight={setBarHeight}>
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
                accessibilityHint={t("a11y.dialogue.composerHint")}
                // The field applies scaledSize itself, so the OS multiplier
                // must be off or the patient's 200 % setting becomes 400 %
                // and the composer truncates (SC 1.4.4).
                allowFontScaling={false}
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
                <View
                  pointerEvents="none"
                  // The field already carries this text as its name; read
                  // again as a sibling it says the same thing twice.
                  accessibilityElementsHidden
                  importantForAccessibility="no-hide-descendants"
                  style={styles.composerHintWrap}
                >
                  <AppText role="body" color="inkFaint">
                    {t("dialogue.typeThisStep")}
                  </AppText>
                </View>
              ) : null}
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("dialogue.send")}
              // Icon-only, so the disabled state has no visible word either:
              // 0.4 opacity is the sighted half and this is the other half.
              accessibilityState={{ disabled: draft.trim().length === 0 }}
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
  content: { gap: spacing.md, padding: spacing.screen },
  bubble: {
    maxWidth: "84%",
    borderRadius: radius.group,
    padding: spacing.md,
    gap: spacing.xs,
    // The speaking bubble IS the barge-in target (INT-235), and the
    // listening bubble is the stop target. 32 pt of padding plus a body
    // line already clears the floor; pinned so no copy change can take the
    // control that interrupts the agent below it (SC 2.5.8).
    minHeight: MIN_TAP,
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
    minHeight: MIN_TAP,
    justifyContent: "center",
    // INT-136: the same bound the typed lane's chips carry. A wrap item gets
    // no shrink in React Native, so an option label wider than the row would
    // put the chip off-screen with no horizontal scroll to reach it, and
    // truncating it is banned (files/00 §2).
    maxWidth: "100%",
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
