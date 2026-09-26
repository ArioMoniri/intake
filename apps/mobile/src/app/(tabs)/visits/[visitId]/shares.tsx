/**
 * Paylaşımlarınız (02 §4: the visit detail carries the share centre; 02 §312:
 * *"expiry; revoke any time; audit log visible to patient"*).
 *
 * Three grants over one note, who opened it, and the control that stops one.
 * Everything on the screen is the pass-5 settings anatomy — group headers
 * outside the groups, 56 pt rows with hairlines between, quiet trailing
 * values, the honest explanation as the group's footer. No new primitive, no
 * new colour, no new type role.
 *
 * What the screen is careful about, in the order it matters:
 *
 * **The revoke control never depends on a consent.** INT-150 §6 declares
 * revoke and the access log under the `core` purpose ALONE, precisely so that
 * withdrawing consent to share cannot lock the patient out of stopping the
 * sharing they already started. The client half is `revokeOffered`, which
 * takes a grant and nothing else — there is no consent value in scope here to
 * gate it on. `e2e/shares.spec.ts` fails if one appears here, and its §7 checks the
 * same rule against the router's own `require_scopes` decorators, so the three
 * routes this app calls cannot quietly acquire the share purpose either.
 *
 * **Stopping a share is two taps, and the first only changes the word.** The
 * INT-140 idiom, reused rather than reinvented: no modal and no `Alert`, whose
 * text could not live in the catalogue (invariant 5) and whose buttons could
 * not carry a hint. Arming a second grant disarms the first, so a
 * half-finished revocation never waits.
 *
 * **Nothing is shown as stopped until the record says so.** There is no
 * optimistic write anywhere in this seam. A patient who is told their share
 * is stopped stops checking, and a revocation that never left the phone would
 * produce exactly that silence.
 *
 * **The log shows a role, never a person.** files/10 §3 and INT-150 §8: the
 * projection carries `AccessorRole` by construction, the client drops the two
 * id-shaped fields on the row, and the group's footer says so out loud so the
 * patient is not left wondering whether a name was withheld or never existed.
 *
 * **No numeral except a date, and no duration at all.** The view budget is
 * spoken as a state ("Görüntüleme hakkı bitti") rather than printed as a
 * counter (the INT-140 rule), and how quickly a revocation takes effect is a
 * measurement in docs/evidence/INT-139.md — never a promise in patient copy
 * (invariant 20). What the copy does promise is the mechanism: a stopped
 * share does not work at the next attempt to open it.
 *
 * No biometric re-gate: the tabs shell already carries one, and this screen
 * renders no clinical content — the note itself lives behind `review`, which
 * keeps its own. Capture is blocked all the same, because a recipient label
 * is the patient's own words about who they are seeing.
 */
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { AnnouncedText } from "@/components/Announced";
import { useTabBarClearance } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, Screen, useStackHeader } from "@/components/Themed";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import { t } from "@/lib/i18n";
import {
  categoryLabelKey,
  formatShareMoment,
  linkState,
  revokeOffered,
  roleLabelKey,
  stateLabelKey,
} from "@/lib/shares/links";
import { loadShareCentre, revokeShare, useShareCentre } from "@/lib/shares/store";
import { spacing } from "@/lib/theme";

/** Pushed screen: the stack header owns the top inset. */
const HEADER_EDGES = ["left", "right"] as const;

