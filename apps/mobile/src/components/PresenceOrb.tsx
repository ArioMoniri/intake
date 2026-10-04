/**
 * The presence orb (INT-336, MOTION-7;
 * docs/design/motion/motion-verification.md §1.1 O1–O8 as revised, §4
 * MOTION-7; intake-voice-motion-spec.md §4). One faceless disc on the
 * dialogue's glass bar that says, without words, whose turn it is: the
 * patient's (listening, its halo following their voice), the agent's
 * (speaking), the agent preparing (thinking), a lost connection (retry), or
 * nothing happening (idle). It replaces the dialogue's pulsing dot and its
 * three spinners, which now read as still text.
 *
 * - It draws; it decides nothing. The caller passes the state from
 *   `orbStateFor`; the visual, the transition and the sampler plan come from
 *   lib/motion/orb.ts. Every duration is a token or a policy result.
 * - Opacity only (ADR-033 Q5 is open): the core, the halo, the retry core and
 *   the work ring change opacity, and nothing scales.
 * - It runs on the UI thread: the loops and the level live in shared values,
 *   so a stalled JS thread does not stop it and a level sample renders no
 *   React tree.
 * - A loop is held, never reset: a state change freezes the running value and
 *   the next state's rest is reached from there.
 * - Decoration: hidden from the accessibility tree and not pressable. The
 *   dialogue's text and its one live announcement carry every state.
 * - Under reduce-motion it is still: no loop, no level, no transition.
 *
 * ADR-039 S1 (INT-466): on the chat stage the caller passes `stage`, and the
 * orb draws the stage body (components/stage/VoiceOrb), a gradient sphere
 * whose breathing and turning come from the S1 policy the caller computed
 * from this same state. The voice level scales that body through
 * `levelScale`, a worklet on the sampler's shared value, so a sample still
 * renders nothing. The work ring keeps its fade. Nothing else changes: the
 * state is still `orbStateFor`'s, the orb is still decoration, and it still
 * reports nothing back.
 *
 * INT-491: the stage also names the body's variant (lib/stage/orbVariants),
 * which the build's flag chose. The orb only hands it on: the variant draws
 * from the same S1 motion and the same level scale, so every bound and every
 * still state above holds for it too. Off, it is the sphere.
 */
