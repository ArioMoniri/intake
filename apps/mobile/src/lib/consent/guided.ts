/**
 * Guided-sweep ordering (INT consent UX redesign) — a read-only projection of
 * `viewOf`, added beside the ledger without touching it.
 *
 * The İzinleriniz redesign grants inline: a row expands to its hash-bound text
 * and a Grant button, so a patient never leaves the screen and comes back. The
 * optional "grant each remaining permission in turn" affordance uses these two
 * selectors to walk the still-grantable purposes one at a time.
 *
 * They add NO policy. A purpose is grantable iff `viewOf` already said so
 * (`view.grantable`) — which is false whenever the text is not loaded (fail
 * closed, invariant 18), the purpose is already on, it is `info` (core), or it
 * is `lane:affect` without a standing voice consent. These functions only
 * order and pick from that set; the grant rules stay in one place, the ledger.
 */
import type { PurposeView } from "./ledger";
import type { PurposeId } from "./purposes";

/**
 * The purposes the patient can grant right now, in the 06 §2 registry order
 * the list already renders. `viewOf` returns views in registry order, so a
 * plain filter preserves it. Computed from LIVE views, so a purpose that only
 * becomes grantable mid-sweep — `lane:affect`, once `voice` is granted — joins
 * the walk on the next pass rather than being skipped.
 */
export function remainingGrantable(views: readonly PurposeView[]): readonly PurposeId[] {
  return views.filter((view) => view.grantable).map((view) => view.id);
}

/**
 * The next purpose the guided sweep should expand: the earliest still-grantable
 * one, or null when none remain (the sweep is complete, or no text has loaded
 * so there was never anywhere to go).
 */
export function firstGrantable(views: readonly PurposeView[]): PurposeId | null {
  return remainingGrantable(views)[0] ?? null;
}
