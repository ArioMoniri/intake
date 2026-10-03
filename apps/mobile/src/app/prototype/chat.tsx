/**
 * The conversation stage, prototype route (development builds only).
 *
 * The owner, on PR #792 (3 Oct 2026), said the chat still looks old and asked
 * for a bold redesign: modern, dynamic, with motion, and like a health app
 * such as Oura. This route shows the proposed direction in every turn state,
 * picked by `?state=`, so each state can be judged and captured exactly:
 * idle, speaking, listening, typed and confirm. It renders catalogue strings
 * only, and question text is verbatim. It is not wired to a session. Once the
 * owner approves the direction, DialogueIntake adopts these components and
 * this route goes.
 *
 * A release build renders nothing here.
 */
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { AmbientBackdrop } from "@/components/stage/AmbientBackdrop";
import {
  AnswerCard,
  GlassComposer,
  StageButton,
  StageTopBar,
  type ComposerControl,
} from "@/components/stage/StageControls";
import { VoiceOrb } from "@/components/stage/VoiceOrb";
import { AppText, useScheme } from "@/components/Themed";
import { useGlassMode } from "@/components/glassMode";
import { useIncreasedContrast, useReducedMotion } from "@/lib/a11y/prefs";
import { t, type MessageKey } from "@/lib/i18n";
import type { OrbState } from "@/lib/motion/orb";
import { stageOrbMotion } from "@/lib/stage/orb";
import { stagePalette } from "@/lib/stage/palette";
import { fonts } from "@/lib/theme";

const ROUNDED = fonts.rounded.ios;

type StageState = "idle" | "speaking" | "listening" | "typed" | "confirm";
const STATES: readonly StageState[] = ["idle", "speaking", "listening", "typed", "confirm"];

const ORB: Record<StageState, OrbState> = {
  idle: "idle",
  speaking: "speaking",
  listening: "listening",
  typed: "idle",
  confirm: "idle",
};

const ORB_SIZE: Record<StageState, number> = {
  idle: 112,
  speaking: 132,
  listening: 156,
  typed: 0,
  confirm: 0,
};

const CAPTION: Partial<Record<StageState, MessageKey>> = {
  speaking: "dialogue.speakingHint",
  listening: "voiceFirst.listening",
};

const OPTIONS: readonly MessageKey[] = [
  "intake.opt.pain",
  "intake.opt.fever",
  "intake.opt.cough",
  "intake.opt.dyspnoea",
  "intake.opt.fatigue",
  "intake.opt.stomach",
  "intake.opt.headache",
  "intake.opt.other",
];

export default function ChatStagePrototype() {
  const params = useLocalSearchParams<{ state?: string }>();
  const state: StageState = STATES.includes(params.state as StageState)
    ? (params.state as StageState)
    : "idle";
  if (!__DEV__) {
    return null;
  }
  // A new state is a new turn: remount, so its loops and its draft start fresh.
  return <Stage key={state} state={state} />;
}

