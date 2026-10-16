/**
 * The visit-start gate (INT-537). Visits and their notes are processed under
 * the `core` açık rıza scope — services/api declares it on every visit and
 * note route, and refuses without it. The app asks for it where it is needed,
 * at the start of a visit, and reads the answer from the consent ledger the
 * İzinleriniz screens write, so the screen and the server decide alike:
 *
 * - open: an honoured core grant (bound to the current text, or an unbound
 *   dev seed while no text exists — the server's own semantics);
 * - shut, stale: the core text moved since the grant, so the patient is
 *   asked to read the NEW text, never told they never agreed;
 * - shut: no core grant.
 *
 * Pure and node-testable. It reads core and nothing else: an optional
 * purpose never gates a visit (files/02 §7).
 */
import { viewOf, type LedgerState } from "./ledger";

export type CoreGate = { open: true } | { open: false; stale: boolean };

export function coreGate(state: LedgerState): CoreGate {
  const core = viewOf(state).find((view) => view.id === "core");
  if (core !== undefined && core.allowed) {
    return { open: true };
  }
  return { open: false, stale: core?.display === "stale" };
}
