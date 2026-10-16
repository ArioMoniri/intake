/**
 * INT-337: the device half of the dialogue's transients (MOTION-8). It holds
 * the arbiter's state for the dialogue and steps it in the render that
 * changes the scene, so a decision lands in the same commit as the element it
 * decides: content is never a frame late.
 *
 * The one thing the pure reducer cannot know is when a fade ended. A
 * Reanimated callback would need a hop back to the JS runtime, which
 * e2e/motion.spec.ts forbids, so the end is reported by a timer set to the
 * fade the policy granted (`fadeOf`). The timer frees the arbiter's slot and
 * nothing else: no turn, commit or navigation waits on it, and a report that
 * never comes only makes later content render instantly (transients.test.ts,
 * fake clock). It lives here, under src/lib, where e2e/a11y.spec.ts BK13
 * classifies it; the dialogue owns no timer.
 */
import { useEffect, useState } from "react";

import {
  fadeOf,
  initialDialogueMotion,
  releaseDialogueMotion,
  sameScene,
  stepDialogueMotion,
  type DialogueMotion,
  type DialogueScene,
} from "../transients";

export function useDialogueMotion(scene: DialogueScene, reduce: boolean): DialogueMotion {
  const [held, setHeld] = useState(() => initialDialogueMotion(scene));
  let current = held;
  if (!sameScene(held.scene, scene)) {
    // React's derived-state pattern: the step is pure, and the re-render it
    // asks for happens before anything is committed.
    current = stepDialogueMotion(held, scene, { reduce });
    setHeld(current);
  }

  const running = current.arbiter.running?.id ?? null;
  const fadeMs = running === null ? 0 : (fadeOf(current, running, { reduce })?.durationMs ?? 0);
  useEffect(() => {
    if (running === null) {
      return undefined;
    }
    const timer = setTimeout(
      () => setHeld((state) => releaseDialogueMotion(state, running)),
      fadeMs,
    );
    return () => clearTimeout(timer);
  }, [running, fadeMs]);

  return current;
}
