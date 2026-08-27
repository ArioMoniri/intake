/**
 * Root layout (INT-130): session provider + auth gate. Signed out → (auth)
 * welcome; signed in → the five-tab shell. Animations obey the motion budget
 * (02 §5.2a): fades only.
 *
 * The navigator is keyed by the active locale: `t()` reads a module-level
 * catalog, so a language switch must remount the tree — otherwise screens
 * that consume no session state keep their old-language strings (found by
 * the INT-193 smoke run).
 *
 * Display face: Fraunces (OFL) — the Oura-register soft serif for hero and
 * title lines only; body stays system sans. The splash stays up until the
 * face is loaded so headings never flash a fallback.
 */
import { Fraunces_400Regular, Fraunces_600SemiBold, useFonts } from "@expo-google-fonts/fraunces";
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
  const [fontsLoaded] = useFonts({ Fraunces_400Regular, Fraunces_600SemiBold });
  if (!fontsLoaded) {
    return null;
  }
  return (
    <SessionProvider>
      <StatusBar style="auto" />
      <LocalizedStack />
    </SessionProvider>
  );
}
