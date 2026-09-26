/**
 * The visits tab hosts its own stack (index → detail → intake/review).
 * Under native tabs the inner navigator must be explicit — without this
 * layout, pushes into the tab are silently dropped (found by the INT-193
 * simulator smoke run). Fades only (02 §5.2a), for 120 ms rather than the
 * iOS 500 ms default, and none at all under the OS reduce-motion setting
 * (INT-144, SC 2.2.2). The intake cannot be swiped away — its header back
 * control is the exit (INT-330); the policy decides that by route, in
 * lib/motion/transitions.
 */
import { Stack } from "expo-router";

import { useReducedMotion } from "@/lib/a11y/prefs";
import { routeClassOf, transitionFor } from "@/lib/motion/transitions";

export default function VisitsLayout() {
  const reduceMotion = useReducedMotion();
  return (
    <Stack
      screenOptions={({ route }) => ({
        headerShown: false,
        ...transitionFor(routeClassOf(`(tabs)/visits/${route.name}`), { reduce: reduceMotion }),
      })}
    />
  );
}
