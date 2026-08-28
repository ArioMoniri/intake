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

import { FloatingTabBar } from "@/components/FloatingTabBar";
import { useTheme } from "@/components/Themed";
import { motion } from "@/lib/theme";
import { useSession, visibleTabs } from "@/lib/session";

export default function TabsLayout() {
  const theme = useTheme();
  const { account, consents } = useSession();
  if (account === null) {
    return <Redirect href="/(auth)/welcome" />;
  }
  const tabs = visibleTabs(consents);
  return (
    <Tabs
      tabBar={(props) => <FloatingTabBar {...props} />}
      screenOptions={{
        headerShown: false,
        lazy: true,
        // Motion budget (02 §5.2a): fades only, 120 ms.
        animation: "fade",
        transitionSpec: { animation: "timing", config: { duration: motion.fadeMs } },
        sceneStyle: { backgroundColor: theme.background },
      }}
    >
      <Tabs.Screen name="today" />
      <Tabs.Screen name="visits" />
      <Tabs.Screen name="records" />
      <Tabs.Protected guard={tabs.includes("wellbeing")}>
        <Tabs.Screen name="wellbeing" />
      </Tabs.Protected>
      <Tabs.Screen name="me/index" />
      <Tabs.Screen name="me/learned" />
    </Tabs>
  );
}
