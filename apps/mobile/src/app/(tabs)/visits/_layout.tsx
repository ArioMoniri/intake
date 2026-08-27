/**
 * The visits tab hosts its own stack (index → detail → intake/review).
 * Under native tabs the inner navigator must be explicit — without this
 * layout, pushes into the tab are silently dropped (found by the INT-193
 * simulator smoke run). Fades only (02 §5.2a).
 */
import { Stack } from "expo-router";

export default function VisitsLayout() {
  return <Stack screenOptions={{ headerShown: false, animation: "fade" }} />;
}
