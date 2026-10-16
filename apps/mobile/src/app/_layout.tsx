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
 * Face: the platform's own (SF Pro on iOS, the system sans on Android) since
 * INT-422, so there is nothing to load and the first frame is the real one.
 */
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useMemo, type ReactNode } from "react";
import { ReduceMotion, ReducedMotionConfig } from "react-native-reanimated";

import { KioskGate } from "@/components/KioskGate";
import { RedCoveredNavigator, RedLayer } from "@/components/RedLayer";
import { useScheme, useTheme } from "@/components/Themed";
import { useReducedMotion } from "@/lib/a11y/prefs";
import { navigationThemeFor } from "@/lib/navigationTheme";
import { appHaptics } from "@/lib/motion/appHaptics";
import { routeClassOf, transitionFor } from "@/lib/motion/transitions";
import { AppearanceProvider } from "@/lib/prefs/AppearanceProvider";
import { holdHapticsUnderRed } from "@/lib/red/hapticHold";
import { redStore } from "@/lib/red/store";
import { SessionProvider, useSession } from "@/lib/session";
import { clientTelemetry, installCrashHandler } from "@/lib/telemetry/expoTelemetry";

/** Evaluated when the root module loads — the earliest clock this app has. */
const APP_START_MS = Date.now();

/**
 * INT-331 (motion S-2): Reanimated follows the app's reduce-motion policy, the
 * OS setting OR the in-app switch and reduced until the OS answers, and
 * follows it live. Its own "follow the system" mode is read once at module
 * load and never sees the in-app switch, so it is never used. This sits
 * inside AppearanceProvider, or the switch could not reach it.
 */
function ReanimatedMotionPolicy() {
  const reduceMotion = useReducedMotion();
  return <ReducedMotionConfig mode={reduceMotion ? ReduceMotion.Always : ReduceMotion.Never} />;
}

/**
 * The navigators' theme and the status bar follow the app's resolved scheme
 * (the OS setting or the Görünüm override), never the library default.
 *
 * The native stack passes its theme's `dark` flag to every native header as
 * the bar's user-interface style. With React Navigation's default theme that
 * flag was always false, so on a dark screen each bar was forced light, and
 * on iOS 26 the back chevron took the light label colour: black on the black
 * page (INT-433's report, reproduced on INT451-16e). lib/navigationTheme.ts
 * builds the theme from the app's own tokens; the fonts stay the library's.
 */
function NavigationTheme({ children }: { children: ReactNode }) {
  const scheme = useScheme();
  const colors = useTheme();
  const value = useMemo(() => {
    const base = scheme === "dark" ? DarkTheme : DefaultTheme;
    return { ...base, ...navigationThemeFor(scheme, colors) };
  }, [scheme, colors]);
  return <ThemeProvider value={value}>{children}</ThemeProvider>;
}

/** The status bar's content follows the same scheme, gate or not. */
function SchemeStatusBar() {
  const scheme = useScheme();
  return <StatusBar style={scheme === "dark" ? "light" : "dark"} />;
}

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
  // INT-145: one launch is one session, and cold start ends at the first
  // frame the patient could actually read, which with the platform face is
  // the first one committed. Inert unless a GlitchTip DSN is configured
  // (app.json `extra.glitchtipDsn`, empty by default).
  useEffect(() => {
    installCrashHandler();
    clientTelemetry().noteColdStart(Date.now() - APP_START_MS);
  }, []);
  // INT-551: while a RED the patient sees stands no haptic is felt (ALERT,
  // CALM), and after a SILENT one none is felt again this session. The gate
  // decides; this tells it a RED is there (lib/red/hapticHold).
  useEffect(() => holdHapticsUnderRed(redStore, appHaptics), []);
  return (
    // INT-260: outermost, because the scheme, the text scale and the motion
    // policy are read by the navigators themselves — a provider inside the
    // session would leave the shell's own chrome on the OS values.
    <AppearanceProvider>
      <ReanimatedMotionPolicy />
      <SessionProvider>
        <SchemeStatusBar />
        {/* INT-143 — on a clinic-provisioned kiosk this gates entry/exit on
            the clinic PIN, wipes between patients and blocks on tamper; on a
            normal phone it is a pass-through. */}
        <RedCoveredNavigator>
          <KioskGate>
            <NavigationTheme>
              <LocalizedStack />
            </NavigationTheme>
          </KioskGate>
        </RedCoveredNavigator>
        {/* INT-446 — the RED root layer, a sibling AFTER the navigator
            container: ALERT and CALM paint above every screen with no
            navigation call (lib/motion/red.ts), and the rules-engine hop
            runs here for every visit's bound answers. */}
        <RedLayer />
      </SessionProvider>
    </AppearanceProvider>
  );
}
