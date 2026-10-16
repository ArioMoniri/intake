/**
 * INT-336: the device half of the orb's level (MOTION-7;
 * docs/design/motion/motion-verification.md §1.1 O2(b)(c)). It samples one
 * loudness scalar the recorder already computes and writes it to a
 * UI-thread shared value, so the orb's halo follows the patient's voice
 * with zero React renders per sample.
 *
 * - The rate and the run/stop decision are the policy's (`levelSamplerPlan`
 *   in ../orb.ts): 10 Hz or less, while listening only, never under
 *   reduce-motion, stopped on every exit from listening.
 * - The number is the policy's too: normalised, smoothed, stepped, and
 *   written only when the step changed.
 * - It reads a scalar and keeps nothing: no buffer, no log, no send
 *   (invariants 3 and 6), and it never feeds affect (invariant 11).
 *
 * This is the one timer the orb needs, and it lives under src/lib, where
 * e2e/a11y.spec.ts BK13 classifies it (a meter; it limits nothing). A
 * component never owns it.
 */
import { useEffect, useRef } from "react";
import { Easing, withTiming, type SharedValue } from "react-native-reanimated";

import { motion } from "../../theme";
import { normalizeLevel, quantizeLevel, smoothLevel, type LevelSamplerPlan } from "../orb";

/** A metering reading in dBFS, or undefined when the recorder has none. */
export type LevelReader = () => number | undefined;

export function useLevelSampler(
  plan: LevelSamplerPlan,
  read: LevelReader,
  level: SharedValue<number>,
): void {
  // The latest reader, without restarting the sampler when it changes.
  const readRef = useRef(read);
  useEffect(() => {
    readRef.current = read;
  }, [read]);

  const { run } = plan;
  const intervalMs = plan.intervalMs;
  useEffect(() => {
    if (!run) {
      level.set(0);
      return undefined;
    }
    const follow = { duration: intervalMs, easing: Easing.bezier(...motion.easing.linear) };
    let smoothed = 0;
    let written = 0;
    const timer = setInterval(() => {
      let reading: number | undefined;
      try {
        reading = readRef.current();
      } catch {
        // The recorder closed between samples: silence, not an error.
        reading = undefined;
      }
      smoothed = smoothLevel(smoothed, normalizeLevel(reading));
      const next = quantizeLevel(written, smoothed);
      if (next.changed) {
        written = next.value;
        level.set(withTiming(next.value, follow));
      }
    }, intervalMs);
    return () => clearInterval(timer);
  }, [run, intervalMs, level]);
}