export default function ShareCentre() {
  useClinicalScreenPrivacy();
  const headerOptions = useStackHeader();
  const router = useRouter();
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  const { links, log, loaded, unreachable, unsent } = useShareCentre();
  const tabBarClearance = useTabBarClearance();
  // Armed, not stopped: the first tap on a grant only changes the word, and
  // arming another disarms this one.
  const [armed, setArmed] = useState<string | null>(null);
  const visit = visitId ?? "";

  useEffect(() => {
    if (visit !== "") {
      void loadShareCentre(visit);
    }
  }, [visit]);

  return (
    <Screen edges={HEADER_EDGES}>
      <Stack.Screen options={headerOptions(t("shares.title"))} />
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: tabBarClearance }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("shares.title")}
        </AppText>
        <GuidanceBlock
          accent
          icon="person.2"
          kickerKey="shares.guide.kicker"
          titleKey="shares.guide.title"
          bodyKey="shares.guide.body"
        />
        {/* INT-311 — the act of issuing has one owner and one surface, and this
            is the way in. It is a plain navigation from the hub; the bearer
            credential it renders never touches this screen (INT-139 §3 still
            holds), only the screen it opens. */}
        <ListGroup>
          <ListRow
            icon="paperplane"
            label={t("shares.issue.entry")}
            sublabel={t("shares.issue.sub")}
            chevron
            hint={t("a11y.shares.issueHint")}
            onPress={() => router.push(`/(tabs)/visits/${visit}/issue-link`)}
          />
        </ListGroup>
        <View style={styles.section}>
          <Kicker label={t("shares.active")} />
          <ListGroup footer={emptyFooter(loaded, unreachable, links.length)}>
            {links.flatMap((link) => {
              const state = linkState(link);
              const isArmed = armed === link.id;
              const rows = [
                <ListRow
                  key={link.id}
                  icon="paperplane"
                  label={link.recipient}
                  sublabel={`${t("shares.until")}: ${formatShareMoment(link.expiresAt)}`}
                  trailing={
                    <AppText role="caption" color={state === "live" ? "primary" : "inkSoft"}>
                      {t(stateLabelKey(state))}
                    </AppText>
                  }
                />,
              ];
              if (revokeOffered(link)) {
                rows.push(
                  <ListRow
                    key={`${link.id}-stop`}
                    inset
                    label={isArmed ? t("shares.revoke.confirm") : t("shares.revoke")}
                    // Several grants carry the same control, so the row's
                    // accessible name has to say WHICH one (INT-144): the
                    // visible word first (SC 2.5.3), the recipient after.
                    labelContext={link.recipient}
                    hint={isArmed ? t("a11y.shares.confirmHint") : t("a11y.shares.revokeHint")}
                    onPress={() => {
                      if (isArmed) {
                        setArmed(null);
                        void revokeShare(visit, link.id);
                        return;
                      }
                      setArmed(link.id);
                    }}
                  />,
                );
              }
              return rows;
            })}
          </ListGroup>
          {unreachable ? (
            // In the footer's place and style, but announced (SC 4.1.3): a
            // list that could not be read must not pass for an empty one.
            <AnnouncedText
              tone="status"
              role="caption"
              color="inkFaint"
              style={styles.footerLine}
              message={t("shares.unreachable")}
            />
          ) : null}
          <AppText role="caption" color="inkSoft">
            {t("shares.revoke.effect")}
          </AppText>
          {unsent ? (
            // SC 3.3.1: the stop the patient asked for did not arrive, and the
            // share may still be open — announced as an error (INT-362).
            <AnnouncedText
              tone="error"
              role="caption"
              color="inkSoft"
              message={t("shares.revoke.unsent")}
            />
          ) : null}
        </View>
        <View style={styles.section}>
          <Kicker label={t("shares.log")} />
          <ListGroup footer={log.length === 0 ? t("shares.log.empty") : t("shares.log.noNames")}>
            {log.map((entry) => (
              <ListRow
                key={entry.seq}
                label={t(categoryLabelKey(entry.category))}
                sublabel={formatShareMoment(entry.occurredAt)}
                trailing={
                  <AppText role="caption" color="inkSoft">
                    {t(roleLabelKey(entry.role))}
                  </AppText>
                }
              />
            ))}
          </ListGroup>
        </View>
        <AppText role="caption" color="inkFaint">
          {t("shares.held")}
        </AppText>
      </ScrollView>
    </Screen>
  );
}

/**
 * The footer under the grants. "Nobody has access" and "we could not ask" are
 * different sentences, and only one of them is safe to print when it is not
 * true — so an unreachable read prints no reassuring line at all. What it
 * does say is rendered below the group as an announced status (INT-362),
 * because a footer is a quiet caption that no screen reader is told about.
 */
function emptyFooter(loaded: boolean, unreachable: boolean, count: number): string | undefined {
  if (unreachable) {
    return undefined;
  }
  return loaded && count === 0 ? t("shares.empty") : undefined;
}

const styles = StyleSheet.create({
  content: { gap: spacing.md },
  heroLine: { marginTop: spacing.xl, marginBottom: spacing.sm },
  section: { gap: spacing.sm, marginTop: spacing.sm },
  // The ListGroup footer's own inset, so the line sits where the footer did.
  footerLine: { paddingHorizontal: spacing.md },
});
