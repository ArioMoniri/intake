/**
 * Typed intake shell (INT-179): ONE question per screen (Alan pacing) —
 * chips multi-select (CVS grid), single-select cards, then free text.
 * Progress is dots + numerals; answers land in the session note state, so
 * leaving and returning resumes at the first unanswered question.
 * Fixture questions only — the compiled protocol set (INT-096) replaces them.
 * Design pass 3: the step's one CTA sits on a floating glass bar (Oura
 * chrome) and the question body scrolls under it; single-select steps have
 * no CTA and no bar.
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
import { useReducer, useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View, useColorScheme } from "react-native";

import { GLASS_BAR_CLEARANCE, GlassBar } from "@/components/GlassBar";
import {
  AppText,
  Card,
  PrimaryButton,
  Screen,
  useFontScale,
  useStackHeader,
  useTheme,
} from "@/components/Themed";
import { DevVoiceBanner } from "@/components/DevVoiceBanner";
import { DialogueGate } from "@/components/DialogueGate";
import { DialogueIntake } from "@/components/DialogueIntake";
import { VoiceNote } from "@/components/VoiceNote";
import { voiceAllowedForIntegrity } from "@/lib/auth/integrity";
import { joinParts } from "@/lib/a11y/labels";
import { MIN_TAP, verticalSlop } from "@/lib/a11y/target";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import type { ReachabilityReport } from "@/lib/dev/hosts";
import { t } from "@/lib/i18n";
import {
  applicableQuestions,
  nextApplicableQuestion,
  packForDepartment,
  type IntakeQuestion,
} from "@/lib/intake/questions";
import {
  initialVoiceIntakeState,
  resolveAnswer,
  voiceIntakeReducer,
  type PrefillMap,
} from "@/lib/intake/voiceFirst";
import { useSession } from "@/lib/session";
import { fonts, radius, scaledSize, spacing } from "@/lib/theme";

// With the top bar shown, the header owns the top inset (design pass 6).
const FLOW_EDGES = ["left", "right"] as const;

export default function TypedIntake() {
  useClinicalScreenPrivacy(); // FLAG_SECURE-class capture blocking (INT-131)
  const headerOptions = useStackHeader();
  const { visitId, q } = useLocalSearchParams<{ visitId: string; q?: string }>();
  const { notes, consents, visits, integrity } = useSession();
  const note = notes[visitId ?? ""];
  const visit = visits.find((v) => v.id === visitId);
  const intakeQuestions = packForDepartment(visit?.department);

  // Voice goes FIRST on a fresh run: not edit mode, nothing answered yet,
  // voice consent ON, dev lane present. The ASR probe gates inside the flow.
  // Jailbreak/root soft signal (10 §4, INT-131): a compromised device gets
  // the typed lane plus the warning banner, never voice.
  const editing = typeof q === "string" && q.length > 0;
  const integrityCompromised = !voiceAllowedForIntegrity(integrity);
  const voiceEligible =
    __DEV__ &&
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

  return (
    <Screen style={styles.screenFlush} edges={FLOW_EDGES}>
      {/* Design pass 6: every Oura full-screen flow carries a top-left way
          out (Mobbin 11265937, 96fb49c7); ours had none. Back-only bar —
          the serif question line stays the screen's title, so the bar
          itself is untitled (the resilience-sheet anatomy, b67baac0). */}
      <Stack.Screen options={headerOptions("")} />
      {/* Focused flow (design pass 4): the tab rail unmounts here, so the
          glass bar owns the physical bottom edge, home indicator included. */}
      {integrityCompromised ? (
        <View
          accessible
          accessibilityLabel={joinParts(
            t("auth.integrity.warnTitle"),
            t("auth.integrity.warnBody"),
          )}
          accessibilityLiveRegion="polite"
          style={styles.integrityWarn}
        >
          <AppText role="label">{t("auth.integrity.warnTitle")}</AppText>
          <AppText role="caption" color="inkSoft">
            {t("auth.integrity.warnBody")}
          </AppText>
        </View>
      ) : null}
      <DevVoiceBanner report={voiceProbe} />
      <View style={styles.body}>
        {voiceState.phase === "steps" ? (
          <StepFlow
            visitId={visitId}
            requestedQ={q}
            intakeQuestions={intakeQuestions}
            prefill={voiceState.prefill}
            voiceFailed={voiceState.failed}
          />
        ) : voiceState.phase === "dialogue" ? (
          // The intake (INT-233/235/239): an ask-ahead conversation over
          // the same pack, entered directly. Answers commit per confirm, so
          // a service failure resumes these exact manual steps at the first
          // unanswered question with the honest notice; a settled dialogue
          // (or a chosen exit) hands over ONLY the unanswered questions,
          // any unconfirmed suggestions riding along as prefill.
          <DialogueIntake
            visitId={visitId}
            questions={intakeQuestions}
            packName={visit?.department ?? "general"}
            onFailed={(prefill) => dispatchVoice({ type: "failure", prefill })}
            onHandoff={(prefill) => dispatchVoice({ type: "candidates", prefill })}
          />
        ) : (
          <DialogueGate dispatch={dispatchVoice} onProbe={setVoiceProbe} />
        )}
      </View>
    </Screen>
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
}

