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
import { useHeaderHeight } from "expo-router/react-navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
  useColorScheme,
} from "react-native";
import Animated, { LayoutAnimationConfig } from "react-native-reanimated";

import { AgentQuestionLines } from "@/components/ChatLines";
import { GlassBar, useGlassBarClearance } from "@/components/GlassBar";
import { Icon } from "@/components/Icon";
import { Kicker } from "@/components/Kicker";
import { PresenceOrb } from "@/components/PresenceOrb";
import { SectionSheet, SectionStrip } from "@/components/SectionPanel";
import {
  AppText,
  PrimaryButton,
  SecondaryButton,
  useFontScale,
  useTheme,
} from "@/components/Themed";
import { joinParts, spoken } from "@/lib/a11y/labels";
import { scrollAnimated } from "@/lib/a11y/motion";
import { useLiveAnnouncement, useReducedMotion } from "@/lib/a11y/prefs";
import { MIN_TAP, verticalSlop } from "@/lib/a11y/target";
import {
  BUBBLE_SHARE,
  GROUPED_MARGIN,
  bubbleMaxWidth,
  placeTurns,
  sideOf,
  type Side,
} from "@/lib/dialogue/rhythm";
import { sectionPanelModel } from "@/lib/dialogue/sectionPanel";
import { questionAsideTr } from "@/lib/dialogue/speech";
import { answerWords, type StreamEntry } from "@/lib/dialogue/stream";
import { useDialogueSession } from "@/lib/dialogue/useDialogueSession";
import { t } from "@/lib/i18n";
import { optionLabelKey, type IntakeQuestion } from "@/lib/intake/questions";
import type { PrefillMap } from "@/lib/intake/voiceFirst";
import { enteringFor } from "@/lib/motion/native/reanimated";
import { useDialogueMotion } from "@/lib/motion/native/useDialogueMotion";
import { orbStateFor } from "@/lib/motion/orb";
import { WORK, dialogueScene, fadeOf, nodeKey, revealId } from "@/lib/motion/transients";
import { useSession } from "@/lib/session";
import { fonts, motion, radius, scaledSize, spacing } from "@/lib/theme";

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

/** The live turn's marker in its bubble: a still dot (INT-336). The state
 * moves on the presence orb in the glass bar, one element for the whole
 * dialogue, so the bubbles no longer pulse or spin; their words say the
 * rest. */
