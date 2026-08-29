/**
 * The auth stack. Fades only (02 §5.2a) — and no fade at all when the OS
 * says to reduce motion (INT-144, SC 2.2.2).
 */
import { Stack } from "expo-router";

import { screenAnimation } from "@/lib/a11y/motion";
import { useReducedMotion } from "@/lib/a11y/prefs";

export default function AuthLayout() {
  const reduceMotion = useReducedMotion();
  return (
    <Stack
      screenOptions={{ headerShown: false, animation: screenAnimation(reduceMotion) }}
    />
  );
}