function StepFlow({ visitId, requestedQ, intakeQuestions, prefill, voiceFailed }: StepFlowProps) {
  const router = useRouter();
  const theme = useTheme();
  const dark = useColorScheme() === "dark";
  const fontScale = useFontScale();
  const { notes, updateNote, consents } = useSession();
  const note = notes[visitId ?? ""];

  // Adaptive flow (INT-236): the applicable list derives from the committed
  // answers on EVERY render, so gates open and close as answers change and
  // the progress denominator is honest ("n of applicable", never the full
  // pack). The advance rule lives in nextApplicableQuestion (pack layer).
  const answers = note?.answers ?? [];
  const applicable = applicableQuestions(intakeQuestions, answers);

  // `q` = edit mode: jump straight to that question with its current answer
  // preloaded (the review screen's pencil). Otherwise resume at the first
  // unanswered APPLICABLE question.
  const answeredIds = new Set(answers.map((a) => a.questionId));
  const requested = requestedQ ? intakeQuestions.find((x) => x.id === requestedQ) : undefined;
  const firstUnanswered = applicable.find((x) => !answeredIds.has(x.id));
  const initialQuestion = requested ?? firstUnanswered ?? applicable[applicable.length - 1];
  const initialAnswer = answers.find((a) => a.questionId === initialQuestion.id);
  const initialPrefill = initialAnswer === undefined ? prefill[initialQuestion.id] : undefined;
  const initialKind = initialQuestion.kind;
  const [currentId, setCurrentId] = useState(initialQuestion.id);
  const [selected, setSelected] = useState<string[]>(
    initialKind === "text" ? [] : (initialAnswer?.values ?? initialPrefill?.values ?? []),
  );
  const [text, setText] = useState(
    initialKind === "text"
      ? (initialAnswer?.values.join(" ") ?? initialPrefill?.values.join(" ") ?? "")
      : "",
  );
  const editing = requested !== undefined;

  const question = intakeQuestions.find((x) => x.id === currentId) ?? initialQuestion;
  const stepIndex = Math.max(
    applicable.findIndex((x) => x.id === question.id),
    0,
  );
  // Progress is honest about a flow whose length is not fixed (INT-239):
  // the count is what has been ANSWERED — never "x / 9" against a total
  // that the next answer can change — and when a gate could still open we
  // say so in one line rather than letting the dots imply a finish line.
  const answeredCount = applicable.filter((item) => answeredIds.has(item.id)).length;
  const flowCanGrow = applicable.length < intakeQuestions.length;
  // The suggestion for THIS question (saved answers always win over it).
  const suggestion = answers.some((a) => a.questionId === question.id)
    ? undefined
    : prefill[question.id];

  // Mode context (INT-236): Hızlı default; Hastanedeyim → Detaylı (02 §2).
  const mode = note?.mode ?? "hizli";
  const detayli = mode === "detayli";
  const privacy = note?.privacy ?? "unchecked";

  const commit = (values: string[]) => {
    if (visitId) {
      updateNote(visitId, { type: "answer", questionId: question.id, values });
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
      { questionId: question.id, values },
    ];
    const nextQuestion = nextApplicableQuestion(intakeQuestions, nextAnswers, question.id);
    if (nextQuestion === null) {
      router.replace(`/(tabs)/visits/${visitId}/review`);
      return;
    }
    const nextPrefill = prefill[nextQuestion.id];
    setSelected(nextQuestion.kind === "text" ? [] : (nextPrefill?.values ?? []));
    setText(nextQuestion.kind === "text" ? (nextPrefill?.values.join(" ") ?? "") : "");
    setCurrentId(nextQuestion.id);
  };

  const toggleChip = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  // "Sıranız geldi" (02 §34): checkpoint INSTANTLY — no dialog, no
  // confirmation — and land on the partial-note review. Committed answers
  // are untouched by the reducer (test-pinned: zero lost turns).
  const queueCalled = () => {
    if (visitId) {
      updateNote(visitId, { type: "checkpoint" });
      router.replace(`/(tabs)/visits/${visitId}/review`);
    }
  };

  const modeBar = (
    <ModeBar
      detayli={detayli}
      deferredNotice={detayli && privacy === "not_private"}
      onToggleMode={() =>
        visitId && updateNote(visitId, { type: "mode", mode: detayli ? "hizli" : "detayli" })
      }
      onQueueCalled={queueCalled}
    />
  );

  // Environment self-check (02 §33): one calm question before Detaylı
  // continues. If privacy is not established, sensitive sections are
  // DEFERRED — not asked quieter, not asked in text — and the note carries
  // `eksik: ortam uygun değildi` (buildNote). Wellbeing is today's only
  // deferral consumer; the dev packs carry no sensitive-flagged questions.
  if (detayli && privacy === "unchecked" && !editing) {
    return (
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        {modeBar}
        <AppText role="hero" heading>
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

  const floatingCta = question.kind !== "single";

  return (
    <>
      <ScrollView
        contentContainerStyle={[styles.content, floatingCta ? styles.contentUnderBar : null]}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        {modeBar}
        <View style={styles.progressRow}>
          {/* SC 1.4.1: per-question progress exists here ONLY as a hue, and
              a hue is not a fact. The dots are hidden as the decoration
              they are and the counter beside them carries the state. */}
          {applicable.map((item, i) => (
            <View
              key={item.id}
              accessibilityElementsHidden
              importantForAccessibility="no-hide-descendants"
              style={[
                styles.progressDot,
                {
                  backgroundColor:
                    answeredIds.has(item.id) || i === stepIndex ? theme.primary : theme.border,
                },
              ]}
            />
          ))}
          <AppText role="caption" color="inkFaint" style={styles.progressCount}>
            {answeredCount} {t("intake.progress.answered")}
          </AppText>
        </View>
        {flowCanGrow ? (
          <AppText role="caption" color="inkFaint">
            {t("intake.progress.grows")}
          </AppText>
        ) : null}
        {voiceFailed && question.id === initialQuestion.id ? (
          <AppText role="caption" color="inkFaint">
            {t("voiceFirst.failed")}
          </AppText>
        ) : null}
        {/* The bar is untitled by design (pass 6), so the question line is
            this screen's title and must be a heading (SC 1.3.1). */}
        <AppText role="hero" heading>
          {t(question.titleKey)}
        </AppText>
        {question.hintKey ? (
          <AppText role="body" color="inkSoft">
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

        {question.kind === "chips" ? (
          <View style={styles.chipWrap}>
            {question.options!.map((o) => {
              const on = selected.includes(o.id);
              return (
                <Pressable
                  key={o.id}
                  accessibilityRole="checkbox"
                  accessibilityLabel={t(o.labelKey)}
                  accessibilityHint={t("a11y.selectHint")}
                  accessibilityState={{ checked: on }}
                  onPress={() => toggleChip(o.id)}
                  style={[
                    styles.chip,
                    {
                      backgroundColor: on ? theme.primarySoft : theme.surface,
                      // Oura chips are filled, borderless in dark (tonal
                      // separation); light keeps the hairline (pass 4).
                      borderColor: on ? theme.primary : dark ? "transparent" : theme.border,
                    },
                  ]}
                >
                  <AppText role="label" color={on ? "primary" : "ink"}>
                    {t(o.labelKey)}
                  </AppText>
                </Pressable>
              );
            })}
          </View>
        ) : null}

        {question.kind === "single" ? (
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
                    )
                  }
                >
                  <Card wash={suggested ? "primary" : "none"}>
                    {suggested ? (
                      <AppText role="caption" color="primary">
                        {t("voiceFirst.suggested")}
                      </AppText>
                    ) : null}
                    <AppText role="body">{t(o.labelKey)}</AppText>
                  </Card>
                </Pressable>
              );
            })}
          </View>
        ) : null}

        {question.kind === "text" ? (
          <>
            <TextInput
              accessibilityLabel={t(question.titleKey)}
              accessibilityHint={question.hintKey ? t(question.hintKey) : undefined}
              allowFontScaling={false}
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
            {__DEV__ && consents?.voice === true ? (
              <VoiceNote
                onTranscript={(spoken) =>
                  setText((prev) => (prev.trim().length > 0 ? `${prev.trim()} ${spoken}` : spoken))
                }
              />
            ) : null}
          </>
        ) : null}
      </ScrollView>
      {question.kind === "chips" ? (
        <GlassBar>
          <PrimaryButton
            label={editing ? t("intake.finish") : t("intake.next")}
            disabled={selected.length === 0}
            onPress={() => commit(selected)}
          />
        </GlassBar>
      ) : null}
      {question.kind === "text" ? (
        <GlassBar>
          <PrimaryButton
            label={t("intake.finish")}
            onPress={() => commit(text.trim().length > 0 ? [text.trim()] : [])}
          />
        </GlassBar>
      ) : null}
    </>
  );
}

