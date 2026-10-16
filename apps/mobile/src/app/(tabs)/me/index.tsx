/**
 * Profilim (02 §4): identity, consents, language, and the "what it learned
 * about me" ledger entry point. Consents live on their own layered
 * İzinleriniz screen (INT-132) — this screen carries the permanent
 * one-tap-away entry row; only the device-local health toggle (INT-208)
 * stays inline, because it never leaves the phone and mirrors no server
 * purpose.
 *
 * Design pass 5: the Oura settings anatomy — group headers OUTSIDE the
 * groups, squarer ListGroups of 56 pt rows with hairlines between, "›" on
 * the one row that navigates, and sign-out as a quiet pill instead of the
 * screen's loudest element (the saturated accent belongs to forward
 * actions, never to leaving).
 *
 * INT-499 (ADR-039 amendment): settings on the still stage. The wash and the
 * stage palette sit under the groups, every group is a solid stage card
 * (22 pt), and signing out is an inert, untinted glass capsule, never the
 * accent. Nothing moves.
 */
import { useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { useTabBarClearance } from "@/components/FloatingTabBar";
import { HealthSection } from "@/components/HealthSection";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AmbientBackdrop } from "@/components/stage/AmbientBackdrop";
import { StageButton } from "@/components/stage/StageControls";
import { StageSurfaceProvider } from "@/components/stage/StageSurface";
import { useStageScreen } from "@/components/stage/useStageScreen";
import { AppText, RAIL_EDGES, Screen, useTheme } from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import { verticalSlop } from "@/lib/a11y/target";
import { availableLocales, t, type Locale } from "@/lib/i18n";
import { chooseFromChooser, present, toChoices } from "@/lib/locale/chooser";
import { offerableAppLocales } from "@/lib/i18n/locale";
import { accountBadgeKey } from "@/lib/profile/badge";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

/**
 * INT-296 / INT-301 — the chooser renders what the locale registry OFFERS,
 * never a hardcoded pair, and each language in its OWN name (its endonym from
 * the registry) rather than a catalogue label. INT-301 adds the honest state:
 * a chooser with one option teaches a patient the feature does not work, so
 * `present()` drops a would-be one-item chooser to nothing and the whole row
 * is absent. The registry holds exactly `tr` until HB-O5 names another and
 * HB-C19 signs its clinical text, so today this row does not render at all.
 */

/** An offered locale this app also carries a UI catalogue for — the narrowing
 * `switchLocale` needs, since its parameter is the catalogue's `Locale`. */
function isCatalogued(code: string): code is Locale {
  return (availableLocales as readonly string[]).includes(code);
}

/**
 * Tonal state pill (Oura tag register: filled, borderless; the label always
 * carries the state — colour never alone, 02 §8.2).
 */
function StatePill({
  label,
  context,
  active,
  activeColor,
  onPress,
  accessibilityRole = "button",
  checked,
  hint,
}: {
  label: string;
  /**
   * What the pill governs (INT-144). Its visible word is a state — "Açık",
   * "Türkçe" — which alone names nothing; the row supplies the subject to
   * the eye, and this supplies it to a screen reader.
   */
  context?: string;
  active: boolean;
  activeColor: "success" | "primary";
  onPress: () => void;
  accessibilityRole?: "button" | "switch";
  checked?: boolean;
  hint?: string;
}) {
  const theme = useTheme();
  const bg = active
    ? activeColor === "success"
      ? theme.successSoft
      : theme.primarySoft
    : theme.surfaceRaised;
  const fg = active ? (activeColor === "success" ? theme.success : theme.primary) : theme.inkSoft;
  return (
    <Pressable
      accessibilityRole={accessibilityRole}
      // Visible word first (SC 2.5.3), subject after.
      accessibilityLabel={withContext(label, context)}
      accessibilityHint={hint}
      accessibilityState={accessibilityRole === "switch" ? { checked } : { selected: active }}
      // 30 pt by design (Oura tag register). Slop lifts the TARGET to the
      // SC 2.5.8 floor without disturbing the 56 pt row it sits in; vertical
      // only, so the tr and en pills never swallow each other.
      hitSlop={verticalSlop(30)}
      onPress={onPress}
      style={[styles.statePill, { backgroundColor: bg }]}
    >
      <AppText role="caption" style={{ color: fg, fontWeight: "600" }}>
        {label}
      </AppText>
    </Pressable>
  );
}

