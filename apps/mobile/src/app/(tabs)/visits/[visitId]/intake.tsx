/**
 * Typed intake shell (INT-179): ONE question per screen (Alan pacing) —
 * chips multi-select (CVS grid), single-select cards, then free text.
 * Progress is a thin bar and a "Soru N / M" line (INT-433); answers land in
 * the session note state, so leaving and returning resumes at the first
 * unanswered question.
 * Fixture questions only — the compiled protocol set (INT-096) replaces them.
 * Design pass 3: the step's one CTA sits on a floating glass bar (Oura
 * chrome) and the question body scrolls under it; single-select steps have
 * no CTA and no bar.
 * INT-433 (owner review, 2 Oct 2026): the native pass. Filled fields with a
 * focus ring, filled capsule chips with a checked state, and Liquid Glass on
 * both bars: the nav bar draws the bottom bar's material, the content stays
 * on solid fills, and Reduce Transparency is solid (docs/design/
 * question-screen.md).
 *
 * Voice entry (INT-199 → INT-239): a FRESH intake (not edit mode, no
 * answers) with dev-lane voice available goes STRAIGHT into the spoken
 * dialogue after one probe beat — karşılıklı konuşma is the entry, not one
 * of two offered paths, and the old one-shot "record it all at once" route
 * is gone. Typed intake stays reachable as the quiet second door from the
 * gate, from inside the dialogue, and as the landing place for any failure
 * — never a dead end. Suggestions are never triage or a diagnosis
 * (invariant 1); the transcript renders only as quotes.
 *
 * Adaptive flow + modes (INT-236, deepened in INT-239): the steps run over
 * the pack's APPLICABLE questions only — `askIf` gates mirror the DSL's
 * ask_if (packages/protocols dsl.py), evaluated against committed answers
 * and re-evaluated on every change, so the flow's LENGTH is decided by the
 * answers and the progress row says so instead of printing a fixed total.
 * The mode context lives on the note state: Hızlı by
 * default; the quiet "Hastanedeyim" switch sets Detaylı, which (a) asks the
 * one calm environment question (02 §33) and defers sensitive sections when
 * privacy is not established, and (b) keeps a persistent "Sıranız geldi"
 * affordance that checkpoints INSTANTLY — no dialog, no lost turns
 * (02 §34) — into the partial-note review.
 */
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useHeaderHeight } from "expo-router/react-navigation";
import { useReducer, useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";
import Animated, { LayoutAnimationConfig } from "react-native-reanimated";

import { AnnouncedRegion, AnnouncedText } from "@/components/Announced";
import { GlassBar, useGlassBarClearance, withGlassNav, withStageNav } from "@/components/GlassBar";
import { useGlassMode } from "@/components/glassMode";
import { Icon } from "@/components/Icon";
import { QuestionProgress } from "@/components/QuestionProgress";
import {
  AppText,
  Card,
  PrimaryButton,
  Screen,
  useFontScale,
  useScheme,
  useStackHeader,
  useTheme,
} from "@/components/Themed";
import { ChipSlot } from "@/components/ChipSlot";
import { DevVoiceBanner } from "@/components/DevVoiceBanner";
import { DialogueGate } from "@/components/DialogueGate";
import { DialogueIntake } from "@/components/DialogueIntake";
import { stagePalette } from "@/lib/stage/palette";
import { InstrumentStep } from "@/components/InstrumentStep";
import { VoiceNote } from "@/components/VoiceNote";
import { voiceAllowedForIntegrity } from "@/lib/auth/integrity";
import { asDeliveryKey } from "@/lib/dialogue/deliveryDeck";
import { typedStepDelivery } from "@/lib/dialogue/deliveryPlan";
import { joinParts } from "@/lib/a11y/labels";
import { useIncreasedContrast, useReducedMotion } from "@/lib/a11y/prefs";
import { MIN_TAP } from "@/lib/a11y/target";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import type { ReachabilityReport } from "@/lib/dev/hosts";
import { voiceDiagnostic } from "@/lib/dev/voiceDiagnostic";
import { flags } from "@/lib/featureFlags";
import { t } from "@/lib/i18n";
import { measurementLine } from "@/lib/intake/baseLayer";
import {
  intakeProgress,
  isOpenAsk,
  nextApplicableQuestion,
  packForVisit,
  resumeQuestion,
  spokenPack,
  type IntakeQuestion,
} from "@/lib/intake/questions";
import { chipChrome, filledFieldChrome, questionPosition } from "@/lib/intake/questionScreen";
import {
  initialVoiceIntakeState,
  resolveAnswer,
  voiceIntakeReducer,
  type PrefillMap,
} from "@/lib/intake/voiceFirst";
import { haptic } from "@/lib/motion/appHaptics";
import { enteringFor } from "@/lib/motion/native/reanimated";
import { typedFallback, typedStep } from "@/lib/motion/transients";
import { useAppearance } from "@/lib/prefs/AppearanceProvider";
import { useSession } from "@/lib/session";
import { fonts, radius, scaledSize, spacing } from "@/lib/theme";

// With the top bar shown, the header owns the top inset (design pass 6).
const FLOW_EDGES = ["left", "right"] as const;

export default function TypedIntake() {
  useClinicalScreenPrivacy(); // FLAG_SECURE-class capture blocking (INT-131)
  const headerOptions = useStackHeader();
  const scheme = useScheme();
  const { visitId, q } = useLocalSearchParams<{ visitId: string; q?: string }>();
  const { notes, consents, visits, integrity } = useSession();
  // INT-260: "Ziyarete başlarken" — the patient's own answer to whether a
  // fresh visit opens by speaking or by typing. It can only ever narrow the
  // existing eligibility rule; typed intake was already reachable from the
  // gate, from inside the dialogue, and from any failure.
  const { prefs } = useAppearance();
  const note = notes[visitId ?? ""];
  const visit = visits.find((v) => v.id === visitId);
  // The pack a visit runs = the department's dimensions + the universal
  // history block, narrowed to this session's profile (INT-256): Hızlı asks
  // meds/allergies, Detaylı adds the PMH/FH deltas, and a section the 02 §33
  // self-check deferred is absent rather than asked quietly.
  const intakeQuestions = packForVisit(visit?.department, {
    mode: note?.mode ?? "hizli",
    deferred: note?.deferred,
  });

  // Voice goes FIRST on a fresh run: not edit mode, nothing answered yet,
  // voice consent ON, dev lane present. The ASR probe gates inside the flow.
  // Jailbreak/root soft signal (10 §4, INT-131): a compromised device gets
  // the typed lane plus the warning banner, never voice.
  const editing = typeof q === "string" && q.length > 0;
  const integrityCompromised = !voiceAllowedForIntegrity(integrity);
  const voiceEligible =
    __DEV__ &&
    prefs.startMode === "voice" &&
    consents?.voice === true &&
    !editing &&
    !integrityCompromised &&
    (note?.answers.length ?? 0) === 0;
  const [voiceState, dispatchVoice] = useReducer(
    voiceIntakeReducer,
    voiceEligible,
    initialVoiceIntakeState,
  );
  // INT-246: the probe's detail, held here because the gate unmounts the
  // moment the fallback fires. `setVoiceProbe` is a stable setter, so the
  // gate's effect does not re-run and the dead host is probed once. The
  // banner it feeds renders only under __DEV__ (lib/dev/voiceDiagnostic).
  const [voiceProbe, setVoiceProbe] = useState<ReachabilityReport | null>(null);
  // INT-339 (MOTION-10, C15): the typed steps' entrance when they replace the
  // voice lane. Enter-only, from the fade policy, and nothing under reduce-motion.
  const reduceMotion = useReducedMotion();
  const fallback = typedFallback({ reduce: reduceMotion });

  // INT-321: the mode is asked ONCE, up front — before either lane — so a
  // patient meets one calm choice instead of a switch riding on top of every
  // question. It shows only on a fresh run (not an edit, nothing answered) and
  // only until a choice is recorded (`modeChosen`). Voice-vs-typed is decided
  // after, by voiceEligible above, exactly as before.
  const showModeChoice =
    !editing && (note?.answers.length ?? 0) === 0 && !(note?.modeChosen ?? false);

  // INT-433: the glass nav bar belongs to the typed steps. The question
  // scrolls under it and clears it by the header's own height. A warning
  // banner above the steps keeps the solid bar, so nothing it says can sit
  // under glass; the dialogue and the mode choice keep it too.
  const headerHeight = useHeaderHeight();
  const bannerShown = integrityCompromised || voiceDiagnostic(voiceProbe, __DEV__) !== null;
  const glassNav = !showModeChoice && voiceState.phase === "steps" && !bannerShown;
  // INT-451 follow-up: the same helper as the visit's other pushed screens,
  // so iOS 26 gets the platform bar and its scroll-edge effect rather than a
  // full-bar GlassView the question would scroll through.
  const glass = useGlassMode();
  // INT-466 (ADR-039 S3): the dialogue is the chat stage. With Liquid Glass
  // its bar is the platform's own, transparent over the stage backdrop with
  // a soft scroll edge; otherwise it is solid in the stage's base colour.
  // A warning banner keeps the solid bar here too.
  const stageNav = !showModeChoice && voiceState.phase === "dialogue" && !bannerShown;
  const stageBase = stagePalette(scheme, {
    reduceTransparency: true,
    increasedContrast: false,
  }).base;
  const navOptions = glassNav
    ? withGlassNav(headerOptions(""), glass)
    : stageNav
      ? withStageNav(headerOptions(""), glass, stageBase)
      : headerOptions("");

  return (
    <Screen style={styles.screenFlush} edges={FLOW_EDGES}>
      {/* Design pass 6: every Oura full-screen flow carries a top-left way
          out (Mobbin 11265937, 96fb49c7); ours had none. Back-only bar —
          the serif question line stays the screen's title, so the bar
          itself is untitled (the resilience-sheet anatomy, b67baac0). */}
      <Stack.Screen options={navOptions} />
      {/* Focused flow (design pass 4): the tab rail unmounts here, so the
          glass bar owns the physical bottom edge, home indicator included. */}
      {integrityCompromised ? (
        // SC 4.1.3 on both platforms (INT-362): one element, named by both lines.
        <AnnouncedRegion
          tone="status"
          merged
          message={joinParts(t("auth.integrity.warnTitle"), t("auth.integrity.warnBody"))}
          style={styles.integrityWarn}
        >
          <AppText role="label">{t("auth.integrity.warnTitle")}</AppText>
          <AppText role="caption" color="inkSoft">
            {t("auth.integrity.warnBody")}
          </AppText>
        </AnnouncedRegion>
      ) : null}
      <DevVoiceBanner report={voiceProbe} />
      <View style={styles.body}>
        {/* INT-339 (MOTION-10, C15): the lane on screen first arrives with
            the route's own fade, so its entrance is skipped. A lane that
            REPLACES another one (the typed steps after a failure, a hand-over
            or "Yazarak devam edin") fades in, enter-only: the lane it replaces
            is gone in the same commit, so no frame shows both. */}
        <LayoutAnimationConfig skipEntering>
          {showModeChoice ? (
            <ModeChoice visitId={visitId} />
          ) : voiceState.phase === "steps" ? (
            <Animated.View entering={enteringFor(fallback.enter)} style={styles.lane}>
              <StepFlow
                visitId={visitId}
                requestedQ={q}
                intakeQuestions={intakeQuestions}
                prefill={voiceState.prefill}
                voiceFailed={voiceState.failed}
                topInset={glassNav ? headerHeight : 0}
              />
            </Animated.View>
          ) : voiceState.phase === "dialogue" ? (
            // The intake (INT-233/235/239): an ask-ahead conversation over
            // the same pack, entered directly. Answers commit per confirm, so
            // a service failure resumes these exact manual steps at the first
            // unanswered question with the honest notice; a settled dialogue
            // (or a chosen exit) hands over ONLY the unanswered questions,
            // any unconfirmed suggestions riding along as prefill.
            <DialogueIntake
              visitId={visitId}
              // files/13 §13: the spoken lane asks the speakable steps only.
              // INT-282's numeral-bearing steps declare `text_only`, so no
              // digit can reach a voice profile (invariant 22) — they are
              // asked in the typed lane below, which is where the guarded
              // controls live.
              questions={spokenPack(intakeQuestions)}
              packName={visit?.department ?? "general"}
              onFailed={(prefill) => dispatchVoice({ type: "failure", prefill })}
              onHandoff={(prefill) => dispatchVoice({ type: "candidates", prefill })}
            />
          ) : (
            <DialogueGate dispatch={dispatchVoice} onProbe={setVoiceProbe} />
          )}
        </LayoutAnimationConfig>
      </View>
    </Screen>
  );
}

/**
 * The up-front mode choice (INT-321): one calm screen, two doors, shown once
 * before the questions. "Hastanedeyim" opens the ayrıntılı flow (02 §2) — the
 * environment self-check and the "Bitirdim" checkpoint come with it; "Kısa
 * tutalım" runs the short set. Recording the choice (`modeChosen`) is what
 * dismisses this screen, so a default value is never a silent decision.
 */
function ModeChoice({ visitId }: { visitId: string | undefined }) {
  const { updateNote } = useSession();
  const choose = (mode: "hizli" | "detayli") => {
    if (visitId) {
      updateNote(visitId, { type: "mode", mode });
    }
  };
  return (
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <AppText role="question" heading>
        {t("intake.mode.q")}
      </AppText>
      <View style={styles.optionColumn}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("intake.mode.hospital")}
          style={styles.cardTarget}
          onPress={() => choose("detayli")}
        >
          <Card>
            <AppText role="body">{t("intake.mode.hospital")}</AppText>
            <AppText role="caption" color="inkSoft">
              {t("intake.mode.hospitalSub")}
            </AppText>
          </Card>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("intake.mode.brief")}
          style={styles.cardTarget}
          onPress={() => choose("hizli")}
        >
          <Card>
            <AppText role="body">{t("intake.mode.brief")}</AppText>
            <AppText role="caption" color="inkSoft">
              {t("intake.mode.briefSub")}
            </AppText>
          </Card>
        </Pressable>
      </View>
    </ScrollView>
  );
}