interface ModeBarProps {
  detayli: boolean;
  /** Show the calm one-liner that private questions are deferred (02 §33). */
  deferredNotice: boolean;
  onToggleMode: () => void;
  onQueueCalled: () => void;
}

/**
 * The quiet mode row (INT-236): the "Hastanedeyim" switch (02 §2 table —
 * Detaylı trigger) and, while Detaylı is on, the persistent "Sıranız geldi"
 * affordance (02 §34). Both are caption-register chips — mode is context,
 * never the screen's subject.
 */
function ModeBar({ detayli, deferredNotice, onToggleMode, onQueueCalled }: ModeBarProps) {
  const theme = useTheme();
  return (
    <View style={styles.modeBlock}>
      <View style={styles.modeRow}>
        <Pressable
          accessibilityRole="switch"
          accessibilityLabel={t("intake.mode.hastanedeyim")}
          accessibilityState={{ checked: detayli }}
          hitSlop={verticalSlop(26)}
          onPress={onToggleMode}
          style={[
            styles.modeChip,
            { backgroundColor: detayli ? theme.primarySoft : theme.surfaceRaised },
          ]}
        >
          <AppText role="caption" color={detayli ? "primary" : "inkSoft"}>
            {t("intake.mode.hastanedeyim")}
          </AppText>
        </Pressable>
        {detayli ? (
          <>
            <AppText role="caption" color="inkFaint">
              {t("intake.mode.detayliOn")}
            </AppText>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("intake.queue.called")}
              hitSlop={verticalSlop(26)}
              onPress={onQueueCalled}
              style={[styles.modeChip, styles.queueChip, { backgroundColor: theme.surfaceRaised }]}
            >
              <AppText role="caption" color="primary">
                {t("intake.queue.called")}
              </AppText>
            </Pressable>
          </>
        ) : null}
      </View>
      {deferredNotice ? (
        <AppText role="caption" color="inkFaint">
          {t("intake.privacy.deferredInfo")}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screenFlush: { padding: 0 },
  integrityWarn: { paddingHorizontal: spacing.screen, paddingTop: spacing.sm, gap: 2 },
  body: { flex: 1 },
  content: { gap: spacing.md, padding: spacing.screen, paddingBottom: spacing.xl },
  contentUnderBar: { paddingBottom: GLASS_BAR_CLEARANCE },
  modeBlock: { gap: spacing.xs },
  modeRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  modeChip: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
  },
  queueChip: { marginLeft: "auto" },
  // The Card inside is far taller than the floor; declaring it keeps the
  // SC 2.5.8 guarantee a property of the control rather than of its content.
  cardTarget: { minHeight: MIN_TAP },
  progressRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  progressDot: { width: 8, height: 8, borderRadius: radius.chip },
  // Tabular figures so the counter doesn't reflow step to step (design
  // pass 6 microtypography — Oura's numeric rows are tabular).
  progressCount: { fontVariant: ["tabular-nums"] },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    borderRadius: radius.chip,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    minHeight: 44,
    justifyContent: "center",
  },
  optionColumn: { gap: spacing.sm },
  textField: {
    borderRadius: radius.control,
    borderWidth: 1,
    minHeight: 120,
    padding: spacing.md,
    textAlignVertical: "top",
    fontFamily: fonts.sans,
  },
});
