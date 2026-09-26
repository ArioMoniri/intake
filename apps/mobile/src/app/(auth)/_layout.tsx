/**
 * The auth stack. Fades only (02 §5.2a), for 120 ms rather than the iOS
 * 500 ms default — and no fade at all when the OS says to reduce motion
 * (INT-144, SC 2.2.2). The consent first-run renders hash-bound legal text,
 * so it never animates at any setting (INT-330); the policy decides that by
 * route, in lib/motion/transitions.
 */
import { Stack } from "expo-router";

import { useReducedMotion } from "@/lib/a11y/prefs";
import { routeClassOf, transitionFor } from "@/lib/motion/transitions";

export default function AuthLayout() {
  const reduceMotion = useReducedMotion();
  return (
    <Stack
      screenOptions={({ route }) => ({
        headerShown: false,
        ...transitionFor(routeClassOf(`(auth)/${route.name}`), { reduce: reduceMotion }),
      })}
    />
  );
}