import { useEffect, useRef } from "react";
import { StyleSheet, View } from "react-native";
import Animated, {
  Easing,
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from "react-native-reanimated";

import { VoiceOrb } from "@/components/stage/VoiceOrb";
import { useFontScale, useTheme } from "@/components/Themed";
import { loopingDecorationEnabled } from "@/lib/a11y/motion";
import { useReducedMotion } from "@/lib/a11y/prefs";
import { useLevelSampler, type LevelReader } from "@/lib/motion/native/useLevelSampler";
import {
  levelSamplerPlan,
  orbTransition,
  orbVisual,
  workRing,
  type OrbLoopKind,
  type OrbState,
} from "@/lib/motion/orb";
import { levelScale, type StageOrbMotion } from "@/lib/stage/orb";
import type { OrbVariant } from "@/lib/stage/orbVariants";
import type { StagePalette } from "@/lib/stage/palette";
import { motion, radius, scaledControl } from "@/lib/theme";

/** Half of a loop's full period: each half is one fade (SC 2.3.1: over 167 ms). */
function halfPeriod(kind: OrbLoopKind): number {
  switch (kind) {
    case "breathe":
      return motion.loop.breathePeriodMs / 2;
    case "speak":
      return motion.loop.speakPeriodMs / 2;
    case "shimmer":
      return motion.loop.shimmerPeriodMs / 2;
  }
}

interface PresenceOrbProps {
  /** From `orbStateFor`, and from nowhere else. */
  state: OrbState;
  /** The work indicator is shown (the arbiter's work chip, INT-337). */
  working: boolean;
  /** The arbiter granted the work indicator its fade; otherwise it switches instantly. */
  workFades: boolean;
  /** The recorder's metering, read by the level sampler while listening. */
  readLevel: LevelReader;
  /** The chat stage's body (ADR-039 S1); absent, the orb draws its disc. */
  stage?: {
    readonly size: number;
    readonly motion: StageOrbMotion;
    readonly palette: StagePalette;
    readonly glass: boolean;
    /** The body the build's flag chose (INT-491); `classic` is the sphere. */
    readonly variant: OrbVariant;
  };
}

export function PresenceOrb({ state, working, workFades, readLevel, stage }: PresenceOrbProps) {
  const theme = useTheme();
  const fontScale = useFontScale();
  const reduce = useReducedMotion();
  const still = !loopingDecorationEnabled(reduce);
  const visual = orbVisual(state, { reduce: still });

  const core = useSharedValue(0);
  const halo = useSharedValue(0);
  const retry = useSharedValue(0);
  const ring = useSharedValue(0);
  const level = useSharedValue(0);

  useLevelSampler(levelSamplerPlan(state, { reduce: still }), readLevel, level);

  // The orb arrives from nothing: its first transition is the mount fade.
  const previous = useRef<OrbState>("hidden");
  useEffect(() => {
    const timing = orbTransition(previous.current, state, { reduce: still });
    previous.current = state;
    const target = orbVisual(state, { reduce: still });
    const settle = { duration: timing.durationMs, easing: Easing.bezier(...timing.easing) };
    retry.set(withTiming(target.retryCoreOpacity, settle));
    const loop = target.loop;
    const looping = loop === null ? null : loop.layer === "core" ? core : halo;
    if (looping !== core) {
      core.set(withTiming(target.coreOpacity, settle));
    }
    if (looping !== halo) {
      halo.set(withTiming(target.haloOpacity, settle));
    }
    if (loop !== null && looping !== null) {
      const breath = { duration: halfPeriod(loop.kind), easing: Easing.bezier(...loop.easing) };
      looping.set(
        withSequence(
          withTiming(loop.from, settle),
          withRepeat(withTiming(loop.to, breath), -1, true),
        ),
      );
    }
    // Hold, never rest: the next state starts from wherever this one stopped.
    return () => {
      cancelAnimation(core);
      cancelAnimation(halo);
      cancelAnimation(retry);
    };
  }, [state, still, core, halo, retry]);

  useEffect(() => {
    const on = workRing(working, { reduce: still || !workFades });
    ring.set(
      withTiming(on.opacity, {
        duration: on.durationMs,
        easing: Easing.bezier(...motion.easing.out),
      }),
    );
  }, [working, workFades, still, ring]);

  const reactive = visual.levelReactive;
  const coreStyle = useAnimatedStyle(() => ({ opacity: core.get() }));
  const haloStyle = useAnimatedStyle(() => ({ opacity: halo.get() }));
  const retryStyle = useAnimatedStyle(() => ({ opacity: retry.get() }));
  const ringStyle = useAnimatedStyle(() => ({ opacity: ring.get() }));
  const levelStyle = useAnimatedStyle(
    () => ({ opacity: reactive ? level.get() * motion.orb.haloOpacity : 0 }),
    [reactive],
  );
  const gain = stage?.motion.levelGain ?? 0;
  const stageLevelStyle = useAnimatedStyle(
    () => ({ transform: [{ scale: levelScale(level.get(), gain) }] }),
    [gain],
  );

  if (!visual.mounted) {
    return null;
  }
  if (stage !== undefined) {
    return (
      <View
        // Decoration, as the disc is: the stage writes and announces the state.
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        pointerEvents="none"
        style={styles.box}
      >
        <Animated.View style={stageLevelStyle}>
          <VoiceOrb
            size={stage.size}
            motion={stage.motion}
            palette={stage.palette}
            glass={stage.glass}
            variant={stage.variant}
          />
        </Animated.View>
        <Animated.View
          style={[
            styles.layer,
            { width: stage.size, height: stage.size, borderRadius: radius.chip },
            { borderColor: stage.palette.inkSoft },
            styles.ring,
            ringStyle,
          ]}
        />
      </View>
    );
  }
  const box = scaledControl(motion.orb.boxPt, fontScale);
  const disc = scaledControl(motion.orb.sizePt, fontScale);
  const round = { borderRadius: radius.chip };
  return (
    <View
      // Decoration: every state it shows is also said in text, and the turn
      // state is announced once by the dialogue. Nothing here is a control.
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      pointerEvents="none"
      style={[styles.box, { width: box, height: box }]}
    >
      <Animated.View
        style={[
          styles.layer,
          round,
          { width: box, height: box },
          { backgroundColor: theme.primarySoft },
          haloStyle,
        ]}
      />
      <Animated.View
        style={[
          styles.layer,
          round,
          { width: box, height: box },
          { backgroundColor: theme.primarySoft },
          levelStyle,
        ]}
      />
      <Animated.View
        style={[
          styles.layer,
          round,
          { width: box, height: box, borderColor: theme.inkFaint },
          styles.ring,
          ringStyle,
        ]}
      />
      <Animated.View
        style={[
          styles.layer,
          round,
          { width: disc, height: disc },
          { backgroundColor: theme.primary },
          coreStyle,
        ]}
      />
      <Animated.View
        style={[
          styles.layer,
          round,
          { width: disc, height: disc },
          { backgroundColor: theme.inkFaint },
          retryStyle,
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  box: { alignItems: "center", justifyContent: "center" },
  layer: { position: "absolute" },
  ring: { borderWidth: StyleSheet.hairlineWidth },
});
