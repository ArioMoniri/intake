/**
 * Root layout (INT-130): session provider + auth gate. Signed out → (auth)
 * welcome; signed in → the five-tab shell. Animations obey the motion budget
 * (02 §5.2a): fades only, 120 ms, from the policy in lib/motion/transitions.
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
import { useEffect } from "react";

import { KioskGate } from "@/components/KioskGate";
import { useReducedMotion } from "@/lib/a11y/prefs";
import { routeClassOf, transitionFor } from "@/lib/motion/transitions";
import { AppearanceProvider } from "@/lib/prefs/AppearanceProvider";
import { SessionProvider, useSession } from "@/lib/session";
import { clientTelemetry, installCrashHandler } from "@/lib/telemetry/expoTelemetry";

/** Evaluated when the root module loads — the earliest clock this app has. */
const APP_START_MS = Date.now();

function LocalizedStack() {
  const { locale } = useSession();
  const reduceMotion = useReducedMotion();
  return (
    // INT-330: the transition, its 120 ms duration included, comes from the
    // motion policy by route — never the iOS 500 ms default (motion S-1).
    <Stack
      key={locale}
      screenOptions={({ route }) => ({
        headerShown: false,
        ...transitionFor(routeClassOf(route.name), { reduce: reduceMotion }),
      })}
    >
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
  // INT-145: one launch is one session, and cold start ends at the first
  // frame the patient could actually read — after the faces resolve, since
  // until then this component returns null. Inert unless a GlitchTip DSN is
  // configured (app.json `extra.glitchtipDsn`, empty by default).
  useEffect(() => {
    if (!fontsLoaded) {
      return;
    }
    installCrashHandler();
    clientTelemetry().noteColdStart(Date.now() - APP_START_MS);
  }, [fontsLoaded]);
  if (!fontsLoaded) {
    return null;
  }
  return (
    // INT-260: outermost, because the scheme, the text scale and the motion
    // policy are read by the navigators themselves — a provider inside the
    // session would leave the shell's own chrome on the OS values.
    <AppearanceProvider>
      <SessionProvider>
        <StatusBar style="auto" />
        {/* INT-143 — on a clinic-provisioned kiosk this gates entry/exit on
            the clinic PIN, wipes between patients and blocks on tamper; on a
            normal phone it is a pass-through. */}
        <KioskGate>
          <LocalizedStack />
        </KioskGate>
      </SessionProvider>
    </AppearanceProvider>
  );
}