interface StepFlowProps {
  visitId: string | undefined;
  requestedQ: string | undefined;
  intakeQuestions: readonly IntakeQuestion[];
  /** Voice-run suggestions: pre-selected answers + the patient's quote. */
  prefill: PrefillMap;
  /** True when a voice attempt fell back here — say so once, honestly. */
  voiceFailed: boolean;
  /** The glass nav bar's height when the content scrolls under it, else 0. */
  topInset: number;
}

function StepFlow({
  visitId,
  requestedQ,
  intakeQuestions,
  prefill,
  voiceFailed,
  topInset,
}: StepFlowProps) {
  const router = useRouter();
  const theme = useTheme();
  const fontScale = useFontScale();
  const increasedContrast = useIncreasedContrast() === "high";
  // The answer field's focus ring (INT-433); one field is on screen at a time.
  const [fieldFocused, setFieldFocused] = useState(false);
  const underNav = topInset > 0 ? { paddingTop: spacing.screen + topInset } : null;
  const { notes, updateNote, consents } = useSession();
  const note = notes[visitId ?? ""];
  const reduceMotion = useReducedMotion();

  // Adaptive flow (INT-236): the applicable list derives from the committed
  // answers on EVERY render, so gates open and close as answers change and
  // the progress denominator is honest ("n of applicable", never the full
  // pack). The advance rule lives in nextApplicableQuestion (pack layer).
  const answers = note?.answers ?? [];
  // INT-136 moved both rules into the pack layer, so "progress + resume" is
  // held by unit tests rather than by a screenshot.
  const {
    answered: answeredCount,
    applicable,
    canGrow: flowCanGrow,
  } = intakeProgress(intakeQuestions, answers);

  // `q` = edit mode: jump straight to that question with its current answer
  // preloaded (the review screen's pencil). Otherwise resume at the first
  // unanswered APPLICABLE question. The `?? intakeQuestions[0]` only keeps the
  // type total and is unreachable: questions.test.ts pins that every shipped
  // pack has something applicable before a single answer is given.
  const requested = requestedQ ? intakeQuestions.find((x) => x.id === requestedQ) : undefined;
  const initialQuestion =
    resumeQuestion(intakeQuestions, answers, requestedQ) ?? intakeQuestions[0];
  const initialAnswer = answers.find((a) => a.questionId === initialQuestion.id);
  const initialPrefill = initialAnswer === undefined ? prefill[initialQuestion.id] : undefined;
  const initialKind = initialQuestion.kind;
  const [currentId, setCurrentId] = useState(initialQuestion.id);
  const [selected, setSelected] = useState<string[]>(
    initialKind === "text" ? [] : (initialAnswer?.values ?? initialPrefill?.values ?? []),
  );
  // The free-text box: the whole answer on a `text` step, and the patient's
  // OWN WORDS on an open step (INT-286), where the coded value still comes
  // from the options underneath. An edit reopens with what they wrote; a
  // prefill's quote is NOT poured in here — it is already on screen above as
  // provenance, and a suggestion is not something the patient typed.
  const [text, setText] = useState(
    initialKind === "text"
      ? (initialAnswer?.values.join(" ") ?? initialPrefill?.values.join(" ") ?? "")
      : (initialAnswer?.words ?? ""),
  );
  // The glass bar reports its own height (INT-284): the CTA label wraps at
  // the large text steps, so the room reserved for it cannot be a constant —
  // it was 128 against a bar that measures 131 at 2.0, and the last option
  // chip was clipped by the bar with nowhere left to scroll.
  const [barHeight, setBarHeight] = useState<number | null>(null);
  const barClearance = useGlassBarClearance(barHeight);
  // The guarded measure (INT-282, invariant 22). `null` means the patient
  // has not moved the control yet: the stepper shows where it OPENS, but
  // nothing is committed and the CTA stays disabled, so a value can never
  // be recorded by tapping through. There is no prefill path — a measure
  // step is `text_only` and the voice lane never sees it.
  const [measure, setMeasure] = useState<number | null>(
    initialKind === "measure" && initialAnswer !== undefined
      ? Number(initialAnswer.values[0])
      : null,
  );
  const editing = requested !== undefined;
  // INT-414: the sitting this screen opened on, held rather than re-derived —
  // the resume point moves with every answer, and the delivery plan is folded
  // from where the patient actually started. A fresh intake opens with the
  // welcome; a resumed one, or the steps after a voice hand-over, pick up.
  const [sitting] = useState(() => ({
    startId: initialQuestion.id,
    fresh: !editing && answers.length === 0 && Object.keys(prefill).length === 0 && !voiceFailed,
  }));

  const question = intakeQuestions.find((x) => x.id === currentId) ?? initialQuestion;
  // The line above the step: a welcome, a lead-in, a topic transition or an
  // acknowledgement — at most one after the opening, and none while editing a
  // single answer from the review. Pure and synchronous: the heading below
  // never waits on it, and it never touches the question's words.
  const deliveryLines = editing
    ? []
    : typedStepDelivery({
        applicable,
        answers,
        currentId: question.id,
        startId: sitting.startId,
        fresh: sitting.fresh,
        sessionSeed: visitId ?? "",
      });
  // INT-339 (MOTION-10, C16): the question's body is keyed by the question,
  // so a step change removes the old body in the commit that mounts the next
  // one, and only the next one fades in. No frame holds two questions.
  const step = typedStep(question.id, { reduce: reduceMotion });
  // The suggestion for THIS question (saved answers always win over it).
  const suggestion = answers.some((a) => a.questionId === question.id)
    ? undefined
    : prefill[question.id];

  // Mode context (INT-236): Hızlı default; Hastanedeyim → Detaylı (02 §2).
  const mode = note?.mode ?? "hizli";
  const detayli = mode === "detayli";
  const privacy = note?.privacy ?? "unchecked";

  /**
   * Commit one answer. `words` is the patient's own sentence for an open step
   * (INT-286) — recorded beside the coded values, never inside them, so no
   * free text can open a gate or reach a rule (invariant 1). The typed lane
   * resolves nothing from those words: the options are on screen and the tap
   * is the answer, so there is nothing here for a matcher to do. (The spoken
   * lane, which has no chips, reads the patient's words against the same
   * declared labels before handing anything the extract boundary cannot place
   * back to the patient — lib/intake/answerMatch.ts, INT-293.)
   */
  const commit = (values: string[], words?: string) => {
    if (visitId) {
      updateNote(visitId, { type: "answer", questionId: question.id, values, words });
    }
    if (editing) {
      // an edit returns straight to the review; a fresh run continues
      router.replace(`/(tabs)/visits/${visitId}/review`);
      return;
    }
    // Advance against the answers INCLUDING this commit, so a gate this
    // answer just opened (or closed) is honoured immediately.
    const nextAnswers = [
      ...answers.filter((a) => a.questionId !== question.id),
      { questionId: question.id, values, words },
    ];
    const nextQuestion = nextApplicableQuestion(intakeQuestions, nextAnswers, question.id);
    if (nextQuestion === null) {
      router.replace(`/(tabs)/visits/${visitId}/review`);
      return;
    }
    const nextPrefill = prefill[nextQuestion.id];
    setSelected(nextQuestion.kind === "text" ? [] : (nextPrefill?.values ?? []));
    setText(nextQuestion.kind === "text" ? (nextPrefill?.values.join(" ") ?? "") : "");
    setMeasure(null);
    setCurrentId(nextQuestion.id);
  };

  /**
   * The patient's own words to record with the answer being committed
   * (INT-286): what they typed or dictated into the open field, or — when
   * they are confirming a voice suggestion and wrote nothing — the verbatim
   * quote that suggestion came from. Undefined on a closed step, so nothing
   * changes for one.
   */
  const openWords = (confirmingSuggestion: boolean): string | undefined => {
    if (!isOpenAsk(question)) {
      return undefined;
    }
    const typed = text.trim();
    if (typed.length > 0) {
      return typed;
    }
    return confirmingSuggestion ? suggestion?.quote : undefined;
  };

  const toggleChip = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  // "Bitirdim" (02 §34): the clinic-interruptible checkpoint — instant, no
  // dialog, no confirmation — and land on the partial-note review. Committed
  // answers are untouched by the reducer (test-pinned: zero lost turns).
  // INT-321 relabelled it from "Sıranız geldi" to the plain first-person and
  // moved it off the per-question row: it belongs to the ayrıntılı flow, where
  // a patient standing in a corridor may be called in, and appears only once
  // something has been answered (there is nothing to keep before that).
  const finishNow = () => {
    if (visitId) {
      updateNote(visitId, { type: "checkpoint" });
      router.replace(`/(tabs)/visits/${visitId}/review`);
    }
  };
  const finishNowBar =
    detayli && answeredCount > 0 ? (
      <View style={styles.finishRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("intake.finishNow")}
          onPress={finishNow}
          style={[styles.finishChip, { backgroundColor: theme.surfaceRaised }]}
        >
          <AppText role="caption" color="primary">
            {t("intake.finishNow")}
          </AppText>
        </Pressable>
      </View>
    ) : null;

  // Environment self-check (02 §33): one calm question before Detaylı
  // continues. If privacy is not established, sensitive sections are
  // DEFERRED — not asked quieter, not asked in text — and the note carries
  // `eksik: ortam uygun değildi` (buildNote). Wellbeing is today's only
  // deferral consumer; the dev packs carry no sensitive-flagged questions.
  if (detayli && privacy === "unchecked" && !editing) {
    return (
      <ScrollView
        contentContainerStyle={[styles.content, underNav]}
        scrollIndicatorInsets={{ top: topInset }}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        <AppText role="question" heading>
          {t("intake.privacy.q")}
        </AppText>
        <AppText role="body" color="inkSoft">
          {t("intake.privacy.hint")}
        </AppText>
        <View style={styles.optionColumn}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("intake.privacy.notAlone")}
            style={styles.cardTarget}
            onPress={() => visitId && updateNote(visitId, { type: "privacy", alone: false })}
          >
            <Card>
              <AppText role="body">{t("intake.privacy.notAlone")}</AppText>
            </Card>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("intake.privacy.alone")}
            style={styles.cardTarget}
            onPress={() => visitId && updateNote(visitId, { type: "privacy", alone: true })}
          >
            <Card>
              <AppText role="body">{t("intake.privacy.alone")}</AppText>
            </Card>
          </Pressable>
        </View>
      </ScrollView>
    );
  }

  // INT-286 — the owner's report: the screen was "completly written and
  // option based". On an OPEN step the answer field comes first and the
  // options move under it as the fallback, so the patient's own words are
  // the primary act on this lane too. A single-select step therefore grows a
  // CTA it never had: without one, words typed and no card tapped would have
  // no way to be committed.
  const openAsk = isOpenAsk(question);
  // INT-136 — a step that reproduces one item of a validated instrument. It
  // owns the whole body: its title line IS the item, verbatim from the pack
  // (invariant 10), and its choices are the instrument's own, so the screen's
  // catalogue-driven title and option controls are not rendered beside them.
  // It commits on the tap, so it carries no CTA either.
  const instrumentStep = question.instrument !== undefined;
  const floatingCta = !instrumentStep && (question.kind !== "single" || openAsk);
  // INT-256: the text CTA used to read "Bitir" unconditionally, which was
  // true only while `extra` was the one text step in the pack. The universal
  // history block adds free-text steps mid-flow, so the label now follows
  // the flow: "Bitir" when this is the last applicable question (or an edit
  // returning to the review), "Devam" otherwise.
  const isLastApplicable =
    applicable.length > 0 && applicable[applicable.length - 1].id === question.id;
  const ctaLabel = editing || isLastApplicable ? t("intake.finish") : t("intake.next");

  return (
    <>
      <ScrollView
        contentContainerStyle={[
          styles.content,
          underNav,
          floatingCta ? { paddingBottom: barClearance } : null,
        ]}
        scrollIndicatorInsets={{ top: topInset }}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        // SC 1.3.4 (INT-360): the answer field scrolls clear of the keyboard,
        // which takes about half of a landscape window.
        automaticallyAdjustKeyboardInsets
      >
        {finishNowBar}
        {/* The deferral notice (02 §33) lived on the old mode row; it stays,
            as the calm one-liner that private questions are held for later,
            shown when a third party is present in the ayrıntılı flow. */}
        {detayli && privacy === "not_private" ? (
          <AppText role="caption" color="inkFaint">
            {t("intake.privacy.deferredInfo")}
          </AppText>
        ) : null}
        <QuestionProgress
          position={questionPosition(applicable, question.id, flowCanGrow)}
          capsule={flags.progressMicro ? { flow: applicable, flags } : undefined}
        />
        {/* INT-339 (MOTION-10, C16): the question, and only the question.
            The progress above and the glass-bar CTA below swap instantly
            with the step (C9), and the first step arrives with its container
            (skipEntering) rather than fading a second time inside it. */}
        <LayoutAnimationConfig skipEntering>
          <Animated.View key={step.key} entering={enteringFor(step.enter)} style={styles.step}>
            {voiceFailed && question.id === initialQuestion.id ? (
              // SC 4.1.3: why the conversation became these steps. A status, not
              // an error — nothing the patient did failed (INT-362).
              <AnnouncedText
                tone="status"
                role="caption"
                color="inkFaint"
                message={t("voiceFirst.failed")}
              />
            ) : null}
            {deliveryLines.map((utterance) => {
              const deckKey = asDeliveryKey(utterance.key);
              return deckKey === null ? null : (
                <AppText key={utterance.key} role="body" color="inkSoft">
                  {t(deckKey)}
                </AppText>
              );
            })}
            {/* The bar is untitled by design (pass 6), so the question line is
            this screen's title and must be a heading (SC 1.3.1). An instrument
            step's heading is the ITEM, so it is rendered by InstrumentStep and
            the catalogue title is not shown at all — two askings of one
            question is how a verbatim item stops being the one that was
            validated. */}
            {instrumentStep ? (
              <InstrumentStep
                instrument={question.instrument!}
                options={question.options ?? []}
                onSelect={(optionId) => commit([optionId])}
              />
            ) : (
              <AppText role="question" heading>
                {t(question.titleKey)}
              </AppText>
            )}
            {/* On an open step the invitation replaces the pack's control hint
            here: "Birden fazla seçebilirsiniz" describes the chips grid, and
            the grid is now below the answer field, so the hint travels down
            with the control it describes (the same rule INT-261 applied to
            the spoken turn). */}
            {instrumentStep ? null : openAsk ? (
              <AppText role="caption" color="inkSoft">
                {t("intake.open.hint")}
              </AppText>
            ) : question.hintKey ? (
              <AppText role="caption" color="inkSoft">
                {t(question.hintKey)}
              </AppText>
            ) : null}

            {suggestion !== undefined && suggestion.quote.length > 0 ? (
              // Provenance, verbatim: the patient's own words behind the
              // suggestion — quoted, never interpreted (INT-199).
              <Card>
                <AppText role="caption" color="inkFaint">
                  {t("voiceFirst.saidLabel")}
                </AppText>
                <AppText role="body" color="inkSoft">
                  “{suggestion.quote}”
                </AppText>
              </Card>
            ) : null}

            {/* INT-286 — the open answer, first. What the patient writes or
            dictates here is recorded as their own words and is NEVER put in
            `values`: the typed lane resolves nothing locally, because the
            only route from words to a declared option id is the INT-083
            extraction boundary and there is not going to be a second one.
            So an answer given only in words carries no coded value, opens no
            gate, and reaches the clinician as the sentence they said. */}
            {openAsk ? (
              <>
                <TextInput
                  accessibilityLabel={t(question.titleKey)}
                  accessibilityHint={t("intake.open.hint")}
                  allowFontScaling={false}
                  value={text}
                  onChangeText={setText}
                  onFocus={() => setFieldFocused(true)}
                  onBlur={() => setFieldFocused(false)}
                  multiline
                  style={[
                    styles.textField,
                    filledFieldChrome(theme, { focused: fieldFocused, increasedContrast }),
                    { color: theme.ink, fontSize: scaledSize("body", fontScale) },
                  ]}
                />
                {__DEV__ && consents?.voice === true ? (
                  <VoiceNote
                    onTranscript={(spoken) =>
                      setText((prev) =>
                        prev.trim().length > 0 ? `${prev.trim()} ${spoken}` : spoken,
                      )
                    }
                  />
                ) : null}
                <AppText role="caption" color="inkFaint">
                  {t("intake.open.orChoose")}
                </AppText>
                {question.hintKey ? (
                  <AppText role="caption" color="inkFaint">
                    {t(question.hintKey)}
                  </AppText>
                ) : null}
              </>
            ) : null}

            {question.kind === "chips" && !instrumentStep ? (
              <View style={styles.chipWrap}>
                {question.options!.map((o) => {
                  const on = selected.includes(o.id);
                  // INT-433: a filled capsule; selected is tinted AND checked,
                  // so the state is never carried by the hue alone (SC 1.4.1).
                  const look = chipChrome(theme, on);
                  return (
                    <Pressable
                      key={o.id}
                      accessibilityRole="checkbox"
                      accessibilityLabel={t(o.labelKey)}
                      accessibilityHint={t("a11y.selectHint")}
                      accessibilityState={{ checked: on }}
                      onPress={() => {
                        toggleChip(o.id);
                        // ADR-038 A2 (INT-462): every option ticks the same;
                        // a validated instrument's options never reach here.
                        haptic("select", { surface: "intakeChip", valueChanged: true });
                      }}
                      style={[styles.chip, { backgroundColor: look.backgroundColor }]}
                    >
                      {/* INT-492 (flag): the check slot is reserved in both
                          states, so a tap never reflows the chips. */}
                      {flags.progressMicro ? (
                        <ChipSlot selected={on} />
                      ) : look.check ? (
                        <Icon
                          name="checkmark"
                          size={scaledSize("label", fontScale)}
                          tintColor={theme.primary}
                        />
                      ) : null}
                      <AppText role="label" color={look.textColor} style={styles.chipLabel}>
                        {t(o.labelKey)}
                      </AppText>
                    </Pressable>
                  );
                })}
              </View>
            ) : null}

            {question.kind === "single" && !instrumentStep ? (
              <View style={styles.optionColumn}>
                {question.options!.map((o) => {
                  const suggested = suggestion?.values.includes(o.id) === true;
                  return (
                    <Pressable
                      key={o.id}
                      // One answer per turn: a radio says so, a button does not.
                      accessibilityRole="radio"
                      // The suggested card is marked by a wash only — the word
                      // "Önerilen" is inside the card, so it survives the merge
                      // as context after the option itself (SC 1.4.1, 2.5.3).
                      // The card renders "Önerilen yanıt" ABOVE the option, so
                      // the name follows the same order the eye reads.
                      accessibilityLabel={joinParts(
                        suggested ? t("voiceFirst.suggested") : null,
                        t(o.labelKey),
                      )}
                      // NOT `checked: suggested`. "Önerilen" means the voice pass
                      // proposed this option, not that the patient chose it, and
                      // nothing commits until the tap below (invariant 1). A
                      // reader announcing it as selected would be the one
                      // modality in which the suggestion looks like an answer.
                      accessibilityState={{ checked: false }}
                      style={styles.cardTarget}
                      onPress={() =>
                        commit(
                          resolveAnswer(
                            suggestion,
                            suggested ? { type: "confirm" } : { type: "change", values: [o.id] },
                          ),
                          // INT-286 — the provenance that belongs to THIS value:
                          // what the patient wrote in the open field if they
                          // wrote anything, otherwise the quote behind a
                          // suggestion they are confirming. Never the quote
                          // behind a suggestion they just overrode: those words
                          // were not said about this card.
                          openWords(suggested),
                        )
                      }
                    >
                      <Card wash={suggested ? "primary" : "none"}>
                        {suggested ? (
                          <AppText role="caption" color="primary">
                            {t("voiceFirst.suggested")}
                          </AppText>
                        ) : null}
                        <AppText role="body">
                          {/* invariant 22: the numeral is an INLINE render
                          beside the word it renders, on the same option
                          object — never a numeral inside the string. */}
                          {o.inline === undefined
                            ? t(o.labelKey)
                            : `${o.inline} — ${t(o.labelKey)}`}
                        </AppText>
                      </Card>
                    </Pressable>
                  );
                })}
              </View>
            ) : null}

            {question.kind === "measure" ? (
              <MeasureStepper question={question} value={measure} onChange={setMeasure} />
            ) : null}

            {question.kind === "text" ? (
              <>
                <TextInput
                  accessibilityLabel={t(question.titleKey)}
                  accessibilityHint={question.hintKey ? t(question.hintKey) : undefined}
                  allowFontScaling={false}
                  value={text}
                  onChangeText={setText}
                  onFocus={() => setFieldFocused(true)}
                  onBlur={() => setFieldFocused(false)}
                  multiline
                  style={[
                    styles.textField,
                    filledFieldChrome(theme, { focused: fieldFocused, increasedContrast }),
                    { color: theme.ink, fontSize: scaledSize("body", fontScale) },
                  ]}
                />
                {__DEV__ && consents?.voice === true ? (
                  <VoiceNote
                    onTranscript={(spoken) =>
                      setText((prev) =>
                        prev.trim().length > 0 ? `${prev.trim()} ${spoken}` : spoken,
                      )
                    }
                  />
                ) : null}
              </>
            ) : null}
          </Animated.View>
        </LayoutAnimationConfig>
      </ScrollView>
      {question.kind === "chips" && !instrumentStep ? (
        <GlassBar onHeight={setBarHeight}>
          <PrimaryButton
            label={ctaLabel}
            pressScale={flags.progressMicro}
            // INT-286: on an open step, words are an answer — the CTA opens
            // on either, so a patient who described it in a sentence is not
            // held at the screen until they also tap a chip.
            disabled={selected.length === 0 && !(openAsk && text.trim().length > 0)}
            onPress={() => commit(selected, openWords(false))}
          />
        </GlassBar>
      ) : null}
      {question.kind === "single" && openAsk ? (
        <GlassBar onHeight={setBarHeight}>
          <PrimaryButton
            label={ctaLabel}
            pressScale={flags.progressMicro}
            // A card tap commits on its own (above); this bar exists for the
            // answer given only in words. Disabled until there are some, so
            // it can never record an empty answer by being tapped through.
            disabled={text.trim().length === 0}
            onPress={() => commit([], openWords(false))}
          />
        </GlassBar>
      ) : null}
      {question.kind === "text" ? (
        <GlassBar onHeight={setBarHeight}>
          <PrimaryButton
            label={ctaLabel}
            pressScale={flags.progressMicro}
            onPress={() => commit(text.trim().length > 0 ? [text.trim()] : [])}
          />
        </GlassBar>
      ) : null}
      {question.kind === "measure" ? (
        <GlassBar onHeight={setBarHeight}>
          <PrimaryButton
            label={ctaLabel}
            pressScale={flags.progressMicro}
            // Disabled until the control has been MOVED: where a stepper
            // opens is an affordance, not an answer, and tapping through
            // must not be able to record one.
            disabled={measure === null}
            onPress={() => commit(measure === null ? [] : [String(measure)])}
          />
        </GlassBar>
      ) : null}
    </>
  );
}

