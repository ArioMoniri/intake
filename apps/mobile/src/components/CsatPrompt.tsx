/**
 * One-tap satisfaction after a sent note (INT-137; 02 §5.4).
 *
 * Three properties, each of them a rule rather than a preference:
 *
 * 1. **It cannot gate the note.** This file imports nothing from the note
 *    layer and holds no value the note path reads. It renders only from the
 *    review screen's already-sent branch, so refusing it, ignoring it or
 *    answering half of it costs the patient nothing.
 * 2. **Consent gates collection, closed.** `satisfaction` (files/06 §2) is
 *    açık rıza and default OFF. Until the patient grants it against a loaded,
 *    hash-bound text this component renders NOTHING and no score exists to
 *    collect — the gate IS the render, so there is no path where a tap is
 *    recorded first and justified afterwards. No new purpose is invented and
 *    no new data field is declared: the shape is INT-240's landed `csat.v1`.
 * 3. **No figure comes back.** Invariant 20: the answer is collected, never
 *    rendered back as a number, an average or a target.
 *
 * The controls are `Segmented` rather than new pressables, so the radiogroup
 * semantics, the MIN_TAP-by-box floor and the large-text stacking behaviour
 * are INT-260's, already proven, and this file adds no accessibility surface
 * of its own. Five options always stack, which is what five Turkish phrases
 * need at any scale.
 */
import { useReducer } from "react";

import { Segmented } from "@/components/Segmented";
import { AppText, Card, Hairline } from "@/components/Themed";
import { useConsentLedger } from "@/lib/consent/store";
import { t } from "@/lib/i18n";
import {
  CSAT_REASONS,
  CSAT_SCORES,
  csatCollectable,
  csatReducer,
  emptyCsat,
} from "@/lib/intake/csat";

export function CsatPrompt() {
  const ledger = useConsentLedger();
  const [state, dispatch] = useReducer(csatReducer, emptyCsat());
  // Fail closed: without the files/06 §2 `satisfaction` grant there is no
  // question on screen, so there is nothing to answer and nothing to hold.
  if (!csatCollectable(ledger)) {
    return null;
  }
  const chosen = CSAT_SCORES.find((entry) => entry.score === state.score) ?? null;
  return (
    <Card>
      {/* The question is the card's own heading (SC 1.3.1), not an eyebrow —
          it is addressed to the patient rather than naming a section. */}
      <AppText role="title" heading>
        {t("csat.title")}
      </AppText>
      <Hairline />
      <AppText role="caption" color="inkSoft">
        {t("csat.optional")}
      </AppText>
      <Segmented
        label={t("csat.scoreGroup")}
        options={CSAT_SCORES.map((entry) => ({ id: entry.id, label: t(entry.labelKey) }))}
        value={chosen === null ? null : chosen.id}
        hint={t("a11y.selectHint")}
        onChange={(id) => {
          const picked = CSAT_SCORES.find((entry) => entry.id === id);
          if (picked !== undefined) {
            dispatch({ type: "score", score: picked.score });
          }
        }}
      />
      {state.score === null ? null : (
        <>
          <Segmented
            label={t("csat.reasonGroup")}
            options={CSAT_REASONS.map((entry) => ({ id: entry.id, label: t(entry.labelKey) }))}
            value={state.reason}
            hint={t("a11y.selectHint")}
            onChange={(id) => {
              const picked = CSAT_REASONS.find((entry) => entry.id === id);
              if (picked !== undefined) {
                dispatch({ type: "reason", reason: picked.id });
              }
            }}
          />
          <AppText role="caption" color="inkSoft">
            {t("csat.thanks")}
          </AppText>
        </>
      )}
    </Card>
  );
}
