/**
 * Root layout (INT-130): session provider + auth gate. Signed out → (auth)
 * welcome; signed in → the five-tab shell. Animations obey the motion budget
 * (02 §5.2a): fades only.
 *
 * The navigator is keyed by the active locale: `t()` reads a module-level
 * catalog, so a language switch must remount the tree — otherwise screens
 * that consume no session state keep their old-language strings (found by
 * the INT-193 smoke run).
 */
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { SessionProvider, useSession } from "@/lib/session";

function LocalizedStack() {
  const { locale } = useSession();
  return (
    <Stack key={locale} screenOptions={{ headerShown: false, animation: "fade" }}>
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(tabs)" />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <SessionProvider>
      <StatusBar style="auto" />
      <LocalizedStack />
    </SessionProvider>
  );
}