/**
 * The guarded numeric control of invariant 22 (INT-282): a stepper between
 * the question's authored bounds. There is no keyboard, no parser and no
 * free numeral — the only way to produce a value is to move the control,
 * and the only way to read one back is `measurementLine`, which is the same
 * `useGrouping:false` + non-breaking number+unit render the note uses.
 *
 * Two step sizes rather than one, because a single ±1 would put a plausible
 * height forty taps away and a control nobody can face is a control people
 * work around.
 */
function MeasureStepper({
  question,
  value,
  onChange,
}: {
  question: IntakeQuestion;
  value: number | null;
  onChange: (next: number) => void;
}) {
  const theme = useTheme();
  const measure = question.measure;
  if (measure === undefined) {
    return null;
  }
  const shown = value ?? measure.start;
  const move = (delta: number) =>
    onChange(Math.min(measure.max, Math.max(measure.min, shown + delta)));

  const button = (delta: number, label: string, a11y: string) => (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={a11y}
      onPress={() => move(delta)}
      style={[styles.stepButton, { backgroundColor: theme.surface }]}
    >
      <AppText role="label" color="ink">
        {label}
      </AppText>
    </Pressable>
  );

  return (
    <View style={styles.measureBlock}>
      <View style={styles.measureRow}>
        {button(-measure.coarseStep, "−−", t("a11y.measure.decreaseMore"))}
        {button(-measure.step, "−", t("a11y.measure.decrease"))}
        <View style={styles.measureValue}>
          <AppText
            role="title"
            // Until the control is moved, the reading is where it OPENS and
            // is shown as such: faint, and not yet an answer.
            color={value === null ? "inkFaint" : "ink"}
          >
            {measurementLine(question, [String(shown)])}
          </AppText>
        </View>
        {button(measure.step, "+", t("a11y.measure.increase"))}
        {button(measure.coarseStep, "++", t("a11y.measure.increaseMore"))}
      </View>
      {value === null ? (
        <AppText role="caption" color="inkFaint">
          {t("intake.measure.untouched")}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screenFlush: { padding: 0 },
  integrityWarn: { paddingHorizontal: spacing.screen, paddingTop: spacing.sm, gap: 2 },
  body: { flex: 1 },
  // The typed lane fills the body exactly as StepFlow did before it had a
  // container, so the floating glass bar still anchors to the same edge.
  lane: { flex: 1 },
  content: { gap: spacing.md, padding: spacing.screen, paddingBottom: spacing.xl },
  // One question's body: the same rhythm as the scroll content around it.
  step: { gap: spacing.md },
  // The Card inside is far taller than the floor; declaring it keeps the
  // SC 2.5.8 guarantee a property of the control rather than of its content.
  cardTarget: { minHeight: MIN_TAP },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    borderRadius: radius.chip,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    minHeight: MIN_TAP,
    justifyContent: "center",
    // A wrap item gets no shrink in React Native, so without this an option
    // label wider than the row makes the CHIP wider than the row and there is
    // no horizontal scroll to reach it. Truncating is banned (files/00 §2), so
    // the bound is what keeps a long Turkish label reachable at the largest
    // step the app's own control offers (INT-295: that control REPLACES the OS
    // value, so 1.0 says nothing about what it can ask for).
    maxWidth: "100%",
  },
  // The label wraps inside the capsule rather than pushing the check out.
  chipLabel: { flexShrink: 1 },
  optionColumn: { gap: spacing.sm },
  // The "Bitirdim" checkpoint (INT-321): a quiet chip aligned to the top-right
  // of the flow — a control the patient reaches for rarely, never the loudest
  // thing on the screen, and a real touch target by box (not slop).
  finishRow: { flexDirection: "row", justifyContent: "flex-end" },
  finishChip: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    minHeight: MIN_TAP,
    alignItems: "center",
    justifyContent: "center",
  },
  measureBlock: { gap: spacing.xs },
  measureRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  measureValue: { flex: 1, alignItems: "center" },
  stepButton: {
    borderRadius: radius.control,
    minWidth: MIN_TAP,
    minHeight: MIN_TAP,
    alignItems: "center",
    justifyContent: "center",
  },
  // The filled field (INT-433): its fill, ring and width come from
  // filledFieldChrome, which holds one border width in every state.
  textField: {
    borderRadius: radius.control,
    minHeight: 120,
    padding: spacing.md,
    textAlignVertical: "top",
    fontFamily: fonts.sans,
  },
});
