/**
 * The five-tab shell (02 §4): today · visits · records · wellbeing · me.
 *
 * Design pass 4 (owner decision 2026-08-28): the JS tabs navigator with the
 * FloatingTabBar pill replaces NativeTabs — the owner's Oura mandate
 * supersedes 02 §4's native-tabs choice for the dev tier; revisit at iOS 26
 * Liquid Glass ubiquity (the NativeTabs path lives in git history at this
 * file, pre-pass-4).
 *
 * The wellbeing trigger is consent-gated — `visibleTabs` is the single
 * source of that rule; `Tabs.Protected` UNREGISTERS the route when consent
 * is off (02 §4: absent until consent, never teasing — and not merely
 * hidden: a guarded route rejects navigation entirely).
 */
import { Redirect } from "expo-router";
import { Tabs } from "expo-router/js-tabs";

import { BiometricGate } from "@/components/BiometricGate";
import { FloatingTabBar } from "@/components/FloatingTabBar";
import { useTheme } from "@/components/Themed";
import { useReducedMotion } from "@/lib/a11y/prefs";
import { routeClassOf, tabTransition } from "@/lib/motion/transitions";
import { usePushRegistration } from "@/lib/push/usePushRegistration";
import { useSession, visibleTabs } from "@/lib/session";

export default function TabsLayout() {
  const theme = useTheme();
  const { account, consents, kioskActive } = useSession();
  // INT-583: keep this device's new-sign-in registration fresh, silently and
  // only when notices are already allowed — never a prompt at launch. A
  // synthetic dev account holds no server session to register against.
  usePushRegistration(account?.kind === "otp" ? account.id : null, kioskActive);
  if (account === null) {
    return <Redirect href="/(auth)/welcome" />;
  }
  const tabs = visibleTabs(consents);
  return (
    // Biometric gate on app open (10 §2, INT-131): the signed-in shell
    // renders only after the device factor passes; capability-detected, so
    // devices without a factor pass through instead of dead-ending.
    <BiometricGate>
      <TabsShell tabs={tabs} themeBackground={theme.background} />
    </BiometricGate>
  );
}

function TabsShell({
  tabs,
  themeBackground,
}: {
  tabs: ReturnType<typeof visibleTabs>;
  themeBackground: string;
}) {
  const reduceMotion = useReducedMotion();
  return (
    <Tabs
      tabBar={(props) => <FloatingTabBar {...props} />}
      screenOptions={({ route }) => ({
        headerShown: false,
        lazy: true,
        // Motion budget (02 §5.2a): fades only, 120 ms — and nothing at all
        // when the OS asks for reduced motion (INT-144, SC 2.2.2). The two
        // consent screens render hash-bound legal text and never animate
        // (INT-330); the policy decides that by route.
        ...tabTransition(routeClassOf(`(tabs)/${route.name}`), { reduce: reduceMotion }),
        sceneStyle: { backgroundColor: themeBackground },
      })}
    >
      <Tabs.Screen name="today" />
      <Tabs.Screen name="visits" />
      <Tabs.Screen name="records" />
      <Tabs.Protected guard={tabs.includes("wellbeing")}>
        <Tabs.Screen name="wellbeing" />
      </Tabs.Protected>
      <Tabs.Screen name="me/index" />
      <Tabs.Screen name="me/appearance" />
      <Tabs.Screen name="me/data" />
      <Tabs.Screen name="me/learned" />
      <Tabs.Screen name="me/notifications" />
      <Tabs.Screen name="me/sessions" />
      <Tabs.Screen name="me/companion" />
      <Tabs.Screen name="me/consents/index" />
      <Tabs.Screen name="me/consents/[purpose]" />
    </Tabs>
  );
}
