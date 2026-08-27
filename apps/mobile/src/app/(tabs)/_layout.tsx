/**
 * The five-tab shell (02 §4): today · visits · records · wellbeing · me.
 * Native tabs (SF Symbols on iOS, Material drawables on Android). The
 * wellbeing trigger is consent-gated — `visibleTabs` is the single source of
 * that rule; a hidden trigger removes the tab from the bar entirely rather
 * than disabling it (02 §4: absent until consent, never teasing).
 */
import { Redirect } from "expo-router";
import { NativeTabs } from "expo-router/unstable-native-tabs";

import { t } from "@/lib/i18n";
import { useSession, visibleTabs } from "@/lib/session";

export default function TabsLayout() {
  const { account } = useSession();
  if (account === null) {
    return <Redirect href="/(auth)/welcome" />;
  }
  const tabs = visibleTabs(account.consents);
  return (
    <NativeTabs>
      <NativeTabs.Trigger name="today">
        <NativeTabs.Trigger.Icon sf="sun.max" drawable="ic_today" />
        <NativeTabs.Trigger.Label>{t("tabs.today")}</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="visits">
        <NativeTabs.Trigger.Icon sf="calendar" drawable="ic_visits" />
        <NativeTabs.Trigger.Label>{t("tabs.visits")}</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="records">
        <NativeTabs.Trigger.Icon sf="folder" drawable="ic_records" />
        <NativeTabs.Trigger.Label>{t("tabs.records")}</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      {tabs.includes("wellbeing") ? (
        <NativeTabs.Trigger name="wellbeing">
          <NativeTabs.Trigger.Icon sf="heart" drawable="ic_wellbeing" />
          <NativeTabs.Trigger.Label>{t("tabs.wellbeing")}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
      ) : null}
      <NativeTabs.Trigger name="me">
        <NativeTabs.Trigger.Icon sf="person.crop.circle" drawable="ic_me" />
        <NativeTabs.Trigger.Label>{t("tabs.me")}</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
