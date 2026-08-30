/**
 * The visits tab hosts its own stack (index → detail → intake/review).
 * Under native tabs the inner navigator must be explicit — without this
 * layout, pushes into the tab are silently dropped (found by the INT-193
 * simulator smoke run). Fades only (02 §5.2a), and none at all under the
 * OS reduce-motion setting (INT-144, SC 2.2.2).
 */
import { Stack } from "expo-router";

import { screenAnimation } from "@/lib/a11y/motion";
import { useReducedMotion } from "@/lib/a11y/prefs";

export default function VisitsLayout() {
  const reduceMotion = useReducedMotion();
  return <Stack screenOptions={{ headerShown: false, animation: screenAnimation(reduceMotion) }} />;
}
