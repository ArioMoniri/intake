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
 *
 * INT-464 (ADR-039 S7): the iOS setup layout in the stage's visual language.
 * A calm hero (the stage orb drawn still, the static large title and the
 * tagline) over the still stage backdrop; the phone sign-in and the
 * disclaimer in a tray at the bottom; the synthetic accounts as a grouped
 * inset list on the stage card. Nothing moves: the glass action is inert.
 */
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { useGlassMode } from "@/components/glassMode";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AmbientBackdrop } from "@/components/stage/AmbientBackdrop";
import { StageButton } from "@/components/stage/StageControls";
import { useStagePalette } from "@/components/stage/useStagePalette";
import { VoiceOrb } from "@/components/stage/VoiceOrb";
import { AppText, Screen, useTheme } from "@/components/Themed";
import { verticalSlop } from "@/lib/a11y/target";
import { availableLocales, t, type Locale } from "@/lib/i18n";
import { appLocaleChooser, chooseFromChooser } from "@/lib/locale/chooser";
import { useSession } from "@/lib/session";
import { stillOrb } from "@/lib/stage/orb";
import type { StagePalette } from "@/lib/stage/palette";
import { radius, spacing } from "@/lib/theme";
import type { TestAccount } from "@/lib/types/account";

/** The welcome mark's diameter: the dialogue's listening orb, at rest. */
const HERO_ORB = 112;

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
 * render an empty list if it ever rendered this, and it does not.
 *
 * INT-464: a grouped inset list on the stage card, one row per account with
 * the navigation chevron, the header outside the group and the note as its
 * footer, as iOS draws a settings group.
 */
function DevSignIn({ palette }: { palette: StagePalette }) {
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
  if (accounts.length === 0) {
    return null;
  }
  return (
    <View style={styles.devSection}>
      <Kicker label={t("welcome.devSignIn")} inset />
      <ListGroup surface={palette.card} footer={t("welcome.devNote")}>
        {accounts.map((account) => (
          <ListRow
            key={account.id}
            label={account.name}
            chevron
            onPress={() => {
              signIn(account);
              router.replace("/(tabs)/today");
            }}
          />
        ))}
      </ListGroup>
    </View>
  );
}

export default function Welcome() {
  const router = useRouter();
  const palette = useStagePalette();
  const glassMode = useGlassMode();
  return (
    <Screen style={[styles.flush, { backgroundColor: palette.base }]}>
      {/* ADR-039 S7: the stage's still backdrop, full-bleed. */}
      <AmbientBackdrop palette={palette} />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.hero}>
          <VoiceOrb
            size={HERO_ORB}
            motion={stillOrb()}
            palette={palette}
            glass={glassMode === "liquid"}
          />
          <AppText role="hero" heading style={[styles.centred, { color: palette.ink }]}>
            {t("app.name")}
          </AppText>
          <AppText role="body" style={[styles.centred, { color: palette.inkSoft }]}>
            {t("app.tagline")}
          </AppText>
        </View>
        <FirstRunLanguage />
        <AppText role="body" style={[styles.centred, { color: palette.ink }]}>
          {t("welcome.body")}
        </AppText>
        {__DEV__ ? <DevSignIn palette={palette} /> : null}
        {/* The tray: the one action and the disclaimer, at the bottom while
            the column fits, scrolled to once it does not. */}
        <View style={styles.tray}>
          <StageButton
            palette={palette}
            prominent
            interactive={false}
            label={t("welcome.phoneCta")}
            onPress={() => router.push("/(auth)/phone")}
          />
          <AppText role="caption" style={[styles.centred, { color: palette.inkSoft }]}>
            {t("app.disclaimer")}
          </AppText>
        </View>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  // The stage runs edge to edge; the column keeps the screen margin.
  flush: { padding: 0 },
  // `flexGrow` rather than `flex`: at the small steps the column is shorter
  // than the screen and the tray sits at the bottom; at the large ones it is
  // taller, flexGrow stops applying, and the same container scrolls.
  content: {
    flexGrow: 1,
    gap: spacing.lg,
    paddingHorizontal: spacing.screen,
    // Room above the mark for its glow, which the scroll view would
    // otherwise cut at its top edge, under the status bar.
    paddingTop: spacing.xl * 2,
    paddingBottom: spacing.md,
  },
  hero: { alignItems: "center", gap: spacing.md },
  centred: { textAlign: "center" },
  // Wraps so the endonym pills reflow at the enlarged text steps and hold
  // identically once the row flips under a right-to-left locale (INT-301).
  langRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  langPill: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
  },
  devSection: { gap: spacing.sm },
  // `marginTop: "auto"` takes the column's spare room, so the tray rests on
  // the bottom edge while the column fits.
  tray: { marginTop: "auto", gap: spacing.md, paddingTop: spacing.md },
});
