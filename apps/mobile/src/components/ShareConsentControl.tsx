/**
 * INT-587 — the patient takes the share consent back, from the share centre.
 *
 * The share consent is granted at each send and has no İzinleriniz row (a
 * bare share toggle would be the bundled consent files/06 §2 forbids), so the
 * place to withdraw it is the hub over the shares it governs. share.tr.md
 * says what follows: every open link closes. The server does that in the same
 * pass as the withdrawal (consents.py → withdraw_consent revokes every live
 * share and Doctor Link), and refuses new links on its own record afterwards.
 *
 * Kept apart from the share centre's stop control on purpose: stopping ONE
 * link must never depend on a consent value (INT-150 §6, e2e/shares.spec.ts),
 * and this control is about the consent itself. It is the INT-140 two-step —
 * the first tap only changes the words — and, like the stop control, it says
 * the consent is withdrawn only once the server has the withdrawal: a patient
 * told their links are closed stops checking, so an unsent withdrawal says so.
 *
 * On this phone the withdrawal is instant: anything still queued for delivery
 * is held back before the server even hears of it (no share without the grant).
 */
import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import { AnnouncedText } from "@/components/Announced";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText } from "@/components/Themed";
import { seedLedgerForAccount, useConsentLedger, withdrawShareLocal } from "@/lib/consent/store";
import { t } from "@/lib/i18n";
import { holdDeliveriesForConsent } from "@/lib/intake/delivery/store";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

type Outcome = "none" | "landed" | "unsent";

export function ShareConsentControl({ onWithdrawn }: { onWithdrawn: () => void }) {
  const { account, consents } = useSession();
  // Only the standing is read here — no legal text is rendered on this control,
  // so the share centre stays an ordinary route (motion/transitions.ts).
  const standing = useConsentLedger().share.standing;
  const [armed, setArmed] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>("none");
  // Offered unless withdrawn here already: the server may hold a grant from an
  // earlier session that this phone never saw.
  const withdrawable = standing !== "withdrawn";

  // Seed before any change: seeding later would replace the working copy, and
  // a withdrawal still queued in it would be lost with it.
  useEffect(() => {
    if (account !== null) {
      seedLedgerForAccount(account.id, consents);
    }
  }, [account, consents]);

  const withdraw = async () => {
    setArmed(false);
    await holdDeliveriesForConsent();
    const landed = await withdrawShareLocal();
    setOutcome(landed ? "landed" : "unsent");
    if (landed) {
      onWithdrawn();
    }
  };

  return (
    <View style={styles.section}>
      <Kicker label={t("shares.consent.title")} />
      {withdrawable ? (
        <ListGroup>
          <ListRow
            label={armed ? t("shares.consent.confirm") : t("shares.consent.withdraw")}
            hint={armed ? t("a11y.shares.consentConfirmHint") : t("a11y.shares.consentHint")}
            onPress={() => {
              if (armed) {
                void withdraw();
                return;
              }
              setArmed(true);
            }}
          />
        </ListGroup>
      ) : null}
      <AppText role="caption" color="inkSoft">
        {t("shares.consent.effect")}
      </AppText>
      {outcome === "landed" ? (
        <AnnouncedText
          tone="status"
          role="caption"
          color="inkSoft"
          message={t("shares.consent.done")}
        />
      ) : null}
      {outcome === "unsent" ? (
        <AnnouncedText
          tone="error"
          role="caption"
          color="inkSoft"
          message={t("shares.consent.unsent")}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.sm, marginTop: spacing.sm },
});
