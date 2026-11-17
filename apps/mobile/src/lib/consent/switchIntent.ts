/**
 * What a tap on an İzinleriniz switch does (INT-603, design audit 2026-11 K2).
 *
 * The state control used to be a pill that withdrew on one tap when it read
 * "Açık" and opened the text when it read anything else: one look, two
 * actions. It is now a switch, and the two directions are told apart here:
 *
 * - turning something ON needs no confirmation of its own. It opens layer 2,
 *   where the patient grants against the versioned, hash-bound text — the only
 *   place a grant can happen (invariant 18). A pending or stale row goes there
 *   too: its switch is off, and the detail holds the re-approval and the
 *   withdraw control a standing record keeps;
 * - turning something OFF asks once. The confirmation names what stops — the
 *   purpose and every granted purpose its cascade takes down, exactly the set
 *   `withdraw()` flips — and says that it takes effect immediately, using the
 *   catalogue fact the detail screen already states. Asking changes nothing:
 *   only the confirmed withdrawal queues the op the server records and audits
 *   (invariant 4).
 *
 * Withdrawal stays as easy as grant (files/06 §2): two taps each from the list
 * (switch + confirm; row + "Okudum, kabul ediyorum").
 *
 * The two default-on learning rows sit on the registry's non-consent bases
 * (service performance, de-identified opt-out), so turning one off is an
 * opt-out and is worded as one. Whether those grounds carry health data is
 * the open HB-L27 question; this wording makes no claim either way.
 */
import type { MessageKey } from "@/lib/i18n";

import type { PurposeView } from "./ledger";
import { purposeDef, type PurposeId } from "./purposes";

export type SwitchIntent = "open_detail" | "confirm_withdraw";

export interface WithdrawConfirmation {
  id: PurposeId;
  titleKey: MessageKey;
  /** Label keys of everything that stops, the tapped purpose first. */
  stopKeys: readonly MessageKey[];
  /** The "takes effect immediately" line. */
  noteKey: MessageKey;
  actionKey: MessageKey;
  cancelKey: MessageKey;
}

/** An açık rıza purpose — a consent scope in the files/06 §2 sense. */
export function isConsentScope(view: PurposeView): boolean {
  return view.basis === "explicit_consent";
}

/** The switch shows what is honoured: granted and not stale. */
export function switchChecked(view: PurposeView): boolean {
  return view.display === "on";
}

export function switchIntent(view: PurposeView): SwitchIntent {
  return switchChecked(view) && view.withdrawable ? "confirm_withdraw" : "open_detail";
}

/**
 * The confirmation for turning `id` off, or null when the switch would not
 * ask (it is off, so a tap opens the text instead).
 */
export function withdrawConfirmation(
  views: readonly PurposeView[],
  id: PurposeId,
): WithdrawConfirmation | null {
  const view = views.find((v) => v.id === id);
  const def = purposeDef(id);
  if (view === undefined || def === null || switchIntent(view) !== "confirm_withdraw") {
    return null;
  }
  const byId = new Map(views.map((v) => [v.id, v]));
  const stopKeys = [id, ...def.cascadeChildren]
    .map((scope) => byId.get(scope))
    .filter((v): v is PurposeView => v !== undefined && v.withdrawable)
    .map((v) => v.labelKey);
  const consent = isConsentScope(view);
  return {
    id,
    titleKey: consent ? "consent.confirm.withdrawTitle" : "consent.confirm.optoutTitle",
    stopKeys,
    noteKey: consent ? "consent.detail.withdrawNote" : "consent.confirm.optoutNote",
    actionKey: consent ? "consent.detail.withdraw" : "consent.confirm.optoutAction",
    cancelKey: "consent.confirm.cancel",
  };
}
