/**
 * Yakınınız adına (INT-133; 02 §4 me/companions, 06 §6, 13 §13).
 *
 * Four blocks, in the order the decision is actually made:
 *
 * 1. WHO is doing this sitting — kendim / yakınım adına;
 * 2. once it is a companion, WHO is answering — the patient's own words on
 *    someone else's phone is `assisted_self_report`, a third value that
 *    exists because the other two both misdescribe it (02 §3);
 * 3. the ACKNOWLEDGEMENT, which gates the companion roles and says plainly
 *    what it is not: acknowledging the role is not a claim to decide for
 *    anyone (the proof-of-representation standard is with counsel);
 * 4. WHAT CHANGES — the proxy flag on the note, sensitive sections going to
 *    text, safeguarding not being asked (13 §13). Stated before the session,
 *    never discovered during it.
 *
 * The under-18 block is deliberately a closed door with the reason on it. A
 * minor's intake runs through a guardian account holding the consent (06 §6;
 * TMK velâyet, HHY-24), and that needs a persisted guardian↔minor link whose
 * lawful basis and proof standard are both open with Turkish counsel
 * (HB-L20). So the flow is not offered, and the copy says "not yet" instead
 * of opening a form that ends in a refusal. The screen never names the band,
 * the policy rows or the blocker ids: this phone may be in a waiting room.
 */
import { ScrollView, StyleSheet, View } from "react-native";

import { useTabBarClearance } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, Card, RAIL_EDGES, Screen } from "@/components/Themed";
import { t } from "@/lib/i18n";
import {
  setCompanionDeclaration,
  useCompanionDeclaration,
  useCompanionOutcome,
} from "@/lib/profile/store";
import { spacing } from "@/lib/theme";

export default function Companion() {
  const declaration = useCompanionDeclaration();
  const outcome = useCompanionOutcome();
  const isCompanion = declaration.role === "companion";

  const effects: string[] = [];
  if (outcome.proxyReported) {
    effects.push(t("companion.effect.proxy"));
  }
  if (outcome.attribution === "assisted_self_report") {
    effects.push(t("companion.effect.assisted"));
  }
  if (outcome.sensitiveTextOnly) {
    effects.push(t("companion.effect.textOnly"));
  }
  if (!outcome.safeguardingAsked) {
    effects.push(t("companion.effect.noSafeguarding"));
  }

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: useTabBarClearance() }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("companion.title")}
        </AppText>
        <GuidanceBlock
          accent
          icon="person.2"
          kickerKey="companion.guide.kicker"
          titleKey="companion.guide.title"
          bodyKey="companion.guide.body"
        />

        <View style={styles.section}>
          <Kicker label={t("companion.role.kicker")} />
          <ListGroup>
            <ListRow
              label={t("companion.role.self")}
              trailing={<Selected on={!isCompanion} />}
              hint={t("a11y.companion.roleHint")}
              onPress={() => setCompanionDeclaration({ role: "self" })}
            />
            <ListRow
              label={t("companion.role.companion")}
              trailing={<Selected on={isCompanion} />}
              hint={t("a11y.companion.roleHint")}
              onPress={() => setCompanionDeclaration({ role: "companion" })}
            />
          </ListGroup>
        </View>

        {isCompanion ? (
          <View style={styles.section}>
            <Kicker label={t("companion.speaker.kicker")} />
            <ListGroup footer={t("companion.speaker.footer")}>
              <ListRow
                label={t("companion.speaker.companion")}
                trailing={<Selected on={declaration.speaker === "companion"} />}
                hint={t("a11y.companion.speakerHint")}
                onPress={() => setCompanionDeclaration({ speaker: "companion" })}
              />
              <ListRow
                label={t("companion.speaker.patient")}
                trailing={<Selected on={declaration.speaker === "patient"} />}
                hint={t("a11y.companion.speakerHint")}
                onPress={() => setCompanionDeclaration({ speaker: "patient" })}
              />
            </ListGroup>
          </View>
        ) : (
          <View style={styles.section}>
            <Kicker label={t("companion.thirdParty.kicker")} />
            <ListGroup footer={t("companion.thirdParty.footer")}>
              <ListRow
                label={t("companion.thirdParty.label")}
                trailing={<Selected on={declaration.thirdPartyPresent} />}
                hint={t("a11y.companion.thirdPartyHint")}
                onPress={() =>
                  setCompanionDeclaration({
                    thirdPartyPresent: !declaration.thirdPartyPresent,
                  })
                }
              />
            </ListGroup>
          </View>
        )}

        {isCompanion ? (
          <View style={styles.section}>
            <Kicker label={t("companion.ack.kicker")} />
            <ListGroup footer={t("companion.ack.notProof")}>
              <ListRow
                label={t("companion.ack.label")}
                sublabel={outcome.ready ? undefined : t("companion.refusal.ack")}
                trailing={<Selected on={declaration.acknowledged} />}
                hint={t("a11y.companion.ackHint")}
                onPress={() => setCompanionDeclaration({ acknowledged: !declaration.acknowledged })}
              />
            </ListGroup>
          </View>
        ) : null}

        <View style={styles.section}>
          <Kicker label={t("companion.effect.kicker")} />
          <Card>
            {effects.length === 0 ? (
              <AppText role="body" color="inkSoft">
                {t("companion.effect.none")}
              </AppText>
            ) : (
              effects.map((line) => (
                <AppText key={line} role="body" color="inkSoft">
                  {line}
                </AppText>
              ))
            )}
          </Card>
        </View>

        {/* 06 §6 — the under-18 door, with the reason on it. */}
        <View style={styles.section}>
          <Kicker label={t("companion.guardian.kicker")} />
          <ListGroup footer={t("companion.guardian.body")}>
            <ListRow
              label={t("companion.guardian.label")}
              sublabel={t("companion.guardian.unavailable")}
            />
          </ListGroup>
        </View>

        {/* 06 §6 — the adolescent-private section, stated to the guardian
            before they ask, so the withholding is not a surprise. */}
        <View style={styles.section}>
          <Kicker label={t("companion.private.kicker")} />
          <Card>
            <AppText role="body" color="inkSoft">
              {t("companion.private.body")}
            </AppText>
          </Card>
        </View>
      </ScrollView>
    </Screen>
  );
}

/** The chosen-row marker. The word carries the state, never the colour
 * alone (02 §8.2), and it is spoken because the row's own label does not
 * say whether it is the active choice. */
function Selected({ on }: { on: boolean }) {
  return (
    <AppText role="caption" color={on ? "ink" : "inkFaint"}>
      {on ? t("companion.selected") : t("companion.notSelected")}
    </AppText>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md },
  heroLine: { marginTop: spacing.xl, marginBottom: spacing.sm },
  section: { gap: spacing.sm, marginTop: spacing.sm },
});
