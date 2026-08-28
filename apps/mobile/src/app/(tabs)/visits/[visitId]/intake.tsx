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
 * Voice-first entry (INT-199): a FRESH intake (not edit mode, no answers)
 * with dev-lane voice available opens with the "Sesli anlatın" step — the
 * patient speaks freely, the transcript becomes per-question ANSWER
 * SUGGESTIONS (extract daemon), and the same steps run as a confirm flow:
 * suggested answers pre-selected with the patient's verbatim words as
 * provenance, still one question per turn. Skipping or any failure lands in
 * this exact manual flow — never a dead end. Suggestions are never triage
 * or a diagnosis (invariant 1); the transcript renders only as quotes.
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
import { DialogueIntake } from "@/components/DialogueIntake";
import { VoiceFirstIntake } from "@/components/VoiceFirstIntake";
import { VoiceNote } from "@/components/VoiceNote";
import { voiceAllowedForIntegrity } from "@/lib/auth/integrity";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import { t } from "@/lib/i18n";
import { packForDepartment, type IntakeQuestion } from "@/lib/intake/questions";
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
        <View style={styles.integrityWarn}>
          <AppText role="label">{t("auth.integrity.warnTitle")}</AppText>
          <AppText role="caption" color="inkSoft">
            {t("auth.integrity.warnBody")}
          </AppText>
        </View>
      ) : null}
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
          // Voice chat mode (INT-233/235): ask-ahead conversation over the
          // same pack. Answers commit per confirm, so a service failure
          // resumes these exact manual steps at the first unanswered
          // question with the honest notice; a settled dialogue (or a
          // chosen exit) hands over ONLY the unanswered questions, any
          // unconfirmed suggestions riding along as prefill.
          <DialogueIntake
            visitId={visitId}
            questions={intakeQuestions}
            packName={visit?.department ?? "general"}
            onFailed={() => dispatchVoice({ type: "failure" })}
            onHandoff={(prefill) => dispatchVoice({ type: "candidates", prefill })}
          />
        ) : (
          <VoiceFirstIntake
            state={voiceState}
            dispatch={dispatchVoice}
            questions={intakeQuestions}
            packName={visit?.department ?? "general"}
          />
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

  // `q` = edit mode: jump straight to that question with its current answer
  // preloaded (the review screen's pencil). Otherwise resume at the first
  // unanswered question.
  const answeredIds = new Set(note?.answers.map((a) => a.questionId));
  const requested = requestedQ ? intakeQuestions.findIndex((x) => x.id === requestedQ) : -1;
  const firstUnanswered = intakeQuestions.findIndex((x) => !answeredIds.has(x.id));
  const initialStep =
    requested !== -1
      ? requested
      : firstUnanswered === -1
        ? intakeQuestions.length - 1
        : firstUnanswered;
  const initialQuestion = intakeQuestions[initialStep];
  const initialAnswer = note?.answers.find((a) => a.questionId === initialQuestion.id);
  const initialPrefill = initialAnswer === undefined ? prefill[initialQuestion.id] : undefined;
  const initialKind = initialQuestion.kind;
  const [step, setStep] = useState(initialStep);
  const [selected, setSelected] = useState<string[]>(
    initialKind === "text" ? [] : (initialAnswer?.values ?? initialPrefill?.values ?? []),
  );
  const [text, setText] = useState(
    initialKind === "text"
      ? (initialAnswer?.values.join(" ") ?? initialPrefill?.values.join(" ") ?? "")
      : "",
  );
  const editing = requested !== -1;

  const question = intakeQuestions[step];
  const last = step === intakeQuestions.length - 1;
  // The suggestion for THIS question (saved answers always win over it).
  const suggestion =
    note?.answers.some((a) => a.questionId === question.id) === true
      ? undefined
      : prefill[question.id];

  const commit = (values: string[]) => {
    if (visitId) {
      updateNote(visitId, { type: "answer", questionId: question.id, values });
    }
    if (editing || last) {
      // an edit returns straight to the review; a fresh run continues
      router.replace(`/(tabs)/visits/${visitId}/review`);
    } else {
      const next = step + 1;
      const nextQuestion = intakeQuestions[next];
      const nextPrefill = prefill[nextQuestion.id];
      setSelected(nextQuestion.kind === "text" ? [] : (nextPrefill?.values ?? []));
      setText(nextQuestion.kind === "text" ? (nextPrefill?.values.join(" ") ?? "") : "");
      setStep(next);
    }
  };

  const toggleChip = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const floatingCta = question.kind !== "single";

  return (
    <>
      <ScrollView
        contentContainerStyle={[styles.content, floatingCta ? styles.contentUnderBar : null]}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        <View style={styles.progressRow}>
          {intakeQuestions.map((item, i) => (
            <View
              key={item.id}
              style={[
                styles.progressDot,
                { backgroundColor: i <= step ? theme.primary : theme.border },
              ]}
            />
          ))}
          <AppText role="caption" color="inkFaint" style={styles.progressCount}>
            {step + 1} / {intakeQuestions.length}
          </AppText>
        </View>
        {voiceFailed && step === initialStep ? (
          <AppText role="caption" color="inkFaint">
            {t("voiceFirst.failed")}
          </AppText>
        ) : null}
        <AppText role="hero">{t(question.titleKey)}</AppText>
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
                  accessibilityRole="button"
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

const styles = StyleSheet.create({
  screenFlush: { padding: 0 },
  integrityWarn: { paddingHorizontal: spacing.screen, paddingTop: spacing.sm, gap: 2 },
  body: { flex: 1 },
  content: { gap: spacing.md, padding: spacing.screen, paddingBottom: spacing.xl },
  contentUnderBar: { paddingBottom: GLASS_BAR_CLEARANCE },
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