export default function Me() {
  const router = useRouter();
  const { account, consents, setConsent, signOut, locale, switchLocale } = useSession();
  // Hoisted above the early return: hooks run in the same order every render.
  const tabBarClearance = useTabBarClearance();
  const { palette, chrome } = useStageScreen("settings");
  // INT-301 — the language chooser, reachable here without ending a visit in
  // progress. It reads the registry (INT-296) and is ABSENT below two real
  // choices; with only `tr` registered it renders nothing.
  const languageChoices = present(toChoices(offerableAppLocales()));
  const pickLanguage = (code: string): void => {
    try {
      // The sanctioned switch: refused while a red-flag script is in flight
      // (invariant 21), the same refusal barge-in uses. The Me tab hosts no
      // RED script, so the flag is false here; a RED-hosting surface passes
      // its live state to the same guard.
      chooseFromChooser(code, { redScriptInFlight: false });
    } catch {
      return;
    }
    if (isCatalogued(code)) {
      switchLocale(code);
    }
  };
  if (account === null || consents === null) {
    // The tabs layout has already redirected to welcome by the time this
    // renders without a session; render nothing during that frame.
    return null;
  }
  // INT-421: the synthetic label belongs to the dev fixture session alone; a
  // phone-verified account in a store build carries no sublabel at all.
  const badge = accountBadgeKey(account);
  return (
    <Screen edges={RAIL_EDGES} style={{ backgroundColor: palette.base }}>
      {chrome.backdrop ? <AmbientBackdrop palette={palette} /> : null}
      <StageSurfaceProvider palette={palette}>
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: tabBarClearance }]}>
          <AppText role="hero" heading style={[styles.heroLine, { color: palette.ink }]}>
            {t("me.title")}
          </AppText>
          <ListGroup>
            <ListRow
              icon="person.crop.circle"
              label={account.name}
              sublabel={badge === null ? undefined : t(badge)}
            />
          </ListGroup>
          {/* Görünüm (INT-260): text size, theme, motion and how a visit
            starts. Above İzinleriniz because a patient who cannot read the
            screen cannot reach anything below it either. */}
          <ListGroup>
            <ListRow
              icon="textformat.size"
              label={t("appearance.title")}
              chevron
              hint={t("a11y.appearance.entry")}
              onPress={() => router.push("/(tabs)/me/appearance")}
            />
          </ListGroup>
          {/* İzinleriniz (INT-132): the per-purpose record moved to its own
            layered screen — every 06 §2 purpose, versioned texts, one-tap
            withdrawal. This row is the permanent one-tap-away entry. */}
          <View style={styles.section}>
            <Kicker label={t("me.consents")} />
            <ListGroup>
              <ListRow
                icon="checkmark.shield"
                label={t("me.consents")}
                sublabel={t("consent.entry.sub")}
                chevron
                hint={t("a11y.openHint")}
                onPress={() => router.push("/(tabs)/me/consents")}
              />
            </ListGroup>
          </View>
          {/* Sağlık verileri (INT-208): device-local reads behind their own
            consent. The hint states the scope honestly — read on this phone
            only, nothing sent, nothing enters a note unless the patient adds
            it. Content renders only while the consent is ON; the hint is the
            group's quiet footer (Oura's under-group explanations). */}
          <View style={styles.section}>
            <Kicker label={t("me.health")} />
            <ListGroup footer={t("consent.health.hint")}>
              <ListRow
                label={t("consent.health")}
                trailing={
                  <StatePill
                    label={consents.health ? t("consent.on") : t("consent.off")}
                    context={t("consent.health")}
                    hint={t("a11y.consent.switchHint")}
                    active={consents.health}
                    activeColor="success"
                    accessibilityRole="switch"
                    checked={consents.health}
                    onPress={() => setConsent("health", !consents.health)}
                  />
                }
              />
            </ListGroup>
            {consents.health ? <HealthSection /> : null}
          </View>
          <ListGroup>
            {languageChoices.length > 0 ? (
              <ListRow
                label={t("me.language")}
                trailing={
                  <View style={styles.langGroup}>
                    {languageChoices.map((choice) => (
                      <StatePill
                        key={choice.code}
                        // Each language in its own name and script (acceptance 1).
                        label={choice.endonym}
                        context={t("me.language")}
                        active={locale === choice.code}
                        activeColor="primary"
                        onPress={() => pickLanguage(choice.code)}
                      />
                    ))}
                  </View>
                }
              />
            ) : null}
            {/* Bildirimler (INT-141): opt-out and quiet hours. Its own screen
              because the quiet-window choices do not fit a settings row —
              and because the honest explanation of what a reminder never
              says belongs beside the switch that governs it. */}
            <ListRow
              label={t("me.notifications")}
              sublabel={t("notifications.entry.sub")}
              chevron
              hint={t("a11y.openHint")}
              onPress={() => router.push("/(tabs)/me/notifications")}
            />
            {/* Yakınınız adına (INT-133): who is doing this sitting, and what
              that does to the note (06 §6, 13 §13). The under-18 door lives
              on that screen too, closed with its reason on it. */}
            <ListRow
              label={t("me.companion")}
              sublabel={t("companion.entry.sub")}
              chevron
              hint={t("a11y.openHint")}
              onPress={() => router.push("/(tabs)/me/companion")}
            />
            <ListRow
              label={t("me.learned")}
              chevron
              hint={t("a11y.openHint")}
              onPress={() => router.push("/(tabs)/me/learned")}
            />
            {/* Verileriniz (INT-140): the KVKK m.11 controls — a copy of the
              record, and its erasure. Last in the group and one tap away,
              which is where a right the patient rarely exercises belongs:
              always reachable, never the loudest thing on the screen. */}
            <ListRow
              label={t("me.data")}
              sublabel={t("data.entry.sub")}
              chevron
              hint={t("a11y.openHint")}
              onPress={() => router.push("/(tabs)/me/data")}
            />
          </ListGroup>
          {/* Leaving is never the accent: an untinted stage capsule, inert glass
            (ADR-039 S3, S7), solid wherever the policy says so. */}
          <StageButton
            palette={palette}
            interactive={false}
            solid={!chrome.glass}
            label={t("me.signOut")}
            onPress={signOut}
          />
        </ScrollView>
      </StageSurfaceProvider>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md },
  heroLine: { marginTop: spacing.xl, marginBottom: spacing.sm },
  section: { gap: spacing.sm, marginTop: spacing.sm },
  statePill: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
  },
  // INT-301: wraps so the endonym pills reflow at the enlarged text steps
  // (INT-295's class of defect) — and, because it wraps rather than pinning an
  // edge, it holds identically once the row flips under a right-to-left locale.
  langGroup: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
});