function StateDot() {
  const theme = useTheme();
  return (
    <View
      // Pure decoration: the state it marks is spoken by the text beside it,
      // so announcing the dot as well would say everything twice.
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.stateDot, { backgroundColor: theme.primary }]}
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
  // The transcript's own laid-out width (INT-423): the measure is a share of
  // the box the bubbles sit in, so landscape insets are already out of it.
  const [transcriptWidth, setTranscriptWidth] = useState<number | null>(null);
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
  // INT-337: a focused composer shuts the arbiter's commit window (the
  // patient is mid-sentence), exactly as listening does.
  const [composerFocused, setComposerFocused] = useState(false);
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
  // INT-360: the keyboard and the stack pinned above it. The avoiding view
  // measures its overlap with the keyboard from its OWN top, and the stack
  // header sits above it, so the header's height is the offset. The frame is
  // the height left between the header and the keyboard: the stack is capped
  // at it, so in a landscape window with the keyboard up no control is pushed
  // above its top edge.
  const headerHeight = useHeaderHeight();
  const [frameHeight, setFrameHeight] = useState<number | null>(null);

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
  const model = sectionPanelModel(questions, state, account?.carriedFacts ?? []);
  const chipsOpen = turn.phase === "confirming" && question !== null && question.kind !== "text";

  // INT-337: what fades, what renders at once and what waits for the commit
  // window is the arbiter's answer for each new element (lib/motion/
  // transients.ts). Nothing here waits on it: it is decided in the render
  // that shows the element.
  const scene = dialogueScene(state, {
    composerFocused,
    chipsOpen,
    strip: { filled: model.filled, total: model.total },
  });
  const transients = useDialogueMotion(scene, reduceMotion);
  const motionContext = { reduce: reduceMotion };

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
        words: answerWords(question, turn.candidate.quote),
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
    if (rowQuestion === undefined) {
      // No question, no write — and therefore no confirm either. Confirming
      // here would clear the row off the panel and out of the hand-over while
      // the note kept nothing, which is the INT-293 defect with an extra step.
      return;
    }
    if (visitId) {
      updateNote(visitId, {
        type: "answer",
        questionId,
        values: [...candidate.values],
        words: answerWords(rowQuestion, candidate.quote),
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

  // INT-336: the orb's one input. This lane is the dev dialogue over HTTP:
  // it has no media transport to lose and no RED channel (the LiveKit lane
  // feeds both), so those two inputs are honestly "connected" and none.
  const orbState = orbStateFor({
    lane: "voice",
    turnPhase: turn.phase,
    playing: session.playing,
    voiceMuted: state.voiceMuted,
    transport: "connected",
    red: null,
  });
  // While the agent speaks, the LAST logged agent turn is the live bubble.
  const liveAgentIndex = turn.phase === "speaking" ? state.stream.length - 1 : -1;

  // INT-423: the rhythm. Consecutive turns from one speaker group, and the
  // tail belongs to a run's last bubble; the open-mic turn is the patient's,
  // after the stream. The measure is lib/dialogue/rhythm's.
  const sides: Side[] = [
    ...state.stream.map(sideOf),
    ...(turn.phase === "listening" ? (["patient"] as const) : []),
  ];
  const placements = placeTurns(sides);
  const measure =
    transcriptWidth === null
      ? (`${BUBBLE_SHARE * 100}%` as const)
      : bubbleMaxWidth(transcriptWidth - 2 * spacing.screen, fontScale);
  const shape = (index: number) => {
    const placement = placements[index];
    const tail = placement?.tail
      ? sides[index] === "agent"
        ? styles.agentTail
        : styles.patientTail
      : null;
    return [{ maxWidth: measure, marginTop: placement?.grouped ? GROUPED_MARGIN : 0 }, tail];
  };

  const renderAgentBubble = (entry: StreamEntry, index: number) => {
    const live = index === liveAgentIndex;
    const bubbleStyle = [
      styles.bubble,
      styles.agentBubble,
      { backgroundColor: theme.surface, borderColor: dark ? "transparent" : theme.border },
      ...shape(index),
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
      body = <AgentQuestionLines question={t(q.titleKey)} aside={aside} />;
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
        style={({ pressed }) => [
          ...bubbleStyle,
          { opacity: pressed ? motion.press.rowOpacity : 1 },
        ]}
      >
        {body}
        <View style={styles.stateRow}>
          <StateDot />
          <AppText role="caption" color="inkFaint">
            {session.playing ? t("dialogue.speakingHint") : t("dialogue.preparing")}
          </AppText>
        </View>
      </Pressable>
    );
  };

  const renderEntry = (entry: StreamEntry, index: number, key: string) => {
    if (entry.kind === "agent_question" || entry.kind === "agent_confirm") {
      return renderAgentBubble(entry, index);
    }
    // INT-293: the words the patient gave for the previous question mapped to
    // nothing — here or at the extractor — so the agent asks it once more and
    // says why first. Its own quiet bubble rather than a line inside the
    // question's: the question that follows is spoken verbatim from the pack
    // (invariant 10), and this sentence is not part of it.
    if (entry.kind === "agent_unclear") {
      return (
        <View
          key={`u-${index}`}
          accessible
          accessibilityLabel={spoken(t("a11y.speaker.agent"), t("dialogue.notUnderstood"))}
          style={[
            styles.bubble,
            styles.agentBubble,
            { backgroundColor: theme.surface, borderColor: dark ? "transparent" : theme.border },
            ...shape(index),
          ]}
        >
          <AppText role="caption" color="inkSoft">
            {t("dialogue.notUnderstood")}
          </AppText>
        </View>
      );
    }
    // Patient turns, keyed by work id. A transcribing bubble is the
    // in-place stand-in the ASR text will replace (never a takeover). The
    // words replace it when the arbiter applies their reveal (INT-337): at
    // once on an agent turn, at the next window while the patient is
    // listening or typing.
    const reveal = revealId(key);
    if (entry.status === "transcribing" || transients.entered[reveal] === undefined) {
      return (
        <View
          key={`w-${entry.workId}`}
          accessible
          // The bubble's own visible words (SC 2.5.3). The transition is
          // announced once by useLiveAnnouncement; a live region here would
          // say it a second time.
          accessibilityLabel={spoken(t("a11y.speaker.patient"), t("dialogue.transcribing"))}
          style={[
            styles.bubble,
            styles.patientBubble,
            { backgroundColor: theme.surfaceRaised },
            ...shape(index),
          ]}
        >
          <AppText role="caption" color="inkSoft">
            {t("dialogue.transcribing")}
          </AppText>
        </View>
      );
    }
    return (
      <View
        key={`w-${entry.workId}`}
        accessible
        accessibilityLabel={spoken(t("a11y.speaker.patient"), entry.text)}
        style={[
          styles.bubble,
          styles.patientBubble,
          { backgroundColor: theme.surfaceRaised },
          ...shape(index),
        ]}
      >
        {/* Only the new text fades; the bubble frame stays still (C3). */}
        <Animated.View
          key={nodeKey(transients, reveal)}
          entering={enteringFor(fadeOf(transients, reveal, motionContext))}
        >
          <AppText role="body">{entry.text}</AppText>
        </Animated.View>
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={headerHeight}
    >
      {/* INT-360: the frame the bottom stack pins to. The avoiding view lifts
          its content with PADDING, and an absolutely positioned child ignores
          its parent's padding (Yoga places it against the border box), so a
          stack pinned in the avoiding view itself sat behind the keyboard.
          Inside this frame, `bottom: 0` is the keyboard's top edge. */}
      <View
        style={styles.root}
        onLayout={(event) => setFrameHeight(event.nativeEvent.layout.height)}
      >
        <ScrollView
          ref={scrollRef}
          // SC 1.3.1: the conversation is a named region, so a screen-reader
          // user knows the scroller they landed in is the transcript and not
          // the page.
          accessibilityLabel={t("a11y.dialogue.transcript")}
          onLayout={(event) => setTranscriptWidth(event.nativeEvent.layout.width)}
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

          {/* History never fades in: only what arrives after the first mount
              can enter, and only as the arbiter grants it (INT-337). */}
          <LayoutAnimationConfig skipEntering>
            {state.stream.map((entry, index) => {
              const key = scene.entries[index].key;
              return (
                <Animated.View
                  key={nodeKey(transients, key)}
                  entering={enteringFor(fadeOf(transients, key, motionContext))}
                >
                  {renderEntry(entry, index, key)}
                </Animated.View>
              );
            })}
          </LayoutAnimationConfig>

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
                  opacity: pressed ? motion.press.rowOpacity : 1,
                },
                ...shape(state.stream.length),
              ]}
            >
              <View style={styles.stateRow}>
                <StateDot />
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
              <AppText role="caption" color="inkSoft">
                {t("voiceFirst.preparing")}
              </AppText>
            </View>
          ) : null}

          {chipsOpen && question !== null && scene.chips !== null ? (
            // The inline confirm chips on the agent's follow-up turn: the
            // candidate arrives pre-selected; the patient adjusts, then
            // confirms on the bar (nothing auto-commits). The group enters
            // as one element; a selection changes no motion (INT-337).
            <Animated.View
              key={nodeKey(transients, scene.chips)}
              entering={enteringFor(fadeOf(transients, scene.chips, motionContext))}
              style={styles.chipWrap}
            >
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
            </Animated.View>
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

        <View
          style={[styles.bottomStack, frameHeight !== null ? { maxHeight: frameHeight } : null]}
        >
          <GlassBar floating={false} onHeight={setBarHeight}>
            {/* INT-360: the strip and the turn's CTAs scroll when the capped
              stack cannot hold them (the largest step, landscape, keyboard
              up); the composer below keeps its whole height, so the field
              the patient is typing into stays in view. */}
            <ScrollView style={styles.barScroll} keyboardShouldPersistTaps="handled">
              <View style={styles.stripRow}>
                <PresenceOrb
                  state={orbState}
                  working={transients.ring}
                  workFades={fadeOf(transients, WORK, motionContext) !== undefined}
                  readLevel={session.readLevel}
                />
                <View style={styles.stripFill}>
                  <SectionStrip
                    filled={transients.strip.filled}
                    total={transients.strip.total}
                    onPress={() => setSheetOpen(true)}
                  />
                </View>
              </View>
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
                    disabled={
                      question !== null && question.kind !== "text" && selected.length === 0
                    }
                    onPress={confirmTurn}
                  />
                  <SecondaryButton
                    label={t("dialogue.speakCorrection")}
                    onPress={session.speakCorrection}
                  />
                </View>
              ) : null}
            </ScrollView>
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
                  onFocus={() => setComposerFocused(true)}
                  onBlur={() => setComposerFocused(false)}
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
                // the disabled opacity is the sighted half and this is the other.
                accessibilityState={{ disabled: draft.trim().length === 0 }}
                disabled={draft.trim().length === 0}
                onPress={send}
                style={({ pressed }) => [
                  styles.sendButton,
                  {
                    backgroundColor: theme.cta,
                    opacity:
                      draft.trim().length === 0
                        ? motion.press.disabledOpacity
                        : pressed
                          ? motion.press.opacity
                          : 1,
                  },
                ]}
              >
                <Icon name="arrow.up" size={17} tintColor={theme.onCta} />
              </Pressable>
            </View>
          </GlassBar>
        </View>
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
    borderRadius: radius.group,
    borderCurve: "continuous",
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
    borderWidth: 1,
  },
  patientBubble: {
    alignSelf: "flex-end",
  },
  // INT-423: the tail corner, on a speaker's last bubble in a run only.
  agentTail: { borderBottomLeftRadius: spacing.xs },
  patientTail: { borderBottomRightRadius: spacing.xs },
  listeningBubble: { borderWidth: 1 },
  stateRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  stateDot: { width: 8, height: 8, borderRadius: radius.chip },
  // The orb leads the bar's first row; the strip takes the rest of it.
  stripRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  stripFill: { flex: 1 },
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
  // Its natural height while the stack has room, and it gives height back —
  // then scrolls — once the stack is capped (INT-360).
  barScroll: { flexGrow: 0, flexShrink: 1 },
  barItem: { marginBottom: spacing.sm },
  barStack: { gap: spacing.sm },
  composerRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  composerFieldWrap: { flex: 1, justifyContent: "center" },
  composerField: {
    borderRadius: radius.control,
    borderCurve: "continuous",
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
    borderRadius: radius.chip,
    alignItems: "center",
    justifyContent: "center",
  },
});
