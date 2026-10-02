/**
 * Welcome (02 §4 auth flow). The primary path is REAL sign-in — phone
 * verification (INT-131) at /(auth)/phone. Development builds additionally
 * offer the synthetic test accounts (INT-197 demo tier, load-bearing until
 * the OTP tier fully lands); that block is compiled out of release builds
 * via __DEV__ and renders as quiet pills so the one saturated CTA stays
 * the real sign-in (02 §5.2).
 *
 * INT-410 (audit F30): compiling the block out was not enough. The seed was
 * a static import, and Metro keeps a module that is imported statically even
 * when only dead code reads it, so every synthetic account shipped in the
 * release bundle. `DevSignIn` now loads the seed with an `import()` inside
 * `if (__DEV__)`. A release build folds that branch away before Metro collects
 * dependencies, so the seed module is not in the bundle at all.
 *
 * INT-284: the screen SCROLLS. It used to centre its column in a `flex: 1`
 * box, which is fine until the column outgrows the box — flexbox centring does
 * not clip, it pushes the overflow out of BOTH ends, past the safe-area inset
 * the Screen just applied. At the largest text step INT-260 can now reach, the
 * title rendered under the notch and the footer was cut off at the physical
 * bottom edge, and a 400 pt swipe moved nothing: the copy explaining what this
 * screen IS was unreachable. `flexGrow: 1` on the scroll content keeps the
 * centring while it fits and hands the patient the rest when it does not.
 */
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { Kicker } from "@/components/Kicker";
import {
  AppText,
  Card,
  PrimaryButton,
  Screen,
  SecondaryButton,
  useTheme,
} from "@/components/Themed";
import { verticalSlop } from "@/lib/a11y/target";
import { availableLocales, t, type Locale } from "@/lib/i18n";
import { appLocaleChooser, chooseFromChooser } from "@/lib/locale/chooser";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";
import type { TestAccount } from "@/lib/types/account";

/** An offered locale this app also carries a UI catalogue for. */
function isCatalogued(code: string): code is Locale {
  return (availableLocales as readonly string[]).includes(code);
}

/**
 * INT-301 — the language chooser at first run. Same registry, same
 * absent-when-one rule as the Me screen: with only `tr` registered it renders
 * nothing (a one-item chooser teaches the patient the feature does not work).
 * No red-flag script exists before a visit, so the switch's RED guard is
 * satisfied trivially here.
 */
function FirstRunLanguage() {
  const theme = useTheme();
  const { locale, switchLocale } = useSession();
  const choices = appLocaleChooser();
  if (choices.length === 0) {
    return null;
  }
  const pick = (code: string): void => {
    try {
      chooseFromChooser(code, { redScriptInFlight: false });
    } catch {
      return;
    }
    if (isCatalogued(code)) {
      switchLocale(code);
    }
  };
  return (
    <View style={styles.langRow}>
      {choices.map((choice) => {
        const active = locale === choice.code;
        return (
          <Pressable
            key={choice.code}
            accessibilityRole="button"
            accessibilityLabel={choice.endonym}
            accessibilityState={{ selected: active }}
            // ~30 pt visible pill; slop lifts the TARGET to the SC 2.5.8 floor.
            hitSlop={verticalSlop(30)}
            onPress={() => pick(choice.code)}
            style={[
              styles.langPill,
              { backgroundColor: active ? theme.primarySoft : theme.surfaceRaised },
            ]}
          >
            {/* Each language in its own name and script (acceptance 1). */}
            <AppText role="caption" color={active ? "primary" : "inkSoft"}>
              {choice.endonym}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

/**
 * The synthetic accounts, for a development build only. The `import()` sits
 * inside `if (__DEV__)`, so a release build never bundles the seed: it would
 * render an empty card if it ever rendered this, and it does not.
 */
function DevSignIn() {
  const router = useRouter();
  const { signIn } = useSession();
  const [accounts, setAccounts] = useState<readonly TestAccount[]>([]);
  useEffect(() => {
    let mounted = true;
    if (__DEV__) {
      void import("@/lib/dev/accounts").then((seed) => {
        if (mounted) {
          setAccounts(seed.testAccounts);
        }
      });
    }
    return () => {
      mounted = false;
    };
  }, []);
  return (
    <Card style={styles.devCard}>
      <Kicker label={t("welcome.devSignIn")} />
      {accounts.map((account) => (
        <SecondaryButton
          key={account.id}
          label={account.name}
          onPress={() => {
            signIn(account);
            router.replace("/(tabs)/today");
          }}
        />
      ))}
      <AppText role="caption" color="inkFaint">
        {t("welcome.devNote")}
      </AppText>
    </Card>
  );
}

export default function Welcome() {
  const router = useRouter();
  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.hero}>
          <AppText role="hero" heading>
            {t("app.name")}
          </AppText>
          <AppText role="body" color="inkSoft">
            {t("app.tagline")}
          </AppText>
        </View>
        <FirstRunLanguage />
        <AppText role="body">{t("welcome.body")}</AppText>
        <PrimaryButton label={t("welcome.phoneCta")} onPress={() => router.push("/(auth)/phone")} />
        {__DEV__ ? <DevSignIn /> : null}
        <AppText role="caption" color="inkFaint" style={styles.disclaimer}>
          {t("app.disclaimer")}
        </AppText>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  // `flexGrow` rather than `flex`: at the small steps the column is shorter
  // than the screen and centring is the design; at the large ones it is
  // taller, flexGrow stops applying, and the same container scrolls.
  content: { flexGrow: 1, justifyContent: "center", gap: spacing.lg },
  hero: { gap: spacing.sm },
  // Wraps so the endonym pills reflow at the enlarged text steps and hold
  // identically once the row flips under a right-to-left locale (INT-301).
  langRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  langPill: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
  },
  devCard: { gap: spacing.sm },
  disclaimer: { textAlign: "center" },
});
