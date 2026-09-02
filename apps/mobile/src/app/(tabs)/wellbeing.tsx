/**
 * İyilik hâli (02 §4): exists in the rail only after the wellbeing consent
 * is ON (gate lives in the tabs layout via `visibleTabs`). Content here is
 * the WHO-5-family surface — BLOCKED on licence (HB-L2), so the shell only
 * frames the space without any screening items. Design pass 3: the frame is
 * a stack of Oura-style guidance blocks about the PRODUCT (how the space
 * will work, the privacy promise, share control) — no health advice, no
 * instrument content. Design pass 6: sections separate on whitespace alone
 * (Oura's explainer prose carries no hairlines — Mobbin b67baac0) and the
 * screen's block wears the primer-badge mark.
 */
import { ScrollView, StyleSheet } from "react-native";

import { useTabBarClearance } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { AppText, RAIL_EDGES, Screen } from "@/components/Themed";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import { t } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

export default function Wellbeing() {
  useClinicalScreenPrivacy(); // clinical screen: FLAG_SECURE-class (INT-131)
  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: useTabBarClearance() }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("wellbeing.title")}
        </AppText>
        <AppText role="body" color="inkSoft">
          {t("wellbeing.intro")}
        </AppText>
        <GuidanceBlock
          accent
          icon="heart"
          kickerKey="wellbeing.guide.how.kicker"
          titleKey="wellbeing.guide.how.title"
          bodyKey="wellbeing.guide.how.body"
        />
        <GuidanceBlock
          kickerKey="wellbeing.guide.privacy.kicker"
          titleKey="wellbeing.guide.privacy.title"
          bodyKey="wellbeing.guide.privacy.body"
        />
        <GuidanceBlock
          kickerKey="wellbeing.guide.share.kicker"
          titleKey="wellbeing.guide.share.title"
          bodyKey="wellbeing.guide.share.body"
        />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.xl },
  heroLine: { marginTop: spacing.xl },
});
