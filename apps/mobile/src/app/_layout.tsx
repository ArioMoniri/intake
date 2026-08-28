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
 * Faces: Newsreader (OFL) — the Oura-register soft serif for hero and title
 * lines; Inter (OFL) carries body/label/caption since design pass 4 (Oura's
 * UI sans is Inter-class). The splash stays up until both are loaded so no
 * line ever flashes a fallback.
 */
import { Inter_400Regular, Inter_500Medium, Inter_600SemiBold } from "@expo-google-fonts/inter";
import {
  Newsreader_400Regular,
  Newsreader_500Medium,
  Newsreader_500Medium_Italic,
  useFonts,
} from "@expo-google-fonts/newsreader";
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
  const [fontsLoaded] = useFonts({
    Newsreader_400Regular,
    Newsreader_500Medium,
    Newsreader_500Medium_Italic,
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
  });
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