function Stage({ state }: { state: StageState }) {
  const router = useRouter();
  const scheme = useScheme() === "dark" ? "dark" : "light";
  const glass = useGlassMode() === "liquid";
  const reduce = useReducedMotion();
  const palette = stagePalette(scheme, {
    reduceTransparency: !glass,
    increasedContrast: useIncreasedContrast() === "high",
  });
  const surface = { palette, scheme, glass } as const;
  const motion = stageOrbMotion(ORB[state], { reduce, redPresented: false, flag: true });
  const [draft, setDraft] = useState(state === "typed" ? t("intake.opt.fatigue") : "");
  const [selected, setSelected] = useState<readonly MessageKey[]>(["intake.opt.fatigue"]);

  const control: ComposerControl =
    draft.trim().length > 0 ? "send" : state === "listening" ? "stop" : "mic";
  const controlLabel: MessageKey =
    control === "send"
      ? "dialogue.send"
      : control === "stop"
        ? "voiceFirst.stop"
        : state === "confirm"
          ? "dialogue.speakCorrection"
          : "dialogue.mic";
  const caption = CAPTION[state];

  return (
    <View style={[styles.root, { backgroundColor: palette.base }]}>
      <Stack.Screen options={{ headerShown: false }} />
      <AmbientBackdrop palette={palette} />
      <SafeAreaView edges={["top"]}>
        <StageTopBar
          surface={surface}
          onBack={() => router.back()}
          backLabel={t("dialogue.close")}
          status={t("dialogue.noteForming")}
          count={`0 / 10 ${t("dialogue.sectionsLabel")}`}
        />
      </SafeAreaView>
      <ScrollView style={styles.flex} contentContainerStyle={styles.content}>
        <AppText
          role="label"
          style={[styles.rounded, { color: palette.accent, fontWeight: "600" }]}
        >
          {t("dialogue.kicker")}
        </AppText>
        <AppText
          role="hero"
          heading
          style={[styles.rounded, { color: palette.ink, fontWeight: "600" }]}
        >
          {t("intake.q.complaint")}
        </AppText>
        {state !== "confirm" ? (
          <AppText role="body" style={[styles.rounded, { color: palette.inkSoft }]}>
            {t("dialogue.openInvite")}
          </AppText>
        ) : null}

        {state === "confirm" ? (
          <View style={styles.thread}>
            <View style={[styles.understood, { backgroundColor: palette.card }]}>
              <AppText role="label" style={[styles.rounded, { color: palette.inkSoft }]}>
                {t("dialogue.confirmIntro")}
              </AppText>
              <AppText
                role="question"
                style={[styles.rounded, { color: palette.ink, fontWeight: "600" }]}
              >
                {t("intake.opt.fatigue")}
              </AppText>
              <AppText role="label" style={[styles.rounded, { color: palette.inkSoft }]}>
                {t("dialogue.confirmAsk")}
              </AppText>
            </View>
            <View style={styles.grid}>
              {OPTIONS.map((key) => (
                <AnswerCard
                  key={key}
                  palette={palette}
                  label={t(key)}
                  selected={selected.includes(key)}
                  onPress={() =>
                    setSelected((now) =>
                      now.includes(key) ? now.filter((k) => k !== key) : [...now, key],
                    )
                  }
                />
              ))}
            </View>
          </View>
        ) : null}
      </ScrollView>

      <SafeAreaView edges={["bottom"]} style={styles.dock}>
        {motion.visible && ORB_SIZE[state] > 0 ? (
          <View style={styles.orbZone}>
            <VoiceOrb
              size={ORB_SIZE[state]}
              motion={motion}
              palette={palette}
              level={state === "listening" ? 0.45 : 0}
              glass={glass}
            />
            {caption !== undefined ? (
              <AppText role="title" style={[styles.rounded, styles.center, { color: palette.ink }]}>
                {t(caption)}
              </AppText>
            ) : null}
            {state === "listening" ? (
              <AppText
                role="label"
                style={[styles.rounded, styles.center, { color: palette.inkSoft }]}
              >
                {t("dialogue.listeningHint")}
              </AppText>
            ) : null}
          </View>
        ) : null}
        {state === "listening" ? (
          <StageButton
            surface={surface}
            prominent
            label={t("voiceFirst.stop")}
            onPress={() => {}}
          />
        ) : null}
        {state === "confirm" ? (
          <View style={styles.actions}>
            <StageButton
              surface={surface}
              prominent
              label={t("dialogue.confirm")}
              onPress={() => {}}
            />
          </View>
        ) : null}
        <GlassComposer
          surface={surface}
          value={draft}
          onChangeText={setDraft}
          prompt={t("dialogue.typeThisStep")}
          control={control}
          controlLabel={t(controlLabel)}
          onControl={() => setDraft("")}
          focused={state === "typed"}
        />
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  flex: { flex: 1 },
  rounded: { fontFamily: ROUNDED },
  center: { textAlign: "center" },
  content: { paddingHorizontal: 24, paddingTop: 28, paddingBottom: 24, gap: 12 },
  thread: { gap: 14, marginTop: 12 },
  understood: { borderRadius: 24, padding: 20, gap: 6 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 4 },
  dock: { paddingHorizontal: 16, gap: 12, paddingTop: 8 },
  orbZone: { alignItems: "center", gap: 6, paddingBottom: 8 },
  actions: { gap: 10 },
});
