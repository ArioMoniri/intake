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
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";

import { GlassBar, useGlassBarClearance } from "@/components/GlassBar";
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
import { DevVoiceBanner } from "@/components/DevVoiceBanner";
import { DialogueGate } from "@/components/DialogueGate";
import { DialogueIntake } from "@/components/DialogueIntake";
import { ModeBar } from "@/components/ModeBar";
import { VoiceNote } from "@/components/VoiceNote";
import { voiceAllowedForIntegrity } from "@/lib/auth/integrity";
import { joinParts } from "@/lib/a11y/labels";
import { MIN_TAP } from "@/lib/a11y/target";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import type { ReachabilityReport } from "@/lib/dev/hosts";
import { t } from "@/lib/i18n";
import { measurementLine } from "@/lib/intake/baseLayer";
import {
  applicableQuestions,
  isOpenAsk,
  nextApplicableQuestion,
  packForVisit,
  spokenPack,
  type IntakeQuestion,
} from "@/lib/intake/questions";
import {
  initialVoiceIntakeState,
  resolveAnswer,
  voiceIntakeReducer,
  type PrefillMap,
} from "@/lib/intake/voiceFirst";
import { useAppearance } from "@/lib/prefs/AppearanceProvider";
import { useSession } from "@/lib/session";
import { fonts, radius, scaledSize, spacing } from "@/lib/theme";

// With the top bar shown, the header owns the top inset (design pass 6).
const FLOW_EDGES = ["left", "right"] as const;

export default function TypedIntake() {
  useClinicalScreenPrivacy(); // FLAG_SECURE-class capture blocking (INT-131)
  const headerOptions = useStackHeader();
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
  const dark = useScheme() === "dark";
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

  // INT-286 — the owner's report: the screen was "completly written and
  // option based". On an OPEN step the answer field comes first and the
  // options move under it as the fallback, so the patient's own words are
  // the primary act on this lane too. A single-select step therefore grows a
  // CTA it never had: without one, words typed and no card tapped would have
  // no way to be committed.
  const openAsk = isOpenAsk(question);
  const floatingCta = question.kind !== "single" || openAsk;
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
          floatingCta ? { paddingBottom: barClearance } : null,
        ]}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        {modeBar}
        <View style={styles.progressRow}>
          {/* SC 1.4.1: per-question progress exists here ONLY as a hue, and
              a hue is not a fact. The dots are hidden as the decoration
              they are and the counter beside them carries the state.

              INT-295: the dots own a box that WRAPS and SHRINKS, and the
              counter does neither. A Detaylı flow reaches about thirty dots,
              which at 8 pt plus a 4 pt gap is longer than the content width
              on its own — so the row used to push the counter off the right
              edge at the DEFAULT text size, and the fact went with it. The
              decoration yields the room now; the fact keeps it. */}
          <View style={styles.progressRail}>
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
          </View>
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
        {/* On an open step the invitation replaces the pack's control hint
            here: "Birden fazla seçebilirsiniz" describes the chips grid, and
            the grid is now below the answer field, so the hint travels down
            with the control it describes (the same rule INT-261 applied to
            the spoken turn). */}
        {openAsk ? (
          <AppText role="body" color="inkSoft">
            {t("intake.open.hint")}
          </AppText>
        ) : question.hintKey ? (
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
                      {o.inline === undefined ? t(o.labelKey) : `${o.inline} — ${t(o.labelKey)}`}
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
        <GlassBar onHeight={setBarHeight}>
          <PrimaryButton
            label={ctaLabel}
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
            onPress={() => commit(text.trim().length > 0 ? [text.trim()] : [])}
          />
        </GlassBar>
      ) : null}
      {question.kind === "measure" ? (
        <GlassBar onHeight={setBarHeight}>
          <PrimaryButton
            label={ctaLabel}
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
      style={[styles.stepButton, { backgroundColor: theme.surface, borderColor: theme.border }]}
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
  content: { gap: spacing.md, padding: spacing.screen, paddingBottom: spacing.xl },
  // The Card inside is far taller than the floor; declaring it keeps the
  // SC 2.5.8 guarantee a property of the control rather than of its content.
  cardTarget: { minHeight: MIN_TAP },
  progressRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  // The decoration is the part that gives way: it wraps onto a second line
  // and shrinks, so the counter beside it never has to leave the screen.
  progressRail: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: spacing.xs,
    flexShrink: 1,
  },
  progressDot: { width: 8, height: 8, borderRadius: radius.chip },
  // Tabular figures so the counter doesn't reflow step to step (design
  // pass 6 microtypography — Oura's numeric rows are tabular).
  // Never shrinks: the count is the fact, and it fits the narrowest phone at
  // the largest step in both catalogues (asserted in e2e/overflow.spec.ts).
  progressCount: { flexShrink: 0, fontVariant: ["tabular-nums"] },
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
  measureBlock: { gap: spacing.xs },
  measureRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  measureValue: { flex: 1, alignItems: "center" },
  stepButton: {
    borderRadius: radius.control,
    borderWidth: 1,
    minWidth: MIN_TAP,
    minHeight: MIN_TAP,
    alignItems: "center",
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
});
